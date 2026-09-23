"use client";

import { useEffect, useState } from "react";
import type { EvidenceLibraryCatalog, EvidenceLibraryPackage } from "@floodguard/contracts";
import { caseHref, pushCaseSelection, readCaseSelection, resolveAnalysisSelection, resolveEvidenceCase, type CaseSelection } from "@/lib/case-selection";
import { EVIDENCE_CATALOG_URL, fetchEvidencePackage, parseEvidenceCatalog } from "@/lib/evidence-library";
import { useLanguage } from "@/lib/use-language";
import { SERVICE_NAMES } from "./finals-analysis";
import { GenerationTimes } from "./generation-times";
import { MainRoadStatus } from "./main-road-status";
import styles from "./candidate-case-context.module.css";

export function CandidateCaseContext({ role }: { role: "planning" | "studio" }) {
  const [language] = useLanguage("en");
  const th = language === "th";
  const [catalog, setCatalog] = useState<EvidenceLibraryCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selection, setSelection] = useState<CaseSelection>(() => typeof window === "undefined" ? {} : readCaseSelection(window.location.search));
  const [loaded, setLoaded] = useState<{ hash: string; value: EvidenceLibraryPackage | null; error: string | null }>({ hash: "", value: null, error: null });

  useEffect(() => {
    const controller = new AbortController();
    fetch(EVIDENCE_CATALOG_URL, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
      return parseEvidenceCatalog(await response.json());
    }).then((value) => { if (!controller.signal.aborted) setCatalog(value); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    const onPopState = () => setSelection(readCaseSelection(window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => { controller.abort(); window.removeEventListener("popstate", onPopState); };
  }, []);

  const resolved = catalog ? resolveEvidenceCase(catalog, selection) : null;
  const reference = resolved?.reference;
  useEffect(() => {
    if (!catalog || !reference) return;
    const controller = new AbortController();
    fetchEvidencePackage(catalog, reference, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setLoaded({ hash: reference.sha256, value, error: null }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoaded({ hash: reference.sha256, value: null, error: error instanceof Error ? error.message : "Package unavailable" }); });
    return () => controller.abort();
  }, [catalog, reference]);

  const evidence = reference?.sha256 === loaded.hash ? loaded.value : null;
  const error = reference?.sha256 === loaded.hash ? loaded.error : null;
  const analysis = evidence?.decision_brief?.finals_analysis;
  const choice = analysis ? resolveAnalysisSelection(analysis, selection) : null;
  const service = analysis?.services.find((item) => item.id === choice?.service);
  const variant = service?.variants.find((item) => item.travel_mode === choice?.mode && item.speed_factor === 1);
  const selectedRoute = analysis?.routes?.comparisons.find((item) => item.id === selection.scenario);
  const flood = choice?.service === "hospital" && choice.mode
    && (!selection.scenario || selection.scenario === analysis?.flood_scenarios?.[choice.mode]?.impact.id
      || (selectedRoute?.scenario_kind === "close_edge" && analysis?.routes?.closure_basis === "candidate_flood"))
    ? analysis?.flood_scenarios?.[choice.mode] : null;
  const aoi = catalog?.aois.find((item) => item.id === reference?.aoi_id);
  const event = catalog?.events.find((item) => item.id === reference?.event_id);
  const query = { ...selection, aoi: reference?.aoi_id, event: reference?.event_id, version: catalog?.package_version };
  const n = (value: number) => value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
  const choose = (next: CaseSelection) => {
    setSelection(next);
    pushCaseSelection(next);
  };

  return <section className={styles.case} aria-labelledby={`${role}-shared-case-title`} data-shared-case={role} data-case-id={evidence?.id}>
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
        {analysis ? <>
          <label>{th ? "บริการ" : "Service"}<select value={choice?.service ?? ""} onChange={(event) => choose({ ...selection, aoi: evidence?.aoi_id, event: evidence?.event_id, version: catalog.package_version, service: event.target.value })}>
            {!choice?.service ? <option value="" disabled>{th ? "บริการที่ไม่รองรับ" : "Unsupported service"}</option> : null}
            {analysis.services.map((item) => <option key={item.id} value={item.id}>{SERVICE_NAMES[item.id][th ? 1 : 0]}</option>)}
            <option value="main_road" disabled>{th ? "ถนนสายหลัก — ยังไม่มีผลการเข้าถึง" : "Main-road access — unavailable"}</option>
          </select></label>
          <label>{th ? "วิธีเดินทาง" : "Travel mode"}<select value={choice?.mode ?? ""} onChange={(event) => choose({ ...selection, aoi: evidence?.aoi_id, event: evidence?.event_id, version: catalog.package_version, mode: event.target.value })}>
            {!choice?.mode ? <option value="" disabled>{th ? "วิธีที่ไม่รองรับ" : "Unsupported mode"}</option> : null}
            <option value="walking">{th ? "แบบจำลองการเดิน" : "Walking model"}</option><option value="modelled_vehicle">{th ? "แบบจำลองยานพาหนะ" : "Vehicle model"}</option>
          </select></label>
        </> : null}
      </div>
      {!reference ? <p className={styles.error} role="alert">{resolved?.reason === "version_mismatch" ? (th ? "เวอร์ชันลิงก์ไม่ตรงกับแพ็กเกจที่เผยแพร่" : "The link's version does not match the published package.") : (th ? "ไม่พบพื้นที่และเหตุการณ์นี้ จะไม่ใช้ข้อมูลอื่นแทน" : "This area and event are unavailable. Another case is not substituted.")}</p> : null}
      {error ? <p className={styles.error} role="alert">{th ? "ตรวจสอบแพ็กเกจไม่ผ่าน" : "Package verification failed"}: {error}</p> : null}
      {reference && !evidence && !error ? <p role="status">{th ? "กำลังตรวจสอบแพ็กเกจ…" : "Verifying case package…"}</p> : null}
      {evidence && aoi && event ? <>
        <p className={styles.identity}><strong>{th ? aoi.name_th ?? aoi.name : aoi.name} — {th ? event.name_th ?? event.name : event.name}</strong><code>{evidence.id}</code><small>{event.start}–{event.end} · {evidence.package_version}</small></p>
        {choice?.reason ? <p className={styles.error} role="alert">{th ? "ไม่มีผลสำหรับบริการ วิธีเดินทาง สถานการณ์ หรือจุดเริ่มต้นนี้ จะไม่ใช้ผลอื่นแทน" : "No result exists for this service, mode, scenario or origin. Another result is not substituted."} <code>{choice.reason}</code> {choice.reason === "unknown_scenario" || choice.reason === "unknown_origin" ? <button type="button" className={styles.reset} onClick={() => { const next = { ...selection, scenario: undefined, origin: undefined }; choose(next); }}>{th ? "ล้างตัวเลือกที่ไม่เข้ากัน" : "Clear incompatible selection"}</button> : null}</p> : <>
          {variant ? <div className={styles.metrics}>
            <div><span>{th ? `ประชากรตามแบบจำลองปี ${analysis?.scope.population_year}` : `Modelled residents (${analysis?.scope.population_year})`}</span><strong>{n(variant.baseline.modelled_population)}</strong></div>
            <div><span>{th ? "เข้าถึงภายใน 30 นาที · กรณีฐาน" : "Within 30 minutes · baseline"}</span><strong>{n(variant.baseline.within_30_minutes_population)}</strong></div>
            <div><span>{flood ? (th ? "สูญเสียการเข้าถึง · สมมติปิดถนน" : "Lose 30-minute access · imposed closures") : (th ? "ผลจากน้ำท่วมผู้สมัคร" : "Candidate-flood consequence")}</span><strong>{flood ? n(flood.impact.losing_30_min_access) : (th ? "ยังไม่มี" : "Unavailable")}</strong></div>
            <div><span>{th ? "FPPS / ชั้นการตัดสินใจที่รับรอง" : "Accepted FPPS / action class"}</span><strong>{th ? "ยังไม่มี" : "Unavailable"}</strong></div>
          </div> : <p role="status">{service?.reason ?? (th ? "ยังไม่มีผลบริการสำหรับกรณีนี้" : "Service result unavailable for this case.")}</p>}
          <p>{flood ? (th ? "ขอบเขตน้ำท่วมผู้สมัครและการปิดถนนเป็นสมมติฐาน ไม่ใช่สภาพถนนที่สังเกต" : "Flood extent is a candidate and road closures are imposed assumptions, not observed conditions.") : (th ? "ไม่มีผลกระทบจากน้ำท่วมที่รับรองสำหรับตัวเลือกนี้" : "No qualified flood consequence exists for this selection.")}</p>
          {role === "planning" ? <p>{evidence.decision_brief?.next_actions[0] ? (th ? "สิ่งที่ควรตรวจสอบต่อ: " : "Next verification task: ") + evidence.decision_brief.next_actions[0].action : (th ? "ตรวจสอบขอบเขตน้ำท่วม ถนน และสถานที่ก่อนตัดสินใจ" : "Verify flood extent, roads and services before a decision.")}</p> : <p>{th ? "ชุดนี้ยังไม่มี FPPS อายุหรือการยอมรับปลายน้ำ ตรวจสอบต้นทาง สิทธิ์ ความครอบคลุม และค่าแฮชในคลังข้อมูล" : "This package has no accepted FPPS, age equity or downstream acceptance. Inspect source rights, coverage and hashes in the library."}</p>}
        </>}
        <MainRoadStatus th={th} />
        <p className={styles.provenance}>{flood ? (th ? "เวลาที่ได้ภาพน้ำท่วมผู้สมัคร" : "Candidate flood acquisition") : (th ? "เวลาสังเกตการณ์ของแหล่งข้อมูล" : "Source observation time")}: {flood?.source_timestamp ?? evidence.source_timestamp ?? (th ? "หลายช่วงเวลา ดูรายละเอียดแหล่งข้อมูล" : "mixed periods; inspect sources")} · SHA-256: <code>{reference?.sha256}</code></p>
        <GenerationTimes className={styles.provenance} sourceAnalysisGeneratedAt={analysis?.generated_at ?? null} releaseGeneratedAt={evidence.generated_at} th={th} />
        <nav aria-label={th ? "มุมมองของกรณีเดียวกัน" : "Views of this same case"}>
          <a href={caseHref("/public/", query)}>{th ? "สรุปสำหรับประชาชน" : "Public summary"}</a>
          <a href={caseHref("/command/", query)}>{th ? "การวางแผน" : "Planning"}</a>
          <a href={caseHref("/studio/", query)}>{th ? "รายงานการตรวจสอบ" : "Studio report"}</a>
          <a href={caseHref("/studio/brief/", query)}>{th ? "เปรียบเทียบเส้นทาง" : "Route comparison"}</a>
          <a href={caseHref("/studio/library/", query)}>{th ? "คลังข้อมูล" : "Evidence library"}</a>
        </nav>
      </> : null}
    </> : null}
  </section>;
}
