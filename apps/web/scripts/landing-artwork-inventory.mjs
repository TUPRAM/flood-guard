import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { resolve, sep } from "node:path";

export const landingArtworkManifest = "/landing/offline-artwork.json";
export const fallbackArtworkUrls = [
  ...["resident", "planner"].flatMap((person) => [480, 800, 1374].map((width) => `characters/${person}-${width}.webp`)),
  "decor/botanical.svg", "decor/contours.svg",
].map((file) => `/landing/floodguard-v1/${file}`);

export function sceneArtworkUrls(manifest) {
  if (!Array.isArray(manifest.cameraFrames) || !manifest.cameraFrames.length) {
    throw new Error("The landing scene manifest has no camera frames.");
  }
  const sources = [
    ...manifest.cameraFrames.map((frame) => frame.src),
    ...["W0", "W1", "W2"].map((state) => manifest.closeStates?.[state]),
  ];
  for (const src of sources) {
    if (typeof src !== "string" || !src.startsWith("/landing/floodguard-v2/")
      || !/^\/[A-Za-z0-9._/-]+$/.test(src)
      || !/\.(webp|png|jpe?g|avif)$/i.test(src)
      || new URL(src, "https://floodguard.invalid").pathname !== src) {
      throw new Error(`Invalid local landing scene artwork source: ${String(src)}`);
    }
  }
  return [...new Set(sources)];
}

export function collectLandingArtwork(out) {
  const scene = JSON.parse(readFileSync(resolve(out, "landing/floodguard-v2/scene-manifest.json"), "utf8"));
  const versions = [
    { directory: "floodguard-v1", urls: fallbackArtworkUrls },
    { directory: "floodguard-v2", urls: sceneArtworkUrls(scene) },
  ];
  const combined = [];
  for (const { directory, urls } of versions) {
    const root = resolve(out, "landing", directory);
    const assets = urls.map((url) => {
      const path = resolve(out, url.slice(1));
      if (!path.startsWith(`${root}${sep}`) || !existsSync(path) || !statSync(path).isFile()) {
        throw new Error(`Missing approved landing artwork: ${url}`);
      }
      const body = readFileSync(path);
      return { url, sha256: createHash("sha256").update(body).digest("hex"), bytes: body.byteLength };
    });
    writeInventory(resolve(root, "offline-artwork.json"), assets);
    combined.push(...assets);
  }
  writeInventory(resolve(out, landingArtworkManifest.slice(1)), combined);
  return combined;
}

export function readLandingArtwork(out) {
  const manifest = JSON.parse(readFileSync(resolve(out, landingArtworkManifest.slice(1)), "utf8"));
  if (manifest.policy !== "optional_after_first_paint" || !Array.isArray(manifest.assets) || !manifest.assets.length) {
    throw new Error("Deferred landing artwork inventory is incomplete.");
  }
  const urls = new Set();
  for (const asset of manifest.assets) {
    if (typeof asset.url !== "string" || !asset.url.startsWith("/landing/") || urls.has(asset.url)
      || !/^[a-f0-9]{64}$/.test(asset.sha256) || !Number.isSafeInteger(asset.bytes) || asset.bytes <= 0) {
      throw new Error(`Invalid deferred landing artwork record: ${JSON.stringify(asset)}`);
    }
    urls.add(asset.url);
  }
  return manifest.assets;
}

function writeInventory(path, assets) {
  writeFileSync(path, `${JSON.stringify({ policy: "optional_after_first_paint", assets }, null, 2)}\n`, "utf8");
}
