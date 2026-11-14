"""Expose pinned project skills and read-only Claude roles; never change global settings."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PIN = '22f0b463e7a5e579904dd6211a520321035526f7'


def install(root=ROOT):
    root = root.resolve()
    for path in [root/'.claude', root/'.claude/skills', root/'.claude/agents']:
        if path.is_symlink():
            raise SystemExit(f'Refusing symlink destination: {path}')
    vendor = root / 'vendor/superpowers'
    actual = subprocess.check_output(['git','-C',str(vendor),'rev-parse','HEAD'], text=True).strip()
    if actual != PIN:
        raise SystemExit('Unexpected Superpowers revision; no installation performed.')
    destinations = []
    for folder in sorted((vendor/'skills').iterdir()):
        if (folder/'SKILL.md').is_file():
            dest = root/'.claude/skills'/folder.name
            target = Path('../../vendor/superpowers/skills')/folder.name
            if dest.is_symlink() and dest.readlink() == target:
                continue
            if dest.exists() or dest.is_symlink():
                raise SystemExit(f'Refusing to overwrite {dest}')
            destinations.append((dest, target))
    roles = []
    for src in (root/'team-config/claude').glob('*.md'):
        dest = root/'.claude/agents'/src.name
        if src.is_symlink() or dest.is_symlink():
            raise SystemExit(f'Refusing symlink role: {dest}')
        if dest.exists() and dest.read_text() != src.read_text():
            raise SystemExit(f'Refusing to overwrite {dest}')
        if dest.exists():
            continue
        roles.append((src,dest))
    for dest, target in destinations:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(target, target_is_directory=True)
    for src,dest in roles:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src,dest)
    print('Claude project skills and Haiku/Opus read-only roles installed. Restart Claude Code.')


if __name__ == '__main__': install()
