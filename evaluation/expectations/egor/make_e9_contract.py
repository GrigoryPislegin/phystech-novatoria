"""Generate the E9 integration-contract fixtures: normal, disputed and incomplete runs.

python evaluation/expectations/egor/make_e9_contract.py
Each file holds the wired report (policy v2 scores, E5 profile and conditions) and what the views
derive from it (E7 comparisons of adjacent places, E8 queue, E8 handoff state without decisions).
Real pipeline with synthetic models; `events` dropped for determinism. Synthetic texts only.
"""
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row  # noqa: E402
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs  # noqa: E402
from prototype.pipeline import run_pipeline  # noqa: E402
from prototype.tests.e9_wiring import derived, wire  # noqa: E402

NORMAL_PROFILE = {
    'summary': [{'text': 'Python 3 года', 'sources': [{'fact_id': 'f1', 'quote': 'Разрабатывал на Python 3 года.'}]}],
    'stack': [{'text': 'Python', 'sources': [{'fact_id': 'f1', 'quote': 'Python'}]},
              {'text': 'SQL', 'sources': [{'fact_id': 'f2', 'quote': 'SQL'}]}],
    'last_position': None, 'achievements': [], 'missing': ['last_position', 'achievements']}

CV = ('Работал с:\n- Python\n\nНе работал с:\n- Python\n\nSQL 2 года.\nРассматриваю только удалённую работу.\n'
      'Ожидания по доходу: от 200 000 рублей в месяц.')
JOBS = [('job-a', 'Обязателен опыт Python.\nSQL желателен.\nРабота в офисе.\nЗарплата: до 250 000 рублей в месяц.'),
        ('job-b', 'Обязательно: Go. Python желателен.')]
DISPUTED_PROFILE = {
    'summary': [{'text': 'SQL 5 лет', 'sources': [{'fact_id': 'f2', 'quote': 'SQL 2 года.'}]}],  # invented number
    'stack': [{'text': 'SQL', 'sources': [{'fact_id': 'f2', 'quote': 'SQL'}]}],
    'last_position': None, 'achievements': [], 'missing': ['last_position', 'achievements']}
DISPUTED_CONDITIONS = {'job-a': {'items': [
    {'kind': 'work_mode', 'state': 'conflict',
     'cv': {'fact_id': 'f3', 'quote': 'Рассматриваю только удалённую работу.'},
     'vacancy_quote': 'Работа в офисе.', 'note': 'Удалённо против офиса.'},
    {'kind': 'salary', 'state': 'compatible', 'cv': {'fact_id': 'f4', 'quote': 'от 200 000 рублей в месяц'},
     'vacancy_quote': 'до 250 000 рублей в месяц', 'note': 'Ожидание ниже верхней границы.'}]}}


class DisputedModel:
    async def ask(self, schema, task, payload):
        if task == 'facts':
            return Facts(items=[Fact(id='f1', text='Python', quote='Python'),
                                Fact(id='f2', text='SQL 2 года', quote='SQL 2 года.'),
                                Fact(id='f3', text='Удалённо', quote='Рассматриваю только удалённую работу.'),
                                Fact(id='f4', text='Доход', quote='Ожидания по доходу: от 200 000 рублей в месяц.')])
        if task == 'requirements':
            text = payload['text']
            if text.startswith('Обязателен опыт Python'):
                return Requirements(items=[
                    Requirement(id='r1', text='Python', quote='Обязателен опыт Python.',
                                mandatory_quote='Обязателен опыт Python.'),
                    Requirement(id='r2', text='SQL', quote='SQL желателен.', mandatory_quote=None)])
            return Requirements(items=[Requirement(id='r1', text='Python', quote='Python', mandatory_quote=text)])
        if len(payload['requirements']['items']) == 2:
            return Evaluation(rows=[
                Row(requirement_id='r1', status='full', fact_ids=['f1'], comment='Python указан.', question=None),
                Row(requirement_id='r2', status='full', fact_ids=['f2'], comment='SQL указан.', question=None)])
        return Evaluation(rows=[Row(requirement_id='r1', status='fail', fact_ids=['f2'], comment='Нет Python.',
                                    question='Есть ли опыт Python?')])


class IncompleteModel(ReplayModel):
    """The demo replay, except that job-002's requirements cite text the vacancy does not contain."""

    async def ask(self, schema, task, payload):
        if task == 'requirements' and payload['text'].startswith('Java'):
            return Requirements(items=[Requirement(id='r1', text='Java', quote='нет в вакансии', mandatory_quote=None)])
        return await super().ask(schema, task, payload)


def save(name, report, resume, jobs, profile, conditions, note):
    report = {k: v for k, v in report.items() if k != 'events'}
    wired = wire(report, resume, dict(jobs), profile, conditions, run_id=f'run-e9-{name}')
    data = {'schema_version': 'egor-e9-contract-0.1', 'note': note, 'report': wired, 'derived': derived(wired)}
    Path(__file__).with_name(f'e9-contract-{name}.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(name, wired['ranking']['recommendation'], data['derived']['handoff'])


def main():
    resume, jobs = demo_inputs('success')
    normal = asyncio.run(run_pipeline(resume, jobs, ReplayModel(), SyntheticPrivacy()))
    save('normal', normal, resume, jobs, NORMAL_PROFILE, {'job-001': {'items': []}},
         'demo success, подключённый по контракту: профиль без замечаний, условий нет.')
    disputed = asyncio.run(run_pipeline(CV, JOBS, DisputedModel(), SyntheticPrivacy()))
    save('disputed', disputed, CV, JOBS, DISPUTED_PROFILE, DISPUTED_CONDITIONS,
         'Неоднозначная цитата, маркер обязательности не того требования, конфликт формата, '
         'зарплата на сверку, придуманное число в профиле.')
    incomplete = asyncio.run(run_pipeline(resume, jobs, IncompleteModel(), SyntheticPrivacy()))
    save('incomplete', incomplete, resume, jobs, NORMAL_PROFILE, {},
         'job-002 не прошла проверку цитат: запуск неполный, итог только предварительный.')


if __name__ == '__main__':
    main()
