# 템플릿 시스템

## 기본 템플릿

| template_id | 이름 | 대상 | 규모 |
|---|---|---|---|
| research | 연구 조직 | 대학원생·연구원·연구실 | 연구 책임자 + 6명, 부서 3 |
| university | 대학생 조직 | 대학생·취업 준비생 | 개인 매니저 + 6명, 부서 3 |
| software | 소프트웨어 개발 조직 | 개인 개발자·개발팀·스타트업 | 프로젝트 매니저 + 7명, 부서 4 |
| marketing | 마케팅 조직 | 마케터·크리에이터·소규모 사업자 | 마케팅 디렉터 + 6명, 부서 3 |
| business | 비즈니스 조직 | 스타트업·1인 기업·소규모 기업 | CEO + 6명, 부서 4 |
| personal | 개인 비서 조직 | 일반 사용자·직장인 | 비서실장 + 5명 |

## 데이터 구조

파일: `apps/server/src/ai_org/templates/<template_id>.json`. 스키마: `spec.TemplateFile`(로드 시 검증).

```json
{ "template_id": "research", "version": "1.0.0", "name": "...", "description": "...", "category": "연구",
  "target_users": ["..."], "org_size": "...", "spec": { /* OrgSpec */ } }
```

요구된 항목과의 대응: departments·agents·agent_roles·agent_instructions → `spec.departments/agents`,
organization_structure → `reports_to`, collaboration_rules → `spec.collaborations`, default_permissions → 에이전트 `permissions`
(생략 시 기본값: 셸 금지, 셸·파일 수정·삭제 승인 필요), recommended_skills/mcp → 조직·에이전트 수준, workflows → `spec.workflows`.

## 원칙

- 모든 템플릿이 같은 OrgSpec을 쓴다. 템플릿별 코드 분기는 없다.
- 템플릿은 출발점이다. 설계 초안으로 복사된 뒤에는 템플릿과 독립이다 — 템플릿을 고쳐도 기존 조직은 바뀌지 않는다
  (초안의 `origin`에 `template:<id>@<version>`만 남는다).
- 권한 기본값은 보수적으로 둔다. 템플릿이 넓은 권한을 담아도 사용자가 검토 화면에서 확인한 뒤에만 적용된다.

## 추가·수정

1. JSON 파일을 추가하거나 고치고 `version`을 올린다(SemVer: 구조 변경 major, 에이전트 추가 minor, 문구 patch).
2. `pytest`(템플릿 로드 검증)를 돌린다.

## 향후(Planned)

사용자 정의 템플릿 저장(현재 조직 → 템플릿), 복제·편집, 내보내기/가져오기(JSON), 버전 이력, 커뮤니티 공유.
외부 템플릿 가져오기는 권한·실행 설정을 검토 화면에서 확인한 뒤에만 적용한다(AI 제안과 같은 `sanitize` 경로).
