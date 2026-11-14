#!/usr/bin/env bash
set -euo pipefail

image=$1
scratch=$(mktemp -d)
work=$(cd "$scratch" && pwd -P)
trap 'rm -rf "$work"' EXIT

# Probe the committed .dockerignore in an isolated copy with synthetic canaries.
context="$work/context"
mkdir -p "$context"
git archive HEAD | tar -xf - -C "$context"
mkdir -p "$context/data/private/prototype-runs" "$context/runtime/privacy-models"
printf 'synthetic\n' > "$context/.env"
printf 'synthetic\n' > "$context/data/private/original-resume.txt"
printf '{}\n' > "$context/data/private/prototype-runs/report.json"
printf 'synthetic\n' > "$context/runtime/privacy-models/extra.txt"
docker build --network none --output "type=local,dest=$work/build-inputs" \
  --file - "$context" <<'DOCKERFILE'
FROM scratch
COPY . /context/
DOCKERFILE
for path in .env data/private services evaluation runtime/privacy-models/extra.txt; do
  test ! -e "$work/build-inputs/context/$path" || { echo "unexpected_build_input: $path" >&2; exit 1; }
done
test -f "$work/build-inputs/context/prototype/static/index.html"
echo 'build_context: pass'

docker run --rm --network none --entrypoint python -i "$image" - <<'PY'
from importlib import import_module
import os
from pathlib import Path
import platform

assert os.getuid() == 10001
assert 'OPENAI_API_KEY' not in os.environ
for module in ('evidence', 'requirements_review', 'candidate_profile', 'review_policy', 'review_queue', 'web_app'):
    import_module('prototype.' + module)
for asset in ('index.html', 'viewer.js', 'report.js', 'manager-report.js', 'report.css', 'demo-report.js'):
    assert (Path('prototype/static') / asset).is_file(), 'missing_web_asset: ' + asset
for path in ('.env', 'services', 'evaluation', 'report.json', 'data/private/original-resume.txt'):
    assert not Path(path).exists(), 'unexpected_runtime_path: ' + path
assert not any(Path('data/private/prototype-runs').iterdir())
print('runtime_files:', platform.system(), platform.machine(), platform.python_version(), 'pass')
PY

mkdir -p "$work/fixtures/jobs" "$work/missing" "$work/wrong-checksum" "$work/rejected"
printf 'Разрабатывал на Python 3 года.\n' > "$work/fixtures/resume.txt"
printf 'Обязателен Python.\n' > "$work/fixtures/jobs/job.txt"

# Change the first archive without changing its size. Leave the second archive intact.
docker run --rm --network none --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$work/wrong-checksum,dst=/test-models" --entrypoint python -i "$image" - <<'PY'
from pathlib import Path
from shutil import copyfile

from prototype.privacy_core.models import MODELS

first, *remaining = MODELS
with (Path('/test-models') / first).open('xb') as stream:
    stream.truncate(MODELS[first][2])
for name in remaining:
    copyfile(Path('/opt/privacy-models') / name, Path('/test-models') / name)
PY

for scenario in missing wrong-checksum; do
  code=0
  output=$(docker run --rm --network none --user "$(id -u):$(id -g)" \
    --env PRIVACY_MODELS_DIR=/test-models \
    --mount "type=bind,src=$work/$scenario,dst=/test-models,readonly" \
    --mount "type=bind,src=$work/fixtures,dst=/fixtures,readonly" \
    --mount "type=bind,src=$work/rejected,dst=/out" \
    "$image" run --resume /fixtures/resume.txt --jobs /fixtures/jobs --out /out) || code=$?
  if [[ "$code" -ne 2 || "$output" != *privacy_models_missing_or_invalid* ]]; then
    echo "unexpected_privacy_result: $scenario, exit $code" >&2
    exit 1
  fi
  printf '%s: privacy_models_missing_or_invalid, exit %s\n' "$scenario" "$code"
done
test -z "$(find "$work/rejected" -mindepth 1 -print -quit)"
