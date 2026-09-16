import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const output = resolve("out");
const artifacts = resolve("test-results/mae-sai-demo");
const caseData = JSON.parse(readFileSync(resolve("src/data/mae-sai-planning-demo.json"), "utf8"));
mkdirSync(artifacts, { recursive: true });
let baseUrl = process.env.FLOODGUARD_DEMO_BASE_URL;
let server;
if (!baseUrl) {
  assert(existsSync(resolve(output, "command/mae-sai-demo/index.html")), "Build the competition profile first.");
  const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
  server = createServer((request, response) => {
    let file = resolve(output, decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "") || "index.html");
    if (file !== output && !file.startsWith(`${output}${sep}`)) return response.writeHead(403).end();
    if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
    if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("Unavailable");
    response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store" });
    createReadStream(file).pipe(response);
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
}

const browser = await launchFloodGuardBrowser();
const checks = [];
const pageErrors = [];
const consoleErrors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: "block", acceptDownloads: true });
  await context.route("**/*", (route) => new URL(route.request().url()).origin === new URL(baseUrl).origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  const response = await page.goto(`${baseUrl}/command/mae-sai-demo/`, { waitUntil: "networkidle" });
  assert.equal(response.status(), 200);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("defensible decision");
  await expect(page.getByRole("combobox", { name: "Focus area", exact: true })).toHaveValue("TH570903");
  await expect(page.getByText("4,877", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("−917", { exact: true })).toBeVisible();
  checks.push("direct route, real case context and candidate service comparison");

  await page.getByRole("combobox", { name: "Planning assumption", exact: true }).selectOption("close_road");
  await expect(page.getByRole("combobox", { name: "Focus area", exact: true })).toHaveValue("TH570903");
  await page.getByRole("button", { name: "View Mae Sai (+98)", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Focus area", exact: true })).toHaveValue("TH570901");
  await expect(page.getByText("172", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("+98", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: /Mae Sai administrative boundaries/ })).toBeVisible();
  checks.push("road closure and area selection display the recorded +98 consequence");

  async function fillReview(target, decision) {
    await target.getByLabel("Proposed decision", { exact: true }).fill(decision);
    await target.getByLabel("Reasoning and evidence", { exact: true }).fill("The hypothetical closure adds 98 modelled people losing access; check the real connection before choosing an intervention.");
    await target.getByLabel("Required verification before action", { exact: true }).fill("Confirm road identity, historical passability and facility operating role.");
    await target.getByLabel("Exercise owner / team", { exact: true }).fill("Planning exercise team");
    await target.getByLabel("Exercise role", { exact: true }).fill("Access reviewer");
  }
  await fillReview(page, "Verify the candidate road connection");
  await page.getByRole("combobox", { name: /^Exercise review status/ }).selectOption("reviewed_for_exercise");
  await page.getByRole("button", { name: "Save a new record" }).click();
  await expect(page.locator("main").getByRole("status")).toContainText("New record saved on this device");
  await page.getByLabel("Proposed decision", { exact: true }).fill("Discuss the alternative after verification");
  await page.getByRole("combobox", { name: /^Exercise review status/ }).selectOption("draft");
  await page.getByRole("button", { name: "Save a new record" }).click();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("2 records", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Discuss the alternative after verification/ })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: /Verify the candidate road connection/ }).click();
  checks.push("two saved snapshots survive reload; newest selected; earlier decision retained");

  // Active comparison is now the default Ko Chang option. Export must still
  // represent the earlier saved Mae Sai closure decision.
  const jsonDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export evidence · JSON" }).click();
  const downloaded = await jsonDownload;
  const jsonPath = resolve(artifacts, "saved-decision.json");
  await downloaded.saveAs(jsonPath);
  const exported = JSON.parse(readFileSync(jsonPath, "utf8"));
  assert.equal(exported.review.scenarioId, "close_road");
  assert.equal(exported.review.areaId, "TH570901");
  assert.equal(exported.selected_area_scenario.change_people_losing_30_min_access, 98);
  assert.equal(exported.evidence_package.meta.package_sha256, caseData.meta.package_sha256);
  assert.equal(exported.evidence_package.meta.fpps_recalculated, false);
  assert.equal(exported.official_warning, false);
  const markdownDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export brief · Markdown" }).click();
  const markdownPath = resolve(artifacts, "saved-decision.md");
  await (await markdownDownload).saveAs(markdownPath);
  const markdown = readFileSync(markdownPath, "utf8");
  assert(markdown.includes("Focus-area change: 98"));
  assert(markdown.includes("no authenticated staff approval or server receipt"));
  checks.push("JSON and Markdown exports preserve saved area/scenario and exact evidence identity");

  for (const [width, height] of [[390, 844], [430, 932], [1024, 768], [1440, 900], [1536, 1024], [2048, 1152]]) {
    await page.setViewportSize({ width, height });
    await page.goto(`${baseUrl}/command/mae-sai-demo/`, { waitUntil: "networkidle" });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `No horizontal overflow at ${width}×${height}`);
    await page.screenshot({ path: resolve(artifacts, `case-${width}x${height}.png`), fullPage: true });
    await expect(page.getByRole("combobox", { name: "Planning assumption", exact: true })).toBeVisible();
  }
  checks.push("all six required responsive viewports have no horizontal overflow");
  await page.getByRole("button", { name: "ใช้ภาษาไทย", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("การตัดสินใจที่อธิบายได้");
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await page.screenshot({ path: resolve(artifacts, "case-thai-mobile.png"), fullPage: true });
  checks.push("Thai controls and mobile layout render");

  const blocked = await browser.newContext({ serviceWorkers: "block" });
  await blocked.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith("floodguard:mae-sai:reviews:")) throw new DOMException("Quota exceeded", "QuotaExceededError");
      return original.call(this, key, value);
    };
  });
  const blockedPage = await blocked.newPage();
  await blockedPage.goto(`${baseUrl}/command/mae-sai-demo/`, { waitUntil: "networkidle" });
  await fillReview(blockedPage, "Unsaved storage-failure exercise");
  await blockedPage.getByRole("button", { name: "Save a new record" }).click();
  await expect(blockedPage.locator("main").getByRole("status")).toContainText("Browser storage could not confirm the save");
  await expect(blockedPage.getByText("0 records", { exact: true })).toBeVisible();
  checks.push("failed browser storage is not acknowledged as a saved review");
  await blocked.close();
  await context.close();
  assert.deepEqual(pageErrors, [], "No page runtime errors");
  assert.deepEqual(consoleErrors, [], "No console errors");
  writeFileSync(resolve(artifacts, "verification.json"), `${JSON.stringify({ checked_at: new Date().toISOString(), baseUrl, package_sha256: caseData.meta.package_sha256, checks, pageErrors, consoleErrors }, null, 2)}\n`);
  console.log(`Mae Sai demo browser smoke: ${checks.length} checks passed; screenshots and exported decisions in test-results/mae-sai-demo`);
} finally {
  await browser.close();
  if (server) await new Promise((done) => server.close(done));
}
