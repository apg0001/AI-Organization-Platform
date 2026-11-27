/**
 * 에이전트 설정 화면의 일반 저장(PATCH) 본문 만들기. 사용자가 실제로 바꾼 필드만 담는다.
 * 화면이 들고 있던 값(before)과 편집 결과(next)를 비교하므로, 그 사이 다른 곳(권한 표의 모델 선택 등)에서 바뀐 필드를
 * 화면의 옛 값으로 되돌리지 않는다. 권한은 여기서 다루지 않는다(usePermissionChange가 따로 저장한다).
 */

import type { SpecAgent } from "./api";

/** 편집기의 필드 이름 → PATCH 본문의 필드 이름. */
const FIELDS = {
  name: "name",
  title: "title",
  role: "role",
  responsibilities: "responsibilities",
  expertise: "expertise",
  instructions: "instructions",
  department: "department_id",
  reports_to: "reports_to_id",
  enabled: "enabled",
  model: "model",
  allowed_skills: "allowed_skills",
  allowed_mcp_servers: "allowed_mcp_servers",
  allowed_plugins: "allowed_plugins",
} as const satisfies Partial<Record<keyof SpecAgent, string>>;

export type AgentPatchBody = Partial<Record<(typeof FIELDS)[keyof typeof FIELDS], unknown>>;

/** 바뀐 필드만 담은 본문. 바뀐 것이 없으면 빈 객체(요청을 보내지 않는다). */
export function changedAgentFields(before: SpecAgent, next: SpecAgent): AgentPatchBody {
  const body: AgentPatchBody = {};
  for (const key of Object.keys(FIELDS) as (keyof typeof FIELDS)[]) {
    if (JSON.stringify(before[key]) !== JSON.stringify(next[key])) body[FIELDS[key]] = next[key];
  }
  return body;
}
