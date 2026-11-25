import { describe, expect, it } from "vitest";

import { sentHistory, stepHistory } from "./Composer";

describe("stepHistory", () => {
  const h = ["첫째", "둘째", "셋째"];
  it("↑는 최근부터 오래된 쪽으로, 처음에서 멈춘다", () => {
    expect(stepHistory(h, null, "up")).toEqual({ index: 2 });
    expect(stepHistory(h, 2, "up")).toEqual({ index: 1 });
    expect(stepHistory(h, 0, "up")).toBeNull();
  });
  it("↓는 끝을 지나면 초안(null)으로 돌아오고, 초안에서는 그대로", () => {
    expect(stepHistory(h, 1, "down")).toEqual({ index: 2 });
    expect(stepHistory(h, 2, "down")).toEqual({ index: null });
    expect(stepHistory(h, null, "down")).toBeNull();
  });
  it("기록이 없으면 아무것도 안 한다", () => {
    expect(stepHistory([], null, "up")).toBeNull();
  });
});

describe("sentHistory", () => {
  it("사용자 메시지·명령만, 이어진 중복은 하나로", () => {
    const m = (role: string, content: string) => ({ role, content });
    expect(
      sentHistory([m("user", "a"), m("assistant", "x"), m("user", "a"), m("command", "/agents"), m("user", " ")]),
    ).toEqual(["a", "/agents"]);
  });
});
