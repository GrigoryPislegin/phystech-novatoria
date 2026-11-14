"""E14: real matches must be counted, invented ones must not (evidence rules evidence-0.2).

The screen that started this: one requirement proposed as `full`, seven `unknown`, and the vacancy
shown with coverage 0 and the interval 0–100. The row was a model proposal with an exact quote, but
the structure check refused every quote that was a part of a sentence or a bullet of a list — the
two ordinary ways to cite a skill. Synthetic texts only; nothing here measures a model.
"""
import unittest

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row
from prototype.evidence import RULES_VERSION, Source, check_pair, reverses
from prototype.ranking_explanation import explain_leader
from prototype.scoring import rank, score

REF = '[[PRIV:0123456789abcdef:{}:ORG]]'.format


def one_of_eight(cv, requirement_quote, fact_quote, *, status='full', text='Фреймворк интерфейсов', mandatory=False):
    """The first requirement gets the claim under test; seven more are unknown."""
    others = [f'Пункт {i}.' for i in range(2, 9)]
    vacancy = '\n'.join([requirement_quote, *others])
    reqs = Requirements(items=[
        Requirement(id='r1', text=text, quote=requirement_quote,
                    mandatory_quote=requirement_quote if mandatory else None),
        *[Requirement(id=f'r{i}', text=f'другое {i}', quote=q, mandatory_quote=None) for i, q in enumerate(others, 2)]])
    facts = Facts(items=[Fact(id='f1', text='факт', quote=fact_quote)])
    rows = [Row(requirement_id='r1', status=status, fact_ids=['f1'], comment='c',
                question=None if status == 'full' else 'Уточните.')]
    rows += [Row(requirement_id=f'r{i}', status='unknown', fact_ids=[], comment='c', question='Уточните.')
             for i in range(2, 9)]
    evaluation = Evaluation(rows=rows)
    evidence = check_pair(reqs, facts, evaluation, Source.of('cv', cv), Source.of('job', vacancy))
    return score(reqs, evaluation, evidence), evidence.rows[0], (reqs, evaluation, evidence)


def codes(check):
    return {r.code for r in check.reasons}


class ScreenScenarioTests(unittest.TestCase):
    """One real match among eight requirements is 12.5 counted points, never «coverage 0, 0–100»."""

    ORDINARY = {
        'a part of a sentence': ('Разрабатывал интерфейсы на Vue.js 3 года, писал тесты.',
                                 'Разрабатывал интерфейсы на Vue.js 3 года'),
        'one item of an inline list': ('Навыки: Vue.js, TypeScript, Git.', 'Vue.js'),
        'a bullet under a neutral heading': ('Навыки:\n- Vue.js\n- TypeScript', 'Vue.js'),
        'two whole sentences': ('Работал с Vue.js. Писал на TypeScript.', 'Работал с Vue.js. Писал на TypeScript.'),
        'a whole sentence': ('Разрабатывал интерфейсы на Vue.js 3 года.', 'Разрабатывал интерфейсы на Vue.js 3 года.'),
    }

    def test_ordinary_citations_are_counted(self):
        for name, (cv, quote) in self.ORDINARY.items():
            with self.subTest(name):
                s, check, _ = one_of_eight(cv, 'Опыт работы с Vue.js.', quote)
                self.assertEqual((check.state, codes(check)), ('structure_ok', set()))
                self.assertEqual((s['lower'], s['upper'], s['coverage']), (12.5, 100, 12.5))
                self.assertEqual(s['shares'], {'confirmed': 12.5, 'disputed': 0, 'unknown': 87.5})
                self.assertEqual((s['breakdown']['full'], len(s['breakdown']['unknown'])), (['r1'], 7))

    def test_a_disputed_claim_is_shown_apart_from_missing_data(self):
        # Still not counted, but it is a model claim awaiting a check, not «nothing is known».
        s, check, _ = one_of_eight('С Vue.js не работал, писал на jQuery.', 'Опыт работы с Vue.js.', 'Vue.js')
        self.assertEqual((check.state, s['lower'], s['coverage']), ('needs_review', 0, 0))
        self.assertEqual(s['shares'], {'confirmed': 0, 'disputed': 12.5, 'unknown': 87.5})
        self.assertEqual((s['breakdown']['disputed'], s['breakdown']['full']), (['r1'], []))

    def test_new_checks_carry_the_rules_version(self):
        _, _, (_, _, evidence) = one_of_eight('Работал с Vue.js.', 'Опыт работы с Vue.js.', 'Работал с Vue.js.')
        self.assertEqual((evidence.rules_version, RULES_VERSION), ('evidence-0.2', 'evidence-0.2'))
        stored = evidence.model_dump()
        del stored['rules_version']  # a check stored before this change is read as it was
        self.assertIsNone(type(evidence).model_validate(stored).rules_version)


class InventedEvidenceTests(unittest.TestCase):
    """What the stricter old rule protected from is still refused."""

    def refused(self, cv, quote, code, **kwargs):
        s, check, _ = one_of_eight(cv, 'Опыт работы с Vue.js.', quote, **kwargs)
        self.assertEqual(check.state, 'needs_review', cv)
        self.assertIn(code, codes(check), cv)
        self.assertEqual((s['lower'], s['coverage']), (0, 0), cv)
        return s

    def test_the_left_out_part_of_the_sentence_reverses_or_limits_the_quote(self):
        for cv in ('С Vue.js не работал, писал на jQuery.',
                   'Писал на jQuery, а не на Vue.js.',
                   'Планирую изучить Vue.js в этом году.',
                   'Прошёл курс по Vue.js.',
                   'Vue.js использовал только в учебном проекте.',
                   'Vue.js — базовый уровень.',
                   'Without commercial Vue.js experience.',
                   'Знаком с Vue.js по документации.'):
            with self.subTest(cv):
                self.refused(cv, 'Vue.js', 'quote_is_fragment')

    def test_a_negation_inside_the_quote_is_the_model_s_to_read(self):
        # The whole negating sentence is cited for a fail: the structure is sound and the fail is counted.
        s, check, _ = one_of_eight('С Vue.js не работал.', 'Опыт работы с Vue.js.', 'С Vue.js не работал.',
                                   status='fail', mandatory=True)
        self.assertEqual((check.state, s['mandatory'], s['breakdown']['stop_factors']), ('structure_ok', 'violated', ['r1']))

    def test_a_heading_with_a_reversing_word_still_disputes_its_bullets(self):
        for heading in ('Не работал с:', 'Хочу изучить:', 'Планирую освоить:', 'Только учебные проекты:'):
            with self.subTest(heading):
                self.refused(f'{heading}\n- Vue.js\n- TypeScript', 'Vue.js', 'heading_context')

    def test_quote_cut_out_of_two_sentences_with_a_negation_left_out(self):
        self.refused('Писал на jQuery. Vue.js не использовал.', 'jQuery. Vue.js', 'quote_spans_sentences')

    def test_unrelated_fact_proves_nothing(self):
        self.refused('Вёл бухгалтерский учёт в 1С.', 'Вёл бухгалтерский учёт в 1С.', 'evidence_not_linked')

    def test_disputed_fail_never_becomes_a_stop_factor(self):
        s = self.refused('Vue.js изучаю, писал на jQuery.', 'Vue.js', 'quote_is_fragment', status='fail', mandatory=True)
        self.assertEqual((s['mandatory'], s['breakdown']['stop_factors']), ('clarify', []))

    def test_reverses_reads_whole_words_only(self):
        self.assertFalse(any(map(reverses, ('Навыки:', 'Опыт работы:', 'Нетология', 'Notebook', 'Технологии:',
                                            'Работал с Next.js 3 года', 'Ключевые навыки'))))
        self.assertTrue(all(map(reverses, ('не работал', 'Нет опыта', 'без опыта', "don't use", 'ещё изучаю'))))


class MaskedTermTests(unittest.TestCase):
    """A privacy reference is one hidden term: the same value links, the marker itself never does."""

    def test_the_same_hidden_value_links_resume_and_vacancy(self):
        s, check, _ = one_of_eight(f'Разрабатывал интерфейсы на {REF(1)} 3 года.', f'Опыт работы с {REF(1)}.',
                                   f'Разрабатывал интерфейсы на {REF(1)} 3 года.')
        self.assertEqual((check.state, s['coverage']), ('structure_ok', 12.5))

    def test_different_hidden_values_do_not_link_through_the_marker(self):
        # Before: «PRIV», «ORG» and the run id were shared "terms", so any two masked sentences were linked.
        s, check, _ = one_of_eight(f'Разрабатывал интерфейсы на {REF(1)} 3 года.', f'Опыт работы с {REF(2)}.',
                                   f'Разрабатывал интерфейсы на {REF(1)} 3 года.', text='Фреймворк')
        self.assertEqual((check.state, codes(check), s['coverage']), ('needs_review', {'link_hidden_by_mask'}, 0))

    def test_a_term_hidden_on_one_side_only_is_named_as_such(self):
        s, check, _ = one_of_eight(f'Разрабатывал интерфейсы на {REF(1)} 3 года.', 'Опыт работы с Vue.js.',
                                   f'Разрабатывал интерфейсы на {REF(1)} 3 года.', text='Vue.js')
        self.assertEqual((check.state, codes(check)), ('needs_review', {'link_hidden_by_mask'}))
        self.assertIn('скрыт защитой', check.reasons[0].message)
        self.assertEqual(s['shares']['disputed'], 12.5)  # a claim to check against the original, not «unknown»


class InsufficientDataTests(unittest.TestCase):
    def ranking(self, *jobs):
        results = [{'job_id': f'job-{i}', 'requirements': reqs.model_dump(), 'evaluation': ev.model_dump(),
                    'evidence_check': evidence.model_dump(), 'score': score(reqs, ev, evidence)}
                   for i, (_, _, (reqs, ev, evidence)) in enumerate(jobs, 1)]
        return {'facts': {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]},
                'ranking': rank(results, len(results))}

    def test_no_counted_evidence_anywhere_is_not_a_leader(self):
        disputed = one_of_eight('С Vue.js не работал, писал на jQuery.', 'Опыт работы с Vue.js.', 'Vue.js')
        report = self.ranking(disputed, disputed)
        leader = report['ranking']['leader']
        self.assertEqual((leader['comparable'], leader['state'], report['ranking']['recommendation']),
                         (False, 'open', 'clarify'))
        self.assertIn('no_confirmed_fit', leader['reasons'])
        self.assertTrue(explain_leader(report).summary.startswith('Недостаточно данных для сравнения'))

    def test_one_counted_match_makes_the_set_comparable(self):
        real = one_of_eight('Навыки: Vue.js, TypeScript, Git.', 'Опыт работы с Vue.js.', 'Vue.js')
        disputed = one_of_eight('С Vue.js не работал, писал на jQuery.', 'Опыт работы с Vue.js.', 'Vue.js')
        report = self.ranking(disputed, real)
        leader = report['ranking']['leader']
        self.assertEqual((leader['comparable'], leader['job_ids']), (True, ['job-2']))
        self.assertNotIn('Недостаточно данных', explain_leader(report).summary)


if __name__ == '__main__':
    unittest.main()
