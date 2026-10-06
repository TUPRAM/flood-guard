import type { EvidenceLibraryCatalog, EvidenceLibraryPackage } from "@floodguard/contracts";

/** Synthetic, open test fixtures; never imported by the shipped evidence UI. */
export function evidenceFixtures(): { catalog: EvidenceLibraryCatalog; evidence: EvidenceLibraryPackage } {
  const catalog: EvidenceLibraryCatalog = {
    schema_version: "1.0", generated_at: "2026-09-21T00:00:00Z", package_version: "test-v1", non_operational: true,
    aois: [{ id: "test-aoi", name: "Synthetic test area", geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] }, event_ids: ["test-event"], sha256: "a".repeat(64) }],
    events: [{ id: "test-event", name: "Synthetic test event", start: "2024-09-01", end: "2024-09-30" }],
    datasets: [{ id: "test-data", title: "Synthetic test source", role: "scenario", source_urls: [], temporal: { start: null, end: null, kind: "synthetic", label: "Test-only assumptions" }, limitations: ["Not observed evidence."], rights: { status: "test_fixture", license: "Project-owned synthetic test fixture", public_derivatives: true, attribution: ["FloodGuard test fixture"] } }],
    packages: [{ id: "test-package", aoi_id: "test-aoi", event_id: "test-event", url: "/evidence-library/test-package.json", sha256: "b".repeat(64) }],
  };
  const evidence: EvidenceLibraryPackage = {
    schema_version: "1.0", package_version: "test-v1", id: "test-package", aoi_id: "test-aoi", event_id: "test-event", generated_at: "2026-09-21T00:00:00Z",
    input_hashes: { aoi_sha256: "a".repeat(64) }, dataset_mode: "candidate", official_warning: false, operational_status: "non_operational",
    source_timestamp: null, confidence_class: "low", assumptions: ["Synthetic test fixture only."],
    datasets: [{ dataset_id: "test-data", availability: "metadata_only", coverage: "Synthetic test AOI", qc: ["No observation claim."], summary: "Metadata fixture." }],
    layers: [{ id: "test-layer", title: "Synthetic geometry", role: "scenario", dataset_id: "test-data", availability: "available", reason: "Synthetic fixture", data: { type: "FeatureCollection", features: [] } }],
    gauges: [], assessment: { components: [{ id: "flood_likelihood", label: "Flood likelihood", weight: .3, value: null, reason: "No qualified flood extent." }], fpps: null, bounds: { lower: 0, upper: 100 }, action_class: null, limitations: ["No evidence acceptance."] },
    scenarios: [{ id: "test-scenario", title: "Explicit test assumption", kind: "synthetic", summary: "Scenario outcomes only.", assumptions: ["No road is asserted open."], metrics: [{ label: "Test demand", value: null, unit: "people" }] }],
    report_url: "/evidence-library/test-report.md",
  };
  return { catalog, evidence };
}
