"use client";

/**
 * Observed evidence in the Mae Sai replay: the NOAA/GMU VIIRS daily flood maps (375 m, compared with the model in
 * clear-sky pixels only), the Sentinel-2 water check of 15 Sep (water or saturated mud on clear pixels) and the HII
 * hourly rain gauges (forcing, not flooding). Everything here is rendered from the manifest's `viirs_daily`,
 * `s2_crosscheck` and `rainfall` blocks. Both comparisons with the model are indicative, never a validation.
 */

import { memo } from "react";

import {
  formatLocalStamp,
  formatShortDate,
  hourIndex,
  rainAt,
  rgbaCss,
  s2CrosscheckDate,
  s2CrosscheckScenes,
  TIMELINE_END_T,
  VIIRS_CLASSES,
  viirsReading,
  type Language,
  type Rainfall,
  type RainStation,
  type S2Crosscheck,
  type ViirsDaily,
  type ViirsDay,
} from "@/lib/flood-timeline";
import { localizedText } from "@/lib/flood-timeline-copy";

import styles from "./mae-sai-flood-timeline.module.css";

type Translate = (en: string, th: string) => string;
const translator = (language: Language): Translate => (en, th) => (language === "th" ? th : en);

function ManifestText({ text, language }: { text: string; language: Language }) {
  const value = localizedText(text, language);
  return <span lang={value.lang}>{value.text}</span>;
}

/** "10–14 Sep, 18 Sep" for a set of local dates, consecutive days merged. */
export function formatDateSet(dates: readonly string[], language: Language): string {
  const sorted = [...new Set(dates)].sort();
  const dayMs = 86_400_000;
  const runs: [string, string][] = [];
  for (const date of sorted) {
    const last = runs.at(-1);
    if (last && Date.parse(`${date}T00:00:00Z`) - Date.parse(`${last[1]}T00:00:00Z`) === dayMs) last[1] = date;
    else runs.push([date, date]);
  }
  return runs.map(([start, end]) => {
    if (start === end) return formatShortDate(start, language);
    const [startDay, ...startMonth] = formatShortDate(start, language).split(" ");
    const endText = formatShortDate(end, language);
    return startMonth.join(" ") === endText.split(" ").slice(1).join(" ") ? `${startDay}–${endText}` : `${formatShortDate(start, language)} – ${endText}`;
  }).join(language === "th" ? " และ " : ", ");
}

/** Days on which cloud hid at least half of the district. */
export const cloudyViirsDays = (days: readonly Pick<ViirsDay, "date" | "cloud_share">[]) => days.filter((day) => day.cloud_share >= 0.5).map((day) => day.date);

/** Station name in the page language. */
export const rainStationName = (station: Pick<RainStation, "name_en" | "name_th">, language: Language) => (language === "th" ? station.name_th : station.name_en);

const km = (value: number) => value.toFixed(1);
const pct = (share: number) => `${Math.round(share * 100)}%`;

/**
 * What VIIRS shows at this moment, for the evidence list: the day on the map (nominal pass, cloud, clear-sky sizes)
 * or why none is shown.
 */
export function viirsMomentText(day: ViirsDay | null, viirs: Pick<ViirsDaily, "days">, language: Language): string {
  const t = translator(language);
  if (!day) {
    const range = formatDateSet(viirs.days.map((item) => item.date), language);
    return t(
      `No VIIRS daily map for this moment; the maps cover ${range}, each from its nominal 13:30 ICT pass.`,
      `ไม่มีแผนที่ VIIRS รายวันสำหรับช่วงเวลานี้ แผนที่ครอบคลุม ${range} โดยแต่ละภาพเริ่มแสดงตั้งแต่เวลาโคจรผ่านโดยประมาณ 13:30 น.`,
    );
  }
  const stamp = formatLocalStamp(day.nominal_local_time, language);
  const reading = viirsReading(day);
  if (reading.kind === "no_observation") {
    return t(`${stamp} (nominal): cloud covered the whole district, so there is no observation.`, `${stamp} (โดยประมาณ): เมฆปกคลุมทั้งอำเภอ จึงไม่มีการสังเกต`);
  }
  return t(
    `${stamp} (nominal): ${pct(day.cloud_share)} cloud. In the ${km(day.clear_km2)} km² of clear sky, VIIRS shows ${km(day.viirs_flood_km2_clear)} km² of flood water and the model ${km(day.model_flood_km2_clear)} km².`,
    `${stamp} (โดยประมาณ): เมฆ ${pct(day.cloud_share)} ในพื้นที่ท้องฟ้าโปร่ง ${km(day.clear_km2)} ตร.กม. VIIRS พบน้ำท่วม ${km(day.viirs_flood_km2_clear)} ตร.กม. และแบบจำลองระบุ ${km(day.model_flood_km2_clear)} ตร.กม.`,
  );
}

// --- Sentinel-2 water check (15 Sep) -----------------------------------------------------------------

/**
 * What the Sentinel-2 water check observed: the product, the acquisition time, the share of the district seen and the
 * area of water or saturated mud, beside the scene before the flood and the part that is new. Observed figures only.
 */
export function s2ObservedText(check: S2Crosscheck, language: Language): string {
  const t = translator(language);
  const scenes = s2CrosscheckScenes(check);
  if (!scenes) return "";
  const { event, pre } = scenes;
  const stamp = formatLocalStamp(event.local_time, language);
  if (event.water_km2 === null) {
    return t(
      `Observed (Sentinel-2 L2A, ${stamp}): cloud covered the whole district, so there is no observation.`,
      `สังเกตการณ์ (Sentinel-2 L2A ${stamp}): เมฆปกคลุมทั้งอำเภอ จึงไม่มีการสังเกต`,
    );
  }
  const before = pre.water_km2 === null ? "" : t(
    `, against ${km(pre.water_km2)} km² on ${formatShortDate(pre.local_time, "en")}, before the flood (${pct(pre.clear_share)} clear)`,
    ` เทียบกับ ${km(pre.water_km2)} ตร.กม. เมื่อ ${formatShortDate(pre.local_time, "th")} ก่อนน้ำท่วม (มองเห็น ${pct(pre.clear_share)})`,
  );
  const fresh = check.change.new_water_km2 === null ? "" : t(
    ` Where both dates are clear, ${km(check.change.new_water_km2)} km² is new.`,
    ` ในบริเวณที่มองเห็นได้ทั้งสองวัน มี ${km(check.change.new_water_km2)} ตร.กม. ที่เพิ่มขึ้นใหม่`,
  );
  return t(
    `Observed (Sentinel-2 L2A, ${stamp}, ${pct(event.clear_share)} of the district clear): ${km(event.water_km2)} km² of water or saturated mud outside the mapped channels${before}.${fresh}`,
    `สังเกตการณ์ (Sentinel-2 L2A ${stamp} มองเห็นพื้นที่อำเภอ ${pct(event.clear_share)} โดยไม่มีเมฆบัง): พบน้ำหรือโคลนอิ่มน้ำ ${km(event.water_km2)} ตร.กม. นอกร่องน้ำในแผนที่${before}${fresh}`,
  );
}

/** The model beside the Sentinel-2 observation, in the same clear pixels; the comparison is labelled indicative. */
export function s2ModelText(check: S2Crosscheck, language: Language): string {
  const t = translator(language);
  const model = check.model_at_event_scene;
  return t(
    `Model at that time (assumed stage ${model.model_stage_m.toFixed(2)} m): ${km(model.model_flood_km2_clear)} km² in the same clear pixels. This comparison is indicative.`,
    `แบบจำลอง ณ เวลาเดียวกัน (ระดับน้ำสมมุติ ${model.model_stage_m.toFixed(2)} ม.): ${km(model.model_flood_km2_clear)} ตร.กม. ในพิกเซลเดียวกัน การเปรียบเทียบนี้เป็นเพียงข้อบ่งชี้`,
  );
}

/**
 * True when every observation of the day shows a larger area than the model in its own clear pixels: Sentinel-2
 * always, and VIIRS when the day has a VIIRS map with clear sky. Only then may the page speak of "the larger observed area".
 */
export function observedLargerThanModel(check: S2Crosscheck, viirsDay: Pick<ViirsDay, "clear_km2" | "viirs_flood_km2_clear" | "model_flood_km2_clear"> | null): boolean {
  const water = s2CrosscheckScenes(check)?.event.water_km2 ?? null;
  if (water === null || water <= check.model_at_event_scene.model_flood_km2_clear) return false;
  return !viirsDay || viirsDay.clear_km2 <= 0 || viirsDay.viirs_flood_km2_clear > viirsDay.model_flood_km2_clear;
}

/**
 * Both observations of the day named side by side, each against the model in its own clear pixels: VIIRS (when the
 * day has a map with clear sky) and Sentinel-2. Numbers only; what they are consistent with is said separately.
 */
export function bothObservationsText(check: S2Crosscheck, viirsDay: ViirsDay | null, language: Language): string {
  const t = translator(language);
  const scenes = s2CrosscheckScenes(check);
  if (!scenes || scenes.event.water_km2 === null) return "";
  const s2Stamp = formatLocalStamp(scenes.event.local_time, language);
  const s2Model = km(check.model_at_event_scene.model_flood_km2_clear);
  const s2 = km(scenes.event.water_km2);
  if (!viirsDay || viirsDay.clear_km2 <= 0) {
    return t(
      `One observation on this day: Sentinel-2 (${s2Stamp}) shows ${s2} km² of water or saturated mud against the model's ${s2Model} km² in the same clear pixels.`,
      `วันนี้มีการสังเกตการณ์หนึ่งแหล่ง: Sentinel-2 (${s2Stamp}) พบน้ำหรือโคลนอิ่มน้ำ ${s2} ตร.กม. เทียบกับแบบจำลอง ${s2Model} ตร.กม. ในพิกเซลเดียวกัน`,
    );
  }
  const viirsStamp = formatLocalStamp(viirsDay.nominal_local_time, language);
  return t(
    `Two observations on this day: VIIRS (${viirsStamp}, nominal) shows ${km(viirsDay.viirs_flood_km2_clear)} km² of flood water against the model's ${km(viirsDay.model_flood_km2_clear)} km², and Sentinel-2 (${s2Stamp}) shows ${s2} km² of water or saturated mud against the model's ${s2Model} km², each in its own clear pixels.`,
    `วันนี้มีการสังเกตการณ์สองแหล่ง: VIIRS (${viirsStamp} โดยประมาณ) พบน้ำท่วม ${km(viirsDay.viirs_flood_km2_clear)} ตร.กม. เทียบกับแบบจำลอง ${km(viirsDay.model_flood_km2_clear)} ตร.กม. และ Sentinel-2 (${s2Stamp}) พบน้ำหรือโคลนอิ่มน้ำ ${s2} ตร.กม. เทียบกับแบบจำลอง ${s2Model} ตร.กม. โดยแต่ละแหล่งนับเฉพาะพิกเซลที่ตนมองเห็น`,
  );
}

/**
 * The reading of the day with two observations: the numbers of both, then (only when both show more than the model)
 * the manifest's sentence on what that is consistent with, then the caveat. It states no cause.
 */
export function ObservedReading({ check, viirsDay, language }: { check: S2Crosscheck; viirsDay: ViirsDay | null; language: Language }) {
  return (
    <>
      {bothObservationsText(check, viirsDay, language)}{" "}
      {observedLargerThanModel(check, viirsDay) && <><strong data-testid="s2-reading"><ManifestText text={check.reading} language={language} /></strong>{" "}</>}
      <ManifestText text={check.caveat} language={language} />
    </>
  );
}

/**
 * Evidence rows for the day of the Sentinel-2 water check (15 Sep): what Sentinel-2 observed, the model beside it,
 * and the reading of both observations. Rendered inside the "Evidence for this moment" list on that day only.
 */
export function Sentinel2Evidence({ check, viirsDay, language }: { check: S2Crosscheck; viirsDay: ViirsDay | null; language: Language }) {
  const t = translator(language);
  if (!s2CrosscheckScenes(check)) return null;
  return (
    <>
      <div data-testid="s2-evidence">
        <dt>{t("Sentinel-2 (observed)", "Sentinel-2 (สังเกตการณ์)")}</dt>
        <dd>{s2ObservedText(check, language)} {s2ModelText(check, language)}</dd>
      </div>
      <div data-testid="observed-reading">
        <dt>{t("VIIRS and Sentinel-2", "VIIRS และ Sentinel-2")}</dt>
        <dd><ObservedReading check={check} viirsDay={viirsDay} language={language} /></dd>
      </div>
    </>
  );
}

const SENSITIVITY_LABELS: Readonly<Record<string, [string, string]>> = {
  strict_clear: ["only vegetation, bare ground and water classes count as clear", "นับเฉพาะชั้นพืชพรรณ ดินเปล่า และน้ำว่าไม่มีเมฆบัง"],
  threshold_0_1: ["MNDWI above 0.1", "MNDWI มากกว่า 0.1"],
  threshold_0_2: ["MNDWI above 0.2", "MNDWI มากกว่า 0.2"],
};

/** "Under stricter rules the 15 Sep area is …": the sensitivity rows the page knows how to name, or an empty string. */
export function s2SensitivityText(check: S2Crosscheck, language: Language): string {
  const t = translator(language);
  const scenes = s2CrosscheckScenes(check);
  const rows = check.sensitivity.filter((row) => SENSITIVITY_LABELS[row.id] && row.event_water_km2 !== null);
  if (!scenes || rows.length === 0) return "";
  const parts = rows.map((row) => `${km(row.event_water_km2 ?? 0)} ${t("km²", "ตร.กม.")} (${SENSITIVITY_LABELS[row.id][language === "th" ? 1 : 0]})`);
  const date = formatShortDate(scenes.event.local_time, language);
  return t(
    `Under stricter rules the ${date} area is ${parts.join("; ")}.`,
    `หากใช้เกณฑ์ที่เข้มขึ้น พื้นที่ของวันที่ ${date} เป็น ${parts.join(" · ")}`,
  );
}

/** Legend of the pre-coloured VIIRS classes, labelled from the manifest legend (Thai from the page). */
export function ViirsLegend({ viirs, language }: { viirs: Pick<ViirsDaily, "legend">; language: Language }) {
  const t = translator(language);
  return (
    <div data-testid="viirs-legend">
      <strong>{t("VIIRS daily flood map (375 m, observed)", "แผนที่น้ำท่วมรายวัน VIIRS (375 ม. การสังเกตการณ์)")}</strong>
      <ul>
        {VIIRS_CLASSES.map((item) => (
          <li key={item.code}><i className={styles.viirsSwatch} style={{ background: rgbaCss(item.rgba) }} />{language === "th" ? item.th : viirs.legend[item.code] ?? item.code}</li>
        ))}
      </ul>
      <small className={styles.legendNote}>{t(
        "Observed at a nominal 13:30 ICT; clear, dry land is transparent. Purple is observed flood water; the model's water is blue.",
        "สังเกตการณ์ ณ เวลาโดยประมาณ 13:30 น. พื้นดินแห้งที่ท้องฟ้าโปร่งแสดงแบบโปร่งใส สีม่วงคือน้ำท่วมที่สังเกตได้ ส่วนน้ำจากแบบจำลองเป็นสีน้ำเงิน",
      )}</small>
    </div>
  );
}

/**
 * "Observed vs modelled (VIIRS, clear sky only)": per day, the cloud share, the clear-sky area, the VIIRS flood area and
 * the model's area in the same clear pixels, with a plain reading of each day and the product's caveat. Memoised: it
 * changes only when the day on show changes.
 */
export const ViirsComparisonCard = memo(function ViirsComparisonCard({ viirs, activeDate, showOnMap, onShowOnMap, language, s2 = null }: {
  viirs: ViirsDaily;
  /** Local date of the VIIRS map at or before the playhead, highlighted in the table. */
  activeDate: string | null;
  /** The Sentinel-2 water check while the playhead is on its day (15 Sep): the second observation of that day. */
  s2?: S2Crosscheck | null;
  showOnMap: boolean;
  onShowOnMap: (value: boolean) => void;
  language: Language;
}) {
  const t = translator(language);
  const days = viirs.days;
  if (days.length === 0) return null;
  const range = formatDateSet(days.map((day) => day.date), language);
  const cloudy = cloudyViirsDays(days);
  const unit = t("km²", "ตร.กม.");
  // The day of the Sentinel-2 water check, named by its date: the row highlighted above is the VIIRS map at or before
  // the playhead, which is the day before until the 13:30 pass.
  const s2Date = s2 && s2CrosscheckScenes(s2) ? s2CrosscheckDate(s2) : null;
  return (
    <section className={styles.card} aria-labelledby="mae-sai-viirs-title" data-testid="viirs-card">
      <p className={styles.eyebrow}>{t("OBSERVED · VIIRS 375 m · DAILY", "การสังเกตการณ์ · VIIRS 375 ม. · รายวัน")}</p>
      <h2 id="mae-sai-viirs-title">{t("Observed vs modelled (VIIRS, clear sky only)", "การสังเกตเทียบกับแบบจำลอง (VIIRS เฉพาะท้องฟ้าโปร่ง)")}</h2>
      <p className={styles.muted}>{t(
        `Daily satellite flood maps for ${range}: a coarse observation (375 m pixels), compared with the reconstruction only where the sky over the district was clear. It is a size check where VIIRS could see, not a validation of the model.`,
        `แผนที่น้ำท่วมรายวันจากดาวเทียมสำหรับ ${range}: การสังเกตการณ์แบบหยาบ (พิกเซล 375 ม.) เทียบกับการจำลองเฉพาะบริเวณที่ท้องฟ้าเหนืออำเภอโปร่ง เป็นการตรวจขนาดเฉพาะส่วนที่ VIIRS มองเห็น ไม่ใช่การยืนยันความถูกต้องของแบบจำลอง`,
      )}</p>
      {cloudy.length > 0 && (
        <p className={styles.caveat} data-testid="viirs-cloud">{t(
          `Cloud hid at least half of the district on ${cloudy.length} of ${days.length} days (${formatDateSet(cloudy, "en")}), so most of the flood is not observed here.`,
          `เมฆบังพื้นที่อำเภออย่างน้อยครึ่งหนึ่งใน ${cloudy.length} จาก ${days.length} วัน (${formatDateSet(cloudy, "th")}) น้ำท่วมส่วนใหญ่จึงไม่ได้ถูกสังเกตในข้อมูลนี้`,
        )}</p>
      )}
      <div className={styles.tableScroll}>
        <table className={styles.viirsTable}>
          <caption className={styles.srOnly}>{t("VIIRS and model flood area in clear-sky district pixels, by day", "พื้นที่น้ำท่วมจาก VIIRS และแบบจำลองในพิกเซลท้องฟ้าโปร่งของอำเภอ รายวัน")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("Day", "วัน")}</th>
              <th scope="col">{t("Cloud", "เมฆ")}</th>
              <th scope="col">{t(`Clear ${unit}`, `ท้องฟ้าโปร่ง ${unit}`)}</th>
              <th scope="col">{t(`VIIRS flood ${unit}`, `น้ำท่วม VIIRS ${unit}`)}</th>
              <th scope="col">{t(`Model ${unit}, same pixels`, `แบบจำลอง ${unit} พิกเซลเดียวกัน`)}</th>
            </tr>
          </thead>
          <tbody>
            {days.map((day) => {
              // With no clear sky there is nothing to compare: a dash, never a zero that reads as "no flood".
              const seen = day.clear_km2 > 0;
              const none = <span title={t("No clear sky: no observation", "ไม่มีท้องฟ้าโปร่ง: ไม่มีการสังเกต")}>—<span className={styles.srOnly}>{t(" no observation", " ไม่มีการสังเกต")}</span></span>;
              return (
                <tr key={day.date} data-active={day.date === activeDate || undefined} aria-current={day.date === activeDate ? "date" : undefined}>
                  <th scope="row">{formatShortDate(day.date, language)}</th>
                  <td>{pct(day.cloud_share)}</td>
                  <td>{km(day.clear_km2)}</td>
                  <td data-tone="observed">{seen ? km(day.viirs_flood_km2_clear) : none}</td>
                  <td>{seen ? km(day.model_flood_km2_clear) : none}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <h3>{t("Reading, day by day", "สรุปรายวัน")}</h3>
      <ul className={styles.viirsReadings}>
        {days.map((day) => {
          const reading = viirsReading(day);
          return (
            <li key={day.date} data-kind={reading.kind} data-active={day.date === activeDate || undefined}>
              <strong>{formatShortDate(day.date, language)}</strong> {language === "th" ? reading.th : reading.en}
            </li>
          );
        })}
      </ul>
      {s2 && s2Date && (
        <p className={styles.caveat} data-testid="viirs-s2-note">
          <strong>{t(`Second observation on ${formatShortDate(s2Date, "en")}`, `การสังเกตการณ์แหล่งที่สองของวันที่ ${formatShortDate(s2Date, "th")}`)}:</strong>{" "}
          {s2ObservedText(s2, language)} {s2ModelText(s2, language)}{" "}
          {observedLargerThanModel(s2, days.find((day) => day.date === s2Date) ?? null) && <ManifestText text={s2.reading} language={language} />}
        </p>
      )}
      <p className={styles.caveat}>
        <strong>{t("Caveat", "ข้อควรระวัง")}:</strong> <ManifestText text={viirs.caveat} language={language} />{" "}
        {t(
          "Turbid flood water can be missed too, and standing water in rice paddies can read as flood water, so a difference in either direction is indicative, not proof that the model is wrong.",
          "น้ำท่วมที่ขุ่นก็อาจตรวจไม่พบเช่นกัน และน้ำขังในนาข้าวอาจถูกอ่านเป็นน้ำท่วม ความต่างไม่ว่าทางใดจึงเป็นเพียงข้อบ่งชี้ ไม่ใช่หลักฐานว่าแบบจำลองผิด",
        )}
      </p>
      <p className={styles.muted}>
        {t("How it is compared", "วิธีเปรียบเทียบ")}: <ManifestText text={viirs.comparison_rule} language={language} />{" "}
        <ManifestText text={viirs.nominal_overpass} language={language} />
      </p>
      <p className={styles.muted}>
        <span lang="en">{viirs.attribution}</span> · <span lang="en">{viirs.licence}</span>{" "}
        <a href={viirs.source_url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{viirs.source_url}</a>
      </p>
      <label className={styles.inlineToggle}>
        <input type="checkbox" checked={showOnMap} onChange={(event) => onShowOnMap(event.target.checked)} />
        {t("Show the VIIRS map for this moment on the map", "แสดงแผนที่ VIIRS ของช่วงเวลานี้บนแผนที่")}
      </label>
    </section>
  );
});

// --- Hourly rain ----------------------------------------------------------------------------------

/** Rain chart geometry: the x axis matches the hydrograph above it (same viewBox width and side margins). */
const RAIN = { width: 640, left: 34, right: 12, top: 4, labelH: 18, rowH: 44, gap: 6, bottom: 24 } as const;

function rainGeometry(stations: number) {
  const plotW = RAIN.width - RAIN.left - RAIN.right;
  const rowTop = (index: number) => RAIN.top + index * (RAIN.labelH + RAIN.rowH + RAIN.gap) + RAIN.labelH;
  const height = RAIN.top + stations * (RAIN.labelH + RAIN.rowH) + Math.max(0, stations - 1) * RAIN.gap + RAIN.bottom;
  const x = (t: number) => RAIN.left + (t / TIMELINE_END_T) * plotW;
  return { plotW, rowTop, height, x };
}

/**
 * The static part of the rain chart (bars, axes, labels): one path per station, built once per manifest and language,
 * so playback only moves the playhead.
 */
const RainBars = memo(function RainBars({ rainfall, dayLabels, language }: { rainfall: Rainfall; dayLabels: readonly string[]; language: Language }) {
  const t = translator(language);
  const { rowTop, height, x } = rainGeometry(rainfall.stations.length);
  const peak = Math.max(1, ...rainfall.stations.map((station) => station.max_hour_mm));
  const yMax = Math.max(5, Math.ceil(peak / 10) * 10);
  return (
    <>
      {dayLabels.map((label, index) => (
        <g key={`day-${label}-${index}`}>
          {index > 0 && <line x1={x(index)} x2={x(index)} y1={RAIN.top + RAIN.labelH} y2={height - RAIN.bottom} className={styles.gridLine} />}
          <text x={x(index + 0.5)} y={height - 8} textAnchor="middle" className={styles.axisText}>{label}</text>
        </g>
      ))}
      {rainfall.stations.map((station, index) => {
        const series = rainfall.hourly_mm[station.code] ?? [];
        const top = rowTop(index);
        const base = top + RAIN.rowH;
        let bars = "";
        let missing = "";
        series.forEach((value, hour) => {
          const x0 = x(hour / 24);
          const x1 = x((hour + 1) / 24);
          if (typeof value !== "number" || !Number.isFinite(value)) {
            missing += `M${x0.toFixed(2)} ${base + 2}H${x1.toFixed(2)}V${base + 5}H${x0.toFixed(2)}Z`;
          } else if (value > 0) {
            const y = base - (Math.min(value, yMax) / yMax) * RAIN.rowH;
            bars += `M${x0.toFixed(2)} ${base}V${y.toFixed(2)}H${x1.toFixed(2)}V${base}Z`;
          }
        });
        return (
          <g key={station.code} data-station={station.code}>
            <text x={RAIN.left} y={top - 4} className={styles.rainLabel}>
              {t(
                `${station.code} · rain, mm/h · total ${station.total_mm.toFixed(1)} mm · wettest hour ${station.max_hour_mm.toFixed(1)} mm`,
                `${station.code} · ฝน มม./ชม. · รวม ${station.total_mm.toFixed(1)} มม. · ชั่วโมงที่ฝนหนักที่สุด ${station.max_hour_mm.toFixed(1)} มม.`,
              )}
            </text>
            <line x1={RAIN.left} x2={RAIN.width - RAIN.right} y1={top} y2={top} className={styles.gridLine} />
            <line x1={RAIN.left} x2={RAIN.width - RAIN.right} y1={base} y2={base} className={styles.rainBase} />
            <text x={RAIN.left - 6} y={top + 3.5} textAnchor="end" className={styles.axisText}>{yMax}</text>
            <text x={RAIN.left - 6} y={base + 3.5} textAnchor="end" className={styles.axisText}>0</text>
            {bars && <path d={bars} className={styles.rainBar} />}
            {missing && <path d={missing} className={styles.rainMissing} />}
          </g>
        );
      })}
    </>
  );
});

/**
 * Observed hourly rain at the manifest's gauges, one row per station on the hydrograph's time axis, with the playhead.
 * Labelled as observed forcing, not flooding.
 */
export function RainChart({ rainfall, time, dayLabels, language }: {
  rainfall: Rainfall;
  time: number;
  /** Day-of-month label per replay day (index 0 = 9 Sep). */
  dayLabels: readonly string[];
  language: Language;
}) {
  const t = translator(language);
  if (rainfall.stations.length === 0) return null;
  const { rowTop, height, x } = rainGeometry(rainfall.stations.length);
  const hours = Math.max(0, ...rainfall.stations.map((station) => rainfall.hourly_mm[station.code]?.length ?? 0));
  const hour = Math.min(Math.max(0, hours - 1), hourIndex(time));
  const summary = t(
    `Observed hourly rain, 9–19 Sep (ICT), at ${rainfall.stations.length} gauges: ${rainfall.stations.map((station) => `${station.name_en} (${station.code}) ${station.total_mm.toFixed(1)} mm in total, wettest hour ${station.max_hour_mm.toFixed(1)} mm`).join("; ")}.`,
    `ปริมาณฝนรายชั่วโมงที่ตรวจวัดได้ 9–19 ก.ย. (เวลาประเทศไทย) จาก ${rainfall.stations.length} สถานี: ${rainfall.stations.map((station) => `${station.name_th} (${station.code}) รวม ${station.total_mm.toFixed(1)} มม. ชั่วโมงที่ฝนหนักที่สุด ${station.max_hour_mm.toFixed(1)} มม.`).join(" ")}`,
  );
  const now = rainfall.stations.map((station) => {
    const value = rainAt(rainfall, station.code, hour);
    return `${station.code} ${value === null ? t("no record", "ไม่มีข้อมูล") : `${value.toFixed(1)} ${t("mm", "มม.")}`}`;
  }).join(" · ");
  return (
    <figure className={`${styles.hydrograph} ${styles.rainChart}`} data-testid="rain-chart">
      <svg viewBox={`0 0 ${RAIN.width} ${height}`} role="img" aria-label={summary}>
        <RainBars rainfall={rainfall} dayLabels={dayLabels} language={language} />
        <line x1={x(time)} x2={x(time)} y1={rowTop(0) - 2} y2={height - RAIN.bottom} className={styles.playhead} />
      </svg>
      <figcaption>
        <span>{t(
          "Observed hourly rain (mm per hour) at HII rain gauges — the forcing, not flooding. Same time axis as the stage curve above.",
          "ปริมาณฝนรายชั่วโมงที่ตรวจวัดได้ (มม. ต่อชั่วโมง) จากสถานีวัดฝนของ สสน. — เป็นปัจจัยที่ทำให้เกิดน้ำ ไม่ใช่ขอบเขตน้ำท่วม ใช้แกนเวลาเดียวกับกราฟระดับน้ำด้านบน",
        )}</span>
        <ul className={styles.obsList} aria-label={t("Rain gauges", "สถานีวัดฝน")}>
          {rainfall.stations.map((station) => (
            <li key={station.code}>
              <i className={styles.rainSwatch} aria-hidden="true" />
              <span lang={language}>{station.code} {rainStationName(station, language)}</span>
            </li>
          ))}
        </ul>
        <span className={styles.rainNow} data-testid="rain-now">{t("This hour", "ชั่วโมงนี้")}: {now}</span>
        <span>
          <span lang="en">{rainfall.source}</span> · <span lang="en">{rainfall.licence}</span>
        </span>
      </figcaption>
    </figure>
  );
}
