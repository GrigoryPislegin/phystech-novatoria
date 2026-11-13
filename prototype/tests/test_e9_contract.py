"""E9a: E5/E7/E8 wired together as the integration contract says. Synthetic fixtures only.

The wired reports come from the real pipeline with synthetic models and the reference wiring in
e9_wiring.py. Expectations below are written by hand; `derived` in the fixtures is a snapshot.
"""
import copy
import json
import unittest
from pathlib import Path

from prototype.candidate_profile import CandidateProfile, Conditions
from prototype.contracts import Evaluation, Facts, Requirements, RequirementFactors
from prototype.evidence import PairCheck
from prototype.ranking_explanation import compare
from prototype.review_policy import assess_handoff, current_versions, report_sha256
from prototype.review_queue import build_review_queue
from prototype.scoring import POLICY_VERSION, score
from prototype.tests.e9_wiring import derived

ROOT = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'


def load(name):
    return json.loads((ROOT / f'e9-contract-{name}.json').read_text(encoding='utf-8'))


def reasons(report, job_id=None):
    return {(i.requirement_id or i.condition_kind, i.reason_code) for i in build_review_queue(report).items
            if i.job_id == job_id}


class ContractShapeTests(unittest.TestCase):
    def test_fields_the_manager_view_reads(self):
        for name in ('normal', 'disputed', 'incomplete'):
            with self.subTest(name):
                report = load(name)['report']
                profile = report['profile']
                self.assertEqual(profile['schema_version'], 'candidate-profile-0.1')
                self.assertLessEqual({'state', 'findings', 'spans', 'display'}, set(profile))
                for job in report['ranking']['jobs']:
                    self.assertEqual(job['score']['policy_version'], POLICY_VERSION)
                    self.assertTrue(job['score']['evidence_applied'])
                    # score_review is only a copy of the v2 field for old readers, never a second correction
                    self.assertEqual(job['score_review']['excluded_mandatory_ids'],
                                     job['score']['excluded_mandatory_ids'])
                    if 'conditions' in job:
                        self.assertLessEqual({'items', 'findings', 'conflicts', 'needs_review', 'has_invalid'},
                                             set(job['conditions']))

    def test_views_are_reproduced_from_the_report(self):
        for name in ('normal', 'disputed', 'incomplete'):
            with self.subTest(name):
                data = load(name)
                self.assertEqual(derived(data['report']), data['derived'])

    def test_model_dtos_pass_the_sdk_strict_conversion(self):
        try:
            from openai.lib._pydantic import to_strict_json_schema
        except ImportError:
            self.skipTest('openai SDK not installed')
        for model in (Requirements, Facts, Evaluation, RequirementFactors, CandidateProfile, Conditions):
            with self.subTest(model.__name__):
                schema = to_strict_json_schema(model)
                for node in [schema, *schema.get('$defs', {}).values()]:
                    if 'properties' in node:
                        self.assertIs(node.get('additionalProperties'), False)
                        self.assertEqual(set(node.get('required', [])), set(node['properties']))


class ScenarioTests(unittest.TestCase):
    def test_normal(self):
        report = load('normal')['report']
        self.assertEqual(report['ranking']['recommendation'], 'review_top')
        self.assertEqual(report['profile']['state'], 'structure_ok')
        self.assertNotIn((None, 'profile_review'), reasons(report))
        self.assertEqual(reasons(report, 'job-003'), {('r1', 'mandatory_fail'), (None, 'requirements_unconfirmed')})

    def test_disputed(self):
        report = load('disputed')['report']
        self.assertEqual(report['ranking']['recommendation'], 'clarify')
        self.assertEqual(report['profile']['state'], 'invalid')  # «SQL 5 лет» from «SQL 2 года.»
        self.assertIn((None, 'profile_review'), reasons(report))
        job_a = reasons(report, 'job-a')
        self.assertLessEqual({('r1', 'ambiguous_location'), ('work_mode', 'condition_conflict'),
                              ('salary', 'condition_review')}, job_a)
        job_b = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-b')
        self.assertEqual((job_b['score']['mandatory'], job_b['score']['excluded_mandatory_ids']), ('not_set', ['r1']))
        self.assertEqual(assess_handoff(report, [], 'job-a').state, 'blocked')

    def test_incomplete(self):
        report = load('incomplete')['report']
        self.assertEqual(report['ranking']['recommendation'], 'incomplete')
        self.assertEqual([e['job_id'] for e in report['unprocessed']], ['job-002'])
        c = compare(report, 'job-001', 'job-003')
        self.assertIn('incomplete_run', c.caveats)
        for job in ('job-001', 'job-003', 'job-002'):
            self.assertEqual(assess_handoff(report, [], job).state, 'blocked')


class ReviewFindingTests(unittest.TestCase):
    def test_presentation_is_built_from_the_wired_scores(self):
        for name in ('normal', 'disputed', 'incomplete'):
            report = load(name)['report']
            ranking = {j['job_id']: j['score'] for j in report['ranking']['jobs']}
            for job in report['presentation']['jobs']:
                with self.subTest(name=name, job=job['job_id']):
                    self.assertEqual(job['score'], ranking[job['job_id']])
        job_b = next(j for j in load('disputed')['report']['presentation']['jobs'] if j['job_id'] == 'job-b')
        self.assertFalse(job_b['rows'][0]['mandatory_applied_to_score'])

    def test_profile_or_conditions_error_does_not_make_the_run_incomplete(self):
        report = copy.deepcopy(load('normal')['report'])
        report['errors'] = [{'job_id': None, 'code': 'model_invalid', 'stage': 'profile', 'type': 'ValueError'},
                            {'job_id': 'job-001', 'code': 'model_invalid', 'stage': 'conditions',
                             'type': 'ValueError'}]
        queue = build_review_queue(report)
        self.assertNotIn('processing_error', queue.by_reason)
        self.assertIn((None, 'profile_review'), reasons(report))
        self.assertIn(('conditions', 'condition_review'), reasons(report, 'job-001'))
        self.assertTrue(assess_handoff(report, [], 'job-001').processing_complete)

    def test_report_without_run_id_is_never_handed_off(self):
        report = copy.deepcopy(load('normal')['report'])
        del report['run_id']
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-001')
        versions = current_versions(report, job)
        decisions = [{'decision_id': f'd{n}', 'job_id': 'job-001', 'item_id': None, 'action': action, **versions,
                      'decided_by': 'recruiter', 'recorded_by': 'service', 'decided_at': 't'}
                     for n, action in enumerate(('confirm_requirements', 'mark_for_handoff'))]
        result = assess_handoff(report, decisions, 'job-001')
        self.assertEqual(result.state, 'draft')
        self.assertIn('run_unbound', {i.code for i in result.reasons})
        report['run_id'] = 'run-x'
        decisions = [{**d, **current_versions(report, job)} for d in decisions]
        self.assertEqual(assess_handoff(report, decisions, 'job-001').state, 'reviewed_for_handoff')


class HazardTests(unittest.TestCase):
    def test_stripping_markers_and_passing_evidence_hides_the_correction(self):
        # Contract: pass the ORIGINAL requirements. Stripping markers as the v1 pipeline does and also passing
        # evidence gives the same numbers but loses excluded_mandatory_ids, so views would show the marker applied.
        job = next(j for j in load('disputed')['report']['ranking']['jobs'] if j['job_id'] == 'job-b')
        original = Requirements.model_validate(job['requirements'])
        stripped = Requirements(items=[r.model_copy(update={'mandatory_quote': None}) for r in original.items])
        ev, evidence = Evaluation.model_validate(job['evaluation']), PairCheck.model_validate(job['evidence_check'])
        right, twice = score(original, ev, evidence), score(stripped, ev, evidence)
        self.assertEqual((right['lower'], right['mandatory']), (twice['lower'], twice['mandatory']))
        self.assertEqual((right['excluded_mandatory_ids'], twice['excluded_mandatory_ids']), (['r1'], []))

    def test_profile_change_makes_profile_decisions_stale(self):
        report = load('disputed')['report']
        item = next(i.id for i in build_review_queue(report).items if i.reason_code == 'profile_review')
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-b')
        read = {'decision_id': 'p1', 'job_id': 'job-b', 'item_id': item, 'action': 'read_context',
                **current_versions(report, job), 'decided_by': 'recruiter', 'recorded_by': 'service',
                'decided_at': 't'}
        self.assertIn(item, assess_handoff(report, [read], 'job-b').acknowledged)
        changed = copy.deepcopy(report)
        changed['profile']['display']['summary[0]'] = 'другое'
        self.assertNotEqual(report_sha256(changed), report_sha256(report))
        self.assertEqual(assess_handoff(changed, [read], 'job-b').state, 'stale')


if __name__ == '__main__':
    unittest.main()
