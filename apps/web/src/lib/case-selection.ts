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

/** An explicit unknown or mixed-version selection never falls back to another case. */
export function resolveEvidenceCase(catalog: EvidenceLibraryCatalog, selection: CaseSelection) {
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
