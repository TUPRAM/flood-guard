import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { getPublicOfflineData } from "@/lib/public-data-provider";

import { PublicHomePage } from "./public-home-page";

describe("PublicHomePage on a day without practice", () => {
  const render = (selectedAreaId: string) => {
    const data = getPublicOfflineData();
    const onSelectArea = vi.fn();
    const onLocationChange = vi.fn();
    const onPracticeEnd = vi.fn();
    const html = renderToStaticMarkup(<PublicHomePage
      language="en"
      data={data}
      selectedAreaId={selectedAreaId}
      onSelectArea={onSelectArea}
      onLocationChange={onLocationChange}
      onPracticeEnd={onPracticeEnd}
      researchHref="/public-cases/"
    />);
    return { data, html, onSelectArea, onLocationChange, onPracticeEnd };
  };

  it("shows no score: the priority card is gone and the areas are outlines", () => {
    const { data, html } = render("TH570903");
    const text = html.replace(/<[^>]*>/g, " ");

    // The card that stood at the foot of the map until 13 Oct 2026, and every word of its scale.
    expect(html).not.toContain("public-risk-indicator");
    expect(text).not.toMatch(/Historical planning priority|Lower priority|Higher priority|planning priority/i);
    expect(text).not.toMatch(/Low risk|High risk/);
    for (const area of data.publicAreas) {
      expect(text).not.toContain(area.planning_priority_0_100.toFixed(1));
    }
    // The list of the map's results is still in the page: it is the map's text alternative, shown to the keyboard.
    expect(html).toContain("View map results as a list");
    for (const area of data.publicAreas) expect(html).toContain(area.area_name_en);
  });

  it("keeps a grey banner under the search field as the one control that opens the panel", () => {
    const { html } = render("TH570903");
    const banner = html.match(/<button type="button" class="public-signal-banner"[\s\S]*?<\/button>/)?.[0] ?? "";

    // Grey, not the green of an all-clear: the app has no feed of current water.
    expect(banner).toContain('data-tone="neutral"');
    expect(banner).toContain("No flood reports near you");
    expect(banner).toContain('aria-controls="public-hazard-panel"');
    // The banner stands directly after the search field, in the rail. The separate Hazard Info button, which opened
    // the same panel, was removed as redundant (owner request of 13 Oct 2026).
    expect(html).toMatch(/<\/form><\/div><button type="button" class="public-signal-banner"/);
    expect(html).not.toContain("public-hazard-button");
    expect(html.replace(/<[^>]*>/g, " ")).not.toMatch(/Hazard Info/);
  });

  it("says on the first screen what the page is not", () => {
    const { html, onSelectArea, onLocationChange, onPracticeEnd } = render("TH570903");
    const note = html.match(/<p class="public-map-note"[\s\S]*?<\/p>/)?.[0] ?? "";

    expect(note).toContain("data-public-not-a-warning");
    expect(note).toContain("Preparedness information · not an official warning");
    expect(note).not.toContain('data-practice="true"');
    // The credit of the map data folds away from the map once shown, and is repeated in the layers menu.
    expect(html).toContain('data-map-credit="shown"');
    const credit = html.match(/<p class="map-credit"[\s\S]*?<\/p>/)?.[0] ?? "";
    expect(credit).toContain('href="https://www.openstreetmap.org/copyright"');
    expect(credit).toContain("© OpenStreetMap contributors");
    // Nothing stands between the header and the map but a heading for a screen reader.
    expect(html).not.toContain("public-home-intro");
    expect(html).not.toContain("Make my plan");
    expect(html).not.toContain("Help and contacts");
    expect(html).toContain('<h1 class="sr-only">Ko Chang</h1>');
    // The research link waits in the panel behind the banner, which is closed at first.
    expect(html).not.toContain("Explore research cases");
    expect(onSelectArea).not.toHaveBeenCalled();
    expect(onLocationChange).not.toHaveBeenCalled();
    expect(onPracticeEnd).not.toHaveBeenCalled();
  });

  it("frames no area for a reader who has chosen none", () => {
    const { html } = render("");

    expect(html).toContain('<h1 class="sr-only">Choose your planning area</h1>');
    expect(html).toContain('data-selected-area=""');
    expect(html).not.toContain("Example ·");
  });
});

describe("PublicHomePage with a practice scenario chosen", () => {
  it("says that the replay is loading, in grey, until its files are read", () => {
    const html = renderToStaticMarkup(<PublicHomePage
      language="en"
      data={getPublicOfflineData()}
      selectedAreaId="TH570903"
      onSelectArea={vi.fn()}
      onLocationChange={vi.fn()}
      practice={{ status: "loading" }}
    />);
    const banner = html.match(/<button type="button" class="public-signal-banner"[\s\S]*?<\/button>/)?.[0] ?? "";
    const note = html.match(/<p class="public-map-note"[\s\S]*?<\/p>/)?.[0] ?? "";

    // Nothing of the scenario is claimed before the replay is there to compute it from.
    expect(banner).toContain('data-tone="neutral"');
    expect(banner).toContain("Loading the practice replay");
    expect(banner).not.toContain("No shelter within walking reach");
    expect(note).toContain('data-practice="true"');
    expect(note).toContain("not an official warning");
  });
});
