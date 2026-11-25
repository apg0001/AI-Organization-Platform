/**
 * 입력창 바로 위 '응답 중' 도크와 '새 응답' 알림(#46).
 * 여러 에이전트가 동시에 응답하면 메시지 칸이 위아래로 나뉘어 함께 자라므로, 화면 밖 진행·완료를 여기서 한눈에 보여 준다.
 * 줄을 누르면 그 메시지로 이동한다.
 */

import { ArrowDown, ArrowUp, Loader2, X } from "lucide-react";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import type { Agent } from "@/lib/api";
import { cn } from "@/lib/utils";

import type { DockItem } from "./liveDock";

export interface Unseen {
  messageId: string;
  agentId: string | null;
  failed: boolean;
  above: boolean;
}

export function LiveDock({
  items,
  visible,
  show,
  unseen,
  agentById,
  onJump,
  onDismiss,
}: {
  items: DockItem[];
  visible: ReadonlySet<string>;
  show: boolean;
  unseen: Unseen[];
  agentById: Map<string, Agent>;
  onJump: (messageId: string) => void;
  onDismiss: (messageId: string) => void;
}) {
  if (!show && unseen.length === 0) return null;
  const name = (id: string | null) => (id ? (agentById.get(id)?.name ?? "에이전트") : "에이전트");
  return (
    <div className="flex flex-col gap-1.5 px-4 pb-2">
      {unseen.length ? (
        <ul className="flex flex-wrap gap-1.5" aria-label="새 응답">
          {unseen.map((u) => (
            <li key={u.messageId} className="feed-in flex items-center rounded-full border border-border-strong bg-surface-2 text-xs shadow-overlay">
              <button
                type="button"
                onClick={() => onJump(u.messageId)}
                className="flex items-center gap-1.5 rounded-l-full py-1 pr-1 pl-2.5 hover:bg-surface-3"
              >
                {u.above ? <ArrowUp className="size-3.5" aria-hidden /> : <ArrowDown className="size-3.5" aria-hidden />}
                <span className="font-medium">{name(u.agentId)}</span>
                <span className={u.failed ? "text-danger" : "text-muted"}>{u.failed ? "응답 실패" : "응답 완료"}</span>
              </button>
              <button
                type="button"
                aria-label={`${name(u.agentId)} 알림 닫기`}
                onClick={() => onDismiss(u.messageId)}
                className="grid size-6 place-items-center rounded-r-full text-faint hover:bg-surface-3 hover:text-fg"
              >
                <X className="size-3" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {show ? (
        <section aria-label={`응답 중 ${items.length}`} className="rounded-md border border-border bg-surface-1">
          <h2 className="flex items-center gap-1.5 px-2.5 pt-1.5 text-2xs font-medium text-faint">
            <Loader2 className="size-3 animate-spin" aria-hidden /> 응답 중 {items.length}
          </h2>
          <ul className="flex max-h-32 flex-col overflow-y-auto py-1">
            {items.map((item) => (
              <li key={item.messageId}>
                <button
                  type="button"
                  onClick={() => onJump(item.messageId)}
                  className={cn(
                    "flex w-full items-center gap-2 px-2.5 py-1 text-left text-xs hover:bg-surface-2",
                    visible.has(item.messageId) && "opacity-70",
                  )}
                  title="이 응답으로 이동"
                >
                  <AgentAvatar id={item.agentId ?? item.messageId} size={18} />
                  <span className="shrink-0 font-medium">{name(item.agentId)}</span>
                  <span className="min-w-0 flex-1 truncate text-muted">{item.line}</span>
                  <span className="shrink-0 text-2xs text-faint">{visible.has(item.messageId) ? "보는 중" : "이동"}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
