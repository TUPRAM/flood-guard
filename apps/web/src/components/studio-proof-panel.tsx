import Image from "next/image";

import type { ModelRun } from "@floodguard/contracts";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
import { publicArtifactHref } from "@/lib/proposal-evidence";
import type { Language } from "@/lib/types";
import { useProposalEvidence } from "@/lib/use-proposal-evidence";

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

export function StudioProofPanel({
  geoAiRun,
  language,
}: {
  geoAiRun?: ModelRun;
  language: Language;
}) {
  const evidence = useProposalEvidence();
  const th = language === "th";
  const manifest = evidence.state === "ready" ? evidence.manifest : undefined;
  const proof = manifest?.geoai_proof;
  const proofReceipt = manifest?.artifacts.find((artifact) => artifact.kind === "geoai_proof_receipt");
  const channels = geoAiRun?.channel_names.length ? geoAiRun.channel_names : TARGET_STACK;
  const imageArtifacts = manifest?.artifacts
    .filter((artifact) => artifact.media_type.startsWith("image/") && /probability|histogram/i.test(artifact.kind))
    .map((artifact) => ({ ...artifact, href: publicArtifactHref(artifact.relative_path, artifact.sha256) }))
    .filter((artifact): artifact is typeof artifact & { href: string } => Boolean(artifact.href))
    .slice(0, 2) ?? [];

  return (
    <section className="studio-section geoai-proof" aria-labelledby="geoai-proof-title">
      <div className="section-heading proof-heading">
        <div>
          <p className="eyebrow">01 · GEOAI PROOF PATH</p>
          <h2 id="geoai-proof-title">{th ? "หลักฐานการเชื่อมต่อแบบจำลอง" : "GeoAI integration evidence"}</h2>
        </div>
        <div className="proof-status-pills">
          {manifest && <StatePill tone="caution">{manifest.dataset_mode.replaceAll("_", " ")} · {manifest.operational_status.replaceAll("_", " ")}</StatePill>}
          <StatePill tone={manifest ? "ready" : evidence.state === "loading" ? "info" : "caution"}>
            {manifest
              ? (th ? "ตรวจ manifest แล้ว" : "Manifest validated")
              : evidence.state === "loading"
                ? (th ? "กำลังตรวจ manifest" : "Checking manifest")
                : (th ? "ยังไม่มี manifest" : "Manifest unavailable")}
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

      <div className="proof-layout">
        <div className="proof-flow" aria-label={th ? "ลำดับงาน GeoAI" : "GeoAI workflow"}>
          <ProofStep index="01" label={th ? "สแต็กคุณลักษณะ" : "Feature stack"} value={proof?.feature_stack_id ?? (th ? "เป้าหมายสัญญา 8 แบนด์" : "Eight-band contract target")} />
          <ProofStep index="02" label={th ? "การแปลงค่า" : "Explicit transform"} value={proof?.preprocessing_id ?? (th ? "ไม่ส่งค่า dB/ภูมิประเทศดิบผ่าน /255" : "No raw dB/terrain through implicit /255")} />
          <ProofStep index="03" label={th ? "การเตรียมไทล์" : "Tile preparation"} value={geoAiRun?.prepared_tile_manifest_sha256 ? shortDigest(geoAiRun.prepared_tile_manifest_sha256) : proofReceipt ? `${th ? "ใบรับรอง" : "proof receipt"} ${shortDigest(proofReceipt.sha256)}` : (th ? "รอหลักฐาน run" : "Awaiting run receipt")} />
          <ProofStep index="04" label={th ? "การอนุมาน" : "GeoAI inference"} value={proof ? `geoai-py ${proof.geoai_version}` : (th ? "รอ manifest ที่ตรวจสอบได้" : "Awaiting validated manifest")} />
          <ProofStep index="05" label={th ? "ความน่าจะเป็นชั้น 1" : "Class-1 probability"} value={proof?.output_probability_sha256 ? shortDigest(proof.output_probability_sha256) : (th ? "ยังไม่มี checksum" : "No checksum published")} />
          <ProofStep index="06" label={th ? "สะพานสู่ FloodGuard" : "FloodGuard aggregation"} value={proof?.aggregation_status ?? (th ? "ยังไม่มีหลักฐาน manifest" : "No manifest evidence")} />
        </div>

        <aside className="proof-contract" aria-label={th ? "สัญญาแบนด์และเกณฑ์" : "Band and gate contract"}>
          <div className="proof-contract-heading">
            <div><p className="eyebrow">{th ? "ลำดับแบนด์" : "Band order"}</p><h3>{channels.length} {th ? "ช่องข้อมูล" : "channels"}</h3></div>
            <StatePill tone={geoAiRun ? "ready" : "info"}>{geoAiRun ? (th ? "จาก model run" : "From model run") : (th ? "เป้าหมายสัญญา" : "Contract target")}</StatePill>
          </div>
          <ol className="band-list">{channels.map((channel) => <li key={channel}><span>{channel}</span></li>)}</ol>
          <dl className="proof-gates">
            <div><dt>processing_allowed</dt><dd>{String(proof?.processing_allowed ?? false)}</dd></div>
            <div><dt>can_feed_decision_layer</dt><dd>{String(proof?.can_feed_decision_layer ?? false)}</dd></div>
            <div><dt>{th ? "สถานะตรวจสอบ" : "Validation"}</dt><dd>{proof?.validation_status ?? (th ? "ไม่มีหลักฐาน" : "Unavailable")}</dd></div>
          </dl>
          <p className="proof-blocked-reason">{proof?.reason_blocked ?? (th ? "ยังไม่มี proposal evidence manifest ที่ผ่านการตรวจ จึงคงสถานะบล็อก" : "No validated proposal evidence manifest is available, so the proof remains fail-closed.")}</p>
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
