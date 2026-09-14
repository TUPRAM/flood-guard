import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LandingPage } from "../components/landing/landing-page";

describe("LandingPage", () => {
  it("exports the complete story and direct workspace entry without JavaScript", () => {
    const html = renderToStaticMarkup(<LandingPage />);

    expect(html).toContain("data-landing");
    expect(html).toContain('lang="en"');
    for (const route of ["public", "command", "studio"]) {
      expect(html).toMatch(new RegExp(`href="/${route}/?"`));
    }
    for (const chapter of ["place", "flood", "access", "finding"]) {
      expect(html).toContain(`id="${chapter}"`);
    }
    for (const section of ["story", "method", "case", "workspaces", "questions"]) {
      expect(html).toContain(`id="${section}"`);
    }
    expect(html).toContain("See the flood.");
    expect(html).toContain("Understand who may be cut off.");
    expect(html).toContain("Synthetic illustration");
    expect(html).toContain("Assumed disruption, not a confirmed closure");
    expect(html).toContain("No qualified evaluation or operational authorization");
    expect(html).not.toContain("DEMO-R017");
    expect(html).not.toContain("Sample report received");
    expect(html).toContain("<details");
    expect(html).not.toContain("<canvas");
    expect(html).not.toMatch(/<iframe|<form|demo=true/i);
  });

  it("exports the source limitation and four matched fallback figures", () => {
    const html = renderToStaticMarkup(<LandingPage />);

    expect(html).toContain("data-opening-provenance");
    expect(html).toMatch(/inferred|Inferred/);
    expect(html).toMatch(/not a verified reconstruction/i);
    for (const chapter of ["connected", "flood", "access", "finding"]) {
      expect(decodeURIComponent(html)).toMatch(new RegExp(`(?:src="|url=)/landing/desktop-v4/${chapter}\\.webp`));
    }
    expect(html).toContain('href="#place"');
  });

  it("separates the computed synthetic finding, real product views and historical evidence", () => {
    const html = renderToStaticMarkup(<LandingPage />);
    expect(html).toContain('data-scenario-id="SYN-ACCESS-01"');
    for (const field of ["finding", "reason", "uncertainty", "next-step"]) expect(html).toContain(`data-finding-field="${field}"`);
    expect(html).toContain("Connection unavailable");
    expect(html).toContain("SYNTHETIC EXAMPLE / NOT A MAE SAI RESULT");
    for (const view of ["public", "command", "studio"]) expect(html).toContain(`data-product-view="${view}"`);
    for (const status of ["Available", "Derived", "Needs verification"]) expect(html).toContain(`data-evidence-status="${status}"`);
    expect(html).toContain("Scenario comparison is unavailable");
    expect(html).toContain("Not a September flood mask");
    expect(html).not.toMatch(/href="\/public\/(prepare|#prepare)/);
  });
});
