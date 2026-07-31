import type { ProposalEvidenceManifest } from "@floodguard/contracts";

const HEX = /^[a-f0-9]+$/i;
const PRIVATE_PATH = /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;
const CLAIM_BOUNDARY = "Synthetic integration proof; not evidence of real flood-detection accuracy.";
const ACTUAL_GEOAI_CALLS = [
  "geoai.utils.training.export_geotiff_tiles",
  "geoai.inference.predict_geotiff",
] as const;
const VALIDATION_KEYS = [
  "crs",
  "transform",
  "shape",
  "nodata",
  "class_mapping",
  "probability_range",
  "provenance_tags",
] as const;

export interface GeoAiProofReceipt {
  schema_version: "1.0";
  proof_scope: "synthetic_integration_only";
  dataset_mode: "candidate";
  operational_status: "non_operational";
  official_warning: false;
  generated_at: string;
  source_timestamp: string;
  run_id: string;
  geoai_version: "0.41.1";
  geoai_commit: string;
  floodguard_commit: string;
  execution_mode: "real_geoai_smoke";
  actual_geoai_calls: [typeof ACTUAL_GEOAI_CALLS[0], typeof ACTUAL_GEOAI_CALLS[1]];
  training_execution: "model_construction_only" | "one_epoch_completed";
  model: {
    model_id: string;
    model_revision: string;
    model_sha256: string;
    architecture: string;
    encoder: string;
    encoder_weights: string | null;
  };
  feature_stack: {
    feature_stack_id: string;
    preprocessing_id: string;
    value_domain: "uint8_0_255";
    channel_count: number;
    channel_names: string[];
    input_manifest_sha256: string;
    encoded_feature_sha256: string;
    preprocessing_sidecar_sha256: string;
  };
  tile_export: {
    prepared_tile_manifest_sha256: string;
    training_tile_count: number;
    holdout_tile_count: number;
    rejected_boundary_tile_count: number;
  };
  probability: {
    artifact_name: string;
    sha256: string;
    band_name: "flood_probability_0_1";
    class_index: 1;
    dtype: "float32";
    nodata: number;
    minimum: number;
    maximum: number;
    mean: number;
    valid_pixel_count: number;
    histogram_bin_edges: number[];
    histogram_counts: number[];
    grid: {
      crs: string;
      transform: number[];
      width: number;
      height: number;
      bounds: number[];
      resolution: number[];
    };
  };
  validation_checks: Record<(typeof VALIDATION_KEYS)[number], true>;
  aggregation: {
    status: "report_only";
    sample_pixel_count: number;
    mean_flood_probability_0_1: number;
    p90_flood_probability_0_1: number;
    eligible_for_decision_layer: false;
    eligible_for_fpps: false;
  };
  processing_allowed: boolean;
  can_feed_decision_layer: false;
  reason_blocked: string;
  claim_boundary: typeof CLAIM_BOUNDARY;
  receipt_payload_sha256: string;
}

/** Validate the public-safe receipt and bind every safety-significant field to the manifest. */
export function validateGeoAiProofReceipt(
  value: unknown,
  manifest: ProposalEvidenceManifest,
): GeoAiProofReceipt {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt must be an object.");
  if (PRIVATE_PATH.test(JSON.stringify(value))) throw new Error("GeoAI proof receipt contains a private absolute path.");
  if (value.schema_version !== "1.0") throw new Error("GeoAI proof receipt schema_version is invalid.");
  if (value.proof_scope !== "synthetic_integration_only") throw new Error("GeoAI proof receipt scope is invalid.");
  if (value.dataset_mode !== "candidate" || value.dataset_mode !== manifest.dataset_mode) {
    throw new Error("GeoAI proof receipt dataset mode does not match the evidence manifest.");
  }
  if (value.operational_status !== "non_operational" || value.operational_status !== manifest.operational_status) {
    throw new Error("GeoAI proof receipt operational status does not match the evidence manifest.");
  }
  if (value.official_warning !== false || value.can_feed_decision_layer !== false) {
    throw new Error("GeoAI proof receipt must remain non-warning and blocked from the decision layer.");
  }
  if (value.claim_boundary !== CLAIM_BOUNDARY) throw new Error("GeoAI proof receipt claim boundary is invalid.");
  requireTimestamp(value.generated_at, "generated_at");
  requireTimestamp(value.source_timestamp, "source_timestamp");
  requireString(value.run_id, "run_id");
  requireSha(value.geoai_commit, "geoai_commit", 40);
  requireSha(value.floodguard_commit, "floodguard_commit", 40);
  if (value.floodguard_commit !== manifest.git_commit) throw new Error("GeoAI proof receipt commit does not match the evidence manifest.");
  if (value.geoai_version !== "0.41.1" || value.geoai_version !== manifest.geoai_proof.geoai_version) {
    throw new Error("GeoAI proof receipt version does not match the evidence manifest.");
  }
  validateExecution(value);
  const model = validateModel(value.model);
  const featureStack = validateFeatureStack(value.feature_stack);
  const tileExport = validateTileExport(value.tile_export);
  const probability = validateProbability(value.probability);
  const validationChecks = validateChecks(value.validation_checks);
  const aggregation = validateAggregation(value.aggregation, probability);
  if (typeof value.processing_allowed !== "boolean" || value.processing_allowed !== manifest.geoai_proof.processing_allowed) {
    throw new Error("GeoAI proof receipt processing gate does not match the evidence manifest.");
  }
  requireString(value.reason_blocked, "reason_blocked");
  if (value.reason_blocked !== manifest.geoai_proof.reason_blocked) {
    throw new Error("GeoAI proof receipt blocked reason does not match the evidence manifest.");
  }
  requireSha(value.receipt_payload_sha256, "receipt_payload_sha256");

  const proof = manifest.geoai_proof;
  if (
    proof.validation_status !== "passed"
    || proof.aggregation_status !== "report_only"
    || proof.can_feed_decision_layer
    || featureStack.feature_stack_id !== proof.feature_stack_id
    || featureStack.preprocessing_id !== proof.preprocessing_id
    || featureStack.input_manifest_sha256 !== proof.input_manifest_sha256
    || probability.sha256 !== proof.output_probability_sha256
  ) {
    throw new Error("GeoAI proof receipt does not match the validated proof summary.");
  }

  return {
    ...value,
    model,
    feature_stack: featureStack,
    tile_export: tileExport,
    probability,
    validation_checks: validationChecks,
    aggregation,
  } as GeoAiProofReceipt;
}

function validateExecution(value: Record<string, unknown>): void {
  if (value.execution_mode !== "real_geoai_smoke") {
    throw new Error("Only a real GeoAI smoke receipt can be published as execution evidence.");
  }
  if (value.training_execution !== "model_construction_only" && value.training_execution !== "one_epoch_completed") {
    throw new Error("GeoAI proof receipt training boundary is invalid.");
  }
  if (
    !Array.isArray(value.actual_geoai_calls)
    || value.actual_geoai_calls.length !== ACTUAL_GEOAI_CALLS.length
    || value.actual_geoai_calls.some((call, index) => call !== ACTUAL_GEOAI_CALLS[index])
  ) {
    throw new Error("GeoAI proof receipt execution calls are invalid.");
  }
}

function validateModel(value: unknown): GeoAiProofReceipt["model"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt model is required.");
  for (const key of ["model_id", "model_revision", "architecture", "encoder"] as const) requireString(value[key], `model.${key}`);
  requireSha(value.model_sha256, "model.model_sha256");
  if (value.encoder_weights !== null) requireString(value.encoder_weights, "model.encoder_weights");
  return value as unknown as GeoAiProofReceipt["model"];
}

function validateFeatureStack(value: unknown): GeoAiProofReceipt["feature_stack"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt feature stack is required.");
  requireString(value.feature_stack_id, "feature_stack.feature_stack_id");
  requireString(value.preprocessing_id, "feature_stack.preprocessing_id");
  if (value.value_domain !== "uint8_0_255") throw new Error("GeoAI proof receipt feature value domain is invalid.");
  if (!Number.isInteger(value.channel_count) || Number(value.channel_count) < 6 || Number(value.channel_count) > 8) {
    throw new Error("GeoAI proof receipt channel count must be between six and eight.");
  }
  if (
    !Array.isArray(value.channel_names)
    || value.channel_names.length !== value.channel_count
    || value.channel_names.some((name) => typeof name !== "string" || !name.trim())
  ) {
    throw new Error("GeoAI proof receipt channel order is invalid.");
  }
  for (const key of ["input_manifest_sha256", "encoded_feature_sha256", "preprocessing_sidecar_sha256"] as const) {
    requireSha(value[key], `feature_stack.${key}`);
  }
  return value as unknown as GeoAiProofReceipt["feature_stack"];
}

function validateTileExport(value: unknown): GeoAiProofReceipt["tile_export"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt tile export is required.");
  requireSha(value.prepared_tile_manifest_sha256, "tile_export.prepared_tile_manifest_sha256");
  for (const key of ["training_tile_count", "holdout_tile_count", "rejected_boundary_tile_count"] as const) {
    if (!Number.isInteger(value[key]) || Number(value[key]) < 0) throw new Error(`tile_export.${key} is invalid.`);
  }
  if (Number(value.training_tile_count) < 1 || Number(value.holdout_tile_count) < 1) {
    throw new Error("GeoAI proof receipt requires non-empty train and spatial holdout tiles.");
  }
  return value as unknown as GeoAiProofReceipt["tile_export"];
}

function validateProbability(value: unknown): GeoAiProofReceipt["probability"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt probability output is required.");
  requireString(value.artifact_name, "probability.artifact_name");
  if (/^[A-Za-z]:[\\/]|^\\\\|^file:\/\/|^\//i.test(value.artifact_name as string) || (value.artifact_name as string).includes("..")) {
    throw new Error("GeoAI probability artifact name must be public-safe and relative.");
  }
  requireSha(value.sha256, "probability.sha256");
  if (value.band_name !== "flood_probability_0_1" || value.class_index !== 1 || value.dtype !== "float32") {
    throw new Error("GeoAI proof receipt must explicitly identify float32 class-1 probability.");
  }
  requireFinite(value.nodata, "probability.nodata");
  for (const key of ["minimum", "maximum", "mean"] as const) requireProbability(value[key], `probability.${key}`);
  if (Number(value.minimum) > Number(value.mean) || Number(value.mean) > Number(value.maximum)) {
    throw new Error("GeoAI proof receipt probability summary is inconsistent.");
  }
  if (!Number.isInteger(value.valid_pixel_count) || Number(value.valid_pixel_count) < 1) {
    throw new Error("GeoAI proof receipt valid pixel count is invalid.");
  }
  if (!Array.isArray(value.histogram_bin_edges) || !Array.isArray(value.histogram_counts)) {
    throw new Error("GeoAI proof receipt probability histogram is required.");
  }
  const histogramEdges = value.histogram_bin_edges;
  const histogramCounts = value.histogram_counts;
  if (histogramEdges.length !== histogramCounts.length + 1 || histogramCounts.length < 2) {
    throw new Error("GeoAI proof receipt probability histogram shape is invalid.");
  }
  histogramEdges.forEach((edge, index) => {
    requireProbability(edge, `probability.histogram_bin_edges[${index}]`);
    if (index > 0 && Number(edge) <= Number(histogramEdges[index - 1])) {
      throw new Error("GeoAI proof receipt probability histogram edges must increase.");
    }
  });
  if (histogramEdges[0] !== 0 || histogramEdges.at(-1) !== 1) {
    throw new Error("GeoAI proof receipt probability histogram must span [0,1].");
  }
  histogramCounts.forEach((count, index) => {
    if (!Number.isInteger(count) || Number(count) < 0) throw new Error(`probability.histogram_counts[${index}] is invalid.`);
  });
  if (histogramCounts.reduce((total, count) => total + Number(count), 0) !== value.valid_pixel_count) {
    throw new Error("GeoAI proof receipt histogram count does not match valid pixels.");
  }
  const grid = validateGrid(value.grid);
  return { ...value, grid } as unknown as GeoAiProofReceipt["probability"];
}

function validateGrid(value: unknown): GeoAiProofReceipt["probability"]["grid"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt probability grid is required.");
  requireString(value.crs, "probability.grid.crs");
  if (!/^EPSG:\d+$/i.test(value.crs as string)) throw new Error("GeoAI proof receipt grid CRS is invalid.");
  if (!Number.isInteger(value.width) || Number(value.width) < 1 || !Number.isInteger(value.height) || Number(value.height) < 1) {
    throw new Error("GeoAI proof receipt grid dimensions are invalid.");
  }
  validateFiniteArray(value.transform, 9, "probability.grid.transform");
  validateFiniteArray(value.bounds, 4, "probability.grid.bounds");
  validateFiniteArray(value.resolution, 2, "probability.grid.resolution");
  if ((value.resolution as number[]).some((resolution) => resolution <= 0)) {
    throw new Error("GeoAI proof receipt grid resolution must be positive.");
  }
  return value as unknown as GeoAiProofReceipt["probability"]["grid"];
}

function validateChecks(value: unknown): GeoAiProofReceipt["validation_checks"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt validation checks are required.");
  for (const key of VALIDATION_KEYS) {
    if (value[key] !== true) throw new Error(`GeoAI proof receipt validation check ${key} did not pass.`);
  }
  if (
    Object.keys(value).some((key) => !VALIDATION_KEYS.includes(key as (typeof VALIDATION_KEYS)[number]))
    || Object.values(value).some((check) => check !== true)
  ) {
    throw new Error("GeoAI proof receipt contains a failed validation check.");
  }
  return value as unknown as GeoAiProofReceipt["validation_checks"];
}

function validateAggregation(
  value: unknown,
  probability: GeoAiProofReceipt["probability"],
): GeoAiProofReceipt["aggregation"] {
  if (!isRecord(value)) throw new Error("GeoAI proof receipt aggregation is required.");
  if (
    value.status !== "report_only"
    || value.eligible_for_decision_layer !== false
    || value.eligible_for_fpps !== false
  ) {
    throw new Error("Synthetic GeoAI aggregation must remain report-only and ineligible.");
  }
  if (value.sample_pixel_count !== probability.valid_pixel_count) {
    throw new Error("GeoAI aggregation sample count does not match the probability raster.");
  }
  requireProbability(value.mean_flood_probability_0_1, "aggregation.mean_flood_probability_0_1");
  requireProbability(value.p90_flood_probability_0_1, "aggregation.p90_flood_probability_0_1");
  if (Math.abs(Number(value.mean_flood_probability_0_1) - probability.mean) > 0.000001) {
    throw new Error("GeoAI aggregation mean does not match the probability raster.");
  }
  return value as unknown as GeoAiProofReceipt["aggregation"];
}

function validateFiniteArray(value: unknown, length: number, label: string): asserts value is number[] {
  if (!Array.isArray(value) || value.length !== length || value.some((item) => typeof item !== "number" || !Number.isFinite(item))) {
    throw new Error(`${label} is invalid.`);
  }
}

function requireString(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`${label} is required.`);
}

function requireTimestamp(value: unknown, label: string): asserts value is string {
  requireString(value, label);
  if (!Number.isFinite(Date.parse(value))) throw new Error(`${label} must be an ISO timestamp.`);
}

function requireSha(value: unknown, label: string, exactLength = 64): asserts value is string {
  if (typeof value !== "string" || value.length !== exactLength || !HEX.test(value)) {
    throw new Error(`${label} must be a ${exactLength === 64 ? "SHA-256 digest" : `${exactLength}-character hexadecimal commit`}.`);
  }
}

function requireFinite(value: unknown, label: string): asserts value is number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} must be finite.`);
}

function requireProbability(value: unknown, label: string): asserts value is number {
  requireFinite(value, label);
  if (value < 0 || value > 1) throw new Error(`${label} must be in [0,1].`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
