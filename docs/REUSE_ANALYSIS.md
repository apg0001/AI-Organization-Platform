# Agent Office 재사용 분석

대상: `apg0001/Agent-Office` 0.1.0-beta.10(로컬 `~/Agent-Office`, MIT). **원본은 수정하지 않았다**(읽기·복사만).
신규 프로젝트는 원본 없이 실행된다(빌드·런타임 의존 없음).

## 1. Agent Office는 무엇인가

여러 PC의 Claude Code·Codex 세션을 Go Collector(훅·JSONL)가 관측해 FastAPI + PostgreSQL 서버로 보내고, React + Phaser 4
아이소메트릭 사무실에 픽셀 캐릭터로 보여 주는 **다중 사용자 관측 서비스**. 에이전트를 실행하지 않는다.
→ 우리는 **단일 사용자 로컬 앱 + 에이전트를 직접 실행**하므로 서버·수집 구조는 계승하지 않는다.

## 2. 모듈별 판단

| 모듈 | 판단 | 이유 / 결과 |
|---|---|---|
| 사무실 렌더러 `apps/web/src/office/` 순수 모듈(iso, grid, pathfinding, camera, walls, behavior, smoothing, presence, headline, lab, furnitureArt, sprites, types, workspace) | **복사·소폭 수정** | Phaser 없이 테스트된 순수 코드, 독립적. `sprites`에 `member` 역할(왕관 없음) 추가, `behavior`가 구성원에게도 책상 배정 |
| `OfficeScene.ts` | **복사·소폭 수정** | 입력 상태 모델(장치·세션·에이전트)을 그대로 두고 어댑터(`orgOffice.ts`)로 조직 데이터를 맞춤. create() 중 `applyState`가 무시되는 문제(초기 상태가 완전한 경우 캐릭터가 안 나옴)를 첫 프레임 적용으로 수정 — 원본에도 잠재(실시간 갱신으로 가려짐) |
| Kenney Furniture Kit PNG 15개 | **복사** | CC0 |
| Galmuri 글꼴 | **복사**(지도 라벨만) | OFL, 라이선스 동봉 |
| OfficeView·SessionList·AgentPanel·liveSource·synthetic | 재구현 | 세션·장치·팀 범위 UI. 우리 화면 구조와 다름 |
| styles.css(픽셀 UI) | 미사용 | 제품 전체가 게임처럼 보이지 않게(브리프) — 픽셀은 아바타·사무실에만 |
| 서버 `state/engine.py`(훅 이벤트 → 턴 상태) | 개념 재사용 | 우리는 SDK 이벤트를 직접 받아 상태 전이를 `RunManager`에 구현 |
| Collector 도구 분류·테스트 명령 판별(Go) | **Python으로 이식** | `runtime/activity.py`. 사무실 구역·활동 패널 분류 |
| `origin.py`, Host 검사 아이디어 | 재구현 | 로컬 전용 미들웨어(Host 허용 목록 추가) |
| WebSocket 스냅샷+델타 프로토콜, `change_seq` | 단순화 | 프로세스 내 버스 + 재연결 시 전체 재조회 |
| `state/desks.py` 책상 배정 | 미사용 | 조직도 순서로 고정 배정(세션 수명과 무관) |
| 훅 안전 설치(Go hooks) | 미사용(참고) | 우리는 사용자 설정을 건드리지 않고 SDK 훅을 실행마다 전달 |
| 인증·팀·장치·OAuth·알림·백업·보존·비밀 저장소 | 미사용 | 다중 사용자 기능. 로그인 설계 시 OAuth 흐름만 참고(SECURITY.md §7) |
| PostgreSQL 스키마·Alembic | 미사용 | SQLite, 도메인이 다름 |
| 기술 스택(React 19, TS 7, Vite 8, Phaser 4.2.1, Vitest, FastAPI, Ruff·mypy strict) | **계승** | 같은 Pi에서 검증된 조합 |

## 3. 라이선스

Agent Office는 MIT → 복사·수정한 파일은 머리 주석과 `THIRD_PARTY_NOTICES.md`에 출처와 MIT 고지를 남겼다.
Kenney CC0, Galmuri OFL 1.1(라이선스 파일 동봉).

## 4. 위험

- Phaser 번들(약 1.4MB)은 사무실 화면에서만 지연 로드.
- 렌더러는 Agent Office의 장치·세션 모델을 전제한다 → 어댑터가 깨지지 않도록 `orgOffice.ts` 테스트 유지.
- Agent Office가 고친 버그를 자동으로 받지 않는다(복사본). 큰 변경이 있으면 차이를 수동 검토한다.
