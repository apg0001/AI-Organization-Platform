#!/usr/bin/env bash
# 로컬 개발 실행: 백엔드(127.0.0.1:8000)와 웹(127.0.0.1:3000)을 함께 띄운다. Ctrl+C로 둘 다 종료.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="$ROOT/apps/server"

if [[ ! -x "$SERVER/.venv/bin/ai-org-server" ]]; then
  echo "백엔드 가상환경이 없습니다. 먼저 실행하세요: (cd apps/server && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]')" >&2
  exit 1
fi
if [[ ! -d "$ROOT/node_modules" ]]; then
  echo "웹 의존성이 없습니다. 먼저 실행하세요: npm install" >&2
  exit 1
fi

trap 'kill 0' EXIT INT TERM
"$SERVER/.venv/bin/ai-org-server" &
(cd "$ROOT" && npm run dev:web) &
wait
