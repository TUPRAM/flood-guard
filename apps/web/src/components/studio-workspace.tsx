"use client";

import Image from "next/image";
import { useState } from "react";

import { LanguageToggle } from "@/components/language-toggle";
import { GeoaiRealPanel } from "@/components/geoai-real-panel";
import { ModelRegistryPanel } from "@/components/model-registry-panel";
import { QualifiedEvidenceFoundationPanel } from "@/components/qualified-evidence-foundation-panel";
import { StatusBar } from "@/components/status-bar";
import { downloadText } from "@/lib/download";
import { formatConfidence, formatSourceTime } from "@/lib/format";
import {
  buildEvidenceDecisionMatrix,
  evidenceContextMatches,
  evidenceRecordFileName,
  evidenceRecordJson,
  type EvidenceDecisionStage,
} from "@/lib/studio-evidence";
import type { Language, ReadinessRow, StudyAreaId } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useLanguage } from "@/lib/use-language";

import {
  blockerPresentation,
  decisionReasonPresentation,
  readinessReasonPresentation,
} from "./studio-presentation";
import styles from "./studio-workspace.module.css";

type StudioTab = "technical" | "observed" | "quality" | "metrics" | "governance" | "files";

const TABS: Array<{ id: StudioTab; en: string; th: string }> = [
  { id: "technical", en: "Technical verification", th: "การตรวจสอบทางเทคนิค" },
  { id: "observed", en: "Observed-data validation", th: "การยืนยันด้วยข้อมูลสังเกตการณ์" },
  { id: "quality", en: "Data quality", th: "คุณภาพข้อมูล" },
  { id: "metrics", en: "Models & evaluation", th: "โมเดลและการประเมิน" },
  { id: "governance", en: "Governance", th: "ธรรมาภิบาล" },
  { id: "files", en: "Files & history", th: "ไฟล์และประวัติ" },
];

const STAGE_LABELS: Record<EvidenceDecisionStage, { en: string; th: string }> = {
  processing_execution: { en: "Processing execution", th: "การประมวลผล" },
  technical_verification: { en: "Technical verification", th: "การตรวจสอบทางเทคนิค" },
  observed_event_validation: { en: "Observed-event validation", th: "การยืนยันเหตุการณ์ที่สังเกต" },
  governance_decision: { en: "Governance decision", th: "การตัดสินใจด้านธรรมาภิบาล" },
  operational_authorization: { en: "Operational authorization", th: "การอนุญาตใช้งาน" },
};

const GATE_LABELS: Record<string, { en: string; th: string; requiredEn: string; requiredTh: string }> = {
  real_open_context: {
    en: "Open-context source integrity",
    th: "ความสมบูรณ์ของแหล่งข้อมูลเปิด",
    requiredEn: "A checksummed source and provenance manifest.",
    requiredTh: "รายการแหล่งข้อมูลและ provenance พร้อม checksum",
  },
  facility_verification: {
    en: "Facility verification",
    th: "การตรวจสอบสถานที่",
    requiredEn: "Agency verification of role, operating state, capacity, and accessibility.",
    requiredTh: "การยืนยันจากหน่วยงานเรื่องบทบาท สถานะเปิดให้บริการ ความจุ และการเข้าถึง",
  },
  segment_raster_intersection: {
    en: "Road-segment evidence",
    th: "หลักฐานระดับช่วงถนน",
    requiredEn: "A validated segment-to-raster intersection receipt.",
    requiredTh: "ใบรับรองการเชื่อมโยงช่วงถนนกับราสเตอร์ที่ผ่านการตรวจสอบ",
  },
  reference_mask: {
    en: "Event reference validation",
    th: "การยืนยันข้อมูลอ้างอิงเหตุการณ์",
    requiredEn: "A qualified Thailand event-flood reference with provenance and permission.",
    requiredTh: "ข้อมูลอ้างอิงน้ำท่วมเหตุการณ์ในไทยที่ผ่านเกณฑ์พร้อม provenance และสิทธิ์ใช้งาน",
  },
  reviewer_calibration: {
    en: "Independent reviewer calibration",
    th: "การปรับเทียบผู้ตรวจสอบอิสระ",
    requiredEn: "A passing blind reviewer-calibration and adjudication receipt.",
    requiredTh: "ใบรับรองการปรับเทียบและการตัดสินโดยผู้ตรวจสอบอิสระที่ผ่านเกณฑ์",
  },
  weak_reference_seed_scope: {
    en: "Reference-data scope",
    th: "ขอบเขตข้อมูลอ้างอิง",
    requiredEn: "A qualified in-area event reference and its permission record.",
    requiredTh: "ข้อมูลอ้างอิงเหตุการณ์ในพื้นที่ที่ผ่านการรับรองพร้อมบันทึกสิทธิ์",
  },
  cleared_training_labels: {
    en: "Training-label clearance",
    th: "การรับรองป้ายกำกับฝึกสอน",
    requiredEn: "A verified label-clearance receipt.",
    requiredTh: "ใบรับรองการอนุมัติป้ายกำกับที่ตรวจสอบได้",
  },
  canonical_projected_grid: {
    en: "Spatial alignment",
    th: "การจัดแนวเชิงพื้นที่",
    requiredEn: "A reproducible projected-grid check.",
    requiredTh: "การตรวจสอบกริดฉายภาพที่ทำซ้ำได้",
  },
  reviewer_calibration_complete: {
    en: "Reviewer calibration",
    th: "การปรับเทียบผู้ตรวจสอบ",
    requiredEn: "A passing independent reviewer-calibration receipt.",
    requiredTh: "ใบรับรองการปรับเทียบผู้ตรวจสอบอิสระที่ผ่านเกณฑ์",
  },
  blind_double_review: {
    en: "Independent double review",
    th: "การตรวจสอบซ้ำโดยอิสระ",
    requiredEn: "A complete, independently paired review record.",
    requiredTh: "บันทึกการตรวจสอบซ้ำที่จับคู่โดยอิสระและครบถ้วน",
  },
  immutable_training_labelset: {
    en: "Label-set integrity",
    th: "ความสมบูรณ์ของชุดป้ายกำกับ",
    requiredEn: "An immutable, checksummed label-set receipt.",
    requiredTh: "ใบรับรองชุดป้ายกำกับแบบคงที่พร้อม checksum",
  },
  query_model_safety_boundary: {
    en: "Training/evaluation separation",
    th: "การแยกข้อมูลฝึกสอนและประเมิน",
    requiredEn: "An independently verified separation receipt.",
    requiredTh: "ใบรับรองการแยกข้อมูลที่ตรวจสอบโดยอิสระ",
  },
  geographic_generalization: {
    en: "Geographic generalization",
    th: "การใช้กับพื้นที่อื่น",
    requiredEn: "Qualified validation across additional events and basins.",
    requiredTh: "การตรวจสอบที่ผ่านเกณฑ์ในเหตุการณ์และลุ่มน้ำเพิ่มเติม",
  },
};

function requestedStudyArea(evidenceContextId?: string): StudyAreaId {
  return evidenceContextId?.startsWith("fixture-thailand-demo:")
    ? "fixture_thailand_demo"
    : "mae_sai_candidate_v1";
}

function studyAreaLabel(studyArea: string, th: boolean): string {
  if (studyArea === "mae_sai_candidate_v1") return th ? "อำเภอแม่สาย จังหวัดเชียงราย" : "Mae Sai district, Chiang Rai";
  return th ? "พื้นที่อ้างอิงการตรวจสอบทางเทคนิค" : "Technical verification reference area";
}

function friendlyMode(mode: string, th: boolean): string {
  if (mode === "official_input") return th ? "ข้อมูลหน่วยงาน" : "Agency-provided evidence";
  if (mode === "candidate") return th ? "หลักฐานการวางแผนทางประวัติศาสตร์" : "Historical planning evidence";
  return th ? "หลักฐานการตรวจสอบทางเทคนิค" : "Technical verification evidence";
}

function friendlyOperationalState(value: string, th: boolean): string {
  if (value === "agency_operational") return th ? "ได้รับอนุญาตจากหน่วยงาน" : "Agency-authorized";
  if (value === "planning_only") return th ? "ใช้เพื่อการวางแผนเท่านั้น" : "Planning only";
  return th ? "ไม่ได้รับอนุญาตให้ใช้เชิงปฏิบัติการ" : "Not operationally authorized";
}

function shortDigest(value: string | null): string {
  if (!value) return "Not recorded";
  return `${value.slice(0, 12)}…${value.slice(-10)}`;
}

function gateCopy(row: ReadinessRow, th: boolean) {
  const known = GATE_LABELS[row.check_id];
  return {
    label: known?.[th ? "th" : "en"] ?? (th ? "ข้อกำหนดหลักฐาน" : "Evidence requirement"),
    required: known?.[th ? "requiredTh" : "requiredEn"] ?? (th ? "ต้องมีหลักฐานที่ตรวจสอบได้สำหรับข้อกำหนดนี้" : "A verifiable record satisfying this requirement."),
  };
}

function nextTab(current: StudioTab, key: string): StudioTab | null {
  const index = TABS.findIndex((tab) => tab.id === current);
  if (key === "Home") return TABS[0].id;
  if (key === "End") return TABS[TABS.length - 1].id;
  if (key === "ArrowRight") return TABS[(index + 1) % TABS.length].id;
  if (key === "ArrowLeft") return TABS[(index - 1 + TABS.length) % TABS.length].id;
  return null;
}

export interface StudioWorkspaceProps {
  evidenceContextId?: string;
}

export function StudioWorkspace({ evidenceContextId }: StudioWorkspaceProps = {}) {
  const data = useFloodGuardData({
    studyArea: requestedStudyArea(evidenceContextId),
    role: "studio",
    evidenceContextId,
  });
  const [language, setLanguage] = useLanguage("en");
  const [activeTab, setActiveTab] = useState<StudioTab>("technical");
  const th = language === "th";
  const context = data.evidenceContext;
  const record = data.evidenceRecord;
  const exactContext = evidenceContextMatches(context, record, evidenceContextId);
  const contextRun = context.model_run_id
    ? data.model_runs.find((run) => run.run_id === context.model_run_id)
    : undefined;
  const decisionRows = buildEvidenceDecisionMatrix(context, record);
  const blockedGateCount = data.readiness.filter((row) => row.status !== "ready").length;
  const unavailable = data.dataState === "unavailable" || !exactContext;

  return (
    <main className="studio-page studio-final-surface" lang={language}>
      <header className="studio-header studio-final-header">
        <a href="/studio/" className="brand brand-light">
          <Image src="/icon.svg" alt="" width={40} height={40} priority />
          <span><b>FloodGuard</b><small>{th ? "รายงานการตรวจสอบหลักฐาน" : "Validation & evidence report"}</small></span>
        </a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a href="/command/">{th ? "การวางแผน" : "Planning"}</a><a className="active" href="/studio/">Studio</a></nav>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>
      <StatusBar data={data} language={language} compact />

      <div className={`studio-shell studio-final-shell ${styles.shell}`}>
        <section className={styles.hero} aria-labelledby="research-console-title">
          <div>
            <p className="eyebrow">{th ? "รายงานแบบอ่านอย่างเดียว" : "Read-only evidence report"}</p>
            <h1 id="research-console-title">{th ? "การตรวจสอบและหลักฐาน" : "Validation & evidence report"}</h1>
            <p>{th ? "ตรวจสอบแหล่งข้อมูล คุณภาพ การประเมิน และข้อจำกัดของหลักฐานชุดเดียวกัน โดยไม่เปลี่ยนสถานะหรืออนุมัติการใช้งาน" : "Inspect provenance, quality, evaluation, and authorization for one immutable evidence context. This report does not change state or grant approval."}</p>
            <div className={styles.heroMeta}>
              <span>{th ? "เวลาบริบทน้ำท่วม" : "Flood-context time"}: <b>{formatSourceTime(data.status.source_timestamp, language)}</b></span>
              <span>{th ? "ความเชื่อมั่น" : "Confidence"}: <b>{formatConfidence(data.status.confidence_class, language)}</b></span>
            </div>
          </div>
          <dl className={styles.heroSummary}>
            <div><dt>{th ? "บริบทหลักฐาน" : "Evidence context"}</dt><dd>{exactContext ? (th ? "ตรงกัน" : "Exact match") : (th ? "ไม่ตรงกัน" : "Mismatch")}</dd></div>
            <div><dt>{th ? "ข้อกำหนดที่ยังไม่ผ่าน" : "Blocking evidence gates"}</dt><dd>{blockedGateCount}</dd></div>
            <div><dt>{th ? "การอนุญาตใช้งาน" : "Authorization"}</dt><dd>{record?.operational_authorized ? (th ? "อนุญาต" : "Authorized") : (th ? "ไม่อนุญาต" : "Not authorized")}</dd></div>
          </dl>
        </section>

        <section className={styles.contextHeader} aria-labelledby="evidence-context-title">
          <div className={styles.contextHeading}>
            <div><p className="eyebrow">{th ? "บริบทหลักฐานที่กำลังดู" : "ACTIVE EVIDENCE CONTEXT"}</p><h2 id="evidence-context-title">{studyAreaLabel(context.study_area_id, th)}</h2></div>
            <span className={record?.operational_authorized ? styles.authorized : styles.blocked}>{friendlyOperationalState(context.operational_status, th)}</span>
          </div>
          <dl className={styles.contextGrid}>
            <div><dt>{th ? "รหัสบริบท" : "Evidence-context ID"}</dt><dd><code>{context.evidence_context_id}</code></dd></div>
            <div><dt>{th ? "แพ็กเกจหลักฐาน" : "Evidence package"}</dt><dd><code>{context.evidence_package_id}</code></dd></div>
            <div><dt>{th ? "การประเมิน" : "Evaluation"}</dt><dd><code>{context.model_run_id ?? "not_recorded"}</code></dd></div>
            <div><dt>{th ? "โมเดลและเวอร์ชัน" : "Model & version"}</dt><dd><code>{record?.model_id ?? "not_recorded"} · {record?.model_version ?? "not_recorded"}</code></dd></div>
            <div><dt>{th ? "เวอร์ชันข้อมูล" : "Data version"}</dt><dd><code>{context.data_version}</code></dd></div>
            <div><dt>{th ? "ขอบเขตหลักฐาน" : "Evidence scope"}</dt><dd>{record?.evidence_scope ?? (th ? "ยังไม่มีบันทึก" : "Not recorded")}</dd></div>
            <div><dt>{th ? "โหมดข้อมูล" : "Canonical mode"}</dt><dd>{friendlyMode(context.dataset_mode, th)} <code>{context.dataset_mode}</code></dd></div>
            <div><dt>{th ? "สถานะการอนุญาต" : "Canonical authorization"}</dt><dd><code>{record?.operational_authorized ? "operational_authorized" : "not_authorized"}</code></dd></div>
          </dl>
        </section>

        {unavailable ? (
          <section className={styles.unavailable} role="status" aria-live="polite">
            <span aria-hidden="true">!</span>
            <div>
              <h2>{th ? "ไม่มีการประเมินสำหรับแพ็กเกจหลักฐานนี้" : "Evaluation unavailable for this evidence package."}</h2>
              <p>{th ? "ระบบจะไม่เปลี่ยนไปใช้พื้นที่ เวอร์ชันข้อมูล หรือการประเมินอื่นโดยอัตโนมัติ โปรดเปิดลิงก์จากรายการหลักฐานที่เผยแพร่แล้ว" : "FloodGuard will not substitute another study area, data version, or evaluation. Open a context from the published evidence catalog."}</p>
            </div>
          </section>
        ) : (
          <>
            <div className={styles.tabs} role="tablist" aria-label={th ? "ส่วนรายงานทางเทคนิค" : "Technical report sections"}>
              {TABS.map((tab) => (
                <button
                  type="button"
                  role="tab"
                  id={`studio-tab-${tab.id}`}
                  aria-controls="studio-tab-panel"
                  aria-selected={activeTab === tab.id}
                  tabIndex={activeTab === tab.id ? 0 : -1}
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  onKeyDown={(event) => {
                    const target = nextTab(tab.id, event.key);
                    if (!target) return;
                    event.preventDefault();
                    setActiveTab(target);
                    document.getElementById(`studio-tab-${target}`)?.focus();
                  }}
                >
                  {th ? tab.th : tab.en}
                </button>
              ))}
            </div>

            <div id="studio-tab-panel" role="tabpanel" aria-labelledby={`studio-tab-${activeTab}`} className={styles.tabPanel}>
              {activeTab === "technical" && (
                <section aria-labelledby="decision-matrix-title">
                  <div className={styles.sectionHeading}><div><p className="eyebrow">01 · {th ? "ขอบเขตการตัดสินใจ" : "DECISION BOUNDARY"}</p><h2 id="decision-matrix-title">{th ? "เมทริกซ์สถานะหลักฐาน" : "Evidence decision matrix"}</h2></div><p>{th ? "แต่ละแถวแสดงหลักฐานที่บันทึกจริง ไม่ได้อนุมานสถานะจากหน้าจออื่น" : "Each row reflects an explicit record; no decision or authority is inferred from another readiness flag."}</p></div>
                  <div className={styles.tableScroll}>
                    <table className={styles.reportTable}>
                      <thead><tr><th>{th ? "ขั้นตอน" : "Stage"}</th><th>{th ? "สถานะ" : "Canonical state"}</th><th>{th ? "ความหมาย" : "Meaning"}</th></tr></thead>
                      <tbody>{decisionRows.map((row) => <tr key={row.stage}><td><b>{STAGE_LABELS[row.stage][language]}</b><code>{row.stage}</code></td><td><span className={`${styles.state} ${styles[row.state]}`}>{row.state}</span></td><td>{decisionReasonPresentation(row, language)}</td></tr>)}</tbody>
                    </table>
                  </div>
                  {!contextRun && <article className={styles.notice}><b>{th ? "ไม่มีการประเมินโมเดลที่ผูกกับบริบทนี้" : "No model evaluation is bound to this context."}</b><p>{th ? "เมตริกหรือผลการตรวจสอบจากแพ็กเกจอื่นจะไม่ถูกนำมาแสดงแทน" : "Metrics and technical results from another evidence package are intentionally not substituted."}</p></article>}
                  {!contextRun && (data.model_registry?.length ?? 0) > 0 && (
                    <article className={styles.notice}>
                      <b>{th ? "มีบันทึกโมเดลที่ถูกบล็อกสำหรับการตรวจสอบทางเทคนิค" : "A blocked model record is available for technical inspection."}</b>
                      <p>{th ? "เปิดแท็บโมเดลและการประเมินเพื่อดูสายข้อมูลและเหตุผลที่ถูกบล็อก บันทึกนี้ไม่ได้ผูกกับบริบทหลักฐานและไม่มีสิทธิ์เข้าสู่ชั้นการตัดสินใจ" : "Open Models & evaluation to inspect its lineage and blocker. The record is not bound to this evidence context and cannot enter the decision layer."}</p>
                    </article>
                  )}
                </section>
              )}

              {activeTab === "observed" && (
                <section aria-labelledby="observed-title">
                  <div className={styles.sectionHeading}><div><p className="eyebrow">02 · {th ? "ขอบเขตข้อมูลสังเกตการณ์" : "OBSERVED-DATA SCOPE"}</p><h2 id="observed-title">{th ? "สถานะการยืนยันเหตุการณ์" : "Observed-event validation"}</h2></div></div>
                  <article className={styles.notice}>
                    <b>{th ? "ยังไม่มีการยืนยันด้วยข้อมูลสังเกตการณ์" : "Observed-event validation is not recorded"}</b>
                    <p>{th ? "บริบทน้ำท่วมเดือนกันยายน 2024 เป็นหลักฐานการวางแผนทางประวัติศาสตร์ สภาพปัจจุบันยังไม่ทราบและต้องยืนยันกับหน่วยงานท้องถิ่น" : "The September 2024 flood context is historical planning evidence. Current conditions are unknown and require local-authority confirmation."}</p>
                  </article>
                  <SourceHistory language={language} data={data} roles={["historic_flood_context", "reporting_boundaries"]} />
                </section>
              )}

              {activeTab === "quality" && (
                <section aria-labelledby="quality-title">
                  <div className={styles.sectionHeading}><div><p className="eyebrow">03 · {th ? "คุณภาพข้อมูล" : "DATA QUALITY"}</p><h2 id="quality-title">{th ? "ตารางหลักฐานที่ยังขาด" : "Blocking evidence table"}</h2></div><span>{blockedGateCount} {th ? "ข้อกำหนด" : "gates"}</span></div>
                  <div className={styles.tableScroll}>
                    <table className={styles.reportTable}>
                      <thead><tr><th>{th ? "ข้อกำหนด" : "Gate"}</th><th>{th ? "สถานะ" : "State"}</th><th>{th ? "เหตุผล" : "Reason"}</th><th>{th ? "หลักฐานที่ต้องมี" : "Required evidence"}</th><th>{th ? "ลิงก์" : "Evidence link"}</th><th>{th ? "อัปเดตล่าสุด" : "Last update"}</th></tr></thead>
                      <tbody>{data.readiness.map((row) => {
                        const copy = gateCopy(row, th);
                        return <tr key={row.check_id}><td><b>{copy.label}</b><code>{row.check_id}</code></td><td><span className={`${styles.state} ${styles[row.status === "ready" ? "recorded" : "blocked"]}`}>{row.status}</span></td><td>{readinessReasonPresentation(row, language)}</td><td>{copy.required}</td><td>{th ? "ยังไม่เผยแพร่" : "Not published"}</td><td>{formatSourceTime(context.generated_at, language)}</td></tr>;
                      })}</tbody>
                    </table>
                  </div>
                </section>
              )}

              {activeTab === "metrics" && (
                <>
                  <QualifiedEvidenceFoundationPanel
                    foundation={data.qualified_evidence_foundation}
                    language={language}
                  />
                  <ModelRegistryPanel
                    context={context}
                    entries={data.model_registry ?? []}
                    evaluations={data.model_evaluations ?? []}
                    products={data.observation_products ?? []}
                    evidenceState={data.modelEvidenceState}
                    evidenceReason={data.modelEvidenceReason}
                    language={language}
                  />
                  <GeoaiRealPanel language={language} variant="studio" />
                </>
              )}

              {activeTab === "governance" && (
                <section aria-labelledby="governance-title">
                  <div className={styles.sectionHeading}><div><p className="eyebrow">05 · {th ? "ธรรมาภิบาล" : "GOVERNANCE"}</p><h2 id="governance-title">{th ? "การตัดสินใจและอำนาจที่บันทึก" : "Recorded decision and authority"}</h2></div></div>
                  <dl className={styles.governanceGrid}>
                    <div><dt>{th ? "การตัดสินใจ" : "Decision"}</dt><dd><code>{record?.decision ?? "not_recorded"}</code></dd></div>
                    <div><dt>{th ? "ผู้มีอำนาจตัดสินใจ" : "Decision authority"}</dt><dd><code>{record?.decision_authority ?? "not_recorded"}</code></dd></div>
                    <div><dt>{th ? "เวลาตัดสินใจ" : "Decision time"}</dt><dd><code>{record?.decision_at ?? "not_recorded"}</code></dd></div>
                    <div><dt>{th ? "การอนุญาตใช้งาน" : "Operational authorization"}</dt><dd><code>{record?.operational_authorized ? "true" : "false"}</code></dd></div>
                  </dl>
                  <article className={styles.blockers}><h3>{th ? "เหตุผลที่ไม่อนุญาต" : "Authorization blockers"}</h3>{record?.blockers.length ? <ul>{record.blockers.map((blocker) => <li key={blocker}>{blockerPresentation(blocker, language)}</li>)}</ul> : <p>{th ? "ไม่มีเหตุผลที่บันทึก" : "No blockers are recorded."}</p>}</article>
                </section>
              )}

              {activeTab === "files" && (
                <section aria-labelledby="files-title">
                  <div className={styles.sectionHeading}><div><p className="eyebrow">06 · {th ? "ไฟล์และประวัติ" : "FILES & HISTORY"}</p><h2 id="files-title">{th ? "บันทึกหลักฐานและแหล่งข้อมูล" : "Evidence record and source history"}</h2></div>{record && <button type="button" className={styles.download} onClick={() => downloadText(evidenceRecordFileName(record), evidenceRecordJson(record), "application/json")}>{th ? "ดาวน์โหลดบันทึก JSON" : "Download canonical JSON"}</button>}</div>
                  <dl className={styles.fileGrid}>
                    <div><dt>{th ? "รหัสบันทึก" : "Evidence-record ID"}</dt><dd><code>{record?.evidence_record_id ?? "not_recorded"}</code></dd></div>
                    <div><dt>{th ? "Checksum แพ็กเกจ" : "Package checksum"}</dt><dd title={context.evidence_package_sha256}><code>{shortDigest(context.evidence_package_sha256)}</code></dd></div>
                    <div><dt>{th ? "Checksum การประเมิน" : "Evaluation checksum"}</dt><dd title={record?.evaluation_sha256 ?? undefined}><code>{shortDigest(record?.evaluation_sha256 ?? null)}</code></dd></div>
                    <div><dt>{th ? "Checksum โมเดล" : "Model checksum"}</dt><dd title={record?.model_sha256 ?? undefined}><code>{shortDigest(record?.model_sha256 ?? null)}</code></dd></div>
                    <div><dt>{th ? "สร้างบริบทเมื่อ" : "Context generated"}</dt><dd>{formatSourceTime(context.generated_at, language)}</dd></div>
                    <div><dt>{th ? "สร้างบันทึกเมื่อ" : "Record generated"}</dt><dd>{record ? formatSourceTime(record.generated_at, language) : (th ? "ยังไม่บันทึก" : "Not recorded")}</dd></div>
                  </dl>
                  <SourceHistory language={language} data={data} />
                </section>
              )}
            </div>
          </>
        )}

        <footer className="studio-footer"><span>{th ? "รายงานนี้ไม่ใช่คำเตือนภัยหรือการอนุญาตใช้งาน" : "This report is not a warning or operational authorization."}</span><a href="/command/">{th ? "เปิดพื้นที่วางแผน →" : "Open planning workspace →"}</a></footer>
      </div>
    </main>
  );
}

function SourceHistory({ language, data, roles }: { language: Language; data: ReturnType<typeof useFloodGuardData>; roles?: string[] }) {
  const th = language === "th";
  const components = roles
    ? data.evidenceContext.source_components.filter((component) => roles.includes(component.role))
    : data.evidenceContext.source_components;
  return (
    <div className={styles.tableScroll}>
      <table className={styles.reportTable}>
        <thead><tr><th>{th ? "องค์ประกอบ" : "Source component"}</th><th>{th ? "บทบาท" : "Role"}</th><th>{th ? "เวลาของแหล่งข้อมูล" : "Source time"}</th><th>{th ? "ความหมายของเวลา" : "Temporal meaning"}</th><th>{th ? "ความใหม่" : "Freshness"}</th><th>{th ? "ตรวจสอบล่าสุด" : "Last checked"}</th></tr></thead>
        <tbody>{components.map((component) => <tr key={component.source_component_id}><td><b>{component.source_name}</b><code>{component.source_component_id}</code></td><td><code>{component.role}</code></td><td>{component.source_timestamp ? formatSourceTime(component.source_timestamp, language) : (th ? "ไม่ทราบ" : "Unknown")}</td><td><code>{component.temporal_meaning}</code></td><td><span className={`${styles.state} ${component.freshness === "current" ? styles.recorded : styles.not_recorded}`}>{component.freshness}</span></td><td>{component.last_checked_at ? formatSourceTime(component.last_checked_at, language) : (th ? "ยังไม่บันทึก" : "Not recorded")}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
