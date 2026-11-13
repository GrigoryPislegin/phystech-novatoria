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

`what_if_options(report)` lists the open rows of every processed job.
"""
import copy
from typing import Literal

from pydantic import ValidationError

from .contracts import StrictModel
from .ranking_explanation import _Job
from .scoring import POLICY_VERSION, rank

Assumed = Literal['full', 'partial', 'fail']


class Option(StrictModel):
    job_id: str
    requirement_id: str
    requirement_quote: str
    status: Literal['full', 'partial', 'fail', 'unknown']
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
    requirement_quote: str
    from_status: Literal['full', 'partial', 'fail', 'unknown']
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
    return jobs, facts


def _score(s: dict) -> JobScore:
    return JobScore(**{k: s[k] for k in ('lower', 'upper', 'coverage', 'mandatory')})


def what_if_options(report: dict) -> list[Option]:
    jobs, facts = _jobs(report)
    options = []
    for job_id in sorted(jobs):
        try:
            job = _Job(jobs[job_id], facts)
        except (KeyError, TypeError, ValidationError):
            raise ValueError('incomplete_report') from None
        options += [Option(job_id=job_id, requirement_id=rid, requirement_quote=job.quotes[rid],
                           status=job.status[rid], disputed=rid in job.disputed) for rid in job.unresolved()]
    return options


def what_if(report: dict, job_id: str, requirement_id: str, assumed_status: str) -> WhatIf:
    if assumed_status not in ('full', 'partial', 'fail'):
        raise ValueError('invalid_status')
    jobs, facts = _jobs(report)
    if job_id not in jobs:
        raise ValueError('unknown_job')
    snapshot = copy.deepcopy(report)
    try:
        # Every job must reproduce its reported score, and the reported places and recommendation must be
        # what scoring.rank gives for them; otherwise a "difference" would be a code difference.
        parsed = {j: _Job(jobs[j], facts) for j in jobs}
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
    if requirement_id not in target.unresolved():
        raise ValueError('not_open')  # a resolved row is the model's claim to review, not a what-if

    changed = target.rescore(requirement_id, assumed_status)
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
    assumption = Assumption(job_id=job_id, requirement_id=requirement_id,
                            requirement_quote=target.quotes[requirement_id],
                            from_status=target.status[requirement_id],
                            from_disputed=requirement_id in target.disputed, to_status=assumed_status)
    if report != snapshot:  # the projection never writes into the report
        raise RuntimeError('report_modified')
    return WhatIf(policy_version=POLICY_VERSION, assumption=assumption, baseline=baseline,
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
