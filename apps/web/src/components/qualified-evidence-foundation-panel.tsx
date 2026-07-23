"use client";

import { useEffect, useState } from "react";

import { formatSourceTime } from "@/lib/format";
import {
  canonicalJson,
  parseQualifiedEvidenceFoundation,
  verifyQualifiedEvidenceFoundationHash,
} from "@/lib/qualified-evidence-foundation";
import type {
  Language,
  QualifiedEvidenceFoundation,
} from "@/lib/types";

import styles from "./qualified-evidence-foundation-panel.module.css";

type IntegrityState = "checking" | "verified" | "invalid" | "unavailable";

export interface QualifiedEvidenceFoundationPanelProps {
  foundation?: QualifiedEvidenceFoundation;
  language: Language;
}

export function QualifiedEvidenceFoundationPanel({
  foundation,
  language,
}: QualifiedEvidenceFoundationPanelProps) {
  const parsed = parseQualifiedEvidenceFoundation(foundation);
  const record = parsed.value;
  const payloadIdentity = record ? canonicalJson(record) : null;
  const [verification, setVerification] = useState<{
    payloadIdentity: string;
    state: Exclude<IntegrityState, "checking">;
  } | null>(null);
  const th = language === "th";

  useEffect(() => {
    let active = true;
    if (!record || payloadIdentity === null) {
      return () => {
        active = false;
      };
    }

    void verifyQualifiedEvidenceFoundationHash(record)
      .then((matches) => {
        if (active) {
          setVerification({
            payloadIdentity,
            state: matches ? "verified" : "invalid",
          });
        }
      })
      .catch(() => {
        if (active) {
          setVerification({
            payloadIdentity,
            state: "unavailable",
          });
        }
      });
    return () => {
      active = false;
    };
  }, [payloadIdentity, record]);

  if (!record) {
    return (
      <section
        className={styles.unavailable}
        aria-labelledby="qualified-evidence-foundation-title"
        role="status"
      >
        <p className="eyebrow">P0 · EVIDENCE FOUNDATION</p>
        <h2 id="qualified-evidence-foundation-title">
          {th
            ? "ไม่สามารถอ่านสถานะข้อมูลอ้างอิงและชุดป้ายกำกับได้"
            : "Qualified-reference status is unavailable"}
        </h2>
        <p>
          {th
            ? "ข้อมูล Studio ไม่ผ่านสัญญาโครงสร้าง จึงไม่แสดงสถานะทดแทนและยังคงปิดการทดลอง"
            : "The Studio payload failed its structure contract. No substitute status is shown, and experiment processing remains blocked."}
        </p>
      </section>
    );
  }

  const integrityState: IntegrityState =
    verification?.payloadIdentity === payloadIdentity
      ? verification.state
      : "checking";
  const integrityCopy = {
    checking: th
      ? "กำลังตรวจสอบ checksum ในเบราว์เซอร์"
      : "Checking checksum in this browser",
    verified: th
      ? "checksum ตรงกับข้อมูลสถานะแบบมาตรฐาน"
      : "Checksum matches the canonical status payload",
    invalid: th
      ? "checksum ไม่ตรง — ห้ามเชื่อถือข้อมูลสถานะนี้"
      : "Checksum mismatch — do not trust this status payload",
    unavailable: th
      ? "เบราว์เซอร์นี้ตรวจสอบ checksum ไม่ได้"
      : "This browser cannot verify the checksum",
  }[integrityState];
  const integrityClass =
    integrityState === "unavailable"
      ? styles.integrityUnavailable
      : styles[integrityState];

  if (integrityState !== "verified") {
    const title = {
      checking: th
        ? "กำลังตรวจสอบความถูกต้องของสถานะข้อมูลอ้างอิง"
        : "Qualified-reference status verification is pending",
      invalid: th
        ? "สถานะข้อมูลอ้างอิงไม่ผ่านการตรวจสอบความถูกต้อง"
        : "Qualified-reference status failed integrity verification",
      unavailable: th
        ? "ไม่สามารถตรวจสอบความถูกต้องของสถานะข้อมูลอ้างอิงได้"
        : "Qualified-reference status integrity is unavailable",
      verified: "",
    }[integrityState];
    const detail = {
      checking: th
        ? "ระบบจะไม่แสดงรายละเอียดหลักฐานจนกว่า checksum SHA-256 จะผ่านการตรวจสอบในเบราว์เซอร์ การประมวลผลการทดลองยังคงถูกปิดกั้น"
        : "Evidence details are withheld until browser SHA-256 verification succeeds. Experiment processing remains blocked.",
      invalid: th
        ? "checksum SHA-256 ไม่ตรงกัน จึงไม่แสดงรายละเอียดใดจากข้อมูลนี้ และการประมวลผลการทดลองยังคงถูกปิดกั้น"
        : "The SHA-256 checksum did not match. No evidence details from this payload are displayed, and experiment processing remains blocked.",
      unavailable: th
        ? "เบราว์เซอร์ไม่สามารถตรวจสอบ checksum SHA-256 ได้ จึงไม่แสดงรายละเอียดใดจากข้อมูลนี้ และการประมวลผลการทดลองยังคงถูกปิดกั้น"
        : "This browser cannot verify SHA-256. No evidence details from this payload are displayed, and experiment processing remains blocked.",
      verified: "",
    }[integrityState];

    return (
      <section
        className={styles.unavailable}
        aria-labelledby="qualified-evidence-foundation-title"
        role={integrityState === "invalid" ? "alert" : "status"}
        aria-live="polite"
      >
        <p className="eyebrow">P0 · EVIDENCE FOUNDATION</p>
        <h2 id="qualified-evidence-foundation-title">{title}</h2>
        <div className={`${styles.integrity} ${integrityClass}`}>
          <b>{th ? "ความสมบูรณ์ของข้อมูล Studio" : "Studio payload integrity"}</b>
          <span>{integrityCopy}</span>
        </div>
        <p>{detail}</p>
      </section>
    );
  }

  return (
    <section
      className={styles.panel}
      aria-labelledby="qualified-evidence-foundation-title"
    >
      <header className={styles.heading}>
        <div>
          <p className="eyebrow">P0 · EVIDENCE FOUNDATION</p>
          <h2 id="qualified-evidence-foundation-title">
            {th
              ? "ข้อมูลอ้างอิงเหตุการณ์ไทยที่ผ่านเกณฑ์และชุดป้ายกำกับฉบับตรึง v1"
              : "Qualified Thai Reference & Frozen Label Release v1"}
          </h2>
          <p>
            {th
              ? "ภาพรวมแบบอ่านอย่างเดียวของสิ่งที่ระบบสร้างเสร็จแล้วและหลักฐานภายนอกที่ยังขาดอยู่"
              : "A read-only view of the engineering foundation already in place and the external evidence that is still missing."}
          </p>
        </div>
        <span className={`${styles.status} ${styles.blocked}`}>
          {th ? "ถูกบล็อก" : "BLOCKED"}
        </span>
      </header>

      <div
        className={`${styles.integrity} ${integrityClass}`}
        role="status"
        aria-live="polite"
      >
        <b>{th ? "ความสมบูรณ์ของข้อมูล Studio" : "Studio payload integrity"}</b>
        <span>{integrityCopy}</span>
      </div>

      <article className={styles.boundary}>
        <b>
          {th
            ? "ข้อมูลนี้ไม่ใช่ใบรับรองหรือการอนุมัติ"
            : "This is not an approval or release receipt"}
        </b>
        <p>
          {th
            ? "authoritative_receipt=false · ใช้เพื่ออธิบายสถานะเท่านั้น การฝึก การประเมิน FPPS ชั้นการตัดสินใจ และการใช้งานจริงยังไม่ได้รับอนุญาต"
            : "authoritative_receipt=false · This projection explains recorded status only. Training, evaluation, FPPS, the decision layer, and operational use remain unauthorized."}
        </p>
      </article>

      <article
        className={styles.candidateBinding}
        aria-labelledby="p0-candidate-binding-title"
      >
        <div>
          <p className="eyebrow">
            {th ? "การผูกหลักฐานผู้สมัคร" : "CANDIDATE EVIDENCE BINDING"}
          </p>
          <h3 id="p0-candidate-binding-title">
            {record.reference_candidate_binding.product_id}
          </h3>
          <p>
            {th
              ? "ข้อมูลเหตุการณ์จริงที่อยู่ในพื้นที่ แต่ยังไม่ใช่ข้อมูลอ้างอิงที่ผ่านเกณฑ์"
              : "Real in-area event evidence, still not a qualified reference."}
          </p>
        </div>
        <dl>
          <div>
            <dt>{th ? "ผู้ให้ข้อมูล" : "Provider"}</dt>
            <dd>{record.reference_candidate_binding.provider}</dd>
          </div>
          <div>
            <dt>{th ? "เวลาสังเกตเริ่มต้น" : "Observation starts"}</dt>
            <dd>
              {formatSourceTime(
                record.reference_candidate_binding.observation_start_utc,
                language,
              )}
            </dd>
          </div>
          <div>
            <dt>{th ? "Checksum ของ manifest" : "Manifest checksum"}</dt>
            <dd>
              <code>
                {record.reference_candidate_binding.manifest_canonical_sha256}
              </code>
            </dd>
          </div>
          <div>
            <dt>{th ? "Checksum ของ archive ต้นทาง" : "Source archive checksum"}</dt>
            <dd>
              <code>
                {record.reference_candidate_binding.source_archive_sha256}
              </code>
            </dd>
          </div>
          <div>
            <dt>{th ? "อำนาจการประมวลผล" : "Processing authority"}</dt>
            <dd>
              <code>processing_allowed=false</code>
            </dd>
          </div>
        </dl>
      </article>

      <div
        className={styles.permissionGrid}
        aria-label={th ? "ขอบเขตการประมวลผล" : "Processing scopes"}
      >
        <article className={styles.allowedScope}>
          <span>{th ? "การประมวลผลแหล่งข้อมูล" : "Source processing"}</span>
          <b>processing_allowed=true</b>
          <p>
            {th
              ? record.permissions.source_processing_scope_th
              : record.permissions.source_processing_scope_en}
          </p>
        </article>
        <article className={styles.blockedScope}>
          <span>
            {th ? "การประมวลผลการทดลอง" : "Experiment processing"}
          </span>
          <b>processing_allowed=false</b>
          <p>
            {th
              ? "ยังไม่มีข้อมูลอ้างอิงไทยที่ผ่านเกณฑ์ การปรับเทียบผู้ทบทวน หรือชุดป้ายกำกับฉบับตรึง"
              : "Qualified Thai reference, reviewer calibration, and a frozen label release are still missing."}
          </p>
        </article>
      </div>

      <div className={styles.sectionHeading}>
        <div>
          <p className="eyebrow">
            {th ? "ลำดับหลักฐาน" : "EVIDENCE SEQUENCE"}
          </p>
          <h3>{th ? "ห้าด่านของรุ่น v1" : "Five v1 stages"}</h3>
        </div>
        <p>
          {th
            ? "คำว่า พร้อม หมายถึงเครื่องมือวิศวกรรมพร้อมเท่านั้น ไม่ใช่การรับรองข้อมูล"
            : "Ready means the engineering mechanism exists; it does not confer evidence authority."}
        </p>
      </div>

      <ol className={styles.timeline}>
        {record.stages.map((stage) => (
          <li className={styles.timelineItem} key={stage.stage_id}>
            <div className={styles.timelineTopline}>
              <b>{th ? stage.label_th : stage.label_en}</b>
              <span className={`${styles.status} ${styles[stage.state]}`}>
                {th
                  ? stage.state === "ready"
                    ? "พร้อม"
                    : stage.state === "blocked"
                      ? "ถูกบล็อก"
                      : "ยังไม่มี"
                  : stage.state.toUpperCase()}
              </span>
            </div>
            <p>{th ? stage.detail_th : stage.detail_en}</p>
          </li>
        ))}
      </ol>

      <div className={styles.detailsGrid}>
        <section aria-labelledby="p0-blockers-title">
          <h3 id="p0-blockers-title">
            {th ? "ตัวบล็อกที่บันทึกไว้" : "Recorded blockers"}
          </h3>
          <ul>
            {record.blockers.map((blocker) => (
              <li key={blocker.code}>
                {th ? blocker.detail_th : blocker.detail_en}
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="p0-actions-title">
          <h3 id="p0-actions-title">
            {th ? "การดำเนินการถัดไปตามลำดับ" : "Next exact actions"}
          </h3>
          <ol>
            {record.next_actions.map((action) => (
              <li key={action.sequence}>
                {th ? action.action_th : action.action_en}
              </li>
            ))}
          </ol>
        </section>
      </div>

      <footer className={styles.footer}>
        <span>
          {th ? "เวลาหลักฐานสถานะ" : "Status-evidence time"}:{" "}
          <b>{formatSourceTime(record.source_timestamp, language)}</b>
        </span>
        <span>
          {th ? "ระดับความเชื่อมั่น" : "Confidence"}:{" "}
          <b>{record.confidence_class}</b>
        </span>
        <span>
          {th ? "ผลต่อการตัดสินใจ" : "Decision effect"}:{" "}
          <b>{th ? "ไม่มี" : "none"}</b>
        </span>
      </footer>
    </section>
  );
}
