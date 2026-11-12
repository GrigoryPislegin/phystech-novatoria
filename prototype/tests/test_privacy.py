import asyncio
import unittest
from types import SimpleNamespace
from prototype.privacy import CertumPrivacy
from prototype.pipeline import run_pipeline
from prototype.demo import ReplayModel, demo_inputs


class FakeDetector:
    def __init__(self): self.calls = 0
    async def redact(self, scope, text, source):
        self.calls += 1
        return SimpleNamespace(text='человек#1: Python', replacements=[SimpleNamespace(ref='человек#1')])
    async def scan(self, scope, text): return []


class PrivacyTests(unittest.TestCase):
    def test_raw_reference_collision_never_reaches_model_or_detector(self):
        detector = FakeDetector(); privacy = CertumPrivacy(detector, None, None)
        model = ReplayModel()
        with self.assertRaises(RuntimeError):
            asyncio.run(run_pipeline('contact#79123456789', demo_inputs()[1], model, privacy))
        self.assertEqual(model.calls, 0)
        self.assertEqual(detector.calls, 0)

    def test_only_refs_issued_by_detector_are_allowed_in_output(self):
        privacy = CertumPrivacy(FakeDetector(), None, None)
        async def check():
            await privacy.redact('Вымышленный текст')
            await privacy.check('человек#1: Python')
            with self.assertRaises(RuntimeError): await privacy.check('contact#79123456789')
        asyncio.run(check())
