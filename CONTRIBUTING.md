# 기여 안내

## 개발 환경

- Python 3.12+, Node.js 24+/npm 11+, Claude Code CLI(로그인).
- `npm install` → `cd apps/server && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
- 실행: `./scripts/dev.sh`(웹 :3000, API :8000). 환경 변수: `.env.example`.
- Claude Code에서 작업할 때는 `CLAUDE.md`를 따른다.

## 작업 흐름

1. 기존 이슈를 고르거나 한국어로 새 이슈를 만든다(`[type] 제목`).
2. `develop`에서 `type/#번호-영문-설명` 브랜치를 만든다(`docs/GIT_CONVENTION.md`).
3. 작은 커밋으로 구현·테스트·문서를 함께 바꾼다. 커밋: `[type] 한국어 요약 (#번호)`.
4. `develop` 대상 PR을 만들고 템플릿을 실제 결과로 채운다. `CI Gate` 통과 후 merge commit으로 병합한다.

`main`·`develop`에 직접 push하지 않는다. `develop → main` 릴리스는 소유자 승인 후에만.

## 코드 리뷰 규칙

- 정확성 > 보안·권한 > 문서 일치 > 단순성 순으로 본다.
- 권한·파일 접근·실행 경로 변경은 거부·우회 시나리오 테스트가 있어야 한다.
- 동작하지 않는 기능을 동작한다고 쓰지 않았는지(UI 문구·문서) 확인한다.

## 테스트 규칙

- 백엔드: `ruff check`, `ruff format --check`, `mypy`(strict), `pytest`. 웹: `npm run typecheck`, `npm test`, `npm run build`.
- 화면·흐름을 바꾸면 `npm run e2e`(Playwright)를 돌리고 필요하면 `apps/web/e2e`에 단계를 추가한다.
- 새 기능·버그 수정에는 테스트를 추가한다. Claude 사용량을 쓰는 실제 실행 검증은 수동으로 하고 PR에 결과를 적는다.
- 실행하지 않은 검사는 '미실행 검증'에 이유와 함께 적는다.

## 문서 규칙

기능·API·DB·아키텍처·보안 정책·설치 방법·환경 변수가 바뀌면 같은 PR에서 관련 문서(README, docs/*, CHANGELOG)를 갱신한다.
기술 선택을 바꿀 때는 기존 ADR을 고치지 않고 새 ADR을 추가한다(`docs/decisions/`).

## 플랫폼으로 개발하기

이 저장소의 이슈는 플랫폼의 에이전트 조직에게 맡길 수 있다. 실행용 체크아웃과 개발용 worktree를 분리하고, 결과는 사람이 검토해 PR로 올린다.
커밋 본문에 에이전트가 구현했음을 적는다. 방법: [docs/SELF_DEVELOPMENT.md](docs/SELF_DEVELOPMENT.md).

## 화면 검증(Chrome DevTools MCP)

저장소의 `.mcp.json`에 `chrome-devtools`(chrome-devtools-mcp, 헤드리스·임시 프로필·사용 통계와 CrUX 전송 끔)가 있다.
이 폴더에서 `claude`를 처음 실행할 때 프로젝트 MCP 서버를 승인하면 Claude Code가 브라우저로 `http://127.0.0.1:3000`을 열어
화면·콘솔·네트워크를 확인할 수 있다. UI 변경 PR에는 확인한 화면을 적는다.

## 디자인 규칙

`docs/DESIGN_SYSTEM.md` 토큰과 `docs/COMPONENT_GUIDELINES.md`의 공통 컴포넌트를 쓴다. 새 색·컴포넌트는 문서에 먼저 추가한다.
