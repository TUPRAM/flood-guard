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
const configuredApi = process.env.FLOODGUARD_API_URL ?? process.env.NEXT_PUBLIC_FLOODGUARD_API_URL;
if (configuredApi) approvedOrigins.add(new URL(configuredApi).origin);
const browser = await launchFloodGuardBrowser();

try {
  const context = await browser.newContext({ serviceWorkers: "allow" });
  const page = await context.newPage();
  const pageErrors = [];
  const consoleErrors = [];
  const unexpectedRequests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!approvedOrigins.has(url.origin)) unexpectedRequests.push(request.url());
  });

  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.locator("main.public-page").waitFor({ state: "visible" });
  await page.getByRole("button", { name: "Use English" }).click();
  await page.waitForFunction(() => document.documentElement.lang === "en");
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
  console.log("public profile browser smoke: direct Public entry, verified cache inventory, normalized offline navigation, and absent staff routes");
} finally {
  await browser.close();
  await new Promise((resolveClose, rejectClose) => server.close((error) => error ? rejectClose(error) : resolveClose()));
}
