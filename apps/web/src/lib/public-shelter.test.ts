import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PublicShelterPage } from "@/components/public-shelter-page";
import { createEmptyHouseholdPlan } from "./household-plan";
import type { Language } from "./types";

function shelterMarkup(language: Language): string {
  return renderToStaticMarkup(createElement(PublicShelterPage, {
    language,
    selectedAreaId: "TH570901",
    selectedAreaName: "Mae Sai",
    areas: [],
    areaFeatures: { type: "FeatureCollection", name: "areas", features: [] },
    datasetMode: "fixture_demo",
    plan: createEmptyHouseholdPlan("TH570901"),
    onNavigatePrepare: () => {},
  }));
}

describe("public journey planning boundaries", () => {
  it.each(["en", "th"] as const)("starts without destination or completed confirmations in %s", (language) => {
    const html = shelterMarkup(language);
    expect(html).not.toContain('checked=""');
    expect(html).not.toContain("Ban Pa Daeng");
    expect(html).toContain('type="text" value=""');
    expect(html).toContain('value="0"');
    expect(html).not.toContain('class="public-shelter-directions__list"');
  });

  it("explains the area-centre origin and unavailable route without fallback movement guidance", () => {
    const html = shelterMarkup("en");
    expect(html).toContain("centre of the planning-area boundary, not your home");
    expect(html).toContain("Route unavailable");
    expect(html).toContain("A straight line will not be used as travel guidance");
    expect(html).not.toMatch(/Set out from|Head north|direct, about|Arrive at/);
  });

  it("provides the same planning boundary in Thai", () => {
    const html = shelterMarkup("th");
    expect(html).toContain("ไม่ใช่ตำแหน่งบ้านของคุณ");
    expect(html).toContain("ไม่มีเส้นทางที่ใช้แสดงได้");
    expect(html).toContain("ระบบจะไม่ใช้เส้นตรงแทนคำแนะนำการเดินทาง");
  });
});
