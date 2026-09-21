import type { FinalsAnalysis } from "./finals-analysis";

/** A research decision brief keeps scenario evidence separate from accepted action. */
export interface BriefAccess {
  modelled_population: number;
  unknown_access_population: number;
  connected_without_route_population: number;
  over_30_minutes_population: number;
  within_30_minutes_population: number;
}

export interface BriefIntervention {
  id: string;
  scenario_id: string;
  kind: "add_destination" | "close_edge" | "remove_destination";
  gaining_30_min_access: number;
  losing_30_min_access: number;
  slower_population: number;
  faster_population: number;
  comparable_population: number;
  mean_travel_time_delta_minutes: number | null;
  result: "threshold_change" | "travel_time_only" | "no_measured_change";
  observed: false;
  selection_method?: string;
}

export interface BriefReportingUnit {
  id: string;
  name: string;
  name_th: string;
  scope: "full_unit" | "partial_unit";
  unit_coverage_fraction: number;
  intersection_area_km2: number;
  population_context: BriefAccess | null;
  affected_population: null;
  fpps: null;
  action_class: null;
  interventions: BriefIntervention[];
}

export interface DecisionBrief {
  schema_version: "1.0";
  generated_at: string;
  aoi_id: string;
  event_id: string;
  status: "scenario_only" | "coverage_only";
  priority: { status: "unavailable"; fpps: null; action_class: null; reason: string };
  affected_population: null;
  population_reference_year: number | null;
  population_role: "modelled_residential_context";
  access: BriefAccess | null;
  reporting: {
    status: "available" | "unavailable";
    source_url: string | null;
    reference_date: string | null;
    coverage_fraction: number | null;
    unassigned_modelled_population: number | null;
    ambiguous_population_cells: number;
    scope: string;
    units: BriefReportingUnit[];
  };
  interventions: BriefIntervention[];
  evidence_notes: { topic: string; status: string; summary: string; source_urls: string[] }[];
  capacity_experiments: { id: string; title: string; participation_fraction: number | null; residential_population: number | null; demand_basis: string | null; actual_evacuation_demand: null; actual_available_capacity: null; unknown_capacity: number | null; assumed_demand: number | null; assigned: number | null; capacity_limited: number | null; unreachable: number | null; coverage_excluded: number | null }[];
  capacity_status: "assumed_demand_and_capacity_only";
  demographic_equity_status: "unavailable";
  coverage: { connected_components: number | null; connected_destinations: number | null; candidate_destinations: number | null };
  drivers: string[];
  next_actions: { id: string; order: number; action: string; reason: string }[];
  limitations: string[];
  finals_analysis?: FinalsAnalysis;
}
