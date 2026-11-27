import { describe, expect, it } from "vitest";

import { clearAllDrafts, draftKey, loadDraft, pruneDrafts, recallScroll, rememberScroll, saveDraft } from "./drafts";

function memory() {
  const data = new Map<string, string>();
  return {
    data,
    get length() {
      return data.size;
    },
    key: (i: number) => [...data.keys()][i] ?? null,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

describe("대화별 입력 초안", () => {
  it("키는 조직·대화별로 다르다", () => {
    expect(draftKey("o1", "c1")).not.toBe(draftKey("o1", "c2"));
    expect(draftKey("o1", "c1")).not.toBe(draftKey("o2", "c1"));
    expect(draftKey(null, "c1")).toBe("ai-org.draft.none.c1");
  });
  it("저장·읽기·빈 글이면 지우기(전송 뒤)", () => {
    const s = memory();
    saveDraft("k", "쓰던 글", s);
    expect(loadDraft("k", s)).toBe("쓰던 글");
    saveDraft("k", "", s);
    expect(s.data.has("k")).toBe(false);
    expect(loadDraft("k", s)).toBe("");
  });
  it("저장소가 없거나 실패해도 입력을 막지 않는다", () => {
    expect(loadDraft("k", null)).toBe("");
    expect(() => saveDraft("k", "x", null)).not.toThrow();
    const broken = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("full"); }, removeItem: () => undefined };
    expect(loadDraft("k", broken)).toBe("");
    expect(() => saveDraft("k", "x", broken)).not.toThrow();
  });
});

describe("스크롤 위치(메모리)", () => {
  it("대화별로 기억한다", () => {
    expect(recallScroll("none")).toBeUndefined();
    rememberScroll("c1", { top: 120, stick: false });
    rememberScroll("c2", { top: 0, stick: true });
    expect(recallScroll("c1")).toEqual({ top: 120, stick: false });
    expect(recallScroll("c2")).toEqual({ top: 0, stick: true });
  });
});

describe("초안 지우기", () => {
  it("로그아웃: 초안 키만 모두 지운다(다른 키는 그대로)", () => {
    const s = memory();
    saveDraft(draftKey("o1", "c1"), "a", s);
    saveDraft(draftKey("o2", "c2"), "b", s);
    s.setItem("ai-org.theme", "dark");
    expect(clearAllDrafts(s)).toBe(2);
    expect([...s.data.keys()]).toEqual(["ai-org.theme"]);
    expect(clearAllDrafts(null)).toBe(0);
  });
  it("탭 정리: 그 조직에서 없어진 대화의 초안만 지운다", () => {
    const s = memory();
    saveDraft(draftKey("o1", "keep"), "a", s);
    saveDraft(draftKey("o1", "gone"), "b", s);
    saveDraft(draftKey("o2", "gone"), "c", s); // 다른 조직은 건드리지 않는다
    expect(pruneDrafts("o1", ["keep"], s)).toBe(1);
    expect(loadDraft(draftKey("o1", "keep"), s)).toBe("a");
    expect(loadDraft(draftKey("o1", "gone"), s)).toBe("");
    expect(loadDraft(draftKey("o2", "gone"), s)).toBe("c");
  });
});
