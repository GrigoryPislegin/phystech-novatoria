import asyncio
import json
import unittest

from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.pipeline import run_pipeline


class IntegratedAnalysisTests(unittest.TestCase):
    def test_duplicate_unit_with_conflicting_or_missing_labels_stays_outside_chart(self):
        class DuplicateModel(ReplayModel):
            def __init__(self, second):
                super().__init__()
                self.second = second

            async def ask(self, schema, task, payload):
                if task == 'requirements':
                    labels = [{'requirement_id':'r1', 'factor':'stack'}]
                    if self.second is not None:
                        labels.append({'requirement_id':'r2', 'factor':self.second})
                    return schema.model_validate({'items':[
                        {'id':rid, 'text':quote, 'quote':quote, 'mandatory_quote':None}
                        for rid, quote in [('r1','Python'), ('r2','Python.')]], 'factors':{'items':labels}})
                if task == 'evaluation':
                    return schema.model_validate({'rows':[
                        {'requirement_id':rid, 'status':'full', 'fact_ids':['f1'], 'comment':'Python', 'question':None}
                        for rid in ('r1','r2')], 'conditions':{'items':[]}})
                return await super().ask(schema, task, payload)

        def result(label):
            report = asyncio.run(run_pipeline(demo_inputs()[0], [('j1','Python.')],
                                               DuplicateModel(label), SyntheticPrivacy()))
            self.assertEqual(report['errors'], [])
            return report['ranking']['jobs'][0]

        baseline = result('stack')
        self.assertEqual(len(baseline['score']['units']), 1)
        self.assertEqual(baseline['competency_axes']['axes'][0]['weight'], 100)
        for label in ('management', 'other', 'conditions', None):
            with self.subTest(second_label=label):
                job = result(label)
                self.assertEqual(job['score'], baseline['score'])
                self.assertEqual(job['competency_axes']['axes'], [])
                self.assertEqual(job['competency_axes']['outside_weight'], 100)

    def test_competency_labels_share_requirements_request_and_keep_score_unchanged(self):
        from prototype.tests.test_e13_support import load_fixture, run
        fixture = load_fixture('analytics')
        labels = {'r1':'relevant_experience', 'r2':'stack', 'r3':'relevant_experience',
                  'r4':'stack', 'r5':'stack', 'r6':'stack', 'r7':'domain', 'r8':'language', 'r9':'management'}

        def add_labels(task, jid, answer):
            if task == 'requirements' and jid == 'an-1':
                answer['factors'] = {'items':[{'requirement_id':rid, 'factor':factor}
                                             for rid, factor in labels.items()]}

        baseline, _ = run(fixture)
        report, replay = run(fixture, faults={'edit':add_labels})
        self.assertEqual(len(replay.requests), 7)
        original = {j['job_id']:j for j in baseline['ranking']['jobs']}
        for job in report['ranking']['jobs']:
            self.assertEqual(job['score'], original[job['job_id']]['score'])
            self.assertEqual(job['rank'], original[job['job_id']]['rank'])
            axes = job['competency_axes']
            if job['job_id'] == 'an-1':
                self.assertTrue(axes['radar_ready'])
                self.assertEqual(len(axes['axes']), 5)
                self.assertAlmostEqual(sum(a['weight'] for a in axes['axes']) + axes['outside_weight'], 100)
                self.assertEqual({r for a in axes['axes'] for r in a['requirement_ids']}, set(labels))
            else:
                self.assertEqual(axes['reason'], 'no_labels')
                self.assertFalse(axes['radar_ready'])
        for raw in replay.outbound:
            request = json.loads(raw)
            if json.loads(request['input'][1]['content'])['task'] == 'requirements':
                self.assertIn('factors', request['text']['format']['schema']['required'])

    def test_forged_competency_labels_are_rejected_before_evaluation(self):
        from prototype.tests.test_e13_support import load_fixture, run

        def forge(task, jid, answer):
            if task == 'requirements' and jid == 'an-1':
                answer['factors'] = {'items':[{'requirement_id':'nonexistent', 'factor':'stack'}]}

        report, replay = run(load_fixture('analytics'), faults={'edit':forge})
        self.assertEqual(report['unprocessed_job_ids'], ['an-1'])
        self.assertEqual(report['errors'][0]['code'], 'model_invalid')
        self.assertEqual(replay.requests.count(('requirements', 'an-1')), 2)
        self.assertNotIn(('evaluation', 'an-1'), replay.requests)

    def test_refresh_legacy_report_without_axes_or_additive_score_fields(self):
        from prototype.pipeline import refresh_derived
        report = asyncio.run(run_pipeline(*demo_inputs(), ReplayModel(), SyntheticPrivacy()))
        report['ranking']['leader'].pop('comparable')
        for job in report['ranking']['jobs']:
            job.pop('requirement_factors')
            job.pop('competency_axes')
            job['score'].pop('shares')
            job['score'].pop('breakdown')
        scores = [json.dumps(job['score'], sort_keys=True) for job in report['ranking']['jobs']]
        refresh_derived(report)
        self.assertEqual(scores, [json.dumps(job['score'], sort_keys=True) for job in report['ranking']['jobs']])
        self.assertTrue(all(job['competency_axes'] is None for job in report['ranking']['jobs']))

    def test_snapshot_sink_receives_processed_sources_before_model(self):
        captured = []
        class Replacing(SyntheticPrivacy):
            async def redact(self, text):
                return text.replace('PRIVATE-NAME ', '')
        model = ReplayModel()
        resume, jobs = demo_inputs()
        def sink(value):
            self.assertEqual(model.calls, 0)
            captured.append(value)
        report = asyncio.run(run_pipeline('PRIVATE-NAME ' + resume, jobs, model, Replacing(), source_sink=sink))
        self.assertTrue(report['ranking']['complete'])
        self.assertEqual(captured, [{'resume':resume, 'jobs':dict(jobs)}])

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
        self.assertTrue(report['ranking']['complete'])
        self.assertEqual(report['profile']['state'], 'invalid')
        self.assertTrue(any(i['reason_code'] == 'profile_review' for i in report['review_queue']['items']))
        self.assertTrue(all(h['state'] != 'reviewed_for_handoff' for h in report['handoff']))


if __name__ == '__main__':
    unittest.main()
