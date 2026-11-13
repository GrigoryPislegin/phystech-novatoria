"""What if one open requirement were resolved? (E7 what-if). A pure, hypothetical projection.

`what_if(report, job_id, requirement_id, assumed_status)`:
- only an open row can be asked about: status `unknown`, or evidence that E3 sent to review;
- the assumed status (`full` / `partial` / `fail`) is an assumption for the recruiter to check with the
  candidate, never a prediction of the candidate's answer;
- the job is rescored with the policy's own formula (the same inputs `ranking_explanation` uses to
  reproduce the reported score), then every job of the run is re-ranked with `scoring.rank` and the
  run's expected count, so an incomplete run stays incomplete;
- the result holds the baseline and the alternative (places, recommendation, the job's L/H), and
  `affected_ids`, the jobs whose place changes. The report, its evaluation and HR decisions are not
  modified, and no model is called.

`what_if_options(report)` lists the open requirements of every processed job, one per requirement unit.

Under a policy with requirement units (v3), literal repeats are one unit: it is offered once, and an
assumption resolves all its rows. A unit whose repeats disagree (`conflict`: in H, not in L) is open too.
"""
import copy
from typing import Literal

from pydantic import ValidationError

from .contracts import Evaluation, StrictModel
from .ranking_explanation import _Job
from .scoring import rank

Assumed = Literal['full', 'partial', 'fail']
Status = Literal['full', 'partial', 'fail', 'unknown', 'conflict']


class Option(StrictModel):
    job_id: str
    requirement_id: str  # the first row of the unit; any row of it may be asked about
    requirement_ids: list[str]
    requirement_quote: str
    status: Status
    disputed: bool


class JobScore(StrictModel):
    lower: float
    upper: float
    coverage: float
    mandatory: str


class Outcome(StrictModel):
    places: dict[str, int]
    recommendation: str
    job_score: JobScore


class Assumption(StrictModel):
    job_id: str
    requirement_id: str
    requirement_ids: list[str]
    requirement_quote: str
    from_status: Status
    from_disputed: bool
    to_status: Assumed


class WhatIf(StrictModel):
    kind: Literal['hypothetical'] = 'hypothetical'
    policy_version: str
    assumption: Assumption
    baseline: Outcome
    alternative: Outcome
    affected_ids: list[str]
    caveats: list[Literal['incomplete_run', 'different_requirement_lists']]
    summary: str


def _jobs(report: dict) -> tuple[dict[str, dict], dict[str, str]]:
    try:
        jobs = {j['job_id']: j for j in report['ranking']['jobs']}
        facts = {f['id']: f['quote'] for f in report['facts']['items']}
    except (KeyError, TypeError):
        raise ValueError('incomplete_report') from None
    if len(jobs) != len(report['ranking']['jobs']):  # a repeated job_id would silently hide a job
        raise ValueError('incomplete_report')
    return jobs, facts


def _score(s: dict) -> JobScore:
    return JobScore(**{k: s[k] for k in ('lower', 'upper', 'coverage', 'mandatory')})


def _one_policy(report: dict, jobs: dict[str, dict]) -> str:
    """Every job and the report itself name one policy; the projection is labelled with it."""
    try:
        versions = {j['score'].get('policy_version') for j in jobs.values()}
    except (KeyError, TypeError, AttributeError):
        raise ValueError('incomplete_report') from None
    if len(versions) != 1 or report.get('policy_version', next(iter(versions))) not in versions:
        raise ValueError('policy_mismatch')
    return versions.pop()


OPEN_UNIT = ('unknown', 'disputed', 'conflict')


def _units(job: _Job) -> list[tuple[list[str], str | None]]:
    """Requirement units of the job with the policy's own state (v3), else one row each without one."""
    units = [(sorted(u['ids']), u['state']) for u in job.score.get('units', [])]
    folded = {rid for ids, _ in units for rid in ids}
    return sorted(units + [([rid], None) for rid in job.status if rid not in folded])


def _open(job: _Job) -> list[tuple[list[str], str]]:
    """Open units with their status.

    With policy units (v3) the unit's own state decides: a unit that counts in L is settled even if a
    repeat of it has no data. Rows E3 sent to review that the score ignored (v1-style) stay open.
    Without units, a row is open when it is unknown or disputed. Repeats with different known
    statuses are reported as `conflict`, also when the policy calls the unit `disputed`."""
    unresolved = set(job.unresolved())
    found = []
    for ids, state in _units(job):
        is_open = (state in OPEN_UNIT or bool(job.unscored_review & set(ids))) if state else bool(unresolved & set(ids))
        if not is_open:
            continue
        known = {job.status[i] for i in ids} - {'unknown'}
        found.append((ids, 'conflict' if state == 'conflict' or len(known) > 1 else known.pop() if known else 'unknown'))
    return found


def _resolve(job: _Job, ids: list[str], status: str) -> dict:
    """The job's score with every row of one unit resolved to `status` (structurally confirmed),
    through the job's own `rescore`, so the policy that scored the report scores the projection."""
    projected = copy.copy(job)
    projected.evaluation = Evaluation(rows=[r.model_copy(update={'status': status}) if r.requirement_id in ids
                                            else r for r in job.evaluation.rows])
    if job.evidence is not None:
        projected.evidence = job.evidence.model_copy(update={'rows': [
            c.model_copy(update={'status': status, 'state': 'structure_ok'}) if c.requirement_id in ids else c
            for c in job.evidence.rows]})
    return projected.rescore()


def _parse(jobs: dict[str, dict], facts: dict[str, str], only: list[str]) -> dict[str, _Job]:
    try:
        return {j: _Job(jobs[j], facts) for j in only}
    except (KeyError, TypeError, ValidationError):
        raise ValueError('incomplete_report') from None


def what_if_options(report: dict) -> list[Option]:
    jobs, facts = _jobs(report)
    if not jobs:  # nothing processed: nothing to ask about
        return []
    _one_policy(report, jobs)
    options = []
    for job_id, job in sorted(_parse(jobs, facts, list(jobs)).items()):
        options += [Option(job_id=job_id, requirement_id=ids[0], requirement_ids=ids,
                           requirement_quote=job.quotes[ids[0]], status=status,
                           disputed=bool(job.disputed & set(ids))) for ids, status in _open(job)]
    return options


def what_if(report: dict, job_id: str, requirement_id: str, assumed_status: str) -> WhatIf:
    if assumed_status not in ('full', 'partial', 'fail'):
        raise ValueError('invalid_status')
    jobs, facts = _jobs(report)
    if job_id not in jobs:
        raise ValueError('unknown_job')
    policy = _one_policy(report, jobs)
    snapshot = copy.deepcopy(report)
    # Every job must reproduce its reported score, and the reported places and recommendation must be
    # what scoring.rank gives for them; otherwise a "difference" would be a code difference.
    parsed = _parse(jobs, facts, list(jobs))
    try:
        complete = report['ranking']['complete']
        recommendation = report['ranking']['recommendation']
        reported_places = {j: jobs[j]['rank'] for j in jobs}
    except (KeyError, TypeError, ValidationError):
        raise ValueError('incomplete_report') from None
    unprocessed = report.get('unprocessed') or []
    expected = len(jobs) + len(unprocessed) if complete or unprocessed else len(jobs) + 1
    base_rank = rank([{'job_id': j, 'score': parsed[j].score} for j in jobs], expected)
    if ({j['job_id']: j['rank'] for j in base_rank['jobs']} != reported_places
            or base_rank['recommendation'] != recommendation):
        raise ValueError('ranking_not_reproducible')

    target = parsed[job_id]
    if requirement_id not in target.status:
        raise ValueError('unknown_requirement')
    unit = next(((ids, status) for ids, status in _open(target) if requirement_id in ids), None)
    if unit is None:
        raise ValueError('not_open')  # a resolved row is the model's claim to review, not a what-if
    ids, from_status = unit

    changed = _resolve(target, ids, assumed_status)
    alt_rank = rank([{'job_id': j, 'score': changed if j == job_id else parsed[j].score} for j in jobs], expected)
    baseline = Outcome(places=dict(sorted(reported_places.items())), recommendation=recommendation,
                       job_score=_score(target.score))
    alternative = Outcome(places={j['job_id']: j['rank'] for j in sorted(alt_rank['jobs'], key=lambda x: x['job_id'])},
                          recommendation=alt_rank['recommendation'], job_score=_score(changed))
    affected = sorted(j for j in jobs if baseline.places[j] != alternative.places[j])

    caveats = []
    if not complete or unprocessed:
        caveats.append('incomplete_run')
    if len({tuple(sorted(r['quote'].strip().casefold() for r in j['requirements']['items']))
            for j in jobs.values()}) > 1:
        caveats.append('different_requirement_lists')
    assumption = Assumption(job_id=job_id, requirement_id=requirement_id, requirement_ids=ids,
                            requirement_quote=target.quotes[requirement_id], from_status=from_status,
                            from_disputed=bool(target.disputed & set(ids)), to_status=assumed_status)
    if report != snapshot:  # the projection never writes into the report
        raise RuntimeError('report_modified')
    return WhatIf(policy_version=policy, assumption=assumption, baseline=baseline,
                  alternative=alternative, affected_ids=affected, caveats=caveats,
                  summary=_summary(assumption, baseline, alternative, affected, caveats))


def _place(outcome: Outcome, job_id: str) -> str:
    """«2» or «1 (общее с job-001)»: a shared place is never presented as overtaking."""
    place = outcome.places[job_id]
    shared = sorted(j for j, p in outcome.places.items() if p == place and j != job_id)
    return f'{place} (общее с {", ".join(shared)})' if shared else str(place)


def _summary(a: Assumption, base: Outcome, alt: Outcome, affected: list[str], caveats: list[str]) -> str:
    text = (f'Допущение: если «{a.requirement_quote}» в {a.job_id} подтвердится как {a.to_status}, '
            f'нижняя граница {base.job_score.lower} → {alt.job_score.lower}, '
            f'группа обязательных {base.job_score.mandatory} → {alt.job_score.mandatory}.')
    if a.from_status == 'conflict':
        text += f' Сейчас повторы требования ({", ".join(a.requirement_ids)}) противоречат друг другу.'
    elif len(a.requirement_ids) > 1:
        text += f' Требование повторяется ({", ".join(a.requirement_ids)}) и уточняется один раз.'
    if base.places[a.job_id] != alt.places[a.job_id]:
        text += f' Место {a.job_id}: {_place(base, a.job_id)} → {_place(alt, a.job_id)}.'
    else:
        text += f' Место {a.job_id} не меняется: {_place(alt, a.job_id)}.'
    others = [j for j in affected if j != a.job_id]
    if others:
        text += ' Сдвигаются также: ' + ', '.join(f'{j} {_place(base, j)} → {_place(alt, j)}' for j in others) + '.'
    if alt.recommendation != base.recommendation:
        text += f' Рекомендация: {base.recommendation} → {alt.recommendation}.'
    if 'different_requirement_lists' in caveats:
        text += ' Списки требований разные: L считается внутри своей вакансии.'
    if 'incomplete_run' in caveats:
        text += ' Обработаны не все вакансии: порядок остаётся предварительным.'
    return text + ' Это допущение для уточнения у кандидата, не ответ кандидата и не решение.'
