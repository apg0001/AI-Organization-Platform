import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { isDesktopShell } from "./lib/notify";
import "./styles/globals.css";

isDesktopShell(); // 데스크톱 앱 창 표시(?desktop=1)를 탭 동안 기억
const root = document.getElementById("root");
if (!root) throw new Error("root 요소를 찾을 수 없습니다.");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
