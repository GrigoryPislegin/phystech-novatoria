"""E7 what-if: one open requirement resolved hypothetically. Synthetic reports only."""
import asyncio
import copy
import unittest

from prototype.contracts import Evaluation, Requirements
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.evidence import PairCheck
from prototype.pipeline import run_pipeline
from prototype.scoring import rank, score
from prototype.what_if import what_if, what_if_options


def demo(scenario='success', model=None):
    return asyncio.run(run_pipeline(*demo_inputs(scenario), model or ReplayModel(), SyntheticPrivacy()))


class Fragment(ReplayModel):
    """The Python fact quotes one word, so E3 sends job-001 r1 to review (a disputed full)."""

    async def ask(self, schema, task, payload):
        result = await super().ask(schema, task, payload)
        if task == 'facts':
            result.items[0].quote = 'Python'
            result.profile.summary[0].text = 'Python'
            result.profile.summary[0].sources[0].quote = 'Python'
        return result


def as_v1(report):
    """An explicit v1 report: scores without evidence, unbound markers stripped (historical pipeline)."""
    for job in report['ranking']['jobs']:
        reqs = Requirements.model_validate(job['requirements'])
        excluded = set(job['score_review']['excluded_mandatory_ids'])
        stripped = Requirements(items=[r.model_copy(update={'mandatory_quote': None}) if r.id in excluded else r
                                       for r in reqs.items])
        job['score'] = score(stripped, Evaluation.model_validate(job['evaluation']))
    report['ranking'] = rank(report['ranking']['jobs'], len(report['ranking']['jobs']))
    return report


def twin(report, job_id, src, status, new='rX'):
    """Add a literal repeat of row `src` with `status` to one job, rescore it and re-rank the run."""
    jobs = report['ranking']['jobs']
    job = next(j for j in jobs if j['job_id'] == job_id)
    req = next(r for r in job['requirements']['items'] if r['id'] == src)
    job['requirements']['items'].append({**req, 'id': new})
    row = next(r for r in job['evaluation']['rows'] if r['requirement_id'] == src)
    job['evaluation']['rows'].append({**row, 'requirement_id': new, 'status': status})
    check = job['evidence_check']
    c = next(r for r in check['rows'] if r['requirement_id'] == src)
    check['rows'].append({**c, 'requirement_id': new, 'status': status,
                          'state': 'no_evidence' if status == 'unknown' else c['state'],
                          'evidence': [] if status == 'unknown' else c['evidence']})
    check['mandatory'] += [{**m, 'requirement_id': new} for m in check['mandatory'] if m['requirement_id'] == src]
    job['score'] = score(Requirements.model_validate(job['requirements']), Evaluation.model_validate(job['evaluation']),
                         PairCheck.model_validate(check))
    report['ranking'] = rank(jobs, len(jobs))
    return report


def resolved(job, ids, status):
    """Independent rescoring of one job with rows `ids` confirmed as `status`."""
    ev = Evaluation.model_validate(job['evaluation'])
    ev.rows = [r.model_copy(update={'status': status}) if r.requirement_id in ids else r for r in ev.rows]
    evidence = PairCheck.model_validate(job['evidence_check'])
    evidence.rows = [r.model_copy(update={'status': status, 'state': 'structure_ok'}) if r.requirement_id in ids else r
                     for r in evidence.rows]
    return score(Requirements.model_validate(job['requirements']), ev, evidence)


class WhatIfTests(unittest.TestCase):
    def test_only_open_rows_are_offered(self):
        report = demo()
        self.assertEqual([(o.job_id, o.requirement_id, o.status, o.disputed) for o in what_if_options(report)],
                         [('job-002', 'r1', 'unknown', False)])
        with self.assertRaisesRegex(ValueError, 'not_open'):
            what_if(report, 'job-003', 'r1', 'full')  # a verified fail is a claim to review, not a what-if

    def test_unknown_mandatory_resolved_as_full_moves_the_job_up(self):
        w = what_if(demo(), 'job-002', 'r1', 'full')
        self.assertEqual((w.baseline.places['job-002'], w.alternative.places['job-002']), (2, 1))
        self.assertEqual(w.affected_ids, ['job-002'])  # job-001 keeps place 1, now shared
        self.assertEqual((w.baseline.job_score.mandatory, w.alternative.job_score.mandatory), ('clarify', 'confirmed'))
        self.assertEqual(w.kind, 'hypothetical')
        self.assertIn('не ответ кандидата', w.summary)

    def test_resolved_as_fail_moves_others(self):
        w = what_if(demo(), 'job-002', 'r1', 'fail')
        self.assertEqual(w.alternative.job_score.mandatory, 'violated')
        self.assertEqual(w.affected_ids, ['job-003'])
        self.assertEqual((w.baseline.places['job-003'], w.alternative.places['job-003']), (3, 2))

    def test_recommendation_change_is_reported(self):
        w = what_if(demo('disputed'), 'job-002', 'r1', 'full')
        self.assertEqual((w.baseline.recommendation, w.alternative.recommendation), ('clarify', 'review_top'))
        self.assertEqual(w.affected_ids, ['job-001', 'job-002'])
        self.assertIn('Рекомендация: clarify → review_top', w.summary)

    def test_disputed_row_can_be_confirmed(self):
        report = demo(model=Fragment())
        options = {(o.job_id, o.requirement_id): o for o in what_if_options(report)}
        self.assertTrue(options[('job-001', 'r1')].disputed)
        w = what_if(report, 'job-001', 'r1', 'full')
        self.assertTrue(w.assumption.from_disputed)
        self.assertGreater(w.alternative.job_score.lower, w.baseline.job_score.lower)

    def test_alternative_uses_the_same_formula(self):
        report = demo()
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-002')
        ev = Evaluation.model_validate(job['evaluation'])
        ev.rows[0] = ev.rows[0].model_copy(update={'status': 'full'})
        evidence = PairCheck.model_validate(job['evidence_check'])
        evidence.rows[0] = evidence.rows[0].model_copy(update={'status': 'full', 'state': 'structure_ok'})
        expected = score(Requirements.model_validate(job['requirements']), ev, evidence)
        got = what_if(report, 'job-002', 'r1', 'full').alternative.job_score
        self.assertEqual((got.lower, got.upper, got.coverage, got.mandatory),
                         (expected['lower'], expected['upper'], expected['coverage'], expected['mandatory']))

    def test_report_and_decisions_are_untouched(self):
        report = demo()
        report['run_id'] = 'run-x'
        before = copy.deepcopy(report)
        what_if(report, 'job-002', 'r1', 'full')
        self.assertEqual(report, before)

    def test_incomplete_run_stays_incomplete(self):
        report = demo()
        report['ranking']['jobs'] = [j for j in report['ranking']['jobs'] if j['job_id'] != 'job-003']
        report['unprocessed'] = [{'job_id': 'job-003', 'reason': 'model_invalid'}]
        report['ranking']['recommendation'] = 'incomplete'
        w = what_if(report, 'job-002', 'r1', 'full')
        self.assertEqual(w.alternative.recommendation, 'incomplete')
        self.assertIn('incomplete_run', w.caveats)
        self.assertNotIn('job-003', w.alternative.places)

    def test_shared_places_are_named(self):
        w = what_if(demo(), 'job-002', 'r1', 'full')
        self.assertIn('Место job-002: 2 → 1 (общее с job-001)', w.summary)
        w = what_if(demo(), 'job-002', 'r1', 'fail')
        self.assertIn('Место job-002 не меняется: 2 (общее с job-003)', w.summary)

    def test_every_job_and_the_ranking_must_reproduce(self):
        for name, change, code in [
                ('other score', lambda r: r['ranking']['jobs'][2]['score'].update(lower=42.0),
                 'score_not_reproducible'),
                ('other policy', lambda r: r['ranking']['jobs'][2]['score'].update(policy_version='old'),
                 'policy_mismatch'),
                ('rank', lambda r: r['ranking']['jobs'][2].update(rank=2), 'ranking_not_reproducible'),
                ('recommendation', lambda r: r['ranking'].update(recommendation='clarify'),
                 'ranking_not_reproducible'),
                ('no evaluation', lambda r: r['ranking']['jobs'][0].pop('evaluation'), 'incomplete_report')]:
            report = demo()
            change(report)
            with self.subTest(name), self.assertRaisesRegex(ValueError, code):
                what_if(report, 'job-002', 'r1', 'full')

    def test_report_marked_incomplete_without_unprocessed_list_stays_incomplete(self):
        report = demo()
        report['ranking']['jobs'] = [j for j in report['ranking']['jobs'] if j['job_id'] != 'job-003']
        report.pop('unprocessed')
        report['ranking'].update(complete=False, recommendation='incomplete')
        w = what_if(report, 'job-002', 'r1', 'full')
        self.assertEqual(w.alternative.recommendation, 'incomplete')
        self.assertIn('incomplete_run', w.caveats)

    def test_v1_report_is_supported(self):
        report = as_v1(demo(model=Fragment()))
        self.assertFalse(report['ranking']['jobs'][0]['score']['evidence_applied'])
        option = next(o for o in what_if_options(report) if o.job_id == 'job-001')
        self.assertTrue(option.disputed)
        w = what_if(report, 'job-001', 'r1', 'fail')
        self.assertEqual(w.alternative.job_score.mandatory, 'violated')

    def test_one_policy_names_the_projection(self):
        report = demo()
        policy = report['ranking']['jobs'][0]['score']['policy_version']
        self.assertEqual(what_if(report, 'job-002', 'r1', 'full').policy_version, policy)
        other = demo()
        other['policy_version'] = 'draft-other'  # the jobs agree, the report names another policy
        with self.assertRaisesRegex(ValueError, 'policy_mismatch'):
            what_if(other, 'job-002', 'r1', 'full')
        with self.assertRaisesRegex(ValueError, 'policy_mismatch'):
            what_if_options(other)
        # Two known policies in one report: UnitTests.test_known_policies_are_not_mixed (needs v3).

    def test_empty_or_ambiguous_ranking(self):
        report = demo()
        report['unprocessed'] = [{'job_id': j['job_id'], 'reason': 'model_invalid'} for j in report['ranking']['jobs']]
        report['ranking'] = rank([], 3)
        self.assertEqual(what_if_options(report), [])
        twice = demo()
        twice['ranking']['jobs'].append(copy.deepcopy(twice['ranking']['jobs'][0]))
        for call in (lambda: what_if_options(twice), lambda: what_if(twice, 'job-002', 'r1', 'full')):
            with self.assertRaisesRegex(ValueError, 'incomplete_report'):
                call()

    def test_bad_questions_are_refused(self):
        report = demo()
        cases = [(('job-404', 'r1', 'full'), 'unknown_job'), (('job-002', 'r9', 'full'), 'unknown_requirement'),
                 (('job-002', 'r1', 'unknown'), 'invalid_status'), (('job-002', 'r1', 'maybe'), 'invalid_status')]
        for args, code in cases:
            with self.subTest(code), self.assertRaisesRegex(ValueError, code):
                what_if(report, *args)
        tampered = copy.deepcopy(report)
        tampered['ranking']['jobs'][1]['score']['lower'] = 42
        with self.assertRaisesRegex(ValueError, 'score_not_reproducible'):
            what_if(tampered, 'job-002', 'r1', 'full')


class UnitTests(unittest.TestCase):
    """Policies with requirement units (v3): a repeat is one question, a conflict is an open one."""

    def setUp(self):
        if 'units' not in demo()['ranking']['jobs'][0]['score']:
            self.skipTest('the scoring policy has no requirement units')

    def test_conflicting_repeats_are_offered_once_and_resolved_together(self):
        report = twin(demo(), 'job-001', 'r1', 'fail')
        job = report['ranking']['jobs'][0]
        self.assertEqual(job['score']['conflict_ids'], ['r1', 'rX'])
        option = next(o for o in what_if_options(report) if o.job_id == 'job-001')
        self.assertEqual((option.requirement_ids, option.status), (['r1', 'rX'], 'conflict'))
        for status in ('full', 'fail'):
            expected = resolved(job, ['r1', 'rX'], status)
            for asked in ('r1', 'rX'):
                with self.subTest(status=status, asked=asked):
                    w = what_if(report, 'job-001', asked, status)
                    self.assertEqual((w.assumption.from_status, w.assumption.requirement_ids), ('conflict', ['r1', 'rX']))
                    self.assertEqual((w.alternative.job_score.lower, w.alternative.job_score.upper),
                                     (expected['lower'], expected['upper']))
                    self.assertIn('противоречат друг другу', w.summary)
        self.assertGreater(what_if(report, 'job-001', 'rX', 'full').alternative.job_score.lower,
                           job['score']['lower'])

    def test_a_repeat_without_data_does_not_reopen_a_settled_unit(self):
        report = twin(demo(), 'job-001', 'r1', 'unknown')  # r1 confirmed full, its repeat rX has no data
        job = report['ranking']['jobs'][0]
        self.assertEqual(next(u['state'] for u in job['score']['units'] if 'rX' in u['ids']), 'full')
        self.assertEqual([o for o in what_if_options(report) if o.job_id == 'job-001'], [])
        for asked in ('r1', 'rX'):
            with self.subTest(asked), self.assertRaisesRegex(ValueError, 'not_open'):
                what_if(report, 'job-001', asked, 'fail')

    def test_disputed_repeats_that_disagree_are_a_conflict(self):
        report = twin(demo(model=Fragment()), 'job-001', 'r1', 'fail')  # both rows sent to review: full and fail
        job = report['ranking']['jobs'][0]
        self.assertEqual(next(u['state'] for u in job['score']['units'] if 'rX' in u['ids']), 'disputed')
        option = next(o for o in what_if_options(report) if o.job_id == 'job-001')
        self.assertEqual((option.requirement_ids, option.status, option.disputed), (['r1', 'rX'], 'conflict', True))
        w = what_if(report, 'job-001', 'r1', 'full')
        self.assertEqual(w.assumption.from_status, 'conflict')
        self.assertIn('противоречат друг другу', w.summary)
        self.assertEqual(w.alternative.job_score.lower, resolved(job, ['r1', 'rX'], 'full')['lower'])

    def test_known_policies_are_not_mixed(self):
        from prototype.scoring import POLICIES, POLICY_VERSION
        report = demo()
        job = report['ranking']['jobs'][2]
        older = next(p for p in POLICIES if p and p != POLICY_VERSION)
        job['score'] = score(Requirements.model_validate(job['requirements']), Evaluation.model_validate(job['evaluation']),
                             PairCheck.model_validate(job['evidence_check']), policy=older)
        with self.assertRaisesRegex(ValueError, 'policy_mismatch'):
            what_if(report, 'job-002', 'r1', 'full')

    def test_repeated_unknown_is_one_question(self):
        report = twin(demo(), 'job-002', 'r1', 'unknown')
        options = [(o.job_id, o.requirement_ids, o.status) for o in what_if_options(report)]
        self.assertEqual(options, [('job-002', ['r1', 'rX'], 'unknown')])
        by_first, by_twin = (what_if(report, 'job-002', rid, 'full') for rid in ('r1', 'rX'))
        self.assertEqual((by_first.alternative, by_first.affected_ids), (by_twin.alternative, by_twin.affected_ids))
        expected = resolved(report['ranking']['jobs'][1], ['r1', 'rX'], 'full')
        self.assertEqual(by_twin.alternative.job_score.lower, expected['lower'])
        self.assertIn('уточняется один раз', by_twin.summary)


if __name__ == '__main__':
    unittest.main()
