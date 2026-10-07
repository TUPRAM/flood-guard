/**
 * The planning assessment overlay parser against the committed fixture (plan task E11).
 *
 * The fixture is written by Python (`apps/web/scripts/planning-overlay-fixture.py`) after the JSON schema and the
 * strict Python validator accept it; pytest checks that the committed file is what Python writes today
 * (`tests/test_planning_overlay.py`). Here the TypeScript parser reads the same bytes and must find the same
 * content: the same file hash, the same content digest and the same counts as the summary Python wrote. The refusal
 * cases are shared with pytest, so both parsers refuse the same things for the same reason. The fixture is an
 * invented case with invented units: a fixture, not a place.
 *
 * The parser checks every overlay against `planning-protocol-binding.json`, which Python writes from the two signed
 * protocol files. The tests here read those two files too, so a constant the parser uses cannot drift from them.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ASSIGNED_CONFIDENCE_CLASSES,
  caseFloodInputNames,
  classByRuleV1,
  CONFIDENCE_BASIS_VALUES,
  CONFIDENCE_CONDITION_IDS,
  EVIDENCE_TIERS,
  expectedConfidenceBasis,
  expectedTemporalRelation,
  HEADLINE_STATUSES,
  INPUT_ROLES,
  ISO_DATE_PATTERN,
  LANE_COLUMNS,
  NO_V2_TRIGGER,
  parsePlanningAssessmentOverlay,
  PLANNING_ACTION_CLASSES,
  PLANNING_LANES,
  PLANNING_OVERLAY_REFUSAL_CODES,
  PLANNING_OVERLAY_SCHEMA_ID,
  PLANNING_OVERLAY_SHAPE,
  PLANNING_PROTOCOL_BINDING,
  PLANNING_REASON_CODES,
  PlanningOverlayError,
  planningOverlayProblems,
  PRODUCT_4009_CREDIT,
  PRODUCT_4009_LICENCE,
  PRODUCT_4009_SOURCE,
  PUBLICATION_LEVELS,
  SCORE_COMPONENTS,
  summarisePlanningAssessmentOverlay,
  TEMPORAL_RELATIONS,
  V2_TRIGGER_ORDER,
  type DerivedConfidence,
  type OverlaySpec,
  type PlanningAssessmentOverlay,
  type ScoreComponent,
} from "./planning-assessment-overlay";
import { canonicalJson } from "./qualified-evidence-foundation";

type Json = Record<string, unknown>;
interface PatchStep {
  row?: string;
  input?: string;
  path: (string | number)[];
  set?: unknown;
  delete?: boolean;
}
interface RefusalCase {
  id: string;
  refuses: string;
  basis: string;
  checked_by: ("schema" | "python" | "typescript" | "python_with_protocols")[];
  patch: PatchStep[];
}

const repository = resolve(import.meta.dirname, "../../../..");
const fixtures = resolve(import.meta.dirname, "__fixtures__");
const fixtureBytes = readFileSync(resolve(fixtures, "planning-assessment-overlay.fixture.json"));
const fixtureText = fixtureBytes.toString("utf8");
const readFixture = (): Json => JSON.parse(fixtureText) as Json;
const pythonSummary = JSON.parse(readFileSync(resolve(fixtures, "planning-assessment-overlay.fixture.summary.json"), "utf8")) as {
  fixture: string;
  file_sha256: string;
  summary: Json & { content_sha256: string };
};
const refusals = JSON.parse(readFileSync(resolve(fixtures, "planning-assessment-overlay.refusals.json"), "utf8")) as { cases: RefusalCase[] };
const schema = JSON.parse(readFileSync(resolve(repository, "packages/contracts/schemas/planning-assessment-overlay.schema.json"), "utf8")) as Json & { $defs: Record<string, Json> };
const protocolBytes = { v1a: readFileSync(resolve(repository, "docs/proposal_execution/planning_protocol_v1a.json")), v1b: readFileSync(resolve(repository, "docs/proposal_execution/planning_protocol_v1b.json")) };
const sha256 = (data: string | Buffer) => createHash("sha256").update(data).digest("hex");
const binding = PLANNING_PROTOCOL_BINDING;
const codes = (value: unknown) => [...new Set(planningOverlayProblems(value).map((problem) => problem.code))];

/** Apply the steps of a refusal case to a fresh copy of the fixture. */
function patched(steps: PatchStep[]): Json {
  const overlay = readFixture();
  for (const step of steps) {
    let target: unknown = overlay;
    if (step.row) target = (overlay.rows as Json[]).find((row) => row.row_id === step.row);
    if (step.input) target = (overlay.inputs as Json[]).find((item) => item.input_id === step.input);
    expect(target, `the fixture has ${step.row ?? step.input}`).toBeDefined();
    for (const key of step.path.slice(0, -1)) target = (target as Record<string | number, unknown>)[key];
    const last = step.path[step.path.length - 1];
    if (step.delete) delete (target as Record<string | number, unknown>)[last];
    else (target as Record<string | number, unknown>)[last] = step.set;
  }
  return overlay;
}

/**
 * The fixture's dated agency rows relabelled, in memory, as a candidate overlay of protocol case O2: the case header
 * and the flood input carry the names and the date protocol v1a gives, and the units stay invented. It tests the
 * candidate path of the parser. It is not a result for any place and is never written to a file.
 */
function relabelledAsCaseO2(): PlanningAssessmentOverlay {
  const overlay = readFixture() as unknown as PlanningAssessmentOverlay;
  const o2 = binding.cases.find((item) => item.id === "O2")!;
  const referenceDate = o2.case_reference_date!;
  const name = o2.flood_inputs[0];
  overlay.dataset_mode = "candidate";
  Object.assign(overlay.case, { case_id: o2.id, kind: "portfolio_case", fixture_notice: null, case_reference_date: referenceDate });
  const flood = overlay.inputs.find((item) => item.input_id === "fx_agency_extent_dated")!;
  Object.assign(flood, { name, source_product: PRODUCT_4009_SOURCE, acquisition_date: binding.product_4009.dated_acquisition_date, licence: PRODUCT_4009_LICENCE, attribution: `${PRODUCT_4009_CREDIT}, CC BY-SA 4.0`, change_notice: "Changed by FloodGuard: text of this test only." });
  overlay.rows = overlay.rows.filter((row) => row.tier === "T3" && row.lineage.flood_input_id === flood.input_id);
  for (const row of overlay.rows) {
    const record = row.confidence as DerivedConfidence;
    row.flood_input = name;
    record.flood_input = name;
    Object.assign(record.measurements, { acquisition_date: flood.acquisition_date, case_reference_date: referenceDate, recency_days: 0 });
  }
  return overlay;
}

describe("Planning assessment overlay: the fixture Python wrote", () => {
  const raw = readFixture();
  const overlay = parsePlanningAssessmentOverlay(readFixture());

  it("is accepted, and parsing changes nothing", () => {
    expect(planningOverlayProblems(raw)).toEqual([]);
    expect(overlay).toEqual(raw);
    expect(overlay.schema_id).toBe(PLANNING_OVERLAY_SCHEMA_ID);
  });

  it("holds the same content Python wrote: file hash, content digest and every count", () => {
    expect(pythonSummary.fixture).toBe("planning-assessment-overlay.fixture.json");
    expect(fixtureBytes.includes(0x0d)).toBe(false);
    expect(sha256(fixtureBytes)).toBe(pythonSummary.file_sha256);
    const { content_sha256: pythonDigest, ...pythonCounts } = pythonSummary.summary;
    expect(sha256(canonicalJson(overlay))).toBe(pythonDigest);
    expect(summarisePlanningAssessmentOverlay(overlay)).toEqual(pythonCounts);
  });

  it("is labelled as a fixture that is not a place, not an official warning and non-operational", () => {
    expect(overlay.dataset_mode).toBe("fixture_demo");
    expect(overlay.case.kind).toBe("fixture");
    expect(overlay.case.fixture_notice).toContain("not a place");
    expect(overlay.official_warning).toBe(false);
    expect(overlay.operational_status).toBe("non_operational");
    expect(overlay.can_feed_decision_layer).toBe(false);
    expect([overlay.accepted_fpps, overlay.accepted_action_class]).toEqual([null, null]);
    for (const row of overlay.rows) {
      expect(row.unit_name_en, row.row_id).toContain("not a place");
      expect(row.unit_id, row.row_id).toMatch(/^FX-[UE][0-9]{2}$/);
      expect([row.accepted_fpps, row.accepted_action_class], row.row_id).toEqual([null, null]);
      expect(row.source_timestamp && row.assumptions.length, row.row_id).toBeTruthy();
    }
    // No unit code of a real Thai subdistrict, and no flood input the protocol names.
    expect(fixtureText).not.toMatch(/TH[0-9]{6}|M1-v2|M1-literal|UN-SPIDER|A6-prime|CHIANGRAI_|4009/);
  });

  it("carries real text only where the signed protocols put it: the frame header and the protocol hashes", () => {
    // The notice says so, and does not claim that every string of the file is invented.
    expect(overlay.case.fixture_notice).toContain("are those of the signed protocols");
    expect(overlay.assumptions.join(" ")).toContain("They describe the protocol, not a unit of this file.");
    // The one real place name is inside the anchor disclosure of frame v1, which every overlay carries unchanged.
    const disclosure = binding.scoring_frame.flood_anchor_disclosure;
    expect(disclosure).toContain("Mae Sai");
    const withoutFrameText = fixtureText.split(JSON.stringify(disclosure).slice(1, -1)).join("");
    expect(withoutFrameText).not.toMatch(/Mae Sai|Chiang Rai|Rim Kok|Hat Yai/);
    expect(overlay.scoring_frame).toEqual(binding.scoring_frame);
    expect(overlay.protocol_sha256).toEqual(binding.protocol_sha256);
  });

  it("exercises every tier, lane, reason code, failed condition, would-be class and v2 outcome", () => {
    const summary = summarisePlanningAssessmentOverlay(overlay);
    const unused = (counts: Record<string, number>, keys: readonly string[]) => keys.filter((key) => !counts[key]);
    const across = (byColumn: Record<string, Record<string, number>>): Record<string, number> => {
      const out: Record<string, number> = {};
      for (const counts of Object.values(byColumn)) for (const [key, count] of Object.entries(counts)) out[key] = (out[key] ?? 0) + count;
      return out;
    };
    expect(unused(summary.rows_by_tier, EVIDENCE_TIERS)).toEqual([]);
    expect(unused(summary.rows_by_lane, PLANNING_LANES)).toEqual([]);
    expect(unused(summary.rows_by_temporal_relation, TEMPORAL_RELATIONS)).toEqual([]);
    expect(unused(across(summary.reason_code_by_lane_column), PLANNING_REASON_CODES)).toEqual([]);
    expect(unused(summary.binding_class_by_lane_column.OBS, PLANNING_ACTION_CLASSES)).toEqual([]);
    expect(unused(summary.binding_class_by_lane_column.ENG, PLANNING_ACTION_CLASSES)).toEqual([]);
    expect(unused(across(summary.would_be_class_by_lane_column), PLANNING_ACTION_CLASSES)).toEqual([]);
    expect(unused(across(summary.v2_result_by_lane_column), [...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER])).toEqual([]);
    expect(unused(across(summary.failed_conditions_by_lane_column), CONFIDENCE_CONDITION_IDS)).toEqual([]);
    expect(unused(across(summary.headline_status_by_lane_column), HEADLINE_STATUSES)).toEqual([]);
    expect(unused(summary.confidence_class_by_lane_column.OBS, ASSIGNED_CONFIDENCE_CLASSES)).toEqual([]);
    expect(unused(summary.inputs_by_rights_level, PUBLICATION_LEVELS)).toEqual([]);
    expect(overlay.publication_eligibility).toBe("local");
    // Condition C3 by construction is granted to product 4009 in the eight Mae Sai tambons only: not in a fixture.
    expect(across(summary.basis_values_by_lane_column)).toMatchObject({ by_construction: 0 });
    // The scenario declaration is counted in the SCN column, and never in the observed one.
    expect(summary.basis_values_by_lane_column.SCN.by_scenario_declaration).toBeGreaterThan(0);
    expect(summary.basis_values_by_lane_column.OBS.by_scenario_declaration).toBe(0);
  });

  it("counts classes and confidence per lane column, never observed, scenario and engine rows together", () => {
    const summary = summarisePlanningAssessmentOverlay(overlay);
    const total = (counts: Record<string, number>) => Object.values(counts).reduce((sum, count) => sum + count, 0);
    const rowsIn = (column: string) => overlay.rows.filter((row) => (row.lane === "SCN-ENV" ? "SCN" : row.lane ?? "no_lane") === column);
    for (const column of LANE_COLUMNS) {
      expect(total(summary.binding_class_by_lane_column[column]), column).toBe(rowsIn(column).length);
      expect(total(summary.confidence_class_by_lane_column[column]), column).toBe(rowsIn(column).length);
      for (const letter of PLANNING_ACTION_CLASSES) {
        expect(summary.binding_class_by_lane_column[column][letter], `${column} ${letter}`).toBe(rowsIn(column).filter((row) => row.action_class === letter).length);
      }
    }
    // Lane SCN-ENV is part of the SCN column; the locked tier has no lane and no class.
    expect(total(summary.binding_class_by_lane_column.SCN)).toBe(summary.rows_by_lane.SCN + summary.rows_by_lane["SCN-ENV"]);
    expect(summary.binding_class_by_lane_column.no_lane).toMatchObject({ A: 0, B: 0, C: 0, D: 0, E: 0, none: summary.rows_by_tier.T4 });
    expect(Object.keys(summary).filter((key) => /^rows_by_(binding_class|would_be_class|confidence_class|reason_code|v2_result)/.test(key))).toEqual([]);
  });

  it("shows each guardrail outcome the protocols name", () => {
    const row = (key: string) => overlay.rows.find((item) => item.row_id === `FX-CASE-01:${key}`)!;
    // GR1: fewer than 100 residents, so no binding class, no would-be class and no v2 class.
    const small = row("obs-t3-c6-gr1-no-class");
    expect([small.action_class, small.action_reason_code, small.would_be_class, small.class_v2?.result]).toEqual([null, "insufficient_denominator", null, null]);
    expect(small.confidence).toMatchObject({ confidence_class: "low", failed_conditions: ["C6_residents"], reason_code: "insufficient_denominator" });
    // Low confidence forces class E; the would-be class is kept beside it and is not the binding class.
    const lowRows = overlay.rows.filter((item) => item.confidence?.confidence_class === "low" && item.action_class !== null);
    expect(lowRows.length).toBeGreaterThan(5);
    for (const item of lowRows) expect([item.action_class, item.action_reason_code], item.row_id).toEqual(["E", "low_confidence"]);
    expect(row("obs-t3-c7-baseline-no-route")).toMatchObject({ action_class: "E", would_be_class: "A" });
    // GR7: the OBS row that is not event_aligned stays at E.
    expect(row("obs-t3-c2-not-event-aligned")).toMatchObject({ lane: "OBS", temporal_relation: "dated_other", action_class: "E", would_be_class: "B" });
    for (const item of overlay.rows) {
      if (item.lane === "OBS" && item.temporal_relation !== "event_aligned") expect(item.action_class, item.row_id).toBe("E");
    }
    // v2 is a labelled secondary axis; "no v2 trigger met" is its own outcome.
    expect(row("obs-t3-no-v2-trigger").class_v2).toMatchObject({ label: "secondary", binding: false, result: "no_v2_trigger" });
    // GR8: eligible at or above 0.6 retention, otherwise unstable, and not evaluated until an ensemble has run.
    expect(row("obs-t3-class-a").headline_stability).toMatchObject({ status: "headline_eligible", class_retention: 0.83 });
    expect(row("obs-t3-class-b").headline_stability).toMatchObject({ status: "unstable_verify", class_retention: 0.41 });
    expect(row("obs-t3-class-c").headline_stability).toMatchObject({ status: "not_evaluated", class_retention: null });
    // A component the protocol gives no value for: no FPPS, class E by low confidence, no would-be class.
    expect(row("obs-t3-c5-component-not-computed")).toMatchObject({ fpps_0_100: null, action_class: "E", would_be_class: null, leave_one_component_out: null });
    // Tier T4 is locked: the row carries nothing.
    expect(row("t4-locked")).toMatchObject({ tier: "T4", lane: null, fpps_0_100: null, confidence: null, action_class: null });
    // Scenario confidence is never observed confidence, and an engine row declares its own.
    for (const item of overlay.rows) {
      if (item.tier === "T1") expect(item.confidence?.confidence_kind, item.row_id).toBe("scenario");
      if (item.tier === "T0") expect(item.confidence?.confidence_kind, item.row_id).toBe("declared");
    }
  });

  it("states one flood input, one acquisition date and one closure basis per row", () => {
    const byId = new Map(overlay.inputs.map((item) => [item.input_id, item]));
    for (const row of overlay.rows) {
      if (row.confidence === null || row.confidence.confidence_kind === "declared") continue;
      const flood = byId.get(row.lineage.flood_input_id!)!;
      expect(row.confidence.measurements.acquisition_date, row.row_id).toBe(flood.acquisition_date);
      expect(row.lineage.closure_rule?.closure_basis, row.row_id).toBe(`modelled_from_${flood.input_id}`);
      expect(row.temporal_relation, row.row_id).toBe(expectedTemporalRelation(row.confidence.measurements));
      expect(row.confidence.basis, row.row_id).toEqual(expectedConfidenceBasis(row.confidence));
    }
    for (const item of overlay.inputs) {
      if (item.role !== "flood_input") expect(item.acquisition_date, item.input_id).toBeNull();
      expect(item.source_product, item.input_id).toBe("fixture_invented_input");
    }
  });
});

describe("Planning assessment overlay: the protocols in force", () => {
  const v1a = JSON.parse(protocolBytes.v1a.toString("utf8")) as Json & Record<string, Json>;

  it("holds the SHA-256 of the two signed protocol files", () => {
    expect(binding.protocol_sha256).toEqual({ v1a: sha256(protocolBytes.v1a), v1b: sha256(protocolBytes.v1b) });
    expect(binding.scoring_frame.protocol_sha256).toEqual(binding.protocol_sha256);
  });

  it("uses class rule v1 exactly as protocol v1a writes it", () => {
    const classRules = v1a.class_rules as Record<string, Json>;
    expect(binding.class_rule_v1.rules).toEqual(classRules.v1.rules);
    expect(binding.class_rule_v1.version).toBe(classRules.v1.version);
    const v2 = classRules.v2 as { evaluation: { order: string[]; otherwise: string }; parameters: Record<string, number>; version: string };
    expect(binding.class_rule_v2).toEqual({ version: v2.version, order: v2.evaluation.order, otherwise: v2.evaluation.otherwise, fpps_min: v2.parameters.fpps_min, exposure_floor_for_non_e: v2.parameters.exposure_floor_for_non_e });
    expect([...V2_TRIGGER_ORDER]).toEqual(v2.evaluation.order);
  });

  it("gives the class the v1a thresholds give, at each boundary", () => {
    const row = (exposure: number, access: number, road: number): Record<ScoreComponent, number> => ({ flood_likelihood_0_100: 100, exposure_0_100: exposure, access_gap_0_100: access, road_criticality_0_100: road, vulnerability_context_0_100: 50 });
    expect(classByRuleV1(row(70, 70, 0), 60, "medium")).toBe("A");
    expect(classByRuleV1(row(69.99, 70, 0), 60, "medium")).toBe("C");
    expect(classByRuleV1(row(69.99, 70, 75), 60, "medium")).toBe("B");
    expect(classByRuleV1(row(0, 55, 75), 60, "medium")).toBe("B");
    expect(classByRuleV1(row(0, 54.99, 75), 60, "medium")).toBe("D");
    expect(classByRuleV1(row(65, 50, 0), 60, "medium")).toBe("C");
    expect(classByRuleV1(row(64.99, 50, 0), 60, "medium")).toBe("D");
    expect(classByRuleV1(row(65, 49.99, 0), 60, "medium")).toBe("D");
    // FPPS below 35 and low confidence both give E, before any other rule.
    expect(classByRuleV1(row(100, 100, 100), 34.99, "medium")).toBe("E");
    expect(classByRuleV1(row(100, 100, 100), 35, "medium")).toBe("A");
    expect(classByRuleV1(row(100, 100, 100), 90, "low")).toBe("E");
  });

  it("uses the thresholds, the weights and the cases of protocol v1a", () => {
    const frame = v1a.scoring_frame as { weights: Record<string, number>; lane_disclosure: string; components: Record<string, Json> };
    expect(binding.scoring_frame.weights).toEqual(frame.weights);
    expect(binding.scoring_frame.lane_disclosure).toBe(frame.lane_disclosure);
    expect(binding.scoring_frame.flood_anchor).toBe(frame.components.flood_likelihood_0_100.anchor);
    expect(binding.scoring_frame.flood_anchor_disclosure).toBe(frame.components.flood_likelihood_0_100.anchor_disclosure);
    const conditions = Object.fromEntries(((v1a.confidence_rule_v1 as Json).medium_requires_all as { id: string; threshold?: Record<string, number> }[]).map((item) => [item.id, item.threshold ?? {}]));
    const thresholds = binding.confidence_rule.thresholds;
    expect(thresholds.recency_window_days).toBe(conditions.C2_recency.recency_window_days);
    expect(thresholds.unit_valid_coverage_min).toBe(conditions.C3_coverage.unit_valid_coverage_min);
    expect(thresholds.exposure_plus_minus_one_pixel_max_points).toBe(conditions.C4_input_uncertainty.exposure_plus_minus_one_pixel_max_points);
    expect(thresholds.t2_abstention_fraction_max).toBe(conditions.C4_input_uncertainty.t2_abstention_fraction_max);
    expect(thresholds.unit_residents_min).toBe(conditions.C6_residents.unit_residents_min);
    expect(thresholds.baseline_vehicle_no_route_share_max).toBe(conditions.C7_baseline_no_route.baseline_vehicle_no_route_share_max);
    expect(thresholds.hospitals_reachable_at_baseline_min).toBe(conditions.C8_hospital.hospitals_reachable_at_baseline_min);
    const guardrails = Object.fromEntries((v1a.guardrails as unknown as { id: string; parameters?: Record<string, number> }[]).map((item) => [item.id, item.parameters ?? {}]));
    expect(binding.confidence_rule.gr1_unit_residents_min_for_class).toBe(guardrails.GR1_minimum_denominators.unit_residents_min_for_class);
    expect(binding.headline.class_retention_min).toBe(guardrails.GR8_headline_stability.class_retention_min);
    const skill = v1a.t2_skill_bar as { conditions: Record<string, number>; declared_unable_to_meet: string[]; evaluated_by_the_rule: string[] };
    expect(binding.confidence_rule.t2_skill).toEqual({ thresholds: skill.conditions, declared_unable_to_meet: skill.declared_unable_to_meet, evaluated_by_the_rule: skill.evaluated_by_the_rule });
    const portfolio = v1a.case_portfolio as { cases: Json[]; cut_now: string[]; mae_sai_reporting_frame: { units: string[] } };
    expect(binding.cases).toEqual(portfolio.cases.map((item) => ({ id: item.id, case_reference_date: item.case_reference_date, lane: item.lane, tier: item.tier, flood_inputs: item.flood_inputs })));
    expect(binding.cut_cases).toEqual(portfolio.cut_now);
    expect(binding.confidence_rule.coverage_by_construction.units).toEqual(portfolio.mae_sai_reporting_frame.units);
    const product = (v1a.date_rule as Json).product_4009 as Record<string, { layer: string; case_reference_date?: string }>;
    expect(binding.product_4009.layer_names).toEqual([product.accumulated_layer.layer, product.layer_22_oct.layer]);
    expect(binding.product_4009.dated_acquisition_date).toBe(product.layer_22_oct.case_reference_date);
    expect(binding.product_4009.credit).toBe((v1a.wording as Json).product_4009_credit);
    for (const id of binding.cases_without_class) expect(String(portfolio.cases.find((item) => item.id === id)?.note)).toContain("no FPPS and no class");
  });

  it("refuses an overlay written under other protocol bytes, even when it is consistent with itself", () => {
    // Both hashes replaced everywhere, so every record still agrees with the header of its own overlay.
    const replaced = JSON.parse(fixtureText.split(binding.protocol_sha256.v1a).join("0".repeat(64)).split(binding.protocol_sha256.v1b).join("1".repeat(64))) as Json;
    const found = codes(replaced);
    expect(found).toContain("protocol_not_in_force");
    expect(found).not.toContain("protocol_hash_mismatch");
    expect(() => parsePlanningAssessmentOverlay(replaced)).toThrow(PlanningOverlayError);
  });

  it("refuses weights other than the signed ones, whatever the rows say", () => {
    const changed = readFixture() as unknown as PlanningAssessmentOverlay;
    for (const name of SCORE_COMPONENTS) changed.scoring_frame.weights[name] = 0.2;
    expect(codes(changed)).toEqual(expect.arrayContaining(["structure", "frame_not_protocol_frame"]));
  });
});

describe("Planning assessment overlay: a candidate overlay of a portfolio case", () => {
  it("is accepted when it is the case protocol v1a describes", () => {
    const candidate = relabelledAsCaseO2();
    expect(candidate.rows.length).toBeGreaterThan(8);
    expect(planningOverlayProblems(candidate)).toEqual([]);
    expect(caseFloodInputNames(binding.cases.find((item) => item.id === "O2")!)).toEqual(expect.arrayContaining(["CHIANGRAI_20241022_FloodExtent", candidate.rows[0].flood_input]));
  });

  it("is refused with another reference date, a case the protocol cut, or a case the schema cannot carry", () => {
    const moved = relabelledAsCaseO2();
    moved.case.case_reference_date = "2030-01-10";
    expect(codes(moved)).toContain("case_not_protocol_case");
    for (const caseId of ["Phayao", "NOT-A-CASE", "SE2-dist"]) {
      const renamed = relabelledAsCaseO2();
      renamed.case.case_id = caseId;
      expect(codes(renamed), caseId).toContain("case_not_protocol_case");
    }
  });

  it("is refused when a row has another tier, lane or flood input than the case", () => {
    // Case O1 is the own-candidate case (tier T2, reference 15 Sep): the 22 Oct agency layer is not its input.
    const asO1 = relabelledAsCaseO2();
    asO1.case.case_id = "O1";
    const problems = planningOverlayProblems(asO1);
    expect(problems.map((item) => item.code)).toContain("case_not_protocol_case");
    expect(problems.some((item) => item.path === "$.case.case_reference_date")).toBe(true);
    expect(problems.some((item) => item.path.endsWith(".tier"))).toBe(true);
    expect(problems.some((item) => item.path.endsWith(".flood_input"))).toBe(true);
    // Case SE1 is a season-envelope case: it has no observed row.
    const asSe1 = relabelledAsCaseO2();
    asSe1.case.case_id = "SE1";
    expect(planningOverlayProblems(asSe1).some((item) => item.code === "case_not_protocol_case" && item.path.endsWith(".lane"))).toBe(true);
  });

  it("cannot restate the date of the 22 Oct layer to make it event_aligned for a September case", () => {
    const restated = relabelledAsCaseO2();
    const september = "2024-09-15";
    restated.case.case_reference_date = september;
    const flood = restated.inputs.find((item) => item.source_product === PRODUCT_4009_SOURCE)!;
    flood.acquisition_date = september;
    for (const row of restated.rows) Object.assign((row.confidence as DerivedConfidence).measurements, { acquisition_date: september, case_reference_date: september });
    const problems = planningOverlayProblems(restated);
    expect(problems.some((item) => item.code === "product_4009_layer_not_protocol_layer" && item.path.endsWith(".acquisition_date"))).toBe(true);
    // With the layer's own date, the same rows are dated_other against September and may not carry a class above E.
    const honest = relabelledAsCaseO2();
    for (const row of honest.rows) Object.assign((row.confidence as DerivedConfidence).measurements, { case_reference_date: september, recency_days: 37 });
    honest.case.case_reference_date = september;
    expect(codes(honest)).toEqual(expect.arrayContaining(["temporal_relation_mismatch", "confidence_record_mismatch"]));
  });
});

describe("Planning assessment overlay: refusals shared with the Python validator", () => {
  const cases = refusals.cases;
  const pythonOnly = ["protocol_binding_required", "public_write_not_eligible", "product_4009_rights_not_confirmed"];

  it("covers the four refusals task E11 names, and every case names a known code", () => {
    const named = new Set(cases.filter((item) => item.checked_by.includes("typescript")).map((item) => item.refuses));
    for (const code of ["unknown_tier", "class_above_e_without_medium_confidence", "accepted_value_not_null", "temporal_honesty_gr7"]) expect(named, code).toContain(code);
    for (const item of cases) expect([...PLANNING_OVERLAY_REFUSAL_CODES, ...pythonOnly], item.id).toContain(item.refuses);
    // Every code this parser can give is exercised by at least one shared case.
    expect(PLANNING_OVERLAY_REFUSAL_CODES.filter((code) => !named.has(code))).toEqual([]);
    // Only a case this parser cannot see (it always holds the binding) is left to Python alone.
    expect(cases.filter((item) => !item.checked_by.includes("typescript")).map((item) => item.refuses)).toEqual(["protocol_binding_required"]);
  });

  it.each(cases.filter((item) => item.checked_by.includes("typescript")).map((item) => [item.id, item] as const))("refuses %s", (_id, item) => {
    const overlay = patched(item.patch);
    expect(planningOverlayProblems(overlay).map((problem) => problem.code)).toContain(item.refuses);
    let thrown: unknown;
    try {
      parsePlanningAssessmentOverlay(overlay);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(PlanningOverlayError);
    expect((thrown as PlanningOverlayError).codes).toContain(item.refuses);
    expect((thrown as PlanningOverlayError).message).toContain("Planning overlay refused");
  });

  it("applies class rule v1 itself: a class, a would-be class and a leave-one-out class the rule does not give", () => {
    for (const [id, code] of [["class-not-given-by-rule-v1", "class_rule_mismatch"], ["would-be-class-not-the-scorer-rerun", "would_be_class_mismatch"]] as const) {
      const item = cases.find((candidate) => candidate.id === id)!;
      expect(item.checked_by).toEqual(["python", "typescript"]);
      expect(codes(patched(item.patch))).toEqual([code]);
    }
    const changed = readFixture() as unknown as PlanningAssessmentOverlay;
    const row = changed.rows.find((item) => item.row_id === "FX-CASE-01:obs-t3-class-a")!;
    row.leave_one_component_out!.road_criticality_0_100.action_class = "D";
    expect(codes(changed)).toEqual(["leave_one_component_out_mismatch"]);
  });

  it("refuses a 60-resident unit restated as 600 in its confidence record only (guardrail GR1)", () => {
    const item = cases.find((candidate) => candidate.id === "gr1-bypassed-by-a-second-resident-count")!;
    const overlay = patched(item.patch) as unknown as PlanningAssessmentOverlay;
    const row = overlay.rows.find((candidate) => candidate.row_id === "FX-CASE-01:obs-t3-c6-gr1-no-class")!;
    // The row states a binding class for a unit its own exposure record counts at 60 residents.
    expect(row.action_class).toBe("D");
    expect(row.components.exposure_0_100).toMatchObject({ inputs: { unit_residents: 60 } });
    expect((row.confidence as DerivedConfidence).measurements.unit_residents).toBe(600);
    const problems = planningOverlayProblems(overlay);
    expect(problems.map((problem) => [problem.code, problem.path])).toEqual([["confidence_record_mismatch", "$.rows[10].confidence.measurements.unit_residents"]]);
  });

  it("names product 4009 under every name the protocol and the rights record use", () => {
    for (const name of ["CHIANGRAI_20240801_20241012_AccumulatedFlood", "CHIANGRAI_20241022_FloodExtent", "FL20240912THA", "the 4009 22 Oct layer", "UNOSAT/GISTDA product 4009, accumulated layer", "unosat4009/envelope"]) {
      const overlay = patched([{ input: "fx_local_only_layer", path: ["name"], set: name }]);
      expect(codes(overlay), name).toEqual(["source_product_not_declared"]);
    }
    for (const name of ["EPSG 32647 grid, 14009 cells", "Fixture layer 40090"]) {
      expect(codes(patched([{ input: "fx_local_only_layer", path: ["name"], set: name }])), name).toEqual([]);
    }
  });

  it("refuses without throwing when a field a rule reads is missing or null", () => {
    for (const step of [
      { row: "FX-CASE-01:obs-t3-class-a", path: ["confidence"], set: null },
      { row: "FX-CASE-01:obs-t3-class-a", path: ["components"], set: null },
      { row: "FX-CASE-01:obs-t3-class-a", path: ["lineage"], set: null },
      { row: "FX-CASE-01:obs-t3-class-a", path: ["confidence", "measurements"], set: null },
      { path: ["scoring_frame"], set: null },
      { path: ["case"], set: null },
      { path: ["inputs"], set: null },
      { path: ["rows"], set: [null] },
    ] as PatchStep[]) {
      const overlay = patched([step]);
      expect(codes(overlay), JSON.stringify(step.path)).toContain("structure");
      expect(() => parsePlanningAssessmentOverlay(overlay)).toThrow(PlanningOverlayError);
    }
  });

  it("refuses values that are not an overlay at all", () => {
    for (const value of [null, [], "overlay", 3, {}]) {
      expect(planningOverlayProblems(value).map((problem) => problem.code)).toContain("structure");
      expect(() => parsePlanningAssessmentOverlay(value)).toThrow(PlanningOverlayError);
    }
  });
});

describe("Planning assessment overlay: the TypeScript shape against the JSON schema", () => {
  type Schema = typeof schema;
  const resolved = (node: unknown, root: Schema): Json => {
    const item = node as Json;
    return typeof item.$ref === "string" ? root.$defs[item.$ref.replace("#/$defs/", "")] : item;
  };
  const same = (left: unknown, right: unknown) => JSON.stringify(left) === JSON.stringify(right);

  /** Walk the TypeScript shape and the JSON schema together and list every place where they differ. */
  function differences(spec: OverlaySpec, raw: unknown, path: string, out: string[], root: Schema = schema): void {
    const node = resolved(raw, root);
    const differ = (what: string) => out.push(`${path}: ${what}`);
    switch (spec.k) {
      case "text":
        if (!(node.type === "string" && node.minLength === 1 && node.pattern === undefined)) differ("not non-empty text");
        return;
      case "string":
        if (!(node.type === "string" && node.minLength === undefined && node.pattern === undefined)) differ("not plain text");
        return;
      case "pattern":
        if (!(node.type === "string" && node.pattern === spec.source && node.format === undefined)) differ(`pattern ${String(node.pattern)}`);
        return;
      case "date":
        if (!(node.type === "string" && node.pattern === ISO_DATE_PATTERN && node.format === "date")) differ("not a calendar date");
        return;
      case "number":
        if (node.type !== (spec.integer ? "integer" : "number") || node.minimum !== spec.min || node.maximum !== spec.max || node.exclusiveMaximum !== spec.exclusiveMax) differ("number limits");
        return;
      case "boolean":
      case "null":
        if (node.type !== spec.k) differ(`type ${String(node.type)}`);
        return;
      case "const":
        if (node.const !== spec.value) differ(`const ${String(node.const)}`);
        return;
      case "enum":
        if (!same(node.enum, spec.values)) differ(`enum ${JSON.stringify(node.enum)}`);
        return;
      case "array":
        if (node.type !== "array" || node.minItems !== spec.minItems || node.maxItems !== spec.maxItems || node.uniqueItems !== (spec.unique ? true : undefined)) differ("list limits");
        differences(spec.items, node.items, `${path}[]`, out, root);
        return;
      case "object": {
        if (spec.name && (raw as Json).$ref !== `#/$defs/${spec.name}`) differ(`is not $defs/${spec.name}`);
        const properties = (node.properties ?? {}) as Json;
        const keys = Object.keys(spec.fields);
        if (node.type !== "object" || node.additionalProperties !== false || !same(Object.keys(properties).sort(), [...keys].sort()) || !same([...(node.required as string[])].sort(), [...keys].sort())) {
          differ("object keys");
          return;
        }
        for (const key of keys) differences(spec.fields[key], properties[key], `${path}.${key}`, out, root);
        return;
      }
      case "map":
        if (node.type !== "object" || node.minProperties !== spec.minProperties || (node.propertyNames as Json | undefined)?.pattern !== spec.keyPattern) differ("map limits");
        differences(spec.values, node.additionalProperties, `${path}.*`, out, root);
        return;
      case "oneOf": {
        const options = (node.oneOf ?? []) as unknown[];
        if (options.length !== spec.options.length) return void differ("oneOf length");
        spec.options.forEach((option, index) => differences(option, options[index], `${path}|${index}`, out, root));
        return;
      }
    }
  }

  it("is the same shape, field for field", () => {
    expect(schema.$id).toBe(PLANNING_OVERLAY_SCHEMA_ID);
    const found: string[] = [];
    differences(PLANNING_OVERLAY_SHAPE, schema, "$", found);
    expect(found).toEqual([]);
  });

  it("would notice a schema that changed: a field removed, a vocabulary widened, a limit or a signed number moved", () => {
    const changed = JSON.parse(JSON.stringify(schema)) as Schema;
    delete (changed.$defs.row.properties as Json).would_be_class;
    (changed.$defs.tier.enum as string[]).push("T5");
    (changed.$defs.share as Json).maximum = 100;
    (changed.$defs.exposureRecord.properties as Json).exposed_headcount = { type: "number" };
    ((changed.$defs.guardrailGr1.properties as Json).unit_residents_min_for_class as Json).const = 50;
    ((changed.$defs.weights.properties as Json).exposure_0_100 as Json).const = 0.3;
    delete (changed.$defs.isoDate as Json).format;
    const found: string[] = [];
    differences(PLANNING_OVERLAY_SHAPE, changed, "$", found, changed);
    expect(found).toContain("$.rows[]: object keys");
    expect(found).toContain("$.scoring_frame.weights.exposure_0_100: const 0.3");
    expect(found).toContain("$.case.case_reference_date|0: not a calendar date");
    expect(found.some((item) => item.endsWith(".flood_anchor_sensitivity_one_at_a_time[]: number limits"))).toBe(true);
    expect(found.length).toBeGreaterThan(5);
  });

  it("pins the signed numbers in the schema as constants", () => {
    const defs = schema.$defs;
    const constantsOf = (node: Json) => Object.fromEntries(Object.entries(node.properties as Record<string, Json>).map(([name, value]) => [name, value.const]));
    expect(constantsOf(defs.weights)).toEqual(binding.scoring_frame.weights);
    const frame = defs.scoringFrame.properties as Record<string, Json>;
    expect(frame.flood_anchor.const).toBe(binding.scoring_frame.flood_anchor);
    expect(frame.lane_disclosure.const).toBe(binding.scoring_frame.lane_disclosure);
    for (const name of SCORE_COMPONENTS) {
      expect(constantsOf((frame.leave_one_component_out_weights.properties as Record<string, Json>)[name]), name).toEqual(binding.scoring_frame.leave_one_component_out_weights[name]);
    }
    expect(constantsOf((defs.derivedConfidence.properties as Record<string, Json>).thresholds)).toEqual(binding.confidence_rule.thresholds);
    expect(constantsOf((defs.t2SkillCondition.properties as Record<string, Json>).thresholds)).toEqual(binding.confidence_rule.t2_skill.thresholds);
    expect(((defs.guardrailGr1.properties as Json).unit_residents_min_for_class as Json).const).toBe(binding.confidence_rule.gr1_unit_residents_min_for_class);
    expect(((defs.headlineStability.properties as Json).class_retention_min as Json).const).toBe(binding.headline.class_retention_min);
  });

  it("uses the vocabularies of the schema", () => {
    const defs = schema.$defs;
    expect(defs.tier.enum).toEqual([...EVIDENCE_TIERS]);
    expect(defs.lane.enum).toEqual([...PLANNING_LANES]);
    expect(defs.temporalRelation.enum).toEqual([...TEMPORAL_RELATIONS]);
    expect(defs.actionClass.enum).toEqual([...PLANNING_ACTION_CLASSES]);
    expect(defs.actionReasonCode.enum).toEqual([...PLANNING_REASON_CODES]);
    expect(defs.assignedConfidenceClass.enum).toEqual([...ASSIGNED_CONFIDENCE_CLASSES]);
    expect(defs.basisValue.enum).toEqual([...CONFIDENCE_BASIS_VALUES]);
    expect(defs.conditionId.enum).toEqual([...CONFIDENCE_CONDITION_IDS]);
    expect(defs.componentName.enum).toEqual([...SCORE_COMPONENTS]);
    expect(defs.publicationLevel.enum).toEqual([...PUBLICATION_LEVELS]);
    expect(((defs.headlineStability.properties as Json).status as Json).enum).toEqual([...HEADLINE_STATUSES]);
    expect(((defs.input.properties as Json).role as Json).enum).toEqual([...INPUT_ROLES]);
  });

  it("notices a field the schema does not have", () => {
    const withExtra = readFixture() as unknown as PlanningAssessmentOverlay & Json;
    (withExtra.rows[0] as unknown as Json).priority_rank = 1;
    expect(planningOverlayProblems(withExtra)).toEqual([{ code: "structure", path: "$.rows[0].priority_rank", message: "is not a field of the overlay schema" }]);
  });
});

describe("Planning assessment overlay: a bundler prints the signed numbers again", () => {
  // A production bundle shipped the frame weight 0.39999999999999997 (0.30 / 0.75) as `.4`, one unit in the last
  // place away, and the parser, which compared with ===, refused every real overlay in the browser. The tests read
  // the JSON module itself, so they passed. These cases state the weight both ways and expect the same answer.
  const path = ["scoring_frame", "leave_one_component_out_weights", "exposure_0_100", "flood_likelihood_0_100"];

  it("holds the weight in the form Python wrote, and it is not the float 0.4", () => {
    const written = (readFixture() as unknown as PlanningAssessmentOverlay).scoring_frame.leave_one_component_out_weights.exposure_0_100.flood_likelihood_0_100;
    expect(written).toBe(0.39999999999999997);
    expect(written).not.toBe(0.4);
  });

  it("accepts an overlay whose weight is one unit in the last place from the signed constant", () => {
    const overlay = patched([{ path, set: 0.4 }]);
    expect(planningOverlayProblems(overlay)).toEqual([]);
    expect(parsePlanningAssessmentOverlay(overlay).rows.length).toBeGreaterThan(0);
  });

  it("still refuses a weight that is another signed value, or any value a reader could tell apart", () => {
    for (const other of [0.4000001, 0.39, 0.3]) {
      const codes = planningOverlayProblems(patched([{ path, set: other }])).map((problem) => problem.code);
      expect(codes, String(other)).toContain("structure");
      expect(codes, String(other)).toContain("frame_not_protocol_frame");
    }
  });
});
