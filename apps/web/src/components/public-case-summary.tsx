"use client";

import { useState } from "react";
import type { EvidenceLibraryPackage, FinalsServiceId, FinalsTravelMode } from "@floodguard/contracts";
import { SERVICE_NAMES } from "./finals-analysis";
import styles from "./evidence-library.module.css";

/** A public explanation of the same checksum-verified research package. */
export function PublicCaseSummary({ evidence, th }: { evidence: EvidenceLibraryPackage; th: boolean }) {
  const analysis = evidence.decision_brief?.finals_analysis;
  const [serviceId, setServiceId] = useState<FinalsServiceId>(() => {
    const selected = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("service");
    return analysis?.services.find((item) => item.id === selected)?.id ?? analysis?.primary_service ?? "hospital";
  });
  const [mode, setMode] = useState<FinalsTravelMode>(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mode") === "modelled_vehicle" ? "modelled_vehicle" : "walking");
  if (!analysis) return <section className={styles.panel}><h2>{th ? "ข้อมูลประกอบพื้นที่" : "Evidence context only"}</h2><p>{th ? "ยังไม่มีการวิเคราะห์บริการแยกประเภทสำหรับพื้นที่นี้ ดูหลักฐานและข้อจำกัดในคลังข้อมูล" : "This surrounding area supplies evidence and routing context. A standalone service-specific result has not been computed."}</p></section>;
  const service = analysis.services.find((s) => s.id === serviceId);
  const variant = service?.variants.find((v) => v.travel_mode === mode && v.speed_factor === 1);
  const flood = serviceId === "hospital" ? analysis.flood_scenarios?.[mode] : undefined;
  const n = (value: number) => value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
  const query = new URLSearchParams({ aoi: evidence.aoi_id, event: evidence.event_id, service: serviceId, mode });
  return <section className={`${styles.panel} ${styles.briefLead}`} data-public-case-summary>
    <p className={styles.eyebrow}>{th ? "สถานการณ์วิจัย · ความเชื่อมั่นต่ำ" : "RESEARCH SCENARIO · LOW CONFIDENCE"}</p>
    <h2>{th ? "การเข้าถึงบริการเปลี่ยนอย่างไร?" : "How could access to services change?"}</h2>
    <div className={styles.selectors}>
      <label>{th ? "บริการ" : "Service"}<select value={serviceId} onChange={(e) => setServiceId(e.target.value as FinalsServiceId)}>{analysis.services.map((s) => <option key={s.id} value={s.id}>{SERVICE_NAMES[s.id][th ? 1 : 0]}</option>)}</select></label>
      <label>{th ? "การเดินทาง" : "Travel mode"}<select value={mode} onChange={(e) => setMode(e.target.value as FinalsTravelMode)}><option value="walking">{th ? "แบบจำลองการเดิน" : "Walking model"}</option><option value="modelled_vehicle">{th ? "แบบจำลองยานพาหนะ" : "Vehicle model"}</option></select></label>
    </div>
    {evidence.aoi_id.startsWith("aoi-05") || evidence.aoi_id.startsWith("aoi-06") ? <p className={styles.notice}>{th ? "ปี 2024 และ 2025 ใช้กรณีฐานการเข้าถึงเดียวกัน ไม่ใช่การเปรียบเทียบผลน้ำท่วมสองปี เส้นทางนอก AOI ยังไม่ได้ประเมิน" : "The 2024 and 2025 selections share the same access baseline. Identical values do not compare flood impacts between years. Paths beyond the AOI are not evaluated."}</p> : null}
    <p>{flood ? (th ? "ทดสอบปิดช่วงถนนที่ตัดกับขอบเขตน้ำท่วมผู้สมัครจากดาวเทียม ไม่ใช่หลักฐานว่าถนนปิดจริง" : "Road closures are imposed where roads intersect the satellite flood candidate. These are not observed closures.") : (th ? "การเปรียบเทียบนี้ใช้การปิดถนนหรือหยุดบริการสมมติ ยังไม่มีผลน้ำท่วมที่รับรองสำหรับบริการนี้" : "This service comparison uses explicit hypothetical disruptions. It is not an estimate of observed flood impacts.")}</p>
    {variant ? <>
      <div className={styles.briefStats}>
        <div><span>{th ? "ประชากรตามแบบจำลองปี 2020" : "Modelled residents (2020)"}</span><strong>{n(variant.baseline.modelled_population)}</strong></div>
        <div><span>{th ? "กรณีฐาน: ภายใน 30 นาที" : "Baseline: within 30 minutes"}</span><strong>{n(variant.baseline.within_30_minutes_population)}</strong></div>
        <div><span>{th ? "จุดหมายผู้สมัคร ไม่ยืนยันการเปิดบริการ" : "Candidate destinations; operation unverified"}</span><strong>{service?.facilities}</strong></div>
      </div>
      {flood ? <p className={styles.notice}><strong>{n(flood.impact.losing_30_min_access)}</strong> {th ? "คนตามแบบจำลองสูญเสียการเข้าถึงภายใน 30 นาทีในสถานการณ์น้ำท่วมผู้สมัคร" : "modelled residents lose 30-minute access under the candidate-flood closure scenario."} {th ? "ไม่ใช่จำนวนผู้ประสบภัย" : "This is not a count of flood victims."}</p> : null}
      <p>{th ? "เชื่อมถนนแต่ไม่มีเส้นทางถึงบริการ" : "Connected to roads but no route to this service"}: <strong>{n(variant.baseline.connected_without_route_population)}</strong>. {th ? "ยังไม่ทราบการเข้าถึงเพราะเชื่อมถนนไม่ได้" : "Access unknown because no connector is accepted"}: <strong>{n(variant.baseline.unknown_access_population)}</strong>.</p>
      <p>{th ? "ควรตรวจสอบจุดหมาย ทางเข้า และส่วนถนนที่ประชากรพึ่งพา ก่อนตีความว่าพื้นที่ถูกตัดขาด" : "Investigate destination coverage, entrances and consequential road connections before interpreting these gaps as isolation."}</p>
    </> : <p role="status" className={styles.empty}>{th ? "บริการนี้ยังใช้วิเคราะห์ไม่ได้ ไม่มีการแทนด้วยบริการอื่น" : "This service is unavailable. Another service is not substituted."} {service?.reason}</p>}
    <p><strong>{th ? "FPPS / ระดับที่รับรอง: ยังไม่มี" : "Accepted FPPS / action class: unavailable."}</strong> {flood ? (th ? "ขาดความน่าจะเป็นน้ำท่วมที่สอบเทียบและข้อมูลความเปราะบางที่สอดคล้องกัน ค่า E ในการทดลองหมายถึงความเชื่อมั่นต่ำ ไม่ใช่ปลอดภัย" : "Calibrated flood likelihood and compatible vulnerability/context are missing. Class E in completed sensitivity scenarios means low confidence, not safety.") : (th ? "ขาดขอบเขตน้ำท่วมที่ใช้ได้ ความน่าจะเป็นที่สอบเทียบ และข้อมูลความเปราะบางที่สอดคล้องกัน" : "An admissible flood extent, calibrated likelihood and compatible vulnerability/context are missing.")}</p>
    <nav className={styles.caseLinks} aria-label={th ? "ตรวจสอบผลเดียวกัน" : "Explore this same case"}>
      <a className={styles.download} href={`/studio/brief/?${query}`}>{th ? "ดูแผนที่เส้นทางก่อน/หลัง" : "View before/after route map"}</a>
      <a href={`/command/cases/?${query}`}>{th ? "เปรียบเทียบใน Command" : "Compare in Command"}</a>
      <a href={`/studio/library/?${query}`}>{th ? "ข้อมูลและกราฟระดับน้ำ" : "Evidence and gauge plots"}</a>
    </nav>
    <p className={styles.hint}>{th ? "ข้อมูลหลายปี: ประชากร 2020 ขอบเขต 2022 ถนนเก็บในปี 2026 ไม่ใช่การสร้างเหตุการณ์ย้อนหลังที่สมบูรณ์" : "Mixed years: population 2020, boundaries 2022, OSM acquired in 2026. This is not a complete historical reconstruction."}</p>
    <details><summary>{th ? "ข้อจำกัดที่อาจเปลี่ยนข้อสรุป" : "What could change the conclusion?"}</summary><ul>{analysis.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p className={styles.hash}>SHA-256: {analysis.analysis_sha256}</p></details>
  </section>;
}
