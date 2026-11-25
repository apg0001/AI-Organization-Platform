# Organization Builder(조직 설계)

구현: `spec.py`(OrgSpec), `services/design.py`, `api/designs.py`, 웹 `features/builder/*`, `components/org/OrgChart.tsx`,
`components/agent/AgentEditor.tsx`.

## 1. 생성 방식

| 진입점 | 동작 |
|---|---|
| 추천 템플릿 | 템플릿 미리보기(조직도·에이전트·업무 흐름·추천 도구) → `POST /designs {template_id}` → 작업 공간에서 수정 |
| AI와 함께 만들기 | 빈 설계(CEO 1명) → 설계 담당 Claude와 대화 |
| 직접 만들기 | 빈 설계 → 조직도에서 부서·에이전트 추가 |
| 기존 조직 수정 | 조직 화면 `조직 수정` → 현재 조직을 명세로 바꾼 초안 |
| 되돌리기 | 이력 → 그 구성의 초안 → 검토 후 적용 |

## 2. 단일 설계 상태

`OrgDesign.spec`(OrgSpec JSON) 하나를 대화·조직도·설정 패널·검토 화면이 함께 쓴다.

- 조직도·패널 편집 → `PUT /designs/{id}/spec`(서버 검증: key 중복, 존재하지 않는 부서·상위, 순환, CEO 정확히 1명, 협업 대상).
  변경이 있으면 설계 대화 기록에 `edit` 항목으로 남는다.
- 대화 → 설계 담당 Claude가 `<current_spec>`(현재 명세)을 받아 전체 수정본을 구조화 출력으로 돌려준다 → 검증 → 정리 → 같은 spec을 교체.
- 따라서 사용자가 조직도에서 바꾼 내용은 다음 대화 턴에 그대로 반영되고, 대화로 바꾼 내용은 즉시 조직도에 보인다.

## 3. OrgSpec 구조

```
OrgSpec { name, description, mission, base_instructions, policy,
          departments[ {key, name, description, color} ],
          agents[ {key, name, title, department, role, responsibilities[], expertise[], instructions,
                   reports_to, is_lead, enabled, permissions, permission_suggestion,
                   recommended_skills[], recommended_mcp[], allowed_skills[], allowed_mcp_servers[], model} ],
          collaborations[ {source, target, kind: handoff|review|consult, label} ],
          workflows[ {name, steps[]} ], recommended_skills[], recommended_mcp[] }
```

key는 명세 안의 식별자다. 기존 조직에서 만든 명세는 실제 ID를 key로 써서, 적용 시 key가 같으면 갱신·다르면 생성·없으면 삭제한다.

## 4. 대화형 설계(설계 담당 Claude)

- 조직 구성원이 아닌 별도 역할이다. 도구 없이(`tools=[]`, `StructuredOutput`만 허용) 사용자 설정도 읽지 않는다(`setting_sources=[]`).
- 출력 스키마: `{reply, questions[], spec | null}`. 질문만 할 때는 `spec=null`.
- 지침(`DESIGNER_SYSTEM`): 정보가 부족하면 중요한 질문 1~2개만, 확인된 것은 다시 묻지 않기, 위험 권한은 켜지 않기, 기존 key 유지,
  존재하지 않는 도구를 지어내지 않기, 에이전트 지침에 작업 방식·결과물 형식 적기.
- 같은 설계의 다음 턴은 `designer_session_id`로 resume해 맥락을 유지한다.
- 서버 검증에 실패한 제안은 반영하지 않고 오류를 대화에 남긴다.

## 5. AI 추천과 실제 적용의 구분

`sanitize_proposal`이 AI 제안에서 다음을 막는다.
- **권한 확대**(셸·삭제·쓰기·네트워크·위임 켜기, 승인 항목 제거, acceptEdits, 파일 범위 확대)는 `permissions`에 넣지 않고
  `permission_suggestion`으로 옮긴다. 사용자가 에이전트 설정에서 `제안 수락`을 눌러야 적용된다.
- **실제 허용 목록**(`allowed_skills`, `allowed_mcp_servers`)은 AI가 바꿀 수 없다. AI는 `recommended_*`만 쓴다.

추천 도구의 상태(이 컴퓨터 기준): `available`(설치·허용됨) · `approval_required`(설치됨, 허용 전) · `install_required`(없음) ·
`unsupported`(설치됐지만 실행 연결 미구현 — 현재 MCP 전부).

## 6. 검토와 적용

`검토 후 조직 생성/적용` 대화상자: 이름·목적 수정, 에이전트별 부서·허용 권한·승인 항목, 미수락 권한 제안, 추천 도구 상태 집계.
`POST /designs/{id}/apply`
- 기존 조직에 실행 중인 에이전트가 있으면 409와 경고 → 사용자가 확인하면 `confirm_running=true`로 다시 적용.
- 적용 결과는 `OrgRevision`(적용 후 명세 스냅샷 + 변경 요약 + 출처)으로 남는다.
- 적용된 초안은 읽기 전용이 된다.

## 7. 변경 이력과 복원

`GET /organizations/{id}/revisions` → 각 적용의 요약. `restore`는 그 명세로 초안을 만들 뿐 바로 바꾸지 않는다.
삭제 후 복원되는 에이전트는 새 ID를 받으므로 이전 대화·세션은 이어지지 않는다.

## 8. 에이전트 설정 항목

이름·직책·부서·상위 관리자·역할·책임·전문 분야·시스템 지시사항·활성화, 권한(셸·파일 수정·삭제·네트워크·위임, 승인 필요 작업,
권한 모드), 허용 Skills·MCP. 파일 접근 범위(`file_scope`)는 데이터 모델에 있으나 편집 UI는 아직 없다(Planned).
