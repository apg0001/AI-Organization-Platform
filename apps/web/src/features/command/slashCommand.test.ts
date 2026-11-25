import { describe, expect, it } from "vitest";

import { isCommandInput } from "./Composer";

describe("isCommandInput", () => {
  it("첫 단어가 /이름 꼴이면 명령", () => {
    expect(isCommandInput("/agents")).toBe(true);
    expect(isCommandInput("/delegate @QA 점검")).toBe(true);
    expect(isCommandInput("/no-such-cmd")).toBe(true);
  });
  it("경로로 시작하면 일반 메시지", () => {
    expect(isCommandInput("/home/gichan/Agent-Office 지금 이거 아님?")).toBe(false);
    expect(isCommandInput("/etc/hosts 봐 줘")).toBe(false);
    expect(isCommandInput("/")).toBe(false);
    expect(isCommandInput("경로는 /home/me")).toBe(false);
  });
});
