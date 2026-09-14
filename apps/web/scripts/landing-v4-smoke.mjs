import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { cpus, platform } from "node:os";
import { dirname, extname, relative, resolve, sep } from "node:path";
import { gzipSync } from "node:zlib";
import AxeBuilder from "@axe-core/playwright";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const args = process.argv.slice(2);
if (args.includes("--help")) {
  console.log("Usage: node scripts/landing-v4-smoke.mjs [case names]\nFLOODGUARD_V4_URL: existing dev/static URL (default http://127.0.0.1:4310). FLOODGUARD_V4_OUT: optional production export directory; serves it with repository CSP and gzip on an ephemeral port. FLOODGUARD_V4_EVIDENCE: fresh evidence directory. FLOODGUARD_BROWSER_EXECUTABLE: browser override. Does not build, deploy, stop an existing server, submit reports, or request geolocation. Production resource budgets apply only when FLOODGUARD_V4_OUT is supplied.");
  process.exit(0);
}
assert(args.every((arg) => !arg.startsWith("--")), "Unknown option; use --help");
const selected = new Set(args);
const require = createRequire(import.meta.url);
const sharp = require(require.resolve("sharp", { paths: [dirname(require.resolve("next/package.json"))] }));
const evidence = resolve(process.env.FLOODGUARD_V4_EVIDENCE ?? "test-results/landing-v4/browser");
const out = process.env.FLOODGUARD_V4_OUT ? resolve(process.env.FLOODGUARD_V4_OUT) : null;
let base = process.env.FLOODGUARD_V4_URL ?? "http://127.0.0.1:4310";
const chapters = ["place", "flood", "access", "finding"];
const labels = ["Connection", "Flood evidence", "Access", "Finding"];
const hash = (value) => createHash("sha256").update(value).digest("hex");
const sourceFiles = ["src/components/landing/landing-page.tsx", "src/components/landing/landing.module.css", "src/components/landing/landing-nav.client.tsx", "src/components/landing/narrative-experience.client.tsx", "src/components/landing/desktop-narrative-canvas.client.tsx", "src/components/landing/illustrative-finding.tsx", "src/components/landing/scene/drone-scene.ts", "src/lib/landing/sample-desktop-story.ts", "src/lib/landing/illustrative-scenario.ts", "src/lib/landing/copy.en.json", "public/landing/fonts/instrument-sans-latin-variable.woff2", "public/landing/fonts/OFL.txt", "scripts/landing-v4-smoke.mjs"];
const sourceHashes = () => Object.fromEntries(sourceFiles.map((path) => [path, hash(readFileSync(resolve(path)))]));
const report = { result: "STARTED", startedAt: new Date().toISOString(), configuration: { mode: out ? "production-export" : "existing-server", serviceWorkers: "blocked", deviceScaleFactor: 1, syntheticInput: "read-only browser scrolling and UI navigation", fieldPerformanceClaim: false }, device: { platform: platform(), cpu: cpus()[0]?.model }, budgets: { initialBytes: 2 * 1024 * 1024, fullBytes: 3 * 1024 * 1024, cls: .1, triangles: 250000, drawCalls: 45 }, sourceBefore: sourceHashes(), cases: [], captures: [], recordings: [], samples: [], motion: [], accessibility: [], performance: [] };
mkdirSync(evidence, { recursive: true });
const reportPath = resolve(evidence, "landing-v4-smoke.json");
const save = () => writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
save();
let server, browser, currentCaseName;
const rendererChunks = new Set();
try {
  const assetRoot = out ?? resolve("public");
  const scenePath = resolve(assetRoot, "landing/desktop-v4/scene-manifest.json");
  const scene = JSON.parse(readFileSync(scenePath, "utf8"));
  assert.equal(scene.status, "generated_and_browser_rendered_not_geographically_validated");
  for (const source of scene.editableSources) assert.equal(hash(readFileSync(resolve(source.path))), source.sha256, `Scene source no longer matches rendered assets: ${source.path}`);
  for (const asset of scene.assets) {
    const file = resolve(assetRoot, asset.path.replace(/^\/+/, ""));
    assert(file.startsWith(`${assetRoot}${sep}`));
    const bytes = readFileSync(file);
    assert.equal(bytes.length, asset.bytes);
    assert.equal(hash(bytes), asset.sha256);
  }
  const connected = scene.assets.find(({ id }) => id === "connected");
  for (const id of ["flood", "access", "finding"]) {
    const asset = scene.assets.find((entry) => entry.id === id);
    assert.equal(asset.cameraSignature, connected.cameraSignature);
    assert.deepEqual(asset.annotations, connected.annotations);
    assert.equal(asset.floodAmount, 1);
  }
  report.sceneManifest = { path: scenePath, sha256: hash(readFileSync(scenePath)), worldId: scene.worldId, assets: scene.assets.map(({ id, sha256, bytes }) => ({ id, sha256, bytes })) };
  const productsPath = resolve(assetRoot, "landing/product/capture-manifest.json");
  const productManifest = JSON.parse(readFileSync(productsPath, "utf8"));
  for (const asset of productManifest.assets) assert.equal(hash(readFileSync(resolve(assetRoot, asset.file.replace(/^\/+/, "")))), asset.sha256);
  report.productManifest = { path: productsPath, sha256: hash(readFileSync(productsPath)), capturedAt: productManifest.capturedAt, assets: productManifest.assets.map(({ file, qualification, sha256 }) => ({ file, qualification, sha256 })) };
  if (out) {
    for (const entry of readdirSync(resolve(out, "_next/static/chunks"), { withFileTypes: true })) {
      if (entry.isFile() && entry.name.endsWith(".js")) {
        const path = resolve(out, "_next/static/chunks", entry.name);
        if (readFileSync(path, "utf8").includes("data-desktop-canvas")) rendererChunks.add(`/${relative(out, path).split(sep).join("/")}`);
      }
    }
    assert(rendererChunks.size > 0, "A final production renderer must be identified for delayed/failure tests");
    assert.equal(JSON.parse(readFileSync(resolve(out, "deployment-profile.json"), "utf8")).profile, "competition");
    for (const path of sourceFiles.filter((path) => path.startsWith("public/"))) assert.equal(hash(readFileSync(resolve(out, path.slice(7)))), report.sourceBefore[path], `Exported retained asset must match its source: ${path}`);
    const sw = readFileSync(resolve(out, "sw.js"), "utf8");
    report.artifact = { entrySha256: hash(readFileSync(resolve(out, "index.html"))), cacheName: JSON.parse(sw.match(/^const CACHE_NAME = ("[^"]+");/m)?.[1] ?? "null"), offlineManifestSha256: hash(readFileSync(resolve(out, "offline-assets.json"))) };
    assert(report.artifact.cacheName, "Production evidence requires a versioned competition export");
    const config = JSON.parse(readFileSync(resolve("../../vercel.json"), "utf8"));
    const headers = Object.fromEntries(config.headers.find((entry) => entry.source === "/(.*)").headers.map(({ key, value }) => [key, value]));
    report.securityHeaders = headers;
    const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".txt": "text/plain", ".webmanifest": "application/manifest+json" };
    server = createServer((request, response) => {
      const pathname = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
      let file = resolve(out, pathname || "index.html");
      if (file !== out && !file.startsWith(`${out}${sep}`)) return response.writeHead(403).end();
      if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
      if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
      const gzip = /\.(html|js|css|json|svg|txt)$/.test(file) && (request.headers["accept-encoding"] ?? "").split(",").some((part) => {
        const [encoding, ...parameters] = part.trim().split(";");
        return encoding === "gzip" && !parameters.some((value) => /^q\s*=\s*0(?:\.0*)?$/.test(value.trim()));
      });
      response.writeHead(200, { ...headers, "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control": "no-store", ...(gzip ? { "Content-Encoding": "gzip" } : {}) });
      const bytes = readFileSync(file);
      response.end(gzip ? gzipSync(bytes) : bytes);
    });
    await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
    base = `http://127.0.0.1:${server.address().port}`;
  }
  report.base = base;
  browser = await launchFloodGuardBrowser();
  report.browser = browser.version();

  for (const viewport of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }, { width: 1100, height: 700 }, { width: 1440, height: 900 }, { width: 2048, height: 1152 }]) {
    await run(`desktop-${viewport.width}`, viewport, async (page) => {
      await enhanced(page);
      await resetPointer(page);
      await hero(page);
      if (viewport.width === 1366) {
        const camera = await page.locator("[data-desktop-canvas]").getAttribute("data-camera-signature");
        await page.mouse.move(viewport.width - 80, viewport.height - 100);
        await page.waitForFunction(() => JSON.parse(document.querySelector("[data-desktop-canvas]")?.dataset.pointer ?? "[0,0]").some((value) => Math.abs(value) > .02));
        await resetPointer(page);
        assert.equal(await page.locator("[data-desktop-canvas]").getAttribute("data-camera-signature"), camera, "Pointer movement must restore the canonical camera on exit");
      }
      await capture(page, `hero-${viewport.width}`);
      if (viewport.width === 1366) await performanceSample(page, "initial");
      const original = await page.locator("[data-desktop-canvas] canvas").elementHandle();
      const states = [];
      for (const [id, progress] of [["place", .23], ["flood", .46], ["access", .70], ["finding", .90]]) {
        if (viewport.width === 1366) await smoothScroll(page, progress, 1800);
        await seek(page, progress);
        await panel(page, id);
        const state = await sample(page, `${viewport.width}-${id}`);
        states.push(state);
        await capture(page, `${viewport.width}-${id}`);
        assert(await original.evaluate((node) => node.isConnected && node === document.querySelector("[data-desktop-canvas] canvas")), "Chapter changes must preserve the actual canvas node");
        await noOverflow(page);
      }
      for (const state of states.slice(1)) {
        assert.equal(state.cameraSignature, states[0].cameraSignature, "Connection/flood/access/finding hold the same close camera");
        assert.deepEqual(state.landmarks, states[0].landmarks, "The same geographic anchors remain registered");
        assert.equal(state.worldId, states[0].worldId);
      }
      assert.equal(states[0].flood, 0);
      assert.equal(states[1].flood, 1);
      assert.equal(states[1].network, 0);
      assert.equal(states[2].network, 1);
      assert.equal(states[2].baselineReachable, "true");
      assert.equal(states[2].scenarioReachable, "false");
      assert.equal(states[3].flood, 1, "Flood does not disappear when a planning finding is revealed");
      assert.equal(states[3].result, 1);
      await pixelDifference(states[0].pixels, states[1].pixels, .005, "Water must visibly change the same scene");
      await pixelDifference(states[1].pixels, states[2].pixels, .0001, "Assumed link disruption must visibly change the network");
      await finding(page);
      if (viewport.width === 1366) {
        await smoothScroll(page, .23, 2400);
        await seek(page, .23);
        const reversed = await sample(page, "reverse-connection");
        assert.equal(reversed.flood, 0);
        assert.equal(reversed.network, 0);
        assert.equal(reversed.result, 0);
        assert.equal(reversed.cameraSignature, states[0].cameraSignature);
        await products(page);
        await performanceSample(page, "full-story");
        await auditAccessibility(page, "desktop");
      }
    }, { record: viewport.width === 1366 });
  }

  await run("jumps-resize-motion", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    for (const progress of [.90, .23, .70, .46, .90]) await seek(page, progress);
    await panel(page, "finding");
    await motionToggle(page);
    await seek(page, .70);
    await page.setViewportSize({ width: 1024, height: 768 });
    await staticPage(page);
    await page.setViewportSize({ width: 1366, height: 768 });
    await enhanced(page);
    await seek(page, .70);
    await panel(page, "access");
    await page.locator("#workspaces").scrollIntoViewIfNeeded();
    await page.waitForFunction(() => document.querySelector("[data-desktop-canvas]")?.getAttribute("data-scene-active") === "false");
    await idle(page, "Offscreen scene");
  });

  await run("controls-and-focus", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    const menu = page.locator("header details").filter({ has: page.locator("summary", { hasText: "Workspaces" }) });
    await menu.locator("summary").click();
    assert(await menu.evaluate((node) => node.open));
    for (const route of ["/public/", "/command/", "/studio/"]) await menu.locator(`a[href='${route}']`).waitFor({ state: "visible" });
    await page.keyboard.press("Escape");
    assert.equal(await menu.evaluate((node) => node.open), false);
    assert(await menu.locator("summary").evaluate((node) => node === document.activeElement));
    for (const [index, id] of chapters.entries()) {
      const link = page.locator("[data-story-controls]").getByRole("link", { name: labels[index], exact: true });
      await link.focus();
      await focusedVisible(page);
      await page.keyboard.press("Enter");
      await settle(page);
      assert.equal(new URL(page.url()).hash, `#${id}`);
      (report.focusNavigation ??= []).push(await page.evaluate(() => ({ hash: location.hash, html: document.activeElement?.outerHTML?.slice(0, 350), rect: document.activeElement?.getBoundingClientRect().toJSON() })));
      // Native nonfocusable hash targets reset activeElement to body, then define the next Tab origin.
      if (await page.evaluate(() => document.activeElement === document.body)) await page.keyboard.press("Tab");
      await focusedVisible(page);
    }
    await page.locator("#questions").scrollIntoViewIfNeeded();
    const faq = page.locator("#questions details").first();
    await faq.locator("summary").focus();
    await page.keyboard.press("Space");
    assert(await faq.evaluate((node) => node.open));
    await capture(page, "faq-open");
    await faq.locator("summary").click();
    assert.equal(await faq.evaluate((node) => node.open), false);
    await page.mouse.move(100, 200);
    await page.waitForTimeout(1400);
    const idleColor = await page.evaluate(() => getComputedStyle(document.documentElement).scrollbarColor);
    await page.mouse.wheel(0, -150);
    await page.waitForFunction(() => document.documentElement.dataset.landingScrolling === "true");
    await page.waitForTimeout(320);
    assert.notEqual(await page.evaluate(() => getComputedStyle(document.documentElement).scrollbarColor), idleColor);
    await page.waitForTimeout(1400);
    assert.equal(await page.evaluate(() => document.documentElement.dataset.landingScrolling), "false");
  });

  for (const id of chapters) await run(`deep-${id}`, { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    await settle(page);
    assert.equal(new URL(page.url()).hash, `#${id}`);
    assert.equal(await page.locator("[data-story]").getAttribute("data-active-chapter-id"), id);
    await panel(page, id);
    await capture(page, `deep-${id}`);
  }, { hash: `#${id}` });

  for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 768 }, { width: 1024, height: 768 }, { width: 1264, height: 620 }]) {
    await run(`static-${viewport.width}`, viewport, async (page) => {
      await staticPage(page);
      await capture(page, `static-${viewport.width}-hero`);
      for (const id of chapters) {
        await page.locator(`#${id}`).scrollIntoViewIfNeeded();
        await decodeImages(page.locator(`#${id}`));
        await noOverflow(page);
        await capture(page, `static-${viewport.width}-${id}`);
      }
      await products(page);
      if (viewport.width <= 390) await mobileAvailability(page);
      if (viewport.width === 390) await auditAccessibility(page, "mobile");
    });
  }
  await run("reduced-motion", { width: 1366, height: 768 }, async (page) => { await staticPage(page); await products(page); await capture(page, "reduced-motion"); }, { context: { reducedMotion: "reduce" } });
  await run("no-javascript", { width: 1366, height: 768 }, async (page) => { await staticPage(page); await products(page); await capture(page, "no-javascript"); }, { context: { javaScriptEnabled: false } });
  await run("webgl-unavailable", { width: 1366, height: 768 }, async (page) => { await staticPage(page); await products(page); await capture(page, "webgl-unavailable"); }, { prepare: async (page) => page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type, ...args) { return /^(webgl2?|experimental-webgl)$/.test(type) ? null : original.call(this, type, ...args); };
  }) });
  await run("save-data", { width: 1366, height: 768 }, async (page) => { await staticPage(page); }, { prepare: async (page) => page.addInitScript(() => Object.defineProperty(navigator, "connection", { configurable: true, value: { saveData: true, addEventListener() {}, removeEventListener() {} } })) });
  await run("offline-policy", { width: 1366, height: 768 }, async (page) => { await staticPage(page); }, { hash: "#finding", prepare: async (page) => page.addInitScript(() => Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false })) });
  for (const id of ["access", "finding"]) {
    let release, intercepted = 0;
    const gate = new Promise((done) => { release = done; });
    await run(`delayed-${id}`, { width: 1366, height: 768 }, async (page) => {
      await page.waitForFunction(() => document.querySelector("[data-story]")?.dataset.renderMode === "enhanced");
      await page.waitForTimeout(1000);
      assert(intercepted > 0, "The actual optional renderer request must be held");
      assert.equal(await page.locator("[data-story]").getAttribute("data-annotation-ready"), "false");
      for (const key of ["home", "affected-link", "facility"]) assert.equal(await visualOpacity(page.locator(`[data-scene-annotation='${key}']`)), 0, "Unprojected labels must stay hidden");
      await capture(page, `delayed-${id}-before-renderer`);
      release();
      await enhanced(page);
      await seek(page, id === "access" ? .70 : .90);
      await panel(page, id);
      await capture(page, `delayed-${id}-ready`);
    }, { hash: `#${id}`, waitUntil: "domcontentloaded", prepare: async (page) => page.route(isRendererChunk, async (route) => { intercepted++; await gate; await route.continue().catch(() => {}); }), cleanup: release });
  }
  const injectedChunkFailures = [];
  let releaseHashRenderer, heldHashRenderer = 0;
  const hashGate = new Promise((done) => { releaseHashRenderer = done; });
  await run("hash-during-pending-restoration", { width: 1366, height: 768 }, async (page) => {
    await page.waitForFunction(() => document.querySelector("[data-story]")?.dataset.storyScrollStops);
    const deadline = Date.now() + 20000;
    while (!heldHashRenderer && Date.now() < deadline) await page.waitForTimeout(50);
    assert(heldHashRenderer > 0);
    await page.evaluate(() => { location.hash = "#place"; });
    releaseHashRenderer();
    await enhanced(page);
    await settle(page);
    assert.equal(new URL(page.url()).hash, "#place");
    assert.equal(await page.locator("[data-story]").getAttribute("data-active-chapter-id"), "place", "A new native hash wins over retained initial-fragment restoration");
    await capture(page, "hash-during-pending-restoration");
  }, { hash: "#finding", waitUntil: "domcontentloaded", prepare: async (page) => page.route(isRendererChunk, async (route) => { heldHashRenderer++; await hashGate; await route.continue().catch(() => {}); }), cleanup: releaseHashRenderer });

  await run("renderer-load-failure", { width: 1366, height: 768 }, async (page) => {
    await staticPage(page);
    assert(injectedChunkFailures.length > 0);
    assert.equal(await page.locator("[data-story]").getAttribute("data-render-failure"), "renderer-load-failed");
    await products(page);
    await capture(page, "renderer-load-failure-static");
  }, { hash: "#access", injectedChunkFailures, prepare: async (page) => page.route(isRendererChunk, (route) => { injectedChunkFailures.push(route.request().url()); return route.abort("failed"); }) });
  const injectedImageFailures = [];
  await run("poster-image-failure", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    assert(injectedImageFailures.length > 0);
    await seek(page, .70);
    await panel(page, "access");
    await sample(page, "poster-image-failure");
    await capture(page, "poster-image-failure-ready");
  }, { injectedImageFailures, prepare: async (page) => page.route("**/landing/desktop-v4/far.webp", (route) => { injectedImageFailures.push(route.request().url()); return route.abort("failed"); }) });
  await run("mounted-context-loss", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    await seek(page, .70);
    await page.locator("[data-desktop-canvas] canvas").evaluate((canvas) => {
      const extension = canvas.getContext("webgl2")?.getExtension("WEBGL_lose_context");
      if (!extension) throw new Error("Context-loss injection is unavailable on this driver");
      extension.loseContext();
    });
    await staticPage(page);
    assert.equal(await page.locator("[data-story]").getAttribute("data-render-failure"), "desktop-context-lost");
    await products(page);
    await capture(page, "context-loss-static");
  }, { expectedContextLoss: true });
  await run("hidden-document-idle", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    await seek(page, .70);
    const cover = await page.context().newPage();
    await cover.bringToFront();
    const nativeHidden = await page.evaluate(() => document.visibilityState === "hidden");
    report.visibilityReview = { nativeHidden, mode: nativeHidden ? "native tab visibility" : "synthetic document visibility policy; native background scheduling not asserted" };
    if (!nativeHidden) await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
      Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    try {
      await page.waitForFunction(() => document.querySelector("[data-desktop-canvas]")?.dataset.sceneActive === "false");
      await idle(page, "Hidden document policy");
    } finally {
      await cover.close();
      await page.bringToFront();
      if (!nativeHidden) await page.evaluate(() => { delete document.visibilityState; delete document.hidden; document.dispatchEvent(new Event("visibilitychange")); });
    }
    await enhanced(page);
    await seek(page, .70);
    await panel(page, "access");
  });
  await run("route-lifecycle", { width: 1366, height: 768 }, async (page, phase) => {
    const cdp = await page.context().newCDPSession(page);
    const navigation = async (step) => { (report.navigationHistory ??= []).push({ step, url: page.url(), history: await cdp.send("Page.getNavigationHistory") }); };
    const dwellTimes = [0, 60, 200, 0, 60, 200, 0, 200];
    const lifecycle = { cycles: dwellTimes.length, activeCanvasVisits: 0, planningVisits: 0, studioVisits: 0, dwellTimes, routing: "Actual native workspace anchors and history; document/BFCache lifecycle, not an assertion of React unmount on every departure." };
    for (const dwell of dwellTimes) {
      await page.locator("[data-story][data-render-mode='enhanced']").waitFor();
      await seek(page, .70);
      phase.current = "public-transition";
      await phase.navigate(async () => { await page.locator("#workspaces a[href='/public/']").click(); await page.locator("main.public-page").waitFor(); });
      assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
      await page.locator("main.public-page .leaflet-overlay-pane canvas").first().waitFor({ state: "visible" });
      lifecycle.activeCanvasVisits++;
      if (dwell) await page.waitForTimeout(dwell);
      await phase.navigate(async () => { await page.goBack({ waitUntil: "domcontentloaded" }); await page.locator("main[data-landing]").waitFor(); });
      phase.current = "planning-transition";
      await phase.navigate(async () => { await page.locator("#workspaces a[href='/command/']").click(); await page.locator(".command-page").waitFor(); });
      lifecycle.planningVisits++;
      phase.current = "studio-transition";
      await phase.navigate(async () => { await page.locator("nav[aria-label='Product surfaces'] a[href='/studio/']").click(); await page.locator(".studio-page").waitFor(); });
      lifecycle.studioVisits++;
      await navigation("studio");
      phase.current = "planning-transition";
      await phase.navigate(async () => { await page.goBack({ waitUntil: "domcontentloaded" }); await page.locator(".command-page").waitFor(); });
      await navigation("back-planning");
      await phase.navigate(async () => { await page.goBack({ waitUntil: "domcontentloaded" }); await page.locator("main[data-landing]").waitFor(); });
      await navigation("back-landing-requested");
      await page.locator("main[data-landing]").waitFor();
      phase.current = "landing";
    }
    await seek(page, .70);
    await idle(page, "Repeated route entry");
    report.routeLifecycle = lifecycle;
    await capture(page, "route-lifecycle-final");
  });

  let holdHistoryScripts = false, heldHistoryScripts = 0, releaseHistory = () => {}, historyGate;
  await run("native-history-before-hydration", { width: 1366, height: 768 }, async (page, phase) => {
    phase.current = "planning-transition";
    await phase.navigate(async () => { await page.locator("#workspaces a[href='/command/']").click(); await page.locator(".command-page").waitFor(); });
    phase.current = "studio-transition";
    await phase.navigate(async () => { await page.locator("nav[aria-label='Product surfaces'] a[href='/studio/']").click(); await page.locator(".studio-page").waitFor(); });
    const studioDocument = await page.evaluate(() => globalThis.__v4history.documentId);
    historyGate = new Promise((done) => { releaseHistory = done; });
    holdHistoryScripts = true;
    phase.current = "planning-transition";
    await phase.navigate(async () => { await page.evaluate(() => history.back()); await page.locator(".command-page").waitFor(); });
    const restored = await page.evaluate(() => ({ url: location.href, ...globalThis.__v4history }));
    assert.notEqual(restored.documentId, studioDocument);
    assert.equal(restored.popstateListeners, 0, "The second Back must exercise the unhydrated Planning document");
    await phase.navigate(async () => { await page.evaluate(() => history.back()); await page.waitForURL((url) => url.pathname === "/", { waitUntil: "commit" }); await page.locator("main[data-landing]").waitFor(); });
    assert(heldHistoryScripts > 0, "Actual scripts must be held, not a timing-only approximation");
    report.heldHistory = { heldScriptRequests: heldHistoryScripts, restored, landing: await page.evaluate(() => ({ url: location.href, ...globalThis.__v4history })) };
    assert.notEqual(report.heldHistory.landing.documentId, restored.documentId, "Native Back must leave the unhydrated Planning document");
    holdHistoryScripts = false;
    releaseHistory();
    phase.current = "landing";
    await page.locator("[data-story][data-render-mode='enhanced']").waitFor();
    await seek(page, .70);
    await panel(page, "access");
    await capture(page, "native-history-before-hydration-restored");
  }, { prepare: async (page) => {
    await page.addInitScript(() => {
      globalThis.__v4history = { documentId: crypto.randomUUID(), popstateListeners: 0 };
      const original = window.addEventListener;
      window.addEventListener = function (type, ...args) { if (type === "popstate") globalThis.__v4history.popstateListeners++; return original.call(this, type, ...args); };
    });
    await page.route("**/_next/**/*.js", async (route) => { if (holdHistoryScripts) { heldHistoryScripts++; await historyGate; } await route.continue().catch(() => {}); });
  }, cleanup: () => { holdHistoryScripts = false; releaseHistory(); } });

  if (selected.has("motion-review")) await run("motion-review", { width: 1366, height: 768 }, async (page) => {
    await enhanced(page);
    await resetPointer(page);
    report.motionRenderer = await page.locator("[data-desktop-canvas] canvas").evaluate((canvas) => {
      const gl = canvas.getContext("webgl2"), extension = gl.getExtension("WEBGL_debug_renderer_info");
      return { renderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), version: gl.getParameter(gl.VERSION) };
    });
    await capture(page, "motion-review-hero");
    for (const [id, progress] of [["place", .23], ["flood", .46], ["access", .70], ["finding", .90], ["access-reverse", .70], ["flood-reverse", .46], ["place-reverse", .23]]) {
      await smoothScroll(page, progress, 2200);
      await settle(page);
      await capture(page, `motion-review-${id}`);
      await page.waitForTimeout(350);
    }
  }, { record: true });

  for (const viewport of [{ width: 1366, height: 768 }, { width: 390, height: 844 }]) {
    const name = `manual-contrast-${viewport.width}`;
    if (!selected.has(name)) continue;
    await run(name, viewport, async (page) => {
      if (viewport.width === 1366) await enhanced(page); else await staticPage(page);
      await contrastEvidence(page, `${viewport.width}-hero`, "#hero");
      for (const [id, progress] of [["place", .23], ["access", .70], ["finding", .90]]) {
        if (viewport.width === 1366) {
          await seek(page, progress);
          await contrastEvidence(page, `${viewport.width}-${id}`, `[data-story-panel='${id}'], [data-scene-annotation], [data-story-controls], [data-pwa-availability], [data-desktop-overlay] > p`);
        } else {
          await page.locator(`#${id}`).evaluate((node) => node.scrollIntoView({ block: "start", behavior: "instant" }));
          await decodeImages(page.locator(`#${id}`));
          await contrastEvidence(page, `${viewport.width}-${id}`, `#${id}, [data-pwa-availability]`);
        }
      }
      for (const [label, selector] of [["case-heading", "#case"], ["case-caption", "#case figure figcaption"], ["questions", "#questions"]]) {
        await page.locator(selector).evaluate((node) => scrollTo({ top: node.getBoundingClientRect().top + scrollY - 130, behavior: "instant" }));
        await contrastEvidence(page, `${viewport.width}-${label}`, "#case, #questions");
      }
    });
  }

  report.sourceAfter = sourceHashes();
  assert.deepEqual(report.sourceAfter, report.sourceBefore, "Application sources changed during QA; this is not a frozen-artifact result");
  assert(report.cases.length > 0, "No matching V4 QA cases were selected");
  report.result = report.cases.every((entry) => entry.result === "PASS") ? "PASS" : "FAIL";
} catch (error) { report.result = "FAIL"; report.failure = error.stack ?? error.message; }
finally {
  await browser?.close();
  if (server) await new Promise((done) => server.close(done));
  report.completedAt = new Date().toISOString();
  save();
}
console.log(JSON.stringify({ result: report.result, cases: report.cases.map(({ name, result, error }) => ({ name, result, error })), reportPath }, null, 2));
if (report.result !== "PASS") process.exitCode = 1;

async function run(name, viewport, check, options = {}) {
  if (selected.size && !selected.has(name)) return;
  currentCaseName = name;
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, serviceWorkers: "block", ...(options.record ? { recordVideo: { dir: resolve(evidence, "recordings"), size: viewport } } : {}), ...options.context });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  const errors = [], consoleErrors = [], writes = [], external = [], badResponses = [], failedRequests = [], publicRequests = [], documentRequests = [];
  const phase = { current: "landing" };
  let navigationEpoch = 0, documentEpoch = 0;
  page.on("framenavigated", (frame) => { if (frame === page.mainFrame()) documentEpoch++; });
  const navigationIntents = [];
  phase.navigate = async (action) => {
    const source = await page.evaluate(() => ({ id: globalThis.__v4documentId, url: location.href }));
    const intent = { epoch: navigationEpoch, documentEpoch, source, beganAt: Date.now() };
    navigationIntents.push(intent);
    await action();
    intent.destination = await page.evaluate(() => ({ id: globalThis.__v4documentId, url: location.href }));
    intent.destinationDocumentEpoch = documentEpoch;
    intent.completedAt = Date.now();
    intent.documentChanged = Boolean(source.id && intent.destination.id && source.id !== intent.destination.id);
  };
  const requestDocuments = new WeakMap();
  const approvedBasemaps = new Set(["https://tile.openstreetmap.org", "https://services.arcgisonline.com"]);
  const publicBasemapRequests = new WeakSet();
  page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("request", (request) => {
    if (request.isNavigationRequest() && request.frame() === page.mainFrame()) documentRequests.push({ url: request.url(), recordedAt: new Date().toISOString(), epoch: ++navigationEpoch });
    requestDocuments.set(request, { epoch: navigationEpoch, documentEpoch, document: request.frame().url() });
    if (!/^(GET|HEAD|OPTIONS)$/.test(request.method())) writes.push(`${request.method()} ${request.url()}`);
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== new URL(base).origin) {
      if (phase.current !== "landing" && approvedBasemaps.has(new URL(request.url()).origin)) { publicBasemapRequests.add(request); publicRequests.push({ url: request.url(), phase: phase.current }); }
      else external.push(request.url());
    }
  });
  page.on("response", (response) => { if (response.status() >= 400) badResponses.push({ url: response.url(), status: response.status(), optionalPublicBasemap: publicBasemapRequests.has(response.request()) }); });
  page.on("requestfailed", (request) => {
    const owner = requestDocuments.get(request), error = request.failure()?.errorText;
    failedRequests.push({ url: request.url(), error, method: request.method(), navigationRequest: request.isNavigationRequest(), failedAt: Date.now(), optionalPublicBasemap: publicBasemapRequests.has(request), owner, failedAtNavigationEpoch: navigationEpoch, failedAtDocumentEpoch: documentEpoch });
  });
  try {
    await page.addInitScript(() => {
      globalThis.__v4documentId = crypto.randomUUID();
      performance.setResourceTimingBufferSize(5000);
      globalThis.__v4qa = { geolocation: 0, csp: [], contextEvents: [], shifts: [], lcp: [], longTasks: [] };
      document.addEventListener("securitypolicyviolation", (event) => globalThis.__v4qa.csp.push({ directive: event.violatedDirective, blockedURI: event.blockedURI }));
      // Ignore the deliberately detached capability-probe context; record mounted scene failures.
      for (const type of ["webglcontextlost", "webglcontextrestored"]) document.addEventListener(type, (event) => { if (event.target.closest?.("[data-desktop-canvas]")) globalThis.__v4qa.contextEvents.push({ type, time: performance.now() }); }, true);
      for (const key of ["getCurrentPosition", "watchPosition"]) Object.defineProperty(navigator.geolocation, key, { configurable: true, value: () => { globalThis.__v4qa.geolocation++; throw new Error("Landing QA must not request geolocation"); } });
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) if (!entry.hadRecentInput) globalThis.__v4qa.shifts.push({ value: entry.value, time: entry.startTime, sources: entry.sources.map((source) => ({ node: source.node?.outerHTML?.slice(0, 250), previousRect: source.previousRect.toJSON(), currentRect: source.currentRect.toJSON() })) }); }).observe({ type: "layout-shift", buffered: true });
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) globalThis.__v4qa.lcp.push({ time: entry.startTime, size: entry.size, url: entry.url }); }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((list) => { for (const entry of list.getEntries()) globalThis.__v4qa.longTasks.push({ time: entry.startTime, duration: entry.duration }); }).observe({ type: "longtask", buffered: true });
    });
    await options.prepare?.(page);
    await page.goto(`${base}/${options.hash ?? ""}`, { waitUntil: options.waitUntil ?? "networkidle" });
    await page.locator("main[data-landing]").waitFor();
    await page.evaluate(() => document.fonts.ready);
    await semantics(page);
    await check(page, phase);
    // Requests can start after outgoing navigation begins but before its document commits. Match the committed source document and confirmed departure interval.
    for (const entry of failedRequests) {
      const intent = navigationIntents.find((item) => item.documentChanged && item.documentEpoch === entry.owner?.documentEpoch && item.source.url === entry.owner?.document && entry.failedAt >= item.beganAt && entry.failedAt <= item.completedAt);
      entry.navigationCancelled = ["route-lifecycle", "native-history-before-hydration"].includes(name) && entry.error === "net::ERR_ABORTED" && entry.method === "GET" && !entry.navigationRequest && new URL(entry.url).origin === new URL(base).origin && Boolean(intent);
      if (entry.navigationCancelled) entry.departureProof = intent;
    }
    const safety = await page.evaluate(() => globalThis.__v4qa ?? { geolocation: 0, csp: [], contextEvents: [] });
    assert.equal(safety.geolocation, 0);
    assert.deepEqual(safety.csp, []);
    if (options.expectedContextLoss) assert.deepEqual(safety.contextEvents.map((entry) => entry.type), ["webglcontextlost"]);
    else assert.deepEqual(safety.contextEvents, []);
    assert.deepEqual(errors, []);
    const expectedAssetError = (message) => (options.injectedChunkFailures?.length && /ChunkLoadError|Failed to load chunk/.test(message)) || ((options.injectedChunkFailures?.length || options.injectedImageFailures?.length) && /Failed to load resource: net::ERR_FAILED/.test(message));
    assert.deepEqual(consoleErrors.filter((message) => !expectedAssetError(message)), []);
    assert.deepEqual(writes, []);
    assert.deepEqual(external, []);
    assert.deepEqual(badResponses.filter((entry) => !entry.optionalPublicBasemap), []);
    const unexpectedFailures = failedRequests.filter((entry) => !entry.optionalPublicBasemap && !entry.navigationCancelled && !options.injectedChunkFailures?.includes(entry.url) && !options.injectedImageFailures?.includes(entry.url) && !(name === "no-javascript" && /csp/i.test(entry.error ?? "") && /\/_next\/.*\.js$/.test(entry.url)));
    assert.deepEqual(unexpectedFailures, [], "Unexpected asset failures require investigation");
    report.cases.push({ name, result: "PASS", viewport, errors, consoleErrors, writes, external, publicRequests, documentRequests, navigationIntents, badResponses, failedRequests, injectedChunkFailures: options.injectedChunkFailures, injectedImageFailures: options.injectedImageFailures, expectedContextLoss: options.expectedContextLoss, safety });
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({ url: location.href, scrollY, focused: { html: document.activeElement?.outerHTML?.slice(0, 400), rect: document.activeElement?.getBoundingClientRect().toJSON() }, root: document.querySelector("[data-story]")?.dataset, canvas: document.querySelector("[data-desktop-canvas]")?.dataset, geometry: Object.fromEntries(["main[data-landing] > header", "[data-story-stage]", "[data-story-content]", "[data-story-end]", "[data-story-panel='finding']"].map((selector) => [selector, document.querySelector(selector)?.getBoundingClientRect().toJSON()])), safety: globalThis.__v4qa })).catch(() => null);
    await capture(page, `${name}-failure`).catch(() => {});
    report.cases.push({ name, result: "FAIL", error: error.stack ?? error.message, viewport, diagnostic, errors, consoleErrors, writes, external, publicRequests, documentRequests, navigationIntents, badResponses, failedRequests });
  } finally {
    await options.cleanup?.();
    const video = page.video();
    await context.close();
    if (video) report.recordings.push({ case: name, path: await video.path() });
    save();
    console.log(`landing V4 ${name}: ${report.cases.at(-1)?.result}`);
  }
}

function isRendererChunk(url) {
  return out ? rendererChunks.has(url.pathname) : /\/_next\/static\/chunks\/.*desktop-narrative-canvas.*\.js$/.test(url.pathname);
}

async function semantics(page) {
  assert.deepEqual(await page.locator("[data-story-chapter]").evaluateAll((nodes) => nodes.map((node) => node.id)), chapters);
  for (const id of ["method", "workspaces", "case", "questions"]) assert.equal(await page.locator(`#${id}`).count(), 1);
  for (const route of ["/public/", "/command/", "/studio/"]) assert(await page.locator(`a[href='${route}']`).count() > 0);
  const text = await page.locator("main[data-landing]").innerText();
  assert.match(text, /historical/i);
  assert.match(text, /not (?:a )?live|not current conditions/i);
  assert.match(text, /illustrative|synthetic/i);
  await noOverflow(page);
}
async function enhanced(page) {
  await page.locator("[data-story][data-render-mode='enhanced']").waitFor();
  await page.locator("[data-desktop-canvas][data-ready='true']").waitFor();
  assert.equal(await page.locator("[data-story] canvas").count(), 1);
}
async function staticPage(page) {
  await page.locator("[data-story][data-render-mode='static']").waitFor();
  assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
  await semantics(page);
}
async function hero(page) {
  assert.equal(await page.evaluate(() => scrollY), 0);
  const h1 = page.locator("h1");
  assert.equal(await h1.count(), 1);
  await h1.waitFor({ state: "visible" });
  const box = await h1.boundingBox(), header = await page.locator("main[data-landing] > header").boundingBox();
  assert(box.y >= header.y + header.height, "Hero headline must clear the floating header");
  assert(box.y + box.height <= await page.evaluate(() => innerHeight));
  await page.getByRole("link", { name: "Explore the planning demo", exact: true }).first().waitFor({ state: "visible" });
  await page.locator("#hero").getByRole("link", { name: /^(See )?how it works$/i }).waitFor({ state: "visible" });
}
async function noOverflow(page) {
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "No horizontal document overflow");
}
async function targetY(page, progress) {
  if (progress === 0) return 0;
  await page.waitForFunction(() => document.querySelector("[data-story]")?.dataset.storyScrollStops);
  return page.evaluate((progress) => {
    const stops = JSON.parse(document.querySelector("[data-story]").dataset.storyScrollStops);
    const index = stops.findIndex((a, i) => i < stops.length - 1 && progress >= a.progress && progress <= stops[i + 1].progress);
    if (index < 0) throw new Error("Requested progress is outside measured story");
    const a = stops[index], b = stops[index + 1], start = stops[0].scrollY, end = stops.at(-1).scrollY;
    const y = a.scrollY + (b.scrollY - a.scrollY) * (progress - a.progress) / (b.progress - a.progress);
    return Math.round(start) + (y - start) / (end - start) * (Math.round(end) - Math.round(start));
  }, progress);
}
async function seek(page, progress) {
  await page.evaluate((top) => scrollTo({ top, behavior: "instant" }), await targetY(page, progress));
  await resetPointer(page);
  await settle(page);
}
async function settle(page) {
  await page.evaluate(() => { delete globalThis.__v4settle; });
  await page.waitForFunction(() => {
    const root = document.querySelector("[data-story]"), host = root?.querySelector("[data-desktop-canvas]");
    if (!root?.dataset.storyScrollStops || !host) return false;
    const stops = JSON.parse(root.dataset.storyScrollStops), start = stops[0].scrollY, end = stops.at(-1).scrollY;
    // Match integer ScrollTrigger bounds and the six-decimal GSAP plain-property clock.
    const clock = Math.round(Math.min(1, Math.max(0, (scrollY - Math.round(start)) / (Math.round(end) - Math.round(start)))) * 1e6) / 1e6;
    const y = start + clock * (end - start);
    const index = stops.findIndex((a, i) => i < stops.length - 1 && y >= a.scrollY && y <= stops[i + 1].scrollY);
    const a = stops[index], b = stops[index + 1];
    const expected = clock === 0 ? 0 : clock === 1 ? 1 : a ? a.progress + (b.progress - a.progress) * (y - a.scrollY) / (b.scrollY - a.scrollY) : NaN;
    if (!Number.isFinite(expected) || Math.abs(Number(root.dataset.desktopProgress) - expected) > .000002 || Math.abs(Number(host.dataset.sceneProgress) - expected) > .000002 || host.dataset.ready !== "true") return false;
    const key = `${root.dataset.desktopProgress}:${host.dataset.renderFrames}:${host.dataset.pointer}`;
    const old = globalThis.__v4settle;
    if (!old || old.key !== key) { globalThis.__v4settle = { key, time: performance.now() }; return false; }
    return performance.now() - old.time >= 200;
  }, null, { timeout: 20000 });
}
async function resetPointer(page) {
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await page.waitForFunction(() => { const node = document.querySelector("[data-desktop-canvas]"); return node?.dataset.pointerSettled === "true" && JSON.parse(node.dataset.pointer ?? "null")?.every((value) => value === 0); });
}
async function panel(page, id) {
  assert.equal(await page.locator("[data-story]").getAttribute("data-active-chapter-id"), id);
  const active = page.locator(`[data-story-panel='${id}']`);
  await active.waitFor({ state: "visible" });
  for (const other of chapters.filter((value) => value !== id)) assert.equal(await page.locator(`[data-story-panel='${other}']`).isVisible(), false);
  const box = await active.boundingBox(), header = await page.locator("main[data-landing] > header").boundingBox();
  assert(box.y >= header.y + header.height, `The ${id} reading panel must clear the header`);
  assert(box.y + box.height <= await page.evaluate(() => innerHeight), `The ${id} reading panel must fit the viewport`);
  const availability = page.locator("[data-pwa-availability] > summary");
  if (await availability.count() && await availability.isVisible()) {
    const status = await availability.boundingBox(), controls = await page.locator("[data-story-controls]").boundingBox();
    const host = page.locator("[data-pwa-availability]");
    assert.equal(await host.evaluate((node) => getComputedStyle(node).position), "static", "Desktop availability must remain in document flow");
    assert(status.y >= await page.evaluate(() => innerHeight), "Desktop availability must not float over the scene or reading content");
    const intersection = Math.max(0, Math.min(status.x + status.width, controls.x + controls.width) - Math.max(status.x, controls.x)) * Math.max(0, Math.min(status.y + status.height, controls.y + controls.height) - Math.max(status.y, controls.y));
    assert.equal(intersection, 0, "The production availability status must not overlap chapter controls");
  }
  if (["access", "finding"].includes(id)) {
    assert.match(await active.innerText(), /assum|illustrative|synthetic/i);
    for (const key of ["home", "affected-link", "facility"]) {
      const expected = key === "affected-link" ? Number(await page.locator("[data-story]").getAttribute("data-network-progress")) : 1;
      assert(Math.abs(await visualOpacity(page.locator(`[data-scene-annotation='${key}']`)) - expected) <= .00002, "Annotation opacity must match the sampled state, including partial native-anchor entry");
    }
  }
}
async function sample(page, name) {
  const state = await page.locator("[data-desktop-canvas]").evaluate((node) => ({ progress: Number(node.dataset.sceneProgress), cameraSignature: node.dataset.cameraSignature, landmarks: JSON.parse(node.dataset.landmarks), annotations: JSON.parse(node.dataset.annotations), worldId: node.dataset.worldId, flood: Number(node.dataset.floodAmount), network: Number(node.dataset.networkAmount), result: Number(node.dataset.resultAmount), baselineReachable: node.dataset.baselineReachable, scenarioReachable: node.dataset.scenarioReachable, triangles: Number(node.dataset.triangles), draws: Number(node.dataset.drawCalls) }));
  assert(state.cameraSignature && state.worldId);
  assert(state.triangles > 0 && state.triangles <= report.budgets.triangles);
  assert(state.draws > 0 && state.draws <= report.budgets.drawCalls);
  if (!report.renderer) report.renderer = await page.locator("[data-desktop-canvas] canvas").evaluate((canvas) => {
    const gl = canvas.getContext("webgl2"), extension = gl?.getExtension("WEBGL_debug_renderer_info");
    return { vendor: extension ? gl.getParameter(extension.UNMASKED_VENDOR_WEBGL) : gl?.getParameter(gl.VENDOR), renderer: extension ? gl.getParameter(extension.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER), version: gl?.getParameter(gl.VERSION) };
  });
  const path = resolve(evidence, `${name}-canvas.png`);
  // Element screenshots include higher HTML layers; isolate scene pixels for material comparisons.
  await page.locator("[data-desktop-canvas] canvas").screenshot({ path, style: "[data-desktop-overlay], main[data-landing] > header, [data-story-controls], [data-motion-controls] { visibility: hidden !important; }" });
  const stats = await sharp(path).stats();
  assert(stats.channels.slice(0, 3).some((channel) => channel.stdev > 8), "Canvas must contain nonblank scene pixels");
  const value = { name, ...state, pixels: path, pixelsSha256: hash(readFileSync(path)) };
  report.samples.push(value);
  return value;
}
async function pixelDifference(a, b, minimumFraction, message) {
  const left = await sharp(a).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const right = await sharp(b).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.deepEqual(left.info, right.info);
  let changed = 0;
  for (let i = 0; i < left.data.length; i += 3) if (Math.max(...[0, 1, 2].map((channel) => Math.abs(left.data[i + channel] - right.data[i + channel]))) > 24) changed++;
  const fraction = changed / (left.data.length / 3);
  report.samples.push({ name: "pixel-comparison", a, b, fraction, minimumFraction });
  assert(fraction >= minimumFraction, `${message}; changed fraction ${fraction}`);
}
async function finding(page) {
  const section = page.locator("[data-story-panel='finding']");
  for (const field of ["finding", "reason", "uncertainty", "next-step"]) {
    const node = section.locator(`[data-finding-field='${field}']`);
    await node.waitFor({ state: "visible" });
    assert((await node.innerText()).trim().length > 12);
  }
}
async function products(page) {
  await page.locator("#workspaces").scrollIntoViewIfNeeded();
  for (const [file, id] of [["public-preparedness", "public"], ["planning-priorities", "command"], ["studio-evidence", "studio"]]) {
    const image = page.locator(`img[src*='${file}']`);
    assert.equal(await image.count(), 1);
    await image.scrollIntoViewIfNeeded();
    await image.evaluate(async (node) => { await node.decode(); if (!node.naturalWidth) throw new Error("Product image is blank"); });
    if (currentCaseName === "desktop-1366") {
      await page.locator(`[data-product-view='${id}']`).evaluate((node) => scrollTo({ top: node.getBoundingClientRect().top + scrollY - 120, behavior: "instant" }));
      await capture(page, `product-${id}`);
    }
  }
  for (const path of ["/public/", "/command/", "/studio/"]) assert(await page.locator(`#workspaces a[href='${path}']`).count() > 0);
  await page.locator("#case").scrollIntoViewIfNeeded();
  const text = await page.locator("#case").innerText();
  assert.match(text, /available/i);
  assert.match(text, /derived/i);
  assert.match(text, /verif/i);
  assert.match(text, /2024/);
  assert.match(text, /qualified|authorization|authorised|authorized/i);
  await decodeImages(page.locator("#case"));
  if (currentCaseName === "desktop-1366") await capture(page, "historical-evidence");
  await noOverflow(page);
  const viewport = page.viewportSize();
  if (viewport.width > 680) await desktopAvailability(page);
}
async function decodeImages(locator) {
  await locator.locator("img").evaluateAll(async (images) => { for (const image of images) { await image.decode(); if (!image.naturalWidth) throw new Error("Image failed to decode"); } });
}
async function visualOpacity(locator) {
  return locator.evaluate((node) => {
    let opacity = 1;
    for (let current = node; current; current = current.parentElement) {
      const css = getComputedStyle(current);
      if (css.display === "none" || css.visibility === "hidden") return 0;
      opacity *= Number(css.opacity);
    }
    return opacity;
  });
}
async function mobileAvailability(page) {
  const availability = page.locator("[data-pwa-availability]");
  if (!await availability.count()) { assert(!out, "Production must expose availability state"); return; }
  const viewport = page.viewportSize(), summary = availability.locator(":scope > summary");
  const closed = await availability.boundingBox(), summaryBox = await summary.boundingBox();
  assert.equal(closed.x, 0);
  assert.equal(closed.width, viewport.width, "Mobile availability is an opaque bottom band, not a partial-line floating pill");
  assert(Math.abs(closed.y + closed.height - viewport.height) <= 1);
  assert(summaryBox.height >= 44);
  await summary.click();
  assert(await availability.evaluate((node) => node.open));
  const opened = await availability.boundingBox(), header = await page.locator("main[data-landing] > header").boundingBox();
  assert(opened.y >= header.y + header.height && opened.y + opened.height <= viewport.height + 1);
  await capture(page, `mobile-${viewport.width}-availability-open`);
  await summary.click();
  await page.locator("main[data-landing] > footer").scrollIntoViewIfNeeded();
  const footer = await page.locator("main[data-landing] > footer").evaluate((node) => Array.from(node.querySelectorAll("p,span,a")).filter((element) => element.getBoundingClientRect().height > 0).map((element) => element.getBoundingClientRect().bottom));
  const band = await availability.boundingBox();
  assert(Math.max(...footer) <= band.y, "The bottom status band must leave final footer content reachable");
  await capture(page, `mobile-${viewport.width}-footer`);
}
async function desktopAvailability(page) {
  const availability = page.locator("[data-pwa-availability]");
  if (!await availability.count()) { assert(!out, "Production must expose availability state"); return; }
  assert.equal(await availability.evaluate((node) => getComputedStyle(node).position), "static");
  await availability.scrollIntoViewIfNeeded();
  const footer = await page.locator("main[data-landing] > footer").boundingBox(), closed = await availability.boundingBox();
  assert(closed.y >= footer.y + footer.height - 1, "Desktop availability must follow the footer without covering its content");
  const summary = availability.locator(":scope > summary");
  await summary.click();
  assert(await availability.evaluate((node) => node.open));
  const body = availability.locator(":scope > summary + div");
  await body.waitFor({ state: "visible" });
  await body.scrollIntoViewIfNeeded();
  await noOverflow(page);
  if (currentCaseName === "desktop-1366") await capture(page, "desktop-availability-footer-open");
  await summary.click();
  assert.equal(await availability.evaluate((node) => node.open), false);
}
async function focusedVisible(page) {
  const result = await page.evaluate(() => {
    const node = document.activeElement, rect = node.getBoundingClientRect();
    let opacity = 1;
    for (let current = node; current; current = current.parentElement) { const css = getComputedStyle(current); if (css.visibility === "hidden" || css.display === "none") return false; opacity *= Number(css.opacity); }
    return opacity >= .9 && rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.bottom <= innerHeight;
  });
  assert(result, "Keyboard focus must be visible inside the viewport");
}
async function motionToggle(page) {
  const readingState = () => page.evaluate(() => ({ scrollY, root: document.querySelector("[data-story]")?.dataset, candidates: Array.from(document.querySelectorAll("[data-story-reading], h2, p")).map((node) => ({ text: node.textContent?.slice(0, 140), key: node.getAttribute("data-story-reading"), rect: node.getBoundingClientRect().toJSON(), opacity: getComputedStyle(node).opacity, clip: getComputedStyle(node).clipPath })).filter((entry) => entry.rect.width > 3 && entry.rect.height > 3 && entry.rect.bottom > 0 && entry.rect.top < innerHeight) }));
  report.motionReading ??= [];
  report.motionReading.push({ step: "before-reduce", state: await readingState() });
  const before = await readingPosition(page, "finding");
  await page.getByRole("button", { name: "Reduce motion", exact: true }).focus();
  await focusedVisible(page);
  await page.keyboard.press("Space");
  await staticPage(page);
  const reduced = await readingPosition(page, "finding");
  report.motionReading.push({ step: "before-enable", state: await readingState() });
  assert(Math.abs(before - reduced) <= 12, `Reduce motion must preserve the reading anchor: ${before} -> ${reduced}`);
  await page.getByRole("button", { name: "Enable motion", exact: true }).click();
  await page.waitForTimeout(300);
  report.motionReading.push({ step: "after-enable", state: await readingState() });
  await enhanced(page);
  await settle(page);
  const enabled = await readingPosition(page, "finding");
  assert(Math.abs(reduced - enabled) <= 12, `Enable motion must preserve the reading anchor: ${reduced} -> ${enabled}`);
  await page.getByRole("button", { name: "Reduce motion", exact: true }).click();
  await staticPage(page);
  await page.reload({ waitUntil: "networkidle" });
  await enhanced(page);
  assert.equal(await page.locator("[data-story]").getAttribute("data-motion-preference"), "auto", "Explicit motion reduction is per visit, not a saved setting");
}
async function readingPosition(page, id) {
  return page.locator(`[data-story-reading='${id}']`).evaluateAll((nodes) => {
    const visible = nodes.filter((node) => {
      const r = node.getBoundingClientRect();
      if (r.width <= 3 || r.height <= 3) return false;
      for (let current = node; current; current = current.parentElement) {
        const css = getComputedStyle(current), rect = current.getBoundingClientRect();
        if (css.visibility === "hidden" || css.display === "none" || Number(css.opacity) < .9 || css.clipPath === "inset(50%)" || (css.overflow === "hidden" && (rect.width <= 3 || rect.height <= 3))) return false;
      }
      return true;
    });
    if (visible.length !== 1) throw new Error(`Expected one actual visible reading anchor, found ${visible.length}`);
    return visible[0].getBoundingClientRect().top;
  });
}
async function idle(page, description) {
  await page.evaluate(() => { delete globalThis.__v4idle; });
  await page.waitForFunction(() => { const count = document.querySelector("[data-desktop-canvas]")?.dataset.renderFrames; if (!count) return false; const old = globalThis.__v4idle; if (!old || old.count !== count) { globalThis.__v4idle = { count, time: performance.now() }; return false; } return performance.now() - old.time >= 200; }, null, { timeout: 15000 });
  const count = await page.locator("[data-desktop-canvas]").getAttribute("data-render-frames");
  await page.waitForTimeout(700);
  assert.equal(await page.locator("[data-desktop-canvas]").getAttribute("data-render-frames"), count, `${description} must stop unnecessary rendering`);
}
async function smoothScroll(page, progress, duration) {
  const samples = await page.evaluate(({ to, duration }) => new Promise((done) => {
    const from = scrollY, start = performance.now(), samples = [];
    function frame(time) { const t = Math.min(1, (time - start) / duration); scrollTo({ top: from + (to - from) * t, behavior: "instant" }); const node = document.querySelector("[data-story]"); samples.push({ time: time - start, scrollY, progress: Number(node.dataset.desktopProgress), network: Number(node.dataset.networkProgress), flood: Number(node.dataset.desktopFlood) }); if (t < 1) requestAnimationFrame(frame); else done(samples); }
    requestAnimationFrame(frame);
  }), { to: await targetY(page, progress), duration });
  const gaps = samples.slice(1).map((entry, index) => entry.time - samples[index].time).sort((a, b) => a - b);
  report.motion.push({ target: progress, requestedDuration: duration, samples, medianRafGap: gaps[Math.floor(gaps.length / 2)], p95RafGap: gaps[Math.floor(gaps.length * .95)], longFramesOver50ms: gaps.filter((value) => value > 50).length });
}
async function capture(page, name) {
  const path = resolve(evidence, `${name}.png`);
  await page.screenshot({ path });
  report.captures.push({ name, path, sha256: hash(readFileSync(path)) });
}
async function auditAccessibility(page, name) {
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  report.accessibility.push({ name, violations: result.violations, incomplete: result.incomplete });
  assert.deepEqual(result.violations, [], "Accessibility violations require investigation; incomplete results are not passes");
}
async function performanceSample(page, name) {
  const sample = await page.evaluate(() => {
    const entries = [...performance.getEntriesByType("navigation"), ...performance.getEntriesByType("resource")].map((entry) => ({ name: entry.name, transferSize: entry.transferSize, encodedBodySize: entry.encodedBodySize, decodedBodySize: entry.decodedBodySize, initiatorType: entry.initiatorType }));
    return { entries, transferredBytes: entries.reduce((sum, entry) => sum + entry.transferSize, 0), cls: globalThis.__v4qa.shifts.reduce((sum, entry) => sum + entry.value, 0), lcp: globalThis.__v4qa.lcp.at(-1), layoutShifts: globalThis.__v4qa.shifts, longTasks: globalThis.__v4qa.longTasks };
  });
  report.performance.push({ name, ...sample, enforcedProductionBudget: Boolean(out) });
  if (out) {
    assert(sample.transferredBytes <= (name === "initial" ? report.budgets.initialBytes : report.budgets.fullBytes), `${name} resource transfer budget exceeded: ${sample.transferredBytes}`);
    assert(sample.cls <= report.budgets.cls, `${name} layout shift exceeded: ${sample.cls}`);
  }
  save();
}

async function contrastEvidence(page, name, selector) {
  const text = await page.locator(selector).evaluateAll((roots) => {
    const output = [], seen = new Set();
    const overlays = Array.from(document.querySelectorAll("body *")).filter((element) => {
      const css = getComputedStyle(element);
      return ["fixed", "sticky"].includes(css.position) && element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
    });
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const node = walker.currentNode, element = node.parentElement;
        if (seen.has(node) || !node.textContent.trim() || !element) continue;
        seen.add(node);
        if (!element.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) continue;
        let visible = true;
        for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
          const css = getComputedStyle(ancestor), rect = ancestor.getBoundingClientRect();
          if ((ancestor.tagName === "DETAILS" && !ancestor.open && !ancestor.querySelector(":scope > summary")?.contains(element)) || css.display === "none" || css.visibility === "hidden" || Number(css.opacity) < .99 || css.clipPath === "inset(50%)" || (css.display !== "contents" && (rect.width <= 2 || rect.height <= 2))) { visible = false; break; }
        }
        if (!visible) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        const rects = Array.from(range.getClientRects()).map((rect) => rect.toJSON()).filter((rect) => rect.top >= 104 && rect.bottom <= innerHeight && rect.left >= 0 && rect.right <= innerWidth);
        if (!rects.length) continue;
        const css = getComputedStyle(element);
        const occlusions = overlays.filter((overlay) => {
          if (overlay.contains(element) || element.contains(overlay)) return false;
          const rect = overlay.getBoundingClientRect();
          return rects.some((line) => {
            const left = Math.max(rect.left, line.left), right = Math.min(rect.right, line.right), top = Math.max(rect.top, line.top), bottom = Math.min(rect.bottom, line.bottom);
            if (left >= right || top >= bottom) return false;
            const hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
            return hit && overlay.contains(hit) && hit !== element && !element.contains(hit);
          });
        }).map((overlay) => ({ tag: overlay.tagName, pwa: overlay.hasAttribute("data-pwa-availability"), rect: overlay.getBoundingClientRect().toJSON() }));
        output.push({ text: node.textContent.trim(), tag: element.tagName, color: element instanceof SVGElement ? css.fill : css.color, fontSize: parseFloat(css.fontSize), fontWeight: Number(css.fontWeight), rects, occlusions });
      }
    }
    return output;
  });
  assert(text.length > 0, `No actual visible text was measured for ${name}`);
  await capture(page, `manual-${name}`);
  const path = resolve(evidence, `manual-${name}-text-backing.png`);
  await page.screenshot({ path, style: "main[data-landing] :is(h1,h2,h3,p,small,span,a,button,summary,dt,dd,figcaption,code), [data-pwa-availability] :is(summary,span,small,strong,dt,dd,p,button) { color: transparent !important; -webkit-text-fill-color: transparent !important; text-shadow: none !important; } main[data-landing] svg text { fill: transparent !important; }" });
  const image = await sharp(path).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  const luminance = (rgb) => rgb.map((value) => value / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, i) => sum + value * [.2126, .7152, .0722][i], 0);
  const measurements = text.map((entry) => {
    const rgb = entry.color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
    assert(rgb?.length === 3, `Unsupported text color ${entry.color}`);
    const foreground = luminance(rgb);
    let minimum = Infinity, backing = null, testedPixels = 0, belowThreshold = 0, occludedPixels = 0;
    const threshold = entry.fontSize >= 24 || (entry.fontSize >= 18.667 && entry.fontWeight >= 700) ? 3 : 4.5;
    for (const rect of entry.rects) for (let y = Math.ceil(rect.top); y < Math.floor(rect.bottom); y++) for (let x = Math.ceil(rect.left); x < Math.floor(rect.right); x++) {
      if (entry.occlusions.some(({ rect: overlay }) => x >= overlay.left && x < overlay.right && y >= overlay.top && y < overlay.bottom)) { occludedPixels++; continue; }
      const index = (y * image.info.width + x) * 3, backgroundRgb = Array.from(image.data.subarray(index, index + 3)), background = luminance(backgroundRgb);
      const ratio = (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
      testedPixels++;
      if (ratio < threshold) belowThreshold++;
      if (ratio < minimum) { minimum = ratio; backing = { x, y, rgb: backgroundRgb }; }
    }
    return { ...entry, threshold, minimum: testedPixels ? minimum : null, backing, testedPixels, belowThreshold, occludedPixels };
  });
  (report.contrastMeasurements ??= []).push({ name, recordedAt: new Date().toISOString(), scope: "Rendered backing pixels within visible text line rectangles at this viewport/state; manual inspection still required, not a full accessibility certification.", backingPath: path, backingSha256: hash(readFileSync(path)), measurements });
  assert(measurements.some((entry) => entry.testedPixels > 0), `No unobscured painted text was measured for ${name}`);
  assert(measurements.every((entry) => entry.belowThreshold === 0), `A measured text backing failed the scoped contrast threshold in ${name}; inspect the retained image and pixel coordinates`);
}
