import base64
import json
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
from pathlib import Path

from prototype.local_service import LocalService, SyntheticSDKModel
from prototype.demo import SyntheticPrivacy, demo_inputs
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

    def test_thirty_uploaded_vacancies_complete_or_report_an_explicit_gap(self):
        self.service.allow_live = True
        resume, jobs = demo_inputs()

        def file(name, text):
            return {'name':name, 'content_base64':base64.b64encode(text.encode()).decode()}

        vacancies = [file(f'job-{i}.txt', jobs[1 if i == 21 else 0][1]) for i in range(1, 31)]
        payload = {'resume':file('resume.txt', resume), 'jobs':vacancies}
        self.assertEqual(self.service.capabilities['max_files'], 31)
        with patch('prototype.local_service.read_document_bytes') as parse:
            with self.assertRaisesRegex(StoreError, '^invalid_job_set$'):
                self.service.inspect({**payload, 'jobs':[*vacancies, vacancies[0]]})
            parse.assert_not_called()
        self.assertFalse(self.service._inputs)

        @asynccontextmanager
        async def fixture_privacy():
            # Only the fixed fictional texts above use this substitute. The
            # tests below cover NER separately; this tests count and recovery.
            yield SyntheticPrivacy()

        for scenario, skipped in (('success', []), ('incomplete', [21])):
            with self.subTest(scenario=scenario):
                models = []

                def make_model(_model, privacy, _budget):
                    model = SyntheticSDKModel(privacy, scenario)
                    models.append(model)
                    return model

                inspected = self.service.inspect(payload)
                self.assertTrue(inspected['ready'])
                self.assertEqual(len(inspected['files']), 31)
                self.assertTrue(all(f['status'] == 'ok' for f in inspected['files']))
                with patch('prototype.local_service.local_privacy', fixture_privacy), \
                     patch('prototype.local_service.Model', side_effect=make_model), \
                     patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
                    run = self.service.create({'mode':'protected-live', 'input_id':inspected['input_id'],
                        'budget':1, 'idempotency_key':f'batch-{scenario}'})
                    summary = self.service.wait(run['run_id'])
                self.assertFalse(self.service._inputs)
                self.assertEqual(summary['total'], 30)
                self.assertEqual(summary['processed'], 30 - len(skipped))
                self.assertEqual(summary['state'], 'partial' if skipped else 'complete')
                self.assertEqual([model.budget.calls for model in models], [61])
                report = self.service.store.report(run['run_id'])
                self.assertEqual(report['ranking']['complete'], not skipped)
                batch_index = lambda jid: int(jid.rsplit('-', 1)[1])
                expected = [i for i in range(1, 31) if i not in skipped]
                self.assertEqual(sorted(batch_index(job['job_id']) for job in report['ranking']['jobs']), expected)
                self.assertEqual([batch_index(e['job_id']) for e in report['events'] if e['stage']=='job_finished'], expected)
                self.assertEqual([batch_index(jid) for jid in report['unprocessed_job_ids']], skipped)
                if skipped:
                    self.assertEqual([item['reason'] for item in report['unprocessed']], ['model_invalid'])
                    self.assertFalse(any(item['can_mark_for_handoff'] for item in report['handoff']))

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
        from httpx import MockTransport
        resume, jobs = demo_inputs()
        contacts = ('Upload.Synthetic@example.com', 'upload.synthetic@example.com')
        file = lambda name,text:{'name':name,'content_base64':base64.b64encode(text.encode()).decode()}
        cv = '\n'.join([*(f'Email: {contact}' for contact in contacts), resume])
        uploaded = self.service.inspect({'resume':file('synthetic-candidate.txt', cv),
            'jobs':[file('synthetic-vacancy-'+str(i)+'.md',text) for i,(_,text) in enumerate(jobs)]})
        outgoing, privacy_sessions = [], []
        send_mock = MockTransport.handle_async_request

        async def capture_request(transport, request):
            body = json.loads(request.content)
            outgoing.append(json.loads(body['input'][1]['content'])['data'])
            return await send_mock(transport, request)

        def make_model(_model, privacy, _budget):
            privacy_sessions.append(privacy)
            return SyntheticSDKModel(privacy, 'success')

        with patch('prototype.local_service.Model', side_effect=make_model) as factory, \
             patch.object(MockTransport, 'handle_async_request', capture_request), \
             patch('socket.socket.connect', side_effect=AssertionError('network forbidden in this test')):
            run = self.service.create({'mode':'protected-live','input_id':uploaded['input_id'],
                                       'budget':1,'idempotency_key':'uploaded-synthetic'})
            self.assertEqual(self.service.wait(run['run_id'],90)['state'], 'complete')
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(len(outgoing), 7)
            for contact in contacts:
                self.assertNotIn(contact, str(outgoing))
            self.assertNotIn('synthetic-candidate.txt', str(outgoing))
            self.assertFalse(self.service._inputs)
            report = self.service.store.report(run['run_id'])
            self.assertTrue(all(j['job_id'] not in {'job-001','job-002','job-003'} for j in report['ranking']['jobs']))
            for contact in contacts:
                self.assertNotIn(contact, str(report))
            rid = run['run_id']
            aliases = self.service.store.display_data(rid)['aliases']
            facts_input = outgoing[0]['text']
            refs = {value:ref for ref,value in aliases.items()}
            self.assertLess(facts_input.index(refs[contacts[0]]), facts_input.index(refs[contacts[1]]))
            self.assertTrue(privacy_sessions[0].closed)
            self.assertEqual(privacy_sessions[0]._display_aliases, {})
            jid = report['ranking']['jobs'][0]['job_id']
            for action in ('confirm_requirements','mark_for_handoff'):
                changed = self.service.store.review(run['run_id'], {'expected_revision':report['revision'],
                    'job_id':jid,'action':action,'item_id':None,'idempotency_key':action})
                report = changed['report']
            self.assertEqual(report['handoff'][0]['state'], 'reviewed_for_handoff')
            self.assertEqual(len(outgoing), 7, 'HR decisions must not call the model')
            self.assertNotIn('display_aliases', report)
            record_path = self.service.root / 'runs' / rid / 'record.json'
            self.assertEqual(record_path.stat().st_mode & 0o777, 0o600)
            record = json.loads(record_path.read_text())['record']
            self.assertEqual(record.pop('display_aliases'), aliases)
            for contact in contacts:
                self.assertNotIn(contact, str(record))
            self.service.close()
            self.service = LocalService(Path(self.tmp.name), allow_live=True)
            self.assertEqual(self.service.store.display_data(rid), {
                'run_id':rid, 'revision':report['revision'], 'aliases':aliases})
            self.service.store.delete(rid)
            with self.assertRaisesRegex(StoreError, 'not_found'):
                self.service.store.display_data(rid)


if __name__ == '__main__':
    unittest.main()
