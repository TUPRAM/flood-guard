import type { Language } from "@/lib/types";

import styles from "./geoai-real-panel.module.css";

/** Where the historical research report, with its research scores and classes, is kept: Studio's archive. */
export const HISTORICAL_RESEARCH_REPORT_ROUTE = "/studio/archive/mae-sai-geoai/";
const CURRENT_BRIEF_HREF = "/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024";

/**
 * The notice that stands on Command where the research score table was (owner decision of 4 Oct 2026, R17). The
 * table, with its per-subdistrict research FPPS and A–E classes, predates the signed protocol and is shown only in
 * Studio's archive, labelled as historical research. This notice loads nothing and shows no score.
 */
export function ResearchReportNotice({ language = "en" }: { language?: Language }) {
  const th = language === "th";
  return (
    <section className={`studio-section ${styles.panel}`} aria-labelledby="research-report-notice-title" data-research-report-notice="true">
      <h2 id="research-report-notice-title">{th ? "รายงานวิจัยแม่สายฉบับก่อน: เก็บไว้ในคลังของ Studio" : "Earlier Mae Sai research report: kept in Studio's archive"}</h2>
      <p className={styles.detail}>
        {th
          ? "คะแนนและชั้นการดำเนินการในงานวิจัยเดิมไม่ใช่ลำดับความสำคัญในการรับมือเหตุการณ์ที่ได้รับการยอมรับ ตารางคะแนนวิจัยรายตำบลไม่แสดงในหน้าการวางแผนอีกต่อไป และเก็บไว้เป็นงานวิจัยย้อนหลังในคลังของ Studio เท่านั้น"
          : "Earlier research scores and classes are not accepted event-response priorities. The per-subdistrict research score table is no longer shown on Planning; it is kept, as historical research, only in Studio's archive."}
      </p>
      <p className={styles.detail}>
        <a href={HISTORICAL_RESEARCH_REPORT_ROUTE}>{th ? "เปิดรายงานวิจัยย้อนหลังในคลังของ Studio" : "Open the historical research report in Studio's archive"}</a>
        {" · "}
        <a href={CURRENT_BRIEF_HREF}>{th ? "เปิดบทสรุปหลักฐานปัจจุบัน" : "Open the current evidence brief"}</a>
      </p>
    </section>
  );
}
