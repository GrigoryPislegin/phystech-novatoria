"""Policy draft-2026-11-14-v3 (E11): adversarial cases against v2, invariants, explanation and queue.

Synthetic data only. These tests check the policy arithmetic and that the explanation, the queue and
the recommendation follow the same calculation. They do not measure model quality or HR agreement.
"""
import asyncio
import copy
import json
import random
import unittest
from pathlib import Path

from evaluation.policy_compare import DEFAULT_CASES, build_job, compare as compare_policies
from prototype.contracts import Evaluation, Requirements
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.evidence import PairCheck
from prototype.pipeline import run_pipeline
from prototype.ranking_explanation import compare, explain_leader
from prototype.review_policy import assess_handoff, closing_decision, current_versions
from prototype.review_queue import build_review_queue
from prototype.scoring import ANSWERS, CORE_SHARE, POLICY_V2, POLICY_VERSION, rank, score
from prototype.tests.test_scoring_policy import random_job, with_status

CASES = {c['id']: c for c in json.loads(DEFAULT_CASES.read_text(encoding='utf-8'))['cases']}
E9 = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'


def report_of(case, policy=POLICY_VERSION):
    """A minimal report of a policy case: what compare, explain_leader and the queue read."""
    results = []
    for job in case['jobs']:
        reqs, ev, evidence = build_job(job)
        results.append({'job_id': job['job_id'], 'requirements': reqs.model_dump(), 'evaluation': ev.model_dump(),
                        'evidence_check': evidence.model_dump(), 'safe_source_sha256': 'src-' + job['job_id'],
                        'score': score(reqs, ev, evidence, policy=policy)})
    return {'run_id': 'run-1', 'safe_resume_sha256': 'cv', 'ranking': rank(results, len(results)),
            'facts': {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]}}


class AdversarialSetTests(unittest.TestCase):
    """The same inputs under v2 and v3. Expectations are the team's hypotheses, fixed before the run."""

    @classmethod
    def setUpClass(cls):
        cls.result = compare_policies(list(CASES.values()))
        cls.summary = cls.result['summary']

    def test_v3_meets_every_expectation_and_regresses_nowhere(self):
        failed = {r['id']: r['v3']['failed'] for r in self.result['rows'] if r['v3']['failed']}
        self.assertEqual(failed, {})
        self.assertEqual(self.summary['regressed_in_v3'], [])

    def test_the_improvement_over_v2_is_these_cases(self):
        self.assertEqual(self.summary['fixed_by_v3'],
                         ['E11-01', 'E11-02', 'E11-03', 'E11-09', 'E11-10', 'E11-13'])

    def test_stricter_interval_rule_would_be_worse(self):
        # L above every other H: a job nothing is known about keeps every first place open.
        self.assertEqual(self.summary['aggressive_worse_than_v3'], ['E11-14', 'E11-15'])

    def test_known_limit_is_not_reported_as_passed(self):
        self.assertEqual(self.summary['known_limits'], ['E11-05'])
        split = next(r for r in self.result['rows'] if r['id'] == 'E11-05')
        self.assertNotEqual(split['v3']['lower']['split'], split['v3']['lower']['single'])  # still not fixed

    def test_expectations_are_drafts_on_the_dev_split(self):
        data = json.loads(DEFAULT_CASES.read_text(encoding='utf-8'))
        self.assertEqual((data['split'], data['decision_status']), ('dev', 'draft'))
        self.assertTrue(all(c['hypothesis'] and c['covers'] for c in data['cases']))


class GroupShareTests(unittest.TestCase):
    def test_one_mandatory_and_one_optional_equal_v2(self):
        rng = random.Random(11)
        for _ in range(300):
            job = random_job(rng, 2)
            markers = [c.state for c in job[2].mandatory]
            if sorted(markers) != ['not_mandatory', 'structure_ok']:
                continue
            v2, v3 = score(*job, policy=POLICY_V2), score(*job)
            self.assertEqual([v2[k] for k in ('lower', 'upper', 'coverage', 'mandatory')],
                             [v3[k] for k in ('lower', 'upper', 'coverage', 'mandatory')])

    def test_optional_rows_never_change_the_mandatory_part(self):
        rng = random.Random(12)
        checked = 0
        for _ in range(1000):
            reqs, ev, evidence = random_job(rng)
            base = score(reqs, ev, evidence)
            if not (base['groups']['core'] and base['groups']['extra']):
                continue
            extra_id = next(r.id for r in reqs.items if r.id not in base['mandatory_ids'])
            # Drop one optional row: the mandatory part keeps its points.
            if len(reqs.items) - len(base['mandatory_ids']) > 1:
                keep = lambda xs, field: [x for x in xs if getattr(x, field) != extra_id]
                less = score(Requirements(items=keep(reqs.items, 'id')),
                             Evaluation(rows=keep(ev.rows, 'requirement_id')),
                             evidence.model_copy(update={'rows': keep(evidence.rows, 'requirement_id'),
                                                         'mandatory': keep(evidence.mandatory, 'requirement_id')}))
                self.assertEqual(less['groups']['core'], base['groups']['core'])
                checked += 1
            self.assertEqual(base['groups']['core']['share'], CORE_SHARE)
            self.assertAlmostEqual(base['groups']['core']['lower'] + base['groups']['extra']['lower'], base['lower'],
                                   places=3)
        self.assertGreater(checked, 100)

    def test_weights_are_the_whole_scale_and_explain_the_bounds(self):
        rng = random.Random(13)
        for _ in range(1000):
            reqs, ev, evidence = job = random_job(rng)
            s = score(*job)
            self.assertAlmostEqual(sum(s['weights'].values()), 100, places=2)
            rows = {r.requirement_id: r.status for r in ev.rows}
            value = {'full': 1, 'partial': 0.5, 'fail': 0}
            lower = sum(w * value[rows[rid]] for rid, w in s['weights'].items()
                        if rows[rid] != 'unknown' and rid not in s['disputed_ids'])
            self.assertAlmostEqual(lower, s['lower'], places=2)

    def test_literal_repeat_counts_once(self):
        def job(texts):
            return build_job({'job_id': 'j', 'rows': [{'id': f'r{i}', 'text': t, 'm': False, 'status': st}
                                                      for i, (t, st) in enumerate(texts)]})
        plain = score(*job([('Python', 'full'), ('SQL', 'fail')]))
        repeat = score(*job([('Python', 'full'), ('SQL', 'fail'), (' sql. ', 'fail')]))
        self.assertEqual(repeat['lower'], plain['lower'])
        self.assertEqual(repeat['repeated_ids'], [['r1', 'r2']])
        # Different wording is not merged: equal meaning is not provable here.
        reworded = score(*job([('Python', 'full'), ('SQL', 'fail'), ('Знание SQL', 'fail')]))
        self.assertEqual(reworded['repeated_ids'], [])
        self.assertLess(reworded['lower'], plain['lower'])

    def test_a_repeat_of_a_mandatory_row_does_not_violate_by_itself(self):
        reqs, ev, evidence = build_job({'job_id': 'j', 'rows': [
            {'id': 'r1', 'text': 'Python', 'm': True, 'status': 'full'},
            {'id': 'r2', 'text': 'python', 'm': False, 'status': 'fail'}]})
        s = score(reqs, ev, evidence)
        self.assertEqual((s['mandatory'], s['groups']['extra'], s['lower']), ('confirmed', None, 50))


class LeaderTests(unittest.TestCase):
    def leader(self, case_id):
        return report_of(CASES[case_id])['ranking']

    def test_state_and_reasons_of_the_cases(self):
        expected = {'E11-02': ('open', ['challenger_answers']), 'E11-10': ('close', ['close_margin']),
                    'E11-11': ('stable', []), 'E11-12': ('tie', []), 'E11-13': ('open', ['challenger_answers']),
                    'E11-14': ('stable', []), 'E11-07': ('open', ['own_mandatory_unresolved', 'no_confirmed_fit']),
                    'E11-06': ('open', ['own_marker_unapplied'])}
        for case_id, (state, reasons) in expected.items():
            with self.subTest(case_id):
                leader = self.leader(case_id)['leader']
                self.assertEqual((leader['state'], leader['reasons']), (state, reasons))

    def test_job_without_confirmed_matches_is_unassessed_not_a_rival(self):
        ranking = self.leader('E11-14')
        self.assertEqual((ranking['recommendation'], ranking['leader']['unassessed']), ('review_top', ['empty']))

    def test_decisive_rows_are_few_and_named(self):
        leader = self.leader('E11-13')['leader']
        self.assertEqual([(d['job_id'], d['requirement_id'], d['kind'], d['role']) for d in leader['decisive']],
                         [('second', 'r3', 'unknown', 'challenger')])
        self.assertEqual(leader['challengers'], [{'job_id': 'second', 'answers_needed': 1}])
        far = self.leader('E11-15')['leader']
        self.assertEqual((far['decisive'], far['challengers'], far['answers_limit']), ([], [], ANSWERS))

    def test_v3_never_establishes_a_first_place_v2_rules_keep_open(self):
        rng = random.Random(14)
        open_v2 = 0
        for _ in range(1500):
            jobs = [{'job_id': f'j{i}', 'score': score(*random_job(rng))} for i in range(rng.randint(1, 5))]
            new = rank(jobs, len(jobs))
            # The same scores read by the v2 rule (a score without a version takes the v2 path).
            old = rank([{'job_id': j['job_id'], 'score': {k: v for k, v in j['score'].items() if k != 'policy_version'}}
                        for j in jobs], len(jobs))
            self.assertEqual({j['job_id']: j['rank'] for j in new['jobs']},
                             {j['job_id']: j['rank'] for j in old['jobs']})
            if old['recommendation'] != 'review_top':
                self.assertNotEqual(new['recommendation'], 'review_top')
                open_v2 += 1
        self.assertGreater(open_v2, 300)

    def test_strengthening_a_confirmed_leader_row_keeps_it_first(self):
        rng = random.Random(15)
        for _ in range(500):
            built = [random_job(rng) for _ in range(rng.randint(2, 4))]
            jobs = [{'job_id': f'j{i}', 'score': score(*job)} for i, job in enumerate(built)]
            first = rank(jobs, len(jobs))['jobs'][0]
            idx = int(first['job_id'][1:])
            rid = rng.choice(built[idx][0].items).id
            stronger = score(*with_status(built[idx], rid, 'full', 'structure_ok'))
            if stronger['mandatory'] == 'violated' or first['score']['mandatory'] == 'violated':
                continue
            again = rank([j if i != idx else {'job_id': j['job_id'], 'score': stronger}
                          for i, j in enumerate(jobs)], len(jobs))
            if stronger['lower'] >= first['score']['lower']:
                self.assertEqual(next(j['rank'] for j in again['jobs'] if j['job_id'] == first['job_id']), 1)

    def test_mixed_policy_versions_are_refused(self):
        old, new = (score(*build_job(CASES['E11-12']['jobs'][0]), policy=p) for p in (POLICY_V2, POLICY_VERSION))
        with self.assertRaisesRegex(ValueError, 'mixed_policy'):
            rank([{'job_id': 'a', 'score': old}, {'job_id': 'b', 'score': new}], 2)


class ExplanationTests(unittest.TestCase):
    def test_leader_explanation_repeats_the_ranking(self):
        for case_id in CASES:
            with self.subTest(case_id):
                report = report_of(CASES[case_id])
                leader, text = report['ranking']['leader'], explain_leader(report)
                self.assertEqual((text.job_ids, text.state, text.reasons), (
                    leader['job_ids'], leader['state'], leader['reasons']))
                self.assertLessEqual(len(text.factors), 3)
                self.assertEqual([(c.row.job_id, c.row.requirement_id) for c in text.can_change],
                                 [(d['job_id'], d['requirement_id']) for d in leader['decisive']])
                top = {j['job_id']: j['score'] for j in report['ranking']['jobs'] if j['rank'] == 1}
                for ref in text.factors:  # a factor is a confirmed row of a leader with exactly its points
                    row_weight = top[ref.job_id]['weights'][ref.requirement_id]
                    self.assertAlmostEqual(ref.effect, row_weight * (1 if ref.status == 'full' else 0.5), places=3)

    def test_factors_of_the_demo_first_place(self):
        report = asyncio.run(run_pipeline(*demo_inputs('success'), ReplayModel(), SyntheticPrivacy()))
        text = explain_leader(report)
        self.assertEqual((text.job_ids, text.state), (['job-001'], 'stable'))
        self.assertEqual([(r.requirement_id, r.effect, r.mandatory_applied) for r in text.factors],
                         [('r1', 75.0, True), ('r2', 25.0, False)])
        self.assertEqual((text.limits, text.can_change, text.unassessed), ([], [], ['job-002']))
        self.assertIn('это отсутствие сведений, не отказ', text.summary)

    def test_tampered_leader_block_is_refused(self):
        report = report_of(CASES['E11-13'])
        report['ranking']['leader']['state'] = 'stable'
        with self.assertRaisesRegex(ValueError, 'score_not_reproducible'):
            explain_leader(report)

    def test_condition_conflict_is_shown_apart_and_does_not_move_the_score(self):
        report = json.loads((E9 / 'e9-contract-disputed.json').read_text(encoding='utf-8'))['report']
        first = report['ranking']['jobs'][0]
        self.assertIn('work_mode', first['conditions']['conflicts'])
        text = explain_leader(report)
        self.assertEqual(text.condition_conflicts, first['conditions']['conflicts'])
        self.assertIn('в оценку не входят, решает HR', text.summary)
        # score() takes requirements, rows and evidence only: conditions cannot enter it.
        reqs, ev = Requirements.model_validate(first['requirements']), Evaluation.model_validate(first['evaluation'])
        self.assertEqual(score(reqs, ev, PairCheck.model_validate(first['evidence_check'])), first['score'])

    def test_close_pair_is_said_in_the_comparison(self):
        c = compare(report_of(CASES['E11-10']), 'short', 'long')
        self.assertEqual((c.outcome, c.reason, c.close, c.margin), ('a_higher', 'lower_bound', True, 8.3333))
        self.assertIn('close_margin', c.caveats)
        self.assertIn('превосходство по проценту не установлено', c.summary)
        clear = compare(report_of(CASES['E11-11']), 'short', 'long')
        self.assertEqual((clear.close, clear.caveats), (False, ['different_requirement_lists']))

    def test_stored_v2_report_is_explained_by_v2_and_gets_no_v3_reading(self):
        report = report_of(CASES['E11-09'], policy=POLICY_V2)
        self.assertNotIn('leader', report['ranking'])
        c = compare(report, 'relevant', 'weak')
        self.assertEqual((c.policy_version, c.outcome, c.close), (POLICY_V2, 'b_higher', False))  # the v2 order
        self.assertIsNone(explain_leader(report))
        mixed = copy.deepcopy(report)
        reqs, ev, evidence = build_job(CASES['E11-09']['jobs'][0])
        mixed['ranking']['jobs'][0]['score'] = score(reqs, ev, evidence)  # only one job re-scored by v3
        with self.assertRaises(ValueError):
            compare(mixed, 'relevant', 'weak')


class QueueAndDecisionTests(unittest.TestCase):
    def test_decisive_unknown_row_is_queued_first_and_others_are_not(self):
        report = report_of(CASES['E11-13'])
        queue = build_review_queue(report)
        decisive = [i for i in queue.items if i.decisive]
        self.assertEqual([(i.job_id, i.requirement_id, i.reason_code, i.priority, i.action) for i in decisive],
                         [('second', 'r3', 'decisive_unknown', 2, 'ask_candidate')])
        self.assertEqual(closing_decision('decisive_unknown'), 'read_context')
        far = build_review_queue(report_of(CASES['E11-15']))  # five unknown optional rows, none decisive
        self.assertEqual([i for i in far.items if i.requirement_id], [])

    def test_decisive_mandatory_row_is_raised_inside_the_queue(self):
        queue = build_review_queue(report_of(CASES['E11-02']))
        first_row_item = next(i for i in queue.items if i.requirement_id)
        self.assertEqual((first_row_item.job_id, first_row_item.requirement_id, first_row_item.reason_code,
                          first_row_item.priority, first_row_item.decisive),
                         ('pluses', 'r1', 'mandatory_unknown', 2, True))

    def test_item_id_does_not_depend_on_being_decisive(self):
        report = report_of(CASES['E11-02'])
        plain = copy.deepcopy(report)
        plain['ranking']['leader']['decisive'] = []
        ids = lambda r: {(i.job_id, i.requirement_id, i.reason_code): i.id for i in build_review_queue(r).items}
        self.assertEqual(ids(report), ids(plain))

    def test_decision_made_under_v2_does_not_confirm_the_v3_report(self):
        case = CASES['E11-12']
        old, new = report_of(case, policy=POLICY_V2), report_of(case)
        job = lambda r: next(j for j in r['ranking']['jobs'] if j['job_id'] == 'a')
        made = {'decision_id': 'd1', 'job_id': 'a', 'item_id': None, 'action': 'confirm_requirements',
                **current_versions(old, job(old)), 'decided_by': 'recruiter', 'recorded_by': 'service',
                'decided_at': '2026-11-14T10:00:00+03:00'}
        self.assertTrue(assess_handoff(old, [made], 'a').requirements_confirmed)
        after = assess_handoff(new, [made], 'a')
        self.assertFalse(after.requirements_confirmed)
        self.assertLessEqual({'stale_policy_version', 'stale_report_sha256'}, {i.code for i in after.reasons})


class WireCompatibilityTests(unittest.TestCase):
    """Fields the current UI and report writer read keep their names, types and value sets."""

    def test_score_and_ranking_keep_the_v2_fields(self):
        report = asyncio.run(run_pipeline(*demo_inputs('disputed'), ReplayModel(), SyntheticPrivacy()))
        for job in report['ranking']['jobs']:
            s = job['score']
            self.assertLessEqual({'lower', 'upper', 'coverage', 'mandatory', 'disputed_ids', 'excluded_mandatory_ids',
                                  'evidence_applied', 'policy_version'}, set(s))
            self.assertIn(s['mandatory'], {'confirmed', 'clarify', 'violated', 'not_set'})
            self.assertTrue(0 <= s['lower'] <= s['upper'] <= 100)
            self.assertEqual(s['policy_version'], POLICY_VERSION)
        self.assertIn(report['ranking']['recommendation'], {'review_top', 'clarify', 'review_none_fit', 'incomplete'})
        self.assertEqual(report['policy_version'], POLICY_VERSION)
        for c in report['comparisons']:
            self.assertIn(c['reason'], {'mandatory_violation', 'lower_bound', 'tie'})


if __name__ == '__main__':
    unittest.main()
