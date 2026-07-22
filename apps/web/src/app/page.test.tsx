import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import SurfaceChooser from "./page";

describe("SurfaceChooser", () => {
  it("renders the final-product platform entry with all three role workspaces", () => {
    const html = renderToStaticMarkup(<SurfaceChooser />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain('class="surface-chooser"');
    expect(html).toContain('id="main-content" lang="en"');
    expect(html).toContain('class="chooser-thai" lang="th"');
    expect(html).toContain('class="chooser-header"');
    expect(html).toContain('href="/public"');
    expect(html).toContain('href="/command"');
    expect(html).toContain('href="/studio"');
    expect(html).toContain("One platform. Three planning views.");
    expect(html).toContain("Check DDPM and local-authority updates");
    expect(visibleText).not.toMatch(/\b(?:rehearsal|demo|fixture|candidate|synthetic|non-operational)\b/i);
  });
});
