import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import accessJson from "../../public/offline-demo/mae-sai/access-hotspots.json";
import areasJson from "../../public/offline-demo/mae-sai/areas.json";
import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import facilitiesJson from "../../public/offline-demo/mae-sai/facilities.json";
import manifestJson from "../../public/offline-demo/mae-sai/manifest.json";
import publicAreasJson from "../../public/offline-demo/mae-sai/public-areas.json";
import publicBundleJson from "../../public/offline-demo/mae-sai/public-bundle.json";
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
    expect(bundleJson.evidence_context.evidence_context_id).toBe(
      bundleJson.status.evidence_context_id,
    );
    expect(bundleJson.evidence_record.evidence_context.evidence_package_sha256).toBe(
      bundleJson.evidence_context.evidence_package_sha256,
    );
    expect(bundleJson.evidence_record.evidence_context.model_run_id).toBeNull();
    expect(bundleJson.model_runs_v2).toHaveLength(1);
    expect(bundleJson.model_registry).toHaveLength(1);
    expect(bundleJson.model_registry[0].payload).toMatchObject({
      evidence_kind: "external_algorithmic_baseline",
      registry_status: "blocked",
      permitted_use: "report_only",
      can_feed_decision_layer: false,
      official_warning: false,
    });
    expect(bundleJson.model_runs_v2[0]).toMatchObject({
      run_id: bundleJson.model_registry[0].payload.model_run_id,
      study_area_id: "mae_sai_candidate_v1",
      run_status: "blocked",
      processing_allowed: false,
      can_feed_decision_layer: false,
    });
    expect(bundleJson.model_evaluations[0].evaluation_scope).toBe("not_evaluated");
    expect(bundleJson.observation_products[0]).toMatchObject({
      valid_coverage_fraction: 0,
      abstained_fraction: 1,
      counts_as_observed_evidence: false,
      can_feed_decision_layer: false,
    });
  });

  it("ships a separately generated public-safe projection", () => {
    expect(publicBundleJson.evidence_context.evidence_context_id).toBe(
      bundleJson.evidence_context.evidence_context_id,
    );
    expect(publicBundleJson.public_areas).toHaveLength(8);
    expect(publicAreasJson.features).toHaveLength(8);
    expect(publicBundleJson.layers.map((layer) => layer.layer_id)).toEqual([
      "public_preparedness_areas",
    ]);
    expect(publicBundleJson.layers[0].role_visibility).toEqual(["public"]);
    expect(publicBundleJson.shelters).toEqual([]);
    expect(publicBundleJson).not.toHaveProperty("model_registry");
    expect(publicBundleJson).not.toHaveProperty("model_runs_v2");
    expect(publicBundleJson).not.toHaveProperty("model_evaluations");
    expect(publicBundleJson).not.toHaveProperty("observation_products");
    expect(publicBundleJson).not.toHaveProperty("model_asset_descriptors");
    const publicKeys = new Set([
      "schema_version",
      "evidence_context_id",
      "area_id",
      "area_name_th",
      "area_name_en",
      "planning_priority_0_100",
      "evidence_sufficiency",
      "recommendation_code",
      "source_timestamp",
      "freshness",
      "current_conditions_confirmed",
    ]);
    expect(publicAreasJson.features.every((feature) => (
      Object.keys(feature.properties).every((key) => publicKeys.has(key))
      && feature.properties.current_conditions_confirmed === false
    ))).toBe(true);
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
    expect(manifestJson.evidence_context.evidence_context_id).toBe(
      bundleJson.evidence_context.evidence_context_id,
    );
    expect(manifestJson.public_bundle.sha256).toBe(
      sha256(resolve(process.cwd(), "public", "offline-demo", "mae-sai", "public-bundle.json")),
    );
    for (const layer of manifestJson.layers) {
      const browserPath = resolve(process.cwd(), "public", layer.relative_url.replace(/^\/offline-demo\//, "offline-demo/"));
      const sourcePath = resolve(process.cwd(), "..", "..", layer.source_relative_path);
      expect(sha256(browserPath), layer.layer_id).toBe(layer.sha256);
      expect(sha256(sourcePath), `${layer.layer_id} source`).toBe(layer.source_sha256);
    }
    const bundlePath = resolve(process.cwd(), "public", manifestJson.bundle.relative_url.replace(/^\/offline-demo\//, "offline-demo/"));
    expect(sha256(bundlePath)).toBe(manifestJson.bundle.sha256);
    expect(manifestJson.model_evidence_descriptors).toHaveLength(5);
    for (const descriptor of manifestJson.model_evidence_descriptors) {
      const descriptorPath = resolve(
        process.cwd(),
        "public",
        descriptor.relative_url.replace(/^\//, ""),
      );
      expect(sha256(descriptorPath), descriptor.relative_url).toBe(
        descriptor.sha256,
      );
      expect(JSON.parse(readFileSync(descriptorPath, "utf8"))).toMatchObject({
        descriptor_type: "floodguard.blocked_observation_asset",
        materialization_status: "descriptor_only_no_raster",
        counts_as_observed_evidence: false,
        can_feed_decision_layer: false,
      });
    }
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
