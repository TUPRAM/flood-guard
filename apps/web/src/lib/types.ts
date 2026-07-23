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
