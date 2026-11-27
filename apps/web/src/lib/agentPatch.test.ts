import { describe, expect, it } from "vitest";

import { changedAgentFields } from "./agentPatch";
import type { SpecAgent } from "./api";

const base: SpecAgent = {
  key: "a1",
  name: "QA 엔지니어",
  title: "QA",
  department: "d1",
  role: "검증",
  responsibilities: ["테스트"],
  expertise: [],
  instructions: "",
  reports_to: "lead",
  is_lead: false,
  enabled: true,
  permissions: {
    permission_mode: "default",
    file_scope: [],
    allow_shell: false,
    allow_network: true,
    allow_file_write: true,
    allow_file_delete: false,
    require_approval: ["shell"],
    can_delegate: false,
    allow_rules: [],
  },
  permission_suggestion: null,
  recommended_skills: [],
  recommended_mcp: [],
  allowed_skills: [],
  allowed_mcp_servers: [],
  allowed_plugins: [],
  model: null,
};

describe("에이전트 일반 저장 본문: 바뀐 필드만", () => {
  it("바뀐 것이 없으면 빈 객체", () => {
    expect(changedAgentFields(base, { ...base })).toEqual({});
    expect(changedAgentFields(base, { ...base, responsibilities: ["테스트"] })).toEqual({});
  });

  it("다른 필드만 바꾸면 model은 담지 않는다(다른 곳에서 바꾼 모델을 되돌리지 않게)", () => {
    const body = changedAgentFields(base, { ...base, role: "회귀 검증" });
    expect(body).toEqual({ role: "회귀 검증" });
    expect("model" in body).toBe(false);
    // 화면이 옛 모델을 들고 있어도 마찬가지다.
    const stale = { ...base, model: "opus" };
    expect(changedAgentFields(stale, { ...stale, name: "QA" })).toEqual({ name: "QA" });
  });

  it("model: null ↔ 값", () => {
    expect(changedAgentFields(base, { ...base, model: "sonnet" })).toEqual({ model: "sonnet" });
    expect(changedAgentFields({ ...base, model: "sonnet" }, base)).toEqual({ model: null });
    expect(changedAgentFields({ ...base, model: "sonnet" }, { ...base, model: "haiku" })).toEqual({ model: "haiku" });
  });

  it("부서·상위 관리자는 서버 필드 이름으로, null(없음)도 보낸다", () => {
    expect(changedAgentFields(base, { ...base, department: null, reports_to: "other" })).toEqual({ department_id: null, reports_to_id: "other" });
  });

  it("목록 필드와 여러 필드 동시 변경", () => {
    expect(changedAgentFields(base, { ...base, expertise: ["E2E"], enabled: false, allowed_skills: ["s1"] })).toEqual({
      expertise: ["E2E"],
      enabled: false,
      allowed_skills: ["s1"],
    });
  });

  it("권한과 편집기 전용 필드는 담지 않는다", () => {
    const next = { ...base, permissions: { ...base.permissions, allow_shell: true }, recommended_skills: ["x"], is_lead: true };
    expect(changedAgentFields(base, next)).toEqual({});
  });
});
