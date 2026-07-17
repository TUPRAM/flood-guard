import { describe, expect, it, vi } from "vitest";

import {
  loadProposalEvidence,
  publicArtifactHref,
  validateProposalEvidenceManifest,
} from "./proposal-evidence";

const digest = "a".repeat(64);

function manifest() {
  return {
    schema_version: "1.0",
    generated_at: "2026-07-17T00:00:00Z",
    git_commit: "f424b52",
    dataset_mode: "fixture_demo",
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
      aggregation_status: "passed",
      processing_allowed: true,
      can_feed_decision_layer: false,
      reason_blocked: "Synthetic proof only.",
    },
  };
}

describe("proposal evidence manifest", () => {
  it("accepts a checksummed, non-operational synthetic receipt", () => {
    expect(validateProposalEvidenceManifest(manifest()).geoai_proof.validation_status).toBe("passed");
    expect(publicArtifactHref("apps/web/public/evidence/probability.png")).toBe("/evidence/probability.png");
    expect(publicArtifactHref("services/geoai-runner/evidence/probability.png", digest)).toBe(`/proposal-evidence-assets/${digest.slice(0, 12)}-probability.png`);
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

  it("does not request a missing manifest when a build marks it unavailable", async () => {
    const fetcher = vi.fn(async () => Response.json({ available: false }));

    await expect(loadProposalEvidence(fetcher as typeof fetch)).resolves.toMatchObject({
      state: "unavailable",
      reason: expect.stringMatching(/no proposal evidence manifest was published/i),
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
