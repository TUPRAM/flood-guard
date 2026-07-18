import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LAST_KNOWN_API_SNAPSHOT_KEY,
  areaFeatures,
  contextFeatures,
  assertNoPrivatePaths,
  getOfflineData,
  loadFloodGuardData,
  roadFeatures,
  type SnapshotStorage,
} from "./data-provider";

afterEach(() => vi.unstubAllGlobals());

describe("offline judging bundle", () => {
  it("is explicitly non-operational and never an official warning", () => {
    const data = getOfflineData();
    expect(data.dataOrigin).toBe("offline_bundle");
    expect(data.status.dataset_mode).toBe("fixture_demo");
    expect(data.status.operational_status).toBe("non_operational");
    expect(data.status.official_warning).toBe(false);
    expect(data.pilot_readiness.operational_status).toBe("non_operational");
    expect(data.pilot_readiness.agency_operational_allowed).toBe(false);
    expect(data.areas).toHaveLength(5);
    expect(data.areas.every((area) => area.official_warning === false)).toBe(true);
  });

  it("ships geospatial features instead of a schematic map", () => {
    expect(areaFeatures.type).toBe("FeatureCollection");
    expect(areaFeatures.features).toHaveLength(5);
    expect(roadFeatures.features).toHaveLength(3);
    expect(contextFeatures.features).toHaveLength(8);
    expect(areaFeatures.features.every((feature) => feature.geometry.type === "Polygon")).toBe(true);
  });

  it("does not permit a model run to feed decisions", () => {
    const data = getOfflineData();
    expect(data.model_runs.length).toBeGreaterThan(0);
    expect(data.model_runs.every((run) => run.can_feed_decision_layer === false)).toBe(true);
  });
});

describe("private path safety", () => {
  it.each([
    "C:\\Users\\person\\private.tif",
    "C:/Users/person/private.tif",
    "D:\\data\\private.tif",
    "artifact at C:\\Users\\person\\private.tif",
    "\\\\server\\share\\private.tif",
    "file:///tmp/private.tif",
    "/home/person/private.tif",
    "/Users/person/private.tif",
    "/root/person/private.tif",
    "see /tmp/person/private.tif",
  ])("rejects %s", (path) => {
    expect(() => assertNoPrivatePaths({ path })).toThrow(/private absolute path/i);
  });

  it("allows redacted external workspace hints", () => {
    expect(() => assertNoPrivatePaths({ path: "external-data-workspace/run-001" })).not.toThrow();
  });
});

describe("partial API availability", () => {
  it("keeps current core decisions when Studio, road, and scenario artifacts fail", async () => {
    const fixture = getOfflineData();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/status")) return Response.json(fixture.status);
      if (url.endsWith("/api/v1/areas")) return Response.json({ items: fixture.areas });
      if (url.endsWith("/api/v1/layers")) return Response.json({ items: fixture.layers });
      if (url.endsWith("/offline-demo/areas.geojson")) return Response.json(areaFeatures);
      return new Response(null, { status: 503 });
    }));

    const data = await loadFloodGuardData("https://api.example");

    expect(data.dataOrigin).toBe("api");
    expect(data.fallbackReason).toBeUndefined();
    expect(data.areas).toHaveLength(fixture.areas.length);
    expect(data.areaFeatures.features).toHaveLength(areaFeatures.features.length);
    expect(data.roadFeatures.features).toHaveLength(0);
    expect(data.contextFeatures.features).toHaveLength(contextFeatures.features.length);
    expect(data.model_runs).toHaveLength(0);
    expect(data.readiness).toEqual(expect.arrayContaining([expect.objectContaining({ status: "unavailable" })]));
    expect(data.scenarioState).toBe("unavailable");
    expect(data.degradedReason).toMatch(/Model-run catalog unavailable/);
  });

  it("downgrades agency claims when pilot acceptance cannot be revalidated", async () => {
    const fixture = getOfflineData();
    const apiStatus = {
      ...fixture.status,
      dataset_mode: "official_input" as const,
      operational_status: "agency_operational" as const,
      official_warning: true,
      study_area: "example_study_area",
      data_version: "example-official-v1",
    };
    const apiAreas = fixture.areas.map((area) => ({
      ...area,
      dataset_mode: "official_input" as const,
      operational_status: "agency_operational" as const,
      official_warning: true,
    }));
    const apiLayers = fixture.layers.map((layer) => ({
      ...layer,
      dataset_mode: "official_input" as const,
      operational_status: "agency_operational" as const,
      official_warning: true,
    }));
    const apiRuns = fixture.model_runs.map((run) => ({
      ...run,
      dataset_mode: "official_input" as const,
      operational_status: "agency_operational" as const,
      official_warning: true,
      can_feed_decision_layer: true,
      reason_blocked: "",
    }));
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/status")) return Response.json(apiStatus);
      if (url.endsWith("/api/v1/areas")) return Response.json({ items: apiAreas });
      if (url.endsWith("/api/v1/layers")) return Response.json({ items: apiLayers });
      if (url.endsWith("/api/v1/model-runs")) return Response.json({ items: apiRuns });
      if (url.endsWith("/api/v1/data-readiness")) return Response.json({ items: fixture.readiness });
      if (url.endsWith("/api/v1/pilot/readiness")) return new Response(null, { status: 503 });
      if (url.endsWith("/offline-demo/areas.geojson")) return Response.json(areaFeatures);
      if (url.endsWith("/offline-demo/roads.geojson")) return Response.json(roadFeatures);
      return new Response(null, { status: 404 });
    }));

    const data = await loadFloodGuardData("https://api.example");

    expect(data.dataOrigin).toBe("api");
    expect(data.status.operational_status).toBe("non_operational");
    expect(data.status.official_warning).toBe(false);
    expect(data.areas.every((area) => area.operational_status === "non_operational")).toBe(true);
    expect(data.layers.every((layer) => layer.operational_status === "non_operational")).toBe(true);
    expect(data.model_runs.every((run) => run.can_feed_decision_layer === false)).toBe(true);
    expect(data.pilot_readiness.agency_operational_allowed).toBe(false);
    expect(data.degradedReason).toMatch(/Pilot-readiness control unavailable/);
  });

  it("uses the stale offline fixture only when the core API fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));

    const data = await loadFloodGuardData("https://api.example");

    expect(data.dataOrigin).toBe("offline_bundle");
    expect(data.dataState).toBe("stale_offline");
    expect(data.fallbackReason).toMatch(/Core API returned 503/);
  });
});

describe("last-known API snapshot", () => {
  it("caches a successful API payload and reuses it as stale/offline", async () => {
    const fixture = getOfflineData();
    const storage = memoryStorage();
    const apiStatus = {
      ...fixture.status,
      dataset_mode: "official_input" as const,
      operational_status: "agency_operational" as const,
      study_area: "candidate_api_area",
      source_name: "Current contract API",
      data_state: "ready" as const,
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/v1/status")) return Response.json(apiStatus);
      if (url.endsWith("/api/v1/areas")) return Response.json({ items: fixture.areas });
      if (url.endsWith("/api/v1/layers")) return Response.json({ items: fixture.layers });
      if (url.endsWith("/api/v1/model-runs")) return Response.json({ items: [] });
      if (url.endsWith("/api/v1/data-readiness")) return Response.json({ items: fixture.readiness });
      if (url.endsWith("/api/v1/pilot/readiness")) return Response.json({
        ...fixture.pilot_readiness,
        operational_status: "agency_operational",
        agency_operational_allowed: true,
        identity_state: "configured",
        acceptance_receipt_state: "accepted",
        audit_state: "valid",
        retention_state: "configured",
        deployment_state: "accepted_for_agency_operation",
        acceptance_criteria: fixture.pilot_readiness.acceptance_criteria.map((item) => ({
          ...item,
          status: "accepted",
        })),
        reason_blocked_th: "",
        reason_blocked_en: "",
      });
      if (url.endsWith("/offline-demo/areas.geojson")) return Response.json(areaFeatures);
      if (url.endsWith("/offline-demo/roads.geojson")) return Response.json(roadFeatures);
      return new Response(null, { status: 404 });
    }));

    const current = await loadFloodGuardData("https://api.example", storage);
    expect(current.dataOrigin).toBe("api");
    expect(current.status.source_name).toBe("Current contract API");
    expect(current.pilot_readiness.agency_operational_allowed).toBe(true);
    expect(storage.getItem(LAST_KNOWN_API_SNAPSHOT_KEY)).not.toBeNull();

    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));
    const cached = await loadFloodGuardData("https://api.example", storage);

    expect(cached.dataOrigin).toBe("cached_api");
    expect(cached.dataState).toBe("stale_offline");
    expect(cached.scenarioState).toBe("unavailable");
    expect(cached.status.source_name).toBe("Current contract API");
    expect(cached.status.operational_status).toBe("non_operational");
    expect(cached.status.official_warning).toBe(false);
    expect(cached.areas.every((area) => area.operational_status === "non_operational")).toBe(true);
    expect(cached.model_runs.every((run) => run.can_feed_decision_layer === false)).toBe(true);
    expect(cached.pilot_readiness.operational_status).toBe("non_operational");
    expect(cached.pilot_readiness.agency_operational_allowed).toBe(false);
    expect(cached.pilot_readiness.deployment_state).toBe("degraded");
    expect(cached.status.source_timestamp).toBe(current.status.source_timestamp);
    expect(cached.snapshotCachedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(cached.fallbackReason).toMatch(/Core API returned 503/);
    expect(cached.apiBase).toBeUndefined();
  });

  it("keeps a no-cache fallback labelled as the bundled fixture", async () => {
    const storage = memoryStorage();
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 503 })));

    const fallback = await loadFloodGuardData("https://api.example", storage);

    expect(fallback.dataOrigin).toBe("offline_bundle");
    expect(fallback.status.dataset_mode).toBe("fixture_demo");
    expect(fallback.status.operational_status).toBe("non_operational");
    expect(fallback.status.official_warning).toBe(false);
    expect(fallback.snapshotCachedAt).toBeUndefined();
  });

  it("ignores malformed or private-path cache entries", async () => {
    const storage = memoryStorage();
    storage.setItem(LAST_KNOWN_API_SNAPSHOT_KEY, JSON.stringify({
      schema_version: "1.0",
      cached_at: "2026-07-16T08:00:00Z",
      data: {
        ...getOfflineData(),
        dataOrigin: "api",
        private_path: "C:\\Users\\person\\secret.tif",
      },
    }));

    const fallback = await loadFloodGuardData(undefined, storage);

    expect(fallback.dataOrigin).toBe("offline_bundle");
    expect(fallback.status.official_warning).toBe(false);
  });
});

function memoryStorage(): SnapshotStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}
