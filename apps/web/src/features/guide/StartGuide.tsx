/** 시작 가이드(8단계). 각 단계는 실제 데이터나 화면 방문으로 자동 완료된다. 대시보드 위에 보이고 숨길 수 있다. */

import { Check, ChevronRight, X } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import { useConversations, useCurrentOrg, useOrganizations, useProjects, useTasks } from "@/lib/queries";
import { cn } from "@/lib/utils";

import { setGuideHidden, useGuideState } from "./guide";

interface Step {
  title: string;
  hint: string;
  to: string;
  done: boolean;
}

export function useGuideSteps(): Step[] {
  const { orgId } = useCurrentOrg();
  const orgs = useOrganizations();
  const projects = useProjects();
  const conversations = useConversations(orgId);
  const tasks = useTasks(orgId);
  const { visited } = useGuideState();
  const seen = (p: string) => visited.includes(p);
  return [
    { title: "조직 만들기", hint: "템플릿을 고르거나 AI와 대화해 회사를 설계하고 적용합니다.", to: "/builder", done: (orgs.data?.length ?? 0) > 0 },
    { title: "조직도 살펴보기", hint: "에이전트를 눌러 역할·권한(셸·파일 수정 승인)을 확인합니다.", to: "/organization", done: seen("/organization") },
    { title: "프로젝트 연결", hint: "탐색 경로를 추가하고 작업할 저장소를 등록합니다.", to: "/projects", done: (projects.data?.length ?? 0) > 0 },
    { title: "기능 확인", hint: "에이전트가 쓸 수 있는 Skills·MCP·Plugins를 봅니다.", to: "/capabilities", done: seen("/capabilities") },
    { title: "대화 시작", hint: "커맨드 센터에서 CEO나 팀과 새 대화를 엽니다.", to: "/command", done: (conversations.data?.length ?? 0) > 0 },
    { title: "업무 맡기기", hint: "CEO에게 일을 주면 팀에 위임합니다. /delegate 명령으로 직접 맡길 수도 있습니다.", to: "/command", done: (tasks.data?.length ?? 0) > 0 },
    { title: "사무실 보기", hint: "에이전트가 일하는 모습을 아이소메트릭 사무실에서 봅니다.", to: "/office", done: seen("/office") },
    { title: "사용량 확인", hint: "Claude·Codex 사용률과 소진 예측을 봅니다.", to: "/usage", done: seen("/usage") },
  ];
}

export function StartGuide() {
  const { hidden } = useGuideState();
  const steps = useGuideSteps();
  const done = steps.filter((s) => s.done).length;
  if (hidden) return null;
  const next = steps.findIndex((s) => !s.done);
  return (
    <section aria-labelledby="guide-title" className="rounded-lg border border-border bg-surface-1 p-4">
      <header className="flex items-center gap-3">
        <h2 id="guide-title" className="text-sm font-semibold">
          시작 가이드
        </h2>
        <span className="text-xs text-muted tabular">
          {done}/{steps.length} 완료
        </span>
        <div
          className="h-1.5 w-32 overflow-hidden rounded-full bg-surface-3"
          role="progressbar"
          aria-label="시작 가이드 진행률"
          aria-valuemin={0}
          aria-valuemax={steps.length}
          aria-valuenow={done}
        >
          <div className="h-full rounded-full bg-success transition-[width] duration-500 ease-[var(--ease-out)]" style={{ width: `${(done / steps.length) * 100}%` }} />
        </div>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setGuideHidden(true)} aria-label="시작 가이드 숨기기">
          <X /> {done === steps.length ? "닫기" : "숨기기"}
        </Button>
      </header>
      {done === steps.length ? (
        <p className="mt-3 text-sm text-muted">모든 단계를 마쳤습니다. 가이드는 왼쪽 아래 메뉴에서 다시 열 수 있습니다.</p>
      ) : (
        <ol className="mt-3 grid gap-1.5 sm:grid-cols-2 xl:grid-cols-4">
          {steps.map((s, i) => (
            <li key={s.title}>
              <Link
                to={s.to}
                className={cn(
                  "group flex h-full items-start gap-2.5 rounded-md border px-3 py-2.5 transition-colors",
                  i === next ? "border-primary-text/50 bg-primary-soft" : "border-border hover:bg-surface-2",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-2xs font-semibold tabular",
                    s.done ? "bg-success text-bg" : "border border-border-strong text-muted",
                  )}
                  aria-hidden
                >
                  {s.done ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className={cn("text-sm font-medium", s.done && "text-muted line-through decoration-faint")}>
                    {s.title}
                    <span className="sr-only">{s.done ? " (완료)" : " (남음)"}</span>
                  </span>
                  <span className="text-xs text-faint">{s.hint}</span>
                </span>
                <ChevronRight className="ml-auto size-4 shrink-0 self-center text-faint opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
