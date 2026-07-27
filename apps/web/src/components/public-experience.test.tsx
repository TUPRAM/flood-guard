import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { FeatureCollection } from "@/lib/types";

import { PublicExperience, projectPublicFacilityFeatures } from "./public-experience";

describe("PublicExperience", () => {
  it("renders the compact Public shell without the removed logo, subtitle, or historical banner", () => {
    const html = renderToStaticMarkup(<PublicExperience />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain('<main class="public-page public-app-shell" lang="th">');
    expect(html).toContain('class="public-app-header"');
    expect(html).toContain('class="public-profile-trigger"');
    expect(html).toContain('aria-controls="public-profile-drawer"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('class="public-wordmark"');
    expect(visibleText).toContain("FloodGuard");
    expect(html).toContain('class="language-toggle"');
    expect(html).not.toContain("public-brand-mark");
    expect(html).not.toContain("public-boundary-banner");
    expect(visibleText).not.toMatch(/Public preparedness/iu);
    expect(visibleText).not.toMatch(/Historical preparedness information/iu);
    expect(html).not.toContain('href="/studio/"');
    expect(visibleText).not.toMatch(
      /rehearsal|demo|prototype|mock|sample|illustrative|placeholder|coming soon|under construction|not ready|work in progress|fixture|candidate|synthetic|non-operational/iu,
    );
  });

  it("ships Thai-first navigation with exactly Home, Report, Shelter, Prepare, and SOS", () => {
    const html = renderToStaticMarkup(<PublicExperience />);
    const navHtml = html.match(/<nav class="public-bottom-nav"[\s\S]*?<\/nav>/)?.[0] ?? "";
    const tabIds = [...navHtml.matchAll(/id="public-tab-([^"]+)"/g)].map((match) => match[1]);

    expect(html).toContain('aria-controls="public-active-panel"');
    expect(tabIds).toEqual(["home", "report", "shelter", "prepare", "sos"]);
    for (const tab of ["home", "report", "shelter", "prepare", "sos"]) {
      expect(html).toContain(`id="public-tab-${tab}"`);
    }
    for (const retiredTab of ["map", "shelters", "data"]) {
      expect(html).not.toContain(`id="public-tab-${retiredTab}"`);
    }
    expect((navHtml.match(/aria-(?:pressed|selected)="true"|aria-current="page"/g) ?? [])).toHaveLength(1);
    for (const suppliedPath of [
      "M3.75 10.15 12 3.8l8.25 6.35",
      "M5.4 4.5h13.2A2.4 2.4",
      "M3.5 9.55 12 3.9l8.5 5.65",
      "M9 5.5V4.4A1.4 1.4",
      "M7.5 15.55v-4.1a4.5 4.5",
    ]) {
      expect(navHtml).toContain(suppliedPath);
    }
  });

  it("asks before precise GPS access and keeps the Public Home location in transient UI state", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    expect(html).toContain('class="public-location-consent"');
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain('class="public-location-consent-actions"');
    expect(html).toContain('role="combobox"');
    expect(html).toContain('aria-autocomplete="list"');
    expect(html).toContain("ใช้ตำแหน่งที่แม่นยำ");
    expect(html).toContain("พิมพ์ที่อยู่แทน");
    expect(html).toContain("จะไม่ถูกบันทึก");
    expect(html).not.toContain("public-map-center-pin");
    expect(html).not.toContain('class="map-attribution"');
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
