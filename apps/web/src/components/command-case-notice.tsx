"use client";

import { useEffect, useState } from "react";
import type { EvidenceLibraryCatalog } from "@floodguard/contracts";

import { PLANNING_OVERVIEW_ROUTE, readCaseSelection, resolveEvidenceCase } from "@/lib/case-selection";
import type { Language } from "@/lib/types";

import styles from "./command-case-notice.module.css";

/**
 * The published catalogue of study cases (EVIDENCE_CATALOG_URL in @/lib/evidence-library). The address is repeated
 * here, and the catalogue is read with the small reader below, so that the map workspace does not load the parsers
 * of the evidence library for one line of text.
 */
export const CASE_CATALOGUE_URL = "/evidence-library/catalog.json";

/** What this line reads of the catalogue: its version, and the ids and names of its areas, events and cases. */
export type CaseCatalogue = Pick<EvidenceLibraryCatalog, "package_version" | "aois" | "events" | "packages">;

/** The catalogue, when it has those parts in their expected form; otherwise nothing, and the line names no case. */
export function readCaseCatalogue(value: unknown): CaseCatalogue | null {
  const record = (item: unknown): item is Record<string, unknown> => item !== null && typeof item === "object" && !Array.isArray(item);
  const named = (item: unknown) => record(item) && typeof item.id === "string" && typeof item.name === "string"
    && (item.name_th === undefined || typeof item.name_th === "string");
  const cases = (item: unknown) => record(item) && typeof item.id === "string" && typeof item.aoi_id === "string" && typeof item.event_id === "string";
  if (!record(value) || typeof value.package_version !== "string"
    || !Array.isArray(value.aois) || !value.aois.every(named)
    || !Array.isArray(value.events) || !value.events.every(named)
    || !Array.isArray(value.packages) || !value.packages.every(cases)) return null;
  return value as unknown as CaseCatalogue;
}

/**
 * One line at the head of the map workspace when its address names a study case. Since the owner's request of
 * 5 Oct 2026 (decision log R19) the "Planning" link of every header, and of the eight published case briefs, opens
 * the workspace with the case in the address. The workspace does not read the case: it always shows the retained
 * Mae Sai comparison. This line says which case the link named and that the map does not show it, and leads to the
 * planning overview of that case. It shows no score and no class.
 */
export function CommandCaseNoticeLine({ search, language, catalog, page = "workspace" }: {
  search: string;
  language: Language;
  catalog: CaseCatalogue | null;
  /** Which page shows the line: the older map workspace, or the Command exercise replay at /command/. */
  page?: "workspace" | "exercise";
}) {
  const selection = readCaseSelection(search);
  if (!selection.aoi && !selection.event) return null;
  const th = language === "th";
  // A case is named only when the published catalogue holds it under this address: an unknown case, half a case or
  // another version is not given a name here, and the overview says what is wrong with the link.
  const reference = catalog ? resolveEvidenceCase(catalog, selection).reference : null;
  const aoi = reference ? catalog?.aois.find((item) => item.id === reference.aoi_id) : undefined;
  const event = reference ? catalog?.events.find((item) => item.id === reference.event_id) : undefined;
  const name = aoi && event ? `${th ? aoi.name_th ?? aoi.name : aoi.name} — ${th ? event.name_th ?? event.name : event.name}` : null;
  return (
    <aside className={styles.notice} aria-label={th ? "กรณีศึกษาที่เลือก" : "Selected case"} data-command-case-notice={name && reference ? reference.id : "unnamed"}>
      <p>
        <strong>
          {name
            ? (th ? `กรณีศึกษาที่เลือก: ${name}` : `Selected case: ${name}.`)
            : (th ? "ลิงก์ที่เปิดหน้านี้ระบุกรณีศึกษาไว้" : "The link that opened this page names a study case.")}
        </strong>{" "}
        {page === "exercise" ? (th
          ? "หน้านี้เป็นการฝึกซ้อมย้อนเหตุการณ์น้ำท่วมแม่สาย เดือนกันยายน 2567 (2024) และไม่ได้แสดงผลของกรณีศึกษานั้น"
          : "This page replays the Mae Sai flood of September 2024 as an exercise. It does not show the results of that case.") : th
          ? "แผนที่นี้ไม่ได้แสดงผลของกรณีศึกษานั้น แสดงเฉพาะผลเปรียบเทียบงานวิจัยแม่สายที่เก็บไว้เท่านั้น"
          : "This map does not show the results of that case. It shows the retained Mae Sai research comparison only."}
      </p>
      <a href={`${PLANNING_OVERVIEW_ROUTE}${search}`} data-command-case-overview-link="true">
        {name
          ? (th ? `ภาพรวมเพื่อการวางแผนของ ${name}` : `Planning overview of ${name}`)
          : (th ? "ภาพรวมเพื่อการวางแผนของกรณีศึกษานั้น" : "Planning overview of that case")}
      </a>
    </aside>
  );
}

/** The line above, with the published catalogue of cases. Nothing is requested when the address names no case. */
export function CommandCaseNotice({ search, language, page = "workspace" }: { search: string | null; language: Language; page?: "workspace" | "exercise" }) {
  const [catalog, setCatalog] = useState<CaseCatalogue | null>(null);
  const selection = readCaseSelection(search ?? "");
  const named = Boolean(selection.aoi || selection.event);

  useEffect(() => {
    if (!named) return;
    const controller = new AbortController();
    fetch(CASE_CATALOGUE_URL, { signal: controller.signal })
      .then(async (response) => (response.ok ? readCaseCatalogue(await response.json()) : null))
      .then((value) => { if (!controller.signal.aborted) setCatalog(value); })
      // Without the catalogue the line stays in its form without a name; the link still carries the case.
      .catch(() => undefined);
    return () => controller.abort();
  }, [named]);

  return search === null ? null : <CommandCaseNoticeLine search={search} language={language} catalog={catalog} page={page} />;
}
