/**
 * 조직 화면의 권한 표. 행 = 에이전트, 열 = 모드·셸·파일 수정·삭제·네트워크·위임·MCP.
 * 칸을 누르면 허용 → 승인 필요 → 금지로 바뀌고 바로 저장한다(넓어지는 변경은 확인 창).
 * 위쪽 프리셋은 선택한 에이전트(부서 단위로도 선택 가능)에 한꺼번에 적용한다.
 */

import { useState } from "react";
import { Link } from "react-router";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { DeptChip } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form";
import type { Organization } from "@/lib/api";
import { GROUPS, GROUP_LABELS, PRESETS, type PresetId, applyPreset } from "@/lib/permissions";

import { CellLegend, ModeSelect, PermissionCell } from "./PermissionParts";
import { usePermissionChange } from "./usePermissionChange";

export function PermissionMatrix({ org }: { org: Organization }) {
  const { request, dialog, pending } = usePermissionChange();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState("");
  const depts = new Map(org.departments.map((d) => [d.id, d]));
  // 조직이 바뀌어 사라진 에이전트는 선택에서 뺀다.
  const selected = org.agents.filter((a) => picked.has(a.id));
  const allPicked = selected.length === org.agents.length && org.agents.length > 0;

  const pickScope = (value: string) => {
    setScope(value);
    if (value === "all") setPicked(new Set(org.agents.map((a) => a.id)));
    else if (value === "none") setPicked(new Set());
    else if (value.startsWith("dept:")) setPicked(new Set(org.agents.filter((a) => a.department_id === value.slice(5)).map((a) => a.id)));
  };
  const toggle = (id: string, on: boolean) => {
    setScope("");
    setPicked((current) => {
      const next = new Set(current);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };
  const preset = (id: PresetId, label: string) =>
    request(
      selected.map((agent) => ({ agent, next: applyPreset(agent.permissions, id) })),
      { label: `프리셋 '${label}'을(를) ${selected.length}명에 적용` },
    );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2" role="group" aria-label="프리셋 적용">
        <Select aria-label="적용 대상 선택" className="h-8 w-48" value={scope} onChange={(e) => pickScope(e.target.value)}>
          <option value="">직접 선택</option>
          <option value="all">전체 에이전트</option>
          <option value="none">선택 해제</option>
          <optgroup label="부서 전체">
            {org.departments.map((d) => (
              <option key={d.id} value={`dept:${d.id}`}>
                {d.name}
              </option>
            ))}
          </optgroup>
        </Select>
        <span className="text-xs text-muted" aria-live="polite">
          선택 {selected.length}명에 적용
        </span>
        {PRESETS.map((p) => (
          <Button key={p.id} size="sm" title={p.description} disabled={selected.length === 0 || pending} onClick={() => preset(p.id, p.label)}>
            {p.label}
          </Button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[920px] text-left text-sm">
          <caption className="sr-only">에이전트별 권한. 칸을 누르면 허용, 승인 필요, 금지 순서로 바뀝니다.</caption>
          <thead className="text-2xs text-faint">
            <tr>
              <th scope="col" className="w-8 pb-2 font-medium">
                <input
                  type="checkbox"
                  aria-label="전체 에이전트 선택"
                  className="size-3.5 accent-[var(--primary)]"
                  checked={allPicked}
                  onChange={(e) => pickScope(e.target.checked ? "all" : "none")}
                />
              </th>
              <th scope="col" className="pb-2 font-medium">에이전트</th>
              <th scope="col" className="pb-2 font-medium">모드</th>
              {GROUPS.map((group) => (
                <th key={group} scope="col" className="pb-2 font-medium">
                  {GROUP_LABELS[group]}
                </th>
              ))}
              <th scope="col" className="pb-2 font-medium">허용 규칙</th>
            </tr>
          </thead>
          <tbody>
            {org.agents.map((a) => {
              const dept = a.department_id ? depts.get(a.department_id) : undefined;
              return (
                <tr key={a.id} className="border-t border-border align-top" data-agent={a.name}>
                  <td className="py-2.5">
                    <input
                      type="checkbox"
                      aria-label={`${a.name} 선택`}
                      className="mt-1.5 size-3.5 accent-[var(--primary)]"
                      checked={picked.has(a.id)}
                      onChange={(e) => toggle(a.id, e.target.checked)}
                    />
                  </td>
                  <th scope="row" className="py-2 pr-3 font-normal">
                    <span className="flex items-center gap-2">
                      <AgentAvatar id={a.id} lead={a.is_lead} dim={!a.enabled} size={26} />
                      <span className="min-w-0">
                        <span className="block truncate">{a.name}</span>
                        {dept ? <DeptChip name={dept.name} color={dept.color} /> : <span className="text-2xs text-faint">부서 없음</span>}
                      </span>
                    </span>
                  </th>
                  <td className="py-2 pr-3">
                    <ModeSelect
                      agentName={a.name}
                      value={a.permissions.permission_mode}
                      disabled={pending}
                      onChange={(permission_mode) => request([{ agent: a, next: { ...a.permissions, permission_mode } }])}
                    />
                  </td>
                  {GROUPS.map((group) => (
                    <td key={group} className="py-2 pr-3">
                      <PermissionCell
                        agentName={a.name}
                        group={group}
                        perms={a.permissions}
                        disabled={pending}
                        onChange={(next) => request([{ agent: a, next }])}
                      />
                    </td>
                  ))}
                  <td className="py-2.5 text-xs">
                    <Link
                      to={`/agents/${a.id}?tab=settings`}
                      className="text-primary-text underline underline-offset-[3px]"
                      aria-label={`${a.name} 허용 규칙 ${a.permissions.allow_rules.length}개, 전체 편집`}
                    >
                      {a.permissions.allow_rules.length}개 · 편집
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex max-w-[70ch] flex-col gap-1 text-xs text-faint">
        <CellLegend />
        <p>
          권한을 넓히는 변경(금지 → 승인 필요·허용, 승인 필요 → 허용, 모드 상향, auto 켜기)은 확인 창을 거칩니다. 셸을 켜서 삭제가 함께 풀리는
          경우도 확인 창에 나옵니다.
        </p>
        <p>auto 모드에서는 '승인 필요' 칸 대신 Claude가 판단합니다. 작업 폴더 밖 경로는 어떤 모드에서도 승인을 받고, 금지한 도구는 쓸 수 없습니다.</p>
        <p>삭제는 셸 명령으로 실행되므로 셸이 금지면 함께 막힙니다.</p>
        <p>MCP에는 금지 칸이 없습니다. 서버를 쓸 수 있는지는 에이전트 설정의 '허용된 MCP 서버'로 정합니다.</p>
        <p>프리셋은 위임·작업 범위·허용 규칙을 바꾸지 않습니다.</p>
      </div>
      {dialog}
    </div>
  );
}
