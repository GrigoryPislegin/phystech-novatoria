import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prototype.__main__ import execute
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline, write_report


class RuntimeSafetyTests(unittest.TestCase):
    def test_metadata_cannot_replace_computed_verification(self):
        from prototype.application import analyze
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'invalid_metadata'):
                asyncio.run(analyze(*demo_inputs(), model_factory=ReplayModel, privacy=SyntheticPrivacy(),
                    out=Path(tmp), mode='synthetic_replay_NOT_model_output', metadata={'verification':{'final_allowed':True}}))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_cli_rejects_too_many_files_before_parsing_any_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jobs = root/'jobs'; jobs.mkdir()
            for i in range(21): (jobs/f'{i}.txt').write_text('synthetic')
            cv = root/'cv.txt'; cv.write_text('synthetic')
            args = SimpleNamespace(command='run', resume=cv, jobs=jobs, out=root/'out')
            with patch('prototype.__main__.read_document', side_effect=AssertionError('parsed before preflight')):
                with self.assertRaisesRegex(ValueError, 'invalid_job_set'):
                    asyncio.run(execute(args))

    def test_symlink_job_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); jobs = root/'jobs'; jobs.mkdir()
            cv = root/'cv.txt'; cv.write_text('synthetic')
            (jobs/'link.txt').symlink_to(cv)
            args = SimpleNamespace(command='run', resume=cv, jobs=jobs, out=root/'out')
            with patch('prototype.__main__.read_document', side_effect=AssertionError('parsed before preflight')):
                with self.assertRaisesRegex(ValueError, 'input_symlink'):
                    asyncio.run(execute(args))

    def test_bad_output_prevents_model_initialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'file'; out.write_text('occupied')
            args = SimpleNamespace(command='demo', scenario='success', live=False, out=out)
            with patch('prototype.__main__.ReplayModel', side_effect=AssertionError('model before output preflight')):
                with self.assertRaisesRegex(ValueError, 'output_unavailable'):
                    asyncio.run(execute(args))

    def test_failed_csv_export_leaves_no_visible_or_staging_report(self):
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        with tempfile.TemporaryDirectory() as tmp:
            with patch('prototype.pipeline.csv.writer', side_effect=OSError('synthetic disk full')):
                with self.assertRaises(OSError): write_report(report, Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_local_validation_failure_continues_remaining_jobs(self):
        class InvalidSecond(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'requirements' and 'Java' in payload['text']:
                    result.items[0].quote = 'NOT_IN_SOURCE'
                return result
        report = asyncio.run(run_pipeline(*demo_inputs(), InvalidSecond(), SyntheticPrivacy()))
        self.assertEqual([j['job_id'] for j in report['ranking']['jobs']], ['job-001','job-003'])
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(report['unprocessed_job_ids'], ['job-002'])
        self.assertEqual(report['errors'][0]['code'], 'model_invalid')

    def test_fatal_error_stops_calls_and_preserves_successful_prefix(self):
        class FatalSecond(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'requirements' and 'Java' in payload['text']:
                    raise RuntimeError('privacy_untrusted_reference')
                return await super().ask(schema, task, payload)
        model = FatalSecond()
        report = asyncio.run(run_pipeline(*demo_inputs(), model, SyntheticPrivacy()))
        self.assertEqual(model.calls, 3)
        self.assertEqual(report['unprocessed_job_ids'], ['job-002','job-003'])
        self.assertEqual(report['unprocessed'][1]['reason'], 'stopped_after_error')

    def test_deadline_preserves_results_and_progress_contains_no_document_text(self):
        from prototype.pipeline import RunControl
        class SlowSecond(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'requirements' and 'Java' in payload['text']:
                    await asyncio.sleep(1)
                return await super().ask(schema, task, payload)
        events=[]
        control = RunControl(timeout_seconds=0.03, progress=events.append)
        report = asyncio.run(run_pipeline(*demo_inputs(), SlowSecond(), SyntheticPrivacy(), control=control))
        self.assertEqual(len(report['ranking']['jobs']), 1)
        self.assertEqual(report['errors'][0]['code'], 'deadline_exceeded')
        self.assertNotIn('Python', json.dumps(events))

    def test_cancel_at_second_job_does_not_start_second_request(self):
        from prototype.pipeline import RunControl
        control = RunControl()
        def progress(event):
            if event['stage']=='requirements' and event['job_id']=='job-002': control.cancel()
        control.progress = progress
        model = ReplayModel()
        report = asyncio.run(run_pipeline(*demo_inputs(), model, SyntheticPrivacy(), control=control))
        self.assertEqual(model.calls, 3)
        self.assertEqual(report['errors'][0]['code'], 'cancelled')

    def test_budget_stop_has_distinct_reason(self):
        from prototype.errors import BudgetLimit
        class Limited(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'requirements' and 'Java' in payload['text']:
                    raise BudgetLimit('budget_or_call_limit')
                return await super().ask(schema, task, payload)
        report = asyncio.run(run_pipeline(*demo_inputs(), Limited(), SyntheticPrivacy()))
        self.assertEqual(report['errors'][0]['code'], 'budget_limit')
        self.assertEqual(len(report['ranking']['jobs']), 1)

    def test_content_ids_survive_rename_and_manifest_remains_local(self):
        from prototype.application import load_documents, analyze
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root/'jobs'; folder.mkdir()
            resume, jobs = demo_inputs()
            cv = root/'cv-secret-filename.txt'; cv.write_text(resume)
            job = folder/'secret-job-name.txt'; job.write_text(jobs[0][1])
            _, first, manifest = load_documents(cv, folder)
            job.rename(folder/'renamed.txt')
            _, second, _ = load_documents(cv, folder)
            self.assertEqual(first[0][0], second[0][0])
            result = asyncio.run(analyze(resume, first, model_factory=ReplayModel,
                privacy=SyntheticPrivacy(), out=root/'out', mode='synthetic_replay_NOT_model_output', manifest=manifest))
            self.assertEqual(result.exit_code, 0)
            self.assertNotIn('secret-', (result.path/'report.json').read_text())
            self.assertIn('secret-job-name.txt', (result.path/'inputs.manifest.json').read_text())
            self.assertEqual(result.path.stat().st_mode & 0o777, 0o700)
            self.assertEqual((result.path/'inputs.manifest.json').stat().st_mode & 0o777, 0o600)
