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


def rows_job(*rows, job_id='j', mandatory=()):
    """(text, status[, quote]) rows of one vacancy; `mandatory` lists row indexes with an applied marker."""
    return build_job({'job_id': job_id, 'rows': [
        {'id': f'r{i}', 'text': r[0], 'status': r[1], 'm': i in mandatory, **({'quote': r[2]} if len(r) > 2 else {})}
        for i, r in enumerate(rows)]})


def ranked(**jobs):
    return rank([{'job_id': name, 'score': score(*job)} for name, job in jobs.items()], len(jobs))


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
        plain = score(*rows_job(('Python', 'full'), ('SQL', 'fail')))
        repeat = score(*rows_job(('Python', 'full'), ('SQL', 'fail', 'Знание SQL'), (' sql. ', 'fail', 'знание  SQL.')))
        self.assertEqual((repeat['lower'], repeat['upper']), (plain['lower'], plain['upper']))
        self.assertEqual(repeat['repeated_ids'], [['r1', 'r2']])
        # Different wording is not merged: equal meaning is not provable here.
        reworded = score(*rows_job(('Python', 'full'), ('SQL', 'fail'), ('Знание SQL', 'fail')))
        self.assertEqual(reworded['repeated_ids'], [])
        self.assertLess(reworded['lower'], plain['lower'])

    def test_same_text_from_another_quote_or_obligatoriness_is_not_a_repeat(self):
        other_quote = score(*rows_job(('Python', 'full', 'Python от 3 лет'), ('Python', 'fail', 'Python будет плюсом')))
        self.assertEqual((other_quote['repeated_ids'], other_quote['conflict_ids'], other_quote['lower']), ([], [], 50))
        reqs, ev, evidence = build_job({'job_id': 'j', 'rows': [
            {'id': 'r1', 'text': 'Python', 'quote': 'Python', 'm': True, 'status': 'full'},
            {'id': 'r2', 'text': 'python', 'quote': 'python.', 'm': False, 'status': 'fail'}]})
        s = score(reqs, ev, evidence)  # an optional mention never joins, or violates, the mandatory one
        self.assertEqual((s['mandatory'], s['repeated_ids'], s['lower']), ('confirmed', [], 75))

    def test_conflicting_repeats_are_not_averaged(self):
        s = score(*rows_job(('Python', 'full', 'Python'), ('Python', 'fail', 'python.'), ('SQL', 'full')))
        self.assertEqual((s['conflict_ids'], s['lower'], s['upper'], s['coverage']), (['r0', 'r1'], 50, 100, 50))
        ranking = rank([{'job_id': 'j', 'score': s}], 1)
        self.assertEqual((ranking['recommendation'], ranking['leader']['reasons']), ('clarify', ['own_disputed']))
        # A row without data does not contradict a known one: the unit keeps the known status.
        silent = score(*rows_job(('Python', 'full', 'Python'), ('Python', 'unknown', 'python.'), ('SQL', 'full')))
        self.assertEqual((silent['conflict_ids'], silent['lower']), ([], 100))


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

    def test_a_doubted_leader_is_never_a_plain_review_top(self):
        # The v2 own-basis rules hold in v3. A rival is judged by reach (see ReviewRegressionTests), not by H.
        rng = random.Random(14)
        doubted = 0
        for _ in range(1500):
            jobs = [{'job_id': f'j{i}', 'score': score(*random_job(rng))} for i in range(rng.randint(1, 5))]
            ranking = rank(jobs, len(jobs))
            top = [j['score'] for j in ranking['jobs'] if j['rank'] == 1]
            if any(s['mandatory'] == 'clarify' or s['disputed_ids'] or s['excluded_mandatory_ids'] or s['lower'] == 0
                   for s in top):
                self.assertNotEqual(ranking['recommendation'], 'review_top')
                doubted += 1
        self.assertGreater(doubted, 300)

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


class ReviewRegressionTests(unittest.TestCase):
    """Defects found by the independent review of ba3e014 (PR #29)."""

    def test_scenario_uses_exact_weights_not_rounded_ones(self):
        ranking = ranked(a=rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail')),
                         b=rows_job(('x', 'full'), ('y', 'unknown'), ('z', 'fail')))
        leader = ranking['leader']
        self.assertEqual((ranking['recommendation'], leader['state'], leader['challengers']),
                         ('clarify', 'open', [{'job_id': 'b', 'answers_needed': 1}]))
        # ...and the real re-score of that one answer is a tie.
        again = ranked(a=rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail')),
                       b=rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail')))
        self.assertEqual([j['rank'] for j in again['jobs']], [1, 1])

    def test_repeats_of_a_leader_unit_do_not_change_closeness(self):
        rival = rows_job(*[(f'o{i}', 'full') for i in range(4)], ('o4', 'fail'))
        one = ranked(top=rows_job(('Python', 'full', 'Python')), rival=rival)
        five = ranked(top=rows_job(*[('Python', 'full', 'Python' + '.' * i) for i in range(5)]), rival=rival)
        for ranking in (one, five):
            self.assertEqual((ranking['leader']['state'], ranking['leader']['close_to']), ('close', ['rival']))
        self.assertEqual(one['leader']['resolution'], five['leader']['resolution'])
        scores = [j['score'] for j in five['jobs']]
        self.assertEqual([s['resolution'] for s in scores], [50, 10])  # by units: one unit of 100, five of 20
        self.assertNotEqual(min(scores[0]['weights'].values()) / 2, scores[0]['resolution'])  # rows mislead
        self.assertEqual(five['leader']['resolution'], max(s['resolution'] for s in scores))
        self.assertLess(five['leader']['margin'], five['leader']['resolution'])

    def test_repeats_of_an_unknown_unit_do_not_change_the_answer_budget(self):
        top = rows_job(('a', 'full'), ('b', 'full'), ('c', 'full'), ('d', 'partial'), ('e', 'fail'), ('f', 'fail'))
        plain = rows_job(('x', 'full'), ('y', 'unknown', 'Знание Y'), ('z', 'fail'))
        repeated = rows_job(('x', 'full'), *[('y', 'unknown', 'Знание Y' + '.' * i) for i in range(4)], ('z', 'fail'))
        for rival in (plain, repeated):
            s = score(*rival)
            self.assertEqual((s['lower'], s['upper']), (33.3333, 66.6667))
            ranking = ranked(top=top, rival=rival)
            self.assertEqual(ranking['jobs'][0]['score']['lower'], 58.3333)
            self.assertEqual((ranking['recommendation'], ranking['leader']['challengers']),
                             ('clarify', [{'job_id': 'rival', 'answers_needed': 1}]))
        decisive = ranked(top=top, rival=repeated)['leader']['decisive']
        self.assertEqual([d['requirement_ids'] for d in decisive], [['r1', 'r2', 'r3', 'r4']])  # one question

    def test_tied_leaders_are_all_checked_whatever_their_ids(self):
        two = rows_job(('a', 'full'), ('b', 'partial'))
        four = rows_job(('a', 'full'), ('b', 'full'), ('c', 'full'), ('d', 'fail'))
        third = rows_job(('a', 'full'), ('b', 'full'), ('c', 'full'), ('d', 'fail'), ('e', 'fail'))
        seen = set()
        for first, second in (('a', 'b'), ('b', 'a')):
            ranking = ranked(**{first: two, second: four, 'z': third})
            self.assertEqual([j['score']['lower'] for j in ranking['jobs']], [75, 75, 60])
            seen.add((ranking['recommendation'], ranking['leader']['state'], tuple(ranking['leader']['close_to'])))
        self.assertEqual(seen, {('clarify', 'close', ('z',))})

    def test_a_tie_one_answer_would_break_is_open_and_names_the_row(self):
        ranking = ranked(a=rows_job(('x', 'full'), ('y', 'unknown')), b=rows_job(('x', 'full'), ('y', 'fail')))
        leader = ranking['leader']
        self.assertEqual(([j['rank'] for j in ranking['jobs']], ranking['recommendation'], leader['reasons']),
                         ([1, 1], 'clarify', ['tie_unresolved']))
        self.assertEqual([(d['job_id'], d['requirement_id'], d['kind']) for d in leader['decisive']],
                         [('a', 'r1', 'unknown')])
        settled = ranked(a=rows_job(('x', 'full'), ('y', 'fail')), b=rows_job(('x', 'full'), ('y', 'fail')))
        self.assertEqual((settled['recommendation'], settled['leader']['state']), ('review_top', 'tie'))

    def test_disputed_and_unknown_gains_are_counted_apart(self):
        rival = build_job({'job_id': 'rival', 'rows': [
            {'id': 'r0', 'text': 'a', 'm': False, 'status': 'full'}, {'id': 'r1', 'text': 'b', 'm': False, 'status': 'full'},
            {'id': 'r2', 'text': 'c', 'm': False, 'status': 'unknown'}, {'id': 'r3', 'text': 'd', 'm': False, 'status': 'unknown'},
            {'id': 'r4', 'text': 'e', 'm': False, 'status': 'unknown'},
            {'id': 'r5', 'text': 'f', 'm': False, 'status': 'full', 'evidence': 'review'}]})
        ranking = ranked(top=rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail')), rival=rival)
        leader = ranking['leader']
        self.assertEqual((leader['reasons'], leader['challengers']),
                         (['challenger_answers'], [{'job_id': 'rival', 'answers_needed': 1}]))
        self.assertEqual(sorted((d['requirement_id'], d['kind']) for d in leader['decisive']),
                         [('r2', 'unknown'), ('r5', 'disputed')])
        # Reading the disputed row alone reaches 50, below the leader's 66.6667: that is not "0 answers".
        far = build_job({'job_id': 'rival', 'rows': [
            {'id': 'r0', 'text': 'a', 'm': False, 'status': 'fail'}, {'id': 'r1', 'text': 'b', 'm': False, 'status': 'fail'},
            {'id': 'r2', 'text': 'c', 'm': False, 'status': 'fail'},
            {'id': 'r3', 'text': 'f', 'm': False, 'status': 'full', 'evidence': 'review'}]})
        self.assertEqual(ranked(top=rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail')), rival=far)['leader']['state'],
                         'stable')

    def test_applying_an_unapplied_marker_is_really_rescored(self):
        top = rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail'))
        def rival(marker):
            return build_job({'job_id': 'rival', 'rows': [
                {'id': 'r0', 'text': 'a', 'm': True, 'marker': marker, 'status': 'full'},
                *[{'id': f'r{i}', 'text': t, 'm': False, 'status': 'fail'} for i, t in enumerate('bcd', 1)]]})
        s = score(*rival('review'))
        self.assertEqual((s['lower'], s['upper'], s['excluded_mandatory_ids']), (25, 25, ['r0']))  # H does not bound it
        ranking = ranked(top=top, rival=rival('review'))
        leader = ranking['leader']
        self.assertEqual((ranking['recommendation'], leader['reasons'], leader['challengers']),
                         ('clarify', ['challenger_doubted'], [{'job_id': 'rival', 'answers_needed': 0}]))
        self.assertEqual([(d['job_id'], d['requirement_id'], d['kind']) for d in leader['decisive']],
                         [('rival', 'r0', 'marker')])
        # The scenario is the real score with only the E3 marker state changed: the rival becomes first.
        applied = score(*rival('ok'))
        self.assertEqual(s['marker_scenarios'][0]['units'], applied['units'])
        self.assertEqual(ranked(top=top, rival=rival('ok'))['jobs'][0]['job_id'], 'rival')
        # A marker whose application cannot reach the top keeps the first place stable.
        weak = build_job({'job_id': 'rival', 'rows': [
            {'id': 'r0', 'text': 'a', 'm': True, 'marker': 'review', 'status': 'fail'},
            {'id': 'r1', 'text': 'b', 'm': False, 'status': 'full'}, {'id': 'r2', 'text': 'c', 'm': False, 'status': 'fail'}]})
        self.assertEqual(ranked(top=top, rival=weak)['leader']['state'], 'stable')

    def test_every_marker_combination_or_a_conservative_answer(self):
        rng = random.Random(23)
        seen = 0
        for _ in range(600):
            reqs, ev, evidence = random_job(rng)
            s = score(reqs, ev, evidence)
            for scenario in s['marker_scenarios'] or []:
                seen += 1
                markers = [c.model_copy(update={'state': 'structure_ok'}) if c.requirement_id in scenario['applied']
                           else c for c in evidence.mandatory]
                real = score(reqs, ev, evidence.model_copy(update={'mandatory': markers}))
                self.assertEqual((scenario['units'], scenario['mandatory']), (real['units'], real['mandatory']))
        self.assertGreater(seen, 200)
        many = build_job({'job_id': 'rival', 'rows': [
            {'id': f'r{i}', 'text': f't{i}', 'm': True, 'marker': 'review', 'status': 'fail'} for i in range(5)]
            + [{'id': 'r9', 'text': 'z', 'm': False, 'status': 'partial'}]})
        self.assertIsNone(score(*many)['marker_scenarios'])
        ranking = ranked(top=rows_job(('x', 'full')), rival=many)
        self.assertEqual((ranking['recommendation'], ranking['leader']['challengers']),
                         ('clarify', [{'job_id': 'rival', 'answers_needed': None}]))

    def test_explanations_walk_requirement_units(self):
        def report(**jobs):
            return report_of({'jobs': [{'job_id': name, 'rows': rows} for name, rows in jobs.items()]})
        row = lambda rid, text, status, quote=None: {'id': rid, 'text': text, 'status': status, 'm': False,
                                                     **({'quote': quote} if quote else {})}
        # One optional unit made of two equal full rows gives L 100: the factor must not vanish.
        r = report(top=[row('r1', 'Python', 'full', 'Python'), row('r2', 'python', 'full', 'python.')],
                   low=[row('r1', 'Go', 'fail')])
        self.assertEqual(r['ranking']['jobs'][0]['score']['lower'], 100)
        self.assertEqual([(f.requirement_id, f.effect) for f in explain_leader(r).factors], [('r1', 100)])
        c = compare(r, 'top', 'low')
        self.assertIn(('top', 'r1', 100), [(d.job_id, d.requirement_id, d.effect) for d in c.deciding])
        # One unknown unit made of two rows is one answer in rank and one swing in compare.
        r = report(top=[row('r1', 'a', 'full'), row('r2', 'b', 'fail')],
                   low=[row('r1', 'a', 'partial'), row('r2', 'b', 'unknown', 'Знание B'),
                        row('r3', 'b', 'unknown', 'знание  b.')])
        leader = r['ranking']['leader']
        self.assertEqual(leader['challengers'], [{'job_id': 'low', 'answers_needed': 1}])
        swings = compare(r, 'top', 'low').swings
        self.assertEqual([(s.row.job_id, s.row.requirement_id, s.result) for s in swings], [('low', 'r2', 'reversed')])
        change = explain_leader(r).can_change
        self.assertEqual([c.requirement_ids for c in change], [['r2', 'r3']])
        # Conflicting repeats are disputed in every reference, though E3 found each row structurally sound.
        r = report(top=[row('r1', 'Python', 'full', 'Python'), row('r2', 'python', 'fail', 'python.'),
                        row('r3', 'SQL', 'full')], low=[row('r1', 'Go', 'fail')])
        self.assertEqual(r['ranking']['jobs'][0]['score']['disputed_ids'], [])
        text = explain_leader(r)
        self.assertEqual([(l.requirement_id, l.disputed) for l in text.limits], [('r1', True)])
        self.assertEqual([(c.row.disputed, c.kind, c.requirement_ids) for c in text.can_change],
                         [(True, 'disputed', ['r1', 'r2'])])
        self.assertEqual([f.requirement_id for f in text.factors], ['r3'])

    def test_paired_comparison_uses_the_row_that_carries_the_unit_status(self):
        row = lambda rid, status, quote: {'id': rid, 'text': 'Python', 'status': status, 'm': False, 'quote': quote}
        report = report_of({'jobs': [
            {'job_id': 'top', 'rows': [row('r1', 'unknown', 'Python'), row('r2', 'full', 'Python.')]},
            {'job_id': 'low', 'rows': [row('r1', 'partial', 'Python'), row('r2', 'partial', 'Python.')]}]})
        self.assertEqual([j['score']['lower'] for j in report['ranking']['jobs']], [100, 50])
        c = compare(report, 'top', 'low')
        self.assertEqual([(d.job_id, d.requirement_id, d.status, d.counterpart_status, d.effect) for d in c.deciding],
                         [('low', 'r1', 'partial', 'full', 50)])
        self.assertNotIn('unknown', c.summary)
        factors = explain_leader(report).factors  # the confirmed row of the unit, with its fact
        self.assertEqual([(f.requirement_id, f.status, f.effect, f.cv_quotes) for f in factors],
                         [('r2', 'full', 100, ['цитата'])])

    def test_fewest_answers_first_then_fewest_markers(self):
        top = rows_job(('x', 'full'), ('y', 'full'), ('z', 'fail'))
        rival = build_job({'job_id': 'rival', 'rows': [
            {'id': 'r0', 'text': 'a', 'm': True, 'marker': 'review', 'status': 'full'},
            {'id': 'r1', 'text': 'b', 'm': False, 'status': 'unknown'},
            {'id': 'r2', 'text': 'c', 'm': False, 'status': 'unknown'},
            {'id': 'r3', 'text': 'd', 'm': False, 'status': 'fail'}]})
        leader = ranked(top=top, rival=rival)['leader']
        self.assertEqual(leader['challengers'], [{'job_id': 'rival', 'answers_needed': 0}])
        self.assertEqual([(d['requirement_id'], d['kind']) for d in leader['decisive']], [('r0', 'marker')])
        # With equal answers the baseline wins: no marker is named when answers alone are as short.
        same = build_job({'job_id': 'rival', 'rows': [
            {'id': 'r0', 'text': 'a', 'm': True, 'marker': 'review', 'status': 'fail'},
            {'id': 'r1', 'text': 'b', 'm': False, 'status': 'full'},
            {'id': 'r2', 'text': 'c', 'm': False, 'status': 'unknown'}]})
        leader = ranked(top=top, rival=same)['leader']
        self.assertEqual(leader['challengers'], [{'job_id': 'rival', 'answers_needed': 1}])
        self.assertEqual([(d['requirement_id'], d['kind']) for d in leader['decisive']], [('r2', 'unknown')])

    def test_rival_with_nothing_confirmed_is_not_close(self):
        ranking = ranked(top=rows_job(('a', 'partial'), ('b', 'fail'), ('c', 'fail'), ('d', 'fail')),
                         empty=rows_job(('x', 'unknown')))
        leader = ranking['leader']
        self.assertEqual((ranking['jobs'][0]['score']['lower'], leader['state'], leader['close_to'], leader['unassessed']),
                         (12.5, 'stable', [], ['empty']))

    def test_one_set_one_policy(self):
        new = score(*rows_job(('a', 'full')))
        old = score(*rows_job(('a', 'full')), policy=POLICY_V2)
        for scores, code in (((old, new), 'mixed_policy'), ((old, {**old, 'policy_version': 'draft-x'}), 'mixed_policy'),
                             (({**old, 'policy_version': 'draft-x'},), 'unknown_policy')):
            with self.subTest(code=code, n=len(scores)), self.assertRaisesRegex(ValueError, code):
                rank([{'job_id': f'j{i}', 'score': s} for i, s in enumerate(scores)], len(scores))
        report = report_of(CASES['E11-08'])  # three jobs
        third = report['ranking']['jobs'][2]
        reqs, ev = Requirements.model_validate(third['requirements']), Evaluation.model_validate(third['evaluation'])
        mixed = copy.deepcopy(report)
        mixed['ranking']['jobs'][2]['score'] = score(reqs, ev, PairCheck.model_validate(third['evidence_check']),
                                                     policy=POLICY_V2)
        first, second = (j['job_id'] for j in report['ranking']['jobs'][:2])
        stamped = {**copy.deepcopy(report), 'policy_version': POLICY_V2}
        for broken in (mixed, stamped):
            with self.assertRaisesRegex(ValueError, 'policy_mismatch'):
                compare(broken, first, second)
            with self.assertRaisesRegex(ValueError, 'policy_mismatch'):
                explain_leader(broken)
        self.assertEqual(compare({**report, 'policy_version': POLICY_VERSION}, first, second).policy_version,
                         POLICY_VERSION)

    def test_stable_means_no_real_rescore_of_two_answers_reaches_the_top(self):
        rng = random.Random(21)
        stable = 0
        for _ in range(3000):
            built = [random_job(rng) for _ in range(rng.randint(2, 4))]
            jobs = [{'job_id': f'j{i}', 'score': score(*job)} for i, job in enumerate(built)]
            ranking = rank(jobs, len(jobs))
            if ranking['leader']['state'] != 'stable':
                continue
            stable += 1
            best = ranking['jobs'][0]['score']['lower']
            for job in ranking['jobs'][1:]:
                s, idx = job['score'], int(job['job_id'][1:])
                if s['mandatory'] == 'violated' or s['lower'] == 0:
                    continue
                unknown = s['unknown_ids']
                for pair in [(a, b) for a in unknown for b in unknown if a <= b]:
                    changed = built[idx]
                    for rid in set(pair):
                        changed = with_status(changed, rid, 'full', 'structure_ok')
                    self.assertLess(score(*changed)['lower'], best)
        self.assertGreater(stable, 30)

    def test_rank_compare_and_explanation_agree(self):
        rng = random.Random(22)
        for _ in range(150):
            results = []
            for i in range(rng.randint(2, 4)):
                reqs, ev, evidence = random_job(rng)
                results.append({'job_id': f'j{i}', 'requirements': reqs.model_dump(), 'evaluation': ev.model_dump(),
                                'evidence_check': evidence.model_dump(), 'score': score(reqs, ev, evidence)})
            report = {'facts': {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]},
                      'ranking': rank(results, len(results))}
            leader, places = report['ranking']['leader'], {j['job_id']: j['rank'] for j in report['ranking']['jobs']}
            text = explain_leader(report)
            self.assertEqual((text.state, text.close_to), (leader['state'], leader['close_to']))
            top = leader['job_ids'][0]
            for other in places:
                if other == top:
                    continue
                c = compare(report, top, other)
                self.assertEqual(c.outcome, 'tie' if places[other] == 1 else 'a_higher')
                if len(leader['job_ids']) == 1 and leader['state'] != 'none_fit' and c.reason == 'lower_bound':
                    assessed = other in leader['close_to'] or other not in leader['unassessed']
                    self.assertEqual(c.close and assessed, other in leader['close_to'])


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
