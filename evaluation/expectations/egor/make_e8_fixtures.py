"""Generate the E8 review-queue fixtures from the real pipeline with a synthetic model.

python evaluation/expectations/egor/make_e8_fixtures.py
Writes e8-queue-normal.json and e8-queue-disputed.json next to this file. Synthetic texts only;
`events` (timings) are dropped so the files are deterministic. Uses the integrated wire DTOs
(profile with the facts, conditions with the rows).
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row  # noqa: E402
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs  # noqa: E402
from prototype.pipeline import refresh_derived, run_pipeline  # noqa: E402
from prototype.review_queue import build_review_queue  # noqa: E402

CV = 'Работал с:\n- Python\n\nНе работал с:\n- Python\n\nSQL 2 года.\nРассматриваю только удалённую работу.'
JOBS = [
    ('job-a', 'Обязателен опыт Python.\nSQL желателен.\nРабота в офисе.'),
    ('job-b', 'Обязательно: Go. Python желателен.'),
    ('job-c', 'Rust обязателен.'),
    ('job-d', 'Kotlin обязателен.'),
]


EMPTY_PROFILE = {'summary': [], 'stack': [], 'last_position': None, 'achievements': [],
                 'missing': ['summary', 'stack', 'last_position', 'achievements']}
WORK_MODE_CONFLICT = {'items': [{'kind': 'work_mode', 'state': 'conflict',
                                 'cv': {'fact_id': 'f3', 'quote': 'Рассматриваю только удалённую работу.'},
                                 'vacancy_quote': 'Работа в офисе.', 'note': 'Удалённо против офиса.'}]}


class DisputedModel:
    """Each vacancy carries one kind of signal; job-d fails validation and stays unprocessed.
    Answers use the integrated wire DTOs: the profile comes with the facts, conditions with the rows."""

    async def ask(self, schema, task, payload):
        answer = (await self._answer(task, payload)).model_dump()
        if 'profile' in schema.model_fields:
            answer['profile'] = EMPTY_PROFILE
        if 'conditions' in schema.model_fields:
            first = payload['requirements']['items'][0]['quote']
            answer['conditions'] = WORK_MODE_CONFLICT if first == 'Обязателен опыт Python.' else {'items': []}
        return schema.model_validate(answer)

    async def _answer(self, task, payload):
        if task == 'facts':
            return Facts(items=[Fact(id='f1', text='Python', quote='Python'),
                                Fact(id='f2', text='SQL 2 года', quote='SQL 2 года.'),
                                Fact(id='f3', text='Удалённо', quote='Рассматриваю только удалённую работу.')])
        if task == 'requirements':
            text = payload['text']
            if text.startswith('Обязателен опыт Python'):
                return Requirements(items=[
                    Requirement(id='r1', text='Python', quote='Обязателен опыт Python.',
                                mandatory_quote='Обязателен опыт Python.'),
                    Requirement(id='r2', text='SQL', quote='SQL желателен.', mandatory_quote=None)])
            if text.startswith('Обязательно: Go'):  # marker bound to the wrong requirement
                return Requirements(items=[Requirement(id='r1', text='Python', quote='Python', mandatory_quote=text)])
            if text.startswith('Rust'):
                return Requirements(items=[Requirement(id='r1', text='Rust', quote=text, mandatory_quote=text)])
            return Requirements(items=[Requirement(id='r1', text='Kotlin', quote='не из вакансии',
                                                   mandatory_quote=None)])
        ids = [r['id'] for r in payload['requirements']['items']]
        first = payload['requirements']['items'][0]['text']
        if ids == ['r1', 'r2']:
            return Evaluation(rows=[
                Row(requirement_id='r1', status='full', fact_ids=['f1'], comment='Python указан.', question=None),
                Row(requirement_id='r2', status='full', fact_ids=['f2'], comment='SQL указан.', question=None)])
        if first == 'Python':
            return Evaluation(rows=[Row(requirement_id='r1', status='fail', fact_ids=['f2'], comment='Нет Python.',
                                        question='Есть ли опыт Python?')])
        return Evaluation(rows=[Row(requirement_id='r1', status='unknown', fact_ids=[], comment='Rust не указан.',
                                    question='Есть ли опыт Rust?')])


def expected(queue):
    return [{k: getattr(i, k) for k in ('job_id', 'requirement_id', 'condition_kind', 'reason_code', 'priority',
                                         'action')}
            for i in queue.items]


def save(name, report, note):
    # The service stamps run_id on every published report; derived views are rebuilt after that.
    report = refresh_derived({**{k: v for k, v in report.items() if k != 'events'},
                              'run_id': f"run-{name.split('.')[0].removeprefix('e8-queue-')}"})
    queue = build_review_queue(report)
    data = {'schema_version': 'egor-e8-fixture-0.1', 'note': note, 'report': report, 'expected': expected(queue),
            'by_priority': queue.by_priority}
    Path(__file__).with_name(name).write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(name, queue.by_priority)


def main():
    normal = asyncio.run(run_pipeline(*demo_inputs('success'), ReplayModel(), SyntheticPrivacy()))
    save('e8-queue-normal.json', normal,
         'demo success: обычный отчёт. Срочных пунктов нет, кроме проверенного fail по обязательному SQL.')
    disputed = asyncio.run(run_pipeline(CV, JOBS, DisputedModel(), SyntheticPrivacy()))
    disputed['privacy'] = {'professional_information_may_be_hidden': True}  # as application.analyze adds it
    save('e8-queue-disputed.json', disputed,
         'Спорный отчёт: «Работал/Не работал с Python», маркер обязательности не того требования, '
         'Rust без сведений при защите данных, необработанная вакансия, конфликт формата работы.')


if __name__ == '__main__':
    main()
