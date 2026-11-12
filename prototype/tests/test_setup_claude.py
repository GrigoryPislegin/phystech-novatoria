import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.setup_claude import install, PIN


class SetupTests(unittest.TestCase):
    @patch('scripts.setup_claude.subprocess.check_output', return_value=PIN)
    def test_does_not_write_through_external_parent_symlink(self, _):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as outside:
            root = Path(repo)
            (root/'vendor/superpowers/skills').mkdir(parents=True)
            (root/'team-config/claude').mkdir(parents=True)
            (root/'team-config/claude/reviewer.md').write_text('role')
            (root/'.claude').mkdir()
            (root/'.claude/agents').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SystemExit): install(root)
            self.assertEqual(list(Path(outside).iterdir()), [])

    @patch('scripts.setup_claude.subprocess.check_output', return_value=PIN)
    def test_does_not_write_through_dangling_role_symlink(self, _):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as outside:
            root = Path(repo)
            (root/'vendor/superpowers/skills').mkdir(parents=True)
            (root/'team-config/claude').mkdir(parents=True)
            (root/'team-config/claude/reviewer.md').write_text('role')
            (root/'.claude/agents').mkdir(parents=True)
            target = Path(outside)/'unexpected'
            (root/'.claude/agents/reviewer.md').symlink_to(target)
            with self.assertRaises(SystemExit): install(root)
            self.assertFalse(target.exists())
