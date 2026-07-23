/** Runtime enum constants and hand-maintained types for FloodGuard JSON schemas. */

export const SCHEMA_VERSION = "1.0" as const;

export const COMMON_METADATA_FIELDS = [
  "schema_version",
  "dataset_mode",
  "operational_status",
  "source_timestamp",
  "generated_at",
  "confidence_class",
  "source_name",
  "assumptions",
  "official_warning",
  "data_version",
  "git_commit",
] as const;

export const DATASET_MODES = [
  "fixture_demo",
  "candidate",
  "official_input",
] as const;
export type DatasetMode = (typeof DATASET_MODES)[number];

export const OPERATIONAL_STATUSES = [
  "non_operational",
  "planning_only",
  "agency_operational",
] as const;
export type OperationalStatus = (typeof OPERATIONAL_STATUSES)[number];

export const CONFIDENCE_CLASSES = ["low", "medium", "high"] as const;
export type ConfidenceClass = (typeof CONFIDENCE_CLASSES)[number];

export const DATA_STATES = ["ready", "stale", "blocked", "unavailable"] as const;
export type DataState = (typeof DATA_STATES)[number];

export const ACTION_CLASSES = ["A", "B", "C", "D", "E"] as const;
export type ActionClass = (typeof ACTION_CLASSES)[number];

export const ACTION_REASON_CODES = [
  "low_confidence",
  "low_priority_score",
  "life_safety_exposure",
  "critical_route_access",
  "essential_service_access",
  "resilience",
] as const;
export type ActionReasonCode = (typeof ACTION_REASON_CODES)[number];

export const PILOT_ROLES = [
  "public_viewer",
  "command_viewer",
  "analyst",
  "data_steward",
  "pilot_admin",
] as const;
export type PilotRole = (typeof PILOT_ROLES)[number];

export const ACCEPTANCE_RECEIPT_STATES = [
  "missing",
  "invalid",
  "expired",
  "accepted",
] as const;
export type AcceptanceReceiptState =
  (typeof ACCEPTANCE_RECEIPT_STATES)[number];

export const ROLE_VISIBILITIES = ["public", "command", "studio"] as const;
export type RoleVisibility = (typeof ROLE_VISIBILITIES)[number];

export const EVIDENCE_TYPES = ["modelled", "observed", "locally_confirmed"] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

export const EVIDENCE_GRANULARITIES = [
  "area_summary",
  "road_segment",
  "facility",
] as const;
export type EvidenceGranularity = (typeof EVIDENCE_GRANULARITIES)[number];

export const PERMITTED_USES = [
  "public_preparedness",
  "planning_only",
  "operational_authorized",
] as const;
export type PermittedUse = (typeof PERMITTED_USES)[number];

export const EVIDENCE_GATE_STATES = ["ready", "blocked", "not_applicable"] as const;
export type EvidenceGateState = (typeof EVIDENCE_GATE_STATES)[number];

export const FRESHNESS_STATES = ["current", "aging", "historical", "unknown"] as const;
export type FreshnessState = (typeof FRESHNESS_STATES)[number];

export const FRESHNESS_POLICY_VERSION = "source-freshness-v1" as const;

export const SOURCE_TEMPORAL_MEANINGS = [
  "observation_time",
  "valid_from",
  "publication_year",
  "extract_time",
  "generation_time",
  "unknown",
] as const;
export type SourceTemporalMeaning = (typeof SOURCE_TEMPORAL_MEANINGS)[number];

export const EVIDENCE_DECISIONS = ["not_evaluated", "passed", "failed", "blocked"] as const;
export type EvidenceDecision = (typeof EVIDENCE_DECISIONS)[number];

export const LAYER_FORMATS = ["geojson", "cog", "pmtiles"] as const;
export type LayerFormat = (typeof LAYER_FORMATS)[number];

export const MODEL_FAMILIES = [
  "deterministic_sar_baseline",
  "weak_label_logistic",
  "geoai",
] as const;
export type ModelFamily = (typeof MODEL_FAMILIES)[number];

export const MODEL_RUN_STATUSES = [
  "blocked",
  "prepared",
  "running",
  "completed",
  "failed",
] as const;
export type ModelRunStatus = (typeof MODEL_RUN_STATUSES)[number];

export const EVIDENCE_RESULTS = ["not_run", "passed", "failed"] as const;
export type EvidenceResult = (typeof EVIDENCE_RESULTS)[number];

export const GEOAI_VALIDATION_STATUSES = [
  "not_run",
  "passed",
  "failed",
  "blocked",
] as const;
export type GeoAIValidationStatus =
  (typeof GEOAI_VALIDATION_STATUSES)[number];

export const GEOAI_AGGREGATION_STATUSES = [
  "not_run",
  "passed",
  "report_only",
  "failed",
  "blocked",
] as const;
export type GeoAIAggregationStatus =
  (typeof GEOAI_AGGREGATION_STATUSES)[number];

export const PREPROCESSING_VALUE_DOMAINS = [
  "uint8_0_255",
  "float_0_1",
  "physical_units",
] as const;
export type PreprocessingValueDomain =
  (typeof PREPROCESSING_VALUE_DOMAINS)[number];

export const MODEL_RUN_V2_SCHEMA_VERSION = "2.0" as const;
export const MODEL_REGISTRY_ENTRY_SCHEMA_VERSION = "1.0" as const;

export const EVIDENCE_KINDS = [
  "satellite_observed_extent",
  "optical_corroboration",
  "susceptibility_forecast",
  "scenario_assumption",
  "external_algorithmic_baseline",
  "human_field_observation",
] as const;
export type EvidenceKind = (typeof EVIDENCE_KINDS)[number];

export const MODEL_BACKENDS = [
  "deterministic",
  "sklearn",
  "smp",
  "segformer",
  "terramind",
  "prithvi",
  "ensemble",
] as const;
export type ModelBackend = (typeof MODEL_BACKENDS)[number];

export const MODEL_RUN_V2_FAMILIES = [
  "deterministic_sar_baseline",
  "weak_label_logistic",
  "geoai_unet_fpn",
  "segformer",
  "terramind",
  "prithvi_optical",
  "ensemble",
] as const;
export type ModelRunV2Family = (typeof MODEL_RUN_V2_FAMILIES)[number];

export const MODEL_EVALUATION_STATUSES = [
  "blocked",
  "completed_report_only",
  "failed",
] as const;
export type ModelEvaluationStatus =
  (typeof MODEL_EVALUATION_STATUSES)[number];

export const OBSERVATION_ASSET_ROLES = [
  "flood_probability",
  "hard_extent",
  "validity_mask",
  "sensor_quality_mask",
  "model_uncertainty",
  "ood_score",
  "abstention_mask",
  "permanent_water_context",
  "preview",
  "stac_item",
] as const;
export type ObservationAssetRole =
  (typeof OBSERVATION_ASSET_ROLES)[number];

export const MODEL_REGISTRY_STATUSES = [
  "candidate",
  "shadow",
  "approved",
  "revoked",
  "expired",
  "blocked",
] as const;
export type ModelRegistryStatus =
  (typeof MODEL_REGISTRY_STATUSES)[number];

export const MODEL_PERMITTED_USES = [
  "report_only",
  "shadow_only",
  "decision_input",
] as const;
export type ModelPermittedUse = (typeof MODEL_PERMITTED_USES)[number];

export interface CommonMetadata {
  schema_version: typeof SCHEMA_VERSION;
  dataset_mode: DatasetMode;
  operational_status: OperationalStatus;
  /** RFC 3339 timestamp of the newest source observation represented. */
  source_timestamp: string;
  /** RFC 3339 timestamp at which this response was generated. */
  generated_at: string;
  confidence_class: ConfidenceClass;
  source_name: string;
  assumptions: string[];
  /** Always false for fixture_demo and candidate payloads. */
  official_warning: boolean;
  data_version: string;
  git_commit: string;
}

export interface StatusResponse extends CommonMetadata {
  evidence_context_id: string;
  evidence_package_id: string;
  study_area: string;
  data_state: DataState;
  message_th: string;
  message_en: string;
}

export interface RoadEvidence {
  at_risk_segments: number;
  bridge_count: number;
  summary: string;
}

export interface FacilityEvidence {
  facility_count: number;
  summary: string;
}

export interface ScenarioDelta {
  scenario_id: string;
  fpps_delta: number;
  access_loss_delta: number;
}

export interface AreaDecision extends CommonMetadata {
  evidence_context_id: string;
  area_id: string;
  area_name_th: string;
  area_name_en: string;
  fpps_0_100: number;
  action_class: ActionClass;
  action_reason_code: ActionReasonCode;
  top_reason: string;
  flood_likelihood_0_100: number;
  exposure_0_100: number;
  access_gap_0_100: number;
  road_criticality_0_100: number;
  vulnerability_context_0_100: number;
  people_losing_30_min_access: number;
  equity_gap_ratio: number | null;
  road_evidence?: RoadEvidence;
  facility_evidence?: FacilityEvidence;
  scenario_delta?: ScenarioDelta;
}

export interface LayerCatalogItem extends CommonMetadata {
  evidence_context_id: string;
  evidence_package_id: string;
  layer_id: string;
  title_th: string;
  title_en: string;
  role_visibility: RoleVisibility[];
  format: LayerFormat;
  url: string;
  data_state: DataState;
  model_run_id: string | null;
  evidence_state: EvidenceState;
  source_components: SourceComponent[];
  attribution: string[];
}

export interface EvidenceState {
  evidence_type: EvidenceType;
  granularity: EvidenceGranularity;
  confidence_class: ConfidenceClass;
  confidence_reason: string;
  permitted_use: PermittedUse;
  required_gate: string | null;
  gate_state: EvidenceGateState;
}

export interface SourceComponent {
  source_component_id: string;
  role: string;
  source_name: string;
  source_version: string | null;
  source_timestamp: string | null;
  last_checked_at: string | null;
  temporal_meaning: SourceTemporalMeaning;
  freshness: FreshnessState;
  freshness_policy_version: typeof FRESHNESS_POLICY_VERSION;
  freshness_as_of: string;
  attribution: string[];
}

export interface EvidenceContext {
  schema_version: typeof SCHEMA_VERSION;
  evidence_context_id: string;
  study_area_id: string;
  data_version: string;
  evidence_package_id: string;
  evidence_package_sha256: string;
  model_run_id: string | null;
  dataset_mode: DatasetMode;
  operational_status: OperationalStatus;
  official_warning: boolean;
  generated_at: string;
  source_components: SourceComponent[];
}

export interface PublicPreparednessArea {
  schema_version: typeof SCHEMA_VERSION;
  evidence_context_id: string;
  area_id: string;
  area_name_th: string;
  area_name_en: string;
  planning_priority_0_100: number;
  evidence_sufficiency: ConfidenceClass;
  recommendation_code: ActionReasonCode;
  source_timestamp: string;
  freshness: FreshnessState;
  current_conditions_confirmed: boolean;
}

export interface EvidenceRecord {
  schema_version: typeof SCHEMA_VERSION;
  evidence_record_id: string;
  evidence_context: EvidenceContext;
  evidence_scope: string;
  model_id: string | null;
  model_version: string | null;
  model_sha256: string | null;
  evaluation_sha256: string | null;
  decision: EvidenceDecision;
  decision_authority: string | null;
  decision_at: string | null;
  operational_authorized: boolean;
  blockers: string[];
  generated_at: string;
}

export interface ModelInputManifestRow {
  product_id: string;
  role: string;
  sha256: string;
  source_timestamp: string;
  processing_allowed: boolean;
}

export interface ModelPreprocessing {
  method: string;
  value_domain: PreprocessingValueDomain;
  sidecar_sha256: string | null;
  transforms: BandTransform[];
}

export interface BandTransform {
  name: string;
  physical_min: number;
  physical_max: number;
  units: string;
  description: string;
}

export interface SpatialPartition {
  spatial_group_id: string;
  split: "train" | "holdout";
  bounds: [number, number, number, number];
}

export interface ValidationMetrics {
  iou: number | null;
  f1_dice: number | null;
  precision: number | null;
  recall: number | null;
  area_error_ratio: number | null;
  brier_score: number | null;
  /** Equal-width-bin expected calibration error, or null when not evaluated. */
  expected_calibration_error: number | null;
}

export interface ModelRun extends CommonMetadata {
  run_id: string;
  study_area: string;
  model_family: ModelFamily;
  run_status: ModelRunStatus;
  geoai_version: string | null;
  geoai_commit: string | null;
  model_id: string | null;
  model_revision: string | null;
  model_sha256: string | null;
  architecture: string | null;
  encoder: string | null;
  encoder_weights: string | null;
  num_channels: number | null;
  channel_names: string[];
  preprocessing: ModelPreprocessing;
  input_manifest_rows: ModelInputManifestRow[];
  encoded_feature_sha256: string | null;
  reference_mask_sha256: string | null;
  prepared_tile_manifest_sha256: string | null;
  spatial_holdout_ids: string[];
  spatial_partitions: SpatialPartition[];
  reference_mask_id: string;
  reference_mask_status: string;
  target_crs: string;
  resolution: [number, number];
  bounds: [number, number, number, number];
  tile_size: number;
  overlap: number;
  stride: number;
  batch_size: number;
  device: string;
  flood_class_index: number;
  probability_threshold: number;
  /** Redacted workspace hint, never a private absolute path. */
  external_output_workspace: string;
  processing_scope: string;
  processing_allowed: boolean;
  can_feed_decision_layer: boolean;
  reason_blocked: string;
  validation_metrics: ValidationMetrics;
  error_categories: string[];
}

export interface CommonMetadataV2 {
  schema_version: typeof MODEL_RUN_V2_SCHEMA_VERSION;
  dataset_mode: DatasetMode;
  operational_status: OperationalStatus;
  source_timestamp: string;
  generated_at: string;
  confidence_class: ConfidenceClass;
  source_name: string;
  assumptions: string[];
  official_warning: false;
  data_version: string;
  git_commit: string;
}

export interface ModelRunV2Input {
  role: string;
  modality:
    | "sentinel_1_sar"
    | "sentinel_2_optical"
    | "terrain"
    | "hydrology"
    | "permanent_water"
    | "land_cover"
    | "rainfall"
    | "reference_mask"
    | "other_context";
  product_id: string;
  sha256: string;
  source_timestamp: string;
  processing_allowed: boolean;
}

export interface ModelRunV2 extends CommonMetadataV2 {
  run_id: string;
  study_area_id: string;
  event_id: string;
  evidence_kind: EvidenceKind;
  run_status: ModelRunStatus;
  model: {
    model_id: string | null;
    model_revision: string | null;
    model_family: ModelRunV2Family;
    backend: ModelBackend;
    architecture: string | null;
    encoder: string | null;
    encoder_weights: string | null;
    framework: string | null;
    framework_version: string | null;
    framework_commit: string | null;
    model_sha256: string | null;
  };
  input_manifest_rows: ModelRunV2Input[];
  feature_contract: {
    feature_schema_id: string;
    value_domain:
      | "encoded_uint8"
      | "normalized_float32"
      | "physical_float32";
    dtype: "uint8" | "float32";
    channel_count: number;
    channel_names: string[];
    preprocessing_sidecar_sha256: string;
    feature_stack_sha256: string;
  };
  target_contract: {
    task: "semantic_segmentation";
    class_schema_id: string;
    classes: Array<{
      index: number;
      name: string;
      training_role: "positive" | "negative" | "ignore";
    }>;
    positive_class_index: 1;
    ignore_index: 255;
    reference_mask_status:
      | "blocked"
      | "synthetic_fixture_only"
      | "qualified_expert_or_adjudicated"
      | "confirmed_for_model_purpose";
    label_release_sha256: string | null;
  };
  training_lineage: {
    input_manifest_sha256: string;
    training_dataset_manifest_sha256: string | null;
    label_release_sha256: string | null;
    prepared_tile_manifest_sha256: string | null;
    controlled_model_run_receipt_sha256: string | null;
    threshold_selection_receipt_sha256: string | null;
    calibration_receipt_sha256: string | null;
  };
  partition_contract: {
    partition_manifest_sha256: string | null;
    training_partition_sha256: string | null;
    calibration_partition_sha256: string | null;
    final_holdout_partition_sha256: string | null;
    train_ids: string[];
    calibration_ids: string[];
    final_holdout_ids: string[];
  };
  inference_contract: {
    target_crs: string;
    resolution: [number, number];
    bounds: [number, number, number, number];
    tile_size: number;
    overlap: number;
    stride: number;
    batch_size: number;
    device: string;
    probability_threshold: number;
  };
  processing_allowed: boolean;
  can_feed_decision_layer: false;
  reason_blocked: string;
}

export interface ModelEvaluationMetricsV2 {
  sample_count: number | null;
  true_positive: number | null;
  false_positive: number | null;
  false_negative: number | null;
  true_negative: number | null;
  iou: number | null;
  f1_dice: number | null;
  precision: number | null;
  recall: number | null;
  boundary_f1: number | null;
  signed_area_error_ratio: number | null;
  absolute_area_error_ratio: number | null;
  brier_score: number | null;
  negative_log_likelihood: number | null;
  expected_calibration_error: number | null;
}

export interface ModelEvaluationV2 extends CommonMetadataV2 {
  evaluation_id: string;
  experiment_id: string;
  study_area_id: string;
  event_ids: string[];
  model_run_id: string;
  model_id: string;
  model_sha256: string;
  model_run_manifest_sha256: string;
  controlled_result_receipt_sha256: string | null;
  evaluation_status: ModelEvaluationStatus;
  evaluation_scope: "not_evaluated" | "final_holdout";
  reference_evidence: {
    reference_mask_status:
      | "blocked"
      | "synthetic_fixture_only"
      | "qualified_expert_or_adjudicated"
      | "confirmed_for_model_purpose";
    reference_mask_sha256: string | null;
    label_release_sha256: string | null;
    reviewer_qualification_receipt_sha256: string | null;
  };
  partition_evidence: {
    partition_manifest_sha256: string | null;
    training_partition_sha256: string | null;
    calibration_partition_sha256: string | null;
    final_holdout_partition_sha256: string | null;
  };
  threshold_evidence: {
    threshold: number | null;
    threshold_selection_receipt_sha256: string | null;
    selection_scope:
      | "not_selected"
      | "verified_calibration_projection_only";
    final_holdout_evaluated_during_selection: boolean;
  };
  overall_metrics: ModelEvaluationMetricsV2;
  event_metrics: Array<{
    event_id: string;
    sample_count: number;
    iou: number;
    f1_dice: number;
    precision: number;
    recall: number;
    absolute_area_error_ratio: number;
    brier_score: number;
    expected_calibration_error: number;
  }>;
  error_strata: Array<{
    category: string;
    coverage_status: "measured" | "insufficient" | "absent";
    cell_count: number;
    false_positive_count: number;
    false_negative_count: number;
    precision: number | null;
    recall: number | null;
  }>;
  calibration: {
    status: "not_evaluated" | "evaluated" | "failed";
    method: string | null;
    reliability_asset_sha256: string | null;
  };
  selective_prediction: {
    status: "not_evaluated" | "evaluated" | "failed";
    risk_coverage_asset_sha256: string | null;
  };
  ood_evaluation: {
    status: "not_evaluated" | "passed" | "failed";
    method: string | null;
    threshold: number | null;
    score_asset_sha256: string | null;
  };
  downstream_impact: {
    status: "not_evaluated" | "evaluated" | "failed";
    population_absolute_error: number | null;
    critical_road_false_negative_count: number | null;
    access_classification_flip_count: number | null;
    equity_gap_absolute_error: number | null;
    fpps_mean_absolute_error: number | null;
    fpps_rank_correlation: number | null;
    action_class_flip_count: number | null;
    artifact_sha256: string | null;
  };
  runtime: {
    training_seconds: number | null;
    calibration_seconds: number | null;
    inference_seconds: number | null;
    total_seconds: number | null;
    peak_memory_mb: number | null;
    device: string | null;
    hardware_class: string | null;
  };
  processing_allowed: boolean;
  can_feed_decision_layer: false;
  reason_blocked: string;
}

export interface FloodObservationAssetV2 {
  role: ObservationAssetRole;
  relative_path: string;
  media_type: string;
  sha256: string;
  dtype: "uint8" | "float32" | "json" | "png";
  band_name: string | null;
  nodata: number | null;
  minimum: number | null;
  maximum: number | null;
}

export interface FloodObservationProductV2 extends CommonMetadataV2 {
  product_id: string;
  run_id: string;
  study_area_id: string;
  event_id: string;
  evidence_kind: EvidenceKind;
  source_manifest_sha256: string;
  model_run_manifest_sha256: string;
  model_sha256: string;
  evaluation_manifest_sha256: string;
  grid: {
    crs: string;
    resolution: [number, number];
    bounds: [number, number, number, number];
    width: number;
    height: number;
    transform: [number, number, number, number, number, number];
    nodata: number;
    grid_sha256: string;
  };
  assets: FloodObservationAssetV2[];
  valid_coverage_fraction: number;
  abstained_fraction: number;
  sensor_quality_status: "not_evaluated" | "passed" | "degraded" | "failed";
  ood_status: "not_evaluated" | "in_domain" | "out_of_distribution";
  review_required_reasons: string[];
  unknown_cell_policy: "preserve_nodata_and_abstention_never_fill_as_dry";
  counts_as_observed_evidence: boolean;
  processing_allowed: boolean;
  can_feed_decision_layer: false;
  reason_blocked: string;
}

export interface ModelRegistryEntryPayloadV1 {
  schema_version: typeof MODEL_REGISTRY_ENTRY_SCHEMA_VERSION;
  registry_entry_id: string;
  study_area_id: string;
  event_id: string;
  evidence_kind: EvidenceKind;
  source_bundle_sha256: string;
  model_run_id: string;
  model_id: string;
  model_sha256: string;
  model_run_manifest_sha256: string;
  evaluation_id: string;
  evaluation_manifest_sha256: string;
  controlled_result_receipt_sha256: string | null;
  product_id: string;
  product_manifest_sha256: string;
  promotion_acceptance_receipt_sha256: string | null;
  field_validation_receipt_sha256: string | null;
  agency_acceptance_receipt_sha256: string | null;
  dataset_mode: DatasetMode;
  operational_status: OperationalStatus;
  registry_status: ModelRegistryStatus;
  permitted_use: ModelPermittedUse;
  issued_at: string;
  valid_from: string;
  expires_at: string;
  official_warning: false;
  can_feed_decision_layer: boolean;
  reason_blocked: string;
}

export interface ModelRegistryEntryV1 {
  payload: ModelRegistryEntryPayloadV1;
  signature: {
    algorithm: "HMAC-SHA256";
    key_id: string;
    payload_sha256: string;
    value: string;
  };
}

export interface BilingualAcceptanceCriterion {
  criterion_id: string;
  required: boolean;
  status: "pending" | "accepted";
  text_th: string;
  text_en: string;
}

export interface PilotReadiness {
  schema_version: typeof SCHEMA_VERSION;
  operational_status: OperationalStatus;
  agency_operational_allowed: boolean;
  identity_state: "unconfigured" | "configured";
  acceptance_receipt_state: AcceptanceReceiptState;
  audit_state: "unconfigured" | "valid" | "invalid";
  retention_state: "unconfigured" | "configured";
  deployment_state:
    | "pilot_not_configured"
    | "pilot_ready_non_operational"
    | "degraded"
    | "accepted_for_agency_operation";
  acceptance_criteria: BilingualAcceptanceCriterion[];
  field_validation_protocol_version: "field-validation-v1";
  roles: PilotRole[];
  reason_blocked_th: string;
  reason_blocked_en: string;
}

export interface AcceptanceReceiptPayload {
  schema_version: typeof SCHEMA_VERSION;
  acceptance_id: string;
  study_area: string;
  dataset_mode: "official_input";
  data_version: string;
  artifact_manifest_sha256: string;
  source_timestamp: string;
  requested_operational_status: "agency_operational";
  acceptance_status: "accepted";
  acceptance_criteria_ids: string[];
  field_validation_receipt_sha256: string;
  field_validation_protocol_version: "field-validation-v1";
  issued_at: string;
  expires_at: string;
  issuer_subject: string;
}

export interface SignedAcceptanceReceipt {
  payload: AcceptanceReceiptPayload;
  signature: {
    algorithm: "HMAC-SHA256";
    key_id: string;
    payload_sha256: string;
    value: string;
  };
}

export interface FieldValidationReceipt {
  schema_version: typeof SCHEMA_VERSION;
  protocol_version: "field-validation-v1";
  receipt_id: string;
  dataset_mode: DatasetMode;
  operational_status: "non_operational" | "planning_only";
  source_timestamp: string;
  generated_at: string;
  confidence_class: ConfidenceClass;
  source_name: string;
  assumptions: string[];
  official_warning: false;
  git_commit: string;
  can_feed_decision_layer: false;
  study_area: string;
  event_id: string;
  data_version: string;
  observation_window: { start: string; end: string };
  evidence_hashes: {
    product_manifest_sha256: string | null;
    model_manifest_sha256: string | null;
    probability_raster_sha256: string | null;
    zonal_receipt_sha256: string | null;
    reporting_geometry_sha256: string | null;
    sampling_plan_sha256: string | null;
    holdout_geometry_sha256: string | null;
  };
  stratum_counts: Array<{
    stratum_id: string;
    observed: number;
    usable: number;
    excluded: number;
  }>;
  reviewer_calibration: {
    status: "passed" | "failed" | "not_evaluated";
    metric: string | null;
    score: number | null;
    threshold: number | null;
    evidence_sha256: string | null;
  };
  metrics: {
    iou: number | null;
    f1_dice: number | null;
    precision: number | null;
    recall: number | null;
    signed_area_error_ratio: number | null;
    absolute_area_error_ratio: number | null;
    brier_score: number | null;
    expected_calibration_error: number | null;
  };
  error_categories: Array<{ category: string; count: number }>;
  safety_incidents: number;
  stop_work_events: number;
  data_protection_confirmed: boolean;
  licensing_confirmed: boolean;
  decision_th: string;
  decision_en: string;
  issued_at: string;
  review_due_at: string;
  accountable_role_ids: string[];
  status: "accepted" | "rejected" | "incomplete";
}

export interface ProposalEvidenceArtifact {
  kind: string;
  /** Repository-relative or public artifact path; never a private absolute path. */
  relative_path: string;
  media_type: string;
  sha256: string;
}

export interface ProposalTestSuiteReceipt {
  name: string;
  command: string;
  result: EvidenceResult;
  passed: number;
  skipped: number;
}

export interface ProposalGeoAIProof {
  geoai_version: "0.41.1";
  feature_stack_id: string;
  preprocessing_id: string;
  input_manifest_sha256: string | null;
  output_probability_sha256: string | null;
  validation_status: GeoAIValidationStatus;
  aggregation_status: GeoAIAggregationStatus;
  processing_allowed: boolean;
  can_feed_decision_layer: boolean;
  reason_blocked: string;
}

export interface ProposalEvidenceManifest {
  schema_version: typeof SCHEMA_VERSION;
  generated_at: string;
  git_commit: string;
  dataset_mode: DatasetMode;
  operational_status: OperationalStatus;
  artifacts: ProposalEvidenceArtifact[];
  test_suites: ProposalTestSuiteReceipt[];
  geoai_proof: ProposalGeoAIProof;
}
