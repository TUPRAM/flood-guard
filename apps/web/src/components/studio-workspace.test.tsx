import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { getOfflineData } from "@/lib/data-provider";

import { publicationManifest, StudioWorkspace } from "./studio-workspace";

describe("StudioWorkspace", () => {
  it("renders the final research and validation hierarchy", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);

    expect(html).toContain("Research &amp; validation studio");
    expect(html).toContain("Published evaluations");
    expect(html).toContain("Evidence readiness");
    expect(html).toContain("Evidence-scoped comparison");
    expect(html).toContain("Acceptance &amp; governance");
    expect(html).toContain("Source time");
    expect(html).toContain("Confidence");
  });

  it("separates technical verification, observed-data validation, and operational readiness", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain("Technical verification");
    expect(html).toContain("Observed-data validation");
    expect(html).toContain("Operational readiness");
    expect(html).toContain("This result verifies the technical workflow only.");
    expect(html).toContain("Review held");
    expect(html).not.toContain("Integration smoke");
    expect(html).not.toContain("Qualified real-data evaluation");
    expect(html).not.toContain("can_feed_decision_layer = false");
    expect(visibleText).not.toMatch(/\b(?:rehearsal|demo|fixture|candidate|synthetic|non-operational|server-produced|FastAPI)\b/i);
  });

  it("downloads a publication-safe evidence projection", () => {
    const run = getOfflineData().model_runs[0];
    const manifest = publicationManifest(run);

    expect(manifest).toContain('"source_timestamp"');
    expect(manifest).toContain('"confidence"');
    expect(manifest).toContain('"metrics"');
    expect(manifest).toContain('"operational_readiness"');
    expect(manifest).not.toMatch(/\b(?:demo|fixture|candidate|synthetic|non-operational)\b/i);
    expect(manifest).not.toMatch(/run_id|external_output_workspace|processing_scope|processing_allowed|can_feed_decision_layer/);
  });
});
