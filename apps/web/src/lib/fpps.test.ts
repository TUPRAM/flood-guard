import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import type { ConfidenceClass } from "@floodguard/contracts";

import {
  DEFAULT_FPPS_WEIGHTS,
  FPPS_COMPONENTS,
  fppsScore,
  normaliseWeights,
  roundScore,
  scoreSubdistrict,
  type FppsComponents,
  type FppsWeights,
} from "./fpps";

interface FixtureOutput { subdistrict_id: string; fpps_0_100: number; action_class: string; action_reason_code: string; top_reason: string }
interface Fixture {
  components: string[];
  default_weights: FppsWeights;
  inputs: (FppsComponents & { subdistrict_id: string; confidence_class: ConfidenceClass })[];
  default_outputs: FixtureOutput[];
  alt_weights: FppsWeights;
  alt_outputs: FixtureOutput[];
}

// Generated from src/floodguard/scoring.py by scripts/build_fpps_parity_fixture.py.
const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "../../tests/fixtures/fpps_parity_cases.json"), "utf8")) as Fixture;

describe("FPPS port parity with floodguard.scoring", () => {
  it("uses the same components and default weights", () => {
    expect([...FPPS_COMPONENTS]).toEqual(fixture.components);
    expect(DEFAULT_FPPS_WEIGHTS).toEqual(fixture.default_weights);
  });

  it.each([
    ["default", undefined, "default_outputs"],
    ["alternative", "alt_weights", "alt_outputs"],
  ] as const)("matches every Python row with %s weights", (_, weightKey, outputKey) => {
    const weights = weightKey ? fixture[weightKey] : undefined;
    fixture.inputs.forEach((input, index) => {
      const expected = fixture[outputKey][index];
      expect(scoreSubdistrict(input, weights), input.subdistrict_id).toEqual({
        fpps_0_100: expected.fpps_0_100,
        action_class: expected.action_class,
        action_reason_code: expected.action_reason_code,
        top_reason: expected.top_reason,
      });
    });
  });
});

describe("FPPS rules", () => {
  const all = (value: number): FppsComponents => Object.fromEntries(FPPS_COMPONENTS.map((key) => [key, value])) as FppsComponents;

  it("forces class E for low confidence however high the score", () => {
    const result = scoreSubdistrict({ ...all(100), confidence_class: "low" });
    expect(result.fpps_0_100).toBe(100);
    expect(result.action_class).toBe("E");
    expect(result.action_reason_code).toBe("low_confidence");
  });

  it("classifies on the rounded score, like the Python engine", () => {
    expect(fppsScore({ ...all(35), flood_likelihood_0_100: 34.99 })).toBe(35);
    expect(scoreSubdistrict({ ...all(35), flood_likelihood_0_100: 34.99, confidence_class: "medium" }).action_class).toBe("D");
  });

  it("rounds exact halves to even", () => {
    expect(roundScore(0.125)).toBe(0.12);
    expect(roundScore(0.375)).toBe(0.38);
  });

  it("rejects out-of-range components and invalid weights", () => {
    expect(() => fppsScore({ ...all(50), exposure_0_100: 101 })).toThrow(RangeError);
    expect(() => fppsScore({ ...all(50), exposure_0_100: Number.NaN })).toThrow(RangeError);
    expect(() => normaliseWeights({ ...DEFAULT_FPPS_WEIGHTS, exposure_0_100: -1 })).toThrow(RangeError);
    expect(() => normaliseWeights(Object.fromEntries(FPPS_COMPONENTS.map((key) => [key, 0])) as FppsWeights)).toThrow(RangeError);
  });
});
