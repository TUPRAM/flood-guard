import { createReadStream, existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { chromium } from "@playwright/test";

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
const browser = await chromium.launch(
  process.env.FLOODGUARD_BROWSER_EXECUTABLE
    ? { executablePath: process.env.FLOODGUARD_BROWSER_EXECUTABLE, headless: true }
    : process.platform === "win32"
      ? { channel: "chrome", headless: true }
      : { headless: true },
);

const routes = [
  { path: "/public/", selector: "main.public-page" },
  { path: "/command/", selector: "main.command-page" },
  { path: "/studio/", selector: "main.studio-page" },
];
const externalRequests = [];
const pageErrors = [];
const consoleErrors = [];

try {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== baseUrl) {
      externalRequests.push(url.href);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  for (const route of routes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: "networkidle" });
    await page.locator(route.selector).waitFor({ state: "visible" });
  }

  // Public: the citizen action and official-help block must own the mobile
  // first viewport, and the household plan must persist only on this device.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/public/`, { waitUntil: "networkidle" });
  const initialBody = await page.locator("body").innerText();
  if (!initialBody.includes("Bundled offline fixture") && !initialBody.includes("ชุดข้อมูลสาธิตออฟไลน์")) {
    throw new Error("No-cache judging mode did not identify the bundled fixture honestly.");
  }
  const primaryAction = page.locator('[data-action="build-household-plan"]');
  const officialHelp = page.locator('[data-testid="public-official-help"]');
  if (!(await primaryAction.isVisible()) || !(await officialHelp.isVisible())) {
    throw new Error("Public first viewport is missing the household-plan action or official help.");
  }
  const [primaryActionBox, officialHelpBox] = await Promise.all([
    primaryAction.boundingBox(),
    officialHelp.boundingBox(),
  ]);
  if (!primaryActionBox || primaryActionBox.y + primaryActionBox.height > 844) {
    throw new Error("Build-my-household-plan action is not visible in the 390x844 first viewport.");
  }
  if (!officialHelpBox || officialHelpBox.y >= 844) {
    throw new Error("Official help does not begin in the 390x844 first viewport.");
  }
  await primaryAction.click();
  await page.locator("#household-plan-builder").waitFor({ state: "visible" });
  await page.locator(".household-need-options button").first().click();
  await page.locator(".checklist-grid input").first().check();
  const storedPlan = await page.evaluate(() => localStorage.getItem("floodguard:household-plan:v1"));
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

  // Shared map: selected-area sheet, synthetic context, and accessible text
  // selection must stay synchronized without requesting a live basemap.
  await page.locator("#public-tab-map").click();
  await page.locator(".public-map-view .leaflet-container").waitFor({ state: "visible" });
  await page.locator(".map-selection-sheet.open").waitFor({ state: "visible" });
  const contextLegend = await page.locator(".context-swatch").count();
  if (contextLegend !== 1) throw new Error("Public map is missing its synthetic geographic-context disclosure.");
  await page.locator(".map-text-alternative summary").click();
  await page.locator(".map-text-alternative button").first().click();
  if (await page.locator(".geo-map-shell").getAttribute("data-selected-area") !== "FG-TB-001") {
    throw new Error("Map text alternative did not synchronize the selected reporting area.");
  }
  if (!(await page.locator(".map-selection-sheet").innerText()).includes("FG-TB-001")
    && !(await page.locator(".map-selection-sheet").innerText()).includes("ตลาดริมน้ำ")) {
    throw new Error("Selected-area bottom sheet did not update with map selection.");
  }

  // Command: at tablet size the evidence drawer remains visible, while the
  // exact server-produced scenario artifact changes map tone and evidence.
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto(`${baseUrl}/command/`, { waitUntil: "networkidle" });
  await page.locator(".map-workspace .leaflet-container").waitFor({ state: "visible" });
  const evidenceDrawer = page.locator(".tablet-evidence-drawer");
  if (!(await evidenceDrawer.isVisible()) || await evidenceDrawer.locator(".tablet-evidence-body").isHidden()) {
    throw new Error("The 1024x768 command workspace does not keep its evidence drawer open.");
  }
  const drawerBox = await evidenceDrawer.boundingBox();
  if (!drawerBox || drawerBox.x < 0 || drawerBox.x + drawerBox.width > 1024 || drawerBox.y + drawerBox.height > 768) {
    throw new Error(`The tablet evidence drawer is clipped: ${JSON.stringify(drawerBox)}.`);
  }
  const scenarioSelect = page.locator('select[aria-label="Select scenario"]');
  await scenarioSelect.selectOption("add_temporary_shelter");
  await page.waitForFunction(() => (
    document.querySelector(".map-workspace .geo-map-shell")?.getAttribute("data-scenario-id") === "add_temporary_shelter"
    && document.querySelector(".decision-panel")?.getAttribute("data-scenario-tone") === "improves"
  ));
  if (await page.locator('.map-workspace path[fill="#0f8a7b"]').count() === 0) {
    throw new Error("Server-produced scenario delta did not visibly change the map presentation.");
  }
  const scenarioEvidence = await page.locator(".scenario-evidence-comparison").innerText();
  if (!scenarioEvidence.includes("-30") || !scenarioEvidence.includes("Server-produced access delta")) {
    throw new Error("Scenario evidence panel did not expose the exact server-produced delta.");
  }
  await page.locator(".ranked-areas button").filter({ hasText: "FG-TB-001" }).click();
  await page.waitForFunction(() => (
    document.querySelector(".geo-map-shell")?.getAttribute("data-selected-area") === "FG-TB-001"
    && document.querySelector(".tablet-evidence-drawer")?.textContent?.includes("FG-TB-001")
  ));

  // Studio: evidence scopes must remain visibly separate and selecting a run
  // must update the model card rather than a detached presentation copy.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${baseUrl}/studio/`, { waitUntil: "networkidle" });
  await page.locator(".geoai-proof").waitFor({ state: "visible" });
  try {
    await page.waitForFunction(() => {
      const body = document.body.innerText;
      const normalized = body.toLocaleLowerCase("en-US");
      return (normalized.includes("integration smoke") || body.includes("การทดสอบการเชื่อมต่อ"))
        && (normalized.includes("qualified real-data evaluation") || body.includes("การประเมินข้อมูลจริงที่ผ่านเกณฑ์"))
        && (normalized.includes("decision eligibility") || body.includes("สิทธิ์ส่งต่อชั้นการตัดสินใจ"));
    }, undefined, { timeout: 5_000 });
  } catch (error) {
    throw new Error(`Studio evidence scopes did not render: ${(await page.locator("body").innerText()).slice(0, 1800)}`, {
      cause: error,
    });
  }
  const studioBody = await page.locator("body").innerText();
  const normalizedStudioBody = studioBody.toLocaleLowerCase("en-US");
  for (const [english, thai] of [
    ["Integration smoke", "การทดสอบการเชื่อมต่อ"],
    ["Qualified real-data evaluation", "การประเมินข้อมูลจริงที่ผ่านเกณฑ์"],
    ["Decision eligibility", "สิทธิ์ส่งต่อชั้นการตัดสินใจ"],
  ]) {
    if (!normalizedStudioBody.includes(english.toLocaleLowerCase("en-US")) && !studioBody.includes(thai)) {
      throw new Error(`Studio is missing its ${english} evidence scope.`);
    }
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
  await page.evaluate(async () => {
    const [bundle, areaFeatures, roadFeatures, contextFeatures] = await Promise.all([
      fetch("/offline-demo/bundle.json").then((response) => response.json()),
      fetch("/offline-demo/areas.geojson").then((response) => response.json()),
      fetch("/offline-demo/roads.geojson").then((response) => response.json()),
      fetch("/offline-demo/context.geojson").then((response) => response.json()),
    ]);
    localStorage.setItem("floodguard:last-known-api-snapshot:v2", JSON.stringify({
      schema_version: "1.0",
      cached_at: new Date().toISOString(),
      data: {
        ...bundle,
        dataState: "ready",
        dataOrigin: "api",
        scenarioState: "ready",
        areaFeatures,
        roadFeatures,
        contextFeatures,
      },
    }));
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.locator('.language-toggle button[lang="en"]').click();
  if (await page.locator("html").getAttribute("lang") !== "en") {
    throw new Error("Language switch did not update the document language.");
  }
  if (await page.locator('.language-toggle button[lang="en"]').getAttribute("aria-pressed") !== "true") {
    throw new Error("Language switch did not expose its selected state.");
  }
  try {
    await page.waitForFunction(
      () => document.body.innerText.toLowerCase().includes("cached api snapshot (stale/offline)"),
      undefined,
      { timeout: 10_000 },
    );
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      body: document.body.innerText.slice(0, 800),
      snapshot: localStorage.getItem("floodguard:last-known-api-snapshot:v2")?.slice(0, 400),
    }));
    throw new Error(`Cached snapshot did not load: ${JSON.stringify(diagnostic)}`, {
      cause: error,
    });
  }
  const cachedBody = await page.locator("body").innerText();
  if (!cachedBody.toLowerCase().includes("stale / offline")) {
    throw new Error("Cached API snapshot did not expose its stale/offline state.");
  }
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

  await context.setOffline(true);
  for (const route of routes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
    await page.locator(route.selector).waitFor({ state: "visible" });
    const body = await page.locator("body").innerText();
    const normalizedBody = body.toLocaleLowerCase("en-US");
    if (!normalizedBody.includes("fixture demo") && !body.includes("ข้อมูลสาธิต")) {
      throw new Error(
        `${route.path} lost its fixture disclosure while offline: ${body.slice(0, 240)}`,
      );
    }
    if (!normalizedBody.includes("non-operational") && !body.includes("ไม่ใช่ระบบปฏิบัติการ")) {
      throw new Error(`${route.path} lost its non-operational disclosure while offline.`);
    }
    if (["/command/", "/studio/"].includes(route.path)) {
      if (!normalizedBody.includes("bounded agency pilot")) {
        throw new Error(`${route.path} lost its bounded agency-pilot readiness panel.`);
      }
      if (!normalizedBody.includes("not authorized for operation")) {
        throw new Error(`${route.path} falsely suggests agency operation while offline.`);
      }
    }
    if (route.path === "/studio/" && !normalizedBody.includes("synthetic integration proof")) {
      throw new Error("Studio lost its synthetic-proof limitation while offline.");
    }
  }

  if (externalRequests.length > 0) {
    throw new Error(`External requests were attempted: ${externalRequests.join(", ")}`);
  }
  if (pageErrors.length > 0 || consoleErrors.length > 0) {
    throw new Error(
      `Offline browser errors: ${[...pageErrors, ...consoleErrors].join(" | ")}`,
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
    `browser offline smoke: ${routes.length} routes rendered from a content-versioned service-worker cache; 0 external requests`,
  );
  console.log("legacy dashboard offline smoke: embedded Leaflet vectors, text equivalent, and dataset control verified");
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => {
    server.close((error) => error ? rejectClose(error) : resolveClose());
  });
}
