import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = process.env.AI_ORG_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.AI_ORG_WEB_PORT ?? 3000),
    strictPort: true,
    // API·WebSocket을 같은 출처로 보이게 한다(백엔드 Origin 검사와 일치).
    proxy: { "/api": { target: api, ws: true } },
  },
  preview: { host: "127.0.0.1", port: 3000, proxy: { "/api": { target: api, ws: true } } },
  build: {
    // Phaser(약 1.2MB)는 사무실 화면에서만 동적 import로 받는다.
    chunkSizeWarningLimit: 1600,
  },
});
