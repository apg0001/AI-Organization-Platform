/**
 * 채팅 입력: 텍스트, `/` 명령 자동완성(서버 Command Registry), `@` 멘션 자동완성, 파일 첨부(끌어놓기·선택·붙여넣기).
 * 첨부는 고르는 즉시 로컬 백엔드로 올리고(진행률 표시), 메시지를 보낼 때 ID만 넘긴다.
 */

import { FileText, Loader2, Paperclip, SendHorizontal, Square, X } from "lucide-react";
import {
  type ClipboardEvent,
  type DragEvent,
  type KeyboardEvent,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { IconButton } from "@/components/ui/button";
import { type Agent, type AttachmentInfo, type CommandSpec, api, uploadFile } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";

const MAX_BYTES = 20 * 1024 * 1024;
const MAX_FILES = 10;
/** 입력창이 내용에 맞춰 늘어나는 최대 줄 수. 넘으면 입력창 안에서 스크롤한다. */
export const MAX_LINES = 5;

/**
 * 명령으로 볼지: 첫 단어가 `/이름`(영문·숫자·-·_만) 꼴일 때만. `/home/me/app 봐 줘`처럼 경로로 시작하면 일반 메시지다.
 */
export function isCommandInput(text: string): boolean {
  return /^\/[\w-]+(\s|$)/.test(text);
}

/**
 * 보낸 메시지 기록 탐색(↑/↓, #69). index는 기록 안 위치(null이면 쓰던 초안).
 * 위로 가면 더 오래된 기록, 아래로 끝을 지나면 초안으로 돌아온다. 바뀌지 않으면 null.
 */
export function stepHistory(
  history: string[],
  index: number | null,
  direction: "up" | "down",
): { index: number | null } | null {
  if (history.length === 0) return null;
  if (direction === "up") {
    if (index === null) return { index: history.length - 1 };
    return index > 0 ? { index: index - 1 } : null;
  }
  if (index === null) return null;
  return index < history.length - 1 ? { index: index + 1 } : { index: null };
}

/** 이 대화에서 보낸 글(오래된 것 먼저), 바로 이어진 같은 글은 하나로. */
export function sentHistory(messages: { role: string; content: string }[]): string[] {
  const out: string[] = [];
  for (const m of messages) {
    if ((m.role === "user" || m.role === "command") && m.content.trim() && out.at(-1) !== m.content) out.push(m.content);
  }
  return out;
}

/** 내용 높이에 맞춰 늘리되 최대 줄 수에서 멈추고, 넘치면 스크롤을 켠다. */
export function fitTextarea(el: HTMLTextAreaElement, maxLines = MAX_LINES): void {
  const style = window.getComputedStyle(el);
  const line = Number.parseFloat(style.lineHeight) || 24;
  const padding = Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom) || 0;
  const max = line * maxLines + padding;
  el.style.height = "auto";
  const height = Math.min(el.scrollHeight, max);
  el.style.height = `${height}px`;
  el.style.overflowY = el.scrollHeight > max + 1 ? "auto" : "hidden";
}
export const ACCEPT =
  ".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.md,.csv,.tsv,.json,.jsonl,.yaml,.yml,.toml,.xml,.html,.css,.py,.ts,.tsx,.js,.jsx,.go,.rs,.java,.c,.cpp,.h,.sh,.sql,.log,.diff,.patch";

interface Pending {
  key: string;
  file: File;
  progress: number;
  preview?: string;
  uploaded?: AttachmentInfo;
  error?: string;
}

export interface SendPayload {
  content: string;
  mentionIds: string[];
  mentionAll: boolean;
  attachmentIds: string[];
}

type Suggestion =
  | { kind: "command"; spec: CommandSpec }
  | { kind: "agent"; agent: Agent }
  | { kind: "all" };

export function Composer({
  agents,
  commands,
  busy,
  disabled,
  onSend,
  onCommand,
  onStop,
  placeholder,
  history = [],
}: {
  /** ↑/↓로 다시 불러올 보낸 글(오래된 것 먼저). */
  history?: string[];
  agents: Agent[];
  commands: CommandSpec[];
  busy: boolean;
  disabled?: boolean;
  onSend: (payload: SendPayload) => Promise<void>;
  onCommand: (name: string, args: Record<string, string>) => Promise<void>;
  onStop: () => void;
  placeholder: string;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<Pending[]>([]);
  const [dragging, setDragging] = useState(false);
  const [active, setActive] = useState(0);
  const [caret, setCaret] = useState(0);
  const [sending, setSending] = useState(false);
  const [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const draft = useRef("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const enabled = agents.filter((a) => a.enabled);

  // 글이 바뀔 때마다(입력·붙여넣기·보낸 뒤 비우기) 높이를 맞춘다.
  useLayoutEffect(() => {
    if (inputRef.current) fitTextarea(inputRef.current);
  }, [text]);

  useEffect(() => () => files.forEach((f) => f.preview && URL.revokeObjectURL(f.preview)), []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 자동완성 ────────────────────────────────────────────────────────────
  const suggestions: Suggestion[] = useMemo(() => {
    const before = text.slice(0, caret);
    if (/^\/[\w-]*$/.test(before)) {
      const q = before.slice(1).toLowerCase();
      return commands.filter((c) => c.name.startsWith(q)).map((spec) => ({ kind: "command" as const, spec }));
    }
    const at = /(^|\s)@([^\s@]*)$/.exec(before);
    if (at) {
      const q = (at[2] ?? "").toLowerCase();
      const list: Suggestion[] = enabled
        .filter((a) => a.name.toLowerCase().includes(q) || a.title.toLowerCase().includes(q))
        .slice(0, 8)
        .map((agent) => ({ kind: "agent" as const, agent }));
      if (!text.startsWith("/") && "all".startsWith(q)) list.push({ kind: "all" });
      return list;
    }
    return [];
  }, [text, caret, commands, enabled]);
  useEffect(() => setActive(0), [suggestions.length]);

  const applySuggestion = (s: Suggestion) => {
    const before = text.slice(0, caret);
    const after = text.slice(caret);
    let next: string;
    if (s.kind === "command") next = `/${s.spec.name} ${after.trimStart()}`;
    else {
      const name = s.kind === "all" ? "All" : s.agent.name;
      next = before.replace(/@([^\s@]*)$/, `@${name} `) + after;
    }
    setText(next);
    const pos = s.kind === "command" ? s.spec.name.length + 2 : next.length - after.length;
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(pos, pos);
      setCaret(pos);
    });
  };

  // ── 첨부 ────────────────────────────────────────────────────────────────
  const addFiles = (list: FileList | File[]) => {
    const incoming = Array.from(list);
    if (files.length + incoming.length > MAX_FILES) {
      toast.error(`한 번에 ${MAX_FILES}개까지 첨부할 수 있습니다.`);
      return;
    }
    for (const file of incoming) {
      if (file.size > MAX_BYTES) {
        toast.error(`${file.name}: 20MB를 넘는 파일은 첨부할 수 없습니다.`);
        continue;
      }
      const key = `${file.name}-${file.size}-${Math.random()}`;
      const preview = file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined;
      setFiles((fs) => [...fs, { key, file, progress: 0, preview }]);
      uploadFile(file, (progress) => setFiles((fs) => fs.map((f) => (f.key === key ? { ...f, progress } : f))))
        .then((uploaded) => setFiles((fs) => fs.map((f) => (f.key === key ? { ...f, uploaded, progress: 1 } : f))))
        .catch((error: Error) => setFiles((fs) => fs.map((f) => (f.key === key ? { ...f, error: error.message } : f))));
    }
  };
  const removeFile = (p: Pending) => {
    if (p.preview) URL.revokeObjectURL(p.preview);
    setFiles((fs) => fs.filter((f) => f.key !== p.key));
    if (p.uploaded) void api(`/attachments/${p.uploaded.id}`, { method: "DELETE" }).catch(() => undefined);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };
  const onPaste = (e: ClipboardEvent) => {
    if (e.clipboardData.files.length) {
      e.preventDefault();
      addFiles(e.clipboardData.files);
    }
  };

  // ── 보내기 ──────────────────────────────────────────────────────────────
  const uploading = files.some((f) => !f.uploaded && !f.error);
  const submit = async () => {
    const content = text.trim();
    if (!content || sending || uploading || disabled) return;
    setSending(true);
    try {
      if (isCommandInput(content)) {
        const [, name = "", rest = ""] = /^\/([\w-]+)\s*([\s\S]*)$/.exec(content) ?? [];
        const spec = commands.find((c) => c.name === name);
        if (!spec) {
          toast.error(`알 수 없는 명령입니다: /${name}. /help로 목록을 보세요.`);
          return;
        }
        await onCommand(name, parseArgs(spec, rest, enabled));
      } else {
        const mentionIds = enabled.filter((a) => content.includes(`@${a.name}`)).map((a) => a.id);
        await onSend({
          content,
          mentionIds,
          mentionAll: /(^|\s)@All(\s|$)/.test(content),
          attachmentIds: files.flatMap((f) => (f.uploaded ? [f.uploaded.id] : [])),
        });
        files.forEach((f) => f.preview && URL.revokeObjectURL(f.preview));
        setFiles([]);
      }
      setText("");
      setHistoryIndex(null);
      draft.current = "";
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (suggestions.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => (i + (e.key === "ArrowDown" ? 1 : suggestions.length - 1)) % suggestions.length);
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        applySuggestion(suggestions[active]!);
        return;
      }
      if (e.key === "Escape") {
        setCaret(-1);
        return;
      }
    }
    if ((e.key === "ArrowUp" || e.key === "ArrowDown") && !e.shiftKey && !e.altKey && !e.metaKey && !e.ctrlKey) {
      const el = e.currentTarget;
      const before = el.value.slice(0, el.selectionStart);
      const after = el.value.slice(el.selectionEnd);
      // 여러 줄 글 안에서는 줄 이동을 막지 않는다: 첫 줄에서 ↑, 마지막 줄에서 ↓일 때만 기록을 탐색한다.
      const atEdge = e.key === "ArrowUp" ? !before.includes("\n") : !after.includes("\n");
      const next = atEdge ? stepHistory(history, historyIndex, e.key === "ArrowUp" ? "up" : "down") : null;
      if (next) {
        e.preventDefault();
        if (historyIndex === null) draft.current = text;
        const value = next.index === null ? draft.current : history[next.index]!;
        setHistoryIndex(next.index);
        setText(value);
        window.requestAnimationFrame(() => {
          const pos = e.key === "ArrowUp" ? 0 : value.length;
          inputRef.current?.setSelectionRange(pos, pos);
          setCaret(pos);
        });
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  const command = text.startsWith("/") ? commands.find((c) => text.startsWith(`/${c.name} `) || text === `/${c.name}`) : undefined;

  return (
    <div
      className="relative px-4 pb-4"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      {suggestions.length > 0 ? (
        <ul
          role="listbox"
          aria-label={suggestions[0]?.kind === "command" ? "명령어" : "에이전트"}
          className="overlay-in absolute right-4 bottom-full left-4 mb-1 max-h-72 overflow-y-auto rounded-md border border-border-strong bg-surface-2 p-1 shadow-overlay"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.kind === "command" ? s.spec.name : s.kind === "agent" ? s.agent.id : "all"}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                applySuggestion(s);
              }}
              onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm", i === active && "bg-surface-3")}
            >
              {s.kind === "command" ? (
                <>
                  <span className="w-24 shrink-0 font-mono text-xs text-primary-text">/{s.spec.name}</span>
                  <span className="min-w-0 truncate text-muted">{s.spec.description}</span>
                </>
              ) : s.kind === "agent" ? (
                <>
                  <AgentAvatar id={s.agent.id} lead={s.agent.is_lead} size={22} />
                  <span>{s.agent.name}</span>
                  <span className="truncate text-xs text-faint">{s.agent.title}</span>
                </>
              ) : (
                <>
                  <span className="grid size-[22px] place-items-center rounded-md bg-primary-soft text-2xs text-primary-text">All</span>
                  <span>@All</span>
                  <span className="text-xs text-faint">조직 전체 공지(CEO가 받아 분배)</span>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <div
        className={cn(
          "flex flex-col gap-2 rounded-lg border bg-surface-2 p-2 transition-colors",
          dragging ? "border-primary-text bg-primary-soft" : "border-border-strong focus-within:border-ring",
        )}
      >
        {files.length ? (
          <ul className="flex flex-wrap gap-2 px-1 pt-1" aria-label="첨부 파일">
            {files.map((f) => (
              <li key={f.key} className="relative flex items-center gap-2 rounded-md border border-border bg-surface-1 py-1 pr-1 pl-1.5 text-xs">
                {f.preview ? (
                  <img src={f.preview} alt="" width={32} height={32} className="size-8 rounded-sm object-cover" />
                ) : (
                  <FileText className="size-4 text-muted" aria-hidden />
                )}
                <span className="flex min-w-0 flex-col">
                  <span className="max-w-40 truncate">{f.file.name}</span>
                  <span className={cn("text-2xs", f.error ? "text-danger" : "text-faint")}>
                    {f.error ?? (f.uploaded ? formatBytes(f.file.size) : `올리는 중 ${Math.round(f.progress * 100)}%`)}
                  </span>
                </span>
                {!f.uploaded && !f.error ? <Loader2 className="size-3.5 animate-spin text-faint" aria-hidden /> : null}
                <IconButton label={`${f.file.name} 첨부 취소`} size="icon-sm" className="size-6" onClick={() => removeFile(f)}>
                  <X />
                </IconButton>
              </li>
            ))}
          </ul>
        ) : null}
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => {
            setHistoryIndex(null);
            setText(e.target.value);
            setCaret(e.target.selectionStart);
          }}
          onSelect={(e) => setCaret(e.currentTarget.selectionStart)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={1}
          disabled={disabled}
          placeholder={placeholder}
          aria-label="메시지"
          data-composer-input
          className="resize-none overflow-y-hidden bg-transparent px-1.5 py-1 text-base leading-6 placeholder:text-faint focus:outline-none"
        />
        <div className="flex items-center gap-1">
          <input ref={fileRef} type="file" multiple accept={ACCEPT} hidden onChange={(e) => e.target.files && addFiles(e.target.files)} />
          <IconButton label="파일 첨부" size="icon-sm" onClick={() => fileRef.current?.click()} disabled={disabled}>
            <Paperclip />
          </IconButton>
          <span className="truncate px-1 text-2xs text-faint">
            {command ? `${command.usage} — ${command.description}` : "/ 명령 · @ 에이전트 지정 · ↑↓ 보낸 글 · Shift+Enter 줄바꿈"}
          </span>
          <span className="ml-auto" />
          {busy ? (
            <IconButton label="실행 중지" variant="secondary" size="icon-sm" onClick={onStop}>
              <Square />
            </IconButton>
          ) : null}
          <IconButton
            label="보내기"
            variant="primary"
            size="icon-sm"
            onClick={() => void submit()}
            disabled={!text.trim() || sending || uploading || disabled}
          >
            <SendHorizontal />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

/** 명령 인자 해석: agent 인자는 첫 @이름, 나머지 text 인자는 남은 글 전체. */
export function parseArgs(spec: CommandSpec, rest: string, agents: Agent[]): Record<string, string> {
  const args: Record<string, string> = {};
  let remaining = rest.trim();
  for (const arg of spec.args) {
    if (arg.kind === "agent") {
      const found = agents
        .slice()
        .sort((a, b) => b.name.length - a.name.length)
        .find((a) => remaining.startsWith(`@${a.name}`));
      if (found) {
        args[arg.name] = found.id;
        remaining = remaining.slice(found.name.length + 1).trim();
      } else {
        const [token = "", ...others] = remaining.split(/\s+/);
        args[arg.name] = token;
        remaining = others.join(" ");
      }
    } else {
      args[arg.name] = remaining;
      remaining = "";
    }
  }
  return args;
}
