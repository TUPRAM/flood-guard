import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { getPublicOfflineData } from "@/lib/public-data-provider";

import { PublicHomePage } from "./public-home-page";

describe("PublicHomePage planning context", () => {
  it("keeps historical date and confidence beside the English priority indicator", () => {
    const data = getPublicOfflineData();
    const onSelectArea = vi.fn();
    const onLocationChange = vi.fn();
    const html = renderToStaticMarkup(<PublicHomePage
      language="en"
      data={data}
      selectedAreaId="TH570903"
      onSelectArea={onSelectArea}
      onLocationChange={onLocationChange}
      researchHref="/public-cases/"
    />);
    const indicator = html.match(/<aside class="public-risk-indicator"[\s\S]*?<\/aside>/)?.[0] ?? "";

    expect(indicator).toContain("Historical planning priority");
    expect(indicator).toContain("Sept 2024");
    expect(indicator).toContain("Confidence: low");
    expect(indicator).toContain("Verify current conditions");
    expect(indicator).toContain("Lower priority");
    expect(indicator).toContain("Higher priority");
    expect(indicator).not.toMatch(/Low risk|High risk/);
    // The card says what it is not, now that the block above the map is gone (owner request of 7 Oct 2026).
    expect(indicator).toContain("non-operational · not an official warning");
    // The list of the map's results is still in the page: it is the map's text alternative, shown to the keyboard.
    expect(html).toContain("View map results as a list");
    // Nothing stands between the header and the map but a heading for a screen reader.
    expect(html).not.toContain("public-home-intro");
    expect(html).not.toContain("Make my plan");
    expect(html).not.toContain("Help and contacts");
    expect(html).toContain('<h1 class="sr-only">Ko Chang</h1>');
    // Hazard Info is a control of the map itself, not of the dock at its foot; the research link waits in its panel.
    expect(html).toMatch(/<\/aside><\/div><button type="button" class="public-hazard-button"/);
    expect(html).not.toContain("Explore research cases");
    for (const area of data.publicAreas) expect(html).toContain(area.area_name_en);
    expect(onSelectArea).not.toHaveBeenCalled();
    expect(onLocationChange).not.toHaveBeenCalled();
  });
});
