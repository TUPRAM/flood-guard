import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import accessJson from "../../public/offline-demo/mae-sai/access-hotspots.json";
import areasJson from "../../public/offline-demo/mae-sai/areas.json";
import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import facilitiesJson from "../../public/offline-demo/mae-sai/facilities.json";
import manifestJson from "../../public/offline-demo/mae-sai/manifest.json";
import roadsJson from "../../public/offline-demo/mae-sai/roads.json";

describe("Mae Sai offline command bundle", () => {
  it("contains the complete real-coordinate candidate context and stays non-operational", () => {
    expect(bundleJson.status).toMatchObject({
      study_area: "mae_sai_candidate_v1",
      dataset_mode: "candidate",
      operational_status: "non_operational",
      official_warning: false,
    });
    expect(bundleJson.areas).toHaveLength(8);
    expect(areasJson.features).toHaveLength(8);
    expect(areasJson.features.every((feature) => feature.geometry.type === "MultiPolygon")).toBe(true);
    expect(roadsJson.features).toHaveLength(4_458);
    expect(facilitiesJson.features).toHaveLength(42);
    expect(accessJson.features).toHaveLength(8);
    expect(bundleJson.areas.every((area) => area.official_warning === false && area.operational_status === "non_operational")).toBe(true);
  });

  it("never promotes an open-context facility or candidate road to observed truth", () => {
    const areaIds = new Set(bundleJson.areas.map((area) => area.area_id));
    expect(facilitiesJson.features.every((feature) => (
      areaIds.has(feature.properties.area_id)
      && feature.properties.verification_status === "open_context_candidate"
      && feature.properties.emergency_role === "no_confirmed_emergency_role"
      && feature.properties.candidate_status === "unverified_osm_candidate"
      && feature.properties.warning_text.includes("unverified")
    ))).toBe(true);
    expect(roadsJson.features.every((feature) => (
      areaIds.has(feature.properties.area_id)
      && feature.properties.warning_text.includes("Not an observed closure")
    ))).toBe(true);
    expect(accessJson.features.every((feature) => areaIds.has(feature.properties.area_id))).toBe(true);
  });

  it("binds every browser layer to its generated and source checksum", () => {
    expect(manifestJson).toMatchObject({
      study_area_id: "mae_sai_candidate_v1",
      dataset_mode: "candidate",
      operational_status: "non_operational",
      official_warning: false,
      expected_crs: "EPSG:4326",
      processing_allowed: true,
      can_feed_decision_layer: false,
    });
    for (const layer of manifestJson.layers) {
      const browserPath = resolve(process.cwd(), "public", layer.relative_url.replace(/^\/offline-demo\//, "offline-demo/"));
      const sourcePath = resolve(process.cwd(), "..", "..", layer.source_relative_path);
      expect(sha256(browserPath), layer.layer_id).toBe(layer.sha256);
      expect(sha256(sourcePath), `${layer.layer_id} source`).toBe(layer.source_sha256);
    }
    const bundlePath = resolve(process.cwd(), "public", manifestJson.bundle.relative_url.replace(/^\/offline-demo\//, "offline-demo/"));
    expect(sha256(bundlePath)).toBe(manifestJson.bundle.sha256);
  });

  it("keeps all coordinates inside the declared Mae Sai bounds", () => {
    const [west, south, east, north] = manifestJson.bounds;
    expect(west).toBeGreaterThanOrEqual(99.8);
    expect(east).toBeLessThanOrEqual(100.05);
    expect(south).toBeGreaterThanOrEqual(20.24);
    expect(north).toBeLessThanOrEqual(20.48);
  });
});

function sha256(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}
