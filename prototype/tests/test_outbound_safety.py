"""Actual model boundary, with synthetic values and a local SDK transport only."""
import asyncio
import os
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from prototype.contracts import Fact, Facts
from prototype.model import Budget, Model
from prototype.privacy_core import Finding, LocalPrivacy


class OutboundSafetyTests(unittest.TestCase):
    def make_model(self):
        detector = SimpleNamespace(scan=Mock(return_value=[]))
        privacy = LocalPrivacy(detector)
        privacy.issued_refs.add('[[PRIV:deadbeefdeadbeef:1:PERSON]]')
        model = Model.__new__(Model)
        model.model, model.privacy = 'gpt-6-luna', privacy
        model.budget, model.usage = Budget(model.model), []
        result = SimpleNamespace(status='completed', usage=None, output_parsed=Facts(items=[]))
        model.client = SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(return_value=result)))
        return model, detector

    def test_issued_refs_survive_newline_tab_quote_and_backslash_in_both_directions(self):
        for prefix in ['\n', '\t', '"', '\\']:
            with self.subTest(prefix=repr(prefix)):
                model, detector = self.make_model()
                value = prefix + '[[PRIV:deadbeefdeadbeef:1:PERSON]]'
                model.client.responses.parse.return_value.output_parsed = Facts(
                    items=[Fact(id='f1', text=value, quote=value)])
                result = asyncio.run(model.ask(Facts, 'facts', {'text':value}))
                self.assertEqual(result.items[0].quote, value)
                self.assertEqual(model.budget.calls, 1)

    def test_unissued_refs_in_nested_keys_and_values_stop_before_sdk(self):
        for payload in [{'text':['\n[[PRIV:deadbeefdeadbeef:2:PERSON]]']}, {'[[PRIV:deadbeefdeadbeef:2:PERSON]]':{'text':'Python'}}]:
            model, detector = self.make_model()
            with self.assertRaisesRegex(RuntimeError, 'privacy_untrusted_reference'):
                asyncio.run(model.ask(Facts, 'facts', payload))
            self.assertEqual(model.budget.calls, 0)
            model.client.responses.parse.assert_not_called()

    def test_residual_scan_stops_before_sdk(self):
        model, detector = self.make_model()
        detector.scan.return_value = [Finding(0, 4, 'PERSON')]
        with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
            asyncio.run(model.ask(Facts, 'facts', {'text':'synthetic'}))
        self.assertEqual(model.budget.calls, 0)

    def test_sdk_debug_and_exception_logs_do_not_expose_payload_or_credentials(self):
        # A fresh process also exercises OPENAI_LOG's import-time logging setup.
        script = r'''
import asyncio, logging
from prototype.model import Model
from prototype.contracts import Facts
from prototype.demo import SyntheticPrivacy
import httpx
from openai import AsyncOpenAI
async def main():
    model = Model('gpt-6-luna', SyntheticPrivacy())
    await model.close()
    def respond(request):
        return httpx.Response(400, json={'error':{'message':'RESPONSE_CANARY_78', 'type':'invalid_request_error'}}, request=request)
    model.client = AsyncOpenAI(api_key='FAKE_KEY_CANARY_31', max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        await model.ask(Facts, 'facts', {'text':'PAYLOAD_CANARY_57'})
    except Exception:
        pass
    finally:
        await model.close()
    try:
        raise ValueError('DSN_CANARY_42')
    except ValueError:
        for name in ('certum_core.synthetic_late_logger', 'presidio-analyzer.synthetic', 'httpx2.synthetic'):
            logging.getLogger(name).exception('CORE_CANARY_93')
    print('completed_synthetic_transport')
asyncio.run(main())
'''
        env = {**os.environ, 'OPENAI_LOG':'debug', 'OPENAI_API_KEY':'FAKE_KEY_CANARY_31'}
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, 'synthetic subprocess failed')
        output = result.stdout + result.stderr
        self.assertIn('completed_synthetic_transport', output)
        for secret in ['PAYLOAD_CANARY_57','RESPONSE_CANARY_78','FAKE_KEY_CANARY_31','DSN_CANARY_42','CORE_CANARY_93']:
            self.assertFalse(secret in output, 'dependency logging leaked a synthetic canary')
