import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve, sep } from "node:path";

/**
 * Offline inventory of the Mae Sai case replay (/studio/cases/mae-sai-2024/).
 *
 * The replay's data revision is chosen in exactly one place, `TIMELINE_MANIFEST_URL` in
 * src/lib/flood-timeline.ts. This module reads that constant and derives every file from the manifest it
 * names, so the build, the service worker and the checks never carry their own list of revision paths.
 *
 * Budget policy: the replay data (6.2 MB in revision r4: imagery, a HAND raster, vectors and the manifest) is
 * NOT part of the blocking service-worker installation. It is an opt-in bucket, like the landing artwork: the
 * replay page asks the worker to keep it after the replay has rendered online, and the worker stores each file
 * only when its SHA-256 matches this build's manifest. The street basemap stays online-only.
 *
 * One revision ships, and its precache set (the manifest plus every file it lists) must stay within
 * `CASE_REPLAY_BUDGET_BYTES`.
 *
 * The export pack (`exports.files` in the manifest: tables and one map layer to download) is a second list
 * with a budget of its own, `CASE_REPLAY_EXPORT_BUDGET_BYTES`. Its files are NOT in the precache set and do
 * not count against the 6.5 MB budget. The worker keeps them after the replay data, on the same request, so a
 * download link on a saved replay still answers without a connection; the page never loads them itself.
 */

export const CASE_REPLAY_ROUTE = "/studio/cases/mae-sai-2024/";
export const caseReplayInventory = "/offline-case-replay.json";
export const CASE_REPLAY_POLICY = "optional_after_replay_render";
/** Budget of the replay's precache set: 6.5 MB (decimal megabytes), manifest included. */
export const CASE_REPLAY_BUDGET_BYTES = 6_500_000;
/** Budget of the replay's export pack: 1.0 MB (decimal megabytes), counted apart from the precache set. */
export const CASE_REPLAY_EXPORT_BUDGET_BYTES = 1_000_000;
/** Manifest key of the export pack and the sub-folder of the revision that holds its files. */
export const CASE_REPLAY_EXPORT_KEY = "exports";
/**
 * Sub-folder of the revision that holds the season envelope's files (UNOSAT and GISTDA product 4009: a 1-bit raster,
 * a statistics file and the CC BY-SA 4.0 licence notice). The manifest lists them like any other asset, so they are
 * part of the precache set and of its 6.5 MB budget; the licence notice travels with the offline copy.
 */
export const CASE_REPLAY_ENVELOPE_FOLDER = "unosat4009";
const webRoot = resolve(import.meta.dirname, "..");
const SHA256 = /^[a-f0-9]{64}$/;
const SAFE_URL = /^\/[A-Za-z0-9._/-]+$/;
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");

/** The replay manifest URL, read from its single definition in src/lib/flood-timeline.ts. */
export function timelineManifestUrl(root = webRoot) {
  const source = readFileSync(resolve(root, "src/lib/flood-timeline.ts"), "utf8");
  const url = source.match(/^export const TIMELINE_MANIFEST_URL = "([^"]+)";$/m)?.[1];
  if (!url || !url.startsWith("/studies/") || !url.endsWith(".json") || !SAFE_URL.test(url) || url.includes("..")) {
    throw new Error("TIMELINE_MANIFEST_URL is missing or invalid in src/lib/flood-timeline.ts.");
  }
  return url;
}

/** Directory (with trailing slash) that must contain every file the manifest references. */
export function manifestDirectory(manifestUrl) {
  return manifestUrl.slice(0, manifestUrl.lastIndexOf("/") + 1);
}

function hashedAssets(value) {
  const found = new Map();
  const visit = (node) => {
    if (Array.isArray(node)) return node.forEach(visit);
    if (!node || typeof node !== "object") return;
    if (typeof node.href === "string" && typeof node.sha256 === "string" && SHA256.test(node.sha256)
      && typeof node.bytes === "number" && !found.has(node.href)) {
      found.set(node.href, { href: node.href, sha256: node.sha256, bytes: node.bytes });
    }
    Object.values(node).forEach(visit);
  };
  visit(value);
  return [...found.values()];
}

/**
 * Every hashed asset of the replay's precache set (`{ href, sha256, bytes }` anywhere in the manifest except
 * its top-level export pack), first occurrence per href.
 * Mirrors `manifestAssets` in src/lib/flood-timeline.ts, which a unit test keeps in step with this copy.
 */
export function timelineManifestAssets(manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) return hashedAssets(manifest);
  return hashedAssets(Object.fromEntries(Object.entries(manifest).filter(([key]) => key !== CASE_REPLAY_EXPORT_KEY)));
}

/**
 * The export pack's files (`exports.files` of the manifest), first occurrence per href; empty for a manifest
 * without a pack. Mirrors `manifestExportAssets` in src/lib/flood-timeline.ts.
 */
export function timelineExportAssets(manifest) {
  const pack = manifest && typeof manifest === "object" && !Array.isArray(manifest) ? manifest[CASE_REPLAY_EXPORT_KEY] : null;
  return pack && typeof pack === "object" ? hashedAssets(pack.files ?? []) : [];
}

function fileFor(root, url) {
  if (!SAFE_URL.test(url) || url.includes("..")) throw new Error(`Invalid replay asset path: ${url}`);
  const path = resolve(root, url.slice(1));
  if (!path.startsWith(`${resolve(root)}${sep}`)) throw new Error(`Replay asset escapes its root: ${url}`);
  return path;
}

function verified(root, asset, label) {
  const bytes = readFileSync(fileFor(root, asset.href));
  if (digest(bytes) !== asset.sha256 || bytes.byteLength !== asset.bytes) {
    throw new Error(`${label} checksum/length mismatch: ${asset.href}`);
  }
  return { url: asset.href, sha256: asset.sha256, bytes: asset.bytes };
}

/**
 * Hash-verified list of the manifest itself plus every asset of its precache set, read from `root`
 * (apps/web/public for the source tree, apps/web/out for a build). Throws when a file is missing, differs
 * from the manifest's hash or length, or lies outside the manifest's revision directory or inside its
 * export folder.
 */
export function readCaseReplayAssets(root, manifestUrl = timelineManifestUrl()) {
  const manifestBytes = readFileSync(fileFor(root, manifestUrl));
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const directory = manifestDirectory(manifestUrl);
  const assets = [{ url: manifestUrl, sha256: digest(manifestBytes), bytes: manifestBytes.byteLength }];
  for (const asset of timelineManifestAssets(manifest)) {
    if (!asset.href.startsWith(directory)) throw new Error(`Timeline asset outside its revision: ${asset.href}`);
    if (asset.href.startsWith(`${directory}${CASE_REPLAY_EXPORT_KEY}/`)) throw new Error(`Timeline asset inside the export folder: ${asset.href}`);
    assets.push(verified(root, asset, "Timeline asset"));
  }
  return { manifest, assets };
}

/**
 * Hash-verified list of the export pack's files, read from `root`. Every file must sit directly in the
 * revision's `exports/` folder and match the manifest's hash and length; a file listed twice or also listed
 * in the precache set is refused.
 */
export function readCaseReplayExports(root, manifestUrl = timelineManifestUrl()) {
  const manifest = JSON.parse(readFileSync(fileFor(root, manifestUrl), "utf8"));
  const folder = `${manifestDirectory(manifestUrl)}${CASE_REPLAY_EXPORT_KEY}/`;
  const listed = manifest?.[CASE_REPLAY_EXPORT_KEY]?.files ?? [];
  const precached = new Set(timelineManifestAssets(manifest).map((asset) => asset.href));
  const assets = timelineExportAssets(manifest);
  if (assets.length !== listed.length) throw new Error("An export file is listed twice or lacks its hash and size.");
  return assets.map((asset) => {
    if (!asset.href.startsWith(folder) || asset.href.slice(folder.length).includes("/")) throw new Error(`Export file outside the export folder: ${asset.href}`);
    if (precached.has(asset.href)) throw new Error(`Export file is also in the precache set: ${asset.href}`);
    return verified(root, asset, "Export file");
  });
}

/** Total size of a replay asset list; throws when it exceeds the precache budget. */
export function caseReplayBytes(assets, budget = CASE_REPLAY_BUDGET_BYTES) {
  const bytes = assets.reduce((sum, asset) => sum + asset.bytes, 0);
  if (!Number.isSafeInteger(bytes) || bytes <= 0) throw new Error("Case-replay precache set has no measurable size.");
  if (bytes > budget) {
    throw new Error(`Case-replay precache set is ${bytes} bytes, over its ${budget}-byte budget (${(budget / 1e6).toFixed(1)} MB).`);
  }
  return bytes;
}

/** Total size of the export pack (0 for no pack); throws when it exceeds the export budget. */
export function caseReplayExportBytes(assets, budget = CASE_REPLAY_EXPORT_BUDGET_BYTES) {
  const bytes = assets.reduce((sum, asset) => sum + asset.bytes, 0);
  if (!Number.isSafeInteger(bytes) || bytes < 0) throw new Error("Case-replay export pack has no measurable size.");
  if (bytes > budget) {
    throw new Error(`Case-replay export pack is ${bytes} bytes, over its ${budget}-byte budget (${(budget / 1e6).toFixed(1)} MB).`);
  }
  return bytes;
}

/**
 * Build step: verify the replay files in `out` and write the deferred inventory next to the other offline lists.
 * The inventory lists the precache set and, apart from it, the export pack with its own byte total and budget.
 * Returns the precache set; `readCaseReplayExports(out)` gives the export pack.
 */
export function collectCaseReplay(out) {
  const manifestUrl = timelineManifestUrl();
  const { assets } = readCaseReplayAssets(out, manifestUrl);
  const bytes = caseReplayBytes(assets);
  const exportAssets = readCaseReplayExports(out, manifestUrl);
  const exports = { budget_bytes: CASE_REPLAY_EXPORT_BUDGET_BYTES, bytes: caseReplayExportBytes(exportAssets), assets: exportAssets };
  writeFileSync(
    resolve(out, caseReplayInventory.slice(1)),
    `${JSON.stringify({ policy: CASE_REPLAY_POLICY, route: CASE_REPLAY_ROUTE, manifest: manifestUrl, budget_bytes: CASE_REPLAY_BUDGET_BYTES, bytes, assets, exports }, null, 2)}\n`,
    "utf8",
  );
  return assets;
}

/** Read and validate the inventory a build wrote. */
export function readCaseReplay(out) {
  const inventory = JSON.parse(readFileSync(resolve(out, caseReplayInventory.slice(1)), "utf8"));
  const manifestUrl = timelineManifestUrl();
  if (inventory.policy !== CASE_REPLAY_POLICY || inventory.route !== CASE_REPLAY_ROUTE || inventory.manifest !== manifestUrl
    || !Array.isArray(inventory.assets) || inventory.assets[0]?.url !== manifestUrl) {
    throw new Error("Deferred case-replay inventory is incomplete or names another manifest.");
  }
  const directory = manifestDirectory(manifestUrl);
  const exportFolder = `${directory}${CASE_REPLAY_EXPORT_KEY}/`;
  const urls = new Set();
  const check = (asset, inExportFolder) => {
    if (typeof asset.url !== "string" || !asset.url.startsWith(directory) || urls.has(asset.url)
      || asset.url.startsWith(exportFolder) !== inExportFolder
      || !SHA256.test(asset.sha256) || !Number.isSafeInteger(asset.bytes) || asset.bytes <= 0) {
      throw new Error(`Invalid case-replay inventory record: ${JSON.stringify(asset)}`);
    }
    urls.add(asset.url);
  };
  for (const asset of inventory.assets) check(asset, false);
  if (inventory.bytes !== caseReplayBytes(inventory.assets)) {
    throw new Error("Case-replay inventory byte total is inconsistent.");
  }
  const pack = inventory.exports;
  if (!pack || !Array.isArray(pack.assets) || pack.budget_bytes !== CASE_REPLAY_EXPORT_BUDGET_BYTES) {
    throw new Error("Deferred case-replay inventory lacks its export pack list.");
  }
  for (const asset of pack.assets) check(asset, true);
  if (pack.bytes !== caseReplayExportBytes(pack.assets)) {
    throw new Error("Case-replay export pack byte total is inconsistent.");
  }
  return inventory;
}
