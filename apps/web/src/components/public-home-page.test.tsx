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
    />);
    const indicator = html.match(/<aside class="public-risk-indicator"[\s\S]*?<\/aside>/)?.[0] ?? "";

    expect(indicator).toContain("Historical planning priority");
    expect(indicator).toContain("Sept 2024");
    expect(indicator).toContain("Confidence: low");
    expect(indicator).toContain("Verify current conditions");
    expect(indicator).toContain("Lower priority");
    expect(indicator).toContain("Higher priority");
    expect(indicator).not.toMatch(/Low risk|High risk/);
    expect(html).toContain("View map results as a list");
    for (const area of data.publicAreas) expect(html).toContain(area.area_name_en);
    expect(onSelectArea).not.toHaveBeenCalled();
    expect(onLocationChange).not.toHaveBeenCalled();
  });
});
