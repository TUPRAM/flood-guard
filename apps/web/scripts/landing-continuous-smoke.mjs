import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const options = Object.fromEntries(process.argv.slice(2).filter((value) => value.startsWith("--")).map((value) => {
  const [key, ...rest] = value.slice(2).split("=");
  return [key, rest.join("=")];
}));
const positional = process.argv.slice(2).filter((value) => !value.startsWith("--"));
const baseUrl = (options["base-url"] || positional[0] || "http://127.0.0.1:3100").replace(/\/$/, "");
const output = resolve(options.output || positional[1] || "../../docs/visual-qa/landing-v2/browser-acceptance");
const story = JSON.parse(readFileSync(new URL("../src/lib/landing-v1/story.json", import.meta.url), "utf8"));
const sceneAssets = JSON.parse(readFileSync(new URL("../public/landing/floodguard-v2/scene-manifest.json", import.meta.url), "utf8"));
const sceneIds = story.scenes.map((scene) => scene.id);
const stageSelector = "[data-fg-continuous-stage]";
const viewports = [{ width: 1672, height: 941 }, { width: 636, height: 728 }, { width: 390, height: 844 }];
mkdirSync(output, { recursive: true });
const browser = await launchFloodGuardBrowser();
const report = {
  startedAt: new Date().toISOString(), baseUrl, browser: browser.version(), checks: [],
  environment: "Fresh local Chromium contexts; service workers blocked; production headers expected. These are functional/visual checks, not field-performance measurements.",
  method: "Native document scrolling, computed geometry/opacity, persistent DOM references, real links and keyboard interaction. Captures wait for visible artwork to decode. Scene artwork quality still requires human visual inspection.",
};
const cleanText = (value) => value.replace(/\s+/g, " ").trim();
const stage = (page) => page.locator(stageSelector);
const waitFrames = (page) => page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));

async function check(name, viewport, contextOptions, run) {
  if (options.only && !name.includes(options.only)) return;
  const started = Date.now();
  const context = await browser.newContext({ viewport, serviceWorkers: "block", reducedMotion: "no-preference", ...contextOptions });
  const errors = [], mutations = [], resourceFailures = [];
  await context.addInitScript(() => {
    window.__fgCspViolations = [];
    window.__fgGeoCalls = 0;
    document.addEventListener("securitypolicyviolation", (event) => window.__fgCspViolations.push({ directive: event.effectiveDirective, blockedURI: event.blockedURI, disposition: event.disposition }));
    for (const method of ["getCurrentPosition", "watchPosition"]) {
      Object.defineProperty(navigator.geolocation, method, { configurable: true, value: () => { window.__fgGeoCalls++; throw new Error("A landing narrative must not request geolocation."); } });
    }
  });
  context.on("request", (request) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) mutations.push({ method: request.method(), url: request.url() });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(20_000);
  page.setDefaultNavigationTimeout(60_000);
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400 && new URL(response.url()).pathname.startsWith("/landing/")) resourceFailures.push({ url: response.url(), status: response.status() });
  });
  const result = { name, viewport, status: "running", captures: [] };
  try {
    result.details = await run(page, result, context);
    const safety = await page.evaluate(() => ({ violations: window.__fgCspViolations || [], geolocationCalls: window.__fgGeoCalls || 0 }));
    assert.deepEqual(errors, [], "No page errors are allowed.");
    assert.deepEqual(resourceFailures, [], "All referenced landing files must be served successfully.");
    assert.deepEqual(mutations, [], "The story must not submit operational requests.");
    assert.deepEqual(safety.violations, [], "Production CSP must allow the implemented experience without violations.");
    assert.equal(safety.geolocationCalls, 0);
    result.safety = safety;
    result.status = "passed";
    console.log(`PASS ${name}`);
  } catch (error) {
    result.status = "failed";
    result.failure = error.stack || String(error);
    result.browserErrors = errors;
    result.resourceFailures = resourceFailures;
    result.mutations = mutations;
    result.state = await snapshot(page).catch(() => null);
    const path = resolve(output, `${name}-failure.png`);
    await page.screenshot({ path }).then(() => { result.failureCapture = path; }, () => {});
    console.log(`FAIL ${name}: ${error.message}`);
  } finally {
    const video = page.video();
    await context.close();
    if (video) result.video = await video.path();
    result.durationMs = Date.now() - started;
    report.checks.push(result);
    writeReport();
  }
}

async function open(page, hash = "", mode = "enhanced", staticDocument = false) {
  const response = await page.goto(`${baseUrl}/${hash}`, { waitUntil: staticDocument ? "load" : "domcontentloaded" });
  assert.ok(response?.ok(), `Landing returned ${response?.status()}`);
  const headers = response.headers();
  assert.ok(headers["content-security-policy"], "Run this acceptance against the production preview with actual CSP headers.");
  await page.locator("main[data-fg-landing]").waitFor({ state: "visible" });
  await page.waitForFunction((expected) => document.querySelector("main[data-fg-mode]")?.getAttribute("data-fg-mode") === expected, mode);
  if (!staticDocument) {
    await page.evaluate(() => document.fonts.ready);
    await waitFrames(page);
  }
  return headers["content-security-policy"];
}

async function snapshot(page) {
  return page.evaluate(() => {
    const root = document.querySelector("[data-fg-continuous-stage]");
    const rect = (selector) => root?.querySelector(selector)?.getBoundingClientRect().toJSON() ?? null;
    const effectiveOpacity = (element) => {
      let value = 1;
      for (let current = element; current && current !== root; current = current.parentElement) {
        const style = getComputedStyle(current);
        if (style.display === "none" || style.visibility === "hidden") return 0;
        value *= Number(style.opacity);
      }
      return value;
    };
    const paper = root?.querySelector("[data-fg-panel-background]");
    const narrative = root?.querySelector("[data-fg-panel-copy] h2");
    const card = root?.querySelector("[data-fg-card]");
    const resident = root?.querySelector('[data-fg-portrait="resident"]');
    const planner = root?.querySelector('[data-fg-portrait="planner"]');
    return {
      url: location.href, scrollY, width: innerWidth, height: innerHeight, documentWidth: document.documentElement.scrollWidth,
      mode: document.querySelector("main[data-fg-mode]")?.getAttribute("data-fg-mode"),
      scene: root?.getAttribute("data-fg-active-scene"),
      readingHold: root?.getAttribute("data-fg-reading-hold") === "true",
      camera: Number(root?.getAttribute("data-fg-camera-progress")),
      window: Number(root?.getAttribute("data-fg-window-progress")),
      panel: Number(root?.getAttribute("data-fg-panel-progress")),
      textOpacity: Number(root?.getAttribute("data-fg-text-opacity") ?? getComputedStyle(root || document.body).getPropertyValue("--copy-opacity")),
      stage: root?.getBoundingClientRect().toJSON(), art: rect("[data-fg-art-window]"), paper: rect("[data-fg-panel-background]"), panelBox: rect("[data-fg-story-panel]"),
      paperOpacity: effectiveOpacity(paper), narrativeOpacity: effectiveOpacity(narrative), cardOpacity: card ? effectiveOpacity(card) : null,
      residentOpacity: effectiveOpacity(resident), plannerOpacity: effectiveOpacity(planner),
      portraits: [resident, planner].filter(Boolean).map((image) => ({
        person: image.dataset.fgPortrait, source: image.currentSrc, naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight, geometry: image.getBoundingClientRect().toJSON(),
        opacity: effectiveOpacity(image),
      })),
      artLayers: [...(root?.querySelectorAll("[data-fg-art-layers] > img") || [])].map((image) => ({
        source: image.currentSrc,
        kind: image.hasAttribute("data-fg-retained-poster") ? "poster" : image.getAttribute("data-fg-water-layer") || "camera",
        opacity: Number(getComputedStyle(image).opacity), blendMode: getComputedStyle(image).mixBlendMode,
        transform: getComputedStyle(image).transform,
      })),
      layerIsolation: root?.querySelector("[data-fg-art-layers]") ? getComputedStyle(root.querySelector("[data-fg-art-layers]")).isolation : null,
      title: narrative?.textContent?.replace(/\s+/g, " ").trim(),
      visibleFrames: [...(root?.querySelectorAll("[data-fg-camera-frame]") || [])].filter((image) => effectiveOpacity(image) > 0.03).map((image) => ({ index: Number(image.getAttribute("data-fg-camera-frame")), src: image.currentSrc, decoded: image.complete && image.naturalWidth > 0, opacity: effectiveOpacity(image) })),
      identity: window.__fgPersistentNodes ? {
        stage: root === window.__fgPersistentNodes.stage,
        paper: paper === window.__fgPersistentNodes.paper,
        resident: resident === window.__fgPersistentNodes.resident,
        planner: planner === window.__fgPersistentNodes.planner,
      } : null,
    };
  });
}

async function rememberNodes(page) {
  await page.evaluate(() => {
    const stage = document.querySelector("[data-fg-continuous-stage]");
    window.__fgPersistentNodes = { stage, paper: stage.querySelector("[data-fg-panel-background]"), resident: stage.querySelector('[data-fg-portrait="resident"]'), planner: stage.querySelector('[data-fg-portrait="planner"]') };
  });
}

async function anchors(page) {
  return page.locator("[data-fg-anchor-position]").evaluateAll((elements) => elements.map((element) => ({ id: element.dataset.fgAnchor, anchor: element.id, hold: Number(element.dataset.fgAnchorPosition) })));
}

async function scrollPosition(page, position) {
  await page.evaluate((position) => {
    const first = document.querySelector("[data-fg-anchor-position]");
    const track = first.parentElement;
    const trackRect = track.getBoundingClientRect();
    const unit = (first.getBoundingClientRect().top - trackRect.top) / Number(first.dataset.fgAnchorPosition);
    window.scrollTo({ top: scrollY + trackRect.top + position * unit, behavior: "instant" });
  }, position);
  await waitFrames(page);
}

async function seekOpening(page, field, target) {
  const first = (await anchors(page))[0].hold;
  let low = 0, high = first;
  for (let count = 0; count < 15; count++) {
    const position = (low + high) / 2;
    await scrollPosition(page, position);
    const result = await snapshot(page);
    if (result[field] < target) low = position;
    else high = position;
  }
  await scrollPosition(page, high);
  const result = await snapshot(page);
  assert.ok(Math.abs(result[field] - target) < 0.01, `Cannot locate opening ${field}=${target}; last ${JSON.stringify(result)}`);
  return { position: high, ...result };
}

async function visibleArtReady(page) {
  const characters = Object.fromEntries(story.scenes.map((scene) => [scene.id, scene.character]));
  await page.waitForFunction((characters) => {
    const root = document.querySelector("[data-fg-continuous-stage]");
    if (!root) return false;
    if (root.hasAttribute("data-fg-art-ready") && root.getAttribute("data-fg-art-ready") !== "true") return false;
    const assigned = root.dataset.fgReadingHold === "true" ? characters[root.dataset.fgActiveScene] : null;
    for (const person of ["resident", "planner"]) {
      if (assigned !== person && Number(root.getAttribute(`data-fg-${person}-opacity`)) <= 0.025) continue;
      const portrait = root.querySelector(`[data-fg-portrait="${person}"]`);
      if (!portrait?.currentSrc || !portrait.complete || portrait.naturalWidth <= 0) return false;
    }
    const visible = [...root.querySelectorAll("img")].filter((image) => {
      let opacity = 1;
      for (let node = image; node && node !== root; node = node.parentElement) opacity *= Number(getComputedStyle(node).opacity);
      const box = image.getBoundingClientRect();
      return opacity > 0.025 && box.width > 0 && box.bottom > 0 && box.top < innerHeight;
    });
    return visible.length > 0 && visible.every((image) => image.currentSrc && image.complete && image.naturalWidth > 0);
  }, characters, { timeout: 60_000 });
  const decoded = await page.evaluate(async (characters) => {
    const root = document.querySelector("[data-fg-continuous-stage]");
    const opacity = (image) => {
      let value = 1;
      for (let node = image; node && node !== root; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (style.display === "none" || style.visibility === "hidden") return 0;
        value *= Number(style.opacity);
      }
      return value;
    };
    const required = new Set([...root.querySelectorAll("img")].filter((image) => {
      const box = image.getBoundingClientRect();
      return opacity(image) > 0.025 && box.width > 0 && box.bottom > 0 && box.top < innerHeight;
    }));
    const assigned = root.dataset.fgReadingHold === "true" ? characters[root.dataset.fgActiveScene] : null;
    for (const person of ["resident", "planner"]) {
      if (assigned !== person && Number(root.getAttribute(`data-fg-${person}-opacity`)) <= 0.025) continue;
      const portrait = root.querySelector(`[data-fg-portrait="${person}"]`);
      if (!portrait) throw new Error(`The ${person} portrait is required at this story position.`);
      const image = portrait.getBoundingClientRect();
      const shell = root.querySelector("[data-fg-portrait-shell]").getBoundingClientRect();
      const panel = root.querySelector("[data-fg-story-panel]").getBoundingClientRect();
      const visibleWidth = Math.min(image.right, shell.right, panel.right, innerWidth) - Math.max(image.left, shell.left, panel.left, 0);
      const visibleHeight = Math.min(image.bottom, shell.bottom, panel.bottom, innerHeight) - Math.max(image.top, shell.top, panel.top, 0);
      if (visibleWidth <= 0 || visibleHeight <= 0 || opacity(portrait) <= 0.025) {
        throw new Error(`The active ${person} portrait has no visible geometry: ${JSON.stringify({ image, shell, panel, visibleWidth, visibleHeight })}`);
      }
      required.add(portrait);
    }
    return Promise.all([...required].map(async (image) => {
      const source = image.currentSrc;
      await image.decode();
      if (image.currentSrc !== source || image.naturalWidth <= 0 || image.naturalHeight <= 0) throw new Error(`Artwork changed or lost decoded pixels during capture: ${source}`);
      return { source, portrait: image.dataset.fgPortrait || null, width: image.naturalWidth, height: image.naturalHeight, decoded: true };
    }));
  }, characters);
  await waitFrames(page);
  return decoded;
}

async function capture(page, result, label) {
  const decodedImages = await visibleArtReady(page);
  const path = resolve(output, `${result.viewport.width}x${result.viewport.height}-${label}.png`);
  await page.screenshot({ path });
  result.captures.push({ label, path, decodedImages, state: await snapshot(page) });
}

async function settle(page, id) {
  await page.waitForFunction((id) => {
    const stage = document.querySelector("[data-fg-continuous-stage]");
    return stage?.getAttribute("data-fg-active-scene") === id && stage.getAttribute("data-fg-reading-hold") === "true";
  }, id);
  assert.equal(await stage(page).count(), 1, "Exactly one story stage must exist.");
}

async function jump(page, id) {
  if (id === "H-01") await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  else {
    await page.locator(`[data-fg-anchor="${id}"]`).evaluate((element) => {
      element.scrollIntoView({ block: "start", behavior: "instant" });
      window.scrollBy({ top: 2, behavior: "instant" });
    });
  }
  await settle(page, id);
}

function nearRect(actual, expected, label) {
  for (const dimension of ["x", "y", "width", "height"]) assert.ok(Math.abs(actual[dimension] - expected[dimension]) < 1.5, `${label} changed ${dimension}: ${actual[dimension]} vs ${expected[dimension]}`);
}

function assertSettledArtwork(state, waterState) {
  assert.ok(state.artLayers.length > 0, "The image-only compositing stack must exist.");
  assert.equal(state.layerIsolation, "isolate", "Image cross-fades must be isolated from the page and analytical overlays.");
  const visible = state.artLayers.filter((layer) => layer.opacity > 0.005);
  assert.equal(visible.length, 1, `Exactly one physical plate must be visible at rest: ${JSON.stringify(visible)}`);
  assert.ok(state.artLayers.filter((layer) => layer.kind === "poster").every((layer) => layer.opacity < 0.005), "The retained loading poster must stop contributing after the requested view decodes.");
  assert.ok(Math.abs(state.artLayers.reduce((sum, layer) => sum + layer.opacity, 0) - 1) < 0.01, "Image opacity weights must sum to one at rest.");
  assert.equal(visible[0].kind, waterState === "W0" ? "camera" : waterState, "The visible image must represent the current physical water state.");
}

async function assertNoOverflow(page) {
  const state = await snapshot(page);
  assert.ok(state.documentWidth <= state.width + 1, `Document overflow: ${JSON.stringify(state)}`);
  if (state.art) {
    assert.ok(state.art.left >= -1 && state.art.right <= state.width + 1, "The artwork window must stay inside the viewport.");
    assert.ok(state.art.width > 0 && state.art.height > 0);
    const clippedActions = await page.locator("[data-fg-art-window] button").evaluateAll((buttons) => buttons.filter((button) => !button.disabled && Number(getComputedStyle(button).opacity) > 0.97).flatMap((button) => {
      const bounds = button.getBoundingClientRect();
      const artworkWindow = button.closest("[data-fg-art-window]").getBoundingClientRect();
      return bounds.left < artworkWindow.left - 1 || bounds.right > artworkWindow.right + 1 || bounds.top < artworkWindow.top - 1 || bounds.bottom > artworkWindow.bottom + 1
        ? [{ label: button.textContent?.trim(), button: bounds.toJSON(), artworkWindow: artworkWindow.toJSON() }] : [];
    }));
    assert.deepEqual(clippedActions, [], "Interactive map controls must remain fully visible inside the cropped artwork window.");
  }
  return { documentWidth: state.documentWidth, viewportWidth: state.width };
}

async function clickChapter(page, anchor) {
  const nav = stage(page).getByRole("navigation", { name: "Story chapters and steps" });
  const direct = nav.locator(`ol a[href="#${anchor}"]`);
  if (await direct.isVisible()) await direct.click();
  else {
    await nav.locator("details > summary").click();
    await nav.locator(`details a[href="#${anchor}"]`).click();
  }
}

function writeReport() {
  report.finishedAt = new Date().toISOString();
  report.status = report.checks.some((check) => check.status === "failed") ? "failed" : "passed";
  report.passed = report.checks.filter((check) => check.status === "passed").length;
  report.failed = report.checks.filter((check) => check.status === "failed").length;
  writeFileSync(resolve(output, "continuous-browser-results.json"), JSON.stringify(report, null, 2));
}

try {
  for (const viewport of viewports) {
    const size = `${viewport.width}x${viewport.height}`;
    await check(`opening-choreography-${size}`, viewport, {}, async (page, result) => {
      await open(page);
      await rememberNodes(page);
      await capture(page, result, "hero");
      const hero = await snapshot(page);
      assert.ok(hero.camera < 0.01 && hero.window < 0.01 && hero.paperOpacity < 0.01);
      assert.ok(hero.art.width >= viewport.width * 0.98 && hero.art.height >= viewport.height * 0.98, "The drone view must initially occupy the full stage.");
      await seekOpening(page, "camera", 0.25);
      await capture(page, result, "quarter-camera");
      const camera = await seekOpening(page, "camera", 0.5);
      await capture(page, result, "mid-camera");
      const decodedCamera = await snapshot(page);
      assert.ok(camera.window < 0.01 && camera.paperOpacity < 0.01, "Camera approach must precede the window and paper entrance.");
      assert.ok(decodedCamera.visibleFrames.some((frame) => frame.index > 0 && frame.decoded), "The approach must display a decoded intermediate camera image.");
      await seekOpening(page, "camera", 0.75);
      await capture(page, result, "three-quarter-camera");
      const shrink = await seekOpening(page, "window", 0.5);
      await capture(page, result, "half-window-shrink");
      assert.ok(shrink.camera > 0.99 && shrink.paperOpacity < 0.01 && shrink.residentOpacity < 0.01 && shrink.narrativeOpacity < 0.01);
      assert.ok(shrink.art.width * shrink.art.height < hero.art.width * hero.art.height * 0.85, "Artwork area must shrink before the panel appears.");
      if (viewport.width >= 560) assert.ok(shrink.art.left > hero.art.left + 30 && shrink.art.width < hero.art.width - 50, "Desktop and compact layouts create the left space by moving and shrinking the artwork window.");
      else assert.ok(shrink.art.height < hero.art.height - 80, "The phone layout creates the panel area by reducing artwork height.");
      const paper = await seekOpening(page, "panel", 1);
      await capture(page, result, "empty-paper");
      assert.ok(paper.window > 0.99 && paper.residentOpacity < 0.01 && paper.narrativeOpacity < 0.01, "The paper must settle before portrait and text.");
      if (viewport.width >= 560) assert.ok(paper.panelBox.right <= paper.art.left + 2, "Panel space must sit beside the shrunken artwork.");
      else assert.ok(paper.art.bottom <= paper.panelBox.top + 2, "The phone panel must occupy the area released below the artwork.");
      const portrait = await seekOpening(page, "residentOpacity", 0.5);
      await capture(page, result, "first-portrait");
      assert.ok(portrait.paperOpacity > 0.99 && portrait.narrativeOpacity < 0.02, "The portrait arrives after the paper and before the text.");
      await jump(page, "S1-01");
      const complete = await snapshot(page);
      assert.ok(complete.residentOpacity > 0.99 && complete.narrativeOpacity > 0.99);
      assert.ok(Object.values(complete.identity).every(Boolean), "Opening choreography must retain the same stage, paper and portrait nodes.");
      await assertNoOverflow(page);
      return { hero, camera: decodedCamera, shrink, emptyPaper: paper, portrait, complete };
    });

    await check(`persistent-story-and-reading-holds-${size}`, viewport, {}, async (page, result) => {
      await open(page);
      await rememberNodes(page);
      const stops = await anchors(page);
      assert.deepEqual(stops.map((stop) => stop.id), sceneIds.slice(1));
      const states = [];
      let settledPaper;
      for (const scene of story.scenes) {
        await jump(page, scene.id);
        await capture(page, result, `settled-${scene.id}`);
        const state = await snapshot(page);
        assertSettledArtwork(state, scene.waterState);
        assert.ok(Object.values(state.identity).every(Boolean), `${scene.id} replaced a persistent stage/paper/portrait node.`);
        if (scene.id !== "H-01") {
          assert.equal(state.title, cleanText(scene.title));
          assert.ok(state.narrativeOpacity > 0.99 && state.paperOpacity > 0.99);
          if (!settledPaper) settledPaper = state.paper;
          else nearRect(state.paper, settledPaper, `${scene.id} paper`);
          if (scene.character) assert.ok(state[`${scene.character}Opacity`] > 0.99, `${scene.id} must display its assigned person.`);
        }
        await assertNoOverflow(page);
        states.push(state);
      }
      const transitions = [];
      for (let index = 1; index < stops.length; index++) {
        const from = stops[index - 1], to = stops[index];
        const before = story.scenes.find((scene) => scene.id === from.id);
        const after = story.scenes.find((scene) => scene.id === to.id);
        const samples = [];
        for (let sample = 0; sample <= 24; sample++) {
          await scrollPosition(page, from.hold + 0.035 + (to.hold - from.hold - 0.02) * sample / 24);
          const state = await snapshot(page);
          assert.ok(Object.values(state.identity).every(Boolean));
          nearRect(state.paper, settledPaper, "Paper during scene transition");
          if (before.character && before.character === after.character) assert.ok(state[`${before.character}Opacity`] > 0.98, `The unchanged ${before.character} must remain visible throughout ${from.id} → ${to.id}.`);
          samples.push({ scene: state.scene, textOpacity: state.textOpacity, narrativeOpacity: state.narrativeOpacity, cardOpacity: state.cardOpacity, residentOpacity: state.residentOpacity, plannerOpacity: state.plannerOpacity, readingHold: state.readingHold });
        }
        assert.ok(samples.some((sample) => sample.textOpacity < 0.15), `Changing content must fade between ${from.id} and ${to.id}.`);
        assert.ok(samples.slice(0, 4).every((sample) => sample.readingHold && sample.textOpacity > 0.99), `A reading hold must follow ${from.id}.`);
        if (before.title === after.title && before.body === after.body) {
          assert.ok(samples.every((sample) => sample.narrativeOpacity > 0.98), "An unchanged narrative must remain visible while its card changes.");
          assert.ok(samples.some((sample) => sample.cardOpacity !== null && sample.cardOpacity < 0.15), "The changing card must visibly fade while the unchanged heading stays in place.");
        } else assert.ok(samples.some((sample) => sample.narrativeOpacity < 0.15), "The changed heading must visibly fade in the actual browser composition.");
        transitions.push({ from: from.id, to: to.id, samples });
      }
      for (const sceneId of [...sceneIds].reverse()) await jump(page, sceneId);
      assert.ok(Object.values((await snapshot(page)).identity).every(Boolean), "Reverse scrolling must retain the same asset nodes.");
      return { states, transitions, reversedScenes: [...sceneIds].reverse() };
    });

    await check(`anchors-dialog-and-brief-${size}`, viewport, {}, async (page, result) => {
      await open(page, "#story-connections");
      await settle(page, "S3A-01");
      await clickChapter(page, "story-next");
      await settle(page, "S4-01");
      assert.equal(new URL(page.url()).hash, "#story-next");
      await page.goBack(); await settle(page, "S3A-01");
      await page.goForward(); await settle(page, "S4-01");
      await page.reload({ waitUntil: "domcontentloaded" }); await settle(page, "S4-01");
      await stage(page).getByRole("link", { name: "Previous story step" }).click();
      await settle(page, "S3B-01");
      await stage(page).getByRole("link", { name: "Previous story step" }).click();
      await settle(page, "S3B-OBS");
      const observation = stage(page).getByRole("button", { name: "Inspect sample observation DEMO-R01", exact: true });
      await observation.focus(); await page.keyboard.press("Enter");
      const dialog = stage(page).getByRole("dialog", { name: /DEMO-R01/ });
      await dialog.waitFor({ state: "visible" });
      assert.match(await dialog.innerText(), /Not verified/);
      const dialogPath = resolve(output, `${size}-observation-dialog.png`);
      await page.screenshot({ path: dialogPath }); result.captures.push({ label: "observation-dialog", path: dialogPath });
      await page.keyboard.press("Escape"); await dialog.waitFor({ state: "hidden" });
      assert.ok(await observation.evaluate((element) => element === document.activeElement), "Escape must restore observation-trigger focus.");
      await clickChapter(page, "story-next"); await settle(page, "S4-01");
      const selection = stage(page).getByRole("button", { name: new RegExp(story.routeLabels.selection) });
      await selection.click();
      const brief = stage(page).locator("[data-fg-card=brief] details");
      assert.ok(await brief.evaluate((element) => element.open && element === document.activeElement), "Selection must open and focus the review brief.");
      const briefRect = await brief.boundingBox();
      assert.ok(briefRect && briefRect.y < viewport.height && briefRect.y + briefRect.height > 0, "The selected brief must be brought into the visible panel.");
      await capture(page, result, "opened-review-brief");
      await page.keyboard.press("Escape");
      assert.ok(await brief.evaluate((element) => !element.open && element.querySelector("summary") === document.activeElement));
      await assertNoOverflow(page);
      return { directEntry: "S3A-01", backForwardReload: true, previousSteps: ["S3B-01", "S3B-OBS"], observationFocusReturn: true, selectionOpensBrief: true };
    });
  }

  for (const viewport of [viewports[0], viewports[2]]) {
    await check(`reduced-motion-flow-${viewport.width}x${viewport.height}`, viewport, { reducedMotion: "reduce" }, async (page, result) => {
      await open(page, "#story-conditions", "flow");
      assert.equal(await stage(page).count(), 0);
      assert.equal(await page.locator("[data-fg-fallback-frame]").count(), sceneIds.length);
      assert.equal(await page.locator("[data-fg-reduced-motion]").getAttribute("data-fg-reduced-motion"), "true");
      const frame = page.locator('[data-fg-fallback-frame][data-fg-scene="S2-01"]');
      await frame.scrollIntoViewIfNeeded();
      await frame.locator("img[data-fg-plate-image]").first().scrollIntoViewIfNeeded();
      await page.waitForFunction(() => {
        const image = document.querySelector('[data-fg-fallback-frame][data-fg-scene="S2-01"] img[data-fg-plate-image]');
        return image?.currentSrc && image.complete && image.naturalWidth > 0;
      });
      const path = resolve(output, `${viewport.width}x${viewport.height}-reduced-motion-flow.png`);
      await page.screenshot({ path }); result.captures.push({ label: "reduced-motion-flow", path });
      await assertNoOverflow(page);
      await page.emulateMedia({ reducedMotion: "no-preference" });
      await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "enhanced");
      await settle(page, "S2-01");
      await page.getByRole("button", { name: "Reduce motion", exact: true }).click();
      await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
      assert.equal(await page.evaluate(() => localStorage.getItem("floodguard:landing-reduced-motion")), "1");
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
      return { fallbackScenes: sceneIds.length, dynamicOsPreference: true, manualPreferencePersists: true };
    });
  }

  for (const viewport of [viewports[1], viewports[2]]) {
    await check(`keyboard-scrollable-explanation-${viewport.width}x${viewport.height}`, viewport, {}, async (page, result) => {
      await open(page);
      let sceneId = "S3B-01";
      await jump(page, sceneId); await visibleArtReady(page);
      const region = stage(page).getByRole("region", { name: "Story explanation", exact: true });
      let dimensions = await region.evaluate((element) => ({ height: element.clientHeight, content: element.scrollHeight }));
      if (dimensions.content <= dimensions.height + 4) {
        sceneId = "S4-01";
        await jump(page, sceneId); await visibleArtReady(page);
        await stage(page).locator('[data-fg-card="brief"] summary').click();
        dimensions = await region.evaluate((element) => ({ height: element.clientHeight, content: element.scrollHeight }));
      }
      assert.ok(dimensions.content > dimensions.height + 4, "This check must exercise genuinely overflowing explanation content.");
      await stage(page).getByRole("button", { name: "Inspect sample observation DEMO-R01", exact: true }).focus();
      const tabOrder = [];
      for (let attempt = 0; attempt < 8; attempt++) {
        await page.keyboard.press("Tab");
        const focus = await page.evaluate(() => ({ tag: document.activeElement.tagName, label: document.activeElement.getAttribute("aria-label") || document.activeElement.textContent?.trim().slice(0, 80), region: document.activeElement.hasAttribute("data-fg-panel-copy") }));
        tabOrder.push(focus);
        if (focus.region) break;
      }
      assert.ok(await region.evaluate((element) => document.activeElement === element), "Normal Tab navigation must reach the scrollable story explanation.");
      await region.evaluate((element) => element.scrollTo({ top: 0, behavior: "instant" }));
      const before = await page.evaluate(() => ({ documentY: scrollY, panelY: document.querySelector("[data-fg-panel-copy]").scrollTop, scene: document.querySelector("[data-fg-continuous-stage]").getAttribute("data-fg-active-scene") }));
      await page.keyboard.press("PageDown");
      await page.waitForFunction((previous) => document.querySelector("[data-fg-panel-copy]").scrollTop > previous + 1, before.panelY);
      await page.waitForTimeout(200);
      const after = await page.evaluate(() => ({ documentY: scrollY, panelY: document.querySelector("[data-fg-panel-copy]").scrollTop, scene: document.querySelector("[data-fg-continuous-stage]").getAttribute("data-fg-active-scene") }));
      assert.equal(after.scene, sceneId, "Reading overflow text with the keyboard must not advance the story.");
      assert.ok(Math.abs(after.documentY - before.documentY) < 2, "PageDown must scroll the focused explanation region, not the document.");
      assert.ok(after.panelY > before.panelY);
      await capture(page, result, "keyboard-scrolled-explanation");
      await assertNoOverflow(page);
      return { dimensions, tabOrder, before, after };
    });
  }

  await check("no-javascript-readable-story", viewports[2], { javaScriptEnabled: false }, async (page, result) => {
    await open(page, "", "flow", true);
    assert.equal(await stage(page).count(), 0);
    assert.equal(await page.locator("[data-fg-fallback-frame]").count(), sceneIds.length);
    const images = [];
    for (const scene of story.scenes) {
      const frame = page.locator(`[data-fg-fallback-frame][data-fg-scene="${scene.id}"]`);
      assert.ok(cleanText(await frame.innerText()).includes(cleanText(scene.title)));
      const image = frame.locator("img[data-fg-plate-image][src]").first();
      await image.scrollIntoViewIfNeeded();
      await image.evaluate((image) => image.decode());
      const details = await image.evaluate((image) => ({ src: image.currentSrc, width: image.naturalWidth, height: image.naturalHeight }));
      assert.ok(details.src.includes("/landing/floodguard-v2/") && details.width > 0, "No-JavaScript reading must show the same new neighborhood artwork.");
      images.push({ scene: scene.id, ...details });
      await assertNoOverflow(page);
    }
    const briefFrame = page.locator('[data-fg-fallback-frame][data-fg-scene="S4-01"]');
    const summary = briefFrame.locator("details > summary").filter({ hasText: story.cards.brief.actionLabel }).first();
    await summary.click();
    assert.ok(await summary.evaluate((element) => element.parentElement.open));
    const path = resolve(output, "390x844-no-javascript-brief.png");
    await page.screenshot({ path }); result.captures.push({ label: "no-javascript-brief", path });
    return { decodedNeighborhoods: images, nativeBriefWorks: true };
  });

  await check("200-percent-root-text-readable-flow", viewports[0], {}, async (page, result) => {
    await open(page);
    const measure = () => page.evaluate(() => {
      const heading = document.querySelector("main h1");
      const body = heading.parentElement.querySelectorAll("p")[1];
      return { rootPx: parseFloat(getComputedStyle(document.documentElement).fontSize), headingPx: parseFloat(getComputedStyle(heading).fontSize), bodyPx: parseFloat(getComputedStyle(body).fontSize) };
    });
    const before = await measure();
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    await page.waitForFunction(() => document.querySelector("main[data-fg-mode]")?.getAttribute("data-fg-mode") === "flow");
    const after = await measure();
    assert.ok(after.rootPx / before.rootPx >= 1.99, "The root text size must actually double.");
    assert.equal(await stage(page).count(), 0);
    assert.equal(await page.locator("[data-fg-fallback-frame]").count(), sceneIds.length);
    assert.equal(await page.locator("main").getAttribute("data-fg-text-enlarged"), "true");
    const layouts = [];
    for (const id of ["H-01", "S3B-01", "S4-01", "S4-END"]) {
      const frame = page.locator(`[data-fg-fallback-frame][data-fg-scene="${id}"]`);
      await frame.locator("h1,h2,h3").first().scrollIntoViewIfNeeded();
      layouts.push({ scene: id, ...await assertNoOverflow(page) });
      const titleBounds = await frame.locator("h1,h2,h3").first().boundingBox();
      assert.ok(titleBounds);
      assert.ok(titleBounds.x >= -1 && titleBounds.x + titleBounds.width <= viewports[0].width + 1, "Enlarged headings must remain inside the readable page.");
      if (id === "H-01" || id === "S3B-01") {
        const path = resolve(output, `1672x941-root-text-200-${id}.png`);
        await page.screenshot({ path }); result.captures.push({ label: `root-text-200-${id}`, path });
      }
    }
    return { before, after, actualRootScale: after.rootPx / before.rootPx, actualHeadingScale: after.headingPx / before.headingPx, actualBodyScale: after.bodyPx / before.bodyPx, layouts, qualification: "The layout changes from the continuous stage to readable flow. Actual heading/body sizes are reported separately; doubling the root font is not presented as a universal twofold scale of every responsive heading." };
  });

  await check("smallest-supported-phone-320x800", { width: 320, height: 800 }, {}, async (page, result) => {
    await open(page);
    await rememberNodes(page);
    const layouts = [];
    for (const id of sceneIds) {
      await jump(page, id);
      await visibleArtReady(page);
      layouts.push({ scene: id, ...await assertNoOverflow(page) });
      assert.ok(Object.values((await snapshot(page)).identity).every(Boolean));
      if (["H-01", "S3B-OBS", "S4-01"].includes(id)) await capture(page, result, `small-phone-${id}`);
    }
    await jump(page, "S1-01");
    await clickChapter(page, "story-next");
    await settle(page, "S4-01");
    const summary = stage(page).locator('[data-fg-card="brief"] summary');
    await summary.focus(); await page.keyboard.press("Enter");
    assert.ok(await summary.evaluate((element) => element.parentElement.open));
    await assertNoOverflow(page);
    return { mode: "enhanced", layouts, compactChapterMenu: true, nativeBriefKeyboard: true };
  });

  await check("short-landscape-readable-flow-844x390", { width: 844, height: 390 }, {}, async (page, result) => {
    await open(page, "", "flow");
    assert.equal(await stage(page).count(), 0);
    assert.equal(await page.locator("[data-fg-fallback-frame]").count(), sceneIds.length);
    const layouts = [];
    for (const id of ["H-01", "S3B-OBS", "S4-01", "S4-END"]) {
      const frame = page.locator(`[data-fg-fallback-frame][data-fg-scene="${id}"]`);
      await frame.locator("h1,h2,h3").first().scrollIntoViewIfNeeded();
      layouts.push({ scene: id, ...await assertNoOverflow(page) });
    }
    const frame = page.locator('[data-fg-fallback-frame][data-fg-scene="S4-01"]');
    const summary = frame.locator("details > summary").filter({ hasText: story.cards.brief.actionLabel }).first();
    await summary.click();
    assert.ok(await summary.evaluate((element) => element.parentElement.open));
    const path = resolve(output, "844x390-short-landscape-brief.png");
    await page.screenshot({ path }); result.captures.push({ label: "short-landscape-brief", path });
    return { mode: "flow", layouts, nativeBrief: true };
  });

  await check("failed-artwork-explicit-fallback-and-readable-story", viewports[0], {}, async (page, result, context) => {
    const failedPath = sceneAssets.closeStates.W2;
    let aborted = 0;
    await context.route(`**${failedPath}`, (route) => { aborted++; return route.abort("failed"); });
    await open(page);
    await jump(page, "S3B-01");
    const scene = story.scenes.find((scene) => scene.id === "S3B-01");
    const fallback = stage(page).getByRole("img", { name: scene.imageDescription, exact: true });
    await fallback.waitFor({ state: "visible" });
    assert.match(await fallback.innerText(), /Illustration unavailable/);
    assert.ok(aborted > 0, "The requested flooded artwork must actually fail in this test.");
    const state = await snapshot(page);
    assert.equal(state.title, cleanText(scene.title));
    assert.ok(state.narrativeOpacity > 0.99, "Narrative must remain readable when its artwork fails.");
    assert.ok(await stage(page).getByRole("heading", { name: story.cards.analysis.title, exact: true }).isVisible());
    const path = resolve(output, "1672x941-failed-artwork-readable-analysis.png");
    await page.screenshot({ path }); result.captures.push({ label: "failed-artwork", path });
    await clickChapter(page, "story-next"); await settle(page, "S4-01");
    const summary = stage(page).locator('[data-fg-card="brief"] summary');
    await summary.click();
    assert.ok(await summary.evaluate((element) => element.parentElement.open), "The local brief remains usable without the illustration.");
    await jump(page, "S1-01"); await visibleArtReady(page);
    assert.equal(await stage(page).getByText("Illustration unavailable", { exact: true }).count(), 0, "A failed W2 request must not hide a successfully available dry scene.");
    await assertNoOverflow(page);
    return { intentionallyAbortedAsset: failedPath, abortedRequests: aborted, explicitFallback: true, readableAnalysis: true, briefUsable: true, dryViewRecovered: true };
  });

  for (const viewport of [viewports[0], viewports[2]]) {
    await check(`cold-image-bytes-cls-fcp-${viewport.width}x${viewport.height}`, viewport, {}, async (page, result, context) => {
      await context.addInitScript(() => {
        window.__fgColdShifts = [];
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) if (!entry.hadRecentInput) window.__fgColdShifts.push({ value: entry.value, startTime: entry.startTime });
        }).observe({ type: "layout-shift", buffered: true });
      });
      const cdp = await context.newCDPSession(page);
      await cdp.send("Network.enable");
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
      const requests = new Map();
      let phase = "cold-opening";
      cdp.on("Network.requestWillBeSent", ({ requestId, request, type, timestamp, wallTime }) => {
        if (type === "Image") requests.set(requestId, { url: request.url, phase, startTimestamp: timestamp, startUnixMs: wallTime * 1000, encodedBytes: null });
      });
      cdp.on("Network.responseReceived", ({ requestId, response }) => {
        if (requests.has(requestId)) Object.assign(requests.get(requestId), { status: response.status, mimeType: response.mimeType, fromDiskCache: Boolean(response.fromDiskCache), fromServiceWorker: Boolean(response.fromServiceWorker) });
      });
      cdp.on("Network.loadingFinished", ({ requestId, encodedDataLength, timestamp }) => {
        if (requests.has(requestId)) Object.assign(requests.get(requestId), { encodedBytes: encodedDataLength, durationMs: (timestamp - requests.get(requestId).startTimestamp) * 1000 });
      });
      cdp.on("Network.loadingFailed", ({ requestId, errorText }) => {
        if (requests.has(requestId)) requests.get(requestId).failure = errorText;
      });
      await open(page);
      await visibleArtReady(page);
      await page.waitForTimeout(2500);
      const initialTiming = await page.evaluate(() => {
        let maximum = 0, sessionValue = 0, sessionStart = 0, lastShift = 0;
        for (const shift of window.__fgColdShifts) {
          if (shift.startTime - lastShift > 1000 || shift.startTime - sessionStart > 5000) { sessionStart = shift.startTime; sessionValue = 0; }
          sessionValue += shift.value;
          maximum = Math.max(maximum, sessionValue);
          lastShift = shift.startTime;
        }
        return { timeOrigin: performance.timeOrigin, observationEndMs: performance.now(), firstContentfulPaintMs: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null, navigationLoadEndMs: performance.getEntriesByType("navigation")[0]?.loadEventEnd ?? null, cumulativeLayoutShift: maximum, shiftEntries: window.__fgColdShifts, deviceScaleFactor: devicePixelRatio, serviceWorkerController: Boolean(navigator.serviceWorker.controller) };
      });
      const initial = structuredClone([...requests.values()]);
      const imagePath = resolve(output, `${viewport.width}x${viewport.height}-cold-opening.png`);
      await page.screenshot({ path: imagePath }); result.captures.push({ label: "cold-opening", path: imagePath });
      phase = "story-interaction";
      for (const id of ["S2-01", "S3B-01"]) { await jump(page, id); await visibleArtReady(page); }
      await page.waitForTimeout(400);
      const normalize = (items) => items.map((request) => ({
        ...request,
        startedAfterNavigationMs: request.startUnixMs - initialTiming.timeOrigin,
        completedAfterNavigationMs: request.durationMs === undefined ? null : request.startUnixMs - initialTiming.timeOrigin + request.durationMs,
      }));
      const initialRequests = normalize(initial), allRequests = normalize([...requests.values()]);
      const measurement = {
        ...initialTiming,
        viewport,
        cache: "Fresh browser context; HTTP cache explicitly disabled with CDP; service workers blocked.",
        observation: "Cold-opening snapshot taken 2500 ms after the requested hero artwork decoded; the actual observation end is recorded above. Deferred background camera preparation can be included in this window.",
        byteMethod: "Chrome DevTools Network.loadingFinished.encodedDataLength, actual received encoded image bytes. Null denotes an unfinished or failed request. This is distinct from decoded image-memory size or response-body byte accounting.",
        initialRequests,
        storyRequests: allRequests.filter((request) => request.phase === "story-interaction"),
        initialEncodedImageBytes: initialRequests.reduce((sum, request) => sum + (request.encodedBytes || 0), 0),
        totalEncodedImageBytes: allRequests.reduce((sum, request) => sum + (request.encodedBytes || 0), 0),
        completedImageBytesByFirstContentfulPaint: initialRequests.filter((request) => request.completedAfterNavigationMs !== null && request.completedAfterNavigationMs <= initialTiming.firstContentfulPaintMs).reduce((sum, request) => sum + (request.encodedBytes || 0), 0),
        requestsPerSource: Object.fromEntries([...new Set(allRequests.map((request) => request.url))].map((url) => [url, allRequests.filter((request) => request.url === url).length])),
        budgetPolicy: "Measured values are reported without an invented byte, timing or CLS pass threshold.",
      };
      assert.ok(initialTiming.firstContentfulPaintMs > 0, "The FCP observation must be available.");
      assert.equal(initialTiming.serviceWorkerController, false);
      assert.ok(initialRequests.some((request) => new URL(request.url).pathname === sceneAssets.cameraFrames[0].src && request.encodedBytes > 0), "The actual wide drone image must have transferred in the cold context.");
      assert.ok(allRequests.every((request) => !request.fromServiceWorker && !request.fromDiskCache), "The cold measurement must not use disk-cache or service-worker responses.");
      return measurement;
    });
  }

  await check("deterministic-wide-scroll-video", viewports[0], { recordVideo: { dir: resolve(output, "video"), size: viewports[0] } }, async (page, result) => {
    await open(page);
    await visibleArtReady(page);
    const stops = await anchors(page);
    const finish = stops.at(-1).hold + 0.4;
    const duration = 24_000;
    const observed = await page.evaluate(async ({ finish, duration }) => {
      const first = document.querySelector("[data-fg-anchor-position]");
      const track = first.parentElement;
      const origin = scrollY + track.getBoundingClientRect().top;
      const unit = (first.getBoundingClientRect().top - track.getBoundingClientRect().top) / Number(first.dataset.fgAnchorPosition);
      const seen = new Set();
      const start = performance.now();
      await new Promise((resolve) => {
        const frame = (now) => {
          const progress = Math.min(1, (now - start) / duration);
          window.scrollTo({ top: origin + finish * unit * progress, behavior: "instant" });
          seen.add(document.querySelector("[data-fg-continuous-stage]")?.getAttribute("data-fg-active-scene"));
          if (progress < 1) requestAnimationFrame(frame);
          else resolve();
        };
        requestAnimationFrame(frame);
      });
      return [...seen];
    }, { finish, duration });
    await settle(page, sceneIds.at(-1));
    assert.deepEqual(observed, sceneIds, "A continuous forward scroll must visit every story scene.");
    await capture(page, result, "video-ending");
    return { durationMs: duration, observedScenes: observed, movement: "Native requestAnimationFrame-driven document scroll; no synthetic scene state assignments." };
  });
} finally {
  await browser.close();
  writeReport();
  console.log(JSON.stringify({ status: report.status, passed: report.passed, failed: report.failed, output }));
  if (report.failed) process.exitCode = 1;
}
