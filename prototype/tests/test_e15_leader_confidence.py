"""E15: one partial match and a wide unknown are not a convincing first place (leader rules leader-0.2).

Found defect: a vacancy with a single counted requirement out of eight, next to vacancies with no
data, was reported as a stable first place with the advice «check the leader». Synthetic; relations
only, no vacancy is favoured.
"""
import json
import unittest

from prototype.ranking_explanation import compare, explain_leader
from prototype.review_queue import build_review_queue
from prototype.scoring import LEADER_RULES, rank, score
from prototype.tests.test_scoring_v3 import rows_job


def report(**jobs):
    results = []
    for name, (reqs, evaluation, evidence) in jobs.items():
        results.append({'job_id': name, 'requirements': reqs.model_dump(), 'evaluation': evaluation.model_dump(),
                        'evidence_check': evidence.model_dump(), 'safe_source_sha256': 'src-' + name,
                        'score': score(reqs, evaluation, evidence)})
    return {'run_id': 'run-1', 'safe_resume_sha256': 'cv', 'ranking': rank(results, len(results)),
            'facts': {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]}}


def unknowns(n, prefix='n'):
    return [(f'{prefix}{i}', 'unknown') for i in range(n)]


THIN = rows_job(('a', 'partial'), *unknowns(7))          # 1 partial of 8: 6.25 counted, coverage 12.5
EMPTY = rows_job(*unknowns(5, 'm'))


class ThinLeaderTests(unittest.TestCase):
    def test_one_partial_match_among_unknowns_is_not_an_established_first_place(self):
        r = report(thin=THIN, empty=EMPTY)
        ranking, leader = r['ranking'], r['ranking']['leader']
        self.assertEqual([(j['job_id'], j['score']['lower'], j['score']['coverage']) for j in ranking['jobs']],
                         [('thin', 6.25, 12.5), ('empty', 0, 0)])  # the order itself is unchanged
        self.assertEqual((ranking['recommendation'], leader['state'], leader['reasons']),
                         ('clarify', 'open', ['own_mostly_unknown']))
        self.assertEqual((leader['comparable'], leader['unassessed']), (True, ['empty']))
        # The questions are the leader's own heaviest open requirements, at most three.
        self.assertEqual([(d['job_id'], d['kind'], d['role']) for d in leader['decisive']],
                         [('thin', 'unknown', 'leader')] * 3)
        text = explain_leader(r)
        self.assertIn('покрывают меньше половины', text.summary)
        self.assertNotIn('устойчиво', text.summary)
        decisive = [i for i in build_review_queue(r).items if i.decisive]
        self.assertEqual({(i.job_id, i.action) for i in decisive}, {('thin', 'ask_candidate')})

    def test_the_rule_is_about_coverage_not_about_the_score(self):
        cases = {
            'half known, all failed': (rows_job(('a', 'fail'), ('b', 'fail'), ('c', 'partial'), *unknowns(3)), 'stable'),
            'just under half': (rows_job(('a', 'full'), ('b', 'full'), ('c', 'full'), *unknowns(4)), 'open'),
            'mandatory confirmed, optional unknown': (rows_job(('a', 'full'), *unknowns(5), mandatory=(0,)), 'stable'),
            'one optional full of ten': (rows_job(('a', 'full'), *unknowns(9)), 'open'),
            'fully known, weak': (rows_job(('a', 'partial'), ('b', 'fail'), ('c', 'fail')), 'stable'),
        }
        for name, (job, state) in cases.items():
            with self.subTest(name):
                leader = report(top=job, empty=EMPTY)['ranking']['leader']
                self.assertEqual(leader['state'], state)
                self.assertEqual('own_mostly_unknown' in leader['reasons'], state == 'open')

    def test_the_mechanism_of_the_changing_leader_is_reported_as_open_both_ways(self):
        # Two readings of one vacancy: 7 equal optional units, or 2 mandatory + 15 optional (as in the issue).
        a = rows_job(*[(f'p{i}', 'partial') for i in range(4)], *unknowns(8))
        first = rows_job(('x', 'partial'), *unknowns(6))
        second = rows_job(('c1', 'partial'), ('c2', 'unknown'), *unknowns(15, 'e'), mandatory=(0, 1))
        for name, b in (('first reading', first), ('second reading', second)):
            with self.subTest(name):
                ranking = report(a=a, b=b)['ranking']
                self.assertEqual((ranking['recommendation'], ranking['leader']['state']), ('clarify', 'open'))
        orders = [[j['job_id'] for j in report(a=a, b=b)['ranking']['jobs']] for b in (first, second)]
        self.assertEqual(orders, [['a', 'b'], ['b', 'a']])  # the arithmetic follows the extraction: not hidden

    def test_enough_counted_evidence_still_gives_a_plain_first_place(self):
        solid = rows_job(('a', 'full'), ('b', 'full'), ('c', 'partial'), ('d', 'fail'), ('e', 'unknown'), mandatory=(0,))
        ranking = report(solid=solid, thin=THIN, empty=EMPTY)['ranking']
        self.assertEqual((ranking['recommendation'], ranking['leader']['state'], ranking['leader']['job_ids']),
                         ('review_top', 'stable', ['solid']))


class StoredReportTests(unittest.TestCase):
    def test_new_scores_are_stamped_and_older_ones_keep_their_leader(self):
        r = report(thin=THIN, empty=EMPTY)
        self.assertTrue(all(j['score']['leader_rules'] == LEADER_RULES for j in r['ranking']['jobs']))
        old = json.loads(json.dumps(r))  # as saved before leader-0.2: stable, no stamp
        for job in old['ranking']['jobs']:
            del job['score']['leader_rules']
        old['ranking'] = rank([{k: v for k, v in j.items() if k != 'rank'} for j in old['ranking']['jobs']], 2)
        self.assertEqual((old['ranking']['leader']['state'], old['ranking']['recommendation']), ('stable', 'review_top'))
        text = explain_leader(old)  # reopened by the rules it was ranked by, not refused and not re-read
        self.assertEqual(text.state, 'stable')
        self.assertEqual(compare(old, 'thin', 'empty').outcome, 'a_higher')
        mixed = json.loads(json.dumps(r))
        del mixed['ranking']['jobs'][1]['score']['leader_rules']  # one stamped, one not: the older rules apply
        again = rank([{k: v for k, v in j.items() if k != 'rank'} for j in mixed['ranking']['jobs']], 2)
        self.assertEqual(again['leader']['state'], 'stable')


if __name__ == '__main__':
    unittest.main()
