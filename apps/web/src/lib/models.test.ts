import { describe, expect, it } from "vitest";

import { DEFAULT_MODEL_LABEL, MODEL_ALIASES, isKnownModel, modelFromValue, modelLabel, modelOptions, modelPatch, modelToValue } from "./models";

describe("Claude 모델 선택지", () => {
  it("기본값 + Claude Code 별칭 셋", () => {
    expect(MODEL_ALIASES).toEqual(["opus", "sonnet", "haiku"]);
    expect(modelOptions(null)).toEqual([
      { value: "", label: "기본값(Claude Code 기본 모델)" },
      { value: "opus", label: "opus" },
      { value: "sonnet", label: "sonnet" },
      { value: "haiku", label: "haiku" },
    ]);
    expect(modelOptions("sonnet")).toEqual(modelOptions(null));
  });

  it("목록에 없는 저장 값은 '사용자 지정'으로 그대로 보여 준다(지우지 않는다)", () => {
    const options = modelOptions("claude-opus-4-1-20250805");
    expect(options).toHaveLength(5);
    expect(options[4]).toEqual({ value: "claude-opus-4-1-20250805", label: "사용자 지정: claude-opus-4-1-20250805" });
    // 그 값을 그대로 다시 고르면 같은 값이 저장된다.
    expect(modelPatch(modelToValue("claude-opus-4-1-20250805"))).toEqual({ model: "claude-opus-4-1-20250805" });
    expect(isKnownModel("claude-opus-4-1-20250805")).toBe(false);
    expect(isKnownModel("Opus")).toBe(false); // 대소문자를 바꿔 주지 않는다(서버 값 그대로)
  });

  it("라벨", () => {
    expect(modelLabel(null)).toBe(DEFAULT_MODEL_LABEL);
    expect(modelLabel("")).toBe(DEFAULT_MODEL_LABEL);
    expect(modelLabel("haiku")).toBe("haiku");
    expect(modelLabel("my-model")).toBe("사용자 지정: my-model");
  });

  it("선택 상자 값 ↔ model: 기본값은 null", () => {
    expect(modelToValue(null)).toBe("");
    expect(modelFromValue("")).toBeNull();
    expect(modelFromValue("opus")).toBe("opus");
    for (const model of [null, "opus", "sonnet", "haiku", "custom-id"]) expect(modelFromValue(modelToValue(model))).toBe(model);
  });

  it("PATCH 본문은 model 하나만 담는다", () => {
    expect(modelPatch("sonnet")).toEqual({ model: "sonnet" });
    expect(modelPatch("")).toEqual({ model: null });
    expect(Object.keys(modelPatch("opus"))).toEqual(["model"]);
  });
});
