import base64
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from prototype.local_service import LocalService, UPLOAD_MOCK
from prototype.run_store import StoreError
from prototype.web_app import create_server


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = LocalService(Path(self.tmp.name))
        self.server = create_server(self.service, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        _, self.session, _ = self.request('GET','/api/session')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.service.close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        supplied = {'Content-Type':'application/json', **(headers or {})}
        encoded = None if body is None else json.dumps(body).encode()
        connection.request(method,path,body=encoded,headers=supplied)
        response = connection.getresponse()
        raw = response.read()
        content = json.loads(raw) if response.getheader('Content-Type','').startswith('application/json') else raw
        result = response.status, content, dict(response.getheaders())
        connection.close()
        return result

    def test_mutation_requires_same_origin_and_session_token(self):
        body = {'mode':'synthetic-replay','scenario':'success','idempotency_key':'one'}
        self.assertEqual(self.request('POST','/api/runs',body)[0],403)
        self.assertEqual(self.request('POST','/api/runs',body,{
            'X-CSRF-Token':self.session['csrf_token'],'Origin':'https://attacker.example'})[0],403)
        self.assertEqual(self.request('GET','/api/session',headers={'Host':'attacker.example'})[0],403)
        self.assertEqual(self.request('POST','/api/runs',body,{'X-CSRF-Token':'é'})[1]['error'],'csrf_rejected')
        with self.assertRaisesRegex(StoreError, 'loopback_required'):
            create_server(self.service, '192.0.2.1', 0)
        self.assertEqual(self.service.store.list(), [])

    def test_request_over_25_mb_is_rejected_before_reading_or_inspection(self):
        headers = {'Content-Length':'25000001', 'X-CSRF-Token':self.session['csrf_token']}
        with patch.object(self.service, 'inspect') as inspect:
            status, response, _ = self.request('POST','/api/inputs/inspect',headers=headers)
            self.assertEqual((status, response), (413, {'error':'input_too_large'}))
            inspect.assert_not_called()

    def test_start_read_review_and_delete_actual_service(self):
        headers = {'X-CSRF-Token':self.session['csrf_token']}
        status, created, _ = self.request('POST','/api/runs',
            {'mode':'synthetic-replay','scenario':'success','idempotency_key':'one'},headers)
        self.assertEqual(status,202)
        rid = created['run_id']
        self.service.wait(rid)
        status, report, _ = self.request('GET',f'/api/runs/{rid}/report')
        self.assertEqual((status,report['revision']),(200,1))
        action = {'expected_revision':1,'job_id':'job-001','action':'confirm_requirements',
                  'item_id':None,'idempotency_key':'confirm'}
        status, checked, _ = self.request('POST',f'/api/runs/{rid}/review',action,headers)
        self.assertEqual((status,checked['report']['revision']),(200,2))
        status, _, _ = self.request('POST',f'/api/runs/{rid}/review',{**action,'idempotency_key':'stale'},headers)
        self.assertEqual(status,409)
        self.assertEqual(self.request('DELETE',f'/api/runs/{rid}',{},headers)[0],200)
        self.assertEqual(self.request('GET',f'/api/runs/{rid}/report')[0],404)

    def test_static_whitelist_csp_and_no_private_paths(self):
        for path in ('/.env','/../.env','/%2e%2e/.env','/api/runs/../../.env','/data/private'):
            self.assertEqual(self.request('GET',path)[0],404)
        status, content, headers = self.request('GET','/')
        self.assertEqual(status,200)
        self.assertIn(b'<!',content)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'],'no-store')

    def test_compare_two_non_leaders_in_the_same_run_without_writes(self):
        run = self.service.create({'mode':'synthetic-replay','scenario':'disputed','idempotency_key':'compare'})
        rid = run['run_id']
        self.service.wait(rid)
        base = self.service.store.report(rid)
        left, right = [j['job_id'] for j in base['ranking']['jobs'][1:]]
        path = f'/api/runs/{rid}/report?' + urlencode({'a':left,'b':right})
        status, payload, _ = self.request('GET',path)
        self.assertEqual((status, payload['revision'], payload['run_id']), (200, 1, rid))
        self.assertEqual((payload['comparison']['job_a'],payload['comparison']['job_b']), (left,right))
        self.assertEqual(self.service.store.report(rid), base)
        for bad in (path.replace(rid, '0' * 32), path.replace(left, 'other-run-vacancy')):
            self.assertEqual(self.request('GET',bad)[0],404)
        self.assertEqual(self.request('GET', path + '&a=repeat')[0], 400)

    @unittest.skipUnless((Path(os.environ.get('PRIVACY_MODELS_DIR', 'data/private/privacy-models')) /
                          'slovnet_ner_news_v1.tar').is_file(), 'Local NER weights unavailable')
    def test_docx_upload_runs_real_local_ner_and_sdk_mock_over_http(self):
        from io import BytesIO
        from docx import Document
        from prototype.demo import demo_inputs

        def entry(name, raw):
            return {'name':name,'content_base64':base64.b64encode(raw).decode()}

        resume, jobs = demo_inputs('disputed')
        doc, stream = Document(), BytesIO()
        doc.add_paragraph(resume)
        doc.save(stream)
        headers = {'X-CSRF-Token':self.session['csrf_token']}
        inputs = {'resume':entry('candidate.docx',stream.getvalue()),
                  'jobs':[entry('job.txt',text.encode()) for _,text in jobs]}
        status, checked, _ = self.request('POST','/api/inputs/inspect',inputs,headers)
        self.assertEqual(status, 200)
        self.assertEqual(checked['mock_scenario'], 'disputed')
        request = {'mode':UPLOAD_MOCK,'input_id':checked['input_id'],'idempotency_key':'uploaded'}
        status, created, _ = self.request('POST','/api/runs',request,headers)
        self.assertEqual(status, 202)
        rid = created['run_id']
        self.assertEqual(self.service.wait(rid, 30)['state'], 'complete')
        status, report, _ = self.request('GET',f'/api/runs/{rid}/report')
        self.assertEqual((status, report['mode'], report['openai_network_calls']),
                         (200, 'synthetic_sdk_mock_NOT_model_output', 0))
        self.assertEqual(report['ranking']['recommendation'], 'clarify')
        self.assertNotIn('candidate.docx', str(report))
        self.assertEqual(self.request('POST','/api/runs',request,headers)[1]['run_id'], rid)


if __name__ == '__main__':
    unittest.main()
