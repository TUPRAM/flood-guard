"use client";

import { useEffect, useState } from "react";
import type { EvidenceLibraryCatalog, EvidenceLibraryPackage } from "@floodguard/contracts";

import { caseHref, readCaseSelection, resolveEvidenceCase, type CaseSelection } from "@/lib/case-selection";
import { EVIDENCE_CATALOG_URL, fetchEvidencePackage, parseEvidenceCatalog } from "@/lib/evidence-library";
import { useLanguage } from "@/lib/use-language";

import styles from "./studio-candidate-report.module.css";

type ReportTab = "technical" | "observed" | "quality" | "models" | "governance" | "files";
type StageState = "verified" | "not_recorded" | "unavailable" | "blocked";

const TABS: { id: ReportTab; en: string; th: string }[] = [
  { id: "technical", en: "Technical verification", th: "การตรวจสอบทางเทคนิค" },
  { id: "observed", en: "Observed event", th: "เหตุการณ์ที่สังเกต" },
  { id: "quality", en: "Data quality", th: "คุณภาพข้อมูล" },
  { id: "models", en: "Models & evaluation", th: "โมเดลและการประเมิน" },
  { id: "governance", en: "Governance", th: "ธรรมาภิบาล" },
  { id: "files", en: "Files & history", th: "ไฟล์และประวัติ" },
];

const TH_ACTIONS: Record<string, { action: string; reason: string }> = {
  event_reference: {
    action: "ตรวจสอบขอบเขตน้ำท่วมตามวันที่",
    reason: "เชื่อมหลักฐานน้ำท่วมกับช่วงเหตุการณ์ ขอบเขตการสังเกต และหน่วยรายงาน ก่อนสรุปการสัมผัสหรือความสำคัญ",
  },
  access_review: {
    action: "ตรวจสอบเส้นทางเชื่อมต่อและจุดหมายที่มีผลมาก",
    reason: "ใช้ผลเปรียบเทียบสถานการณ์เพื่อเลือกจุดตรวจสอบ การเปลี่ยนแปลงตามแบบจำลองไม่ใช่การปิดถนนที่สังเกตจริง",
  },
  demand_capacity: {
    action: "ยืนยันกลุ่มประชากรและสมมติฐานความจุ",
    reason: "ใช้สถานการณ์การมีส่วนร่วมที่ระบุชัด จนกว่าจะมีหลักฐานรองรับความต้องการจริง นิยามอายุ และความจุศูนย์พักพิงที่ใช้ได้",
  },
};

const TH_COMPONENTS: Record<string, { label: string; reason: string }> = {
  flood_likelihood_0_100: { label: "โอกาสน้ำท่วม", reason: "ยังไม่มีการปรับเทียบโอกาสน้ำท่วมเฉพาะเหตุการณ์ที่รับรอง" },
  exposure_0_100: { label: "การสัมผัส", reason: "ยังไม่มีขอบเขตน้ำท่วมและการคำนวณการสัมผัสที่ตรงกับเหตุการณ์และผ่านเกณฑ์" },
  access_gap_0_100: { label: "ช่องว่างการเข้าถึง", reason: "สถานการณ์การเข้าถึงเป็นสมมติฐานตามแบบจำลอง ไม่ใช่ผลสังเกตของเหตุการณ์" },
  road_criticality_0_100: { label: "ความสำคัญของถนน", reason: "หลักฐานสภาพถนนและความสำคัญของเส้นทางในเหตุการณ์ยังไม่ครบ" },
  vulnerability_context_0_100: { label: "ความเปราะบางและบริบท", reason: "นิยามอายุ การเชื่อมพื้นที่ และตัวหารปีที่ตรงกันยังไม่คลี่คลาย" },
};

export interface CandidateDecisionStage {
  id: string;
  title: { en: string; th: string };
  state: StageState;
  meaning: { en: string; th: string };
}

/**
 * These are candidate-package checkpoints, not canonical gate decisions.
 * The caller must have checksum-verified the package with fetchEvidencePackage.
 */
export function candidateDecisionStages(): CandidateDecisionStage[] {
  return [
    {
      id: "integrity",
      title: { en: "Published package integrity", th: "ความสมบูรณ์ของแพ็กเกจที่เผยแพร่" },
      state: "verified",
      meaning: {
        en: "The package bytes match the catalog SHA-256. This verifies identity, not scientific acceptance.",
        th: "ข้อมูลแพ็กเกจตรงกับ SHA-256 ในแค็ตตาล็อก เป็นการยืนยันตัวตนข้อมูล ไม่ใช่การรับรองทางวิทยาศาสตร์",
      },
    },
    {
      id: "reference",
      title: { en: "Qualified event reference", th: "ข้อมูลอ้างอิงเหตุการณ์ที่ผ่านเกณฑ์" },
      state: "not_recorded",
      meaning: {
        en: "This candidate package contains no qualified-reference or independent-review acceptance receipt.",
        th: "แพ็กเกจผู้สมัครนี้ไม่มีใบรับรองข้อมูลอ้างอิงที่ผ่านเกณฑ์หรือการตรวจสอบอิสระ",
      },
    },
    {
      id: "evaluation",
      title: { en: "Independent model evaluation", th: "การประเมินโมเดลโดยอิสระ" },
      state: "not_recorded",
      meaning: {
        en: "No accepted model evaluation is bound to this candidate package. Scenario comparisons are not evaluation receipts.",
        th: "ไม่มีผลประเมินโมเดลที่รับรองผูกกับแพ็กเกจผู้สมัครนี้ การเปรียบเทียบสถานการณ์ไม่ใช่ใบรับรองการประเมิน",
      },
    },
    {
      id: "decision",
      title: { en: "Downstream FPPS and action", th: "FPPS และระดับการดำเนินการปลายน้ำ" },
      state: "unavailable",
      meaning: {
        en: "Accepted FPPS and action class are null. Missing inputs are not zero and weights are not redistributed.",
        th: "FPPS และระดับการดำเนินการที่รับรองยังไม่มี ค่าที่ขาดไม่ใช่ศูนย์และไม่มีการปรับน้ำหนักใหม่",
      },
    },
    {
      id: "authorization",
      title: { en: "Operational authorization", th: "การอนุญาตใช้เชิงปฏิบัติการ" },
      state: "blocked",
      meaning: {
        en: "The published package is non-operational and official_warning is false.",
        th: "แพ็กเกจที่เผยแพร่ไม่ใช้เชิงปฏิบัติการ และ official_warning เป็น false",
      },
    },
  ];
}

function nextTab(current: ReportTab, key: string): ReportTab | null {
  const index = TABS.findIndex((tab) => tab.id === current);
  if (key === "Home") return TABS[0].id;
  if (key === "End") return TABS[TABS.length - 1].id;
  if (key === "ArrowRight") return TABS[(index + 1) % TABS.length].id;
  if (key === "ArrowLeft") return TABS[(index - 1 + TABS.length) % TABS.length].id;
  return null;
}

function visibleTime(value: string | null, th: boolean): string {
  return value ?? (th ? "หลายช่วงเวลา ดูข้อมูลแหล่งที่มา" : "Mixed periods; inspect source records");
}

export function StudioCandidateReport() {
  const [language] = useLanguage("en");
  const th = language === "th";
  const [catalog, setCatalog] = useState<EvidenceLibraryCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [selection, setSelection] = useState<CaseSelection>({});
  const [loaded, setLoaded] = useState<{ hash: string; value: EvidenceLibraryPackage | null; error: string | null }>({ hash: "", value: null, error: null });
  const [activeTab, setActiveTab] = useState<ReportTab>("technical");

  useEffect(() => {
    const controller = new AbortController();
    fetch(EVIDENCE_CATALOG_URL, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Catalog unavailable (${response.status}).`);
        return parseEvidenceCatalog(await response.json());
      })
      .then((value) => { if (!controller.signal.aborted) setCatalog(value); })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setCatalogError(error instanceof Error ? error.message : "Catalog unavailable");
      });
    const onPopState = () => setSelection(readCaseSelection(window.location.search));
    onPopState();
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
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoaded({ hash: reference.sha256, value: null, error: error instanceof Error ? error.message : "Package unavailable" });
      });
    return () => controller.abort();
  }, [catalog, reference]);

  const evidence = reference?.sha256 === loaded.hash ? loaded.value : null;
  const packageError = reference?.sha256 === loaded.hash ? loaded.error : null;
  const aoi = catalog?.aois.find((item) => item.id === reference?.aoi_id);
  const event = catalog?.events.find((item) => item.id === reference?.event_id);
  const stages = evidence ? candidateDecisionStages() : [];
  const unresolvedStages = stages.filter((stage) => stage.state !== "verified").length;
  const caseQuery = { ...selection, aoi: reference?.aoi_id, event: reference?.event_id, version: catalog?.package_version };
  const qualityCounts = evidence ? {
    available: evidence.datasets.filter((item) => item.availability === "available").length,
    partial: evidence.datasets.filter((item) => item.availability === "partial").length,
    limited: evidence.datasets.filter((item) => !["available", "partial"].includes(item.availability)).length,
  } : null;
  const openTab = (tab: ReportTab) => {
    setActiveTab(tab);
    document.getElementById(`studio-candidate-tab-${tab}`)?.focus();
  };

  return <main id="main-content" tabIndex={-1} className={styles.report} lang={language} data-evidence-case-id={evidence?.id}>
    <header className={styles.heading}>
      <div>
        <p className={styles.eyebrow}>{th ? "รายงานการตรวจสอบ · กรณีศึกษาที่เลือก" : "VALIDATION REPORT · SELECTED STUDY CASE"}</p>
        <h1>{th ? "สถานะหลักฐานและเกณฑ์การตัดสินใจ" : "Evidence status and decision boundary"}</h1>
        {evidence && aoi && event ? <p className={styles.selectedCase}>{th ? aoi.name_th ?? aoi.name : aoi.name} — {th ? event.name_th ?? event.name : event.name}</p> : null}
        <p>{th ? "รายงานนี้ตรวจแพ็กเกจผู้สมัครที่เลือกเท่านั้น การตรวจสอบ checksum ไม่ใช่การรับรองข้อมูลสังเกต โมเดล หรือคะแนน FPPS" : "This report follows only the selected candidate package. A verified checksum does not qualify an event observation, model evaluation or FPPS."}</p>
      </div>
    </header>

    {catalogError ? <p className={styles.error} role="alert">{th ? "โหลดรายการกรณีศึกษาไม่ได้" : "Case catalog unavailable"}: {catalogError}</p> : null}
    {!catalog && !catalogError ? <p className={styles.loading} role="status">{th ? "กำลังโหลดรายการกรณีศึกษา…" : "Loading case catalog…"}</p> : null}
    {catalog && !reference ? <p className={styles.loading}>{th ? "เลือกกรณีศึกษาที่เผยแพร่ด้านบนเพื่อดูรายงานของแพ็กเกจนั้น" : "Choose a published case above to inspect its own package report."}</p> : null}
    {packageError ? <p className={styles.error} role="alert">{th ? "ตรวจสอบแพ็กเกจไม่ผ่าน" : "Package verification failed"}: {packageError}</p> : null}
    {reference && !evidence && !packageError ? <p className={styles.loading} role="status">{th ? "กำลังตรวจสอบ checksum ของแพ็กเกจ…" : "Verifying package checksum…"}</p> : null}

    {evidence && reference && aoi && event ? <>
      <section className={styles.summary} aria-label={th ? "สรุปการตรวจสอบ" : "Validation summary"}>
        <div><span>{th ? "ความสมบูรณ์ของแพ็กเกจ" : "Package integrity"}</span><strong>{th ? "ตรวจสอบแล้ว" : "Verified"}</strong><small>{th ? "ตรงกับ SHA-256 ในแค็ตตาล็อก" : "Catalog SHA-256 matches"}</small></div>
        <div><span>{th ? "ขั้นตอนการตัดสินใจที่ยังไม่พร้อม" : "Unresolved decision stages"}</span><strong>{unresolvedStages}</strong><small>{th ? "รายการสรุปด้านล่าง ไม่ใช่จำนวน gate อย่างเป็นทางการ" : "Report checkpoints, not a canonical gate count"}</small></div>
        <div><span>{th ? "FPPS / ชั้นการดำเนินการที่รับรอง" : "Accepted FPPS / action class"}</span><strong>{th ? "ยังไม่มี" : "Unavailable"}</strong><small>{th ? "ค่า null ในแพ็กเกจนี้" : "Null in this package"}</small></div>
      </section>

      <section className={styles.panel} aria-labelledby="candidate-matrix-title">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>01 · {th ? "ขอบเขตการตัดสินใจ" : "DECISION BOUNDARY"}</p><h2 id="candidate-matrix-title">{th ? "ตารางสถานะหลักฐานผู้สมัคร" : "Candidate evidence decision matrix"}</h2></div>
          <p>{th ? "แต่ละแถวใช้ข้อมูลแพ็กเกจนี้เท่านั้น ไม่ยืมผลตรวจจากคลังรายงานเก่า" : "Every row describes this package only; historical technical checks are not borrowed."}</p></div>
        <div className={styles.decisionTable}><div className={styles.tableWrap} tabIndex={0} role="region" aria-label={th ? "ตารางสถานะหลักฐาน เลื่อนแนวนอนได้" : "Evidence status table; scroll horizontally"}>
          <table className={styles.matrix}><thead><tr><th>{th ? "ขั้นตอน" : "Stage"}</th><th>{th ? "สถานะ" : "State"}</th><th>{th ? "ความหมาย" : "Meaning"}</th></tr></thead>
            <tbody>{stages.map((stage) => <tr key={stage.id}><th scope="row">{stage.title[language]}</th><td><span className={`${styles.state} ${styles[stage.state]}`}>{stage.state === "verified" ? (th ? "ตรวจสอบแล้ว" : "Verified") : stage.state === "not_recorded" ? (th ? "ไม่มีบันทึกในแพ็กเกจ" : "Not recorded here") : stage.state === "unavailable" ? (th ? "ยังไม่มี" : "Unavailable") : (th ? "ไม่อนุญาต" : "Blocked")}</span></td><td>{stage.meaning[language]}</td></tr>)}</tbody>
          </table>
        </div></div>
        <ul className={styles.decisionCards}>{stages.map((stage) => <li key={stage.id}><div><strong>{stage.title[language]}</strong><span className={`${styles.state} ${styles[stage.state]}`}>{stage.state === "verified" ? (th ? "ตรวจสอบแล้ว" : "Verified") : stage.state === "not_recorded" ? (th ? "ไม่มีบันทึก" : "Not recorded") : stage.state === "unavailable" ? (th ? "ยังไม่มี" : "Unavailable") : (th ? "ไม่อนุญาต" : "Blocked")}</span></div><p>{stage.meaning[language]}</p></li>)}</ul>
      </section>

      <section className={styles.panel} aria-labelledby="candidate-next-title">
        <div className={styles.sectionHeading}><div><p className={styles.eyebrow}>02 · {th ? "งานตรวจสอบต่อ" : "NEXT VERIFICATION"}</p><h2 id="candidate-next-title">{th ? "สิ่งที่ต้องพิสูจน์ต่อ" : "What still needs evidence"}</h2></div>
          <p>{th ? "รายการนี้เป็นงานตรวจสอบ ไม่ใช่การอนุมัติหรือกำหนดผู้ตรวจ" : "These are verification tasks, not approvals or reviewer assignments."}</p></div>
        {evidence.decision_brief?.next_actions.length ? <ol className={styles.actions}>{[...evidence.decision_brief.next_actions].sort((left, right) => left.order - right.order).map((action) => <li key={action.id}><strong lang={th && !TH_ACTIONS[action.id] ? "en" : undefined}>{th ? TH_ACTIONS[action.id]?.action ?? action.action : action.action}</strong><p lang={th && !TH_ACTIONS[action.id] ? "en" : undefined}>{th ? TH_ACTIONS[action.id]?.reason ?? action.reason : action.reason}</p></li>)}</ol>
          : <p>{th ? "ไม่มีรายการงานตรวจสอบเฉพาะกรณีในแพ็กเกจนี้ ดูข้อจำกัดของแหล่งข้อมูลในคลังข้อมูล" : "No case-specific next actions are published in this package. Inspect source limitations in the library."}</p>}
      </section>

      <nav className={styles.tabs} role="tablist" aria-label={th ? "ส่วนของรายงานหลักฐาน" : "Evidence report sections"} onKeyDown={(event) => {
        const next = nextTab(activeTab, event.key);
        if (next) { event.preventDefault(); openTab(next); }
      }}>
        {TABS.map((tab) => <button key={tab.id} type="button" id={`studio-candidate-tab-${tab.id}`} role="tab" aria-selected={activeTab === tab.id} aria-controls="studio-candidate-panel" tabIndex={activeTab === tab.id ? 0 : -1} onClick={() => openTab(tab.id)}>{tab[language]}</button>)}
      </nav>
      <section className={styles.panel} id="studio-candidate-panel" role="tabpanel" aria-labelledby={`studio-candidate-tab-${activeTab}`} tabIndex={0}>
        {activeTab === "technical" ? <>
          <h2>{th ? "การตรวจสอบทางเทคนิค" : "Technical verification"}</h2>
          <p>{th ? "แพ็กเกจที่แสดงผ่านการตรวจสอบ SHA-256 เทียบกับแค็ตตาล็อกที่เผยแพร่ การตรวจนี้ไม่ได้ยืนยันความถูกต้องของการตรวจจับน้ำท่วม การเข้าถึง หรือความปลอดภัยของถนน" : "The displayed package passed its published catalog SHA-256 check. This check does not validate flood detection, access modelling or road safety."}</p>
          <dl className={styles.facts}><div><dt>{th ? "แพ็กเกจ" : "Package"}</dt><dd><code>{evidence.id}</code></dd></div><div><dt>{th ? "เวอร์ชัน" : "Version"}</dt><dd><code>{evidence.package_version}</code></dd></div><div><dt>{th ? "ช่วงแหล่งข้อมูล" : "Source observation period"}</dt><dd>{visibleTime(evidence.source_timestamp, th)}</dd></div></dl>
        </> : null}
        {activeTab === "observed" ? <>
          <h2>{th ? "ข้อมูลเหตุการณ์ที่สังเกต" : "Observed-event reference"}</h2>
          <p>{th ? "ขอบเขตน้ำท่วมเป็นผู้สมัครและการปิดถนนเป็นสมมติฐาน ไม่มีหลักฐานอ้างอิงเหตุการณ์ที่ผ่านเกณฑ์ผูกกับแพ็กเกจนี้ ข้อมูลนอกขอบเขตสังเกตไม่ถือว่าแห้ง" : "Flood extent is a candidate and closures are assumptions. No qualified event reference is bound to this package. Area outside observation coverage is not treated as dry."}</p>
          <p>{th ? "ขอบเขตเหตุการณ์" : "Event period"}: {event.start}–{event.end}. {th ? "ช่วงเวลาของแหล่งข้อมูลแต่ละรายการอยู่ในคลังข้อมูล" : "Individual source periods are listed in the evidence library."}</p>
        </> : null}
        {activeTab === "quality" && qualityCounts ? <>
          <h2>{th ? "คุณภาพและความครอบคลุมของข้อมูล" : "Data quality and coverage"}</h2>
          <p>{th ? `รายการแหล่งข้อมูลในแพ็กเกจ: ใช้ได้ ${qualityCounts.available}, บางส่วน ${qualityCounts.partial}, จำกัดหรือเป็น metadata ${qualityCounts.limited}` : `Package source entries: ${qualityCounts.available} available, ${qualityCounts.partial} partial, ${qualityCounts.limited} limited or metadata-only.`}</p>
          <p>{th ? "สถานะใช้ได้ไม่ได้แปลว่าผ่านเกณฑ์อ้างอิงเหตุการณ์ สิทธิ์การใช้และข้อจำกัดเป็นรายแหล่ง" : "Availability does not establish event-reference qualification. Rights and limitations vary by source."}</p>
          <details><summary>{th ? "ดูประเด็นคุณภาพที่บันทึกไว้" : "Inspect recorded quality findings"}</summary>{th ? <p>ข้อความจากบันทึกต้นทางภาษาอังกฤษ</p> : null}<ul className={styles.qualityList} lang={th ? "en" : undefined}>{evidence.datasets.flatMap((dataset) => dataset.qc.map((finding, index) => <li key={`${dataset.dataset_id}-${index}`}><code>{dataset.dataset_id}</code> {finding}</li>))}</ul></details>
        </> : null}
        {activeTab === "models" ? <>
          <h2>{th ? "โมเดล การประเมิน และความครบถ้วนของคะแนน" : "Models, evaluation and score completeness"}</h2>
          <p>{th ? "ไม่มีผลประเมินโมเดลที่ผ่านการรับรองผูกกับแพ็กเกจนี้ FPPS และชั้นการดำเนินการยังเป็น null; สถานการณ์ความไวไม่ใช่คะแนนเหตุการณ์ที่รับรอง" : "No accepted model evaluation is bound to this package. FPPS and action class remain null; sensitivity scenarios are not accepted event scores."}</p>
          <div className={styles.tableWrap} tabIndex={0} role="region" aria-label={th ? "ตารางองค์ประกอบ FPPS เลื่อนแนวนอนได้" : "FPPS component table; scroll horizontally"}><table className={styles.matrix}><thead><tr><th>{th ? "องค์ประกอบ" : "Component"}</th><th>{th ? "น้ำหนัก" : "Weight"}</th><th>{th ? "ค่า" : "Value"}</th><th>{th ? "สาเหตุที่ยังไม่มี" : "Reason unavailable"}</th></tr></thead><tbody>{evidence.assessment.components.map((component) => <tr key={component.id}><th scope="row" lang={th && !TH_COMPONENTS[component.id] ? "en" : undefined}>{th ? TH_COMPONENTS[component.id]?.label ?? component.label : component.label}</th><td>{Math.round(component.weight * 100)}%</td><td>{component.value ?? (th ? "ยังไม่มี" : "Unavailable")}</td><td lang={th && !TH_COMPONENTS[component.id] ? "en" : undefined}>{th ? TH_COMPONENTS[component.id]?.reason ?? component.reason ?? "—" : component.reason ?? "—"}</td></tr>)}</tbody></table></div>
        </> : null}
        {activeTab === "governance" ? <>
          <h2>{th ? "สิทธิ์และขอบเขตการใช้งาน" : "Governance and use boundary"}</h2>
          <dl className={styles.facts}><div><dt>{th ? "โหมดข้อมูล" : "Evidence mode"}</dt><dd>{th ? "ผู้สมัคร" : "Candidate"}</dd></div><div><dt>{th ? "สถานะเชิงปฏิบัติการ" : "Operational status"}</dt><dd>{th ? "ไม่ใช้เชิงปฏิบัติการ" : "Non-operational"}</dd></div><div><dt>{th ? "คำเตือนทางการ" : "Official warning"}</dt><dd>{th ? "ไม่ใช่" : "False"}</dd></div><div><dt>{th ? "ระดับการดำเนินการ" : "Action class"}</dt><dd>{th ? "ยังไม่มี" : "Unavailable"}</dd></div></dl>
          <p>{th ? "หลักฐานที่ตรงกับเหตุการณ์และองค์ประกอบคะแนนครบถ้วนยังไม่ผ่านการรับรอง การเปรียบเทียบสถานการณ์ไม่กำหนดลำดับความสำคัญเพื่อรับมือเหตุการณ์" : evidence.decision_brief?.priority.reason ?? "Downstream acceptance has not been established."}</p>
          <p>{th ? "การยืนยันข้อมูลและสิทธิ์แต่ละแหล่งอยู่ในคลังข้อมูล" : "Source-specific rights and clearance detail are available in the evidence library."}</p>
        </> : null}
        {activeTab === "files" ? <>
          <h2>{th ? "ไฟล์และประวัติข้อมูล" : "Files and provenance"}</h2>
          <dl className={styles.facts}><div><dt>{th ? "รหัสแพ็กเกจ" : "Package ID"}</dt><dd><code>{evidence.id}</code></dd></div><div><dt>{th ? "แฮชแพ็กเกจ" : "Package SHA-256"}</dt><dd><code>{reference.sha256}</code></dd></div><div><dt>{th ? "เวลาสังเกตการณ์" : "Source observation time"}</dt><dd>{visibleTime(evidence.source_timestamp, th)}</dd></div><div><dt>{th ? "เวลาสร้างผลวิเคราะห์" : "Analysis generated"}</dt><dd>{evidence.decision_brief?.finals_analysis?.generated_at ?? (th ? "ยังไม่มี" : "Unavailable")}</dd></div><div><dt>{th ? "เวลาสร้างแพ็กเกจ" : "Package generated"}</dt><dd>{evidence.generated_at}</dd></div></dl>
          <details><summary>{th ? "แฮชของข้อมูลนำเข้า" : "Input checksums"}</summary><dl className={styles.facts}>{Object.entries(evidence.input_hashes).map(([name, hash]) => <div key={name}><dt>{name}</dt><dd><code>{hash}</code></dd></div>)}</dl></details>
        </> : null}
        <div className={styles.panelLinks}><a href={caseHref("/studio/library/", caseQuery)}>{th ? "ตรวจสอบคลังข้อมูลฉบับเต็ม" : "Inspect the full evidence library"}</a><a href={caseHref("/studio/brief/", caseQuery)}>{th ? "เปิดบทสรุปสถานการณ์สมมติ" : "Open the scenario decision brief"}</a></div>
      </section>
      <p className={styles.footerNote}>{th ? "รายงานนี้ไม่ใช่คำเตือนภัยหรือการอนุญาตใช้เชิงปฏิบัติการ" : "This report is not a warning or operational authorization."} <a href="/studio/archive/">{th ? "คลังรายงานแม่สายเดิม" : "Historical Mae Sai technical archive"}</a></p>
    </> : null}
  </main>;
}
