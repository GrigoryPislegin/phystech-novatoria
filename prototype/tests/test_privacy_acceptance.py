"""Acceptance metrics must expose missed identifiers and lost professional text."""
import asyncio
from types import SimpleNamespace
import unittest
from prototype.privacy_core import Detector, Finding, LocalPrivacy, REFERENCE
from evaluation.privacy_acceptance import assess_case, aggregate, evaluate, validate_cases


def case():
    return {'id': 'synthetic', 'text': 'Ann Python', 'expected': [
        {'start': 0, 'end': 3, 'quote': 'Ann', 'role': 'identifier'},
        {'start': 4, 'end': 10, 'quote': 'Python', 'role': 'professional'}],
        'known_limit': None}


class PrivacyAcceptanceTests(unittest.TestCase):
    def test_explicit_english_introduction_preserves_following_professional_sentence(self):
        for name in ['John Smith', "Jean-Luc O'Neil", 'John A. Smith', 'J. R. Smith']:
            with self.subTest(name=name):
                privacy = LocalPrivacy(Detector(lambda _: SimpleNamespace(spans=[])))
                source = f'My name is {name}. I develop software using Python.'
                protected = asyncio.run(privacy.redact(source))
                self.assertNotIn(name, protected)
                for component in name.split():
                    self.assertNotIn(component, REFERENCE.sub('', protected))
                self.assertIn('I develop software using Python.', protected)
                privacy.close()

    def test_english_introduction_followed_by_conjunction_preserves_experience(self):
        privacy = LocalPrivacy(Detector(lambda _: SimpleNamespace(spans=[])))
        protected = asyncio.run(privacy.redact('My name is John Smith and I develop software using Python.'))
        self.assertNotIn('John Smith', protected)
        self.assertIn('and I develop software using Python.', protected)
        privacy.close()

    def test_residual_detection_blocks_actual_redact_and_keeps_metrics_unmeasured(self):
        class AlwaysFinding:
            def scan(self, text):
                return [Finding(0, 1, 'PERSON')]
        report = asyncio.run(evaluate([case()], AlwaysFinding(), 'test_double'))
        self.assertEqual(report['cases_assessed'], 0)
        self.assertEqual(report['cases'][0]['error'], 'privacy_execution_failed')
        self.assertIsNone(report['metrics']['identifiers_masked']['value'])

    def test_empty_corpus_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_cases({'origin': 'synthetic', 'cases': []})

    def test_english_professional_sentence_without_identity_introduction_is_not_a_name(self):
        privacy = LocalPrivacy(Detector(lambda _: SimpleNamespace(spans=[])))
        source = 'I developed an API using Python and Java.'
        self.assertEqual(asyncio.run(privacy.redact(source)), source)
        privacy.close()

    def test_partial_name_match_is_not_success(self):
        result = assess_case(case(), [Finding(0, 1, 'PERSON')])
        self.assertEqual(result['spans'][0]['outcome'], 'partially_masked')
        metrics = aggregate([result])
        self.assertEqual(metrics['identifiers_masked']['passed'], 0)
        self.assertEqual(metrics['identifiers_masked']['assessed'], 1)

    def test_overlap_is_counted_once_and_professional_loss_is_reported(self):
        result = assess_case(case(), [Finding(0, 3, 'PERSON'), Finding(1, 3, 'IDENTITY'), Finding(4, 10, 'ORG')])
        self.assertEqual(result['spans'][0]['covered_characters'], 3)
        self.assertEqual(result['spans'][1]['outcome'], 'removed')
        self.assertEqual(aggregate([result])['professional_preserved']['value'], 0)

    def test_empty_or_blocked_results_are_unmeasured(self):
        empty = aggregate([])
        self.assertIsNone(empty['identifiers_masked']['value'])
        blocked = assess_case(case(), [], error='models_unavailable')
        metric = aggregate([blocked])['identifiers_masked']
        self.assertEqual((metric['expected'], metric['assessed'], metric['unmeasured']), (1, 0, 1))
        self.assertIsNone(metric['value'])

    def test_known_limit_does_not_exclude_failure_from_denominator(self):
        sample = case()
        sample['known_limit'] = 'deliberate missing name'
        metric = aggregate([assess_case(sample, [])])['identifiers_masked']
        self.assertEqual((metric['passed'], metric['assessed'], metric['value']), (0, 1, 0))

    def test_annotation_offsets_are_validated_after_normalization(self):
        sample = case()
        sample['text'] = 'A\u200bnn Python'
        self.assertEqual(validate_cases({'origin': 'synthetic', 'cases': [sample]}), [sample])
        sample['expected'][0]['end'] = 2
        with self.assertRaises(ValueError):
            validate_cases({'origin': 'synthetic', 'cases': [sample]})
