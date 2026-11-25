import { useMutation } from "@tanstack/react-query";
import { Activity, Blocks, Loader2, Plug, Puzzle, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/common/states";
import { Button, IconButton } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { type Capability, type McpHealth, api } from "@/lib/api";
import { useCapabilities, useCurrentOrg, useOrganization } from "@/lib/queries";
import { cn } from "@/lib/utils";

/**
 * Capability Manager. 이 컴퓨터의 Claude Code 설정에서 Skills·MCP·Plugins를 읽기 전용으로 탐색하고, 현재 조직의 어떤 에이전트에게
 * 허용됐는지 보여 준다. 허용된 항목은 그 에이전트 실행에 연결된다. MCP는 `claude mcp list`로 연결을 점검한다. 설치는 CLI로 한다.
 */
export function CapabilitiesPage() {
  const caps = useCapabilities();
  const { orgId } = useCurrentOrg();
  const org = useOrganization(orgId);
  const list = caps.data ?? [];
  const health = useMutation({
    mutationFn: () => api<McpHealth[]>("/capabilities/mcp/health"),
    onError: (e) => toast.error(e.message),
  });
  const healthOf = (name: string) => health.data?.find((h) => h.name === name);
  const byKind = (kind: Capability["kind"]) => list.filter((c) => c.kind === kind);
  const allowedBy = (cap: Capability) =>
    (org.data?.agents ?? []).filter((a) =>
      cap.kind === "skill" ? a.allowed_skills.includes(cap.id) : cap.kind === "mcp" ? a.allowed_mcp_servers.includes(cap.id) : a.allowed_plugins.includes(cap.id),
    );

  return (
    <div className="flex-1 overflow-y-auto">
      <PageHeader
        title="기능 관리"
        description="이 컴퓨터의 Claude Code 설정에서 찾은 Skills·MCP 서버·Plugins입니다. 에이전트별 허용은 에이전트 설정에서 바꿉니다."
        actions={
          <IconButton label="다시 탐색" onClick={() => void caps.refetch()}>
            <RefreshCw className={cn(caps.isFetching && "animate-spin")} />
          </IconButton>
        }
      />
      <div className="px-6 pb-10">
        {caps.isLoading ? <LoadingState /> : null}
        {caps.error ? <ErrorState error={caps.error} retry={() => void caps.refetch()} /> : null}
        <Tabs defaultValue="skill">
          <TabsList>
            <TabsTrigger value="skill">Skills {byKind("skill").length}</TabsTrigger>
            <TabsTrigger value="mcp">MCP 서버 {byKind("mcp").length}</TabsTrigger>
            <TabsTrigger value="plugin">Plugins {byKind("plugin").length}</TabsTrigger>
          </TabsList>
          {(["skill", "mcp", "plugin"] as const).map((kind) => (
            <TabsContent key={kind} value={kind} className="pt-4">
              {kind === "mcp" ? (
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <p className="max-w-[80ch] text-xs text-faint">
                    비밀이 담길 수 있는 값(환경 변수·헤더·인자·URL 쿼리)은 화면에 보내지 않습니다. 에이전트에게 허용한 서버만 그 에이전트
                    실행에 연결되며, 도구 호출은 에이전트의 MCP 승인 설정을 따릅니다. 연결 점검은 서버를 실제로 띄워 보므로 수십 초 걸릴 수
                    있습니다.
                  </p>
                  <Button size="sm" onClick={() => health.mutate()} disabled={health.isPending}>
                    {health.isPending ? <Loader2 className="animate-spin" /> : <Activity />}
                    {health.isPending ? "점검하는 중…" : "연결 점검"}
                  </Button>
                </div>
              ) : null}
              {byKind(kind).length === 0 && !caps.isLoading ? (
                <EmptyState icon={kind === "skill" ? <Sparkles /> : kind === "mcp" ? <Plug /> : <Puzzle />} title="찾은 항목이 없습니다">
                  {kind === "skill"
                    ? "~/.claude/skills 또는 등록한 프로젝트의 .claude/skills에 SKILL.md가 있는 폴더를 두면 나타납니다."
                    : kind === "mcp"
                      ? "`claude mcp add`로 추가한 서버나 프로젝트의 .mcp.json이 여기에 나타납니다."
                      : "`claude plugin install`로 설치한 플러그인이 나타납니다."}
                </EmptyState>
              ) : (
                <table className="w-full text-left text-sm">
                  <thead className="text-2xs text-faint">
                    <tr>
                      <th className="pb-2 font-medium">이름</th>
                      <th className="pb-2 font-medium">범위</th>
                      <th className="pb-2 font-medium">설명</th>
                      {kind === "mcp" ? <th className="pb-2 font-medium">연결</th> : null}
                      <th className="pb-2 font-medium">허용된 에이전트</th>
                    </tr>
                  </thead>
                  <tbody>
                    {byKind(kind).map((c) => {
                      const agents = allowedBy(c);
                      return (
                        <tr key={c.id} className="border-t border-border align-top">
                          <td className="py-2 pr-3">
                            <span className="flex items-center gap-1.5 font-medium">
                              <Blocks className="size-3.5 text-faint" aria-hidden />
                              {c.name}
                            </span>
                            <span className="block truncate font-mono text-2xs text-faint">{c.source}</span>
                          </td>
                          <td className="py-2 pr-3 text-xs text-muted">
                            {c.scope}
                            {c.transport ? ` · ${c.transport}` : ""}
                          </td>
                          <td className="max-w-[56ch] py-2 pr-3 text-xs text-muted">
                            <span className="line-clamp-2">{c.description || detailText(c)}</span>
                          </td>
                          {kind === "mcp" ? (
                            <td className="py-2 pr-3 text-xs">
                              <HealthBadge health={healthOf(c.name)} checked={Boolean(health.data)} />
                            </td>
                          ) : null}
                          <td className="py-2 text-xs">{agents.length ? agents.map((a) => a.name).join(", ") : <span className="text-faint">없음</span>}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  );
}

function detailText(c: Capability): string {
  const d = c.detail;
  const parts = [d.command && `명령 ${String(d.command)}`, d.host && `호스트 ${String(d.host)}`, d.version && `v${String(d.version)}`];
  return parts.filter(Boolean).join(" · ") || "—";
}

const HEALTH_LABELS: Record<McpHealth["state"], { label: string; color: string }> = {
  connected: { label: "연결됨", color: "var(--success)" },
  needs_auth: { label: "인증 필요", color: "var(--warning)" },
  failed: { label: "연결 실패", color: "var(--danger)" },
  pending_approval: { label: "CLI 승인 대기(앱 실행엔 영향 없음)", color: "var(--warning)" },
  disabled: { label: "비활성", color: "var(--text-faint)" },
  unknown: { label: "알 수 없음", color: "var(--text-faint)" },
  error: { label: "점검 오류", color: "var(--danger)" },
};

function HealthBadge({ health, checked }: { health?: McpHealth; checked: boolean }) {
  if (!checked) return <span className="text-faint">점검 전</span>;
  if (!health) return <span className="text-faint" title="claude mcp list에 나타나지 않았습니다(프로젝트·로컬 범위는 그 폴더 기준)">목록에 없음</span>;
  const meta = HEALTH_LABELS[health.state] ?? HEALTH_LABELS.unknown;
  return (
    <span className="inline-flex items-center gap-1.5" style={{ color: meta.color }} title={health.message}>
      <span className="size-1.5 rounded-full" style={{ background: "currentColor" }} aria-hidden />
      {meta.label}
    </span>
  );
}
