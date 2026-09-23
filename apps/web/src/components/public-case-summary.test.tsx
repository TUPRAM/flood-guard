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
    expect(html).toContain(`/command/?aoi=${pkg.aoi_id}&amp;event=${pkg.event_id}&amp;version=${pkg.package_version}&amp;service=hospital&amp;mode=walking`);
    expect(html).toContain("/studio/?aoi=");
    expect(html).toContain("/studio/library/");
    expect(html).toContain(th ? "ยังไม่มี" : "Accepted FPPS / action class: unavailable");
    expect(html).toContain('value="main_road" disabled=""');
    expect(html).toContain(th ? "ถนนสายหลัก — ยังไม่มีผลการเข้าถึง" : "Main-road access — unavailable");
    expect(html).not.toContain("safe evacuation route");
  });
  it("does not substitute Mae Sai analysis for a context-only area", () => {
    const { evidence: pkg } = evidenceFixtures();
    delete pkg.decision_brief;
    const html = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={false} />);
    expect(html).toContain("Evidence context only");
    expect(html).not.toContain("Baseline: within 30 minutes");
  });
  it.each([false, true])("describes the lower-basin routing buffer without moving demand outside the AOI (Thai %s)", (th) => {
    const { evidence: pkg } = evidenceFixtures();
    pkg.aoi_id = "aoi-05_chao_phraya_bang_ban_sena";
    pkg.decision_brief = decisionBriefFixture();
    pkg.decision_brief.finals_analysis = finalsAnalysisFixture();
    const html = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={th} />);
    expect(html).toContain(th ? "พื้นที่กันชน 10 กม. รอบ AOI" : "10 km buffer around the AOI");
    expect(html).toContain(th ? "ประชากรและพื้นที่รายงานยังจำกัดที่ส่วนตัดกับ AOI" : "resident demand and reporting remain in AOI intersections");
    expect(html).not.toContain(th ? "เส้นทางนอก AOI ยังไม่ได้ประเมิน" : "Paths beyond the AOI are not evaluated");
  });
});
