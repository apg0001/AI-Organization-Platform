# 실행·배포

## 현재: 로컬 개발 실행

README의 설치 후 `./scripts/dev.sh`. 백엔드 `127.0.0.1:8000`, 웹 `127.0.0.1:3000`.

## 로컬 운영 실행(빌드본)

```bash
npm run build                                  # apps/web/dist
apps/server/.venv/bin/ai-org-server &          # API
npx --workspace @ai-org/web vite preview       # 127.0.0.1:3000에서 dist 제공 + /api 프록시
```

### 단일 프로세스(백엔드가 화면도 제공)

```bash
npm run build
AI_ORG_WEB_DIST=apps/web/dist apps/server/.venv/bin/ai-org-server   # http://127.0.0.1:8000
```

`AI_ORG_WEB_DIST`가 있으면 백엔드가 웹 빌드를 `/`에서 제공한다(화면 주소는 index.html로 대체, `/api`는 대체하지 않음).
데스크톱 번들은 번들 안의 `web/`을 자동으로 쓴다.

## 데이터

`~/.ai-org/`(ai-org.db, uploads/, workspaces/, designer/). 백업은 서버를 멈춘 뒤 폴더를 복사한다.
스키마 변경 시 마이그레이션 정책은 DATABASE.md.

## 데스크톱 앱

구조·결정: [ADR-009](decisions/ADR-009-desktop-tauri.md). 코드: `apps/desktop`(Tauri 2), `apps/desktop/sidecar/server.py`(백엔드 진입점).

### 설치 파일(GitHub Release)

| OS | 파일 |
|---|---|
| Linux x64 / arm64 | `.deb`, `.AppImage` |
| macOS(Apple Silicon) | `.dmg` |
| Windows x64 | `-setup.exe`(NSIS) |

- **먼저 Claude Code CLI를 설치하고 로그인**한다(`claude` 실행). 앱은 CLI를 포함하지 않는다.
- 서명하지 않은 빌드다. macOS는 처음 열 때 경고가 뜨면 `xattr -dr com.apple.quarantine "/Applications/AI Organization.app"` 후 다시 연다.
  Windows는 SmartScreen에서 `추가 정보 → 실행`. Linux AppImage는 `chmod +x` 후 실행(FUSE 필요, 없으면 `--appimage-extract-and-run`).
- 데이터는 브라우저 실행과 같은 `~/.ai-org`를 쓴다(두 방식을 동시에 실행하지 않는다 — 앱은 한 번만 실행되게 막혀 있다).

### 동작

- 시작하면 내장 백엔드를 루프백 임의 포트로 띄우고, 준비되면 창에 화면을 연다(첫 실행 시 몇 초).
- 창을 닫으면 트레이로 숨고 작업은 계속된다. 종료는 트레이 메뉴 `종료`.
- 트레이 메뉴: 실행 중인 에이전트 수, 승인 대기 수, 사용량(켜져 있을 때), 열기, 종료. 3초마다 갱신.
- 네이티브 알림: 승인 요청, 작업 완료·실패(사용자 대화의 응답, 위임 하위 실행 제외), 사용량 임계치.
- Linux 트레이는 AppIndicator(StatusNotifier) 지원이 필요하다. GNOME은 'AppIndicator' 확장을 켠다.

### 직접 빌드

```bash
npm ci && npm run build
python3 -m pip install ./apps/server "pyinstaller>=6.11"
scripts/build-sidecar.sh                          # apps/desktop/src-tauri/binaries/ai-org-server-<target>
cd apps/desktop && npx @tauri-apps/cli@2.12.6 build
```

Rust(rustup)와 OS별 Tauri 의존성이 필요하다(Linux: `libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev`).
CI(`.github/workflows/desktop.yml`)가 OS별로 빌드하고, 백엔드 스모크(`scripts/smoke_sidecar.py`)와 Linux 가상 화면 실행
스모크(`scripts/smoke_desktop.py`)를 돌린다. 태그 `v*`를 올리면 같은 이름의 GitHub Release에 설치 파일을 올린다.

### 브라우저 알림(데스크톱 앱 없이)

왼쪽 아래 `화면 설정 → 브라우저 알림 켜기` → 권한 허용. 탭이 보이지 않을 때만 승인 요청·작업 완료/실패·사용량 경고를 알린다.

## 라이선스

배포물에는 LICENSE(Apache-2.0), NOTICE, THIRD_PARTY_NOTICES.md를 함께 넣는다(Apache-2.0 §4, MIT 고지 유지).

## 하지 않는 것

원격 서버 배포, 외부 노출(리버스 프록시 포함). 루프백 바인딩만 지원한다.
