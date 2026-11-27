/**
 * 대기 중인 메시지 수정(#95). 화면 판단을 순수 함수로 두고 queuedEdit.test.ts로 고정한다.
 * 서버: POST /conversations/{id}/messages/{message_id}/edit-queued — 대기 중(queue_state=waiting)인 사용자 메시지만 고칠 수 있다.
 */

import { ApiError, type ChatMessage } from "@/lib/api";

export const MAX_MESSAGE_LENGTH = 50_000;

/** 수정할 수 있는 메시지인지: 아직 전달되지 않고 대기 중인 사용자 메시지만. */
export function canEditQueued(message: Pick<ChatMessage, "role" | "data">): boolean {
  return message.role === "user" && message.data.queue_state === "waiting";
}

/** 저장 전에 막을 수 있는 입력 문제. 문제없으면 null. */
export function queuedEditProblem(original: string, draft: string): string | null {
  if (!draft.trim()) return "내용을 입력하세요.";
  if (draft.length > MAX_MESSAGE_LENGTH) return `메시지는 ${MAX_MESSAGE_LENGTH.toLocaleString()}자까지 쓸 수 있습니다.`;
  if (draft === original) return "바뀐 내용이 없습니다.";
  return null;
}

/**
 * 저장 실패를 어떻게 처리할지.
 * - stale(409): 그사이 전달·취소됨 → 편집을 닫고 최신 값으로.
 * - error: 그 밖의 오류 → 서버 사유를 알리고 편집은 유지(입력을 잃지 않게).
 */
export function editFailure(error: unknown): "stale" | "error" {
  return error instanceof ApiError && error.status === 409 ? "stale" : "error";
}

export const STALE_EDIT_MESSAGE = "이미 전달되어 수정할 수 없습니다.";

/** 편집 중에 메시지가 전달·취소되어 편집을 닫을 때의 알림 문구. */
export function closedEditNotice(state: ChatMessage["data"]["queue_state"]): string {
  return state === "cancelled"
    ? "메시지가 취소되어 수정을 닫았습니다. 입력하던 내용은 메시지 아래에 남겨 두었습니다."
    : "메시지가 이미 전달되어 수정을 닫았습니다. 고친 내용은 반영되지 않았고, 메시지 아래에 남겨 두었습니다.";
}

/** 클립보드에 쓸 수 있는지(보안 컨텍스트가 아니면 navigator.clipboard가 없다). */
export function canCopy(nav: Pick<Navigator, "clipboard"> | undefined): boolean {
  return typeof nav?.clipboard?.writeText === "function";
}
