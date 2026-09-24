import { describe, expect, it } from "vitest";
import copy from "./copy.en.json";
import { landingGateStatus, resolveGateCriteria, type GateStatusDocument } from "./gate-status";

const RECEIPT_IDS = ["qualified_reference_mask", "frozen_holdout_and_calibration", "blind_review_and_adjudication"];

function status(overrides: Record<string, { met: boolean; receipt_sha256: string | null }>): GateStatusDocument {
  const criteria = Object.fromEntries(RECEIPT_IDS.map(id => [id, { met: false, receipt_sha256: null }]));
  return { schema: "floodguard.landing_gate_status.v1", generated_utc: "2026-09-24T00:00:00Z", criteria: { ...criteria, ...overrides } };
}

describe("landing gate status", () => {
  it("the committed status keeps all three receipt-driven gates closed", () => {
    for (const id of RECEIPT_IDS) {
      expect(landingGateStatus.criteria[id]).toMatchObject({ met: false, receipt_sha256: null });
    }
  });

  it("the three receipt-driven criteria are bound by id in the copy", () => {
    const ids = copy.pipeline.gate.criteria.map(c => ("id" in c ? c.id : undefined)).filter(Boolean);
    expect(ids.sort()).toEqual([...RECEIPT_IDS].sort());
  });

  it("ignores a copy value of true for a receipt-driven criterion", () => {
    const criteria = [{ id: "qualified_reference_mask", label: "Ref", met: true, detail: "no", detail_met: "yes" }];
    const [resolved] = resolveGateCriteria(criteria, status({}));
    expect(resolved).toMatchObject({ met: false, detail: "no", source: "receipt", receiptSha256: null });
  });

  it("needs both met and a SHA-256 receipt", () => {
    const criteria = [{ id: "qualified_reference_mask", label: "Ref", met: false, detail: "no", detail_met: "yes" }];
    const noReceipt = resolveGateCriteria(criteria, status({ qualified_reference_mask: { met: true, receipt_sha256: null } }));
    expect(noReceipt[0].met).toBe(false);
    const badReceipt = resolveGateCriteria(criteria, status({ qualified_reference_mask: { met: true, receipt_sha256: "abc" } }));
    expect(badReceipt[0].met).toBe(false);
    const ok = resolveGateCriteria(criteria, status({ qualified_reference_mask: { met: true, receipt_sha256: "a".repeat(64) } }));
    expect(ok[0]).toMatchObject({ met: true, detail: "yes", receiptSha256: "a".repeat(64) });
  });

  it("keeps copy values for criteria without a status entry", () => {
    const [resolved] = resolveGateCriteria([{ label: "Provenance", met: true, detail: "d" }], status({}));
    expect(resolved).toMatchObject({ met: true, source: "copy" });
  });
});
