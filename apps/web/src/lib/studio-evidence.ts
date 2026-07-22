import type { EvidenceContext, EvidenceRecord } from "@floodguard/contracts";

import { evidenceContextsMatch } from "./evidence-context";

export type EvidenceDecisionStage =
  | "processing_execution"
  | "technical_verification"
  | "observed_event_validation"
  | "governance_decision"
  | "operational_authorization";

export interface EvidenceDecisionRow {
  stage: EvidenceDecisionStage;
  state: "recorded" | "not_recorded" | "blocked" | "authorized";
  reason: string;
}

export function evidenceContextMatches(
  context: EvidenceContext,
  record: EvidenceRecord | null,
  requestedContextId?: string,
): boolean {
  if (requestedContextId && context.evidence_context_id !== requestedContextId) return false;
  return record !== null && evidenceContextsMatch(context, record.evidence_context);
}

export function buildEvidenceDecisionMatrix(
  context: EvidenceContext,
  record: EvidenceRecord | null,
): EvidenceDecisionRow[] {
  const processingRecorded = /^[a-f0-9]{64}$/.test(context.evidence_package_sha256);
  const technicalRecorded = Boolean(context.model_run_id && record?.evaluation_sha256);
  // Dataset mode and an evaluation checksum do not establish that a qualified
  // observed-event validation took place. Keep this stage fail-closed until the
  // evidence contract carries an explicit observed-validation record.
  const governanceRecorded = Boolean(record?.decision_authority && record.decision_at);
  const authorized = Boolean(record?.operational_authorized);

  return [
    {
      stage: "processing_execution",
      state: processingRecorded ? "recorded" : "not_recorded",
      reason: processingRecorded
        ? "The evidence package has a canonical integrity checksum."
        : "A checksummed evidence package has not been recorded.",
    },
    {
      stage: "technical_verification",
      state: technicalRecorded ? "recorded" : "not_recorded",
      reason: technicalRecorded
        ? "A checksummed evaluation is bound to this evidence context."
        : "No checksummed model evaluation is bound to this evidence context.",
    },
    {
      stage: "observed_event_validation",
      state: "not_recorded",
      reason: "Observed-event validation is not recorded for this evidence context.",
    },
    {
      stage: "governance_decision",
      state: governanceRecorded ? "recorded" : "not_recorded",
      reason: governanceRecorded
        ? "A decision authority and decision timestamp are recorded."
        : "Decision authority and decision time are not recorded.",
    },
    {
      stage: "operational_authorization",
      state: authorized ? "authorized" : "blocked",
      reason: authorized
        ? "The evidence record explicitly grants operational authorization."
        : "The evidence record does not grant operational authorization.",
    },
  ];
}

export function evidenceRecordJson(record: EvidenceRecord): string {
  return JSON.stringify(record, null, 2);
}

export function evidenceRecordFileName(record: EvidenceRecord): string {
  const context = record.evidence_context;
  const area = safeFilePart(context.study_area_id);
  const run = safeFilePart(context.model_run_id ?? "no-bound-run");
  const date = safeFilePart(record.generated_at.slice(0, 10) || "undated");
  const identity = safeFilePart(record.evidence_record_id).slice(-48);
  const checksum = context.evidence_package_sha256.slice(0, 12);
  return `floodguard-evidence-${area}-${run}-${date}-${identity}-${checksum}.json`;
}

function safeFilePart(value: string): string {
  return value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "not-recorded";
}
