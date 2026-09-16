"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  PUBLIC_REPORT_LIMIT,
  createPublicReport,
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
  const [sessionOnlyIds, setSessionOnlyIds] = useState<Set<string>>(new Set());
  const currentReports = useRef<PublicReport[]>([]);
  const hydrated = useRef(false);

  useEffect(() => {
    if (hydrated.current) return;
    hydrated.current = true;
    currentReports.current = readStoredPublicReports(browserStorage());
    setReports(currentReports.current);
  }, []);

  const addReport = useCallback((input: CreatePublicReportInput) => {
    const timestamp = new Date().toISOString();
    const report = createPublicReport(input, timestamp, createReportId(timestamp));

    const next = [report, ...currentReports.current].slice(0, PUBLIC_REPORT_LIMIT);
    const persisted = writeStoredPublicReports(browserStorage(), next);
    currentReports.current = next;
    setReports(next);
    setSessionOnlyIds((current) => persisted
      ? new Set()
      : new Set([...current, report.report_id]));

    return { report, persisted };
  }, []);

  return { reports, addReport, sessionOnlyIds } as const;
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
