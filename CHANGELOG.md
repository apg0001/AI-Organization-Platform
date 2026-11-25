# 변경 기록

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따르고, 버전은 SemVer를 따른다.

## [Unreleased]

### 추가
- 애니메이션: 사무실 업무 전달 연출(위임 이벤트마다 봉투가 위임자→담당자로 이동, 동작 줄이기 시 정지)과 전달 기록, 새 메시지·상태 아이콘 전환 모션.
- 화면: 테마 4종(다크·라이트·고대비·시스템 설정, 계정에 저장)과 대시보드 시작 가이드 8단계(데이터·화면 방문으로 자동 완료).
- 사용량: Claude·Codex 사용률·초기화 남은 시간·소진 예측·이력 그래프·임계치 알림(GigaCharge 방식, Claude는 사용자가 켤 때만) — `docs/USAGE.md`.
- 오케스트레이션: 작업 계획 도구 `run_plan` — 선행 작업 순서·병렬 실행·선행 결과 전달·검토 수정 요청 시 재작업(최대 2회)·실패 전파.
- 문서: 이 플랫폼으로 이 저장소를 개발하는 방법과 첫 실측(`docs/SELF_DEVELOPMENT.md`). `/status`에 실행 중인 에이전트 표시(#23 — 플랫폼 에이전트가 구현).
- 테스트: Playwright 브라우저 E2E(사용자 여정 6단계), 테스트용 가짜 런타임(`AI_ORG_RUNTIME=fake`), CI E2E 작업.
- 로그인: 첫 실행 계정 생성, 로그인·로그아웃, 세션 쿠키(해시 저장), 로그인 시도 제한, 비밀번호 변경, `ai-org-admin reset-auth`, `AI_ORG_AUTH`.
- 오케스트레이션: 위임 권한이 있는 에이전트의 `delegate_task`·`request_review` 도구(하위·협업 대상만, 순환·깊이 제한), 같은 대화에서 위임 실행·보고 취합, 작업 트리, 실행 패널 위임 트리 표시.
- 기능 관리: 허용된 MCP 서버·Plugins를 에이전트 실행에 연결, `claude mcp list` 기반 MCP 연결 점검, MCP 도구 승인 묶음(`mcp`).
- 개발: 저장소 `.mcp.json`에 chrome-devtools MCP(헤드리스·임시 프로필·사용 통계 끔) — Claude Code로 화면을 검증할 때 사용.

### 변경
- 보안: 셸 경로 검사 오탐 수정 — 검색어(`/status`)를 경로로 보지 않고, 같은 명령의 `cd`를 따라 상대 경로를 계산.
- 보안: 셸 명령 안의 작업 폴더 밖 경로를 감지해 사용자 승인을 요구(승인 요청에 사유 표시).
- 라이선스: Apache License 2.0 적용(LICENSE, NOTICE).

### 추가
- 프로젝트 골격: FastAPI + SQLite 백엔드, React 19 + Vite + Tailwind v4 웹, 로컬 전용 보안 미들웨어.
- 조직 관리: 조직·부서·에이전트·협업 관계 CRUD, 순환 보고 방지, CEO 1명 규칙.
- 조직 설계(Organization Builder): 버전 있는 JSON 템플릿 6종, 설계 초안(단일 설계 상태), 설계 담당 Claude와의 대화형 설계(구조화 출력), AI 권한 확대 제안의 사용자 수락 절차, 적용 전 검토, 변경 이력·되돌리기.
- Claude Code 런타임: 공식 Agent SDK로 사용자의 CLI 실행, 스트리밍, 세션 이어가기(resume), 중지, PreToolUse 훅 기반 권한 정책과 사용자 승인.
- 채팅: CEO·팀·개별 에이전트 대화, @멘션·@All, 슬래시 명령 12종(Command Registry), 파일 첨부(검증·진행률), 컨텍스트(경로·에이전트·작업 결과·GitHub·Skill), WebSocket 실시간 이벤트.
- 프로젝트 관리: 탐색 경로 등록·탐색, 프로젝트 등록, Git 상태(읽기 전용).
- 기능 관리: Skills·MCP·Plugins 읽기 전용 탐색(비밀 값 제외).
- 아이소메트릭 사무실: Agent Office 렌더러 이식, 조직 에이전트 상태로 구동.
- 디자인 시스템과 문서 일체, Git 규칙·템플릿, CI Gate.
