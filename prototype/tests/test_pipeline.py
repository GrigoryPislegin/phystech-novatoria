import asyncio
import tempfile
import unittest
from pathlib import Path
from prototype.documents import read_document
from prototype.model import Budget, Model
from prototype.pipeline import run_pipeline, write_report, literal
from prototype.demo import demo_inputs, ReplayModel


class Deny:
    async def redact(self, text): raise RuntimeError('privacy_unavailable')
    async def check(self, text): raise RuntimeError('privacy_unavailable')


class PassSynthetic:
    async def redact(self, text): return text
    async def check(self, text): pass


class PipelineTests(unittest.TestCase):
    def test_replay_end_to_end(self):
        resume, jobs = demo_inputs()
        report = asyncio.run(run_pipeline(resume, jobs, ReplayModel(), PassSynthetic()))
        self.assertEqual(len(report['ranking']['jobs']), 3)
        self.assertTrue(report['ranking']['complete'])
        self.assertEqual(report['ranking']['jobs'][0]['job_id'], 'job-001')
        with tempfile.TemporaryDirectory() as tmp:
            out = write_report(report, Path(tmp))
            self.assertTrue((out / 'report.json').is_file())
            self.assertIn('requirement', (out / 'requirements.csv').read_text())
            self.assertEqual(report['leader']['state'], report['ranking']['leader']['state'])
            self.assertEqual(report['leader']['policy_version'], report['policy_version'])
            markdown = (out / 'report.md').read_text()
            self.assertIn('обязательная группа — 75', markdown)
            self.assertIn(literal(report['leader']['summary']), markdown)
            self.assertNotIn('обязательное требование — 3', markdown)

    def test_privacy_failure_prevents_model_calls(self):
        model = ReplayModel()
        with self.assertRaises(RuntimeError):
            asyncio.run(run_pipeline(*demo_inputs(), model, Deny()))
        self.assertEqual(model.calls, 0)

    def test_budget_rejected_before_request(self):
        budget = Budget('gpt-6-luna', 0.000001)
        with self.assertRaises(ValueError): budget.reserve(100, 100)
        self.assertEqual(budget.calls, 0)
        budget = Budget('gpt-6-luna', 1, max_calls=1)
        budget.reserve(100, 100)
        with self.assertRaises(ValueError): budget.reserve(100, 100)

    def test_invalid_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.txt'; path.write_text('')
            with self.assertRaises(ValueError): read_document(path)
            path.write_text('Синтетический пример Python')
            self.assertIn('Python', read_document(path))
            path = Path(tmp) / 'bad.exe'; path.write_text('data')
            with self.assertRaises(ValueError): read_document(path)

    def test_partial_failure_is_explicit(self):
        class Broken(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'requirements' and 'SQL' in payload['text']:
                    raise ValueError('invalid_response')
                return await super().ask(schema, task, payload)
        report = asyncio.run(run_pipeline(*demo_inputs(), Broken(), PassSynthetic()))
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(report['ranking']['recommendation'], 'incomplete')
        self.assertTrue(report['errors'])

    def test_markdown_fields_are_literal_even_with_backticks(self):
        hostile = '![x](https://example.test/pixel)<img src="https://example.test">`'
        self.assertEqual(literal(hostile), '`` ' + hostile + ' ``')
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), PassSynthetic()))
        report['facts']['items'][0]['quote'] = hostile
        with tempfile.TemporaryDirectory() as tmp:
            path = write_report(report, Path(tmp)) / 'report.md'
            self.assertIn('Резюме: ' + literal(hostile), path.read_text())


if __name__ == '__main__': unittest.main()
