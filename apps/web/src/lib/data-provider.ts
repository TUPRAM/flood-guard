import bundleJson from "../../public/offline-demo/bundle.json";
import maeSaiBundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import maeSaiManifestJson from "../../public/offline-demo/mae-sai/manifest.json";
import maeSaiPublicBundleJson from "../../public/offline-demo/mae-sai/public-bundle.json";
import areasGeoJson from "../data/areas.json";
import contextGeoJson from "../data/context.json";
import roadsGeoJson from "../data/roads.json";

import {
  ACCEPTANCE_RECEIPT_STATES,
  OPERATIONAL_STATUSES,
  PILOT_ROLES,
  type AreaDecision,
  type EvidenceContext,
  type EvidenceRecord,
  type LayerCatalogItem,
  type ModelRun,
  type PilotReadiness,
  type PublicPreparednessArea,
  type RoleVisibility,
  type StatusResponse,
} from "@floodguard/contracts";

import { assertArtifactsMatchEvidenceContext, assertEvidenceContextMatches, evidenceRecordMatchesContext } from "./evidence-context";
import { assertLayerVisibleForRole, visibleLayersForRole } from "./layer-visibility";
import type { AreaRecord, FeatureCollection, FloodGuardData, FloodGuardDataOptions, OfflineBundle, ReadinessRow, ScenarioId, ScenarioResult, StudyAreaId } from "./types";

const offlineBundle = bundleJson as unknown as OfflineBundle;
const maeSaiOfflineBundle = maeSaiBundleJson as unknown as OfflineBundle;
const maeSaiPublicBundle = maeSaiPublicBundleJson as unknown as {
  evidence_context: EvidenceContext;
  evidence_record: EvidenceRecord;
  public_areas: PublicPreparednessArea[];
  status: OfflineBundle["status"];
  layers: LayerCatalogItem[];
  hotlines: OfflineBundle["hotlines"];
  shelters: OfflineBundle["shelters"];
};
const maeSaiManifest = maeSaiManifestJson as unknown as {
  evidence_context: EvidenceContext;
  layers: Array<{
    layer_id: string;
    source_sha256: string;
    feature_count: number;
    role_visibility: RoleVisibility[];
  }>;
};

export const LAST_KNOWN_API_SNAPSHOT_KEY = "floodguard:last-known-api-snapshot:v2";
const SNAPSHOT_SCHEMA_VERSION = "2.0";

const DEFAULT_DATA_OPTIONS: FloodGuardDataOptions = {
  studyArea: "fixture_thailand_demo",
  role: "command",
};

export function normalizeDataOptions(
  requested: FloodGuardDataOptions | StudyAreaId = DEFAULT_DATA_OPTIONS,
): FloodGuardDataOptions {
  if (typeof requested === "string") {
    return {
      studyArea: requested,
      role: "command",
    };
  }
  return {
    studyArea: requested.studyArea,
    role: requested.role,
    evidenceContextId: requested.evidenceContextId,
  };
}

const fixtureSourceComponent = {
  source_component_id: "fixture-decision-inputs",
  role: "synthetic_decision_fixture",
  source_name: "FloodGuard committed fixture bundle",
  source_version: offlineBundle.status.data_version,
  source_timestamp: offlineBundle.status.source_timestamp,
  last_checked_at: offlineBundle.status.generated_at,
  temporal_meaning: "generation_time" as const,
  freshness: "historical" as const,
  freshness_policy_version: "source-freshness-v1" as const,
  freshness_as_of: offlineBundle.status.generated_at,
  attribution: ["FloodGuard synthetic fixtures"],
};

const fixtureEvidenceContext: EvidenceContext = {
  schema_version: "1.0",
  evidence_context_id: "fixture-thailand-demo:fixture-2026-06-29-v1",
  study_area_id: "fixture_thailand_demo",
  data_version: offlineBundle.status.data_version,
  evidence_package_id: "floodguard-fixture:fixture-2026-06-29-v1",
  evidence_package_sha256: "d49770def1e3b8648aa4093e1e2f72f2fcb95164086725bdb1f72c7717a07c28",
  model_run_id: null,
  dataset_mode: "fixture_demo",
  operational_status: "non_operational",
  official_warning: false,
  generated_at: offlineBundle.status.generated_at,
  source_components: [fixtureSourceComponent],
};

const fixtureEvidenceRecord: EvidenceRecord = {
  schema_version: "1.0",
  evidence_record_id: `${fixtureEvidenceContext.evidence_context_id}:blocked`,
  evidence_context: fixtureEvidenceContext,
  evidence_scope: "Synthetic integration evidence only",
  model_id: null,
  model_version: null,
  model_sha256: null,
  evaluation_sha256: null,
  decision: "blocked",
  decision_authority: null,
  decision_at: null,
  operational_authorized: false,
  blockers: ["Fixture evidence is not real-event validation or operational authorization."],
  generated_at: offlineBundle.status.generated_at,
};

export interface SnapshotStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const areaFeatures = areasGeoJson as unknown as FeatureCollection;
export const roadFeatures = roadsGeoJson as unknown as FeatureCollection;
export const contextFeatures = contextGeoJson as unknown as FeatureCollection;

export function getOfflineData(
  reason?: string,
  requested: FloodGuardDataOptions | StudyAreaId = DEFAULT_DATA_OPTIONS,
): FloodGuardData {
  const options = normalizeDataOptions(requested);
  const layers = visibleLayersForRole(offlineBundle.layers, options.role);
  const publicAreas = offlineBundle.areas.map((area) => ({
    schema_version: "1.0" as const,
    evidence_context_id: fixtureEvidenceContext.evidence_context_id,
    area_id: area.area_id,
    area_name_th: area.area_name_th,
    area_name_en: area.area_name_en,
    planning_priority_0_100: area.fpps_0_100,
    evidence_sufficiency: area.confidence_class,
    recommendation_code: area.action_reason_code,
    source_timestamp: area.source_timestamp,
    freshness: "historical" as const,
    current_conditions_confirmed: false,
  }));
  return {
    ...offlineBundle,
    status: {
      ...offlineBundle.status,
      evidence_context_id: fixtureEvidenceContext.evidence_context_id,
    },
    areas: offlineBundle.areas.map((area) => ({
      ...area,
      evidence_context_id: fixtureEvidenceContext.evidence_context_id,
    })),
    layers,
    role: options.role,
    evidenceContext: fixtureEvidenceContext,
    evidenceRecord: fixtureEvidenceRecord,
    publicAreas,
    dataState: reason ? "stale_offline" : "ready",
    dataOrigin: "offline_bundle",
    scenarioState: "ready",
    availableScenarios: ["baseline", "add_temporary_shelter", "close_road"],
    areaFeatures,
    roadFeatures: layers.some((layer) => layer.layer_id === "road_risk")
      ? roadFeatures
      : emptyFeatureCollection("fixture_road_layer_not_visible"),
    contextFeatures,
    facilityFeatures: emptyFeatureCollection("fixture_facilities_unavailable"),
    accessFeatures: emptyFeatureCollection("fixture_access_hotspots_unavailable"),
    fallbackReason: reason,
  };
}

export function getMaeSaiOfflineData(
  reason?: string,
  requested: FloodGuardDataOptions | StudyAreaId = {
    studyArea: "mae_sai_candidate_v1",
    role: "command",
  },
): FloodGuardData {
  const options = normalizeDataOptions(requested);
  const context = maeSaiPublicBundle.evidence_context;
  const recordMatches = evidenceRecordMatchesContext(
    maeSaiPublicBundle.evidence_record,
    context,
  );
  const mismatch = options.studyArea !== "mae_sai_candidate_v1"
    || (options.evidenceContextId !== undefined
      && options.evidenceContextId !== context.evidence_context_id)
    || !recordMatches;
  const layers = mismatch
    ? []
    : visibleLayersForRole(maeSaiOfflineBundle.layers, options.role);
  return {
    ...maeSaiOfflineBundle,
    status: maeSaiPublicBundle.status,
    areas: mismatch || options.role === "public" ? [] : maeSaiOfflineBundle.areas,
    layers,
    role: options.role,
    evidenceContext: context,
    evidenceRecord: recordMatches ? maeSaiPublicBundle.evidence_record : null,
    publicAreas: mismatch ? [] : maeSaiPublicBundle.public_areas,
    dataState: mismatch ? "unavailable" : reason ? "stale_offline" : "loading",
    dataOrigin: "offline_bundle",
    scenarioState: "unavailable",
    availableScenarios: ["baseline"],
    areaFeatures: emptyFeatureCollection("mae_sai_priority_areas_loading"),
    roadFeatures: emptyFeatureCollection("mae_sai_roads_loading"),
    contextFeatures: emptyFeatureCollection("mae_sai_context_loading"),
    facilityFeatures: emptyFeatureCollection("mae_sai_facilities_loading"),
    accessFeatures: emptyFeatureCollection("mae_sai_access_hotspots_loading"),
    fallbackReason: mismatch
      ? "The requested evidence context is not available in the Mae Sai offline package."
      : reason,
  };
}

export async function loadMaeSaiOfflineData(
  reason?: string,
  requested: FloodGuardDataOptions | StudyAreaId = {
    studyArea: "mae_sai_candidate_v1",
    role: "command",
  },
): Promise<FloodGuardData> {
  const options = normalizeDataOptions(requested);
  const base = getMaeSaiOfflineData(reason, options);
  if (base.dataState === "unavailable") return base;
  try {
    if (options.role === "public") {
      const publicAreas = await loadFeatureCollection(
        "/offline-demo/mae-sai/public-areas.json",
      );
      assertMaeSaiPublicCollection(publicAreas);
      return {
        ...base,
        dataState: reason ? "stale_offline" : "ready",
        areaFeatures: publicAreas,
      };
    }
    const [areas, roads, facilities, access] = await Promise.all([
      loadFeatureCollection("/offline-demo/mae-sai/areas.json"),
      loadFeatureCollection("/offline-demo/mae-sai/roads.json"),
      loadFeatureCollection("/offline-demo/mae-sai/facilities.json"),
      loadFeatureCollection("/offline-demo/mae-sai/access-hotspots.json"),
    ]);
    assertMaeSaiCollections(areas, roads, facilities, access, "complete", options.role);
    return {
      ...base,
      dataState: reason ? "stale_offline" : "ready",
      areaFeatures: areas,
      roadFeatures: roads,
      facilityFeatures: facilities,
      accessFeatures: access,
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Mae Sai offline bundle unavailable.";
    return {
      ...base,
      dataState: "unavailable",
      fallbackReason: reason ? `${reason} ${detail}` : detail,
    };
  }
}

export async function loadFloodGuardData(
  apiBase = process.env.NEXT_PUBLIC_FLOODGUARD_API_URL,
  snapshotStorage?: SnapshotStorage | null,
  requested: FloodGuardDataOptions | StudyAreaId = DEFAULT_DATA_OPTIONS,
): Promise<FloodGuardData> {
  const options = normalizeDataOptions(requested);
  const preferredStudyArea = options.studyArea;
  const storage = resolveSnapshotStorage(snapshotStorage);
  const snapshotKey = snapshotKeyFor(options);
  if (!apiBase) {
    const cached = preferredStudyArea === "mae_sai_candidate_v1"
      ? null
      : readLastKnownApiSnapshot(storage, "API endpoint is not configured.", snapshotKey);
    if (cached) return cached;
    return preferredStudyArea === "mae_sai_candidate_v1"
      ? loadMaeSaiOfflineData(undefined, options)
      : getOfflineData(undefined, options);
  }

  try {
    const base = apiBase.replace(/\/$/, "");
    const [statusResponse, contextResponse] = await Promise.all([
      fetch(withStudyArea(`${base}/api/v1/status`, preferredStudyArea), { cache: "no-store" }),
      fetch(withStudyArea(`${base}/api/v1/evidence-context`, preferredStudyArea), { cache: "no-store" }),
    ]);
    if (!statusResponse.ok || !contextResponse.ok) {
      throw new Error(
        `Evidence API returned ${statusResponse.status}, ${contextResponse.status}`,
      );
    }
    const [status, evidenceContext] = await Promise.all([
      statusResponse.json() as Promise<StatusResponse>,
      contextResponse.json() as Promise<EvidenceContext>,
    ]);
    assertEvidenceContextMatches(
      evidenceContext,
      status,
      preferredStudyArea,
      options.evidenceContextId,
    );
    const [areasResponse, publicAreasResponse, layersResponse, evidenceRecordResponse] = await Promise.all([
      options.role === "public"
        ? Promise.resolve(null)
        : fetch(withStudyArea(`${base}/api/v1/areas`, preferredStudyArea), { cache: "no-store" }),
      fetch(withStudyArea(`${base}/api/v1/public-areas`, preferredStudyArea), { cache: "no-store" }),
      fetch(withRole(
        withStudyArea(`${base}/api/v1/layers`, preferredStudyArea),
        options.role,
      ), { cache: "no-store" }),
      fetch(`${base}/api/v1/evidence-records/${encodeURIComponent(evidenceContext.evidence_context_id)}`, { cache: "no-store" }),
    ]);
    const coreResponses = [publicAreasResponse, layersResponse, evidenceRecordResponse];
    if (areasResponse) coreResponses.push(areasResponse);
    if (coreResponses.some((response) => !response.ok)) {
      throw new Error(
        `Context-bound API returned ${coreResponses.map((response) => response.status).join(", ")}`,
      );
    }
    const [publicAreasRaw, layersRaw, evidenceRecord] = await Promise.all([
      publicAreasResponse.json(),
      layersResponse.json(),
      evidenceRecordResponse.json() as Promise<EvidenceRecord>,
    ]);
    const areas = areasResponse
      ? asItems<AreaDecision>(await areasResponse.json())
      : [];
    const publicAreas = asItems<PublicPreparednessArea>(publicAreasRaw);
    const layers = visibleLayersForRole(
      asItems<LayerCatalogItem>(layersRaw),
      options.role,
    );
    if (!evidenceRecordMatchesContext(evidenceRecord, evidenceContext)) {
      throw new Error("Evidence record does not match the active evidence context.");
    }
    assertRequestedStudyArea(
      status,
      areas,
      publicAreas,
      evidenceContext,
      preferredStudyArea,
      options.role,
    );
    assertArtifactsMatchEvidenceContext(evidenceContext, areas, layers);
    const degradationReasons: string[] = [];
    const candidateProfile = status.study_area === "mae_sai_candidate_v1";
    const [runsResult, readinessResult, pilotResult] = await Promise.allSettled([
      candidateProfile
        ? Promise.resolve([] as ModelRun[])
        : loadCollection<ModelRun>(`${base}/api/v1/model-runs`),
      candidateProfile
        ? Promise.resolve(maeSaiOfflineBundle.readiness as ReadinessRow[])
        : loadCollection<Record<string, unknown>>(`${base}/api/v1/data-readiness`),
      candidateProfile
        ? Promise.resolve(maeSaiOfflineBundle.pilot_readiness)
        : loadPilotReadiness(`${base}/api/v1/pilot/readiness`),
    ]);
    const modelRuns = runsResult.status === "fulfilled" ? runsResult.value : [];
    if (runsResult.status === "rejected") degradationReasons.push("Model-run catalog unavailable.");
    const readiness = readinessResult.status === "fulfilled"
      ? readinessResult.value.map((row) => candidateProfile
          ? row as ReadinessRow
          : adaptReadiness(row as unknown as Record<string, unknown>))
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
    const scenarioEligible = options.role !== "public" && (
      status.data_state === "ready"
      || (status.study_area === "mae_sai_candidate_v1" && status.data_state === "stale")
    ) && (fixtureCompatible || status.study_area === "mae_sai_candidate_v1");
    const areaLayerId = options.role === "public"
      ? "public_preparedness_areas"
      : "priority_areas";
    const [areaLayerResult, roadLayerResult, facilityLayerResult, accessLayerResult, scenarioResult] = await Promise.allSettled([
      loadLayerData(base, layers, areaLayerId, options.role),
      options.role === "public"
        ? Promise.resolve(emptyFeatureCollection("road_risk_not_public"))
        : loadLayerData(base, layers, "road_risk", options.role),
      options.role === "public"
        ? Promise.resolve(emptyFeatureCollection("facilities_not_public"))
        : loadOptionalLayerData(base, layers, "facilities", options.role),
      options.role === "public"
        ? Promise.resolve(emptyFeatureCollection("access_hotspots_not_public"))
        : loadOptionalLayerData(base, layers, "access_hotspots", options.role),
      scenarioEligible
        ? loadScenarioResults(base, status, boundedAreas)
        : Promise.resolve(emptyScenarioLoadResult()),
    ]);
    if (areaLayerResult.status === "rejected") throw areaLayerResult.reason;
    const apiAreaFeatures = areaLayerResult.value;
    const apiRoadFeatures = roadLayerResult.status === "fulfilled"
      ? roadLayerResult.value
      : emptyFeatureCollection("road_risk_unavailable");
    if (options.role !== "public" && roadLayerResult.status === "rejected") degradationReasons.push("Road-risk layer unavailable.");
    const apiFacilityFeatures = facilityLayerResult.status === "fulfilled"
      ? facilityLayerResult.value
      : emptyFeatureCollection("facilities_unavailable");
    if (options.role !== "public" && facilityLayerResult.status === "rejected") degradationReasons.push("Facility layer unavailable.");
    const apiAccessFeatures = accessLayerResult.status === "fulfilled"
      ? accessLayerResult.value
      : emptyFeatureCollection("access_hotspots_unavailable");
    if (options.role !== "public" && accessLayerResult.status === "rejected") degradationReasons.push("Access-hotspot layer unavailable.");
    const loadedScenarios = scenarioResult.status === "fulfilled"
      ? scenarioResult.value
      : emptyScenarioLoadResult();
    const scenarioResults = loadedScenarios.results;
    const scenarioState = scenarioEligible
      && scenarioResult.status === "fulfilled"
      && loadedScenarios.availableScenarios.length > 1
      ? "ready"
      : "unavailable";
    if (scenarioEligible && scenarioResult.status === "rejected") degradationReasons.push("Scenario artifacts unavailable.");
    if (loadedScenarios.failedScenarioCount > 0) {
      degradationReasons.push(
        `${loadedScenarios.failedScenarioCount} server-defined scenario artifact${loadedScenarios.failedScenarioCount === 1 ? " is" : "s are"} unavailable.`,
      );
    }
    const availableLayers = roadLayerResult.status === "fulfilled"
      ? boundedLayers
      : boundedLayers.map((layer) => layer.layer_id === "road_risk" ? { ...layer, data_state: "unavailable" as const } : layer);
    const compatibleBundle = status.study_area === "mae_sai_candidate_v1"
      ? maeSaiOfflineBundle
      : offlineBundle;
    const candidate = {
      ...compatibleBundle,
      status: boundedStatus,
      areas: options.role === "public"
        ? []
        : boundedAreas.map((area) => adaptArea(area, scenarioResults)),
      layers: availableLayers,
      model_runs: options.role === "public" ? [] : boundedModelRuns,
      readiness,
      pilot_readiness: pilotReadiness,
      shelters: fixtureCompatible ? offlineBundle.shelters : [],
      error_categories: fixtureCompatible ? offlineBundle.error_categories : errorCategories,
      role: options.role,
      evidenceContext,
      evidenceRecord,
      publicAreas,
      dataState: boundedStatus.data_state,
      dataOrigin: "api",
      scenarioState,
      availableScenarios: scenarioState === "ready"
        ? loadedScenarios.availableScenarios
        : ["baseline"],
      apiBase: base,
      areaFeatures: apiAreaFeatures,
      roadFeatures: apiRoadFeatures,
      contextFeatures: fixtureCompatible
        ? contextFeatures
        : emptyFeatureCollection("context_unavailable_for_current_dataset"),
      facilityFeatures: apiFacilityFeatures,
      accessFeatures: apiAccessFeatures,
      degradedReason: degradationReasons.length > 0 ? degradationReasons.join(" ") : undefined,
    } as FloodGuardData;
    if (status.study_area === "mae_sai_candidate_v1") {
      if (options.role === "public") {
        assertMaeSaiPublicCollection(candidate.areaFeatures);
      } else {
        assertMaeSaiCollections(
          candidate.areaFeatures,
          candidate.roadFeatures,
          candidate.facilityFeatures,
          candidate.accessFeatures,
          "regional",
          options.role,
        );
      }
    }
    assertNoPrivatePaths(candidate);
    writeLastKnownApiSnapshot(storage, candidate, snapshotKey);
    return candidate;
  } catch (error) {
    const reason = error instanceof Error ? error.message : "API unavailable";
    const cached = preferredStudyArea === "mae_sai_candidate_v1"
      ? null
      : readLastKnownApiSnapshot(storage, reason, snapshotKey);
    if (cached) return cached;
    return preferredStudyArea === "mae_sai_candidate_v1"
      ? loadMaeSaiOfflineData(reason, options)
      : getOfflineData(reason, options);
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

function snapshotKeyFor(options: FloodGuardDataOptions): string {
  if (
    options.studyArea === "fixture_thailand_demo"
    && options.role === "command"
    && options.evidenceContextId === undefined
  ) return LAST_KNOWN_API_SNAPSHOT_KEY;
  const contextSuffix = options.evidenceContextId
    ? `:${encodeURIComponent(options.evidenceContextId)}`
    : "";
  return `${LAST_KNOWN_API_SNAPSHOT_KEY}:${options.studyArea}:${options.role}${contextSuffix}`;
}

function withStudyArea(url: string, studyArea: StudyAreaId): string {
  if (studyArea === "fixture_thailand_demo") return url;
  const parsed = new URL(url);
  parsed.searchParams.set("study_area", studyArea);
  return parsed.toString();
}

function writeLastKnownApiSnapshot(
  storage: SnapshotStorage | null,
  data: FloodGuardData,
  snapshotKey = LAST_KNOWN_API_SNAPSHOT_KEY,
): void {
  if (
    !storage
    || data.dataOrigin !== "api"
    || data.status.study_area === "mae_sai_candidate_v1"
  ) return;
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
    storage.setItem(snapshotKey, JSON.stringify(envelope));
  } catch {
    // Browser storage is optional; quota or privacy-mode failures must not
    // replace a valid current API response.
  }
}

function readLastKnownApiSnapshot(
  storage: SnapshotStorage | null,
  reason: string,
  snapshotKey = LAST_KNOWN_API_SNAPSHOT_KEY,
): FloodGuardData | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(snapshotKey);
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
      availableScenarios: ["baseline"],
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
): value is { schema_version: "2.0"; cached_at: string; data: FloodGuardData } {
  if (!isRecord(value) || value.schema_version !== SNAPSHOT_SCHEMA_VERSION) return false;
  if (typeof value.cached_at !== "string" || !Number.isFinite(Date.parse(value.cached_at))) return false;
  const data = value.data;
  if (!isRecord(data) || data.dataOrigin !== "api") return false;
  if (!isRecord(data.status) || typeof data.status.source_timestamp !== "string") return false;
  if (typeof data.status.source_name !== "string" || typeof data.status.official_warning !== "boolean") return false;
  if (!Array.isArray(data.areas) || !Array.isArray(data.layers)) return false;
  if (
    !Array.isArray(data.availableScenarios)
    || !data.availableScenarios.includes("baseline")
    || data.availableScenarios.some((scenario) => !isScenarioId(scenario))
  ) return false;
  if (!Array.isArray(data.readiness) || !Array.isArray(data.model_runs)) return false;
  if (!isRecord(data.pilot_readiness)) return false;
  if (typeof data.pilot_readiness.agency_operational_allowed !== "boolean") return false;
  if (!Array.isArray(data.hotlines) || !Array.isArray(data.shelters)) return false;
  if (!["public", "command", "studio"].includes(String(data.role))) return false;
  if (!isRecord(data.evidenceContext) || !isRecord(data.status)) return false;
  const snapshotContextId = data.evidenceContext.evidence_context_id;
  if (snapshotContextId !== data.status.evidence_context_id) return false;
  if (!Array.isArray(data.publicAreas)) return false;
  if (
    data.publicAreas.some((area) => (
      !isRecord(area)
      || area.evidence_context_id !== snapshotContextId
    ))
  ) return false;
  if (
    !isFeatureCollection(data.areaFeatures)
    || !isFeatureCollection(data.roadFeatures)
    || !isFeatureCollection(data.contextFeatures)
    || !isFeatureCollection(data.facilityFeatures)
    || !isFeatureCollection(data.accessFeatures)
  ) return false;
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

async function loadFeatureCollection(url: string): Promise<FeatureCollection> {
  const response = await fetch(url, { cache: "force-cache" });
  if (!response.ok) throw new Error(`Offline geospatial asset returned ${response.status} for ${url}.`);
  const value = await response.json() as unknown;
  if (!isFeatureCollection(value)) throw new Error(`Offline geospatial asset is not a FeatureCollection: ${url}.`);
  assertNoPrivatePaths(value);
  return value;
}

function assertRequestedStudyArea(
  status: StatusResponse,
  areas: AreaDecision[],
  publicAreas: PublicPreparednessArea[],
  context: EvidenceContext,
  preferredStudyArea: StudyAreaId,
  role: RoleVisibility,
): void {
  if (
    status.study_area !== preferredStudyArea
    || context.study_area_id !== preferredStudyArea
    || status.evidence_context_id !== context.evidence_context_id
    || publicAreas.some((area) => area.evidence_context_id !== context.evidence_context_id)
  ) {
    throw new Error("API study-area or evidence-context identity failed.");
  }
  if (preferredStudyArea !== "mae_sai_candidate_v1") return;
  const expectedIds = new Set(maeSaiOfflineBundle.areas.map((area) => area.area_id));
  const receivedIds = new Set(
    (role === "public" ? publicAreas : areas).map((area) => area.area_id),
  );
  const expectedCommit = maeSaiOfflineBundle.status.git_commit;
  const expectedSourceTimestamp = maeSaiOfflineBundle.status.source_timestamp;
  const expectedDataVersion = maeSaiOfflineBundle.status.data_version;
  if (
    status.study_area !== preferredStudyArea
    || status.dataset_mode !== "candidate"
    || status.operational_status !== "non_operational"
    || status.official_warning
    || status.data_version !== expectedDataVersion
    || status.git_commit !== expectedCommit
    || status.source_timestamp !== expectedSourceTimestamp
    || (role === "public" ? publicAreas.length : areas.length) !== expectedIds.size
    || receivedIds.size !== expectedIds.size
    || [...expectedIds].some((areaId) => !receivedIds.has(areaId))
    || areas.some((area) => (
      area.dataset_mode !== "candidate"
      || area.operational_status !== "non_operational"
      || area.official_warning
      || area.data_version !== expectedDataVersion
      || area.git_commit !== expectedCommit
      || area.source_timestamp !== expectedSourceTimestamp
    ))
  ) {
    throw new Error("Mae Sai API study-area identity or safety contract failed.");
  }
}

function assertMaeSaiCollections(
  areas: FeatureCollection,
  roads: FeatureCollection,
  facilities: FeatureCollection,
  access: FeatureCollection,
  roadScope: "complete" | "regional",
  role: Exclude<RoleVisibility, "public">,
): void {
  if (role !== "command" && role !== "studio") {
    throw new Error("Staff Mae Sai collections require a staff role.");
  }
  const expectedIds = new Set(maeSaiOfflineBundle.areas.map((area) => area.area_id));
  if (
    areas.features.length !== 8
    || roads.features.length !== (roadScope === "complete" ? 4_458 : 750)
    || facilities.features.length !== 42
    || access.features.length !== 8
  ) throw new Error("Mae Sai geospatial feature-count contract failed.");
  if (roadScope === "regional") {
    assertMaeSaiLayerMetadata(areas, "priority_areas");
    assertMaeSaiLayerMetadata(roads, "road_risk");
    assertMaeSaiLayerMetadata(facilities, "facilities");
    assertMaeSaiLayerMetadata(access, "access_hotspots");
    const query = (roads as unknown as { floodguard_query?: Record<string, unknown> }).floodguard_query;
    if (
      !query
      || query.detail !== "regional"
      || query.area_id !== null
      || query.returned_feature_count !== roads.features.length
      || roads.features.some((feature) => (
        feature.properties.dataset_mode !== "candidate"
        || feature.properties.official_warning !== false
        || feature.properties.observation_status !== "modelled_candidate_not_observed"
      ))
    ) throw new Error("Mae Sai regional road-layer query contract failed.");
  }
  const collections = [areas, roads, facilities, access];
  for (const collection of collections) {
    for (const feature of collection.features) {
      const areaId = String(feature.properties.area_id ?? "");
      if (!expectedIds.has(areaId)) throw new Error("Mae Sai feature references an unknown reporting area.");
      for (const [longitude, latitude] of coordinatePairs(feature.geometry.coordinates)) {
        if (longitude < 99.8 || longitude > 100.05 || latitude < 20.24 || latitude > 20.48) {
          throw new Error("Mae Sai feature escaped the declared geographic bounds.");
        }
      }
    }
  }
  if (facilities.features.some((feature) => (
    feature.properties.verification_status !== "open_context_candidate"
    || feature.properties.emergency_role !== "no_confirmed_emergency_role"
    || feature.properties.candidate_status !== "unverified_osm_candidate"
  ))) throw new Error("Mae Sai facility candidate was substituted or promoted without authority.");
}

function withRole(url: string, role: RoleVisibility): string {
  const parsed = new URL(url);
  parsed.searchParams.set("role", role);
  return parsed.toString();
}

function assertMaeSaiPublicCollection(collection: FeatureCollection): void {
  if (collection.features.length !== 8) {
    throw new Error("Mae Sai public preparedness feature-count contract failed.");
  }
  const metadata = (collection as unknown as { floodguard_metadata?: Record<string, unknown> }).floodguard_metadata;
  if (
    !metadata
    || metadata.study_area_id !== "mae_sai_candidate_v1"
    || metadata.evidence_context_id !== maeSaiPublicBundle.evidence_context.evidence_context_id
    || metadata.official_warning !== false
    || !Array.isArray(metadata.role_visibility)
    || metadata.role_visibility.length !== 1
    || metadata.role_visibility[0] !== "public"
  ) {
    throw new Error("Mae Sai public preparedness lineage contract failed.");
  }
  const forbidden = new Set([
    "action_class",
    "fpps_component_flood_0_100",
    "fpps_component_exposure_0_100",
    "fpps_component_access_0_100",
    "fpps_component_road_0_100",
    "fpps_component_vulnerability_0_100",
    "people_losing_30_min_access",
    "equity_gap_ratio",
    "candidate_evidence",
  ]);
  for (const feature of collection.features) {
    if (
      feature.properties.evidence_context_id !== maeSaiPublicBundle.evidence_context.evidence_context_id
      || feature.properties.current_conditions_confirmed !== false
      || Object.keys(feature.properties).some((key) => forbidden.has(key))
    ) {
      throw new Error("Mae Sai public preparedness projection contains staff-only fields.");
    }
  }
}

function assertMaeSaiLayerMetadata(collection: FeatureCollection, layerId: string): void {
  const metadata = (collection as unknown as { floodguard_metadata?: Record<string, unknown> }).floodguard_metadata;
  const expectedLayer = maeSaiManifest.layers.find((layer) => layer.layer_id === layerId);
  if (
    !metadata
    || !expectedLayer
    || metadata.schema_version !== "1.0"
    || metadata.study_area_id !== "mae_sai_candidate_v1"
    || metadata.dataset_mode !== "candidate"
    || metadata.operational_status !== "non_operational"
    || metadata.official_warning !== false
    || metadata.data_version !== maeSaiOfflineBundle.status.data_version
    || metadata.artifact_sha256 !== expectedLayer.source_sha256
    || metadata.processing_allowed !== true
    || metadata.can_feed_decision_layer !== false
    || typeof metadata.reason_blocked !== "string"
    || !metadata.reason_blocked
  ) throw new Error(`Mae Sai ${layerId} lineage metadata contract failed.`);
}

function coordinatePairs(value: unknown): Array<[number, number]> {
  if (!Array.isArray(value)) return [];
  if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
    return [[value[0], value[1]]];
  }
  return value.flatMap(coordinatePairs);
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
  baseline_people_losing_30_min_access: number;
  scenario_people_losing_30_min_access: number;
  baseline_equity_gap_ratio: number | null;
  scenario_equity_gap_ratio: number | null;
  change_people_losing_30_min_access: number;
};

type ApiScenarioParameterDefinition = {
  name: string;
  value_type: "integer" | "string";
  required: boolean;
  default: string | number;
  minimum: number | null;
  maximum: number | null;
  allowed_values: string[] | null;
};

type ApiScenarioDefinition = {
  scenario_id: Exclude<ScenarioId, "baseline">;
  parameters: ApiScenarioParameterDefinition[];
  backend_config_version: "fixture-access-scenarios-v1" | "mae-sai-candidate-access-scenarios-v1";
  access_method: "nearest_facility_shortest_path_threshold";
};

type ApiScenarioRun = {
  schema_version: string;
  run_id: string;
  scenario_id: Exclude<ScenarioId, "baseline">;
  study_area: string;
  parameters: Record<string, string | number>;
  run_status: "completed";
  result_state: "ready" | "stale";
  backend_config_version: ApiScenarioDefinition["backend_config_version"];
  access_method: ApiScenarioDefinition["access_method"];
  fpps_recalculated: false;
  dataset_mode: StatusResponse["dataset_mode"];
  operational_status: StatusResponse["operational_status"];
  official_warning: boolean;
  source_timestamp: string;
  generated_at: string;
  confidence_class: string;
  source_name: string;
  assumptions: string[];
  data_version: string;
  git_commit: string;
  input_manifest_sha256: string | null;
  input_receipt_sha256: string | null;
  areas: ApiScenarioArea[];
};

type ScenarioLoadResult = {
  results: Map<string, Partial<Record<ScenarioId, ScenarioResult>>>;
  availableScenarios: ScenarioId[];
  failedScenarioCount: number;
};

function emptyScenarioLoadResult(): ScenarioLoadResult {
  return {
    results: new Map(),
    availableScenarios: ["baseline"],
    failedScenarioCount: 0,
  };
}

async function loadScenarioResults(
  base: string,
  status: StatusResponse,
  areas: AreaDecision[],
): Promise<ScenarioLoadResult> {
  const results = new Map<string, Partial<Record<ScenarioId, ScenarioResult>>>();
  if (
    status.data_state !== "ready"
    && !(status.study_area === "mae_sai_candidate_v1" && status.data_state === "stale")
  ) return emptyScenarioLoadResult();

  const catalogUrl = new URL(`${base}/api/v1/scenarios`);
  catalogUrl.searchParams.set("study_area", status.study_area);
  const catalogResponse = await fetch(catalogUrl.toString(), { cache: "no-store" });
  if (!catalogResponse.ok) throw new Error(`Scenario catalog returned ${catalogResponse.status}.`);
  const definitions = validateScenarioDefinitions(
    asItems<ApiScenarioDefinition>(await catalogResponse.json()),
    status.study_area,
  );
  if (definitions.length === 0) return emptyScenarioLoadResult();

  const baselineByArea = new Map(areas.map((area) => [area.area_id, area]));
  const payloads = await Promise.allSettled(definitions.map(async (definition) => {
    const parameters = Object.fromEntries(
      definition.parameters.map((parameter) => [parameter.name, parameter.default]),
    );
    const response = await fetch(`${base}/api/v1/scenario-runs`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: definition.scenario_id,
        study_area: status.study_area,
        parameters,
      }),
    });
    if (!response.ok) throw new Error(`Scenario API returned ${response.status}.`);
    const payload = await response.json() as ApiScenarioRun;
    assertNoPrivatePaths(payload);
    validateScenarioRun(payload, definition, status, parameters, baselineByArea);
    return { id: definition.scenario_id, payload };
  }));

  const availableScenarios: ScenarioId[] = ["baseline"];
  for (const settled of payloads) {
    if (settled.status === "rejected") continue;
    const { id, payload } = settled.value;
    availableScenarios.push(id);
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
  return {
    results,
    availableScenarios,
    failedScenarioCount: payloads.filter((payload) => payload.status === "rejected").length,
  };
}

function validateScenarioDefinitions(
  definitions: ApiScenarioDefinition[],
  studyArea: string,
): ApiScenarioDefinition[] {
  const expectedConfig = studyArea === "mae_sai_candidate_v1"
    ? "mae-sai-candidate-access-scenarios-v1"
    : "fixture-access-scenarios-v1";
  const scenarioIds = new Set<string>();
  for (const definition of definitions) {
    if (!isServerScenarioId(definition.scenario_id) || scenarioIds.has(definition.scenario_id)) {
      throw new Error("Scenario catalog contains an unknown or duplicate scenario ID.");
    }
    scenarioIds.add(definition.scenario_id);
    if (
      definition.backend_config_version !== expectedConfig
      || definition.access_method !== "nearest_facility_shortest_path_threshold"
      || !Array.isArray(definition.parameters)
    ) throw new Error("Scenario catalog is not bound to the selected dataset contract.");
    const parameterNames = new Set<string>();
    for (const parameter of definition.parameters) {
      if (
        !parameter
        || typeof parameter.name !== "string"
        || !parameter.name
        || parameterNames.has(parameter.name)
        || typeof parameter.required !== "boolean"
      ) throw new Error("Scenario catalog parameter contract failed.");
      parameterNames.add(parameter.name);
      if (parameter.value_type === "integer") {
        if (
          typeof parameter.default !== "number"
          ||
          !Number.isInteger(parameter.default)
          || (typeof parameter.minimum === "number" && parameter.default < parameter.minimum)
          || (typeof parameter.maximum === "number" && parameter.default > parameter.maximum)
        ) throw new Error("Scenario integer default is outside its server-defined range.");
      } else if (parameter.value_type === "string") {
        if (
          typeof parameter.default !== "string"
          || (Array.isArray(parameter.allowed_values) && !parameter.allowed_values.includes(parameter.default))
        ) throw new Error("Scenario string default is not server-defined.");
      } else {
        throw new Error("Scenario catalog contains an unsupported parameter type.");
      }
    }
  }
  return definitions;
}

function validateScenarioRun(
  payload: ApiScenarioRun,
  definition: ApiScenarioDefinition,
  status: StatusResponse,
  parameters: Record<string, string | number>,
  baselineByArea: Map<string, AreaDecision>,
): void {
  if (
    payload.scenario_id !== definition.scenario_id
    || payload.schema_version !== "1.0"
    || typeof payload.run_id !== "string"
    || !payload.run_id
    || payload.study_area !== status.study_area
    || payload.run_status !== "completed"
    || !["ready", "stale"].includes(payload.result_state)
    || payload.backend_config_version !== definition.backend_config_version
    || payload.access_method !== definition.access_method
    || payload.fpps_recalculated !== false
    || payload.dataset_mode !== status.dataset_mode
    || payload.operational_status !== status.operational_status
    || payload.official_warning !== false
    || !isRfc3339WithTimezone(payload.source_timestamp)
    || !isRfc3339WithTimezone(payload.generated_at)
    || payload.confidence_class !== "low"
    || typeof payload.source_name !== "string"
    || !payload.source_name
    || !Array.isArray(payload.assumptions)
    || payload.assumptions.length === 0
    || payload.assumptions.some((assumption) => typeof assumption !== "string" || !assumption)
    || payload.data_version !== status.data_version
    || payload.git_commit !== status.git_commit
    || (
      status.study_area === "mae_sai_candidate_v1"
      && (!isSha256(payload.input_manifest_sha256) || !isSha256(payload.input_receipt_sha256))
    )
    || !sameServerParameters(payload.parameters, parameters)
    || !Array.isArray(payload.areas)
    || payload.areas.length !== baselineByArea.size
  ) throw new Error("Scenario result is not bound to the requested dataset and server definition.");

  const receivedAreaIds = new Set<string>();
  for (const area of payload.areas) {
    const baseline = baselineByArea.get(area.area_id);
    if (
      !baseline
      || receivedAreaIds.has(area.area_id)
      || !Number.isInteger(area.baseline_people_losing_30_min_access)
      || !Number.isInteger(area.scenario_people_losing_30_min_access)
      || !Number.isInteger(area.change_people_losing_30_min_access)
      || area.baseline_people_losing_30_min_access < 0
      || area.scenario_people_losing_30_min_access < 0
      || area.baseline_people_losing_30_min_access !== baseline.people_losing_30_min_access
      || area.scenario_people_losing_30_min_access - area.baseline_people_losing_30_min_access
        !== area.change_people_losing_30_min_access
      || !isNullableFiniteNumber(area.baseline_equity_gap_ratio)
      || !isNullableFiniteNumber(area.scenario_equity_gap_ratio)
      || (area.baseline_equity_gap_ratio !== null && area.baseline_equity_gap_ratio < 0)
      || (area.scenario_equity_gap_ratio !== null && area.scenario_equity_gap_ratio < 0)
      || !sameNullableNumber(area.baseline_equity_gap_ratio, baseline.equity_gap_ratio)
    ) throw new Error("Scenario result area evidence failed its baseline or delta contract.");
    receivedAreaIds.add(area.area_id);
  }
}

function sameServerParameters(
  received: Record<string, string | number>,
  expected: Record<string, string | number>,
): boolean {
  if (!isRecord(received)) return false;
  const receivedKeys = Object.keys(received).sort();
  const expectedKeys = Object.keys(expected).sort();
  return receivedKeys.length === expectedKeys.length
    && receivedKeys.every((key, index) => key === expectedKeys[index] && received[key] === expected[key]);
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value));
}

function sameNullableNumber(left: number | null, right: number | null): boolean {
  if (left === null || right === null) return left === right;
  return Math.abs(left - right) < 1e-9;
}

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function isRfc3339WithTimezone(value: unknown): value is string {
  return typeof value === "string"
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function isServerScenarioId(value: unknown): value is Exclude<ScenarioId, "baseline"> {
  return value === "add_temporary_shelter" || value === "close_road";
}

function isScenarioId(value: unknown): value is ScenarioId {
  return value === "baseline" || isServerScenarioId(value);
}

function adaptArea(area: AreaDecision, scenarios: Map<string, Partial<Record<ScenarioId, ScenarioResult>>>): AreaRecord {
  const fixtureMatch = offlineBundle.areas.find(
    (item) => item.area_id === area.area_id && item.data_version === area.data_version,
  );
  const candidateMatch = area.dataset_mode === "candidate"
    ? maeSaiOfflineBundle.areas.find((item) => (
        item.area_id === area.area_id
        && item.data_version === area.data_version
        && item.git_commit === area.git_commit
        && item.source_timestamp === area.source_timestamp
      ))
    : undefined;
  const offlineMatch = fixtureMatch ?? candidateMatch;
  const baseline: ScenarioResult = {
    people_losing_30_min_access: area.people_losing_30_min_access,
    equity_gap_ratio: area.equity_gap_ratio,
    delta: 0,
  };
  const server = scenarios.get(area.area_id) ?? {};
  return {
    ...area,
    total_population: offlineMatch?.total_population ?? 0,
    candidate_evidence: candidateMatch?.candidate_evidence,
    scenario_results: {
      baseline,
      add_temporary_shelter: server.add_temporary_shelter ?? baseline,
      close_road: server.close_road ?? baseline,
    },
  };
}

async function loadOptionalLayerData(
  base: string,
  layers: LayerCatalogItem[],
  layerId: string,
  role: RoleVisibility,
): Promise<FeatureCollection> {
  const layer = layers.find((item) => item.layer_id === layerId);
  if (!layer || !["ready", "stale"].includes(layer.data_state)) return emptyFeatureCollection(`${layerId}_unavailable`);
  return loadLayerData(base, layers, layerId, role);
}

async function loadLayerData(
  base: string,
  layers: LayerCatalogItem[],
  layerId: string,
  role: RoleVisibility,
): Promise<FeatureCollection> {
  const layer = layers.find((item) => item.layer_id === layerId);
  if (!layer || !["ready", "stale"].includes(layer.data_state)) throw new Error(`Required API layer ${layerId} is unavailable.`);
  assertLayerVisibleForRole(layer, role);
  const parsed = new URL(layer.url, `${base}/`);
  parsed.searchParams.set("role", role);
  const url = parsed.toString();
  if (new URL(url).origin !== new URL(base).origin) throw new Error("Cross-origin layer URL rejected.");
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error(`Layer ${layerId} returned ${response.status}.`);
  const responseContextId = response.headers.get("X-FloodGuard-Evidence-Context-Id");
  if (responseContextId && responseContextId !== layer.evidence_context_id) {
    throw new Error(`Layer ${layerId} response does not match its evidence context.`);
  }
  const collection = await response.json() as FeatureCollection;
  if (collection.type !== "FeatureCollection" || !Array.isArray(collection.features)) throw new Error(`Layer ${layerId} is not GeoJSON.`);
  return collection;
}

export async function loadMaeSaiRoadDetail(
  apiBase: string,
  areaId: string,
  expectedFeatureCount: number,
): Promise<FeatureCollection> {
  const validAreaIds = new Set(maeSaiOfflineBundle.areas.map((area) => area.area_id));
  if (!validAreaIds.has(areaId) || !Number.isInteger(expectedFeatureCount) || expectedFeatureCount < 0) {
    throw new Error("Mae Sai selected-area road request failed its area contract.");
  }
  const base = apiBase.replace(/\/$/, "");
  const url = new URL(`${base}/api/v1/layer-data/road_risk`);
  url.searchParams.set("study_area", "mae_sai_candidate_v1");
  url.searchParams.set("detail", "selected_area");
  url.searchParams.set("area_id", areaId);
  url.searchParams.set("role", "command");
  const response = await fetch(url.toString(), { cache: "no-cache" });
  if (!response.ok) throw new Error(`Mae Sai selected-area road layer returned ${response.status}.`);
  const collection = await response.json() as FeatureCollection;
  assertNoPrivatePaths(collection);
  if (!isFeatureCollection(collection) || collection.features.length !== expectedFeatureCount) {
    throw new Error("Mae Sai selected-area road feature-count contract failed.");
  }
  assertMaeSaiLayerMetadata(collection, "road_risk");
  const query = (collection as unknown as { floodguard_query?: Record<string, unknown> }).floodguard_query;
  if (
    !query
    || query.detail !== "selected_area"
    || query.area_id !== areaId
    || query.returned_feature_count !== expectedFeatureCount
  ) throw new Error("Mae Sai selected-area road lineage contract failed.");

  const roadIds = new Set<string>();
  for (const feature of collection.features) {
    const roadId = String(feature.properties.road_id ?? "");
    if (
      feature.geometry.type !== "LineString"
      && feature.geometry.type !== "MultiLineString"
    ) throw new Error("Mae Sai selected-area road geometry contract failed.");
    if (
      !roadId
      || roadIds.has(roadId)
      || feature.properties.area_id !== areaId
      || feature.properties.dataset_mode !== "candidate"
      || feature.properties.official_warning !== false
      || feature.properties.observation_status !== "modelled_candidate_not_observed"
    ) throw new Error("Mae Sai selected-area road identity or safety contract failed.");
    roadIds.add(roadId);
    for (const [longitude, latitude] of coordinatePairs(feature.geometry.coordinates)) {
      if (longitude < 99.8 || longitude > 100.05 || latitude < 20.24 || latitude > 20.48) {
        throw new Error("Mae Sai selected-area road escaped the declared geographic bounds.");
      }
    }
  }
  return collection;
}

export async function loadApiBrief(
  apiBase: string,
  areaId: string,
  studyArea: StudyAreaId = "fixture_thailand_demo",
): Promise<{ fileName: string; contentMarkdown: string }> {
  const base = apiBase.replace(/\/$/, "");
  const url = new URL(`${base}/api/v1/briefs/${encodeURIComponent(areaId)}`);
  url.searchParams.set("study_area", studyArea);
  const response = await fetch(url.toString(), {
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
assertNoPrivatePaths(maeSaiOfflineBundle);
