import gateStatus from "./gate-status.json";

/** One gate criterion as written in the landing copy. */
export interface GateCriterionCopy {
  id?: string;
  label: string;
  met: boolean;
  detail: string;
  detail_met?: string;
}

/** A criterion ready to render, with the source of its mark. */
export interface ResolvedGateCriterion {
  id?: string;
  label: string;
  met: boolean;
  detail: string;
  receiptSha256: string | null;
  source: "receipt" | "copy";
}

interface GateStatusEntry {
  met: boolean;
  receipt_sha256: string | null;
}

/** Shape of the file written by `scripts/build_landing_gate_status.py`. */
export interface GateStatusDocument {
  schema: string;
  generated_utc: string;
  track?: "automated";
  source_timestamp?: string | null;
  confidence?: string;
  assumptions?: string[];
  criteria: Record<string, GateStatusEntry>;
  candidate_agreement?: Record<string, {
    processing_variant: string;
    iou: number | null;
    evaluated_coverage: number | null;
    meets_predeclared_limits: boolean;
  }>;
  human_reviewed?: boolean;
  can_feed_decision_layer?: boolean;
  official_warning?: boolean;
  operational_status?: string;
}

const SHA256 = /^[0-9a-f]{64}$/;

/**
 * Resolve each criterion's mark. A criterion whose id appears in the status
 * document is receipt-driven: it is met only when the validated status says
 * so and carries a SHA-256 receipt. Its copy value is ignored. Any other
 * criterion keeps its copy value.
 */
export function resolveGateCriteria(
  criteria: readonly GateCriterionCopy[],
  status: GateStatusDocument,
): ResolvedGateCriterion[] {
  return criteria.map(criterion => {
    const entry = criterion.id ? status.criteria[criterion.id] : undefined;
    if (!entry) {
      return {
        id: criterion.id,
        label: criterion.label,
        met: criterion.id && status.track === "automated" ? false : criterion.met,
        detail: criterion.detail,
        receiptSha256: null,
        source: criterion.id && status.track === "automated" ? "receipt" as const : "copy" as const,
      };
    }
    const receipt = typeof entry.receipt_sha256 === "string" && SHA256.test(entry.receipt_sha256) ? entry.receipt_sha256 : null;
    const met = entry.met === true && receipt !== null;
    return {
      id: criterion.id,
      label: criterion.label,
      met,
      detail: met && criterion.detail_met ? criterion.detail_met : criterion.detail,
      receiptSha256: met ? receipt : null,
      source: "receipt",
    };
  });
}

/** The committed, receipt-validated gate status used by the landing page. */
export const landingGateStatus: GateStatusDocument = gateStatus as GateStatusDocument;
