"""Explicit setup step for public weights; no documents or credentials are used."""
import argparse
import os
import ssl
import shutil
import certifi
from pathlib import Path
import tempfile
from urllib.request import urlopen
from .models import MODELS, verify


def prepare(directory, source=None):
    directory = Path(directory)
    if any(p.is_symlink() for p in [directory, *directory.parents]):
        raise RuntimeError('privacy_models_missing_or_invalid')
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, _, size) in MODELS.items():
        destination = directory/name
        print('privacy_model_prepare: ' + name, flush=True)
        if destination.exists() or destination.is_symlink():
            verify(destination, name)
            continue
        fd, temp = tempfile.mkstemp(prefix='.model-', dir=directory)
        temp = Path(temp)
        try:
            with os.fdopen(fd, 'wb') as output:
                if source is not None:
                    verified = verify(Path(source)/name, name)
                    with verified.open('rb') as incoming:
                        shutil.copyfileobj(incoming, output)
                else:
                    with urlopen(url, timeout=60, context=ssl.create_default_context(cafile=certifi.where())) as response:
                        total = 0
                        while chunk := response.read(1_048_576):
                            total += len(chunk)
                            if total > size:
                                raise RuntimeError('privacy_models_missing_or_invalid')
                            output.write(chunk)
            verify(temp, name)
            os.chmod(temp, 0o644)  # Public weights; readable by the container's non-root user.
            os.link(temp, destination)  # Never overwrite a concurrent writer or symlink.
        finally:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', type=Path, default=Path('data/private/privacy-models'))
    parser.add_argument('--from-dir', type=Path, help='Copy only the two pinned public archives, verify before and after copying')
    args = parser.parse_args()
    try:
        prepare(args.dir, args.from_dir)
    except Exception as exc:
        print('privacy_models_setup_failed:' + type(exc).__name__)
        return 2
    print('privacy_models_verified: 2')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
