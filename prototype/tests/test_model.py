import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from prototype.contracts import Facts
from prototype.model import Model, Budget


class ModelBoundaryTests(unittest.TestCase):
    def test_budget_settlement_releases_only_measured_call_headroom(self):
        budget = Budget('gpt-6-luna', 0.02, max_calls=65)
        first = budget.reserve(20000, 16000)
        second = budget.reserve(20000, 16000)
        with self.assertRaisesRegex(ValueError, 'budget_or_call_limit'):
            budget.reserve(20000, 16000)
        budget.settle(first, 100, 100)
        self.assertEqual(float(budget.reserved), 0.01006)
        budget.settle(second, 100, 100)
        for _ in range(59):
            ticket = budget.reserve(20000, 16000)
            budget.settle(ticket, 100, 100)
        self.assertEqual(budget.calls, 61)
        self.assertAlmostEqual(float(budget.reserved), 0.00366)

    def test_unmeasured_call_keeps_reservation_after_other_call_settles(self):
        budget = Budget('gpt-6-luna', 0.02)
        budget.reserve(20000, 16000)
        ticket = budget.reserve(20000, 16000)
        budget.settle(ticket, 100, 100)
        with self.assertRaisesRegex(ValueError, 'budget_or_call_limit'):
            budget.reserve(20000, 16000)

    def test_parallel_budget_waits_for_usage_instead_of_cancelling_affordable_batch(self):
        from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
        from prototype.pipeline import run_pipeline
        async def run():
            budget = Budget('gpt-6-luna', 0.025)
            active, peak = 0, 0
            class Measured(ReplayModel):
                async def ask(self, schema, task, payload):
                    nonlocal active, peak
                    ticket = await budget.acquire(20000, 16000)
                    active += 1
                    peak = max(peak, active)
                    try:
                        await asyncio.sleep(0.005)
                        return await super().ask(schema, task, payload)
                    finally:
                        active -= 1
                        budget.settle(ticket, 100, 100)
            report = await asyncio.wait_for(run_pipeline(*demo_inputs(), Measured(), SyntheticPrivacy()), 2)
            self.assertTrue(report['ranking']['complete'], report['errors'])
            self.assertEqual((active, peak, budget.calls), (0, 2, 7))
            self.assertAlmostEqual(float(budget.reserved), 0.00042)
        asyncio.run(run())

    def test_unmeasured_completed_lease_wakes_budget_waiter_with_real_limit(self):
        async def run():
            budget = Budget('gpt-6-luna', 0.015)
            ticket = await budget.acquire(20000, 16000)
            waiting = asyncio.create_task(budget.acquire(20000, 16000))
            await asyncio.sleep(0)
            self.assertFalse(waiting.done())
            budget.retain(ticket)
            with self.assertRaisesRegex(ValueError, 'budget_or_call_limit'):
                await asyncio.wait_for(waiting, 1)
            self.assertEqual(float(budget.reserved), 0.01)
        asyncio.run(run())

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

    def test_outbound_untrusted_reference_is_not_retried(self):
        model = self.model(AsyncMock(side_effect=RuntimeError('privacy_untrusted_reference')))
        with self.assertRaisesRegex(RuntimeError, 'privacy_untrusted_reference'):
            asyncio.run(model.ask(Facts, 'facts', {'text':'[[PRIV:bad]]'}))
        model.client.responses.parse.assert_not_called()
        self.assertEqual(model.privacy.check.await_count, 1)

    def test_short_references_roundtrip_nested_quotes_and_preserve_literal_aliases(self):
        from prototype.model_references import ModelReferences
        first, second = '[[PRIV:0123456789abcdef:1:PERSON]]', '[[PRIV:0123456789abcdef:2:ORG]]'
        source = {'text':f'[[REF_1]] {first} {second} {first}',
                  'facts':{'items':[{'quote':second}]}}
        references = ModelReferences(source)
        wire = references.encode(source)
        self.assertNotIn('PRIV:', json.dumps(wire))
        self.assertNotEqual(references.prefix, 'REF_')
        self.assertLessEqual(len(references.prefix), 12)
        self.assertEqual(wire['text'], f'[[REF_1]] [[{references.prefix}1]] [[{references.prefix}2]] [[{references.prefix}1]]')
        self.assertEqual(references.decode(wire), source)

    def test_adversarial_literal_namespace_keeps_aliases_short(self):
        from prototype.model_references import ModelReferences
        value = {'text':'X' * 59990 + 'REF_ [[PRIV:0123456789abcdef:1:ORG]]'}
        references = ModelReferences(value)
        self.assertLessEqual(len(references.prefix), 12)
        self.assertEqual(references.decode(references.encode(value)), value)

    def test_ordinary_model_prose_is_not_a_wire_alias(self):
        from prototype.model_references import ModelReferences
        references = ModelReferences({'text':'Python'})
        value = {'text':'Python preferred; reference architecture'}
        self.assertEqual(references.decode(value), value)

    def test_damaged_alias_in_free_text_cannot_survive_valid_quote(self):
        for marker in ('[[REF-1]]', '[[REF 1]]', '［［ＲＥＦ＿１］］'):
            model = self.model(AsyncMock())
            model.client.responses.parse.return_value.output_parsed = Facts(
                items=[{'id':'f1','text':marker,'quote':'Работал в [[REF_1]].'}])
            with self.assertRaisesRegex(ValueError, 'model_invalid'):
                asyncio.run(model.ask(Facts, 'facts', {'text':'Работал в [[PRIV:0123456789abcdef:42:ORG]].'}))
            self.assertEqual(model.client.responses.parse.await_count, 2)

    def test_response_aliases_expand_before_source_and_privacy_checks(self):
        reference = '[[PRIV:0123456789abcdef:42:ORG]]'
        source = f'Работал в {reference}.'
        model = self.model(AsyncMock())
        model.client.responses.parse.return_value.output_parsed = Facts(
            items=[{'id':'f1','text':'[[REF_1]]','quote':'Работал в [[REF_1]].'}])
        result = asyncio.run(model.ask(Facts, 'facts', {'text':source}))
        self.assertEqual(result.items[0].quote, source)
        self.assertEqual(result.items[0].text, reference)
        request = model.client.responses.parse.call_args.kwargs['input'][1]['content']
        self.assertNotIn('PRIV:', request)
        self.assertIn('[[REF_1]]', request)
        self.assertIn(reference, model.privacy.check.call_args.args[0])
        self.assertNotIn('REF_', model.privacy.check.call_args.args[0])

    def test_damaged_alias_retries_without_echoing_rejected_answer(self):
        for bad_alias in ('[[REF_999]]', '[[REF_1]', '[[ref_1]]'):
            model = self.model(AsyncMock())
            responses = [Facts(items=[{'id':'f1','text':alias, 'quote':f'Работал в {alias}.'}])
                         for alias in (bad_alias, '[[REF_1]]')]
            model.client.responses.parse.side_effect = [
                SimpleNamespace(status='completed', output_parsed=value, usage=None) for value in responses]
            source = 'Работал в [[PRIV:0123456789abcdef:42:ORG]].'
            result = asyncio.run(model.ask(Facts, 'facts', {'text':source}))
            self.assertEqual(result.items[0].quote, source)
            self.assertEqual(model.budget.calls, 2)
            calls = model.client.responses.parse.call_args_list
            self.assertEqual(calls[0].kwargs['input'][1], calls[1].kwargs['input'][1])

    def test_unknown_alias_is_never_accepted_and_retry_obeys_budget(self):
        for max_calls, error in ((2, 'model_invalid'), (1, 'budget_or_call_limit')):
            model = self.model(AsyncMock())
            model.budget.max_calls = max_calls
            model.client.responses.parse.return_value.output_parsed = Facts(
                items=[{'id':'f1','text':'[[REF_999]]','quote':'[[REF_999]]'}])
            with self.assertRaisesRegex(ValueError, error):
                asyncio.run(model.ask(Facts, 'facts', {'text':'[[PRIV:0123456789abcdef:42:ORG]]'}))
            self.assertEqual(model.client.responses.parse.await_count, max_calls)

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

    def test_failed_or_cancelled_request_without_usage_is_not_reported_as_fully_measured(self):
        for error in (RuntimeError('transport failed'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                model = self.model(AsyncMock())
                model.client.responses.parse.side_effect = error
                with self.assertRaises(type(error)):
                    asyncio.run(model.ask(Facts, 'facts', {'text':'fictional'}))
                self.assertFalse(model.usage_complete)
                self.assertEqual(model.budget.calls, 1)
                self.assertGreater(model.budget.reserved, 0)
