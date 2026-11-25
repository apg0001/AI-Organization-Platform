/**
 * 조직 설계 작업 공간(설계 모드). 대화·조직도·에이전트 설정·검토가 하나의 설계 상태(Design.spec)를 공유한다.
 * - 대화: 설계 담당 Claude에게 보내면 서버가 구조화된 명세를 검증·정리해 spec을 바꾼다.
 * - 조직도·설정: 직접 고친 내용은 즉시 PUT /spec. 다음 대화 턴은 이 상태를 기준으로 한다.
 * - 적용: 검토 대화상자에서 확인한 구성만 실제 조직으로 만든다.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Building, LayoutGrid, Loader2, Plus, SendHorizontal, Sparkles, Trash2, UserPlus } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { AgentEditor, APPROVAL_LABELS } from "@/components/agent/AgentEditor";
import { DeptChip, ErrorState, LoadingState } from "@/components/common/states";
import { ChartLegend, OrgChart } from "@/components/org/OrgChart";
import { Button, IconButton } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/overlay";
import { ApiError, type Design, type OrgSpec, type SpecAgent, api } from "@/lib/api";
import { useCapabilities, useCurrentOrg, useDesign } from "@/lib/queries";
import { cn } from "@/lib/utils";

const DEPT_COLORS = Array.from({ length: 8 }, (_, i) => `dept-${i + 1}`);

function newKey(prefix: string, taken: Set<string>): string {
  let i = 1;
  while (taken.has(`${prefix}${i}`)) i += 1;
  return `${prefix}${i}`;
}

export function BuilderWorkspace() {
  const { designId } = useParams();
  const design = useDesign(designId);
  const queryClient = useQueryClient();
  const caps = useCapabilities();
  const [selected, setSelected] = useState<string | null>(null);
  const [layoutVersion, setLayoutVersion] = useState(0);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [deptOpen, setDeptOpen] = useState(false);

  const saveSpec = useMutation({
    mutationFn: (spec: OrgSpec) => api<Design>(`/designs/${designId}/spec`, { method: "PUT", body: { spec } }),
    onMutate: (spec) => {
      // 낙관적 반영: 조직도가 즉시 바뀌고, 서버 검증이 실패하면 되돌린다.
      const previous = queryClient.getQueryData<Design>(["design", designId]);
      if (previous) queryClient.setQueryData(["design", designId], { ...previous, spec });
      return { previous };
    },
    onSuccess: (data) => queryClient.setQueryData(["design", designId], data),
    onError: (error, _spec, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(["design", designId], ctx.previous);
      toast.error(`반영하지 못했습니다: ${error.message}`);
    },
  });

  const accept = useMutation({
    mutationFn: (key: string) => api<Design>(`/designs/${designId}/accept-permissions/${key}`, { method: "POST" }),
    onSuccess: (data) => queryClient.setQueryData(["design", designId], data),
    onError: (error) => toast.error(error.message),
  });

  if (design.isLoading) return <LoadingState className="p-6" />;
  if (design.error || !design.data) return <ErrorState className="m-6" error={design.error} retry={() => void design.refetch()} />;
  const d = design.data;
  const spec = d.spec;
  const editable = d.status === "draft";
  const agent = spec.agents.find((a) => a.key === selected) ?? null;
  const update = (next: OrgSpec) => editable && saveSpec.mutate(next);

  const addAgent = () => {
    const key = newKey("agent", new Set(spec.agents.map((a) => a.key)));
    const lead = spec.agents.find((a) => a.is_lead);
    const fresh: SpecAgent = {
      key,
      name: "새 에이전트",
      title: "",
      department: null,
      role: "",
      responsibilities: [],
      expertise: [],
      instructions: "",
      reports_to: lead?.key ?? null,
      is_lead: false,
      enabled: true,
      permissions: lead
        ? { ...lead.permissions, allow_shell: false, allow_file_delete: false, can_delegate: false, require_approval: ["shell", "file_write", "file_delete", "mcp"] }
        : {
            permission_mode: "default",
            file_scope: [],
            allow_shell: false,
            allow_network: true,
            allow_file_write: true,
            allow_file_delete: false,
            require_approval: ["shell", "file_write", "file_delete", "mcp"],
            can_delegate: false,
          },
      permission_suggestion: null,
      recommended_skills: [],
      recommended_mcp: [],
      allowed_skills: [],
      allowed_mcp_servers: [],
      allowed_plugins: [],
      model: null,
    };
    update({ ...spec, agents: [...spec.agents, fresh] });
    setSelected(key);
  };

  const removeAgent = (key: string) => {
    const target = spec.agents.find((a) => a.key === key);
    if (!target || target.is_lead) return;
    update({
      ...spec,
      agents: spec.agents
        .filter((a) => a.key !== key)
        .map((a) => (a.reports_to === key ? { ...a, reports_to: target.reports_to } : a)),
      collaborations: spec.collaborations.filter((c) => c.source !== key && c.target !== key),
    });
    setSelected(null);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-2.5">
        <IconButton label="조직 설계 목록으로" asChild>
          <Link to="/builder">
            <ArrowLeft />
          </Link>
        </IconButton>
        <div className="flex min-w-0 flex-col">
          <h1 className="truncate text-md font-semibold">{spec.name}</h1>
          <span className="text-2xs text-faint">
            {d.organization_id ? "기존 조직 변경안" : "새 조직 설계"} · 부서 {spec.departments.length} · 에이전트 {spec.agents.length}
            {d.status !== "draft" ? " · 적용됨(읽기 전용)" : ""}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {saveSpec.isPending ? <Loader2 className="size-4 animate-spin text-faint" aria-label="저장 중" /> : null}
          <Button size="sm" variant="ghost" onClick={() => setDeptOpen(true)} disabled={!editable}>
            <Building /> 부서
          </Button>
          <Button size="sm" variant="ghost" onClick={addAgent} disabled={!editable}>
            <UserPlus /> 에이전트 추가
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setLayoutVersion((v) => v + 1)}>
            <LayoutGrid /> 자동 정렬
          </Button>
          <Button size="sm" variant="primary" onClick={() => setReviewOpen(true)} disabled={!editable || d.busy}>
            검토 후 {d.organization_id ? "적용" : "조직 생성"}
          </Button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(320px,380px)_1fr] max-lg:grid-cols-1">
        <DesignerChat design={d} />
        <div className="relative flex min-h-0 flex-col max-lg:h-[520px]">
          <div className="min-h-0 flex-1">
            <OrgChart
              spec={spec}
              selected={selected}
              onSelect={setSelected}
              onChange={editable ? update : undefined}
              layoutVersion={layoutVersion}
            />
          </div>
          <div className="border-t border-border px-4 py-2">
            <ChartLegend />
          </div>
          {agent ? (
            <aside
              className="absolute top-0 right-0 bottom-0 z-10 flex w-[400px] max-w-full flex-col border-l border-border bg-surface-1 shadow-overlay"
              aria-label={`${agent.name} 설정`}
            >
              <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
                <h2 className="truncate text-sm font-semibold">{agent.name}</h2>
                <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                  닫기
                </Button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                <fieldset disabled={!editable} className="contents">
                  <AgentEditor
                    agent={agent}
                    agents={spec.agents}
                    departments={spec.departments}
                    capabilities={caps.data ?? []}
                    recommendations={d.recommendations}
                    onChange={(next) => update({ ...spec, agents: spec.agents.map((a) => (a.key === next.key ? next : a)) })}
                    onDelete={() => removeAgent(agent.key)}
                    onAcceptSuggestion={() => accept.mutate(agent.key)}
                  />
                </fieldset>
              </div>
            </aside>
          ) : null}
        </div>
      </div>

      <DepartmentsDialog open={deptOpen} onOpenChange={setDeptOpen} spec={spec} onChange={update} />
      <ReviewDialog open={reviewOpen} onOpenChange={setReviewOpen} design={d} onChange={update} />
    </div>
  );
}

// ── 설계 대화 ─────────────────────────────────────────────────────────────

function DesignerChat({ design }: { design: Design }) {
  const [text, setText] = useState("");
  const [params] = useSearchParams();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const send = useMutation({
    mutationFn: (content: string) => api(`/designs/${design.id}/messages`, { method: "POST", body: { content } }),
    onSuccess: () => {
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["design", design.id] });
    },
    onError: (error) => toast.error(error.message),
  });
  useEffect(() => {
    if (params.get("focus") === "chat") inputRef.current?.focus();
  }, [params]);
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [design.messages.length, design.busy]);
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (text.trim() && !design.busy) send.mutate(text.trim());
  };
  const editable = design.status === "draft";
  const examples = [
    "자율운항 선박 연구를 위한 조직을 만들어 줘. 논문 조사, LiDAR 데이터 분석, 객체 인식 모델 개발, 실험 검증이 필요해.",
    "1인 개발자를 위한 작은 개발 조직. 기획·구현·리뷰 3명이면 충분해.",
    "마케팅 부서를 추가하고 연구원과 데이터 분석가가 직접 협업하게 해 줘.",
  ];

  return (
    <section className="flex min-h-0 flex-col border-r border-border bg-surface-1 max-lg:border-r-0 max-lg:border-b" aria-label="설계 대화">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <Sparkles className="size-4 text-primary-text" aria-hidden />
        <h2 className="text-sm font-semibold">설계 담당 Claude</h2>
        <span className="ml-auto text-2xs text-faint">도구 없이 설계만 합니다</span>
      </div>
      <div ref={listRef} className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4" aria-live="polite">
        {design.messages.length === 0 ? (
          <div className="flex flex-col gap-3 text-sm text-muted">
            <p>어떤 일을 하는 조직이 필요한지 설명해 주세요. 필요한 정보는 한두 가지씩 되물어 봅니다.</p>
            <ul className="flex flex-col gap-1.5">
              {examples.map((ex) => (
                <li key={ex}>
                  <button
                    type="button"
                    disabled={!editable}
                    className="w-full cursor-pointer rounded-md border border-border px-3 py-2 text-left text-xs text-muted transition-colors hover:border-border-strong hover:text-fg"
                    onClick={() => {
                      setText(ex);
                      inputRef.current?.focus();
                    }}
                  >
                    {ex}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {design.messages.map((m, index) => (
          <div key={`${m.at}-${index}`} className={cn("flex flex-col gap-1.5", m.role === "user" && "items-end")}>
            {m.role === "user" ? (
              <p className="max-w-[90%] rounded-lg bg-surface-3 px-3 py-2 text-sm whitespace-pre-wrap">{m.content}</p>
            ) : m.role === "edit" ? (
              <p className="text-xs text-faint">
                {m.content}
                {m.changes?.length ? `: ${m.changes.slice(0, 3).join(", ")}${m.changes.length > 3 ? " 외" : ""}` : ""}
              </p>
            ) : (
              <div className="flex flex-col gap-2 text-sm">
                {m.content ? <p className="whitespace-pre-wrap leading-relaxed">{m.content}</p> : null}
                {m.questions?.length ? (
                  <ul className="flex flex-col gap-1">
                    {m.questions.map((q) => (
                      <li key={q}>
                        <button
                          type="button"
                          className="cursor-pointer text-left text-sm text-primary-text hover:underline"
                          onClick={() => {
                            setText(`${q}\n→ `);
                            inputRef.current?.focus();
                          }}
                        >
                          {q}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {m.changes?.length ? (
                  <details className="text-xs text-muted">
                    <summary className="cursor-pointer text-faint">조직도 변경 {m.changes.length}건</summary>
                    <ul className="mt-1 list-disc pl-5">
                      {m.changes.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                {m.notes?.map((n) => (
                  <p key={n} className="text-xs text-warning">
                    {n}
                  </p>
                ))}
                {m.error ? <p className="text-xs text-danger">{m.error}</p> : null}
              </div>
            )}
          </div>
        ))}
        {design.busy ? (
          <p className="flex items-center gap-2 text-sm text-muted" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> 조직을 설계하는 중… 라즈베리 파이에서는 1~2분 걸릴 수 있습니다.
          </p>
        ) : null}
      </div>
      <form onSubmit={submit} className="border-t border-border p-3">
        <div className="flex items-end gap-2 rounded-lg border border-border-strong bg-surface-2 p-2 focus-within:border-ring">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            disabled={!editable}
            placeholder={editable ? "원하는 조직을 설명하거나 바꿀 점을 말해 주세요…" : "적용이 끝난 설계입니다."}
            aria-label="설계 담당자에게 보낼 메시지"
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent text-sm placeholder:text-faint focus:outline-none"
          />
          <IconButton
            label="보내기"
            type="submit"
            variant="primary"
            size="icon-sm"
            disabled={!text.trim() || design.busy || send.isPending || !editable}
          >
            <SendHorizontal />
          </IconButton>
        </div>
      </form>
    </section>
  );
}

// ── 부서 관리 ─────────────────────────────────────────────────────────────

function DepartmentsDialog({
  open,
  onOpenChange,
  spec,
  onChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  spec: OrgSpec;
  onChange: (next: OrgSpec) => void;
}) {
  const [name, setName] = useState("");
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    spec.agents.forEach((a) => a.department && m.set(a.department, (m.get(a.department) ?? 0) + 1));
    return m;
  }, [spec.agents]);
  const add = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    const key = newKey("dept", new Set(spec.departments.map((d) => d.key)));
    const color = DEPT_COLORS[spec.departments.length % DEPT_COLORS.length]!;
    onChange({ ...spec, departments: [...spec.departments, { key, name: name.trim(), description: "", color }] });
    setName("");
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="부서" description="부서를 지우면 소속 에이전트는 '부서 없음'이 됩니다.">
        <ul className="flex flex-col divide-y divide-border">
          {spec.departments.map((d) => (
            <li key={d.key} className="flex items-center gap-2 py-2">
              <DeptChip name="" color={d.color} />
              <Input
                aria-label="부서 이름"
                defaultValue={d.name}
                onBlur={(e) =>
                  e.target.value.trim() &&
                  e.target.value !== d.name &&
                  onChange({
                    ...spec,
                    departments: spec.departments.map((x) => (x.key === d.key ? { ...x, name: e.target.value.trim() } : x)),
                  })
                }
              />
              <span className="w-14 shrink-0 text-right text-xs text-faint tabular">{counts.get(d.key) ?? 0}명</span>
              <IconButton
                label={`${d.name} 삭제`}
                size="icon-sm"
                onClick={() =>
                  onChange({
                    ...spec,
                    departments: spec.departments.filter((x) => x.key !== d.key),
                    agents: spec.agents.map((a) => (a.department === d.key ? { ...a, department: null } : a)),
                  })
                }
              >
                <Trash2 />
              </IconButton>
            </li>
          ))}
          {spec.departments.length === 0 ? <li className="py-2 text-sm text-faint">아직 부서가 없습니다.</li> : null}
        </ul>
        <form onSubmit={add} className="mt-4 flex gap-2">
          <Input aria-label="새 부서 이름" placeholder="새 부서 이름…" value={name} onChange={(e) => setName(e.target.value)} />
          <Button type="submit" disabled={!name.trim()}>
            <Plus /> 추가
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── 최종 검토 ─────────────────────────────────────────────────────────────

function ReviewDialog({
  open,
  onOpenChange,
  design,
  onChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  design: Design;
  onChange: (next: OrgSpec) => void;
}) {
  const spec = design.spec;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { setOrgId } = useCurrentOrg();
  const [runningWarning, setRunningWarning] = useState<string | null>(null);
  const apply = useMutation({
    mutationFn: (confirm_running: boolean) =>
      api<{ organization_id: string; changes: string[] }>(`/designs/${design.id}/apply`, {
        method: "POST",
        body: { confirm_running },
      }),
    onSuccess: (res) => {
      toast.success(design.organization_id ? "조직 구성을 적용했습니다." : "조직을 만들었습니다.", {
        description: res.changes.slice(0, 4).join(", "),
      });
      void queryClient.invalidateQueries();
      setOrgId(res.organization_id);
      navigate("/organization");
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409 && error.detail && typeof error.detail === "object") {
        setRunningWarning(error.message);
      } else toast.error(error.message);
    },
  });
  const depts = new Map(spec.departments.map((d) => [d.key, d]));
  const pendingSuggestions = spec.agents.filter((a) => a.permission_suggestion);
  const recCounts = design.recommendations.reduce<Record<string, number>>((acc, r) => {
    acc[r.status] = (acc[r.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        wide
        title={design.organization_id ? "변경 사항 검토" : "조직 생성 전 검토"}
        description="여기서 확인한 구성만 실제 조직으로 만들어집니다. AI가 제안했지만 수락하지 않은 권한은 적용되지 않습니다."
      >
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="조직 이름">
            {(id) => (
              <Input id={id} defaultValue={spec.name} onBlur={(e) => e.target.value.trim() && e.target.value !== spec.name && onChange({ ...spec, name: e.target.value.trim() })} />
            )}
          </Field>
          <Field label="목적">
            {(id) => (
              <Textarea id={id} className="min-h-10" defaultValue={spec.mission} onBlur={(e) => e.target.value !== spec.mission && onChange({ ...spec, mission: e.target.value })} />
            )}
          </Field>
        </div>
        <table className="mt-5 w-full text-left text-sm">
          <caption className="mb-2 text-left text-xs font-semibold text-muted">에이전트 {spec.agents.length}명</caption>
          <thead className="text-2xs text-faint">
            <tr className="border-b border-border">
              <th className="py-1.5 pr-3 font-medium">이름</th>
              <th className="py-1.5 pr-3 font-medium">부서</th>
              <th className="py-1.5 pr-3 font-medium">허용</th>
              <th className="py-1.5 font-medium">승인 필요</th>
            </tr>
          </thead>
          <tbody>
            {spec.agents.map((a) => {
              const dept = a.department ? depts.get(a.department) : undefined;
              const allowed = [
                a.permissions.allow_shell && "셸",
                a.permissions.allow_file_write && "파일 수정",
                a.permissions.allow_file_delete && "삭제",
                a.permissions.allow_network && "웹",
                a.permissions.can_delegate && "위임",
              ].filter(Boolean);
              return (
                <tr key={a.key} className="border-b border-border align-top">
                  <td className="py-1.5 pr-3">
                    {a.name}
                    <span className="block text-2xs text-faint">{a.title}</span>
                  </td>
                  <td className="py-1.5 pr-3">{dept ? <DeptChip name={dept.name} color={dept.color} /> : <span className="text-faint">—</span>}</td>
                  <td className="py-1.5 pr-3 text-xs">
                    {allowed.join(", ") || "읽기만"}
                    {a.permission_suggestion ? <span className="block text-warning">권한 제안 검토 대기(미적용)</span> : null}
                  </td>
                  <td className="py-1.5 text-xs text-muted">
                    {a.permissions.require_approval.map((g) => APPROVAL_LABELS[g]).join(", ") || "없음"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="mt-4 grid gap-1 text-xs text-muted">
          <p>협업 관계 {spec.collaborations.length}개 · 부서 {spec.departments.length}개</p>
          <p>
            추천 도구: 사용 가능 {recCounts.available ?? 0} · 허용 필요 {recCounts.approval_required ?? 0} · 설치 필요{" "}
            {recCounts.install_required ?? 0} · 미지원 {recCounts.unsupported ?? 0}
          </p>
          {pendingSuggestions.length ? (
            <p className="text-warning">
              권한 확대 제안 {pendingSuggestions.length}건은 수락하지 않으면 적용되지 않습니다(에이전트 설정에서 수락).
            </p>
          ) : null}
        </div>
        {runningWarning ? (
          <div className="mt-4 rounded-md border border-[#5c4a22] bg-[#2a2213] px-3 py-2.5 text-sm">
            <p className="text-warning">{runningWarning}</p>
            <Button className="mt-2" size="sm" variant="warning" onClick={() => apply.mutate(true)} disabled={apply.isPending}>
              확인하고 적용
            </Button>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            계속 편집
          </Button>
          <Button variant="primary" onClick={() => apply.mutate(false)} disabled={apply.isPending}>
            {apply.isPending ? "적용하는 중…" : design.organization_id ? "변경 적용" : "이 구성으로 조직 생성"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
