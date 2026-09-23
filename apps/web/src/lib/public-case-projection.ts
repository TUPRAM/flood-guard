export const PUBLIC_CASE_CATALOG_URL = "/public-case-projections/catalog.json";
const SHA256 = /^[a-f0-9]{64}$/;
const SERVICE_IDS = ["hospital", "primary_care", "pharmacy", "shelter", "main_road"] as const;
const MODES = ["walking", "modelled_vehicle"] as const;

export type PublicCaseService = (typeof SERVICE_IDS)[number];
export type PublicCaseMode = (typeof MODES)[number];
export interface PublicCaseReference { id: string; aoi_id: string; event_id: string; url: string; sha256: string; source_package_sha256: string }
export interface PublicCaseCatalog {
  schema_version: "floodguard.public_case_catalog.v1";
  package_version: string;
  source_catalog_sha256: string;
  aois: { id: string; name: string; name_th: string }[];
  events: { id: string; name: string; name_th: string; start: string; end: string }[];
  packages: PublicCaseReference[];
}
export interface PublicCaseProjection {
  schema_version: "floodguard.public_case.v1";
  package_version: string;
  id: string;
  aoi_id: string;
  event_id: string;
  source_package_sha256: string;
  generated_at: string;
  source_analysis_generated_at: string | null;
  source_timestamp: string | null;
  dataset_mode: "candidate";
  operational_status: "non_operational";
  official_warning: false;
  confidence_class: "low";
  fpps: null;
  action_class: null;
  affected_population: null;
  demographic_equity_status: "unavailable";
  population_reference_year: number | null;
  population_role: "modelled_residential_context";
  access: null;
  reporting_coverage_fraction: number | null;
  reporting_scope: string;
  limitations: string[];
  services: { id: PublicCaseService; status: "available" | "unavailable"; reason: string | null; facilities: number | null; variants: {
    id: string; travel_mode: PublicCaseMode; modelled_population: number;
    within_30_minutes_population: number; connected_without_route_population: number;
    unknown_access_population: number; candidate_flood_losing_30_min_access: number | null;
    candidate_flood_newly_unreachable_population: number | null; candidate_flood_scenario_id: string | null;
    candidate_flood_source_timestamp: string | null;
  }[] }[];
}

function record(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value); }
function text(value: unknown): value is string { return typeof value === "string" && value.length > 0; }
function nonnegative(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value) && value >= 0; }
function optionalCount(value: unknown): boolean { return value === null || nonnegative(value); }
function exactKeys(value: Record<string, unknown>, required: string[], optional: string[] = []): boolean {
  return required.every((key) => key in value) && Object.keys(value).every((key) => required.includes(key) || optional.includes(key));
}
function publicCaseUrl(value: unknown): value is string {
  return typeof value === "string" && /^\/public-case-projections\/cases\/[A-Za-z0-9_-]+\.json$/.test(value);
}

export function parsePublicCaseCatalog(value: unknown): PublicCaseCatalog {
  if (!record(value) || !exactKeys(value, ["schema_version", "package_version", "source_catalog_sha256", "aois", "events", "packages"])
    || value.schema_version !== "floodguard.public_case_catalog.v1" || !text(value.package_version)
    || typeof value.source_catalog_sha256 !== "string" || !SHA256.test(value.source_catalog_sha256)
    || !Array.isArray(value.aois) || !Array.isArray(value.events) || !Array.isArray(value.packages)
    || !value.aois.every((row) => record(row) && exactKeys(row, ["id", "name", "name_th"]) && text(row.id) && text(row.name) && text(row.name_th))
    || !value.events.every((row) => record(row) && exactKeys(row, ["id", "name", "name_th", "start", "end"]) && ["id", "name", "name_th", "start", "end"].every((key) => text(row[key])))
    || !value.packages.every((row) => record(row) && exactKeys(row, ["id", "aoi_id", "event_id", "url", "sha256", "source_package_sha256"])
      && text(row.id) && text(row.aoi_id) && text(row.event_id) && publicCaseUrl(row.url)
      && typeof row.sha256 === "string" && SHA256.test(row.sha256) && typeof row.source_package_sha256 === "string" && SHA256.test(row.source_package_sha256))) {
    throw new Error("Invalid public case catalog.");
  }
  const catalog = value as unknown as PublicCaseCatalog;
  const ids = new Set<string>();
  const pairs = new Set<string>();
  for (const item of catalog.packages) {
    const pair = `${item.aoi_id}/${item.event_id}`;
    if (ids.has(item.id) || pairs.has(pair) || !catalog.aois.some((aoi) => aoi.id === item.aoi_id)
      || !catalog.events.some((event) => event.id === item.event_id)) throw new Error("Invalid public case binding.");
    ids.add(item.id); pairs.add(pair);
  }
  return catalog;
}

export function parsePublicCaseProjection(value: unknown, catalog: PublicCaseCatalog, reference: PublicCaseReference): PublicCaseProjection {
  const fields = ["schema_version", "package_version", "id", "aoi_id", "event_id", "source_package_sha256", "generated_at", "source_analysis_generated_at", "source_timestamp", "dataset_mode", "operational_status", "official_warning", "confidence_class", "fpps", "action_class", "affected_population", "demographic_equity_status", "population_reference_year", "population_role", "access", "reporting_coverage_fraction", "reporting_scope", "limitations", "services"];
  if (!record(value) || !exactKeys(value, fields) || value.schema_version !== "floodguard.public_case.v1"
    || value.package_version !== catalog.package_version || value.id !== reference.id || value.aoi_id !== reference.aoi_id || value.event_id !== reference.event_id
    || value.source_package_sha256 !== reference.source_package_sha256 || !text(value.generated_at)
    || !(value.source_analysis_generated_at === null || (text(value.source_analysis_generated_at)
      && Number.isFinite(Date.parse(value.source_analysis_generated_at)) && Number.isFinite(Date.parse(value.generated_at as string))
      && Date.parse(value.source_analysis_generated_at) <= Date.parse(value.generated_at as string)))
    || !(value.source_timestamp === null || text(value.source_timestamp)) || value.dataset_mode !== "candidate"
    || value.operational_status !== "non_operational" || value.official_warning !== false || value.confidence_class !== "low"
    || value.fpps !== null || value.action_class !== null || value.affected_population !== null || value.demographic_equity_status !== "unavailable"
    || !(value.population_reference_year === null || (Number.isInteger(value.population_reference_year) && nonnegative(value.population_reference_year)))
    || value.population_role !== "modelled_residential_context"
    || value.access !== null
    || !(value.reporting_coverage_fraction === null || (nonnegative(value.reporting_coverage_fraction) && value.reporting_coverage_fraction <= 1))
    || !text(value.reporting_scope) || !Array.isArray(value.limitations) || !value.limitations.every(text)
    || !Array.isArray(value.services) || !value.services.every((service) => record(service) && exactKeys(service, ["id", "status", "reason", "facilities", "variants"])
      && SERVICE_IDS.includes(service.id as PublicCaseService) && ["available", "unavailable"].includes(String(service.status))
      && (service.reason === null || text(service.reason))
      && (service.facilities === null || (Number.isInteger(service.facilities) && nonnegative(service.facilities)))
      && Array.isArray(service.variants) && service.variants.every((variant) => record(variant)
        && exactKeys(variant, ["id", "travel_mode", "modelled_population", "within_30_minutes_population", "connected_without_route_population", "unknown_access_population", "candidate_flood_losing_30_min_access", "candidate_flood_newly_unreachable_population", "candidate_flood_scenario_id", "candidate_flood_source_timestamp"])
        && text(variant.id) && MODES.includes(variant.travel_mode as PublicCaseMode)
        && ["modelled_population", "within_30_minutes_population", "connected_without_route_population", "unknown_access_population"].every((key) => nonnegative(variant[key]))
        && optionalCount(variant.candidate_flood_losing_30_min_access) && optionalCount(variant.candidate_flood_newly_unreachable_population)
        && (variant.candidate_flood_scenario_id === null || text(variant.candidate_flood_scenario_id))
        && (variant.candidate_flood_source_timestamp === null || text(variant.candidate_flood_source_timestamp))))) {
    throw new Error("Invalid or unsafe public case projection.");
  }
  const projection = value as unknown as PublicCaseProjection;
  if (!projection.services.some((service) => service.id === "main_road")
    || new Set(projection.services.map((service) => service.id)).size !== projection.services.length
    || projection.services.some((service) => (service.status === "unavailable") !== (service.variants.length === 0)
      || (service.id === "main_road" && (service.status !== "unavailable" || service.reason === null
        || service.facilities !== null || service.variants.length !== 0))
      || new Set(service.variants.map((variant) => variant.travel_mode)).size !== service.variants.length
      || service.variants.some((variant) => variant.within_30_minutes_population + variant.connected_without_route_population + variant.unknown_access_population > variant.modelled_population + .05
        || (variant.candidate_flood_scenario_id === null) !== (variant.candidate_flood_losing_30_min_access === null)
        || (variant.candidate_flood_scenario_id === null) !== (variant.candidate_flood_newly_unreachable_population === null)
        || (variant.candidate_flood_scenario_id === null) !== (variant.candidate_flood_source_timestamp === null)))) {
    throw new Error("Public case service values are inconsistent.");
  }
  return projection;
}

export async function fetchPublicCase(catalog: PublicCaseCatalog, reference: PublicCaseReference, signal?: AbortSignal): Promise<PublicCaseProjection> {
  if (!publicCaseUrl(reference.url)) throw new Error("Invalid public case URL.");
  const response = await fetch(reference.url, { signal });
  if (!response.ok) throw new Error(`Public case unavailable (${response.status}).`);
  const bytes = await response.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const actual = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (actual !== reference.sha256) throw new Error("Public case checksum differs from the catalog.");
  return parsePublicCaseProjection(JSON.parse(new TextDecoder().decode(bytes)), catalog, reference);
}
