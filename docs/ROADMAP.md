# 로드맵과 구현 상태

상태: **Planned** → **In Progress** → **Implemented**(코드 있음) → **Tested**(자동 테스트 또는 실제 실행 검증) → **Completed**(구현·테스트·문서 모두 확인) / **Blocked**.
코드만 있는 것을 완료로 표시하지 않는다. 마지막 갱신: 2026-11-25.

| 단계 | 내용 | 상태 |
|---|---|---|
| Phase 0 | 기존 Agent Office 분석, 재사용 판단 | Completed — [REUSE_ANALYSIS.md](REUSE_ANALYSIS.md) |
| Phase 1 | 독립 저장소, 백엔드·웹 골격, 데이터 모델, 로컬 실행, 디자인 시스템 | Completed |
| Phase 2 | 조직 관리 + Organization Builder(템플릿·대화형 설계·검토·이력) | Tested — UI 자동 테스트 미작성 |
| Phase 3 | Claude Code 런타임·세션·이벤트·채팅·승인 | Tested — 실제 Claude 스모크 테스트 통과(아래) |
| Phase 4 | Capability Manager | Tested — 탐색·허용·실행 연결(Skills·MCP·Plugins)·MCP 연결 점검. 설치 UI·도구 단위 허용 Planned |
| Phase 5 | 오케스트레이션(CEO 자동 분배, 에이전트 간 메시지, 검토·재작업) | Tested — 위임·검토 요청·작업 계획(선행 작업·병렬·결과 전달·검토 재작업), 작업 트리, 순환·깊이 제한, 실제 Claude 검증 |
| Phase 6 | 사무실 시각화 | Tested — 상태·활동 구역 이동, 위임 이벤트의 업무 전달 연출(봉투)·기록(E2E) |
| Phase 7 | 프로젝트 관리 | Tested — 탐색·등록·Git 상태 |
| Phase 8 | UX·튜토리얼·로그인·데스크톱 패키징(Tauri) | In Progress — 로컬 계정 로그인 Tested, AI 사용량(Claude·Codex) Tested, 테마 4종·시작 가이드 Tested, 패키징 Planned |

## 실제 Claude Code로 검증한 것(2026-11-25, Claude Code 2.1.326, Raspberry Pi aarch64)

- CEO 대화 응답(스트리밍·저장) 약 5초.
- `require_approval: shell`인 에이전트의 `echo` 실행이 승인 요청을 만들고, 승인 후 실행됨.
  (처음 구현은 `can_use_tool`만 써서 Claude Code가 자동 허용하는 읽기 전용 명령이 승인 없이 실행됐다 → PreToolUse 훅으로 수정.)
- 설계 담당 Claude가 자연어 설명으로 부서 4·에이전트 6 조직을 만들고, 다음 턴에서 맥락을 유지해 수정(턴당 약 1~2분).
  (처음 구현은 구조화 출력의 내부 도구 `StructuredOutput`까지 막아 실패했다 → 그 도구만 허용.)
- 프로젝트를 연결한 대화에서 에이전트가 저장소 파일을 읽고 답함.

## 자기 개발(dogfooding)

이 저장소는 플랫폼 자신으로도 개발한다. 첫 실측: 이슈 #23을 에이전트 조직이 구현 → PR #25 병합(2026-11-25). 방법·결과: [SELF_DEVELOPMENT.md](SELF_DEVELOPMENT.md).

## 다음 작업(우선순위)

1. Phase 5 다음: 비동기 위임, 계획 중 사용자 승인 단계 — [AGENT_ORCHESTRATION.md](AGENT_ORCHESTRATION.md).
4. Alembic 도입(스키마 변경 전).
5. 다중 사용자(AUTH-3) — 조직·대화 소유 범위.

## 보류·알려진 제한

- 셸 명령의 정적 경로는 검사하지만 변수 확장·명령 치환·스크립트 내부 경로는 알 수 없다(SECURITY.md). 셸 허용 시 승인 유지를 권장한다.
- 사무실 캐릭터의 활동 구역은 최근 도구 분류 이벤트를 따르며, 새로고침 직후에는 상태만으로 정한다.
