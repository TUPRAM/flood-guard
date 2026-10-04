/**
 * The planning assessment overlay parser against the committed fixture (plan task E11).
 *
 * The fixture is written by Python (`apps/web/scripts/planning-overlay-fixture.py`) after the JSON schema and the
 * strict Python validator accept it; pytest checks that the committed file is what Python writes today
 * (`tests/test_planning_overlay.py`). Here the TypeScript parser reads the same bytes and must find the same
 * content: the same file hash, the same content digest and the same counts as the summary Python wrote. The refusal
 * cases are shared with pytest, so both parsers refuse the same things for the same reason. The fixture is an
 * invented case with invented units: a fixture, not a place.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ASSIGNED_CONFIDENCE_CLASSES,
  CONFIDENCE_BASIS_VALUES,
  CONFIDENCE_CONDITION_IDS,
  EVIDENCE_TIERS,
  HEADLINE_STATUSES,
  INPUT_ROLES,
  NO_V2_TRIGGER,
  parsePlanningAssessmentOverlay,
  PLANNING_ACTION_CLASSES,
  PLANNING_LANES,
  PLANNING_OVERLAY_REFUSAL_CODES,
  PLANNING_OVERLAY_SCHEMA_ID,
  PLANNING_OVERLAY_SHAPE,
  PLANNING_REASON_CODES,
  PlanningOverlayError,
  planningOverlayProblems,
  PUBLICATION_LEVELS,
  SCORE_COMPONENTS,
  summarisePlanningAssessmentOverlay,
  TEMPORAL_RELATIONS,
  type OverlaySpec,
  type PlanningAssessmentOverlay,
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

const fixtures = resolve(import.meta.dirname, "__fixtures__");
const fixtureBytes = readFileSync(resolve(fixtures, "planning-assessment-overlay.fixture.json"));
const readFixture = (): Json => JSON.parse(fixtureBytes.toString("utf8")) as Json;
const pythonSummary = JSON.parse(readFileSync(resolve(fixtures, "planning-assessment-overlay.fixture.summary.json"), "utf8")) as {
  fixture: string;
  file_sha256: string;
  summary: Json & { content_sha256: string };
};
const refusals = JSON.parse(readFileSync(resolve(fixtures, "planning-assessment-overlay.refusals.json"), "utf8")) as { cases: RefusalCase[] };
const schema = JSON.parse(
  readFileSync(resolve(import.meta.dirname, "../../../../packages/contracts/schemas/planning-assessment-overlay.schema.json"), "utf8"),
) as Json & { $defs: Record<string, Json> };
const sha256 = (data: string | Buffer) => createHash("sha256").update(data).digest("hex");

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
    expect(fixtureBytes.toString("utf8")).not.toMatch(/TH[0-9]{6}|M1-v2|M1-literal|UN-SPIDER|A6-prime|CHIANGRAI_/);
  });

  it("exercises every tier, lane, reason code, failed condition, would-be class and v2 outcome", () => {
    const summary = summarisePlanningAssessmentOverlay(overlay);
    const everyKeyUsed = (counts: Record<string, number>, keys: readonly string[]) => keys.filter((key) => !counts[key]);
    expect(everyKeyUsed(summary.rows_by_tier, EVIDENCE_TIERS)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_lane, PLANNING_LANES)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_temporal_relation, TEMPORAL_RELATIONS)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_reason_code, PLANNING_REASON_CODES)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_binding_class, PLANNING_ACTION_CLASSES)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_would_be_class, PLANNING_ACTION_CLASSES)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_v2_result, [...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER])).toEqual([]);
    expect(everyKeyUsed(summary.failed_condition_counts, CONFIDENCE_CONDITION_IDS)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_headline_status, HEADLINE_STATUSES)).toEqual([]);
    expect(everyKeyUsed(summary.rows_by_confidence_class, ASSIGNED_CONFIDENCE_CLASSES)).toEqual([]);
    expect(everyKeyUsed(summary.inputs_by_rights_level, PUBLICATION_LEVELS)).toEqual([]);
    expect(overlay.publication_eligibility).toBe("local");
    // Condition C3 by construction is granted to product 4009 in the eight Mae Sai tambons only: not in a fixture.
    expect(summary.basis_value_counts).toMatchObject({ by_construction: 0 });
    expect(summary.basis_value_counts.by_scenario_declaration).toBeGreaterThan(0);
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

  it("accepts the same rows as a candidate overlay of a portfolio case", () => {
    const candidate = readFixture();
    candidate.dataset_mode = "candidate";
    Object.assign(candidate.case as Json, { kind: "portfolio_case", fixture_notice: null });
    expect(planningOverlayProblems(candidate)).toEqual([]);
  });
});

describe("Planning assessment overlay: refusals shared with the Python validator", () => {
  const cases = refusals.cases;

  it("covers the four refusals task E11 names, and every case names a known code", () => {
    const named = new Set(cases.filter((item) => item.checked_by.includes("typescript")).map((item) => item.refuses));
    for (const code of ["unknown_tier", "class_above_e_without_medium_confidence", "accepted_value_not_null", "temporal_honesty_gr7"]) expect(named, code).toContain(code);
    const pythonOnly = ["class_rule_mismatch", "protocol_not_in_force", "frame_not_protocol_frame", "component_not_frame_record", "confidence_not_rule_record"];
    for (const item of cases) expect([...PLANNING_OVERLAY_REFUSAL_CODES, ...pythonOnly], item.id).toContain(item.refuses);
    // Every code this parser can give is exercised by at least one shared case.
    expect(PLANNING_OVERLAY_REFUSAL_CODES.filter((code) => !named.has(code))).toEqual([]);
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

  it("leaves the class rule itself to the Python validator, which reruns the scorer", () => {
    // Stated so that the limit is visible: a class that breaks none of the invariants is not recomputed here.
    for (const id of ["class-not-given-by-rule-v1", "would-be-class-not-the-scorer-rerun"]) {
      const item = cases.find((candidate) => candidate.id === id)!;
      expect(item.checked_by).toEqual(["python"]);
      expect(planningOverlayProblems(patched(item.patch))).toEqual([]);
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
        if (!(node.type === "string" && node.pattern === spec.source)) differ(`pattern ${String(node.pattern)}`);
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

  it("would notice a schema that changed: a field removed, a vocabulary widened, a limit moved", () => {
    const changed = JSON.parse(JSON.stringify(schema)) as Schema;
    delete (changed.$defs.row.properties as Json).would_be_class;
    (changed.$defs.tier.enum as string[]).push("T5");
    (changed.$defs.share as Json).maximum = 100;
    (changed.$defs.exposureRecord.properties as Json).exposed_headcount = { type: "number" };
    const found: string[] = [];
    differences(PLANNING_OVERLAY_SHAPE, changed, "$", found, changed);
    expect(found).toContain("$.rows[]: object keys");
    expect(found.some((item) => item.endsWith(".flood_anchor: number limits"))).toBe(true);
    expect(found.length).toBeGreaterThan(3);
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
