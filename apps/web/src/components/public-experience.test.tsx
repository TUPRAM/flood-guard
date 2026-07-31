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
    expect(html).toContain('class="public-greeting"');
    expect(html).toContain('class="public-greeting-name"');
    expect(html).toContain('class="public-greeting-location"');
    expect(html).toContain('class="public-header-logo"');
    expect(html).toContain('aria-label="FloodGuard home"');
    // The brand mark is the supplied asset, not a hand-drawn shield path.
    expect(html).toContain('class="public-header-logo-mark"');
    expect(html).not.toContain("public-header-shield");
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

  it("opens on address entry and reaches for GPS only from an explicit control", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    // Home now starts in the address-entry state: no blocking consent card.
    expect(html).not.toContain("public-location-consent");
    expect(html).not.toContain('aria-modal="true"');
    expect(html).toContain('role="combobox"');
    expect(html).toContain('aria-autocomplete="list"');

    // GPS stays reachable, and only ever from a control the reader presses, so
    // opening the app never requests the device position on its own.
    expect(html).toContain('class="public-locate-button"');
    expect(html).toContain('aria-label="ใช้ตำแหน่งของฉัน"');
    expect(html).not.toContain("public-map-center-pin");
    expect(html).not.toContain('class="map-attribution"');
  });

  it("frames Home on the highest-priority area without writing it into the saved plan", () => {
    const html = renderToStaticMarkup(<PublicExperience />);
    const legend = html.match(
      /<aside class="public-risk-indicator"[\s\S]*?<\/aside>/,
    )?.[0] ?? "";

    // Ko Chang carries the highest planning priority in the Mae Sai bundle, so
    // Home opens on it and the severity chip reports its own band.
    expect(legend).toContain("เกาะช้าง");
    expect(legend).toContain('data-band="high"');
    expect(legend).toContain(">สูง<");
    expect(legend).not.toMatch(/ยังไม่พบพื้นที่วางแผน/u);
    // The card carries place and band only; the exact score stays in the panel.
    expect(legend).not.toContain("public-risk-value");
    expect(legend).toContain("ความเสี่ยงต่ำ");
    expect(legend).toContain("ความเสี่ยงสูง");

    // The title is dropped from the visible card but kept as the accessible
    // name, so the card is still identifiable to a screen reader.
    const legendText = legend.replace(/<[^>]*>/g, "");
    expect(legendText).not.toMatch(/ตัวชี้วัดการวางแผนน้ำท่วม/u);
    expect(legend).toContain('aria-label="ตัวชี้วัดการวางแผนน้ำท่วม"');

    expect(html).toContain('data-selected-area="TH570903"');

    // Framing the map is not the reader choosing a household planning area, so
    // the header location stays unset until they pick one.
    const greeting = html.match(
      /<span class="public-greeting-location">[\s\S]*?<\/span><\/span>/,
    )?.[0] ?? "";
    expect(greeting).toContain("ยังไม่ได้เลือกตำแหน่ง");
    expect(greeting).not.toContain("เกาะช้าง");
  });

  it("draws the public preparedness areas on the Home map instead of hiding them", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    expect(html).not.toContain("public_home_boundaries_hidden");
    expect(html).toContain('class="public-map-rail"');
    expect(html).toContain('class="public-map-dock"');
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
