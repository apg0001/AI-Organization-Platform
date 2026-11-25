/**
 * 브라우저 알림. 서버의 알림 센터가 보낸 `notify` 이벤트(승인 요청·작업 완료/실패·사용량 경고)를
 * 사용자가 켜고 권한을 준 경우에만, 이 탭이 보이지 않을 때 OS 알림으로 띄운다.
 * 데스크톱 앱 창(?desktop=1로 열림)에서는 앱이 네이티브 알림을 보내므로 띄우지 않는다(중복 방지).
 */

import { useSyncExternalStore } from "react";

const KEY = "ai-org.notify";
const DESKTOP_KEY = "ai-org.desktop";
const listeners = new Set<() => void>();

export interface ServerNotification {
  id: number;
  kind: string;
  title: string;
  body: string;
  url?: string;
}

/** 데스크톱 앱이 연 창인지(첫 진입 주소의 ?desktop=1을 탭 동안 기억). */
export function isDesktopShell(): boolean {
  if (new URLSearchParams(window.location.search).get("desktop") === "1") sessionStorage.setItem(DESKTOP_KEY, "1");
  return sessionStorage.getItem(DESKTOP_KEY) === "1";
}

export const notificationsSupported = () => typeof window !== "undefined" && "Notification" in window;

function enabled(): boolean {
  return localStorage.getItem(KEY) === "on" && notificationsSupported() && Notification.permission === "granted";
}

export function useBrowserNotifications(): boolean {
  return useSyncExternalStore((cb) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  }, enabled);
}

/** 켜기: 권한을 묻고 허용되면 저장한다. 결과 권한을 돌려준다. */
export async function enableBrowserNotifications(): Promise<NotificationPermission> {
  const permission = Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
  localStorage.setItem(KEY, permission === "granted" ? "on" : "off");
  listeners.forEach((l) => l());
  return permission;
}

export function disableBrowserNotifications() {
  localStorage.setItem(KEY, "off");
  listeners.forEach((l) => l());
}

export function showBrowserNotification(n: ServerNotification) {
  if (!enabled() || isDesktopShell() || (document.visibilityState === "visible" && document.hasFocus())) return;
  const note = new Notification(n.title, { body: n.body, tag: `ai-org-${n.id}`, icon: "/favicon.svg" });
  note.onclick = () => {
    window.focus();
    if (n.url) {
      // SPA 안에서 이동(새로고침 없이): 라우터가 popstate를 듣는다.
      window.history.pushState(null, "", n.url);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
    note.close();
  };
}
