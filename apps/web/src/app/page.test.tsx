import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { LandingPage } from "../components/landing/landing-page";
import { landingGateStatus } from "../lib/landing/gate-status";

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
    expect(html).toContain("We assumed this road is cut. Nobody has confirmed it.");
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
    // Decode only well-formed escapes: page copy legitimately contains bare "%"
    // (percentages in the pipeline extracts), which would make a whole-document
    // decodeURIComponent throw URIError.
    const decoded = html.replace(/%[0-9A-Fa-f]{2}/g, (escape) => decodeURIComponent(escape));
    for (const chapter of ["connected", "flood", "access", "finding"]) {
      expect(decoded).toMatch(new RegExp(`(?:src="|url=)/landing/desktop-v4/${chapter}\\.webp`));
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

  it("labels the automated evidence track and its hold-out scores honestly", () => {
    const html = renderToStaticMarkup(<LandingPage />);
    for (const label of [
      "Copernicus reuse terms recorded",
      "Automated optical reference (not human-qualified)",
      "Two-method automated cross-review (no human review)",
      "Pre-registered hold-out evaluation (automated)",
      "Human qualification and blind review were not performed.",
    ]) expect(html).toContain(label);
    expect(html).toContain("Any final-holdout score is agreement with an automated optical map, not accuracy.");
    expect(html).toContain("Contains modified Copernicus Sentinel data 2024.");
    for (const id of ["automated_optical_reference", "automated_cross_review", "preregistered_holdout_evaluation"]) {
      expect(html).toContain(`data-criterion-id="${id}"`);
    }
    expect(html).not.toContain("A four-person blind-reviewed, adjudicated label release revalidates.");
    if (landingGateStatus.criteria.preregistered_holdout_evaluation.met) {
      expect(html).toContain('data-automated-score="mae_sai_m2_gamma0_10m_otsu_candidate"');
      expect(html).toContain('data-automated-score="mae_sai_20m_amplitude_comparator"');
      expect(html.match(/agreement with an automated optical map, not accuracy/g)).toHaveLength(3);
    } else {
      expect(html).toContain("Final-holdout agreement scores are not available from a verified result.");
      expect(html).not.toContain("data-automated-score=");
    }
  });
});
