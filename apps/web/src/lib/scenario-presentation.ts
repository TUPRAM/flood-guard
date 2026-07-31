import type { ScenarioId, ScenarioResult } from "@/lib/types";

export type ScenarioTone = "baseline" | "improves" | "neutral" | "worsens" | "unavailable";

export interface ScenarioMapPresentation {
  tone: ScenarioTone;
  fillColor: string;
  outlineColor: string;
  serverDelta: number | null;
}

export const ACTION_CLASS_COLORS: Record<string, string> = {
  A: "#b42318",
  B: "#c65d16",
  C: "#b88700",
  D: "#25766d",
  E: "#5d6b78",
};

export const SCENARIO_TONE_COLORS: Record<Exclude<ScenarioTone, "baseline">, string> = {
  improves: "#0f8a7b",
  neutral: "#6b7785",
  worsens: "#c43d4d",
  unavailable: "#8b96a3",
};

/**
 * Convert an engine-produced access delta into a visual tone.
 *
 * This is presentation-only: the browser never recomputes access, equity, FPPS,
 * or action class. The returned delta is the exact value supplied by the API or
 * fixture scenario artifact.
 */
export function scenarioMapPresentation(
  actionClass: string,
  scenarioId: ScenarioId,
  result?: ScenarioResult,
): ScenarioMapPresentation {
  const classColor = ACTION_CLASS_COLORS[actionClass] ?? ACTION_CLASS_COLORS.E;
  if (scenarioId === "baseline") {
    return {
      tone: "baseline",
      fillColor: classColor,
      outlineColor: classColor,
      serverDelta: result?.delta ?? null,
    };
  }

  if (!result) {
    return {
      tone: "unavailable",
      fillColor: SCENARIO_TONE_COLORS.unavailable,
      outlineColor: classColor,
      serverDelta: null,
    };
  }

  const tone = result.delta < 0
    ? "improves"
    : result.delta > 0
      ? "worsens"
      : "neutral";

  return {
    tone,
    fillColor: SCENARIO_TONE_COLORS[tone],
    outlineColor: classColor,
    serverDelta: result.delta,
  };
}

/** Format an already-computed scenario delta without deriving a new metric. */
export function formatServerDelta(delta: number): string {
  return `${delta > 0 ? "+" : ""}${delta}`;
}
