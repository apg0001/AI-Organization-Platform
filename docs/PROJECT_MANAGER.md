# Project Manager(프로젝트 관리)

구현: `services/projects.py`, `api/projects.py`, 웹 `features/projects/`.

## 동작

1. **탐색 경로 등록**: 절대 경로만, 실제 경로로 해석(`resolve`), 파일 시스템 루트(`/`) 금지, 깊이 0~4.
2. **탐색**: 경로 아래에서 `.git` 또는 표식 파일(package.json, pyproject.toml, requirements.txt, go.mod, Cargo.toml, pom.xml,
   build.gradle, Gemfile, CMakeLists.txt)이 있는 폴더를 찾는다. 찾은 프로젝트 안으로는 더 내려가지 않는다. 숨김 폴더·
   node_modules·.venv·dist 등과 심볼릭 링크는 건너뛴다. 유형은 표식으로 추정(node·python·go·rust·java·ruby·cpp·mixed).
3. **등록**: 등록된 탐색 경로 **안의 실제 경로**만 등록할 수 있다(심볼릭 링크로 밖을 가리키면 403).
4. **Git 정보**(읽기 전용): 브랜치, HEAD·제목, 변경 파일 수, 원격 대비 앞섬·뒤처짐, origin URL(자격증명 제거).
   `git`을 셸 없이 인자 배열로, 5초 제한, `GIT_OPTIONAL_LOCKS=0`으로 호출한다. 저장소를 바꾸는 명령은 쓰지 않는다.
5. **조직 연결**: 프로젝트마다 조직 하나(선택). 대화마다 프로젝트를 고르면 에이전트의 작업 폴더가 된다.
6. **등록 해제**: 레지스트리에서만 지운다. 파일은 건드리지 않는다.

## 파일 접근 원칙

- 브라우저는 경로 문자열만 보내고, 파일 시스템 접근은 로컬 백엔드만 한다.
- 에이전트 도구의 경로는 작업 폴더·첨부 폴더 안만 허용된다(정책). 프로젝트 트리 API는 프로젝트 밖으로 나갈 수 없다.
- 전체 디스크 탐색은 제공하지 않는다(요구사항의 '별도 옵션'은 Planned, 명시적 확인 UI와 함께).

## Planned

최근 작업·세션 목록을 프로젝트별로 집계, 작업 결과물(변경 파일) 보기, worktree 격리 실행 검토.
