import evidenceRecordJsonFixture from "../../../../packages/contracts/examples/evidence-record.fixture-demo.json";
import { describe, expect, it } from "vitest";

import type { EvidenceRecord } from "@floodguard/contracts";

import {
  buildEvidenceDecisionMatrix,
  evidenceContextMatches,
  evidenceRecordFileName,
  evidenceRecordJson,
} from "./studio-evidence";

const record = evidenceRecordJsonFixture as EvidenceRecord;

describe("Studio evidence presentation", () => {
  it("requires an exact immutable evidence-context tuple", () => {
    expect(evidenceContextMatches(record.evidence_context, record)).toBe(true);
    expect(evidenceContextMatches(record.evidence_context, record, "another-context")).toBe(false);
    expect(evidenceContextMatches(
      { ...record.evidence_context, data_version: "different-version" },
      record,
    )).toBe(false);
    expect(evidenceContextMatches(record.evidence_context, null)).toBe(false);
    expect(evidenceContextMatches(
      { ...record.evidence_context, study_area_id: "different-study-area" },
      record,
    )).toBe(false);
  });

  it("does not infer decisions or authority from readiness", () => {
    const matrix = buildEvidenceDecisionMatrix(record.evidence_context, record);

    expect(matrix.find((row) => row.stage === "technical_verification")?.state).toBe("not_recorded");
    expect(matrix.find((row) => row.stage === "governance_decision")?.state).toBe("not_recorded");
    expect(matrix.find((row) => row.stage === "operational_authorization")?.state).toBe("blocked");
  });

  it("does not infer observed-event validation from official-input mode", () => {
    const officialInputRecord: EvidenceRecord = {
      ...record,
      evidence_context: {
        ...record.evidence_context,
        dataset_mode: "official_input",
        model_run_id: "model-run-1",
      },
      evaluation_sha256: "a".repeat(64),
    };

    const matrix = buildEvidenceDecisionMatrix(
      officialInputRecord.evidence_context,
      officialInputRecord,
    );

    expect(matrix.find((row) => row.stage === "technical_verification")?.state).toBe("recorded");
    expect(matrix.find((row) => row.stage === "observed_event_validation")?.state).toBe("not_recorded");
  });

  it("exports the server record without rewriting canonical provenance", () => {
    const json = evidenceRecordJson(record);
    const parsed = JSON.parse(json) as EvidenceRecord;

    expect(parsed.evidence_record_id).toBe(record.evidence_record_id);
    expect(parsed.evidence_context.evidence_context_id).toBe(record.evidence_context.evidence_context_id);
    expect(parsed.evidence_context.dataset_mode).toBe("fixture_demo");
    expect(parsed.evidence_context.operational_status).toBe("non_operational");
    expect(parsed.evidence_context.data_version).toBe("fixture-demo-1");
    expect(parsed.evidence_context.model_run_id).toBeNull();
    expect(parsed.decision_authority).toBeNull();
    expect(parsed.operational_authorized).toBe(false);
    expect(parsed.blockers).toEqual(record.blockers);
  });

  it("uses context, date, identity, and checksum in a collision-resistant filename", () => {
    const fileName = evidenceRecordFileName(record);

    expect(fileName).toMatch(/^floodguard-evidence-fixture_thailand_demo-no-bound-run-2026-07-16-/);
    expect(fileName).toContain(record.evidence_context.evidence_package_sha256.slice(0, 12));
    expect(fileName).toMatch(/\.json$/);
  });
});
