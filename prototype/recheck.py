"""Explicit local recalculation of a saved model response; no provider calls."""
import copy

from .contracts import Facts, Requirements, Evaluation, validate_pair
from .evidence import Source, check_pair, RULES_VERSION
from .pipeline import refresh_derived
from .run_store import RunStore, StoreError
from .scoring import score, rank


def recheck_report(report, sources):
    """Return a new calculation, preserving model statuses, usage and original evidence provenance."""
    RunStore._validate_snapshot(report, sources)
    updated = copy.deepcopy(report)
    facts = Facts.model_validate(updated['facts'])
    facts.validate_source(sources['resume'])
    cv = Source.of('cv', sources['resume'])
    previous = []
    for job in updated['ranking']['jobs']:
        requirements = Requirements.model_validate(job['requirements'])
        evaluation = Evaluation.model_validate(job['evaluation'])
        validate_pair(requirements, facts, evaluation)
        evidence = check_pair(requirements, facts, evaluation, cv,
                              Source.of(job['job_id'], sources['jobs'][job['job_id']]))
        if evidence.has_invalid:
            raise StoreError('invalid_evidence')
        previous.append({'job_id':job['job_id'], 'score':copy.deepcopy(job['score']),
                         'evidence_rules':job['evidence_check'].get('rules_version')})
        job['evidence_check'] = evidence.model_dump()
        job['score'] = score(requirements, evaluation, evidence, policy=job['score']['policy_version'])
        job['score_review']['excluded_mandatory_ids'] = job['score']['excluded_mandatory_ids']
    updated['ranking'] = rank(updated['ranking']['jobs'],
                              len(updated['ranking']['jobs']) + len(updated['unprocessed_job_ids']))
    updated['evidence_recalculation'] = {'rules_version':RULES_VERSION, 'model_calls':0, 'previous':previous}
    return refresh_derived(updated)
