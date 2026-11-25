import { describe, expect, it } from "vitest";

import { crumbs } from "./FolderPicker";

describe("crumbs", () => {
  it("홈부터 현재 폴더까지 이동 단계를 만든다", () => {
    expect(crumbs("/home/u/code/app", "/home/u")).toEqual([
      { label: "홈", path: "/home/u" },
      { label: "code", path: "/home/u/code" },
      { label: "app", path: "/home/u/code/app" },
    ]);
  });
  it("홈이면 홈 하나만", () => {
    expect(crumbs("/home/u", "/home/u")).toEqual([{ label: "홈", path: "/home/u" }]);
  });
});
