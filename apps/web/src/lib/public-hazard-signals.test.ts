import type { PublicPreparednessArea } from "@floodguard/contracts";
import { describe, expect, it } from "vitest";

import {
  derivePublicHazardSignals,
  hazardSignalSummary,
} from "./public-hazard-signals";

function area(overrides: Partial<PublicPreparednessArea> = {}): PublicPreparednessArea {
  return {
    schema_version: "1.0.0",
    evidence_context_id: "ctx-test",
    area_id: "FG-TB-001",
    area_name_th: "พื้นที่ทดสอบ",
    area_name_en: "Test area",
    planning_priority_0_100: 10,
    evidence_sufficiency: "high",
    recommendation_code: "resilience",
    source_timestamp: "2024-01-01T00:00:00Z",
    freshness: "historical",
    current_conditions_confirmed: false,
    ...overrides,
  } as PublicPreparednessArea;
}

describe("derivePublicHazardSignals", () => {
  it("returns no signals when no area is matched", () => {
    expect(derivePublicHazardSignals(undefined)).toEqual([]);
  });

  it("returns no signals for a low-priority area with a resilience recommendation", () => {
    expect(derivePublicHazardSignals(area())).toEqual([]);
  });

  it("flags elevated planning priority at the 50 threshold", () => {
    const signals = derivePublicHazardSignals(area({ planning_priority_0_100: 50 }));
    expect(signals.map((signal) => signal.code)).toEqual(["elevated_planning_priority"]);
  });

  it("does not flag priority just below the threshold", () => {
    expect(derivePublicHazardSignals(area({ planning_priority_0_100: 49.9 }))).toEqual([]);
  });

  it("adds the exposure signal carried by the recommendation code", () => {
    const signals = derivePublicHazardSignals(area({
      planning_priority_0_100: 81.6,
      recommendation_code: "life_safety_exposure",
    }));
    expect(signals.map((signal) => signal.code)).toEqual([
      "elevated_planning_priority",
      "life_safety_exposure",
    ]);
  });

  it("never derives a signal from evidence-quality caveats alone", () => {
    const signals = derivePublicHazardSignals(area({
      evidence_sufficiency: "low",
      freshness: "unknown",
    }));
    expect(signals).toEqual([]);
  });

  it("keeps every signal label bilingual", () => {
    const signals = derivePublicHazardSignals(area({
      planning_priority_0_100: 90,
      recommendation_code: "critical_route_access",
    }));
    for (const signal of signals) {
      expect(signal.label_en.length).toBeGreaterThan(0);
      expect(signal.label_th.length).toBeGreaterThan(0);
    }
  });
});

describe("hazardSignalSummary", () => {
  it("uses a singular English phrase for one signal", () => {
    expect(hazardSignalSummary(1, "en")).toBe("1 preparedness signal for your area");
  });

  it("uses a plural English phrase beyond one signal", () => {
    expect(hazardSignalSummary(2, "en")).toBe("2 preparedness signals for your area");
  });

  it("never claims a confirmed hazard", () => {
    for (const language of ["en", "th"] as const) {
      expect(hazardSignalSummary(2, language)).not.toMatch(/hazard|warning|danger/iu);
    }
  });
});
