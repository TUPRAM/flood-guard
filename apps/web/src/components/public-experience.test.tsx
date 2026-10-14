import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FeatureCollection } from "@/lib/types";

import { PublicExperience, projectPublicFacilityFeatures, readPublicPage } from "./public-experience";

describe("PublicExperience", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

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
    // No example area is framed for the reader any more (13 Oct 2026); the note at the foot of the map stays. The
    // only example named is the example home of the practice scenario the page opens on (14 Oct 2026).
    expect(visibleText.replaceAll("บ้านตัวอย่าง", "")).not.toMatch(/ตัวอย่าง/u);
    expect(visibleText).toMatch(/ไม่ใช่คำเตือนทางการ/u);
    // The research link moved into the panel behind the banner (owner request of 7 Oct 2026), which is closed at first, and
    // nothing stands between the header and the map: no intro block, and no status bar while everything is in order.
    expect(html).not.toContain('href="/public-cases/"');
    expect(html).not.toContain("public-home-intro");
    expect(html).toContain('<div data-app-availability-slot="true" class="public-availability-slot"></div>');
    expect(html).not.toContain("public-research-details");
  });

  it("ships Thai-first navigation with exactly Home, Report, Shelter, Prepare, and SOS", () => {
    const html = renderToStaticMarkup(<PublicExperience />);
    const navHtml = html.match(/<nav class="public-bottom-nav"[\s\S]*?<\/nav>/)?.[0] ?? "";
    const tabIds = [...navHtml.matchAll(/id="public-tab-([^"]+)"/g)].map((match) => match[1]);

    expect(html).toContain('aria-controls="main-content"');
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

  it("opens Home of the public build on the whole district, with no score and no example area", () => {
    // The public build does not carry the replay, so it has no practice scenario to open on.
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    const html = renderToStaticMarkup(<PublicExperience />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    // The priority card and its scale were removed on the owner's request of 13 Oct 2026.
    expect(html).not.toContain("public-risk-indicator");
    expect(visibleText).not.toMatch(/ลำดับความสำคัญ|ความสำคัญต่ำ|ความสำคัญสูง/u);
    expect(html).toContain('class="map-text-alternative"');
    // No area is chosen for the reader, on the map or in the header.
    expect(html).toContain('data-selected-area=""');
    const greeting = html.match(
      /<span class="public-greeting-location">[\s\S]*?<\/span><\/span>/,
    )?.[0] ?? "";
    expect(greeting).toContain("ยังไม่ได้เลือกตำแหน่ง");
    expect(greeting).not.toContain("เกาะช้าง");

    // The banner is always there, grey on a day without practice, and the note says what the page is not.
    const banner = html.match(/<button type="button" class="public-signal-banner"[\s\S]*?<\/button>/)?.[0] ?? "";
    expect(banner).toContain('data-tone="neutral"');
    expect(banner).toContain("ไม่มีรายงานน้ำท่วมใกล้คุณ");
    const note = html.match(/<p class="public-map-note"[\s\S]*?<\/p>/)?.[0] ?? "";
    expect(note).toContain("ข้อมูลเพื่อการเตรียมพร้อม · ไม่ใช่คำเตือนทางการ");
  });

  it("opens on the practice scenario \"Normal day\" where the replay ships, with its menu right of the language switch", () => {
    const html = renderToStaticMarkup(<PublicExperience />);
    const actions = html.match(/<div class="public-header-actions">[\s\S]*?<\/header>/)?.[0] ?? "";

    expect(actions.indexOf('class="language-toggle"')).toBeGreaterThan(-1);
    expect(actions.indexOf('class="public-practice-trigger"')).toBeGreaterThan(actions.indexOf('class="language-toggle"'));
    expect(actions).toContain('aria-label="สถานการณ์ฝึกซ้อม"');
    expect(actions).toContain('aria-expanded="false"');
    expect(html).not.toContain('class="public-practice-list"');
    // A scenario is shown from the first paint (owner request of 14 Oct 2026): the replay is still being read here,
    // so the banner says so, and the header names the example home.
    expect(actions).toContain('data-active="true"');
    expect(html).toContain('data-practice="true"');
    const banner = html.match(/<button type="button" class="public-signal-banner"[\s\S]*?<\/button>/)?.[0] ?? "";
    expect(banner).toContain("กำลังโหลดภาพจำลองเพื่อฝึกซ้อม…");
    const greeting = html.match(/<span class="public-greeting-location">[\s\S]*?<\/span><\/span>/)?.[0] ?? "";
    expect(greeting).toContain("บ้านตัวอย่าง · แม่สาย");
  });

  it("has no scenario menu and no scenario in the public build", () => {
    vi.stubEnv("NEXT_PUBLIC_FLOODGUARD_APP_PROFILE", "public-production");
    const html = renderToStaticMarkup(<PublicExperience />);
    expect(html).not.toContain('class="public-practice-trigger"');
    expect(html).not.toContain('data-practice="true"');
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

describe("Public tab URL", () => {
  it("accepts only the five known tabs and defaults to Home", () => {
    expect(readPublicPage("?tab=report&aoi=aoi-01")).toBe("report");
    expect(readPublicPage("?tab=shelter")).toBe("shelter");
    expect(readPublicPage("?tab=prepare")).toBe("prepare");
    expect(readPublicPage("?tab=sos")).toBe("sos");
    expect(readPublicPage("?tab=unknown")).toBe("home");
    expect(readPublicPage("?aoi=aoi-01")).toBe("home");
  });
});
