# Claude Code 런타임 연동

구현: `apps/server/src/ai_org/runtime/claude_code.py`(실행), `runtime/base.py`(계약), `runtime/activity.py`(도구 분류),
`services/runs.py`(실행 관리), `services/policy.py`(권한).

## 1. 연결 방식

공식 **Claude Agent SDK(Python, `claude-agent-sdk`)** 의 `ClaudeSDKClient`로 Claude Code CLI를 서브프로세스로 실행한다(ADR-004).
- `cli_path`를 사용자가 설치한 `claude`(PATH)로 지정 → SDK에 포함된 CLI 대신 사용자의 버전·로그인을 쓴다.
- 대안 비교: `claude -p --output-format stream-json`을 직접 다루면 의존성은 줄지만 권한 콜백(`can_use_tool`)·훅·중단을
  직접 구현해야 한다. Agent Teams는 실험 기능이고 `-p`/SDK에서 팀원이 생성되지 않아 쓰지 않는다(공식 문서 agent-teams).

검증 환경: Claude Code 2.1.326, claude-agent-sdk 0.2.189(번들 CLI 2.1.332), Raspberry Pi aarch64, 2026-11-25.

## 2. 인증

- 이 앱은 Claude 자격증명을 읽거나 저장하지 않는다. CLI에 로그인된 자격(`~/.claude/.credentials.json` 등)을 CLI가 직접 쓴다.
- 공식 문서의 인증 우선순위상 `ANTHROPIC_API_KEY`가 있으면 `-p`/SDK 실행은 구독 로그인보다 API 키를 쓴다 → `/system/info`가 경고한다.
- `--bare` 모드는 OAuth를 읽지 않으므로 쓰지 않는다.
- 이용 약관: Anthropic은 승인 없이 제3자 제품이 claude.ai 로그인을 제공하는 것을 허용하지 않는다(Agent SDK 개요).
  이 앱은 사용자 본인 컴퓨터에서 본인 CLI를 실행하는 로컬 도구다. 배포·공유 형태가 바뀌면 이 조건을 다시 검토한다(**검토 중**).

## 3. 실행 옵션(에이전트 한 턴)

| 옵션 | 값 | 이유 |
|---|---|---|
| `cwd` | 대화에 연결된 프로젝트, 없으면 `~/.ai-org/workspaces/<org>/<agent>` | 에이전트별 작업 폴더 분리 |
| `system_prompt` | `{"type":"preset","preset":"claude_code","append": 조직·역할 지침}` | Claude Code 기본 동작 유지 + 역할 부여 |
| `setting_sources` | `["project"]` | 사용자 전역 allow 규칙이 앱 승인을 건너뛰지 않게 |
| `disallowed_tools` | 권한에서 끈 도구 묶음(Bash 등) | deny 규칙은 모든 모드에서 우선 |
| `permission_mode` | default · plan · acceptEdits (bypassPermissions 금지) | |
| `add_dirs` | 첨부 파일 폴더 | Read 도구로 첨부를 읽게 |
| `skills` | 에이전트에게 허용된 Skill 이름 | SDK의 Skills 제한 옵션 |
| `mcp_servers`, `strict_mcp_config=True` | 에이전트에게 허용된 MCP 서버의 원본 설정만 | 허용하지 않은 서버(사용자·프로젝트 설정)는 붙지 않음 |
| `plugins` | 허용된 플러그인 설치 경로(`{"type":"local"}`) | |
| `resume` | 같은 대화·에이전트·작업 폴더의 이전 세션 ID | 대화 맥락 유지 |
| `include_partial_messages` | True | 텍스트 스트리밍 |
| `max_turns` | `AI_ORG_MAX_TURNS`(30) | 폭주 방지 |
| `hooks.PreToolUse` | 정책 훅(타임아웃 = 승인 대기 + 30초) | 아래 §5 |

설계 담당자 실행은 다르다: `tools=[]`, `setting_sources=[]`, `system_prompt`=설계 지침만, `output_format`=JSON 스키마.

## 4. 이벤트 정규화

| SDK 메시지 | RuntimeEvent |
|---|---|
| `SystemMessage(init)` | `session.started{session_id, model, tools, skills}` |
| `StreamEvent(content_block_delta/text_delta)`(하위 에이전트 제외) | `message.delta{text}` |
| `AssistantMessage` TextBlock / ToolUseBlock | `message{text}` / `tool.started{id, tool, input, subagent}` |
| `UserMessage` ToolResultBlock | `tool.completed` / `tool.failed{id}` |
| `ResultMessage` | `turn.completed{session_id, is_error, subtype, cost_usd, duration_ms, num_turns, structured_output, result, interrupted}` |
| 예외 | `error{message}` |

도구 입력 원문은 저장하지 않는다. `activity.target_of`가 경로·명령·검색어를 120자로 줄여 활동 패널에 쓴다.
비용(`total_cost_usd`)은 SDK가 계산한 추정치다.

## 5. 권한과 승인

1. 모든 도구 호출은 먼저 **PreToolUse 훅**에서 `policy.decide`로 판정된다: 허용 범위 밖 경로 → 거부, 꺼진 묶음 → 거부,
   `require_approval` 묶음 → 사용자 승인 대기, 그 외 → 통과.
2. 훅은 거부하거나 통과시킬 뿐 `allow`를 반환하지 않는다(Claude Code 확인을 건너뛰어 권한을 넓히지 않음).
3. 그 뒤 Claude Code가 자체 규칙으로 확인을 요청하면 `can_use_tool`이 불리고, 훅에서 이미 통과한 호출이면 허용한다.

**왜 훅인가(실측)**: `can_use_tool`만 쓰면 Claude Code가 묻지 않고 허용하는 읽기 전용 명령(`echo` 등)이 승인 없이 실행됐다.
**구조화 출력 주의(실측)**: Claude Code는 구조화 출력을 내부 도구 `StructuredOutput` 호출로 전달한다. 설계 담당자의 '모든 도구 거부'
정책이 이것까지 막아 결과를 받지 못했다 → 그 도구만 허용한다.

승인 대기는 `asyncio.Future`로 실행을 멈추고(`AI_ORG_APPROVAL_TIMEOUT`, 기본 900초), 사용자가 `POST /approvals/{id}/decision`으로
결정한다. 시간이 지나거나 실행이 끝나면 거부·만료 처리한다. 장기 대기용 `defer`/resume 방식은 Phase 5에서 검토한다.

## 6. 세션

- 한 턴 = 한 프로세스. 끝나면 `disconnect`. 다음 턴은 `AgentThread`(대화×에이전트)의 세션 ID로 `resume`.
- 작업 폴더가 바뀌면 resume하지 않는다(Claude Code는 세션을 작업 폴더 기준으로 찾는다).
- resume 시 MCP·도구·설정 플래그는 복원되지 않으므로 매 턴 다시 전달한다(공식 문서 sessions).
- 같은 세션을 두 프로세스가 동시에 이어 쓰지 않도록 같은 대화의 같은 에이전트 동시 실행을 막는다.
- 세션 기록은 Claude Code가 보관한다(기본 30일, `cleanupPeriodDays`).

## 7. 오류·재시도·중지

- SDK 예외·CLI 미설치·작업 폴더 없음 → `error` 이벤트 → 메시지 `error` 상태(자동 재시도 없음, 사용자가 '다시 생성').
- API 재시도는 Claude Code가 자체 수행한다(`system/api_retry`).
- 중지: `client.interrupt()` → 메시지 `interrupted`, 대기 승인 거부.
- 서버 재시작: `recover()`가 진행 중 상태를 `interrupted`/`expired`로 정리.

## 8. 동시성·자원

- 동시 실행 수 `AI_ORG_MAX_RUNS`(기본 2). 초과분은 `pending`으로 기다린다.
- 라즈베리 파이 실측: 단순 응답 약 5초, 설계 담당 턴 1~2분(구조화 출력 + 큰 명세).

## 9. 런타임 확장

`AgentRuntime` 프로토콜(`detect()`, `start(request, on_permission) → RunHandle`)을 구현하고 `main.create_app`의
`runtime_for`에 등록한다. 조직의 `Agent.runtime` 필드가 선택 키다(현재 `claude-code`만 허용). 다른 CLI도 '권한 콜백·중단·세션 ID'를
제공할 수 있어야 같은 정책을 지킬 수 있다.
