import bundleJson from "../../public/offline-demo/bundle.json";
import areasGeoJson from "../data/areas.json";
import roadsGeoJson from "../data/roads.json";

import {
  ACCEPTANCE_RECEIPT_STATES,
  OPERATIONAL_STATUSES,
  PILOT_ROLES,
  type AreaDecision,
  type LayerCatalogItem,
  type ModelRun,
  type PilotReadiness,
  type StatusResponse,
} from "@floodguard/contracts";

import type { AreaRecord, FeatureCollection, FloodGuardData, OfflineBundle, ReadinessRow, ScenarioId, ScenarioResult } from "./types";

const offlineBundle = bundleJson as unknown as OfflineBundle;

export const LAST_KNOWN_API_SNAPSHOT_KEY = "floodguard:last-known-api-snapshot:v2";
const SNAPSHOT_SCHEMA_VERSION = "1.0";

export interface SnapshotStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const areaFeatures = areasGeoJson as unknown as FeatureCollection;
export const roadFeatures = roadsGeoJson as unknown as FeatureCollection;

export function getOfflineData(reason?: string): FloodGuardData {
  return {
    ...offlineBundle,
    dataState: reason ? "stale_offline" : "ready",
    dataOrigin: "offline_bundle",
    scenarioState: "ready",
    areaFeatures,
    roadFeatures,
    fallbackReason: reason,
  };
}

export async function loadFloodGuardData(
  apiBase = process.env.NEXT_PUBLIC_FLOODGUARD_API_URL,
  snapshotStorage?: SnapshotStorage | null,
): Promise<FloodGuardData> {
  const storage = resolveSnapshotStorage(snapshotStorage);
  if (!apiBase) {
    return readLastKnownApiSnapshot(storage, "API endpoint is not configured.") ?? getOfflineData();
  }

  try {
    const base = apiBase.replace(/\/$/, "");
    const [statusResponse, areasResponse, layersResponse] = await Promise.all([
        fetch(`${base}/api/v1/status`, { cache: "no-store" }),
        fetch(`${base}/api/v1/areas`, { cache: "no-store" }),
        fetch(`${base}/api/v1/layers`, { cache: "no-store" }),
      ]);

    const responses = [statusResponse, areasResponse, layersResponse];
    if (responses.some((response) => !response.ok)) {
      throw new Error(`Core API returned ${responses.map((response) => response.status).join(", ")}`);
    }

    const [statusRaw, areasRaw, layersRaw] = await Promise.all(
      responses.map((response) => response.json()),
    );
    const status = statusRaw as StatusResponse;
    const areas = asItems<AreaDecision>(areasRaw);
    const layers = asItems<LayerCatalogItem>(layersRaw);
    const degradationReasons: string[] = [];
    const [runsResult, readinessResult, pilotResult] = await Promise.allSettled([
      loadCollection<ModelRun>(`${base}/api/v1/model-runs`),
      loadCollection<Record<string, unknown>>(`${base}/api/v1/data-readiness`),
      loadPilotReadiness(`${base}/api/v1/pilot/readiness`),
    ]);
    const modelRuns = runsResult.status === "fulfilled" ? runsResult.value : [];
    if (runsResult.status === "rejected") degradationReasons.push("Model-run catalog unavailable.");
    const readiness = readinessResult.status === "fulfilled"
      ? readinessResult.value.map(adaptReadiness)
      : [{
          check_id: "api_data_readiness",
          source: "API readiness artifact",
          status: "unavailable" as const,
          severity: "high" as const,
          reason_blocked: "The current API data-readiness artifact is unavailable.",
        }];
    if (readinessResult.status === "rejected") degradationReasons.push("Data-readiness artifact unavailable.");
    const pilotReadiness = pilotResult.status === "fulfilled"
      ? pilotResult.value
      : offlineBundle.pilot_readiness;
    if (pilotResult.status === "rejected") degradationReasons.push("Pilot-readiness control unavailable.");
    const agencyOperationVerified = (
      pilotResult.status === "fulfilled"
      && status.dataset_mode === "official_input"
      && status.operational_status === "agency_operational"
      && pilotReadiness.operational_status === "agency_operational"
      && pilotReadiness.agency_operational_allowed
      && pilotReadiness.acceptance_receipt_state === "accepted"
      && pilotReadiness.audit_state === "valid"
      && pilotReadiness.retention_state === "configured"
      && pilotReadiness.deployment_state === "accepted_for_agency_operation"
    );
    const boundedStatus = !agencyOperationVerified && status.operational_status === "agency_operational"
      ? { ...status, operational_status: "non_operational" as const, official_warning: false }
      : status;
    const boundedAreas = areas.map((area) => (
      !agencyOperationVerified && area.operational_status === "agency_operational"
        ? { ...area, operational_status: "non_operational" as const, official_warning: false }
        : area
    ));
    const boundedLayers = layers.map((layer) => (
      !agencyOperationVerified && layer.operational_status === "agency_operational"
        ? { ...layer, operational_status: "non_operational" as const, official_warning: false }
        : layer
    ));
    const boundedModelRuns = modelRuns.map((run) => (
      !agencyOperationVerified && run.operational_status === "agency_operational"
        ? {
            ...run,
            operational_status: "non_operational" as const,
            official_warning: false,
            can_feed_decision_layer: false,
            reason_blocked: "Pilot acceptance controls could not be revalidated.",
          }
        : run
    ));
    const fixtureCompatible = status.dataset_mode === "fixture_demo" && status.study_area === "fixture_thailand_demo";
    const errorCategories = boundedModelRuns.length > 0
      ? [...new Set(boundedModelRuns.flatMap((run) => run.error_categories))].map((category) => ({
          category,
          status: "reviewed" as const,
          note: "Reported by the current API model-run manifest.",
        }))
      : [{
          category: "model_run_catalog_unavailable",
          status: "not_evaluated" as const,
          note: "Model validation categories are unavailable from the current API.",
        }];
    const scenarioEligible = fixtureCompatible && status.data_state === "ready";
    const [areaLayerResult, roadLayerResult, scenarioResult] = await Promise.allSettled([
      loadLayerData(base, layers, "priority_areas"),
      loadLayerData(base, layers, "road_risk"),
      scenarioEligible ? loadScenarioResults(base, status) : Promise.resolve(new Map()),
    ]);
    if (areaLayerResult.status === "rejected") throw areaLayerResult.reason;
    const apiAreaFeatures = areaLayerResult.value;
    const apiRoadFeatures = roadLayerResult.status === "fulfilled"
      ? roadLayerResult.value
      : emptyFeatureCollection("road_risk_unavailable");
    if (roadLayerResult.status === "rejected") degradationReasons.push("Road-risk layer unavailable.");
    const scenarioResults = scenarioResult.status === "fulfilled" ? scenarioResult.value : new Map();
    const scenarioState = scenarioEligible && scenarioResult.status === "fulfilled" ? "ready" : "unavailable";
    if (scenarioEligible && scenarioResult.status === "rejected") degradationReasons.push("Scenario artifacts unavailable.");
    const publicLayers = roadLayerResult.status === "fulfilled"
      ? boundedLayers
      : boundedLayers.map((layer) => layer.layer_id === "road_risk" ? { ...layer, data_state: "unavailable" as const } : layer);
    const candidate = {
      ...offlineBundle,
      status: boundedStatus,
      areas: boundedAreas.map((area) => adaptArea(area, scenarioResults)),
      layers: publicLayers,
      model_runs: boundedModelRuns,
      readiness,
      pilot_readiness: pilotReadiness,
      shelters: fixtureCompatible ? offlineBundle.shelters : [],
      error_categories: fixtureCompatible ? offlineBundle.error_categories : errorCategories,
      dataState: boundedStatus.data_state,
      dataOrigin: "api",
      scenarioState,
      apiBase: base,
      areaFeatures: apiAreaFeatures,
      roadFeatures: apiRoadFeatures,
      degradedReason: degradationReasons.length > 0 ? degradationReasons.join(" ") : undefined,
    } as FloodGuardData;
    assertNoPrivatePaths(candidate);
    writeLastKnownApiSnapshot(storage, candidate);
    return candidate;
  } catch (error) {
    const reason = error instanceof Error ? error.message : "API unavailable";
    return readLastKnownApiSnapshot(storage, reason) ?? getOfflineData(reason);
  }
}

function resolveSnapshotStorage(
  storage: SnapshotStorage | null | undefined,
): SnapshotStorage | null {
  if (storage !== undefined) return storage;
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function writeLastKnownApiSnapshot(
  storage: SnapshotStorage | null,
  data: FloodGuardData,
): void {
  if (!storage || data.dataOrigin !== "api") return;
  const publicData: FloodGuardData = {
    ...data,
    apiBase: undefined,
    fallbackReason: undefined,
    snapshotCachedAt: undefined,
  };
  const envelope = {
    schema_version: SNAPSHOT_SCHEMA_VERSION,
    cached_at: new Date().toISOString(),
    data: publicData,
  };
  try {
    assertNoPrivatePaths(envelope);
    storage.setItem(LAST_KNOWN_API_SNAPSHOT_KEY, JSON.stringify(envelope));
  } catch {
    // Browser storage is optional; quota or privacy-mode failures must not
    // replace a valid current API response.
  }
}

function readLastKnownApiSnapshot(
  storage: SnapshotStorage | null,
  reason: string,
): FloodGuardData | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(LAST_KNOWN_API_SNAPSHOT_KEY);
    if (!raw) return null;
    const envelope = JSON.parse(raw) as unknown;
    if (!isSnapshotEnvelope(envelope)) return null;
    assertNoPrivatePaths(envelope);
    return {
      ...envelope.data,
      status: {
        ...envelope.data.status,
        operational_status: "non_operational",
        official_warning: false,
        data_state: "stale",
      },
      areas: envelope.data.areas.map((area) => ({
        ...area,
        operational_status: "non_operational",
        official_warning: false,
      })),
      layers: envelope.data.layers.map((layer) => ({
        ...layer,
        operational_status: "non_operational",
        official_warning: false,
        data_state: "stale",
      })),
      model_runs: envelope.data.model_runs.map((run) => ({
        ...run,
        operational_status: "non_operational",
        official_warning: false,
        can_feed_decision_layer: false,
        reason_blocked: run.reason_blocked || "Cached offline evidence cannot feed the decision layer.",
      })),
      pilot_readiness: {
        ...envelope.data.pilot_readiness,
        operational_status: "non_operational",
        agency_operational_allowed: false,
        deployment_state: "degraded",
        reason_blocked_th: "โหมดออฟไลน์ไม่สามารถตรวจสอบใบรับรองการยอมรับกับเซิร์ฟเวอร์ได้",
        reason_blocked_en: "Offline mode cannot revalidate the acceptance receipt with the server.",
      },
      dataState: "stale_offline",
      dataOrigin: "cached_api",
      scenarioState: "unavailable",
      apiBase: undefined,
      snapshotCachedAt: envelope.cached_at,
      fallbackReason: reason,
    };
  } catch {
    return null;
  }
}

function isSnapshotEnvelope(
  value: unknown,
): value is { schema_version: "1.0"; cached_at: string; data: FloodGuardData } {
  if (!isRecord(value) || value.schema_version !== SNAPSHOT_SCHEMA_VERSION) return false;
  if (typeof value.cached_at !== "string" || !Number.isFinite(Date.parse(value.cached_at))) return false;
  const data = value.data;
  if (!isRecord(data) || data.dataOrigin !== "api") return false;
  if (!isRecord(data.status) || typeof data.status.source_timestamp !== "string") return false;
  if (typeof data.status.source_name !== "string" || typeof data.status.official_warning !== "boolean") return false;
  if (!Array.isArray(data.areas) || !Array.isArray(data.layers)) return false;
  if (!Array.isArray(data.readiness) || !Array.isArray(data.model_runs)) return false;
  if (!isRecord(data.pilot_readiness)) return false;
  if (typeof data.pilot_readiness.agency_operational_allowed !== "boolean") return false;
  if (!Array.isArray(data.hotlines) || !Array.isArray(data.shelters)) return false;
  if (!isFeatureCollection(data.areaFeatures) || !isFeatureCollection(data.roadFeatures)) return false;
  return true;
}

async function loadObject<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`API returned ${response.status} for ${url}`);
  const payload = await response.json() as unknown;
  if (!isRecord(payload)) throw new Error(`API object contract failed for ${url}`);
  return payload as T;
}

async function loadPilotReadiness(url: string): Promise<PilotReadiness> {
  const payload = await loadObject<unknown>(url);
  if (!isPilotReadiness(payload)) {
    throw new Error(`Pilot-readiness contract failed for ${url}`);
  }
  return payload;
}

function isPilotReadiness(value: unknown): value is PilotReadiness {
  if (!isRecord(value) || value.schema_version !== "1.0") return false;
  if (!OPERATIONAL_STATUSES.includes(value.operational_status as never)) return false;
  if (typeof value.agency_operational_allowed !== "boolean") return false;
  if (!["unconfigured", "configured"].includes(String(value.identity_state))) return false;
  if (!ACCEPTANCE_RECEIPT_STATES.includes(value.acceptance_receipt_state as never)) return false;
  if (!["unconfigured", "valid", "invalid"].includes(String(value.audit_state))) return false;
  if (!["unconfigured", "configured"].includes(String(value.retention_state))) return false;
  if (![
    "pilot_not_configured",
    "pilot_ready_non_operational",
    "degraded",
    "accepted_for_agency_operation",
  ].includes(String(value.deployment_state))) return false;
  if (value.field_validation_protocol_version !== "field-validation-v1") return false;
  if (typeof value.reason_blocked_th !== "string" || typeof value.reason_blocked_en !== "string") return false;
  const roles = value.roles;
  if (!Array.isArray(roles) || roles.length !== PILOT_ROLES.length) return false;
  if (new Set(roles).size !== PILOT_ROLES.length) return false;
  if (!PILOT_ROLES.every((role) => roles.includes(role))) return false;
  const requiredCriteria = [
    "AC-SAFETY-01",
    "AC-DATA-02",
    "AC-OFFLINE-03",
    "AC-AUTH-04",
    "AC-FIELD-05",
  ];
  if (!Array.isArray(value.acceptance_criteria) || value.acceptance_criteria.length !== requiredCriteria.length) return false;
  const criteria = value.acceptance_criteria;
  for (const criterion of criteria) {
    if (!isRecord(criterion)) return false;
    if (!requiredCriteria.includes(String(criterion.criterion_id))) return false;
    if (criterion.required !== true) return false;
    if (!["pending", "accepted"].includes(String(criterion.status))) return false;
    if (typeof criterion.text_th !== "string" || !criterion.text_th) return false;
    if (typeof criterion.text_en !== "string" || !criterion.text_en) return false;
  }
  if (new Set(criteria.map((item) => item.criterion_id)).size !== requiredCriteria.length) return false;
  if (value.operational_status === "agency_operational") {
    if (
      !value.agency_operational_allowed
      || value.acceptance_receipt_state !== "accepted"
      || value.identity_state !== "configured"
      || value.audit_state !== "valid"
      || value.retention_state !== "configured"
      || value.deployment_state !== "accepted_for_agency_operation"
      || criteria.some((criterion) => criterion.status !== "accepted")
    ) return false;
  } else if (
    value.agency_operational_allowed
    || value.deployment_state === "accepted_for_agency_operation"
  ) {
    return false;
  }
  return true;
}

function isFeatureCollection(value: unknown): value is FeatureCollection {
  return isRecord(value) && value.type === "FeatureCollection" && Array.isArray(value.features);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function loadCollection<T>(url: string): Promise<T[]> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Optional API collection returned ${response.status}.`);
  return asItems<T>(await response.json());
}

function emptyFeatureCollection(name: string): FeatureCollection {
  return { type: "FeatureCollection", name, features: [] };
}

function asItems<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === "object" && "items" in value && Array.isArray(value.items)) return value.items as T[];
  throw new Error("API collection response is not an array.");
}

function adaptReadiness(row: Record<string, unknown>): ReadinessRow {
  const status = String(row.status) as ReadinessRow["status"];
  if (!["ready", "stale", "blocked", "unavailable"].includes(status)) throw new Error("Unknown readiness state.");
  return {
    check_id: String(row.check_id),
    source: String(row.source ?? row.source_status ?? row.phase ?? "API readiness artifact"),
    status,
    severity: String(row.severity) as ReadinessRow["severity"],
    reason_blocked: String(row.reason_blocked ?? ""),
  };
}

type ApiScenarioArea = {
  area_id: string;
  scenario_people_losing_30_min_access: number;
  scenario_equity_gap_ratio: number | null;
  change_people_losing_30_min_access: number;
};

async function loadScenarioResults(base: string, status: StatusResponse): Promise<Map<string, Partial<Record<ScenarioId, ScenarioResult>>>> {
  const results = new Map<string, Partial<Record<ScenarioId, ScenarioResult>>>();
  if (status.dataset_mode !== "fixture_demo" || status.study_area !== "fixture_thailand_demo" || status.data_state !== "ready") return results;
  const requests = [
    { scenario_id: "add_temporary_shelter" as const, parameters: { node_id: "P2A", capacity: 500 } },
    { scenario_id: "close_road" as const, parameters: { road_id: "FG-RD-002" } },
  ];
  const payloads = await Promise.all(requests.map(async (request) => {
    const response = await fetch(`${base}/api/v1/scenario-runs`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, study_area: "fixture_thailand_demo" }),
    });
    if (!response.ok) throw new Error(`Scenario API returned ${response.status}.`);
    return { id: request.scenario_id, payload: await response.json() as { areas: ApiScenarioArea[] } };
  }));
  for (const { id, payload } of payloads) {
    for (const area of payload.areas) {
      const current = results.get(area.area_id) ?? {};
      current[id] = {
        people_losing_30_min_access: area.scenario_people_losing_30_min_access,
        equity_gap_ratio: area.scenario_equity_gap_ratio,
        delta: area.change_people_losing_30_min_access,
      };
      results.set(area.area_id, current);
    }
  }
  return results;
}

function adaptArea(area: AreaDecision, scenarios: Map<string, Partial<Record<ScenarioId, ScenarioResult>>>): AreaRecord {
  const offlineMatch = offlineBundle.areas.find((item) => item.area_id === area.area_id && item.data_version === area.data_version);
  const baseline: ScenarioResult = {
    people_losing_30_min_access: area.people_losing_30_min_access,
    equity_gap_ratio: area.equity_gap_ratio,
    delta: 0,
  };
  const server = scenarios.get(area.area_id) ?? {};
  return {
    ...area,
    total_population: offlineMatch?.total_population ?? 0,
    scenario_results: {
      baseline,
      add_temporary_shelter: server.add_temporary_shelter ?? baseline,
      close_road: server.close_road ?? baseline,
    },
  };
}

async function loadLayerData(base: string, layers: LayerCatalogItem[], layerId: string): Promise<FeatureCollection> {
  const layer = layers.find((item) => item.layer_id === layerId);
  if (!layer || layer.data_state !== "ready") throw new Error(`Required API layer ${layerId} is unavailable.`);
  const url = new URL(layer.url, `${base}/`).toString();
  if (new URL(url).origin !== new URL(base).origin) throw new Error("Cross-origin layer URL rejected.");
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`Layer ${layerId} returned ${response.status}.`);
  const collection = await response.json() as FeatureCollection;
  if (collection.type !== "FeatureCollection" || !Array.isArray(collection.features)) throw new Error(`Layer ${layerId} is not GeoJSON.`);
  return collection;
}

export async function loadApiBrief(
  apiBase: string,
  areaId: string,
): Promise<{ fileName: string; contentMarkdown: string }> {
  const base = apiBase.replace(/\/$/, "");
  const response = await fetch(`${base}/api/v1/briefs/${encodeURIComponent(areaId)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`Brief API returned ${response.status}.`);
  const payload = await response.json() as Record<string, unknown>;
  assertNoPrivatePaths(payload);
  if (typeof payload.file_name !== "string" || typeof payload.content_markdown !== "string") {
    throw new Error("Brief API response is invalid.");
  }
  return { fileName: payload.file_name, contentMarkdown: payload.content_markdown };
}

export function assertNoPrivatePaths(value: unknown): void {
  const privatePath = /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;
  const strings: string[] = [];
  JSON.stringify(value, (key, candidate: unknown) => {
    strings.push(key);
    if (typeof candidate === "string") strings.push(candidate);
    return candidate;
  });
  if (strings.some((candidate) => privatePath.test(candidate))) {
    throw new Error("Data provider rejected a private absolute path.");
  }
}

assertNoPrivatePaths(offlineBundle);
