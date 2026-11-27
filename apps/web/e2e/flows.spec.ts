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

/** 권한 표의 칸 버튼(aria-label이 "에이전트 열: 상태. …"로 시작한다). */
function cellOf(page: Page, agent: string, column: string) {
  return page.getByRole("button", { name: new RegExp(`^${agent} ${column}: `) });
}

/** 칸을 눌러 원하는 상태로 만든다(허용 → 승인 필요 → 금지 순환). 금지 → 허용은 넓히는 변경이라 확인 창을 거친다. */
async function setCell(page: Page, agent: string, column: string, target: "allow" | "ask" | "deny") {
  const cell = cellOf(page, agent, column);
  await expect(cell).toBeVisible();
  for (let i = 0; i < 3; i += 1) {
    const state = await cell.getAttribute("data-state");
    if (state === target) return;
    await cell.click();
    if (state === "deny") await page.getByRole("button", { name: "권한 확대 적용" }).click();
    await expect(cell).not.toHaveAttribute("data-state", state ?? "");
    await expect(cell).toBeEnabled();
  }
  await expect(cell).toHaveAttribute("data-state", target);
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
  // 메시지 문구는 대화 기록 안에서만 찾는다('응답 중' 도크도 스트리밍 중인 문장을 보여 준다, #46).
  const chatLog = page.locator("[data-message-id]");

  // 입력창은 내용에 맞춰 늘어나고 5줄에서 멈춘 뒤 스크롤한다(#44).
  const height = () => input.evaluate((el) => el.getBoundingClientRect().height);
  const oneLine = await height();
  await input.fill("1\n2\n3");
  const threeLines = await height();
  expect(threeLines).toBeGreaterThan(oneLine * 2);
  await input.fill(Array.from({ length: 12 }, (_, i) => `${i + 1}`).join("\n"));
  const capped = await height();
  expect(capped).toBeLessThan(oneLine * 6);
  expect(await input.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await input.fill("");
  expect(await height()).toBe(oneLine);

  await input.fill("안녕하세요 팀");
  await input.press("Enter");
  await expect(chatLog.getByText("가짜 런타임 응답입니다:")).toBeVisible();
  await expect(page.locator("pre code")).toContainText("print('hello e2e')");

  // 경로로 시작하는 메시지는 명령이 아니라 일반 메시지로 보낸다(#67).
  await input.fill("/tmp/e2e-path 이 폴더 봐 줘");
  await input.press("Enter");
  await expect(chatLog.getByText("가짜 런타임 응답입니다:").last()).toContainText("/tmp/e2e-path 이 폴더 봐 줘");

  // ↑/↓로 보낸 글을 다시 불러오고, 끝을 지나면 쓰던 초안으로 돌아온다(#69).
  await input.fill("쓰던 초안");
  await input.press("ArrowUp");
  await expect(input).toHaveValue("/tmp/e2e-path 이 폴더 봐 줘");
  await input.press("ArrowUp");
  await expect(input).toHaveValue("안녕하세요 팀");
  await input.press("ArrowDown");
  await input.press("ArrowDown");
  await expect(input).toHaveValue("쓰던 초안");
  await input.fill("");

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
  // Write 요청은 만들어질 규칙(작업 폴더 기준 상대 경로)을 글자로 보여 준다.
  await expect(banner.getByText("Edit(e2e.txt)")).toBeVisible();
  // 응답 중(승인 대기)에도 보낼 수 있다. 대기열에 들어갔다가 지금 응답이 끝나면 이어서 전달된다(#45).
  await input.fill("대기열 확인 메시지");
  await input.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "지금 응답이 끝나면 이어서 전달합니다" })).toBeVisible();
  await banner.getByRole("button", { name: "이번만 허용" }).click();
  await expect(chatLog.getByText("파일 쓰기가 승인되었습니다.")).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "지금 응답이 끝나면 이어서 전달합니다" })).toHaveCount(0);
  await expect(chatLog.getByText("가짜 런타임 응답입니다:").last()).toContainText("대기열 확인 메시지");

  await input.fill("[위임:QA 엔지니어] 점검해 줘");
  await input.press("Enter");
  await expect(chatLog.getByText("← 프로젝트 매니저의 위임")).toBeVisible();
  await expect(chatLog.getByText("보고를 취합했습니다.")).toBeVisible();
  await expect(chatLog.getByText("[QA 엔지니어의 보고 — 작업 상태: done]")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "실행 현황" }).getByText("E2E 위임 작업")).toBeVisible();

  // 두 에이전트가 동시에 응답하면 입력창 위 '응답 중' 도크에 한 줄씩 보인다(#46).
  await input.fill("@QA 엔지니어 @코드 리뷰어 [승인] 동시에 점검해 줘");
  await input.press("Escape");
  await input.press("Enter");
  const dock = page.getByRole("region", { name: "응답 중 2" });
  await expect(dock).toBeVisible();
  await expect(dock.getByRole("button", { name: /QA 엔지니어/ })).toBeVisible();
  await expect(dock.getByRole("button", { name: /코드 리뷰어/ })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("concurrent-dock.png") });
  const approvals = page.getByRole("alert").filter({ hasText: "실행 승인을 요청합니다" });
  for (let i = 0; i < 2; i += 1) await approvals.getByRole("button", { name: "이번만 허용" }).first().click();
  await expect(page.getByRole("region", { name: /응답 중/ })).toHaveCount(0);

  // 대화 목록은 주 사이드바 안에 있고, 사이드바를 접으면 대화 위쪽 '대화' 메뉴로 바꾼다(#79).
  const convList = page.getByRole("navigation", { name: "주 메뉴" }).getByRole("region", { name: "대화 목록" });
  await expect(convList).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("sidebar-open.png") });
  await page.getByRole("button", { name: "사이드바 접기" }).click();
  await expect(convList).toBeHidden();
  await expect(page.getByRole("button", { name: "대화 목록" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("sidebar-rail.png") });
  await page.keyboard.press("Control+b");
  await expect(convList).toBeVisible();

  // 왼쪽 위에서 조직을 바꾸면 열린 대화도 그 조직 것으로 바뀐다(#79).
  const openUrl = page.url();
  await page.evaluate(() =>
    fetch("/api/v1/organizations/from-template", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ template_key: "personal", name: "E2E 두 번째 조직" }),
    }),
  );
  await page.reload();
  await page.getByRole("button", { name: "조직 선택" }).click();
  await page.getByRole("menuitem", { name: /E2E 두 번째 조직/ }).click();
  await expect(page.getByRole("button", { name: "CEO에게 업무 지시" })).toBeVisible();
  expect(page.url()).not.toBe(openUrl);
  await page.goto(openUrl); // 다른 조직 대화 링크를 열면 조직이 그 대화의 조직으로 돌아온다
  await expect(page.getByRole("button", { name: "조직 선택" })).not.toContainText("E2E 두 번째 조직");
  // 뒤 테스트가 첫 조직을 쓰므로 두 번째 조직은 지운다.
  await page.evaluate(async () => {
    const orgs = (await (await fetch("/api/v1/organizations")).json()) as { id: string; name: string }[];
    const extra = orgs.find((o) => o.name === "E2E 두 번째 조직");
    if (extra) await fetch(`/api/v1/organizations/${extra.id}`, { method: "DELETE" });
  });
});

test("권한 표: 셸 금지가 저장되고 조직도 배지에 반영", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "조직", exact: true }).click();
  const qa = page.locator(".react-flow__node").filter({ hasText: "QA 엔지니어" });

  // 먼저 셸을 '승인 필요'로 맞춘다(금지에서 넓히는 길이면 확인 창을 거친다) → 배지에 '셸 금지'가 없다.
  await page.getByRole("tab", { name: "권한" }).click();
  await setCell(page, "QA 엔지니어", "셸", "ask");
  await page.getByRole("tab", { name: "조직도" }).click();
  await expect(qa.getByText("승인 필요")).toBeVisible();
  await expect(qa.getByText("셸 금지")).toHaveCount(0);

  // 금지로 바꾸면(좁히는 변경이라 확인 창 없음) 저장되고 배지가 생긴다. 새로고침해도 남는다.
  await page.getByRole("tab", { name: "권한" }).click();
  await setCell(page, "QA 엔지니어", "셸", "deny");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("tab", { name: "조직도" }).click();
  await expect(qa.getByText("셸 금지")).toBeVisible();
  await page.reload();
  await expect(qa.getByText("셸 금지")).toBeVisible();

  // 넓히는 변경을 확인 창에서 취소하면 저장되지 않는다.
  await page.getByRole("tab", { name: "권한" }).click();
  const shell = cellOf(page, "QA 엔지니어", "셸");
  await shell.click();
  const dialog = page.getByRole("dialog", { name: "권한을 넓힐까요?" });
  await expect(dialog.getByText("셸: 금지 → 허용")).toBeVisible();
  await dialog.getByRole("button", { name: "취소" }).click();
  await expect(shell).toHaveAttribute("data-state", "deny");
  await expect(shell).toBeFocused();

  // 조직도 노드의 프리셋 메뉴는 버튼(키보드)으로 열리고 Esc로 닫히며 포커스가 버튼으로 돌아온다.
  await page.getByRole("tab", { name: "조직도" }).click();
  const menuButton = page.getByRole("button", { name: "QA 엔지니어 권한 프리셋" });
  await menuButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "안전(읽기만)" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(menuButton).toBeFocused();
  await expect(page).toHaveURL(/\/organization$/);
  // 우클릭으로도 같은 메뉴가 열린다.
  await qa.click({ button: "right" });
  await expect(page.getByRole("menuitem", { name: "표준(편집·셸 승인)" })).toBeVisible();
  await page.keyboard.press("Escape");
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("권한 프리셋 '안전' 적용 후 에이전트 편집 창 값 일치", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("tab", { name: "권한" }).click();
  await page.getByRole("checkbox", { name: "QA 엔지니어 선택" }).check();
  await expect(page.getByText("선택 1명에 적용")).toBeVisible();
  await page.getByRole("button", { name: "안전(읽기만)" }).click();
  // '안전'은 금지·승인 필요로만 바꾸지만, 템플릿 값에 따라 넓어지는 칸이 있으면(예: MCP) 확인 창이 뜬다.
  const confirm = page.getByRole("button", { name: "권한 확대 적용" });
  await expect(async () => {
    if (await confirm.isVisible()) await confirm.click();
    await expect(cellOf(page, "QA 엔지니어", "파일 수정")).toHaveAttribute("data-state", "deny", { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
  for (const [column, state] of [["셸", "deny"], ["삭제", "deny"], ["네트워크", "deny"], ["MCP", "ask"]] as const) {
    await expect(cellOf(page, "QA 엔지니어", column)).toHaveAttribute("data-state", state);
  }
  await expect(page.getByRole("combobox", { name: "QA 엔지니어 권한 모드" })).toHaveValue("default");

  await page.getByRole("link", { name: /^QA 엔지니어 허용 규칙 \d+개, 전체 편집$/ }).click();
  await expect(page).toHaveURL(/\/agents\/[^/]+\?tab=settings$/);
  await expect(page.getByRole("switch", { name: /^셸 명령/ })).not.toBeChecked();
  await expect(page.getByRole("switch", { name: /^파일 생성·수정/ })).not.toBeChecked();
  await expect(page.getByRole("switch", { name: /^파일 삭제/ })).not.toBeChecked();
  await expect(page.getByRole("switch", { name: /^웹 검색·가져오기/ })).not.toBeChecked();
  for (const name of ["셸 명령 실행", "파일 생성·수정", "파일 삭제", "웹 검색·가져오기", "MCP 도구 사용"]) {
    await expect(page.getByRole("checkbox", { name, exact: true })).toBeChecked();
  }
  await expect(page.getByLabel("Claude Code 권한 모드")).toHaveValue("default");
  await expect(page.getByLabel("Claude Code 권한 모드").getByRole("option", { name: /^auto — 안전한 작업은 Claude가 판단/ })).toBeAttached();
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("승인 배너 '항상 허용' 뒤 같은 요청은 배너 없이 진행", async ({ page }) => {
  await login(page);
  // CEO(프로젝트 매니저)의 셸을 '승인 필요'로 맞춘다.
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("tab", { name: "권한" }).click();
  await setCell(page, "프로젝트 매니저", "셸", "ask");
  await expect(page.getByRole("combobox", { name: "프로젝트 매니저 권한 모드" })).not.toHaveValue("auto");

  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();
  const input = page.getByLabel("메시지");
  const banner = page.getByRole("alert").filter({ hasText: "실행 승인을 요청합니다" });
  const allowed = page.getByRole("listitem").filter({ hasText: "npm test: 허용되었습니다" });

  await input.fill("[셸:npm test]");
  await input.press("Enter");
  await expect(banner).toBeVisible();
  // 만들어질 규칙을 글자로 보여 준다.
  await expect(banner.getByText("Bash(npm test:*)")).toBeVisible();
  await expect(banner.getByRole("link", { name: "권한 보기" })).toBeVisible();
  await banner.getByRole("button", { name: "항상 허용" }).click();
  await expect(page.getByText("허용 규칙을 추가했습니다: Bash(npm test:*)")).toBeVisible();
  await expect(allowed).toHaveCount(1);
  await expect(banner).toHaveCount(0);

  // 같은 요청: 승인 없이 끝난다(승인을 기다렸다면 응답이 오지 않는다).
  await input.fill("[셸:npm test]");
  await input.press("Enter");
  await expect(allowed).toHaveCount(2);
  await expect(banner).toHaveCount(0);

  // 규칙에 맞지 않는 명령은 여전히 묻는다. 거부는 기존대로.
  await input.fill("[셸:git status]");
  await input.press("Enter");
  await expect(banner.getByText("Bash(git status:*)")).toBeVisible();
  await banner.getByRole("button", { name: "거부" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "git status: 거부되었습니다" })).toHaveCount(1);

  // 추가된 규칙은 권한 표와 에이전트 편집 창에 보인다.
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("tab", { name: "권한" }).click();
  await page.getByRole("link", { name: "프로젝트 매니저 허용 규칙 1개, 전체 편집" }).click();
  await expect(page.getByRole("list", { name: "허용 규칙" }).getByText("Bash(npm test:*)")).toBeVisible();
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("커맨드 센터에서 권한 표 열기: 칸 저장·Esc로 닫으면 포커스 복귀(#87)", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();
  const opener = page.getByRole("button", { name: "권한 표 열기" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "권한 표" });
  await expect(dialog).toBeVisible();
  // 대화 화면을 떠나지 않는다. 지금 대화의 상대(조직 대화면 CEO) 행에 '현재 대화'가 적힌다.
  await expect(page).toHaveURL(/\/command\//);
  await expect(dialog.getByRole("row").filter({ hasText: "현재 대화" })).toHaveCount(1);

  // 셸 칸을 바꾸면 저장된다(금지에서 넓히는 길이면 표 위에 확인 창이 겹쳐 뜬다 — setCell이 처리).
  const shell = cellOf(page, "코드 리뷰어", "셸");
  await expect(shell).toBeVisible();
  const target = (await shell.getAttribute("data-state")) === "ask" ? "deny" : "ask";
  await setCell(page, "코드 리뷰어", "셸", target);
  await expect(dialog).toBeVisible(); // 확인 창을 닫아도 권한 표는 열려 있다

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();

  // 다시 열면 저장된 값이 보인다. 조직 화면의 권한 탭도 같은 값이다.
  await opener.click();
  await expect(cellOf(page, "코드 리뷰어", "셸")).toHaveAttribute("data-state", target);
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("tab", { name: "권한" }).click();
  await expect(cellOf(page, "코드 리뷰어", "셸")).toHaveAttribute("data-state", target);
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("권한 표에서 모델을 sonnet으로 바꾸면 저장되고 편집 창에 같은 값(#87)", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();
  await page.getByRole("button", { name: "권한 표 열기" }).click();
  const dialog = page.getByRole("dialog", { name: "권한 표" });
  const model = dialog.getByRole("combobox", { name: "QA 엔지니어 모델" });
  await expect(model).toHaveValue(""); // 기본값(Claude Code 기본 모델)
  await model.selectOption("sonnet");
  await expect(page.getByText("QA 엔지니어: 모델을 sonnet(으)로 저장했습니다.", { exact: false })).toBeVisible();
  await expect(model).toHaveValue("sonnet");
  await expect(model).toBeEnabled();
  await page.keyboard.press("Escape");

  // 새로고침해도 남고(서버에 저장됨), 조직 화면의 표와 에이전트 편집 창에도 같은 값이 보인다.
  await page.reload();
  await page.getByRole("link", { name: "조직", exact: true }).click();
  await page.getByRole("tab", { name: "권한" }).click();
  await expect(page.getByRole("combobox", { name: "QA 엔지니어 모델" })).toHaveValue("sonnet");
  await page.getByRole("link", { name: /^QA 엔지니어 허용 규칙 \d+개, 전체 편집$/ }).click();
  await expect(page.getByLabel("Claude 모델", { exact: true })).toHaveValue("sonnet");
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
});

test("대기 중인 메시지 수정: 고친 내용이 전달된다 · 사이드바 상단 접기 버튼(#95)", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();

  // 사이드바 접기·펴기 버튼은 상단(조직 줄)에 있고 aria-expanded로 상태를 알린다.
  const nav = page.getByRole("navigation", { name: "주 메뉴" });
  const collapse = nav.getByRole("button", { name: "사이드바 접기" });
  await expect(collapse).toHaveAttribute("aria-expanded", "true");
  await collapse.click();
  const expand = nav.getByRole("button", { name: "사이드바 펴기" });
  await expect(expand).toHaveAttribute("aria-expanded", "false");
  await expand.click();
  await expect(nav.getByRole("button", { name: "사이드바 접기" })).toHaveAttribute("aria-expanded", "true");

  // 새 CEO 대화에서 승인을 기다리는 동안 메시지를 보내 대기열에 넣는다(CEO 셸은 앞 테스트에서 '승인 필요', git status는 규칙 없음).
  await expect(page).toHaveURL(/\/command\/[^/]+$/);
  const before = page.url();
  await page.getByRole("button", { name: "새 대화" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "대화 시작" }).click();
  // 새 대화로 옮겨 간 뒤에 보낸다(옮기기 전에 보내면 앞 대화로 간다).
  await expect(page).not.toHaveURL(before);
  await expect(page.getByRole("region", { name: "채팅" }).getByText("무엇을 맡길까요?")).toBeVisible();
  const input = page.getByLabel("메시지");
  const chatLog = page.locator("[data-message-id]");
  await input.fill("[셸:git status]");
  await input.press("Enter");
  const banner = page.getByRole("alert").filter({ hasText: "실행 승인을 요청합니다" });
  await expect(banner).toBeVisible();
  await input.fill("수정 전 대기 메시지");
  await input.press("Enter");
  const waiting = page.getByRole("status").filter({ hasText: "지금 응답이 끝나면 이어서 전달합니다" });
  await expect(waiting).toBeVisible();

  // '수정'으로 그 자리에서 고친다(Esc는 취소, Ctrl+Enter는 저장).
  await waiting.getByRole("button", { name: "대기 중인 메시지 수정" }).click();
  const editor = page.getByRole("textbox", { name: "대기 중인 메시지 수정" });
  await editor.fill("버려질 내용");
  await editor.press("Escape");
  await expect(editor).toHaveCount(0);
  await expect(chatLog.getByText("수정 전 대기 메시지")).toBeVisible();
  await waiting.getByRole("button", { name: "대기 중인 메시지 수정" }).click();
  await editor.fill("수정 후 대기 메시지");
  await editor.press("Control+Enter");
  await expect(editor).toHaveCount(0);
  await expect(chatLog.getByText("수정 후 대기 메시지")).toBeVisible();
  await expect(chatLog.getByText("수정됨", { exact: true })).toBeVisible();

  // 지금 응답이 끝나면 고친 내용이 전달된다(가짜 런타임은 받은 마지막 줄을 응답에 넣는다).
  await banner.getByRole("button", { name: "거부" }).click();
  await expect(waiting).toHaveCount(0);
  await expect(chatLog.getByText("가짜 런타임 응답입니다:").last()).toContainText("수정 후 대기 메시지");
  await expect(chatLog.getByText("가짜 런타임 응답입니다:").last()).not.toContainText("수정 전");
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
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

  // 폴더 탐색 창에서 서버 홈 폴더를 둘러보고 바로 추가한다(탐색 경로 + 프로젝트 한 번에, #65).
  await page.getByRole("button", { name: "폴더에서 추가" }).click();
  const picker = page.getByRole("dialog", { name: "폴더에서 프로젝트 추가" });
  await picker.getByRole("list", { name: "하위 폴더" }).getByRole("button", { name: /code/ }).click();
  await picker.getByRole("list", { name: "하위 폴더" }).getByRole("button", { name: /picked-app/ }).click();
  await expect(picker.getByRole("navigation", { name: "현재 위치" })).toContainText("picked-app");
  await page.screenshot({ path: test.info().outputPath("folder-picker.png") });
  await picker.getByRole("button", { name: "이 폴더 추가" }).click();
  await expect(page.getByRole("button", { name: "picked-app 등록 해제(파일은 지우지 않음)" })).toBeVisible();

  // 프로젝트를 조직에 연결하면, 프로젝트 없이 시작한 기존 대화에 경고와 바로 연결 버튼이 뜬다(#71).
  await page.getByLabel("picked-app 연결 조직").selectOption({ index: 1 });
  await page.getByRole("link", { name: "커맨드 센터", exact: true }).click();
  await page.getByRole("link", { name: /안녕하세요 팀/ }).first().click();
  const notice = page.getByRole("status").filter({ hasText: "빈 작업 폴더" });
  await expect(notice).toBeVisible();
  await notice.getByRole("button", { name: "picked-app 연결" }).click();
  await expect(notice).toHaveCount(0);
  await page.getByRole("link", { name: "프로젝트", exact: true }).click();

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

  // 실제 위임 이벤트(task.delegated)가 오면 사무실에 업무 전달 기록이 뜬다(봉투 연출은 캔버스라 글 기록으로 확인).
  await page.evaluate(async () => {
    const orgs = (await (await fetch("/api/v1/organizations")).json()) as { id: string }[];
    const conv = (await (
      await fetch("/api/v1/conversations", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ organization_id: orgs[0]!.id, target_kind: "org" }),
      })
    ).json()) as { id: string };
    await fetch(`/api/v1/conversations/${conv.id}/messages`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content: "[위임:QA 엔지니어] 확인해 줘", mention_agent_ids: [], mention_all: false, attachment_ids: [] }),
    });
  });
  await expect(page.getByRole("list", { name: "최근 업무 전달" }).getByText("QA 엔지니어")).toBeVisible();
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
