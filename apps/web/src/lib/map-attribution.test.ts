import { describe, expect, it } from "vitest";

import type { LayerCatalogItem } from "@floodguard/contracts";

import { visibleLayerAttributions } from "./map-attribution";

describe("visibleLayerAttributions", () => {
  it("deduplicates visible source attribution and preserves the OSM copyright notice", () => {
    const layers = [
      layer("priority_areas", ["HDX COD-AB", "FloodGuard"]),
      layer("road_risk", ["OpenStreetMap contributors", "FloodGuard"], "OpenStreetMap Thailand via Geofabrik"),
      layer("facilities", ["© OpenStreetMap contributors", "Geofabrik"]),
      layer("hidden_layer", ["Must not be shown"]),
    ];

    expect(visibleLayerAttributions(
      layers,
      new Set(["priority_areas", "road_risk", "facilities"]),
      "command",
    )).toEqual([
      "HDX COD-AB",
      "FloodGuard",
      "© OpenStreetMap contributors",
      "Geofabrik",
    ]);
  });
});

function layer(layerId: string, attribution: string[], sourceName = "Test source"): LayerCatalogItem {
  return {
    schema_version: "1.0",
    dataset_mode: "candidate",
    operational_status: "non_operational",
    source_timestamp: "2024-09-15T23:16:01Z",
    generated_at: "2026-07-18T00:00:00Z",
    confidence_class: "low",
    source_name: sourceName,
    assumptions: ["Test fixture."],
    official_warning: false,
    data_version: "mae-sai-candidate-2024-09-15-v1",
    git_commit: "7e42882efb7cb7dc40b7c1cdd4c3fa960569b95f",
    evidence_context_id: "mae-sai:2024-09:test-v1",
    evidence_package_id: "test-package-v1",
    layer_id: layerId,
    title_th: "ชั้นข้อมูลทดสอบ",
    title_en: "Test layer",
    role_visibility: ["command"],
    format: "geojson",
    url: `/layers/${layerId}`,
    data_state: "ready",
    model_run_id: null,
    evidence_state: {
      evidence_type: "modelled",
      granularity: "area_summary",
      confidence_class: "low",
      confidence_reason: "Test evidence only.",
      permitted_use: "planning_only",
      required_gate: "qualified_real_event_evaluation",
      gate_state: "blocked",
    },
    source_components: [{
      source_component_id: "test-source",
      role: "test",
      source_name: sourceName,
      source_version: "v1",
      source_timestamp: "2024-09-15T23:16:01Z",
      last_checked_at: "2026-07-18T00:00:00Z",
      temporal_meaning: "observation_time",
      freshness: "historical",
      freshness_policy_version: "source-freshness-v1",
      freshness_as_of: "2026-07-18T00:00:00Z",
      attribution,
    }],
    attribution,
  };
}
