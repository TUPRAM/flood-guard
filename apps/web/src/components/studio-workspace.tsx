"use client";

import Image from "next/image";
import { useState } from "react";

import type { ModelRun } from "@floodguard/contracts";

import { LanguageToggle } from "@/components/language-toggle";
import { PilotReadinessPanel } from "@/components/pilot-readiness-panel";
import { StatusBar } from "@/components/status-bar";
import { StudioProofPanel } from "@/components/studio-proof-panel";
import { downloadText } from "@/lib/download";
import { formatNumber } from "@/lib/format";
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
  if (value === "deterministic_sar_baseline") return "Deterministic SAR baseline";
  if (value === "weak_label_logistic") return "Weak-label logistic";
  return "GeoAI candidate";
}

function safeManifest(run: ModelRun): string {
  return JSON.stringify(run, null, 2);
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
        <section className={styles.consoleHeader} aria-labelledby="research-console-title">
          <div>
            <p className="eyebrow">{th ? "หลักฐานก่อนการเลื่อนสถานะ" : "Evidence before promotion"}</p>
            <h1 id="research-console-title">{th ? "คอนโซลวิจัยและตรวจสอบ" : "Research evidence console"}</h1>
            <p>{th ? "ดูสิ่งที่รัน ขอบเขตหลักฐาน สิ่งที่ผ่าน เหตุผลบล็อก และสิทธิ์ส่งต่อชั้นการตัดสินใจในมุมมองเดียว" : "See what ran, its evidence scope, passed checks, exact blockers, and decision eligibility in one fail-closed workspace."}</p>
          </div>
          <div className={styles.consoleSummary} aria-label={th ? "สรุปสถานะสตูดิโอ" : "Studio status summary"}>
            <div><span>{th ? "รันที่เผยแพร่" : "Published runs"}</span><b>{data.model_runs.length}</b></div>
            <div><span>{th ? "เกณฑ์ข้อมูลบล็อก" : "Blocked data gates"}</span><b>{blockedGateCount}</b></div>
            <div><span>{th ? "ชั้นการตัดสินใจ" : "Decision layer"}</span><b>{decisionEligible ? (th ? "ผ่านเกณฑ์" : "Eligible") : (th ? "บล็อก" : "Blocked")}</b></div>
          </div>
        </section>

        <nav className={styles.consoleNav} aria-label={th ? "ส่วนของคอนโซลวิจัย" : "Research console sections"}>
          <a href="#integration-proof">{th ? "หลักฐานการเชื่อมต่อ" : "Integration proof"}</a>
          <a href="#data-gates">{th ? "เกณฑ์ข้อมูล" : "Data gates"}</a>
          <a href="#model-matrix">{th ? "การเปรียบเทียบ" : "Model matrix"}</a>
          <a href="#model-card">{th ? "การ์ดโมเดล" : "Model card"}</a>
          <a href="#validation">{th ? "การตรวจสอบ" : "Validation"}</a>
          <a href="#pilot-readiness">{th ? "ความพร้อมนำร่อง" : "Pilot readiness"}</a>
        </nav>

        <div className={styles.consoleGrid}>
          <aside className={styles.runRail} aria-labelledby="published-runs-title">
            <div><p className="eyebrow">RUN CATALOG</p><h2 id="published-runs-title">{th ? "รันที่เผยแพร่" : "Published runs"}</h2></div>
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
                  <b>{run.run_id}</b>
                  <small>{run.dataset_mode.replaceAll("_", " ")} · {run.run_status.replaceAll("_", " ")}</small>
                </button>
              ))}
              {!hasGeoAiRun && (
                <article className={styles.futureRun}>
                  <span>GeoAI U-Net / FPN</span>
                  <b>{th ? "ยังไม่มีรันประเมินข้อมูลจริง" : "No qualified real-data run"}</b>
                  <small>{th ? "รอใบอนุญาต หน้ากากอ้างอิง และโพลิกอน holdout" : "Licensing, reference-mask, and immutable holdout gates remain open."}</small>
                </article>
              )}
            </div>
            <p className={styles.railGate}>
              <b>can_feed_decision_layer = {String(decisionEligible)}</b><br />
              {decisionEligible
                ? (th ? "มีรัน official_input ที่ผ่านเกณฑ์การส่งต่ออย่างชัดเจน" : "An official-input run explicitly passes promotion gates.")
                : (th ? "ไม่มีรัน official_input ที่ผ่านเกณฑ์การประมวลผลและการส่งต่อ" : "No official-input run passes both processing and promotion gates.")}
            </p>
          </aside>

          <div className={styles.consoleMain}>
            <div id="integration-proof">
              <StudioProofPanel language={language} modelRuns={data.model_runs} />
            </div>

            <section id="data-gates" className="studio-section" aria-labelledby="readiness-title">
              <div className="section-heading"><div><p className="eyebrow">02 · DATA GATES</p><h2 id="readiness-title">{th ? "ความพร้อมของข้อมูล" : "Data readiness"}</h2></div><span className="section-count">{blockedGateCount} {th ? "รายการบล็อก" : "blocked"}</span></div>
              <div className="table-scroll"><table className="readiness-table"><thead><tr><th>{th ? "การตรวจ" : "Gate"}</th><th>{th ? "แหล่งข้อมูล" : "Source"}</th><th>{th ? "สถานะ" : "State"}</th><th>{th ? "เหตุผล" : "Reason"}</th></tr></thead><tbody>{data.readiness.map((row) => <tr key={row.check_id}><td><code>{row.check_id}</code></td><td>{row.source}</td><td><span className={`readiness-state ${row.status}`}>{row.status}</span></td><td>{row.reason_blocked || (th ? "ผ่านการตรวจแบบสาธิต" : "Fixture check ready")}</td></tr>)}</tbody></table></div>
            </section>

            <section id="model-matrix" className="studio-section" aria-labelledby="model-matrix-title">
              <div className="section-heading"><div><p className="eyebrow">03 · MODEL MATRIX</p><h2 id="model-matrix-title">{th ? "เปรียบเทียบภายในขอบเขตหลักฐาน" : "Evidence-scoped comparison"}</h2></div><p>{th ? "เมตริกจาก fixture, weak label และข้อมูลจริงที่ผ่านเกณฑ์ห้ามเปรียบเทียบเป็นผลความแม่นยำเดียวกัน" : "Fixture, weak-label, and qualified real-data metrics are different evidence scopes and are not one accuracy leaderboard."}</p></div>
              <div className="table-scroll">
                <table className="readiness-table">
                  <thead><tr><th>Run</th><th>{th ? "ขอบเขต" : "Scope"}</th><th>IoU</th><th>F1 / Dice</th><th>{th ? "การตัดสินใจ" : "Decision"}</th></tr></thead>
                  <tbody>
                    {data.model_runs.map((run) => (
                      <tr key={run.run_id}>
                        <td><button type="button" className="download-manifest" onClick={() => setSelectedRunId(run.run_id)}>{familyLabel(run.model_family)}</button></td>
                        <td>{run.dataset_mode.replaceAll("_", " ")} · {run.processing_scope}</td>
                        <td>{formatNumber(run.validation_metrics.iou, language, 3)}</td>
                        <td>{formatNumber(run.validation_metrics.f1_dice, language, 3)}</td>
                        <td><span className={`feed-decision ${run.can_feed_decision_layer ? "yes" : "no"}`}>{String(run.can_feed_decision_layer)}</span></td>
                      </tr>
                    ))}
                    {!hasGeoAiRun && <tr><td>GeoAI U-Net / FPN</td><td>{th ? "ยังไม่รันบนข้อมูลจริงที่ผ่านเกณฑ์" : "Qualified real-data evaluation not run"}</td><td>—</td><td>—</td><td><span className="feed-decision no">false</span></td></tr>}
                  </tbody>
                </table>
              </div>
            </section>

            {selectedRun && <section id="model-card" className="studio-section model-detail" aria-labelledby="model-card-title">
              <div className="section-heading"><div><p className="eyebrow">04 · SELECTED MODEL CARD</p><h2 id="model-card-title">{selectedRun.run_id}</h2><p>{familyLabel(selectedRun.model_family)} · {selectedRun.dataset_mode.replaceAll("_", " ")} · {selectedRun.processing_scope}</p></div><button type="button" className="download-manifest" onClick={() => downloadText(`${selectedRun.run_id}-manifest.json`, safeManifest(selectedRun), "application/json")}>{th ? "ดาวน์โหลด manifest" : "Download manifest"}</button></div>
              <div className="model-detail-grid">
                <dl className="contract-list"><div><dt>Family</dt><dd>{familyLabel(selectedRun.model_family)}</dd></div><div><dt>Architecture</dt><dd>{selectedRun.architecture ?? "Unavailable"}</dd></div><div><dt>Channels</dt><dd>{selectedRun.num_channels ?? "—"} · {selectedRun.channel_names.join(", ")}</dd></div><div><dt>Preprocessing</dt><dd>{selectedRun.preprocessing.method}</dd></div><div><dt>Band transforms</dt><dd>{selectedRun.preprocessing.transforms.length > 0 ? selectedRun.preprocessing.transforms.map((item) => `${item.name}: ${item.physical_min}…${item.physical_max} ${item.units}`).join("; ") : "Not published for this legacy run"}</dd></div><div><dt>Transform receipt</dt><dd>{selectedRun.preprocessing.sidecar_sha256 ?? "Unavailable"}</dd></div><div><dt>Input roles</dt><dd>{selectedRun.input_manifest_rows.map((row) => row.role).join(", ")}</dd></div><div><dt>Feature receipt</dt><dd>{selectedRun.encoded_feature_sha256 ?? "Unavailable"}</dd></div><div><dt>Reference mask</dt><dd>{selectedRun.reference_mask_id} · {selectedRun.reference_mask_status}</dd></div><div><dt>Mask receipt</dt><dd>{selectedRun.reference_mask_sha256 ?? "Unavailable"}</dd></div><div><dt>Tile manifest</dt><dd>{selectedRun.prepared_tile_manifest_sha256 ?? "Not prepared"}</dd></div><div><dt>Spatial holdout</dt><dd>{selectedRun.spatial_holdout_ids.length > 0 ? selectedRun.spatial_holdout_ids.join(", ") : "Not declared"}</dd></div><div><dt>Spatial partitions</dt><dd>{selectedRun.spatial_partitions.length > 0 ? selectedRun.spatial_partitions.map((item) => `${item.spatial_group_id} (${item.split})`).join(", ") : "Not published"}</dd></div><div><dt>Output workspace</dt><dd>{selectedRun.external_output_workspace}</dd></div></dl>
                <div className="metric-panel"><h3>{th ? "เมตริกตามขอบเขตหลักฐาน" : "Evidence-scoped metrics"}</h3>{METRICS.map(([key, label]) => <div className="metric-row" key={key}><span>{label}</span><b>{formatNumber(selectedRun.validation_metrics[key], language, 3)}</b></div>)}<article className={selectedRun.can_feed_decision_layer ? "eligible-reason" : "blocked-reason"}><b>{selectedRun.can_feed_decision_layer ? (th ? "สถานะการส่งต่อ" : "Promotion state") : (th ? "เหตุผลที่บล็อก" : "Reason blocked")}</b><p>{selectedRun.can_feed_decision_layer ? (th ? "manifest ระบุว่าผ่านเกณฑ์การส่งต่อทั้งหมด" : "The manifest declares all decision-feed gates passed.") : selectedRun.reason_blocked}</p></article></div>
              </div>
            </section>}

            <section id="validation" className="studio-section" aria-labelledby="errors-title">
              <div className="section-heading"><div><p className="eyebrow">05 · VALIDATION</p><h2 id="errors-title">{th ? "หมวดความผิดพลาด" : "Error categories"}</h2></div></div>
              <div className="error-grid">{data.error_categories.map((item) => <article key={item.category}><span>{item.status}</span><h3>{item.category.replaceAll("_", " ")}</h3><p>{item.note}</p></article>)}</div>
            </section>

            <div id="pilot-readiness"><PilotReadinessPanel readiness={data.pilot_readiness} language={language} surface="studio" /></div>
          </div>
        </div>

        <footer className="studio-footer"><p>{data.status.dataset_mode === "fixture_demo" ? (th ? "ไม่มีพาธส่วนตัว ไฟล์ภาพต้นฉบับ หรือน้ำหนักแบบจำลองในชุดสาธิตนี้" : "This fixture bundle contains no private paths, source imagery, or model weights.") : (th ? "หน้าจอนี้แสดงเฉพาะ manifest สาธารณะที่ตัดพาธส่วนตัวออกแล้ว" : "This screen exposes only public manifests with private paths removed.")}</p><a href="/command/">{th ? "กลับไปที่ศูนย์บัญชาการ →" : "Open planning command center →"}</a></footer>
      </div>
    </main>
  );
}
