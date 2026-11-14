"""E14 acceptance relations for a useful ranking. Synthetic; relations, not one «right» order."""
import unittest

from prototype.ranking_explanation import compare, explain_leader
from prototype.review_queue import build_review_queue
from prototype.tests.test_scoring_v3 import CASES, ranked, report_of, rows_job


def job(core, *extras):
    """One mandatory requirement with `core` status and optional ones."""
    return rows_job(('Vue.js', core), *[(f'навык {i}', s) for i, s in enumerate(extras)], mandatory=(0,))


class RelationTests(unittest.TestCase):
    def lower(self, *args):
        from prototype.scoring import score
        return score(*job(*args))

    def test_the_four_statuses_of_a_key_requirement_are_four_different_results(self):
        full, partial, unknown, fail = (self.lower(s, 'full') for s in ('full', 'partial', 'unknown', 'fail'))
        self.assertEqual([full['lower'], partial['lower'], unknown['lower'], fail['lower']], [100, 62.5, 25, 25])
        self.assertEqual([s['mandatory'] for s in (full, partial, unknown, fail)],
                         ['confirmed', 'clarify', 'clarify', 'violated'])
        # No data and a stated absence give the same points but not the same answer.
        self.assertEqual((unknown['upper'], fail['upper']), (100, 25))
        self.assertEqual((unknown['breakdown']['stop_factors'], fail['breakdown']['stop_factors']), ([], ['r0']))

    def test_more_confirmed_relevant_experience_ranks_higher(self):
        ranking = ranked(strong=job('full', 'full', 'fail'), weak=job('partial', 'full', 'fail'))
        self.assertEqual([j['job_id'] for j in ranking['jobs']], ['strong', 'weak'])

    def test_a_proven_mandatory_fail_ranks_below_any_vacancy_without_one(self):
        ranking = ranked(failed=job('fail', 'full', 'full', 'full'), modest=job('partial', 'fail', 'fail', 'fail'))
        self.assertEqual([(j['job_id'], j['score']['mandatory']) for j in ranking['jobs']],
                         [('modest', 'clarify'), ('failed', 'violated')])

    def test_repeats_splitting_and_optional_rows_do_not_flip_the_order(self):
        base = ranked(a=job('full', 'fail'), b=job('partial', 'full'))
        more_optional = ranked(a=job('full', 'fail', 'fail', 'fail', 'fail'), b=job('partial', 'full'))
        self.assertEqual([j['job_id'] for j in base['jobs']], [j['job_id'] for j in more_optional['jobs']])
        repeat = report_of(CASES['E11-03'])['ranking']  # a literal repeat of a requirement
        places = {j['job_id']: j['rank'] for j in repeat['jobs']}
        self.assertEqual(places['repeat'], places['plain'])

    def test_one_key_unknown_gives_one_exact_question(self):
        report = report_of(CASES['E11-02'])  # the mandatory requirement of the second vacancy is unknown
        leader = report['ranking']['leader']
        self.assertEqual([(d['job_id'], d['requirement_id'], d['kind']) for d in leader['decisive']],
                         [('pluses', 'r1', 'unknown')])
        item = next(i for i in build_review_queue(report).items if i.decisive)
        self.assertEqual((item.job_id, item.requirement_id, item.action), ('pluses', 'r1', 'ask_candidate'))
        self.assertIn('Стаж учёта ОС от 3 лет', item.refs[0].quote)  # the question names the requirement itself

    def test_why_this_one_is_higher_cites_existing_quotes(self):
        report = report_of(CASES['E11-09'])
        c = compare(report, 'relevant', 'weak')
        self.assertEqual(c.outcome, 'a_higher')
        quotes = {r['quote'] for j in report['ranking']['jobs'] for r in j['requirements']['items']}
        self.assertTrue(c.deciding and all(d.requirement_quote in quotes for d in c.deciding))
        self.assertTrue(all(d.cv_quotes == ['цитата'] for d in c.deciding))  # the fact quote of the report
        text = explain_leader(report)
        self.assertTrue(text.factors and all(f.status in ('full', 'partial') for f in text.factors))

    def test_an_unconfirmed_requirement_list_is_a_process_state_not_a_zero(self):
        report = report_of(CASES['E11-12'])  # nobody has confirmed any list
        reasons = {i.reason_code for i in build_review_queue(report).items}
        self.assertIn('requirements_unconfirmed', reasons)
        self.assertTrue(all(j['score']['lower'] > 0 for j in report['ranking']['jobs']))


if __name__ == '__main__':
    unittest.main()
