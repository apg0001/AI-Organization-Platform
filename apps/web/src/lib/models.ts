/**
 * 에이전트별 Claude 모델 선택지(권한 표·권한 팝오버·에이전트 편집기 공용, models.test.ts로 고정).
 *
 * 서버는 에이전트의 `model`을 형식만 검증해 저장하고(`clean_model`), 실행을 시작할 때 Claude Code의 모델 옵션으로 넘긴다
 * (apps/server: services/runs.py → runtime/claude_code.py).
 * - 형식: 1~100자, 영문·숫자와 `. _ : - [ ]`만, `-`로 시작할 수 없다. 틀리면 저장이 422로 거부된다(사유는 선택 상자의 실패 토스트에 그대로 보인다).
 * - 빈 값·null은 기본 모델이다(모델을 지정하지 않아 Claude Code의 기본 모델이 쓰인다).
 * - 예전에 저장된 값이 형식에 맞지 않으면 조회 응답에서 null(기본값)로 보인다.
 * 서버는 그 이름의 모델이 실제로 있는지는 확인하지 않는다. 그래서 여기서는 Claude Code가 받는 별칭만 고르게 하고,
 * 이미 저장된 다른 값(전체 모델 ID 등)은 지우지 않고 그대로 보여 준다.
 */

/** Claude Code가 받는 모델 별칭. */
export const MODEL_ALIASES = ["opus", "sonnet", "haiku"] as const;
export type ModelAlias = (typeof MODEL_ALIASES)[number];

/** 선택 상자에서 '기본값'(model: null)을 나타내는 값. */
export const DEFAULT_MODEL_VALUE = "";

export const DEFAULT_MODEL_LABEL = "기본값(Claude Code 기본 모델)";

export const MODEL_NOTE = "모델은 다음 실행부터 적용됩니다(실행 중인 작업은 바뀌지 않음). 모델마다 속도와 사용량이 다릅니다.";

export function isKnownModel(model: string | null): boolean {
  return model === null || model === "" || (MODEL_ALIASES as readonly string[]).includes(model);
}

/** 화면에 보일 이름. 목록에 없는 값은 '사용자 지정: 값'. */
export function modelLabel(model: string | null): string {
  if (model === null || model === "") return DEFAULT_MODEL_LABEL;
  return isKnownModel(model) ? model : `사용자 지정: ${model}`;
}

export interface ModelOption {
  value: string;
  label: string;
}

/** 선택지: 기본값 + 별칭. 지금 저장된 값이 목록에 없으면 맨 끝에 그대로 넣는다(고르지 않는 한 지워지지 않게). */
export function modelOptions(current: string | null): ModelOption[] {
  const options: ModelOption[] = [
    { value: DEFAULT_MODEL_VALUE, label: DEFAULT_MODEL_LABEL },
    ...MODEL_ALIASES.map((alias) => ({ value: alias, label: alias })),
  ];
  if (current !== null && !isKnownModel(current)) options.push({ value: current, label: modelLabel(current) });
  return options;
}

/** 선택 상자의 값 ↔ 에이전트의 model. */
export function modelToValue(model: string | null): string {
  return model ?? DEFAULT_MODEL_VALUE;
}
export function modelFromValue(value: string): string | null {
  return value === DEFAULT_MODEL_VALUE ? null : value;
}

/** 모델만 바꾸는 PATCH 본문. 권한 등 다른 필드는 함께 보내지 않는다. */
export function modelPatch(value: string): { model: string | null } {
  return { model: modelFromValue(value) };
}
