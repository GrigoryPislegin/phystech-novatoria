"""E7: why one vacancy is above another. Synthetic reports only."""
import asyncio
import copy
import random
import unittest

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.evidence import MandatoryCheck, PairCheck, RowCheck
from prototype.pipeline import run_pipeline
from prototype.ranking_explanation import INTEGRATED, compare
from prototype.scoring import rank, score
from prototype.tests.test_scoring_policy import random_job


def demo_report(scenario='success', model=None):
    return asyncio.run(run_pipeline(*demo_inputs(scenario), model or ReplayModel(), SyntheticPrivacy()))


def with_evidence(report):
    """The report as it will look once the pipeline passes evidence to score (policy v2)."""
    results = [{**{k: v for k, v in j.items() if k != 'rank'}, 'score': score(
        Requirements.model_validate(j['requirements']), Evaluation.model_validate(j['evaluation']),
        PairCheck.model_validate(j['evidence_check']))} for j in report['ranking']['jobs']]
    return {**report, 'ranking': rank(results, len(results))}


def random_report(rng, n):
    results = []
    for i in range(n):
        reqs, ev, evidence = random_job(rng)
        results.append({'job_id': f'j{i}', 'requirements': reqs.model_dump(), 'evaluation': ev.model_dump(),
                        'evidence_check': evidence.model_dump(), 'score': score(reqs, ev, evidence)})
    return {'facts': {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]}, 'ranking': rank(results, n)}


class CompareTests(unittest.TestCase):
    def test_lower_bound_reason_and_a_swing_to_tie(self):
        c = compare(demo_report(), 'job-001', 'job-002')
        self.assertEqual((c.outcome, c.reason), ('a_higher', 'lower_bound'))
        self.assertEqual([(r.job_id, r.requirement_id) for r in c.deciding], [('job-001', 'r1'), ('job-001', 'r2')])
        self.assertEqual([(s.row.job_id, s.assumed_status, s.result) for s in c.swings], [('job-002', 'full', 'tie')])
        self.assertIn('different_requirement_lists', c.caveats)

    def test_violated_mandatory_comes_first(self):
        c = compare(demo_report(), 'job-003', 'job-002')
        self.assertEqual((c.outcome, c.reason), ('b_higher', 'mandatory_violation'))
        first = c.deciding[0]
        self.assertEqual((first.job_id, first.status, first.mandatory_applied, first.effect),
                         ('job-003', 'fail', True, 100))
        self.assertIn('не выполнено обязательное требование', c.summary)

    def test_tie_has_no_deciding_rows(self):
        report = demo_report()
        twin = copy.deepcopy(report['ranking']['jobs'][0])
        twin['job_id'] = 'job-001-copy'
        report['ranking'] = rank([*report['ranking']['jobs'], twin], 4)
        c = compare(report, 'job-001', 'job-001-copy')
        self.assertEqual((c.outcome, c.reason, c.deciding, c.caveats), ('tie', 'tie', [], []))
        self.assertIn('делят место', c.summary)

    def test_swapping_arguments_mirrors_the_result(self):
        report = demo_report('disputed')
        ab, ba = compare(report, 'job-001', 'job-002'), compare(report, 'job-002', 'job-001')
        self.assertEqual({ab.outcome, ba.outcome}, {'a_higher', 'b_higher'})
        self.assertEqual((ab.reason, ab.deciding, ab.swings), (ba.reason, ba.deciding, ba.swings))

    def test_references_exist_in_the_report(self):
        report = demo_report('disputed')
        facts = {f['quote'] for f in report['facts']['items']}
        jobs = {j['job_id']: {r['id']: r['quote'] for r in j['requirements']['items']}
                for j in report['ranking']['jobs']}
        for a in jobs:
            for b in jobs:
                if a == b:
                    continue
                c = compare(report, a, b)
                for ref in c.deciding + [s.row for s in c.swings]:
                    with self.subTest(a=a, b=b, row=ref.requirement_id):
                        self.assertEqual(jobs[ref.job_id][ref.requirement_id], ref.requirement_quote)
                        self.assertLessEqual(set(ref.cv_quotes), facts)

    def test_disputed_row_is_open_under_policy_v2(self):
        class Fragment(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'facts':
                    result.items[0].quote = 'Python'
                return result
        report = with_evidence(demo_report(model=Fragment()))
        c = compare(report, 'job-001', 'job-002')
        disputed = [s.row for s in c.swings if s.row.job_id == 'job-001']
        self.assertTrue(disputed and disputed[0].disputed)
        self.assertEqual(c.policy_version, 'draft-2026-11-13-v2')

    def test_caveat_for_incomplete_run(self):
        report = demo_report()
        report['ranking'] = rank(report['ranking']['jobs'][:2], 3)
        self.assertIn('incomplete_run', compare(report, 'job-001', 'job-002').caveats)

    def test_bad_input_is_rejected(self):
        report = demo_report()
        for a, b, code in [('job-001', 'job-001', 'same_job'), ('job-001', 'job-404', 'unknown_job')]:
            with self.subTest(code), self.assertRaisesRegex(ValueError, code):
                compare(report, a, b)
        report['ranking']['jobs'][0]['score']['lower'] = 42
        with self.assertRaisesRegex(ValueError, 'score_not_reproducible'):
            compare(report, 'job-001', 'job-002')

    def test_report_is_not_modified(self):
        report = demo_report('disputed')
        before = copy.deepcopy(report)
        compare(report, 'job-001', 'job-003')
        self.assertEqual(report, before)

    def test_not_integrated(self):
        self.assertFalse(INTEGRATED)


def manual_report(*jobs):
    """jobs: (job_id, [(status, mandatory), ...]); all evidence structure_ok."""
    results = []
    for job_id, rows in jobs:
        reqs = Requirements(items=[Requirement(id=f'r{i}', text=f'т{i}', quote=f'ц{i}',
                                               mandatory_quote=f'обязательно ц{i}' if m else None)
                                   for i, (_, m) in enumerate(rows)])
        ev = Evaluation(rows=[Row(requirement_id=f'r{i}', status=s, fact_ids=[] if s == 'unknown' else ['f1'],
                                  comment='c', question=None) for i, (s, _) in enumerate(rows)])
        evidence = PairCheck(cv_sha256='c', vacancy_id=job_id, vacancy_sha256='v',
                             needs_review=False, has_invalid=False,
                             rows=[RowCheck(requirement_id=f'r{i}', status=s, reasons=[], evidence=[],
                                            state='no_evidence' if s == 'unknown' else 'structure_ok')
                                   for i, (s, _) in enumerate(rows)],
                             mandatory=[MandatoryCheck(requirement_id=f'r{i}', reasons=[],
                                                       state='structure_ok' if m else 'not_mandatory')
                                        for i, (_, m) in enumerate(rows)])
        results.append({'job_id': job_id, 'requirements': reqs.model_dump(), 'evaluation': ev.model_dump(),
                        'evidence_check': evidence.model_dump(), 'score': score(reqs, ev, evidence)})
    facts = {'items': [{'id': 'f1', 'text': 'факт', 'quote': 'цитата'}]}
    return {'facts': facts, 'ranking': rank(results, len(results))}


class ReasonTests(unittest.TestCase):
    def test_violated_row_leads_even_when_a_gain_is_larger(self):
        report = manual_report(('high', [('full', False)]),
                               ('low', [('fail', True)] + [('full', False)] * 6))
        c = compare(report, 'high', 'low')
        self.assertEqual(c.reason, 'mandatory_violation')
        self.assertEqual((c.deciding[0].job_id, c.deciding[0].status), ('low', 'fail'))
        self.assertGreater(c.deciding[1].effect, c.deciding[0].effect)

    def test_every_violated_row_comes_before_larger_gains(self):
        report = manual_report(('high', [('full', False)]), ('low', [('fail', True), ('fail', True)]))
        c = compare(report, 'high', 'low')
        self.assertEqual([(r.job_id, r.requirement_id) for r in c.deciding[:2]], [('low', 'r0'), ('low', 'r1')])

    def test_two_violated_jobs_compare_by_lower_bound(self):
        report = manual_report(('a', [('fail', True), ('full', False)]), ('b', [('fail', True), ('fail', False)]))
        c = compare(report, 'a', 'b')
        self.assertEqual((c.outcome, c.reason), ('a_higher', 'lower_bound'))

    def test_same_list_shows_only_rows_that_differ(self):
        c = compare(manual_report(('a', [('full', False)] * 3), ('b', [('full', False), ('full', False),
                                                                      ('partial', False)])), 'a', 'b')
        self.assertEqual([(r.job_id, r.requirement_id, r.status, r.counterpart_status) for r in c.deciding],
                         [('b', 'r2', 'partial', 'full')])
        self.assertEqual(c.caveats, [])
        self.assertIn('Различия', c.summary)

    def test_different_lists_lead_with_the_lower_jobs_loss(self):
        c = compare(manual_report(('a', [('full', False)] * 3), ('b', [('partial', False)] * 2)), 'a', 'b')
        self.assertEqual(c.deciding[0].job_id, 'b')
        self.assertIn('different_requirement_lists', c.caveats)
        self.assertIn('Наибольший вклад', c.summary)

    def test_same_quotes_with_different_weights_are_different_scales(self):
        c = compare(manual_report(('a', [('full', True), ('fail', False)]), ('b', [('full', False), ('fail', False)])),
                    'a', 'b')
        self.assertIn('different_requirement_lists', c.caveats)

    def test_tie_text_names_both_mandatory_groups(self):
        report = manual_report(('a', [('full', True), ('unknown', False)]),
                               ('b', [('unknown', True)] + [('full', False)] * 9))
        c = compare(report, 'a', 'b')
        self.assertEqual(c.outcome, 'tie')
        self.assertIn('a — confirmed', c.summary)
        self.assertIn('b — clarify', c.summary)

    def test_both_violated_is_said(self):
        report = manual_report(('a', [('fail', True), ('full', False)]), ('b', [('fail', True), ('fail', False)]))
        self.assertIn('у обеих не выполнено обязательное требование', compare(report, 'a', 'b').summary)

    def test_v1_report_marks_disputed_rows(self):
        class Fragment(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'facts':
                    result.items[0].quote = 'Python'
                return result
        report = demo_report(model=Fragment())
        self.assertFalse(report['ranking']['jobs'][0]['score']['evidence_applied'])
        c = compare(report, 'job-001', 'job-002')
        self.assertIn('evidence_not_applied', c.caveats)
        self.assertFalse(any(r.disputed for r in c.deciding))
        self.assertTrue(any(s.row.disputed and s.row.job_id == 'job-001' for s in c.swings))

    def test_malformed_reports_are_refused(self):
        report = demo_report()
        no_fact = copy.deepcopy(report)
        no_fact['facts']['items'] = no_fact['facts']['items'][1:]
        old_policy = copy.deepcopy(report)
        old_policy['ranking']['jobs'][0]['score']['policy_version'] = 'draft-2026-11-12-v1'
        no_check = with_evidence(report)
        del no_check['ranking']['jobs'][0]['evidence_check']
        for broken, code in [(no_fact, 'unknown_fact'), (old_policy, 'policy_mismatch'),
                             (no_check, 'incomplete_report'), ({'ranking': {}}, 'incomplete_report')]:
            with self.subTest(code), self.assertRaisesRegex(ValueError, code):
                compare(broken, 'job-001', 'job-002')

    def test_v1_report_with_unbound_marker_is_reproduced(self):
        class WrongMarker:
            async def ask(self, schema, task, payload):
                if task == 'facts':
                    return Facts(items=[Fact(id='f', text='Нет Python', quote='Не работал с Python.')])
                if task == 'requirements':
                    return Requirements(items=[Requirement(id='r', text='Python', quote='Python',
                                                           mandatory_quote=payload['text'])])
                return Evaluation(rows=[Row(requirement_id='r', status='fail', fact_ids=['f'], comment='c',
                                            question='q')])
        jobs = [('j1', 'Обязательно: SQL. Python желателен.'), ('j2', 'Обязательно: Go. Python желателен.')]
        report = asyncio.run(run_pipeline('Не работал с Python.', jobs, WrongMarker(), SyntheticPrivacy()))
        self.assertEqual(report['ranking']['jobs'][0]['score_review']['excluded_mandatory_ids'], ['r'])
        c = compare(report, 'j1', 'j2')
        self.assertEqual(c.outcome, 'tie')
        self.assertTrue(all(not s.row.mandatory_applied for s in c.swings))


class RandomReportTests(unittest.TestCase):
    def test_outcome_matches_places_and_swings_really_swing(self):
        rng = random.Random(8)
        for _ in range(300):
            report = random_report(rng, rng.randint(2, 4))
            jobs = {j['job_id']: j for j in report['ranking']['jobs']}
            a, b = rng.sample(sorted(jobs), 2)
            c = compare(report, a, b)
            ra, rb = jobs[a]['rank'], jobs[b]['rank']
            self.assertEqual(c.outcome, 'tie' if ra == rb else 'a_higher' if ra < rb else 'b_higher')
            self.assertLessEqual(len(c.deciding), 3)
            if c.outcome == 'tie':
                self.assertEqual(c.deciding, [])
            listed = {(s.row.job_id, s.row.requirement_id) for s in c.swings}
            self.assertEqual(listed, self.expected_swings(jobs, a, b, c.outcome))

    @staticmethod
    def resolved(job, rid, status):
        """The job's score with one row resolved, computed straight from the report dict."""
        reqs = Requirements.model_validate(job['requirements'])
        ev = Evaluation.model_validate(job['evaluation'])
        ev.rows = [r.model_copy(update={'status': status}) if r.requirement_id == rid else r for r in ev.rows]
        evidence = PairCheck.model_validate(job['evidence_check'])
        evidence.rows = [c.model_copy(update={'status': status, 'state': 'structure_ok'}) if c.requirement_id == rid
                         else c for c in evidence.rows]
        return score(reqs, ev, evidence)

    def expected_swings(self, jobs, a, b, outcome):
        def places(sa, sb):
            ranked = rank([{'job_id': a, 'score': sa}, {'job_id': b, 'score': sb}], 2)['jobs']
            return {j['job_id']: j['rank'] for j in ranked}
        base = places(jobs[a]['score'], jobs[b]['score'])
        expected = set()
        for job_id, other in ((a, b), (b, a)):
            job = jobs[job_id]
            unresolved = [r['requirement_id'] for r in job['evaluation']['rows']
                          if r['status'] == 'unknown' or r['requirement_id'] in job['score']['disputed_ids']]
            higher = base[job_id] < base[other]
            for rid in unresolved:
                new = self.resolved(job, rid, 'fail' if higher else 'full')
                after = places(new, jobs[b]['score']) if job_id == a else places(jobs[a]['score'], new)
                if after != base:
                    expected.add((job_id, rid))
        return expected


if __name__ == '__main__':
    unittest.main()
