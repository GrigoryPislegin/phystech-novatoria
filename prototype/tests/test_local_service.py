import base64
import copy
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from prototype.local_service import LocalService, SyntheticSDKModel, UPLOAD_MOCK
from prototype.demo import demo_inputs
from prototype.run_store import StoreError


class LocalServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = LocalService(Path(self.tmp.name))

    def tearDown(self):
        self.service.close()
        self.tmp.cleanup()

    def test_demo_runs_and_reopens_from_authoritative_store(self):
        run = self.service.create({'mode':'synthetic-replay','scenario':'success','idempotency_key':'one'})
        finished = self.service.wait(run['run_id'])
        self.assertEqual(finished['state'], 'complete')
        report = self.service.store.report(run['run_id'])
        self.assertEqual(len(report['ranking']['jobs']), 3)
        self.assertEqual(report['revision'], 1)
        self.assertEqual(report['mode'], 'synthetic_replay_NOT_model_output')
        again = self.service.create({'mode':'synthetic-replay','scenario':'success','idempotency_key':'one'})
        self.assertEqual(run['run_id'], again['run_id'])

    def test_incomplete_run_preserves_success_and_cannot_be_handed_off(self):
        run = self.service.create({'mode':'synthetic-replay','scenario':'incomplete','idempotency_key':'partial'})
        self.assertEqual(self.service.wait(run['run_id'])['state'], 'partial')
        report = self.service.store.report(run['run_id'])
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(report['unprocessed_job_ids'], ['job-002'])
        self.assertTrue(all(not h['can_mark_for_handoff'] for h in report['handoff']))

    def test_inspect_is_local_and_live_disabled_rejects_before_any_model(self):
        def file(name, text):
            return {'name':name,'content_base64':base64.b64encode(text.encode()).decode()}
        inspected = self.service.inspect({'resume':file('private-name.txt','Python 3 года.'),
            'jobs':[file('job.md','Python обязателен.')]})
        self.assertTrue(inspected['ready'])
        self.assertNotIn('private-name', str(inspected))
        self.assertTrue(all(f['status']=='ok' for f in inspected['files']))
        with self.assertRaisesRegex(StoreError, 'live_disabled'):
            self.service.create({'mode':'protected-live','input_id':inspected['input_id'],
                'budget':1,'idempotency_key':'no-live'})
        self.assertEqual(self.service.store.list(), [])

    def test_invalid_document_and_path_are_reported_without_storing_usable_input(self):
        def file(name, raw):
            return {'name':name,'content_base64':base64.b64encode(raw).decode()}
        bad = self.service.inspect({'resume':file('cv.pdf',b'not-a-pdf'),
                                  'jobs':[file('job.txt','Python'.encode())]})
        self.assertFalse(bad['ready'])
        self.assertIsNone(bad['input_id'])
        self.assertEqual(bad['files'][0]['status'], 'error')
        with self.assertRaisesRegex(StoreError, 'input_invalid'):
            self.service.inspect({'resume':file('../cv.txt',b'x'),'jobs':[file('job.txt',b'x')]})
        inspected = self.service.inspect({'resume':file('cv.rtf',b'x'),'jobs':[file('job.txt',b'x')]})
        self.assertEqual([f['status'] for f in inspected['files']], ['error', 'ok'])
        self.assertEqual(inspected['files'][0]['error'], 'input_unsupported')

    def test_replay_cannot_accept_user_documents_or_a_forged_mode(self):
        for request in ({'mode':'synthetic-replay','scenario':'success','input_id':'x','idempotency_key':'a'},
                        {'mode':'unsafe-live','scenario':'success','idempotency_key':'b'}):
            with self.assertRaises(StoreError):
                self.service.create(request)
        self.assertEqual(self.service.store.list(), [])

    def test_inspection_never_writes_raw_uploads_and_repeated_inspection_does_not_lock_ui(self):
        def file(name, text):
            return {'name':name,'content_base64':base64.b64encode(text.encode()).decode()}
        payload = {'resume':file('cv.txt','Python 3 года.'),'jobs':[file('job.txt','Python обязателен.')]}
        with patch('prototype.local_service.tempfile.TemporaryDirectory', side_effect=AssertionError('raw disk write')):
            for _ in range(22):
                self.assertTrue(self.service.inspect(payload)['ready'])
        self.assertFalse(self.service._inputs)

    def test_invalid_scenario_type_is_a_client_error(self):
        for value in ([], {}, None, True):
            with self.assertRaisesRegex(StoreError, 'invalid_request'):
                self.service.create({'mode':'synthetic-replay','scenario':value,'idempotency_key':'bad'})

    def test_live_request_is_idempotent_after_consumption_and_restart_without_any_api(self):
        self.service.allow_live = True
        file = lambda name:{'name':name,'content_base64':base64.b64encode(b'Python').decode()}
        inspected = self.service.inspect({'resume':file('cv.txt'),'jobs':[file('job.txt')]})
        request = {'mode':'protected-live','input_id':inspected['input_id'],'budget':1,'idempotency_key':'live-test'}
        with patch.object(self.service, '_execute', side_effect=lambda rid,*args:self.service.store.fail(rid,'synthetic_test')) as call:
            first = self.service.create(request)
            self.service.wait(first['run_id'])
            self.assertFalse(self.service._inputs)
            self.assertEqual(self.service.create(request)['run_id'], first['run_id'])
            self.assertEqual(call.call_count, 1)
        self.service.close()
        self.service = LocalService(Path(self.tmp.name), allow_live=True)
        self.assertEqual(self.service.create(request)['run_id'], first['run_id'])

    def test_simultaneous_uploaded_start_reuses_the_first_run(self):
        resume, jobs = demo_inputs('disputed')
        def file(text):
            return {'name': 'synthetic.txt', 'content_base64': base64.b64encode(text.encode()).decode()}
        inspected = self.service.inspect({'resume':file(resume), 'jobs':[file(text) for _, text in reversed(jobs)]})
        self.assertEqual(inspected['mock_scenario'], 'disputed')
        request = {'mode':UPLOAD_MOCK, 'input_id':inspected['input_id'], 'idempotency_key':'same-upload'}
        arrived = threading.Barrier(2)
        def start():
            arrived.wait(timeout=5)
            return self.service.create(request)['run_id']
        with patch.object(self.service, '_execute', side_effect=lambda rid,*args:self.service.store.fail(rid,'synthetic_test')) as calls:
            with ThreadPoolExecutor(2) as pool:
                first, second = list(pool.map(lambda _: start(), range(2)))
            self.service.wait(first)
            self.assertEqual(first, second)
            self.assertEqual(calls.call_count, 1)
            with self.assertRaisesRegex(StoreError, 'input_not_found'):
                self.service.create({**request, 'idempotency_key':'another-key'})
        self.assertEqual(len(self.service.store.list()), 1)

    def test_uploaded_mock_requires_the_known_synthetic_documents(self):
        self.service.allow_live = True
        sample, jobs = demo_inputs()
        def file(text):
            return {'name': 'synthetic.txt', 'content_base64': base64.b64encode(text.encode()).decode()}
        inspected = self.service.inspect({'resume':file(sample + ' Дополнительный факт.'),
                                          'jobs':[file(text) for _, text in jobs]})
        self.assertIsNone(inspected['mock_scenario'])
        with self.assertRaisesRegex(StoreError, 'mock_requires_demo_documents'):
            self.service.create({'mode':UPLOAD_MOCK, 'input_id':inspected['input_id'], 'idempotency_key':'rejected'})
        self.assertFalse(self.service.store.list())

    def test_cancel_status_persists_until_worker_stops(self):
        entered, release = threading.Event(), threading.Event()
        def execute(rid, request, inputs, control):
            self.service.store.start(rid)
            entered.set()
            release.wait(timeout=5)
            self.service.store.fail(rid, 'cancelled' if control.cancelled else 'synthetic_test')
        with patch.object(self.service, '_execute', side_effect=execute):
            run = self.service.create({'mode':'synthetic-replay','scenario':'success','idempotency_key':'cancel-test'})
            rid = run['run_id']
            try:
                self.assertTrue(entered.wait(timeout=5))
                self.assertTrue(self.service.cancel(rid)['cancel_requested'])
                self.assertTrue(self.service.store.list()[0]['cancel_requested'])
            finally:
                release.set()
            self.assertEqual(self.service.wait(rid)['state'], 'cancelled')

    @unittest.skipUnless((Path(os.environ.get('PRIVACY_MODELS_DIR', 'data/private/privacy-models')) /
                          'slovnet_ner_news_v1.tar').is_file(), 'Local NER weights unavailable')
    def test_protected_mock_matrix_keeps_privacy_and_partial_recovery(self):
        for scenario, expected in (('success',3), ('disputed',3), ('incomplete',2)):
            with self.subTest(scenario=scenario):
                run = self.service.create({'mode':'synthetic-protected-mock','scenario':scenario,'idempotency_key':scenario})
                completed = self.service.wait(run['run_id'], 90)
                self.assertEqual(completed['processed'], expected)
                report = self.service.store.report(run['run_id'])
                self.assertEqual(report['openai_network_calls'], 0)
                self.assertEqual(report['mode'], 'synthetic_sdk_mock_NOT_model_output')
                self.assertEqual(completed['state'], 'partial' if scenario == 'incomplete' else 'complete')
                self.assertNotIn('ivan.synthetic@example.com', str(report))

    @unittest.skipUnless((Path(os.environ.get('PRIVACY_MODELS_DIR', 'data/private/privacy-models')) /
                          'slovnet_ner_news_v1.tar').is_file(), 'Local NER weights unavailable')
    def test_uploaded_synthetic_files_reach_protected_pipeline_and_review_without_network(self):
        # Exercise the upload branch with real parsing/NER/SDK and a local
        # transport injected ONLY by this test. This is not evidence of live API.
        self.service.allow_live = True
        resume, jobs = demo_inputs()
        contact = 'upload.synthetic@example.com'
        file = lambda name,text:{'name':name,'content_base64':base64.b64encode(text.encode()).decode()}
        uploaded = self.service.inspect({'resume':file('synthetic-candidate.txt', 'Email: '+contact+'\n'+resume),
            'jobs':[file('synthetic-vacancy-'+str(i)+'.md',text) for i,(_,text) in enumerate(jobs)]})
        outgoing = []
        class CapturingSDK(SyntheticSDKModel):
            async def ask(self, schema, task, payload):
                outgoing.append(copy.deepcopy(payload))
                return await super().ask(schema, task, payload)
        with patch('prototype.local_service.Model', side_effect=lambda model,p,b:CapturingSDK(p,'success')) as factory, \
             patch('socket.socket.connect', side_effect=AssertionError('network forbidden in this test')):
            run = self.service.create({'mode':'protected-live','input_id':uploaded['input_id'],
                                       'budget':1,'idempotency_key':'uploaded-synthetic'})
            self.assertEqual(self.service.wait(run['run_id'],90)['state'], 'complete')
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(len(outgoing), 7)
            self.assertNotIn(contact, str(outgoing))
            self.assertNotIn('synthetic-candidate.txt', str(outgoing))
            self.assertFalse(self.service._inputs)
            report = self.service.store.report(run['run_id'])
            self.assertTrue(all(j['job_id'] not in {'job-001','job-002','job-003'} for j in report['ranking']['jobs']))
            self.assertNotIn(contact, str(report))
            jid = report['ranking']['jobs'][0]['job_id']
            for action in ('confirm_requirements','mark_for_handoff'):
                changed = self.service.store.review(run['run_id'], {'expected_revision':report['revision'],
                    'job_id':jid,'action':action,'item_id':None,'idempotency_key':action})
                report = changed['report']
            self.assertEqual(report['handoff'][0]['state'], 'reviewed_for_handoff')
            self.assertEqual(len(outgoing), 7, 'HR decisions must not call the model')
            for path in self.service.root.rglob('*'):
                if path.is_file():
                    self.assertNotIn(contact.encode(), path.read_bytes())


if __name__ == '__main__':
    unittest.main()
