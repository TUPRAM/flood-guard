import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { cpus, platform } from "node:os";
import { dirname, extname, resolve, sep } from "node:path";
import { gzipSync } from "node:zlib";
import AxeBuilder from "@axe-core/playwright";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const require = createRequire(import.meta.url);
const sharp = require(require.resolve("sharp", { paths: [dirname(require.resolve("next/package.json"))] }));
const out = resolve(process.env.FLOODGUARD_LANDING_OUT ?? "out");
const evidence = resolve(process.env.FLOODGUARD_DESKTOP_EVIDENCE ?? "test-results/landing-v3/browser");
const baseline = resolve(process.env.FLOODGUARD_V2_BASELINE ?? "C:/Users/iputu/Documents/Project Support/FloodGuard/landing-2026-09-09-v2");
const arguments_ = process.argv.slice(2);
const desktopOnly = arguments_.includes("--desktop-only");
const mobileBaselineOnly = arguments_.includes("--mobile-baseline");
assert(!(desktopOnly && mobileBaselineOnly), "--desktop-only and --mobile-baseline are mutually exclusive");
assert(arguments_.filter((argument) => argument.startsWith("--")).every((argument) => ["--desktop-only", "--mobile-baseline"].includes(argument)), "Unknown desktop QA option");
const requested = new Set(arguments_.filter((argument) => !argument.startsWith("--")));
const chapters = ["place", "dry", "flood", "access", "public", "command", "studio", "shared"];
const desktop = { width: 1440, height: 1000 };
const report = { result: "STARTED", recordedAt: new Date().toISOString(), configuration: "Local static competition export with deployed CSP headers, gzip text, Chromium headless, DPR1, no throttling, service workers blocked. Desktop V3 only; V2 mobile is checked against the dated archived baseline. Lab results are not field performance or owner acceptance.", budgets: { initialTransferBytes: 2 * 1024 * 1024, fullStoryTransferBytes: 3 * 1024 * 1024, accumulatedNonInputLayoutShift: .1, visibleTriangles: 250000, drawCalls: 45 }, device: { platform: platform(), cpu: cpus()[0]?.model }, cases: [], screenshots: [], recordings: [], samples: [], scrollMotion: [], interludeChecks: [], accessibility: [], mobileComparisons: [] };
report.selection = { group: desktopOnly ? "desktop-only" : mobileBaselineOnly ? "mobile-baseline" : "all", namedCases: [...requested] };
mkdirSync(evidence, { recursive: true });
const reportPath = resolve(evidence, "desktop-landing-smoke.json");
const hash = (value) => createHash("sha256").update(value).digest("hex");
const saveReport = () => writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
report.clockContract = {
  description: "ScrollTrigger rounds numeric start/end to integer pixels; GSAP core rounds a plain numeric tween property to six decimals; the runtime then maps that clock through its original measured chapter anchors. QA uses these same operations and retains the 2e-6 telemetry tolerance.",
  sources: ["node_modules/gsap/ScrollTrigger.js", "node_modules/gsap/gsap-core.js"].map((path) => ({ path, sha256: hash(readFileSync(path)) })),
  preservedDiagnostic: "test-results/landing-v3/settle-diagnostics/desktop-landing-smoke.json",
  observedCases: [
    { viewport: "1366x768", scrollY: 1513, originalEnd: 7141.5575, roundedEnd: 7142, correctedExpected: .20002202527366536, observedRootAndGPU: .200022 },
    { viewport: "1536x1024", scrollY: 2034, originalEnd: 9374.390625, roundedEnd: 9374, correctedExpected: .19998893739715573, observedRootAndGPU: .199989 },
    { viewport: "2048x1152", scrollY: 2313, originalEnd: 10571.1875, roundedEnd: 10571, correctedExpected: .1999605190934245, observedRootAndGPU: .199961 },
  ],
};
saveReport();

assert.equal(JSON.parse(readFileSync(resolve(out, "deployment-profile.json"), "utf8")).profile, "competition");
report.artifact = {
  entrySha256: hash(readFileSync(resolve(out, "index.html"))),
  cacheName: JSON.parse(readFileSync(resolve(out, "sw.js"), "utf8").match(/^const CACHE_NAME = ("[^"]+");/m)?.[1] ?? "null"),
  offlineManifestSha256: hash(readFileSync(resolve(out, "offline-assets.json"))),
};
assert(report.artifact.cacheName, "Build the competition export before desktop QA");
const baselineReport = JSON.parse(readFileSync(resolve(baseline, "browser/landing-smoke.json"), "utf8"));
assert.equal(baselineReport.result, "PASS");
const baselineAssets = JSON.parse(readFileSync(resolve(baseline, "source/apps/web/public/landing/assets-manifest.json"), "utf8"));
assert.equal(hash(readFileSync(resolve(out, "landing/assets-manifest.json"))), hash(readFileSync(resolve(baseline, "source/apps/web/public/landing/assets-manifest.json"))), "The complete V2 asset manifest must remain byte-identical");
report.mobileBaseline = { directory: baseline, reportSha256: hash(readFileSync(resolve(baseline, "browser/landing-smoke.json"))), recordedAt: baselineReport.recordedAt, artifact: baselineReport.artifact, unchangedAssets: [] };
for (const asset of baselineAssets.assets) {
  const current = resolve(out, asset.path.replace(/^\/+/, ""));
  assert(current.startsWith(`${out}${sep}`));
  assert.equal(hash(readFileSync(current)), asset.sha256, `Preserve V2 fallback asset ${asset.path}`);
  report.mobileBaseline.unchangedAssets.push({ path: asset.path, sha256: asset.sha256 });
}
const desktopManifestPath = resolve(out, "landing/desktop-v3/assets-manifest.json");
const desktopManifest = JSON.parse(readFileSync(desktopManifestPath, "utf8"));
assert.equal(desktopManifest.status, "generated_and_browser_rendered_not_geographically_validated");
assert.equal(desktopManifest.plan.sourceStatus, "original_illustrative_geography_not_surveyed");
assert(desktopManifest.provenance.length > 0);
for (const source of desktopManifest.editableSources) {
  const data = readFileSync(resolve(source.path));
  assert.equal(data.length, source.bytes, `Desktop source size changed after asset generation: ${source.path}`);
  assert.equal(hash(data), source.sha256, `Desktop source changed after asset generation: ${source.path}`);
}
for (const asset of desktopManifest.assets) {
  const file = resolve(out, asset.path.replace(/^\/+/, ""));
  assert(file.startsWith(`${out}${sep}`));
  const data = readFileSync(file), dimensions = await sharp(data).metadata();
  assert.equal(data.length, asset.bytes);
  assert.equal(hash(data), asset.sha256);
  assert.equal(dimensions.width, asset.width);
  assert.equal(dimensions.height, asset.height);
  assert.equal(asset.worldId, desktopManifest.worldId);
}
const dryAsset = desktopManifest.assets.find((asset) => asset.id === "dry");
const floodedAsset = desktopManifest.assets.find((asset) => asset.id === "flood");
assert.equal(dryAsset.cameraSignature, floodedAsset.cameraSignature);
assert.deepEqual(dryAsset.landmarks, floodedAsset.landmarks);
assert.equal(dryAsset.floodAmount, 0);
assert.equal(floodedAsset.floodAmount, 1);
report.desktopProvenance = { manifestSha256: hash(readFileSync(desktopManifestPath)), ...desktopManifest };
const rendererFiles = readdirSync(resolve(out, "_next/static/chunks")).filter((name) => name.endsWith(".js") && readFileSync(resolve(out, "_next/static/chunks", name), "utf8").includes("data-desktop-canvas")).map((name) => `/_next/static/chunks/${name}`);
assert(rendererFiles.length > 0, "The export must contain the V3 desktop renderer");
report.rendererAssets = rendererFiles.map((path) => { const data = readFileSync(resolve(out, path.slice(1))); return { path, bytes: data.length, gzipBytes: gzipSync(data).length, sha256: hash(data) }; });
const vercel = JSON.parse(readFileSync(resolve("../../vercel.json"), "utf8"));
const headers = Object.fromEntries((vercel.headers ?? []).find((entry) => entry.source === "/(.*)")?.headers.map(({ key, value }) => [key, value]) ?? []);
report.securityHeaders = headers;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".glb": "model/gltf-binary", ".txt": "text/plain", ".webmanifest": "application/manifest+json" };
const server = createServer((request, response) => {
  const path = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
  let file = resolve(out, path || "index.html");
  if (file !== out && !file.startsWith(`${out}${sep}`)) return response.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
  if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
  const gzip = /\.(html|css|js|json|svg|txt)$/.test(file) && (request.headers["accept-encoding"] ?? "").split(",").some((part) => {
    const [encoding, ...parameters] = part.trim().split(";");
    return encoding === "gzip" && !parameters.some((parameter) => /^q\s*=\s*0(?:\.0*)?$/.test(parameter.trim()));
  });
  response.writeHead(200, { ...headers, "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store", ...(gzip ? { "Content-Encoding": "gzip" } : {}) });
  const data = readFileSync(file);
  response.end(gzip ? gzipSync(data) : data);
});
await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await launchFloodGuardBrowser();
report.browser = browser.version();

try {
  if (mobileBaselineOnly) assert.equal(browser.version(), baselineReport.browser, "Mobile preservation requires the archived baseline browser version; unset FLOODGUARD_BROWSER_EXECUTABLE or provide that exact browser");
  await runCase("desktop-story", { viewport: desktop, record: true }, async (page) => {
    await expectEnhanced(page);
    await pointerReset(page);
    await seek(page, 0);
    report.initialHeroGeometry = await heroGeometry(page);
    const canvas = await page.locator("[data-desktop-canvas] canvas").elementHandle();
    report.webglDriver = await canvas.evaluate((element) => {
      const gl = element.getContext("webgl2"), debug = gl.getExtension("WEBGL_debug_renderer_info");
      return { version: gl.getParameter(gl.VERSION), renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), vendor: debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR) };
    });
    report.initialResources = await resources(page);
    saveReport();
    console.log(`desktop initial performance captured: ${JSON.stringify({ transferBytes: report.initialResources.transferBytes, lcpMs: report.initialResources.metrics.lcp, accumulatedShift: report.initialResources.metrics.cls })}`);
    assert(report.initialResources.transferBytes <= report.budgets.initialTransferBytes, "Initial transfer exceeds the agreed V3 2MiB limit");
    assert(report.initialResources.metrics.cls <= 0.1, "Initial layout shifts exceed0.1");
    await capture(page, "desktop-hero-far");
    const initial = await sample(page, "far", true);
    const states = {};
    for (const [name, progress] of [["flight-early", .08], ["flight-mid", .12], ["flight-late", .16], ["close-dry", .20], ["opaque-interlude", .26], ["re-exposure", .31], ["flood-rise", .37], ["post-flood", .43], ["resident", .60], ["planner", .73], ["research", .85], ["closing-flooded", .95]]) {
      await animateScroll(page, progress, 1000);
      await settle(page, progress, name !== "opaque-interlude");
      assert(await canvas.evaluate((element) => element.isConnected && element === document.querySelector("[data-desktop-canvas] canvas")), "Desktop motion must retain one canvas instance");
      assert.equal(await page.locator("[data-story] canvas").count(), 1);
      states[name] = await sample(page, name, name !== "opaque-interlude");
      await capture(page, `desktop-${name}`);
      if (name === "opaque-interlude") {
        assert(states[name].interlude >= .999, "The reading interlude must be fully opaque");
        await assertOpaqueInterlude(page, name);
        await assertIdle(page, "full opaque interlude");
      }
    }
    assert.notEqual(initial.cameraSignature, states["close-dry"].cameraSignature, "Flight must change the actual rendered viewpoint");
    assert.equal(states["close-dry"].cameraSignature, states["flood-rise"].cameraSignature, "Flood onset must hold the close dry camera");
    assert.equal(states["close-dry"].cameraSignature, states["post-flood"].cameraSignature, "Flooded comparison must preserve the dry camera");
    assert.deepEqual(states["close-dry"].landmarks, states["post-flood"].landmarks, "Dry/flood landmarks must stay registered");
    assert(states["close-dry"].floodAmount <= .001);
    assert(states["flood-rise"].floodAmount > .05 && states["flood-rise"].floodAmount < .99);
    assert(states["post-flood"].floodAmount >= .999 && states["closing-flooded"].floodAmount >= .999, "Closing must retain the flooded world");
    await seek(page, .26);
    const reverseCovered = await sample(page, "reverse-covered-dry");
    assert(reverseCovered.floodAmount <= .001, "A direct reverse seek must reset the hidden world to dry");
    assert.equal(reverseCovered.cameraSignature, states["close-dry"].cameraSignature);
    await assertIdle(page, "reverse opaque interlude");
    await seek(page, .32);
    assert((await sample(page, "reverse-re-exposed-dry", true)).floodAmount <= .001);
    await seek(page, .20);
    const reverse = await sample(page, "reverse-close-dry", true);
    assert.equal(reverse.cameraSignature, states["close-dry"].cameraSignature);
    assert.deepEqual(reverse.landmarks, states["close-dry"].landmarks);
    assert(reverse.floodAmount <= .001, "Reverse must restore dry state deterministically");
    await seek(page, 0);
    await capture(page, "desktop-reversed-far");
    report.fullResources = await resources(page);
    assert(report.fullResources.transferBytes <= report.budgets.fullStoryTransferBytes, "Full story transfer exceeds the agreed V3 3MiB limit");
    assert(report.fullResources.metrics.cls <= .1, "Full-story layout shifts exceed0.1");
    await canvas.dispose();
    await auditAccessibility(page, "desktop-hero");
  });

  await runCase("pointer-and-idle", { viewport: desktop }, async (page) => {
    await expectEnhanced(page);
    await pointerReset(page);
    await seek(page, .20);
    const neutral = await sample(page, "pointer-neutral");
    await movePointer(page, 300, 600);
    const left = await sample(page, "pointer-left", true);
    await movePointer(page, 1300, 700);
    const right = await sample(page, "pointer-right", true);
    assert.notEqual(left.cameraSignature, right.cameraSignature, "Pointer wiggle must change the rendered camera");
    assert.equal(left.floodAmount, right.floodAmount, "Pointer must not change flood state");
    await pointerReset(page);
    await settle(page, .20);
    const reset = await sample(page, "pointer-reset", true);
    assert.equal(reset.cameraSignature, neutral.cameraSignature, "Leaving the page must restore exact neutral camera");
    await assertIdle(page, "visible stationary scene");
    await seek(page, .26);
    await page.mouse.move(1200, 500);
    await assertIdle(page, "pointer movement behind the opaque cover");
    await seek(page, .20);
    await page.evaluate(() => { Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" }); document.dispatchEvent(new Event("visibilitychange")); });
    await page.waitForFunction(() => document.querySelector("[data-desktop-canvas]")?.getAttribute("data-scene-active") === "false");
    await assertIdle(page, "synthetic document-hidden policy");
    await page.evaluate(() => { delete document.visibilityState; document.dispatchEvent(new Event("visibilitychange")); });
    await expectEnhanced(page);
    await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForFunction(() => document.querySelector("[data-desktop-canvas]")?.getAttribute("data-scene-active") === "false");
    await assertIdle(page, "offscreen scene");
  });

  await runCase("hero-keyboard-reveal", { viewport: desktop }, async (page) => {
    await expectEnhanced(page);
    await seek(page, 0);
    let focusedControls = null;
    for (let index = 0; index < 24; index += 1) {
      await page.keyboard.press("Tab");
      focusedControls = await page.evaluate(() => {
        const active = document.activeElement, controls = active?.closest("[data-story-controls]");
        if (!controls) return null;
        const rect = active.getBoundingClientRect(), style = getComputedStyle(controls);
        const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return { opacity: Number(style.opacity), visibility: style.visibility, bounds: rect.toJSON(), viewportHeight: innerHeight, unobscured: active === hit || active.contains(hit) };
      });
      if (focusedControls) break;
    }
    assert(focusedControls, "The far-state chapter controls must remain keyboard discoverable through their focus-reveal behavior");
    assert(focusedControls.opacity === 1 && focusedControls.visibility === "visible" && focusedControls.unobscured, "Keyboard focus must reveal opaque, unobscured controls");
    assert(focusedControls.bounds.top >= 0 && focusedControls.bounds.bottom <= focusedControls.viewportHeight + 1, "Focused chapter control must fit in the viewport");
    report.heroKeyboardReveal = focusedControls;
    await capture(page, "hero-keyboard-reveal");
  });

  for (const id of ["dry", "flood", "access", "studio", "shared"]) {
    await runCase(`anchor-${id}`, { viewport: desktop, path: `/#${id}` }, async (page) => {
      await expectEnhanced(page);
      await page.waitForFunction((id) => document.querySelector("[data-story]")?.getAttribute("data-active-chapter-id") === id, id);
      assert(await page.locator(`#${id}`).evaluate((element) => { const rect = element.getBoundingClientRect(); return rect.bottom > 0 && rect.top < innerHeight; }), "Native anchor must expose its requested content");
      await capture(page, `anchor-${id}`);
      await seek(page, .20);
      assert((await sample(page, `anchor-${id}-reversed`)).floodAmount <= .001);
    });
  }

  for (const viewport of [{ width: 1280, height: 720 }, { width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1536, height: 1024 }, { width: 1920, height: 1080 }, { width: 2048, height: 1152 }]) {
    await runCase(`viewport-${viewport.width}x${viewport.height}`, { viewport }, async (page) => {
      await expectEnhanced(page);
      await seek(page, 0);
      const hero = await heroGeometry(page);
      report.samples.push({ name: `hero-${viewport.width}x${viewport.height}`, ...hero });
      await capture(page, `viewport-${viewport.width}x${viewport.height}-hero`);
      await seek(page, .20);
      await sample(page, `viewport-${viewport.width}x${viewport.height}-dry`, true);
      await capture(page, `viewport-${viewport.width}x${viewport.height}-dry`);
      await seek(page, .26);
      await assertOpaqueInterlude(page, `${viewport.width}x${viewport.height}`);
      await capture(page, `viewport-${viewport.width}x${viewport.height}-interlude`);
      await noOverflow(page);
    });
  }

  await runCase("resize-policy", { viewport: desktop }, async (page) => {
    await expectEnhanced(page);
    await seek(page, .43);
    await page.setViewportSize({ width: 390, height: 844 });
    await expectStatic(page);
    await capture(page, "resize-mobile-static");
    await page.setViewportSize(desktop);
    await expectEnhanced(page);
    await pointerReset(page);
    await seek(page, .43);
    assert((await sample(page, "resize-restored", true)).floodAmount >= .999);
  });

  for (const [name, options, prepare] of [
    ["reduced-motion", { reducedMotion: "reduce" }],
    ["no-javascript", { javaScriptEnabled: false }],
    ["stored-static", {}, (page) => page.addInitScript(() => localStorage.setItem("floodguard:landing-motion:v1", "static"))],
    ["save-data", {}, (page) => page.addInitScript(() => { const connection = new EventTarget(); Object.defineProperty(connection, "saveData", { value: true }); Object.defineProperty(navigator, "connection", { configurable: true, value: connection }); })],
    ["offline-policy", { path: "/#shared" }, (page) => page.addInitScript(() => Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false }))],
    ["webgl-unavailable", {}, (page) => page.addInitScript(() => { const original = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (type, ...args) { return /webgl/.test(type) ? null : original.call(this, type, ...args); }; })],
  ]) {
    await runCase(name, { viewport: desktop, ...options }, async (page) => {
      await expectStatic(page);
      assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
      await capture(page, name);
      if (name !== "webgl-unavailable") assert.deepEqual((await resources(page)).entries.filter((entry) => rendererFiles.includes(entry.path)), [], "Static policy must not request the desktop renderer");
    }, prepare);
  }

  await runCase("renderer-download-failure", { viewport: desktop }, async (page) => {
    await expectStatic(page);
    await capture(page, "renderer-download-failure");
  }, (page) => page.route((url) => rendererFiles.includes(url.pathname), (route) => route.abort()));

  await runCase("slow-desktop-assets", { viewport: desktop, waitUntil: "domcontentloaded" }, async (page) => {
    await page.waitForFunction(() => { const image = document.querySelector("[data-story-aerial] img"); return image?.complete && image.naturalWidth > 0; });
    await capture(page, "desktop-loading-placeholder");
    await assertBackdropPixels(page, "loading before poster and renderer");
    await expectEnhanced(page);
    await capture(page, "desktop-loaded-after-delay");
    await sample(page, "loaded-after-delay", true);
  }, (page) => page.route((url) => rendererFiles.includes(url.pathname) || url.pathname === "/landing/desktop-v3/far.webp", async (route) => { await new Promise((done) => setTimeout(done, 4000)); await route.continue().catch(() => {}); }));

  await runCase("poster-failure", { viewport: desktop }, async (page) => {
    await expectEnhanced(page);
    await sample(page, "renderer-without-poster", true);
    await capture(page, "desktop-poster-failure-renderer-ready");
  }, (page) => page.route("**/landing/desktop-v3/far.webp", (route) => route.abort()));

  await runCase("context-loss", { viewport: desktop }, async (page) => {
    await expectEnhanced(page);
    await page.locator("[data-desktop-canvas] canvas").evaluate((canvas) => { const gl = canvas.getContext("webgl2"); const extension = gl?.getExtension("WEBGL_lose_context"); if (!extension) throw new Error("Cannot inject WebGL context loss"); extension.loseContext(); });
    await expectStatic(page);
    await capture(page, "context-loss-static");
  });

  for (const [name, viewport] of [["mobile", { width: 390, height: 844 }], ["narrow", { width: 320, height: 768 }]]) {
    await runCase(`v2-${name}-unchanged`, { viewport }, async (page) => {
      await expectStatic(page);
      assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
      assert.deepEqual((await resources(page)).entries.filter((entry) => rendererFiles.includes(entry.path)), []);
      assert.deepEqual((await resources(page)).entries.filter((entry) => entry.path.startsWith("/landing/desktop-v3/")), [], "Mobile must not download V3-only art");
      await compareMobile(page, `${name}-hero`);
      await page.locator("#studio").scrollIntoViewIfNeeded();
      await page.locator("#studio img").evaluate(async (image) => { await image.decode(); });
      await compareMobile(page, `${name}-studio`);
      if (name === "mobile") {
        await auditAccessibility(page, "v2-mobile");
        await page.locator("[data-opening-provenance]").scrollIntoViewIfNeeded();
        await compareMobile(page, "mobile-source-provenance");
        await page.locator("[data-pwa-availability] > summary").click();
        await compareMobile(page, "mobile-status-open");
        await page.locator("[data-pwa-availability] > summary").click();
        await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
        await compareMobile(page, "mobile-footer-clearance");
      }
    });
  }
  assert(report.cases.length > 0, "No desktop QA cases matched the requested group and names");
  report.result = report.cases.some((entry) => entry.result !== "PASS") ? "FAIL" : "PASS";
} catch (error) {
  report.result = "FAIL";
  report.failure = error.stack ?? error.message;
  throw error;
} finally {
  report.completedAt = new Date().toISOString();
  await browser.close();
  await new Promise((done) => server.close(done));
  saveReport();
}
console.log(JSON.stringify({ result: report.result, cases: report.cases.map(({ name, result, error }) => ({ name, result, error })), reportPath }, null, 2));
if (report.result !== "PASS") process.exitCode = 1;

async function runCase(name, options, check, prepare) {
  if (requested.size && !requested.has(name)) return;
  if (desktopOnly && name.startsWith("v2-")) return;
  if (mobileBaselineOnly && !name.startsWith("v2-")) return;
  const { record, path = "/", waitUntil = "networkidle", ...contextOptions } = options;
  const context = await browser.newContext({ serviceWorkers: "block", deviceScaleFactor: 1, ...(record ? { recordVideo: { dir: resolve(evidence, "recordings"), size: options.viewport } } : {}), ...contextOptions });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  const errors = [], writes = [], external = [], cspViolations = [], networkFailures = [], badResponses = [], consoleDiagnostics = [];
  page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
  page.on("console", (message) => { if (["warning", "error"].includes(message.type())) consoleDiagnostics.push({ type: message.type(), text: message.text(), location: message.location() }); });
  page.on("request", (request) => { if (!/^(GET|HEAD|OPTIONS)$/.test(request.method())) writes.push(`${request.method()} ${request.url()}`); if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== base) external.push(request.url()); });
  page.on("requestfailed", (request) => networkFailures.push({ path: new URL(request.url()).pathname, error: request.failure()?.errorText }));
  page.on("response", (response) => { if (response.status() >= 400) badResponses.push({ path: new URL(response.url()).pathname, status: response.status() }); });
  try {
    await page.addInitScript(() => {
      globalThis.__desktopQA = { lcp: 0, cls: 0, shifts: [], geolocationRequests: 0, csp: [], contextEvents: [] };
      for (const type of ["webglcontextlost", "webglcontextrestored", "webglcontextcreationerror"]) window.addEventListener(type, (event) => globalThis.__desktopQA.contextEvents.push({ type, statusMessage: event.statusMessage ?? null, trusted: event.isTrusted, mountedDesktopCanvas: Boolean(event.target?.closest?.("[data-desktop-canvas]")), connected: Boolean(event.target?.isConnected), time: performance.now() }), true);
      for (const name of ["getCurrentPosition", "watchPosition"]) Object.defineProperty(navigator.geolocation, name, { configurable: true, value: () => { globalThis.__desktopQA.geolocationRequests += 1; } });
      document.addEventListener("securitypolicyviolation", (event) => globalThis.__desktopQA.csp.push({ directive: event.violatedDirective, uri: event.blockedURI }));
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) globalThis.__desktopQA.lcp = entry.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) { if (!entry.hadRecentInput) globalThis.__desktopQA.cls += entry.value; globalThis.__desktopQA.shifts.push({ time: entry.startTime, value: entry.value, hadRecentInput: entry.hadRecentInput, sources: entry.sources.map((source) => ({ element: source.node?.outerHTML?.slice(0, 500), previousRect: source.previousRect.toJSON(), currentRect: source.currentRect.toJSON() })) }); } }).observe({ type: "layout-shift", buffered: true });
    });
    await prepare?.(page);
    await page.goto(`${base}${path}`, { waitUntil });
    await page.locator("main[data-landing]").waitFor({ state: "visible" });
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator("[data-chapter]").count(), chapters.length);
    for (const route of ["/public/", "/command/", "/studio/"]) assert(await page.locator(`header a[href='${route}']`).count() > 0);
    await noOverflow(page);
    await check(page);
    const safety = await page.evaluate(() => globalThis.__desktopQA ?? { csp: [], geolocationRequests: 0 });
    cspViolations.push(...safety.csp);
    assert.equal(safety.geolocationRequests, 0);
    assert.deepEqual(errors, [], "No uncaught browser errors are allowed");
    assert.deepEqual(writes, [], "Landing must not perform operational writes");
    assert.deepEqual(external, [], "Landing must not request external services");
    assert.deepEqual(cspViolations, [], "Desktop must comply with the production CSP");
    if (name !== "context-loss") assert.deepEqual(safety.contextEvents ?? [], [], "Unexpected WebGL context events require diagnosis");
    assert.deepEqual(badResponses, [], "Landing assets must return successful HTTP responses");
    const intentionalNoScriptBlocks = name === "no-javascript" ? networkFailures.filter((entry) => entry.error === "csp" && /^\/_next\/static\/chunks\/[^/]+\.js$/.test(entry.path)) : [];
    assert.deepEqual(networkFailures.filter((entry) => !intentionalNoScriptBlocks.includes(entry) && !(name === "renderer-download-failure" && rendererFiles.includes(entry.path)) && !(name === "poster-failure" && entry.path === "/landing/desktop-v3/far.webp")), [], "Unexpected asset request failures are not allowed");
    report.cases.push({ name, result: "PASS", errors, writes, external, cspViolations, networkFailures, intentionalNoScriptBlocks, badResponses, consoleDiagnostics, contextEvents: safety.contextEvents ?? [], geolocationRequests: safety.geolocationRequests });
  } catch (error) {
    const diagnostic = await page.evaluate(() => {
      const root = document.querySelector("[data-story]"), host = root?.querySelector("[data-desktop-canvas]");
      const stops = JSON.parse(root?.getAttribute("data-story-scroll-stops") ?? "null");
      const index = stops?.findIndex((stop, i) => i < stops.length - 1 && scrollY >= stop.scrollY && scrollY <= stops[i + 1].scrollY);
      const a = index >= 0 ? stops[index] : null, b = index >= 0 ? stops[index + 1] : null;
      const expected = a ? a.progress + (b.progress - a.progress) * (scrollY - a.scrollY) / (b.scrollY - a.scrollY) : scrollY <= stops?.[0]?.scrollY ? 0 : null;
      const totalSpan = stops ? stops.at(-1).scrollY - stops[0].scrollY : null;
      const roundedClock = stops ? Math.round(Math.min(1, Math.max(0, (scrollY - stops[0].scrollY) / totalSpan)) * 1e6) / 1e6 : null;
      const roundedY = stops ? stops[0].scrollY + roundedClock * totalSpan : null;
      const roundedIndex = stops?.findIndex((stop, i) => i < stops.length - 1 && roundedY >= stop.scrollY && roundedY <= stops[i + 1].scrollY);
      const ra = roundedIndex >= 0 ? stops[roundedIndex] : null, rb = roundedIndex >= 0 ? stops[roundedIndex + 1] : null;
      const expectedWithGsapClockRounding = ra ? ra.progress + (rb.progress - ra.progress) * (roundedY - ra.scrollY) / (rb.scrollY - ra.scrollY) : roundedClock === 0 ? 0 : null;
      return { scrollY, viewport: { width: innerWidth, height: innerHeight }, expected, roundedClock, expectedWithGsapClockRounding, root: root ? { ...root.dataset } : null, canvas: host ? { ...host.dataset } : null, settleProbe: globalThis.__desktopSettle, contextEvents: globalThis.__desktopQA?.contextEvents ?? [] };
    }).catch(() => null);
    await capture(page, `${name}-failure`).catch(() => {});
    report.cases.push({ name, result: "FAIL", error: error.message, stack: error.stack, diagnostic, errors, writes, external, cspViolations, networkFailures, badResponses, consoleDiagnostics });
  } finally {
    const video = page.video();
    await context.close();
    if (video) report.recordings.push({ case: name, path: await video.path() });
    saveReport();
    console.log(`desktop landing ${name}: ${report.cases.at(-1)?.result}`);
  }
}

async function expectEnhanced(page) {
  await page.waitForFunction(() => { const root = document.querySelector("[data-story]"); return root?.getAttribute("data-story-variant") === "desktop-world" && root.getAttribute("data-render-mode") === "enhanced"; });
  await page.locator("[data-desktop-canvas][data-ready='true']").waitFor();
  await page.waitForFunction(() => { const aerial = document.querySelector("[data-story-aerial]"); return aerial && getComputedStyle(aerial).visibility === "hidden"; });
}

async function expectStatic(page) {
  await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "static");
  assert.equal(await page.locator("[data-chapter]").count(), 8);
  await noOverflow(page);
}

async function targetY(page, progress) {
  if (progress === 0) return 0;
  await page.waitForFunction(() => Boolean(document.querySelector("[data-story]")?.getAttribute("data-story-scroll-stops")));
  return page.evaluate((target) => {
    const stops = JSON.parse(document.querySelector("[data-story]").getAttribute("data-story-scroll-stops"));
    const index = stops.findIndex((stop, i) => i < stops.length - 1 && target >= stop.progress && target <= stops[i + 1].progress);
    if (index < 0) throw new Error(`No scroll interval for ${target}`);
    const a = stops[index], b = stops[index + 1];
    const start = stops[0].scrollY, end = stops.at(-1).scrollY;
    const measuredY = a.scrollY + (b.scrollY - a.scrollY) * (target - a.progress) / (b.progress - a.progress);
    return Math.round(start) + (measuredY - start) / (end - start) * (Math.round(end) - Math.round(start));
  }, progress);
}

async function seek(page, progress) {
  const top = await targetY(page, progress);
  await page.evaluate((top) => scrollTo({ top, behavior: "instant" }), top);
  await settle(page, progress, progress < .24 || progress > .28);
}

async function animateScroll(page, progress, duration) {
  const target = await targetY(page, progress);
  const samples = await page.evaluate(({ target, duration }) => new Promise((done) => {
    const start = performance.now(), from = scrollY;
    const frames = [];
    const step = (time) => {
      const p = Math.min(1, (time - start) / duration);
      scrollTo({ top: from + (target - from) * p, behavior: "instant" });
      const root = document.querySelector("[data-story]"), host = root.querySelector("[data-desktop-canvas]");
      frames.push({ time: time - start, scrollY, progress: Number(root.getAttribute("data-desktop-progress")), renderedProgress: Number(host?.getAttribute("data-scene-progress")), renderedFrames: Number(host?.getAttribute("data-render-frames")), interlude: Number(root.getAttribute("data-desktop-interlude")) });
      if (p < 1) requestAnimationFrame(step); else done(frames);
    };
    requestAnimationFrame(step);
  }), { target, duration });
  const gaps = samples.slice(1).map((entry, i) => entry.time - samples[i].time).sort((a, b) => a - b);
  report.scrollMotion.push({ targetProgress: progress, requestedDurationMs: duration, actualDurationMs: samples.at(-1)?.time, samples, rafGapMedianMs: gaps[Math.floor(gaps.length / 2)], rafGap95Ms: gaps[Math.floor(gaps.length * .95)], note: "Browser rAF sampling gaps during actual scroll; not a universal GPU FPS claim. Opaque interlude intentionally allows the renderer to sleep while canonical scroll progresses." });
}

async function settle(page, progress, requireGPU = true) {
  await page.evaluate(() => { delete globalThis.__desktopSettle; });
  await page.waitForFunction(({ requireGPU }) => {
    const root = document.querySelector("[data-story]"), host = root?.querySelector("[data-desktop-canvas]");
    if (!root || !host) return false;
    const stops = JSON.parse(root.getAttribute("data-story-scroll-stops"));
    // Match ScrollTrigger's integer bounds and GSAP's six-decimal plain-property clock.
    const start = stops[0].scrollY, end = stops.at(-1).scrollY;
    const clock = Math.round(Math.min(1, Math.max(0, (scrollY - Math.round(start)) / (Math.round(end) - Math.round(start)))) * 1e6) / 1e6;
    const measuredY = start + clock * (end - start);
    let expected = stops[0].progress;
    if (clock > 0) {
      const index = stops.findIndex((stop, i) => i < stops.length - 1 && measuredY >= stop.scrollY && measuredY <= stops[i + 1].scrollY);
      if (index < 0) return false;
      const a = stops[index], b = stops[index + 1];
      expected = a.progress + (b.progress - a.progress) * (measuredY - a.scrollY) / (b.scrollY - a.scrollY);
    }
    const current = Number(root.getAttribute("data-desktop-progress"));
    if (Math.abs(current - expected) > .000002) return false;
    if (requireGPU && (host.getAttribute("data-ready") !== "true" || Math.abs(Number(host.getAttribute("data-scene-progress")) - expected) > .000002)) return false;
    const key = `${current}:${host.getAttribute("data-render-frames")}:${host.getAttribute("data-pointer")}`;
    const probe = globalThis.__desktopSettle;
    if (!probe || probe.key !== key) { globalThis.__desktopSettle = { key, time: performance.now() }; return false; }
    return performance.now() - probe.time >= 200;
  }, { requireGPU, progress }, { timeout: 20000 });
}

async function pointerReset(page) {
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await page.waitForFunction(() => { const host = document.querySelector("[data-desktop-canvas]"); return host?.getAttribute("data-pointer-settled") === "true" && JSON.parse(host.getAttribute("data-pointer") ?? "null")?.every((value) => value === 0); });
}

async function movePointer(page, x, y) {
  const before = await page.locator("[data-desktop-canvas]").getAttribute("data-camera-signature");
  await page.mouse.move(x, y);
  await page.waitForFunction((before) => { const host = document.querySelector("[data-desktop-canvas]"); return host?.getAttribute("data-pointer-settled") === "true" && host.getAttribute("data-camera-signature") !== before; }, before);
}

async function assertIdle(page, reason) {
  await page.evaluate(() => { delete globalThis.__desktopIdle; });
  await page.waitForFunction(() => { const frames = document.querySelector("[data-desktop-canvas]")?.getAttribute("data-render-frames"); if (!frames) return false; const old = globalThis.__desktopIdle; if (!old || old.frames !== frames) { globalThis.__desktopIdle = { frames, time: performance.now() }; return false; } return performance.now() - old.time >= 200; }, null, { timeout: 15000 });
  const before = await page.locator("[data-desktop-canvas]").getAttribute("data-render-frames");
  await page.waitForTimeout(700);
  assert.equal(await page.locator("[data-desktop-canvas]").getAttribute("data-render-frames"), before, `${reason} must not continuously render`);
}

async function sample(page, name, pixels = false) {
  const state = await page.locator("[data-story]").evaluate((root) => {
    const host = root.querySelector("[data-desktop-canvas]");
    const visual = root.querySelector("[data-story-visual]"), rect = visual.getBoundingClientRect();
    return { progress: Number(root.getAttribute("data-desktop-progress")), beat: root.getAttribute("data-desktop-beat"), interlude: Number(root.getAttribute("data-desktop-interlude")), cover: Number(root.getAttribute("data-desktop-cover-progress")), floodAmount: Number(host.getAttribute("data-flood-amount")), worldId: host.getAttribute("data-world-id"), cameraSignature: host.getAttribute("data-camera-signature"), landmarks: JSON.parse(host.getAttribute("data-landmarks") ?? "null"), pointer: JSON.parse(host.getAttribute("data-pointer") ?? "null"), frames: Number(host.getAttribute("data-render-frames")), triangles: Number(host.getAttribute("data-triangles")), drawCalls: Number(host.getAttribute("data-draw-calls")), visual: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, clipPath: getComputedStyle(visual).clipPath }, scrollY };
  });
  assert(state.cameraSignature && state.landmarks, "Rendered camera and landmarks must have telemetry");
  assert.equal(state.worldId, desktopManifest.worldId, "Runtime must render the same authored world as the poster assets");
  assert(state.triangles <= report.budgets.visibleTriangles, `${name} exceeds250000 visible triangles`);
  assert(state.drawCalls <= report.budgets.drawCalls, `${name} exceeds45 draw calls`);
  for (const id of ["Junction_A", "Service_A", "Neighborhood_A", "Field_A"]) assert(Number.isFinite(state.landmarks[id]?.x) && Number.isFinite(state.landmarks[id]?.y));
  if (pixels) {
    const bytes = await page.locator("[data-desktop-canvas] canvas").screenshot();
    const { data, info } = await sharp(bytes).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
    const colors = new Set();
    for (let offset = 0; offset < data.length; offset += 4 * 41) if (data[offset + 3]) colors.add(`${data[offset] >> 3},${data[offset + 1] >> 3},${data[offset + 2] >> 3}`);
    assert(colors.size > 20, `The ${name} scene must contain nonblank rendered geometry`);
    state.pixels = { width: info.width, height: info.height, colors: colors.size, sha256: hash(data) };
  }
  report.samples.push({ name, ...state });
  return state;
}

async function capture(page, name) {
  const path = resolve(evidence, `${name}.png`);
  await page.screenshot({ path, animations: "disabled" });
  report.screenshots.push(path);
  return path;
}

async function assertOpaqueInterlude(page, name) {
  const result = await page.locator("[data-drone-interlude]").evaluate((element) => {
    const rect = element.getBoundingClientRect(), visual = document.querySelector("[data-story-visual]").getBoundingClientRect();
    const css = getComputedStyle(element);
    return { viewport: { width: innerWidth, height: innerHeight }, rect: rect.toJSON(), visual: visual.toJSON(), background: css.backgroundColor, opacity: css.opacity, visibility: css.visibility, clipPath: css.clipPath, text: [...element.querySelectorAll("h2,p,li")].map((node) => ({ text: node.textContent.trim(), rect: node.getBoundingClientRect().toJSON() })) };
  });
  assert.equal(result.background, "rgb(245, 246, 242)", "Reading plane must have its opaque paper background");
  assert.equal(Number(result.opacity), 1, "Reading plane must not be a transparent overlay");
  assert.equal(result.visibility, "visible");
  assert.equal(await page.locator("[data-story-controls]").evaluate((element) => getComputedStyle(element).visibility), "hidden", "Covered scene controls must be removed from keyboard visibility");
  const focusedHiddenLink = await page.locator("[data-story-controls] a").first().evaluate((element) => { element.focus({ preventScroll: true }); return document.activeElement === element; });
  assert.equal(focusedHiddenLink, false, "A hidden chapter control must not accept focus through the opaque reading plane");
  assert(/^inset\(0(?:px|%)?(?:\s|\))/.test(result.clipPath), `The whole reading plane must be revealed: ${result.clipPath}`);
  assert(result.rect.x <= result.visual.x + 1 && result.rect.y <= result.visual.y + 1 && result.rect.right >= result.visual.right - 1 && result.rect.bottom >= result.visual.bottom - 1, "Opaque interlude must cover the complete underlying visual stage");
  assert(result.text.length > 0 && result.text.every((item) => item.rect.x >= 0 && item.rect.right <= result.viewport.width && item.rect.top >= 0 && item.rect.bottom <= result.viewport.height), `Interlude text must fit the viewport: ${JSON.stringify(result.text)}`);
  const png = await page.screenshot();
  const { data, info } = await sharp(png).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  let paper = 0, count = 0;
  for (let y = Math.max(120, Math.ceil(result.rect.top + 20)); y < Math.min(info.height - 80, result.rect.bottom - 20); y += 17) {
    for (let x = 30; x < info.width - 30; x += 17) { const at = (y * info.width + x) * 3; count += 1; if (Math.abs(data[at] - 245) <= 2 && Math.abs(data[at + 1] - 246) <= 2 && Math.abs(data[at + 2] - 242) <= 2) paper += 1; }
  }
  result.paperPixelFraction = paper / count;
  assert(result.paperPixelFraction > .8, `Actual covered frame is not mostly opaque reading paper: ${result.paperPixelFraction}`);
  report.interludeChecks.push({ name, ...result });
}

async function assertBackdropPixels(page, name) {
  const viewport = page.viewportSize();
  const png = await page.screenshot({ clip: { x: 30, y: Math.round(viewport.height * .65), width: viewport.width - 60, height: Math.round(viewport.height * .25) } });
  const { data } = await sharp(png).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const colors = new Set();
  for (let offset = 0; offset < data.length; offset += 3 * 31) colors.add(`${data[offset] >> 3},${data[offset + 1] >> 3},${data[offset + 2] >> 3}`);
  assert(colors.size > 25, `${name} must retain a nonblank visual while assets load`);
  report.samples.push({ name, loadingPixelColors: colors.size, sha256: hash(data) });
}

async function compareMobile(page, name) {
  const currentPath = await capture(page, `v2-${name}`);
  const baselinePath = resolve(baseline, "browser", `${name}.png`);
  const a = await sharp(baselinePath).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const b = await sharp(currentPath).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.deepEqual(b.info, a.info, `V2 ${name} screenshot geometry changed`);
  let absolute = 0, changed = 0;
  for (let i = 0; i < a.data.length; i += 3) { let largest = 0; for (let channel = 0; channel < 3; channel++) { const delta = Math.abs(a.data[i + channel] - b.data[i + channel]); absolute += delta; largest = Math.max(largest, delta); } if (largest > 24) changed += 1; }
  const result = { name, baselinePath, currentPath, baselineSha256: hash(readFileSync(baselinePath)), currentSha256: hash(readFileSync(currentPath)), meanAbsoluteRGBDifference: absolute / a.data.length, significantlyChangedPixelFraction: changed / (a.data.length / 3), baselineBrowser: baselineReport.browser, currentBrowser: browser.version() };
  report.mobileComparisons.push(result);
  assert(result.meanAbsoluteRGBDifference <= 1 && result.significantlyChangedPixelFraction <= .01, `V2 ${name} visual changed: ${JSON.stringify(result)}`);
}

async function noOverflow(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "No horizontal overflow is allowed");
}

async function heroGeometry(page) {
  const value = await page.evaluate(() => {
    const rect = (selector) => document.querySelector(selector).getBoundingClientRect().toJSON();
    const visual = rect("[data-story-visual]");
    const clipPath = getComputedStyle(document.querySelector("[data-story-visual]")).clipPath;
    const lengths = clipPath.match(/^inset\(([^)]+)\)$/)?.[1].split(/\s+/) ?? [];
    const pixels = (token, dimension) => token?.endsWith("%") ? parseFloat(token) * dimension / 100 : parseFloat(token ?? "0");
    const top = pixels(lengths[0], visual.height);
    const bottom = pixels(lengths[2] ?? lengths[0], visual.height);
    const visibleTop = Math.max(0, visual.top + top);
    const visibleBottom = Math.min(innerHeight, visual.bottom - bottom);
    return { scrollY, viewport: { width: innerWidth, height: innerHeight }, header: rect("main[data-landing] header"), hero: rect("#hero"), heading: rect("#landing-title"), cue: rect("[data-story-cue]"), visual, aperture: { clipPath, visibleTop, visibleBottom, heightFraction: Math.max(0, visibleBottom - visibleTop) / innerHeight } };
  });
  assert.equal(value.scrollY, 0, "Initial hero evidence must be at actual document top");
  assert(value.heading.top >= value.header.bottom - 1 && value.heading.bottom <= value.viewport.height, "The hero title must fit below the fixed header");
  assert(value.cue.top >= 0 && value.cue.bottom <= value.viewport.height, "The next-story cue must be visible in the first viewport");
  assert(value.aperture.heightFraction >= (value.viewport.height < 768 ? .38 : .40) && value.aperture.heightFraction <= .55, `The desktop opening scene must occupy roughly the lower half of the viewport: ${JSON.stringify(value.aperture)}`);
  return value;
}

async function auditAccessibility(page, name) {
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  report.accessibility.push({ name, violations: audit.violations, incomplete: audit.incomplete, passes: audit.passes.length });
  assert.deepEqual(audit.violations, [], `${name} accessibility violations require resolution`);
}

async function resources(page) {
  return page.evaluate(() => {
    const navigation = performance.getEntriesByType("navigation")[0];
    const entries = performance.getEntriesByType("resource").map((entry) => ({ path: new URL(entry.name).pathname, transferBytes: entry.transferSize, encodedBytes: entry.encodedBodySize, decodedBytes: entry.decodedBodySize, initiator: entry.initiatorType }));
    return { transferBytes: entries.reduce((sum, entry) => sum + entry.transferBytes, navigation?.transferSize ?? 0), entries, metrics: globalThis.__desktopQA ?? { cls: 0, lcp: null } };
  });
}
