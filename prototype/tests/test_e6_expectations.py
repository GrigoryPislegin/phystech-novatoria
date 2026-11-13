"""E6: semantic expectations for frontend, fixed assets and education. Synthetic data only.

These tests check that the expectations are well-formed, consistent with the scoring policy and
that the holdout has not been edited. They do not measure model quality: no model is called.
"""
import hashlib
import itertools
import json
import unittest
from collections import Counter
from pathlib import Path

from prototype.contracts import Evaluation, Fact, Facts, Requirement, Requirements, Row
from prototype.evidence import Source, check_pair
from prototype.scoring import rank, score

ROOT = Path(__file__).resolve().parents[2] / 'evaluation' / 'expectations' / 'egor'
STATUSES = {'full', 'partial', 'fail', 'unknown'}
RECOMMENDATIONS = {'review_top', 'clarify', 'review_none_fit', 'incomplete'}
REQUIRED_COVERAGE = {'positive', 'negation', 'synonym', 'unknown_vs_fail', 'overlapping_periods', 'conditions',
                     'incomplete_run', 'equivalent_wording', 'learning_not_experience', 'education',
                     'ambiguous_status', 'prompt_injection', 'irrelevant_vacancy', 'related_not_equal'}
# Key behaviours must also appear in the holdout, in a different area than in dev where possible.
HOLDOUT_COVERAGE = {'negation', 'synonym', 'overlapping_periods', 'incomplete_run', 'unknown_vs_fail'}


def load():
    return json.loads((ROOT / 'e6-cases.json').read_text(encoding='utf-8'))


def processed(case):
    return [v['job_id'] for v in case['vacancies'] if v['job_id'] not in case['unprocessed_job_ids']]


def scored_run(case, statuses):
    """Score and rank one combination of statuses {key: status} the way the pipeline would."""
    results = []
    for job in processed(case):
        rows = [r for r in case['requirements'] if r['job_id'] == job]
        reqs = Requirements(items=[Requirement(id=r['key'], text=r['key'], quote=r['quote'],
                                               mandatory_quote=f"Обязательно: {r['quote']}" if r['mandatory'] else None)
                                   for r in rows])
        ev = Evaluation(rows=[Row(requirement_id=r['key'], status=statuses[r['key']],
                                  fact_ids=[] if statuses[r['key']] == 'unknown' else ['f'], comment='c', question=None)
                              for r in rows])
        results.append({'job_id': job, 'score': score(reqs, ev)})
    return rank(results, len(case['vacancies']))


class FormatTests(unittest.TestCase):
    def test_set_size_domains_and_coverage(self):
        cases = load()['cases']
        self.assertGreaterEqual(len(cases), 12)
        self.assertEqual(len({c['case_id'] for c in cases}), len(cases))
        domains = Counter(c['domain'] for c in cases)
        self.assertEqual(set(domains), {'frontend', 'fixed_assets', 'education'})
        self.assertTrue(all(n >= 4 for n in domains.values()), domains)
        self.assertLessEqual(REQUIRED_COVERAGE, {t for c in cases for t in c['covers']})
        self.assertLessEqual(HOLDOUT_COVERAGE, {t for c in cases if c['split'] == 'holdout' for t in c['covers']})

    def test_every_case_is_a_draft(self):
        self.assertTrue(all(c['decision_status'] == 'draft' for c in load()['cases']))

    def test_quotes_are_exact(self):
        for case in load()['cases']:
            texts = {v['job_id']: v['text'] for v in case['vacancies']}
            for r in case['requirements']:
                with self.subTest(case=case['case_id'], key=r['key']):
                    self.assertEqual(texts[r['job_id']].count(r['quote']), 1)
                    for quote in r['cv_quotes']:
                        self.assertIn(quote, case['cv_text'])

    def test_statuses_are_consistent(self):
        for case in load()['cases']:
            for r in case['requirements']:
                with self.subTest(case=case['case_id'], key=r['key']):
                    allowed, forbidden = set(r['allowed_status']), set(r['forbidden_status'])
                    self.assertTrue(allowed and allowed <= STATUSES and not allowed & forbidden)
                    self.assertEqual(allowed | forbidden, STATUSES)
                    if allowed == {'unknown'}:
                        self.assertEqual(r['cv_quotes'], [])
                    else:
                        self.assertTrue(r['cv_quotes'], 'a known status needs a CV quote')

    def test_every_processed_vacancy_has_all_its_requirements(self):
        for case in load()['cases']:
            keys = Counter(r['job_id'] for r in case['requirements'])
            for job in processed(case):
                self.assertEqual(keys[job], 3, (case['case_id'], job))
            self.assertLessEqual(set(case['ranking']['allowed_recommendations']), RECOMMENDATIONS)

    def test_equivalent_wordings_share_expectations(self):
        groups = {}
        for case in load()['cases']:
            if case['equivalence_group']:
                statuses = sorted((r['key'], tuple(sorted(r['allowed_status']))) for r in case['requirements'])
                expectation = (tuple(statuses), tuple(case['ranking']['allowed_recommendations']))
                groups.setdefault(case['equivalence_group'], []).append(expectation)
        self.assertTrue(groups)
        for name, items in groups.items():
            with self.subTest(name):
                self.assertGreaterEqual(len(items), 2)
                self.assertEqual(len(set(items)), 1)

    def test_holdout_is_frozen(self):
        cases = load()['cases']
        holdout = [c for c in cases if c['split'] == 'holdout']
        recorded, *ids = (ROOT / 'holdout.sha256').read_text().split()
        canon = json.dumps(holdout, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        self.assertEqual([c['case_id'] for c in holdout], ids)
        self.assertEqual(hashlib.sha256(canon.encode()).hexdigest(), recorded,
                         'Holdout changed after it was fixed; record the change and the reason.')
        self.assertEqual({c['domain'] for c in holdout}, {'frontend', 'fixed_assets', 'education'})


class PolicyConsistencyTests(unittest.TestCase):
    def test_every_allowed_combination_gives_an_allowed_outcome(self):
        for case in load()['cases']:
            rows = [r for r in case['requirements'] if r['job_id'] in processed(case)]
            allowed = set(case['ranking']['allowed_recommendations'])
            for combo in itertools.product(*(r['allowed_status'] for r in rows)):
                run = scored_run(case, {r['key']: s for r, s in zip(rows, combo)})
                with self.subTest(case=case['case_id'], combo=combo):
                    self.assertIn(run['recommendation'], allowed)
                    place = {j['job_id']: j['rank'] for j in run['jobs']}
                    for rel in case['ranking']['relations']:
                        better, worse = place[rel['better']], place[rel['worse']]
                        self.assertTrue(better < worse if rel['strict'] else better <= worse)

    def test_unprocessed_vacancy_always_means_incomplete(self):
        for case in load()['cases']:
            if case['unprocessed_job_ids']:
                self.assertEqual(case['ranking']['allowed_recommendations'], ['incomplete'])


class EvidenceMeasurementTests(unittest.TestCase):
    """How E3 treats the expected (correct) quotes. A measurement, not a pass/fail quality claim."""

    def review_rows(self):
        flagged, total = [], 0
        for case in load()['cases']:
            for job in processed(case):
                rows = [r for r in case['requirements'] if r['job_id'] == job and r['allowed_status'][0] != 'unknown']
                facts, items, ev_rows = [], [], []
                for r in rows:
                    ids = []
                    for quote in r['cv_quotes']:
                        ids.append(f'f{len(facts)}')
                        facts.append(Fact(id=ids[-1], text='факт', quote=quote))
                    items.append(Requirement(id=r['key'], text=r['quote'], quote=r['quote'], mandatory_quote=None))
                    ev_rows.append(Row(requirement_id=r['key'], status=r['allowed_status'][0], fact_ids=ids,
                                       comment='c', question=None))
                if not rows:
                    continue
                vacancy = next(v['text'] for v in case['vacancies'] if v['job_id'] == job)
                check = check_pair(Requirements(items=items), Facts(items=facts), Evaluation(rows=ev_rows),
                                   Source.of('cv', case['cv_text']), Source.of(job, vacancy))
                total += len(check.rows)
                self.assertFalse(check.has_invalid, case['case_id'])
                flagged += [(case['case_id'], c.requirement_id) for c in check.rows if c.state == 'needs_review']
        return flagged, total

    def test_only_explained_cases_go_to_review(self):
        # Expected quotes are structurally valid, and E3 sends a correct row to review only where the case
        # relies on a synonym or on a supporting sentence without a shared term (split_evidence).
        # Fewer flagged rows after an E3 improvement still pass.
        flagged, total = self.review_rows()
        explained_cases = {c['case_id'] for c in load()['cases'] if {'synonym', 'split_evidence'} & set(c['covers'])}
        self.assertGreater(total, 0)
        self.assertLessEqual({case_id for case_id, _ in flagged}, explained_cases)


if __name__ == '__main__':
    unittest.main()
