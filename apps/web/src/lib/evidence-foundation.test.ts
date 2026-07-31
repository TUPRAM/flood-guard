import { describe, expect, it } from "vitest";

import type {
  EvidenceContext,
  EvidenceRecord,
  LayerCatalogItem,
  SourceComponent,
  StatusResponse,
} from "@floodguard/contracts";

import {
  assertEvidenceContextMatches,
  evidenceContextsMatch,
  evidenceRecordMatchesContext,
} from "./evidence-context";
import { limitingFreshness, sourceTimestampLabel } from "./evidence-freshness";
import { visibleLayersForRole } from "./layer-visibility";

const component: SourceComponent = {
  source_component_id: "historic-flood",
  role: "flood_context",
  source_name: "Test source",
  source_version: "v1",
  source_timestamp: "2024-09-15T00:00:00Z",
  last_checked_at: "2026-07-20T00:00:00Z",
  temporal_meaning: "observation_time" as const,
  freshness: "historical" as const,
  freshness_policy_version: "source-freshness-v1" as const,
  freshness_as_of: "2026-07-20T00:00:00Z",
  attribution: ["Test source"],
};

const context: EvidenceContext = {
  schema_version: "1.0",
  evidence_context_id: "mae-sai:test-context",
  study_area_id: "mae_sai_candidate_v1",
  data_version: "test-v1",
  evidence_package_id: "test-package-v1",
  evidence_package_sha256: "a".repeat(64),
  model_run_id: null,
  dataset_mode: "candidate",
  operational_status: "non_operational",
  official_warning: false,
  generated_at: "2026-07-20T00:00:00Z",
  source_components: [component],
};

const status = {
  schema_version: "1.0",
  dataset_mode: "candidate",
  operational_status: "non_operational",
  source_timestamp: "2024-09-15T00:00:00Z",
  generated_at: "2026-07-20T00:00:00Z",
  confidence_class: "low",
  source_name: "Test",
  assumptions: ["Test only"],
  official_warning: false,
  data_version: "test-v1",
  git_commit: "abcdef1",
  evidence_context_id: "mae-sai:test-context",
  evidence_package_id: "test-package-v1",
  study_area: "mae_sai_candidate_v1",
  data_state: "stale",
  message_th: "ทดสอบ",
  message_en: "Test",
} satisfies StatusResponse;

describe("evidence foundation", () => {
  it("fails closed when a deep-linked context does not match", () => {
    expect(() => assertEvidenceContextMatches(
      context,
      status,
      "mae_sai_candidate_v1",
      "different-context",
    )).toThrow(/does not match/);
  });

  it("does not infer freshness from bundle generation time", () => {
    expect(limitingFreshness(context.source_components)).toBe("historical");
    expect(sourceTimestampLabel(component)).toBe("Observation time");
  });

  it("filters role visibility before callers use layer URLs", () => {
    const base = {
      schema_version: "1.0",
      dataset_mode: "candidate",
      operational_status: "non_operational",
      source_timestamp: "2024-09-15T00:00:00Z",
      generated_at: "2026-07-20T00:00:00Z",
      confidence_class: "low",
      source_name: "Test",
      assumptions: ["Test only"],
      official_warning: false,
      data_version: "test-v1",
      git_commit: "abcdef1",
      evidence_context_id: "mae-sai:test-context",
      evidence_package_id: "test-package-v1",
      title_th: "ทดสอบ",
      title_en: "Test",
      format: "geojson",
      data_state: "stale",
      model_run_id: null,
      evidence_state: {
        evidence_type: "modelled",
        granularity: "area_summary",
        confidence_class: "low",
        confidence_reason: "Test only",
        permitted_use: "planning_only",
        required_gate: "test",
        gate_state: "blocked",
      },
      source_components: [component],
      attribution: ["Test"],
    } satisfies Omit<LayerCatalogItem, "layer_id" | "role_visibility" | "url">;
    const layers: LayerCatalogItem[] = [
      { ...base, layer_id: "staff", role_visibility: ["command"], url: "/staff" },
      {
        ...base,
        layer_id: "public",
        role_visibility: ["public"],
        url: "/public",
        evidence_state: {
          ...base.evidence_state,
          permitted_use: "public_preparedness",
        },
      },
    ];
    expect(visibleLayersForRole(layers, "public").map((item) => item.layer_id))
      .toEqual(["public"]);
  });

  it("binds evidence exports to the exact package checksum", () => {
    const record = {
      schema_version: "1.0",
      evidence_record_id: "mae-sai:test-context:blocked",
      evidence_context: context,
      evidence_scope: "Test",
      model_id: null,
      model_version: null,
      model_sha256: null,
      evaluation_sha256: null,
      decision: "blocked",
      decision_authority: null,
      decision_at: null,
      operational_authorized: false,
      blockers: ["Test only"],
      generated_at: "2026-07-20T00:00:00Z",
    } satisfies EvidenceRecord;
    expect(evidenceRecordMatchesContext(record, context)).toBe(true);
    expect(evidenceRecordMatchesContext(
      record,
      { ...context, evidence_package_sha256: "b".repeat(64) },
    )).toBe(false);
    const mismatches: EvidenceContext[] = [
      { ...context, evidence_context_id: "mae-sai:other-context" },
      { ...context, study_area_id: "other-study-area" },
      { ...context, data_version: "other-version" },
      { ...context, evidence_package_id: "other-package" },
      { ...context, evidence_package_sha256: "b".repeat(64) },
      { ...context, model_run_id: "other-model-run" },
      { ...context, dataset_mode: "official_input" },
      { ...context, operational_status: "planning_only" },
      { ...context, official_warning: true },
      { ...context, generated_at: "2026-07-21T00:00:00Z" },
    ];
    expect(mismatches.every((candidate) => (
      !evidenceContextsMatch(context, candidate)
      && !evidenceRecordMatchesContext(record, candidate)
    ))).toBe(true);
  });
});
