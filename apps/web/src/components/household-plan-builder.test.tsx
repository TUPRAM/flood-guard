import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { createEmptyHouseholdPlan } from "@/lib/household-plan";

import { HouseholdPlanBuilder } from "./household-plan-builder";

const handlers = {
  onToggleItem: () => undefined,
  onToggleNeed: () => undefined,
  onSelectNoNeedsApply: () => undefined,
  onMarkReviewed: () => undefined,
  onResetChecklist: () => undefined,
  onClearPlan: () => undefined,
};

describe("HouseholdPlanBuilder", () => {
  it("keeps core, needs, and review progress separate and blocks premature review", () => {
    const plan = createEmptyHouseholdPlan("TH570901");
    for (const itemId of Object.keys(plan.checklist) as Array<keyof typeof plan.checklist>) {
      plan.checklist[itemId] = true;
    }

    const html = renderToStaticMarkup(
      <HouseholdPlanBuilder language="en" plan={plan} areaNameTh="แม่สาย" areaNameEn="Mae Sai" {...handlers} />,
    );

    expect(html).toContain("Core actions");
    expect(html).toContain("5/5");
    expect(html).toContain("Household needs");
    expect(html).toContain("Not reviewed");
    expect(html).toContain("Plan review");
    expect(html).toContain("These statuses describe only what you recorded");
    expect(html).toContain('aria-describedby="plan-review-requirement"');
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Record plan review<\/button>/);
    expect(html).not.toContain("ready to review");
  });

  it("renders deterministic actions for selected household needs", () => {
    const plan = createEmptyHouseholdPlan("TH570901");
    plan.needs.pets = true;
    plan.needs.regular_medicine = true;
    plan.needs_review_state = "selected";
    plan.needs_reviewed_at = "2026-07-22T01:00:00.000Z";

    const html = renderToStaticMarkup(
      <HouseholdPlanBuilder language="en" plan={plan} areaNameTh="แม่สาย" areaNameEn="Mae Sai" {...handlers} />,
    );

    expect(html).toContain("2 selected");
    expect(html).toContain("Confirm a pet-friendly destination");
    expect(html).toContain("Pack medicine, a medicine list");
    expect(html).not.toContain('aria-describedby="plan-review-requirement"');
    expect(html).not.toMatch(/<button[^>]*disabled=""[^>]*>Record plan review<\/button>/);
  });

  it("represents none-apply as an explicit reviewed choice", () => {
    const plan = createEmptyHouseholdPlan("TH570901");
    plan.needs_review_state = "none_apply";
    plan.needs_reviewed_at = "2026-07-22T01:00:00.000Z";

    const html = renderToStaticMarkup(
      <HouseholdPlanBuilder language="en" plan={plan} areaNameTh="แม่สาย" areaNameEn="Mae Sai" {...handlers} />,
    );

    expect(html).toContain("Confirmed: none apply");
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("Continue with the core actions");
  });
});
