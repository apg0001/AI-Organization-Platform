# Git 규칙

이 규칙은 소유자(apg0001)가 실제로 운영 중인 저장소를 `gh`로 조사해 정했다(2026-11-25, 읽기 전용 조사).
조사 대상: Agent-Office(커밋 약 410·PR 159), lab-wars(약 366·208), instagram-auto-uploader(약 145·94), hwp_for_mac, mecalib,
AI_PROJECT_PBL2_WEBRTC, AI_Agent_Usage_Widget_for_MAC. 우선순위: 최근 활발한 저장소 → 반복 사용 규칙 → 여러 저장소 공통 규칙.

## 조사 결과 요약

| 항목 | 실제 사용 패턴 | 일관성 |
|---|---|---|
| 브랜치 | `main`(릴리스) + `develop`(통합), 작업은 `type/#이슈-영문-설명` | 모든 활성 저장소. hwp_for_mac은 CI 정규식으로 강제 |
| 커밋 | `[type] 한국어 요약 (#이슈)`, 본문은 필요할 때(목록 또는 원인·수정 문단, `검증:` 줄), `Co-Authored-By: Claude …` 트레일러 | Agent-Office·lab-wars·instagram·mecalib·PBL2 거의 100% |
| PR | 제목 = 커밋 제목, 본문 `Closes #N` + 템플릿, `develop` 대상, 끝에 Claude Code 문구 | 동일 |
| 병합 | **merge commit만**(squash·rebase 미사용), 브랜치는 삭제하지 않음 | 모든 저장소 |
| 릴리스 | `develop → main` PR `[release] x.y.z`(소유자 승인 후), 이후 `main → develop` 역병합 `chore/#N-backmerge-x.y.z` | Agent-Office·lab-wars·instagram |
| 이슈 | 제목 `[type] 한국어 제목`(번호 없음), 한국어 본문, 라벨은 드물게 | 동일. 마일스톤 미사용 |
| 보호 | main·develop: PR 필수(관리자 포함), `CI Gate` 필수(strict), 승인 0명, 대화 해결 필수, force-push·삭제 금지 | Agent-Office·lab-wars |
| 언어 | 이슈·PR·커밋·문서 한국어, 브랜치 설명·타입·코드는 영어 | 전부 |

차이: 역병합 표기(Agent-Office `역병합`, 나머지 `백머지`) → 이 저장소는 **역병합**. 릴리스 준비 타입(Agent-Office `docs`, lab-wars `chore`) → **docs**.

## 1. 브랜치 전략

- `main`: 릴리스만. `develop`: 통합 브랜치(기본 개발 대상). 둘 다 직접 push 금지.
- 작업 브랜치: `develop` 최신에서 만든다. **한 브랜치 = 한 이슈**.

## 2. 브랜치 이름

`<type>/#<이슈번호>-<영문-kebab-설명>` — 정규식 `^(feat|fix|docs|chore|test|refactor|perf|ci)/#[0-9]+-[a-z0-9-]+$`

예: `feat/#12-mcp-runtime`, `fix/#15-approval-timeout`, `docs/#3-project-docs`, `chore/#20-backmerge-0.1.0`

## 3. 커밋 메시지

```
[type] 한국어 요약 (#이슈)

- 무엇을 바꿨는지(필요할 때)
- 왜 바꿨는지

검증: 실행한 검사와 결과

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

type: feat · fix · docs · refactor · test · chore · ci · style · perf. 한 커밋에는 논리적으로 연관된 변경만.
AI가 작성에 참여한 커밋에는 `Co-Authored-By` 트레일러를 단다(기존 저장소 관행).

## 4. Pull Request

- 대상: `develop`(릴리스·역병합 제외). 제목: `[type] 한국어 요약 (#이슈)`.
- 본문: `.github/pull_request_template.md`를 지우지 않고 실제 결과로 채운다. 해당 없는 항목은 `해당 없음`.
- 승인 수 0(단일 관리자)이지만 템플릿의 검증 근거와 자체 리뷰는 필수. `CI Gate` 통과와 리뷰 대화 해결 후 병합.
- 문서 갱신 여부를 리뷰 체크리스트로 확인한다.

## 5. 이슈

제목 `[type] 한국어 제목`. 템플릿: 기능(`feature.yml`), 버그(`bug.yml`), 문서(`documentation.yml`). 빈 이슈는 막고 보안 제보는
Security Advisory로 안내한다. 라벨은 필요할 때만(`bug`, `enhancement`, `documentation`, `backend`, `frontend`, `runtime`, `security`, `priority:P0~P2`).

## 6. 병합

GitHub의 **Create a merge commit**만 쓴다. 병합 후 브랜치는 지우지 않는다(기존 관행). force-push 금지.

## 7. 작업 시작·종료 절차

1. 이슈를 만들고 실제 번호를 확인한다.
2. `git switch develop && git pull` → `git switch -c feat/#N-slug`
3. 구현 + 테스트 + 관련 문서를 함께 바꾼다. 작은 커밋.
4. 로컬 검사(TESTING.md) → `git push -u origin feat/#N-slug` → `gh pr create --base develop`.
5. CI Gate 통과·자체 리뷰 → merge commit으로 병합 → 이슈는 `Closes #N`로 닫힘.
6. 릴리스: 준비 PR(`docs/#N-release-x.y.z`: CHANGELOG·버전) → 소유자 승인 후 `[release] x.y.z`(develop→main) → 역병합.

## 8. 명령 예시

```bash
gh issue create --title "[feat] MCP 서버를 에이전트 실행에 연결" --body-file issue.md
git switch develop && git pull
git switch -c feat/#12-mcp-runtime
git commit -m "[feat] 허용된 MCP 서버를 실행 옵션으로 전달 (#12)"
git push -u origin feat/#12-mcp-runtime
gh pr create --base develop --title "[feat] 허용된 MCP 서버를 실행 옵션으로 전달 (#12)" --body-file pr.md
gh pr merge 13 --merge
```
