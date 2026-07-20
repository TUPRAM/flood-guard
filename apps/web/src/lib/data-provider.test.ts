import { afterEach, describe, expect, it, vi } from "vitest";

import maeSaiAccess from "../../public/offline-demo/mae-sai/access-hotspots.json";
import maeSaiAreas from "../../public/offline-demo/mae-sai/areas.json";
import maeSaiBundle from "../../public/offline-demo/mae-sai/bundle.json";
import maeSaiFacilities from "../../public/offline-demo/mae-sai/facilities.json";
import maeSaiManifest from "../../public/offline-demo/mae-sai/manifest.json";
import maeSaiRoads from "../../public/offline-demo/mae-sai/roads.json";

import {
  LAST_KNOWN_API_SNAPSHOT_KEY,
  areaFeatures,
  contextFeatures,
  assertNoPrivatePaths,
  getOfflineData,
  loadApiBrief,
  loadFloodGuardData,
  loadMaeSaiRoadDetail,
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

  it("loads the Mae Sai command bundle from same-origin offline assets", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/areas.json")) return Response.json(maeSaiAreas);
      if (url.endsWith("/roads.json")) return Response.json(maeSaiRoads);
      if (url.endsWith("/facilities.json")) return Response.json(maeSaiFacilities);
      if (url.endsWith("/access-hotspots.json")) return Response.json(maeSaiAccess);
      return new Response(null, { status: 404 });
    }));

    const data = await loadFloodGuardData(undefined, null, "mae_sai_candidate_v1");

    expect(data.status.study_area).toBe("mae_sai_candidate_v1");
    expect(data.status.dataset_mode).toBe("candidate");
    expect(data.status.operational_status).toBe("non_operational");
    expect(data.status.official_warning).toBe(false);
    expect(data.scenarioState).toBe("unavailable");
    expect(data.areaFeatures.features).toHaveLength(8);
    expect(data.roadFeatures.features).toHaveLength(4_458);
    expect(data.areas.reduce((total, area) => total + (area.candidate_evidence?.road_count ?? 0), 0)).toBe(4_458);
    expect(data.facilityFeatures.features).toHaveLength(42);
    expect(data.accessFeatures.features).toHaveLength(8);
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

describe("study-area-scoped API artifacts", () => {
  it("requests a Mae Sai brief from the selected dataset adapter", async () => {
    let requestedUrl = "";
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      requestedUrl = String(input);
      return Response.json({
        file_name: "floodguard-TH570903-brief.md",
        content_markdown: "# Mae Sai candidate brief\n\nNon-operational; not an official warning.",
      });
    }));

    const brief = await loadApiBrief("https://api.example", "TH570903", "mae_sai_candidate_v1");

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe("/api/v1/briefs/TH570903");
    expect(url.searchParams.get("study_area")).toBe("mae_sai_candidate_v1");
    expect(brief.fileName).toBe("floodguard-TH570903-brief.md");
  });

  it("loads checksum-bound selected-area road detail instead of an unbounded road layer", async () => {
    let requestedUrl = "";
    let requestedCache: RequestCache | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requestedUrl = String(input);
      requestedCache = init?.cache;
      return Response.json(maeSaiSelectedRoads("TH570903"));
    }));

    const roads = await loadMaeSaiRoadDetail("https://api.example", "TH570903", 451);

    const url = new URL(requestedUrl);
    expect(url.pathname).toBe("/api/v1/layer-data/road_risk");
    expect(url.searchParams.get("study_area")).toBe("mae_sai_candidate_v1");
    expect(url.searchParams.get("detail")).toBe("selected_area");
    expect(url.searchParams.get("area_id")).toBe("TH570903");
    expect(requestedCache).toBe("no-cache");
    expect(roads.features).toHaveLength(451);
    expect(roads.features.every((feature) => feature.properties.area_id === "TH570903")).toBe(true);
  });
});

describe("partial API availability", () => {
  it("rejects a substituted Mae Sai data version instead of merging local evidence", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "https://api.example");
      if (url.pathname === "/api/v1/status") {
        return Response.json({ ...maeSaiApiStatus(), data_version: "substituted-mae-sai-v2" });
      }
      if (url.pathname === "/api/v1/areas") return Response.json({ items: maeSaiApiAreas() });
      if (url.pathname === "/api/v1/layers") return Response.json({ items: maeSaiApiLayers() });
      if (url.pathname.endsWith("/areas.json")) return Response.json(maeSaiAreas);
      if (url.pathname.endsWith("/roads.json")) return Response.json(maeSaiRoads);
      if (url.pathname.endsWith("/facilities.json")) return Response.json(maeSaiFacilities);
      if (url.pathname.endsWith("/access-hotspots.json")) return Response.json(maeSaiAccess);
      return new Response(null, { status: 503 });
    }));

    const data = await loadFloodGuardData("https://api.example", null, "mae_sai_candidate_v1");

    expect(data.dataOrigin).toBe("offline_bundle");
    expect(data.status.data_version).toBe(maeSaiBundle.status.data_version);
    expect(data.fallbackReason).toMatch(/study-area identity or safety contract failed/i);
  });

  it("rejects substituted non-road layer lineage and uses the pinned offline bundle", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "https://api.example");
      if (url.pathname === "/api/v1/layer-data/facilities") {
        const payload = maeSaiApiLayer("facilities", maeSaiFacilities);
        payload.floodguard_metadata.artifact_sha256 = "0".repeat(64);
        return Response.json(payload);
      }
      return maeSaiApiFetchWithoutScenarios(input);
    }));

    const data = await loadFloodGuardData("https://api.example", null, "mae_sai_candidate_v1");

    expect(data.dataOrigin).toBe("offline_bundle");
    expect(data.dataState).toBe("stale_offline");
    expect(data.fallbackReason).toMatch(/facilities lineage metadata contract failed/i);
    expect(data.facilityFeatures.features).toHaveLength(42);
  });

  it("uses only the Mae Sai scenario IDs and parameter defaults returned by the server", async () => {
    const postedBodies: Array<Record<string, unknown>> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "https://api.example");
      if (url.pathname === "/api/v1/status") return Response.json(maeSaiApiStatus());
      if (url.pathname === "/api/v1/areas") return Response.json({ items: maeSaiApiAreas() });
      if (url.pathname === "/api/v1/layers") return Response.json({ items: maeSaiApiLayers() });
      if (url.pathname === "/api/v1/scenarios") {
        expect(url.searchParams.get("study_area")).toBe("mae_sai_candidate_v1");
        return Response.json({ items: maeSaiScenarioDefinitions() });
      }
      if (url.pathname === "/api/v1/scenario-runs") {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        postedBodies.push(body);
        return Response.json(maeSaiScenarioResponse(body));
      }
      if (url.pathname === "/api/v1/layer-data/priority_areas") return Response.json(maeSaiApiLayer("priority_areas", maeSaiAreas));
      if (url.pathname === "/api/v1/layer-data/road_risk") return Response.json(maeSaiRegionalRoads());
      if (url.pathname === "/api/v1/layer-data/facilities") return Response.json(maeSaiApiLayer("facilities", maeSaiFacilities));
      if (url.pathname === "/api/v1/layer-data/access_hotspots") return Response.json(maeSaiApiLayer("access_hotspots", maeSaiAccess));
      if (url.pathname === "/offline-demo/mae-sai/areas.json") return Response.json(maeSaiAreas);
      if (url.pathname === "/offline-demo/mae-sai/roads.json") return Response.json(maeSaiRoads);
      if (url.pathname === "/offline-demo/mae-sai/facilities.json") return Response.json(maeSaiFacilities);
      if (url.pathname === "/offline-demo/mae-sai/access-hotspots.json") return Response.json(maeSaiAccess);
      return new Response(null, { status: 503 });
    }));

    const data = await loadFloodGuardData("https://api.example", null, "mae_sai_candidate_v1");

    expect(data.dataOrigin).toBe("api");
    expect(data.dataState).toBe("stale");
    expect(data.scenarioState).toBe("ready");
    expect(data.availableScenarios).toEqual(["baseline", "add_temporary_shelter", "close_road"]);
    expect(postedBodies).toEqual([
      {
        scenario_id: "add_temporary_shelter",
        study_area: "mae_sai_candidate_v1",
        parameters: { node_id: "N-99.9742609-20.4457677", capacity: 500 },
      },
      {
        scenario_id: "close_road",
        study_area: "mae_sai_candidate_v1",
        parameters: { edge_id: "MS-EDGE-0008687" },
      },
    ]);
    expect(data.areas.find((area) => area.area_id === "TH570903")?.scenario_results.add_temporary_shelter).toEqual({
      people_losing_30_min_access: 90,
      equity_gap_ratio: 1.5,
      delta: -5_704,
    });
    expect(data.areas.find((area) => area.area_id === "TH570903")?.total_population).toBe(6_708);
    expect(data.areas.find((area) => area.area_id === "TH570903")?.candidate_evidence?.road_count).toBe(451);
  });

  it("keeps a substituted Mae Sai scenario catalog unavailable without inventing parameters", async () => {
    const post = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "https://api.example");
      if (url.pathname === "/api/v1/status") return Response.json(maeSaiApiStatus());
      if (url.pathname === "/api/v1/areas") return Response.json({ items: maeSaiApiAreas() });
      if (url.pathname === "/api/v1/layers") return Response.json({ items: maeSaiApiLayers() });
      if (url.pathname === "/api/v1/scenarios") {
        const definitions = maeSaiScenarioDefinitions();
        definitions[1].parameters[0].default = "SUBSTITUTED-EDGE";
        return Response.json({ items: definitions });
      }
      if (url.pathname === "/api/v1/scenario-runs") {
        post(init?.body);
        return new Response(null, { status: 500 });
      }
      if (url.pathname === "/api/v1/layer-data/priority_areas") return Response.json(maeSaiApiLayer("priority_areas", maeSaiAreas));
      if (url.pathname === "/api/v1/layer-data/road_risk") return Response.json(maeSaiRegionalRoads());
      if (url.pathname === "/api/v1/layer-data/facilities") return Response.json(maeSaiApiLayer("facilities", maeSaiFacilities));
      if (url.pathname === "/api/v1/layer-data/access_hotspots") return Response.json(maeSaiApiLayer("access_hotspots", maeSaiAccess));
      if (url.pathname === "/offline-demo/mae-sai/areas.json") return Response.json(maeSaiAreas);
      if (url.pathname === "/offline-demo/mae-sai/roads.json") return Response.json(maeSaiRoads);
      if (url.pathname === "/offline-demo/mae-sai/facilities.json") return Response.json(maeSaiFacilities);
      if (url.pathname === "/offline-demo/mae-sai/access-hotspots.json") return Response.json(maeSaiAccess);
      return new Response(null, { status: 503 });
    }));

    const data = await loadFloodGuardData("https://api.example", null, "mae_sai_candidate_v1");

    expect(data.dataOrigin).toBe("api");
    expect(data.scenarioState).toBe("unavailable");
    expect(data.availableScenarios).toEqual(["baseline"]);
    expect(data.degradedReason).toMatch(/Scenario artifacts unavailable/);
    expect(post).not.toHaveBeenCalled();
  });

  it("enables only the Mae Sai scenario whose server run completed and validated", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "https://api.example");
      if (url.pathname === "/api/v1/status") return Response.json(maeSaiApiStatus());
      if (url.pathname === "/api/v1/areas") return Response.json({ items: maeSaiApiAreas() });
      if (url.pathname === "/api/v1/layers") return Response.json({ items: maeSaiApiLayers() });
      if (url.pathname === "/api/v1/scenarios") return Response.json({ items: maeSaiScenarioDefinitions() });
      if (url.pathname === "/api/v1/scenario-runs") {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return body.scenario_id === "close_road"
          ? new Response(null, { status: 503 })
          : Response.json(maeSaiScenarioResponse(body));
      }
      if (url.pathname === "/api/v1/layer-data/priority_areas") return Response.json(maeSaiApiLayer("priority_areas", maeSaiAreas));
      if (url.pathname === "/api/v1/layer-data/road_risk") return Response.json(maeSaiRegionalRoads());
      if (url.pathname === "/api/v1/layer-data/facilities") return Response.json(maeSaiApiLayer("facilities", maeSaiFacilities));
      if (url.pathname === "/api/v1/layer-data/access_hotspots") return Response.json(maeSaiApiLayer("access_hotspots", maeSaiAccess));
      if (url.pathname === "/offline-demo/mae-sai/areas.json") return Response.json(maeSaiAreas);
      if (url.pathname === "/offline-demo/mae-sai/roads.json") return Response.json(maeSaiRoads);
      if (url.pathname === "/offline-demo/mae-sai/facilities.json") return Response.json(maeSaiFacilities);
      if (url.pathname === "/offline-demo/mae-sai/access-hotspots.json") return Response.json(maeSaiAccess);
      return new Response(null, { status: 503 });
    }));

    const data = await loadFloodGuardData("https://api.example", null, "mae_sai_candidate_v1");

    expect(data.scenarioState).toBe("ready");
    expect(data.availableScenarios).toEqual(["baseline", "add_temporary_shelter"]);
    expect(data.degradedReason).toMatch(/1 server-defined scenario artifact is unavailable/);
    expect(data.areas.find((area) => area.area_id === "TH570903")?.scenario_results.close_road.delta).toBe(0);
  });

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
  it("does not write the complete Mae Sai geospatial bundle to localStorage", async () => {
    const storage = memoryStorage();
    vi.stubGlobal("fetch", vi.fn(maeSaiApiFetchWithoutScenarios));

    const data = await loadFloodGuardData(
      "https://api.example",
      storage,
      "mae_sai_candidate_v1",
    );

    expect(data.dataOrigin).toBe("api");
    expect(data.roadFeatures.features).toHaveLength(750);
    expect(data.areas.reduce((total, area) => total + (area.candidate_evidence?.road_count ?? 0), 0)).toBe(4_458);
    expect(storage.getItem(`${LAST_KNOWN_API_SNAPSHOT_KEY}:mae_sai_candidate_v1`)).toBeNull();
  });

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

function maeSaiApiStatus() {
  return {
    ...maeSaiBundle.status,
    data_state: "stale",
  };
}

function maeSaiApiAreas() {
  return maeSaiBundle.areas;
}

function maeSaiApiLayers() {
  return maeSaiBundle.layers.map((layer) => ({
    ...layer,
    data_state: "stale",
    url: `/api/v1/layer-data/${layer.layer_id}?study_area=mae_sai_candidate_v1`,
  }));
}

function maeSaiApiLayer<T extends { features: unknown[] }>(layerId: string, collection: T) {
  return {
    ...collection,
    floodguard_metadata: maeSaiLayerMetadata(layerId),
    floodguard_query: {
      area_id: null,
      bbox: null,
      facility_type: null,
      verification_status: null,
      minimum_risk: 0,
      detail: "regional",
      returned_feature_count: collection.features.length,
    },
  };
}

function maeSaiLayerMetadata(layerId: string) {
  const layer = maeSaiManifest.layers.find((item) => item.layer_id === layerId);
  return {
    schema_version: "1.0",
    study_area_id: "mae_sai_candidate_v1",
    dataset_mode: "candidate",
    operational_status: "non_operational",
    official_warning: false,
    data_version: maeSaiBundle.status.data_version,
    artifact_sha256: layer?.source_sha256,
    processing_allowed: true,
    can_feed_decision_layer: false,
    reason_blocked: "Candidate layer is not qualified for decision promotion.",
  };
}

function maeSaiRegionalRoads() {
  const features = maeSaiRoads.features.slice(0, 750).map((feature) => ({
    ...feature,
    properties: {
      ...feature.properties,
      dataset_mode: "candidate",
      official_warning: false,
      observation_status: "modelled_candidate_not_observed",
    },
  }));
  return {
    ...maeSaiRoads,
    features,
    floodguard_metadata: maeSaiLayerMetadata("road_risk"),
    floodguard_query: {
      area_id: null,
      bbox: null,
      facility_type: null,
      verification_status: null,
      minimum_risk: 0,
      detail: "regional",
      returned_feature_count: features.length,
    },
  };
}

function maeSaiSelectedRoads(areaId: string) {
  const features = maeSaiRoads.features
    .filter((feature) => feature.properties.area_id === areaId)
    .map((feature) => ({
      ...feature,
      properties: {
        ...feature.properties,
        dataset_mode: "candidate",
        operational_status: "non_operational",
        official_warning: false,
        observation_status: "modelled_candidate_not_observed",
      },
    }));
  return {
    ...maeSaiRoads,
    features,
    floodguard_metadata: maeSaiLayerMetadata("road_risk"),
    floodguard_query: {
      area_id: areaId,
      bbox: null,
      facility_type: null,
      verification_status: null,
      minimum_risk: 0,
      detail: "selected_area",
      returned_feature_count: features.length,
    },
  };
}

function maeSaiScenarioDefinitions() {
  return [
    {
      scenario_id: "add_temporary_shelter",
      parameters: [
        {
          name: "node_id",
          value_type: "string",
          required: false,
          default: "N-99.9742609-20.4457677",
          minimum: null,
          maximum: null,
          allowed_values: ["N-99.9742609-20.4457677"],
        },
        {
          name: "capacity",
          value_type: "integer",
          required: false,
          default: 500,
          minimum: 1,
          maximum: 5000,
          allowed_values: null,
        },
      ],
      backend_config_version: "mae-sai-candidate-access-scenarios-v1",
      access_method: "nearest_facility_shortest_path_threshold",
    },
    {
      scenario_id: "close_road",
      parameters: [
        {
          name: "edge_id",
          value_type: "string",
          required: false,
          default: "MS-EDGE-0008687",
          minimum: null,
          maximum: null,
          allowed_values: ["MS-EDGE-0008687"],
        },
      ],
      backend_config_version: "mae-sai-candidate-access-scenarios-v1",
      access_method: "nearest_facility_shortest_path_threshold",
    },
  ];
}

function maeSaiScenarioResponse(request: Record<string, unknown>) {
  const scenarioId = String(request.scenario_id);
  return {
    schema_version: "1.0",
    run_id: `mae-sai-${scenarioId}-test`,
    scenario_id: scenarioId,
    study_area: "mae_sai_candidate_v1",
    parameters: request.parameters,
    run_status: "completed",
    result_state: "stale",
    backend_config_version: "mae-sai-candidate-access-scenarios-v1",
    access_method: "nearest_facility_shortest_path_threshold",
    fpps_recalculated: false,
    dataset_mode: "candidate",
    operational_status: "non_operational",
    official_warning: false,
    source_timestamp: "2026-07-09T14:53:08Z",
    generated_at: "2026-07-18T12:00:00Z",
    confidence_class: "low",
    source_name: "FloodGuard immutable Mae Sai candidate scenario inputs",
    assumptions: ["Historic candidate access scenario; not an observed closure or official warning."],
    data_version: maeSaiBundle.status.data_version,
    git_commit: maeSaiBundle.status.git_commit,
    input_manifest_sha256: "a".repeat(64),
    input_receipt_sha256: "b".repeat(64),
    areas: maeSaiBundle.areas.map((area) => {
      const changed = area.area_id === "TH570903";
      const scenarioPeople = changed
        ? scenarioId === "add_temporary_shelter" ? 90 : 240
        : area.people_losing_30_min_access;
      const scenarioEquity = changed
        ? scenarioId === "add_temporary_shelter" ? 1.5 : 2.4
        : area.equity_gap_ratio;
      return {
        area_id: area.area_id,
        baseline_people_losing_30_min_access: area.people_losing_30_min_access,
        scenario_people_losing_30_min_access: scenarioPeople,
        change_people_losing_30_min_access: scenarioPeople - area.people_losing_30_min_access,
        baseline_equity_gap_ratio: area.equity_gap_ratio,
        scenario_equity_gap_ratio: scenarioEquity,
      };
    }),
  };
}

async function maeSaiApiFetchWithoutScenarios(input: RequestInfo | URL): Promise<Response> {
  const url = new URL(String(input), "https://api.example");
  if (url.pathname === "/api/v1/status") return Response.json(maeSaiApiStatus());
  if (url.pathname === "/api/v1/areas") return Response.json({ items: maeSaiApiAreas() });
  if (url.pathname === "/api/v1/layers") return Response.json({ items: maeSaiApiLayers() });
  if (url.pathname === "/api/v1/scenarios") return Response.json({ items: [] });
  if (url.pathname === "/api/v1/layer-data/priority_areas") return Response.json(maeSaiApiLayer("priority_areas", maeSaiAreas));
  if (url.pathname === "/api/v1/layer-data/road_risk") return Response.json(maeSaiRegionalRoads());
  if (url.pathname === "/api/v1/layer-data/facilities") return Response.json(maeSaiApiLayer("facilities", maeSaiFacilities));
  if (url.pathname === "/api/v1/layer-data/access_hotspots") return Response.json(maeSaiApiLayer("access_hotspots", maeSaiAccess));
  if (url.pathname === "/offline-demo/mae-sai/areas.json") return Response.json(maeSaiAreas);
  if (url.pathname === "/offline-demo/mae-sai/roads.json") return Response.json(maeSaiRoads);
  if (url.pathname === "/offline-demo/mae-sai/facilities.json") return Response.json(maeSaiFacilities);
  if (url.pathname === "/offline-demo/mae-sai/access-hotspots.json") return Response.json(maeSaiAccess);
  return new Response(null, { status: 503 });
}

function memoryStorage(): SnapshotStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
  };
}
