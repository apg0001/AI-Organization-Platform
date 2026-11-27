import { describe, expect, it } from "vitest";

import { ApiError, type ChatMessage } from "@/lib/api";

import { MAX_MESSAGE_LENGTH, canCopy, canEditQueued, closedEditNotice, editFailure, queuedEditProblem } from "./queuedEdit";

const msg = (role: ChatMessage["role"], data: ChatMessage["data"]) => ({ role, data });

describe("대기 메시지 수정 가능 여부", () => {
  it("대기 중인 사용자 메시지만", () => {
    expect(canEditQueued(msg("user", { queue_state: "waiting" }))).toBe(true);
    expect(canEditQueued(msg("user", { queue_state: "delivered" }))).toBe(false);
    expect(canEditQueued(msg("user", { queue_state: "cancelled" }))).toBe(false);
    expect(canEditQueued(msg("user", {}))).toBe(false);
    expect(canEditQueued(msg("assistant", { queue_state: "waiting" }))).toBe(false);
    expect(canEditQueued(msg("command", { queue_state: "waiting" }))).toBe(false);
  });
});

describe("수정 입력 검사", () => {
  it("빈 내용·변화 없음·길이 초과를 막는다", () => {
    expect(queuedEditProblem("원래", "  \n")).toBe("내용을 입력하세요.");
    expect(queuedEditProblem("원래", "원래")).toBe("바뀐 내용이 없습니다.");
    expect(queuedEditProblem("원래", "a".repeat(MAX_MESSAGE_LENGTH + 1))).toContain("50,000자");
    expect(queuedEditProblem("원래", "고친 내용")).toBeNull();
    expect(queuedEditProblem("원래", "a".repeat(MAX_MESSAGE_LENGTH))).toBeNull();
  });
});

describe("저장 실패 처리", () => {
  it("409는 이미 전달됨(편집 닫기), 그 밖은 편집 유지", () => {
    expect(editFailure(new ApiError(409, "이미 전달되었거나 대기 중이 아닌 메시지입니다.", null))).toBe("stale");
    expect(editFailure(new ApiError(422, "빈 내용", null))).toBe("error");
    expect(editFailure(new ApiError(404, "없음", null))).toBe("error");
    expect(editFailure(new Error("연결 끊김"))).toBe("error");
  });
});

describe("편집 중 전달·취소로 닫힐 때", () => {
  it("알림은 상태에 맞게, 입력 내용을 남겨 두었다고 알린다", () => {
    expect(closedEditNotice("delivered")).toContain("이미 전달되어");
    expect(closedEditNotice("cancelled")).toContain("취소되어");
    for (const state of ["delivered", "cancelled"] as const) expect(closedEditNotice(state)).toContain("남겨 두었습니다");
  });
  it("클립보드가 없으면(보안 컨텍스트 아님) 복사 버튼을 내지 않는다", () => {
    expect(canCopy(undefined)).toBe(false);
    expect(canCopy({} as Navigator)).toBe(false);
    expect(canCopy({ clipboard: { writeText: () => Promise.resolve() } } as unknown as Navigator)).toBe(true);
  });
});
