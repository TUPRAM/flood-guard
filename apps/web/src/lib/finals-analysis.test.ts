import { describe, expect, it } from "vitest";
import { finalsAnalysisFixture } from "./finals-analysis.fixtures";
import { decisionBriefFixture } from "./decision-brief.fixtures";
import { parseFinalsAnalysis } from "./finals-analysis";
import { parseDecisionBrief } from "./decision-brief";

const parse = (value: unknown) => parseFinalsAnalysis(value, "2026-09-21T00:00:00Z");
describe("finals service and route evidence", () => {
  it("rejects a candidate claim with no flood computation", () => {
    const value = finalsAnalysisFixture();
    value.case_identity!.flood_basis = "unvalidated_satellite_candidate";
    expect(() => parse(value)).toThrow();
  });
  it("rejects another area's analysis even when the outer brief matches", () => {
    const value = finalsAnalysisFixture();
    value.case_identity!.aoi_id = "another-area";
    const brief = { ...decisionBriefFixture(), finals_analysis: value };
    expect(() => parseDecisionBrief(brief, brief.aoi_id, brief.event_id, brief.generated_at)).toThrow();
  });
  it("accepts one linked scenario while keeping accepted claims unavailable", () => {
    const value = finalsAnalysisFixture();
    expect(parse(value)).toBe(value);
    const brief = { ...decisionBriefFixture(), finals_analysis: value };
    expect(parseDecisionBrief(brief, brief.aoi_id, brief.event_id, brief.generated_at).priority.fpps).toBeNull();
  });
  it("rejects mixed generation times and unreconciled geographic population", () => {
    const value = finalsAnalysisFixture(); value.scope.excluded_population = 0;
    expect(() => parse(value)).toThrow(/scope/);
    expect(() => parse({ ...finalsAnalysisFixture(), generated_at: "2026-01-01T00:00:00Z" })).toThrow();
  });
  it("accepts an earlier, receipt-bound analysis while rejecting a future or unbound one", () => {
    const brief = { ...decisionBriefFixture(), finals_analysis: { ...finalsAnalysisFixture(), generated_at: "2026-09-20T00:00:00Z" } };
    const hashes = { finals_receipt_sha256: "a".repeat(64), finals_generation_identity_sha256: "b".repeat(64) };
    expect(parseDecisionBrief(brief, brief.aoi_id, brief.event_id, brief.generated_at, hashes).priority.fpps).toBeNull();
    expect(() => parseDecisionBrief(brief, brief.aoi_id, brief.event_id, brief.generated_at)).toThrow();
    brief.finals_analysis.generated_at = "2026-09-22T00:00:00Z";
    expect(() => parseDecisionBrief(brief, brief.aoi_id, brief.event_id, brief.generated_at, hashes)).toThrow();
  });
  it("rejects substitution of available facilities into an unavailable service", () => {
    const value = finalsAnalysisFixture(); value.services[3].facilities = 1;
    expect(() => parse(value)).toThrow(/service/);
  });
  it("rejects a nonmonotone threshold count and excessive route coverage", () => {
    const value = finalsAnalysisFixture(); value.services[0].variants[0].baseline.within_15_minutes_population = 80;
    expect(() => parse(value)).toThrow();
    value.services[0].variants[0].baseline.within_15_minutes_population = 30;
    value.services[0].variants[0].baseline.within_60_minutes_population = 71;
    expect(() => parse(value)).toThrow();
  });
  it("rejects changing an intervention target after sensitivity outcomes are known", () => {
    const value = finalsAnalysisFixture(); value.services[0].variants[1].interventions[0].target_id = "n-new";
    expect(() => parse(value)).toThrow(/scenario identity/);
  });
  it("requires a complete distinct speed/mode matrix", () => {
    const value = finalsAnalysisFixture(); value.services[0].variants[0].speed_factor = 1;
    expect(() => parse(value)).toThrow();
  });
  it("rejects an unlinked capacity site or nonconserved demand", () => {
    const value = finalsAnalysisFixture(); value.capacity.site_id = "different-site";
    expect(() => parse(value)).toThrow(/capacity/);
    value.capacity.site_id = "hypothetical-n3"; value.capacity.experiments[0].assigned = 10;
    expect(() => parse(value)).toThrow(/capacity/);
  });
  it("rejects unsupported actual capacity and fabricated review acceptance", () => {
    const value = finalsAnalysisFixture(); Object.assign(value.facility_review[0], { actual_capacity: 50 });
    expect(() => parse(value)).toThrow();
    const other = finalsAnalysisFixture(); other.topology_review!.accepted_connections = 3;
    expect(() => parse(other)).toThrow();
  });
  it("rejects a wrong route origin, coordinate order or inconsistent time delta", () => {
    const value = finalsAnalysisFixture(); value.routes!.comparisons[0].origin_id = "unknown";
    expect(() => parse(value)).toThrow();
    value.routes!.comparisons[0].origin_id = "origin-1"; value.routes!.origins[0].latitude = 99.88;
    expect(() => parse(value)).toThrow();
    value.routes!.origins[0].latitude = 20.421; value.routes!.comparisons[0].delta_minutes = 0;
    expect(() => parse(value)).toThrow();
  });
  it("rejects fake geometry or zero time on an unavailable route", () => {
    const value = finalsAnalysisFixture(); value.routes!.comparisons[0].after.status = "unavailable";
    expect(() => parse(value)).toThrow();
  });
  it("rejects an available path whose edge order cannot match its geometry", () => {
    const value = finalsAnalysisFixture(); value.routes!.comparisons[0].after.coordinates.pop();
    expect(() => parse(value)).toThrow();
  });
});
