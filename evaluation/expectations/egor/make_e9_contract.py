"""Generate the E9 contract fixtures from the integrated pipeline: normal, disputed, incomplete.

python evaluation/expectations/egor/make_e9_contract.py
Real `run_pipeline` with synthetic models that answer in the wire DTOs (profile with the facts,
conditions with the rows). The service's run_id is stamped and `refresh_derived` rebuilds the
views, as the run store will. `events` are dropped for determinism. Synthetic texts only.
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

CV = ('Работал с:\n- Python\n\nНе работал с:\n- Python\n\nSQL 2 года.\nРассматриваю только удалённую работу.\n'
      'Ожидания по доходу: от 200 000 рублей в месяц.')
JOBS = [('job-a', 'Обязателен опыт Python.\nSQL желателен.\nРабота в офисе.\nЗарплата: до 250 000 рублей в месяц.'),
        ('job-b', 'Обязательно: Go. Python желателен.')]
FACTS = [Fact(id='f1', text='Python', quote='Python'), Fact(id='f2', text='SQL 2 года', quote='SQL 2 года.'),
         Fact(id='f3', text='Удалённо', quote='Рассматриваю только удалённую работу.'),
         Fact(id='f4', text='Доход', quote='Ожидания по доходу: от 200 000 рублей в месяц.')]
# «Python» is cited from a fact whose quote stands under both «Работал с:» and «Не работал с:».
DISPUTED_PROFILE = {
    'summary': [{'text': 'SQL 2 года', 'sources': [{'fact_id': 'f2', 'quote': 'SQL 2 года.'}]}],
    'stack': [{'text': 'Python', 'sources': [{'fact_id': 'f1', 'quote': 'Python'}]},
              {'text': 'SQL', 'sources': [{'fact_id': 'f2', 'quote': 'SQL'}]}],
    'last_position': None, 'achievements': [], 'missing': ['last_position', 'achievements']}
JOB_A_CONDITIONS = {'items': [
    {'kind': 'work_mode', 'state': 'conflict',
     'cv': {'fact_id': 'f3', 'quote': 'Рассматриваю только удалённую работу.'},
     'vacancy_quote': 'Работа в офисе.', 'note': 'Удалённо против офиса.'},
    {'kind': 'salary', 'state': 'compatible', 'cv': {'fact_id': 'f4', 'quote': 'от 200 000 рублей в месяц'},
     'vacancy_quote': 'до 250 000 рублей в месяц', 'note': 'Ожидание ниже верхней границы.'}]}


class DisputedModel:
    def __init__(self, profile=DISPUTED_PROFILE, job_a_conditions=JOB_A_CONDITIONS):
        self.profile, self.job_a_conditions = profile, job_a_conditions

    async def ask(self, schema, task, payload):
        if task == 'facts':
            return schema.model_validate({'items': [f.model_dump() for f in FACTS], 'profile': self.profile})
        if task == 'requirements':
            text = payload['text']
            if text.startswith('Обязателен опыт Python'):
                return Requirements(items=[
                    Requirement(id='r1', text='Python', quote='Обязателен опыт Python.',
                                mandatory_quote='Обязателен опыт Python.'),
                    Requirement(id='r2', text='SQL', quote='SQL желателен.', mandatory_quote=None)])
            return Requirements(items=[Requirement(id='r1', text='Python', quote='Python', mandatory_quote=text)])
        if len(payload['requirements']['items']) == 2:
            rows = [Row(requirement_id='r1', status='full', fact_ids=['f1'], comment='Python указан.', question=None),
                    Row(requirement_id='r2', status='full', fact_ids=['f2'], comment='SQL указан.', question=None)]
            return schema.model_validate({'rows': [r.model_dump() for r in rows], 'conditions': self.job_a_conditions})
        row = Row(requirement_id='r1', status='fail', fact_ids=['f2'], comment='Нет Python.',
                  question='Есть ли Python?')
        return schema.model_validate({'rows': [row.model_dump()], 'conditions': {'items': []}})


class IncompleteModel(ReplayModel):
    """The demo replay, except that job-002's requirements cite text the vacancy does not contain."""

    async def _answer(self, task, payload):
        if task == 'requirements' and payload['text'].startswith('Java'):
            return Requirements(items=[Requirement(id='r1', text='Java', quote='нет в вакансии', mandatory_quote=None)])
        return await super()._answer(task, payload)


def publish(report, run_id):
    """What the run store does before anyone reads the report."""
    return refresh_derived({**{k: v for k, v in report.items() if k != 'events'}, 'run_id': run_id})


def scenarios():
    resume, jobs = demo_inputs('success')
    return {
        'normal': (publish(asyncio.run(run_pipeline(resume, jobs, ReplayModel(), SyntheticPrivacy())),
                           'run-e9-normal'),
                   'demo success через интегрированный pipeline.'),
        'disputed': (publish(asyncio.run(run_pipeline(CV, JOBS, DisputedModel(), SyntheticPrivacy())),
                             'run-e9-disputed'),
                     'Неоднозначная цитата «Python», маркер обязательности не того требования, конфликт формата, '
                     'зарплата на сверку, профиль needs_review.'),
        'incomplete': (publish(asyncio.run(run_pipeline(resume, jobs, IncompleteModel(), SyntheticPrivacy())),
                               'run-e9-incomplete'),
                       'job-002 не прошла проверку цитат: запуск неполный.'),
    }


def main():
    for name, (report, note) in scenarios().items():
        data = {'schema_version': 'egor-e9-contract-0.2', 'note': note, 'report': report}
        Path(__file__).with_name(f'e9-contract-{name}.json').write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(name, report['ranking']['recommendation'], [h['state'] for h in report['handoff']])


if __name__ == '__main__':
    main()
