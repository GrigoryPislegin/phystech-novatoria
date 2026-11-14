"""Real local HTTP/store, synthetic analysis only; no credentials or model network."""
import asyncio
import base64
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from prototype.application import analyze
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.local_service import LocalService
from prototype.public_demo import COOKIE, PublicDemo
from prototype.run_store import StoreError
from prototype.web_app import create_server


def synthetic_execute(service, rid, request, inputs, control):
    sources = {}
    service.store.start(rid)
    with tempfile.TemporaryDirectory() as directory:
        result = asyncio.run(analyze(*inputs, model_factory=ReplayModel, privacy=SyntheticPrivacy(),
            out=Path(directory), mode='synthetic_public_demo_test', source_sink=sources.update))
    result.report['reserved_usd_estimate'] = '0.10'
    service.store.finish(rid, result.report, sources)


def inputs():
    resume, jobs = demo_inputs()
    file = lambda text:{'name':'example.txt','content_base64':base64.b64encode(text.encode()).decode()}
    return {'resume':file(resume), 'jobs':[file(text) for _,text in jobs]}


class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(LocalService, '_execute', synthetic_execute)
        self.patch.start()
        self.demo = PublicDemo(Path(self.tmp.name) / 'public', '.15')

    def tearDown(self):
        self.demo.close()
        self.patch.stop()
        self.tmp.cleanup()

    def request(self, visitor, key='one'):
        checked = self.demo.inspect(visitor, inputs())
        return {'mode':'protected-live','input_id':checked['input_id'],'budget':1,'idempotency_key':key}

    def test_bootstrap_is_stateless_cookie_is_signed_and_cached_uploads_are_globally_bounded(self):
        for _ in range(100):
            visitor, issued = self.demo.visitor(None, create=True)
            self.assertTrue(issued)
        self.assertEqual(self.demo.visitors, {})
        self.assertFalse(any(path.is_dir() for path in self.demo.root.iterdir()))
        cookie = self.demo.cookie(visitor)
        with self.assertRaisesRegex(StoreError, 'session_required'):
            self.demo.visitor(cookie[:-1] + ('1' if cookie[-1] != '1' else '2'))
        restored, issued = self.demo.visitor(cookie)
        self.assertFalse(issued)
        self.assertEqual(restored.csrf, visitor.csrf)
        for _ in range(12):
            person, _ = self.demo.visitor(None, create=True)
            self.demo.inspect(person, inputs())
        self.assertLessEqual(sum(len(v.service._inputs) for v in self.demo.visitors.values()), 8)

    def test_budget_survives_restart_deletion_and_crash_between_dispatch_and_binding(self):
        visitor, _ = self.demo.visitor(None, create=True)
        cookie = self.demo.cookie(visitor)
        request = self.request(visitor)
        created = self.demo.create(visitor, request)
        self.demo.service(visitor).wait(created['run_id'])
        self.assertEqual(self.demo.create(visitor, request)['run_id'], created['run_id'])
        self.assertEqual(len(self.demo.entries), 1)
        # Reproduce the persisted state of a crash after LocalService.create.
        self.demo.entries[0]['run_id'] = None
        self.demo.entries[0]['settled'] = False
        self.demo.entries[0]['amount'] = '0.15'
        self.demo.close()
        self.demo = PublicDemo(Path(self.tmp.name) / 'public', '.15')
        visitor, _ = self.demo.visitor(cookie)
        self.assertEqual(self.demo.create(visitor, request)['run_id'], created['run_id'])
        self.assertEqual(self.demo.entries[0]['amount'], '0.10')
        self.demo.before_delete()
        self.demo.service(visitor).store.delete(created['run_id'])
        # The deleted run still counts. Remaining budget is reserved before the next dispatch.
        with patch.object(LocalService, '_execute', lambda *args:None):
            new = self.demo.create(visitor, self.request(visitor, 'two'))
            self.assertEqual(self.demo.entries[-1]['amount'], '0.05')
            self.demo.service(visitor).store.fail(new['run_id'], 'interrupted')
        with self.assertRaisesRegex(StoreError, 'demo_budget_exhausted'):
            self.demo.create(visitor, self.request(visitor, 'three'))

    def test_global_busy_and_cross_visitor_input_rejection_do_not_double_spend(self):
        a, _ = self.demo.visitor(None, create=True)
        b, _ = self.demo.visitor(None, create=True)
        request = self.request(a)
        with self.assertRaisesRegex(StoreError, 'input_not_found'):
            self.demo.create(b, request)
        self.assertEqual(self.demo.entries, [])
        with patch.object(LocalService, '_execute', lambda *args:None):
            created = self.demo.create(a, request)
            with self.assertRaisesRegex(StoreError, 'busy'):
                self.demo.create(b, self.request(b))
            self.assertEqual(len(self.demo.entries), 1)
            self.demo.service(a).store.fail(created['run_id'], 'interrupted')


class PublicDemoHTTPTests(unittest.TestCase):
    def test_passwordless_cookie_and_every_run_route_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(LocalService, '_execute', synthetic_execute):
            service = LocalService(Path(directory), allow_live=True)
            old, _ = service.store.create({'mode':'synthetic-replay'}, 'private-owner-history')
            server = create_server(service, port=0, public_origin='https://demo.example', anonymous_demo_budget=5)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, path, body=None, cookie=None, csrf=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                headers = {'Host':'demo.example','Content-Type':'application/json'}
                if cookie: headers['Cookie'] = cookie
                if csrf: headers.update({'Origin':'https://demo.example','X-CSRF-Token':csrf})
                connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
                response = connection.getresponse()
                raw = response.read()
                result = response.status, raw, dict(response.getheaders())
                connection.close()
                return result
            try:
                self.assertEqual(request('GET','/')[0], 200)
                sessions = []
                for _ in range(2):
                    status, raw, headers = request('GET','/api/session')
                    self.assertEqual(status, 200)
                    self.assertNotIn('WWW-Authenticate', headers)
                    cookie = headers['Set-Cookie']
                    for flag in ('Secure','HttpOnly','SameSite=Lax','Path=/'): self.assertIn(flag, cookie)
                    sessions.append((cookie.split(';')[0], json.loads(raw)['csrf_token']))
                (a, ac), (b, bc) = sessions
                self.assertNotEqual(ac, bc)
                # A slow body must not hold the registry mutex or block another browser.
                import socket, time
                deadline_patch = patch('prototype.web_app.BODY_SECONDS', .3)
                deadline_patch.start()
                slow = socket.create_connection(('127.0.0.1', server.server_port))
                slow.sendall(('POST /api/inputs/inspect HTTP/1.1\r\nHost: demo.example\r\n'
                              'Content-Type: application/json\r\nContent-Length: 1000\r\n'
                              f'Cookie: {a}\r\nX-CSRF-Token: {ac}\r\n\r\n{{').encode())
                try:
                    time.sleep(.05)
                    self.assertEqual(request('GET','/api/session',cookie=b)[0],200)
                    self.assertEqual(request('POST','/api/inputs/inspect',inputs(),b,bc)[0],409)
                    # Even a still-open upload releases the slot at the total deadline.
                    slow.settimeout(2)
                    self.assertIn(b'400', slow.recv(4096).split(b'\r\n', 1)[0])
                finally:
                    deadline_patch.stop()
                    slow.close()
                for _ in range(100):
                    if server.public_demo.inspect_gate.acquire(blocking=False):
                        server.public_demo.inspect_gate.release()
                        break
                    time.sleep(.01)
                self.assertEqual(json.loads(request('GET','/api/runs',cookie=a)[1]), {'runs':[]})
                self.assertEqual(request('GET', '/api/runs/' + old['run_id'], cookie=a)[0], 404)
                self.assertEqual(request('POST','/api/inputs/inspect',inputs(),a,bc)[0],403)
                status, raw, _ = request('POST','/api/inputs/inspect',inputs(),a,ac)
                self.assertEqual(status,200)
                body = {'mode':'protected-live','input_id':json.loads(raw)['input_id'],'budget':1,'idempotency_key':'one'}
                status, raw, _ = request('POST','/api/runs',body,a,ac)
                self.assertEqual(status,202)
                rid = json.loads(raw)['run_id']
                visitor, _ = server.public_demo.visitor(a.split('=',1)[1])
                server.public_demo.service(visitor).wait(rid)
                self.assertEqual(request('GET',f'/api/runs/{rid}/report',cookie=a)[0],200)
                for method, suffix, payload in [('GET','',None),('GET','/report',None),('GET','/display-data',None),
                                               ('POST','/cancel',{}),('POST','/review',{}),('DELETE','',{})]:
                    self.assertEqual(request(method, f'/api/runs/{rid}{suffix}',payload,b,bc)[0],404)
                self.assertEqual(json.loads(request('GET','/api/runs',cookie=b)[1]), {'runs':[]})
            finally:
                server.shutdown(); server.server_close(); thread.join()
                server.public_demo.close(); service.close()
