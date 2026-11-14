import contextlib
import io
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AgentSetupTests(unittest.TestCase):
    def test_symlink_parent_or_file_is_rejected_before_any_write(self):
        original=Path(__file__).resolve().parents[2]/'scripts/setup_agents.py'
        for target in ('.codex', '.agents', '.codex/config.toml', '.codex/agents'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'project'; outside=Path(tmp)/'outside'; outside.mkdir()
                (root/'scripts').mkdir(parents=True)
                script=root/'scripts/setup_agents.py'; shutil.copyfile(original,script)
                skill=root/'vendor/superpowers/skills/sample'; skill.mkdir(parents=True)
                (skill/'SKILL.md').write_text('synthetic')
                link=root/target; link.parent.mkdir(parents=True,exist_ok=True)
                link.symlink_to(outside/'config.toml' if target.endswith('.toml') else outside)
                with patch('subprocess.check_output',return_value='22f0b463e7a5e579904dd6211a520321035526f7'), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit): runpy.run_path(str(script),run_name='__main__')
                self.assertEqual(list(outside.iterdir()),[])
                if target != '.codex/config.toml': self.assertFalse((root/'.codex/config.toml').exists())
