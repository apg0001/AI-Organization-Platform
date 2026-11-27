import { describe, expect, it } from "vitest";

import { MAX_TABS, closeTab, moveTab, nthTab, openTab, parseStoredTabs, placeActive, pruneTabs, replaceTab, tabShortcut } from "./tabsState";

const many = (n: number) => Array.from({ length: n }, (_, i) => `c${i + 1}`);

describe("탭 열기", () => {
  it("중복 없이 연다. 이미 있으면 목록 그대로", () => {
    expect(openTab([], "a").tabs).toEqual(["a"]);
    expect(openTab(["a", "b"], "a")).toEqual({ tabs: ["a", "b"], rejected: false });
  });
  it("기준 탭 바로 오른쪽에, 없으면 맨 끝에", () => {
    expect(openTab(["a", "b", "c"], "x", "a").tabs).toEqual(["a", "x", "b", "c"]);
    expect(openTab(["a", "b"], "x", "zz").tabs).toEqual(["a", "b", "x"]);
    expect(openTab(["a", "b"], "x").tabs).toEqual(["a", "b", "x"]);
  });
  it(`최대 ${MAX_TABS}개: 가득 차면 거부하고 목록은 그대로`, () => {
    const full = many(MAX_TABS);
    expect(openTab(full, "new")).toEqual({ tabs: full, rejected: true });
    expect(openTab(full, "c3")).toEqual({ tabs: full, rejected: false }); // 이미 열린 탭은 거부하지 않는다
    expect(openTab(many(MAX_TABS - 1), "new").tabs).toHaveLength(MAX_TABS);
  });
});

describe("현재 탭 내용 바꾸기(일반 클릭·대화 따라가기)", () => {
  it("현재 탭 자리를 바꾼다", () => {
    expect(replaceTab(["a", "b", "c"], "b", "x")).toEqual(["a", "x", "c"]);
  });
  it("이미 다른 탭에 열려 있으면 목록 그대로(그 탭으로 이동)", () => {
    expect(replaceTab(["a", "b"], "a", "b")).toEqual(["a", "b"]);
  });
  it("현재 탭이 없으면 새로, 가득 찼으면 맨 끝 탭을 바꾼다", () => {
    expect(replaceTab([], null, "x")).toEqual(["x"]);
    expect(replaceTab(["a"], "gone", "x")).toEqual(["a", "x"]);
    const full = many(MAX_TABS);
    expect(replaceTab(full, null, "x")).toEqual([...full.slice(0, -1), "x"]);
  });
});

describe("탭 닫기", () => {
  it("활성 탭을 닫으면 오른쪽 이웃 → 없으면 왼쪽", () => {
    expect(closeTab(["a", "b", "c"], "b", "b")).toEqual({ tabs: ["a", "c"], active: "c" });
    expect(closeTab(["a", "b", "c"], "c", "c")).toEqual({ tabs: ["a", "b"], active: "b" });
    expect(closeTab(["a"], "a", "a")).toEqual({ tabs: [], active: null });
  });
  it("비활성 탭을 닫으면 활성 탭 그대로", () => {
    expect(closeTab(["a", "b", "c"], "a", "c")).toEqual({ tabs: ["b", "c"], active: "c" });
  });
  it("없는 탭은 무시", () => {
    expect(closeTab(["a"], "x", "a")).toEqual({ tabs: ["a"], active: "a" });
  });
});

describe("정리", () => {
  it("대화 목록에 없는 탭(삭제·보관)을 뺀다", () => {
    expect(pruneTabs(["a", "b", "c"], ["a", "c", "z"])).toEqual(["a", "c"]);
  });
  it("목록을 아직 못 받았으면(로딩 중) 건드리지 않는다", () => {
    const tabs = ["a", "b"];
    expect(pruneTabs(tabs, undefined)).toBe(tabs);
  });
  it("바뀐 것이 없으면 같은 배열(불필요한 저장·렌더를 막는다)", () => {
    const tabs = ["a", "b"];
    expect(pruneTabs(tabs, ["b", "a"])).toBe(tabs);
  });
});

describe("이동·n번째·단축키·저장 값", () => {
  it("왼쪽·오른쪽으로 옮기고 끝에서는 그대로", () => {
    expect(moveTab(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(moveTab(["a", "b", "c"], "b", 1)).toEqual(["a", "c", "b"]);
    expect(moveTab(["a", "b"], "a", -1)).toEqual(["a", "b"]);
  });
  it("n번째(1부터), 9는 마지막", () => {
    expect(nthTab(["a", "b", "c"], 1)).toBe("a");
    expect(nthTab(["a", "b", "c"], 3)).toBe("c");
    expect(nthTab(["a", "b", "c"], 4)).toBeNull();
    expect(nthTab(["a", "b", "c"], 9)).toBe("c");
    expect(nthTab([], 9)).toBeNull();
  });
  it("Alt+숫자·Alt+W를 event.code로 판정(macOS Option 문자와 무관)", () => {
    const key = (code: string, mods: Partial<Record<"altKey" | "ctrlKey" | "metaKey" | "shiftKey", boolean>> = {}) => ({
      altKey: false,
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
      code,
      ...mods,
    });
    expect(tabShortcut(key("Digit2", { altKey: true }))).toEqual({ kind: "nth", n: 2 });
    expect(tabShortcut(key("KeyW", { altKey: true }))).toEqual({ kind: "close" });
    expect(tabShortcut(key("Digit2"))).toBeNull(); // Alt 없음
    expect(tabShortcut(key("Digit2", { altKey: true, ctrlKey: true }))).toBeNull(); // 다른 조합과 겹치지 않게
    expect(tabShortcut(key("KeyB", { ctrlKey: true }))).toBeNull(); // Ctrl+B(사이드바)와 무관
    expect(tabShortcut(key("Digit0", { altKey: true }))).toBeNull();
  });
  it("저장 값 읽기: 망가진 값은 빈 목록, 중복 제거, 최대 개수", () => {
    expect(parseStoredTabs(null)).toEqual([]);
    expect(parseStoredTabs("not json")).toEqual([]);
    expect(parseStoredTabs('{"a":1}')).toEqual([]);
    expect(parseStoredTabs('["a","a",3,"b"]')).toEqual(["a", "b"]);
    expect(parseStoredTabs(JSON.stringify(many(12)))).toHaveLength(MAX_TABS);
  });
});

describe("주소의 대화를 그 조직의 탭에 반영(다른 조직 링크)", () => {
  it("같은 조직이면 현재 탭 자리를 바꾼다", () => {
    expect(placeActive(["a", "b"], "b", "x", "orgA", "orgA")).toEqual(["a", "x"]);
    expect(placeActive(["a", "b"], "a", "b", "orgA", "orgA")).toEqual(["a", "b"]);
  });
  it("조직을 아직 모르거나 다른 조직이면 건드리지 않는다(앞 조직 탭이 사라지지 않게)", () => {
    expect(placeActive(["a", "b"], "b", "x", undefined, "orgA")).toBeNull();
    expect(placeActive(["a", "b"], "b", "x", "orgB", "orgA")).toBeNull();
    expect(placeActive(["a"], "a", "x", "orgA", null)).toBeNull();
  });
  it("조직이 바뀐 뒤에는 그 조직의 탭 목록에 넣는다(앞 조직의 대화는 그 목록에 없으므로 끝에 추가)", () => {
    expect(placeActive(["p", "q"], "a", "x", "orgB", "orgB")).toEqual(["p", "q", "x"]);
  });
});

describe("입력기 조합 중 단축키", () => {
  it("isComposing·keyCode 229면 무시", () => {
    const base = { altKey: true, ctrlKey: false, metaKey: false, shiftKey: false, code: "Digit1" };
    expect(tabShortcut({ ...base, isComposing: true })).toBeNull();
    expect(tabShortcut({ ...base, keyCode: 229 })).toBeNull();
    expect(tabShortcut({ ...base, isComposing: false, keyCode: 49 })).toEqual({ kind: "nth", n: 1 });
  });
});
