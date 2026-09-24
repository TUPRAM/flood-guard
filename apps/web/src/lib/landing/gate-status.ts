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
  criteria: Record<string, GateStatusEntry>;
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
      return { label: criterion.label, met: criterion.met, detail: criterion.detail, receiptSha256: null, source: "copy" };
    }
    const receipt = typeof entry.receipt_sha256 === "string" && SHA256.test(entry.receipt_sha256) ? entry.receipt_sha256 : null;
    const met = entry.met === true && receipt !== null;
    return {
      label: criterion.label,
      met,
      detail: met && criterion.detail_met ? criterion.detail_met : criterion.detail,
      receiptSha256: met ? receipt : null,
      source: "receipt",
    };
  });
}

/** The committed, receipt-validated gate status used by the landing page. */
export const landingGateStatus: GateStatusDocument = gateStatus;
