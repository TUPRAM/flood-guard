"use client";

import { useEffect, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
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
}: {
  language?: Language;
  variant?: "studio" | "command";
}) {
  const th = language === "th";
  const [bundle, setBundle] = useState<GeoaiRealBundle | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetch("/geoai/mae-sai-real.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: GeoaiRealBundle) => {
        if (active) setBundle(data);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  if (failed) {
    return null;
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
                ? "ชั้นข้อมูล GeoAI (ข้อมูลจริง)"
                : "GEOAI LAYER · REAL DATA"
              : th
                ? "หลักฐาน GeoAI จากข้อมูลจริง"
                : "GEOAI · REAL OBSERVED DATA"}
          </p>
          <h2 id="geoai-real-title">
            {th
              ? "ผลแบบจำลอง GeoAI จริง — แม่สาย ก.ย. 2567"
              : "Real GeoAI results — Mae Sai, Sept 2024"}
          </h2>
        </div>
        <div className={styles.pills}>
          <StatePill tone={bundle ? "ready" : "info"}>
            {bundle
              ? th
                ? "ข้อมูลจริง"
                : "Real data"
              : th
                ? "กำลังโหลด"
                : "Loading"}
          </StatePill>
        </div>
      </div>

      <EvidenceNotice
        tone="caution"
        title={th ? "ขอบเขตของผลนี้" : "Scope of this result"}
      >
        {th
          ? "คำนวณจากภาพดาวเทียมจริง (Sentinel-1/2, Copernicus DEM) และชั้นข้อมูลหน่วยงานไทยจริง สำหรับการวางแผนเท่านั้น ไม่ใช่คำเตือนภัยอย่างเป็นทางการ"
          : "Computed from real satellite imagery (Sentinel-1/2, Copernicus DEM) and real Thai authoritative layers. For planning only — not an official warning."}
      </EvidenceNotice>

      {h && (
        <div className={styles.chips}>
          <span className={styles.chip}>
            <b>SAR flood extent</b> {h.sar_flood_pct}%
          </span>
          <span className={styles.chip}>
            <b>U-Net water IoU</b>{" "}
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
              ? "ลำดับความสำคัญรายตำบล (AI ขับเคลื่อน 55% ของคะแนน)"
              : "Sub-district priority — AI drives 55% of the score"}
          </h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{th ? "ตำบล" : "Sub-district"}</th>
                  <th>{th ? "โอกาสน้ำท่วม" : "Flood lik."}</th>
                  <th>{th ? "ความเสี่ยง" : "Exposure"}</th>
                  <th>FPPS</th>
                  <th>{th ? "การกระทำ" : "Action"}</th>
                  <th>{th ? "ความเชื่อมั่น" : "Confidence"}</th>
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
                    <td className={styles.conf}>{s.confidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className={styles.more}>
            <summary>{th ? "แหล่งข้อมูลและข้อจำกัด" : "Data sources & limitations"}</summary>
            <div className={styles.sources}>
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
