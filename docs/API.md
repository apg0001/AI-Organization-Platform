# API

기준 주소 `http://127.0.0.1:8000/api/v1`(개발 웹은 `:3000/api`를 프록시). 실행 중인 서버의 OpenAPI 문서: `/api/docs`.
요청·응답 스키마의 원본은 `apps/server/src/ai_org/schemas.py`, `spec.py`, `api/*.py`다.

## 공통 규칙

- **인증**: 없음(로컬 단일 사용자). 대신 모든 요청에 다음을 강제한다([SECURITY.md](SECURITY.md)).
  - `Host`가 `127.0.0.1`·`localhost`·`[::1]`이 아니면 `403 host not allowed`
  - `Origin`이 있으면 `http://{127.0.0.1|localhost}:{3000|8000}`이 아니면 `403 origin not allowed`
  - 본문이 있는 POST/PUT/PATCH/DELETE는 `application/json`이어야 함(`/attachments`만 `multipart/form-data`) — 아니면 `415`
- **오류 형식**: `{"detail": "메시지"}` 또는 검증 오류 배열(`422`). 실행 중 적용 경고는 `{"detail": {"message", "running_agent_ids"}}`.
- **시각**: ISO 8601 UTC(`...Z`).

| 코드 | 의미 |
|---|---|
| 400/422 | 입력 검증 실패, 규칙 위반(순환 보고, 범위 밖 경로, 잘못된 명세) |
| 403 | Host/Origin 거부, 등록 경로 밖 접근 |
| 404 | 대상 없음 또는 다른 조직 소속 |
| 409 | 중복, 이미 처리됨, 실행 중 충돌(같은 에이전트 응답 중, 실행 중 적용) |
| 413/415 | 첨부 크기 초과 / 형식 불일치 |

## 시스템

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/system/health` | `{"status":"ok"}` |
| GET | `/system/info` | 버전, 데이터 폴더, 런타임 감지(`claude --version`) |
| GET | `/workspace` | 대시보드 묶음: 조직 요약, 프로젝트, 실행 중 에이전트, 최근 작업, 승인 대기, 활동 20건 |
| GET | `/capabilities` | 탐색한 Skills·MCP·Plugins(비밀 값 제외) |
| GET | `/capabilities/mcp/health` | `claude mcp list` 연결 점검 → `[{name, state, message}]`(state: connected·needs_auth·failed·pending_approval·disabled·unknown·error) |

## 조직

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST | `/organizations` | 목록(요약·개수) / 생성(CEO 1명 포함) |
| POST | `/organizations/from-template` | `{template_key, name?}` 템플릿을 검토 없이 바로 적용(테스트·빠른 시작용) |
| GET/PATCH/DELETE | `/organizations/{id}` | 상세(부서·에이전트·협업 포함) / 수정 / 삭제 |
| PUT | `/organizations/{id}/layout` | 조직도 위치 저장 `{positions:[{id,x,y}]}` |
| POST, PATCH, DELETE | `/organizations/{id}/departments[/{dept_id}]` | 부서 |
| POST, PATCH, DELETE | `/organizations/{id}/agents[/{agent_id}]` | 에이전트(삭제 시 부하는 상위로 재연결) |
| GET | `/agents/{agent_id}` | 에이전트 단건 |
| POST, DELETE | `/organizations/{id}/collaborations[/{collab_id}]` | 협업 관계 |
| GET | `/organizations/{id}/revisions` | 적용 이력 |
| POST | `/organizations/{id}/revisions/{rid}/restore` | 그 구성으로 설계 초안 생성(적용 아님) |

## 조직 설계

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/templates` | 템플릿 전체(명세 포함) |
| POST | `/designs` | `{organization_id?|template_id?, name?}` 초안 생성 |
| GET | `/designs` | 작성 중 초안 목록(`?organization_id=`) |
| GET/DELETE | `/designs/{id}` | 초안(명세·대화·추천 상태) / 버리기 |
| PUT | `/designs/{id}/spec` | `{spec, note?}` 직접 편집 반영(검증) |
| POST | `/designs/{id}/accept-permissions/{agent_key}` | AI 권한 확대 제안 수락 |
| POST | `/designs/{id}/messages` | `{content}` 설계 담당에게 보냄(202, 결과는 `design.updated`) |
| POST | `/designs/{id}/apply` | `{confirm_running}` 적용 → `{organization_id, changes}` |

## 채팅

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST | `/conversations` | `?organization_id=` 목록 / `{organization_id, target_kind, target_id?, project_id?}` 생성 |
| GET/PATCH/DELETE | `/conversations/{id}` | 메시지 포함 상세 / 제목·대상·프로젝트·컨텍스트·보관 / 삭제(첨부 파일도 삭제) |
| POST | `/conversations/{id}/messages` | `{content, mention_agent_ids[], mention_all, attachment_ids[]}` → 202 `{user_message, assistant_message_ids}` |
| POST | `/conversations/{id}/messages/{mid}/regenerate` | 같은 질문으로 다시 생성 |
| POST | `/conversations/{id}/stop` | 이 대화의 실행 중지 → `{stopped}` |
| GET | `/commands` | 슬래시 명령 명세 |
| POST | `/conversations/{id}/commands` | `{name, args}` 실행 → command 메시지 |
| POST | `/attachments` | multipart `file` → 초안 첨부 |
| GET/DELETE | `/attachments/{id}[/content]` | 내용(inline) / 초안 삭제(보낸 첨부는 409) |
| GET | `/approvals` | `?organization_id=&status=pending` |
| POST | `/approvals/{id}/decision` | `{allow}` |
| GET | `/tasks` | `?organization_id=` |
| GET | `/runs` | 현재 실행 중인 메시지 |

## 프로젝트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST/DELETE | `/project-roots[/{id}]` | 탐색 경로(`{path, max_depth 0..4}`, 루트 `/` 금지) |
| GET | `/project-roots/scan` | 경로 아래 프로젝트 후보 |
| GET/POST | `/projects` | 목록 / 등록(등록 경로 안만, 심볼릭 링크 해석) |
| GET/PATCH/DELETE | `/projects/{id}` | Git 정보 포함 상세 / 이름·설명·조직 / 등록 해제(파일 유지) |
| GET | `/projects/{id}/tree?path=` | 한 단계 디렉터리 목록(프로젝트 밖 403) |

## WebSocket

`/api/v1/ws` — 연결 시 Host·Origin을 검사(위반 시 close 4403). 서버가 보내는 메시지는 모두 `{type, at, ...}`.

| type | 필드 | 의미 |
|---|---|---|
| `ping` | — | 25초 유휴 시 |
| `message.created` | conversation_id, message | 새 메시지(사용자·assistant pending·command) |
| `message.status` | conversation_id, message_id, status | `streaming` 시작 |
| `message.delta` | conversation_id, message_id, text | 스트리밍 텍스트 조각 |
| `run.activity` | conversation_id, message_id, agent_id, entry | 도구 사용(id, tool, activity, target, status) |
| `run.denied` | conversation_id, message_id, agent_id, tool, reason | 정책 거부 |
| `message.completed` | conversation_id, message | 확정된 메시지 |
| `agent.status` | organization_id, agent_id, status, detail | 상태 변경(detail: 활동 분류 또는 도구) |
| `approval.requested` | organization_id, conversation_id, approval{id, agent_id, agent_name, tool, target, group, reason, message_id} | 승인 요청(reason: 범위 밖 경로 등 승인 사유) |
| `approval.resolved` | organization_id, approval_id, status | 승인 처리 |
| `task.updated` | organization_id, task_id, status | 작업 상태 |
| `design.updated` | design_id, status, busy | 설계 초안 변경 |
| `organization.updated` | organization_id | 설계 적용 |
