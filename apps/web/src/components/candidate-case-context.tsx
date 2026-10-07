"use client";

import { useEffect, useState } from "react";
import type { EvidenceLibraryCatalog, EvidenceLibraryPackage } from "@floodguard/contracts";
import { LanguageToggle } from "./language-toggle";
import { PLANNING_WORKSPACE_ROUTE, STUDIO_CANDIDATE_REPORT_ROUTE, caseHref, pushCaseSelection, readCaseSelection, resolveAnalysisSelection, resolveEvidenceCase, type CaseSelection } from "@/lib/case-selection";
import { EVIDENCE_CATALOG_URL, fetchEvidencePackage, parseEvidenceCatalog } from "@/lib/evidence-library";
import { evidencePackageFailure, type EvidencePackageFailure } from "@/lib/evidence-offline";
import { useLanguage } from "@/lib/use-language";
import { EvidenceOfflineControl, EvidencePackageNotice, useRetryWhenOnline } from "./evidence-offline";
import { SERVICE_NAMES } from "./finals-analysis";
import { GenerationTimes } from "./generation-times";
import styles from "./candidate-case-context.module.css";

export function CandidateCaseContext({ role }: { role: "planning" | "studio" }) {
  const [language, setLanguage] = useLanguage("en");
  const th = language === "th";
  const [catalog, setCatalog] = useState<EvidenceLibraryCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selection, setSelection] = useState<CaseSelection>({});
  const [loaded, setLoaded] = useState<{ hash: string; value: EvidenceLibraryPackage | null; failure: EvidencePackageFailure | null }>({ hash: "", value: null, failure: null });

  useEffect(() => {
    const controller = new AbortController();
    fetch(EVIDENCE_CATALOG_URL, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
      return parseEvidenceCatalog(await response.json());
    }).then((value) => { if (!controller.signal.aborted) setCatalog(value); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    const onPopState = () => setSelection(readCaseSelection(window.location.search));
    onPopState();
    window.addEventListener("popstate", onPopState);
    return () => { controller.abort(); window.removeEventListener("popstate", onPopState); };
  }, []);

  const resolved = catalog ? resolveEvidenceCase(catalog, selection) : null;
  const reference = resolved?.reference;
  const failure = reference?.sha256 === loaded.hash ? loaded.failure : null;
  // A package that could not be reached is requested again when the connection returns.
  const retry = useRetryWhenOnline(Boolean(failure && failure.kind !== "invalid"));
  useEffect(() => {
    if (!catalog || !reference) return;
    const controller = new AbortController();
    fetchEvidencePackage(catalog, reference, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setLoaded({ hash: reference.sha256, value, failure: null }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoaded({ hash: reference.sha256, value: null, failure: evidencePackageFailure(error) }); });
    return () => controller.abort();
  }, [catalog, reference, retry]);

  const evidence = reference?.sha256 === loaded.hash ? loaded.value : null;
  const analysis = evidence?.decision_brief?.finals_analysis;
  const choice = analysis ? resolveAnalysisSelection(analysis, selection) : null;
  const aoi = catalog?.aois.find((item) => item.id === reference?.aoi_id);
  const event = catalog?.events.find((item) => item.id === reference?.event_id);
  const query = reference
    ? { ...selection, aoi: reference.aoi_id, event: reference.event_id, version: catalog?.package_version }
    : selection;
  const choose = (next: CaseSelection) => {
    setSelection(next);
    pushCaseSelection(next);
  };

  return <section className={styles.case} aria-labelledby={`${role}-shared-case-title`} data-shared-case={role} data-case-id={evidence?.id}>
    <header className={styles.header}>
      <a className={styles.brand} href={caseHref(role === "planning" ? PLANNING_WORKSPACE_ROUTE : STUDIO_CANDIDATE_REPORT_ROUTE, query)}>FloodGuard <span>{role === "planning" ? (th ? "การวางแผน" : "Planning") : (th ? "หลักฐาน" : "Studio")}</span></a>
      <nav aria-label={th ? "พื้นที่หลัก" : "Main areas"}>
        <a href={caseHref("/public/", query)}>{th ? "ประชาชน" : "Public"}</a>
        {/* The Planning link is the map workspace at /command/. The planning overview that carries this header is below it, at
            /command/planning/, so there the link marks the current section and does not name the current page. */}
        <a href={caseHref(PLANNING_WORKSPACE_ROUTE, query)} aria-current={role === "planning" ? "true" : undefined}>{th ? "การวางแผน" : "Planning"}</a>
        <a href={caseHref(STUDIO_CANDIDATE_REPORT_ROUTE, query)} aria-current={role === "studio" ? "page" : undefined}>{th ? "หลักฐาน" : "Studio"}</a>
      </nav>
      <LanguageToggle language={language} onChange={setLanguage} />
    </header>
    <div data-app-availability-slot />
    <div className={styles.inner}>
    <div className={styles.heading}>
      <div><p className={styles.eyebrow}>{th ? "กรณีศึกษาร่วม · ไม่ใช้เชิงปฏิบัติการ" : "SHARED CASE · NON-OPERATIONAL"}</p><h2 id={`${role}-shared-case-title`}>{role === "planning" ? (th ? "กรณีศึกษาสำหรับการวางแผน" : "Planning case") : (th ? "หลักฐานกรณีศึกษา" : "Study-case evidence")}</h2></div>
      <span className={styles.badge}>{th ? "ผู้สมัคร · ความเชื่อมั่นต่ำ" : "Candidate · low confidence"}</span>
    </div>
    {catalogError ? <p className={styles.error} role="alert">{th ? "โหลดรายการกรณีศึกษาไม่ได้" : "Case catalog unavailable"}: {catalogError}</p> : null}
    {!catalog && !catalogError ? <p role="status">{th ? "กำลังโหลดรายการกรณีศึกษา…" : "Loading case catalog…"}</p> : null}
    {catalog ? <>
      <div className={styles.controls}>
        <label>{th ? "พื้นที่ศึกษา — เหตุการณ์" : "Study area — Event"}<select value={reference?.id ?? ""} onChange={(event) => {
          const next = catalog.packages.find((item) => item.id === event.target.value);
          if (next) choose({ aoi: next.aoi_id, event: next.event_id, version: catalog.package_version });
        }}>
          {!reference ? <option value="" disabled>{th ? "ไม่มีผลสำหรับลิงก์นี้" : "No result for this link"}</option> : null}
          {catalog.packages.map((item) => {
            const area = catalog.aois.find((row) => row.id === item.aoi_id);
            const period = catalog.events.find((row) => row.id === item.event_id);
            return <option key={item.id} value={item.id}>{th ? area?.name_th ?? area?.name : area?.name} — {th ? period?.name_th ?? period?.name : period?.name}</option>;
          })}
        </select></label>
        {role === "planning" && analysis ? <>
          <label>{th ? "บริการ" : "Service"}<select value={choice?.service ?? ""} onChange={(event) => choose({ ...query, service: event.target.value, scenario: undefined, origin: undefined })}>
            {!choice?.service ? <option value="" disabled>{th ? "บริการที่ไม่รองรับ" : "Unsupported service"}</option> : null}
            {analysis.services.map((item) => <option key={item.id} value={item.id}>{SERVICE_NAMES[item.id][th ? 1 : 0]}</option>)}
            <option value="main_road" disabled>{th ? "ถนนสายหลัก — ยังไม่มีผลการเข้าถึง" : "Main-road access — unavailable"}</option>
          </select></label>
          <label>{th ? "วิธีเดินทาง" : "Travel mode"}<select value={choice?.mode ?? ""} onChange={(event) => choose({ ...query, mode: event.target.value, scenario: undefined, origin: undefined })}>
            {!choice?.mode ? <option value="" disabled>{th ? "วิธีที่ไม่รองรับ" : "Unsupported mode"}</option> : null}
            <option value="walking">{th ? "แบบจำลองการเดิน" : "Walking model"}</option><option value="modelled_vehicle">{th ? "แบบจำลองยานพาหนะ" : "Vehicle model"}</option>
          </select></label>
        </> : null}
      </div>
      {!reference ? <p className={styles.error} role="alert">{resolved?.reason === "version_mismatch" ? (th ? "เวอร์ชันลิงก์ไม่ตรงกับแพ็กเกจที่เผยแพร่" : "The link's version does not match the published package.") : (th ? "ไม่พบพื้นที่และเหตุการณ์นี้ จะไม่ใช้ข้อมูลอื่นแทน" : "This area and event are unavailable. Another case is not substituted.")}</p> : null}
      {failure ? <EvidencePackageNotice failure={failure} th={th} className={styles.error} invalidLabel={th ? "ตรวจสอบแพ็กเกจไม่ผ่าน" : "Package verification failed"} /> : null}
      {reference && !evidence && !failure ? <p role="status">{th ? "กำลังตรวจสอบแพ็กเกจ…" : "Verifying case package…"}</p> : null}
      {evidence && aoi && event ? <>
        <div className={styles.identity}><strong>{th ? aoi.name_th ?? aoi.name : aoi.name} — {th ? event.name_th ?? event.name : event.name}</strong><span>{event.start}–{event.end}</span><span>{th ? "คะแนนและระดับที่รับรอง: ยังไม่มี" : "Accepted FPPS / action class: unavailable"}</span></div>
        {role === "planning" && choice?.reason ? <p className={styles.error} role="alert">{th ? "ไม่มีผลสำหรับตัวเลือกนี้ จะไม่ใช้ผลอื่นแทน" : "No result exists for this selection. Another result is not substituted."} <code>{choice.reason}</code> {choice.reason === "unknown_scenario" || choice.reason === "unknown_origin" ? <button type="button" className={styles.reset} onClick={() => choose({ ...query, scenario: undefined, origin: undefined })}>{th ? "ล้างตัวเลือกที่ไม่เข้ากัน" : "Clear incompatible selection"}</button> : null}</p> : null}
        <p className={styles.caution}>{th ? "ขอบเขตน้ำท่วมเป็นข้อมูลผู้สมัคร การปิดถนนเป็นสมมติฐาน ไม่ใช่สภาพถนนที่สังเกต" : "Candidate flood extent and imposed road closures are assumptions, not observed road conditions."}</p>
        <div className={styles.lowerRow}>
          <nav aria-label={th ? "รายละเอียดกรณีศึกษา" : "Case details"}>
            {/* The link to the map workspace, the other Planning page, stands directly below this block, at the head of the overview. */}
            {role === "planning" ? <a href={caseHref("/command/cases/", query)}>{th ? "เปรียบเทียบเส้นทาง" : "Route comparison"}</a> : <><a href={caseHref("/studio/brief/", query)}>{th ? "บทสรุปและเส้นทาง" : "Decision brief"}</a><a href={caseHref("/studio/library/", query)}>{th ? "คลังหลักฐาน" : "Evidence library"}</a><a href={caseHref("/studio/archive/", query)}>{th ? "รายงานเก่า" : "Historical report"}</a></>}
          </nav>
          <details className={styles.provenance}><summary>{th ? "แหล่งข้อมูลและที่มา" : "Sources and provenance"}</summary><p>{evidence.id} · {evidence.package_version}</p><p>{th ? "เวลาสังเกตการณ์ของแหล่งข้อมูล" : "Source observation time"}: {evidence.source_timestamp ?? (th ? "หลายช่วงเวลา ดูข้อมูลรายแหล่ง" : "mixed periods; see source records")}</p><GenerationTimes sourceAnalysisGeneratedAt={analysis?.generated_at ?? null} releaseGeneratedAt={evidence.generated_at} th={th} /><p>SHA-256: <code>{reference?.sha256}</code></p></details>
        </div>
      </> : null}
      <EvidenceOfflineControl catalog={catalog} aoiId={reference?.aoi_id} th={th} className={styles.offline} />
    </> : null}
    </div>
  </section>;
}
