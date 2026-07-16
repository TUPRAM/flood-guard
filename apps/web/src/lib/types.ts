import type {
  AreaDecision,
  LayerCatalogItem,
  ModelRun,
  StatusResponse,
} from "@floodguard/contracts";

export type Language = "th" | "en";
export type DataState = "loading" | "ready" | "stale" | "blocked" | "stale_offline" | "unavailable";
export type ScenarioId = "baseline" | "add_temporary_shelter" | "close_road";

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
  type: "Polygon" | "LineString" | "Point";
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
  status: StatusResponse & {
    study_area: string;
    message_th: string;
    message_en: string;
  };
  areas: AreaRecord[];
  layers: LayerCatalogItem[];
  readiness: ReadinessRow[];
  model_runs: ModelRun[];
  hotlines: Hotline[];
  shelters: ShelterRecord[];
  error_categories: ErrorCategory[];
}

export interface FloodGuardData extends OfflineBundle {
  dataState: DataState;
  dataOrigin: "api" | "cached_api" | "offline_bundle";
  scenarioState: "ready" | "unavailable";
  apiBase?: string;
  snapshotCachedAt?: string;
  areaFeatures: FeatureCollection;
  roadFeatures: FeatureCollection;
  fallbackReason?: string;
  degradedReason?: string;
}
