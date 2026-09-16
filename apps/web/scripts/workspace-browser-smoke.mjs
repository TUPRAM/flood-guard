import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const baseUrl = process.env.FLOODGUARD_WORKSPACE_BASE_URL;
assert(baseUrl, "Set FLOODGUARD_WORKSPACE_BASE_URL to the running static preview.");
const artifacts = resolve("test-results/workspace-theme");
mkdirSync(artifacts, { recursive: true });
const browser = await launchFloodGuardBrowser();
const checks = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: "block" });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  async function visit(path) {
    const response = await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
    assert.equal(response.status(), 200, path);
    await page.evaluate(() => document.fonts.ready);
  }
  async function headerFits() {
    const header = page.locator("header").first();
    const nav = header.locator("nav");
    await expect(nav).toBeVisible();
    await expect(nav.locator("a")).toHaveCount(3);
    for (const link of await nav.locator("a").all()) {
      await link.hover();
      await expect(link).toHaveCSS("text-decoration-line", "none");
    }
    const box = await nav.boundingBox();
    const headerBox = await header.boundingBox();
    assert(Math.abs(box.x + box.width / 2 - (headerBox.x + headerBox.width / 2)) < 2, "Navigation is centered within the header");
    const children = await header.locator(":scope > *").evaluateAll((nodes) => nodes.map((node) => {
      const { left, right, top, bottom } = node.getBoundingClientRect();
      return { left, right, top, bottom };
    }));
    for (let i = 0; i < children.length; i++) for (let j = i + 1; j < children.length; j++) {
      const a = children[i], b = children[j];
      assert(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top, "Header brand, navigation and language control do not overlap");
    }
    for (const button of await header.getByRole("button").all()) {
      const bounds = await button.boundingBox();
      assert(bounds.height >= 44 && bounds.width >= 44, "Language controls meet touch target size");
    }
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "No page-wide horizontal overflow");
  }
  await visit("/studio/");
  await expect(page.getByRole("heading", { name: "Every result has a context." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Use English" })).toHaveAttribute("aria-pressed", "true");
  await headerFits();
  await page.screenshot({ path: resolve(artifacts, "studio-desktop-en.png"), fullPage: true });
  await page.getByRole("button", { name: "ใช้ภาษาไทย" }).click();
  await expect(page.getByRole("heading", { name: "ทุกผลลัพธ์มีบริบทของตัวเอง" })).toBeVisible();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("main")).toHaveAttribute("lang", "th");
  await headerFits();
  await page.screenshot({ path: resolve(artifacts, "studio-desktop-th.png"), fullPage: true });
  await page.locator("header").first().getByRole("link", { name: "การวางแผน", exact: true }).click();
  await expect(page.locator("main")).toHaveAttribute("lang", "th");
  await expect(page.getByPlaceholder("ชื่อหรือรหัสพื้นที่")).toBeVisible();
  await headerFits();
  await page.getByRole("button", { name: "Use English" }).click();
  await expect(page.getByPlaceholder("Name or area ID")).toBeVisible();
  const areaCount = await page.locator(".ranked-areas li").count();
  await page.getByPlaceholder("Name or area ID").fill("TH570903");
  await expect(page.locator(".ranked-areas li")).toHaveCount(1);
  await page.getByPlaceholder("Name or area ID").clear();
  await expect(page.locator(".ranked-areas li")).toHaveCount(areaCount);
  await page.getByRole("tab", { name: "Verification", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Verification", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Summary", exact: true }).click();
  await page.screenshot({ path: resolve(artifacts, "planning-desktop-en.png"), fullPage: true });
  checks.push("English default; Thai switch, reload and cross-page preference; centered desktop header with no underline on hover; Planning search and tabs");
  for (const width of [1024, 768, 700, 641, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/studio/", "/command/"]) {
      await visit(path);
      for (const language of ["en", "th"]) {
        await page.getByRole("button", { name: language === "en" ? "Use English" : "ใช้ภาษาไทย" }).click();
        await headerFits();
        if (width === 390) await page.screenshot({ path: resolve(artifacts, `${path.includes("command") ? "planning" : "studio"}-mobile-${language}.png`), fullPage: true });
      }
    }
  }
  checks.push("English and Thai layouts at 1024, 768, 700, 641, 390 and 320 pixels without page overflow or overlapping header controls");
  await visit("/studio/studies/c2s-ms-20260915/mae-sai/");
  await expect(page.getByRole("heading", { name: "แม่สาย · การประยุกต์ใช้โมเดล C2S" })).toBeVisible();
  await expect(page.getByLabel("ส่วนของงานศึกษา")).toBeVisible();
  await expect(page.getByText("รายละเอียดการทดลอง ผลลัพธ์ และหลักฐานต้นฉบับด้านล่างคงไว้เป็นภาษาอังกฤษ", { exact: false })).toBeVisible();
  assert.equal(await page.locator("main").getByRole("alert").count(), 0);
  checks.push("Thai study navigation retains original English evidence and separate Mae Sai evaluation scope");
  assert.deepEqual(errors, [], "No client exceptions");
  writeFileSync(resolve(artifacts, "verification.json"), JSON.stringify({ checked_at: new Date().toISOString(), base_url: baseUrl, checks }, null, 2));
  console.log(`Workspace checks passed: ${checks.join("; ")}`);
} finally {
  await browser.close();
}
