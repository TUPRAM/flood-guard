"use client";

import { useEffect, useMemo, useState } from "react";

import {
  getMaeSaiOfflineData,
  getOfflineData,
  loadFloodGuardData,
  normalizeDataOptions,
} from "./data-provider";
import type { FloodGuardData, FloodGuardDataOptions, StudyAreaId } from "./types";

function dataOptionsKey(options: FloodGuardDataOptions): string {
  return JSON.stringify([
    options.studyArea,
    options.role,
    options.evidenceContextId ?? null,
  ]);
}

function dataOptionsFromKey(key: string): FloodGuardDataOptions {
  const [studyArea, role, evidenceContextId] = JSON.parse(key) as [
    FloodGuardDataOptions["studyArea"],
    FloodGuardDataOptions["role"],
    string | null,
  ];
  return {
    studyArea,
    role,
    evidenceContextId: evidenceContextId ?? undefined,
  };
}

export function useFloodGuardData(
  requested: FloodGuardDataOptions | StudyAreaId = "fixture_thailand_demo",
): FloodGuardData {
  const options = normalizeDataOptions(requested);
  const contextKey = dataOptionsKey(options);
  const offlineFallback = useMemo(() => {
    const fallbackOptions = dataOptionsFromKey(contextKey);
    return fallbackOptions.studyArea === "mae_sai_candidate_v1"
      ? getMaeSaiOfflineData(undefined, fallbackOptions)
      : getOfflineData(undefined, fallbackOptions);
  }, [contextKey]);
  const [resolved, setResolved] = useState<{ key: string; data: FloodGuardData }>(() => ({
    key: contextKey,
    data: offlineFallback,
  }));

  useEffect(() => {
    let active = true;
    const activeOptions = dataOptionsFromKey(contextKey);
    loadFloodGuardData(undefined, undefined, activeOptions).then((next) => {
      if (active) setResolved({ key: contextKey, data: next });
    });
    return () => {
      active = false;
    };
  }, [contextKey]);

  return resolved.key === contextKey ? resolved.data : offlineFallback;
}
