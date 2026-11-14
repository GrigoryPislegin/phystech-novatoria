"""Build a versioned source bundle from committed public files and pinned NER weights."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    def git(*values):
        return subprocess.check_output(['git', *values], cwd=root)
    head = git('rev-parse', 'HEAD').decode().strip()
    stamp = int(git('show', '-s', '--format=%ct', 'HEAD'))
    # Read blobs from the commit, never the worktree's untracked/private files.
    paths = git('ls-tree', '-r', '--name-only', '-z', head, '--',
                'prototype', 'evaluation', 'docs', 'scripts', 'tests',
                'README.md', 'Dockerfile', '.dockerignore', '.gitignore', 'THIRD_PARTY_NOTICES.md').decode().split('\0')
    files = {}
    for path in filter(None, paths):
        parts = Path(path).parts
        if any(part in {'private', '.git', '__pycache__'} for part in parts) or Path(path).name in {'.env', 'model.env'}:
            raise SystemExit('private_path_in_release_selection')
        files[path] = git('show', f'{head}:{path}')
    from prototype.privacy_core.models import MODELS, verify
    for name in MODELS:
        path = verify(root/'runtime/privacy-models'/name, name)
        files['runtime/privacy-models/'+name] = path.read_bytes()
    manifest = {'commit':head, 'format':'recruiter-source-v1',
                'files':{name:hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files['RELEASE.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('xb') as destination, tarfile.open(fileobj=destination, mode='w:gz') as archive:
        for name, data in sorted(files.items()):
            entry = tarfile.TarInfo(name)
            entry.size, entry.mtime, entry.mode = len(data), stamp, 0o644
            archive.addfile(entry, io.BytesIO(data))
    digest = hashlib.file_digest(args.out.open('rb'), 'sha256').hexdigest()
    args.out.with_suffix(args.out.suffix+'.sha256').write_text(digest+'  '+args.out.name+'\n')
    print(json.dumps({'commit':head, 'files':len(manifest['files']),
                      'bytes':args.out.stat().st_size, 'sha256':digest, 'archive':str(args.out)}))


if __name__ == '__main__':
    main()
