import type { EvidenceLibraryCatalog, FinalsAnalysis, FinalsServiceId, FinalsTravelMode } from "@floodguard/contracts";

export interface CaseSelection {
  aoi?: string;
  event?: string;
  version?: string;
  service?: string;
  mode?: string;
  scenario?: string;
  origin?: string;
}

const CASE_KEYS = ["aoi", "event", "version", "service", "mode", "scenario", "origin"] as const;

/**
 * Route of the candidate-package validation report (shared case header plus `StudioCandidateReport`).
 * `/studio/` itself is the study library; the report keeps its own address below it, and the shared-case
 * pages link here when they mean "the Studio view of this case".
 */
export const STUDIO_CANDIDATE_REPORT_ROUTE = "/studio/candidate-report/";

/**
 * The two Planning pages (owner request of 5 Oct 2026, decision log R19). `/command/` is the map workspace: the
 * default Planning page and the address of every "Planning" link in a header. The candidate planning overview
 * (shared case header plus `PlanningCandidateOverview`) keeps its own address below it, and pages link there when
 * they mean "the planning overview of this case". `/command/archive/`, the workspace's address before the swap,
 * only forwards to `/command/`.
 */
export const PLANNING_WORKSPACE_ROUTE = "/command/";
export const PLANNING_OVERVIEW_ROUTE = "/command/ver2/";

export function readCaseSelection(search: string): CaseSelection {
  const query = new URLSearchParams(search);
  return Object.fromEntries(CASE_KEYS.flatMap((key) => {
    const value = query.get(key);
    return value ? [[key, value]] : [];
  })) as CaseSelection;
}

export function caseHref(path: string, selection: CaseSelection): string {
  const query = new URLSearchParams();
  for (const key of CASE_KEYS) {
    if (selection[key]) query.set(key, selection[key]);
  }
  return query.size ? `${path}?${query}` : path;
}

/** Notify all role views after changing the current case URL without a page load. */
export function pushCaseSelection(selection: CaseSelection): void {
  window.history.pushState(null, "", caseHref(window.location.pathname, selection));
  window.dispatchEvent(new Event("popstate"));
}

/**
 * An explicit unknown or mixed-version selection never falls back to another case. Only the catalogue's version and
 * its list of cases are read, so a caller that holds no more of the catalogue than that can ask too.
 */
export function resolveEvidenceCase(catalog: Pick<EvidenceLibraryCatalog, "package_version" | "packages">, selection: CaseSelection) {
  if (Boolean(selection.aoi) !== Boolean(selection.event)) return { reference: null, reason: "incomplete_case" } as const;
  if (selection.version && selection.version !== catalog.package_version) return { reference: null, reason: "version_mismatch" } as const;
  const reference = selection.aoi && selection.event
    ? catalog.packages.find((item) => item.aoi_id === selection.aoi && item.event_id === selection.event)
    : catalog.packages[0];
  return reference ? { reference, reason: null } as const : { reference: null, reason: "unknown_case" } as const;
}

export function resolveAnalysisSelection(analysis: FinalsAnalysis, selection: CaseSelection): {
  service: FinalsServiceId | null;
  mode: FinalsTravelMode | null;
  origin: string | null;
  scenario: string | null;
  reason: "unknown_service" | "unknown_mode" | "unknown_origin" | "unknown_scenario" | null;
} {
  const service = selection.service ?? analysis.primary_service;
  if (!analysis.services.some((item) => item.id === service)) return { service: null, mode: null, origin: null, scenario: null, reason: "unknown_service" };
  const mode = selection.mode ?? "walking";
  if (mode !== "walking" && mode !== "modelled_vehicle") return { service: service as FinalsServiceId, mode: null, origin: null, scenario: null, reason: "unknown_mode" };
  const origin = selection.origin ?? analysis.routes?.origins[0]?.id ?? null;
  if (selection.origin && !analysis.routes?.origins.some((item) => item.id === selection.origin)) {
    return { service: service as FinalsServiceId, mode, origin: null, scenario: null, reason: "unknown_origin" };
  }
  const scenario = selection.scenario ?? null;
  const supported = scenario === null || (service === "hospital" && scenario === analysis.flood_scenarios?.[mode]?.impact.id)
    || Boolean(analysis.routes?.comparisons.some((item) => item.id === scenario && item.origin_id === origin && item.service_type === service && item.travel_mode === mode));
  if (!supported) return { service: service as FinalsServiceId, mode, origin, scenario: null, reason: "unknown_scenario" };
  return { service: service as FinalsServiceId, mode, origin, scenario, reason: null };
}
