"use client";

import { useEffect, useState } from "react";

import { EvidenceNotice } from "@/components/evidence-notice";
import { StatePill } from "@/components/state-pill";
import type { Language } from "@/lib/types";
import { parseGeoaiResearchBundle, type GeoaiResearchBundle } from "@/lib/geoai-research-bundle";

import styles from "./geoai-real-panel.module.css";

const briefHref = "/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024";

export function GeoaiRealPanel({
  language = "en",
  variant = "studio",
}: {
  language?: Language;
  variant?: "studio" | "command";
}) {
  const th = language === "th";
  const [bundle, setBundle] = useState<GeoaiResearchBundle | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (variant === "command") return;
    let active = true;
    fetch("/geoai/mae-sai-real.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: unknown) => {
        const checked = parseGeoaiResearchBundle(data);
        if (active) setBundle(checked);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [variant]);

  if (variant === "command") return <section className={`studio-section ${styles.panel}`} aria-label={th ? "ขอบเขตผลการวิจัยเดิม" : "Archived research scope"}>
    <h2>{th ? "ผลวิจัยแม่สายที่เก็บไว้เพื่อเปรียบเทียบ" : "Archived Mae Sai research comparator"}</h2>
    <p>{th ? "คะแนนและชั้นการดำเนินการในงานวิจัยเดิมยังไม่ผ่านการยอมรับเพื่อจัดอันดับรับมือเหตุการณ์ ดูสถานะหลักฐานและการทดลองปัจจุบันในบทสรุป" : "Earlier research scores and classes are not accepted event-response priorities. The current brief explains evidence status and intervention experiments."}</p>
    <a href={briefHref}>{th ? "เปิดบทสรุปหลักฐานปัจจุบัน" : "Open the current evidence brief"}</a>
    <a href="/studio/#geoai-real-title">{th ? "ตรวจสอบงานวิจัยเดิม" : "Inspect the research archive in Studio"}</a>
  </section>;

  return <GeoaiResearchContent bundle={bundle} th={th} failed={failed} />;
}

/** Display only a parsed archive, separately from the accepted decision brief. */
export function GeoaiResearchContent({ bundle, th, failed = false }: { bundle: GeoaiResearchBundle | null; th: boolean; failed?: boolean }) {
  const h = bundle?.headline;
  const rows = bundle?.subdistricts ?? [];

  return (
    <section
      className={`studio-section ${styles.panel}`}
      aria-labelledby="geoai-real-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {th ? "งานวิจัยเดิม · ใช้ตรวจสอบเท่านั้น" : "RESEARCH ARCHIVE · REPORT ONLY"}
          </p>
          <h2 id="geoai-real-title">
            {th
              ? "ผลวิจัยแม่สายที่เก็บไว้เพื่อเปรียบเทียบ"
              : "Archived GeoAI comparator — Mae Sai"}
          </h2>
        </div>
        <div className={styles.pills}>
          <StatePill tone="caution">
            {th ? "ยังไม่ยอมรับเพื่อการตัดสินใจ" : "Not accepted for decisions"}
          </StatePill>
        </div>
      </div>

      <EvidenceNotice
        tone="caution"
        title={th ? "แยกงานวิจัยเดิมออกจากข้อเสนอแนะปัจจุบัน" : "Earlier arithmetic is not an accepted action recommendation"}
      >
        {th
          ? "ชุดวิจัยนี้ใช้ภาพและข้อมูลจริง แต่ผลประมาณการไม่ใช่ขอบเขตน้ำท่วมที่ผ่านการตรวจสอบ และไม่ได้รับอนุญาตให้ป้อนชั้นการตัดสินใจ คะแนนหรือชั้น D/E เดิมไม่เปลี่ยนสถานะ FPPS และจำนวนผู้ได้รับผลกระทบที่ยังไม่พร้อมในบทสรุปปัจจุบัน"
          : "This archive uses real inputs, but its estimates are not validated flood observations and cannot feed the decision layer. Its earlier scores or D/E classes do not replace the unavailable accepted FPPS and flood-affected population in the current brief."}
      </EvidenceNotice>
      <a href={briefHref}>{th ? "เปิดบทสรุปหลักฐานปัจจุบัน" : "Open the current evidence brief"}</a>
      {failed ? <p role="status">{th ? "ไม่สามารถยืนยันชุดวิจัยเดิมได้ จึงไม่แสดงผลตัวเลข" : "The archive could not be verified. Its numerical results are unavailable."}</p> : !bundle ? <p role="status">{th ? "กำลังโหลดชุดวิจัยเดิม" : "Loading the research archive."}</p> : null}

      {bundle && <details className={styles.more}>
        <summary>{th ? "เปิดบันทึกวิธีและตัวเลขเดิม (ไม่ใช่ผลยอมรับสำหรับเหตุการณ์)" : "Inspect archived methods and arithmetic (not accepted event results)"}</summary>
        <p>{th ? "วันที่ที่บันทึกในชุดวิจัย" : "Timestamp recorded in the archive"}: <time dateTime={bundle.generated_at}>{bundle.generated_at}</time> · {bundle.study_area}</p>
        <p>{th ? "เวลาในบันทึกนี้ไม่ใช่เวลาตรวจสอบภาคสนามหรือหลักฐานว่าข้อมูลทั้งหมดมาจากช่วงเดียวกัน" : "This recorded timestamp does not establish field validation or a common observation period for all inputs."}</p>
      {h && (
        <div className={styles.chips}>
          <span className={styles.chip}>
            <b>{th ? "สัดส่วนตามการประมาณ SAR เดิม" : "Archived SAR candidate fraction"}</b> {h.sar_flood_pct}%
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
                {th ? "บันทึกวิธีวิจัยเพิ่มเติม" : "Additional method records"}
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
              ? "ตัวเลขรายตำบลจากงานวิจัยเดิม · ไม่ใช่ลำดับที่ยอมรับ"
              : "Archived subdistrict arithmetic · no accepted ranking"}
          </h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{th ? "ตำบล" : "Sub-district"}</th>
                  <th>{th ? "องค์ประกอบน้ำท่วมเดิม" : "Archived flood component"}</th>
                  <th>{th ? "องค์ประกอบการเปิดรับเดิม" : "Archived exposure component"}</th>
                  <th>{th ? "คะแนนเดิม" : "Archived score"}</th>
                  <th>{th ? "ชั้นเดิม" : "Archived class"}</th>
                  <th>{th ? "ความเชื่อมั่นที่บันทึกไว้" : "Recorded confidence"}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td>{s.flood_likelihood}</td>
                    <td>{s.exposure}</td>
                    <td>{s.fpps}</td>
                    <td>{s.action}</td>
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
      </details>}
    </section>
  );
}
