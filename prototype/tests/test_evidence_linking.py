"""Handwritten counterexamples for false evidence rejection; no case documents."""
import unittest

from prototype.contracts import Fact, Facts, Requirement, Row
from prototype.evidence import Source, check_row, verify_span


def assess(requirement, quotes, source=None, status='partial', paraphrase=None):
    facts = Facts(items=[Fact(id=f'f{i}', text=q, quote=q) for i, q in enumerate(quotes)])
    row = Row(requirement_id='r', status=status, fact_ids=[f.id for f in facts.items],
              comment='Synthetic example', question=None if status == 'full' else 'Clarify?')
    req = Requirement(id='r', text=paraphrase or requirement, quote=requirement, mandatory_quote=None)
    return check_row(row, req, facts, Source.of('cv', source or '\n'.join(quotes)))


class EvidenceLinkingTests(unittest.TestCase):
    def test_aliases_versions_and_related_framework_only_get_supported_credit(self):
        for need, fact, status in [
            ('JavaScript', 'Писал JS', 'full'), ('TypeScript', 'Использовал TS', 'full'),
            ('HTML5 и семантика', 'Создавал страницы HTML', 'partial'),
            ('CSS3 и анимации', 'Писал CSS', 'partial'),
            ('Тестирование интерфейсов', 'Покрывал компоненты unit-тестами', 'partial'),
            ('Vue.js, props и emit', 'Разрабатывал приложения на Nuxt', 'partial')]:
            with self.subTest(need=need):
                self.assertEqual(assess(need, [fact], status=status).state, 'structure_ok')
        self.assertEqual(assess('Опыт ML', ['С машинным обучением не работал'], status='fail').state, 'structure_ok')
        self.assertEqual(assess('Nuxt', ['Работал с Vue']).state, 'needs_review')
        for need, fact in [('HTML5', 'HTML'), ('Vue.js', 'Nuxt'), ('Vue.js', 'JavaScript'),
                           ('JavaScript', 'Java'), ('TypeScript', 'JavaScript')]:
            with self.subTest(need=need, fact=fact):
                self.assertEqual(assess(need, [fact], status='full').state, 'needs_review')

    def test_source_quote_not_model_paraphrase_establishes_relevance(self):
        result = assess('Python', ['JavaScript'], paraphrase='Python или JavaScript')
        self.assertEqual(result.state, 'needs_review')

    def test_general_tenure_does_not_create_skill_tenure_or_ignore_threshold(self):
        self.assertEqual(assess('Опыт работы от 2 лет', ['Опыт работы — 6 лет 3 месяца'],
                                status='full').state, 'structure_ok')
        for need, fact in [('Опыт работы от 5 лет', 'Опыт работы — 2 года'),
                           ('Опыт работы от 2 лет', 'Возраст проекта 6 лет'),
                           ('Опыт работы от 2 лет', 'Обучение 6 лет'),
                           ('Опыт работы от 2 лет', 'Опыт работы — ' + '9' * 4400 + ' лет'),
                           ('Опыт работы с Python от 2 лет', 'Опыт работы — 6 лет')]:
            with self.subTest(need=need, fact=fact):
                self.assertEqual(assess(need, [fact], status='full').state, 'needs_review')

    def test_repeated_positive_quotes_are_bound_to_verifiable_location(self):
        source = 'Использовал Pinia в приложении.\nСтек: Vue, Pinia.\nVue, Pinia, TypeScript'
        check = assess('Pinia', ['Pinia'], source, status='full')
        self.assertEqual(check.state, 'structure_ok')
        self.assertEqual(verify_span(check.evidence[0], {'cv':Source.of('cv', source)}), [])
        for other in ['Не работал с Pinia.', 'Планирую изучить Pinia.', 'Коллеги использовали Pinia.',
                      'Офис выдал книгу про Pinia.', 'Статья про Pinia.', 'Офис Pinia на третьем этаже.',
                      'Стек клиента: Pinia.', 'Ему пригодились навыки Pinia.', 'Пример: миграция на Pinia.']:
            with self.subTest(other=other):
                self.assertEqual(assess('Pinia', ['Pinia'], 'Использовал Pinia. ' + other,
                                        status='full').state, 'needs_review')

    def test_partial_needs_one_relevant_fact_but_does_not_ignore_negative_or_forged_facts(self):
        self.assertEqual(assess('Vue, props и emit', ['Разрабатывал на Nuxt', 'Интегрировал REST API']).state,
                         'structure_ok')
        for extra in ['Не использовал Vue', 'Коллеги использовали Vue']:
            self.assertEqual(assess('Vue, props и emit', ['Разрабатывал на Nuxt', extra]).state, 'needs_review')
        self.assertEqual(assess('Vue', ['Nuxt', 'Выдуманная цитата'], 'Nuxt').state, 'invalid')


if __name__ == '__main__':
    unittest.main()
