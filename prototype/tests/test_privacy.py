import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from prototype.privacy_core import Detector, Finding, LocalPrivacy
from prototype.privacy_core.models import load
from prototype.pipeline import run_pipeline
from prototype.demo import ReplayModel, demo_inputs


class PrivacyTests(unittest.TestCase):
    def privacy(self):
        return LocalPrivacy(Detector(lambda text: SimpleNamespace(spans=[])))

    def test_contacts_masked_consistently_without_changing_professional_text(self):
        async def run():
            privacy = self.privacy()
            source = 'ФИО: Иван Иванов\n+7 (999) 123-45-67\nivan@example.com\nPython 3 года. SQL 1 год.'
            safe = await privacy.redact(source)
            for value in ['Иван', '999', 'ivan@example.com']:
                self.assertNotIn(value, safe)
            self.assertIn('Python 3 года. SQL 1 год.', safe)
            again = await privacy.redact('ivan@example.com')
            self.assertIn(again, safe)
            self.assertNotEqual(again, await self.privacy().redact('ivan@example.com'))
            await privacy.check(safe)
        asyncio.run(run())

    def test_source_cannot_supply_a_protected_reference(self):
        privacy = self.privacy(); privacy.detector.scan = Mock(return_value=[])
        model = ReplayModel()
        with self.assertRaisesRegex(RuntimeError, 'privacy_untrusted_reference'):
            asyncio.run(run_pipeline('[[PRIV:deadbeefdeadbeef:1:PERSON]]', demo_inputs()[1], model, privacy))
        self.assertEqual(model.calls, 0)
        privacy.detector.scan.assert_not_called()

    def test_unissued_malformed_and_cross_run_references_rejected(self):
        async def run():
            privacy = self.privacy()
            ref = await privacy.redact('a@example.com')
            await privacy.check(ref)
            for text in ['[[PRIV:broken', ref.replace(':1:', ':2:')]:
                with self.assertRaisesRegex(RuntimeError, 'privacy_untrusted_reference'):
                    await privacy.check(text)
            with self.assertRaisesRegex(RuntimeError, 'privacy_untrusted_reference'):
                await self.privacy().check(ref)
        asyncio.run(run())

    def test_normalization_and_decoded_contacts_do_not_bypass_detector(self):
        async def run():
            privacy = self.privacy()
            for text in ['ivan\u200b@example.com', 'ivan＠example.com', 'ivan [at] example [dot] com',
                         'Telegram: ivan_handle', 'John Smith\nPython 3 years']:
                with self.subTest(text=text):
                    self.assertNotEqual(await privacy.redact(text), text)
                    with self.assertRaisesRegex(RuntimeError, 'privacy_residual_findings'):
                        await privacy.check(text)
        asyncio.run(run())

    def test_detector_failure_or_residuals_stop_before_model(self):
        for detector in [Mock(scan=Mock(side_effect=RuntimeError('failed'))),
                         Mock(scan=Mock(return_value=[Finding(0, 5, 'PERSON')]))]:
            model = ReplayModel()
            with self.assertRaises(RuntimeError):
                asyncio.run(run_pipeline(*demo_inputs(), model, LocalPrivacy(detector)))
            self.assertEqual(model.calls, 0)

    def test_closed_instance_cannot_be_reused(self):
        privacy = self.privacy()
        asyncio.run(privacy.redact('a@example.com'))
        privacy.close()
        self.assertEqual(privacy.issued_refs, set())
        self.assertEqual(privacy._aliases, {})
        with self.assertRaisesRegex(RuntimeError, 'privacy_closed'):
            asyncio.run(privacy.check('Python'))

    def test_missing_or_corrupt_models_fail_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'privacy_models_missing_or_invalid'):
                load(tmp)
            (Path(tmp)/'slovnet_ner_news_v1.tar').write_bytes(b'corrupt')
            with self.assertRaisesRegex(RuntimeError, 'privacy_models_missing_or_invalid'):
                load(tmp)

    def test_overlap_is_masked_as_a_single_span(self):
        detector = Mock(scan=Mock(side_effect=[[Finding(0, 5, 'PERSON'), Finding(3, 8, 'ORG')], []]))
        privacy = LocalPrivacy(detector)
        result = asyncio.run(privacy.redact('abcdefgh skill'))
        self.assertEqual(len(privacy.issued_refs), 1)
        self.assertTrue(result.endswith(' skill'))
