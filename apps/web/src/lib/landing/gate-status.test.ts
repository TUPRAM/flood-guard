import { describe, expect, it } from "vitest";
import copy from "./copy.en.json";
import { landingGateStatus, resolveGateCriteria, type GateStatusDocument } from "./gate-status";

const RECEIPT_IDS = ["automated_optical_reference", "automated_cross_review", "preregistered_holdout_evaluation"];

function status(overrides: Record<string, { met: boolean; receipt_sha256: string | null }>): GateStatusDocument {
  const criteria = Object.fromEntries(RECEIPT_IDS.map(id => [id, { met: false, receipt_sha256: null }]));
  return { schema: "floodguard.landing_gate_status.v1", track: "automated", generated_utc: "2026-09-24T00:00:00Z", criteria: { ...criteria, ...overrides } };
}

describe("landing gate status", () => {
  it("the committed automated status carries three receipt-driven criteria", () => {
    expect(landingGateStatus.track).toBe("automated");
    expect(landingGateStatus).toMatchObject({ human_reviewed: false, can_feed_decision_layer: false,
      official_warning: false, operational_status: "non_operational" });
    for (const id of RECEIPT_IDS) {
      const criterion = landingGateStatus.criteria[id];
      expect(criterion).toBeDefined();
      if (criterion.met) expect(criterion.receipt_sha256).toMatch(/^[0-9a-f]{64}$/);
      else expect(criterion.receipt_sha256).toBeNull();
    }
  });

  it("the three receipt-driven criteria are bound by id in the copy", () => {
    const ids = copy.pipeline.gate.criteria.map(c => ("id" in c ? c.id : undefined)).filter(Boolean);
    expect(ids.sort()).toEqual([...RECEIPT_IDS].sort());
  });

  it("ignores a copy value of true for a receipt-driven criterion", () => {
    const criteria = [{ id: "automated_optical_reference", label: "Ref", met: true, detail: "no", detail_met: "yes" }];
    const [resolved] = resolveGateCriteria(criteria, status({}));
    expect(resolved).toMatchObject({ met: false, detail: "no", source: "receipt", receiptSha256: null });
  });

  it("needs both met and a SHA-256 receipt", () => {
    const criteria = [{ id: "automated_optical_reference", label: "Ref", met: false, detail: "no", detail_met: "yes" }];
    const noReceipt = resolveGateCriteria(criteria, status({ automated_optical_reference: { met: true, receipt_sha256: null } }));
    expect(noReceipt[0].met).toBe(false);
    const badReceipt = resolveGateCriteria(criteria, status({ automated_optical_reference: { met: true, receipt_sha256: "abc" } }));
    expect(badReceipt[0].met).toBe(false);
    const ok = resolveGateCriteria(criteria, status({ automated_optical_reference: { met: true, receipt_sha256: "a".repeat(64) } }));
    expect(ok[0]).toMatchObject({ met: true, detail: "yes", receiptSha256: "a".repeat(64) });
  });

  it("fails closed when an automated receipt entry is missing", () => {
    const [resolved] = resolveGateCriteria([{ id: "automated_cross_review", label: "Review", met: true, detail: "no" }],
      { ...status({}), criteria: {} });
    expect(resolved).toMatchObject({ met: false, source: "receipt", receiptSha256: null });
  });

  it("keeps copy values for criteria without a status entry", () => {
    const [resolved] = resolveGateCriteria([{ label: "Provenance", met: true, detail: "d" }], status({}));
    expect(resolved).toMatchObject({ met: true, source: "copy" });
  });
});
