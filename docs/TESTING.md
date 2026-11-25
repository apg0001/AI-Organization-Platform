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

CI(`.github/workflows/ci.yml`)가 같은 검사를 돌리고 `CI Gate` 하나로 집계한다.

## 백엔드 테스트 구성(`apps/server/tests`)

| 파일 | 범위 |
|---|---|
| test_organizations.py | 조직·에이전트 CRUD, 템플릿, 순환 금지, CEO 1명, 조직 간 참조 금지, 협업, 권한 모드 제한 |
| test_security_system.py | Host·Origin·폼 거부, 런타임 감지, Capability 비밀 비노출, 프로젝트 경로 제한(심볼릭 링크), UTC 시각 |
| test_chat.py | 가짜 런타임으로: 라우팅(CEO·팀·멘션·@All), 스트리밍 이벤트, resume, 승인 허용·거부, 정책 거부, 범위 밖 경로, 중지, 명령 12종, 첨부 검증·전달·삭제, 컨텍스트 검증 |
| test_policy.py | 기본 권한, 읽기 전용 명령도 승인, 삭제 탐지, 위임·MCP, 활동 분류 |
| test_designs.py | 템플릿 미리보기 후 적용, 설계 대화의 단일 명세 갱신·권한 제안 격리·resume, 잘못된 AI 명세 거부, 직접 편집 검증, 이력·복원, 설계자 도구 허용 범위 |

가짜 런타임(`tests/test_chat.py::FakeRuntime`)은 실제 런타임처럼 도구 단계에서 권한 콜백을 부른다.

## 실제 Claude Code 스모크 테스트(수동)

자동 테스트는 Claude 사용량을 쓰지 않는다. 런타임을 바꾸면 임시 데이터 폴더로 서버를 띄우고 확인한다:

```bash
AI_ORG_HOME=$(mktemp -d) apps/server/.venv/bin/uvicorn ai_org.main:app --port 8011
# 1) 조직 생성 → 대화 → 짧은 메시지: 응답 done
# 2) CEO에 allow_shell + require_approval:[shell] → "echo 실행" → 승인 요청 발생 → 허용 → 출력
# 3) 설계 초안 → 설계 메시지 2턴 → spec 변경·맥락 유지
```

결과는 ROADMAP.md의 '실제 Claude Code로 검증한 것'에 날짜·버전과 함께 기록한다.

## 웹

- `npm test`(Vitest, node 환경): 순수 로직 — 조직 → 사무실 상태 어댑터, 명령 인자 해석.
- UI 검증은 헤드리스 Chrome 스크린샷으로 각 화면을 확인했다(2026-11-25). 컴포넌트·E2E 테스트(Playwright)는 Planned.

## 규칙

- 실행하지 않은 테스트를 통과했다고 쓰지 않는다. PR 템플릿의 '실제 실행한 검증'·'미실행 검증'을 구분해 채운다.
- 버그를 고치면 재현 테스트를 먼저 추가한다.
