import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";
import { readLandingArtwork } from "./landing-artwork-inventory.mjs";

const competitionOut = resolve(process.env.FLOODGUARD_COMPETITION_PROFILE_OUT ?? resolve(process.cwd(), "out"));
const publicOut = resolve(process.env.FLOODGUARD_PUBLIC_PROFILE_OUT ?? "");
if (!existsSync(resolve(competitionOut, "command", "index.html"))) throw new Error("Competition profile output is unavailable.");
if (!publicOut || !existsSync(resolve(publicOut, "deployment-profile.json"))) throw new Error("Public profile output is unavailable.");
const expectedArtworkUrls = readLandingArtwork(competitionOut).map((asset) => asset.url);

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
};
let activeOut = competitionOut;

const server = createServer((request, response) => {
  const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");
  const relativePath = decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  let filePath = resolve(activeOut, relativePath || "index.html");
  if (!filePath.startsWith(`${activeOut}${sep}`) && filePath !== activeOut) {
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
if (!address || typeof address === "string") throw new Error("Profile-transition server did not bind.");
const baseUrl = `http://127.0.0.1:${address.port}`;
const basemapOrigins = new Set([
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const approvedOrigins = new Set([baseUrl, ...basemapOrigins]);
const browser = await launchFloodGuardBrowser();
let page;
let phase = "initial competition page";
let offlineMode = false;
let expectedDeniedNavigation = false;
const pendingRequests = new Map();

try {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  // Cache isolation must not depend on the availability or traffic of external
  // map providers. Real tile loading and CSP are covered by csp-smoke.mjs.
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin === baseUrl) return route.continue();
    if (basemapOrigins.has(url.origin)) {
      return route.fulfill({
        status: 503,
        contentType: "text/plain",
        headers: { "Access-Control-Allow-Origin": "*" },
        body: "Map unavailable in the profile-isolation test",
      });
    }
    return route.abort("blockedbyclient");
  });
  page = await context.newPage();
  const pageErrors = [];
  const unexpectedRequests = [];
  const resourceErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    pendingRequests.set(request, request.url());
    if (!approvedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
  });
  page.on("requestfinished", (request) => pendingRequests.delete(request));
  page.on("requestfailed", (request) => {
    pendingRequests.delete(request);
    const reason = request.failure()?.errorText ?? "failed";
    if (reason === "net::ERR_ABORTED" || expectedResourceFailure(request.url())) return;
    resourceErrors.push(`${phase}: ${request.url()}: ${reason}`);
  });
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const url = message.location().url;
    if (url && expectedResourceFailure(url)) return;
    resourceErrors.push(`${phase}: ${url || "unknown resource"}: ${message.text()}`);
  });

  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await page.locator("main[data-fg-landing]").waitFor({ state: "visible" });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  await waitForEvaluated(page, async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return Boolean(registration?.active && !registration.installing && !registration.waiting);
  }, undefined, "initial competition worker to settle");
  await waitForEvaluated(page, async (expectedUrls) => {
    const key = (await caches.keys()).find((item) => /^floodguard-offline-[0-9a-f]{12}$/.test(item));
    if (!key) return false;
    const paths = (await (await caches.open(key)).keys()).map((request) => new URL(request.url).pathname);
    const artworkPaths = paths.filter((path) => path.startsWith("/landing/"));
    return artworkPaths.length === expectedUrls.length && expectedUrls.every((url) => artworkPaths.includes(url));
  }, expectedArtworkUrls, "deferred competition artwork to be cached before profile downgrade");
  const competitionCache = await page.evaluate(async () => {
    const key = (await caches.keys()).find((item) => /^floodguard-offline-[0-9a-f]{12}$/.test(item));
    if (!key) return null;
    const cache = await caches.open(key);
    return { key, paths: (await cache.keys()).map((request) => new URL(request.url).pathname) };
  });
  if (!competitionCache?.paths.includes("/command/")) throw new Error("Competition profile did not cache Command before transition.");

  phase = "competition to public downgrade";
  activeOut = publicOut;
  await requestRegistrationUpdate(page);
  await waitForEvaluated(page, async () => {
    const worker = navigator.serviceWorker.controller;
    if (!worker) return false;
    const status = await new Promise((resolveStatus) => {
      const channel = new MessageChannel();
      const timeout = window.setTimeout(() => resolveStatus(null), 500);
      channel.port1.onmessage = (event) => {
        window.clearTimeout(timeout);
        resolveStatus(event.data);
      };
      worker.postMessage({ type: "FLOODGUARD_STATUS_REQUEST" }, [channel.port2]);
    });
    return status?.profile === "public-production";
  }, undefined, "public worker to control the page");
  await waitForEvaluated(page, async (oldKey) => {
    const keys = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    if (keys.length !== 1 || keys[0] === oldKey) return false;
    const response = await caches.open(keys[0]).then((cache) => cache.match("/deployment-profile.json"));
    if (!response) return false;
    return (await response.json()).profile === "public-production";
  }, competitionCache.key, "public cache to replace the competition cache");
  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Use English" }).click();
  await page.waitForFunction(() => document.documentElement.lang === "en");
  await page.evaluate(async () => {
    const paths = ["/", "/public/", "/deployment-profile.json", "/offline-demo/mae-sai/public-bundle.json"];
    await Promise.all(Array.from({ length: 4 }, () => paths.map((path) => fetch(path))).flat());
  });

  const publicCacheAudit = await page.evaluate(async () => {
    const readWorker = (worker) => new Promise((resolveStatus) => {
      if (!worker) {
        resolveStatus(null);
        return;
      }
      const channel = new MessageChannel();
      const timeout = window.setTimeout(() => resolveStatus({ state: worker.state, status: "timeout" }), 500);
      channel.port1.onmessage = (event) => {
        window.clearTimeout(timeout);
        resolveStatus({ state: worker.state, ...event.data });
      };
      worker.postMessage({ type: "FLOODGUARD_STATUS_REQUEST" }, [channel.port2]);
    });
    const keys = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    const cache = await caches.open(keys[0]);
    const registration = await navigator.serviceWorker.getRegistration();
    const profiles = Object.fromEntries(await Promise.all(keys.map(async (key) => {
      const response = await caches.open(key).then((entry) => entry.match("/deployment-profile.json"));
      return [key, response ? (await response.json()).profile : "missing"];
    })));
    const workers = {
      controller: await readWorker(navigator.serviceWorker.controller),
      active: await readWorker(registration?.active),
      waiting: await readWorker(registration?.waiting),
      installing: await readWorker(registration?.installing),
    };
    return { keys, paths: (await cache.keys()).map((request) => new URL(request.url).pathname), profiles, workers };
  });
  if (publicCacheAudit.keys.includes(competitionCache.key)) {
    throw new Error(`Competition cache survived the public-profile transition: ${JSON.stringify(publicCacheAudit)}`);
  }
  if (publicCacheAudit.paths.some((path) => path.startsWith("/landing/"))) throw new Error("Public cache retained competition artwork after downgrade.");
  for (const forbidden of ["/command/", "/studio/", "/offline-demo/mae-sai/roads.json", "/offline-demo/mae-sai/facilities.json"]) {
    if (publicCacheAudit.paths.includes(forbidden)) throw new Error(`Public cache retained ${forbidden} after transition.`);
  }
  await performSuccessfulUpdateCheck(page);
  await assertAvailabilityPanel(page, { online: true, ready: true });

  phase = "public offline staff-route exclusion";
  offlineMode = true;
  await context.setOffline(true);
  await page.waitForFunction(() => document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("Offline"));
  let commandRecovered = false;
  expectedDeniedNavigation = true;
  try {
    await page.goto(`${baseUrl}/command/`, { waitUntil: "domcontentloaded", timeout: 5000 });
    commandRecovered = await page.locator("main.command-page").count() > 0;
  } catch {
    commandRecovered = false;
  } finally {
    expectedDeniedNavigation = false;
  }
  if (commandRecovered) throw new Error("Command remained available offline after the public-profile downgrade.");

  // Reconnect the Public profile before switching the same origin back to the
  // broader competition build. This proves the online/offline indicator and
  // refresh check recover after a real failed navigation.
  phase = "public reconnect after denied staff navigation";
  await context.setOffline(false);
  offlineMode = false;
  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await assertAvailabilityPanel(page, { online: true, ready: true });

  // Public -> competition intentionally waits for user activation. Until the
  // waiting worker is installed, the old Public cache must not be described as
  // a complete saved competition app.
  phase = "public to competition waiting update";
  activeOut = competitionOut;
  await requestRegistrationUpdate(page);
  await waitForEvaluated(
    page,
    async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting),
    undefined,
    "competition update to reach the waiting state",
  );
  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await page.locator("main[data-fg-landing]").waitFor({ state: "visible" });
  await page.locator('[data-pwa-availability="true"]').waitFor({ state: "hidden" });
  await page.goto(`${baseUrl}/public/`, { waitUntil: "domcontentloaded" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.waitForFunction(() => (
    document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("Install available update")
    && !document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("saved app ready")
  ));
  const pendingRows = await readAvailabilityRows(page);
  if (pendingRows["Saved planning view"] !== "Open once online to save") {
    throw new Error(`Profile mismatch was presented as offline-ready: ${JSON.stringify(pendingRows)}`);
  }

  const pendingPanel = page.locator('[data-pwa-availability="true"]');
  if (await pendingPanel.getAttribute("open") === null) await pendingPanel.locator("summary").click();
  phase = "activate competition update";
  await page.getByRole("button", { name: "Install available update" }).click();
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await waitForEvaluated(page, async (oldKey) => {
    const keys = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    if (keys.length !== 1 || keys[0] === oldKey) return false;
    const response = await caches.open(keys[0]).then((cache) => cache.match("/deployment-profile.json"));
    return response ? (await response.json()).profile === "competition" : false;
  }, publicCacheAudit.keys[0], "activated competition cache to replace the public cache");
  await assertAvailabilityPanel(page, { online: true, ready: true });

  // The activated competition worker must now serve both staff routes offline,
  // and the availability panel must report the cached snapshot and map limits.
  phase = "competition offline staff-route recovery";
  offlineMode = true;
  await context.setOffline(true);
  for (const [path, selector] of [["/command/", "main.command-page"], ["/studio/", "main.studio-page"]]) {
    await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
    await page.locator(selector).waitFor({ state: "visible" });
    await assertAvailabilityPanel(page, { online: false, ready: true });
    await page.waitForFunction((state) => (
      document.querySelector("[data-map-availability]")?.getAttribute("data-map-availability") === state
    ), path === "/command/" ? "offline" : "none");
    const rows = await readAvailabilityRows(page);
    const expectedBackground = path === "/command/" ? "Map background offline" : "No map background active";
    if (rows["Map backgrounds"] !== expectedBackground) {
      throw new Error(`${path} offline map-background status is misleading: ${JSON.stringify(rows)}`);
    }
  }

  phase = "competition reconnect";
  await context.setOffline(false);
  offlineMode = false;
  await page.waitForFunction(() => navigator.onLine && document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("Online"));
  await assertAvailabilityPanel(page, { online: true, ready: true });

  if (unexpectedRequests.length) {
    throw new Error(`Profile transition attempted unapproved requests: ${[...new Set(unexpectedRequests)].join(", ")}`);
  }
  if (pageErrors.length) throw new Error(`Profile transition browser errors: ${[...new Set(pageErrors)].join(" | ")}`);
  if (resourceErrors.length) throw new Error(`Profile transition resource errors: ${[...new Set(resourceErrors)].join(" | ")}`);

  await context.close();
  console.log("profile transition smoke: competition -> Public downgrade, Public -> competition user update, offline staff readiness, and reconnect state passed");
} catch (error) {
  const browserState = await page?.evaluate(async () => ({
    url: location.href,
    online: navigator.onLine,
    renderedSurface: document.querySelector("main")?.className,
    mapStates: [...document.querySelectorAll("[data-basemap-state]")].map((map) => map.getAttribute("data-basemap-state")),
    availability: document.querySelector('[data-pwa-availability="true"]')?.textContent,
    cacheKeys: (await caches.keys()).filter((key) => key.startsWith("floodguard-offline-")),
    workers: await Promise.all((await navigator.serviceWorker.getRegistrations()).map((registration) => ({
      active: registration.active?.state,
      waiting: registration.waiting?.state,
      installing: registration.installing?.state,
      controller: navigator.serviceWorker.controller?.state,
    }))),
  })).catch((diagnosticError) => ({ diagnosticError: diagnosticError.message }));
  console.error("profile transition diagnostics:", JSON.stringify({
    phase,
    servedProfile: activeOut === publicOut ? "public-production" : "competition",
    pendingRequests: [...new Set(pendingRequests.values())],
    browserState,
  }));
  throw error;
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose()));
}

async function assertAvailabilityPanel(page, { online, ready }) {
  const panel = page.locator('[data-pwa-availability="true"]');
  await panel.waitFor({ state: "visible" });
  await page.waitForFunction(
    ({ expectedOnline, expectedReady }) => {
      const text = document.querySelector('[data-pwa-availability="true"]')?.textContent ?? "";
      return text.includes(expectedOnline ? "Online" : "Offline")
        && text.includes(expectedReady ? "Available offline" : "Open once online to save");
    },
    { expectedOnline: online, expectedReady: ready },
  );
  if (await panel.getAttribute("open") === null) await panel.locator("summary").click();
  const rows = await readAvailabilityRows(page);
  for (const label of ["Saved planning view", "Household plan", "Flood context", "Cached planning snapshot", "Last successful update check", "Map backgrounds"]) {
    if (!rows[label]) throw new Error(`Availability panel omitted ${label}: ${JSON.stringify(rows)}`);
  }
  if (ready && (rows["Cached planning snapshot"] === "Not checked yet" || rows["Last successful update check"] === "Not checked yet")) {
    throw new Error(`Availability panel omitted saved-app timestamps: ${JSON.stringify(rows)}`);
  }
}

function expectedResourceFailure(resource) {
  const url = new URL(resource, baseUrl);
  return basemapOrigins.has(url.origin)
    || (offlineMode && url.origin === baseUrl && (
      (expectedDeniedNavigation && url.pathname === "/command/")
      || url.searchParams.has("_rsc")
      // The optional research report is outside the planning-view cache.
      || url.pathname === "/geoai/mae-sai-real.json"
    ));
}

async function readAvailabilityRows(page) {
  return page.locator('[data-pwa-availability="true"] dl').evaluate((list) => Object.fromEntries(
    [...list.querySelectorAll(":scope > div")].map((row) => [
      row.querySelector("dt")?.textContent?.trim() ?? "",
      row.querySelector("dd")?.textContent?.trim() ?? "",
    ]),
  ));
}

async function requestRegistrationUpdate(page) {
  await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    if (!registration) throw new Error("FloodGuard service-worker registration is unavailable.");
    await registration.update();
  });
}

async function performSuccessfulUpdateCheck(page) {
  const panel = page.locator('[data-pwa-availability="true"]');
  if (await panel.getAttribute("open") === null) await panel.locator("summary").click();
  await page.getByRole("button", { name: "Check for app update" }).click();
  await waitForEvaluated(page, () => {
    const panelElement = document.querySelector('[data-pwa-availability="true"]');
    const rows = panelElement?.querySelectorAll("dl > div") ?? [];
    const values = Object.fromEntries([...rows].map((row) => [
      row.querySelector("dt")?.textContent?.trim() ?? "",
      row.querySelector("dd")?.textContent?.trim() ?? "",
    ]));
    return values["Last successful update check"] !== undefined
      && values["Last successful update check"] !== "Not checked yet";
  }, undefined, "a successful saved-app update check timestamp");
}

async function waitForEvaluated(page, predicate, argument, description, timeoutMs = 30_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      if (await page.evaluate(predicate, argument)) return;
      lastError = null;
    } catch (error) {
      lastError = error;
    }
    await page.waitForTimeout(100);
  }
  const detail = lastError instanceof Error ? ` Last evaluation error: ${lastError.message}` : "";
  throw new Error(`Timed out waiting for ${description}.${detail}`);
}
