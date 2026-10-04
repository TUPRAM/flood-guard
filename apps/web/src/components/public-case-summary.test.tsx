import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
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
    const caseQuery = `aoi=${pkg.aoi_id}&amp;event=${pkg.event_id}&amp;version=${pkg.package_version}&amp;service=hospital&amp;mode=walking`;
    expect(html).toContain(`/studio/brief/?${caseQuery}`);
    expect(html).toContain(`/studio/library/?${caseQuery}`);
    expect(html).not.toContain('href="/command/');
    expect(html).not.toContain('href="/studio/?');
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
  it("keeps a selected route experiment separate from the aggregate candidate-flood closure", () => {
    const { evidence: pkg } = evidenceFixtures();
    const analysis = finalsAnalysisFixture();
    const impact = {
      ...analysis.services[0].variants[0].interventions[0],
      id: "candidate-flood-closure",
      losing_30_min_access: 12345,
    };
    const flood: NonNullable<typeof analysis.flood_scenarios>["walking"] = {
      status: "candidate_scenario_only",
      candidate_affected_population: 20000,
      unobserved_population: 5,
      closed_edges: [],
      impact,
      source_timestamp: "2024-09-15T00:00:00Z",
      candidate_provenance: { threshold_db: 2, method: "Synthetic fixture", limitations: [], sources: [] },
      subdistricts: [],
      normalization: {},
      limitations: [],
    };
    analysis.flood_scenarios = { walking: flood, modelled_vehicle: flood };
    pkg.decision_brief = decisionBriefFixture();
    pkg.decision_brief.finals_analysis = analysis;
    try {
      vi.stubGlobal("window", { location: { search: "?scenario=origin-1-hospital-walking-close" } });
      const routeHtml = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={false} />);
      expect(routeHtml).not.toContain("12,345");
      expect(routeHtml).not.toContain("under the candidate-flood closure scenario");
      expect(routeHtml).toContain("scenario=origin-1-hospital-walking-close");

      vi.stubGlobal("window", { location: { search: "?scenario=candidate-flood-closure" } });
      const floodHtml = renderToStaticMarkup(<PublicCaseSummary evidence={pkg} th={false} />);
      expect(floodHtml).toContain("12,345");
      expect(floodHtml).toContain("under the candidate-flood closure scenario");
    } finally {
      vi.unstubAllGlobals();
    }
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
