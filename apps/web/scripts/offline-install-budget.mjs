import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";

/**
 * Budget of the blocking service-worker installation.
 *
 * The worker's install step stores `CORE_ASSETS` plus every script and style chunk listed in `/offline-assets.json`
 * with one `cache.addAll`: it is all or nothing, the "available offline" status waits for it, and every new
 * deployment downloads it again. So this list holds the application shell, the pages, small catalogues and indexes
 * and the case briefs only. Anything large is a deferred bucket, saved after a page asks for it: the landing artwork,
 * the Mae Sai replay's data and export pack, and each study area of the evidence library.
 *
 * The budget is 12 MB (decimal megabytes), counted as the size of the files as built. A build over it fails, and so
 * do the checks that read a built `out` directory.
 */
export const OFFLINE_INSTALL_BUDGET_BYTES = 12_000_000;

const SAFE_URL = /^\/[A-Za-z0-9._~/@-]*$/;

/** The built file a cached URL stands for: a route (trailing slash) is its `index.html`. */
export function installFile(out, url) {
  if (typeof url !== "string" || !SAFE_URL.test(url) || url.includes("..") || url.includes("//")) {
    throw new Error(`Invalid offline install URL: ${url}`);
  }
  const root = resolve(out);
  const path = url.endsWith("/") ? resolve(root, url.slice(1), "index.html") : resolve(root, url.slice(1));
  if (path !== root && !path.startsWith(`${root}${sep}`)) throw new Error(`Offline install URL escapes the build: ${url}`);
  if (!existsSync(path) || !statSync(path).isFile()) throw new Error(`Offline install file is missing: ${url}`);
  return path;
}

/**
 * Size of the blocking installation: `coreAssets` (the worker's `CORE_ASSETS`) plus `chunkAssets` (the generated
 * `/offline-assets.json`), each URL counted once. Throws when a file is missing or the total exceeds the budget.
 */
export function offlineInstallBytes(out, coreAssets, chunkAssets, budget = OFFLINE_INSTALL_BUDGET_BYTES) {
  const sizes = new Map();
  for (const url of [...coreAssets, ...chunkAssets]) {
    if (!sizes.has(url)) sizes.set(url, statSync(installFile(out, url)).size);
  }
  const total = (urls) => [...new Set(urls)].reduce((sum, url) => sum + sizes.get(url), 0);
  const bytes = [...sizes.values()].reduce((sum, size) => sum + size, 0);
  const largest = [...sizes].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([url, size]) => ({ url, bytes: size }));
  if (bytes > budget) {
    throw new Error(
      `The blocking offline installation is ${bytes} bytes (${megabytes(bytes)} MB), over its ${budget}-byte budget (${megabytes(budget)} MB). `
      + `Largest files: ${largest.map((item) => `${item.url} (${megabytes(item.bytes)} MB)`).join(", ")}. `
      + "Large data belongs in a bucket the reader saves on request, not in the installation.",
    );
  }
  return { files: sizes.size, bytes, core_bytes: total(coreAssets), chunk_bytes: total(chunkAssets.filter((url) => !coreAssets.includes(url))), budget_bytes: budget, largest };
}

/** The blocking list a finalized service worker carries (`CORE_ASSETS`). */
export function readWorkerCoreAssets(serviceWorker) {
  const declaration = serviceWorker.match(/const CORE_ASSETS = (\[[^;]*\]);/)?.[1];
  if (!declaration) throw new Error("The service worker has no CORE_ASSETS list.");
  const urls = JSON.parse(declaration);
  if (!Array.isArray(urls) || urls.some((url) => typeof url !== "string")) throw new Error("The service worker's CORE_ASSETS list is malformed.");
  return urls;
}

/** Measure the blocking installation of a built `out` directory against the budget; throws when it is over. */
export function verifyOfflineInstall(out, budget = OFFLINE_INSTALL_BUDGET_BYTES) {
  const coreAssets = readWorkerCoreAssets(readFileSync(resolve(out, "sw.js"), "utf8"));
  const chunkAssets = JSON.parse(readFileSync(resolve(out, "offline-assets.json"), "utf8"));
  if (!Array.isArray(chunkAssets)) throw new Error("The offline chunk list is malformed.");
  return { ...offlineInstallBytes(out, coreAssets, chunkAssets, budget), coreAssets, chunkAssets };
}

/** Decimal megabytes with one decimal, the unit of every offline budget in this project. */
export function megabytes(bytes) {
  return (bytes / 1e6).toFixed(1);
}
