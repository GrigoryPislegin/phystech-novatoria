"""Local N-C3 span regression on a fixed, wholly synthetic corpus. Never calls an API."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from prototype.privacy_core import Detector, LocalPrivacy, POLICY_VERSION, normalized
from prototype.privacy_core.models import MODELS, load

CORPUS = Path(__file__).parent / 'fixtures' / 'privacy' / 'cases.json'


def validate_cases(document):
    if (document.get('origin') != 'synthetic' or not isinstance(document.get('cases'), list)
            or not document['cases']):
        raise ValueError('synthetic_corpus_required')
    seen = set()
    for case in document['cases']:
        if not isinstance(case.get('id'), str) or case['id'] in seen or not isinstance(case.get('text'), str):
            raise ValueError('invalid_case')
        seen.add(case['id'])
        text = normalized(case['text'])
        if not isinstance(case.get('expected'), list) or not case['expected']:
            raise ValueError('annotations_required')
        for span in case['expected']:
            start, end = span.get('start'), span.get('end')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or span.get('role') not in {'identifier', 'professional'}
                    or text[start:end] != span.get('quote')):
                raise ValueError('invalid_expected_span')
    return document['cases']


def assess_case(case, findings, error=None):
    """Offsets refer to normalized source; overlapping detector spans count only once."""
    text = normalized(case['text'])
    covered = set()
    for finding in findings:
        if not 0 <= finding.start < finding.end <= len(text):
            raise ValueError('invalid_detected_span')
        covered.update(range(finding.start, finding.end))
    spans = []
    for span in case['expected']:
        count = len(covered.intersection(range(span['start'], span['end'])))
        if error:
            outcome = 'not_run'
        elif span['role'] == 'identifier':
            outcome = 'masked' if count == span['end'] - span['start'] else 'partially_masked' if count else 'missed'
        else:
            outcome = 'removed' if count else 'preserved'
        spans.append({**span, 'covered_characters': count if not error else None, 'outcome': outcome})
    return {'id': case['id'], 'status': 'blocked' if error else 'assessed', 'error': error,
            'known_limit': case.get('known_limit'), 'normalized_text': text,
            'source_sha256': hashlib.sha256(text.encode()).hexdigest(), 'spans': spans,
            'findings': [{'start': f.start, 'end': f.end, 'kind': f.kind, 'quote': text[f.start:f.end]}
                         for f in findings]}


def aggregate(results):
    metrics = {}
    for name, role, success in [('identifiers_masked', 'identifier', 'masked'),
                                ('professional_preserved', 'professional', 'preserved')]:
        rows = [(case['id'], span) for case in results for span in case['spans'] if span['role'] == role]
        assessed = [(cid, span) for cid, span in rows if span['outcome'] != 'not_run']
        passed = sum(span['outcome'] == success for _, span in assessed)
        metrics[name] = {'expected': len(rows), 'assessed': len(assessed), 'passed': passed,
                         'failed': len(assessed) - passed, 'unmeasured': len(rows) - len(assessed),
                         'value': passed / len(assessed) if assessed else None,
                         'failure_case_ids': sorted({cid for cid, span in assessed if span['outcome'] != success})}
    return metrics


async def evaluate(cases, detector, mode):
    results = []
    for case in cases:
        if detector is None:
            results.append(assess_case(case, [], error='models_unavailable'))
            continue
        class RecordingDetector:
            first = None
            additional_findings = False

            def scan(self, text):
                found = detector.scan(text)
                if self.first is None:
                    self.first = list(found)
                elif found:
                    self.additional_findings = True
                return found
        recorder = RecordingDetector()
        privacy = LocalPrivacy(recorder)
        try:
            await privacy.redact(case['text'])  # Includes the actual residual-PII check.
            # Later offsets refer to transformed text, not the annotated source.
            # Do not call first-pass preservation a measurement of the final result.
            result = assess_case(case, [] if recorder.additional_findings else (recorder.first or []),
                                 error='multipass_metrics_unavailable' if recorder.additional_findings else None)
            result['privacy_summary'] = privacy.summary()
        except Exception:
            # A blocked transformation must not become a perfect or safely empty result.
            result = assess_case(case, [], error='privacy_execution_failed')
        finally:
            privacy.close()
        results.append(result)
    metrics = aggregate(results)
    assessed = sum(case['status'] == 'assessed' for case in results)
    return {'schema_version': 'privacy-acceptance-0.1', 'mode': mode, 'origin': 'synthetic',
            'policy_version': POLICY_VERSION, 'cases_expected': len(cases), 'cases_assessed': assessed,
            'scope': 'synthetic_span_regression_only', 'anonymity_verified': False,
            'semantic_model_quality_measured': False, 'model_api_calls': 0,
            'metrics': metrics, 'cases': results}


def markdown(report):
    lines = ['# Privacy acceptance — синтетический корпус', '',
             f"Режим: `{report['mode']}`; оценено {report['cases_assessed']}/{report['cases_expected']} случаев.",
             'Не измеряет анонимность, recall реальных резюме или качество модели подбора.', '',
             '| Метрика | Успешно / оценено | Ожидалось | Не измерено |', '|---|---:|---:|---:|']
    for name, metric in report['metrics'].items():
        lines.append(f"| {name} | {metric['passed']}/{metric['assessed']} | {metric['expected']} | {metric['unmeasured']} |")
    for case in report['cases']:
        lines.extend(['', f"## {case['id']} — {case['status']}", ''])
        if case['known_limit']:
            lines.append('Известное ограничение (остаётся в знаменателе): ' + case['known_limit'])
        if case['error']:
            lines.append('Ошибка: ' + case['error'])
        lines.extend(['', '| Роль | Ожидаемый фрагмент | [start, end) | Результат |', '|---|---|---|---|'])
        for span in case['spans']:
            quote = span['quote'].replace('|', '\\|').replace('\n', ' ↵ ')
            lines.append(f"| {span['role']} | {quote} | [{span['start']}, {span['end']}) | {span['outcome']} |")
        findings = [f"{f['kind']}[{f['start']}:{f['end']}]={f['quote']!r}" for f in case['findings']]
        finding_text = ('; '.join(findings) or 'нет')
        if case['error'] == 'multipass_metrics_unavailable':
            finding_text = 'итоговые смещения не измерены; маскирование завершилось за несколько проходов'
        lines.extend(['', 'Найденные фрагменты: ' + finding_text])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models-dir', type=Path, default=Path('data/private/privacy-models'))
    parser.add_argument('--out', required=True, type=Path, help='New directory; previous reports are never overwritten')
    args = parser.parse_args()
    from prototype.privacy import protect_dependency_logs
    protect_dependency_logs()
    try:
        cases = validate_cases(json.loads(CORPUS.read_text()))
        try:
            detector = Detector(load(args.models_dir))
        except Exception:
            detector = None
        report = asyncio.run(evaluate(cases, detector, 'real_local_ner_on_synthetic'))
        report['corpus_sha256'] = hashlib.sha256(CORPUS.read_bytes()).hexdigest()
        report['model_artifacts'] = {name: value[1] for name, value in MODELS.items()} if detector else {}
        if any(path.is_symlink() for path in [args.out, *args.out.parents]):
            raise ValueError('output_symlink')
        args.out.mkdir(parents=True, exist_ok=False, mode=0o700)
        (args.out / 'privacy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        (args.out / 'privacy.md').write_text(markdown(report))
        print(json.dumps({key: report[key] for key in ['mode', 'cases_expected', 'cases_assessed', 'metrics']}))
        if report['cases_assessed'] != report['cases_expected']:
            return 2
        return 1 if any(metric['failed'] for metric in report['metrics'].values()) else 0
    except Exception:
        print(json.dumps({'status': 'failed', 'code': 'privacy_acceptance_input_or_output'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
