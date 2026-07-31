import type {
  EvidenceContext,
  FloodObservationProductV2,
  ModelEvaluationMetricsV2,
  ModelEvaluationV2,
  ModelRegistryEntryV1,
} from "@floodguard/contracts";

const SHA256 = /^[a-f0-9]{64}$/;
const PRIVATE_PATH =
  /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;

export interface ModelEvidenceProjection {
  entries: ModelRegistryEntryV1[];
  evaluations: ModelEvaluationV2[];
  products: FloodObservationProductV2[];
  state: "blocked" | "unavailable";
  reason: string;
}

/**
 * Validate the public-safe Studio projection against the active evidence
 * context. This deliberately accepts only the bounded competition state:
 * synthetic report-only proof that cannot feed FPPS or any decision layer.
 *
 * The browser validates the signed-envelope shape and strict cross-document
 * lineage only. It does not claim cryptographic authority: the API verifies
 * the HMAC and payload digest, while the static profile is protected by its
 * checksummed build artifact.
 */
export function validateModelEvidenceProjection(
  context: EvidenceContext,
  registryValue: unknown,
  evaluationValue: unknown,
  productValue: unknown,
): ModelEvidenceProjection {
  try {
    assertNoPrivatePaths({ registryValue, evaluationValue, productValue });
    if (
      !Array.isArray(registryValue)
      || !Array.isArray(evaluationValue)
      || !Array.isArray(productValue)
    ) {
      throw new Error("Model registry projection arrays are missing.");
    }
    if (registryValue.length === 0) {
      return unavailable(
        "No public-safe model registry record is published for this evidence context.",
      );
    }

    const entries = registryValue.map(validateRegistryEnvelope);
    const evaluations = evaluationValue.map(validateEvaluation);
    const products = productValue.map(validateProduct);
    assertUnique(
      entries.map((entry) => entry.payload.registry_entry_id),
      "registry entry",
    );
    assertUnique(
      entries.map((entry) => entry.payload.model_run_id),
      "registry model run",
    );
    assertUnique(
      evaluations.map((evaluation) => evaluation.evaluation_id),
      "evaluation",
    );
    assertUnique(products.map((product) => product.product_id), "observation product");

    const evaluationById = new Map(
      evaluations.map((evaluation) => [evaluation.evaluation_id, evaluation]),
    );
    const productById = new Map(
      products.map((product) => [product.product_id, product]),
    );

    for (const entry of entries) {
      const payload = entry.payload;
      assertRegistryContext(payload, context);
      if (
        !["candidate", "blocked"].includes(payload.registry_status)
        || payload.permitted_use !== "report_only"
        || payload.operational_status !== "non_operational"
        || payload.can_feed_decision_layer
        || payload.official_warning
        || payload.promotion_acceptance_receipt_sha256 !== null
        || payload.field_validation_receipt_sha256 !== null
        || payload.agency_acceptance_receipt_sha256 !== null
      ) {
        throw new Error(
          "Competition registry entries must remain candidate or blocked, report-only, non-operational, non-warning, and unaccepted.",
        );
      }
      if (payload.evidence_kind !== "external_algorithmic_baseline") {
        throw new Error(
          "Synthetic Studio proof must use external_algorithmic_baseline evidence.",
        );
      }
      if (Date.parse(payload.expires_at) < Date.parse(payload.valid_from)) {
        throw new Error("Model registry expiry predates its validity time.");
      }

      const evaluation = evaluationById.get(payload.evaluation_id);
      if (!evaluation) throw new Error("Model registry evaluation is missing.");
      assertEvaluationJoin(evaluation, payload, context);

      const product = productById.get(payload.product_id);
      if (!product) throw new Error("Model registry observation product is missing.");
      assertProductJoin(product, payload, context);
    }

    if (evaluations.length !== entries.length || products.length !== entries.length) {
      throw new Error("Unreferenced model evaluation or product record is present.");
    }

    return {
      entries,
      evaluations,
      products,
      state: "blocked",
      reason: entries
        .map((entry) => entry.payload.reason_blocked.trim())
        .find(Boolean)
        ?? "Qualified observed-event evaluation and promotion gates have not passed.",
    };
  } catch (error) {
    return unavailable(
      error instanceof Error ? error.message : "Model registry validation failed.",
    );
  }
}

function validateRegistryEnvelope(value: unknown): ModelRegistryEntryV1 {
  const envelope = requireRecord(value, "model registry envelope");
  const payload = requireRecord(envelope.payload, "model registry payload");
  const signature = requireRecord(envelope.signature, "model registry signature");
  requireLiteral(payload.schema_version, "1.0", "registry schema version");
  for (const field of [
    "registry_entry_id",
    "study_area_id",
    "event_id",
    "model_run_id",
    "model_id",
    "evaluation_id",
    "product_id",
    "reason_blocked",
  ] as const) {
    requireString(payload[field], `registry.payload.${field}`);
  }
  for (const field of [
    "source_bundle_sha256",
    "model_sha256",
    "model_run_manifest_sha256",
    "evaluation_manifest_sha256",
    "product_manifest_sha256",
  ] as const) {
    requireSha(payload[field], `registry.payload.${field}`);
  }
  for (const field of [
    "controlled_result_receipt_sha256",
    "promotion_acceptance_receipt_sha256",
    "field_validation_receipt_sha256",
    "agency_acceptance_receipt_sha256",
  ] as const) {
    requireNullableSha(payload[field], `registry.payload.${field}`);
  }
  requireOneOf(
    payload.evidence_kind,
    [
      "satellite_observed_extent",
      "optical_corroboration",
      "susceptibility_forecast",
      "scenario_assumption",
      "external_algorithmic_baseline",
      "human_field_observation",
    ],
    "registry.payload.evidence_kind",
  );
  requireOneOf(
    payload.dataset_mode,
    ["fixture_demo", "candidate", "official_input"],
    "registry.payload.dataset_mode",
  );
  requireOneOf(
    payload.operational_status,
    ["non_operational", "planning_only", "agency_operational"],
    "registry.payload.operational_status",
  );
  requireOneOf(
    payload.registry_status,
    ["candidate", "shadow", "approved", "revoked", "expired", "blocked"],
    "registry.payload.registry_status",
  );
  requireOneOf(
    payload.permitted_use,
    ["report_only", "shadow_only", "decision_input"],
    "registry.payload.permitted_use",
  );
  for (const field of ["issued_at", "valid_from", "expires_at"] as const) {
    requireTimestamp(payload[field], `registry.payload.${field}`);
  }
  requireBoolean(payload.official_warning, "registry.payload.official_warning");
  requireBoolean(
    payload.can_feed_decision_layer,
    "registry.payload.can_feed_decision_layer",
  );

  requireLiteral(
    signature.algorithm,
    "HMAC-SHA256",
    "registry.signature.algorithm",
  );
  requireString(signature.key_id, "registry.signature.key_id");
  requireSha(signature.payload_sha256, "registry.signature.payload_sha256");
  requireSha(signature.value, "registry.signature.value");
  return envelope as unknown as ModelRegistryEntryV1;
}

function validateEvaluation(value: unknown): ModelEvaluationV2 {
  const record = requireRecord(value, "model evaluation");
  requireCommonV2(record, "evaluation");
  for (const field of [
    "evaluation_id",
    "experiment_id",
    "study_area_id",
    "model_run_id",
    "model_id",
    "reason_blocked",
  ] as const) {
    requireString(record[field], `evaluation.${field}`);
  }
  if (
    !Array.isArray(record.event_ids)
    || record.event_ids.length === 0
    || record.event_ids.some((item) => typeof item !== "string" || !item.trim())
  ) {
    throw new Error("evaluation.event_ids must contain at least one event.");
  }
  for (const field of [
    "model_sha256",
    "model_run_manifest_sha256",
  ] as const) {
    requireSha(record[field], `evaluation.${field}`);
  }
  requireNullableSha(
    record.controlled_result_receipt_sha256,
    "evaluation.controlled_result_receipt_sha256",
  );
  requireOneOf(
    record.evaluation_status,
    ["blocked", "completed_report_only", "failed"],
    "evaluation.evaluation_status",
  );
  requireOneOf(
    record.evaluation_scope,
    ["not_evaluated", "final_holdout"],
    "evaluation.evaluation_scope",
  );
  const reference = requireRecord(
    record.reference_evidence,
    "evaluation.reference_evidence",
  );
  requireOneOf(
    reference.reference_mask_status,
    [
      "blocked",
      "synthetic_fixture_only",
      "qualified_expert_or_adjudicated",
      "confirmed_for_model_purpose",
    ],
    "evaluation.reference_evidence.reference_mask_status",
  );
  requireNullableSha(
    reference.reference_mask_sha256,
    "evaluation.reference_evidence.reference_mask_sha256",
  );
  requireNullableSha(
    reference.label_release_sha256,
    "evaluation.reference_evidence.label_release_sha256",
  );
  requireNullableSha(
    reference.reviewer_qualification_receipt_sha256,
    "evaluation.reference_evidence.reviewer_qualification_receipt_sha256",
  );
  const metrics = requireRecord(record.overall_metrics, "evaluation.overall_metrics");
  validateMetrics(metrics);
  for (const field of [
    "event_metrics",
    "error_strata",
  ] as const) {
    if (!Array.isArray(record[field])) {
      throw new Error(`evaluation.${field} must be an array.`);
    }
  }
  for (const field of [
    "partition_evidence",
    "threshold_evidence",
    "calibration",
    "selective_prediction",
    "ood_evaluation",
    "downstream_impact",
    "runtime",
  ] as const) {
    requireRecord(record[field], `evaluation.${field}`);
  }
  requireBoolean(record.processing_allowed, "evaluation.processing_allowed");
  requireBoolean(
    record.can_feed_decision_layer,
    "evaluation.can_feed_decision_layer",
  );
  return record as unknown as ModelEvaluationV2;
}

function validateProduct(value: unknown): FloodObservationProductV2 {
  const record = requireRecord(value, "observation product");
  requireCommonV2(record, "product");
  for (const field of [
    "product_id",
    "run_id",
    "study_area_id",
    "event_id",
    "reason_blocked",
  ] as const) {
    requireString(record[field], `product.${field}`);
  }
  for (const field of [
    "source_manifest_sha256",
    "model_run_manifest_sha256",
    "model_sha256",
    "evaluation_manifest_sha256",
  ] as const) {
    requireSha(record[field], `product.${field}`);
  }
  requireOneOf(
    record.evidence_kind,
    [
      "satellite_observed_extent",
      "optical_corroboration",
      "susceptibility_forecast",
      "scenario_assumption",
      "external_algorithmic_baseline",
      "human_field_observation",
    ],
    "product.evidence_kind",
  );
  const grid = requireRecord(record.grid, "product.grid");
  requireString(grid.crs, "product.grid.crs");
  requireSha(grid.grid_sha256, "product.grid.grid_sha256");
  if (!Array.isArray(record.assets) || record.assets.length === 0) {
    throw new Error("product.assets must contain browser-safe artifact descriptors.");
  }
  for (const rawAsset of record.assets) {
    const asset = requireRecord(rawAsset, "product asset");
    requireString(asset.role, "product.asset.role");
    requireString(asset.relative_path, "product.asset.relative_path");
    requireString(asset.media_type, "product.asset.media_type");
    requireSha(asset.sha256, "product.asset.sha256");
    const relativePath = String(asset.relative_path).replaceAll("\\", "/");
    if (
      relativePath.startsWith("/")
      || relativePath.split("/").includes("..")
      || PRIVATE_PATH.test(relativePath)
    ) {
      throw new Error("product.asset.relative_path must remain a safe relative path.");
    }
  }
  requireFraction(record.valid_coverage_fraction, "product.valid_coverage_fraction");
  requireFraction(record.abstained_fraction, "product.abstained_fraction");
  requireOneOf(
    record.sensor_quality_status,
    ["not_evaluated", "passed", "degraded", "failed"],
    "product.sensor_quality_status",
  );
  requireOneOf(
    record.ood_status,
    ["not_evaluated", "in_domain", "out_of_distribution"],
    "product.ood_status",
  );
  if (
    !Array.isArray(record.review_required_reasons)
    || record.review_required_reasons.length === 0
  ) {
    throw new Error("product.review_required_reasons must explain required review.");
  }
  requireLiteral(
    record.unknown_cell_policy,
    "preserve_nodata_and_abstention_never_fill_as_dry",
    "product.unknown_cell_policy",
  );
  requireBoolean(
    record.counts_as_observed_evidence,
    "product.counts_as_observed_evidence",
  );
  requireBoolean(record.processing_allowed, "product.processing_allowed");
  requireBoolean(
    record.can_feed_decision_layer,
    "product.can_feed_decision_layer",
  );
  return record as unknown as FloodObservationProductV2;
}

function assertRegistryContext(
  payload: ModelRegistryEntryV1["payload"],
  context: EvidenceContext,
): void {
  if (
    payload.study_area_id !== context.study_area_id
    || payload.source_bundle_sha256 !== context.evidence_package_sha256
    || payload.dataset_mode !== context.dataset_mode
    || payload.operational_status !== context.operational_status
  ) {
    throw new Error(
      "Model registry entry does not exactly match the active evidence context.",
    );
  }
}

function assertEvaluationJoin(
  evaluation: ModelEvaluationV2,
  payload: ModelRegistryEntryV1["payload"],
  context: EvidenceContext,
): void {
  if (
    evaluation.study_area_id !== context.study_area_id
    || evaluation.data_version !== context.data_version
    || !evaluation.event_ids.includes(payload.event_id)
    || evaluation.model_run_id !== payload.model_run_id
    || evaluation.model_id !== payload.model_id
    || evaluation.model_sha256 !== payload.model_sha256
    || evaluation.model_run_manifest_sha256 !== payload.model_run_manifest_sha256
    || evaluation.dataset_mode !== context.dataset_mode
    || evaluation.operational_status !== "non_operational"
    || evaluation.controlled_result_receipt_sha256
      !== payload.controlled_result_receipt_sha256
    || evaluation.can_feed_decision_layer
    || evaluation.official_warning
    || evaluation.downstream_impact.status !== "not_evaluated"
  ) {
    throw new Error(
      "Model evaluation does not match the blocked synthetic registry record.",
    );
  }
  const fixtureEvaluation = context.dataset_mode === "fixture_demo";
  if (
    fixtureEvaluation
      ? (
          evaluation.evaluation_status !== "completed_report_only"
          || evaluation.evaluation_scope !== "final_holdout"
          || evaluation.reference_evidence.reference_mask_status
            !== "synthetic_fixture_only"
          || evaluation.controlled_result_receipt_sha256 === null
          || !evaluation.processing_allowed
        )
      : (
          evaluation.evaluation_status !== "blocked"
          || evaluation.evaluation_scope !== "not_evaluated"
          || !["blocked", "synthetic_fixture_only"].includes(
            evaluation.reference_evidence.reference_mask_status,
          )
          || evaluation.reference_evidence.reviewer_qualification_receipt_sha256
            !== null
          || evaluation.controlled_result_receipt_sha256 !== null
          || evaluation.processing_allowed
          || !allMetricsNull(evaluation.overall_metrics)
          || evaluation.event_metrics.length !== 0
        )
  ) {
    throw new Error(
      "Model evaluation status is incompatible with its fixture or candidate evidence scope.",
    );
  }
}

function assertProductJoin(
  product: FloodObservationProductV2,
  payload: ModelRegistryEntryV1["payload"],
  context: EvidenceContext,
): void {
  if (
    product.study_area_id !== context.study_area_id
    || product.data_version !== context.data_version
    || product.event_id !== payload.event_id
    || product.run_id !== payload.model_run_id
    || product.model_sha256 !== payload.model_sha256
    || product.model_run_manifest_sha256 !== payload.model_run_manifest_sha256
    || product.evaluation_manifest_sha256 !== payload.evaluation_manifest_sha256
    || product.source_manifest_sha256 !== context.evidence_package_sha256
    || product.evidence_kind !== "external_algorithmic_baseline"
    || product.dataset_mode !== context.dataset_mode
    || product.operational_status !== "non_operational"
    || product.counts_as_observed_evidence
    || product.can_feed_decision_layer
    || product.official_warning
  ) {
    throw new Error(
      "Observation product does not match the report-only registry record.",
    );
  }
}

function requireCommonV2(
  record: Record<string, unknown>,
  label: string,
): void {
  requireLiteral(record.schema_version, "2.0", `${label}.schema_version`);
  requireOneOf(
    record.dataset_mode,
    ["fixture_demo", "candidate", "official_input"],
    `${label}.dataset_mode`,
  );
  requireOneOf(
    record.operational_status,
    ["non_operational", "planning_only", "agency_operational"],
    `${label}.operational_status`,
  );
  requireTimestamp(record.source_timestamp, `${label}.source_timestamp`);
  requireTimestamp(record.generated_at, `${label}.generated_at`);
  requireOneOf(
    record.confidence_class,
    ["low", "medium", "high"],
    `${label}.confidence_class`,
  );
  requireString(record.source_name, `${label}.source_name`);
  if (!Array.isArray(record.assumptions) || record.assumptions.length === 0) {
    throw new Error(`${label}.assumptions must explain the evidence boundary.`);
  }
  requireBoolean(record.official_warning, `${label}.official_warning`);
  requireString(record.data_version, `${label}.data_version`);
  requireString(record.git_commit, `${label}.git_commit`);
}

function validateMetrics(metrics: Record<string, unknown>): void {
  for (const field of [
    "sample_count",
    "true_positive",
    "false_positive",
    "false_negative",
    "true_negative",
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "boundary_f1",
    "signed_area_error_ratio",
    "absolute_area_error_ratio",
    "brier_score",
    "negative_log_likelihood",
    "expected_calibration_error",
  ] satisfies Array<keyof ModelEvaluationMetricsV2>) {
    const value = metrics[field];
    if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
      throw new Error(`evaluation.overall_metrics.${field} must be finite or null.`);
    }
  }
}

function allMetricsNull(metrics: ModelEvaluationMetricsV2): boolean {
  return Object.values(metrics).every((value) => value === null);
}

function unavailable(reason: string): ModelEvidenceProjection {
  return {
    entries: [],
    evaluations: [],
    products: [],
    state: "unavailable",
    reason,
  };
}

function assertUnique(values: string[], label: string): void {
  if (new Set(values).size !== values.length) {
    throw new Error(`Duplicate ${label} identity is present.`);
  }
}

function assertNoPrivatePaths(value: unknown): void {
  if (PRIVATE_PATH.test(JSON.stringify(value))) {
    throw new Error("Model registry projection contains a private absolute path.");
  }
}

function requireRecord(
  value: unknown,
  label: string,
): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} is required.`);
  }
}

function requireSha(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !SHA256.test(value)) {
    throw new Error(`${label} must be a lowercase SHA-256 digest.`);
  }
}

function requireNullableSha(
  value: unknown,
  label: string,
): asserts value is string | null {
  if (value !== null) requireSha(value, label);
}

function requireTimestamp(value: unknown, label: string): asserts value is string {
  requireString(value, label);
  if (!Number.isFinite(Date.parse(value))) {
    throw new Error(`${label} must be an ISO timestamp.`);
  }
}

function requireBoolean(value: unknown, label: string): asserts value is boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${label} must be boolean.`);
  }
}

function requireLiteral(value: unknown, expected: string, label: string): void {
  if (value !== expected) throw new Error(`${label} must be ${expected}.`);
}

function requireOneOf(
  value: unknown,
  allowed: readonly string[],
  label: string,
): void {
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw new Error(`${label} is invalid.`);
  }
}

function requireFraction(value: unknown, label: string): void {
  if (
    typeof value !== "number"
    || !Number.isFinite(value)
    || value < 0
    || value > 1
  ) {
    throw new Error(`${label} must be in [0,1].`);
  }
}
