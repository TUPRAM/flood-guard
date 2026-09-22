import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { decisionBriefFixture } from "@/lib/decision-brief.fixtures";
import { finalsAnalysisFixture } from "@/lib/finals-analysis.fixtures";
import { PublicCaseSummary } from "./public-case-summary";

describe("public study-case projection", () => {
  it.each([false, true])("keeps package selections and unavailable evidence explicit (Thai %s)", (th) => {
    const { evidence: pkg } = evidenceFixtures();
    pkg.decision_brief = decisionBriefFixture();
    pkg.decision_brief.finals_analysis = finalsAnalysisFixture();
    const html = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={th} />);
    expect(html).toContain("data-public-case-summary");
    expect(html).toContain(`/studio/brief/?aoi=${pkg.aoi_id}&amp;event=${pkg.event_id}`);
    expect(html).toContain("/command/cases/");
    expect(html).toContain("/studio/library/");
    expect(html).toContain(th ? "ยังไม่มี" : "Accepted FPPS / action class: unavailable");
    expect(html).not.toContain("safe evacuation route");
  });
  it("does not substitute Mae Sai analysis for a context-only area", () => {
    const { evidence: pkg } = evidenceFixtures();
    delete pkg.decision_brief;
    const html = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={false} />);
    expect(html).toContain("Evidence context only");
    expect(html).not.toContain("Baseline: within 30 minutes");
  });
});
