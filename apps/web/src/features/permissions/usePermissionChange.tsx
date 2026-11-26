/**
 * 권한 변경 저장(권한 표·팝오버·조직도 프리셋·에이전트 설정 공용).
 * 권한이 넓어지는 변경(lib/permissions.ts의 escalations)은 확인 창을 거친 뒤에만 저장한다.
 * 저장은 기존 에이전트 PATCH API를 에이전트마다 한 번씩 부른다.
 *
 * 오래된 값으로 저장하지 않기 위한 장치 셋:
 * 1. 호출한 화면이 준 값이 아니라 캐시의 최신 값을 기준으로 변경을 다시 얹는다(rebasePermissions). 확대 판정도 그 기준으로 한다.
 * 2. PATCH 응답으로 캐시를 바로 갱신한다(다음 변경의 기준이 항상 방금 저장된 서버 값).
 * 3. 저장하고 다시 불러오기가 끝날 때까지 pending이 참이다(이 훅을 쓰는 모든 화면이 함께 잠긴다). 그동안의 요청은 버린다.
 */

import { type QueryClient, useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/overlay";
import { type Agent, type AgentPermissions, type Organization, api } from "@/lib/api";
import { admitChange, escalations, rebasePermissions, samePermissions } from "@/lib/permissions";

export interface PermissionChange {
  /** permissions는 변경을 만들 때 화면이 보고 있던 값(기준). */
  agent: Pick<Agent, "id" | "name" | "organization_id" | "permissions">;
  next: AgentPermissions;
}

export interface RequestOptions {
  /** 확인 창 제목에 붙일 설명(예: "프리셋 '자율' 적용"). */
  label?: string;
  /** 확인 창이 닫힌 뒤 포커스를 돌려줄 요소(연 요소가 메뉴 항목처럼 사라지는 경우). */
  returnFocus?: HTMLElement | null;
}

export type RequestPermissionChange = (changes: PermissionChange[], options?: RequestOptions) => void;

const MUTATION_KEY = ["permission-change"];

class SaveError extends Error {
  constructor(
    message: string,
    readonly saved: number,
    readonly original: unknown,
  ) {
    super(message);
  }
}

/** 캐시에 있는 그 에이전트의 가장 최근 권한(에이전트 상세·조직 캐시 중 updated_at이 늦은 쪽). 없으면 null. */
function latestPermissions(queryClient: QueryClient, agentId: string): AgentPermissions | null {
  const found: Agent[] = [];
  const single = queryClient.getQueryData<Agent>(["agent", agentId]);
  if (single) found.push(single);
  for (const [, org] of queryClient.getQueriesData<Organization>({ queryKey: ["organization"] })) {
    const agent = org?.agents?.find((a) => a.id === agentId);
    if (agent) found.push(agent);
  }
  found.sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0));
  return found[0]?.permissions ?? null;
}

/** PATCH 응답을 캐시에 바로 넣는다. */
function storeAgent(queryClient: QueryClient, agent: Agent) {
  queryClient.setQueryData<Agent>(["agent", agent.id], (old) => (old ? agent : old));
  queryClient.setQueriesData<Organization>({ queryKey: ["organization"] }, (org) =>
    org?.agents?.some((a) => a.id === agent.id) ? { ...org, agents: org.agents.map((a) => (a.id === agent.id ? agent : a)) } : org,
  );
}

export function usePermissionChange(): {
  request: RequestPermissionChange;
  dialog: ReactNode;
  confirming: boolean;
  /** 저장 중이거나 저장 뒤 다시 불러오는 중. 이 동안 칸·모드·프리셋을 잠근다. */
  pending: boolean;
  /** 마지막 저장이 실패했을 때 서버가 준 오류(ApiError). 다음 저장을 시작하면 지워진다. */
  error: unknown;
} {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState<{ label?: string; changes: PermissionChange[] } | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  // 버튼의 disabled가 화면에 반영되기 전의 연타도 막는다.
  const busy = useRef(false);
  const pending = useIsMutating({ mutationKey: MUTATION_KEY }) > 0;

  /** 화면이 준 변경을 캐시의 최신 값 위에 다시 얹고, 바뀌는 것이 없는 항목은 뺀다. */
  const rebase = (changes: PermissionChange[]): PermissionChange[] =>
    changes
      .map(({ agent, next }) => {
        const latest = latestPermissions(queryClient, agent.id) ?? agent.permissions;
        return { agent: { ...agent, permissions: latest }, next: rebasePermissions(agent.permissions, next, latest) };
      })
      .filter((c) => !samePermissions(c.agent.permissions, c.next));

  const save = useMutation({
    mutationKey: MUTATION_KEY,
    mutationFn: async (changes: PermissionChange[]) => {
      let saved = 0;
      for (const { agent, next } of changes) {
        try {
          const updated = await api<Agent>(`/organizations/${agent.organization_id}/agents/${agent.id}`, { method: "PATCH", body: { permissions: next } });
          storeAgent(queryClient, updated);
        } catch (e) {
          throw new SaveError(`${agent.name}: ${(e as Error).message}`, saved, e);
        }
        saved += 1;
      }
      return saved;
    },
    onSuccess: (saved) => toast.success(saved > 1 ? `에이전트 ${saved}명의 권한을 저장했습니다.` : "권한을 저장했습니다."),
    onError: (e) =>
      toast.error(e instanceof SaveError && e.saved > 0 ? `${e.message} (앞의 ${e.saved}명은 저장됨)` : e.message),
    // 다시 불러오기가 끝날 때까지 기다린다(그동안 pending).
    onSettled: async () => {
      try {
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: ["organization"] }),
          queryClient.invalidateQueries({ queryKey: ["agent"] }),
        ]);
      } finally {
        busy.current = false;
      }
    },
  });

  const start = (changes: PermissionChange[]) => {
    busy.current = true;
    save.mutate(changes);
  };

  const request: RequestPermissionChange = (changes, options) => {
    // 잠금 중 요청은 버리되 조용히 버리지 않는다(표·팝오버·조직도 프리셋·에이전트 설정 공통).
    if (!admitChange(busy.current || pending, (message) => toast.warning(message))) return;
    const effective = rebase(changes);
    if (effective.length === 0) {
      toast("이미 같은 권한입니다. 바뀌는 것이 없습니다.");
      return;
    }
    if (effective.some((c) => escalations(c.agent.permissions, c.next).length > 0)) {
      // 이 확인 창은 연 버튼(Dialog.Trigger)이 없어 Radix가 포커스를 돌려주지 못한다. 직전에 포커스가 있던 요소를 기억해 둔다.
      const active = document.activeElement;
      returnFocus.current = options?.returnFocus ?? (active instanceof HTMLElement ? active : null);
      setConfirm({ label: options?.label, changes: effective });
    } else start(effective);
  };

  const widened = (confirm?.changes ?? [])
    .map((c) => ({ agent: c.agent, reasons: escalations(c.agent.permissions, c.next) }))
    .filter((x) => x.reasons.length > 0);
  const others = (confirm?.changes.length ?? 0) - widened.length;

  const dialog = (
    <Dialog open={confirm !== null} onOpenChange={(open) => !open && setConfirm(null)}>
      <DialogContent
        title="권한을 넓힐까요?"
        description={
          confirm?.label
            ? `${confirm.label} — 아래 변경은 에이전트가 할 수 있는 일을 늘립니다.`
            : "아래 변경은 에이전트가 할 수 있는 일을 늘립니다."
        }
        onCloseAutoFocus={(event) => {
          const target = returnFocus.current;
          returnFocus.current = null;
          if (target?.isConnected) {
            event.preventDefault();
            target.focus();
          }
        }}
      >
        <ul className="flex flex-col gap-3" aria-label="넓어지는 권한">
          {widened.map(({ agent, reasons }) => (
            <li key={agent.id} className="flex flex-col gap-1">
              <span className="flex items-center gap-1.5 text-sm font-medium">
                <ShieldAlert className="size-4 shrink-0 text-warning" aria-hidden />
                {agent.name}
              </span>
              <ul className="list-disc pl-7 text-xs text-muted">
                {reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {others > 0 ? <p className="mt-3 text-xs text-faint">권한이 넓어지지 않는 에이전트 {others}명의 변경도 함께 저장합니다.</p> : null}
        <p className="mt-3 text-xs text-faint">꺼 둔 도구와 작업 폴더 밖 경로는 어떤 모드·허용 규칙으로도 열리지 않습니다.</p>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setConfirm(null)}>
            취소
          </Button>
          <Button
            variant="warning"
            onClick={() => {
              // 확인 창이 떠 있는 동안 값이 바뀌었을 수 있다('항상 허용' 등). 저장 직전에 한 번 더 최신 값에 얹는다.
              setConfirm(null);
              if (!confirm || !admitChange(busy.current || pending, (message) => toast.warning(message))) return;
              const changes = rebase(confirm.changes);
              if (changes.length > 0) start(changes);
              else toast("이미 같은 권한입니다. 바뀌는 것이 없습니다.");
            }}
          >
            권한 확대 적용
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return {
    request,
    dialog,
    confirming: confirm !== null,
    pending,
    error: save.error instanceof SaveError ? save.error.original : save.error,
  };
}
