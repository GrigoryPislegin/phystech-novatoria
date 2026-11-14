"""E15: a continuous quote from an explicit heading down to its item is a valid mandatory marker.

Found defect: `mandatory_spans_segments` rejected such a marker whenever the vacancy list did not
use «-», «*», «•» or digits — «●», «·», «▪», «o», «✓», «+» after DOCX/PDF extraction, items
without any mark, a blank line under the heading, a heading without a colon. Every marker of the
vacancy was then dropped, all requirements became equal optional units, and the order of vacancies
depended on which layout the model happened to cite. Synthetic texts; no model is measured.
"""
import unittest

from prototype.contracts import Evaluation, Requirement, Requirements, Row
from prototype.evidence import RULES_VERSION, Source, check_mandatory, check_pair
from prototype.contracts import Fact, Facts
from prototype.scoring import score

HEAD = 'Обязательные требования:'
ITEMS = ['Опыт Python от 3 лет.', 'Знание SQL.', 'Git.']


def vacancy(mark='- ', head=HEAD, gap='', optional_head='Будет плюсом:', optional='Docker.'):
    lines = [head, *([''] if gap else []), *(mark + i for i in ITEMS), optional_head, mark + optional]
    return '\n'.join(lines)


def marker(text, quote, head=HEAD):
    return text[text.index(head):text.index(quote) + len(quote)]


def check(text, quote, marker_quote):
    return check_mandatory(Requirement(id='r1', text=quote, quote=quote, mandatory_quote=marker_quote),
                           Source.of('job', text))


def codes(result):
    return {r.code for r in result.reasons}


class ContinuousMarkerTests(unittest.TestCase):
    def test_every_item_of_the_list_is_governed_whatever_the_list_mark(self):
        for mark in ('- ', '* ', '• ', '— ', '1. ', '1) ', '● ', '· ', '▪ ', '◦ ', 'o ', '✓ ', '+ ', '‣ ', '➢ ', '■ '):
            text = vacancy(mark)
            for quote in ITEMS:
                with self.subTest(mark=mark, quote=quote):
                    result = check(text, quote, marker(text, quote))
                    self.assertEqual((result.state, codes(result)), ('structure_ok', set()))

    def test_items_without_marks_a_blank_line_and_a_heading_without_a_colon(self):
        layouts = {'plain lines': vacancy(''),
                   'blank line under the heading': vacancy('- ', gap='\n'),
                   'heading without a colon': vacancy('- ', head='Обязательные требования', optional_head='Будет плюсом'),
                   'plain lines, next part without a colon': vacancy('', optional_head='Будет плюсом')}
        for name, text in layouts.items():
            head = 'Обязательные требования' if 'colon' in name and 'next' not in name else HEAD
            for quote in ITEMS:
                with self.subTest(layout=name, quote=quote):
                    result = check(text, quote, marker(text, quote, head))
                    self.assertEqual((result.state, codes(result)), ('structure_ok', set()))

    def test_the_heading_alone_as_the_marker_still_governs_its_list(self):
        for mark in ('- ', '● ', ''):
            text = vacancy(mark)
            self.assertEqual(check(text, 'Git.', HEAD).state, 'structure_ok', mark)


class StrictNegativeTests(unittest.TestCase):
    """The fix must not turn the marker into a permission."""

    def test_an_item_of_the_optional_part_is_not_governed(self):
        for mark, optional_head in (('- ', 'Будет плюсом:'), ('● ', 'Будет плюсом:'), ('', 'Будет плюсом:'),
                                    ('', 'Будет плюсом'), ('', 'Желательно'), ('● ', 'Nice to have')):
            text = vacancy(mark, optional_head=optional_head)
            for marker_quote in (HEAD, marker(text, 'Docker.')):
                with self.subTest(mark=mark, optional_head=optional_head, marker=marker_quote[:30]):
                    result = check(text, 'Docker.', marker_quote)
                    self.assertEqual(result.state, 'needs_review')
                    self.assertTrue(codes(result) & {'mandatory_not_linked', 'mandatory_spans_segments'})

    def test_a_blank_line_inside_the_list_ends_it(self):
        text = f'{HEAD}\n● Опыт Python от 3 лет.\n\n● Docker.'
        self.assertEqual(check(text, 'Опыт Python от 3 лет.', HEAD).state, 'structure_ok')
        self.assertEqual(check(text, 'Docker.', HEAD).state, 'needs_review')

    def test_another_section_and_its_items_are_not_governed(self):
        text = f'{HEAD}\n● Опыт Python от 3 лет.\nУсловия:\n● Офис в центре города.'
        result = check(text, 'Офис в центре города.', marker(text, 'Офис в центре города.'))
        self.assertEqual(result.state, 'needs_review')
        plain = f'{HEAD}\nОпыт Python от 3 лет.\nУсловия\nОфис в центре города.'
        self.assertEqual(check(plain, 'Офис в центре города.', HEAD).state, 'needs_review')

    def test_a_glued_marker_that_is_not_in_the_vacancy_is_invalid(self):
        text = vacancy('● ')
        glued = f'{HEAD} Git.'  # heading and item joined, skipping what stands between them
        result = Requirement(id='r1', text='Git', quote='Git.', mandatory_quote=glued)
        self.assertEqual((check_mandatory(result, Source.of('job', text)).state,
                          codes(check_mandatory(result, Source.of('job', text)))), ('invalid', {'quote_not_found'}))

    def test_a_heading_that_denies_the_obligation_is_no_marker(self):
        for head in ('Необязательные требования:', 'Не обязательно, но желательно:', 'Желательные навыки:',
                     'Будет плюсом:', 'Nice to have:'):
            for mark in ('- ', '● '):
                text = vacancy(mark, head=head, optional_head='Условия:', optional='Удалённо.')
                for marker_quote in (head, marker(text, 'Git.', head)):
                    with self.subTest(head=head, mark=mark, marker=marker_quote[:25]):
                        result = check(text, 'Git.', marker_quote)
                        self.assertEqual(result.state, 'needs_review')
                        if mark == '- ' or 'требования' in head:  # the list is recognised: the reason is exact
                            self.assertEqual(codes(result), {'mandatory_not_stated'})

    def test_a_short_line_above_ordinary_text_is_not_a_heading(self):
        text = 'Обязательные требования\nОпыт Python от 3 лет.\nGit.'  # no colon and no marked list
        self.assertEqual(check(text, 'Git.', 'Обязательные требования').state, 'needs_review')


class ReviewOf04b80daTests(unittest.TestCase):
    """Counterexamples of the integration review: exact continuous markers that must stay refused."""

    def run_contract(self, text, quotes, markers, statuses, cv='Python знаю. Docker не использовал.'):
        reqs = Requirements(items=[Requirement(id=f'r{i}', text=q, quote=q, mandatory_quote=m)
                                   for i, (q, m) in enumerate(zip(quotes, markers), 1)])
        reqs.validate_source(text)  # the DTO passes the strict wire validation: these are exact quotes
        facts = Facts(items=[Fact(id='f1', text='факт', quote='Python знаю.'),
                             Fact(id='f2', text='факт', quote='Docker не использовал.')])
        rows = [Row(requirement_id=f'r{i}', status=st, fact_ids=[] if st == 'unknown' else [fact], comment='c',
                    question=None if st == 'full' else 'q') for i, (st, fact) in enumerate(statuses, 1)]
        evaluation = Evaluation(rows=rows)
        evidence = check_pair(reqs, facts, evaluation, Source.of('cv', cv), Source.of('job', text))
        return score(reqs, evaluation, evidence), evidence

    def test_only_a_requirements_heading_recovers_a_list_across_lines(self):
        for text, quote in (('Условия работы:\nУдалённо.', 'Удалённо.'),
                            ('Стек проекта:\n● Python.', 'Python.'),
                            ('О команде:\n✓ Пишем на Python.', 'Пишем на Python.'),
                            ('Мы предлагаем\n● Удалённую работу.', 'Удалённую работу.')):
            with self.subTest(text):
                result = check(text, quote, text)  # the whole continuous block as the marker
                self.assertEqual(result.state, 'needs_review')
                self.assertTrue(codes(result) & {'mandatory_spans_segments', 'mandatory_not_linked'})
        for head in ('Требования:', 'Обязательно:', 'Необходимые навыки:', 'Требуется:', 'Must have:', 'Requirements:'):
            text = f'{head}\n● Python.\n● Git.'
            self.assertEqual(check(text, 'Git.', text).state, 'structure_ok', head)
        # What every heading governed before stays: «-» items directly under it.
        self.assertEqual(check('Стек проекта:\n- Python.', 'Python.', 'Стек проекта:').state, 'structure_ok')

    def test_an_item_that_denies_the_obligation_is_not_mandatory(self):
        for text, quote in (('Требования:\n● Docker не требуется.', 'Docker не требуется.'),
                            ('Требования:\n- Docker не требуется.', 'Docker не требуется.'),
                            ('Обязательные требования:\n● Python.\n● Docker не обязателен.', 'Docker не обязателен.'),
                            ('Требования:\n● Docker желателен.', 'Docker желателен.'),
                            ('Требования:\n● Docker — по желанию.', 'Docker — по желанию.')):
            with self.subTest(text):
                result = check(text, quote, text)
                self.assertEqual((result.state, codes(result)), ('needs_review', {'mandatory_not_stated'}))

    def test_a_marked_optional_item_ends_the_mandatory_list(self):
        text = 'Обязательные требования:\n● Python.\n● Будет плюсом: Docker.'
        self.assertEqual(check(text, 'Python.', text[:text.index('Python.') + 7]).state, 'structure_ok')
        for quote in ('Будет плюсом: Docker.', 'Docker.'):
            result = check(text, quote, text)
            self.assertEqual(result.state, 'needs_review', quote)
        after = 'Обязательные требования:\n● Python.\n● Будет плюсом: Docker.\n● Kafka.'
        self.assertEqual(check(after, 'Kafka.', after).state, 'needs_review')  # nothing after it is governed either

    def test_the_score_of_the_exact_contract_keeps_the_optional_item_optional(self):
        text = 'Обязательные требования:\n● Python.\n● Будет плюсом: Docker.'
        s, evidence = self.run_contract(text, ['Python.', 'Docker.'],
                                        ['Обязательные требования:\n● Python.', text],
                                        [('full', 'f1'), ('fail', 'f2')])
        self.assertEqual((s['mandatory'], s['lower'], s['excluded_mandatory_ids'], s['weights']),
                         ('confirmed', 75, ['r2'], {'r1': 75, 'r2': 25}))  # Docker never becomes a hard requirement
        self.assertEqual(s['breakdown']['stop_factors'], [])
        self.assertEqual(evidence.rules_version, RULES_VERSION)
        # The reviewer's reading: both rows quote the whole block as the marker of an optional fail.
        s, _ = self.run_contract('Требования:\n● Python.\n● Docker не требуется.', ['Python.', 'Docker не требуется.'],
                                 [None, 'Требования:\n● Python.\n● Docker не требуется.'],
                                 [('full', 'f1'), ('fail', 'f2')])
        self.assertEqual((s['mandatory'], s['lower'], s['excluded_mandatory_ids'], s['weights']),
                         ('not_set', 50, ['r2'], {'r1': 50, 'r2': 50}))

    def test_a_bonus_item_and_a_plus_inside_an_item_stay_optional(self):
        head = 'Обязательные требования:'
        bonus = f'{head}\n● Python.\n● Бонус: Docker.\n● Kafka.'
        self.assertEqual(check(bonus, 'Python.', bonus[:bonus.index('Python.') + 7]).state, 'structure_ok')
        for quote in ('Docker.', 'Бонус: Docker.', 'Kafka.'):  # the bonus item ends the mandatory list
            self.assertEqual(check(bonus, quote, bonus[:bonus.index(quote) + len(quote)]).state, 'needs_review', quote)
        s, _ = self.run_contract(bonus, ['Python.', 'Docker.'],
                                 [bonus[:bonus.index('Python.') + 7], bonus[:bonus.index('Docker.') + 7]],
                                 [('full', 'f1'), ('fail', 'f2')])
        self.assertEqual((s['mandatory'], s['excluded_mandatory_ids'], s['weights'], s['breakdown']['stop_factors']),
                         ('confirmed', ['r2'], {'r1': 75, 'r2': 25}, []))
        mixed = f'{head}\n● Обязателен Python; Docker — плюс.'
        self.assertEqual(check(mixed, 'Обязателен Python', mixed).state, 'structure_ok')
        result = check(mixed, 'Docker — плюс.', mixed)
        self.assertEqual((result.state, codes(result)), ('needs_review', {'mandatory_not_stated'}))
        s, _ = self.run_contract(mixed, ['Обязателен Python', 'Docker — плюс.'], [mixed, mixed],
                                 [('full', 'f1'), ('fail', 'f2')])
        self.assertEqual((s['mandatory'], s['excluded_mandatory_ids'], s['weights'], s['breakdown']['stop_factors']),
                         ('confirmed', ['r2'], {'r1': 75, 'r2': 25}, []))
        for item in ('Docker будет плюсом.', 'Docker — бонусом.', 'Docker is a plus.', 'Bonus: Docker.'):
            text = f'{head}\n● Python.\n● {item}'
            self.assertEqual(check(text, item, text).state, 'needs_review', item)
        # «плюс» inside another word or a product name is not a denial.
        for item in ('C++ и STL.', 'Плюсовая разработка на C++.', 'Опыт с 1С:Бухгалтерия.'):
            text = f'{head}\n● {item}'
            self.assertEqual(check(text, item, text).state, 'structure_ok', item)

    def test_rules_version_changed_with_the_rules(self):
        self.assertEqual(RULES_VERSION, 'evidence-0.3')


class OrderStabilityTests(unittest.TestCase):
    """The mechanism behind the changing leader: the same vacancy and statuses, two list layouts."""

    def job(self, mark):
        text = vacancy(mark)
        quotes = [*ITEMS, 'Docker.']
        reqs = Requirements(items=[Requirement(id=f'r{i}', text=q, quote=q,
                                               mandatory_quote=marker(text, q) if q in ITEMS else None)
                                   for i, q in enumerate(quotes, 1)])
        cv = 'Писал на Python 4 года.'
        facts = Facts(items=[Fact(id='f1', text='факт', quote=cv)])
        rows = [Row(requirement_id='r1', status='partial', fact_ids=['f1'], comment='c', question='q')]
        rows += [Row(requirement_id=f'r{i}', status='unknown', fact_ids=[], comment='c', question='q') for i in (2, 3, 4)]
        evaluation = Evaluation(rows=rows)
        evidence = check_pair(reqs, facts, evaluation, Source.of('cv', cv), Source.of('job', text))
        return score(reqs, evaluation, evidence)

    def test_the_list_mark_does_not_change_the_score(self):
        dash, dot = self.job('- '), self.job('● ')
        self.assertEqual((dash['excluded_mandatory_ids'], dot['excluded_mandatory_ids']), ([], []))
        self.assertEqual((dash['lower'], dash['upper'], dash['mandatory']), (dot['lower'], dot['upper'], dot['mandatory']))
        self.assertEqual((dot['lower'], dot['groups']['core']['units']), (12.5, 3))  # 75 / 3 mandatory units, partial


if __name__ == '__main__':
    unittest.main()
