import type { FinalsAnalysis } from "@floodguard/contracts";

const record = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nonnegative = (v: unknown): v is number => number(v) && v >= 0;
const count = (v: unknown): v is number => nonnegative(v) && Number.isInteger(v);
const fraction = (v: unknown): v is number => nonnegative(v) && v <= 1;
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text);
const url = (v: unknown): v is string => text(v) && /^https?:\/\//.test(v);
const nullableNumber = (v: unknown) => v === null || number(v);
const nullableText = (v: unknown) => v === null || text(v);
const hash = (v: unknown) => text(v) && /^[a-f0-9]{64}$/.test(v);
const services = ["hospital", "primary_care", "pharmacy", "shelter"];
const unique = (rows: unknown[]) => new Set(rows.map((row) => record(row) ? row.id : undefined)).size === rows.length;
const almost = (a: number, b: number) => Math.abs(a - b) <= .05;
const coordinate = (v: unknown) => Array.isArray(v) && v.length === 2 && number(v[0]) && number(v[1]) && Math.abs(v[0]) <= 180 && Math.abs(v[1]) <= 90;

function validRoute(v: unknown): boolean {
  if (!record(v) || !["available", "unavailable"].includes(String(v.status)) || !text(v.reason) || !nullableText(v.destination_id) || !nullableText(v.destination_name)
    || !["total_minutes", "network_minutes", "connector_minutes", "distance_m"].every((key) => v[key] === null || nonnegative(v[key]))
    || !strings(v.edge_ids) || !Array.isArray(v.coordinates) || !v.coordinates.every(coordinate)
    || !Array.isArray(v.connectors) || !v.connectors.every((line) => Array.isArray(line) && line.length === 2 && line.every(coordinate))) return false;
  if (v.status === "unavailable") return v.destination_id === null && v.destination_name === null && ["total_minutes", "network_minutes", "connector_minutes", "distance_m"].every((key) => v[key] === null) && !v.edge_ids.length && !v.coordinates.length && !v.connectors.length;
  return text(v.destination_id) && text(v.destination_name) && ["total_minutes", "network_minutes", "connector_minutes", "distance_m"].every((key) => nonnegative(v[key]))
    && v.coordinates.length === v.edge_ids.length + 1 && v.connectors.length === 2
    && almost(v.total_minutes as number, (v.network_minutes as number) + (v.connector_minutes as number));
}

function validRoutes(value: unknown): boolean {
  if (!record(value) || !["available", "unavailable"].includes(String(value.status)) || !strings(value.limitations)
    || !Array.isArray(value.origins) || !unique(value.origins) || !value.origins.every((row) => record(row)
      && ["id", "name", "geometry_role", "location_status"].every((key) => text(row[key])) && coordinate([row.longitude, row.latitude]) && url(row.source_url))
    || !Array.isArray(value.comparisons) || !unique(value.comparisons)) return false;
  if (value.status === "unavailable") return !value.origins.length && !value.comparisons.length;
  if (!value.origins.length) return false;
  const originIds = new Set(value.origins.map((row) => (row as Record<string, unknown>).id));
  return value.comparisons.every((row) => record(row) && text(row.id) && originIds.has(row.origin_id) && services.includes(String(row.service_type))
    && ["walking", "modelled_vehicle"].includes(String(row.travel_mode)) && ["close_edge", "remove_destination"].includes(String(row.scenario_kind))
    && strings(row.changed_ids) && text(row.selection_method) && hash(row.context_sha256) && validRoute(row.baseline) && validRoute(row.after)
    && nullableNumber(row.delta_minutes) && (record(row.baseline) && record(row.after)
      && (row.baseline.status === "available" && row.after.status === "available"
        ? number(row.delta_minutes) && almost(row.delta_minutes, (row.after.total_minutes as number) - (row.baseline.total_minutes as number))
        : row.delta_minutes === null)));
}

function validBaseline(v: unknown, population: number): boolean {
  if (!record(v) || !["modelled_population", "unknown_access_population", "connected_without_route_population", "within_15_minutes_population", "within_30_minutes_population", "within_60_minutes_population"].every((key) => nonnegative(v[key]))
    || !["median_minutes", "p90_minutes", "max_minutes"].every((key) => v[key] === null || nonnegative(v[key]))) return false;
  const total = v.modelled_population as number;
  const finite = total - (v.unknown_access_population as number) - (v.connected_without_route_population as number);
  return almost(total, population) && finite >= -.05
    && (v.within_15_minutes_population as number) <= (v.within_30_minutes_population as number) + .001
    && (v.within_30_minutes_population as number) <= (v.within_60_minutes_population as number) + .001
    && (v.within_60_minutes_population as number) <= finite + .05
    && (v.median_minutes === null ? v.p90_minutes === null && v.max_minutes === null
      : number(v.p90_minutes) && number(v.max_minutes) && (v.median_minutes as number) <= v.p90_minutes && v.p90_minutes <= v.max_minutes);
}

function validIntervention(v: unknown, total: number): boolean {
  return record(v) && ["id", "target_id", "target_label", "selection_method"].every((key) => text(v[key]))
    && ["add_destination", "close_edge", "remove_destination"].includes(String(v.kind))
    && ["gaining_15_min_access", "losing_15_min_access", "gaining_30_min_access", "losing_30_min_access", "gaining_60_min_access", "losing_60_min_access", "slower_population", "faster_population", "newly_reachable_population", "newly_unreachable_population", "comparable_population"].every((key) => nonnegative(v[key]) && v[key] <= total + .05)
    && ["mean_travel_time_delta_minutes", "p90_delta_minutes", "max_delta_minutes"].every((key) => nullableNumber(v[key]))
    && number(v.net_person_minutes)
    && (v.slower_population as number) + (v.faster_population as number) <= (v.comparable_population as number) + .05;
}

/** Verify the experiment boundary, service separation, population accounts and frozen shortlist. */
export function parseFinalsAnalysis(value: unknown, generatedAt: string): FinalsAnalysis {
  const fail = () => { throw new Error("Invalid finals analysis: service, scope, capacity or scenario identity differs from its evidence package."); };
  if (!record(value) || value.schema_version !== "1.0" || value.status !== "scenario_only" || value.generated_at !== generatedAt
    || !text(value.question) || !services.includes(String(value.primary_service)) || !hash(value.analysis_sha256) || !strings(value.limitations)) return fail();
  const scope = value.scope;
  if (!record(scope) || !["jurisdiction", "boundary_reference_date", "osm_retrieved_at"].every((key) => text(scope[key]))
    || !count(scope.population_year) || !["study_population", "in_scope_population", "excluded_population"].every((key) => nonnegative(scope[key]))
    || !almost(scope.study_population as number, (scope.in_scope_population as number) + (scope.excluded_population as number))) return fail();
  const total = scope.in_scope_population as number;
  if (!Array.isArray(value.timeline) || !unique(value.timeline) || !value.timeline.every((row) => record(row)
    && ["id", "title", "role"].every((key) => text(row[key])) && nullableText(row.start) && nullableText(row.end) && url(row.source_url) && strings(row.limitations)
    && (row.start === null || row.end === null || String(row.start) <= String(row.end)))) return fail();
  if (!Array.isArray(value.services) || value.services.length !== services.length || !unique(value.services)) return fail();
  for (const service of value.services) {
    if (!record(service) || !services.includes(String(service.id)) || !["available", "unavailable"].includes(String(service.status)) || !count(service.facilities)
      || !text(service.reason) || !Array.isArray(service.variants) || !unique(service.variants)) return fail();
    if (service.status === "unavailable") {
      if (service.facilities !== 0 || service.variants.length !== 0) return fail();
      continue;
    }
    if (service.facilities === 0 || service.variants.length !== 6) return fail();
    const cases = new Set<string>();
    const shortlist = new Map<string, string>();
    for (const variant of service.variants) {
      if (!record(variant) || !text(variant.id) || !["walking", "modelled_vehicle"].includes(String(variant.travel_mode))
        || !number(variant.speed_factor) || ![.75, 1, 1.25].includes(variant.speed_factor) || !hash(variant.context_sha256)
        || !validBaseline(variant.baseline, total) || !Array.isArray(variant.interventions) || !unique(variant.interventions)
        || !variant.interventions.every((row) => validIntervention(row, total))) return fail();
      const key = `${variant.travel_mode}-${variant.speed_factor}`;
      if (cases.has(key)) return fail();
      cases.add(key);
      const targets = JSON.stringify(variant.interventions.map((row) => { const r = row as Record<string, unknown>; return [r.id, r.kind, r.target_id]; }));
      const mode = String(variant.travel_mode);
      if (shortlist.has(mode) && shortlist.get(mode) !== targets) return fail();
      shortlist.set(mode, targets);
    }
  }
  if (!Array.isArray(value.facility_review) || !unique(value.facility_review) || !value.facility_review.every((row) => record(row)
    && ["id", "name", "service_type", "geometry_role"].every((key) => text(row[key])) && typeof row.eligible === "boolean"
    && row.event_availability === "unknown" && row.actual_capacity === null && url(row.source_url))) return fail();
  if (value.routes !== undefined && !validRoutes(value.routes)) return fail();
  const topology = value.topology_review;
  if (topology !== undefined && (!record(topology) || !count(topology.reviewed_candidates) || !count(topology.accepted_connections) || topology.accepted_connections > topology.reviewed_candidates || !text(topology.summary))) return fail();
  if (value.focus_briefs !== undefined && (!Array.isArray(value.focus_briefs) || !unique(value.focus_briefs) || !value.focus_briefs.every((row) => record(row)
    && ["id", "name", "name_th", "service_type", "useful_intervention"].every((key) => text(row[key])) && fraction(row.unit_coverage_fraction)
    && nonnegative(row.modelled_population) && row.priority === "verification" && row.travel_mode === "walking" && strings(row.main_drivers) && strings(row.uncertainty)))) return fail();
  const capacity = value.capacity;
  if (!record(capacity) || !["unavailable", "scenario_only"].includes(String(capacity.status)) || !nullableText(capacity.site_id) || !nullableText(capacity.linked_access_intervention_id)
    || capacity.demand_basis !== "residential_participation" || capacity.actual_evacuation_demand !== null || capacity.actual_available_capacity !== null || !strings(capacity.assumptions)
    || !Array.isArray(capacity.experiments) || !capacity.experiments.every((row) => record(row) && fraction(row.participation_fraction)
      && ["places", "assumed_demand", "assigned", "capacity_limited", "unreachable", "coverage_excluded"].every((key) => nonnegative(row[key]))
      && (row.assigned as number) <= (row.places as number) + .05
      && almost(row.assumed_demand as number, total * (row.participation_fraction as number))
      && almost(row.assumed_demand as number, (row.assigned as number) + (row.capacity_limited as number) + (row.unreachable as number) + (row.coverage_excluded as number)))) return fail();
  if (capacity.status === "unavailable" && (capacity.site_id !== null || capacity.linked_access_intervention_id !== null || capacity.experiments.length !== 0)) return fail();
  if (capacity.status === "scenario_only") {
    if (!text(capacity.site_id) || !text(capacity.linked_access_intervention_id)) return fail();
    if (capacity.linked_service !== undefined || capacity.linked_variant_id !== undefined) {
      const service = value.services.find((row) => record(row) && row.id === capacity.linked_service) as Record<string, unknown> | undefined;
      const variant = Array.isArray(service?.variants) ? service.variants.find((row) => record(row) && row.id === capacity.linked_variant_id) as Record<string, unknown> | undefined : undefined;
      if (!variant || variant.travel_mode !== "walking" || variant.speed_factor !== 1 || !Array.isArray(variant.interventions)
        || !variant.interventions.some((row) => record(row) && row.id === capacity.linked_access_intervention_id && row.kind === "add_destination" && capacity.site_id === `hypothetical-${row.target_id}`)) return fail();
    }
  }
  return value as unknown as FinalsAnalysis;
}
