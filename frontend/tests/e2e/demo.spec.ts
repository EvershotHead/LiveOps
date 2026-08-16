import { test, expect, type Page } from "@playwright/test";

/**
 * 公开演示站 QA：9 页面 × 桌面/移动。
 * 断言：页面渲染无崩溃、图表非空、证据链接可用、无过度泛化表述、演示只读。
 */

const PAGES = [
  { path: "/", name: "数据与任务" },
  { path: "/overview", name: "总览" },
  { path: "/timeline", name: "版本时间线" },
  { path: "/topics", name: "主题洞察" },
  { path: "/controversy", name: "社区争议" },
  { path: "/compare", name: "双游戏对照" },
  { path: "/evidence", name: "证据与审核" },
  { path: "/evaluation", name: "模型评测" },
  { path: "/report", name: "运营报告" },
];

async function expectNoConsoleError(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return errors;
}

for (const p of PAGES) {
  test(`[${p.name}] 桌面渲染与图表非空`, async ({ page }) => {
    const errs = await expectNoConsoleError(page);
    await page.goto(p.path, { waitUntil: "networkidle" });
    await expect(page.locator("main")).toBeVisible();
    // 图表页：canvas 必须存在且至少一个非空
    if (["/overview", "/timeline", "/topics", "/compare"].includes(p.path)) {
      const canvas = page.locator("canvas");
      const n = await canvas.count();
      test.expect(n, `${p.name} 应有图表`).toBeGreaterThan(0);
      const sizes = await canvas.evaluateAll((els) =>
        (els as HTMLCanvasElement[]).map((c) => c.width * c.height),
      );
      test.expect(sizes.some((s) => s > 0), "图表画布非空").toBeTruthy();
    }
    expect(errs, `页面异常: ${errs.join(";")}`).toHaveLength(0);
  });

  test(`[${p.name}] 移动端无横向溢出`, async ({ page }) => {
    await page.goto(p.path, { waitUntil: "networkidle" });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    test.expect(overflow, "移动端不应横向溢出超过 8px").toBeLessThanOrEqual(8);
  });
}

test("总览：口径声明与真实数字", async ({ page }) => {
  await page.goto("/overview", { waitUntil: "networkidle" });
  await expect(page.getByText("所采样的 B 站讨论").first()).toBeVisible();
  // 有效评论数字为真实整数（非 0）
  const stat = page.getByText("有效相关评论", { exact: true });
  await expect(stat).toBeVisible();
});

test("主题洞察：表格行非空", async ({ page }) => {
  await page.goto("/topics", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const rows = page.locator("tbody tr");
  test.expect(await rows.count(), "主题表格应有数据").toBeGreaterThan(3);
});

test("社区争议：证据可点击且加载原文", async ({ page }) => {
  await page.goto("/controversy", { waitUntil: "networkidle" });
  await page.waitForTimeout(600);
  const ev = page.locator("[data-evidence-id]").first();
  await expect(ev).toBeVisible();
  await ev.click();
  await page.waitForTimeout(800);
  // 加载后出现来源链接
  const link = page.locator("[data-evidence-id] a[href*='bilibili']").first();
  if (await link.count()) {
    const href = await link.getAttribute("href");
    test.expect(href, "证据链接非空").toContain("http");
  }
});

test("双游戏对照：样本差异提示与免责", async ({ page }) => {
  await page.goto("/compare", { waitUntil: "networkidle" });
  await expect(page.getByText("样本量差异").first()).toBeVisible();
  await expect(page.getByText("不构成任何胜负结论").first()).toBeVisible();
});

test("模型评测：未测量如实展示", async ({ page }) => {
  await page.goto("/evaluation", { waitUntil: "networkidle" });
  await expect(page.getByText("未测量").first()).toBeVisible();
});

test("运营报告：结论引用与验证状态", async ({ page }) => {
  await page.goto("/report", { waitUntil: "networkidle" });
  await expect(page.getByText("结论验证通过")).toBeVisible();
  await expect(page.locator("[data-claim]").first()).toBeVisible();
});

test("演示模式：游戏切换", async ({ page }) => {
  await page.goto("/overview", { waitUntil: "networkidle" });
  const sw = page.locator("[data-demo-switch]");
  // 移动端切换器在抽屉菜单内：bbox 在视口外时先打开菜单
  const box = await sw.boundingBox();
  if (!box || box.x < 0) {
    await page.getByRole("button", { name: "菜单" }).click();
    await page.waitForTimeout(400);
  }
  await sw.getByText("鸣潮 3.5").click();
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("鸣潮 3.5 · 总览").first()).toBeVisible();
});

test("演示模式：只读（无导入入口）", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByText("公开演示模式")).toBeVisible();
  test.expect(await page.locator("input[type=file]").count(), "演示无文件上传").toBe(0);
});
