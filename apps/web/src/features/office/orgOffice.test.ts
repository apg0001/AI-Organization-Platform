import { describe, expect, it } from "vitest";

import type { Agent } from "@/lib/api";

import { spriteRows } from "./sprites";
import { toOfficeState } from "./orgOffice";

const base: Omit<Agent, "id" | "name" | "is_lead" | "status" | "enabled"> = {
  organization_id: "o",
  title: "엔지니어",
  role: "",
  responsibilities: [],
  expertise: [],
  instructions: "",
  department_id: null,
  reports_to_id: null,
  runtime: "claude-code",
  model: null,
  allowed_skills: [],
  allowed_mcp_servers: [],
  allowed_plugins: [],
  permissions: {
    permission_mode: "default",
    file_scope: [],
    allow_shell: false,
    allow_network: true,
    allow_file_write: true,
    allow_file_delete: false,
    require_approval: [],
    can_delegate: false,
  },
  pos_x: null,
  pos_y: null,
  created_at: "2026-11-25T00:00:00Z",
  updated_at: "2026-11-25T00:00:00Z",
};
const agent = (id: string, extra: Partial<Agent>): Agent =>
  ({ ...base, id, name: id, is_lead: false, status: "idle", enabled: true, ...extra }) as Agent;

describe("toOfficeState", () => {
  it("CEO가 0번 책상, 비활성 에이전트는 제외", () => {
    const state = toOfficeState(
      [agent("a", {}), agent("ceo", { is_lead: true }), agent("off", { enabled: false })],
      {},
    );
    expect(state.sessions.map((s) => [s.id, s.desk_slot])).toEqual([
      ["ceo", 0],
      ["a", 1],
    ]);
    expect(state.agents.find((a) => a.id === "ceo")?.role).toBe("lead");
    expect(state.agents.find((a) => a.id === "a")?.role).toBe("member");
  });

  it("상태와 최근 활동으로 턴·활동을 정한다", () => {
    const state = toOfficeState(
      [agent("w", { status: "working" }), agent("q", { status: "waiting" }), agent("t", { status: "thinking" }), agent("d", { status: "completed" })],
      { w: "testing", t: "unknown" },
    );
    const by = Object.fromEntries(state.agents.map((a) => [a.id, [a.turn_state, a.activity]]));
    expect(by).toEqual({
      w: ["WORKING", "testing"],
      q: ["WAITING_USER", "waiting_user"],
      t: ["THINKING", "thinking"],
      d: ["IDLE", "idle"],
    });
  });
});

describe("sprites", () => {
  it("구성원은 왕관이 없다", () => {
    expect(spriteRows("lead", 0).join("")).toContain("k");
    expect(spriteRows("member", 0).join("")).not.toContain("k");
  });
});
