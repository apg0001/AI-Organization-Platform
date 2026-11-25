import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { type Page, expect, test } from "@playwright/test";

/** 하나의 백엔드를 순서대로 쓰는 사용자 여정. 각 단계는 앞 단계의 결과(계정·조직)에 이어진다. */
test.describe.configure({ mode: "serial" });

const USER = { username: "owner", password: "e2e-password-1" };
const consoleErrors: string[] = [];

async function login(page: Page) {
  await page.goto("/");
  const loginButton = page.getByRole("button", { name: "로그인" });
  const nav = page.getByRole("navigation", { name: "주 메뉴" });
  // 인증 상태를 불러오는 동안에는 둘 다 없다. 로그인 화면이나 앱 중 하나가 나타날 때까지 기다린다.
  await expect(loginButton.or(nav)).toBeVisible();
  if (await loginButton.isVisible()) {
    await page.getByLabel("아이디").fill(USER.username);
    await page.getByLabel("비밀번호").fill(USER.password);
    await loginButton.click();
  }
  await expect(page.getByRole("navigation", { name: "주 메뉴" })).toBeVisible();
}

/** 조직도는 처음 그릴 때 화면 맞춤 애니메이션이 있어, 노드 클릭 → 설정 서랍이 열릴 때까지 재시도한다. */
async function openNode(page: Page, name: string) {
  const node = page.locator(".react-flow__node").filter({ hasText: name });
  const drawer = page.getByRole("complementary", { name: `${name} 설정` });
  await expect(async () => {
    await node.click();
    await expect(drawer).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

test.beforeEach(({ page }) => {
  page.on("console", (msg) => {
    // 401(로그인 전·틀린 비밀번호)은 의도된 응답이라 브라우저가 남기는 리소스 오류 로그에서 제외한다.
    if (msg.type() === "error" && !/WebGL|GPU stall|favicon|status of 401/i.test(msg.text())) consoleErrors.push(msg.text());
  });
});

test("첫 실행: 계정 만들기와 빈 대시보드", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "AI 조직을 시작합니다" })).toBeVisible();
  await page.getByLabel("아이디").fill(USER.username);
  await page.getByLabel("표시 이름(선택)").fill("E2E 주인");
  await page.getByLabel("비밀번호", { exact: true }).fill(USER.password);
  await page.getByLabel("비밀번호 확인").fill("different-password");
  await page.getByRole("button", { name: "계정 만들기" }).click();
  await expect(page.getByRole("alert")).toContainText("일치하지 않습니다");
  await page.getByLabel("비밀번호 확인").fill(USER.password);
  await page.getByRole("button", { name: "계정 만들기" }).click();
  await expect(page.getByRole("heading", { name: "AI 조직을 만들어 시작하세요" })).toBeVisible();
  await expect(page.getByText("테스트용 가짜 런타임")).toBeVisible();
});

test("템플릿 미리보기 → 설계 → 검토 → 조직 생성", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "조직 설계", exact: true }).click();
  await page.getByRole("button", { name: /소프트웨어 개발 조직/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("에이전트 8명")).toBeVisible();
  await dialog.getByRole("button", { name: "이 템플릿으로 설계 시작" }).click();
  await expect(page.getByRole("heading", { name: "소프트웨어 개발 조직" })).toBeVisible();
  // 조직도 노드 선택 → 설정 서랍
  await openNode(page, "QA 엔지니어");
  await page.getByRole("button", { name: "닫기" }).first().click();
  await page.getByRole("button", { name: "검토 후 조직 생성" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "이 구성으로 조직 생성" }).click();
  await expect(page).toHaveURL(/\/organization$/);
  await expect(page.locator(".react-flow__node")).toHaveCount(8);
});

test("설계 담당자와 대화: 단일 명세 갱신과 권한 제안 수락", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("button", { name: "조직 수정" }).click();
  await page.getByLabel("설계 담당자에게 보낼 메시지").fill("E2E팀을 추가해 줘");
  await page.getByRole("button", { name: "보내기" }).click();
  await expect(page.getByText("E2E팀과 E2E 분석가를 추가했습니다.")).toBeVisible();
  const node = page.locator(".react-flow__node").filter({ hasText: "E2E 분석가" });
  await expect(node).toBeVisible();
  await expect(node.getByText("권한 제안")).toBeVisible();
  await openNode(page, "E2E 분석가");
  await expect(page.getByText("AI가 권한 확대를 제안했습니다")).toBeVisible();
  await page.getByRole("button", { name: "제안 수락" }).click();
  await expect(page.getByText("AI가 권한 확대를 제안했습니다")).toBeHidden();
  await page.getByRole("button", { name: "닫기" }).first().click();
  await page.getByRole("button", { name: "검토 후 적용" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "변경 적용" }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(9);
  await page.getByRole("button", { name: "변경 이력" }).click();
  await expect(page.getByRole("dialog").getByText("에이전트 추가: E2E 분석가")).toBeVisible();
});

test("커맨드 센터: 스트리밍 응답·명령·멘션 자동완성·승인·위임", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();
  await page.getByRole("button", { name: "CEO에게 업무 지시" }).click();
  const input = page.getByLabel("메시지");

  await input.fill("안녕하세요 팀");
  await input.press("Enter");
  await expect(page.getByText("가짜 런타임 응답입니다:")).toBeVisible();
  await expect(page.locator("pre code")).toContainText("print('hello e2e')");

  await input.fill("/ag");
  await expect(page.getByRole("listbox", { name: "명령어" }).getByRole("option", { name: /\/agents/ })).toBeVisible();
  await input.press("Enter");
  await input.press("Enter");
  await expect(page.getByRole("cell", { name: "QA 엔지니어" })).toBeVisible();

  await input.fill("@QA");
  await expect(page.getByRole("listbox", { name: "에이전트" }).getByRole("option", { name: /QA 엔지니어/ })).toBeVisible();
  await input.press("Escape");
  await input.fill("");

  await input.fill("[승인] 파일을 하나 써 줘");
  await input.press("Enter");
  const banner = page.getByRole("alert").filter({ hasText: "실행 승인을 요청합니다" });
  await expect(banner).toBeVisible();
  await banner.getByRole("button", { name: "허용" }).click();
  await expect(page.getByText("파일 쓰기가 승인되었습니다.")).toBeVisible();

  await input.fill("[위임:QA 엔지니어] 점검해 줘");
  await input.press("Enter");
  await expect(page.getByText("← 프로젝트 매니저의 위임")).toBeVisible();
  await expect(page.getByText("보고를 취합했습니다.")).toBeVisible();
  await expect(page.getByText("[QA 엔지니어의 보고 — 작업 상태: done]")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "실행 현황" }).getByText("E2E 위임 작업")).toBeVisible();
});

test("프로젝트 등록과 기능 관리·사무실 화면", async ({ page }) => {
  await login(page);
  const root = mkdtempSync(join(tmpdir(), "ai-org-e2e-code-"));
  mkdirSync(join(root, "sample-app"));
  writeFileSync(join(root, "sample-app", "package.json"), "{}");
  await page.getByRole("link", { name: "프로젝트", exact: true }).click();
  await page.getByRole("button", { name: "탐색 경로 추가" }).click();
  await page.getByLabel("절대 경로").fill(root);
  await page.getByRole("dialog").getByRole("button", { name: "추가" }).click();
  await page.getByRole("button", { name: "등록" }).first().click();
  await expect(page.getByRole("button", { name: "sample-app 등록 해제(파일은 지우지 않음)" })).toBeVisible();

  await page.getByRole("link", { name: "기능 관리", exact: true }).click();
  await expect(page.getByRole("tab", { name: /Skills/ })).toBeVisible();
  await page.getByRole("tab", { name: /MCP 서버/ }).click();
  await expect(page.getByRole("button", { name: "연결 점검" })).toBeVisible();

  await page.getByRole("link", { name: "사용량", exact: true }).click();
  await expect(page.getByRole("heading", { name: "사용량" })).toBeVisible();
  await expect(page.getByText("꺼져 있습니다.")).toBeVisible(); // Claude 조회는 기본 꺼짐
  await expect(page.getByRole("switch", { name: "Claude 사용량 조회" })).not.toBeChecked();

  await page.getByRole("link", { name: "사무실", exact: true }).click();
  await expect(page.locator("canvas")).toBeVisible();
});

test("로그아웃 후 다시 로그인", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "계정 메뉴" }).click();
  await page.getByRole("menuitem", { name: "로그아웃" }).click();
  await expect(page.getByRole("button", { name: "로그인" })).toBeVisible();
  await page.getByLabel("아이디").fill(USER.username);
  await page.getByLabel("비밀번호").fill("wrong-password");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByRole("alert")).toContainText("올바르지 않습니다");
  await login(page);
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("테마 바꾸기와 시작 가이드", async ({ page }) => {
  await login(page);
  const guide = page.getByRole("region", { name: "시작 가이드" });
  await expect(guide).toBeVisible();
  // 데이터 단계(조직·프로젝트·대화·업무)는 앞 테스트에서 만든 데이터로 완료. 방문 단계는 새 브라우저라 아직 남음.
  await expect(guide.getByText("4/8 완료")).toBeVisible();
  for (const [name, path] of [
    ["조직", "/organization"],
    ["기능 관리", "/capabilities"],
    ["사무실", "/office"],
    ["사용량", "/usage"],
  ]) {
    const link = page.getByRole("link", { name, exact: true });
    await link.click();
    // 라우터 전환은 지연 로딩 화면이 준비돼야 확정된다(그 전에는 이전 화면 유지). 메뉴 활성 표시로 확정을 기다린다.
    await expect(link).toHaveAttribute("aria-current", "page");
    await expect(page).toHaveURL(new RegExp(`${path}$`));
  }
  await page.getByRole("link", { name: "대시보드", exact: true }).click();
  await expect(guide.getByText("모든 단계를 마쳤습니다", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "화면 설정" }).click();
  await page.getByRole("menuitemradio", { name: "라이트" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "화면 설정" }).click();
  await page.getByRole("menuitemradio", { name: "고대비" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "contrast");

  await guide.getByRole("button", { name: "시작 가이드 숨기기" }).click();
  await expect(guide).toBeHidden();
  await page.getByRole("button", { name: "화면 설정" }).click();
  await page.getByRole("menuitem", { name: "시작 가이드 보기" }).click();
  await expect(page.getByRole("region", { name: "시작 가이드" })).toBeVisible();
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});
