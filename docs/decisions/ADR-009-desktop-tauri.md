# ADR-009: 데스크톱 앱 — Tauri 2 + 내장 백엔드(PyInstaller 사이드카)

- 날짜: 2026-11-25 · 상태: 채택

## 배경
브라우저와 터미널 두 개를 띄우지 않고 설치 한 번으로 쓰고 싶다. 창을 닫아도 에이전트 작업이 계속되고, 시스템 트레이에서
실행 상태·승인 대기·사용량을 보고, 승인 요청·작업 완료가 네이티브 알림으로 와야 한다. 대상: Linux(x64·arm64)·macOS·Windows.

## 결정
- 셸은 **Tauri 2**(Rust, OS 웹뷰). 백엔드(FastAPI)는 **PyInstaller 단일 실행 파일**로 묶어 Tauri `externalBin`(사이드카)로 실행한다.
- 백엔드가 웹 빌드도 제공한다(단일 프로세스). 창은 `http://127.0.0.1:<임의 포트>/?desktop=1`을 연다 — 웹 화면은 브라우저 실행과 같은 코드다.
  창은 원격 주소라 Tauri IPC를 쓰지 않는다. 트레이·알림은 Rust가 백엔드 `/api/v1/desktop/summary`를 3초마다 읽어 처리한다.
- 요약 API는 앱이 띄울 때 만든 임의 토큰(`AI_ORG_DESKTOP_TOKEN`, 메모리에만)으로만 열린다.
- 앱이 끝나면 백엔드 표준 입력이 닫히고 백엔드가 정상 종료한다(앱이 강제 종료돼도 OS가 파이프를 닫아 고아 프로세스가 남지 않음).
- Claude Code CLI는 번들하지 않는다(`claude-agent-sdk`의 번들 CLI 제외 → 사이드카 약 43MB). 사용자의 `claude`와 그 로그인을 쓴다.
- 빌드는 CI(OS별 러너)에서만 한다. 서명·공증·자동 업데이트는 하지 않는다(설치 시 경고 — DEPLOYMENT.md).

## 대안
- Electron: 크롬 런타임 포함으로 설치 파일 100MB+, 메모리 사용이 라즈베리 파이에 부담.
- 백엔드를 Rust로 재작성: Claude Agent SDK(Python)와 기존 코드 재사용을 잃는다.
- 웹뷰에 Tauri IPC로 알림: 원격 주소 창에 IPC를 열어야 해 공격면이 커진다 → Rust 쪽 폴링으로 대체.

## 영향
+ 설치 파일이 작고(웹뷰는 OS 것), 웹·데스크톱 화면 코드가 하나다. + 트레이·알림이 웹 화면과 독립적으로 동작한다.
− 미서명이라 macOS Gatekeeper·Windows SmartScreen 경고. − Linux 트레이는 AppIndicator 지원 환경이 필요(GNOME은 확장 필요).
− PyInstaller 단일 파일은 첫 실행 시 압축을 풀어 시작이 몇 초 걸린다.
