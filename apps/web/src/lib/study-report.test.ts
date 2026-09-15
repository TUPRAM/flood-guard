import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import {
  loadStudyMaeSai, loadStudyModelDetail, loadStudyRtc, loadStudySummary,
  loadStudyGeography, loadStudyJsonAsset,
  validateStudyAsset, validateStudyMaeSai, validateStudySummary,
} from "./study-report";

const publicRoot = fileURLToPath(new URL("../../public/", import.meta.url));
function source(href: string): string { return readFileSync(resolve(publicRoot, href.slice(1)), "utf8"); }
const summaryValue = () => JSON.parse(source("/studies/c2s-ms-20260915/r1/summary.json"));
function localFetch(): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => new Response(source(String(input)), {
    status: 200, headers: { "content-type": "application/json" },
  })) as unknown as typeof fetch;
}

describe("immutable public study reports", () => {
  it("loads the complete pinned study with reconciled dataset and role support", async () => {
    const summary = await loadStudySummary(localFetch());
    expect(summary.counts).toEqual({ chips: 900, events: 18, scenes: 36, files: 2700, download_bytes: 1514731043 });
    expect(summary.roles.map((r) => r.n_chips)).toEqual([443, 130, 98, 118, 111]);
    expect(summary.benchmarks).toHaveLength(7);
    expect(summary.benchmarks.filter((b) => b.arm === "context").every((b) => b.invalid_chips === 11 && b.supported_chips === 100)).toBe(true);
  });

  it("loads every model detail, both RTC arms and all six separate inference records", async () => {
    const fetcher = localFetch();
    const summary = await loadStudySummary(fetcher);
    for (const b of summary.benchmarks) {
      const detail = await loadStudyModelDetail(b.detail, fetcher);
      expect(detail.benchmark.source.sha256).toBe(b.source.sha256);
      expect(detail.benchmark.raw.full_valid).toEqual(b.raw.full_valid);
    }
    const rtc = await loadStudyRtc(summary.rtc, fetcher);
    expect(rtc.arms.every((a) => a.n_paired_test_chips === 46 && a.n_excluded_chips === 65)).toBe(true);
    const mae = await loadStudyMaeSai(summary.mae_sai, fetcher);
    expect(mae.records).toHaveLength(6);
    expect(mae.records.every((r) => r.valid_pixels === 2618380 && r.metrics === null)).toBe(true);
    expect(summary.geography).not.toBeNull();
    const geography = await loadStudyGeography(summary.geography!, fetcher);
    expect(Object.keys(geography.event_countries)).toHaveLength(18);
    expect(geography.features.length).toBeGreaterThan(100);
    expect(summary.visuals).not.toBeNull();
    const visuals = await loadStudyJsonAsset(summary.visuals!, fetcher);
    expect(visuals.chips).toHaveLength(111);
  });

  it("fails closed on unavailable, modified or truncated bytes without fallback", async () => {
    await expect(loadStudySummary(vi.fn(async () => new Response("", { status: 404 })))).rejects.toThrow("HTTP 404");
    const corrupt = vi.fn(async (input: RequestInfo | URL) => new Response(source(String(input)) + " "));
    await expect(loadStudySummary(corrupt)).rejects.toThrow("SHA-256 mismatch");
    const summary = await loadStudySummary(localFetch());
    const truncate = vi.fn(async (input: RequestInfo | URL) => new Response(
      String(input).endsWith("manifest.json") ? source(String(input)) : source(String(input)).slice(1),
    ));
    await expect(loadStudyModelDetail(summary.benchmarks[0].detail, truncate)).rejects.toThrow("byte count mismatch");
  });

  it("rejects foreign-study assets and mismatched declared hashes", async () => {
    const summary = await loadStudySummary(localFetch());
    expect(() => validateStudyAsset({ ...summary.rtc, href: "/studies/another/r1/rtc.json" })).toThrow();
    expect(() => validateStudyAsset({ ...summary.rtc, href: "/studies/c2s-ms-20260915/r1/../rtc.json" })).toThrow();
    await expect(loadStudyRtc({ ...summary.rtc, sha256: "a".repeat(64) }, localFetch())).rejects.toThrow("pinned release");
  });

  it.each(["official_warning", "can_feed_decision_layer"])("rejects accidental promotion through %s", (flag) => {
    const data = summaryValue(); data[flag] = true;
    expect(() => validateStudySummary(data)).toThrow("scope mismatch");
  });

  it("rejects invalid confusion counts, role overlap and private source paths", () => {
    const counts = summaryValue(); counts.benchmarks[0].raw.full_valid.true_positive += 1;
    expect(() => validateStudySummary(counts)).toThrow("Confusion");
    const roles = summaryValue(); roles.roles[0].event_ids.push(roles.roles[4].event_ids[0]);
    expect(() => validateStudySummary(roles)).toThrow("Role membership");
    const paths = summaryValue(); paths.provenance[0].source_path = "C:/Users/private/file.json";
    expect(() => validateStudySummary(paths)).toThrow("Private paths");
  });

  it("retains calibration regressions, incomplete support and unavailable Thai accuracy", () => {
    const summary = validateStudySummary(summaryValue());
    const unet = summary.benchmarks.find((b) => b.id === "sar/unet")!;
    const otsu = summary.benchmarks.find((b) => b.id === "sar/vh_otsu")!;
    expect(unet.raw.full_valid.iou).toBeLessThan(otsu.raw.full_valid.iou!);
    const mae = JSON.parse(source(summary.mae_sai.href)); mae.metrics = { iou: 0.99 };
    expect(() => validateStudyMaeSai(mae)).toThrow("no independent accuracy");
  });
});
