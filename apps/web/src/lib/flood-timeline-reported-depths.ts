/**
 * Reported depths for the Mae Sai replay (roadmap C-2): flood depths that news reports gave at named places on
 * 10-13 Sep 2024, paraphrased and cited, with their consistency with the model. Their status is "reported (anecdotal,
 * not surveyed)": the comparison is a consistency check, never a validation, and the reports are never used to tune
 * the model. Pure helpers only (no DOM): which block may be shown, the map's places, and the bilingual wording of the
 * popups, the legend and the Sources table.
 */

import {
  formatDateWithYear,
  formatLocalStamp,
  formatShortDate,
  type Language,
  type Localized,
  type ReportedDepthCounts,
  type ReportedDepthReport,
  type ReportedDepths,
  type ReportedDepthStatus,
  type TimelineManifest,
} from "./flood-timeline";

/** The block's status, as the bake writes it; any other status withholds the layer. */
export const REPORTED_DEPTH_STATUS = "reported (anecdotal, not surveyed)";
export const REPORTED_DEPTH_STATUSES: readonly ReportedDepthStatus[] = ["consistent", "model_shallower", "model_dry", "not_comparable"];
export const REPORTED_DEPTH_BASES = ["numeric", "qualitative", "all"] as const;

export const REPORTED_DEPTH_COPY = {
  toggle: { en: "Reported depths (news, not surveyed)", th: "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)" },
  legend: { en: "Reported depth (news, not surveyed); select for the report", th: "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ) เลือกเพื่อดูรายงาน" },
  marker: { en: "Reported depth (news, not surveyed)", th: "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)" },
  title: { en: "Reported depths (news, not surveyed)", th: "ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)" },
  status: { en: "Status: reported (anecdotal, not surveyed).", th: "สถานะ: ตามรายงาน (คำบอกเล่า ไม่ได้สำรวจ)" },
  tableCaption: { en: "Consistency with the model, number of reports", th: "ความสอดคล้องกับแบบจำลอง (จำนวนรายงาน)" },
  causes: { en: "Likely causes where the model is dry or shallower", th: "สาเหตุที่น่าจะเป็นเมื่อแบบจำลองแห้งหรือตื้นกว่า" },
  allReports: { en: "Every report, with its source", th: "รายงานทั้งหมดพร้อมแหล่งข่าว" },
} as const satisfies Record<string, Localized>;

const COLUMN_TEXT: Record<ReportedDepthStatus, Localized> = {
  consistent: { en: "Consistent", th: "สอดคล้อง" },
  model_shallower: { en: "Model shallower", th: "แบบจำลองตื้นกว่า" },
  model_dry: { en: "Model dry", th: "แบบจำลองแห้ง" },
  not_comparable: { en: "Not comparable", th: "เทียบไม่ได้" },
};
const ROW_TEXT: Record<(typeof REPORTED_DEPTH_BASES)[number], Localized> = {
  numeric: { en: "Numbers (lower bounds and ranges)", th: "ตัวเลข (ค่าขั้นต่ำและช่วงค่า)" },
  qualitative: { en: "Storey or body references (wet or dry only)", th: "อ้างอิงชั้นอาคารหรือระดับร่างกาย (เทียบเพียงมีน้ำหรือแห้ง)" },
  all: { en: "All reports", th: "รายงานทั้งหมด" },
};
const STATUS_TEXT: Record<ReportedDepthStatus, { numeric: Localized; qualitative: Localized }> = {
  consistent: {
    numeric: { en: "consistent: the model reaches the reported lower bound", th: "สอดคล้อง: แบบจำลองลึกถึงค่าขั้นต่ำที่รายงาน" },
    qualitative: { en: "consistent: the model has water here (no depth is compared)", th: "สอดคล้อง: แบบจำลองมีน้ำที่จุดนี้ (ไม่ได้เทียบความลึก)" },
  },
  model_shallower: {
    numeric: { en: "the model is shallower than the reported lower bound", th: "แบบจำลองตื้นกว่าค่าขั้นต่ำที่รายงาน" },
    qualitative: { en: "the model is shallower than reported", th: "แบบจำลองตื้นกว่าที่รายงาน" },
  },
  model_dry: {
    numeric: { en: "the model is dry here over the report's time window", th: "แบบจำลองไม่มีน้ำที่จุดนี้ในช่วงเวลาของรายงาน" },
    qualitative: { en: "the model is dry here over the report's time window", th: "แบบจำลองไม่มีน้ำที่จุดนี้ในช่วงเวลาของรายงาน" },
  },
  not_comparable: {
    numeric: { en: "not comparable: no point on the map or no time window", th: "เทียบไม่ได้: ไม่มีจุดบนแผนที่หรือไม่มีช่วงเวลา" },
    qualitative: { en: "not comparable: no point on the map or no time window", th: "เทียบไม่ได้: ไม่มีจุดบนแผนที่หรือไม่มีช่วงเวลา" },
  },
};
const CONFIDENCE_TEXT: Record<ReportedDepthReport["location_confidence"], Localized> = {
  low: { en: "low", th: "ต่ำ" },
  medium: { en: "medium", th: "ปานกลาง" },
  high: { en: "high", th: "สูง" },
};

const pick = (text: Localized, language: Language) => (language === "th" ? text.th : text.en);
const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const isLocalized = (value: unknown): value is Localized => isRecord(value) && typeof value.en === "string" && typeof value.th === "string" && !!value.en && !!value.th;
const isTally = (value: unknown) => isRecord(value) && REPORTED_DEPTH_STATUSES.every((status) => Number.isInteger(value[status]) && (value[status] as number) >= 0);

/**
 * The reported depths when the page may show them: the status is "reported (anecdotal, not surveyed)", the lane is
 * REP, the use rule says the check is never a validation and the reports are never used to tune the model, the counts
 * are present, and every report carries its place, paraphrase, time and source in both languages (a located one with
 * its point). Anything else withholds the layer and the Sources entry (null): the reports are never shown unlabelled.
 */
export function shippableReportedDepths(manifest: Pick<TimelineManifest, "reported_depths"> | null | undefined): ReportedDepths | null {
  const block = manifest?.reported_depths as unknown;
  if (!isRecord(block) || block.status !== REPORTED_DEPTH_STATUS || block.lane !== "REP") return null;
  const rule = block.use_rule;
  if (!isLocalized(rule) || !rule.en.includes("never used to tune") || !rule.en.includes("never a validation")) return null;
  if (!isLocalized(block.label) || !isLocalized(block.comparison_rule) || !isLocalized(block.confidence_reason)) return null;
  if (!isRecord(block.counts) || !REPORTED_DEPTH_BASES.every((basis) => isTally((block.counts as Record<string, unknown>)[basis]))) return null;
  if (!Array.isArray(block.reports) || block.reports.length === 0) return null;
  for (const report of block.reports as unknown[]) {
    if (!isRecord(report) || !isLocalized(report.place) || !isRecord(report.depth) || !isLocalized(report.depth.statement)) return null;
    if (!isRecord(report.time) || !isLocalized(report.time.text) || !isRecord(report.source) || typeof report.source.url !== "string") return null;
    if (!REPORTED_DEPTH_STATUSES.includes(report.consistency as ReportedDepthStatus)) return null;
    const point = report.point;
    if (point !== null && !(isRecord(point) && Number.isFinite(point.lat) && Number.isFinite(point.lon))) return null;
  }
  return block as unknown as ReportedDepths;
}

/** Reports that share one point, drawn as one marker. */
export interface ReportedDepthPlace { key: string; lat: number; lon: number; reports: ReportedDepthReport[] }

/** The located reports grouped by point, in the order of their first report (several reports can name one place). */
export function reportedDepthPlaces(block: Pick<ReportedDepths, "reports">): ReportedDepthPlace[] {
  const places = new Map<string, ReportedDepthPlace>();
  for (const report of block.reports) {
    if (!report.point) continue;
    const key = `${report.point.lat},${report.point.lon}`;
    const place = places.get(key) ?? { key, lat: report.point.lat, lon: report.point.lon, reports: [] };
    place.reports.push(report);
    places.set(key, place);
  }
  return [...places.values()];
}

const metres = (value: number, language: Language) => `${value}${language === "th" ? " ม." : " m"}`;
const twoDecimals = (value: number, language: Language) => `${value.toFixed(2)}${language === "th" ? " ม." : " m"}`;

/** The reported depth in a few words: a lower bound, a range with its lower bound, or a class with no number. */
export function reportedDepthText(report: Pick<ReportedDepthReport, "depth">, block: Pick<ReportedDepths, "depth_classes">, language: Language): string {
  const { depth } = report;
  const th = language === "th";
  if (depth.kind === "lower_bound" && depth.lower_bound_m !== null) {
    return th ? `ลึกเกิน ${metres(depth.lower_bound_m, language)} (ค่าขั้นต่ำ)` : `more than ${metres(depth.lower_bound_m, language)} (lower bound)`;
  }
  if (depth.kind === "range" && depth.lower_bound_m !== null && depth.upper_m !== null) {
    return th
      ? `บางจุด ${depth.lower_bound_m}–${metres(depth.upper_m, language)} (ค่าขั้นต่ำ ${metres(depth.lower_bound_m, language)})`
      : `${depth.lower_bound_m}–${metres(depth.upper_m, language)} in places (lower bound ${metres(depth.lower_bound_m, language)})`;
  }
  const label = block.depth_classes.find((item) => item.id === depth.class)?.label;
  const name = label ? pick(label, language) : th ? "ไม่ระบุความลึก" : "depth not stated";
  return th ? `${name} (ไม่ระบุตัวเลข)` : `${name} (no number given)`;
}

/** Local HH:MM of an ISO instant (ICT, UTC+7). */
const localClock = (value: string) => new Date(Date.parse(value) + 7 * 3_600_000).toISOString().slice(11, 16);

/** A report's time window: "10 Sep 00:00–05:32 ICT", or "10 Sep 18:00 – 11 Sep 01:23 ICT" across midnight. */
export function reportedDepthWindow(report: Pick<ReportedDepthReport, "time">, language: Language): string | null {
  const { window_start: start, window_end: end } = report.time;
  if (!start || !end) return null;
  const suffix = language === "th" ? " น." : " ICT";
  if (formatShortDate(start, language) === formatShortDate(end, language)) {
    return `${formatShortDate(start, language)} ${localClock(start)}–${localClock(end)}${suffix}`;
  }
  return `${formatShortDate(start, language)} ${localClock(start)} – ${formatShortDate(end, language)} ${localClock(end)}${suffix}`;
}

/** The outcome of one report, in words. */
export function reportedDepthStatusText(report: Pick<ReportedDepthReport, "consistency" | "depth">, language: Language): string {
  return pick(STATUS_TEXT[report.consistency][report.depth.basis], language);
}

/** Column and row labels of the counts table. */
export const reportedDepthColumn = (status: ReportedDepthStatus, language: Language) => pick(COLUMN_TEXT[status], language);
export const reportedDepthRow = (basis: (typeof REPORTED_DEPTH_BASES)[number], language: Language) => pick(ROW_TEXT[basis], language);
export const locationConfidenceText = (level: ReportedDepthReport["location_confidence"], language: Language) => pick(CONFIDENCE_TEXT[level], language);

/** One sentence of counts, e.g. "3 consistent, 0 model shallower, 9 model dry, 9 not comparable". */
export function reportedDepthTallyText(counts: ReportedDepthCounts["all"], language: Language): string {
  return REPORTED_DEPTH_STATUSES.map((status) => (language === "th"
    ? `${pick(COLUMN_TEXT[status], language)} ${counts[status]}`
    : `${counts[status]} ${pick(COLUMN_TEXT[status], language).toLowerCase()}`)).join(language === "th" ? " · " : ", ");
}

/**
 * What the model has at the report's point over the report's window, in words (T1 scenario values; not part of the
 * report). A report without a point or without a window says why it is not compared.
 */
export function reportedDepthModelText(report: ReportedDepthReport, block: Pick<ReportedDepths, "peak_stage_m">, language: Language): string[] {
  const th = language === "th";
  const model = report.model;
  if (!model) {
    if (!report.point) {
      return [th
        ? "ไม่ได้เทียบกับแบบจำลอง: ความเชื่อมั่นของตำแหน่งต่ำ รายงานนี้จึงไม่มีจุดบนแผนที่"
        : "Not compared with the model: the location confidence is low, so the report has no point on the map."];
    }
    return [th ? "ไม่ได้เทียบกับแบบจำลอง: รายงานไม่ระบุเวลา" : "Not compared with the model: the report gives no time."];
  }
  const window = reportedDepthWindow(report, language) ?? "";
  const reached = model.depth_m > 0
    ? th ? `ลึกที่สุด ${twoDecimals(model.depth_m, language)}` : `up to ${twoDecimals(model.depth_m, language)} deep`
    : th ? "แห้ง" : "dry";
  const lines = [th
    ? `แบบจำลอง ณ จุดนี้ ช่วง ${window}: ${reached} (ระดับน้ำสมมุติสูงสุด ${model.window_max_stage_m.toFixed(2)} ม. เมื่อ ${formatLocalStamp(model.window_max_at, language)})`
    : `Model at this point, ${window}: ${reached} (assumed river level up to ${model.window_max_stage_m.toFixed(2)} m, at ${formatLocalStamp(model.window_max_at, language)}).`];
  const height = model.height_above_channel_m === null
    ? th ? "สูงกว่าระดับสูงสุดที่แบบจำลองบันทึก" : "above the highest level the model encodes"
    : th ? `สูงจากร่องน้ำ ${twoDecimals(model.height_above_channel_m, language)}` : `${twoDecimals(model.height_above_channel_m, language)} above its channel`;
  const firstWet = model.first_wet
    ? th ? `มีน้ำครั้งแรก ${formatLocalStamp(model.first_wet, language)}` : `first wet ${formatLocalStamp(model.first_wet, language)}`
    : th ? "ไม่มีน้ำเลยในแบบจำลอง" : "never wet in the model";
  lines.push(th
    ? `ที่ระดับสูงสุดของแบบจำลอง (ระดับน้ำสมมุติ ${block.peak_stage_m} ม.): ${twoDecimals(model.peak_depth_m, language)} · ${firstWet} · จุดนี้${height}`
    : `At the modelled peak (assumed river level ${block.peak_stage_m} m): ${twoDecimals(model.peak_depth_m, language)}; ${firstWet}; the point is ${height}.`);
  if (model.cell === "nearest_out_of_channel") {
    lines.push(th
      ? `อ่านค่าห่างจากจุด ${Math.round(model.moved_m)} ม. นอกร่องน้ำของแม่น้ำในแผนที่`
      : `Read ${Math.round(model.moved_m)} m from the point, outside the mapped river channel.`);
  }
  if (report.location_tolerance_m !== null) {
    lines.push(th
      ? `การทดสอบความไว: ภายในระยะ ${report.location_tolerance_m} ม. จากจุด น้ำในแบบจำลองลึกที่สุด ${twoDecimals(model.max_within_tolerance_m, language)} ในช่วงเวลานั้น`
      : `Sensitivity: within ${report.location_tolerance_m} m of the point the deepest modelled water in that window is ${twoDecimals(model.max_within_tolerance_m, language)}.`);
  }
  return lines;
}

/** A line of a popup: text with a tone, and the language of the text when it differs from the page's. */
export interface ReportedDepthLine { text: string; tone?: "title" | "muted"; lang?: Language }

/**
 * The popup section of one report: its lines and the link to its source. The link reads "publisher, date: title"; the
 * title is the article's own (cited as published, in the article's language).
 */
export function reportedDepthPopup(report: ReportedDepthReport, block: Pick<ReportedDepths, "depth_classes" | "peak_stage_m">, language: Language): {
  lines: ReportedDepthLine[];
  link: { href: string; text: string; title: string; titleLang: string };
} {
  const th = language === "th";
  const other: Language = th ? "en" : "th";
  const lines: ReportedDepthLine[] = [
    { text: pick(report.place, language), tone: "title" },
    { text: pick(report.place, other), tone: "muted", lang: other },
    { text: `${th ? "ตามรายงานข่าว (ไม่ได้สำรวจ)" : "Reported in news (not surveyed)"}: ${reportedDepthText(report, block, language)}` },
    { text: pick(report.depth.statement, language) },
    { text: `${th ? "เวลา" : "When"}: ${pick(report.time.text, language)}` },
    { text: `${th ? "ตำแหน่ง" : "Location"}: ${th ? "ความเชื่อมั่น" : "confidence"} ${locationConfidenceText(report.location_confidence, language)}${report.location_tolerance_m !== null
      ? th ? ` (จุดที่รายงานอาจห่างได้ถึงราว ${report.location_tolerance_m} ม.)` : ` (the reported spot may lie up to about ${report.location_tolerance_m} m away)` : ""} · ${th ? "ตำบล" : "Subdistrict"} ${pick(report.tambon, language)}`, tone: "muted" },
    ...reportedDepthModelText(report, block as Pick<ReportedDepths, "peak_stage_m">, language).map((text) => ({ text, tone: "muted" as const })),
    { text: `${th ? "ผลการเทียบ" : "Consistency"}: ${reportedDepthStatusText(report, language)}` },
  ];
  return {
    lines,
    link: { href: report.source.url, text: `${report.source.publisher}, ${formatDateWithYear(report.source.published, language)}: `, title: report.source.title, titleLang: report.source.language },
  };
}

/** Hover title of a marker: what it is and the place names it holds. */
export function reportedDepthMarkerTitle(place: ReportedDepthPlace, language: Language): string {
  const names = [...new Set(place.reports.map((report) => pick(report.place, language)))].join(" · ");
  const count = place.reports.length > 1 ? (language === "th" ? ` (${place.reports.length} รายงาน)` : ` (${place.reports.length} reports)`) : "";
  return `${pick(REPORTED_DEPTH_COPY.marker, language)}: ${names}${count}`;
}
