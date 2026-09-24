import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, resolve } from "node:path";
import assert from "node:assert/strict";
import test from "node:test";
import { collectPublicCaseAssets } from "./public-case-assets.mjs";

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const bytes = (value) => Buffer.from(`${JSON.stringify(value)}\n`, "utf8");

function fixture() {
  const root = mkdtempSync(resolve(tmpdir(), "floodguard-public-asset-"));
  const caseId = "test_case_2024";
  mkdirSync(resolve(root, "evidence-library", "packages"), { recursive: true });
  mkdirSync(resolve(root, "public-case-projections", "cases"), { recursive: true });
  const sourcePackage = { id: caseId, aoi_id: "test_aoi", event_id: "test_event", generated_at: "2026-09-23T12:00:00Z",
    decision_brief: { finals_analysis: { generated_at: "2026-09-22T06:00:00Z" } } };
  const sourceBytes = bytes(sourcePackage);
  writeFileSync(resolve(root, "evidence-library", "packages", `${caseId}.json`), sourceBytes);
  const sourceCatalog = { package_version: "test-v1", packages: [{ id: caseId, aoi_id: "test_aoi", event_id: "test_event",
    url: `/evidence-library/packages/${caseId}.json`, sha256: sha256(sourceBytes) }] };
  const sourceCatalogBytes = bytes(sourceCatalog);
  writeFileSync(resolve(root, "evidence-library", "catalog.json"), sourceCatalogBytes);
  const projected = { schema_version: "floodguard.public_case.v1", package_version: "test-v1", id: caseId,
    aoi_id: "test_aoi", event_id: "test_event", source_package_sha256: sha256(sourceBytes),
    generated_at: sourcePackage.generated_at, source_analysis_generated_at: sourcePackage.decision_brief.finals_analysis.generated_at,
    dataset_mode: "candidate", operational_status: "non_operational", official_warning: false,
    fpps: null, action_class: null, affected_population: null, access: null,
    services: [{ id: "main_road", status: "unavailable", reason: "Not qualified", facilities: null, variants: [] }] };
  const casePath = resolve(root, "public-case-projections", "cases", `${caseId}.json`);
  writeFileSync(casePath, bytes(projected));
  const catalogPath = resolve(root, "public-case-projections", "catalog.json");
  const catalog = { schema_version: "floodguard.public_case_catalog.v1", package_version: "test-v1",
    source_catalog_sha256: sha256(sourceCatalogBytes), packages: [{ id: caseId, aoi_id: "test_aoi", event_id: "test_event",
      url: `/public-case-projections/cases/${caseId}.json`, sha256: sha256(readFileSync(casePath)),
      source_package_sha256: sha256(sourceBytes) }] };
  writeFileSync(catalogPath, bytes(catalog));
  return { root, projected, catalog, casePath, catalogPath };
}

test("competition asset collector binds candidate case, source hashes and separate clocks", () => {
  const item = fixture();
  try {
    assert.deepEqual(collectPublicCaseAssets(item.root), ["/public-case-projections/cases/test_case_2024.json", "/public-case-projections/catalog.json"]);
    item.projected.access = { modelled_population: 1 };
    writeFileSync(item.casePath, bytes(item.projected));
    item.catalog.packages[0].sha256 = sha256(readFileSync(item.casePath));
    writeFileSync(item.catalogPath, bytes(item.catalog));
    assert.throws(() => collectPublicCaseAssets(item.root), /Unsafe public case projection/);
    item.projected.access = null;
    item.projected.source_analysis_generated_at = "2026-09-22T06:00:00Z";
    item.projected.services[0].facilities = 0;
    writeFileSync(item.casePath, bytes(item.projected));
    item.catalog.packages[0].sha256 = sha256(readFileSync(item.casePath));
    writeFileSync(item.catalogPath, bytes(item.catalog));
    assert.throws(() => collectPublicCaseAssets(item.root), /Unqualified main-road access/);
    item.projected.services[0].facilities = null;
    item.projected.source_analysis_generated_at = item.projected.generated_at;
    writeFileSync(item.casePath, bytes(item.projected));
    item.catalog.packages[0].sha256 = sha256(readFileSync(item.casePath));
    writeFileSync(item.catalogPath, bytes(item.catalog));
    assert.throws(() => collectPublicCaseAssets(item.root), /Unsafe public case projection/);
  } finally {
    assert.equal(dirname(item.root), resolve(tmpdir()));
    assert.ok(basename(item.root).startsWith("floodguard-public-asset-"));
    rmSync(item.root, { recursive: true });
  }
});
