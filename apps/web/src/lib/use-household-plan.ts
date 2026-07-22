"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createEmptyHouseholdPlan,
  markNoHouseholdNeedsApply,
  readStoredHouseholdPlan,
  recordHouseholdPlanReview,
  removeStoredHouseholdPlan,
  toggleHouseholdNeed,
  writeStoredHouseholdPlan,
  type HouseholdNeedId,
  type HouseholdPlan,
  type HouseholdPlanItemId,
} from "./household-plan";

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function useHouseholdPlan(defaultAreaId: string) {
  const [plan, setPlan] = useState<HouseholdPlan>(() => createEmptyHouseholdPlan(defaultAreaId));
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    setPlan(readStoredHouseholdPlan(browserStorage(), defaultAreaId));
  }, [defaultAreaId]);

  const updatePlan = useCallback((update: (current: HouseholdPlan, timestamp: string) => HouseholdPlan) => {
    setPlan((current) => {
      const timestamp = new Date().toISOString();
      const next = { ...update(current, timestamp), last_saved_at: timestamp };
      writeStoredHouseholdPlan(browserStorage(), next);
      return next;
    });
  }, []);

  const selectPlanningArea = useCallback((areaId: string) => {
    updatePlan((current) => current.planning_area_id === areaId
      ? current
      : { ...current, planning_area_id: areaId, last_reviewed_at: null });
  }, [updatePlan]);

  const toggleChecklistItem = useCallback((itemId: HouseholdPlanItemId) => {
    updatePlan((current) => ({
      ...current,
      checklist: { ...current.checklist, [itemId]: !current.checklist[itemId] },
      last_reviewed_at: null,
    }));
  }, [updatePlan]);

  const toggleNeed = useCallback((needId: HouseholdNeedId) => {
    updatePlan((current, timestamp) => toggleHouseholdNeed(current, needId, timestamp));
  }, [updatePlan]);

  const selectNoNeedsApply = useCallback(() => {
    updatePlan((current, timestamp) => markNoHouseholdNeedsApply(current, timestamp));
  }, [updatePlan]);

  const markReviewed = useCallback(() => {
    updatePlan((current, timestamp) => recordHouseholdPlanReview(current, timestamp));
  }, [updatePlan]);

  const resetChecklist = useCallback(() => {
    updatePlan((current) => ({
      ...current,
      checklist: createEmptyHouseholdPlan(current.planning_area_id).checklist,
      last_reviewed_at: null,
    }));
  }, [updatePlan]);

  const clearPlan = useCallback(() => {
    removeStoredHouseholdPlan(browserStorage());
    setPlan(createEmptyHouseholdPlan(defaultAreaId));
  }, [defaultAreaId]);

  return {
    plan,
    selectPlanningArea,
    toggleChecklistItem,
    toggleNeed,
    selectNoNeedsApply,
    markReviewed,
    resetChecklist,
    clearPlan,
  } as const;
}
