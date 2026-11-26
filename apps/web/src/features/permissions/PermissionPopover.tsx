/**
 * 에이전트 이름을 누르면 뜨는 권한 팝오버(커맨드 센터 실행 패널).
 * 모드·묶음 칸·허용 규칙 요약을 보이고, 전체 편집은 에이전트 설정으로 보낸다.
 * 저장·확인 창은 부모의 usePermissionChange를 쓴다(확인 창이 떠 있는 동안 팝오버는 닫히지 않는다).
 */

import { X } from "lucide-react";
import { Link } from "react-router";

import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@/components/ui/overlay";
import type { Agent } from "@/lib/api";
import { AUTO_DESCRIPTION, GROUPS, GROUP_LABELS } from "@/lib/permissions";
import { cn } from "@/lib/utils";

import { CellLegend, ModeSelect, PermissionCell } from "./PermissionParts";
import type { RequestPermissionChange } from "./usePermissionChange";

const SUMMARY_RULES = 3;

export function PermissionPopover({
  agent,
  request,
  confirming,
  pending,
  className,
}: {
  agent: Agent;
  request: RequestPermissionChange;
  confirming: boolean;
  /** 저장·다시 불러오기 중이면 칸과 모드 선택을 잠근다. */
  pending: boolean;
  className?: string;
}) {
  const perms = agent.permissions;
  const rules = perms.allow_rules;
  return (
    <Popover>
      <PopoverTrigger
        title={`${agent.name} 권한 보기`}
        className={cn(
          "min-w-0 cursor-pointer truncate rounded-sm text-left underline decoration-border-strong decoration-dotted underline-offset-[3px] hover:text-primary-text",
          className,
        )}
      >
        {agent.name}
      </PopoverTrigger>
      <PopoverContent
        align="start"
        side="left"
        aria-label={`${agent.name} 권한`}
        onInteractOutside={(event) => confirming && event.preventDefault()}
        onFocusOutside={(event) => confirming && event.preventDefault()}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="truncate text-sm font-semibold">{agent.name} 권한</h3>
          <PopoverClose aria-label="닫기" title="닫기" className="cursor-pointer rounded-md p-1 text-muted hover:bg-surface-3 hover:text-fg">
            <X className="size-3.5" aria-hidden />
          </PopoverClose>
        </div>
        <div className="mt-2 flex items-center justify-between gap-3 text-sm">
          <span className="text-muted">모드</span>
          <ModeSelect
            agentName={agent.name}
            value={perms.permission_mode}
            disabled={pending}
            onChange={(permission_mode) => request([{ agent, next: { ...perms, permission_mode } }])}
          />
        </div>
        {perms.permission_mode === "auto" ? <p className="mt-1 text-2xs text-faint">{AUTO_DESCRIPTION}</p> : null}
        <ul className="mt-2 flex flex-col gap-1.5 border-t border-border pt-2">
          {GROUPS.map((group) => (
            <li key={group} className="flex items-start justify-between gap-3 text-sm">
              <span className="pt-1 text-muted">{GROUP_LABELS[group]}</span>
              <PermissionCell agentName={agent.name} group={group} perms={perms} disabled={pending} onChange={(next) => request([{ agent, next }])} />
            </li>
          ))}
        </ul>
        <CellLegend className="mt-2" />
        <div className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
          <span className="text-xs text-muted">허용 규칙 {rules.length}개</span>
          {rules.length === 0 ? <span className="text-2xs text-faint">묻지 않고 허용하는 규칙이 없습니다.</span> : null}
          <ul className="flex flex-col gap-0.5">
            {rules.slice(0, SUMMARY_RULES).map((rule) => (
              <li key={rule}>
                <code className="block truncate font-mono text-2xs text-muted" title={rule}>
                  {rule}
                </code>
              </li>
            ))}
          </ul>
          {rules.length > SUMMARY_RULES ? <span className="text-2xs text-faint">외 {rules.length - SUMMARY_RULES}개</span> : null}
        </div>
        <Link
          to={`/agents/${agent.id}?tab=settings`}
          className="mt-2 inline-block text-xs text-primary-text underline underline-offset-[3px]"
        >
          전체 편집
        </Link>
      </PopoverContent>
    </Popover>
  );
}
