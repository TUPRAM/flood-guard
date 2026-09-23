"use client";

import { useEffect, useState } from "react";
import { caseHref, pushCaseSelection, readCaseSelection, type CaseSelection } from "@/lib/case-selection";
import { PUBLIC_CASE_CATALOG_URL, fetchPublicCase, parsePublicCaseCatalog, type PublicCaseCatalog, type PublicCaseProjection, type PublicCaseService } from "@/lib/public-case-projection";
import type { Language } from "@/lib/types";
import { GenerationTimes } from "./generation-times";
import { MainRoadStatus } from "./main-road-status";

const SERVICE_NAMES: Record<PublicCaseService, { en: string; th: string }> = {
  hospital: { en: "Hospital care", th: "โรงพยาบาล" },
  primary_care: { en: "Primary care", th: "บริการปฐมภูมิ" },
  pharmacy: { en: "Pharmacy", th: "ร้านขายยา" },
  shelter: { en: "Shelter", th: "ศูนย์พักพิง" },
  main_road: { en: "Main-road access — unavailable", th: "ถนนสายหลัก — ยังไม่มีผลการเข้าถึง" },
};

export function PublicResearchCase({ language }: { language: Language }) {
  const [catalog, setCatalog] = useState<PublicCaseCatalog | null>(null);
  const [selection, setSelection] = useState<CaseSelection>(() => typeof window === "undefined" ? {} : readCaseSelection(window.location.search));
  const [loaded, setLoaded] = useState<{ id: string; value: PublicCaseProjection | null; error: string | null }>({ id: "", value: null, error: null });
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const th = language === "th";

  useEffect(() => {
    const controller = new AbortController();
    fetch(PUBLIC_CASE_CATALOG_URL, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
      return parsePublicCaseCatalog(await response.json());
    }).then((value) => { if (!controller.signal.aborted) { setCatalog(value); if (readCaseSelection(window.location.search).aoi) setExpanded(true); } })
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    const onPopState = () => setSelection(readCaseSelection(window.location.search));
    window.addEventListener("popstate", onPopState);
    return () => { controller.abort(); window.removeEventListener("popstate", onPopState); };
  }, []);

  const invalidPair = Boolean(selection.aoi) !== Boolean(selection.event);
  const invalidVersion = Boolean(catalog && selection.version && selection.version !== catalog.package_version);
  const reference = !invalidPair && !invalidVersion
    ? catalog?.packages.find((item) => selection.aoi || selection.event
      ? item.aoi_id === selection.aoi && item.event_id === selection.event
      : item.id === catalog.packages[0]?.id)
    : null;

  useEffect(() => {
    if (!catalog || !reference) return;
    const controller = new AbortController();
    fetchPublicCase(catalog, reference, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setLoaded({ id: reference.sha256, value, error: null }); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setLoaded({ id: reference.sha256, value: null, error: error instanceof Error ? error.message : "Case unavailable" }); });
    return () => controller.abort();
  }, [catalog, reference]);

  // A stale response from a previous selection is never rendered for this one.
  const evidence = reference?.sha256 === loaded.id ? loaded.value : null;
  const error = reference?.sha256 === loaded.id ? loaded.error : null;
  const aoi = catalog?.aois.find((item) => item.id === reference?.aoi_id);
  const event = catalog?.events.find((item) => item.id === reference?.event_id);
  const serviceId = selection.service ?? "hospital";
  const mode = selection.mode ?? "walking";
  const service = evidence?.services.find((item) => item.id === serviceId);
  const variant = service?.variants.find((item) => item.travel_mode === mode);
  const invalidService = Boolean(evidence && selection.service && !service);
  const invalidMode = Boolean(evidence && selection.mode && mode !== "walking" && mode !== "modelled_vehicle");
  const invalidScenario = Boolean(evidence && selection.scenario && selection.scenario !== variant?.candidate_flood_scenario_id);
  const query = { ...selection, aoi: reference?.aoi_id, event: reference?.event_id, version: catalog?.package_version };
  const number = (value: number) => value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
  const choose = (next: CaseSelection) => {
    setSelection(next);
    pushCaseSelection(next);
  };

  return <details className="public-research-details" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}><summary>{th ? "สำรวจกรณีศึกษา: แม่สาย หาดใหญ่ และเจ้าพระยา" : "Explore study cases: Mae Sai, Hat Yai and Chao Phraya"}</summary><section className="public-research-case" aria-labelledby="public-research-title" data-public-research-case>
    <h2 id="public-research-title">{th ? "กรณีศึกษาและการเตรียมพร้อม" : "Study case and preparation"}</h2>
    <p>{th ? "ผลวิจัยความเชื่อมั่นต่ำสำหรับการเรียนรู้ ไม่ใช่คำเตือนหรือคำแนะนำเส้นทางปัจจุบัน" : "Low-confidence research for learning; not a current warning or route instruction."}</p>
    {catalogError ? <p role="alert">{th ? "ข้อมูลกรณีศึกษาใช้ไม่ได้" : "Study case unavailable"}: {catalogError}</p> : null}
    {!catalog && !catalogError ? <p role="status">{th ? "กำลังโหลดกรณีศึกษา…" : "Loading study cases…"}</p> : null}
    {catalog ? <>
      <label>{th ? "พื้นที่ศึกษา — เหตุการณ์" : "Study area — Event"}<select value={reference?.id ?? ""} onChange={(event) => {
        const next = catalog.packages.find((item) => item.id === event.target.value);
        if (next) choose({ aoi: next.aoi_id, event: next.event_id, version: catalog.package_version });
      }}>
        {!reference ? <option value="" disabled>{th ? "ไม่มีผลสำหรับลิงก์นี้" : "No result for this link"}</option> : null}
        {catalog.packages.map((item) => {
          const area = catalog.aois.find((row) => row.id === item.aoi_id);
          const period = catalog.events.find((row) => row.id === item.event_id);
          return <option key={item.id} value={item.id}>{th ? area?.name_th : area?.name} — {th ? period?.name_th : period?.name}</option>;
        })}
      </select></label>
      {!reference ? <p role="alert">{invalidVersion ? (th ? "เวอร์ชันของลิงก์ไม่ตรงกับชุดข้อมูลที่เผยแพร่" : "The link's package version differs from the published cases.") : (th ? "ไม่พบพื้นที่และเหตุการณ์ในลิงก์นี้ จะไม่ใช้กรณีอื่นแทน" : "This area and event are unavailable. Another case is not substituted.")}</p> : null}
      {error ? <p role="alert">{th ? "ชุดข้อมูลตรวจสอบไม่ผ่าน" : "Case verification failed"}: {error}</p> : null}
      {reference && !evidence && !error ? <p role="status">{th ? "กำลังตรวจสอบข้อมูลกรณีศึกษา…" : "Verifying study case…"}</p> : null}
      {evidence && aoi && event ? <>
        <p><strong>{th ? aoi.name_th : aoi.name} — {th ? event.name_th : event.name}</strong> · {event.start}–{event.end}</p>
        <p>{th ? "บทบาทหลักฐาน: สถานการณ์วิจัย ความเชื่อมั่นต่ำ" : "Evidence role: candidate research, low confidence"} · {th ? "FPPS / ชั้นการตัดสินใจที่รับรอง: ยังไม่มี" : "Accepted FPPS / action class: unavailable"}</p>
        <div className="public-research-controls">
          <label>{th ? "บริการ" : "Service"}<select value={invalidService || !evidence.services.length ? "" : serviceId} onChange={(event) => choose({ ...selection, service: event.target.value, version: catalog.package_version, aoi: evidence.aoi_id, event: evidence.event_id })}>
            {invalidService || !evidence.services.length ? <option value="" disabled>{th ? "ยังไม่มีบริการที่วิเคราะห์ได้" : "No eligible service result"}</option> : null}
            {evidence.services.map((item) => <option key={item.id} value={item.id} disabled={item.id === "main_road"}>{SERVICE_NAMES[item.id][language]}</option>)}
            {!evidence.services.some((item) => item.id === "main_road") ? <option value="main_road" disabled>{SERVICE_NAMES.main_road[language]}</option> : null}
          </select></label>
          <label>{th ? "การเดินทาง" : "Travel mode"}<select value={invalidMode ? "" : mode} onChange={(event) => choose({ ...selection, mode: event.target.value, version: catalog.package_version, aoi: evidence.aoi_id, event: evidence.event_id })}>
            {invalidMode ? <option value="" disabled>{th ? "วิธีเดินทางที่ไม่รองรับ" : "Unsupported mode"}</option> : null}
            <option value="walking">{th ? "แบบจำลองการเดิน" : "Walking model"}</option><option value="modelled_vehicle">{th ? "แบบจำลองยานพาหนะ" : "Vehicle model"}</option>
          </select></label>
        </div>
        {invalidService || invalidMode || invalidScenario ? <p role="alert">{th ? "ไม่มีผลสำหรับบริการ วิธีเดินทาง หรือสถานการณ์นี้ จะไม่ใช้ผลอื่นแทน" : "No result exists for this service, mode or scenario. Another result is not substituted."} {invalidScenario ? <button type="button" onClick={() => choose({ ...selection, scenario: undefined })}>{th ? "ล้างสถานการณ์ที่ไม่เข้ากัน" : "Clear incompatible scenario"}</button> : null}</p>
          : variant ? <>
            <p><strong>{number(variant.within_30_minutes_population)}</strong> / {number(variant.modelled_population)} {th ? `คนตามแบบจำลองปี ${evidence.population_reference_year ?? "ไม่ทราบ"} เข้าถึงบริการภายใน 30 นาทีในกรณีฐาน` : `modelled residents (${evidence.population_reference_year ?? "year unknown"}) reach this service within 30 minutes at baseline`}.</p>
            {variant.candidate_flood_losing_30_min_access !== null ? <p><strong>{number(variant.candidate_flood_losing_30_min_access)}</strong> {th ? "คนตามแบบจำลองสูญเสียการเข้าถึงภายใน 30 นาที เมื่อสมมติปิดถนนที่ตัดขอบเขตน้ำท่วมผู้สมัคร ไม่ใช่การปิดจริง" : "modelled residents lose 30-minute access when roads intersecting the flood candidate are assumed closed; closures are not observed."}</p>
              : <p>{th ? "ยังไม่มีผลน้ำท่วมผู้สมัครที่เข้ากันได้กับบริการและวิธีเดินทางนี้" : "No compatible flood-candidate consequence is available for this service and mode."}</p>}
            <p>{th ? "ไม่ทราบการเข้าถึงเพราะไม่มีจุดเชื่อมที่รับรอง" : "Access unknown without an accepted connector"}: {number(variant.unknown_access_population)}. {th ? "เชื่อมถนนแต่ไม่มีเส้นทางถึงบริการ" : "Connected to roads but no service route"}: {number(variant.connected_without_route_population)}.</p>
          </> : <p role="status">{serviceId === "main_road"
            ? (th ? "การเข้าถึงถนนสายหลักยังไม่มีผลแยกที่ผ่านการตรวจสอบ" : "Main-road access has no separately qualified result.")
            : service?.reason ?? (th ? "ยังไม่มีผลการเข้าถึงสำหรับพื้นที่นี้" : "Service access is unavailable for this area.")}</p>}
        <p>{th ? "ประชากรตามแบบจำลองไม่ใช่จำนวนผู้ประสบภัย ความจุและการเปิดใช้สถานที่ช่วงเหตุการณ์ยังไม่ทราบ" : "Modelled residents are not a victim count. Event-time facility operation and capacity remain unknown."}</p>
        <MainRoadStatus th={th} />
        <p>{th ? "เวลาสังเกตการณ์ของแหล่งข้อมูล" : "Source observation time"}: {variant?.candidate_flood_source_timestamp ?? evidence.source_timestamp ?? (th ? "หลายช่วงเวลา ดูแหล่งข้อมูล" : "mixed source periods; inspect sources")} · {th ? "แพ็กเกจ" : "Package"}: <code>{evidence.id}</code></p>
        <GenerationTimes sourceAnalysisGeneratedAt={evidence.source_analysis_generated_at} releaseGeneratedAt={evidence.generated_at} th={th} />
        <nav aria-label={th ? "ตรวจสอบกรณีเดียวกัน" : "Inspect the same case"}><a href={caseHref("/command/", query)}>{th ? "ดูการวางแผน" : "Open Planning"}</a><a href={caseHref("/studio/", query)}>{th ? "ตรวจสอบหลักฐาน" : "Inspect Studio"}</a></nav>
        <details><summary>{th ? "ข้อจำกัดของกรณีศึกษา" : "Case limitations"}</summary><p>{evidence.reporting_scope}</p><ul>{evidence.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p>SHA-256: {evidence.source_package_sha256}</p></details>
      </> : null}
    </> : null}
  </section></details>;
}
