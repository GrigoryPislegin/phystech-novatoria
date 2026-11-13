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
- a literal repeat is one requirement unit and does not count twice: rows are one unit only when the
  requirement text, the vacancy quote (case, spaces and final punctuation aside) and the applied
  obligatoriness all coincide. Nothing else is merged: the same word quoted from another sentence, or
  equal meaning in other words, stays separate. Repeats with different known statuses are a
  conflict: the unit is not counted in L (it stays in H) and is sent to review, never averaged;
- `rank` adds `leader`: whether the first place is established. It is 'open' when the leader's own
  basis is doubted, or when a lower job could reach it by reading its disputed rows or by at most
  ANSWERS answers to unknown rows (only a job that already has confirmed matches is such a
  challenger; a job with none is listed as unassessed and never holds the top open), and 'close'
  when the lead is smaller than one status step of the coarser of the two requirement lists.
  Steps, answers and scenarios are counted in requirement units with exact fractions, so they agree
  with a real re-score and do not depend on repeats, ids or rounding. A tie that one answer could
  break is 'open'. 'review_top' is given only for a stable or settled tied first place.
Evidence must cover exactly these requirements and rows, or score raises 'invalid_evidence'.
Without an evidence check every row and marker is taken as given.
"""
from fractions import Fraction

from .contracts import Evaluation, Requirements
from .evidence import PairCheck

POLICY_V2 = 'draft-2026-11-13-v2'
POLICY_VERSION = 'draft-2026-11-14-v3'
POLICY_V1 = 'draft-2026-11-12-v1'
POLICIES = (POLICY_V2, POLICY_VERSION)
LEGACY = (None, POLICY_V1, POLICY_V2)  # ranked by the v2 rules they were computed with
VALUE = {'full': 1, 'partial': 0.5, 'fail': 0}
CORE_SHARE = 75  # points of the scale for applied mandatory requirements when both groups exist
ANSWERS = 2  # how many candidate answers a challenger may need and still keep the first place open
MAX_DECISIVE = 3
MAX_MARKERS = 4  # unapplied markers whose every combination is re-scored; above that the job is 'unbounded'


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


def _norm(text: str) -> str:
    return ' '.join(text.casefold().split()).strip(' .;,:—–-•*')


def _weights_v2(requirements: Requirements, mandatory: set[str]) -> dict:
    weight = {r.id: Fraction(3 if r.id in mandatory else 1) for r in requirements.items}
    total = sum(weight.values())
    return {rid: 100 * w / total for rid, w in weight.items()}


def _points(x) -> float:
    return round(float(x), 4)


def _units(requirements: Requirements, mandatory: set[str], excluded: set[str], state: dict) -> list[dict]:
    """Requirement units of policy v3: literal repeats folded, each with one state.

    The state of a unit is the common state of its rows; a row without data does not contradict a
    known one. Different known or disputed states are a 'conflict'."""
    grouped: dict[tuple, list[str]] = {}
    for r in requirements.items:
        grouped.setdefault((_norm(r.text), _norm(r.quote), r.id in mandatory, r.id in excluded), []).append(r.id)
    units = []
    for (_, _, core, _), ids in grouped.items():
        states = {state[i] for i in ids} - {'unknown'}
        units.append({'ids': sorted(ids), 'group': 'core' if core else 'extra',
                      'state': 'unknown' if not states else states.pop() if len(states) == 1 else 'conflict'})
    return sorted(units, key=lambda u: u['ids'])


def exact(score: dict) -> dict:
    """Exact fractions of a v3 score, rebuilt from its units: the unit weights and L. `rank`, the
    comparison and every what-if use these, never the rounded numbers shown to people."""
    sizes = {g: sum(u['group'] == g for u in score['units']) for g in ('core', 'extra')}
    share = {'core': Fraction(CORE_SHARE if sizes['extra'] else 100), 'extra': Fraction(100 - CORE_SHARE if sizes['core'] else 100)}
    weights = [share[u['group']] / sizes[u['group']] for u in score['units']]
    lower = sum(w * Fraction(VALUE[u['state']]) for u, w in zip(score['units'], weights) if u['state'] in VALUE)
    return {'weights': weights, 'lower': lower, 'step': min(weights) / 2}


def is_close(a: dict, b: dict) -> bool:
    """The lead between two v3 scores is below one status step of the coarser list."""
    ea, eb = exact(a), exact(b)
    return 0 < abs(ea['lower'] - eb['lower']) < max(ea['step'], eb['step'])


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
    common = {'disputed_ids': sorted(disputed), 'excluded_mandatory_ids': sorted(excluded),
              'evidence_applied': evidence is not None, 'policy_version': policy}

    def gate_state(gate):
        return ('not_set' if not gate else 'violated' if 'fail' in gate
                else 'confirmed' if all(s == 'full' for s in gate) else 'clarify')

    if policy == POLICY_V2:
        weight = _weights_v2(requirements, mandatory)
        counted = {rid for rid in weight if rows[rid].status != 'unknown' and rid not in disputed}
        points = sum(weight[rid] * Fraction(VALUE[rows[rid].status]) for rid in counted)
        known = sum(weight[rid] for rid in counted)
        gate = [('disputed' if rid in disputed else rows[rid].status) for rid in sorted(mandatory)]
        return {'lower': _points(points), 'upper': _points(points + 100 - known), 'coverage': _points(known),
                'mandatory': gate_state(gate), **common}

    state = {rid: 'disputed' if rid in disputed else rows[rid].status for rid in rows}
    units = _units(requirements, mandatory, excluded, state)

    def core_gate(us):
        return gate_state([u['state'] for u in us if u['group'] == 'core'])

    # What the job would be if the recruiter applied its unapplied markers: a real re-score of every
    # combination, because an applied marker changes the weights and H does not bound that.
    scenarios = []
    if 0 < len(excluded) <= MAX_MARKERS:
        for mask in range(1, 2 ** len(excluded)):
            applied = {rid for i, rid in enumerate(sorted(excluded)) if mask >> i & 1}
            alt = _units(requirements, mandatory | applied, excluded - applied, state)
            scenarios.append({'applied': sorted(applied), 'mandatory': core_gate(alt), 'units': alt})
    result = {'units': units}
    ex = exact(result)
    known = sum(w for u, w in zip(units, ex['weights']) if u['state'] in VALUE)

    def part(name):
        mine = [(u, w) for u, w in zip(units, ex['weights']) if u['group'] == name]
        if not mine:
            return None
        low = sum(w * Fraction(VALUE[u['state']]) for u, w in mine if u['state'] in VALUE)
        return {'share': _points(sum(w for _, w in mine)), 'units': len(mine), 'lower': _points(low),
                'upper': _points(low + sum(w for u, w in mine if u['state'] not in VALUE))}

    # Everything `rank` and the explanations need to show exactly this calculation.
    result.update({
        'lower': _points(ex['lower']), 'upper': _points(ex['lower'] + 100 - known), 'coverage': _points(known),
        'mandatory': core_gate(units), **common,
        # One status step of the lightest requirement unit, in points. A lead below the larger
        # `resolution` of two jobs is 'close'. Readers use this field, never min(weights) / 2.
        'resolution': _points(ex['step']),
        'weights': {rid: _points(w / len(u['ids'])) for u, w in zip(units, ex['weights']) for rid in u['ids']},
        'mandatory_ids': sorted(mandatory),
        'unknown_ids': sorted(rid for rid in rows if rows[rid].status == 'unknown'),
        'partial_ids': sorted(rid for rid in rows if state[rid] == 'partial'),
        'conflict_ids': sorted(rid for u in units if u['state'] == 'conflict' for rid in u['ids']),
        'groups': {'core': part('core'), 'extra': part('extra')},
        'repeated_ids': [u['ids'] for u in units if len(u['ids']) > 1],
        # None: too many unapplied markers to enumerate; such a job is treated as able to reach the top.
        'marker_scenarios': None if len(excluded) > MAX_MARKERS else scenarios})
    return result


def _version(results) -> str | None:
    """The one policy of a set of scores; a mixed or unknown set is refused."""
    versions = {j['score'].get('policy_version') for j in results}
    if len(versions) > 1:
        raise ValueError('mixed_policy')
    version = versions.pop() if versions else None
    if version not in LEGACY and version != POLICY_VERSION:
        raise ValueError('unknown_policy')
    return version


def _places(results, v3: bool):
    def key(item):  # v3 orders by the exact L, so a rounding coincidence is never a tie
        low = exact(item['score'])['lower'] if v3 else item['score']['lower']
        return item['score']['mandatory'] == 'violated', low

    ordered = sorted(results, key=lambda x: (key(x)[0], -key(x)[1], x['job_id']))
    jobs, last, place = [], None, 0
    for idx, item in enumerate(ordered, 1):
        if key(item) != last:
            place = idx
        jobs.append({**item, 'rank': place})
        last = key(item)
    return jobs


def _leader(jobs: list[dict]) -> dict:
    """Is the first place established, and which requirement units could change it.

    Exact arithmetic over units: a scenario here gives the same order as re-scoring the rows."""
    top = [j for j in jobs if j['rank'] == 1]
    first = top[0]['score']
    out = {'job_ids': [j['job_id'] for j in top], 'state': 'stable', 'reasons': [], 'margin': None,
           'resolution': None, 'close_to': [], 'challengers': [], 'unassessed': [], 'decisive': [],
           'decisive_total': 0, 'answers_limit': ANSWERS}
    if first['mandatory'] == 'violated':
        return {**out, 'state': 'none_fit'}
    reasons, decisive = set(), {}
    best = exact(first)['lower']

    def add(job, ids, kind, role, effect):
        decisive.setdefault((job['job_id'], ids[0]), {
            'job_id': job['job_id'], 'requirement_id': ids[0], 'requirement_ids': list(ids), 'kind': kind,
            'role': role, 'effect': effect})

    def units_in(view, states):
        found = [(u, w) for u, w in zip(view['units'], exact(view)['weights']) if u['state'] in states]
        return sorted(found, key=lambda x: (-x[1], x[0]['ids']))

    def open_units(job, states):
        return units_in(job['score'], states)

    def reach(view):
        """Exact L of a view, its disputed units and the fewest unknown answers that bring it to the top."""
        low, doubted = exact(view)['lower'], units_in(view, {'disputed', 'conflict'})
        got, asked = low + sum(w for _, w in doubted), []
        for u, w in units_in(view, {'unknown'})[:ANSWERS]:
            if got >= best:
                break
            got += w
            asked.append((u, w))
        needs_reading = low + sum(w for _, w in asked) < best  # the answers alone are not enough
        return got >= best, asked, doubted if needs_reading else []

    kinds = {'conflict': 'disputed', 'disputed': 'disputed', 'unknown': 'unknown', 'partial': 'partial'}
    for job in top:
        s = job['score']
        if s['mandatory'] == 'clarify':
            reasons.add('own_mandatory_unresolved')
            for u, w in open_units(job, kinds):
                if u['group'] == 'core':
                    add(job, u['ids'], kinds[u['state']], 'leader', w / 2 if u['state'] == 'partial' else w)
        if s['disputed_ids'] or s['conflict_ids']:
            reasons.add('own_disputed')
            for u, w in open_units(job, {'disputed', 'conflict'}):
                add(job, u['ids'], 'disputed', 'leader', w)
        if s['excluded_mandatory_ids']:
            reasons.add('own_marker_unapplied')
            for rid in s['excluded_mandatory_ids']:
                add(job, [rid], 'marker', 'leader', Fraction(s['weights'][rid]))
        if best == 0:
            reasons.add('no_confirmed_fit')
        if len(top) > 1 and open_units(job, {'unknown'}):  # one answer would break the tie
            reasons.add('tie_unresolved')
            for u, w in open_units(job, {'unknown'}):
                add(job, u['ids'], 'unknown', 'leader', w)

    rivals = [j for j in jobs if j['rank'] > 1 and j['score']['mandatory'] != 'violated']
    assessed = []
    for job in rivals:
        s = job['score']
        low = exact(s)['lower']
        doubted, unknown = open_units(job, {'disputed', 'conflict'}), open_units(job, {'unknown'})
        if s['excluded_mandatory_ids']:
            # Applying a marker changes the weights, so every combination is really re-scored; a job
            # with too many markers to enumerate is conservatively taken as able to reach the top.
            assessed.append(job)
            views = [v for v in s['marker_scenarios'] or [] if v['mandatory'] != 'violated']
            hits = sorted(((len(r[1]), len(v['applied']), v['applied'], v, r) for v in views
                           for r in [reach(v)] if r[0]), key=lambda h: h[:3])
            now = reach(s)
            if s['marker_scenarios'] is None or (hits and not now[0]):
                reasons.add('challenger_doubted')
                applied = hits[0][2] if hits else s['excluded_mandatory_ids']
                asked, read = (hits[0][4][1], hits[0][4][2]) if hits else ([], [])
                out['challengers'].append({'job_id': job['job_id'], 'answers_needed': len(asked) if hits else None})
                for rid in applied:
                    add(job, [rid], 'marker', 'challenger', Fraction(s['weights'][rid]))
                for u, w in read:
                    add(job, u['ids'], 'disputed', 'challenger', w)
                for u, w in asked:
                    add(job, u['ids'], 'unknown', 'challenger', w)
                continue
            if not now[0]:
                continue
        elif low == 0 and not doubted:
            out['unassessed'].append(job['job_id'])  # nothing confirmed or claimed: neither rejected nor a rival
            continue
        else:
            assessed.append(job)
        # Reading the disputed rows and answers to unknown units are counted apart.
        reached, asked, read = reach(s)
        if not reached:
            continue
        reasons.add('challenger_answers' if asked else 'challenger_doubted')
        out['challengers'].append({'job_id': job['job_id'], 'answers_needed': len(asked)})
        for u, w in read:
            add(job, u['ids'], 'disputed', 'challenger', w)
        for u, w in asked:
            add(job, u['ids'], 'unknown', 'challenger', w)
    if rivals:
        out['margin'] = _points(best - max(exact(j['score'])['lower'] for j in rivals))
    for job in assessed:  # every leader against every assessed rival, so ids and repeats change nothing
        steps = [max(exact(t['score'])['step'], exact(job['score'])['step']) for t in top
                 if is_close(t['score'], job['score'])]
        if steps:
            out['close_to'].append(job['job_id'])
            out['resolution'] = max(out['resolution'] or 0, _points(max(steps)))
    if out['close_to']:
        reasons.add('close_margin')

    order = ['own_mandatory_unresolved', 'own_disputed', 'own_marker_unapplied', 'no_confirmed_fit',
             'tie_unresolved', 'challenger_doubted', 'challenger_answers', 'close_margin']
    out['reasons'] = [r for r in order if r in reasons]
    if reasons - {'close_margin'}:
        out['state'] = 'open'
    elif reasons:
        out['state'] = 'close'
    elif len(top) > 1:
        out['state'] = 'tie'
    ranked = sorted(decisive.values(), key=lambda d: (d['role'] != 'leader', -d['effect'], d['job_id'],
                                                      d['requirement_id']))
    out['decisive_total'] = len(ranked)
    out['decisive'] = [{**d, 'effect': _points(d['effect'])} for d in ranked[:MAX_DECISIVE]]
    return out


def rank(results, expected_count):
    """Places and the recommendation. Scores of policy v3 also get the `leader` analysis; legacy scores
    (v1, v2 or hand-built without a version) are ranked by the v2 rules. One set, one policy."""
    v3 = _version(results) == POLICY_VERSION
    jobs = _places(results, v3)
    leader = _leader(jobs) if jobs and v3 else None
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
