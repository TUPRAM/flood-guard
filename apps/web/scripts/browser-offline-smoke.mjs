import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.cwd(), "out");
if (!existsSync(resolve(out, "public", "index.html"))) {
  throw new Error("Build output is missing; run the production build first.");
}

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

const server = createServer((request, response) => {
  const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
  const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  let filePath = resolve(out, relativePath || "index.html");
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
  { path: "/", selector: "main.surface-chooser" },
  { path: "/public/", selector: "main.public-page" },
  { path: "/command/", selector: "main.command-page" },
  { path: "/studio/", selector: "main.studio-page" },
];
const approvedBasemapOrigins = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const approvedBasemapOriginsSeen = new Set();
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

  // Root: the platform entry must use the final blue product system, expose
  // all three role workspaces, and remain free of mobile overflow.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  const rootBody = await page.locator("body").innerText();
  assertFinalVisibleCopy(rootBody, "/");
  const rootAudit = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    language: document.querySelector("main.surface-chooser")?.getAttribute("lang"),
    links: [...document.querySelectorAll(".surface-grid a")].map((link) => link.getAttribute("href")),
    cards: document.querySelectorAll(".surface-card").length,
  }));
  if (rootAudit.documentWidth > rootAudit.viewportWidth + 1) {
    throw new Error(`Root chooser has mobile overflow: ${rootAudit.documentWidth}px > ${rootAudit.viewportWidth}px.`);
  }
  if (rootAudit.cards !== 3 || rootAudit.links.join("|") !== "/public/|/command/|/studio/") {
    throw new Error(`Root chooser workspaces are incomplete: ${JSON.stringify(rootAudit)}.`);
  }
  if (rootAudit.language !== "en") {
    throw new Error(`Root chooser does not declare its English content language: ${JSON.stringify(rootAudit)}.`);
  }

  // Public: the current-official-information action and household-plan action
  // must own the mobile first viewport. Emergency contacts follow the selected
  // area/context flow and must remain present and keyboard reachable.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/public/`, { waitUntil: "networkidle" });
  await page.locator('.language-toggle button[lang="en"]').click();
  const initialBody = await page.locator("body").innerText();
  assertFinalVisibleCopy(initialBody, "/public/");
  const primaryAction = page.locator('[data-action="build-household-plan"]');
  const officialUpdate = page.locator(".public-official-update");
  const officialUpdateLink = officialUpdate.locator('a[href*="disaster.go.th"]');
  const officialHelp = page.locator('[data-testid="public-official-help"]');
  const publicNavigation = page.locator(".public-bottom-nav");
  if (!(await primaryAction.isVisible()) || !(await officialUpdateLink.isVisible()) || !(await officialHelp.isVisible())) {
    throw new Error("Public Home is missing its household-plan action, official DDPM action, or emergency contacts.");
  }
  const [primaryActionBox, officialUpdateLinkBox, publicNavigationBox] = await Promise.all([
    primaryAction.boundingBox(),
    officialUpdateLink.boundingBox(),
    publicNavigation.boundingBox(),
  ]);
  if (!primaryActionBox || !publicNavigationBox || primaryActionBox.y + primaryActionBox.height > publicNavigationBox.y) {
    throw new Error("Build-my-household-plan action is not visible in the 390x844 first viewport.");
  }
  if (!officialUpdateLinkBox || !publicNavigationBox || officialUpdateLinkBox.y + officialUpdateLinkBox.height > publicNavigationBox.y) {
    throw new Error("Official DDPM action is not visible in the 390x844 first viewport.");
  }
  const hotlineLinks = officialHelp.locator('a[href^="tel:"]');
  if (await hotlineLinks.count() !== 3) throw new Error("Public Home does not expose all three official emergency contacts.");
  await officialHelp.scrollIntoViewIfNeeded();
  await hotlineLinks.first().focus();
  if (!await hotlineLinks.first().evaluate((link) => document.activeElement === link)) {
    throw new Error("Public emergency contacts are not keyboard reachable.");
  }
  const publicAreaSelect = page.locator("#public-area-select");
  if (await publicAreaSelect.inputValue() !== "") {
    throw new Error("A fresh Public session selected a planning area without user choice.");
  }
  await publicAreaSelect.selectOption("TH570901");
  await page.waitForFunction(() => document.querySelector("#public-area-select")?.value === "TH570901");
  await primaryAction.click();
  await page.locator("#household-plan-builder").waitFor({ state: "visible" });
  await page.locator(".household-need-options button").first().click();
  await page.locator(".checklist-grid input").first().check();
  const storedPlan = await page.evaluate(() => localStorage.getItem("floodguard:household-plan:v2"));
  if (!storedPlan || !storedPlan.includes('"children":true') || !storedPlan.includes('"official_contacts":true')) {
    throw new Error("The device-local household plan did not persist selected needs and checklist state.");
  }
  await page.reload({ waitUntil: "networkidle" });
  await page.locator("#public-tab-prepare").click();
  if (
    await page.locator(".household-need-options button").first().getAttribute("aria-pressed") !== "true"
    || !(await page.locator(".checklist-grid input").first().isChecked())
  ) {
    throw new Error("The household plan did not restore from device-local storage after reload.");
  }

  // Shared map: real Mae Sai boundaries and defensively approved public facilities must remain
  // usable when all approved basemap hosts are deliberately unavailable.
  await page.locator("#public-tab-map").click();
  await page.locator(".public-map-view .leaflet-container").waitFor({ state: "visible" });
  await page.locator(".map-selection-sheet.open").waitFor({ state: "visible" });
  await assertMaeSaiMap(page, ".public-map-view", { expectRoads: false });
  await exerciseBasemapSelector(page, ".public-map-view", "unavailable");
  await page.locator(".map-text-alternative summary").click();
  await page.locator(".map-text-alternative button").nth(1).click();
  if (await page.locator(".public-map-view .geo-map-shell").getAttribute("data-selected-area") !== "TH570902") {
    throw new Error("Map results list did not synchronize the selected reporting area.");
  }
  if (!(await page.locator(".map-selection-sheet").innerText()).includes("Huai Khrai")) {
    throw new Error("Selected-area bottom sheet did not update with map selection.");
  }

  // Command: the real-coordinate Mae Sai planning bundle renders at tablet
  // size with its evidence drawer and verification boundary visible.
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/command/`, { waitUntil: "networkidle" });
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
  if (!drawerBox || drawerBox.x < 0 || drawerBox.x + drawerBox.width > 1024 || drawerBox.y + drawerBox.height > 768) {
    throw new Error(`The tablet evidence drawer is clipped: ${JSON.stringify(drawerBox)}.`);
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
  await page.goto(`${baseUrl}/studio/`, { waitUntil: "networkidle" });
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
  assertFinalVisibleCopy(studioBody, "/studio/");
  await page.getByRole("tab", { name: "Models & evaluation" }).click();
  await page.locator("#model-registry-title").waitFor({ state: "visible" });
  const registryBody = await page.locator("#studio-tab-panel").innerText();
  for (const required of [
    "No model evaluation is bound to this evidence context",
    "External algorithmic baseline",
    "No real-event evaluation",
    "Report only",
    "not eligible for FPPS or the decision layer",
    "Remain unknown; never treated as dry",
    "Browser cryptographic status: not verified",
    "The API and repository are the authority for cryptographic verification.",
  ]) {
    if (!registryBody.includes(required)) {
      throw new Error(`Studio model registry is missing its fail-closed copy: ${required}.`);
    }
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
  assertFinalVisibleCopy(await page.locator("body").innerText(), "/public/");
  await page.goto(`${baseUrl}/command/`, { waitUntil: "networkidle" });
  if (await page.locator("html").getAttribute("lang") !== "en" || await page.locator('.language-toggle button[lang="en"]').getAttribute("aria-pressed") !== "true") {
    throw new Error("Language preference did not persist between product surfaces.");
  }
  if (await page.locator(".ranked-areas button").count() === 0) {
    throw new Error("Command route did not render its synchronized FPPS ranking.");
  }
  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  const cacheKeys = await page.evaluate(() => caches.keys());
  if (!cacheKeys.some((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key))) {
    throw new Error(`Content-versioned offline cache was not installed: ${cacheKeys.join(", ")}`);
  }

  offlineMode = true;
  await context.setOffline(true);
  for (const route of routes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
    await page.locator(route.selector).waitFor({ state: "visible" });
    const body = await page.locator("body").innerText();
    assertFinalVisibleCopy(body, route.path);
    if (route.path === "/public/") {
      await page.locator("#public-tab-map").click();
      await assertMaeSaiMap(page, ".public-map-view", { expectRoads: false });
    }
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
    `browser offline smoke: ${routes.length} routes rendered from a content-versioned service-worker cache; approved basemaps failed gracefully and no unapproved external requests occurred`,
  );
  console.log("legacy dashboard offline smoke: embedded Leaflet vectors, text equivalent, and dataset control verified");
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose());
  });
}

async function exerciseBasemapSelector(page, scopeSelector, expectedState) {
  const buttons = page.locator(`${scopeSelector} .map-basemap-switcher button`);
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

async function assertMaeSaiMap(page, scopeSelector, { expectRoads }) {
  await page.waitForFunction(
    ({ scope, requireRoads }) => {
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
        && rendererCount > 0
        && (!requireRoads || roads >= 4_458);
    },
    { scope: scopeSelector, requireRoads: expectRoads },
  );
  const shell = page.locator(`${scopeSelector} .geo-map-shell`);
  const audience = await shell.getAttribute("data-map-audience");
  const expectedFacilityCount = audience === "public" ? "0" : "42";
  if (await shell.getAttribute("data-facility-dataset-count") !== expectedFacilityCount) {
    throw new Error(`${scopeSelector} did not retain its role-approved facility projection.`);
  }
  const alternativeText = await page.locator(`${scopeSelector} .map-text-alternative`).textContent();
  if (!alternativeText?.includes("Selected area") || !alternativeText.includes("Road network context") || !alternativeText.includes("Assumptions")) {
    throw new Error(`${scopeSelector} list view does not describe its selected area, roads, and access assumptions.`);
  }
  const boundaryRendererCount = await page.locator(`${scopeSelector} .leaflet-overlay-pane canvas, ${scopeSelector} .leaflet-overlay-pane path`).count();
  if (boundaryRendererCount === 0 || !await shell.getAttribute("data-selected-area")) {
    throw new Error(`${scopeSelector} did not render its highlighted AOI boundary overlay.`);
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

function assertFinalVisibleCopy(body, routePath) {
  const normalized = body.toLocaleLowerCase("en-US");
  const required = routePath === "/"
    ? ["one platform. three planning views.", "continue by role", "ddpm", "local-authority"]
    : routePath === "/public/"
      ? ["mae sai flood context", "evidence date", "model confidence", "ddpm", "local authorities"]
      : routePath === "/command/"
        ? ["planning intelligence", "source time", "confidence", "ddpm", "local-authority"]
        : ["validation & evidence report", "source time", "confidence", "technical verification", "observed-data validation", "operational authorization", "immutable evidence context"];
  for (const phrase of required) {
    if (!normalized.includes(phrase)) {
      throw new Error(`${routePath} is missing polished final copy: ${phrase}.`);
    }
  }
  const forbidden = routePath === "/studio/"
    ? /(?:^|[^\p{L}\p{N}])(?:rehearsals?|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula/iu
    : /(?:^|[^\p{L}\p{N}])(?:rehearsals?|demos?|fixtures?|candidates?|synthetic|non[-_ ]?operational|fail[-_ ]?closed|server[-_ ]?produced)(?=$|[^\p{L}\p{N}])|developer note|no browser formula|processing_scope|can_feed_decision_layer/iu;
  const match = body.match(forbidden);
  if (match) {
    throw new Error(`${routePath} exposes forbidden internal copy: ${match[0]}.`);
  }
}
