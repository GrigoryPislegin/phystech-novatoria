"""Check that credential diagnostics fail safely without exposing values."""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'scripts/check_repository.py'
spec = importlib.util.spec_from_file_location('repository_check', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CredentialDiagnosticsTests(unittest.TestCase):
    def test_embedded_credential_is_detected_without_value(self):
        token = 'ghp_' + 'A' * 36
        findings = module.credential_findings('first line\n' + token)
        self.assertIn(('GitHub token', 2), findings)
        self.assertNotIn(token, repr(findings))

    def test_empty_config_and_test_placeholders_are_allowed(self):
        self.assertEqual(module.credential_findings('secret = ""\naccess_token = "test_token"'), [])

    def test_private_key_header_is_detected(self):
        header = '-----BEGIN ' + 'PRIVATE KEY-----'
        self.assertIn(('private key', 1), module.credential_findings(header))

    def test_openai_token_is_detected_without_exposing_value(self):
        token = 'sk-proj-' + 'C' * 40
        findings = module.credential_findings(token)
        self.assertIn(('OpenAI token', 1), findings)
        self.assertNotIn(token, repr(findings))

    def test_config_uri_credentials_are_not_printed(self):
        uri = 'amqp://' + 'fixture-user:fixture-password@local/'
        findings = module.credential_findings(uri, check_dsn=True)
        self.assertIn(('DSN credentials', 1), findings)
        self.assertNotIn('fixture-password', repr(findings))

    def test_environment_uri_template_is_not_a_literal_secret(self):
        uri = 'postgresql://' + '${USER}:${PASSWORD}@local/db'
        self.assertEqual(module.credential_findings(uri, check_dsn=True), [])


class RepositoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        import subprocess
        import tempfile
        from unittest.mock import patch
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        self.patch = patch.object(module, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        for name in module.REQUIRED:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            body = '{}' if target.suffix == '.json' else '# fixture\n'
            target.write_text(body)

    def run_check(self):
        import contextlib
        import io
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = module.main()
        return result, stream.getvalue()

    def test_missing_runtime_dependencies_are_rejected(self):
        (self.root / 'prototype/requirements.lock.txt').unlink()
        result, output = self.run_check()
        self.assertEqual(result, 1)
        self.assertIn('Missing or ignored required file: prototype/requirements.lock.txt', output)

    def test_toml_example_is_parsed(self):
        (self.root / 'config.toml.example').write_text('port = [')
        result, output = self.run_check()
        self.assertEqual(result, 1)
        self.assertIn('config.toml.example: parse error', output)

    def test_toml_example_credentials_are_rejected(self):
        secret = 'ghp_' + 'B' * 36
        (self.root / 'config.toml.example').write_text('secret = "' + secret + '"')
        result, output = self.run_check()
        self.assertEqual(result, 1)
        self.assertIn('GitHub token', output)
        self.assertNotIn(secret, output)

    def test_dangling_symlink_is_rejected(self):
        (self.root / 'dangling').symlink_to(self.root / 'missing')
        result, output = self.run_check()
        self.assertEqual(result, 1)
        self.assertIn('Symlink must be reviewed: dangling', output)

    def test_directory_symlink_is_rejected(self):
        (self.root / 'linked-services').symlink_to(self.root / 'services', target_is_directory=True)
        result, output = self.run_check()
        self.assertEqual(result, 1)
        self.assertIn('Symlink must be reviewed: linked-services', output)
