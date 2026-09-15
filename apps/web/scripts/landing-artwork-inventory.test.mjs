import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { collectLandingArtwork, fallbackArtworkUrls, readLandingArtwork, sceneArtworkUrls } from "./landing-artwork-inventory.mjs";

const frame = "/landing/floodguard-v2/camera/approach.webp";
const flooded = "/landing/floodguard-v2/plates/w2.webp";
const scene = {
  cameraFrames: [{ src: frame, at: 0 }, { src: frame, at: 1 }],
  closeStates: { W0: frame, W1: flooded, W2: flooded },
};

test("scene inventory deduplicates repeated camera and physical-state sources", () => {
  assert.deepEqual(sceneArtworkUrls(scene), [frame, flooded]);
});

test("scene inventory rejects missing states, external URLs and escaped local paths", () => {
  for (const invalid of [undefined, "https://example.org/image.webp", "/landing/floodguard-v2/../private.webp", "/landing/floodguard-v2/image.webp?secret=yes", "/landing/floodguard-v2/file%2f..%2fprivate.webp"]) {
    const altered = { ...scene, closeStates: { ...scene.closeStates, W2: invalid } };
    assert.throws(() => sceneArtworkUrls(altered), /Invalid local landing/);
  }
});

test("combined inventory retains fallback variants, hashes actual bytes and records both asset sets", () => {
  const out = mkdtempSync(resolve(tmpdir(), "floodguard-artwork-inventory-"));
  try {
    const urls = [...fallbackArtworkUrls, frame, flooded];
    for (const url of urls) {
      const path = resolve(out, url.slice(1));
      mkdirSync(dirname(path), { recursive: true });
      writeFileSync(path, `fixture content for ${url}`);
    }
    const scenePath = resolve(out, "landing/floodguard-v2/scene-manifest.json");
    writeFileSync(scenePath, JSON.stringify(scene));
    const assets = collectLandingArtwork(out);
    assert.deepEqual(assets.map((asset) => asset.url), urls);
    assert.deepEqual(readLandingArtwork(out), assets);
    for (const directory of ["floodguard-v1", "floodguard-v2"]) {
      const manifest = JSON.parse(readFileSync(resolve(out, "landing", directory, "offline-artwork.json"), "utf8"));
      assert.deepEqual(manifest.assets, assets.filter((asset) => asset.url.startsWith(`/landing/${directory}/`)));
    }
    const oldFlood = assets.find((asset) => asset.url === flooded);
    writeFileSync(resolve(out, flooded.slice(1)), "revised rendered water");
    const updated = collectLandingArtwork(out).find((asset) => asset.url === flooded);
    assert.notEqual(updated.sha256, oldFlood.sha256);
    assert.equal(updated.sha256, createHash("sha256").update("revised rendered water").digest("hex"));
    assert.equal(updated.bytes, Buffer.byteLength("revised rendered water"));
  } finally {
    assert.ok(out.startsWith(resolve(tmpdir(), "floodguard-artwork-inventory-")));
    rmSync(out, { recursive: true, force: true });
  }
});
