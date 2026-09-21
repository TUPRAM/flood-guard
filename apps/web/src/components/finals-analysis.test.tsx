import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { finalsAnalysisFixture } from "@/lib/finals-analysis.fixtures";
import { decisionBriefFixture } from "@/lib/decision-brief.fixtures";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { DecisionBriefPanel } from "./decision-brief";
import { FinalsRouteComparisonPanel } from "./finals-route-comparison";
import { FinalsAnalysisPanel } from "./finals-analysis";

describe("finals route-first comparison", () => {
  it("leads with a public origin and explicit before/after, retaining null accepted claims", () => {
    const { evidence } = evidenceFixtures(); evidence.decision_brief = { ...decisionBriefFixture(), finals_analysis: finalsAnalysisFixture() };
    const html = renderToStaticMarkup(<DecisionBriefPanel evidence={evidence} th={false} />);
    expect(html).toContain("From this place, how does the route change?");
    expect(html.indexOf("From this place")).toBeLessThan(html.indexOf("Baseline before the imposed change"));
    expect(html).toContain("Synthetic public square");
    expect(html).toContain("+5 minutes");
    expect(html).toContain("Pharmacies do not substitute for hospitals or shelters");
    expect(html).toContain("Flood-affected population");
    expect(html).toContain("Age-group equity");
    expect(html).toContain("Unknown");
    expect(html).not.toContain("Separate hypothetical location from the access addition");
  });
  it("keeps no route and zero change distinct without substituting another service", () => {
    const routes = finalsAnalysisFixture().routes!;
    const empty = renderToStaticMarkup(<FinalsRouteComparisonPanel routes={routes} service="shelter" mode="walking" layers={[]} th={false} />);
    expect(empty).toContain("Another origin or service is not substituted");
    expect(empty).not.toContain("Synthetic hospital");
    routes.comparisons[0].delta_minutes = 0;
    expect(renderToStaticMarkup(<FinalsRouteComparisonPanel routes={routes} service="hospital" mode="walking" layers={[]} th={false} />)).toContain("No difference in this case");
  });
  it("has a Thai text equivalent and identifies connectors and unverified safety", () => {
    const routes = finalsAnalysisFixture().routes!;
    const html = renderToStaticMarkup(<FinalsRouteComparisonPanel routes={routes} service="hospital" mode="walking" layers={[]} th />);
    expect(html).toContain("จากจุดนี้ เส้นทางเปลี่ยนอย่างไร");
    expect(html).toContain("ยังไม่ได้ตรวจทางเข้า");
    expect(html).toContain("edge-1");
    expect(html).toContain("จุดเชื่อมต่อตามสมมติฐาน");
  });
  it.each([false, true])("makes single-hospital connection uncertainty visible before aggregate effects (Thai: %s)", (th) => {
    const analysis = finalsAnalysisFixture();
    analysis.services.find((item) => item.id === "hospital")!.facilities = 1;
    const html = renderToStaticMarkup(<FinalsAnalysisPanel analysis={analysis} layers={[]} th={th} />);
    expect(html).toContain(th ? "ควรตรวจสอบทางเข้าและจุดเชื่อมนี้ก่อน" : "make the entrance and connection a review priority");
    expect(html.indexOf('data-hospital-connection-caveat="true"')).toBeLessThan(html.indexOf(th ? "ผลการทดลองการเข้าถึง เลื่อนแนวนอนได้" : "Access experiments; scroll horizontally"));
  });
});
