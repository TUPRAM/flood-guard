import publicBundleJson from "../../public/offline-demo/mae-sai/public-bundle.json";

import type {
  EvidenceContext,
  EvidenceRecord,
  LayerCatalogItem,
  PublicPreparednessArea,
  StatusResponse,
} from "@floodguard/contracts";

import {
  assertEvidenceContextMatches,
  evidenceRecordMatchesContext,
} from "./evidence-context";
import { assertLayerVisibleForRole, visibleLayersForRole } from "./layer-visibility";
import type {
  FeatureCollection,
  OfflineBundle,
  PublicFloodGuardData,
} from "./types";

const publicBundle = publicBundleJson as unknown as {
  evidence_context: EvidenceContext;
  evidence_record: EvidenceRecord;
  public_areas: PublicPreparednessArea[];
  status: OfflineBundle["status"];
  layers: LayerCatalogItem[];
  hotlines: OfflineBundle["hotlines"];
  shelters: OfflineBundle["shelters"];
};

const STUDY_AREA = "mae_sai_candidate_v1" as const;
const PUBLIC_LAYER_ID = "public_preparedness_areas";
const PUBLIC_ASSET_URL = "/offline-demo/mae-sai/public-areas.json";

export function getPublicOfflineData(
  reason?: string,
  evidenceContextId?: string,
): PublicFloodGuardData {
  const recordMatches = evidenceRecordMatchesContext(
    publicBundle.evidence_record,
    publicBundle.evidence_context,
  );
  const contextMatches = recordMatches && (
    evidenceContextId === undefined
    || evidenceContextId === publicBundle.evidence_context.evidence_context_id
  );
  return {
    role: "public",
    status: publicBundle.status,
    evidenceContext: publicBundle.evidence_context,
    evidenceRecord: recordMatches ? publicBundle.evidence_record : null,
    publicAreas: contextMatches ? publicBundle.public_areas : [],
    layers: contextMatches ? visibleLayersForRole(publicBundle.layers, "public") : [],
    hotlines: publicBundle.hotlines,
    shelters: publicBundle.shelters,
    areaFeatures: emptyFeatureCollection(
      contextMatches ? "public_preparedness_areas_loading" : "requested_context_unavailable",
    ),
    dataState: contextMatches
      ? reason ? "stale_offline" : "loading"
      : "unavailable",
    dataOrigin: "offline_bundle",
    fallbackReason: contextMatches
      ? reason
      : "The requested evidence context is not available in the public offline package.",
  };
}

export async function loadPublicOfflineData(
  reason?: string,
  evidenceContextId?: string,
): Promise<PublicFloodGuardData> {
  const base = getPublicOfflineData(reason, evidenceContextId);
  if (base.dataState === "unavailable") return base;
  try {
    const collection = await loadPublicFeatureCollection(PUBLIC_ASSET_URL);
    assertPublicProjection(collection, base.evidenceContext, base.publicAreas);
    return {
      ...base,
      areaFeatures: collection,
      dataState: reason ? "stale_offline" : "ready",
    };
  } catch (error) {
    const detail = error instanceof Error
      ? error.message
      : "The public offline package is unavailable.";
    return {
      ...base,
      dataState: "unavailable",
      fallbackReason: reason ? `${reason} ${detail}` : detail,
    };
  }
}

export async function loadPublicFloodGuardData(
  apiBase = process.env.NEXT_PUBLIC_FLOODGUARD_API_URL,
  evidenceContextId?: string,
): Promise<PublicFloodGuardData> {
  if (!apiBase) return loadPublicOfflineData(undefined, evidenceContextId);
  try {
    const base = apiBase.replace(/\/$/, "");
    const [statusResponse, contextResponse] = await Promise.all([
      fetch(withStudyArea(`${base}/api/v1/status`), { cache: "no-store" }),
      fetch(withStudyArea(`${base}/api/v1/evidence-context`), { cache: "no-store" }),
    ]);
    if (!statusResponse.ok || !contextResponse.ok) {
      throw new Error(
        `Public evidence API returned ${statusResponse.status}, ${contextResponse.status}.`,
      );
    }
    const [status, context] = await Promise.all([
      statusResponse.json() as Promise<StatusResponse>,
      contextResponse.json() as Promise<EvidenceContext>,
    ]);
    assertEvidenceContextMatches(context, status, STUDY_AREA, evidenceContextId);

    const [areasResponse, layersResponse, recordResponse] = await Promise.all([
      fetch(withStudyArea(`${base}/api/v1/public-areas`), { cache: "no-store" }),
      fetch(withPublicRole(withStudyArea(`${base}/api/v1/layers`)), { cache: "no-store" }),
      fetch(
        `${base}/api/v1/evidence-records/${encodeURIComponent(context.evidence_context_id)}`,
        { cache: "no-store" },
      ),
    ]);
    if (!areasResponse.ok || !layersResponse.ok || !recordResponse.ok) {
      throw new Error(
        `Public context API returned ${areasResponse.status}, ${layersResponse.status}, ${recordResponse.status}.`,
      );
    }
    const [areasPayload, layersPayload, record] = await Promise.all([
      areasResponse.json(),
      layersResponse.json(),
      recordResponse.json() as Promise<EvidenceRecord>,
    ]);
    const publicAreas = asItems<PublicPreparednessArea>(areasPayload);
    const layers = visibleLayersForRole(
      asItems<LayerCatalogItem>(layersPayload),
      "public",
    );
    if (!evidenceRecordMatchesContext(record, context)) {
      throw new Error("Public evidence record does not match the active context.");
    }
    assertPublicRecords(context, status, publicAreas, layers);

    const publicLayer = layers.find((layer) => layer.layer_id === PUBLIC_LAYER_ID);
    if (!publicLayer || !["ready", "stale"].includes(publicLayer.data_state)) {
      throw new Error("The public preparedness layer is unavailable.");
    }
    assertLayerVisibleForRole(publicLayer, "public");
    const layerUrl = new URL(publicLayer.url, `${base}/`);
    layerUrl.searchParams.set("role", "public");
    if (layerUrl.origin !== new URL(base).origin) {
      throw new Error("Cross-origin public layer URL rejected.");
    }
    const layerResponse = await fetch(layerUrl.toString(), { cache: "no-cache" });
    if (!layerResponse.ok) {
      throw new Error(`Public preparedness layer returned ${layerResponse.status}.`);
    }
    const responseContextId = layerResponse.headers.get(
      "X-FloodGuard-Evidence-Context-Id",
    );
    if (responseContextId && responseContextId !== context.evidence_context_id) {
      throw new Error("Public layer response does not match the active context.");
    }
    const areaFeatures = await readFeatureCollection(layerResponse);
    assertPublicProjection(areaFeatures, context, publicAreas);
    return {
      role: "public",
      status: status as OfflineBundle["status"],
      evidenceContext: context,
      evidenceRecord: record,
      publicAreas,
      layers,
      hotlines: publicBundle.hotlines,
      shelters: [],
      areaFeatures,
      dataState: status.data_state,
      dataOrigin: "api",
      apiBase: base,
    };
  } catch (error) {
    const reason = error instanceof Error ? error.message : "Public evidence API unavailable.";
    return loadPublicOfflineData(reason, evidenceContextId);
  }
}

function assertPublicRecords(
  context: EvidenceContext,
  status: StatusResponse,
  publicAreas: PublicPreparednessArea[],
  layers: LayerCatalogItem[],
): void {
  if (
    status.study_area !== STUDY_AREA
    || status.evidence_context_id !== context.evidence_context_id
    || status.evidence_package_id !== context.evidence_package_id
    || publicAreas.length !== 8
    || publicAreas.some((area) => (
      area.evidence_context_id !== context.evidence_context_id
      || area.current_conditions_confirmed
    ))
    || layers.length !== 1
    || layers[0]?.layer_id !== PUBLIC_LAYER_ID
    || layers.some((layer) => (
      layer.evidence_context_id !== context.evidence_context_id
      || layer.evidence_package_id !== context.evidence_package_id
    ))
  ) {
    throw new Error("Public artifacts do not match the active evidence context.");
  }
}

function assertPublicProjection(
  collection: FeatureCollection,
  context: EvidenceContext,
  publicAreas: PublicPreparednessArea[],
): void {
  const expectedIds = new Set(publicAreas.map((area) => area.area_id));
  const metadata = (collection as unknown as {
    floodguard_metadata?: Record<string, unknown>;
  }).floodguard_metadata;
  if (
    collection.features.length !== expectedIds.size
    || expectedIds.size !== 8
    || !metadata
    || metadata.evidence_context_id !== context.evidence_context_id
    || !Array.isArray(metadata.role_visibility)
    || metadata.role_visibility.length !== 1
    || metadata.role_visibility[0] !== "public"
  ) {
    throw new Error("Public area projection failed its context or role contract.");
  }
  const allowedProperties = new Set([
    "schema_version",
    "evidence_context_id",
    "area_id",
    "area_name_th",
    "area_name_en",
    "planning_priority_0_100",
    "evidence_sufficiency",
    "recommendation_code",
    "source_timestamp",
    "freshness",
    "current_conditions_confirmed",
  ]);
  for (const feature of collection.features) {
    if (
      !expectedIds.has(String(feature.properties.area_id ?? ""))
      || feature.properties.evidence_context_id !== context.evidence_context_id
      || feature.properties.current_conditions_confirmed !== false
      || Object.keys(feature.properties).some((key) => !allowedProperties.has(key))
    ) {
      throw new Error("Public area projection contains an unapproved field or identity.");
    }
  }
  assertNoPrivatePaths(collection);
}

async function loadPublicFeatureCollection(url: string): Promise<FeatureCollection> {
  const response = await fetch(url, { cache: "force-cache" });
  if (!response.ok) throw new Error(`Public geospatial asset returned ${response.status}.`);
  return readFeatureCollection(response);
}

async function readFeatureCollection(response: Response): Promise<FeatureCollection> {
  const value = await response.json() as unknown;
  if (!isRecord(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features)) {
    throw new Error("Public geospatial asset is not a FeatureCollection.");
  }
  return value as unknown as FeatureCollection;
}

function asItems<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (isRecord(value) && Array.isArray(value.items)) return value.items as T[];
  throw new Error("Public API collection response is not an array.");
}

function withStudyArea(url: string): string {
  const parsed = new URL(url);
  parsed.searchParams.set("study_area", STUDY_AREA);
  return parsed.toString();
}

function withPublicRole(url: string): string {
  const parsed = new URL(url);
  parsed.searchParams.set("role", "public");
  return parsed.toString();
}

function emptyFeatureCollection(name: string): FeatureCollection {
  return { type: "FeatureCollection", name, features: [] };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertNoPrivatePaths(value: unknown): void {
  const privatePath = /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;
  const strings: string[] = [];
  JSON.stringify(value, (key, candidate: unknown) => {
    strings.push(key);
    if (typeof candidate === "string") strings.push(candidate);
    return candidate;
  });
  if (strings.some((candidate) => privatePath.test(candidate))) {
    throw new Error("Public data provider rejected a private absolute path.");
  }
}

assertNoPrivatePaths(publicBundle);
