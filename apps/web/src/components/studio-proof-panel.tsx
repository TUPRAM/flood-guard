import Image from "next/image";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
import { publicArtifactHref } from "@/lib/proposal-evidence";
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

export function StudioProofPanel({ language }: { language: Language }) {
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
  const receiptUnavailableReason = evidence.state === "unavailable"
    ? evidence.reason
    : manifest?.geoai_proof.reason_blocked ?? (th ? "ยังไม่มีใบรับรอง GeoAI ที่ตรวจสอบได้" : "No validated GeoAI proof receipt is available.");

  return (
    <section className="studio-section geoai-proof" aria-labelledby="geoai-proof-title">
      <div className="section-heading proof-heading">
        <div>
          <p className="eyebrow">01 · GEOAI PROOF PATH</p>
          <h2 id="geoai-proof-title">{th ? "หลักฐานการเชื่อมต่อแบบจำลอง" : "GeoAI integration evidence"}</h2>
        </div>
        <div className="proof-status-pills">
          {manifest && <StatePill tone="caution">{manifest.dataset_mode.replaceAll("_", " ")} · {manifest.operational_status.replaceAll("_", " ")}</StatePill>}
          <StatePill tone={receipt ? "ready" : evidence.state === "loading" ? "info" : "caution"}>
            {receipt
              ? (th ? "ตรวจ manifest และใบรับรองแล้ว" : "Manifest + receipt verified")
              : evidence.state === "loading"
                ? (th ? "กำลังตรวจ manifest และ checksum" : "Checking manifest + checksum")
                : (th ? "คงสถานะบล็อก" : "Evidence fail-closed")}
          </StatePill>
        </div>
      </div>

      <EvidenceNotice
        tone="caution"
        title={th ? "หลักฐานสังเคราะห์ ไม่ใช่ความแม่นยำจากเหตุการณ์จริง" : "Synthetic integration proof; not evidence of real flood-detection accuracy."}
      >
        {th
          ? "เอาต์พุตนี้ไม่ใช่คำเตือนภัย และยังไม่ผ่านเกณฑ์เพื่อส่งต่อชั้นการตัดสินใจ"
          : "This output is not a warning and remains blocked from the decision layer until qualified real-data gates pass."}
      </EvidenceNotice>

      <div className={styles.receiptGrid} aria-label={th ? "รายละเอียดใบรับรอง GeoAI" : "Validated GeoAI receipt details"}>
        {receipt ? (
          <>
            <article className={styles.receiptCard}>
              <div className={styles.receiptCardHeader}>
                <div><p className="eyebrow">MODEL CONTRACT</p><h3>{th ? "โมเดลที่รันจริง" : "Executed model"}</h3></div>
                <StatePill tone="ready">{receipt.training_execution.replaceAll("_", " ")}</StatePill>
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
                <div><p className="eyebrow">GRID + OUTPUT</p><h3>{th ? "การตรวจสอบแบบ fail-closed" : "Fail-closed validation"}</h3></div>
                <StatePill tone="ready">{validationEntries.length}/{validationEntries.length} passed</StatePill>
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
                <div><p className="eyebrow">PROBABILITY</p><h3>{th ? "ฮิสโตแกรมและการรวมผล" : "Histogram + aggregation"}</h3></div>
                <StatePill tone="caution">report only</StatePill>
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
              <figcaption className={styles.visuallyHidden}>{th ? "ผลรวม FloodGuard ใช้เพื่อรายงานเท่านั้น และส่งต่อ FPPS ไม่ได้" : "FloodGuard aggregation is report-only and cannot feed FPPS or the decision layer."}</figcaption>
            </figure>
          </>
        ) : (
          <p className={styles.blockedReceipt} role="status">
            <b>{th ? "ไม่แสดงรายละเอียดหลักฐานทดแทน" : "No substitute proof details displayed."}</b>{" "}
            {receiptUnavailableReason}
          </p>
        )}
      </div>

      <div className="proof-layout">
        <div className="proof-flow" aria-label={th ? "ลำดับงาน GeoAI" : "GeoAI workflow"}>
          <ProofStep index="01" label={th ? "สแต็กคุณลักษณะ" : "Feature stack"} value={receipt?.feature_stack.feature_stack_id ?? (th ? "เป้าหมายสัญญา 8 แบนด์" : "Eight-band contract target")} />
          <ProofStep index="02" label={th ? "การแปลงค่า" : "Explicit transform"} value={receipt?.feature_stack.preprocessing_id ?? (th ? "ไม่ส่งค่า dB/ภูมิประเทศดิบผ่าน /255" : "No raw dB/terrain through implicit /255")} />
          <ProofStep index="03" label={th ? "การเตรียมไทล์" : "Tile preparation"} value={receipt ? shortDigest(receipt.tile_export.prepared_tile_manifest_sha256) : (th ? "รอใบรับรองที่ตรวจสอบได้" : "Awaiting validated receipt")} />
          <ProofStep index="04" label={th ? "สถาปัตยกรรมโมเดล" : "Model architecture"} value={receipt ? `${receipt.model.architecture} · ${receipt.model.encoder} · weights ${receipt.model.encoder_weights ?? "none"}` : (th ? "ไม่แสดงเมื่อไม่มีใบรับรอง" : "Hidden without verified receipt")} />
          <ProofStep index="05" label={th ? "การอนุมาน" : "GeoAI inference"} value={receipt ? `geoai-py ${receipt.geoai_version} · ${receipt.execution_mode.replaceAll("_", " ")}` : (th ? "รอ checksum" : "Awaiting checksum verification")} />
          <ProofStep index="06" label="Input manifest" value={receipt ? shortDigest(receipt.feature_stack.input_manifest_sha256) : (th ? "ยังไม่ตรวจสอบ" : "Not verified")} />
          <ProofStep index="07" label={th ? "ความน่าจะเป็นชั้น 1" : "Class-1 probability"} value={receipt ? shortDigest(receipt.probability.sha256) : (th ? "ยังไม่มี checksum ที่ตรวจแล้ว" : "No verified checksum")} />
          <ProofStep index="08" label={th ? "CRS และกริด" : "CRS + grid validation"} value={receipt ? `${validationEntries.length}/${validationEntries.length} ${th ? "ผ่าน" : "checks passed"}` : (th ? "คงสถานะบล็อก" : "Fail-closed")} />
          <ProofStep index="09" label={th ? "การรวมผล FloodGuard" : "FloodGuard aggregation"} value={receipt ? `${formatPercent(receipt.aggregation.mean_flood_probability_0_1)} mean · ${receipt.aggregation.status}` : (th ? "ไม่มีผลที่ตรวจสอบแล้ว" : "No validated result")} />
        </div>

        <aside className="proof-contract" aria-label={th ? "สัญญาแบนด์และเกณฑ์" : "Band and gate contract"}>
          <div className="proof-contract-heading">
            <div><p className="eyebrow">{th ? "ลำดับแบนด์" : "Band order"}</p><h3>{channels.length} {th ? "ช่องข้อมูล" : "channels"}</h3></div>
            <StatePill tone={receipt ? "ready" : "info"}>{receipt ? (th ? "จากใบรับรอง" : "From receipt") : (th ? "เป้าหมายสัญญา" : "Contract target")}</StatePill>
          </div>
          <ol className="band-list">{channels.map((channel) => <li key={channel}><span>{channel}</span></li>)}</ol>
          <dl className="proof-gates">
            <div><dt>processing_allowed</dt><dd>{String(receipt?.processing_allowed ?? false)}</dd></div>
            <div><dt>can_feed_decision_layer</dt><dd>{String(receipt?.can_feed_decision_layer ?? false)}</dd></div>
            <div><dt>{th ? "สถานะตรวจสอบ" : "Validation"}</dt><dd>{receipt ? proof?.validation_status : (th ? "ไม่มีหลักฐาน" : "Unavailable")}</dd></div>
            <div><dt>eligible_for_fpps</dt><dd>{String(receipt?.aggregation.eligible_for_fpps ?? false)}</dd></div>
            <div><dt>{th ? "ใบรับรองไฟล์" : "Receipt file"}</dt><dd>{receiptArtifact && receipt ? shortDigest(receiptArtifact.sha256) : (th ? "ยังไม่ตรวจสอบ" : "Unverified")}</dd></div>
          </dl>
          <p className="proof-blocked-reason">{receipt?.reason_blocked ?? receiptUnavailableReason}</p>
        </aside>
      </div>

      {imageArtifacts.length > 0 && (
        <div className="proof-images">
          {imageArtifacts.map((artifact) => (
            <figure key={artifact.sha256}>
              <Image src={artifact.href} width={640} height={320} unoptimized alt={artifact.kind.replaceAll("_", " ")} />
              <figcaption>{artifact.kind.replaceAll("_", " ")} · SHA-256 {shortDigest(artifact.sha256)}</figcaption>
            </figure>
          ))}
        </div>
      )}

      <p className="proof-manifest-state" role="status">
        {manifest
          ? `${manifest.artifacts.length} ${th ? "อาร์ติแฟกต์" : "artifacts"} · ${manifest.test_suites.length} ${th ? "ชุดทดสอบ" : "test suites"} · ${th ? "สร้างเมื่อ" : "generated"} ${manifest.generated_at}`
          : evidence.state === "unavailable"
            ? (th ? "ไม่ใช้ข้อมูลทดแทน: " : "No substitute evidence used: ") + evidence.reason
            : (th ? "กำลังตรวจสอบ manifest โดยไม่เลื่อนสถานะ" : "Validating the manifest without promoting its state")}
      </p>
    </section>
  );
}

function ProofStep({ index, label, value }: { index: string; label: string; value: string }) {
  return <article><span>{index}</span><div><b>{label}</b><small>{value}</small></div></article>;
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
