import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";
import { CASE_REPLAY_EXPORT_BUDGET_BYTES } from "./case-replay-inventory.mjs";

const output = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? "out");
const artifacts = resolve("test-results/studio-studies");
mkdirSync(artifacts, { recursive: true });
let server;
let baseUrl = process.env.FLOODGUARD_STUDY_BASE_URL;
if (!baseUrl) {
  assert(existsSync(resolve(output, "studio/studies/c2s-ms-20260915/index.html")), "Build the static study routes before running this check.");
  const types = { ".html":"text/html", ".js":"text/javascript", ".css":"text/css", ".json":"application/json", ".geojson":"application/geo+json", ".png":"image/png", ".webp":"image/webp", ".svg":"image/svg+xml", ".woff2":"font/woff2" };
  server = createServer((request, response) => {
    const path = decodeURIComponent(new URL(request.url ?? "/", "http://localhost").pathname).replace(/^\/+/, "");
    let file = resolve(output, path || "index.html");
    if (file !== output && !file.startsWith(`${output}${sep}`)) return response.writeHead(403).end();
    if (existsSync(file) && statSync(file).isDirectory()) file = resolve(file, "index.html");
    if (!existsSync(file) || !statSync(file).isFile()) return response.writeHead(404).end("Unavailable");
    response.writeHead(200, { "Content-Type": types[extname(file)] ?? "application/octet-stream", "Cache-Control":"no-store" });
    createReadStream(file).pipe(response);
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  baseUrl = `http://127.0.0.1:${server.address().port}`;
}

const study = "/studio/studies/c2s-ms-20260915/";
const browser = await launchFloodGuardBrowser();
const checks = [];
try {
  const context = await browser.newContext({ viewport:{width:1440,height:1000}, serviceWorkers:"block" });
  await context.route("**/*", (route) => new URL(route.request().url()).origin === new URL(baseUrl).origin ? route.continue() : route.abort());
  const page = await context.newPage();
  const pageErrors = [];
  const failedResponses = [];
  const consoleErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => { if (response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`); });
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(`${message.text()} ${message.location()?.url ?? ""}`.trim()); });
  async function visit(path, ready) {
    const response = await page.goto(`${baseUrl}${path}`, { waitUntil:"networkidle" });
    assert.equal(response?.status(), 200, `Direct route ${path}`);
    await expect(page.getByText(ready, {exact:false}).first()).toBeVisible();
    assert.equal(await page.locator("main").getByRole("alert").count(), 0, `No evidence errors at ${path}`);
    checks.push(`direct route ${path}`);
  }
  await visit(study, "What the experiment establishes");
  await visit(`${study}data/`, "Five separate jobs for the data");
  await expect(page.locator("svg path").first()).toBeVisible();
  await page.getByLabel("Show event role").selectOption("test");
  await expect(page).toHaveURL(/role=test/);
  await expect(page.locator("tr[id^=event-]")).toHaveCount(3);
  await page.reload({waitUntil:"networkidle"});
  await expect(page.getByLabel("Show event role")).toHaveValue("test");
  checks.push("event filter survives reload");
  await visit(`${study}models/`, "XGBoost · recorded fit");
  await expect(page.getByText("XGBoost feature contributions", {exact:true})).toBeVisible();
  await page.getByLabel("Model and input version").selectOption("sar/unet");
  await expect(page.getByText("U-Net · recorded fit", {exact:true})).toBeVisible();
  await visit(`${study}results/`, "10,455,894");
  await page.getByLabel("Probability version").selectOption("raw");
  await expect(page).toHaveURL(/calibration=raw/);
  await expect(page.getByText("0.7735", {exact:true}).first()).toBeVisible();
  await page.goBack({waitUntil:"networkidle"});
  await expect(page.getByLabel("Probability version")).toHaveValue("calibrated");
  await page.getByLabel("Comparison view").selectOption("events");
  await expect(page.getByText("Nigeria", {exact:true}).first()).toBeVisible();
  checks.push("raw/calibrated and event results shareable; browser Back restores state");
  await visit(`${study}rtc/`, "The fixed 1–5 dB change ramp");
  await expect(page.getByText("11,732,437", {exact:true}).first()).toBeVisible();
  await visit(`${study}explorer/`, "Human water reference");
  await expect(page.getByText("0.1334", {exact:true})).toBeVisible();
  const initialChip = await page.getByLabel(/^Chip \(/).inputValue();
  await page.getByLabel(/^Model/).selectOption("xgboost");
  await page.getByLabel(/^Input version/).selectOption("sar");
  await expect(page.getByRole("img", {name:"Prediction errors against the human reference"})).toBeVisible();
  await page.reload({waitUntil:"networkidle"});
  await expect(page.getByLabel(/^Input version/)).toHaveValue("sar");
  await expect(page.getByLabel(/^Model/)).toHaveValue("xgboost");
  const index = await (await context.request.get(`${baseUrl}/studies/c2s-ms-20260915/r1/visual-index.json`)).json();
  const missing = index.chips.find((chip) => chip.models.context.unet.status === "unavailable");
  assert(missing, "An unsupported context chip stays in the visual catalogue.");
  await page.goto(`${baseUrl}${study}explorer/?arm=context&model=unet&chip=${encodeURIComponent(missing.chip_id)}`, {waitUntil:"networkidle"});
  await expect(page.locator("main").getByRole("alert")).toContainText("Model preview unavailable");
  assert.equal(await page.getByRole("img",{name:"Binary water prediction"}).count(),0);
  checks.push("Australian U-Net failure visible and unsupported context case fails closed");
  await visit(`${study}files/`, "Reproduce the recorded result");
  for (const link of await page.locator("a[download]").evaluateAll((nodes) => nodes.map((node) => node.href))) {
    assert.equal((await context.request.get(link)).status(),200,`Download ${link}`);
  }
  checks.push("all presented study downloads resolve");
  await visit(`${study}mae-sai/`, "Inference identity and model lineage");
  for (const arm of ["sar","context"]) for (const model of ["random_forest","xgboost","unet"]) {
    await page.getByLabel(/^Input version/).selectOption(arm);
    await page.getByLabel(/^Model/).selectOption(model);
    for (const layer of ["probability","validity","entropy","abstention"]) {
      await page.getByLabel("Map layer").selectOption(layer);
      await page.waitForFunction(() => [...document.querySelectorAll("figure img")].every((img) => img.complete && img.naturalWidth > 0));
      assert.equal(await page.locator("main").getByRole("alert").count(),0,`Mae Sai ${arm}/${model}/${layer}`);
    }
  }
  const maeText = await page.locator("main").innerText();
  assert(!/\bIoU\b|0\.8661|Human water reference/.test(maeText), "Mae Sai cannot show benchmark scores or a local human reference.");
  checks.push("all 24 Mae Sai model/input/layer combinations render without local accuracy claims");
  await page.getByLabel("Map layer").selectOption("probability");
  await page.getByLabel("Abstention overlay").selectOption("on");
  await expect(page).toHaveURL(/overlay=on/);
  await expect(page.getByText("Abstention overlay applied at 35% opacity",{exact:false})).toBeVisible();
  await page.reload({waitUntil:"networkidle"});
  await expect(page.getByLabel("Abstention overlay")).toHaveValue("on");
  await expect(page.getByRole("img",{name:"Abstention overlay at 35 percent opacity"})).toBeVisible();
  checks.push("same-grid abstention overlay preserves original pixels and shareable URL state");
  await page.screenshot({path:resolve(artifacts,"mae-sai-desktop.png"),fullPage:true});
  await visit("/studio/archive/mae-sai-geoai/", "Historical research");
  await expect(page.getByText(/teacher agreement|Teacher agreement|distillation fidelity/).first()).toBeVisible();
  await visit("/studio/", "Every result has a context.");
  await page.screenshot({path:resolve(artifacts,"studio-library-desktop.png"),fullPage:true});
  // Case replay (/studio/cases/mae-sai-2024/): renders from its manifest, the hourly slider drives the readout,
  // and the view is a shareable link. The street basemap is answered locally so the check never needs the network.
  const caseRoute = "/studio/cases/mae-sai-2024/";
  const blankTile = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "base64");
  await page.route("https://tile.openstreetmap.org/**", (route) => route.fulfill({ status: 200, contentType: "image/png", body: blankTile }));
  const readout = page.getByTestId("replay-readout");
  const slider = page.getByRole("slider", { name: "Replay time (hourly)" });
  const waterModel = () => page.waitForFunction(() => !document.body.innerText.includes("Preparing the water model"), undefined, { timeout: 30_000 });
  // Imagery, water and road modes and the layer switches live in the "Map layers" drawer over the map.
  const layersButton = page.getByRole("button", { name: "Map layers", exact: true });
  const openLayers = async () => {
    if ((await layersButton.getAttribute("aria-expanded")) !== "true") await layersButton.click();
    await expect(page.locator("#mae-sai-map-layers")).toBeVisible();
  };
  // What sits over the map, by name. A box counts only while it is shown (the notes and the legend fade out while a
  // popup is open); the checks below compare the shown boxes pairwise and against the map frame.
  const MAP_BOXES = {
    zoom: ".leaflet-control-zoom",
    notes: "[data-testid='map-notes']",
    legend: "[data-testid='map-legend']",
    "basemap note": "[data-testid='basemap-note']",
    "clear route": "[data-testid='clear-route']",
    "envelope chip": "[data-testid='envelope-chip']",
    "envelope failure": "[data-testid='envelope-failed-map']",
    attribution: ".leaflet-control-attribution",
    popup: ".leaflet-popup",
    "left label": "[data-testid='compare-label-left']",
    "right label": "[data-testid='compare-label-right']",
    "divider handle": "[data-testid='compare-handle']",
  };
  const mapLayout = (target = page) => target.evaluate((selectors) => {
    const frame = document.querySelector("[class*='mapFrame']").getBoundingClientRect();
    const boxes = Object.entries(selectors).flatMap(([name, selector]) => {
      const element = document.querySelector(selector);
      if (!element) return [];
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      if (box.width === 0 || box.height === 0 || style.display === "none" || style.visibility === "hidden" || Number(style.opacity) < 0.05) return [];
      return [{ name, left: box.left, top: box.top, right: box.right, bottom: box.bottom }];
    });
    const overlapping = [];
    const outside = [];
    for (const [index, a] of boxes.entries()) {
      if (a.left < frame.left - 0.5 || a.right > frame.right + 0.5 || a.top < frame.top - 0.5 || a.bottom > frame.bottom + 0.5) outside.push(a.name);
      for (const b of boxes.slice(index + 1)) {
        const across = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const down = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (across > 0.5 && down > 0.5) overlapping.push(`${a.name} over ${b.name} (${Math.round(across)} x ${Math.round(down)} px)`);
      }
    }
    return { shown: boxes.map((box) => box.name), overlapping, outside };
  }, MAP_BOXES);
  /**
   * Exactly the boxes named in `expected` are shown, none of them overlap, and all lie inside the map frame. Fades and
   * map pans take a moment, so the settled state is what counts: the check polls until it holds.
   */
  const expectClearMap = async (expected, label, target = page) => {
    let layout;
    await expect.poll(async () => {
      layout = await mapLayout(target);
      const problems = [
        ...expected.filter((name) => !layout.shown.includes(name)).map((name) => `${name} is missing`),
        ...layout.shown.filter((name) => !expected.includes(name)).map((name) => `${name} should not be shown`),
        ...layout.overlapping,
        ...layout.outside.map((name) => `${name} leaves the map frame`),
      ];
      return problems.join("; ");
    }, { message: `${label}: ${expected.join(", ")} on the map, clear of each other and inside the frame`, timeout: 8000 }).toBe("");
    return layout;
  };
  /**
   * Where the map sits and the sizes of the bar above it; none may change when a label changes. The map's place is
   * given as the page position of the map-and-cards row plus the map's offset inside its own column, because that
   * column is sticky on desktop and its page position follows the scroll.
   */
  const stageGeometry = (target = page) => target.evaluate(() => {
    const round = (value) => Math.round(value * 10) / 10;
    const map = document.querySelector("[class*='mapFrame']");
    const bar = document.querySelector("[class*='stageBar']");
    const column = map.parentElement;
    const row = column.parentElement;
    const button = document.querySelector("[data-testid='play-button']").getBoundingClientRect();
    const layers = document.querySelector("[aria-controls='mae-sai-map-layers']").getBoundingClientRect();
    return {
      mapTop: round(row.getBoundingClientRect().top + window.scrollY + map.getBoundingClientRect().top - column.getBoundingClientRect().top),
      barHeight: round(bar.getBoundingClientRect().height),
      playWidth: round(button.width),
      playHeight: round(button.height),
      layersLeft: round(layers.left),
    };
  });
  /** Play, then pause: the map does not move, and the Play button and the bar keep their size. */
  const expectSteadyPlay = async (label, target = page) => {
    const button = target.getByTestId("play-button");
    const before = await stageGeometry(target);
    const idleLabel = (await button.innerText()).trim();
    await button.click();
    await expect(button).toContainText(/Pause|หยุดชั่วคราว/);
    const during = await stageGeometry(target);
    await button.click();
    await expect(button).not.toContainText(/Pause|หยุดชั่วคราว/);
    const after = await stageGeometry(target);
    assert.deepEqual(during, before, `${label}: pressing Play moves nothing (${idleLabel} -> Pause)`);
    assert.deepEqual(after, before, `${label}: pressing Pause moves nothing`);
    return before;
  };
  /** Keyboard only: the drawer takes focus when it opens, Tab lands on its first control, Escape hands focus back. */
  const expectDrawerFocus = async (label) => {
    const drawer = page.locator("#mae-sai-map-layers");
    await expect(drawer).toBeHidden();
    await layersButton.focus();
    await page.keyboard.press("Enter");
    await expect(drawer).toBeVisible();
    await expect(drawer).toBeFocused();
    await page.keyboard.press("Tab");
    const reached = await page.evaluate(() => {
      const active = document.activeElement;
      return { inside: Boolean(active && active !== document.body && document.querySelector("#mae-sai-map-layers").contains(active)), tag: active?.tagName, text: active?.textContent?.trim() };
    });
    assert(reached.inside && reached.tag === "BUTTON" && reached.text === "Close", `${label}: Tab from the opened drawer reaches its first control (${JSON.stringify(reached)})`);
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(layersButton).toBeFocused();
    // Once focus has left the drawer, Escape still closes it, from Play and from the timeline slider, and leaves
    // focus where the reader is.
    for (const [name, target] of [["Play", page.getByTestId("play-button")], ["the timeline slider", page.locator("input[type='range'][class*='range']")]]) {
      await layersButton.focus();
      await page.keyboard.press("Enter");
      await expect(drawer).toBeVisible();
      await target.focus();
      await expect(drawer, `${label}: the drawer stays open when focus moves to ${name}`).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(drawer, `${label}: Escape closes the drawer while focus is on ${name}`).toBeHidden();
      await expect(target, `${label}: focus stays on ${name}`).toBeFocused();
    }
  };
  /** Thai text nodes of the page that are letter-spaced (none may be): Thai has no capitals and its tone marks crowd. */
  const spacedThai = (target = page) => target.evaluate(() => {
    const walker = document.createTreeWalker(document.querySelector("main"), NodeFilter.SHOW_TEXT);
    const found = new Set();
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const element = node.parentElement;
      if (!element || !/[\u0E00-\u0E7F]/.test(node.textContent ?? "") || element.getClientRects().length === 0) continue;
      const spacing = getComputedStyle(element).letterSpacing;
      if (!["normal", "0px"].includes(spacing)) found.add(`${element.tagName}.${String(element.className).split(" ")[0]}: ${spacing} "${(node.textContent ?? "").trim().slice(0, 24)}"`);
    }
    return [...found];
  });
  /**
   * The time readout over every replay hour: no line of it is cut (scrollWidth within clientWidth), the bar keeps one
   * height and the map one place. Returns the widest line and the room it had.
   */
  const expectWholeReadout = async (label) => {
    const range = page.locator("input[type='range'][class*='range']");
    const seen = { widest: 0, room: Infinity, cut: [], barHeights: new Set(), mapTops: new Set() };
    for (let hour = 0; hour <= 264; hour += 1) {
      await range.fill(String(hour));
      // The width the text needs is measured on the text itself (a range), because scrollWidth never reads below
      // clientWidth and a nowrap line with an ellipsis reports no overflow in some engines.
      const state = await page.evaluate(() => [...document.querySelectorAll("[data-testid='replay-readout'] > *")].map((line) => {
        const range = document.createRange();
        range.selectNodeContents(line);
        return { text: line.textContent, need: Math.ceil(Math.max(range.getBoundingClientRect().width, line.scrollWidth > line.clientWidth ? line.scrollWidth : 0)), room: line.clientWidth };
      }));
      for (const line of state) {
        seen.widest = Math.max(seen.widest, line.need);
        seen.room = Math.min(seen.room, line.room);
        if (line.need > line.room) seen.cut.push(`hour ${hour}: "${line.text}" needs ${line.need} px, has ${line.room}`);
      }
      const geometry = await stageGeometry();
      seen.barHeights.add(geometry.barHeight);
      seen.mapTops.add(geometry.mapTop);
    }
    assert.deepEqual(seen.cut.slice(0, 5), [], `${label}: the time readout is never cut`);
    assert.deepEqual([seen.barHeights.size, seen.mapTops.size], [1, 1], `${label}: the bar and the map keep their place over the whole replay`);
    return seen;
  };
  /** Every glossary term: its definition opens on focus inside the viewport, and Escape closes it with focus kept. */
  const expectTooltips = async (label) => {
    const terms = page.locator("[class*='termLabel']");
    const count = await terms.count();
    assert(count >= 3, `${label}: the page has glossary terms (${count})`);
    let checked = 0;
    for (let index = 0; index < count; index += 1) {
      const term = terms.nth(index);
      if (!(await term.isVisible())) continue;
      await term.focus();
      const tip = term.locator("xpath=following-sibling::*[@role='tooltip']");
      await expect(tip).toBeVisible();
      const box = await tip.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        return { left: rect.left, right: rect.right, viewport: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth - window.innerWidth };
      });
      assert(box.left >= 0 && box.right <= box.viewport, `${label}: tooltip ${index} stays inside the viewport (${JSON.stringify(box)})`);
      assert(box.scroll <= 1, `${label}: tooltip ${index} adds no horizontal scroll (${box.scroll}px)`);
      await page.keyboard.press("Escape");
      await expect(tip).toBeHidden();
      await expect(term).toBeFocused();
      checked += 1;
    }
    assert(checked >= 3, `${label}: glossary tooltips were checked (${checked})`);
    await page.evaluate(() => document.activeElement?.blur());
    return checked;
  };
  /**
   * Save the PNG of this moment and measure the low-confidence hatch in it. The HAND raster's flag channel says which
   * cells are low-confidence and the hatch rule ((x + y) mod 6 < 2) says which of them lie on a stripe; the export is
   * sampled on a stripe and between stripes, in low-confidence water and, as a control, in ordinary water.
   */
  const exportedHatch = async () => {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save PNG of this moment" }).click()]);
    const png = readFileSync(await download.path()).toString("base64");
    const measured = await page.evaluate(async (base64) => {
      const pixels = async (blob) => {
        const bitmap = await createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
        const canvas = document.createElement("canvas");
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        context.drawImage(bitmap, 0, 0);
        return context.getImageData(0, 0, bitmap.width, bitmap.height);
      };
      const manifestUrl = performance.getEntriesByType("resource").map((entry) => entry.name).find((name) => name.endsWith("/timeline.json"));
      const manifest = await (await fetch(manifestUrl)).json();
      const hand = await pixels(await (await fetch(manifest.hand.href)).blob());
      const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
      const shot = await pixels(new Blob([bytes], { type: "image/png" }));
      // Portrait export: the map fills the full width from the top, with the HAND grid's aspect; the caption is below.
      const mapHeight = Math.round((shot.width * hand.height) / hand.width);
      const sx = shot.width / hand.width;
      const sy = mapHeight / hand.height;
      const cell = (x, y) => (y * hand.width + x) * 4;
      const low = (x, y) => hand.data[cell(x, y) + 2] >= 128;
      // Shallow ground that is not the channel: wet at the replay's peak whatever its depth factor.
      const shallow = (x, y) => hand.data[cell(x, y)] >= 1 && hand.data[cell(x, y)] <= 6;
      const colour = (x, y) => {
        const px = Math.min(shot.width - 1, Math.max(0, Math.round(x * sx - 0.5)));
        const py = Math.min(mapHeight - 1, Math.max(0, Math.round((y + 0.5) * sy - 0.5)));
        const at = (py * shot.width + px) * 4;
        return [shot.data[at], shot.data[at + 1], shot.data[at + 2], px, py];
      };
      const contrasts = { low: [], ordinary: [] };
      for (let y = 0; y < hand.height; y += 1) {
        for (let x = (6 - (y % 6)) % 6; x + 5 < hand.width; x += 6) {
          let lowRun = true;
          let ordinaryRun = true;
          for (let step = 0; step < 6; step += 1) {
            if (!shallow(x + step, y)) lowRun = ordinaryRun = false;
            else if (low(x + step, y)) ordinaryRun = false;
            else lowRun = false;
          }
          if (!lowRun && !ordinaryRun) continue;
          // Cells x and x + 1 are the stripe (sampled on their shared edge), x + 2 … x + 5 the wash between stripes.
          const stripe = colour(x + 1, y);
          const between = colour(x + 4, y);
          // The legend box covers the bottom-left corner of the map.
          if (stripe[4] > mapHeight - 340 && stripe[3] < 820) continue;
          (lowRun ? contrasts.low : contrasts.ordinary).push(Math.abs(stripe[0] - between[0]) + Math.abs(stripe[1] - between[1]) + Math.abs(stripe[2] - between[2]));
        }
      }
      const median = (values) => (values.length ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] : null);
      return {
        size: [shot.width, shot.height], mapHeight,
        low: { samples: contrasts.low.length, median: median(contrasts.low) },
        ordinary: { samples: contrasts.ordinary.length, median: median(contrasts.ordinary) },
      };
    }, png);
    return { name: download.suggestedFilename(), ...measured };
  };
  const expectHatchedExport = async (label) => {
    const hatch = await exportedHatch();
    assert(hatch.low.samples > 500 && hatch.ordinary.samples > 500, `${label}: enough water was sampled in the exported PNG (${JSON.stringify(hatch)})`);
    assert(hatch.low.median >= 24 && hatch.low.median >= 4 * (hatch.ordinary.median + 2),
      `${label}: low-confidence water is hatched in the exported PNG and ordinary water is not (${JSON.stringify(hatch)})`);
    return hatch;
  };
  /** The availability pill has hidden itself; it returns when the page goes offline, and again when it reconnects. */
  const expectPillReturns = async (label) => {
    const pill = page.locator("[data-pwa-auto-hide='true']");
    await expect(pill, `${label}: the availability pill hides itself on this page`).toHaveCount(0, { timeout: 12_000 });
    await context.setOffline(true);
    await expect(pill, `${label}: the pill returns when the page goes offline`).toBeVisible();
    await expect(pill).toContainText("Offline");
    await expect(pill, `${label}: the returned pill hides itself again`).toHaveCount(0, { timeout: 12_000 });
    await context.setOffline(false);
    await expect(pill, `${label}: the pill returns when the connection comes back`).toBeVisible();
    await expect(pill).toContainText("Online");
  };
  // --- Season envelope (UNOSAT and GISTDA product 4009, a scenario layer) -----------------------------------------
  const ENVELOPE_CREDIT = "UNOSAT and GISTDA · CC BY-SA 4.0";
  /** What an exported PNG or video says of the layer: the full credit, the licence with its address and a change note. */
  const ENVELOPE_EXPORT_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0)";
  const ENVELOPE_STANDARD = "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.";
  /** Fewest pixels of each stripe colour the exported PNG must gain with the layer on (measured: several times more). */
  const ENVELOPE_EXPORT_PIXELS = 5000;
  const ENVELOPE_CAPTION = "UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; the product is described to 22 Oct); includes August and early-October water; not an observation for any replay day. Clipped to Mae Sai district and rasterised to the replay grid by FloodGuard.";
  /** What the page shows of the envelope right now: its canvas on the map, the map credit, the chip, the caption, the legend entry. */
  const envelopeState = (target = page) => target.evaluate(() => ({
    canvases: document.querySelectorAll(".leaflet-fg-envelope-pane canvas").length,
    credit: document.querySelector(".leaflet-control-attribution")?.textContent ?? "",
    chip: document.querySelector("[data-testid='envelope-chip']")?.textContent ?? null,
    caption: document.querySelector("[data-testid='envelope-caption']")?.textContent ?? null,
    legend: document.querySelector("[data-testid='map-legend'] [data-testid='envelope-legend']")?.textContent ?? null,
    exportCredits: document.querySelector("[data-testid='export-credits']")?.textContent ?? "",
  }));
  /**
   * The hatch as it is on screen: the envelope's canvas is read back and its stripes measured along rows that lie
   * inside the envelope, then scaled by the size the canvas is drawn at. A flat fill would give one colour and no period.
   */
  const envelopeHatchOnScreen = (target = page) => target.evaluate(() => {
    const canvas = document.querySelector(".leaflet-fg-envelope-pane canvas");
    if (!canvas) return null;
    const box = canvas.getBoundingClientRect();
    const scale = box.width / canvas.width;
    const image = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    const colours = new Map();
    const runs = { dark: [], period: [] };
    for (let y = 16; y < canvas.height; y += 16) {
      let run = 0;
      let lastDarkStart = -1;
      for (let x = 0; x < canvas.width; x += 1) {
        const at = (y * canvas.width + x) * 4;
        const alpha = image[at + 3];
        if (alpha === 0) {
          run = 0;
          lastDarkStart = -1;
          continue;
        }
        const key = `${image[at]},${image[at + 1]},${image[at + 2]},${alpha}`;
        colours.set(key, (colours.get(key) ?? 0) + 1);
        const dark = image[at] < 100 && alpha > 200;
        if (dark) {
          if (run === 0) {
            if (lastDarkStart >= 0) runs.period.push(x - lastDarkStart);
            lastDarkStart = x;
          }
          run += 1;
        } else if (run > 0) {
          runs.dark.push(run);
          run = 0;
        }
      }
    }
    const median = (values) => (values.length ? [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)] : 0);
    const frame = document.querySelector("[class*='mapFrame']").getBoundingClientRect();
    return {
      colours: [...colours.entries()].sort((a, b) => b[1] - a[1]).map(([key]) => key),
      scale: Math.round(scale * 1000) / 1000,
      periodPx: Math.round(median(runs.period) * scale * 10) / 10,
      darkPx: Math.round(median(runs.dark) * scale * 10) / 10,
      samples: runs.period.length,
      onScreen: box.right > frame.left && box.left < frame.right && box.bottom > frame.top && box.top < frame.bottom,
    };
  });
  /**
   * The scenario chip as a reader sees it: inside the map frame, shown, and not cut off by a box that hides its overflow
   * (on phones the notes column drops what does not fit; the chip must never be among what is dropped).
   */
  const envelopeChipOnMap = (target = page) => target.evaluate(() => {
    const chip = document.querySelector("[data-testid='envelope-chip']");
    if (!chip) return { present: false };
    const frame = document.querySelector("[class*='mapFrame']").getBoundingClientRect();
    const box = chip.getBoundingClientRect();
    const inside = (outer) => box.left >= outer.left - 0.5 && box.right <= outer.right + 0.5 && box.top >= outer.top - 0.5 && box.bottom <= outer.bottom + 0.5;
    let hidden = false;
    let clipped = false;
    for (let node = chip; node && !String(node.className).includes("mapFrame"); node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) < 0.05) hidden = true;
      if (node !== chip && style.overflow !== "visible" && !inside(node.getBoundingClientRect())) clipped = true;
    }
    return { present: true, visible: box.width > 0 && box.height > 0 && !hidden && !clipped && inside(frame), hidden, clipped, box: [box.left, box.top, box.right, box.bottom].map(Math.round), parent: chip.parentElement.getAttribute("data-testid") };
  });
  /** The chip is visible inside the map while the layer is drawn (the layer never ships unlabelled). */
  const expectEnvelopeChipVisible = async (label, target = page) => {
    await expect.poll(async () => JSON.stringify(await envelopeChipOnMap(target)), { message: `${label}: the scenario chip is visible on the map`, timeout: 8000 }).toContain('"visible":true');
    const chip = await envelopeChipOnMap(target);
    assert.equal(chip.parent, "map-foot", `${label}: the chip sits in the bottom stack, which is never clipped (${JSON.stringify(chip)})`);
    return chip;
  };
  /** The envelope canvas's screen pixels per raster cell once a zoom has finished (two equal readings in a row). */
  const settledEnvelopeScale = async (target = page) => {
    let last = null;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const scale = (await envelopeHatchOnScreen(target))?.scale ?? null;
      if (scale !== null && scale === last) return scale;
      last = scale;
      await target.waitForTimeout(150);
    }
    throw new Error(`The map did not settle after a zoom (${last})`);
  };
  /** One click on a zoom button, waited for: the zoom control ignores a click that arrives during a zoom animation. */
  const zoomEnvelopeMap = async (direction, label) => {
    const before = await settledEnvelopeScale();
    await page.locator(`.leaflet-control-zoom-${direction}`).click();
    await expect.poll(async () => (await envelopeHatchOnScreen()).scale / before, { message: label })[direction === "in" ? "toBeGreaterThan" : "toBeLessThan"](direction === "in" ? 1.5 : 0.75);
    return settledEnvelopeScale();
  };
  /** The layer is on: canvas, chip, caption, legend entry, map credit and export credit; hatched with stripes a reader can see. */
  const expectEnvelopeShown = async (label, target = page, language = "en") => {
    await expect(target.locator(".leaflet-fg-envelope-pane canvas"), `${label}: the envelope layer is on the map`).toHaveCount(1);
    const state = await envelopeState(target);
    assert(state.credit.includes(ENVELOPE_CREDIT), `${label}: the map credit names UNOSAT and GISTDA and CC BY-SA 4.0 (${state.credit})`);
    assert(state.exportCredits.includes(ENVELOPE_EXPORT_CREDIT), `${label}: the export credit gives the full attribution and the licence with its address (${state.exportCredits})`);
    await expectEnvelopeChipVisible(label, target);
    if (language === "en") {
      assert.equal(state.chip, "Scenario (SCN-ENV): 2024 season envelope", `${label}: the scenario chip`);
      assert(state.exportCredits.includes(`${ENVELOPE_EXPORT_CREDIT} · clipped to Mae Sai district and rasterised by FloodGuard`), `${label}: the export credit says what FloodGuard changed (${state.exportCredits})`);
      // The standard sentence leads the caption: the reader is told under the map that the extent is preliminary and was not validated.
      assert(state.caption?.includes(`Scenario (SCN-ENV): 2024 season envelope. ${ENVELOPE_STANDARD} ${ENVELOPE_CAPTION}`) && state.caption.includes("Licence: CC BY-SA 4.0") && state.caption.includes("Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009."),
        `${label}: the caption under the map (${state.caption})`);
      assert(!/September extent|GISTDA's map/i.test(`${state.chip} ${state.caption} ${state.legend}`), `${label}: the layer is never called the September extent or GISTDA's map`);
    } else {
      assert.equal(state.chip, "สถานการณ์จำลอง (SCN-ENV): ขอบเขตน้ำตลอดฤดูปี 2567 (2024)", `${label}: the scenario chip in Thai`);
      assert(state.exportCredits.includes(`${ENVELOPE_EXPORT_CREDIT} · FloodGuard ตัดตามขอบเขตอำเภอแม่สายและแปลงเป็นราสเตอร์`), `${label}: the export credit says in Thai what FloodGuard changed (${state.exportCredits})`);
      assert(state.caption?.includes("ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู") && state.caption.includes("สัญญาอนุญาต: CC BY-SA 4.0") && state.caption.includes("เครดิต: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"),
        `${label}: the Thai caption under the map (${state.caption})`);
      assert(state.caption.includes("FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน") && !state.caption.includes("FloodGuard did not validate it"), `${label}: the Thai caption carries the standard sentence in Thai (${state.caption})`);
    }
    const hatch = await envelopeHatchOnScreen(target);
    assert(hatch && hatch.onScreen && hatch.samples > 150, `${label}: the envelope is drawn inside the map (${JSON.stringify(hatch)})`);
    // Hatched, not colour-only: a dark stripe, a yellow edge and a faint wash, with a period of about 9 px on screen.
    // (A canvas stores colours premultiplied, so the faint wash reads back a shade off; its opacity is what is checked.)
    assert(hatch.colours.length === 3 && hatch.colours.includes("38,30,0,235") && hatch.colours.includes("255,204,0,240") && hatch.colours.some((colour) => /^255,20\d,0,38$/.test(colour)),
      `${label}: the envelope is painted with its two stripe colours and its wash (${JSON.stringify(hatch.colours)})`);
    assert(hatch.periodPx >= 7 && hatch.periodPx <= 12 && hatch.darkPx >= 1.4 && hatch.darkPx <= 3.5, `${label}: the hatch stripes are visible on screen (${JSON.stringify(hatch)})`);
    return { ...state, hatch };
  };
  /** The layer is off: no canvas, no chip, no caption, no legend entry and no trace of its credit on the map or in the exports. */
  const expectEnvelopeHidden = async (label, target = page) => {
    const state = await envelopeState(target);
    assert.deepEqual([state.canvases, state.chip, state.caption, state.legend], [0, null, null, null], `${label}: the envelope layer is off (${JSON.stringify(state)})`);
    assert(!/CC BY-SA|UNOSAT|GISTDA/.test(state.credit), `${label}: the map credit does not name the envelope while it is hidden (${state.credit})`);
    assert(!/CC BY-SA|UNOSAT|GISTDA/.test(state.exportCredits), `${label}: the export credit does not name the envelope while it is hidden (${state.exportCredits})`);
  };
  /**
   * The sticky stage (bar, map, caption and timeline) while it is stuck to the top of the window: its bottom edge and the
   * bottom of the day buttons against the window's height. Positive values are pixels cut off below the window.
   */
  const stuckStage = async (target = page) => {
    await target.evaluate(() => window.scrollTo(0, 640));
    await target.waitForTimeout(150);
    return target.evaluate(() => {
      const section = document.querySelector("[class*='mapFrame']").parentElement;
      const stage = section.getBoundingClientRect();
      const days = [...section.querySelectorAll("button")].map((button) => button.getBoundingClientRect()).filter((box) => box.width > 0).map((box) => box.bottom);
      const caption = document.querySelector("[data-testid='envelope-caption']")?.getBoundingClientRect() ?? null;
      return {
        top: Math.round(stage.top), over: Math.round(stage.bottom - window.innerHeight), daysOver: Math.round(Math.max(...days) - window.innerHeight),
        map: Math.round(document.querySelector("[class*='mapFrame']").getBoundingClientRect().height), caption: caption ? Math.round(caption.height) : 0,
      };
    });
  };
  /** Yellow stripe pixels of the season envelope in the map part of the video's live preview (the recording canvas). */
  const previewStripes = () => page.evaluate(() => {
    const canvas = document.querySelector("[class*='videoPreview'] canvas");
    if (!canvas) return null;
    const data = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let yellow = 0;
    for (let at = 0; at < data.length; at += 4) if (data[at] > 215 && data[at + 1] > 170 && data[at + 1] < 225 && data[at + 2] < 70) yellow += 1;
    return { width: canvas.width, height: canvas.height, yellow };
  });
  /** Record a 16:9 video until the replay frames are being drawn, read its preview, and cancel. Null without MediaRecorder. */
  const recordedStripes = async () => {
    const button = page.getByRole("button", { name: /^Record video/ });
    if (!(await button.count())) return null;
    await page.getByRole("radio", { name: "16:9 (1280 × 720)" }).check();
    await button.click();
    const progress = page.getByRole("progressbar", { name: "Recording progress" });
    await expect(progress).toBeVisible();
    // The first second is the title card; the replay frames follow.
    await expect.poll(async () => progress.evaluate((element) => Number(element.value)), { message: "the recording reaches the replay frames", timeout: 20_000 }).toBeGreaterThanOrEqual(12);
    const stripes = await previewStripes();
    await page.getByRole("button", { name: "Cancel recording" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recording cancelled." })).toBeVisible();
    await page.getByRole("radio", { name: "Whole study area (portrait)" }).check();
    return stripes;
  };
  /** Save the PNG of this moment and return its size and how many pixels of its map are the envelope's stripe colours. */
  const exportedEnvelope = async () => {
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save PNG of this moment" }).click()]);
    const png = readFileSync(await download.path()).toString("base64");
    return page.evaluate(async (base64) => {
      const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
      const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(bitmap, 0, 0);
      const manifestUrl = performance.getEntriesByType("resource").map((entry) => entry.name).find((name) => name.endsWith("/timeline.json"));
      const manifest = await (await fetch(manifestUrl)).json();
      const mapHeight = Math.round((bitmap.width * manifest.hand.height) / manifest.hand.width);
      const data = context.getImageData(0, 0, bitmap.width, mapHeight).data;
      let dark = 0;
      let yellow = 0;
      for (let at = 0; at < data.length; at += 4) {
        // The stripe is near black with a brown cast (38, 30, 0 at 92% over the map), which dark imagery (grey, green
        // or blue) is not; its edge is a saturated yellow that no other layer uses.
        if (Math.abs(data[at] - 44) <= 12 && Math.abs(data[at + 1] - 36) <= 12 && data[at + 2] <= 20 && data[at] >= data[at + 1] + 3 && data[at + 1] >= data[at + 2] + 12) dark += 1;
        else if (data[at] > 215 && data[at + 1] > 170 && data[at + 1] < 225 && data[at + 2] < 70) yellow += 1;
      }
      return { width: bitmap.width, height: bitmap.height, mapHeight, band: bitmap.height - mapHeight, dark, yellow };
    }, png);
  };
  await visit(caseRoute, "Mae Sai flood, September 2024 — day by day");
  await expect(readout).toContainText("Mon 9 Sep 2024 · 12:00 ICT");
  await waterModel();
  await expect(page.getByText("Historical reconstruction for preparedness learning — not real-time, not an official warning.")).toBeVisible();
  // Above the fold at 1440 x 1000: Play (with the window and its length), the readout and the top of the map.
  const play = page.getByTestId("play-button");
  await expect(play).toContainText("Play 9 → 19 Sep");
  const fold = await page.evaluate(() => ({
    play: document.querySelector("[data-testid='play-button']").getBoundingClientRect().bottom,
    map: document.querySelector("[role='region'].leaflet-container, .leaflet-container").getBoundingClientRect().top,
    height: window.innerHeight,
  }));
  assert(fold.play < fold.height && fold.map + 200 < fold.height, `Play and the map start above the fold: ${JSON.stringify(fold)}`);
  await expect(page.locator("#mae-sai-map-layers")).toBeHidden();
  await expect(page.getByTestId("map-legend")).toContainText("Water depth (model)");
  await expect(page.getByTestId("low-confidence-legend")).toBeVisible();
  await expect(page.getByTestId("low-confidence-evidence")).toContainText("flat or filled low ground");
  // The 42 OpenStreetMap key facilities start hidden (the layer switch keeps them available).
  await expect(page.locator(".leaflet-fg-facilities-pane .leaflet-interactive")).toHaveCount(0);
  checks.push("Play, readout and map above the fold; layer controls folded into a drawer; low-confidence water in the on-map legend and the evidence");
  // Keyboard and layout fixes at 1440 px: the drawer takes focus, tooltips close on Escape, Play to Pause moves nothing.
  await expectDrawerFocus("1440 px");
  const desktopTips = await expectTooltips("1440 px");
  const desktopStage = await expectSteadyPlay("1440 px");
  assert.equal(desktopStage.barHeight, 66, `The desktop bar keeps its height (${JSON.stringify(desktopStage)})`);
  await expectClearMap(["zoom", "notes", "legend", "attribution"], "1440 px");
  checks.push(`desktop: opening "Map layers" moves focus into the drawer, Tab reaches its first control and Escape returns focus, and Escape closes it from Play and the slider too; ${desktopTips} glossary tooltips close on Escape; Play to Pause moves nothing`);
  // The narrow end of the two-column layout (a 1366 x 768 laptop at 125 % is 1093 x 614): Play, the whole time readout
  // and "Map layers" share one row at every replay hour, in English and in Thai, and no Thai text is letter-spaced.
  const narrowDesktop = [];
  for (const width of [1081, 1100, 1240]) {
    for (const language of ["en", "th"]) {
      await page.setViewportSize({ width, height: 614 });
      await page.goto(`${baseUrl}${caseRoute}?t=84&lang=${language}`, { waitUntil: "networkidle" });
      await waterModel();
      const columns = await page.evaluate(() => getComputedStyle(document.querySelector("[class*='layout']")).gridTemplateColumns.split(" ").length);
      assert.equal(columns, 2, `${width} px is in the two-column layout`);
      const readoutState = await expectWholeReadout(`${width} px (${language})`);
      const bar = await stageGeometry();
      assert.equal(bar.barHeight, 66, `${width} px (${language}): the bar keeps its one-row height (${JSON.stringify(bar)})`);
      // Headless Chromium draws no scrollbar; a classic one takes 17 px of the same viewport.
      assert(readoutState.room - readoutState.widest >= 17, `${width} px (${language}): the readout keeps room for a scrollbar (${readoutState.widest} px in ${readoutState.room} px)`);
      if (language === "th") assert.deepEqual(await spacedThai(), [], `${width} px: no Thai text is letter-spaced`);
      narrowDesktop.push(`${width} px ${language}: widest line ${readoutState.widest} px in ${readoutState.room} px`);
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${baseUrl}${caseRoute}?lang=th`, { waitUntil: "networkidle" });
  await waterModel();
  assert.deepEqual(await spacedThai(), [], "1440 px: no Thai text is letter-spaced (title, readout and header sub-label included)");
  // The language choice is remembered, so the page is set back to English before the checks below.
  await page.goto(`${baseUrl}${caseRoute}?lang=en`, { waitUntil: "networkidle" });
  await page.goto(`${baseUrl}${caseRoute}`, { waitUntil: "networkidle" });
  await expect(readout).toContainText("Mon 9 Sep 2024 · 12:00 ICT");
  await waterModel();
  checks.push(`narrow two-column desktop: the time readout is whole at all 265 replay hours on one 66 px row (${narrowDesktop.join("; ")}); no Thai text node is letter-spaced`);
  // Evidence envelope: the status and generation time, a licence per input, what was known during tuning, and the
  // radar line labelled calibration-informed. Both boxes are closed again so the layout below is unchanged.
  const howTo = page.getByTestId("how-to-read");
  await howTo.locator("summary").click();
  await expect(page.getByTestId("how-to-status")).toContainText("Status: non-operational");
  await expect(page.getByTestId("how-to-status").getByTestId("generated-at")).toHaveText(/Data files generated: \d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} ICT\./);
  await howTo.locator("summary").click();
  const sourcesPanel = page.getByTestId("sources-panel");
  await sourcesPanel.locator("summary").click();
  const licences = sourcesPanel.getByTestId("licences-by-input");
  await expect(licences).toBeVisible();
  for (const licence of ["CC BY-NC", "ODbL 1.0", "CC BY 4.0", "CC BY-IGO", "No licence stated by the provider", "CC BY-SA 4.0"]) await expect(licences).toContainText(licence);
  // Every input is shown. Product 4009 comes last: a season envelope scenario layer, with the date its rights record was confirmed.
  await expect(licences.locator("li[data-shown='false']")).toHaveCount(0);
  const envelopeLicence = licences.locator("li").filter({ hasText: "Shown as a season envelope scenario layer" });
  await expect(envelopeLicence).toHaveCount(1);
  await expect(envelopeLicence).toContainText("CC BY-SA 4.0");
  await expect(envelopeLicence).toContainText(/Shown as a season envelope scenario layer; the owners confirmed the rights record on \d{1,2} \w{3} \d{4}\./);
  // The envelope's own entry: licence, credit, change notice and its three files, each answering with the bytes the manifest lists.
  const envelopeSources = sourcesPanel.getByTestId("envelope-sources");
  await expect(envelopeSources).toContainText("Scenario (SCN-ENV): 2024 season envelope");
  await expect(envelopeSources.getByTestId("envelope-licence")).toContainText("Licence: CC BY-SA 4.0");
  await expect(envelopeSources.getByTestId("envelope-licence")).toContainText("Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.");
  await expect(envelopeSources).toContainText(ENVELOPE_STANDARD);
  // The statistics file's other inputs keep their own licences and credits.
  for (const needle of ["Copernicus DEM licence (free, attribution)", "CC BY 4.0; WorldPop (www.worldpop.org), University of Southampton", "CC BY-IGO; OCHA / HDX Thailand COD-AB"]) {
    await expect(envelopeSources.getByTestId("envelope-other-inputs")).toContainText(needle);
  }
  await expect(envelopeSources.getByTestId("envelope-change-notice")).toContainText(/Change notice: Changed by FloodGuard: clipped to Mae Sai district \(.+\); geometry repaired \(make_valid; \d+ parts repaired\); reprojected from EPSG:4326 to EPSG:3857; rasterised to about 15 m cells\./);
  const envelopeFiles = await page.evaluate(async () => {
    const manifestUrl = performance.getEntriesByType("resource").map((entry) => entry.name).find((name) => name.endsWith("/timeline.json"));
    const files = (await (await fetch(manifestUrl)).json()).season_envelope.files;
    return Promise.all(Object.entries(files).map(async ([key, file]) => {
      const response = await fetch(file.href);
      const buffer = await response.arrayBuffer();
      const digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
      return { key, href: file.href, ok: response.ok && digest === file.sha256 && buffer.byteLength === file.bytes };
    }));
  });
  assert.deepEqual(envelopeFiles.map((file) => [file.key, file.ok]), [["raster", true], ["statistics", true], ["licence", true]], "The envelope's three files answer with the bytes the manifest lists");
  assert.deepEqual(await envelopeSources.getByTestId("envelope-files").locator("a[download]").evaluateAll((links) => links.map((link) => link.getAttribute("href"))),
    envelopeFiles.map((file) => file.href), "The Sources panel links the raster, the statistics and the licence notice");
  assert(envelopeFiles[2].href.endsWith("/unosat4009/LICENSE"), "The licence notice ships beside the envelope's files");
  await expect(sourcesPanel.getByTestId("tuning-disclosure").locator("li[data-relation='used_for_tuning']")).toHaveCount(2);
  await expect(sourcesPanel.getByTestId("sources-footer")).toContainText("status: non-operational · Data files generated:");
  // "k" is the plan size on this page: the sources name the depth factor in words and write it f.
  const sourcesText = await sourcesPanel.innerText();
  assert(sourcesText.includes("scaled by the depth factor f = clip(") && sourcesText.includes("the exported depth factor f makes h + 0.3/f"), "The sources panel names the depth factor f");
  assert(!/(?<![A-Za-z0-9_])k(?![A-Za-z0-9_])/.test(sourcesText), "The sources panel shows no standalone k");
  // Export pack: download links under the standing sentence; each link answers from this origin with exactly the
  // bytes the manifest lists, and no link text or file name calls a modelled table a timetable of closures.
  const packInventory = await page.evaluate(async (budget) => {
    const manifestUrl = performance.getEntriesByType("resource").map((entry) => entry.name).find((name) => name.endsWith("/timeline.json"));
    const pack = (await (await fetch(manifestUrl)).json()).exports;
    return { budget_bytes: budget, bytes: pack.bytes, assets: pack.files.map((file) => ({ url: file.href, sha256: file.sha256, bytes: file.bytes })) };
  }, CASE_REPLAY_EXPORT_BUDGET_BYTES);
  assert.equal(packInventory.assets.reduce((sum, asset) => sum + asset.bytes, 0), packInventory.bytes, "The export pack's size is the sum of its files");
  const downloads = sourcesPanel.getByTestId("export-files");
  await expect(downloads.locator("a[download]")).toHaveCount(packInventory.assets.length);
  await expect(sourcesPanel.getByTestId("export-tier")).toContainText("T1 scenario (model): modelled, not observed.");
  await expect(sourcesPanel.getByTestId("export-tier")).toContainText("not a forecast, not an observed closure record and not an official warning");
  await expect(sourcesPanel.getByTestId("export-licence")).toContainText("under ODbL 1.0 (attribution and share-alike)");
  await expect(sourcesPanel.getByTestId("export-footer")).toContainText("Confidence: low");
  const downloadLinks = await downloads.locator("a[download]").evaluateAll((links) => links.map((link) => ({
    href: link.getAttribute("href"), name: link.getAttribute("download"), text: link.textContent, box: link.getBoundingClientRect().width,
  })));
  assert.deepEqual(downloadLinks.map((link) => link.href), packInventory.assets.map((asset) => asset.url), "Every export file has a download link, in the manifest's order");
  for (const link of downloadLinks) {
    assert(link.href.endsWith(`/exports/${link.name}`) && link.box > 0, `The download link is visible and saves under its file name (${link.name})`);
    assert(!/schedule|closure plan|cut-off list/i.test(`${link.name} ${link.text}`), `No download is named as a closure timetable (${link.name})`);
  }
  const downloaded = await page.evaluate(async (assets) => Promise.all(assets.map(async (asset) => {
    const response = await fetch(asset.url);
    const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
    return response.ok && [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("") === asset.sha256;
  })), packInventory.assets);
  assert(downloaded.every(Boolean), "Every download link answers with the bytes the manifest lists");
  assert(packInventory.bytes <= packInventory.budget_bytes, "The export pack is within its own budget");
  checks.push(`export pack: ${packInventory.assets.length} download links under the standing sentence (modelled, not observed), each answering with its hashed bytes (${packInventory.bytes} of ${packInventory.budget_bytes} export-budget bytes, outside the precache budget)`);
  // The water layer of 22 Oct 2024 (observed case O2 of the planning overlay) is one dated line: no layer, no slider position.
  const o2Line = sourcesPanel.getByTestId("separate-case-o2");
  await expect(o2Line).toBeVisible();
  await expect(o2Line).toContainText("22 Oct 2024 · UNOSAT and GISTDA water layer of 22 Oct 2024 (product 4009). A separate observed case, O2, in the planning overlay.");
  await expect(o2Line).toContainText("It is not on this map and has no position on the replay slider, which ends on 19 Sep 2024");
  checks.push("Sources panel: one dated line for the 22 Oct 2024 water layer (separate observed case O2), with no map layer and no slider position");
  await sourcesPanel.locator("summary").click();
  await expect(page.getByText("Radar size comparison (Sentinel-1", { exact: false })).toContainText("calibration-informed, not an independent check");
  // The size comparison pairs the 16 Sep pass with the 4 Sep pass of the same track; the cross-track pair is a sensitivity.
  await expect(page.getByText("Radar size comparison (Sentinel-1", { exact: false })).toContainText("4 Sep 06:16 ICT → 16 Sep 06:16 ICT; same track: descending, relative orbit 135");
  await expect(page.getByTestId("radar-sensitivity")).toContainText("Sensitivity, cross-track pair (6 Sep 18:31 ICT → 16 Sep 06:16 ICT; ascending, relative orbit 172");
  await expect(page.getByText("Radar check", { exact: false })).toHaveCount(0);
  checks.push("evidence fields on the page: non-operational status, generation time, licence per input with product 4009 shown as a season envelope scenario layer, its licence notice and files in the Sources panel, tuning disclosure, calibration-informed radar line; depth factor written f, never k");
  // Season envelope at 1440 px. Off by default, and no replay day turns it on: every hour of the replay and every day
  // button leaves the map, its credit and the export credit without it.
  await expectEnvelopeHidden("1440 px, as the page opens");
  for (let hour = 0; hour <= 264; hour += 6) {
    await slider.fill(String(hour));
    const state = await envelopeState();
    assert(state.canvases === 0 && state.chip === null && !state.credit.includes("CC BY-SA"), `Hour ${hour} does not select the season envelope (${JSON.stringify(state)})`);
  }
  for (const button of await page.getByRole("group", { name: "Jump to a day (local noon)" }).getByRole("button").all()) {
    await button.click();
    await expectEnvelopeHidden(`day button ${await button.innerText()}`);
  }
  // It is not among the day observation chips on the timeline, nor an imagery choice.
  const dayChips = await page.evaluate(() => [...document.querySelectorAll("[class*='obsMarker'], [class*='obsList'] li")].map((chip) => `${chip.textContent} ${chip.getAttribute("title") ?? ""}`));
  assert(dayChips.length >= 2 && !dayChips.some((chip) => /envelope|4009|UNOSAT|GISTDA/i.test(chip)), `The season envelope is not among the day observation chips (${dayChips.join(" | ")})`);
  await openLayers();
  const imageryOptions = await page.locator("#mae-sai-map-layers").getByLabel("Imagery", { exact: true }).locator("option").allInnerTexts();
  assert(!imageryOptions.some((option) => /envelope|4009/i.test(option)), `The season envelope is not an imagery choice (${imageryOptions.join(" | ")})`);
  // Its own toggle turns it on: chip, caption, hatched legend entry, map credit and export credit, clear of the other boxes.
  const envelopeToggle = page.getByRole("checkbox", { name: "2024 season envelope (scenario, hatched)" });
  await expect(page.getByTestId("envelope-toggle")).toContainText("Scenario layer (not tied to the replay hour)");
  await envelopeToggle.check();
  await page.locator("#mae-sai-map-layers").getByRole("button", { name: "Close", exact: true }).click();
  await slider.fill("84");
  const envelopeDesktop = await expectEnvelopeShown("1440 px");
  await expect(page).toHaveURL(/[?&]layers=[a-z]*e(&|$)/);
  await expect(page.getByTestId("map-legend").getByTestId("envelope-legend")).toContainText("Hatched: water mapped at some time from August to October 2024; not an observation for any replay day");
  await expectClearMap(["zoom", "notes", "legend", "envelope chip", "attribution"], "1440 px with the season envelope");
  // With the layer on, the hour still plays no part: every hour keeps the layer and its credit.
  for (let hour = 0; hour <= 264; hour += 24) {
    await slider.fill(String(hour));
    const state = await envelopeState();
    assert(state.canvases === 1 && state.credit.includes(ENVELOPE_CREDIT) && state.chip !== null, `Hour ${hour} keeps the season envelope on (${JSON.stringify(state)})`);
  }
  await slider.fill("84");
  // Zooming in repaints the hatch in whole raster cells: up to two screen pixels per cell the stripes keep about the
  // same width on screen.
  for (const step of [1, 2]) await zoomEnvelopeMap("in", `the map zooms in, step ${step}`);
  await expect.poll(async () => (await envelopeHatchOnScreen()).scale, { message: "the map zooms in" }).toBeGreaterThan(envelopeDesktop.hatch.scale * 3);
  await expect.poll(async () => (await envelopeHatchOnScreen()).periodPx, { message: "the hatch is repainted for the new zoom" }).toBeLessThanOrEqual(12);
  const envelopeZoomed = await envelopeHatchOnScreen();
  assert(envelopeZoomed.scale <= 2 && envelopeZoomed.periodPx >= 7 && envelopeZoomed.darkPx >= 1.4, `The hatch keeps its width on screen after zooming in (${JSON.stringify(envelopeZoomed)})`);
  // Closer in (street level) a stripe cannot be thinner than a cell: the period is four cells, so it grows with the zoom.
  for (const step of [3, 4]) await zoomEnvelopeMap("in", `the map zooms in, step ${step}`);
  await expect.poll(async () => (await envelopeHatchOnScreen()).scale, { message: "the map zooms in to street level" }).toBeGreaterThan(4);
  await expect.poll(async () => { const hatch = await envelopeHatchOnScreen(); return hatch.periodPx / hatch.scale; }, { message: "the hatch is four cells wide at street level" }).toBeCloseTo(4, 0);
  const envelopeStreet = await envelopeHatchOnScreen();
  assert(envelopeStreet.periodPx > 12 && envelopeStreet.darkPx >= 1.4 && envelopeStreet.colours.length === 3, `At street level the hatch is still a hatch, four cells wide (${JSON.stringify(envelopeStreet)})`);
  for (const step of [1, 2, 3, 4]) await zoomEnvelopeMap("out", `the map zooms back out, step ${step}`);
  // The comparison is the third group of the checks: plausibility, not validation, and never an independent check.
  const envelopeComparison = page.getByTestId("envelope-comparison");
  await expect(envelopeComparison).toContainText("Season envelope comparison (scenario; plausibility, not validation)");
  await expect(envelopeComparison).toContainText("Plausibility against a season envelope, not a validation.");
  await expect(envelopeComparison.getByTestId("envelope-district").locator("li[data-row='modelled_peak']")).toContainText(/\(3\.5 m stage\): agreement \(IoU\) 0\.48; 60\.5% of the modelled water lies inside the envelope; the modelled water reaches 70\.4% of the envelope\./);
  await expect(envelopeComparison.getByTestId("envelope-district").locator("li[data-row='largest_extent_13_19_sep']")).toContainText("(2.65 m stage): agreement (IoU) 0.46");
  await expect(envelopeComparison.getByTestId("envelope-disagreement")).toContainText("the comparison does not say which of the two is right");
  await expect(envelopeComparison.getByTestId("envelope-dsm")).toContainText("modelled water and residents in town are likely underestimated");
  const comparisonText = await envelopeComparison.innerText();
  assert(!/precision|recall|accuracy|validated|corroborat|too low|too high|September extent|GISTDA's map/i.test(comparisonText), "The envelope comparison uses none of the words it must not");
  await expect(page.getByText("Independent size checks", { exact: true })).toHaveCount(0);
  // The exported PNG draws the layer hatched and adds its full credit under the standing credits, wrapped onto whole
  // lines (a taller caption band); hidden, it does neither. The video draws it too: its live preview is read back.
  await expect(page.getByTestId("export-envelope")).toContainText("the PNG and the video draw it hatched, with its legend entry, its full credit, its licence and a note of what FloodGuard changed");
  const exportWith = await exportedEnvelope();
  const videoWith = await recordedStripes();
  await openLayers();
  await envelopeToggle.uncheck();
  await page.locator("#mae-sai-map-layers").getByRole("button", { name: "Close", exact: true }).click();
  await expectEnvelopeHidden("1440 px, after switching the layer off");
  await expect(page.getByTestId("export-envelope")).toHaveCount(0);
  const exportWithout = await exportedEnvelope();
  const videoWithout = await recordedStripes();
  const creditLine = (16 * exportWith.width) / 720;
  const creditLines = (exportWith.band - exportWithout.band) / creditLine;
  assert(exportWith.width === exportWithout.width && exportWith.mapHeight === exportWithout.mapHeight
    && creditLines >= 0.9 && creditLines <= 3.1 && Math.abs(creditLines - Math.round(creditLines)) < 0.1,
    `The exported PNG is taller by the whole lines of the envelope's credit (${JSON.stringify([exportWith, exportWithout, creditLines])})`);
  assert(exportWith.yellow > ENVELOPE_EXPORT_PIXELS && exportWith.yellow > 5 * (exportWithout.yellow + 50) && exportWith.dark > ENVELOPE_EXPORT_PIXELS && exportWith.dark > 5 * (exportWithout.dark + 50),
    `The exported PNG draws the envelope's two stripe colours only while the layer is on (${JSON.stringify([exportWith, exportWithout])})`);
  if (videoWith && videoWithout) {
    assert.deepEqual([videoWith.width, videoWith.height, videoWithout.width, videoWithout.height], [1280, 720, 1280, 720], "The 16:9 video is recorded at 1280 x 720 with and without the layer");
    assert(videoWith.yellow > 1500 && videoWith.yellow > 3 * (videoWithout.yellow + 50),
      `The recorded video draws the envelope's hatch only while the layer is on (${JSON.stringify([videoWith, videoWithout])})`);
  }
  await expect(page).not.toHaveURL(/[?&]layers=[a-z]*e(&|$)/);
  // A shared link restores the layer by its own letter, at any hour.
  await page.goto(`${baseUrl}${caseRoute}?t=10&layers=trsce`, { waitUntil: "networkidle" });
  await waterModel();
  await expect(readout).toContainText("Mon 9 Sep 2024 · 10:00 ICT");
  await expectEnvelopeShown("1440 px, shared link at 9 Sep 10:00");
  await page.goto(`${baseUrl}${caseRoute}`, { waitUntil: "networkidle" });
  await waterModel();
  await expectEnvelopeHidden("1440 px, link without the layer letter");
  checks.push(`season envelope (scenario, SCN-ENV) at 1440 px: off by default and selected by no replay hour or day button; its own toggle shows the chip, the caption with the standard sentence, a hatched legend entry and the layer (hatch period ${envelopeDesktop.hatch.periodPx} px, stripe ${envelopeDesktop.hatch.darkPx} px; ${envelopeZoomed.periodPx} px at ${envelopeZoomed.scale} px per cell; four cells, ${envelopeStreet.periodPx} px, at ${envelopeStreet.scale} px per cell), clear of zoom, notes, legend and attribution; the map credit adds "${ENVELOPE_CREDIT}" and the export credit the full attribution, the licence and the change note only while it is visible; the exported PNG draws it hatched (${exportWith.yellow} yellow and ${exportWith.dark} dark pixels against ${exportWithout.yellow} and ${exportWithout.dark}) on a band ${Math.round(creditLines)} credit lines taller${videoWith ? `; the 16:9 video preview holds ${videoWith.yellow} stripe pixels with the layer and ${videoWithout.yellow} without` : ""}; the comparison group says plausibility, not validation`);
  // The stage is sticky on wide screens: with the caption under the map it must still end inside the window, so the
  // day buttons of the timeline stay in view, at common laptop sizes, in English and in Thai.
  const stageFits = [];
  for (const [width, height] of [[1440, 1000], [1440, 900], [1366, 768], [1280, 720], [1093, 615]]) {
    await page.setViewportSize({ width, height });
    for (const language of ["en", "th"]) {
      await page.goto(`${baseUrl}${caseRoute}?t=84&layers=trsce&lang=${language}`, { waitUntil: "networkidle" });
      await waterModel();
      await expect(page.getByTestId("envelope-caption")).toBeVisible();
      await expect.poll(async () => (await stuckStage()).over, { message: `${width} x ${height} (${language}): the stage with the envelope's caption ends inside the window` }).toBeLessThanOrEqual(0);
      const fit = await stuckStage();
      assert(fit.top === 12 && fit.over <= 0 && fit.daysOver <= 0 && fit.caption > 40 && fit.map >= 220,
        `${width} x ${height} (${language}): the stuck stage, its day buttons and the caption fit the window (${JSON.stringify(fit)})`);
      stageFits.push(`${width}x${height} ${language}: map ${fit.map} px, caption ${fit.caption} px, ${-fit.over} px to spare`);
    }
    await page.goto(`${baseUrl}${caseRoute}?t=84&lang=en`, { waitUntil: "networkidle" });
    await waterModel();
    // Measure once the stage has stuck, as the checks with the layer do: on a slow runner the first scroll can land
    // before the page has settled. A stage that is genuinely too tall never sticks, so the assertion below still fails.
    await expect.poll(async () => (await stuckStage()).top, { message: `${width} x ${height}: the stage without the layer sticks under the header` }).toBe(12);
    const without = await stuckStage();
    assert(without.caption === 0 && without.map >= 360 && (height < 640 || without.over <= 0), `${width} x ${height}: without the layer the map keeps its usual height (${JSON.stringify(without)})`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  checks.push(`sticky stage with the season envelope's caption: the map gives up the caption's height, so the stage and its day buttons stay inside the window (${stageFits.join("; ")})`);
  // The envelope's two files load on their own. Without the raster the comparison keeps its figures and only the layer is
  // withheld; without the statistics, or with statistics the page cannot read, both are withheld. Each case says so by
  // the map, and the link no longer asks for the layer.
  const envelopeFailures = await context.newPage();
  const failureErrors = [];
  envelopeFailures.on("pageerror", (error) => failureErrors.push(error.message));
  await envelopeFailures.route("https://tile.openstreetmap.org/**", (route) => route.fulfill({ status: 200, contentType: "image/png", body: blankTile }));
  const failureReady = () => envelopeFailures.waitForFunction(() => !document.body.innerText.includes("Preparing the water model"), undefined, { timeout: 30_000 });
  await envelopeFailures.route("**/unosat4009/envelope.png", (route) => route.fulfill({ status: 404, body: "missing" }));
  await envelopeFailures.goto(`${baseUrl}${caseRoute}?t=84&layers=trsce`, { waitUntil: "networkidle" });
  await failureReady();
  const layerFailed = "The season envelope's map layer could not be loaded, so the layer is not shown. Its comparison figures are still shown under “Evidence for this moment”.";
  await expect(envelopeFailures.getByTestId("envelope-failed-map")).toBeVisible();
  await expect(envelopeFailures.getByTestId("envelope-failed-map")).toHaveText(layerFailed);
  await expect(envelopeFailures.getByTestId("envelope-failed-map")).toHaveAttribute("role", "status");
  await expectClearMap(["zoom", "notes", "legend", "envelope failure", "attribution"], "raster missing", envelopeFailures);
  await expect(envelopeFailures.locator(".leaflet-fg-envelope-pane canvas")).toHaveCount(0);
  await expect(envelopeFailures.getByTestId("envelope-chip")).toHaveCount(0);
  await expect(envelopeFailures.getByTestId("envelope-comparison").getByTestId("envelope-district").locator("li[data-row='modelled_peak']")).toContainText("agreement (IoU) 0.48");
  await expect(envelopeFailures.getByTestId("envelope-comparison").getByTestId("envelope-residents")).toContainText("about 17,927");
  await expect(envelopeFailures.getByTestId("envelope-comparison-status")).toHaveCount(0);
  await expect(envelopeFailures).not.toHaveURL(/[?&]layers=[a-z]*e(&|$)/);
  assert(!/CC BY-SA|UNOSAT/.test(await envelopeFailures.locator(".leaflet-control-attribution").innerText()), "A layer that is not drawn adds no credit to the map");
  await envelopeFailures.getByRole("button", { name: "Map layers", exact: true }).click();
  await expect(envelopeFailures.getByTestId("envelope-toggle")).toHaveCount(0);
  await expect(envelopeFailures.getByTestId("envelope-failed")).toHaveText(layerFailed);
  await envelopeFailures.unroute("**/unosat4009/envelope.png");
  const allFailed = "The season envelope could not be loaded, so its layer and its comparison are not shown.";
  const brokenStatistics = [
    ["statistics missing", (route) => route.fulfill({ status: 404, body: "missing" })],
    ["statistics without the residents block", async (route) => {
      const document = await (await route.fetch()).json();
      delete document.comparison.residents;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(document) });
    }],
    ["statistics without the lists of differences", async (route) => {
      const document = await (await route.fetch()).json();
      delete document.comparison.disagreement;
      delete document.comparison.low_confidence;
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(document) });
    }],
  ];
  for (const [name, handler] of brokenStatistics) {
    await envelopeFailures.route("**/unosat4009/envelope.json", handler);
    await envelopeFailures.goto(`${baseUrl}${caseRoute}?t=84&layers=trsce`, { waitUntil: "networkidle" });
    await failureReady();
    await expect(envelopeFailures.getByTestId("envelope-failed-map"), name).toHaveText(allFailed);
    await expect(envelopeFailures.getByTestId("envelope-comparison-status"), name).toHaveText("The figures of this comparison are not shown: its statistics file could not be loaded.");
    await expect(envelopeFailures.getByTestId("envelope-district"), name).toHaveCount(0);
    await expect(envelopeFailures.locator(".leaflet-fg-envelope-pane canvas"), name).toHaveCount(0);
    // The rest of the page is whole: the readout, the access card and the checks above the comparison.
    await expect(envelopeFailures.getByTestId("replay-readout"), name).toContainText("Thu 12 Sep 2024 · 12:00 ICT");
    await expect(envelopeFailures.getByTestId("access-card"), name).toBeVisible();
    await expect(envelopeFailures).not.toHaveURL(/[?&]layers=[a-z]*e(&|$)/);
    await envelopeFailures.unroute("**/unosat4009/envelope.json");
  }
  assert.deepEqual(failureErrors, [], "A missing or unreadable season-envelope file raises no client exception");
  await envelopeFailures.close();
  checks.push("season envelope files load on their own: without the raster the comparison keeps its figures and a note by the map says the layer is not shown; without readable statistics the layer and the comparison are withheld with their own sentences; the shared link drops the layer letter; no client exception");
  await slider.fill("84");
  await expect(readout).toContainText("Thu 12 Sep 2024 · 12:00 ICT");
  await expect(page).toHaveURL(/[?&]t=84(&|$)/);
  await slider.press("Shift+ArrowRight");
  await expect(readout).toContainText("Fri 13 Sep 2024 · 12:00 ICT");
  await slider.press("ArrowLeft");
  await expect(readout).toContainText("Fri 13 Sep 2024 · 11:00 ICT");
  checks.push("case replay renders and the hourly slider moves the readout");
  await openLayers();
  await page.getByRole("radio", { name: "First flooded (hour)" }).check();
  await expect(page.getByText("First flooded (model, local time)", { exact: true })).toBeVisible();
  await expect(page.getByText("Not yet flooded at this moment (faded)", { exact: true })).toBeVisible();
  await expect(page.getByTestId("map-legend").getByTestId("low-confidence-legend")).toBeVisible();
  await page.getByRole("radio", { name: "Hours under water" }).check();
  await expect(page.getByText("Hours under water, 9–19 Sep (model)", { exact: true })).toBeVisible();
  await expect(page.getByTestId("map-legend").getByTestId("low-confidence-legend")).toBeVisible();
  await page.getByRole("radio", { name: "Hours cut" }).check();
  await expect(page.getByText("Roads — hours impassable ≥ 0.3 m (model)", { exact: true })).toBeVisible();
  const routes = page.locator("section[aria-labelledby='mae-sai-route-cuts-title']");
  await expect(routes.getByText("Modelled, not observed closures", { exact: false })).toBeVisible();
  const firstRoute = routes.getByRole("button").first();
  await firstRoute.click();
  await expect(firstRoute).toHaveAttribute("aria-pressed", "true");
  // The selected route gets a halo (cyan under white, colours no road state uses) and a "Clear route selection" button.
  const halo = page.locator(".leaflet-fg-highlight-pane path");
  await expect(halo).toHaveCount(2);
  await page.getByRole("button", { name: "Clear route selection" }).click();
  await expect(firstRoute).toHaveAttribute("aria-pressed", "false");
  await expect(halo).toHaveCount(0);
  await firstRoute.click();
  await expect(firstRoute).toHaveAttribute("aria-pressed", "true");
  await routes.getByRole("button", { name: "Show the whole area" }).click();
  checks.push("water modes (depth, first flooded, hours under water), each with the low-confidence legend entry, and modelled road-cut hours with the Keep Routes Open list");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  const divider = page.getByRole("slider", { name: "Imagery comparison divider" });
  await expect(divider).toHaveAttribute("aria-valuenow", "50");
  await divider.focus();
  await divider.press("ArrowRight");
  await expect(divider).toHaveAttribute("aria-valuenow", "52");
  await expect(page.getByText("◀ 5 Sep 10:58 ICT · Sentinel-2", { exact: true })).toBeVisible();
  await expect(page.getByText("15 Sep 10:58 ICT · Sentinel-2 ▶", { exact: true })).toBeVisible();
  // While comparing, the model water is drawn faintly and the page says it is the model at the selected hour.
  await expect(page.getByTestId("compare-note")).toContainText("30%");
  await expect(page.getByTestId("compare-note")).toContainText("the model at the selected hour");
  await expect(page).toHaveURL(/cmp=s2-20240905,s2-20240915/);
  const clips = await page.evaluate(() => [...document.querySelectorAll(".leaflet-fg-compare-left-pane, .leaflet-fg-compare-right-pane")].map((pane) => getComputedStyle(pane).clipPath));
  assert(clips.length === 2 && clips.every((clip) => clip.startsWith("inset(")), `Swipe panes are clipped: ${JSON.stringify(clips)}`);
  checks.push("imagery swipe compare: keyboard divider, dated side labels, clipped panes");
  await expect(page).toHaveURL(/wm=duration/);
  await expect(page).toHaveURL(/rm=hours/);
  await page.reload({ waitUntil: "networkidle" });
  await expect(readout).toContainText("Fri 13 Sep 2024 · 11:00 ICT");
  await openLayers();
  await expect(page.getByRole("radio", { name: "Hours under water" })).toBeChecked();
  await expect(page.getByRole("radio", { name: "Hours cut" })).toBeChecked();
  await expect(page.getByRole("slider", { name: "Imagery comparison divider" })).toBeVisible();
  await page.getByRole("button", { name: "Copy link to this moment" }).click();
  await expect(page.getByText(/Link to this moment copied\.|select the link below and copy it/)).toBeVisible();
  await page.goto(`${baseUrl}${caseRoute}?t=99999&wm=flow&img=bogus&layers=zz&cmp=x,y&set=all&k=99`, { waitUntil: "networkidle" });
  await expect(readout).toContainText("Mon 9 Sep 2024 · 12:00 ICT");
  await openLayers();
  await expect(page.getByRole("radio", { name: "Depth at this moment" })).toBeChecked();
  await expect(page.getByRole("radio", { name: /^Reported used in Sep 2024/ })).toBeChecked();
  assert.equal(await page.getByRole("slider", { name: "Imagery comparison divider" }).count(), 0, "Invalid comparison falls back to off");
  checks.push("deep link restores the moment, modes and comparison; invalid parameters fall back to defaults");
  await waterModel();
  await slider.fill("84");
  const [still] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Save PNG of this moment" }).click()]);
  assert.equal(still.suggestedFilename(), "mae-sai-flood-2024-09-12-1200-ict.png");
  // The export draws the view on the map. Low-confidence water is hatched in it in the depth view and, as on the map,
  // in the first-flooded and hours-under-water views.
  await expect(page.getByTestId("export-view")).toHaveText("The PNG and the video show water depth (model), as on the map.");
  const hatches = { depth: await expectHatchedExport("depth view") };
  await openLayers();
  await page.getByRole("radio", { name: "First flooded (hour)" }).check();
  await expect(page.getByTestId("export-view")).toHaveText("The PNG and the video show the first flooded hour (model), as on the map.");
  hatches.arrival = await expectHatchedExport("first-flooded view");
  await page.getByRole("radio", { name: "Hours under water" }).check();
  await expect(page.getByTestId("export-view")).toHaveText("The PNG and the video show hours under water (model), as on the map.");
  hatches.duration = await expectHatchedExport("hours-under-water view");
  await page.getByRole("radio", { name: "Depth at this moment" }).check();
  checks.push(`low-confidence hatch in the exported PNG, stripe against wash (ordinary water as control): ${Object.entries(hatches).map(([view, hatch]) => `${view} ${hatch.low.median} (${hatch.ordinary.median})`).join(", ")}`);
  const record = page.getByRole("button", { name: /^Record video/ });
  if (await record.count()) {
    await expect(page.getByRole("radio", { name: "16:9 (1280 × 720)" })).toHaveCount(1);
    await record.click();
    await expect(page.getByRole("progressbar", { name: "Recording progress" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel recording" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recording cancelled." })).toBeVisible();
    // Cancel while the video is still being prepared (image decoding slowed so "Preparing" lasts): it must never start.
    await page.evaluate(() => {
      const original = HTMLImageElement.prototype.decode;
      window.__restoreImageDecode = () => { HTMLImageElement.prototype.decode = original; };
      HTMLImageElement.prototype.decode = function decode() {
        return new Promise((done) => window.setTimeout(done, 1500)).then(() => original.call(this));
      };
    });
    await record.click();
    await expect(page.getByRole("status").filter({ hasText: "Preparing the video…" })).toBeVisible();
    await page.getByRole("button", { name: "Cancel recording" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recording cancelled." })).toBeVisible();
    await page.waitForTimeout(2500);
    assert.equal(await page.getByRole("progressbar", { name: "Recording progress" }).count(), 0, "A recording cancelled while preparing never starts");
    await expect(page.getByRole("status").filter({ hasText: "Recording cancelled." })).toBeVisible();
    await page.evaluate(() => window.__restoreImageDecode?.());
  }
  checks.push(`PNG export of the moment${(await record.count()) ? " and cancellable video recording, including cancel while preparing" : " (video hidden without MediaRecorder)"}`);
  // Observed evidence: the VIIRS daily map for the day at or before the playhead (pixelated, deep-linked as "v"), its
  // clear-sky comparison card, and the hourly rain chart under the stage curve.
  await page.goto(`${baseUrl}${caseRoute}?t=158`, { waitUntil: "networkidle" });
  await waterModel();
  // 15 Sep 14:00: the first clear optical image after the flood is on screen, and the page says what its brown is.
  await expect(page.getByTestId("mud-cue")).toContainText("brown areas are consistent with mud left by floodwater (observed image; our reading)");
  await openLayers();
  await page.getByRole("checkbox", { name: "VIIRS daily flood map (375 m, observed)" }).check();
  await expect(page).toHaveURL(/[?&]layers=[a-z]*v/);
  const viirsImage = page.locator(".leaflet-fg-viirs-pane img");
  await expect(viirsImage).toHaveCount(1);
  await expect(viirsImage).toHaveAttribute("src", /viirs-20240915\.png$/);
  await page.waitForFunction(() => {
    const image = document.querySelector(".leaflet-fg-viirs-pane img");
    return Boolean(image && image.complete && image.naturalWidth > 0);
  });
  assert.equal(await viirsImage.evaluate((image) => getComputedStyle(image).imageRendering), "pixelated", "VIIRS pixels are drawn square");
  await expect(page.getByTestId("viirs-note")).toContainText("VIIRS daily flood map (observed, 375 m)");
  await expect(page.getByTestId("viirs-legend")).toBeVisible();
  const viirsCard = page.getByTestId("viirs-card");
  await expect(viirsCard.getByText("not a validation of the model", { exact: false })).toBeVisible();
  await expect(viirsCard.locator("tr[aria-current='date']")).toContainText("15 Sep");
  // 15 Sep has a second observation, the Sentinel-2 water check: the evidence list names both observations and says
  // what the larger observed area is consistent with (never what explains it); the comparison is labelled indicative.
  const s2Evidence = page.getByTestId("s2-evidence");
  await expect(s2Evidence).toContainText(/Observed \(Sentinel-2 L2A, 15 Sep 10:58 ICT, \d+% of the district clear\): \d+\.\d km² of water or saturated mud outside the mapped channels/);
  await expect(s2Evidence).toContainText("This comparison is indicative.");
  const observedReading = page.getByTestId("observed-reading");
  await expect(observedReading).toContainText("Two observations on this day: VIIRS (15 Sep 13:30 ICT, nominal)");
  await expect(observedReading).toContainText("and Sentinel-2 (15 Sep 10:58 ICT) shows");
  // The Sentinel-2 figures are given like for like: the water that is new since 5 Sep against the model where both dates are clear.
  await expect(observedReading).toContainText(/of which \d+\.\d km² is new since 5 Sep against the model's \d+\.\d km² where both dates are clear/);
  await expect(observedReading.getByTestId("s2-reading")).toHaveText("The larger observed area is consistent with water or saturated mud left after the river fell; the terrain-only model cannot hold water once the river level drops.");
  // The next clear VIIRS day shows less than the model, and the page says so beside the reading instead of leaving 15 Sep alone.
  const followingDay = observedReading.getByTestId("s2-following-day");
  await expect(followingDay).toContainText(/The next clear VIIRS map \(16 Sep 13:30 ICT, nominal\) shows \d+\.\d km² of flood water against the model's \d+\.\d km²/);
  await expect(followingDay).toContainText("is consistent with saturated mud or short-lived water rather than lasting ponding");
  await expect(observedReading).toContainText("not a flood extent");
  await expect(observedReading).not.toContainText(/explain|on fields/i);
  await expect(viirsCard.getByTestId("viirs-s2-note")).toContainText("Second observation on 15 Sep");
  await slider.fill("40");
  await expect(viirsImage).toHaveAttribute("src", /viirs-20240910\.png$/);
  // The water check is one observation of one day: on any other day the rows and the note are gone.
  await expect(page.getByTestId("s2-evidence")).toHaveCount(0);
  await expect(page.getByTestId("observed-reading")).toHaveCount(0);
  await expect(viirsCard.getByTestId("viirs-s2-note")).toHaveCount(0);
  await slider.fill("12");
  await expect(viirsImage).toHaveCount(0);
  await expect(page.getByTestId("viirs-note")).toContainText("no daily map");
  await expect(page.getByTestId("rain-chart")).toBeVisible();
  await expect(page.getByTestId("rain-now")).toContainText("MOU189");
  checks.push("observed VIIRS daily map (day at or before the playhead, pixelated, deep-linked) with its clear-sky comparison card, and the hourly rain chart");
  checks.push("15 Sep names both observations (VIIRS and the Sentinel-2 water check) with the consistent-with reading, the next clear VIIRS day beside it and the indicative label; no land cover named; no Sentinel-2 rows on another day");
  // Reported depths (news, not surveyed; roadmap C-2) at 1440 px: off by default and selected by no replay hour; their
  // own toggle draws one speech-bubble marker per point, with a legend entry; a popup gives the place, the paraphrase,
  // the time, the location confidence, the model at that point and the source link; the Sources panel has the counts.
  const depthMarkers = (target = page) => target.locator(".leaflet-fg-reported-depths-pane [class*='reportedDepthIcon']");
  const depthToggle = (target = page, name = "Reported depths (news, not surveyed)") => target.getByRole("checkbox", { name });
  const LOCATED_DEPTHS = ["ms-c2-01", "ms-c2-02", "ms-c2-07", "ms-c2-08", "ms-c2-09", "ms-c2-12", "ms-c2-14", "ms-c2-15", "ms-c2-18", "ms-c2-19", "ms-c2-20", "ms-c2-22"];
  /** Every located place record sits on exactly one marker (nearby places share a marker with a count); returns the marker count. */
  const expectDepthRecordsOnMarkers = async (label, target = page) => {
    const held = await depthMarkers(target).evaluateAll((markers) => markers.map((marker) => marker.dataset.reports ?? ""));
    assert.deepEqual(held.flatMap((ids) => ids.split(" ").filter(Boolean)).sort(), LOCATED_DEPTHS, `${label}: every located place record sits on exactly one marker (${held.join(" | ")})`);
    return held.length;
  };
  const waterReady = (target) => target.waitForFunction(() => !/Preparing the water model|กำลังเตรียมแบบจำลองน้ำ/.test(document.body.innerText), undefined, { timeout: 30_000 });
  /** Where each reported-depth marker's centre is on screen, and whether that point hits the marker itself. */
  const depthSpots = (target) => depthMarkers(target).evaluateAll((markers) => markers.map((marker) => {
    const box = marker.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const hit = document.elementFromPoint(x, y);
    // Map chrome (the legend chip, the notes, the layers drawer) is not a map object: a reader drags the map out from under it.
    const chrome = Boolean(hit) && !hit.closest(".leaflet-pane");
    const named = hit?.closest("[data-testid]");
    const what = hit ? `${hit.tagName} ${hit.className}`.trim().slice(0, 80) + (named ? ` in ${named.dataset.testid}` : "") : "nothing";
    return { x, y, width: box.width, reports: marker.dataset.reports, own: hit === marker || marker.contains(hit), chrome, hit: what };
  }));
  /** A point of the map that no chrome, control, marker or popup covers, nearest to the map's centre (null when there is none). */
  const clearMapPoint = (target) => target.locator(".leaflet-container").evaluate((element) => {
    const box = element.getBoundingClientRect();
    const free = [];
    for (let row = 2; row < 19; row += 1) {
      for (let col = 2; col < 19; col += 1) {
        const x = box.left + (box.width * col) / 20;
        const y = box.top + (box.height * row) / 20;
        if (y < 4 || y > window.innerHeight - 4) continue;
        const hit = document.elementFromPoint(x, y);
        if (hit && hit.closest(".leaflet-pane") && !hit.closest(".leaflet-marker-icon, .leaflet-popup")) free.push({ x, y });
      }
    }
    const cx = box.left + box.width / 2;
    const cy = box.top + box.height / 2;
    free.sort((a, b) => Math.hypot(a.x - cx, a.y - cy) - Math.hypot(b.x - cx, b.y - cy));
    return free[0] ?? null;
  });
  /** Drags the map so the point (x, y) moves to the map's centre, from a spot of the map that is no marker or control. */
  const centreMapOn = async (target, x, y) => {
    const map = await target.locator(".leaflet-container").boundingBox();
    await dragMapBy(target, map.x + map.width / 2 - x, map.y + map.height / 2 - y);
  };
  /** Drags the map by (dx, dy) px, from a spot of the map that is no marker or control. */
  const dragMapBy = async (target, dx, dy) => {
    const from = await target.locator(".leaflet-container").evaluate((element, [dx, dy]) => {
      const box = element.getBoundingClientRect();
      for (let row = 1; row < 10; row += 1) {
        for (let col = 1; col < 10; col += 1) {
          const sx = box.left + (box.width * col) / 10;
          const sy = box.top + (box.height * row) / 10;
          if (sx + dx < box.left + 8 || sx + dx > box.right - 8 || sy + dy < box.top + 8 || sy + dy > box.bottom - 8) continue;
          if (Math.min(sy, sy + dy) < 4 || Math.max(sy, sy + dy) > window.innerHeight - 4) continue;
          const hit = document.elementFromPoint(sx, sy);
          if (hit && element.contains(hit) && !hit.closest(".leaflet-marker-icon, .leaflet-control-container, .leaflet-popup")) return { x: sx, y: sy };
        }
      }
      return null;
    }, [dx, dy]);
    assert(from, `A free spot of the map to drag it by ${Math.round(dx)}, ${Math.round(dy)} px`);
    await target.mouse.move(from.x, from.y);
    await target.mouse.down();
    await target.mouse.move(from.x + dx, from.y + dy, { steps: 8 });
    await target.mouse.up();
    await target.waitForTimeout(350);
  };
  /**
   * Opens every reported-depth marker the way a reader does: the map scrolled into view and the town dragged to its
   * middle (optionally zoomed in around it with the wheel), then each marker brought to the middle of the map and opened
   * with a real pointer click (or a finger tap) at its centre. Nothing may cover the centre (not a shelter, not another
   * marker) and the popup must hold that marker's own records. The last popup is left open.
   */
  const expectDepthMarkersOpenTheirOwn = async (label, target, url, { tap = false, wheel = 0 } = {}) => {
    await target.goto(url, { waitUntil: "networkidle" });
    await waterReady(target);
    await target.locator(".leaflet-container").evaluate((map) => map.scrollIntoView({ block: "center", behavior: "instant" }));
    await target.waitForTimeout(200);
    const town = async () => {
      const spots = await depthSpots(target);
      return { x: spots.reduce((sum, spot) => sum + spot.x, 0) / spots.length, y: spots.reduce((sum, spot) => sum + spot.y, 0) / spots.length };
    };
    const middle = await town();
    await centreMapOn(target, middle.x, middle.y);
    if (wheel) {
      const around = await town();
      await target.mouse.move(around.x, around.y);
      await target.mouse.wheel(0, wheel);
      await target.waitForTimeout(900);
    }
    const count = await expectDepthRecordsOnMarkers(label, target);
    const popup = target.locator(".leaflet-popup-content [data-testid='reported-depth-popup']");
    const sizes = [];
    for (let index = 0; index < count; index += 1) {
      const before = (await depthSpots(target))[index];
      await centreMapOn(target, before.x, before.y);
      let spot = (await depthSpots(target))[index];
      assert(spot.width >= 24, `${label}: marker ${spot.reports} is at least 24 px wide (${spot.width})`);
      if (!spot.own && spot.chrome) {
        // Map chrome sits over the middle of this map (a legend chip on a narrow phone, say): bring the marker into the clear.
        const clear = await clearMapPoint(target);
        assert(clear, `${label}: the map keeps a clear spot to bring marker ${spot.reports} to (its centre is under ${spot.hit})`);
        await dragMapBy(target, clear.x - spot.x, clear.y - spot.y);
        spot = (await depthSpots(target))[index];
      }
      assert(spot.own, `${label}: no shelter, marker or map chrome covers the centre of marker ${spot.reports} once it is in the clear (${spot.hit})`);
      if (tap) await target.touchscreen.tap(spot.x, spot.y);
      else await target.mouse.click(spot.x, spot.y);
      await expect(popup, `${label}: marker ${spot.reports} opens a reported-depth popup`).toBeVisible();
      const shown = await popup.locator("section[data-report]").evaluateAll((sections) => sections.map((section) => section.dataset.report).join(" "));
      assert.equal(shown, spot.reports, `${label}: marker ${spot.reports} opens its own place records`);
      sizes.push(spot.reports.split(" ").length);
      if (index < count - 1) {
        await target.locator(".leaflet-popup-close-button").click();
        await expect(popup).toHaveCount(0);
      }
    }
    return sizes;
  };
  /** The counts table fits its card by itself (no sideways scroll inside it) and no header is squeezed to a sliver. */
  const expectDepthTableFits = async (label, target = page) => {
    const fit = await target.getByTestId("reported-depth-counts-scroll").evaluate((box) => ({
      need: box.scrollWidth, room: box.clientWidth,
      narrowest: Math.min(...[...box.querySelectorAll("th")].map((cell) => Math.round(cell.getBoundingClientRect().width))),
    }));
    assert(fit.need <= fit.room + 1, `${label}: the reported-depth counts table needs no sideways scroll (${JSON.stringify(fit)})`);
    assert(fit.narrowest >= 44, `${label}: every header of the reported-depth counts table is at least 44 px wide (${JSON.stringify(fit)})`);
    return fit;
  };
  await page.goto(`${baseUrl}${caseRoute}?t=84`, { waitUntil: "networkidle" });
  await waterModel();
  await expect(depthMarkers()).toHaveCount(0);
  for (const hour of ["0", "40", "84", "158", "264"]) {
    await slider.fill(hour);
    await expect(depthMarkers(), `hour ${hour} shows no reported depth while the layer is off`).toHaveCount(0);
  }
  await openLayers();
  await expect(depthToggle()).not.toBeChecked();
  await depthToggle().check();
  await expect(page).toHaveURL(/[?&]layers=[a-z]*d(&|$)/);
  const openingMarkers = await expectDepthRecordsOnMarkers("1440 px, opening view");
  for (const hour of ["0", "84", "264"]) {
    await slider.fill(hour);
    assert.equal(await expectDepthRecordsOnMarkers(`1440 px, hour ${hour}`), openingMarkers, `hour ${hour} keeps the reported depths on`);
  }
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(page.getByTestId("map-legend").getByTestId("reported-depth-legend")).toContainText("Reported depth (news, not surveyed); select for the report. A number counts the place records a marker holds");
  const depthTitles = await depthMarkers().evaluateAll((markers) => markers.map((marker) => marker.getAttribute("aria-label")));
  assert(depthTitles.every((title) => title?.startsWith("Reported depth (news, not surveyed): ")), `Every reported-depth marker names what it is (${depthTitles.join(" | ")})`);
  // Every marker opens its own records with a real click at its centre: at the opening zoom, where nearby places share a
  // marker, and zoomed in around the town, where they separate. The reported depths sit above the shelters.
  const depthUrl = `${baseUrl}${caseRoute}?t=84&layers=trscd`;
  const openedWide = await expectDepthMarkersOpenTheirOwn("1440 px", page, depthUrl);
  const openedZoomed = await expectDepthMarkersOpenTheirOwn("1440 px, zoomed in around the town", page, depthUrl, { wheel: -300 });
  assert(openedZoomed.length > openedWide.length, `Zooming in separates nearby places (${openedWide.length} markers, then ${openedZoomed.length})`);
  // The paraphrase, the time, the location confidence, the model and the link of one place record.
  await page.goto(depthUrl, { waitUntil: "networkidle" });
  await waterModel();
  await page.locator(".leaflet-fg-reported-depths-pane [data-reports~='ms-c2-01']").click();
  const depthPopup = page.locator(".leaflet-popup-content [data-testid='reported-depth-popup']");
  await expect(depthPopup).toBeVisible();
  const firstReport = depthPopup.locator("section[data-report='ms-c2-01']");
  await expect(firstReport).toContainText("Sai Lom Joy border market");
  await expect(firstReport).toContainText("Reported in news (not surveyed): more than 1 m (lower bound)");
  await expect(firstReport).toContainText("Thansettakij reports Sai River water spreading into the market area");
  await expect(firstReport).toContainText("When: Early morning of 10 Sep 2024 (article time-stamped 05:32 ICT)");
  await expect(firstReport).toContainText("Location: confidence medium (the reported spot may lie up to about 150 m away)");
  await expect(firstReport).toContainText("Model at this point, 10 Sep 00:00–05:32 ICT: dry");
  await expect(firstReport).toContainText("Comparison with the model: the model is dry here over the report's time window");
  await expect(firstReport.locator("a[href='https://www.thansettakij.com/news/general-news/606236']")).toHaveAttribute("target", "_blank");
  const popupText = await depthPopup.innerText();
  assert(!/confirm|validated|validation of/i.test(popupText), "A reported-depth popup never calls the comparison a validation or a confirmation");
  await expectClearMap(["zoom", "attribution", "popup"], "1440 px, reported-depth popup (notes and legend step aside)");
  await page.locator(".leaflet-popup-close-button").click();
  await expect(depthPopup).toHaveCount(0);
  // From the keyboard: Enter on a focused marker opens its popup and moves focus into it, Tab reaches its source link,
  // and Escape closes it and hands focus back to the marker.
  const keyedMarker = depthMarkers().first();
  const keyedRecords = await keyedMarker.getAttribute("data-reports");
  await keyedMarker.focus();
  await page.keyboard.press("Enter");
  await expect(depthPopup).toBeVisible();
  assert(await page.evaluate(() => Boolean(document.activeElement?.closest(".leaflet-popup"))), "Enter on a reported-depth marker moves focus into its popup");
  await page.keyboard.press("Tab");
  const tabbedTo = await page.evaluate(() => ({ tag: document.activeElement?.tagName, inPopup: Boolean(document.activeElement?.closest(".leaflet-popup")), href: document.activeElement?.getAttribute("href") }));
  assert(tabbedTo.tag === "A" && tabbedTo.inPopup && tabbedTo.href?.startsWith("https://"), `Tab reaches the popup's source link (${JSON.stringify(tabbedTo)})`);
  await page.keyboard.press("Escape");
  await expect(depthPopup).toHaveCount(0);
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-reports")), keyedRecords, "Escape closes the popup and focus returns to its marker");
  // The same for a reported-shelter star (the older markers share the keyboard path).
  const keyedStar = page.locator(".leaflet-fg-shelters-pane [class*='starIcon']").first();
  await keyedStar.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator(".leaflet-popup-content").filter({ hasText: "Sep 2024" })).toBeVisible();
  assert(await page.evaluate(() => Boolean(document.activeElement?.closest(".leaflet-popup"))), "Enter on a shelter star moves focus into its popup");
  await page.keyboard.press("Escape");
  await expect(page.locator(".leaflet-popup")).toHaveCount(0);
  assert(await keyedStar.evaluate((element) => element === document.activeElement), "Escape returns focus to the shelter star");
  // The counts table in the Sources panel: outcomes as rows; numbers, storey or body references, and all place records.
  const depthSources = page.getByTestId("sources-panel");
  await depthSources.locator("summary").click();
  const countsTable = depthSources.getByTestId("reported-depth-counts");
  await expect(countsTable).toBeVisible();
  await expect(countsTable.locator("tr[data-status='consistent'] td")).toHaveText(["1", "–", "1"]);
  await expect(countsTable.locator("tr[data-status='model_wet'] td")).toHaveText(["–", "2", "2"]);
  await expect(countsTable.locator("tr[data-status='model_dry'] td")).toHaveText(["6", "3", "9"]);
  await expect(depthSources.getByTestId("reported-depths-counted")).toContainText("21 place records from 17 statements in 14 news articles");
  await expect(depthSources.getByTestId("reported-depths-statements")).toContainText("1 with different outcomes at its places");
  const wideTable = await expectDepthTableFits("1440 px, English");
  await expect(depthSources.getByTestId("reported-depths-use")).toContainText("never a validation");
  await expect(depthSources.getByTestId("reported-depths-use")).toContainText("never used to tune the model");
  await expect(depthSources.getByTestId("reported-depths-causes").locator("li")).toHaveCount(4);
  await depthSources.locator("summary").click();
  await openLayers();
  await depthToggle().uncheck();
  await expect(depthMarkers()).toHaveCount(0);
  await expect(page).not.toHaveURL(/[?&]layers=[a-z]*d(&|$)/);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  checks.push(`reported depths (news, not surveyed) at 1440 px: off by default and selected by no replay hour; their own toggle draws the 12 located place records on ${openingMarkers} markers at the opening view (nearby places share a marker with a count), with a legend entry and the link letter d; a real click at each marker's centre opens its own records (${openedWide.length} markers, then ${openedZoomed.length} zoomed in around the town), nothing covering it; a popup gives the place, the paraphrase, the time, the location confidence, the model at that point and the source link, never a validation; Enter opens a marker's popup with focus inside, Tab reaches its link, Escape closes it and returns focus (reported-depth marker and shelter star); the Sources panel shows 21 place records from 17 statements in 14 articles and the counts with outcomes as rows (1 consistent, 2 model wet, 9 model dry), fitting its card (${wideTable.need} of ${wideTable.room} px)`);
  // While the residents raster is still loading, a resident view draws water depth, and the legend says exactly that.
  let releaseResidents;
  const residentsHeld = new Promise((release) => { releaseResidents = release; });
  await page.route("**/population-density.png", async (route) => {
    await residentsHeld;
    await route.continue();
  });
  await page.goto(`${baseUrl}${caseRoute}?t=84&wm=people`, { waitUntil: "domcontentloaded" });
  await expect(readout).toContainText("Thu 12 Sep 2024 · 12:00 ICT");
  await waterModel();
  const pendingLegend = page.getByTestId("map-legend");
  await expect(pendingLegend.getByTestId("legend-residents-pending")).toHaveText("The residents layer is still loading, so the map shows water depth until it is ready.");
  await expect(pendingLegend).toContainText("Water depth (model)");
  await expect(pendingLegend).not.toContainText("residents per hectare");
  await expect(pendingLegend.getByTestId("low-confidence-legend")).toBeVisible();
  releaseResidents();
  await expect(pendingLegend).toContainText("People in flood water: residents per hectare (WorldPop 2020, model)");
  await expect(pendingLegend.getByTestId("legend-residents-pending")).toHaveCount(0);
  await expect(pendingLegend).not.toContainText("Water depth (model)");
  await page.unroute("**/population-density.png");
  checks.push("the legend shows water depth, and says why, while the residents raster is loading; it switches with the map when the raster is ready");
  // Residents, the evacuation-access scenario and shelters (all model scenarios, never "observed").
  await page.goto(`${baseUrl}${caseRoute}?t=84`, { waitUntil: "networkidle" });
  await waterModel();
  await openLayers();
  await page.getByRole("radio", { name: "People in flood water" }).check();
  await expect(page.getByText("People in flood water: residents per hectare (WorldPop 2020, model)", { exact: true })).toBeVisible();
  await expect(page.getByTestId("people-in-water")).toHaveText(/^\d{1,3}(,\d{3})*$/);
  await page.getByRole("radio", { name: "All residents", exact: true }).check();
  await expect(page.getByText("All residents per hectare (WorldPop 2020, modelled)", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "People in flood water" }).check();
  await layersButton.click();
  await expect(page.locator("#mae-sai-map-layers")).toBeHidden();
  const accessCard = page.getByTestId("access-card");
  await expect(accessCard.getByText("Planning scenario, not observed evacuation outcomes", { exact: false })).toBeVisible();
  await expect(accessCard.getByTestId("access-without")).toContainText("/");
  // Both shelter sets side by side, each counted both ways with its own baseline; no single headline ranks them.
  const comparison = accessCard.getByTestId("set-comparison");
  await expect(comparison.getByTestId("set-comparison-label")).toContainText("T1 scenario (model)");
  await expect(comparison.getByTestId("set-comparison-label")).toContainText("No single figure ranks the sets");
  await expect(comparison.getByTestId("set-comparison-label")).toContainText("Hours from illustrative stage keyframes, not observed.");
  await expect(comparison.getByTestId("compare-reported-all-baseline")).toHaveText("34,525 of 81,799");
  await expect(comparison.getByTestId("compare-reported-all-lost")).toHaveText("7,086 of 34,525 (21%)");
  await expect(comparison.getByTestId("compare-reported-flooded-baseline")).toHaveText("5,698 of 14,169");
  await expect(comparison.getByTestId("compare-reported-flooded-keeping")).toHaveText("299");
  await expect(comparison.getByTestId("compare-reported-all-cutoff")).toContainText("Not reached in this replay");
  await expect(comparison.getByTestId("compare-plan-all-baseline")).toHaveText("24,910 of 81,799");
  await expect(comparison.getByTestId("compare-plan-all-lost")).toHaveText("13,429 of 24,910 (54%)");
  await expect(comparison.getByTestId("compare-plan-flooded-baseline")).toHaveText("7,580 of 14,169");
  await expect(comparison.getByTestId("compare-plan-flooded-keeping")).toHaveText("460");
  await expect(comparison.getByTestId("compare-plan-flooded-cutoff")).toHaveText("10 Sep 23:00");
  // The plan's table leads with its cut-off hour and explains its loss at the peak.
  const planRows = await comparison.getByTestId("set-compare-plan").locator("tbody tr th").allInnerTexts();
  assert(planRows.length === 4 && planRows[0].startsWith("Modelled access cut-off hour"), `The plan leads with the cut-off hour: ${planRows[0]}`);
  const reportedRows = await comparison.getByTestId("set-compare-reported").locator("tbody tr th").allInnerTexts();
  assert(reportedRows[0].startsWith("Had a shelter of this set within reach before the flood") && reportedRows[3].startsWith("Modelled access cut-off hour"),
    `The reported set is read baseline first, cut-off hour last: ${reportedRows.join(" | ")}`);
  await expect(comparison.getByTestId("plan-reading")).toContainText("it does not grade the choice of sites");
  await expect(comparison.getByTestId("set-compare-reported")).toHaveAttribute("data-selected", "");
  assert.equal(await accessCard.locator("[data-tone]").count(), 0, "The access card has no alert-toned headline figure");
  const accessText = await accessCard.innerText();
  assert(!/better plan|best plan|worse than|outperform|last safe departure/i.test(accessText), "The access card ranks no shelter set and names no safe departure time");
  // Like with like: by default the card counts the residents whose homes flood at the peak, as the plan does.
  await expect(accessCard.getByRole("radio", { name: /^Residents whose homes flood at the peak/ })).toBeChecked();
  await expect(accessCard.getByTestId("plan-optimises")).toContainText("What the ranked plan optimises");
  await accessCard.getByRole("radio", { name: /^All residents at road nodes/ }).check();
  await expect(page).toHaveURL(/[?&]pop=all(&|$)/);
  await accessCard.getByRole("radio", { name: /^Residents whose homes flood at the peak/ }).check();
  await expect(page).toHaveURL(/[?&]pop=flooded(&|$)/);
  // Evacuation Equity Gap (owner decision R8, option B): of the residents in each group who had a shelter within reach
  // before the flood, the share who lost it. The default view (reported set, residents whose homes flood) has no
  // proxy-vulnerable resident within reach, so it shows no ratio and says why in plain words.
  const equity = accessCard.getByTestId("equity-gap");
  await expect(equity).toContainText("terrain/remoteness proxy");
  await expect(equity).toHaveAttribute("data-reason", "insufficient_group_denominator");
  await expect(equity).toContainText("Evacuation Equity Gap: no ratio shown");
  await expect(equity).toContainText("No proxy-vulnerable resident counted here had a shelter within reach before the flood, so none could lose it. A ratio needs at least 50 such residents in each group.");
  await expect(equity.getByTestId("equity-rule")).toHaveText("What is compared. Of the residents in each group who had a shelter within reach before the flood, the share who lost it.");
  await expect(equity.getByTestId("equity-counts")).toHaveText(
    "Proxy-vulnerable: 0 lost of 0 within reach before the flood (103 residents counted). Everyone else: 5,400 lost of 5,698 within reach before the flood (14,067 residents counted).");
  await expect(equity.getByTestId("equity-label")).toContainText("T1 scenario (model). Vulnerable = terrain/remoteness proxy. Hours from illustrative stage keyframes, not observed.");
  await expect(equity.getByTestId("equity-why")).toHaveCount(0);
  // All residents at road nodes, reported set: none of the 2,440 proxy-vulnerable residents within reach lost access. Never "0.00".
  await accessCard.getByRole("radio", { name: /^All residents at road nodes/ }).check();
  await expect(equity).toContainText("Evacuation Equity Gap: no proxy-vulnerable resident has lost access · At this replay hour, 22.08% of everyone else who had a shelter within reach before the flood have lost it.");
  await expect(equity).not.toContainText("Evacuation Equity Gap: 0.00");
  await expect(equity.getByTestId("equity-counts")).toHaveText(
    "Proxy-vulnerable: 0 lost of 2,440 within reach before the flood (7,152 residents counted). Everyone else: 7,086 lost of 32,085 within reach before the flood (74,647 residents counted).");
  assert.equal(await equity.getAttribute("data-reason"), null, "With a ratio the equity block carries no reason");
  // All residents, ranked plan of 8 at the 3.5 m peak: 320 of 373 against 13,109 of 24,537, about 1.6 and "more likely".
  await accessCard.getByRole("radio", { name: "Ranked plan" }).check();
  await expect(equity).toContainText("Evacuation Equity Gap: 1.61 · Among residents with a shelter within reach before the flood, proxy-vulnerable residents are about 1.6× more likely to lose it (85.77% vs 53.42%).");
  await expect(equity.getByTestId("equity-counts")).toHaveText(
    "Proxy-vulnerable: 320 lost of 373 within reach before the flood (7,152 residents counted). Everyone else: 13,109 lost of 24,537 within reach before the flood (74,647 residents counted).");
  await expect(equity.getByTestId("equity-why")).toContainText("the ratio counts only residents who had a shelter of this set within reach before the flood. So a high ratio says where those homes sit");
  assert.equal(await equity.getAttribute("data-reason"), null, "The plan of 8 over all residents has a ratio");
  await equity.locator("details summary").click();
  await expect(equity.locator("details")).toContainText("by the residents of that group who had a shelter of this set within reach before the flood");
  await expect(equity.locator("details")).toContainText("No ratio is shown when a group has fewer than 50 residents within reach before the flood");
  assert(!/all residents counted in that group|less likely to lose (?:access|it)/.test(await equity.innerText()), "No rate on the card divides by all residents counted");
  await equity.locator("details summary").click();
  // Back to residents whose homes flood: 27 proxy-vulnerable residents are within reach of the plan's 8 sites, too few for a ratio.
  await accessCard.getByRole("radio", { name: /^Residents whose homes flood at the peak/ }).check();
  await expect(equity).toHaveAttribute("data-reason", "insufficient_group_denominator");
  await expect(equity).toContainText("Evacuation Equity Gap: no ratio shown · Only 27 proxy-vulnerable residents had a shelter within reach before the flood, fewer than the 50 a ratio needs in each group.");
  await expect(equity.getByTestId("equity-counts")).toContainText("Proxy-vulnerable: 27 lost of 27 within reach before the flood (103 residents counted).");
  await expect(page).toHaveURL(/[?&]pop=flooded(&|$)/);
  checks.push("Evacuation Equity Gap on the within-reach denominator (R8, option B): the rule in one sentence, 1.61 for the plan of 8 over all residents (320 of 373 against 13,109 of 24,537), no proxy-vulnerable loss for the reported set, no ratio with the reason in the default view, both counts per group");
  await accessCard.getByRole("radio", { name: "Ranked plan" }).check();
  const planSlider = accessCard.getByRole("slider", { name: /^Plan size k/ });
  await planSlider.fill("3");
  await expect(page).toHaveURL(/[?&]set=plan(&|$)/);
  await expect(page).toHaveURL(/[?&]k=3(&|$)/);
  await expect(accessCard.getByTestId("plan-k-sentence")).toContainText(/k = 3: 3 sites cover [\d,]+ of [\d,]+ residents whose homes flood \(\d+%\) · late evacuation \d+%/);
  await expect(page.locator(".leaflet-fg-shelters-pane [class*='planBadgeIcon']")).toHaveCount(3);
  // Markers name themselves on hover (subdistrict outlines already did).
  const star = page.locator(".leaflet-fg-shelters-pane [class*='starIcon']").first();
  await star.dispatchEvent("mouseover");
  await expect(page.locator(".leaflet-tooltip").filter({ hasText: "Reported shelter (2024)" })).toBeVisible();
  await star.dispatchEvent("mouseout");
  await accessCard.getByRole("checkbox", { name: /Show people cut off on the map/ }).check();
  await expect(page.locator(".leaflet-fg-cutoff-pane canvas")).toHaveCount(1);
  await expect(page.getByText("People cut off from a dry shelter (scenario)", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/[?&]layers=[a-z]*x/);
  const planCard = page.getByTestId("shelter-plan-card");
  await expect(planCard.getByText("Ranked range, not a fixed number", { exact: false })).toBeVisible();
  await expect(planCard.getByRole("slider", { name: /^Plan size k/ })).toHaveValue("3");
  // Desktop: the map column stays in view beside the cards (sticky), so a card's control changes a visible map.
  await planCard.scrollIntoViewIfNeeded();
  const mapTop = await page.evaluate(() => document.querySelector(".leaflet-container").getBoundingClientRect().top);
  assert(mapTop >= 0 && mapTop < 200, `The map stays in view beside the plan card (top ${mapTop}px)`);
  await expect(planCard.getByText("Shelter gap", { exact: true })).toBeVisible();
  // The capacity-aware view sits beside the plan (k = 3): both bounds, overflow = demand − fit, and the standing caveats.
  const capacityBlock = planCard.getByTestId("capacity-aware");
  await expect(capacityBlock.getByRole("heading", { name: "If capacity counts: who fits (two bounds)" })).toBeVisible();
  await expect(capacityBlock.getByTestId("capacity-coverage-lower")).toHaveText("385 overflow 13,784");
  await expect(capacityBlock.getByTestId("capacity-coverage-upper")).toHaveText("466 overflow 13,703");
  await expect(capacityBlock.getByTestId("capacity-aware-sentence")).toHaveText(
    "Reading for k = 3: 5,725 residents can walk to the first 3 sites of the plan above, and the capacity estimates hold 385 to 466 of them. That leaves 13,703 to 13,784 of the 14,169 without a place.");
  const capacityFigures = await capacityBlock.locator("td[data-testid^='capacity-']").evaluateAll((cells) => cells.map((cell) => cell.textContent.replaceAll(",", "").match(/\d+/g).map(Number)));
  assert(capacityFigures.length === 8 && capacityFigures.every(([served, overflow]) => served + overflow === 14169), `Every capacity cell keeps overflow = demand − fit (${JSON.stringify(capacityFigures)})`);
  for (let index = 0; index < capacityFigures.length; index += 2) {
    assert(capacityFigures[index][0] <= capacityFigures[index + 1][0], `The lower bound never exceeds the upper bound (${JSON.stringify(capacityFigures)})`);
  }
  const caveats = capacityBlock.getByTestId("capacity-caveats");
  await expect(caveats.locator("li")).toHaveCount(6);
  await expect(caveats).toContainText("T1 scenario (model)");
  await expect(caveats).toContainText("Neither bound is a limit on who fits.");
  await expect(capacityBlock.getByTestId("capacity-bound-upper")).toContainText("not a maximum");
  await expect(caveats).toContainText("That is an upper bound: many people stay with relatives");
  await expect(caveats).toContainText("Capacity is an unverified estimate from mapped building footprints");
  await expect(caveats).toContainText("candidates to verify on the ground, not a list of sites to open");
  await expect(caveats).toContainText("The planning overlay's listed-capacity figures come from a different source");
  // The site with 79 places carrying about 2,430 residents is flagged on its row and named in the note.
  await expect(planCard.locator("li[data-over-capacity]").first()).toContainText("≈ 79 places for ≈ 2,430 residents assigned");
  await expect(capacityBlock.getByTestId("over-capacity-note")).toContainText("≈ 79 places for ≈ 2,430 residents assigned (about 31 times the estimate)");
  await expect(planCard).not.toContainText(/open these shelters|shelters to open/i);
  // The capacity-aware ranking's own sites: closed until asked for, then load against capacity with the capacity basis.
  const capacitySites = capacityBlock.getByTestId("capacity-ranking-sites");
  await expect(capacitySites).not.toHaveAttribute("open", "");
  await capacitySites.locator("summary").click();
  await expect(capacitySites.locator("ol > li")).toHaveCount(3);
  await expect(capacitySites.locator("ol > li").first()).toContainText("Assigned 984 of 984 places (lower bound) · 984 of 984 (upper bound)");
  await expect(capacitySites.locator("ol > li").first()).toContainText("OpenStreetMap footprint × 0.5 ÷ 3.5 m² per person (Sphere), unverified");
  await expect(capacitySites.locator("ol > li[data-capacity-basis='unknown']").first()).toContainText("Capacity unknown (no mapped building footprint): 0 in the lower bound, 253 in the upper bound");
  await capacitySites.locator("summary").click();
  // What-if levels around the illustrative peak, not return periods, with the robust core marked on the plan list.
  const whatIf = planCard.getByTestId("what-if-levels");
  await expect(whatIf.getByTestId("what-if-label")).toContainText("What-if levels around an illustrative peak, not return periods.");
  await expect(whatIf.getByTestId("what-if-demand-2.5")).toHaveText("10,333");
  await expect(whatIf.getByTestId("what-if-demand-3.5")).toHaveText("14,169");
  await expect(whatIf.getByTestId("what-if-demand-4.0")).toHaveText("16,069");
  await expect(whatIf.getByTestId("robust-core-sentence")).toContainText("1 of the first 3 sites of the plan above is among the first 3 at every level");
  await expect(planCard.getByTestId("robust-core")).toHaveCount(1);
  await expect(planCard.getByTestId("robust-core")).toHaveText("Robust core: also among the first 3 sites at 2.5 m and 4.0 m");
  await expect(planCard).not.toContainText(/\b(?:25|100)[- ]?year/i);
  const planTables = await planCard.locator("[data-testid='capacity-aware-table'], [data-testid='what-if-table']")
    .evaluateAll((boxes) => boxes.map((box) => ({ need: box.querySelector("table").scrollWidth, room: box.clientWidth })));
  assert(planTables.length === 2 && planTables.every((box) => box.need <= box.room), `The capacity and what-if tables fit the plan card (${JSON.stringify(planTables)})`);
  checks.push("capacity-aware view beside the plan: both bounds with overflow = demand − fit and what each assumes, six caveats (neither bound is a limit), the 79-place site flagged, candidates to verify; what-if levels labelled as not return periods, robust core marked");
  // Local check of the candidates: no verification sheet has been returned, so the card says so and states no result.
  const verification = planCard.getByTestId("shelter-verification");
  await expect(verification).toHaveAttribute("data-status", "not_conducted");
  await expect(verification.getByTestId("verification-status")).toContainText("Not conducted. No verification sheet has been returned");
  await expect(verification.getByTestId("verification-sheet")).toContainText("“Checked by <role> on <date>; not an official shelter register”");
  await expect(verification.getByTestId("verification-rows")).toHaveCount(0);
  // No check was returned, so no site carries a local-check line and nothing says the plans ignore one.
  await expect(planCard.getByTestId("local-check")).toHaveCount(0);
  await expect(verification.getByTestId("verification-not-used")).toHaveCount(0);
  const sheetLink = verification.getByTestId("verification-sheet-link");
  await expect(sheetLink).toHaveAttribute("download", "shelter_candidate_verification_sheet.csv");
  const sheetFile = await page.evaluate(async (href) => {
    const bytes = new Uint8Array(await (await fetch(href)).arrayBuffer());
    return { bom: [...bytes.slice(0, 3)], text: new TextDecoder("utf-8").decode(bytes) };
  }, await sheetLink.getAttribute("href"));
  const sheetText = sheetFile.text;
  assert.deepEqual(sheetFile.bom, [0xef, 0xbb, 0xbf], "The blank sheet starts with a UTF-8 byte-order mark, so Excel reads its Thai text");
  assert(sheetText.includes("# verification_status,not_conducted"), "The blank sheet says no check was conducted");
  const sheetRows = sheetText.split("\n").filter((line) => /^C\d{3},/.test(line));
  assert(sheetRows.length === 95 && sheetRows.every((line) => line.endsWith(",,,,,")), "The sheet lists the 95 eligible candidates with the five checker columns empty");
  assert(sheetText.includes("Keep the lines that start with # and the first eight columns exactly as they are"), "The sheet tells the checker to keep its provenance lines and prefilled columns");
  assert(/capacity_basis_th \([^)]*[\u0E00-\u0E7F]/.test(sheetText) && sheetText.includes("ไม่ทราบ"), "The sheet gives the capacity basis in Thai beside the English phrase");
  checks.push("shelter-candidate check: not conducted, no result stated; the blank sheet downloads with 95 candidates and empty checker columns");
  await planCard.getByRole("button", { name: /^Show plan site 1, / }).click();
  // A closing popup fades out for a moment, so each check picks the popup by its text.
  const popupWith = (text) => page.locator(".leaflet-popup-content").filter({ hasText: text });
  await expect(popupWith("Plan rank 1 of the first 3")).toBeVisible();
  await expect(popupWith("Plan rank 1 of the first 3")).toContainText("planning scenario");
  const reportedCard = page.getByTestId("reported-shelters-card");
  await expect(page.locator(".leaflet-fg-shelters-pane [class*='starIcon']").first()).toBeAttached();
  // The card's first <details> is its confidence chip; the sites are the list items.
  await expect(reportedCard.getByTestId("reported-provenance")).not.toHaveAttribute("open", "");
  const firstReported = reportedCard.locator("li[data-role] > details").first();
  await firstReported.locator("summary").click();
  await firstReported.getByRole("button", { name: /^Show .+ on the map$/ }).click();
  await expect(popupWith("reported in use, Sep 2024")).toBeVisible();
  assert((await popupWith("reported in use, Sep 2024").locator("a[rel='noopener noreferrer']").count()) > 0, "Reported shelter popups link their sources");
  await expect(reportedCard.getByText("Not located on the map", { exact: false }).first()).toBeVisible();
  // The comparison follows the plan size, and the chosen set carries the "shown on the map" marker.
  await expect(comparison.getByTestId("set-compare-plan")).toHaveAttribute("data-selected", "");
  await expect(comparison.getByTestId("set-compare-plan").locator("caption")).toContainText("Ranked plan, first 3 sites");
  await expect(comparison.getByTestId("compare-plan-all-baseline")).toHaveText("17,794 of 81,799");
  checks.push("people in flood water and all-residents views, access scenario with population scope, set and k (live coverage sentence), cut-off heat, sticky map beside the cards, plan badges and sourced shelter popups");
  checks.push("shelter sets side by side: both denominators, own baseline and share, modelled access cut-off hour (leading for the plan), no ranking headline, equity never printed as 0.00");
  await page.reload({ waitUntil: "networkidle" });
  await openLayers();
  await expect(page.getByRole("radio", { name: "People in flood water" })).toBeChecked();
  await expect(page.getByRole("radio", { name: "Ranked plan" })).toBeChecked();
  await expect(page.getByTestId("access-card").getByRole("slider", { name: /^Plan size k/ })).toHaveValue("3");
  await expect(page.getByRole("checkbox", { name: "People cut off (scenario)" })).toBeChecked();
  checks.push("deep link restores the residents view, shelter set, plan size and cut-off layer");
  await page.screenshot({ path: resolve(artifacts, "case-replay-desktop.png"), fullPage: true });
  // Before the water rises nobody has lost access: counting all residents, no ratio is shown and the card says why.
  await page.goto(`${baseUrl}${caseRoute}?t=0&pop=all`, { waitUntil: "networkidle" });
  await waterModel();
  const dryEquity = page.getByTestId("access-card").getByTestId("equity-gap");
  await expect(dryEquity).toHaveAttribute("data-reason", "no_loss");
  await expect(dryEquity).toContainText("Evacuation Equity Gap: no ratio shown");
  await expect(dryEquity).toContainText("No one in either group has lost access at this replay hour");
  await expect(dryEquity.getByTestId("equity-counts")).toContainText("Proxy-vulnerable: 0 lost of 2,440 within reach before the flood (7,152 residents counted). Everyone else: 0 lost of 32,085");
  await expect(page.getByTestId("access-card").getByTestId("compare-reported-all-lost")).toHaveText("0 of 34,525 (0%)");
  // Among residents whose homes flood the reason is the group size at every hour: it does not change as the water rises.
  await page.getByTestId("access-card").getByRole("radio", { name: /^Residents whose homes flood at the peak/ }).check();
  await expect(dryEquity).toHaveAttribute("data-reason", "insufficient_group_denominator");
  await expect(dryEquity).toContainText("No proxy-vulnerable resident counted here had a shelter within reach before the flood, so none could lose it.");
  checks.push("equity gap gives no ratio, with the reason, before anyone has lost access; a group with too few residents within reach keeps that reason at every hour");
  const envelopePhones = [];
  for (const width of [360, 390]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`${baseUrl}${caseRoute}?t=84`, { waitUntil: "networkidle" });
    await expect(readout).toContainText("Thu 12 Sep 2024 · 12:00 ICT");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) {
      await page.screenshot({ path: resolve(artifacts, `case-replay-overflow-${width}.png`), fullPage: true });
      assert.fail(`Case replay overflows by ${overflow}px at ${width}px`);
    }
    const clipped = await page.evaluate(() => [...document.querySelectorAll("[class*='segmentFull'], [class*='segmentShort']")]
      .filter((label) => label.getClientRects().length > 0 && label.scrollWidth > label.clientWidth + 1)
      .map((label) => label.textContent));
    assert.deepEqual(clipped, [], `Phase labels are not truncated at ${width}px`);
    await expect(page.getByRole("list", { name: "Event phases" })).toContainText("Peak");
    const chipHeights = await page.getByRole("group", { name: "Jump to a day (local noon)" }).getByRole("button")
      .evaluateAll((buttons) => buttons.map((button) => Math.round(button.getBoundingClientRect().height)));
    assert(chipHeights.length === 11 && chipHeights.every((height) => height >= 40), `Day chips are finger-sized at ${width}px: ${chipHeights}`);
    const noScroll = async (state) => {
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      assert(scroll <= 1, `No horizontal scroll at ${width}px ${state} (${scroll}px)`);
    };
    const at = `${width} px`;
    await waterModel();
    // The bar above the map is a fixed grid: Play to Pause, and every hour of the replay, leave the map where it is.
    const steady = await expectSteadyPlay(at);
    const barHeights = new Set();
    const mapTops = new Set();
    for (let hour = 0; hour <= 264; hour += 12) {
      await slider.fill(String(hour));
      const geometry = await stageGeometry();
      barHeights.add(geometry.barHeight);
      mapTops.add(geometry.mapTop);
    }
    assert.deepEqual([[...barHeights], [...mapTops]], [[steady.barHeight], [steady.mapTop]], `The bar and the map keep their place over the whole replay at ${at}`);
    await expectDrawerFocus(at);
    await expectTooltips(at);
    await noScroll("after the tooltips");
    // The availability pill hides itself here and returns when the connection status changes.
    await expectPillReturns(at);
    // 15 Sep 14:00 with the VIIRS layer: the imagery caption, the mud cue and the VIIRS note are all on the map.
    await page.goto(`${baseUrl}${caseRoute}?t=158&layers=trscv`, { waitUntil: "networkidle" });
    await waterModel();
    await expect(page.getByTestId("viirs-note")).toBeVisible();
    await expect(page.getByTestId("mud-cue")).toBeVisible();
    await expectClearMap(["zoom", "notes", "legend", "attribution"], `${at}, three notes`);
    // The season envelope on a phone: its chip joins the notes, its credit the attribution, and its caption sits under
    // the map. The hatch is still a hatch at this size, and nothing overlaps or scrolls sideways.
    await page.goto(`${baseUrl}${caseRoute}?t=84&layers=trsce`, { waitUntil: "networkidle" });
    await waterModel();
    const envelopePhone = await expectEnvelopeShown(at);
    await expectClearMap(["zoom", "notes", "legend", "envelope chip", "attribution"], `${at} with the season envelope`);
    await noScroll("with the season envelope");
    const captionFit = await page.getByTestId("envelope-caption").evaluate((caption) => {
      const frame = document.querySelector("[class*='mapFrame']").getBoundingClientRect();
      const box = caption.getBoundingClientRect();
      return { need: caption.scrollWidth, room: caption.clientWidth, below: box.top >= frame.bottom - 0.5, inside: box.right <= window.innerWidth + 0.5 };
    });
    assert(captionFit.need <= captionFit.room && captionFit.below && captionFit.inside, `${at}: the envelope's caption fits under the map (${JSON.stringify(captionFit)})`);
    // Three notes and the envelope's chip together (15 Sep 14:00 with the VIIRS layer): still clear of each other.
    await page.goto(`${baseUrl}${caseRoute}?t=158&layers=trscve`, { waitUntil: "networkidle" });
    await waterModel();
    await expect(page.getByTestId("envelope-chip")).toBeVisible();
    await expectClearMap(["zoom", "notes", "legend", "envelope chip", "attribution"], `${at}, three notes and the season envelope`);
    await noScroll("with three notes and the season envelope");
    // With the legend open the notes step aside; the chip does not.
    await page.getByTestId("map-legend").locator("> summary").click();
    await expectClearMap(["zoom", "legend", "envelope chip", "attribution"], `${at}, legend open with the season envelope`);
    await expectEnvelopeChipVisible(`${at}, legend open`);
    await page.getByTestId("map-legend").locator("> summary").click();
    // The imagery swipe with the layer on: the notes column drops what does not fit under the side labels, and the chip
    // is not in it, so the hatched layer is never on the map without its label. One note and three, English and Thai.
    for (const [query, state] of [["?t=84&layers=trsce&cmp=s2-20240905,s2-20240915", "swipe with the season envelope"],
      ["?t=158&layers=trscve&cmp=s2-20240905,s2-20240915", "swipe with three notes and the season envelope"],
      ["?t=84&layers=trsce&cmp=s2-20240905,s2-20240915&lang=th", "swipe with the season envelope in Thai"],
      ["?t=158&layers=trscve&cmp=s2-20240905,s2-20240915&lang=th", "swipe with three notes and the season envelope in Thai"]]) {
      await page.goto(`${baseUrl}${caseRoute}${query}`, { waitUntil: "networkidle" });
      await waterModel();
      await expect(page.locator(".leaflet-fg-envelope-pane canvas"), `${at}, ${state}: the layer is drawn`).toHaveCount(1);
      await expectEnvelopeChipVisible(`${at}, ${state}`);
      await expectClearMap(["zoom", "notes", "legend", "envelope chip", "attribution", "left label", "right label", "divider handle"], `${at}, ${state}`);
      await noScroll(state);
    }
    await page.goto(`${baseUrl}${caseRoute}?t=158&layers=trscve&lang=en`, { waitUntil: "networkidle" });
    await waterModel();
    envelopePhones.push(`${at}: hatch period ${envelopePhone.hatch.periodPx} px, stripe ${envelopePhone.hatch.darkPx} px`);
    // The imagery swipe: both side labels (they wrap here), the divider's handle, the notes, the legend and the zoom
    // control are clear of each other, with one note and with three, in English and in Thai.
    for (const [query, state] of [["?t=84&cmp=s2-20240905,s2-20240915", "swipe"], ["?t=158&layers=trscv&cmp=s2-20240905,s2-20240915", "swipe with three notes"],
      ["?t=84&cmp=s2-20240905,s2-20240915&lang=th", "swipe in Thai"]]) {
      await page.goto(`${baseUrl}${caseRoute}${query}`, { waitUntil: "networkidle" });
      await waterModel();
      await expect(page.getByTestId("compare-note")).toBeVisible();
      const swipe = await expectClearMap(["zoom", "notes", "legend", "attribution", "left label", "right label", "divider handle"], `${at}, ${state}`);
      const edges = await page.evaluate(() => {
        const box = (selector) => document.querySelector(selector).getBoundingClientRect();
        const frame = box("[class*='mapFrame']");
        return { labelLeft: Math.round(box("[data-testid='compare-label-left']").left - frame.left), zoomRight: Math.round(box(".leaflet-control-zoom").right - frame.left) };
      });
      assert(edges.labelLeft >= edges.zoomRight + 4, `${at}, ${state}: the left label keeps clear of the zoom control (${JSON.stringify(edges)})`);
      assert(swipe.shown.includes("notes"), `${at}, ${state}: the comparison note is on the map`);
      await noScroll(state);
    }
    // Back to English (the language choice is remembered) for the checks below.
    await page.goto(`${baseUrl}${caseRoute}?t=158&layers=trscv&lang=en`, { waitUntil: "networkidle" });
    await waterModel();
    // Offline with a route selected: the basemap note and "Clear route selection" share one stack above the attribution.
    await context.setOffline(true);
    await page.getByTestId("basemap-note").waitFor({ state: "visible" });
    await expect(page.getByTestId("basemap-note")).toContainText("Offline: the street basemap is online-only.");
    const phoneRoute = page.locator("section[aria-labelledby='mae-sai-route-cuts-title']").getByRole("button").first();
    await phoneRoute.click();
    await expect(phoneRoute).toHaveAttribute("aria-pressed", "true");
    await expectClearMap(["zoom", "notes", "legend", "basemap note", "clear route", "attribution"], `${at}, offline with a route selected`);
    const stack = await page.evaluate(() => {
      const note = document.querySelector("[data-testid='basemap-note']");
      const clear = document.querySelector("[data-testid='clear-route']");
      return { sameStack: note.parentElement === clear.parentElement, noteAbove: note.getBoundingClientRect().bottom <= clear.getBoundingClientRect().top };
    });
    assert(stack.sameStack && stack.noteAbove, `The basemap note and "Clear route selection" share one stack at ${at}`);
    // The open legend takes the notes' place on a phone, still clear of the stack below it.
    await page.getByTestId("map-legend").locator("> summary").click();
    await expectClearMap(["zoom", "legend", "basemap note", "clear route", "attribution"], `${at}, legend open (the notes step aside)`);
    await page.getByTestId("map-legend").locator("> summary").click();
    await noScroll("offline with a route selected");
    // Popups: a reported shelter (its long text scrolls inside the popup) and a ranked plan site. Each stays inside
    // the map, clear of the zoom buttons, the basemap note and the attribution; notes and legend step aside.
    const reportedSite = page.getByTestId("reported-shelters-card").locator("li[data-role] > details").first();
    await reportedSite.locator("summary").click();
    await reportedSite.getByRole("button", { name: /^Show .+ on the map$/ }).click();
    await expect(page.locator(".leaflet-popup-content").filter({ hasText: "reported in use, Sep 2024" })).toBeVisible();
    await expectClearMap(["zoom", "basemap note", "attribution", "popup"], `${at}, reported-shelter popup (notes and legend step aside)`);
    const popupScroll = await page.locator(".leaflet-popup-content").filter({ hasText: "reported in use, Sep 2024" }).evaluate((element) => ({
      height: Math.round(element.getBoundingClientRect().height), content: element.scrollHeight, overflow: getComputedStyle(element).overflowY,
    }));
    assert(popupScroll.height <= 300 && (popupScroll.content <= popupScroll.height + 1 || popupScroll.overflow === "auto"),
      `A popup taller than the map allows scrolls inside itself at ${at} (${JSON.stringify(popupScroll)})`);
    await page.getByTestId("shelter-plan-card").getByRole("button", { name: /^Show plan site 1, / }).click();
    await expect(page.locator(".leaflet-popup-content").filter({ hasText: "Plan rank 1 of the first" })).toBeVisible();
    await expectClearMap(["zoom", "basemap note", "attribution", "popup"], `${at}, plan-site popup (notes and legend step aside)`);
    await noScroll("with a popup open");
    await context.setOffline(false);
    if (width === 360) {
      // The PNG is drawn off screen at its own size, so one phone width is enough: hatch pixels in the first-flooded view.
      await page.goto(`${baseUrl}${caseRoute}?t=84&wm=arrival`, { waitUntil: "networkidle" });
      await waterModel();
      await expect(page.getByTestId("export-view")).toHaveText("The PNG and the video show the first flooded hour (model), as on the map.");
      await expectHatchedExport(`first-flooded view at ${at}`);
    }
  }
  // Reported depths on a 390 px phone (English): the markers by link, a popup inside the map and the screen, clear of the
  // zoom buttons and the attribution, the counts table in the Sources panel, and no horizontal scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  const phoneOpened = await expectDepthMarkersOpenTheirOwn("390 px", page, `${baseUrl}${caseRoute}?t=84&layers=trscd`);
  await expect(page.locator(".leaflet-popup-content [data-testid='reported-depth-popup']")).toBeVisible();
  await expectClearMap(["zoom", "attribution", "popup"], "390 px, reported-depth popup (notes and legend step aside)");
  const phoneDepthPopup = await page.locator(".leaflet-popup").evaluate((popup) => {
    const box = popup.getBoundingClientRect();
    return { left: Math.round(box.left), right: Math.round(box.right), width: window.innerWidth };
  });
  assert(phoneDepthPopup.left >= 0 && phoneDepthPopup.right <= phoneDepthPopup.width, `The reported-depth popup stays inside a 390 px screen (${JSON.stringify(phoneDepthPopup)})`);
  await page.locator(".leaflet-popup-close-button").click();
  const phoneSources = page.getByTestId("sources-panel");
  await phoneSources.locator("summary").click();
  await expect(phoneSources.getByTestId("reported-depth-counts").locator("tr[data-status='not_comparable'] td")).toHaveText(["5", "4", "9"]);
  const phoneDepthFit = await phoneSources.getByTestId("reported-depths-sources").evaluate((box) => ({ need: box.scrollWidth, room: box.clientWidth }));
  assert(phoneDepthFit.need <= phoneDepthFit.room + 1, `The reported depths fit the Sources panel at 390 px (${JSON.stringify(phoneDepthFit)})`);
  const phoneTable = await expectDepthTableFits("390 px, English");
  const phoneDepthScroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(phoneDepthScroll <= 1, `No horizontal scroll at 390 px with the reported depths (${phoneDepthScroll}px)`);
  await page.setViewportSize({ width: 360, height: 780 });
  const narrowTable = await expectDepthTableFits("360 px, English");
  await page.setViewportSize({ width: 390, height: 844 });
  checks.push(`reported depths at 390 px: a real click at each marker's centre opens its own records (${phoneOpened.length} markers), a popup inside the map and the screen (${phoneDepthPopup.left}–${phoneDepthPopup.right} px) clear of the zoom buttons and the attribution; the counts table needs no sideways scroll at 390 and 360 px (${phoneTable.need} of ${phoneTable.room} px, ${narrowTable.need} of ${narrowTable.room} px; narrowest header ${Math.min(phoneTable.narrowest, narrowTable.narrowest)} px), no horizontal scroll`);
  await page.goto(`${baseUrl}${caseRoute}?t=84`, { waitUntil: "networkidle" });
  await page.screenshot({ path: resolve(artifacts, "case-replay-mobile.png"), fullPage: true });
  // The tile route stays: this page keeps its map until the next navigation.
  await page.setViewportSize({ width: 1440, height: 1000 });
  checks.push("case replay fits 360 and 390 px without overflow or truncated phase labels, with finger-sized day chips");
  checks.push(`season envelope on phones: toggle on by link, chip in the bottom stack of the map (visible with the legend open and during the imagery swipe, one note and three, English and Thai), credit in the attribution and caption under the map, hatched (${envelopePhones.join("; ")}), nothing overlapping and no horizontal scroll`);
  checks.push("phones (360 and 390 px): Play to Pause and every replay hour move the map by 0 px; nothing overlaps among zoom buttons, notes, legend, basemap note, clear-route, attribution and popups, all inside the map, nor among the swipe's side labels, its handle, the notes, the legend and the zoom buttons (English and Thai, one note and three); no horizontal scroll; Tab reaches the drawer and Escape closes it from Play and the slider; tooltips stay in the viewport and close on Escape; hatch pixels in the first-flooded PNG; the availability pill returns when the page goes offline");
  // A touch phone in Thai: no keyboard hint, Buddhist-era years with the CE year, and no letter-spacing on Thai eyebrows.
  const touch = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, serviceWorkers: "block" });
  await touch.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.origin === new URL(baseUrl).origin) return route.continue();
    if (url.hostname === "tile.openstreetmap.org") return route.fulfill({ status: 200, contentType: "image/png", body: blankTile });
    return route.abort();
  });
  const touchPage = await touch.newPage();
  touchPage.on("pageerror", (error) => pageErrors.push(error.message));
  await touchPage.goto(`${baseUrl}${caseRoute}?t=84&lang=th`, { waitUntil: "networkidle" });
  await expect(touchPage.getByTestId("replay-readout")).toContainText("พฤ. 12 ก.ย. 2567 (2024) · 12:00 น.");
  await expect(touchPage.getByTestId("keyboard-hint")).toBeHidden();
  const thaiEyebrow = await touchPage.evaluate(() => getComputedStyle(document.querySelector("section[aria-labelledby='mae-sai-replay-title'] p[class*='eyebrow']")).letterSpacing);
  assert(thaiEyebrow === "normal" || thaiEyebrow === "0px", `Thai eyebrows are not letter-spaced (${thaiEyebrow})`);
  const touchChips = await touchPage.getByRole("group", { name: "ไปยังวัน (เที่ยงวันเวลาท้องถิ่น)" }).getByRole("button")
    .evaluateAll((buttons) => buttons.map((button) => Math.round(button.getBoundingClientRect().height)));
  assert(touchChips.length === 11 && touchChips.every((height) => height >= 40), `Day chips are finger-sized on touch: ${touchChips}`);
  // The shelter-set comparison in Thai: same figures, the hours label, and no letter-spacing on Thai text.
  const thaiComparison = touchPage.getByTestId("access-card").getByTestId("set-comparison");
  await expect(thaiComparison.getByTestId("set-comparison-label")).toContainText("ไม่มีตัวเลขใดตัวเลขเดียวที่ใช้จัดอันดับชุดที่พักพิง");
  await expect(thaiComparison.getByTestId("set-comparison-label")).toContainText("ชั่วโมงมาจากจุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่ค่าที่สังเกตได้");
  await expect(thaiComparison.getByTestId("compare-reported-all-lost")).toHaveText("7,086 จาก 34,525 (21%)");
  await expect(thaiComparison.getByTestId("compare-plan-flooded-cutoff")).toHaveText("10 ก.ย. 23:00 น.");
  // The equity block in Thai, default view: no ratio, the plain reason, the rule and both counts per group.
  const thaiEquity = touchPage.getByTestId("access-card").getByTestId("equity-gap");
  await expect(thaiEquity).toHaveAttribute("data-reason", "insufficient_group_denominator");
  await expect(thaiEquity).toContainText("ช่องว่างความเท่าเทียมในการอพยพ: ไม่แสดงอัตราส่วน");
  await expect(thaiEquity).toContainText("ไม่มีผู้อยู่อาศัยกลุ่มเปราะบางตามตัวแทนที่นับในที่นี้มีที่พักพิงในระยะเดินตั้งแต่ก่อนน้ำท่วม จึงไม่มีผู้ใดในกลุ่มนี้สูญเสียการเข้าถึงได้");
  await expect(thaiEquity.getByTestId("equity-rule")).toHaveText("สิ่งที่นำมาเปรียบเทียบ: ในบรรดาผู้อยู่อาศัยของแต่ละกลุ่มที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม สัดส่วนของผู้ที่สูญเสียการเข้าถึง");
  await expect(thaiEquity.getByTestId("equity-counts")).toContainText("กลุ่มเปราะบางตามตัวแทน: สูญเสีย 0 จาก 0 คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด 103 คน)");
  await expect(thaiEquity.getByTestId("equity-label")).toContainText("กลุ่มเปราะบาง = ตัวแทนจากภูมิประเทศและความห่างไกล");
  // All residents, ranked plan of 8: the ratio and its plain comparison in Thai.
  await touchPage.getByTestId("access-card").getByRole("radio", { name: /^ผู้อยู่อาศัยทั้งหมดที่จุดถนน/ }).check();
  await touchPage.getByTestId("access-card").getByRole("radio", { name: "แผนจัดอันดับ" }).check();
  await expect(thaiEquity).toContainText("ช่องว่างความเท่าเทียมในการอพยพ: 1.61 · ในกลุ่มผู้อยู่อาศัยที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม กลุ่มเปราะบางตามตัวแทนมีโอกาสสูญเสียการเข้าถึงมากกว่ากลุ่มอื่นประมาณ 1.6 เท่า (85.77% เทียบกับ 53.42%)");
  await expect(thaiEquity.getByTestId("equity-counts")).toContainText("กลุ่มเปราะบางตามตัวแทน: สูญเสีย 320 จาก 373 คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด 7,152 คน)");
  await expect(thaiEquity.getByTestId("equity-why")).toContainText("ค่าที่สูงจึงบอกตำแหน่งของบ้านเหล่านั้น");
  const thaiEquityFit = await thaiEquity.evaluate((box) => ({ need: box.scrollWidth, room: box.clientWidth }));
  assert(thaiEquityFit.need <= thaiEquityFit.room, `The Thai equity block fits the access card at 390 px (${JSON.stringify(thaiEquityFit)})`);
  await touchPage.getByTestId("access-card").getByRole("radio", { name: "มีรายงานว่าใช้", exact: false }).check();
  await touchPage.getByTestId("access-card").getByRole("radio", { name: /^ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด/ }).check();
  await expect(thaiEquity).toHaveAttribute("data-reason", "insufficient_group_denominator");
  // The season envelope on the touch phone in Thai: Thai chip and caption, hatched, credited, clear of the other boxes.
  await touchPage.goto(`${baseUrl}${caseRoute}?t=84&lang=th&layers=trsce`, { waitUntil: "networkidle" });
  await touchPage.waitForFunction(() => !document.body.innerText.includes("กำลังเตรียมแบบจำลองน้ำ"), undefined, { timeout: 30_000 });
  const envelopeThai = await expectEnvelopeShown("touch phone in Thai", touchPage, "th");
  await expectClearMap(["zoom", "notes", "legend", "envelope chip", "attribution"], "touch phone in Thai with the season envelope", touchPage);
  assert.deepEqual(await spacedThai(touchPage), [], "Touch phone: no Thai text is letter-spaced with the season envelope on");
  const envelopeThaiScroll = await touchPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(envelopeThaiScroll <= 1, `Touch phone in Thai: no horizontal scroll with the season envelope (${envelopeThaiScroll}px)`);
  const thaiComparisonGroup = touchPage.getByTestId("envelope-comparison");
  await expect(thaiComparisonGroup).toContainText("การเทียบกับขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง; ดูความสมเหตุสมผล ไม่ใช่การยืนยันความถูกต้อง)");
  await expect(thaiComparisonGroup).toContainText("ความสอดคล้อง (IoU) 0.48");
  const thaiComparisonFit = await thaiComparisonGroup.evaluate((box) => ({ need: box.scrollWidth, room: box.clientWidth }));
  assert(thaiComparisonFit.need <= thaiComparisonFit.room, `The Thai envelope comparison fits its card at 390 px (${JSON.stringify(thaiComparisonFit)})`);
  checks.push(`touch phone in Thai: the season envelope's chip and caption in Thai with the CE year, hatched (period ${envelopeThai.hatch.periodPx} px), credited, without overlap, overflow or letter-spacing; the comparison group in Thai`);
  // Reported depths on the touch phone in Thai: the Thai toggle, a Thai popup clear of the other boxes, the Thai counts
  // table, no letter-spacing on Thai text and no horizontal scroll.
  const thaiOpened = await expectDepthMarkersOpenTheirOwn("touch phone in Thai", touchPage, `${baseUrl}${caseRoute}?t=84&lang=th&layers=trscd`, { tap: true });
  const thaiOpenedZoomed = await expectDepthMarkersOpenTheirOwn("touch phone in Thai, zoomed in around the town", touchPage, `${baseUrl}${caseRoute}?t=84&lang=th&layers=trscd`, { tap: true, wheel: -300 });
  const thaiDepthPopup = touchPage.locator(".leaflet-popup-content [data-testid='reported-depth-popup']");
  await expect(thaiDepthPopup).toBeVisible();
  await expect(thaiDepthPopup).toContainText("ตามรายงานข่าว (ไม่ได้สำรวจ)");
  await expect(thaiDepthPopup).toContainText("ความเชื่อมั่น");
  await expect(thaiDepthPopup).toContainText("ผลการเทียบ");
  await expectClearMap(["zoom", "attribution", "popup"], "touch phone in Thai, reported-depth popup", touchPage);
  assert.deepEqual(await spacedThai(touchPage), [], "No Thai text is letter-spaced with a reported-depth popup open at 390 px");
  await touchPage.locator(".leaflet-popup-close-button").click();
  await touchPage.getByRole("button", { name: "ชั้นแผนที่", exact: true }).click();
  await expect(depthToggle(touchPage, "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)")).toBeChecked();
  await touchPage.getByRole("button", { name: "ปิด", exact: true }).click();
  const thaiDepthSources = touchPage.getByTestId("sources-panel");
  await thaiDepthSources.locator("summary").click();
  const thaiDepthTable = thaiDepthSources.getByTestId("reported-depth-counts");
  await expect(thaiDepthTable).toContainText("แบบจำลองตื้นกว่า");
  await expect(thaiDepthTable.locator("tr[data-status='model_dry'] td")).toHaveText(["6", "3", "9"]);
  await expect(thaiDepthSources.getByTestId("reported-depths-counted")).toContainText("21 รายการตามสถานที่ จาก 17 ข้อความใน 14 ข่าว");
  const thaiTable = await expectDepthTableFits("touch phone in Thai, 390 px", touchPage);
  await touchPage.setViewportSize({ width: 360, height: 780 });
  const thaiNarrowTable = await expectDepthTableFits("touch phone in Thai, 360 px", touchPage);
  await touchPage.setViewportSize({ width: 390, height: 844 });
  await expect(thaiDepthSources.getByTestId("reported-depths-sources")).toContainText("สถานะ: ตามรายงาน (คำบอกเล่า ไม่ได้สำรวจ)");
  const thaiDepthFit = await thaiDepthSources.getByTestId("reported-depths-sources").evaluate((box) => ({ need: box.scrollWidth, room: box.clientWidth }));
  assert(thaiDepthFit.need <= thaiDepthFit.room + 1, `The Thai reported depths fit the Sources panel at 390 px (${JSON.stringify(thaiDepthFit)})`);
  assert.deepEqual(await spacedThai(touchPage), [], "No Thai text is letter-spaced with the reported depths in the Sources panel at 390 px");
  const thaiDepthScroll = await touchPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(thaiDepthScroll <= 1, `No horizontal scroll in Thai at 390 px with the reported depths (${thaiDepthScroll}px)`);
  checks.push(`touch phone in Thai: reported depths by link, a tap at each marker's centre opens its own records (${thaiOpened.length} markers, then ${thaiOpenedZoomed.length} zoomed in around the town), a Thai popup clear of the zoom buttons and the attribution, the Thai toggle on, the Thai counts table needs no sideways scroll at 390 and 360 px (${thaiTable.need} of ${thaiTable.room} px, ${thaiNarrowTable.need} of ${thaiNarrowTable.room} px), no letter-spacing on Thai text and no horizontal scroll`);
  await touchPage.goto(`${baseUrl}${caseRoute}?t=84&lang=th`, { waitUntil: "networkidle" });
  await touchPage.getByTestId("access-card").getByTestId("equity-gap").waitFor({ state: "visible" });
  const thaiSpacing = await touchPage.getByTestId("access-card").evaluate((card) => [...card.querySelectorAll("p, th, td, caption, legend, h2, h3, small, strong, span")]
    .filter((element) => /[\u0E00-\u0E7F]/.test(element.textContent ?? "") && !["normal", "0px"].includes(getComputedStyle(element).letterSpacing))
    .map((element) => `${element.tagName}: ${getComputedStyle(element).letterSpacing}`));
  assert.deepEqual(thaiSpacing, [], "Thai text on the access card is not letter-spaced");
  // The capacity-aware view and the what-if levels in Thai (default plan size): same figures, the caveats, no letter-spacing, tables fit.
  const thaiPlan = touchPage.getByTestId("shelter-plan-card");
  await expect(thaiPlan.getByTestId("capacity-coverage-lower")).toHaveText("495 ไม่มีที่รองรับ 13,674");
  await expect(thaiPlan.getByTestId("capacity-coverage-upper")).toHaveText("1,057 ไม่มีที่รองรับ 13,112");
  await expect(thaiPlan.getByTestId("capacity-aware-sentence")).toContainText("ค่าประมาณความจุรองรับได้ 495 ถึง 1,057 คน จึงเหลือ 13,112 ถึง 13,674 คนจาก 14,169 คนที่ไม่มีที่รองรับ");
  await expect(thaiPlan.getByTestId("capacity-caveats")).toContainText("เป็นค่าขอบเขตบน เพราะหลายคนไปพักกับญาติ");
  await expect(thaiPlan.getByTestId("capacity-caveats")).toContainText("สถานที่ที่ควรตรวจสอบในพื้นที่ ไม่ใช่รายชื่อสถานที่ที่ต้องเปิด");
  await expect(thaiPlan.getByTestId("capacity-caveats")).toContainText("มาจากแหล่งข้อมูลอื่น");
  await expect(thaiPlan.getByTestId("over-capacity-note")).toContainText("รองรับได้ ≈ 79 คน แต่ได้รับผู้อพยพ ≈ 2,430 คน");
  await expect(thaiPlan.getByTestId("what-if-label")).toContainText("ระดับน้ำสมมุติรอบ ๆ ระดับสูงสุดที่ใช้เพื่อการอธิบาย ไม่ใช่คาบการเกิดซ้ำ");
  await expect(thaiPlan.getByTestId("robust-core")).toHaveCount(5);
  await expect(thaiPlan.getByTestId("robust-core").first()).toHaveText("แกนที่คงทน: อยู่ใน 8 แห่งแรกที่ระดับ 2.5 ม. และ 4.0 ม. ด้วย");
  await expect(thaiPlan).not.toContainText(/Lower bound|Upper bound|overflow|What-if|Robust core|เปิดที่พักพิงเหล่านี้/);
  await expect(thaiPlan.getByTestId("verification-status")).toContainText("ยังไม่ได้ดำเนินการ ยังไม่มีแบบตรวจสอบส่งกลับมา");
  await expect(thaiPlan.getByTestId("verification-sheet")).toContainText("“ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ”");
  await expect(thaiPlan.getByTestId("shelter-verification")).not.toContainText(/Not conducted|Download the blank sheet/);
  await expect(thaiPlan.getByTestId("capacity-caveats")).toContainText("ทั้งสองขอบเขตไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้");
  // No text on the plan card is smaller than 10.5 px: a note under a column heading keeps the heading's size (a bare
  // <small> under a .7rem heading renders at 9.3 px, too small for Thai with stacked marks on a phone).
  const tinyPlanText = await thaiPlan.evaluate((card) => [...card.querySelectorAll("*")]
    .filter((element) => !(element instanceof SVGElement) && element.getClientRects().length > 0
      && [...element.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim())
      && Number.parseFloat(getComputedStyle(element).fontSize) < 10.5)
    .map((element) => `${element.tagName} ${getComputedStyle(element).fontSize}: ${element.textContent.trim().slice(0, 40)}`));
  assert.deepEqual(tinyPlanText, [], "No text on the Thai plan card is smaller than 10.5 px at 390 px");
  const peakNote = Number.parseFloat(await thaiPlan.locator("[data-testid='what-if-table'] thead th small").first().evaluate((element) => getComputedStyle(element).fontSize));
  assert(peakNote >= 10.5, `The label of the replay's own what-if column is readable (${peakNote}px)`);
  // The download list in Thai: Thai titles for every file, the standing sentence, and no overflow at 390 px.
  await touchPage.getByTestId("sources-panel").locator("summary").click();
  const thaiDownloads = touchPage.getByTestId("sources-panel").getByTestId("export-files");
  await expect(thaiDownloads.locator("a[download]")).toHaveCount(9);
  assert((await thaiDownloads.locator("a[download]").allInnerTexts()).every((label) => /[฀-๿]/.test(label)), "Every download link has a Thai title");
  await expect(touchPage.getByTestId("sources-panel").getByTestId("export-tier")).toContainText("ค่าจากแบบจำลอง ไม่ใช่ค่าที่สังเกตได้");
  await expect(touchPage.getByTestId("sources-panel").getByTestId("export-tier")).toContainText("ไม่ใช่การพยากรณ์ ไม่ใช่บันทึกการปิดถนนที่สังเกตได้จริง และไม่ใช่การเตือนภัยอย่างเป็นทางการ");
  // The footer of the download list is Thai throughout, the pack's source timestamp included.
  const thaiFooter = touchPage.getByTestId("sources-panel").getByTestId("export-footer");
  await expect(thaiFooter).toContainText("เวลาของข้อมูลต้นทาง: ข้อมูล OSM");
  await expect(thaiFooter).not.toContainText(/OSM extract|reported shelters compiled|illustrative stage keyframes/);
  assert.equal(await thaiFooter.locator("[lang='en']").count(), 0, "The Thai download footer carries no English sentence");
  const thaiDownloadOverflow = await touchPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(thaiDownloadOverflow <= 1, `The Thai download list does not overflow at 390 px (${thaiDownloadOverflow}px)`);
  const thaiO2 = touchPage.getByTestId("sources-panel").getByTestId("separate-case-o2");
  await expect(thaiO2).toContainText("22 ต.ค. 2567 (2024) · ชั้นข้อมูลน้ำของ UNOSAT และ GISTDA");
  await expect(thaiO2).toContainText("ไม่แสดงบนแผนที่นี้และไม่มีตำแหน่งบนแถบเลื่อนเวลา");
  assert.equal(await thaiO2.locator("[lang='en']").count(), 0, "The Thai line for the 22 Oct layer carries no English sentence");
  assert.deepEqual(await spacedThai(touchPage), [], "No Thai text node is letter-spaced with the sources panel open at 390 px");
  await touchPage.getByTestId("sources-panel").locator("summary").click();
  const thaiPlanSpacing = await thaiPlan.evaluate((card) => [...card.querySelectorAll("p, th, td, caption, h2, h3, li, small, strong, span, summary")]
    .filter((element) => /[\u0E00-\u0E7F]/.test(element.textContent ?? "") && !["normal", "0px"].includes(getComputedStyle(element).letterSpacing))
    .map((element) => `${element.tagName}: ${getComputedStyle(element).letterSpacing}`));
  assert.deepEqual(thaiPlanSpacing, [], "Thai text on the plan card is not letter-spaced");
  const thaiPlanTables = await thaiPlan.locator("[data-testid='capacity-aware-table'], [data-testid='what-if-table']")
    .evaluateAll((boxes) => boxes.map((box) => ({ need: box.querySelector("table").scrollWidth, room: box.clientWidth })));
  assert(thaiPlanTables.length === 2 && thaiPlanTables.every((box) => box.need <= box.room), `The capacity and what-if tables fit the plan card at 390 px in Thai (${JSON.stringify(thaiPlanTables)})`);
  assert.deepEqual(await spacedThai(touchPage), [], "No Thai text node on the page is letter-spaced at 390 px (title, readout and header sub-label included)");
  const thaiOverflow = await touchPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(thaiOverflow <= 1, `The Thai case replay does not overflow at 390 px (${thaiOverflow}px)`);
  await touchPage.getByTestId("how-to-read").locator("summary").click();
  await expect(touchPage.getByTestId("how-to-status")).toContainText("สถานะ: ไม่ใช้ในการปฏิบัติการ");
  await expect(touchPage.getByTestId("how-to-status").getByTestId("generated-at")).toHaveText(/สร้างไฟล์ข้อมูลเมื่อ \d{1,2} \S+ 25\d{2} \(20\d{2}\) \d{2}:\d{2} น\./);
  // 15 Sep in Thai: both observations, the consistent-with reading and the caveat, with no English sentence left,
  // no letter-spacing and no overflow at 390 px.
  await touchPage.goto(`${baseUrl}${caseRoute}?t=158&lang=th`, { waitUntil: "networkidle" });
  await expect(touchPage.getByTestId("replay-readout")).toContainText("15 ก.ย. 2567 (2024) · 14:00 น.");
  const thaiS2 = touchPage.getByTestId("s2-evidence");
  await expect(thaiS2).toContainText("สังเกตการณ์ (Sentinel-2 L2A 15 ก.ย. 10:58 น. มองเห็นพื้นที่อำเภอ");
  await expect(thaiS2).toContainText("น้ำหรือโคลนอิ่มน้ำ");
  await expect(thaiS2).toContainText("การเปรียบเทียบนี้เป็นเพียงข้อบ่งชี้");
  const thaiReading = touchPage.getByTestId("observed-reading");
  await expect(thaiReading).toContainText("วันนี้มีการสังเกตการณ์สองแหล่ง: VIIRS (15 ก.ย. 13:30 น. โดยประมาณ)");
  await expect(thaiReading.getByTestId("s2-reading")).toContainText("พื้นที่ที่สังเกตได้ซึ่งกว้างกว่าสอดคล้องกับน้ำหรือโคลนอิ่มน้ำที่ยังค้างอยู่หลังระดับแม่น้ำลดลง");
  await expect(thaiReading.getByTestId("s2-following-day")).toContainText("แผนที่ VIIRS ที่ท้องฟ้าโปร่งถัดมา (16 ก.ย. 13:30 น. โดยประมาณ)");
  await expect(thaiReading.getByTestId("s2-following-day")).toContainText("มากกว่าน้ำขังที่คงอยู่นาน");
  await expect(thaiReading).not.toContainText("ไร่นา");
  await expect(thaiReading).toContainText("ไม่ใช่ขอบเขตน้ำท่วม");
  await expect(thaiReading).not.toContainText(/Water or saturated mud|indicative|consistent with/);
  await expect(touchPage.getByTestId("viirs-card").getByTestId("viirs-s2-note")).toContainText("การสังเกตการณ์แหล่งที่สองของวันที่ 15 ก.ย.");
  assert.deepEqual(await spacedThai(touchPage), [], "No Thai text node is letter-spaced on 15 Sep at 390 px");
  const thaiS2Overflow = await touchPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(thaiS2Overflow <= 1, `The Thai 15 Sep evidence does not overflow at 390 px (${thaiS2Overflow}px)`);
  await touch.close();
  checks.push("touch phone in Thai: keyboard hint hidden, พ.ศ. dates with the CE year, Thai eyebrows not letter-spaced, finger-sized day chips, non-operational status and generation time in Thai, shelter-set comparison in Thai without letter-spacing or overflow");
  checks.push("touch phone in Thai: capacity-aware bounds, caveats and what-if label in Thai, robust core marked, no letter-spacing, no text under 10.5 px, tables fit at 390 px");
  checks.push("touch phone in Thai: the candidate check says not conducted, and the eight download links have Thai titles under the standing sentence, with a Thai source timestamp, without overflow or letter-spacing");
  checks.push("touch phone in Thai on 15 Sep: both observations, the consistent-with reading, the next clear VIIRS day and the caveat in Thai, without letter-spacing or overflow");
  for (const path of [study, `${study}data/`, `${study}results/`, `${study}explorer/?chip=${encodeURIComponent(initialChip)}`, `${study}mae-sai/`]) {
    await page.setViewportSize({width:390,height:844});
    await page.goto(`${baseUrl}${path}`,{waitUntil:"networkidle"});
    const overflow = await page.evaluate(()=>[...document.querySelectorAll("main *")].filter((element)=>element.getBoundingClientRect().right>window.innerWidth+1).slice(0,12).map(element=>({tag:element.tagName,class:element.className,text:element.textContent?.slice(0,80),right:element.getBoundingClientRect().right,width:element.getBoundingClientRect().width})));
    if (!(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1))) {
      await page.screenshot({path:resolve(artifacts,"overflow-failure.png"),fullPage:true});
      assert.fail(`Page overflow at ${path}: ${JSON.stringify(overflow)}`);
    }
    await expect(page.getByLabel(/^Study section/)).toBeVisible();
  }
  await page.screenshot({path:resolve(artifacts,"mae-sai-mobile.png"),fullPage:true});
  checks.push("mobile layout and compact section navigation");
  assert.deepEqual(failedResponses, [], "Study navigation must not request missing assets or Next prefetch documents.");
  assert.deepEqual(consoleErrors, [], "No console errors before the deliberate missing-file tests.");
  const broken = await context.newPage();
  await broken.route("**/studies/c2s-ms-20260915/r1/summary.json",route=>route.fulfill({status:404,body:"missing"}));
  await broken.goto(`${baseUrl}${study}results/`,{waitUntil:"networkidle"});
  await expect(broken.locator("main").getByRole("alert")).toContainText("Study asset unavailable");
  assert(!(await broken.locator("main").innerText()).includes("0.8661"));
  checks.push("missing report fails closed without historical or planning fallback");
  await broken.unrouteAll();
  await broken.route("**/visuals/mae-sai/context/xgboost/abstention.png*",route=>route.fulfill({status:404,body:"missing"}));
  await broken.goto(`${baseUrl}${study}mae-sai/?arm=context&model=xgboost&layer=probability&overlay=on`,{waitUntil:"networkidle"});
  await expect(broken.locator("main").getByRole("alert")).toContainText("Abstention overlay unavailable");
  assert.equal(await broken.getByText("Abstention overlay applied",{exact:false}).count(),0);
  checks.push("a missing mask cannot be labelled as an applied overlay");
  await broken.unrouteAll();
  await broken.goto(`${baseUrl}${study}results/?revision=r99`,{waitUntil:"networkidle"});
  await expect(broken.locator("main").getByRole("alert")).toContainText("Study revision unavailable");
  checks.push("unknown revision cannot silently reuse r1");
  assert.deepEqual(pageErrors, [], "No client exceptions during study navigation.");
  writeFileSync(resolve(artifacts,"verification.json"),JSON.stringify({checked_at:new Date().toISOString(),base_url:baseUrl,status:"passed",checks},null,2));
  console.log(JSON.stringify({status:"passed",checks:checks.length,artifacts},null,2));
} finally {
  await browser.close();
  if(server) await new Promise((done)=>server.close(done));
}
