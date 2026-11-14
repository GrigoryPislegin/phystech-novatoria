"""Check saved prototype reports against E6 expectations without calling a model."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from prototype.candidate_profile import ConditionsCheck, ProfileCheck
from prototype.contracts import Evaluation, Facts, Requirements, unique_ids, validate_pair
from prototype.evidence import PairCheck, Source, check_pair, occurrences, sha256_text, verify_span
from prototype.presentation import EXPLANATIONS, gap_question
from prototype.requirements_review import draft


SCHEMA = 'egor-e6-expectations-0.1'
DEFAULT_EXPECTATIONS = Path(__file__).parent / 'expectations/egor/e6-cases.json'
MODES = {
    'replay': {'synthetic_replay_NOT_model_output'},
    'live': {'live_synthetic', 'live_local_privacy'},
}
ROWS = ('pass', 'error', 'missed_requirement', 'wrong_mandatory', 'wrong_status', 'wrong_evidence', 'not_run')
CHECKS = ('pass', 'fail', 'not_run')


def read_json(path):
    with path.open(encoding='utf-8-sig') as stream:
        return json.load(stream)


def load_expectations(path):
    data = read_json(path)
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA:
        raise ValueError('unsupported_expectations_schema')
    cases = data['cases']
    ids = [case['case_id'] for case in cases]
    if not ids or len(set(ids)) != len(ids) or not all(re.fullmatch(r'E6-[A-Z0-9-]+', key) for key in ids):
        raise ValueError('invalid_case_ids')
    for case in cases:
        if case['split'] not in {'dev', 'holdout'} or case['domain'] not in {'frontend', 'fixed_assets', 'education'}:
            raise ValueError('invalid_case_group')
        jobs = {job['job_id']: job['text'] for job in case['vacancies']}
        if len(jobs) != len(case['vacancies']) or not set(case['unprocessed_job_ids']) <= jobs.keys():
            raise ValueError('invalid_expected_jobs')
        if len({row['key'] for row in case['requirements']}) != len(case['requirements']):
            raise ValueError('duplicate_expected_requirement')
        for row in case['requirements']:
            if jobs[row['job_id']].count(row['quote']) != 1 or not row['quote'].strip():
                raise ValueError('invalid_expected_quote')
            if not all(quote.strip() and quote in case['cv_text'] for quote in row['cv_quotes']):
                raise ValueError('invalid_expected_evidence')
    holdout = path.with_name('holdout.sha256')
    if holdout.is_file():
        digest, *ids = holdout.read_text(encoding='utf-8').split()
        selected = [case for case in cases if case['split'] == 'holdout']
        canonical = json.dumps(selected, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if [case['case_id'] for case in selected] != ids or sha256_text(canonical) != digest:
            raise ValueError('holdout_changed')
    return cases


def overlap(text, first, second):
    """Largest overlap of two literal quotes in the same source."""
    if first == second:
        return len(first) if first in text else 0
    longest = 0
    a, b = text.find(first), text.find(second)
    while a != -1 and b != -1:
        end_a, end_b = a + len(first), b + len(second)
        longest = max(longest, min(end_a, end_b) - max(a, b))
        if longest == min(len(first), len(second)):
            break
        if end_a <= end_b:
            a = text.find(first, a + 1)
        else:
            b = text.find(second, b + 1)
    return longest


def evidence_overlaps(text, span, references):
    """Overlap a located fact with expected evidence, including some text."""
    for quote in references:
        for start in occurrences(text, quote):
            left, right = max(start, span.start), min(start + len(quote), span.end)
            if right > left and any(character.isalnum() for character in text[left:right]):
                return True
    return False


def match_requirements(text, expected, extracted):
    """Match one to one, preferring more shared text and then earlier requirements."""
    candidates = []
    for reference in expected:
        quote = reference['quote']
        for row in extracted:
            length = overlap(text, quote, row['quote'])
            if length > 0:
                candidates.append((-length, text.index(quote), reference['key'], row['id']))
    matches, used = {}, set()
    for _, _, key, requirement_id in sorted(candidates):
        if key not in matches and requirement_id not in used:
            matches[key] = requirement_id
            used.add(requirement_id)
    return matches


def row_result(expected, outcome, status=None):
    result = {'job_id': expected['job_id'], 'key': expected['key'], 'outcome': outcome}
    if status is not None:
        result['status'] = status
    return result


def case_result(case, status, row_outcome):
    return {
        'case_id': case['case_id'], 'domain': case['domain'], 'split': case['split'],
        'decision_status': case['decision_status'], 'status': status, 'issues': [],
        'rows': [row_result(row, row_outcome) for row in case['requirements']],
        'extras': [], 'relations': [dict(relation, outcome='not_run') for relation in case['ranking']['relations']],
        'recommendation': 'not_run',
        'conditions': [
            {'job_id': condition['job_id'], 'kind': condition['kind'], 'outcome': 'not_run'}
            for condition in case['conditions']
        ],
        'manual_review': case['forbidden_conclusions'],
    }


def not_run(case):
    return case_result(case, 'not_run', 'not_run')


def case_error(case, code):
    result = case_result(case, 'failed', 'error')
    result['issues'].append(code)
    return result


def report_jobs(report, texts):
    aliases = {jid: jid for jid in texts}
    repeats = Counter()
    for jid, text in texts.items():
        digest = sha256_text(text)[:24]
        repeats[digest] += 1
        aliases[f'job-{digest}-{repeats[digest]}'] = jid

    ranking = report['ranking']
    jobs = {}
    expected_ids = texts.keys()
    previous_rank = 0
    for job in ranking['jobs']:
        jid, rank = aliases[job['job_id']], job['rank']
        if (jid in jobs or type(rank) is not int or rank not in {previous_rank, len(jobs) + 1} or rank < 1):
            raise ValueError('invalid_ranking')
        previous_rank = rank
        jobs[jid] = job
    skipped_ids = set(report['unprocessed_job_ids'])
    skipped = {aliases[jid] for jid in skipped_ids}
    errors = defaultdict(set)
    for error in report['errors']:
        if not isinstance(error['code'], str) or not error['code'].strip():
            raise ValueError('invalid_processing_error')
        if error['job_id'] is None:
            if jobs:
                raise ValueError('global_error_with_processed_jobs')
        else:
            if error['job_id'] not in skipped_ids:
                raise ValueError('invalid_processing_error')
            errors[error['job_id']].add(error['code'])
    if (set(jobs) & skipped or set(jobs) | skipped != expected_ids
            or len(skipped) != len(report['unprocessed_job_ids'])
            or ranking['complete'] is not (not skipped)):
        raise ValueError('invalid_processing_status')
    recorded_failures = set()
    if 'unprocessed' in report:
        entries = {entry['job_id']: entry['reason'] for entry in report['unprocessed']}
        if entries.keys() != skipped_ids or len(entries) != len(report['unprocessed']):
            raise ValueError('invalid_unprocessed_entries')
        if any(jid in errors and reason not in errors[jid] for jid, reason in entries.items()):
            raise ValueError('unprocessed_reason_mismatch')
        recorded_failures = {aliases[jid] for jid, reason in entries.items() if reason in errors[jid]}
    return jobs, skipped, recorded_failures


def checked_evidence(job, requirements, facts, evaluation, cv, vacancy):
    checks = check_pair(requirements, facts, evaluation, cv, vacancy)
    invalid = {row.requirement_id for row in checks.rows if row.state == 'invalid'}
    invalid.update(row.requirement_id for row in checks.mandatory if row.state == 'invalid')
    if job.get('evidence_check') is None:
        return invalid, {row.requirement_id: row.evidence for row in checks.rows}
    stored = PairCheck.model_validate(job['evidence_check'])
    evaluations = {row.requirement_id: row for row in evaluation.rows}
    fact_quotes = {fact.id: fact.quote for fact in facts.items}
    if (stored.cv_sha256 != cv.sha256 or stored.vacancy_id != vacancy.source_id
            or stored.vacancy_sha256 != vacancy.sha256
            or len(stored.rows) != len(evaluations) or len(stored.mandatory) != len(evaluations)
            or {row.requirement_id: row.status for row in stored.rows} !=
               {rid: row.status for rid, row in evaluations.items()}
            or {row.requirement_id for row in stored.mandatory} != evaluations.keys()):
        raise ValueError('invalid_evidence_binding')
    sources = {cv.source_id: cv}
    evidence = {row.requirement_id: row.evidence for row in checks.rows}
    for row in stored.rows:
        expected = {fact_quotes[fid] for fid in evaluations[row.requirement_id].fact_ids}
        actual = {span.quote for span in row.evidence}
        if (row.state == 'invalid' or any(reason.severity == 'invalid' for reason in row.reasons)
                or actual - expected or (row.state == 'structure_ok' and actual != expected)
                or any(verify_span(span, sources) for span in row.evidence)):
            invalid.add(row.requirement_id)
        if row.evidence:
            evidence[row.requirement_id] = row.evidence
    invalid.update(row.requirement_id for row in stored.mandatory
                   if row.state == 'invalid' or any(reason.severity == 'invalid' for reason in row.reasons))
    return invalid, evidence


def check_job(job, expected, facts, cv, vacancy):
    requirements = Requirements.model_validate(job['requirements'])
    evaluation = Evaluation.model_validate(job['evaluation'])
    requirements.validate_source(vacancy.text)
    validate_pair(requirements, facts, evaluation)
    if job.get('requirements_draft') is not None and (
            job['requirements_draft'] != draft(vacancy.source_id, vacancy.text, requirements).model_dump()):
        raise ValueError('invalid_requirements_draft')
    invalid, evidence = checked_evidence(job, requirements, facts, evaluation, cv, vacancy)
    matches = match_requirements(vacancy.text, expected, job['requirements']['items'])
    req_by_id = {req.id: req for req in requirements.items}
    rows = {row.requirement_id: row for row in evaluation.rows}

    outcomes = []
    for reference in expected:
        requirement_id = matches.get(reference['key'])
        if requirement_id is None:
            outcomes.append(row_result(reference, 'missed_requirement'))
            continue
        req, row = req_by_id[requirement_id], rows[requirement_id]
        outcome = 'pass'
        if bool(req.mandatory_quote) != reference['mandatory']:
            outcome = 'wrong_mandatory'
        elif row.status not in reference['allowed_status']:
            outcome = 'wrong_status'
        elif requirement_id in invalid or (row.status != 'unknown' and not any(
                evidence_overlaps(cv.text, span, reference['cv_quotes']) for span in evidence[requirement_id])):
            outcome = 'wrong_evidence'
        outcomes.append(row_result(reference, outcome, row.status))
    return outcomes, len(req_by_id.keys() - set(matches.values()))


def presentation_valid(report, jobs, facts):
    # A saved presentation may be absent on legacy reports. Keep raw model prose
    # out of automatic semantic checks, and validate references if it is present.
    data = report.get('presentation')
    if report.get('verification', {}).get('final_allowed') is True:
        return False
    if data is None:
        return True
    if data.get('final_allowed') is True:
        return False
    seen = set()
    quotes = {fact.id: fact.quote for fact in facts.items}
    for item in data['jobs']:
        jid = item['job_id']
        if jid in seen or jid not in jobs or item['rank'] != jobs[jid]['rank']:
            return False
        seen.add(jid)
        job = jobs[jid]
        if item.get('requirements_draft') != job.get('requirements_draft'):
            return False
        expected = {r['id']: r for r in job['requirements']['items']}
        scored = {r['requirement_id']: r for r in job['evaluation']['rows']}
        rows = {r['requirement_id']: r for r in item['rows']}
        if len(rows) != len(item['rows']) or rows.keys() != expected.keys() or rows.keys() != scored.keys():
            return False
        for requirement_id, row in rows.items():
            req, score = expected[requirement_id], scored[requirement_id]
            if (row['requirement_quote'] != req['quote'] or row['status'] != score['status']
                    or row.get('mandatory_quote') != req['mandatory_quote']
                    or row['resume_quotes'] != [quotes[f] for f in score['fact_ids']]
                    or not row['label'].strip() or row['label'] not in req['quote']
                    or row.get('status_verification') == 'confirmed'
                    or row.get('explanation') != EXPLANATIONS[score['status']]
                    or row.get('question') != gap_question(score['status'], req['quote'])):
                return False
        brief = item.get('manager_brief')
        if brief is not None and (brief['state'] != 'draft_requires_review' or brief['final_allowed'] is not False
                or brief['processing_complete'] is not report['ranking']['complete']
                or any(row != rows.get(row['requirement_id']) for row in brief['grounds'] + brief['risks'])
                or any(question not in {row.get('question') for row in rows.values()} for question in brief['questions'])):
            return False
    return seen == jobs.keys()


def profile_valid(data, facts, cv):
    if data is None:
        return True
    profile = ProfileCheck.model_validate(data)
    if (profile.state == 'invalid' or any(f.severity == 'invalid' for f in profile.findings)
            or profile.spans.keys() != profile.display.keys()):
        return False
    facts_quotes = [fact.quote for fact in facts.items]
    for field, spans in profile.spans.items():
        if any(verify_span(span, {cv.source_id: cv}) or not any(span.quote in quote for quote in facts_quotes)
               for span in spans):
            return False
        display = profile.display[field]
        quotes = [span.quote for span in spans]
        if any(display.strip() and display in quote for quote in quotes) or (quotes and display == ' / '.join(quotes)):
            continue
        ambiguous = any(f.code == 'ambiguous_location' and f.where.startswith(field + '.sources[')
                        for f in profile.findings)
        if profile.state != 'needs_review' or not ambiguous or not (
                any(display.strip() and display in quote for quote in facts_quotes) or all(
                    fragment.strip() and any(fragment in quote for quote in facts_quotes)
                    for fragment in display.split(' / '))):
            return False
    return True


def check_condition(expected, job, facts, cv, vacancy):
    if job is None:
        return 'fail'
    conditions = job.get('conditions')
    if conditions is None:
        return 'not_run'
    checked = ConditionsCheck.model_validate(conditions)
    matches = [item for item in checked.items if item.kind == expected['kind']]
    if len(matches) != 1:
        return 'fail'
    item, = matches
    if (checked.has_invalid or item.state not in expected['allowed_states'] or item.check == 'invalid'
            or any(f.severity == 'invalid' for f in checked.findings + item.findings)):
        return 'fail'
    if item.cv_span and not any(item.cv_span.quote in fact.quote for fact in facts.items):
        return 'fail'
    for span, source in [(item.cv_span, cv), (item.vacancy_span, vacancy)]:
        if span is None:
            if item.state != 'unknown':
                return 'fail'
        elif verify_span(span, {source.source_id: source}):
            return 'fail'
    return 'pass'


def _check_case(case, report, mode):
    if report.get('schema_version') != '0.1':
        return case_error(case, 'unsupported_report_schema')
    if report.get('mode') not in MODES[mode]:
        return case_error(case, 'mode_mismatch')
    texts = {job['job_id']: job['text'] for job in case['vacancies']}
    jobs, skipped, recorded_failures = report_jobs(report, texts)
    cv = Source.of('cv', case['cv_text'])
    if report.get('safe_resume_sha256') not in {None, cv.sha256}:
        return case_error(case, 'resume_source_mismatch')
    facts = Facts.model_validate(report['facts'])
    unique_ids(facts.items)
    sources = {jid: Source.of(job['job_id'], texts[jid]) for jid, job in jobs.items()}
    result = case_result(case, 'checked', 'not_run')
    expected_skips = set(case['unprocessed_job_ids'])
    setup_ok = expected_skips <= recorded_failures
    if not setup_ok:
        result['issues'].append('setup_error')
    if skipped - expected_skips:
        result['issues'].append('unexpected_processing_error')
    if any(not fact.quote.strip() or fact.quote not in cv.text for fact in facts.items):
        result['issues'].append('invalid_fact_quote')
    if not profile_valid(report.get('profile'), facts, cv):
        result['issues'].append('invalid_profile')

    rows_by_job = defaultdict(list)
    for row in case['requirements']:
        rows_by_job[row['job_id']].append(row)
    outcomes = {}
    for jid in texts:
        expected, job = rows_by_job[jid], jobs.get(jid)
        if job is None or jid in expected_skips:
            rows = [row_result(row, 'error') for row in expected]
        else:
            try:
                if job.get('safe_source_sha256') not in {None, sources[jid].sha256}:
                    raise ValueError('vacancy_source_mismatch')
                rows, extras = check_job(job, expected, facts, cv, sources[jid])
                if extras:
                    result['extras'].append({'job_id': jid, 'count': extras})
            except (KeyError, TypeError, ValueError):
                rows = [row_result(row, 'error') for row in expected]
                result['issues'].append('invalid_vacancy_report')
        outcomes.update((row['key'], row) for row in rows)
    result['rows'] = [outcomes[row['key']] for row in case['requirements']]

    if not presentation_valid(report, {job['job_id']: job for job in jobs.values()}, facts):
        result['issues'].append('invalid_presentation')
    if setup_ok:
        recommendation = report['ranking']['recommendation']
        result['recommendation'] = 'pass' if recommendation in case['ranking']['allowed_recommendations'] else 'fail'
        for relation in result['relations']:
            better, worse = jobs.get(relation['better']), jobs.get(relation['worse'])
            satisfied = better and worse and (
                better['rank'] < worse['rank'] if relation['strict'] else better['rank'] <= worse['rank'])
            relation['outcome'] = 'pass' if satisfied else 'fail'
    for expected, outcome in zip(case['conditions'], result['conditions'], strict=True):
        jid = expected['job_id']
        outcome['outcome'] = check_condition(expected, jobs.get(jid), facts, cv, sources.get(jid))
    if (result['issues'] or result['extras'] or any(row['outcome'] != 'pass' for row in result['rows'])
            or result['recommendation'] == 'fail'
            or any(check['outcome'] == 'fail' for check in result['relations'] + result['conditions'])):
        result['status'] = 'failed'
    return result


def check_case(case, report, mode):
    try:
        return _check_case(case, report, mode)
    except (KeyError, TypeError, ValueError, AttributeError):
        return case_error(case, 'invalid_report')


def check_groups(cases, results):
    groups = defaultdict(list)
    for case, result in zip(cases, results, strict=True):
        if case['equivalence_group']:
            groups[case['equivalence_group']].append(result)
    outcomes = []
    for key, group in groups.items():
        status_maps = [{row['key']: row['status'] for row in result['rows'] if 'status' in row} for result in group]
        keys = sorted({row['key'] for result in group for row in result['rows']})
        for requirement in keys:
            statuses = [statuses.get(requirement) for statuses in status_maps]
            if len(statuses) < 2 or None in statuses:
                outcome = 'not_run'
            else:
                outcome = 'pass' if len(set(statuses)) == 1 else 'fail'
            outcomes.append({'group': key, 'key': requirement, 'case_ids': [result['case_id'] for result in group],
                             'outcome': outcome})
    return outcomes


def counts(values, labels):
    total = Counter(values)
    return {label: total[label] for label in labels}


def summarize(results):
    return {
        'cases': counts((result['status'] for result in results), ('checked', 'failed', 'not_run')),
        'expected_rows': sum(len(result['rows']) for result in results),
        'rows': counts((row['outcome'] for result in results for row in result['rows']), ROWS),
        'extra_requirement': sum(extra['count'] for result in results for extra in result['extras']),
        'recommendations': counts((result['recommendation'] for result in results), CHECKS),
        'relations': counts((rel['outcome'] for result in results for rel in result['relations']), CHECKS),
        'conditions': counts((item['outcome'] for result in results for item in result['conditions']), CHECKS),
    }


def markdown(data):
    def summary_row(name, stats):
        rows = stats['rows']
        failures = stats['expected_rows'] - rows['pass'] - rows['not_run']
        return f"| {name} | {stats['expected_rows']} | {rows['pass']} | {failures} | {rows['not_run']} | {stats['extra_requirement']} |"

    lines = ['# Проверка сохранённых отчётов', '', f"Режим — {data['mode']}.",
             'Ожидания зафиксированы отдельно от результатов.']
    if data['model_quality'] == 'not_measured':
        lines.append('Качество модели не измерено.')
    lines += ['', '| Группа | Ожидаемых строк | Прошли | Ошибки | Без прогона | Лишние требования |',
              '|---|---:|---:|---:|---:|---:|', summary_row('Всего', data['overall'])]
    for group, stats in data['groups'].items():
        lines.append(summary_row(group, stats))
    stats = data['overall']
    lines += ['', '| Проверка | Прошли | Ошибки | Без прогона |', '|---|---:|---:|---:|']
    for label, checks in [('Рекомендации', stats['recommendations']), ('Отношения мест', stats['relations']),
                          ('Условия', stats['conditions']), ('Равнозначные формулировки', stats['equivalence'])]:
        lines.append(f"| {label} | {checks['pass']} | {checks['fail']} | {checks['not_run']} |")
    lines += ['', '## Замечания', '']
    for case in data['cases']:
        failed = [row['key'] + ' — ' + row['outcome'] for row in case['rows'] if row['outcome'] not in {'pass', 'not_run'}]
        checks = [
            name for name in ('recommendation',) if case[name] == 'fail'
        ] + [name for name in ('relations', 'conditions') if any(item['outcome'] == 'fail' for item in case[name])]
        details = case['issues'] + failed + checks
        if case['extras']:
            details.append(f"extra_requirement × {sum(extra['count'] for extra in case['extras'])}")
        if details:
            lines.append(f"- {case['case_id']} — " + ', '.join(details))
    for group in data['equivalence']:
        if group['outcome'] == 'fail':
            lines.append(f"- {group['group']}/{group['key']} — group_inconsistent")
    lines += ['', 'Формулировки из списка запрещённых выводов требуют ручной сверки. См. manual_review в JSON.']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expectations', type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument('--reports', required=True, type=Path, help='Папка с файлами <case_id>.json')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--mode', choices=MODES, default='replay')
    args = parser.parse_args(argv)
    try:
        cases = load_expectations(args.expectations)
        if not args.reports.is_dir():
            raise ValueError('missing_reports_directory')
        results = []
        for case in cases:
            path = args.reports / (case['case_id'] + '.json')
            try:
                report = read_json(path)
            except FileNotFoundError:
                result = not_run(case)
            except (OSError, ValueError):
                result = case_error(case, 'unreadable_report')
            else:
                result = check_case(case, report, args.mode)
            results.append(result)
        equivalence = check_groups(cases, results)
        groups = defaultdict(list)
        for result in results:
            for group in (result['domain'], result['split'], f"{result['domain']}/{result['split']}"):
                groups[group].append(result)
        data = {
            'mode': args.mode,
            'expectations_sha256': hashlib.sha256(args.expectations.read_bytes()).hexdigest(),
            'model_quality': 'evaluated_saved_live_reports' if args.mode == 'live' and any(
                row['outcome'] not in {'not_run', 'error'} for result in results for row in result['rows']
            ) else 'not_measured',
            'overall': summarize(results), 'groups': {group: summarize(items) for group, items in sorted(groups.items())},
            'equivalence': equivalence, 'cases': results,
        }
        data['overall']['equivalence'] = counts((group['outcome'] for group in equivalence), CHECKS)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'summary.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (args.out / 'summary.md').write_text(markdown(data), encoding='utf-8')
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        parser.exit(2, 'Не удалось прочитать ожидания или записать сводку.\n')
    print(json.dumps(data['overall']['cases'], ensure_ascii=False))
    return int(any(result['status'] == 'failed' for result in results) or
               any(group['outcome'] == 'fail' for group in equivalence))


if __name__ == '__main__':
    raise SystemExit(main())
