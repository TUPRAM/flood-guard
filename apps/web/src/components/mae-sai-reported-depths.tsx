"use client";

import { formatDateWithYear, type Language, type ReportedDepths } from "@/lib/flood-timeline";
import {
  REPORTED_DEPTH_APPLIES,
  REPORTED_DEPTH_BASES,
  REPORTED_DEPTH_COPY,
  REPORTED_DEPTH_STATUSES,
  locationConfidenceText,
  reportedDepthBasis,
  reportedDepthCountedText,
  reportedDepthOutcome,
  reportedDepthSharedText,
  reportedDepthStatementTallyText,
  reportedDepthStatusText,
  reportedDepthTallyText,
  reportedDepthText,
} from "@/lib/flood-timeline-reported-depths";

import styles from "./mae-sai-flood-timeline.module.css";

/** A speech bubble with two wave lines, in a 24-unit box: a report someone gave, never a measurement or a shelter. */
export const REPORTED_DEPTH_PATH = "M4.5 2.5h15a2.5 2.5 0 0 1 2.5 2.5v9.5a2.5 2.5 0 0 1-2.5 2.5h-8.2L6 21.5V17H4.5A2.5 2.5 0 0 1 2 14.5V5a2.5 2.5 0 0 1 2.5-2.5z";
export const REPORTED_DEPTH_WAVES = "M5.5 8.2c1.6-1.3 3.2-1.3 4.8 0s3.2 1.3 4.8 0 2.2-1.1 3.4-.6M5.5 12.2c1.6-1.3 3.2-1.3 4.8 0s3.2 1.3 4.8 0 2.2-1.1 3.4-.6";
/** The marker's markup on the map (Leaflet divIcon). */
export const REPORTED_DEPTH_ICON = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="${REPORTED_DEPTH_PATH}"/><path d="${REPORTED_DEPTH_WAVES}" fill="none" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/></svg>`;
/** A marker holding more than one place record shows how many in a badge (the hover title and popup list them). */
export const reportedDepthIconHtml = (records: number) => (records > 1 ? `${REPORTED_DEPTH_ICON}<b aria-hidden="true">${records}</b>` : REPORTED_DEPTH_ICON);
/**
 * The marker's box: 28 px, larger than the 22 px bubble so the hit target is at least 24 px. The anchor is the bubble's
 * tail (the report's point); the popup opens just above the bubble.
 */
export const REPORTED_DEPTH_ICON_BOX = { iconSize: [28, 28] as [number, number], iconAnchor: [9, 23] as [number, number], popupAnchor: [5, -18] as [number, number] };
/** Markers whose tails lie closer than this on screen (px) are drawn as one marker holding all their place records. */
export const REPORTED_DEPTH_GROUP_PX = 30;

/** The marker as a key (legend and layer toggle). */
export function ReportedDepthSwatch() {
  return (
    <i className={styles.legendReportedDepth} aria-hidden="true">
      <svg viewBox="0 0 24 24" width="15" height="15" focusable="false"><path d={REPORTED_DEPTH_PATH} /><path d={REPORTED_DEPTH_WAVES} fill="none" stroke="#fff" strokeWidth={1.5} strokeLinecap="round" /></svg>
    </i>
  );
}

/** Legend entry while the layer is on: news reports, not surveyed. */
export function ReportedDepthLegend({ language }: { language: Language }) {
  return (
    <div data-testid="reported-depth-legend">
      <strong>{REPORTED_DEPTH_COPY.title[language]}</strong>
      <ul>
        <li><ReportedDepthSwatch />{REPORTED_DEPTH_COPY.legend[language]}</li>
      </ul>
    </div>
  );
}

/**
 * The reported depths in "Sources, assumptions and limits": the status (reported, anecdotal, not surveyed), what was
 * counted (place records, statements, articles), the use rule (a consistency check, never a validation, never used to
 * tune the model), how the model is read, the counts per outcome in a small table (outcomes as rows, so it fits a
 * phone), the same counts once per statement and the statements recorded at several places, the location sensitivity,
 * the likely causes where the model is dry or shallower, the data file's assumptions, and every place record with its
 * place, depth, time, location confidence, outcome and source link, as a plain list.
 */
export function ReportedDepthsSources({ block, language }: { block: ReportedDepths; language: Language }) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const counts = block.counts;
  const located = block.reports.filter((report) => report.point);
  const points = new Set(located.map((report) => `${report.point!.lat},${report.point!.lon}`)).size;
  return (
    <>
      <h3 id="mae-sai-reported-depths">{REPORTED_DEPTH_COPY.title[language]}</h3>
      <div data-testid="reported-depths-sources">
        <p data-testid="reported-depths-counted">
          <strong>{REPORTED_DEPTH_COPY.status[language]}</strong>{" "}
          {t(
            `${reportedDepthCountedText(block.counted, "en")} of 10–13 Sep 2024 give a depth at a named place. A statement that names several communities is recorded once per community, so the counts below are of place records, with each statement counted once beside them. Each record is paraphrased and linked to its article. ${located.length} records have a point on the map (${points} points; location confidence medium or high), drawn by the layer "${REPORTED_DEPTH_COPY.toggle.en}" under “Map layers”, which is off until you turn it on.`,
            `${reportedDepthCountedText(block.counted, "th")} ระหว่างวันที่ 10–13 ก.ย. 2567 (2024) ระบุความลึก ณ สถานที่ที่มีชื่อ ข้อความที่กล่าวถึงหลายชุมชนบันทึกแยกหนึ่งรายการต่อหนึ่งชุมชน ตัวเลขด้านล่างจึงนับเป็นรายการตามสถานที่ และแสดงการนับหนึ่งครั้งต่อหนึ่งข้อความไว้ด้วย แต่ละรายการเรียบเรียงใหม่และมีลิงก์ไปยังข่าวต้นทาง มี ${located.length} รายการที่มีจุดบนแผนที่ (${points} จุด ความเชื่อมั่นของตำแหน่งปานกลางหรือสูง) แสดงด้วยชั้นข้อมูล “${REPORTED_DEPTH_COPY.toggle.th}” ใน “ชั้นแผนที่” ซึ่งปิดอยู่จนกว่าจะเปิด`,
          )}
        </p>
        <p data-testid="reported-depths-use">{block.use_rule[language]}</p>
        <p className={styles.muted}>{block.comparison_rule[language]}</p>
        <div className={styles.tableScroll} data-testid="reported-depth-counts-scroll">
          <table className={`${styles.viirsTable} ${styles.depthCounts}`} data-testid="reported-depth-counts">
            <caption className={styles.srOnly}>{REPORTED_DEPTH_COPY.tableCaption[language]}</caption>
            <thead>
              <tr>
                <th scope="col">{REPORTED_DEPTH_COPY.outcome[language]}</th>
                {REPORTED_DEPTH_BASES.map((basis) => <th key={basis} scope="col" data-basis={basis}>{reportedDepthBasis(basis, language)}</th>)}
              </tr>
            </thead>
            <tbody>
              {REPORTED_DEPTH_STATUSES.map((status) => (
                <tr key={status} data-status={status}>
                  <th scope="row">{reportedDepthOutcome(status, language)}</th>
                  {REPORTED_DEPTH_BASES.map((basis) => (REPORTED_DEPTH_APPLIES[basis].includes(status)
                    ? <td key={basis} data-basis={basis}>{counts[basis][status]}</td>
                    : <td key={basis} data-basis={basis} aria-label={REPORTED_DEPTH_COPY.notApplicable[language]}>–</td>))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className={styles.muted} data-testid="reported-depth-counts-note">{REPORTED_DEPTH_COPY.tableNote[language]}</p>
        <p data-testid="reported-depths-statements">
          {t(`Counted once per statement (${block.counted.statements} statements):`, `นับหนึ่งครั้งต่อหนึ่งข้อความ (${block.counted.statements} ข้อความ):`)}{" "}
          {reportedDepthStatementTallyText(block.counts_by_statement, language)}{th ? "" : "."}
        </p>
        {block.shared_statements.length > 0 && (
          <>
            <p>{t("Statements recorded at several places (one statement, one record per community):", "ข้อความที่บันทึกไว้หลายสถานที่ (ข้อความเดียว หนึ่งรายการต่อหนึ่งชุมชน):")}</p>
            <ul className={styles.list} data-testid="reported-depths-shared">
              {reportedDepthSharedText(block, language).map((line, index) => <li key={block.shared_statements[index].statement_id} data-statement={block.shared_statements[index].statement_id}>{line}</li>)}
            </ul>
          </>
        )}
        <p className={styles.muted} data-testid="reported-depths-sensitivity">
          {block.tolerance_rule[language]}{" "}
          {t("All place records:", "ทุกรายการ:")} {reportedDepthTallyText(block.counts_within_tolerance.all, language)}{th ? "" : "."}
        </p>
        <p><strong>{REPORTED_DEPTH_COPY.causes[language]}</strong></p>
        <ul className={styles.list} data-testid="reported-depths-causes">
          {block.likely_causes.map((cause) => <li key={cause.id} data-cause={cause.id}>{cause.text[language]}</li>)}
        </ul>
        <p><strong>{REPORTED_DEPTH_COPY.assumptions[language]}</strong></p>
        <ul className={styles.list} data-testid="reported-depths-assumptions">
          {block.assumptions[language].map((line) => <li key={line}>{line}</li>)}
        </ul>
        {/* A plain list, not a nested disclosure: the Sources panel is itself one collapsed section. */}
        <p><strong>{REPORTED_DEPTH_COPY.allReports[language]} ({block.reports.length})</strong></p>
        <ul className={`${styles.list} ${styles.reportedDepthList}`} data-testid="reported-depths-list">
          {block.reports.map((report) => (
            <li key={report.id} data-report={report.id} data-consistency={report.consistency}>
              <strong>{report.place[language]}</strong>{" — "}{reportedDepthText(report, block, language)}{" · "}{report.time.text[language]}{" · "}
              {t("location confidence", "ความเชื่อมั่นของตำแหน่ง")} {locationConfidenceText(report.location_confidence, language)}{" · "}
              {reportedDepthStatusText(report, language)}{". "}
              <a href={report.source.url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>
                {report.source.publisher}, {formatDateWithYear(report.source.published, language)}: <span lang={report.source.language}>{report.source.title}</span>
              </a>
            </li>
          ))}
        </ul>
        <p className={styles.muted} data-testid="reported-depths-footer">
          {t("Confidence", "ความเชื่อมั่น")}: {block.confidence.toLowerCase() === "low" ? t("low", "ต่ำ") : block.confidence} — {block.confidence_reason[language]}{" "}
          {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: <span lang="en">{block.source_timestamp}</span>{" · "}
          {t(
            `${block.left_out.dropped} candidate reports were dropped by the second reader and ${block.left_out.excluded} search hits were left out by rule (other floods, other places, or no depth at a named place).`,
            `ผู้ตรวจคนที่สองตัดรายงานที่เข้าข่าย ${block.left_out.dropped} ชิ้น และไม่นับผลการค้นหา ${block.left_out.excluded} รายการตามเกณฑ์ (เป็นน้ำท่วมครั้งอื่น สถานที่อื่น หรือไม่มีความลึก ณ สถานที่ที่มีชื่อ)`,
          )}
        </p>
      </div>
    </>
  );
}
