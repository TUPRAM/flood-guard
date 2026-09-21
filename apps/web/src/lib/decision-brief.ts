import type { DecisionBrief } from "@floodguard/contracts";

const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const positive = (v: unknown): v is number => num(v) && v >= 0;
const nullableNumber = (v: unknown) => v === null || positive(v);
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const texts = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
const fraction = (v: unknown) => positive(v) && v <= 1;
function access(v: unknown): boolean {
  if (v === null) return true;
  if (!record(v) || !["modelled_population", "unknown_access_population", "connected_without_route_population", "over_30_minutes_population", "within_30_minutes_population"].every((key) => positive(v[key]))) return false;
  return Math.abs((v.modelled_population as number) - ((v.unknown_access_population as number) + (v.connected_without_route_population as number) + (v.over_30_minutes_population as number) + (v.within_30_minutes_population as number))) <= .05;
}
function interventions(v: unknown): boolean {
  return Array.isArray(v) && new Set(v.map((row) => record(row) ? row.id : null)).size === v.length && v.every((row) => record(row) && text(row.id) && text(row.scenario_id)
    && ["add_destination", "close_edge", "remove_destination"].includes(String(row.kind)) && row.observed === false
    && ["gaining_30_min_access", "losing_30_min_access", "slower_population", "faster_population", "comparable_population"].every((key) => positive(row[key]))
    && (row.mean_travel_time_delta_minutes === null || num(row.mean_travel_time_delta_minutes))
    && ["threshold_change", "travel_time_only", "no_measured_change"].includes(String(row.result))
    && (row.selection_method === undefined || text(row.selection_method)));
}

/** Reject mixed identities and unsupported observed action/exposure claims. */
export function parseDecisionBrief(value: unknown, aoi: string, event: string, generatedAt: string): DecisionBrief {
  const fail = () => { throw new Error("Invalid decision brief: identity, population partition or evidence boundary differs from its package."); };
  if (!record(value)) return fail();
  const p = value.priority; const r = value.reporting; const c = value.coverage;
  if (value.schema_version !== "1.0" || value.aoi_id !== aoi || value.event_id !== event || value.generated_at !== generatedAt
    || !["scenario_only", "coverage_only"].includes(String(value.status)) || value.affected_population !== null
    || value.population_role !== "modelled_residential_context" || !(value.population_reference_year === null || (positive(value.population_reference_year) && Number.isInteger(value.population_reference_year)))
    || !record(p) || p.status !== "unavailable" || p.fpps !== null || p.action_class !== null || !text(p.reason)
    || !access(value.access) || !interventions(value.interventions)
    || value.capacity_status !== "assumed_demand_and_capacity_only" || value.demographic_equity_status !== "unavailable"
    || !record(c) || !["connected_components", "connected_destinations", "candidate_destinations"].every((key) => nullableNumber(c[key]))
    || !Array.isArray(value.evidence_notes) || !value.evidence_notes.every((row) => record(row) && text(row.topic) && text(row.status) && text(row.summary) && texts(row.source_urls) && row.source_urls.every((url) => /^https?:\/\//.test(url)))
    || !Array.isArray(value.capacity_experiments) || !value.capacity_experiments.every((row) => record(row) && text(row.id) && text(row.title) && (row.participation_fraction === null || fraction(row.participation_fraction)) && ["assumed_demand", "assigned", "capacity_limited", "unreachable", "coverage_excluded", "residential_population", "unknown_capacity"].every((key) => nullableNumber(row[key])) && row.actual_evacuation_demand === null && row.actual_available_capacity === null && (row.demand_basis === null || text(row.demand_basis)))
    || !texts(value.drivers) || !texts(value.limitations) || !Array.isArray(value.next_actions)
    || !value.next_actions.every((row) => record(row) && text(row.id) && positive(row.order) && text(row.action) && text(row.reason))
    || !record(r) || !["available", "unavailable"].includes(String(r.status)) || !text(r.scope)
    || !(r.source_url === null || (text(r.source_url) && /^https?:\/\//.test(r.source_url)))
    || !(r.reference_date === null || text(r.reference_date)) || !(r.coverage_fraction === null || fraction(r.coverage_fraction))
    || !nullableNumber(r.unassigned_modelled_population) || !positive(r.ambiguous_population_cells) || !Array.isArray(r.units)) return fail();
  if (new Set(r.units.map((row) => record(row) ? row.id : null)).size !== r.units.length
    || !r.units.every((row) => record(row) && text(row.id) && text(row.name) && text(row.name_th)
      && ["full_unit", "partial_unit"].includes(String(row.scope)) && fraction(row.unit_coverage_fraction) && positive(row.intersection_area_km2)
      && access(row.population_context) && row.affected_population === null && row.fpps === null && row.action_class === null && interventions(row.interventions))) return fail();
  return value as unknown as DecisionBrief;
}
