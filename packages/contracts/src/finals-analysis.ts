/** Public, precomputed service experiments; no accepted event score is implied. */
export type FinalsServiceId = "hospital" | "primary_care" | "pharmacy" | "shelter";
export type FinalsTravelMode = "walking" | "modelled_vehicle";

export interface FinalsBaseline {
  modelled_population: number;
  unknown_access_population: number;
  connected_without_route_population: number;
  within_15_minutes_population: number;
  within_30_minutes_population: number;
  within_60_minutes_population: number;
  median_minutes: number | null;
  p90_minutes: number | null;
  max_minutes: number | null;
}

export interface FinalsIntervention {
  id: string;
  kind: "add_destination" | "close_edge" | "remove_destination";
  target_id: string;
  target_label: string;
  selection_method: string;
  gaining_15_min_access: number;
  losing_15_min_access: number;
  gaining_30_min_access: number;
  losing_30_min_access: number;
  gaining_60_min_access: number;
  losing_60_min_access: number;
  slower_population: number;
  faster_population: number;
  newly_reachable_population: number;
  newly_unreachable_population: number;
  comparable_population: number;
  mean_travel_time_delta_minutes: number | null;
  p90_delta_minutes: number | null;
  max_delta_minutes: number | null;
  net_person_minutes: number;
}

export interface FinalsVariant {
  id: string;
  travel_mode: FinalsTravelMode;
  speed_factor: number;
  context_sha256: string;
  baseline: FinalsBaseline;
  interventions: FinalsIntervention[];
}

export interface FinalsRoute {
  status: "available" | "unavailable";
  reason: string;
  destination_id: string | null;
  destination_name: string | null;
  total_minutes: number | null;
  network_minutes: number | null;
  connector_minutes: number | null;
  distance_m: number | null;
  edge_ids: string[];
  coordinates: [number, number][];
  connectors: [number, number][][];
}

export interface FinalsOrigin {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
  source_url: string;
  geometry_role: string;
  location_status: string;
}

export interface FinalsRouteComparison {
  id: string;
  origin_id: string;
  service_type: FinalsServiceId;
  travel_mode: FinalsTravelMode;
  scenario_kind: "close_edge" | "remove_destination";
  changed_ids: string[];
  selection_method: string;
  context_sha256: string;
  baseline: FinalsRoute;
  after: FinalsRoute;
  delta_minutes: number | null;
}

export interface FinalsRoutes {
  status: "available" | "unavailable";
  origins: FinalsOrigin[];
  comparisons: FinalsRouteComparison[];
  limitations: string[];
}

export interface FinalsAnalysis {
  schema_version: "1.0";
  generated_at: string;
  status: "scenario_only";
  question: string;
  primary_service: FinalsServiceId;
  analysis_sha256: string;
  scope: {
    jurisdiction: string;
    population_year: number;
    boundary_reference_date: string;
    osm_retrieved_at: string;
    study_population: number;
    in_scope_population: number;
    excluded_population: number;
  };
  timeline: { id: string; title: string; start: string | null; end: string | null; role: string; source_url: string; limitations: string[] }[];
  services: { id: FinalsServiceId; status: "available" | "unavailable"; facilities: number; reason: string; variants: FinalsVariant[] }[];
  facility_review: { id: string; name: string; service_type: string; geometry_role: string; eligible: boolean; event_availability: "unknown"; actual_capacity: null; source_url: string }[];
  routes?: FinalsRoutes;
  topology_review?: { reviewed_candidates: number; accepted_connections: number; summary: string };
  focus_briefs?: { id: string; name: string; name_th: string; unit_coverage_fraction: number; modelled_population: number; priority: "verification"; service_type: string; travel_mode: "walking"; main_drivers: string[]; useful_intervention: string; uncertainty: string[] }[];
  capacity: {
    status: "unavailable" | "scenario_only";
    site_id: string | null;
    linked_access_intervention_id: string | null;
    linked_service?: FinalsServiceId | null;
    linked_variant_id?: string | null;
    demand_basis: "residential_participation";
    actual_evacuation_demand: null;
    actual_available_capacity: null;
    experiments: { participation_fraction: number; places: number; assumed_demand: number; assigned: number; capacity_limited: number; unreachable: number; coverage_excluded: number }[];
    assumptions: string[];
  };
  limitations: string[];
}
