import maeSaiBundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import type { EvidenceRecord } from "@floodguard/contracts";
import { describe, expect, it } from "vitest";

import { buildEvidenceDecisionMatrix } from "@/lib/studio-evidence";
import type { ReadinessRow } from "@/lib/types";

import {
  blockerPresentation,
  decisionReasonPresentation,
  readinessReasonPresentation,
} from "./studio-presentation";

const bundle = maeSaiBundleJson as unknown as {
  evidence_record: EvidenceRecord;
  readiness: ReadinessRow[];
};

describe("Studio Thai evidence presentation", () => {
  it("translates every decision explanation while retaining canonical rows", () => {
    const rows = buildEvidenceDecisionMatrix(
      bundle.evidence_record.evidence_context,
      bundle.evidence_record,
    );

    for (const row of rows) {
      expect(decisionReasonPresentation(row, "en")).toBe(row.reason);
      expect(decisionReasonPresentation(row, "th")).toMatch(/[\u0E00-\u0E7F]/u);
      expect(decisionReasonPresentation(row, "th")).not.toBe(row.reason);
      expect(row.stage).toMatch(/^[a-z_]+$/);
    }
  });

  it("translates all current readiness reasons without rewriting check IDs", () => {
    for (const row of bundle.readiness) {
      expect(readinessReasonPresentation(row, "en")).toBe(row.reason_blocked);
      expect(readinessReasonPresentation(row, "th")).toMatch(/[\u0E00-\u0E7F]/u);
      expect(row.check_id).toMatch(/^[a-z0-9_]+$/);
    }
  });

  it("translates every current authorization blocker", () => {
    for (const blocker of bundle.evidence_record.blockers) {
      expect(blockerPresentation(blocker, "en")).toBe(blocker);
      expect(blockerPresentation(blocker, "th")).toMatch(/[\u0E00-\u0E7F]/u);
      expect(blockerPresentation(blocker, "th")).not.toBe(blocker);
    }
  });
});
