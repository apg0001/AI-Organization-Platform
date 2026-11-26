/**
 * 권한 표·팝오버·프리셋·배지가 함께 쓰는 순수 함수(화면 없음, permissions.test.ts로 고정).
 *
 * 백엔드 필드(apps/server/src/ai_org/schemas.py AgentPermissions)와의 대응:
 * - 칸 3상태 = allow_*(쓸 수 있는지) + require_approval(쓰기 전에 승인받는지).
 * - MCP는 allow_* 필드가 없다(서버 허용은 에이전트의 allowed_mcp_servers로 따로 정한다). 그래서 2상태(허용·승인 필요)다.
 * - auto 모드에서는 백엔드가 require_approval을 적용하지 않는다(값은 저장해 두고, 모드를 내리면 다시 적용된다).
 */

import type { AgentPermissions, ApprovalGroup, PermissionMode } from "./api";

export type CellState = "allow" | "ask" | "deny";

export const CELL_LABELS: Record<CellState, string> = { allow: "허용", ask: "승인 필요", deny: "금지" };

/** 표의 열 순서. */
export const GROUPS: ApprovalGroup[] = ["shell", "file_write", "file_delete", "network", "delegate", "mcp"];

export const GROUP_LABELS: Record<ApprovalGroup, string> = {
  shell: "셸",
  file_write: "파일 수정",
  file_delete: "삭제",
  network: "네트워크",
  delegate: "위임",
  mcp: "MCP",
};

type AllowKey = "allow_shell" | "allow_file_write" | "allow_file_delete" | "allow_network" | "can_delegate";

/** 묶음 → 허용 필드. MCP는 대응 필드가 없어 null. */
export const ALLOW_FIELD: Record<ApprovalGroup, AllowKey | null> = {
  shell: "allow_shell",
  file_write: "allow_file_write",
  file_delete: "allow_file_delete",
  network: "allow_network",
  delegate: "can_delegate",
  mcp: null,
};

/** 그 묶음에서 고를 수 있는 상태(순환 순서). */
export function statesOf(group: ApprovalGroup): CellState[] {
  return ALLOW_FIELD[group] ? ["allow", "ask", "deny"] : ["allow", "ask"];
}

export function cellState(perms: AgentPermissions, group: ApprovalGroup): CellState {
  const field = ALLOW_FIELD[group];
  if (field && !perms[field]) return "deny";
  return perms.require_approval.includes(group) ? "ask" : "allow";
}

/** 허용 → 승인 필요 → 금지 → 허용. MCP는 허용 ↔ 승인 필요. */
export function nextState(group: ApprovalGroup, state: CellState): CellState {
  const states = statesOf(group);
  return states[(states.indexOf(state) + 1) % states.length] ?? "ask";
}

/**
 * 칸 상태를 필드로 옮긴다.
 * - 허용: allow_*=true, require_approval에서 뺀다.
 * - 승인 필요: allow_*=true, require_approval에 넣는다.
 * - 금지: allow_*=false, require_approval에 넣는다(나중에 다시 켜도 승인부터 받게).
 */
export function setCell(perms: AgentPermissions, group: ApprovalGroup, state: CellState): AgentPermissions {
  const field = ALLOW_FIELD[group];
  if (state === "deny" && !field) return perms; // MCP에는 금지가 없다.
  const others = perms.require_approval.filter((g) => g !== group);
  const next: AgentPermissions = {
    ...perms,
    require_approval: state === "allow" ? others : GROUPS.filter((g) => g === group || others.includes(g)),
  };
  if (field) next[field] = state !== "deny";
  return next;
}

// ── 권한 모드 ─────────────────────────────────────────────────────────────

export const MODES: PermissionMode[] = ["plan", "default", "acceptEdits", "auto"];

export const MODE_LABELS: Record<PermissionMode, string> = {
  plan: "plan — 계획 전용",
  default: "default — 필요할 때 확인",
  acceptEdits: "acceptEdits — 편집 자동 허용",
  auto: "auto — Claude가 판단",
};

export const AUTO_DESCRIPTION = "안전한 작업은 Claude가 판단 · 작업 폴더 밖은 항상 승인";

/** 모드의 자율 정도. 숫자가 커지면 '상향'(확대)이다. */
const MODE_RANK: Record<PermissionMode, number> = { plan: 0, default: 1, acceptEdits: 2, auto: 3 };

/**
 * 칸의 실제 동작. 저장된 칸 상태(cellState)와 다른 경우가 둘 있다.
 * - 삭제는 셸 명령으로 실행되므로 셸이 금지면 삭제 칸 값과 관계없이 금지다.
 * - auto 모드에서는 '승인 필요'가 적용되지 않고 Claude가 판단한다("judged" — 승인 없이 실행될 수 있다).
 */
export type EffectiveState = "deny" | "ask" | "judged" | "allow";

export const EFFECTIVE_LABELS: Record<EffectiveState, string> = {
  deny: "금지",
  ask: "승인 필요",
  judged: "Claude 판단(승인 없이 실행될 수 있음)",
  allow: "허용",
};

const EFFECTIVE_RANK: Record<EffectiveState, number> = { deny: 0, ask: 1, judged: 2, allow: 3 };

export function effectiveState(perms: AgentPermissions, group: ApprovalGroup): EffectiveState {
  if (group === "file_delete" && !perms.allow_shell) return "deny";
  const state = cellState(perms, group);
  return state === "ask" && perms.permission_mode === "auto" ? "judged" : state;
}

// ── 프리셋 ────────────────────────────────────────────────────────────────

export type PresetId = "safe" | "standard" | "autonomous";

export const PRESETS: { id: PresetId; label: string; description: string }[] = [
  { id: "safe", label: "안전(읽기만)", description: "셸·파일 수정·삭제·네트워크 금지, MCP는 승인 필요. 위임·허용 리스트는 바꾸지 않음" },
  { id: "standard", label: "표준(편집·셸 승인)", description: "셸·파일 수정은 승인 후 실행, 삭제 금지. 위임·허용 리스트는 바꾸지 않음" },
  { id: "autonomous", label: "자율(auto)", description: `auto 모드. ${AUTO_DESCRIPTION}. 삭제·위임·허용 리스트는 바꾸지 않음` },
];

const PRESET_VALUES: Record<PresetId, { mode: PermissionMode; cells: Partial<Record<ApprovalGroup, CellState>> }> = {
  safe: { mode: "default", cells: { shell: "deny", file_write: "deny", file_delete: "deny", network: "deny", mcp: "ask" } },
  standard: { mode: "default", cells: { shell: "ask", file_write: "ask", file_delete: "deny", network: "allow", mcp: "ask" } },
  // 삭제는 건드리지 않는다(자율이라도 삭제를 대신 켜 주지 않는다). 승인 묶음은 모드를 내렸을 때를 위해 남긴다.
  autonomous: { mode: "auto", cells: { shell: "ask", file_write: "ask", network: "allow", mcp: "ask" } },
};

/**
 * 프리셋 적용. 위임(can_delegate·delegate 승인), 작업 범위(file_scope), 허용 리스트(allow_rules)는
 * 어느 프리셋도 바꾸지 않는다. 자율 프리셋은 삭제 칸도 그대로 둔다.
 */
export function applyPreset(perms: AgentPermissions, preset: PresetId): AgentPermissions {
  const { mode, cells } = PRESET_VALUES[preset];
  let next: AgentPermissions = { ...perms, permission_mode: mode };
  for (const group of GROUPS) {
    const state = cells[group];
    if (state) next = setCell(next, group, state);
  }
  return { ...next, allow_rules: [...perms.allow_rules] };
}

// ── 확대 판정 ─────────────────────────────────────────────────────────────

/**
 * 바꾸면 권한이 넓어지는 점들(사람이 읽는 문장). 비어 있으면 확대가 아니다.
 * 칸은 저장된 값이 아니라 실제 동작(effectiveState)으로 비교한다. 그래서 다른 설정을 바꿔 딸려 풀리는 것도 잡는다.
 * - 칸: 금지 < 승인 필요 < Claude 판단 < 허용 순서에서 올라감
 *   (셸을 켜면 '셸 금지로 막힘'이던 삭제가 풀리고, auto로 바꾸면 승인 필요였던 묶음이 Claude 판단이 된다)
 * - 모드: plan < default < acceptEdits < auto 순서에서 올라감
 * - 허용 리스트: 전에 없던 규칙이 생김
 */
export function escalations(before: AgentPermissions, after: AgentPermissions): string[] {
  const out: string[] = [];
  if (MODE_RANK[after.permission_mode] > MODE_RANK[before.permission_mode]) {
    out.push(
      after.permission_mode === "auto"
        ? `모드 ${before.permission_mode} → auto: 삭제·위임을 포함해 묶음별 승인이 적용되지 않고 Claude가 판단합니다(작업 폴더 밖 경로는 계속 승인)`
        : `모드 ${before.permission_mode} → ${after.permission_mode}`,
    );
  }
  for (const group of GROUPS) {
    const from = effectiveState(before, group);
    const to = effectiveState(after, group);
    if (EFFECTIVE_RANK[to] > EFFECTIVE_RANK[from]) out.push(`${GROUP_LABELS[group]}: ${EFFECTIVE_LABELS[from]} → ${EFFECTIVE_LABELS[to]}`);
  }
  const added = after.allow_rules.filter((rule) => !before.allow_rules.includes(rule));
  if (added.length) out.push(`허용 규칙 추가: ${added.join(", ")}`);
  return out;
}

export function isEscalation(before: AgentPermissions, after: AgentPermissions): boolean {
  return escalations(before, after).length > 0;
}

/** 저장할 것이 있는지(순서만 다른 require_approval은 같은 것으로 본다). */
export function samePermissions(a: AgentPermissions, b: AgentPermissions): boolean {
  return (
    a.permission_mode === b.permission_mode &&
    GROUPS.every((g) => cellState(a, g) === cellState(b, g) && a.require_approval.includes(g) === b.require_approval.includes(g)) &&
    a.allow_rules.length === b.allow_rules.length &&
    a.allow_rules.every((rule, i) => rule === b.allow_rules[i]) &&
    a.file_scope.join("\n") === b.file_scope.join("\n")
  );
}

/**
 * 오래된 화면 값(base)에서 만든 변경(next)을 최신 서버 값(latest) 위에 다시 얹는다.
 * base와 next 사이에서 실제로 바뀐 것(모드, 칸, 추가·삭제한 규칙, 작업 범위)만 latest에 적용하므로,
 * 그 사이 다른 곳에서 바뀐 값(방금 금지로 바꾼 칸, '항상 허용'으로 늘어난 규칙)을 옛 값으로 덮어쓰지 않는다.
 */
export function rebasePermissions(base: AgentPermissions, next: AgentPermissions, latest: AgentPermissions): AgentPermissions {
  const out: AgentPermissions = { ...latest, require_approval: [...latest.require_approval] };
  if (next.permission_mode !== base.permission_mode) out.permission_mode = next.permission_mode;
  // 칸 상태가 아니라 필드 단위로 본다(금지 칸의 승인 체크만 바꾼 편집기 변경도 옮겨야 한다).
  for (const group of GROUPS) {
    const field = ALLOW_FIELD[group];
    if (field && base[field] !== next[field]) out[field] = next[field];
    const required = next.require_approval.includes(group);
    if (required !== base.require_approval.includes(group)) {
      out.require_approval = GROUPS.filter((g) => (g === group ? required : out.require_approval.includes(g)));
    }
  }
  const removed = base.allow_rules.filter((rule) => !next.allow_rules.includes(rule));
  const added = next.allow_rules.filter((rule) => !base.allow_rules.includes(rule));
  const kept = latest.allow_rules.filter((rule) => !removed.includes(rule));
  out.allow_rules = [...kept, ...added.filter((rule) => !kept.includes(rule))];
  if (next.file_scope.join("\n") !== base.file_scope.join("\n")) out.file_scope = [...next.file_scope];
  return out;
}

export const BUSY_MESSAGE = "권한을 저장하는 중이라 방금 변경은 반영되지 않았습니다. 잠시 뒤 다시 시도하세요.";

/**
 * 저장·다시 불러오기 중(locked)에 들어온 변경 요청은 받지 않는다. 조용히 버리지 않고 notify로 알린다.
 * 받아도 되면 true.
 */
export function admitChange(locked: boolean, notify: (message: string) => void): boolean {
  if (locked) notify(BUSY_MESSAGE);
  return !locked;
}

// ── 조직도 배지 ───────────────────────────────────────────────────────────

export type BadgeId = "auto" | "plan" | "approval" | "no-shell";

export const BADGE_LABELS: Record<BadgeId, string> = { auto: "auto", plan: "계획만", approval: "승인 필요", "no-shell": "셸 금지" };

/**
 * 조직도 노드에 보일 배지.
 * - auto: auto 모드(이때는 묶음별 승인이 적용되지 않으므로 '승인 필요'를 함께 보이지 않는다).
 * - 계획만: plan 모드(계획만 세우고 실행하지 않으므로 '승인 필요' 대신 보인다).
 * - 승인 필요: 쓸 수 있는 묶음 중 승인을 거치는 것이 하나라도 있음.
 * - 셸 금지: allow_shell=false.
 */
export function badgesOf(perms: AgentPermissions): BadgeId[] {
  const out: BadgeId[] = [];
  if (perms.permission_mode === "auto") out.push("auto");
  else if (perms.permission_mode === "plan") out.push("plan");
  else if (GROUPS.some((g) => effectiveState(perms, g) === "ask")) out.push("approval");
  if (!perms.allow_shell) out.push("no-shell");
  return out;
}

// ── 허용 리스트 입력 ──────────────────────────────────────────────────────

export const MAX_RULES = 50;
export const MAX_RULE_LENGTH = 200;

/** 서버에 보내기 전에 걸러 낼 수 있는 것만 본다(문법·위험 규칙 판정은 서버가 한다). 문제없으면 null. */
export function ruleInputProblem(rules: string[], input: string): string | null {
  const rule = input.trim();
  if (!rule) return "규칙을 입력하세요.";
  if (rule.length > MAX_RULE_LENGTH) return `규칙은 ${MAX_RULE_LENGTH}자까지 쓸 수 있습니다.`;
  if (rules.includes(rule)) return "이미 있는 규칙입니다.";
  if (rules.length >= MAX_RULES) return `허용 규칙은 에이전트당 ${MAX_RULES}개까지 저장할 수 있습니다.`;
  return null;
}
