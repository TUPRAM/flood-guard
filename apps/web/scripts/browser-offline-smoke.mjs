import { createHash } from "node:crypto";
import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";
import { readCaseReplay } from "./case-replay-inventory.mjs";
import { EVIDENCE_AREA_CACHE, EVIDENCE_CATALOG_ASSET, readWorkerEvidenceAreas } from "./evidence-library-assets.mjs";
import { readLandingArtwork } from "./landing-artwork-inventory.mjs";
import { megabytes, verifyOfflineInstall } from "./offline-install-budget.mjs";

const out = resolve(process.cwd(), "out");
if (!existsSync(resolve(out, "public", "index.html"))) {
  throw new Error("Build output is missing; run the production build first.");
}
// The evidence library's study areas, as the built worker lists them: each is saved only when the reader asks.
const evidenceAreas = readWorkerEvidenceAreas(readFileSync(resolve(out, "sw.js"), "utf8"));
const evidenceCatalog = JSON.parse(readFileSync(resolve(out, EVIDENCE_CATALOG_ASSET.slice(1)), "utf8"));
// The offline pages below open the default case, so its study area is saved first. Another area is left unsaved.
const savedCase = evidenceCatalog.packages[0];
const unsavedCase = evidenceCatalog.packages.find((item) => item.aoi_id !== savedCase.aoi_id && item.aoi_id.startsWith("aoi-03"));
const savedArea = evidenceAreas.find((area) => area.aoi_id === savedCase.aoi_id);
if (!savedArea || !unsavedCase || !evidenceAreas.some((area) => area.aoi_id === unsavedCase.aoi_id)) {
  throw new Error("The evidence library does not list the two study areas this check uses.");
}

const contentTypes = {
  ".bin": "application/octet-stream",
  ".css": "text/css; charset=utf-8",
  ".geojson": "application/geo+json",
  ".png": "image/png",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};

// A stand-in for the next deployment: once set, the worker script is served under this build id and with nothing
// else changed, so the browser installs a new worker whose study-area files are the same.
let redeployedBuild = null;

const server = createServer((request, response) => {
  const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
  const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  let filePath = resolve(out, relativePath || "index.html");
  if (redeployedBuild && relativePath === "sw.js") {
    response.writeHead(200, { "Cache-Control": "no-store", "Content-Type": contentTypes[".js"], "Service-Worker-Allowed": "/" });
    response.end(readFileSync(filePath, "utf8").replace(/floodguard-offline-[0-9a-f]{12}/, `floodguard-offline-${redeployedBuild}`));
    return;
  }
  if (!filePath.startsWith(`${out}${sep}`) && filePath !== out) {
    response.writeHead(403).end("Forbidden");
    return;
  }
  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = resolve(filePath, "index.html");
  }
  if (!existsSync(filePath) || !statSync(filePath).isFile()) {
    response.writeHead(404).end("Not found");
    return;
  }
  response.writeHead(200, {
    "Cache-Control": "no-store",
    "Content-Type": contentTypes[extname(filePath)] ?? "application/octet-stream",
    "Service-Worker-Allowed": "/",
  });
  createReadStream(filePath).pipe(response);
});

await new Promise((resolveListen, rejectListen) => {
  server.once("error", rejectListen);
  server.listen(0, "127.0.0.1", resolveListen);
});

const address = server.address();
if (!address || typeof address === "string") throw new Error("Static server did not bind.");
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await launchFloodGuardBrowser();

const routes = [
  { path: "/", selector: "main[data-fg-landing]" },
  { path: "/public/", selector: "main.public-page" },
  { path: "/public-cases/", selector: "main[data-evidence-library]" },
  { path: "/command/", selector: "main[data-planning-candidate]" },
  { path: "/command/cases/", selector: "main[data-evidence-library]" },
  { path: "/command/archive/", selector: "main.command-page" },
  { path: "/studio/", selector: "main.studio-page" },
  { path: "/studio/planning-evidence/", selector: "main.studio-page" },
  { path: "/studio/candidate-report/", selector: "main[data-evidence-case-id]" },
  { path: "/studio/library/", selector: "main[data-evidence-library]" },
  { path: "/studio/brief/", selector: "main[data-evidence-library]" },
  { path: "/studio/archive/", selector: "main.studio-page" },
];
const approvedBasemapOrigins = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const approvedBasemapOriginsSeen = new Set();
// External data services the app may call as online enhancements: address
// geocoding (Public search and Shelter destination) and walking-route
// directions (Shelter). Permitted but NOT required — both degrade gracefully
// offline, so unlike the basemap providers they need not be requested.
const approvedDataServiceOrigins = new Set([
  "https://geocode.arcgis.com",
  "https://routing.openstreetmap.de",
]);
const externalRequests = [];
const pageErrors = [];
const consoleErrors = [];
const unexpectedRequestFailures = [];
let offlineMode = false;

try {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== baseUrl) {
      if (approvedBasemapOrigins.has(url.origin)) {
        approvedBasemapOriginsSeen.add(url.origin);
        await route.abort("blockedbyclient");
        return;
      }
      if (approvedDataServiceOrigins.has(url.origin)) {
        // Permitted online enhancement; block it (offline test) without flagging.
        await route.abort("blockedbyclient");
        return;
      }
      externalRequests.push(url.href);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    const url = new URL(request.url());
    if (approvedBasemapOrigins.has(url.origin)) return;
    if (approvedDataServiceOrigins.has(url.origin)) return;
    const errorText = request.failure()?.errorText ?? "failed";
    // Next cancels speculative RSC/data requests during route changes. Once
    // offline, uncached speculative RSC requests may fail while the tested HTML
    // routes and core assets are served successfully by the service worker.
    if (errorText === "net::ERR_ABORTED" || (offlineMode && errorText === "net::ERR_FAILED")) return;
    unexpectedRequestFailures.push(
      `${request.method()} ${url.href}: ${errorText}`,
    );
  });
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    // Chromium can report an explicitly blocked image tile as ERR_FAILED even
    // when Playwright aborted it with `blockedbyclient`. URL-aware
    // `requestfailed` handling above still rejects every non-basemap failure.
    if (
      text.includes("net::ERR_BLOCKED_BY_CLIENT")
      || text === "Failed to load resource: net::ERR_FAILED"
    ) return;
    consoleErrors.push(text);
  });

  for (const route of routes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: "networkidle" });
    await page.locator(route.selector).waitFor({ state: "visible" });
  }

  // The illustrated landing retains all three workspaces and fits mobile.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  const rootBody = await page.locator("body").innerText();
  assertFinalVisibleCopy(rootBody, "/");
  const rootAudit = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    language: document.querySelector("main[data-fg-landing]")?.getAttribute("lang"),
    links: [...new Set([...document.querySelectorAll("[data-fg-landing] a")].map((link) => link.getAttribute("href")))],
  }));
  if (rootAudit.documentWidth > rootAudit.viewportWidth + 1) {
    throw new Error(`Landing has mobile overflow: ${rootAudit.documentWidth}px > ${rootAudit.viewportWidth}px.`);
  }
  if (!["/public/", "/command/", "/studio/"].every((route) => rootAudit.links.includes(route))) {
    throw new Error(`Landing workspaces are incomplete: ${JSON.stringify(rootAudit)}.`);
  }
  if (rootAudit.language !== "en") {
    throw new Error(`Landing does not declare its English content language: ${JSON.stringify(rootAudit)}.`);
  }

  // Public: the compact shell and all five pages must remain usable at the
  // primary mobile viewport. Home owns the full middle row; the other pages
  // retain device-local interactions and safety boundaries.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/public/`, { waitUntil: "networkidle" });
  await page.locator('.language-toggle button[lang="en"]').click();
  await waitForFinalVisibleCopy(page, "/public/");
  await assertCompactPublicShell(page);
  await assertPublicNavigation(page);
  await selectPublicPlanningArea(page, "TH570901", "Mae Sai");

  const publicMapScope = await firstVisibleSelector(page, [
    ".public-home-page",
    ".public-home-view",
    ".public-map-view",
  ]);
  await page.locator(`${publicMapScope} .leaflet-container`).waitFor({ state: "visible" });
  // The redesigned Public Home shades the role-approved preparedness areas
  // (public-areas.json, role_visibility ["public"], validated by
  // assertPublicProjection) with the selected area highlighted, so it now
  // renders a boundary overlay. The genuine public safety guards below — zero
  // facilities, no facility markers, no roads — are unchanged and still assert.
  await assertMaeSaiMap(page, publicMapScope, {
    expectRoads: false,
    expectTextAlternative: true,
    expectBoundary: true,
  });
  await exerciseBasemapSelector(page, publicMapScope, "unavailable");
  await assertPublicHomeLayout(page, publicMapScope);
  await selectPublicPlanningArea(page, "TH570906", "Wiang Phang Kham");
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const language of ["th", "en"]) {
      await page.locator(`.language-toggle button[lang="${language}"]`).click();
      await page.waitForFunction((lang) => document.documentElement.lang === lang, language);
      await assertPublicHomeLayout(page, publicMapScope);
      const list = page.locator(`${publicMapScope} .map-text-alternative`);
      await list.locator("summary").click();
      const listLayout = await list.evaluate((element) => ({
        open: element.open,
        width: element.getBoundingClientRect().width,
        viewport: window.innerWidth,
        contentWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
      }));
      if (!listLayout.open || listLayout.width < listLayout.viewport - 28 || listLayout.contentWidth > listLayout.clientWidth + 1) {
        throw new Error(`Public map list is cramped or overflows: ${JSON.stringify(listLayout)}.`);
      }
      await list.locator("summary").click();
    }
  }
  // The map background cannot load here (its tiles are blocked). On phones the notice is one line and one button,
  // clear of the list button and the map tools; the sentence and the actions open behind the button.
  const phoneNotice = [];
  // The layer menu was left open by the background check above; it is a list the reader opens over the map.
  const layerMenu = page.locator(`${publicMapScope} .map-basemap-menu`);
  if (await layerMenu.getAttribute("open") !== null) await layerMenu.locator("summary").click();
  for (const [width, height] of [[320, 844], [375, 812], [390, 844]]) {
    await page.setViewportSize({ width, height });
    for (const language of ["th", "en"]) {
      await page.locator(`.language-toggle button[lang="${language}"]`).click();
      await page.waitForFunction((lang) => document.documentElement.lang === lang, language);
      phoneNotice.push(await assertPhoneMapNotice(page, publicMapScope, language, `${width}x${height}`));
    }
  }
  await assertPhoneMapNoticeActions(page, publicMapScope);
  await page.setViewportSize({ width: 390, height: 844 });
  await assertPublicPlanningFallback(page, publicMapScope);
  await page.locator(".public-hazard-button").click();
  const hazardPanel = page.locator("#public-hazard-panel");
  await hazardPanel.waitFor({ state: "visible" });
  const hazardText = await hazardPanel.innerText();
  for (const required of ["Planning indicator", "Evidence sufficiency", "Source time", "candidate planning indicator", "separate from the selected study case", "non-operational", "DDPM"]) {
    if (!hazardText.includes(required)) {
      throw new Error(`Public Hazard Info is missing its evidence boundary: ${required}.`);
    }
  }
  await page.getByRole("button", { name: "Close hazard information" }).click();

  await activatePublicPage(page, "report", ".public-report-page");
  // Water depth is a continuous slider now; its band buttons set a
  // representative value. The separate report category was removed.
  await page.locator(".flood-height-steps button", { hasText: "Knee" }).click();
  await page.locator("#public-report-notes").fill("Blocked drain observed from a safe position.");
  await page.locator(".public-report-submit").click();
  if (!(await page.locator(".public-report-form-status").innerText()).includes("saved on this device")) {
    throw new Error("The Public report did not confirm its device-local save boundary.");
  }
  // The illustrative example feed reuses the feed-list class, so scope the count
  // to the real device feed (the ol that is a direct child of .public-report-feed).
  if (await page.locator(".public-report-feed > .public-report-feed-list > li").count() !== 1) {
    throw new Error("The Public report did not appear in the device-local area feed.");
  }

  await activatePublicPage(
    page,
    "shelter",
    ".public-shelter-page, .public-shelter-view",
  );
  const shelterText = await page.locator("#main-content").innerText();
  if (!/DDPM|1784|confirm/iu.test(shelterText)) {
    throw new Error("The Shelter page lost its official-confirmation boundary.");
  }

  await activatePublicPage(page, "prepare", "#household-plan-builder");
  await page.locator(".household-need-options button").first().click();
  await page.locator(".checklist-grid input").first().check();
  const storedPlan = await page.evaluate(() => localStorage.getItem("floodguard:household-plan:v2"));
  if (!storedPlan || !storedPlan.includes('"children":true') || !storedPlan.includes('"official_contacts":true')) {
    throw new Error("The device-local household plan did not persist selected needs and checklist state.");
  }

  await activatePublicPage(page, "sos", ".public-sos-page, .public-sos-view");
  const emergencyLinks = page.locator('#main-content a[href^="tel:"]');
  if (await emergencyLinks.count() < 3) {
    throw new Error("SOS does not expose the three official emergency phone actions.");
  }
  await emergencyLinks.first().focus();
  if (!await emergencyLinks.first().evaluate((link) => document.activeElement === link)) {
    throw new Error("SOS emergency contacts are not keyboard reachable.");
  }

  await page.reload({ waitUntil: "networkidle" });
  await activatePublicPage(page, "prepare", "#household-plan-builder");
  if (
    await page.locator(".household-need-options button").first().getAttribute("aria-pressed") !== "true"
    || !(await page.locator(".checklist-grid input").first().isChecked())
  ) {
    throw new Error("The household plan did not restore from device-local storage after reload.");
  }

  // Command: the real-coordinate Mae Sai planning bundle renders at tablet
  // size with its evidence drawer and verification boundary visible.
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/command/`, { waitUntil: "networkidle" });
  await page.locator('main[data-planning-candidate="aoi-01_mae_sai_core_mae_sai_2024"]').waitFor({ state: "visible" });
  if (!(await page.locator('main[data-planning-candidate]').innerText()).includes("Accepted FPPS and action class remain unavailable")) {
    throw new Error("Current Planning overview lost its candidate scoring boundary.");
  }
  await page.goto(`${baseUrl}/studio/candidate-report/`, { waitUntil: "networkidle" });
  await page.locator('main[data-evidence-case-id="aoi-01_mae_sai_core_mae_sai_2024"]').waitFor({ state: "visible" });
  if (!(await page.locator('main[data-evidence-case-id]').innerText()).includes("Accepted FPPS / action class")) {
    throw new Error("Current Studio report lost its downstream acceptance boundary.");
  }
  await page.goto(`${baseUrl}/command/archive/`, { waitUntil: "networkidle" });
  await page.locator(".map-workspace .leaflet-container").waitFor({ state: "visible" });
  await page.waitForFunction(() => (
    document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-road-feature-count") === "4458"
    && document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-facility-feature-count") === "42"
    && document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-facility-presentation") === "clusters"
    && document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-access-feature-count") === "8"
  ));
  await assertMaeSaiMap(page, ".map-workspace", { expectRoads: true });
  await page.locator(".ranked-areas button").filter({ hasText: "Mae Sai" }).first().click();
  await page.waitForFunction(() => document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-selected-area") === "TH570901");
  for (let index = 0; index < 6 && await page.locator(".map-workspace .geo-map-shell").getAttribute("data-facility-presentation") !== "features"; index += 1) {
    await page.locator(".map-workspace .leaflet-control-zoom-in").click();
  }
  await page.waitForFunction(() => document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-facility-presentation") === "features");
  if (await page.locator(".map-workspace .facility-type-marker").count() !== 42) {
    throw new Error("Command map did not expand facility clusters into individual staff markers at detail zoom.");
  }
  if (await page.locator(".map-workspace .facility-type-marker.facility-possible_shelter").count() === 0) {
    throw new Error("Command map is missing the neutral possible-shelter marker category.");
  }
  if (await page.locator(".map-workspace .facility-type-marker.facility-muted").count() === 0) {
    throw new Error("Command map did not mute facilities outside the selected area at detail zoom.");
  }
  await exerciseBasemapSelector(page, ".map-workspace", "unavailable");
  const offlineAttribution = page.getByLabel("Map data attribution");
  const offlineAttributionText = await offlineAttribution.innerText();
  for (const requiredAttribution of ["HDX Thailand COD-AB", "FloodGuard", "© OpenStreetMap contributors", "Geofabrik"]) {
    if (!offlineAttributionText.includes(requiredAttribution)) {
      throw new Error(`Offline Command map is missing attribution: ${requiredAttribution}.`);
    }
  }
  if (await offlineAttribution.locator('a[href="https://www.openstreetmap.org/copyright"]').count() !== 1) {
    throw new Error("Offline Command map does not link the canonical OpenStreetMap copyright notice.");
  }
  const evidenceDrawer = page.locator(".tablet-evidence-drawer");
  if (!(await evidenceDrawer.isVisible()) || await evidenceDrawer.locator(".tablet-evidence-body").isHidden()) {
    throw new Error("The 1024x768 command workspace does not keep its evidence drawer open.");
  }
  const drawerBox = await evidenceDrawer.boundingBox();
  if (!drawerBox || drawerBox.x < 0 || drawerBox.x + drawerBox.width > 1024) {
    throw new Error(`The tablet evidence drawer is clipped horizontally: ${JSON.stringify(drawerBox)}.`);
  }
  await evidenceDrawer.scrollIntoViewIfNeeded();
  const visibleDrawerBox = await evidenceDrawer.boundingBox();
  if (!visibleDrawerBox || visibleDrawerBox.y < -1 || visibleDrawerBox.y + visibleDrawerBox.height > 769) {
    throw new Error(`The tablet evidence drawer cannot be brought fully into view: ${JSON.stringify(visibleDrawerBox)}.`);
  }
  const scenarioSelect = page.locator('select[aria-label="Select scenario"]');
  if (!(await scenarioSelect.isDisabled())) {
    throw new Error("Planning scenarios were enabled without the validated analysis service.");
  }
  if (await page.getByRole("tab", { name: "Scenario" }).count() !== 0) {
    throw new Error("Command exposed the Scenario tab without a deliberate non-baseline scenario.");
  }
  if (await page.locator(".command-release-panel .scenario-evidence-comparison, .scenario-delta-strip").count() !== 0) {
    throw new Error("Command rendered a baseline comparison without a reviewed non-baseline scenario.");
  }
  await page.locator(".ranked-areas button").filter({ hasText: "TH570901" }).click();
  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570901"
    && document.querySelector(".tablet-evidence-drawer")?.textContent?.includes("TH570901")
  ));

  // Studio: assurance levels must remain visibly separate and selecting an
  // evaluation must update the model card rather than detached presentation copy.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${baseUrl}/studio/planning-evidence/`, { waitUntil: "networkidle" });
  await page.locator("#evidence-context-title").waitFor({ state: "visible" });
  try {
    await page.waitForFunction(() => {
      const body = document.body.innerText;
      const normalized = body.toLocaleLowerCase("en-US");
      return normalized.includes("technical verification")
        && normalized.includes("observed-data validation")
        && normalized.includes("operational authorization");
    }, undefined, { timeout: 5_000 });
  } catch (error) {
    throw new Error(`Studio evidence scopes did not render: ${(await page.locator("body").innerText()).slice(0, 1800)}`, {
      cause: error,
    });
  }
  const studioBody = await page.locator("body").innerText();
  const normalizedStudioBody = studioBody.toLocaleLowerCase("en-US");
  for (const english of ["Technical verification", "Observed-data validation", "Operational authorization"]) {
    if (!normalizedStudioBody.includes(english.toLocaleLowerCase("en-US"))) {
      throw new Error(`Studio is missing its ${english} evidence scope.`);
    }
  }
  assertFinalVisibleCopy(studioBody, "/studio/planning-evidence/");
  await page.getByRole("tab", { name: "Models & evaluation" }).click();
  await page.locator("#qualified-evidence-foundation-title").waitFor({ state: "visible" });
  await page.locator("#model-registry-title").waitFor({ state: "visible" });
  await page.waitForFunction(() => (
    document.querySelector("#studio-tab-panel")?.textContent?.includes(
      "Checksum matches the canonical status payload",
    )
  ));
  const registryBody = await page.locator("#studio-tab-panel").innerText();
  const normalizedRegistryBody = registryBody.toLocaleLowerCase("en-US");
  for (const required of [
    "Qualified Thai Reference & Frozen Label Release v1",
    "authoritative_receipt=false",
    "CANDIDATE EVIDENCE BINDING",
    "AIT-VAP001-TH",
    "Manifest checksum",
    "Source archive checksum",
    "Source processing",
    "processing_allowed=true",
    "Experiment processing",
    "processing_allowed=false",
    "Qualified Thai event reference",
    "Reviewer assignment and calibration",
    "Blind double review and adjudication",
    "Frozen label release",
    "Checksum matches the canonical status payload",
    "No model evaluation is bound to this evidence context",
    "External algorithmic baseline",
    "No real-event evaluation",
    "Report only",
    "not eligible for FPPS or the decision layer",
    "Remain unknown; never treated as dry",
    "Browser cryptographic status: not verified",
    "The API and repository are the authority for cryptographic verification.",
  ]) {
    if (!normalizedRegistryBody.includes(required.toLocaleLowerCase("en-US"))) {
      throw new Error(`Studio model registry is missing its fail-closed copy: ${required}.`);
    }
  }
  const foundationBody = await page
    .locator("#qualified-evidence-foundation-title")
    .locator("xpath=ancestor::section[1]")
    .innerText();
  if (
    /[A-Za-z]:[\\/]|\\\\|file:\/\/|\/(?:Users|home|root|tmp)\//i.test(foundationBody)
    || /\.(?:gpkg|tif|zip|json|csv)\b/i.test(foundationBody)
  ) {
    throw new Error("Studio P0 status exposes a private path or technical artifact name.");
  }
  const registryButtons = page.locator('#studio-tab-panel button[aria-pressed]');
  if (await registryButtons.count() !== 1 || await registryButtons.first().getAttribute("aria-pressed") !== "true") {
    throw new Error("Studio model registry selection is missing or not keyboard-state visible.");
  }
  if (!registryBody.includes("0%") || !registryBody.includes("100%")) {
    throw new Error("Studio does not show the all-unknown coverage and abstention state.");
  }
  if (registryBody.includes("Signature authority")) {
    throw new Error("Studio overstates the browser trust boundary as signature authority.");
  }
  const runButtons = page.locator('button[aria-pressed][class*="runButton"]');
  if (await runButtons.count() > 1) {
    await runButtons.nth(1).click();
    const selectedRunId = (await runButtons.nth(1).innerText()).split("\n")[1];
    if (selectedRunId && !(await page.locator("#model-card").innerText()).includes(selectedRunId)) {
      throw new Error("Studio run selection did not update the selected model card.");
    }
  }

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto(`${baseUrl}/public/`, { waitUntil: "networkidle" });
  await page.locator('.language-toggle button[lang="en"]').click();
  if (await page.locator("html").getAttribute("lang") !== "en") {
    throw new Error("Language switch did not update the document language.");
  }
  if (await page.locator('.language-toggle button[lang="en"]').getAttribute("aria-pressed") !== "true") {
    throw new Error("Language switch did not expose its selected state.");
  }
  await waitForFinalVisibleCopy(page, "/public/");
  await page.goto(`${baseUrl}/command/archive/`, { waitUntil: "networkidle" });
  if (await page.locator("html").getAttribute("lang") !== "en" || await page.locator('.language-toggle button[lang="en"]').getAttribute("aria-pressed") !== "true") {
    throw new Error("Language preference did not persist between product surfaces.");
  }
  if (await page.locator(".ranked-areas button").count() === 0) {
    throw new Error("Command route did not render its synchronized FPPS ranking.");
  }
  // Command does not show the GeoAI research report (owner decision of 4 Oct 2026, R17): on the archive, where the
  // panel was, and on the overview a short notice says that the earlier scores are not accepted event-response
  // priorities and where the report is kept. The table itself is in Studio's archive, labelled historical.
  for (const commandRoute of ["/command/archive/", "/command/"]) {
    if (commandRoute !== "/command/archive/") await page.goto(`${baseUrl}${commandRoute}`, { waitUntil: "networkidle" });
    const researchNotice = page.locator('[data-research-report-notice="true"]');
    await researchNotice.waitFor({ state: "visible" });
    const noticeCopy = await researchNotice.innerText();
    if (!noticeCopy.includes("Earlier research scores and classes are not accepted event-response priorities.")
      || !noticeCopy.includes("only in Studio's archive")
      || await researchNotice.locator('a[href="/studio/archive/mae-sai-geoai/"]').count() !== 1) {
      throw new Error(`${commandRoute} lacks the notice that replaces the research report, or its link to Studio's archive.`);
    }
    if (await page.locator('section[aria-labelledby="geoai-real-title"]').count() !== 0 || await researchNotice.locator("table").count() !== 0
      || /Research FPPS|Research class|GeoAI research report|GEOAI RESEARCH/.test(await page.locator("body").innerText())) {
      throw new Error(`${commandRoute} still shows the GeoAI research report or its score table.`);
    }
  }
  await page.locator('[data-research-report-notice="true"] a[href="/studio/archive/mae-sai-geoai/"]').click();
  await page.waitForURL(`${baseUrl}/studio/archive/mae-sai-geoai/`);
  const researchPanel = page.locator('section[aria-labelledby="geoai-real-title"]');
  await researchPanel.locator("table").waitFor({ state: "visible" });
  const researchCopy = await researchPanel.innerText();
  const historicalStudyCopy = await page.locator("main").innerText();
  // The column headings are shown in capitals by the stylesheet.
  if (!researchCopy.includes("Report only") || !/research fpps/i.test(researchCopy) || !/research class/i.test(researchCopy)
    || !researchCopy.includes("Research scores and classes; not action recommendations")
    || await researchPanel.locator("tbody tr").count() !== 8
    || !historicalStudyCopy.includes("HISTORICAL RESEARCH · REPORT ONLY") || !historicalStudyCopy.includes("Earlier Mae Sai GeoAI analysis")) {
    throw new Error("Studio's archive must show the research table for the eight subdistricts, labelled as historical research and report only.");
  }
  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  const cacheKeys = await page.evaluate(() => caches.keys());
  if (!cacheKeys.some((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key))) {
    throw new Error(`Content-versioned offline cache was not installed: ${cacheKeys.join(", ")}`);
  }

  // A fresh installation holds the blocking list only, and that list is within its 12 MB budget. The evidence
  // library's pages were opened above, yet none of its study areas has been saved: only its catalogue is cached.
  const install = verifyOfflineInstall(out);
  const installed = await page.evaluate(async ({ urls, savedCache }) => {
    const keys = await caches.keys();
    const cache = await caches.open(keys.find((entry) => /^floodguard-offline-[0-9a-f]{12}$/.test(entry)));
    let bytes = 0;
    const missing = [];
    for (const url of urls) {
      const response = await cache.match(url);
      if (response) bytes += (await response.arrayBuffer()).byteLength;
      else missing.push(url);
    }
    const paths = (await cache.keys()).map((request) => new URL(request.url).pathname);
    return { bytes, missing, library: paths.filter((path) => path.startsWith("/evidence-library/")), savedCache: keys.includes(savedCache) };
  }, { urls: [...new Set([...install.coreAssets, ...install.chunkAssets])], savedCache: EVIDENCE_AREA_CACHE });
  if (installed.missing.length > 0) throw new Error(`The installation lacks files of its blocking list: ${installed.missing.join(", ")}`);
  if (installed.bytes !== install.bytes || installed.bytes > install.budget_bytes) {
    throw new Error(`A fresh installation is ${installed.bytes} bytes; the built list is ${install.bytes} bytes and the budget ${install.budget_bytes}.`);
  }
  if (installed.library.join(",") !== EVIDENCE_CATALOG_ASSET || installed.savedCache) {
    throw new Error(`A fresh installation holds evidence-library files besides the catalogue: ${JSON.stringify(installed)}`);
  }

  // The reader asks for one study area on its page in the library: "Save this area for offline use". The worker
  // stores each file only when it matches its pinned SHA-256, in a cache apart from the per-build cache.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/studio/library/`, { waitUntil: "networkidle" });
  await page.locator("main[data-evidence-library] footer").filter({ hasText: savedCase.id }).waitFor();
  const areaRow = page.locator(`[data-evidence-offline-control="true"] [data-evidence-offline-area="${savedArea.aoi_id}"]`).first();
  await areaRow.waitFor({ state: "visible" });
  if (await areaRow.getAttribute("data-state") !== "none" || !(await areaRow.innerText()).includes("Not saved on this device")) {
    throw new Error("A study area reads as saved before the reader asked for it.");
  }
  // The library list offers every study area, each with its own request and none saved yet.
  const areaList = page.locator('[data-evidence-offline-list="true"]');
  if (await areaList.locator("[data-evidence-offline-area]").count() !== evidenceAreas.length
    || await areaList.locator('[data-evidence-offline-area][data-state="none"]').count() !== evidenceAreas.length
    || !(await areaList.locator("summary").innerText()).includes(`0 of ${evidenceAreas.length} saved on this device`)) {
    throw new Error("The library list does not offer every study area for saving, unsaved.");
  }
  await areaRow.getByRole("button", { name: /^Save this area for offline use \(/ }).click();
  await page.waitForFunction((id) => (
    document.querySelector(`[data-evidence-offline-area="${id}"]`)?.getAttribute("data-state") === "saved"
  ), savedArea.aoi_id, { timeout: 120_000 });
  if (!(await areaRow.innerText()).includes(`Saved on this device: ${savedArea.assets.length} files`) || !(await areaRow.innerText()).includes("Each file matched its SHA-256")) {
    throw new Error("The saved study area does not report its files and their hash check.");
  }
  const savedAudit = await page.evaluate(async ({ cacheName, assets }) => {
    const hex = async (response) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", await response.arrayBuffer()))]
      .map((byte) => byte.toString(16).padStart(2, "0")).join("");
    const keys = await caches.keys();
    const saved = await caches.open(cacheName);
    const build = await caches.open(keys.find((entry) => /^floodguard-offline-[0-9a-f]{12}$/.test(entry)));
    const buildPaths = (await build.keys()).map((request) => new URL(request.url).pathname);
    const verified = [];
    for (const asset of assets) {
      const response = await saved.match(asset.url);
      verified.push(Boolean(response) && response.headers.get("X-FloodGuard-SHA256") === asset.sha256 && await hex(response) === asset.sha256);
    }
    return {
      paths: (await saved.keys()).map((request) => new URL(request.url).pathname).sort(),
      verified,
      inBuildCache: assets.filter((asset) => buildPaths.includes(asset.url)).map((asset) => asset.url),
    };
  }, { cacheName: EVIDENCE_AREA_CACHE, assets: savedArea.assets });
  if (JSON.stringify(savedAudit.paths) !== JSON.stringify(savedArea.assets.map((asset) => asset.url).sort())
    || !savedAudit.verified.every(Boolean) || savedAudit.inBuildCache.length > 0) {
    throw new Error(`The saved study area is not exactly its own hash-checked files, apart from the build cache: ${JSON.stringify(savedAudit)}`);
  }

  // A new deployment whose study-area files did not change keeps the saved area. The per-build cache is replaced;
  // the saved files stay where they are and are not downloaded again.
  const firstBuild = cacheKeys.find((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
  const refetched = [];
  const watchRedeployment = (request) => {
    const path = new URL(request.url()).pathname;
    if (savedArea.assets.some((asset) => asset.url === path)) refetched.push(path);
  };
  context.on("request", watchRedeployment);
  redeployedBuild = `${firstBuild.slice(-12, -1)}${firstBuild.endsWith("0") ? "1" : "0"}`;
  await page.evaluate(async () => (await navigator.serviceWorker.getRegistration()).update());
  await waitForEvaluated(page, async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting), undefined, "the new deployment's worker to install", 120_000);
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    const controlled = new Promise((resolveChange) => navigator.serviceWorker.addEventListener("controllerchange", resolveChange, { once: true }));
    registration.waiting.postMessage({ type: "SKIP_WAITING" });
    await controlled;
  });
  // The new worker controls the page as soon as it starts to activate; its activation then removes the old build cache.
  await waitForEvaluated(page, async (expected) => {
    const builds = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    return builds.length === 1 && builds[0] === expected && (await navigator.serviceWorker.getRegistration())?.active?.state === "activated";
  }, `floodguard-offline-${redeployedBuild}`, "the new deployment to replace the build cache", 60_000);
  const redeployed = await page.evaluate(async ({ cacheName, assets }) => {
    const keys = await caches.keys();
    const saved = keys.includes(cacheName) ? await caches.open(cacheName) : null;
    const kept = saved
      ? await Promise.all(assets.map(async (asset) => (await saved.match(asset.url))?.headers.get("X-FloodGuard-SHA256") === asset.sha256))
      : [];
    return { builds: keys.filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key)), kept };
  }, { cacheName: EVIDENCE_AREA_CACHE, assets: savedArea.assets });
  context.off("request", watchRedeployment);
  if (redeployed.builds.join(",") !== `floodguard-offline-${redeployedBuild}`) {
    throw new Error(`The new deployment did not replace the build cache: ${redeployed.builds.join(", ")}`);
  }
  if (redeployed.kept.length !== savedArea.assets.length || !redeployed.kept.every(Boolean) || refetched.length > 0) {
    throw new Error(`A saved study area did not survive a new deployment unchanged: kept ${JSON.stringify(redeployed.kept)}, downloaded again ${refetched.join(", ") || "nothing"}`);
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction((id) => (
    document.querySelector(`[data-evidence-offline-area="${id}"]`)?.getAttribute("data-state") === "saved"
  ), savedArea.aoi_id);

  // The landing itself requests optional artwork after paint. Wait for every
  // srcset width, then prove all of them remain fetchable without the network.
  const artwork = readLandingArtwork(out);
  await page.goto(`${baseUrl}/`, { waitUntil: "load" });
  await waitForEvaluated(page, buildCacheHolds, artwork.map((asset) => asset.url), "the landing artwork to be saved", 60_000);

  // Case replay: once it has rendered online it asks the worker to keep its deferred data (derived from the
  // timeline manifest at build time); wait for every file, then replay it without the network below.
  const caseReplay = readCaseReplay(out);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}${caseReplay.route}`, { waitUntil: "load" });
  await page.getByTestId("replay-readout").waitFor({ state: "visible" });
  await waitForEvaluated(page, buildCacheHolds, caseReplay.assets.map((asset) => asset.url), "the case replay's data to be saved", 60_000);
  await page.getByText(`Offline copy: this replay's ${caseReplay.assets.length} data files are saved on this device`, { exact: false })
    .waitFor({ state: "attached", timeout: 15_000 });
  // The export pack (download files) is saved by the same request, after the replay data and counted apart from it.
  await waitForEvaluated(page, buildCacheHolds, caseReplay.exports.assets.map((asset) => asset.url), "the case replay's export files to be saved", 60_000);
  await page.getByText(`Offline copy: the ${caseReplay.exports.assets.length} download files are saved on this device too`, { exact: false })
    .waitFor({ state: "attached", timeout: 15_000 });

  offlineMode = true;
  await context.setOffline(true);
  const artworkOffline = await page.evaluate(async (urls) => Promise.all(urls.map(async (url) => {
    const response = await fetch(url);
    return response.ok && (await response.arrayBuffer()).byteLength > 0;
  })), artwork.map((asset) => asset.url));
  if (!artworkOffline.every(Boolean)) throw new Error("An approved artwork variant is missing offline.");
  for (const route of routes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
    await page.locator(route.selector).waitFor({ state: "visible" });
    await waitForFinalVisibleCopy(page, route.path);
    if (route.path === "/public/") {
      await assertCompactPublicShell(page);
      await assertPublicNavigation(page);
      for (const [id, selector] of [
        ["home", "#main-content .leaflet-container"],
        ["report", "#main-content .public-report-page"],
        ["shelter", "#main-content .public-shelter-page, #main-content .public-shelter-view"],
        ["prepare", "#main-content #household-plan-builder"],
        ["sos", "#main-content .public-sos-page, #main-content .public-sos-view"],
      ]) {
        await activatePublicPage(page, id, selector);
      }
      await activatePublicPage(page, "home", "#main-content .leaflet-container");
      const offlinePublicMapScope = await firstVisibleSelector(page, [
        ".public-home-page",
        ".public-home-view",
        ".public-map-view",
      ]);
      // Public Home renders its role-approved preparedness-area overlay (see the
      // first assertMaeSaiMap call); the same holds after the offline reload.
      await assertMaeSaiMap(page, offlinePublicMapScope, {
        expectRoads: false,
        expectTextAlternative: true,
        expectBoundary: true,
      });
      await page.waitForFunction((scope) => (
        document.querySelector(`${scope} .geo-map-shell`)?.getAttribute("data-basemap-state") === "offline"
      ), offlinePublicMapScope);
    }
  }

  // The study area the reader saved opens without a connection and passes its hash check: the page verifies the
  // package against the catalogue's SHA-256 before it shows anything, and every saved file still has its pinned hash.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}/studio/library/?aoi=${savedCase.aoi_id}&event=${savedCase.event_id}`, { waitUntil: "domcontentloaded" });
  const library = page.locator("main[data-evidence-library]");
  await library.locator("footer").filter({ hasText: savedCase.id }).waitFor();
  const savedLibraryText = await library.innerText();
  if (!savedLibraryText.includes("HASH-VERIFIED PACKAGE") || await library.getByRole("alert").count() !== 0) {
    throw new Error("The saved study area did not open, verified, without a connection.");
  }
  const savedOffline = await page.evaluate(async (assets) => Promise.all(assets.map(async (asset) => {
    const response = await fetch(asset.url);
    const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
    return response.ok && [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("") === asset.sha256;
  })), savedArea.assets);
  if (!savedOffline.every(Boolean)) throw new Error("A file of the saved study area is missing or changed offline.");
  await page.waitForFunction((id) => (
    document.querySelector(`[data-evidence-offline-area="${id}"]`)?.getAttribute("data-state") === "saved"
  ), savedArea.aoi_id);
  // The report is part of the saved copy; the database archives never are, and say so instead of offering a dead link.
  const savedPackage = JSON.parse(readFileSync(resolve(out, savedCase.url.slice(1)), "utf8"));
  await library.getByRole("link", { name: "Download report", exact: true }).waitFor({ state: "visible" });
  if (await library.getByRole("link", { name: "Download report", exact: true }).count() !== 1
    || await library.locator('[data-evidence-download-offline="database"]').count() !== (savedPackage.downloads ?? []).length
    || await library.locator('a[href^="/evidence-library/databases/"]').count() !== 0) {
    throw new Error("Offline, the saved study area must offer its report and mark its database archives as needing a connection.");
  }
  await page.goto(`${baseUrl}/studio/candidate-report/?aoi=${savedCase.aoi_id}&event=${savedCase.event_id}`, { waitUntil: "domcontentloaded" });
  await page.locator(`main[data-evidence-case-id="${savedCase.id}"]`).waitFor({ state: "visible" });
  if (!(await page.locator("main[data-evidence-case-id]").innerText()).includes("Catalog SHA-256 matches")) {
    throw new Error("The saved study area's package did not pass its catalogue hash check offline.");
  }

  // A study area that was not saved: every page that reads it says so plainly, shows nothing of the package and
  // does not even request its files.
  const unsavedRequests = [];
  const watchLibraryRequests = (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/evidence-library/") && path !== EVIDENCE_CATALOG_ASSET) unsavedRequests.push(path);
  };
  page.on("request", watchLibraryRequests);
  const unsavedQuery = `aoi=${unsavedCase.aoi_id}&event=${unsavedCase.event_id}`;
  for (const path of ["/studio/library/", "/studio/brief/", "/command/cases/", "/public-cases/", "/command/", "/studio/candidate-report/"]) {
    await page.goto(`${baseUrl}${path}?${unsavedQuery}`, { waitUntil: "domcontentloaded" });
    const unavailable = page.locator('[data-evidence-unavailable="offline_not_saved"]');
    await unavailable.first().waitFor({ state: "visible" });
    if (!(await unavailable.first().innerText()).includes("You are offline, and this study area is not saved on this device, so none of its data is shown.")) {
      throw new Error(`${path} does not say plainly that the study area is not saved on this device.`);
    }
    await page.waitForFunction((id) => (
      document.querySelector(`[data-evidence-offline-area="${id}"]`)?.getAttribute("data-state") === "none"
    ), unsavedCase.aoi_id);
    await page.waitForFunction(() => !/Verifying|Loading (?:and verifying|case catalog|evidence catalog)/.test(document.body.innerText));
    const body = await page.locator("body").innerText();
    const looksLoaded = ["HASH-VERIFIED PACKAGE", "Traceable evidence package", unsavedCase.id, "Accepted FPPS / action class", "Catalog SHA-256 matches", "Download report", "Loading and verifying", "Verifying"]
      .filter((text) => body.includes(text));
    const loadedBlocks = await page.locator("[data-decision-brief], [data-public-case-summary], [data-feature-browser], [data-route-comparison], [data-case-id], [data-evidence-case-id], main .leaflet-container").count();
    if (looksLoaded.length > 0 || loadedBlocks > 0) {
      throw new Error(`${path} shows something of a study area that is not saved, offline: ${looksLoaded.join(", ")} (${loadedBlocks} blocks)`);
    }
    const unsavedRow = page.locator(`[data-evidence-offline-area="${unsavedCase.aoi_id}"]`).first();
    if (!(await unsavedRow.innerText()).includes("Connect to the internet to save this area.") || !await unsavedRow.locator('button[data-action="save"]').isDisabled()) {
      throw new Error(`${path} offers to save a study area without a connection.`);
    }
    if (path === "/command/" && await page.locator('main[data-planning-candidate="unavailable"]').count() !== 1) {
      throw new Error("The planning overview does not mark an unsaved study area as unavailable.");
    }
  }
  page.off("request", watchLibraryRequests);
  if (unsavedRequests.length > 0) throw new Error(`Files of a study area that is not saved were requested offline: ${[...new Set(unsavedRequests)].join(", ")}`);

  // The saved copy can be removed (no connection is needed for that). Afterwards the area reads as not saved.
  await page.goto(`${baseUrl}/studio/library/?aoi=${savedCase.aoi_id}&event=${savedCase.event_id}`, { waitUntil: "domcontentloaded" });
  await library.locator("footer").filter({ hasText: savedCase.id }).waitFor();
  const removableRow = page.locator(`[data-evidence-offline-area="${savedArea.aoi_id}"]`).first();
  await removableRow.getByRole("button", { name: "Remove saved copy", exact: true }).click();
  await page.waitForFunction((id) => (
    document.querySelector(`[data-evidence-offline-area="${id}"]`)?.getAttribute("data-state") === "none"
  ), savedArea.aoi_id);
  if (await page.evaluate(async (cacheName) => (await caches.keys()).includes(cacheName), EVIDENCE_AREA_CACHE)) {
    throw new Error("Removing the only saved study area left its cache behind.");
  }
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.locator('[data-evidence-unavailable="offline_not_saved"]').first().waitFor({ state: "visible" });
  if (await library.locator("footer").filter({ hasText: savedCase.id }).count() !== 0) {
    throw new Error("A removed study area still opens without a connection.");
  }

  // The saved case replay renders offline at a shared moment; only the street basemap is missing, and says so.
  await page.goto(`${baseUrl}${caseReplay.route}?t=84&wm=arrival`, { waitUntil: "domcontentloaded" });
  const offlineReadout = page.getByTestId("replay-readout");
  await offlineReadout.waitFor({ state: "visible" });
  await page.waitForFunction(() => document.querySelector("[data-testid='replay-readout']")?.textContent?.includes("12 Sep 2024 · 12:00"));
  await page.getByTestId("basemap-note").waitFor({ state: "visible" });
  if (!/basemap/i.test(await page.getByTestId("basemap-note").innerText())) throw new Error("The offline replay does not explain the online-only basemap.");
  await page.getByText("First flooded (model, local time)", { exact: true }).waitFor({ state: "visible" });
  await page.waitForFunction(() => !document.body.innerText.includes("Preparing the water model"), undefined, { timeout: 30_000 });
  if (await page.locator("main").getByRole("alert").count() !== 0) {
    throw new Error(`The saved case replay failed offline: ${await page.locator("main").getByRole("alert").first().innerText()}`);
  }
  // Opened without a connection, the saved replay still says it is saved: the worker cannot re-check the deployment
  // profile offline, and must then report what its cache holds instead of "0 of N files".
  await page.getByText(`Offline copy: this replay's ${caseReplay.assets.length} data files are saved on this device`, { exact: false })
    .waitFor({ state: "attached", timeout: 15_000 });
  await page.getByText(`Offline copy: the ${caseReplay.exports.assets.length} download files are saved on this device too`, { exact: false })
    .waitFor({ state: "attached", timeout: 15_000 });
  if (await page.getByText("Offline copy incomplete", { exact: false }).count() !== 0) {
    throw new Error("The saved case replay reports an incomplete offline copy when it is opened without a connection.");
  }
  await page.locator('input[type="range"][aria-label="Replay time (hourly)"]').fill("120");
  await page.waitForFunction(() => document.querySelector("[data-testid='replay-readout']")?.textContent?.includes("14 Sep 2024 · 00:00"));
  // The residents raster and the access node file come from the same offline copy.
  await page.goto(`${baseUrl}${caseReplay.route}?t=84&wm=people&set=plan&k=3&layers=trfscx`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("people-in-water").waitFor({ state: "visible", timeout: 30_000 });
  await page.getByTestId("set-comparison").waitFor({ state: "visible", timeout: 30_000 });
  // The shelter-set comparison is computed from the saved node file: the plan of 3 reaches 17,794 residents before the flood.
  if ((await page.getByTestId("compare-plan-all-baseline").innerText()).replace(/\s+/g, " ").trim() !== "17,794 of 81,799") {
    throw new Error(`The saved access node file gives an unexpected plan baseline: ${await page.getByTestId("compare-plan-all-baseline").innerText()}`);
  }
  await page.getByText("People in flood water: residents per hectare (WorldPop 2020, model)", { exact: true }).waitFor({ state: "visible" });
  await page.waitForFunction(() => !/Preparing the (residents layer|access scenario)/.test(document.body.innerText), undefined, { timeout: 30_000 });
  if (await page.locator("main").getByRole("alert").count() !== 0) {
    throw new Error(`The saved residents or access data failed offline: ${await page.locator("main").getByRole("alert").first().innerText()}`);
  }
  // The observed VIIRS daily maps come from the same offline copy.
  await page.goto(`${baseUrl}${caseReplay.route}?t=158&layers=trfv`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => {
    const image = document.querySelector(".leaflet-fg-viirs-pane img");
    return Boolean(image && image.complete && image.naturalWidth > 0);
  }, undefined, { timeout: 30_000 });
  // The reported depths (news, not surveyed) live inside the manifest, so the saved manifest draws them without a
  // connection: the markers by link, holding all 12 located place records (nearby places share a marker), and the
  // counts table in the Sources panel.
  await page.goto(`${baseUrl}${caseReplay.route}?t=84&layers=trd`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => [...document.querySelectorAll(".leaflet-fg-reported-depths-pane [class*='reportedDepthIcon']")]
    .flatMap((marker) => (marker.getAttribute("data-reports") ?? "").split(" ").filter(Boolean)).length === 12, undefined, { timeout: 30_000 });
  if (await page.getByTestId("reported-depth-counts").count() !== 1) throw new Error("The reported depths' counts table is missing offline.");
  // The season envelope (UNOSAT and GISTDA product 4009, a scenario layer) comes from the same offline copy: its raster,
  // its statistics and its licence notice. With its toggle on, by link, the layer is drawn hatched and credited without a
  // connection, at 1440 px and at 390 px, clear of the legend, the notes, the zoom buttons and the attribution.
  const envelopeAssets = caseReplay.assets.filter((asset) => asset.url.includes("/unosat4009/"));
  if (envelopeAssets.map((asset) => asset.url.split("/").at(-1)).sort().join(",") !== "LICENSE,envelope.json,envelope.png") {
    throw new Error(`The offline copy does not list the season envelope's three files: ${envelopeAssets.map((asset) => asset.url).join(", ")}`);
  }
  const offlineEnvelopeFiles = await page.evaluate(async (assets) => Promise.all(assets.map(async (asset) => {
    const response = await fetch(asset.url);
    const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
    return response.ok && [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("") === asset.sha256;
  })), envelopeAssets);
  if (!offlineEnvelopeFiles.every(Boolean)) throw new Error("A season-envelope file (raster, statistics or licence notice) is missing or changed offline.");
  const envelopeOffline = [];
  for (const [width, height] of [[1440, 1000], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.goto(`${baseUrl}${caseReplay.route}?t=84&layers=trsce`, { waitUntil: "domcontentloaded" });
    await page.locator(".leaflet-fg-envelope-pane canvas").waitFor({ state: "attached", timeout: 30_000 });
    await page.getByTestId("envelope-chip").waitFor({ state: "visible" });
    await page.waitForFunction(() => !document.body.innerText.includes("Preparing the water model"), undefined, { timeout: 30_000 });
    await page.waitForFunction(() => (document.querySelector(".leaflet-control-attribution")?.textContent ?? "").includes("UNOSAT and GISTDA · CC BY-SA 4.0"), undefined, { timeout: 15_000 });
    await page.getByTestId("basemap-note").waitFor({ state: "visible" });
    const state = await page.evaluate(() => {
      const canvas = document.querySelector(".leaflet-fg-envelope-pane canvas");
      const scale = canvas.getBoundingClientRect().width / canvas.width;
      const image = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      const colours = new Set();
      const periods = [];
      for (let y = 16; y < canvas.height; y += 16) {
        let lastDarkStart = -1;
        let inDark = false;
        for (let x = 0; x < canvas.width; x += 1) {
          const at = (y * canvas.width + x) * 4;
          if (image[at + 3] === 0) {
            lastDarkStart = -1;
            inDark = false;
            continue;
          }
          colours.add(`${image[at]},${image[at + 1]},${image[at + 2]},${image[at + 3]}`);
          const dark = image[at] < 100 && image[at + 3] > 200;
          if (dark && !inDark) {
            if (lastDarkStart >= 0) periods.push(x - lastDarkStart);
            lastDarkStart = x;
          }
          inDark = dark;
        }
      }
      periods.sort((a, b) => a - b);
      const frame = document.querySelector("[class*='mapFrame']").getBoundingClientRect();
      const boxes = [".leaflet-control-zoom", "[data-testid='map-notes']", "[data-testid='map-legend']", "[data-testid='envelope-chip']", "[data-testid='basemap-note']", ".leaflet-control-attribution"]
        .flatMap((selector) => {
          const element = document.querySelector(selector);
          if (!element) return [];
          const style = getComputedStyle(element);
          const box = element.getBoundingClientRect();
          return box.width === 0 || box.height === 0 || style.display === "none" || style.visibility === "hidden" || Number(style.opacity) < 0.05 ? [] : [[selector, box]];
        });
      const overlapping = [];
      const outside = [];
      for (const [index, [name, a]] of boxes.entries()) {
        if (a.left < frame.left - 0.5 || a.right > frame.right + 0.5 || a.top < frame.top - 0.5 || a.bottom > frame.bottom + 0.5) outside.push(name);
        for (const [other, b] of boxes.slice(index + 1)) {
          if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5) overlapping.push(`${name} over ${other}`);
        }
      }
      return {
        colours: colours.size, periodPx: periods.length ? Math.round(periods[Math.floor(periods.length / 2)] * scale * 10) / 10 : 0, samples: periods.length,
        chip: document.querySelector("[data-testid='envelope-chip']").textContent,
        caption: document.querySelector("[data-testid='envelope-caption']")?.textContent ?? "",
        exportCredits: document.querySelector("[data-testid='export-credits']")?.textContent ?? "",
        scroll: document.documentElement.scrollWidth - window.innerWidth, overlapping, outside,
      };
    });
    if (state.chip !== "Scenario (SCN-ENV): 2024 season envelope" || !state.caption.includes("not an observation for any replay day")
      || !state.caption.includes("FloodGuard did not validate it.")
      || !state.caption.includes("Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.")
      || !state.exportCredits.includes("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · clipped to Mae Sai district and rasterised by FloodGuard")) {
      throw new Error(`The saved season envelope lacks its chip, caption or credit offline at ${width} px: ${JSON.stringify(state)}`);
    }
    if (state.colours !== 3 || state.samples < 150 || state.periodPx < 7 || state.periodPx > 12) {
      throw new Error(`The saved season envelope is not hatched offline at ${width} px: ${JSON.stringify(state)}`);
    }
    if (state.overlapping.length > 0 || state.outside.length > 0 || state.scroll > 1) {
      throw new Error(`The saved season envelope overlaps or overflows offline at ${width} px: ${JSON.stringify(state)}`);
    }
    if (await page.locator("main").getByRole("alert").count() !== 0) {
      throw new Error(`The saved season envelope failed offline: ${await page.locator("main").getByRole("alert").first().innerText()}`);
    }
    envelopeOffline.push(`${width} px: hatch period ${state.periodPx} px`);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${baseUrl}${caseReplay.route}?t=158&layers=trfv`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("replay-readout").waitFor({ state: "visible" });
  // The download links of the saved replay work without a connection: every export file answers with the bytes the
  // manifest lists, and a click on a link saves the file under its own name.
  const offlineDownloads = await page.evaluate(async (assets) => Promise.all(assets.map(async (asset) => {
    const response = await fetch(asset.url);
    const digest = await crypto.subtle.digest("SHA-256", await response.arrayBuffer());
    return response.ok && [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("") === asset.sha256;
  })), caseReplay.exports.assets);
  if (!offlineDownloads.every(Boolean)) throw new Error("An export file of the saved replay is missing or changed offline.");
  await page.getByTestId("sources-panel").locator("summary").click();
  const roadTable = caseReplay.exports.assets.find((asset) => asset.url.endsWith("/modelled_road_inundation_by_hour.csv"));
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 20_000 }),
    page.getByTestId("export-modelled_road_inundation_by_hour").click(),
  ]);
  if (download.suggestedFilename() !== "modelled_road_inundation_by_hour.csv") {
    throw new Error(`The offline download has an unexpected file name: ${download.suggestedFilename()}`);
  }
  const savedTable = readFileSync(await download.path());
  if (!roadTable || createHash("sha256").update(savedTable).digest("hex") !== roadTable.sha256 || savedTable.byteLength !== roadTable.bytes) {
    throw new Error("The road table downloaded offline differs from the file the manifest lists.");
  }
  // Excel reads the Thai text only with the UTF-8 byte-order mark; the table says what it is before its first row.
  if (savedTable[0] !== 0xef || savedTable[1] !== 0xbb || savedTable[2] !== 0xbf || !savedTable.toString("utf8").includes("not an observed closure record")) {
    throw new Error("The road table downloaded offline lacks its byte-order mark or its standing sentence.");
  }

  if (externalRequests.length > 0) {
    throw new Error(`Unapproved external requests were attempted: ${externalRequests.join(", ")}`);
  }
  for (const origin of approvedBasemapOrigins) {
    if (!approvedBasemapOriginsSeen.has(origin)) {
      throw new Error(`Basemap selector never requested approved provider ${origin}.`);
    }
  }
  if (pageErrors.length > 0 || consoleErrors.length > 0 || unexpectedRequestFailures.length > 0) {
    throw new Error(
      `Offline browser errors: ${[
        ...pageErrors,
        ...consoleErrors,
        ...unexpectedRequestFailures,
      ].join(" | ")}`,
    );
  }
  await context.close();

  const legacyDashboard = resolve(process.cwd(), "..", "..", "outputs", "dashboard.html");
  if (!existsSync(legacyDashboard)) throw new Error("Legacy static dashboard is missing.");
  const legacyContext = await browser.newContext({ serviceWorkers: "block" });
  await legacyContext.setOffline(true);
  const legacyPage = await legacyContext.newPage();
  const legacyPageErrors = [];
  legacyPage.on("pageerror", (error) => legacyPageErrors.push(error.message));
  await legacyPage.setContent(readFileSync(legacyDashboard, "utf8"), { waitUntil: "load" });
  await legacyPage.locator("#map.leaflet-container").waitFor({ state: "visible" });
  await legacyPage.locator("#map .leaflet-overlay-pane canvas").waitFor({ state: "attached" });
  const basemapStatus = await legacyPage.locator("#basemap-status").innerText();
  if (!basemapStatus.includes("Offline mode; embedded vector layers remain active")) {
    throw new Error(`Legacy dashboard lacks its offline basemap disclosure: ${basemapStatus}`);
  }
  if (await legacyPage.locator('script[src^="http"], link[href^="http"]').count()) {
    throw new Error("Legacy dashboard retains an external initial-load dependency.");
  }
  const textAlternative = legacyPage.locator("#offline-map-fallback");
  if (!(await textAlternative.innerText()).includes("Offline map text equivalent")) {
    throw new Error("Legacy dashboard lacks its embedded map text equivalent.");
  }
  await legacyPage.locator("#dataset-mode-select").selectOption("mae_sai_weak_reference");
  if (await legacyPage.locator("#dataset-mode-select").inputValue() !== "mae_sai_weak_reference") {
    throw new Error("Legacy dashboard dataset control failed while offline.");
  }
  if (legacyPageErrors.length > 0) {
    throw new Error(`Legacy offline dashboard errors: ${legacyPageErrors.join(" | ")}`);
  }
  await legacyContext.close();
  console.log(
    `browser offline smoke: ${routes.length} routes rendered from a content-versioned service-worker cache; a fresh installation is ${install.files} files, ${megabytes(installed.bytes)} of ${megabytes(install.budget_bytes)} MB budget (${installed.bytes} bytes) with no study area in it; the study area ${savedArea.aoi_id} (${savedArea.assets.length} files, ${megabytes(savedArea.bytes)} MB) was saved on request, kept through a new deployment without a download, opened offline with every file matching its SHA-256, and was removed; the unsaved area ${unsavedCase.aoi_id} said so on six pages without a request; the phone map notice stays one line and one button clear of the map controls (${phoneNotice.join("; ")}); Command shows the research-report notice and Studio's archive the table; the case replay and its ${caseReplay.assets.length} opt-in data files replayed offline, the season envelope's raster, statistics and licence notice among them (toggle on, hatched and credited: ${envelopeOffline.join("; ")}), the reported depths' markers (all 12 located place records) and counts table from the saved manifest, and its ${caseReplay.exports.assets.length} export files downloaded offline (${caseReplay.exports.bytes} of ${caseReplay.exports.budget_bytes} export-budget bytes); approved basemaps failed gracefully and no unapproved external requests occurred`,
  );
  console.log("legacy dashboard offline smoke: embedded Leaflet vectors, text equivalent, and dataset control verified");
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose());
  });
}

/**
 * Poll an async page function until it returns a truthy value. `page.waitForFunction` runs an async function once
 * and resolves with whatever it returns, so it cannot wait on the Cache or the service-worker registration.
 */
async function waitForEvaluated(page, predicate, argument, description, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.evaluate(predicate, argument)) return;
    await page.waitForTimeout(100);
  }
  throw new Error(`Timed out waiting for ${description}.`);
}

/** Runs in the page: true when the current build cache holds every listed URL. */
async function buildCacheHolds(urls) {
  const key = (await caches.keys()).find((entry) => /^floodguard-offline-[0-9a-f]{12}$/.test(entry));
  if (!key) return false;
  const cache = await caches.open(key);
  return (await Promise.all(urls.map((url) => cache.match(url)))).every(Boolean);
}

async function assertCompactPublicShell(page) {
  const header = page.locator(".public-app-header");
  if (await header.count() !== 1 || !(await header.isVisible())) {
    throw new Error("Public is missing its compact app header.");
  }
  if (await page.locator(".public-header-logo[aria-label='FloodGuard home']").count() !== 1) {
    throw new Error("Public is missing the FloodGuard home control.");
  }
  if (await page.locator(".public-greeting .public-greeting-name").count() !== 1) {
    throw new Error("Public is missing the household greeting.");
  }
  if (await page.locator(".public-brand-mark, .public-boundary-banner").count()) {
    throw new Error("Public retains the removed logo or historical banner.");
  }
  const publicText = await page.locator("main.public-page").innerText();
  if (/Public preparedness|Historical preparedness information/iu.test(publicText)) {
    throw new Error("Public retains removed header or historical-banner copy.");
  }
  const trigger = page.locator(".public-profile-trigger");
  await trigger.click();
  await page.locator("#public-profile-drawer").waitFor({ state: "visible" });
  await page.locator("#public-profile-drawer .public-icon-button").click();
  if (await trigger.getAttribute("aria-expanded") !== "false") {
    throw new Error("Public profile drawer did not close.");
  }
}

async function assertPublicNavigation(page) {
  const expected = ["home", "report", "shelter", "prepare", "sos"];
  const navigation = page.locator(".public-bottom-nav");
  if (await navigation.count() !== 1 || !(await navigation.isVisible())) {
    throw new Error("Public bottom navigation is missing.");
  }
  for (const id of expected) {
    if (await page.locator(`#public-tab-${id}`).count() !== 1) {
      throw new Error(`Public bottom navigation is missing ${id}.`);
    }
  }
  for (const retired of ["map", "shelters", "data"]) {
    if (await page.locator(`#public-tab-${retired}`).count()) {
      throw new Error(`Public retains retired navigation: ${retired}.`);
    }
  }
  const activeCount = await navigation.locator(
    '[aria-current="page"], [aria-pressed="true"], [aria-selected="true"]',
  ).count();
  if (activeCount !== 1) {
    throw new Error(`Public navigation must expose exactly one active page; found ${activeCount}.`);
  }
}

async function activatePublicPage(page, id, readySelector) {
  const button = page.locator(`#public-tab-${id}`);
  await button.click();
  await page.locator(readySelector).first().waitFor({ state: "visible" });
  const state = await button.evaluate((element) => ({
    current: element.getAttribute("aria-current"),
    pressed: element.getAttribute("aria-pressed"),
    selected: element.getAttribute("aria-selected"),
  }));
  if (state.current !== "page" && state.pressed !== "true" && state.selected !== "true") {
    throw new Error(`Public navigation did not expose ${id} as active.`);
  }
  const visibleText = await page.locator("#main-content").innerText();
  const forbidden = visibleText.match(
    /(?:^|[^\p{L}\p{N}])(?:demos?|prototypes?|mocks?|samples?|illustrative|placeholders?)(?=$|[^\p{L}\p{N}])|coming soon|under construction|not ready|work in progress/iu,
  );
  if (forbidden) throw new Error(`Public ${id} exposes development-state copy: ${forbidden[0]}.`);
}

async function selectPublicPlanningArea(page, areaId, areaName) {
  const select = page.locator("#public-area-select");
  if (await select.count()) {
    await select.selectOption(areaId);
    await page.waitForFunction(
      ({ id }) => document.querySelector("#public-area-select")?.value === id,
      { id: areaId },
    );
    return;
  }

  const search = page.locator(
    "#public-area-search, .public-home-search input, .public-map-search input, input[aria-label*=\"Search\"]",
  ).first();
  if (!await search.count()) throw new Error("Public Home is missing its area search control.");
  await search.fill(areaName);
  await search.press("Enter");
  await page.waitForFunction(
    ({ id }) => document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === id,
    { id: areaId },
  );
}

async function firstVisibleSelector(page, selectors) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if (await locator.count() && await locator.isVisible()) return selector;
  }
  throw new Error(`None of the expected Public selectors is visible: ${selectors.join(", ")}.`);
}

async function assertPublicHomeLayout(page, mapScope) {
  const audit = await page.evaluate((scope) => {
    const header = document.querySelector(".public-app-header")?.getBoundingClientRect();
    const navigation = document.querySelector(".public-bottom-nav")?.getBoundingClientRect();
    const map = document.querySelector(`${scope} .leaflet-container`)?.getBoundingClientRect();
    const trigger = document.querySelector(".public-profile-trigger")?.getBoundingClientRect();
    const priorityIndicator = document.querySelector(".public-risk-indicator");
    const risk = priorityIndicator?.getBoundingClientRect();
    const hazard = document.querySelector(".public-hazard-button")?.getBoundingClientRect();
    const attribution = document.querySelector(".leaflet-control-attribution")?.getBoundingClientRect();
    const availability = document.querySelector('[data-pwa-availability="true"] > summary')?.getBoundingClientRect();
    const closedAvailability = document.querySelector('[data-pwa-availability="true"]:not([open])')?.getBoundingClientRect();
    // The status pill belongs in the slot under the header. A rule written for the floating pill once moved it
    // 128 px down, onto the first action button, while it was still inside the slot in the document.
    const availabilitySlot = document.querySelector("[data-app-availability-slot]");
    const slot = availabilitySlot?.getBoundingClientRect();
    const actions = document.querySelector(".public-home-actions")?.getBoundingClientRect();
    const listSummary = document.querySelector(".map-text-alternative > summary");
    const listBounds = listSummary?.getBoundingClientRect();
    const listPointerTarget = listBounds && document.elementFromPoint(
      listBounds.left + listBounds.width / 2,
      listBounds.top + listBounds.height / 2,
    );
    const mapControls = [...document.querySelectorAll(
      ".leaflet-control-zoom a, .public-locate-button, .map-basemap-menu > summary, .map-text-alternative > summary, .public-signal-banner",
    )].map((element) => element.getBoundingClientRect());
    const navigationTargets = [...document.querySelectorAll(".public-bottom-nav button")]
      .map((element) => element.getBoundingClientRect());
    const overlaps = (left, right) => Boolean(left && right
      && Math.min(left.right, right.right) > Math.max(left.left, right.left)
      && Math.min(left.bottom, right.bottom) > Math.max(left.top, right.top));
    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      header: header ? { top: header.top, bottom: header.bottom, height: header.height } : null,
      navigation: navigation ? { top: navigation.top, bottom: navigation.bottom } : null,
      map: map ? { top: map.top, right: map.right, bottom: map.bottom, left: map.left } : null,
      trigger: trigger ? { width: trigger.width, height: trigger.height } : null,
      navigationTargets: navigationTargets.map(({ width, height }) => ({ width, height })),
      lowerControls: {
        priority: risk?.toJSON(),
        priorityContentWidth: priorityIndicator?.scrollWidth,
        priorityClientWidth: priorityIndicator?.clientWidth,
        attribution: attribution?.toJSON(),
        availability: availability?.toJSON(),
        riskNavigationGap: risk && navigation ? navigation.top - risk.bottom : null,
        hazardNavigationGap: hazard && navigation ? navigation.top - hazard.bottom : null,
        hazardAttributionOverlap: overlaps(hazard, attribution),
        availabilityRiskOverlap: overlaps(availability, risk),
        availabilityHazardOverlap: overlaps(availability, hazard),
        availabilityAttributionOverlap: overlaps(availability, attribution),
        availabilityMapControlOverlap: mapControls.some((control) => overlaps(availability, control)),
        availabilitySlot: slot?.toJSON(),
        availabilityInSlot: Boolean(availabilitySlot?.querySelector('[data-pwa-availability="true"]')),
        availabilityInsideSlotBox: Boolean(availability && slot
          && availability.left >= slot.left - 1 && availability.right <= slot.right + 1
          && availability.top >= slot.top - 1 && availability.bottom <= slot.bottom + 1),
        availabilityActionsOverlap: overlaps(availability, actions),
        closedAvailabilityListOverlap: overlaps(closedAvailability, listBounds),
        listReceivesPointer: Boolean(listSummary && listPointerTarget && listSummary.contains(listPointerTarget)),
      },
    };
  }, mapScope);
  if (!audit.header || !audit.navigation || !audit.map) {
    throw new Error(`Public Home layout landmarks are missing: ${JSON.stringify(audit)}.`);
  }
  if (audit.documentWidth > audit.viewportWidth + 1) {
    throw new Error(`Public Home has horizontal overflow: ${JSON.stringify(audit)}.`);
  }
  if (
    audit.map.top < audit.header.bottom - 2
    || audit.map.bottom - audit.map.top < 300
    || Math.abs(audit.map.bottom - audit.navigation.top) > 2
    || audit.map.left > 1
    || audit.map.right < audit.viewportWidth - 1
  ) {
    throw new Error(`Public Home map is clipped or leaves the space above navigation: ${JSON.stringify(audit)}.`);
  }
  if (audit.header.height > 58) {
    throw new Error(`Public header is not compact: ${audit.header.height}px.`);
  }
  if (!audit.trigger || audit.trigger.width < 43.5 || audit.trigger.height < 43.5) {
    throw new Error(`Public profile trigger is smaller than 44px: ${JSON.stringify(audit.trigger)}.`);
  }
  if (audit.navigationTargets.some(({ width, height }) => width < 43.5 || height < 43.5)) {
    throw new Error("Public bottom navigation contains a touch target smaller than 44px.");
  }
  if (
    audit.lowerControls.priorityContentWidth > audit.lowerControls.priorityClientWidth + 1
    || audit.lowerControls.riskNavigationGap < 10
    || audit.lowerControls.hazardNavigationGap < 10
    || audit.lowerControls.hazardAttributionOverlap
    || audit.lowerControls.availabilityRiskOverlap
    || audit.lowerControls.availabilityHazardOverlap
    || audit.lowerControls.availabilityAttributionOverlap
    || audit.lowerControls.availabilityMapControlOverlap
    || !audit.lowerControls.availabilityInSlot
    || !audit.lowerControls.availabilityInsideSlotBox
    || audit.lowerControls.availabilityActionsOverlap
    || audit.lowerControls.closedAvailabilityListOverlap
    || !audit.lowerControls.listReceivesPointer
  ) {
    throw new Error(`Public Home controls overlap, crowd the navigation, or the status pill left its slot: ${JSON.stringify(audit.lowerControls)}.`);
  }
}

/**
 * The map-background notice on a phone, folded (its default): one line of text and one button, inside the map and
 * clear of the list button, the search field and every map tool. Opened, it shows the sentence and the actions above
 * the other controls, and folds back.
 */
async function assertPhoneMapNotice(page, mapScope, language, label) {
  const notice = page.locator(`${mapScope} .map-basemap-notice`);
  await notice.waitFor({ state: "visible" });
  if (await page.locator(`${mapScope} .geo-map-shell`).getAttribute("data-basemap-state") !== "unavailable") {
    throw new Error(`The map background is expected to be unavailable for the notice check at ${label}.`);
  }
  const measure = () => page.evaluate((scope) => {
    const visibleBox = (element) => {
      if (!element) return null;
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && style.display !== "none" && style.visibility !== "hidden" ? box : null;
    };
    const notice = document.querySelector(`${scope} .map-basemap-notice`);
    const box = visibleBox(notice);
    const map = document.querySelector(`${scope} .leaflet-container`).getBoundingClientRect();
    const controls = {
      "list button": `${scope} .map-text-alternative > summary`,
      "search field": `${scope} .public-map-search-field`,
      "map layers button": `${scope} .map-basemap-menu > summary`,
      "zoom buttons": `${scope} .leaflet-control-zoom`,
      "locate button": ".public-locate-button",
      "map attribution": `${scope} .leaflet-control-attribution`,
      "priority card": ".public-risk-indicator",
      "hazard button": ".public-hazard-button",
      "signal banner": ".public-signal-banner",
      "status pill": '[data-pwa-availability="true"] > summary',
    };
    const overlaps = [];
    const found = [];
    for (const [name, selector] of Object.entries(controls)) {
      const other = visibleBox(document.querySelector(selector));
      if (!other) continue;
      found.push(name);
      const width = Math.min(box.right, other.right) - Math.max(box.left, other.left);
      const height = Math.min(box.bottom, other.bottom) - Math.max(box.top, other.top);
      if (width > 0.5 && height > 0.5) overlaps.push(`${name} ${Math.round(width)}x${Math.round(height)}`);
    }
    const paragraph = notice.querySelector("p");
    const top = document.elementFromPoint(box.left + box.width / 2, box.top + Math.min(box.height / 2, 20));
    return {
      expanded: notice.getAttribute("data-expanded"),
      text: notice.innerText.replace(/\s+/g, " ").trim(),
      buttons: [...notice.querySelectorAll("button")].filter((button) => visibleBox(button)).map((button) => button.textContent.trim()),
      lines: Math.round(paragraph.getBoundingClientRect().height / Number.parseFloat(getComputedStyle(paragraph).lineHeight)),
      truncated: paragraph.scrollWidth > paragraph.clientWidth + 1,
      height: Math.round(box.height),
      insideMap: box.left >= map.left - 0.5 && box.right <= map.right + 0.5 && box.top >= map.top - 0.5 && box.bottom <= map.bottom + 0.5,
      onTop: Boolean(top && notice.contains(top)),
      overlaps,
      found,
      scroll: document.documentElement.scrollWidth - window.innerWidth,
    };
  }, mapScope);
  const copy = language === "th"
    ? { short: "พื้นหลังแผนที่ไม่พร้อมใช้", full: "พื้นหลังแผนที่ไม่พร้อมใช้งาน ขอบเขตและหลักฐานการวางแผนยังแสดงอยู่", open: "ตัวเลือก", close: "ปิด", actions: ["ลองอีกครั้ง", "เปลี่ยนเป็น ดาวเทียม", "ซ่อนพื้นหลัง"] }
    : { short: "Map background unavailable", full: "The map background is unavailable. Planning boundaries and evidence remain visible.", open: "Options", close: "Close", actions: ["Retry", "Switch to Satellite", "Hide background"] };
  const folded = await measure();
  if (folded.expanded !== "false" || folded.text !== `${copy.short} ${copy.open}` || folded.buttons.join("|") !== copy.open || folded.lines !== 1 || folded.truncated) {
    throw new Error(`The phone map notice is not one line and one button at ${label} (${language}): ${JSON.stringify(folded)}`);
  }
  for (const required of ["list button", "search field", "map layers button", "zoom buttons", "locate button", "priority card", "hazard button"]) {
    if (!folded.found.includes(required)) throw new Error(`The notice check found no ${required} to compare with at ${label} (${language}).`);
  }
  if (folded.overlaps.length > 0 || !folded.insideMap || folded.scroll > 1) {
    throw new Error(`The phone map notice overlaps a map control or leaves the map at ${label} (${language}): ${JSON.stringify(folded)}`);
  }
  // The list button, which the long notice used to reach, takes the tap at its own centre.
  const listTakesTap = await page.locator(`${mapScope} .map-text-alternative > summary`).evaluate((summary) => {
    const box = summary.getBoundingClientRect();
    return [0.1, 0.5, 0.9].every((share) => summary.contains(document.elementFromPoint(box.left + box.width * share, box.top + box.height / 2)));
  });
  if (!listTakesTap) throw new Error(`The list button is covered at ${label} (${language}).`);

  await notice.getByRole("button", { name: copy.open, exact: true }).click();
  const opened = await measure();
  if (opened.expanded !== "true" || !opened.text.startsWith(copy.full) || opened.buttons.join("|") !== [copy.close, ...copy.actions].join("|") || !opened.onTop || opened.scroll > 1) {
    throw new Error(`The opened phone map notice lacks its sentence or its actions, or is covered, at ${label} (${language}): ${JSON.stringify(opened)}`);
  }
  await notice.getByRole("button", { name: copy.close, exact: true }).click();
  if (await notice.getAttribute("data-expanded") !== "false") throw new Error(`The phone map notice did not fold back at ${label} (${language}).`);
  return `${label} ${language}: ${folded.height} px`;
}

/** The actions behind the phone notice's button work, and the notice folds back to one line after each. */
async function assertPhoneMapNoticeActions(page, mapScope) {
  const notice = page.locator(`${mapScope} .map-basemap-notice`);
  const stateIs = (state) => page.waitForFunction(({ scope, expected }) => (
    document.querySelector(`${scope} .geo-map-shell`)?.getAttribute("data-basemap-state") === expected
  ), { scope: mapScope, expected: state });
  await notice.getByRole("button", { name: "Options", exact: true }).click();
  await notice.getByRole("button", { name: "Hide background", exact: true }).click();
  await stateIs("hidden");
  if (await notice.getAttribute("data-expanded") !== "false" || !(await notice.innerText()).includes("Map background hidden")
    || await notice.getByRole("button").count() !== 1) {
    throw new Error("The phone map notice did not fold back to one line after hiding the background.");
  }
  await notice.getByRole("button", { name: "Options", exact: true }).click();
  await notice.getByRole("button", { name: "Show background", exact: true }).click();
  await stateIs("unavailable");
  if (await notice.getAttribute("data-expanded") !== "false") throw new Error("The phone map notice stayed open after showing the background.");
}

async function assertPublicPlanningFallback(page, mapScope) {
  const indicator = await page.locator(".public-risk-indicator").innerText();
  for (const required of ["Historical planning priority", "2024", "Confidence: low", "Verify current conditions"]) {
    if (!indicator.includes(required)) throw new Error(`Public planning context is missing: ${required}.`);
  }
  if (/Low risk|High risk/.test(indicator)) {
    throw new Error("Public historical planning priority is still labelled as current risk.");
  }
  await page.locator("#public-area-search").fill("Mae Sai Hospital");
  await page.locator(".public-location-status").filter({ hasText: "Online address search is unavailable" }).waitFor({ state: "visible" });
  const list = page.locator(`${mapScope} .map-text-alternative`);
  await list.locator("summary").click();
  await list.locator(".map-area-results button").filter({ hasText: /^Mae Sai/ }).click();
  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "TH570901"
  ));
  await list.locator("summary").click();
  if (await page.locator("#public-area-search").inputValue() !== "") {
    throw new Error("Choosing a local planning area did not clear the failed online search.");
  }
}

async function exerciseBasemapSelector(page, scopeSelector, expectedState) {
  const menu = page.locator(`${scopeSelector} .map-basemap-menu`);
  if (await menu.count() && await menu.getAttribute("open") === null) {
    await menu.locator("summary").click();
  }
  const buttons = page.locator(
    `${scopeSelector} .map-basemap-switcher button[aria-pressed], ${scopeSelector} .map-basemap-menu button[aria-pressed]`,
  );
  if (await buttons.count() !== 3) {
    throw new Error(`${scopeSelector} must expose Street, Satellite, and Terrain map backgrounds.`);
  }
  const labels = await buttons.allTextContents();
  if (labels.map((label) => label.trim()).join("|") !== "Street|Satellite|Terrain") {
    throw new Error(`${scopeSelector} map backgrounds are mislabeled: ${labels.join(", ")}.`);
  }
  for (const [index, basemap] of ["street", "satellite", "terrain"].entries()) {
    await buttons.nth(index).click();
    await page.waitForFunction(
      ({ scope, expectedBasemap, state }) => {
        const element = document.querySelector(`${scope} .geo-map-shell`);
        return element?.getAttribute("data-basemap") === expectedBasemap
          && element?.getAttribute("data-basemap-state") === state;
      },
      { scope: scopeSelector, expectedBasemap: basemap, state: expectedState },
    );
    if (await buttons.nth(index).getAttribute("aria-pressed") !== "true") {
      throw new Error(`${scopeSelector} did not expose ${basemap} as the selected map background.`);
    }
    const audience = await page.locator(`${scopeSelector} .geo-map-shell`).getAttribute("data-map-audience");
    if (audience === "public") {
      if (await page.locator(`${scopeSelector} p.map-attribution`).count() !== 0) {
        throw new Error(`${scopeSelector} retains the removed full attribution paragraph.`);
      }
    } else {
      const attribution = await page.locator(`${scopeSelector} .map-attribution`).innerText();
      const expectedAttribution = basemap === "street"
        ? "OpenStreetMap contributors"
        : basemap === "satellite"
          ? "Esri World Imagery"
          : "OpenTopoMap";
      if (!attribution.includes(expectedAttribution)) {
        throw new Error(`${scopeSelector} ${basemap} background is missing ${expectedAttribution} attribution.`);
      }
    }
  }
  await buttons.first().click();
  await page.waitForFunction(
    ({ scope, state }) => {
      const element = document.querySelector(`${scope} .geo-map-shell`);
      return element?.getAttribute("data-basemap") === "street"
        && element?.getAttribute("data-basemap-state") === state;
    },
    { scope: scopeSelector, state: expectedState },
  );
}

async function assertMaeSaiMap(page, scopeSelector, {
  expectRoads,
  expectTextAlternative = true,
  expectBoundary = true,
}) {
  await page.waitForFunction(
    ({ scope, requireRoads, requireBoundary }) => {
      const shell = document.querySelector(`${scope} .geo-map-shell`);
      const audience = shell?.getAttribute("data-map-audience");
      const visibleFacilityCount = shell?.getAttribute("data-facility-feature-count");
      const facilityDatasetCount = shell?.getAttribute("data-facility-dataset-count");
      const clusterCount = document.querySelectorAll(`${scope} .facility-cluster-marker`).length;
      const rendererCount = document.querySelectorAll(`${scope} .leaflet-overlay-pane canvas, ${scope} .leaflet-overlay-pane path`).length;
      const roads = Number(shell?.getAttribute("data-road-feature-count") ?? 0);
      const facilitiesReady = audience === "public"
        ? facilityDatasetCount === "0" && visibleFacilityCount === "0" && clusterCount === 0
        : visibleFacilityCount === "42" && clusterCount > 0 && shell?.getAttribute("data-facility-presentation") === "clusters";
      return facilitiesReady
        && (!requireBoundary || rendererCount > 0)
        && (!requireRoads || roads >= 4_458);
    },
    { scope: scopeSelector, requireRoads: expectRoads, requireBoundary: expectBoundary },
  );
  const shell = page.locator(`${scopeSelector} .geo-map-shell`);
  const audience = await shell.getAttribute("data-map-audience");
  const expectedFacilityCount = audience === "public" ? "0" : "42";
  if (await shell.getAttribute("data-facility-dataset-count") !== expectedFacilityCount) {
    throw new Error(`${scopeSelector} did not retain its role-approved facility projection.`);
  }
  if (expectTextAlternative) {
    const alternativeText = await page.locator(`${scopeSelector} .map-text-alternative`).textContent();
    if (!alternativeText?.includes("Selected area") || !alternativeText.includes("Road network context") || !alternativeText.includes("Assumptions")) {
      throw new Error(`${scopeSelector} list view does not describe its selected area, roads, and access assumptions.`);
    }
  }
  const boundaryRendererCount = await page.locator(`${scopeSelector} .leaflet-overlay-pane canvas, ${scopeSelector} .leaflet-overlay-pane path`).count();
  if (expectBoundary && (boundaryRendererCount === 0 || !await shell.getAttribute("data-selected-area"))) {
    throw new Error(`${scopeSelector} did not render its highlighted AOI boundary overlay.`);
  }
  if (!expectBoundary && await shell.getAttribute("data-area-feature-count") !== "0") {
    throw new Error(`${scopeSelector} retained a Public administrative boundary layer.`);
  }
  if (audience === "public") {
    if (await page.locator(`${scopeSelector} .facility-type-marker, ${scopeSelector} .facility-cluster-marker`).count() !== 0) {
      throw new Error(`${scopeSelector} exposed unverified facilities on the public map.`);
    }
  } else if (await page.locator(`${scopeSelector} .facility-cluster-marker`).count() === 0) {
    throw new Error(`${scopeSelector} did not cluster staff facility records at regional zoom.`);
  }
  const roads = Number(await shell.getAttribute("data-road-feature-count"));
  if (expectRoads && roads < 4_458) {
    throw new Error(`${scopeSelector} did not retain the full Mae Sai road evidence layer.`);
  }
}

function requiredFinalCopy(routePath) {
  if (routePath === "/public-cases/") return ["understand the study cases", "non-operational", "candidate research evidence"];
  if (routePath === "/command/cases/") return ["compare before & after routes", "research prototype", "imposed scenarios", "not observed flood conditions or safe-route guidance"];
  if (routePath === "/command/archive/") return ["historical mae sai research archive", "planning intelligence", "source time", "confidence"];
  if (routePath === "/studio/archive/") return ["historical mae sai technical report", "separate evidence context", "technical verification", "observed-data validation", "operational authorization"];
  if (routePath === "/studio/candidate-report/") return ["evidence status and decision boundary", "candidate", "accepted fpps / action class"];
  if (routePath === "/studio/library/") return ["study-area evidence library", "non-operational", "candidate research evidence"];
  if (routePath === "/studio/brief/") return ["compare before & after routes", "research prototype", "imposed scenarios", "not observed flood conditions or safe-route guidance"];
  return routePath === "/"
    ? ["see the flood.", "understand what it changes.", "illustrat"]
    : routePath === "/public/"
      // The Public header now shows the FloodGuard logo image instead of a text
      // wordmark, so the brand is no longer body text here. The nav labels and
      // Hazard Info still prove the finished Public UI rendered.
      ? ["hazard info", "report", "shelter", "prepare", "sos", "candidate", "non-operational", "lower priority", "higher priority"]
      : routePath === "/command/"
        ? ["planning overview", "candidate", "accepted fpps and action class remain unavailable"]
        : routePath === "/studio/"
          ? ["every result has a context", "research studies", "planning evidence", "historical studies"]
          : ["validation & evidence report", "source time", "confidence", "technical verification", "observed-data validation", "operational authorization", "immutable evidence context"];
}

/**
 * Restoring the saved language re-renders the tree after hydration, so the
 * document language can already read `en` while the paint still shows Thai.
 * Let that settle before asserting, then assert for the precise failure text.
 */
async function waitForFinalVisibleCopy(page, routePath) {
  await page
    .waitForFunction(
      (phrases) => {
        const text = document.body.innerText.toLocaleLowerCase("en-US");
        return phrases.every((phrase) => text.includes(phrase));
      },
      requiredFinalCopy(routePath),
      { timeout: 10_000 },
    )
    .catch(() => {});
  assertFinalVisibleCopy(await page.locator("body").innerText(), routePath);
}

function assertFinalVisibleCopy(body, routePath) {
  const normalized = body.toLocaleLowerCase("en-US");
  const required = requiredFinalCopy(routePath);
  for (const phrase of required) {
    if (!normalized.includes(phrase)) {
      throw new Error(`${routePath} is missing polished final copy: ${phrase}.`);
    }
  }
  const forbidden = routePath === "/"
    ? /coming soon|under construction|work in progress|developer note|processing_scope|can_feed_decision_layer|official dispatch confirmed/iu
    // The study library at /studio/ keeps the strict list it had before the report pages moved below it. Those
    // pages say "candidate" and "non-operational" by design, so they have the shorter list.
    : routePath === "/studio/"
    ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|fixtures?|candidates?|synthetic|non[-_ ]?operational|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|processing_scope|can_feed_decision_layer/iu
    : routePath.startsWith("/studio/")
    ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula/iu
    : routePath === "/public/"
      ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|prototypes?|mocks?|samples?|illustrative|placeholders?|fixtures?|synthetic|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|coming soon|under construction|not ready|work in progress|developer note|no browser formula|processing_scope|can_feed_decision_layer/iu
      : /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|fixtures?|synthetic|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|processing_scope|can_feed_decision_layer/iu;
  const match = body.match(forbidden);
  if (match) {
    throw new Error(`${routePath} exposes forbidden internal copy: ${match[0]}.`);
  }
}
