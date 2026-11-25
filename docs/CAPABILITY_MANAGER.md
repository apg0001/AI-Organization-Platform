# Capability Manager(기능 관리)

구현: `services/capabilities.py`, `GET /capabilities`, 웹 `features/capabilities/`, 에이전트 설정의 허용 목록.

## 현재(Phase 4)

| 대상 | 출처(읽기 전용) | 화면 | 실행 반영 |
|---|---|---|---|
| Skills | `~/.claude/skills/*/SKILL.md`(user), 등록 프로젝트의 `.claude/skills/*/SKILL.md`(project) — frontmatter name·description | 목록·허용된 에이전트 | 허용된 Skill 이름을 SDK `skills` 옵션으로 전달 |
| MCP 서버 | `~/.claude.json`의 `mcpServers`(user)·`projects[경로].mcpServers`(local), 프로젝트 `.mcp.json`(project) | 이름·범위·전송·명령 이름·호스트·env/헤더 개수, 연결 점검 | 허용된 서버의 원본 설정을 SDK `mcp_servers`로 전달(`strict_mcp_config`로 그 밖의 서버 차단) |
| Plugins | `~/.claude/plugins/installed_plugins.json` + 각 `plugin.json` 설명 | 이름·마켓플레이스·버전 | 허용된 플러그인 설치 경로를 SDK `plugins`(local)로 전달 |

**연결 점검**: `GET /capabilities/mcp/health`가 `claude mcp list`를 홈(사용자 범위)과 `.mcp.json`이 있는 등록 프로젝트에서 실행해
결과(연결됨·인증 필요·실패·CLI 승인 대기·비활성)를 합친다. 'CLI 승인 대기'는 그 폴더에서 대화형 `claude`를 쓸 때의 프로젝트 서버
승인 상태이며, 이 앱의 에이전트 실행은 설정을 직접 넘기므로 영향을 받지 않는다.

**MCP 도구 승인**: MCP 도구 호출은 권한 묶음 `mcp`로 판정한다. 기본값은 '실행 전에 내 승인 받기'에 포함(승인 필요).

**실측(2026-11-25)**: 저장소 `.mcp.json`의 `chrome-devtools`(chrome-devtools-mcp 1.14.0, 헤드리스·임시 프로필·사용 통계와 CrUX 전송 끔)를
CEO에게 허용 → "로컬 페이지를 열고 내용을 알려 줘" → `new_page`·`take_snapshot` 각각 승인 후 실행, 페이지 내용 응답(14초).

**비밀 보호**: env 값·헤더 값·명령 인자·명령 전체 경로·URL 쿼리는 응답에 넣지 않는다(테스트 `test_capabilities_never_leak_secrets`).
파일은 2MB 넘으면 읽지 않는다. 쓰기는 하지 않는다.

## 자동 선택과 권한의 분리

- 허용(권한): 에이전트의 `allowed_skills`·`allowed_mcp_servers`·`allowed_plugins`. 사용자만 바꾼다(AI 설계 제안은 추천만).
- 선택(자동): 허용된 것 중에서 Claude Code가 작업에 맞게 고른다(Skill 자동 호출은 Claude Code 동작). 허용되지 않은 것은 실행에 전달하지 않는다.

## Planned

1. 서버별 도구 목록 표시(SDK `get_mcp_status`), 도구 단위 허용.
2. 설치·업데이트: `claude mcp add`·`claude plugin install`을 사용자 확인 후 실행하는 화면.
3. Hooks: 조직 단위 훅 정책 표시(읽기 전용부터).
4. 같은 이름의 서버가 여러 프로젝트 `.mcp.json`에 있을 때 ID에 프로젝트 포함(현재는 범위+이름, 처음 찾은 것 사용).
