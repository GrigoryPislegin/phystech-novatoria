import asyncio
import tempfile
import unittest
from pathlib import Path

from prototype.contracts import Requirement, Requirements, Facts, Fact
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline, write_report


class ReviewFixTests(unittest.TestCase):
    def test_mandatory_quote_must_include_own_requirement(self):
        for quote in ['Python обязателен.', 'л']:
            reqs = Requirements(items=[Requirement(id='r1', text='SQL', quote='SQL желателен.', mandatory_quote=quote)])
            with self.assertRaises(ValueError):
                reqs.validate_source('Python обязателен. SQL желателен.')

    def test_shared_mandatory_span_is_allowed(self):
        source = 'Python и SQL обязательны.'
        Requirements(items=[Requirement(id=str(i), text=skill, quote=skill, mandatory_quote=source)
                            for i, skill in enumerate(['Python', 'SQL'])]).validate_source(source)

    def test_mandatory_quote_requires_context_even_when_it_contains_requirement(self):
        reqs = Requirements(items=[Requirement(id='r1', text='SQL', quote='SQL', mandatory_quote='SQL')])
        with self.assertRaisesRegex(ValueError, 'unbound_mandatory_quote'):
            reqs.validate_source('SQL')

    def test_identical_requirements_do_not_double_weight(self):
        reqs = Requirements(items=[Requirement(id=str(i), text='Python', quote='Python обязателен.',
                                               mandatory_quote='Python обязателен.') for i in range(2)])
        with self.assertRaises(ValueError):
            reqs.validate_source('Python обязателен.')

    def test_bad_facts_yield_empty_incomplete_report_without_leaking(self):
        class Broken(ReplayModel):
            async def ask(self, schema, task, payload):
                self.calls += 1
                return Facts(items=[Fact(id='f1', text='private-value', quote='fabricated-private-quote')])
        model = Broken()
        report = asyncio.run(run_pipeline(*demo_inputs(), model, SyntheticPrivacy()))
        self.assertEqual(model.calls, 1)
        self.assertEqual(report['facts']['items'], [])
        self.assertEqual(report['ranking']['recommendation'], 'incomplete')
        self.assertEqual(report['errors'][0]['stage'], 'facts_validation')
        self.assertEqual(len(report['unprocessed_job_ids']), 3)
        with tempfile.TemporaryDirectory() as tmp:
            out = write_report(report, Path(tmp))
            self.assertNotIn('private', (out / 'report.json').read_text())
            self.assertIn('facts_validation', (out / 'report.md').read_text())

    def test_requirement_error_has_stage_and_stops_calls(self):
        class Broken(ReplayModel):
            def __init__(self):
                super().__init__()
                self.tasks = []
            async def ask(self, schema, task, payload):
                self.tasks.append(task)
                if task == 'requirements':
                    raise RuntimeError('private-message')
                return await super().ask(schema, task, payload)
        model = Broken()
        report = asyncio.run(run_pipeline(*demo_inputs(), model, SyntheticPrivacy(), max_concurrency=1))
        self.assertEqual(model.tasks, ['facts', 'requirements'])
        self.assertEqual(report['errors'][0]['stage'], 'requirements')
        self.assertEqual(report['errors'][0]['code'], 'requirements_failed')
        self.assertEqual(report['ranking']['jobs'], [])

    def test_report_names_top_requirements_and_mandatory_evidence(self):
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        with tempfile.TemporaryDirectory() as tmp:
            md = (write_report(report, Path(tmp)) / 'report.md').read_text()
        self.assertIn('job-001', md.split('\n## ')[0])
        self.assertIn('Обязательность предложена моделью', md)
        self.assertIn('Сильные стороны: ` Python `, ` SQL `', md)
        self.assertNotIn('Сильные стороны: строки full', md)

    def test_clarify_without_unknown_does_not_invent_missing_information(self):
        class AllFail(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'requirements':
                    for req in result.items:
                        req.mandatory_quote = None
                if task == 'evaluation':
                    for row in result.rows:
                        row.status, row.fact_ids, row.question = 'fail', ['f1'], 'Проверить факт?'
                return result
        report = asyncio.run(run_pipeline(*demo_inputs(), AllFail(), SyntheticPrivacy()))
        self.assertEqual(report['ranking']['recommendation'], 'clarify')
        with tempfile.TemporaryDirectory() as tmp:
            md = (write_report(report, Path(tmp)) / 'report.md').read_text()
        self.assertIn('Подтверждённого соответствия недостаточно', md)
        self.assertNotIn('Сначала уточните неизвестные', md)


if __name__ == '__main__':
    unittest.main()
