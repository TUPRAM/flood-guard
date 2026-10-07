"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  PUBLIC_REPORT_LIMIT,
  PUBLIC_REPORT_STORAGE_KEY,
  createPublicReport,
  parseStoredPublicReports,
  readStoredPublicReports,
  writeStoredPublicReports,
  type CreatePublicReportInput,
  type PublicReport,
} from "./public-report";

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function usePublicReports() {
  const [reports, setReports] = useState<PublicReport[]>([]);
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    setReports(readStoredPublicReports(browserStorage()));
  }, []);

  const addReport = useCallback((input: CreatePublicReportInput): PublicReport => {
    const timestamp = new Date().toISOString();
    const report = createPublicReport(input, timestamp, createReportId(timestamp));

    setReports((current) => {
      const next = [report, ...current].slice(0, PUBLIC_REPORT_LIMIT);
      writeStoredPublicReports(browserStorage(), next);
      return next;
    });

    return report;
  }, []);

  return { reports, addReport } as const;
}

const NO_REPORTS: PublicReport[] = [];
let storedSnapshot: { raw: string | null; reports: PublicReport[] } = { raw: null, reports: NO_REPORTS };

/** The stored reports as one list that stays the same object until the stored text changes. */
function storedReportsSnapshot(): PublicReport[] {
  let raw: string | null = null;
  try {
    raw = browserStorage()?.getItem(PUBLIC_REPORT_STORAGE_KEY) ?? null;
  } catch {
    raw = null;
  }
  if (raw !== storedSnapshot.raw) storedSnapshot = { raw, reports: raw ? parseStoredPublicReports(raw) : NO_REPORTS };
  return storedSnapshot.reports;
}

function subscribeToStoredReports(notify: () => void): () => void {
  // A report saved in another tab of this browser arrives as a `storage` event; coming back to this tab re-reads too.
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === PUBLIC_REPORT_STORAGE_KEY) notify();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("focus", notify);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("focus", notify);
  };
}

/**
 * The reports the Public page has saved in this browser, read only, and kept up to date: a report saved in another
 * tab shows without a reload. Nothing is sent anywhere; the reports never leave this device.
 */
export function useStoredPublicReports(): PublicReport[] {
  return useSyncExternalStore(subscribeToStoredReports, storedReportsSnapshot, () => NO_REPORTS);
}

function createReportId(timestamp: string): string {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return `public-report:${crypto.randomUUID()}`;
    }
  } catch {
    // Fall through to a device-local, non-identifying ID.
  }

  const timestampPart = timestamp.replaceAll(/[^0-9]/gu, "");
  const randomPart = Math.random().toString(36).slice(2, 12);
  return `public-report:${timestampPart}:${randomPart}`;
}
