import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommandWorkspace } from "./command-workspace";

describe("CommandWorkspace", () => {
  it("renders a synchronized map, persistent tablet evidence drawer, and decision panel", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain('class="tablet-evidence-drawer open"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('data-scenario-id="baseline"');
    expect(html).toContain('aria-label="Decision evidence"');
    expect(html).toContain("FPPS and A–E class remain published artifact values");
  });

  it("labels scenario values as engine or server outputs rather than browser calculations", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain("Engine-computed scenario");
    expect(html).toContain("Values come from Python scenario artifacts; there is no browser formula.");
    expect(html).toContain("server-produced");
    expect(html).toContain("The browser does not calculate decision results.");
  });
});
