/** Public study projections are independent of the operational evidence context. */
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type StudyArm = "sar" | "context";
export type StudyModel = "random_forest" | "xgboost" | "unet" | "vh_otsu";
export type StudyRole = "train" | "tune" | "calibration" | "selection" | "test";

export interface StudySafety {
  aggregation_status: "report_only";
  operational_status: "non_operational";
  can_feed_decision_layer: false;
  official_warning: false;
  confidence: string;
}

export interface StudyAsset {
  href: string;
  sha256: string;
  bytes: number;
  label: string;
  media_type: "application/json";
  source_sha256: string | null;
  transformation: string;
}

export interface StudyReceipt {
  source_path: string;
  sha256: string;
  bytes: number;
}

export interface StudyMetrics {
  iou: number | null;
  f1_dice: number | null;
  precision: number | null;
  recall: number | null;
  brier: number | null;
  ece: number | null;
  error_rate: number | null;
  n_pixels: number;
  n_reference_positive: number;
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
  reliability: Array<{ bin_lo: number; bin_hi: number; n: number; mean_predicted: number | null; observed_frequency: number | null }>;
}

export interface StudyScore {
  full_valid: StudyMetrics;
  selective: StudyMetrics;
  coverage: number;
  n_valid_pixels: number;
}

export interface StudyEvent {
  event_id: string;
  role: StudyRole;
  country: string | null;
  country_source: string;
  bbox: [number, number, number, number];
  centroid_lon_lat: [number, number];
  n_chips: number;
  scene_ids: string[];
  source_timestamps: string[];
  source_start: string;
  source_end: string;
}

export interface StudyRoleSummary {
  role: StudyRole;
  n_events: number;
  n_chips: number;
  event_ids: string[];
  purpose: string;
}

export interface StudySource {
  id: string;
  name: string;
  version: string;
  purpose: string;
  source_period: string;
  license: string;
  attribution: string;
  links: Array<{ label: string; href: string }>;
  limitations: string[];
}

export interface BenchmarkSummary {
  id: string;
  arm: StudyArm;
  model: StudyModel;
  dataset: string;
  source_timestamp: string;
  processed_utc: string;
  inventory_chips: number;
  supported_chips: number;
  invalid_chips: number;
  n_test_events: number;
  raw: StudyScore;
  calibrated: StudyScore;
  per_event: Record<string, { raw: StudyScore; calibrated: StudyScore }>;
  event_macro_iou: { raw: number; calibrated: number; n_events: number; confidence_interval: "not_estimated" };
  combined_screening: {
    coverage_of_original_valid_pixels: number;
    n_accepted_pixels: number;
    n_context_vetoed: number;
    n_original_valid_pixels: number;
    metrics_on_accepted_pixels: StudyMetrics;
  } | null;
  calibration: JsonObject | null;
  abstention: JsonObject | null;
  source: StudyReceipt;
  detail: StudyAsset;
  download: StudyAsset;
}

export interface StudySummary extends StudySafety {
  schema_version: "floodguard.study-summary.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  title: string;
  dataset: string;
  data_mode: "public_benchmark_report_projection";
  source_timestamp: string;
  processed_utc: string;
  partition_frozen_utc: string;
  counts: { chips: number; events: number; scenes: number; files: number; download_bytes: number };
  events: StudyEvent[];
  roles: StudyRoleSummary[];
  partition: JsonObject;
  provenance: StudyReceipt[];
  benchmarks: BenchmarkSummary[];
  rtc: StudyAsset;
  mae_sai: StudyAsset;
  geography: StudyAsset | null;
  visuals: StudyAsset | null;
  sources: StudySource[];
  assumptions: string[];
  limitations: string[];
  findings: JsonObject[];
  downloads: StudyAsset[];
}

export interface StudyTraining {
  feature_names: string[];
  feature_units: Record<string, string>;
  checkpoint: StudyReceipt | null;
  feature_manifest: StudyReceipt | null;
  fit: JsonObject;
  sampling: JsonObject | null;
  seed: number | null;
  download: StudyAsset | null;
}

export interface StudyModelDetail extends StudySafety {
  schema_version: "floodguard.study-model.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  benchmark: Omit<BenchmarkSummary, "detail">;
  training: StudyTraining | null;
  assumptions: string[];
  risk_coverage_curve: Array<{ confidence_cutoff: number; coverage: number; error_rate: number | null }>;
  tree_shap: { method: string; n_samples: number; role: string; feature_names: string[]; mean_absolute_contribution: number[]; feature_units: Record<string, string>; assumptions: string[] } | null;
  per_chip: JsonObject[];
}

export interface RtcArm {
  arm: StudyArm;
  common_valid_pixels: number;
  n_paired_test_chips: number;
  n_excluded_chips: number;
  n_paired_events: number;
  n_full_test_chips: number;
  pooled: Record<string, { raw: StudyScore; calibrated?: StudyScore }>;
  per_event: Record<string, Record<string, { raw: StudyScore; calibrated?: StudyScore }>>;
  assumptions: string[];
  source_timestamp: string;
  source: StudyReceipt;
  download: StudyAsset;
}

export interface RtcReport extends StudySafety {
  schema_version: "floodguard.study-rtc.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  source_timestamp: string;
  arms: RtcArm[];
  assumptions: string[];
  acquisition: JsonObject;
}

export interface MaeSaiModelRecord {
  id: string;
  arm: StudyArm;
  model: Exclude<StudyModel, "vh_otsu">;
  source_timestamp: string;
  processed_utc: string;
  valid_pixels: number;
  accepted_pixels: number;
  accepted_fraction: number;
  accuracy_status: "unavailable_no_qualified_Thai_reference";
  metrics: null;
  grid: JsonObject;
  calibration: JsonObject;
  abstention_policy: JsonObject;
  context_screening: JsonObject;
  layers: StudyReceipt;
  benchmark_sha256: string;
  checkpoint_sha256: string;
  source: StudyReceipt;
  download: StudyAsset;
}

export interface MaeSaiReport extends StudySafety {
  schema_version: "floodguard.study-mae-sai.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  source_timestamp: string;
  records: MaeSaiModelRecord[];
  bands: string[];
  accuracy_status: "unavailable_no_qualified_Thai_reference";
  metrics: null;
  source_pair: JsonObject;
  assumptions: string[];
}

export interface StudyManifest extends StudySafety {
  schema_version: "floodguard.study-manifest.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  source_timestamp: string;
  summary: StudyAsset;
  assets: StudyAsset[];
}

export interface StudyGeography extends StudySafety {
  schema_version: "floodguard.study-geography.v1";
  study_id: "c2s-ms-20260915";
  revision: "r1";
  source_timestamp: string;
  source_url: string;
  source_sha256: string;
  source_bytes: number;
  license: string;
  license_url: string;
  features: Array<{ name: string; path: string }>;
  event_countries: Record<string, string>;
  assumptions: string[];
}
