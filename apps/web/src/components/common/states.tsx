import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Hand,
  Loader2,
  MoonStar,
  Sparkles,
  Telescope,
  XCircle,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";

import type { AgentStatus as Status } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── 에이전트 상태 ─────────────────────────────────────────────────────────

export const STATUS_META: Record<Status, { label: string; icon: typeof CircleDashed; color: string; pulse?: boolean }> = {
  idle: { label: "대기", icon: CircleDashed, color: "var(--status-idle)" },
  thinking: { label: "생각 중", icon: Sparkles, color: "var(--status-thinking)", pulse: true },
  working: { label: "작업 중", icon: Wrench, color: "var(--status-working)", pulse: true },
  waiting: { label: "승인 대기", icon: Hand, color: "var(--status-waiting)" },
  reviewing: { label: "검토 중", icon: Telescope, color: "var(--status-reviewing)", pulse: true },
  completed: { label: "완료", icon: CheckCircle2, color: "var(--status-completed)" },
  failed: { label: "실패", icon: XCircle, color: "var(--status-failed)" },
  offline: { label: "꺼짐", icon: MoonStar, color: "var(--status-offline)" },
};

/** 상태는 색만으로 구분하지 않는다: 아이콘 + 글자 + 색. compact면 아이콘만(이때 title로 글자 제공). */
export function AgentStatus({ status, compact = false, className }: { status: Status; compact?: boolean; className?: string }) {
  const meta = STATUS_META[status] ?? STATUS_META.idle;
  const Icon = meta.icon;
  return (
    <span
      className={cn("inline-flex items-center gap-1 text-xs whitespace-nowrap", className)}
      style={{ color: meta.color }}
      title={compact ? meta.label : undefined}
    >
      {/* key로 상태가 바뀔 때만 다시 그려 전환 모션을 준다. */}
      <span key={status} className="status-in inline-flex">
        <Icon className={cn("size-3.5", meta.pulse && "status-pulse")} aria-hidden />
      </span>
      {compact ? <span className="sr-only">{meta.label}</span> : meta.label}
    </span>
  );
}

// ── 페이지 머리 ───────────────────────────────────────────────────────────

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-3 px-6 pt-6 pb-4", className)}>
      <div className="min-w-0">
        <h1 className="text-lg font-semibold">{title}</h1>
        {description ? <p className="mt-1 max-w-[70ch] text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}

// ── 빈·로딩·오류 상태 ─────────────────────────────────────────────────────

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-2 rounded-lg border border-dashed border-border-strong px-5 py-6", className)}>
      {icon ? <div className="text-faint [&_svg]:size-5">{icon}</div> : null}
      <p className="text-sm font-medium">{title}</p>
      {children ? <div className="max-w-[60ch] text-sm text-muted">{children}</div> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

export function LoadingState({ label = "불러오는 중…", className }: { label?: string; className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 px-1 py-3 text-sm text-muted", className)} role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorState({ error, retry, className }: { error: unknown; retry?: () => void; className?: string }) {
  const message = error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";
  return (
    <div className={cn("flex items-start gap-2 rounded-md border border-danger-border bg-danger-surface px-3 py-2.5 text-sm", className)} role="alert">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="flex flex-col gap-1">
        <span className="text-fg">{message}</span>
        {retry ? (
          <button type="button" onClick={retry} className="w-fit cursor-pointer text-xs text-primary-text underline">
            다시 시도
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** 섹션 제목(페이지 안 구획). 카드 대신 제목 + 구분선으로 정보를 묶는다. */
export function Section({
  title,
  actions,
  children,
  className,
}: {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border pb-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function DeptChip({ name, color, className }: { name: string; color: string; className?: string }) {
  return (
    <span
      className={cn("inline-flex max-w-full items-center gap-1.5 truncate text-xs", className)}
      style={{ color: `var(--${color}, var(--text-muted))` }}
    >
      <span className="size-1.5 shrink-0 rounded-full" style={{ background: "currentColor" }} aria-hidden />
      <span className="truncate">{name}</span>
    </span>
  );
}
