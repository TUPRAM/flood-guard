import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const output = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? "out");
const artifacts = resolve("../../.tmp/policy-qa");
assert(existsSync(resolve(output, "policy/index.html")), "Build the competition profile before testing policy.");
assert.equal(JSON.parse(readFileSync(resolve(output, "deployment-profile.json"), "utf8")).profile, "competition");
mkdirSync(artifacts, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".webp": "image/webp", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
  let file = resolve(output, pathname || "index.html");
  if (file !== output && !file.startsWith(`${output}${sep}`)) return response.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
  if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("Unavailable");
  response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store", "Service-Worker-Allowed": "/" });
  createReadStream(file).pipe(response);
});
await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const errors = [];
const checks = [];
let browser;
const recordErrors = (page) => {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(`${message.text()} ${message.location().url}`.trim()); });
  page.on("requestfailed", (request) => {
    if (request.failure()?.errorText !== "net::ERR_ABORTED") errors.push(`${request.method()} ${request.url()} (${request.resourceType()}): ${request.failure()?.errorText}`);
  });
};
const roles = [
  ["Public", "ประชาชน", "What should my household prepare?", "ครัวเรือนควรเตรียมอะไร?", "/public/"],
  ["Planning", "การวางแผน", "Where should we focus, and why?", "ควรให้ความสำคัญกับพื้นที่ใด เพราะอะไร?", "/command/"],
  ["Studio", "สตูดิโอ", "Is the evidence fit for this decision?", "หลักฐานเหมาะกับการตัดสินใจนี้หรือไม่?", "/studio/"],
];
const actions = [
  ["A", "Protect lives now", "ปกป้องชีวิต"], ["B", "Keep routes open", "รักษาการเชื่อมต่อของเส้นทาง"],
  ["C", "Protect essential services", "คุ้มครองบริการจำเป็น"], ["D", "Build resilience", "สร้างความพร้อมระยะยาว"],
  ["E", "Monitor and verify", "ติดตามและตรวจสอบ"],
];

try {
  browser = await launchFloodGuardBrowser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: "block", reducedMotion: "reduce" });
  const page = await context.newPage();
  recordErrors(page);
  assert.equal((await page.goto(`${baseUrl}/policy/`, { waitUntil: "networkidle" }))?.status(), 200);
  await expect(page.locator("h1")).toContainText("From flood evidence");
  await expect(page.locator("#evidence")).toContainText("3.5 m");
  await expect(page.locator("#evidence")).toContainText("12 September, 12:00 ICT");
  await expect(page.locator("#evidence")).toContainText("low confidence");
  await page.locator("#evidence summary").click();
  for (const score of ["89.34", "85.98", "81.14", "76.38", "66.13", "53.93", "34.09", "31.27"]) {
    await expect(page.locator("#evidence ol")).toContainText(score);
  }
  await expect(page.locator("#evidence ol li")).toHaveCount(8);
  assert(!/53\.6|44\.0/.test(await page.locator("#evidence").innerText()), "Retired Ko Chang values must not replace the current example.");
  await expect(page.locator('#evidence a[href*="2e5a099ee075532e27236067810699ce6996c5c4"]').first()).toBeVisible();
  await expect(page.locator("#evidence")).toContainText("does not contain this FPPS update");
  checks.push("pinned r2 priority study, eight reproduced scores, and historical scenario context");

  for (const language of ["en", "th"]) {
    const thai = language === "th";
    await page.getByRole("button", { name: thai ? "ใช้ภาษาไทย" : "Use English", exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("lang", language);
    const audience = page.getByRole("group", { name: thai ? "เลือกกลุ่มผู้ใช้" : "Choose an audience" });
    for (const role of roles) {
      const button = audience.getByRole("button", { name: role[thai ? 1 : 0], exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#policy-role h3")).toHaveText(role[thai ? 3 : 2]);
      await expect(page.locator("#policy-role a")).toHaveAttribute("href", role[4]);
    }
    for (const [letter, en, th] of actions) {
      const title = thai ? th : en;
      const button = page.getByRole("button", { name: `${letter} · ${title}`, exact: true });
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator("#policy-action h4")).toHaveText(title);
      await expect(page.locator("#policy-action p").first()).not.toBeEmpty();
      await expect(page.locator("#policy-action")).toContainText(thai ? "ผู้ทบทวนที่เสนอ" : "Suggested reviewer");
    }
    for (const summary of await page.locator("main details summary").all()) {
      if (!(await summary.evaluate((node) => node.parentElement.open))) await summary.click();
      await expect(summary.locator("..")).toHaveAttribute("open", "");
    }
    await expect(page.locator("#sources a")).toHaveCount(6);
    for (const width of [320, 390, 430, 1024, 1440, 2048]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate(() => document.fonts.ready);
      const sizes = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth }));
      assert(sizes.document <= width + 1 && sizes.body <= width + 1, `${language} at ${width}px has overflow: ${JSON.stringify(sizes)}`);
      if ((width === 1440 && !thai) || (width === 390 && thai)) {
        await page.evaluate(() => scrollTo(0, 0));
        await page.screenshot({ path: resolve(artifacts, `${language}-${width}-hero.png`) });
        await page.locator("#evidence").screenshot({ path: resolve(artifacts, `${language}-${width}-evidence.png`) });
        await page.locator("#priorities").screenshot({ path: resolve(artifacts, `${language}-${width}-priorities.png`) });
      }
    }
    checks.push(`${language}: all audiences and A–E controls, disclosures, six widths without page overflow`);
  }
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("lang", "th");
  await expect(page.locator("h1")).toContainText("จากหลักฐานน้ำท่วม");
  await page.getByRole("button", { name: "Use English", exact: true }).click();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  checks.push("Thai and English preferences survive reload");

  for (const area of ["header", "footer"]) {
    await page.locator(`${area} a[href="/"]`).first().click();
    await expect(page.locator("[data-fg-landing]")).toBeVisible();
    await page.setViewportSize({ width: 320, height: 1000 });
    const policyLink = page.locator(`${area} a[href="/policy/"]`);
    await expect(policyLink).toBeVisible();
    if (area === "header") {
      await expect(policyLink).toBeInViewport();
      const bounds = await page.locator("header").boundingBox();
      assert(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 321, "The compact landing header fits 320px.");
    }
    await policyLink.click();
    await expect(page.locator("h1")).toContainText("From flood evidence");
  }
  checks.push("landing header and footer policy links, including the 320px header, navigate both ways");
  await context.close();

  const offline = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "allow" });
  const offlinePage = await offline.newPage();
  recordErrors(offlinePage);
  await offlinePage.goto(`${baseUrl}/policy/`, { waitUntil: "networkidle" });
  await offlinePage.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  const cachePaths = ["/", "/policy/", ...(await (await offline.request.get(`${baseUrl}/offline-assets.json`)).json())];
  await offlinePage.waitForFunction(async (paths) => {
    if (!navigator.serviceWorker.controller) return false;
    for (const key of await caches.keys()) {
      if (!key.startsWith("floodguard-offline-")) continue;
      const cache = await caches.open(key);
      if ((await Promise.all(paths.map((path) => cache.match(path)))).every(Boolean)) return true;
    }
    return false;
  }, cachePaths, { timeout: 60_000 });
  await offline.setOffline(true);
  await offlinePage.reload({ waitUntil: "networkidle" });
  await expect(offlinePage.locator("h1")).toContainText("From flood evidence");
  await offlinePage.getByRole("button", { name: "B · Keep routes open", exact: true }).click();
  await expect(offlinePage.locator("#policy-action h4")).toHaveText("Keep routes open");
  checks.push("competition cache serves the policy page and its controls offline");
  assert.deepEqual(errors, [], "No page or console errors");
  writeFileSync(resolve(artifacts, "checks.json"), `${JSON.stringify({ checks, errors }, null, 2)}\n`);
  console.log(`policy browser smoke: ${checks.length} check groups passed; screenshots in ${artifacts}`);
} finally {
  await browser?.close();
  await new Promise((done) => server.close(done));
}
