import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import publicAreasGeoJson from "../../public/offline-demo/mae-sai/public-areas.json";
import publicBundleJson from "../../public/offline-demo/mae-sai/public-bundle.json";

import {
  loadPublicFloodGuardData,
  loadPublicOfflineData,
} from "./public-data-provider";

const publicBundle = publicBundleJson;

afterEach(() => vi.unstubAllGlobals());

describe("public-only data provider", () => {
  it("has no static dependency on the staff provider or restricted asset paths", () => {
    const source = readFileSync(new URL("./public-data-provider.ts", import.meta.url), "utf8");
    const hookSource = readFileSync(
      new URL("./use-public-floodguard-data.ts", import.meta.url),
      "utf8",
    );
    expect(source).not.toContain('from "./data-provider"');
    expect(hookSource).not.toContain('from "./data-provider"');
    expect(source).not.toMatch(/(?:roads|facilities|access-hotspots)\.json/);
    expect(source).not.toContain("mae-sai/bundle.json");
  });

  it("loads only the reduced same-origin public projection offline", async () => {
    const requestedUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      requestedUrls.push(String(input));
      return Response.json(publicAreasGeoJson);
    }));

    const data = await loadPublicOfflineData();

    expect(requestedUrls).toEqual(["/offline-demo/mae-sai/public-areas.json"]);
    expect(data.dataState).toBe("ready");
    expect(data.role).toBe("public");
    expect(data.publicAreas).toHaveLength(8);
    expect(data.areaFeatures.features).toHaveLength(8);
    expect(data.layers.map((layer) => layer.layer_id)).toEqual([
      "public_preparedness_areas",
    ]);
    expect(data.shelters).toEqual([]);
  });

  it("fails closed before fetching when a deep-linked context is unavailable", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const data = await loadPublicOfflineData("network unavailable", "wrong-context");

    expect(fetchMock).not.toHaveBeenCalled();
    expect(data.dataState).toBe("unavailable");
    expect(data.publicAreas).toEqual([]);
    expect(data.areaFeatures.features).toEqual([]);
  });

  it("requests a role-scoped, exact-context API projection", async () => {
    const requestedUrls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "https://api.example");
      requestedUrls.push(url.toString());
      if (url.pathname === "/api/v1/status") {
        return Response.json({ ...publicBundle.status, data_state: "stale" });
      }
      if (url.pathname === "/api/v1/evidence-context") {
        return Response.json(publicBundle.evidence_context);
      }
      if (url.pathname === "/api/v1/public-areas") {
        return Response.json({ items: publicBundle.public_areas });
      }
      if (url.pathname === "/api/v1/layers") {
        return Response.json({
          items: publicBundle.layers.map((layer) => ({
            ...layer,
            data_state: "stale",
            url: "/api/v1/layer-data/public_preparedness_areas?study_area=mae_sai_candidate_v1",
          })),
        });
      }
      if (url.pathname.startsWith("/api/v1/evidence-records/")) {
        return Response.json(publicBundle.evidence_record);
      }
      if (url.pathname === "/api/v1/layer-data/public_preparedness_areas") {
        return Response.json(publicAreasGeoJson, {
          headers: {
            "X-FloodGuard-Evidence-Context-Id": (
              publicBundle.evidence_context.evidence_context_id
            ),
          },
        });
      }
      return new Response(null, { status: 404 });
    }));

    const data = await loadPublicFloodGuardData(
      "https://api.example",
      publicBundle.evidence_context.evidence_context_id,
    );

    expect(data.dataOrigin).toBe("api");
    expect(data.dataState).toBe("stale");
    expect(data.evidenceContext.evidence_context_id).toBe(
      publicBundle.evidence_context.evidence_context_id,
    );
    expect(data.areaFeatures.features).toHaveLength(8);
    const catalogUrl = requestedUrls.find((value) => (
      new URL(value).pathname === "/api/v1/layers"
    ));
    const layerUrl = requestedUrls.find((value) => (
      new URL(value).pathname === "/api/v1/layer-data/public_preparedness_areas"
    ));
    expect(new URL(String(catalogUrl)).searchParams.get("role")).toBe("public");
    expect(new URL(String(layerUrl)).searchParams.get("role")).toBe("public");
  });
});
