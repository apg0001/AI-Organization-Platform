# 이 플랫폼으로 이 저장소 개발하기(자기 개발)

AI Organization Platform의 에이전트 조직에게 이 저장소의 이슈를 맡겨 개발·고도화하는 방법이다.
사람은 이슈를 정하고, 위험한 작업을 승인하고, 결과를 검토해 PR로 올린다.

## 1. 구성: 실행용과 개발용을 분리한다

```
~/AI_Organization_Platform            실행용(플랫폼이 도는 체크아웃 — develop 또는 릴리스)
~/AI_Organization_Platform-dogfood    개발용 git worktree(에이전트가 고치는 곳, 이슈 브랜치)
```

플랫폼이 자기 실행 코드를 직접 고치면 서버 재시작·의존성 변경으로 실행 중인 에이전트가 끊긴다. 에이전트는 **worktree만** 고치게 한다.

```bash
cd ~/AI_Organization_Platform
gh issue create --title "[feat] …"                      # 이슈 번호 N
git worktree add ../AI_Organization_Platform-dogfood -b feat/#N-slug develop
cd ../AI_Organization_Platform-dogfood/apps/server && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd .. && npm install                                    # 웹 작업이면
```

## 2. 플랫폼 준비

1. 프로젝트 → 탐색 경로에 worktree 경로(깊이 0) 추가 → 등록.
2. 조직 설계 → '소프트웨어 개발 조직' 템플릿(또는 기존 개발 조직).
3. 권한(에이전트 설정)
   - 백엔드·프론트엔드 개발자, QA: 셸 허용(테스트 실행), **셸·파일 수정은 승인 유지**(기본값).
   - CEO·설계자: 위임 허용(기본값).
   - QA에게 `chrome-devtools`(저장소 `.mcp.json`) MCP를 허용하면 브라우저로 화면을 확인할 수 있다.
4. 커맨드 센터 → 새 대화(CEO) → 프로젝트로 worktree 선택.

## 3. 업무 지시 예

> 이슈 #N을 처리해 줘: (요구사항). 백엔드 개발자에게 구현과 테스트 추가를 위임하고, 끝나면 QA 엔지니어에게
> `cd apps/server && .venv/bin/pytest -o addopts= -q`로 검증을 위임해. git commit·push는 하지 마. 최종 보고에 바꾼 파일, 테스트 결과, 남은 위험을 적어.

승인 요청이 오면 명령·경로를 보고 허용한다. 작업 폴더 밖 경로·삭제·`git push`는 거부한다.

## 4. 결과를 PR로

```bash
cd ~/AI_Organization_Platform-dogfood
git diff                                   # 사람이 검토
apps/server/.venv/bin/ruff check … && apps/server/.venv/bin/mypy && apps/server/.venv/bin/pytest
git commit -m "[feat] … (#N)"              # 규칙: docs/GIT_CONVENTION.md
git push -u origin feat/#N-slug && gh pr create --base develop
```

CI Gate·브랜치 보호가 마지막 안전장치다(에이전트는 main·develop에 직접 올릴 수 없다).

## 5. 실측

첫 실측(2026-11-25, Raspberry Pi, Claude Code 2.1.326) — 이슈 #23 "`/status`에 실행 중인 에이전트 표시"를 플랫폼 에이전트 조직이 처리했다.

| 항목 | 결과 |
|---|---|
| 흐름 | CEO(프로젝트 매니저)가 코드를 읽고 → 백엔드 개발자에게 구현·테스트 추가 위임 → QA 엔지니어에게 전체 테스트 검증 위임 → 두 보고를 취합해 바꾼 파일·테스트 결과·남은 위험 보고 |
| 소요·비용 | 3분 47초, SDK 추정 비용 합계 약 $1.04(CEO 0.26, 백엔드 0.69, QA 0.09) |
| 변경 | `services/commands.py` 6줄, 테스트 1개, `docs/CHAT_SYSTEM.md` 1줄 |
| 에이전트 검증 | 백엔드: ruff·format·mypy·관련 테스트 / QA: 전체 55 passed, 새 테스트 3회 반복 통과 |
| 승인 | 17건(셸 11·파일 수정 3 등). 실험 스크립트가 규칙(범위 밖·커밋·푸시·삭제·외부 다운로드 거부)으로 대신 결정 — 허용 10, 거부 7 |
| 사람 | diff 검토, 검사 재실행(pytest 3회 연속 55 passed), 규칙대로 PR #25 → CI Gate(E2E 포함) 통과 → 병합 |

**알게 된 것과 고친 것**

- 거부 7건은 모두 셸 경로 검사의 **오탐**이었다(검색어 `/status`를 경로로 판정, `cd` 뒤 상대 경로를 루트 기준으로 계산).
  에이전트는 막히면 다른 방법(직접 파일 읽기)으로 우회해 일을 끝냈다. 이 오탐은 #26에서 고쳤다.
- CEO 보고가 스스로 남은 위험(새 테스트의 타이밍 의존, 웹 검증 미실행)을 짚었다 — 사람 검토의 출발점으로 유용했다.
- 에이전트는 지시대로 커밋·푸시를 하지 않았고, 변경은 worktree에만 있었다.

## 6. 안전 수칙

- 실행용 체크아웃을 에이전트 프로젝트로 등록하지 않는다.
- `git commit/push`, 원격 작업, 삭제는 에이전트에게 맡기지 않는다(사람이 검토 후).
- 셸 허용 에이전트는 셸 승인을 끄지 않는다.
- 동시 실행 수는 컴퓨터 자원에 맞춘다(라즈베리 파이 2).
- 큰 작업은 이슈를 작게 나눈다(한 대화 = 한 이슈).
