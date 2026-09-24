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
import { readFile } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const OUT_DIR = resolve(HERE, "..", "out");
const VERCEL_JSON = resolve(HERE, "..", "..", "..", "vercel.json");

const ROUTES = ["/", "/public/", "/public-cases/", "/command/", "/command/cases/", "/command/archive/", "/studio/", "/studio/library/", "/studio/brief/", "/studio/archive/"];

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

async function verifyPublicBlockedTiles(browser, base, responseKind) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  // OSM's policy-block response is a valid 256px PNG with a black/yellow rail.
  // Generate that visual signature locally so the test does not redistribute
  // the provider's artwork or depend on a live blocked response.
  const blockedPng = responseKind === "png" ? Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    const context = canvas.getContext("2d");
    context.fillStyle = "#fff";
    context.fillRect(0, 0, 256, 256);
    for (const [y, color] of [[20, "#000"], [40, "#ff0"], [60, "#000"], [80, "#ff0"], [100, "#ff0"], [120, "#000"], [150, "#000"], [170, "#ff0"]]) {
      context.fillStyle = color;
      context.fillRect(8, y - 4, 12, 8);
    }
    context.fillStyle = "#111";
    context.font = "bold 22px sans-serif";
    context.fillText("403 Access blocked", 24, 80);
    return canvas.toDataURL("image/png").split(",")[1];
  }), "base64") : null;
  const problems = [];
  let tileRequests = 0;
  const tileUrl = "https://tile.openstreetmap.org/";
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  await page.route(`${tileUrl}**`, async (route) => {
    tileRequests += 1;
    await route.fulfill(responseKind === "png"
      ? { status: 403, contentType: "image/png", body: blockedPng, headers: { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" } }
      : { status: 403, contentType: "text/plain", body: "403 Access blocked", headers: { "Access-Control-Allow-Origin": "*", "Cache-Control": "no-store" } });
  });

  try {
    await page.goto(`${base}/public/`, { waitUntil: "networkidle" });
    const shell = page.locator(".public-home-map .geo-map-shell");
    await page.waitForFunction(() => {
      const shell = document.querySelector(".public-home-map .geo-map-shell");
      return shell?.getAttribute("data-map-ready") === "true"
        && Number(shell.getAttribute("data-area-feature-count")) > 0;
    }, null, { timeout: 15_000 });
    if (tileRequests === 0) problems.push("No OpenStreetMap tile request was intercepted");

    const checkFallback = async (step) => {
      const state = await shell.getAttribute("data-basemap-state");
      const tileImages = await shell.locator(".leaflet-tile-pane img.leaflet-tile").count();
      const localOverlays = await shell.locator(".leaflet-overlay-pane canvas, .leaflet-overlay-pane path").count();
      if (state !== "unavailable") problems.push(`${step}: expected unavailable basemap, got ${state}`);
      if (tileImages !== 0) problems.push(`${step}: ${tileImages} blocked tile images still cover the map`);
      if (localOverlays === 0) problems.push(`${step}: local area overlays disappeared`);
    };
    await checkFallback("initial 403");

    await page.getByRole("button", { name: "Use English", exact: true }).click();
    const notice = shell.locator(".map-basemap-notice");
    const noticeText = await notice.count() ? await notice.innerText() : "";
    if (!noticeText.includes("Map background unavailable; boundaries and evidence remain visible.")) {
      problems.push("Missing truthful map-background fallback notice");
    }
    const retry = notice.getByRole("button", { name: "Retry", exact: true });
    if (await retry.count()) {
      await retry.click();
      await page.waitForFunction(() => document.querySelector(".public-home-map .geo-map-shell")?.getAttribute("data-basemap-state") === "unavailable");
      await checkFallback("retry after 403");
    } else {
      problems.push("Missing map-background Retry action");
    }

    const menu = shell.locator(".map-basemap-menu");
    await menu.locator("summary").click();
    await menu.getByRole("button", { name: "Hide background", exact: true }).click();
    await page.waitForFunction(() => document.querySelector(".public-home-map .geo-map-shell")?.getAttribute("data-basemap-state") === "hidden");
    if (await shell.getAttribute("data-basemap-state") !== "hidden") problems.push("Hide background did not set the hidden state");
    if (await shell.locator(".leaflet-overlay-pane canvas, .leaflet-overlay-pane path").count() === 0) problems.push("Hide background removed local overlays");
    const show = notice.getByRole("button", { name: "Show background", exact: true });
    if (await show.count()) {
      await show.click();
      await page.waitForFunction(() => document.querySelector(".public-home-map .geo-map-shell")?.getAttribute("data-basemap-state") === "unavailable");
      await checkFallback("show after 403");
    } else {
      problems.push("Missing Show background action while hidden");
    }
  } finally {
    await context.close();
  }

  if (problems.length) throw new Error(`${responseKind} 403 tile fallback:\n    ${problems.join("\n    ")}`);
  console.log(`  ok  /public/ (${responseKind} 403 tiles removed; overlays and controls retained)`);
}

async function verifyIsolatedTileFailure(browser, base) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  const tilePng = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 256;
    return canvas.toDataURL("image/png").split(",")[1];
  }), "base64");
  let requests = 0;
  try {
    await page.route("https://tile.openstreetmap.org/**", async (route) => {
      requests += 1;
      await route.fulfill(requests === 1
        ? { status: 403, contentType: "text/plain", body: "single missing tile", headers: { "Access-Control-Allow-Origin": "*" } }
        : { status: 200, contentType: "image/png", body: tilePng, headers: { "Access-Control-Allow-Origin": "*" } });
    });
    await page.goto(`${base}/public/`, { waitUntil: "networkidle" });
    const shell = page.locator(".public-home-map .geo-map-shell");
    await page.waitForFunction(() => document.querySelector(".public-home-map .geo-map-shell")?.getAttribute("data-basemap-state") === "ready");
    if (requests < 2 || await shell.locator(".leaflet-tile-pane img.leaflet-tile").count() === 0) {
      throw new Error("An isolated tile failure removed the otherwise usable basemap");
    }
    console.log("  ok  /public/ (one failed tile does not remove a usable background)");
  } finally {
    await context.close();
  }
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
  if (headers["Referrer-Policy"] !== "strict-origin-when-cross-origin") {
    throw new Error("Cross-origin web tile requests must send an origin-only referrer.");
  }
  if (!headers["Permissions-Policy"]?.includes("geolocation=(self)")) {
    throw new Error("The visible Public location control requires same-origin geolocation permission.");
  }
  for (const origin of ["https://geocode.arcgis.com", "https://routing.openstreetmap.de"]) {
    if (!headers["Content-Security-Policy"].includes(origin)) {
      throw new Error(`Public search or routing origin is missing from CSP: ${origin}`);
    }
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
      const context = await browser.newContext();
      const page = await context.newPage();
      const problems = [];
      page.on("console", (message) => {
        const text = message.text();
        // Tile requests to external hosts fail in a sandbox with no network;
        // that is an environment artifact, not a CSP violation.
        const offline =
          text.includes("tile.openstreetmap.org") ||
          text.includes("arcgisonline.com") ||
          text.includes("opentopomap.org");
        if (message.type() === "error" && !offline) problems.push(`console: ${text}`);
        if (/Content Security Policy|Refused to/i.test(text)) problems.push(`CSP: ${text}`);
      });
      page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));

      await page.goto(`${base}${route}`, { waitUntil: "networkidle" });
      // Hydration is the thing 'unsafe-inline' protects; if it were blocked the
      // React root would stay empty.
      const rendered = await page.evaluate(
        () => (document.body.innerText ?? "").trim().length,
      );
      if (rendered < 50) problems.push(`route rendered only ${rendered} chars of text`);

      if (problems.length) failures.push(`${route}\n    ${problems.join("\n    ")}`);
      else console.log(`  ok  ${route} (${rendered} chars rendered)`);
      await context.close();
    }
    for (const responseKind of ["text", "png"]) {
      try {
        await verifyPublicBlockedTiles(browser, base, responseKind);
      } catch (error) {
        failures.push(error instanceof Error ? error.message : String(error));
      }
    }
    try {
      await verifyIsolatedTileFailure(browser, base);
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
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
