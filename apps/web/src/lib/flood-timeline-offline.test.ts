import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  CASE_REPLAY_BUDGET_BYTES,
  CASE_REPLAY_EXPORT_BUDGET_BYTES,
  CASE_REPLAY_EXPORT_KEY,
  CASE_REPLAY_ROUTE,
  caseReplayBytes,
  caseReplayExportBytes,
  readCaseReplayAssets,
  readCaseReplayExports,
  timelineExportAssets,
  timelineManifestAssets,
  timelineManifestUrl,
} from "../../scripts/case-replay-inventory.mjs";
import { MAE_SAI_TIMELINE_ROUTE } from "../components/mae-sai-flood-timeline";
import { EXPORT_PACK_KEY, manifestAssets, manifestDirectory, manifestExportAssets, manifestRevision, TIMELINE_MANIFEST_URL } from "./flood-timeline";

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
    // The export pack is the manifest's top-level "exports" key on both sides; the two copies split it off the same way.
    expect(CASE_REPLAY_EXPORT_KEY).toBe(EXPORT_PACK_KEY);
    expect(timelineExportAssets(manifest)).toEqual(manifestExportAssets(manifest));
    const withPack = {
      layers: [{ href: "/x", sha256: "b".repeat(64), bytes: 3, exports: { href: "/nested", sha256: "d".repeat(64), bytes: 9 } }],
      exports: { files: [{ href: "/e/a.csv", sha256: "e".repeat(64), bytes: 5 }, { href: "/e/a.csv", sha256: "f".repeat(64), bytes: 6 }, { href: "/e/b.csv", sha256: "bad", bytes: 1 }],
        folder: { href: "/e/", sha256: "a".repeat(64), bytes: 1 } },
    };
    // Only the top-level pack is split off (a nested key of that name is ordinary content), and only its file list is the pack.
    expect(timelineManifestAssets(withPack).map((asset) => asset.href)).toEqual(["/x", "/nested"]);
    expect(timelineManifestAssets(withPack)).toEqual(manifestAssets(withPack));
    expect(timelineExportAssets(withPack)).toEqual([{ href: "/e/a.csv", sha256: "e".repeat(64), bytes: 5 }]);
    expect(timelineExportAssets(withPack)).toEqual(manifestExportAssets(withPack));
    for (const none of [synthetic, null, [], "text", { exports: null }, { exports: { files: null } }]) {
      expect(timelineExportAssets(none)).toEqual([]);
      expect(manifestExportAssets(none)).toEqual([]);
    }
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
    // The set is every file of the revision folder: the manifest plus every file it lists, and nothing else on disk.
    // The one sub-folder is the export pack, which is not in this set (see the next test).
    const directory = resolve(publicRoot, manifestDirectory(TIMELINE_MANIFEST_URL).slice(1));
    const entries = readdirSync(directory, { withFileTypes: true });
    expect(entries.filter((entry) => !entry.isFile()).map((entry) => entry.name)).toEqual([CASE_REPLAY_EXPORT_KEY]);
    const onDisk = entries.filter((entry) => entry.isFile()).map((entry) => entry.name);
    expect(onDisk.sort()).toEqual(assets.map((asset) => asset.url.slice(asset.url.lastIndexOf("/") + 1)).sort());
    expect(onDisk.reduce((sum, name) => sum + statSync(resolve(directory, name)).size, 0)).toBe(bytes);
    expect(readdirSync(resolve(directory, ".."))).toEqual([manifestRevision()]);
    // The check fails one byte over the budget, and on a list with no measurable size.
    expect(caseReplayBytes(assets, bytes)).toBe(bytes);
    expect(() => caseReplayBytes(assets, bytes - 1)).toThrow(/over its \d+-byte budget/);
    expect(() => caseReplayBytes([])).toThrow(/no measurable size/);
    expect(() => caseReplayBytes([{ bytes: CASE_REPLAY_BUDGET_BYTES + 1 }])).toThrow(/6\.5 MB/);
  });

  it("lists the export pack apart from the precache set, under a budget of its own", () => {
    const { assets } = readCaseReplayAssets(publicRoot);
    const exports = readCaseReplayExports(publicRoot);
    const folder = `${manifestDirectory(TIMELINE_MANIFEST_URL)}${CASE_REPLAY_EXPORT_KEY}/`;
    expect(exports.length).toBe(8);
    expect(exports.map((asset) => asset.url)).toEqual(manifestExportAssets(manifest).map((asset) => asset.href));
    for (const asset of exports) expect(asset.url.startsWith(folder)).toBe(true);
    // The pack is the whole export folder, and no file of it is in the replay's precache set.
    const directory = resolve(publicRoot, folder.slice(1));
    expect(readdirSync(directory).sort()).toEqual(exports.map((asset) => asset.url.slice(folder.length)).sort());
    expect(assets.filter((asset) => asset.url.startsWith(folder))).toEqual([]);
    // Its own budget line: 1.0 MB, counted apart from the 6.5 MB of the precache set.
    expect(CASE_REPLAY_EXPORT_BUDGET_BYTES).toBe(1_000_000);
    const bytes = caseReplayExportBytes(exports);
    expect(bytes).toBe(readdirSync(directory).reduce((sum, name) => sum + statSync(resolve(directory, name)).size, 0));
    expect(bytes).toBe((manifest as { exports: { bytes: number } }).exports.bytes);
    expect(bytes).toBeLessThanOrEqual(CASE_REPLAY_EXPORT_BUDGET_BYTES);
    expect(caseReplayExportBytes(exports, bytes)).toBe(bytes);
    expect(() => caseReplayExportBytes(exports, bytes - 1)).toThrow(/export pack is \d+ bytes, over its \d+-byte budget/);
    expect(() => caseReplayExportBytes([{ bytes: CASE_REPLAY_EXPORT_BUDGET_BYTES + 1 }])).toThrow(/1\.0 MB/);
    expect(caseReplayExportBytes([])).toBe(0);
    // The pack would not fit under the precache budget's remaining room by accident: the two totals are never added.
    expect(caseReplayBytes(assets)).toBe(assets.reduce((sum, asset) => sum + asset.bytes, 0));
  });

  it("refuses an export file that is changed, misplaced or also precached", () => {
    const root = mkdtempSync(join(tmpdir(), "floodguard-export-pack-"));
    try {
      const url = "/studies/case/r9/timeline.json";
      const sha = (body: string) => createHash("sha256").update(body).digest("hex");
      const write = (path: string, body: string) => {
        const target = resolve(root, path.slice(1));
        mkdirSync(resolve(target, ".."), { recursive: true });
        writeFileSync(target, body);
        return { href: path, sha256: sha(body), bytes: Buffer.byteLength(body) };
      };
      const layer = write("/studies/case/r9/hand.png", "raster");
      const table = write("/studies/case/r9/exports/modelled_road_inundation_by_hour.csv", "roads");
      const save = (document: unknown) => writeFileSync(resolve(root, url.slice(1)), JSON.stringify(document));
      save({ hand: layer, exports: { files: [table] } });
      expect(readCaseReplayExports(root, url)).toEqual([{ url: table.href, sha256: table.sha256, bytes: table.bytes }]);
      expect(readCaseReplayAssets(root, url).assets.map((asset) => asset.url)).toEqual([url, layer.href]);
      save({ hand: layer });
      expect(readCaseReplayExports(root, url)).toEqual([]);
      save({ hand: layer, exports: { files: [{ ...table, sha256: sha("other bytes") }] } });
      expect(() => readCaseReplayExports(root, url)).toThrow(/Export file checksum\/length mismatch/);
      save({ hand: layer, exports: { files: [write("/studies/case/r9/table.csv", "outside")] } });
      expect(() => readCaseReplayExports(root, url)).toThrow(/outside the export folder/);
      save({ hand: layer, exports: { files: [write("/studies/case/r9/exports/deep/table.csv", "nested")] } });
      expect(() => readCaseReplayExports(root, url)).toThrow(/outside the export folder/);
      save({ hand: layer, extra: table, exports: { files: [table] } });
      expect(() => readCaseReplayExports(root, url)).toThrow(/also in the precache set/);
      expect(() => readCaseReplayAssets(root, url)).toThrow(/inside the export folder/);
      save({ hand: layer, exports: { files: [table, table] } });
      expect(() => readCaseReplayExports(root, url)).toThrow(/listed twice/);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });

  it("keeps the replay data out of the blocking install and answers the page's cache request", () => {
    const worker = readFileSync(resolve(publicRoot, "sw.js"), "utf8");
    expect(worker).toContain("const OPTIONAL_CASE_REPLAY = []; /* __OPTIONAL_CASE_REPLAY__ */");
    // The export pack is a second deferred list, saved by the same request and reported apart from the replay data.
    expect(worker).toContain("const OPTIONAL_CASE_REPLAY_EXPORTS = []; /* __OPTIONAL_CASE_REPLAY_EXPORTS__ */");
    expect(worker).toContain("exports_cached: pack.cached, exports_failed: pack.failed, exports_total: pack.total");
    const build = readFileSync(resolve(webRoot, "scripts/write-offline-assets.mjs"), "utf8");
    expect(build).toContain('"const OPTIONAL_CASE_REPLAY_EXPORTS = []; /* __OPTIONAL_CASE_REPLAY_EXPORTS__ */"');
    expect(build).toContain("caseReplayExportBytes(optionalCaseReplayExports)");
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
