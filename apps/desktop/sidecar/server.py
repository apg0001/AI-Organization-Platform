"""데스크톱 번들용 백엔드 진입점(PyInstaller가 이 파일로 단일 실행 파일 `ai-org-server`를 만든다).

데스크톱 앱이 환경 변수로 포트·데스크톱 토큰을 넘기고, 표준 입력이 닫히면(앱 종료) 서버도 끝난다.
웹 화면은 번들 안의 `web/`(apps/web/dist)을 백엔드가 직접 제공한다.
"""

from ai_org.main import run

if __name__ == "__main__":
    run()
