/**
 * 커맨드 센터(운영 모드): 대화 목록 · 채팅 · 실행 패널.
 * 스트리밍 텍스트와 도구 활동은 WebSocket 이벤트로 받아 화면에만 누적하고, 완료되면 서버의 확정본으로 바꾼다.
 */

import { useIsMutating, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Check,
  CheckCheck,
  FolderGit2,
  GitBranch,
  Hand,
  MessageSquarePlus,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  ShieldAlert,
  Sparkles,
  User,
  Users,
  X,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { AgentStatus, EmptyState, ErrorState, LoadingState } from "@/components/common/states";
import { Button, IconButton } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form";
import { Dialog, DialogContent, DialogFooter, Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from "@/components/ui/overlay";
import {
  type ActivityEntry,
  type Agent,
  type ApprovalRequest,
  type ApprovalSource,
  type ContextItem,
  type Conversation,
  type ConversationDetail,
  type DecisionRequest,
  type DecisionResponse,
  type Task,
  api,
} from "@/lib/api";
import { PermissionPopover } from "@/features/permissions/PermissionPopover";
import { usePermissionChange } from "@/features/permissions/usePermissionChange";
import { onLive } from "@/lib/live";
import {
  useApprovals,
  useCapabilities,
  useCommands,
  useConversation,
  useConversations,
  useCurrentOrg,
  useOrganization,
  useProjects,
  useTasks,
} from "@/lib/queries";
import { cn, timeAgo } from "@/lib/utils";
import { TaskStatus } from "@/features/dashboard/DashboardPage";

import { Composer, type SendPayload } from "./Composer";
import { ACTIVITY_LABELS, MessageView } from "./Messages";

const PANEL_KEY = "ai-org.command.panel";

export function CommandCenter() {
  const { orgId } = useCurrentOrg();
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const org = useOrganization(orgId);
  const conversations = useConversations(orgId);
  const queryClient = useQueryClient();
  const [panelOpen, setPanelOpen] = useState(() => localStorage.getItem(PANEL_KEY) !== "closed");
  const [newOpen, setNewOpen] = useState(false);

  // 대화를 고르지 않았으면 가장 최근 대화로.
  useEffect(() => {
    if (!conversationId && conversations.data?.[0]) navigate(`/command/${conversations.data[0].id}`, { replace: true });
  }, [conversationId, conversations.data, navigate]);

  const create = useMutation({
    mutationFn: (body: { target_kind: string; target_id: string | null }) =>
      api<Conversation>("/conversations", { method: "POST", body: { organization_id: orgId, ...body } }),
    onSuccess: (c) => {
      void queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
      setNewOpen(false);
      navigate(`/command/${c.id}`);
    },
    onError: (e) => toast.error(e.message),
  });

  if (!orgId)
    return (
      <div className="p-6">
        <EmptyState icon={<Sparkles />} title="조직이 필요합니다" action={<Button variant="primary" asChild><Link to="/builder">조직 설계 시작</Link></Button>}>
          커맨드 센터에서는 조직의 CEO·팀·에이전트에게 일을 맡깁니다.
        </EmptyState>
      </div>
    );
  const agents = org.data?.agents ?? [];

  return (
    <div className={cn("grid h-full min-h-0", panelOpen ? "grid-cols-[240px_1fr_320px]" : "grid-cols-[240px_1fr]", "max-xl:grid-cols-[220px_1fr]")}>
      <aside className="flex min-h-0 flex-col border-r border-border bg-surface-1" aria-label="대화 목록">
        <div className="flex items-center justify-between px-3 py-2.5">
          <h1 className="text-sm font-semibold">대화</h1>
          <IconButton label="새 대화" size="icon-sm" onClick={() => setNewOpen(true)}>
            <MessageSquarePlus />
          </IconButton>
        </div>
        <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-3">
          {conversations.isLoading ? <LoadingState /> : null}
          {conversations.data?.length === 0 ? (
            <li className="px-2 py-2 text-xs text-faint">아직 대화가 없습니다. 새 대화로 CEO에게 첫 업무를 지시하세요.</li>
          ) : null}
          {(conversations.data ?? []).map((c) => (
            <li key={c.id}>
              <Link
                to={`/command/${c.id}`}
                className={cn(
                  "flex flex-col gap-0.5 rounded-md px-2 py-1.5 transition-colors",
                  c.id === conversationId ? "bg-surface-3" : "hover:bg-surface-2",
                )}
              >
                <span className="flex items-center gap-1.5 text-sm">
                  {c.busy ? <span className="status-pulse size-1.5 shrink-0 rounded-full bg-[var(--status-working)]" aria-label="실행 중" /> : null}
                  <span className="truncate">{c.title}</span>
                </span>
                <span className="flex items-center gap-1 truncate text-2xs text-faint">
                  <TargetIcon kind={c.target_kind} />
                  {targetName(c, org.data)} · {timeAgo(c.updated_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </aside>

      {conversationId ? (
        <ChatPane
          key={conversationId}
          conversationId={conversationId}
          agents={agents}
          panelOpen={panelOpen}
          togglePanel={() => {
            localStorage.setItem(PANEL_KEY, panelOpen ? "closed" : "open");
            setPanelOpen(!panelOpen);
          }}
        />
      ) : (
        <div className="p-6">
          <EmptyState
            icon={<MessageSquarePlus />}
            title="대화를 시작하세요"
            action={
              <Button variant="primary" onClick={() => create.mutate({ target_kind: "org", target_id: null })}>
                CEO에게 업무 지시
              </Button>
            }
          >
            조직 전체(CEO), 특정 팀, 개별 에이전트와 대화할 수 있습니다.
          </EmptyState>
        </div>
      )}

      {panelOpen ? <ExecutionPanel orgId={orgId} agents={agents} conversationId={conversationId ?? null} /> : null}

      <Dialog open={newOpen} onOpenChange={setNewOpen}>
        <NewConversation org={org.data} onCreate={(kind, id) => create.mutate({ target_kind: kind, target_id: id })} pending={create.isPending} />
      </Dialog>
    </div>
  );
}

function TargetIcon({ kind }: { kind: Conversation["target_kind"] }) {
  const Icon = kind === "org" ? Building2 : kind === "team" ? Users : User;
  return <Icon className="size-3 shrink-0" aria-hidden />;
}

function targetName(c: Conversation, org: ReturnType<typeof useOrganization>["data"]): string {
  if (c.target_kind === "org") return "조직 전체(CEO)";
  if (c.target_kind === "team") return org?.departments.find((d) => d.id === c.target_id)?.name ?? "팀";
  return org?.agents.find((a) => a.id === c.target_id)?.name ?? "에이전트";
}

function NewConversation({
  org,
  onCreate,
  pending,
}: {
  org: ReturnType<typeof useOrganization>["data"];
  onCreate: (kind: string, id: string | null) => void;
  pending: boolean;
}) {
  const [value, setValue] = useState("org:");
  const [kind, id] = value.split(":") as [string, string];
  return (
    <DialogContent title="새 대화" description="누구와 이야기할지 고르세요. CEO에게 말하면 조직 전체를 대표해 분배 계획을 세웁니다.">
      <Field label="대화 대상">
        {(fid) => (
          <Select id={fid} value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="org:">조직 전체(CEO)</option>
            <optgroup label="팀">
              {(org?.departments ?? []).map((d) => (
                <option key={d.id} value={`team:${d.id}`}>
                  {d.name}
                </option>
              ))}
            </optgroup>
            <optgroup label="에이전트">
              {(org?.agents ?? []).filter((a) => a.enabled).map((a) => (
                <option key={a.id} value={`agent:${a.id}`}>
                  {a.name}
                  {a.title ? ` — ${a.title}` : ""}
                </option>
              ))}
            </optgroup>
          </Select>
        )}
      </Field>
      <DialogFooter>
        <Button variant="primary" disabled={pending} onClick={() => onCreate(kind, id || null)}>
          대화 시작
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}

// ── 채팅 ──────────────────────────────────────────────────────────────────

function ChatPane({
  conversationId,
  agents,
  panelOpen,
  togglePanel,
}: {
  conversationId: string;
  agents: Agent[];
  panelOpen: boolean;
  togglePanel: () => void;
}) {
  const conv = useConversation(conversationId);
  const commands = useCommands();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { orgId } = useCurrentOrg();
  const [liveText, setLiveText] = useState<Record<string, string>>({});
  const [liveActivity, setLiveActivity] = useState<Record<string, ActivityEntry[]>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const agentById = useMemo(() => new Map(agents.map((a) => [a.id, a])), [agents]);

  useEffect(
    () =>
      onLive((event) => {
        if (event.conversation_id !== conversationId) return;
        if (event.type === "message.delta") {
          const id = String(event.message_id);
          setLiveText((t) => ({ ...t, [id]: (t[id] ?? "") + String(event.text) }));
        } else if (event.type === "run.activity") {
          const id = String(event.message_id);
          const entry = event.entry as ActivityEntry;
          setLiveActivity((a) => {
            const list = a[id] ?? [];
            const i = list.findIndex((x) => x.id === entry.id);
            return { ...a, [id]: i >= 0 ? list.map((x, j) => (j === i ? entry : x)) : [...list, entry] };
          });
        } else if (event.type === "message.created" || event.type === "message.status") {
          void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
        }
      }),
    [conversationId, queryClient],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [conv.data?.messages.length, liveText, liveActivity]);

  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["conversation", conversationId] });
  const send = async (p: SendPayload) => {
    try {
      await api(`/conversations/${conversationId}/messages`, {
        method: "POST",
        body: { content: p.content, mention_agent_ids: p.mentionIds, mention_all: p.mentionAll, attachment_ids: p.attachmentIds },
      });
      stick.current = true;
      refresh();
    } catch (e) {
      toast.error((e as Error).message);
      throw e;
    }
  };
  const runCommand = async (name: string, args: Record<string, string>) => {
    const msg = await api<ConversationDetail["messages"][number]>(`/conversations/${conversationId}/commands`, {
      method: "POST",
      body: { name, args },
    });
    refresh();
    const action = msg.data.result?.action;
    if (action?.type === "conversation.open" && action.id) {
      void queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
      navigate(`/command/${action.id}`);
    } else if (action?.type === "conversation.updated") {
      void queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
    } else if (action?.type === "approvals.open" && !panelOpen) togglePanel();
  };
  const stop = () =>
    void api<{ stopped: number }>(`/conversations/${conversationId}/stop`, { method: "POST" }).then((r) =>
      toast(r.stopped ? `실행 ${r.stopped}개를 중지했습니다.` : "실행 중인 작업이 없습니다."),
    );
  const regenerate = (messageId: string) =>
    void api(`/conversations/${conversationId}/messages/${messageId}/regenerate`, { method: "POST" })
      .then(refresh)
      .catch((e: Error) => toast.error(e.message));

  if (conv.isLoading) return <LoadingState className="p-6" />;
  if (conv.error || !conv.data) return <ErrorState className="m-6" error={conv.error} retry={() => void conv.refetch()} />;
  const c = conv.data;
  const busy = c.messages.some((m) => m.status === "pending" || m.status === "streaming");
  const target =
    c.target_kind === "agent"
      ? agentById.get(c.target_id ?? "")?.name
      : c.target_kind === "team"
        ? "팀"
        : "CEO";

  return (
    <section className="flex min-h-0 min-w-0 flex-col" aria-label="채팅">
      <ChatHeader conversation={c} agents={agents} panelOpen={panelOpen} togglePanel={togglePanel} />
      <div
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="min-h-0 flex-1 overflow-y-auto"
        aria-live="polite"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-5 py-6">
          {c.messages.length === 0 ? (
            <div className="flex flex-col gap-2 text-sm text-muted">
              <p className="text-fg">무엇을 맡길까요?</p>
              <p>
                메시지는 {c.target_kind === "org" ? "CEO가 받아 분석하고 분배 계획을 세웁니다" : `${target ?? "대상"}에게 바로 전달됩니다`}.
                <code className="mx-1 font-mono text-xs">@이름</code>으로 특정 에이전트에게,
                <code className="mx-1 font-mono text-xs">/delegate</code>로 작업을 위임할 수 있습니다.
              </p>
            </div>
          ) : null}
          {c.messages.map((m) => (
            // 방금 생긴 메시지만 떠오르며 나타난다(대화를 열 때 불러온 기록은 그대로).
            <div key={m.id} className={cn(Date.now() - Date.parse(m.created_at) < 8_000 && "message-in")}>
            <MessageView
              message={m}
              agent={m.agent_id ? agentById.get(m.agent_id) : undefined}
              delegatedBy={m.data.delegated_by ? agentById.get(m.data.delegated_by) : undefined}
              liveText={liveText[m.id]}
              liveActivity={liveActivity[m.id]}
              onRegenerate={m.role === "assistant" && !busy ? () => regenerate(m.id) : undefined}
              onAction={() => !panelOpen && togglePanel()}
            />
            </div>
          ))}
        </div>
      </div>
      <PendingApprovalBanner conversationId={c.id} agents={agents} />
      <div className="mx-auto w-full max-w-3xl">
        <Composer
          agents={agents}
          commands={commands.data ?? []}
          busy={busy}
          onSend={send}
          onCommand={runCommand}
          onStop={stop}
          placeholder={`${target ?? "대상"}에게 메시지 보내기…`}
        />
      </div>
    </section>
  );
}

function ChatHeader({
  conversation,
  agents,
  panelOpen,
  togglePanel,
}: {
  conversation: ConversationDetail;
  agents: Agent[];
  panelOpen: boolean;
  togglePanel: () => void;
}) {
  const { orgId } = useCurrentOrg();
  const org = useOrganization(orgId);
  const projects = useProjects();
  const tasks = useTasks(orgId);
  const caps = useCapabilities();
  const queryClient = useQueryClient();
  const [pathOpen, setPathOpen] = useState(false);
  const [repo, setRepo] = useState("");
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/conversations/${conversation.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["conversation", conversation.id] });
      void queryClient.invalidateQueries({ queryKey: ["conversations", orgId] });
    },
    onError: (e) => toast.error(e.message),
  });
  const ctx = conversation.context;
  const addContext = (item: ContextItem) => {
    if (ctx.some((x) => x.kind === item.kind && x.ref === item.ref)) return;
    patch.mutate({ context: [...ctx, item] });
  };
  const project = projects.data?.find((p) => p.id === conversation.project_id);
  const targetValue = conversation.target_kind === "org" ? "org:" : `${conversation.target_kind}:${conversation.target_id}`;
  const doneTasks = (tasks.data ?? []).filter((t) => t.status === "done").slice(0, 10);

  return (
    <header className="flex flex-col gap-2 border-b border-border px-4 py-2.5">
      <div className="flex items-center gap-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{conversation.title}</h2>
        <Select
          aria-label="대화 대상"
          className="h-7 w-48 text-xs"
          value={targetValue}
          onChange={(e) => {
            const [kind, id] = e.target.value.split(":");
            patch.mutate({ target_kind: kind, target_id: id || null });
          }}
        >
          <option value="org:">조직 전체(CEO)</option>
          {(org.data?.departments ?? []).map((d) => (
            <option key={d.id} value={`team:${d.id}`}>
              팀 · {d.name}
            </option>
          ))}
          {agents.filter((a) => a.enabled).map((a) => (
            <option key={a.id} value={`agent:${a.id}`}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="연결된 프로젝트"
          className="h-7 w-44 text-xs"
          value={conversation.project_id ?? ""}
          onChange={(e) => patch.mutate({ project_id: e.target.value || null, context: ctx.filter((x) => x.kind !== "path") })}
        >
          <option value="">프로젝트 없음(전용 작업 폴더)</option>
          {(projects.data ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <IconButton label={panelOpen ? "실행 패널 닫기" : "실행 패널 열기"} size="icon-sm" onClick={togglePanel}>
          {panelOpen ? <PanelRightClose /> : <PanelRightOpen />}
        </IconButton>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {project ? (
          <span className="flex items-center gap-1 rounded-sm bg-surface-3 px-1.5 py-0.5 text-2xs text-muted" title={project.path}>
            <FolderGit2 className="size-3" aria-hidden /> {project.name}
          </span>
        ) : null}
        {ctx.map((item) => (
          <span key={`${item.kind}:${item.ref}`} className="flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-2xs text-muted">
            {item.kind === "github" ? <GitBranch className="size-3" aria-hidden /> : null}
            <span className="max-w-48 truncate">{item.label || item.ref}</span>
            <button
              type="button"
              aria-label={`${item.label || item.ref} 컨텍스트 제거`}
              className="cursor-pointer text-faint hover:text-fg"
              onClick={() => patch.mutate({ context: ctx.filter((x) => x !== item) })}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        <Menu>
          <MenuTrigger className="flex cursor-pointer items-center gap-1 rounded-sm px-1.5 py-0.5 text-2xs text-faint hover:bg-surface-2 hover:text-fg">
            <Plus className="size-3" aria-hidden /> 컨텍스트
          </MenuTrigger>
          <MenuContent align="start" className="w-64">
            <MenuItem disabled={!project} onSelect={() => setPathOpen(true)}>
              프로젝트 폴더·파일{!project ? " (프로젝트 먼저 연결)" : ""}
            </MenuItem>
            <MenuLabel>에이전트 소개</MenuLabel>
            {agents.slice(0, 8).map((a) => (
              <MenuItem key={a.id} onSelect={() => addContext({ kind: "agent", ref: a.id, label: `@${a.name}` })}>
                {a.name}
              </MenuItem>
            ))}
            {doneTasks.length ? <MenuLabel>이전 작업 결과</MenuLabel> : null}
            {doneTasks.map((t) => (
              <MenuItem key={t.id} onSelect={() => addContext({ kind: "task", ref: t.id, label: `작업: ${t.title}` })}>
                <span className="truncate">{t.title}</span>
              </MenuItem>
            ))}
            {(caps.data ?? []).filter((x) => x.kind === "skill").length ? <MenuLabel>Skills 정보</MenuLabel> : null}
            {(caps.data ?? [])
              .filter((x) => x.kind === "skill")
              .slice(0, 6)
              .map((cap) => (
                <MenuItem key={cap.id} onSelect={() => addContext({ kind: "capability", ref: cap.name, label: `Skill: ${cap.name}` })}>
                  {cap.name}
                </MenuItem>
              ))}
          </MenuContent>
        </Menu>
        <form
          className="flex items-center"
          onSubmit={(e) => {
            e.preventDefault();
            if (/^[\w.-]+\/[\w.-]+$/.test(repo.trim())) {
              addContext({ kind: "github", ref: repo.trim(), label: repo.trim() });
              setRepo("");
            } else toast.error("GitHub 저장소는 owner/repo 형식으로 입력하세요.");
          }}
        >
          <Input
            aria-label="GitHub 저장소(owner/repo)"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="GitHub owner/repo…"
            className="h-6 w-40 text-2xs"
            spellCheck={false}
          />
        </form>
      </div>
      {project ? (
        <PathPicker
          open={pathOpen}
          onOpenChange={setPathOpen}
          projectId={project.id}
          onPick={(path) => addContext({ kind: "path", ref: path, label: path || project.name })}
        />
      ) : null}
    </header>
  );
}

function PathPicker({
  open,
  onOpenChange,
  projectId,
  onPick,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: string;
  onPick: (path: string) => void;
}) {
  const [dir, setDir] = useState("");
  const [entries, setEntries] = useState<{ name: string; path: string; is_dir: boolean }[] | null>(null);
  useEffect(() => {
    if (!open) return;
    setEntries(null);
    void api<{ path: string; entries: { name: string; path: string; is_dir: boolean }[] }>(
      `/projects/${projectId}/tree?path=${encodeURIComponent(dir)}`,
    )
      .then((r) => setEntries(r.entries))
      .catch((e: Error) => toast.error(e.message));
  }, [open, dir, projectId]);
  const parent = dir.includes("/") ? dir.slice(0, dir.lastIndexOf("/")) : "";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="컨텍스트로 넣을 폴더·파일" description="프로젝트 안의 경로만 고를 수 있습니다. 에이전트는 내용을 자기 권한 안에서 직접 읽습니다.">
        <p className="mb-2 font-mono text-xs text-muted">/{dir}</p>
        {entries === null ? <LoadingState /> : null}
        <ul className="flex max-h-80 flex-col overflow-y-auto">
          {dir ? (
            <li>
              <button type="button" className="w-full cursor-pointer rounded-sm px-2 py-1 text-left text-sm text-muted hover:bg-surface-2" onClick={() => setDir(parent)}>
                ..
              </button>
            </li>
          ) : null}
          {(entries ?? []).map((e) => (
            <li key={e.path} className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-surface-2">
              {e.is_dir ? (
                <button type="button" className="min-w-0 flex-1 cursor-pointer truncate text-left text-sm" onClick={() => setDir(e.path)}>
                  {e.name}/
                </button>
              ) : (
                <span className="min-w-0 flex-1 truncate text-sm text-muted">{e.name}</span>
              )}
              <Button size="sm" variant="ghost" onClick={() => { onPick(e.path); onOpenChange(false); }}>
                추가
              </Button>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button onClick={() => { onPick(dir); onOpenChange(false); }}>현재 폴더 추가</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── 승인·실행 패널 ────────────────────────────────────────────────────────

const DECISION_KEY = ["approval-decision"];

/**
 * 승인 결정. busy는 결정 요청을 보내고 승인 목록을 다시 받을 때까지 참이다(배너·실행 패널이 함께 본다).
 * 그동안 결정 버튼을 잠가, 이미 처리된 요청을 다시 눌러 409가 나는 일을 막는다.
 */
function useDecide() {
  const queryClient = useQueryClient();
  const busy = useIsMutating({ mutationKey: DECISION_KEY }) > 0;
  const mutation = useMutation({
    mutationKey: DECISION_KEY,
    mutationFn: ({ id, allow, always }: { id: string } & DecisionRequest) =>
      api<DecisionResponse>(`/approvals/${id}/decision`, { method: "POST", body: always ? { allow, always } : { allow } }),
    // 목록을 다시 받을 때까지 기다린다(그동안 busy).
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
    onSuccess: (result) => {
      if (!result.always) return;
      // '항상 허용': 규칙이 그 에이전트의 허용 리스트에 더해졌으면 권한을 다시 불러온다.
      const { rule, added, reason } = result.always;
      if (rule === null) toast.warning(`이번만 허용했습니다. ${reason ?? "규칙을 만들 수 없는 요청입니다."}`);
      else toast.success(added ? `허용 규칙을 추가했습니다: ${rule}` : `이미 있는 허용 규칙입니다: ${rule}`);
      void queryClient.invalidateQueries({ queryKey: ["organization"] });
      void queryClient.invalidateQueries({ queryKey: ["agent"] });
    },
    onError: (e) => toast.error(e.message),
  });
  return { mutate: mutation.mutate, busy };
}

/**
 * 승인 요청의 결정 버튼: 거부 · 권한 보기 · 이번만 허용 · 항상 허용.
 * '항상 허용'은 추가될 규칙을 글자로 보여 준다. 규칙을 만들 수 없는 요청이면 버튼을 끄고 사유를 보인다.
 */
function ApprovalActions({
  id,
  agentId,
  alwaysRule,
  alwaysReason,
  source,
  decide,
}: {
  id: string;
  agentId: string;
  alwaysRule: string | null | undefined;
  alwaysReason: string | null | undefined;
  source?: ApprovalSource;
  decide: ReturnType<typeof useDecide>;
}) {
  const noteId = useId();
  return (
    <>
      <p id={noteId} className="text-xs text-muted">
        {source === "runtime" ? <span className="block text-faint">auto 모드에서 Claude Code가 확인을 요청했습니다.</span> : null}
        {alwaysRule ? (
          <>
            '항상 허용'을 누르면 이 에이전트의 허용 규칙에 추가됩니다:{" "}
            <code className="font-mono break-all text-fg">{alwaysRule}</code>
            {/^Bash\(.*:\*\)$/.test(alwaysRule) ? (
              <span className="block text-faint">이 접두로 시작하는 명령은 앞으로 묻지 않습니다(스크립트를 실행하는 명령이면 그 내용까지).</span>
            ) : null}
          </>
        ) : (
          <>항상 허용할 수 없음: {alwaysReason || "이 요청으로는 허용 규칙을 만들 수 없습니다."}</>
        )}
      </p>
      <span className="flex flex-wrap items-center justify-end gap-1.5">
        <Button size="sm" variant="ghost" asChild>
          <Link to={`/agents/${agentId}?tab=settings`}>
            <ShieldAlert /> 권한 보기
          </Link>
        </Button>
        <Button size="sm" variant="ghost" disabled={decide.busy} onClick={() => decide.mutate({ id, allow: false })}>
          거부
        </Button>
        <Button size="sm" variant="secondary" disabled={decide.busy} onClick={() => decide.mutate({ id, allow: true })}>
          <Check /> 이번만 허용
        </Button>
        <Button
          size="sm"
          variant="warning"
          disabled={!alwaysRule || decide.busy}
          aria-describedby={noteId}
          onClick={() => decide.mutate({ id, allow: true, always: true })}
        >
          <CheckCheck /> 항상 허용
        </Button>
      </span>
    </>
  );
}

function PendingApprovalBanner({ conversationId, agents }: { conversationId: string; agents: Agent[] }) {
  const { orgId } = useCurrentOrg();
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [resolved, setResolved] = useState<Set<string>>(new Set());
  const approvals = useApprovals(orgId);
  const decide = useDecide();
  useEffect(
    () =>
      onLive((event) => {
        if (event.type === "approval.requested" && event.conversation_id === conversationId) {
          const a = event.approval as ApprovalRequest;
          setPending((p) => [...p.filter((x) => x.id !== a.id), a]);
        } else if (event.type === "approval.resolved") {
          const id = String(event.approval_id);
          setPending((p) => p.filter((x) => x.id !== id));
          setResolved((r) => new Set(r).add(id));
        }
      }),
    [conversationId],
  );
  // 서버 목록이 기준이다(새로고침 뒤에도 이 대화의 대기 요청이 보인다).
  // 실시간 이벤트는 목록을 다시 받는 동안의 틈만 메운다: 방금 온 요청은 먼저 보이고, 방금 처리된 요청은 먼저 사라진다.
  const listed = (approvals.data ?? []).filter((a) => a.detail?.conversation_id === conversationId);
  const fresh = !approvals.data || approvals.isFetching ? pending.filter((p) => !listed.some((a) => a.id === p.id)) : [];
  const open: ApprovalRequest[] = [
    ...listed.map((a) => ({
          id: a.id,
          agent_id: a.agent_id,
          agent_name: agents.find((x) => x.id === a.agent_id)?.name ?? "에이전트",
          tool: a.detail.tool ?? a.summary,
          target: a.detail.target ?? "",
          group: a.detail.group ?? null,
          reason: a.detail.reason,
          source: a.detail.source,
      always_rule: a.detail.always_rule,
      always_reason: a.detail.always_reason,
    })),
    ...fresh,
  ].filter((a) => !resolved.has(a.id));
  if (open.length === 0) return null;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-1.5 px-4 pb-2" role="alert">
      {open.map((a) => (
        <div key={a.id} className="flex flex-col gap-2 rounded-md border border-warning-border bg-warning-surface px-3 py-2">
          <div className="flex items-start gap-3">
            <Hand className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <span className="min-w-0 flex-1 text-sm">
              <span className="font-medium">{a.agent_name}</span>이(가) <span className="font-medium">{a.tool}</span> 실행 승인을 요청합니다
              {a.target ? <code className="mt-0.5 block truncate font-mono text-xs text-muted">{a.target}</code> : null}
              {a.reason ? <span className="mt-0.5 block text-xs text-warning">{a.reason}</span> : null}
            </span>
          </div>
          <ApprovalActions id={a.id} agentId={a.agent_id} alwaysRule={a.always_rule} alwaysReason={a.always_reason} source={a.source} decide={decide} />
        </div>
      ))}
    </div>
  );
}

function ExecutionPanel({ orgId, agents }: { orgId: string; agents: Agent[]; conversationId: string | null }) {
  const approvals = useApprovals(orgId);
  const tasks = useTasks(orgId);
  const decide = useDecide();
  const permissions = usePermissionChange();
  const agentOf = (id: string) => agents.find((a) => a.id === id);
  const [events, setEvents] = useState<{ key: string; agentId: string; entry: ActivityEntry }[]>([]);
  const [sections, setSections] = useState({ approvals: true, agents: true, events: true, tasks: true });
  useEffect(
    () =>
      onLive((event) => {
        if (event.type === "run.activity") {
          const entry = event.entry as ActivityEntry;
          setEvents((list) =>
            [{ key: `${entry.id}-${entry.status}`, agentId: String(event.agent_id), entry }, ...list.filter((x) => x.entry.id !== entry.id)].slice(0, 30),
          );
        }
      }),
    [],
  );
  const active = agents.filter((a) => ["thinking", "working", "waiting", "reviewing"].includes(a.status));
  const name = (id: string) => agents.find((a) => a.id === id)?.name ?? "—";
  const toggle = (k: keyof typeof sections) => setSections((s) => ({ ...s, [k]: !s[k] }));

  return (
    <aside className="flex min-h-0 flex-col overflow-y-auto border-l border-border bg-surface-1 max-xl:hidden" aria-label="실행 현황">
      <PanelSection title={`승인 대기 ${approvals.data?.length ?? 0}`} open={sections.approvals} onToggle={() => toggle("approvals")}>
        {(approvals.data ?? []).length === 0 ? <p className="text-xs text-faint">없음</p> : null}
        {(approvals.data ?? []).map((a) => {
          const agent = agentOf(a.agent_id);
          return (
            <div key={a.id} className="flex flex-col gap-1.5 rounded-md border border-warning-border bg-warning-surface px-2.5 py-2">
              <span className="flex items-center gap-1 text-xs">
                {agent ? (
                  <PermissionPopover
                    agent={agent}
                    request={permissions.request}
                    confirming={permissions.confirming}
                    pending={permissions.pending}
                    className="font-medium"
                  />
                ) : (
                  <span className="font-medium">—</span>
                )}
                <span className="shrink-0 text-faint"> · {timeAgo(a.created_at)}</span>
              </span>
              <code className="font-mono text-2xs break-all text-muted">{a.summary}</code>
              {a.detail?.reason ? <span className="text-2xs text-warning">{a.detail.reason}</span> : null}
              <ApprovalActions
                id={a.id}
                agentId={a.agent_id}
                alwaysRule={a.detail?.always_rule}
                alwaysReason={a.detail?.always_reason}
                source={a.detail?.source}
                decide={decide}
              />
            </div>
          );
        })}
      </PanelSection>
      <PanelSection title={`실행 중 ${active.length}`} open={sections.agents} onToggle={() => toggle("agents")}>
        {active.length === 0 ? <p className="text-xs text-faint">지금 일하는 에이전트가 없습니다.</p> : null}
        {active.map((a) => {
          const latest = events.find((e) => e.agentId === a.id);
          return (
            <div key={a.id} className="flex items-start gap-2">
              <AgentAvatar id={a.id} lead={a.is_lead} size={26} />
              <div className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2 text-sm">
                  <PermissionPopover agent={a} request={permissions.request} confirming={permissions.confirming} pending={permissions.pending} />
                  <AgentStatus status={a.status} />
                </span>
                {latest ? (
                  <span className="block truncate text-2xs text-faint" title={latest.entry.target}>
                    {latest.entry.tool} {latest.entry.target}
                  </span>
                ) : null}
              </div>
            </div>
          );
        })}
      </PanelSection>
      <PanelSection title="최근 도구 사용" open={sections.events} onToggle={() => toggle("events")}>
        {events.length === 0 ? <p className="text-xs text-faint">실행 이벤트가 오면 여기에 표시됩니다(새로고침하면 비워집니다).</p> : null}
        <ol className="flex flex-col gap-1">
          {events.map(({ key, agentId, entry }) => (
            <li key={key} className="flex items-center gap-2 text-2xs">
              <span className="w-14 shrink-0 truncate text-muted">{name(agentId)}</span>
              <span className="w-8 shrink-0 text-faint">{ACTIVITY_LABELS[entry.activity] ?? "도구"}</span>
              <span className="min-w-0 truncate font-mono text-faint" title={entry.target}>
                {entry.tool} {entry.target}
              </span>
              <span className={cn("ml-auto shrink-0", entry.status === "failed" ? "text-danger" : entry.status === "running" ? "text-primary-text" : "text-faint")}>
                {entry.status === "running" ? "실행" : entry.status === "failed" ? "실패" : "완료"}
              </span>
            </li>
          ))}
        </ol>
      </PanelSection>
      <PanelSection title="작업" open={sections.tasks} onToggle={() => toggle("tasks")}>
        {(tasks.data ?? []).length === 0 ? <p className="text-xs text-faint">/delegate로 만든 작업이 여기에 표시됩니다.</p> : null}
        {taskTree(tasks.data ?? []).slice(0, 16).map(({ task: t, depth }) => (
          <div key={t.id} className="flex items-center justify-between gap-2 text-xs" style={{ paddingLeft: depth * 12 }}>
            <span className="min-w-0 truncate">
              {depth > 0 ? <span className="mr-1 text-faint" aria-hidden>↳</span> : null}
              {t.title}
              {t.assignee_id ? <span className="ml-1.5 text-faint">{name(t.assignee_id)}</span> : null}
            </span>
            <TaskStatus status={t.status} />
          </div>
        ))}
      </PanelSection>
      <p className="mt-auto px-3 py-3 text-2xs text-faint">
        진행률은 표시하지 않습니다. Claude Code는 진행률을 알려 주지 않으며, 보이는 것은 모두 실제 실행 이벤트입니다.
      </p>
      {permissions.dialog}
    </aside>
  );
}

/** 위임 트리 순서로 펼친다(부모 바로 아래 자식). 최근 작업 트리가 위로. */
function taskTree(tasks: Task[]): { task: Task; depth: number }[] {
  const children = new Map<string, Task[]>();
  const ids = new Set(tasks.map((t) => t.id));
  for (const t of tasks) {
    if (t.parent_id && ids.has(t.parent_id)) children.set(t.parent_id, [...(children.get(t.parent_id) ?? []), t]);
  }
  const out: { task: Task; depth: number }[] = [];
  const visit = (t: Task, depth: number) => {
    out.push({ task: t, depth });
    (children.get(t.id) ?? []).slice().reverse().forEach((c) => visit(c, depth + 1));
  };
  tasks.filter((t) => !t.parent_id || !ids.has(t.parent_id)).forEach((t) => visit(t, 0));
  return out;
}

function PanelSection({ title, open, onToggle, children }: { title: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <section className="border-b border-border px-3 py-2.5">
      <button type="button" className="flex w-full cursor-pointer items-center justify-between text-xs font-semibold text-muted hover:text-fg" onClick={onToggle} aria-expanded={open}>
        {title}
        <span className="text-faint">{open ? "접기" : "펼치기"}</span>
      </button>
      {open ? <div className="mt-2 flex flex-col gap-2">{children}</div> : null}
    </section>
  );
}
