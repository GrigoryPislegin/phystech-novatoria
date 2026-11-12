#!/bin/bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if ! codex login status 2>&1 | grep -qi 'using ChatGPT'; then
  echo 'Для этого стенда нужен вход Codex через ChatGPT. Выполните codex login и выберите ChatGPT.' >&2
  exit 1
fi
export SUPERPOWERS_DISABLE_TELEMETRY=1
exec codex --strict-config -C "$PROJECT_ROOT" -m gpt-6.1-sol -c 'model_reasoning_effort="medium"' --sandbox workspace-write 'Прочитай AGENTS.md, README.md и docs/14-team-kickoff.md. Кейс получен, текущая архитектура в docs/15-architecture.md. Используй проектные hackathon_scout и hackathon_reviewer по необходимости, максимум один помощник одновременно. Выполняй только назначенную пользователем задачу и учитывай изменения других участников.'
