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
        self.assertGreaterEqual(kwargs['max_output_tokens'], 2048)
        self.assertEqual(json.loads(kwargs['input'][1]['content'])['data']['text'], 'fictional')
        self.assertEqual(check.await_count, 2)

    def test_short_outputs_reserve_less_than_dense_requirements(self):
        short = self.model(AsyncMock())
        dense = self.model(AsyncMock())
        asyncio.run(short.ask(Facts, 'facts', {'text':'Python 3 года'}))
        asyncio.run(dense.ask(Facts, 'facts', {'text':'Подробное описание профессионального опыта. '*500}))
        self.assertLess(short.client.responses.parse.call_args.kwargs['max_output_tokens'],
                        dense.client.responses.parse.call_args.kwargs['max_output_tokens'])
        self.assertLess(short.budget.reserved, dense.budget.reserved)

    def test_incomplete_response_not_accepted(self):
        model = self.model(AsyncMock())
        model.client.responses.parse.return_value.status = 'incomplete'
        with self.assertRaises(ValueError):
            asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))

    def test_whitespace_only_quote_uses_exact_source_without_retry(self):
        check = AsyncMock()
        model = self.model(check)
        original = Facts(items=[{'id':'f1','text':'Python','quote':'Делал Python 3 года.'}])
        model.client.responses.parse.return_value.output_parsed = original
        source = 'Делал Python\t3\nгода.'
        result = asyncio.run(model.ask(Facts, 'facts', {'text':source}))
        self.assertEqual(result.items[0].quote, source)
        self.assertEqual(original.items[0].quote, 'Делал Python 3 года.')
        self.assertEqual(model.client.responses.parse.await_count, 1)
        self.assertEqual(check.await_count, 3, 'restored DTO must pass privacy again')
        self.assertEqual(model.response_normalizations,
                         [{'stage':'facts','action':'source_quote_whitespace_restored','count':1}])

    def test_ambiguous_or_changed_words_are_not_repaired(self):
        cases = [('Делал Python 3 года.', 'Делал Python\t3 года.\nДелал Python\n3 года.'),
                 ('не работал', 'неработал'), ('Python', 'Py thon'),
                 ('Делал Python.', 'Делал python.'), ('A A', 'A\tA\tA'),
                 ('Делал Python', 'Делал новый Python')]
        for quote, source in cases:
            with self.subTest(quote=quote, source=source):
                model = self.model(AsyncMock())
                model.client.responses.parse.return_value.output_parsed = Facts(
                    items=[{'id':'f1','text':'test','quote':quote}])
                with self.assertRaisesRegex(ValueError, 'model_invalid'):
                    asyncio.run(model.ask(Facts, 'facts', {'text':source}))
                self.assertEqual(model.client.responses.parse.await_count, 2)

    def test_profile_citations_are_restored_inside_the_referenced_fact_only(self):
        from prototype.analysis_contracts import ResumeAnalysis
        from prototype.model import _restore_source_quote_whitespace
        value = ResumeAnalysis(items=[{'id':'f1','text':'Python','quote':'Python 3 года'},
                                      {'id':'f2','text':'SQL','quote':'SQL\t1 год'}],
            profile={'summary':[{'text':'Python', 'sources':[{'fact_id':'f1','quote':'Python 3'}]},
                                {'text':'SQL', 'sources':[{'fact_id':'f1','quote':'SQL 1 год'}]}],
                     'stack':[], 'last_position':None, 'achievements':[],
                     'missing':['stack','last_position','achievements']})
        result, count = _restore_source_quote_whitespace(value, {'text':'Python\n3 года\nSQL\t1 год'})
        self.assertEqual(count, 2)
        self.assertEqual(result.items[0].quote, 'Python\n3 года')
        self.assertEqual(result.profile.summary[0].sources[0].quote, 'Python\n3')
        self.assertEqual(result.profile.summary[1].sources[0].quote, 'SQL 1 год')
