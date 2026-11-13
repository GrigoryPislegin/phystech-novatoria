"""E3: structural evidence checks. All texts are handwritten synthetic examples."""
import json
import unittest
from pathlib import Path

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row, validate_pair
from prototype.evidence import INTEGRATED, Source, check_mandatory, check_pair, check_row, locate, verify_span

CASES = Path(__file__).resolve().parents[2] / 'docs/reviews/egor-cases-2026-11-13.json'


def req(rid='r1', text='Python', quote='Python обязателен.', mandatory=None):
    return Requirement(id=rid, text=text, quote=quote, mandatory_quote=mandatory)


def row(status, fact_ids, rid='r1'):
    return Row(requirement_id=rid, status=status, fact_ids=fact_ids, comment='синтетика',
               question=None if status == 'full' else 'Синтетический вопрос?')


def codes(check):
    return {r.code for r in check.reasons}


class AcceptanceTests(unittest.TestCase):
    def test_1_negation_fragment_is_not_structure_ok(self):
        cv = Source.of('cv', 'Аналитик. Не работал с Python, планирую изучить.')
        facts = Facts(items=[Fact(id='f1', text='Python 3 года', quote='Python')])
        r = req(text='Опыт разработки на Python', quote='Python')
        validate_pair(Requirements(items=[r]), facts, Evaluation(rows=[row('full', ['f1'])]))  # old check passes
        check = check_row(row('full', ['f1']), r, facts, cv)
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('quote_is_fragment', codes(check))
        self.assertIn('Не работал с Python, планирую изучить', check.reasons[0].context)
        self.assertEqual(check.status, 'full')  # model status kept, no fifth status
        self.assertEqual(check.meaning, 'model_claim_unverified')

    def test_2_unrelated_fact_is_not_basis_for_fail(self):
        cv = Source.of('cv', 'Финансовый аналитик. Работал с Excel 5 лет.')
        facts = Facts(items=[Fact(id='f1', text='Excel 5 лет', quote='Работал с Excel 5 лет')])
        r = req(text='Опыт работы с Python', quote='Python обязателен.')
        check = check_row(row('fail', ['f1']), r, facts, cv)
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('evidence_not_linked', codes(check))

    def test_3_heading_scope_for_mandatory(self):
        vacancy = Source.of('job-1', 'Обязательно:\n- Python от 2 лет\nЖелательно:\n- SQL')
        python = req('r1', 'Python от 2 лет', 'Python от 2 лет', 'Обязательно:')
        self.assertEqual(check_mandatory(python, vacancy).state, 'structure_ok')
        sql_short = req('r2', 'SQL', 'SQL', 'Обязательно:')
        self.assertEqual(check_mandatory(sql_short, vacancy).state, 'needs_review')
        sql_long = req('r2', 'SQL', 'SQL', 'Обязательно:\n- Python от 2 лет\nЖелательно:\n- SQL')
        check = check_mandatory(sql_long, vacancy)
        self.assertNotEqual(check.state, 'structure_ok')
        self.assertIn('mandatory_spans_segments', codes(check))

    def test_3b_inline_mandatory_of_other_requirement(self):
        vacancy = Source.of('job-1', 'Python обязателен. SQL желателен.')
        sql = req('r2', 'SQL', 'SQL желателен.', 'Python обязателен.')
        self.assertIn('mandatory_not_linked', codes(check_mandatory(sql, vacancy)))
        python = req('r1', 'Python', 'Python обязателен.', 'Python обязателен.')
        self.assertEqual(check_mandatory(python, vacancy).state, 'structure_ok')
        self.assertEqual(check_mandatory(req('r2', 'SQL', 'SQL желателен.'), vacancy).state, 'not_mandatory')

    def test_4_positive_example_passes(self):
        cv = Source.of('cv', 'Backend-разработчик. Разрабатывал на Python 3 года. Использовал SQL 2 года в отчётности.')
        facts = Facts(items=[Fact(id='f1', text='Python 3 года', quote='Разрабатывал на Python 3 года.'),
                             Fact(id='f2', text='SQL 2 года', quote='Использовал SQL 2 года в отчётности')])
        vacancy = Source.of('job-1', 'Обязательно: Python от 2 лет. Желательно: SQL.')
        reqs = Requirements(items=[req('r1', 'Python от 2 лет', 'Python от 2 лет', 'Обязательно:'),
                                   req('r2', 'SQL', 'SQL')])
        ev = Evaluation(rows=[row('full', ['f1'], 'r1'), row('full', ['f2'], 'r2')])
        pair = check_pair(reqs, facts, ev, cv, vacancy)
        self.assertEqual([r.state for r in pair.rows], ['structure_ok', 'structure_ok'])
        self.assertEqual([m.state for m in pair.mandatory], ['structure_ok', 'not_mandatory'])
        self.assertEqual(pair.rows[0].evidence[0].sentence, 'Разрабатывал на Python 3 года')
        self.assertFalse(pair.needs_review)

    def test_4b_repeated_quote_is_not_chosen_silently(self):
        text = 'Использовал Python 3 года. Изучал Python на курсе.'
        cv = Source.of('cv', text)
        located = locate(cv, 'Python')
        self.assertEqual(located.reason.code, 'ambiguous_location')
        self.assertIsNone(located.span)
        explicit = locate(cv, 'Изучал Python на курсе', start=text.index('Изучал'))
        self.assertIsNotNone(explicit.span)

    def test_4c_repeated_sentence_with_same_context_is_fine(self):
        cv = Source.of('cv', 'Python 3 года.\nPython 3 года.')
        self.assertIsNotNone(locate(cv, 'Python 3 года').span)

    def test_4d_quote_across_sentences_needs_review(self):
        cv = Source.of('cv', 'Не работал с Java. Python 3 года.')
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Java. Python 3 года')])
        check = check_row(row('full', ['f1']), req(), facts, cv)
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('quote_spans_sentences', codes(check))
        self.assertIn('Не работал с Java', check.reasons[0].context)

    def test_5_fabricated_inputs_are_invalid(self):
        cv = Source.of('cv', 'Разрабатывал на Python 3 года.')
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Разрабатывал на Python 3 года')])
        self.assertIn('unknown_fact_id', codes(check_row(row('full', ['f9']), req(), facts, cv)))
        fake = Facts(items=[Fact(id='f1', text='Python', quote='Писал на Python 10 лет')])
        self.assertEqual(check_row(row('full', ['f1']), req(), fake, cv).state, 'invalid')
        self.assertEqual(locate(cv, 'Python', start=0).reason.code, 'range_mismatch')
        self.assertEqual(locate(cv, 'Python', start=999).reason.code, 'range_mismatch')
        span = locate(cv, 'Разрабатывал на Python 3 года').span
        self.assertEqual(verify_span(span, {'cv': cv}), [])

        def tampered(**change):
            return verify_span(span.model_copy(update=change), {'cv': cv})[0].code

        self.assertEqual(tampered(source_id='cv-x'), 'unknown_source')
        self.assertEqual(tampered(end=span.end + 1), 'range_mismatch')
        self.assertEqual(tampered(start=span.start + 3, end=span.end + 50), 'range_mismatch')
        other = Source.of('cv', 'Разрабатывал на Python 3 года. Добавлено.')
        self.assertEqual(verify_span(span, {'cv': other})[0].code, 'source_mismatch')

    def test_5c_blank_requirement_quote_is_invalid(self):
        vacancy = Source.of('job-1', 'Обязательно: Python. ')
        check = check_mandatory(req('r1', 'Python', ' ', 'Обязательно:'), vacancy)
        self.assertEqual((check.state, codes(check)), ('invalid', {'quote_not_found'}))

    def test_5b_three_kinds_are_distinguishable(self):
        cv = Source.of('cv', 'Разрабатывал на Python 3 года.')
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Python')])
        missing = check_row(row('unknown', []), req(), facts, cv).state
        disputed = check_row(row('full', ['f1']), req(), facts, cv).state
        broken = check_row(row('full', ['f7']), req(), facts, cv).state
        self.assertEqual((missing, disputed, broken), ('no_evidence', 'needs_review', 'invalid'))

    def test_unknown_with_evidence_is_invalid_not_unknown(self):
        cv = Source.of('cv', 'Разрабатывал на Python 3 года.')
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Разрабатывал на Python 3 года')])
        bad = Row(requirement_id='r1', status='unknown', fact_ids=['f1'], comment='c', question='q?')
        self.assertEqual(check_row(bad, req(), facts, cv).state, 'invalid')

    def test_not_integrated_flag(self):
        self.assertTrue(INTEGRATED)


class ReviewRegressionTests(unittest.TestCase):
    """Defects found by the independent review of E3; inputs are synthetic."""

    def test_mandatory_heading_block_ends_at_non_list_line(self):
        python = req('r1', 'Python от 2 лет', 'Python от 2 лет', 'Обязательно:')
        for text in ['Обязательно:\n- Python от 2 лет\nЖелательно: SQL',
                     'Обязательно:\n- Python от 2 лет\nБудет плюсом\n- SQL',
                     'Обязательно:\n- Python от 2 лет\n\n- SQL']:
            with self.subTest(text=text):
                vacancy = Source.of('job-1', text)
                self.assertEqual(check_mandatory(python, vacancy).state, 'structure_ok')
                sql = check_mandatory(req('r2', 'SQL', 'SQL', 'Обязательно:'), vacancy)
                self.assertEqual((sql.state, codes(sql)), ('needs_review', {'mandatory_not_linked'}))

    def test_numbered_list_and_crlf_under_heading(self):
        vacancy = Source.of('job-1', 'Обязательно:\r\n1. Python от 2 лет\r\n2) SQL\r\nЖелательно:\r\n- Docker')
        for quote in ['Python от 2 лет', 'SQL']:
            self.assertEqual(check_mandatory(req('r1', quote, quote, 'Обязательно:'), vacancy).state, 'structure_ok')
        self.assertEqual(check_mandatory(req('r3', 'Docker', 'Docker', 'Обязательно:'), vacancy).state, 'needs_review')

    def test_dots_inside_words_and_numbers_do_not_split_sentences(self):
        cv = Source.of('cv', 'Опыт с Node.js — только учебные проекты.')
        node = req(text='Node.js от 2 лет', quote='Node.js от 2 лет')
        trap = check_row(row('full', ['f1']), node, Facts(items=[Fact(id='f1', text='x', quote='Опыт с Node.')]), cv)
        self.assertEqual(trap.state, 'needs_review')
        self.assertIn('только учебные проекты', trap.reasons[0].context)
        for text, requirement in [('Разрабатывал на Python 3.5 года.', 'Python'),
                                  ('Работаю с ASP.NET Core 2 года.', 'ASP.NET Core')]:
            with self.subTest(text=text):
                cv = Source.of('cv', text)
                ok = check_row(row('full', ['f1']), req(text=requirement, quote=requirement),
                               Facts(items=[Fact(id='f1', text='x', quote=text)]), cv)
                self.assertEqual(ok.state, 'structure_ok', ok.model_dump())

    def test_cv_list_item_under_heading_shows_heading(self):
        python = req(text='Опыт разработки на Python', quote='Python')
        cv = Source.of('cv', 'Ключевые навыки: Excel, SQL.\nНе работал с:\n- Python')
        check = check_row(row('full', ['f1']), python, Facts(items=[Fact(id='f1', text='x', quote='Python')]), cv)
        self.assertEqual(check.state, 'needs_review')
        self.assertIn('heading_context', codes(check))
        self.assertIn('Не работал с', check.evidence[0].heading)
        neutral = Source.of('cv', 'Навыки:\n- Python 3 года')
        check = check_row(row('full', ['f1']), python, Facts(items=[Fact(id='f1', text='x', quote='Python 3 года')]),
                          neutral)
        self.assertEqual(check.evidence[0].heading, 'Навыки:')
        self.assertEqual(codes(check), {'heading_context'})  # code cannot read the heading: a human does

    def test_repeated_requirement_quote_in_vacancy_is_not_chosen_silently(self):
        vacancy = Source.of('job-1', 'Обязательно:\n- Python и SQL\nЖелательно:\n- SQL')
        sql = check_mandatory(req('r2', 'SQL', 'SQL', 'Обязательно:'), vacancy)
        self.assertEqual((sql.state, codes(sql)), ('needs_review', {'ambiguous_requirement_location'}))
        once = Source.of('job-1', 'Обязательно:\n- Python и SQL\nЖелательно:\n- Docker')
        self.assertEqual(check_mandatory(req('r2', 'SQL', 'SQL', 'Обязательно:'), once).state, 'structure_ok')


class SyntheticCasesTests(unittest.TestCase):
    """Expected (draft) answers in docs/reviews must pass; the documented traps must not be structure_ok."""

    @classmethod
    def setUpClass(cls):
        cls.cases = {c['case_id']: c for c in json.loads(CASES.read_text(encoding='utf-8'))['cases']}

    def build(self, case, vacancy):
        cv = Source.of('cv', case['cv_text'])
        vac = Source.of(vacancy['vacancy_id'], vacancy['vacancy_text'])
        reqs = Requirements(items=[Requirement(id=r['id'], text=r['text'], quote=r['quote'],
                                               mandatory_quote=r['mandatory_quote'])
                                   for r in vacancy['expected_requirements']])
        quotes = sorted({q for r in vacancy['expected_rows'] for q in r['cv_quotes']})
        ids = {q: f'f{i + 1}' for i, q in enumerate(quotes)}
        facts = Facts(items=[Fact(id=ids[q], text=q, quote=q) for q in quotes])
        rows = [Row(requirement_id=r['requirement_id'], status=r['status'], fact_ids=[ids[q] for q in r['cv_quotes']],
                    comment=r['rationale'], question=r['question']) for r in vacancy['expected_rows']]
        return reqs, facts, Evaluation(rows=rows), cv, vac

    def test_expected_answers_have_valid_structure(self):
        for case in self.cases.values():
            for vacancy in case['vacancies']:
                if not vacancy['expected_rows']:
                    continue
                with self.subTest(case=case['case_id'], vacancy=vacancy['vacancy_id']):
                    reqs, facts, ev, cv, vac = self.build(case, vacancy)
                    validate_pair(reqs, facts, ev)
                    pair = check_pair(reqs, facts, ev, cv, vac)
                    self.assertFalse([r for r in pair.rows if r.state == 'invalid'])
                    self.assertFalse([m for m in pair.mandatory if m.state in ('invalid', 'needs_review')],
                                     [m.model_dump() for m in pair.mandatory])
                    for r in pair.rows:
                        self.assertEqual(r.state, 'no_evidence' if r.status == 'unknown' else 'structure_ok',
                                         r.model_dump())

    def test_documented_traps_are_flagged(self):
        def trap_row(case_id, status, requirement_text, fact_quote):
            cv = Source.of('cv', self.cases[case_id]['cv_text'])
            facts = Facts(items=[Fact(id='f1', text='x', quote=fact_quote)])
            return check_row(row(status, ['f1']), req(text=requirement_text, quote=requirement_text), facts, cv).state

        def trap_mandatory(case_id, vacancy_index, quote, marker):
            vacancy = self.cases[case_id]['vacancies'][vacancy_index]
            source = Source.of(vacancy['vacancy_id'], vacancy['vacancy_text'])
            return check_mandatory(req('rx', quote, quote, marker), source).state

        self.assertEqual(trap_row('C01-negation', 'full', 'опыт разработки на Python', 'Python'), 'needs_review')
        self.assertEqual(trap_row('C02-irrelevant-fail-evidence', 'fail', 'Python для автоматизации отчётов',
                                  'Работал с Excel 5 лет.'), 'needs_review')
        self.assertNotEqual(trap_mandatory('C03-headings', 0, 'SQL', 'Обязательно:'), 'structure_ok')
        self.assertNotEqual(trap_mandatory('C08-short-vs-detailed', 1, 'Docker', 'Обязательно: SQL.'), 'structure_ok')


if __name__ == '__main__':
    unittest.main()
