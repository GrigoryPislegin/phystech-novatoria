"""Versioned scoring policy, not an ML probability. No model can supply the numeric score.

Policy draft-2026-11-13-v2, docs/reviews/egor-scoring-policy.md. With an evidence check (E3):
- a row counts towards L and coverage only when its evidence is structure_ok; a disputed row
  (needs_review) moves only H, so a recruiter's review can raise the score but never lower it;
- a mandatory marker gives weight 3 and enters the mandatory group only when check_mandatory is
  structure_ok; otherwise the requirement has weight 1;
- a disputed fail never makes a job violated, and a disputed full never confirms it;
- a first place with a disputed row or an unapplied mandatory marker is 'clarify', never 'review_top';
  so is a first place that a lower job could reach once its own disputed rows or markers are resolved.
Evidence must cover exactly these requirements and rows, or score raises 'invalid_evidence'.
Without an evidence check every row and marker is taken as given (the v1 behaviour).
"""
from .contracts import Evaluation, Requirements
from .evidence import PairCheck

POLICY_VERSION = 'draft-2026-11-13-v2'
VALUE = {'full': 1, 'partial': 0.5, 'fail': 0}


def _evidence_fits(requirements: Requirements, evaluation: Evaluation, evidence: PairCheck) -> bool:
    """One valid check per requirement, made for these very rows; the has_invalid flag is not trusted."""
    ids = {r.id for r in requirements.items}
    statuses = {r.requirement_id: r.status for r in evaluation.rows}
    checks = evidence.rows + evidence.mandatory
    return (len(evidence.rows) == len(evidence.mandatory) == len(ids)
            and {c.requirement_id for c in evidence.rows} == ids == {c.requirement_id for c in evidence.mandatory}
            and all(c.status == statuses[c.requirement_id] for c in evidence.rows)
            and not evidence.has_invalid
            and all(c.state != 'invalid' and all(x.severity != 'invalid' for x in c.reasons) for c in checks))


def score(requirements: Requirements, evaluation: Evaluation, evidence: PairCheck | None = None) -> dict:
    rows = {r.requirement_id: r for r in evaluation.rows}
    if len(rows) != len(evaluation.rows) or set(rows) != {r.id for r in requirements.items}:
        raise ValueError('requirement_coverage')
    if evidence is not None and not _evidence_fits(requirements, evaluation, evidence):
        raise ValueError('invalid_evidence')
    row_state = {c.requirement_id: c.state for c in evidence.rows} if evidence else {}
    marker_state = {c.requirement_id: c.state for c in evidence.mandatory} if evidence else {}

    disputed = {rid for rid, state in row_state.items() if state == 'needs_review'}
    excluded = {r.id for r in requirements.items
                if r.mandatory_quote and evidence is not None and marker_state.get(r.id) != 'structure_ok'}
    mandatory = {r.id for r in requirements.items if r.mandatory_quote} - excluded

    weight = {r.id: 3 if r.id in mandatory else 1 for r in requirements.items}
    total = sum(weight.values())
    points = known = 0
    for rid, w in weight.items():
        status = rows[rid].status
        if status != 'unknown' and rid not in disputed:
            known += w
            points += w * VALUE[status]

    gate = [('disputed' if rid in disputed else rows[rid].status) for rid in sorted(mandatory)]
    mandatory_state = ('not_set' if not gate else 'violated' if 'fail' in gate
                       else 'confirmed' if all(s == 'full' for s in gate) else 'clarify')
    return {'lower': round(100 * points / total, 4),
            'upper': round(100 * (points + total - known) / total, 4),
            'coverage': round(100 * known / total, 4), 'mandatory': mandatory_state,
            'disputed_ids': sorted(disputed), 'excluded_mandatory_ids': sorted(excluded),
            'evidence_applied': evidence is not None, 'policy_version': POLICY_VERSION}


def rank(results, expected_count):
    def key(item):
        return item['score']['mandatory'] == 'violated', item['score']['lower']

    ordered = sorted(results, key=lambda x: (key(x)[0], -key(x)[1], x['job_id']))
    jobs, last, place = [], None, 0
    for idx, item in enumerate(ordered, 1):
        if key(item) != last:
            place = idx
        jobs.append({**item, 'rank': place})
        last = key(item)
    top = [j['score'] for j in jobs if j['rank'] == 1]
    # A lower job whose own doubted rows (disputed evidence, unapplied marker) could reach first place
    # keeps the order open: the top is not a plain review_top while that is unresolved.
    contested = [j['score'] for j in jobs if j['rank'] > 1 and j['score']['mandatory'] != 'violated'
                 and (j['score'].get('disputed_ids') or j['score'].get('excluded_mandatory_ids'))
                 and top and j['score']['upper'] >= top[0]['lower']]
    if len(jobs) != expected_count or not jobs:
        recommendation = 'incomplete'
    elif all(j['score']['mandatory'] == 'violated' for j in jobs):
        recommendation = 'review_none_fit'
    elif any(s['mandatory'] == 'clarify' or s.get('disputed_ids') or s.get('excluded_mandatory_ids')
             for s in top) or top[0]['lower'] == 0 or contested:
        recommendation = 'clarify'
    else:
        recommendation = 'review_top'
    return {'jobs': jobs, 'recommendation': recommendation, 'complete': len(jobs) == expected_count,
            'requires_human_review': True}
