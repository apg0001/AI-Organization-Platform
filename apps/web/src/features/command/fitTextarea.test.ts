import { afterEach, describe, expect, it, vi } from "vitest";

import { MAX_LINES, fitTextarea } from "./Composer";

/** 줄 높이 24px, 위아래 여백 4px인 가짜 입력창. scrollHeight는 줄 수로 정한다. */
function fakeTextarea(lines: number) {
  const el = { style: { height: "", overflowY: "" }, scrollHeight: lines * 24 + 8 };
  vi.stubGlobal("window", {
    getComputedStyle: () => ({ lineHeight: "24px", paddingTop: "4px", paddingBottom: "4px" }),
  });
  return el as unknown as HTMLTextAreaElement & { style: { height: string; overflowY: string } };
}

afterEach(() => vi.unstubAllGlobals());

describe("fitTextarea", () => {
  it("내용 줄 수만큼 늘어나고 스크롤은 끈다", () => {
    const el = fakeTextarea(3);
    fitTextarea(el);
    expect(el.style.height).toBe(`${3 * 24 + 8}px`);
    expect(el.style.overflowY).toBe("hidden");
  });

  it(`${MAX_LINES}줄을 넘으면 최대 높이에서 멈추고 스크롤한다`, () => {
    const el = fakeTextarea(12);
    fitTextarea(el);
    expect(el.style.height).toBe(`${MAX_LINES * 24 + 8}px`);
    expect(el.style.overflowY).toBe("auto");
  });
});
