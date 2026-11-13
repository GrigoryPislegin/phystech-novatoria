"""Check saved reports against the E6 expectations. No model calls, no keys, no network.

python -m evaluation.runner --reports DIR --expectations evaluation/expectations/egor/e6-cases.json \\
    --split dev --out OUT

DIR holds `manifest.json` and one report per case:
    {"mode": "synthetic_replay" | "sdk_mock" | "live", "reports": {"E6-FE-01": "E6-FE-01.json", ...}}
Every report must be a pipeline report (schema 0.1) whose own `mode`, if present, agrees with the
manifest; mixed modes are refused. Actual values are read only from the reports, never from the
expectations. Only `live` reports can say anything about model quality; replay and mock runs check
the pipeline and this runner.

Each metric has a numerator, a denominator and the cases behind every failure, skip and
unmeasured item. A missing report, an empty result, an unknown version or an incomplete pair is
counted as not measured: an empty denominator gives `value: null`, never 100%. The numbers are
shares of checks passed under the team's draft expectations, not probabilities of truth.
The holdout split is used only when asked for, after its recorded digest matches.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from prototype.review_queue import build_review_queue

MODES = {'synthetic_replay', 'sdk_mock', 'live'}
REPORT_SCHEMA = '0.1'
STATUSES = ('full', 'partial', 'fail', 'unknown')
ROW_OUTCOMES = ('pass', 'wrong_status', 'wrong_evidence', 'wrong_mandatory', 'missed_requirement', 'error',
                'not_applicable')


class RunnerError(Exception):
    """The run cannot be evaluated at all (bad manifest, mixed modes, holdout digest)."""


# ---------- inputs ----------------------------------------------------------------------------

def load_cases(path: Path, split: str) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    cases = data['cases']
    if split == 'holdout':
        holdout = [c for c in cases if c['split'] == 'holdout']
        recorded, *ids = (path.parent / 'holdout.sha256').read_text().split()
        canon = json.dumps(holdout, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(canon.encode()).hexdigest() != recorded or [c['case_id'] for c in holdout] != ids:
            raise RunnerError('holdout_digest_mismatch')
        return holdout
    if split != 'dev':
        raise RunnerError('unknown_split')
    return [c for c in cases if c['split'] == 'dev']


def load_reports(directory: Path) -> tuple[str, dict[str, dict | None], dict[str, str]]:
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    mode = manifest.get('mode')
    if mode not in MODES:
        raise RunnerError('unknown_mode')
    reports, problems = {}, {}
    for case_id, name in manifest.get('reports', {}).items():
        path = (directory / name).resolve()
        if directory.resolve() not in path.parents:
            raise RunnerError('report_outside_directory')
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            reports[case_id], problems[case_id] = None, 'unreadable_report'
            continue
        if report.get('mode') not in (None, mode):
            raise RunnerError('mixed_modes')
        reports[case_id] = report
    return mode, reports, problems


# ---------- matching --------------------------------------------------------------------------

def _span(text: str, quote: str) -> tuple[int, int] | None:
    """Position of a quote that occurs exactly once; None when absent or ambiguous."""
    if not quote or text.count(quote) != 1:
        return None
    start = text.find(quote)
    return start, start + len(quote)


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def match_requirements(expected: list[dict], extracted: list[dict], text: str) -> dict[str, dict]:
    """One-to-one by overlap in the vacancy text; the longer overlap wins, then the earlier expected."""
    want = {e['key']: _span(text, e['quote']) for e in expected}
    got = [(r, _span(text, r['quote'])) for r in extracted]
    pairs = sorted(((_overlap(w, g), want[key][0], key, i) for key, w in want.items() if w
                    for i, (_, g) in enumerate(got) if g and _overlap(w, g) > 0), key=lambda p: (-p[0], p[1]))
    taken_keys, taken_rows, matched = set(), set(), {}
    for _, _, key, i in pairs:
        if key not in taken_keys and i not in taken_rows:
            matched[key] = got[i][0]
            taken_keys.add(key)
            taken_rows.add(i)
    return matched


# ---------- one case ---------------------------------------------------------------------------

def evaluate_case(case: dict, report: dict | None, problem: str | None = None) -> dict:
    result = {'case_id': case['case_id'], 'domain': case['domain'], 'split': case['split'],
              'decision_status': case['decision_status'], 'setup': 'ok', 'rows': [], 'extra': [],
              'references': [], 'relations': [], 'recommendation': None, 'conditions': [],
              'review_load': None, 'manual_checks': list(case['forbidden_conclusions'])}
    if report is None:
        result['setup'] = problem or 'missing_report'
        return result
    if report.get('schema_version') != REPORT_SCHEMA:
        result['setup'] = 'unknown_report_version'
        return result
    try:
        jobs = {j['job_id']: j for j in report['ranking']['jobs']}
        failed = {e['job_id'] for e in report.get('unprocessed', [])}
        facts = {f['id']: f['quote'] for f in report['facts']['items']}
    except (KeyError, TypeError):
        result['setup'] = 'malformed_report'
        return result
    texts = {v['job_id']: v['text'] for v in case['vacancies']}
    if set(jobs) | failed != set(texts) or set(jobs) & failed:
        result['setup'] = 'job_set_mismatch'
        return result
    expected_failed = set(case['unprocessed_job_ids'])
    if not expected_failed <= failed:
        result['setup'] = 'expected_failure_not_reproduced'  # e.g. the job was simply left out of rank
        return result
    cv = case['cv_text']

    for fid, quote in facts.items():  # facts must come from the CV
        if quote not in cv:
            result['references'].append({'kind': 'fact_not_in_cv', 'fact_id': fid})
    for job_id, job in jobs.items():
        for r in job['requirements']['items']:
            if r['quote'] not in texts[job_id]:
                result['references'].append({'kind': 'requirement_not_in_vacancy', 'job_id': job_id,
                                             'requirement_id': r['id']})
        for row in job['evaluation']['rows']:
            for fid in row['fact_ids']:
                if fid not in facts:
                    result['references'].append({'kind': 'unknown_fact_id', 'job_id': job_id, 'fact_id': fid})

    for job_id in texts:
        expected = [e for e in case['requirements'] if e['job_id'] == job_id]
        if job_id in failed:
            outcome = 'not_applicable' if job_id in expected_failed else 'error'
            result['rows'] += [{'job_id': job_id, 'key': e['key'], 'outcome': outcome} for e in expected]
            continue
        job = jobs[job_id]
        matched = match_requirements(expected, job['requirements']['items'], texts[job_id])
        rows = {r['requirement_id']: r for r in job['evaluation']['rows']}
        checks = {c['requirement_id']: c for c in job.get('evidence_check', {}).get('rows', [])}
        paired = {r['id'] for r in matched.values()}
        result['extra'] += [{'job_id': job_id, 'requirement_id': r['id']} for r in job['requirements']['items']
                            if r['id'] not in paired]
        for e in expected:
            requirement = matched.get(e['key'])
            if requirement is None:
                result['rows'].append({'job_id': job_id, 'key': e['key'], 'outcome': 'missed_requirement'})
                continue
            row = rows.get(requirement['id'])
            if row is None:
                result['rows'].append({'job_id': job_id, 'key': e['key'], 'outcome': 'error'})
                continue
            status = row['status']
            entry = {'job_id': job_id, 'key': e['key'], 'requirement_id': requirement['id'], 'status': status,
                     'mandatory_ok': (requirement['mandatory_quote'] is not None) == e['mandatory'],
                     'status_ok': status not in e['forbidden_status'],
                     'evidence_ok': None if status == 'unknown' else _evidence_ok(
                         row, checks.get(requirement['id']), facts, cv, e['cv_quotes'])}
            entry['outcome'] = ('wrong_mandatory' if not entry['mandatory_ok'] else 'wrong_status'
                                if not entry['status_ok'] else 'wrong_evidence' if entry['evidence_ok'] is False
                                else 'pass')
            result['rows'].append(entry)

    places = {j: jobs[j]['rank'] for j in jobs}
    for rel in case['ranking']['relations']:
        better, worse = rel['better'], rel['worse']
        if better not in places or worse not in places:
            result['relations'].append({**rel, 'outcome': 'unmeasured'})
            continue
        ok = places[better] < places[worse] if rel['strict'] else places[better] <= places[worse]
        result['relations'].append({**rel, 'outcome': 'pass' if ok else 'fail'})
    recommendation = report['ranking'].get('recommendation')
    result['recommendation'] = {'actual': recommendation,
                                'outcome': 'pass' if recommendation in case['ranking']['allowed_recommendations']
                                else 'fail'}
    for expect in case['conditions']:
        job = jobs.get(expect['job_id'])
        found = None
        if job and isinstance(job.get('conditions'), dict):
            found = next((i for i in job['conditions'].get('items', []) if i.get('kind') == expect['kind']), None)
        if job is None or job.get('conditions') is None:
            outcome = 'not_run'
        elif found is None:
            outcome = 'fail'  # the condition was compared, this kind is missing
        else:
            outcome = 'pass' if found.get('state') in expect['allowed_states'] else 'fail'
        result['conditions'].append({'job_id': expect['job_id'], 'kind': expect['kind'], 'outcome': outcome,
                                     'actual': found.get('state') if found else None})
    result['review_load'] = _load(report)
    return result


def _evidence_ok(row: dict, check: dict | None, facts: dict[str, str], cv: str, expected_quotes: list[str]) -> bool:
    """The row cites at least one fact overlapping an expected CV quote, and E3 did not find it invalid."""
    if check is not None and check.get('state') == 'invalid':
        return False
    wanted = [s for s in (_span(cv, q) for q in expected_quotes) if s]
    cited = [s for s in (_span(cv, facts.get(f, '')) for f in row['fact_ids']) if s]
    return any(_overlap(w, c) for w in wanted for c in cited)


def _load(report: dict) -> dict:
    queue = build_review_queue(report)
    rows = [r for j in report['ranking']['jobs'] for r in j['evaluation']['rows']]
    checks = [c for j in report['ranking']['jobs'] for c in j.get('evidence_check', {}).get('rows', [])]
    return {'queue_items': len(queue.items), 'by_priority': queue.by_priority, 'rows': len(rows),
            'unknown_rows': sum(r['status'] == 'unknown' for r in rows),
            'fail_rows': sum(r['status'] == 'fail' for r in rows),
            'needs_review_rows': sum(c['state'] == 'needs_review' for c in checks),
            'condition_conflicts': sum(len((j.get('conditions') or {}).get('conflicts', []))
                                       for j in report['ranking']['jobs'])}


# ---------- run ---------------------------------------------------------------------------------

def _metric(name: str, items: list[tuple[str, str]]) -> dict:
    """items: (case_id, 'pass' | 'fail' | anything else = unmeasured). Unmeasured stays out of the denominator."""
    num = sum(o == 'pass' for _, o in items)
    den = sum(o in ('pass', 'fail') for _, o in items)
    return {'metric': name, 'numerator': num, 'denominator': den, 'value': round(num / den, 4) if den else None,
            'failures': sorted({c for c, o in items if o == 'fail'}),
            'unmeasured': sorted({f'{c}:{o}' for c, o in items if o not in ('pass', 'fail')})}


def _flag(value) -> str:
    return 'unmeasured' if value is None else 'pass' if value else 'fail'


def run(cases: list[dict], mode: str, reports: dict[str, dict | None], problems: dict[str, str]) -> dict:
    results = [evaluate_case(c, reports.get(c['case_id']), problems.get(c['case_id'])) for c in cases]
    unknown_ids = sorted(set(reports) - {c['case_id'] for c in cases})
    rows = [(r['case_id'], row) for r in results for row in r['rows']]
    paired = [(c, row) for c, row in rows if 'status' in row]
    expected_rows = [(c, row) for c, row in rows if row['outcome'] != 'not_applicable']
    metrics = [
        # completeness of processing
        _metric('cases_evaluated', [(r['case_id'], 'pass' if r['setup'] == 'ok' else 'fail') for r in results]),
        _metric('rows_without_processing_error',
                [(c, 'fail' if row['outcome'] == 'error' else 'pass') for c, row in expected_rows]),
        _metric('requirement_extraction_coverage',
                [(c, 'fail' if row['outcome'] == 'missed_requirement' else 'pass') for c, row in expected_rows
                 if row['outcome'] != 'error']),
        # correctness of what could be checked
        _metric('status_allowed', [(c, _flag(row['status_ok'])) for c, row in paired]),
        _metric('evidence_matches_expected_quote', [(c, _flag(row['evidence_ok'])) for c, row in paired
                                                    if row['status_ok']]),
        _metric('mandatory_marking', [(c, _flag(row['mandatory_ok'])) for c, row in paired]),
        _metric('row_fully_correct', [(c, 'pass' if row['outcome'] == 'pass' else 'fail') for c, row in paired]),
        _metric('rank_relations', [(r['case_id'], x['outcome']) for r in results for x in r['relations']]),
        _metric('recommendation_allowed', [(r['case_id'], r['recommendation']['outcome']) for r in results
                                           if r['recommendation']]),
        _metric('conditions', [(r['case_id'], x['outcome']) for r in results for x in r['conditions']]),
        _metric('references_valid', [(r['case_id'], 'fail' if r['references'] else 'pass') for r in results
                                     if r['setup'] == 'ok']),
    ]
    groups = defaultdict(list)
    for case, r in zip(cases, results):
        if case['equivalence_group']:
            groups[case['equivalence_group']].append(r)
    group_items = []
    for name, members in sorted(groups.items()):
        statuses = [{row['key']: row.get('status') for row in m['rows']} for m in members]
        measured = all(m['setup'] == 'ok' and all('status' in row for row in m['rows']) for m in members)
        group_items.append((name, ('pass' if all(s == statuses[0] for s in statuses) else 'fail') if measured
                            else 'unmeasured'))
    metrics.append(_metric('equivalent_wording_consistent', group_items))
    load = [r['review_load'] for r in results if r['review_load']]
    return {'schema_version': 'egor-e9-evaluation-0.1', 'mode': mode,
            'quality_measured': mode == 'live',
            'note': ('Ожидания — черновик команды (draft), не ответы эксперта. Доли — прошедшие проверки, '
                     'не вероятность истинности.') + ('' if mode == 'live' else
                                                      ' Режим не live: качество модели не измерено.'),
            'cases': len(cases), 'unknown_report_ids': unknown_ids,
            'row_outcomes': dict(Counter(row['outcome'] for _, row in rows)), 'metrics': metrics,
            'review_load': {k: sum(x[k] for x in load) for k in ('queue_items', 'rows', 'unknown_rows', 'fail_rows',
                                                                 'needs_review_rows', 'condition_conflicts')}
            if load else None,
            'extra_requirements': sum(len(r['extra']) for r in results),
            'manual_checks': sum(len(r['manual_checks']) for r in results if r['setup'] == 'ok'),
            'results': results}


def to_markdown(summary: dict) -> str:
    lines = ['# Проверка отчётов против E6', '',
             f"Режим: `{summary['mode']}`. Случаев: {summary['cases']}. {summary['note']}", '',
             '| Метрика | Числитель | Знаменатель | Доля | Провалы | Не измерено |', '|---|---|---|---|---|---|']
    for m in summary['metrics']:
        value = 'не измерено' if m['value'] is None else f"{m['value']:.2%}"
        lines.append(f"| {m['metric']} | {m['numerator']} | {m['denominator']} | {value} | "
                     f"{', '.join(m['failures']) or '—'} | {', '.join(m['unmeasured']) or '—'} |")
    lines += ['', f"Исходы строк: {summary['row_outcomes'] or 'нет'}",
              f"Нагрузка проверки: {summary['review_load'] or 'не измерена'}",
              f"Запрещённые выводы для ручной проверки: {summary['manual_checks']}"]
    if summary['unknown_report_ids']:
        lines.append(f"Отчёты без случая: {', '.join(summary['unknown_report_ids'])}")
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, required=True)
    parser.add_argument('--split', choices=('dev', 'holdout'), default='dev')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.expectations, args.split)
        mode, reports, problems = load_reports(args.reports)
    except (RunnerError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f'evaluation refused: {exc}', file=sys.stderr)
        return 2
    summary = run(cases, mode, reports, problems)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'evaluation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n',
                                              encoding='utf-8')
    (args.out / 'evaluation.md').write_text(to_markdown(summary), encoding='utf-8')
    print(to_markdown(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
