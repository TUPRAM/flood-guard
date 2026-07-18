export type StudioEvidenceState = "checking" | "executed" | "not_run" | "blocked" | "eligible";

export interface StudioModelEvidence {
  datasetMode: "fixture_demo" | "candidate" | "official_input";
  modelFamily: string;
  runStatus: string;
  processingAllowed: boolean;
  canFeedDecisionLayer: boolean;
  reasonBlocked: string;
  hasQualifiedReferenceMask: boolean;
  hasImmutableSpatialHoldout: boolean;
  hasCompleteValidationMetrics: boolean;
}

export interface StudioEvidenceScopeInput {
  evidenceState: "loading" | "ready" | "unavailable";
  proofReceiptVerified: boolean;
  proofReasonBlocked: string;
  evidenceUnavailableReason?: string;
  models: StudioModelEvidence[];
}

export interface StudioEvidenceScopeItem {
  state: StudioEvidenceState;
  reason: string;
}

export interface StudioEvidenceScope {
  integration: StudioEvidenceScopeItem;
  qualifiedEvaluation: StudioEvidenceScopeItem;
  decisionEligibility: StudioEvidenceScopeItem;
}

const REQUIRED_MODEL_FAMILIES = [
  "deterministic_sar_baseline",
  "weak_label_logistic",
  "geoai",
] as const;

export function classifyStudioEvidenceScope(input: StudioEvidenceScopeInput): StudioEvidenceScope {
  const integration = classifyIntegrationProof(input);
  const geoAiRuns = input.models.filter((run) => run.modelFamily === "geoai");
  const qualifiedRuns = input.models.filter(isQualifiedEvaluation);
  const hasQualifiedThreeModelEvaluation = REQUIRED_MODEL_FAMILIES.every((family) =>
    qualifiedRuns.some((run) => run.modelFamily === family),
  );
  const decisionRun = input.models.find(
    (run) => run.datasetMode === "official_input" && run.processingAllowed && run.canFeedDecisionLayer,
  );

  const qualifiedEvaluation: StudioEvidenceScopeItem = hasQualifiedThreeModelEvaluation
    ? {
        state: "executed",
        reason: "The baseline, weak-label, and GeoAI runs share qualified official inputs, reference masks, immutable spatial holdouts, and the full validation metric set.",
      }
    : geoAiRuns.length > 0
      ? {
          state: "blocked",
          reason: firstBlockedReason(geoAiRuns) || "The published GeoAI run does not satisfy every qualified real-data evaluation gate.",
        }
      : {
          state: "not_run",
          reason: "No qualified official-input three-model evaluation is published.",
        };

  const decisionEligibility: StudioEvidenceScopeItem = decisionRun
    ? {
        state: "eligible",
        reason: "An official-input run explicitly declares processing_allowed=true and can_feed_decision_layer=true.",
      }
    : {
        state: "blocked",
        reason: qualifiedRuns.map((run) => run.reasonBlocked.trim()).find(Boolean)
          || firstBlockedReason(geoAiRuns)
          || "Qualified real-data evaluation and promotion gates have not passed.",
      };

  return { integration, qualifiedEvaluation, decisionEligibility };
}

function classifyIntegrationProof(input: StudioEvidenceScopeInput): StudioEvidenceScopeItem {
  if (input.evidenceState === "loading") {
    return { state: "checking", reason: "Validating the published manifest and proof-receipt checksum." };
  }
  if (input.evidenceState === "ready" && input.proofReceiptVerified) {
    return {
      state: "executed",
      reason: "A checksummed synthetic execution receipt verifies the integration path; it is not an accuracy evaluation.",
    };
  }
  return {
    state: "blocked",
    reason: input.evidenceUnavailableReason?.trim()
      || input.proofReasonBlocked.trim()
      || "No validated GeoAI integration receipt is available.",
  };
}

function isQualifiedEvaluation(run: StudioModelEvidence): boolean {
  return run.datasetMode === "official_input"
    && run.runStatus === "completed"
    && run.processingAllowed
    && run.hasQualifiedReferenceMask
    && run.hasImmutableSpatialHoldout
    && run.hasCompleteValidationMetrics;
}

function firstBlockedReason(runs: StudioModelEvidence[]): string {
  return runs.map((run) => run.reasonBlocked.trim()).find(Boolean) ?? "";
}
