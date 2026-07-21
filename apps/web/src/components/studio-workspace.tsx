"use client";

import Image from "next/image";
import { useState } from "react";

import type { ModelRun } from "@floodguard/contracts";

import { LanguageToggle } from "@/components/language-toggle";
import { StatusBar } from "@/components/status-bar";
import { StudioProofPanel } from "@/components/studio-proof-panel";
import { downloadText } from "@/lib/download";
import { formatConfidence, formatNumber, formatSourceTime } from "@/lib/format";
import { useFloodGuardData } from "@/lib/use-floodguard-data";
import { useLanguage } from "@/lib/use-language";

import styles from "./studio-proof-panel.module.css";

const METRICS = [
  ["iou", "IoU"],
  ["f1_dice", "F1 / Dice"],
  ["precision", "Precision"],
  ["recall", "Recall"],
  ["area_error_ratio", "Area error"],
  ["brier_score", "Brier"],
  ["expected_calibration_error", "Calibration ECE"],
] as const;

function familyLabel(value: string): string {
  if (value === "deterministic_sar_baseline") return "SAR reference model";
  if (value === "weak_label_logistic") return "Logistic benchmark";
  return "GeoAI model";
}

function publicationText(value: string): string {
  return value
    .replace(/legacy[_ -]?synthetic[_ -]?sar[_ -]?v1/gi, "versioned radar-change")
    .replace(/fixture[_ -]?demo/gi, "technical reference")
    .replace(/synthetic/gi, "technical")
    .replace(/candidate/gi, "context")
    .replace(/non[_ -]?operational/gi, "review only");
}

function architectureLabel(value: string | null): string {
  if (!value) return "Unavailable";
  const label = publicationText(value).replaceAll("_", " ");
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}`;
}

function preprocessingLabel(value: string, th: boolean): string {
  if (/legacy[_ -]?synthetic[_ -]?sar[_ -]?v1/i.test(value)) {
    return th
      ? "สูตรการเปลี่ยนแปลงเรดาร์แบบกำหนดเวอร์ชันพร้อมหน่วยทางกายภาพ"
      : "Versioned radar-change formula with explicit physical units";
  }
  return publicationText(value);
}

function evidenceScopeLabel(mode: ModelRun["dataset_mode"], th: boolean): string {
  if (mode === "official_input") return th ? "การประเมินข้อมูลสังเกตการณ์" : "Observed-data evaluation";
  if (mode === "candidate") return th ? "หลักฐานบริบท" : "Context evidence";
  return th ? "การตรวจสอบระบบ" : "Technical verification";
}

function runStatusLabel(status: string, th: boolean): string {
  if (status === "completed") return th ? "ตรวจสอบเสร็จสิ้น" : "Review complete";
  if (status === "failed") return th ? "ต้องตรวจสอบอีกครั้ง" : "Review required";
  return th ? "อยู่ระหว่างตรวจสอบ" : "In review";
}

function readinessCopy(checkId: string, ready: boolean, th: boolean): {
  label: string;
  source: string;
  state: string;
  reason: string;
} {
  const copy: Record<string, { label: [string, string]; source: [string, string]; reason: [string, string] }> = {
    reference_mask: {
      label: ["Reference validation", "การตรวจสอบข้อมูลอ้างอิง"],
      source: ["Reference data record", "บันทึกข้อมูลอ้างอิง"],
      reason: ["An independently validated reference is required.", "ต้องมีข้อมูลอ้างอิงที่ผ่านการตรวจสอบโดยอิสระ"],
    },
    weak_reference_seed_scope: {
      label: ["Reference selection", "การเลือกข้อมูลอ้างอิง"],
      source: ["Reference data record", "บันทึกข้อมูลอ้างอิง"],
      reason: ["An independently validated reference is required.", "ต้องมีข้อมูลอ้างอิงที่ผ่านการตรวจสอบโดยอิสระ"],
    },
    sentinel1_provenance: {
      label: ["Radar source verification", "การตรวจสอบแหล่งข้อมูลเรดาร์"],
      source: ["Earth observation record", "บันทึกข้อมูลสำรวจโลก"],
      reason: ["Product identity and acquisition time need verification.", "ต้องตรวจสอบรหัสผลิตภัณฑ์และเวลาที่บันทึกข้อมูล"],
    },
    canonical_projected_grid: {
      label: ["Spatial alignment", "การจัดแนวเชิงพื้นที่"],
      source: ["Spatial quality record", "บันทึกคุณภาพเชิงพื้นที่"],
      reason: ["Spatial alignment checks are complete.", "การตรวจสอบการจัดแนวเชิงพื้นที่เสร็จสมบูรณ์"],
    },
    reviewer_calibration: {
      label: ["Independent reviewer calibration", "การปรับเทียบผู้ตรวจสอบอิสระ"],
      source: ["Independent review record", "บันทึกการตรวจสอบอิสระ"],
      reason: ["Independent reviewer calibration has not yet been verified.", "ยังไม่ได้ยืนยันการปรับเทียบผู้ตรวจสอบอิสระ"],
    },
    reviewer_calibration_complete: {
      label: ["Independent reviewer calibration", "การปรับเทียบผู้ตรวจสอบอิสระ"],
      source: ["Independent review record", "บันทึกการตรวจสอบอิสระ"],
      reason: ["Independent reviewer calibration has not yet been verified.", "ยังไม่ได้ยืนยันการปรับเทียบผู้ตรวจสอบอิสระ"],
    },
    blind_double_review: {
      label: ["Independent double review", "การตรวจสอบซ้ำโดยอิสระ"],
      source: ["Independent review record", "บันทึกการตรวจสอบอิสระ"],
      reason: ["A complete independent double review is still required.", "ยังต้องมีการตรวจสอบซ้ำโดยอิสระให้ครบถ้วน"],
    },
    cleared_training_labels: {
      label: ["Training-label approval", "การรับรองป้ายกำกับฝึกสอน"],
      source: ["Label quality record", "บันทึกคุณภาพป้ายกำกับ"],
      reason: ["Independent label approval is still required.", "ยังต้องมีการรับรองป้ายกำกับโดยอิสระ"],
    },
    immutable_training_labelset: {
      label: ["Training-label integrity", "ความสมบูรณ์ของป้ายกำกับฝึกสอน"],
      source: ["Label quality record", "บันทึกคุณภาพป้ายกำกับ"],
      reason: ["A verified, versioned label record is still required.", "ยังต้องมีบันทึกป้ายกำกับที่ยืนยันและกำหนดเวอร์ชันแล้ว"],
    },
    query_model_safety_boundary: {
      label: ["Evaluation separation", "การแยกข้อมูลประเมิน"],
      source: ["Model governance record", "บันทึกธรรมาภิบาลโมเดล"],
      reason: ["Training and evaluation data must remain independently reviewed.", "ข้อมูลฝึกสอนและข้อมูลประเมินต้องได้รับการตรวจสอบแยกจากกัน"],
    },
    geographic_generalization: {
      label: ["Geographic coverage", "ความครอบคลุมเชิงพื้นที่"],
      source: ["Regional validation record", "บันทึกการตรวจสอบระดับภูมิภาค"],
      reason: ["Additional events and basins are required before broader use.", "ต้องมีเหตุการณ์และลุ่มน้ำเพิ่มเติมก่อนขยายการใช้งาน"],
    },
  };
  const item = copy[checkId];
  return {
    label: item?.label[th ? 1 : 0] ?? (th ? "การตรวจสอบหลักฐาน" : "Evidence review"),
    source: item?.source[th ? 1 : 0] ?? (th ? "บันทึกหลักฐาน" : "Evidence record"),
    state: ready ? (th ? "พร้อม" : "Ready") : (th ? "ต้องตรวจสอบ" : "Open"),
    reason: ready
      ? (th ? "การตรวจสอบที่จำเป็นเสร็จสมบูรณ์" : "Required checks are complete.")
      : item?.reason[th ? 1 : 0] ?? (th ? "ต้องมีการตรวจสอบเพิ่มเติม" : "Additional validation is required."),
  };
}

function inputRoleLabel(role: string): string {
  if (/pre[_-]?event/i.test(role)) return "Pre-event radar";
  if (/post[_-]?event/i.test(role)) return "Post-event radar";
  if (/reference[_-]?mask/i.test(role)) return "Reference mask";
  if (/holdout/i.test(role)) return "Held-out evaluation area";
  return "Reference input";
}

function referenceStatusLabel(status: string, th: boolean): string {
  if (/qualified|authoritative|accepted/i.test(status)) return th ? "ตรวจสอบแล้ว" : "Validated";
  return th ? "ต้องตรวจสอบโดยอิสระ" : "Independent validation required";
}

function validationStatusLabel(status: string, th: boolean): string {
  if (/complete|evaluated|ready|passed/i.test(status) && !/not[_-]?evaluated/i.test(status)) {
    return th ? "ตรวจสอบแล้ว" : "Reviewed";
  }
  return th ? "รอตรวจสอบ" : "Pending review";
}

function errorCategoryCopy(category: string, th: boolean): { title: string; note: string } {
  const copy: Record<string, { title: [string, string]; note: [string, string] }> = {
    permanent_water: {
      title: ["Permanent water", "แหล่งน้ำถาวร"],
      note: ["Separate permanent-water review required.", "ต้องตรวจสอบแหล่งน้ำถาวรแยกต่างหาก"],
    },
    steep_terrain: {
      title: ["Steep terrain", "พื้นที่ลาดชัน"],
      note: ["Slope and terrain effects require independent review.", "ต้องตรวจสอบผลกระทบจากความลาดชันและภูมิประเทศโดยอิสระ"],
    },
    radar_shadow: {
      title: ["Radar shadow", "เงาเรดาร์"],
      note: ["Radar visibility effects require independent review.", "ต้องตรวจสอบผลกระทบจากการมองเห็นของเรดาร์โดยอิสระ"],
    },
    urban_double_bounce: {
      title: ["Urban signal reflection", "การสะท้อนสัญญาณในเมือง"],
      note: ["Urban reflection effects require independent review.", "ต้องตรวจสอบผลกระทบจากการสะท้อนสัญญาณในเมืองโดยอิสระ"],
    },
  };
  const item = copy[category.toLowerCase()];
  return item
    ? { title: item.title[th ? 1 : 0], note: item.note[th ? 1 : 0] }
    : { title: th ? "หมวดคุณภาพเพิ่มเติม" : "Additional quality category", note: th ? "ต้องมีการตรวจสอบเพิ่มเติม" : "Additional review is required." };
}

export function publicationManifest(run: ModelRun): string {
  const readiness = run.can_feed_decision_layer ? "Ready for acceptance" : "Review held";
  const record = {
    record_type: "FloodGuard model evidence record",
    model: {
      family: familyLabel(run.model_family),
      architecture: architectureLabel(run.architecture),
      channels: run.channel_names,
      model_sha256: run.model_sha256,
    },
    evidence: {
      scope: evidenceScopeLabel(run.dataset_mode, false),
      review_status: runStatusLabel(run.run_status, false),
      source_timestamp: run.source_timestamp,
      confidence: run.confidence_class,
      source: run.dataset_mode === "official_input"
        ? publicationText(run.source_name)
        : "FloodGuard research evaluation record",
      assumptions: run.dataset_mode === "official_input"
        ? run.assumptions.map(publicationText)
        : ["Technical verification and context evidence remain separate from observed-data validation."],
    },
    preprocessing: {
      method: preprocessingLabel(run.preprocessing.method, false),
      transforms: run.preprocessing.transforms.map((transform) => ({
        name: publicationText(transform.name),
        physical_min: transform.physical_min,
        physical_max: transform.physical_max,
        units: transform.units,
      })),
    },
    integrity_records: {
      preprocessing_sha256: run.preprocessing.sidecar_sha256,
      encoded_features_sha256: run.encoded_feature_sha256,
      reference_data_sha256: run.reference_mask_sha256,
      prepared_tiles_sha256: run.prepared_tile_manifest_sha256,
    },
    evaluation: {
      held_out_geography: run.spatial_holdout_ids.map(publicationText),
      metrics: run.validation_metrics,
      quality_categories: run.error_categories.map((category) => errorCategoryCopy(category, false).title),
    },
    operational_readiness: {
      state: readiness,
      note: run.can_feed_decision_layer
        ? "Published data, validation, and governance requirements are complete."
        : "Observed-data validation and governance review must be complete before operational acceptance.",
    },
  };
  return JSON.stringify(record, null, 2);
}

function publicationManifestFileName(run: ModelRun): string {
  const family = familyLabel(run.model_family).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  return `floodguard-${family}-evidence.json`;
}

export function StudioWorkspace() {
  const data = useFloodGuardData();
  const [language, setLanguage] = useLanguage("en");
  const [selectedRunId, setSelectedRunId] = useState(data.model_runs[0]?.run_id ?? "");
  const th = language === "th";
  const selectedRun = data.model_runs.find((run) => run.run_id === selectedRunId) ?? data.model_runs[0];
  const decisionEligible = data.model_runs.some(
    (run) => run.dataset_mode === "official_input" && run.processing_allowed && run.can_feed_decision_layer,
  );
  const hasGeoAiRun = data.model_runs.some((run) => run.model_family === "geoai");
  const blockedGateCount = data.readiness.filter((row) => row.status === "blocked").length;
  const governanceReady = data.pilot_readiness.identity_state === "configured"
    && data.pilot_readiness.audit_state === "valid"
    && data.pilot_readiness.retention_state === "configured";
  const acceptanceReady = data.pilot_readiness.acceptance_receipt_state === "accepted";
  const fieldReviewReady = data.pilot_readiness.acceptance_criteria
    .filter((criterion) => criterion.required)
    .every((criterion) => criterion.status === "accepted");

  return (
    <main className="studio-page studio-final-surface" lang={language}>
      <header className="studio-header studio-final-header">
        <a href="/studio/" className="brand brand-light">
          <Image src="/icon.svg" alt="" width={40} height={40} priority />
          <span><b>FloodGuard</b><small>{th ? "พื้นที่วิจัยและตรวจสอบ" : "Research & validation studio"}</small></span>
        </a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a href="/command/">{th ? "บัญชาการ" : "Command"}</a><a className="active" href="/studio/">Studio</a></nav>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>
      <StatusBar data={data} language={language} compact />

      <div className="studio-shell studio-final-shell">
        <section className={`${styles.consoleHeader} studio-console-hero`} aria-labelledby="research-console-title">
          <div>
            <p className="eyebrow">{th ? "ความเชื่อมั่นจากหลักฐาน" : "Evidence-led assurance"}</p>
            <h1 id="research-console-title">{th ? "สตูดิโอวิจัยและตรวจสอบ" : "Research & validation studio"}</h1>
            <p>{th ? "ตรวจสอบคุณภาพข้อมูล ผลการประเมินโมเดล และความพร้อมใช้งานจากมุมมองเดียว โดยแยกการตรวจสอบระบบออกจากการยืนยันด้วยข้อมูลสังเกตการณ์อย่างชัดเจน" : "Review data quality, model performance, and operational readiness in one workspace, with technical verification clearly separated from observed-data validation."}</p>
            <p className="studio-source-meta">
              <span>{th ? "เวลาข้อมูล" : "Source time"}: <b>{formatSourceTime(data.status.source_timestamp, language)}</b></span>
              <span>{th ? "ความเชื่อมั่น" : "Confidence"}: <b>{formatConfidence(data.status.confidence_class, language)}</b></span>
              <span>{th ? "ใช้ร่วมกับการตรวจสอบของหน่วยงาน" : "Use with agency verification"}</span>
            </p>
          </div>
          <div className={styles.consoleSummary} aria-label={th ? "สรุปสถานะสตูดิโอ" : "Studio status summary"}>
            <div><span>{th ? "การประเมินที่เผยแพร่" : "Published evaluations"}</span><b>{data.model_runs.length}</b></div>
            <div><span>{th ? "รายการที่ต้องตรวจสอบ" : "Open reviews"}</span><b>{blockedGateCount}</b></div>
            <div><span>{th ? "ความพร้อมใช้งาน" : "Operational readiness"}</span><b>{decisionEligible ? (th ? "พร้อมตรวจรับ" : "Ready for acceptance") : (th ? "อยู่ระหว่างตรวจสอบ" : "Review held")}</b></div>
          </div>
        </section>

        <nav className={styles.consoleNav} aria-label={th ? "ส่วนของคอนโซลวิจัย" : "Research console sections"}>
          <a href="#integration-proof">{th ? "การตรวจสอบระบบ" : "Technical verification"}</a>
          <a href="#data-gates">{th ? "ความพร้อมของหลักฐาน" : "Evidence readiness"}</a>
          <a href="#model-matrix">{th ? "เปรียบเทียบโมเดล" : "Model comparison"}</a>
          <a href="#model-card">{th ? "รายละเอียดโมเดล" : "Model details"}</a>
          <a href="#validation">{th ? "การตรวจสอบ" : "Validation"}</a>
          <a href="#pilot-readiness">{th ? "ความพร้อมใช้งาน" : "Operational readiness"}</a>
        </nav>

        <div className={styles.consoleGrid}>
          <aside className={styles.runRail} aria-labelledby="published-runs-title">
            <div><p className="eyebrow">{th ? "รายการประเมิน" : "EVALUATION CATALOG"}</p><h2 id="published-runs-title">{th ? "การประเมินที่เผยแพร่" : "Published evaluations"}</h2></div>
            <div className={styles.runList}>
              {data.model_runs.map((run) => (
                <button
                  type="button"
                  key={run.run_id}
                  className={`${styles.runButton} ${selectedRun?.run_id === run.run_id ? styles.selectedRun : ""}`}
                  aria-pressed={selectedRun?.run_id === run.run_id}
                  onClick={() => setSelectedRunId(run.run_id)}
                >
                  <span>{familyLabel(run.model_family)}</span>
                  <b>{evidenceScopeLabel(run.dataset_mode, th)}</b>
                  <small>{runStatusLabel(run.run_status, th)}</small>
                </button>
              ))}
              {!hasGeoAiRun && (
                <article className={styles.futureRun}>
                  <span>GeoAI U-Net / FPN</span>
                  <b>{th ? "ยังไม่มีการประเมินด้วยข้อมูลสังเกตการณ์" : "Observed-data evaluation unavailable"}</b>
                  <small>{th ? "ยังต้องยืนยันสิทธิ์ข้อมูล ข้อมูลอ้างอิง และชุดประเมินอิสระ" : "Source permissions, reference data, and an independent evaluation set still require verification."}</small>
                </article>
              )}
            </div>
            <p className={styles.railGate}>
              <b>{th ? "สถานะความพร้อม" : "Readiness status"}: {decisionEligible ? (th ? "พร้อมตรวจรับ" : "Ready for acceptance") : (th ? "อยู่ระหว่างตรวจสอบ" : "Review held")}</b><br />
              {decisionEligible
                ? (th ? "มีการประเมินด้วยข้อมูลสังเกตการณ์ที่ผ่านข้อกำหนดด้านหลักฐานทั้งหมด" : "An observed-data evaluation meets every published evidence requirement.")
                : (th ? "ยังไม่มีการประเมินที่ผ่านข้อกำหนดด้านข้อมูล การตรวจสอบ และธรรมาภิบาลครบถ้วน" : "No evaluation currently meets every data, validation, and governance requirement.")}
            </p>
          </aside>

          <div className={styles.consoleMain}>
            <div id="integration-proof">
              <StudioProofPanel language={language} modelRuns={data.model_runs} />
            </div>

            <section id="data-gates" className="studio-section" aria-labelledby="readiness-title">
              <div className="section-heading"><div><p className="eyebrow">{th ? "02 · ความพร้อมของหลักฐาน" : "02 · EVIDENCE READINESS"}</p><h2 id="readiness-title">{th ? "การตรวจสอบคุณภาพข้อมูล" : "Data quality review"}</h2></div><span className="section-count">{blockedGateCount} {th ? "รายการที่ต้องตรวจสอบ" : "open reviews"}</span></div>
              <div className="table-scroll">
                <table className="readiness-table">
                  <thead><tr><th>{th ? "การตรวจสอบ" : "Review"}</th><th>{th ? "แหล่งหลักฐาน" : "Evidence source"}</th><th>{th ? "สถานะ" : "Status"}</th><th>{th ? "รายละเอียด" : "Details"}</th></tr></thead>
                  <tbody>
                    {data.readiness.map((row) => {
                      const copy = readinessCopy(row.check_id, row.status === "ready", th);
                      return <tr key={row.check_id}><td>{copy.label}</td><td>{copy.source}</td><td><span className={`readiness-state ${row.status}`}>{copy.state}</span></td><td>{copy.reason}</td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section id="model-matrix" className="studio-section" aria-labelledby="model-matrix-title">
              <div className="section-heading"><div><p className="eyebrow">{th ? "03 · เปรียบเทียบโมเดล" : "03 · MODEL COMPARISON"}</p><h2 id="model-matrix-title">{th ? "เปรียบเทียบตามขอบเขตหลักฐาน" : "Evidence-scoped comparison"}</h2></div><p>{th ? "ผลจากการตรวจสอบระบบ หลักฐานบริบท และการยืนยันด้วยข้อมูลสังเกตการณ์เป็นคนละระดับหลักฐาน จึงไม่ควรอ่านเป็นตารางจัดอันดับความแม่นยำเดียวกัน" : "Technical verification, context evidence, and observed-data validation represent different evidence levels and should not be read as one accuracy leaderboard."}</p></div>
              <div className="table-scroll">
                <table className="readiness-table">
                  <thead><tr><th>Run</th><th>{th ? "ขอบเขต" : "Scope"}</th><th>IoU</th><th>F1 / Dice</th><th>{th ? "การตัดสินใจ" : "Decision"}</th></tr></thead>
                  <tbody>
                    {data.model_runs.map((run) => (
                      <tr key={run.run_id}>
                        <td><button type="button" className="download-manifest" onClick={() => setSelectedRunId(run.run_id)}>{familyLabel(run.model_family)}</button></td>
                        <td>{evidenceScopeLabel(run.dataset_mode, th)}</td>
                        <td>{formatNumber(run.validation_metrics.iou, language, 3)}</td>
                        <td>{formatNumber(run.validation_metrics.f1_dice, language, 3)}</td>
                        <td><span className={`feed-decision ${run.can_feed_decision_layer ? "yes" : "no"}`}>{run.can_feed_decision_layer ? (th ? "พร้อมตรวจรับ" : "Ready") : (th ? "อยู่ระหว่างตรวจสอบ" : "Review held")}</span></td>
                      </tr>
                    ))}
                    {!hasGeoAiRun && <tr><td>GeoAI U-Net / FPN</td><td>{th ? "ยังไม่มีการประเมินด้วยข้อมูลสังเกตการณ์" : "Observed-data evaluation unavailable"}</td><td>—</td><td>—</td><td><span className="feed-decision no">{th ? "อยู่ระหว่างตรวจสอบ" : "Review held"}</span></td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            {selectedRun && <section id="model-card" className="studio-section model-detail" aria-labelledby="model-card-title">
              <div className="section-heading"><div><p className="eyebrow">{th ? "04 · รายละเอียดโมเดล" : "04 · MODEL DETAILS"}</p><h2 id="model-card-title">{familyLabel(selectedRun.model_family)}</h2><p>{evidenceScopeLabel(selectedRun.dataset_mode, th)} · {runStatusLabel(selectedRun.run_status, th)}</p></div><button type="button" className="download-manifest" onClick={() => downloadText(publicationManifestFileName(selectedRun), publicationManifest(selectedRun), "application/json")}>{th ? "ดาวน์โหลดบันทึกหลักฐาน" : "Download evidence record"}</button></div>
              <div className="model-detail-grid">
                <dl className="contract-list"><div><dt>{th ? "ตระกูลโมเดล" : "Model family"}</dt><dd>{familyLabel(selectedRun.model_family)}</dd></div><div><dt>{th ? "สถาปัตยกรรม" : "Architecture"}</dt><dd>{architectureLabel(selectedRun.architecture)}</dd></div><div><dt>{th ? "ช่องข้อมูล" : "Channels"}</dt><dd>{selectedRun.num_channels ?? "—"} · {selectedRun.channel_names.join(", ")}</dd></div><div><dt>{th ? "การเตรียมข้อมูล" : "Preprocessing"}</dt><dd>{preprocessingLabel(selectedRun.preprocessing.method, th)}</dd></div><div><dt>{th ? "การแปลงข้อมูล" : "Band transforms"}</dt><dd>{selectedRun.preprocessing.transforms.length > 0 ? selectedRun.preprocessing.transforms.map((item) => `${publicationText(item.name)}: ${item.physical_min}…${item.physical_max} ${item.units}`).join("; ") : (th ? "ยังไม่เผยแพร่สำหรับการประเมินนี้" : "Not published for this evaluation")}</dd></div><div><dt>{th ? "บันทึกการแปลง" : "Transform record"}</dt><dd>{selectedRun.preprocessing.sidecar_sha256 ?? (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "ข้อมูลนำเข้า" : "Input coverage"}</dt><dd>{Array.from(new Set(selectedRun.input_manifest_rows.map((row) => inputRoleLabel(row.role)))).join(", ")}</dd></div><div><dt>{th ? "บันทึกคุณลักษณะ" : "Feature record"}</dt><dd>{selectedRun.encoded_feature_sha256 ?? (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "ข้อมูลอ้างอิง" : "Reference data"}</dt><dd>{referenceStatusLabel(selectedRun.reference_mask_status, th)}</dd></div><div><dt>{th ? "บันทึกข้อมูลอ้างอิง" : "Reference record"}</dt><dd>{selectedRun.reference_mask_sha256 ?? (th ? "ไม่มีข้อมูล" : "Unavailable")}</dd></div><div><dt>{th ? "บันทึกชุดข้อมูล" : "Data record"}</dt><dd>{selectedRun.prepared_tile_manifest_sha256 ?? (th ? "ยังไม่จัดเตรียม" : "Not prepared")}</dd></div><div><dt>{th ? "พื้นที่ประเมินอิสระ" : "Held-out geography"}</dt><dd>{selectedRun.spatial_holdout_ids.length > 0 ? selectedRun.spatial_holdout_ids.map(publicationText).join(", ") : (th ? "ยังไม่ระบุ" : "Not declared")}</dd></div><div><dt>{th ? "การแบ่งพื้นที่" : "Spatial partitions"}</dt><dd>{selectedRun.spatial_partitions.length > 0 ? selectedRun.spatial_partitions.map((item) => `${publicationText(item.spatial_group_id)} (${item.split})`).join(", ") : (th ? "ยังไม่เผยแพร่" : "Not published")}</dd></div><div><dt>{th ? "ขอบเขตการเข้าถึง" : "Evidence access"}</dt><dd>{th ? "บันทึกสำหรับการตรวจสอบ" : "Publication record"}</dd></div></dl>
                <div className="metric-panel"><h3>{th ? "เมตริกตามขอบเขตหลักฐาน" : "Evidence-scoped metrics"}</h3>{METRICS.map(([key, label]) => <div className="metric-row" key={key}><span>{label}</span><b>{formatNumber(selectedRun.validation_metrics[key], language, 3)}</b></div>)}<article className={selectedRun.can_feed_decision_layer ? "eligible-reason" : "blocked-reason"}><b>{th ? "ความพร้อมใช้งาน" : "Operational readiness"}</b><p>{selectedRun.can_feed_decision_layer ? (th ? "การประเมินนี้ผ่านข้อกำหนดด้านข้อมูล การตรวจสอบ และธรรมาภิบาลที่เผยแพร่ทั้งหมด" : "This evaluation meets every published data, validation, and governance requirement.") : (th ? "การใช้งานยังอยู่ระหว่างตรวจสอบจนกว่าการยืนยันด้วยข้อมูลสังเกตการณ์และธรรมาภิบาลจะเสร็จสมบูรณ์" : "Operational review remains held until observed-data validation and governance requirements are complete.")}</p></article></div>
              </div>
            </section>}

            <section id="validation" className="studio-section" aria-labelledby="errors-title">
              <div className="section-heading"><div><p className="eyebrow">{th ? "05 · การตรวจสอบ" : "05 · VALIDATION"}</p><h2 id="errors-title">{th ? "หมวดการตรวจสอบคุณภาพ" : "Quality review categories"}</h2></div></div>
              <div className="error-grid">{data.error_categories.map((item) => {
                const copy = errorCategoryCopy(item.category, th);
                return <article key={item.category}><span>{validationStatusLabel(item.status, th)}</span><h3>{copy.title}</h3><p>{copy.note}</p></article>;
              })}</div>
            </section>

            <section id="pilot-readiness" className="studio-section studio-operational-readiness" aria-labelledby="operational-readiness-title">
              <div className="section-heading">
                <div><p className="eyebrow">{th ? "06 · ความพร้อมใช้งาน" : "06 · OPERATIONAL READINESS"}</p><h2 id="operational-readiness-title">{th ? "การตรวจรับและธรรมาภิบาล" : "Acceptance & governance"}</h2></div>
                <span className={`feed-decision ${data.pilot_readiness.agency_operational_allowed ? "yes" : "no"}`}>{data.pilot_readiness.agency_operational_allowed ? (th ? "พร้อมตรวจรับ" : "Ready for acceptance") : (th ? "อยู่ระหว่างตรวจสอบ" : "Review held")}</span>
              </div>
              <div className="model-detail-grid">
                <dl className="contract-list">
                  <div><dt>{th ? "ธรรมาภิบาล" : "Governance record"}</dt><dd>{governanceReady ? (th ? "ตรวจสอบแล้ว" : "Verified") : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")}</dd></div>
                  <div><dt>{th ? "การตรวจรับของหน่วยงาน" : "Agency acceptance"}</dt><dd>{acceptanceReady ? (th ? "ได้รับการรับรอง" : "Accepted") : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")}</dd></div>
                  <div><dt>{th ? "การตรวจสอบภาคสนาม" : "Field validation"}</dt><dd>{fieldReviewReady ? (th ? "ตรวจสอบแล้ว" : "Verified") : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")}</dd></div>
                  <div><dt>{th ? "ความโปร่งใสของข้อมูล" : "Data transparency"}</dt><dd>{th ? "แสดงเวลา แหล่งที่มา ความเชื่อมั่น และสมมติฐาน" : "Source time, provenance, confidence, and assumptions retained"}</dd></div>
                </dl>
                <article className={data.pilot_readiness.agency_operational_allowed ? "eligible-reason" : "blocked-reason"}>
                  <b>{th ? "สถานะปัจจุบัน" : "Current position"}</b>
                  <p>{data.pilot_readiness.agency_operational_allowed
                    ? (th ? "การตรวจรับของหน่วยงานและข้อกำหนดการตรวจสอบครบถ้วนแล้ว" : "Agency acceptance and validation requirements are complete.")
                    : (th ? "ผลการวิจัยใช้เพื่อสนับสนุนการทบทวนเท่านั้น จนกว่าการตรวจรับของหน่วยงานและหลักฐานภาคสนามจะเสร็จสมบูรณ์" : "Research findings support review only until agency acceptance and field evidence are complete.")}</p>
                </article>
              </div>
            </section>
          </div>
        </div>

        <footer className="studio-footer"><p>{th ? "บันทึกหลักฐานที่เผยแพร่คงข้อมูลแหล่งที่มา สถานะการตรวจสอบ ความเชื่อมั่น และขอบเขตการทบทวน" : "Published evidence records retain provenance, validation status, confidence, and review boundaries."}</p><a href="/command/">{th ? "เปิดศูนย์บัญชาการวางแผน →" : "Open planning command center →"}</a></footer>
      </div>
    </main>
  );
}
