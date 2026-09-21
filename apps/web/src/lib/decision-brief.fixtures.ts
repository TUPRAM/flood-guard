import type { DecisionBrief } from "@floodguard/contracts";

/** Open synthetic contract fixture, never a production evidence package. */
export function decisionBriefFixture(): DecisionBrief {
  return {
    schema_version: "1.0", generated_at: "2026-09-21T00:00:00Z", aoi_id: "test-aoi", event_id: "test-event", status: "scenario_only",
    priority: { status: "unavailable", fpps: null, action_class: null, reason: "No accepted event evidence." }, affected_population: null,
    population_reference_year: 2020, population_role: "modelled_residential_context",
    access: { modelled_population: 100, unknown_access_population: 10, connected_without_route_population: 20, over_30_minutes_population: 30, within_30_minutes_population: 40 },
    reporting: { status: "unavailable", source_url: null, reference_date: null, coverage_fraction: null, unassigned_modelled_population: null, ambiguous_population_cells: 0, scope: "No reporting boundary fixture.", units: [] },
    interventions: [{ id: "close_edge", scenario_id: "access-close_edge", kind: "close_edge", gaining_30_min_access: 0, losing_30_min_access: 0, slower_population: 40, faster_population: 0, comparable_population: 70, mean_travel_time_delta_minutes: 2, result: "travel_time_only", observed: false, selection_method: "Synthetic baseline-used edge." }],
    evidence_notes: [], capacity_experiments: [], capacity_status: "assumed_demand_and_capacity_only", demographic_equity_status: "unavailable",
    coverage: { connected_components: 2, candidate_destinations: 2, connected_destinations: 1 }, drivers: ["Synthetic fixture."],
    next_actions: [{ id: "event_reference", order: 1, action: "Verify event coverage", reason: "No qualified flood footprint." }], limitations: ["Synthetic fixture only."],
  };
}
