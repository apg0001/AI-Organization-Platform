"""데스크톱 백엔드 단일 실행 파일 스모크 테스트(CI, 모든 OS).

확인: 시작 → 웹 화면 제공(SPA 대체 포함) → 데스크톱 요약 API(토큰 필요) → 표준 입력을 닫으면 종료.
사용: python scripts/smoke_sidecar.py <binaries 폴더>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("SMOKE_PORT", "18765"))
BASE = f"http://127.0.0.1:{PORT}"


def get(path: str, token: str | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> None:
    binary = next(p for p in Path(sys.argv[1]).iterdir() if p.name.startswith("ai-org-server-"))
    home = tempfile.mkdtemp(prefix="ai-org-smoke-")
    env = {
        **os.environ,
        "AI_ORG_HOME": home,
        "AI_ORG_PORT": str(PORT),
        "AI_ORG_WEB_PORT": str(PORT),
        "AI_ORG_DESKTOP_TOKEN": "smoke-token",
        "AI_ORG_EXIT_ON_STDIN_EOF": "1",
        "AI_ORG_USAGE_POLL": "0",
        "AI_ORG_AUTH": "off",  # 번들 데이터(템플릿) 확인용. 데스크톱 토큰 검사는 로그인 설정과 무관하다.
    }
    proc = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, env=env)
    started = time.time()
    while True:
        try:
            if get("/api/v1/system/health")[0] == 200:
                break
        except OSError:
            pass
        if time.time() - started > 180 or proc.poll() is not None:
            proc.kill()
            raise SystemExit(f"백엔드가 시작되지 않았습니다(종료 코드 {proc.poll()}).")
        time.sleep(1)
    print(f"시작 {time.time() - started:.1f}초")

    for path in ("/", "/usage"):
        status, body = get(path)
        assert status == 200 and b'id="root"' in body, (path, status)
    assert get("/api/v1/desktop/summary")[0] == 401
    status, body = get("/api/v1/desktop/summary", "smoke-token")
    summary = json.loads(body)
    assert status == 200 and summary["notifications"] == [], summary
    assert len(json.loads(get("/api/v1/templates")[1])) >= 6  # 번들 데이터(템플릿) 포함
    print("웹·요약 API·템플릿 확인")

    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait(timeout=60)
    print(f"표준 입력 종료 후 백엔드 종료(코드 {proc.returncode})")


if __name__ == "__main__":
    main()
