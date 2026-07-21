import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommandWorkspace } from "./command-workspace";

describe("CommandWorkspace", () => {
  it("renders the Mae Sai planning workspace with final-product context and safeguards", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain('aria-label="Planning data context"');
    expect(html).toContain("Planning intelligence");
    expect(html).toContain("Source time");
    expect(html).toContain("Confidence");
    expect(html).toContain("follow DDPM and local-authority instructions before action");
    expect(html).toContain("TH570906");
    expect(html).toContain("Wiang Phang Kham");
    expect(html).toContain('class="tablet-evidence-drawer open"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('data-scenario-id="baseline"');
    expect(html).toContain('aria-label="Decision evidence"');
    expect(html).toContain("Important facilities");
    expect(html).toContain("Preparedness prioritization");
    expect(html).toContain("Confirm locally");
    expect(html).toContain('aria-label="Choose map background"');
    expect(html).toContain("Street");
    expect(html).toContain("Satellite");
    expect(html).toContain("Terrain");
    expect(html).toContain('aria-label="Map data attribution"');
    expect(html).toContain("HDX COD-AB");
    expect(html).toContain("FloodGuard");
    expect(visibleText).not.toMatch(/\b(?:rehearsal|demo|fixture|candidate|synthetic|non-operational|server-produced|FastAPI)\b/i);
    expect(html).not.toContain("can_feed_decision_layer");
    expect(html).not.toContain("processing_scope");
  });

  it("keeps unavailable scenario controls clear without exposing implementation notes", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain("Planning scenario");
    expect(html).toContain('select disabled="" aria-label="Select scenario"');
    expect(html).toContain("Current planning outlook");
    expect(html).toContain("Scenario comparison unavailable");
    expect(html).toContain("Planning evidence boundary");
    expect(html).toContain("Scenario comparison can be added after its supporting evidence review is complete");
    expect(html).toContain("Check current field conditions because they do not confirm a road closure");
    expect(html).not.toContain("FastAPI");
    expect(html).not.toContain("Static bundle");
  });
});
