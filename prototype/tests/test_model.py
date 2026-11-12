import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from prototype.contracts import Facts
from prototype.model import Model, Budget


class ModelBoundaryTests(unittest.TestCase):
    def model(self, check):
        model = Model.__new__(Model)
        model.model = 'gpt-6-luna'; model.privacy = SimpleNamespace(check=check)
        model.budget = Budget(model.model); model.usage = []
        response = SimpleNamespace(status='completed', output_parsed=Facts(items=[]), usage=None)
        model.client = SimpleNamespace(responses=SimpleNamespace(parse=AsyncMock(return_value=response)))
        return model

    def test_outbound_privacy_block_prevents_sdk_request(self):
        model = self.model(AsyncMock(side_effect=RuntimeError('privacy_block')))
        with self.assertRaises(RuntimeError):
            asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))
        model.client.responses.parse.assert_not_called()
        self.assertEqual(model.budget.calls, 0)

    def test_budget_block_prevents_sdk_request(self):
        model = self.model(AsyncMock())
        model.budget = Budget(model.model, 0.000001)
        with self.assertRaises(ValueError):
            asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))
        model.client.responses.parse.assert_not_called()

    def test_structured_request_and_response_check(self):
        check = AsyncMock(); model = self.model(check)
        asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))
        kwargs = model.client.responses.parse.call_args.kwargs
        self.assertFalse(kwargs['store'])
        self.assertEqual(kwargs['text_format'], Facts)
        self.assertEqual(kwargs['max_output_tokens'], 8000)
        self.assertEqual(json.loads(kwargs['input'][1]['content'])['data']['text'], 'fictional')
        self.assertEqual(check.await_count, 2)

    def test_incomplete_response_not_accepted(self):
        model = self.model(AsyncMock())
        model.client.responses.parse.return_value.status = 'incomplete'
        with self.assertRaises(ValueError):
            asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))
