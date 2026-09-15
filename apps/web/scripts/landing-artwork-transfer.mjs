import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";
import { landingArtworkManifest } from "./landing-artwork-inventory.mjs";

const baseUrl = (process.argv[2] || "http://127.0.0.1:3100").replace(/\/$/, "");
const output = resolve(process.argv[3] || "../../docs/visual-qa/landing-v1/browser-acceptance-production/service-worker-artwork-transfers.json");
const browser = await launchFloodGuardBrowser();
const report = {
  startedAt: new Date().toISOString(), baseUrl, browser: browser.version(),
  viewport: { width: 1672, height: 941 }, deviceScaleFactor: 1,
  environment: "Fresh isolated browser context; service workers allowed; normal HTTP cache; local production static export.",
  method: "Observe the application's natural deferred cache request. Playwright response.body() records actual worker-fetched response body bytes. These exclude HTTP headers and are not encoded wire-byte measurements. No test message triggers artwork caching.",
  requests: [], errors: [],
};
const pendingBodies = [];
try {
  const inventoryResponse = await fetch(`${baseUrl}${landingArtworkManifest}`, { cache: "no-store" });
  assert.equal(inventoryResponse.status, 200, "The built artwork inventory must be available.");
  const inventory = await inventoryResponse.json();
  assert.equal(inventory.policy, "optional_after_first_paint");
  assert.ok(Array.isArray(inventory.assets) && inventory.assets.length > 0);
  const expectedAssets = new Map(inventory.assets.map((asset) => [asset.url, asset]));
  assert.equal(expectedAssets.size, inventory.assets.length, "The approved inventory must not duplicate URLs.");
  report.expectedAssets = inventory.assets;
  const context = await browser.newContext({ viewport: report.viewport, serviceWorkers: "allow" });
  context.on("response", (response) => {
    const request = response.request();
    const worker = request.serviceWorker();
    if (!worker || !new URL(response.url()).pathname.startsWith("/landing/")) return;
    pendingBodies.push((async () => {
      const entry = { url: response.url(), worker: worker.url(), status: response.status() };
      try {
        const body = await response.body();
        entry.bodyBytes = body.byteLength;
        entry.sha256 = createHash("sha256").update(body).digest("hex");
        entry.requestTiming = request.timing();
      } catch (error) { entry.error = error.message; }
      report.requests.push(entry);
    })());
  });
  await context.addInitScript(() => {
    window.__fgArtworkMessages = [];
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event.data?.type === "FLOODGUARD_LANDING_ARTWORK_STATUS") {
        window.__fgArtworkMessages.push({ ...event.data, receivedAfterNavigationMs: performance.now() });
      }
    });
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => report.errors.push(error.message));
  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await page.locator("main[data-fg-landing]").waitFor({ state: "visible" });
  await page.waitForFunction((total) => window.__fgArtworkMessages.some((message) => message.total === total && message.cached === total && message.failed === 0), expectedAssets.size, { timeout: 60_000 });
  await Promise.all(pendingBodies);
  report.pageTiming = await page.evaluate(() => ({
    timeOrigin: performance.timeOrigin,
    firstContentfulPaintMs: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
    loadEventEndMs: performance.getEntriesByType("navigation")[0]?.loadEventEnd ?? null,
    messages: window.__fgArtworkMessages,
  }));
  report.requests.sort((left, right) => left.requestTiming.startTime - right.requestTiming.startTime);
  for (const request of report.requests) {
    request.startAfterNavigationMs = request.requestTiming.startTime - report.pageTiming.timeOrigin;
    request.startAfterFirstContentfulPaintMs = report.pageTiming.firstContentfulPaintMs === null ? null : request.startAfterNavigationMs - report.pageTiming.firstContentfulPaintMs;
  }
  report.responseBodyBytes = report.requests.reduce((sum, request) => sum + (request.bodyBytes || 0), 0);
  report.assetCount = report.requests.length;
  report.cache = await page.evaluate(async () => {
    const names = (await caches.keys()).filter((name) => name.startsWith("floodguard-offline-"));
    return Promise.all(names.map(async (name) => ({ name, artworkUrls: (await (await caches.open(name)).keys()).map((request) => request.url).filter((url) => new URL(url).pathname.startsWith("/landing/")) })));
  });
  assert.equal(report.errors.length, 0, JSON.stringify(report.errors));
  assert.equal(report.requests.length, expectedAssets.size, "Expected one worker response for each approved artwork asset.");
  assert.deepEqual(report.requests.map((request) => new URL(request.url).pathname).sort(), [...expectedAssets.keys()].sort());
  assert.ok(report.requests.every((request) => request.status === 200 && request.bodyBytes > 0 && !request.error));
  for (const request of report.requests) {
    const expected = expectedAssets.get(new URL(request.url).pathname);
    assert.equal(request.bodyBytes, expected.bytes, `Incorrect body size for ${request.url}`);
    assert.equal(request.sha256, expected.sha256, `Incorrect body hash for ${request.url}`);
  }
  assert.ok(report.pageTiming.firstContentfulPaintMs !== null, "First contentful paint timing is required for the deferred-load observation.");
  assert.ok(report.requests.every((request) => request.startAfterFirstContentfulPaintMs > 0), "Optional artwork requests must start after first contentful paint.");
  assert.deepEqual(report.cache.flatMap((cache) => cache.artworkUrls).map((url) => new URL(url).pathname).sort(), [...expectedAssets.keys()].sort());
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.failure = error.stack || String(error);
  process.exitCode = 1;
} finally {
  report.finishedAt = new Date().toISOString();
  await browser.close();
  mkdirSync(resolve(output, ".."), { recursive: true });
  writeFileSync(output, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ status: report.status, assetCount: report.assetCount, responseBodyBytes: report.responseBodyBytes, output, failure: report.failure }));
}
