/**
 * Planning assessment overlay: the typed shape and the strict parser of the file the planning engine writes for one
 * case and every screen reads (restructuring plan v2, section 7.1, task E11). The JSON schema is
 * `packages/contracts/schemas/planning-assessment-overlay.schema.json`; the Python side is
 * `src/floodguard/planning_overlay.py`, and both sides use the same refusal codes.
 *
 * One row is one unit in one lane with one flood input and one scenario. The component and confidence records are
 * the ones `normalisation.py` and `confidence.py` return under the signed planning protocols v1a and v1b. The parser
 * holds the constants of those two files (`planning-protocol-binding.json`, written by Python from the files in
 * force) and refuses what the protocols forbid:
 *
 * - an unknown tier, a class above E without medium confidence, a non-null `accepted_fpps` or
 *   `accepted_action_class`, a value on the locked tier T4, a v2 class shown as binding;
 * - an OBS row that is not event_aligned with a binding class above E (guardrail GR7), where the temporal relation
 *   is the one the two echoed dates give;
 * - a class for a unit with fewer than 100 residents (guardrail GR1), judged on the residents the row is scored on;
 * - a confidence record that is not what rule v1 derives from the measurements it echoes, and a component record
 *   that is not the frame v1 record of the inputs it echoes (guardrail GR2);
 * - an FPPS that is not the weighted sum, and a binding, would-be or leave-one-out class that class rule v1 does
 *   not give;
 * - protocol hashes or a frame header that are not those of the files in force, and a portfolio case that is not
 *   the case protocol v1a describes;
 * - a rights level above the minimum of the lineage (guardrail GR6), and a product 4009 input without its licence.
 *
 * The parser does not check the assumptions text of a confidence record; the Python validator does.
 *
 * An overlay is planning guidance for preparedness and post-event prioritisation. It is not an official warning, and
 * class E never means safe.
 */

import protocolBinding from "./planning-protocol-binding.json";

export const PLANNING_OVERLAY_SCHEMA_ID = "https://floodguard.th/contracts/planning-assessment-overlay.schema.json" as const;
export const PLANNING_OVERLAY_SCHEMA_VERSION = "1.1" as const;

export const EVIDENCE_TIERS = ["T0", "T1", "T2", "T3", "T4"] as const;
export type EvidenceTier = (typeof EVIDENCE_TIERS)[number];
/** Tier T4 (qualified) is locked in this release: a T4 row is a placeholder and carries no value. */
export const LOCKED_TIER = "T4" as const satisfies EvidenceTier;

export const PLANNING_LANES = ["OBS", "SCN", "SCN-ENV", "ENG"] as const;
export type PlanningLane = (typeof PLANNING_LANES)[number];

/**
 * The columns a count is reported in (protocol v1a class_coverage_deliverable: OBS / SCN / ENG). Lane SCN-ENV is
 * part of the SCN column, and `no_lane` holds the rows of the locked tier T4. Scenario and engine classes are never
 * merged with observed ones.
 */
export const LANE_COLUMNS = ["OBS", "SCN", "ENG", "no_lane"] as const;
export type LaneColumn = (typeof LANE_COLUMNS)[number];

export const TEMPORAL_RELATIONS = ["event_aligned", "dated_other", "season_window"] as const;
export type TemporalRelation = (typeof TEMPORAL_RELATIONS)[number];

export const PLANNING_ACTION_CLASSES = ["A", "B", "C", "D", "E"] as const;
export type PlanningActionClass = (typeof PLANNING_ACTION_CLASSES)[number];

/** The six reason codes of class rule v1 and the one code the planning overlay adds (guardrail GR1). */
export const PLANNING_REASON_CODES = [
  "low_confidence",
  "low_priority_score",
  "life_safety_exposure",
  "critical_route_access",
  "essential_service_access",
  "resilience",
  "insufficient_denominator",
] as const;
export type PlanningReasonCode = (typeof PLANNING_REASON_CODES)[number];

/** `high` requires tier T4, which is locked, so it is never assigned. */
export const ASSIGNED_CONFIDENCE_CLASSES = ["low", "medium"] as const;
export type AssignedConfidenceClass = (typeof ASSIGNED_CONFIDENCE_CLASSES)[number];

export const CONFIDENCE_KINDS = ["observed", "scenario", "declared"] as const;
export type ConfidenceKind = (typeof CONFIDENCE_KINDS)[number];

export const CONFIDENCE_BASIS_VALUES = ["pass", "fail", "by_construction", "by_scenario_declaration"] as const;
export type ConfidenceBasisValue = (typeof CONFIDENCE_BASIS_VALUES)[number];

export const CONFIDENCE_CONDITION_IDS = [
  "C1_tier",
  "C2_recency",
  "C3_coverage",
  "C4_input_uncertainty",
  "C5_components",
  "C6_residents",
  "C7_baseline_no_route",
  "C8_hospital",
] as const;
export type ConfidenceConditionId = (typeof CONFIDENCE_CONDITION_IDS)[number];

export const SCORE_COMPONENTS = [
  "flood_likelihood_0_100",
  "exposure_0_100",
  "access_gap_0_100",
  "road_criticality_0_100",
  "vulnerability_context_0_100",
] as const;
export type ScoreComponent = (typeof SCORE_COMPONENTS)[number];

/** Guardrail GR6, lowest first: the rights level of an overlay is the minimum across its lineage. */
export const PUBLICATION_LEVELS = ["local", "pitch", "public"] as const;
export type PublicationLevel = (typeof PUBLICATION_LEVELS)[number];

/** Class rule v2 is evaluated in this order; the first trigger met gives the v2 class (protocol v1a, DR-A08). */
export const V2_TRIGGER_ORDER = ["E", "A", "B", "C", "D"] as const;
export const NO_V2_TRIGGER = "no_v2_trigger" as const;
/** The v2 result of a row whose result depends on a trigger no stage evaluated (schema 1.1, decision R20). */
export const V2_NOT_EVALUATED = "not_evaluated" as const;
export type ClassV2Result = PlanningActionClass | typeof NO_V2_TRIGGER | typeof V2_NOT_EVALUATED;

export const HEADLINE_STATUSES = ["not_evaluated", "headline_eligible", "unstable_verify"] as const;
export type HeadlineStatus = (typeof HEADLINE_STATUSES)[number];

export const INPUT_ROLES = [
  "flood_input",
  "routing_context",
  "population",
  "age_structure",
  "boundaries",
  "facilities",
  "permanent_water",
  "other",
] as const;
export type InputRole = (typeof INPUT_ROLES)[number];

/** Every reason the parser gives for a refusal. `src/floodguard/planning_overlay.py` uses the same strings. */
export const PLANNING_OVERLAY_REFUSAL_CODES = [
  "structure",
  "unknown_tier",
  "accepted_value_not_null",
  "official_warning_not_false",
  "operational_status_not_non_operational",
  "class_above_e_without_medium_confidence",
  "temporal_honesty_gr7",
  "high_confidence_not_assigned",
  "tier_lane_mismatch",
  "t4_locked_row_carries_values",
  "confidence_record_mismatch",
  "temporal_relation_mismatch",
  "assumed_component_in_a_row",
  "component_mismatch",
  "fpps_mismatch",
  "gr1_no_class",
  "low_confidence_forces_e",
  "class_rule_mismatch",
  "reason_code_mismatch",
  "would_be_class_mismatch",
  "v2_result_inconsistent",
  "leave_one_component_out_mismatch",
  "headline_stability_inconsistent",
  "lineage_unresolved",
  "publication_eligibility_not_lineage_minimum",
  "product_4009_licence_missing",
  "source_product_not_declared",
  "protocol_hash_mismatch",
  "scoring_frame_inconsistent",
  "duplicate_id",
  "fixture_label_missing",
  "protocol_not_in_force",
  "frame_not_protocol_frame",
  "component_not_frame_record",
  "confidence_not_rule_record",
  "case_not_protocol_case",
  "product_4009_layer_not_protocol_layer",
] as const;
export type PlanningOverlayRefusalCode = (typeof PLANNING_OVERLAY_REFUSAL_CODES)[number];

// --- Types ------------------------------------------------------------------------------------------------------

export interface ProtocolSha256 {
  v1a: string;
  v1b: string;
}

export type ComponentWeights = Record<ScoreComponent, number>;

export interface AccessService {
  service: string;
  mode: string;
  threshold_minutes: number;
  level: "public" | "pitch";
}

export interface PermanentWater {
  source: string;
  class: number;
}

/** The frame header as `floodguard.normalisation.frame_record` returns it. */
export interface PlanningFrameHeader {
  normalisation_version: "planning_frame_v1";
  normalisation_rule: string;
  weights: ComponentWeights;
  flood_anchor: number;
  flood_anchor_sensitivity_one_at_a_time: number[];
  flood_anchor_disclosure: string;
  permanent_water: PermanentWater;
  exposure_kind: "share_only";
  access_services: AccessService[];
  vulnerability_anchor_version: "national_vulnerability_anchors_v1";
  vulnerability_anchors: { lower: string; upper: string; values: Record<string, number> };
  vulnerability_anchor_sensitivity: { lower: string; upper: string };
  vulnerability_anchor_receipt_sha256: string;
  leave_one_component_out_weights: Record<ScoreComponent, ComponentWeights>;
  /** Guardrail GR3: one flood input drives 4 of 5 components (90% of weight). */
  lane_disclosure: string;
  protocol_sha256: ProtocolSha256;
}

interface ComponentRecordHead<Name extends ScoreComponent> {
  component: Name;
  value_0_100: number;
  normalisation_version: "planning_frame_v1";
  protocol_sha256: ProtocolSha256;
  definition: string;
}

export interface FloodLikelihoodRecord extends ComponentRecordHead<"flood_likelihood_0_100"> {
  inputs: { flooded_non_permanent_water_land_area: number; non_permanent_water_land_area: number };
  flooded_share: number;
  anchor: number;
  anchor_sensitivity_one_at_a_time: { anchor: number; value_0_100: number }[];
  anchor_disclosure: string;
  permanent_water: PermanentWater;
}

export interface ExposureRecord extends ComponentRecordHead<"exposure_0_100"> {
  inputs: { residents_inside_flood_extent: number; unit_residents: number };
  exposed_share: number;
  kind: "share_only";
}

export interface AccessGapServiceInputs {
  mode: string;
  threshold_minutes: number;
  baseline_access_residents: number;
  newly_lost_residents: number;
}

export interface AccessGapRecord extends ComponentRecordHead<"access_gap_0_100"> {
  inputs: { services: Record<string, AccessGapServiceInputs> };
  services: (AccessGapServiceInputs & { service: string; newly_lost_share: number | null })[];
  baseline_access_residents_all_services: number;
  publication_level: "public" | "pitch";
}

export interface RoadCriticalityRecord extends ComponentRecordHead<"road_criticality_0_100"> {
  inputs: { residents_losing_all_routes: number; residents_with_baseline_route: number };
  share_losing_all_routes: number;
}

export interface VulnerabilityRecord extends ComponentRecordHead<"vulnerability_context_0_100"> {
  inputs: { children_0_14: number; older_60_plus: number; residents: number };
  dependent_share: number;
  anchors: { lower: string; lower_value: number; upper: string; upper_value: number };
  anchor_sensitivity: { lower: string; lower_value: number; upper: string; upper_value: number; value_0_100: number };
  anchor_version: "national_vulnerability_anchors_v1";
  anchor_receipt_sha256: string;
  caveat: string;
}

export type FrameComponentRecord = FloodLikelihoodRecord | ExposureRecord | AccessGapRecord | RoadCriticalityRecord | VulnerabilityRecord;

/** A synthetic value of an engine row (tier T0): not a place and not a frame v1 record. */
export interface SyntheticComponent {
  component: ScoreComponent;
  value_0_100: number;
  synthetic: true;
}

/** `null` says the protocol states no value for the unit: the component is not computed. */
export interface PlanningComponents {
  flood_likelihood_0_100: FloodLikelihoodRecord | SyntheticComponent | null;
  exposure_0_100: ExposureRecord | SyntheticComponent | null;
  access_gap_0_100: AccessGapRecord | SyntheticComponent | null;
  road_criticality_0_100: RoadCriticalityRecord | SyntheticComponent | null;
  vulnerability_context_0_100: VulnerabilityRecord | SyntheticComponent | null;
}

export const T2_SKILL_CONDITION_IDS = [
  "geoid_held_out_test_iou_min",
  "mae_sai_abstention_fraction_max",
  "mae_sai_unit_coverage_min",
  "recency_window_days",
] as const;
export type T2SkillConditionId = (typeof T2_SKILL_CONDITION_IDS)[number];
export type T2SkillStatus = "declared_unable_to_meet" | "not_evaluated_by_the_rule" | "evaluated";

/** As `floodguard.confidence.t2_skill_condition` returns it. */
export interface T2SkillCondition {
  flood_input: string;
  status: T2SkillStatus;
  passes: boolean;
  conditions: Record<T2SkillConditionId, "pass" | "fail">;
  failed_conditions: T2SkillConditionId[];
  measurements: {
    geoid_held_out_test_iou: number | null;
    abstention_fraction: number | null;
    unit_valid_coverage: number | null;
    recency_days: number | null;
  };
  thresholds: Record<T2SkillConditionId, number>;
  metric_wording: string;
  protocol_v1a_sha256: string;
}

export interface GuardrailGr1 {
  id: "GR1_minimum_denominators";
  applies: boolean;
  unit_residents_min_for_class: number;
  no_binding_class: boolean;
  no_would_be_class: boolean;
  no_v2_class: boolean;
}

export interface ConfidenceThresholds {
  recency_window_days: number;
  unit_valid_coverage_min: number;
  exposure_plus_minus_one_pixel_max_points: number;
  exposure_plus_minus_one_pixel_float_guard_points: number;
  t2_abstention_fraction_max: number;
  unit_residents_min: number;
  baseline_vehicle_no_route_share_max: number;
  hospitals_reachable_at_baseline_min: number;
}

export interface ConfidenceMeasurements {
  recency_days: number | null;
  acquisition_date: string | null;
  case_reference_date: string | null;
  unit_valid_coverage: number | null;
  coverage_by_construction: boolean;
  exposure_plus_one_pixel_0_100: number | null;
  exposure_minus_one_pixel_0_100: number | null;
  exposure_plus_minus_one_pixel_points: number | null;
  t2_abstention_fraction: number | null;
  component_status: Record<ScoreComponent, "computed" | "assumed" | "not_computed">;
  unit_residents: number;
  baseline_vehicle_no_route_share: number | null;
  hospitals_reachable_at_baseline: number | null;
}

/** The confidence record as `floodguard.confidence.derive_confidence` returns it (rule v1, per unit and lane). */
export interface DerivedConfidence {
  unit_id: string;
  lane: "OBS" | "SCN" | "SCN-ENV";
  tier: "T1" | "T2" | "T3";
  flood_input: string;
  scenario_base: "agency_product_as_provided" | "own_t2_candidate" | null;
  confidence_rule_version: "confidence_rule_v1";
  confidence_class: AssignedConfidenceClass;
  /** Scenario confidence is never shown or counted as observed confidence. */
  confidence_kind: "observed" | "scenario";
  basis: Record<ConfidenceConditionId, ConfidenceBasisValue>;
  failed_conditions: ConfidenceConditionId[];
  reason_code: "low_confidence" | "insufficient_denominator" | null;
  guardrail_gr1: GuardrailGr1;
  t2_skill_condition: T2SkillCondition | null;
  measurements: ConfidenceMeasurements;
  thresholds: ConfidenceThresholds;
  uses_ensemble_output: false;
  rights_are_an_input: false;
  protocol_v1a_sha256: string;
  assumptions: string[];
}

/** The confidence of an engine row (tier T0): declared per row, not derived by rule v1. */
export interface DeclaredConfidence {
  confidence_class: AssignedConfidenceClass;
  confidence_kind: "declared";
  declaration: string;
}

export type PlanningConfidence = DerivedConfidence | DeclaredConfidence;

export interface ClosureRule {
  version: "closure_rule_v1";
  level: "strict" | "central" | "permissive";
  /** `modelled_from_<flood input id>`: a flood intersection does not prove a road closure. */
  closure_basis: string;
}

/** Guardrail GR3 (lane purity): the one flood input, the one routing context and the one closure rule of the row. */
export interface RowLineage {
  flood_input_id: string | null;
  routing_context_id: string | null;
  closure_rule: ClosureRule | null;
}

export interface TriggerEvidence {
  trigger: PlanningActionClass;
  /** `null` says that no stage evaluated the trigger. A trigger that was not evaluated is never written `false`. */
  met: boolean | null;
  evidence: string;
}

/** Class rule v2: a predeclared secondary axis, never binding (decision D6). */
export interface ClassV2 {
  class_rule_version: "class_rule_v2";
  label: "secondary";
  binding: false;
  /**
   * `no_v2_trigger` is shown as "no v2 trigger met"; `not_evaluated` says the result depends on a trigger no stage
   * evaluated, so no v2 class is stated; `null` says the unit gets no v2 class (guardrail GR1).
   */
  result: ClassV2Result | null;
  trigger_evidence: TriggerEvidence[];
}

export type LeaveOneComponentOut = Record<ScoreComponent, { fpps_0_100: number; action_class: PlanningActionClass | null }>;

/** Guardrail GR8: headlined only with at least 60 percent class retention; otherwise "unstable: verify". */
export interface HeadlineStability {
  guardrail: "GR8_headline_stability";
  status: HeadlineStatus;
  class_retention: number | null;
  class_retention_min: 0.6;
}

export interface PlanningOverlayRow {
  row_id: string;
  unit_id: string;
  unit_name_en: string;
  unit_name_th: string;
  tier: EvidenceTier;
  lane: PlanningLane | null;
  temporal_relation: TemporalRelation | null;
  flood_input: string | null;
  scenario: { id: string; declaration: string } | null;
  lineage: RowLineage;
  normalisation_version: "planning_frame_v1";
  components: PlanningComponents;
  fpps_0_100: number | null;
  confidence: PlanningConfidence | null;
  /** The binding class (class rule v1). `null` under guardrail GR1 and on the locked tier T4. */
  action_class: PlanningActionClass | null;
  action_reason_code: PlanningReasonCode | null;
  /** The scorer rerun with confidence medium, for low-confidence rows. Never binding. */
  would_be_class: PlanningActionClass | null;
  class_v2: ClassV2 | null;
  leave_one_component_out: LeaveOneComponentOut | null;
  headline_stability: HeadlineStability;
  accepted_fpps: null;
  accepted_action_class: null;
  source_timestamp: string;
  assumptions: string[];
}

export interface PlanningOverlayInput {
  input_id: string;
  role: InputRole;
  name: string;
  /** The source product the input declares; `unosat_product_4009` is UNOSAT/GISTDA product 4009. */
  source_product: string | null;
  /** The single acquisition date of a flood input; `null` for one with no single date and for every other input. */
  acquisition_date: string | null;
  sha256: string;
  rights_level: PublicationLevel;
  licence: string;
  attribution: string;
  change_notice: string | null;
  source_timestamp: string;
}

export interface PlanningOverlayCase {
  case_id: string;
  kind: "fixture" | "portfolio_case";
  title_en: string;
  title_th: string;
  frame: string;
  case_reference_date: string | null;
  fixture_notice: string | null;
}

export interface PlanningAssessmentOverlay {
  schema_version: typeof PLANNING_OVERLAY_SCHEMA_VERSION;
  schema_id: typeof PLANNING_OVERLAY_SCHEMA_ID;
  dataset_mode: "fixture_demo" | "candidate";
  operational_status: "non_operational";
  official_warning: false;
  can_feed_decision_layer: false;
  accepted_fpps: null;
  accepted_action_class: null;
  source_timestamp: string;
  generated_at: string;
  source_name: string;
  data_version: string;
  git_commit: string;
  case: PlanningOverlayCase;
  protocol_sha256: ProtocolSha256;
  evidence_tier_model_version: "evidence_tiers_v1";
  normalisation_version: "planning_frame_v1";
  confidence_rule_version: "confidence_rule_v1";
  class_rule_version: "class_rule_v1";
  secondary_class_rule_version: "class_rule_v2";
  scoring_frame: PlanningFrameHeader;
  publication_eligibility: PublicationLevel;
  inputs: PlanningOverlayInput[];
  assumptions: string[];
  rows: PlanningOverlayRow[];
}

export interface PlanningOverlayProblem {
  code: PlanningOverlayRefusalCode;
  path: string;
  message: string;
}

/** Thrown when an overlay is refused. `problems` lists every reason found. */
export class PlanningOverlayError extends Error {
  readonly problems: readonly PlanningOverlayProblem[];

  constructor(problems: readonly PlanningOverlayProblem[]) {
    const shown = problems.slice(0, 5).map((item) => `${item.code} at ${item.path}: ${item.message}`).join("; ");
    super(`Planning overlay refused: ${shown}${problems.length > 5 ? ` (and ${problems.length - 5} more)` : ""}`);
    this.name = "PlanningOverlayError";
    this.problems = problems;
  }

  get codes(): PlanningOverlayRefusalCode[] {
    return [...new Set(this.problems.map((item) => item.code))];
  }
}

// --- The protocol binding ---------------------------------------------------------------------------------------

/** One rule of class rule v1, as protocol v1a `class_rules.v1.rules` writes it. */
export interface ClassRuleV1 {
  class: PlanningActionClass;
  combine: "any" | "all" | "otherwise";
  conditions: { field: string; operator: string; value: string | number }[];
}

/** One case of protocol v1a `case_portfolio`. */
export interface ProtocolCase {
  id: string;
  case_reference_date: string | null;
  lane: PlanningLane;
  tier: EvidenceTier;
  flood_inputs: string[];
}

/**
 * The constants of the two signed protocol files, as `floodguard.planning_overlay.protocol_binding_record` writes
 * them. Python checks the file against the protocols in force (`tests/test_planning_overlay.py`).
 */
export interface PlanningProtocolBinding {
  about: string;
  protocol_sha256: ProtocolSha256;
  scoring_frame: PlanningFrameHeader;
  component_definitions: Record<ScoreComponent, string>;
  vulnerability_caveat: string;
  confidence_rule: {
    version: "confidence_rule_v1";
    thresholds: ConfidenceThresholds;
    gr1_unit_residents_min_for_class: number;
    t2_skill: { thresholds: Record<T2SkillConditionId, number>; declared_unable_to_meet: string[]; evaluated_by_the_rule: string[] };
    own_t2_candidates_named: string[];
    coverage_by_construction: { units: string[]; flood_inputs: string[] };
  };
  class_rule_v1: { version: "class_rule_v1"; rules: ClassRuleV1[] };
  class_rule_v2: { version: "class_rule_v2"; order: PlanningActionClass[]; otherwise: typeof NO_V2_TRIGGER; fpps_min: number; exposure_floor_for_non_e: number };
  headline: { guardrail: "GR8_headline_stability"; class_retention_min: number };
  cases: ProtocolCase[];
  cases_without_class: string[];
  cut_cases: string[];
  product_4009: {
    source_product: string;
    licence: string;
    credit: string;
    event_code: string;
    layer_names: string[];
    accumulated_names: string[];
    dated_names: string[];
    dated_acquisition_date: string;
  };
}

/** The protocols in force, as Python wrote them. The parser checks every overlay against this record. */
export const PLANNING_PROTOCOL_BINDING = protocolBinding as unknown as PlanningProtocolBinding;

const BINDING = PLANNING_PROTOCOL_BINDING;
const RULE = BINDING.confidence_rule;
const FRAME = BINDING.scoring_frame;
const PRODUCT_4009 = BINDING.product_4009;

export const PRODUCT_4009_SOURCE = PRODUCT_4009.source_product;
export const PRODUCT_4009_LICENCE = PRODUCT_4009.licence;
export const PRODUCT_4009_CREDIT = PRODUCT_4009.credit;

// --- Shape ------------------------------------------------------------------------------------------------------
// The shape below mirrors the JSON schema node for node; a unit test compares the two, so they cannot drift apart.
// The signed numbers (weights, anchors, thresholds) are constants here and in the schema.

export type OverlaySpec =
  | { k: "text" }
  | { k: "string" }
  | { k: "pattern"; source: string }
  | { k: "date" }
  | { k: "number"; min?: number; max?: number; exclusiveMax?: number; integer?: boolean }
  | { k: "boolean" }
  | { k: "null" }
  | { k: "const"; value: string | number | boolean }
  | { k: "enum"; values: readonly (string | null)[] }
  | { k: "array"; items: OverlaySpec; minItems?: number; maxItems?: number; unique?: boolean }
  | { k: "object"; name?: string; fields: Record<string, OverlaySpec> }
  | { k: "map"; values: OverlaySpec; keyPattern?: string; minProperties?: number }
  | { k: "oneOf"; options: OverlaySpec[] };

/** The pattern of a calendar date. The `date` spec also requires the date to exist (no 2030-13-45). */
export const ISO_DATE_PATTERN = "^[0-9]{4}-[0-9]{2}-[0-9]{2}$";
const IDENTIFIER_PATTERN = "^[a-z0-9][a-z0-9_.-]{1,63}$";

const TEXT: OverlaySpec = { k: "text" };
const STRING: OverlaySpec = { k: "string" };
const BOOLEAN: OverlaySpec = { k: "boolean" };
const NULL: OverlaySpec = { k: "null" };
const SCORE: OverlaySpec = { k: "number", min: 0, max: 100 };
const SHARE: OverlaySpec = { k: "number", min: 0, max: 1 };
const COUNT: OverlaySpec = { k: "number", min: 0 };
const WHOLE_FROM_0: OverlaySpec = { k: "number", min: 0, integer: true };
const WHOLE_FROM_1: OverlaySpec = { k: "number", min: 1, integer: true };
const SHA256: OverlaySpec = { k: "pattern", source: "^[0-9a-f]{64}$" };
const ISO_DATE: OverlaySpec = { k: "date" };
const INSTANT: OverlaySpec = {
  k: "pattern",
  source: "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$",
};
const INPUT_ID: OverlaySpec = { k: "pattern", source: IDENTIFIER_PATTERN };
const PRODUCT_ID: OverlaySpec = { k: "pattern", source: IDENTIFIER_PATTERN };
const PASS_FAIL = ["pass", "fail"] as const;
const constant = (value: string | number | boolean): OverlaySpec => ({ k: "const", value });
const oneOfValues = (values: readonly (string | null)[]): OverlaySpec => ({ k: "enum", values });
const nullable = (spec: OverlaySpec): OverlaySpec => ({ k: "oneOf", options: [spec, NULL] });
const object = (fields: Record<string, OverlaySpec>, name?: string): OverlaySpec => ({ k: "object", name, fields });
const list = (items: OverlaySpec, limits: { minItems?: number; maxItems?: number; unique?: boolean } = {}): OverlaySpec => ({ k: "array", items, ...limits });
const perComponent = (spec: (name: ScoreComponent) => OverlaySpec): Record<string, OverlaySpec> =>
  Object.fromEntries(SCORE_COMPONENTS.map((name) => [name, spec(name)]));
const constants = (values: object): Record<string, OverlaySpec> =>
  Object.fromEntries(Object.entries(values).map(([name, value]) => [name, constant(value as number)]));

const ACTION_CLASS = oneOfValues(PLANNING_ACTION_CLASSES);
const ASSUMPTIONS = list(TEXT, { minItems: 1, unique: true });
const PROTOCOL_SHA256 = object({ v1a: SHA256, v1b: SHA256 }, "protocolSha256");
const PERMANENT_WATER = object({ source: TEXT, class: { k: "number", integer: true } }, "permanentWater");
const recordHead = (name: ScoreComponent): Record<string, OverlaySpec> => ({
  component: constant(name),
  value_0_100: SCORE,
  normalisation_version: constant("planning_frame_v1"),
  protocol_sha256: PROTOCOL_SHA256,
  definition: TEXT,
});
const SERVICE_INPUTS = { mode: TEXT, threshold_minutes: WHOLE_FROM_1, baseline_access_residents: COUNT, newly_lost_residents: COUNT };

const COMPONENT_RECORDS: Record<ScoreComponent, OverlaySpec> = {
  flood_likelihood_0_100: object({
    ...recordHead("flood_likelihood_0_100"),
    inputs: object({ flooded_non_permanent_water_land_area: COUNT, non_permanent_water_land_area: COUNT }),
    flooded_share: SHARE,
    anchor: SHARE,
    anchor_sensitivity_one_at_a_time: list(object({ anchor: SHARE, value_0_100: SCORE })),
    anchor_disclosure: TEXT,
    permanent_water: PERMANENT_WATER,
  }, "floodLikelihoodRecord"),
  exposure_0_100: object({
    ...recordHead("exposure_0_100"),
    inputs: object({ residents_inside_flood_extent: COUNT, unit_residents: COUNT }),
    exposed_share: SHARE,
    kind: constant("share_only"),
  }, "exposureRecord"),
  access_gap_0_100: object({
    ...recordHead("access_gap_0_100"),
    inputs: object({ services: { k: "map", values: object(SERVICE_INPUTS), minProperties: 1 } }),
    services: list(object({
      service: TEXT,
      mode: TEXT,
      threshold_minutes: WHOLE_FROM_1,
      baseline_access_residents: COUNT,
      newly_lost_residents: COUNT,
      newly_lost_share: nullable(SHARE),
    }), { minItems: 1 }),
    baseline_access_residents_all_services: COUNT,
    publication_level: oneOfValues(["public", "pitch"]),
  }, "accessGapRecord"),
  road_criticality_0_100: object({
    ...recordHead("road_criticality_0_100"),
    inputs: object({ residents_losing_all_routes: COUNT, residents_with_baseline_route: COUNT }),
    share_losing_all_routes: SHARE,
  }, "roadCriticalityRecord"),
  vulnerability_context_0_100: object({
    ...recordHead("vulnerability_context_0_100"),
    inputs: object({ children_0_14: COUNT, older_60_plus: COUNT, residents: COUNT }),
    dependent_share: SHARE,
    anchors: object({ lower: TEXT, lower_value: SHARE, upper: TEXT, upper_value: SHARE }),
    anchor_sensitivity: object({ lower: TEXT, lower_value: SHARE, upper: TEXT, upper_value: SHARE, value_0_100: SCORE }),
    anchor_version: constant("national_vulnerability_anchors_v1"),
    anchor_receipt_sha256: SHA256,
    caveat: TEXT,
  }, "vulnerabilityRecord"),
};
const SYNTHETIC_COMPONENT = object({ component: oneOfValues(SCORE_COMPONENTS), value_0_100: SCORE, synthetic: constant(true) }, "syntheticComponent");

const T2_SKILL_CONDITION = object({
  flood_input: STRING,
  status: oneOfValues(["declared_unable_to_meet", "not_evaluated_by_the_rule", "evaluated"]),
  passes: BOOLEAN,
  conditions: object(Object.fromEntries(T2_SKILL_CONDITION_IDS.map((name) => [name, oneOfValues(PASS_FAIL)]))),
  failed_conditions: list(oneOfValues(T2_SKILL_CONDITION_IDS), { unique: true }),
  measurements: object({
    geoid_held_out_test_iou: nullable(SHARE),
    abstention_fraction: nullable(SHARE),
    unit_valid_coverage: nullable(SHARE),
    recency_days: nullable(WHOLE_FROM_0),
  }),
  thresholds: object(constants(RULE.t2_skill.thresholds)),
  metric_wording: TEXT,
  protocol_v1a_sha256: SHA256,
}, "t2SkillCondition");

// Rule v1 records by_construction for C3 only, and by_scenario_declaration for C1 and C2 only.
const BASIS_VALUES_BY_CONDITION: Record<ConfidenceConditionId, readonly ConfidenceBasisValue[]> = {
  C1_tier: ["pass", "fail", "by_scenario_declaration"],
  C2_recency: ["pass", "fail", "by_scenario_declaration"],
  C3_coverage: ["pass", "fail", "by_construction"],
  C4_input_uncertainty: PASS_FAIL,
  C5_components: PASS_FAIL,
  C6_residents: PASS_FAIL,
  C7_baseline_no_route: PASS_FAIL,
  C8_hospital: PASS_FAIL,
};

const DERIVED_CONFIDENCE = object({
  unit_id: TEXT,
  lane: oneOfValues(["OBS", "SCN", "SCN-ENV"]),
  tier: oneOfValues(["T1", "T2", "T3"]),
  flood_input: STRING,
  scenario_base: oneOfValues(["agency_product_as_provided", "own_t2_candidate", null]),
  confidence_rule_version: constant("confidence_rule_v1"),
  confidence_class: oneOfValues(ASSIGNED_CONFIDENCE_CLASSES),
  confidence_kind: oneOfValues(["observed", "scenario"]),
  basis: object(Object.fromEntries(CONFIDENCE_CONDITION_IDS.map((name) => [name, oneOfValues(BASIS_VALUES_BY_CONDITION[name])]))),
  failed_conditions: list(oneOfValues(CONFIDENCE_CONDITION_IDS), { unique: true }),
  reason_code: oneOfValues(["low_confidence", "insufficient_denominator", null]),
  guardrail_gr1: object({
    id: constant("GR1_minimum_denominators"),
    applies: BOOLEAN,
    unit_residents_min_for_class: constant(RULE.gr1_unit_residents_min_for_class),
    no_binding_class: BOOLEAN,
    no_would_be_class: BOOLEAN,
    no_v2_class: BOOLEAN,
  }, "guardrailGr1"),
  t2_skill_condition: nullable(T2_SKILL_CONDITION),
  measurements: object({
    recency_days: nullable(WHOLE_FROM_0),
    acquisition_date: nullable(ISO_DATE),
    case_reference_date: nullable(ISO_DATE),
    unit_valid_coverage: nullable(SHARE),
    coverage_by_construction: BOOLEAN,
    exposure_plus_one_pixel_0_100: nullable(SCORE),
    exposure_minus_one_pixel_0_100: nullable(SCORE),
    exposure_plus_minus_one_pixel_points: nullable(SCORE),
    t2_abstention_fraction: nullable(SHARE),
    component_status: object(perComponent(() => oneOfValues(["computed", "assumed", "not_computed"]))),
    unit_residents: COUNT,
    baseline_vehicle_no_route_share: nullable(SHARE),
    hospitals_reachable_at_baseline: nullable(COUNT),
  }),
  thresholds: object(constants(RULE.thresholds)),
  uses_ensemble_output: constant(false),
  rights_are_an_input: constant(false),
  protocol_v1a_sha256: SHA256,
  assumptions: ASSUMPTIONS,
}, "derivedConfidence");

const DECLARED_CONFIDENCE = object({
  confidence_class: oneOfValues(ASSIGNED_CONFIDENCE_CLASSES),
  confidence_kind: constant("declared"),
  declaration: TEXT,
}, "declaredConfidence");

const ROW = object({
  row_id: TEXT,
  unit_id: TEXT,
  unit_name_en: TEXT,
  unit_name_th: TEXT,
  tier: oneOfValues(EVIDENCE_TIERS),
  lane: nullable(oneOfValues(PLANNING_LANES)),
  temporal_relation: nullable(oneOfValues(TEMPORAL_RELATIONS)),
  flood_input: nullable(TEXT),
  scenario: nullable(object({ id: TEXT, declaration: TEXT }, "scenario")),
  lineage: object({
    flood_input_id: nullable(INPUT_ID),
    routing_context_id: nullable(INPUT_ID),
    closure_rule: nullable(object({
      version: constant("closure_rule_v1"),
      level: oneOfValues(["strict", "central", "permissive"]),
      closure_basis: { k: "pattern", source: "^modelled_from_.+" },
    }, "closureRule")),
  }, "lineage"),
  normalisation_version: constant("planning_frame_v1"),
  components: object(perComponent((name) => ({ k: "oneOf", options: [COMPONENT_RECORDS[name], SYNTHETIC_COMPONENT, NULL] })), "components"),
  fpps_0_100: nullable(SCORE),
  confidence: { k: "oneOf", options: [DERIVED_CONFIDENCE, DECLARED_CONFIDENCE, NULL] },
  action_class: nullable(ACTION_CLASS),
  action_reason_code: nullable(oneOfValues(PLANNING_REASON_CODES)),
  would_be_class: nullable(ACTION_CLASS),
  class_v2: nullable(object({
    class_rule_version: constant("class_rule_v2"),
    label: constant("secondary"),
    binding: constant(false),
    result: oneOfValues([...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER, V2_NOT_EVALUATED, null]),
    trigger_evidence: list(object({ trigger: ACTION_CLASS, met: nullable(BOOLEAN), evidence: TEXT }, "triggerEvidence"), { maxItems: 5 }),
  }, "classV2")),
  leave_one_component_out: nullable(object(perComponent(() => object({ fpps_0_100: SCORE, action_class: nullable(ACTION_CLASS) })), "leaveOneComponentOut")),
  headline_stability: object({
    guardrail: constant("GR8_headline_stability"),
    status: oneOfValues(HEADLINE_STATUSES),
    class_retention: nullable(SHARE),
    class_retention_min: constant(0.6),
  }, "headlineStability"),
  accepted_fpps: NULL,
  accepted_action_class: NULL,
  source_timestamp: INSTANT,
  assumptions: ASSUMPTIONS,
}, "row");

/** The shape of an overlay. It is exported for the unit test that compares it with the JSON schema. */
export const PLANNING_OVERLAY_SHAPE: OverlaySpec = object({
  schema_version: constant(PLANNING_OVERLAY_SCHEMA_VERSION),
  schema_id: constant(PLANNING_OVERLAY_SCHEMA_ID),
  dataset_mode: oneOfValues(["fixture_demo", "candidate"]),
  operational_status: constant("non_operational"),
  official_warning: constant(false),
  can_feed_decision_layer: constant(false),
  accepted_fpps: NULL,
  accepted_action_class: NULL,
  source_timestamp: INSTANT,
  generated_at: INSTANT,
  source_name: TEXT,
  data_version: TEXT,
  git_commit: { k: "pattern", source: "^[0-9a-f]{7,40}$" },
  case: object({
    case_id: TEXT,
    kind: oneOfValues(["fixture", "portfolio_case"]),
    title_en: TEXT,
    title_th: TEXT,
    frame: TEXT,
    case_reference_date: nullable(ISO_DATE),
    fixture_notice: nullable(TEXT),
  }, "case"),
  protocol_sha256: PROTOCOL_SHA256,
  evidence_tier_model_version: constant("evidence_tiers_v1"),
  normalisation_version: constant("planning_frame_v1"),
  confidence_rule_version: constant("confidence_rule_v1"),
  class_rule_version: constant("class_rule_v1"),
  secondary_class_rule_version: constant("class_rule_v2"),
  scoring_frame: object({
    normalisation_version: constant("planning_frame_v1"),
    normalisation_rule: TEXT,
    weights: object(constants(FRAME.weights), "weights"),
    flood_anchor: constant(FRAME.flood_anchor),
    flood_anchor_sensitivity_one_at_a_time: list(SHARE),
    flood_anchor_disclosure: TEXT,
    permanent_water: PERMANENT_WATER,
    exposure_kind: constant("share_only"),
    access_services: list(object({ service: TEXT, mode: TEXT, threshold_minutes: WHOLE_FROM_1, level: oneOfValues(["public", "pitch"]) }, "accessService"), { minItems: 1 }),
    vulnerability_anchor_version: constant("national_vulnerability_anchors_v1"),
    vulnerability_anchors: object({ lower: TEXT, upper: TEXT, values: { k: "map", values: SHARE, keyPattern: "^P[0-9]{1,2}$", minProperties: 2 } }),
    vulnerability_anchor_sensitivity: object({ lower: TEXT, upper: TEXT }),
    vulnerability_anchor_receipt_sha256: SHA256,
    leave_one_component_out_weights: object(perComponent((name) => object(constants(FRAME.leave_one_component_out_weights[name])))),
    lane_disclosure: constant(FRAME.lane_disclosure),
    protocol_sha256: PROTOCOL_SHA256,
  }, "scoringFrame"),
  publication_eligibility: oneOfValues(PUBLICATION_LEVELS),
  inputs: list(object({
    input_id: INPUT_ID,
    role: oneOfValues(INPUT_ROLES),
    name: TEXT,
    source_product: nullable(PRODUCT_ID),
    acquisition_date: nullable(ISO_DATE),
    sha256: SHA256,
    rights_level: oneOfValues(PUBLICATION_LEVELS),
    licence: TEXT,
    attribution: TEXT,
    change_notice: nullable(TEXT),
    source_timestamp: TEXT,
  }, "input"), { minItems: 1 }),
  assumptions: ASSUMPTIONS,
  rows: list(ROW, { minItems: 1 }),
});

const compiled = new Map<string, RegExp>();
const matches = (source: string, value: string): boolean => {
  let pattern = compiled.get(source);
  if (!pattern) {
    pattern = new RegExp(source);
    compiled.set(source, pattern);
  }
  return pattern.test(value);
};
const isRecord = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
const show = (value: unknown): string => JSON.stringify(value) ?? String(value);

const DAY_MS = 86_400_000;
/** The time of a calendar date, or null when the text is not a date that exists (2030-13-45, 2030-02-30). */
function calendarDayMs(value: unknown): number | null {
  if (typeof value !== "string" || !matches(ISO_DATE_PATTERN, value)) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1) return null;
  const date = new Date(Date.UTC(2000, month - 1, day));
  date.setUTCFullYear(year);
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? date.getTime() : null;
}

/** Structure problems of `value` against `spec`: exact keys, types, enumerations, ranges and patterns. */
function shapeProblems(value: unknown, spec: OverlaySpec, path: string, out: PlanningOverlayProblem[]): void {
  const fail = (message: string) => out.push({ code: "structure", path, message });
  switch (spec.k) {
    case "text":
      if (typeof value !== "string" || value.length === 0) fail("must be non-empty text");
      return;
    case "string":
      if (typeof value !== "string") fail("must be text");
      return;
    case "pattern":
      if (typeof value !== "string" || !matches(spec.source, value)) fail(`must match ${spec.source}`);
      return;
    case "date":
      if (calendarDayMs(value) === null) fail("must be a calendar date, YYYY-MM-DD");
      return;
    case "number":
      if (typeof value !== "number" || !Number.isFinite(value)) fail("must be a finite number");
      else if (spec.integer && !Number.isInteger(value)) fail("must be a whole number");
      else if ((spec.min !== undefined && value < spec.min) || (spec.max !== undefined && value > spec.max) || (spec.exclusiveMax !== undefined && value >= spec.exclusiveMax)) fail(`${value} is out of range`);
      return;
    case "boolean":
      if (typeof value !== "boolean") fail("must be true or false");
      return;
    case "null":
      if (value !== null) fail("must be null");
      return;
    case "const":
      if (value !== spec.value) fail(`must be ${show(spec.value)}`);
      return;
    case "enum":
      if (!(value === null || typeof value === "string") || !spec.values.includes(value)) fail(`${show(value)} is not one of ${show(spec.values)}`);
      return;
    case "array": {
      if (!Array.isArray(value)) return void fail("must be a list");
      if ((spec.minItems !== undefined && value.length < spec.minItems) || (spec.maxItems !== undefined && value.length > spec.maxItems)) fail(`has ${value.length} items`);
      if (spec.unique && new Set(value.map(show)).size !== value.length) fail("repeats an item");
      value.forEach((item, index) => shapeProblems(item, spec.items, `${path}[${index}]`, out));
      return;
    }
    case "object": {
      if (!isRecord(value)) return void fail("must be an object");
      for (const key of Object.keys(spec.fields)) if (!(key in value)) out.push({ code: "structure", path: `${path}.${key}`, message: "is required" });
      for (const key of Object.keys(value)) {
        if (key in spec.fields) shapeProblems(value[key], spec.fields[key], `${path}.${key}`, out);
        else out.push({ code: "structure", path: `${path}.${key}`, message: "is not a field of the overlay schema" });
      }
      return;
    }
    case "map": {
      if (!isRecord(value)) return void fail("must be an object");
      const keys = Object.keys(value);
      if (spec.minProperties !== undefined && keys.length < spec.minProperties) fail(`has ${keys.length} entries`);
      for (const key of keys) {
        if (spec.keyPattern && !matches(spec.keyPattern, key)) out.push({ code: "structure", path: `${path}.${key}`, message: `the key must match ${spec.keyPattern}` });
        shapeProblems(value[key], spec.values, `${path}.${key}`, out);
      }
      return;
    }
    case "oneOf": {
      const attempts = spec.options.map((option) => {
        const found: PlanningOverlayProblem[] = [];
        shapeProblems(value, option, path, found);
        return found;
      });
      if (attempts.some((found) => found.length === 0)) return;
      // Report the closest shape: the one with the fewest problems says most about what is wrong.
      const closest = attempts.reduce((best, found) => (found.length < best.length ? found : best));
      out.push(...closest);
      return;
    }
  }
}

// --- Rules ------------------------------------------------------------------------------------------------------

const CLASSES_ABOVE_E: readonly unknown[] = ["A", "B", "C", "D"];
const TIER_LANES: Record<EvidenceTier, readonly (PlanningLane | null)[]> = {
  T0: ["ENG"],
  T1: ["SCN", "SCN-ENV"],
  T2: ["OBS"],
  T3: ["OBS"],
  T4: [null],
};
const KIND_BY_TIER: Record<Exclude<EvidenceTier, "T4">, ConfidenceKind> = { T0: "declared", T1: "scenario", T2: "observed", T3: "observed" };
const REASON_BY_CLASS: Record<Exclude<PlanningActionClass, "E">, PlanningReasonCode> = {
  A: "life_safety_exposure",
  B: "critical_route_access",
  C: "essential_service_access",
  D: "resilience",
};
// The scorer rounds FPPS to two decimals, so a stated FPPS may differ from the weighted sum by half a hundredth.
const FPPS_TOLERANCE = 0.005 + 1e-9;
const MEASUREMENT_TOLERANCE = 1e-9;
const SHARE_TOLERANCE = 1e-9;
const FIXTURE_LABEL = "not a place";
const CLOSURE_BASIS_PREFIX = "modelled_from_";
const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// Text that names product 4009 whatever the spelling: the citation the rights module knows, the bare product
// number ("the 4009 22 Oct layer"), the event code and the two layer names of protocol v1a.
const PRODUCT_4009_TEXT = new RegExp(
  ["(?:unosat|product)[-_ /A-Za-z]{0,20}?4009(?![0-9])", "(?:^|[^0-9A-Za-z])4009(?![0-9])", escapeRegExp(PRODUCT_4009.event_code), ...PRODUCT_4009.layer_names.map(escapeRegExp)].join("|"),
  "i",
);

const laneColumn = (lane: PlanningLane | null): LaneColumn => (lane === null ? "no_lane" : lane === "SCN-ENV" ? "SCN" : lane);
const met = (passes: boolean): "pass" | "fail" => (passes ? "pass" : "fail");
const atLeast = (value: number | null, minimum: number): boolean => value !== null && value >= minimum;
const atMost = (value: number | null, maximum: number): boolean => value !== null && value <= maximum;
const differs = (stated: number | null, expected: number | null): boolean =>
  stated === null || expected === null ? stated !== expected : Math.abs(stated - expected) > MEASUREMENT_TOLERANCE;
const ownCandidate = (record: DerivedConfidence): boolean => record.tier === "T2" || record.scenario_base === "own_t2_candidate";
const isFrameRecord = (record: FrameComponentRecord | SyntheticComponent | null): record is FrameComponentRecord => record !== null && !("synthetic" in record);
const declaresProduct4009 = (item: PlanningOverlayInput): boolean => item.source_product === PRODUCT_4009_SOURCE;
const namesProduct4009 = (item: PlanningOverlayInput): boolean => [item.input_id, item.name, item.attribution].some((text) => PRODUCT_4009_TEXT.test(text));

/** Deep equality of two JSON values; the order of object keys does not matter. */
function sameJson(left: unknown, right: unknown, tolerance = 0): boolean {
  if (typeof left === "number" && typeof right === "number") return left === right || Math.abs(left - right) <= tolerance * Math.max(1, Math.abs(left), Math.abs(right));
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((item, index) => sameJson(item, right[index], tolerance));
  if (isRecord(left) && isRecord(right)) {
    const keys = Object.keys(left);
    return keys.length === Object.keys(right).length && keys.every((key) => key in right && sameJson(left[key], right[key], tolerance));
  }
  return left === right;
}

/** The whole days between two echoed dates, or null when either is missing. */
function recencyDays(acquisitionDate: string | null, caseReferenceDate: string | null): number | null {
  const acquired = calendarDayMs(acquisitionDate);
  const reference = calendarDayMs(caseReferenceDate);
  return acquired === null || reference === null ? null : Math.round(Math.abs(acquired - reference) / DAY_MS);
}

/**
 * The temporal relation the two echoed dates give (protocol v1a `date_rule`). An input is `event_aligned` only when
 * its acquisition is within the recency window of the case reference date; the rule is strict. A dated input outside
 * the window, or with no reference date to compare with, is `dated_other`. An input with no single acquisition date
 * is a `season_window`.
 */
export function expectedTemporalRelation(measurements: Pick<ConfidenceMeasurements, "acquisition_date" | "case_reference_date">, recencyWindowDays: number = RULE.thresholds.recency_window_days): TemporalRelation {
  if (measurements.acquisition_date === null) return "season_window";
  return atMost(recencyDays(measurements.acquisition_date, measurements.case_reference_date), recencyWindowDays) ? "event_aligned" : "dated_other";
}

/** The four conditions of the T2 skill bar from the measurements a skill record echoes (protocol v1a `t2_skill_bar`). */
function skillConditions(skill: T2SkillCondition, limits: Record<T2SkillConditionId, number>): Record<T2SkillConditionId, "pass" | "fail"> {
  return {
    geoid_held_out_test_iou_min: met(atLeast(skill.measurements.geoid_held_out_test_iou, limits.geoid_held_out_test_iou_min)),
    mae_sai_abstention_fraction_max: met(atMost(skill.measurements.abstention_fraction, limits.mae_sai_abstention_fraction_max)),
    mae_sai_unit_coverage_min: met(atLeast(skill.measurements.unit_valid_coverage, limits.mae_sai_unit_coverage_min)),
    recency_window_days: met(atMost(skill.measurements.recency_days, limits.recency_window_days)),
  };
}

/**
 * The basis of C1 to C8 that rule v1 (protocol v1a `confidence_rule_v1`) gives the measurements a confidence record
 * echoes: C1 from the tier and the T2 skill record, C2 from the two dates (or the scenario declaration for a tier T1
 * row), C3 to C8 from their measurements. A missing measurement fails its condition.
 */
export function expectedConfidenceBasis(record: DerivedConfidence, thresholds: ConfidenceThresholds = RULE.thresholds, skillPasses: boolean | null = record.t2_skill_condition?.passes ?? null): Record<ConfidenceConditionId, ConfidenceBasisValue> {
  const m = record.measurements;
  const points = m.exposure_plus_one_pixel_0_100 === null || m.exposure_minus_one_pixel_0_100 === null ? null : Math.abs(m.exposure_plus_one_pixel_0_100 - m.exposure_minus_one_pixel_0_100);
  const pointsMax = thresholds.exposure_plus_minus_one_pixel_max_points + thresholds.exposure_plus_minus_one_pixel_float_guard_points;
  return {
    C1_tier: record.tier === "T3" ? "pass" : skillPasses !== null ? met(skillPasses) : record.tier === "T1" ? "by_scenario_declaration" : "fail",
    C2_recency: record.tier === "T1" ? "by_scenario_declaration" : met(atMost(recencyDays(m.acquisition_date, m.case_reference_date), thresholds.recency_window_days)),
    C3_coverage: m.coverage_by_construction ? "by_construction" : met(atLeast(m.unit_valid_coverage, thresholds.unit_valid_coverage_min)),
    C4_input_uncertainty: met(atMost(points, pointsMax) && (!ownCandidate(record) || atMost(m.t2_abstention_fraction, thresholds.t2_abstention_fraction_max))),
    C5_components: met(SCORE_COMPONENTS.every((name) => m.component_status[name] === "computed")),
    C6_residents: met(m.unit_residents >= thresholds.unit_residents_min),
    C7_baseline_no_route: met(atMost(m.baseline_vehicle_no_route_share, thresholds.baseline_vehicle_no_route_share_max)),
    C8_hospital: met(atLeast(m.hospitals_reachable_at_baseline, thresholds.hospitals_reachable_at_baseline_min)),
  };
}

/**
 * Class rule v1 (protocol v1a `class_rules.v1.rules`): the rules are evaluated in the order listed and the first one
 * that matches gives the class. `fpps` is the FPPS rounded to two decimals, as the scorer compares it.
 */
export function classByRuleV1(values: Record<ScoreComponent, number>, fpps: number, confidenceClass: string, rules: readonly ClassRuleV1[] = BINDING.class_rule_v1.rules): PlanningActionClass {
  const fields: Record<string, string | number> = { ...values, fpps_0_100: fpps, confidence_class: confidenceClass };
  const holds = (condition: ClassRuleV1["conditions"][number]): boolean => {
    if (condition.operator === "==") return fields[condition.field] === condition.value;
    const left = Number(fields[condition.field]);
    const right = Number(condition.value);
    switch (condition.operator) {
      case "<":
        return left < right;
      case "<=":
        return left <= right;
      case ">":
        return left > right;
      case ">=":
        return left >= right;
      default:
        throw new Error(`class rule v1 uses an operator this parser does not know: ${condition.operator}`);
    }
  };
  for (const rule of rules) {
    if (rule.combine === "otherwise" || (rule.combine === "any" ? rule.conditions.some(holds) : rule.conditions.every(holds))) return rule.class;
  }
  throw new Error("class rule v1 gives no class: it has no rule that matches every row");
}

/** The refusals that are named whatever else is wrong; they assume nothing about the shape. */
function guardProblems(overlay: Record<string, unknown>): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  if (overlay.official_warning !== false) out.push({ code: "official_warning_not_false", path: "$.official_warning", message: "must be false" });
  if (overlay.operational_status !== "non_operational") out.push({ code: "operational_status_not_non_operational", path: "$.operational_status", message: "must be non_operational" });
  const accepted = (holder: Record<string, unknown>, where: string) => {
    for (const name of ["accepted_fpps", "accepted_action_class"]) {
      if (holder[name] !== null && holder[name] !== undefined) out.push({ code: "accepted_value_not_null", path: `${where}.${name}`, message: "is null while tier T4 is locked" });
    }
  };
  accepted(overlay, "$");
  if (!Array.isArray(overlay.rows)) return out;
  overlay.rows.forEach((row: unknown, index: number) => {
    if (!isRecord(row)) return;
    const where = `$.rows[${index}]`;
    if (!(EVIDENCE_TIERS as readonly unknown[]).includes(row.tier)) out.push({ code: "unknown_tier", path: `${where}.tier`, message: `${show(row.tier)} is not one of ${EVIDENCE_TIERS.join(", ")}` });
    accepted(row, where);
    const confidenceClass = isRecord(row.confidence) ? row.confidence.confidence_class : null;
    const aboveE = CLASSES_ABOVE_E.includes(row.action_class);
    if (confidenceClass === "high") out.push({ code: "high_confidence_not_assigned", path: `${where}.confidence.confidence_class`, message: "high requires tier T4, which is locked in this release" });
    if (aboveE && confidenceClass !== "medium") {
      out.push({ code: "class_above_e_without_medium_confidence", path: `${where}.action_class`, message: `binding class ${show(row.action_class)} with confidence ${show(confidenceClass)}: no class above E without medium confidence` });
    }
    if (row.lane === "OBS" && row.temporal_relation !== "event_aligned" && aboveE) {
      out.push({ code: "temporal_honesty_gr7", path: `${where}.action_class`, message: `an OBS row that is ${show(row.temporal_relation)}, not event_aligned, carries binding class ${show(row.action_class)}` });
    }
  });
  return out;
}

/** The parts of the JSON schema that depend on another field: what each tier, case kind and input role must carry. */
function conditionalShapeProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const fail = (path: string, message: string) => out.push({ code: "structure", path, message });
  const fixture = overlay.case.kind === "fixture";
  if ((overlay.dataset_mode === "fixture_demo") !== fixture) fail("$.case.kind", "a fixture_demo overlay holds a fixture case, and only it does");
  if (fixture ? !(typeof overlay.case.fixture_notice === "string" && overlay.case.fixture_notice.includes(FIXTURE_LABEL)) : overlay.case.fixture_notice !== null) {
    fail("$.case.fixture_notice", `a fixture case says '${FIXTURE_LABEL}'; a portfolio case carries null`);
  }
  overlay.inputs.forEach((item, index) => {
    if (item.role !== "flood_input" && item.acquisition_date !== null) fail(`$.inputs[${index}].acquisition_date`, "only a flood input carries an acquisition date");
  });
  overlay.rows.forEach((row, index) => {
    const where = `$.rows[${index}]`;
    if (row.tier === LOCKED_TIER) return;
    const lineage = Object.values(row.lineage);
    if (row.confidence === null || row.action_reason_code === null) fail(where, "a row below tier T4 carries a confidence and a reason code");
    if (row.tier === "T0") {
      if (row.temporal_relation !== null || row.flood_input !== null || lineage.some((item) => item !== null) || row.class_v2 !== null || row.confidence?.confidence_kind !== "declared") {
        fail(where, "an engine row has no flood input, no lineage and no v2 class, and declares its confidence");
      }
    } else if (row.temporal_relation === null || row.flood_input === null || lineage.some((item) => item === null) || row.class_v2 === null || row.confidence?.confidence_kind === "declared") {
      fail(where, "a row of tier T1, T2 or T3 names its flood input, temporal relation and lineage, and carries a derived confidence and the v2 axis");
    }
    if ((row.tier === "T1") !== (row.scenario !== null)) fail(`${where}.scenario`, "a scenario declaration belongs to tier T1 rows, and every one has it");
  });
  return out;
}

function overlayLevelProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  if (!sameJson(overlay.scoring_frame.protocol_sha256, overlay.protocol_sha256)) out.push({ code: "protocol_hash_mismatch", path: "$.scoring_frame.protocol_sha256", message: "differs from $.protocol_sha256" });
  const frame = overlay.scoring_frame;
  const weightSets: [string, ComponentWeights, ScoreComponent | null][] = [["weights", frame.weights, null]];
  for (const name of SCORE_COMPONENTS) weightSets.push([`leave_one_component_out_weights.${name}`, frame.leave_one_component_out_weights[name], name]);
  for (const [name, weights, dropped] of weightSets) {
    const total = SCORE_COMPONENTS.reduce((sum, component) => sum + weights[component], 0);
    if (Math.abs(total - 1) > 1e-9 || (dropped !== null && weights[dropped] !== 0)) {
      out.push({ code: "scoring_frame_inconsistent", path: `$.scoring_frame.${name}`, message: "the weights sum to 1, and a leave-one-out set gives the dropped component 0" });
    }
  }
  for (const [name, values] of [["input_id", overlay.inputs.map((item) => item.input_id)], ["row_id", overlay.rows.map((row) => row.row_id)]] as const) {
    const repeated = [...new Set(values.filter((value, index) => values.indexOf(value) !== index))].sort();
    if (repeated.length) out.push({ code: "duplicate_id", path: "$", message: `${name} repeated: ${repeated.join(", ")}` });
  }
  const keys = overlay.rows.map((row) => show([row.unit_id, row.lane, row.lineage.flood_input_id, row.scenario?.id ?? null]));
  const twice = overlay.rows.filter((_row, index) => keys.indexOf(keys[index]) !== keys.lastIndexOf(keys[index])).map((row) => row.row_id).sort();
  if (twice.length) out.push({ code: "duplicate_id", path: "$.rows", message: `one row is one unit in one lane with one flood input and one scenario; these rows share theirs: ${twice.join(", ")}` });
  const lowest = Math.min(...overlay.inputs.map((item) => PUBLICATION_LEVELS.indexOf(item.rights_level)));
  if (overlay.publication_eligibility !== PUBLICATION_LEVELS[lowest]) {
    out.push({ code: "publication_eligibility_not_lineage_minimum", path: "$.publication_eligibility", message: `${overlay.publication_eligibility} is not the minimum across the lineage (${PUBLICATION_LEVELS[lowest]})` });
  }
  overlay.rows.forEach((row, index) => {
    const record = row.components.access_gap_0_100;
    if (record && "publication_level" in record && record.publication_level === "pitch" && overlay.publication_eligibility === "public") {
      out.push({ code: "publication_eligibility_not_lineage_minimum", path: `$.rows[${index}].components.access_gap_0_100.publication_level`, message: "a pitch-level access gap cannot sit in a public overlay" });
    }
  });
  overlay.inputs.forEach((item, index) => {
    if (!declaresProduct4009(item)) {
      if (namesProduct4009(item)) out.push({ code: "source_product_not_declared", path: `$.inputs[${index}].source_product`, message: `the input names product 4009, so its source_product is ${show(PRODUCT_4009_SOURCE)}` });
      return;
    }
    if (item.licence !== PRODUCT_4009_LICENCE || !item.attribution.includes(PRODUCT_4009_CREDIT) || !item.change_notice?.trim()) {
      out.push({ code: "product_4009_licence_missing", path: `$.inputs[${index}]`, message: `a product 4009 input carries the licence ${PRODUCT_4009_LICENCE}, the credit '${PRODUCT_4009_CREDIT}' and a change notice` });
    }
  });
  if (overlay.dataset_mode === "fixture_demo") {
    const unlabelled = overlay.rows.filter((row) => !row.unit_name_en.includes(FIXTURE_LABEL)).map((row) => row.row_id);
    if (unlabelled.length) out.push({ code: "fixture_label_missing", path: "$.rows", message: `fixture units are named '${FIXTURE_LABEL}': ${unlabelled.join(", ")}` });
  }
  return out;
}

/** Check the T2 skill record of an own candidate against the measurements it echoes. */
function skillRecordProblems(record: DerivedConfidence, where: string): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (field: string, message: string) => out.push({ code: "confidence_record_mismatch", path: `${where}.confidence.${field}`, message });
  const skill = record.t2_skill_condition;
  const m = record.measurements;
  if ((skill !== null) !== ownCandidate(record)) add("t2_skill_condition", "an own candidate (tier T2, or the own-candidate base of a scenario) carries the T2 skill record, and no other row does");
  if (!ownCandidate(record) && m.t2_abstention_fraction !== null) add("measurements.t2_abstention_fraction", "the T2 abstention fraction belongs to an own candidate only");
  if (skill === null) return out;
  const echoed = { abstention_fraction: m.t2_abstention_fraction, unit_valid_coverage: m.unit_valid_coverage, recency_days: recencyDays(m.acquisition_date, m.case_reference_date) };
  for (const name of ["abstention_fraction", "unit_valid_coverage", "recency_days"] as const) {
    if (differs(skill.measurements[name], echoed[name])) add(`t2_skill_condition.measurements.${name}`, `is ${show(skill.measurements[name])}; the confidence record measures ${show(echoed[name])}`);
  }
  if (skill.flood_input !== record.flood_input) add("t2_skill_condition.flood_input", "is not the flood input of the record");
  const conditions = skillConditions(skill, skill.thresholds);
  const failed = T2_SKILL_CONDITION_IDS.filter((name) => conditions[name] === "fail");
  if (!sameJson(skill.conditions, conditions) || skill.failed_conditions.join() !== failed.join()) add("t2_skill_condition.conditions", `the measurements of the skill record give ${show(conditions)}`);
  if (skill.passes !== (skill.status === "evaluated" && failed.length === 0)) add("t2_skill_condition.passes", "a T2 input passes only when the rule evaluates it and all four conditions pass");
  return out;
}

function derivedConfidenceProblems(overlay: PlanningAssessmentOverlay, row: PlanningOverlayRow, record: DerivedConfidence, where: string): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (code: PlanningOverlayRefusalCode, field: string, message: string) => out.push({ code, path: `${where}.confidence.${field}`, message });
  for (const name of ["unit_id", "lane", "tier", "flood_input"] as const) {
    if (record[name] !== row[name]) add("confidence_record_mismatch", name, `is ${show(record[name])}; the row says ${show(row[name])}`);
  }
  if ((record.scenario_base !== null) !== (row.tier === "T1")) add("confidence_record_mismatch", "scenario_base", "a scenario base is named for tier T1 rows only");
  if (record.lane === "SCN-ENV" && record.scenario_base !== "agency_product_as_provided") add("confidence_record_mismatch", "scenario_base", "lane SCN-ENV is the agency season layer, used as provided");
  if (record.protocol_v1a_sha256 !== overlay.protocol_sha256.v1a) add("protocol_hash_mismatch", "protocol_v1a_sha256", "differs from $.protocol_sha256.v1a");
  const m = record.measurements;
  const days = recencyDays(m.acquisition_date, m.case_reference_date);
  if (differs(m.recency_days, days)) add("confidence_record_mismatch", "measurements.recency_days", `the two dates of the record are ${show(days)} days apart`);
  const points = m.exposure_plus_one_pixel_0_100 === null || m.exposure_minus_one_pixel_0_100 === null ? null : Math.abs(m.exposure_plus_one_pixel_0_100 - m.exposure_minus_one_pixel_0_100);
  if (differs(m.exposure_plus_minus_one_pixel_points, points)) add("confidence_record_mismatch", "measurements.exposure_plus_minus_one_pixel_points", `the two exposures of the record are ${show(points)} points apart`);
  if (m.coverage_by_construction && ownCandidate(record)) add("confidence_record_mismatch", "measurements.coverage_by_construction", "coverage by construction is stated for an agency product, not for an own candidate");
  out.push(...skillRecordProblems(record, where));
  const recomputed = expectedConfidenceBasis(record, record.thresholds);
  for (const name of CONFIDENCE_CONDITION_IDS) {
    if (record.basis[name] !== recomputed[name]) add("confidence_record_mismatch", `basis.${name}`, `is ${show(record.basis[name])}; the measurements the record echoes give ${show(recomputed[name])}`);
  }
  const failed = CONFIDENCE_CONDITION_IDS.filter((name) => record.basis[name] === "fail");
  if (record.failed_conditions.join() !== failed.join()) add("confidence_record_mismatch", "failed_conditions", `the basis record fails ${show(failed)}`);
  const expectedClass = failed.length ? "low" : "medium";
  if (record.confidence_class !== expectedClass) add("confidence_record_mismatch", "confidence_class", `the basis record gives ${expectedClass}`);
  const gr1 = record.guardrail_gr1;
  if (gr1.applies !== m.unit_residents < gr1.unit_residents_min_for_class) add("gr1_no_class", "guardrail_gr1.applies", "does not follow from the unit residents");
  if ([gr1.no_binding_class, gr1.no_would_be_class, gr1.no_v2_class].some((flag) => flag !== gr1.applies)) add("gr1_no_class", "guardrail_gr1", "no binding class, no would-be class and no v2 class go together");
  if (gr1.applies && !failed.includes("C6_residents")) add("gr1_no_class", "failed_conditions", "a unit under guardrail GR1 fails condition C6");
  const expectedReason = gr1.applies ? "insufficient_denominator" : failed.length ? "low_confidence" : null;
  if (record.reason_code !== expectedReason) add("confidence_record_mismatch", "reason_code", `is ${show(record.reason_code)}, expected ${show(expectedReason)}`);
  for (const name of SCORE_COMPONENTS) {
    const status = m.component_status[name];
    if (status === "assumed") out.push({ code: "assumed_component_in_a_row", path: `${where}.confidence.measurements.component_status.${name}`, message: "no case row and no scenario cell carries an assumed component (drafter reading DR-A05)" });
    if ((row.components[name] !== null) !== (status === "computed")) out.push({ code: "component_mismatch", path: `${where}.components.${name}`, message: `the confidence record says ${status}; a record is present only for a computed component` });
  }
  if (row.lane === "OBS" && m.case_reference_date !== overlay.case.case_reference_date) {
    add("confidence_record_mismatch", "measurements.case_reference_date", "an OBS row is judged against the reference date of its case");
  }
  const relation = expectedTemporalRelation(m, record.thresholds.recency_window_days);
  if (row.lane === "SCN-ENV" && relation !== "season_window") {
    out.push({ code: "temporal_relation_mismatch", path: `${where}.confidence.measurements.acquisition_date`, message: "lane SCN-ENV is the season layer, which has no single acquisition date and is not a dated extent" });
  }
  if (row.temporal_relation !== relation) {
    out.push({ code: "temporal_relation_mismatch", path: `${where}.temporal_relation`, message: `is ${show(row.temporal_relation)}; the dates the row echoes give ${show(relation)}. An input is event_aligned only when its acquisition is inside the recency window, and one with no single acquisition date is a season_window` });
  }
  return out;
}

/**
 * What rule v1 under the protocols in force derives from the measurements a confidence record echoes, against what the
 * record states. This is `confidence.derive_confidence` without its assumptions text.
 */
function ruleRecordProblems(record: DerivedConfidence, where: string): PlanningOverlayProblem[] {
  const refuse = (message: string): PlanningOverlayProblem[] => [{ code: "confidence_not_rule_record", path: `${where}.confidence`, message }];
  const m = record.measurements;
  const own = ownCandidate(record);
  if (!own && RULE.own_t2_candidates_named.includes(record.flood_input)) {
    return refuse(`protocol v1a names ${show(record.flood_input)} as an own T2 candidate: it is judged at tier T2, or as the own-candidate base of a scenario, and never as an agency product`);
  }
  if (m.coverage_by_construction) {
    const scope = RULE.coverage_by_construction;
    if (own || !scope.units.includes(record.unit_id) || !scope.flood_inputs.includes(record.flood_input)) {
      return refuse("coverage by construction is stated for product 4009 in the eight Mae Sai tambons only: for any other unit or flood input the unit's valid coverage is measured");
    }
    if (m.unit_valid_coverage !== null && m.unit_valid_coverage < RULE.thresholds.unit_valid_coverage_min) return refuse("coverage is declared by construction, but the measured coverage is below the minimum");
  }
  const differing: string[] = [];
  const note = (name: string, same: boolean) => {
    if (!same) differing.push(name);
  };
  const skill = record.t2_skill_condition;
  let skillPasses: boolean | null = null;
  if (own) {
    const status: T2SkillStatus = RULE.t2_skill.declared_unable_to_meet.includes(record.flood_input) ? "declared_unable_to_meet" : RULE.t2_skill.evaluated_by_the_rule.includes(record.flood_input) ? "evaluated" : "not_evaluated_by_the_rule";
    if (skill === null) {
      skillPasses = false;
      note("t2_skill_condition", false);
    } else {
      const conditions = skillConditions(skill, RULE.t2_skill.thresholds);
      const failed = T2_SKILL_CONDITION_IDS.filter((name) => conditions[name] === "fail");
      skillPasses = status === "evaluated" && failed.length === 0;
      const echoes = !differs(skill.measurements.abstention_fraction, m.t2_abstention_fraction) && !differs(skill.measurements.unit_valid_coverage, m.unit_valid_coverage) && !differs(skill.measurements.recency_days, recencyDays(m.acquisition_date, m.case_reference_date));
      note(
        "t2_skill_condition",
        skill.flood_input === record.flood_input && skill.status === status && skill.passes === skillPasses && sameJson(skill.conditions, conditions) && skill.failed_conditions.join() === failed.join() && echoes && sameJson(skill.thresholds, RULE.t2_skill.thresholds) && skill.protocol_v1a_sha256 === BINDING.protocol_sha256.v1a,
      );
    }
  } else {
    note("t2_skill_condition", skill === null);
  }
  const basis = expectedConfidenceBasis(record, RULE.thresholds, skillPasses);
  const failed = CONFIDENCE_CONDITION_IDS.filter((name) => basis[name] === "fail");
  const applies = m.unit_residents < RULE.gr1_unit_residents_min_for_class;
  note("basis", sameJson(record.basis, basis));
  note("failed_conditions", record.failed_conditions.join() === failed.join());
  note("confidence_class", record.confidence_class === (failed.length ? "low" : "medium"));
  note("confidence_kind", record.confidence_kind === (record.tier === "T1" ? "scenario" : "observed"));
  note("reason_code", record.reason_code === (applies ? "insufficient_denominator" : failed.length ? "low_confidence" : null));
  note("guardrail_gr1", sameJson(record.guardrail_gr1, { id: "GR1_minimum_denominators", applies, unit_residents_min_for_class: RULE.gr1_unit_residents_min_for_class, no_binding_class: applies, no_would_be_class: applies, no_v2_class: applies }));
  const points = m.exposure_plus_one_pixel_0_100 === null || m.exposure_minus_one_pixel_0_100 === null ? null : Math.abs(m.exposure_plus_one_pixel_0_100 - m.exposure_minus_one_pixel_0_100);
  note("measurements", !differs(m.recency_days, recencyDays(m.acquisition_date, m.case_reference_date)) && !differs(m.exposure_plus_minus_one_pixel_points, points) && (own || m.t2_abstention_fraction === null));
  note("thresholds", sameJson(record.thresholds, RULE.thresholds));
  note("protocol_v1a_sha256", record.protocol_v1a_sha256 === BINDING.protocol_sha256.v1a);
  return differing.length ? refuse(`rule v1 derives other values from the echoed measurements: ${differing.sort().join(", ")}`) : [];
}

const shareOf = (part: number, whole: number): number | null => (whole <= 0 || part > whole * (1 + SHARE_TOLERANCE) + SHARE_TOLERANCE ? null : Math.min(1, part / whole));
const anchored = (share: number, anchor: number): number => 100 * Math.min(1, share / anchor);
const between = (share: number, lower: number, upper: number): number => 100 * Math.min(1, Math.max(0, (share - lower) / (upper - lower)));

/**
 * The frame v1 record of the inputs a component record echoes (`floodguard.normalisation`), or null when the protocol
 * states no value for such inputs (a zero denominator, a part above its whole, services the frame does not declare).
 */
function expectedFrameRecord(record: FrameComponentRecord): Record<string, unknown> | null {
  const head = { component: record.component, normalisation_version: FRAME.normalisation_version, protocol_sha256: BINDING.protocol_sha256, definition: BINDING.component_definitions[record.component] };
  switch (record.component) {
    case "flood_likelihood_0_100": {
      const share = shareOf(record.inputs.flooded_non_permanent_water_land_area, record.inputs.non_permanent_water_land_area);
      if (share === null) return null;
      return {
        ...head,
        value_0_100: anchored(share, FRAME.flood_anchor),
        inputs: record.inputs,
        flooded_share: share,
        anchor: FRAME.flood_anchor,
        anchor_sensitivity_one_at_a_time: FRAME.flood_anchor_sensitivity_one_at_a_time.map((anchor) => ({ anchor, value_0_100: anchored(share, anchor) })),
        anchor_disclosure: FRAME.flood_anchor_disclosure,
        permanent_water: FRAME.permanent_water,
      };
    }
    case "exposure_0_100": {
      const share = shareOf(record.inputs.residents_inside_flood_extent, record.inputs.unit_residents);
      return share === null ? null : { ...head, value_0_100: 100 * share, inputs: record.inputs, exposed_share: share, kind: "share_only" };
    }
    case "access_gap_0_100": {
      const supplied = record.inputs.services;
      const names = Object.keys(supplied).sort().join();
      const publicNames = FRAME.access_services.filter((service) => service.level === "public").map((service) => service.service);
      const allNames = FRAME.access_services.map((service) => service.service);
      const level = names === [...publicNames].sort().join() ? "public" : names === [...allNames].sort().join() ? "pitch" : null;
      if (level === null) return null;
      const rows: AccessGapRecord["services"] = [];
      let lostWeighted = 0;
      let total = 0;
      for (const service of FRAME.access_services) {
        const counts = supplied[service.service];
        if (!counts) continue;
        if (counts.mode !== service.mode || counts.threshold_minutes !== service.threshold_minutes) return null;
        if (counts.newly_lost_residents > counts.baseline_access_residents * (1 + SHARE_TOLERANCE) + SHARE_TOLERANCE) return null;
        const share = counts.baseline_access_residents > 0 ? Math.min(1, counts.newly_lost_residents / counts.baseline_access_residents) : null;
        if (share !== null) lostWeighted += counts.baseline_access_residents * share;
        total += counts.baseline_access_residents;
        rows.push({ service: service.service, mode: service.mode, threshold_minutes: service.threshold_minutes, baseline_access_residents: counts.baseline_access_residents, newly_lost_residents: counts.newly_lost_residents, newly_lost_share: share });
      }
      if (total <= 0) return null;
      const inputs = { services: Object.fromEntries(rows.map((row) => [row.service, { mode: row.mode, threshold_minutes: row.threshold_minutes, baseline_access_residents: row.baseline_access_residents, newly_lost_residents: row.newly_lost_residents }])) };
      return { ...head, value_0_100: 100 * Math.min(1, lostWeighted / total), inputs, services: rows, baseline_access_residents_all_services: total, publication_level: level };
    }
    case "road_criticality_0_100": {
      const share = shareOf(record.inputs.residents_losing_all_routes, record.inputs.residents_with_baseline_route);
      return share === null ? null : { ...head, value_0_100: 100 * share, inputs: record.inputs, share_losing_all_routes: share };
    }
    case "vulnerability_context_0_100": {
      const share = shareOf(record.inputs.children_0_14 + record.inputs.older_60_plus, record.inputs.residents);
      if (share === null) return null;
      const anchors = FRAME.vulnerability_anchors;
      const sensitivity = FRAME.vulnerability_anchor_sensitivity;
      const value = (name: string): number => anchors.values[name];
      return {
        ...head,
        value_0_100: between(share, value(anchors.lower), value(anchors.upper)),
        inputs: record.inputs,
        dependent_share: share,
        anchors: { lower: anchors.lower, lower_value: value(anchors.lower), upper: anchors.upper, upper_value: value(anchors.upper) },
        anchor_sensitivity: { lower: sensitivity.lower, lower_value: value(sensitivity.lower), upper: sensitivity.upper, upper_value: value(sensitivity.upper), value_0_100: between(share, value(sensitivity.lower), value(sensitivity.upper)) },
        anchor_version: FRAME.vulnerability_anchor_version,
        anchor_receipt_sha256: FRAME.vulnerability_anchor_receipt_sha256,
        caveat: BINDING.vulnerability_caveat,
      };
    }
  }
}

/** The class a row would get, with the reasons a stated v2 axis disagrees with the row (protocol v1a class_rules.v2). */
function classV2Problems(row: PlanningOverlayRow, v2: ClassV2, low: boolean, exposure: number | null): string[] {
  const rule = BINDING.class_rule_v2;
  const order = v2.trigger_evidence.map((item) => item.trigger);
  const isMet = (trigger: PlanningActionClass): boolean => v2.trigger_evidence.some((item) => item.trigger === trigger && item.met === true);
  const wrong: string[] = [];
  if (order.join() !== rule.order.join()) {
    wrong.push(`trigger_evidence lists ${show(order)}, not ${show(rule.order)}`);
  } else {
    // Schema 1.1: a trigger nobody evaluated has `met` null. Where one stands before the first trigger met, or no
    // trigger is met and one was not evaluated, the result depends on it and is `not_evaluated`.
    const decisive = v2.trigger_evidence.find((item) => item.met !== false);
    const expected: ClassV2Result = decisive === undefined ? rule.otherwise : decisive.met === null ? V2_NOT_EVALUATED : decisive.trigger;
    if (v2.result !== expected) wrong.push(`result is ${show(v2.result)}; the first trigger met, or not evaluated, in the order ${show(rule.order)} gives ${show(expected)}`);
    const evaluatedE = v2.trigger_evidence[0]?.met !== null;
    if (!evaluatedE) wrong.push("trigger E is recomputed from the row, so it is true or false, never not evaluated");
    const scoredEnough = row.fpps_0_100 !== null && row.fpps_0_100 >= rule.fpps_min;
    const triggerE = low || !scoredEnough || (exposure !== null && exposure < rule.exposure_floor_for_non_e);
    if (evaluatedE && isMet("E") !== triggerE) wrong.push(`trigger E is ${triggerE ? "met" : "not met"} for this row: low confidence, exposure below ${rule.exposure_floor_for_non_e} or FPPS below ${rule.fpps_min}`);
    if (isMet("A") && row.action_class !== "A") wrong.push("trigger A needs the v1 class A");
    if (isMet("C") && (!scoredEnough || low)) wrong.push(`trigger C needs an FPPS of at least ${rule.fpps_min} and medium confidence`);
    if (isMet("D") && !scoredEnough) wrong.push(`trigger D needs an FPPS of at least ${rule.fpps_min}`);
  }
  if (low && v2.result !== "E") wrong.push("low confidence gives v2 class E");
  return wrong;
}

function rowProblems(overlay: PlanningAssessmentOverlay, row: PlanningOverlayRow, where: string): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (code: PlanningOverlayRefusalCode, field: string, message: string) => out.push({ code, path: field ? `${where}.${field}` : where, message });
  if (!TIER_LANES[row.tier].includes(row.lane)) add("tier_lane_mismatch", "lane", `tier ${row.tier} belongs to ${show(TIER_LANES[row.tier])}, not ${show(row.lane)}`);
  if (row.tier === LOCKED_TIER) {
    const slots = { temporal_relation: row.temporal_relation, flood_input: row.flood_input, scenario: row.scenario, fpps_0_100: row.fpps_0_100, confidence: row.confidence, action_class: row.action_class, action_reason_code: row.action_reason_code, would_be_class: row.would_be_class, class_v2: row.class_v2, leave_one_component_out: row.leave_one_component_out, ...row.components, ...row.lineage };
    const carried = Object.entries(slots).filter(([, value]) => value !== null).map(([name]) => name);
    if (row.headline_stability.status !== "not_evaluated") carried.push("headline_stability");
    if (carried.length) add("t4_locked_row_carries_values", "", `tier T4 is locked in this release; the row carries ${carried.join(", ")}`);
    return out;
  }
  const confidence = row.confidence as PlanningConfidence;
  const low = confidence.confidence_class === "low";
  if (confidence.confidence_kind !== KIND_BY_TIER[row.tier]) add("confidence_record_mismatch", "confidence.confidence_kind", `tier ${row.tier} carries ${KIND_BY_TIER[row.tier]} confidence`);
  let gr1 = false;
  if (confidence.confidence_kind === "declared") {
    if (SCORE_COMPONENTS.some((name) => row.components[name] === null)) add("component_mismatch", "components", "an engine row carries all five components");
  } else {
    gr1 = confidence.guardrail_gr1.applies;
    out.push(...derivedConfidenceProblems(overlay, row, confidence, where));
    out.push(...ruleRecordProblems(confidence, where));
    const flood = overlay.inputs.find((item) => item.input_id === row.lineage.flood_input_id);
    if (!flood || flood.role !== "flood_input" || flood.name !== row.flood_input) add("lineage_unresolved", "lineage.flood_input_id", "does not name the flood input of the row");
    else if (flood.acquisition_date !== confidence.measurements.acquisition_date) {
      add("confidence_record_mismatch", "confidence.measurements.acquisition_date", `is ${show(confidence.measurements.acquisition_date)}; the flood input record says ${show(flood.acquisition_date)}`);
    }
    const routing = overlay.inputs.find((item) => item.input_id === row.lineage.routing_context_id);
    if (!routing || routing.role !== "routing_context") add("lineage_unresolved", "lineage.routing_context_id", "does not name a routing context");
    const closureBasis = `${CLOSURE_BASIS_PREFIX}${row.lineage.flood_input_id}`;
    if (row.lineage.closure_rule?.closure_basis !== closureBasis) add("lineage_unresolved", "lineage.closure_rule.closure_basis", `the closure of a row is modelled from its own flood input (guardrail GR3): ${closureBasis}`);
    const exposure = row.components.exposure_0_100;
    if (isFrameRecord(exposure) && exposure.inputs.unit_residents !== confidence.measurements.unit_residents) {
      add("confidence_record_mismatch", "confidence.measurements.unit_residents", `is ${confidence.measurements.unit_residents}; the exposure record of the row counts ${exposure.inputs.unit_residents} unit residents. Guardrail GR1 and condition C6 are judged on the residents the row is scored on`);
    }
  }

  const values = SCORE_COMPONENTS.map((name) => {
    const record = row.components[name];
    if (record === null) return null;
    if (record.component !== name) add("component_mismatch", `components.${name}.component`, `is ${show(record.component)}`);
    if (!isFrameRecord(record)) {
      if (row.tier !== "T0") add("component_mismatch", `components.${name}`, "a synthetic value belongs to an engine row (tier T0)");
    } else {
      if (!sameJson(record.protocol_sha256, overlay.protocol_sha256)) add("protocol_hash_mismatch", `components.${name}.protocol_sha256`, "differs from $.protocol_sha256");
      const expected = record.component === name ? expectedFrameRecord(record) : null;
      if (expected === null) add("component_not_frame_record", `components.${name}`, "guardrail GR2: the protocol states no frame v1 value for the inputs the record echoes");
      else if (!sameJson(record, expected, MEASUREMENT_TOLERANCE)) {
        const fields = [...new Set([...Object.keys(record), ...Object.keys(expected)])].filter((key) => !sameJson((record as unknown as Record<string, unknown>)[key], expected[key], MEASUREMENT_TOLERANCE));
        add("component_not_frame_record", `components.${name}`, `guardrail GR2: the record is not the frame v1 record of the inputs it echoes; fields that differ: ${fields.sort().join(", ")}`);
      }
    }
    return record.value_0_100;
  });
  const complete = values.every((value) => value !== null);
  const byName = Object.fromEntries(SCORE_COMPONENTS.map((name, index) => [name, values[index] ?? 0])) as Record<ScoreComponent, number>;
  const weighted = (weights: ComponentWeights) => SCORE_COMPONENTS.reduce((sum, name) => sum + weights[name] * byName[name], 0);
  // The scorer states FPPS rounded to two decimals and compares that value with the class thresholds.
  const isFpps = (stated: number, weights: ComponentWeights) => Math.abs(stated - weighted(weights)) <= FPPS_TOLERANCE && Math.abs(stated * 100 - Math.round(stated * 100)) <= 1e-6;
  const loco = row.leave_one_component_out;
  const fpps = row.fpps_0_100;
  let scored = false;
  if (!complete) {
    if (fpps !== null || loco !== null) add("fpps_mismatch", "fpps_0_100", "a row with a component that is not computed has no FPPS and no leave-one-out");
  } else if (fpps === null || !isFpps(fpps, overlay.scoring_frame.weights)) {
    add("fpps_mismatch", "fpps_0_100", `is ${show(fpps)}; the frame weights give ${weighted(overlay.scoring_frame.weights).toFixed(2)}, rounded to two decimals`);
  } else {
    scored = true;
  }

  const reason = row.action_reason_code;
  if (gr1) {
    if (row.action_class !== null || reason !== "insufficient_denominator" || row.would_be_class !== null || row.class_v2?.result !== null || row.class_v2.trigger_evidence.length) {
      add("gr1_no_class", "action_class", "guardrail GR1: no binding class, no would-be class and no v2 class; reason insufficient_denominator");
    }
  } else {
    if (row.action_class === null || reason === "insufficient_denominator") add("gr1_no_class", "action_class", `in schema ${PLANNING_OVERLAY_SCHEMA_VERSION} every row below tier T4 carries a class, and only a unit under guardrail GR1 has none`);
    if (low) {
      if (row.action_class !== "E" || reason !== "low_confidence") add("low_confidence_forces_e", "action_class", "low confidence gives binding class E, reason low_confidence");
    } else if (row.action_class !== null) {
      const expected = row.action_class === "E" ? "low_priority_score" : REASON_BY_CLASS[row.action_class];
      if (reason !== expected) add("reason_code_mismatch", "action_reason_code", `is ${show(reason)}; class ${row.action_class} carries ${expected}`);
      if (scored && fpps !== null) {
        const ruled = classByRuleV1(byName, fpps, confidence.confidence_class);
        if (row.action_class !== ruled) add("class_rule_mismatch", "action_class", `is ${show(row.action_class)}; class rule v1 gives ${show(ruled)}`);
      }
    }
  }
  const expectedWouldBe = low && !gr1 && scored && fpps !== null ? classByRuleV1(byName, fpps, "medium") : null;
  if ((row.would_be_class !== null) !== (low && !gr1 && complete) || (scored && row.would_be_class !== expectedWouldBe)) {
    add("would_be_class_mismatch", "would_be_class", `is ${show(row.would_be_class)}; the scorer rerun with confidence medium gives ${show(expectedWouldBe)} (a would-be class exists for low-confidence rows only and is never binding)`);
  }

  if (complete && loco !== null) {
    for (const dropped of SCORE_COMPONENTS) {
      const entry = loco[dropped];
      const weights = overlay.scoring_frame.leave_one_component_out_weights[dropped];
      const expectedClass = gr1 || !isFpps(entry.fpps_0_100, weights) ? null : classByRuleV1(byName, entry.fpps_0_100, confidence.confidence_class);
      if (!isFpps(entry.fpps_0_100, weights) || entry.action_class !== expectedClass) {
        add("leave_one_component_out_mismatch", `leave_one_component_out.${dropped}`, `expected an FPPS of ${weighted(weights).toFixed(2)} and ${gr1 ? "no class" : `the class rule v1 gives it${expectedClass ? ` (${expectedClass})` : ""}`}`);
      }
    }
  } else if (complete) {
    add("leave_one_component_out_mismatch", "leave_one_component_out", "is required on every row that has an FPPS");
  }

  if (row.tier !== "T0" && !gr1 && row.class_v2) {
    const exposureIndex = SCORE_COMPONENTS.indexOf("exposure_0_100");
    const wrong = classV2Problems(row, row.class_v2, low, values[exposureIndex]);
    if (wrong.length) add("v2_result_inconsistent", "class_v2", wrong.join("; "));
  }

  const headline = row.headline_stability;
  const expectedStatus: HeadlineStatus = headline.class_retention === null ? "not_evaluated" : headline.class_retention >= headline.class_retention_min ? "headline_eligible" : "unstable_verify";
  if (headline.status !== expectedStatus || (row.action_class === null && headline.status !== "not_evaluated")) {
    add("headline_stability_inconsistent", "headline_stability", `status ${headline.status} with retention ${show(headline.class_retention)} and class ${show(row.action_class)} (guardrail GR8)`);
  }
  return out;
}

/** The hashes and the frame header against the protocols in force. */
function protocolProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  if (!sameJson(overlay.protocol_sha256, BINDING.protocol_sha256)) out.push({ code: "protocol_not_in_force", path: "$.protocol_sha256", message: "is not the SHA-256 of the protocol files in force" });
  if (!sameJson(overlay.scoring_frame, BINDING.scoring_frame)) out.push({ code: "frame_not_protocol_frame", path: "$.scoring_frame", message: "is not the frame v1 header of the protocols in force" });
  return out;
}

/** Every name protocol v1a gives the flood inputs of a case: its `flood_inputs` and, for a product 4009 case, the layer names. */
export function caseFloodInputNames(protocolCase: ProtocolCase): string[] {
  const names = [...protocolCase.flood_inputs];
  for (const layerNames of [PRODUCT_4009.accumulated_names, PRODUCT_4009.dated_names]) {
    if (names.some((name) => layerNames.includes(name))) names.push(...layerNames);
  }
  return [...new Set(names)];
}

/**
 * The case header and the rows of its own lane against protocol v1a `case_portfolio`. Rows in lane SCN (scenario
 * cells built on a base case), engine rows and the T4 placeholder are not compared: the protocols do not say which
 * overlay carries them.
 */
function caseProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (path: string, message: string) => out.push({ code: "case_not_protocol_case", path, message });
  const caseId = overlay.case.case_id;
  const known = BINDING.cases.find((item) => item.id === caseId);
  const cut = BINDING.cut_cases.includes(caseId);
  if (overlay.case.kind !== "portfolio_case") {
    if (known || cut) add("$.case.case_id", `a fixture does not carry the id of protocol case ${show(caseId)}`);
    return out;
  }
  if (!known) {
    add("$.case.case_id", `${show(caseId)}${cut ? ", which v1a cut (case_portfolio.cut_now)" : ""} is not a case of protocol v1a case_portfolio`);
    return out;
  }
  if (BINDING.cases_without_class.includes(caseId)) {
    add("$.case.case_id", `v1a gives case ${caseId} flood likelihood and exposure only, no FPPS and no class; schema ${PLANNING_OVERLAY_SCHEMA_VERSION} does not carry it`);
    return out;
  }
  if (overlay.case.case_reference_date !== known.case_reference_date) add("$.case.case_reference_date", `is ${show(overlay.case.case_reference_date)}; v1a gives case ${caseId} ${show(known.case_reference_date)}`);
  const names = caseFloodInputNames(known);
  overlay.rows.forEach((row, index) => {
    if (row.lane !== "OBS" && row.lane !== "SCN-ENV") return;
    const where = `$.rows[${index}]`;
    if (row.lane !== known.lane) return void add(`${where}.lane`, `v1a gives case ${caseId} lane ${known.lane}, not a ${row.lane} row`);
    if (row.tier !== known.tier) add(`${where}.tier`, `v1a places case ${caseId} at tier ${known.tier}`);
    if (row.flood_input === null || !names.includes(row.flood_input)) add(`${where}.flood_input`, `${show(row.flood_input)} is not a flood input v1a gives case ${caseId}: ${names.join("; ")}`);
  });
  return out;
}

/**
 * A product 4009 flood input is one of the two layers protocol v1a names (`date_rule.product_4009`): the accumulated
 * layer has no single acquisition date and is used in lane SCN-ENV only, and the 22 Oct layer carries its own date.
 */
function product4009LayerProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (path: string, message: string) => out.push({ code: "product_4009_layer_not_protocol_layer", path, message });
  const accumulated = new Set<string>();
  overlay.inputs.forEach((item, index) => {
    if (item.role !== "flood_input" || !declaresProduct4009(item)) return;
    const where = `$.inputs[${index}]`;
    if (PRODUCT_4009.accumulated_names.includes(item.name)) {
      accumulated.add(item.input_id);
      if (item.acquisition_date !== null) add(`${where}.acquisition_date`, "the accumulated layer has no per-patch dates: it has no single acquisition date");
    } else if (PRODUCT_4009.dated_names.includes(item.name)) {
      if (item.acquisition_date !== PRODUCT_4009.dated_acquisition_date) add(`${where}.acquisition_date`, `v1a dates the 22 Oct layer ${PRODUCT_4009.dated_acquisition_date}`);
    } else {
      add(`${where}.name`, `a product 4009 flood input carries one of the names v1a gives its two layers: ${[...PRODUCT_4009.accumulated_names, ...PRODUCT_4009.dated_names].join("; ")}`);
    }
  });
  overlay.rows.forEach((row, index) => {
    if (row.lineage.flood_input_id !== null && accumulated.has(row.lineage.flood_input_id) && row.lane !== "SCN-ENV") add(`$.rows[${index}].lane`, "v1a uses the accumulated layer in lane SCN-ENV only (scenario only)");
  });
  return out;
}

/** Every reason `value` is refused as a planning assessment overlay; an empty list means it is accepted. */
export function planningOverlayProblems(value: unknown): PlanningOverlayProblem[] {
  if (!isRecord(value)) return [{ code: "structure", path: "$", message: "the overlay must be a JSON object" }];
  const structure: PlanningOverlayProblem[] = [];
  shapeProblems(value, PLANNING_OVERLAY_SHAPE, "$", structure);
  const overlay = value as unknown as PlanningAssessmentOverlay;
  try {
    structure.push(...conditionalShapeProblems(overlay));
  } catch (error) {
    // The conditional shape reads fields the shape problems already report as wrong.
    if (structure.length === 0) throw error;
  }
  const problems = [...guardProblems(value), ...structure];
  const checks: (() => PlanningOverlayProblem[])[] = [
    () => overlayLevelProblems(overlay),
    ...(Array.isArray(overlay.rows) ? overlay.rows.map((row, index) => () => rowProblems(overlay, row, `$.rows[${index}]`)) : []),
    () => protocolProblems(overlay),
    () => caseProblems(overlay),
    () => product4009LayerProblems(overlay),
  ];
  for (const check of checks) {
    try {
      problems.push(...check());
    } catch (error) {
      // A malformed overlay can break a cross-field check. The structure problems already say why.
      if (structure.length === 0) throw error;
    }
  }
  const seen = new Set<string>();
  return problems.filter((item) => {
    const key = `${item.code}|${item.path}|${item.message}`;
    return seen.has(key) ? false : (seen.add(key), true);
  });
}

/** Parse a planning assessment overlay, or throw `PlanningOverlayError` with every reason it is refused. */
export function parsePlanningAssessmentOverlay(value: unknown): PlanningAssessmentOverlay {
  const problems = planningOverlayProblems(value);
  if (problems.length) throw new PlanningOverlayError(problems);
  return value as PlanningAssessmentOverlay;
}

// --- Summary ----------------------------------------------------------------------------------------------------

type Counts = Record<string, number>;
const countBy = (keys: readonly string[], values: readonly (string | null)[]): Counts => {
  const out: Counts = Object.fromEntries([...keys, "none"].map((key) => [key, 0]));
  for (const value of values) out[value ?? "none"] += 1;
  return out;
};
const countByColumn = (rows: readonly PlanningOverlayRow[], keys: readonly string[], value: (row: PlanningOverlayRow) => string | null): Record<LaneColumn, Counts> =>
  Object.fromEntries(LANE_COLUMNS.map((column) => [column, countBy(keys, rows.filter((row) => laneColumn(row.lane) === column).map(value))])) as Record<LaneColumn, Counts>;

export interface PlanningOverlaySummary {
  case_id: string;
  dataset_mode: string;
  publication_eligibility: PublicationLevel;
  protocol_sha256: ProtocolSha256;
  row_count: number;
  unit_count: number;
  rows_by_tier: Counts;
  rows_by_lane: Counts;
  rows_by_temporal_relation: Counts;
  rows_by_confidence_kind: Counts;
  confidence_class_by_lane_column: Record<LaneColumn, Counts>;
  binding_class_by_lane_column: Record<LaneColumn, Counts>;
  reason_code_by_lane_column: Record<LaneColumn, Counts>;
  would_be_class_by_lane_column: Record<LaneColumn, Counts>;
  v2_result_by_lane_column: Record<LaneColumn, Counts>;
  headline_status_by_lane_column: Record<LaneColumn, Counts>;
  failed_conditions_by_lane_column: Record<"OBS" | "SCN", Counts>;
  basis_values_by_lane_column: Record<"OBS" | "SCN", Counts>;
  rows_under_gr1: number;
  rows_without_fpps: number;
  obs_rows_not_event_aligned: number;
  inputs_by_rights_level: Counts;
}

/**
 * Count what an accepted overlay holds: rows by tier and lane, and classes and confidence per lane column. Classes,
 * reason codes and confidence are counted per column (OBS, SCN with SCN-ENV, ENG, and `no_lane` for tier T4) and never
 * across them: protocol v1a counts scenario classes only in the SCN column, never counts engine classes as an observed
 * or scenario distribution, and never counts scenario confidence as observed confidence. The Python side
 * (`floodguard.planning_overlay.summarise_overlay`) counts the same things, so a test can show both read the same file.
 */
export function summarisePlanningAssessmentOverlay(overlay: PlanningAssessmentOverlay): PlanningOverlaySummary {
  const rows = overlay.rows;
  const derivedRows = rows.filter((row) => row.confidence !== null && row.confidence.confidence_kind !== "declared");
  const derivedColumns = ["OBS", "SCN"] as const;
  const failed = Object.fromEntries(derivedColumns.map((column) => [column, Object.fromEntries(CONFIDENCE_CONDITION_IDS.map((name) => [name, 0]))])) as Record<"OBS" | "SCN", Counts>;
  const basis = Object.fromEntries(derivedColumns.map((column) => [column, Object.fromEntries(CONFIDENCE_BASIS_VALUES.map((name) => [name, 0]))])) as Record<"OBS" | "SCN", Counts>;
  for (const row of derivedRows) {
    const column = laneColumn(row.lane) as "OBS" | "SCN";
    const record = row.confidence as DerivedConfidence;
    for (const name of record.failed_conditions) failed[column][name] += 1;
    for (const value of Object.values(record.basis)) basis[column][value] += 1;
  }
  return {
    case_id: overlay.case.case_id,
    dataset_mode: overlay.dataset_mode,
    publication_eligibility: overlay.publication_eligibility,
    protocol_sha256: { ...overlay.protocol_sha256 },
    row_count: rows.length,
    unit_count: new Set(rows.map((row) => row.unit_id)).size,
    rows_by_tier: countBy(EVIDENCE_TIERS, rows.map((row) => row.tier)),
    rows_by_lane: countBy(PLANNING_LANES, rows.map((row) => row.lane)),
    rows_by_temporal_relation: countBy(TEMPORAL_RELATIONS, rows.map((row) => row.temporal_relation)),
    rows_by_confidence_kind: countBy(CONFIDENCE_KINDS, rows.map((row) => row.confidence?.confidence_kind ?? null)),
    confidence_class_by_lane_column: countByColumn(rows, ASSIGNED_CONFIDENCE_CLASSES, (row) => row.confidence?.confidence_class ?? null),
    binding_class_by_lane_column: countByColumn(rows, PLANNING_ACTION_CLASSES, (row) => row.action_class),
    reason_code_by_lane_column: countByColumn(rows, PLANNING_REASON_CODES, (row) => row.action_reason_code),
    would_be_class_by_lane_column: countByColumn(rows, PLANNING_ACTION_CLASSES, (row) => row.would_be_class),
    v2_result_by_lane_column: countByColumn(rows, [...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER, V2_NOT_EVALUATED], (row) => row.class_v2?.result ?? null),
    headline_status_by_lane_column: countByColumn(rows, HEADLINE_STATUSES, (row) => row.headline_stability.status),
    failed_conditions_by_lane_column: failed,
    basis_values_by_lane_column: basis,
    rows_under_gr1: derivedRows.filter((row) => (row.confidence as DerivedConfidence).guardrail_gr1.applies).length,
    rows_without_fpps: rows.filter((row) => row.fpps_0_100 === null).length,
    obs_rows_not_event_aligned: rows.filter((row) => row.lane === "OBS" && row.temporal_relation !== "event_aligned").length,
    inputs_by_rights_level: countBy(PUBLICATION_LEVELS, overlay.inputs.map((item) => item.rights_level)),
  };
}
