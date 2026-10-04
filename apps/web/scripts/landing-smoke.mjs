import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { cpus, platform, release, totalmem } from "node:os";
import { dirname, extname, resolve, sep } from "node:path";
import { gzipSync } from "node:zlib";
import AxeBuilder from "@axe-core/playwright";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const require = createRequire(import.meta.url);
const sharp = require(require.resolve("sharp", { paths: [dirname(require.resolve("next/package.json"))] }));
const out = resolve(process.env.FLOODGUARD_LANDING_OUT ?? "out");
const evidence = resolve(process.env.FLOODGUARD_LANDING_EVIDENCE ?? "test-results/landing-v2");
const chapters = ["place", "dry", "flood", "access", "public", "command", "studio", "shared"];
const requestedCases = new Set(process.argv.slice(2));
const publicBasemapOrigins = new Set(["https://tile.openstreetmap.org", "https://services.arcgisonline.com"]);
const report = {
  recordedAt: new Date().toISOString(),
  result: "STARTED",
  configuration: "Playwright Chromium, headless, local static HTTP with gzip for text, DPR 1, no network throttling, service workers blocked; laboratory evidence only. The metrics.cls guard sums all non-input layout shifts across the tested story, which is stricter than field CWV session-window CLS.",
  device: { platform: platform(), release: release(), cpu: cpus()[0]?.model, logicalCpus: cpus().length, memoryBytes: totalmem() },
  cases: [],
  screenshots: [],
  heroCues: [],
  accessibility: [],
  contrastEvidence: [],
  requestedCases: [...requestedCases],
  historicalV1ManualAccessibilityReview: {
    reviewedOn: "2026-09-08",
    reviewedCompetitionCacheVersion: "dc46e4fa5b77",
    sourceSha256: {
      "src/components/landing/landing.module.css": "f833dc41d0653ead5ddd86abdb8e22f42a2c8c21758f686a2922ed76fb11681e",
      "src/components/landing/landing-page.tsx": "d218336ae71f107e3851e24096c346c3c9f6de132c785eb7ff0fdb3d091c973a",
      "src/components/landing/landing-nav.client.tsx": "c5f9eb2bba7ca35b877fb96f12171568b1efd64e2f2cb5d29b99139dda5b7c9f",
      "src/components/pwa-register.module.css": "f92cb23149bf4ede9170fb91f467d8ebf39c58d7ec94ee2c5dbb1c8be66e56a8",
      "src/components/pwa-register.tsx": "925ec659ddfca04fa88943438c8a85758d01baf5644249381d0cce71e09506eb",
      "src/app/globals.css": "3406da5a3fd29dce0b9c7ccb93ce69641304c73898c55e59495520f73bf52084",
      "src/lib/landing/copy.en.json": "4c6e88312ca220e1de737fc9f897636504c2686f631f1d6e93307467c21be6bd",
    },
    emittedCssSha256: {
      "063-aa~6urabc.css": "f4fe691813c06fd1d56720023bb79c1a7f070a7f4fad9b3ebf03f01cbc08c474",
      "0dxb5qpo2-a~e.css": "5cb8775fdb234c0d92716b9c58317e621b7b2c5058313e0bf7bc86017455ebaa",
      "0etwwhav7_u_..css": "acabd1e0e842357376d98dd028069875f3fa269071afcc93d3a98411e48e5a91",
      "0sstoqtpias.r.css": "a1ee81ec8d7426e87309e750efad1b121d0a720f798263da5adb10570569a734",
      "15257ht_21.vq.css": "5dead1cfb987134d4bb52fbc65dc3105e5315005fd9af5abe513754e5e35c200",
    },
    scope: "Hero contrast items marked incomplete by axe, inspected in exported Chromium screenshots and computed styles at 1440x1000 and 390x844; this is a separate manual review, not an automated axe pass.",
    method: "WCAG relative-luminance contrast from computed foreground/background colors, checked against actual glyph positions and decorative-image bounds. Mobile status uses a conservative 96-percent-white-over-black backing.",
    normalTextMinimumRatio: 4.5,
    pairs: [
      { foreground: "#102f3a", background: "#f6f7f3", ratio: 13.1010, use: "Hero title, supporting heading and links" },
      { foreground: "#006c73", background: "#f6f7f3", ratio: 5.7529, use: "Hero eyebrow and accent text" },
      { foreground: "#4a6470", background: "#f6f7f3", ratio: 5.8295, use: "Hero body and scope captions" },
      { foreground: "#ffffff", background: "#006c73", ratio: 6.1900, use: "Primary action" },
      { foreground: "#102f3a", background: "rgb(244.8,244.8,244.8)", ratio: 12.9071, use: "Online status, worst-case alpha-composited backing" },
    ],
    observations: [
      "Desktop central hero glyphs stay clear of contour fields at x0..280 and x1160..1440; the next-story cue ends at y540.25 before illustration begins at y544.25.",
      "Desktop scope caption glyphs at y1000.25 are below the decorative contour field, and their right clearance prevents status-pill overlap.",
      "Mobile decorative contours are disabled; the status label has its own opaque-enough backing and does not overlap hero text.",
      "The first chapter's content cue appears in the first viewport: y496.25..540.25 at 1440x1000 and y552.48..596.48 at 390x844.",
    ],
    historicalFinding: "Reviewed hero contrast items meet 4.5:1; all axe incomplete records remain recorded separately for transparency. This dated finding must not be treated as a manual review of changed future artifacts.",
  },
};
mkdirSync(evidence, { recursive: true });
writeFileSync(resolve(evidence, "landing-smoke.json"), `${JSON.stringify(report, null, 2)}\n`);
const cssDirectory = resolve(out, "_next/static/chunks");
const emittedCss = existsSync(cssDirectory) ? readdirSync(cssDirectory).filter((file) => file.endsWith(".css")) : [];
const manualReviewPath = resolve(process.env.FLOODGUARD_LANDING_MANUAL_REVIEW ?? `${evidence}/manual-contrast-review.json`);
report.manualAccessibilityReview = existsSync(manualReviewPath)
  ? { ...JSON.parse(readFileSync(manualReviewPath, "utf8")), recordPath: manualReviewPath }
  : { result: "NOT_REVIEWED_FOR_CURRENT_ARTIFACT", applicableToCurrentArtifact: false, note: "A new dated manual review is required for the v2 artifact; the historical v1 record is not current acceptance." };
for (const manualReview of [report.historicalV1ManualAccessibilityReview, report.manualAccessibilityReview]) {
  if (!manualReview.sourceSha256 || !manualReview.emittedCssSha256) continue;
  const sources = Object.entries(manualReview.sourceSha256);
  const sourceMatchesReview = sources.length > 0 && sources.every(([file, hash]) =>
    existsSync(file) && createHash("sha256").update(readFileSync(file)).digest("hex") === hash,
  );
  const cssMatchesReview = emittedCss.length > 0 && emittedCss.length === Object.keys(manualReview.emittedCssSha256).length && emittedCss.every((file) =>
    createHash("sha256").update(readFileSync(resolve(cssDirectory, file))).digest("hex") === manualReview.emittedCssSha256[file],
  );
  const assetMatchesReview = Object.entries(manualReview.assetSha256 ?? {}).every(([file, hash]) =>
    existsSync(resolve(out, file)) && createHash("sha256").update(readFileSync(resolve(out, file))).digest("hex") === hash,
  );
  manualReview.applicableToCurrentArtifact = sourceMatchesReview && cssMatchesReview && assetMatchesReview;
  manualReview.result = manualReview.applicableToCurrentArtifact ? "APPLICABLE_DATED_REVIEW" : "NOT_REVIEWED_FOR_CURRENT_ARTIFACT";
}
const vercel = JSON.parse(readFileSync(resolve("../../vercel.json"), "utf8"));
const securityHeaders = Object.fromEntries(
  (vercel.headers ?? []).find((entry) => entry.source === "/(.*)")?.headers.map(({ key, value }) => [key, value]) ?? [],
);
const rendererFiles = new Set();
for (const manifestPath of [".next/react-loadable-manifest.json", ".next/server/app/page/react-loadable-manifest.json"]) {
  if (!existsSync(manifestPath)) continue;
  for (const entry of Object.values(JSON.parse(readFileSync(manifestPath, "utf8")))) {
    const files = entry.files ?? [];
    if (!files.some((file) => file.endsWith(".js") && readFileSync(resolve(out, "_next", file), "utf8").includes("data-narrative-canvas"))) continue;
    for (const file of files) rendererFiles.add(`/_next/${file}`);
  }
}
report.deferredAnimation = [...rendererFiles].map((file) => {
  const bytes = readFileSync(resolve(out, file.slice(1)));
  return { file, bytes: bytes.length, gzipBytes: gzipSync(bytes).length };
});
assert(existsSync(resolve(out, "index.html")), "Build the competition profile before running landing smoke.");
const deploymentProfile = JSON.parse(readFileSync(resolve(out, "deployment-profile.json"), "utf8"));
assert.equal(deploymentProfile.profile, "competition", "Landing QA requires the competition export");
report.artifact = {
  profile: deploymentProfile.profile,
  cacheName: JSON.parse(readFileSync(resolve(out, "sw.js"), "utf8").match(/^const CACHE_NAME = ("[^"]+");/m)?.[1] ?? "null"),
  entrySha256: createHash("sha256").update(readFileSync(resolve(out, "index.html"))).digest("hex"),
  offlineManifestSha256: createHash("sha256").update(readFileSync(resolve(out, "offline-assets.json"))).digest("hex"),
};
assert(report.artifact.cacheName, "Export must identify its service-worker cache");
const assetManifest = JSON.parse(readFileSync(resolve(out, "landing/assets-manifest.json"), "utf8"));
assert(typeof assetManifest.provenance === "string" && assetManifest.provenance.length > 0, "Landing assets require explicit source provenance");
assert(typeof assetManifest.source === "string" && existsSync(assetManifest.source), "Landing assets require an available editable master");
assert(Array.isArray(assetManifest.assets) && assetManifest.assets.length > 0, "Landing asset manifest is empty");
assert(assetManifest.district?.buildingCount >= 30 && assetManifest.district.buildingCount <= 60, "The district must contain 30 to 60 buildings");
assert.deepEqual([...assetManifest.district.landmarks].sort(), ["Junction_A", "Service_A", "Neighborhood_A", "Field_A"].sort(), "The district must retain the four named landmarks");
assert.equal(assetManifest.contextSource?.status, "user_supplied_unverified_photo_style_concept", "The opening source must not be promoted to documentary or registered imagery");
assert(/^[a-f0-9]{64}$/.test(assetManifest.contextSource.sha256), "The opening source must retain its original checksum");
assert(Array.isArray(assetManifest.editableSources) && assetManifest.editableSources.length > 0, "The asset manifest must bind its editable source inputs");
for (const source of assetManifest.editableSources) {
  const bytes = readFileSync(source.path);
  assert.equal(bytes.length, source.bytes, `Editable source size changed after art generation: ${source.path}`);
  assert.equal(createHash("sha256").update(bytes).digest("hex"), source.sha256, `Editable source changed after art generation: ${source.path}`);
}
for (const chapter of chapters) assert(assetManifest.assets.some((asset) => asset.id === chapter), `${chapter} requires a same-master static figure`);
for (const asset of assetManifest.assets) {
  const path = resolve(out, String(asset.path).replace(/^\/+/, ""));
  assert(path.startsWith(`${out}${sep}`), "Landing asset path must stay inside the export");
  const bytes = readFileSync(path);
  assert.equal(bytes.length, asset.bytes, `Asset size differs from its manifest: ${asset.path}`);
  assert.equal(createHash("sha256").update(bytes).digest("hex"), asset.sha256, `Asset checksum differs from its manifest: ${asset.path}`);
  if (/\.(?:webp|png|jpe?g)$/i.test(path)) {
    const metadata = await sharp(bytes).metadata();
    assert.equal(metadata.width, asset.width, `Asset width differs from its manifest: ${asset.path}`);
    assert.equal(metadata.height, asset.height, `Asset height differs from its manifest: ${asset.path}`);
  }
}
const staticRegistration = Object.fromEntries(chapters.map((id) => [id, assetManifest.assets.find((asset) => asset.id === id)]));
assert(staticRegistration.dry.cameraSignature && staticRegistration.dry.cameraSignature === staticRegistration.flood.cameraSignature,
  "The dry and flooded fallback figures must use the same camera");
assert(staticRegistration.dry.floodAmount === 0 && staticRegistration.flood.floodAmount > 0 && staticRegistration.shared.floodAmount === 1,
  "The static figures must show unaffected, flooded, and persistently flooded closing states");
for (const id of assetManifest.district.landmarks) {
  assert.deepEqual(staticRegistration.dry.landmarks?.[id], staticRegistration.flood.landmarks?.[id], `${id} must retain its position in the paired fallback figures`);
  assert(Number.isFinite(staticRegistration.dry.landmarks?.[id]?.x) && Number.isFinite(staticRegistration.dry.landmarks?.[id]?.y), `${id} requires recorded static registration coordinates`);
}
report.assetProvenance = {
  revision: assetManifest.revision,
  origin: assetManifest.origin,
  source: assetManifest.source,
  sourceSha256: createHash("sha256").update(readFileSync(assetManifest.source)).digest("hex"),
  provenance: assetManifest.provenance,
  contextSource: assetManifest.contextSource,
  district: assetManifest.district,
  editableSources: assetManifest.editableSources,
  staticRegistration: Object.fromEntries(Object.entries(staticRegistration).map(([id, asset]) => [id, { floodAmount: asset.floodAmount, cameraSignature: asset.cameraSignature, landmarks: asset.landmarks }])),
  manifestSha256: createHash("sha256").update(readFileSync(resolve(out, "landing/assets-manifest.json"))).digest("hex"),
  verifiedAssetCount: assetManifest.assets.length,
  verifiedAssetBytes: assetManifest.assets.reduce((sum, asset) => sum + asset.bytes, 0),
};

const contentTypes = {
  ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png",
  ".woff2": "font/woff2", ".glb": "model/gltf-binary",
  ".webmanifest": "application/manifest+json",
  ".txt": "text/plain; charset=utf-8",
};
const server = createServer((request, response) => {
  const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
  let file = resolve(out, decodeURIComponent(pathname).replace(/^\/+/, "") || "index.html");
  if (file !== out && !file.startsWith(`${out}${sep}`)) return response.writeHead(403).end();
  if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
  if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end();
  const extension = extname(file);
  const acceptsGzip = (request.headers["accept-encoding"] ?? "").split(",").some((part) => {
    const [encoding, ...parameters] = part.trim().split(";");
    return encoding === "gzip" && !parameters.some((parameter) => /^q\s*=\s*0(?:\.0*)?$/.test(parameter.trim()));
  });
  const compress = acceptsGzip && /\.(?:html|css|js|json|svg|txt)$/.test(extension);
  const body = readFileSync(file);
  response.writeHead(200, {
    ...securityHeaders,
    "Content-Type": contentTypes[extension] ?? "application/octet-stream",
    "Cache-Control": "no-store",
    ...(compress ? { "Content-Encoding": "gzip" } : {}),
  });
  response.end(compress ? gzipSync(body) : body);
});
await new Promise((done, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", done); });
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await launchFloodGuardBrowser();

try {
  report.browser = browser.version();
  await runCase("desktop", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await assertStoryCue(page);
    report.initialOpeningGeometry = await initialOpeningGeometry(page);
    await screenshot(page, "desktop-hero");
    report.initialResources = await resources(page);
    assert(report.initialResources.transferBytes <= 1200 * 1024, "Initial transfer exceeds 1200 KiB");
    assert(report.initialResources.metrics.cls <= 0.1, "Initial layout shifts exceed CLS 0.1");
    assert(report.deferredAnimation.reduce((sum, asset) => sum + asset.gzipBytes, 0) <= 650 * 1024, "Deferred renderer exceeds 650 KiB gzip");
    for (const path of ["/public/", "/command/", "/studio/"]) {
      assert.equal((await page.request.get(`${base}${path}`)).status(), 200, `${path} must exist`);
    }
    const fingerprints = [];
    const registeredFrames = {};
    let persistentCanvas;
    for (const chapter of chapters) {
      await seekChapter(page, chapter);
      await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "enhanced", undefined, { timeout: 20000 });
      await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
      assert.equal(await page.locator("[data-story] canvas").count(), 1, "Only one story canvas may exist");
      if (!persistentCanvas) persistentCanvas = await page.locator("[data-story] canvas").elementHandle();
      else assert(await persistentCanvas.evaluate((canvas) => canvas.isConnected && canvas === document.querySelector("[data-story] canvas")), "Story chapters must retain the same canvas instance");
      assert.equal(await page.locator("[data-story-stage]").getAttribute("data-active-chapter"), String(chapters.indexOf(chapter)));
      await assertStageLabelsClear(page);
      fingerprints.push(await canvasPixels(page, chapter));
      registeredFrames[chapter] = await sceneRegistration(page);
      report.contrastEvidence.push({ name: `desktop-${chapter}`, labels: await labelStyles(page) });
      await screenshot(page, `desktop-${chapter}`);
    }
    await persistentCanvas?.dispose();
    assert(new Set(fingerprints.map((entry) => entry.hash)).size > 2, "Scrolling must change the rendered scene");
    report.canvas = fingerprints;
    report.sceneRegistration = registeredFrames;
    assert.equal(registeredFrames.dry.cameraSignature, registeredFrames.flood.cameraSignature, "The dry-to-flood comparison must hold its camera");
    assert.equal(registeredFrames.dry.cameraSignature, registeredFrames.access.cameraSignature, "The blocked-connection explanation must preserve the comparison camera");
    assert(registeredFrames.dry.floodAmount <= 0.001, "The dry neighborhood must be unaffected");
    assert(registeredFrames.flood.floodAmount > 0, "Flood chapter must visibly introduce water");
    assert(registeredFrames.shared.floodAmount >= 0.99 && registeredFrames.shared.floodAmount >= registeredFrames.flood.floodAmount,
      "The closing overview must retain the flood rather than remove it");
    for (const id of ["Junction_A", "Service_A", "Neighborhood_A", "Field_A"]) {
      const dry = registeredFrames.dry.landmarks[id];
      const flood = registeredFrames.flood.landmarks[id];
      assert(Math.hypot(dry.x - flood.x, dry.y - flood.y) <= 0.002, `${id} moved between dry and flooded states`);
      for (const coordinate of [dry.x, dry.y, flood.x, flood.y]) assert(coordinate >= 0 && coordinate <= 1, `${id} is outside the registered comparison frame`);
    }
    await waitForSettledScene(page);
    const idleBefore = await sceneCounters(page);
    await page.waitForTimeout(700);
    const idleAfter = await sceneCounters(page);
    report.idleObservation = { before: idleBefore, after: idleAfter };
    assert.equal(idleAfter.frames, idleBefore.frames, "Settled scene must not keep rendering");
    assert(idleAfter.triangles <= 100000, "Visible geometry exceeds its budget");
    assert(idleAfter.drawCalls <= 70, "Visible draw calls exceed their budget");
    report.renderCounters = idleAfter;
    await seekChapter(page, "public");
    await waitForSettledScene(page);
    const reversed = await canvasPixels(page, "public-reversed");
    assert.equal(reversed.hash, fingerprints[chapters.indexOf("public")].hash, "Reverse seeking must restore the same rendered chapter pose");
    await screenshot(page, "desktop-reversed-public");
    report.storyResources = await resources(page);
    assert(report.storyResources.transferBytes <= 6 * 1024 * 1024, "Enhanced narrative transfer exceeds 6 MiB");
    assert(report.storyResources.metrics.cls <= 0.1, `Story layout shifts exceed CLS 0.1 (${report.storyResources.metrics.cls})`);
    const control = page.getByRole("button", { name: /View without animation/i }).first();
    await control.click();
    await assertStatic(page);
    await page.reload({ waitUntil: "networkidle" });
    await assertStatic(page);
    const prefs = await page.evaluate(() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => /motion|landing/i.test(key))));
    assert(Object.keys(prefs).length > 0, "Explicit static preference must persist locally");
    report.motionPreference = prefs;
    await screenshot(page, "desktop-static-preference");
  });

  await runCase("opening-handoff", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    const frames = [];
    let persistentCanvas;
    for (const progress of [0, 0.04, 0.08, 0.12, 0.128, 0.132, 0.16, 0.18]) {
      await seekStoryProgress(page, progress);
      if (progress >= 0.08) await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
      const state = await openingState(page);
      if (progress >= 0.08) await assertStageLabelsClear(page);
      if (progress === 0.08 || progress === 0.132) report.contrastEvidence.push({ name: `opening-${progress}`, labels: await labelStyles(page) });
      assert(Number.isFinite(state.photoOpacity) && Number.isFinite(state.selectionProgress) && Number.isFinite(state.extractionProgress) && Number.isFinite(state.architectureProgress), "Opening transition values must be finite");
      assert(state.photoOpacity >= 0 && state.photoOpacity <= 1, "Photo opacity is outside its range");
      assert(state.photoPixelsReady, "Opening image must be decoded throughout the transition");
      assert(state.actualPhotoOpacity > 0 || state.sceneReady, "Photo-to-model handoff must not expose an empty stage");
      if (!state.sceneReady) assert(state.actualPhotoOpacity >= 0.99, "The photograph must remain visible until the model frame is ready");
      assert(await page.locator("[data-story] canvas").count() <= 1, "Opening must not allocate overlapping renderers");
      if (state.sceneReady) {
        if (!persistentCanvas) persistentCanvas = await page.locator("[data-story] canvas").elementHandle();
        else assert(await persistentCanvas.evaluate((canvas) => canvas.isConnected && canvas === document.querySelector("[data-story] canvas")), "Opening handoff must preserve the renderer instance");
      }
      const previous = frames.at(-1);
      if (previous) assert(state.photoOpacity <= previous.photoOpacity + 0.001, "Forward opening motion must not restore the photo unexpectedly");
      if (previous) assert(state.extractionProgress >= previous.extractionProgress - 0.001, "Forward opening motion must not reverse the district extraction unexpectedly");
      frames.push({ progress, ...state });
      await screenshot(page, `opening-${Math.round(progress * 1000).toString().padStart(3, "0")}`);
    }
    assert(frames[0].actualPhotoOpacity >= 0.99, "The opening must begin with its photographic concept");
    assert(frames.at(-1).actualPhotoOpacity <= 0.001, "The dry neighborhood must finish the photo-to-model handoff");
    const before = frames.find((frame) => frame.progress === 0.128).stage;
    const after = frames.find((frame) => frame.progress === 0.132).stage;
    for (const key of ["x", "y", "width", "height"]) assert(Math.abs(before[key] - after[key]) <= 1, `The visual stage jumps at the end of the handoff: ${key}`);
    await seekStoryProgress(page, 0.08);
    const reversed = await openingState(page);
    report.openingContinuity = { scope: "Automated stage geometry, readiness, scalar continuity and renderer identity. Aerial-to-model visual correspondence requires separate manual review and does not establish geographic registration.", frames, reversed };
    assert(Math.abs(reversed.actualPhotoOpacity - frames.find((frame) => frame.progress === 0.08).actualPhotoOpacity) <= 0.002,
      `Reverse scroll must restore the same photo/model blend (forward ${frames.find((frame) => frame.progress === 0.08).actualPhotoOpacity}, reverse ${reversed.actualPhotoOpacity})`);
    await screenshot(page, "opening-reversed");
    await persistentCanvas?.dispose();
  });

  for (const [name, viewport] of [
    ["mobile", { width: 390, height: 844 }],
    ["narrow", { width: 320, height: 768 }],
    ["short-desktop", { width: 1264, height: 620 }],
    ["zoom-reflow", { width: 720, height: 500 }],
  ]) {
    await runCase(name, { viewport }, async (page, routePhase) => {
      await assertStatic(page);
      if (name !== "zoom-reflow") await assertStoryCue(page);
      await screenshot(page, `${name}-hero`);
      await page.locator("#studio").scrollIntoViewIfNeeded();
      await screenshot(page, `${name}-studio`);
      await assertNoOverflow(page);
      if (name === "mobile") {
        const menu = page.locator('summary[aria-label="Open navigation menu"]');
        await menu.click();
        await screenshot(page, "mobile-menu");
        await page.keyboard.press("Escape");
        assert.equal(await menu.evaluate((summary) => summary.parentElement.open), false);
        const panel = page.locator("[data-pwa-availability]");
        const closed = await mobilePwaGeometry(page);
        assert(closed.panel.x <= 1 && closed.panel.width >= viewport.width - 1 && Math.abs(closed.panel.bottom - viewport.height) <= 1,
          "Mobile landing status must occupy a full-width bottom band");
        assert.equal(closed.background, "rgb(255, 255, 255)", "The status band needs an opaque reading boundary");
        assert(closed.summary.height >= 44, "The status control must retain its touch target");
        await page.locator("[data-opening-provenance]").scrollIntoViewIfNeeded();
        const provenance = await page.locator("[data-opening-provenance] span").evaluateAll((elements) => elements.map((element) => {
          const rect = element.getBoundingClientRect();
          return { text: element.textContent.trim(), top: rect.top, bottom: rect.bottom };
        }));
        assert(provenance.length >= 2 && provenance.every((line) => line.text.length > 0 && line.top >= 60 && line.bottom <= closed.panel.y),
          "Both mobile source-disclosure lines must remain reachable in the reading area");
        await screenshot(page, "mobile-source-provenance");
        await panel.locator("summary").click();
        const open = await mobilePwaGeometry(page);
        assert(open.panel.y >= 60 && open.panel.bottom <= viewport.height + 1, "Expanded status must fit below the mobile header");
        await screenshot(page, "mobile-status-open");
        await panel.locator("summary").click();
        await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
        const footerBottom = await page.locator("main[data-landing] footer span").last().evaluate((element) => element.getBoundingClientRect().bottom);
        const footerBand = await mobilePwaGeometry(page);
        assert(footerBottom <= footerBand.panel.y, "The final footer text must be reachable above the mobile status band");
        await screenshot(page, "mobile-footer-clearance");
        routePhase.current = "public-transition";
        await page.locator('footer a[href="/public/"]').click();
        await page.locator("main.public-page").waitFor();
        await page.locator("main.public-page .leaflet-overlay-pane canvas").first().waitFor({ state: "visible" });
        const publicWorkspace = await mobilePwaGeometry(page);
        assert(publicWorkspace.panel.x > 0 && publicWorkspace.panel.width < viewport.width && publicWorkspace.panel.bottom < viewport.height - 20,
          "The landing-only status band must not alter Public's existing layout");
        await screenshot(page, "mobile-public-status-scope");
        await page.goBack({ waitUntil: "domcontentloaded" });
        await page.locator("main[data-landing]").waitFor();
        routePhase.current = "landing";
        const returned = await mobilePwaGeometry(page);
        assert(returned.panel.x <= 1 && returned.panel.width >= viewport.width - 1 && Math.abs(returned.panel.bottom - viewport.height) <= 1,
          "Returning to the landing page must restore its scoped status band");
        report.mobilePwa = { closed, provenance, open, footerBottom, footerBand, publicWorkspace, returned };
      }
    });
  }
  for (const viewport of [
    { width: 430, height: 932 }, { width: 1024, height: 768 },
    { width: 1440, height: 900 }, { width: 1536, height: 1024 },
    { width: 2048, height: 1152 }, { width: 1280, height: 700 },
  ]) {
    const name = `viewport-${viewport.width}x${viewport.height}`;
    await runCase(name, { viewport }, async (page) => {
      await assertStoryCue(page);
      await screenshot(page, `${name}-hero`);
      if (viewport.width < 1100) {
        await assertStatic(page);
        await page.locator("#access").scrollIntoViewIfNeeded();
      } else {
        await seekChapter(page, "access");
        await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
        await canvasPixels(page, name);
        await assertStageLabelsClear(page);
        const controls = await page.locator("[data-story-controls]").evaluate((element) => {
          const rect = element.getBoundingClientRect();
          return { top: rect.top, bottom: rect.bottom, viewportHeight: innerHeight };
        });
        assert(controls.top >= 0 && controls.bottom <= controls.viewportHeight, `${name} clips chapter controls: ${JSON.stringify(controls)}`);
      }
      await assertNoOverflow(page);
      await screenshot(page, `${name}-access`);
    });
  }

  await runCase("reduced-motion", { viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" }, async (page) => {
    await assertStatic(page);
    assert.equal(await page.locator("[data-narrative-canvas]").count(), 0, "Reduced motion must not allocate the optional scene");
    assert.notEqual(await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior), "smooth");
    await screenshot(page, "reduced-motion");
  });
  await runCase("save-data", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await assertStatic(page);
    assert.equal(await page.locator("[data-narrative-canvas]").count(), 0, "Data-saving mode must not allocate the optional scene");
    const requested = (await resources(page)).entries.filter((entry) => rendererFiles.has(entry.path));
    assert.deepEqual(requested, [], "Data-saving mode must not download the deferred renderer");
    await screenshot(page, "save-data");
  }, async (page) => {
    await page.addInitScript(() => {
      const connection = new EventTarget();
      Object.defineProperty(connection, "saveData", { value: true });
      Object.defineProperty(navigator, "connection", { configurable: true, value: connection });
    });
  });
  await runCase("offline-policy", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    const initialFragmentTop = await page.locator("#shared").evaluate((element) => element.getBoundingClientRect().top);
    assert(initialFragmentTop >= 0 && initialFragmentTop < 250, "A cold offline deep link must restore its static chapter");
    await assertStatic(page);
    assert.equal(await page.locator("[data-narrative-canvas]").count(), 0, "Offline policy must not allocate the uncached optional scene");
    const requested = (await resources(page)).entries.filter((entry) => rendererFiles.has(entry.path));
    assert.deepEqual(requested, [], "Offline policy must not request the deferred renderer");
    report.offlinePolicy = { scope: "navigator.onLine=false fixture at cold #shared; local HTTP stays available to verify policy and static content. Real service-worker offline behavior is tested separately.", initialFragmentTop };
    await screenshot(page, "offline-policy");
  }, async (page) => {
    await page.addInitScript(() => Object.defineProperty(navigator, "onLine", { configurable: true, value: false }));
  }, "/#shared");
  await runCase("connectivity-transition", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await seekChapter(page, "public");
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    const readingElement = await page.locator("[data-story]").evaluateHandle((root) => [...root.querySelectorAll("h2,p")]
      .map((element) => ({ element, bounds: element.getBoundingClientRect() }))
      .filter(({ bounds }) => bounds.height > 0 && bounds.bottom > 180 && bounds.top < innerHeight)
      .sort((a, b) => Math.abs(a.bounds.top - 180) - Math.abs(b.bounds.top - 180))[0]?.element);
    const before = await readingElement.evaluate((element) => element.getBoundingClientRect().top);
    await page.evaluate(() => {
      Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
      dispatchEvent(new Event("offline"));
    });
    await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "static");
    await page.waitForTimeout(800);
    const offline = await readingElement.evaluate((element) => element.getBoundingClientRect().top);
    assert(Math.abs(before - offline) <= 2, "Going offline must preserve the visible reading position");
    assert.equal(await page.locator("[data-narrative-canvas]").count(), 0, "Going offline must release the optional renderer");
    await screenshot(page, "connectivity-offline");
    await page.evaluate(() => {
      Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
      dispatchEvent(new Event("online"));
    });
    await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "enhanced");
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    await page.waitForTimeout(800);
    const reconnected = await readingElement.evaluate((element) => element.getBoundingClientRect().top);
    assert(Math.abs(before - reconnected) <= 2, "Reconnecting must preserve the visible reading position");
    assert.equal(await page.locator("[data-story] canvas").count(), 1);
    report.connectivityTransition = { scope: "Synthetic online/offline browser events; real service-worker caching tested separately.", before, offline, reconnected };
    await readingElement.dispose();
    await screenshot(page, "connectivity-restored");
  });
  await runCase("no-javascript", { viewport: { width: 390, height: 844 }, javaScriptEnabled: false }, async (page) => {
    assert.equal(await page.locator("canvas").count(), 0);
    assert.equal(await page.locator("[data-chapter]").count(), chapters.length);
    await assertStatic(page);
    await assertStoryCue(page);
    await page.locator("#questions summary").first().click();
    assert(await page.locator("#questions details").first().getAttribute("open") !== null);
    await screenshot(page, "no-javascript-faq");
  });
  await runCase("no-javascript-desktop", { viewport: { width: 1440, height: 1000 }, javaScriptEnabled: false }, async (page) => {
    const geometry = await initialOpeningGeometry(page);
    report.noJavaScriptDesktopGeometry = geometry;
    if (report.initialOpeningGeometry) {
      for (const element of ["image", "visual", "opening"]) {
        for (const key of ["x", "y", "width", "height"]) {
          assert(Math.abs(geometry[element][key] - report.initialOpeningGeometry[element][key]) <= 1,
            `The static-to-enhanced opening must preserve ${element} ${key}`);
        }
      }
    }
    await assertStatic(page);
    await assertStoryCue(page);
    await screenshot(page, "no-javascript-desktop-hero");
    await page.locator("#dry").scrollIntoViewIfNeeded();
    await screenshot(page, "no-javascript-desktop-dry");
  });
  await runCase("webgl-unavailable", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await seekChapter(page, "studio");
    await assertStatic(page);
    await screenshot(page, "webgl-unavailable-studio");
  }, async (page) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (kind, ...args) {
        if (/webgl/i.test(kind)) return null;
        return original.call(this, kind, ...args);
      };
    });
  });
  await runCase("deep-link", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "enhanced", undefined, { timeout: 20000 });
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    assert.equal(await page.locator("[data-story-stage]").getAttribute("data-active-chapter"), String(chapters.indexOf("studio")));
    await canvasPixels(page, "deep-link-studio");
    await screenshot(page, "deep-link-studio");
    await seekChapter(page, "place");
    await screenshot(page, "deep-link-reversed-place");
  }, undefined, "/#studio");
  await runCase("renderer-download-failure", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    assert(rendererFiles.size > 0, "Renderer dependency manifest is needed to exercise download failure");
    await seekChapter(page, "studio");
    await page.waitForFunction(() => Boolean(document.querySelector("[data-story]")?.getAttribute("data-render-failure")));
    await assertStatic(page);
    await screenshot(page, "renderer-download-failure");
  }, async (page) => {
    await page.route("**/_next/static/**", (route) => rendererFiles.has(new URL(route.request().url()).pathname)
      ? route.abort("failed") : route.continue());
  });
  await runCase("slow-renderer-deep-link", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    assert.equal(await page.locator("[data-story-stage]").getAttribute("data-scene-ready"), "false", "Slow renderer must retain its poster");
    await screenshot(page, "slow-renderer-poster");
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    assert.equal(await page.locator("[data-story-stage]").getAttribute("data-active-chapter"), String(chapters.indexOf("studio")));
    await screenshot(page, "slow-renderer-ready");
  }, async (page) => {
    await page.route("**/_next/static/**", async (route) => {
      if (rendererFiles.has(new URL(route.request().url()).pathname)) await new Promise((done) => setTimeout(done, 2500));
      await route.continue();
    });
  }, "/#studio", "domcontentloaded");
  await runCase("context-loss", { viewport: { width: 1440, height: 1000 } }, async (page) => {
    await seekChapter(page, "command");
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    await page.locator("[data-story] canvas").evaluate((canvas) => {
      const event = new Event("webglcontextlost", { cancelable: true });
      canvas.dispatchEvent(event);
    });
    await assertStatic(page);
    await screenshot(page, "context-loss-static");
  });
  await runCase("route-lifecycle", { viewport: { width: 1440, height: 1000 } }, async (page, routePhase) => {
    const publicDwellMs = [0, 60, 200, 0, 60, 200, 0, 200];
    report.routeLifecycle = { cycles: publicDwellMs.length, publicDwellMs, activeCanvasVisits: 0 };
    for (const dwell of publicDwellMs) {
      await seekChapter(page, "access");
      await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
      assert.equal(await page.locator("[data-story] canvas").count(), 1);
      routePhase.current = "public-transition";
      await page.locator('#workspaces a[href="/public/"]').click();
      await page.locator("main.public-page").waitFor();
      assert.equal(await page.locator("[data-narrative-canvas]").count(), 0);
      await page.locator("main.public-page .leaflet-overlay-pane canvas").first().waitFor({ state: "visible" });
      report.routeLifecycle.activeCanvasVisits += 1;
      if (dwell > 0) await page.waitForTimeout(dwell);
      await page.goBack({ waitUntil: "domcontentloaded" });
      await page.locator("main[data-landing]").waitFor();
      routePhase.current = "landing";
    }
    await seekChapter(page, "command");
    await page.locator("[data-narrative-canvas][data-ready='true']").waitFor();
    assert.equal(await page.locator("[data-story] canvas").count(), 1);
    await waitForSettledScene(page);
    const before = await sceneCounters(page);
    await page.waitForTimeout(700);
    assert.equal((await sceneCounters(page)).frames, before.frames, "Repeated route entry leaked a rendering loop");
    await screenshot(page, "repeated-route-entry");
  });

  const failures = report.cases.filter((entry) => entry.result === "FAIL");
  assert(report.cases.length > 0, "No matching landing smoke cases were selected");
  assert.equal(failures.length, 0, failures.map((entry) => `${entry.name}: ${entry.error}`).join("\n"));
  report.result = "PASS";
} catch (error) {
  report.result = "FAIL";
  report.failure = error.stack ?? error.message;
  throw error;
} finally {
  writeFileSync(resolve(evidence, "landing-smoke.json"), `${JSON.stringify(report, null, 2)}\n`);
  await browser.close();
  await new Promise((done, reject) => server.close((error) => error ? reject(error) : done()));
  console.log(`landing smoke ${report.result}: ${report.cases.length} cases; evidence ${evidence}`);
}

async function runCase(name, options, check, prepare, path = "/", waitUntil = "networkidle") {
  if (requestedCases.size && !requestedCases.has(name)) return;
  const context = await browser.newContext({ serviceWorkers: "block", deviceScaleFactor: 1, ...options });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  const errors = [];
  const mutations = [];
  const external = [];
  const workspaceTransitionExternal = [];
  const routePhase = { current: "landing" };
  let accessibilityIssues = [];
  page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
  page.on("request", (request) => {
    if (!/^(GET|HEAD|OPTIONS)$/.test(request.method())) mutations.push(`${request.method()} ${request.url()}`);
    if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== base) {
      if (routePhase.current === "public-transition" && publicBasemapOrigins.has(new URL(request.url()).origin)) {
        workspaceTransitionExternal.push(request.url());
      } else external.push(request.url());
    }
  });
  try {
    if (options.javaScriptEnabled !== false) {
      await page.addInitScript(() => {
        globalThis.__landingLocationRequests = 0;
        for (const method of ["getCurrentPosition", "watchPosition"]) {
          Object.defineProperty(navigator.geolocation, method, {
            configurable: true,
            value() { globalThis.__landingLocationRequests += 1; },
          });
        }
        globalThis.__landingMetrics = { lcp: 0, cls: 0, layoutShifts: [] };
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) globalThis.__landingMetrics.lcp = entry.startTime;
        }).observe({ type: "largest-contentful-paint", buffered: true });
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (!entry.hadRecentInput) globalThis.__landingMetrics.cls += entry.value;
            globalThis.__landingMetrics.layoutShifts.push({ time: entry.startTime, value: entry.value, hadRecentInput: entry.hadRecentInput,
              sources: entry.sources.map((source) => ({ element: source.node?.outerHTML?.slice(0, 500), previousRect: source.previousRect.toJSON(), currentRect: source.currentRect.toJSON() })) });
          }
        }).observe({ type: "layout-shift", buffered: true });
      });
    }
    if (prepare) await prepare(page);
    await page.goto(`${base}${path}`, { waitUntil });
    await page.locator("main[data-landing]").waitFor({ state: "visible" });
    assert.equal(await page.locator("main[data-landing]").getAttribute("lang"), "en");
    assert.equal(await page.locator("[data-chapter]").count(), chapters.length);
    for (const route of ["/public/", "/command/", "/studio/"]) {
      assert(await page.locator(`header a[href="${route}"]`).count() > 0, `Header must expose ${route}`);
    }
    await assertNoOverflow(page);
    if (name === "desktop" || name === "mobile") {
      const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      report.accessibility.push({ name, violations: audit.violations, incomplete: audit.incomplete.map(({ id, impact, nodes }) => ({ id, impact, targets: nodes.map((node) => node.target) })), passes: audit.passes.length });
      accessibilityIssues = audit.violations.map(({ id, nodes }) => ({ id, targets: nodes.map((node) => node.target) }));
      report.contrastEvidence.push({ name, labels: await labelStyles(page) });
    }
    await check(page, routePhase);
    assert.deepEqual(mutations, [], "Story must never perform operational writes");
    assert.deepEqual(external, [], "Landing must be self-contained");
    assert.deepEqual(errors, [], "Landing must not throw browser errors");
    assert.deepEqual(accessibilityIssues, [], `${name} automated accessibility violations`);
    if (options.javaScriptEnabled !== false) {
      assert.equal(await page.evaluate(() => globalThis.__landingLocationRequests), 0);
    }
    report.cases.push({ name, result: "PASS", errors, mutations, external, workspaceTransitionExternal });
  } catch (error) {
    await screenshot(page, `${name}-failure`).catch(() => {});
    report.cases.push({ name, result: "FAIL", error: error.message, errors, mutations, external, workspaceTransitionExternal });
  } finally {
    await context.close();
    writeFileSync(resolve(evidence, "landing-smoke.json"), `${JSON.stringify(report, null, 2)}\n`);
    console.log(`landing ${name}: ${report.cases.at(-1)?.result}`);
  }
}

async function sceneCounters(page) {
  return page.locator("[data-narrative-canvas]").evaluate((element) => ({
    frames: Number(element.getAttribute("data-render-frames")),
    triangles: Number(element.getAttribute("data-triangles")),
    drawCalls: Number(element.getAttribute("data-draw-calls")),
  }));
}

async function sceneRegistration(page) {
  const frame = await page.locator("[data-narrative-canvas]").evaluate((element) => ({
    floodAmount: element.getAttribute("data-flood-amount"),
    cameraSignature: element.getAttribute("data-camera-signature"),
    landmarks: element.getAttribute("data-landmarks"),
  }));
  assert(frame.floodAmount !== null && frame.cameraSignature && frame.landmarks, "The rendered scene must expose its registration evidence");
  const floodAmount = Number(frame.floodAmount);
  const landmarks = JSON.parse(frame.landmarks);
  assert(Number.isFinite(floodAmount) && floodAmount >= 0 && floodAmount <= 1, "Rendered flood amount is invalid");
  for (const id of ["Junction_A", "Service_A", "Neighborhood_A", "Field_A"]) {
    assert(Number.isFinite(landmarks[id]?.x) && Number.isFinite(landmarks[id]?.y), `Missing rendered landmark ${id}`);
  }
  return { floodAmount, cameraSignature: frame.cameraSignature, landmarks };
}

async function assertNoOverflow(page) {
  const sizes = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
  assert(sizes.scroll <= sizes.width + 1, `Horizontal overflow: ${JSON.stringify(sizes)}`);
}

async function assertStageLabelsClear(page) {
  const overlaps = await page.evaluate(() => {
    const status = document.querySelector("[data-pwa-availability] > summary")?.getBoundingClientRect();
    if (!status) return [];
    const overlaps = [];
    for (const element of document.querySelectorAll("[data-story-caption],[data-story-status]")) {
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) < 0.05) continue;
      const range = document.createRange();
      range.selectNodeContents(element);
      for (const rect of range.getClientRects()) {
        if (rect.right > status.left && rect.left < status.right && rect.bottom > status.top && rect.top < status.bottom) {
          overlaps.push(element.textContent.trim());
        }
      }
    }
    return overlaps;
  });
  assert.deepEqual(overlaps, [], "Stage caption text must not sit behind the fixed connectivity status");
}

async function labelStyles(page) {
  return page.locator("[data-opening-provenance] span,[data-pwa-availability] > summary,[data-story-status],[data-story-caption]").evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const backgrounds = [];
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const computed = getComputedStyle(ancestor);
      if (computed.backgroundColor !== "rgba(0, 0, 0, 0)" || computed.backgroundImage !== "none") {
        backgrounds.push({ tag: ancestor.tagName, color: computed.backgroundColor, image: computed.backgroundImage, opacity: computed.opacity });
      }
    }
    return { text: element.textContent.trim(), foreground: style.color, fontSize: style.fontSize, fontWeight: style.fontWeight, opacity: style.opacity, visibility: style.visibility, display: style.display, bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, backgrounds };
  }));
}

async function mobilePwaGeometry(page) {
  return page.locator("[data-pwa-availability]").evaluate((element) => {
    const summary = element.querySelector("summary");
    const panelRect = element.getBoundingClientRect();
    const summaryRect = summary.getBoundingClientRect();
    const rect = (bounds) => ({ x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height, bottom: bounds.bottom });
    return { panel: rect(panelRect), summary: rect(summaryRect), background: getComputedStyle(summary).backgroundColor };
  });
}

async function assertStatic(page) {
  await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "static");
  assert.equal(await page.locator("[data-story] canvas:visible").count(), 0, "Static mode must hide the optional renderer");
  if (await page.locator("[data-narrative-canvas]").count()) {
    assert.equal(await page.locator("[data-story-canvas]").getAttribute("data-scene-active"), "false");
    await waitForSettledScene(page, false);
    const before = await sceneCounters(page);
    await page.waitForTimeout(700);
    assert.equal((await sceneCounters(page)).frames, before.frames, "Static mode must suspend rendering");
  }
  for (const chapter of chapters) {
    const figure = page.locator(`#${chapter} img`).first();
    assert.equal(await figure.count(), 1, `Static chapter ${chapter} needs a still`);
    await figure.scrollIntoViewIfNeeded();
    await figure.evaluate((img) => img.decode());
    assert(await figure.evaluate((img) => img.naturalWidth > 0), `${chapter} still failed to load`);
  }
  await page.evaluate(() => scrollTo(0, 0));
}

async function seekChapter(page, chapter) {
  await page.evaluate((id) => {
    const section = document.getElementById(id);
    const top = section.getBoundingClientRect().top + scrollY;
    const stage = document.querySelector("[data-story-stage]");
    const threshold = Math.max(112, Number.parseFloat(getComputedStyle(stage).top) || 112) + Math.min(160, innerHeight * 0.16);
    scrollTo({ top: top + section.offsetHeight * 0.42 - threshold, behavior: "instant" });
  }, chapter);
  await page.waitForTimeout(800);
}

async function seekStoryProgress(page, progress) {
  await page.waitForFunction(() => Boolean(document.querySelector("[data-story]")?.getAttribute("data-story-scroll-stops")));
  await page.evaluate((target) => {
    const root = document.querySelector("[data-story]");
    const stops = JSON.parse(root.getAttribute("data-story-scroll-stops"));
    const index = stops.findIndex((stop, position) => position < stops.length - 1 && target >= stop.progress && target <= stops[position + 1].progress);
    if (index < 0) throw new Error(`No measured scroll interval for progress ${target}`);
    const start = stops[index];
    const end = stops[index + 1];
    const fraction = (target - start.progress) / (end.progress - start.progress);
    scrollTo({ top: start.scrollY + (end.scrollY - start.scrollY) * fraction, behavior: "instant" });
  }, progress);
  if (progress > 0.005) await waitForSettledScene(page);
}

async function waitForSettledScene(page, requireCurrentPose = true) {
  await page.evaluate(() => { delete globalThis.__landingSettleProbe; });
  await page.waitForFunction((requireCurrentPose) => {
    const root = document.querySelector("[data-story]");
    const canvas = root?.querySelector(requireCurrentPose ? "[data-narrative-canvas][data-ready='true']" : "[data-narrative-canvas]");
    if (!canvas) return false;
    const rendered = Number(canvas.getAttribute("data-scene-progress"));
    const frames = Number(canvas.getAttribute("data-render-frames"));
    if (requireCurrentPose) {
      const stops = JSON.parse(root.getAttribute("data-story-scroll-stops"));
      const index = stops.findIndex((stop, position) => position < stops.length - 1 && scrollY >= stop.scrollY && scrollY <= stops[position + 1].scrollY);
      if (index < 0) return false;
      const start = stops[index];
      const end = stops[index + 1];
      const expected = start.progress + (end.progress - start.progress) * (scrollY - start.scrollY) / (end.scrollY - start.scrollY);
      if (Math.abs(rendered - expected) > 0.000002) {
        delete globalThis.__landingSettleProbe;
        return false;
      }
    }
    const previous = globalThis.__landingSettleProbe;
    if (!previous || previous.frames !== frames || Math.abs(previous.progress - rendered) > 0.000002) {
      globalThis.__landingSettleProbe = { frames, progress: rendered, time: performance.now() };
      return false;
    }
    return performance.now() - previous.time >= 150;
  }, requireCurrentPose, { timeout: 15000 });
}

async function openingState(page) {
  return page.locator("[data-story]").evaluate((root) => {
    const aerial = root.querySelector("[data-story-aerial]");
    const image = aerial?.querySelector("img");
    const stage = root.querySelector("[data-story-stage]");
    const rect = root.querySelector("[data-story-visual]").getBoundingClientRect();
    return {
      photoOpacity: Number(root.getAttribute("data-photo-opacity") ?? Number.NaN),
      scrollY,
      renderedProgress: Number(root.querySelector("[data-narrative-canvas]")?.getAttribute("data-scene-progress") ?? Number.NaN),
      scrollStops: JSON.parse(root.getAttribute("data-story-scroll-stops") ?? "null"),
      selectionProgress: Number(root.getAttribute("data-selection-progress") ?? Number.NaN),
      extractionProgress: Number(root.getAttribute("data-extraction-progress") ?? Number.NaN),
      architectureProgress: Number(root.getAttribute("data-architecture-progress") ?? Number.NaN),
      actualPhotoOpacity: aerial ? Number(getComputedStyle(aerial).opacity) : 0,
      photoPixelsReady: Boolean(image?.complete && image.naturalWidth > 0),
      sceneReady: stage.getAttribute("data-scene-ready") === "true",
      stage: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  });
}

async function initialOpeningGeometry(page) {
  return page.locator("[data-story]").evaluate((root) => Object.fromEntries([
    ["image", "[data-story-aerial] img"], ["visual", "[data-story-visual]"], ["opening", "[data-story-opening]"],
  ].map(([name, selector]) => {
    const rect = root.querySelector(selector).getBoundingClientRect();
    return [name, { x: rect.x, y: rect.y, width: rect.width, height: rect.height }];
  })));
}

async function screenshot(page, name) {
  const path = resolve(evidence, `${name}.png`);
  await page.screenshot({ path, animations: "disabled" });
  report.screenshots.push(path);
}

async function assertStoryCue(page) {
  const cue = page.locator("[data-story-cue]");
  await cue.waitFor({ state: "visible" });
  assert.equal(await cue.getAttribute("href"), "#place", "Hero cue must link to the first story chapter");
  const geometry = await cue.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { width: innerWidth, height: innerHeight, top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left, text: element.textContent.trim() };
  });
  report.heroCues.push(geometry);
  assert(geometry.text.length > 0, "Hero cue must expose next-story content");
  const explicitLabel = await cue.getAttribute("aria-label");
  assert(explicitLabel === null || explicitLabel.replace(/\s+/g, " ").trim().toLowerCase().includes(geometry.text.replace(/\s+/g, " ").trim().toLowerCase()),
    "Hero cue's accessible name must include its visible text");
  assert(geometry.top >= 0 && geometry.left >= 0 && geometry.bottom <= geometry.height && geometry.right <= geometry.width,
    `Next-story cue must fit in the first viewport: ${JSON.stringify(geometry)}`);
}

async function canvasPixels(page, chapter) {
  const canvas = page.locator("[data-story] canvas");
  await canvas.waitFor({ state: "visible" });
  const png = await canvas.screenshot({ animations: "disabled" });
  const { data, info } = await sharp(png).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const colors = new Set();
  for (let offset = 0; offset < data.length; offset += 4 * 41) {
    if (data[offset + 3] > 0) colors.add(`${data[offset] >> 3},${data[offset + 1] >> 3},${data[offset + 2] >> 3}`);
  }
  assert(colors.size > 12, `Canvas ${chapter} is blank or lacks visible geometry (${colors.size} quantized colors)`);
  return { chapter, width: info.width, height: info.height, colors: colors.size, hash: createHash("sha256").update(data).digest("hex") };
}

async function resources(page) {
  return page.evaluate(() => {
    const entries = performance.getEntriesByType("resource").map((entry) => ({
      path: new URL(entry.name).pathname,
      transferBytes: entry.transferSize,
      encodedBytes: entry.encodedBodySize,
      decodedBytes: entry.decodedBodySize,
      initiator: entry.initiatorType,
    }));
    const navigation = performance.getEntriesByType("navigation")[0];
    return {
      transferBytes: entries.reduce((sum, entry) => sum + entry.transferBytes, navigation?.transferSize ?? 0),
      metrics: globalThis.__landingMetrics,
      entries,
    };
  });
}
