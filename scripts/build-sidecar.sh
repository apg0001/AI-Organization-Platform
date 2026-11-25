#!/usr/bin/env bash
# 데스크톱 번들용 백엔드 단일 실행 파일을 만든다(PyInstaller).
# 결과: apps/desktop/src-tauri/binaries/ai-org-server-<rust target triple>[.exe] — Tauri externalBin 이름 규칙.
# 전제: apps/web/dist(npm run build), PyInstaller와 백엔드가 설치된 Python(PYTHON, 기본 python3).
# Claude Code CLI는 번들하지 않는다(사용자 컴퓨터의 `claude`를 쓴다 — 로그인도 그쪽).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
test -f apps/web/dist/index.html || { echo "apps/web/dist가 없습니다. 먼저 npm run build" >&2; exit 1; }
TARGET=${TARGET:-$(rustc -vV | sed -n 's/^host: //p')}
SEP=":"; EXT=""
if [[ "$TARGET" == *windows* ]]; then SEP=";"; EXT=".exe"; fi

"$PY" -m PyInstaller --noconfirm --clean --onefile --name ai-org-server \
  --distpath build/sidecar/dist --workpath build/sidecar/work \
  --paths apps/server/src \
  --collect-submodules ai_org --collect-data ai_org \
  --collect-submodules uvicorn --hidden-import sqlalchemy.dialects.sqlite \
  --add-data "apps/web/dist${SEP}web" \
  apps/desktop/sidecar/server.py
rm -f ai-org-server.spec

mkdir -p apps/desktop/src-tauri/binaries
cp "build/sidecar/dist/ai-org-server${EXT}" "apps/desktop/src-tauri/binaries/ai-org-server-${TARGET}${EXT}"
echo "sidecar: apps/desktop/src-tauri/binaries/ai-org-server-${TARGET}${EXT}"
