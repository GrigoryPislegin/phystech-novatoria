"""E9: the integrated pipeline against the E5/E7/E8 contract. Synthetic fixtures only.

Fixtures are produced by the real run_pipeline with synthetic models (make_e9_contract.py).
Expectations here are written by hand. Regression tests reproduce resolved findings in files
the integrator owns (pipeline.py); all accepted findings now run as normal regressions
(docs/reviews/egor-e9-integration-contract.md).
"""
import asyncio
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from prototype.candidate_profile import CandidateProfile, Conditions
from prototype.contracts import Evaluation, Facts, Requirements, RequirementFactors
from prototype.demo import SyntheticPrivacy
from prototype.pipeline import refresh_derived, run_pipeline, write_report
from prototype.ranking_explanation import compare
from prototype.review_policy import assess_handoff, report_sha256
from prototype.review_queue import build_review_queue
from prototype.scoring import POLICY_VERSION

ROOT = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'


def load(name):
    return json.loads((ROOT / f'e9-contract-{name}.json').read_text(encoding='utf-8'))['report']


def generator():
    spec = importlib.util.spec_from_file_location('make_e9_contract', ROOT / 'make_e9_contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reasons(report, job_id=None):
    return {(i.requirement_id or i.condition_kind, i.reason_code) for i in build_review_queue(report).items
            if i.job_id == job_id}


def job(report, job_id):
    return next(j for j in report['ranking']['jobs'] if j['job_id'] == job_id)


def markdown(report):
    with tempfile.TemporaryDirectory() as out:
        return (write_report({**report, 'events': []}, Path(out)) / 'report.md').read_text(encoding='utf-8')


def section(text, job_id):
    """The `## N. job` block of report.md."""
    return next(part for part in text.split('\n## ')[1:] if part.splitlines()[0].endswith(f'` {job_id} `'))


class ShapeTests(unittest.TestCase):
    def test_fields_and_versions(self):
        for name in ('normal', 'disputed', 'incomplete'):
            report = load(name)
            with self.subTest(name):
                self.assertEqual(report['profile']['schema_version'], 'candidate-profile-0.1')
                self.assertLessEqual({'state', 'findings', 'spans', 'display'}, set(report['profile']))
                for j in report['ranking']['jobs']:
                    self.assertEqual(j['score']['policy_version'], POLICY_VERSION)
                    self.assertTrue(j['score']['evidence_applied'])
                    self.assertEqual(j['score_review']['excluded_mandatory_ids'], j['score']['excluded_mandatory_ids'])
                    self.assertLessEqual({'items', 'findings', 'conflicts', 'needs_review', 'has_invalid'},
                                         set(j['conditions']))

    def test_derived_views_follow_the_report(self):
        for name in ('normal', 'disputed', 'incomplete'):
            report = load(name)
            with self.subTest(name):
                self.assertEqual(report['review_queue'], build_review_queue(report).model_dump())
                self.assertEqual(report['handoff'], [assess_handoff(report, [], j['job_id']).model_dump()
                                                     for j in report['ranking']['jobs']])
                top = report['ranking']['jobs'][0]['job_id']
                comparisons = [compare(report, top, j['job_id']).model_dump() for j in report['ranking']['jobs'][1:]]
                for stored, current in zip(report['comparisons'], comparisons, strict=True):
                    # The persisted E9 fixtures predate optional scores for the hypothetical row.
                    for old_swing, new_swing in zip(stored['swings'], current['swings'], strict=True):
                        if 'hypothetical_score' not in old_swing:
                            del new_swing['hypothetical_score']
                    self.assertEqual(stored, current)
                scores = {j['job_id']: j['score'] for j in report['ranking']['jobs']}
                for view in report['presentation']['jobs']:
                    self.assertEqual(view['score'], scores[view['job_id']])

    def test_wire_dtos_pass_the_sdk_strict_conversion(self):
        try:
            from openai.lib._pydantic import to_strict_json_schema
        except ImportError:
            self.skipTest('openai SDK not installed')
        from prototype.analysis_contracts import ResumeAnalysis, VacancyAnalysis
        for model in (Requirements, Facts, Evaluation, RequirementFactors, CandidateProfile, Conditions,
                      ResumeAnalysis, VacancyAnalysis):
            with self.subTest(model.__name__):
                schema = to_strict_json_schema(model)
                for node in [schema, *schema.get('$defs', {}).values()]:
                    if 'properties' in node:
                        self.assertIs(node.get('additionalProperties'), False)
                        self.assertEqual(set(node.get('required', [])), set(node['properties']))


class ScenarioTests(unittest.TestCase):
    def test_normal(self):
        report = load('normal')
        self.assertEqual(report['ranking']['recommendation'], 'review_top')
        self.assertNotIn((None, 'profile_review'), reasons(report))
        self.assertEqual(reasons(report, 'job-003'), {('r1', 'mandatory_fail'), (None, 'requirements_unconfirmed')})

    def test_disputed(self):
        report = load('disputed')
        self.assertEqual(report['ranking']['recommendation'], 'clarify')
        self.assertEqual(report['profile']['state'], 'needs_review')
        self.assertIn((None, 'profile_review'), reasons(report))
        self.assertLessEqual({('r1', 'ambiguous_location'), ('work_mode', 'condition_conflict'),
                              ('salary', 'condition_review')}, reasons(report, 'job-a'))
        self.assertEqual((job(report, 'job-a')['score']['lower'], job(report, 'job-a')['score']['disputed_ids']),
                         (25.0, ['r1']))
        self.assertEqual(job(report, 'job-b')['score']['excluded_mandatory_ids'], ['r1'])
        self.assertEqual(assess_handoff(report, [], 'job-a').state, 'blocked')

    def test_incomplete(self):
        report = load('incomplete')
        self.assertEqual(report['ranking']['recommendation'], 'incomplete')
        self.assertIn('incomplete_run', report['comparisons'][0]['caveats'])
        self.assertEqual({h['state'] for h in report['handoff']}, {'blocked'})

    def test_pipeline_output_without_run_id_is_never_handed_off(self):
        # The run store must stamp run_id and call refresh_derived; until then handoff stays closed.
        report = copy.deepcopy(load('normal'))
        del report['run_id']
        refresh_derived(report)
        self.assertTrue(all('run_unbound' in {i['code'] for i in h['reasons']} for h in report['handoff']))

    def test_profile_and_missing_sections_are_in_the_report_version(self):
        report = load('disputed')
        for field, value in (('profile_missing', []), ('profile', None)):
            changed = copy.deepcopy(report)
            changed[field] = value
            self.assertNotEqual(report_sha256(changed), report_sha256(report), field)


class SkillListModel:
    """E9c repro: a CV skill list makes the matching row disputed (heading_context)."""
    CV = 'Навыки:\n- Python 5 лет\nРаботал в команде из 5 человек.'
    JOBS = [('job-a', 'Python обязателен.'), ('job-b', 'Опыт работы в команде.')]

    async def ask(self, schema, task, payload):
        if task == 'facts':
            facts = [{'id': 'f1', 'text': 'Python', 'quote': 'Python 5 лет'},
                     {'id': 'f2', 'text': 'команда', 'quote': 'Работал в команде из 5 человек.'}]
            empty = {'summary': [], 'stack': [], 'last_position': None, 'achievements': [],
                     'missing': ['summary', 'stack', 'last_position', 'achievements']}
            return schema.model_validate({'items': facts, 'profile': empty})
        if task == 'requirements':
            text = payload['text']
            return Requirements(items=[{'id': 'r1', 'text': text, 'quote': text,
                                        'mandatory_quote': text if 'обязателен' in text else None}])
        fact = 'f1' if 'Python' in payload['requirements']['items'][0]['quote'] else 'f2'
        row = {'requirement_id': 'r1', 'status': 'full', 'fact_ids': [fact], 'comment': 'c', 'question': None}
        return schema.model_validate({'rows': [row], 'conditions': {'items': []}})


class E9cFindingTests(unittest.TestCase):
    def test_top_stays_open_while_a_doubted_lower_job_could_reach_it(self):
        report = asyncio.run(run_pipeline(SkillListModel.CV, SkillListModel.JOBS, SkillListModel(),
                                          SyntheticPrivacy()))
        places = {j['job_id']: (j['rank'], j['score']['disputed_ids']) for j in report['ranking']['jobs']}
        self.assertEqual(places, {'job-b': (1, []), 'job-a': (2, ['r1'])})
        self.assertEqual(report['ranking']['recommendation'], 'clarify')  # was review_top

    def test_p2_clarify_action_names_the_real_cause(self):
        # Top job-a: both rows full, one disputed. report.md tells the recruiter to check «выявленные
        # несоответствия», but there is no fail; the cause is the disputed evidence (pipeline.py:234-239).
        head = markdown(load('disputed')).split('\n## ', 1)[0]
        self.assertNotIn('выявленные несоответствия', head.lower())


class IntegrationFindingTests(unittest.TestCase):
    """Reproductions of findings in pipeline.py (owned by the integrator). See the contract doc."""

    def test_p1_invalid_profile_does_not_lose_the_ranking(self):
        gen = generator()
        invented = copy.deepcopy(gen.DISPUTED_PROFILE)
        invented['summary'][0]['text'] = 'SQL 5 лет'  # a number not in «SQL 2 года.»
        report = asyncio.run(run_pipeline(gen.CV, gen.JOBS, gen.DisputedModel(profile=invented), SyntheticPrivacy()))
        self.assertEqual(len(report['ranking']['jobs']), 2)  # today: 0, the whole run fails at facts_validation
        self.assertEqual(report['profile']['state'], 'invalid')

    def test_p1_invalid_conditions_do_not_drop_the_vacancy(self):
        gen = generator()
        broken = copy.deepcopy(gen.JOB_A_CONDITIONS)
        broken['items'][0]['vacancy_quote'] = 'Офис в Москве.'  # not in the vacancy text
        report = asyncio.run(run_pipeline(gen.CV, gen.JOBS, gen.DisputedModel(job_a_conditions=broken),
                                          SyntheticPrivacy()))
        self.assertIn('job-a', [j['job_id'] for j in report['ranking']['jobs']])  # today: job-a is unprocessed

    def test_p1_report_md_does_not_list_a_disputed_full_as_strength(self):
        text = section(markdown(load('disputed')), 'job-a')
        strengths = next(line for line in text.splitlines() if line.startswith('Сильные стороны'))
        self.assertNotIn('Python', strengths)  # «Python» stands under both «Работал с:» and «Не работал с:»

    def test_p2_report_md_does_not_list_a_disputed_fail_as_identified_mismatch(self):
        text = section(markdown(load('disputed')), 'job-b')
        mismatches = next(line for line in text.splitlines() if line.startswith('Выявленные несоответствия'))
        self.assertNotIn('Python', mismatches)  # the «evidence» is «SQL 2 года.»

    def test_p2_report_md_shows_condition_conflicts(self):
        self.assertIn('Рассматриваю только удалённую работу', section(markdown(load('disputed')), 'job-a'))


if __name__ == '__main__':
    unittest.main()
