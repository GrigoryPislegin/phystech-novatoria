"""Install the pinned local skills and project-scoped agent configuration."""
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parent.parent
vendor = root / 'vendor/superpowers'
expected = '22f0b463e7a5e579904dd6211a520321035526f7'
for destination in (root/'.codex', root/'.codex/agents', root/'.agents', root/'.agents/skills'):
    if destination.is_symlink():
        raise SystemExit(f'Refusing symlink destination: {destination}')
actual = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
if actual != expected:
    raise SystemExit('Unexpected Superpowers revision; review before installing.')

pending_files = []

def write(path, text):
    if path.is_symlink():
        raise SystemExit(f'Refusing symlink configuration: {path}')
    if path.exists() and path.read_text() != text:
        raise SystemExit(f'Refusing to overwrite different configuration: {path}')
    pending_files.append((path, text))

write(root / '.codex/config.toml', '''# Project-scoped. Keep parent authentication, permissions and primary model.
[agents]
enabled = true
max_concurrent_threads_per_session = 1
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
''')
for name, model, effort, responsibility in [
    ('hackathon_scout', 'gpt-6-luna', 'high', 'Bounded read-only exploration. Identify relevant files, contracts and concrete risks. Return evidence and a short handoff.'),
    ('hackathon_reviewer', 'gpt-6.1-sol', 'medium', 'One focused read-only review for correctness, authorization, regressions and missing meaningful tests. Report file, line, trigger, impact and minimal fix. Do not invent findings.'),
]:
    instruction = responsibility + ' Never edit files. Never spawn subagents. Read only the paths needed for the delegated task. Do not access personal memory, credentials or unrelated archives. Keep output concise. Return actual checks and limitations. These are behavioral limits, not a separate filesystem sandbox.'
    write(root / f'.codex/agents/{name}.toml', '\n'.join([
        'name = ' + json.dumps(name),
        'description = ' + json.dumps(responsibility),
        'model = ' + json.dumps(model),
        'model_reasoning_effort = ' + json.dumps(effort),
        'developer_instructions = ' + json.dumps(instruction), '',
    ]))

skills = root / '.agents/skills'
pending_links = []
for directory in (vendor / 'skills').iterdir():
    if not (directory / 'SKILL.md').is_file():
        continue
    link = skills / directory.name
    target = Path('../../vendor/superpowers/skills') / directory.name
    if link.is_symlink() and link.readlink() == target:
        continue
    if link.exists() or link.is_symlink():
        raise SystemExit(f'Refusing to overwrite {link}')
    pending_links.append((link, target))

# Validate every destination before the first mutation, including late conflicts.
for path, text in pending_files:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
for link, target in pending_links:
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
print('Installed project roles and local Superpowers skills at pinned revision ' + expected)
