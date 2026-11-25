import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Gauge, OctagonAlert, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState, PageHeader, Section } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Input, Switch } from "@/components/ui/form";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/overlay";
import { type UsagePayload, type UsageProvider, type UsageWindow, api } from "@/lib/api";
import { useUsage } from "@/lib/queries";
import { cn, timeAgo } from "@/lib/utils";

import { UsageChart } from "./UsageChart";

const STATE_TEXT: Record<UsageProvider["state"], string> = {
  ok: "",
  disabled: "꺼져 있습니다.",
  pending: "조회 중입니다…",
  not_logged_in: "로그인 정보를 찾지 못했습니다.",
  token_expired: "로그인 토큰이 만료되었습니다.",
  rate_limited: "사용량 API가 잠시 막혔습니다.",
  error: "조회하지 못했습니다.",
  no_data: "표시할 사용량이 없습니다.",
};

function level(percent: number): { label: string; color: string; Icon: typeof AlertTriangle | null } {
  if (percent >= 90) return { label: "위험", color: "var(--danger)", Icon: OctagonAlert };
  if (percent >= 75) return { label: "주의", color: "var(--warning)", Icon: AlertTriangle };
  return { label: "", color: "var(--chart-1)", Icon: null };
}

function until(iso: string | null): string {
  if (!iso) return "초기화 시각 모름";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "곧 초기화";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.round((ms % 3_600_000) / 60_000);
  return h >= 24 ? `${Math.floor(h / 24)}일 ${h % 24}시간 뒤 초기화` : `${h}시간 ${m}분 뒤 초기화`;
}

/** 사용량 막대: 채움 = 사용률, 세로선 = 기간 경과율. 막대가 선보다 앞서면 시간보다 빨리 쓰는 중. */
export function UsageMeter({ window: w, compact = false }: { window: UsageWindow; compact?: boolean }) {
  const lv = level(w.percent);
  return (
    <div className="flex flex-col gap-1">
      <div className={cn("relative overflow-hidden rounded-full bg-surface-3", compact ? "h-1.5" : "h-2.5")}>
        <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${Math.min(100, w.percent)}%`, background: lv.color }} />
        {w.elapsed_percent !== null ? (
          <div
            className="absolute top-0 h-full w-0.5 bg-fg/70"
            style={{ left: `${w.elapsed_percent}%` }}
            title={`기간 경과 ${w.elapsed_percent}%`}
            aria-hidden
          />
        ) : null}
      </div>
    </div>
  );
}

export function UsagePage() {
  const usage = useUsage();
  const queryClient = useQueryClient();
  const refresh = useMutation({
    mutationFn: () => api<UsagePayload>("/usage/refresh", { method: "POST" }),
    onSuccess: (d) => queryClient.setQueryData(["usage"], d),
    onError: (e) => toast.error(e.message),
  });
  const save = useMutation({
    mutationFn: (body: Partial<UsagePayload["settings"]>) => api<UsagePayload>("/usage/settings", { method: "PUT", body }),
    onSuccess: (d) => queryClient.setQueryData(["usage"], d),
    onError: (e) => toast.error(e.message),
  });
  if (usage.isLoading) return <LoadingState className="p-6" />;
  if (usage.error || !usage.data) return <ErrorState className="m-6" error={usage.error} retry={() => void usage.refetch()} />;
  const { settings, providers } = usage.data;

  return (
    <div className="flex-1 overflow-y-auto">
      <PageHeader
        title="사용량"
        description="Claude·Codex 사용률과 초기화까지 남은 시간, 소진 예측입니다. GigaCharge와 같은 방식으로 수집합니다."
        actions={
          <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            <RefreshCw className={cn(refresh.isPending && "animate-spin")} /> 새로 고침
          </Button>
        }
      />
      <div className="grid gap-8 px-6 pb-10 xl:grid-cols-[1.6fr_1fr]">
        <div className="flex flex-col gap-8">
          {providers.map((p) => (
            <ProviderSection key={p.id} provider={p} />
          ))}
        </div>
        <Section title="설정">
          <Switch
            label="Claude 사용량 조회"
            description="켜면 Claude Code CLI 로그인 토큰을 읽어(읽기만, 저장·갱신 안 함) Anthropic 사용량 API에 60초마다 조회합니다. 비공개 API라 바뀌면 멈출 수 있습니다."
            checked={settings.claude_enabled}
            onCheckedChange={(v) => save.mutate({ claude_enabled: v })}
          />
          <Switch
            label="Codex 사용량 읽기"
            description="Codex CLI가 남긴 세션 기록에서 사용률을 읽습니다(네트워크 없음)."
            checked={settings.codex_enabled}
            onCheckedChange={(v) => save.mutate({ codex_enabled: v })}
          />
          <ThresholdEditor thresholds={settings.thresholds} onSave={(thresholds) => save.mutate({ thresholds })} />
        </Section>
      </div>
    </div>
  );
}

function ThresholdEditor({ thresholds, onSave }: { thresholds: number[]; onSave: (t: number[]) => void }) {
  const [text, setText] = useState(thresholds.join(", "));
  return (
    <form
      className="flex flex-col gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        const values = text.split(/[,\s]+/).map(Number).filter((n) => Number.isFinite(n) && n >= 1 && n <= 100);
        if (values.length) onSave([...new Set(values)].sort((a, b) => a - b).slice(0, 5));
      }}
    >
      <label htmlFor="thresholds" className="text-xs font-medium text-muted">
        알림 임계치(%)
      </label>
      <div className="flex gap-2">
        <Input id="thresholds" value={text} onChange={(e) => setText(e.target.value)} inputMode="numeric" />
        <Button type="submit">저장</Button>
      </div>
      <p className="text-xs text-faint">값이 이 선을 처음 넘을 때 웹 알림(토스트)과 활동 기록을 남깁니다. 최대 5개.</p>
    </form>
  );
}

function ProviderSection({ provider: p }: { provider: UsageProvider }) {
  const [windowId, setWindowId] = useState<string | null>(null);
  const [hours, setHours] = useState("24");
  const selected = p.windows.find((w) => w.id === windowId) ?? p.windows[0];
  const history = useQuery({
    queryKey: ["usage-history", p.id, selected?.id, hours],
    queryFn: () => api<{ at: string; percent: number }[]>(`/usage/history?provider=${p.id}&window=${selected!.id}&hours=${hours}`),
    enabled: Boolean(selected),
  });
  return (
    <Section
      title={`${p.name}${p.plan ? ` · ${p.plan}` : ""}`}
      actions={p.observed_at ? <span className="text-xs text-faint">관측 {timeAgo(p.observed_at)}</span> : null}
    >
      {p.state !== "ok" ? (
        <EmptyState icon={<Gauge />} title={STATE_TEXT[p.state]}>
          {p.message}
        </EmptyState>
      ) : (
        <>
          <ul className="flex flex-col gap-5">
            {p.windows.map((w) => {
              const lv = level(w.percent);
              return (
                <li key={w.id} className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{w.label}</span>
                    <span className="flex items-baseline gap-2">
                      {lv.Icon ? (
                        <span className="flex items-center gap-1 text-xs" style={{ color: lv.color }}>
                          <lv.Icon className="size-3.5" aria-hidden /> {lv.label}
                        </span>
                      ) : null}
                      <span className="text-lg font-semibold tabular">{w.percent.toFixed(0)}%</span>
                    </span>
                  </div>
                  <UsageMeter window={w} />
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                    <span>{until(w.resets_at)}</span>
                    {w.elapsed_percent !== null ? <span className="tabular">기간 경과 {w.elapsed_percent.toFixed(0)}%</span> : null}
                    {w.confidence === "learning" ? (
                      <span className="text-faint">소진 예측: 학습 중(관측 {w.samples}개)</span>
                    ) : (
                      <>
                        <span className="tabular">시간당 {w.burn_rate_per_hour?.toFixed(1)}%p</span>
                        {w.projected_at_reset !== null ? <span className="tabular">초기화 때 예상 {w.projected_at_reset.toFixed(0)}%</span> : null}
                        {w.exhaust_at ? <span style={{ color: "var(--danger)" }}>{new Date(w.exhaust_at).toLocaleString("ko")} 소진 예상</span> : null}
                        {w.confidence === "low" ? <span className="text-faint">(신뢰도 낮음)</span> : null}
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {selected ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-3">
                {p.windows.length > 1 ? (
                  <Tabs value={selected.id} onValueChange={setWindowId}>
                    <TabsList>
                      {p.windows.map((w) => (
                        <TabsTrigger key={w.id} value={w.id}>
                          {w.label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                ) : null}
                <Tabs value={hours} onValueChange={setHours} className="ml-auto">
                  <TabsList>
                    <TabsTrigger value="24">24시간</TabsTrigger>
                    <TabsTrigger value="168">7일</TabsTrigger>
                    <TabsTrigger value="720">30일</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              <UsageChart points={history.data ?? []} title={`${p.name} ${selected.label} 사용률 추이`} />
            </div>
          ) : null}
        </>
      )}
    </Section>
  );
}
