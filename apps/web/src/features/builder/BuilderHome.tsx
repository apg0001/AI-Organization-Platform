import { useMutation, useQuery } from "@tanstack/react-query";
import { LayoutTemplate, MessageSquareText, PencilRuler, Users } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";

import { ErrorState, LoadingState, PageHeader, Section } from "@/components/common/states";
import { OrgChart } from "@/components/org/OrgChart";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/overlay";
import { type Design, type Template, api } from "@/lib/api";
import { useTemplates } from "@/lib/queries";
import { cn, timeAgo } from "@/lib/utils";

/** 조직 설계 시작 화면(설계 모드 진입점): 템플릿 / AI와 함께 / 직접 만들기. */
export function BuilderHome() {
  const templates = useTemplates();
  const navigate = useNavigate();
  const [preview, setPreview] = useState<Template | null>(null);
  const drafts = useQuery({
    queryKey: ["designs"],
    queryFn: () => api<{ id: string; organization_id: string | null; origin: string; name: string; updated_at: string }[]>("/designs"),
  });
  const start = useMutation({
    mutationFn: (body: { template_id?: string }) => api<Design>("/designs", { method: "POST", body }),
    onSuccess: (design, vars) => navigate(`/builder/${design.id}${vars.template_id ? "" : "?focus=chat"}`),
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="flex-1 overflow-y-auto">
      <PageHeader
        title="조직 설계"
        description="템플릿에서 시작하거나, Claude와 대화하며 목적에 맞는 AI 조직을 설계하세요. 설계는 검토하고 적용하기 전까지 실제 조직에 반영되지 않습니다."
      />
      <div className="flex flex-col gap-8 px-6 pb-10">
        <div className="grid gap-3 md:grid-cols-3">
          <EntryButton
            icon={<MessageSquareText />}
            title="AI와 함께 만들기"
            description="목적을 설명하면 설계 담당 Claude가 부서·에이전트·권한 초안을 만들고 대화로 다듬습니다."
            onClick={() => start.mutate({})}
            primary
            disabled={start.isPending}
          />
          <EntryButton
            icon={<LayoutTemplate />}
            title="추천 템플릿으로 시작"
            description="연구·학습·개발·마케팅·비즈니스·개인 비서 조직 중 하나를 미리 보고 고쳐서 씁니다."
            onClick={() => document.getElementById("templates")?.scrollIntoView({ behavior: "smooth" })}
          />
          <EntryButton
            icon={<PencilRuler />}
            title="직접 만들기"
            description="CEO 한 명에서 시작해 조직도에서 부서와 에이전트를 직접 추가합니다."
            onClick={() => start.mutate({})}
            disabled={start.isPending}
          />
        </div>

        {drafts.data && drafts.data.length > 0 ? (
          <Section title="작성 중인 설계">
            <ul className="divide-y divide-border">
              {drafts.data.map((d) => (
                <li key={d.id}>
                  <Link to={`/builder/${d.id}`} className="flex items-center justify-between gap-3 py-2 text-sm hover:text-primary-text">
                    <span className="truncate">
                      {d.name}
                      <span className="ml-2 text-xs text-faint">{d.organization_id ? "기존 조직 변경안" : "새 조직"}</span>
                    </span>
                    <span className="text-xs text-faint">{timeAgo(d.updated_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        ) : null}

        <Section title="추천 템플릿">
          <div id="templates" className="scroll-mt-4" />
          {templates.isLoading ? <LoadingState /> : null}
          {templates.error ? <ErrorState error={templates.error} retry={() => void templates.refetch()} /> : null}
          <ul className="grid gap-x-6 gap-y-1 md:grid-cols-2">
            {(templates.data ?? []).map((t) => (
              <li key={t.template_id}>
                <button
                  type="button"
                  onClick={() => setPreview(t)}
                  className="group flex w-full cursor-pointer items-start gap-3 rounded-md px-2 py-3 text-left transition-colors hover:bg-surface-2"
                >
                  <span className="mt-0.5 rounded-sm bg-surface-3 px-1.5 py-0.5 text-2xs text-muted">{t.category}</span>
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="text-sm font-medium group-hover:text-primary-text">{t.name}</span>
                    <span className="text-xs text-muted">{t.description}</span>
                    <span className="flex items-center gap-3 text-2xs text-faint">
                      <span className="flex items-center gap-1">
                        <Users className="size-3" aria-hidden /> {t.org_size}
                      </span>
                      <span>추천 대상: {t.target_users.join(", ")}</span>
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <Dialog open={preview !== null} onOpenChange={(open) => !open && setPreview(null)}>
        {preview ? (
          <DialogContent wide title={preview.name} description={`${preview.description} · v${preview.version}`}>
            <TemplatePreview template={preview} />
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPreview(null)}>
                닫기
              </Button>
              <Button
                variant="primary"
                disabled={start.isPending}
                onClick={() => start.mutate({ template_id: preview.template_id })}
              >
                이 템플릿으로 설계 시작
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </div>
  );
}

function EntryButton({
  icon,
  title,
  description,
  onClick,
  primary,
  disabled,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex cursor-pointer flex-col items-start gap-2 rounded-lg border px-4 py-4 text-left transition-colors duration-150 disabled:opacity-50 [&_svg]:size-5",
        primary
          ? "border-primary/60 bg-primary-soft hover:border-primary-text [&_svg]:text-primary-text"
          : "border-border-strong hover:bg-surface-2 [&_svg]:text-muted",
      )}
    >
      {icon}
      <span className="text-sm font-semibold">{title}</span>
      <span className="text-xs text-muted">{description}</span>
    </button>
  );
}

function TemplatePreview({ template }: { template: Template }) {
  const spec = template.spec;
  const depts = new Map(spec.departments.map((d) => [d.key, d.name]));
  return (
    <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
      <div className="h-[380px] overflow-hidden rounded-md border border-border">
        <OrgChart spec={spec} />
      </div>
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-muted">{spec.mission}</p>
        <div>
          <h4 className="mb-1.5 text-xs font-semibold text-muted">에이전트 {spec.agents.length}명</h4>
          <ul className="flex flex-col gap-1.5">
            {spec.agents.map((a) => (
              <li key={a.key}>
                <span className="font-medium">{a.name}</span>
                <span className="text-xs text-faint"> · {a.title}{a.department ? ` · ${depts.get(a.department)}` : ""}</span>
                <p className="text-xs text-muted">{a.role}</p>
              </li>
            ))}
          </ul>
        </div>
        {spec.workflows.map((w) => (
          <div key={w.name}>
            <h4 className="mb-1 text-xs font-semibold text-muted">기본 업무 흐름 — {w.name}</h4>
            <ol className="flex flex-wrap items-center gap-1 text-xs">
              {w.steps.map((s, i) => (
                <li key={s} className="flex items-center gap-1">
                  {i > 0 ? <span className="text-faint" aria-hidden>›</span> : null}
                  <span className="rounded-sm bg-surface-3 px-1.5 py-0.5">{s}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
        {spec.recommended_skills.length + spec.recommended_mcp.length > 0 ? (
          <p className="text-xs text-faint">
            추천 Skills: {spec.recommended_skills.join(", ") || "없음"} · 추천 MCP: {spec.recommended_mcp.join(", ") || "없음"}
            <br />
            설치 여부는 설계를 시작하면 이 컴퓨터 기준으로 확인합니다.
          </p>
        ) : null}
      </div>
    </div>
  );
}
