import asyncio
import csv
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
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
            for i in range(31): (jobs/f'{i}.txt').write_text('synthetic')
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

    def test_local_exports_restore_before_escaping_and_keep_machine_report_protected(self):
        ref = '[[PRIV:0123456789abcdef:1:ORG]]'
        original = '=HYPERLINK("https://example.test", "`<img src=x>`")'
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        report = json.loads(json.dumps(report).replace('Python', ref))
        before = json.dumps(report, sort_keys=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = write_report(report, Path(tmp), display_aliases={ref:original})
            self.assertEqual(json.loads((out/'report.json').read_text()), report)
            self.assertNotIn(original, (out/'report.json').read_text())
            markdown = (out/'report.md').read_text()
            self.assertNotIn(ref, markdown)
            self.assertIn('`` ' + original + ' обязателен. ``', markdown)
            with (out/'requirements.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            restored = [row['job_quote'] for row in rows if original in row['job_quote']]
            self.assertTrue(restored)
            self.assertTrue(all(value.startswith("'=") for value in restored))
            for name in ('report.json', 'report.md', 'requirements.csv'):
                self.assertEqual((out/name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.dumps(report, sort_keys=True), before)

    def test_legacy_exports_use_stable_neutral_labels_without_guessing_originals(self):
        ref = '[[PRIV:0123456789abcdef:1:PERSON]]'
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        report = json.loads(json.dumps(report).replace('Python', ref))
        with tempfile.TemporaryDirectory() as tmp:
            out = write_report(report, Path(tmp))
            for name in ('report.md', 'requirements.csv'):
                text = (out/name).read_text()
                self.assertNotIn('[[PRIV:', text)
                self.assertIn('Фрагмент 1', text)
                self.assertNotIn('Человек 1', text)
            self.assertIn(ref, (out/'report.json').read_text())

    def test_protected_application_restores_after_privacy_session_is_closed(self):
        from prototype.application import analyze_protected
        ref = '[[PRIV:0123456789abcdef:1:ORG]]'
        aliases = {ref:'Python'}
        closed = []

        class MaskSynthetic(SyntheticPrivacy):
            async def redact(self, text):
                return text.replace('Python', ref)

            def export_display_aliases(self):
                return aliases.copy()

        @asynccontextmanager
        async def privacy_context():
            try:
                yield MaskSynthetic()
            finally:
                aliases.clear()
                closed.append(True)

        class MaskedReplay(ReplayModel):
            async def ask(self, schema, task, payload):
                source = json.loads(json.dumps(payload).replace(ref, 'Python'))
                answer = await super().ask(schema, task, source)
                return schema.model_validate_json(answer.model_dump_json().replace('Python', ref))

        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(analyze_protected(*demo_inputs(), privacy_context=privacy_context,
                model_factory=lambda privacy:MaskedReplay(), out=Path(tmp), mode='synthetic_test'))
            self.assertTrue(closed)
            self.assertFalse(aliases)
            self.assertEqual(result.display_aliases, {ref:'Python'})
            self.assertIn('Python', (result.path/'report.md').read_text())
            self.assertNotIn(ref, (result.path/'report.md').read_text())
            self.assertNotIn('Python', (result.path/'report.json').read_text())

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

    def test_cross_thread_cancel_interrupts_pending_request_and_preserves_completed_job(self):
        from prototype.pipeline import RunControl

        async def scenario():
            started, never = asyncio.Event(), asyncio.Event()
            cleaned = []

            class PendingSecond(ReplayModel):
                async def ask(self, schema, task, payload):
                    if task == 'requirements' and 'Java' in payload['text']:
                        started.set()
                        try:
                            await never.wait()
                        finally:
                            cleaned.append(True)
                    return await super().ask(schema, task, payload)

            model, control = PendingSecond(), RunControl()
            analysis = asyncio.create_task(run_pipeline(*demo_inputs(), model, SyntheticPrivacy(), control=control))
            await asyncio.wait_for(started.wait(), timeout=1)
            await asyncio.to_thread(control.cancel)
            report = await asyncio.wait_for(analysis, timeout=1)
            self.assertTrue(cleaned, 'the pending request must finish its cancellation cleanup')
            self.assertEqual(model.calls, 3)
            self.assertEqual([j['job_id'] for j in report['ranking']['jobs']], ['job-001'])
            self.assertEqual(report['errors'][0]['code'], 'cancelled')
            self.assertEqual(report['unprocessed_job_ids'], ['job-002', 'job-003'])
            self.assertFalse(control._pending)

        asyncio.run(scenario())

    def _cancel_during_cleanup(self, trigger):
        from prototype.pipeline import RunControl
        from prototype.errors import RunStopped

        async def scenario():
            started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
            finished = []
            control = RunControl(timeout_seconds=0.05 if trigger == 'deadline' else 300)

            async def operation():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release.wait()
                    finished.append(True)

            call = asyncio.create_task(control.call(operation, 'test'))
            await started.wait()
            await asyncio.to_thread(control.cancel)
            await asyncio.wait_for(cleaning.wait(), timeout=1)
            if trigger == 'repeat':
                await asyncio.to_thread(control.cancel)
            elif trigger == 'deadline':
                await asyncio.sleep(0.06)
                self.assertFalse(call.done(), 'deadline must not interrupt cancellation cleanup')
            else:
                call.cancel()
                if trigger == 'caller_twice':
                    await asyncio.sleep(0)
                    call.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(call.done(), 'caller must wait for cleanup after repeated cancellation')
            release.set()
            expected = asyncio.CancelledError if trigger.startswith('caller') else RunStopped
            with self.assertRaises(expected) as caught:
                await asyncio.wait_for(call, timeout=1)
            if not trigger.startswith('caller'):
                self.assertEqual(caught.exception.code, 'cancelled')
            self.assertTrue(finished)
            self.assertFalse(control._pending)

        asyncio.run(scenario())

    def test_repeated_cancel_does_not_interrupt_async_cleanup(self):
        self._cancel_during_cleanup('repeat')

    def test_deadline_during_cancel_cleanup_keeps_first_reason(self):
        self._cancel_during_cleanup('deadline')

    def test_caller_cancellation_is_not_converted_to_a_partial_report(self):
        self._cancel_during_cleanup('caller')

    def test_repeated_caller_cancellation_waits_for_operation_cleanup(self):
        self._cancel_during_cleanup('caller_twice')

    def test_cancel_before_deadline_wins_even_when_loop_notification_is_delayed(self):
        from prototype.pipeline import RunControl
        from prototype.errors import RunStopped

        async def scenario():
            control = RunControl(timeout_seconds=0.03)
            started, cleaned = asyncio.Event(), []

            async def operation():
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.append(True)

            call = asyncio.create_task(control.call(operation, 'test'))
            await started.wait()
            loop = asyncio.get_running_loop()
            with patch.object(loop, 'call_soon_threadsafe'):
                control.cancel()  # Record the request; deliberately delay delivery to the loop.
            with self.assertRaises(RunStopped) as caught:
                await asyncio.wait_for(call, timeout=1)
            self.assertEqual(caught.exception.code, 'cancelled')
            self.assertTrue(cleaned)

        asyncio.run(scenario())

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
