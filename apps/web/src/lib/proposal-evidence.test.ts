import { createHash } from "node:crypto";

import { describe, expect, it, vi } from "vitest";

import { validateGeoAiProofReceipt } from "./geoai-proof-receipt";
import {
  loadProposalEvidence,
  publicArtifactHref,
  validateProposalEvidenceManifest,
} from "./proposal-evidence";

const digest = "a".repeat(64);
const commit = "f".repeat(40);

function manifest() {
  return {
    schema_version: "1.0",
    generated_at: "2026-07-17T00:00:00Z",
    git_commit: commit,
    dataset_mode: "candidate",
    operational_status: "non_operational",
    artifacts: [{ kind: "probability_thumbnail", relative_path: "apps/web/public/evidence/probability.png", media_type: "image/png", sha256: digest }],
    test_suites: [{ name: "frontend", command: "npm run test", result: "passed", passed: 24, skipped: 0 }],
    geoai_proof: {
      geoai_version: "0.41.1",
      feature_stack_id: "synthetic-eight-band-v1",
      preprocessing_id: "explicit-uint8-v1",
      input_manifest_sha256: digest,
      output_probability_sha256: digest,
      validation_status: "passed",
      aggregation_status: "report_only",
      processing_allowed: true,
      can_feed_decision_layer: false,
      reason_blocked: "Synthetic proof only.",
    },
  };
}

function receipt() {
  return {
    schema_version: "1.0",
    proof_scope: "synthetic_integration_only",
    dataset_mode: "candidate",
    operational_status: "non_operational",
    official_warning: false,
    generated_at: "2026-07-17T00:00:00Z",
    source_timestamp: "2024-09-15T23:16:01Z",
    run_id: "geoai-synthetic-proof-001",
    geoai_version: "0.41.1",
    geoai_commit: "b".repeat(40),
    floodguard_commit: commit,
    execution_mode: "real_geoai_smoke",
    actual_geoai_calls: [
      "geoai.utils.training.export_geotiff_tiles",
      "geoai.inference.predict_geotiff",
    ],
    training_execution: "model_construction_only",
    model: {
      model_id: "floodguard/synthetic-unet",
      model_revision: "contract-proof-1",
      model_sha256: "c".repeat(64),
      architecture: "unet",
      encoder: "resnet34",
      encoder_weights: null,
    },
    feature_stack: {
      feature_stack_id: "synthetic-eight-band-v1",
      preprocessing_id: "explicit-uint8-v1",
      value_domain: "uint8_0_255",
      channel_count: 8,
      channel_names: ["pre_vv", "post_vv", "pre_vh", "post_vh", "vv_change", "vh_change", "slope", "permanent_water"],
      input_manifest_sha256: digest,
      encoded_feature_sha256: "d".repeat(64),
      preprocessing_sidecar_sha256: "e".repeat(64),
    },
    tile_export: {
      prepared_tile_manifest_sha256: "1".repeat(64),
      training_tile_count: 5,
      holdout_tile_count: 3,
      rejected_boundary_tile_count: 1,
    },
    probability: {
      artifact_name: "external-workspace/flood-probability.tif",
      sha256: digest,
      band_name: "flood_probability_0_1",
      class_index: 1,
      dtype: "float32",
      nodata: -9999,
      minimum: 0.1,
      maximum: 0.8,
      mean: 0.4,
      valid_pixel_count: 10,
      histogram_bin_edges: [0, 0.5, 1],
      histogram_counts: [6, 4],
      grid: {
        crs: "EPSG:32647",
        transform: [10, 0, 600000, 0, -10, 2200080, 0, 0, 1],
        width: 5,
        height: 2,
        bounds: [600000, 2200060, 600050, 2200080],
        resolution: [10, 10],
      },
    },
    validation_checks: {
      crs: true,
      transform: true,
      shape: true,
      nodata: true,
      class_mapping: true,
      probability_range: true,
      provenance_tags: true,
    },
    aggregation: {
      status: "report_only",
      sample_pixel_count: 10,
      mean_flood_probability_0_1: 0.4,
      p90_flood_probability_0_1: 0.7,
      eligible_for_decision_layer: false,
      eligible_for_fpps: false,
    },
    processing_allowed: true,
    can_feed_decision_layer: false,
    reason_blocked: "Synthetic proof only.",
    claim_boundary: "Synthetic integration proof; not evidence of real flood-detection accuracy.",
    receipt_payload_sha256: "2".repeat(64),
  };
}

describe("proposal evidence manifest", () => {
  it("accepts a checksummed, non-operational synthetic receipt", () => {
    expect(validateProposalEvidenceManifest(manifest()).geoai_proof.validation_status).toBe("passed");
    expect(publicArtifactHref("apps/web/public/evidence/probability.png")).toBe("/evidence/probability.png");
    expect(publicArtifactHref("services/geoai-runner/evidence/probability.png", digest)).toBe(`/proposal-evidence-assets/${digest.slice(0, 12)}-probability.png`);
  });

  it("validates the typed receipt and binds it to the manifest summary", () => {
    const value = validateProposalEvidenceManifest(manifest());
    expect(validateGeoAiProofReceipt(receipt(), value)).toMatchObject({
      model: { architecture: "unet", encoder: "resnet34", encoder_weights: null },
      validation_checks: { crs: true, probability_range: true },
      aggregation: { status: "report_only", sample_pixel_count: 10 },
    });
  });

  it("keeps a not-run proof fail-closed when shared contract checksums are null", () => {
    const value = {
      ...manifest(),
      geoai_proof: {
        ...manifest().geoai_proof,
        input_manifest_sha256: null,
        output_probability_sha256: null,
        validation_status: "not_run",
        aggregation_status: "not_run",
        processing_allowed: false,
        reason_blocked: "Proof has not run.",
      },
    };

    expect(validateProposalEvidenceManifest(value).geoai_proof).toMatchObject({
      input_manifest_sha256: null,
      output_probability_sha256: null,
      can_feed_decision_layer: false,
    });
  });

  it("fails closed for decision promotion or path substitution", () => {
    expect(() => validateProposalEvidenceManifest({
      ...manifest(),
      geoai_proof: { ...manifest().geoai_proof, can_feed_decision_layer: true },
    })).toThrow(/cannot feed/i);
    expect(() => validateProposalEvidenceManifest({
      ...manifest(),
      artifacts: [{ ...manifest().artifacts[0], relative_path: "C:\\Users\\person\\proof.png" }],
    })).toThrow(/public and relative|private absolute path/i);
    expect(() => validateProposalEvidenceManifest({
      ...manifest(),
      artifacts: [{ ...manifest().artifacts[0], relative_path: "https://untrusted.example/proof.png" }],
    })).toThrow(/public and relative/i);
    expect(() => validateProposalEvidenceManifest({
      ...manifest(),
      operational_status: "agency_operational",
    })).toThrow(/cannot claim agency operation/i);
  });

  it("returns an unavailable state instead of trusting malformed evidence", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith("proposal-evidence-status.json")
      ? Response.json({ available: true })
      : Response.json({ ...manifest(), geoai_proof: {} }));
    await expect(loadProposalEvidence(fetcher as typeof fetch)).resolves.toMatchObject({ state: "unavailable" });
  });

  it("loads a checksum-bound receipt before publishing proof details", async () => {
    const receiptText = JSON.stringify(receipt());
    const receiptSha256 = createHash("sha256").update(receiptText).digest("hex");
    const value = {
      ...manifest(),
      artifacts: [
        ...manifest().artifacts,
        {
          kind: "geoai_proof_receipt",
          relative_path: "services/geoai-runner/evidence/geoai-proof-receipt.json",
          media_type: "application/json",
          sha256: receiptSha256,
        },
      ],
    };
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("proposal-evidence-status.json")) return Response.json({ available: true });
      if (path.endsWith("proposal-evidence.json")) return Response.json(value);
      return new Response(receiptText, { headers: { "content-type": "application/json" } });
    });

    await expect(loadProposalEvidence(fetcher as typeof fetch)).resolves.toMatchObject({
      state: "ready",
      proofReceipt: { model: { architecture: "unet" }, can_feed_decision_layer: false },
    });
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("fails closed for receipt file and proof-summary substitutions", async () => {
    const substituted = { ...receipt(), probability: { ...receipt().probability, sha256: "9".repeat(64) } };
    const substitutedText = JSON.stringify(substituted);
    const substitutedSha = createHash("sha256").update(substitutedText).digest("hex");
    const value = {
      ...manifest(),
      artifacts: [{
        kind: "geoai_proof_receipt",
        relative_path: "services/geoai-runner/evidence/geoai-proof-receipt.json",
        media_type: "application/json",
        sha256: substitutedSha,
      }],
    };
    const summarySubstitution = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("proposal-evidence-status.json")) return Response.json({ available: true });
      if (path.endsWith("proposal-evidence.json")) return Response.json(value);
      return new Response(substitutedText);
    });
    await expect(loadProposalEvidence(summarySubstitution as typeof fetch)).resolves.toMatchObject({
      state: "unavailable",
      reason: expect.stringMatching(/does not match the validated proof summary/i),
    });

    const validText = JSON.stringify(receipt());
    const tamperedBytes = `${validText} `;
    const fileSubstitution = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("proposal-evidence-status.json")) return Response.json({ available: true });
      if (path.endsWith("proposal-evidence.json")) return Response.json({
        ...manifest(),
        artifacts: [{ ...value.artifacts[0], sha256: createHash("sha256").update(validText).digest("hex") }],
      });
      return new Response(tamperedBytes);
    });
    await expect(loadProposalEvidence(fileSubstitution as typeof fetch)).resolves.toMatchObject({
      state: "unavailable",
      reason: expect.stringMatching(/file checksum/i),
    });
  });

  it("does not request a missing manifest when a build marks it unavailable", async () => {
    const fetcher = vi.fn(async () => Response.json({ available: false }));

    await expect(loadProposalEvidence(fetcher as typeof fetch)).resolves.toMatchObject({
      state: "unavailable",
      reason: expect.stringMatching(/no proposal evidence manifest was published/i),
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
