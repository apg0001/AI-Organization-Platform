import { describe, expect, it } from "vitest";

import type { ActivityEntry, ChatMessage } from "@/lib/api";

import { dockItems, lastLine, showDock } from "./liveDock";

const msg = (id: string, status: ChatMessage["status"], content = "", agent = `agent-${id}`): ChatMessage => ({
  id,
  conversation_id: "c",
  role: "assistant",
  agent_id: agent,
  content,
  data: {},
  activity: [],
  status,
  error: null,
  cost_usd: null,
  duration_ms: null,
  task_id: null,
  created_at: "2026-11-25T00:00:00Z",
});

const tool = (status: ActivityEntry["status"]): ActivityEntry => ({
  id: "t",
  tool: "Bash",
  activity: "testing",
  target: "npm test",
  status,
  subagent: false,
  at: "2026-11-25T00:00:00Z",
});

describe("dockItems", () => {
  it("응답 중인 메시지만, 실행 중 도구 > 마지막 문장 > 준비 중 순으로 한 줄을 만든다", () => {
    const items = dockItems(
      [msg("a", "streaming"), msg("b", "done", "끝"), msg("c", "streaming"), msg("d", "pending")],
      { c: "# 계획\n\n- 첫째\n- 둘째 단계 진행" },
      { a: [tool("done"), tool("running")] },
    );
    expect(items.map((i) => i.messageId)).toEqual(["a", "c", "d"]);
    expect(items[0]!.line).toBe("테스트 · Bash npm test");
    expect(items[1]!.line).toBe("둘째 단계 진행");
    expect(items[2]!.line).toBe("준비 중");
  });
});

describe("showDock", () => {
  const one = dockItems([msg("a", "streaming")], {}, {});
  const two = dockItems([msg("a", "streaming"), msg("b", "streaming")], {}, {});
  it("하나만 응답 중이고 보이면 숨기고, 화면 밖이면 보인다", () => {
    expect(showDock(one, new Set(["a"]))).toBe(false);
    expect(showDock(one, new Set())).toBe(true);
  });
  it("둘 이상 동시에 응답하면 항상 보인다", () => {
    expect(showDock(two, new Set(["a", "b"]))).toBe(true);
  });
  it("응답 중이 없으면 숨긴다", () => {
    expect(showDock([], new Set())).toBe(false);
  });
});

describe("lastLine", () => {
  it("긴 줄은 끝부분만 남긴다", () => {
    expect(lastLine("x".repeat(200))).toHaveLength(91);
  });
});
