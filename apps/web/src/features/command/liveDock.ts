/**
 * 여러 에이전트가 한 대화에서 동시에 응답할 때 놓치지 않게(#46): 입력창 위 '응답 중' 도크와 '새 응답' 알림의 상태 계산.
 * 메시지 순서는 바꾸지 않는다(읽던 위치가 튀지 않게). 화면 밖 메시지를 한 줄 요약으로 끌어올려 보여 줄 뿐이다.
 */

import type { ActivityEntry, ChatMessage } from "@/lib/api";

import { ACTIVITY_LABELS } from "./Messages";

export interface DockItem {
  messageId: string;
  agentId: string | null;
  /** 지금 하는 일 한 줄: 실행 중 도구 > 마지막 문장 > 준비 중. */
  line: string;
}

const LINE_MAX = 90;

/** 스트리밍 글의 마지막 의미 있는 줄(마크다운 기호·빈 줄 제외)을 짧게. */
export function lastLine(text: string): string {
  const lines = text
    .split("\n")
    .map((l) => l.replace(/^[#>*\-\s`]+/, "").trim())
    .filter(Boolean);
  const line = lines.at(-1) ?? "";
  return line.length > LINE_MAX ? `…${line.slice(-LINE_MAX)}` : line;
}

export function activityLine(entries: ActivityEntry[] | undefined): string | null {
  const running = [...(entries ?? [])].reverse().find((e) => e.status === "running");
  if (!running) return null;
  const label = ACTIVITY_LABELS[running.activity] ?? "도구";
  return `${label} · ${running.tool}${running.target ? ` ${running.target}` : ""}`;
}

/** 지금 응답 중인 assistant 메시지마다 한 줄. 화면 순서(오래된 것 먼저)를 따른다. */
export function dockItems(
  messages: ChatMessage[],
  liveText: Record<string, string>,
  liveActivity: Record<string, ActivityEntry[]>,
): DockItem[] {
  return messages
    .filter((m) => m.role === "assistant" && (m.status === "pending" || m.status === "streaming"))
    .map((m) => ({
      messageId: m.id,
      agentId: m.agent_id,
      line:
        activityLine(liveActivity[m.id] ?? m.activity) ??
        (lastLine(liveText[m.id] ?? m.content) || (m.status === "pending" ? "준비 중" : "생각 중")),
    }));
}

/**
 * 도크를 보일지: 둘 이상 동시에 응답 중이거나, 응답 중인 메시지 중 하나라도 화면 밖이면.
 * 하나만 응답 중이고 그게 보이고 있으면 도크는 군더더기라 숨긴다.
 */
export function showDock(items: DockItem[], visible: ReadonlySet<string>): boolean {
  if (items.length >= 2) return true;
  return items.some((i) => !visible.has(i.messageId));
}
