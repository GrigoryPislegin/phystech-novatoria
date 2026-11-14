"""E15: a continuous quote from an explicit heading down to its item is a valid mandatory marker.

Found defect: `mandatory_spans_segments` rejected such a marker whenever the vacancy list did not
use «-», «*», «•» or digits — «●», «·», «▪», «o», «✓», «+» after DOCX/PDF extraction, items
without any mark, a blank line under the heading, a heading without a colon. Every marker of the
vacancy was then dropped, all requirements became equal optional units, and the order of vacancies
depended on which layout the model happened to cite. Synthetic texts; no model is measured.
"""
import unittest

from prototype.contracts import Evaluation, Requirement, Requirements, Row
from prototype.evidence import Source, check_mandatory, check_pair
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
            text = vacancy('● ', head=head, optional_head='Условия:', optional='Удалённо.')
            for marker_quote in (head, marker(text, 'Git.', head)):
                with self.subTest(head=head, marker=marker_quote[:25]):
                    result = check(text, 'Git.', marker_quote)
                    self.assertEqual((result.state, codes(result)), ('needs_review', {'mandatory_not_stated'}))

    def test_a_short_line_above_ordinary_text_is_not_a_heading(self):
        text = 'Обязательные требования\nОпыт Python от 3 лет.\nGit.'  # no colon and no marked list
        self.assertEqual(check(text, 'Git.', 'Обязательные требования').state, 'needs_review')


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
