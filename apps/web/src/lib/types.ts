import type {
  AreaDecision,
  EvidenceContext,
  EvidenceRecord,
  FloodObservationProductV2,
  LayerCatalogItem,
  ModelEvaluationV2,
  ModelRegistryEntryV1,
  ModelRun,
  ModelRunV2,
  PilotReadiness,
  PublicPreparednessArea,
  RoleVisibility,
  StatusResponse,
} from "@floodguard/contracts";

export type Language = "th" | "en";
export type DataState = "loading" | "ready" | "stale" | "blocked" | "stale_offline" | "unavailable";
export type ScenarioId = "baseline" | "add_temporary_shelter" | "close_road";
export type StudyAreaId = "fixture_thailand_demo" | "mae_sai_candidate_v1";
export type ModelEvidenceState = "ready" | "blocked" | "unavailable";
export type QualifiedEvidenceStageState = "ready" | "blocked" | "absent";
export type QualifiedEvidenceStageId =
  | "engineering_foundation"
  | "qualified_thai_reference"
  | "reviewer_calibration"
  | "blind_review_adjudication"
  | "frozen_label_release";

export interface QualifiedEvidenceStage {
  stage_id: QualifiedEvidenceStageId;
  state: QualifiedEvidenceStageState;
  label_en: string;
  label_th: string;
  detail_en: string;
  detail_th: string;
}

export interface QualifiedEvidenceFoundation {
  schema_version: "floodguard.qualified-evidence-foundation.v1";
  foundation_id: "qualified-thai-reference-frozen-label-release-v1";
  study_area_id: "mae_sai_candidate_v1";
  /** Candidate-inspection/status-evidence time, not a flood-observation time. */
  source_timestamp: string;
  generated_at: string;
  confidence_class: "low";
  status: "blocked";
  /** SHA-256 of canonical JSON after omitting this field. */
  canonical_sha256: string;
  authoritative_receipt: false;
  reference_candidate_binding: {
    manifest_schema: "floodguard.reference_candidate_manifest.v1";
    product_id: "AIT-VAP001-TH";
    provider: "Asian Institute of Technology via Sentinel Asia";
    observation_start_utc: string;
    observation_end_utc: string;
    manifest_canonical_sha256: string;
    manifest_file_sha256: string;
    source_archive_sha256: string;
    qualification_status: "blocked_external_permission_and_scientific_review";
    processing_allowed: false;
  };
  stages: QualifiedEvidenceStage[];
  permissions: {
    source_processing_allowed: boolean;
    source_processing_scope_en: string;
    source_processing_scope_th: string;
    experiment_processing_allowed: boolean;
    qualified_reference_use_allowed: boolean;
    training_allowed: boolean;
    evaluation_allowed: boolean;
    decision_layer_allowed: boolean;
    operational_use_allowed: boolean;
  };
  blockers: Array<{
    code: string;
    detail_en: string;
    detail_th: string;
  }>;
  next_actions: Array<{
    sequence: number;
    action_en: string;
    action_th: string;
  }>;
  assumptions: Array<{
    assumption_en: string;
    assumption_th: string;
  }>;
  safety: {
    official_warning: false;
    operational_authorized: false;
    can_feed_decision_layer: false;
    can_feed_fpps: false;
    can_assign_action_class: false;
  };
}

/**
 * Studio consumes the canonical signed registry envelope and v2 evidence
 * records. The competition bundle includes only a browser-safe, blocked
 * candidate; public-production removes these arrays entirely.
 */
export type StudioModelRegistryEntry = ModelRegistryEntryV1;
export type StudioModelEvaluationRecord = ModelEvaluationV2;
export type StudioFloodObservationProductRecord = FloodObservationProductV2;

export interface FloodGuardDataOptions {
  studyArea: StudyAreaId;
  role: RoleVisibility;
  /** Exact context requested by a deep link; mismatch must fail closed. */
  evidenceContextId?: string;
}

export interface ScenarioResult {
  people_losing_30_min_access: number;
  equity_gap_ratio: number | null;
  delta: number;
}

export interface AreaRecord extends AreaDecision {
  total_population: number;
  people_losing_30_min_access: number;
  equity_gap_ratio: number | null;
  scenario_results: Record<ScenarioId, ScenarioResult>;
  candidate_evidence?: {
    mean_flood_probability_0_1: number;
    p90_flood_probability_0_1: number;
    binary_flood_share_0_1: number;
    facility_count: number;
    road_count: number;
    bridge_count: number;
    worldpop_bbox_coverage_rate: number;
    road_snap_population_coverage_rate: number;
    dem_population_coverage_rate: number;
    boundary_version: string;
    boundary_valid_on: string;
    reference_status: string;
    processing_scope: string;
  };
}

export interface ReadinessRow {
  check_id: string;
  source: string;
  status: "ready" | "stale" | "blocked" | "unavailable";
  severity: "critical" | "high" | "medium" | "low";
  reason_blocked: string;
}

export interface Hotline {
  number: string;
  label_th: string;
  label_en: string;
  href: `tel:${string}`;
  source_url: string;
}

export interface ShelterRecord {
  facility_id: string;
  name_th: string;
  name_en: string;
  area_id: string;
  capacity_status: "confirmed" | "unconfirmed";
  route_status: "preparedness_rehearsal_only" | "unavailable";
  source: string;
}

export interface ErrorCategory {
  category: string;
  status: "not_evaluated" | "reviewed";
  note: string;
}

export interface FeatureGeometry {
  type: "Polygon" | "MultiPolygon" | "LineString" | "MultiLineString" | "Point";
  coordinates: unknown;
}

export interface GeoFeature {
  type: "Feature";
  properties: Record<string, string | number | boolean | null>;
  geometry: FeatureGeometry;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  name: string;
  features: GeoFeature[];
}

export interface OfflineBundle {
  evidence_context?: EvidenceContext;
  evidence_record?: EvidenceRecord;
  /** Studio-only P0 evidence status. Public projections omit this object. */
  qualified_evidence_foundation?: QualifiedEvidenceFoundation;
  public_areas?: PublicPreparednessArea[];
  status: StatusResponse & {
    study_area: string;
    message_th: string;
    message_en: string;
  };
  areas: AreaRecord[];
  layers: LayerCatalogItem[];
  readiness: ReadinessRow[];
  model_runs: ModelRun[];
  /** Exact v2 manifests referenced by the Studio-only model registry chain. */
  model_runs_v2?: ModelRunV2[];
  model_registry?: StudioModelRegistryEntry[];
  model_evaluations?: StudioModelEvaluationRecord[];
  observation_products?: StudioFloodObservationProductRecord[];
  hotlines: Hotline[];
  shelters: ShelterRecord[];
  error_categories: ErrorCategory[];
  pilot_readiness: PilotReadiness;
}

export interface FloodGuardData extends OfflineBundle {
  model_registry: StudioModelRegistryEntry[];
  model_evaluations: StudioModelEvaluationRecord[];
  observation_products: StudioFloodObservationProductRecord[];
  role: RoleVisibility;
  evidenceContext: EvidenceContext;
  evidenceRecord: EvidenceRecord | null;
  publicAreas: PublicPreparednessArea[];
  dataState: DataState;
  dataOrigin: "api" | "cached_api" | "offline_bundle";
  scenarioState: "ready" | "unavailable";
  availableScenarios: ScenarioId[];
  apiBase?: string;
  snapshotCachedAt?: string;
  areaFeatures: FeatureCollection;
  roadFeatures: FeatureCollection;
  contextFeatures: FeatureCollection;
  facilityFeatures: FeatureCollection;
  accessFeatures: FeatureCollection;
  modelEvidenceState: ModelEvidenceState;
  modelEvidenceReason: string;
  fallbackReason?: string;
  degradedReason?: string;
}

/** Deliberately reduced public-surface contract; staff records cannot enter this graph. */
export interface PublicFloodGuardData {
  role: "public";
  status: OfflineBundle["status"];
  evidenceContext: EvidenceContext;
  evidenceRecord: EvidenceRecord | null;
  publicAreas: PublicPreparednessArea[];
  layers: LayerCatalogItem[];
  hotlines: Hotline[];
  shelters: ShelterRecord[];
  areaFeatures: FeatureCollection;
  dataState: DataState;
  dataOrigin: "api" | "offline_bundle";
  apiBase?: string;
  fallbackReason?: string;
  degradedReason?: string;
}
