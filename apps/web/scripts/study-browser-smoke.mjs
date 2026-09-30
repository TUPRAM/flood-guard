import assert from "node:assert/strict";
import { createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { expect } from "@playwright/test";
import { launchFloodGuardBrowser } from "./browser-launch.mjs";

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
  await page.getByRole("radio", { name: "Hours under water" }).check();
  await expect(page.getByText("Hours under water, 9–19 Sep (model)", { exact: true })).toBeVisible();
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
  checks.push("water modes (depth, first flooded, hours under water) and modelled road-cut hours with the Keep Routes Open list");
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
  await slider.fill("40");
  await expect(viirsImage).toHaveAttribute("src", /viirs-20240910\.png$/);
  await slider.fill("12");
  await expect(viirsImage).toHaveCount(0);
  await expect(page.getByTestId("viirs-note")).toContainText("no daily map");
  await expect(page.getByTestId("rain-chart")).toBeVisible();
  await expect(page.getByTestId("rain-now")).toContainText("MOU189");
  checks.push("observed VIIRS daily map (day at or before the playhead, pixelated, deep-linked) with its clear-sky comparison card, and the hourly rain chart");
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
  // Like with like: by default the card counts the residents whose homes flood at the peak, as the plan does.
  await expect(accessCard.getByRole("radio", { name: /^Residents whose homes flood at the peak/ })).toBeChecked();
  await expect(accessCard.getByTestId("plan-optimises")).toContainText("What the ranked plan optimises");
  await accessCard.getByRole("radio", { name: /^All residents at road nodes/ }).check();
  await expect(page).toHaveURL(/[?&]pop=all(&|$)/);
  await accessCard.getByRole("radio", { name: /^Residents whose homes flood at the peak/ }).check();
  await expect(page).toHaveURL(/[?&]pop=flooded(&|$)/);
  await expect(accessCard.getByTestId("equity-gap")).toContainText("Evacuation Equity Gap");
  await expect(accessCard.getByTestId("equity-gap")).toContainText("terrain/remoteness proxy");
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
  checks.push("people in flood water and all-residents views, access scenario with population scope, set and k (live coverage sentence), cut-off heat, sticky map beside the cards, plan badges and sourced shelter popups");
  await page.reload({ waitUntil: "networkidle" });
  await openLayers();
  await expect(page.getByRole("radio", { name: "People in flood water" })).toBeChecked();
  await expect(page.getByRole("radio", { name: "Ranked plan" })).toBeChecked();
  await expect(page.getByTestId("access-card").getByRole("slider", { name: /^Plan size k/ })).toHaveValue("3");
  await expect(page.getByRole("checkbox", { name: "People cut off (scenario)" })).toBeChecked();
  checks.push("deep link restores the residents view, shelter set, plan size and cut-off layer");
  await page.screenshot({ path: resolve(artifacts, "case-replay-desktop.png"), fullPage: true });
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
    if (width === 360) {
      // Offline, the basemap note must sit above Leaflet's attribution (two lines at this width), not under it.
      await context.setOffline(true);
      await page.getByTestId("basemap-note").waitFor({ state: "visible" });
      const overlap = await page.evaluate(() => {
        const note = document.querySelector("[data-testid='basemap-note']").getBoundingClientRect();
        const credit = document.querySelector(".leaflet-control-attribution").getBoundingClientRect();
        const across = Math.min(note.right, credit.right) - Math.max(note.left, credit.left);
        const down = Math.min(note.bottom, credit.bottom) - Math.max(note.top, credit.top);
        return across > 0 && down > 0 ? Math.round(down * 10) / 10 : 0;
      });
      await context.setOffline(false);
      assert.equal(overlap, 0, `The basemap note overlaps the map attribution by ${overlap}px at ${width}px`);
    }
  }
  await page.screenshot({ path: resolve(artifacts, "case-replay-mobile.png"), fullPage: true });
  // The tile route stays: this page keeps its map until the next navigation.
  await page.setViewportSize({ width: 1440, height: 1000 });
  checks.push("case replay fits 360 and 390 px without overflow or truncated phase labels, with finger-sized day chips; the offline basemap note clears the attribution");
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
  await touch.close();
  checks.push("touch phone in Thai: keyboard hint hidden, พ.ศ. dates with the CE year, Thai eyebrows not letter-spaced, finger-sized day chips");
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
