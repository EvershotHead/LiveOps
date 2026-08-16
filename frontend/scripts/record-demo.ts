import { chromium } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

/** 录制 2-3 分钟演示视频：9 页面巡览 + 游戏切换 + 证据回溯。 */
(async () => {
  const outDir = path.resolve(__dirname, "../../demo/video");
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: outDir, size: { width: 1440, height: 900 } },
  });
  const page = await ctx.newPage();
  const base = "http://localhost:4173";

  const visit = async (p: string, ms = 6000, label?: string) => {
    await page.goto(base + p, { waitUntil: "networkidle" });
    if (label) {
      await page.evaluate((t) => {
        const el = document.createElement("div");
        el.textContent = t;
        el.style.cssText =
          "position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:9999;" +
          "background:#18181b;color:#fff;padding:8px 16px;border-radius:8px;font:14px/1 sans-serif";
        document.body.appendChild(el);
      }, label);
    }
    await page.waitForTimeout(ms);
  };

  await visit("/", 7000, "LiveOps Community Intelligence — 公开演示（无密钥只读）");
  await visit("/overview", 9000, "总览：数据覆盖 / 主题分布 / 风险与机会（口径：所采样的 B 站讨论）");
  await visit("/timeline", 8000, "版本时间线：T0 三段窗口（预热/上线/发酵）");
  await visit("/topics", 8000, "主题洞察：12 固定主题指标矩阵（Python 计算）");
  await visit("/controversy", 9000, "社区争议：冲突排序 + 观点矩阵 + 证据原文回溯");
  await visit("/compare", 9000, "双游戏对照：每千条归一化，不输出胜负结论");
  await visit("/evaluation", 8000, "模型评测：真实数字 + 未测量项如实标注");
  await visit("/report", 8000, "运营报告：结论引用指标与证据，验证节点把关");

  // 游戏切换演示
  await page.goto(base + "/overview", { waitUntil: "networkidle" });
  await page.locator("[data-demo-switch]").getByText("鸣潮 3.5").click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(6000);

  await ctx.close();
  await browser.close();
  const files = fs.readdirSync(outDir).filter((f) => f.endsWith(".webm"));
  console.log("视频已生成:", files.map((f) => path.join(outDir, f)));
})();
