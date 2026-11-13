"""Versioned scoring policies, not an ML probability. No model can supply the numeric score.

Current policy: draft-2026-11-14-v3, docs/reviews/egor-scoring-policy-v3.md. The previous policy
draft-2026-11-13-v2 stays callable (`policy=POLICY_V2`) so that a stored v2 report is reproduced by
its own rules and never silently re-read under v3.

What v3 keeps from v2 (evidence check E3):
- a row counts towards L and coverage only when its evidence is structure_ok; a disputed row
  (needs_review) moves only H;
- a mandatory marker is applied only when check_mandatory is structure_ok;
- only a structurally supported fail on an applied mandatory requirement gives 'violated', and such a
  job is placed below every job without a violation; unknown and a disputed fail never do that.

What v3 changes:
- the applied mandatory requirements and the other requirements are two groups with fixed shares of
  the scale (75 / 25 points; a single group takes 100). Inside a group every requirement unit weighs
  the same. Adding, removing or splitting optional rows therefore cannot dilute the mandatory part,
  and a pile of optional matches cannot outweigh it. For one mandatory and one optional requirement
  this equals the v2 weights 3 : 1;
- rows with the same requirement text (case, spaces and final punctuation aside) are one unit: a
  literal repeat does not count twice. Nothing else is merged: equal meaning in different words is
  not detectable here;
- `rank` adds `leader`: whether the first place is established. It is 'open' when the leader's own
  basis is doubted, or when a lower job could reach it by reading its disputed rows or by at most
  ANSWERS answers to unknown rows (only a job that already has confirmed matches is such a
  challenger; a job with none is listed as unassessed and never holds the top open), and 'close'
  when the lead is smaller than one status step of the coarser of the two requirement lists.
  'review_top' is given only for a stable (or exactly tied) first place.
Evidence must cover exactly these requirements and rows, or score raises 'invalid_evidence'.
Without an evidence check every row and marker is taken as given.
"""
from fractions import Fraction

from .contracts import Evaluation, Requirements
from .evidence import PairCheck

POLICY_V2 = 'draft-2026-11-13-v2'
POLICY_VERSION = 'draft-2026-11-14-v3'
POLICIES = (POLICY_V2, POLICY_VERSION)
VALUE = {'full': 1, 'partial': 0.5, 'fail': 0}
CORE_SHARE = 75  # points of the scale for applied mandatory requirements when both groups exist
ANSWERS = 2  # how many candidate answers a challenger may need and still keep the first place open
MAX_DECISIVE = 3


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


def _unit_key(text: str) -> str:
    return ' '.join(text.casefold().split()).strip(' .;,:')


def _weights_v2(requirements: Requirements, mandatory: set[str]) -> tuple[dict, dict, list]:
    weight = {r.id: Fraction(3 if r.id in mandatory else 1) for r in requirements.items}
    total = sum(weight.values())
    return {rid: 100 * w / total for rid, w in weight.items()}, {}, []


def _weights_v3(requirements: Requirements, mandatory: set[str]) -> tuple[dict, dict, list]:
    """Points of the 100-point scale per row; the share of each group; literal repeats."""
    units: dict[str, list[str]] = {}
    for r in requirements.items:
        units.setdefault(_unit_key(r.text), []).append(r.id)
    core = [ids for ids in units.values() if any(i in mandatory for i in ids)]
    extra = [ids for ids in units.values() if not any(i in mandatory for i in ids)]
    shares = {'core': Fraction(CORE_SHARE if extra else 100) if core else None,
              'extra': Fraction(100 - CORE_SHARE if core else 100) if extra else None}
    weight, group = {}, {}
    for name, members in (('core', core), ('extra', extra)):
        for ids in members:
            for rid in ids:
                weight[rid] = shares[name] / len(members) / len(ids)
                group[rid] = name
    return weight, {'shares': shares, 'of': group}, sorted(sorted(ids) for ids in units.values() if len(ids) > 1)


def _points(x) -> float:
    return round(float(x), 4)


def score(requirements: Requirements, evaluation: Evaluation, evidence: PairCheck | None = None, *,
          policy: str = POLICY_VERSION) -> dict:
    if policy not in POLICIES:
        raise ValueError('unknown_policy')
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

    weight, groups, repeated = (_weights_v3 if policy == POLICY_VERSION else _weights_v2)(requirements, mandatory)
    counted = {rid for rid in weight if rows[rid].status != 'unknown' and rid not in disputed}
    gained = {rid: weight[rid] * Fraction(VALUE[rows[rid].status]) for rid in counted}
    points, known = sum(gained.values()), sum(weight[rid] for rid in counted)

    gate = [('disputed' if rid in disputed else rows[rid].status) for rid in sorted(mandatory)]
    mandatory_state = ('not_set' if not gate else 'violated' if 'fail' in gate
                       else 'confirmed' if all(s == 'full' for s in gate) else 'clarify')
    result = {'lower': _points(points), 'upper': _points(points + 100 - known), 'coverage': _points(known),
              'mandatory': mandatory_state, 'disputed_ids': sorted(disputed),
              'excluded_mandatory_ids': sorted(excluded), 'evidence_applied': evidence is not None,
              'policy_version': policy}
    if policy == POLICY_V2:
        return result

    def part(name):
        share = groups['shares'][name]
        if share is None:
            return None
        ids = [rid for rid, g in groups['of'].items() if g == name]
        low = sum(gained.get(rid, 0) for rid in ids)
        return {'share': _points(share), 'lower': _points(low),
                'upper': _points(low + sum(weight[rid] for rid in ids if rid not in counted))}

    # Everything `rank` and the explanations need to show exactly this calculation.
    result.update({
        'weights': {rid: _points(w) for rid, w in sorted(weight.items())},
        'mandatory_ids': sorted(mandatory),
        'unknown_ids': sorted(rid for rid in weight if rows[rid].status == 'unknown'),
        'partial_ids': sorted(rid for rid in counted if rows[rid].status == 'partial'),
        'groups': {'core': part('core'), 'extra': part('extra')},
        'repeated_ids': repeated})
    return result


def _places(results):
    def key(item):
        return item['score']['mandatory'] == 'violated', item['score']['lower']

    ordered = sorted(results, key=lambda x: (key(x)[0], -key(x)[1], x['job_id']))
    jobs, last, place = [], None, 0
    for idx, item in enumerate(ordered, 1):
        if key(item) != last:
            place = idx
        jobs.append({**item, 'rank': place})
        last = key(item)
    return jobs


def _leader(jobs: list[dict]) -> dict:
    """Is the first place established, and which rows could change it. Pure arithmetic over scores."""
    top = [j for j in jobs if j['rank'] == 1]
    first = top[0]['score']
    out = {'job_ids': [j['job_id'] for j in top], 'state': 'stable', 'reasons': [], 'margin': None,
           'resolution': None, 'close_to': [], 'challengers': [], 'unassessed': [], 'decisive': [],
           'decisive_total': 0, 'answers_limit': ANSWERS}
    if first['mandatory'] == 'violated':
        return {**out, 'state': 'none_fit'}
    reasons, decisive = set(), []

    def add(job, rid, kind, role):
        decisive.append({'job_id': job['job_id'], 'requirement_id': rid, 'kind': kind, 'role': role,
                         'effect': job['score']['weights'][rid] * (0.5 if kind == 'partial' else 1)})

    for job in top:
        s = job['score']
        core = set(s['mandatory_ids'])
        if s['mandatory'] == 'clarify':
            reasons.add('own_mandatory_unresolved')
            for rid in sorted(core):
                kind = ('disputed' if rid in s['disputed_ids'] else 'unknown' if rid in s['unknown_ids']
                        else 'partial' if rid in s['partial_ids'] else None)
                if kind:
                    add(job, rid, kind, 'leader')
        if s['disputed_ids']:
            reasons.add('own_disputed')
            for rid in s['disputed_ids']:
                if rid not in core:
                    add(job, rid, 'disputed', 'leader')
        if s['excluded_mandatory_ids']:
            reasons.add('own_marker_unapplied')
            for rid in s['excluded_mandatory_ids']:
                add(job, rid, 'marker', 'leader')
        if s['lower'] == 0:
            reasons.add('no_confirmed_fit')

    rivals = [j for j in jobs if j['rank'] > 1 and j['score']['mandatory'] != 'violated']
    for job in rivals:
        s = job['score']
        if (s['disputed_ids'] or s['excluded_mandatory_ids']) and s['upper'] >= first['lower']:
            # The v2 rule: reading the job's own doubted rows or markers could bring it to the top.
            reasons.add('challenger_doubted')
            out['challengers'].append({'job_id': job['job_id'], 'answers_needed': 0})
            for rid in s['disputed_ids']:
                add(job, rid, 'disputed', 'challenger')
            for rid in s['excluded_mandatory_ids']:
                add(job, rid, 'marker', 'challenger')
        elif s['lower'] == 0:
            out['unassessed'].append(job['job_id'])  # nothing confirmed: neither a rejection nor a rival
        else:
            reach = s['lower'] + sum(s['weights'][rid] for rid in s['disputed_ids'])
            asked = []
            for rid in sorted(s['unknown_ids'], key=lambda r: (-s['weights'][r], r))[:ANSWERS]:
                if reach >= first['lower']:
                    break
                reach += s['weights'][rid]
                asked.append(rid)
            if asked and round(reach, 4) >= first['lower']:
                reasons.add('challenger_answers')
                out['challengers'].append({'job_id': job['job_id'], 'answers_needed': len(asked)})
                for rid in asked:
                    add(job, rid, 'unknown', 'challenger')
    if rivals:
        second = max(j['score']['lower'] for j in rivals)
        out['margin'] = round(first['lower'] - second, 4)
        for job in rivals:
            s = job['score']
            step = round(max(min(first['weights'].values()), min(s['weights'].values())) / 2, 4)
            if first['lower'] - s['lower'] < step:
                out['close_to'].append(job['job_id'])
                out['resolution'] = max(out['resolution'] or 0, step)
        if out['close_to']:
            reasons.add('close_margin')

    order = ['own_mandatory_unresolved', 'own_disputed', 'own_marker_unapplied', 'no_confirmed_fit',
             'challenger_doubted', 'challenger_answers', 'close_margin']
    out['reasons'] = [r for r in order if r in reasons]
    if reasons - {'close_margin'}:
        out['state'] = 'open'
    elif reasons:
        out['state'] = 'close'
    elif len(top) > 1:
        out['state'] = 'tie'
    decisive.sort(key=lambda d: (d['role'] != 'leader', -d['effect'], d['job_id'], d['requirement_id']))
    out['decisive_total'] = len(decisive)
    out['decisive'] = [{**d, 'effect': round(d['effect'], 4)} for d in decisive[:MAX_DECISIVE]]
    return out


def rank(results, expected_count):
    """Places and the recommendation. Scores of policy v3 also get the `leader` analysis; scores of
    another (or no) version are ranked by the v2 rules they were computed with."""
    jobs = _places(results)
    versions = {j['score'].get('policy_version') for j in jobs}
    if len(versions) > 1 and POLICY_VERSION in versions:
        raise ValueError('mixed_policy')
    leader = _leader(jobs) if jobs and versions == {POLICY_VERSION} else None
    top = [j['score'] for j in jobs if j['rank'] == 1]
    if len(jobs) != expected_count or not jobs:
        recommendation = 'incomplete'
    elif all(j['score']['mandatory'] == 'violated' for j in jobs):
        recommendation = 'review_none_fit'
    elif leader is not None:
        recommendation = 'review_top' if leader['state'] in {'stable', 'tie'} else 'clarify'
    else:
        # v2: a lower job whose own doubted rows (disputed evidence, unapplied marker) could reach first
        # place keeps the order open.
        contested = [j['score'] for j in jobs if j['rank'] > 1 and j['score']['mandatory'] != 'violated'
                     and (j['score'].get('disputed_ids') or j['score'].get('excluded_mandatory_ids'))
                     and j['score']['upper'] >= top[0]['lower']]
        doubted = any(s['mandatory'] == 'clarify' or s.get('disputed_ids') or s.get('excluded_mandatory_ids')
                      for s in top) or top[0]['lower'] == 0 or contested
        recommendation = 'clarify' if doubted else 'review_top'
    ranking = {'jobs': jobs, 'recommendation': recommendation, 'complete': len(jobs) == expected_count,
               'requires_human_review': True}
    if leader is not None:
        ranking['leader'] = leader
    return ranking
