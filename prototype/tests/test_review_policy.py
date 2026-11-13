"""E8b: recruiter decisions and handoff readiness. Synthetic fixtures only."""
import asyncio
import copy
import itertools
import json
import random
import unittest
from pathlib import Path

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline
from typing import get_args

from prototype.review_policy import (BLOCKERS, CLOSED_BY, INTEGRATED, assess_handoff, closing_decision,
                                     current_versions, report_sha256)
from prototype.review_queue import ReasonCode
from prototype.review_queue import build_review_queue

ROOT = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'
_ids = itertools.count(1)


def fixture(name):
    return json.loads((ROOT / f'e8-queue-{name}.json').read_text(encoding='utf-8'))['report']


def job(report, job_id):
    return next(j for j in report['ranking']['jobs'] if j['job_id'] == job_id)


def items(report, job_id, reason=None):
    return [i for i in build_review_queue(report).items
            if i.job_id in (job_id, None) and (reason is None or i.reason_code == reason)]


def decision(report, job_id, action, item_id=None, **override):
    return {'decision_id': f'd{next(_ids)}', 'job_id': job_id, 'item_id': item_id, 'action': action,
            **current_versions(report, job(report, job_id)), 'decided_by': 'recruiter', 'recorded_by': 'service',
            'decided_at': '2026-11-14T01:00:00+03:00', **override}


def close_all(report, job_id):
    """What a recruiter does to hand a vacancy off: confirm the list, read every item, accept conflicts."""
    out = [decision(report, job_id, 'confirm_requirements')]
    for item in items(report, job_id):
        if item.reason_code == 'condition_conflict':
            out.append(decision(report, job_id, 'accept_condition', item.id))
        elif item.reason_code not in {'requirements_unconfirmed', 'uncovered_text'}:
            out.append(decision(report, job_id, 'read_context', item.id))
    return out + [decision(report, job_id, 'mark_for_handoff')]


def clean_report():
    resume, jobs = demo_inputs('success')
    report = asyncio.run(run_pipeline(resume, jobs[:1], ReplayModel(), SyntheticPrivacy()))
    return {**report, 'run_id': 'run-clean'}  # the service stamps every published report


class HandoffTests(unittest.TestCase):
    def test_clean_report_needs_confirmation_and_an_explicit_mark(self):
        report = clean_report()
        self.assertEqual(assess_handoff(report, [], 'job-001').state, 'draft')
        marked = assess_handoff(report, [decision(report, 'job-001', 'mark_for_handoff')], 'job-001')
        self.assertEqual(marked.state, 'draft')  # 1. a complete report with an unconfirmed list is not reviewed
        self.assertIn('marked_without_confirmed_list', {i.code for i in marked.reasons})
        done = assess_handoff(report, close_all(report, 'job-001'), 'job-001')
        self.assertEqual((done.state, done.requirements_confirmed, done.open_items), ('reviewed_for_handoff', True, []))
        self.assertEqual(done.model_status, 'model_proposed')

    def test_everything_closed_but_not_marked_is_a_draft(self):
        report = clean_report()
        unmarked = [d for d in close_all(report, 'job-001') if d['action'] != 'mark_for_handoff']
        result = assess_handoff(report, unmarked, 'job-001')
        self.assertEqual((result.state, result.open_items, result.requirements_confirmed), ('draft', [], True))

    def test_marked_with_an_open_item_is_a_draft(self):
        report = fixture('normal')
        decisions = [decision(report, 'job-002', 'confirm_requirements'),
                     decision(report, 'job-002', 'mark_for_handoff')]
        result = assess_handoff(report, decisions, 'job-002')
        self.assertEqual(result.state, 'draft')
        self.assertEqual(result.open_items, [items(report, 'job-002', 'mandatory_unknown')[0].id])
        self.assertIn('marked_with_open_items', {i.code for i in result.reasons})

    def test_confirmed_list_does_not_close_a_bad_source(self):  # 2 and 7
        report = fixture('disputed')
        result = assess_handoff(report, close_all(report, 'job-a'), 'job-a')
        self.assertEqual(result.state, 'blocked')
        ambiguous = items(report, 'job-a', 'ambiguous_location')[0].id
        self.assertIn(ambiguous, result.blockers)
        self.assertIn('blocker_not_closable', {i.code for i in result.reasons})
        self.assertTrue(result.requirements_confirmed)

    def test_decisions_are_not_inherited(self):  # 3
        report = clean_report()
        ok = close_all(report, 'job-001')
        moved = [dict(d, job_id='job-999') if d['action'] == 'confirm_requirements' else d for d in ok]
        result = assess_handoff(report, moved, 'job-001')  # another vacancy's confirmation does not count here
        self.assertEqual((result.state, result.requirements_confirmed), ('draft', False))
        own_item = items(report, 'job-001')[0].id
        filed_elsewhere = dict(decision(report, 'job-001', 'read_context', own_item), job_id='job-999')
        self.assertEqual(assess_handoff(report, ok + [filed_elsewhere], 'job-001').state, 'invalid')
        old_source = [dict(d, source_sha256='old') for d in ok]
        self.assertEqual(assess_handoff(report, old_source, 'job-001').state, 'stale')
        relaxed = copy.deepcopy(report)
        job(relaxed, 'job-001')['requirements']['items'][0]['mandatory_quote'] = None
        result = assess_handoff(relaxed, ok, 'job-001')
        self.assertEqual(result.state, 'stale')
        self.assertTrue(any(i.code.startswith('stale_') for i in result.reasons))

    def test_another_candidate_does_not_inherit_decisions(self):
        report = clean_report()
        ok = close_all(report, 'job-001')
        other = copy.deepcopy(report)
        other['safe_resume_sha256'] = 'другой кандидат'
        result = assess_handoff(other, ok, 'job-001')
        self.assertEqual(result.state, 'stale')
        self.assertIn('stale_report_sha256', {i.code for i in result.reasons})

    def test_unknown_stays_unknown_after_reading(self):  # 4 and 6
        report = fixture('disputed')
        before = copy.deepcopy(report)
        unknown = items(report, 'job-c', 'mandatory_unknown')[0].id
        result = assess_handoff(report, [decision(report, 'job-c', 'read_context', unknown)], 'job-c')
        self.assertIn(unknown, result.acknowledged)
        self.assertEqual(report, before)
        self.assertEqual(job(report, 'job-c')['evaluation']['rows'][0]['status'], 'unknown')
        privacy = items(report, 'job-c', 'privacy_may_hide')[0].id
        self.assertIn(privacy, result.open_items)

    def test_accepted_condition_stays_visible(self):  # 5
        report = copy.deepcopy(fixture('disputed'))
        conflict = items(report, 'job-a', 'condition_conflict')[0].id
        result = assess_handoff(report, [decision(report, 'job-a', 'accept_condition', conflict)], 'job-a')
        self.assertEqual(result.accepted_exceptions, [conflict])
        self.assertIn(conflict, [i.id for i in build_review_queue(report).items])
        read = assess_handoff(report, [decision(report, 'job-a', 'read_context', conflict)], 'job-a')
        self.assertIn(conflict, read.open_items)  # reading does not accept a conflict
        self.assertIn('wrong_action', {i.code for i in read.reasons})

    def test_identical_clicks_and_job_order_change_nothing(self):  # 8
        report = clean_report()
        ok = close_all(report, 'job-001')
        twice = ok + copy.deepcopy(ok)
        self.assertEqual(assess_handoff(report, twice, 'job-001'), assess_handoff(report, ok, 'job-001'))
        report = fixture('disputed')
        base = assess_handoff(report, close_all(report, 'job-c'), 'job-c')
        shuffled = copy.deepcopy(report)
        random.Random(3).shuffle(shuffled['ranking']['jobs'])
        decisions = close_all(shuffled, 'job-c')
        self.assertEqual(assess_handoff(shuffled, decisions, 'job-c').model_dump(exclude={'reasons'}),
                         base.model_dump(exclude={'reasons'}))

    def test_incomplete_run_is_never_final(self):  # 9
        report = fixture('disputed')
        result = assess_handoff(report, close_all(report, 'job-c'), 'job-c')
        self.assertFalse(result.processing_complete)
        self.assertEqual(result.state, 'blocked')
        missing = assess_handoff(report, [], 'job-d')
        self.assertEqual((missing.state, missing.processing_complete), ('blocked', False))

    def test_report_without_signals_is_not_flooded(self):  # 10
        report = clean_report()
        result = assess_handoff(report, [], 'job-001')
        self.assertEqual(result.blockers, [])
        self.assertEqual(len(result.open_items), 1)  # only the unconfirmed requirement list
        self.assertTrue(result.processing_complete)


class DecisionValidityTests(unittest.TestCase):
    def setUp(self):
        self.report = clean_report()
        self.ok = close_all(self.report, 'job-001')

    def test_reused_id_with_other_content_is_invalid(self):
        clash = dict(self.ok[0], action='mark_for_handoff')
        self.assertEqual(assess_handoff(self.report, self.ok + [clash], 'job-001').state, 'invalid')

    def test_records_not_made_by_the_service_or_recruiter_are_invalid(self):
        for field, value in (('recorded_by', 'client'), ('decided_by', 'model')):
            with self.subTest(field):
                forged = dict(self.ok[-1], **{field: value})
                result = assess_handoff(self.report, self.ok[:-1] + [forged], 'job-001')
                self.assertEqual(result.state, 'invalid')
        result = assess_handoff(self.report, self.ok + [{'action': 'mark_for_handoff'}], 'job-001')
        self.assertEqual(result.state, 'invalid')

    def test_item_from_another_report_is_stale(self):
        ghost = decision(self.report, 'job-001', 'read_context', 'ffffffffffffffff')
        result = assess_handoff(self.report, [ghost], 'job-001')
        self.assertEqual(result.state, 'stale')
        self.assertIn('unknown_item', {i.code for i in result.reasons})

    def test_report_version_ignores_timings_only(self):
        changed = copy.deepcopy(self.report)
        changed['events'] = []
        self.assertEqual(report_sha256(changed), report_sha256(self.report))
        job(changed, 'job-001')['evaluation']['rows'][0]['status'] = 'partial'
        self.assertNotEqual(report_sha256(changed), report_sha256(self.report))
        self.assertEqual(assess_handoff(changed, self.ok, 'job-001').state, 'stale')

    def test_reused_id_across_vacancies_is_invalid_for_both(self):
        report = fixture('normal')
        a = decision(report, 'job-001', 'mark_for_handoff')
        b = dict(decision(report, 'job-002', 'confirm_requirements'), decision_id=a['decision_id'])
        for job_id in ('job-001', 'job-002'):
            self.assertEqual(assess_handoff(report, [a, b], job_id).state, 'invalid')

    def test_other_vacancys_item_filed_here_is_invalid(self):
        report = fixture('normal')
        theirs = items(report, 'job-003', 'mandatory_fail')[0].id
        decisions = close_all(report, 'job-001') + [decision(report, 'job-001', 'read_context', theirs)]
        result = assess_handoff(report, decisions, 'job-001')
        self.assertEqual(result.state, 'invalid')
        self.assertIn('foreign_job', {i.code for i in result.reasons})

    def test_accepted_conflict_survives_a_stray_click_in_any_order(self):
        report = fixture('disputed')
        conflict = items(report, 'job-a', 'condition_conflict')[0].id
        accept = dict(decision(report, 'job-a', 'accept_condition', conflict), decision_id='d10')
        stray = dict(decision(report, 'job-a', 'read_context', conflict), decision_id='d9')
        for order in ([accept, stray], [stray, accept]):
            result = assess_handoff(report, order, 'job-a')
            self.assertEqual(result.accepted_exceptions, [conflict])
            self.assertIn('wrong_action', {i.code for i in result.reasons})

    def test_run_level_item_is_read_without_foreign_error(self):
        report = fixture('disputed')
        privacy = items(report, 'job-c', 'privacy_may_hide')[0].id
        result = assess_handoff(report, [decision(report, 'job-c', 'read_context', privacy)], 'job-c')
        self.assertIn(privacy, result.acknowledged)
        self.assertNotEqual(result.state, 'invalid')

    def test_every_changed_version_is_reported(self):
        stale = [dict(d, resume_sha256='другое', policy_version='draft-old') for d in self.ok]
        codes = {i.code for i in assess_handoff(self.report, stale, 'job-001').reasons}
        self.assertLessEqual({'stale_resume_sha256', 'stale_policy_version'}, codes)
        self.assertNotIn('stale_source_sha256', codes)

    def test_policy_change_alone_makes_decisions_stale(self):
        changed = copy.deepcopy(self.report)
        job(changed, 'job-001')['score']['policy_version'] = 'draft-2026-11-14-v3'
        result = assess_handoff(changed, self.ok, 'job-001')
        self.assertEqual(result.state, 'stale')
        self.assertIn('stale_policy_version', {i.code for i in result.reasons})

    def test_stale_e4_confirmation_blocks_despite_a_confirm_decision(self):
        changed = copy.deepcopy(self.report)
        job(changed, 'job-001')['requirements_review'] = {'vacancy_id': 'job-001', 'state': 'stale', 'reasons': []}
        self.assertEqual(assess_handoff(changed, close_all(changed, 'job-001'), 'job-001').state, 'blocked')

    def test_old_stale_decisions_do_not_spoil_a_current_review(self):
        old = [dict(d, decision_id='old-' + d['decision_id'], source_sha256='old') for d in self.ok]
        self.assertEqual(assess_handoff(self.report, old + self.ok, 'job-001').state, 'reviewed_for_handoff')

    def test_review_layer_and_job_order_do_not_change_the_version(self):
        changed = copy.deepcopy(self.report)
        changed['verification'] = {'final_allowed': True}
        changed['usage'] = [{'input_tokens': 1}]
        job(changed, 'job-001')['requirements_review'] = {'vacancy_id': 'job-001', 'state': 'confirmed', 'reasons': []}
        self.assertEqual(report_sha256(changed), report_sha256(self.report))
        two = fixture('normal')
        swapped = copy.deepcopy(two)
        swapped['ranking']['jobs'].reverse()
        self.assertEqual(report_sha256(swapped), report_sha256(two))

    def test_every_queue_reason_has_a_closing_rule(self):
        for reason in get_args(ReasonCode):
            with self.subTest(reason):
                self.assertNotEqual(reason in BLOCKERS, reason in CLOSED_BY)
                self.assertEqual(closing_decision(reason), None if reason in BLOCKERS else CLOSED_BY[reason])

    def test_hand_written_confirmed_field_confirms_nothing(self):
        # E9 regression: a report edited to say E4 'confirmed' plus a single mark used to be handed off.
        forged = copy.deepcopy(self.report)
        job(forged, 'job-001')['requirements_review'] = {'vacancy_id': 'job-001', 'state': 'confirmed', 'reasons': []}
        self.assertIn('requirements_unconfirmed', {i.reason_code for i in items(forged, 'job-001')})
        result = assess_handoff(forged, [decision(forged, 'job-001', 'mark_for_handoff')], 'job-001')
        self.assertEqual((result.state, result.requirements_confirmed), ('draft', False))
        self.assertIn('report_confirmation_not_trusted', {i.code for i in result.reasons})

    def test_decisions_do_not_cross_runs(self):
        # E9 regression: two replay runs give identical analysis; once the service stamps run_id, a decision
        # from one run is stale in the other.
        first, second = copy.deepcopy(self.report), copy.deepcopy(self.report)
        first['run_id'], second['run_id'] = 'run-a', 'run-b'
        decisions = close_all(first, 'job-001')
        self.assertEqual(assess_handoff(first, decisions, 'job-001').state, 'reviewed_for_handoff')
        result = assess_handoff(second, decisions, 'job-001')
        self.assertEqual(result.state, 'stale')
        self.assertIn('stale_report_sha256', {i.code for i in result.reasons})

    def test_profile_or_missing_sections_change_the_version(self):
        changed = copy.deepcopy(self.report)
        changed['profile_missing'] = ['summary']
        self.assertNotEqual(report_sha256(changed), report_sha256(self.report))
        self.assertEqual(assess_handoff(changed, self.ok, 'job-001').state, 'stale')

    def test_unknown_job_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unknown_job'):
            assess_handoff(self.report, [], 'job-404')

    def test_not_integrated(self):
        self.assertFalse(INTEGRATED)



class DecisionFixtureTests(unittest.TestCase):
    # Written by hand, independently of the generator that recorded the fixture.
    STATES = {'normal-ready': 'reviewed_for_handoff', 'normal-open-unknown': 'draft',
              'normal-unknown-read': 'reviewed_for_handoff', 'disputed-blocked': 'blocked'}

    def test_recorded_decisions_give_the_recorded_assessment(self):
        data = json.loads((ROOT / 'e8-decisions.json').read_text(encoding='utf-8'))
        self.assertEqual({s['scenario'] for s in data['scenarios']}, set(self.STATES))
        for s in data['scenarios']:
            with self.subTest(s['scenario']):
                report = json.loads((ROOT / s['report']).read_text(encoding='utf-8'))['report']
                result = assess_handoff(report, s['decisions'], s['job_id'])
                self.assertEqual(result.state, self.STATES[s['scenario']])
                expected = dict(s['expected'])
                self.assertEqual(sorted({i.code for i in result.reasons}), expected.pop('reason_codes'))
                self.assertEqual(result.model_dump(exclude={'reasons'}), expected)


if __name__ == '__main__':
    unittest.main()
