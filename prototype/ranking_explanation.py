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
from .scoring import POLICY_VERSION, rank, score

INTEGRATED = True
MAX_DECIDING = 3

Status = Literal['full', 'partial', 'fail', 'unknown']
Caveat = Literal['different_requirement_lists', 'incomplete_run', 'evidence_not_applied']


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


class Swing(StrictModel):
    row: RowRef
    assumed_status: Literal['full', 'fail']
    result: Literal['reversed', 'tie', 'breaks_tie']


class JobScore(StrictModel):
    rank: int
    lower: float
    upper: float
    coverage: float
    mandatory: str


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
        if reported.get('policy_version') != POLICY_VERSION:
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
        self.disputed = set(self.score['disputed_ids']) | self.unscored_review
        self.mandatory = {r.id for r in self.requirements.items if r.mandatory_quote} - set(
            self.score['excluded_mandatory_ids'])
        self.quotes = {r.id: r.quote for r in self.requirements.items}
        self.by_key = {_key(r.quote): r.id for r in self.requirements.items}
        self.status = {row.requirement_id: row.status for row in self.evaluation.rows}
        if any(f not in facts for row in self.evaluation.rows for f in row.fact_ids):
            raise ValueError('unknown_fact')
        self.cv_quotes = {row.requirement_id: [facts[f] for f in row.fact_ids] for row in self.evaluation.rows}

    def rescore(self, requirement_id: str | None = None, status: str | None = None) -> dict:
        """Score as reported, or with one row resolved to `status` (structurally confirmed)."""
        evaluation, evidence = self.evaluation, self.evidence
        if requirement_id is not None:
            evaluation = Evaluation(rows=[
                r.model_copy(update={'status': status}) if r.requirement_id == requirement_id else r
                for r in evaluation.rows])
            if evidence is not None:
                state = 'no_evidence' if status == 'unknown' else 'structure_ok'
                evidence = evidence.model_copy(update={'rows': [
                    c.model_copy(update={'status': status, 'state': state}) if c.requirement_id == requirement_id
                    else c for c in evidence.rows]})
        return score(self.requirements, evaluation, evidence)

    def contribution(self, rid: str) -> float:
        """Points of L the row gives now: L minus L with the row unknown."""
        return self.score['lower'] - self.rescore(rid, 'unknown')['lower']

    def ref(self, rid: str, effect: float, counterpart: str | None = None) -> RowRef:
        return RowRef(job_id=self.id, requirement_id=rid, requirement_quote=self.quotes[rid], status=self.status[rid],
                      counterpart_status=counterpart, mandatory_applied=rid in self.mandatory,
                      disputed=rid in self.disputed, cv_quotes=self.cv_quotes[rid], effect=round(effect, 4))

    def unresolved(self) -> list[str]:
        return sorted(rid for rid, st in self.status.items() if st == 'unknown' or rid in self.disputed)

    def scale(self) -> list[tuple[str, bool]]:
        return sorted((_key(r.quote), r.id in self.mandatory) for r in self.requirements.items)


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
        refs += [loss(rid) for rid in sorted(low.status)
                 if low.status[rid] == 'fail' and rid in low.mandatory and rid not in low.disputed]
    if paired:  # same requirements and weights: rows that differ, by the gap they make in L (equal rows give 0)
        pairs = [(high.by_key[k], rid) for k, rid in sorted(low.by_key.items())]
        candidates = [low.ref(lr, high.contribution(hr) - low.contribution(lr), counterpart=high.status[hr])
                      for hr, lr in pairs if hr not in high.unresolved() and lr not in low.unresolved()]
        candidates.sort(key=lambda r: (-r.effect, r.requirement_id))
    else:  # different lists: the largest loss of the lower job, then the largest gains of the higher one
        losses = sorted((loss(rid) for rid in low.status if rid not in low.unresolved()),
                        key=lambda r: (-r.effect, r.requirement_id))
        gains = sorted((high.ref(rid, high.contribution(rid)) for rid in high.status if rid not in high.unresolved()),
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
        for rid in job.unresolved():
            changed = job.rescore(rid, assumed)
            new = _order(changed, other.score) if first else _order(other.score, changed)
            if new == outcome:
                continue
            result = 'breaks_tie' if outcome == 'tie' else 'tie' if new == 'tie' else 'reversed'
            swings.append(Swing(row=job.ref(rid, changed['lower'] - job.score['lower']), assumed_status=assumed,
                                result=result))
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
    caveats = ((['different_requirement_lists'] if not paired else [])
               + (['incomplete_run'] if not report['ranking'].get('complete', True) else [])
               + (['evidence_not_applied'] if a.unscored_review or b.unscored_review else []))
    return Comparison(
        policy_version=POLICY_VERSION, job_a=job_a, job_b=job_b, outcome=outcome, reason=reason,
        scores={j.id: JobScore(rank=j.rank, **{k: j.score[k] for k in ('lower', 'upper', 'coverage', 'mandatory')})
                for j in (a, b)},
        deciding=deciding, swings=swings, caveats=caveats,
        summary=_summary(a, b, outcome, reason, deciding, swings, caveats, paired))
