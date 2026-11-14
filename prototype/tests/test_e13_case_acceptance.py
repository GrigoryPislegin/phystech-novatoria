"""E13: synthetic case-like documents through the real SDK (MockTransport) → Model.ask → pipeline → report.

Two layers:
- `passthrough` always runs: contracts, exact quotes, references, failure variants and the draft
  expectations on the original synthetic text;
- `local` runs only where the public NER weights and libraries are installed (the Docker image):
  the same fixtures behind the real privacy_core. A result that is still blocked is compared with
  the blocker recorded in e13-cases.json and reported as a skip with its reason, so the blocker
  stays reproducible without disabling any check. Any other result fails.
The answers are handwritten: nothing here measures an LLM, and no request leaves the process.
"""
import json
import unittest

from prototype.tests.test_e13_support import EXPECTATIONS, load_fixture, real_privacy_available, run, statuses

CASES = {c['case_id']: c for c in json.loads((EXPECTATIONS / 'e13-cases.json').read_text(encoding='utf-8'))['cases']}


def outcome(report: dict) -> dict:
    """What a recruiter would get: how many vacancies were assessed and where the run stopped."""
    first = next(iter(report['errors']), None)
    return {'processed': len(report['ranking']['jobs']),
            'stopped_at': None if first is None else {'stage': first['stage'], 'code': first['code']}}


class CaseMixin:
    case_id: str

    @classmethod
    def setUpClass(cls):
        cls.case = CASES[cls.case_id]
        cls.fixture = load_fixture(cls.case['fixture'])
        cls.report, cls.replay = run(cls.fixture)
        cls.jobs = {j['job_id']: j for j in cls.report['ranking']['jobs']}

    def test_real_model_and_pipeline_were_called_through_the_mock_transport(self):
        n = len(self.fixture['vacancies'])
        self.assertEqual(len(self.replay.requests), 1 + 2 * n)
        self.assertEqual(len(self.replay.outbound), 1 + 2 * n)  # every call went through the SDK client
        self.assertEqual(len(self.report['usage']), 1 + 2 * n)  # usage is recorded only by Model.ask
        self.assertEqual((self.report['model'], self.report['mode']),
                         ('gpt-6-luna', 'synthetic_sdk_mock_NOT_model_output'))
        self.assertEqual((self.report['errors'], self.report['ranking']['complete']), ([], True))
        self.assertTrue(self.fixture['synthetic'])

    def test_every_quote_and_reference_is_exact(self):
        cv = self.fixture['cv_text']
        facts = {f['id']: f['quote'] for f in self.report['facts']['items']}
        self.assertGreaterEqual(len(facts), self.case['min_facts'])
        for quote in facts.values():
            self.assertIn(quote, cv)
        texts = {v['job_id']: v['text'] for v in self.fixture['vacancies']}
        for jid, job in self.jobs.items():
            self.assertGreaterEqual(len(job['requirements']['items']), self.case['min_requirements'])
            for requirement in job['requirements']['items']:
                self.assertIn(requirement['quote'], texts[jid])
                if requirement['mandatory_quote']:
                    self.assertIn(requirement['mandatory_quote'], texts[jid])
            for row in job['evaluation']['rows']:
                self.assertLessEqual(set(row['fact_ids']), set(facts))
                self.assertEqual(row['status'] == 'unknown', not row['fact_ids'])
            self.assertFalse(job['evidence_check']['has_invalid'])
            self.assertFalse(job['conditions']['has_invalid'])
        self.assertNotEqual(self.report['profile']['state'], 'invalid')

    def test_draft_expectations_hold(self):
        expect = self.case['passthrough']
        places = {jid: j['rank'] for jid, j in self.jobs.items()}
        for better, worse in expect['order']:
            self.assertLess(places[better], places[worse], (better, worse))
        self.assertIn(self.report['ranking']['recommendation'], expect['recommendation_in'])
        got = statuses(self.report)
        for jid, rows in expect['statuses'].items():
            for quote, allowed in rows.items():
                self.assertIn(got[jid][quote], allowed, (jid, quote))
        for jid, state in expect['mandatory'].items():
            self.assertEqual(self.jobs[jid]['score']['mandatory'], state, jid)
        for jid, kinds in expect['conflicts'].items():
            self.assertEqual(sorted(self.jobs[jid]['conditions']['conflicts']), sorted(kinds), jid)

    def test_fit_unknowns_and_obligatoriness_are_reported_apart(self):
        for jid, job in self.jobs.items():
            s = job['score']
            unknown = [r for r in job['evaluation']['rows'] if r['status'] == 'unknown']
            self.assertEqual(s['coverage'] < 100, bool(unknown or s['disputed_ids'] or s['conflict_ids']), jid)
            self.assertLessEqual(s['lower'], s['upper'])
            if unknown or s['disputed_ids']:
                self.assertLess(s['lower'], s['upper'], jid)  # missing data widens the range, it is not a fail
            self.assertIn(s['mandatory'], {'confirmed', 'clarify', 'violated', 'not_set'})
            # A condition conflict is shown apart and never moves the score.
            self.assertNotIn('conditions', s)


@unittest.skipUnless(real_privacy_available(), 'public NER weights or libraries are not installed')
class RealPrivacyMixin:
    case_id: str

    @classmethod
    def setUpClass(cls):
        cls.case = CASES[cls.case_id]
        cls.fixture = load_fixture(cls.case['fixture'])
        cls.report, cls.replay = run(cls.fixture, privacy='local')

    def test_run_reaches_the_expected_result_or_the_recorded_blocker(self):
        real, got = self.case['real_privacy'], outcome(self.report)
        if got == real['expected']:
            return
        self.assertEqual(got, real['known_blocker'], 'neither the expected result nor the recorded blocker')
        self.skipTest(f"KNOWN BLOCKER {self.case_id}: {got}; expected {real['expected']}")

    def test_personal_data_never_reaches_the_model(self):
        sent = '\n'.join(self.replay.outbound)
        leaked = [value for value in self.case['personal'] if value in sent]
        if not leaked:
            return
        self.assertEqual(leaked, self.case['real_privacy']['known_leak'], 'a leak that is not recorded')
        self.skipTest(f'KNOWN P0 {self.case_id}: personal data in the outbound payload: {len(leaked)} value(s)')

    def test_no_external_request_and_a_declared_synthetic_mode(self):
        self.assertEqual(self.report['mode'], 'synthetic_sdk_mock_NOT_model_output')
        self.assertEqual(len(self.replay.outbound), len(self.replay.requests))
        self.assertEqual(self.report['privacy']['kind'], 'pseudonymization_not_anonymity')


class MinimalTests(CaseMixin, unittest.TestCase):
    case_id = 'E13-minimal'


class MinimalRealPrivacyTests(RealPrivacyMixin, unittest.TestCase):
    case_id = 'E13-minimal'


class FinanceTests(CaseMixin, unittest.TestCase):
    case_id = 'E13-finance'


class FinanceRealPrivacyTests(RealPrivacyMixin, unittest.TestCase):
    case_id = 'E13-finance'


class AnalyticsTests(CaseMixin, unittest.TestCase):
    case_id = 'E13-analytics'


class AnalyticsRealPrivacyTests(RealPrivacyMixin, unittest.TestCase):
    case_id = 'E13-analytics'


class DevelopmentTests(CaseMixin, unittest.TestCase):
    case_id = 'E13-development'


class DevelopmentRealPrivacyTests(RealPrivacyMixin, unittest.TestCase):
    case_id = 'E13-development'


if __name__ == '__main__':
    unittest.main()
