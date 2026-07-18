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
    layer_id: layerId,
    title_th: "ชั้นข้อมูลทดสอบ",
    title_en: "Test layer",
    role_visibility: ["command"],
    format: "geojson",
    url: `/layers/${layerId}`,
    data_state: "ready",
    model_run_id: null,
    attribution,
  };
}
