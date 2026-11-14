"""Why one vacancy is above another (E7). A pure function over a finished report.

The comparison re-runs `scoring.score` and `scoring.rank` on the report's own requirements,
rows and evidence, so it uses exactly the formula the ranking used, and refuses a report whose
scores it cannot reproduce. It references only existing requirement ids, quotes and fact quotes:
no model call and no new facts.

- outcome: the order of the two jobs under the policy, or 'tie' when they share a place;
- reason: a violated mandatory requirement on one side, or a higher lower bound L;
- deciding: up to three rows that explain the gap: violated mandatory rows first; for the same
  requirement list only the rows that differ between the jobs, by the gap they make in L; for
  different lists the lower job's largest loss and the higher job's largest contributions;
- swings: unresolved rows (unknown or disputed) whose single resolution would reverse or tie the
  order (or break a tie). This is a sensitivity check, not a prediction of the recruiter's answer.

Different vacancies usually have different requirement lists or weights; L is a share of each
vacancy's own weight, so the comparison carries the caveat 'different_requirement_lists'. For a
report scored without evidence (v1), rows E3 sent to review are marked disputed and kept out of
`deciding`, with the caveat 'evidence_not_applied'. A malformed report raises ValueError.
Wired into the pipeline; see docs/28-local-app-runbook.md.
"""
from typing import Literal

from pydantic import ValidationError

from .contracts import Evaluation, Requirements, StrictModel
from .evidence import PairCheck
from .scoring import POLICIES, POLICY_VERSION, _norm, is_close, rank, score

INTEGRATED = True
MAX_DECIDING = 3

Status = Literal['full', 'partial', 'fail', 'unknown']
Caveat = Literal['different_requirement_lists', 'incomplete_run', 'evidence_not_applied', 'close_margin']


class RowRef(StrictModel):
    job_id: str
    requirement_id: str
    requirement_quote: str
    status: Status
    counterpart_status: Status | None  # status of the same requirement in the other job, if both lists have it
    mandatory_applied: bool
    disputed: bool
    cv_quotes: list[str]
    effect: float  # percentage points of L: added by the row (higher job), lost (lower job), or the pair gap


class JobScore(StrictModel):
    rank: int
    lower: float
    upper: float
    coverage: float
    mandatory: str


class Swing(StrictModel):
    row: RowRef
    assumed_status: Literal['full', 'fail']
    result: Literal['reversed', 'tie', 'breaks_tie']
    hypothetical_score: JobScore | None = None


class Comparison(StrictModel):
    policy_version: str
    job_a: str
    job_b: str
    outcome: Literal['a_higher', 'b_higher', 'tie']
    reason: Literal['mandatory_violation', 'lower_bound', 'tie']
    scores: dict[str, JobScore]
    deciding: list[RowRef]
    swings: list[Swing]
    caveats: list[Caveat]
    summary: str
    margin: float | None = None  # L of the higher job minus L of the lower one, in points
    close: bool = False  # v3: the gap is below one status step of the coarser list; the order is not established


def _key(quote: str) -> str:
    return quote.strip().casefold()


class _Job:
    """One job of the report with the exact inputs that reproduce its reported score."""

    def __init__(self, job: dict, facts: dict[str, str]):
        self.id = job['job_id']
        self.rank = job['rank']
        self.requirements = Requirements.model_validate(job['requirements'])
        self.evaluation = Evaluation.model_validate(job['evaluation'])
        reported = job['score']
        self.policy = reported.get('policy_version')
        if self.policy not in POLICIES:  # a report is explained only by the policy that scored it
            raise ValueError('policy_mismatch')
        checks = PairCheck.model_validate(job['evidence_check']) if 'evidence_check' in job else None
        if reported.get('evidence_applied'):
            if checks is None:
                raise ValueError('incomplete_report')
            self.evidence = checks
        else:  # v1 call: the pipeline stripped unbound mandatory markers before scoring
            self.evidence = None
            excluded = set(job.get('score_review', {}).get('excluded_mandatory_ids', []))
            self.requirements = Requirements(items=[
                r.model_copy(update={'mandatory_quote': None}) if r.id in excluded else r
                for r in self.requirements.items])
        self.score = self.rescore()
        if any(self.score[k] != reported[k] for k in ('lower', 'upper', 'coverage', 'mandatory')):
            raise ValueError('score_not_reproducible')
        # Under v1 the score ignored E3; rows E3 sent to review are still disputed for the explanation.
        self.unscored_review = set() if self.evidence is not None or checks is None else {
            c.requirement_id for c in checks.rows if c.state == 'needs_review'}
        # v3: rows of one requirement unit act together; repeats with conflicting statuses are disputed too.
        units = [u['ids'] for u in self.score.get('units', [])] or [[r.id] for r in self.requirements.items]
        self.unit = {rid: ids for ids in units for rid in ids}
        states = {tuple(u['ids']): u['state'] for u in self.score.get('units', [])}
        rows = {row.requirement_id: row.status for row in self.evaluation.rows}
        # One row stands for its unit in every walk below: a row that carries the unit's own status.
        self.reps = [next((i for i in ids if rows[i] == states.get(tuple(ids))), ids[0]) for ids in units]
        self.open_units = {rid for u in self.score.get('units', []) if u['state'] not in ('full', 'partial', 'fail')
                           for rid in u['ids']}
        self.disputed = (set(self.score['disputed_ids']) | self.unscored_review
                         | set(self.score.get('conflict_ids', [])))
        self.mandatory = {r.id for r in self.requirements.items if r.mandatory_quote} - set(
            self.score['excluded_mandatory_ids'])
        self.quotes = {r.id: r.quote for r in self.requirements.items}
        self.by_key = {_key(r.quote): r.id for r in self.requirements.items}
        self.status = {row.requirement_id: row.status for row in self.evaluation.rows}
        if any(f not in facts for row in self.evaluation.rows for f in row.fact_ids):
            raise ValueError('unknown_fact')
        self.cv_quotes = {row.requirement_id: [facts[f] for f in row.fact_ids] for row in self.evaluation.rows}

    def rescore(self, requirement_id: str | None = None, status: str | None = None) -> dict:
        """Score as reported, or with one requirement resolved to `status` (structurally confirmed).
        Under v3 every row of the requirement's unit is resolved together; v2 stays row by row."""
        evaluation, evidence = self.evaluation, self.evidence
        if requirement_id is not None:
            ids = set(self.unit[requirement_id])
            evaluation = Evaluation(rows=[
                r.model_copy(update={'status': status}) if r.requirement_id in ids else r
                for r in evaluation.rows])
            if evidence is not None:
                state = 'no_evidence' if status == 'unknown' else 'structure_ok'
                evidence = evidence.model_copy(update={'rows': [
                    c.model_copy(update={'status': status, 'state': state}) if c.requirement_id in ids
                    else c for c in evidence.rows]})
        return score(self.requirements, evaluation, evidence, policy=self.policy)

    def contribution(self, rid: str) -> float:
        """Points of L the row gives now: L minus L with the row unknown."""
        return self.score['lower'] - self.rescore(rid, 'unknown')['lower']

    def ref(self, rid: str, effect: float, counterpart: str | None = None) -> RowRef:
        return RowRef(job_id=self.id, requirement_id=rid, requirement_quote=self.quotes[rid], status=self.status[rid],
                      counterpart_status=counterpart, mandatory_applied=rid in self.mandatory,
                      disputed=rid in self.disputed, cv_quotes=self.cv_quotes[rid], effect=round(effect, 4))

    def unresolved(self) -> list[str]:
        """Rows still open. v3: the rows of units without a counted state (a silent repeat of a known
        requirement is not open); v2: unknown or disputed rows."""
        if 'units' in self.score:
            return sorted(self.open_units | (self.unscored_review & set(self.status)))
        return sorted(rid for rid, st in self.status.items() if st == 'unknown' or rid in self.disputed)

    def pairs_with(self, low: '_Job') -> list[tuple[str, str]]:
        """(own row, row of `low`) for the same requirement. v3 pairs the representatives of units, which
        carry the unit's status, so a silent repeat never stands for a confirmed requirement."""
        if 'units' not in self.score:
            return [(self.by_key[k], rid) for k, rid in sorted(low.by_key.items())]
        mine = {_norm(self.quotes[i]): rep for rep in self.reps for i in self.unit[rep]}
        found = {(mine[_norm(low.quotes[i])], rep) for rep in low.reps for i in low.unit[rep]
                 if _norm(low.quotes[i]) in mine}
        return sorted(found, key=lambda p: (p[1], p[0]))

    def open_reps(self) -> list[str]:
        open_rows = set(self.unresolved())
        return [rid for rid in sorted(self.reps) if rid in open_rows]

    def known_reps(self) -> list[str]:
        open_rows = set(self.unresolved())
        return [rid for rid in sorted(self.reps) if rid not in open_rows]

    def scale(self) -> list[tuple[str, bool]]:
        return sorted((_key(r.quote), r.id in self.mandatory) for r in self.requirements.items)


def _one_policy(report: dict, jobs) -> None:
    """Every job of the report, and the report itself, name one policy; a mixed report is refused."""
    versions = {(j.get('score') or {}).get('policy_version') for j in jobs}
    if len(versions) != 1 or report.get('policy_version', next(iter(versions))) not in versions:
        raise ValueError('policy_mismatch')


def _order(a: dict, b: dict) -> Literal['a_higher', 'b_higher', 'tie']:
    """The order of two scores under scoring.rank itself."""
    ranked = rank([{'job_id': 'a', 'score': a}, {'job_id': 'b', 'score': b}], 2)['jobs']
    places = {j['job_id']: j['rank'] for j in ranked}
    return 'tie' if places['a'] == places['b'] else 'a_higher' if places['a'] < places['b'] else 'b_higher'


def _deciding(high: _Job, low: _Job, reason: str, paired: bool) -> list[RowRef]:
    def loss(rid):
        return low.ref(rid, low.rescore(rid, 'full')['lower'] - low.score['lower'])

    refs = []
    if reason == 'mandatory_violation':  # the violated mandatory rows explain the order first
        refs += [loss(rid) for rid in low.known_reps()
                 if low.status[rid] == 'fail' and rid in low.mandatory and rid not in low.disputed]
    if paired:  # same requirements and weights: rows that differ, by the gap they make in L (equal rows give 0)
        pairs = high.pairs_with(low)
        candidates = [low.ref(lr, high.contribution(hr) - low.contribution(lr), counterpart=high.status[hr])
                      for hr, lr in pairs if hr not in high.unresolved() and lr in low.known_reps()]
        candidates.sort(key=lambda r: (-r.effect, r.requirement_id))
    else:  # different lists: the largest loss of the lower job, then the largest gains of the higher one
        losses = sorted((loss(rid) for rid in low.known_reps()),
                        key=lambda r: (-r.effect, r.requirement_id))
        gains = sorted((high.ref(rid, high.contribution(rid)) for rid in high.known_reps()),
                       key=lambda r: (-r.effect, r.requirement_id))
        candidates = losses[:1] + sorted(gains + losses[1:], key=lambda r: (-r.effect, r.job_id, r.requirement_id))
    seen = {(r.job_id, r.requirement_id) for r in refs}
    refs += [r for r in candidates if r.effect > 0 and (r.job_id, r.requirement_id) not in seen]
    return refs[:MAX_DECIDING]


def _swings(a: _Job, b: _Job, outcome: str) -> list[Swing]:
    swings = []
    for job, other, first in ((a, b, True), (b, a, False)):
        if outcome == 'tie':
            assumed = 'full'
        else:
            higher = (outcome == 'a_higher') == first
            assumed = 'fail' if higher else 'full'
        for rid in job.open_reps():  # one swing per requirement unit
            changed = job.rescore(rid, assumed)
            new = _order(changed, other.score) if first else _order(other.score, changed)
            if new == outcome:
                continue
            result = 'breaks_tie' if outcome == 'tie' else 'tie' if new == 'tie' else 'reversed'
            # The alternative rank is within this pair. The published ranking is untouched.
            pair_rank = 1 if new in ('tie', 'a_higher' if first else 'b_higher') else 2
            alternative = JobScore(rank=pair_rank, **{k: changed[k] for k in ('lower', 'upper', 'coverage', 'mandatory')})
            swings.append(Swing(row=job.ref(rid, changed['lower'] - job.score['lower']), assumed_status=assumed,
                                result=result, hypothetical_score=alternative))
    return swings


def _summary(a: _Job, b: _Job, outcome: str, reason: str, deciding: list[RowRef], swings: list[Swing],
             caveats: list[str], paired: bool) -> str:
    groups = f'обязательные: {a.id} — {a.score["mandatory"]}, {b.id} — {b.score["mandatory"]}'
    if outcome == 'tie':
        text = f'{a.id} и {b.id} делят место: L = {a.score["lower"]}; {groups}.'
    else:
        high, low = (a, b) if outcome == 'a_higher' else (b, a)
        bounds = f'нижняя граница {high.score["lower"]} против {low.score["lower"]}'
        if reason == 'mandatory_violation':
            text = f'{high.id} выше {low.id}: модель предложила у {low.id} несоответствие обязательному требованию.'
        elif high.score['mandatory'] == 'violated':
            text = (f'{high.id} выше {low.id}: модель предложила у обеих несоответствие обязательному требованию, '
                    f'{bounds}.')
        else:
            text = f'{high.id} выше {low.id}: {bounds}; {groups}.'
        if deciding:
            if paired:
                text += ' Различия: ' + '; '.join(
                    f'«{r.requirement_quote}» — у {low.id} {r.status}, у {high.id} {r.counterpart_status}'
                    if r.counterpart_status else f'«{r.requirement_quote}» — у {r.job_id} {r.status}'
                    for r in deciding) + '.'
            else:
                text += ' Наибольший вклад: ' + '; '.join(
                    f'{r.job_id} «{r.requirement_quote}» — {r.status}' for r in deciding) + '.'
    if swings:
        text += ' Вывод может измениться после уточнения: ' + '; '.join(
            f'{s.row.job_id} «{s.row.requirement_quote}»' for s in swings) + '.'
    if 'different_requirement_lists' in caveats:
        text += ' Списки требований или их веса разные: L считается внутри своей вакансии.'
    if 'close_margin' in caveats:
        text += (' Разрыв меньше одного шага оценки одного требования в более коротком списке: '
                 'превосходство по проценту не установлено, сравните вакансии по существу.')
    if 'evidence_not_applied' in caveats:
        text += ' Балл посчитан без учёта спорных доказательств; такие строки помечены и в различия не входят.'
    if 'incomplete_run' in caveats:
        text += ' Обработаны не все вакансии.'
    return text


def compare(report: dict, job_a: str, job_b: str) -> Comparison:
    if job_a == job_b:
        raise ValueError('same_job')
    try:
        jobs = {j['job_id']: j for j in report['ranking']['jobs']}
        if job_a not in jobs or job_b not in jobs:
            raise ValueError('unknown_job')
        facts = {f['id']: f['quote'] for f in report['facts']['items']}
        a, b = _Job(jobs[job_a], facts), _Job(jobs[job_b], facts)
    except (KeyError, TypeError, ValidationError):
        raise ValueError('incomplete_report') from None
    _one_policy(report, jobs.values())

    paired = a.scale() == b.scale()
    outcome = _order(a.score, b.score)
    if outcome == 'tie':
        reason, deciding = 'tie', []
    else:
        high, low = (a, b) if outcome == 'a_higher' else (b, a)
        violated = {j.id for j in (a, b) if j.score['mandatory'] == 'violated'}
        reason = 'mandatory_violation' if violated == {low.id} else 'lower_bound'
        deciding = _deciding(high, low, reason, paired)
    swings = _swings(a, b, outcome)
    margin = None if outcome == 'tie' else round(abs(a.score['lower'] - b.score['lower']), 4)
    # The same rule `rank` applies to the first place: one status step of the coarser list of units.
    close = (a.policy == POLICY_VERSION and outcome != 'tie' and reason == 'lower_bound'
             and is_close(a.score, b.score))
    caveats = ((['different_requirement_lists'] if not paired else [])
               + (['incomplete_run'] if not report['ranking'].get('complete', True) else [])
               + (['evidence_not_applied'] if a.unscored_review or b.unscored_review else [])
               + (['close_margin'] if close else []))
    return Comparison(
        margin=margin, close=close,
        policy_version=a.policy, job_a=job_a, job_b=job_b, outcome=outcome, reason=reason,
        scores={j.id: JobScore(rank=j.rank, **{k: j.score[k] for k in ('lower', 'upper', 'coverage', 'mandatory')})
                for j in (a, b)},
        deciding=deciding, swings=swings, caveats=caveats,
        summary=_summary(a, b, outcome, reason, deciding, swings, caveats, paired))


# ---------- first place (E11, policy v3) ---------------------------------------------------------

class Change(StrictModel):
    """A row whose resolution could change the first place. A sensitivity check, not a forecast."""
    row: RowRef  # effect: points of L the resolution can move
    kind: Literal['unknown', 'disputed', 'partial', 'marker']
    role: Literal['leader', 'challenger']
    requirement_ids: list[str] = []  # every row of the requirement unit; `row` is its representative


class LeaderExplanation(StrictModel):
    policy_version: str
    job_ids: list[str]
    state: Literal['stable', 'tie', 'close', 'open', 'none_fit']
    reasons: list[str]
    factors: list[RowRef]  # up to three confirmed rows that give the leader most of its L
    limits: list[RowRef]  # up to three rows where the leader loses or lacks points
    condition_conflicts: list[str]  # E5 kinds; shown apart, they never enter the score
    can_change: list[Change]
    challengers: list[str]
    close_to: list[str]
    unassessed: list[str]
    summary: str


_STATE_TEXT = {
    'stable': 'Первое место устойчиво: ни чтение спорных строк, ни один-два ответа кандидата его не меняют.',
    'tie': 'Первое место делят несколько вакансий с равной оценкой.',
    'close': 'Первое место не установлено: отрыв меньше одного шага оценки одного требования.',
    'open': 'Первое место предварительное: его могут изменить перечисленные уточнения.',
    'none_fit': 'У всех вакансий модель предложила несоответствие обязательному требованию; решение за HR.',
}


def explain_leader(report: dict) -> LeaderExplanation | None:
    """Two or three deciding factors of the first place, its limits and what could change it.

    Built only from the report and re-checked against `scoring.rank`: the explanation is refused
    ('score_not_reproducible') when the stored leader block differs from the recomputed one.
    Returns None for a report scored by a policy without a leader analysis (v2) or with no jobs."""
    try:
        ranking = report['ranking']
        if not ranking['jobs'] or 'leader' not in ranking:
            return None
        facts = {f['id']: f['quote'] for f in report['facts']['items']}
        _one_policy(report, ranking['jobs'])
        jobs = {j['job_id']: _Job(j, facts) for j in ranking['jobs']}
    except (KeyError, TypeError, ValidationError):
        raise ValueError('incomplete_report') from None
    again = rank([{'job_id': j.id, 'score': j.score} for j in jobs.values()], len(jobs))
    leader = again['leader']
    if leader != ranking['leader'] or {j['job_id']: j['rank'] for j in again['jobs']} != {
            j.id: j.rank for j in jobs.values()}:
        raise ValueError('score_not_reproducible')

    top = [jobs[i] for i in leader['job_ids']]
    factors, limits = [], []
    for job in top:
        for rid in job.open_reps():
            limits.append(job.ref(rid, sum(job.score['weights'][i] for i in job.unit[rid])))
        for rid in job.known_reps():
            if job.status[rid] != 'full':
                limits.append(job.ref(rid, job.rescore(rid, 'full')['lower'] - job.score['lower']))
            if job.status[rid] != 'fail':
                factors.append(job.ref(rid, job.contribution(rid)))
    order = lambda r: (not r.mandatory_applied, -r.effect, r.job_id, r.requirement_id)
    conflicts = sorted({k for j in ranking['jobs'] if j['job_id'] in leader['job_ids']
                        for k in (j.get('conditions') or {}).get('conflicts', [])})
    changes = [Change(row=jobs[d['job_id']].ref(d['requirement_id'], d['effect']), kind=d['kind'], role=d['role'],
                      requirement_ids=d['requirement_ids'])
               for d in leader['decisive']]
    factors = sorted((r for r in factors if r.effect > 0), key=order)[:MAX_DECIDING]
    limits = sorted(limits, key=order)[:MAX_DECIDING]

    names = ', '.join(leader['job_ids'])
    text = f'{names}: {_STATE_TEXT[leader["state"]]}'
    if factors and leader['state'] != 'none_fit':
        text += ' Решающие основания: ' + '; '.join(
            f'«{r.requirement_quote}» — {r.status}, {r.effect} п' for r in factors) + '.'
    if limits:
        text += ' Ограничения: ' + '; '.join(
            f'«{r.requirement_quote}» — {"спорно" if r.disputed else r.status}' for r in limits) + '.'
    if conflicts:
        text += ' Условия работы расходятся (' + ', '.join(conflicts) + '): в оценку не входят, решает HR.'
    if changes:
        text += ' Может изменить выбор: ' + '; '.join(
            f'{c.row.job_id} «{c.row.requirement_quote}»' for c in changes) + '.'
    if leader['close_to']:
        text += ' Близкие вакансии: ' + ', '.join(leader['close_to']) + '.'
    if leader['unassessed']:
        text += (' Без подтверждённых совпадений: ' + ', '.join(leader['unassessed'])
                 + ' — это отсутствие сведений, не отказ.')
    if not ranking.get('complete', True):
        text += ' Обработаны не все вакансии: место предварительное.'
    return LeaderExplanation(
        policy_version=top[0].policy, job_ids=leader['job_ids'], state=leader['state'], reasons=leader['reasons'],
        factors=factors, limits=limits, condition_conflicts=conflicts, can_change=changes,
        challengers=[c['job_id'] for c in leader['challengers']], close_to=leader['close_to'],
        unassessed=leader['unassessed'], summary=text)
