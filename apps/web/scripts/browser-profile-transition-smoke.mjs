import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";

import { launchFloodGuardBrowser } from "./browser-launch.mjs";

const competitionOut = resolve(process.env.FLOODGUARD_COMPETITION_PROFILE_OUT ?? resolve(process.cwd(), "out"));
const publicOut = resolve(process.env.FLOODGUARD_PUBLIC_PROFILE_OUT ?? "");
if (!existsSync(resolve(competitionOut, "command", "index.html"))) throw new Error("Competition profile output is unavailable.");
if (!publicOut || !existsSync(resolve(publicOut, "deployment-profile.json"))) throw new Error("Public profile output is unavailable.");

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
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
const approvedOrigins = new Set([
  new URL(baseUrl).origin,
  "https://tile.openstreetmap.org",
  "https://services.arcgisonline.com",
  "https://a.tile.opentopomap.org",
]);
const browser = await launchFloodGuardBrowser();

try {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  const page = await context.newPage();
  const pageErrors = [];
  const unexpectedRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!approvedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
  });

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.surface-chooser").waitFor({ state: "visible" });
  await page.waitForFunction(() => Boolean(navigator.serviceWorker?.controller));
  await waitForEvaluated(page, async () => {
    const registration = await navigator.serviceWorker.getRegistration();
    return Boolean(registration?.active && !registration.installing && !registration.waiting);
  }, undefined, "initial competition worker to settle");
  const competitionCache = await page.evaluate(async () => {
    const key = (await caches.keys()).find((item) => /^floodguard-offline-[0-9a-f]{12}$/.test(item));
    if (!key) return null;
    const cache = await caches.open(key);
    return { key, paths: (await cache.keys()).map((request) => new URL(request.url).pathname) };
  });
  if (!competitionCache?.paths.includes("/command/")) throw new Error("Competition profile did not cache Command before transition.");

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
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Use English" }).click();
  await page.waitForFunction(() => document.documentElement.lang === "en");
  await page.locator(".public-location-consent-actions .secondary").click();
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
  for (const forbidden of ["/command/", "/studio/", "/offline-demo/mae-sai/roads.json", "/offline-demo/mae-sai/facilities.json"]) {
    if (publicCacheAudit.paths.includes(forbidden)) throw new Error(`Public cache retained ${forbidden} after transition.`);
  }
  await performSuccessfulUpdateCheck(page);
  await assertAvailabilityPanel(page, { online: true, ready: true });

  await context.setOffline(true);
  await page.waitForFunction(() => document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("Offline"));
  let commandRecovered = false;
  try {
    await page.goto(`${baseUrl}/command/`, { waitUntil: "domcontentloaded", timeout: 5000 });
    commandRecovered = await page.locator("main.command-page").count() > 0;
  } catch {
    commandRecovered = false;
  }
  if (commandRecovered) throw new Error("Command remained available offline after the public-profile downgrade.");

  // Reconnect the Public profile before switching the same origin back to the
  // broader competition build. This proves the online/offline indicator and
  // refresh check recover after a real failed navigation.
  await context.setOffline(false);
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.locator(".public-location-consent-actions .secondary").click();
  await assertAvailabilityPanel(page, { online: true, ready: true });

  // Public -> competition intentionally waits for user activation. Until the
  // waiting worker is installed, the old Public cache must not be described as
  // a complete saved competition app.
  activeOut = competitionOut;
  await requestRegistrationUpdate(page);
  await waitForEvaluated(
    page,
    async () => Boolean((await navigator.serviceWorker.getRegistration())?.waiting),
    undefined,
    "competition update to reach the waiting state",
  );
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.surface-chooser").waitFor({ state: "visible" });
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
  await page.getByRole("button", { name: "Install available update" }).click();
  await page.locator("main.surface-chooser").waitFor({ state: "visible" });
  await waitForEvaluated(page, async (oldKey) => {
    const keys = (await caches.keys()).filter((key) => /^floodguard-offline-[0-9a-f]{12}$/.test(key));
    if (keys.length !== 1 || keys[0] === oldKey) return false;
    const response = await caches.open(keys[0]).then((cache) => cache.match("/deployment-profile.json"));
    return response ? (await response.json()).profile === "competition" : false;
  }, publicCacheAudit.keys[0], "activated competition cache to replace the public cache");
  await assertAvailabilityPanel(page, { online: true, ready: true });

  // The activated competition worker must now serve both staff routes offline,
  // and the availability panel must report the cached snapshot and map limits.
  await context.setOffline(true);
  for (const [path, selector] of [["/command/", "main.command-page"], ["/studio/", "main.studio-page"]]) {
    await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
    await page.locator(selector).waitFor({ state: "visible" });
  }
  await assertAvailabilityPanel(page, { online: false, ready: true });
  const offlineRows = await readAvailabilityRows(page);
  if (offlineRows["Map backgrounds"] !== "May be unavailable offline") {
    throw new Error(`Offline map-background status is misleading: ${JSON.stringify(offlineRows)}`);
  }

  await context.setOffline(false);
  await page.waitForFunction(() => navigator.onLine && document.querySelector('[data-pwa-availability="true"]')?.textContent?.includes("Online"));
  await assertAvailabilityPanel(page, { online: true, ready: true });

  if (unexpectedRequests.length) {
    throw new Error(`Profile transition attempted unapproved requests: ${[...new Set(unexpectedRequests)].join(", ")}`);
  }
  if (pageErrors.length) throw new Error(`Profile transition browser errors: ${[...new Set(pageErrors)].join(" | ")}`);

  await context.close();
  console.log("profile transition smoke: competition -> Public downgrade, Public -> competition user update, offline staff readiness, and reconnect state passed");
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
        && text.includes(expectedReady ? "saved app ready" : "Open once online to save");
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
