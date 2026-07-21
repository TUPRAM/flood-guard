import Image from "next/image";

import type { ModelRun } from "@floodguard/contracts";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
import { publicArtifactHref } from "@/lib/proposal-evidence";
import {
  classifyStudioEvidenceScope,
  type StudioEvidenceScopeItem,
  type StudioModelEvidence,
} from "@/lib/studio-evidence-scope";
import type { Language } from "@/lib/types";
import { useProposalEvidence } from "@/lib/use-proposal-evidence";

import styles from "./studio-proof-panel.module.css";

const TARGET_STACK = [
  "pre-event VV",
  "post-event VV",
  "pre-event VH",
  "post-event VH",
  "VV change",
  "VH change",
  "slope or HAND",
  "permanent-water flag",
] as const;

const VALIDATION_LABELS = {
  crs: "CRS",
  transform: "Transform",
  shape: "Shape / dimensions",
  nodata: "Nodata",
  class_mapping: "Class mapping",
  probability_range: "Probability range",
  provenance_tags: "Provenance tags",
} as const;

const QUALIFIED_METRICS = [
  "iou",
  "f1_dice",
  "precision",
  "recall",
  "area_error_ratio",
  "brier_score",
  "expected_calibration_error",
] as const;

type EvidenceScopeKind = "technical" | "observed" | "operational";

function evidenceScopeReason(kind: EvidenceScopeKind, state: StudioEvidenceScopeItem["state"], th: boolean): string {
  if (kind === "technical") {
    if (state === "checking") return th ? "กำลังตรวจสอบความสมบูรณ์ของบันทึกหลักฐาน" : "Evidence-record integrity checks are in progress.";
    if (state === "executed") return th ? "เส้นทางประมวลผลผ่านการตรวจสอบความสมบูรณ์แล้ว ผลนี้ไม่ใช่การวัดความแม่นยำจากเหตุการณ์ที่สังเกตจริง" : "The end-to-end model path passed its integrity checks. This is a systems check, not observed-event accuracy.";
    return th ? "ยังไม่มีบันทึกการประมวลผลที่ตรวจสอบความสมบูรณ์ได้" : "A verified end-to-end processing record is not currently available.";
  }
  if (kind === "observed") {
    if (state === "executed") return th ? "โมเดลที่เปรียบเทียบใช้ข้อมูลสังเกตการณ์ ข้อมูลอ้างอิง พื้นที่ทดสอบอิสระ และชุดเมตริกที่ตรวจสอบแล้วร่วมกัน" : "All comparison models share validated observations, reference data, held-out geography, and the required metrics.";
    if (state === "not_run") return th ? "ยังไม่มีการเปรียบเทียบด้วยข้อมูลสังเกตการณ์ที่ครบถ้วน" : "No complete observed-data comparison is currently published.";
    return th ? "การประเมินที่เผยแพร่ยังขาดข้อกำหนดการยืนยันด้วยข้อมูลสังเกตการณ์อย่างน้อยหนึ่งรายการ" : "The published evaluation is missing one or more observed-data validation requirements.";
  }
  if (state === "eligible") return th ? "มีอย่างน้อยหนึ่งการประเมินที่ผ่านข้อกำหนดด้านหลักฐานสำหรับการตรวจรับ" : "At least one evaluation meets every evidence requirement for operational acceptance.";
  return th ? "ยังไม่มีการประเมินที่ผ่านข้อกำหนดด้านหลักฐานและธรรมาภิบาลครบถ้วน" : "No evaluation currently meets every operational evidence and governance requirement.";
}

function reviewStateLabel(value: boolean, th: boolean): string {
  return value ? (th ? "ตรวจสอบแล้ว" : "Verified") : (th ? "อยู่ระหว่างตรวจสอบ" : "In review");
}

export function StudioProofPanel({ language, modelRuns }: { language: Language; modelRuns: ModelRun[] }) {
  const evidence = useProposalEvidence();
  const th = language === "th";
  const manifest = evidence.state === "ready" ? evidence.manifest : undefined;
  const receipt = evidence.state === "ready" ? evidence.proofReceipt : null;
  const proof = receipt ? manifest?.geoai_proof : undefined;
  const receiptArtifact = manifest?.artifacts.find((artifact) => artifact.kind === "geoai_proof_receipt");
  const channels = receipt?.feature_stack.channel_names ?? TARGET_STACK;
  const imageArtifacts = receipt ? manifest?.artifacts
    .filter((artifact) => artifact.media_type.startsWith("image/") && /probability|histogram/i.test(artifact.kind))
    .map((artifact) => ({ ...artifact, href: publicArtifactHref(artifact.relative_path, artifact.sha256) }))
    .filter((artifact): artifact is typeof artifact & { href: string } => Boolean(artifact.href))
    .slice(0, 2) ?? [] : [];
  const validationEntries = receipt ? Object.entries(receipt.validation_checks) : [];
  const receiptUnavailableReason = th
    ? "ยังไม่มีบันทึกหลักฐาน GeoAI ที่ตรวจสอบความสมบูรณ์ได้"
    : "A verified GeoAI evidence record is not currently available.";
  const evidenceScope = classifyStudioEvidenceScope({
    evidenceState: evidence.state,
    proofReceiptVerified: Boolean(receipt),
    proofReasonBlocked: receipt?.reason_blocked ?? manifest?.geoai_proof.reason_blocked ?? "",
    evidenceUnavailableReason: evidence.state === "unavailable" ? evidence.reason : undefined,
    models: modelRuns.map(toStudioModelEvidence),
  });

  return (
    <section className="studio-section geoai-proof studio-evidence-assurance" aria-labelledby="geoai-proof-title">
      <div className="section-heading proof-heading">
        <div>
          <p className="eyebrow">{th ? "01 · การรับรองหลักฐาน" : "01 · EVIDENCE ASSURANCE"}</p>
          <h2 id="geoai-proof-title">{th ? "การตรวจสอบหลักฐาน GeoAI" : "GeoAI evidence assurance"}</h2>
        </div>
        <div className="proof-status-pills">
          {manifest && <StatePill tone="info">{th ? "บันทึกงานวิจัย" : "Research record"}</StatePill>}
          <StatePill tone={receipt ? "ready" : evidence.state === "loading" ? "info" : "caution"}>
            {receipt
              ? (th ? "ตรวจสอบบันทึกหลักฐานแล้ว" : "Evidence record verified")
              : evidence.state === "loading"
                ? (th ? "กำลังตรวจสอบความสมบูรณ์" : "Checking record integrity")
                : (th ? "ต้องตรวจสอบเพิ่มเติม" : "Further review required")}
          </StatePill>
        </div>
      </div>

      <div className={styles.scopeGrid} aria-label={th ? "ระดับการตรวจสอบหลักฐาน" : "Evidence assurance levels"}>
        <EvidenceScopeCard
          kind="technical"
          title={th ? "การตรวจสอบระบบ" : "Technical verification"}
          item={evidenceScope.integration}
          language={language}
        />
        <EvidenceScopeCard
          kind="observed"
          title={th ? "การยืนยันด้วยข้อมูลสังเกตการณ์" : "Observed-data validation"}
          item={evidenceScope.qualifiedEvaluation}
          language={language}
        />
        <EvidenceScopeCard
          kind="operational"
          title={th ? "ความพร้อมใช้งาน" : "Operational readiness"}
          item={evidenceScope.decisionEligibility}
          language={language}
        />
      </div>

      <EvidenceNotice
        tone="caution"
        title={th ? "ขอบเขตของการประเมินนี้" : "Scope of this evaluation"}
      >
        {th
          ? "ผลนี้ยืนยันขั้นตอนทางเทคนิคเท่านั้น ไม่ใช่การวัดความแม่นยำจากเหตุการณ์ที่สังเกตจริง คำเตือนภัยอย่างเป็นทางการ หรือการอนุญาตใช้งาน"
          : "This result verifies the technical workflow only. It is not observed-event accuracy, an official warning, or operational authorization."}
      </EvidenceNotice>

      <div className={styles.receiptGrid} aria-label={th ? "รายละเอียดใบรับรอง GeoAI" : "Validated GeoAI receipt details"}>
        {receipt ? (
          <>
            <article className={styles.receiptCard}>
              <div className={styles.receiptCardHeader}>
                <div><p className="eyebrow">{th ? "บันทึกโมเดล" : "MODEL RECORD"}</p><h3>{th ? "โมเดลที่ประเมิน" : "Evaluated model"}</h3></div>
                <StatePill tone="ready">{th ? "ตรวจสอบแล้ว" : "Verified execution"}</StatePill>
              </div>
              <dl className={styles.receiptList}>
                <div><dt>{th ? "สถาปัตยกรรม" : "Architecture"}</dt><dd>{receipt.model.architecture}</dd></div>
                <div><dt>Encoder</dt><dd>{receipt.model.encoder}</dd></div>
                <div><dt>Encoder weights</dt><dd>{receipt.model.encoder_weights ?? "None"}</dd></div>
                <div><dt>{th ? "ลำดับแบนด์" : "Band order"}</dt><dd>{receipt.feature_stack.channel_count} channels</dd></div>
                <div>
                  <dt>Input manifest</dt>
                  <dd title={receipt.feature_stack.input_manifest_sha256} aria-label={`SHA-256 ${receipt.feature_stack.input_manifest_sha256}`}>{shortDigest(receipt.feature_stack.input_manifest_sha256)}</dd>
                </div>
                <div>
                  <dt>{th ? "ใบรับรองไทล์" : "Tile manifest"}</dt>
                  <dd title={receipt.tile_export.prepared_tile_manifest_sha256} aria-label={`SHA-256 ${receipt.tile_export.prepared_tile_manifest_sha256}`}>{shortDigest(receipt.tile_export.prepared_tile_manifest_sha256)}</dd>
                </div>
              </dl>
            </article>

            <article className={styles.receiptCard}>
              <div className={styles.receiptCardHeader}>
                <div><p className="eyebrow">{th ? "กริดและผลลัพธ์" : "GRID & OUTPUT"}</p><h3>{th ? "การตรวจสอบความสมบูรณ์" : "Integrity validation"}</h3></div>
                <StatePill tone="ready">{validationEntries.length}/{validationEntries.length} {th ? "ผ่าน" : "checks passed"}</StatePill>
              </div>
              <ul className={styles.validationList}>
                {validationEntries.map(([name]) => (
                  <li key={name}>{VALIDATION_LABELS[name as keyof typeof VALIDATION_LABELS]}</li>
                ))}
              </ul>
              <dl className={styles.receiptList}>
                <div><dt>CRS</dt><dd>{receipt.probability.grid.crs}</dd></div>
                <div><dt>{th ? "ขนาดกริด" : "Grid shape"}</dt><dd>{receipt.probability.grid.width} × {receipt.probability.grid.height}</dd></div>
                <div><dt>Nodata</dt><dd>{receipt.probability.nodata}</dd></div>
                <div><dt>{th ? "คลาสที่สกัด" : "Extracted class"}</dt><dd>class {receipt.probability.class_index} · {receipt.probability.dtype}</dd></div>
              </dl>
            </article>

            <figure className={styles.receiptCard}>
              <div className={styles.receiptCardHeader}>
                <div><p className="eyebrow">{th ? "ความน่าจะเป็น" : "PROBABILITY"}</p><h3>{th ? "การกระจายและค่าสรุป" : "Distribution & summary"}</h3></div>
                <StatePill tone="caution">{th ? "ผลการวิจัย" : "Research summary"}</StatePill>
              </div>
              <ol className={styles.histogram} aria-hidden="true">
                {receipt.probability.histogram_counts.map((count, index) => (
                  <li key={`${receipt.probability.histogram_bin_edges[index]}-${receipt.probability.histogram_bin_edges[index + 1]}`}>
                    <span style={{ height: `${histogramHeight(count, receipt.probability.histogram_counts)}%` }} />
                  </li>
                ))}
              </ol>
              <div className={styles.histogramAxis} aria-hidden="true"><span>0.0</span><span>{th ? "ความน่าจะเป็นชั้น 1" : "class-1 probability"}</span><span>1.0</span></div>
              <table className={styles.visuallyHidden}>
                <caption>{th ? "จำนวนพิกเซลในแต่ละช่วงความน่าจะเป็นชั้น 1" : "Class-1 probability histogram pixel counts"}</caption>
                <thead><tr><th>{th ? "ช่วง" : "Range"}</th><th>{th ? "จำนวนพิกเซล" : "Pixels"}</th></tr></thead>
                <tbody>
                  {receipt.probability.histogram_counts.map((count, index) => (
                    <tr key={`table-${receipt.probability.histogram_bin_edges[index]}`}>
                      <td>{formatBin(receipt.probability.histogram_bin_edges[index])}–{formatBin(receipt.probability.histogram_bin_edges[index + 1])}</td>
                      <td>{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className={styles.metricStrip}>
                <div><span>{th ? "ค่าเฉลี่ย" : "Mean"}</span><strong>{formatPercent(receipt.aggregation.mean_flood_probability_0_1)}</strong></div>
                <div><span>P90</span><strong>{formatPercent(receipt.aggregation.p90_flood_probability_0_1)}</strong></div>
                <div><span>{th ? "พิกเซล" : "Pixels"}</span><strong>{receipt.aggregation.sample_pixel_count.toLocaleString("en-US")}</strong></div>
              </div>
              <figcaption className={styles.visuallyHidden}>{th ? "ค่าสรุปงานวิจัยนี้จะไม่ใช้ในการจัดลำดับเชิงปฏิบัติการหากยังไม่ผ่านการยืนยันด้วยข้อมูลสังเกตการณ์" : "This research summary is not used for operational prioritization without observed-data validation."}</figcaption>
            </figure>
          </>
        ) : (
          <p className={styles.blockedReceipt} role="status">
            <b>{th ? "รายละเอียดการตรวจสอบยังไม่พร้อม" : "Verification details are not yet available."}</b>{" "}
            {receiptUnavailableReason}
          </p>
        )}
      </div>

      <details className={styles.technicalDetails}>
        <summary>{th ? "ดูขั้นตอน แบนด์ การแปลงค่า และเกณฑ์การตรวจสอบ" : "View workflow, band order, transforms, and review criteria"}</summary>
        <div className="proof-layout">
          <div className="proof-flow" aria-label={th ? "ลำดับงาน GeoAI" : "GeoAI workflow"}>
          <ProofStep index="01" label={th ? "สแต็กคุณลักษณะ" : "Feature stack"} value={receipt?.feature_stack.feature_stack_id ?? (th ? "เป้าหมายสัญญา 8 แบนด์" : "Eight-band contract target")} />
          <ProofStep index="02" label={th ? "การแปลงค่า" : "Explicit transform"} value={receipt?.feature_stack.preprocessing_id ?? (th ? "ไม่ส่งค่า dB/ภูมิประเทศดิบผ่าน /255" : "No raw dB/terrain through implicit /255")} />
          <ProofStep index="03" label={th ? "การเตรียมไทล์" : "Tile preparation"} value={receipt ? shortDigest(receipt.tile_export.prepared_tile_manifest_sha256) : (th ? "รอบันทึกที่ตรวจสอบได้" : "Awaiting verified record")} />
          <ProofStep index="04" label={th ? "สถาปัตยกรรมโมเดล" : "Model architecture"} value={receipt ? `${receipt.model.architecture} · ${receipt.model.encoder} · weights ${receipt.model.encoder_weights ?? "none"}` : (th ? "แสดงเมื่อมีบันทึกที่ตรวจสอบแล้ว" : "Available with a verified record")} />
          <ProofStep index="05" label={th ? "การอนุมาน" : "GeoAI inference"} value={receipt ? `geoai-py ${receipt.geoai_version} · ${receipt.execution_mode.replaceAll("_", " ")}` : (th ? "รอตรวจสอบความสมบูรณ์" : "Awaiting integrity verification")} />
          <ProofStep index="06" label="Input manifest" value={receipt ? shortDigest(receipt.feature_stack.input_manifest_sha256) : (th ? "ยังไม่ตรวจสอบ" : "Not verified")} />
          <ProofStep index="07" label={th ? "ความน่าจะเป็นชั้น 1" : "Class-1 probability"} value={receipt ? shortDigest(receipt.probability.sha256) : (th ? "ยังไม่มี checksum ที่ตรวจแล้ว" : "No verified checksum")} />
          <ProofStep index="08" label={th ? "CRS และกริด" : "CRS + grid validation"} value={receipt ? `${validationEntries.length}/${validationEntries.length} ${th ? "ผ่าน" : "checks passed"}` : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")} />
          <ProofStep index="09" label={th ? "การรวมผล FloodGuard" : "FloodGuard aggregation"} value={receipt ? `${formatPercent(receipt.aggregation.mean_flood_probability_0_1)} mean · ${receipt.aggregation.status}` : (th ? "ไม่มีผลที่ตรวจสอบแล้ว" : "No validated result")} />
          </div>

          <aside className="proof-contract" aria-label={th ? "แบนด์และเกณฑ์การตรวจสอบ" : "Band and review criteria"}>
          <div className="proof-contract-heading">
            <div><p className="eyebrow">{th ? "ลำดับแบนด์" : "Band order"}</p><h3>{channels.length} {th ? "ช่องข้อมูล" : "channels"}</h3></div>
            <StatePill tone={receipt ? "ready" : "info"}>{receipt ? (th ? "บันทึกที่ตรวจสอบแล้ว" : "Verified record") : (th ? "ข้อกำหนดอ้างอิง" : "Reference specification")}</StatePill>
          </div>
          <ol className="band-list">{channels.map((channel) => <li key={channel}><span>{channel}</span></li>)}</ol>
          <dl className="proof-gates">
            <div><dt>{th ? "การอนุมัติข้อมูลนำเข้า" : "Input-use approval"}</dt><dd>{reviewStateLabel(Boolean(receipt?.processing_allowed), th)}</dd></div>
            <div><dt>{th ? "ความพร้อมใช้งาน" : "Operational readiness"}</dt><dd>{reviewStateLabel(Boolean(receipt?.can_feed_decision_layer), th)}</dd></div>
            <div><dt>{th ? "สถานะตรวจสอบ" : "Validation status"}</dt><dd>{receipt && proof?.validation_status === "passed" ? (th ? "ตรวจสอบแล้ว" : "Verified") : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")}</dd></div>
            <div><dt>{th ? "การรวมใน FPPS" : "FPPS inclusion"}</dt><dd>{reviewStateLabel(Boolean(receipt?.aggregation.eligible_for_fpps), th)}</dd></div>
            <div><dt>{th ? "ความสมบูรณ์ของไฟล์" : "File integrity"}</dt><dd>{receiptArtifact && receipt ? shortDigest(receiptArtifact.sha256) : (th ? "อยู่ระหว่างตรวจสอบ" : "In review")}</dd></div>
          </dl>
          <p className="proof-blocked-reason">{receipt?.can_feed_decision_layer
            ? (th ? "หลักฐานผ่านข้อกำหนดสำหรับการตรวจรับแล้ว" : "The evidence meets the requirements for operational acceptance.")
            : (th ? "การใช้งานยังอยู่ระหว่างตรวจสอบจนกว่าการยืนยันด้วยข้อมูลสังเกตการณ์และธรรมาภิบาลจะเสร็จสมบูรณ์" : "Operational review remains held until observed-data validation and governance requirements are complete.")}</p>
          </aside>
        </div>
      </details>

      {imageArtifacts.length > 0 && (
        <div className="proof-images">
          {imageArtifacts.map((artifact) => (
            <figure key={artifact.sha256}>
              <Image src={artifact.href} width={640} height={320} unoptimized alt={th ? "ภาพสรุปผลการวิจัย" : "Research result figure"} />
              <figcaption>{th ? "ภาพสรุปผลการวิจัย" : "Research result figure"} · SHA-256 {shortDigest(artifact.sha256)}</figcaption>
            </figure>
          ))}
        </div>
      )}

      <p className="proof-manifest-state" role="status">
        {manifest
          ? `${manifest.artifacts.length} ${th ? "ไฟล์หลักฐาน" : "evidence files"} · ${manifest.test_suites.length} ${th ? "ชุดการตรวจสอบ" : "validation suites"} · ${th ? "ปรับปรุงเมื่อ" : "updated"} ${manifest.generated_at}`
          : evidence.state === "unavailable"
            ? (th ? "ยังไม่มีบันทึกหลักฐานที่ตรวจสอบได้" : "A verified evidence record is not currently available.")
            : (th ? "กำลังตรวจสอบความสมบูรณ์ของบันทึกหลักฐาน" : "Validating evidence-record integrity")}
      </p>
    </section>
  );
}

function ProofStep({ index, label, value }: { index: string; label: string; value: string }) {
  return <article><span>{index}</span><div><b>{label}</b><small>{value}</small></div></article>;
}

function EvidenceScopeCard({ kind, title, item, language }: { kind: EvidenceScopeKind; title: string; item: StudioEvidenceScopeItem; language: Language }) {
  const th = language === "th";
  return (
    <article className={`${styles.scopeCard} ${styles[item.state]} studio-scope-${kind}`}>
      <span>{title}</span>
      <b>{evidenceStateLabel(item.state, th)}</b>
      <p>{evidenceScopeReason(kind, item.state, th)}</p>
    </article>
  );
}

function evidenceStateLabel(state: StudioEvidenceScopeItem["state"], th: boolean): string {
  if (state === "checking") return th ? "กำลังตรวจสอบ" : "Checking";
  if (state === "executed") return th ? "ตรวจสอบแล้ว" : "Verified";
  if (state === "not_run") return th ? "ยังไม่พร้อม" : "Unavailable";
  if (state === "eligible") return th ? "พร้อมตรวจรับ" : "Ready for acceptance";
  return th ? "อยู่ระหว่างตรวจสอบ" : "Review held";
}

function toStudioModelEvidence(run: ModelRun): StudioModelEvidence {
  const referenceMaskStatus = run.reference_mask_status.toLowerCase();
  const hasHoldoutReceipt = run.input_manifest_rows.some(
    (row) => /spatial[_-]?holdout/i.test(row.role) && /^[a-f0-9]{64}$/i.test(row.sha256) && row.processing_allowed,
  );
  return {
    datasetMode: run.dataset_mode,
    modelFamily: run.model_family,
    runStatus: run.run_status,
    processingAllowed: run.processing_allowed,
    canFeedDecisionLayer: run.can_feed_decision_layer,
    reasonBlocked: run.reason_blocked,
    hasQualifiedReferenceMask: Boolean(run.reference_mask_sha256)
      && /^(qualified|authoritative|accepted)(?:_|$)/.test(referenceMaskStatus),
    hasImmutableSpatialHoldout: hasHoldoutReceipt
      && run.spatial_holdout_ids.length > 0
      && run.spatial_partitions.some((partition) => partition.split === "holdout"),
    hasCompleteValidationMetrics: QUALIFIED_METRICS.every((metric) => typeof run.validation_metrics[metric] === "number"),
  };
}

function shortDigest(value: string): string {
  return `${value.slice(0, 10)}…${value.slice(-8)}`;
}

function histogramHeight(count: number, counts: number[]): number {
  const maximum = Math.max(...counts, 1);
  return count === 0 ? 2 : Math.max(6, Math.round((count / maximum) * 100));
}

function formatBin(value: number): string {
  return value.toFixed(1);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(value);
}
