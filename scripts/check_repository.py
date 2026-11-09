#!/usr/bin/env python3
"""Offline repository check. Does not import or run application code."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'Telegram bot token': re.compile(r'\b\d{8,12}:[A-Za-z0-9_-]{30,}\b'),
    'JWT literal': re.compile(r'\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b'),
}
DSN_PATTERN = re.compile(r"\b(?:mongodb(?:\+srv)?|postgres(?:ql)?(?:\+asyncpg)?|amqps?|rediss?)://[^\s/:@\"']+:[^\s/@\"']+@")
TEXT_SUFFIXES = {'.py', '.md', '.toml', '.yaml', '.yml', '.json', '.tmpl', '.proto', '.j2', '.sh', '.csv'}
TEAM_DOCS = ['README.md', 'START_HERE.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md',
             'docs/01-brief.md', 'docs/ML_READINESS.md', 'docs/SETUP.md', 'docs/TEAM_REQUEST.md',
             'docs/nanimai/REVIEW.md', 'docs/nanimai/MIPT_CASE.md']
REQUIRED = TEAM_DOCS + ['services/platform/uv.lock', 'services/hharon/uv.lock',
                       'services/platform/pyproject.toml', 'services/hharon/pyproject.toml',
                       'services/platform/example.config.toml', 'services/hharon/config.toml.example',
                       'docs/nanimai/import-manifest.json', 'docs/nanimai/input-sha256.json',
                       'services/platform/dist/hhsdk-1.0.1-py3-none-any.whl',
                       '.github/workflows/repository-check.yml', 'templates/team.csv', 'templates/backlog.csv']


def credential_findings(text: str, *, check_dsn: bool = False) -> list[tuple[str, int]]:
    """Return labels/line numbers, never matched credential values."""
    findings = [(label, text.count('\n', 0, match.start()) + 1)
                for label, pattern in PATTERNS.items() for match in pattern.finditer(text)]
    if check_dsn:
        findings.extend(('DSN credentials', text.count('\n', 0, match.start()) + 1)
                        for match in DSN_PATTERN.finditer(text)
                        if '${' not in match.group() and '{' not in match.group())
    return findings


def main() -> int:
    if sys.version_info < (3, 13):
        print('Use Python 3.13+ to parse both imported services.'); return 1
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=ROOT, capture_output=True, check=True)
    paths = sorted({p.decode() for p in result.stdout.split(b'\0') if p})
    errors: list[str] = []
    python_files = 0
    for name in REQUIRED:
        if name not in paths or not (ROOT / name).is_file():
            errors.append(f'Missing or ignored required file: {name}')
    for name in paths:
        path = ROOT / name
        if path.is_symlink():
            errors.append(f'Symlink must be reviewed: {name}'); continue
        if not path.is_file():
            continue
        if path.name == 'config.toml' or path.name == '.env' or (path.name.startswith('.env.') and path.name != '.env.example'):
            errors.append(f'Runtime config must not be tracked: {name}')
        if path.suffix in {'.pem', '.key', '.zip', '.safetensors', '.onnx', '.pt', '.pth'}:
            errors.append(f'Private/large artifact must not be tracked: {name}')
        toml_example = path.name.endswith('.toml.example')
        if path.suffix not in TEXT_SUFFIXES and not toml_example:
            continue
        text = path.read_text(encoding='utf-8')
        for label, line in credential_findings(text, check_dsn=toml_example or path.suffix in {'.toml', '.yml', '.yaml'}):
            errors.append(f'{name}:{line}: credential-shaped {label}; value omitted')
        try:
            if path.suffix == '.py':
                # Validate platform against its pinned Python minor version.
                version = (3, 12) if name.startswith('services/platform/') else (3, 13)
                ast.parse(text, filename=name, feature_version=version); python_files += 1
            elif path.suffix == '.json':
                json.loads(text)
            elif path.suffix == '.toml' or toml_example:
                tomllib.loads(text)
        except (SyntaxError, ValueError) as exc:
            errors.append(f'{name}: parse error ({type(exc).__name__}, line {getattr(exc, "lineno", "unknown")})')
    for name in TEAM_DOCS:
        path = ROOT / name
        if not path.is_file(): continue
        for raw in re.findall(r'\]\((<[^>]+>|[^)]+)\)', path.read_text()):
            target = raw.strip('<>').split('#', 1)[0]
            if not target or '://' in target or target.startswith('mailto:'): continue
            resolved = (path.parent / unquote(target)).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                errors.append(f'{name}: missing/nonportable link: {target}')
    if errors:
        print('\n'.join(errors)); return 1
    print(f'PASS: {len(paths)} repository files; {python_files} Python files parsed; team links and basic secret patterns checked.')
    print('NOT RUN: application tests, dependency install, services, ML evaluation. This heuristic is not a full secret scan.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
