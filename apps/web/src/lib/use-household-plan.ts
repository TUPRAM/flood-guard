"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createEmptyHouseholdPlan,
  readStoredHouseholdPlan,
  removeStoredHouseholdPlan,
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

  const updatePlan = useCallback((update: (current: HouseholdPlan) => HouseholdPlan) => {
    setPlan((current) => {
      const next = update(current);
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
    updatePlan((current) => ({
      ...current,
      needs: { ...current.needs, [needId]: !current.needs[needId] },
      last_reviewed_at: null,
    }));
  }, [updatePlan]);

  const markReviewed = useCallback(() => {
    updatePlan((current) => ({ ...current, last_reviewed_at: new Date().toISOString() }));
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
    markReviewed,
    resetChecklist,
    clearPlan,
  } as const;
}
