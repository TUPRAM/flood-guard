import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const out = resolve(process.env.FLOODGUARD_PROFILE_OUT ?? resolve(process.cwd(), "out"));
const profilePath = resolve(out, "deployment-profile.json");
if (!existsSync(profilePath)) throw new Error("Public profile output is missing.");

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
  if (existsSync(filePath) && statSync(filePath).isDirectory()) filePath = resolve(filePath, "index.html");
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
if (!address || typeof address === "string") throw new Error("Public profile server did not bind.");
const baseUrl = `http://127.0.0.1:${address.port}`;
const approvedOrigins = new Set([
  new URL(baseUrl).origin,
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const geocoderOrigin = "https://geocode.arcgis.com";
const geocoderPath = "/arcgis/rest/services/World/GeocodeServer/findAddressCandidates";
const routingOrigin = "https://routing.openstreetmap.de";
const configuredApi = process.env.FLOODGUARD_API_URL ?? process.env.NEXT_PUBLIC_FLOODGUARD_API_URL;
if (configuredApi) approvedOrigins.add(new URL(configuredApi).origin);
const browser = await launchFloodGuardBrowser();

try {
  const context = await browser.newContext({
    serviceWorkers: "allow",
    geolocation: {
      latitude: 20.429799,
      longitude: 99.884366,
      accuracy: 12,
    },
    permissions: ["geolocation"],
  });
  const geocoderRequests = [];
  await context.route(`${geocoderOrigin}${geocoderPath}**`, async (route) => {
    const url = new URL(route.request().url());
    geocoderRequests.push(url.href);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        candidates: [
          {
            address: "117 หมู่ 10 ตำบลเวียงพางคำ อำเภอแม่สาย จังหวัดเชียงราย 57130",
            location: { x: 99.884365731796, y: 20.429799258909 },
            score: 100,
            attributes: { Addr_type: "PointAddress" },
          },
        ],
      }),
    });
  });
  // Walking-route directions are an approved online enhancement (see the
  // Shelter page). Mock a minimal valid OSRM foot response so the profile check
  // stays deterministic and makes no real network call.
  await context.route(`${routingOrigin}/**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "Ok",
        routes: [{
          distance: 800,
          duration: 640,
          geometry: {
            type: "LineString",
            coordinates: [[99.879205, 20.40842], [99.884365731796, 20.429799258909]],
          },
          legs: [{
            steps: [
              { maneuver: { type: "depart" }, name: "", distance: 800 },
              { maneuver: { type: "arrive" }, name: "", distance: 0 },
            ],
          }],
        }],
      }),
    });
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    const geolocation = navigator.geolocation;
    if (!geolocation) return;
    const original = geolocation.getCurrentPosition.bind(geolocation);
    try {
      geolocation.getCurrentPosition = (success, error, options) => {
        globalThis.__floodGuardGeolocationOptions = options;
        return original(success, error, options);
      };
    } catch {
      // Browser-level position assertions still run if the method is read-only.
    }
  });
  const pageErrors = [];
  const consoleErrors = [];
  const unexpectedRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.stack ?? error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === geocoderOrigin && url.pathname === geocoderPath) return;
    if (url.origin === routingOrigin) return;
    if (!approvedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
  });

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Use English" }).click();
  await page.waitForFunction(() => document.documentElement.lang === "en");
  await assertInitialPreciseLocation(page);
  await assertStreetAddressSearch(page, geocoderRequests);
  await assertCompactPublicShell(page);
  await exercisePublicPages(page);
  if (await page.locator('a[href^="/command"], a[href^="/studio"]').count()) {
    throw new Error("Public profile root exposes a staff-surface link.");
  }
  const commandResponse = await context.request.get(`${baseUrl}/command/`);
  const studioResponse = await context.request.get(`${baseUrl}/studio/`);
  if (commandResponse.status() !== 404 || studioResponse.status() !== 404) {
    throw new Error(`Public profile staff routes did not return 404: ${commandResponse.status()}, ${studioResponse.status()}`);
  }

  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  await page.waitForFunction(() => document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("saved app ready"));
  const cacheAudit = await page.evaluate(async () => {
    const keys = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    const urls = [];
    for (const key of keys) {
      const cache = await caches.open(key);
      urls.push(...(await cache.keys()).map((request) => new URL(request.url).pathname));
    }
    return { keys, urls };
  });
  if (cacheAudit.keys.length !== 1) throw new Error(`Public profile installed ${cacheAudit.keys.length} FloodGuard caches.`);
  for (const forbidden of [
    "/command/",
    "/studio/",
    "/offline-demo/bundle.json",
    "/offline-demo/mae-sai/bundle.json",
    "/offline-demo/mae-sai/roads.json",
    "/offline-demo/mae-sai/facilities.json",
    "/offline-demo/mae-sai/access-hotspots.json",
    "/proposal-evidence.json",
  ]) {
    if (cacheAudit.urls.includes(forbidden)) throw new Error(`Public offline cache contains ${forbidden}`);
  }
  for (const required of ["/", "/public/", "/offline-demo/mae-sai/public-bundle.json", "/offline-demo/mae-sai/public-areas.json"]) {
    if (!cacheAudit.urls.includes(required)) throw new Error(`Public offline cache omits ${required}`);
  }

  await context.setOffline(true);
  for (const path of ["/", "/public", "/public/", "/public/?source=offline-check"]) {
    await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
    await page.locator("main.public-page").waitFor({ state: "visible" });
    await assertCompactPublicShell(page);
    await exercisePublicPages(page);
  }
  let commandLoaded = true;
  try {
    await page.goto(`${baseUrl}/command/`, { waitUntil: "domcontentloaded", timeout: 5000 });
    commandLoaded = await page.locator("main.command-page").count() > 0;
  } catch {
    commandLoaded = false;
  }
  if (commandLoaded) throw new Error("Public profile recovered Command while offline.");
  if (unexpectedRequests.length) {
    throw new Error(`Public profile attempted unapproved requests: ${[...new Set(unexpectedRequests)].join(", ")}`);
  }
  if (pageErrors.length || consoleErrors.length) {
    throw new Error(`Public profile browser errors: ${[...new Set([...pageErrors, ...consoleErrors])].join(" | ")}`);
  }

  await context.close();
  console.log("public profile browser smoke: direct Public entry, five-page navigation, verified cache inventory, normalized offline navigation, and absent staff routes");
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose()));
}

async function assertCompactPublicShell(page) {
  if (await page.locator(".public-app-header").count() !== 1) {
    throw new Error("Public profile is missing the compact app header.");
  }
  if (await page.locator(".public-header-logo[aria-label='FloodGuard home']").count() !== 1) {
    throw new Error("Public profile is missing its FloodGuard home control.");
  }
  if (await page.locator(".public-greeting .public-greeting-name").count() !== 1) {
    throw new Error("Public profile is missing the household greeting.");
  }
  if (await page.locator(".public-brand-mark, .public-boundary-banner").count() !== 0) {
    throw new Error("Public profile retains the removed logo or historical banner.");
  }
  const visibleText = await page.locator("main.public-page").innerText();
  if (/Public preparedness|Historical preparedness information/iu.test(visibleText)) {
    throw new Error("Public profile retains removed header or historical-banner copy.");
  }
  const profileButton = page.getByRole("button", { name: "Open household profile" });
  await profileButton.click();
  await page.locator("#public-profile-drawer").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Close profile" }).click();
  if (await profileButton.getAttribute("aria-expanded") !== "false") {
    throw new Error("Public profile drawer did not return to its closed state.");
  }
}

async function exercisePublicPages(page) {
  const publicPages = [
    ["home", "#public-active-panel .leaflet-container"],
    ["report", "#public-active-panel .public-report-page"],
    ["shelter", "#public-active-panel .public-shelter-page, #public-active-panel .public-shelter-view"],
    ["prepare", "#public-active-panel #household-plan-builder"],
    ["sos", "#public-active-panel .public-sos-page, #public-active-panel .public-sos-view"],
  ];
  for (const [id, readySelector] of publicPages) {
    const button = page.locator(`#public-tab-${id}`);
    if (await button.count() !== 1) throw new Error(`Public navigation is missing ${id}.`);
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
    const visibleText = await page.locator("#public-active-panel").innerText();
    const forbidden = visibleText.match(
      /(?:^|[^\p{L}\p{N}])(?:demos?|prototypes?|mocks?|samples?|illustrative|placeholders?)(?=$|[^\p{L}\p{N}])|coming soon|under construction|not ready|work in progress/iu,
    );
    if (forbidden) throw new Error(`Public ${id} exposes development-state copy: ${forbidden[0]}.`);
  }
  for (const retired of ["map", "shelters", "data"]) {
    if (await page.locator(`#public-tab-${retired}`).count()) {
      throw new Error(`Public profile retains retired navigation: ${retired}.`);
    }
  }
}

async function assertInitialPreciseLocation(page) {
  // Home opens straight into address entry. The privacy guarantee is unchanged:
  // nothing may reach for the device position until the reader presses locate.
  const locateButton = page.locator(".public-locate-button");
  await locateButton.waitFor({ state: "visible" });
  if (await page.locator(".public-location-marker").count() !== 0) {
    throw new Error("Public Home placed a precise pin before the user granted location access.");
  }
  const beforeRequest = await page.evaluate(() => globalThis.__floodGuardGeolocationOptions ?? null);
  if (beforeRequest !== null) {
    throw new Error("Public Home requested geolocation before the explicit locate action.");
  }

  await locateButton.click();
  await page.waitForFunction(() => (
    document.querySelector(".public-home-page .geo-map-shell")
      ?.getAttribute("data-location-source") === "gps"
  ));
  await page.locator(".public-location-marker").waitFor({ state: "visible" });
  const audit = await page.evaluate(() => {
    const shell = document.querySelector(".public-home-page .geo-map-shell");
    const mapFrame = document.querySelector(".public-home-map > .geo-map-shell");
    const style = mapFrame ? getComputedStyle(mapFrame) : null;
    const storedValues = Object.keys(localStorage).map((key) => localStorage.getItem(key) ?? "");
    return {
      latitude: shell?.getAttribute("data-location-latitude"),
      longitude: shell?.getAttribute("data-location-longitude"),
      accuracy: shell?.getAttribute("data-location-accuracy"),
      areaFeatureCount: shell?.getAttribute("data-area-feature-count"),
      options: globalThis.__floodGuardGeolocationOptions ?? null,
      customAttributionCount: document.querySelectorAll(".public-home-page p.map-attribution").length,
      nativeAttributionVisible: Boolean(
        document.querySelector(".public-home-page .leaflet-control-attribution")?.getClientRects().length,
      ),
      borderWidth: style?.borderWidth,
      borderRadius: style?.borderRadius,
      leakedToStorage: storedValues.some((value) => (
        value.includes("20.429799") || value.includes("99.884366")
      )),
    };
  });
  if (
    Number(audit.latitude) !== 20.429799
    || Number(audit.longitude) !== 99.884366
    || Number(audit.accuracy) !== 12
  ) {
    throw new Error(`Public precise pin did not preserve the browser coordinates: ${JSON.stringify(audit)}.`);
  }
  if (
    audit.options?.enableHighAccuracy !== true
    || audit.options?.maximumAge !== 0
    || audit.options?.timeout !== 15_000
  ) {
    throw new Error(`Public precise location did not request the required options: ${JSON.stringify(audit.options)}.`);
  }
  if (
    audit.areaFeatureCount !== "8"
    || audit.customAttributionCount !== 0
    || !audit.nativeAttributionVisible
    || audit.borderWidth !== "0px"
    || audit.borderRadius !== "0px"
    || audit.leakedToStorage
  ) {
    throw new Error(`Public precise-location map contract failed: ${JSON.stringify(audit)}.`);
  }
}

async function assertStreetAddressSearch(page, geocoderRequests) {
  if (geocoderRequests.length !== 0) {
    throw new Error("Public Home requested address suggestions before the user typed an address.");
  }
  const input = page.locator("#public-area-search");
  await input.fill("117 หมู่ 10 แม่สาย เชียงราย");
  const suggestion = page.getByRole("option", {
    name: /117 หมู่ 10 ตำบลเวียงพางคำ อำเภอแม่สาย จังหวัดเชียงราย 57130/iu,
  });
  await suggestion.waitFor({ state: "visible" });
  if (geocoderRequests.length !== 1) {
    throw new Error(`Public Home made ${geocoderRequests.length} requests for one debounced address query.`);
  }
  const requestUrl = new URL(geocoderRequests[0]);
  if (
    requestUrl.searchParams.get("countryCode") !== "THA"
    || requestUrl.searchParams.get("searchExtent") !== "99.72,20.12,100.18,20.62"
    || requestUrl.searchParams.get("forStorage") !== "false"
    || requestUrl.searchParams.get("locationType") !== "rooftop"
  ) {
    throw new Error(`Public Home sent an unbounded address query: ${requestUrl.href}`);
  }
  await suggestion.click();
  await page.waitForFunction(() => (
    document.querySelector(".public-home-page .geo-map-shell")
      ?.getAttribute("data-location-source") === "address"
  ));
  const audit = await page.evaluate(() => {
    const shell = document.querySelector(".public-home-page .geo-map-shell");
    const storedValues = Object.keys(localStorage).map((key) => localStorage.getItem(key) ?? "");
    return {
      latitude: shell?.getAttribute("data-location-latitude"),
      longitude: shell?.getAttribute("data-location-longitude"),
      markerCount: document.querySelectorAll(".public-location-marker").length,
      inputValue: document.querySelector("#public-area-search")?.value,
      leakedToStorage: storedValues.some((value) => (
        value.includes("117 หมู่ 10")
        || value.includes("20.429799258909")
        || value.includes("99.884365731796")
      )),
    };
  });
  if (
    Number(audit.latitude) !== 20.429799258909
    || Number(audit.longitude) !== 99.884365731796
    || audit.markerCount !== 1
    || !audit.inputValue?.startsWith("117 หมู่ 10")
    || audit.leakedToStorage
  ) {
    throw new Error(`Public exact-address selection failed: ${JSON.stringify(audit)}.`);
  }
}
