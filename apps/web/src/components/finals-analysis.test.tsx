import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { finalsAnalysisFixture } from "@/lib/finals-analysis.fixtures";
import { decisionBriefFixture } from "@/lib/decision-brief.fixtures";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { DecisionBriefPanel } from "./decision-brief";
import { FinalsRouteComparisonPanel } from "./finals-route-comparison";
import { FinalsAnalysisPanel } from "./finals-analysis";

describe("finals route-first comparison", () => {
  it.each([false, true])("keeps supporting analysis in a closed accessible detail dialog (Thai: %s)", (th) => {
    const html = renderToStaticMarkup(<FinalsAnalysisPanel analysis={finalsAnalysisFixture()} layers={[]} th={th} context={<p>Accepted score remains unavailable.</p>} />);
    const dialogStart = html.search(/<dialog\b[^>]*data-finals-detail-panel="true"/);
    const dialog = html.slice(dialogStart, html.indexOf("</dialog>", dialogStart));
    expect(dialogStart).toBeGreaterThan(html.indexOf("data-route-comparison"));
    expect(html.slice(0, dialogStart)).toContain('data-finals-detail="population"');
    expect(html.slice(0, dialogStart)).toContain('data-finals-detail="interventions"');
    expect(html.slice(0, dialogStart)).toContain('data-finals-detail="evidence"');
    expect(html.slice(0, dialogStart)).not.toContain(th ? "ประชากรตามแบบจำลองในขอบเขต" : "Modelled residents in scope");
    expect(html.slice(dialogStart, html.indexOf(">", dialogStart))).not.toMatch(/\sopen(?:=|\s|$)/);
    expect(dialog).toContain('role="tablist"');
    expect(dialog.match(/role="tabpanel"/g)).toHaveLength(3);
    expect(dialog.match(/role="tab"/g)).toHaveLength(3);
    expect(dialog.match(/aria-selected="true"/g)).toHaveLength(1);
    expect(dialog.match(/hidden=""/g)).toHaveLength(2);
    expect(dialog).toMatch(/role="tabpanel"[^>]*-panel-evidence[^>]*hidden=""[^>]*>[\s\S]*Accepted score remains unavailable\./);
    expect(dialog).toContain(th ? ">ปิด</button>" : ">Close</button>");
  });
  it("retains controls and explanations if the package has no prepared routes", () => {
    const analysis = finalsAnalysisFixture();
    delete analysis.routes;
    const html = renderToStaticMarkup(<FinalsAnalysisPanel analysis={analysis} layers={[]} th={false} />);
    expect(html).toContain("Route data is unavailable for this comparison.");
    expect(html).toContain("Service needed");
    expect(html).toContain('value="main_road" disabled=""');
    expect(html).toContain("Main-road access — unavailable");
    expect(html).toContain("Modelled travel mode");
    expect(html).toContain('data-finals-detail="evidence"');
    expect(html).toContain("Flood evidence timeline");
  });
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
    expect(html).toContain("ยังไม่ยืนยันทางเข้า");
    expect(html).toContain("edge-1");
    expect(html).toContain("จุดเชื่อมสมมติ");
  });
  it.each([false, true])("makes single-hospital connection uncertainty visible before aggregate effects (Thai: %s)", (th) => {
    const analysis = finalsAnalysisFixture();
    analysis.services.find((item) => item.id === "hospital")!.facilities = 1;
    const html = renderToStaticMarkup(<FinalsAnalysisPanel analysis={analysis} layers={[]} th={th} />);
    expect(html).toContain(th ? "ควรตรวจสอบทางเข้าและจุดเชื่อมนี้ก่อน" : "make the entrance and connection a review priority");
    expect(html.indexOf('data-hospital-connection-caveat="true"')).toBeLessThan(html.indexOf(th ? "ผลการทดลองการเข้าถึง เลื่อนแนวนอนได้" : "Access experiments; scroll horizontally"));
  });
});
