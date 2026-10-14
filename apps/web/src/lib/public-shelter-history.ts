/**
 * The places reported in use as shelters in September 2024, for the Public Shelter map: what the page may show of
 * them, and the words it uses.
 *
 * They come from the replay's manifest (`shelters.reported`), which was compiled from public sources: official
 * situation reports and news. It is history. It is not a register of shelters, it says nothing about which place is
 * open today, and a position marked approximate was placed from a description. The page therefore never proposes one
 * of them: a reader may take one as a destination, and must still confirm it with an authority before it is used.
 *
 * No DOM access in this module. The code that reads the replay is loaded with the manifest, so the page carries
 * neither where the replay does not ship (the public build).
 */

import type { ReportedShelter, TimelineManifest } from "./flood-timeline";
import type { Language } from "./types";

type Localized = Record<Language, string>;

/** How a place came to be in the list: an official source, several media reports, or one. */
export type ShelterEvidence = "official" | "several_reports" | "one_report";

export interface ShelterHistorySite {
  id: string;
  name: Localized;
  /** Null where no source gives a position that could be placed on the map. */
  point: { latitude: number; longitude: number } | null;
  evidence: ShelterEvidence;
  /** The position was placed from a description or a listing, not matched to a mapped building. */
  approximate: boolean;
  /**
   * Whether the walk the practice replay measures counts the place: the bake counts located places reported in use
   * as overnight shelters by 12 Sep 2024. A place first used later (Wat Mueang Daeng from 21 Sep) is not counted.
   */
  countedForWalk: boolean;
  /** Why the walk counts the place or not, from the manifest. */
  walkNote: Localized;
}

/** The places of 2024 and the date their list was compiled ("2026-09-27"). */
export interface ShelterHistory {
  sites: ShelterHistorySite[];
  compiled: string;
}

const evidenceOf = (strength: string): ShelterEvidence =>
  strength === "official" ? "official" : strength === "multiple_media" ? "several_reports" : "one_report";

function siteOf(site: ReportedShelter): ShelterHistorySite {
  const located = typeof site.lat === "number" && typeof site.lon === "number" && Number.isFinite(site.lat) && Number.isFinite(site.lon);
  return {
    id: site.id,
    name: { en: site.name_en, th: site.name_th },
    point: located ? { latitude: site.lat as number, longitude: site.lon as number } : null,
    evidence: evidenceOf(site.evidence_strength),
    approximate: located && site.location_confidence !== "high",
    countedForWalk: located && site.in_access_set,
    walkNote: { en: site.access_set_note, th: site.access_set_note_th ?? site.access_set_note },
  };
}

/**
 * The reported shelters of the manifest, in its order. The district's command centre is left out: it was reported
 * as a relief and command centre, not as a place to stay.
 */
export function shelterHistorySites(manifest: Pick<TimelineManifest, "shelters">): ShelterHistorySite[] {
  return (manifest.shelters?.reported ?? []).filter((site) => site.role === "shelter").map(siteOf);
}

/** Reads the manifest of the current replay and returns its reported shelters with the date of their list. */
export async function loadShelterHistory(signal: AbortSignal): Promise<ShelterHistory> {
  const { parseTimelineManifest, TIMELINE_MANIFEST_URL } = await import("./flood-timeline");
  const response = await fetch(TIMELINE_MANIFEST_URL, { signal });
  if (!response.ok) throw new Error(`${TIMELINE_MANIFEST_URL}: HTTP ${response.status}`);
  const manifest = parseTimelineManifest(await response.json());
  return { sites: shelterHistorySites(manifest), compiled: manifest.shelters?.reported_compiled ?? "" };
}

const MONTHS: Readonly<Record<Language, readonly string[]>> = {
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  th: ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."],
};

/**
 * A date of the manifest ("2026-09-27") as the page writes it: "27 Sep 2026", or in Thai the Buddhist year with the
 * Common Era year after it, as the rest of the page does. Anything else is returned as it is.
 */
export function formatListDate(value: string, language: Language): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return value;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const name = MONTHS[language][month - 1];
  if (!name) return value;
  return language === "th" ? `${day} ${name} ${year + 543} (${year})` : `${day} ${name} ${year}`;
}

/**
 * When and from what the list was compiled: the source time the page gives with the list, its markers and the
 * place the reader takes from it. Empty when the manifest has no date.
 */
export function shelterListCompiled(compiled: string, language: Language): string {
  if (!compiled) return "";
  const date = formatListDate(compiled, language);
  return language === "th"
    ? `รวบรวมรายชื่อเมื่อ ${date} จากแหล่งข้อมูลสาธารณะ ไม่ใช่รายชื่อทางการ`
    : `List compiled on ${date} from public sources; not an official list.`;
}

export const SHELTER_HISTORY_COPY = {
  /** A line of the note at the foot of the map, once the markers are there. */
  mapNote: { en: "Markers: reported as shelters in September 2024", th: "หมุด: มีรายงานว่าใช้เป็นที่พักพิงในเดือนกันยายน 2567 (2024)" },
  listHeading: { en: "Reported as shelters in September 2024", th: "มีรายงานว่าใช้เป็นที่พักพิงในเดือนกันยายน 2567 (2024)" },
  listNote: {
    en: "This says nothing about today: confirm with DDPM 1784 that a place is open before you go.",
    th: "รายชื่อนี้ไม่ได้บอกสถานะในวันนี้ โปรดสอบถาม ปภ. 1784 ว่าสถานที่เปิดรับก่อนเดินทาง",
  },
  /** In a practice scenario, a place the walk of the replay does not count; its reason follows. */
  notCounted: { en: "Not counted for the walk in this practice replay.", th: "ไม่นับรวมในการคำนวณทางเดินของภาพจำลองฝึกซ้อมนี้" },
  notCountedShort: { en: "not counted for the walk", th: "ไม่นับรวมในการคำนวณทางเดิน" },
  siteLine: { en: "Reported in use as a shelter in September 2024.", th: "มีรายงานว่าใช้เป็นที่พักพิงในเดือนกันยายน 2567 (2024)" },
  notToday: {
    en: "This says nothing about today. Confirm with DDPM 1784 that it is open before you go.",
    th: "ข้อมูลนี้ไม่ได้บอกสถานะในวันนี้ โปรดสอบถาม ปภ. 1784 ว่าเปิดรับก่อนเดินทาง",
  },
  approximate: { en: "Its position on the map is approximate.", th: "ตำแหน่งบนแผนที่เป็นตำแหน่งโดยประมาณ" },
  approximateShort: { en: "position approximate", th: "ตำแหน่งโดยประมาณ" },
  noPosition: { en: "position not known", th: "ไม่ทราบตำแหน่ง" },
  use: { en: "Use as destination", th: "ใช้เป็นจุดหมาย" },
} as const satisfies Record<string, Localized>;

/** The labels of the evidence, in the words Studio uses for the same list. */
export const SHELTER_EVIDENCE_COPY: Readonly<Record<ShelterEvidence, Localized>> = {
  official: { en: "Official source", th: "แหล่งข้อมูลทางการ" },
  several_reports: { en: "Several media reports", th: "รายงานสื่อหลายแหล่ง" },
  one_report: { en: "One media report", th: "รายงานสื่อแหล่งเดียว" },
};

/** How a place is shown: with the date of its list, and, in a practice scenario, whether the walk counts it. */
export interface ShelterSiteContext {
  compiled: string;
  practice: boolean;
}

/** The lines of a marker's popup (and of the place taken from the list), in the reader's language. */
export function shelterSiteLines(site: ShelterHistorySite, language: Language, context: ShelterSiteContext): string[] {
  const compiled = shelterListCompiled(context.compiled, language);
  return [
    `${SHELTER_HISTORY_COPY.siteLine[language]} ${SHELTER_EVIDENCE_COPY[site.evidence][language]}.`,
    ...(site.approximate ? [SHELTER_HISTORY_COPY.approximate[language]] : []),
    ...(context.practice && !site.countedForWalk ? [`${SHELTER_HISTORY_COPY.notCounted[language]} ${site.walkNote[language]}`] : []),
    ...(compiled ? [compiled] : []),
    SHELTER_HISTORY_COPY.notToday[language],
  ];
}

/** The one line under a place's name in the list: where the report came from and how well the place is located. */
export function shelterSiteSummary(site: ShelterHistorySite, language: Language, practice = false): string {
  return [
    SHELTER_EVIDENCE_COPY[site.evidence][language],
    ...(site.point ? (site.approximate ? [SHELTER_HISTORY_COPY.approximateShort[language]] : []) : [SHELTER_HISTORY_COPY.noPosition[language]]),
    ...(practice && site.point && !site.countedForWalk ? [SHELTER_HISTORY_COPY.notCountedShort[language]] : []),
  ].join(" · ");
}
