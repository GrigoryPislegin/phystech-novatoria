"""Policy draft-2026-11-13-v2: disputed evidence, mandatory filter, invariants. Synthetic data only."""
import asyncio
import random
import unittest

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.evidence import MandatoryCheck, PairCheck, RowCheck, Source, check_pair
from prototype.pipeline import run_pipeline
from prototype.scoring import POLICY_VERSION, rank, score

STATUSES = ('full', 'partial', 'fail', 'unknown')


def case(cv, vacancy, fact_quote, status, *, quote, mandatory=None):
    """One requirement, one fact; evidence is the real E3 check on the texts."""
    requirements = Requirements(items=[Requirement(id='r1', text='Python', quote=quote, mandatory_quote=mandatory)])
    facts = Facts(items=[Fact(id='f1', text='факт', quote=fact_quote)])
    row = Row(requirement_id='r1', status=status, fact_ids=[] if status == 'unknown' else ['f1'],
              comment='синтетика', question=None if status == 'full' else 'Уточните опыт.')
    evaluation = Evaluation(rows=[row])
    evidence = check_pair(requirements, facts, evaluation, Source.of('cv', cv), Source.of('job', vacancy))
    return requirements, evaluation, evidence


class DisputedEvidenceTests(unittest.TestCase):
    def test_negated_skill_with_fragment_quote_is_not_counted(self):
        reqs, ev, evidence = case('Аналитик. Не работал с Python, планирую изучить.', 'Нужен Python.',
                                  'Python', 'full', quote='Python')
        self.assertEqual(score(reqs, ev)['lower'], 100)  # without evidence: the v1 failure
        s = score(reqs, ev, evidence)
        self.assertEqual((s['lower'], s['upper'], s['coverage']), (0, 100, 0))
        self.assertEqual(s['disputed_ids'], ['r1'])
        self.assertEqual(rank([{'job_id': 'job', 'score': s}], 1)['recommendation'], 'clarify')

    def test_irrelevant_fact_cannot_violate_mandatory(self):
        for fact in ('Excel', 'Работал с Excel.'):
            with self.subTest(fact):
                reqs, ev, evidence = case('Работал с Excel.', 'Python обязателен.', fact, 'fail',
                                          quote='Python обязателен.', mandatory='Python обязателен.')
                self.assertEqual(score(reqs, ev)['mandatory'], 'violated')
                s = score(reqs, ev, evidence)
                self.assertEqual(s['mandatory'], 'clarify')
                self.assertNotEqual(rank([{'job_id': 'job', 'score': s}], 1)['recommendation'], 'review_none_fit')

    def test_structurally_supported_fail_still_violates(self):
        reqs, ev, evidence = case('Не работал с Python.', 'Python обязателен.', 'Не работал с Python.', 'fail',
                                  quote='Python обязателен.', mandatory='Python обязателен.')
        s = score(reqs, ev, evidence)
        self.assertEqual((s['mandatory'], s['disputed_ids']), ('violated', []))
        self.assertEqual(rank([{'job_id': 'job', 'score': s}], 1)['recommendation'], 'review_none_fit')

    def test_unbound_mandatory_marker_gets_regular_weight(self):
        vacancy = 'Обязательно: SQL. Python желателен.'
        reqs, ev, evidence = case('Не работал с Python.', vacancy, 'Не работал с Python.', 'fail',
                                  quote='Python', mandatory=vacancy)
        s = score(reqs, ev, evidence)
        self.assertEqual((s['mandatory'], s['excluded_mandatory_ids']), ('not_set', ['r1']))

    def test_disputed_optional_row_at_the_top_asks_to_clarify(self):
        reqs = Requirements(items=[
            Requirement(id='r1', text='Python', quote='Python обязателен.', mandatory_quote='Python обязателен.'),
            Requirement(id='r2', text='Go', quote='Go', mandatory_quote=None)])
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Разрабатывал на Python 3 года.'),
                             Fact(id='f2', text='Go', quote='Go')])
        ev = Evaluation(rows=[Row(requirement_id='r1', status='full', fact_ids=['f1'], comment='c', question=None),
                              Row(requirement_id='r2', status='full', fact_ids=['f2'], comment='c', question=None)])
        evidence = check_pair(reqs, facts, ev, Source.of('cv', 'Разрабатывал на Python 3 года. Не знаю Go.'),
                              Source.of('job', 'Python обязателен. Желателен Go.'))
        s = score(reqs, ev, evidence)
        self.assertEqual((s['mandatory'], s['disputed_ids'], s['lower']), ('confirmed', ['r2'], 75))
        self.assertEqual(rank([{'job_id': 'job', 'score': s}], 1)['recommendation'], 'clarify')
        self.assertEqual(rank([{'job_id': 'job', 'score': score(reqs, ev)}], 1)['recommendation'], 'review_top')

    def test_lower_job_with_doubted_rows_that_could_overtake_keeps_clarify(self):
        # E9c: CV «Навыки:\n- Python 5 лет»: the bullet is disputed (heading_context), so the Python vacancy
        # has L=0, H=100 and sits second, yet resolving that one row would tie first place.
        top = {'lower': 100.0, 'upper': 100.0, 'mandatory': 'not_set', 'disputed_ids': [],
               'excluded_mandatory_ids': []}
        doubted = {'lower': 0.0, 'upper': 100.0, 'mandatory': 'clarify', 'disputed_ids': ['r1'],
                   'excluded_mandatory_ids': []}
        jobs = [{'job_id': 'b', 'score': top}, {'job_id': 'a', 'score': doubted}]
        self.assertEqual(rank(jobs, 2)['recommendation'], 'clarify')
        unreachable = {**doubted, 'upper': 90.0}
        self.assertEqual(rank([jobs[0], {'job_id': 'a', 'score': unreachable}], 2)['recommendation'], 'review_top')
        plain_unknown = {**doubted, 'disputed_ids': []}  # ordinary missing data does not hold the top open
        self.assertEqual(rank([jobs[0], {'job_id': 'a', 'score': plain_unknown}], 2)['recommendation'], 'review_top')

    def test_invalid_evidence_is_an_error_not_unknown(self):
        reqs, ev, evidence = case('Python 3 года.', 'Нужен Python.', 'Python 3 года.', 'full', quote='Python')
        broken = evidence.model_copy(update={'has_invalid': True})
        with self.assertRaisesRegex(ValueError, 'invalid_evidence'):
            score(reqs, ev, broken)

    def test_evidence_must_match_the_rows_it_scores(self):
        reqs, ev, evidence = case('Python 3 года.', 'Нужен Python.', 'Python 3 года.', 'full', quote='Python')
        row, marker = evidence.rows[0], evidence.mandatory[0]
        broken = {
            'missing row check': {'rows': []},
            'invalid state, flag false': {'rows': [row.model_copy(update={'state': 'invalid'})]},
            'status mismatch': {'rows': [row.model_copy(update={'status': 'fail'})]},
            'extra id': {'rows': [row, row.model_copy(update={'requirement_id': 'r9'})]},
            'row for another id': {'rows': [row.model_copy(update={'requirement_id': 'r9'})]},
            'marker for another id': {'mandatory': [marker.model_copy(update={'requirement_id': 'r9'})]},
            'missing marker check': {'mandatory': []},
            'invalid marker': {'mandatory': [marker.model_copy(update={'state': 'invalid'})]},
        }
        self.assertEqual(score(reqs, ev, evidence)['lower'], 100)
        for name, update in broken.items():
            with self.subTest(name), self.assertRaisesRegex(ValueError, 'invalid_evidence'):
                score(reqs, ev, evidence.model_copy(update=update))

    def test_unapplied_marker_keeps_the_top_place_open(self):
        def job(marker_state):
            reqs = Requirements(items=[
                Requirement(id='r1', text='a', quote='a', mandatory_quote='обязательно a'),
                Requirement(id='r2', text='b', quote='b', mandatory_quote=None)])
            ev = Evaluation(rows=[Row(requirement_id='r1', status='fail', fact_ids=['f'], comment='c', question='q'),
                                  Row(requirement_id='r2', status='full', fact_ids=['f'], comment='c', question=None)])
            rows = [RowCheck(requirement_id=r.requirement_id, status=r.status, state='structure_ok', reasons=[],
                             evidence=[]) for r in ev.rows]
            markers = [MandatoryCheck(requirement_id='r1', state=marker_state, reasons=[]),
                       MandatoryCheck(requirement_id='r2', state='not_mandatory', reasons=[])]
            return score(reqs, ev, PairCheck(cv_sha256='c', vacancy_id='job', vacancy_sha256='v', rows=rows,
                                             mandatory=markers, needs_review=False, has_invalid=False))
        unbound, confirmed = job('needs_review'), job('structure_ok')
        self.assertEqual((unbound['lower'], unbound['mandatory']), (50, 'not_set'))
        self.assertEqual((confirmed['lower'], confirmed['mandatory']), (25, 'violated'))
        # Confirming a marker can lower L, so a job with an unapplied marker is never a plain review_top.
        self.assertEqual(rank([{'job_id': 'job', 'score': unbound}], 1)['recommendation'], 'clarify')

    def test_policy_version(self):
        reqs, ev, evidence = case('Python 3 года.', 'Нужен Python.', 'Python 3 года.', 'full', quote='Python')
        s = score(reqs, ev, evidence)
        self.assertEqual((s['policy_version'], s['evidence_applied']), (POLICY_VERSION, True))
        self.assertFalse(score(reqs, ev)['evidence_applied'])


class ReplayTests(unittest.TestCase):
    def test_replays_keep_places_and_recommendation_with_evidence(self):
        for scenario in ('success', 'disputed'):
            with self.subTest(scenario):
                report = asyncio.run(run_pipeline(*demo_inputs(scenario), ReplayModel(), SyntheticPrivacy()))
                jobs = report['ranking']['jobs']
                rescored = [{'job_id': j['job_id'], 'score': score(
                    Requirements.model_validate(j['requirements']), Evaluation.model_validate(j['evaluation']),
                    PairCheck.model_validate(j['evidence_check']))} for j in jobs]
                again = rank(rescored, len(jobs))
                self.assertEqual(again['recommendation'], report['ranking']['recommendation'])
                places = {j['job_id']: j['rank'] for j in jobs}
                self.assertEqual({j['job_id']: j['rank'] for j in again['jobs']}, places)
                self.assertEqual({j['job_id']: j['score']['lower'] for j in again['jobs']},
                                 {j['job_id']: j['score']['lower'] for j in jobs})


def random_job(rng, n=None):
    """Requirements, evaluation and a hand-built evidence check with random states."""
    n = n or rng.randint(1, 6)
    items, rows, row_checks, marker_checks = [], [], [], []
    for i in range(n):
        rid, mandatory = f'r{i}', rng.random() < 0.4
        status = rng.choice(STATUSES)
        marker = f'обязательно ц{i}' if mandatory else None
        items.append(Requirement(id=rid, text=f'т{i}', quote=f'ц{i}', mandatory_quote=marker))
        rows.append(Row(requirement_id=rid, status=status, fact_ids=[] if status == 'unknown' else ['f1'],
                        comment='c', question=None))
        state = 'no_evidence' if status == 'unknown' else rng.choice(['structure_ok', 'needs_review'])
        row_checks.append(RowCheck(requirement_id=rid, status=status, state=state, reasons=[], evidence=[]))
        marker_state = rng.choice(['structure_ok', 'needs_review']) if mandatory else 'not_mandatory'
        marker_checks.append(MandatoryCheck(requirement_id=rid, state=marker_state, reasons=[]))
    evidence = PairCheck(cv_sha256='c', vacancy_id='job', vacancy_sha256='v', rows=row_checks,
                         mandatory=marker_checks, needs_review=False, has_invalid=False)
    return Requirements(items=items), Evaluation(rows=rows), evidence


def with_status(job, rid, status, state=None):
    reqs, ev, evidence = job
    rows = [r.model_copy(update={'status': status}) if r.requirement_id == rid else r for r in ev.rows]
    checks = [c.model_copy(update={'status': status, 'state': state or c.state}) if c.requirement_id == rid else c
              for c in evidence.rows]
    return reqs, Evaluation(rows=rows), evidence.model_copy(update={'rows': checks})


def shuffled_and_renamed(job, rng):
    reqs, ev, evidence = job
    ids = [r.id for r in reqs.items]
    new = dict(zip(ids, rng.sample([f'x{i}' for i in range(len(ids))], len(ids))))
    def rename(items, field):
        out = [x.model_copy(update={field: new[getattr(x, field)]}) for x in items]
        rng.shuffle(out)
        return out
    moved = (Requirements(items=rename(reqs.items, 'id')), Evaluation(rows=rename(ev.rows, 'requirement_id')),
             evidence.model_copy(update={'rows': rename(evidence.rows, 'requirement_id'),
                                         'mandatory': rename(evidence.mandatory, 'requirement_id')}))
    return moved, new


def essence(s, names=None):
    names = names or {}
    ids = lambda key: sorted(names.get(i, i) for i in s[key])
    return s['lower'], s['upper'], s['coverage'], s['mandatory'], ids('disputed_ids'), ids('excluded_mandatory_ids')


class InvariantTests(unittest.TestCase):
    RUNS = 2000

    def test_bounds(self):
        rng = random.Random(1)
        for _ in range(self.RUNS):
            s = score(*random_job(rng))
            self.assertTrue(0 <= s['lower'] <= s['upper'] <= 100)

    def test_permutation_and_renaming_do_not_change_score(self):
        rng = random.Random(2)
        for _ in range(self.RUNS):
            job = random_job(rng)
            moved, names = shuffled_and_renamed(job, rng)
            self.assertEqual(essence(score(*job), names), essence(score(*moved)))

    def test_only_a_verified_mandatory_fail_violates(self):
        rng = random.Random(3)
        violated = 0
        for _ in range(self.RUNS):
            reqs, ev, evidence = job = random_job(rng)
            rows = {c.requirement_id: c for c in evidence.rows}
            markers = {c.requirement_id: c.state for c in evidence.mandatory}
            expected = any(r.mandatory_quote and markers[r.id] == 'structure_ok'
                           and rows[r.id].status == 'fail' and rows[r.id].state == 'structure_ok'
                           for r in reqs.items)
            self.assertEqual(score(*job)['mandatory'] == 'violated', expected)
            violated += expected
        self.assertGreater(violated, 100)  # the generator does produce violations

    def test_stronger_status_never_lowers_lower_bound(self):
        rng = random.Random(4)
        for _ in range(self.RUNS):
            job = random_job(rng)
            rid = rng.choice(job[0].items).id
            state = rng.choice(['structure_ok', 'needs_review'])
            lowers = [score(*with_status(job, rid, st, state))['lower'] for st in ('fail', 'partial', 'full')]
            self.assertEqual(lowers, sorted(lowers))

    def test_disputed_row_moves_only_upper_bound(self):
        rng = random.Random(5)
        for _ in range(self.RUNS):
            job = random_job(rng)
            rid = rng.choice(job[0].items).id
            status = rng.choice(['full', 'partial', 'fail'])
            verified = score(*with_status(job, rid, status, 'structure_ok'))
            disputed = score(*with_status(job, rid, status, 'needs_review'))
            unknown = score(*with_status(job, rid, 'unknown', 'no_evidence'))
            self.assertEqual((disputed['lower'], disputed['upper']), (unknown['lower'], unknown['upper']))
            self.assertLessEqual(disputed['lower'], verified['lower'])
            self.assertGreaterEqual(disputed['upper'], verified['upper'])
            self.assertEqual(disputed['mandatory'], unknown['mandatory'])  # a disputed fail never violates

    def test_ranking_ignores_job_order_and_names(self):
        rng = random.Random(6)
        for _ in range(500):
            jobs = [{'job_id': f'j{i}', 'score': score(*random_job(rng))} for i in range(rng.randint(1, 5))]
            base = rank(jobs, len(jobs))
            ids = [j['job_id'] for j in jobs]
            names = dict(zip(ids, rng.sample([f'k{i}' for i in range(len(ids))], len(ids))))
            moved = [{'job_id': names[j['job_id']], 'score': j['score']} for j in jobs]
            rng.shuffle(moved)
            other = rank(moved, len(jobs))
            self.assertEqual(base['recommendation'], other['recommendation'])
            self.assertEqual({names[j['job_id']]: j['rank'] for j in base['jobs']},
                             {j['job_id']: j['rank'] for j in other['jobs']})

    def test_incomplete_run_never_says_none_fit(self):
        rng = random.Random(7)
        for _ in range(500):
            jobs = [{'job_id': f'j{i}', 'score': score(*random_job(rng))} for i in range(rng.randint(1, 4))]
            self.assertEqual(rank(jobs, len(jobs) + 1)['recommendation'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
