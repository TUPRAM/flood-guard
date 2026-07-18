import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { StudioWorkspace } from "./studio-workspace";

describe("StudioWorkspace", () => {
  it("renders the compact research-console hierarchy", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);

    expect(html).toContain("Research evidence console");
    expect(html).toContain("Published runs");
    expect(html).toContain("Data gates");
    expect(html).toContain("Evidence-scoped comparison");
  });

  it("separates synthetic integration proof from qualified evaluation and promotion", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);

    expect(html).toContain("Integration smoke");
    expect(html).toContain("Qualified real-data evaluation");
    expect(html).toContain("Decision eligibility");
    expect(html).toContain("Synthetic integration proof; not evidence of real flood-detection accuracy.");
    expect(html).toContain("can_feed_decision_layer = false");
  });
});
