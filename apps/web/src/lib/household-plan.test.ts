import { describe, expect, it } from "vitest";

import {
  HOUSEHOLD_PLAN_ITEMS,
  HOUSEHOLD_PLAN_STORAGE_KEY,
  LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY,
  buildHouseholdPlanText,
  canReviewHouseholdPlan,
  countCompletedPlanItems,
  createEmptyHouseholdPlan,
  markNoHouseholdNeedsApply,
  parseHouseholdPlan,
  readStoredHouseholdPlan,
  recordHouseholdPlanReview,
  removeStoredHouseholdPlan,
  selectedHouseholdNeeds,
  toggleHouseholdNeed,
  writeStoredHouseholdPlan,
} from "./household-plan";

describe("household preparedness plan", () => {
  it("starts fail-closed with distinct core, needs, save, and review states", () => {
    const plan = createEmptyHouseholdPlan("FG-TB-002");

    expect(plan).toMatchObject({
      schema_version: "2.0",
      planning_area_id: "FG-TB-002",
      needs_review_state: "not_reviewed",
      needs_reviewed_at: null,
      last_saved_at: null,
      last_reviewed_at: null,
    });
    expect(countCompletedPlanItems(plan)).toBe(0);
    expect(selectedHouseholdNeeds(plan)).toEqual([]);
    expect(canReviewHouseholdPlan(plan)).toBe(false);
  });

  it("migrates v1 deterministically without treating unchecked needs as none apply", () => {
    const migrated = parseHouseholdPlan(JSON.stringify({
      schema_version: "1.0",
      planning_area_id: "FG-TB-003",
      checklist: { official_contacts: true, injected_claim: true },
      needs: { pets: true, children: "yes" },
      last_reviewed_at: "2026-07-18T03:00:00.000Z",
    }), "FG-TB-002");

    expect(migrated.schema_version).toBe("2.0");
    expect(migrated.planning_area_id).toBe("FG-TB-003");
    expect(migrated.checklist.official_contacts).toBe(true);
    expect(migrated.checklist.waterproof_supplies).toBe(false);
    expect(migrated.needs.pets).toBe(true);
    expect(migrated.needs.children).toBe(false);
    expect(migrated.needs_review_state).toBe("selected");
    expect(migrated.needs_reviewed_at).toBe("2026-07-18T03:00:00.000Z");
    expect(migrated.last_saved_at).toBeNull();
    expect(migrated.last_reviewed_at).toBe("2026-07-18T03:00:00.000Z");

    const unchecked = parseHouseholdPlan(JSON.stringify({
      schema_version: "1.0",
      planning_area_id: "FG-TB-003",
      checklist: {},
      needs: {},
      last_reviewed_at: "2026-07-18T03:00:00.000Z",
    }), "FG-TB-002");
    expect(unchecked.needs_review_state).toBe("not_reviewed");
    expect(unchecked.needs_reviewed_at).toBeNull();
    expect(unchecked.last_reviewed_at).toBe("2026-07-18T03:00:00.000Z");
  });

  it("normalizes v2 none-apply state and malformed values", () => {
    const parsed = parseHouseholdPlan(JSON.stringify({
      schema_version: "2.0",
      planning_area_id: "FG-TB-004",
      checklist: { official_contacts: true },
      needs: { pets: true },
      needs_review_state: "none_apply",
      needs_reviewed_at: "2026-07-19T03:00:00.000Z",
      last_saved_at: "not-a-date",
      last_reviewed_at: "not-a-date",
    }), "FG-TB-002");

    expect(parsed.needs_review_state).toBe("none_apply");
    expect(Object.values(parsed.needs).every((selected) => selected === false)).toBe(true);
    expect(parsed.needs_reviewed_at).toBe("2026-07-19T03:00:00.000Z");
    expect(parsed.last_saved_at).toBeNull();
    expect(parsed.last_reviewed_at).toBeNull();
    expect(canReviewHouseholdPlan(parsed)).toBe(true);
    expect(parseHouseholdPlan("not-json", "FG-TB-002")).toEqual(createEmptyHouseholdPlan("FG-TB-002"));
  });

  it("requires an explicit needs choice before a plan review can be recorded", () => {
    const timestamp = "2026-07-22T01:00:00.000Z";
    const empty = createEmptyHouseholdPlan("FG-TB-002");

    expect(recordHouseholdPlanReview(empty, timestamp).last_reviewed_at).toBeNull();

    const selected = toggleHouseholdNeed(empty, "pets", timestamp);
    expect(selected.needs_review_state).toBe("selected");
    expect(selected.needs_reviewed_at).toBe(timestamp);
    expect(recordHouseholdPlanReview(selected, timestamp).last_reviewed_at).toBe(timestamp);

    const unselected = toggleHouseholdNeed(selected, "pets", timestamp);
    expect(unselected.needs_review_state).toBe("not_reviewed");
    expect(unselected.needs_reviewed_at).toBeNull();

    const noneApply = markNoHouseholdNeedsApply(selected, timestamp);
    expect(noneApply.needs_review_state).toBe("none_apply");
    expect(Object.values(noneApply.needs).every((value) => value === false)).toBe(true);
    expect(recordHouseholdPlanReview(noneApply, timestamp).last_reviewed_at).toBe(timestamp);
  });

  it("prefers v2 storage, migrates from the legacy key, and clears both keys", () => {
    const values = new Map<string, string>();
    const legacy = JSON.stringify({
      schema_version: "1.0",
      planning_area_id: "FG-TB-001",
      checklist: { official_contacts: true },
      needs: { pets: true },
      last_reviewed_at: null,
    });
    values.set(LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY, legacy);

    const migrated = readStoredHouseholdPlan({ getItem: (key) => values.get(key) ?? null }, "");
    expect(migrated.schema_version).toBe("2.0");
    expect(migrated.checklist.official_contacts).toBe(true);
    expect(migrated.needs_review_state).toBe("selected");

    migrated.planning_area_id = "FG-TB-004";
    writeStoredHouseholdPlan({ setItem: (key, value) => values.set(key, value) }, migrated);
    expect(values.has(HOUSEHOLD_PLAN_STORAGE_KEY)).toBe(true);
    expect(readStoredHouseholdPlan({ getItem: (key) => values.get(key) ?? null }, "").planning_area_id).toBe("FG-TB-004");

    removeStoredHouseholdPlan({ removeItem: (key) => values.delete(key) });
    expect(values.has(HOUSEHOLD_PLAN_STORAGE_KEY)).toBe(false);
    expect(values.has(LEGACY_HOUSEHOLD_PLAN_STORAGE_KEY)).toBe(false);
  });

  it("does not throw when browser storage is blocked", () => {
    const plan = createEmptyHouseholdPlan("FG-TB-004");
    expect(() => writeStoredHouseholdPlan({ setItem: () => { throw new Error("blocked"); } }, plan)).not.toThrow();
    expect(() => readStoredHouseholdPlan({ getItem: () => { throw new Error("blocked"); } }, "FG-TB-001")).not.toThrow();
    expect(() => removeStoredHouseholdPlan({ removeItem: () => { throw new Error("blocked"); } })).not.toThrow();
  });

  it("exports tailored bilingual actions without an exact-location or safety claim", () => {
    const plan = createEmptyHouseholdPlan("FG-TB-002");
    plan.checklist[HOUSEHOLD_PLAN_ITEMS[0].id] = true;
    plan.needs.pets = true;
    plan.needs.regular_medicine = true;
    plan.needs_review_state = "selected";
    plan.needs_reviewed_at = "2026-07-18T02:00:00.000Z";
    plan.last_saved_at = "2026-07-18T02:30:00.000Z";
    plan.last_reviewed_at = "2026-07-18T03:00:00.000Z";

    const text = buildHouseholdPlanText(plan, "พื้นที่วางแผน 2", "Planning area 2");

    expect(text).toContain("แผนเตรียมพร้อมของครัวเรือน");
    expect(text).toContain("household preparedness plan");
    expect(text).toContain("CHECK CURRENT INSTRUCTIONS WITH DDPM");
    expect(text).toContain("does not identify an exact household location");
    expect(text).toContain("does not calculate a safe route");
    expect(text).toContain("Confirm a pet-friendly destination");
    expect(text).toContain("Pack medicine, a medicine list");
    expect(text).toContain("[x] บันทึกหมายเลข ปภ. 1784");
    expect(text).not.toMatch(/household is safe|safety score/i);
  });
});
