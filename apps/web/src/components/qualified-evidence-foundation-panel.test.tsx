import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";

import type { QualifiedEvidenceFoundation } from "@/lib/types";

import { QualifiedEvidenceFoundationPanel } from "./qualified-evidence-foundation-panel";

describe("QualifiedEvidenceFoundationPanel", () => {
  it("withholds all evidence details while browser verification is pending", () => {
    const html = renderToStaticMarkup(
      <QualifiedEvidenceFoundationPanel
        foundation={
          bundleJson.qualified_evidence_foundation as QualifiedEvidenceFoundation
        }
        language="en"
      />,
    );
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain(
      "Qualified-reference status verification is pending",
    );
    expect(html).toContain(
      "Evidence details are withheld until browser SHA-256 verification succeeds.",
    );
    expect(html).not.toContain("CANDIDATE EVIDENCE BINDING");
    expect(html).not.toContain("AIT-VAP001-TH");
    expect(html).not.toContain(
      bundleJson.qualified_evidence_foundation.reference_candidate_binding
        .manifest_canonical_sha256,
    );
    expect(html).not.toContain("processing_allowed=true");
    expect(html).not.toContain("Qualified Thai event reference");
    expect(html).not.toContain("Next exact actions");
    expect(visibleText).not.toMatch(
      /[A-Za-z]:[\\/]|\\\\|file:\/\/|\/(?:Users|home|root|tmp)\//i,
    );
    expect(visibleText).not.toMatch(/\.(?:gpkg|tif|zip|json|csv)\b/i);
  });

  it("fails closed when the Studio object is absent", () => {
    const html = renderToStaticMarkup(
      <QualifiedEvidenceFoundationPanel
        foundation={undefined}
        language="en"
      />,
    );

    expect(html).toContain("Qualified-reference status is unavailable");
    expect(html).toContain("experiment processing remains blocked");
    expect(html).not.toContain("processing_allowed=true");
  });

  it("does not render tampered payload content before integrity failure resolves", () => {
    const tampered = structuredClone(
      bundleJson.qualified_evidence_foundation,
    ) as QualifiedEvidenceFoundation;
    tampered.stages[1].detail_en =
      "TAMPERED EVIDENCE DETAIL MUST NEVER BE DISPLAYED";

    const html = renderToStaticMarkup(
      <QualifiedEvidenceFoundationPanel
        foundation={tampered}
        language="en"
      />,
    );

    expect(html).toContain(
      "Qualified-reference status verification is pending",
    );
    expect(html).not.toContain(
      "TAMPERED EVIDENCE DETAIL MUST NEVER BE DISPLAYED",
    );
    expect(html).not.toContain("AIT-VAP001-TH");
    expect(html).not.toContain("processing_allowed=true");
  });
});
