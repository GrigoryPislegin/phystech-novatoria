import asyncio
import unittest

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline


class IntegratedAnalysisTests(unittest.TestCase):
    def test_actual_pipeline_has_sourced_profile_evidence_scores_and_comparisons(self):
        model = ReplayModel()
        report = asyncio.run(run_pipeline(*demo_inputs(), model, SyntheticPrivacy()))
        self.assertEqual(model.calls, 7, 'Profile and conditions must share existing calls')
        self.assertIn('profile', list(report))
        self.assertEqual(report['profile']['display']['stack[0]'], 'Python')
        self.assertNotIn('last_position.role', report['profile']['display'])
        self.assertTrue(all(j['score']['evidence_applied'] for j in report['ranking']['jobs']))
        self.assertEqual(len(report['comparisons']), 2)
        self.assertTrue(report['review_queue']['items'])
        self.assertFalse(report['verification']['final_allowed'])

    def test_one_word_negated_quote_never_becomes_full_score_or_manager_ground(self):
        class Negated(ReplayModel):
            async def ask(self, schema, task, payload):
                value = await super().ask(schema, task, payload)
                if task == 'facts':
                    value.items[0].quote = 'Python'
                    if hasattr(value, 'profile'):
                        value.profile.summary[0].text = 'Python'
                        value.profile.summary[0].sources[0].quote = 'Python'
                return value
        report = asyncio.run(run_pipeline('Не работал с Python. Использовал SQL 1 год.',
            demo_inputs()[1], Negated(), SyntheticPrivacy()))
        job = next(j for j in report['ranking']['jobs'] if j['job_id'] == 'job-001')
        self.assertEqual(job['score']['lower'], 25)
        self.assertEqual(job['score']['upper'], 100)
        self.assertIn('r1', job['score']['disputed_ids'])
        shown = next(j for j in report['presentation']['jobs'] if j['job_id'] == 'job-001')
        self.assertNotIn('r1', [r['requirement_id'] for r in shown['manager_brief']['grounds']])

    def test_conditions_reach_report_with_both_sources_and_no_extra_calls(self):
        class ConditionsModel(ReplayModel):
            async def ask(self, schema, task, payload):
                value = await super().ask(schema, task, payload)
                data = value.model_dump()
                if task == 'facts':
                    data['items'].append({'id':'f3', 'text':'Удалённо', 'quote':'Только удалённая работа.'})
                if task == 'evaluation' and 'conditions' in schema.model_fields:
                    data['conditions'] = {'items':[{'kind':'work_mode', 'state':'conflict',
                        'cv':{'fact_id':'f3','quote':'Только удалённая работа.'},
                        'vacancy_quote':'Работа в офисе.', 'note':'Условия различаются.'}]}
                return schema.model_validate(data)
        resume, jobs = demo_inputs()
        jobs = [(jid, text + ' Работа в офисе.') for jid,text in jobs]
        model = ConditionsModel()
        report = asyncio.run(run_pipeline(resume + ' Только удалённая работа.', jobs, model, SyntheticPrivacy()))
        self.assertEqual(model.calls, 7)
        self.assertTrue(report['ranking']['complete'])
        self.assertIn('conditions', list(report['ranking']['jobs'][0]))
        self.assertEqual(report['ranking']['jobs'][0]['conditions']['conflicts'], ['work_mode'])
        self.assertTrue(any(i['reason_code'] == 'condition_conflict' for i in report['review_queue']['items']))

    def test_forged_profile_fact_is_not_published_as_valid_candidate(self):
        class Forged(ReplayModel):
            async def ask(self, schema, task, payload):
                value = await super().ask(schema, task, payload)
                if task == 'facts' and hasattr(value, 'profile'):
                    value.profile.stack[0].sources[0].fact_id = 'not-a-fact'
                return value
        report = asyncio.run(run_pipeline(*demo_inputs(), Forged(), SyntheticPrivacy()))
        self.assertFalse(report['ranking']['complete'])
        self.assertEqual(report['errors'][0]['code'], 'model_invalid')


if __name__ == '__main__':
    unittest.main()
