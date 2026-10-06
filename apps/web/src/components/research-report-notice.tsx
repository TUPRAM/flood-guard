"use client";

import type { Language } from "@/lib/types";
import { useOnline } from "@/lib/use-online";

import styles from "./geoai-real-panel.module.css";

/** Where the historical research report, with its research scores and classes, is kept: Studio's archive. */
export const HISTORICAL_RESEARCH_REPORT_ROUTE = "/studio/archive/mae-sai-geoai/";
const CURRENT_BRIEF_HREF = "/studio/brief/?aoi=aoi-01_mae_sai_core&event=mae_sai_2024";

/**
 * The notice that stands on Command where the GeoAI research report was (owner decision of 4 Oct 2026, R17). The
 * report's table, with its per-subdistrict research FPPS and A–E classes, predates the signed protocol and is shown
 * only in Studio's archive, labelled as historical research. This notice loads nothing and shows no score.
 *
 * `retainedRanking` is for the map workspace, which keeps its own ranking, scores and classes from the planning
 * bundle: there the notice says so, and that those values are not the report's. The workspace is the default
 * Planning page at /command/ (owner request of 5 Oct 2026, R19; it was at /command/archive/ before). The planning
 * overview at /command/ver2/ shows no such ranking and uses the notice without it.
 *
 * The report's page is not part of the offline installation (its images alone would take the installation over its
 * 12 MB budget), so without a connection the link is replaced by a sentence that says it needs one.
 */
export function ResearchReportNotice({ language = "en", retainedRanking = false }: { language?: Language; retainedRanking?: boolean }) {
  const th = language === "th";
  const online = useOnline();
  return (
    <section className={`studio-section ${styles.panel}`} aria-labelledby="research-report-notice-title" data-research-report-notice="true">
      <h2 id="research-report-notice-title">{th ? "รายงานวิจัยแม่สายฉบับก่อน: เก็บไว้ในคลังของ Studio" : "Earlier Mae Sai research report: kept in Studio's archive"}</h2>
      <p className={styles.detail}>
        {th
          ? "คะแนนและชั้นการดำเนินการในงานวิจัยเดิมไม่ใช่ลำดับความสำคัญในการรับมือเหตุการณ์ที่ได้รับการยอมรับ ตารางคะแนนของรายงาน GeoAI แม่สายฉบับก่อน ซึ่งมีคะแนนและชั้นงานวิจัยของแต่ละตำบล ไม่แสดงในหน้าการวางแผน และเก็บไว้เป็นงานวิจัยย้อนหลังในคลังของ Studio เท่านั้น"
          : "Earlier research scores and classes are not accepted event-response priorities. The score table of the earlier Mae Sai GeoAI report, with a research score and class for each subdistrict, is not shown on Planning; it is kept, as historical research, only in Studio's archive."}
      </p>
      {retainedRanking ? (
        <p className={styles.detail} data-research-retained-ranking="true">
          {th
            ? "ลำดับ คะแนน FPPS และชั้นของตำบลที่ยังแสดงในหน้านี้เป็นผลเปรียบเทียบงานวิจัยเดิมอีกชุดหนึ่ง ไม่ใช่ตารางของรายงานดังกล่าว ค่าจึงต่างจากในรายงาน และไม่ใช่ลำดับความสำคัญที่ได้รับการยอมรับเช่นกัน"
            : "The ranking, FPPS and classes still shown on this page are a separate retained research comparison, not that report's table. Their values differ from the report's, and they are not accepted priorities either."}
        </p>
      ) : null}
      <p className={styles.detail}>
        {online
          ? <a href={HISTORICAL_RESEARCH_REPORT_ROUTE}>{th ? "เปิดรายงานวิจัยย้อนหลังในคลังของ Studio" : "Open the historical research report in Studio's archive"}</a>
          : <span data-research-report-offline="true">{th
            ? "รายงานวิจัยย้อนหลังในคลังของ Studio ต้องใช้การเชื่อมต่อ ไม่ได้บันทึกไว้ในอุปกรณ์นี้"
            : "The historical research report in Studio's archive needs a connection; it is not saved on this device"}</span>}
        {" · "}
        <a href={CURRENT_BRIEF_HREF}>{th ? "เปิดบทสรุปหลักฐานปัจจุบัน" : "Open the current evidence brief"}</a>
      </p>
    </section>
  );
}
