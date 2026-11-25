/**
 * 에이전트 설정 편집기. 설계 모드(명세의 SpecAgent)와 운영 모드(Agent Detail)가 함께 쓴다.
 * '추천'(recommended_*)과 '실제 허용'(allowed_*)을 분리해 보여 준다. AI 권한 제안은 사용자가 수락해야 적용된다.
 */

import { AlertTriangle, Check, ShieldAlert, Trash2 } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Switch, Textarea } from "@/components/ui/form";
import type { AgentPermissions, ApprovalGroup, Capability, Recommendation, SpecAgent, SpecDepartment } from "@/lib/api";
import { cn } from "@/lib/utils";

export const APPROVAL_LABELS: Record<ApprovalGroup, string> = {
  shell: "셸 명령 실행",
  file_write: "파일 생성·수정",
  file_delete: "파일 삭제",
  network: "웹 검색·가져오기",
  delegate: "하위 에이전트 위임",
};

const REC_STATUS: Record<Recommendation["status"], { label: string; className: string }> = {
  available: { label: "사용 가능", className: "text-success" },
  approval_required: { label: "허용 필요", className: "text-warning" },
  install_required: { label: "설치·연결 필요", className: "text-muted" },
  unsupported: { label: "아직 지원 안 됨", className: "text-faint" },
};

function lines(value: string[]): string {
  return value.join("\n");
}
function unlines(value: string): string[] {
  return value
    .split("\n")
    .map((v) => v.trim())
    .filter(Boolean);
}

export function AgentEditor({
  agent,
  agents,
  departments,
  capabilities,
  recommendations = [],
  onChange,
  onDelete,
  onAcceptSuggestion,
  footer,
}: {
  agent: SpecAgent;
  agents: SpecAgent[];
  departments: SpecDepartment[];
  capabilities: Capability[];
  recommendations?: Recommendation[];
  onChange: (next: SpecAgent) => void;
  onDelete?: () => void;
  onAcceptSuggestion?: () => void;
  footer?: ReactNode;
}) {
  // 긴 텍스트는 입력 중에는 로컬로 두고 포커스를 떠날 때 반영한다(입력마다 저장 요청을 보내지 않게).
  const [draft, setDraft] = useState(agent);
  useEffect(() => setDraft(agent), [agent]);
  const commit = (next: Partial<SpecAgent>) => onChange({ ...agent, ...next });
  const perms = agent.permissions;
  const setPerms = (next: Partial<AgentPermissions>) => commit({ permissions: { ...perms, ...next } });
  const managers = agents.filter((a) => a.key !== agent.key);
  const skills = capabilities.filter((c) => c.kind === "skill");
  const mcps = capabilities.filter((c) => c.kind === "mcp");
  const myRecs = recommendations.filter((r) => r.agent === agent.key);

  return (
    <div className="flex flex-col gap-6">
      <Group title="기본 정보">
        <div className="grid grid-cols-2 gap-3">
          <Field label="이름">
            {(id) => (
              <Input
                id={id}
                value={draft.name}
                maxLength={80}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                onBlur={() => draft.name.trim() && draft.name !== agent.name && commit({ name: draft.name.trim() })}
              />
            )}
          </Field>
          <Field label="직책">
            {(id) => (
              <Input
                id={id}
                value={draft.title}
                maxLength={80}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                onBlur={() => draft.title !== agent.title && commit({ title: draft.title })}
              />
            )}
          </Field>
          <Field label="부서">
            {(id) => (
              <Select id={id} value={agent.department ?? ""} onChange={(e) => commit({ department: e.target.value || null })}>
                <option value="">부서 없음</option>
                {departments.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="상위 관리자">
            {(id) => (
              <Select
                id={id}
                value={agent.reports_to ?? ""}
                disabled={agent.is_lead}
                onChange={(e) => commit({ reports_to: e.target.value || null })}
              >
                <option value="">{agent.is_lead ? "CEO는 상위 관리자가 없습니다" : "없음"}</option>
                {managers.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.name}
                    {m.title ? ` · ${m.title}` : ""}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        <Field label="역할" hint="이 에이전트가 조직에서 맡는 일을 한두 문장으로.">
          {(id) => (
            <Textarea
              id={id}
              className="min-h-16"
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value })}
              onBlur={() => draft.role !== agent.role && commit({ role: draft.role })}
            />
          )}
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="책임(한 줄에 하나)">
            {(id) => (
              <Textarea
                id={id}
                className="min-h-20"
                value={lines(draft.responsibilities)}
                onChange={(e) => setDraft({ ...draft, responsibilities: e.target.value.split("\n") })}
                onBlur={() => commit({ responsibilities: unlines(lines(draft.responsibilities)) })}
              />
            )}
          </Field>
          <Field label="전문 분야(한 줄에 하나)">
            {(id) => (
              <Textarea
                id={id}
                className="min-h-20"
                value={lines(draft.expertise)}
                onChange={(e) => setDraft({ ...draft, expertise: e.target.value.split("\n") })}
                onBlur={() => commit({ expertise: unlines(lines(draft.expertise)) })}
              />
            )}
          </Field>
        </div>
        <Field label="시스템 지시사항" hint="Claude Code 기본 프롬프트 뒤에 덧붙습니다. 작업 방식과 결과물 형식을 적으세요.">
          {(id) => (
            <Textarea
              id={id}
              className="min-h-28 font-mono text-xs"
              value={draft.instructions}
              onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
              onBlur={() => draft.instructions !== agent.instructions && commit({ instructions: draft.instructions })}
            />
          )}
        </Field>
        <Switch
          label="활성화"
          description="끄면 대화·위임 대상에서 빠지고 사무실에 나오지 않습니다."
          checked={agent.enabled}
          onCheckedChange={(enabled) => commit({ enabled })}
        />
      </Group>

      <Group title="권한" icon={<ShieldAlert className="size-4 text-warning" aria-hidden />}>
        {agent.permission_suggestion ? (
          <SuggestionNotice
            current={perms}
            suggestion={agent.permission_suggestion}
            onAccept={onAcceptSuggestion}
          />
        ) : null}
        <p className="text-xs text-faint">
          이 설정은 Claude Code 권한을 좁히기만 합니다. 모든 도구 호출은 실행 전에 이 정책으로 검사됩니다.
        </p>
        <div className="flex flex-col gap-3">
          <Switch label="셸 명령" description="Bash로 명령을 실행합니다(테스트·빌드 등)." checked={perms.allow_shell} onCheckedChange={(v) => setPerms({ allow_shell: v })} />
          <Switch label="파일 생성·수정" checked={perms.allow_file_write} onCheckedChange={(v) => setPerms({ allow_file_write: v })} />
          <Switch label="파일 삭제" description="셸 명령 허용이 함께 필요합니다." checked={perms.allow_file_delete} onCheckedChange={(v) => setPerms({ allow_file_delete: v })} />
          <Switch label="웹 검색·가져오기" checked={perms.allow_network} onCheckedChange={(v) => setPerms({ allow_network: v })} />
          <Switch label="하위 에이전트 위임" description="Claude Code의 하위 에이전트(Agent 도구)를 쓸 수 있습니다." checked={perms.can_delegate} onCheckedChange={(v) => setPerms({ can_delegate: v })} />
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-xs font-medium text-muted">실행 전에 내 승인 받기</legend>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
            {(Object.keys(APPROVAL_LABELS) as ApprovalGroup[]).map((group) => (
              <label key={group} className="flex cursor-pointer items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-3.5 accent-[var(--primary)]"
                  checked={perms.require_approval.includes(group)}
                  onChange={(e) =>
                    setPerms({
                      require_approval: e.target.checked
                        ? [...perms.require_approval, group]
                        : perms.require_approval.filter((g) => g !== group),
                    })
                  }
                />
                {APPROVAL_LABELS[group]}
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Claude Code 권한 모드" hint="plan: 계획만 세우고 실행하지 않음. acceptEdits: 파일 편집을 묻지 않음(승인 설정이 있으면 그것이 우선).">
          {(id) => (
            <Select id={id} value={perms.permission_mode} onChange={(e) => setPerms({ permission_mode: e.target.value as AgentPermissions["permission_mode"] })}>
              <option value="default">default — 필요할 때 확인</option>
              <option value="plan">plan — 계획 전용</option>
              <option value="acceptEdits">acceptEdits — 편집 자동 허용</option>
            </Select>
          )}
        </Field>
      </Group>

      <Group title="Skills·MCP">
        {myRecs.length > 0 ? (
          <div className="flex flex-col gap-1.5">
            <p className="text-xs font-medium text-muted">추천(아직 적용 아님)</p>
            <ul className="flex flex-col gap-1">
              {myRecs.map((r) => (
                <li key={`${r.kind}-${r.name}`} className="flex items-center justify-between gap-2 text-sm">
                  <span className="truncate">
                    <span className="mr-1.5 text-2xs text-faint">{r.kind === "skill" ? "Skill" : "MCP"}</span>
                    {r.name}
                  </span>
                  <span className={cn("text-xs", REC_STATUS[r.status].className)}>{REC_STATUS[r.status].label}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <CapabilityChecklist
          title="허용된 Skills"
          empty="이 컴퓨터에서 찾은 Skill이 없습니다. ~/.claude/skills 또는 프로젝트 .claude/skills에 설치하세요."
          items={skills}
          selected={agent.allowed_skills}
          onChange={(allowed_skills) => commit({ allowed_skills })}
        />
        <CapabilityChecklist
          title="허용된 MCP 서버"
          empty="설정된 MCP 서버가 없습니다."
          items={mcps}
          selected={agent.allowed_mcp_servers}
          onChange={(allowed_mcp_servers) => commit({ allowed_mcp_servers })}
          note="MCP 서버를 에이전트 실행에 실제로 연결하는 기능은 Phase 4에서 구현합니다. 지금은 허용 목록만 저장됩니다."
        />
      </Group>

      {footer}
      {onDelete && !agent.is_lead ? (
        <div className="border-t border-border pt-4">
          <Button variant="ghost" size="sm" className="text-danger hover:text-danger" onClick={onDelete}>
            <Trash2 /> 이 에이전트 삭제
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function Group({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold text-muted">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  );
}

function CapabilityChecklist({
  title,
  empty,
  items,
  selected,
  onChange,
  note,
}: {
  title: string;
  empty: string;
  items: Capability[];
  selected: string[];
  onChange: (next: string[]) => void;
  note?: string;
}) {
  return (
    <fieldset className="flex flex-col gap-1.5">
      <legend className="mb-1 text-xs font-medium text-muted">{title}</legend>
      {items.length === 0 ? <p className="text-xs text-faint">{empty}</p> : null}
      <div className="flex max-h-44 flex-col gap-1 overflow-y-auto">
        {items.map((c) => (
          <label key={c.id} className="flex cursor-pointer items-start gap-2 text-sm" title={c.description}>
            <input
              type="checkbox"
              className="mt-1 size-3.5 accent-[var(--primary)]"
              checked={selected.includes(c.id)}
              onChange={(e) => onChange(e.target.checked ? [...selected, c.id] : selected.filter((id) => id !== c.id))}
            />
            <span className="min-w-0">
              <span className="block truncate">{c.name}</span>
              <span className="block truncate text-2xs text-faint">
                {c.scope} · {c.description || c.source}
              </span>
            </span>
          </label>
        ))}
      </div>
      {note ? <p className="text-2xs text-faint">{note}</p> : null}
    </fieldset>
  );
}

function SuggestionNotice({
  current,
  suggestion,
  onAccept,
}: {
  current: AgentPermissions;
  suggestion: AgentPermissions;
  onAccept?: () => void;
}) {
  const diffs: string[] = [];
  const flag = (key: keyof AgentPermissions, label: string) => {
    if (suggestion[key] && !current[key]) diffs.push(`${label} 허용`);
  };
  flag("allow_shell", "셸 명령");
  flag("allow_file_write", "파일 수정");
  flag("allow_file_delete", "파일 삭제");
  flag("allow_network", "네트워크");
  flag("can_delegate", "위임");
  const dropped = current.require_approval.filter((g) => !suggestion.require_approval.includes(g));
  if (dropped.length) diffs.push(`승인 생략: ${dropped.map((g) => APPROVAL_LABELS[g]).join(", ")}`);
  if (suggestion.permission_mode !== current.permission_mode) diffs.push(`모드 ${suggestion.permission_mode}`);
  return (
    <div className="flex flex-col gap-2 rounded-md border border-[#5c4a22] bg-[#2a2213] px-3 py-2.5 text-sm">
      <span className="flex items-center gap-1.5 font-medium text-warning">
        <AlertTriangle className="size-4" aria-hidden /> AI가 권한 확대를 제안했습니다
      </span>
      <ul className="list-disc pl-5 text-xs text-muted">
        {diffs.map((d) => (
          <li key={d}>{d}</li>
        ))}
      </ul>
      <p className="text-xs text-faint">수락하기 전까지 아래 현재 권한이 적용됩니다.</p>
      {onAccept ? (
        <Button size="sm" variant="warning" className="w-fit" onClick={onAccept}>
          <Check /> 제안 수락
        </Button>
      ) : null}
    </div>
  );
}
