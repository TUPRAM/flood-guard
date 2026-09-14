import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const require = createRequire(import.meta.url);
const sharp = require(require.resolve("sharp", { paths: [dirname(require.resolve("next/package.json"))] }));
const base = process.env.FLOODGUARD_STYLE_URL ?? "http://127.0.0.1:4310";
const evidence = resolve(process.env.FLOODGUARD_STYLE_EVIDENCE ?? "test-results/landing-style-2026-09-12/after");
const baseline = resolve(process.env.FLOODGUARD_STYLE_BASELINE ?? "test-results/landing-style-2026-09-12/before");
const arguments_ = process.argv.slice(2);
if (arguments_.includes("--help")) {
  console.log("Usage: node scripts/landing-style-smoke.mjs [--desktop-only] [case names]\nFLOODGUARD_STYLE_URL selects the already-running site. FLOODGUARD_STYLE_BASELINE selects a directory containing baseline.json. Mobile comparisons require the same browser version, viewport, and development/production environment. The original baseline defaults to development; custom manifests must declare environment and may map captures to archived image paths. Use --desktop-only against production when only the development baseline is available. No tolerance or PWA masking is applied.");
  process.exit(0);
}
const desktopOnly = arguments_.includes("--desktop-only");
const requested = new Set(arguments_.filter((value) => !value.startsWith("--")));
assert(arguments_.every((value) => !value.startsWith("--") || value === "--desktop-only"), "Unknown styling QA option; use --help");
assert(!desktopOnly || [...requested].every((value) => !value.startsWith("mobile-")), "--desktop-only cannot select mobile cases");
let baselineCaptures = {};
const hash = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
const sourcePaths = ["src/components/landing/landing-page.tsx", "src/components/landing/landing.module.css", "src/components/landing/landing-nav.client.tsx", "src/components/landing/narrative-experience.client.tsx"];
const sources = () => Object.fromEntries(sourcePaths.map((path) => [path, hash(resolve(path))]));
const report = { result: "STARTED", startedAt: new Date().toISOString(), base, sourceBefore: sources(), cases: [], captures: [], measurements: [], mobileComparisons: [], accessibility: [], scope: "Desktop-only styling, scene framing and native scrollbar behavior; unchanged mobile and automatic fallbacks. Existing dev server only: this script never starts/stops servers or builds, submits data, or requests geolocation." };
mkdirSync(evidence, { recursive: true });
const reportPath = resolve(evidence, "landing-style-smoke.json");
const save = () => writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
save();
// Playwright normally suppresses native scrollbars; these screenshots must show them.
const browser = await chromium.launch({ executablePath: process.env.FLOODGUARD_BROWSER_EXECUTABLE, ...(process.env.FLOODGUARD_BROWSER_EXECUTABLE ? {} : { channel: "chrome" }), headless: true, ignoreDefaultArgs: ["--hide-scrollbars"] });
report.browser = browser.version();
try {
  for (const viewport of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    await run(`desktop-${viewport.width}`, viewport, async (page) => {
      await enhanced(page);
      const initial = await hero(page);
      report.measurements.push({ name: `hero-${viewport.width}`, ...initial });
      await capture(page, `hero-${viewport.width}`);
      const original = await page.locator("[data-desktop-canvas] canvas").elementHandle();
      await seek(page, .20);
      const full = await framing(page);
      for (const edge of ["left", "right", "top", "bottom"]) assertNear(full.padding[edge], 24, `Full scene ${edge} padding`);
      assert(await original.evaluate((node) => node === document.querySelector("[data-desktop-canvas] canvas") && node.isConnected), "Styling must retain one scene canvas");
      report.measurements.push({ name: `full-${viewport.width}`, ...full });
      await capture(page, `full-${viewport.width}`);
      await nonblankCanvas(page);
      await scrollbar(page, viewport.width);
      await contrast(page, viewport.width);
      if (viewport.width === 1366) await resizeScrollbar(page);
    });
  }
  await run("legacy-static-preference", { width: 1366, height: 768 }, async (page) => { await enhanced(page); await hero(page); }, async (page) => {
    await page.addInitScript(() => localStorage.setItem("floodguard:landing-motion:v1", "static"));
  });
  await run("reduced-motion", { width: 1366, height: 768 }, async (page) => {
    assert.equal(await page.locator("[data-story]").getAttribute("data-render-mode"), "static");
    assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
    assert.equal(await page.locator("[data-chapter]").count(), 8);
    await hero(page, false);
    await capture(page, "reduced-motion");
  }, null, { reducedMotion: "reduce" });
  await run("webgl-unavailable", { width: 1366, height: 768 }, async (page) => {
    await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "static");
    assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
    assert.equal(await page.locator("[data-chapter]").count(), 8);
    await capture(page, "webgl-unavailable");
  }, async (page) => {
    await page.addInitScript(() => {
      const getContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type, ...args) { return type === "webgl" || type === "webgl2" || type === "experimental-webgl" ? null : getContext.call(this, type, ...args); };
    });
  });
  await run("no-javascript", { width: 1366, height: 768 }, async (page) => {
    assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
    assert.equal(await page.locator("[data-chapter]").count(), 8);
    await hero(page, false);
    await capture(page, "no-javascript");
  }, null, { javaScriptEnabled: false });
  await browser.close();
  const mobileSelected = !desktopOnly && (!requested.size || [...requested].some((value) => value.startsWith("mobile-")));
  if (mobileSelected) {
  const mobileBrowser = await chromium.launch({ headless: true, executablePath: process.env.FLOODGUARD_STYLE_BASELINE_EXECUTABLE });
  try {
    const old = JSON.parse(readFileSync(resolve(baseline, "baseline.json"), "utf8"));
    baselineCaptures = old.captures ?? {};
    const baselineEnvironment = old.environment ?? "development";
    assert(["development", "production"].includes(baselineEnvironment), "Baseline environment must be development or production");
    report.mobileBaseline = { directory: baseline, sha256: hash(resolve(baseline, "baseline.json")), environment: baselineEnvironment, browser: old.browser };
    assert.equal(mobileBrowser.version(), old.browser, "Mobile screenshot preservation must use the baseline browser");
    for (const width of [390, 320]) {
      if (requested.size && !requested.has(`mobile-${width}`)) continue;
      const context = await mobileBrowser.newContext({ viewport: { width, height: 844 }, serviceWorkers: "block" });
      const page = await context.newPage(), errors = [], requests = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => requests.push(new URL(request.url()).pathname));
      try {
        await page.goto(base, { waitUntil: "networkidle" });
        await page.locator("main[data-landing]").waitFor();
        await page.evaluate(() => document.fonts.ready);
        const environment = await page.locator("[data-pwa-availability]").count() ? "production" : "development";
        assert.equal(environment, baselineEnvironment, "Unsupported cross-environment mobile comparison: production includes the PWA status band, development does not. Use a matching production baseline or --desktop-only; do not normalize away the status band.");
        assert.equal(await page.locator("[data-story]").getAttribute("data-render-mode"), "static");
        assert.equal(await page.locator("[data-desktop-canvas]").count(), 0);
        await page.locator("[data-story-aerial] img").evaluate((img) => img.decode());
        await capture(page, `mobile-${width}-hero`);
        await compare(`mobile-${width}-hero`);
        await page.locator("#studio").scrollIntoViewIfNeeded();
        await page.locator("#studio img").evaluate((img) => img.decode());
        await capture(page, `mobile-${width}-studio`);
        await compare(`mobile-${width}-studio`);
        assert.deepEqual(errors, []);
        assert(!requests.includes("/landing/topography.webp"), "Desktop bitmap should not add a mobile resource request");
        assert(!requests.includes("/floodguard-logo.png"), "Desktop Public logo should not add a hidden mobile image request");
        report.cases.push({ name: `mobile-${width}`, result: "PASS", errors, requests, browser: mobileBrowser.version() });
      } catch (error) {
        report.cases.push({ name: `mobile-${width}`, result: "FAIL", error: error.message, errors, requests });
      } finally { await context.close(); save(); }
    }
  } finally { await mobileBrowser.close(); }
  }
  report.sourceAfter = sources();
  assert.deepEqual(report.sourceAfter, report.sourceBefore, "Application sources changed during this QA run; evidence is not a frozen styling check");
  assert(report.cases.length > 0, "No matching styling QA cases");
  report.result = report.cases.every(({ result }) => result === "PASS") ? "PASS" : "FAIL";
} catch (error) {
  report.result = "FAIL";
  report.failure = error.stack ?? error.message;
} finally { await browser.close(); report.completedAt = new Date().toISOString(); save(); }
console.log(JSON.stringify({ result: report.result, cases: report.cases, reportPath }, null, 2));
if (report.result !== "PASS") process.exitCode = 1;

async function run(name, viewport, check, prepare, options = {}) {
  if (requested.size && !requested.has(name)) return;
  const context = await browser.newContext({ viewport, serviceWorkers: "block", ...options });
  const page = await context.newPage(), errors = [], consoleErrors = [], writes = [], external = [];
  page.setDefaultTimeout(20000);
  page.on("pageerror", (error) => errors.push(error.stack ?? error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  page.on("request", (request) => { if (!/^(GET|HEAD|OPTIONS)$/.test(request.method())) writes.push(`${request.method()} ${request.url()}`); if (/^https?:/.test(request.url()) && new URL(request.url()).origin !== new URL(base).origin) external.push(request.url()); });
  try {
    await page.addInitScript(() => {
      globalThis.__styleGeolocationCalls = 0;
      for (const key of ["getCurrentPosition", "watchPosition"]) Object.defineProperty(navigator.geolocation, key, { configurable: true, value: () => { globalThis.__styleGeolocationCalls += 1; } });
    });
    await prepare?.(page);
    await page.goto(base, { waitUntil: "networkidle" });
    await page.locator("main[data-landing]").waitFor();
    await page.evaluate(() => document.fonts.ready);
    await check(page);
    assert.deepEqual(errors, [], "No uncaught browser errors");
    assert.deepEqual(consoleErrors, [], "No browser console errors");
    assert.deepEqual(writes, [], "Styling must not create operational writes");
    assert.deepEqual(external, [], "Landing styling must remain local");
    assert.equal(await page.evaluate(() => globalThis.__styleGeolocationCalls ?? 0), 0);
    report.cases.push({ name, result: "PASS", errors, consoleErrors, writes, external });
  } catch (error) {
    await capture(page, `${name}-failure`).catch(() => {});
    report.cases.push({ name, result: "FAIL", error: error.stack ?? error.message, errors, consoleErrors, writes, external });
  } finally { await context.close(); save(); console.log(`landing style ${name}: ${report.cases.at(-1)?.result}`); }
}

async function enhanced(page) {
  await page.locator("[data-story][data-render-mode='enhanced'][data-story-variant='desktop-world']").waitFor();
  await page.locator("[data-desktop-canvas][data-ready='true']").waitFor();
  assert.equal(await page.locator("[data-story] canvas").count(), 1);
}

async function hero(page, checkFrame = true) {
  const value = await page.evaluate(() => {
    const root = document.querySelector("main[data-landing]"), hero = document.querySelector("#hero"), header = root.querySelector("header");
    const walker = document.createTreeWalker(hero, NodeFilter.SHOW_TEXT), text = [], lines = [];
    while (walker.nextNode()) {
      const node = walker.currentNode, parent = node.parentElement;
      if (!node.textContent.trim() || getComputedStyle(parent).visibility !== "visible") continue;
      const range = document.createRange(); range.selectNodeContents(node);
      const rects = [...range.getClientRects()].filter((rect) => rect.width > 3 && rect.height > 3);
      if (!rects.length || parent.getBoundingClientRect().width <= 3 || parent.getBoundingClientRect().height <= 3) continue;
      text.push(node.textContent.trim()); lines.push(...rects.map((rect) => Math.round(rect.top)));
    }
    const brandAssets = [...header.querySelectorAll("img,span")].filter((node) => node.getBoundingClientRect().width > 0 && getComputedStyle(node).visibility === "visible").flatMap((node) => [node.currentSrc ?? "", getComputedStyle(node).backgroundImage]).filter((value) => value.includes("floodguard-logo"));
    const backgrounds = [root, hero, ...hero.querySelectorAll("*")].flatMap((node) => [getComputedStyle(node).backgroundImage, getComputedStyle(node, "::before").backgroundImage, getComputedStyle(node, "::after").backgroundImage]).filter((value) => value !== "none");
    const visibleMotionButtons = [...document.querySelectorAll("button")].filter((node) => /without animation|enable animation/i.test(node.textContent) && node.getBoundingClientRect().width > 0 && getComputedStyle(node).visibility === "visible").map((node) => node.textContent.trim());
    const loadedAssets = performance.getEntriesByType("resource").map(({ name }) => new URL(name).pathname);
    return { scrollY, text: text.join(" "), lineTops: [...new Set(lines)], brandAssets, loadedAssets, backgrounds, visibleMotionButtons, ink: getComputedStyle(root).color, primary: getComputedStyle(header.querySelector("[class*='demoButton']")).backgroundColor, header: header.getBoundingClientRect().toJSON() };
  });
  assert.equal(value.scrollY, 0);
  assert.equal(value.text, "When water rises, every connection matters.", "Desktop hero must contain only the exact requested headline");
  assert.equal(value.lineTops.length, 2, "Desktop headline must occupy exactly two lines");
  assert(value.lineTops[0] > value.header.bottom, "Headline must clear the fixed header");
  assert(value.brandAssets.length > 0, "Desktop header must reuse the actual Public logo asset");
  assert(value.loadedAssets.includes("/floodguard-logo.png"), "Desktop Public logo must be actually requested and rendered");
  assert(value.backgrounds.some((value) => /topo/i.test(value) && !/\.svg/.test(value)), "Desktop backdrop must use the supplied topo bitmap");
  assert.deepEqual(value.visibleMotionButtons, [], "Desktop static-motion toggle must be removed");
  assert.equal(value.ink, "rgb(15, 23, 42)", "Landing text should reuse Public neutral900");
  assert.equal(value.primary, "rgb(15, 76, 129)", "Landing primary action should reuse Public primary");
  if (checkFrame) {
    value.frame = await framing(page);
    for (const edge of ["left", "right", "bottom"]) assertNear(value.frame.padding[edge], 24, `Initial scene ${edge} padding`);
  }
  return value;
}

async function framing(page) {
  return page.evaluate(() => {
    const visual = document.querySelector("[data-story-visual]"), rect = visual.getBoundingClientRect(), clip = getComputedStyle(visual).clipPath;
    const parts = clip.match(/^inset\(([^)]+)\)$/)?.[1].split(/\s+/) ?? [];
    const px = (part, size) => part?.endsWith("%") ? parseFloat(part) * size / 100 : parseFloat(part ?? "0");
    const inset = [px(parts[0], rect.height), px(parts[1] ?? parts[0], rect.width), px(parts[2] ?? parts[0], rect.height), px(parts[3] ?? parts[1] ?? parts[0], rect.width)];
    return { innerWidth, clientWidth: document.documentElement.clientWidth, innerHeight, rect: rect.toJSON(), clip, padding: { top: rect.top + inset[0], right: document.documentElement.clientWidth - rect.right + inset[1], bottom: innerHeight - rect.bottom + inset[2], left: rect.left + inset[3] } };
  });
}

async function seek(page, progress) {
  await page.evaluate((progress) => {
    const stops = JSON.parse(document.querySelector("[data-story]").getAttribute("data-story-scroll-stops"));
    const index = stops.findIndex((stop, i) => i < stops.length - 1 && progress >= stop.progress && progress <= stops[i + 1].progress);
    const a = stops[index], b = stops[index + 1], y = a.scrollY + (progress - a.progress) / (b.progress - a.progress) * (b.scrollY - a.scrollY);
    scrollTo(0, y);
  }, progress);
  await page.waitForFunction(() => Number(document.querySelector("[data-story]").getAttribute("data-desktop-cover-progress")) === 1 && document.querySelector("[data-desktop-canvas]")?.getAttribute("data-ready") === "true");
  await page.waitForTimeout(600);
}

async function scrollbar(page, width) {
  const sample = () => page.evaluate(() => ({ scrolling: document.documentElement.getAttribute("data-landing-scrolling"), color: getComputedStyle(document.documentElement).scrollbarColor, width: getComputedStyle(document.documentElement).scrollbarWidth, innerWidth, clientWidth: document.documentElement.clientWidth }));
  await page.mouse.move(100, 200);
  await page.waitForTimeout(1600);
  const idle = await sample();
  await capture(page, `scrollbar-${width}-idle`);
  await page.mouse.wheel(0, 100);
  await page.waitForFunction(() => document.documentElement.getAttribute("data-landing-scrolling") === "true");
  await page.waitForTimeout(250);
  const active = await sample();
  await capture(page, `scrollbar-${width}-active`);
  assert.notEqual(active.color, idle.color, "Native scrollbar must change from idle to active colors");
  await page.waitForTimeout(1600);
  const settled = await sample();
  assert.equal(settled.scrolling, "false");
  assert.equal(settled.color, idle.color, "Native scrollbar must fade back to its idle colors");
  await page.mouse.move(width - 2, 300);
  await page.waitForTimeout(300);
  const hover = await sample();
  await capture(page, `scrollbar-${width}-hover`);
  assert.notEqual(hover.color, idle.color, "Pointer at native scrollbar edge must reveal it");
  const drag = await page.evaluate(() => {
    const html = document.documentElement, track = innerHeight - 16, thumb = Math.max(24, track * innerHeight / html.scrollHeight);
    return { before: scrollY, x: html.clientWidth + (innerWidth - html.clientWidth) / 2, y: 8 + (track - thumb) * scrollY / (html.scrollHeight - innerHeight) + thumb / 2 };
  });
  await page.mouse.move(drag.x, drag.y);
  await page.mouse.down();
  await page.mouse.move(drag.x, drag.y + 50, { steps: 8 });
  await page.waitForTimeout(1200);
  const held = await sample();
  drag.after = await page.evaluate(() => scrollY);
  await page.mouse.up();
  assert(drag.after > drag.before + 5, "The real native scrollbar thumb must remain draggable");
  assert.notEqual(held.color, idle.color, "Scrollbar must remain visible while the pointer holds its thumb");
  await page.mouse.move(100, 200);
  await page.waitForTimeout(1600);
  const beforeKeyboard = await page.evaluate(() => scrollY);
  await page.keyboard.press("PageDown");
  await page.waitForFunction(() => document.documentElement.getAttribute("data-landing-scrolling") === "true");
  await page.waitForTimeout(250);
  const keyboard = await sample();
  assert(await page.evaluate(() => scrollY) > beforeKeyboard, "Keyboard scrolling must remain available");
  assert.notEqual(keyboard.color, idle.color, "Keyboard scrolling must reveal the native scrollbar");
  report.measurements.push({ name: `scrollbar-${width}`, idle, active, settled, hover, drag, held, keyboard });
}

async function capture(page, name) { const path = resolve(evidence, `${name}.png`); await page.screenshot({ path }); report.captures.push({ path, sha256: hash(path) }); }
async function resizeScrollbar(page) {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.waitForFunction(() => document.querySelector("[data-story]")?.getAttribute("data-render-mode") === "static");
  await page.mouse.move(100, 200);
  await page.setViewportSize({ width: 1366, height: 768 });
  await enhanced(page);
  await page.waitForFunction(() => document.documentElement.getAttribute("data-landing-scrolling") === "false", null, { timeout: 5000 });
  await page.waitForTimeout(400);
  const value = await page.evaluate(() => ({ scrolling: document.documentElement.getAttribute("data-landing-scrolling"), color: getComputedStyle(document.documentElement).scrollbarColor }));
  assert.match(value.color, /rgba\(0, 0, 0, 0\)/, "Resizing back to desktop must restore the transparent idle native thumb");
  report.measurements.push({ name: "scrollbar-resize-desktop-idle", ...value });
}
async function contrast(page, width) {
  const values = await page.locator("#public [class*='callout']").evaluate((node) => ({ foreground: getComputedStyle(node).color, background: getComputedStyle(node.closest("[data-chapter]"), "::before").backgroundColor, fontSize: getComputedStyle(node).fontSize }));
  const luminance = (css) => { const channels = css.match(/[\d.]+/g).slice(0, 3).map(Number).map((n) => n / 255).map((n) => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4); return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722; };
  const foreground = luminance(values.foreground), background = luminance(values.background);
  const ratio = (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05);
  report.measurements.push({ name: `small-callout-contrast-${width}`, ...values, ratio });
  assert(ratio >= 4.5, `Small callout contrast must meet4.5:1, measured${ratio}`);
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  report.accessibility.push({ viewportWidth: width, violations: axe.violations, incomplete: axe.incomplete });
  assert.deepEqual(axe.violations, [], "Automated accessibility violations require investigation; incomplete image-background cases remain separate");
}
async function nonblankCanvas(page) { const buffer = await page.locator("[data-desktop-canvas] canvas").screenshot(); const stats = await sharp(buffer).stats(); assert(stats.channels.slice(0, 3).some(({ stdev }) => stdev > 8), "Canvas pixels must contain the actual varied scene"); }
function assertNear(actual, expected, label) { assert(Math.abs(actual - expected) <= 1, `${label}: expected${expected}px, observed${actual}px`); }
async function compare(name) {
  const oldPath = resolve(baseline, baselineCaptures[name] ?? `${name}.png`), newPath = resolve(evidence, `${name}.png`);
  const a = await sharp(oldPath).removeAlpha().raw().toBuffer({ resolveWithObject: true }), b = await sharp(newPath).removeAlpha().raw().toBuffer({ resolveWithObject: true });
  assert.deepEqual(a.info, b.info);
  let difference = 0, significant = 0;
  for (let i = 0; i < a.data.length; i += 3) { let max = 0; for (let c = 0; c < 3; c++) { const delta = Math.abs(a.data[i + c] - b.data[i + c]); difference += delta; max = Math.max(max, delta); } if (max > 24) significant += 1; }
  const result = { name, baselineSha256: hash(oldPath), currentSha256: hash(newPath), meanRGBDifference: difference / a.data.length, significantPixelFraction: significant / (a.data.length / 3) };
  report.mobileComparisons.push(result);
  assert(result.meanRGBDifference <= 1 && result.significantPixelFraction <= .01, `Mobile appearance changed: ${JSON.stringify(result)}`);
}
