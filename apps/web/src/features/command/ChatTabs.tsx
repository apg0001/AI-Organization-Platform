/**
 * 커맨드 센터 대화 탭 줄(#96). 대화 머리 위에 열린 대화를 탭으로 보인다.
 * - ARIA tablist: ←/→ 이동, Home/End, Enter/Space 활성화, Delete 닫기. 활성 탭만 Tab 순서에 든다(roving tabindex).
 * - 상태 배지(아이콘 + 글자/aria): 실행 중, 승인 대기 n, 새 응답. 색만으로 구분하지 않는다.
 * - 넘치면 가로 스크롤. 탭이 하나여도 줄은 보인다(일관성).
 */

import { Circle, Hand, Keyboard, Loader2, X } from "lucide-react";
import { useRef } from "react";

import { cn } from "@/lib/utils";

import { TAB_SHORTCUTS_HINT } from "./tabsState";

export interface TabInfo {
  id: string;
  title: string;
  busy: boolean;
  approvals: number;
  unread: boolean;
}

export function ChatTabs({
  tabs,
  active,
  onActivate,
  onClose,
}: {
  tabs: TabInfo[];
  active: string | null;
  onActivate: (id: string) => void;
  onClose: (id: string) => void;
}) {
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const focusTab = (id: string | undefined) => id && refs.current.get(id)?.focus();
  const onKeyDown = (event: React.KeyboardEvent, index: number, id: string) => {
    const go = (to: number) => {
      event.preventDefault();
      focusTab(tabs[(to + tabs.length) % tabs.length]?.id);
    };
    if (event.key === "ArrowRight") go(index + 1);
    else if (event.key === "ArrowLeft") go(index - 1);
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(tabs.length - 1);
    else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate(id);
    } else if (event.key === "Delete") {
      event.preventDefault();
      // 닫은 뒤 포커스는 이웃 탭으로(활성 탭이면 화면 전환 뒤 입력창으로 옮겨 간다).
      focusTab(tabs[index + 1]?.id ?? tabs[index - 1]?.id);
      onClose(id);
    }
  };

  return (
    <div className="flex min-w-0 items-end border-b border-border bg-surface-1 px-2 pt-1.5">
      <div
        role="tablist"
        aria-label="열린 대화"
        aria-describedby="chat-tabs-hint"
        className="flex min-w-0 flex-1 gap-0.5 overflow-x-auto [scrollbar-width:thin]"
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          const status = [tab.busy && "실행 중", tab.approvals > 0 && `승인 대기 ${tab.approvals}건`, tab.unread && "새 응답"].filter(Boolean).join(", ");
          return (
            <div
              key={tab.id}
              className={cn(
                "group/tab flex max-w-56 min-w-28 shrink-0 items-center rounded-t-md border border-b-0 text-xs transition-colors duration-[120ms]",
                selected ? "border-border-strong bg-bg text-fg" : "border-transparent text-muted hover:bg-surface-2 hover:text-fg",
              )}
            >
              <button
                ref={(el) => {
                  if (el) refs.current.set(tab.id, el);
                  else refs.current.delete(tab.id);
                }}
                type="button"
                role="tab"
                id={`chat-tab-${tab.id}`}
                aria-selected={selected}
                aria-controls="chat-tab-panel"
                aria-label={status ? `${tab.title} (${status})` : tab.title}
                tabIndex={selected ? 0 : -1}
                title={`${tab.title}${index < 9 ? ` (Alt+${index + 1})` : ""}`}
                data-tab-id={tab.id}
                className="flex h-8 min-w-0 flex-1 cursor-pointer items-center gap-1.5 pr-1 pl-2.5 text-left"
                onClick={() => onActivate(tab.id)}
                onKeyDown={(e) => onKeyDown(e, index, tab.id)}
              >
                {tab.busy ? <Loader2 className="size-3 shrink-0 animate-spin text-[var(--status-working)] motion-reduce:animate-none" aria-hidden /> : null}
                <span className="min-w-0 flex-1 truncate">{tab.title}</span>
                {tab.approvals > 0 ? (
                  <span className="flex shrink-0 items-center gap-0.5 rounded-sm bg-warning px-1 text-2xs font-semibold text-on-warning tabular" aria-hidden>
                    <Hand className="size-3" />
                    {tab.approvals}
                  </span>
                ) : null}
                {tab.unread && !selected ? (
                  <span className="flex shrink-0 items-center gap-0.5 text-2xs text-primary-text" aria-hidden>
                    <Circle className="size-2 fill-current" />
                    새 응답
                  </span>
                ) : null}
              </button>
              <button
                type="button"
                tabIndex={-1}
                aria-label={`탭 닫기: ${tab.title}`}
                title="탭 닫기 (Alt+W)"
                className="mr-1 grid size-5 shrink-0 cursor-pointer place-items-center rounded-sm text-faint hover:bg-surface-3 hover:text-fg"
                onClick={() => onClose(tab.id)}
              >
                <X className="size-3" aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
      {/* 단축키 안내(마우스는 title, 화면 읽기 도구는 탭 목록 설명으로 읽는다). */}
      <span className="mb-1.5 ml-1 flex shrink-0 items-center text-faint" title={TAB_SHORTCUTS_HINT}>
        <Keyboard className="size-3.5" aria-hidden />
        <span id="chat-tabs-hint" className="sr-only">
          {TAB_SHORTCUTS_HINT}
        </span>
      </span>
    </div>
  );
}
