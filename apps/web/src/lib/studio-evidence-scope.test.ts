import { describe, expect, it } from "vitest";

import {
  classifyStudioEvidenceScope,
  type StudioEvidenceScopeInput,
  type StudioModelEvidence,
} from "./studio-evidence-scope";

const blockedGeoAiRun: StudioModelEvidence = {
  datasetMode: "candidate",
  modelFamily: "geoai",
  runStatus: "completed",
  processingAllowed: false,
  canFeedDecisionLayer: false,
  reasonBlocked: "Reference-mask qualification is missing.",
  hasQualifiedReferenceMask: false,
  hasImmutableSpatialHoldout: false,
  hasCompleteValidationMetrics: false,
};

function input(overrides: Partial<StudioEvidenceScopeInput> = {}): StudioEvidenceScopeInput {
  return {
    evidenceState: "ready",
    proofReceiptVerified: true,
    proofReasonBlocked: "Synthetic fixture only.",
    models: [],
    ...overrides,
  };
}

describe("classifyStudioEvidenceScope", () => {
  it("separates an executed synthetic integration smoke from an unrun real-data evaluation", () => {
    const result = classifyStudioEvidenceScope(input());

    expect(result.integration.state).toBe("executed");
    expect(result.integration.reason).toContain("not an accuracy evaluation");
    expect(result.qualifiedEvaluation).toEqual({
      state: "not_run",
      reason: "No qualified official-input three-model evaluation is published.",
    });
    expect(result.decisionEligibility.state).toBe("blocked");
  });

  it("keeps a substituted or unavailable receipt fail-closed", () => {
    const result = classifyStudioEvidenceScope(input({
      evidenceState: "unavailable",
      proofReceiptVerified: false,
      evidenceUnavailableReason: "Proof receipt checksum does not match.",
    }));

    expect(result.integration).toEqual({
      state: "blocked",
      reason: "Proof receipt checksum does not match.",
    });
    expect(result.decisionEligibility.state).toBe("blocked");
  });

  it("shows the exact blocker for an incomplete candidate GeoAI run", () => {
    const result = classifyStudioEvidenceScope(input({ models: [blockedGeoAiRun] }));

    expect(result.qualifiedEvaluation).toEqual({
      state: "blocked",
      reason: "Reference-mask qualification is missing.",
    });
    expect(result.decisionEligibility.reason).toBe("Reference-mask qualification is missing.");
  });

  it("does not mistake a single qualified model run for the controlled three-model evaluation", () => {
    const qualifiedButNotPromoted: StudioModelEvidence = {
      ...blockedGeoAiRun,
      datasetMode: "official_input",
      processingAllowed: true,
      reasonBlocked: "Reviewer promotion threshold was not accepted.",
      hasQualifiedReferenceMask: true,
      hasImmutableSpatialHoldout: true,
      hasCompleteValidationMetrics: true,
    };

    const result = classifyStudioEvidenceScope(input({ models: [qualifiedButNotPromoted] }));

    expect(result.qualifiedEvaluation.state).toBe("blocked");
    expect(result.decisionEligibility).toEqual({
      state: "blocked",
      reason: "Reviewer promotion threshold was not accepted.",
    });
  });

  it("requires explicit official-input processing and promotion flags for decision eligibility", () => {
    const eligible: StudioModelEvidence = {
      ...blockedGeoAiRun,
      datasetMode: "official_input",
      processingAllowed: true,
      canFeedDecisionLayer: true,
      reasonBlocked: "",
      hasQualifiedReferenceMask: true,
      hasImmutableSpatialHoldout: true,
      hasCompleteValidationMetrics: true,
    };

    const result = classifyStudioEvidenceScope(input({ models: [eligible] }));

    expect(result.qualifiedEvaluation.state).toBe("blocked");
    expect(result.decisionEligibility.state).toBe("eligible");
  });

  it("marks the qualified evaluation executed only when all three model families pass the same gates", () => {
    const qualified = (modelFamily: string): StudioModelEvidence => ({
      ...blockedGeoAiRun,
      datasetMode: "official_input",
      modelFamily,
      processingAllowed: true,
      reasonBlocked: "",
      hasQualifiedReferenceMask: true,
      hasImmutableSpatialHoldout: true,
      hasCompleteValidationMetrics: true,
    });

    const result = classifyStudioEvidenceScope(input({
      models: [
        qualified("deterministic_sar_baseline"),
        qualified("weak_label_logistic"),
        qualified("geoai"),
      ],
    }));

    expect(result.qualifiedEvaluation.state).toBe("executed");
    expect(result.decisionEligibility.state).toBe("blocked");
  });
});
