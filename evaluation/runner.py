"""Check saved reports against the E6 expectations. No model calls, no keys, no network.

python -m evaluation.runner --reports DIR --expectations evaluation/expectations/egor/e6-cases.json \\
    --split dev --out OUT

DIR holds `manifest.json` and one report per case:
    {"mode": "synthetic_replay" | "sdk_mock" | "live", "reports": {"E6-FE-01": "E6-FE-01.json", ...}}
Every report must be a pipeline report (schema 0.1) that declares its own `mode` (the CLI values
are mapped: live_* -> live, synthetic_replay_NOT_model_output -> synthetic_replay); a missing or
unknown mode, or one that disagrees with the manifest, is refused, so modes are never mixed.
Actual values are read only from the reports, never from the expectations. Only `live` reports can say anything about model quality; replay and mock runs check
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
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from prototype.candidate_profile import ConditionsCheck, ProfileCheck
from prototype.evidence import Source, Span, verify_span
from prototype.review_queue import build_review_queue

MODES = {'synthetic_replay', 'sdk_mock', 'live'}
# The mode each report declares (prototype CLI / application) -> the manifest mode it belongs to.
REPORT_MODES = {'synthetic_replay_NOT_model_output': 'synthetic_replay', 'synthetic_replay': 'synthetic_replay',
                'synthetic_sdk_mock_NOT_model_output': 'sdk_mock',
                'sdk_mock': 'sdk_mock', 'live_synthetic': 'live', 'live_local_privacy': 'live', 'live': 'live'}
REPORT_SCHEMA = '0.1'
STATUSES = ('full', 'partial', 'fail', 'unknown')
DERIVED_JOB_ID = re.compile(r'job-([0-9a-f]{24})-[1-9][0-9]*')
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
        recorded, *ids = (path.parent / 'holdout.sha256').read_text().split() or ['']
        canon = json.dumps(holdout, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(canon.encode()).hexdigest() != recorded or [c['case_id'] for c in holdout] != ids:
            raise RunnerError('holdout_digest_mismatch')
        return holdout
    if split != 'dev':
        raise RunnerError('unknown_split')
    return [c for c in cases if c['split'] == 'dev']


def _strict_json(text: str):
    def pairs(items):
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise RunnerError('duplicate_keys')
        return dict(items)
    return json.loads(text, object_pairs_hook=pairs)


def load_reports(directory: Path) -> tuple[str, dict[str, dict | None], dict[str, str]]:
    directory = directory.resolve()
    manifest_path = (directory / 'manifest.json').resolve()
    if directory not in manifest_path.parents:
        raise RunnerError('manifest_outside_directory')
    manifest = _strict_json(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or not isinstance(manifest.get('reports'), dict):
        raise RunnerError('malformed_manifest')
    mode = manifest.get('mode')
    if mode not in MODES:
        raise RunnerError('unknown_mode')
    names = list(manifest['reports'].values())
    if not all(isinstance(n, str) for n in names) or len(names) != len(set(names)):
        raise RunnerError('ambiguous_mapping')  # one report per case and one case per report
    reports, problems, paths = {}, {}, set()
    for case_id, name in manifest['reports'].items():
        path = (directory / name).resolve()
        if directory not in path.parents:
            raise RunnerError('report_outside_directory')
        if path == manifest_path or path in paths:
            raise RunnerError('ambiguous_mapping')
        paths.add(path)
        try:
            report = _strict_json(path.read_text(encoding='utf-8'))
        except (OSError, ValueError, RunnerError):
            reports[case_id], problems[case_id] = None, 'unreadable_report'
            continue
        if not isinstance(report, dict):
            reports[case_id], problems[case_id] = None, 'malformed_report'
            continue
        if REPORT_MODES.get(report.get('mode')) != mode:
            raise RunnerError('mixed_or_missing_mode')
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

class _Setup(Exception):
    """The case cannot be evaluated: every check of it is listed as unmeasured with this code."""


def _blank(case: dict) -> dict:
    return {'case_id': case['case_id'], 'domain': case['domain'], 'split': case['split'],
            'decision_status': case['decision_status'], 'setup': 'ok', 'rows': [], 'extra': [],
            'references': [], 'relations': [], 'recommendation': None, 'conditions': [],
            'review_load': None, 'manual_checks': list(case['forbidden_conclusions'])}


def evaluate_case(case: dict, report: dict | None, problem: str | None = None) -> dict:
    result = _blank(case)
    try:
        if report is None:
            raise _Setup(problem or 'missing_report')
        _evaluate(case, report, result)
    except _Setup as setup:
        code = str(setup)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):  # incl. pydantic ValidationError
        code = 'malformed_report'
    else:
        return result
    # Nothing of this case is measured, but every check stays visible as unmeasured, never dropped.
    result = _blank(case)
    result['setup'] = code
    skipped = set(case['unprocessed_job_ids'])
    result['rows'] = [{'job_id': e['job_id'], 'key': e['key'], 'outcome': code} for e in case['requirements']
                      if e['job_id'] not in skipped]
    result['relations'] = [{**rel, 'outcome': code} for rel in case['ranking']['relations']]
    result['recommendation'] = {'actual': None, 'outcome': code}
    result['conditions'] = [{'job_id': c['job_id'], 'kind': c['kind'], 'outcome': code, 'actual': None}
                            for c in case['conditions']]
    return result


def _unique(ids: list, code: str) -> None:
    if len(ids) != len(set(ids)) or not all(isinstance(i, str) and i for i in ids):
        raise _Setup(code)


def _check_shape(report: dict) -> None:
    """The actual report is validated on its own, before any metric and without reading expectations:
    a dict would silently keep one of two duplicate ids, and an unknown status could pass as allowed."""
    _unique([f['id'] for f in report['facts']['items']], 'duplicate_fact_ids')
    jobs = report['ranking']['jobs']
    _unique([j['job_id'] for j in jobs], 'duplicate_job_ids')
    _unique([e['job_id'] for e in report['unprocessed']], 'duplicate_unprocessed_ids')
    for job in jobs:
        rank = job['rank']
        if not isinstance(rank, int) or isinstance(rank, bool) or not 1 <= rank <= len(jobs):
            raise _Setup('invalid_rank')
        _unique([r['id'] for r in job['requirements']['items']], 'duplicate_requirement_ids')
        rows = job['evaluation']['rows']
        _unique([r['requirement_id'] for r in rows], 'duplicate_row_ids')
        if {r['requirement_id'] for r in rows} != {r['id'] for r in job['requirements']['items']}:
            raise _Setup('rows_do_not_cover_requirements')
        for row in rows:
            if row['status'] not in STATUSES or not isinstance(row['fact_ids'], list):
                raise _Setup('invalid_row')


def _validate_processing(report, jobs, failed, expected_failed):
    if report['ranking']['complete'] is not (not failed):
        raise _Setup('invalid_processing_status')
    if 'unprocessed_job_ids' in report and set(report['unprocessed_job_ids']) != failed:
        raise _Setup('invalid_processing_status')
    recorded = {(entry['job_id'], entry['code']) for entry in report['errors']}
    if any(jid not in failed and (jid is not None or jobs) for jid, _ in recorded):
        raise _Setup('invalid_processing_error')
    skipped = {entry['job_id']: entry['reason'] for entry in report['unprocessed']}
    if any((jid, skipped[jid]) not in recorded for jid in expected_failed):
        raise _Setup('expected_failure_not_reproduced')


def _vacancy_ids(report, texts):
    by_digest = defaultdict(list)
    for jid, text in texts.items():
        by_digest[hashlib.sha256(text.encode()).hexdigest()[:24]].append(jid)
    matched = {jid: jid for jid in texts}
    for entry in report['ranking']['jobs'] + report['unprocessed']:
        jid = entry['job_id']
        match = DERIVED_JOB_ID.fullmatch(jid)
        if jid not in matched and match:
            targets = by_digest[match[1]]
            if len(targets) == 1:
                matched[jid] = targets[0]
    return matched


def _mandatory_matches(requirement, expected, vacancy):
    marker = requirement['mandatory_quote']
    if marker is None:
        return not expected
    return (expected and len(marker.strip()) >= 8 and marker in vacancy.text and requirement['quote'] in marker)


def _evaluate(case: dict, report: dict, result: dict) -> None:
    if report.get('schema_version') != REPORT_SCHEMA:
        raise _Setup('unknown_report_version')
    _check_shape(report)
    texts = {v['job_id']: v['text'] for v in case['vacancies']}
    vacancy_ids = _vacancy_ids(report, texts)
    jobs = {vacancy_ids.get(j['job_id'], j['job_id']): j for j in report['ranking']['jobs']}
    failed = {vacancy_ids.get(row['job_id'], row['job_id']): row['job_id'] for row in report['unprocessed']}
    facts = {f['id']: f['quote'] for f in report['facts']['items']}
    if jobs.keys() | failed.keys() != texts.keys() or jobs.keys() & failed.keys():
        raise _Setup('job_set_mismatch')
    if len(jobs) != len(report['ranking']['jobs']) or len(failed) != len(report['unprocessed']):
        raise _Setup('job_set_mismatch')
    expected_failed = set(case['unprocessed_job_ids'])
    if not expected_failed <= failed.keys():
        raise _Setup('expected_failure_not_reproduced')
    _validate_processing(report, jobs, set(failed.values()), {failed[jid] for jid in expected_failed})
    cv = Source.of('cv', case['cv_text'])
    if report.get('safe_resume_sha256', cv.sha256) != cv.sha256:
        raise _Setup('resume_source_mismatch')
    sources = {jid: Source.of(job['job_id'], texts[jid]) for jid, job in jobs.items()}
    if any(job.get('safe_source_sha256', sources[jid].sha256) != sources[jid].sha256
           for jid, job in jobs.items()):
        raise _Setup('vacancy_source_mismatch')

    for fid, quote in facts.items():  # facts must come from the CV
        if not quote.strip() or quote not in cv.text:
            result['references'].append({'kind': 'fact_not_in_cv', 'fact_id': fid})
    if not _profile_valid(report.get('profile'), facts.values(), cv):
        result['references'].append({'kind': 'invalid_profile'})
    for job_id, job in jobs.items():
        checks = job.get('evidence_check')
        if checks is not None and not _evidence_valid(checks, facts, cv, sources[job_id]):
            result['references'].append({'kind': 'invalid_evidence_source', 'job_id': job_id})
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
                     'mandatory_ok': _mandatory_matches(requirement, e['mandatory'], sources[job_id]),
                     'status_ok': status not in e['forbidden_status'],
                     'evidence_ok': None if status == 'unknown' else _evidence_ok(
                         row, checks.get(requirement['id']), facts, cv.text, e['cv_quotes'])}
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
        job_id = expect['job_id']
        job = jobs.get(job_id)
        outcome, actual = 'not_run', None
        if job is not None:
            outcome, actual = _check_condition(expect, job.get('conditions'),
                                               'analysis_schema_version' in report, facts.values(), cv, sources[job_id])
        result['conditions'].append({'job_id': job_id, 'kind': expect['kind'], 'outcome': outcome,
                                     'actual': actual})
    result['review_load'] = _load(report)


def _profile_valid(data, facts, cv):
    if data is None:
        return True
    profile = ProfileCheck.model_validate(data)
    if (profile.state == 'invalid' or any(f.severity == 'invalid' for f in profile.findings)
            or profile.spans.keys() != profile.display.keys()):
        return False
    for field, spans in profile.spans.items():
        if any(verify_span(span, {'cv': cv}) or not any(span.quote in quote for quote in facts) for span in spans):
            return False
        value = profile.display[field]
        quotes = [span.quote for span in spans]
        if any(value.strip() and value in quote for quote in quotes) or (quotes and value == ' / '.join(quotes)):
            continue
        # Ambiguous sources still have literal fact quotes, but no single offset.
        ambiguous = any(f.code == 'ambiguous_location' and f.where.startswith(field + '.sources[')
                        for f in profile.findings)
        if profile.state != 'needs_review' or not ambiguous or not (
                any(value.strip() and value in quote for quote in facts) or all(
                    part.strip() and any(part in quote for quote in facts) for part in value.split(' / '))):
            return False
    return True


def _evidence_valid(checks, facts, cv, vacancy):
    if (checks['cv_sha256'] != cv.sha256 or checks['vacancy_id'] != vacancy.source_id
            or checks['vacancy_sha256'] != vacancy.sha256):
        return False
    return all(not verify_span(Span.model_validate(data), {'cv': cv}) and data['quote'] in facts.values()
               for row in checks['rows'] for data in row['evidence'])


def _check_condition(expect, data, modern, facts, cv, vacancy):
    if data is None:
        return ('fail' if modern else 'not_run'), None
    conditions = ConditionsCheck.model_validate(data)
    items = [item for item in conditions.items if item.kind == expect['kind']]
    if len(items) != 1:
        return 'fail', None
    item, = items
    if (item.state not in expect['allowed_states'] or item.check == 'invalid' or conditions.has_invalid
            or any(f.severity == 'invalid' for f in conditions.findings + item.findings)):
        return 'fail', item.state
    if item.cv_span and not any(item.cv_span.quote in quote for quote in facts):
        return 'fail', item.state
    for span, source in ((item.cv_span, cv), (item.vacancy_span, vacancy)):
        if span is None:
            if item.state != 'unknown':
                return 'fail', item.state
        elif verify_span(span, {source.source_id: source}):
            return 'fail', item.state
    return 'pass', item.state


def _evidence_ok(row: dict, check: dict | None, facts: dict[str, str], cv: str, expected_quotes: list[str]) -> bool:
    """A cited fact lies at least half inside an expected CV quote, and E3 did not find the row invalid.

    Half of the cited span, not any overlap: a fact quoting a whole paragraph overlaps every expected quote.
    """
    if check is not None and check.get('state') == 'invalid':
        return False
    wanted = [s for s in (_span(cv, q) for q in expected_quotes) if s]
    cited = [s for s in (_span(cv, facts.get(f, '')) for f in row['fact_ids']) if s]
    return any(2 * _overlap(w, c) >= c[1] - c[0] and any(
        char.isalnum() for char in cv[max(w[0], c[0]):min(w[1], c[1])]) for w in wanted for c in cited)


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
    expected_rows = [(c, row) for c, row in rows if row['outcome'] != 'not_applicable']
    PROCESSING = {'pass', 'wrong_status', 'wrong_evidence', 'wrong_mandatory', 'missed_requirement'}

    def row_checks(results_subset):
        """Correctness of paired rows; rows that could not be checked stay listed under their reason."""
        sub = [(c, row) for c, row in expected_rows if c in results_subset]
        paired = [(c, row) for c, row in sub if 'status' in row]
        open_ = [(c, row['outcome']) for c, row in sub if 'status' not in row]
        return {
            'status_allowed': [(c, _flag(row['status_ok'])) for c, row in paired] + open_,
            'evidence_matches_expected_quote': [(c, _flag(row['evidence_ok'])) for c, row in paired
                                                if row['status_ok']] + open_,
            'mandatory_marking': [(c, _flag(row['mandatory_ok'])) for c, row in paired] + open_,
            'row_fully_correct': [(c, 'pass' if row['outcome'] == 'pass' else 'fail') for c, row in paired] + open_,
        }

    case_ids = {r['case_id'] for r in results}
    metrics = [
        # completeness of processing
        _metric('cases_evaluated', [(r['case_id'], 'pass' if r['setup'] == 'ok' else 'fail') for r in results]),
        _metric('rows_without_processing_error',
                [(c, 'fail' if row['outcome'] == 'error' else 'pass' if row['outcome'] in PROCESSING
                  else row['outcome']) for c, row in expected_rows]),
        _metric('requirement_extraction_coverage',
                [(c, 'fail' if row['outcome'] == 'missed_requirement' else 'pass' if row['outcome'] in PROCESSING
                  else row['outcome']) for c, row in expected_rows if row['outcome'] != 'error']),
        # correctness of what could be checked
        *[_metric(name, items) for name, items in row_checks(case_ids).items()],
        _metric('rank_relations', [(r['case_id'], x['outcome']) for r in results for x in r['relations']]),
        _metric('recommendation_allowed', [(r['case_id'], r['recommendation']['outcome']) for r in results
                                           if r['recommendation']]),
        _metric('conditions', [(r['case_id'], x['outcome']) for r in results for x in r['conditions']]),
        _metric('references_valid', [(r['case_id'], ('fail' if r['references'] else 'pass') if r['setup'] == 'ok'
                                      else r['setup']) for r in results]),
    ]
    by_domain = {domain: [_metric(name, items) for name, items in
                          row_checks({r['case_id'] for r in results if r['domain'] == domain}).items()
                          if name in ('status_allowed', 'row_fully_correct')]
                 for domain in sorted({r['domain'] for r in results})}
    groups = defaultdict(list)
    for case, r in zip(cases, results):
        if case['equivalence_group']:
            groups[case['equivalence_group']].append(r)
    group_items = []
    for name, members in sorted(groups.items()):
        statuses = [{row['key']: row.get('status') for row in m['rows']} for m in members]
        measured = len(members) > 1 and all(m['setup'] == 'ok' and all('status' in row for row in m['rows'])
                                            for m in members)
        group_items.append((name, ('pass' if all(s == statuses[0] for s in statuses) else 'fail') if measured
                            else 'unmeasured'))
    metrics.append(_metric('equivalent_wording_consistent', group_items))
    load = [r['review_load'] for r in results if r['review_load']]
    return {'schema_version': 'egor-e9-evaluation-0.1', 'mode': mode,
            # live AND something was actually evaluated; an empty or unusable live run measures nothing
            'quality_measured': mode == 'live' and any(r['setup'] == 'ok' for r in results),
            'note': ('Ожидания — черновик команды (draft), не ответы эксперта. Доли — прошедшие проверки, '
                     'не вероятность истинности.') + (
                ' Режим не live: качество модели не измерено.' if mode != 'live' else
                '' if any(r['setup'] == 'ok' for r in results) else
                ' Режим live, но ни один отчёт не оценён: качество модели не измерено.'),
            'cases': len(cases), 'unknown_report_ids': unknown_ids,
            'row_outcomes': dict(Counter(row['outcome'] for _, row in rows)), 'metrics': metrics,
            'by_domain': by_domain,
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


def _write_summary(directory, summary):
    outputs = {
        'evaluation.json': json.dumps(summary, ensure_ascii=False, indent=1) + '\n',
        'evaluation.md': to_markdown(summary),
    }
    if directory.is_symlink() or any((directory / name).is_symlink() for name in outputs):
        raise RunnerError('output_symlink')
    directory.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.evaluation-', dir=directory) as temporary:
        stage = Path(temporary)
        for name, content in outputs.items():
            (stage / name).write_text(content, encoding='utf-8')
        for name in outputs:
            (stage / name).replace(directory / name)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, required=True)
    parser.add_argument('--split', choices=('dev', 'holdout'), default='dev')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true',
                        help='Exit 1 on failures or missing expected comparisons, after writing the summary.')
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.expectations, args.split)
        mode, reports, problems = load_reports(args.reports)
        summary = run(cases, mode, reports, problems)
        _write_summary(args.out, summary)
    except (RunnerError, OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        code = str(exc) if isinstance(exc, RunnerError) else type(exc).__name__
        print(f'evaluation refused: {code}', file=sys.stderr)
        return 2
    print(to_markdown(summary))
    return int(args.check and (not cases or not reports or summary['extra_requirements'] > 0
                               or any(metric['failures'] for metric in summary['metrics'])
                               or any(item['outcome'] == 'not_run' for case in summary['results']
                                      for item in case['conditions'])))


if __name__ == '__main__':
    sys.exit(main())
