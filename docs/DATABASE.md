# 데이터베이스

SQLite 파일 `~/.ai-org/ai-org.db`(WAL, `PRAGMA foreign_keys=ON`). ORM 정의: `apps/server/src/ai_org/models.py`.
ID는 uuid4 hex(32자). 시각은 UTC로 저장하고 API는 `Z` 오프셋으로 낸다(`UTCDateTime`).

## 엔티티 관계

```
Organization 1─* Department
Organization 1─* Agent ─(reports_to)→ Agent        (트리, 순환 금지)
Organization 1─* Collaboration (Agent → Agent, kind)
Organization 1─* OrgDesign(organization_id 없으면 새 조직 설계) · 1─* OrgRevision
Organization 1─* Conversation 1─* ChatMessage · 1─* Attachment · 1─* AgentThread(대화×에이전트)
Organization 1─* Task(parent_id 트리) · 1─* Approval · 1─* ActivityEvent
Agent 1─* RuntimeSession
Project *─1 Organization(선택) · ProjectRoot(독립)
```

## 테이블

| 테이블 | 주요 필드 | 설명 |
|---|---|---|
| organizations | name, description, mission, base_instructions, policy(JSON), template_key, default_project_id | 회사 |
| departments | organization_id, name, description, color(`dept-1..8`), sort_order | 부서 |
| agents | organization_id, department_id, reports_to_id, name, title, role, responsibilities(JSON), expertise(JSON), instructions, is_lead, enabled, runtime, model, allowed_skills/mcp_servers/plugins(JSON), permissions(JSON, `AgentPermissions`), status, pos_x/y | 구성원 정의와 관측 상태 |
| collaborations | source_agent_id, target_agent_id, kind(handoff·review·consult), label | 협업 관계(유일: source·target·kind) |
| project_roots | path(유일), max_depth | 탐색 허용 경로 |
| projects | name, path(유일), description, kind, organization_id | 등록 프로젝트 |
| tasks | organization_id, project_id, parent_id, assignee_id, requested_by_id, title, brief, status, priority, result, depends_on(JSON) | 작업 |
| runtime_sessions | agent_id, task_id, runtime, external_session_id, cwd, state, cost_usd, ended_at | 실행 한 번 |
| approvals | organization_id, agent_id, session_id, kind, summary, detail(JSON), status, decided_at | 사용자 승인 |
| activity_events | organization_id, agent_id, kind, summary, created_at | 감사·타임라인 |
| conversations | organization_id, target_kind(org·team·agent), target_id, project_id, title, context(JSON), archived | 대화 |
| chat_messages | conversation_id, role(user·assistant·command·system), agent_id, content, data(JSON), activity(JSON), status, error, session_id, cost_usd, duration_ms, task_id | 메시지 |
| agent_threads | conversation_id, agent_id(유일 쌍), session_id, cwd | resume용 Claude Code 세션 |
| attachments | conversation_id(보내기 전 NULL), filename, media_type, size, sha256, stored_path | 첨부 |
| org_designs | organization_id, origin, spec(JSON `OrgSpec`), messages(JSON), notes(JSON), designer_session_id, status, busy | 설계 초안 |
| org_revisions | organization_id, spec(JSON), summary(JSON), source | 적용 이력 |
| users | username(유일), display_name, password_hash(scrypt), settings(JSON), last_login_at | 앱 로그인 계정 |
| usage_samples | provider, window_id, percent, resets_at, observed_at | 사용량 이력(30일 보관) |
| app_settings | key(기본 키), value(JSON) | 앱 설정(사용량 `usage`) |
| auth_sessions | user_id, token_hash(SHA-256, 유일), expires_at, last_seen_at | 로그인 세션 |

## 값 규칙

- `agents.status`: idle · thinking · working · waiting · reviewing · completed · failed · offline
- `tasks.status`: queued · running · waiting · review · done · failed · cancelled
- `chat_messages.status`: pending · streaming · done · error · interrupted
- `approvals.status`: pending · approved · denied · expired
- JSON 정책 값의 스키마는 `schemas.AgentPermissions`, `schemas.OrgPolicy`, `spec.OrgSpec`.

## 마이그레이션 정책

현재(0.0.x)는 시작 시 `create_all`만 한다 — 기존 테이블의 열 변경은 반영되지 않는다. 개발 중 스키마가 바뀌면
`~/.ai-org/ai-org.db`를 지우거나 백업 후 다시 만든다. **다음 스키마 변경 전에 Alembic을 도입**한다(ADR-003의 후속).
