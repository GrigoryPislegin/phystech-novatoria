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
    def __init__(self, privacy, mutate, response_usage=None):
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
                           'content':[{'type':'output_text', 'text':json.dumps(value), 'annotations':[]}]}], 'usage':response_usage})
        self.client = AsyncOpenAI(api_key='synthetic-not-a-secret', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))


@unittest.skipUnless(Path('data/private/privacy-models/slovnet_ner_news_v1.tar').is_file(), 'public NER models absent')
class C14BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(load('data/private/privacy-models'))

    def run_fixture(self, mutate, resume_suffix='', max_calls=50):
        async def run():
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, mutate)
            model.budget.max_calls = max_calls
            resume, jobs = demo_inputs()
            sources = {}
            try:
                report = await run_pipeline(resume + ' Использовал Excel 1 год.' + resume_suffix, jobs, model, privacy,
                                            source_sink=sources.update)
                return report, model.requests, privacy.summary(), sources
            finally:
                await model.close()
                privacy.close()
        return asyncio.run(run())

    def test_whitespace_only_quotes_complete_three_jobs_with_seven_sdk_calls(self):
        async def run():
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, lambda *_:None)
            resume, jobs = demo_inputs()
            resume = resume.replace('Python 3', 'Python\t3')
            jobs = [(jid, text.replace('Python обязателен', 'Python  обязателен')) for jid,text in jobs]
            try:
                report = await run_pipeline(resume, jobs, model, privacy)
                self.assertEqual(report['errors'], [])
                self.assertTrue(report['ranking']['complete'])
                self.assertEqual(len(model.requests), 7)
                self.assertEqual(report['facts']['items'][0]['quote'], 'Разрабатывал на Python\t3 года.')
                self.assertEqual(report['profile']['state'], 'structure_ok')
                first = next(job for job in report['ranking']['jobs'] if job['job_id'] == 'job-001')
                self.assertEqual(first['requirements']['items'][0]['quote'], 'Python  обязателен.')
                self.assertEqual(first['requirements']['items'][0]['mandatory_quote'], 'Python  обязателен.')
            finally:
                await model.close()
                privacy.close()
        asyncio.run(run())

    def test_hidden_company_equal_to_category_drops_only_optional_labels(self):
        def mutate(task, payload, value):
            if task == 'requirements':
                value['factors'] = {'items':[{'requirement_id':r['id'], 'factor':'education'} for r in value['items']]}
        report, requests, _, _ = self.run_fixture(mutate, '\nРаботал в компании Education.')
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(requests), 7)
        self.assertEqual(len(report['ranking']['jobs']), 3)
        self.assertTrue(all(j['requirement_factors'] is None for j in report['ranking']['jobs']))
        self.assertNotIn('Education', json.dumps(requests, ensure_ascii=False))

    def test_inexact_optional_mandatory_markers_keep_requirements_with_explicit_warnings(self):
        def mutate(task, payload, value):
            if task == 'requirements':
                value['items'][0]['mandatory_quote'] = 'Требования:\n' + value['items'][0]['quote']
        report, requests, _, sources = self.run_fixture(mutate)
        self.assertEqual(report['errors'], [])
        self.assertEqual(len(requests), 7, 'discarding an unsupported marker needs no new model call')
        self.assertTrue(report['ranking']['complete'])
        self.assertFalse(report['verification']['final_allowed'])
        for job in report['ranking']['jobs']:
            requirement = job['requirements']['items'][0]
            self.assertIsNone(requirement['mandatory_quote'])
            self.assertIn(requirement['quote'], sources['jobs'][job['job_id']])
            self.assertEqual(job['contract_warnings'],
                             [{'code':'mandatory_status_unconfirmed', 'requirement_id':requirement['id']}])
            queued = [item for item in report['review_queue']['items']
                      if item['job_id'] == job['job_id'] and item['requirement_id'] == requirement['id']
                      and item['reason_code'] == 'mandatory_unbound']
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]['action'], 'check_list')
        two = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-001')
        self.assertEqual([r['id'] for r in two['requirements']['items']], ['r1','r2'])
        self.assertEqual(len(two['evaluation']['rows']), 2)

    def test_mandatory_recovery_does_not_accept_invalid_requirement_quotes_or_ids(self):
        for defect in ('quote', 'duplicate_id'):
            def mutate(task, payload, value):
                if task == 'requirements':
                    value['items'][0]['mandatory_quote'] = 'Требования:\n' + value['items'][0]['quote']
                    if defect == 'quote':
                        value['items'][0]['quote'] = 'Требования:\n' + value['items'][0]['quote']
                    else:
                        value['items'].append(dict(value['items'][0]))
            report, requests, _, _ = self.run_fixture(mutate)
            self.assertEqual(report['ranking']['jobs'], [])
            self.assertTrue(all(e['code'] == 'model_invalid' for e in report['errors']))
            self.assertEqual(sum(r['task']=='requirements' for r in requests), 6)
            self.assertFalse(any(r['task']=='evaluation' for r in requests))

    def test_private_or_untrusted_mandatory_marker_blocks_before_recovery(self):
        for marker, error in [('zqxprivate', 'privacy_residual_findings'),
                              ('[[PRIV:0123456789abcdef:99:PERSON]]', 'privacy_untrusted_reference')]:
            def mutate(task, payload, value):
                if task == 'requirements':
                    value['items'][0]['mandatory_quote'] = marker + ' ' + value['items'][0]['quote']
            report, requests, _, _ = self.run_fixture(mutate, '\nФИО: zqxprivate')
            self.assertEqual(report['ranking']['jobs'], [])
            self.assertEqual(report['errors'][0]['code'], error)
            self.assertEqual([r['task'] for r in requests], ['facts','requirements'])

    def test_optional_labels_do_not_hide_forged_or_private_core_ids(self):
        for core_id in (False, True):
            def mutate(task, payload, value):
                if task == 'requirements':
                    value['factors'] = {'items':[{'requirement_id':'Education', 'factor':'education'}]}
                    if core_id:
                        value['items'][0]['id'] = 'Education'
            report, requests, _, _ = self.run_fixture(mutate, '\nРаботал в компании Education.')
            self.assertEqual(report['ranking']['jobs'], [])
            expected = 'privacy_residual_findings' if core_id else 'model_invalid'
            self.assertTrue(all(e['code'] == expected for e in report['errors']))
            self.assertFalse(any(r['task'] == 'evaluation' for r in requests))

    def test_stack_enum_collision_on_requirements_does_not_whitelist_hidden_value(self):
        from prototype.analysis_contracts import RequirementsAnalysis

        def mutate(task, payload, value):
            value['factors'] = {'items':[{'requirement_id':r['id'], 'factor':'stack'} for r in value['items']]}

        async def run():
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, mutate)
            try:
                cv = await privacy.redact('Работал в компании Stack.')
                vacancy = await privacy.redact('Python обязателен. SQL желателен.')
                _, vacancy = await privacy.finalize_sources([cv, vacancy])
                result = await model.ask(RequirementsAnalysis, 'requirements', {'text':vacancy})
                self.assertIsNone(result.factors)
                self.assertEqual(len(result.items), 2)
                self.assertEqual(len(model.requests), 1)
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await privacy.check_prepared('Stack')
            finally:
                await model.close()
                privacy.close()
        asyncio.run(run())

    def test_known_value_in_fact_prose_uses_checked_evidence_without_repeating_network(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'][0]['text'] = 'Опыт zqxprivate в разработке'
                value['profile']['summary'][0]['text'] = 'Разработчик zqxprivate'
        report, requests, _, sources = self.run_fixture(mutate, '\nФИО: zqxprivate')
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(len(requests), 7)
        self.assertNotIn('zqxprivate', json.dumps(report, ensure_ascii=False))
        self.assertNotIn('zqxprivate', json.dumps(requests, ensure_ascii=False))
        fact = report['facts']['items'][0]
        self.assertEqual(fact['text'], fact['quote'])
        self.assertIn(fact['quote'], sources['resume'])

    def test_known_value_recovery_does_not_rewrite_quotes_or_identifiers(self):
        for field in ('quote', 'id', 'profile_source_quote'):
            def mutate(task, payload, value):
                if task == 'facts':
                    if field == 'profile_source_quote':
                        value['profile']['summary'][0]['sources'][0]['quote'] = 'zqxprivate'
                    else:
                        value['items'][0][field] = 'zqxprivate'
            report, requests, _, _ = self.run_fixture(mutate, '\nФИО: zqxprivate')
            self.assertEqual(report['ranking']['jobs'], [])
            self.assertEqual(report['errors'][0]['code'], 'privacy_residual_findings')
            self.assertEqual(len(requests), 1)

    def test_recovered_prose_cannot_make_invented_citation_valid(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'][0]['text'] = 'Опыт zqxprivate'
                value['items'][0]['quote'] = 'Несуществующая цитата об опыте.'
        report, requests, _, _ = self.run_fixture(mutate, '\nФИО: zqxprivate')
        self.assertEqual(report['ranking']['jobs'], [])
        self.assertEqual(report['errors'][0]['code'], 'model_invalid')
        self.assertEqual(len(requests), 2)

    def test_recovered_claim_preserves_number_boundaries_between_sources(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'].extend([
                    {'id':'f3','text':'Два результата','quote':'Выпустил 2 единицы.'},
                    {'id':'f4','text':'Отчёты','quote':'Выпустил 300 отчётов.'}])
                value['profile']['summary'] = [{'text':'Опыт zqxprivate', 'sources':[
                    {'fact_id':'f3','quote':'Выпустил 2'}, {'fact_id':'f4','quote':'300 отчётов'}]}]
        report, _, _, _ = self.run_fixture(mutate, '\nВыпустил 2 единицы. Выпустил 300 отчётов.\nФИО: zqxprivate')
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(report['profile']['state'], 'structure_ok', report['profile']['findings'])

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

    def test_unsafe_paraphrases_are_replaced_at_every_stage_without_changing_evidence(self):
        def mutate(task, payload, value):
            if task in {'facts','requirements'}:
                value['items'][0]['text'] = 'Мария Петрова работала в Москве. zqxprivate'
            else:
                value['rows'][0]['comment'] = 'private@example.org zqxprivate'
                value['rows'][0]['question'] = 'Спросить Марию Петрову?'
                value['conditions']['items'] = [{'kind':'work_mode','state':'unknown','cv':None,
                    'vacancy_quote':None,'note':'private@example.org'}]
        report, requests, _, sources = self.run_fixture(mutate, '\nФИО: zqxprivate')
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(len(requests), 7)
        for forbidden in ('zqxprivate','private@example.org','Мария','Марию'):
            self.assertNotIn(forbidden, json.dumps(report, ensure_ascii=False))
            self.assertNotIn(forbidden, json.dumps(requests, ensure_ascii=False))
        for job in report['ranking']['jobs']:
            for requirement in job['requirements']['items']:
                self.assertIn(requirement['quote'], sources['jobs'][job['job_id']])

    def test_invalid_quote_gets_one_budgeted_retry_from_protected_source(self):
        attempts = []
        def mutate(task, payload, value):
            if task == 'facts':
                attempts.append(task)
                if len(attempts) == 1:
                    value['items'][0]['quote'] = 'Несуществующая цитата об опыте.'
        report, requests, _, _ = self.run_fixture(mutate)
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(requests), 8)
        self.assertNotIn('Несуществующая', json.dumps(requests, ensure_ascii=False))

    def test_retry_respects_budget_and_foreign_refs_never_trigger_it(self):
        def invalid_quote(task, payload, value):
            if task == 'facts':
                value['items'][0]['quote'] = 'Несуществующая цитата об опыте.'
        report, requests, _, _ = self.run_fixture(invalid_quote, max_calls=1)
        self.assertEqual(report['errors'][0]['code'], 'budget_limit')
        self.assertEqual(len(requests), 1)
        def foreign_prose(task, payload, value):
            if task == 'facts':
                value['items'][0]['text'] = '[[PRIV:deadbeefdeadbeef:1:ORG]]'
        report, requests, _, _ = self.run_fixture(foreign_prose)
        self.assertEqual(report['errors'][0]['code'], 'privacy_untrusted_reference')
        self.assertEqual(len(requests), 1)

    def test_prose_recovery_does_not_repair_a_missing_required_question(self):
        for question in (None, '   '):
            def mutate(task, payload, value):
                if task == 'evaluation':
                    value['rows'][0].update(status='partial', fact_ids=['f1'],
                                            question=question, comment='private@example.org')
            report, _, _, _ = self.run_fixture(mutate)
            self.assertFalse(report['ranking']['complete'])
            self.assertEqual(report['ranking']['jobs'], [])
            self.assertTrue(all(e['code'] == 'model_invalid' for e in report['errors']))

    def test_schema_retry_marks_usage_estimate_incomplete(self):
        from prototype.application import analyze
        async def run():
            attempts = []
            def mutate(task, payload, value):
                if task == 'facts':
                    attempts.append(task)
                    if len(attempts) == 1:
                        value['items'] = 'invalid-schema'
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, mutate, {'input_tokens':10,'output_tokens':10,'total_tokens':20})
            try:
                resume, jobs = demo_inputs()
                with tempfile.TemporaryDirectory() as out:
                    result = await analyze(resume, jobs, privacy=privacy, model_factory=lambda:model,
                                           out=Path(out), mode='synthetic_sdk_mock_NOT_model_output')
                self.assertTrue(result.report['ranking']['complete'])
                self.assertEqual((len(model.requests), model.budget.calls, len(model.usage)), (8,8,7))
                self.assertIs(result.report['usage_complete'], False)
                self.assertIsNone(result.report['usage_usd_estimate'])
                self.assertGreater(float(result.report['recorded_usage_usd_estimate']), 0)
            finally:
                await model.close()
                privacy.close()
        asyncio.run(run())

    def test_recovery_does_not_reintroduce_a_hidden_word_in_its_own_template(self):
        # A detector can hide a value identical to a common word. New prose
        # written by recovery must not keep colliding with that run's index.
        report, requests, _, _ = self.run_fixture(lambda *_:None, '\nИмя: опыт')
        self.assertTrue(report['ranking']['complete'], report['errors'])
        self.assertEqual(len(requests), 7)

    def test_unseen_entity_still_blocks_facts_with_safe_diagnostic(self):
        def mutate(task, payload, value):
            if task == 'facts':
                value['items'][0]['quote'] = 'Мария Петрова работала в Москве.'
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
                value['items'][0]['quote'] = 'test.person@example.org'
        report, requests, _, _ = self.run_fixture(mutate)
        self.assertEqual(len(report['ranking']['jobs']), 1)
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(len(requests), 4)
        self.assertGreaterEqual(report['errors'][0]['privacy']['findings']['EMAIL'], 1)
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
            self.assertEqual(len(requests), 1 if code == 'privacy_untrusted_reference' else 2)

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
                    value['items'][0]['quote'] = 'blocked@example.org'
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

    def test_russian_name_header_is_hidden_when_news_ner_misses_it(self):
        from types import SimpleNamespace
        from prototype.privacy_core import normalized
        async def run():
            # No NER span: the independent structural rule must cover this CV
            # heading without treating ordinary job-title headings as names.
            detector = Detector(lambda text:SimpleNamespace(spans=[]))
            for header in ('Орлова Ксения Павловна', 'КСЕНИЯ ПАВЛОВНА ОРЛОВА',
                           'Ксения Павловна Орлова', 'Орлова-Петрова Ксения Павловна'):
                privacy = LocalPrivacy(detector)
                try:
                    source = header + '\nСтарший Аналитик Данных\nИспользовал SQL 4 года.'
                    safe = await privacy.redact(source)
                    self.assertNotIn('ксения', safe.casefold())
                    self.assertIn('Старший Аналитик Данных', safe)
                    self.assertIn('Использовал SQL 4 года.', safe)
                    with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                        await privacy.check_prepared('Опыт: ' + normalized(header).casefold())
                    if 'Петрова' in header:
                        for component in ('орлова','петрова'):
                            with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                                await privacy.check_prepared('Опыт: ' + component)
                finally:
                    privacy.close()
        asyncio.run(run())

    def test_professional_headers_are_not_patronymics(self):
        async def run():
            for heading in ('Кирпич Лицевой Керамический', 'Производство Сэндвич Панелей',
                            'Ремонт Сэндвич Панелей'):
                privacy = LocalPrivacy(self.detector)
                try:
                    safe = await privacy.redact(heading + '\nУправлял поставками и разрабатывал отчеты.')
                    self.assertIn(heading, safe)
                finally:
                    privacy.close()
        asyncio.run(run())
