/**
 * 커맨드 센터 대화 탭(#96)의 상태 계산. 화면 없는 순수 함수이고 tabsState.test.ts로 고정한다.
 *
 * - 활성 탭은 URL(`/command/:id`)이 정한다. 여기서는 열린 탭의 순서(대화 ID 목록)만 다룬다.
 * - 열린 탭 목록은 조직별로 localStorage(`ai-org.tabs.<orgId>`)에 저장한다(기기 사이에 공유하지 않음).
 * - 최대 MAX_TABS개. 가득 찬 상태에서 새 탭을 열면 거부하고 알린다(가장 단순하고 예측 가능 — 사용자가 직접 닫게 한다).
 */

export const MAX_TABS = 8;
export const TABS_KEY_PREFIX = "ai-org.tabs.";
/** 탭 줄 도움말에 보이는 단축키 안내. */
export const TAB_SHORTCUTS_HINT = "Alt+1~9: n번째 탭(9는 마지막) · Alt+W: 현재 탭 닫기 · 대화 목록에서 Ctrl/⌘+클릭: 새 탭";
export const FULL_MESSAGE = `탭은 ${MAX_TABS}개까지 열 수 있습니다. 쓰지 않는 탭을 닫고 다시 여세요.`;

export type Tabs = readonly string[];

export interface OpenResult {
  tabs: Tabs;
  /** 가득 차서 열지 못했으면 true(탭 목록은 그대로). */
  rejected: boolean;
}

/** 새 탭으로 연다. 이미 열려 있으면 그대로(활성화만 하면 된다). 가득 찼으면 거부. 새 탭은 기준 탭(after) 바로 오른쪽, 없으면 맨 끝. */
export function openTab(tabs: Tabs, id: string, after?: string | null): OpenResult {
  if (tabs.includes(id)) return { tabs, rejected: false };
  if (tabs.length >= MAX_TABS) return { tabs, rejected: true };
  const at = after ? tabs.indexOf(after) : -1;
  return { tabs: at >= 0 ? [...tabs.slice(0, at + 1), id, ...tabs.slice(at + 1)] : [...tabs, id], rejected: false };
}

/**
 * 현재 탭(previous)의 내용을 다른 대화(id)로 바꾼다(대화 목록의 일반 클릭, 조직·대화 따라가기).
 * id가 이미 다른 탭에 있으면 목록은 그대로(그 탭으로 옮겨 가면 된다). 현재 탭이 없으면 새로 연다(가득 찼으면 맨 끝 탭을 바꾼다).
 */
export function replaceTab(tabs: Tabs, previous: string | null | undefined, id: string): Tabs {
  if (tabs.includes(id)) return tabs;
  const at = previous ? tabs.indexOf(previous) : -1;
  if (at >= 0) return tabs.map((t, i) => (i === at ? id : t));
  if (tabs.length < MAX_TABS) return [...tabs, id];
  return [...tabs.slice(0, -1), id];
}

/**
 * 주소의 대화(id)를 그 조직의 탭 목록에 반영한다. 반영할 수 없으면 null(아직 기다림).
 * 대화의 조직(convOrg)을 아직 모르거나 지금 조직(orgId)과 다르면 건드리지 않는다:
 * 다른 조직의 대화 링크를 열면 조직이 그 대화의 조직으로 바뀐 뒤에 그 조직의 탭 목록에 들어간다(앞 조직의 탭 자리를 바꾸지 않는다).
 */
export function placeActive(
  tabs: Tabs,
  previous: string | null | undefined,
  id: string,
  convOrg: string | null | undefined,
  orgId: string | null | undefined,
): Tabs | null {
  if (!convOrg || !orgId || convOrg !== orgId) return null;
  return tabs.includes(id) ? tabs : replaceTab(tabs, previous, id);
}

/** 탭을 닫는다. active는 닫은 뒤 활성화할 탭(오른쪽 이웃 → 없으면 왼쪽 → 없으면 null). 닫은 탭이 활성 탭이 아니면 활성 탭 그대로. */
export function closeTab(tabs: Tabs, id: string, current: string | null | undefined): { tabs: Tabs; active: string | null } {
  const at = tabs.indexOf(id);
  if (at < 0) return { tabs, active: current ?? null };
  const next = tabs.filter((t) => t !== id);
  if (current !== id) return { tabs: next, active: current ?? null };
  return { tabs: next, active: tabs[at + 1] ?? tabs[at - 1] ?? null };
}

/** 대화 목록에 없는 탭(삭제·보관된 대화)을 뺀다. 목록을 아직 못 받았으면(known=undefined) 건드리지 않는다. */
export function pruneTabs(tabs: Tabs, known: readonly string[] | undefined): Tabs {
  if (!known) return tabs;
  const set = new Set(known);
  const next = tabs.filter((t) => set.has(t));
  return next.length === tabs.length ? tabs : next;
}

/** 탭을 왼쪽(-1)·오른쪽(+1)으로 한 칸 옮긴다. */
export function moveTab(tabs: Tabs, id: string, delta: -1 | 1): Tabs {
  const at = tabs.indexOf(id);
  const to = at + delta;
  if (at < 0 || to < 0 || to >= tabs.length) return tabs;
  const next = [...tabs];
  [next[at], next[to]] = [next[to]!, next[at]!];
  return next;
}

/** n번째 탭(1부터). 9는 브라우저처럼 마지막 탭. 없으면 null. */
export function nthTab(tabs: Tabs, n: number): string | null {
  if (n === 9) return tabs[tabs.length - 1] ?? null;
  return tabs[n - 1] ?? null;
}

/**
 * 탭 단축키(Alt+1~9, Alt+W). 브라우저 탭 단축키(Ctrl+1~9·W·Tab·T)와 겹치지 않게 Alt를 쓴다.
 * macOS의 Option은 입력 문자를 바꾸므로 event.key가 아니라 event.code(Digit1…·KeyW)로 판정한다.
 */
export function tabShortcut(
  e: Pick<KeyboardEvent, "altKey" | "ctrlKey" | "metaKey" | "shiftKey" | "code"> & Partial<Pick<KeyboardEvent, "isComposing" | "keyCode">>,
): { kind: "nth"; n: number } | { kind: "close" } | null {
  // 한글 등 입력기 조합 중(isComposing, 옛 브라우저는 keyCode 229)에는 무시한다.
  if (e.isComposing || e.keyCode === 229) return null;
  if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return null;
  const digit = /^Digit([1-9])$/.exec(e.code);
  if (digit) return { kind: "nth", n: Number(digit[1]) };
  if (e.code === "KeyW") return { kind: "close" };
  return null;
}

/** 저장 값 읽기(망가진 값은 빈 목록). */
export function parseStoredTabs(raw: string | null): string[] {
  try {
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? [...new Set(value.filter((v): v is string => typeof v === "string"))].slice(0, MAX_TABS) : [];
  } catch {
    return [];
  }
}
