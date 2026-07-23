import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import maeSaiBundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import type { EvidenceContext } from "@floodguard/contracts";

import { validateModelEvidenceProjection } from "./model-registry";

const bundle = maeSaiBundleJson;
const context = bundle.evidence_context as EvidenceContext;

describe("Studio model-evidence projection", () => {
  it("accepts the exact blocked Mae Sai chain and preserves all-unknown output", () => {
    const result = validateModelEvidenceProjection(
      context,
      bundle.model_registry,
      bundle.model_evaluations,
      bundle.observation_products,
    );

    expect(result.state).toBe("blocked");
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0].payload).toMatchObject({
      study_area_id: "mae_sai_candidate_v1",
      evidence_kind: "external_algorithmic_baseline",
      registry_status: "blocked",
      permitted_use: "report_only",
      official_warning: false,
      can_feed_decision_layer: false,
    });
    expect(result.evaluations[0].overall_metrics).toSatisfy(
      (metrics: Record<string, number | null>) =>
        Object.values(metrics).every((value) => value === null),
    );
    expect(result.products[0]).toMatchObject({
      valid_coverage_fraction: 0,
      abstained_fraction: 1,
      counts_as_observed_evidence: false,
      can_feed_decision_layer: false,
      unknown_cell_policy:
        "preserve_nodata_and_abstention_never_fill_as_dry",
    });
  });

  it("fails closed when the registry source bundle does not match the context", () => {
    const registry = structuredClone(bundle.model_registry);
    registry[0].payload.source_bundle_sha256 = "0".repeat(64);

    const result = validateModelEvidenceProjection(
      context,
      registry,
      bundle.model_evaluations,
      bundle.observation_products,
    );

    expect(result.state).toBe("unavailable");
    expect(result.entries).toEqual([]);
    expect(result.reason).toMatch(/active evidence context/i);
  });

  it("rejects decision eligibility, observed-evidence claims, and evidence-kind substitution", () => {
    const registry = structuredClone(bundle.model_registry);
    const products = structuredClone(bundle.observation_products);
    registry[0].payload.can_feed_decision_layer = true;
    registry[0].payload.evidence_kind = "satellite_observed_extent";
    products[0].counts_as_observed_evidence = true;

    const result = validateModelEvidenceProjection(
      context,
      registry,
      bundle.model_evaluations,
      products,
    );

    expect(result.state).toBe("unavailable");
    expect(result.entries).toEqual([]);
  });

  it("rejects absolute paths and parent traversal in product assets", () => {
    for (const unsafePath of [
      "C:\\Users\\operator\\private.tif",
      "../../private.tif",
      "/home/operator/private.tif",
    ]) {
      const products = structuredClone(bundle.observation_products);
      products[0].assets[0].relative_path = unsafePath;
      const result = validateModelEvidenceProjection(
        context,
        bundle.model_registry,
        bundle.model_evaluations,
        products,
      );
      expect(result.state, unsafePath).toBe("unavailable");
      expect(result.entries, unsafePath).toEqual([]);
    }
  });

  it("keeps new Studio registry sources free of mojibake", () => {
    for (const file of [
      resolve(process.cwd(), "src", "components", "model-registry-panel.tsx"),
      resolve(process.cwd(), "src", "lib", "model-registry.ts"),
    ]) {
      const source = readFileSync(file, "utf8");
      expect(source, file).not.toMatch(/à¸|à¹|Â|â€¦|â€“|â€”/u);
    }
  });
});
