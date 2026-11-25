import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { isDesktopShell } from "./lib/notify";
import "./styles/globals.css";

const desktop = isDesktopShell(); // 데스크톱 앱 창 표시(?desktop=1)를 탭 동안 기억

// PWA(#73): 운영 빌드에서만 서비스 워커를 등록한다(개발 서버 HMR과 충돌, 데스크톱 앱 창은 이미 앱이라 불필요).
// 브라우저는 HTTPS·localhost에서만 등록을 허용한다.
if (import.meta.env.PROD && !desktop && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}
const root = document.getElementById("root");
if (!root) throw new Error("root 요소를 찾을 수 없습니다.");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
