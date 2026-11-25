"""데스크톱 앱 실행 스모크 테스트(CI, Linux 가상 화면).

확인: 앱 실행 → 내장 백엔드가 뜸 → 앱을 끝내면 백엔드도 끝남(고아 프로세스 없음).
사용: xvfb 환경에서 python scripts/smoke_desktop.py <앱 실행 파일>
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = int(os.environ.get("SMOKE_PORT", "18766"))


def healthy() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/v1/system/health", timeout=2) as res:
            return res.status == 200
    except OSError:
        return False


def main() -> None:
    env = {
        **os.environ,
        "AI_ORG_HOME": tempfile.mkdtemp(prefix="ai-org-desktop-"),
        "AI_ORG_DESKTOP_PORT": str(PORT),
        "AI_ORG_USAGE_POLL": "0",
    }
    app = subprocess.Popen(["xvfb-run", "-a", sys.argv[1]], env=env)
    started = time.time()
    while not healthy():
        if time.time() - started > 180 or app.poll() is not None:
            app.kill()
            raise SystemExit(f"앱의 내장 백엔드가 시작되지 않았습니다(앱 종료 코드 {app.poll()}).")
        time.sleep(1)
    print(f"앱 시작 → 백엔드 응답 {time.time() - started:.1f}초")
    time.sleep(8)  # 트레이 갱신·창 이동이 몇 번 돌게 둔다
    assert app.poll() is None, f"앱이 스스로 종료되었습니다(코드 {app.returncode})"

    subprocess.run(["pkill", "-TERM", "-f", sys.argv[1]], check=False)
    app.wait(timeout=30)
    deadline = time.time() + 30
    while healthy():
        if time.time() > deadline:
            raise SystemExit("앱을 끝냈는데 내장 백엔드가 남아 있습니다.")
        time.sleep(1)
    print("앱 종료 후 백엔드도 종료")


if __name__ == "__main__":
    main()
