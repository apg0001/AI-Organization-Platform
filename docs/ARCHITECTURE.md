# 아키텍처

## 1. 구성 요소

```
┌────────────── 브라우저 (apps/web, Vite :3000) ──────────────┐
│ 대시보드 · 조직 설계 · 커맨드 센터 · 조직 · 에이전트 · 프로젝트 · 기능 · 사무실(Phaser) │
│ TanStack Query(REST 캐시)  ◀─ 무효화 ─  live.ts(WebSocket 구독)                   │
└───────────────┬──────────────────────────────────────────────┘
                │ /api/v1 (JSON, multipart는 업로드만) · /api/v1/ws
┌───────────────▼────────────── 로컬 백엔드 (apps/server, 127.0.0.1:8000) ─────────┐
│ LocalOnlyMiddleware (Host·Origin·JSON 검사)                                     │
│ api/  organizations · designs · chat · projects · system                        │
│ services/ design(명세↔조직, 적용, 이력) · runs(RunManager) · policy · commands    │
│           prompting · attachments · capabilities · projects · bus(EventBus)     │
│ runtime/  base(계약) · claude_code(Agent SDK) · activity(도구 분류)               │
│ SQLite (SQLAlchemy)  ~/.ai-org/ai-org.db · uploads/ · workspaces/ · designer/   │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │ claude-agent-sdk → 서브프로세스
        ┌───────▼────────┐
        │ claude CLI     │  에이전트 실행마다 1개 프로세스(턴이 끝나면 종료, resume으로 이어감)
        └────────────────┘
```

## 2. 계층과 책임

| 계층 | 책임 | 모르는 것 |
|---|---|---|
| 조직 관리(models, spec, services/design) | 조직·부서·에이전트·관계·정책·설계·이력 | 실행 방법 |
| 오케스트레이션(services/runs, commands, prompting, policy) | 라우팅, 프롬프트 구성, 권한 판정, 승인, 상태·작업 기록 | Claude Code 세부 |
| 런타임(runtime/) | `RunRequest` → 실행 → 정규화된 `RuntimeEvent` | 조직·정책의 의미 |

런타임은 `AgentRuntime` 프로토콜(`detect`, `start → RunHandle(events, interrupt)`)만 구현하면 교체할 수 있다(ADR-004).

## 3. 데이터 흐름: 채팅 한 턴

1. `POST /conversations/{id}/messages` → 라우팅(멘션 > 대화 대상: 에이전트/팀 대표/CEO), 컨텍스트 재검증, 사용자 메시지 저장.
2. 대상마다 assistant 메시지(`pending`) 생성 → `RunManager.launch` → 백그라운드 작업.
3. 동시 실행 세마포어(`AI_ORG_MAX_RUNS`)를 얻으면 `streaming`, `RuntimeSession` 기록, 에이전트 상태 `thinking`.
4. `RunRequest` 구성: 작업 폴더(연결된 프로젝트 또는 `~/.ai-org/workspaces/<org>/<agent>`), 시스템 프롬프트 추가분(조직·역할·지침·조직도),
   금지 도구, 권한 모드, 첨부 폴더(add_dirs), Skills, 이전 세션 ID(resume).
5. 런타임 이벤트 → `message.delta`(방송만) / `tool.started|completed|failed`(활동 기록·상태) / `turn.completed`(세션·비용).
6. 도구 호출마다 PreToolUse 훅 → `policy.decide` → 허용 / 거부 / 승인 대기(`Approval` + `approval.requested`).
7. 종료 시 메시지 확정(`done|error|interrupted`), 작업 결과, 활동 이벤트, `message.completed` 방송, 에이전트 상태 `completed|failed|idle`.

## 4. 데이터 흐름: 조직 설계

`OrgDesign.spec`(OrgSpec JSON)이 단일 상태다. 조직도 편집은 `PUT /designs/{id}/spec`, 대화는 설계 담당 Claude가
구조화 출력으로 새 명세를 내고 서버가 검증·정리(`sanitize_proposal`)해 같은 필드를 바꾼다. `apply`가 명세를 실제 행으로
반영하고 `OrgRevision` 스냅샷을 남긴다. 자세한 내용: [ORGANIZATION_BUILDER.md](ORGANIZATION_BUILDER.md).

## 5. 실시간 통신

- `GET /api/v1/ws`(WebSocket). 서버 → 클라이언트 단방향. 25초마다 `ping`.
- 백엔드의 `EventBus`(프로세스 내 asyncio 큐)가 구독자에게 이벤트를 나눠 준다. 느린 구독자는 이벤트를 잃을 수 있고(큐 1000),
  다시 연결하면 클라이언트가 모든 쿼리를 새로 받는다. 이벤트 목록: [API.md §WebSocket](API.md#websocket).
- 스트리밍 텍스트는 저장하지 않고 방송만 한다. 완료 시 확정본을 저장한다.

## 6. 프로세스 관리

- 턴마다 `claude` 프로세스를 띄우고 끝나면 닫는다(메모리 절약). 다음 턴은 `AgentThread`의 세션 ID로 resume.
- 같은 대화에서 같은 에이전트가 응답 중이면 새 메시지를 409로 거부한다(동시 resume 금지 — 공식 문서 경고).
- 중지: `ClaudeSDKClient.interrupt()`(5초 제한), 대기 중 승인은 거부 처리.
- 서버 시작 시 `recover()`가 남은 `pending/streaming` 메시지·세션·승인·작업·에이전트 상태를 정리한다.
- 서버 종료 시 실행을 중지하고 작업을 취소한다.

## 7. 저장소

- SQLite, WAL, 외래 키 사용. 스키마는 시작 시 `create_all`(마이그레이션 도구는 다음 스키마 변경 전에 도입, ADR-003).
- 파일: `~/.ai-org/uploads/<attachment_id>/<파일>`(0600), `workspaces/`, `designer/`(설계 담당 실행 폴더).
- Claude Code 세션 기록은 Claude Code가 `~/.claude/projects/`에 저장한다(이 앱은 세션 ID만 보관).

## 8. 디렉터리

```
apps/server/src/ai_org/
  main.py config.py db.py deps.py security.py models.py schemas.py spec.py
  api/ organizations.py designs.py chat.py projects.py system.py
  services/ design.py runs.py policy.py commands.py prompting.py attachments.py capabilities.py projects.py bus.py
  runtime/ base.py claude_code.py activity.py
  templates/*.json
apps/web/src/
  App.tsx main.tsx styles/globals.css
  lib/ api.ts queries.ts live.ts utils.ts
  components/ ui/ common/ layout/ org/ agent/
  features/ dashboard builder command organization agents projects capabilities office
```
