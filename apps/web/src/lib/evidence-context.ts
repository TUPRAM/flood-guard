import type {
  AreaDecision,
  EvidenceContext,
  EvidenceRecord,
  LayerCatalogItem,
  StatusResponse,
} from "@floodguard/contracts";

import type { StudyAreaId } from "./types";

export function assertEvidenceContextMatches(
  context: EvidenceContext,
  status: StatusResponse,
  studyArea: StudyAreaId,
  requestedContextId?: string,
): void {
  if (
    (requestedContextId !== undefined
      && context.evidence_context_id !== requestedContextId)
    || context.study_area_id !== studyArea
    || context.evidence_context_id !== status.evidence_context_id
    || context.evidence_package_id !== status.evidence_package_id
    || context.data_version !== status.data_version
    || context.dataset_mode !== status.dataset_mode
    || context.operational_status !== status.operational_status
    || context.official_warning !== status.official_warning
  ) {
    throw new Error("Evidence context does not match the requested study-area artifacts.");
  }
}

export function assertArtifactsMatchEvidenceContext(
  context: EvidenceContext,
  areas: readonly AreaDecision[],
  layers: readonly LayerCatalogItem[],
): void {
  const expectedId = context.evidence_context_id;
  if (
    areas.some((area) => (
      area.evidence_context_id !== expectedId
      || area.data_version !== context.data_version
      || area.dataset_mode !== context.dataset_mode
      || area.operational_status !== context.operational_status
    ))
    || layers.some((layer) => (
      layer.evidence_context_id !== expectedId
      || layer.evidence_package_id !== context.evidence_package_id
      || layer.data_version !== context.data_version
      || layer.dataset_mode !== context.dataset_mode
      || layer.operational_status !== context.operational_status
    ))
  ) {
    throw new Error("One or more artifacts do not belong to the active evidence context.");
  }
}

export function evidenceRecordMatchesContext(
  record: EvidenceRecord,
  context: EvidenceContext,
): boolean {
  return evidenceContextsMatch(record.evidence_context, context);
}

export function evidenceContextsMatch(
  left: EvidenceContext,
  right: EvidenceContext,
): boolean {
  const leftTuple = evidenceContextIdentityTuple(left);
  const rightTuple = evidenceContextIdentityTuple(right);
  return leftTuple.every((value, index) => value === rightTuple[index]);
}

function evidenceContextIdentityTuple(context: EvidenceContext): readonly (
  string | boolean | null
)[] {
  return [
    context.schema_version,
    context.evidence_context_id,
    context.study_area_id,
    context.data_version,
    context.evidence_package_id,
    context.evidence_package_sha256,
    context.model_run_id,
    context.dataset_mode,
    context.operational_status,
    context.official_warning,
    context.generated_at,
  ] as const;
}
