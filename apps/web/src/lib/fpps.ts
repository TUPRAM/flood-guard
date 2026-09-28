/**
 * Flood Preparedness Priority Score (FPPS) and A–E action class: a line-for-line port of
 * `floodguard.scoring` (src/floodguard/scoring.py). Weights, thresholds and the low-confidence rule are the locked
 * project policy; `fpps.test.ts` checks this port against `tests/fixtures/fpps_parity_cases.json`, which is generated
 * from the Python engine.
 */

import type { ActionClass, ConfidenceClass } from "@floodguard/contracts";

export const FPPS_COMPONENTS = [
  "flood_likelihood_0_100",
  "exposure_0_100",
  "access_gap_0_100",
  "road_criticality_0_100",
  "vulnerability_context_0_100",
] as const;
export type FppsComponent = (typeof FPPS_COMPONENTS)[number];
export type FppsComponents = Record<FppsComponent, number>;
export type FppsWeights = Record<FppsComponent, number>;

/** Default weights: 0.30 flood likelihood, 0.25 exposure, 0.20 access gap, 0.15 road criticality, 0.10 vulnerability/context. */
export const DEFAULT_FPPS_WEIGHTS: Readonly<FppsWeights> = {
  flood_likelihood_0_100: 0.3,
  exposure_0_100: 0.25,
  access_gap_0_100: 0.2,
  road_criticality_0_100: 0.15,
  vulnerability_context_0_100: 0.1,
};

export type ActionReasonCode =
  | "low_confidence"
  | "low_priority_score"
  | "life_safety_exposure"
  | "critical_route_access"
  | "essential_service_access"
  | "resilience";

export interface FppsInput extends FppsComponents { confidence_class: ConfidenceClass }

export interface FppsResult {
  fpps_0_100: number;
  action_class: ActionClass;
  action_reason_code: ActionReasonCode;
  top_reason: string;
}

const COMPONENT_LABELS: Record<FppsComponent, string> = {
  flood_likelihood_0_100: "flood likelihood",
  exposure_0_100: "exposure",
  access_gap_0_100: "access gap",
  road_criticality_0_100: "road criticality",
  vulnerability_context_0_100: "vulnerability/context",
};

/** Round half to even at 2 decimals, like pandas/numpy `Series.round(2)`. */
export function roundScore(value: number): number {
  const scaled = value * 100;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  const even = diff === 0.5 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(scaled);
  return even / 100;
}

/** Validate that every component is a number from 0 to 100 (the Python `validate_component_values`). */
export function validateComponents(components: FppsComponents): void {
  for (const key of FPPS_COMPONENTS) {
    const value = components[key];
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      throw new RangeError(`${key} must be a number from 0 to 100; got ${value}`);
    }
  }
}

/** Validate non-negative weights for all five components and normalise them to sum to 1. */
export function normaliseWeights(weights: FppsWeights): FppsWeights {
  let total = 0;
  for (const key of FPPS_COMPONENTS) {
    const weight = weights[key];
    if (!Number.isFinite(weight)) throw new RangeError(`missing weight: ${key}`);
    if (weight < 0) throw new RangeError(`Weight for ${key} must be non-negative.`);
    total += weight;
  }
  if (total <= 0) throw new RangeError("At least one FPPS weight must be greater than zero.");
  return Object.fromEntries(FPPS_COMPONENTS.map((key) => [key, weights[key] / total])) as FppsWeights;
}

/** Weighted points each component adds to the unrounded FPPS (weights normalised). */
export function componentPoints(components: FppsComponents, weights: FppsWeights = DEFAULT_FPPS_WEIGHTS): FppsComponents {
  const active = normaliseWeights(weights);
  return Object.fromEntries(FPPS_COMPONENTS.map((key) => [key, components[key] * active[key]])) as FppsComponents;
}

/** FPPS 0–100, rounded to 2 decimals like the Python engine. */
export function fppsScore(components: FppsComponents, weights: FppsWeights = DEFAULT_FPPS_WEIGHTS): number {
  validateComponents(components);
  const points = componentPoints(components, weights);
  return roundScore(FPPS_COMPONENTS.reduce((sum, key) => sum + points[key], 0));
}

/** A–E class from the rounded score (`assign_action_class`): low confidence or FPPS < 35 is always E. */
export function assignActionClass(input: FppsInput, fpps: number): ActionClass {
  if (input.confidence_class === "low" || fpps < 35) return "E";
  const { exposure_0_100: exposure, access_gap_0_100: access, road_criticality_0_100: road } = input;
  if (exposure >= 70 && access >= 70) return "A";
  if (road >= 75 && access >= 55) return "B";
  if (exposure >= 65 && access >= 50) return "C";
  return "D";
}

/** Canonical reason for the class (`assign_action_reason_code`). */
export function actionReasonCode(input: FppsInput, fpps: number, actionClass: ActionClass): ActionReasonCode {
  if (input.confidence_class === "low") return "low_confidence";
  if (fpps < 35) return "low_priority_score";
  return ({ A: "life_safety_exposure", B: "critical_route_access", C: "essential_service_access", D: "resilience", E: "low_priority_score" } as const)[actionClass];
}

/** English top reason, word for word the Python `generate_top_reason`. */
export function topReason(input: FppsInput, actionClass: ActionClass, reason: ActionReasonCode): string {
  if (actionClass === "E") {
    return reason === "low_confidence"
      ? "Monitor and verify because confidence is low."
      : "Monitor and verify because the priority score is low.";
  }
  if (actionClass === "A") return "High exposure and access loss require life-safety action.";
  if (actionClass === "B") return "Critical routes and access loss threaten isolation.";
  if (actionClass === "C") return "Exposure and access loss threaten essential services.";
  const top = highestComponent(input);
  return `Highest driver is ${COMPONENT_LABELS[top]} (${input[top].toFixed(1)}/100).`;
}

/** Component with the highest 0–100 value; ties go to the earlier component, like Python `max`. */
export function highestComponent(components: FppsComponents): FppsComponent {
  return FPPS_COMPONENTS.reduce((best, key) => (components[key] > components[best] ? key : best), FPPS_COMPONENTS[0]);
}

/** Score one subdistrict row (`score_subdistricts` for a single row). */
export function scoreSubdistrict(input: FppsInput, weights: FppsWeights = DEFAULT_FPPS_WEIGHTS): FppsResult {
  const fpps = fppsScore(input, weights);
  const actionClass = assignActionClass(input, fpps);
  const reason = actionReasonCode(input, fpps, actionClass);
  return { fpps_0_100: fpps, action_class: actionClass, action_reason_code: reason, top_reason: topReason(input, actionClass, reason) };
}
