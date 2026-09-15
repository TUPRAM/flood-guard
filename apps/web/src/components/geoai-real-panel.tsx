"use client";

import { useEffect, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
import { formatConfidence } from "@/lib/format";
import type { Language } from "@/lib/types";

import styles from "./geoai-real-panel.module.css";

interface GeoaiComponent {
  letter: string;
  name: string;
  book: string;
  metric: string;
  detail: string;
  input: string;
  output: string;
}

interface GeoaiExtraMethod {
  letter: string;
  name: string;
  book: string;
  metric: string;
  detail: string;
  image: string | null;
  narratives?: Record<string, Record<string, string>>;
}

interface GeoaiSubdistrict {
  id: string;
  name: string;
  flood_likelihood: number;
  exposure: number;
  fpps: number;
  action: string;
  confidence: string;
  population?: number | null;
  context_source?: string;
  narrative_en?: string | null;
  narrative_th?: string | null;
}

interface GeoaiRealBundle {
  data_mode: string;
  study_area: string;
  generated_at: string;
  evaluation_protocol?: {
    scale_anchors?: Record<string, string>;
  };
  sources: Record<string, string>;
  headline: {
    sar_flood_pct: number;
    sar_pre: string;
    sar_post: string;
    unet_iou: number | null;
    unet_f1: number | null;
    unet_metric_role?: string;
    susc_auc: number;
    susc_auc_jrc: number;
    buildings: number;
    exposed: number;
  };
  components: GeoaiComponent[];
  additional_methods?: GeoaiExtraMethod[];
  subdistricts: GeoaiSubdistrict[];
  limitations: string[];
}

const ACTION_LABEL: Record<string, { en: string; th: string }> = {
  A: { en: "Protect lives", th: "ปกป้องชีวิต" },
  B: { en: "Keep routes open", th: "รักษาเส้นทาง" },
  C: { en: "Essential services", th: "บริการจำเป็น" },
  D: { en: "Build resilience", th: "เสริมความพร้อม" },
  E: { en: "Monitor & verify", th: "เฝ้าระวัง" },
};

export function GeoaiRealPanel({
  language = "en",
  variant = "studio",
  planningDataVersion,
  archiveRecord,
}: {
  language?: Language;
  variant?: "studio" | "command" | "archive";
  planningDataVersion?: string;
  archiveRecord?: { href: string; sha256: string };
}) {
  const th = language === "th";
  const [bundle, setBundle] = useState<GeoaiRealBundle | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    fetch(archiveRecord?.href ?? "/geoai/mae-sai-real.json", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(String(response.status));
        const bytes = await response.arrayBuffer();
        if (archiveRecord) {
          const hash = await crypto.subtle.digest("SHA-256", bytes);
          const actual = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
          if (actual !== archiveRecord.sha256) throw new Error("Historical report checksum mismatch");
        }
        return JSON.parse(new TextDecoder().decode(bytes)) as GeoaiRealBundle;
      })
      .then((data: GeoaiRealBundle) => {
        if (active) setBundle(data);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [archiveRecord]);

  if (failed) {
    return variant === "archive" ? <p role="alert">Historical report unavailable. The archived record could not be loaded or verified.</p> : null;
  }

  const h = bundle?.headline;
  const ranked = bundle ? [...bundle.subdistricts].sort((a, b) => b.fpps - a.fpps) : [];

  return (
    <section
      className={`studio-section ${styles.panel}`}
      aria-labelledby="geoai-real-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {variant === "command"
              ? th
                ? "รายงานวิจัย GeoAI · แยกจากการจัดลำดับเพื่อวางแผน"
                : "GEOAI RESEARCH · SEPARATE FROM PLANNING RANKING"
              : th
                ? "รายงานวิจัย GeoAI · ข้อมูลย้อนหลัง"
                : "GEOAI RESEARCH · HISTORICAL EVIDENCE"}
          </p>
          <h2 id="geoai-real-title">
            {th
              ? "รายงานวิจัย GeoAI — แม่สาย ก.ย. 2567"
              : "GeoAI research report — Mae Sai, Sept 2024"}
          </h2>
        </div>
        <div className={styles.pills}>
          <StatePill tone="caution">
            {th ? "เพื่อรายงานเท่านั้น" : "Report only"}
          </StatePill>
          {!bundle && <StatePill tone="info">{th ? "กำลังโหลด" : "Loading"}</StatePill>}
        </div>
      </div>

      <EvidenceNotice
        tone="caution"
        title={th ? "ผลวิเคราะห์แยกต่างหาก ไม่ใช้กำหนดการดำเนินการ" : "Separate analysis; does not determine planning actions"}
      >
        {th
          ? "รายงานวิจัยจากข้อมูลย้อนหลังนี้ใช้ข้อมูลนำเข้าและสมมติฐานต่างจากมุมมองการวางแผน คะแนน FPPS ชั้น A–E และความเชื่อมั่นของแบบจำลองในรายงานนี้ไม่ใช้กำหนดลำดับ สีแผนที่ หรือข้อเสนอการดำเนินการในมุมมองการวางแผน ไม่ใช่คำเตือนภัยอย่างเป็นทางการ"
          : "This historical research report uses different inputs and assumptions from the planning view. Its FPPS, A–E classes and model confidence do not set the planning workspace ranking, map colors or recommended actions. Not an official warning."}
      </EvidenceNotice>

      {variant === "command" && planningDataVersion && (
        <p className={styles.detail}>
          {th ? "รุ่นข้อมูลที่ใช้ในลำดับและหลักฐานพื้นที่ด้านบน" : "Data version used by the ranking and area evidence above"}: {planningDataVersion}
        </p>
      )}

      {h && (
        <div className={styles.chips}>
          <span className={styles.chip}>
            <b>SAR flood extent</b> {h.sar_flood_pct}%
          </span>
          <span className={styles.chip}>
            <b>{variant === "archive" ? "U-Net teacher-agreement IoU" : "U-Net water IoU"}</b>{" "}
            {h.unet_iou === null || h.unet_iou === undefined
              ? th
                ? "รอการประเมินซ้ำ"
                : "pending re-run"
              : `${h.unet_iou} (${h.unet_metric_role ?? "test"})`}
          </span>
          <span className={styles.chip}>
            <b>Susceptibility AUC</b> {h.susc_auc}
          </span>
          <span className={styles.chip}>
            <b>OSM buildings</b> {h.buildings}
          </span>
          <span className={styles.chip}>
            <b>Pre → post</b> {h.sar_pre} → {h.sar_post}
          </span>
        </div>
      )}

      {bundle && (
        <>
          <div className={styles.models}>
            {bundle.components.map((c) => (
              <article key={c.letter} className={styles.model}>
                {variant === "archive" && c.letter === "B" && <p className={styles.detail}><strong>Teacher agreement / distillation fidelity.</strong> This score compares with an OmniWaterMask teacher. It does not measure water accuracy in Mae Sai; the original run is flagged degenerate.</p>}
                <div className={styles.modelHead}>
                  <span className={styles.letter}>{c.letter}</span>
                  <div>
                    <h3>{c.name}</h3>
                    <p className={styles.book}>{c.book}</p>
                  </div>
                </div>
                <div className={styles.gallery}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.input} alt={`${c.name} input`} loading="lazy" />
                  <span className={styles.arrow} aria-hidden="true">
                    →
                  </span>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.output} alt={`${c.name} AI output`} loading="lazy" />
                </div>
                <p className={styles.metric}>{c.metric}</p>
                <p className={styles.detail}>{c.detail}</p>
              </article>
            ))}
          </div>

          {bundle.additional_methods && bundle.additional_methods.length > 0 && (
            <>
              <h3 className={styles.subhead}>
                {th ? "วิธี AI เพิ่มเติม" : "Additional AI methods (baseline + roadmap, executed)"}
              </h3>
              <div className={styles.extras}>
                {bundle.additional_methods.map((x) => (
                  <article key={x.letter + x.name} className={styles.extra}>
                    <div className={styles.extraHead}>
                      <span className={styles.letter}>{x.letter}</span>
                      <div>
                        <h4>{x.name}</h4>
                        <p className={styles.book}>{x.book}</p>
                      </div>
                    </div>
                    {x.image && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={x.image} alt={x.name} loading="lazy" className={styles.extraImg} />
                    )}
                    <p className={styles.metric}>{x.metric}</p>
                    <p className={styles.detail}>{x.detail}</p>
                    {x.narratives && (
                      <ul className={styles.captions}>
                        {Object.entries(x.narratives).map(([name, byLanguage]) => (
                          <li key={name}>
                            <b>{name}:</b>{" "}
                            {byLanguage[th ? "th" : "en"] ?? byLanguage.en}
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                ))}
              </div>
            </>
          )}

          <h3 className={styles.subhead}>
            {th
              ? "ผลรายตำบลเพื่อการวิจัยเท่านั้น"
              : "Sub-district research results — report only"}
          </h3>
          <p id="geoai-research-confidence" className={styles.detail}>
            {th
              ? "ความเชื่อมั่นของแบบจำลองในรายงานนี้อิงความสอดคล้องระหว่างสัญญาณ SAR และภูมิประเทศ รวมถึงความครบถ้วนของข้อมูล ไม่ใช่ความเชื่อมั่นของหลักฐานในมุมมองการวางแผน"
              : "Model confidence here reflects agreement between SAR and terrain signals, with data-completeness checks. It is separate from the evidence confidence in the planning view."}
          </p>
          <div className={styles.tableWrap}>
            <table className={styles.table} aria-describedby="geoai-research-confidence">
              <caption className={styles.detail}>
                {th ? "คะแนนและชั้นจากงานวิจัย ไม่ใช่ข้อเสนอการดำเนินการ" : "Research scores and classes; not action recommendations"}
              </caption>
              <thead>
                <tr>
                  <th>{th ? "ตำบล" : "Sub-district"}</th>
                  <th>{th ? "โอกาสน้ำท่วม" : "Flood lik."}</th>
                  <th>{th ? "ความเสี่ยง" : "Exposure"}</th>
                  <th>{th ? "FPPS งานวิจัย" : "Research FPPS"}</th>
                  <th>{th ? "ชั้นจากงานวิจัย" : "Research class"}</th>
                  <th>{th ? "ความเชื่อมั่นแบบจำลอง" : "Model confidence"}</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td>{s.flood_likelihood}</td>
                    <td>{s.exposure}</td>
                    <td className={styles.fpps}>{s.fpps}</td>
                    <td>
                      <span
                        className={`${styles.action} ${styles[`a${s.action}`]}`}
                        title={
                          th ? ACTION_LABEL[s.action]?.th : ACTION_LABEL[s.action]?.en
                        }
                      >
                        {s.action}
                      </span>
                    </td>
                    <td className={styles.conf}>{formatConfidence(s.confidence, language)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className={styles.more}>
            <summary>{th ? "แหล่งข้อมูลและข้อจำกัด" : "Data sources & limitations"}</summary>
            <div className={styles.sources}>
              <div>
                <b>{th ? "แหล่งรายงานวิจัย" : "Research report source"}</b>
                <a href="/geoai/mae-sai-real.json">mae-sai-real.json</a>
              </div>
              {bundle.evaluation_protocol?.scale_anchors && (
                <div>
                  <b>{th ? "รุ่นเกณฑ์คะแนนงานวิจัย" : "Research scoring anchor versions"}</b>
                  {Object.values(bundle.evaluation_protocol.scale_anchors).join(" · ")}
                </div>
              )}
              {Object.entries(bundle.sources).map(([k, v]) => (
                <div key={k}>
                  <b>{k}</b> {v}
                </div>
              ))}
            </div>
            <ul className={styles.limits}>
              {bundle.limitations.map((l, i) => (
                <li key={i}>{l}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
