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

export const PREPROCESSING_VALUE_DOMAINS = [
  "uint8_0_255",
  "float_0_1",
  "physical_units",
] as const;
export type PreprocessingValueDomain =
  (typeof PREPROCESSING_VALUE_DOMAINS)[number];

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
  area_id: string;
  area_name_th: string;
  area_name_en: string;
  fpps_0_100: number;
  action_class: ActionClass;
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
  layer_id: string;
  title_th: string;
  title_en: string;
  role_visibility: RoleVisibility[];
  format: LayerFormat;
  url: string;
  data_state: DataState;
  model_run_id: string | null;
  attribution: string[];
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
