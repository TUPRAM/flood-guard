import { describe, expect, it } from "vitest";

import {
  HOUSEHOLD_PLAN_ITEMS,
  HOUSEHOLD_PLAN_STORAGE_KEY,
  buildHouseholdPlanText,
  countCompletedPlanItems,
  createEmptyHouseholdPlan,
  parseHouseholdPlan,
  readStoredHouseholdPlan,
  removeStoredHouseholdPlan,
  writeStoredHouseholdPlan,
} from "./household-plan";

describe("household preparedness plan", () => {
  it("starts fail-closed with no completed or profiled claims", () => {
    const plan = createEmptyHouseholdPlan("FG-TB-002");

    expect(plan.planning_area_id).toBe("FG-TB-002");
    expect(plan.last_reviewed_at).toBeNull();
    expect(countCompletedPlanItems(plan)).toBe(0);
    expect(Object.values(plan.needs).every((selected) => selected === false)).toBe(true);
  });

  it("normalizes persisted data and ignores unknown or malformed values", () => {
    const parsed = parseHouseholdPlan(JSON.stringify({
      schema_version: "1.0",
      planning_area_id: "FG-TB-003",
      checklist: { official_contacts: true, injected_claim: true },
      needs: { pets: true, children: "yes" },
      last_reviewed_at: "not-a-date",
    }), "FG-TB-002");

    expect(parsed.planning_area_id).toBe("FG-TB-003");
    expect(parsed.checklist.official_contacts).toBe(true);
    expect(parsed.checklist.waterproof_supplies).toBe(false);
    expect(parsed.needs.pets).toBe(true);
    expect(parsed.needs.children).toBe(false);
    expect(parsed.last_reviewed_at).toBeNull();
    expect(parseHouseholdPlan("not-json", "FG-TB-002")).toEqual(createEmptyHouseholdPlan("FG-TB-002"));
  });

  it("persists and clears without throwing when browser storage is blocked", () => {
    const values = new Map<string, string>();
    const plan = createEmptyHouseholdPlan("FG-TB-004");
    plan.checklist.official_contacts = true;

    writeStoredHouseholdPlan({ setItem: (key, value) => values.set(key, value) }, plan);
    expect(readStoredHouseholdPlan({ getItem: (key) => values.get(key) ?? null }, "").checklist.official_contacts).toBe(true);
    expect(values.has(HOUSEHOLD_PLAN_STORAGE_KEY)).toBe(true);

    removeStoredHouseholdPlan({ removeItem: (key) => values.delete(key) });
    expect(values.has(HOUSEHOLD_PLAN_STORAGE_KEY)).toBe(false);

    expect(() => writeStoredHouseholdPlan({ setItem: () => { throw new Error("blocked"); } }, plan)).not.toThrow();
    expect(() => readStoredHouseholdPlan({ getItem: () => { throw new Error("blocked"); } }, "FG-TB-001")).not.toThrow();
    expect(() => removeStoredHouseholdPlan({ removeItem: () => { throw new Error("blocked"); } })).not.toThrow();
  });

  it("exports a bilingual, non-operational plan without an exact-location claim", () => {
    const plan = createEmptyHouseholdPlan("FG-TB-002");
    plan.checklist[HOUSEHOLD_PLAN_ITEMS[0].id] = true;
    plan.last_reviewed_at = "2026-07-18T03:00:00.000Z";

    const text = buildHouseholdPlanText(plan, "พื้นที่สาธิต 2", "Fixture area 2");

    expect(text).toContain("แผนเตรียมพร้อมของครัวเรือน");
    expect(text).toContain("household preparedness plan");
    expect(text).toContain("NOT AN OFFICIAL WARNING");
    expect(text).toContain("not an exact household location");
    expect(text).toContain("does not calculate a safe route");
    expect(text).toContain("[x] บันทึกหมายเลข ปภ. 1784");
  });
});
