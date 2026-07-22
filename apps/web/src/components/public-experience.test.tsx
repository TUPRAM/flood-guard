import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FeatureCollection } from "@/lib/types";

import { PublicExperience, projectPublicFacilityFeatures } from "./public-experience";

describe("PublicExperience", () => {
  it("orders official updates, the household plan, explicit area choice, and help before technical detail", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    const boundaryBanner = html.indexOf("public-boundary-banner");
    const officialUpdate = html.indexOf("public-official-update");
    const planOverview = html.indexOf("public-plan-overview");
    const planAction = html.indexOf('data-action="build-household-plan"');
    const areaSelection = html.indexOf("public-area-selection");
    const officialHelp = html.indexOf('data-testid="public-official-help"');

    expect(boundaryBanner).toBeGreaterThan(-1);
    expect(officialUpdate).toBeGreaterThan(boundaryBanner);
    expect(planOverview).toBeGreaterThan(officialUpdate);
    expect(planAction).toBeGreaterThan(planOverview);
    expect(areaSelection).toBeGreaterThan(planAction);
    expect(officialHelp).toBeGreaterThan(areaSelection);
    expect(html).toContain("ข้อมูลประวัติศาสตร์เพื่อการเตรียมพร้อม");
    expect(html).toContain("บริบทอุทกภัยแม่สาย เดือนกันยายน 2567");
    expect(html).toContain("ตรวจสอบประกาศก่อนตัดสินใจ");
    expect(html).toContain('id="public-area-select"');
    expect(html).toContain("ระบบไม่ขอพิกัดหรือที่อยู่บ้าน");
    expect(html).toContain("ยังไม่ได้เลือกพื้นที่");
    expect(html).toContain("ไม่ใช่คะแนนความปลอดภัย");
    expect(html).not.toContain("public-quick-actions");
    expect(html).not.toContain("area-chip-row");
    expect(html).not.toContain('href="/studio/"');
    expect(html).not.toMatch(/rehearsal|demo|fixture|candidate|synthetic|non-operational/iu);
  });

  it("ships Thai-first navigation with Shelter guidance and persistent tab semantics", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    expect(html).toContain('<main class="public-page" lang="th">');
    expect(html).toContain("คำแนะนำที่พักพิง");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-controls="public-active-panel"');
    expect(html.match(/id="public-tab-(?:home|map|shelters|prepare|data)"/g)).toHaveLength(5);
    for (const tab of ["home", "map", "shelters", "prepare", "data"]) {
      expect(html).toContain(`id="public-tab-${tab}"`);
    }
  });

  it("removes unverified and candidate facilities from the Public map projection", () => {
    const collection: FeatureCollection = {
      type: "FeatureCollection",
      name: "facilities",
      features: [
        {
          type: "Feature",
          properties: {
            facility_id: "OSM-CANDIDATE",
            facility_type: "shelter_candidate",
            verification_status: "open_context_candidate",
            candidate_status: "unverified_osm_candidate",
            emergency_role: "no_confirmed_emergency_role",
          },
          geometry: { type: "Point", coordinates: [99.8, 20.3] },
        },
        {
          type: "Feature",
          properties: {
            facility_id: "LOCAL-CONFIRMED",
            facility_type: "healthcare",
            verification_status: "locally_confirmed",
            candidate_status: "confirmed_record",
          },
          geometry: { type: "Point", coordinates: [99.9, 20.4] },
        },
        {
          type: "Feature",
          properties: {
            facility_id: "SHELTER-WITHOUT-ROLE",
            facility_type: "shelter",
            verification_status: "verified",
            candidate_status: "confirmed_record",
            emergency_role: "no_confirmed_emergency_role",
          },
          geometry: { type: "Point", coordinates: [99.91, 20.41] },
        },
        {
          type: "Feature",
          properties: {
            facility_id: "MISLEADING-CANDIDATE-ROLE",
            facility_type: "shelter",
            verification_status: "verified",
            candidate_status: "confirmed_record",
            emergency_role: "temporary_shelter_candidate",
          },
          geometry: { type: "Point", coordinates: [99.92, 20.42] },
        },
        {
          type: "Feature",
          properties: {
            facility_id: "AGENCY-VERIFIED-SHELTER",
            facility_type: "shelter",
            verification_status: "verified",
            candidate_status: "confirmed_record",
            emergency_role: "agency_verified",
          },
          geometry: { type: "Point", coordinates: [99.93, 20.43] },
        },
      ],
    };

    const projected = projectPublicFacilityFeatures(collection);
    expect(projected.features.map((feature) => feature.properties.facility_id)).toEqual([
      "LOCAL-CONFIRMED",
      "AGENCY-VERIFIED-SHELTER",
    ]);
    expect(projected.name).toBe("facilities_public_confirmed");
  });
});
