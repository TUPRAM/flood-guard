"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import type { EvidenceLibraryCatalog, EvidenceLibraryPackage, FinalsServiceId } from "@floodguard/contracts";
import { caseHref, readCaseSelection, resolveAnalysisSelection, resolveEvidenceCase, type CaseSelection } from "@/lib/case-selection";
import { EVIDENCE_CATALOG_URL, fetchEvidencePackage, parseEvidenceCatalog } from "@/lib/evidence-library";
import { useLanguage } from "@/lib/use-language";
import { SERVICE_NAMES } from "./finals-analysis";
import { MainRoadStatus } from "./main-road-status";
import styles from "./planning-candidate-overview.module.css";

const EvidenceMap = dynamic(() => import("./evidence-library-map").then((module) => module.EvidenceLibraryMap), { ssr: false });

const THAI_ACTIONS: Record<string, string> = {
  event_reference: "ตรวจสอบขอบเขตน้ำท่วมที่ระบุวันที่",
  access_review: "ทบทวนจุดเชื่อมต่อและจุดหมายที่มีผลต่อการเข้าถึง",
  demand_capacity: "ยืนยันกลุ่มประชากรและสมมติฐานความจุ",
};

const MAP_LAYER_IDS = new Set(["osm_facilities_geojson", "reporting-subdistricts", "sar-candidate_extent"]);

function number(value: number, th: boolean): string {
  return value.toLocaleString(th ? "th-TH" : "en-GB", { maximumFractionDigits: 0 });
}

export function PlanningCandidateOverview() {
  const [language] = useLanguage("en");
  const th = language === "th";
  const [selection, setSelection] = useState<CaseSelection>({});
  const [catalog, setCatalog] = useState<EvidenceLibraryCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ hash: string; value: EvidenceLibraryPackage | null; error: string | null }>({ hash: "", value: null, error: null });

  useEffect(() => {
    const onPopState = () => setSelection(readCaseSelection(window.location.search));
    onPopState();
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetch(EVIDENCE_CATALOG_URL, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
      return parseEvidenceCatalog(await response.json());
    }).then((value) => { if (!controller.signal.aborted) setCatalog(value); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable"); });
    return () => controller.abort();
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
  const brief = evidence?.decision_brief;
  const analysis = brief?.finals_analysis;
  const choice = analysis ? resolveAnalysisSelection(analysis, selection) : null;
  const service = analysis?.services.find((item) => item.id === choice?.service);
  const variant = service?.variants.find((item) => item.travel_mode === choice?.mode && item.speed_factor === 1);
  const flood = choice?.service === "hospital" && choice.mode
    && (!selection.scenario || selection.scenario === analysis?.flood_scenarios?.[choice.mode]?.impact.id)
    ? analysis?.flood_scenarios?.[choice.mode] : null;
  const aoi = catalog?.aois.find((item) => item.id === reference?.aoi_id);
  const event = catalog?.events.find((item) => item.id === reference?.event_id);
  const query = { ...selection, aoi: reference?.aoi_id, event: reference?.event_id, version: catalog?.package_version };
  const mapLayers = evidence?.layers.filter((layer) => MAP_LAYER_IDS.has(layer.id) && (layer.data || layer.image_url)) ?? [];
  const mapAttributions = [...new Set(mapLayers.flatMap((layer) => layer.attribution ? [layer.attribution] : []))];

  return <main id="main-content" tabIndex={-1} className={styles.page} data-planning-candidate={evidence?.id ?? "loading"}>
    {catalogError ? <p className={styles.error} role="alert">{th ? "โหลดรายการกรณีศึกษาไม่ได้" : "Case catalog unavailable"}: {catalogError}</p> : null}
    {catalog && !reference ? <p className={styles.loading}>{th ? "เลือกกรณีศึกษาที่เผยแพร่ด้านบนเพื่อดูผลเฉพาะกรณีนั้น" : "Choose a published case above to inspect its own results."}</p> : null}
    {error ? <p className={styles.error} role="alert">{th ? "ตรวจสอบชุดข้อมูลไม่ผ่าน" : "Package verification failed"}: {error}</p> : null}
    {reference && !evidence && !error ? <p className={styles.loading} role="status">{th ? "กำลังตรวจสอบชุดข้อมูลเพื่อการวางแผน…" : "Verifying planning evidence…"}</p> : null}
    {evidence && aoi && event ? <>
      <header className={styles.intro}>
        <div><p className={styles.eyebrow}>{th ? "การวางแผน · ชุดข้อมูลผู้สมัคร" : "PLANNING · CANDIDATE EVIDENCE"}</p>
          <h1>{th ? "ภาพรวมเพื่อการวางแผน" : "Planning overview"}</h1>
          <p>{th ? "ผลของพื้นที่และเหตุการณ์ที่เลือกเท่านั้น ใช้ทบทวนความครอบคลุม การเข้าถึง และสิ่งที่ยังต้องตรวจสอบ" : "Results for the selected area and event only. Review coverage, service access and the evidence still needed."}</p>
        </div>
      </header>

      {choice?.reason ? <p className={styles.error} role="alert">{th ? "ไม่มีผลสำหรับบริการ วิธีเดินทาง สถานการณ์ หรือจุดเริ่มต้นนี้ จะไม่ใช้ผลอื่นแทน" : "No result exists for this service, mode, scenario or origin. Another result is not substituted."} <code>{choice.reason}</code></p> : null}
      {!analysis ? <p className={styles.error} role="status">{th ? "ยังไม่มีผลวิเคราะห์การเข้าถึงสำหรับกรณีนี้" : "Access analysis is unavailable for this case."}</p> : null}
      {analysis && !choice?.reason ? <>
        <div className={styles.primary}>
          <section className={styles.panel} aria-labelledby="planning-access-title">
            <div className={styles.panelHeading}><div><p className={styles.eyebrow}>{th ? "01 · ผลหลัก" : "01 · KEY RESULT"}</p><h2 id="planning-access-title">{th ? "การเข้าถึงบริการ" : "Service access"}</h2></div><span className={styles.status}>{th ? "ผลตามแบบจำลอง" : "Modelled"}</span></div>
            <p>{service ? SERVICE_NAMES[service.id][th ? 1 : 0] : (th ? "บริการที่เลือก" : "Selected service")} · {choice?.mode === "modelled_vehicle" ? (th ? "แบบจำลองยานพาหนะ" : "vehicle model") : (th ? "แบบจำลองการเดิน" : "walking model")}</p>
            {variant ? <div className={styles.keyFigures}>
              <div><span>{th ? "ประชากรในพื้นที่ศึกษาตามแบบจำลอง" : "Modelled residents in the study area"}</span><strong>{number(variant.baseline.modelled_population, th)}</strong><small>{th ? `บริบทประชากรปี ${analysis.scope.population_year}` : `${analysis.scope.population_year} population context`}</small></div>
              <div><span>{th ? "เข้าถึงภายใน 30 นาที · กรณีฐาน" : "Within 30 minutes · baseline"}</span><strong>{number(variant.baseline.within_30_minutes_population, th)}</strong><small>{th ? "ไม่ใช่การเดินทางที่สังเกตจริง" : "Not observed travel"}</small></div>
              <div><span>{th ? "สูญเสียการเข้าถึง · สมมติปิดถนน" : "Lose 30-minute access · imposed closures"}</span><strong>{flood ? number(flood.impact.losing_30_min_access, th) : (th ? "ยังไม่มี" : "Unavailable")}</strong><small>{th ? "ไม่ใช่ถนนปิดที่สังเกตจริง" : "Not observed road closures"}</small></div>
            </div> : <p className={styles.missing}>{th ? "ยังไม่มีผลสำหรับบริการและวิธีเดินทางนี้" : "No result for this service and travel mode."}</p>}
            <p className={styles.note}>{th ? "ขอบเขตน้ำท่วมเป็นข้อมูลผู้สมัคร ส่วนการปิดถนนเป็นสมมติฐาน ผลนี้ไม่ใช่เส้นทางปลอดภัย" : "Flood extent is a candidate; road closures are imposed assumptions. This result is not safe-route guidance."}</p>
            <a className={styles.primaryLink} href={caseHref("/command/cases/", query)}>{th ? "เปรียบเทียบเส้นทางและสถานการณ์" : "Compare routes and scenarios"} →</a>
          </section>
          <section className={`${styles.panel} ${styles.mapPanel}`} aria-labelledby="planning-map-title">
            <div className={styles.panelHeading}><div><p className={styles.eyebrow}>{th ? "02 · บริบทเชิงพื้นที่" : "02 · SPATIAL CONTEXT"}</p><h2 id="planning-map-title">{th ? "แผนที่หลักฐาน" : "Evidence map"}</h2></div></div>
            <EvidenceMap key={evidence.id} aoi={aoi} layers={mapLayers} th={th} collapsedLayers />
            <p className={styles.mapAttribution}><strong>{th ? "ที่มาแผนที่" : "Map attribution"}:</strong> Leaflet · FloodGuard candidate evidence{mapAttributions.length ? ` · ${mapAttributions.join(" · ")}` : ""}</p>
            <p className={styles.mapText}>{th ? "ขอบเขตพื้นที่ศึกษาและชั้นข้อมูลที่อนุญาตให้เผยแพร่ ยังไม่ยืนยันสภาพถนนหรือจุดเข้าของสถานที่" : "Study-area boundary and cleared layers only. Road conditions and facility entrances remain unverified."}</p>
          </section>
        </div>

        <div className={styles.sections}>
          <section className={styles.panel} aria-labelledby="planning-services-title"><p className={styles.eyebrow}>{th ? "03 · บริการ" : "03 · SERVICES"}</p><h2 id="planning-services-title">{th ? "บริการที่แยกตามประเภท" : "Services kept distinct"}</h2>
            <div className={styles.serviceList}>{analysis.services.map((item) => {
              const baseline = item.variants.find((row) => row.travel_mode === choice?.mode && row.speed_factor === 1)?.baseline;
              return <div key={item.id} className={styles.serviceRow}><div><strong>{SERVICE_NAMES[item.id as FinalsServiceId][th ? 1 : 0]}</strong><small>{th ? "จุดหมายผู้สมัคร" : "Candidate destinations"}: {number(item.facilities, th)}</small></div><div><span>{th ? "เข้าถึงใน 30 นาที" : "Within 30 minutes"}</span><strong>{baseline ? number(baseline.within_30_minutes_population, th) : (th ? "ยังไม่มี" : "Unavailable")}</strong></div></div>;
            })}</div>
            <p className={styles.note}>{th ? "การเปิดใช้งานจริง จุดเข้าถึง และความจุของแต่ละสถานที่ยังไม่ยืนยัน จำนวนจุดหมายไม่ใช่ความจุ" : "Actual operation, entrances and capacity are unverified. Candidate destination count is not capacity."}</p>
          </section>
          <section className={styles.panel} aria-labelledby="planning-road-title"><p className={styles.eyebrow}>{th ? "04 · ถนน" : "04 · ROADS"}</p><h2 id="planning-road-title">{th ? "สมมติฐานการหยุดชะงัก" : "Disruption assumptions"}</h2>
            <p>{flood ? (th ? `${number(flood.closed_edges.length, th)} ช่วงถนนถูกนำเข้าแบบจำลองปิดถนนจากการตัดกับขอบเขตน้ำท่วมผู้สมัคร` : `${number(flood.closed_edges.length, th)} road segments enter an imposed closure scenario from candidate-flood intersection.`) : (th ? "ไม่มีผลการปิดถนนจากน้ำท่วมสำหรับตัวเลือกนี้" : "No candidate-flood closure comparison exists for this selection.")}</p>
            <p className={styles.note}>{th ? "การตัดกันของเส้นถนนกับน้ำท่วมไม่ได้ยืนยันว่าถนนปิดหรือผ่านไม่ได้" : "Flood intersection does not establish observed closure or passability."}</p>
            <MainRoadStatus th={th} />
          </section>
          <section className={styles.panel} aria-labelledby="planning-equity-title"><p className={styles.eyebrow}>{th ? "05 · ประชากร" : "05 · POPULATION"}</p><h2 id="planning-equity-title">{th ? "ประชากรและความเสมอภาค" : "Population and equity"}</h2>
            <dl className={styles.facts}><div><dt>{th ? "บริบทประชากร" : "Population context"}</dt><dd>{analysis.scope.population_year} · {th ? "ผู้อยู่อาศัยตามแบบจำลอง" : "modelled residents"}</dd></div><div><dt>{th ? "ความเสมอภาคตามกลุ่มอายุ" : "Age-group equity"}</dt><dd>{th ? "ยังไม่มีผลที่ยอมรับ" : "No accepted result"}</dd></div><div><dt>{th ? "ความจุจริงของศูนย์พักพิง" : "Actual shelter capacity"}</dt><dd>{th ? "ไม่ทราบ" : "Unknown"}</dd></div></dl>
            <p className={styles.note}>{th ? "กลุ่มเด็กหมายถึงอายุ 0–14 ปี แต่ยังไม่มีจำนวนเด็กที่สังเกตในพื้นที่ศึกษานี้ ผลระดับตำบลบางส่วนหมายถึงเฉพาะส่วนที่ตัดกับพื้นที่ศึกษา ไม่ใช่ทั้งตำบล" : "Children means ages 0–14; observed local counts are unavailable. A partial subdistrict result describes its AOI intersection, not the full subdistrict."}</p>
          </section>
          <section className={styles.panel} aria-labelledby="planning-verification-title"><p className={styles.eyebrow}>{th ? "06 · ขั้นถัดไป" : "06 · NEXT STEPS"}</p><h2 id="planning-verification-title">{th ? "สิ่งที่ต้องตรวจสอบ" : "Verification priorities"}</h2>
            {brief?.next_actions.length ? <ol className={styles.actions}>{[...brief.next_actions].sort((left, right) => left.order - right.order).map((item) => <li key={item.id}><strong>{th ? THAI_ACTIONS[item.id] ?? item.action : item.action}</strong>{!th ? <span>{item.reason}</span> : null}</li>)}</ol> : <p>{th ? "ยังไม่มีรายการตรวจสอบ" : "No verification queue is recorded."}</p>}
            <p className={styles.note}>{th ? "FPPS และชั้นการดำเนินการที่ยอมรับยังไม่มี ค่าที่ขาดไม่ใช่ศูนย์และไม่มีการกระจายน้ำหนักใหม่" : "Accepted FPPS and action class remain unavailable. Missing inputs are not zero and weights are not redistributed."}</p>
          </section>
        </div>

        <section className={styles.provenance} aria-label={th ? "หลักฐานและแหล่งที่มา" : "Evidence and provenance"}>
          <details><summary>{th ? "แหล่งข้อมูล เวลา และข้อจำกัด" : "Sources, timing and limitations"}</summary>
            <dl className={styles.facts}><div><dt>{th ? "เวลาแหล่งข้อมูล" : "Source observation time"}</dt><dd>{evidence.source_timestamp ?? (th ? "หลายช่วงเวลา ดูรายละเอียดแหล่งข้อมูล" : "Mixed periods; inspect dataset metadata")}</dd></div><div><dt>{th ? "เวลาวิเคราะห์" : "Analysis generated"}</dt><dd>{analysis.generated_at}</dd></div><div><dt>{th ? "เวลาเผยแพร่ชุดข้อมูล" : "Package released"}</dt><dd>{evidence.generated_at}</dd></div><div><dt>{th ? "รหัสชุดข้อมูล" : "Package ID"}</dt><dd><code>{evidence.id}</code></dd></div><div><dt>SHA-256</dt><dd><code>{reference?.sha256}</code></dd></div></dl>
            <ul>{evidence.assumptions.slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul>
            <a href={caseHref("/studio/library/", query)}>{th ? "ตรวจสอบแหล่งข้อมูล สิทธิ์ และค่าแฮชทั้งหมด" : "Inspect all sources, rights and hashes"} →</a>
          </details>
        </section>
        <nav className={styles.footerNav} aria-label={th ? "มุมมองที่เกี่ยวข้อง" : "Related views"}><a href={caseHref("/studio/", query)}>{th ? "รายงานการตรวจสอบ" : "Validation report"} →</a><a href={caseHref("/studio/brief/", query)}>{th ? "บทสรุปเพื่อการตัดสินใจ" : "Decision brief"} →</a><a href="/command/archive/">{th ? "คลังเปรียบเทียบงานวิจัยเดิม" : "Historical research archive"} →</a></nav>
      </> : null}
    </> : null}
  </main>;
}
