import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { assertBriefTimeBinding, renderCaseHtml, validateBriefCase } from "./build-case-briefs.mjs";

const publicRoot = resolve(import.meta.dirname, "..", "public");
const catalog = JSON.parse(readFileSync(resolve(publicRoot, "public-case-projections", "catalog.json"), "utf8"));
const readCase = (id) => {
  const reference = catalog.packages.find((item) => item.id === id);
  const projected = JSON.parse(readFileSync(resolve(publicRoot, reference.url.slice(1)), "utf8"));
  projected.access = null; // Synthetic next-projection fixture; generic legacy context is omitted.
  if (!projected.services.some((service) => service.id === "main_road")) projected.services.push({
    id: "main_road", status: "unavailable", reason: "Main-road access not qualified.", facilities: null, variants: [],
  });
  return { reference, projected, aoi: catalog.aois.find((item) => item.id === reference.aoi_id),
    event: catalog.events.find((item) => item.id === reference.event_id) };
};

test("mixed-time source and later release are displayed as separate bilingual facts", () => {
  const item = readCase("aoi-01_mae_sai_core_mae_sai_2024");
  item.projected.source_analysis_generated_at = "2026-09-22T06:00:00Z";
  item.projected.generated_at = "2026-09-23T12:00:00Z";
  validateBriefCase(item.projected, item.reference, catalog.package_version);
  const sourcePackage = { generated_at: item.projected.generated_at,
    decision_brief: { generated_at: item.projected.generated_at,
      finals_analysis: { generated_at: item.projected.source_analysis_generated_at } },
    input_hashes: { finals_receipt_sha256: "a".repeat(64), finals_generation_identity_sha256: "b".repeat(64) } };
  assert.doesNotThrow(() => assertBriefTimeBinding(item.projected, sourcePackage, item.reference.id));
  const html = renderCaseHtml(item, { catalog, catalogSha256: "f".repeat(64) });
  assert.match(html, /data-source-analysis-generated-at="2026-09-22T06:00:00Z"/);
  assert.match(html, /data-package-release-generated-at="2026-09-23T12:00:00Z"/);
  assert.match(html, /Source analysis generated \/ สร้างผลวิเคราะห์ต้นทาง: 2026-09-22T06:00:00Z/);
  assert.match(html, /Package release generated \/ สร้างแพ็กเกจเผยแพร่: 2026-09-23T12:00:00Z/);
  assert.match(html, /Main-road access has no separately qualified service result/);
  const hospitalWalking = item.projected.services.find((service) => service.id === "hospital")
    .variants.find((variant) => variant.travel_mode === "walking");
  assert.match(html, new RegExp(`${Math.round(hospitalWalking.within_30_minutes_population).toLocaleString("en-US")} residents are within 30 minutes`));
});

test("a missing source analysis stays unavailable and cannot inherit release time", () => {
  const item = readCase("aoi-02_mae_sai_district_mae_sai_2024");
  item.projected.source_analysis_generated_at = null;
  item.projected.generated_at = "2026-09-23T12:00:00Z";
  validateBriefCase(item.projected, item.reference, catalog.package_version);
  assert.doesNotThrow(() => assertBriefTimeBinding(item.projected, { generated_at: item.projected.generated_at,
    decision_brief: { generated_at: item.projected.generated_at } }, item.reference.id));
  const html = renderCaseHtml(item, { catalog, catalogSha256: "f".repeat(64) });
  assert.match(html, /data-source-analysis-generated-at="unavailable"/);
  assert.match(html, /Source analysis generated \/ สร้างผลวิเคราะห์ต้นทาง: Unavailable \/ ยังไม่มี/);
  assert.doesNotMatch(html, /source-analysis-generated-at="2026-09-23T12:00:00Z"/);
});

test("mixed-time output rejects future analysis, mismatched binding and missing receipts", () => {
  const item = readCase("aoi-01_mae_sai_core_mae_sai_2024");
  item.projected.source_analysis_generated_at = "2026-09-24T00:00:00Z";
  item.projected.generated_at = "2026-09-23T12:00:00Z";
  assert.throws(() => validateBriefCase(item.projected, item.reference, catalog.package_version), /exceeds package release/);
  item.projected.source_analysis_generated_at = "2026-09-22T06:00:00Z";
  item.projected.access = { modelled_population: 1, within_30_minutes_population: 1,
    connected_without_route_population: 0, unknown_access_population: 0 };
  assert.throws(() => validateBriefCase(item.projected, item.reference, catalog.package_version), /Generic mixed-basis access must be omitted/);
  item.projected.access = null;
  const mainRoad = { id: "main_road", status: "available", reason: "Unqualified", facilities: 0, variants: [] };
  assert.throws(() => validateBriefCase({ ...item.projected,
    services: item.projected.services.map((service) => service.id === "main_road" ? mainRoad : service) }, item.reference, catalog.package_version),
    /Unqualified main-road access cannot carry numeric results/);
  const sourcePackage = { generated_at: item.projected.generated_at,
    decision_brief: { generated_at: item.projected.generated_at, finals_analysis: { generated_at: item.projected.source_analysis_generated_at } },
    input_hashes: {} };
  assert.throws(() => assertBriefTimeBinding(item.projected, sourcePackage, item.reference.id), /lacks source identity receipts/);
  sourcePackage.input_hashes.finals_receipt_sha256 = "a".repeat(64);
  sourcePackage.input_hashes.finals_generation_identity_sha256 = "b".repeat(64);
  item.projected.source_analysis_generated_at = null;
  assert.throws(() => assertBriefTimeBinding(item.projected, sourcePackage, item.reference.id), /binding mismatch/);
});
