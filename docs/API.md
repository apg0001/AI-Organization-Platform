# API

기준 주소 `http://127.0.0.1:8000/api/v1`(개발 웹은 `:3000/api`를 프록시). 실행 중인 서버의 OpenAPI 문서: `/api/docs`.
요청·응답 스키마의 원본은 `apps/server/src/ai_org/schemas.py`, `spec.py`, `api/*.py`다.

## 공통 규칙

- **인증**: 로그인 세션 쿠키 `ai_org_session`(기본 켬, `AI_ORG_AUTH=off`로 끔). 없거나 만료면 `401`.
  예외: `/system/health`, `/auth/status|setup|login|logout`. WebSocket은 close 4401. 그 밖에 모든 요청에 다음을 강제한다([SECURITY.md](SECURITY.md)).
  - `Host`가 `127.0.0.1`·`localhost`·`[::1]`이 아니면 `403 host not allowed`
  - `Origin`이 있으면 `http://{127.0.0.1|localhost}:{3000|8000}`이 아니면 `403 origin not allowed`
  - 본문이 있는 POST/PUT/PATCH/DELETE는 `application/json`이어야 함(`/attachments`만 `multipart/form-data`) — 아니면 `415`
- **오류 형식**: `{"detail": "메시지"}` 또는 검증 오류 배열(`422`). 실행 중 적용 경고는 `{"detail": {"message", "running_agent_ids"}}`.
- **시각**: ISO 8601 UTC(`...Z`).

| 코드 | 의미 |
|---|---|
| 400/422 | 입력 검증 실패, 규칙 위반(순환 보고, 범위 밖 경로, 잘못된 명세) |
| 401 | 로그인 필요(세션 없음·만료) |
| 403 | Host/Origin 거부, 등록 경로 밖 접근, 현재 비밀번호 불일치 |
| 404 | 대상 없음 또는 다른 조직 소속 |
| 409 | 중복, 이미 처리됨, 실행 중 충돌(같은 에이전트 응답 중, 실행 중 적용) |
| 413/415 | 첨부 크기 초과 / 형식 불일치 |
| 429 | 로그인 시도 제한 |

## 인증

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/auth/status` | `{auth_enabled, setup_required, authenticated, user}` |
| POST | `/auth/setup` | 첫 계정 `{username, password(8자+), display_name?}` → 201 + 세션 쿠키. 계정이 있으면 409 |
| POST | `/auth/login` | `{username, password}` → 세션 쿠키. 실패 401, 시도 제한 429 |
| POST | `/auth/logout` | 세션 삭제, 쿠키 삭제(204) |
| PATCH | `/auth/me` | `{display_name?, settings?}` 사용자 설정(settings는 통째로 바꿈. 웹은 `theme`: dark·light·contrast·system을 저장) |
| POST | `/auth/password` | `{current_password, new_password}` → 204, 다른 세션 종료 |

## 시스템

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/system/health` | `{"status":"ok"}` |
| GET | `/system/info` | 버전, 데이터 폴더, 런타임 감지(`claude --version`) |
| GET | `/workspace` | 대시보드 묶음: 조직 요약, 프로젝트, 실행 중 에이전트, 최근 작업, 승인 대기, 활동 20건 |
| GET | `/capabilities` | 탐색한 Skills·MCP·Plugins(비밀 값 제외) |
| GET | `/capabilities/mcp/health` | `claude mcp list` 연결 점검 → `[{name, state, message}]`(state: connected·needs_auth·failed·pending_approval·disabled·unknown·error) |

## 사용량

[USAGE.md](USAGE.md) 참고. 응답에 토큰은 들어가지 않는다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/usage` | `{settings, providers:[{id, name, state, plan, observed_at, message, windows:[{id, label, percent, resets_at, window_minutes, elapsed_percent, burn_rate_per_hour, projected_at_reset, exhaust_at, confidence, samples}]}]}`. state: ok·disabled·pending·not_logged_in·token_expired·rate_limited·error·no_data |
| POST | `/usage/refresh` | 즉시 다시 조회(Claude는 최소 60초 간격 유지) |
| PUT | `/usage/settings` | `{claude_enabled?, codex_enabled?, thresholds?(1~100, 최대 5개)}` |
| GET | `/usage/history?provider=&window=&hours=` | `[{at, percent}]` |

## 데스크톱

`Authorization: Bearer <AI_ORG_DESKTOP_TOKEN>` 필요(데스크톱 앱이 백엔드를 띄울 때만 설정). 토큰이 설정되지 않았으면 404.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/desktop/summary?after=<id>` | `{version, running, approvals, usage:[{provider, label, percent}], notifications:[{id, at, kind, title, body, url}], latest_id}` — 알림은 `after`보다 큰 id만(최근 100개 보관). kind: approval·done·failed·usage |

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

### 에이전트 모델(`model`)

에이전트 생성·수정과 설계 명세의 `model`은 그 에이전트가 쓸 Claude 모델 이름이다. 원본: `schemas.clean_model`.

- `null`·빈 문자열: 기본값 — 모델을 지정하지 않고 Claude Code의 기본 모델을 쓴다(빈 문자열은 `null`로 저장).
- 형식만 검증한다: 앞뒤 공백을 뗀 뒤 1~100자, 영문·숫자와 `.` `_` `:` `-` `[` `]`만, `-`로 시작할 수 없다. 이름 목록으로 제한하지 않으며
  그 모델이 실제로 있는지도 확인하지 않는다. 웹은 `opus`·`sonnet`·`haiku`만 고르게 하고 다른 저장 값은 그대로 둔다.
- 모델만 바꾸려면 `PATCH …/agents/{agent_id}`에 `{"model": "sonnet"}`만 보낸다(새 경로 없음). **다음 실행부터 적용**되고 실행 중인 작업은 바뀌지 않는다.
- 형식이 틀리면 422: `{"detail": [{"type": "value_error", "loc": ["body", "model"], "msg": "Value error, 모델 이름은 `-`로 시작할 수 없습니다.", …}]}`.
  다른 사유: "모델 이름은 100자를 넘을 수 없습니다.", "모델 이름에는 영문·숫자와 `.` `_` `:` `-` `[` `]`만 쓸 수 있습니다(공백·따옴표 불가)."
- 조회 응답은 저장된 값을 읽는다. 저장돼 있던 값이 형식에 맞지 않으면 응답에서 `null`로 보이고 실행도 기본 모델로 한다(DB 값은 그대로, 서버 경고 로그).

### 에이전트 권한(`permissions`)

에이전트 생성·수정(`POST`·`PATCH …/agents`)과 설계 명세(`PUT /designs/{id}/spec`)의 `permissions` 본문이다. 원본: `schemas.AgentPermissions`.

```json
{
  "permission_mode": "default",
  "file_scope": [],
  "allow_shell": false,
  "allow_network": true,
  "allow_file_write": true,
  "allow_file_delete": false,
  "require_approval": ["shell", "file_write", "file_delete", "mcp"],
  "can_delegate": false,
  "allow_rules": []
}
```

- `permission_mode`: `default`·`acceptEdits`·`plan`·`auto`. `bypassPermissions`·`dontAsk` 등 그 밖의 값은 422.
  `auto`에서는 `require_approval`을 적용하지 않는다(값은 그대로 저장).
- `allow_rules`: 허용 리스트(문자열 배열, 최대 50개·규칙당 200자). 문법과 저장이 거부되는 규칙은 [SECURITY.md](SECURITY.md) §3.2·§3.3.
  저장할 때 공백을 정리하고 중복을 없앤 형태로 바뀐다(순서 유지). 응답에는 정리된 값이 온다.
- `PATCH`로 `permissions`를 보내면 그 객체 전체가 바뀐다(빠진 필드는 기본값).
- 규칙이 거부되면 422이고 `msg`에 사유가 온다(`Value error, ` 뒤가 사용자에게 보일 문장). 사유 예:
  "`git` 접두 규칙은 하위 명령까지 지정해야 합니다(예: `Bash(git <하위 명령>:*)`). 접두 규칙 대신 `Bash(명령 전체)`처럼 명령 전체를 적으세요."(`Bash(git:*)`),
  "`find`는 다른 명령을 실행하거나 파일을 덮어쓸 수 있어 접두 규칙으로 열 수 없습니다. …"(`Bash(find:*)`),
  "`npm install`는 패키지를 설치·변경하며 설치 스크립트를 실행할 수 있어 접두 규칙으로 못 엽니다. …"(`Bash(npm install:*)`),
  "`npx tsx`는 임의 코드를 실행하므로 접두 규칙으로 열 수 없습니다. …"(`Bash(npx tsx:*)`),
  "셸 규칙에는 `(`을(를) 쓸 수 없습니다(명령 연결·치환·리다이렉션·묶음 금지)."
- 조회 응답은 저장된 값을 읽는다. 저장 뒤 검증이 강화돼 더는 통과하지 못하는 규칙은 응답의 `allow_rules`에서 빠지고(서버 경고 로그) 조회·실행은 실패하지 않는다.
- 버전 필드가 없다: 오래된 `permissions` 전체를 `PATCH`하면 그 사이 '항상 허용'으로 추가된 규칙이 덮어써진다. 보내기 직전에 최신 값을 읽어 그 위에 고친다.

```json
{"detail": [{"type": "value_error", "loc": ["body", "permissions", "allow_rules"],
             "msg": "Value error, `rm` 명령은 허용 규칙에 넣을 수 없습니다.", "input": ["Bash(rm:*)"]}]}
```

`loc`의 앞부분은 경로마다 다르고(설계 명세는 `spec`·`agents`·번호가 낀다) 마지막 항목이 `allow_rules`다. 위 예의 `input` 등 나머지 필드는 Pydantic 기본 형식이다.

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
| GET/POST | `/conversations` | `?organization_id=` 목록 / `{organization_id, target_kind, target_id?, project_id?}` 생성. `project_id`를 주지 않았고 조직에 연결된 프로젝트가 하나뿐이면 그 프로젝트로 시작한다 |
| GET/PATCH/DELETE | `/conversations/{id}` | 메시지 포함 상세 / 제목·대상·프로젝트·컨텍스트·보관 / 삭제(첨부 파일도 삭제) |
| POST | `/conversations/{id}/messages` | `{content, mention_agent_ids[], mention_all, attachment_ids[]}` → 202 `{user_message, assistant_message_ids, queued_agent_ids}`. 대상 에이전트가 이 대화에서 응답 중이면 거절하지 않고 대기열에 넣는다(user 메시지 `data.queued`, `data.queue_state`: waiting·delivered·cancelled). 그 에이전트의 실행이 끝나면 대기 메시지를 순서대로 모아 같은 세션으로 이어서 전달한다. 실행 중인 턴 한가운데에 끼워 넣지는 않는다 |
| POST | `/conversations/{id}/messages/{mid}/cancel-queued` | 아직 전달 안 된 대기 메시지 취소(대기 중이 아니면 409). `/stop`과 서버 재시작도 대기 메시지를 취소한다 |
| POST | `/conversations/{id}/messages/{mid}/regenerate` | 같은 질문으로 다시 생성 |
| POST | `/conversations/{id}/stop` | 이 대화의 실행 중지 → `{stopped}` |
| GET | `/commands` | 슬래시 명령 명세 |
| POST | `/conversations/{id}/commands` | `{name, args}` 실행 → command 메시지 |
| POST | `/attachments` | multipart `file` → 초안 첨부 |
| GET/DELETE | `/attachments/{id}[/content]` | 내용(inline) / 초안 삭제(보낸 첨부는 409) |
| GET | `/approvals` | `?organization_id=&status=pending` → `[{id, organization_id, agent_id, kind, summary, detail, status, created_at}]` |
| POST | `/approvals/{id}/decision` | `{allow, always?}` → `{status, always?}`(아래) |
| GET | `/tasks` | `?organization_id=` |
| GET | `/runs` | 현재 실행 중인 메시지 |

### 승인 결정과 '항상 허용'

`approvals`의 `detail`:

| 필드 | 내용 |
|---|---|
| `tool`, `target` | 도구 이름, 짧은 대상(명령·경로, 최대 300자). 도구 원본 입력은 들어가지 않는다 |
| `group` | shell·file_write·file_delete·network·delegate·mcp 또는 `null`(묶음이 없는 도구 — 예: auto에서 Claude Code가 되물은 Read) |
| `reason` | 승인 사유(작업 폴더 밖 경로, "Claude Code가 확인을 요청했습니다." 등). 없으면 빈 문자열 |
| `source` | `hook`(모든 도구 호출 전 정책 판정) · `runtime`(Claude Code가 스스로 되물음 — auto 모드) |
| `always_rule` | '항상 허용'하면 추가될 규칙. 만들 수 없으면 `null`. 예: `ls -la` → `Bash(ls -la)`(기본은 명령 전체 일치), `git status -s` → `Bash(git status:*)`, `npm run build` → `Bash(npm run build:*)`, `npm install left-pad` → `Bash(npm install left-pad)`, `npx vitest run` → `Bash(npx vitest run)`(설치·패키지 실행은 전체 일치), 파일 쓰기 → `Edit(docs/a.md)` |
| `always_reason` | 규칙을 만들 수 없는 사유. 만들 수 있으면 `null`. 예: "삭제 요청은 항상 허용할 수 없습니다.", "작업 폴더 밖 경로를 참조하는 요청은 항상 허용할 수 없습니다.", "경로를 지정하지 않은(작업 폴더 전체) 요청은 항상 허용할 수 없습니다.", "셸 확장 문법(…)이 있는 명령은 허용 규칙에 넣을 수 없습니다." |
| `conversation_id`, `message_id` | 요청이 나온 대화·메시지 |

`POST /approvals/{id}/decision`:

| 요청 | 응답 |
|---|---|
| `{"allow": false}` | `{"status": "denied"}` |
| `{"allow": true}` | `{"status": "approved"}` |
| `{"allow": true, "always": true}` | `{"status": "approved", "always": {"rule", "added", "reason"}}` |
| `{"allow": false, "always": true}` | 422(`detail[0].msg`에 사유). 요청은 처리되지 않고 대기 상태로 남는다 |

- `always.rule`이 문자열이면 그 에이전트의 `allow_rules`에 있는 규칙이다. `added`가 `true`면 이번에 추가됐고, `false`면 이미 있던 규칙이다. `reason`은 `null`.
- `always.rule`이 `null`이면 규칙을 만들지 못해 **이번만 허용**된 것이고 `reason`에 사유가 온다(`added`는 `false`).
- 규칙이 추가되면 WebSocket `organization.updated`가 방송되고 활동 기록에 `agent.rule_added`가 남는다.
- 없는 승인은 404, 이미 처리됐거나 만료된 승인은 409.

## 프로젝트

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST/DELETE | `/project-roots[/{id}]` | 탐색 경로(`{path, max_depth 0..4}`, 루트 `/` 금지) |
| GET | `/project-roots/scan` | 경로 아래 프로젝트 후보 |
| GET | `/fs/browse?path=&hidden=` | 서버 컴퓨터 폴더 탐색(프로젝트 추가용). 홈 폴더 안만(심볼릭 링크 해석 후 검사, 밖이면 403), 하위 폴더 이름만(파일 제외), 숨김 폴더는 `hidden=true`일 때만, 최대 500개 → `{path, home, parent, is_git, kind, entries:[{name, path, is_git, kind}], truncated}` |
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
| `approval.requested` | organization_id, conversation_id, approval{id, agent_id, agent_name, tool, target, group, reason, source, always_rule, always_reason, message_id} | 승인 요청(필드 뜻은 '승인 결정과 항상 허용'의 `detail`과 같다. group은 `null`일 수 있다) |
| `approval.resolved` | organization_id, approval_id, status | 승인 처리 |
| `task.updated` | organization_id, task_id, status | 작업 상태 |
| `task.delegated` | organization_id, conversation_id, from_agent_id, to_agent_id, task_id, kind(delegated·review) | 에이전트 간 위임·검토 요청 |
| `design.updated` | design_id, status, busy | 설계 초안 변경 |
| `organization.updated` | organization_id | 설계 적용, '항상 허용'으로 에이전트 허용 규칙 추가 |
| `usage.updated` | — | 사용량 다시 조회됨 |
| `usage.threshold` | provider, window, threshold, percent, summary | 사용량 임계치를 처음 넘음 |
| `notify` | notification{id, at, kind, title, body, url} | 알림 센터가 고른 알림(승인 요청·작업 완료/실패·사용량 경고). 웹은 브라우저 알림으로 띄운다 |
