import { describe, expect, it } from "vitest";

import {
  ACTION_CLASS_COLORS,
  SCENARIO_TONE_COLORS,
  formatServerDelta,
  scenarioMapPresentation,
} from "./scenario-presentation";

describe("scenario map presentation", () => {
  it("preserves the A-E class treatment for baseline", () => {
    const result = scenarioMapPresentation("A", "baseline", {
      people_losing_30_min_access: 210,
      equity_gap_ratio: 1.4,
      delta: 0,
    });

    expect(result).toEqual({
      tone: "baseline",
      fillColor: ACTION_CLASS_COLORS.A,
      outlineColor: ACTION_CLASS_COLORS.A,
      serverDelta: 0,
    });
  });

  it.each([
    [-31, "improves", SCENARIO_TONE_COLORS.improves],
    [0, "neutral", SCENARIO_TONE_COLORS.neutral],
    [44, "worsens", SCENARIO_TONE_COLORS.worsens],
  ] as const)("maps the server delta %s to the %s visual tone", (delta, tone, color) => {
    const result = scenarioMapPresentation("C", "add_temporary_shelter", {
      people_losing_30_min_access: 179,
      equity_gap_ratio: 1.2,
      delta,
    });

    expect(result.tone).toBe(tone);
    expect(result.fillColor).toBe(color);
    expect(result.outlineColor).toBe(ACTION_CLASS_COLORS.C);
    expect(result.serverDelta).toBe(delta);
  });

  it("fails closed when a non-baseline scenario result is absent", () => {
    const result = scenarioMapPresentation("B", "close_road");

    expect(result.tone).toBe("unavailable");
    expect(result.fillColor).toBe(SCENARIO_TONE_COLORS.unavailable);
    expect(result.serverDelta).toBeNull();
  });

  it("only formats the server-produced delta for display", () => {
    expect(formatServerDelta(-12)).toBe("-12");
    expect(formatServerDelta(0)).toBe("0");
    expect(formatServerDelta(12)).toBe("+12");
  });
});
