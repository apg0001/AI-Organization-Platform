import { Activity, Hand, MessagesSquare, Sparkles } from "lucide-react";
import { Link } from "react-router";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { AgentStatus, EmptyState, ErrorState, LoadingState, PageHeader, Section } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { useCurrentOrg, useWorkspace } from "@/lib/queries";
import { timeAgo } from "@/lib/utils";

/**
 * 워크스페이스 대시보드. 우선순위: ① 나를 기다리는 것(승인) ② 지금 일하는 에이전트 ③ 조직·프로젝트 ④ 최근 활동.
 * 숫자 타일 대신 목록을 보여 준다 — 이 화면의 질문은 "얼마나"가 아니라 "누가 무엇을"이다.
 */
export function DashboardPage() {
  const ws = useWorkspace();
  const { setOrgId } = useCurrentOrg();
  if (ws.isLoading) return <LoadingState className="p-6" />;
  if (ws.error || !ws.data) return <ErrorState className="m-6" error={ws.error} retry={() => void ws.refetch()} />;
  const { organizations, projects, running_agents, pending_approvals, recent_tasks, activity } = ws.data;

  if (organizations.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <PageHeader title="AI 조직을 만들어 시작하세요" />
        <div className="px-6">
          <EmptyState
            icon={<Sparkles />}
            title="아직 조직이 없습니다"
            action={
              <Button variant="primary" asChild>
                <Link to="/builder">조직 설계 시작</Link>
              </Button>
            }
          >
            템플릿을 고르거나 Claude와 대화하며 부서와 에이전트를 설계하세요. 만든 조직의 CEO에게 일을 맡기면 실제 Claude Code
            에이전트가 이 컴퓨터에서 일합니다.
          </EmptyState>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <PageHeader title="대시보드" description="조직과 에이전트가 지금 무엇을 하고 있는지 봅니다." />
      <div className="grid gap-8 px-6 pb-10 xl:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col gap-8">
          {pending_approvals.length > 0 ? (
            <Section title={`승인 대기 ${pending_approvals.length}건`}>
              <ul className="flex flex-col gap-1">
                {pending_approvals.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 rounded-md border border-[#5c4a22] bg-[#2a2213] px-3 py-2 text-sm">
                    <Hand className="size-4 shrink-0 text-warning" aria-hidden />
                    <span className="min-w-0 flex-1 truncate font-mono text-xs">{a.summary}</span>
                    <span className="text-xs text-faint">{timeAgo(a.created_at)}</span>
                    <Button size="sm" variant="warning" asChild>
                      <Link to="/command">검토</Link>
                    </Button>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          <Section title="실행 중인 에이전트">
            {running_agents.length === 0 ? (
              <p className="text-sm text-muted">
                지금 일하는 에이전트가 없습니다.{" "}
                <Link to="/command" className="text-primary-text underline">
                  CEO에게 일을 맡기세요
                </Link>
                .
              </p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {running_agents.map((a) => (
                  <li key={a.id} className="flex items-center gap-3 py-2">
                    <AgentAvatar id={a.id} lead={a.is_lead} />
                    <Link to={`/agents/${a.id}`} className="min-w-0 flex-1 truncate text-sm hover:text-primary-text">
                      {a.name}
                      <span className="ml-2 text-xs text-faint">{a.title}</span>
                    </Link>
                    <AgentStatus status={a.status} />
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section
            title="조직"
            actions={
              <Button size="sm" variant="ghost" asChild>
                <Link to="/builder">새 조직</Link>
              </Button>
            }
          >
            <table className="w-full text-left text-sm">
              <thead className="text-2xs text-faint">
                <tr>
                  <th className="pb-1.5 font-medium">이름</th>
                  <th className="pb-1.5 font-medium">에이전트</th>
                  <th className="pb-1.5 font-medium">부서</th>
                  <th className="pb-1.5 font-medium">프로젝트</th>
                  <th className="pb-1.5 font-medium">변경</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {organizations.map((o) => (
                  <tr key={o.id} className="border-t border-border">
                    <td className="py-2 pr-3">
                      <Link to="/organization" onClick={() => setOrgId(o.id)} className="hover:text-primary-text">
                        {o.name}
                      </Link>
                      {o.mission ? <span className="block max-w-[48ch] truncate text-xs text-faint">{o.mission}</span> : null}
                    </td>
                    <td className="py-2 pr-3">{o.agent_count}</td>
                    <td className="py-2 pr-3">{o.department_count}</td>
                    <td className="py-2 pr-3">{o.project_count}</td>
                    <td className="py-2 text-xs text-faint">{timeAgo(o.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section
            title="프로젝트"
            actions={
              <Button size="sm" variant="ghost" asChild>
                <Link to="/projects">관리</Link>
              </Button>
            }
          >
            {projects.length === 0 ? (
              <p className="text-sm text-muted">등록된 로컬 프로젝트가 없습니다. 에이전트가 작업할 폴더를 프로젝트로 등록하세요.</p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {projects.slice(0, 8).map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                    <span className="truncate">{p.name}</span>
                    <span className="truncate font-mono text-xs text-faint">{p.path}</span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <div className="flex flex-col gap-8">
          <Section title="최근 작업">
            {recent_tasks.length === 0 ? (
              <p className="text-sm text-muted">
                아직 작업이 없습니다. 커맨드 센터에서 <code className="font-mono text-xs">/delegate</code>로 업무를 맡기면 여기에
                기록됩니다.
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {recent_tasks.map((t) => (
                  <li key={t.id} className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate">{t.title}</span>
                    <TaskStatus status={t.status} />
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="활동">
            {activity.length === 0 ? (
              <p className="text-sm text-muted">기록된 활동이 없습니다.</p>
            ) : (
              <ol className="flex flex-col gap-2.5">
                {activity.map((e) => (
                  <li key={e.id} className="flex gap-2.5 text-sm">
                    {e.kind.startsWith("run.") ? (
                      <MessagesSquare className="mt-0.5 size-3.5 shrink-0 text-faint" aria-hidden />
                    ) : (
                      <Activity className="mt-0.5 size-3.5 shrink-0 text-faint" aria-hidden />
                    )}
                    <span className="min-w-0 flex-1">{e.summary}</span>
                    <time className="shrink-0 text-xs text-faint" dateTime={e.created_at}>
                      {timeAgo(e.created_at)}
                    </time>
                  </li>
                ))}
              </ol>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

const TASK_LABELS: Record<string, { label: string; color: string }> = {
  queued: { label: "대기", color: "var(--status-idle)" },
  running: { label: "진행 중", color: "var(--status-working)" },
  waiting: { label: "승인 대기", color: "var(--status-waiting)" },
  review: { label: "검토", color: "var(--status-reviewing)" },
  done: { label: "완료", color: "var(--status-completed)" },
  failed: { label: "실패", color: "var(--status-failed)" },
  cancelled: { label: "취소", color: "var(--status-offline)" },
};

export function TaskStatus({ status }: { status: string }) {
  const meta = TASK_LABELS[status] ?? { label: status, color: "var(--text-muted)" };
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-xs" style={{ color: meta.color }}>
      <span className="size-1.5 rounded-full" style={{ background: "currentColor" }} aria-hidden />
      {meta.label}
    </span>
  );
}
