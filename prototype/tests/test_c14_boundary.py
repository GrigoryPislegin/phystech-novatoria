"""Synthetic regression: real NER, real SDK, strictly local MockTransport."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest

from prototype.analysis_contracts import ResumeAnalysis, VacancyAnalysis
from prototype.contracts import Requirements
from prototype.demo import ReplayModel, demo_inputs
from prototype.model import Model, Budget
from prototype.pipeline import run_pipeline
from prototype.privacy import check_data
from prototype.privacy_core import Detector, LocalPrivacy
from prototype.privacy_core.models import load
from prototype.run_store import RunStore


class FixtureSDK(Model):
    def __init__(self, privacy, mutate):
        import httpx
        from openai import AsyncOpenAI
        self.model, self.privacy = 'gpt-6-luna', privacy
        self.budget, self.usage, self.requests = Budget(self.model), [], []
        replay = ReplayModel()

        async def respond(request):
            data = json.loads(json.loads(request.content)['input'][1]['content'])
            self.requests.append(data)
            task, payload = data['task'], data['data']
            schema = {'facts':ResumeAnalysis, 'requirements':Requirements, 'evaluation':VacancyAnalysis}[task]
            value = (await replay.ask(schema, task, payload)).model_dump()
            mutate(task, payload, value)
            return httpx.Response(200, request=request, json={
                'id':'resp_synthetic', 'object':'response', 'created_at':0, 'model':self.model, 'status':'completed',
                'output':[{'type':'message', 'role':'assistant', 'id':'msg_synthetic', 'status':'completed',
                           'content':[{'type':'output_text', 'text':json.dumps(value), 'annotations':[]}]}], 'usage':None})
        self.client = AsyncOpenAI(api_key='synthetic-not-a-secret', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))


@unittest.skipUnless(Path('data/private/privacy-models/slovnet_ner_news_v1.tar').is_file(), 'public NER models absent')
class C14BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(load('data/private/privacy-models'))

    def run_fixture(self, mutate):
        async def run():
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, mutate)
            resume, jobs = demo_inputs()
            sources = {}
            try:
                report = await run_pipeline(resume + ' Использовал Excel 1 год.', jobs, model, privacy,
                                            source_sink=sources.update)
                return report, model.requests, privacy.summary(), sources
            finally:
                await model.close()
                privacy.close()
        return asyncio.run(run())

    def test_contextual_ner_response_and_re_egress_keep_exact_quotes(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'].append({'id':'f3', 'text':'Создавала отчёты в Excel, где работала бухгалтером.',
                                       'quote':'Использовал Excel 1 год.'})
        report, requests, summary, _ = self.run_fixture(mutate)
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(len(report['ranking']['jobs']), 3)
        self.assertEqual(len(requests), 7)
        self.assertEqual(report['facts']['items'][-1]['quote'], 'Использовал Excel 1 год.')
        self.assertIn('Excel', requests[2]['data']['facts']['items'][-1]['text'])
        self.assertTrue(summary['contextual_findings'])

    def test_unseen_entity_still_blocks_facts_with_safe_diagnostic(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'][0]['text'] = 'Мария Петрова работала в Москве.'
        report, requests, _, sources = self.run_fixture(mutate)
        self.assertEqual(len(requests), 1)
        self.assertEqual(report['ranking']['jobs'], [])
        diagnostic = report['errors'][0]['privacy']
        self.assertEqual(diagnostic['stage'], 'facts')
        self.assertEqual(diagnostic['direction'], 'response')
        self.assertGreater(sum(diagnostic['findings'].values()), 0)
        self.assertNotIn('Мария', json.dumps(report, ensure_ascii=False))
        with tempfile.TemporaryDirectory() as root:
            store = RunStore(root)
            try:
                item, _ = store.create({'mode':'synthetic-protected-mock', 'scenario':'success', 'total':3}, 'c14')
                store.start(item['run_id'])
                store.finish(item['run_id'], report, sources)
                summary = store.get(item['run_id'])
                self.assertEqual(summary['state'], 'failed')
                self.assertEqual(summary['stage'], 'facts')
                self.assertEqual(summary['error'], 'privacy_residual_findings')
            finally:
                store.close()

    def test_response_failure_keeps_completed_vacancy(self):
        def mutate(task, payload, value):
            if task == 'requirements' and 'Java' in payload['text']:
                value['items'][0]['text'] = 'test.person@example.org'
        report, requests, _, _ = self.run_fixture(mutate)
        self.assertEqual(len(report['ranking']['jobs']), 1)
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(len(requests), 4)
        self.assertEqual(report['errors'][0]['privacy']['findings'], {'EMAIL':1})
        self.assertNotIn('устойчиво', report['leader']['summary'].lower())

    def test_forged_refs_and_quotes_are_never_accepted(self):
        for text, code in [('[[PRIV:deadbeefdeadbeef:1:ORG]]','privacy_untrusted_reference'),
                           ('Несуществующая цитата об опыте.', 'model_invalid')]:
            def mutate(task, payload, value):
                if task == 'facts':
                    value['items'][0]['quote'] = text
            report, requests, _, _ = self.run_fixture(mutate)
            self.assertEqual(report['errors'][0]['code'], code)
            self.assertEqual(report['ranking']['jobs'], [])
            self.assertEqual(len(requests), 1)

    def test_hidden_value_cannot_be_restored_even_if_context_now_misses_it(self):
        async def run():
            privacy = LocalPrivacy(self.detector)
            try:
                await privacy.redact('ФИО: zqxprivate\nИспользовал Excel 1 год.')
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await check_data(privacy, {'text':'опыт zqxprivate'}, prepared=True, stage='facts', direction='response')
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await check_data(privacy, {'text':'zqxprivate'}, prepared=True, stage='evaluation', direction='outbound')
            finally:
                privacy.close()
        asyncio.run(run())

    def test_dynamic_model_keys_never_enter_diagnostics(self):
        async def run():
            privacy = LocalPrivacy(self.detector)
            try:
                with self.assertRaises(RuntimeError) as error:
                    await check_data(privacy, {'private@example.org':'skill'}, prepared=True,
                                     stage='facts', direction='response')
                encoded = json.dumps(error.exception.diagnostic)
                self.assertNotIn('private', encoded)
                self.assertEqual(set(error.exception.diagnostic), {'stage','direction','findings'})
            finally:
                privacy.close()
        asyncio.run(run())

    def test_source_and_other_sessions_never_inherit_response_exceptions(self):
        async def run():
            source = 'Создавала отчёты в Excel, где работала бухгалтером.'
            privacy = LocalPrivacy(self.detector)
            await privacy.redact('Использовал Excel 1 год.')
            protected = await privacy.redact(source)
            self.assertNotIn('Excel', protected)
            # Once hidden, the value blocks even if an earlier source retained it.
            with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                await check_data(privacy, {'text':source}, prepared=True)
            other = LocalPrivacy(self.detector)
            with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                await check_data(other, {'text':source}, prepared=True)
            privacy.close()
            other.close()
            self.assertEqual(privacy._safe_sources, [])
        asyncio.run(run())

    def test_hidden_components_and_canonical_forms_cannot_be_restored(self):
        cases = [
            ('ФИО: Иван Иванов, опыт работы 3 года.\nPython.', 'кандидат иван иванов работал в команде.'),
            ('Full name: John Smith, experience listed below.\nDeveloped Python tools.', 'experience: smith developed tools.'),
            ('ФИО: zqxprivate. Дополнение\nОпыт работы 3 года.', 'опыт zqxprivate'),
            ('ФИО: zqxprivate qzxsecond', 'опыт zqxprivate   qzxsecond'),
            ('ФИО: e\u200d\u0301zqx', 'опыт ézqx'),
        ]
        async def run():
            for source, restored in cases:
                privacy = LocalPrivacy(self.detector)
                try:
                    await privacy.redact(source)
                    with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                        await check_data(privacy, {'text':restored}, prepared=True)
                finally:
                    privacy.close()
        asyncio.run(run())

    def test_short_hidden_values_do_not_match_inside_professional_words(self):
        async def run():
            for source in ['Имя: Ли\nАнализировали отчёты.', 'ИНН: 12\nИспользовал Python версии 3.12.']:
                privacy = LocalPrivacy(self.detector)
                try:
                    safe = await privacy.redact(source)
                    await check_data(privacy, {'text':safe}, prepared=True)
                finally:
                    privacy.close()
        asyncio.run(run())

    def test_terminal_privacy_error_wins_over_recoverable_model_error(self):
        def mutate(task, payload, value):
            if task == 'requirements':
                if 'Python' in payload['text']:
                    value['items'] = 'schema-invalid'
                else:
                    value['items'][0]['text'] = 'blocked@example.org'
        report, _, _, sources = self.run_fixture(mutate)
        with tempfile.TemporaryDirectory() as root:
            store = RunStore(root)
            try:
                item, _ = store.create({'mode':'synthetic-protected-mock','scenario':'success','total':3}, 'c14-mixed')
                store.start(item['run_id'])
                store.finish(item['run_id'], report, sources)
                self.assertEqual(store.get(item['run_id'])['error'], 'privacy_residual_findings')
            finally:
                store.close()

    def test_dense_hidden_index_is_bounded_and_cancellable(self):
        from types import SimpleNamespace
        async def run():
            privacy = LocalPrivacy(Detector(lambda text:SimpleNamespace(spans=[])))
            await privacy.redact('\n'.join('ФИО: ' + 'z'*i for i in range(10,90)))
            text = 'Обычный профессиональный текст. '*1900
            with self.assertRaisesRegex(RuntimeError, 'privacy_scan_limit'):
                await privacy.check_prepared(text)
            pending = asyncio.create_task(privacy.check_prepared(text))
            await asyncio.sleep(0)
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            privacy.close()
        asyncio.run(run())

    def test_source_set_masks_known_values_before_granting_provenance(self):
        async def run():
            privacy = LocalPrivacy(self.detector)
            raw = ['ФИО: Иван Иванов, опыт работы 3 года.\nИспользовал Python.',
                   'кандидат иван иванов работал в команде. Опыт Python обязателен.']
            sources = [await privacy.redact(value) for value in raw]
            sources = await privacy.finalize_sources(sources)
            for source in sources:
                self.assertNotIn('иван', source.casefold())
                self.assertIn('Python', source)
                await check_data(privacy, {'text':source}, prepared=True)
            privacy.close()
        asyncio.run(run())
