/** 권한 표·팝오버·조직도가 함께 쓰는 작은 표시 요소: 3상태 칸 버튼, 모드 선택, 배지. 상태는 아이콘 + 글자 + 색으로 구분한다. */

import { Ban, Bot, Check, ClipboardList, Hand } from "lucide-react";

import { Select } from "@/components/ui/form";
import type { AgentPermissions, ApprovalGroup, PermissionMode } from "@/lib/api";
import {
  BADGE_LABELS,
  type BadgeId,
  CELL_LABELS,
  type CellState,
  GROUP_LABELS,
  MODES,
  badgesOf,
  cellState,
  nextState,
  setCell,
} from "@/lib/permissions";
import { cn } from "@/lib/utils";

export const CELL_META: Record<CellState, { icon: typeof Check; className: string }> = {
  allow: { icon: Check, className: "text-success" },
  ask: { icon: Hand, className: "text-warning" },
  deny: { icon: Ban, className: "text-faint" },
};

/** 저장된 값만으로는 드러나지 않는 실제 동작(다른 설정 때문에 달라지는 경우). */
export function cellNote(perms: AgentPermissions, group: ApprovalGroup): string | null {
  const state = cellState(perms, group);
  if (group === "file_delete" && state !== "deny" && !perms.allow_shell) return "셸 금지로 막힘";
  if (state === "ask" && perms.permission_mode === "auto") return "auto: Claude 판단";
  return null;
}

/** 누를 때마다 허용 → 승인 필요 → 금지로 바뀌는 칸. 바꾼 권한을 onChange로 넘긴다(저장·확인은 호출한 쪽). */
export function PermissionCell({
  agentName,
  group,
  perms,
  onChange,
  disabled,
}: {
  agentName: string;
  group: ApprovalGroup;
  perms: AgentPermissions;
  onChange: (next: AgentPermissions) => void;
  disabled?: boolean;
}) {
  const state = cellState(perms, group);
  const next = nextState(group, state);
  const note = cellNote(perms, group);
  const Icon = CELL_META[state].icon;
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button
        type="button"
        disabled={disabled}
        data-state={state}
        aria-label={`${agentName} ${GROUP_LABELS[group]}: ${CELL_LABELS[state]}${note ? `(${note})` : ""}. 누르면 ${CELL_LABELS[next]}(으)로 바꿉니다`}
        title={`누르면 ${CELL_LABELS[next]}(으)로 바꿉니다`}
        className={cn(
          "inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border border-border-strong bg-surface-2 px-2 text-xs font-medium whitespace-nowrap",
          "transition-colors duration-[120ms] hover:bg-surface-3 disabled:cursor-default disabled:opacity-50",
          CELL_META[state].className,
        )}
        onClick={() => onChange(setCell(perms, group, next))}
      >
        <Icon className="size-3.5 shrink-0" aria-hidden />
        {CELL_LABELS[state]}
      </button>
      {note ? <span className="text-2xs text-faint">{note}</span> : null}
    </span>
  );
}

export function ModeSelect({
  agentName,
  value,
  onChange,
  className,
  disabled,
}: {
  agentName: string;
  value: PermissionMode;
  onChange: (mode: PermissionMode) => void;
  className?: string;
  disabled?: boolean;
}) {
  return (
    <Select
      aria-label={`${agentName} 권한 모드`}
      className={cn("h-7 w-32 text-xs", className)}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as PermissionMode)}
    >
      {MODES.map((mode) => (
        <option key={mode} value={mode}>
          {mode}
        </option>
      ))}
    </Select>
  );
}

const BADGE_META: Record<BadgeId, { icon: typeof Check; className: string; title: string }> = {
  auto: { icon: Bot, className: "text-primary-text", title: "auto 모드: 안전한 작업은 Claude가 판단, 작업 폴더 밖은 항상 승인" },
  plan: { icon: ClipboardList, className: "text-muted", title: "plan 모드: 계획만 세우고 실행하지 않습니다" },
  approval: { icon: Hand, className: "text-warning", title: "일부 작업은 실행 전에 내 승인을 받습니다" },
  "no-shell": { icon: Ban, className: "text-faint", title: "셸 명령을 실행할 수 없습니다" },
};

export function PermissionBadges({ perms, className }: { perms: AgentPermissions; className?: string }) {
  const badges = badgesOf(perms);
  if (badges.length === 0) return null;
  return (
    <span className={cn("flex flex-wrap items-center gap-1", className)} aria-label="권한">
      {badges.map((id) => {
        const { icon: Icon, className: color, title } = BADGE_META[id];
        return (
          <span
            key={id}
            title={title}
            data-badge={id}
            className={cn("inline-flex items-center gap-0.5 rounded-sm border border-border px-1 text-2xs leading-4 whitespace-nowrap", color)}
          >
            <Icon className="size-3 shrink-0" aria-hidden />
            {BADGE_LABELS[id]}
          </span>
        );
      })}
    </span>
  );
}

/** 표·팝오버 아래에 두는 상태 설명(아이콘의 뜻을 글로). */
export function CellLegend({ className }: { className?: string }) {
  return (
    <span className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-faint", className)}>
      {(Object.keys(CELL_META) as CellState[]).map((state) => {
        const Icon = CELL_META[state].icon;
        return (
          <span key={state} className={cn("inline-flex items-center gap-1", CELL_META[state].className)}>
            <Icon className="size-3" aria-hidden />
            {CELL_LABELS[state]}
          </span>
        );
      })}
    </span>
  );
}
