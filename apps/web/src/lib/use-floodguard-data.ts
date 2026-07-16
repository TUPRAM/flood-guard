"use client";

import { useEffect, useState } from "react";

import { getOfflineData, loadFloodGuardData } from "./data-provider";
import type { FloodGuardData } from "./types";

export function useFloodGuardData(): FloodGuardData {
  const [data, setData] = useState<FloodGuardData>(() => getOfflineData());

  useEffect(() => {
    let active = true;
    loadFloodGuardData().then((next) => {
      if (active) setData(next);
    });
    return () => {
      active = false;
    };
  }, []);

  return data;
}
