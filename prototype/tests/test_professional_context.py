"""Professional source text must survive without exempting names globally."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from prototype.privacy_core import Detector, LocalPrivacy, REFERENCE
from prototype.privacy_core.models import load


class ProfessionalContextTests(unittest.TestCase):
    def detector(self, value, kind):
        # Force the observed NER misclassification independent of its context
        # sensitivity; keep the actual structural detector and whole pipeline.
        def ner(text):
            start = text.find(value)
            return SimpleNamespace(spans=[] if start < 0 else [
                SimpleNamespace(start=start, stop=start+len(value), type=kind)])
        return Detector(ner)

    def test_residence_labels_mask_complete_address_without_ner_help(self):
        async def run(label, separator, address):
            privacy = LocalPrivacy(Detector(lambda _: SimpleNamespace(spans=[])))
            try:
                source = label + separator + address + '\nСтек: SQL.'
                result = (await privacy.finalize_sources([await privacy.redact(source)]))[0]
                self.assertNotIn('Лесная', result)
                self.assertNotIn('д. 12', result)
                self.assertIn('Стек: SQL.', result)
                await privacy.check_prepared(result)
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await privacy.check_prepared(address)
            finally:
                privacy.close()
        for label in ('Проживаю', '- Проживаю', 'Проживает', 'Зарегистрирован', 'Зарегистрирована', 'Место жительства', 'Адрес', 'Регистрация'):
            for separator in (': ', ':\n', ' — '):
                with self.subTest(label=label, separator=separator):
                    asyncio.run(run(label, separator, 'Казань, ул. Лесная, д. 12.'))
                    asyncio.run(run(label, separator, 'Казань\nул. Лесная, д. 12.'))
                    asyncio.run(run(label, separator, 'Казань\nул. Лесная\nд. 12.'))
                    asyncio.run(run(label, separator, 'Казань; ул. Лесная, д. 12.'))
        asyncio.run(run('Зарегистрирован по адресу', ' ', 'Казань, ул. Лесная, д. 12.'))
        privacy = LocalPrivacy(Detector(lambda _: SimpleNamespace(spans=[])))
        try:
            achievement = 'Зарегистрирован патент на алгоритм обработки данных.'
            self.assertEqual(asyncio.run(privacy.redact(achievement)), achievement)
            result = asyncio.run(privacy.redact('Проживаю в Казани, ул. Лесная, д. 12. Сейчас аналитик.'))
            self.assertIn('Сейчас аналитик.', result)
            self.assertNotIn('Лесная', result)
        finally:
            privacy.close()

    def test_experience_heading_and_role_are_not_personal_identity(self):
        for text, value in [('Опыт работы: 2 года 5 месяцев', 'Опыт'),
                            ('Full Stack Developer', 'Full Stack Developer')]:
            privacy = LocalPrivacy(self.detector(value, 'PER'))
            self.assertEqual(asyncio.run(privacy.redact(text)), text)
            privacy.close()

    def test_known_technology_needs_a_professional_slot(self):
        examples = [
            'Опыт коммерческой разработки на Vue.js: компонентный подход.',
            'Понимание разницы между SQL и NoSQL.',
            'Опыт работы с Git, TypeScript, REST API.',
            'Знание Figma (работа с макетом, экспорт ресурсов).',
            'Не работал с TypeScript 2 года.',
        ]
        for text, term in zip(examples, ['Vue','NoSQL','TypeScript','Figma','TypeScript']):
            privacy = LocalPrivacy(self.detector(term, 'ORG'))
            self.assertEqual(asyncio.run(privacy.redact(text)), text)
            asyncio.run(privacy.check_prepared(text))
            privacy.close()

    def test_analytics_and_skill_lists_preserve_only_exact_professional_hits(self):
        examples = [
            ('Работал с PostgreSQL, Docker и Kafka.', 'Kafka'),
            ('— Опыт работы со Spark.', 'Spark'),
            ('Опыта работы со Spark нет.', 'Spark'),
            ('Обязателен опыт работы с Vue.js от 2 лет.', 'Vue.js'),
            ('Готовил еженедельные отчёты для отдела продаж в Excel.', 'Excel'),
            ('Строил дашборды в Power BI и Tableau.', 'Power BI'),
            ('Построил дашборды удержания и воронки в Tableau.', 'Tableau'),
            ('Настроил сквозную аналитику событий в Amplitude.', 'Amplitude'),
            ('Вёл учёт в 1С:Бухгалтерия и Excel, знаю МСФО.', 'МСФО'),
            ('Airflow использовал только как пользователь готовых пайплайнов, сам пайплайны не писал.', 'Airflow'),
            ('Навыки:\n- Vue.js\n- TypeScript\n- Figma', 'TypeScript'),
            ('Сократил время загрузки страницы с 4 до 1,5 секунды.', 'Сократил'),
        ]
        async def run(text, term):
            privacy = LocalPrivacy(self.detector(term, 'ORG'))
            try:
                result = (await privacy.finalize_sources([await privacy.redact(text)]))[0]
                self.assertEqual(result, text)
                await privacy.check_prepared(result)
            finally:
                privacy.close()
        for text, term in examples:
            with self.subTest(source=text):
                asyncio.run(run(text, term))

    def test_identity_and_employer_contexts_keep_masking(self):
        examples = [
            ('Имя: Опыт', 'Опыт', 'PER'),
            ('ФИО: Full Stack Developer', 'Full Stack Developer', 'PER'),
            ('Имя: Figma', 'Figma', 'ORG'),
            ('Опыт работы в Figma', 'Figma', 'ORG'),
            ('Опыт работы с SQL 1 год как с подрядчиком.', 'SQL', 'ORG'),
            ('Знание Figma, где работала бухгалтером.', 'Figma', 'ORG'),
            ('Знание Microsoft.', 'Microsoft', 'ORG'),
            ('Знание ZqxPrivate.', 'ZqxPrivate', 'ORG'),
            ('Знание Figma Ивана Смирнова.', 'Figma Ивана Смирнова', 'ORG'),
            ('Знание SQL Partners.', 'SQL Partners', 'ORG'),
            ('Знание SQL Partners.', 'SQL', 'ORG'),
            ('Знание Figma.', 'Figma', 'PER'),
            ('Знание Figma.', 'Figma', 'LOC'),
            ('TypeScript', 'TypeScript', 'ORG'),
            ('Навыки:\n- SQL Partners\n- TypeScript', 'SQL', 'ORG'),
            ('Навыки:\n- Kafka\n- TypeScript', 'Kafka', 'PER'),
            ('Строил дашборды в Tableau, где работал бухгалтером.', 'Tableau', 'ORG'),
            ('Работал с Kafka, у них в штате.', 'Kafka', 'ORG'),
            ('Знание DAX Company.', 'DAX', 'ORG'),
            ('Работал в Kafka, работал с Vue.js.', 'Kafka', 'ORG'),
            ('Клиенты:\n— Работал с Tableau.', 'Tableau', 'ORG'),
            ('Среди клиентов — несколько компаний, работал с Tableau и Amplitude.', 'Tableau', 'ORG'),
            ('Сократил', 'Сократил', 'ORG'),
            ('Сократил время загрузки страницы с 4 до 1,5 секунды.', 'Сократил', 'PER'),
        ]
        for text, term, kind in examples:
            with self.subTest(source=text):
                privacy = LocalPrivacy(self.detector(term, kind))
                result = asyncio.run(privacy.redact(text))
                self.assertNotIn(term, REFERENCE.sub('', result))
                privacy.close()

    def test_separate_identification_overrides_professional_context_across_documents(self):
        async def run():
            privacy = LocalPrivacy(self.detector('Figma', 'ORG'))
            try:
                skills = await privacy.redact('Знание Figma.')
                self.assertEqual(skills, 'Знание Figma.')
                name = await privacy.redact('Имя: Figma')
                sources = await privacy.finalize_sources([skills, name])
                self.assertNotIn('Figma', REFERENCE.sub('', '\n'.join(sources)))
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await privacy.check_prepared('Знание Figma.')
            finally:
                privacy.close()
        asyncio.run(run())

    def test_spanning_finding_is_not_partially_exempted(self):
        text = 'Знание Figma. Анна Смирнова'
        privacy = LocalPrivacy(self.detector('Figma. Анна Смирнова', 'ORG'))
        result = asyncio.run(privacy.redact(text))
        self.assertNotIn('Анна', result)
        privacy.close()

    def test_technical_lists_can_include_unrecognized_items_without_exempting_them(self):
        examples = [
            ('Основной стек: Vue.js, Nuxt, Vue Router, TypeScript, REST API.', 'TypeScript'),
            ('Стек:\nNuxt, Vue Router, TypeScript, REST API.', 'REST API'),
            ('Разработка интерфейсов по макетам Figma.', 'Figma'),
            ('Ключевые достижения: интеграция с REST API.', 'REST API'),
        ]
        for text, term in examples:
            privacy = LocalPrivacy(self.detector(term, 'ORG'))
            self.assertEqual(asyncio.run(privacy.redact(text)), text)
            privacy.close()
        for term in ('Nuxt', 'SQL Partners'):
            privacy = LocalPrivacy(self.detector(term, 'ORG'))
            result = asyncio.run(privacy.redact(f'Основной стек: Vue.js, {term}, TypeScript.'))
            self.assertNotIn(term, REFERENCE.sub('', result))
            privacy.close()


@unittest.skipUnless(Path('data/private/privacy-models/slovnet_ner_news_v1.tar').is_file(), 'public NER models absent')
class RealProfessionalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(load('data/private/privacy-models'))

    def test_actual_ner_preserves_professional_phrases_through_source_finalization(self):
        source = ('Опыт коммерческой разработки на Vue.js: компонентный подход.\n'
                  'Понимание разницы между SQL и NoSQL.\n'
                  'Опыт работы с Git, TypeScript, REST API.\n'
                  'Знание Figma (работа с макетом, экспорт ресурсов).\n'
                  'Full Stack Developer\nОпыт работы: 2 года 5 месяцев')
        async def run():
            privacy = LocalPrivacy(self.detector)
            try:
                result = (await privacy.finalize_sources([await privacy.redact(source)]))[0]
                self.assertEqual(result, source)
                await privacy.check_prepared(result)
            finally:
                privacy.close()
        asyncio.run(run())

    def test_reviewed_identity_and_employer_regressions_do_not_reach_sdk(self):
        from prototype.demo import demo_inputs
        from prototype.pipeline import run_pipeline
        from prototype.tests.test_c14_boundary import FixtureSDK
        examples = [('Работал с Figma, где я работал аналитиком.', 'Figma'),
                    ('Клиенты:\n— Работал с Tableau.', 'Tableau'),
                    ('Среди клиентов — несколько компаний, работал с Tableau и Amplitude.', 'Amplitude'),
                    ('- Проживаю: Казань, ул. Лесная, д. 12.', 'Лесная'),
                    ('Проживаю:\nКазань\nул. Лесная, д. 12.', 'Лесная'),
                    ('Место жительства: Казань; ул. Лесная, д. 12.', 'Лесная'),
                    ('Работала с Figma, когда была их бухгалтером.', 'Figma'),
                    ('Работал с Figma, у них в штате.', 'Figma'),
                    ('Дополнительно. макеты Figma как сотрудник.', 'Figma'),
                    ('ФИО:\nFull Stack Developer', 'Full Stack Developer'),
                    ('Имя:\n\nFull Stack Developer', 'Full Stack Developer')]
        async def run(text, hidden):
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, lambda *_:None)
            try:
                resume, jobs = demo_inputs()
                report = await run_pipeline(resume+'\n'+text, jobs, model, privacy)
                # "Full" in an explicitly hidden name can collide with a
                # schema status in a later response. That must fail closed;
                # this regression verifies egress, not success on such a name.
                self.assertGreaterEqual(len(model.requests), 1)
                if report['errors']:
                    self.assertTrue(all(e['code'] == 'privacy_residual_findings' for e in report['errors']))
                self.assertNotIn(hidden, json.dumps(model.requests, ensure_ascii=False))
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await privacy.check_prepared(hidden)
            finally:
                await model.close()
                privacy.close()
        for text, hidden in examples:
            with self.subTest(source=text):
                asyncio.run(run(text, hidden))

    def test_prepared_english_name_cannot_inherit_role_provenance(self):
        async def run():
            privacy = LocalPrivacy(self.detector)
            try:
                source = 'Основной проект: John Smith, поддержка и разработка.'
                await privacy.finalize_sources([await privacy.redact(source)])
                with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                    await privacy.check_prepared('text\n\nJohn Smith')
            finally:
                privacy.close()
        asyncio.run(run())

    def test_professional_evidence_reaches_three_vacancies_via_real_sdk_mock(self):
        from prototype.demo import demo_inputs
        from prototype.pipeline import run_pipeline
        from prototype.tests.test_c14_boundary import FixtureSDK
        professional = ('Опыт коммерческой разработки на Vue.js: компонентный подход.\n'
                        'Опыт работы с Git, TypeScript, REST API.\nЗнание Figma.')

        def response(task, payload, value):
            if task == 'facts':
                value['items'].append({'id':'f3','text':professional,'quote':professional})
            elif task == 'requirements':
                value['items'].append({'id':'r3','text':professional,'quote':professional,'mandatory_quote':None})
            else:
                value['rows'] = [{'requirement_id':f'r{i}','status':'full','fact_ids':[f'f{i}'],
                                  'comment':quote,'question':None}
                                 for i,quote in enumerate(['Разрабатывал на Python 3 года.',
                                                           'Использовал SQL 1 год.',professional], 1)]

        async def run():
            privacy = LocalPrivacy(self.detector)
            model = FixtureSDK(privacy, response)
            resume, _ = demo_inputs()
            try:
                sources = {}
                jobs = [(f'job-{i}', 'Python обязателен. SQL желателен.\n'+professional) for i in range(3)]
                report = await run_pipeline(resume+'\nФИО: Анна Смирнова\n'+professional,
                                            jobs, model, privacy, source_sink=sources.update)
                self.assertEqual(report['errors'], [])
                self.assertTrue(report['ranking']['complete'])
                self.assertEqual(len(report['ranking']['jobs']), 3)
                self.assertEqual(len(model.requests), 7)
                self.assertIn(professional, sources['resume'])
                self.assertNotIn('Смирнова', json.dumps(model.requests, ensure_ascii=False))
                for job in report['ranking']['jobs']:
                    requirement = job['requirements']['items'][2]
                    self.assertEqual(requirement['quote'], professional)
                    self.assertEqual(job['evaluation']['rows'][2]['fact_ids'], ['f3'])
                    self.assertFalse(job['evidence_check']['has_invalid'])
            finally:
                await model.close()
                privacy.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
