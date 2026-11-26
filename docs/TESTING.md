# 테스트

## 실행

```bash
cd apps/server
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests
.venv/bin/mypy            # strict
.venv/bin/pytest          # 백엔드 단위·API 테스트
cd ../..
npm run typecheck && npm test && npm run build   # 웹
```

CI(`.github/workflows/ci.yml`)가 같은 검사와 브라우저 E2E를 돌리고 `CI Gate` 하나로 집계한다.

## 백엔드 테스트 구성(`apps/server/tests`)

| 파일 | 범위 |
|---|---|
| test_organizations.py | 조직·에이전트 CRUD, 템플릿, 순환 금지, CEO 1명, 조직 간 참조 금지, 협업, 권한 모드 제한 |
| test_security_system.py | Host·Origin·폼 거부, 런타임 감지, Capability 비밀 비노출, 프로젝트 경로 제한(심볼릭 링크), UTC 시각 |
| test_chat.py | 가짜 런타임으로: 라우팅(CEO·팀·멘션·@All), 스트리밍 이벤트, resume, 승인 허용·거부, 정책 거부, 범위 밖 경로, 중지, 명령 12종, 첨부 검증·전달·삭제, 컨텍스트 검증 |
| test_policy.py | 기본 권한, 읽기 전용 명령도 승인, 삭제 탐지, 위임·MCP, 활동 분류 |
| test_auth.py | 계정 생성·로그인·로그아웃, 비밀번호·토큰 해시 저장, WebSocket 보호, 시도 제한, 비밀번호 변경 시 다른 세션 종료, 끈 모드 |
| test_delegation.py | 위임·보고, 조직도 밖 거부, 권한 없으면 도구 없음, 협업 순환 거부, 위임 승인, 동시 실행 한도 1 교착 없음 |
| test_mcp_runtime.py | 허용된 MCP·Plugin만 실행에 전달, 비밀 비노출, MCP 승인 묶음, `claude mcp list` 파싱 |
| test_allow_rules.py | 허용 규칙 저장 거부·정리, 매칭(단어 경계·복합 명령·위험 판정), 파일 글롭, 작업 폴더 밖·꺼 둔 도구 우선, auto 모드와 되묻기, '항상 허용' 규칙 생성·API, 설계 AI 제안의 모드·규칙 확대 격리 |
| test_designs.py | 템플릿 미리보기 후 적용, 설계 대화의 단일 명세 갱신·권한 제안 격리·resume, 잘못된 AI 명세 거부, 직접 편집 검증, 이력·복원, 설계자 도구 허용 범위 |

가짜 런타임(`tests/test_chat.py::FakeRuntime`)은 실제 런타임처럼 도구 단계에서 권한 콜백을 부른다.

## 실제 Claude Code 스모크 테스트(수동)

자동 테스트는 Claude 사용량을 쓰지 않는다. 런타임을 바꾸면 임시 데이터 폴더로 서버를 띄우고 확인한다:

```bash
AI_ORG_AUTH=off AI_ORG_HOME=$(mktemp -d) apps/server/.venv/bin/uvicorn ai_org.main:app --port 8011
# 1) 조직 생성 → 대화 → 짧은 메시지: 응답 done
# 2) CEO에 allow_shell + require_approval:[shell] → "echo 실행" → 승인 요청 발생 → 허용 → 출력
# 3) 설계 초안 → 설계 메시지 2턴 → spec 변경·맥락 유지
```

결과는 ROADMAP.md의 '실제 Claude Code로 검증한 것'에 날짜·버전과 함께 기록한다.

## 웹

- `npm test`(Vitest, node 환경): 순수 로직 — 조직 → 사무실 상태 어댑터, 명령 인자 해석, 스프라이트.

## 브라우저 E2E(Playwright)

```bash
npm run e2e        # 루트에서. apps/server/.venv가 있어야 한다
```

- `apps/web/playwright.config.ts`가 임시 데이터 폴더와 **테스트용 가짜 런타임**(`AI_ORG_RUNTIME=fake`, `runtime/fake.py`)으로
  백엔드(127.0.0.1:8100)와 웹(127.0.0.1:3100)을 띄운다. Claude 사용량을 쓰지 않는다. 브라우저는 시스템 Chrome(`channel: "chrome"`).
- 가짜 런타임은 실제 런타임과 같은 계약을 따르며 프롬프트 표식으로 동작한다: 기본(마크다운 스트리밍), `[승인]`(파일 쓰기 승인 요청),
  `[위임:이름]`(delegate_task), `[셸:명령]`(그 Bash 명령을 정책에 물음 — 실제로 실행하지는 않음),
  `[되묻기:명령]`(같은 요청 뒤 auto 모드에서 Claude Code가 되묻는 경우를 흉내), 설계 담당자(명세에 'E2E팀'·'E2E 분석가' 추가 + 권한 확대 제안).
- 권한 E2E 3건(같은 `flows.spec.ts`, 2026-11-26 추가): 권한 표에서 셸 금지 저장 → 조직도 배지 반영·권한 확대 확인 창 / 프리셋 '안전' 적용 뒤
  에이전트 편집 창 값 일치 / 승인 배너 '항상 허용' 뒤 같은 요청은 배너 없이 진행. 아래 '결과' 줄은 이 3건을 넣기 전의 기록이다. 3건을 넣고 develop을 병합한 뒤(2026-11-26) E2E 10개 통과(로컬 QA·CI).
- `e2e/flows.spec.ts`(순서대로 이어지는 사용자 여정 6단계): 첫 계정 생성(비밀번호 확인 오류 포함) → 템플릿 미리보기·설계·검토·조직 생성 →
  설계 담당자 대화로 명세 갱신·권한 제안 수락·적용·변경 이력 → 커맨드 센터 스트리밍·코드 블록·`/agents`·`@` 자동완성·승인 배너·위임 표시와
  작업 트리 → 프로젝트 탐색 경로·등록·기능 관리 연결 점검 버튼·사무실 캔버스 → 로그아웃·틀린 비밀번호·재로그인. 마지막에 브라우저 콘솔 오류가 없는지 확인한다.
- 실패 시 `apps/web/test-results/`에 스크린샷·trace가 남는다(CI는 아티팩트로 올림).
- 결과(2026-11-25): Raspberry Pi(Chrome 156)에서 6개 통과(약 1분).

## 규칙

- 실행하지 않은 테스트를 통과했다고 쓰지 않는다. PR 템플릿의 '실제 실행한 검증'·'미실행 검증'을 구분해 채운다.
- 버그를 고치면 재현 테스트를 먼저 추가한다.
