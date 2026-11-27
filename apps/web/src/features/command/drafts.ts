/**
 * 대화별 입력 초안(#96). 탭을 오가면 Composer가 새로 그려지므로 쓰던 글을 여기에 둔다.
 * - 초안 글: sessionStorage(이 브라우저 탭이 열려 있는 동안만, 키에 조직·대화 ID). 첨부는 저장하지 않는다.
 * - 스크롤 위치: 메모리(새로고침하면 사라진다).
 */

export const DRAFT_KEY_PREFIX = "ai-org.draft.";

export function draftKey(orgId: string | null | undefined, conversationId: string): string {
  return `${DRAFT_KEY_PREFIX}${orgId ?? "none"}.${conversationId}`;
}

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function store(): StorageLike | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

export function loadDraft(key: string, storage: StorageLike | null = store()): string {
  try {
    return storage?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

/** 빈 글이면 지운다(전송 뒤 비우기 포함). 저장소가 가득 차는 등 실패해도 입력은 막지 않는다. */
export function saveDraft(key: string, text: string, storage: StorageLike | null = store()): void {
  try {
    if (text) storage?.setItem(key, text);
    else storage?.removeItem(key);
  } catch {
    // 무시: 초안은 편의 기능이다.
  }
}

type IterableStorage = StorageLike & Pick<Storage, "length" | "key">;

function keysOf(storage: IterableStorage): string[] {
  const keys: string[] = [];
  for (let i = 0; i < storage.length; i += 1) {
    const key = storage.key(i);
    if (key?.startsWith(DRAFT_KEY_PREFIX)) keys.push(key);
  }
  return keys;
}

/** 모든 초안을 지운다(로그아웃 때 — 같은 브라우저를 다른 사람이 쓸 수 있으므로). 지운 개수. */
export function clearAllDrafts(storage: IterableStorage | null = store() as IterableStorage | null): number {
  try {
    if (!storage) return 0;
    const keys = keysOf(storage);
    keys.forEach((k) => storage.removeItem(k));
    return keys.length;
  } catch {
    return 0;
  }
}

/** 그 조직에서 더는 없는 대화(삭제·보관)의 초안을 지운다. 지운 개수. */
export function pruneDrafts(
  orgId: string | null | undefined,
  knownIds: readonly string[],
  storage: IterableStorage | null = store() as IterableStorage | null,
): number {
  try {
    if (!storage) return 0;
    const prefix = `${DRAFT_KEY_PREFIX}${orgId ?? "none"}.`;
    const known = new Set(knownIds);
    const stale = keysOf(storage).filter((k) => k.startsWith(prefix) && !known.has(k.slice(prefix.length)));
    stale.forEach((k) => storage.removeItem(k));
    return stale.length;
  } catch {
    return 0;
  }
}

export interface ScrollMemo {
  top: number;
  /** 맨 아래에 붙어 있었는지(그러면 새 메시지를 따라 내려간다). */
  stick: boolean;
}

const scrolls = new Map<string, ScrollMemo>();

export function rememberScroll(conversationId: string, memo: ScrollMemo): void {
  scrolls.set(conversationId, memo);
}

export function recallScroll(conversationId: string): ScrollMemo | undefined {
  return scrolls.get(conversationId);
}
