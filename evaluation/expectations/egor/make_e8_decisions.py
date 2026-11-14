"""Generate e8-decisions.json: recruiter decisions on the E8 queue fixtures and the expected assessment.

python evaluation/expectations/egor/make_e8_decisions.py   (after make_e8_fixtures.py)
Decisions carry the versions of the fixture reports, as the service would record them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from prototype.review_policy import assess_handoff, current_versions  # noqa: E402
from prototype.review_queue import build_review_queue  # noqa: E402

HERE = Path(__file__).parent


def load(name):
    return json.loads((HERE / f'e8-queue-{name}.json').read_text(encoding='utf-8'))['report']


def scenario(name, report_name, job_id, steps, note):
    report = load(report_name)
    job = next(j for j in report['ranking']['jobs'] if j['job_id'] == job_id)
    queue = [i for i in build_review_queue(report).items if i.job_id in (job_id, None)]
    decisions = []
    for n, (action, reason) in enumerate(steps, 1):
        item = next(i.id for i in queue if i.reason_code == reason) if reason else None
        decisions.append({'decision_id': f'{name}-{n}', 'job_id': job_id, 'item_id': item, 'action': action,
                          **current_versions(report, job), 'decided_by': 'recruiter', 'recorded_by': 'service',
                          'decided_at': f'2026-11-14T01:{n:02d}:00+03:00'})
    result = assess_handoff(report, decisions, job_id)
    expected = {k: v for k, v in result.model_dump().items() if k != 'reasons'}
    expected['reason_codes'] = sorted({i.code for i in result.reasons})
    return {'scenario': name, 'note': note, 'report': f'e8-queue-{report_name}.json', 'job_id': job_id,
            'decisions': decisions, 'expected': expected}


def main():
    scenarios = [
        scenario('normal-ready', 'normal', 'job-001',
                 [('confirm_requirements', None), ('mark_for_handoff', None)],
                 'Список подтверждён, сигналов нет, передача отмечена → reviewed_for_handoff.'),
        scenario('normal-open-unknown', 'normal', 'job-002',
                 [('confirm_requirements', None), ('mark_for_handoff', None)],
                 'Неизвестное обязательное не прочитано → draft, отметка передачи не помогает.'),
        scenario('normal-unknown-read', 'normal', 'job-002',
                 [('confirm_requirements', None), ('read_context', 'mandatory_unknown'), ('mark_for_handoff', None)],
                 'Неизвестное обязательное прочитано → передача возможна, статус остаётся unknown.'),
        scenario('disputed-blocked', 'disputed', 'job-a',
                 [('confirm_requirements', None), ('read_context', 'ambiguous_location'),
                  ('accept_condition', 'condition_conflict'), ('read_context', 'privacy_may_hide'),
                  ('mark_for_handoff', None)],
                 'Неоднозначная цитата и неполный запуск не закрываются кликом → blocked; конфликт принят и виден.'),
    ]
    out = {'schema_version': 'egor-e8-decisions-0.1', 'scenarios': scenarios}
    (HERE / 'e8-decisions.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for s in scenarios:
        print(s['scenario'], s['expected']['state'], s['expected']['reason_codes'])


if __name__ == '__main__':
    main()
