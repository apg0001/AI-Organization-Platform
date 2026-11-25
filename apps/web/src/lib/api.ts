/** 백엔드 REST 계약(apps/server/src/ai_org/schemas.py, docs/API.md)과 같은 모양의 타입과 호출. */

export type AgentStatus =
  | "idle"
  | "thinking"
  | "working"
  | "waiting"
  | "reviewing"
  | "completed"
  | "failed"
  | "offline";

export type ApprovalGroup = "shell" | "file_write" | "file_delete" | "network" | "delegate" | "mcp";

export interface AgentPermissions {
  permission_mode: "default" | "acceptEdits" | "plan";
  file_scope: string[];
  allow_shell: boolean;
  allow_network: boolean;
  allow_file_write: boolean;
  allow_file_delete: boolean;
  require_approval: ApprovalGroup[];
  can_delegate: boolean;
}

export interface Agent {
  id: string;
  organization_id: string;
  name: string;
  title: string;
  role: string;
  responsibilities: string[];
  expertise: string[];
  instructions: string;
  department_id: string | null;
  reports_to_id: string | null;
  is_lead: boolean;
  enabled: boolean;
  runtime: string;
  model: string | null;
  allowed_skills: string[];
  allowed_mcp_servers: string[];
  allowed_plugins: string[];
  permissions: AgentPermissions;
  status: AgentStatus;
  pos_x: number | null;
  pos_y: number | null;
  created_at: string;
  updated_at: string;
}

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  color: string;
  sort_order: number;
}

export interface Collaboration {
  id: string;
  source_agent_id: string;
  target_agent_id: string;
  kind: "handoff" | "review" | "consult";
  label: string;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  description: string;
  mission: string;
  template_key: string | null;
  agent_count: number;
  department_count: number;
  project_count: number;
  created_at: string;
  updated_at: string;
}

export interface Organization {
  id: string;
  name: string;
  description: string;
  mission: string;
  base_instructions: string;
  template_key: string | null;
  default_project_id: string | null;
  departments: Department[];
  agents: Agent[];
  collaborations: Collaboration[];
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  description: string;
  kind: string;
  organization_id: string | null;
  exists: boolean;
  created_at: string;
  updated_at: string;
}

export interface GitInfo {
  is_repo: boolean;
  branch: string | null;
  head: string | null;
  head_subject: string | null;
  dirty_files: number;
  ahead: number | null;
  behind: number | null;
  remote: string | null;
  error: string | null;
}

export interface ProjectRoot {
  id: string;
  path: string;
  max_depth: number;
  exists: boolean;
}

export interface ProjectCandidate {
  name: string;
  path: string;
  kind: string;
  is_git: boolean;
  registered: boolean;
}

/** 서버 컴퓨터의 폴더 탐색 결과(홈 폴더 안, 하위 폴더만, #65). */
export interface FolderListing {
  path: string;
  home: string;
  parent: string | null;
  is_git: boolean;
  kind: string;
  entries: { name: string; path: string; is_git: boolean; kind: string }[];
  truncated: boolean;
}

export interface Task {
  id: string;
  organization_id: string;
  project_id: string | null;
  parent_id: string | null;
  assignee_id: string | null;
  title: string;
  status: string;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface Approval {
  id: string;
  organization_id: string;
  agent_id: string;
  kind: string;
  summary: string;
  detail: { tool?: string; target?: string; group?: string | null; reason?: string };
  status: string;
  created_at: string;
}

export interface ActivityItem {
  id: string;
  organization_id: string | null;
  agent_id: string | null;
  kind: string;
  summary: string;
  created_at: string;
}

export interface Workspace {
  organizations: OrganizationSummary[];
  projects: Project[];
  running_agents: Agent[];
  recent_tasks: Task[];
  pending_approvals: Approval[];
  activity: ActivityItem[];
}

export interface RuntimeInfo {
  id: string;
  name: string;
  available: boolean;
  version: string | null;
  path: string | null;
  detail: string | null;
}

export interface SystemInfo {
  version: string;
  data_dir: string;
  runtimes: RuntimeInfo[];
}

export interface McpHealth {
  name: string;
  state: "connected" | "needs_auth" | "failed" | "pending_approval" | "disabled" | "unknown" | "error";
  message: string;
}

export interface UsageWindow {
  id: string;
  label: string;
  percent: number;
  resets_at: string | null;
  window_minutes: number | null;
  elapsed_percent: number | null;
  burn_rate_per_hour: number | null;
  projected_at_reset: number | null;
  exhaust_at: string | null;
  confidence: "learning" | "low" | "high";
  samples: number;
}

export interface UsageProvider {
  id: "claude" | "codex";
  name: string;
  state: "ok" | "disabled" | "pending" | "not_logged_in" | "token_expired" | "rate_limited" | "error" | "no_data";
  plan: string | null;
  observed_at: string | null;
  message: string | null;
  windows: UsageWindow[];
}

export interface UsagePayload {
  settings: { claude_enabled: boolean; codex_enabled: boolean; thresholds: number[] };
  providers: UsageProvider[];
}

export interface Capability {
  id: string;
  kind: "skill" | "mcp" | "plugin";
  name: string;
  scope: string;
  description: string;
  source: string;
  transport: string | null;
  detail: Record<string, unknown>;
}

// ── 채팅 ──────────────────────────────────────────────────────────────────

export interface ContextItem {
  kind: "path" | "agent" | "task" | "github" | "capability";
  ref: string;
  label: string;
}

export interface Conversation {
  id: string;
  organization_id: string;
  target_kind: "org" | "team" | "agent";
  target_id: string | null;
  project_id: string | null;
  title: string;
  context: ContextItem[];
  archived: boolean;
  busy: boolean;
  created_at: string;
  updated_at: string;
}

export interface ActivityEntry {
  id: string;
  tool: string;
  activity: string;
  target: string;
  status: "running" | "done" | "failed" | "cancelled";
  subagent: boolean;
  at: string;
}

export interface AttachmentInfo {
  id: string;
  filename: string;
  media_type: string;
  size: number;
  conversation_id: string | null;
}

export interface CommandResult {
  kind: "list" | "text" | "action";
  title: string;
  text: string;
  columns: string[];
  rows: string[][];
  action: { type: string; id?: string; ids?: string[] } | null;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "command" | "system";
  agent_id: string | null;
  content: string;
  data: {
    mentions?: string[];
    mention_all?: boolean;
    attachments?: AttachmentInfo[];
    command?: string;
    result?: CommandResult;
    delegated_by?: string;
    /** 작업 중에 보내 대기 중인 메시지(#45): 아직 전달되지 않은 대상과 상태. */
    queued?: { agent_id: string }[];
    queue_state?: "waiting" | "delivered" | "cancelled";
    queue_note?: string;
  };
  activity: ActivityEntry[];
  status: "pending" | "streaming" | "done" | "error" | "interrupted";
  error: string | null;
  cost_usd: number | null;
  duration_ms: number | null;
  task_id: string | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
  attachments: AttachmentInfo[];
}

export interface CommandSpec {
  name: string;
  description: string;
  usage: string;
  args: { name: string; kind: "agent" | "department" | "project" | "text"; required: boolean; description: string }[];
}

// ── 조직 설계 ─────────────────────────────────────────────────────────────

export interface SpecDepartment {
  key: string;
  name: string;
  description: string;
  color: string;
}

export interface SpecAgent {
  key: string;
  name: string;
  title: string;
  department: string | null;
  role: string;
  responsibilities: string[];
  expertise: string[];
  instructions: string;
  reports_to: string | null;
  is_lead: boolean;
  enabled: boolean;
  permissions: AgentPermissions;
  permission_suggestion: AgentPermissions | null;
  recommended_skills: string[];
  recommended_mcp: string[];
  allowed_skills: string[];
  allowed_mcp_servers: string[];
  allowed_plugins: string[];
  model: string | null;
}

export interface SpecCollaboration {
  source: string;
  target: string;
  kind: "handoff" | "review" | "consult";
  label: string;
}

export interface OrgSpec {
  name: string;
  description: string;
  mission: string;
  base_instructions: string;
  policy: Record<string, unknown>;
  departments: SpecDepartment[];
  agents: SpecAgent[];
  collaborations: SpecCollaboration[];
  workflows: { name: string; steps: string[] }[];
  recommended_skills: string[];
  recommended_mcp: string[];
}

export interface Template {
  template_id: string;
  version: string;
  name: string;
  description: string;
  category: string;
  target_users: string[];
  org_size: string;
  spec: OrgSpec;
}

export interface DesignMessage {
  role: "user" | "designer" | "edit";
  content: string;
  questions?: string[];
  changes?: string[];
  notes?: string[];
  error?: string;
  at: string;
}

export interface Recommendation {
  agent: string;
  kind: "skill" | "mcp";
  name: string;
  status: "available" | "approval_required" | "install_required" | "unsupported";
  id: string | null;
}

export interface Design {
  id: string;
  organization_id: string | null;
  origin: string;
  status: "draft" | "applied" | "discarded";
  busy: boolean;
  spec: OrgSpec;
  messages: DesignMessage[];
  notes: string[];
  recommendations: Recommendation[];
  updated_at: string;
}

export interface Revision {
  id: string;
  summary: string[];
  source: string;
  created_at: string;
  agent_count: number;
}

// ── 호출 ──────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail: unknown,
  ) {
    super(message);
  }
}

function messageOf(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail) && detail[0] && typeof detail[0] === "object" && "msg" in detail[0]) {
    return String((detail[0] as { msg: unknown }).msg);
  }
  return `요청이 실패했습니다(HTTP ${status}).`;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  settings: Record<string, unknown>;
}

export interface AuthStatus {
  auth_enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  user: AuthUser | null;
}

/** 로그인이 풀리면(401) 인증 게이트가 상태를 다시 확인하도록 알린다. */
export const UNAUTHORIZED_EVENT = "ai-org:unauthorized";

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: init.method ?? "GET",
    headers: init.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data: unknown = text ? JSON.parse(text) : null;
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/")) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(response.status, messageOf(detail, response.status), detail);
  }
  return data as T;
}

/** 파일 업로드(진행률 표시를 위해 XHR 사용). */
export function uploadFile(file: File, onProgress: (ratio: number) => void): Promise<AttachmentInfo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/attachments");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      const data: unknown = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as AttachmentInfo);
      else {
        const detail = data && typeof data === "object" && "detail" in data ? (data as { detail: unknown }).detail : data;
        reject(new ApiError(xhr.status, messageOf(detail, xhr.status), detail));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "업로드 중 연결이 끊겼습니다.", null));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
