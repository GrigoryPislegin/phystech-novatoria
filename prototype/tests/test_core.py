import unittest

from prototype.contracts import Fact, Facts, Requirement, Requirements, Row, Evaluation, validate_pair
from prototype.scoring import score, rank


def reqs():
    return Requirements(items=[
        Requirement(id='r1', text='Python', quote='Python обязателен', mandatory_quote='Python обязателен'),
        Requirement(id='r2', text='SQL', quote='SQL', mandatory_quote=None),
    ])


def evaluation(a='full', b='unknown'):
    return Evaluation(rows=[
        Row(requirement_id='r1', status=a, fact_ids=[] if a == 'unknown' else ['f1'], comment='Проверить опыт', question='Есть опыт?' if a != 'full' else None),
        Row(requirement_id='r2', status=b, fact_ids=[] if b == 'unknown' else ['f1'], comment='Нет сведений', question='Есть SQL?' if b != 'full' else None),
    ])


class CoreTests(unittest.TestCase):
    def test_unknown_is_not_failure(self):
        s = score(reqs(), evaluation())
        self.assertEqual((s['lower'], s['upper'], s['coverage']), (75, 100, 75))
        self.assertEqual(s['mandatory'], 'confirmed')
        failed = score(reqs(), evaluation(b='fail'))
        self.assertEqual((failed['lower'], failed['upper'], failed['coverage']), (75, 75, 100))

    def test_mandatory_unknown_needs_clarification(self):
        self.assertEqual(score(reqs(), evaluation(a='unknown'))['mandatory'], 'clarify')
        self.assertEqual(score(reqs(), evaluation(a='fail'))['mandatory'], 'violated')
        self.assertEqual(score(reqs(), evaluation(a='partial'))['mandatory'], 'clarify')

    def test_evidence_and_requirement_coverage(self):
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Разрабатывал на Python')])
        validate_pair(reqs(), facts, evaluation())
        bad = evaluation(); bad.rows[0].fact_ids = ['invented']
        with self.assertRaises(ValueError): validate_pair(reqs(), facts, bad)
        bad = evaluation(); bad.rows.append(bad.rows[0])
        with self.assertRaises(ValueError): validate_pair(reqs(), facts, bad)
        bad = evaluation(); bad.rows.pop()
        with self.assertRaises(ValueError): validate_pair(reqs(), facts, bad)
        bad = evaluation(); bad.rows[0].fact_ids = []
        with self.assertRaises(ValueError): validate_pair(reqs(), facts, bad)

    def test_exact_quotes_and_unique_ids(self):
        reqs().validate_source('Python обязателен. SQL')
        with self.assertRaises(ValueError): reqs().validate_source('только Excel')
        facts = Facts(items=[Fact(id='f1', text='вывод', quote='выдуманная цитата')])
        with self.assertRaises(ValueError): facts.validate_source('исходный документ')
        r = reqs(); r.items[1].id = 'r1'
        with self.assertRaises(ValueError): r.validate_source('Python обязателен SQL')

    def test_none_fits_requires_all_results(self):
        result = {'job_id':'j1', 'score':score(reqs(), evaluation(a='fail'))}
        self.assertEqual(rank([result], 1)['recommendation'], 'review_none_fit')
        self.assertEqual(rank([result], 2)['recommendation'], 'incomplete')
        result['score'] = score(reqs(), evaluation(a='unknown'))
        self.assertEqual(rank([result], 1)['recommendation'], 'clarify')

    def test_ties_and_mandatory_sorting(self):
        items = [{'job_id':x, 'score':score(reqs(), evaluation())} for x in ['j2', 'j1']]
        result = rank(items, 2)
        self.assertEqual([x['rank'] for x in result['jobs']], [1, 1])
        self.assertEqual([x['job_id'] for x in result['jobs']], ['j1', 'j2'])

    def test_top_tie_recommendation_does_not_depend_on_filename(self):
        items = [{'job_id':'a', 'score':{'lower':50,'mandatory':'confirmed'}},
                 {'job_id':'b', 'score':{'lower':50,'mandatory':'clarify'}}]
        first = rank(items, 2)['recommendation']
        items[0]['job_id'], items[1]['job_id'] = 'b', 'a'
        self.assertEqual(first, rank(items, 2)['recommendation'])
        self.assertEqual(first, 'clarify')

    def test_model_judgment_never_proves_final_none_fit(self):
        facts = Facts(items=[Fact(id='f1', text='Python', quote='Python')])
        ev = evaluation(a='fail', b='fail')
        validate_pair(reqs(), facts, ev)  # Structural validation cannot prove semantic entailment.
        result = rank([{'job_id':'j1','score':score(reqs(),ev)}],1)
        self.assertNotEqual(result['recommendation'], 'none_fit')
        self.assertTrue(result['requires_human_review'])


if __name__ == '__main__': unittest.main()
