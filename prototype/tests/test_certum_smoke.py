import asyncio
from contextlib import asynccontextmanager, redirect_stdout
import io
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from scripts import certum_smoke


class CertumSmokeTests(unittest.TestCase):
    def test_remote_database_is_rejected_before_adapter(self):
        config = {'CERTUM_DATABASE_URL': 'postgresql+psycopg://test:test@remote.invalid:55439/certum',
                  'CERTUM_MASTER_KEY': 'synthetic'}
        dotenv = types.SimpleNamespace(dotenv_values=lambda *a, **k: config)
        with patch.dict(os.environ), patch.object(certum_smoke.logging, 'disable'), \
                patch.dict(sys.modules, {'dotenv': dotenv}), patch.object(sys, 'argv',
                ['smoke', '--env-file', 'synthetic.env', '--tenant-file', 'unused', '--models-dir', '.']), \
                patch.object(certum_smoke, 'check', new_callable=AsyncMock) as check, \
                patch.object(certum_smoke.Path, 'read_text', return_value='synthetic-tenant'), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(certum_smoke.main(), 2)
        check.assert_not_called()

    def run_fake(self, output, refs, error):
        class Fake:
            issued_refs = refs
            async def redact(self, text):
                if 'contact#123' in text:
                    raise RuntimeError(error)
                return output
            async def check(self, text):
                pass
        @asynccontextmanager
        async def context():
            yield Fake()
        with patch('prototype.privacy.certum_privacy', context):
            return asyncio.run(certum_smoke.check())

    def test_missing_professional_text_cannot_pass(self):
        with self.assertRaises(RuntimeError):
            self.run_fake('name#1', {'name#1'}, 'privacy_untrusted_reference')

    def test_backend_error_is_not_proof_of_reference_protection(self):
        with self.assertRaisesRegex(RuntimeError, 'backend_unavailable'):
            self.run_fake('name#1 phone#2 email#3 Разрабатывал на Python 3 года.',
                          {'name#1', 'phone#2', 'email#3'}, 'backend_unavailable')


if __name__ == '__main__':
    unittest.main()
