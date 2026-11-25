# ADR-004: Claude Code 실행 방식 — 공식 Agent SDK(Python)로 사용자 CLI 실행

- 날짜: 2026-11-25 · 상태: 채택

## 배경
에이전트는 사용자의 Claude Code로 실제 일을 해야 한다(자체 Messages API 에이전트 금지). 권한 승인·중단·세션 유지·실시간 이벤트가 필요하다.

## 대안
1. `claude -p --output-format stream-json` 서브프로세스 직접 관리 2. Claude Agent SDK(`ClaudeSDKClient`) 3. Agent Teams(실험 기능)
4. Agent Office처럼 훅으로 관측만

## 결정
Agent SDK로 실행하고 `cli_path`를 사용자의 `claude`로 지정. 권한은 PreToolUse 훅(정책) + `can_use_tool`. 턴마다 프로세스, `resume`으로 이어감.
런타임 계약(`AgentRuntime`)으로 격리해 다른 런타임을 추가할 수 있게 한다.

## 이유
SDK가 권한 콜백·훅·인터럽트·구조화 출력·Skills 제한을 공식 지원한다. CLI 직접 관리는 이를 다시 구현해야 한다.
Agent Teams는 실험 기능이고 SDK/`-p`에서 팀원이 만들어지지 않으며 팀원별 권한 모드를 정할 수 없다.

## 영향
+ 공식 인터페이스만 사용, 권한 우회 없음. + 실측 검증(ROADMAP). − SDK 휠이 큼(번들 CLI 포함 약 170MB). − 턴마다 프로세스 시작 지연(수 초).
− 이용 약관상 제3자 제품의 claude.ai 로그인 제공 제한 → 현재 형태(본인 컴퓨터의 본인 CLI)는 문제 소지가 낮다고 보지만 배포 형태가 바뀌면 재검토.
