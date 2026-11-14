"""E13 failure variants: a rejected answer must never look like a finished or a negative result.

Real SDK over MockTransport → Model.ask → pipeline, on the synthetic analytics set (three vacancies).
What must be caught: all results lost while the report looks complete, a wrong count of assessed
vacancies, and a ground the source does not contain. Handwritten answers; no model is measured.
"""
import unittest

from prototype.tests.test_e13_support import load_fixture, real_privacy_available, run

JOBS = ['an-1', 'an-2', 'an-3']


def edit(task, job_id, change):
    def apply(seen_task, seen_job, answer):
        if seen_task == task and seen_job == job_id:
            change(answer)
    return {'edit': apply}


class FailureMixin:
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture('analytics')

    def go(self, faults, privacy='passthrough'):
        report, replay = run(self.fixture, privacy=privacy, faults=faults)
        return report, replay

    def assert_incomplete(self, report, *, processed, lost, stage):
        """The honest shape of a partial run: counted, named, blocked, and never a verdict."""
        ranking = report['ranking']
        self.assertEqual(sorted(j['job_id'] for j in ranking['jobs']), sorted(processed))
        self.assertEqual(sorted(u['job_id'] for u in report['unprocessed']), sorted(lost))
        self.assertEqual(len(ranking['jobs']) + len(report['unprocessed']), len(JOBS))  # nobody vanishes
        self.assertFalse(ranking['complete'])
        self.assertEqual(ranking['recommendation'], 'incomplete')  # never review_top / review_none_fit
        self.assertEqual(report['errors'][0]['stage'], stage)
        self.assertTrue(all(h['state'] == 'blocked' for h in report['handoff']))  # nothing can be handed off
        reasons = [i['reason_code'] for i in report['review_queue']['items']]
        self.assertIn('incomplete_run', reasons)
        self.assertEqual(reasons.count('processing_error') >= len(lost), True)
        self.assertFalse(report['verification']['final_allowed'])


class RejectedAnswerTests(FailureMixin, unittest.TestCase):
    def test_rejected_facts_lose_every_vacancy_and_say_so(self):
        for fault in ('not_json', 'schema'):
            with self.subTest(fault):
                report, replay = self.go({'facts': fault})
                self.assert_incomplete(report, processed=[], lost=JOBS, stage='facts')
                self.assertEqual(report['errors'][0]['code'], 'model_invalid')
                self.assertEqual(replay.requests, [('facts', None), ('facts', None)])  # one retry, no vacancy call without facts
                self.assertEqual(report['facts']['items'], [])
                self.assertIsNone(report['profile'])  # no manager brief is invented

    def test_one_rejected_vacancy_keeps_the_others_and_the_count(self):
        for lost in ('an-1', 'an-2'):  # the would-be leader and a lower one
            with self.subTest(lost):
                report, replay = self.go({'job': {lost: 'not_json'}})
                self.assert_incomplete(report, processed=[j for j in JOBS if j != lost], lost=[lost],
                                       stage='evaluation')
                self.assertEqual(len(replay.requests), 8)  # one retry, then the run went on after the rejection
                self.assertEqual(report['unprocessed'][0]['reason'], 'model_invalid')
        # Without the rejected leader the next vacancy is first only among the processed ones.
        report, _ = self.go({'job': {'an-1': 'not_json'}})
        self.assertEqual(report['ranking']['jobs'][0]['job_id'], 'an-3')
        self.assertIn('Обработаны не все вакансии', report['leader']['summary'])


class InventedGroundTests(FailureMixin, unittest.TestCase):
    def test_quote_that_is_not_in_the_resume_rejects_the_facts(self):
        report, _ = self.go(edit('facts', None, lambda a: a['items'][2].update(
            quote='Писал запросы на SQL к Oracle.')))
        self.assert_incomplete(report, processed=[], lost=JOBS, stage='facts')

    def test_quote_that_is_not_in_the_vacancy_rejects_only_that_vacancy(self):
        report, _ = self.go(edit('requirements', 'an-2', lambda a: a['items'][0].update(
            quote='Опыт работы с Hadoop.', mandatory_quote=None)))
        self.assert_incomplete(report, processed=['an-1', 'an-3'], lost=['an-2'], stage='requirements')

    def test_reference_to_a_fact_that_was_not_extracted_is_rejected(self):
        report, _ = self.go(edit('evaluation', 'an-1', lambda a: a['rows'][1].update(fact_ids=['f99'])))
        self.assert_incomplete(report, processed=['an-2', 'an-3'], lost=['an-1'], stage='evaluation')

    def test_unrelated_fact_gives_no_credit(self):
        base, _ = self.go(None)
        report, _ = self.go(edit('evaluation', 'an-1', lambda a: a['rows'][1].update(fact_ids=['f14'])))
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'an-1')
        before = next(j for j in base['ranking']['jobs'] if j['job_id'] == 'an-1')
        self.assertEqual(job['score']['disputed_ids'], ['r2'])  # «SQL» "proved" by the education line
        self.assertLess(job['score']['lower'], before['score']['lower'])
        self.assertEqual(job['score']['upper'], before['score']['upper'])
        self.assertEqual((base['ranking']['recommendation'], report['ranking']['recommendation']),
                         ('review_top', 'clarify'))
        self.assertIn(('an-1', 'r2'), [(i['job_id'], i['requirement_id']) for i in report['review_queue']['items']])

    def test_profile_claim_outside_its_fact_is_invalid_but_keeps_the_ranking(self):
        report, _ = self.go(edit('facts', None, lambda a: a['profile']['stack'][0]['sources'][0].update(
            quote='Oracle')))
        self.assertEqual((report['profile']['state'], report['ranking']['complete']), ('invalid', True))
        self.assertEqual(len(report['ranking']['jobs']), 3)
        self.assertIn('profile_review', [i['reason_code'] for i in report['review_queue']['items']])

    def test_condition_quote_outside_the_vacancy_blocks_that_handoff_only(self):
        report, _ = self.go(edit('evaluation', 'an-1', lambda a: a['conditions']['items'][0].update(
            vacancy_quote='Формат работы: офис.')))
        states = {h['job_id']: h['state'] for h in report['handoff']}
        self.assertEqual(states, {'an-1': 'blocked', 'an-2': 'draft', 'an-3': 'draft'})
        self.assertEqual(len(report['ranking']['jobs']), 3)  # the vacancy stays ranked


class UnknownIsNotFailTests(FailureMixin, unittest.TestCase):
    ROW = 2  # an-3 «Опыт работы с Power BI.»: the resume names another tool and says nothing about this one

    def test_fail_needs_a_fact_and_unknown_must_have_none(self):
        for name, change in (('fail without a fact', {'status': 'fail'}),
                             ('unknown with forged fact', {'fact_ids': ['forged']})):
            with self.subTest(name):
                report, _ = self.go(edit('evaluation', 'an-3', lambda a, c=change: a['rows'][self.ROW].update(c)))
                self.assert_incomplete(report, processed=['an-1', 'an-2'], lost=['an-3'],
                                       stage='evaluation')

    def test_unknown_existing_background_fact_is_removed_without_score_credit(self):
        base, _ = self.go(None)
        report, _ = self.go(edit('evaluation', 'an-3', lambda a: a['rows'][self.ROW].update(fact_ids=['f8'])))
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'an-3')
        original = next(j for j in base['ranking']['jobs'] if j['job_id'] == 'an-3')
        self.assertTrue(report['ranking']['complete'])
        self.assertEqual(job['evaluation']['rows'][self.ROW]['fact_ids'], [])
        self.assertEqual(job['evaluation']['rows'][self.ROW]['status'], 'unknown')
        self.assertEqual(job['score'], original['score'])

    def test_silence_widens_the_range_and_a_stated_absence_narrows_it(self):
        base, _ = self.go(None)
        unknown = next(j for j in base['ranking']['jobs'] if j['job_id'] == 'an-3')['score']
        self.assertEqual((unknown['mandatory'], unknown['lower'] < unknown['upper']), ('clarify', True))
        # The same row as a fail "proved" by the other tool: structurally it passes, so the difference
        # between the two statuses rests on the model and on the recruiter reading the quote.
        report, _ = self.go(edit('evaluation', 'an-3', lambda a: a['rows'][self.ROW].update(
            status='fail', fact_ids=['f8'], comment='Назван другой инструмент.')))
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'an-3')
        row = next(c for c in job['evidence_check']['rows'] if c['requirement_id'] == 'r3')
        if row['state'] == 'structure_ok':
            self.assertEqual(job['score']['mandatory'], 'violated')
            self.assertIn(('an-3', 'r3', 'mandatory_fail'),
                          [(i['job_id'], i['requirement_id'], i['reason_code']) for i in report['review_queue']['items']])
        else:  # the structure check noticed it: the row is disputed and violates nothing
            self.assertEqual(job['score']['mandatory'], 'clarify')
            self.assertIn('r3', job['score']['disputed_ids'])


@unittest.skipUnless(real_privacy_available(), 'public NER weights or libraries are not installed')
class RealPrivacyBoundaryTests(FailureMixin, unittest.TestCase):
    """The same answers behind real privacy_core; historical blockers are failures, not skips."""

    def stop(self, report):
        first = next(iter(report['errors']), None)
        return len(report['ranking']['jobs']), first and (first['stage'], first['code'])

    def test_forged_privacy_reference_is_refused(self):
        report, replay = self.go(edit('facts', None, lambda a: a['items'][0].update(
            text='Работал в [[PRIV:0000000000000000:1:ORG]]')), privacy='local')
        processed, stopped = self.stop(report)
        self.assertEqual(processed, 0)
        self.assertEqual(stopped[0], 'facts')
        self.assertEqual(stopped[1], 'privacy_untrusted_reference')
        self.assertEqual(replay.requests, [('facts', None), ('facts', None)])

    def test_professional_terms_in_free_text_and_in_quotes(self):
        """Expected: 3 of 3. A tool name the model repeats in free text, or cites as a short quote, is
        professional content of the documents, not personal data."""
        report, _ = self.go(None, privacy='local')
        got = self.stop(report)
        self.assertEqual(got, (3, None))


if __name__ == '__main__':
    unittest.main()
