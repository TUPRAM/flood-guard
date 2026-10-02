"use client";

/**
 * Side-panel cards for the Mae Sai replay's population, evacuation-access and shelter analysis.
 * Every figure here is a model scenario on the reconstructed flood (T1), never an observation.
 */

import { memo, useId, useLayoutEffect, useReducer, useRef, useState, type ReactNode } from "react";

import {
  checkDifference,
  coverageComplete,
  densityLegend,
  externalChecksByRole,
  formatHourStamp,
  formatShortDate,
  rgbaCss,
  smallestFloodedExtent,
  thaiYear,
  TIMELINE_END_T,
  formatDateWithYear,
  formatFileSize,
  type AccessInfo,
  type CapacityPlanRow,
  type CheckerRole,
  type ExportFile,
  type ExternalCheck,
  type Language,
  type PopulationInfo,
  type ReportedRole,
  type ReportedShelter,
  type ShelterCandidate,
  type ShelterCheckRow,
  type ShelterInfo,
  type TambonProps,
  type TimelineManifest,
  type TimelineStats,
} from "@/lib/flood-timeline";
import { GLOSSARY, localizedText, placeNameText, plainManifestText, type GlossaryId } from "@/lib/flood-timeline-copy";
import {
  accessEquityGap,
  candidateReasons,
  capacityAwareView,
  capacityFlag,
  countedInReportedSet,
  EQUITY_MIN_GROUP,
  equityRuleSentence,
  equityWhy,
  equityWording,
  osmReference,
  otherCandidates,
  overCapacitySites,
  planCoverageSentence,
  planSites,
  reportedSetExclusions,
  reportedShelterCheck,
  reportedSiteCounts,
  reportedSiteRole,
  robustCore,
  whatIfLevels,
  type AccessCutoff,
  type AccessGroupSums,
  type AccessScope,
  type AccessSnapshot,
  type CapacityCounts,
  type PlannedShelter,
  type ReportedCheck,
  type SetComparison,
} from "@/lib/flood-timeline-evacuation";
import { TIP_CLOSED, tipOpen, tipReducer, tooltipShift } from "@/lib/flood-timeline-layout";
import type { AccessScopeChoice, ShelterSetChoice } from "@/lib/flood-timeline-link";

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
/** Who checked a candidate: a role, never a name (the codes of the verification sheet). */
const CHECKER_ROLES: Record<CheckerRole, [string, string]> = {
  ddpm_officer: ["a DDPM officer", "เจ้าหน้าที่ ปภ."],
  local_government_officer: ["a tambon or municipality officer", "เจ้าหน้าที่ อบต. หรือเทศบาล"],
  village_leader: ["a village head or kamnan", "ผู้ใหญ่บ้านหรือกำนัน"],
  site_staff: ["staff of the site", "เจ้าหน้าที่ของสถานที่"],
  project_team: ["the FloodGuard project team", "ทีมโครงการ FloodGuard"],
  other_local_contact: ["another local contact", "ผู้ประสานงานในพื้นที่อื่น ๆ"],
};

const pick = (table: Record<string, [string, string]>, key: string, language: Language) => {
  const entry = table[key];
  return entry ? entry[language === "th" ? 1 : 0] : key.replaceAll("_", " ");
};
export const candidateKindLabel = (kind: string, language: Language) => pick(CANDIDATE_KINDS, kind, language);
export const reportedTypeLabel = (type: string, language: Language) => pick(REPORTED_TYPES, type, language);
export const evidenceLabel = (strength: string, language: Language) => pick(EVIDENCE_STRENGTH, strength, language);
export const locationMethodLabel = (method: string, language: Language) => pick(LOCATION_METHODS, method, language);
export const confidenceLabel = (level: string, language: Language) => pick(CONFIDENCE, level, language);

/**
 * Candidate name (in English, a Thai-only name gets a type label first: "Mosque · มัสยิด…"), or "Unnamed place of
 * worship (OSM way 123)" when OpenStreetMap has none.
 */
export function candidateTitle(candidate: Pick<ShelterCandidate, "name" | "kind" | "source">, language: Language): string {
  const name = candidate.name.trim();
  if (name) return placeNameText(name, language, candidateKindLabel(candidate.kind, "en"));
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
 * One-line confidence chip for a card; it opens to the confidence reason, card-specific method notes (`children`) and
 * the source timestamp the manifest gives for the card's figures. Manifest sentences are shown in Thai where the page
 * knows a translation, otherwise in their English original. The shared "How to read these numbers" box explains the
 * classes once for the whole page.
 */
export function ProvenanceNote({ kind, confidence, reason, timestamp, language, children }: {
  kind: "access" | "plan" | "capacity" | "robustness" | "verification" | "reported" | "impact" | "people" | "routes";
  confidence: string;
  reason?: string;
  timestamp: string;
  language: Language;
  children?: ReactNode;
}) {
  const t = translator(language);
  const level = confidenceLabel(confidence.toLowerCase(), language);
  const why = reason ? localizedText(reason, language) : null;
  const when = localizedText(timestamp, language);
  return (
    <details className={styles.provenance} data-testid={`${kind}-provenance`}>
      <summary>
        <span className={styles.confidence}>{t("CONFIDENCE", "ความเชื่อมั่น")}: {language === "th" ? level : level.toUpperCase()}</span>
        <span className={styles.provenanceHint}>{t("Why, method and source dates", "เหตุผล วิธีการ และวันที่ของข้อมูล")}</span>
      </summary>
      <p>
        {why && <><span lang={why.lang}>{why.text}</span>{" "}</>}
        {children}{children ? " " : null}
        {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: <span lang={when.lang}>{when.text}</span>{language === "en" ? "." : ""}
      </p>
    </details>
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

/** Left and right edges (viewport px) a tooltip must stay between: the viewport, narrowed by every clipping ancestor. */
function horizontalClip(element: HTMLElement): [number, number] {
  let left = 0;
  let right = document.documentElement.clientWidth;
  for (let node = element.parentElement; node && node !== document.body; node = node.parentElement) {
    if (getComputedStyle(node).overflowX === "visible") continue;
    const box = node.getBoundingClientRect();
    left = Math.max(left, box.left);
    right = Math.min(right, box.right);
  }
  return [left, right];
}

/**
 * A technical term with its short definition on hover or keyboard focus (the definition is also the term's
 * accessible description). Escape closes the definition without moving the pointer or the focus, and the box is
 * moved sideways so it never leaves the viewport. Definitions come from the page glossary, which "How to read these
 * numbers" lists in full.
 */
export function Term({ id, language, children }: { id: GlossaryId; language: Language; children: ReactNode }) {
  const tipId = useId();
  const tip = useRef<HTMLSpanElement | null>(null);
  const [state, dispatch] = useReducer(tipReducer, TIP_CLOSED);
  const open = tipOpen(state);
  useLayoutEffect(() => {
    const element = tip.current;
    if (!open || !element) return;
    const place = () => {
      element.style.setProperty("--fg-tip-shift", "0px");
      const box = element.getBoundingClientRect();
      const [left, right] = horizontalClip(element);
      element.style.setProperty("--fg-tip-shift", `${tooltipShift(box.left - left, box.right - left, right - left)}px`);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") dispatch("escape");
    };
    place();
    window.addEventListener("resize", place);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", place);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, language]);
  return (
    <span className={styles.term} onPointerEnter={() => dispatch("enter")} onPointerLeave={() => dispatch("leave")}>
      <span className={styles.termLabel} tabIndex={0} aria-describedby={tipId} onFocus={() => dispatch("focus")} onBlur={() => dispatch("blur")}>{children}</span>
      <span ref={tip} role="tooltip" id={tipId} className={styles.termTip} data-open={open || undefined}>{GLOSSARY[id].definition[language]}</span>
    </span>
  );
}

/** "an" before a number read with a leading vowel sound (8, 11, 18, 80–89 …), otherwise "a". */
export function indefiniteArticle(value: number): "a" | "an" {
  const digits = String(Math.round(Math.abs(value)));
  return digits.startsWith("8") || digits === "11" || digits === "18" ? "an" : "a";
}

/** Warning for a plan site with no capacity estimate or one far below the residents assigned to it; "" when neither. */
export function capacityFlagText(site: Pick<PlannedShelter, "load" | "capacity">, language: Language): string {
  const t = translator(language);
  const flag = capacityFlag(site);
  if (flag === "unknown") {
    return t("Capacity unknown (no mapped building footprint): check on the ground", "ไม่ทราบความจุ (ไม่มีขอบเขตอาคารในแผนที่): ควรตรวจสอบในพื้นที่");
  }
  if (flag === "far_below" && site.capacity !== null) {
    return t(
      `Capacity far below its load: ≈ ${formatPeople(site.capacity)} places for ≈ ${formatPeople(site.load)} residents assigned`,
      `ความจุต่ำกว่าภาระมาก: รองรับได้ ≈ ${formatPeople(site.capacity)} คน แต่ได้รับผู้อพยพ ≈ ${formatPeople(site.load)} คน`,
    );
  }
  return "";
}

// --- People in flood water ------------------------------------------------------------------------------

/**
 * Modelled residents in reconstructed water: district total and per subdistrict, with the WorldPop caveat. These are
 * population-grid counts; the access and plan cards count residents at road nodes, which the card says.
 */
export function PeopleInWaterCard({ population, stats, names, scale, language, accessResidents, demandPeople, provenance }: {
  population: PopulationInfo;
  stats: TimelineStats;
  names: Record<string, TambonProps>;
  /** Largest subdistrict value over the keyframes, for bar lengths. */
  scale: number;
  language: Language;
  /** Residents snapped to road nodes (the access card's "all residents" total), when the access scenario exists. */
  accessResidents?: number;
  /** Residents at road nodes whose home floods at the modelled peak (the plan's demand). */
  demandPeople?: number;
  /** Confidence, reason and source timestamp of the water model behind the count, for the card's confidence chip. */
  provenance?: { confidence: string; reason: string; timestamp: string };
}) {
  const t = translator(language);
  const residents = Object.values(population.tambon_totals).reduce((sum, value) => sum + value, 0);
  const perTambon = stats.tambon_people_in_water ?? {};
  const source = plainManifestText(population.source);
  const counting = t(
    "A home counts when its 10 m cell of the population grid is under the reconstructed water; the river channel is excluded.",
    "นับบ้านเมื่อช่อง 10 ม. ของกริดประชากรอยู่ใต้น้ำจำลอง ไม่รวมร่องน้ำ",
  );
  return (
    <section className={styles.card} aria-labelledby="mae-sai-people-title">
      <ThemeEyebrow theme="protect_lives" language={language} />
      <h2 id="mae-sai-people-title">{t("People in flood water (model)", "ประชากรในพื้นที่น้ำท่วม (แบบจำลอง)")}</h2>
      <dl className={styles.kpis}>
        <div>
          <dt>{t("Modelled residents in reconstructed water, at this replay hour", "ผู้อยู่อาศัยตามแบบจำลองในพื้นที่น้ำจำลอง ณ ชั่วโมงนี้ของการย้อนดู")}</dt>
          <dd data-tone="alert" data-testid="people-in-water">{formatPeople(stats.people_in_water ?? 0)}</dd>
        </div>
        <div>
          <dt>{t("Modelled residents in the eight subdistricts (population grid)", "ผู้อยู่อาศัยตามแบบจำลองใน 8 ตำบล (กริดประชากร)")}</dt>
          <dd>{formatPeople(residents)}</dd>
        </div>
      </dl>
      <p className={styles.muted}>{t(
        `${source}, ${population.timestamp} (${population.licence}): modelled residents, not a census count, not the 2024 population and not visitors or traders at the border market.`,
        `${source} ${population.timestamp} (${population.licence}): ผู้อยู่อาศัยตามแบบจำลอง ไม่ใช่ตัวเลขสำมะโน ไม่ใช่ประชากรปี ${thaiYear(2024)} และไม่รวมนักท่องเที่ยวหรือผู้ค้าที่ตลาดชายแดน`,
      )}{provenance ? null : ` ${counting}`}</p>
      {provenance && (
        <ProvenanceNote kind="people" confidence={provenance.confidence} reason={provenance.reason} timestamp={provenance.timestamp} language={language}>
          {counting}{" "}{t(`Residents: ${source}, ${population.timestamp}.`, `ผู้อยู่อาศัย: ${source} ${population.timestamp}`)}
        </ProvenanceNote>
      )}
      {accessResidents !== undefined && (
        <p className={styles.muted} data-testid="people-reconcile">{t(
          `Where the totals differ: this card counts the population grid cell by cell. The access and plan cards count the same WorldPop residents snapped to road nodes instead: ${formatPeople(accessResidents)} in all${demandPeople !== undefined ? `, of whom ${formatPeople(demandPeople)} have a home node that floods at the modelled peak` : ""}.`,
          `เหตุที่ตัวเลขรวมต่างกัน: การ์ดนี้นับตามกริดประชากรทีละช่อง ส่วนการ์ดการเข้าถึงและการ์ดแผนนับผู้อยู่อาศัย WorldPop ชุดเดียวกันที่จุดถนนแทน รวม ${formatPeople(accessResidents)} คน${demandPeople !== undefined ? ` ในจำนวนนี้ ${formatPeople(demandPeople)} คนมีจุดบ้านที่ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง` : ""}`,
        )}</p>
      )}
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
    `${label}: people who lost walking access to a dry shelter, 9–19 Sep. Peak ${formatPeople(peak)}${peakHour >= 0 ? ` at ${formatHourStamp(peakHour, "en")}` : ""}; ${formatPeople(series[now] ?? 0)} at this replay hour.`,
    `${label}: ผู้ที่สูญเสียการเดินถึงที่พักพิงที่แห้ง 9–19 ก.ย. สูงสุด ${formatPeople(peak)} คน${peakHour >= 0 ? ` เมื่อ ${formatHourStamp(peakHour, "th")}` : ""} ณ ชั่วโมงนี้ของการย้อนดู ${formatPeople(series[now] ?? 0)} คน`,
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
      <figcaption>{t(
        "People who lost walking access to a dry shelter (T1 scenario, model), 9–19 Sep, local days. Hours from illustrative stage keyframes, not observed.",
        "ผู้ที่สูญเสียการเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลองระดับ T1 แบบจำลอง) 9–19 ก.ย. ตามวันท้องถิ่น ชั่วโมงมาจากจุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่ค่าที่สังเกตได้",
      )}</figcaption>
    </figure>
  );
}

/** The shared plan-size slider label, identical on the access card and the plan card. */
const planSizeLabel = (k: number, language: Language) => translator(language)(`Plan size k = ${k}`, `ขนาดแผน k = ${k}`);

/** Live plan-size sentence under a plan-size slider, plus "(default …)" when k is the default size. */
function PlanSizeSentence({ shelters, k, language }: { shelters: ShelterInfo; k: number; language: Language }) {
  const t = translator(language);
  return (
    <p className={styles.kSentence} data-testid="plan-k-sentence">
      <span className={styles.tagModel}>{t("Model", "แบบจำลอง")}</span>{" "}
      {planCoverageSentence(shelters, k, language)}
      {k === shelters.knee_k && (
        <span className={styles.kDefault}>{t(
          " (default: the smallest plan that gets most of the benefit)",
          " (ค่าเริ่มต้น: แผนที่เล็กที่สุดที่ได้ประโยชน์ส่วนใหญ่แล้ว)",
        )}</span>
      )}
    </p>
  );
}

/** The two shelter sets the access card puts side by side: the reported sites and the first k sites of the ranked plan. */
export interface ShelterSetComparisons { reported: SetComparison | null; plan: SetComparison | null }

/** The label every scenario hour on the access card carries. */
export const hoursLabel = (language: Language): string => translator(language)(
  "Hours from illustrative stage keyframes, not observed.",
  "ชั่วโมงมาจากจุดกำหนดระดับน้ำเพื่อการอธิบาย ไม่ใช่ค่าที่สังเกตได้",
);

/** The modelled access cut-off hour as local replay time ("10 Sep 22:00"), or why the set has none. */
export function cutoffText(cutoff: AccessCutoff, language: Language): string {
  const t = translator(language);
  if (cutoff.status === "reached") return formatHourStamp(cutoff.hour, language);
  if (cutoff.status === "no_baseline") {
    return t("None: no resident of this group has a shelter of this set within reach", "ไม่มี: ไม่มีผู้อยู่อาศัยกลุ่มนี้ที่มีที่พักพิงของชุดนี้ในระยะเดิน");
  }
  return t(
    "Not reached in this replay: at least half keep access at every hour",
    "ไม่ถึงเกณฑ์ในการย้อนดูนี้: อย่างน้อยครึ่งหนึ่งยังเดินถึงได้ทุกชั่วโมง",
  );
}

const COMPARISON_SCOPES: readonly AccessScope[] = ["all", "flooded"];

/**
 * One shelter set counted both ways (all residents at road nodes, and residents whose homes flood at the modelled
 * peak): within reach before the flood, still within reach at this replay hour, newly lost with the set's own baseline
 * as denominator, and the modelled access cut-off hour. The ranked plan is built for evacuating before the flood, so
 * its table leads with the cut-off hour and a note explains its loss at the peak. No row ranks the sets.
 */
export function SetComparisonTable({ kind, title, comparison, selected, language }: {
  kind: "reported" | "plan";
  title: string;
  comparison: SetComparison;
  /** Whether this is the set the map, the chart and the subdistrict bars show. */
  selected: boolean;
  language: Language;
}) {
  const t = translator(language);
  const cell = (name: string, scope: AccessScope) => `compare-${kind}-${scope}-${name}`;
  const rows: Record<"baseline" | "keeping" | "lost" | "cutoff", ReactNode> = {
    baseline: (
      <tr key="baseline">
        <th scope="row">{t("Had a shelter of this set within reach before the flood", "มีที่พักพิงของชุดนี้ในระยะเดินก่อนน้ำท่วม")}</th>
        {COMPARISON_SCOPES.map((scope) => (
          <td key={scope} data-testid={cell("baseline", scope)}>
            {formatPeople(comparison[scope].baseline)}<small> {t(`of ${formatPeople(comparison[scope].residents)}`, `จาก ${formatPeople(comparison[scope].residents)}`)}</small>
          </td>
        ))}
      </tr>
    ),
    keeping: (
      <tr key="keeping">
        <th scope="row">{t("Still have one at this replay hour", "ยังเดินถึงได้ ณ ชั่วโมงนี้ของการย้อนดู")}</th>
        {COMPARISON_SCOPES.map((scope) => <td key={scope} data-testid={cell("keeping", scope)}>{formatPeople(comparison[scope].keeping)}</td>)}
      </tr>
    ),
    lost: (
      <tr key="lost">
        <th scope="row">
          {t("Newly lost because of the flood", "สูญเสียการเข้าถึงเพราะน้ำท่วม")}
          <small>{t("Out of those within reach before it", "จากผู้ที่เคยอยู่ในระยะเดินก่อนน้ำท่วม")}</small>
        </th>
        {COMPARISON_SCOPES.map((scope) => {
          const { lost, baseline, lostShare } = comparison[scope];
          return (
            <td key={scope} data-testid={cell("lost", scope)}>
              {lostShare === null ? "—" : <>
                {formatPeople(lost)}<small> {t(`of ${formatPeople(baseline)} (${percent(lostShare)})`, `จาก ${formatPeople(baseline)} (${percent(lostShare)})`)}</small>
              </>}
            </td>
          );
        })}
      </tr>
    ),
    cutoff: (
      <tr key="cutoff" data-lead={kind === "plan" ? "" : undefined}>
        <th scope="row">
          {t("Modelled access cut-off hour", "ชั่วโมงที่การเข้าถึงถูกตัดตามแบบจำลอง")}
          <small>{t(
            "First replay hour when fewer than half of those within reach before the flood still have access",
            "ชั่วโมงแรกของการย้อนดูที่ผู้ยังเดินถึงได้เหลือไม่ถึงครึ่งของผู้ที่เคยอยู่ในระยะเดินก่อนน้ำท่วม",
          )}</small>
        </th>
        {COMPARISON_SCOPES.map((scope) => <td key={scope} data-testid={cell("cutoff", scope)}>{cutoffText(comparison[scope].cutoff, language)}</td>)}
      </tr>
    ),
  };
  const order: (keyof typeof rows)[] = kind === "plan" ? ["cutoff", "baseline", "keeping", "lost"] : ["baseline", "keeping", "lost", "cutoff"];
  return (
    <div className={styles.setCompare} data-testid={`set-compare-${kind}`} data-selected={selected ? "" : undefined}>
      <table>
        <caption>
          {title}
          {selected && <span className={styles.setShown} data-testid="set-shown"> · {t("shown on the map and in the chart", "แสดงบนแผนที่และในกราฟ")}</span>}
        </caption>
        <thead>
          <tr>
            <td />
            <th scope="col">{t("All residents at road nodes", "ผู้อยู่อาศัยทั้งหมดที่จุดถนน")}</th>
            <th scope="col">{t("Residents whose homes flood at the peak", "ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด")}</th>
          </tr>
        </thead>
        <tbody>{order.map((name) => rows[name])}</tbody>
      </table>
      {kind === "plan" && (
        <p className={styles.muted} data-testid="plan-reading">{t(
          "How to read the plan: it is built for evacuating before the water rises, on normal roads, so its cut-off hour comes first. The loss at the modelled peak counts residents who are still at home by then; it does not grade the choice of sites.",
          "วิธีอ่านแผน: แผนนี้ออกแบบสำหรับการอพยพก่อนน้ำขึ้น บนถนนสภาพปกติ จึงแสดงชั่วโมงที่การเข้าถึงถูกตัดเป็นอันดับแรก การสูญเสียที่ระดับน้ำสูงสุดของแบบจำลองนับผู้ที่ยังอยู่บ้านในขณะนั้น ไม่ได้ใช้ตัดสินการเลือกสถานที่",
        )}</p>
      )}
    </div>
  );
}

/**
 * Evacuation access for the chosen shelter set and population scope. The card first puts the reported set and the
 * ranked plan side by side, each counted both ways (all residents at road nodes, and residents whose homes flood at
 * the modelled peak), with no single headline that ranks them. Below that, for the chosen set and scope: who is
 * without a shelter per subdistrict, the Evacuation Equity Gap (or why no ratio is shown) and the replay curve.
 * The equity block states its rule in one sentence (of the residents in each group who had a shelter within reach
 * before the flood, the share who lost it), then the ratio or the reason there is none, then both counts per group.
 */
export function AccessCard({
  access, shelters, snapshot, series, time, names, tambonTotals, shelterSet, planK, onShelterSet, onPlanK, showCutoff, onShowCutoff,
  scope, onScope, scopeTotals, allResidents, floodedResidents, comparison, language, status,
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
  /** Whose access is counted: residents whose homes flood at the modelled peak, or every resident at a road node. */
  scope: AccessScopeChoice;
  onScope: (value: AccessScopeChoice) => void;
  /** Residents (all, proxy-vulnerable, others) in the chosen scope; null until the node file is read. */
  scopeTotals: AccessGroupSums | null;
  allResidents: number;
  floodedResidents: number;
  /** The reported set and the chosen plan size, each counted for both scopes at this replay hour; null until the node file is read. */
  comparison: ShelterSetComparisons | null;
  language: Language;
  status: "loading" | "ready" | "error";
}) {
  const t = translator(language);
  const sliderId = useId();
  const distanceKm = access.threshold_m / 1000;
  const planTitle = t(`Ranked plan, first ${planK} site${planK === 1 ? "" : "s"}`, `แผนจัดอันดับ ${planK} แห่งแรก`);
  const setLabel = shelterSet === "reported"
    ? t("Shelters reported used in Sep 2024", "ที่พักพิงที่มีรายงานว่าใช้จริงในเดือน ก.ย. 2567 (2024)")
    : planTitle;
  const totals = scopeTotals ?? (scope === "all"
    ? { population: access.totals.population, vulnerable: access.totals.vulnerable, nonVulnerable: access.totals.non_vulnerable }
    : null);
  // Each group's loss rate divides by its residents with a shelter of the set within reach before the flood (R8, option B).
  const gap = snapshot && totals ? accessEquityGap(snapshot, totals) : null;
  const wording = gap ? equityWording(gap, language) : null;
  const why = gap ? equityWhy(gap, language) : null;
  const without = snapshot ? snapshot.lost.population + snapshot.never.population : 0;
  const counted = reportedSiteCounts(shelters).counted;
  const exclusions = shelterSet === "reported" ? reportedSetExclusions(shelters) : [];
  const rule = localizedText(shelters.reported_access_set_rule, language);
  const scopeText = scope === "flooded"
    ? t("residents at road nodes whose homes flood at the modelled peak", "ผู้อยู่อาศัยที่จุดถนนซึ่งบ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง")
    : t("all residents at road nodes", "ผู้อยู่อาศัยทั้งหมดที่จุดถนน");
  const total = totals ? formatPeople(totals.population) : "…";
  const reportedTitle = t(`Shelters reported used in Sep 2024 (${counted} sites counted)`, `ที่พักพิงที่มีรายงานว่าใช้จริงในเดือน ก.ย. 2567 (2024) (นับ ${counted} แห่ง)`);
  return (
    <section className={styles.card} aria-labelledby="mae-sai-access-title" data-testid="access-card">
      <p className={styles.eyebrow}>{t("T1 SCENARIO (MODEL) · EVACUATION ACCESS", "สถานการณ์จำลองระดับ T1 (แบบจำลอง) · การเข้าถึงการอพยพ")}</p>
      <h2 id="mae-sai-access-title">{t("Walking access to a dry shelter (scenario)", "การเดินถึงที่พักพิงที่แห้ง (สถานการณ์จำลอง)")}</h2>
      <p className={styles.muted}>
        {t("Planning scenario, not observed evacuation outcomes (", "สถานการณ์เพื่อการวางแผน ไม่ใช่ผลการอพยพที่สังเกตได้จริง (")}
        <Term id="t1" language={language}>{t("T1 scenario", "สถานการณ์จำลองระดับ T1")}</Term>
        {t("): modelled residents at ", "): ผู้อยู่อาศัยตามแบบจำลองที่")}
        <Term id="road_nodes" language={language}>{t("road nodes", "จุดถนน")}</Term>
        {t(
          ` who can still walk to an open, dry shelter of the chosen set within ${distanceKm} km on roads that are still passable (about 30 minutes on foot).`,
          `ซึ่งยังเดินถึงที่พักพิงที่เปิดและแห้งของชุดที่เลือกได้ภายใน ${distanceKm} กม. บนถนนที่ยังสัญจรได้ (เดินประมาณ 30 นาที)`,
        )}
      </p>
      <ProvenanceNote kind="access" confidence={access.confidence} reason={access.confidence_reason} timestamp={access.source_timestamp} language={language}>
        {t(
          "Method: walking at about 4 km/h; a road closes at 0.3 m of reconstructed depth and a shelter stops serving once water reaches it; access is evaluated every 0.05 m of the assumed stage.",
          "วิธีการ: เดินประมาณ 4 กม./ชม. ถนนปิดเมื่อน้ำจำลองลึก 0.3 ม. และที่พักพิงหยุดใช้งานเมื่อน้ำถึง ประเมินการเข้าถึงทุก 0.05 ม. ของระดับน้ำสมมุติ",
        )}{" "}{assumedWaterText(language)}
      </ProvenanceNote>
      <fieldset className={styles.segmented}>
        <legend>{t("Shelter set", "ชุดที่พักพิง")}</legend>
        <div>
          <label>
            <input type="radio" name="mae-sai-shelter-set" value="reported" checked={shelterSet === "reported"} onChange={() => onShelterSet("reported")} />
            <span>{t(`Reported used in Sep 2024 (${counted} sites counted)`, `มีรายงานว่าใช้ ก.ย. 2567 (2024) (นับ ${counted} แห่ง)`)}</span>
          </label>
          <label>
            <input type="radio" name="mae-sai-shelter-set" value="plan" checked={shelterSet === "plan"} onChange={() => onShelterSet("plan")} />
            <span>{t("Ranked plan", "แผนจัดอันดับ")}</span>
          </label>
        </div>
      </fieldset>
      {shelterSet === "plan" && shelters.plan.length > 0 && (
        <div className={styles.kField}>
          <label htmlFor={sliderId}>{planSizeLabel(planK, language)}</label>
          <input id={sliderId} type="range" min={1} max={shelters.plan.length} step={1} value={planK}
            aria-valuetext={planCoverageSentence(shelters, planK, language)}
            onChange={(event) => onPlanK(Number(event.target.value))} />
          <PlanSizeSentence shelters={shelters} k={planK} language={language} />
        </div>
      )}
      <fieldset className={styles.segmented} data-testid="access-scope">
        <legend>{t("Residents counted in the equity gap, the subdistrict bars, the chart and the map", "ผู้อยู่อาศัยที่นับในช่องว่างความเท่าเทียม แถบรายตำบล กราฟ และแผนที่")}</legend>
        <div>
          <label>
            <input type="radio" name="mae-sai-access-scope" value="flooded" checked={scope === "flooded"} onChange={() => onScope("flooded")} />
            <span>{t(`Residents whose homes flood at the peak (${formatPeople(floodedResidents)})`, `ผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุด (${formatPeople(floodedResidents)})`)}</span>
          </label>
          <label>
            <input type="radio" name="mae-sai-access-scope" value="all" checked={scope === "all"} onChange={() => onScope("all")} />
            <span>{t(`All residents at road nodes (${formatPeople(allResidents)})`, `ผู้อยู่อาศัยทั้งหมดที่จุดถนน (${formatPeople(allResidents)})`)}</span>
          </label>
        </div>
      </fieldset>
      <p className={styles.note} data-testid="plan-optimises">{t(
        `What the ranked plan optimises: sites that as many as possible of the ${formatPeople(shelters.demand_people)} residents whose homes flood at the modelled peak can walk to before the water rises (roads normal). It does not try to serve every resident at a road node, which is why the two ways of counting below give different pictures of it.`,
        `สิ่งที่แผนจัดอันดับมุ่งให้ดีที่สุด: สถานที่ที่ผู้อยู่อาศัย ${formatPeople(shelters.demand_people)} คนซึ่งบ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลองเดินไปถึงได้มากที่สุดก่อนน้ำขึ้น (ถนนปกติ) แผนไม่ได้มุ่งให้บริการผู้อยู่อาศัยทุกคนที่จุดถนน การนับสองแบบด้านล่างจึงให้ภาพของแผนที่ต่างกัน`,
      )}</p>
      {shelterSet === "reported" && (
        <p className={styles.caveat} data-testid="reported-set-caveat">
          {t(
            `The ${counted} counted sites are assumed open for the whole replay, from before the flood.`,
            `สมมุติว่าสถานที่ที่นับรวม ${counted} แห่งเปิดใช้ตลอดช่วงการย้อนดู ตั้งแต่ก่อนน้ำท่วม`,
          )}
          {" "}{t("Which sites count", "เกณฑ์การนับ")}: <span lang={rule.lang}>{rule.text}</span>
          {exclusions.length > 0 && <>
            {" "}{t("Mapped but not counted", "แสดงบนแผนที่แต่ไม่นับรวม")}:{" "}
            {exclusions.map((shelter) => reportedName(shelter, language)).join("; ")}{language === "en" ? "." : ""}
          </>}
        </p>
      )}
      {status === "error" ? (
        <p className={styles.warningNote} role="alert">{t("The access scenario could not be loaded; the other figures remain available.", "โหลดสถานการณ์การเข้าถึงไม่สำเร็จ ตัวเลขอื่นยังใช้ได้")}</p>
      ) : !snapshot || !totals ? (
        <p className={styles.muted} role="status">{t("Preparing the access scenario…", "กำลังเตรียมสถานการณ์การเข้าถึง…")}</p>
      ) : (
        <>
          {comparison && (comparison.reported || comparison.plan) && (
            <div data-testid="set-comparison">
              <h3>{t("The two shelter sets side by side", "ชุดที่พักพิงสองชุดเทียบกัน")}</h3>
              <p className={styles.muted} data-testid="set-comparison-label">{t(
                "T1 scenario (model). Each set is counted two ways: all residents at road nodes, and residents whose homes flood at the modelled peak. No single figure ranks the sets; read both columns.",
                "สถานการณ์จำลองระดับ T1 (แบบจำลอง) แต่ละชุดนับสองแบบ: ผู้อยู่อาศัยทั้งหมดที่จุดถนน และผู้ที่บ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ไม่มีตัวเลขใดตัวเลขเดียวที่ใช้จัดอันดับชุดที่พักพิง ควรอ่านทั้งสองคอลัมน์",
              )}{" "}{hoursLabel(language)}</p>
              {comparison.reported && (
                <SetComparisonTable kind="reported" title={reportedTitle} comparison={comparison.reported} selected={shelterSet === "reported"} language={language} />
              )}
              {comparison.plan && (
                <SetComparisonTable kind="plan" title={planTitle} comparison={comparison.plan} selected={shelterSet === "plan"} language={language} />
              )}
            </div>
          )}
          <p className={styles.muted} data-testid="access-without">{t(
            `${setLabel}, ${scopeText}: ${formatPeople(without)} / ${total} have no dry shelter of this set within a ${distanceKm} km walk at this replay hour (${formatPeople(snapshot.lost.population)} lost it because of the flood; ${formatPeople(snapshot.never.population)} were already out of reach before it). Modelled residents (WorldPop 2020).`,
            `${setLabel} ${scopeText}: ${formatPeople(without)} / ${total} คนไม่มีที่พักพิงที่แห้งของชุดนี้ในระยะเดิน ${distanceKm} กม. ณ ชั่วโมงนี้ของการย้อนดู (${formatPeople(snapshot.lost.population)} คนสูญเสียเพราะน้ำท่วม ${formatPeople(snapshot.never.population)} คนอยู่นอกระยะตั้งแต่ก่อนน้ำท่วม) ผู้อยู่อาศัยตามแบบจำลอง (WorldPop 2020)`,
          )}</p>
          {gap && wording && (
            <div className={styles.equity} data-testid="equity-gap" data-reason={gap.reason ?? undefined}>
              <p>
                <strong>{t("Evacuation Equity Gap", "ช่องว่างความเท่าเทียมในการอพยพ")}: {wording.value}</strong>
                {wording.sentence && <>{" · "}<span>{wording.sentence}</span></>}
              </p>
              <p data-testid="equity-rule">
                <strong>{t("What is compared.", "สิ่งที่นำมาเปรียบเทียบ:")}</strong>{" "}{equityRuleSentence(language)}
              </p>
              {/* Both counts of each group, one group per line: lost out of those within reach, then everyone counted. */}
              <p className={styles.muted} data-testid="equity-counts">
                {t(
                  `Proxy-vulnerable: ${formatPeople(gap.vulnerableLost)} lost of ${formatPeople(gap.vulnerableWithinReach)} within reach before the flood (${formatPeople(totals.vulnerable)} residents counted).`,
                  `กลุ่มเปราะบางตามตัวแทน: สูญเสีย ${formatPeople(gap.vulnerableLost)} จาก ${formatPeople(gap.vulnerableWithinReach)} คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด ${formatPeople(totals.vulnerable)} คน)`,
                )}{" "}
                <br />
                {t(
                  `Everyone else: ${formatPeople(gap.nonVulnerableLost)} lost of ${formatPeople(gap.nonVulnerableWithinReach)} within reach before the flood (${formatPeople(totals.nonVulnerable)} residents counted).`,
                  `กลุ่มอื่น: สูญเสีย ${formatPeople(gap.nonVulnerableLost)} จาก ${formatPeople(gap.nonVulnerableWithinReach)} คนที่มีที่พักพิงในระยะเดินก่อนน้ำท่วม (ผู้อยู่อาศัยที่นับทั้งหมด ${formatPeople(totals.nonVulnerable)} คน)`,
                )}
              </p>
              {why && <p data-testid="equity-why">{why}</p>}
              <p className={styles.muted} data-testid="equity-label">{t(
                "T1 scenario (model). Vulnerable = terrain/remoteness proxy.",
                "สถานการณ์จำลองระดับ T1 (แบบจำลอง) กลุ่มเปราะบาง = ตัวแทนจากภูมิประเทศและความห่างไกล",
              )}{" "}{hoursLabel(language)}</p>
              <details className={styles.more}>
                <summary>{t("What the ratio and “vulnerable” mean", "อัตราส่วนและ “กลุ่มเปราะบาง” หมายถึงอะไร")}</summary>
                <p className={styles.muted}>{t(
                `Ratio of loss rates (vulnerable ÷ everyone else), two decimals; above 1.20 means vulnerable residents are more likely to lose access, below 0.80 less likely. Each rate divides the residents of a group who lost access by the residents of that group who had a shelter of this set within reach before the flood. Residents with no shelter of this set within reach before the flood are not in the rate; the bars below count them as already out of reach. No ratio is shown when a group has fewer than ${EQUITY_MIN_GROUP} residents within reach before the flood, when no one has lost access, or when only proxy-vulnerable residents have (the ratio would divide by zero). “Vulnerable” is this repository's terrain/remoteness proxy (homes on slopes of 8° or more, or 750 m or more from a drivable road), not demographic vulnerability such as age, disability or income.`,
                `อัตราส่วนของอัตราการสูญเสีย (กลุ่มเปราะบาง ÷ กลุ่มอื่น) ทศนิยมสองตำแหน่ง มากกว่า 1.20 หมายถึงกลุ่มเปราะบางมีโอกาสสูญเสียการเข้าถึงมากกว่า ต่ำกว่า 0.80 หมายถึงน้อยกว่า แต่ละอัตราคือผู้อยู่อาศัยของกลุ่มที่สูญเสียการเข้าถึง หารด้วยผู้อยู่อาศัยของกลุ่มนั้นที่มีที่พักพิงของชุดนี้ในระยะเดินก่อนน้ำท่วม ผู้ที่ไม่มีที่พักพิงของชุดนี้ในระยะเดินตั้งแต่ก่อนน้ำท่วมไม่อยู่ในอัตรานี้ โดยแถบด้านล่างนับเป็นผู้ที่อยู่นอกระยะอยู่แล้ว ไม่แสดงอัตราส่วนเมื่อกลุ่มใดมีผู้อยู่อาศัยที่มีที่พักพิงในระยะเดินก่อนน้ำท่วมน้อยกว่า ${EQUITY_MIN_GROUP} คน เมื่อไม่มีผู้ใดสูญเสียการเข้าถึง หรือเมื่อมีเพียงกลุ่มเปราะบางตามตัวแทนที่สูญเสีย (อัตราส่วนจะหารด้วยศูนย์) “กลุ่มเปราะบาง” ในที่นี้เป็นตัวแทนจากภูมิประเทศและความห่างไกล (บ้านบนความลาดชัน 8° ขึ้นไป หรือห่างถนนที่รถวิ่งได้ 750 ม. ขึ้นไป) ไม่ใช่ความเปราะบางทางประชากร เช่น อายุ ความพิการ หรือรายได้`,
                )}</p>
              </details>
            </div>
          )}
          <h3>{t("Without a dry shelter within reach, by subdistrict", "ไม่มีที่พักพิงที่แห้งในระยะเดิน รายตำบล")}</h3>
          <ul className={styles.stackLegend} aria-hidden="true">
            <li><i className={styles.segLost} />{t("lost because of the flood", "สูญเสียเพราะน้ำท่วม")}</li>
            <li><i className={styles.segNever} />{t("already out of reach before the flood", "อยู่นอกระยะตั้งแต่ก่อนน้ำท่วม")}</li>
          </ul>
          <ul className={styles.bars}>
            {access.tambons.map((id, place) => ({ id, lost: snapshot.lostByTambon[place] ?? 0, never: snapshot.neverByTambon[place] ?? 0, placeTotal: tambonTotals?.[place] ?? 0 }))
              .sort((a, b) => (b.lost + b.never) - (a.lost + a.never) || a.id.localeCompare(b.id))
              .map(({ id, lost, never, placeTotal }) => (
                <li key={id}>
                  <span className={styles.barName}><span>{names[id]?.[language] ?? id}</span></span>
                  <span className={`${styles.barTrack} ${styles.stackTrack}`} aria-hidden="true">
                    <span className={styles.segLost} style={{ width: `${placeTotal > 0 ? Math.min(100, (lost / placeTotal) * 100) : 0}%` }} />
                    <span className={styles.segNever} style={{ width: `${placeTotal > 0 ? Math.min(100, (never / placeTotal) * 100) : 0}%` }} />
                  </span>
                  <span className={styles.barValue} title={t(`lost ${formatPeople(lost)} · already out of reach ${formatPeople(never)} · of ${formatPeople(placeTotal)}`, `สูญเสีย ${formatPeople(lost)} · อยู่นอกระยะอยู่แล้ว ${formatPeople(never)} · จาก ${formatPeople(placeTotal)}`)}>
                    {formatPeople(lost + never)}
                    <span className={styles.srOnly}>{t(` (lost ${formatPeople(lost)}, already out of reach ${formatPeople(never)}, of ${formatPeople(placeTotal)} residents)`, ` (สูญเสีย ${formatPeople(lost)} อยู่นอกระยะอยู่แล้ว ${formatPeople(never)} จากผู้อยู่อาศัย ${formatPeople(placeTotal)})`)}</span>
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

/**
 * Cumulative coverage of the ranked plan against k, pre-emptive and late, with the default plan size (the smallest
 * plan that gets most of the benefit) and the chosen k. The y axis is the share of flooded-home residents covered.
 */
export function CoverageCurve({ shelters, k, language }: { shelters: ShelterInfo; k: number; language: Language }) {
  const t = translator(language);
  const plan = shelters.plan;
  const width = 360;
  const height = 196;
  // Tick labels and the axis title sit 20 units apart so they stay clear at the larger mobile font size.
  const margin = { left: 52, right: 12, top: 16, bottom: 38 };
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
    `Coverage of the ${formatPeople(shelters.demand_people)} residents whose homes flood at the modelled peak, by plan size: ${percent(plan[0]?.cumulative_share ?? 0)} with 1 site, ${percent(plan[knee - 1]?.cumulative_share ?? 0)} with ${knee} (the default: the smallest plan that gets most of the benefit), ${percent(plan.at(-1)?.cumulative_share ?? 0)} with ${n}. Selected k = ${k}: ${percent(chosen?.cumulative_share ?? 0)} pre-emptive, ${percent(chosen?.late_cumulative_share ?? 0)} late.`,
    `ความครอบคลุมผู้อยู่อาศัย ${formatPeople(shelters.demand_people)} คนที่บ้านถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ตามจำนวนที่พักพิง: ${percent(plan[0]?.cumulative_share ?? 0)} เมื่อมี 1 แห่ง ${percent(plan[knee - 1]?.cumulative_share ?? 0)} เมื่อมี ${knee} แห่ง (ค่าเริ่มต้น: แผนที่เล็กที่สุดที่ได้ประโยชน์ส่วนใหญ่แล้ว) ${percent(plan.at(-1)?.cumulative_share ?? 0)} เมื่อมี ${n} แห่ง ที่เลือก k = ${k}: อพยพล่วงหน้า ${percent(chosen?.cumulative_share ?? 0)} อพยพล่าช้า ${percent(chosen?.late_cumulative_share ?? 0)}`,
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
        <text x={margin.left + plotW / 2} y={height - 3} textAnchor="middle" className={styles.axisText}>{t("Plan size k (sites in the plan)", "ขนาดแผน k (จำนวนที่พักพิงในแผน)")}</text>
        <text x={11} y={margin.top + plotH / 2} textAnchor="middle" transform={`rotate(-90 11 ${margin.top + plotH / 2})`} className={styles.axisText} data-testid="coverage-y-title">
          {t("Flooded-home residents covered", "ผู้ที่บ้านถูกน้ำท่วมซึ่งครอบคลุมได้")}
        </text>
        {chosen && <rect x={x(k) - 9} y={margin.top - 6} width={18} height={plotH + 6} className={styles.kBand} />}
        <line x1={x(knee)} x2={x(knee)} y1={margin.top - 6} y2={y(0)} className={styles.kneeLine} />
        <text x={x(knee) + 5} y={margin.top + 4} className={styles.kneeText}>{t(`default k = ${knee}`, `ค่าเริ่มต้น k = ${knee}`)}</text>
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

/** "2.5 m and 4.0 m": the what-if levels other than the replay's own peak. */
function otherLevelsText(shelters: Pick<ShelterInfo, "robustness">, language: Language): string {
  const levels = (shelters.robustness?.stages ?? []).filter((stage) => !stage.modelled_peak)
    .map((stage) => `${stage.stage_m.toFixed(1)} ${language === "th" ? "ม." : "m"}`);
  return levels.join(language === "th" ? " และ " : " and ");
}

/** The local check of one candidate, once a returned verification sheet has been imported; null before, or when the site was not checked. */
export function localCheck(shelters: Pick<ShelterInfo, "verification">, candidateId: string): ShelterCheckRow | null {
  const check = shelters.verification;
  if (!check || check.status !== "conducted") return null;
  return check.checked.find((row) => row.candidate_id === candidateId) ?? null;
}

/**
 * What a local checker reported for a site, for the plan lists. The rankings and the capacity figures were computed
 * without the check, so a site reported not usable is still listed: the line says so instead of leaving the two side
 * by side.
 */
export function localCheckText(row: Pick<ShelterCheckRow, "usable_as_shelter" | "verified_capacity">, language: Language): string {
  const t = translator(language);
  if (!row.usable_as_shelter) {
    return t(
      "Local check: reported not usable as a shelter. The ranking and the capacity figures do not use the check, so the site is still listed.",
      "ผลตรวจในพื้นที่: รายงานว่าใช้เป็นที่พักพิงไม่ได้ การจัดอันดับและตัวเลขความจุไม่ได้ใช้ผลตรวจนี้ สถานที่จึงยังอยู่ในรายการ",
    );
  }
  return row.verified_capacity === null
    ? t("Local check: reported usable as a shelter (no capacity given).", "ผลตรวจในพื้นที่: รายงานว่าใช้เป็นที่พักพิงได้ (ไม่ได้ระบุความจุ)")
    : t(
      `Local check: reported usable, capacity ${formatPeople(row.verified_capacity)} people. The figures here still use the footprint estimate.`,
      `ผลตรวจในพื้นที่: รายงานว่าใช้ได้ ความจุ ${formatPeople(row.verified_capacity)} คน ตัวเลขในส่วนนี้ยังใช้ค่าประมาณจากขอบเขตอาคาร`,
    );
}

/** The local-check line of a site in a plan list; nothing when the site was not checked. */
function LocalCheckBadge({ shelters, candidateId, language }: { shelters: ShelterInfo; candidateId: string; language: Language }) {
  const row = localCheck(shelters, candidateId);
  if (!row) return null;
  return (
    <span className={styles.checkBadge} data-usable={row.usable_as_shelter ? "yes" : "no"} data-testid="local-check">
      {localCheckText(row, language)} <span className={styles.muted}>{checkLabel(row, language)}{language === "th" ? "" : "."}</span>
    </span>
  );
}

function PlannedSiteItem({ site, k, shelters, language, onShow, robust }: {
  site: PlannedShelter;
  k: number;
  shelters: ShelterInfo;
  language: Language;
  onShow: (id: string) => void;
  /** Whether the site is also among the first k at every what-if level. */
  robust: boolean;
}) {
  const t = translator(language);
  const title = candidateTitle(site.candidate, language);
  const flag = capacityFlag(site);
  return (
    <li data-capacity-flag={flag ?? undefined} data-over-capacity={site.shortfall ? "" : undefined} data-robust-core={robust ? "" : undefined}>
      <span className={styles.routeHead}>
        <span className={styles.planRank} aria-hidden="true">{site.rank}</span>
        <strong lang={textLang(title, language)}>{title}</strong>
      </span>
      <span className={styles.routeMeta}>{candidateKindLabel(site.candidate.kind, language)} · {freeboardText(site.candidate, language)}</span>
      <span className={styles.routeMeta}>{capacityText(site.candidate, shelters, language)}</span>
      <span className={styles.routeFigures}>
        <span>{t(`Assigned ≈ ${formatPeople(site.load)} residents in ${indefiniteArticle(k)} ${k}-site plan`, `รับผู้อพยพ ≈ ${formatPeople(site.load)} คนในแผน ${k} แห่ง`)}</span>
        {!flag && site.shortfall && site.capacity !== null && (
          <span className={styles.shortfall}>{t(`Over capacity by ≈ ${formatPeople(site.load - site.capacity)}`, `เกินความจุ ≈ ${formatPeople(site.load - site.capacity)} คน`)}</span>
        )}
      </span>
      {flag && <span className={styles.capacityBadge} data-flag={flag} data-testid="capacity-flag"><b aria-hidden="true">!</b> {capacityFlagText(site, language)}</span>}
      {robust && (
        <span className={styles.robustBadge} data-testid="robust-core">{t(
          `Robust core: also among the first ${k} sites at ${otherLevelsText(shelters, language)}`,
          `แกนที่คงทน: อยู่ใน ${k} แห่งแรกที่ระดับ ${otherLevelsText(shelters, language)} ด้วย`,
        )}</span>
      )}
      <LocalCheckBadge shelters={shelters} candidateId={site.candidate.id} language={language} />
      <button type="button" className={styles.linkButton} onClick={() => onShow(site.candidate.id)} aria-label={t(`Show plan site ${site.rank}, ${title}, on the map`, `แสดงสถานที่ในแผนลำดับ ${site.rank} ${title} บนแผนที่`)}>
        {t("Show on map", "แสดงบนแผนที่")}
      </button>
    </li>
  );
}

/** "31" for a load 30.8 times a capacity estimate, "2.4" below ten. */
export function timesOver(load: number, capacity: number): string {
  const factor = load / capacity;
  return factor >= 10 ? String(Math.round(factor)) : factor.toFixed(1);
}

/**
 * A capacity-aware row's capacity under both bounds, with its basis: the unverified footprint estimate, or the median
 * that stands in for an unknown capacity in the upper bound (the lower bound counts it as 0).
 */
export function capacityBoundsText(row: Pick<CapacityPlanRow, "capacity_est" | "upper_capacity_basis" | "upper">, kind: string, language: Language): string {
  const t = translator(language);
  if (row.capacity_est !== null) {
    return t(
      `Capacity ≈ ${formatPeople(row.capacity_est)} places in both bounds: OpenStreetMap footprint × 0.5 ÷ 3.5 m² per person (Sphere), unverified`,
      `ความจุ ≈ ${formatPeople(row.capacity_est)} คนทั้งสองขอบเขต: พื้นที่อาคารใน OpenStreetMap × 0.5 ÷ 3.5 ตร.ม. ต่อคน (Sphere) ยังไม่ได้ตรวจสอบ`,
    );
  }
  const median = row.upper_capacity_basis === "kind_median"
    ? t(
      `the median estimate of its site kind (${candidateKindLabel(kind, "en").toLowerCase()})`,
      `ค่ามัธยฐานของค่าประมาณของสถานที่ประเภทเดียวกัน (${candidateKindLabel(kind, "th")})`,
    )
    : t(
      "the median of every estimate, because no site of its kind has one",
      "ค่ามัธยฐานของค่าประมาณทั้งหมด เพราะไม่มีสถานที่ประเภทเดียวกันที่มีค่าประมาณ",
    );
  return t(
    `Capacity unknown (no mapped building footprint): 0 in the lower bound, ${formatPeople(row.upper.capacity)} in the upper bound, ${median}`,
    `ไม่ทราบความจุ (ไม่มีขอบเขตอาคารในแผนที่): ขอบเขตล่างนับเป็น 0 ขอบเขตบนใช้ ${formatPeople(row.upper.capacity)} คน ตาม${median}`,
  );
}

/** The six standing caveats of the capacity-aware figures, in the order the card lists them. */
export function capacityCaveats(shelters: Pick<ShelterInfo, "capacitated">, language: Language): string[] {
  const t = translator(language);
  const all = shelters.capacitated?.all_eligible;
  const unknown = all ? all.sites - all.sites_with_estimate : 0;
  return [
    t(
      "T1 scenario (model): computed on the reconstructed peak, not a record of who sheltered where.",
      "สถานการณ์จำลองระดับ T1 (แบบจำลอง): คำนวณบนระดับน้ำสูงสุดที่จำลองขึ้น ไม่ใช่บันทึกว่าใครไปพักที่ใด",
    ),
    t(
      "Demand is every resident of a home that floods at the modelled peak. That is an upper bound: many people stay with relatives or on an upper floor.",
      "ความต้องการคือผู้อยู่อาศัยทุกคนในบ้านที่ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ซึ่งเป็นค่าขอบเขตบน เพราะหลายคนไปพักกับญาติหรืออยู่ชั้นบนของบ้าน",
    ),
    t(
      `Capacity is an unverified estimate from mapped building footprints (footprint × 0.5 usable ÷ 3.5 m² per person, Sphere)${all ? `; ${unknown} of the ${all.sites} eligible candidates have no footprint to estimate from` : ""}.`,
      `ความจุเป็นค่าประมาณจากขอบเขตอาคารในแผนที่ที่ยังไม่ได้ตรวจสอบ (พื้นที่อาคาร × ใช้ได้ 0.5 ÷ 3.5 ตร.ม. ต่อคน ตามเกณฑ์ Sphere)${all ? ` สถานที่ที่เข้าเกณฑ์ ${unknown} จาก ${all.sites} แห่งไม่มีขอบเขตอาคารให้ประมาณ` : ""}`,
    ),
    t(
      "Neither bound is a limit on who fits. The two differ only in what a site with no mapped footprint is assumed to hold; a site with a footprint counts at its estimate in both, and that estimate is too low where buildings are unmapped. More residents may fit than the upper bound gives, and fewer than the lower bound if a site turns out unusable.",
      "ทั้งสองขอบเขตไม่ใช่ค่าจำกัดของจำนวนคนที่รองรับได้ ทั้งสองต่างกันเพียงว่าสมมุติให้สถานที่ที่ไม่มีขอบเขตอาคารในแผนที่รับได้เท่าใด ส่วนสถานที่ที่มีขอบเขตอาคารนับตามค่าประมาณทั้งสองขอบเขต ซึ่งต่ำกว่าจริงในบริเวณที่อาคารยังไม่ถูกทำแผนที่ จึงอาจรองรับได้มากกว่าขอบเขตบน และอาจน้อยกว่าขอบเขตล่างหากสถานที่ใช้ไม่ได้จริง",
    ),
    t(
      "The sites are candidates to verify on the ground, not a list of sites to open.",
      "สถานที่เหล่านี้เป็นสถานที่ที่ควรตรวจสอบในพื้นที่ ไม่ใช่รายชื่อสถานที่ที่ต้องเปิด",
    ),
    t(
      "The planning overlay's listed-capacity figures come from a different source (the DDPM shelter list, not building footprints), so its numbers differ from these.",
      "ตัวเลขความจุตามบัญชีรายชื่อในชั้นข้อมูลการวางแผน (planning overlay) มาจากแหล่งข้อมูลอื่น (รายชื่อที่พักพิงของ ปภ. ไม่ใช่ขอบเขตอาคาร) ตัวเลขจึงต่างจากส่วนนี้",
    ),
  ];
}

/**
 * Capacity-aware view of the plan (T1 scenario, model), beside the coverage ranking: how many of the residents whose
 * homes flood at the peak fit under two capacity bounds, for the first k sites of the plan above, for the first k sites
 * of the capacity-aware ranking, for that whole ranking and for every eligible candidate. Figures are read from the
 * manifest; overflow = demand − fit. Renders nothing for a manifest without the capacity-aware plan.
 */
export function CapacityAwareBlock({ shelters, k, language, onShowCandidate }: {
  shelters: ShelterInfo;
  k: number;
  language: Language;
  onShowCandidate: (id: string) => void;
}) {
  const t = translator(language);
  const view = capacityAwareView(shelters, k);
  const plan = shelters.capacitated;
  if (!view || !plan) return null;
  const byId = new Map(shelters.candidates.map((candidate) => [candidate.id, candidate]));
  const size = view.coverage.size;
  const over = overCapacitySites(planSites(shelters, size));
  const worst = over[0];
  const km = shelters.method.threshold_m / 1000;
  const sitesWord = (count: number) => `${count} site${count === 1 ? "" : "s"}`;
  /** "first site" / "first 8 sites". */
  const firstSites = (count: number) => (count === 1 ? "first site" : `first ${count} sites`);
  const floor = `${Number((view.full.gainFloorShare * 100).toFixed(2))}%`;
  const row = (name: string, label: string, note: string, value: CapacityCounts) => (
    <tr key={name}>
      <th scope="row">{label}<small>{note}</small></th>
      {(["lower", "upper"] as const).map((bound) => (
        <td key={bound} data-testid={`capacity-${name}-${bound}`}>
          {formatPeople(value[bound].served)}
          <small> {t(`overflow ${formatPeople(value[bound].overflow)}`, `ไม่มีที่รองรับ ${formatPeople(value[bound].overflow)}`)}</small>
        </td>
      ))}
    </tr>
  );
  return (
    <div className={styles.capacityAware} data-testid="capacity-aware">
      <h3>{t("If capacity counts: who fits (two bounds)", "เมื่อคิดความจุด้วย: รองรับได้กี่คน (สองขอบเขต)")}</h3>
      <p className={styles.muted}>
        <span className={styles.tagModel}>{t("T1 scenario (model)", "สถานการณ์จำลองระดับ T1 (แบบจำลอง)")}</span>{" "}
        {t(
          `The plan above counts who can walk to a site, not who fits inside. Here every resident of a home that floods at the modelled peak (${formatPeople(view.demand)}) is assigned to a site within the ${km} km walk without going over that site's capacity estimate. Lower bound: a site with no capacity estimate holds nobody. Upper bound: it holds the median estimate of its site kind.`,
          `แผนด้านบนนับผู้ที่เดินไปถึงสถานที่ได้ ไม่ได้นับผู้ที่พักได้จริง ส่วนนี้จัดให้ผู้อยู่อาศัยทุกคนในบ้านที่ถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง (${formatPeople(view.demand)} คน) ไปยังสถานที่ภายในระยะเดิน ${km} กม. โดยไม่เกินค่าประมาณความจุของสถานที่นั้น ขอบเขตล่าง: สถานที่ที่ไม่มีค่าประมาณความจุถือว่ารับไม่ได้เลย ขอบเขตบน: ใช้ค่ามัธยฐานของค่าประมาณของสถานที่ประเภทเดียวกัน`,
        )}
      </p>
      <ProvenanceNote kind="capacity" confidence={plan.confidence} reason={plan.confidence_reason} timestamp={plan.source_timestamp} language={language} />
      <div className={styles.setCompare} data-testid="capacity-aware-table">
        <table>
          <caption>{t(
            `Residents who fit, of the ${formatPeople(view.demand)} whose homes flood at the peak (overflow = demand − fit)`,
            `ผู้ที่พักได้ จาก ${formatPeople(view.demand)} คนที่บ้านถูกน้ำท่วมที่ระดับสูงสุด (ผู้ที่ไม่มีที่รองรับ = ความต้องการ − ผู้ที่พักได้)`,
          )}</caption>
          <thead>
            <tr>
              <td />
              <th scope="col" data-testid="capacity-bound-lower">{t("Lower bound", "ขอบเขตล่าง")}<small>{t("a site with no footprint holds nobody", "สถานที่ที่ไม่มีขอบเขตอาคารรับไม่ได้เลย")}</small></th>
              <th scope="col" data-testid="capacity-bound-upper">{t("Upper bound", "ขอบเขตบน")}<small>{t("a site with no footprint holds a typical size; not a maximum", "สถานที่ที่ไม่มีขอบเขตอาคารรับได้ตามขนาดทั่วไป ไม่ใช่ค่าสูงสุด")}</small></th>
            </tr>
          </thead>
          <tbody>
            {row("coverage",
              t(`The ${firstSites(size)} of the plan above`, `${size} แห่งแรกของแผนด้านบน`),
              t(`Ranked by who can walk there · ${formatPeople(view.coverage.withinReach)} within the walk`, `จัดอันดับตามผู้ที่เดินไปถึงได้ · อยู่ในระยะเดิน ${formatPeople(view.coverage.withinReach)} คน`),
              view.coverage)}
            {row("ranked",
              t(`The ${firstSites(view.ranked.size)} of the capacity-aware ranking`, `${view.ranked.size} แห่งแรกของการจัดอันดับแบบคิดความจุ`),
              t(`Each step adds the site where the most additional residents fit · ${formatPeople(view.ranked.withinReach)} within the walk`, `แต่ละขั้นเพิ่มสถานที่ที่ทำให้พักได้เพิ่มมากที่สุด · อยู่ในระยะเดิน ${formatPeople(view.ranked.withinReach)} คน`),
              view.ranked)}
            {row("full",
              t(`All ${sitesWord(view.full.size)} of the capacity-aware ranking`, `ทั้ง ${view.full.size} แห่งของการจัดอันดับแบบคิดความจุ`),
              view.full.endedBy === "gain_floor"
                ? t(`The ranking ends when the next site adds less than ${floor} of demand`, `การจัดอันดับสิ้นสุดเมื่อสถานที่ถัดไปเพิ่มได้น้อยกว่า ${floor} ของความต้องการ`)
                : t(`The ranking is limited to ${view.full.size} sites`, `การจัดอันดับจำกัดไว้ที่ ${view.full.size} แห่ง`),
              view.full)}
            {row("all",
              t(`Every eligible candidate (${view.allEligible.size})`, `สถานที่ที่เข้าเกณฑ์ทั้งหมด (${view.allEligible.size} แห่ง)`),
              t(`${view.allEligible.withEstimate} with a capacity estimate · ${formatPeople(view.allEligible.withinReach)} within the walk`, `มีค่าประมาณความจุ ${view.allEligible.withEstimate} แห่ง · อยู่ในระยะเดิน ${formatPeople(view.allEligible.withinReach)} คน`),
              view.allEligible)}
          </tbody>
        </table>
        <p data-testid="capacity-aware-sentence">{t(
          `Reading for k = ${size}: ${formatPeople(view.coverage.withinReach)} residents can walk to the ${firstSites(size)} of the plan above, and the capacity estimates hold ${formatPeople(view.coverage.lower.served)} to ${formatPeople(view.coverage.upper.served)} of them. That leaves ${formatPeople(view.coverage.upper.overflow)} to ${formatPeople(view.coverage.lower.overflow)} of the ${formatPeople(view.demand)} without a place.`,
          `อ่านที่ k = ${size}: ผู้อยู่อาศัย ${formatPeople(view.coverage.withinReach)} คนเดินไปถึง ${size} แห่งของแผนด้านบนได้ และค่าประมาณความจุรองรับได้ ${formatPeople(view.coverage.lower.served)} ถึง ${formatPeople(view.coverage.upper.served)} คน จึงเหลือ ${formatPeople(view.coverage.upper.overflow)} ถึง ${formatPeople(view.coverage.lower.overflow)} คนจาก ${formatPeople(view.demand)} คนที่ไม่มีที่รองรับ`,
        )}</p>
      </div>
      {worst && worst.capacity !== null && (
        <p className={styles.caveat} data-testid="over-capacity-note">{t(
          `${size === 1 ? "The first site of the plan above is" : `${over.length} of the first ${size} sites of the plan above ${over.length === 1 ? "is" : "are"}`} assigned more residents than ${over.length === 1 ? "its" : "their"} capacity estimate holds. Largest gap: ${candidateTitle(worst.candidate, "en")}, ≈ ${formatPeople(worst.capacity)} places for ≈ ${formatPeople(worst.load)} residents assigned (about ${timesOver(worst.load, worst.capacity)} times the estimate).`,
          `${over.length} จาก ${size} แห่งของแผนด้านบนได้รับผู้อพยพมากกว่าค่าประมาณความจุ ช่องว่างมากที่สุด: ${candidateTitle(worst.candidate, "th")} รองรับได้ ≈ ${formatPeople(worst.capacity)} คน แต่ได้รับผู้อพยพ ≈ ${formatPeople(worst.load)} คน (ประมาณ ${timesOver(worst.load, worst.capacity)} เท่าของค่าประมาณ)`,
        )}</p>
      )}
      <details className={styles.capacitySites} data-testid="capacity-ranking-sites">
        <summary>{t(
          `The ${firstSites(view.ranked.size)} of the capacity-aware ranking (candidates to verify)`,
          `${view.ranked.size} แห่งแรกของการจัดอันดับแบบคิดความจุ (สถานที่ที่ควรตรวจสอบ)`,
        )}</summary>
        <ol className={styles.planList}>
          {view.ranked.rows.map((entry, index) => {
            const candidate = byId.get(entry.candidate_id);
            if (!candidate) return null;
            const title = candidateTitle(candidate, language);
            return (
              <li key={entry.candidate_id} data-capacity-basis={entry.capacity_est === null ? "unknown" : "estimate"}>
                <span className={styles.routeHead}>
                  <span className={styles.planRank} aria-hidden="true">{index + 1}</span>
                  <strong lang={textLang(title, language)}>{title}</strong>
                </span>
                <span className={styles.routeMeta}>{candidateKindLabel(candidate.kind, language)} · {capacityBoundsText(entry, candidate.kind, language)}</span>
                <span className={styles.routeFigures}>{t(
                  `Assigned ${formatPeople(entry.lower.load)} of ${formatPeople(entry.lower.capacity)} places (lower bound) · ${formatPeople(entry.upper.load)} of ${formatPeople(entry.upper.capacity)} (upper bound)`,
                  `จัดให้ ${formatPeople(entry.lower.load)} จาก ${formatPeople(entry.lower.capacity)} ที่ (ขอบเขตล่าง) · ${formatPeople(entry.upper.load)} จาก ${formatPeople(entry.upper.capacity)} ที่ (ขอบเขตบน)`,
                )}</span>
                <LocalCheckBadge shelters={shelters} candidateId={candidate.id} language={language} />
                <button type="button" className={styles.linkButton} onClick={() => onShowCandidate(candidate.id)} aria-label={t(`Show capacity-aware site ${index + 1}, ${title}, on the map`, `แสดงสถานที่แบบคิดความจุลำดับ ${index + 1} ${title} บนแผนที่`)}>
                  {t("Show on map", "แสดงบนแผนที่")}
                </button>
              </li>
            );
          })}
        </ol>
        <p className={styles.muted}>{t(
          "A site's figure is the number of residents it adds when it joins the ranking; other assignments with the same totals exist.",
          "ตัวเลขของแต่ละแห่งคือจำนวนผู้อยู่อาศัยที่เพิ่มขึ้นเมื่อสถานที่นั้นเข้าสู่การจัดอันดับ การจัดแบบอื่นที่ได้ผลรวมเท่ากันก็มีได้",
        )}</p>
      </details>
      <ul className={styles.capacityCaveats} data-testid="capacity-caveats">
        {capacityCaveats(shelters, language).map((caveat) => <li key={caveat}>{caveat}</li>)}
      </ul>
    </div>
  );
}

/**
 * Plan robustness (T1 scenario, model): the coverage ranking repeated at what-if levels around the illustrative peak,
 * which are not return periods, with the count of sites chosen at every level (the robust core). Renders nothing for a
 * manifest without the robustness block.
 */
export function WhatIfBlock({ shelters, k, language }: { shelters: ShelterInfo; k: number; language: Language }) {
  const t = translator(language);
  const robustness = shelters.robustness;
  const levels = whatIfLevels(shelters, k);
  if (!robustness || levels.length === 0) return null;
  const size = Math.min(Math.max(1, Math.round(k)), shelters.plan.length);
  const core = robustCore(shelters, size);
  const label = localizedText(robustness.label, language);
  const unit = language === "th" ? "ม." : "m";
  const peak = levels.find((level) => level.modelledPeak);
  return (
    <div className={styles.whatIf} data-testid="what-if-levels">
      <h3>{t("Other peak levels: which sites stay in the plan", "ระดับน้ำสูงสุดอื่น: สถานที่ใดยังอยู่ในแผน")}</h3>
      <p className={styles.caveat} data-testid="what-if-label">
        <span className={styles.tagModel}>{t("T1 scenario (model)", "สถานการณ์จำลองระดับ T1 (แบบจำลอง)")}</span>{" "}
        <span lang={label.lang}>{label.text}</span>
      </p>
      <p className={styles.muted}>{t(
        `The ${peak ? peak.stage.toFixed(1) : shelters.method.peak_stage_m} m peak of this replay is illustrative (no gauge record), so the ranking is repeated with the peak at ${otherLevelsText(shelters, "en")}: other homes flood and other candidates keep their freeboard.`,
        `ระดับน้ำสูงสุด ${peak ? peak.stage.toFixed(1) : shelters.method.peak_stage_m} ม. ของการย้อนดูนี้เป็นค่าเพื่อการอธิบาย (ไม่มีข้อมูลสถานีวัดน้ำ) จึงจัดอันดับซ้ำโดยให้ระดับสูงสุดเป็น ${otherLevelsText(shelters, "th")} ซึ่งทำให้บ้านที่ถูกน้ำท่วมและสถานที่ที่ยังมีระยะพ้นน้ำเปลี่ยนไป`,
      )}</p>
      <ProvenanceNote kind="robustness" confidence={robustness.confidence} reason={robustness.confidence_reason} timestamp={robustness.source_timestamp} language={language} />
      <div className={styles.setCompare} data-testid="what-if-table">
        <table>
          <caption>{t(`The ranking at each level, for a plan of ${size} site${size === 1 ? "" : "s"}`, `การจัดอันดับที่แต่ละระดับ สำหรับแผน ${size} แห่ง`)}</caption>
          <thead>
            <tr>
              <td />
              {levels.map((level) => (
                <th key={level.stage} scope="col" data-peak={level.modelledPeak ? "" : undefined}>
                  {level.stage.toFixed(1)} {unit}{level.modelledPeak && <small>{t(" (this replay)", " (การย้อนดูนี้)")}</small>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">{t("Residents whose homes flood", "ผู้ที่บ้านถูกน้ำท่วม")}</th>
              {levels.map((level) => <td key={level.stage} data-testid={`what-if-demand-${level.stage.toFixed(1)}`}>{formatPeople(level.demand)}</td>)}
            </tr>
            <tr>
              <th scope="row">{t("Eligible candidates", "สถานที่ที่เข้าเกณฑ์")}</th>
              {levels.map((level) => <td key={level.stage}>{level.eligible}</td>)}
            </tr>
            <tr>
              <th scope="row">
                {t("Within the walk of that level's own plan", "อยู่ในระยะเดินของแผนของระดับนั้นเอง")}
                <small>{t("Capacity not counted", "ยังไม่คิดความจุ")}</small>
              </th>
              {levels.map((level) => (
                <td key={level.stage} data-testid={`what-if-covered-${level.stage.toFixed(1)}`}>
                  {formatPeople(level.covered)}<small> {percent(level.share)}{level.size < size ? t(` · ${level.size} sites ranked`, ` · จัดอันดับได้ ${level.size} แห่ง`) : ""}</small>
                </td>
              ))}
            </tr>
          </tbody>
        </table>
        <p data-testid="robust-core-sentence">{core.length > 0
          ? t(
            `${core.length} of the first ${size} site${size === 1 ? "" : "s"} of the plan above ${core.length === 1 ? "is" : "are"} among the first ${size} at every level: the robust core, marked in the list above. A site in the robust core is still a candidate to verify.`,
            `${core.length} จาก ${size} แห่งแรกของแผนด้านบนอยู่ใน ${size} แห่งแรกที่ทุกระดับ เรียกว่าแกนที่คงทน และมีเครื่องหมายในรายการด้านบน สถานที่ในแกนที่คงทนยังคงเป็นสถานที่ที่ควรตรวจสอบ`,
          )
          : t(
            size === 1
              ? "The first site of the plan above is not the first site at every level, so a plan this small has no robust core."
              : `None of the first ${size} sites of the plan above is among the first ${size} at every level, so a plan this small has no robust core.`,
            `ไม่มีสถานที่ใดใน ${size} แห่งแรกของแผนด้านบนที่อยู่ใน ${size} แห่งแรกที่ทุกระดับ แผนขนาดนี้จึงไม่มีแกนที่คงทน`,
          )}</p>
      </div>
    </div>
  );
}

/** "Checked by <role> on <date>; not an official shelter register", in the page's language. */
export function checkLabel(row: Pick<ShelterCheckRow, "checked_by_role" | "checked_on">, language: Language): string {
  const role = pick(CHECKER_ROLES, row.checked_by_role, language);
  const date = formatDateWithYear(row.checked_on, language);
  return language === "th"
    ? `ตรวจสอบโดย${role} เมื่อ ${date} ไม่ใช่ทะเบียนที่พักพิงทางการ`
    : `Checked by ${role} on ${date}; not an official shelter register`;
}

/**
 * Local check of the shelter candidates through the verification sheet of the export pack. Until a sheet is returned
 * and imported the block says the check was not conducted and states no result. A returned check lists each checked
 * candidate with the label "Checked by <role> on <date>; not an official shelter register", under its confidence, the
 * reason for it and the dates of the checks, and says that the rankings and the capacity figures above do not use it.
 * The checker's access notes are never shown: only that one was given. `sheet` is the blank sheet's download file.
 * Renders nothing for a manifest without the block.
 */
export function ShelterVerificationBlock({ shelters, sheet, language }: { shelters: ShelterInfo; sheet?: ExportFile | null; language: Language }) {
  const t = translator(language);
  const check = shelters.verification;
  if (!check) return null;
  const conducted = check.status === "conducted" && check.checked.length > 0;
  const byId = new Map(shelters.candidates.map((candidate) => [candidate.id, candidate]));
  return (
    <div className={styles.whatIf} data-testid="shelter-verification" data-status={conducted ? "conducted" : "not_conducted"}>
      <h3>{t("Local check of the candidates", "การตรวจสอบสถานที่ในพื้นที่")}</h3>
      {conducted ? (
        <>
          <p data-testid="verification-status">{t(
            `A local check of ${check.checked.length} of the ${check.candidates_listed} eligible candidates was returned${check.imported_on ? ` (imported ${formatDateWithYear(check.imported_on, "en")})` : ""}. It is reported by role and is not an official shelter register; a candidate that is not listed below was not checked.`,
            `มีผลการตรวจสอบในพื้นที่ส่งกลับมา ${check.checked.length} จาก ${check.candidates_listed} แห่งที่เข้าเกณฑ์${check.imported_on ? ` (นำเข้าเมื่อ ${formatDateWithYear(check.imported_on, "th")})` : ""} เป็นข้อมูลที่รายงานตามบทบาท ไม่ใช่ทะเบียนที่พักพิงทางการ สถานที่ที่ไม่อยู่ในรายการด้านล่างยังไม่ได้ตรวจสอบ`,
          )}</p>
          {check.confidence && check.source_timestamp && (
            <ProvenanceNote kind="verification" confidence={check.confidence} reason={check.confidence_reason} timestamp={check.source_timestamp} language={language}>
              {t(
                "One checker reported each site once; the project team did not audit the answers.",
                "ผู้ตรวจสอบหนึ่งรายรายงานแต่ละสถานที่หนึ่งครั้ง ทีมโครงการไม่ได้ตรวจทานคำตอบ",
              )}
            </ProvenanceNote>
          )}
          <p className={styles.caveat} data-testid="verification-not-used">{t(
            "The ranking, the capacity figures and the download tables above were computed without this check: a site reported not usable is still ranked, and a reported capacity does not replace the footprint estimate. Checked sites carry a “Local check” line in the lists above.",
            "การจัดอันดับ ตัวเลขความจุ และตารางดาวน์โหลดด้านบนคำนวณโดยไม่ได้ใช้ผลตรวจนี้ สถานที่ที่รายงานว่าใช้ไม่ได้ยังคงอยู่ในการจัดอันดับ และความจุที่รายงานไม่ได้แทนค่าประมาณจากขอบเขตอาคาร สถานที่ที่ตรวจสอบแล้วมีบรรทัด “ผลตรวจในพื้นที่” ในรายการด้านบน",
          )}</p>
          <ul className={styles.list} data-testid="verification-rows">
            {check.checked.map((row) => {
              const candidate = byId.get(row.candidate_id);
              return (
                <li key={row.candidate_id}>
                  <strong>{candidate ? candidateTitle(candidate, language) : row.candidate_id}</strong>{" — "}
                  {row.usable_as_shelter ? t("usable as a shelter", "ใช้เป็นที่พักพิงได้") : t("not usable as a shelter", "ใช้เป็นที่พักพิงไม่ได้")}
                  {row.verified_capacity !== null && t(`; capacity ${formatPeople(row.verified_capacity)} people`, ` ความจุ ${formatPeople(row.verified_capacity)} คน`)}
                  {row.access_notes_given && t("; access notes were given (not published)", " มีหมายเหตุการเข้าถึง (ไม่เผยแพร่)")}
                  {language === "th" ? " " : ". "}
                  <span className={styles.muted} data-testid="verification-label">{checkLabel(row, language)}{language === "th" ? "" : "."}</span>
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p className={styles.caveat} data-testid="verification-status">{t(
          "Not conducted. No verification sheet has been returned, so no site on this page has been checked on the ground: every capacity is an unverified estimate and every site is a candidate to verify.",
          "ยังไม่ได้ดำเนินการ ยังไม่มีแบบตรวจสอบส่งกลับมา จึงยังไม่มีสถานที่ใดในหน้านี้ที่ได้รับการตรวจสอบในพื้นที่ ความจุทุกค่าเป็นค่าประมาณที่ยังไม่ได้ตรวจสอบ และทุกแห่งเป็นสถานที่ที่ควรตรวจสอบ",
        )}</p>
      )}
      <p className={styles.muted} data-testid="verification-sheet">
        {t(
          `The verification sheet lists the ${check.candidates_listed} eligible candidates with empty columns for a local checker: usable as a shelter, capacity, access notes, role and date. A returned check is labelled “Checked by <role> on <date>; not an official shelter register”. The sheet takes a role, never a name: no names of people, phone numbers or ID numbers. Access notes are for the project team only and are never published.`,
          `แบบตรวจสอบมีรายการสถานที่ที่เข้าเกณฑ์ ${check.candidates_listed} แห่ง พร้อมคอลัมน์ว่างสำหรับผู้ตรวจสอบในพื้นที่ ได้แก่ ใช้เป็นที่พักพิงได้หรือไม่ ความจุ หมายเหตุการเข้าถึง บทบาท และวันที่ ผลที่ส่งกลับมาจะระบุว่า “ตรวจสอบโดย <บทบาท> เมื่อ <วันที่> ไม่ใช่ทะเบียนที่พักพิงทางการ” แบบตรวจสอบรับเฉพาะบทบาท ไม่รับชื่อบุคคล หมายเลขโทรศัพท์ หรือเลขประจำตัว หมายเหตุการเข้าถึงใช้ภายในทีมโครงการเท่านั้นและจะไม่ถูกเผยแพร่`,
        )}
        {sheet && (
          <>
            {" "}
            <a href={sheet.href} download={sheet.name} className={styles.inlineLink} data-testid="verification-sheet-link">
              {t(`Download the blank sheet (CSV, ${formatFileSize(sheet.bytes)})`, `ดาวน์โหลดแบบตรวจสอบเปล่า (CSV, ${formatFileSize(sheet.bytes)})`)}
            </a>
          </>
        )}
      </p>
    </div>
  );
}

/**
 * Ranked shelter plan (planning scenario): coverage curve, the first k sites with loads and capacity, and the gap,
 * then the capacity-aware view (both bounds), the what-if levels with the robust core and the local check of the
 * candidates (not conducted until a verification sheet is returned).
 * Memoised: it does not depend on the replay clock, so playback does not re-render it.
 */
export const ShelterPlanCard = memo(function ShelterPlanCard({ shelters, k, onPlanK, language, onShowCandidate, verificationSheet }: {
  shelters: ShelterInfo;
  k: number;
  onPlanK: (value: number) => void;
  language: Language;
  onShowCandidate: (id: string) => void;
  /** The blank verification sheet of the export pack, for its download link. */
  verificationSheet?: ExportFile | null;
}) {
  const t = translator(language);
  const sliderId = useId();
  if (shelters.plan.length === 0) return null;
  const sites = planSites(shelters, k);
  const knee = shelters.knee_k;
  const flagged = sites.filter((site) => capacityFlag(site) !== null).length;
  const shortfalls = sites.filter((site) => site.shortfall).length;
  const unknown = sites.filter((site) => site.capacity === null).length;
  const freeboard = shelters.method.freeboard_m;
  const core = new Set(robustCore(shelters, k));
  return (
    <section className={styles.card} aria-labelledby="mae-sai-plan-title" data-testid="shelter-plan-card">
      <ThemeEyebrow prefix={t("PLANNING SCENARIO", "สถานการณ์เพื่อการวางแผน")} theme="protect_lives" language={language} />
      <h2 id="mae-sai-plan-title">{t("Where dry shelters would help most (ranked plan)", "ที่พักพิงที่แห้งควรอยู่ที่ใด (แผนจัดอันดับ)")}</h2>
      <p className={styles.muted}>
        {t(
          "A planning scenario, not an official shelter list: OpenStreetMap schools, places of worship, government offices and community centres that keep ",
          "สถานการณ์เพื่อการวางแผน ไม่ใช่รายชื่อที่พักพิงทางการ: โรงเรียน ศาสนสถาน หน่วยงานราชการ และศูนย์ชุมชนจาก OpenStreetMap ที่มี",
        )}
        <Term id="freeboard" language={language}>{t(`${freeboard} m freeboard`, `ระยะพ้นน้ำ ${freeboard} ม.`)}</Term>
        {t(
          ` at the modelled peak (${shelters.method.peak_stage_m} m stage) and lie within ${shelters.method.snap_max_m} m of a road (${shelters.eligible_count} of ${shelters.candidates.length} candidates), ranked greedily by how many of the ${formatPeople(shelters.demand_people)} residents whose homes flood at the peak each adds within a ${shelters.method.threshold_m / 1000} km walk.`,
          ` ขึ้นไปที่ระดับสูงสุดของแบบจำลอง (${shelters.method.peak_stage_m} ม.) และอยู่ห่างถนนไม่เกิน ${shelters.method.snap_max_m} ม. (${shelters.eligible_count} จาก ${shelters.candidates.length} แห่ง) จัดอันดับแบบละโมบตามจำนวนผู้อยู่อาศัยที่บ้านถูกน้ำท่วมที่ระดับสูงสุด (${formatPeople(shelters.demand_people)} คน) ซึ่งแต่ละแห่งเพิ่มความครอบคลุมได้ภายในระยะเดิน ${shelters.method.threshold_m / 1000} กม.`,
        )}
      </p>
      <ProvenanceNote kind="plan" confidence={shelters.confidence} reason={shelters.confidence_reason} timestamp={shelters.source_timestamp} language={language} />
      <div className={styles.kField}>
        <label htmlFor={sliderId}>{planSizeLabel(k, language)}</label>
        <input id={sliderId} type="range" min={1} max={shelters.plan.length} step={1} value={k}
          aria-valuetext={planCoverageSentence(shelters, k, language)}
          onChange={(event) => onPlanK(Number(event.target.value))} />
        <PlanSizeSentence shelters={shelters} k={k} language={language} />
      </div>
      <CoverageCurve shelters={shelters} k={k} language={language} />
      <p>{t(
        `Ranked range, not a fixed number: the first k entries are the plan for k shelters. The default, k = ${knee}, is the smallest plan that reaches 90% of what all ${shelters.plan.length} ranked sites reach.`,
        `เป็นช่วงที่จัดอันดับ ไม่ใช่จำนวนตายตัว: k รายการแรกคือแผนสำหรับที่พักพิง k แห่ง ค่าเริ่มต้น k = ${knee} คือแผนที่เล็กที่สุดที่ครอบคลุมได้ถึง 90% ของค่าสูงสุดที่แผนใด ๆ ทำได้`,
      )}</p>
      <div className={styles.gapCallout} role="note">
        <strong>{t("Shelter gap", "ช่องว่างของที่พักพิง")}</strong>
        <p>{t(
          `${formatPeople(shelters.uncoverable_people)} residents in the modelled peak flood zone have no eligible dry site within a ${shelters.method.threshold_m / 1000} km walk even with every candidate — candidates for new or temporary shelters, or vertical evacuation.`,
          `ผู้อยู่อาศัย ${formatPeople(shelters.uncoverable_people)} คนในพื้นที่น้ำท่วมสูงสุดของแบบจำลองไม่มีสถานที่ที่แห้งและเข้าเกณฑ์ภายในระยะเดิน ${shelters.method.threshold_m / 1000} กม. แม้ใช้ทุกแห่งที่เป็นไปได้ — ควรพิจารณาที่พักพิงใหม่หรือชั่วคราว หรือการอพยพขึ้นที่สูงในอาคาร`,
        )}</p>
      </div>
      <h3>{t(`The first ${k} site${k === 1 ? "" : "s"} of the plan`, `${k} แห่งแรกของแผน`)}</h3>
      {flagged > 0 && (
        <p className={styles.caveat} data-testid="capacity-flag-note">{t(
          `${flagged} of these site${flagged === 1 ? " is" : "s are"} marked “!” on the list and the map: no capacity estimate, or an estimate less than half of the residents assigned. Coverage counts who can walk there, not who fits inside.`,
          `${flagged} แห่งในรายการนี้มีเครื่องหมาย “!” ทั้งในรายการและบนแผนที่: ไม่มีค่าประมาณความจุ หรือความจุต่ำกว่าครึ่งหนึ่งของผู้อพยพที่ได้รับ ความครอบคลุมนับผู้ที่เดินไปถึงได้ ไม่ใช่ผู้ที่พักได้จริง`,
        )}</p>
      )}
      <ol className={styles.planList}>
        {sites.map((site) => (
          <PlannedSiteItem key={site.candidate.id} site={site} k={k} shelters={shelters} language={language} onShow={onShowCandidate} robust={core.has(site.candidate.id)} />
        ))}
      </ol>
      <p className={styles.muted}>{t(
        `Loads assign each covered resident to the nearest site of this plan. ${shortfalls > 0 ? `${shortfalls} site${shortfalls === 1 ? " is" : "s are"} over the capacity estimate. ` : ""}${unknown > 0 ? `${unknown} site${unknown === 1 ? " has" : "s have"} no capacity estimate (OpenStreetMap building coverage in Mae Sai is sparse, so capacities are unknown or underestimated). ` : ""}Candidates and loads are model outputs; check any site on the ground before planning with it.`,
        `ภาระคือจำนวนผู้อยู่อาศัยที่ได้รับการครอบคลุมซึ่งจัดให้ไปยังที่พักพิงที่ใกล้ที่สุดของแผนนี้ ${shortfalls > 0 ? `มี ${shortfalls} แห่งที่เกินความจุประมาณการ ` : ""}${unknown > 0 ? `มี ${unknown} แห่งที่ไม่มีค่าประมาณความจุ (ข้อมูลอาคารใน OpenStreetMap ของแม่สายยังมีน้อย ความจุจึงไม่ทราบหรือต่ำกว่าจริง) ` : ""}สถานที่และภาระเป็นผลจากแบบจำลอง ควรตรวจสอบในพื้นที่ก่อนใช้วางแผน`,
      )}</p>
      <CapacityAwareBlock shelters={shelters} k={k} language={language} onShowCandidate={onShowCandidate} />
      <WhatIfBlock shelters={shelters} k={k} language={language} />
      <ShelterVerificationBlock shelters={shelters} sheet={verificationSheet} language={language} />
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
            {" "}<span className={styles.muted} lang={localizedText(shelter.access_set_note, language).lang}>{localizedText(shelter.access_set_note, language).text}</span>
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
      <p className={styles.eyebrow}>{t("PUBLIC REPORTING · SEPTEMBER 2024", `รายงานสาธารณะ · กันยายน ${thaiYear(2024)}`)}</p>
      <h2 id="mae-sai-reported-title">{title}</h2>
      <p className={styles.muted}>{t(
        `Compiled from news and official updates, with sources. ${located.length} are placed on the map (stars${command > 0 ? "; a diamond marks a relief and command site" : ""}) and checked against the reconstruction; ${flooding} of them flood at the modelled peak, a flag to verify rather than a finding. ${unlocated.length} could not be located and are listed without a pin.`,
        `รวบรวมจากข่าวและรายงานทางการ พร้อมแหล่งที่มา ${located.length} แห่งแสดงบนแผนที่ (ดาว${command > 0 ? " ส่วนรูปข้าวหลามตัดคือศูนย์บัญชาการและจุดช่วยเหลือ" : ""}) และตรวจกับการจำลอง ในจำนวนนี้ ${flooding} แห่งถูกน้ำท่วมที่ระดับสูงสุดของแบบจำลอง ซึ่งเป็นข้อสังเกตที่ต้องตรวจสอบ ไม่ใช่ข้อสรุป อีก ${unlocated.length} แห่งระบุตำแหน่งไม่ได้จึงแสดงเฉพาะในรายการ`,
      )}</p>
      <ProvenanceNote kind="reported" confidence={shelters.confidence} reason={shelters.reported_status} timestamp={shelters.source_timestamp} language={language}>
        {t(
          "Whether the access scenario counts a site is on each site’s “Access scenario” line.",
          "สถานที่แต่ละแห่งนับรวมในสถานการณ์การเข้าถึงหรือไม่ ดูได้ที่บรรทัด “สถานการณ์การเข้าถึง” ของแต่ละแห่ง",
        )}
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

/** A calibration anchor counts as matched when the model is within this share of the reported area. */
const ANCHOR_MATCH_SHARE = 0.1;

/**
 * What a calibration anchor tells the reader: matched by construction when the tuned stage reproduces the figure,
 * otherwise how far the closest stage stays from it, and why when the model's smallest non-zero extent is larger.
 */
function calibrationText(check: ExternalCheck, manifest: CheckManifest, language: Language): string {
  const t = translator(language);
  const difference = checkDifference(check);
  if (difference === null || Math.abs(difference) <= ANCHOR_MATCH_SHARE) {
    return t(
      "This figure was used to set the model's stage, so the agreement holds by construction and does not test the model.",
      "ตัวเลขนี้ใช้กำหนดระดับน้ำของแบบจำลอง ค่าที่ตรงกันจึงเกิดจากการปรับแบบจำลอง ไม่ใช่การทดสอบแบบจำลอง",
    );
  }
  const gapKm2 = Math.abs(check.model_km2 - check.reported_km2).toFixed(1);
  const gapPct = Math.round(Math.abs(difference) * 100);
  const smallest = smallestFloodedExtent(manifest);
  const floor = smallest && smallest.km2 > check.reported_km2 ? smallest : null;
  return t(
    `This figure was used to set the model's stage, so it does not test the model, and even the closest stage stays ${gapKm2} km² (${gapPct}%) ${difference > 0 ? "above" : "below"} it.${floor ? ` The model cannot go lower: its smallest non-zero extent, land within ${floor.stage_m.toFixed(2)} m of the channel level, is already ${floor.km2.toFixed(1)} km².` : ""}`,
    `ตัวเลขนี้ใช้กำหนดระดับน้ำของแบบจำลอง จึงไม่ใช่การทดสอบแบบจำลอง และแม้ที่ระดับน้ำที่ใกล้ที่สุด แบบจำลองยัง${difference > 0 ? "สูงกว่า" : "ต่ำกว่า"}ตัวเลขนี้ ${gapKm2} ตร.กม. (${gapPct}%)${floor ? ` แบบจำลองให้ค่าต่ำกว่านี้ไม่ได้ เพราะขอบเขตน้ำท่วมที่เล็กที่สุดที่ไม่เป็นศูนย์ (พื้นที่ที่สูงจากระดับร่องน้ำไม่เกิน ${floor.stage_m.toFixed(2)} ม.) ก็มีขนาด ${floor.km2.toFixed(1)} ตร.กม. แล้ว` : ""}`,
  );
}

function ExternalCheckItem({ check, manifest, language }: { check: ExternalCheck; manifest: CheckManifest; language: Language }) {
  const t = translator(language);
  const modelKm2 = Number(check.model_km2.toFixed(1));
  const modelled = Math.round(manifest.model_coverage.modelled_km2);
  const district = Math.round(manifest.model_coverage.district_km2);
  const matched = Math.abs(checkDifference(check) ?? 0) <= ANCHOR_MATCH_SHARE;
  // Manifest sentences in Thai where the page knows a translation; the source's own wording is quoted, not bracketed,
  // so its parentheses never nest inside the page's.
  const observed = localizedText(check.observed, language);
  const quoted = localizedText(check.reported_text, language);
  const use = check.use ? localizedText(check.use, language) : null;
  const modelWindow = check.model_window ? localizedText(check.model_window, language) : null;
  return (
    <li>
      <span lang={observed.lang}>{observed.text}</span>{": "}
      {t(`reported ${check.reported_km2} km²`, `รายงาน ${check.reported_km2} ตร.กม.`)}
      {check.reported_people !== undefined && t(` and ≈ ${formatPeople(check.reported_people)} people exposed`, ` และประชากรที่อยู่ในพื้นที่น้ำท่วม ≈ ${formatPeople(check.reported_people)} คน`)}
      {" — “"}<span lang={quoted.lang === "en" ? textLang(quoted.text, "en") : "th"}>{quoted.text}</span>{"”"}{language === "en" ? "." : ""}{" "}
      {check.role === "calibration_anchor" ? (
        <>
          {matched
            ? t(
              `The model gives ${modelKm2} km²${check.model_stage_m !== undefined ? ` at the ${check.model_stage_m} m stage tuned to it` : ""}.`,
              `แบบจำลองให้ค่า ${modelKm2} ตร.กม.${check.model_stage_m !== undefined ? ` ที่ระดับน้ำ ${check.model_stage_m} ม. ซึ่งปรับให้ตรงกับตัวเลขนี้` : ""}`,
            )
            : t(
              `The model gives ${modelKm2} km²${check.model_stage_m !== undefined ? ` at the ${check.model_stage_m} m stage set closest to it` : ""}.`,
              `แบบจำลองให้ค่า ${modelKm2} ตร.กม.${check.model_stage_m !== undefined ? ` ที่ระดับน้ำ ${check.model_stage_m} ม. ซึ่งเป็นระดับที่ใกล้ตัวเลขนี้ที่สุด` : ""}`,
            )}{" "}
          <span className={styles.muted} data-testid="calibration-note">{calibrationText(check, manifest, language)}{use && <>{" "}<span lang={use.lang}>{use.text}</span></>}</span>
        </>
      ) : (
        <>
          {t(
            `The model gives ${modelKm2} km²${check.model_people_in_water !== undefined ? ` and ≈ ${formatPeople(check.model_people_in_water)} modelled residents in water` : ""}${check.model_stage_m !== undefined ? ` at a ${check.model_stage_m} m stage` : ""}`,
            `แบบจำลองให้ค่า ${modelKm2} ตร.กม.${check.model_people_in_water !== undefined ? ` และผู้อยู่อาศัยตามแบบจำลองในน้ำ ≈ ${formatPeople(check.model_people_in_water)} คน` : ""}${check.model_stage_m !== undefined ? ` ที่ระดับน้ำ ${check.model_stage_m} ม.` : ""}`,
          )}
          {modelWindow && <>{" — "}<span lang={modelWindow.lang}>{modelWindow.text}</span></>}{language === "en" ? "." : ""}{" "}
          {check.model_peak_km2 !== undefined && t(
            `For reference, the modelled peak gives ${Number(check.model_peak_km2.toFixed(1))} km²${check.model_peak_people_in_water !== undefined ? ` and ≈ ${formatPeople(check.model_peak_people_in_water)} residents in water` : ""}.`,
            `เพื่อเปรียบเทียบ ระดับสูงสุดของแบบจำลองให้ค่า ${Number(check.model_peak_km2.toFixed(1))} ตร.กม.${check.model_peak_people_in_water !== undefined ? ` และผู้อยู่อาศัยในน้ำ ≈ ${formatPeople(check.model_peak_people_in_water)} คน` : ""}`,
          )}{" "}
          <span className={styles.muted}>{coverageComplete(manifest.model_coverage)
            ? t(`Model figures cover the whole of Mae Sai district (${district} km²).`, `ตัวเลขแบบจำลองครอบคลุมทั้งอำเภอแม่สาย (${district} ตร.กม.)`)
            : t(
              `Model figures cover the modelled part of Mae Sai district (${modelled} of ${district} km²).`,
              `ตัวเลขแบบจำลองครอบคลุมเฉพาะส่วนที่จำลองของอำเภอแม่สาย (${modelled} จาก ${district} ตร.กม.)`,
            )}{" "}{use
            ? <span lang={use.lang}>{use.text}</span>
            : t("Magnitude check only, not a spatial validation.", "ใช้ตรวจขนาดเท่านั้น ไม่ใช่การยืนยันตำแหน่ง")}</span>
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
 * construction), calibration-informed size checks (known while tuning, so not independent) and independent checks
 * (compared over the external product's own time window where it is known).
 */
export const ExternalChecks = memo(function ExternalChecks({ manifest, language }: { manifest: CheckManifest; language: Language }) {
  const t = translator(language);
  const checks = manifest.external_checks ?? [];
  if (checks.length === 0) return null;
  const { calibration, informed, independent } = externalChecksByRole(checks);
  // In Thai, say so only when some source wording has no known translation and stays in its original.
  const untranslated = language === "th" && checks.some((check) => [check.observed, check.reported_text, check.use, check.model_window]
    .some((value) => value && localizedText(value, language).lang !== language));
  return (
    <div className={styles.anchor}>
      {untranslated && <p className={styles.muted}>ข้อความจากแหล่งภายนอกที่ยังไม่มีคำแปลคงไว้เป็นภาษาต้นฉบับ</p>}
      {calibration.length > 0 && (
        <>
          <p><strong>{t("Calibration anchor (not an independent check)", "จุดอ้างอิงที่ใช้ปรับแบบจำลอง (ไม่ใช่การตรวจสอบอิสระ)")}</strong></p>
          <ul className={styles.list}>{calibration.map((check) => <ExternalCheckItem key={check.id} check={check} manifest={manifest} language={language} />)}</ul>
        </>
      )}
      {informed.length > 0 && (
        <>
          <p><strong>{t("Size checks (calibration-informed, not independent)", "การตรวจสอบขนาด (มีส่วนในการปรับแบบจำลอง ไม่ใช่การตรวจสอบอิสระ)")}</strong></p>
          <ul className={styles.list}>{informed.map((check) => <ExternalCheckItem key={check.id} check={check} manifest={manifest} language={language} />)}</ul>
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
