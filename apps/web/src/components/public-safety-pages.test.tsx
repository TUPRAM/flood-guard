import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { createEmptyHouseholdPlan } from "@/lib/household-plan";
import { EMPTY_SHELTER_TRIP } from "@/lib/public-shelter-view";
import type { FeatureCollection } from "@/lib/types";

import { PublicReportPage } from "./public-report-page";
import { PublicShelterPage } from "./public-shelter-page";
import { PublicSosPage } from "./public-sos-page";

const emptyFeatures: FeatureCollection = {
  type: "FeatureCollection",
  name: "empty",
  features: [],
};

describe("Public household pages", () => {
  it("shows only device-local reports and no apparent reviewed feed", () => {
    const html = renderToStaticMarkup(
      <PublicReportPage language="en" areas={[]} onSelectArea={() => {}} />,
    );
    expect(html).toContain("Reports saved on this device");
    expect(html).toContain("the image file is not stored");
    expect(html).not.toContain("Community feed");
    expect(html).not.toContain("Verified");
    expect(html).not.toContain("Resolved");
    expect(html).not.toContain("data-example");
  });

  it("opens the Shelter page on its map, with no destination and nothing confirmed", () => {
    const html = renderToStaticMarkup(
      <PublicShelterPage
        language="en"
        selectedAreaName=""
        selectedAreaId=""
        areas={[]}
        areaFeatures={emptyFeatures}
        datasetMode="candidate"
        plan={createEmptyHouseholdPlan("")}
        onNavigatePrepare={() => {}}
        trip={EMPTY_SHELTER_TRIP}
        onTripChange={() => {}}
      />,
    );
    // The frame of Home (13 Oct 2026): the destination field and the banner stand over the map.
    expect(html).toContain('class="public-home-page public-shelter-page"');
    expect(html).toContain('class="public-home-map public-shelter-map"');
    expect(html).toContain('value=""');
    // The field's button opens the step that asks for the confirmation, and waits for a destination.
    expect(html).toContain('<button type="submit" disabled="">Next</button>');
    // The banner follows the field directly, is grey with no destination, and opens the sheet with the rest.
    expect(html).toMatch(/<\/form><\/div><button type="button" class="public-signal-banner" data-tone="neutral" aria-controls="public-shelter-panel" aria-expanded="false"/);
    expect(html).toContain("No destination chosen yet");
    // What the page does not know stays on the first screen, with the number to confirm at.
    expect(html).toContain("This app does not know which place is open today · confirm with DDPM 1784");
    // The sheet is closed, so nothing is ticked, and no destination is proposed.
    expect(html).not.toContain('id="public-shelter-panel"');
    expect(html).not.toContain('checked=""');
    expect(html).not.toContain("Ban Pa Daeng School");
    // The places reported as shelters in 2024 belong to the replay; without it the page shows none.
    expect(html).not.toContain("September 2024");
    // As on Home, the credit of the map data folds away from the map once shown; the layers menu repeats it.
    expect(html).toContain('data-map-credit="shown"');
    expect(html.match(/<p class="map-credit"[\s\S]*?<\/p>/)?.[0] ?? "").toContain("© OpenStreetMap contributors");
  });

  it("puts direct official phone links ahead of the optional hold interaction", () => {
    const html = renderToStaticMarkup(
      <PublicSosPage
        language="en"
        hotlines={[]}
        plan={createEmptyHouseholdPlan("")}
        selectedAreaName=""
      />,
    );
    expect(html).toContain('href="tel:1784"');
    expect(html.indexOf("Official emergency hotlines")).toBeLessThan(html.indexOf("Press and hold for 3 seconds"));
    expect(html).toContain("FloodGuard does not place the call");
  });
});
