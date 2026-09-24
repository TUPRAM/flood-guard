import { createHash, webcrypto } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { evidenceFixtures } from "./evidence-library.fixtures";
import { evidenceAssetUrl, fetchEvidencePackage, gaugeSegments, parseEvidenceCatalog, parseEvidencePackage, selectEvidencePackage, sourceClockCoordinate } from "./evidence-library";

afterEach(() => vi.unstubAllGlobals());

describe("static evidence library", () => {
  it("accepts its candidate contract and retains missing measurements", () => {
    const { catalog, evidence } = evidenceFixtures();
    expect(parseEvidenceCatalog(catalog)).toEqual(catalog);
    expect(parseEvidencePackage(evidence, catalog, catalog.packages[0]).assessment.fpps).toBeNull();
    expect(selectEvidencePackage(catalog, "test-aoi", "wrong-event")).toBeNull();
    expect(selectEvidencePackage(catalog, "wrong-aoi", "test-event")).toBeNull();
  });

  it.each(["https://other.example/data.json", "//other.example/data.json", "/api/data.json", "/evidence-library/../secrets.json", "/evidence-library/%2e%2e/a.json", "/evidence-library/a.json?next=x", "/evidence-library/a.json#x", "C:\\private.json", "/evidence-library//a.json"])("rejects non-static or escaping path %s", (path) => {
    expect(evidenceAssetUrl(path)).toBeNull();
  });

  it("rejects duplicate selection bindings and unknown source events", () => {
    const { catalog } = evidenceFixtures();
    catalog.packages.push({ ...catalog.packages[0], id: "another-package" });
    expect(() => parseEvidenceCatalog(catalog)).toThrow(/duplicate/i);
    catalog.packages.pop();
    catalog.aois[0].event_ids = ["unlisted-event"];
    expect(() => parseEvidenceCatalog(catalog)).toThrow();
  });

  it.each([
    { aoi_id: "different-aoi" }, { event_id: "different-event" }, { id: "different-package" },
    { package_version: "mixed-version" }, { official_warning: true }, { operational_status: "agency_operational" },
    { dataset_mode: "official_input" }, { report_url: "https://example.org/private.pdf" }, { input_hashes: { aoi_sha256: "f".repeat(64) } },
  ])("fails closed for mixed identity/version or promoted safety: %o", (change) => {
    const { catalog, evidence } = evidenceFixtures();
    expect(() => parseEvidencePackage({ ...evidence, ...change }, catalog, catalog.packages[0])).toThrow();
  });

  it("does not accept restricted geometry even if the package labels it available", () => {
    const { catalog, evidence } = evidenceFixtures();
    catalog.datasets[0].rights.public_derivatives = false;
    expect(() => parseEvidencePackage(evidence, catalog, catalog.packages[0])).toThrow(/clearance/);
    delete evidence.layers[0].data;
    evidence.layers[0].availability = "metadata_only";
    expect(parseEvidencePackage(evidence, catalog, catalog.packages[0]).layers[0].data).toBeUndefined();
  });

  it("accepts bound gzip database offers and rejects external or unhashed downloads", () => {
    const { catalog, evidence } = evidenceFixtures();
    evidence.downloads = [{ title: "Synthetic database", url: "/evidence-library/context.json.gz", sha256: "a".repeat(64) }];
    expect(parseEvidencePackage(evidence, catalog, catalog.packages[0]).downloads).toHaveLength(1);
    evidence.downloads[0].url = "https://example.org/data.json.gz";
    expect(() => parseEvidencePackage(evidence, catalog, catalog.packages[0])).toThrow(/download binding/);
    evidence.downloads[0].url = "/evidence-library/context.json.gz";
    evidence.downloads[0].sha256 = "not a checksum";
    expect(() => parseEvidencePackage(evidence, catalog, catalog.packages[0])).toThrow(/download binding/);
  });

  it("rejects scores and action classes being promoted from partial inputs", () => {
    const { catalog, evidence } = evidenceFixtures();
    expect(() => parseEvidencePackage({ ...evidence, assessment: { ...evidence.assessment, fpps: 80, action_class: "A" } }, catalog, catalog.packages[0])).toThrow(/assessment/);
    expect(() => parseEvidencePackage({ ...evidence, assessment: { ...evidence.assessment, bounds: { lower: 90, upper: 10 } } }, catalog, catalog.packages[0])).toThrow(/assessment/);
  });

  it("breaks hydrographs at null values and at absent ten-minute slots", () => {
    const points = [
      { time: "2025-11-20T00:00:00", value: 1 }, { time: "2025-11-20T00:10:00", value: 2 },
      { time: "2025-11-20T00:20:00", value: null }, { time: "2025-11-20T00:30:00", value: 4 },
      { time: "2025-11-20T01:30:00", value: 5 }, { time: "2025-11-20T01:40:00", value: 6 },
    ];
    expect(gaugeSegments(points).map((segment) => segment.map((point) => point.value))).toEqual([[1, 2], [4], [5, 6]]);
    expect(gaugeSegments([{ time: "2025-11-20T00:00:00", value: null }])).toEqual([]);
  });

  it("keeps naive source-clock ten-minute slots continuous across viewer DST changes", () => {
    const originalZone = process.env.TZ;
    try {
      for (const zone of ["America/New_York", "Europe/London", "Asia/Bangkok"]) {
        process.env.TZ = zone;
        for (const points of [
          ["2025-03-09T01:50:00", "2025-03-09T02:00:00", "2025-03-09T02:10:00", "2025-03-09T02:20:00"],
          ["2025-11-02T01:50:00", "2025-11-02T02:00:00", "2025-11-02T02:10:00", "2025-11-02T02:20:00"],
        ]) {
          const coordinates = points.map((time) => sourceClockCoordinate(time));
          expect(coordinates[1] - coordinates[0]).toBe(600000);
          expect(coordinates[2] - coordinates[1]).toBe(600000);
          expect(gaugeSegments(points.map((time, index) => ({ time, value: index })))).toHaveLength(1);
        }
      }
    } finally {
      if (originalZone === undefined) delete process.env.TZ;
      else process.env.TZ = originalZone;
    }
  });

  it("rejects impossible dates and offset timestamps without a confirmed series timezone", () => {
    expect(sourceClockCoordinate("2025-02-30T00:00:00")).toBeNaN();
    expect(sourceClockCoordinate("2025-11-20T24:00:00")).toBeNaN();
    expect(sourceClockCoordinate("2025-11-20T00:00:00+07:00")).toBeNaN();
    expect(sourceClockCoordinate("2025-11-20T00:00:00Z", "unconfirmed")).toBeNaN();
    expect(sourceClockCoordinate("2025-11-20T00:00:00+07:00", "Asia/Bangkok")).toBe(Date.parse("2025-11-19T17:00:00Z"));
    const { catalog, evidence } = evidenceFixtures();
    evidence.gauges = [{ id: "test", name: "Test", units: "m", timezone: null, limitations: [], points: [{ time: "2025-11-20T00:00:00Z", value: 1 }] }];
    expect(() => parseEvidencePackage(evidence, catalog, catalog.packages[0])).toThrow(/gauge observations/);
  });

  it("verifies package bytes before parsing and rejects a tampered package", async () => {
    const { catalog, evidence } = evidenceFixtures();
    const bytes = JSON.stringify(evidence);
    catalog.packages[0].sha256 = createHash("sha256").update(bytes).digest("hex");
    vi.stubGlobal("crypto", webcrypto);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(bytes))));
    expect((await fetchEvidencePackage(catalog, catalog.packages[0])).id).toBe(evidence.id);
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(new Response(`${bytes}\n`))));
    await expect(fetchEvidencePackage(catalog, catalog.packages[0])).rejects.toThrow(/checksum/);
  });
});
