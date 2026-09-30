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
 * Budget policy: the replay data (about 5 MB of imagery, a HAND raster and vectors) is NOT part of the
 * blocking service-worker installation. It is an opt-in bucket, like the landing artwork: the replay page
 * asks the worker to keep it after the replay has rendered online, and the worker stores each file only
 * when its SHA-256 matches this build's manifest. The street basemap stays online-only.
 */

export const CASE_REPLAY_ROUTE = "/studio/cases/mae-sai-2024/";
export const caseReplayInventory = "/offline-case-replay.json";
export const CASE_REPLAY_POLICY = "optional_after_replay_render";
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

/**
 * Every hashed asset (`{ href, sha256, bytes }` anywhere in the manifest), first occurrence per href.
 * Mirrors `manifestAssets` in src/lib/flood-timeline.ts, which a unit test keeps in step with this copy.
 */
export function timelineManifestAssets(manifest) {
  const found = new Map();
  const visit = (value) => {
    if (Array.isArray(value)) return value.forEach(visit);
    if (!value || typeof value !== "object") return;
    if (typeof value.href === "string" && typeof value.sha256 === "string" && SHA256.test(value.sha256)
      && typeof value.bytes === "number" && !found.has(value.href)) {
      found.set(value.href, { href: value.href, sha256: value.sha256, bytes: value.bytes });
    }
    Object.values(value).forEach(visit);
  };
  visit(manifest);
  return [...found.values()];
}

function fileFor(root, url) {
  if (!SAFE_URL.test(url) || url.includes("..")) throw new Error(`Invalid replay asset path: ${url}`);
  const path = resolve(root, url.slice(1));
  if (!path.startsWith(`${resolve(root)}${sep}`)) throw new Error(`Replay asset escapes its root: ${url}`);
  return path;
}

/**
 * Hash-verified list of the manifest itself plus every asset it references, read from `root`
 * (apps/web/public for the source tree, apps/web/out for a build). Throws when a file is missing, differs
 * from the manifest's hash or length, or lies outside the manifest's revision directory.
 */
export function readCaseReplayAssets(root, manifestUrl = timelineManifestUrl()) {
  const manifestBytes = readFileSync(fileFor(root, manifestUrl));
  const manifest = JSON.parse(manifestBytes.toString("utf8"));
  const directory = manifestDirectory(manifestUrl);
  const assets = [{ url: manifestUrl, sha256: digest(manifestBytes), bytes: manifestBytes.byteLength }];
  for (const asset of timelineManifestAssets(manifest)) {
    if (!asset.href.startsWith(directory)) throw new Error(`Timeline asset outside its revision: ${asset.href}`);
    const bytes = readFileSync(fileFor(root, asset.href));
    if (digest(bytes) !== asset.sha256 || bytes.byteLength !== asset.bytes) {
      throw new Error(`Timeline asset checksum/length mismatch: ${asset.href}`);
    }
    assets.push({ url: asset.href, sha256: asset.sha256, bytes: asset.bytes });
  }
  return { manifest, assets };
}

/** Build step: verify the replay files in `out` and write the deferred inventory next to the other offline lists. */
export function collectCaseReplay(out) {
  const manifestUrl = timelineManifestUrl();
  const { assets } = readCaseReplayAssets(out, manifestUrl);
  const bytes = assets.reduce((sum, asset) => sum + asset.bytes, 0);
  writeFileSync(
    resolve(out, caseReplayInventory.slice(1)),
    `${JSON.stringify({ policy: CASE_REPLAY_POLICY, route: CASE_REPLAY_ROUTE, manifest: manifestUrl, bytes, assets }, null, 2)}\n`,
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
  const urls = new Set();
  for (const asset of inventory.assets) {
    if (typeof asset.url !== "string" || !asset.url.startsWith(manifestDirectory(manifestUrl)) || urls.has(asset.url)
      || !SHA256.test(asset.sha256) || !Number.isSafeInteger(asset.bytes) || asset.bytes <= 0) {
      throw new Error(`Invalid case-replay inventory record: ${JSON.stringify(asset)}`);
    }
    urls.add(asset.url);
  }
  if (inventory.bytes !== inventory.assets.reduce((sum, asset) => sum + asset.bytes, 0)) {
    throw new Error("Case-replay inventory byte total is inconsistent.");
  }
  return inventory;
}
