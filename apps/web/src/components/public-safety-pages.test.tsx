import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { createEmptyHouseholdPlan } from "@/lib/household-plan";
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

  it("starts shelter planning with no destination or authority confirmation", () => {
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
      />,
    );
    expect(html).not.toContain("Ban Pa Daeng School");
    expect(html).toContain('value=""');
    expect(html).toContain("0/4");
    expect(html).toContain("current capacity or operating status");
    expect(html).not.toContain('checked=""');
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
