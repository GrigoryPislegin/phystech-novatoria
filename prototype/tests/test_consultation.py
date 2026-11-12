import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prototype.demo import demo_inputs, ReplayModel, SyntheticPrivacy
from prototype.pipeline import run_pipeline, write_report


class ConsultationTests(unittest.TestCase):
    def test_disputed_cli_retains_partial_unknown_and_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, '-m', 'prototype', 'demo',
                                     '--scenario', 'disputed', '--out', tmp],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(next(Path(tmp).glob('*/report.json')).read_text())
            self.assertEqual(report['mode'], 'synthetic_replay_NOT_model_output')
            self.assertEqual(report['ranking']['recommendation'], 'clarify')
            jobs = report['ranking']['jobs']
            self.assertEqual([j['job_id'] for j in jobs], ['job-001', 'job-002', 'job-003'])
            self.assertEqual(jobs[0]['score']['lower'], 50)
            self.assertEqual({r['status'] for j in jobs for r in j['evaluation']['rows']},
                             {'partial', 'unknown', 'fail'})

    def test_report_explains_order_and_statuses(self):
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        with tempfile.TemporaryDirectory() as tmp:
            md = (write_report(report, Path(tmp)) / 'report.md').read_text()
            self.assertIn('Обработано вакансий: 3/3', md)
            self.assertIn('Порядок вакансий:', md)
            self.assertIn('partial — частичное соответствие', md)
            self.assertIn('unknown — информация не указана', md)
            self.assertIn('При одинаковом L в одной группе по нарушению обязательных требований вакансии делят место', md)

    def test_failed_second_job_keeps_first_and_names_remaining(self):
        class Broken(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'requirements' and 'Java' in payload['text']:
                    raise ValueError('not for report')
                return await super().ask(schema, task, payload)
        report = asyncio.run(run_pipeline(*demo_inputs(), Broken(), SyntheticPrivacy()))
        self.assertEqual(len(report['ranking']['jobs']), 1)
        self.assertEqual(report['ranking']['recommendation'], 'incomplete')
        with tempfile.TemporaryDirectory() as tmp:
            md = (write_report(report, Path(tmp)) / 'report.md').read_text()
            self.assertIn('Обработано вакансий: 1/3', md)
            self.assertIn('Рейтинг неполный', md)
            self.assertIn('job-002', md)
            self.assertIn('job-003', md)
            self.assertNotIn('not for report', md)
