import report from "./policy-weight-sensitivity.json";

/** One weighting of the planning score and the order of the units it gives. */
export interface WeightingResult {
  weights: Record<string, number>;
  order: string[];
  scores: Record<string, number>;
  first: string;
  same_order: boolean;
}

/**
 * The weight test of the published case SE1 (`scripts/build_fpps_weight_sensitivity.py`): would the order of the
 * eight tambons be another one with other weights? Report only: it changes no score, weight or class. A Python test
 * keeps this copy equal to the report under `outputs/` and to what the script writes from the published case.
 */
export interface PolicyWeightTest {
  label: string;
  published: Omit<WeightingResult, "same_order">;
  named: (WeightingResult & { id: string })[];
  one_at_a_time: (WeightingResult & { component: string; factor: number })[];
  random: {
    draws: number;
    seed: number;
    share_first: Record<string, number>;
    share_same_first_three: number;
    share_same_first_four: number;
    share_same_order: number;
  };
  units: Record<string, { en: string; th: string }>;
}

export const POLICY_WEIGHT_TEST = report as unknown as PolicyWeightTest;

/** A share as the page prints it: a whole percent, one decimal from 99% up, and never rounded up to 100%. */
export function weightTestShare(share: number): string {
  if (share >= 1) return "100%";
  if (share >= 0.99) return `${Math.min(99.9, Math.floor(share * 1000) / 10).toFixed(1)}%`;
  return `${Math.round(share * 100)}%`;
}
