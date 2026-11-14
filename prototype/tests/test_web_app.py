import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from prototype.local_service import LocalService
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
        self.assertEqual(self.service.store.list(), [])

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


if __name__ == '__main__':
    unittest.main()
