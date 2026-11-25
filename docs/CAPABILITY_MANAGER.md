# Capability Manager(기능 관리)

구현: `services/capabilities.py`, `GET /capabilities`, 웹 `features/capabilities/`, 에이전트 설정의 허용 목록.

## 현재(Phase 4 일부)

| 대상 | 출처(읽기 전용) | 화면 | 실행 반영 |
|---|---|---|---|
| Skills | `~/.claude/skills/*/SKILL.md`(user), 등록 프로젝트의 `.claude/skills/*/SKILL.md`(project) — frontmatter name·description | 목록·허용된 에이전트 | **예**: 허용된 Skill 이름을 SDK `skills` 옵션으로 전달 |
| MCP 서버 | `~/.claude.json`의 `mcpServers`(user)·`projects[경로].mcpServers`(local), 프로젝트 `.mcp.json`(project) | 이름·범위·전송·명령 이름·호스트·env/헤더 개수 | **아니오**: 실행은 `strict_mcp_config` + 빈 목록 |
| Plugins | `~/.claude/plugins/installed_plugins.json` + 각 `plugin.json` 설명 | 이름·마켓플레이스·버전 | 아니오 |

**비밀 보호**: env 값·헤더 값·명령 인자·명령 전체 경로·URL 쿼리는 응답에 넣지 않는다(테스트 `test_capabilities_never_leak_secrets`).
파일은 2MB 넘으면 읽지 않는다. 쓰기는 하지 않는다.

## 자동 선택과 권한의 분리

- 허용(권한): 에이전트의 `allowed_skills`·`allowed_mcp_servers`·`allowed_plugins`. 사용자만 바꾼다(AI 설계 제안은 추천만).
- 선택(자동): 허용된 것 중에서 Claude Code가 작업에 맞게 고른다(Skill 자동 호출은 Claude Code 동작). 허용되지 않은 것은 실행에 전달하지 않는다.

## Planned(Phase 4)

1. 허용된 MCP 서버의 설정을 백엔드가 읽어 실행마다 `mcp_servers`로 전달(비밀은 프로세스 메모리에서만 사용, 화면·DB 저장 금지).
2. 상태 점검: `claude mcp list` 결과(연결됨·인증 필요·실패)를 파싱해 표시. 도구 목록은 SDK `get_mcp_status`.
3. MCP 도구 호출은 기본적으로 사용자 승인(`policy`가 `mcp__*`에 `ask`) — 이미 구현됨, 연결만 남음.
4. Plugins: `plugins` 옵션으로 허용된 플러그인만 로드, 설치·업데이트는 `claude plugin` CLI를 사용자 확인 후 실행.
5. Hooks: 조직 단위 훅 정책 표시(읽기 전용부터).
