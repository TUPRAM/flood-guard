"use client";

import { useEffect, useState, type FormEvent } from "react";

import boundaries from "../../public/offline-demo/mae-sai/areas.json";

import { maeSaiCase, type MaeSaiScenario } from "@/lib/mae-sai-case";
import { exportMaeSaiReview, loadMaeSaiReviews, saveMaeSaiReview, type MaeSaiReviewRecord } from "@/lib/mae-sai-review";
import type { Language } from "@/lib/types";
import { useLanguage } from "@/lib/use-language";

import { WorkspaceHeader } from "./workspace-header";
import styles from "./mae-sai-planning-demo.module.css";

const numberFormat = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const number = (value: number) => numberFormat.format(value);
const date = (value: string) => new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const ratio = (value: number | null, th: boolean) => value === null ? (th ? "ไม่มีข้อมูล" : "Not available") : `${value.toFixed(2)}×`;

const mapPoints = boundaries.features.flatMap((feature) => feature.geometry.coordinates.flat(2));
const mapMinX = Math.min(...mapPoints.map((point) => point[0]));
const mapMaxX = Math.max(...mapPoints.map((point) => point[0]));
const mapMinY = Math.min(...mapPoints.map((point) => point[1]));
const mapMaxY = Math.max(...mapPoints.map((point) => point[1]));
const mapScale = Math.min(330 / (mapMaxX - mapMinX), 220 / (mapMaxY - mapMinY));
const mapPaths = boundaries.features.map((feature) => ({
  id: feature.properties.area_id,
  name: feature.properties.area_name_en,
  path: feature.geometry.coordinates.map((polygon) => polygon.map((ring) => ring.map((point, index) => `${index ? "L" : "M"}${(18 + (point[0] - mapMinX) * mapScale).toFixed(1)},${(14 + (mapMaxY - point[1]) * mapScale).toFixed(1)}`).join(" ") + "Z").join(" ")).join(" "),
}));

function scenarioTitle(scenario: MaeSaiScenario, th: boolean) {
  if (!th) return scenario.title;
  return ({ baseline: "สภาพฐานของแบบจำลอง", close_road: "สมมติให้ถนนปิดเพิ่มเติม", add_temporary_shelter: "สมมติเพิ่มจุดบริการชั่วคราว" } as Record<string, string>)[scenario.scenario_id] ?? scenario.title;
}

function downloadRecord(record: MaeSaiReviewRecord, format: "json" | "markdown") {
  const blob = new Blob([exportMaeSaiReview(record, format)], { type: format === "json" ? "application/json" : "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `floodguard-mae-sai-${record.id}.${format === "json" ? "json" : "md"}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function MaeSaiPlanningDemo({ defaultLanguage = "en" }: { defaultLanguage?: Language }) {
  const [language, changeLanguage] = useLanguage(defaultLanguage);
  const th = language === "th";
  const [areaId, setAreaId] = useState(maeSaiCase.areas.find((area) => area.area_id === "TH570903")?.area_id ?? maeSaiCase.areas[0].area_id);
  const [scenarioId, setScenarioId] = useState("add_temporary_shelter");
  const [records, setRecords] = useState<MaeSaiReviewRecord[]>([]);
  const [activeRecordId, setActiveRecordId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [noticeIsError, setNoticeIsError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [decision, setDecision] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [verificationNeed, setVerificationNeed] = useState("");
  const [owner, setOwner] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState<"draft" | "reviewed_for_exercise">("draft");

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      const result = loadMaeSaiReviews();
      if (cancelled) return;
      setRecords(result.records);
      setActiveRecordId(result.records[0]?.id ?? null);
      setLoaded(true);
      if (result.warning) {
        setNotice(result.warning);
        setNoticeIsError(true);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const area = maeSaiCase.areas.find((item) => item.area_id === areaId)!;
  const scenario = maeSaiCase.scenarios.find((item) => item.scenario_id === scenarioId) ?? maeSaiCase.scenarios[0];
  const comparison = scenario.areas.find((item) => item.area_id === areaId)!;
  const selectedRecord = records.find((record) => record.id === activeRecordId);
  const areaName = th ? area.name_th : area.name_en;
  const otherChange = scenario.areas.find((item) => item.area_id !== areaId && item.change_people_losing_30_min_access !== 0);
  const otherArea = otherChange ? maeSaiCase.areas.find((item) => item.area_id === otherChange.area_id) : undefined;
  const delta = comparison.change_people_losing_30_min_access;
  const chartMax = Math.max(comparison.baseline_people_losing_30_min_access, comparison.scenario_people_losing_30_min_access, 1);

  function saveReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const result = saveMaeSaiReview({ scenarioId: scenario.scenario_id, areaId, decision, reasoning, verificationNeed, owner, role, status });
      setRecords(result.records);
      setActiveRecordId(result.record.id);
      setNotice(th ? "บันทึกฉบับใหม่ในอุปกรณ์นี้แล้ว ประวัติก่อนหน้ายังคงอยู่" : "New record saved on this device. Earlier records are preserved.");
      setNoticeIsError(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : th ? "ไม่สามารถบันทึกในอุปกรณ์นี้ได้" : "Could not save the record on this device.");
      setNoticeIsError(true);
    }
  }

  function exportRecord(format: "json" | "markdown") {
    if (!selectedRecord) return;
    try {
      downloadRecord(selectedRecord, format);
      setNotice(th ? "เตรียมไฟล์บันทึกและหลักฐานสำหรับดาวน์โหลดแล้ว" : "The saved record and its evidence are ready to download.");
      setNoticeIsError(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not export this record.");
      setNoticeIsError(true);
    }
  }

  return <div className={styles.page}>
    <WorkspaceHeader activeSurface="planning" language={language} onLanguageChange={changeLanguage} />
    <main id="main-content" className={styles.shell}>
      <nav className={styles.breadcrumb} aria-label={th ? "เส้นทางหน้าเว็บ" : "Breadcrumb"}>
        <a href="/command/">{th ? "พื้นที่ทำงานวางแผน" : "Planning workspace"}</a><span aria-hidden="true">/</span><span>{th ? "กรณีศึกษาแม่สาย" : "Mae Sai case study"}</span>
      </nav>

      <section className={styles.hero} aria-labelledby="demo-title">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>{th ? "แม่สาย ประเทศไทย · กรณีศึกษาย้อนหลัง" : "Mae Sai, Thailand · Historical case study"}</p>
          <h1 id="demo-title">{th ? "จากหลักฐานน้ำท่วม สู่การตัดสินใจที่อธิบายได้" : <>From flood evidence<br />to a defensible decision.</>}</h1>
          <p>{th ? "สำรวจช่องว่างการเข้าถึง เปรียบเทียบสมมติฐานหนึ่งอย่าง และบันทึกเหตุผลพร้อมสิ่งที่ต้องตรวจสอบก่อนนำไปใช้" : "Examine an access gap. Test one planning assumption. Preserve your reasoning and what needs verification before action."}</p>
          <div className={styles.heroActions}>
            <a className={`${styles.button} ${styles.primary}`} href="#compare">{th ? "เปรียบเทียบทางเลือก" : "Compare a planning option"}<span aria-hidden="true">↗</span></a>
            <a className={styles.button} href="#evidence">{th ? "ตรวจสอบหลักฐาน" : "Explore the evidence"}</a>
          </div>
        </div>
        <div className={styles.heroMap}>
          <span className={styles.mapLabel}>{th ? "บริบทพื้นที่ศึกษา" : "Study area context"}</span>
          <svg viewBox="0 0 366 248" role="img" aria-labelledby="mae-sai-map-title" className={styles.map}>
            <title id="mae-sai-map-title">{th ? `ขอบเขตตำบลในแม่สาย เน้น ${areaName} ไม่ใช่แผนที่น้ำท่วม` : `Mae Sai administrative boundaries with ${areaName} highlighted. This is a location map, not flood extent.`}</title>
            {mapPaths.map((path) => <path key={path.id} d={path.path} className={path.id === areaId ? styles.mapSelected : styles.mapArea}><title>{path.name}</title></path>)}
            <text x="342" y="28" textAnchor="middle" fill="#cad8ed" fontSize="11">N</text><path d="M342 36 L338 47 L342 44 L346 47Z" fill="#cad8ed" />
          </svg>
          <div className={styles.mapCaption}><div><strong>{areaName}</strong><span>{th ? "ขอบเขตพื้นที่ · ไม่ใช่ขอบเขตน้ำท่วม" : "Administrative outline · Not flood extent"}</span></div><a href="https://data.humdata.org/dataset/cod-ab-tha">HDX COD-AB</a></div>
        </div>
      </section>

      <dl className={styles.context} aria-label={th ? "สถานะหลักฐาน" : "Case evidence status"}>
        <div><dt>{th ? "เวลาสังเกตการณ์น้ำท่วม" : "Flood observation time"}</dt><dd><time dateTime={maeSaiCase.meta.source_timestamp}>{date(maeSaiCase.meta.source_timestamp)} · UTC</time></dd></div>
        <div><dt>{th ? "ความเชื่อมั่น / การใช้งาน" : "Confidence / intended use"}</dt><dd>{th ? "ต่ำ · แบบฝึกหัดวางแผนย้อนหลัง" : "Low · Historical planning exercise"}</dd></div>
        <div><dt>{th ? "ขอบเขตการใช้งาน" : "Operational boundary"}</dt><dd>{th ? "ไม่ใช่คำเตือนทางการหรือคำแนะนำเส้นทาง" : "Not an official warning or route guidance"}</dd></div>
      </dl>

      <nav className={styles.steps} aria-label={th ? "ขั้นตอนกรณีศึกษา" : "Case study steps"}>
        <a href="#evidence"><span>01</span>{th ? "อ่านหลักฐาน" : "Understand the evidence"}</a>
        <a href="#compare"><span>02</span>{th ? "เปรียบเทียบทางเลือก" : "Compare an option"}</a>
        <a href="#record"><span>03</span>{th ? "บันทึกการตัดสินใจ" : "Record a decision"}</a>
      </nav>

      <section id="evidence" className={styles.section} aria-labelledby="evidence-heading">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>01 / {th ? "หลักฐาน" : "Evidence"}</p><h2 id="evidence-heading">{th ? "เหตุการณ์หนึ่งครั้ง ข้อมูลหลายช่วงเวลา" : "One historical event. Different source dates."}</h2></div><p>{th ? "วันที่และสมมติฐานคงอยู่กับทุกผลลัพธ์ ข้อมูลบริบทภายหลังไม่ใช่ภาพเหตุการณ์ปี 2024 ที่สมบูรณ์" : "Dates and assumptions travel with the result. Later context does not reconstruct every condition in 2024."}</p></div>
        <div className={styles.evidenceGrid}>
          <div className={styles.panel}><h3>{th ? "ที่มาของข้อมูล" : "The evidence behind the case"}</h3><dl className={styles.sourceList}>{maeSaiCase.source_components.map((source) => <div key={source.name}><dt>{source.name}</dt><dd>{source.timestamp ? date(source.timestamp) : th ? "ไม่ทราบวันที่" : "Date unknown"}</dd></div>)}</dl></div>
          <div className={styles.panel}><span className={`${styles.tag} ${styles.amber}`}>{th ? "ความแม่นยำในพื้นที่ยังไม่ได้วัด" : "Local accuracy not measured"}</span><h3 style={{ marginTop: 15 }}>{th ? "สิ่งที่กรณีศึกษานี้ช่วยให้สำรวจ" : "What this case can help you explore"}</h3><p>{th ? "ผลลัพธ์การเข้าถึงคำนวณล่วงหน้าด้วยโมดูลวิเคราะห์ของ FloodGuard จากกราฟบริบทที่ตรึงไว้ เปลี่ยนสมมติฐานเพื่อดูว่าข้อสรุปด้านการวางแผนอ่อนไหวเพียงใด" : "Access results are precomputed by FloodGuard’s analysis modules from a frozen context graph. Change an assumption to see how sensitive the planning consequence is."}</p><p>{th ? "ไม่ได้ยืนยันการปิดถนน บทบาทศูนย์พักพิง หรือจำนวนผู้ได้รับผลกระทบจริง งานวิจัย GeoAI ยังคงแยกจากการจัดลำดับนี้" : "These results do not confirm road closures, shelter designation, or observed affected people. GeoAI research remains separate from this planning case."}</p><a className={styles.link} href="/studio/">{th ? "เปิดงานวิจัยและข้อจำกัดใน Studio" : "Open research evidence and limitations in Studio"} ↗</a></div>
        </div>
      </section>

      <section id="compare" className={styles.section} aria-labelledby="compare-heading">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>02 / {th ? "เปรียบเทียบ" : "Compare"}</p><h2 id="compare-heading">{th ? "เมื่อเปลี่ยนสมมติฐาน การเข้าถึงเปลี่ยนอย่างไร?" : "What changes when one assumption changes?"}</h2></div><p>{th ? "ตัวเลขทุกชุดมาจากการคำนวณที่บันทึกไว้ โดยใช้ประชากรและเกณฑ์การเข้าถึงเดียวกัน" : "Each comparison uses recorded engine outputs, the same population basis, and the same access threshold."}</p></div>
        <div className={styles.selectorRow}>
          <label className={styles.field}>{th ? "สมมติฐานการวางแผน" : "Planning assumption"}<select value={scenario.scenario_id} onChange={(event) => setScenarioId(event.target.value)}>{maeSaiCase.scenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{scenarioTitle(item, th)}</option>)}</select></label>
          <label className={styles.field}>{th ? "พื้นที่ที่ต้องการพิจารณา" : "Focus area"}<select value={areaId} onChange={(event) => setAreaId(event.target.value)}>{maeSaiCase.areas.map((item) => <option key={item.area_id} value={item.area_id}>{th ? item.name_th : item.name_en}</option>)}</select></label>
        </div>
        <div className={styles.scenarioDescription}><span aria-hidden="true">↳</span><div><strong>{scenarioTitle(scenario, th)}</strong><p lang="en">{scenario.description}</p><p lang="en">{scenario.changed_assumption}</p></div></div>
        {otherChange && otherArea ? <aside className={styles.affectedArea} aria-label={th ? "การเปลี่ยนแปลงนอกพื้นที่ที่เลือก" : "Changes outside the focus area"}>
          <p>{th ? "สมมติฐานนี้เปลี่ยนผลการเข้าถึงในพื้นที่อื่นด้วย" : "This assumption changes modelled access loss in another area."}</p>
          <button type="button" className={styles.button} onClick={() => setAreaId(otherArea.area_id)}>{th ? "ดู" : "View"} {th ? otherArea.name_th : otherArea.name_en} ({otherChange.change_people_losing_30_min_access > 0 ? "+" : "−"}{number(Math.abs(otherChange.change_people_losing_30_min_access))}) <span aria-hidden="true">↗</span></button>
        </aside> : null}
        <div aria-live="polite" aria-atomic="true">
          <div className={styles.metrics}>
            <div className={styles.metric}><span>{th ? "สูญเสียการเข้าถึง · สภาพฐาน" : "Access loss · Baseline"}</span><strong>{number(comparison.baseline_people_losing_30_min_access)}</strong><small>{th ? `คนในแบบจำลอง · ${areaName}` : `Modelled people · ${areaName}`}</small></div>
            <div className={styles.metric}><span>{th ? "สูญเสียการเข้าถึง · สมมติฐาน" : "Access loss · Selected option"}</span><strong>{number(comparison.scenario_people_losing_30_min_access)}</strong><small>{th ? `เกณฑ์ ${maeSaiCase.scope.threshold_minutes} นาทีเดียวกัน` : `Same ${maeSaiCase.scope.threshold_minutes}-minute threshold`}</small></div>
            <div className={`${styles.metric} ${styles.metricDelta}`}><span>{th ? "ผลต่างจากสภาพฐาน" : "Change from baseline"}</span><strong>{delta > 0 ? "+" : delta < 0 ? "−" : ""}{number(Math.abs(delta))}</strong><small>{delta < 0 ? th ? "คนที่สูญเสียการเข้าถึงลดลง" : "Fewer modelled people losing access" : delta > 0 ? th ? "คนที่สูญเสียการเข้าถึงเพิ่มขึ้น" : "More modelled people losing access" : th ? "ไม่เปลี่ยนภายใต้สมมติฐานนี้" : "No change under this assumption"}</small></div>
          </div>
        </div>
        <div className={styles.comparison}>
          <div className={styles.panel}><h3>{th ? "แยกการสูญเสียใหม่จากช่องว่างเดิม" : "Separate new loss from an existing gap"}</h3><p>{th ? "การสูญเสียการเข้าถึงนับเฉพาะคนที่เคยถึงจุดบริการภายในเกณฑ์เวลา ก่อนที่ถนนในแบบจำลองจะหยุดใช้งาน" : "Access loss counts people who could reach a facility within the threshold before the modelled road disruption."}</p>
            <div className={styles.chart} aria-label={th ? "เปรียบเทียบการสูญเสียการเข้าถึง" : "Access loss comparison"}>{[{ label: th ? "สภาพฐาน" : "Baseline", value: comparison.baseline_people_losing_30_min_access, selected: false }, { label: th ? "สมมติฐานที่เลือก" : "Selected option", value: comparison.scenario_people_losing_30_min_access, selected: true }].map((bar) => <div key={bar.label}><div className={styles.barHeading}><span>{bar.label}</span><strong>{number(bar.value)}</strong></div><div className={styles.barTrack} aria-hidden="true"><div className={`${styles.bar} ${bar.selected ? styles.barScenario : ""}`} style={{ width: `${100 * bar.value / chartMax}%`, minWidth: bar.value ? undefined : 0 }} /></div></div>)}</div>
            <dl className={styles.facts}>
              <div><dt>{th ? "เข้าไม่ถึงอยู่แล้วก่อนเหตุขัดข้อง" : "Already outside the threshold before disruption"}</dt><dd>{number(area.baseline.baseline_underserved_30_min)}</dd></div>
              <div><dt>{th ? "ประชากรที่แทนในกราฟพื้นที่นี้" : "Population represented in this area’s graph"}</dt><dd>{number(area.baseline.total_population)}</dd></div>
              <div><dt>{th ? "อัตราช่องว่างความเป็นธรรม · ฐาน → สมมติฐาน" : "Equity gap ratio · Baseline → Option"}</dt><dd>{ratio(comparison.baseline_equity_gap_ratio, th)} → {ratio(comparison.scenario_equity_gap_ratio, th)}</dd></div>
            </dl>
            <p className={styles.caption}>{th ? "ประชากรที่เข้าไม่ถึงอยู่แล้วไม่ถูกรวมเป็นการสูญเสียใหม่ อัตราความเป็นธรรมใช้กลุ่มเปราะบางที่เป็นตัวแทนในแบบจำลอง ไม่ใช่ผลสำรวจครัวเรือน" : "People already underserved are not counted as newly losing access. Equity compares modelled vulnerability groups; it is not a household survey."}</p>
          </div>
          <div className={`${styles.panel} ${styles.verification}`}><span className={`${styles.tag} ${styles.amber}`}>{th ? "ต้องตรวจสอบก่อนลงมือ" : "Verify before acting"}</span><h3>{th ? "หลักฐานใดอาจเปลี่ยนการตัดสินใจ?" : "What evidence could change the decision?"}</h3><p lang="en">{scenario.verification_need}</p><p>{th ? "ผลต่างช่วยเลือกสิ่งที่ควรตรวจสอบต่อ ไม่ได้ยืนยันว่าทางเลือกนี้ปลอดภัยหรือพร้อมใช้งาน" : "The difference helps prioritize the next check. It does not establish that the option is safe, available, or operationally approved."}</p>
            <div className={styles.priority}><strong>{area.existing_priority.action_class}</strong><p><b>{th ? "ติดตามและตรวจสอบ" : "Monitor and verify"} · FPPS {area.existing_priority.fpps.toFixed(1)}</b>{th ? "คะแนนจากชุดจัดลำดับเดิม ไม่คำนวณใหม่ในสมมติฐานนี้ ชั้น E สะท้อนความเชื่อมั่นต่ำ ไม่ได้ยืนยันว่าผลกระทบต่ำ" : "Existing ranking score; not recalculated by this scenario. Class E reflects low confidence, not evidence of low potential impact."}</p></div>
            <p className={styles.caption}>{th ? "คะแนนคงไว้จากชุดจัดลำดับเดิม ผลต่างการเข้าถึงคำนวณจากกราฟกรณีศึกษาเดียวกัน ตรวจสอบขอบเขตและการปัดเศษในวิธีการ" : "Scores retain the original ranking. Access differences use this case’s graph. Inspect the method for source scope and rounding."}</p>
          </div>
        </div>
        <details className={styles.details}>
          <summary>{th ? "ตรวจสอบที่มา รุ่นข้อมูล วิธีการ และขอบเขตการตรวจสอบ" : "Inspect provenance, versions, method, and validation boundaries"}</summary>
          <div className={styles.detailBody}>
            <dl className={styles.provenance}><div><dt>{th ? "รุ่นกรณีศึกษา" : "Case version"}</dt><dd><code>{maeSaiCase.meta.case_version}</code></dd></div><div><dt>{th ? "รหัสการคำนวณสมมติฐาน" : "Scenario run"}</dt><dd><code>{scenario.run_id}</code></dd></div><div><dt>{th ? "SHA-256 ของชุดหลักฐาน" : "Evidence package SHA-256"}</dt><dd><code>{maeSaiCase.meta.package_sha256}</code></dd></div><div><dt>{th ? "เวลาประมวลผลแหล่งข้อมูล" : "Source processing time"}</dt><dd><time dateTime={maeSaiCase.meta.source_processing_timestamp}>{maeSaiCase.meta.source_processing_timestamp}</time></dd></div><div><dt>{th ? "เวลาสร้างผลลัพธ์" : "Result generated at"}</dt><dd><time dateTime={maeSaiCase.meta.generated_at}>{maeSaiCase.meta.generated_at}</time></dd></div></dl>
            <h3>{th ? "ขอบเขตและวิธีการ" : "Scope and method"}</h3><p lang="en">{maeSaiCase.scope.description} {maeSaiCase.scope.population_basis}</p><p>{number(maeSaiCase.scope.graph_node_count)} {th ? "จุด" : "nodes"} · {number(maeSaiCase.scope.graph_edge_count)} {th ? "ช่วงเชื่อมต่อ" : "edges"} · {number(maeSaiCase.scope.facility_count)} {th ? "จุดบริการ" : "facilities"} · {number(maeSaiCase.scope.graph_population)} {th ? "คนที่แทนในกราฟ" : "represented people"}</p><p lang="en">{maeSaiCase.scope.priority_scope_note}</p>
            <h3>{th ? "สมมติฐาน" : "Assumptions"}</h3><ul lang="en">{[...maeSaiCase.assumptions, ...scenario.assumptions].map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
            <h3>{th ? "สิ่งที่ตรวจวัดแล้ว" : "What has been measured"}</h3><ul lang="en">{maeSaiCase.validation.measured.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>{th ? "สิ่งที่ยังไม่ได้ตรวจวัด" : "What has not been measured"}</h3><ul lang="en">{maeSaiCase.validation.not_measured.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>{th ? "ขั้นตอนตรวจสอบที่ยังต้องทำ" : "Required validation next steps"}</h3><ul lang="en">{maeSaiCase.validation.required_next_steps.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>{th ? "แหล่งข้อมูลที่ผูกกับผลลัพธ์" : "Source bindings"}</h3><dl className={styles.provenance}>{maeSaiCase.sources.map((source) => <div key={source.path}><dt>{source.role}</dt><dd><code>{source.path}</code><br /><code>SHA-256: {source.sha256}</code></dd></div>)}</dl>
          </div>
        </details>
      </section>

      <section id="record" className={styles.section} aria-labelledby="record-heading">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>03 / {th ? "บันทึก" : "Record"}</p><h2 id="record-heading">{th ? "รักษาเหตุผล ไม่ใช่แค่ข้อสรุป" : "Keep the reasoning, not just the conclusion."}</h2></div><p>{th ? "แบบฝึกหัดในอุปกรณ์นี้ ไม่มีการส่งให้เจ้าหน้าที่หรือการยืนยันโดยหน่วยงาน" : "A device-local exercise. Records are not sent to staff and do not represent agency verification."}</p></div>
        <div className={styles.recordGrid}>
          <form className={`${styles.panel} ${styles.form}`} onSubmit={saveReview}>
            <p className={styles.notice}>{th ? "จะบันทึกพร้อม" : "Recording against"}: <strong>{areaName} · {scenarioTitle(scenario, th)}</strong></p>
            <label className={styles.field}>{th ? "ข้อเสนอการตัดสินใจ" : "Proposed decision"}<input required maxLength={300} value={decision} onChange={(event) => setDecision(event.target.value)} placeholder={th ? "สิ่งที่ควรตรวจสอบหรือเตรียมการต่อ" : "What should be checked or prepared next?"} /></label>
            <label className={styles.field}>{th ? "เหตุผลและหลักฐาน" : "Reasoning and evidence"}<textarea required maxLength={3000} rows={3} value={reasoning} onChange={(event) => setReasoning(event.target.value)} placeholder={th ? "ผลเปรียบเทียบสนับสนุนข้อเสนอนี้อย่างไร?" : "How does this comparison support the proposed decision?"} /></label>
            <label className={styles.field}>{th ? "สิ่งที่ต้องตรวจสอบก่อนใช้งาน" : "Required verification before action"}<textarea required maxLength={2000} rows={2} value={verificationNeed} onChange={(event) => setVerificationNeed(event.target.value)} placeholder={th ? "หลักฐานใดอาจเปลี่ยนข้อสรุปนี้?" : "What missing evidence could change this conclusion?"} /></label>
            <div className={styles.formPair}><label className={styles.field}>{th ? "ทีมผู้รับผิดชอบในแบบฝึกหัด" : "Exercise owner / team"}<input required maxLength={120} value={owner} onChange={(event) => setOwner(event.target.value)} placeholder={th ? "เช่น ทีมวางแผน A" : "e.g. Planning team A"} /></label><label className={styles.field}>{th ? "บทบาทในแบบฝึกหัด" : "Exercise role"}<input required maxLength={120} value={role} onChange={(event) => setRole(event.target.value)} placeholder={th ? "เช่น ผู้วิเคราะห์การเข้าถึง" : "e.g. Access analyst"} /></label></div>
            <label className={styles.field}>{th ? "สถานะการทบทวนในแบบฝึกหัด" : "Exercise review status"}<select value={status} onChange={(event) => setStatus(event.target.value as "draft" | "reviewed_for_exercise")}><option value="draft">{th ? "ร่าง · ยังไม่ทบทวน" : "Draft · Not reviewed"}</option><option value="reviewed_for_exercise">{th ? "ทบทวนเพื่อแบบฝึกหัดเท่านั้น" : "Reviewed for exercise only"}</option></select><small>{th ? "ระบุเพียงชื่อทีมและบทบาท ไม่ใส่ข้อมูลส่วนบุคคลหรือข้อมูลอ่อนไหว" : "Use team labels and roles. Do not enter personal or sensitive information."}</small></label>
            <div className={styles.formActions}><button className={`${styles.button} ${styles.primary}`} type="submit" disabled={!loaded}>{th ? "บันทึกฉบับใหม่" : "Save a new record"}<span aria-hidden="true">↗</span></button><p>{th ? "ทุกครั้งสร้างฉบับใหม่ เก็บประวัติก่อนหน้าไว้ในเบราว์เซอร์นี้" : "Each save creates a new snapshot and preserves the earlier history in this browser."}</p></div>
            {notice ? <p role="status" className={`${styles.notice} ${noticeIsError ? styles.error : ""}`}>{notice}</p> : null}
            <p className={styles.caption}>{th ? "การล้างข้อมูลเบราว์เซอร์อาจลบบันทึก ส่งออกไฟล์เพื่อเก็บหรือแบ่งปัน" : "Clearing browser storage can remove these records. Export a copy to retain or share your work."}</p>
          </form>
          <aside className={styles.panel} aria-labelledby="history-heading">
            <div className={styles.historyHeader}><h3 id="history-heading">{th ? "ประวัติการตัดสินใจ" : "Decision history"}</h3><span>{records.length} {th ? "รายการ" : "records"}</span></div>
            <p>{th ? "เลือกฉบับที่บันทึกไว้เพื่ออ่านและส่งออก เหตุผลผูกกับรุ่นหลักฐานและสมมติฐานเดิมเสมอ" : "Choose a saved snapshot to review and export. Its reasoning stays bound to the original evidence version and assumption."}</p>
            {records.length ? <ol className={styles.historyList}>{records.map((record) => <li key={record.id}><button type="button" aria-pressed={record.id === activeRecordId} onClick={() => setActiveRecordId(record.id)}><strong>{record.decision}</strong><span>{date(record.createdAt)} · {record.status === "draft" ? th ? "ร่าง" : "Draft" : th ? "ทบทวนในแบบฝึกหัด" : "Reviewed for exercise"}</span></button></li>)}</ol> : <p className={styles.caption}>{loaded ? th ? "ยังไม่มีบันทึกในอุปกรณ์นี้" : "No records saved on this device yet." : th ? "กำลังอ่านประวัติในอุปกรณ์…" : "Loading local history…"}</p>}
            {selectedRecord ? <div className={styles.recordPreview}><span className={styles.tag}>{th ? "ฉบับที่บันทึกไว้" : "Saved snapshot"}</span><h4>{th ? "ผู้รับผิดชอบ / บทบาท" : "Owner / role"}</h4><p>{selectedRecord.owner} · {selectedRecord.role}</p><h4>{th ? "พื้นที่ / สมมติฐาน" : "Area / assumption"}</h4><p>{selectedRecord.areaId} · {selectedRecord.scenarioId}</p><h4>{th ? "เหตุผล" : "Reasoning"}</h4><p>{selectedRecord.reasoning}</p><h4>{th ? "ต้องตรวจสอบ" : "Verification required"}</h4><p>{selectedRecord.verificationNeed}</p><h4>{th ? "รุ่นหลักฐาน" : "Evidence version"}</h4><p>{selectedRecord.caseVersion}</p><div className={styles.exports}><button type="button" className={styles.button} onClick={() => exportRecord("markdown")}>{th ? "ส่งออกบันทึก Markdown" : "Export brief · Markdown"} ↓</button><button type="button" className={styles.button} onClick={() => exportRecord("json")}>{th ? "ส่งออกหลักฐาน JSON" : "Export evidence · JSON"} ↓</button></div></div> : null}
          </aside>
        </div>
      </section>
      <footer className={styles.footer}><p>{th ? "FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญ กรณีศึกษาย้อนหลังนี้ไม่พร้อมใช้สั่งการ ไม่ยืนยันเส้นทางปลอดภัย ความจุศูนย์พักพิง หรือการประสานงานข้ามหน่วยงาน ให้ปฏิบัติตามคำแนะนำของ ปภ. และหน่วยงานท้องถิ่นก่อนลงมือ" : "FloodGuard supports preparedness and prioritization. This historical case is non-operational: it does not establish safe routes, shelter capacity, or coordination between agencies. Follow DDPM and local-authority instructions before action."}</p><a className={styles.link} href="/command/">{th ? "กลับสู่พื้นที่ทำงานเต็มรูปแบบ" : "Open the full planning workspace"} ↗</a></footer>
    </main>
  </div>;
}
