"""Versioned policy, not an ML probability. No model can supply the numeric score."""
POLICY_VERSION = 'draft-2026-11-12-v1'


def score(requirements, evaluation):
    rows = {r.requirement_id: r for r in evaluation.rows}
    if len(rows) != len(evaluation.rows) or set(rows) != {r.id for r in requirements.items}:
        raise ValueError('requirement_coverage')
    total = sum(r.weight for r in requirements.items)
    if not total:
        raise ValueError('no_requirements')
    points = known = 0
    mandatory = []
    for req in requirements.items:
        status = rows[req.id].status
        if status != 'unknown':
            known += req.weight
            points += req.weight * {'full':1, 'partial':0.5, 'fail':0}[status]
        if req.mandatory_quote:
            mandatory.append(status)
    gate = ('not_set' if not mandatory else 'violated' if 'fail' in mandatory
            else 'confirmed' if all(s == 'full' for s in mandatory) else 'clarify')
    return {'lower': round(100 * points / total, 4),
            'upper': round(100 * (points + total - known) / total, 4),
            'coverage': round(100 * known / total, 4), 'mandatory': gate,
            'policy_version': POLICY_VERSION}


def rank(results, expected_count):
    ordered = sorted(results, key=lambda x:(x['score']['mandatory'] == 'violated', -x['score']['lower'], x['job_id']))
    last, place = None, 0
    jobs = []
    for idx, item in enumerate(ordered, 1):
        key = (item['score']['mandatory'] == 'violated', item['score']['lower'])
        if key != last:
            place = idx
        jobs.append({**item, 'rank': place})
        last = key
    if len(jobs) != expected_count or not jobs:
        recommendation = 'incomplete'
    elif all(j['score']['mandatory'] == 'violated' for j in jobs):
        recommendation = 'review_none_fit'
    elif any(j['score']['mandatory'] == 'clarify' for j in jobs if j['rank'] == 1) or jobs[0]['score']['lower'] == 0:
        recommendation = 'clarify'
    else:
        recommendation = 'review_top'
    return {'jobs':jobs, 'recommendation':recommendation, 'complete':len(jobs) == expected_count,
            'requires_human_review':True}
