/**
 * Serve the static export with the production security headers from
 * vercel.json and assert the app still works under them (D-22).
 *
 * A Content-Security-Policy that breaks the app is worse than no CSP: it ships
 * a blank page to people during a flood. This is not theoretical here --
 * `script-src 'self'` looks like the obviously correct value and silently
 * breaks everything, because the Next.js static export inlines 43 hydration
 * scripts (`self.__next_f.push(...)`) and a static export cannot use nonces.
 *
 * The check loads every exported route under the real headers and fails on any
 * CSP violation, console error, or failed request.
 *
 * Usage:  node apps/web/scripts/csp-smoke.mjs
 */

import { createServer } from "node:http";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect } from "@playwright/test";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const OUT_DIR = resolve(HERE, "..", "out");
const VERCEL_JSON = resolve(HERE, "..", "..", "..", "vercel.json");

const ROUTES = [
  "/", "/public/", "/command/", "/command/mae-sai-demo/", "/studio/", "/studio/planning-evidence/",
  "/studio/archive/mae-sai-geoai/", "/studio/studies/c2s-ms-20260915/",
  ...["data", "models", "results", "rtc", "explorer", "files", "mae-sai"].map((section) => `/studio/studies/c2s-ms-20260915/${section}/`),
];
const TILE_ORIGINS = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
// A valid image with a 403 status reproduces the provider's loadable error-image case.
const TILE_PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64");
const TILE_RESPONSE = { status: 200, contentType: "image/png", headers: { "Access-Control-Allow-Origin": "*" }, body: TILE_PNG };

async function mockExternalServices(context, base, problems) {
  const state = { mode: "ready", tileCount: 0, referrers: [], geocoderRequests: [], pending: [] };
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === base) return route.continue();
    if (TILE_ORIGINS.has(url.origin)) {
      state.referrers.push((await route.request().allHeaders()).referer);
      state.tileCount += 1;
      if (state.mode === "stalled") {
        state.pending.push(route);
        return;
      }
      const blocked = state.mode === "blocked" || (state.mode === "partial" && state.tileCount % 2 === 0);
      return route.fulfill({ ...TILE_RESPONSE, status: blocked ? 403 : 200 });
    }
    if (url.origin === "https://geocode.arcgis.com") {
      state.geocoderRequests.push({ url, headers: await route.request().allHeaders() });
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: JSON.stringify({ candidates: [{
          address: "Mae Sai Hospital, Chiang Rai, Thailand",
          score: 100,
          location: { x: 99.884, y: 20.425 },
          attributes: { Addr_type: "POI" },
        }] }),
      });
    }
    problems.push(`unexpected external request: ${url.origin}${url.pathname}`);
    return route.abort("blockedbyclient");
  });
  return state;
}

async function verifyMapRecovery(page, context, mock, base) {
  const map = page.locator(".geo-map-shell").first();
  const notice = map.locator(".map-basemap-notice");
  const backgrounds = map.getByRole("group", { name: "Choose map background" });
  const stateIs = (value) => expect(map).toHaveAttribute("data-basemap-state", value, { timeout: 18_000 });
  const overlaysRemain = async () => {
    assert.ok(Number(await map.getAttribute("data-area-feature-count")) > 0, "planning boundaries must remain bound during map-background failure");
    await expect(map.locator(".leaflet-overlay-pane canvas, .leaflet-overlay-pane path").first()).toBeVisible();
  };

  await stateIs("ready");
  mock.mode = "blocked";
  await backgrounds.getByRole("button", { name: "Satellite", exact: true }).click();
  await stateIs("unavailable");
  assert.equal(await map.locator('img.leaflet-tile[src^="blob:"]').count(), 0, "403 images must not be displayed as tiles");
  await overlaysRemain();
  await expect(page.locator(".ranked-areas").getByText("Ko Chang", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "ใช้ภาษาไทย", exact: true }).click();
  await expect(notice.getByRole("button", { name: "ลองอีกครั้ง", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Use English", exact: true }).click();

  mock.mode = "ready";
  await notice.getByRole("button", { name: "Retry", exact: true }).click();
  await stateIs("ready");
  mock.mode = "partial";
  await backgrounds.getByRole("button", { name: "Street", exact: true }).click();
  await stateIs("partial");
  assert.ok(await map.locator('img.leaflet-tile[src^="blob:"]').count() > 0, "partial state must retain successful tiles");
  await overlaysRemain();

  mock.mode = "stalled";
  await notice.getByRole("button", { name: "Retry", exact: true }).click();
  await stateIs("loading");
  await stateIs("unavailable");
  await overlaysRemain();
  await notice.getByRole("button", { name: "Hide background", exact: true }).click();
  await stateIs("hidden");
  await overlaysRemain();
  mock.mode = "ready";
  await notice.getByRole("button", { name: "Show background", exact: true }).click();
  await stateIs("ready");
  // Completing cancelled requests must not overwrite a newer successful layer.
  await Promise.all(mock.pending.splice(0).map((route) => route.fulfill(TILE_RESPONSE).catch(() => undefined)));
  await stateIs("ready");

  mock.mode = "blocked";
  await backgrounds.getByRole("button", { name: "Terrain", exact: true }).click();
  await stateIs("unavailable");
  mock.mode = "ready";
  await notice.getByRole("button", { name: "Switch to Satellite", exact: true }).click();
  await stateIs("ready");
  await backgrounds.getByRole("button", { name: "Terrain", exact: true }).click();
  await stateIs("ready");
  await backgrounds.getByRole("button", { name: "Street", exact: true }).click();
  await stateIs("ready");
  await context.setOffline(true);
  await stateIs("offline");
  await overlaysRemain();
  await context.setOffline(false);
  await stateIs("ready");
  assert.ok(mock.referrers.length > 0);
  assert.ok(mock.referrers.every((value) => value === `${base}/`), "tile requests must send only the origin despite the page no-referrer policy");
  console.log("  ok  map 403 images, partial loads, timeout, retry, hide/show, provider switching, offline and origin-only referrers");
}

async function verifyPublicLocation(page, context, mock, base) {
  const map = page.locator(".geo-map-shell").first();
  await expect(map).toHaveAttribute("data-basemap-state", "ready", { timeout: 18_000 });
  await expect(map).toHaveAttribute("data-location-source", "none");
  await page.getByRole("combobox", { name: "Search for an exact address" }).fill("Mae Sai Hospital");
  await page.getByRole("option", { name: /Mae Sai Hospital/ }).click();
  await expect(map).toHaveAttribute("data-location-source", "address");
  assert.ok(mock.geocoderRequests.length > 0, "address search must reach the specifically allowed geocoder");
  assert.ok(mock.geocoderRequests.every(({ headers }) => !headers.referer), "address search must not send a Referer");
  assert.ok(mock.geocoderRequests.some(({ url }) => url.searchParams.get("SingleLine") === "Mae Sai Hospital"));
  await context.grantPermissions(["geolocation"], { origin: base });
  await context.setGeolocation({ latitude: 20.425, longitude: 99.884, accuracy: 15 });
  await page.getByRole("button", { name: "Use my location", exact: true }).click();
  await expect(map).toHaveAttribute("data-location-source", "gps");
  await expect(map).toHaveAttribute("data-location-accuracy", "15");
  await expect(page.getByText(/GPS ±15 m/)).toBeVisible();
  console.log("  ok  public address selection and opt-in synthetic GPS under production policies");
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

function globalHeaders() {
  const config = JSON.parse(readFileSync(VERCEL_JSON, "utf8"));
  const entry = (config.headers ?? []).find((h) => h.source === "/(.*)");
  if (!entry) throw new Error("vercel.json has no global /(.*) header block");
  return Object.fromEntries(entry.headers.map((h) => [h.key, h.value]));
}

async function main() {
  if (!existsSync(OUT_DIR)) {
    throw new Error(`Static export missing at ${OUT_DIR}. Run 'pnpm build:web' first.`);
  }
  const headers = globalHeaders();
  for (const required of [
    "Content-Security-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
  ]) {
    if (!headers[required]) throw new Error(`vercel.json is missing ${required}`);
  }

  const server = createServer(async (req, res) => {
    let path = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    if (path.endsWith("/")) path += "index.html";
    let file = join(OUT_DIR, path);
    if (!existsSync(file) && existsSync(`${file}.html`)) file = `${file}.html`;
    for (const [key, value] of Object.entries(headers)) res.setHeader(key, value);
    if (!existsSync(file)) {
      res.writeHead(404).end("not found");
      return;
    }
    res.setHeader("Content-Type", MIME[extname(file)] ?? "application/octet-stream");
    res.writeHead(200).end(await readFile(file));
  });

  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;

  const browser = await launchFloodGuardBrowser();
  const failures = [];
  try {
    for (const route of ROUTES) {
      const context = await browser.newContext({ serviceWorkers: "block" });
      await context.addInitScript(() => window.localStorage.setItem("floodguard:language:v1", "en"));
      const page = await context.newPage();
      const problems = [];
      const mock = await mockExternalServices(context, base, problems);
      page.on("console", (message) => {
        const text = message.text();
        const tileFailure = TILE_ORIGINS.has(new URL(message.location().url || base, base).origin)
          && /403|ERR_ABORTED|ERR_FAILED|ERR_INTERNET_DISCONNECTED/.test(text);
        if (message.type() === "error" && !tileFailure) problems.push(`console: ${text}`);
        if (/Content Security Policy|Refused to/i.test(text)) problems.push(`CSP: ${text}`);
      });
      page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
      page.on("requestfailed", (request) => {
        const url = new URL(request.url());
        const reason = request.failure()?.errorText ?? "failed";
        if (TILE_ORIGINS.has(url.origin) || reason === "net::ERR_ABORTED") return;
        problems.push(`request failed: ${url.pathname}: ${reason}`);
      });

      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      // Hydration is the thing 'unsafe-inline' protects; if it were blocked the
      // React root would stay empty.
      const rendered = await page.evaluate(
        () => (document.body.innerText ?? "").trim().length,
      );
      if (rendered < 50) problems.push(`route rendered only ${rendered} chars of text`);

      try {
        if (route === "/command/") await verifyMapRecovery(page, context, mock, base);
        if (route === "/public/") await verifyPublicLocation(page, context, mock, base);
      } catch (error) {
        problems.push(error.message);
      }

      if (problems.length) failures.push(`${route}\n    ${problems.join("\n    ")}`);
      else console.log(`  ok  ${route} (${rendered} chars rendered)`);
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (failures.length) {
    throw new Error(`CSP smoke failed:\n  ${failures.join("\n  ")}`);
  }
  console.log("csp smoke: all routes render under production security headers");
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
