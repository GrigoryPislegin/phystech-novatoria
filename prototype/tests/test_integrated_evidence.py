import asyncio
import unittest
from prototype.contracts import Requirement, Requirements, Facts, Fact, Row, Evaluation
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs
from prototype.evidence import Source, locate, verify_span, check_mandatory, sha256_text
from prototype.pipeline import run_pipeline
from prototype.requirements_review import ApprovalCheck, approve, check, summarize, _hash


class IntegratedEvidenceTests(unittest.TestCase):
    def test_foreign_check_cannot_confirm_run(self):
        foreign = ApprovalCheck(vacancy_id='other', state='confirmed', reasons=[])
        result = summarize(True, {'wanted':foreign}, expected_ids=['wanted'])
        self.assertFalse(result.final_allowed)
        self.assertEqual(result.invalid, ['wanted'])

    def test_duplicate_saved_requirement_cannot_confirm_run(self):
        reqs = Requirements(items=[Requirement(id='r', text='Python', quote='Python', mandatory_quote=None)])
        approval = approve('job', 'Python', reqs, 'synthetic-date')
        approval.requirements.append(approval.requirements[0])
        approval.requirements_sha256 = _hash(approval.requirements)
        self.assertEqual(check(approval, 'job', 'Python', reqs).state, 'invalid')
        reqs.items.append(reqs.items[0])
        with self.assertRaises(ValueError): approve('job', 'Python', reqs, 'synthetic-date')

    def test_saved_context_is_not_trusted(self):
        source = Source.of('cv', 'Не работал с Python.')
        span = locate(source, 'Python').span
        span.sentence = 'Работал с Python.'
        self.assertEqual(verify_span(span, {'cv':source})[0].code, 'context_mismatch')

    def test_pipeline_exports_context_and_does_not_auto_confirm(self):
        class Fragment(ReplayModel):
            async def ask(self, schema, task, payload):
                result = await super().ask(schema, task, payload)
                if task == 'facts':
                    result.items[0].quote = 'Python'
                    result.profile.summary[0].text = 'Python'
                    result.profile.summary[0].sources[0].quote = 'Python'
                return result
        report = asyncio.run(run_pipeline(*demo_inputs(), Fragment(), SyntheticPrivacy()))
        self.assertTrue(report['ranking']['complete'])
        self.assertFalse(report['requirements_review']['requirements_confirmed'])
        row = report['presentation']['jobs'][0]['rows'][0]
        self.assertEqual(row['evidence_check']['state'], 'needs_review')
        self.assertIn('quote_is_fragment', [r['code'] for r in row['evidence_check']['reasons']])
        self.assertFalse(report['presentation']['final_allowed'])

    def test_opposite_headings_make_repeated_quote_ambiguous(self):
        result = locate(Source.of('cv', 'Работал с:\n- Python\n\nНе работал с:\n- Python'), 'Python')
        self.assertIsNone(result.span)
        self.assertEqual(result.reason.code, 'ambiguous_location')
        self.assertTrue(any('Не работал' in c for c in result.contexts))

    def test_copied_source_cache_cannot_supply_old_context(self):
        source = Source.of('cv', 'Работал с Python.')
        span = locate(source, 'Python').span
        text = 'Не знает: Python.'
        updated = source.model_copy(update={'text':text, 'sha256':sha256_text(text)})
        span.source_sha256 = updated.sha256
        self.assertEqual(verify_span(span, {'cv':updated})[0].code, 'context_mismatch')

    def test_contiguous_heading_and_bullet_are_valid_marker(self):
        source = Source.of('job', 'Обязательно:\n- Python')
        requirement = Requirement(id='r', text='Python', quote='Python', mandatory_quote=source.text)
        self.assertEqual(check_mandatory(requirement, source).state, 'structure_ok')

    def test_unbound_mandatory_cannot_demote_job_to_violated(self):
        class WrongMarker(ReplayModel):
            async def ask(self, schema, task, payload):
                if task == 'facts':
                    return schema(items=[Fact(id='f',text='Нет Python',quote='Не работал с Python.')], profile=dict(summary=[], stack=[], last_position=None, achievements=[], missing=['summary','stack','last_position','achievements']))
                if task == 'requirements':
                    return Requirements(items=[Requirement(id='r',text='Python',quote='Python',mandatory_quote=payload['text'])])
                return schema(rows=[Row(requirement_id='r',status='fail',fact_ids=['f'],comment='Нет Python',question='Какой опыт?')], conditions={'items':[]})
        result = asyncio.run(run_pipeline('Не работал с Python.', [('j','Обязательно: SQL. Python желателен.')], WrongMarker(), SyntheticPrivacy()))
        job = result['ranking']['jobs'][0]
        self.assertEqual(job['score']['mandatory'], 'not_set')
        self.assertEqual(job['score_review']['excluded_mandatory_ids'], ['r'])
        self.assertFalse(result['presentation']['jobs'][0]['rows'][0]['mandatory_applied_to_score'])
