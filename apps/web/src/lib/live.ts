/**
 * 실시간 이벤트(WebSocket /api/v1/ws). 서버 이벤트를 구독자에게 나눠 주고, 관련 쿼리를 무효화한다.
 * 연결이 끊기면 지수 백오프로 다시 연결하고, 다시 연결되면 모든 쿼리를 새로 받아 놓친 이벤트를 메운다.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

export interface LiveEvent {
  type: string;
  [key: string]: unknown;
}

type Listener = (event: LiveEvent) => void;
const listeners = new Set<Listener>();
let connected = false;
const connectionListeners = new Set<() => void>();

function setConnected(value: boolean) {
  connected = value;
  connectionListeners.forEach((fn) => fn());
}

export function onLive(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLiveConnected(): boolean {
  return useSyncExternalStore(
    (fn) => {
      connectionListeners.add(fn);
      return () => connectionListeners.delete(fn);
    },
    () => connected,
  );
}

/** 앱 최상단에서 한 번 쓴다. */
export function useLiveConnection(): void {
  const queryClient = useQueryClient();
  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = 0;
    let timer: number | undefined;
    let stopped = false;

    const connect = () => {
      const scheme = location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${location.host}/api/v1/ws`);
      socket.onopen = () => {
        if (retry > 0) void queryClient.invalidateQueries();
        retry = 0;
        setConnected(true);
      };
      socket.onmessage = (message) => {
        const event = JSON.parse(String(message.data)) as LiveEvent;
        if (event.type === "ping") return;
        listeners.forEach((fn) => fn(event));
        invalidateFor(event);
      };
      socket.onclose = () => {
        setConnected(false);
        if (stopped) return;
        retry += 1;
        timer = window.setTimeout(connect, Math.min(10_000, 500 * 2 ** retry));
      };
    };

    const invalidateFor = (event: LiveEvent) => {
      switch (event.type) {
        case "agent.status":
          void queryClient.invalidateQueries({ queryKey: ["organization"] });
          void queryClient.invalidateQueries({ queryKey: ["workspace"] });
          break;
        case "approval.requested":
        case "approval.resolved":
          void queryClient.invalidateQueries({ queryKey: ["approvals"] });
          void queryClient.invalidateQueries({ queryKey: ["workspace"] });
          break;
        case "message.completed":
          void queryClient.invalidateQueries({ queryKey: ["conversation", event.conversation_id] });
          void queryClient.invalidateQueries({ queryKey: ["conversations"] });
          void queryClient.invalidateQueries({ queryKey: ["tasks"] });
          void queryClient.invalidateQueries({ queryKey: ["workspace"] });
          break;
        case "task.updated":
          void queryClient.invalidateQueries({ queryKey: ["tasks"] });
          break;
        case "design.updated":
          void queryClient.invalidateQueries({ queryKey: ["design", event.design_id] });
          break;
        case "organization.updated":
          void queryClient.invalidateQueries({ queryKey: ["organization", event.organization_id] });
          void queryClient.invalidateQueries({ queryKey: ["organizations"] });
          void queryClient.invalidateQueries({ queryKey: ["workspace"] });
          break;
      }
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, [queryClient]);
}
