"use client";

import { useEffect, useState } from "react";

import { getMaeSaiOfflineData, getOfflineData, loadFloodGuardData } from "./data-provider";
import type { FloodGuardData, StudyAreaId } from "./types";

export function useFloodGuardData(
  preferredStudyArea: StudyAreaId = "fixture_thailand_demo",
): FloodGuardData {
  const [data, setData] = useState<FloodGuardData>(() => (
    preferredStudyArea === "mae_sai_candidate_v1"
      ? getMaeSaiOfflineData()
      : getOfflineData()
  ));

  useEffect(() => {
    let active = true;
    loadFloodGuardData(undefined, undefined, preferredStudyArea).then((next) => {
      if (active) setData(next);
    });
    return () => {
      active = false;
    };
  }, [preferredStudyArea]);

  return data;
}
