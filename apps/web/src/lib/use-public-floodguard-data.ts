"use client";

import { useEffect, useMemo, useState } from "react";

import {
  getPublicOfflineData,
  loadPublicFloodGuardData,
} from "./public-data-provider";
import type { PublicFloodGuardData } from "./types";

/** Public-only loader; its module graph contains no command or Studio data bundle. */
export function usePublicFloodGuardData(
  evidenceContextId?: string,
): PublicFloodGuardData {
  const contextKey = JSON.stringify([evidenceContextId ?? null]);
  const offlineFallback = useMemo(() => (
    getPublicOfflineData(undefined, publicContextIdFromKey(contextKey))
  ), [contextKey]);
  const [resolved, setResolved] = useState<{ key: string; data: PublicFloodGuardData }>(() => ({
    key: contextKey,
    data: offlineFallback,
  }));

  useEffect(() => {
    let active = true;
    loadPublicFloodGuardData(undefined, publicContextIdFromKey(contextKey)).then((next) => {
      if (active) setResolved({ key: contextKey, data: next });
    });
    return () => {
      active = false;
    };
  }, [contextKey]);

  return resolved.key === contextKey ? resolved.data : offlineFallback;
}

function publicContextIdFromKey(key: string): string | undefined {
  const [evidenceContextId] = JSON.parse(key) as [string | null];
  return evidenceContextId ?? undefined;
}
