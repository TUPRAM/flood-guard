import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { decisionBriefFixture } from "@/lib/decision-brief.fixtures";
import { finalsAnalysisFixture } from "@/lib/finals-analysis.fixtures";
import { DecisionBriefPanel } from "./decision-brief";
import { EvidenceLibrary } from "./evidence-library";

describe("concise decision view", () => {
  it("shows scenario impacts and unknown event totals without the research card wall", () => {
    const {catalog,evidence} = evidenceFixtures(); evidence.decision_brief = decisionBriefFixture();
    evidence.decision_brief.interventions[0].mean_travel_time_delta_minutes = .0173;
    const html = renderToStaticMarkup(<EvidenceLibrary view="brief" initialCatalog={catalog} initialPackage={evidence} />);
    expect(html).toContain("+0.0173");
    expect(html).toContain("Study-area decision brief");
    expect(html).toContain("Flood-affected population");
    expect(html).toContain("Unknown");
    expect(html).toContain("Travel times change even though nobody crosses");
    expect(html).toContain("Access unknown: no accepted connection");
    expect(html).toContain("Main-road access: unavailable as a separate qualified service result");
    expect(html).not.toContain("Acquired data and coverage");
    expect(html).not.toContain("Primary FPPS: unavailable.");
    expect(html).toContain("/studio/library/?aoi=test-aoi&amp;event=test-event");
  });
  it("renders Thai decisions with the same uncertainty boundary", () => {
    const {evidence} = evidenceFixtures(); evidence.decision_brief = decisionBriefFixture();
    const html = renderToStaticMarkup(<DecisionBriefPanel evidence={evidence} th />);
    expect(html).toContain("ประชากรที่ได้รับผลจากน้ำท่วม");
    expect(html).toContain("ยังไม่ทราบ");
    expect(html).toContain("เวลาเดินทางเปลี่ยน");
  });
  it("does not synthesize a brief for an old package or another selection", () => {
    const {catalog,evidence} = evidenceFixtures();
    expect(renderToStaticMarkup(<DecisionBriefPanel evidence={evidence} th={false} />)).toContain("unavailable for this package");
    const html = renderToStaticMarkup(<EvidenceLibrary view="brief" initialCatalog={catalog} initialPackage={evidence} initialAoiId="unknown" />);
    expect(html).toContain("Another area&#x27;s data will not be substituted");
    expect(html).not.toContain("data-decision-brief");
  });
  it("keeps a source analysis creation time distinct from a later release in the concise brief", () => {
    const {evidence} = evidenceFixtures();
    evidence.generated_at = "2026-09-23T12:00:00Z";
    evidence.decision_brief = decisionBriefFixture();
    evidence.decision_brief.generated_at = evidence.generated_at;
    evidence.decision_brief.finals_analysis = finalsAnalysisFixture();
    const html = renderToStaticMarkup(<DecisionBriefPanel evidence={evidence} th={false} />);
    expect(html).toContain(`data-source-analysis-generated-at="${evidence.decision_brief.finals_analysis.generated_at}"`);
    expect(html).toContain('data-package-release-generated-at="2026-09-23T12:00:00Z"');
    expect(html).toContain("Source analysis generated");
    expect(html).toContain("Package release generated");
  });
});
