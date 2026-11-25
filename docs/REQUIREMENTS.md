# 요구사항

원천: 마스터 프롬프트(프로젝트 시작 지시), UI/UX 지시, Git 규칙 지시, Web Chat 지시, Organization Builder 지시, 문서화 지시(2026-11-25).
상태 표기는 [ROADMAP.md](ROADMAP.md)와 같다.

## 1. 목표

로컬에서 AI 조직을 설계하고 실제 Claude Code 에이전트에게 업무를 위임·관찰·승인하는 제품.

## 2. 기능 요구사항

| ID | 요구사항 | 상태 |
|---|---|---|
| ORG-1 | 여러 회사(조직) 생성·수정·삭제, 이름·설명·목표·기본 지침·정책 | Tested |
| ORG-2 | 에이전트 CRUD(직책·부서·상위·역할·책임·전문·지침·런타임·권한·허용 기능·상태) | Tested |
| ORG-3 | 트리형 보고 관계(순환 금지, CEO 1명) + 별도 협업 관계(전달·검토·자문) | Tested |
| ORG-4 | 조직 템플릿 6종(연구·대학생·개발·마케팅·비즈니스·개인 비서), 데이터 파일·버전 | Tested |
| ORG-5 | 대화형 조직 설계(질문, 구조 생성·수정, 맥락 유지) | Tested(실제 Claude 검증) |
| ORG-6 | 조직도와 대화가 단일 설계 상태 공유 | Tested |
| ORG-7 | AI 추천과 실제 적용 구분(권한 확대 제안 수락, Skills/MCP는 추천만) | Tested |
| ORG-8 | 생성 전 최종 검토, 적용 시 실행 중 작업 경고 | Implemented |
| ORG-9 | 변경 이력과 되돌리기(미리보기 후 적용) | Tested |
| RUN-1 | 사용자 Claude Code로 에이전트별 독립 실행, 작업 폴더 분리 | Tested(실제 Claude 검증) |
| RUN-2 | 스트리밍, 도구 이벤트, 상태, 중지, 세션 이어가기 | Tested |
| RUN-3 | 에이전트 권한 정책과 사용자 승인(우회 금지) | Tested(실제 Claude 검증) |
| RUN-4 | 비정상 종료 복구(진행 중 상태 정리) | Implemented |
| CHAT-1 | CEO·팀·개별 에이전트 대화, 대화 목록·제목 | Tested |
| CHAT-2 | 마크다운·코드 하이라이트·복사, 다시 생성 | Implemented |
| CHAT-3 | 파일 첨부(드래그·선택·붙여넣기, 미리보기, 형식·크기 검증, 진행률) | Tested(백엔드) |
| CHAT-4 | 슬래시 명령(레지스트리, 12종, 인자) | Tested |
| CHAT-5 | @멘션(에이전트 직접 지정), @All | Tested |
| CHAT-6 | 컨텍스트 첨부(프로젝트 경로·에이전트·작업 결과·GitHub·Skill), 범위 검증 | Tested |
| CHAT-7 | 실행 패널(상태·도구·승인·작업), 접기 | Implemented |
| ORCH-1 | CEO가 업무를 분석해 하위 에이전트에게 자동 분배·취합 | Tested(실제 Claude 검증) |
| ORCH-2b | 작업 계획: 선행 작업 순서·병렬·결과 전달·검토 재작업 | Tested(실제 Claude 검증) |
| ORCH-2 | 사용자 지시 위임(`/delegate`) → 작업 기록·실행·결과 | Tested |
| CAP-1 | Skills·MCP·Plugins 탐색(비밀 제외) | Tested |
| CAP-2 | 에이전트별 Skills 허용 → 실행에 반영 | Implemented(SDK `skills` 옵션) |
| CAP-3 | MCP 서버를 에이전트 실행에 연결, 연결 점검 | Tested(실제 Claude·chrome-devtools-mcp 검증) |
| CAP-4 | Plugins 실행 연결 | Tested(단위) — 설치·업데이트 UI는 Planned |
| PRJ-1 | 탐색 경로 등록·탐색·프로젝트 등록·Git 상태 | Tested |
| PRJ-2 | 프로젝트–조직 연결, 대화별 프로젝트 | Implemented |
| UI-1 | 대시보드·조직 설계·커맨드 센터·조직·에이전트 상세·프로젝트·기능 관리·사무실 | Implemented |
| UI-2 | 아이소메트릭 사무실(Agent Office 렌더러 재사용) | Implemented |
| AUTH-1 | 로컬 단일 사용자 보호(루프백·Host·Origin 검사) | Tested |
| AUTH-2 | 로컬 계정·로그인·로그아웃·세션·비밀번호 변경·계정 초기화 | Tested |
| AUTH-3 | 다중 사용자·사용자별 조직 접근·OAuth | Planned(설계: SECURITY.md §7) |
| TUT-1 | 튜토리얼 | Planned(Phase 8) |

## 3. 비기능 요구사항

- 로컬 실행: 백엔드는 루프백에만 바인딩한다. 클라우드 의존 없음.
- 저사양 대응: 라즈베리 파이(8GB)에서 동작. 동시 Claude Code 프로세스 기본 2개.
- 정직성: 수집할 수 없는 진행률을 만들지 않는다. 미구현 기능은 UI와 문서에 명시한다.
- 접근성: 상태는 색+아이콘+글자, 키보드 포커스, 줄인 모션.
- 개인정보: 비밀 값(MCP env·헤더 등)은 응답에 넣지 않는다. 실행 기록에는 도구 이름과 짧은 대상만 저장한다.

## 4. 보안·권한 요구사항

[SECURITY.md](SECURITY.md) 참조. 요약: Host/Origin 검사, 등록 경로 밖 접근 금지, 에이전트별 도구 묶음 허용·승인,
권한 확대는 사용자 확인, Claude Code 권한 우회 금지, 업로드 검증·정리.

## 5. 범위

- **MVP(현재 목표)**: 조직 설계 + 단일 에이전트 실행·채팅·승인 + 프로젝트 + 사무실.
- **다음**: MCP 실행 연결(Phase 4), CEO 자동 분배·에이전트 간 메시지(Phase 5), 로그인(AUTH-2), 데스크톱 패키징(Phase 8).
