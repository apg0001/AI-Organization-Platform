# Claude Code 작업 지침 (AI Organization Platform)

- 작업 전 `docs/ROADMAP.md`에서 현재 단계와 상태를 확인한다. Git 규칙은 `docs/GIT_CONVENTION.md`를 따른다.
- `~/Agent-Office`(참고 저장소)는 절대 수정하지 않는다. 가져온 코드는 `THIRD_PARTY_NOTICES.md`와 파일 머리 주석에 출처를 남긴다.
- 실제로 동작하지 않는 기능을 구현했다고 쓰지 않는다. 미구현은 문서·UI에 명시한다.
- 기능·API·DB·보안·환경 변수를 바꾸면 관련 docs를 같은 PR에서 갱신한다.
- 검증: `apps/server`에서 `ruff check`, `ruff format --check`, `mypy`, `pytest` / 루트에서 `npm run typecheck`, `npm test`, `npm run build`.
- 디자인 작업은 `docs/DESIGN_SYSTEM.md` 토큰만 쓴다. 디자인 Skills는 `.claude/skills/`에 있다(impeccable은 런처 없이 마크다운만 설치).
- 이슈·PR·커밋·문서는 한국어로 쓴다.
