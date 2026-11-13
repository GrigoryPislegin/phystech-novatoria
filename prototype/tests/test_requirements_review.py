"""E4: recruiter confirmation of the extracted requirement list. Synthetic vacancies only."""
import unittest

from prototype.contracts import Requirement, Requirements
from prototype.requirements_review import (INTEGRATED, approve, check, draft, requirements_sha256, source_sha256,
                                           summarize)

TEXT = 'Python обязателен. Go обязателен.'
AT = '2026-11-13T15:00:00+03:00'


def python_only():
    return Requirements(items=[Requirement(id='r1', text='Python', quote='Python обязателен.',
                                           mandatory_quote='Python обязателен.')])


def both():
    return Requirements(items=python_only().items + [
        Requirement(id='r2', text='Go', quote='Go обязателен.', mandatory_quote='Go обязателен.')])


def codes(result):
    return {r.code for r in result.reasons}


class RequirementsReviewTests(unittest.TestCase):
    def test_missed_go_is_visible_and_unconfirmed_by_default(self):
        d = draft('job-001', TEXT, python_only())
        self.assertEqual(d.state, 'unconfirmed')
        self.assertEqual(d.uncovered, ['Go обязателен'])
        self.assertEqual(check(None, 'job-001', TEXT, python_only()).state, 'unconfirmed')
        self.assertEqual(draft('job-001', TEXT, both()).uncovered, [])

    def test_headings_are_not_reported_as_uncovered(self):
        text = 'Обязательно:\n- Python\nЖелательно:\n- SQL'
        reqs = Requirements(items=[Requirement(id='r1', text='Python', quote='Python', mandatory_quote='Обязательно:')])
        self.assertEqual(draft('job-001', text, reqs).uncovered, ['SQL'])

    def test_correct_confirmation_fits_only_its_source_and_list(self):
        approval = approve('job-001', TEXT, both(), AT)
        self.assertEqual(check(approval, 'job-001', TEXT, both()).state, 'confirmed')
        self.assertEqual(approval.approved_by, 'recruiter')

    def test_changed_source_is_stale(self):
        approval = approve('job-001', TEXT, both(), AT)
        result = check(approval, 'job-001', TEXT + ' Kafka желательна.', both())
        self.assertEqual((result.state, codes(result)), ('stale', {'source_changed'}))

    def test_added_removed_and_mandatory_changes_are_stale(self):
        approval = approve('job-001', TEXT, python_only(), AT)
        self.assertIn('requirement_added', codes(check(approval, 'job-001', TEXT, both())))
        approval = approve('job-001', TEXT, both(), AT)
        self.assertIn('requirement_removed', codes(check(approval, 'job-001', TEXT, python_only())))
        relaxed = both()
        relaxed.items[1] = relaxed.items[1].model_copy(update={'mandatory_quote': None})
        result = check(approval, 'job-001', TEXT, relaxed)
        self.assertEqual((result.state, codes(result)), ('stale', {'mandatory_changed'}))
        reworded = both()
        reworded.items[1] = reworded.items[1].model_copy(update={'text': 'Go 3 года'})
        self.assertIn('requirement_changed', codes(check(approval, 'job-001', TEXT, reworded)))

    def test_foreign_and_forged_approvals_are_invalid(self):
        approval = approve('job-001', TEXT, both(), AT)
        self.assertEqual(codes(check(approval, 'job-002', TEXT, both())), {'foreign_vacancy'})
        forged = approval.model_copy(update={'requirements_sha256': requirements_sha256(python_only())})
        self.assertEqual(codes(check(forged, 'job-001', TEXT, both())), {'hash_mismatch'})
        other = approve('job-002', 'Java обязателен.', both(), AT)
        self.assertEqual(check(other.model_dump(), 'job-001', TEXT, both()).state, 'invalid')

    def test_model_output_cannot_be_an_approval(self):
        as_model_json = both().model_dump()
        self.assertEqual(codes(check(as_model_json, 'job-001', TEXT, both())), {'malformed'})
        payload = approve('job-001', TEXT, both(), AT).model_dump()
        payload['approved_by'] = 'model'
        self.assertEqual(check(payload, 'job-001', TEXT, both()).state, 'invalid')
        payload = approve('job-001', TEXT, both(), AT).model_dump()
        payload['schema_version'] = 'old'
        self.assertEqual(codes(check(payload, 'job-001', TEXT, both())), {'schema_version'})

    def test_round_trip_from_stored_json(self):
        stored = approve('job-001', TEXT, both(), AT).model_dump(mode='json')
        self.assertEqual(check(stored, 'job-001', TEXT, both()).state, 'confirmed')

    def test_order_of_requirements_does_not_matter(self):
        reordered = Requirements(items=list(reversed(both().items)))
        self.assertEqual(requirements_sha256(reordered), requirements_sha256(both()))

    def test_vacancies_are_independent_and_confirmation_does_not_complete_run(self):
        ok = check(approve('job-001', TEXT, both(), AT), 'job-001', TEXT, both())
        missing = check(None, 'job-002', 'Java обязателен.', python_only())
        summary = summarize(True, {'job-001': ok, 'job-002': missing}, expected_ids=['job-001', 'job-002'])
        self.assertTrue(summary.processing_complete)
        self.assertFalse(summary.requirements_confirmed)
        self.assertEqual(summary.unconfirmed, ['job-002'])
        incomplete = summarize(False, {'job-001': ok}, expected_ids=['job-001'])
        self.assertTrue(incomplete.requirements_confirmed)
        self.assertFalse(incomplete.processing_complete)
        self.assertFalse(incomplete.final_allowed)
        self.assertFalse(summarize(True, {}, expected_ids=[]).requirements_confirmed)

    def test_vacancies_without_a_check_count_as_unconfirmed(self):
        ok = check(approve('job-001', TEXT, both(), AT), 'job-001', TEXT, both())
        summary = summarize(True, {'job-001': ok}, expected_ids=['job-001', 'job-002', 'job-003'])
        self.assertFalse(summary.final_allowed)
        self.assertEqual(summary.unconfirmed, ['job-002', 'job-003'])
        stray = summarize(True, {'job-001': ok, 'job-009': ok}, expected_ids=['job-001'])
        self.assertEqual(stray.invalid, ['job-009'])
        self.assertFalse(stray.final_allowed)

    def test_duplicate_requirement_ids_are_invalid(self):
        approval = approve('job-001', TEXT, both(), AT)
        dup = Requirements(items=both().items + [both().items[0]])
        self.assertEqual(codes(check(approval, 'job-001', TEXT, dup)), {'duplicate_ids'})

    def test_uncovered_skips_list_numbers(self):
        text = 'Обязательно:\n1. Python\n2. Go'
        reqs = Requirements(items=[Requirement(id='r1', text='Python', quote='Python', mandatory_quote='Обязательно:')])
        self.assertEqual(draft('job-001', text, reqs).uncovered, ['Go'])

    def test_source_hash_is_of_processed_text(self):
        self.assertEqual(draft('job-001', TEXT, both()).source_sha256, source_sha256(TEXT))
        self.assertNotEqual(source_sha256(TEXT), source_sha256(TEXT + ' '))

    def test_not_integrated_flag(self):
        self.assertFalse(INTEGRATED)


if __name__ == '__main__':
    unittest.main()
