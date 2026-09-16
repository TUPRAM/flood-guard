import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? "out");
const artifacts = resolve("test-results/public-safety");
const reportKey = "floodguard:public-reports:v1";
const checks = [];
let server;
let browser;
let baseUrl = process.env.FLOODGUARD_DEMO_BASE_URL?.replace(/\/$/, "");

try {
  if (!baseUrl) {
    assert(existsSync(resolve(out, "public/index.html")), "Build output is missing; build first or set FLOODGUARD_DEMO_BASE_URL.");
    const contentTypes = {
      ".css": "text/css; charset=utf-8",
      ".html": "text/html; charset=utf-8",
      ".js": "text/javascript; charset=utf-8",
      ".json": "application/json; charset=utf-8",
      ".svg": "image/svg+xml",
      ".png": "image/png",
      ".webp": "image/webp",
      ".woff2": "font/woff2",
    };
    server = createServer((request, response) => {
      const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
      let path = resolve(out, decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "") || "index.html");
      if (!path.startsWith(`${out}${sep}`) && path !== out) {
        response.writeHead(403).end("Forbidden");
        return;
      }
      if (existsSync(path) && statSync(path).isDirectory()) path = resolve(path, "index.html");
      if (!existsSync(path) || !statSync(path).isFile()) {
        response.writeHead(404).end("Not found");
        return;
      }
      response.writeHead(200, {
        "Cache-Control": "no-store",
        "Content-Type": contentTypes[extname(path)] ?? "application/octet-stream",
      });
      createReadStream(path).pipe(response);
    });
    await new Promise((done, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", done);
    });
    const address = server.address();
    assert(address && typeof address !== "string", "Static server did not bind.");
    baseUrl = `http://127.0.0.1:${address.port}`;
  }

  mkdirSync(artifacts, { recursive: true });
  browser = await launchFloodGuardBrowser();
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    serviceWorkers: "block",
  });
  const externalRequests = [];
  const routingRequests = [];
  let failRouting = true;
  const origin = new URL(baseUrl).origin;
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    if (url.origin === "https://geocode.arcgis.com") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ candidates: [{
          address: "Exercise destination — test fixture",
          location: { x: 99.884366, y: 20.429799 },
          score: 100,
          attributes: { Addr_type: "PointAddress" },
        }] }),
      });
    }
    if (url.origin === "https://routing.openstreetmap.de") {
      routingRequests.push(url.href);
      return route.fulfill({
        status: failRouting ? 503 : 200,
        contentType: "application/json",
        body: JSON.stringify(failRouting ? { code: "NoRoute" } : {
          code: "Ok",
          routes: [{
            distance: 800,
            duration: 640,
            geometry: { type: "LineString", coordinates: [[99.88, 20.43], [99.884366, 20.429799]] },
            legs: [{ steps: [
              { maneuver: { type: "depart" }, name: "Test road", distance: 800 },
              { maneuver: { type: "arrive" }, name: "", distance: 0 },
            ] }],
          }],
        }),
      });
    }
    if (![
      "https://tile.openstreetmap.org",
      "https://services.arcgisonline.com",
      "https://a.tile.opentopomap.org",
    ].includes(url.origin)) externalRequests.push(url.href);
    return route.abort("blockedbyclient");
  });
  await context.addInitScript(() => localStorage.setItem("floodguard:language:v1", "en"));
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto(`${baseUrl}/public/`, { waitUntil: "networkidle" });
  await expect(page.locator("main.public-page")).toHaveAttribute("lang", "en");
  await page.locator("#public-tab-report").click();
  await page.getByRole("button", { name: "Change", exact: true }).click();
  await page.locator("#public-report-area-select").selectOption("TH570903");
  await page.locator("#public-tab-shelter").click();

  const shelter = page.locator(".public-shelter-page");
  const destination = shelter.getByLabel("Destination name or address", { exact: true });
  const confirmation = shelter.getByLabel("I confirmed this destination and route with DDPM or a local authority.", { exact: true });
  await expect(destination).toHaveValue("");
  await expect(shelter.locator('input[type="checkbox"]:checked')).toHaveCount(0);
  await expect(shelter.getByRole("button", { name: "Use this destination", exact: true })).toBeDisabled();
  await expect(shelter.getByText("The preview starts at the centre", { exact: false })).toBeVisible();
  await expect(shelter.locator(".public-shelter-directions__list")).toHaveCount(0);
  checks.push("Blank destination, all confirmations unchecked and visible area-centre-origin disclosure.");

  await destination.fill("Exercise destination — test fixture");
  await confirmation.check();
  await shelter.getByRole("button", { name: "Use this destination", exact: true }).click();
  await expect.poll(() => routingRequests.length).toBeGreaterThan(0);
  await expect(shelter.locator(".public-shelter-directions__empty")).toContainText("Route unavailable");
  await expect(shelter.locator(".public-shelter-directions__list")).toHaveCount(0);
  await expect(shelter.locator('path[stroke-dasharray="9 8"]')).toHaveCount(0);
  await expect(shelter.locator(".public-shelter-route-overview__summary")).not.toContainText(/\bmin\b|Head north|Set out from|Arrive at/);
  await shelter.locator(".public-shelter-directions").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(artifacts, "route-unavailable-mobile.png"), fullPage: true });
  checks.push("Forced road-routing failure produces no movement instructions or straight-line ETA.");

  // A successful router response is still suppressed when the user withdraws confirmation.
  failRouting = false;
  await destination.fill("Second exercise destination — test fixture");
  await expect(confirmation).not.toBeChecked();
  await confirmation.check();
  const routingBefore = routingRequests.length;
  await shelter.getByRole("button", { name: "Use this destination", exact: true }).click();
  await expect.poll(() => routingRequests.length).toBeGreaterThan(routingBefore);
  await expect(shelter.locator(".public-shelter-directions__list")).toBeVisible();
  await confirmation.uncheck();
  await expect(shelter.locator(".public-shelter-directions__list")).toHaveCount(0);
  await expect(shelter.locator('path[stroke-dasharray="9 8"]')).toHaveCount(0);
  checks.push("Revoking confirmation removes an available route preview.");

  await page.locator("#public-tab-report").click();
  const report = page.locator(".public-report-page");
  const feed = report.locator(".public-report-feed-list").first();
  const status = report.locator(".public-report-form-status");
  await expect(report.locator('.public-report-feed-example > p')).toBeVisible();
  await expect(report.locator('.public-report-feed-example > p')).toHaveText("Example report statuses. Not real reports.");
  await report.getByRole("button", { name: "Knee", exact: true }).click();
  await report.locator("#public-report-notes").fill("Synthetic persistence check one");
  await report.getByRole("button", { name: "Save report", exact: true }).click();
  await expect(status).toContainText("Report saved on this device");
  await expect(status).toContainText("It has not been sent to staff");
  await report.getByRole("button", { name: "Waist", exact: true }).click();
  await report.locator("#public-report-notes").fill("Synthetic persistence check two");
  await report.getByRole("button", { name: "Save report", exact: true }).click();
  await expect(feed.locator("li")).toHaveCount(2);
  const saved = await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), reportKey);
  assert.equal(saved.length, 2, "Sequential saves retain both observations.");
  assert.equal(new Set(saved.map((item) => item.report_id)).size, 2, "Each save has a distinct local identity.");
  assert(saved.every((item) => item.storage_scope === "device_local"));
  await page.reload({ waitUntil: "networkidle" });
  await page.locator("#public-tab-report").click();
  await expect(feed.locator("li")).toHaveCount(2);
  await expect(feed).toContainText("Synthetic persistence check one");
  await expect(feed).toContainText("Synthetic persistence check two");
  checks.push("Sequential local saves retain both unique records after reload and do not imply staff receipt.");

  await page.evaluate((key) => {
    const write = Storage.prototype.setItem;
    Storage.prototype.setItem = function (name, value) {
      if (name === key) throw new DOMException("Synthetic quota failure", "QuotaExceededError");
      return write.call(this, name, value);
    };
  }, reportKey);
  await report.getByRole("button", { name: "Knee", exact: true }).click();
  await report.locator("#public-report-notes").fill("Synthetic unsaved English check");
  await report.getByRole("button", { name: "Save report", exact: true }).click();
  await expect(status).toContainText("leave this Report page, reload, or close it");
  await expect(status).toContainText("It has not been sent to staff");
  await expect(feed.getByText("This session only", { exact: true })).toHaveCount(1);
  assert.equal(await page.evaluate((key) => JSON.parse(localStorage.getItem(key)).length, reportKey), 2);

  await page.getByRole("button", { name: "ใช้ภาษาไทย", exact: true }).click();
  await report.getByRole("button", { name: "เข่า", exact: true }).click();
  await report.locator("#public-report-notes").fill("Synthetic unsaved Thai check");
  await report.getByRole("button", { name: "บันทึกรายงาน", exact: true }).click();
  await expect(status).toContainText("ออกจากหน้ารายงาน ปิดหน้า หรือโหลดใหม่");
  await expect(status).toContainText("ยังไม่ได้ส่งให้เจ้าหน้าที่");
  await expect(feed.getByText("เฉพาะหน้านี้", { exact: true })).toHaveCount(2);
  await page.screenshot({ path: resolve(artifacts, "storage-unavailable-mobile-th.png"), fullPage: true });
  await page.locator("#public-tab-home").click();
  await page.locator("#public-tab-report").click();
  await expect(feed.locator("li")).toHaveCount(2);
  await expect(feed).not.toContainText("Synthetic unsaved");
  checks.push("Storage failure reports the session-only lifetime in English and Thai; leaving Report discards unsaved observations while preserving saved ones.");

  assert.deepEqual(pageErrors, [], "No client exceptions.");
  assert.deepEqual(externalRequests, [], "No unexpected external requests.");
  writeFileSync(resolve(artifacts, "verification.json"), JSON.stringify({
    checked_at: new Date().toISOString(),
    base_url: baseUrl,
    scope: "Deterministic browser fixtures; no real report submission, authority confirmation, or safe-route validation.",
    checks,
  }, null, 2));
  console.log(`Public safety checks passed: ${checks.join(" ")}`);
} finally {
  await browser?.close();
  if (server) await new Promise((done) => server.close(done));
}
