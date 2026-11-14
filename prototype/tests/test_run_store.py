import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline
from prototype.run_store import RunStore, StoreError


class RunStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'runs'
        self.store = RunStore(self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def create(self, key='start-1', scenario='success'):
        return self.store.create({'mode':'synthetic-replay','scenario':scenario}, key)

    def complete(self, key='start-1'):
        item, _ = self.create(key)
        rid = item['run_id']
        self.store.start(rid)
        resume, jobs = demo_inputs()
        model = ReplayModel()
        report = asyncio.run(run_pipeline(resume, jobs, model, SyntheticPrivacy()))
        report['mode'] = 'synthetic_replay_NOT_model_output'
        self.store.finish(rid, report, {'resume':resume,'jobs':dict(jobs)})
        return rid, model

    def test_idempotent_start_conflict_and_single_active(self):
        first, created = self.create()
        again, created_again = self.create()
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first['run_id'], again['run_id'])
        with self.assertRaisesRegex(StoreError, 'idempotency_conflict'):
            self.create(scenario='disputed')
        with self.assertRaisesRegex(StoreError, 'busy'):
            self.create(key='other')

    def test_restart_is_interrupted_not_resumed_and_files_are_private(self):
        item, _ = self.create()
        self.store.start(item['run_id'])
        self.store.close()
        self.store = RunStore(self.root)
        state = self.store.get(item['run_id'])
        self.assertEqual(state['state'], 'interrupted')
        self.assertFalse(state['report_available'])
        for path in self.root.rglob('*'):
            if path.is_file():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            elif path.is_dir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_reopen_review_and_export_have_zero_model_calls_and_stale_is_rejected(self):
        rid, model = self.complete()
        report = self.store.report(rid)
        action = {'expected_revision':report['revision'], 'job_id':'job-001',
                  'action':'confirm_requirements', 'item_id':None, 'idempotency_key':'review-1'}
        result = self.store.review(rid, action)
        self.assertEqual(result['report']['ranking']['jobs'][0]['requirements_review']['state'], 'confirmed')
        repeated = self.store.review(rid, action)
        self.assertEqual(repeated['run']['revision'], result['run']['revision'])
        with self.assertRaisesRegex(StoreError, 'stale_revision'):
            self.store.review(rid, {**action, 'idempotency_key':'review-2'})
        report = result['report']
        ready = next(h for h in report['handoff'] if h['job_id'] == 'job-001')
        self.assertTrue(ready['can_mark_for_handoff'])
        final = self.store.review(rid, {**action, 'action':'mark_for_handoff',
            'expected_revision':report['revision'], 'idempotency_key':'review-3'})
        self.assertEqual(final['report']['handoff'][0]['state'], 'reviewed_for_handoff')
        self.assertFalse(final['report']['handoff'][0]['can_mark_for_handoff'])
        self.assertEqual(model.calls, 7)
        self.store.close()
        self.store = RunStore(self.root)
        self.assertEqual(self.store.report(rid)['handoff'][0]['state'], 'reviewed_for_handoff')

    def test_v2_history_remains_reviewed_and_its_decisions_do_not_approve_v3(self):
        from prototype.scoring import score, POLICY_V2, POLICY_VERSION
        from prototype.review_policy import report_sha256, assess_handoff
        with patch('prototype.pipeline.POLICY_VERSION', POLICY_V2), patch(
            'prototype.pipeline.score', side_effect=lambda *args: score(*args, policy=POLICY_V2)
        ):
            rid, model = self.complete(key='legacy-v2')
        for index, action in enumerate(['confirm_requirements', 'mark_for_handoff']):
            before = self.store.report(rid)
            self.store.review(rid, {'expected_revision':before['revision'], 'job_id':'job-001',
                'action':action, 'item_id':None, 'idempotency_key':f'legacy-review-{index}'})
        before = self.store.report(rid)
        self.assertIsNone(before['leader'])
        self.assertEqual(before['handoff'][0]['state'], 'reviewed_for_handoff')
        self.store.close()
        self.store = RunStore(self.root)
        reopened = self.store.report(rid)
        self.assertEqual(reopened['policy_version'], POLICY_V2)
        self.assertEqual(report_sha256(reopened), report_sha256(before))
        self.assertEqual(reopened['ranking'], before['ranking'])
        self.assertEqual(reopened['review_history'], before['review_history'])
        self.assertEqual(reopened['handoff'][0]['state'], 'reviewed_for_handoff')
        self.assertIsNone(reopened['leader'])
        self.assertEqual(model.calls, 7)
        current_id, _ = self.complete(key='current-v3')
        current = self.store.report(current_id)
        self.assertEqual(current['policy_version'], POLICY_VERSION)
        self.assertIsNotNone(current['leader'])
        self.assertNotEqual(current['handoff'][0]['state'], 'reviewed_for_handoff')
        inherited = assess_handoff(current, before['review_history'], 'job-001')
        self.assertEqual(inherited.state, 'stale')
        self.assertIn('stale_policy_version', [reason.code for reason in inherited.reasons])

    def test_forged_action_cannot_override_queue_or_change_model_status(self):
        rid, _ = self.complete()
        original = self.store.report(rid)
        with self.assertRaisesRegex(StoreError, 'action_not_allowed'):
            self.store.review(rid, {'expected_revision':1, 'job_id':'job-002',
                'action':'mark_for_handoff','item_id':None,'idempotency_key':'fake'})
        with self.assertRaisesRegex(StoreError, 'invalid_action'):
            self.store.review(rid, {'expected_revision':1,'job_id':'job-002','action':'confirm_requirements',
                'item_id':None,'idempotency_key':'fake2','requirements_review':{'state':'confirmed'}})
        self.assertEqual(self.store.report(rid), original)

    def test_delete_one_run_preserves_neighbor_and_rejects_active_and_traversal(self):
        a, _ = self.complete()
        b, _ = self.create(key='second')
        with self.assertRaisesRegex(StoreError, 'run_active'):
            self.store.delete(b['run_id'])
        with self.assertRaises(StoreError):
            self.store.get('../outside')
        self.store.delete(a)
        self.assertEqual(self.store.get(b['run_id'])['state'], 'queued')
        with self.assertRaisesRegex(StoreError, 'not_found'):
            self.store.report(a)

    def test_modified_or_symlinked_record_is_never_trusted(self):
        rid, _ = self.complete()
        record = self.root / rid / 'record.json'
        data = json.loads(record.read_text())
        data['record']['report']['verification']['final_allowed'] = True
        record.write_text(json.dumps(data))
        with self.assertRaisesRegex(StoreError, 'store_corrupt'):
            self.store.report(rid)
        record.unlink()
        record.symlink_to(self.root / '.integrity-key')
        with self.assertRaisesRegex(StoreError, 'unsafe_path'):
            self.store.report(rid)

    def test_snapshot_mismatch_cannot_become_review_authority(self):
        item, _ = self.create()
        self.store.start(item['run_id'])
        resume, jobs = demo_inputs()
        report = asyncio.run(run_pipeline(resume, jobs, ReplayModel(), SyntheticPrivacy()))
        with self.assertRaisesRegex(StoreError, 'snapshot_mismatch'):
            self.store.finish(item['run_id'], report, {'resume':resume+'wrong','jobs':dict(jobs)})
        self.assertFalse(self.store.get(item['run_id'])['report_available'])

    def test_display_alias_cannot_be_saved_for_reference_from_outside_snapshot(self):
        item, _ = self.create()
        rid = item['run_id']
        self.store.start(rid)
        resume, jobs = demo_inputs()
        report = asyncio.run(run_pipeline(resume, jobs, ReplayModel(), SyntheticPrivacy()))
        sources = {'resume':resume, 'jobs':dict(jobs)}
        with self.assertRaisesRegex(StoreError, '^invalid_display_aliases$'):
            self.store.finish(rid, report, sources,
                display_aliases={'[[PRIV:0123456789abcdef:1:CONTACT]]':'private@example.test'})
        self.assertFalse(self.store.get(rid)['report_available'])

    def test_catalog_reads_always_see_new_runs(self):
        self.assertEqual(self.store.list(), [])
        first, _ = self.create()
        for _ in range(4):
            self.assertEqual([r['run_id'] for r in self.store.list()], [first['run_id']])

    def test_failed_create_and_interrupted_delete_do_not_poison_store(self):
        with patch.object(self.store, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.create()
        self.assertEqual(self.store.list(), [])
        rid, _ = self.complete()
        with patch.object(self.store, '_remove_directory', side_effect=OSError('interrupted cleanup')):
            with self.assertRaises(OSError):
                self.store.delete(rid)
        self.assertEqual(self.store.list(), [])
        self.store.close()
        self.store = RunStore(self.root)
        self.assertEqual(self.store.list(), [])
        self.assertFalse(any(p.name.startswith(('.creating-', '.deleting-')) for p in self.root.iterdir()))
        self.create(key='after-recovery')

    def test_second_store_cannot_take_ownership(self):
        with self.assertRaisesRegex(StoreError, 'store_in_use'):
            RunStore(self.root)
        self.create()

    def test_oversized_report_is_rejected_before_publication(self):
        item, _ = self.create()
        self.store.start(item['run_id'])
        resume, jobs = demo_inputs()
        report = asyncio.run(run_pipeline(resume, jobs, ReplayModel(), SyntheticPrivacy()))
        with patch('prototype.run_store.MAX_VIEW', 10):
            with self.assertRaisesRegex(StoreError, 'record_too_large'):
                self.store.finish(item['run_id'], report, {'resume':resume, 'jobs':dict(jobs)})
        self.assertFalse(self.store.get(item['run_id'])['report_available'])


if __name__ == '__main__':
    unittest.main()
