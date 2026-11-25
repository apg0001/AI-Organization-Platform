/**
 * 시작 가이드 상태: 숨김 여부와 '화면 방문' 단계 기록(localStorage).
 * 데이터 단계(조직·프로젝트·대화·업무)는 서버 데이터로 판정하고, 둘러보기 단계는 그 화면을 연 적이 있는지로 판정한다.
 */

import { useSyncExternalStore } from "react";

const KEY = "ai-org.guide";
interface GuideState {
  hidden: boolean;
  visited: string[];
}
const listeners = new Set<() => void>();
let cache: GuideState | null = null;

function read(): GuideState {
  if (cache) return cache;
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<GuideState>;
    cache = { hidden: Boolean(v.hidden), visited: Array.isArray(v.visited) ? v.visited.filter((x) => typeof x === "string") : [] };
  } catch {
    cache = { hidden: false, visited: [] };
  }
  return cache;
}

function write(next: GuideState) {
  cache = next;
  localStorage.setItem(KEY, JSON.stringify(next));
  listeners.forEach((l) => l());
}

export const GUIDE_PAGES = ["/organization", "/capabilities", "/office", "/usage"];

export function markVisited(path: string) {
  const page = GUIDE_PAGES.find((p) => path === p || path.startsWith(`${p}/`));
  const s = read();
  if (page && !s.visited.includes(page)) write({ ...s, visited: [...s.visited, page] });
}

export const setGuideHidden = (hidden: boolean) => write({ ...read(), hidden });

export function useGuideState(): GuideState {
  return useSyncExternalStore((cb) => {
    listeners.add(cb);
    return () => listeners.delete(cb);
  }, read);
}
