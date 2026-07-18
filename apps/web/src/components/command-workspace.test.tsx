import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommandWorkspace } from "./command-workspace";

describe("CommandWorkspace", () => {
  it("renders the Mae Sai candidate workspace, persistent evidence drawer, and decision panel", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain("Candidate data");
    expect(html).toContain("Bundled offline Mae Sai candidate");
    expect(html).toContain("TH570906");
    expect(html).toContain("Wiang Phang Kham");
    expect(html).toContain('class="tablet-evidence-drawer open"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('data-scenario-id="baseline"');
    expect(html).toContain('aria-label="Decision evidence"');
    expect(html).toContain("facilities are not confirmed shelters and roads are not observed closures");
    expect(html).toContain("can_feed_decision_layer");
    expect(html).toContain("processing_scope");
    expect(html).toContain("false · blocked");
    expect(html).toContain("Exact blocked reason:");
    expect(html).toContain("weak reference is not qualified");
    expect(html).toContain('aria-label="Map data attribution"');
    expect(html).toContain("HDX COD-AB");
    expect(html).toContain("FloodGuard");
  });

  it("keeps static-bundle scenarios disabled until the validated API is connected", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain("Engine-computed scenario");
    expect(html).toContain('select disabled="" aria-label="Select scenario"');
    expect(html).toContain("Scenarios unavailable · no browser formula");
    expect(html).toContain("Static bundle does not run scenarios");
    expect(html).toContain("connect the API to run the comparison");
    expect(html).toContain("segment-level probability consequences are not yet accepted");
  });
});
