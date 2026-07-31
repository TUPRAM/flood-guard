import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";

import type { PublicPreparednessArea } from "@floodguard/contracts";
import type { AreaRecord, FeatureCollection, GeoFeature } from "@/lib/types";

import {
  displayAttribution,
  facilityClusters,
  facilityDisplayCategory,
  facilityIconMarkup,
  facilityVisibleForAudience,
  GeoMap,
  hasDisplayableRoadSegmentRisk,
  isStructuredRoadSegmentEvidence,
  roadRiskProbability,
} from "./geo-map";

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

  it("announces when selected-area road detail is unavailable without hiding the regional overview", () => {
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
    expect(html).toContain("Selected-area road detail is unavailable; showing the regional road overview.");
  });
});

describe("facility presentation", () => {
  it("maps every Mae Sai facility type to a distinct user-facing icon category", () => {
    expect(facilityDisplayCategory("healthcare")).toBe("healthcare");
    expect(facilityDisplayCategory("school")).toBe("school");
    expect(facilityDisplayCategory("emergency_service")).toBe("emergency");
    expect(facilityDisplayCategory("shelter")).toBe("shelter");
    expect(facilityDisplayCategory("shelter_candidate")).toBe("possible_shelter");
    expect(facilityDisplayCategory("community_facility")).toBe("community");
    expect(facilityDisplayCategory("unknown")).toBe("community");

    const icons = ["healthcare", "school", "emergency", "shelter", "possible_shelter", "community"]
      .map((category) => facilityIconMarkup(category as Parameters<typeof facilityIconMarkup>[0]));
    expect(new Set(icons).size).toBe(icons.length);
    expect(icons.every((icon) => icon.includes("<svg") && !icon.includes("unknown"))).toBe(true);
  });

  it("never presents an unverified shelter candidate as a public shelter", () => {
    const candidate = point("F-SHELTER", "AREA-1", 99.8, 20.2);
    candidate.properties.facility_type = "shelter_candidate";
    candidate.properties.public_visibility = true;
    candidate.properties.verification_status = "verified";

    expect(facilityVisibleForAudience(candidate, "public")).toBe(false);
    expect(facilityVisibleForAudience(candidate, "staff")).toBe(true);
    expect(facilityDisplayCategory("shelter_candidate")).toBe("possible_shelter");
  });

  it("labels shelter candidates neutrally for staff and omits them from the public list", () => {
    const areas = (bundleJson as unknown as { areas: AreaRecord[] }).areas;
    const candidate = point("F-SHELTER", areas[0].area_id, 99.8, 20.2);
    candidate.properties.facility_type = "shelter_candidate";
    candidate.properties.facility_name = "School grounds";
    candidate.properties.public_visibility = false;
    candidate.properties.operating_status = "unverified";
    const props = {
      areas,
      selectedId: areas[0].area_id,
      onSelect: () => undefined,
      language: "en" as const,
      areaFeatures: collection("areas", []),
      roadFeatures: collection("roads", []),
      facilityFeatures: collection("facilities", [candidate]),
      datasetMode: "candidate" as const,
    };

    const staffHtml = renderToStaticMarkup(createElement(GeoMap, { ...props, audience: "staff" }));
    const publicHtml = renderToStaticMarkup(createElement(GeoMap, { ...props, audience: "public" }));
    expect(staffHtml).toContain("Possible shelter site - unverified");
    expect(staffHtml).not.toContain("Verified shelter");
    expect(staffHtml).not.toContain("Shelter location");
    for (const label of ["Type", "Verification", "Source", "Operation"]) expect(staffHtml).toContain(`<dt>${label}</dt>`);
    expect(publicHtml).toContain("No public-verified facilities are available");
    expect(publicHtml).not.toContain("School grounds");
  });

  it("fails closed for public facility visibility and requires explicit verification", () => {
    const facility = point("F-1", "AREA-1", 99.8, 20.2);
    expect(facilityVisibleForAudience(facility, "public")).toBe(false);

    facility.properties.public_visibility = true;
    facility.properties.verification_status = "confirmed";
    facility.properties.operating_status = "open";
    expect(facilityVisibleForAudience(facility, "public")).toBe(true);
    facility.properties.public_visibility = false;
    expect(facilityVisibleForAudience(facility, "public")).toBe(false);
  });

  it("publishes a shelter only with the canonical verified designation and current operation", () => {
    const shelter = point("S-1", "AREA-1", 99.8, 20.2);
    shelter.properties.facility_type = "shelter";
    shelter.properties.public_visibility = true;
    shelter.properties.verification_status = "agency_verified";
    shelter.properties.operating_status = "open";
    shelter.properties.emergency_role = "temporary_shelter_candidate";
    expect(facilityVisibleForAudience(shelter, "public")).toBe(false);

    shelter.properties.emergency_role = "designated_evacuation";
    expect(facilityVisibleForAudience(shelter, "public")).toBe(true);
    shelter.properties.operating_status = "unverified";
    expect(facilityVisibleForAudience(shelter, "public")).toBe(false);
  });

  it("requires explicit road-segment granularity before enabling segment-risk semantics", () => {
    const road: GeoFeature = {
      type: "Feature",
      properties: { road_id: "R-1", road_disruption_probability_0_1: 0.9 },
      geometry: { type: "LineString", coordinates: [[99.7, 20.2], [99.8, 20.3]] },
    };
    expect(isStructuredRoadSegmentEvidence(road)).toBe(false);
    delete road.properties.road_disruption_probability_0_1;
    road.properties.evidence_granularity = "road_segment";
    expect(isStructuredRoadSegmentEvidence(road)).toBe(true);
    expect(roadRiskProbability(road)).toBeUndefined();
    expect(hasDisplayableRoadSegmentRisk(road, true)).toBe(false);
    road.properties.road_disruption_probability_0_1 = 0.4;
    expect(roadRiskProbability(road)).toBe(0.4);
    expect(hasDisplayableRoadSegmentRisk(road, false)).toBe(false);
    expect(hasDisplayableRoadSegmentRisk(road, true)).toBe(true);
  });

  it("renders accessible Street, Satellite, and Terrain controls with Street selected", () => {
    const areas = (bundleJson as unknown as { areas: AreaRecord[] }).areas;
    const html = renderToStaticMarkup(createElement(GeoMap, {
      areas,
      selectedId: areas[0].area_id,
      onSelect: () => undefined,
      language: "en",
      areaFeatures: collection("areas", []),
      roadFeatures: collection("roads", []),
      datasetMode: "candidate",
      enableBasemaps: true,
    }));

    expect(html).toContain('aria-label="Choose map background"');
    expect(html).toContain('data-basemap="street"');
    expect(html).toContain('aria-pressed="true"');
    for (const label of ["Street", "Satellite", "Terrain"]) expect(html).toContain(`>${label}</button>`);
    expect(html).toContain("View map results as a list");
    for (const label of ["Recommendation", "Evidence", "Data status", "Visible facilities", "Access", "Assumptions"]) expect(html).toContain(label);
    expect(html).toContain("Road network context");
    expect(html).not.toContain("Map text alternative");
  });

  it("supports a transient exact-location marker contract without the long attribution paragraph", () => {
    const areas = (bundleJson as unknown as { areas: AreaRecord[] }).areas;
    const html = renderToStaticMarkup(createElement(GeoMap, {
      areas,
      selectedId: "",
      onSelect: () => undefined,
      language: "en",
      areaFeatures: collection("areas", []),
      roadFeatures: collection("roads", []),
      datasetMode: "candidate",
      enableBasemaps: true,
      showDataAttribution: false,
      location: {
        latitude: 20.429799,
        longitude: 99.884366,
        accuracyMeters: 12,
        label: "Your precise location",
        source: "gps",
      },
    }));

    expect(html).toContain('data-location-source="gps"');
    expect(html).toContain('data-location-latitude="20.429799"');
    expect(html).toContain('data-location-longitude="99.884366"');
    expect(html).toContain('data-location-accuracy="12"');
    expect(html).not.toContain('class="map-attribution"');
    expect(html).not.toContain("Data attribution:");
  });

  it("renders the reduced public area contract without staff A-E or FPPS semantics", () => {
    const publicArea: PublicPreparednessArea = {
      schema_version: "1.0",
      evidence_context_id: "public-context",
      area_id: "AREA-1",
      area_name_th: "พื้นที่หนึ่ง",
      area_name_en: "Area One",
      planning_priority_0_100: 62.4,
      evidence_sufficiency: "low",
      recommendation_code: "low_confidence",
      source_timestamp: "2024-09-15T00:00:00Z",
      freshness: "historical",
      current_conditions_confirmed: false,
    };
    const html = renderToStaticMarkup(createElement(GeoMap, {
      areas: [publicArea],
      selectedId: publicArea.area_id,
      onSelect: () => undefined,
      language: "en",
      areaFeatures: collection("areas", []),
      roadFeatures: collection("roads", []),
      datasetMode: "candidate",
      audience: "public",
    }));

    expect(html).toContain("Planning priority");
    expect(html).toContain("Evidence sufficiency");
    expect(html).toContain("Review official updates and verify current conditions");
    expect(html).not.toContain("FPPS");
    expect(html).not.toContain("Protect lives now");
    expect(html).not.toContain(">Class ");
  });

  it("presents internal attribution labels as publication-ready copy", () => {
    expect(displayAttribution("FloodGuard candidate analysis")).toBe("FloodGuard planning analysis");
    expect(displayAttribution("Synthetic fixture context")).toBe("modelled reference context");
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
