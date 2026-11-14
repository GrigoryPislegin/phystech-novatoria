"""E8a: review queue over a finished report. Synthetic fixtures only."""
import asyncio
import copy
import importlib.util
import json
import random
import unittest
from pathlib import Path
from typing import get_args

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline
from prototype.review_queue import INTEGRATED, REASONS, ReasonCode, build_review_queue

ROOT = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'
KEYS = ('job_id', 'requirement_id', 'condition_kind', 'reason_code', 'priority', 'action')


def generator():
    spec = importlib.util.spec_from_file_location('make_e8_fixtures', ROOT / 'make_e8_fixtures.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(name):
    return json.loads((ROOT / f'e8-queue-{name}.json').read_text(encoding='utf-8'))


def summary(queue):
    return [{k: getattr(i, k) for k in KEYS} for i in queue.items]


def reasons(queue, job_id=None):
    return {(i.requirement_id or i.condition_kind, i.reason_code) for i in queue.items if i.job_id == job_id}


class FixtureTests(unittest.TestCase):
    def test_fixtures_give_the_recorded_queue(self):
        for name in ('normal', 'disputed'):
            with self.subTest(name):
                data = fixture(name)
                queue = build_review_queue(data['report'])
                self.assertEqual(summary(queue), data['expected'])
                self.assertEqual(queue.by_priority, data['by_priority'])
                self.assertEqual(queue.model_status, 'model_proposed')

    def test_normal_report_has_no_integrity_or_condition_items(self):
        queue = build_review_queue(fixture('normal')['report'])
        self.assertEqual({i.priority for i in queue.items}, {2, 4})
        self.assertEqual([(i.job_id, i.reason_code) for i in queue.items if i.priority == 2],
                         [('job-003', 'mandatory_fail')])

    def test_clean_report_gets_no_urgent_items(self):
        resume, jobs = demo_inputs('success')
        report = asyncio.run(run_pipeline(resume, jobs[:1], ReplayModel(), SyntheticPrivacy()))
        queue = build_review_queue(report)
        self.assertEqual({i.reason_code for i in queue.items}, {'requirements_unconfirmed'})
        self.assertEqual(queue.model_status, 'model_proposed')


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.report = fixture('disputed')['report']
        self.queue = build_review_queue(self.report)

    def item(self, job_id, reason):
        return next(i for i in self.queue.items if i.job_id == job_id and i.reason_code == reason)

    def test_opposite_contexts_are_an_ambiguity_not_a_match(self):
        item = self.item('job-a', 'ambiguous_location')
        self.assertEqual(item.priority, 1)
        self.assertTrue(any('Не работал с' in c for c in item.contexts))
        self.assertTrue(any(c.startswith('Работал с') for c in item.contexts))

    def test_privacy_loss_is_not_absence_of_skill(self):
        self.assertIn((None, 'privacy_may_hide'), reasons(self.queue))
        self.assertEqual(reasons(self.queue, 'job-c'),
                         {('r1', 'mandatory_unknown'), (None, 'requirements_unconfirmed')})
        row = self.report['ranking']['jobs'][[j['job_id'] for j in self.report['ranking']['jobs']].index('job-c')]
        self.assertEqual(row['evaluation']['rows'][0]['status'], 'unknown')

    def test_unbound_marker_and_disputed_negative_are_separate_items(self):
        self.assertEqual(reasons(self.queue, 'job-b'),
                         {('r1', 'mandatory_unbound'), ('r1', 'disputed_negative'), (None, 'requirements_unconfirmed')})

    def test_incomplete_run_is_not_a_final_verdict(self):
        self.assertEqual(self.report['ranking']['recommendation'], 'incomplete')
        self.assertIn((None, 'incomplete_run'), reasons(self.queue))
        self.assertEqual(self.item('job-d', 'processing_error').priority, 1)

    def test_condition_conflict_shows_both_sides(self):
        item = self.item('job-a', 'condition_conflict')
        self.assertEqual((item.priority, item.action), (3, 'decide_condition'))
        self.assertEqual({r.source for r in item.refs}, {'cv', 'vacancy'})

    def test_stale_or_foreign_confirmation_is_integrity(self):
        report = copy.deepcopy(self.report)
        job = report['ranking']['jobs'][0]
        job['requirements_review'] = {'vacancy_id': job['job_id'], 'state': 'stale',
                                      'reasons': [{'code': 'mandatory_changed', 'message': 'm',
                                                   'requirement_id': 'r1'}]}
        report['ranking']['jobs'][1]['requirements_review']['vacancy_id'] = 'someone-else'
        queue = build_review_queue(report)
        stale = [i for i in queue.items if i.reason_code == 'requirements_stale']
        self.assertEqual({i.job_id for i in stale}, {job['job_id'], report['ranking']['jobs'][1]['job_id']})
        self.assertTrue(all(i.priority == 1 for i in stale))

    def test_invalid_evidence_is_integrity(self):
        report = copy.deepcopy(self.report)
        report['ranking']['jobs'][0]['evidence_check']['rows'][0]['state'] = 'invalid'
        item = next(i for i in build_review_queue(report).items if i.reason_code == 'invalid_evidence')
        self.assertEqual((item.priority, item.action), (1, 'fix_source'))

    def test_two_signals_of_one_item_merge_their_sources(self):
        report = copy.deepcopy(self.report)
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-a')
        job['evidence_check']['rows'][0]['state'] = 'invalid'
        job['evidence_check']['mandatory'][0]['state'] = 'invalid'
        items = [i for i in build_review_queue(report).items if i.reason_code == 'invalid_evidence']
        self.assertEqual(len(items), 1)
        # requirement quote and fact quote from the row (no E3 span for an ambiguous quote), then the marker
        # with its sentence from the mandatory check
        self.assertEqual([(r.source, r.sentence is None) for r in items[0].refs],
                         [('vacancy', True), ('cv', True), ('vacancy', False)])
        self.assertEqual(set(items[0].detail_codes), {'ambiguous_location'})

    def test_references_are_not_invented(self):
        from prototype.evidence import Source, locate
        gen = generator()
        texts = {'cv': gen.CV, **dict(gen.JOBS)}
        for item in self.queue.items:
            for ref in item.refs:
                text = texts['cv' if ref.source == 'cv' else item.job_id]
                with self.subTest(item=item.reason_code, quote=ref.quote):
                    self.assertIn(ref.quote, text)
                    if ref.sentence is not None and ref.source == 'cv':
                        span = locate(Source.of('cv', text), ref.quote).span
                        self.assertEqual((span.sentence, span.heading), (ref.sentence, ref.heading))


class EdgeTests(unittest.TestCase):
    def job(self, report, job_id):
        return next(j for j in report['ranking']['jobs'] if j['job_id'] == job_id)

    def test_bulleted_full_mandatory_is_not_a_negative(self):
        report = copy.deepcopy(fixture('normal')['report'])
        row = self.job(report, 'job-001')['evidence_check']['rows'][0]
        row['state'] = 'needs_review'
        row['reasons'] = [{'code': 'heading_context', 'severity': 'review', 'message': 'm', 'fact_id': 'f1',
                           'context': 'Навыки: → Python'}]
        queue = build_review_queue(report)
        self.assertEqual(reasons(queue, 'job-001') - {(None, 'requirements_unconfirmed')},
                         {('r1', 'disputed_evidence')})
        self.assertNotIn('disputed_negative', queue.by_reason)

    def test_v2_disputed_ids_are_read(self):
        report = copy.deepcopy(fixture('normal')['report'])
        self.job(report, 'job-003')['score']['disputed_ids'] = ['r1']
        self.assertIn(('r1', 'disputed_negative'), reasons(build_review_queue(report), 'job-003'))

    def test_job_without_evidence_check_keeps_mandatory_signals(self):
        report = copy.deepcopy(fixture('normal')['report'])
        for job in report['ranking']['jobs']:
            del job['evidence_check']
        queue = build_review_queue(report)
        self.assertIn(('r1', 'mandatory_fail'), reasons(queue, 'job-003'))
        self.assertIn(('r1', 'mandatory_unknown'), reasons(queue, 'job-002'))
        item = next(i for i in queue.items if i.reason_code == 'mandatory_fail')
        self.assertIn('evidence_not_checked', item.detail_codes)

    def test_failed_facts_stage_is_an_integrity_item(self):
        report = {'safe_resume_sha256': 'x', 'facts': {'items': []}, 'ranking': {'jobs': [], 'complete': False},
                  'errors': [{'job_id': None, 'code': 'model_invalid', 'stage': 'facts'}],
                  'unprocessed': [{'job_id': 'job-1', 'reason': 'model_invalid'}]}
        queue = build_review_queue(report)
        self.assertEqual({i.reason_code for i in queue.items}, {'processing_error', 'incomplete_run'})
        self.assertIn((None, 'processing_error'), {(i.job_id, i.reason_code) for i in queue.items})
        self.assertTrue(all(i.priority == 1 for i in queue.items))

    def test_row_for_an_unknown_requirement_is_integrity(self):
        report = copy.deepcopy(fixture('normal')['report'])
        self.job(report, 'job-002')['evaluation']['rows'][0]['requirement_id'] = 'r9'
        self.assertIn(('r9', 'invalid_evidence'), reasons(build_review_queue(report), 'job-002'))

    def test_malformed_or_summary_only_conditions_are_not_lost(self):
        report = copy.deepcopy(fixture('disputed')['report'])
        job = self.job(report, 'job-a')
        job['conditions'] = {'items': [{'state': 'conflict'}], 'conflicts': ['location'], 'has_invalid': False}
        queue = build_review_queue(report)
        self.assertIn(('conditions', 'invalid_evidence'), reasons(queue, 'job-a'))
        self.assertIn(('location', 'condition_conflict'), reasons(queue, 'job-a'))

    def test_condition_kind_never_collides_with_a_requirement_id(self):
        report = copy.deepcopy(fixture('disputed')['report'])
        job = self.job(report, 'job-a')
        job['requirements']['items'][1]['id'] = 'work_mode'
        for rows in (job['evaluation']['rows'], job['evidence_check']['rows'], job['evidence_check']['mandatory']):
            rows[1]['requirement_id'] = 'work_mode'
        item = next(i for i in build_review_queue(report).items if i.reason_code == 'condition_conflict')
        self.assertEqual((item.requirement_id, item.condition_kind), (None, 'work_mode'))


class StabilityTests(unittest.TestCase):
    def test_job_order_does_not_change_ids_or_order(self):
        report = fixture('disputed')['report']
        base = build_review_queue(report)
        rng = random.Random(9)
        for _ in range(20):
            shuffled = copy.deepcopy(report)
            rng.shuffle(shuffled['ranking']['jobs'])
            for job in shuffled['ranking']['jobs']:
                rng.shuffle(job['evidence_check']['rows'])
            self.assertEqual(build_review_queue(shuffled), base)

    def test_repeated_signal_gives_one_item(self):
        report = fixture('disputed')['report']
        before = build_review_queue(report)
        doubled = copy.deepcopy(report)
        for job in doubled['ranking']['jobs']:
            job['evidence_check']['rows'] += copy.deepcopy(job['evidence_check']['rows'])
        after = build_review_queue(doubled)
        self.assertEqual([i.id for i in after.items], [i.id for i in before.items])
        self.assertEqual(len({i.id for i in after.items}), len(after.items))

    def test_ids_follow_the_resume(self):
        report = fixture('disputed')['report']
        before = {i.id for i in build_review_queue(report).items}
        other = copy.deepcopy(report)
        other['safe_resume_sha256'] = 'другое резюме'
        self.assertFalse(before & {i.id for i in build_review_queue(other).items})

    def test_ids_follow_the_processed_source(self):
        report = fixture('disputed')['report']
        before = {(i.job_id, i.reason_code): i.id for i in build_review_queue(report).items}
        changed = copy.deepcopy(report)
        changed['ranking']['jobs'][0]['safe_source_sha256'] = 'другой'
        moved = changed['ranking']['jobs'][0]['job_id']
        after = {(i.job_id, i.reason_code): i.id for i in build_review_queue(changed).items}
        for key, item_id in before.items():  # run-scoped ids (incl. unprocessed jobs) cover every source
            run_scoped = key[0] is None or key[1] == 'processing_error'
            self.assertEqual(after[key] == item_id, key[0] != moved and not run_scoped, key)

    def test_report_is_not_modified(self):
        report = fixture('disputed')['report']
        before = copy.deepcopy(report)
        build_review_queue(report)
        self.assertEqual(report, before)


class TableTests(unittest.TestCase):
    def test_every_reason_has_priority_kind_and_action(self):
        self.assertEqual(set(REASONS), set(get_args(ReasonCode)))
        integrity = {r for r, (p, kind, _, _) in REASONS.items() if p == 1}
        self.assertTrue(all(REASONS[r][1] == 'integrity' for r in integrity))
        self.assertEqual(REASONS['condition_conflict'][0], 3)

    def test_verified_partial_mandatory_is_queued(self):
        # E9c: a verified partial on an applied mandatory requirement keeps the group at clarify.
        report = copy.deepcopy(fixture('normal')['report'])
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-001')
        job['evaluation']['rows'][0]['status'] = 'partial'
        job['evidence_check']['rows'][0]['status'] = 'partial'
        self.assertIn(('r1', 'mandatory_partial'), reasons(build_review_queue(report), 'job-001'))

    def test_one_sided_condition_is_queued_as_a_question(self):
        report = copy.deepcopy(fixture('disputed')['report'])
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-a')
        item = job['conditions']['items'][0]
        job['conditions'] = {**job['conditions'], 'conflicts': [],
                             'items': [{**item, 'state': 'unknown', 'check': 'structure_ok', 'findings': [],
                                        'cv_span': None}]}
        queue = build_review_queue(report)
        self.assertIn(('work_mode', 'condition_unknown'),
                      {(i.condition_kind, i.reason_code) for i in queue.items if i.job_id == 'job-a'})

    def test_mandatory_fail_text_does_not_promise_exclusion(self):
        # The engine demotes a violated vacancy to the lower group; HR decides. «исключает вакансию» was wrong.
        text = REASONS['mandatory_fail'][3]
        self.assertNotIn('исключает вакансию', text)
        self.assertIn('решение принимает HR', text)

    def test_integrated(self):
        self.assertTrue(INTEGRATED)


if __name__ == '__main__':
    unittest.main()
