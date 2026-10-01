import { readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CASE_REPLAY_BUDGET_BYTES,
  CASE_REPLAY_ROUTE,
  caseReplayBytes,
  readCaseReplayAssets,
  timelineManifestAssets,
  timelineManifestUrl,
} from "../../scripts/case-replay-inventory.mjs";
import { MAE_SAI_TIMELINE_ROUTE } from "../components/mae-sai-flood-timeline";
import { manifestAssets, manifestDirectory, manifestRevision, TIMELINE_MANIFEST_URL } from "./flood-timeline";

const webRoot = resolve(import.meta.dirname, "../..");
const publicRoot = resolve(webRoot, "public");
const manifest: unknown = JSON.parse(readFileSync(resolve(publicRoot, TIMELINE_MANIFEST_URL.slice(1)), "utf8"));

describe("Mae Sai replay offline inventory", () => {
  it("reads the one manifest constant and derives the same assets as the page", () => {
    expect(timelineManifestUrl()).toBe(TIMELINE_MANIFEST_URL);
    expect(CASE_REPLAY_ROUTE).toBe(MAE_SAI_TIMELINE_ROUTE);
    expect(timelineManifestAssets(manifest)).toEqual(manifestAssets(manifest));
    const synthetic = { a: [{ href: "/x", sha256: "b".repeat(64), bytes: 3 }, { href: "/x", sha256: "c".repeat(64), bytes: 4 }], b: { href: "/y", sha256: "bad", bytes: 1 } };
    expect(timelineManifestAssets(synthetic)).toEqual(manifestAssets(synthetic));
  });

  it("hash-verifies the manifest and every file it lists, all inside its revision directory", () => {
    const { assets } = readCaseReplayAssets(publicRoot);
    expect(assets[0].url).toBe(TIMELINE_MANIFEST_URL);
    expect(assets.slice(1).map((asset) => asset.url)).toEqual(manifestAssets(manifest).map((asset) => asset.href));
    for (const asset of assets) expect(asset.url.startsWith(manifestDirectory(TIMELINE_MANIFEST_URL))).toBe(true);
    // The residents raster, the access node file (r2 on) and the VIIRS daily maps (r3 on) travel with the offline copy.
    const typed = manifest as { population?: { href: string }; access?: { nodes: { href: string } }; viirs_daily?: { days: { href: string }[] } };
    const urls = assets.map((asset) => asset.url);
    expect(urls).toContain(typed.population!.href);
    expect(urls).toContain(typed.access!.nodes.href);
    expect(urls.some((url) => url.endsWith(".bin"))).toBe(true);
    expect(typed.viirs_daily!.days.length).toBeGreaterThan(0);
    for (const day of typed.viirs_daily!.days) expect(urls).toContain(day.href);
  });

  it("ships one revision whose precache set stays within its 6.5 MB budget", () => {
    const { assets } = readCaseReplayAssets(publicRoot);
    expect(CASE_REPLAY_BUDGET_BYTES).toBe(6_500_000);
    const bytes = caseReplayBytes(assets);
    expect(bytes).toBeLessThanOrEqual(CASE_REPLAY_BUDGET_BYTES);
    // The set is the whole revision folder: the manifest plus every file it lists, and nothing else on disk.
    const directory = resolve(publicRoot, manifestDirectory(TIMELINE_MANIFEST_URL).slice(1));
    const onDisk = readdirSync(directory);
    expect(onDisk.sort()).toEqual(assets.map((asset) => asset.url.slice(asset.url.lastIndexOf("/") + 1)).sort());
    expect(onDisk.reduce((sum, name) => sum + statSync(resolve(directory, name)).size, 0)).toBe(bytes);
    expect(readdirSync(resolve(directory, ".."))).toEqual([manifestRevision()]);
    // The check fails one byte over the budget, and on a list with no measurable size.
    expect(caseReplayBytes(assets, bytes)).toBe(bytes);
    expect(() => caseReplayBytes(assets, bytes - 1)).toThrow(/over its \d+-byte budget/);
    expect(() => caseReplayBytes([])).toThrow(/no measurable size/);
    expect(() => caseReplayBytes([{ bytes: CASE_REPLAY_BUDGET_BYTES + 1 }])).toThrow(/6\.5 MB/);
  });

  it("keeps the replay data out of the blocking install and answers the page's cache request", () => {
    const worker = readFileSync(resolve(publicRoot, "sw.js"), "utf8");
    expect(worker).toContain("const OPTIONAL_CASE_REPLAY = []; /* __OPTIONAL_CASE_REPLAY__ */");
    expect(worker).toContain('"FLOODGUARD_CACHE_CASE_REPLAY"');
    expect(worker).toContain('"FLOODGUARD_CASE_REPLAY_STATUS"');
    const page = readFileSync(resolve(webRoot, "src/components/mae-sai-flood-timeline.tsx"), "utf8");
    expect(page).toContain('type: "FLOODGUARD_CACHE_CASE_REPLAY"');
    expect(page).toContain('"FLOODGUARD_CASE_REPLAY_STATUS"');
    // No revision directory is written anywhere but the manifest constant.
    for (const file of [
      "src/components/mae-sai-flood-timeline.tsx",
      "src/components/mae-sai-replay-export.tsx",
      "src/components/mae-sai-evacuation-panels.tsx",
      "src/components/mae-sai-observed-panels.tsx",
      "src/lib/flood-timeline-evacuation.ts",
      "src/lib/flood-timeline-link.ts",
      "src/lib/flood-timeline-copy.ts",
      "scripts/write-offline-assets.mjs",
      "scripts/offline-smoke.mjs",
      "scripts/browser-offline-smoke.mjs",
      "scripts/verify-study-assets.mjs",
      "scripts/profile-artifact-smoke.mjs",
      "scripts/study-browser-smoke.mjs",
    ]) {
      expect(readFileSync(resolve(webRoot, file), "utf8"), file).not.toMatch(/mae-sai-2024-timeline\/r\d/);
    }
  });
});
