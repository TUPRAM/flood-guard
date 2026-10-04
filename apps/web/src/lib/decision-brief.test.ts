import { describe, expect, it } from "vitest";
import { parseDecisionBrief } from "./decision-brief";
import { decisionBriefFixture } from "./decision-brief.fixtures";

const parse = (value: unknown) => parseDecisionBrief(value, "test-aoi", "test-event", "2026-09-21T00:00:00Z");
describe("decision brief boundary", () => {
  it("keeps unknown impact separate from zero threshold change", () => {
    const brief = parse(decisionBriefFixture());
    expect(brief.affected_population).toBeNull();
    expect(brief.interventions[0].losing_30_min_access).toBe(0);
    expect(brief.interventions[0].slower_population).toBe(40);
  });
  it.each(["aoi_id", "event_id", "generated_at"])("rejects mixed %s", (field) => {
    expect(() => parse({ ...decisionBriefFixture(), [field]: "other" })).toThrow(/decision brief/);
  });
  it("rejects fabricated accepted priority, missing-data zero and nonconserving coverage", () => {
    const brief = decisionBriefFixture();
    expect(() => parse({ ...brief, affected_population: 0 })).toThrow();
    expect(() => parse({ ...brief, priority: { ...brief.priority, fpps: 90, action_class: "A" } })).toThrow();
    expect(() => parse({ ...brief, access: { ...brief.access, unknown_access_population: 0 } })).toThrow();
  });
  it("rejects observed intervention claims and unsafe source links", () => {
    const brief = decisionBriefFixture();
    expect(() => parse({ ...brief, interventions: [{ ...brief.interventions[0], observed: true }] })).toThrow();
    expect(() => parse({ ...brief, evidence_notes: [{topic:"test",status:"review",summary:"test",source_urls:["javascript:alert(1)"]}] })).toThrow();
  });
});
