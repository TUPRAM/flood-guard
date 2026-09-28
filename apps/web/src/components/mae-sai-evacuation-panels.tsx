"use client";

/**
 * Side-panel cards for the Mae Sai replay's population, evacuation-access and shelter analysis.
 * Every figure here is a model scenario on the reconstructed flood (T1), never an observation.
 */

import { memo, useId, useState, type ReactNode } from "react";

import {
  densityLegend,
  externalChecksByRole,
  formatHourStamp,
  formatShortDate,
  rgbaCss,
  TIMELINE_END_T,
  type AccessInfo,
  type ExternalCheck,
  type Language,
  type PopulationInfo,
  type ReportedRole,
  type ReportedShelter,
  type ShelterCandidate,
  type ShelterInfo,
  type TambonProps,
  type TimelineManifest,
  type TimelineStats,
} from "@/lib/flood-timeline";
import {
  candidateReasons,
  countedInReportedSet,
  evacuationEquityGap,
  osmReference,
  otherCandidates,
  planSites,
  reportedSetExclusions,
  reportedShelterCheck,
  reportedSiteCounts,
  reportedSiteRole,
  shareOfAchievable,
  type AccessSnapshot,
  type EquityGap,
  type PlannedShelter,
  type ReportedCheck,
} from "@/lib/flood-timeline-evacuation";
import type { ShelterSetChoice } from "@/lib/flood-timeline-link";

import styles from "./mae-sai-flood-timeline.module.css";

type Translate = (en: string, th: string) => string;
const translator = (language: Language): Translate => (en, th) => (language === "th" ? th : en);

/** Whole people with thousands separators (the page uses Arabic digits in both languages). */
export const formatPeople = (value: number): string => Math.round(value).toLocaleString("en-US");
const percent = (share: number, digits = 0) => `${(share * 100).toFixed(digits)}%`;
const metres = (value: number, language: Language) => `${value.toFixed(2)} ${language === "th" ? "ม." : "m"}`;

const CANDIDATE_KINDS: Record<string, [string, string]> = {
  school: ["School", "โรงเรียน"],
  worship: ["Place of worship", "ศาสนสถาน"],
  government: ["Government office", "หน่วยงานราชการ"],
  community: ["Community centre", "ศูนย์ชุมชน"],
};
const REPORTED_TYPES: Record<string, [string, string]> = {
  government_office: ["Government office", "สำนักงานราชการ"],
  temple: ["Temple", "วัด"],
  stadium_or_hall: ["Hall or stadium", "หอประชุมหรือสนามกีฬา"],
  hospital: ["Health facility", "สถานพยาบาล"],
  other: ["Other site", "สถานที่อื่น"],
};
const EVIDENCE_STRENGTH: Record<string, [string, string]> = {
  official: ["Official source", "แหล่งข้อมูลทางการ"],
  multiple_media: ["Several media reports", "รายงานสื่อหลายแหล่ง"],
  single_media: ["One media report", "รายงานสื่อแหล่งเดียว"],
};
const LOCATION_METHODS: Record<string, [string, string]> = {
  osm_feature: ["OpenStreetMap feature", "ตำแหน่งจาก OpenStreetMap"],
  approximate_from_description: ["Approximate, from the description", "ประมาณจากคำบรรยาย"],
  official_listing_coordinates: ["Coordinates from an official listing", "พิกัดจากรายชื่อทางการ"],
  geocoded_address: ["Geocoded address", "พิกัดจากการแปลงที่อยู่"],
  unknown: ["Unknown", "ไม่ทราบ"],
};
const CONFIDENCE: Record<string, [string, string]> = { high: ["high", "สูง"], medium: ["medium", "ปานกลาง"], low: ["low", "ต่ำ"] };

const pick = (table: Record<string, [string, string]>, key: string, language: Language) => {
  const entry = table[key];
  return entry ? entry[language === "th" ? 1 : 0] : key.replaceAll("_", " ");
};
export const candidateKindLabel = (kind: string, language: Language) => pick(CANDIDATE_KINDS, kind, language);
export const reportedTypeLabel = (type: string, language: Language) => pick(REPORTED_TYPES, type, language);
export const evidenceLabel = (strength: string, language: Language) => pick(EVIDENCE_STRENGTH, strength, language);
export const locationMethodLabel = (method: string, language: Language) => pick(LOCATION_METHODS, method, language);
export const confidenceLabel = (level: string, language: Language) => pick(CONFIDENCE, level, language);

/** Candidate name, or "Unnamed place of worship (OSM way 123)" when OpenStreetMap has none. */
export function candidateTitle(candidate: Pick<ShelterCandidate, "name" | "kind" | "source">, language: Language): string {
  const name = candidate.name.trim();
  if (name) return name;
  const reference = osmReference(candidate.source);
  const osm = reference ? `OSM ${reference.type} ${reference.id}` : candidate.source;
  const kind = candidateKindLabel(candidate.kind, language);
  return language === "th" ? `${kind}ไม่มีชื่อ (${osm})` : `Unnamed ${kind.toLowerCase()} (${osm})`;
}

/** Capacity estimate with its basis, or why it is unknown. */
export function capacityText(candidate: Pick<ShelterCandidate, "capacity_est" | "footprint_m2">, shelters: Pick<ShelterInfo, "method">, language: Language): string {
  const t = translator(language);
  const { m2_per_person: perPerson, usable_floor_share: usable } = shelters.method;
  const share = Math.round(usable * 100);
  if (candidate.capacity_est === null) {
    return t(
      "Capacity unknown: no mapped building footprint on OpenStreetMap.",
      "ไม่ทราบความจุ: ไม่มีขอบเขตอาคารใน OpenStreetMap",
    );
  }
  return t(
    `Capacity ≈ ${formatPeople(candidate.capacity_est)} people (${formatPeople(candidate.footprint_m2)} m² mapped footprint × ${share}% usable ÷ ${perPerson} m² per person, Sphere minimum)`,
    `ความจุ ≈ ${formatPeople(candidate.capacity_est)} คน (พื้นที่อาคารใน OSM ${formatPeople(candidate.footprint_m2)} ตร.ม. × ใช้ได้ ${share}% ÷ ${perPerson} ตร.ม. ต่อคน ตามเกณฑ์ขั้นต่ำ Sphere)`,
  );
}

/**
 * Freeboard (height of the site above the modelled water surface) at the modelled peak. A site outside the terrain
 * model (manifest `m` false) gets no model result at all.
 */
export function freeboardText(site: Pick<ShelterCandidate, "freeboard_m" | "high_ground" | "m">, language: Language): string {
  const t = translator(language);
  if (!site.m) {
    return t(
      "Not modelled: the site lies outside the terrain model, so there is no freeboard or flood result for it.",
      "ไม่ได้จำลอง: สถานที่อยู่นอกแบบจำลองภูมิประเทศ จึงไม่มีผลระยะพ้นน้ำหรือผลน้ำท่วมสำหรับสถานที่นี้",
    );
  }
  if (site.high_ground) return t("High ground: above every modelled flood level.", "พื้นที่สูง: สูงกว่าระดับน้ำท่วมทุกระดับในแบบจำลอง");
  if (site.freeboard_m === null) return t("Freeboard at the modelled peak unknown.", "ไม่ทราบระยะพ้นน้ำที่ระดับสูงสุดของแบบจำลอง");
  if (site.freeboard_m < 0) {
    return t(
      `Floods at the modelled peak (≈ ${metres(-site.freeboard_m, "en")} of reconstructed water).`,
      `ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง (น้ำจำลองลึก ≈ ${metres(-site.freeboard_m, "th")})`,
    );
  }
  return t(`Freeboard at the modelled peak: ${metres(site.freeboard_m, "en")}.`, `ระยะพ้นน้ำที่ระดับสูงสุดของแบบจำลอง: ${metres(site.freeboard_m, "th")}`);
}

/** Why a candidate was screened out, with the method's thresholds. */
export function ineligibleReasonText(reason: string, shelters: Pick<ShelterInfo, "method">, language: Language): string {
  const t = translator(language);
  const { freeboard_m: freeboard, snap_max_m: snap } = shelters.method;
  if (reason === "floods_or_under_freeboard_at_peak") {
    return t(`Floods, or keeps less than ${freeboard} m freeboard, at the modelled peak`, `ถูกน้ำท่วมหรือสูงกว่าระดับน้ำไม่ถึง ${freeboard} ม. ที่ระดับสูงสุดของแบบจำลอง`);
  }
  if (reason === "no_road_within_400m") return t(`No mapped road node within ${snap} m`, `ไม่มีจุดเชื่อมถนนในแผนที่ภายใน ${snap} ม.`);
  if (reason === "outside_model") return t("Outside the terrain model (no flood result)", "อยู่นอกแบบจำลองภูมิประเทศ (ไม่มีผลน้ำท่วม)");
  return reason.replaceAll("_", " ");
}

/** Role, first use and access-set status of a reported site, from its manifest fields. */
export function reportedRoleText(shelter: Pick<ReportedShelter, "role" | "first_use" | "in_access_set" | "lat" | "lon">, language: Language): string {
  const t = translator(language);
  const counted = countedInReportedSet(shelter)
    ? t("counted in the access set", "นับรวมในชุดการเข้าถึง")
    : t("not counted in the access set", "ไม่นับรวมในชุดการเข้าถึง");
  return `${reportedRoleLabel(shelter.role, language)} · ${t("first use", "เริ่มใช้")} ${firstUseText(shelter.first_use, language)} · ${counted}`;
}

/** A reported site's role as the manifest states it: an overnight shelter or a relief command centre. */
export function reportedRoleLabel(role: ReportedRole, language: Language): string {
  const t = translator(language);
  return role === "relief_command_centre"
    ? t("Relief command centre (not a shelter)", "ศูนย์บัญชาการและจุดช่วยเหลือ (ไม่ใช่ที่พักพิง)")
    : t("Shelter", "ที่พักพิง");
}

/** Manifest `first_use` ("2024-09-21" or "2024-09-15 or earlier") as a local date; any other wording as given. */
export function firstUseText(firstUse: string, language: Language): string {
  const match = /^(\d{4}-\d{2}-\d{2})(\s+or earlier)?$/i.exec(firstUse.trim());
  if (!match) return firstUse;
  const date = formatShortDate(match[1], language);
  if (!match[2]) return date;
  return language === "th" ? `${date} หรือก่อนหน้า` : `${date} or earlier`;
}

/** Whether the "reported_2024" access set counts a reported site, as a short line. */
export function reportedSetStatusText(shelter: Pick<ReportedShelter, "lat" | "lon" | "in_access_set">, language: Language): string {
  const t = translator(language);
  if (countedInReportedSet(shelter)) return t("Counted in the reported-set access scenario", "นับรวมในสถานการณ์การเข้าถึงของชุดที่มีรายงาน");
  if (shelter.in_access_set) {
    return t("Not counted in the reported-set access scenario: not located on the map", "ไม่นับรวมในสถานการณ์การเข้าถึงของชุดที่มีรายงาน: ไม่มีตำแหน่งบนแผนที่");
  }
  return t("Not counted in the reported-set access scenario", "ไม่นับรวมในสถานการณ์การเข้าถึงของชุดที่มีรายงาน");
}

/** Planning theme a card relates to, stated as a theme only: this replay computes no FPPS score and assigns no action class. */
export function ThemeEyebrow({ prefix, theme, language }: { prefix?: string; theme: "protect_lives" | "keep_routes"; language: Language }) {
  const t = translator(language);
  const name = theme === "protect_lives" ? t("PROTECT LIVES NOW", "ปกป้องชีวิตทันที") : t("KEEP ROUTES OPEN", "รักษาเส้นทางให้สัญจรได้");
  return (
    <p className={styles.eyebrow}>
      {prefix ? `${prefix} · ` : ""}{t("THEME", "ประเด็น")}: {name} · {t("NO ACTION CLASS ASSIGNED", "ไม่ได้กำหนดกลุ่มการดำเนินการ")}
    </p>
  );
}

/**
 * Confidence class, its reason and the source timestamp that the manifest gives for the figures in a card (the manifest
 * text stays in its English original). `children` adds card-specific status lines before the timestamp.
 */
export function ProvenanceNote({ kind, confidence, reason, timestamp, language, children }: {
  kind: "access" | "plan" | "reported";
  confidence: string;
  reason?: string;
  timestamp: string;
  language: Language;
  children?: ReactNode;
}) {
  const t = translator(language);
  const level = confidenceLabel(confidence.toLowerCase(), language);
  return (
    <p className={styles.provenance} data-testid={`${kind}-provenance`}>
      <span className={styles.confidence}>{t("CONFIDENCE", "ความเชื่อมั่น")}: {language === "th" ? level : level.toUpperCase()}</span>{" "}
      {reason && <><span lang="en">{reason}</span>{" "}</>}
      {children}{children ? " " : null}
      {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: <span lang="en">{timestamp}</span>{language === "en" ? "." : ""}
    </p>
  );
}

/** Reminder that the water behind a scenario card is the assumed-stage reconstruction, not a gauge record. */
const assumedWaterText = (language: Language) => translator(language)(
  "Water comes from the assumed stages, not a gauge record.",
  "น้ำมาจากระดับน้ำสมมุติ ไม่ใช่ข้อมูลสถานีวัดน้ำ",
);

/** Model-check sentence for a reported shelter. */
export function reportedCheckText(check: ReportedCheck, shelters: Pick<ShelterInfo, "method">, language: Language): string {
  const t = translator(language);
  const peak = shelters.method.peak_stage_m;
  switch (check.status) {
    case "not_located":
      return t("Not located on the map (no reliable coordinates), so the model cannot check it.", "ไม่ได้ระบุตำแหน่งบนแผนที่ (ไม่มีพิกัดที่เชื่อถือได้) จึงตรวจกับแบบจำลองไม่ได้");
    case "not_modelled":
      return t(
        "Not modelled: the site lies outside the terrain model, so there is no flood result for it.",
        "ไม่ได้จำลอง: สถานที่อยู่นอกแบบจำลองภูมิประเทศ จึงไม่มีผลน้ำท่วมสำหรับสถานที่นี้",
      );
    case "floods":
      return check.freeboard !== null && check.freeboard < 0
        ? t(`The model says this site floods at the modelled peak (≈ ${metres(-check.freeboard, "en")} of reconstructed water at a ${peak} m stage).`,
          `แบบจำลองระบุว่าสถานที่นี้ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง (น้ำจำลองลึก ≈ ${metres(-check.freeboard, "th")} ที่ระดับน้ำ ${peak} ม.)`)
        : t("The model says this site floods at the modelled peak.", "แบบจำลองระบุว่าสถานที่นี้ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง");
    case "high_ground":
      return t("Model check: high ground, above every modelled flood level.", "ตรวจกับแบบจำลอง: เป็นพื้นที่สูง สูงกว่าระดับน้ำท่วมทุกระดับในแบบจำลอง");
    case "dry":
      return t(`Model check: dry at the modelled peak (${peak} m stage) with ${metres(check.freeboard, "en")} freeboard.`,
        `ตรวจกับแบบจำลอง: แห้งที่ระดับสูงสุดของแบบจำลอง (${peak} ม.) โดยสูงกว่าระดับน้ำ ${metres(check.freeboard, "th")}`);
    default:
      return t("Model check unavailable.", "ตรวจกับแบบจำลองไม่ได้");
  }
}

/** Manifest occupancy text without its own leading "Occupancy:" label (the page supplies a translated one). */
export const occupancyText = (shelter: Pick<ReportedShelter, "reported_capacity_or_occupancy">): string | null =>
  shelter.reported_capacity_or_occupancy?.replace(/^\s*occupancy\s*:\s*/i, "") || null;

export const reportedName = (shelter: Pick<ReportedShelter, "name_en" | "name_th">, language: Language) => (language === "th" ? shelter.name_th : shelter.name_en);

// --- People in flood water ------------------------------------------------------------------------------

/** Modelled residents in reconstructed water: district total and per subdistrict, with the WorldPop caveat. */
export function PeopleInWaterCard({ population, stats, names, scale, language }: {
  population: PopulationInfo;
  stats: TimelineStats;
  names: Record<string, TambonProps>;
  /** Largest subdistrict value over the keyframes, for bar lengths. */
  scale: number;
  language: Language;
}) {
  const t = translator(language);
  const residents = Object.values(population.tambon_totals).reduce((sum, value) => sum + value, 0);
  const perTambon = stats.tambon_people_in_water ?? {};
  return (
    <section className={styles.card} aria-labelledby="mae-sai-people-title">
      <ThemeEyebrow theme="protect_lives" language={language} />
      <h2 id="mae-sai-people-title">{t("People in flood water (model)", "ประชากรในพื้นที่น้ำท่วม (แบบจำลอง)")}</h2>
      <dl className={styles.kpis}>
        <div>
          <dt>{t("Modelled residents in reconstructed water now", "ผู้อยู่อาศัยตามแบบจำลองในพื้นที่น้ำจำลองขณะนี้")}</dt>
          <dd data-tone="alert" data-testid="people-in-water">{formatPeople(stats.people_in_water ?? 0)}</dd>
        </div>
        <div>
          <dt>{t("Modelled residents in the eight subdistricts", "ผู้อยู่อาศัยตามแบบจำลองใน 8 ตำบล")}</dt>
          <dd>{formatPeople(residents)}</dd>
        </div>
      </dl>
      <p className={styles.muted}>{t(
        `${population.source}, ${population.timestamp} (${population.licence}): modelled residents, not a census count, not the 2024 population and not visitors or traders at the border market. A home counts when its 10 m cell is under the reconstructed water; the river channel is excluded.`,
        `${population.source} ${population.timestamp} (${population.licence}): ผู้อยู่อาศัยตามแบบจำลอง ไม่ใช่ตัวเลขสำมะโน ไม่ใช่ประชากรปี 2024 และไม่รวมนักท่องเที่ยวหรือผู้ค้าที่ตลาดชายแดน นับบ้านเมื่อช่อง 10 ม. อยู่ใต้น้ำจำลอง ไม่รวมร่องน้ำ`,
      )}</p>
      <h3>{t("People in flood water by subdistrict", "ประชากรในพื้นที่น้ำท่วมรายตำบล")}</h3>
      <ul className={styles.bars}>
        {Object.entries(perTambon).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([id, value]) => (
          <li key={id}>
            <span className={styles.barName}><span>{names[id]?.[language] ?? id}</span></span>
            <span className={styles.barTrack} aria-hidden="true"><span className={styles.barPeople} style={{ width: `${Math.min(100, (value / Math.max(scale, 1)) * 100)}%` }} /></span>
            <span className={styles.barValue}>{formatPeople(value)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Legend of the residents heat ramp, in people per hectare decoded from the raster's cap. */
export function DensityLegend({ maxPerHa, language, wetOnly }: { maxPerHa: number; language: Language; wetOnly: boolean }) {
  const t = translator(language);
  const classes = densityLegend(maxPerHa);
  const label = (min: number, max: number, last: boolean) => {
    const value = (number: number) => (number < 10 ? number.toFixed(number % 1 ? 1 : 0) : Math.round(number).toString());
    if (min === 0) return `< ${value(max)}`;
    return last ? `≥ ${value(min)}` : `${value(min)}–${value(max)}`;
  };
  return (
    <div>
      <strong>{wetOnly
        ? t("People in flood water: residents per hectare (WorldPop 2020, model)", "ประชากรในพื้นที่น้ำท่วม: คนต่อเฮกตาร์ (WorldPop 2020 แบบจำลอง)")
        : t("All residents per hectare (WorldPop 2020, modelled)", "ผู้อยู่อาศัยทั้งหมด คนต่อเฮกตาร์ (WorldPop 2020 แบบจำลอง)")}</strong>
      <ul>
        {classes.map((item, index) => (
          <li key={item.min}><i style={{ background: rgbaCss(item.rgba) }} />{label(item.min, item.max, index === classes.length - 1)}</li>
        ))}
        {wetOnly && <li><i className={styles.wetEmpty} />{t("Wet, no mapped residents", "น้ำท่วม ไม่มีผู้อยู่อาศัยในข้อมูล")}</li>}
      </ul>
      <small className={styles.legendNote}>{t(
        `Log scale, capped at ${maxPerHa.toFixed(1)} people/ha (99.5th percentile).`,
        `มาตราส่วนลอการิทึม สูงสุดที่ ${maxPerHa.toFixed(1)} คน/เฮกตาร์ (เปอร์เซ็นไทล์ที่ 99.5)`,
      )}</small>
    </div>
  );
}

// --- Evacuation access ----------------------------------------------------------------------------------

function equityText(gap: EquityGap, language: Language): string {
  if (language === "en") return gap.interpretation;
  const ratio = gap.ratio === null ? "" : String(gap.ratio);
  switch (gap.status) {
    case "no_vulnerable_denominator": return "คำนวณช่องว่างความเท่าเทียมไม่ได้: ไม่มีประชากรกลุ่มเปราะบางเป็นตัวหาร";
    case "no_non_vulnerable_denominator": return "คำนวณช่องว่างความเท่าเทียมไม่ได้: ไม่มีประชากรกลุ่มอื่นเป็นตัวหาร";
    case "no_loss": return "ไม่พบช่องว่าง: ทั้งสองกลุ่มไม่สูญเสียการเข้าถึง";
    case "undefined_ratio": return "หาอัตราส่วนไม่ได้ เพราะกลุ่มเปราะบางสูญเสียการเข้าถึงขณะที่กลุ่มอื่นไม่สูญเสียเลย";
    default:
      return gap.band === "higher"
        ? `กลุ่มเปราะบางมีโอกาสสูญเสียการเข้าถึงมากกว่ากลุ่มอื่น ${ratio} เท่า`
        : gap.band === "lower"
          ? `กลุ่มเปราะบางมีโอกาสสูญเสียการเข้าถึงเป็น ${ratio} เท่าของกลุ่มอื่น`
          : "อัตราการสูญเสียการเข้าถึงของทั้งสองกลุ่มใกล้เคียงกัน";
  }
}

/** People who lost access over the whole replay for the selected set, with the playhead. */
export function AccessChart({ series, time, language, label }: { series: Float64Array; time: number; language: Language; label: string }) {
  const t = translator(language);
  const width = 360;
  const height = 150;
  const margin = { left: 44, right: 10, top: 14, bottom: 22 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const peak = series.reduce((best, value) => Math.max(best, value), 0);
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(peak, 1)));
  const yMax = Math.max(10, Math.ceil(peak / magnitude) * magnitude);
  const hours = series.length;
  const x = (hour: number) => margin.left + (hour / (TIMELINE_END_T * 24)) * plotW;
  const y = (value: number) => margin.top + plotH - (value / yMax) * plotH;
  let line = "";
  for (let hour = 0; hour < hours; hour += 1) {
    line += `${hour ? "L" : "M"}${x(hour).toFixed(1)} ${y(series[hour]).toFixed(1)} L${x(hour + 1).toFixed(1)} ${y(series[hour]).toFixed(1)} `;
  }
  const area = `${line}L${x(hours).toFixed(1)} ${y(0).toFixed(1)} L${x(0).toFixed(1)} ${y(0).toFixed(1)} Z`;
  const now = Math.min(hours - 1, Math.max(0, Math.floor(time * 24 + 1e-6)));
  const peakHour = series.findIndex((value) => value === peak);
  const summary = t(
    `${label}: people who lost walking access to a dry shelter, 9–19 Sep. Peak ${formatPeople(peak)}${peakHour >= 0 ? ` at ${formatHourStamp(peakHour, "en")}` : ""}; now ${formatPeople(series[now] ?? 0)}.`,
    `${label}: ผู้ที่สูญเสียการเดินถึงที่พักพิงที่แห้ง 9–19 ก.ย. สูงสุด ${formatPeople(peak)} คน${peakHour >= 0 ? ` เมื่อ ${formatHourStamp(peakHour, "th")}` : ""} ขณะนี้ ${formatPeople(series[now] ?? 0)} คน`,
  );
  return (
    <figure className={styles.miniChart}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
        {[0, 0.5, 1].map((share) => (
          <g key={share}>
            <line x1={margin.left} x2={width - margin.right} y1={y(yMax * share)} y2={y(yMax * share)} className={styles.gridLine} />
            <text x={margin.left - 6} y={y(yMax * share) + 3.5} textAnchor="end" className={styles.axisText}>{formatPeople(yMax * share)}</text>
          </g>
        ))}
        {Array.from({ length: TIMELINE_END_T }, (_, day) => (
          <text key={day} x={x(day * 24 + 12)} y={height - 8} textAnchor="middle" className={styles.axisText}>{9 + day}</text>
        ))}
        <path d={area} className={styles.lostArea} />
        <path d={line} className={styles.lostLine} />
        <line x1={x(time * 24)} x2={x(time * 24)} y1={margin.top - 6} y2={y(0)} className={styles.playhead} />
        <circle cx={x(time * 24)} cy={y(series[now] ?? 0)} r={4.5} className={styles.playDot} />
      </svg>
      <figcaption>{t("People who lost walking access to a dry shelter (scenario), 9–19 Sep, local days", "ผู้ที่สูญเสียการเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลอง) 9–19 ก.ย. ตามวันท้องถิ่น")}</figcaption>
    </figure>
  );
}

/**
 * Evacuation access at this stage for the chosen shelter set: who has no dry shelter within a 2 km walk (lost
 * during the flood versus never within reach), per subdistrict, the Evacuation Equity Gap and the replay curve.
 */
export function AccessCard({
  access, shelters, snapshot, series, time, names, tambonTotals, shelterSet, planK, onShelterSet, onPlanK, showCutoff, onShowCutoff, language, status,
}: {
  access: AccessInfo;
  shelters: ShelterInfo;
  snapshot: AccessSnapshot | null;
  series: Float64Array | null;
  time: number;
  names: Record<string, TambonProps>;
  tambonTotals: Float64Array | null;
  shelterSet: ShelterSetChoice;
  planK: number;
  onShelterSet: (value: ShelterSetChoice) => void;
  onPlanK: (value: number) => void;
  showCutoff: boolean;
  onShowCutoff: (value: boolean) => void;
  language: Language;
  status: "loading" | "ready" | "error";
}) {
  const t = translator(language);
  const sliderId = useId();
  const distanceKm = access.threshold_m / 1000;
  const setLabel = shelterSet === "reported"
    ? t("Shelters reported used in Sep 2024", "ที่พักพิงที่มีรายงานว่าใช้จริงในเดือน ก.ย. 2024")
    : t(`Ranked plan, first ${planK} site${planK === 1 ? "" : "s"}`, `แผนจัดอันดับ ${planK} แห่งแรก`);
  const gap = snapshot ? evacuationEquityGap({
    vulnerableLost: snapshot.lost.vulnerable,
    vulnerableTotal: access.totals.vulnerable,
    nonVulnerableLost: snapshot.lost.nonVulnerable,
    nonVulnerableTotal: access.totals.non_vulnerable,
  }) : null;
  const without = snapshot ? snapshot.lost.population + snapshot.never.population : 0;
  const counted = reportedSiteCounts(shelters).counted;
  const exclusions = shelterSet === "reported" ? reportedSetExclusions(shelters) : [];
  return (
    <section className={styles.card} aria-labelledby="mae-sai-access-title" data-testid="access-card">
      <p className={styles.eyebrow}>{t("SCENARIO (T1 MODEL) · EVACUATION ACCESS", "สถานการณ์จำลอง (T1) · การเข้าถึงการอพยพ")}</p>
      <h2 id="mae-sai-access-title">{t("Walking access to a dry shelter (scenario)", "การเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลอง)")}</h2>
      <p className={styles.muted}>{t(
        `Planning scenario, not observed evacuation outcomes: modelled residents at road nodes who can still walk to an open, dry shelter of the chosen set within ${distanceKm} km on roads that are still passable (about 30 minutes at 4 km/h). A road closes at 0.3 m of reconstructed depth and a shelter stops serving once water reaches it; levels every 0.05 m of the assumed stage.`,
        `สถานการณ์เพื่อการวางแผน ไม่ใช่ผลการอพยพที่สังเกตได้จริง: ผู้อยู่อาศัยตามแบบจำลองที่จุดถนนซึ่งยังเดินถึงที่พักพิงที่เปิดและแห้งของชุดที่เลือกได้ภายใน ${distanceKm} กม. บนถนนที่ยังสัญจรได้ (ประมาณ 30 นาทีที่ 4 กม./ชม.) ถนนปิดเมื่อน้ำจำลองลึก 0.3 ม. และที่พักพิงหยุดใช้งานเมื่อน้ำถึง ประเมินทุก 0.05 ม. ของระดับน้ำสมมุติ`,
      )}</p>
      <ProvenanceNote kind="access" confidence={access.confidence} reason={access.confidence_reason} timestamp={access.source_timestamp} language={language}>
        {assumedWaterText(language)}
      </ProvenanceNote>
      <fieldset className={styles.segmented}>
        <legend>{t("Shelter set", "ชุดที่พักพิง")}</legend>
        <div>
          <label>
            <input type="radio" name="mae-sai-shelter-set" value="reported" checked={shelterSet === "reported"} onChange={() => onShelterSet("reported")} />
            <span>{t(`Reported used in Sep 2024 (${counted} sites counted)`, `มีรายงานว่าใช้ ก.ย. 2024 (นับ ${counted} แห่ง)`)}</span>
          </label>
          <label>
            <input type="radio" name="mae-sai-shelter-set" value="plan" checked={shelterSet === "plan"} onChange={() => onShelterSet("plan")} />
            <span>{t("Ranked plan", "แผนจัดอันดับ")}</span>
          </label>
        </div>
      </fieldset>
      {shelterSet === "plan" && shelters.plan.length > 0 && (
        <div className={styles.kField}>
          <label htmlFor={sliderId}>{t(`Plan size k = ${planK}`, `จำนวนที่พักพิงในแผน k = ${planK}`)}{planK === shelters.knee_k ? t(" (default: the knee)", " (ค่าเริ่มต้น: จุดหักเห)") : ""}</label>
          <input id={sliderId} type="range" min={1} max={shelters.plan.length} step={1} value={planK}
            aria-valuetext={t(`${planK} of ${shelters.plan.length} ranked sites`, `${planK} จาก ${shelters.plan.length} แห่งที่จัดอันดับ`)}
            onChange={(event) => onPlanK(Number(event.target.value))} />
          <span className={styles.muted}>1 … {shelters.plan.length}</span>
        </div>
      )}
      {shelterSet === "reported" && (
        <p className={styles.caveat} data-testid="reported-set-caveat">
          {t(
            `The ${counted} counted sites are assumed open for the whole replay, from before the flood.`,
            `สมมุติว่าสถานที่ที่นับรวม ${counted} แห่งเปิดใช้ตลอดช่วงการย้อนดู ตั้งแต่ก่อนน้ำท่วม`,
          )}
          {" "}{t("Which sites count", "เกณฑ์การนับ")}: <span lang="en">{shelters.reported_access_set_rule}</span>
          {exclusions.length > 0 && <>
            {" "}{t("Mapped but not counted", "แสดงบนแผนที่แต่ไม่นับรวม")}:{" "}
            {exclusions.map((shelter) => reportedName(shelter, language)).join("; ")}{language === "en" ? "." : ""}
          </>}
        </p>
      )}
      {status === "error" ? (
        <p className={styles.warningNote} role="alert">{t("The access scenario could not be loaded; the other figures remain available.", "โหลดสถานการณ์การเข้าถึงไม่สำเร็จ ตัวเลขอื่นยังใช้ได้")}</p>
      ) : !snapshot ? (
        <p className={styles.muted} role="status">{t("Preparing the access scenario…", "กำลังเตรียมสถานการณ์การเข้าถึง…")}</p>
      ) : (
        <>
          <dl className={styles.kpis}>
            <div className={styles.kpiWide}>
              <dt>{t(`No dry shelter of this set within a ${distanceKm} km walk, now`, `ไม่มีที่พักพิงที่แห้งของชุดนี้ในระยะเดิน ${distanceKm} กม. ขณะนี้`)}</dt>
              <dd data-tone="alert" data-testid="access-without">{formatPeople(without)}<small> / {formatPeople(access.totals.population)}</small></dd>
            </div>
            <div>
              <dt>{t("Lost access during the flood", "สูญเสียการเข้าถึงระหว่างน้ำท่วม")}</dt>
              <dd data-tone="alert" data-testid="access-lost">{formatPeople(snapshot.lost.population)}</dd>
            </div>
            <div>
              <dt>{t("Never had one within reach, even before the flood", "ไม่มีในระยะเดินแม้ก่อนน้ำท่วม")}</dt>
              <dd data-tone="warn">{formatPeople(snapshot.never.population)}</dd>
            </div>
          </dl>
          <p className={styles.muted}>{setLabel} · {t("modelled residents (WorldPop 2020) at road nodes", "ผู้อยู่อาศัยตามแบบจำลอง (WorldPop 2020) ที่จุดถนน")}</p>
          {gap && (
            <div className={styles.equity} data-testid="equity-gap">
              <p>
                <strong>{t("Evacuation Equity Gap", "ช่องว่างความเท่าเทียมในการอพยพ")}: {gap.ratio === null ? t("undefined", "หาค่าไม่ได้") : gap.ratio}</strong>
                {" · "}<span>{equityText(gap, language)}</span>
              </p>
              {gap.vulnerableRate !== null && gap.nonVulnerableRate !== null && (
                <p className={styles.muted}>{t(
                  `Proxy-vulnerable residents who lost access: ${percent(gap.vulnerableRate, 2)} (${formatPeople(snapshot.lost.vulnerable)} of ${formatPeople(access.totals.vulnerable)}); everyone else: ${percent(gap.nonVulnerableRate, 2)} (${formatPeople(snapshot.lost.nonVulnerable)} of ${formatPeople(access.totals.non_vulnerable)}).`,
                  `กลุ่มเปราะบางตามตัวแทนที่สูญเสียการเข้าถึง: ${percent(gap.vulnerableRate, 2)} (${formatPeople(snapshot.lost.vulnerable)} จาก ${formatPeople(access.totals.vulnerable)}) กลุ่มอื่น: ${percent(gap.nonVulnerableRate, 2)} (${formatPeople(snapshot.lost.nonVulnerable)} จาก ${formatPeople(access.totals.non_vulnerable)})`,
                )}</p>
              )}
              <p className={styles.muted}>{t(
                "Ratio of loss rates (vulnerable ÷ everyone else); above 1.2 means vulnerable residents are more likely to lose access, below 0.8 less likely. “Vulnerable” is this repository's terrain/remoteness proxy (homes on slopes of 8° or more, or 750 m or more from a drivable road), not demographic vulnerability such as age, disability or income.",
                "อัตราส่วนของอัตราการสูญเสีย (กลุ่มเปราะบาง ÷ กลุ่มอื่น) มากกว่า 1.2 หมายถึงกลุ่มเปราะบางมีโอกาสสูญเสียการเข้าถึงมากกว่า ต่ำกว่า 0.8 หมายถึงน้อยกว่า “กลุ่มเปราะบาง” ในที่นี้เป็นตัวแทนจากภูมิประเทศและความห่างไกล (บ้านบนความลาดชัน 8° ขึ้นไป หรือห่างถนนที่รถวิ่งได้ 750 ม. ขึ้นไป) ไม่ใช่ความเปราะบางทางประชากร เช่น อายุ ความพิการ หรือรายได้",
              )}</p>
            </div>
          )}
          <h3>{t("Without a dry shelter within reach, by subdistrict", "ไม่มีที่พักพิงที่แห้งในระยะเดิน รายตำบล")}</h3>
          <ul className={styles.stackLegend} aria-hidden="true">
            <li><i className={styles.segLost} />{t("lost during the flood", "สูญเสียระหว่างน้ำท่วม")}</li>
            <li><i className={styles.segNever} />{t("never within reach", "ไม่เคยอยู่ในระยะ")}</li>
          </ul>
          <ul className={styles.bars}>
            {access.tambons.map((id, place) => ({ id, lost: snapshot.lostByTambon[place] ?? 0, never: snapshot.neverByTambon[place] ?? 0, total: tambonTotals?.[place] ?? 0 }))
              .sort((a, b) => (b.lost + b.never) - (a.lost + a.never) || a.id.localeCompare(b.id))
              .map(({ id, lost, never, total }) => (
                <li key={id}>
                  <span className={styles.barName}><span>{names[id]?.[language] ?? id}</span></span>
                  <span className={`${styles.barTrack} ${styles.stackTrack}`} aria-hidden="true">
                    <span className={styles.segLost} style={{ width: `${total > 0 ? Math.min(100, (lost / total) * 100) : 0}%` }} />
                    <span className={styles.segNever} style={{ width: `${total > 0 ? Math.min(100, (never / total) * 100) : 0}%` }} />
                  </span>
                  <span className={styles.barValue} title={t(`lost ${formatPeople(lost)} · never ${formatPeople(never)} · of ${formatPeople(total)}`, `สูญเสีย ${formatPeople(lost)} · ไม่เคย ${formatPeople(never)} · จาก ${formatPeople(total)}`)}>
                    {formatPeople(lost + never)}
                    <span className={styles.srOnly}>{t(` (lost ${formatPeople(lost)}, never within reach ${formatPeople(never)}, of ${formatPeople(total)} residents)`, ` (สูญเสีย ${formatPeople(lost)} ไม่เคยอยู่ในระยะ ${formatPeople(never)} จากผู้อยู่อาศัย ${formatPeople(total)})`)}</span>
                  </span>
                </li>
              ))}
          </ul>
          {series && <AccessChart series={series} time={time} language={language} label={setLabel} />}
          <label className={styles.inlineToggle}>
            <input type="checkbox" checked={showCutoff} onChange={(event) => onShowCutoff(event.target.checked)} />
            {t("Show people cut off on the map (population-weighted)", "แสดงผู้ที่ถูกตัดขาดบนแผนที่ (ถ่วงน้ำหนักตามประชากร)")}
          </label>
        </>
      )}
    </section>
  );
}

// --- Shelters ------------------------------------------------------------------------------------------

/** Cumulative coverage of the ranked plan against k, pre-emptive and late, with the knee and the chosen k. */
export function CoverageCurve({ shelters, k, language }: { shelters: ShelterInfo; k: number; language: Language }) {
  const t = translator(language);
  const plan = shelters.plan;
  const width = 360;
  const height = 196;
  // Tick labels and the axis title sit 20 units apart so they stay clear at the larger mobile font size.
  const margin = { left: 38, right: 12, top: 16, bottom: 38 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const n = plan.length;
  const x = (rank: number) => margin.left + (n > 1 ? ((rank - 1) / (n - 1)) * plotW : plotW / 2);
  const y = (share: number) => margin.top + plotH - share * plotH;
  const path = (key: "cumulative_share" | "late_cumulative_share") =>
    plan.map((entry, index) => `${index ? "L" : "M"}${x(index + 1).toFixed(1)} ${y(entry[key]).toFixed(1)}`).join(" ");
  const knee = shelters.knee_k;
  const chosen = plan[k - 1];
  const summary = t(
    `Coverage of the ${formatPeople(shelters.demand_people)} residents whose homes flood at the modelled peak, by plan size: ${percent(plan[0]?.cumulative_share ?? 0)} with 1 site, ${percent(plan[knee - 1]?.cumulative_share ?? 0)} with ${knee} (the knee), ${percent(plan.at(-1)?.cumulative_share ?? 0)} with ${n}. Selected k = ${k}: ${percent(chosen?.cumulative_share ?? 0)} pre-emptive, ${percent(chosen?.late_cumulative_share ?? 0)} late.`,
    `ความครอบคลุมผู้อยู่อาศัย ${formatPeople(shelters.demand_people)} คนที่บ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ตามจำนวนที่พักพิง: ${percent(plan[0]?.cumulative_share ?? 0)} เมื่อมี 1 แห่ง ${percent(plan[knee - 1]?.cumulative_share ?? 0)} เมื่อมี ${knee} แห่ง (จุดหักเห) ${percent(plan.at(-1)?.cumulative_share ?? 0)} เมื่อมี ${n} แห่ง ที่เลือก k = ${k}: อพยพล่วงหน้า ${percent(chosen?.cumulative_share ?? 0)} อพยพล่าช้า ${percent(chosen?.late_cumulative_share ?? 0)}`,
  );
  return (
    <figure className={styles.miniChart}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
        {[0, 0.25, 0.5, 0.75, 1].map((share) => (
          <g key={share}>
            <line x1={margin.left} x2={width - margin.right} y1={y(share)} y2={y(share)} className={styles.gridLine} />
            <text x={margin.left - 6} y={y(share) + 3.5} textAnchor="end" className={styles.axisText}>{percent(share)}</text>
          </g>
        ))}
        {plan.map((_, index) => (
          <text key={index} x={x(index + 1)} y={margin.top + plotH + 15} textAnchor="middle" className={styles.axisText}>{index + 1}</text>
        ))}
        <text x={margin.left + plotW / 2} y={height - 3} textAnchor="middle" className={styles.axisText}>{t("k (sites in the plan)", "k (จำนวนที่พักพิงในแผน)")}</text>
        {chosen && <rect x={x(k) - 9} y={margin.top - 6} width={18} height={plotH + 6} className={styles.kBand} />}
        <line x1={x(knee)} x2={x(knee)} y1={margin.top - 6} y2={y(0)} className={styles.kneeLine} />
        <text x={x(knee) + 5} y={margin.top + 4} className={styles.kneeText}>{t(`knee k = ${knee}`, `จุดหักเห k = ${knee}`)}</text>
        <path d={path("cumulative_share")} className={styles.coverLine} />
        <path d={path("late_cumulative_share")} className={styles.coverLateLine} />
        {chosen && (
          <>
            <circle cx={x(k)} cy={y(chosen.cumulative_share)} r={5} className={styles.coverDot} />
            <circle cx={x(k)} cy={y(chosen.late_cumulative_share)} r={4.5} className={styles.coverLateDot} />
          </>
        )}
      </svg>
      <figcaption>
        <ul className={styles.curveLegend}>
          <li><i className={styles.curveSolid} aria-hidden="true" />{t("Pre-emptive evacuation (roads normal)", "อพยพล่วงหน้า (ถนนปกติ)")}</li>
          <li><i className={styles.curveDashed} aria-hidden="true" />{t(`Late evacuation (roads still open at a ${shelters.method.late_evacuation_stage_m} m stage)`, `อพยพล่าช้า (ถนนที่ยังเปิดที่ระดับน้ำ ${shelters.method.late_evacuation_stage_m} ม.)`)}</li>
        </ul>
      </figcaption>
    </figure>
  );
}

const THAI_SCRIPT = /[฀-๿]/;
const textLang = (value: string, language: Language) => (THAI_SCRIPT.test(value) ? "th" : language);

function PlannedSiteItem({ site, shelters, language, onShow }: {
  site: PlannedShelter;
  shelters: ShelterInfo;
  language: Language;
  onShow: (id: string) => void;
}) {
  const t = translator(language);
  const title = candidateTitle(site.candidate, language);
  return (
    <li>
      <span className={styles.routeHead}>
        <span className={styles.planRank} aria-hidden="true">{site.rank}</span>
        <strong lang={textLang(title, language)}>{title}</strong>
      </span>
      <span className={styles.routeMeta}>{candidateKindLabel(site.candidate.kind, language)} · {freeboardText(site.candidate, language)}</span>
      <span className={styles.routeMeta}>{capacityText(site.candidate, shelters, language)}</span>
      <span className={styles.routeFigures}>
        <span>{t(`Assigned ≈ ${formatPeople(site.load)} residents`, `รับผู้อพยพ ≈ ${formatPeople(site.load)} คน`)}</span>
        {site.shortfall && site.capacity !== null && (
          <span className={styles.shortfall}>{t(`Over capacity by ≈ ${formatPeople(site.load - site.capacity)}`, `เกินความจุ ≈ ${formatPeople(site.load - site.capacity)} คน`)}</span>
        )}
      </span>
      <button type="button" className={styles.linkButton} onClick={() => onShow(site.candidate.id)} aria-label={t(`Show plan site ${site.rank}, ${title}, on the map`, `แสดงสถานที่ในแผนลำดับ ${site.rank} ${title} บนแผนที่`)}>
        {t("Show on map", "แสดงบนแผนที่")}
      </button>
    </li>
  );
}

/**
 * Ranked shelter plan (planning scenario): coverage curve, the first k sites with loads and capacity, and the gap.
 * Memoised: it does not depend on the replay clock, so playback does not re-render it.
 */
export const ShelterPlanCard = memo(function ShelterPlanCard({ shelters, k, onPlanK, language, onShowCandidate }: {
  shelters: ShelterInfo;
  k: number;
  onPlanK: (value: number) => void;
  language: Language;
  onShowCandidate: (id: string) => void;
}) {
  const t = translator(language);
  const sliderId = useId();
  if (shelters.plan.length === 0) return null;
  const sites = planSites(shelters, k);
  const knee = shelters.knee_k;
  const kneeShare = Math.round(shareOfAchievable(shelters.plan, knee) * 100);
  const shortfalls = sites.filter((site) => site.shortfall).length;
  const unknown = sites.filter((site) => site.capacity === null).length;
  return (
    <section className={styles.card} aria-labelledby="mae-sai-plan-title" data-testid="shelter-plan-card">
      <ThemeEyebrow prefix={t("PLANNING SCENARIO", "สถานการณ์เพื่อการวางแผน")} theme="protect_lives" language={language} />
      <h2 id="mae-sai-plan-title">{t("Where dry shelters would help most (ranked plan)", "ที่พักพิงที่แห้งควรอยู่ที่ใด (แผนจัดอันดับ)")}</h2>
      <p className={styles.muted}>{t(
        `A planning scenario, not an official shelter list: OpenStreetMap schools, places of worship, government offices and community centres that keep ${shelters.method.freeboard_m} m freeboard at the modelled peak (${shelters.method.peak_stage_m} m stage) and lie within ${shelters.method.snap_max_m} m of a road (${shelters.eligible_count} of ${shelters.candidates.length} candidates), ranked greedily by how many of the ${formatPeople(shelters.demand_people)} residents whose homes flood at the peak each adds within a ${shelters.method.threshold_m / 1000} km walk.`,
        `สถานการณ์เพื่อการวางแผน ไม่ใช่รายชื่อที่พักพิงทางการ: โรงเรียน ศาสนสถาน หน่วยงานราชการ และศูนย์ชุมชนจาก OpenStreetMap ที่สูงกว่าระดับน้ำอย่างน้อย ${shelters.method.freeboard_m} ม. ที่ระดับสูงสุดของแบบจำลอง (${shelters.method.peak_stage_m} ม.) และอยู่ห่างถนนไม่เกิน ${shelters.method.snap_max_m} ม. (${shelters.eligible_count} จาก ${shelters.candidates.length} แห่ง) จัดอันดับแบบละโมบตามจำนวนผู้อยู่อาศัยที่บ้านถูกน้ำท่วมที่ระดับสูงสุด (${formatPeople(shelters.demand_people)} คน) ซึ่งแต่ละแห่งเพิ่มความครอบคลุมได้ภายในระยะเดิน ${shelters.method.threshold_m / 1000} กม.`,
      )}</p>
      <ProvenanceNote kind="plan" confidence={shelters.confidence} reason={shelters.confidence_reason} timestamp={shelters.source_timestamp} language={language} />
      <CoverageCurve shelters={shelters} k={k} language={language} />
      <p>{t(
        `Ranked range, not a fixed number: the first k entries are the plan for k shelters; the default k = ${knee} is the smallest plan that reaches 90% of the achievable coverage (${kneeShare}%).`,
        `เป็นช่วงที่จัดอันดับ ไม่ใช่จำนวนตายตัว: k รายการแรกคือแผนสำหรับที่พักพิง k แห่ง ค่าเริ่มต้น k = ${knee} คือแผนที่เล็กที่สุดที่ครอบคลุมถึง 90% ของความครอบคลุมที่ทำได้ (${kneeShare}%)`,
      )}</p>
      <div className={styles.kField}>
        <label htmlFor={sliderId}>{t(`Sites in the plan: k = ${k}`, `จำนวนแห่งในแผน: k = ${k}`)}</label>
        <input id={sliderId} type="range" min={1} max={shelters.plan.length} step={1} value={k}
          aria-valuetext={t(`${k} of ${shelters.plan.length} ranked sites`, `${k} จาก ${shelters.plan.length} แห่งที่จัดอันดับ`)}
          onChange={(event) => onPlanK(Number(event.target.value))} />
      </div>
      <div className={styles.gapCallout} role="note">
        <strong>{t("Shelter gap", "ช่องว่างของที่พักพิง")}</strong>
        <p>{t(
          `${formatPeople(shelters.uncoverable_people)} residents in the modelled peak flood zone have no eligible dry site within a ${shelters.method.threshold_m / 1000} km walk even with every candidate — candidates for new or temporary shelters, or vertical evacuation.`,
          `ผู้อยู่อาศัย ${formatPeople(shelters.uncoverable_people)} คนในพื้นที่น้ำท่วมสูงสุดของแบบจำลองไม่มีสถานที่ที่แห้งและเข้าเกณฑ์ภายในระยะเดิน ${shelters.method.threshold_m / 1000} กม. แม้ใช้ทุกแห่งที่เป็นไปได้ — ควรพิจารณาที่พักพิงใหม่หรือชั่วคราว หรือการอพยพขึ้นที่สูงในอาคาร`,
        )}</p>
      </div>
      <h3>{t(`The first ${k} site${k === 1 ? "" : "s"} of the plan`, `${k} แห่งแรกของแผน`)}</h3>
      <ol className={styles.planList}>
        {sites.map((site) => (
          <PlannedSiteItem key={site.candidate.id} site={site} shelters={shelters} language={language} onShow={onShowCandidate} />
        ))}
      </ol>
      <p className={styles.muted}>{t(
        `Loads assign each covered resident to the nearest site of this plan. ${shortfalls > 0 ? `${shortfalls} site${shortfalls === 1 ? " is" : "s are"} over the capacity estimate. ` : ""}${unknown > 0 ? `${unknown} site${unknown === 1 ? " has" : "s have"} no capacity estimate (OpenStreetMap building coverage in Mae Sai is sparse, so capacities are unknown or underestimated). ` : ""}Candidates and loads are model outputs; check any site on the ground before planning with it.`,
        `ภาระคือจำนวนผู้อยู่อาศัยที่ได้รับการครอบคลุมซึ่งจัดให้ไปยังที่พักพิงที่ใกล้ที่สุดของแผนนี้ ${shortfalls > 0 ? `มี ${shortfalls} แห่งที่เกินความจุประมาณการ ` : ""}${unknown > 0 ? `มี ${unknown} แห่งที่ไม่มีค่าประมาณความจุ (ข้อมูลอาคารใน OpenStreetMap ของแม่สายยังมีน้อย ความจุจึงไม่ทราบหรือต่ำกว่าจริง) ` : ""}สถานที่และภาระเป็นผลจากแบบจำลอง ควรตรวจสอบในพื้นที่ก่อนใช้วางแผน`,
      )}</p>
    </section>
  );
});

function CandidateItem({ candidate, shelters, language, onShow }: {
  candidate: ShelterCandidate;
  shelters: ShelterInfo;
  language: Language;
  onShow: (id: string) => void;
}) {
  const t = translator(language);
  const title = candidateTitle(candidate, language);
  const reasons = candidateReasons(candidate);
  return (
    <li data-eligible={candidate.eligible || undefined}>
      <strong lang={textLang(title, language)}>{title}</strong>
      <span className={styles.routeMeta}>{candidateKindLabel(candidate.kind, language)} · {freeboardText(candidate, language)}</span>
      {reasons.length > 0 && (
        <span className={styles.candidateReasons}>{t("Not eligible", "ไม่เข้าเกณฑ์")}: {reasons.map((reason) => ineligibleReasonText(reason, shelters, language)).join("; ")}</span>
      )}
      <span className={styles.routeMeta}>{capacityText(candidate, shelters, language)}</span>
      <button type="button" className={styles.linkButton} onClick={() => onShow(candidate.id)} aria-label={t(`Show ${title} on the map`, `แสดง ${title} บนแผนที่`)}>
        {t("Show on map", "แสดงบนแผนที่")}
      </button>
    </li>
  );
}

/** The two candidate lists, eligible (outside the first k) and not eligible, with reasons, capacity and model check. */
export function OtherCandidatesList({ shelters, k, language, onShowCandidate }: {
  shelters: ShelterInfo;
  k: number;
  language: Language;
  onShowCandidate: (id: string) => void;
}) {
  const t = translator(language);
  const { eligible, ineligible } = otherCandidates(shelters, k);
  const item = (candidate: ShelterCandidate) => (
    <CandidateItem key={candidate.id} candidate={candidate} shelters={shelters} language={language} onShow={onShowCandidate} />
  );
  return (
    <>
      <p className={styles.muted}>{t(
        "The candidates the map draws as green rings (eligible) and small grey dots (not eligible), listed here so they can be reached without a pointer. Planning scenario from OpenStreetMap, not an official list; model checks are at the modelled peak.",
        "สถานที่ที่แผนที่แสดงเป็นวงกลมสีเขียว (เข้าเกณฑ์) และจุดสีเทาขนาดเล็ก (ไม่เข้าเกณฑ์) แสดงเป็นรายการที่นี่เพื่อให้เข้าถึงได้โดยไม่ต้องใช้เมาส์ เป็นสถานการณ์เพื่อการวางแผนจาก OpenStreetMap ไม่ใช่รายชื่อทางการ ผลตรวจกับแบบจำลองเป็นค่าที่ระดับสูงสุดของแบบจำลอง",
      )}</p>
      {eligible.length > 0 && (
        <>
          <h3>{t(`Eligible, not in the first ${k} (${eligible.length})`, `เข้าเกณฑ์ แต่ไม่อยู่ใน ${k} แห่งแรก (${eligible.length})`)}</h3>
          <ul className={styles.candidateList}>{eligible.map(item)}</ul>
        </>
      )}
      {ineligible.length > 0 && (
        <>
          <h3>{t(`Not eligible (${ineligible.length})`, `ไม่เข้าเกณฑ์ (${ineligible.length})`)}</h3>
          <ul className={`${styles.candidateList} ${styles.candidateListIneligible}`}>{ineligible.map(item)}</ul>
        </>
      )}
    </>
  );
}

/**
 * Collapsible card with every plan candidate the map shows only as an SVG ring or dot (keyboard and screen-reader
 * users cannot open those popups). The list is built only while the card is open.
 */
export const OtherCandidatesCard = memo(function OtherCandidatesCard({ shelters, k, language, onShowCandidate }: {
  shelters: ShelterInfo;
  k: number;
  language: Language;
  onShowCandidate: (id: string) => void;
}) {
  const t = translator(language);
  const [open, setOpen] = useState(false);
  const { eligible, ineligible } = otherCandidates(shelters, k);
  if (eligible.length + ineligible.length === 0) return null;
  return (
    <details className={styles.card} data-testid="other-candidates-card" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{t(
        `Other shelter candidates: ${eligible.length} eligible outside the first ${k}, ${ineligible.length} not eligible`,
        `สถานที่อื่นที่เป็นไปได้: เข้าเกณฑ์นอก ${k} แห่งแรก ${eligible.length} แห่ง ไม่เข้าเกณฑ์ ${ineligible.length} แห่ง`,
      )}</summary>
      {open && <OtherCandidatesList shelters={shelters} k={k} language={language} onShowCandidate={onShowCandidate} />}
    </details>
  );
});

function ReportedShelterItem({ shelter, shelters, language, onShow }: { shelter: ReportedShelter; shelters: ShelterInfo; language: Language; onShow: (id: string) => void }) {
  const t = translator(language);
  const check = reportedShelterCheck(shelter);
  const located = check.status !== "not_located";
  const other = language === "th" ? shelter.name_en : shelter.name_th;
  const command = reportedSiteRole(shelter).role === "relief_command";
  const roleText = reportedRoleText(shelter, language);
  return (
    <li data-role={command ? "relief_command" : "shelter"}>
      <details>
        <summary>
          <span className={command ? styles.reportedCommand : styles.reportedStar} aria-hidden="true" data-located={located || undefined}>{command ? "◆" : "★"}</span>
          <strong lang={language}>{reportedName(shelter, language)}</strong>
          {roleText && <span className={styles.reportedRole}>{roleText}</span>}
          <span className={styles.reportedCheck} data-status={check.status}>{reportedCheckText(check, shelters, language)}</span>
        </summary>
        <dl className={styles.reportedFacts}>
          <div><dt>{t("Other name", "ชื่ออื่น")}</dt><dd lang={language === "th" ? "en" : "th"}>{other}</dd></div>
          <div><dt>{t("Type", "ประเภท")}</dt><dd>{reportedTypeLabel(shelter.type, language)}</dd></div>
          <div><dt>{t("Period used", "ช่วงที่ใช้")}</dt>{shelter.period_used ? <dd lang="en">{shelter.period_used}</dd> : <dd>{t("Not reported", "ไม่มีรายงาน")}</dd>}</div>
          <div><dt>{t("Occupancy", "จำนวนผู้พักพิง")}</dt>{occupancyText(shelter) ? <dd lang="en">{occupancyText(shelter)}</dd> : <dd>{t("Not reported", "ไม่มีรายงาน")}</dd>}</div>
          <div><dt>{t("Evidence", "หลักฐาน")}</dt><dd>{pick(EVIDENCE_STRENGTH, shelter.evidence_strength, language)}</dd></div>
          <div><dt>{t("Location", "ตำแหน่ง")}</dt><dd>
            {pick(LOCATION_METHODS, shelter.location_method, language)} · {t("confidence", "ความเชื่อมั่น")} {pick(CONFIDENCE, shelter.location_confidence, language)}
            {shelter.location_evidence && <span className={styles.muted} lang="en"> — {shelter.location_evidence}</span>}
          </dd></div>
          <div><dt>{t("Access scenario", "สถานการณ์การเข้าถึง")}</dt><dd>
            {reportedSetStatusText(shelter, language)}.
            {" "}<span className={styles.muted} lang="en">{shelter.access_set_note}</span>
          </dd></div>
          {shelter.notes && <div><dt>{t("Notes", "หมายเหตุ")}</dt><dd lang="en">{shelter.notes}</dd></div>}
        </dl>
        <h4>{t("Sources", "แหล่งข้อมูล")}</h4>
        <ul className={styles.sourceList}>
          {shelter.sources.map((source) => (
            <li key={`${source.url}|${source.date}|${source.title}`}>
              <span lang={THAI_SCRIPT.test(source.title) ? "th" : "en"}>{source.title}</span>
              {" — "}{source.publisher}, {source.date}.{" "}
              <a href={source.url} target="_blank" rel="noopener noreferrer">{source.url}</a>
              <span className={styles.muted} lang="en"> {source.quote_or_paraphrase}</span>
            </li>
          ))}
        </ul>
        {located && (
          <button type="button" className={styles.linkButton} onClick={() => onShow(shelter.id)} aria-label={t(`Show ${shelter.name_en} on the map`, `แสดง${shelter.name_th}บนแผนที่`)}>
            {t("Show on map", "แสดงบนแผนที่")}
          </button>
        )}
      </details>
    </li>
  );
}

/**
 * Sites reported in use during the 2024 flood (public reporting), each with its role and model check. Memoised: it
 * does not depend on the replay clock, so playback does not re-render its ~850 elements.
 */
export const ReportedSheltersCard = memo(function ReportedSheltersCard({ shelters, language, onShowReported }: {
  shelters: ShelterInfo;
  language: Language;
  onShowReported: (id: string) => void;
}) {
  const t = translator(language);
  if (shelters.reported.length === 0) return null;
  const located = shelters.reported.filter((shelter) => reportedShelterCheck(shelter).status !== "not_located");
  const unlocated = shelters.reported.filter((shelter) => reportedShelterCheck(shelter).status === "not_located");
  const flooding = located.filter((shelter) => reportedShelterCheck(shelter).status === "floods").length;
  const command = shelters.reported.filter((shelter) => reportedSiteRole(shelter).role === "relief_command").length;
  const total = shelters.reported.length;
  const title = command > 0
    ? t(
      `Sites reported in use (${total}): ${total - command} shelters, ${command} relief and command site${command === 1 ? "" : "s"}`,
      `สถานที่ที่มีรายงานว่าใช้จริง (${total}): ที่พักพิง ${total - command} แห่ง ศูนย์บัญชาการและจุดช่วยเหลือ ${command} แห่ง`,
    )
    : t(`Shelters reported in use (${total})`, `ที่พักพิงที่มีรายงานว่าใช้จริง (${total})`);
  return (
    <section className={styles.card} aria-labelledby="mae-sai-reported-title" data-testid="reported-shelters-card">
      <p className={styles.eyebrow}>{t("PUBLIC REPORTING · SEPTEMBER 2024", "รายงานสาธารณะ · กันยายน 2024")}</p>
      <h2 id="mae-sai-reported-title">{title}</h2>
      <p className={styles.muted}>{t(
        `Compiled from news and official updates, with sources. ${located.length} are placed on the map (stars${command > 0 ? "; a diamond marks a relief and command site" : ""}) and checked against the reconstruction; ${flooding} of them flood at the modelled peak, a flag to verify rather than a finding. ${unlocated.length} could not be located and are listed without a pin.`,
        `รวบรวมจากข่าวและรายงานทางการ พร้อมแหล่งที่มา ${located.length} แห่งแสดงบนแผนที่ (ดาว${command > 0 ? " ส่วนรูปข้าวหลามตัดคือศูนย์บัญชาการและจุดช่วยเหลือ" : ""}) และตรวจกับการจำลอง ในจำนวนนี้ ${flooding} แห่งถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ซึ่งเป็นข้อสังเกตที่ต้องตรวจสอบ ไม่ใช่ข้อสรุป อีก ${unlocated.length} แห่งระบุตำแหน่งไม่ได้จึงแสดงเฉพาะในรายการ`,
      )}</p>
      <ProvenanceNote kind="reported" confidence={shelters.confidence} reason={shelters.reported_status} timestamp={`reported list compiled ${shelters.reported_compiled}; ${shelters.source_timestamp}`} language={language}>
        <span lang="en">{shelters.reported_access_set_rule}</span>
      </ProvenanceNote>
      {language === "th" && <p className={styles.muted}>ช่วงเวลา จำนวนผู้พักพิง หมายเหตุ และคำอธิบายแหล่งข้อมูลคงไว้เป็นภาษาอังกฤษตามต้นฉบับ</p>}
      <ul className={styles.reportedList}>
        {[...located, ...unlocated].map((shelter) => (
          <ReportedShelterItem key={shelter.id} shelter={shelter} shelters={shelters} language={language} onShow={onShowReported} />
        ))}
      </ul>
    </section>
  );
});

type CheckManifest = Pick<TimelineManifest, "external_checks" | "stage_anchors" | "tambon_histograms" | "hand" | "pixel_area_m2" | "impassable_depth_m" | "population" | "model_coverage">;

function ExternalCheckItem({ check, manifest, language }: { check: ExternalCheck; manifest: CheckManifest; language: Language }) {
  const t = translator(language);
  const modelKm2 = Number(check.model_km2.toFixed(1));
  const modelled = Math.round(manifest.model_coverage.modelled_km2);
  const district = Math.round(manifest.model_coverage.district_km2);
  return (
    <li>
      <span lang="en">{check.observed}</span>{": "}
      {t(`reported ${check.reported_km2} km²`, `รายงาน ${check.reported_km2} ตร.กม.`)}
      {check.reported_people !== undefined && t(` and ≈ ${formatPeople(check.reported_people)} people exposed`, ` และประชากรที่ได้รับผลกระทบ ≈ ${formatPeople(check.reported_people)} คน`)}
      {" "}(<span lang={textLang(check.reported_text, "en")}>{check.reported_text}</span>){language === "en" ? "." : ""}{" "}
      {check.role === "calibration_anchor" ? (
        <>
          {t(
            `The model gives ${modelKm2} km²${check.model_stage_m !== undefined ? ` at the ${check.model_stage_m} m stage tuned to it` : ""}.`,
            `แบบจำลองให้ค่า ${modelKm2} ตร.กม.${check.model_stage_m !== undefined ? ` ที่ระดับน้ำ ${check.model_stage_m} ม. ซึ่งปรับให้ตรงกับตัวเลขนี้` : ""}`,
          )}{" "}
          <span className={styles.muted}>{t(
            "This figure was used to set the model's stage, so the agreement holds by construction and does not test the model.",
            "ตัวเลขนี้ใช้กำหนดระดับน้ำของแบบจำลอง ค่าที่ตรงกันจึงเกิดจากการปรับแบบจำลอง ไม่ใช่การทดสอบแบบจำลอง",
          )}{" "}<span lang="en">({check.use})</span></span>
        </>
      ) : (
        <>
          {t(
            `The model gives ${modelKm2} km²${check.model_people_in_water !== undefined ? ` and ≈ ${formatPeople(check.model_people_in_water)} modelled residents in water` : ""}${check.model_stage_m !== undefined ? ` at a ${check.model_stage_m} m stage` : ""}`,
            `แบบจำลองให้ค่า ${modelKm2} ตร.กม.${check.model_people_in_water !== undefined ? ` และผู้อยู่อาศัยตามแบบจำลองในน้ำ ≈ ${formatPeople(check.model_people_in_water)} คน` : ""}${check.model_stage_m !== undefined ? ` ที่ระดับน้ำ ${check.model_stage_m} ม.` : ""}`,
          )}
          {check.model_window && <>{" "}(<span lang="en">{check.model_window}</span>)</>}{language === "en" ? "." : ""}{" "}
          {check.model_peak_km2 !== undefined && t(
            `For reference, the modelled peak gives ${Number(check.model_peak_km2.toFixed(1))} km²${check.model_peak_people_in_water !== undefined ? ` and ≈ ${formatPeople(check.model_peak_people_in_water)} residents in water` : ""}.`,
            `เพื่อเปรียบเทียบ ระดับสูงสุดของแบบจำลองให้ค่า ${Number(check.model_peak_km2.toFixed(1))} ตร.กม.${check.model_peak_people_in_water !== undefined ? ` และผู้อยู่อาศัยในน้ำ ≈ ${formatPeople(check.model_peak_people_in_water)} คน` : ""}`,
          )}{" "}
          <span className={styles.muted}>{t(
            `Model figures cover the modelled part of Mae Sai district (${modelled} of ${district} km²).`,
            `ตัวเลขแบบจำลองครอบคลุมเฉพาะส่วนที่จำลองของอำเภอแม่สาย (${modelled} จาก ${district} ตร.กม.)`,
          )}{" "}{t("Magnitude check only, not a spatial validation.", "ใช้ตรวจขนาดเท่านั้น ไม่ใช่การยืนยันตำแหน่ง")}{" "}<span lang="en">{check.use}</span></span>
        </>
      )}
      {check.urls.map((url) => (
        <span key={url}>{" "}<a href={url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{url}</a></span>
      ))}
    </li>
  );
}

/**
 * External size figures, split into the calibration anchor (it set a stage knot, so the model matches it by
 * construction) and independent checks (compared over the external product's own time window where it is known).
 */
export const ExternalChecks = memo(function ExternalChecks({ manifest, language }: { manifest: CheckManifest; language: Language }) {
  const t = translator(language);
  const checks = manifest.external_checks ?? [];
  if (checks.length === 0) return null;
  const { calibration, independent } = externalChecksByRole(checks);
  return (
    <div className={styles.anchor}>
      {language === "th" && <p className={styles.muted}>ชื่อผลิตภัณฑ์และข้อความอ้างอิงจากแหล่งภายนอกคงไว้เป็นภาษาต้นฉบับ</p>}
      {calibration.length > 0 && (
        <>
          <p><strong>{t("Calibration anchor (not an independent check)", "จุดอ้างอิงที่ใช้ปรับแบบจำลอง (ไม่ใช่การตรวจสอบอิสระ)")}</strong></p>
          <ul className={styles.list}>{calibration.map((check) => <ExternalCheckItem key={check.id} check={check} manifest={manifest} language={language} />)}</ul>
        </>
      )}
      {independent.length > 0 && (
        <>
          <p><strong>{t("Independent size checks", "การตรวจสอบขนาดกับแหล่งอิสระ")}</strong></p>
          <ul className={styles.list}>{independent.map((check) => <ExternalCheckItem key={check.id} check={check} manifest={manifest} language={language} />)}</ul>
        </>
      )}
    </div>
  );
});
