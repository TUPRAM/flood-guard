"use client";

import { useState } from "react";

import type { EvidenceContext, ModelEvaluationV2 } from "@floodguard/contracts";

import type {
  Language,
  ModelEvidenceState,
  StudioFloodObservationProductRecord,
  StudioModelEvaluationRecord,
  StudioModelRegistryEntry,
} from "@/lib/types";

import styles from "./model-registry-panel.module.css";

export interface ModelRegistryPanelProps {
  context: EvidenceContext;
  entries: StudioModelRegistryEntry[];
  evaluations: StudioModelEvaluationRecord[];
  products: StudioFloodObservationProductRecord[];
  evidenceState: ModelEvidenceState;
  evidenceReason: string;
  language: Language;
}

export function ModelRegistryPanel({
  context,
  entries,
  evaluations,
  products,
  evidenceState,
  evidenceReason,
  language,
}: ModelRegistryPanelProps) {
  const th = language === "th";
  const [selectedEntryId, setSelectedEntryId] = useState(
    entries[0]?.payload.registry_entry_id ?? "",
  );
  const selectedEnvelope =
    entries.find(
      (entry) => entry.payload.registry_entry_id === selectedEntryId,
    ) ?? entries[0];
  const selected = selectedEnvelope?.payload;
  const evaluation = selected
    ? evaluations.find((item) => item.evaluation_id === selected.evaluation_id)
    : undefined;
  const product = selected
    ? products.find((item) => item.product_id === selected.product_id)
    : undefined;
  const bound = Boolean(selected && context.model_run_id === selected.model_run_id);
  const unavailable =
    evidenceState === "unavailable" || !selected || !evaluation || !product;
  const syntheticProof =
    evaluation?.reference_evidence.reference_mask_status ===
    "synthetic_fixture_only";

  return (
    <section className={styles.panel} aria-labelledby="model-registry-title">
      <div className={styles.heading}>
        <div>
          <p className="eyebrow">
            04 · {th ? "ทะเบียนโมเดล" : "MODEL REGISTRY"}
          </p>
          <h2 id="model-registry-title">
            {th
              ? "ทะเบียนโมเดลและผลการประเมิน"
              : "Model registry & evaluation"}
          </h2>
        </div>
        <span className={`${styles.status} ${styles[evidenceState]}`}>
          {stateLabel(evidenceState, th)}
        </span>
      </div>

      <div className={styles.boundary} role="status">
        <b>
          {bound
            ? th
              ? "โมเดลนี้ผูกกับบริบทหลักฐานที่กำลังใช้งาน"
              : "This model is bound to the active evidence context"
            : th
              ? "ไม่มีผลการประเมินโมเดลที่ผูกกับบริบทหลักฐานนี้"
              : "No model evaluation is bound to this evidence context"}
        </b>
        <p>
          {bound
            ? th
              ? "การผูกกับบริบทไม่ใช่การอนุญาตเชิงปฏิบัติการ การเลื่อนสถานะและการยอมรับจากหน่วยงานยังเป็นเงื่อนไขแยกต่างหาก"
              : "Context binding is not operational authorization. Promotion and agency acceptance remain separate decisions."
            : th
              ? "บันทึกนี้ใช้ตรวจสอบทางเทคนิคเท่านั้น FloodGuard จะไม่แทนที่ผลประเมินหรือการอนุมัติด้วยข้อมูลจากพื้นที่ เหตุการณ์ รุ่นข้อมูล โมเดล หรือการประเมินอื่น"
              : "This record is available for technical inspection only. FloodGuard will not substitute metrics or approval from another study area, event, data version, model, or evaluation."}
        </p>
      </div>

      {unavailable ? (
        <article className={styles.unavailable} aria-live="polite">
          <b>
            {th
              ? "หลักฐานโมเดลไม่พร้อมสำหรับแพ็กเกจนี้"
              : "Model evidence is unavailable for this package."}
          </b>
          <p>
            {evidenceReason ||
              (th
                ? "ทะเบียน โมเดล การประเมิน หรือสายข้อมูลต้นทางไม่ตรงกับบริบทหลักฐานที่กำลังใช้งาน"
                : "The registry, model, evaluation, or source lineage does not exactly match the active evidence context.")}
          </p>
        </article>
      ) : (
        <>
          <div
            className={styles.summary}
            aria-label={
              th ? "สรุปสถานะหลักฐานโมเดล" : "Model evidence status summary"
            }
          >
            <SummaryItem
              label={th ? "ทะเบียน" : "Registry"}
              value={selected.registry_status}
              blocked={selected.registry_status !== "approved"}
            />
            <SummaryItem
              label={th ? "การประเมิน" : "Evaluation"}
              value={
                evaluation.evaluation_scope === "not_evaluated"
                  ? th
                    ? "ยังไม่ประเมินเหตุการณ์จริง"
                    : "No real-event evaluation"
                  : evaluation.evaluation_status
              }
              blocked={evaluation.evaluation_scope !== "final_holdout"}
            />
            <SummaryItem
              label={th ? "การใช้งานที่อนุญาต" : "Permitted use"}
              value={selected.permitted_use}
              blocked={selected.permitted_use !== "decision_input"}
            />
            <SummaryItem
              label={th ? "สิทธิ์เข้าชั้นตัดสินใจ" : "Decision input"}
              value={
                selected.can_feed_decision_layer
                  ? th
                    ? "อนุญาต"
                    : "Eligible"
                  : th
                    ? "ถูกบล็อก"
                    : "Blocked"
              }
              blocked={!selected.can_feed_decision_layer}
            />
          </div>

          <article className={styles.warning}>
            <b>
              {th
                ? "บันทึกโมเดลผู้สมัครที่ถูกจำกัด"
                : "Restricted candidate model record"}
            </b>
            <p>
              {th
                ? syntheticProof
                  ? "นี่เป็นเพียงหลักฐานการเชื่อมต่อซอฟต์แวร์แบบสังเคราะห์ ไม่ใช่การตรวจสอบความแม่นยำจากเหตุการณ์จริง ไม่มีสิทธิ์เข้าสู่ FPPS หรือชั้นการตัดสินใจ และไม่ใช่คำเตือนภัยอย่างเป็นทางการ"
                  : "นี่เป็นเพียงข้อกำหนดการทดลองที่ถูกบล็อก ยังไม่ยืนยันว่าโมเดลทำงานหรือมีความแม่นยำ ไม่มีสิทธิ์เข้าสู่ FPPS หรือชั้นการตัดสินใจ และไม่ใช่คำเตือนภัยอย่างเป็นทางการ"
                : syntheticProof
                  ? "This is synthetic software-path evidence only. It is not observed-event accuracy validation, is not eligible for FPPS or the decision layer, and is not an official warning."
                  : "This is a blocked experiment specification. It does not show that the model ran or establish accuracy, is not eligible for FPPS or the decision layer, and is not an official warning."}
            </p>
          </article>

          <article className={styles.cryptoBoundary}>
            <b>
              {th
                ? "สถานะการตรวจสอบเชิงเข้ารหัสในเบราว์เซอร์: ไม่ได้ตรวจสอบ"
                : "Browser cryptographic status: not verified"}
            </b>
            <p>
              {th
                ? "หน้าจอนี้ตรวจเฉพาะโครงสร้างที่จำเป็นและการเชื่อมโยงรหัสกับแฮชข้ามระเบียนเท่านั้น เบราว์เซอร์ไม่ได้คำนวณซ้ำหรือยืนยันแฮชของ payload, evaluation หรือ product และไม่ได้ตรวจสอบ HMAC ให้ถือ API และ repository เป็นผู้มีอำนาจสำหรับการตรวจสอบเชิงเข้ารหัส"
                : "This screen checks required shape and cross-record ID/hash lineage only. The browser does not recompute or authenticate the payload, evaluation, or product digests and does not verify the HMAC. The API and repository are the authority for cryptographic verification."}
            </p>
          </article>

          <div className={styles.layout}>
            <nav
              className={styles.registryList}
              aria-label={th ? "เลือกรายการโมเดล" : "Select a model record"}
            >
              {entries.map((entry) => (
                <button
                  type="button"
                  key={entry.payload.registry_entry_id}
                  aria-pressed={
                    entry.payload.registry_entry_id ===
                    selected.registry_entry_id
                  }
                  onClick={() =>
                    setSelectedEntryId(entry.payload.registry_entry_id)
                  }
                >
                  <span>{evidenceKindLabel(entry.payload.evidence_kind, th)}</span>
                  <b>{entry.payload.model_id}</b>
                  <small>
                    {entry.payload.registry_status} ·{" "}
                    {entry.payload.model_run_id}
                  </small>
                </button>
              ))}
            </nav>

            <div
              className={styles.detail}
              id="model-registry-detail"
              aria-live="polite"
            >
              <section aria-labelledby="model-identity-title">
                <div className={styles.sectionHeading}>
                  <div>
                    <p className="eyebrow">
                      {th ? "ข้อมูลประจำตัว" : "IDENTITY"}
                    </p>
                    <h3 id="model-identity-title">{selected.model_id}</h3>
                  </div>
                  <span className={styles.blockedPill}>
                    {th ? "รายงานเท่านั้น" : "Report only"}
                  </span>
                </div>
                <dl className={styles.identityGrid}>
                  <Detail
                    label={th ? "สถานะเชิงปฏิบัติการ" : "Operational status"}
                    value={selected.operational_status}
                  />
                  <Detail
                    label={th ? "ประเภทข้อมูล" : "Dataset mode"}
                    value={selected.dataset_mode}
                  />
                  <Detail label="run_id" value={selected.model_run_id} code />
                  <Detail
                    label="model_sha256"
                    value={shortDigest(selected.model_sha256)}
                    code
                    title={selected.model_sha256}
                  />
                  <Detail
                    label={th ? "เหตุการณ์" : "Event"}
                    value={selected.event_id}
                    code
                  />
                  <Detail
                    label={th ? "หมดอายุ" : "Expires"}
                    value={formatDate(selected.expires_at, language)}
                  />
                  <Detail
                    label={
                      th
                        ? "ป้ายคีย์ผู้ลงนามที่ระบุ"
                        : "Declared signer key label"
                    }
                    value={selectedEnvelope.signature.key_id}
                    code
                  />
                  <Detail
                    label="declared payload_sha256"
                    value={shortDigest(selectedEnvelope.signature.payload_sha256)}
                    code
                    title={selectedEnvelope.signature.payload_sha256}
                  />
                </dl>
              </section>

              <section aria-labelledby="evaluation-detail-title">
                <div className={styles.sectionHeading}>
                  <div>
                    <p className="eyebrow">
                      {th ? "ขอบเขตการประเมิน" : "EVALUATION SCOPE"}
                    </p>
                    <h3 id="evaluation-detail-title">
                      {evaluation.evaluation_id}
                    </h3>
                  </div>
                </div>
                <p className={styles.scopeStatement}>
                  {evaluation.evaluation_scope === "not_evaluated"
                    ? syntheticProof
                      ? th
                        ? "การทดสอบสังเคราะห์ยืนยันเฉพาะโครงสร้างและเส้นทางซอฟต์แวร์เท่านั้น ยังไม่มีผลจากชุดทดสอบเหตุการณ์จริงที่ผ่านเกณฑ์"
                        : "Synthetic testing confirms contract shape and the software path only. No qualified real-event holdout result is recorded."
                      : th
                        ? "ยังไม่มีการดำเนินการประเมินที่ควบคุม ไม่มีผลจากชุดทดสอบเหตุการณ์จริง และค่าตัวชี้วัดทั้งหมดคงเป็นไม่ทราบค่า"
                        : "No controlled evaluation was executed. No qualified real-event holdout result exists, and every accuracy metric remains unknown."
                    : th
                      ? "มีบันทึกขอบเขตชุดทดสอบสุดท้าย แต่ยังต้องตรวจสอบสถานะการเลื่อนขั้นและการยอมรับแยกต่างหาก"
                      : "A final-holdout scope is recorded, but promotion and acceptance must still be verified separately."}
                </p>
                <dl className={styles.metrics}>
                  {evaluationMetrics(evaluation).map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{metricValue(value, language)}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              <section aria-labelledby="product-detail-title">
                <div className={styles.sectionHeading}>
                  <div>
                    <p className="eyebrow">
                      {th ? "ผลิตภัณฑ์หลักฐาน" : "EVIDENCE PRODUCT"}
                    </p>
                    <h3 id="product-detail-title">{product.product_id}</h3>
                  </div>
                </div>
                <dl className={styles.identityGrid}>
                  <Detail
                    label={th ? "ชนิดหลักฐาน" : "Evidence kind"}
                    value={evidenceKindLabel(product.evidence_kind, th)}
                  />
                  <Detail
                    label={th ? "คุณภาพเซนเซอร์" : "Sensor quality"}
                    value={product.sensor_quality_status}
                  />
                  <Detail
                    label={th ? "พื้นที่ข้อมูลที่ใช้ได้" : "Valid coverage"}
                    value={formatPercent(product.valid_coverage_fraction, language)}
                  />
                  <Detail
                    label={th ? "พื้นที่ที่งดคาดการณ์" : "Abstained"}
                    value={formatPercent(product.abstained_fraction, language)}
                  />
                  <Detail
                    label={th ? "นโยบายเซลล์ที่ไม่ทราบค่า" : "Unknown-cell policy"}
                    value={
                      th
                        ? "คงเป็นไม่ทราบค่า ไม่ถือว่าเป็นพื้นที่แห้ง"
                        : "Remain unknown; never treated as dry"
                    }
                  />
                  <Detail
                    label={th ? "ไฟล์หลักฐาน" : "Evidence assets"}
                    value={`${product.assets.length}`}
                  />
                  <Detail
                    label="evaluation_sha256"
                    value={shortDigest(product.evaluation_manifest_sha256)}
                    code
                    title={product.evaluation_manifest_sha256}
                  />
                  <Detail
                    label="product_sha256"
                    value={shortDigest(selected.product_manifest_sha256)}
                    code
                    title={selected.product_manifest_sha256}
                  />
                </dl>
              </section>

              <article className={styles.blocker}>
                <b>{th ? "เหตุผลที่ถูกบล็อก" : "Why this record is blocked"}</b>
                <p>{selected.reason_blocked}</p>
              </article>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function SummaryItem({
  label,
  value,
  blocked,
}: {
  label: string;
  value: string;
  blocked: boolean;
}) {
  return (
    <div className={blocked ? styles.summaryBlocked : styles.summaryReady}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}

function Detail({
  label,
  value,
  code = false,
  title,
}: {
  label: string;
  value: string;
  code?: boolean;
  title?: string;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd title={title}>{code ? <code>{value}</code> : value}</dd>
    </div>
  );
}

function stateLabel(state: ModelEvidenceState, th: boolean): string {
  if (state === "ready") return th ? "พร้อมตรวจสอบ" : "Available for review";
  if (state === "blocked") return th ? "ถูกบล็อก" : "Blocked";
  return th ? "ไม่พร้อมใช้งาน" : "Unavailable";
}

function evidenceKindLabel(
  value: StudioFloodObservationProductRecord["evidence_kind"],
  th: boolean,
): string {
  if (value === "satellite_observed_extent") {
    return th ? "ขอบเขตน้ำท่วมจากดาวเทียม" : "Satellite-observed extent";
  }
  if (value === "optical_corroboration") {
    return th ? "หลักฐานยืนยันจากภาพเชิงแสง" : "Optical corroboration";
  }
  if (value === "susceptibility_forecast") {
    return th ? "การคาดการณ์ความไวต่อน้ำท่วม" : "Susceptibility forecast";
  }
  if (value === "scenario_assumption") {
    return th ? "สมมติฐานสถานการณ์" : "Scenario assumption";
  }
  if (value === "human_field_observation") {
    return th ? "การสังเกตการณ์ภาคสนาม" : "Human field observation";
  }
  return th
    ? "ค่าฐานจากอัลกอริทึมภายนอก"
    : "External algorithmic baseline";
}

function evaluationMetrics(
  evaluation: ModelEvaluationV2,
): Array<[string, number | null]> {
  return [
    ["IoU", evaluation.overall_metrics.iou],
    ["F1 / Dice", evaluation.overall_metrics.f1_dice],
    ["Precision", evaluation.overall_metrics.precision],
    ["Recall", evaluation.overall_metrics.recall],
    ["Boundary F1", evaluation.overall_metrics.boundary_f1],
    ["Absolute area error", evaluation.overall_metrics.absolute_area_error_ratio],
    ["Brier score", evaluation.overall_metrics.brier_score],
    ["Calibration ECE", evaluation.overall_metrics.expected_calibration_error],
    ["Downstream FPPS MAE", evaluation.downstream_impact.fpps_mean_absolute_error],
    ["Action-class flips", evaluation.downstream_impact.action_class_flip_count],
  ];
}

function metricValue(value: number | null, language: Language): string {
  if (value === null) {
    return language === "th" ? "ยังไม่ประเมิน" : "Not evaluated";
  }
  return new Intl.NumberFormat(language === "th" ? "th-TH" : "en-US", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(value);
}

function formatPercent(value: number, language: Language): string {
  return new Intl.NumberFormat(language === "th" ? "th-TH" : "en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function shortDigest(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-10)}`;
}

function formatDate(value: string, language: Language): string {
  return new Intl.DateTimeFormat(language === "th" ? "th-TH" : "en-US", {
    dateStyle: "medium",
    timeZone: "Asia/Bangkok",
  }).format(new Date(value));
}
