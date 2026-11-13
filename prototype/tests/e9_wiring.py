"""Reference wiring of E5/E7/E8 into a pipeline report, as the integration contract describes it.

Test helper only: it shows the exact calls and fields (docs/reviews/egor-e9-integration-contract.md).
Codex owns pipeline.py; this module does not replace it. Synthetic data only.
"""
from prototype.candidate_profile import CandidateProfile, Conditions, check_conditions, check_profile
from prototype.contracts import Evaluation, Facts, Requirements
from prototype.evidence import PairCheck, Source
from prototype.ranking_explanation import compare
from prototype.review_policy import assess_handoff
from prototype.review_queue import build_review_queue
from prototype.scoring import rank, score


def wire(report: dict, resume_text: str, job_texts: dict[str, str], profile: dict | None,
         conditions: dict[str, dict]) -> dict:
    """Return a copy of a pipeline report with policy v2 scores, E5 profile and conditions.

    resume_text / job_texts are the processed (privacy-safe) texts the pipeline already holds.
    """
    facts = Facts.model_validate(report['facts'])
    cv = Source.of('cv', resume_text)
    jobs = []
    for job in report['ranking']['jobs']:
        job = {k: v for k, v in job.items() if k != 'rank'}
        requirements = Requirements.model_validate(job['requirements'])  # original list, markers kept
        evidence = PairCheck.model_validate(job['evidence_check'])
        job['score'] = score(requirements, Evaluation.model_validate(job['evaluation']), evidence)
        job.pop('score_review', None)  # v2 carries excluded_mandatory_ids itself; do not apply twice
        if job['job_id'] in conditions:
            check = check_conditions(Conditions.model_validate(conditions[job['job_id']]), facts, cv,
                                     Source.of(job['job_id'], job_texts[job['job_id']]))
            job['conditions'] = check.model_dump()
        jobs.append(job)
    wired = {**report, 'ranking': rank(jobs, len(jobs) + len(report.get('unprocessed', [])))}
    if profile is not None:
        wired['profile'] = check_profile(CandidateProfile.model_validate(profile), facts, cv).model_dump()
    return wired


def derived(report: dict) -> dict:
    """What UI/manager views take from the wired report without a model call."""
    jobs = [j['job_id'] for j in report['ranking']['jobs']]
    pairs = [compare(report, a, b).model_dump() for a, b in zip(jobs, jobs[1:])]
    queue = build_review_queue(report)
    return {'comparisons': pairs,
            'queue': [{k: getattr(i, k) for k in ('job_id', 'requirement_id', 'condition_kind', 'reason_code',
                                                  'priority', 'action')} for i in queue.items],
            'handoff': {j: assess_handoff(report, [], j).state for j in jobs}}
