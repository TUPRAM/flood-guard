import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const args = Object.fromEntries(process.argv.slice(2).filter((value) => value.startsWith("--")).map((value) => {
  const [name, ...parts] = value.slice(2).split("=");
  return [name, parts.join("=")];
}));
const baseUrl = (args["base-url"] || "http://127.0.0.1:3100").replace(/\/$/, "");
const output = resolve(args.output || "../../docs/visual-qa/landing-v1/browser-acceptance");
const reviewGate = args["review-gate"] !== "off";
mkdirSync(output, { recursive: true });
const browser = await launchFloodGuardBrowser();
const report = {
  startedAt: new Date().toISOString(), baseUrl, reviewGate, browser: browser.version(),
  environment: "Local Chromium browser; new contexts, service workers blocked; no field-performance claim.",
  checks: [], measurements: [], networkMutations: [], geolocationCalls: 0, browserErrors: [],
  limitations: ["Offline/service-worker behavior is checked separately.", "Root-font scaling records which text actually scales; fixed-pixel text is not certified as 200% text zoom by that probe."],
};
let currentPage;
const sceneIds = ["H-01", "S1-01", "S2-01", "S3A-01", "S3B-OBS", "S3B-01", "S4-01", "S4-PUBLIC", "S4-END"];
const anchors = { "S1-01": "story-everyday", "S2-01": "story-conditions", "S3A-01": "story-connections", "S3B-OBS": "scene-s3b-obs", "S3B-01": "scene-s3b-01", "S4-01": "story-next", "S4-PUBLIC": "scene-s4-public", "S4-END": "scene-s4-end" };
const main = (page) => page.locator("main[data-fg-landing]");
const active = (page) => page.locator('[data-fg-scene]:not([data-fg-scene="H-01"])');
const delay = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

async function createContext(options = {}) {
  const context = await browser.newContext({ viewport: { width: 1672, height: 941 }, serviceWorkers: "block", reducedMotion: "no-preference", ...options });
  context.on("request", (request) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) report.networkMutations.push({ method: request.method(), url: request.url() });
  });
  await context.addInitScript(() => {
    window.__fgGeoCalls = 0;
    for (const method of ["getCurrentPosition", "watchPosition"]) {
      Object.defineProperty(navigator.geolocation, method, { configurable: true, value: () => { window.__fgGeoCalls++; throw new Error("Landing must not request geolocation."); } });
    }
    window.__fgShifts = [];
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__fgShifts.push({ value: entry.value, time: entry.startTime });
    }).observe({ type: "layout-shift", buffered: true });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(60_000);
  page.on("pageerror", (error) => report.browserErrors.push({ message: error.message, url: page.url() }));
  currentPage = page;
  return { context, page };
}

async function closeContext(context, page) {
  report.geolocationCalls += await page.evaluate(() => window.__fgGeoCalls || 0).catch(() => 0);
  await context.close();
}

async function check(name, run) {
  if (args.only && !name.includes(args.only)) return;
  const started = Date.now();
  try {
    const details = await run();
    report.checks.push({ name, status: "passed", durationMs: Date.now() - started, details });
    console.log(`PASS ${name}`);
  } catch (error) {
    const capture = resolve(output, `${name.replace(/[^a-z0-9-]/gi, "-")}-failure.png`);
    const state = currentPage && !currentPage.isClosed() ? await currentPage.evaluate(() => ({
      url: location.href, viewport: [innerWidth, innerHeight], scroll: scrollY,
      mode: document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode"),
      scenes: [...document.querySelectorAll("[data-fg-scene]")].map((element) => ({ id: element.getAttribute("data-fg-scene"), phase: element.getAttribute("data-fg-phase"), rect: element.getBoundingClientRect().toJSON() })),
      text: document.body.innerText.slice(0, 1800),
    })).catch(() => null) : null;
    const captured = await currentPage?.screenshot({ path: capture, fullPage: false }).then(() => true, () => false);
    report.checks.push({ name, status: "failed", durationMs: Date.now() - started, error: error.stack || String(error), capture: captured ? capture : null, state });
    console.log(`FAIL ${name}: ${error.message}`);
  } finally {
    writeFileSync(resolve(output, "browser-results.json"), JSON.stringify(report, null, 2));
  }
}

async function open(page, path = "/", mode = "enhanced") {
  await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
  await main(page).waitFor({ state: "visible" });
  if (mode) await page.waitForFunction((value) => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === value, mode);
}

async function settle(page, id) {
  await page.waitForFunction((expected) => {
    const frame = document.querySelector('[data-fg-scene]:not([data-fg-scene="H-01"])');
    return frame?.getAttribute("data-fg-scene") === expected && frame.getAttribute("data-fg-settled") === "true";
  }, id);
  assert.equal(await active(page).count(), 1, "Enhanced mode must contain one interactive story frame.");
}

async function jump(page, id) {
  await page.locator(`#${anchors[id]}`).evaluate((element) => element.scrollIntoView({ block: "start", behavior: "instant" }));
  await settle(page, id);
}

async function waitVisibleArt(page, id) {
  await page.waitForFunction((sceneId) => {
    const frame = document.querySelector(`[data-fg-scene="${sceneId}"]`);
    const images = [...(frame?.querySelectorAll("img") || [])].filter((image) => {
      const box = image.getBoundingClientRect();
      return box.width && box.bottom > 0 && box.top < innerHeight && !image.closest("noscript");
    });
    return images.length > 0 && images.every((image) => image.currentSrc && image.complete && image.naturalWidth > 0);
  }, id);
}

async function assertFits(page) {
  const layout = await page.evaluate(() => {
    const visible = [...document.querySelectorAll("main[data-fg-landing] h1, main[data-fg-landing] h2, main[data-fg-landing] h3, main[data-fg-landing] a, main[data-fg-landing] button, main[data-fg-landing] summary")].filter((element) => {
      const style = getComputedStyle(element);
      return element.getClientRects().length && style.display !== "none" && style.visibility !== "hidden" && !element.closest("dialog:not([open])");
    });
    return {
      width: innerWidth, documentWidth: document.documentElement.scrollWidth,
      clipped: visible.filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 2 && (rect.left < -2 || rect.right > innerWidth + 2 || element.scrollWidth > element.clientWidth + 3);
      }).map((element) => ({ text: element.textContent?.trim().slice(0, 100), tag: element.tagName, width: element.clientWidth, scrollWidth: element.scrollWidth, rect: element.getBoundingClientRect().toJSON() })),
    };
  });
  assert.ok(layout.documentWidth <= layout.width + 1, `Horizontal overflow: ${JSON.stringify(layout)}`);
  assert.equal(layout.clipped.length, 0, `Clipped text/control: ${JSON.stringify(layout.clipped)}`);
  return layout;
}

try {
  await check("native-chapters-refresh-history", async () => {
    const { context, page } = await createContext();
    await open(page);
    await page.evaluate(async () => { await document.fonts.ready; await document.querySelector('[data-fg-scene="H-01"] img[data-fg-plate-image]')?.decode().catch(() => {}); });
    await page.screenshot({ path: resolve(output, "normal-hero-1672x941.png") });
    for (const href of ["/command/", "/public/", "/studio/"]) assert.ok(await page.locator(`a[href="${href}"]`).count());
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "The story" }).click();
    await settle(page, "S1-01");
    assert.equal(new URL(page.url()).hash, "#story-everyday");
    await active(page).getByRole("link", { name: "03 Connections affected" }).click();
    await settle(page, "S3A-01");
    await page.reload({ waitUntil: "domcontentloaded" });
    await settle(page, "S3A-01");
    await active(page).getByRole("link", { name: "04 Next steps" }).click();
    await settle(page, "S4-01");
    await page.goBack();
    await settle(page, "S3A-01");
    await page.goForward();
    await settle(page, "S4-01");
    await assertFits(page);
    await closeContext(context, page);
  });

  await check("forward-reverse-scroll-and-shared-w2-node", async () => {
    const { context, page } = await createContext();
    await open(page);
    const visited = [];
    for (const id of sceneIds.slice(1)) {
      await jump(page, id);
      const expectedChapter = id.startsWith("S1") ? "01" : id.startsWith("S2") ? "02" : id.startsWith("S3") ? "03" : "04";
      assert.match(await active(page).locator('[aria-current="step"]').innerText(), new RegExp(`^${expectedChapter}`));
      const state = await active(page).locator("figure").getAttribute("data-fg-water");
      assert.equal(state, id === "S1-01" ? "W0" : id === "S2-01" ? "W1" : "W2");
      if (id === "S3A-01") await active(page).locator("img[data-fg-plate-image]").evaluate((image) => { window.__fgW2Node = image; window.__fgW2Source = image.currentSrc; });
      if (state === "W2") assert.ok(await active(page).locator("img[data-fg-plate-image]").evaluate((image) => image === window.__fgW2Node && image.currentSrc === window.__fgW2Source), "W2 must retain its actual image node and selected source.");
      visited.push(id);
    }
    for (const id of sceneIds.slice(1).reverse()) { await jump(page, id); visited.push(id); }
    await jump(page, "S3B-01");
    await waitVisibleArt(page, "S3B-01");
    await page.screenshot({ path: resolve(output, "normal-analysis-1672x941.png") });
    await closeContext(context, page);
    return { visited };
  });

  await check("rapid-scroll-cancels-stale-image-decode", async () => {
    const { context, page } = await createContext();
    let w1Requests = 0;
    await context.route("**/landing/floodguard-v1/plates/w1-*.webp", async (route) => { w1Requests++; await delay(1400); await route.continue().catch(() => {}); });
    await open(page);
    await jump(page, "S1-01");
    await page.locator("#story-conditions").evaluate((element) => element.scrollIntoView({ behavior: "instant" }));
    await page.waitForFunction(() => document.querySelector("#story-conditions").getBoundingClientRect().top < innerHeight * .4);
    await delay(100);
    await jump(page, "S3B-01");
    await delay(1900);
    await settle(page, "S3B-01");
    assert.equal(await active(page).locator("figure").getAttribute("data-fg-water"), "W2");
    assert.ok(w1Requests > 0, "The delayed physical-state image request must actually be exercised.");
    await closeContext(context, page);
    return { delayedW1Requests: w1Requests };
  });

  await check("reduced-motion-os-change-and-manual-persistence", async () => {
    const { context, page } = await createContext({ reducedMotion: "reduce" });
    await open(page, "/", "flow");
    await page.waitForFunction(() => document.querySelector("[data-fg-reduced-motion]")?.getAttribute("data-fg-reduced-motion") === "true");
    assert.equal(await page.locator("[data-fg-scene]").count(), 9);
    assert.equal(await main(page).getAttribute("data-fg-reduced-motion"), "true");
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: resolve(output, "reduced-motion-hero-1672x941.png") });
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "enhanced");
    await active(page).getByRole("link", { name: "03 Connections affected" }).click();
    await settle(page, "S3A-01");
    await jump(page, "S3B-01");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
    await waitVisibleArt(page, "S3B-01");
    await page.screenshot({ path: resolve(output, "reduced-motion-analysis-1672x941.png") });
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "enhanced");
    await settle(page, "S3B-01");
    await page.getByRole("button", { name: "Reduce motion", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
    assert.equal(await page.evaluate(() => localStorage.getItem("floodguard:landing-reduced-motion")), "1");
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("button", { name: "Motion reduced", exact: true }).waitFor();
    assert.equal(await main(page).getAttribute("data-fg-mode"), "flow");
    await page.getByRole("button", { name: "Motion reduced", exact: true }).click();
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "enhanced");
    await closeContext(context, page);
  });

  await check("keyboard-observation-dialog-and-native-brief", async () => {
    const { context, page } = await createContext();
    await open(page);
    await jump(page, "S3B-OBS");
    const trigger = active(page).locator("summary").filter({ hasText: "Inspect sample observation" });
    await trigger.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "DEMO-R01 / SAMPLE OBSERVATION" });
    await dialog.waitFor({ state: "visible" });
    assert.match(await dialog.innerText(), /Not verified/);
    assert.match(await dialog.innerText(), /No report is submitted/);
    assert.ok(await dialog.evaluate((element) => element.contains(document.activeElement)));
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    assert.ok(await trigger.evaluate((element) => element === document.activeElement), "Closing the dialog must return focus to its actual trigger.");
    await jump(page, "S4-01");
    const brief = active(page).locator("details").filter({ hasText: "Inspect the review brief" });
    const summary = brief.locator("summary");
    await summary.focus();
    await page.keyboard.press("Enter");
    assert.equal(await brief.evaluate((element) => element.open), true);
    assert.match(await brief.innerText(), /not a verified closure/);
    await page.keyboard.press("Escape");
    assert.equal(await brief.evaluate((element) => element.open), false);
    assert.ok(await summary.evaluate((element) => element === document.activeElement));
    assert.equal(await page.locator('nav[aria-label="Story chapters and steps"]').count(), 1);
    assert.equal(await page.locator('[data-fg-scene]:not([data-fg-scene="H-01"])').count(), 1);
    await closeContext(context, page);
  });

  await check("no-javascript-complete-story-and-local-details", async () => {
    const { context, page } = await createContext({ javaScriptEnabled: false });
    await open(page, "/", null);
    assert.equal(await page.locator("h1").count(), 1);
    for (const id of sceneIds) assert.equal(await page.locator(`[data-fg-scene="${id}"]`).count(), 1);
    for (const id of Object.values(anchors)) assert.equal(await page.locator(`#${id}`).count(), 1);
    await page.goto(`${baseUrl}/#story-next`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("load");
    await page.evaluate(() => document.fonts.ready);
    const brief = page.locator('[data-fg-scene="S4-01"] details').filter({ hasText: "Inspect the review brief" });
    await brief.locator("summary").focus();
    await page.keyboard.press("Enter");
    assert.equal(await brief.getAttribute("open"), "");
    assert.match(await brief.innerText(), /No verification task or rescue request is sent/);
    const decodedFrames = [];
    for (const id of sceneIds) {
      const frame = page.locator(`[data-fg-scene="${id}"]`);
      await frame.evaluate((element) => element.scrollIntoView({ block: "start", behavior: "instant" }));
      const fallbackArt = id === "H-01" ? frame.locator("img[data-fg-plate-image]") : frame.locator("noscript img[data-fg-plate-image]");
      await fallbackArt.evaluate((image) => image.decode());
      assert.ok(await fallbackArt.evaluate((image) => {
        const picture = image.getBoundingClientRect();
        const overlay = image.closest("figure").querySelector("svg").getBoundingClientRect();
        return image.naturalWidth > 0 && Math.abs(picture.x - overlay.x) < 1 && Math.abs(picture.y - overlay.y) < 1 && Math.abs(picture.width - overlay.width) < 1 && Math.abs(picture.height - overlay.height) < 1;
      }), `The native no-JavaScript artwork for ${id} must load and retain the same transform as its SVG.`);
      assert.ok(await frame.locator("img:not([src])").evaluateAll((images) => images.every((image) => {
        const style = getComputedStyle(image);
        return style.visibility === "hidden" || style.display === "none";
      })), `Source-less placeholders for ${id} must not paint broken-image outlines over the native fallback artwork.`);
      for (const portrait of await frame.locator('noscript img[src*="/characters/"]').all()) await portrait.evaluate((image) => image.decode());
      decodedFrames.push(id);
    }
    await page.locator("#story-next").evaluate((element) => element.scrollIntoView({ block: "start", behavior: "instant" }));
    await page.screenshot({ path: resolve(output, "no-javascript-native-brief-1672x941.png") });
    assert.match(await page.locator('[data-fg-scene="S3B-OBS"]').innerText(), /Local example only. No report is submitted./);
    for (const href of ["/public/", "/command/", "/studio/"]) assert.ok(await page.locator(`a[href="${href}"]`).count());
    await closeContext(context, page);
    return { decodedFrames, registeredPlateTransforms: decodedFrames.length };
  });

  await check("requested-water-state-image-failure-fallback", async () => {
    const { context, page } = await createContext();
    await context.route("**/landing/floodguard-v1/plates/w2-*.webp", (route) => route.abort("failed"));
    await open(page);
    await jump(page, "S3A-01");
    await active(page).getByRole("img", { name: /Illustrative flooded neighborhood/ }).waitFor({ state: "visible" });
    assert.match(await active(page).innerText(), /Illustration unavailable/);
    assert.equal(await active(page).locator("figure").getAttribute("data-fg-water"), "W2");
    assert.match(await active(page).innerText(), /The home and clinic remain outside the water/);
    await jump(page, "S4-01");
    assert.match(await active(page).innerText(), /Clinic operating status/);
    await closeContext(context, page);
  });

  await check("delayed-fonts-keep-immediate-promise-and-actions", async () => {
    const { context, page } = await createContext();
    let release;
    const gate = new Promise((done) => { release = done; });
    let delayedFonts = 0;
    await context.route(/\.(?:woff2?|ttf)(?:\?|$)/, async (route) => { delayedFonts++; await gate; await route.continue().catch(() => {}); });
    try {
      await open(page);
      await page.locator('h1').waitFor({ state: "visible" });
      const hero = page.locator('[data-fg-scene="H-01"]');
      assert.match(await hero.locator("h1").innerText(), /See the flood/);
      const action = page.locator("header").getByRole("link", { name: /Planning demo/ });
      assert.equal(await action.getAttribute("href"), "/command/");
      assert.ok(await action.isVisible());
      assert.ok(delayedFonts > 0, "Font requests were actually delayed.");
      release();
      await page.evaluate(() => document.fonts.ready);
      await assertFits(page);
      await closeContext(context, page);
      return { delayedFonts };
    } finally { release(); }
  });

  await check("short-laptop-tablet-and-phone-layout", async () => {
    const layouts = [];
    for (const viewport of [{ width: 1366, height: 700 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 360, height: 800 }]) {
      const { context, page } = await createContext({ viewport });
      await open(page, "/", "flow");
      await page.evaluate(() => document.fonts.ready);
      layouts.push({ viewport, ...await assertFits(page) });
      assert.equal(await page.locator("[data-fg-scene]").count(), 9);
      await page.screenshot({ path: resolve(output, `layout-${viewport.width}x${viewport.height}.png`) });
      if (viewport.width < 600) {
        const chapters = page.locator('[data-fg-scene="S1-01"] nav details');
        await chapters.locator("summary").focus();
        await page.keyboard.press("Enter");
        assert.equal(await chapters.getByRole("link").count(), 4);
        await chapters.getByRole("link", { name: /03.*Connections affected/ }).click();
        assert.equal(new URL(page.url()).hash, "#story-connections");
        const nextFrame = page.locator('[data-fg-scene="S4-01"]');
        await nextFrame.getByRole("button", { name: "Selected for review" }).click();
        const revealedBrief = await nextFrame.locator("details").filter({ hasText: "Inspect the review brief" }).evaluate((element) => ({
          open: element.open, focused: element === document.activeElement,
          top: element.getBoundingClientRect().top, bottom: element.getBoundingClientRect().bottom, viewport: innerHeight,
        }));
        assert.ok(revealedBrief.open && revealedBrief.focused && revealedBrief.top >= 0 && revealedBrief.bottom <= revealedBrief.viewport + 1, `Map-selected brief must be visible and focused: ${JSON.stringify(revealedBrief)}`);
      }
      await closeContext(context, page);
    }
    return layouts;
  });

  await check("200-percent-root-font-layout-probe", async () => {
    const { context, page } = await createContext();
    await open(page);
    await page.evaluate(() => document.fonts.ready);
    const measure = () => page.evaluate(() => ({ root: parseFloat(getComputedStyle(document.documentElement).fontSize), heading: parseFloat(getComputedStyle(document.querySelector("h1")).fontSize), body: parseFloat(getComputedStyle(document.querySelector('[data-fg-scene="H-01"] h1 + p')).fontSize) }));
    const before = await measure();
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
    const after = await measure();
    const layout = await assertFits(page);
    await page.screenshot({ path: resolve(output, "root-font-200-percent.png") });
    const actualTextScale = { heading: after.heading / before.heading, body: after.body / before.body };
    assert.ok(actualTextScale.heading >= 1.9 && actualTextScale.body >= 1.9, `Text did not reach 200%: ${JSON.stringify({ before, after, actualTextScale })}`);
    await closeContext(context, page);
    return { before, after, actualTextScale, actual200PercentTextVerified: actualTextScale.heading >= 1.9 && actualTextScale.body >= 1.9, layout };
  });

  await check("review-gate-policy", async () => {
    const { context, page } = await createContext();
    await open(page, "/?fgReview=S3B-01&fgStill=1", reviewGate ? "review" : "enhanced");
    assert.equal(await main(page).getAttribute("data-fg-mode"), reviewGate ? "review" : "enhanced");
    if (reviewGate) {
      await page.locator('[data-testid="fg-review-frame"][data-fg-ready="true"]').waitFor();
      assert.equal(await active(page).getAttribute("data-fg-scene"), "S3B-01");
    }
    await closeContext(context, page);
  });

  for (const viewport of [{ width: 1672, height: 941 }, { width: 390, height: 844 }]) {
    await check(`cold-image-transfers-${viewport.width}x${viewport.height}`, async () => {
      const { context, page } = await createContext({ viewport });
      const cdp = await context.newCDPSession(page);
      await cdp.send("Network.enable");
      const cacheDisabled = args.cache !== "normal";
      await cdp.send("Network.setCacheDisabled", { cacheDisabled });
      const requests = new Map();
      let phase = "initial";
      cdp.on("Network.requestWillBeSent", ({ requestId, request, type }) => {
        if (type === "Image") requests.set(requestId, { url: request.url, phase, bytes: null });
      });
      cdp.on("Network.loadingFinished", ({ requestId, encodedDataLength }) => {
        if (requests.has(requestId)) requests.get(requestId).bytes = encodedDataLength;
      });
      await open(page, "/", viewport.width > 1100 ? "enhanced" : "flow");
      await page.evaluate(() => document.fonts.ready);
      await delay(1800);
      const initialCLS = await page.evaluate(() => window.__fgShifts.reduce((sum, shift) => sum + shift.value, 0));
      const initial = [...requests.values()].map((request) => ({ ...request }));
      phase = "story-deferred";
      if (viewport.width > 1100) {
        for (const id of ["S2-01", "S3B-01"]) await jump(page, id);
      } else {
        await page.locator("#scene-s3b-01").scrollIntoViewIfNeeded();
      }
      await delay(1600);
      const all = [...requests.values()];
      const groups = {};
      for (const request of all) {
        const match = new URL(request.url).pathname.match(/\/landing\/floodguard-v1\/(plates|characters)\/(.+)-(\d+)\.webp$/);
        if (match) { const key = `${match[1]}/${match[2]}`; groups[key] ||= new Set(); groups[key].add(Number(match[3])); }
      }
      const measurement = {
        viewport, deviceScaleFactor: 1, serviceWorkers: "blocked", cache: cacheDisabled ? "new isolated context, HTTP cache disabled with CDP" : "new isolated cold context, normal HTTP cache", initialCLS,
        initialRequests: initial, deferredRequests: all.filter((request) => request.phase === "story-deferred"),
        initialEncodedBytes: initial.reduce((sum, request) => sum + (request.bytes || 0), 0),
        totalEncodedBytes: all.reduce((sum, request) => sum + (request.bytes || 0), 0),
        variantsByAsset: Object.fromEntries(Object.entries(groups).map(([key, values]) => [key, [...values]])),
        bytesMethod: "Chrome DevTools Network.loadingFinished encodedDataLength, actual received bytes; null means unfinished/cancelled.",
      };
      report.measurements.push(measurement);
      const multiple = Object.entries(groups).filter(([, values]) => values.size > 1).map(([key, values]) => ({ asset: key, widths: [...values] }));
      await closeContext(context, page);
      assert.equal(multiple.length, 0, `Multiple widths requested at a fixed viewport: ${JSON.stringify(multiple)}`);
      assert.ok(initial.some((request) => request.url.includes("/plates/w0-")), "Initial hero art request missing.");
      assert.ok(initial.every((request) => !/\/(?:plates\/w[12]-|characters\/)/.test(request.url)), "Later water states and portraits must remain deferred on initial load.");
      return measurement;
    });
  }

  await check("no-operational-mutations-or-location-access", async () => {
    assert.equal(report.networkMutations.length, 0, JSON.stringify(report.networkMutations));
    assert.equal(report.geolocationCalls, 0);
    assert.equal(report.browserErrors.length, 0, JSON.stringify(report.browserErrors));
    return { nonReadRequests: 0, geolocationCalls: 0, browserErrors: 0 };
  });
} finally {
  report.finishedAt = new Date().toISOString();
  report.summary = { passed: report.checks.filter((check) => check.status === "passed").length, failed: report.checks.filter((check) => check.status === "failed").length };
  await browser.close();
  writeFileSync(resolve(output, "browser-results.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ ...report.summary, report: resolve(output, "browser-results.json") }));
  if (report.summary.failed) process.exitCode = 1;
}
