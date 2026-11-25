/*
 * AI Organization 서비스 워커(PWA, #73).
 * - /api·WebSocket·다른 출처 요청은 건드리지 않는다(로그인·데이터는 절대 캐시하지 않음).
 * - 해시된 정적 파일(/assets/…)·글꼴·아이콘: 캐시 우선(파일 이름이 바뀌면 새 파일).
 * - 화면(HTML 이동): 네트워크 우선 — 새 릴리스를 바로 받고, 서버에 닿지 않을 때만 마지막 화면을 보여 준다.
 */
const VERSION = "v1";
const STATIC = `ai-org-static-${VERSION}`;
const PAGES = `ai-org-pages-${VERSION}`;

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([STATIC, PAGES]);
      for (const key of await caches.keys()) if (!keep.has(key)) await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});

const isStatic = (url) =>
  url.pathname.startsWith("/assets/") ||
  url.pathname.startsWith("/fonts/") ||
  url.pathname.startsWith("/icons/") ||
  url.pathname.startsWith("/office/");

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          if (response.ok) (await caches.open(PAGES)).put("/", response.clone());
          return response;
        } catch {
          return (await caches.match("/")) ?? Response.error();
        }
      })(),
    );
    return;
  }

  if (isStatic(url)) {
    event.respondWith(
      (async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (response.ok) (await caches.open(STATIC)).put(request, response.clone());
        return response;
      })(),
    );
  }
});
