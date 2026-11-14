"""Explicit recalculation preserves saved model outputs and checks source integrity."""
import copy
import unittest

from prototype.recheck import recheck_report
from prototype.run_store import StoreError
from prototype.tests.test_e13_support import load_fixture, run


class RecheckTests(unittest.TestCase):
    def test_recalculation_is_a_new_copy_with_audit_and_same_model_claims(self):
        fixture = load_fixture('analytics')
        report, _ = run(fixture)
        original = copy.deepcopy(report)
        sources = {'resume':fixture['cv_text'], 'jobs':{v['job_id']:v['text'] for v in fixture['vacancies']}}
        result = recheck_report(report, sources)
        self.assertEqual(report, original)
        self.assertEqual(result['facts'], report['facts'])
        original_jobs = {j['job_id']:j for j in report['ranking']['jobs']}
        for job in result['ranking']['jobs']:
            previous = original_jobs[job['job_id']]
            for field in ('evaluation', 'requirements', 'safe_source_sha256', 'conditions'):
                self.assertEqual(job[field], previous[field])
        self.assertEqual(result['evidence_recalculation']['model_calls'], 0)
        self.assertEqual(len(result['evidence_recalculation']['previous']), 3)
        with self.assertRaises(StoreError):
            recheck_report(report, {**sources, 'resume':sources['resume'] + 'changed'})


if __name__ == '__main__':
    unittest.main()
