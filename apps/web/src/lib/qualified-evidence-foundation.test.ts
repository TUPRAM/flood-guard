import { createHash } from "node:crypto";

import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import publicBundleJson from "../../public/offline-demo/mae-sai/public-bundle.json";

import {
  canonicalJson,
  parseQualifiedEvidenceFoundation,
  verifyQualifiedEvidenceFoundationHash,
} from "./qualified-evidence-foundation";
import type { QualifiedEvidenceFoundation } from "./types";

describe("qualified evidence foundation", () => {
  it("accepts and authenticates the full-bundle Studio projection", async () => {
    const parsed = parseQualifiedEvidenceFoundation(
      bundleJson.qualified_evidence_foundation,
    );

    expect(parsed.error).toBeNull();
    expect(parsed.value).toMatchObject({
      schema_version: "floodguard.qualified-evidence-foundation.v1",
      status: "blocked",
      authoritative_receipt: false,
      source_timestamp: "2026-07-23T12:24:48Z",
      confidence_class: "low",
    });
    expect(parsed.value?.reference_candidate_binding).toMatchObject({
      manifest_schema: "floodguard.reference_candidate_manifest.v1",
      product_id: "AIT-VAP001-TH",
      qualification_status:
        "blocked_external_permission_and_scientific_review",
      processing_allowed: false,
    });
    expect(parsed.value?.stages.map((stage) => [stage.stage_id, stage.state]))
      .toEqual([
        ["engineering_foundation", "ready"],
        ["qualified_thai_reference", "blocked"],
        ["reviewer_calibration", "blocked"],
        ["blind_review_adjudication", "blocked"],
        ["frozen_label_release", "absent"],
      ]);
    expect(parsed.value?.permissions).toMatchObject({
      source_processing_allowed: true,
      experiment_processing_allowed: false,
      qualified_reference_use_allowed: false,
      training_allowed: false,
      evaluation_allowed: false,
      decision_layer_allowed: false,
      operational_use_allowed: false,
    });
    expect(parsed.value?.safety).toEqual({
      official_warning: false,
      operational_authorized: false,
      can_feed_decision_layer: false,
      can_feed_fpps: false,
      can_assign_action_class: false,
    });
    expect(
      await verifyQualifiedEvidenceFoundationHash(
        parsed.value as QualifiedEvidenceFoundation,
      ),
    ).toBe(true);
  });

  it("rejects a status mutation that preserves the declared hash", async () => {
    const tampered = structuredClone(
      bundleJson.qualified_evidence_foundation,
    ) as QualifiedEvidenceFoundation;
    tampered.stages[1].detail_en = "Qualified reference approved.";

    const parsed = parseQualifiedEvidenceFoundation(tampered);
    expect(parsed.value).not.toBeNull();
    expect(await verifyQualifiedEvidenceFoundationHash(tampered)).toBe(false);
  });

  it("rejects authority or safety promotion in the shape validator", () => {
    const promoted = structuredClone(
      bundleJson.qualified_evidence_foundation,
    ) as unknown as Record<string, unknown>;
    promoted.authoritative_receipt = true;

    const parsed = parseQualifiedEvidenceFoundation(promoted);
    expect(parsed.value).toBeNull();
    expect(parsed.error).toMatch(/identity or status contract/i);
  });

  it("rejects a rehashed stage state that is impossible under the schema", () => {
    const impossible = structuredClone(
      bundleJson.qualified_evidence_foundation,
    ) as QualifiedEvidenceFoundation;
    impossible.stages[4].state = "blocked";
    const unsigned = structuredClone(impossible) as unknown as Record<
      string,
      unknown
    >;
    delete unsigned.canonical_sha256;
    impossible.canonical_sha256 = createHash("sha256")
      .update(canonicalJson(unsigned))
      .digest("hex");

    const parsed = parseQualifiedEvidenceFoundation(impossible);

    expect(parsed.value).toBeNull();
    expect(parsed.error).toMatch(/stage order or state is invalid/i);
  });

  it("uses deterministic key ordering and stays out of the public bundle", () => {
    expect(canonicalJson({ z: 1, a: { y: true, x: false } })).toBe(
      '{"a":{"x":false,"y":true},"z":1}',
    );
    expect(publicBundleJson).not.toHaveProperty(
      "qualified_evidence_foundation",
    );
    expect(JSON.stringify(publicBundleJson)).not.toContain(
      "qualified-thai-reference-frozen-label-release-v1",
    );
  });
});
