import { AlertTriangle, Check, ChevronRight, Copy, FileText, Loader2, RotateCcw, Square, TerminalSquare } from "lucide-react";
import { type ComponentProps, memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { IconButton } from "@/components/ui/button";
import type { ActivityEntry, Agent, ChatMessage } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";

export const ACTIVITY_LABELS: Record<string, string> = {
  reading: "읽기",
  coding: "편집",
  browsing: "웹",
  testing: "테스트",
  planning: "계획",
  delegating: "위임",
  asking: "질문",
  unknown: "도구",
};

function CodeBlock(props: ComponentProps<"pre">) {
  const [copied, setCopied] = useState(false);
  const copy = (event: React.MouseEvent<HTMLButtonElement>) => {
    const pre = event.currentTarget.parentElement?.querySelector("pre");
    void navigator.clipboard.writeText(pre?.innerText ?? "").then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="group relative">
      <pre {...props} className="overflow-x-auto rounded-md border border-border bg-[#0b0d11] px-3.5 py-3 font-mono text-xs leading-relaxed" />
      <button
        type="button"
        onClick={copy}
        aria-label={copied ? "복사됨" : "코드 복사"}
        className="absolute top-1.5 right-1.5 flex cursor-pointer items-center gap-1 rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 text-2xs text-muted opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
      >
        {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
        {copied ? "복사됨" : "복사"}
      </button>
    </div>
  );
}

export const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <div className="prose-chat">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={{
          pre: CodeBlock,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});

export function ActivityList({ entries, open: initial = false }: { entries: ActivityEntry[]; open?: boolean }) {
  const [open, setOpen] = useState(initial);
  if (entries.length === 0) return null;
  const running = entries.filter((e) => e.status === "running").length;
  return (
    <div className="text-xs">
      <button
        type="button"
        className="flex cursor-pointer items-center gap-1 text-faint hover:text-muted"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <ChevronRight className={cn("size-3.5 transition-transform duration-150", open && "rotate-90")} aria-hidden />
        도구 사용 {entries.length}회{running ? ` · ${running}개 실행 중` : ""}
      </button>
      {open ? (
        <ol className="mt-1.5 flex flex-col gap-1 border-l border-border pl-3">
          {entries.map((e) => (
            <li key={`${e.id}-${e.at}`} className="flex items-center gap-2">
              <span
                className="size-1.5 shrink-0 rounded-full"
                style={{
                  background:
                    e.status === "running"
                      ? "var(--status-working)"
                      : e.status === "failed"
                        ? "var(--status-failed)"
                        : e.status === "cancelled"
                          ? "var(--status-offline)"
                          : "var(--status-completed)",
                }}
                aria-hidden
              />
              <span className="w-10 shrink-0 text-faint">{ACTIVITY_LABELS[e.activity] ?? "도구"}</span>
              <span className="shrink-0 font-medium text-muted">{e.tool}</span>
              <span className="min-w-0 truncate font-mono text-faint" title={e.target}>
                {e.target}
              </span>
              {e.status === "failed" ? <span className="shrink-0 text-danger">거부·실패</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}

export function MessageView({
  message,
  agent,
  liveText,
  liveActivity,
  onRegenerate,
  onAction,
}: {
  message: ChatMessage;
  agent?: Agent;
  liveText?: string;
  liveActivity?: ActivityEntry[];
  onRegenerate?: () => void;
  onAction?: (action: NonNullable<NonNullable<ChatMessage["data"]["result"]>["action"]>) => void;
}) {
  if (message.role === "user") {
    const atts = message.data.attachments ?? [];
    return (
      <div className="flex flex-col items-end gap-1.5">
        <div className="max-w-[min(80%,72ch)] rounded-lg bg-surface-3 px-3.5 py-2.5 text-base whitespace-pre-wrap">
          {message.data.mention_all ? <span className="mr-1 text-primary-text">@All</span> : null}
          {message.content}
        </div>
        {atts.length ? (
          <div className="flex flex-wrap justify-end gap-1.5">
            {atts.map((a) =>
              a.media_type.startsWith("image/") ? (
                <img
                  key={a.id}
                  src={`/api/v1/attachments/${a.id}/content`}
                  alt={a.filename}
                  width={96}
                  height={96}
                  loading="lazy"
                  className="size-24 rounded-md border border-border object-cover"
                />
              ) : (
                <span key={a.id} className="flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-muted">
                  <FileText className="size-3.5" aria-hidden />
                  {a.filename}
                  <span className="text-faint">{formatBytes(a.size)}</span>
                </span>
              ),
            )}
          </div>
        ) : null}
      </div>
    );
  }

  if (message.role === "command") {
    const result = message.data.result;
    return (
      <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-1 px-3.5 py-3">
        <span className="flex items-center gap-1.5 font-mono text-xs text-muted">
          <TerminalSquare className="size-3.5" aria-hidden /> {message.content}
        </span>
        {message.error ? <p className="text-sm text-danger">{message.error}</p> : null}
        {result ? (
          <>
            {result.text ? <p className="text-sm">{result.text}</p> : null}
            {result.rows.length ? (
              <div className="max-h-80 overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-2xs text-faint">
                    <tr>
                      {result.columns.map((c) => (
                        <th key={c} className="pr-3 pb-1 font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        {row.map((cell, j) => (
                          <td key={j} className={cn("py-1 pr-3", j === 0 ? "font-medium" : "text-muted")}>
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {result.action?.type === "approvals.open" && onAction ? (
              <button type="button" className="w-fit cursor-pointer text-xs text-primary-text underline" onClick={() => onAction(result.action!)}>
                실행 패널에서 승인하기
              </button>
            ) : null}
          </>
        ) : null}
      </div>
    );
  }

  // assistant
  const text = message.status === "streaming" || message.status === "pending" ? (liveText ?? message.content) : message.content;
  const activity = message.status === "streaming" && liveActivity ? liveActivity : message.activity;
  const working = message.status === "pending" || message.status === "streaming";
  return (
    <div className="group flex gap-3">
      {agent ? <AgentAvatar id={agent.id} lead={agent.is_lead} size={30} /> : <span className="size-[30px]" />}
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <span className="flex items-center gap-2 text-xs">
          <span className="font-medium text-fg">{agent?.name ?? "삭제된 에이전트"}</span>
          {agent?.title ? <span className="text-faint">{agent.title}</span> : null}
          {message.task_id ? <span className="rounded-sm bg-surface-3 px-1 text-2xs text-muted">위임 작업</span> : null}
        </span>
        <ActivityList entries={activity} open={working} />
        {text ? <Markdown text={text} /> : null}
        {working && !text ? (
          <span className="flex items-center gap-2 text-sm text-muted" role="status">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {message.status === "pending" ? "실행 대기 중(동시 실행 한도)…" : "생각하는 중…"}
          </span>
        ) : null}
        {working && text ? <span className="inline-block h-4 w-1.5 animate-pulse bg-primary-text" aria-hidden /> : null}
        {message.status === "interrupted" ? (
          <span className="flex items-center gap-1.5 text-xs text-faint">
            <Square className="size-3" aria-hidden /> 중지됨{message.error && message.error !== "중지됨" ? ` — ${message.error}` : ""}
          </span>
        ) : null}
        {message.status === "error" ? (
          <span className="flex items-start gap-1.5 text-xs text-danger" role="alert">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {message.error}
          </span>
        ) : null}
        {!working ? (
          <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            {message.content ? (
              <IconButton label="응답 복사" size="icon-sm" onClick={() => void navigator.clipboard.writeText(message.content)}>
                <Copy />
              </IconButton>
            ) : null}
            {onRegenerate ? (
              <IconButton label="다시 생성" size="icon-sm" onClick={onRegenerate}>
                <RotateCcw />
              </IconButton>
            ) : null}
            {message.duration_ms ? (
              <span className="ml-1 text-2xs text-faint tabular">
                {(message.duration_ms / 1000).toFixed(1)}초{message.cost_usd ? ` · $${message.cost_usd.toFixed(3)}` : ""}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
