/**
 * Planning assessment overlay: the typed shape and the strict parser of the file the planning engine writes for one
 * case and every screen reads (restructuring plan v2, section 7.1, task E11). The JSON schema is
 * `packages/contracts/schemas/planning-assessment-overlay.schema.json`; the Python side is
 * `src/floodguard/planning_overlay.py`, and both sides use the same refusal codes.
 *
 * One row is one unit in one lane with one flood input. The component and confidence records are the ones
 * `normalisation.py` and `confidence.py` return under the signed planning protocols v1a and v1b. The parser refuses
 * what the protocols forbid: an unknown tier, a class above E without medium confidence, a non-null `accepted_fpps`
 * or `accepted_action_class`, an OBS row that is not event_aligned with a binding class above E (guardrail GR7), a
 * class for a unit with fewer than 100 residents (guardrail GR1), a value on the locked tier T4, a v2 class shown as
 * binding, a rights level above the minimum of the lineage (guardrail GR6), and an FPPS that is not the weighted sum
 * of its components. It does not recompute the A-E class from the class rule: the Python validator does that with
 * the scorer.
 *
 * An overlay is planning guidance for preparedness and post-event prioritisation. It is not an official warning, and
 * class E never means safe.
 */

export const PLANNING_OVERLAY_SCHEMA_ID = "https://floodguard.th/contracts/planning-assessment-overlay.schema.json" as const;
export const PLANNING_OVERLAY_SCHEMA_VERSION = "1.0" as const;

export const EVIDENCE_TIERS = ["T0", "T1", "T2", "T3", "T4"] as const;
export type EvidenceTier = (typeof EVIDENCE_TIERS)[number];
/** Tier T4 (qualified) is locked in this release: a T4 row is a placeholder and carries no value. */
export const LOCKED_TIER = "T4" as const satisfies EvidenceTier;

export const PLANNING_LANES = ["OBS", "SCN", "SCN-ENV", "ENG"] as const;
export type PlanningLane = (typeof PLANNING_LANES)[number];

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
export type ClassV2Result = PlanningActionClass | typeof NO_V2_TRIGGER;

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

export const PRODUCT_4009_LICENCE = "CC BY-SA 4.0";
export const PRODUCT_4009_CREDIT = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009";

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
  "reason_code_mismatch",
  "would_be_class_mismatch",
  "v2_result_inconsistent",
  "leave_one_component_out_mismatch",
  "headline_stability_inconsistent",
  "lineage_unresolved",
  "publication_eligibility_not_lineage_minimum",
  "product_4009_licence_missing",
  "protocol_hash_mismatch",
  "scoring_frame_inconsistent",
  "duplicate_id",
  "fixture_label_missing",
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

export type T2SkillConditionId =
  | "geoid_held_out_test_iou_min"
  | "mae_sai_abstention_fraction_max"
  | "mae_sai_unit_coverage_min"
  | "recency_window_days";

/** As `floodguard.confidence.t2_skill_condition` returns it. */
export interface T2SkillCondition {
  flood_input: string;
  status: "declared_unable_to_meet" | "not_evaluated_by_the_rule" | "evaluated";
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
  measurements: {
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
  };
  thresholds: {
    recency_window_days: number;
    unit_valid_coverage_min: number;
    exposure_plus_minus_one_pixel_max_points: number;
    exposure_plus_minus_one_pixel_float_guard_points: number;
    t2_abstention_fraction_max: number;
    unit_residents_min: number;
    baseline_vehicle_no_route_share_max: number;
    hospitals_reachable_at_baseline_min: number;
  };
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
  /** A flood intersection does not prove a road closure. */
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
  met: boolean;
  evidence: string;
}

/** Class rule v2: a predeclared secondary axis, never binding (decision D6). */
export interface ClassV2 {
  class_rule_version: "class_rule_v2";
  label: "secondary";
  binding: false;
  /** `no_v2_trigger` is shown as "no v2 trigger met"; `null` says the unit gets no v2 class (guardrail GR1). */
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

// --- Shape ------------------------------------------------------------------------------------------------------
// The shape below mirrors the JSON schema node for node; a unit test compares the two, so they cannot drift apart.

export type OverlaySpec =
  | { k: "text" }
  | { k: "string" }
  | { k: "pattern"; source: string }
  | { k: "number"; min?: number; max?: number; exclusiveMax?: number; integer?: boolean }
  | { k: "boolean" }
  | { k: "null" }
  | { k: "const"; value: string | number | boolean }
  | { k: "enum"; values: readonly (string | null)[] }
  | { k: "array"; items: OverlaySpec; minItems?: number; maxItems?: number; unique?: boolean }
  | { k: "object"; name?: string; fields: Record<string, OverlaySpec> }
  | { k: "map"; values: OverlaySpec; keyPattern?: string; minProperties?: number }
  | { k: "oneOf"; options: OverlaySpec[] };

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
const ISO_DATE: OverlaySpec = { k: "pattern", source: "^[0-9]{4}-[0-9]{2}-[0-9]{2}$" };
const INSTANT: OverlaySpec = {
  k: "pattern",
  source: "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$",
};
const INPUT_ID: OverlaySpec = { k: "pattern", source: "^[a-z0-9][a-z0-9_.-]{1,63}$" };
const constant = (value: string | number | boolean): OverlaySpec => ({ k: "const", value });
const oneOfValues = (values: readonly (string | null)[]): OverlaySpec => ({ k: "enum", values });
const nullable = (spec: OverlaySpec): OverlaySpec => ({ k: "oneOf", options: [spec, NULL] });
const object = (fields: Record<string, OverlaySpec>, name?: string): OverlaySpec => ({ k: "object", name, fields });
const list = (items: OverlaySpec, limits: { minItems?: number; maxItems?: number; unique?: boolean } = {}): OverlaySpec => ({ k: "array", items, ...limits });
const perComponent = (spec: (name: ScoreComponent) => OverlaySpec): Record<string, OverlaySpec> =>
  Object.fromEntries(SCORE_COMPONENTS.map((name) => [name, spec(name)]));

const SKILL_CONDITIONS: readonly T2SkillConditionId[] = [
  "geoid_held_out_test_iou_min",
  "mae_sai_abstention_fraction_max",
  "mae_sai_unit_coverage_min",
  "recency_window_days",
];
const ACTION_CLASS = oneOfValues(PLANNING_ACTION_CLASSES);
const ASSUMPTIONS = list(TEXT, { minItems: 1, unique: true });
const PROTOCOL_SHA256 = object({ v1a: SHA256, v1b: SHA256 }, "protocolSha256");
const WEIGHTS = object(perComponent(() => SHARE), "weights");
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
  conditions: object(Object.fromEntries(SKILL_CONDITIONS.map((name) => [name, oneOfValues(["pass", "fail"])]))),
  failed_conditions: list(oneOfValues(SKILL_CONDITIONS), { unique: true }),
  measurements: object({
    geoid_held_out_test_iou: nullable(SHARE),
    abstention_fraction: nullable(SHARE),
    unit_valid_coverage: nullable(SHARE),
    recency_days: nullable(WHOLE_FROM_0),
  }),
  thresholds: object(Object.fromEntries(SKILL_CONDITIONS.map((name) => [name, COUNT]))),
  metric_wording: TEXT,
  protocol_v1a_sha256: SHA256,
}, "t2SkillCondition");

const DERIVED_CONFIDENCE = object({
  unit_id: TEXT,
  lane: oneOfValues(["OBS", "SCN", "SCN-ENV"]),
  tier: oneOfValues(["T1", "T2", "T3"]),
  flood_input: STRING,
  scenario_base: oneOfValues(["agency_product_as_provided", "own_t2_candidate", null]),
  confidence_rule_version: constant("confidence_rule_v1"),
  confidence_class: oneOfValues(ASSIGNED_CONFIDENCE_CLASSES),
  confidence_kind: oneOfValues(["observed", "scenario"]),
  basis: object(Object.fromEntries(CONFIDENCE_CONDITION_IDS.map((name) => [name, oneOfValues(CONFIDENCE_BASIS_VALUES)]))),
  failed_conditions: list(oneOfValues(CONFIDENCE_CONDITION_IDS), { unique: true }),
  reason_code: oneOfValues(["low_confidence", "insufficient_denominator", null]),
  guardrail_gr1: object({
    id: constant("GR1_minimum_denominators"),
    applies: BOOLEAN,
    unit_residents_min_for_class: COUNT,
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
  thresholds: object({
    recency_window_days: COUNT,
    unit_valid_coverage_min: COUNT,
    exposure_plus_minus_one_pixel_max_points: COUNT,
    exposure_plus_minus_one_pixel_float_guard_points: COUNT,
    t2_abstention_fraction_max: COUNT,
    unit_residents_min: COUNT,
    baseline_vehicle_no_route_share_max: COUNT,
    hospitals_reachable_at_baseline_min: COUNT,
  }),
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
    result: oneOfValues([...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER, null]),
    trigger_evidence: list(object({ trigger: ACTION_CLASS, met: BOOLEAN, evidence: TEXT }, "triggerEvidence"), { maxItems: 5 }),
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
    weights: WEIGHTS,
    flood_anchor: SHARE,
    flood_anchor_sensitivity_one_at_a_time: list(SHARE),
    flood_anchor_disclosure: TEXT,
    permanent_water: PERMANENT_WATER,
    exposure_kind: constant("share_only"),
    access_services: list(object({ service: TEXT, mode: TEXT, threshold_minutes: WHOLE_FROM_1, level: oneOfValues(["public", "pitch"]) }, "accessService"), { minItems: 1 }),
    vulnerability_anchor_version: constant("national_vulnerability_anchors_v1"),
    vulnerability_anchors: object({ lower: TEXT, upper: TEXT, values: { k: "map", values: SHARE, keyPattern: "^P[0-9]{1,2}$", minProperties: 2 } }),
    vulnerability_anchor_sensitivity: object({ lower: TEXT, upper: TEXT }),
    vulnerability_anchor_receipt_sha256: SHA256,
    leave_one_component_out_weights: object(perComponent(() => WEIGHTS)),
    lane_disclosure: TEXT,
    protocol_sha256: PROTOCOL_SHA256,
  }, "scoringFrame"),
  publication_eligibility: oneOfValues(PUBLICATION_LEVELS),
  inputs: list(object({
    input_id: INPUT_ID,
    role: oneOfValues(INPUT_ROLES),
    name: TEXT,
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
const PRODUCT_4009_CITATION = /(?:unosat|product)[-_ /A-Za-z]{0,20}?4009(?![0-9])/i;
const FIXTURE_LABEL = "not a place";

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

/** The parts of the JSON schema that depend on another field: what each tier and each case kind must carry. */
function conditionalShapeProblems(overlay: PlanningAssessmentOverlay): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const fail = (path: string, message: string) => out.push({ code: "structure", path, message });
  const fixture = overlay.case.kind === "fixture";
  if ((overlay.dataset_mode === "fixture_demo") !== fixture) fail("$.case.kind", "a fixture_demo overlay holds a fixture case, and only it does");
  if (fixture ? !(typeof overlay.case.fixture_notice === "string" && overlay.case.fixture_notice.includes(FIXTURE_LABEL)) : overlay.case.fixture_notice !== null) {
    fail("$.case.fixture_notice", `a fixture case says '${FIXTURE_LABEL}'; a portfolio case carries null`);
  }
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
  const same = (left: ProtocolSha256, right: ProtocolSha256) => left.v1a === right.v1a && left.v1b === right.v1b;
  if (!same(overlay.scoring_frame.protocol_sha256, overlay.protocol_sha256)) out.push({ code: "protocol_hash_mismatch", path: "$.scoring_frame.protocol_sha256", message: "differs from $.protocol_sha256" });
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
    if (![item.input_id, item.name, item.attribution].some((text) => PRODUCT_4009_CITATION.test(text))) return;
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

function derivedConfidenceProblems(overlay: PlanningAssessmentOverlay, row: PlanningOverlayRow, record: DerivedConfidence, where: string): PlanningOverlayProblem[] {
  const out: PlanningOverlayProblem[] = [];
  const add = (code: PlanningOverlayRefusalCode, field: string, message: string) => out.push({ code, path: `${where}.confidence.${field}`, message });
  for (const name of ["unit_id", "lane", "tier", "flood_input"] as const) {
    if (record[name] !== row[name]) add("confidence_record_mismatch", name, `is ${show(record[name])}; the row says ${show(row[name])}`);
  }
  if ((record.scenario_base !== null) !== (row.tier === "T1")) add("confidence_record_mismatch", "scenario_base", "a scenario base is named for tier T1 rows only");
  if (record.protocol_v1a_sha256 !== overlay.protocol_sha256.v1a) add("protocol_hash_mismatch", "protocol_v1a_sha256", "differs from $.protocol_sha256.v1a");
  const failed = CONFIDENCE_CONDITION_IDS.filter((name) => record.basis[name] === "fail");
  if (record.failed_conditions.join() !== failed.join()) add("confidence_record_mismatch", "failed_conditions", `the basis record fails ${show(failed)}`);
  const expectedClass = failed.length ? "low" : "medium";
  if (record.confidence_class !== expectedClass) add("confidence_record_mismatch", "confidence_class", `the basis record gives ${expectedClass}`);
  const gr1 = record.guardrail_gr1;
  if (gr1.applies !== record.measurements.unit_residents < gr1.unit_residents_min_for_class) add("gr1_no_class", "guardrail_gr1.applies", "does not follow from the unit residents");
  if ([gr1.no_binding_class, gr1.no_would_be_class, gr1.no_v2_class].some((flag) => flag !== gr1.applies)) add("gr1_no_class", "guardrail_gr1", "no binding class, no would-be class and no v2 class go together");
  if (gr1.applies && !failed.includes("C6_residents")) add("gr1_no_class", "failed_conditions", "a unit under guardrail GR1 fails condition C6");
  const expectedReason = gr1.applies ? "insufficient_denominator" : failed.length ? "low_confidence" : null;
  if (record.reason_code !== expectedReason) add("confidence_record_mismatch", "reason_code", `is ${show(record.reason_code)}, expected ${show(expectedReason)}`);
  for (const name of SCORE_COMPONENTS) {
    const status = record.measurements.component_status[name];
    if (status === "assumed") out.push({ code: "assumed_component_in_a_row", path: `${where}.confidence.measurements.component_status.${name}`, message: "no case row and no scenario cell carries an assumed component (drafter reading DR-A05)" });
    if ((row.components[name] !== null) !== (status === "computed")) out.push({ code: "component_mismatch", path: `${where}.components.${name}`, message: `the confidence record says ${status}; a record is present only for a computed component` });
  }
  if (row.lane === "OBS" && record.measurements.case_reference_date !== overlay.case.case_reference_date) {
    add("confidence_record_mismatch", "measurements.case_reference_date", "an OBS row is judged against the reference date of its case");
  }
  if (row.lane === "OBS" && (row.temporal_relation === "event_aligned") !== (record.basis.C2_recency === "pass")) {
    out.push({ code: "temporal_relation_mismatch", path: `${where}.temporal_relation`, message: "an input is event_aligned only when its acquisition is inside the recency window (condition C2)" });
  }
  return out;
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
    const flood = overlay.inputs.find((item) => item.input_id === row.lineage.flood_input_id);
    if (!flood || flood.role !== "flood_input" || flood.name !== row.flood_input) add("lineage_unresolved", "lineage.flood_input_id", "does not name the flood input of the row");
    const routing = overlay.inputs.find((item) => item.input_id === row.lineage.routing_context_id);
    if (!routing || routing.role !== "routing_context") add("lineage_unresolved", "lineage.routing_context_id", "does not name a routing context");
  }

  const values = SCORE_COMPONENTS.map((name) => {
    const record = row.components[name];
    if (record === null) return null;
    if (record.component !== name) add("component_mismatch", `components.${name}.component`, `is ${show(record.component)}`);
    if ("synthetic" in record) {
      if (row.tier !== "T0") add("component_mismatch", `components.${name}`, "a synthetic value belongs to an engine row (tier T0)");
    } else if (record.protocol_sha256.v1a !== overlay.protocol_sha256.v1a || record.protocol_sha256.v1b !== overlay.protocol_sha256.v1b) {
      add("protocol_hash_mismatch", `components.${name}.protocol_sha256`, "differs from $.protocol_sha256");
    }
    return record.value_0_100;
  });
  const complete = values.every((value) => value !== null);
  const weighted = (weights: ComponentWeights) => SCORE_COMPONENTS.reduce((sum, name, index) => sum + weights[name] * (values[index] ?? 0), 0);
  const loco = row.leave_one_component_out;
  if (!complete) {
    if (row.fpps_0_100 !== null || loco !== null) add("fpps_mismatch", "fpps_0_100", "a row with a component that is not computed has no FPPS and no leave-one-out");
  } else if (row.fpps_0_100 === null || Math.abs(row.fpps_0_100 - weighted(overlay.scoring_frame.weights)) > FPPS_TOLERANCE) {
    add("fpps_mismatch", "fpps_0_100", `is ${show(row.fpps_0_100)}; the frame weights give ${weighted(overlay.scoring_frame.weights).toFixed(2)}`);
  }

  const reason = row.action_reason_code;
  if (gr1) {
    if (row.action_class !== null || reason !== "insufficient_denominator" || row.would_be_class !== null || row.class_v2?.result !== null || row.class_v2.trigger_evidence.length) {
      add("gr1_no_class", "action_class", "guardrail GR1: no binding class, no would-be class and no v2 class; reason insufficient_denominator");
    }
  } else {
    if (row.action_class === null || reason === "insufficient_denominator") add("gr1_no_class", "action_class", "only a unit under guardrail GR1 has no class");
    if (low) {
      if (row.action_class !== "E" || reason !== "low_confidence") add("low_confidence_forces_e", "action_class", "low confidence gives binding class E, reason low_confidence");
    } else if (row.action_class !== null) {
      const expected = row.action_class === "E" ? "low_priority_score" : REASON_BY_CLASS[row.action_class];
      if (reason !== expected) add("reason_code_mismatch", "action_reason_code", `is ${show(reason)}; class ${row.action_class} carries ${expected}`);
    }
  }
  if ((row.would_be_class !== null) !== (low && !gr1 && complete)) {
    add("would_be_class_mismatch", "would_be_class", "a would-be class exists for low-confidence rows only (the scorer rerun with confidence medium) and is never binding");
  }

  if (complete && loco !== null) {
    for (const dropped of SCORE_COMPONENTS) {
      const entry = loco[dropped];
      const expected = weighted(overlay.scoring_frame.leave_one_component_out_weights[dropped]);
      if (Math.abs(entry.fpps_0_100 - expected) > FPPS_TOLERANCE || (entry.action_class === null) !== gr1 || (low && !gr1 && entry.action_class !== "E")) {
        add("leave_one_component_out_mismatch", `leave_one_component_out.${dropped}`, `expected an FPPS of ${expected.toFixed(2)} and ${gr1 ? "no class" : low ? "class E" : "a class"}`);
      }
    }
  } else if (complete) {
    add("leave_one_component_out_mismatch", "leave_one_component_out", "is required on every row that has an FPPS");
  }

  if (row.tier !== "T0" && !gr1 && row.class_v2) {
    const order = row.class_v2.trigger_evidence.map((item) => item.trigger);
    const firstMet = row.class_v2.trigger_evidence.find((item) => item.met)?.trigger ?? NO_V2_TRIGGER;
    const wrong: string[] = [];
    if (order.join() !== V2_TRIGGER_ORDER.join()) wrong.push(`trigger_evidence lists ${show(order)}, not ${show(V2_TRIGGER_ORDER)}`);
    else if (row.class_v2.result !== firstMet) wrong.push(`result is ${show(row.class_v2.result)}; the first trigger met gives ${show(firstMet)}`);
    if (low && row.class_v2.result !== "E") wrong.push("low confidence gives v2 class E");
    if (wrong.length) add("v2_result_inconsistent", "class_v2", wrong.join("; "));
  }

  const headline = row.headline_stability;
  const expectedStatus: HeadlineStatus = headline.class_retention === null ? "not_evaluated" : headline.class_retention >= headline.class_retention_min ? "headline_eligible" : "unstable_verify";
  if (headline.status !== expectedStatus || (row.action_class === null && headline.status !== "not_evaluated")) {
    add("headline_stability_inconsistent", "headline_stability", `status ${headline.status} with retention ${show(headline.class_retention)} and class ${show(row.action_class)} (guardrail GR8)`);
  }
  return out;
}

/** Every reason `value` is refused as a planning assessment overlay; an empty list means it is accepted. */
export function planningOverlayProblems(value: unknown): PlanningOverlayProblem[] {
  if (!isRecord(value)) return [{ code: "structure", path: "$", message: "the overlay must be a JSON object" }];
  const structure: PlanningOverlayProblem[] = [];
  shapeProblems(value, PLANNING_OVERLAY_SHAPE, "$", structure);
  const problems = [...guardProblems(value), ...structure];
  const overlay = value as unknown as PlanningAssessmentOverlay;
  const checks: (() => PlanningOverlayProblem[])[] = [
    () => conditionalShapeProblems(overlay),
    () => overlayLevelProblems(overlay),
    ...(Array.isArray(overlay.rows) ? overlay.rows.map((row, index) => () => rowProblems(overlay, row, `$.rows[${index}]`)) : []),
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

const countBy = (keys: readonly string[], values: readonly (string | null)[]): Record<string, number> => {
  const out: Record<string, number> = Object.fromEntries([...keys, "none"].map((key) => [key, 0]));
  for (const value of values) out[value ?? "none"] += 1;
  return out;
};

export interface PlanningOverlaySummary {
  case_id: string;
  dataset_mode: string;
  publication_eligibility: PublicationLevel;
  protocol_sha256: ProtocolSha256;
  row_count: number;
  unit_count: number;
  rows_by_tier: Record<string, number>;
  rows_by_lane: Record<string, number>;
  rows_by_temporal_relation: Record<string, number>;
  rows_by_confidence_class: Record<string, number>;
  rows_by_confidence_kind: Record<string, number>;
  rows_by_binding_class: Record<string, number>;
  rows_by_reason_code: Record<string, number>;
  rows_by_would_be_class: Record<string, number>;
  rows_by_v2_result: Record<string, number>;
  rows_by_headline_status: Record<string, number>;
  failed_condition_counts: Record<string, number>;
  basis_value_counts: Record<string, number>;
  rows_under_gr1: number;
  rows_without_fpps: number;
  obs_rows_not_event_aligned: number;
  inputs_by_rights_level: Record<string, number>;
}

/**
 * Count what an accepted overlay holds: rows by tier, lane, class, reason code and guardrail outcome. The Python side
 * (`floodguard.planning_overlay.summarise_overlay`) counts the same things, so a test can show both read the same file.
 */
export function summarisePlanningAssessmentOverlay(overlay: PlanningAssessmentOverlay): PlanningOverlaySummary {
  const rows = overlay.rows;
  const derived = rows.map((row) => row.confidence).filter((record): record is DerivedConfidence => record !== null && record.confidence_kind !== "declared");
  const failed: Record<string, number> = Object.fromEntries(CONFIDENCE_CONDITION_IDS.map((name) => [name, 0]));
  const basis: Record<string, number> = Object.fromEntries(CONFIDENCE_BASIS_VALUES.map((name) => [name, 0]));
  for (const record of derived) {
    for (const name of record.failed_conditions) failed[name] += 1;
    for (const value of Object.values(record.basis)) basis[value] += 1;
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
    rows_by_confidence_class: countBy(ASSIGNED_CONFIDENCE_CLASSES, rows.map((row) => row.confidence?.confidence_class ?? null)),
    rows_by_confidence_kind: countBy(CONFIDENCE_KINDS, rows.map((row) => row.confidence?.confidence_kind ?? null)),
    rows_by_binding_class: countBy(PLANNING_ACTION_CLASSES, rows.map((row) => row.action_class)),
    rows_by_reason_code: countBy(PLANNING_REASON_CODES, rows.map((row) => row.action_reason_code)),
    rows_by_would_be_class: countBy(PLANNING_ACTION_CLASSES, rows.map((row) => row.would_be_class)),
    rows_by_v2_result: countBy([...PLANNING_ACTION_CLASSES, NO_V2_TRIGGER], rows.map((row) => row.class_v2?.result ?? null)),
    rows_by_headline_status: countBy(HEADLINE_STATUSES, rows.map((row) => row.headline_stability.status)),
    failed_condition_counts: failed,
    basis_value_counts: basis,
    rows_under_gr1: derived.filter((record) => record.guardrail_gr1.applies).length,
    rows_without_fpps: rows.filter((row) => row.fpps_0_100 === null).length,
    obs_rows_not_event_aligned: rows.filter((row) => row.lane === "OBS" && row.temporal_relation !== "event_aligned").length,
    inputs_by_rights_level: countBy(PUBLICATION_LEVELS, overlay.inputs.map((item) => item.rights_level)),
  };
}
