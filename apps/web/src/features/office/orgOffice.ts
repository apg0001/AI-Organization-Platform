/**
 * 조직 → 사무실 사실 상태(OfficeState) 어댑터.
 *
 * 렌더러(OfficeScene)는 Agent Office의 장치·세션·에이전트 모델을 그대로 받는다. 여기서는 에이전트 한 명을
 * '장치 하나 + 세션 하나 + 에이전트 하나'로 바꿔 렌더러를 수정하지 않고 재사용한다.
 * - 책상 번호: 조직도 순서(CEO가 0번). 비활성 에이전트는 사무실에 나오지 않는다.
 * - 활동(구역): 실행 이벤트의 최근 활동(reading/coding/…)이 있으면 그것, 없으면 상태로 정한다.
 */

import type { Activity, AgentState, OfficeState, TurnState } from "./types";
import type { Agent, AgentStatus } from "@/lib/api";

const STATUS_TURN: Record<AgentStatus, TurnState> = {
  idle: "IDLE",
  completed: "IDLE",
  failed: "IDLE",
  offline: "IDLE",
  thinking: "THINKING",
  working: "WORKING",
  reviewing: "WORKING",
  waiting: "WAITING_USER",
};

const KNOWN_ACTIVITIES = new Set<Activity>(["reading", "browsing", "coding", "testing", "planning", "delegating"]);

export function toOfficeState(agents: Agent[], recentActivity: Record<string, string | undefined>): OfficeState {
  const present = agents.filter((a) => a.enabled);
  const ordered = [...present.filter((a) => a.is_lead), ...present.filter((a) => !a.is_lead)];
  const now = new Date().toISOString();
  return {
    source: "server",
    devices: ordered.map((a) => ({ id: a.id, name: a.name, connection: "ONLINE" })),
    sessions: ordered.map((a, index) => ({
      id: a.id,
      device_id: a.id,
      provider: "claude",
      lifecycle: "OPEN",
      started_at: a.created_at,
      ended_at: null,
      last_event_at: a.status === "idle" ? a.updated_at : now,
      desk_slot: index,
      workspace_name: a.title || null,
      change_seq: 0,
    })),
    agents: ordered.map((a): AgentState => {
      const turn = STATUS_TURN[a.status] ?? "IDLE";
      const recent = recentActivity[a.id] as Activity | undefined;
      const activity: Activity =
        turn === "WAITING_USER"
          ? "waiting_user"
          : turn === "IDLE"
            ? "idle"
            : recent && KNOWN_ACTIVITIES.has(recent)
              ? recent
              : turn === "THINKING"
                ? "thinking"
                : "unknown";
      return {
        id: a.id,
        session_id: a.id,
        parent_agent_id: null,
        role: a.is_lead ? "lead" : "member",
        turn_state: turn,
        activity,
        confidence: "observed",
        wait_kind: turn === "WAITING_USER" ? "permission" : null,
        state_version: 0,
        started_at: a.created_at,
        ended_at: null,
        change_seq: 0,
      };
    }),
  };
}
