"""Compare scoring policies on the same policy-level inputs (E11). No model calls, no network.

python -m evaluation.policy_compare [--cases evaluation/expectations/egor/e11-policy-cases.json] [--out FILE.md]

Every case gives ready requirements, row statuses and E3 states, so this checks the policy only:
it says nothing about extraction quality or about agreement with real recruiters. Expectations are
the team's draft hypotheses. Policies:
- v2         draft-2026-11-13-v2, the control;
- v3         draft-2026-11-14-v3, the chosen policy;
- aggressive v3 scores, but a first place counts as established only when its L is above the upper
             bound H of every other job. Not shipped; it shows why that stricter rule is worse.
`established` means the recommendation is 'review_top'. `decisive` (rows named as able to change
the first place) exists only in v3; for the other policies it is reported as not available.
This is not the E6/E9 runner: that one judges saved pipeline reports against text expectations.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from prototype.contracts import Evaluation, Requirement, Requirements, Row
from prototype.evidence import MandatoryCheck, PairCheck, RowCheck
from prototype.scoring import POLICY_V2, POLICY_VERSION, rank, score

DEFAULT_CASES = Path(__file__).parent / 'expectations' / 'egor' / 'e11-policy-cases.json'
POLICIES = ('v2', 'v3', 'aggressive')


def build_job(job: dict):
    """Requirements, evaluation and a hand-built E3 check from the compact rows of a case."""
    items, rows, row_checks, markers = [], [], [], []
    for r in job['rows']:
        quote = f"{r['text']} ({r['id']})"
        items.append(Requirement(id=r['id'], text=r['text'], quote=quote,
                                 mandatory_quote=f'Обязательно: {quote}' if r['m'] else None))
        unknown = r['status'] == 'unknown'
        rows.append(Row(requirement_id=r['id'], status=r['status'], fact_ids=[] if unknown else ['f1'],
                        comment='синтетика', question=None if r['status'] == 'full' else 'Уточните.'))
        state = 'no_evidence' if unknown else 'needs_review' if r.get('evidence') == 'review' else 'structure_ok'
        row_checks.append(RowCheck(requirement_id=r['id'], status=r['status'], state=state, reasons=[], evidence=[]))
        marker = ('not_mandatory' if not r['m'] else 'needs_review' if r.get('marker') == 'review'
                  else 'structure_ok')
        markers.append(MandatoryCheck(requirement_id=r['id'], state=marker, reasons=[]))
    evidence = PairCheck(cv_sha256='cv', vacancy_id=job['job_id'], vacancy_sha256='v', rows=row_checks,
                         mandatory=markers, needs_review=False, has_invalid=False)
    return Requirements(items=items), Evaluation(rows=rows), evidence


def run_case(case: dict, policy: str) -> dict:
    version = POLICY_V2 if policy == 'v2' else POLICY_VERSION
    scored = [{'job_id': j['job_id'], 'score': score(*build_job(j), policy=version)} for j in case['jobs']]
    ranking = rank(scored, case.get('expected_count', len(scored)))
    if policy == 'aggressive' and ranking['recommendation'] == 'review_top':
        top = ranking['jobs'][0]['score']
        if any(j['score']['upper'] >= top['lower'] for j in ranking['jobs']
               if j['rank'] > 1 and j['score']['mandatory'] != 'violated'):
            ranking['recommendation'] = 'clarify'
    leader = ranking.get('leader')
    return {'places': {j['job_id']: j['rank'] for j in ranking['jobs']},
            'lower': {j['job_id']: j['score']['lower'] for j in ranking['jobs']},
            'recommendation': ranking['recommendation'],
            'state': leader['state'] if leader else None,
            'decisive': [[d['job_id'], d['requirement_id']] for d in leader['decisive']] if leader else None}


def check_case(case: dict, result: dict) -> dict:
    """Failed checks of one case; `unavailable` lists checks this policy cannot express."""
    places, expect, failed, unavailable = result['places'], case['expect'], [], []
    for better, worse in expect.get('order', []):
        if not places[better] < places[worse]:
            failed.append(f'order:{better}>{worse}')
    for a, b in expect.get('tie', []):
        if places[a] != places[b]:
            failed.append(f'tie:{a}={b}')
    if 'established' in expect and (result['recommendation'] == 'review_top') != expect['established']:
        failed.append(f"established:{expect['established']}")
    if 'recommendation' in expect and result['recommendation'] not in expect['recommendation']:
        failed.append('recommendation')
    for pair in expect.get('decisive', []):
        if result['decisive'] is None:
            unavailable.append('decisive:' + ':'.join(pair))
        elif pair not in result['decisive']:
            failed.append('decisive:' + ':'.join(pair))
    return {'failed': failed, 'unavailable': unavailable}


def compare(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        entry = {'id': case['id'], 'covers': case['covers'], 'limit': bool(case.get('limit')),
                 'cost': bool(case.get('cost'))}
        for policy in POLICIES:
            result = run_case(case, policy)
            entry[policy] = {**result, **check_case(case, result)}
        rows.append(entry)
    judged = [r for r in rows if not r['limit']]  # a known limit has no expectation to pass

    def passed(row, policy):
        return not row[policy]['failed']

    def first(row, policy):
        return sorted(j for j, place in row[policy]['places'].items() if place == 1)

    summary = {
        'cases': len(rows), 'judged': len(judged), 'known_limits': [r['id'] for r in rows if r['limit']],
        'passed': {p: sum(passed(r, p) for r in judged) for p in POLICIES},
        'fixed_by_v3': [r['id'] for r in judged if not passed(r, 'v2') and passed(r, 'v3')],
        'regressed_in_v3': [r['id'] for r in judged if passed(r, 'v2') and not passed(r, 'v3')],
        'aggressive_worse_than_v3': [r['id'] for r in judged if passed(r, 'v3') and not passed(r, 'aggressive')],
        'first_place_changed': [r['id'] for r in rows if first(r, 'v2') != first(r, 'v3')],
        'recommendation_changed': [r['id'] for r in rows
                                   if r['v2']['recommendation'] != r['v3']['recommendation']],
        # Manual work: runs where the recruiter is told to clarify before choosing, and for v3 how many
        # rows are named as the ones to look at first.
        'clarify_runs': {p: sum(r[p]['recommendation'] == 'clarify' for r in rows) for p in POLICIES},
        'decisive_rows_v3': sum(len(r['v3']['decisive'] or []) for r in rows),
    }
    return {'rows': rows, 'summary': summary}


def timing(cases: list[dict], repeat: int = 200) -> dict:
    """Local time of the policy arithmetic only. Not an API latency."""
    built = [[build_job(j) for j in case['jobs']] for case in cases]
    out = {}
    for name, version in (('v2', POLICY_V2), ('v3', POLICY_VERSION)):
        start = time.perf_counter()
        for _ in range(repeat):
            for case, jobs in zip(cases, built):
                rank([{'job_id': str(i), 'score': score(*job, policy=version)} for i, job in enumerate(jobs)],
                     len(jobs))
        out[name] = round(1e6 * (time.perf_counter() - start) / (repeat * len(cases)), 1)
    return out  # microseconds per run of score + rank


def markdown(result: dict) -> str:
    def cell(entry):
        mark = 'да' if not entry['failed'] else 'нет: ' + ', '.join(entry['failed'])
        places = ' / '.join(f'{j} {p}' for j, p in sorted(entry['places'].items(), key=lambda x: (x[1], x[0])))
        return f"{mark}<br>{places}<br>{entry['recommendation']}" + (f" · {entry['state']}" if entry['state'] else '')

    lines = ['| Случай | Что проверяет | v2 | v3 | aggressive |', '|---|---|---|---|---|']
    for r in result['rows']:
        if r['limit']:
            note = 'ограничение, без ожидания'
            lines.append(f"| {r['id']} | {', '.join(r['covers'])} | {note}<br>L: {r['v2']['lower']} | "
                         f"{note}<br>L: {r['v3']['lower']} | — |")
        else:
            lines.append(f"| {r['id']} | {', '.join(r['covers'])} | {cell(r['v2'])} | {cell(r['v3'])} | "
                         f"{cell(r['aggressive'])} |")
    s = result['summary']
    lines += ['', f"Случаев с ожиданием: {s['judged']} из {s['cases']}; пройдено — v2 {s['passed']['v2']}, "
                  f"v3 {s['passed']['v3']}, aggressive {s['passed']['aggressive']}.",
              f"Исправлено v3: {', '.join(s['fixed_by_v3']) or 'нет'}.",
              f"Новые регрессии v3: {', '.join(s['regressed_in_v3']) or 'нет'}.",
              f"Сменилось первое место: {', '.join(s['first_place_changed']) or 'нет'}.",
              f"Сменилась рекомендация: {', '.join(s['recommendation_changed']) or 'нет'}.",
              f"Запусков с «уточнить»: v2 {s['clarify_runs']['v2']}, v3 {s['clarify_runs']['v3']}, "
              f"aggressive {s['clarify_runs']['aggressive']}; решающих строк названо v3: {s['decisive_rows_v3']}.",
              f"Aggressive хуже v3: {', '.join(s['aggressive_worse_than_v3']) or 'нет'}.",
              f"Известные ограничения: {', '.join(s['known_limits']) or 'нет'}."]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    cases = json.loads(args.cases.read_text(encoding='utf-8'))['cases']
    result = compare(cases)
    text = markdown(result)
    spent = timing(cases)
    text += f"Локальный расчёт score + rank на один запуск: v2 {spent['v2']} мкс, v3 {spent['v3']} мкс (не latency API).\n"
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    sys.stdout.write(text)
    return 0 if not result['summary']['regressed_in_v3'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
