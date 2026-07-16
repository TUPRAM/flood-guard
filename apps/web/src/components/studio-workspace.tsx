"use client";

import Image from "next/image";
import { useState } from "react";

import type { ModelRun } from "@floodguard/contracts";

import { LanguageToggle } from "@/components/language-toggle";
import { PilotReadinessPanel } from "@/components/pilot-readiness-panel";
import { StatusBar } from "@/components/status-bar";
import { downloadText } from "@/lib/download";
import { formatNumber } from "@/lib/format";
import type { Language } from "@/lib/types";
import { useFloodGuardData } from "@/lib/use-floodguard-data";

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
  if (value === "deterministic_sar_baseline") return "Deterministic SAR baseline";
  if (value === "weak_label_logistic") return "Weak-label logistic";
  return "GeoAI candidate";
}

function safeManifest(run: ModelRun): string {
  return JSON.stringify(run, null, 2);
}

export function StudioWorkspace() {
  const data = useFloodGuardData();
  const [language, setLanguage] = useState<Language>("en");
  const [selectedRunId, setSelectedRunId] = useState(data.model_runs[0]?.run_id ?? "");
  const th = language === "th";
  const selectedRun = data.model_runs.find((run) => run.run_id === selectedRunId) ?? data.model_runs[0];
  const decisionEligible = data.model_runs.some((run) => run.can_feed_decision_layer);
  const hasGeoAiRun = data.model_runs.some((run) => run.model_family === "geoai");

  return (
    <main className="studio-page" lang={language}>
      <header className="studio-header">
        <a href="/studio/" className="brand brand-light">
          <Image src="/icon.svg" alt="" width={40} height={40} priority />
          <span><b>FloodGuard</b><small>{th ? "พื้นที่วิจัยและตรวจสอบ" : "Research & validation studio"}</small></span>
        </a>
        <nav aria-label="Product surfaces"><a href="/public/">{th ? "ประชาชน" : "Public"}</a><a href="/command/">{th ? "บัญชาการ" : "Command"}</a><a className="active" href="/studio/">Studio</a></nav>
        <LanguageToggle language={language} onChange={setLanguage} />
      </header>
      <StatusBar data={data} language={language} compact />

      <div className="studio-shell">
        <section className="studio-intro">
          <div><p className="eyebrow">{th ? "หลักฐานก่อนการใช้งาน" : "Evidence before promotion"}</p><h1>{th ? "มองเห็นข้อจำกัด ไม่ซ่อนสถานะบล็อก" : "Expose gates, not emergency actions"}</h1><p>{th ? "พื้นที่นี้แสดงความพร้อมของข้อมูล การ์ดแบบจำลอง และผลตรวจสอบ โดยไม่อ้างว่าแบบจำลองพร้อมใช้ตัดสินใจ" : "This workspace surfaces data readiness, model cards, and validation evidence without claiming operational readiness."}</p></div>
          <div className={`studio-verdict ${decisionEligible ? "ready" : "blocked"}`}><span>{th ? "ชั้นการตัดสินใจ" : "Decision layer"}</span><b>{decisionEligible ? (th ? "ผ่านเกณฑ์ตาม manifest" : "Manifest eligible") : (th ? "ยังไม่อนุญาต" : "Blocked")}</b><small>can_feed_decision_layer = {String(decisionEligible)}</small></div>
        </section>

        <PilotReadinessPanel readiness={data.pilot_readiness} language={language} surface="studio" />

        <section className="studio-section" aria-labelledby="readiness-title">
          <div className="section-heading"><div><p className="eyebrow">01 · DATA</p><h2 id="readiness-title">{th ? "ความพร้อมของข้อมูล" : "Data readiness"}</h2></div><span className="section-count">{data.readiness.filter((row) => row.status === "blocked").length} {th ? "รายการบล็อก" : "blocked"}</span></div>
          <div className="table-scroll"><table className="readiness-table"><thead><tr><th>{th ? "การตรวจ" : "Gate"}</th><th>{th ? "แหล่งข้อมูล" : "Source"}</th><th>{th ? "สถานะ" : "State"}</th><th>{th ? "เหตุผล" : "Reason"}</th></tr></thead><tbody>{data.readiness.map((row) => <tr key={row.check_id}><td><code>{row.check_id}</code></td><td>{row.source}</td><td><span className={`readiness-state ${row.status}`}>{row.status}</span></td><td>{row.reason_blocked || (th ? "ผ่านการตรวจแบบสาธิต" : "Fixture check ready")}</td></tr>)}</tbody></table></div>
        </section>

        <section className="studio-section" aria-labelledby="model-title">
          <div className="section-heading"><div><p className="eyebrow">02 · MODELS</p><h2 id="model-title">{th ? "เปรียบเทียบแบบจำลอง" : "Model comparison"}</h2></div><p>{th ? "อย่าเปรียบเทียบเมตริกข้ามขอบเขตหลักฐานโดยตรง" : "Metrics from different evidence scopes are not directly comparable."}</p></div>
          <div className="model-comparison-grid">
            {data.model_runs.map((run) => (
              <button type="button" key={run.run_id} className={`model-card ${selectedRun?.run_id === run.run_id ? "selected" : ""}`} onClick={() => setSelectedRunId(run.run_id)}>
                <span className="model-family">{familyLabel(run.model_family)}</span><b>{run.run_status}</b><small>{run.processing_scope}</small>
                <dl>{METRICS.slice(0, 4).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{formatNumber(run.validation_metrics[key], language, 3)}</dd></div>)}</dl>
                <span className={`feed-decision ${run.can_feed_decision_layer ? "yes" : "no"}`}>can_feed_decision_layer = {String(run.can_feed_decision_layer)}</span>
              </button>
            ))}
            {!hasGeoAiRun && <article className="model-card unavailable-card"><span className="model-family">GeoAI U-Net / FPN candidate</span><b>{th ? "ยังไม่รัน" : "Not run"}</b><small>{th ? "รอข้อมูลและหน้ากากอ้างอิงผ่านเกณฑ์" : "Waiting for source and reference-mask gates"}</small><dl>{METRICS.slice(0, 4).map(([, label]) => <div key={label}><dt>{label}</dt><dd>—</dd></div>)}</dl><span className="feed-decision no">can_feed_decision_layer = false</span></article>}
          </div>
        </section>

        {selectedRun && <section className="studio-section model-detail" aria-labelledby="model-card-title">
          <div className="section-heading"><div><p className="eyebrow">03 · MODEL CARD</p><h2 id="model-card-title">{selectedRun.run_id}</h2></div><button type="button" className="download-manifest" onClick={() => downloadText(`${selectedRun.run_id}-manifest.json`, safeManifest(selectedRun), "application/json")}>{th ? "ดาวน์โหลด manifest" : "Download manifest"}</button></div>
          <div className="model-detail-grid">
            <dl className="contract-list"><div><dt>Family</dt><dd>{familyLabel(selectedRun.model_family)}</dd></div><div><dt>Architecture</dt><dd>{selectedRun.architecture ?? "Unavailable"}</dd></div><div><dt>Channels</dt><dd>{selectedRun.num_channels ?? "—"} · {selectedRun.channel_names.join(", ")}</dd></div><div><dt>Preprocessing</dt><dd>{selectedRun.preprocessing.method}</dd></div><div><dt>Band transforms</dt><dd>{selectedRun.preprocessing.transforms.length > 0 ? selectedRun.preprocessing.transforms.map((item) => `${item.name}: ${item.physical_min}…${item.physical_max} ${item.units}`).join("; ") : "Not published for this legacy run"}</dd></div><div><dt>Transform receipt</dt><dd>{selectedRun.preprocessing.sidecar_sha256 ?? "Unavailable"}</dd></div><div><dt>Input roles</dt><dd>{selectedRun.input_manifest_rows.map((row) => row.role).join(", ")}</dd></div><div><dt>Feature receipt</dt><dd>{selectedRun.encoded_feature_sha256 ?? "Unavailable"}</dd></div><div><dt>Reference mask</dt><dd>{selectedRun.reference_mask_id} · {selectedRun.reference_mask_status}</dd></div><div><dt>Mask receipt</dt><dd>{selectedRun.reference_mask_sha256 ?? "Unavailable"}</dd></div><div><dt>Tile manifest</dt><dd>{selectedRun.prepared_tile_manifest_sha256 ?? "Not prepared"}</dd></div><div><dt>Spatial holdout</dt><dd>{selectedRun.spatial_holdout_ids.length > 0 ? selectedRun.spatial_holdout_ids.join(", ") : "Not declared"}</dd></div><div><dt>Spatial partitions</dt><dd>{selectedRun.spatial_partitions.length > 0 ? selectedRun.spatial_partitions.map((item) => `${item.spatial_group_id} (${item.split})`).join(", ") : "Not published"}</dd></div><div><dt>Output workspace</dt><dd>{selectedRun.external_output_workspace}</dd></div></dl>
            <div className="metric-panel"><h3>{th ? "เมตริกตรวจสอบ" : "Validation metrics"}</h3>{METRICS.map(([key, label]) => <div className="metric-row" key={key}><span>{label}</span><b>{formatNumber(selectedRun.validation_metrics[key], language, 3)}</b></div>)}<article className={selectedRun.can_feed_decision_layer ? "eligible-reason" : "blocked-reason"}><b>{selectedRun.can_feed_decision_layer ? (th ? "สถานะการส่งต่อ" : "Promotion state") : (th ? "เหตุผลที่บล็อก" : "Reason blocked")}</b><p>{selectedRun.can_feed_decision_layer ? (th ? "manifest ระบุว่าผ่านเกณฑ์การส่งต่อทั้งหมด" : "The manifest declares all decision-feed gates passed.") : selectedRun.reason_blocked}</p></article></div>
          </div>
        </section>}

        <section className="studio-section" aria-labelledby="errors-title">
          <div className="section-heading"><div><p className="eyebrow">04 · VALIDATION</p><h2 id="errors-title">{th ? "หมวดความผิดพลาด" : "Error categories"}</h2></div></div>
          <div className="error-grid">{data.error_categories.map((item) => <article key={item.category}><span>{item.status}</span><h3>{item.category.replaceAll("_", " ")}</h3><p>{item.note}</p></article>)}</div>
        </section>

        <footer className="studio-footer"><p>{data.status.dataset_mode === "fixture_demo" ? (th ? "ไม่มีพาธส่วนตัว ไฟล์ภาพต้นฉบับ หรือน้ำหนักแบบจำลองในชุดสาธิตนี้" : "This fixture bundle contains no private paths, source imagery, or model weights.") : (th ? "หน้าจอนี้แสดงเฉพาะ manifest สาธารณะที่ตัดพาธส่วนตัวออกแล้ว" : "This screen exposes only public manifests with private paths removed.")}</p><a href="/command/">{th ? "กลับไปที่ศูนย์บัญชาการ →" : "Open planning command center →"}</a></footer>
      </div>
    </main>
  );
}
