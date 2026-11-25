import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig } from "@playwright/test";

/**
 * 브라우저 E2E. 임시 데이터 폴더 + 테스트용 가짜 런타임(AI_ORG_RUNTIME=fake)으로 백엔드(8100)와 웹(3100)을 띄운다.
 * Claude 사용량을 쓰지 않는다(사용량 조회도 기본 꺼짐, Codex 폴더는 빈 임시 폴더). 브라우저는 시스템 Chrome(channel: chrome)을 쓴다.
 */
const home = process.env.AI_ORG_E2E_HOME ?? mkdtempSync(join(tmpdir(), "ai-org-e2e-"));
const python = process.env.AI_ORG_E2E_PYTHON ?? "../server/.venv/bin/python";
// 폴더 탐색(#65)은 서버의 홈 폴더 안만 보여 준다. 실제 홈 대신 고정된 가짜 홈을 쓴다.
const userHome = join(home, "user-home");
mkdirSync(join(userHome, "code", "picked-app", ".git"), { recursive: true });
writeFileSync(join(userHome, "code", "picked-app", "package.json"), "{}");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // 앞 단계 결과에 이어지는 여정이라 재시도하면 첫 단계부터 상태가 어긋난다. 재시도하지 않는다.
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 900 },
    locale: "ko-KR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${python} -m uvicorn ai_org.main:app --host 127.0.0.1 --port 8100`,
      cwd: "../server",
      url: "http://127.0.0.1:8100/api/v1/system/health",
      env: { HOME: userHome, AI_ORG_HOME: home, CODEX_HOME: join(home, "codex"), AI_ORG_RUNTIME: "fake", AI_ORG_PORT: "8100", AI_ORG_WEB_PORT: "3100" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx vite --port 3100",
      url: "http://127.0.0.1:3100",
      env: { AI_ORG_API_URL: "http://127.0.0.1:8100", AI_ORG_WEB_PORT: "3100" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
