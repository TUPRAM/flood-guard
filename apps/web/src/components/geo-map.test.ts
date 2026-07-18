import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";

import type { AreaRecord, FeatureCollection, GeoFeature } from "@/lib/types";

import { facilityClusters, GeoMap } from "./geo-map";

describe("facilityClusters", () => {
  it("positions a regional cluster at the centroid of actual facility points", () => {
    const facilities = collection("facilities", [
      point("F-1", "AREA-1", 99.8, 20.2),
      point("F-2", "AREA-1", 100.0, 20.4),
    ]);
    const access = collection("access", [point("A-1", "AREA-1", 99.1, 19.1)]);

    const [cluster] = facilityClusters(facilities, access);
    expect(cluster.areaId).toBe("AREA-1");
    expect(cluster.count).toBe(2);
    expect(cluster.latlng[0]).toBeCloseTo(20.3);
    expect(cluster.latlng[1]).toBeCloseTo(99.9);
  });

  it("uses access evidence only when an area has no valid facility point", () => {
    const facilities = collection("facilities", [{
      type: "Feature",
      properties: { facility_id: "F-1", area_id: "AREA-1" },
      geometry: { type: "LineString", coordinates: [[99.7, 20.2], [99.8, 20.3]] },
    }]);
    const access = collection("access", [point("A-1", "AREA-1", 99.75, 20.25)]);

    expect(facilityClusters(facilities, access)).toEqual([
      { areaId: "AREA-1", count: 1, latlng: [20.25, 99.75] },
    ]);
  });

  it("announces when selected-area road detail is unavailable without hiding regional candidates", () => {
    const areas = (bundleJson as unknown as { areas: AreaRecord[] }).areas;
    const html = renderToStaticMarkup(createElement(GeoMap, {
      areas,
      selectedId: areas[0].area_id,
      onSelect: () => undefined,
      language: "en",
      areaFeatures: collection("areas", []),
      roadFeatures: collection("roads", []),
      datasetMode: "candidate",
      roadDetailState: "unavailable",
    }));

    expect(html).toContain('class="map-detail-notice unavailable"');
    expect(html).toContain('role="status"');
    expect(html).toContain("Selected-area road detail unavailable; showing bounded regional candidates.");
  });
});

function point(id: string, areaId: string, longitude: number, latitude: number): GeoFeature {
  return {
    type: "Feature",
    properties: { facility_id: id, area_id: areaId },
    geometry: { type: "Point", coordinates: [longitude, latitude] },
  };
}

function collection(name: string, features: GeoFeature[]): FeatureCollection {
  return { type: "FeatureCollection", name, features };
}
