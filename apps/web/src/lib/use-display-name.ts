"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  normalizeDisplayName,
  resolveInitialDisplayName,
  writeStoredDisplayName,
} from "./public-display-name";

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Optional greeting name held on this device only, hydrated after mount so the
 * server-rendered markup stays identical for every visitor.
 */
export function useDisplayName() {
  const [displayName, setDisplayName] = useState("");
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    setDisplayName(resolveInitialDisplayName(browserStorage()));
  }, []);

  const changeDisplayName = useCallback((value: string) => {
    const normalized = normalizeDisplayName(value);
    writeStoredDisplayName(browserStorage(), normalized);
    setDisplayName(normalized);
  }, []);

  return { displayName, changeDisplayName } as const;
}
