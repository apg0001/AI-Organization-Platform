import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageSquare } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { AgentEditor } from "@/components/agent/AgentEditor";
import { AgentStatus, DeptChip, ErrorState, LoadingState, Section } from "@/components/common/states";
import { orgAsSpec } from "@/components/org/OrgChart";
import { Button, IconButton } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { type Agent, type Conversation, type SpecAgent, api, fieldError } from "@/lib/api";
import { usePermissionChange } from "@/features/permissions/usePermissionChange";
import { samePermissions } from "@/lib/permissions";
import { useCapabilities, useOrganization, useTasks } from "@/lib/queries";
import { timeAgo } from "@/lib/utils";
import { TaskStatus } from "@/features/dashboard/DashboardPage";

/**
 * 에이전트 상세(운영 모드). 설정 변경은 사용자가 직접 하는 편집이므로 즉시 저장한다(권한 포함).
 * 구조 변경(부서 개편·대량 수정)은 조직 설계에서 미리보기 후 적용하는 것을 권장한다.
 */
export function AgentDetailPage() {
  const { agentId } = useParams();
  const [searchParams] = useSearchParams();
  const agent = useQuery({ queryKey: ["agent", agentId], queryFn: () => api<Agent>(`/agents/${agentId}`) });
  const org = useOrganization(agent.data?.organization_id);
  const caps = useCapabilities();
  const tasks = useTasks(agent.data?.organization_id ?? null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const save = useMutation({
    mutationFn: (next: SpecAgent) =>
      api<Agent>(`/organizations/${agent.data!.organization_id}/agents/${agentId}`, {
        method: "PATCH",
        body: {
          name: next.name,
          title: next.title,
          role: next.role,
          responsibilities: next.responsibilities,
          expertise: next.expertise,
          instructions: next.instructions,
          department_id: next.department,
          reports_to_id: next.reports_to,
          enabled: next.enabled,
          // 권한은 여기서 보내지 않는다(아래 permissions.request가 최신 값 기준으로 따로 저장한다).
          allowed_skills: next.allowed_skills,
          allowed_mcp_servers: next.allowed_mcp_servers,
          allowed_plugins: next.allowed_plugins,
        },
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent", agentId] });
      void queryClient.invalidateQueries({ queryKey: ["organization"] });
      toast.success("저장했습니다.");
    },
    onError: (e) => toast.error(e.message),
  });
  // 권한 변경은 표·팝오버와 같은 길로 저장한다: 넓어지는 변경(auto 전환, 허용 규칙 추가, 금지 → 허용 등)은 확인 창,
  // 화면이 열려 있는 동안 늘어난 허용 규칙('항상 허용')은 덮어쓰지 않는다.
  const permissions = usePermissionChange();
  const chat = useMutation({
    mutationFn: () =>
      api<Conversation>("/conversations", {
        method: "POST",
        body: { organization_id: agent.data!.organization_id, target_kind: "agent", target_id: agentId },
      }),
    onSuccess: (c) => navigate(`/command/${c.id}`),
    onError: (e) => toast.error(e.message),
  });

  if (agent.isLoading || org.isLoading) return <LoadingState className="p-6" />;
  if (agent.error || !agent.data) return <ErrorState className="m-6" error={agent.error} />;
  if (!org.data) return <ErrorState className="m-6" error={org.error} />;
  const a = agent.data;
  const spec = orgAsSpec(org.data);
  const specAgent = spec.agents.find((x) => x.key === a.id)!;
  const dept = org.data.departments.find((d) => d.id === a.department_id);
  const manager = org.data.agents.find((x) => x.id === a.reports_to_id);
  const mine = (tasks.data ?? []).filter((t) => t.assignee_id === a.id);

  return (
    <div className="flex-1 overflow-y-auto">
      <header className="flex flex-wrap items-center gap-4 px-6 pt-6 pb-4">
        <IconButton label="뒤로" onClick={() => navigate(-1)}>
          <ArrowLeft />
        </IconButton>
        <AgentAvatar id={a.id} lead={a.is_lead} size={48} dim={!a.enabled} />
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold">{a.name}</h1>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span>{a.title || "직책 없음"}</span>
            {dept ? <DeptChip name={dept.name} color={dept.color} /> : null}
            {manager ? <span className="text-xs">보고 대상: {manager.name}</span> : null}
            <AgentStatus status={a.status} />
          </p>
        </div>
        <Button variant="primary" onClick={() => chat.mutate()} disabled={!a.enabled || chat.isPending}>
          <MessageSquare /> 직접 대화
        </Button>
      </header>
      {/* 승인 배너·권한 표의 '권한 보기/편집' 링크는 ?tab=settings로 설정 탭을 바로 연다. */}
      <Tabs defaultValue={searchParams.get("tab") === "settings" ? "settings" : "overview"} className="px-6 pb-10">
        <TabsList>
          <TabsTrigger value="overview">개요</TabsTrigger>
          <TabsTrigger value="settings">설정·권한</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="grid gap-8 pt-5 lg:grid-cols-2">
          <Section title="역할">
            <p className="text-sm whitespace-pre-wrap">{a.role || "역할이 정의되지 않았습니다."}</p>
            {a.responsibilities.length ? (
              <ul className="list-disc pl-5 text-sm text-muted">
                {a.responsibilities.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            ) : null}
            {a.expertise.length ? <p className="text-xs text-faint">전문 분야: {a.expertise.join(", ")}</p> : null}
          </Section>
          <Section title="맡은 작업">
            {mine.length === 0 ? (
              <p className="text-sm text-muted">위임받은 작업이 없습니다.</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {mine.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate">{t.title}</span>
                    <span className="flex items-center gap-3">
                      <span className="text-xs text-faint">{timeAgo(t.updated_at)}</span>
                      <TaskStatus status={t.status} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="실행 환경">
            <dl className="grid grid-cols-[8rem_1fr] gap-y-1.5 text-sm">
              <dt className="text-muted">런타임</dt>
              <dd>Claude Code</dd>
              <dt className="text-muted">모델</dt>
              <dd>{a.model ?? "Claude Code 기본값"}</dd>
              <dt className="text-muted">작업 폴더</dt>
              <dd className="text-xs text-muted">대화에 연결한 프로젝트. 없으면 이 에이전트 전용 작업 폴더(~/.ai-org/workspaces)</dd>
            </dl>
            <p className="text-xs text-faint">
              실행 세션 기록은 커맨드 센터의 각 대화와 오른쪽 실행 패널에서 볼 수 있습니다.{" "}
              <Link to="/command" className="text-primary-text underline">
                커맨드 센터
              </Link>
            </p>
          </Section>
        </TabsContent>
        <TabsContent value="settings" className="max-w-2xl pt-5">
          <AgentEditor
            agent={specAgent}
            agents={spec.agents}
            departments={spec.departments}
            capabilities={caps.data ?? []}
            onChange={(next) => {
              if (!samePermissions(specAgent.permissions, next.permissions)) {
                permissions.request([{ agent: { ...a, permissions: specAgent.permissions }, next: next.permissions }]);
              }
              // 권한 말고 다른 항목이 바뀌었을 때만 나머지를 저장한다.
              if (JSON.stringify({ ...next, permissions: null }) !== JSON.stringify({ ...specAgent, permissions: null })) save.mutate(next);
            }}
            permissionError={fieldError(permissions.error, "allow_rules")}
            permissionsBusy={permissions.pending}
          />
          {permissions.dialog}
        </TabsContent>
      </Tabs>
    </div>
  );
}
