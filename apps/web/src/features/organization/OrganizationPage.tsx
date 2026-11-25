import { useMutation, useQueryClient } from "@tanstack/react-query";
import { History, PencilRuler, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { AgentStatus, DeptChip, EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { ChartLegend, OrgChart, orgAsSpec } from "@/components/org/OrgChart";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { type Design, api } from "@/lib/api";
import { useCurrentOrg, useOrganization, useRevisions } from "@/lib/queries";
import { timeAgo } from "@/lib/utils";

/** 조직(운영 모드): 실제 조직의 조직도·구성원·변경 이력. 구성 변경은 '조직 설계'(설계 모드)에서 한다. */
export function OrganizationPage() {
  const { orgId } = useCurrentOrg();
  const org = useOrganization(orgId);
  const navigate = useNavigate();
  const [historyOpen, setHistoryOpen] = useState(false);
  const edit = useMutation({
    mutationFn: () => api<Design>("/designs", { method: "POST", body: { organization_id: orgId } }),
    onSuccess: (d) => navigate(`/builder/${d.id}`),
    onError: (e) => toast.error(e.message),
  });

  if (!orgId)
    return (
      <div className="p-6">
        <EmptyState
          icon={<Sparkles />}
          title="조직이 없습니다"
          action={
            <Button variant="primary" asChild>
              <Link to="/builder">조직 설계 시작</Link>
            </Button>
          }
        />
      </div>
    );
  if (org.isLoading) return <LoadingState className="p-6" />;
  if (org.error || !org.data) return <ErrorState className="m-6" error={org.error} retry={() => void org.refetch()} />;
  const o = org.data;
  const spec = orgAsSpec(o);
  const statuses = Object.fromEntries(o.agents.map((a) => [a.id, a.status]));
  const depts = new Map(o.departments.map((d) => [d.id, d]));
  const names = new Map(o.agents.map((a) => [a.id, a.name]));

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex flex-wrap items-end justify-between gap-3 px-6 pt-6 pb-3">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold">{o.name}</h1>
          {o.mission ? <p className="mt-1 max-w-[70ch] text-sm text-muted">{o.mission}</p> : null}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setHistoryOpen(true)}>
            <History /> 변경 이력
          </Button>
          <Button variant="primary" onClick={() => edit.mutate()} disabled={edit.isPending}>
            <PencilRuler /> 조직 수정
          </Button>
        </div>
      </header>
      <Tabs defaultValue="chart" className="flex min-h-0 flex-1 flex-col">
        <TabsList className="px-6">
          <TabsTrigger value="chart">조직도</TabsTrigger>
          <TabsTrigger value="members">구성원 {o.agents.length}</TabsTrigger>
        </TabsList>
        <TabsContent value="chart" className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <OrgChart spec={spec} statuses={statuses} onSelect={(id) => id && navigate(`/agents/${id}`)} />
          </div>
          <div className="border-t border-border px-6 py-2">
            <ChartLegend />
          </div>
        </TabsContent>
        <TabsContent value="members" className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          <table className="w-full text-left text-sm">
            <thead className="text-2xs text-faint">
              <tr>
                <th className="pb-2 font-medium">에이전트</th>
                <th className="pb-2 font-medium">부서</th>
                <th className="pb-2 font-medium">상위</th>
                <th className="pb-2 font-medium">상태</th>
              </tr>
            </thead>
            <tbody>
              {o.agents.map((a) => {
                const dept = a.department_id ? depts.get(a.department_id) : undefined;
                return (
                  <tr key={a.id} className="border-t border-border">
                    <td className="py-2 pr-3">
                      <Link to={`/agents/${a.id}`} className="flex items-center gap-2.5 hover:text-primary-text">
                        <AgentAvatar id={a.id} lead={a.is_lead} dim={!a.enabled} />
                        <span className="min-w-0">
                          <span className="block truncate">{a.name}</span>
                          <span className="block truncate text-xs text-faint">{a.title}</span>
                        </span>
                      </Link>
                    </td>
                    <td className="py-2 pr-3">{dept ? <DeptChip name={dept.name} color={dept.color} /> : <span className="text-faint">—</span>}</td>
                    <td className="py-2 pr-3 text-muted">{a.reports_to_id ? names.get(a.reports_to_id) : "—"}</td>
                    <td className="py-2">{a.enabled ? <AgentStatus status={a.status} /> : <span className="text-xs text-faint">비활성</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TabsContent>
      </Tabs>
      <HistoryDialog open={historyOpen} onOpenChange={setHistoryOpen} orgId={o.id} />
    </div>
  );
}

function HistoryDialog({ open, onOpenChange, orgId }: { open: boolean; onOpenChange: (v: boolean) => void; orgId: string }) {
  const revisions = useRevisions(open ? orgId : null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const restore = useMutation({
    mutationFn: (rid: string) => api<Design>(`/organizations/${orgId}/revisions/${rid}/restore`, { method: "POST" }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: ["designs"] });
      navigate(`/builder/${d.id}`);
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="변경 이력"
        description="적용된 구성마다 기록됩니다. 되돌리기는 그 구성으로 설계 초안을 만들고, 검토 후 적용해야 반영됩니다."
      >
        {revisions.isLoading ? <LoadingState /> : null}
        <ol className="flex flex-col divide-y divide-border">
          {(revisions.data ?? []).map((r, index) => (
            <li key={r.id} className="flex items-start gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm">{r.summary.slice(0, 3).join(", ")}{r.summary.length > 3 ? ` 외 ${r.summary.length - 3}건` : ""}</p>
                <p className="text-xs text-faint">
                  {timeAgo(r.created_at)} · 에이전트 {r.agent_count}명 {index === 0 ? "· 현재 구성" : ""}
                </p>
              </div>
              {index > 0 ? (
                <Button size="sm" onClick={() => restore.mutate(r.id)} disabled={restore.isPending}>
                  이 구성으로 되돌리기
                </Button>
              ) : null}
            </li>
          ))}
        </ol>
      </DialogContent>
    </Dialog>
  );
}
