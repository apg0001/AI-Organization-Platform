import { describe, expect, it } from "vitest";

import type { Agent, CommandSpec } from "@/lib/api";

import { parseArgs } from "./Composer";

const agents = [
  { id: "1", name: "QA 엔지니어" },
  { id: "2", name: "QA" },
] as Agent[];
const delegate: CommandSpec = {
  name: "delegate",
  description: "",
  usage: "",
  args: [
    { name: "agent", kind: "agent", required: true, description: "" },
    { name: "task", kind: "text", required: true, description: "" },
  ],
};

describe("parseArgs", () => {
  it("가장 긴 에이전트 이름을 먼저 맞춘다", () => {
    expect(parseArgs(delegate, "@QA 엔지니어 회귀 테스트 돌려", agents)).toEqual({ agent: "1", task: "회귀 테스트 돌려" });
    expect(parseArgs(delegate, "@QA 점검", agents)).toEqual({ agent: "2", task: "점검" });
  });
  it("모르는 이름은 첫 단어를 그대로 넘긴다(서버가 검증)", () => {
    expect(parseArgs(delegate, "@없는사람 일", agents)).toEqual({ agent: "@없는사람", task: "일" });
  });
});
