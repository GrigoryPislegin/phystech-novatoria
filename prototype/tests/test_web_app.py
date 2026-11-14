import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from prototype.local_service import LocalService
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
        display_route = f'/api/runs/{rid}/display-data'
        status, display, display_headers = self.request('GET',display_route)
        from prototype.demo import demo_inputs
        self.assertEqual((status,display),(200,{'run_id':rid,'revision':1,'aliases':{},
                                                'job_titles':dict(demo_inputs()[1])}))
        self.assertEqual(display_headers['Cache-Control'],'no-store')
        for hostile in ({'Host':'attacker.example'}, {'Origin':'https://attacker.example'},
                        {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('GET',display_route,headers=hostile)[0],403)
        action = {'expected_revision':1,'job_id':'job-001','action':'confirm_requirements',
                  'item_id':None,'idempotency_key':'confirm'}
        status, checked, _ = self.request('POST',f'/api/runs/{rid}/review',action,headers)
        self.assertEqual((status,checked['report']['revision']),(200,2))
        status, _, _ = self.request('POST',f'/api/runs/{rid}/review',{**action,'idempotency_key':'stale'},headers)
        self.assertEqual(status,409)
        self.assertEqual(self.request('DELETE',f'/api/runs/{rid}',{},headers)[0],200)
        self.assertEqual(self.request('GET',f'/api/runs/{rid}/report')[0],404)
        self.assertEqual(self.request('GET',display_route)[0],404)

    def test_static_whitelist_csp_and_no_private_paths(self):
        for path in ('/.env','/../.env','/%2e%2e/.env','/api/runs/../../.env','/data/private'):
            self.assertEqual(self.request('GET',path)[0],404)
        status, content, headers = self.request('GET','/')
        self.assertEqual(status,200)
        self.assertIn(b'<!',content)
        self.assertIn("script-src 'self'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'],'no-store')

    @unittest.skipUnless((Path(os.environ.get('PRIVACY_MODELS_DIR', 'data/private/privacy-models')) /
                          'slovnet_ner_news_v1.tar').is_file(), 'Local NER weights unavailable')
    def test_display_endpoint_only_returns_the_requested_runs_aliases(self):
        headers = {'X-CSRF-Token':self.session['csrf_token']}
        contact = 'ivan.synthetic@example.com.'
        for mode in ('synthetic-protected-mock', 'synthetic-replay'):
            status, created, _ = self.request('POST', '/api/runs',
                {'mode':mode, 'scenario':'success', 'idempotency_key':mode}, headers)
            self.assertEqual(status, 202)
            rid = created['run_id']
            self.assertEqual(self.service.wait(rid)['state'], 'complete')
            _, report, _ = self.request('GET', f'/api/runs/{rid}/report')
            self.assertNotIn(contact, str(report))
            status, display, _ = self.request('GET', f'/api/runs/{rid}/display-data')
            self.assertEqual((status, display['run_id'], display['revision']), (200, rid, report['revision']))
            if mode == 'synthetic-protected-mock':
                self.assertIn(contact, display['aliases'].values())
            else:
                self.assertEqual(display['aliases'], {})


class PublicOriginTests(unittest.TestCase):
    host = 'recruiter.example.test:8443'
    origin = 'https://' + host

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = LocalService(Path(self.tmp.name))
        self.addCleanup(self.service.close)
        self.server = create_server(self.service, port=0, public_origin=self.origin)
        self.addCleanup(self.server.server_close)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, headers, body=None):
        # Write headers separately to exercise duplicate Host/Origin rejection.
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.putrequest(method, path, skip_host=True)
            for name, value in headers:
                connection.putheader(name, value)
            raw = None if body is None else json.dumps(body).encode()
            if raw is not None:
                connection.putheader('Content-Type', 'application/json')
                connection.putheader('Content-Length', str(len(raw)))
            connection.endheaders(raw)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_configured_authority_and_origin_are_required_exactly(self):
        host = ('Host', self.host)
        origin = ('Origin', self.origin)
        forwarded = [('Forwarded', f'proto=https;host={self.host}'),
                     ('X-Forwarded-Host', self.host), ('X-Forwarded-Proto', 'https')]
        for headers in ([], [('Host','localhost')], [('Host','recruiter.example.test')],
                        [('Host','recruiter.example.test:8444')], [host,host],
                        [host,('Origin','http://' + self.host)],
                        [host,('Origin','https://attacker.example')],
                        [host,('Origin','https://recruiter.example.test')],
                        [host,origin,origin], [host,('Sec-Fetch-Site','cross-site')],
                        [('Host','localhost'),origin,*forwarded],
                        [host,('Origin','http://' + self.host),*forwarded]):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET','/api/session',headers), (403, {'error':'origin_rejected'}))
        for headers in ([host], [host,origin]):
            self.assertEqual(self.request('GET','/api/session',headers)[0], 200)
        rid = 'a' * 32
        self.assertEqual(self.request('GET',f'/api/runs/{rid}/display-data',
            [host,('Sec-Fetch-Site','cross-site')])[0], 403)

    def test_configured_origin_still_requires_csrf_for_mutations(self):
        headers = [('Host',self.host), ('Origin',self.origin)]
        _, session = self.request('GET','/api/session',headers)
        token = ('X-CSRF-Token',session['csrf_token'])
        body = {'mode':'synthetic-replay','scenario':'success','idempotency_key':'proxy'}
        status, created = self.request('POST','/api/runs',[*headers,token],body)
        self.assertEqual(status, 202)
        rid = created['run_id']
        self.service.wait(rid)
        base = f'/api/runs/{rid}'
        self.assertEqual(self.request('GET',base+'/report',headers)[0], 200)
        for method, route in (('POST','/api/inputs/inspect'), ('POST','/api/runs'),
                              ('POST',base+'/review'), ('POST',base+'/cancel'), ('DELETE',base)):
            with self.subTest(method=method, route=route):
                self.assertEqual(self.request(method,route,headers,{}), (403, {'error':'csrf_rejected'}))
        self.assertEqual(self.request('DELETE',base,[*headers,token,token],{})[0], 403)
        self.assertEqual(self.request('DELETE',base,[*headers,token],{}), (200, {'deleted':rid}))


class PublicOriginConfigTests(unittest.TestCase):
    def test_invalid_origin_fails_before_binding(self):
        values = ('', 'http://example.test', 'HTTPS://example.test', 'https://*.example.test',
                  'https://user@example.test', 'https://example.test/', 'https://example.test?',
                  'https://example.test#', 'https://example.test:0', 'https://example.test:65536',
                  'https://example.test:', 'https://example.test:08443', 'https://-host.test',
                  'https://a..test', 'https://a_b.test', 'https://[not-ipv6]', 'https://999.1.1.1',
                  ' https://example.test', 'https://exam\nple.test', 'https://example.test\t')
        with patch('prototype.web_app.LocalHTTPServer') as bind:
            for origin in values:
                with self.subTest(origin=origin), self.assertRaisesRegex(StoreError, '^invalid_public_origin$'):
                    create_server(None, public_origin=origin)
            bind.assert_not_called()

    def test_public_origin_does_not_enable_nonloopback_binding(self):
        with patch('prototype.web_app.LocalHTTPServer') as bind:
            with self.assertRaisesRegex(StoreError, '^loopback_required$'):
                create_server(None, host='192.0.2.4', public_origin='https://example.test')
            bind.assert_not_called()


if __name__ == '__main__':
    unittest.main()
