/**
 * From seeing to acting on the Command exercise replay (Mae Sai, September 2024), as pure functions: the facts the
 * inspector states about an invented item (where people go, and how to get near), and the short brief a coordinator
 * hands to a team in an exercise.
 *
 * Facts only. The page has the modelled depth and no current, so it gives no advice on the kind of team to send.
 * A distance to a shelter is a straight line, never a route; the nearest road under 0.3 m is not checked for a
 * connected way out, and bridge decks are not modelled. Every figure of the model is a T1 scenario value with low
 * confidence.
 *
 * A brief is exercise text: its first and its last line are the exercise tag, so the tag survives forwarding and
 * trimming. It is built from the stated fields of an item (kind, depth band, people band, needs, place) and from the
 * facts above; it never holds a rain value, the note of a report saved on a device or the statement of a place
 * record. The page sends nothing: a brief leaves the device only through the app the reader picks, and the text
 * message link names no recipient. No DOM access in this module.
 *
 * Thai: written by an AI assistant in the plain register of Thai public disaster notices; no native speaker has
 * reviewed it (owner decision, 5 Oct 2026).
 */

import { roadState, type Language, type LineGeometry, type Localized, type ReportedShelter, type RoadProps } from "./flood-timeline";
import { roundModelFigure, roundModelKm, type CommandChange, type CommandFigures, type CommandTambonRow } from "./flood-timeline-command";
import { COMMAND_FIGURES, commandBaseText, commandHourClock, commandHourOf, commandMoment, commandRoadList } from "./flood-timeline-command-copy";
import { reportedSiteHour, type CommandMode } from "./flood-timeline-command-feed";
import type { ExerciseItem } from "./flood-timeline-command-incidents";
import type { StagingChoice } from "./flood-timeline-command-log";
import { reportedSiteWetAt } from "./flood-timeline-command-map";
import { COMMAND_DEPTH_BAND, COMMAND_EXERCISE, COMMAND_NEED, COMMAND_PEOPLE_BAND, COMMAND_URGENCY, commandItemKind } from "./flood-timeline-command-reports-copy";
import { roadNameText } from "./flood-timeline-copy";
import { accessLevelIndex, countedInReportedSet, NO_BASELINE_CODE, nodeLostAccess, type AccessNodes } from "./flood-timeline-evacuation";

const pick = (text: Localized, language: Language): string => (language === "th" ? text.th : text.en);

// --- Straight lines on the ground ------------------------------------------------------------------------

export interface LatLon { lat: number; lon: number }

const EARTH_RADIUS_M = 6_371_008.8;
const rad = (degrees: number): number => (degrees * Math.PI) / 180;

/** The straight-line distance between two points (m), along the great circle. */
export function distanceM(a: LatLon, b: LatLon): number {
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** The bearing from one point to another, in degrees clockwise from north (0 … 360). */
export function bearingDeg(from: LatLon, to: LatLon): number {
  const dLon = rad(to.lon - from.lon);
  const y = Math.sin(dLon) * Math.cos(rad(to.lat));
  const x = Math.cos(rad(from.lat)) * Math.sin(rad(to.lat)) - Math.sin(rad(from.lat)) * Math.cos(rad(to.lat)) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

export const COMPASS_POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] as const;
export type CompassPoint = (typeof COMPASS_POINTS)[number];

/** The nearest of the eight compass points to a bearing. */
export function compassPoint(bearing: number): CompassPoint {
  return COMPASS_POINTS[Math.round((((bearing % 360) + 360) % 360) / 45) % 8];
}

export const COMPASS_NAMES: Readonly<Record<CompassPoint, Localized>> = {
  N: { en: "north", th: "ทิศเหนือ" },
  NE: { en: "north-east", th: "ทิศตะวันออกเฉียงเหนือ" },
  E: { en: "east", th: "ทิศตะวันออก" },
  SE: { en: "south-east", th: "ทิศตะวันออกเฉียงใต้" },
  S: { en: "south", th: "ทิศใต้" },
  SW: { en: "south-west", th: "ทิศตะวันตกเฉียงใต้" },
  W: { en: "west", th: "ทิศตะวันตก" },
  NW: { en: "north-west", th: "ทิศตะวันตกเฉียงเหนือ" },
};

/**
 * A straight-line distance as the page prints it: "~120 m" to the nearest 10 m below a kilometre ("<10 m" for a few
 * metres), "~1.2 km" from there on. The tilde says that the points themselves are placed to within a tolerance.
 */
export function commandDistanceText(metres: number, language: Language): string {
  const m = language === "th" ? "ม." : "m";
  const km = language === "th" ? "กม." : "km";
  if (!(metres >= 5)) return `<10 ${m}`;
  if (metres < 995) return `~${Math.max(10, Math.round(metres / 10) * 10)} ${m}`;
  return `~${(metres / 1000).toFixed(1)} ${km}`;
}

/** "~1.2 km · north-east" / "~1.2 กม. · ทิศตะวันออกเฉียงเหนือ". */
export function commandDistanceBearing(metres: number, compass: CompassPoint, language: Language): string {
  return `${commandDistanceText(metres, language)} · ${pick(COMPASS_NAMES[compass], language)}`;
}

// --- Where people go: the nearest counted shelters -------------------------------------------------------

/** A site's name without the note in brackets at its end: "ที่ว่าการอำเภอแม่สาย", "Mae Sai District Office". */
export function shortSiteName(name: string): string {
  return name.replace(/\s*\([^()]*\)\s*$/, "").trim() || name;
}

/** One of the located sites counted in the 2024 set, as seen from a point. */
export interface NearSite {
  id: string;
  name: Localized;
  distanceM: number;
  compass: CompassPoint;
  /** Whether the mapped point of the site is in modelled water at this stage; "not_modelled" outside the terrain model. */
  state: "dry" | "wet" | "not_modelled";
  /** First reported use as the data gives it: a local date, or a bound ("2024-09-15 or earlier"). */
  firstUse: string;
  /** The occupancy text of the data, as written, with its dates; null when no source gave a count. */
  occupancy: string | null;
  /** True in trainee mode before the day of the site's first dated 2024 source: not yet reported at this replay hour. */
  pending: boolean;
}

/**
 * The nearest of the located sites counted in the 2024 set, by straight line. The count of twelve is the data's: a
 * site without coordinates, the command centre and a site first used after the replay are not in that set. Nothing
 * here says that a site was open at this hour, could be reached or had room.
 */
export function nearestCountedSites(sites: readonly ReportedShelter[], point: LatLon, stage: number, time: { hour: number; mode: CommandMode }, limit = 3): NearSite[] {
  return sites
    .filter(countedInReportedSet)
    .map((site) => {
      const at = { lat: site.lat as number, lon: site.lon as number };
      const fromHour = reportedSiteHour(site);
      return {
        id: site.id,
        name: { th: site.name_th, en: site.name_en },
        distanceM: distanceM(point, at),
        compass: compassPoint(bearingDeg(point, at)),
        state: site.model_check?.m === false ? "not_modelled" as const : reportedSiteWetAt(site, stage) ? "wet" as const : "dry" as const,
        firstUse: site.first_use,
        occupancy: site.reported_capacity_or_occupancy?.replace(/^\s*occupancy\s*:\s*/i, "") || null,
        pending: time.mode === "trainee" && fromHour !== null && time.hour < fromHour,
      };
    })
    .sort((a, b) => a.distanceM - b.distanceM || a.id.localeCompare(b.id))
    .slice(0, limit);
}

// --- The access model at the nearest resident node -------------------------------------------------------

/** A resident node counts as "near" a point within this distance (m). */
export const ACCESS_NODE_REACH_M = 300;

/** The resident node nearest to a point, when one lies within `reach` metres. */
export function nearestAccessNode(nodes: Pick<AccessNodes, "count" | "lon" | "lat">, point: LatLon, reach: number = ACCESS_NODE_REACH_M): { index: number; distanceM: number } | null {
  // A box of the reach around the point first, so the great-circle distance is worked out for a few nodes only.
  const dLat = reach / 111_000;
  const dLon = reach / (111_000 * Math.max(0.2, Math.cos(rad(point.lat))));
  let best: { index: number; distanceM: number } | null = null;
  for (let index = 0; index < nodes.count; index += 1) {
    const lat = nodes.lat[index];
    const lon = nodes.lon[index];
    if (Math.abs(lat - point.lat) > dLat || Math.abs(lon - point.lon) > dLon) continue;
    const metres = distanceM(point, { lat, lon });
    if (metres <= reach && (!best || metres < best.distanceM)) best = { index, distanceM: metres };
  }
  return best;
}

/**
 * What the access model says of one resident node for one shelter set at a river stage: it keeps a shelter of the set
 * within a 2 km walk on passable roads, it had one before the flood and has lost it at this stage, or it had none
 * within 2 km even before the flood.
 */
export type NodeAccess = "kept" | "lost" | "none_before";

export function nodeAccessAt(nodes: Pick<AccessNodes, "count" | "cutCodes">, setIndex: number, index: number, stage: number, levels: readonly number[]): NodeAccess {
  const code = nodes.cutCodes[setIndex * nodes.count + index];
  if (code === NO_BASELINE_CODE) return "none_before";
  return nodeLostAccess(code, accessLevelIndex(stage, levels)) ? "lost" : "kept";
}

// --- How to get near: facts only -------------------------------------------------------------------------

/** What the model has at a point against the 0.3 m level at which a road counts as impassable. */
export type DepthFact = "not_loaded" | "outside" | "dry" | "under" | "at_or_over";

export function depthFact(depth: number | null | undefined, impassableDepthM: number): DepthFact {
  if (depth === undefined) return "not_loaded";
  if (depth === null) return "outside";
  if (!(depth > 0)) return "dry";
  return Math.round(depth * 1e6) / 1e6 >= impassableDepthM ? "at_or_over" : "under";
}

export interface RoadFeature { properties: RoadProps; geometry: LineGeometry }

/** The nearest road piece that is under the impassable depth in the model. */
export interface NearRoad {
  distanceM: number;
  /** The mapped name of the road; null for a piece without a name. */
  name: string | null;
  /** Dry, or wet under the impassable depth. */
  state: "dry" | "wet";
}

/**
 * The road piece nearest to a point among those the model has under the impassable depth at this stage, with its
 * straight-line distance. It is a fact about one piece of road: nothing checks that the piece connects to dry ground,
 * and bridge decks are not modelled.
 */
export function nearestRoadUnderDepth(roads: readonly RoadFeature[], point: LatLon, stage: number, impassableDepthM: number): NearRoad | null {
  const kLat = 111_132;
  const kLon = 111_320 * Math.cos(rad(point.lat));
  let best: NearRoad | null = null;
  for (const road of roads) {
    const { properties } = road;
    if (!properties.m) continue;
    const state = roadState(properties.h, stage, impassableDepthM, properties.k ?? 1);
    if (state === "impassable") continue;
    const line = road.geometry.coordinates;
    for (let index = 0; index < line.length; index += 1) {
      // The piece in metres around the point: east and north of it.
      const ax = (line[index][0] - point.lon) * kLon;
      const ay = (line[index][1] - point.lat) * kLat;
      let metres = Math.hypot(ax, ay);
      if (index + 1 < line.length) {
        const bx = (line[index + 1][0] - point.lon) * kLon;
        const by = (line[index + 1][1] - point.lat) * kLat;
        const length = (bx - ax) ** 2 + (by - ay) ** 2;
        const along = length > 0 ? Math.max(0, Math.min(1, -(ax * (bx - ax) + ay * (by - ay)) / length)) : 0;
        metres = Math.hypot(ax + along * (bx - ax), ay + along * (by - ay));
      }
      if (!best || metres < best.distanceM) best = { distanceM: metres, name: properties.n?.trim() || null, state };
    }
  }
  return best;
}

// --- The staging point -----------------------------------------------------------------------------------

/** Where the team starts, as a point on the map. */
export interface StagingPoint extends LatLon {
  /** The name of the site; null for a point the facilitator tapped on the map. */
  name: Localized | null;
  siteId: string | null;
}

/** The staging point of a choice: the reported site it names (when the data places it), or the tapped point. */
export function resolveStaging(choice: StagingChoice, sites: readonly ReportedShelter[]): StagingPoint | null {
  if (choice.type === "point") return { lat: choice.lat, lon: choice.lon, name: null, siteId: null };
  const site = sites.find((entry) => entry.id === choice.id);
  if (!site || site.lat === null || site.lon === null) return null;
  return { lat: site.lat, lon: site.lon, name: { th: shortSiteName(site.name_th), en: shortSiteName(site.name_en) }, siteId: site.id };
}

// --- The facts of one item -------------------------------------------------------------------------------

export interface ItemFacts {
  /** Modelled depth at the item's point (m): 0 where dry, null outside the grid, undefined before the raster has loaded. */
  depth: number | null | undefined;
  depthFact: DepthFact;
  road: NearRoad | null;
  /** The three nearest of the located sites counted in the 2024 set. */
  sites: NearSite[];
  /** The nearest resident node within 300 m and what the access model says of it; null when there is none. */
  node: { distanceM: number; access: NodeAccess } | null;
  /** The straight line from the staging point; null when the exercise has none. */
  staging: { point: StagingPoint; distanceM: number; compass: CompassPoint } | null;
}

export interface ItemFactsInput {
  point: LatLon;
  /** Whole replay hour and the mode of the exercise: in trainee mode a site is not yet reported before its first source. */
  hour: number;
  mode: CommandMode;
  /** Assumed river stage (m) at that hour. */
  stage: number;
  depth: number | null | undefined;
  impassableDepthM: number;
  roads: readonly RoadFeature[];
  sites: readonly ReportedShelter[];
  nodes: Pick<AccessNodes, "count" | "lon" | "lat" | "cutCodes">;
  /** Index of the 2024 reported set among the access sets. */
  setIndex: number;
  levels: readonly number[];
  staging: StagingPoint | null;
}

/** Everything the inspector and the brief state about one point at one replay hour. */
export function itemFacts(input: ItemFactsInput): ItemFacts {
  const node = input.setIndex >= 0 ? nearestAccessNode(input.nodes, input.point) : null;
  return {
    depth: input.depth,
    depthFact: depthFact(input.depth, input.impassableDepthM),
    road: nearestRoadUnderDepth(input.roads, input.point, input.stage, input.impassableDepthM),
    sites: nearestCountedSites(input.sites, input.point, input.stage, { hour: input.hour, mode: input.mode }),
    node: node ? { distanceM: node.distanceM, access: nodeAccessAt(input.nodes, input.setIndex, node.index, input.stage, input.levels) } : null,
    staging: input.staging
      ? { point: input.staging, distanceM: distanceM(input.staging, input.point), compass: compassPoint(bearingDeg(input.staging, input.point)) }
      : null,
  };
}

// --- The brief -------------------------------------------------------------------------------------------

/** The first and the last line of every brief. */
export const BRIEF_TAG: Localized = { en: "[EXERCISE – not a real incident]", th: "[ฝึกซ้อม – ไม่ใช่เหตุจริง]" };
/** The short tag at both ends of the text-message version. */
export const BRIEF_TAG_SHORT: Localized = { en: "[EXERCISE]", th: "[ฝึกซ้อม]" };
export const BRIEF_MAX_LINES = 9;
/** A brief is written in Thai unless the reader asks for English. */
export const BRIEF_DEFAULT_LANGUAGE: Language = "th";

export interface ItemBriefInput {
  /** The item with the urgency in force (the operator's, when one was set). */
  item: Pick<ExerciseItem, "id" | "kind" | "subject" | "urgency" | "place" | "point" | "toleranceM" | "depthBand" | "peopleBand" | "needs">;
  tambon: Localized | null;
  /** The callsign of the team the item is assigned to; null before it is assigned. */
  callsign: string | null;
  /** Whole replay hour at which the brief is written. */
  hour: number;
  facts: Pick<ItemFacts, "depth" | "depthFact" | "road" | "sites">;
}

const coordinates = (point: LatLon): string => `${point.lat.toFixed(4)},${point.lon.toFixed(4)}`;
const depthValue = (depth: number): string => (depth < 0.05 ? "<0.1" : `~${depth.toFixed(1)}`);

function needsText(needs: ExerciseItem["needs"], language: Language): string {
  if (needs.length === 0) return pick(COMMAND_EXERCISE.noNeeds, language);
  return `${pick(COMMAND_EXERCISE.needs, language)}: ${needs.map((need) => pick(COMMAND_NEED[need], language)).join(language === "th" ? " " : ", ")}`;
}

/** The "access" line: what the model has at the point, the nearest road under 0.3 m, and that the current is not known. */
function accessLine(facts: ItemBriefInput["facts"], language: Language): string {
  const th = language === "th";
  const parts: string[] = [];
  switch (facts.depthFact) {
    case "not_loaded": parts.push(th ? "ยังอ่านค่าความลึกจากแบบจำลองไม่ได้" : "model depth not loaded"); break;
    case "outside": parts.push(th ? "จุดนี้อยู่นอกพื้นที่ที่แบบจำลองครอบคลุม" : "the point is outside the modelled area"); break;
    case "dry": parts.push(th ? "แบบจำลองแห้ง ณ จุดนี้" : "model dry at the point"); break;
    default: parts.push(th ? `แบบจำลองน้ำลึก ${depthValue(facts.depth as number)} ม.` : `model depth ${depthValue(facts.depth as number)} m`);
  }
  if (facts.road) {
    parts.push(th
      ? `ถนนที่น้ำต่ำกว่า 0.3 ม. ใกล้สุด ${commandDistanceText(facts.road.distanceM, language)}`
      : `nearest road under 0.3 m in the model ${commandDistanceText(facts.road.distanceM, language)}`);
  }
  parts.push(th ? "ไม่ทราบความแรงกระแสน้ำ" : "strength of the current not known");
  return `${th ? "เข้าถึง" : "Access"}: ${parts.join(" · ")}`;
}

/** The "nearest shelter" line: the nearest counted site that has been reported by this replay hour, by straight line. */
function shelterLine(sites: readonly NearSite[], language: Language): string {
  const th = language === "th";
  const lead = th ? "ที่พักพิงใกล้สุด (เส้นตรง)" : "Nearest shelter (straight line)";
  const site = sites.find((entry) => !entry.pending);
  if (!site) return `${lead}: ${th ? "ยังไม่มีรายงานที่พักพิง ณ ชั่วโมงนี้ของการย้อนดู" : "none reported yet at this replay hour"}`;
  const wet = site.state === "wet" ? (th ? " (น้ำท่วมถึงตามแบบจำลอง)" : " (wet in the model)") : "";
  return `${lead}: ${shortSiteName(pick(site.name, language))} ${commandDistanceText(site.distanceM, language)}${wet}`;
}

/**
 * The brief of one invented item, at most nine lines. The first and the last line are the exercise tag. Every other
 * line is built from the stated fields of the item and from the facts of the model: no rain value, no note and no
 * free text enters it.
 */
export function itemBriefLines(input: ItemBriefInput, language: Language = BRIEF_DEFAULT_LANGUAGE): string[] {
  const th = language === "th";
  const { item, facts } = input;
  const tag = pick(BRIEF_TAG, language);
  const team = input.callsign ? (th ? ` · ชุด ${input.callsign}` : ` · team ${input.callsign}`) : "";
  const area = input.tambon ? (th ? ` ต.${input.tambon.th}` : `, ${input.tambon.en} subdistrict`) : "";
  const place = th ? item.place.th : `${item.place.th} (${item.place.en})`;
  const tolerance = th ? `(±${item.toleranceM} ม.)` : `(±${item.toleranceM} m)`;
  return [
    `${tag} ${item.id}${team}`,
    `${th ? "เหตุ" : "What"}: ${commandItemKind(item, language)} (${pick(COMMAND_URGENCY[item.urgency], language)}) · ${pick(COMMAND_DEPTH_BAND[item.depthBand], language)}`,
    `${th ? "ที่" : "Where"}: ${place}${area} ${tolerance} ${coordinates(item.point)}`,
    `${th ? "คน" : "People"}: ${pick(COMMAND_PEOPLE_BAND[item.peopleBand], language)} · ${needsText(item.needs, language)}`,
    accessLine(facts, language),
    shelterLine(facts.sites, language),
    `${th ? "เวลาในการย้อนดู" : "Replay time"}: ${commandMoment(input.hour, language)}`,
    th ? "ที่มา: รายการฝึกซ้อม (สมมุติขึ้น) · แบบจำลองความเชื่อมั่นต่ำ" : "Source: exercise item (invented) · model, low confidence",
    tag,
  ];
}

// --- The text-message version ----------------------------------------------------------------------------

/** The longest text-message version: two parts of a Thai message (67 characters each when joined). */
export const SMS_MAX_CHARS = 134;

const GSM7_BASIC = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà";
const GSM7_EXTENDED = "^{}\\[~]|€";

/**
 * How many parts a text message takes. A message in the basic alphabet of text messages holds 160 characters, or 153
 * per part when joined; any other character (every Thai letter) makes it a 70-character message, or 67 per part.
 * This is the standard's arithmetic; what a carrier does with it was not tested.
 */
export function smsParts(text: string): { characters: number; parts: number; alphabet: "basic" | "unicode" } {
  let septets = 0;
  let basic = true;
  for (const character of text) {
    if (GSM7_BASIC.includes(character)) septets += 1;
    else if (GSM7_EXTENDED.includes(character)) septets += 2;
    else { basic = false; break; }
  }
  if (basic) return { characters: text.length, parts: septets <= 160 ? 1 : Math.ceil(septets / 153), alphabet: "basic" };
  return { characters: text.length, parts: text.length <= 70 ? 1 : Math.ceil(text.length / 67), alphabet: "unicode" };
}

/**
 * The text-message version of a brief: two lines of at most 134 characters together, with the short exercise tag at
 * both ends. When the lines run long, the people band goes first, then the depth band, then the subdistrict, and
 * last the end of the place name.
 */
export function itemBriefSms(input: Pick<ItemBriefInput, "item" | "tambon" | "callsign">, language: Language = BRIEF_DEFAULT_LANGUAGE): string {
  const th = language === "th";
  const { item } = input;
  const tag = pick(BRIEF_TAG_SHORT, language);
  // A plain hyphen keeps an English message in the basic alphabet of text messages.
  const plain = (text: string): string => (th ? text : text.replaceAll("–", "-"));
  const head = `${tag} ${item.id}${input.callsign ? (th ? ` ชุด ${input.callsign}` : ` ${input.callsign}`) : ""}: ${commandItemKind(item, language)}`;
  const depth = item.depthBand === "not_stated" ? null : plain(pick(COMMAND_DEPTH_BAND[item.depthBand], language));
  const people = item.peopleBand === "none_stated" ? null : plain(pick(COMMAND_PEOPLE_BAND[item.peopleBand], language));
  const area = input.tambon ? (th ? `ต.${input.tambon.th}` : input.tambon.en) : null;
  const build = (parts: { depth: boolean; people: boolean; area: boolean }, place: string): string => {
    const first = [head, parts.depth ? depth : null, parts.people ? people : null].filter(Boolean).join(th ? " " : ", ");
    const second = [[place, parts.area ? area : null].filter(Boolean).join(th ? " " : ", "), coordinates(item.point), tag].join(" ");
    return `${first}\n${second}`;
  };
  const place = pick(item.place, language);
  for (const parts of [
    { depth: true, people: true, area: true }, { depth: true, people: false, area: true }, { depth: false, people: false, area: true }, { depth: false, people: false, area: false },
  ]) {
    const text = build(parts, place);
    if (text.length <= SMS_MAX_CHARS) return text;
  }
  const bare = { depth: false, people: false, area: false };
  const room = SMS_MAX_CHARS - build(bare, "").length - 1;
  return build(bare, `${[...place].slice(0, Math.max(0, room)).join("")}…`);
}

/**
 * The link that hands a text to the device's own message app. It names no recipient, so an exercise brief cannot go
 * to a hotline by a slip: the reader has to type the number.
 */
export function smsHref(text: string): string {
  return `sms:?&body=${encodeURIComponent(text)}`;
}

// --- The situation brief ---------------------------------------------------------------------------------

export interface SituationBriefInput {
  /** Whole replay hour. */
  hour: number;
  figures: CommandFigures;
  /** The rows of the table in this hour's order: the first three with residents who lost shelter access are named. */
  rows: readonly Pick<CommandTambonRow, "th" | "en" | "lostAccess">[];
  change: Pick<CommandChange, "sinceHour" | "newlyImpassable">;
}

/**
 * The situation at one replay hour in nine lines: the three model figures, the three subdistricts with the most
 * residents who lost shelter access (a count of this hour, never a score or a class), and the named roads newly
 * impassable. The exercise tag is the first and the last line.
 */
export function situationBriefLines(input: SituationBriefInput, language: Language = BRIEF_DEFAULT_LANGUAGE): string[] {
  const th = language === "th";
  const tag = pick(BRIEF_TAG, language);
  const { figures, change } = input;
  const total = Math.round(figures.roadKmTotal).toLocaleString("en-US");
  const top = input.rows.filter((row) => Math.round(row.lostAccess) > 0).slice(0, 3)
    .map((row) => `${th ? row.th : row.en} ${roundModelFigure(row.lostAccess).text}`);
  const roads = change.newlyImpassable.named;
  const since = change.sinceHour === null ? null : commandHourClock(change.sinceHour, language);
  return [
    `${tag} ${th ? "สรุปสถานการณ์" : "Situation brief"}`,
    `${th ? "เวลาในการย้อนดู" : "Replay time"}: ${commandMoment(input.hour, language)} (${commandHourOf(input.hour, language)})`,
    th
      ? `${pick(COMMAND_FIGURES.lostAccess, language)}: ${roundModelFigure(figures.lostAccess).text} คน (${commandBaseText(figures.withinReachBefore, language, true)})`
      : `Lost shelter access: ${roundModelFigure(figures.lostAccess).text} residents (${commandBaseText(figures.withinReachBefore, language, true)})`,
    th
      ? `${pick(COMMAND_FIGURES.inWater, language)}: ${roundModelFigure(figures.inWater).text} คน`
      : `Residents in modelled water: ${roundModelFigure(figures.inWater).text}`,
    th
      ? `${pick(COMMAND_FIGURES.roads, language)}: ${roundModelKm(figures.roadKmImpassable).text} กม. จาก ${total} กม.`
      : `Roads impassable: ${roundModelKm(figures.roadKmImpassable).text} km of ${total} km`,
    top.length > 0
      ? `${th ? "ตำบลที่มีผู้สูญเสียการเข้าถึงที่พักพิงมากที่สุด" : "Most residents who lost shelter access"}: ${top.join(" · ")}`
      : th ? "ยังไม่มีตำบลใดมีผู้สูญเสียการเข้าถึงที่พักพิง ณ ชั่วโมงนี้" : "No subdistrict has residents who lost shelter access at this hour",
    roads.length > 0 && since !== null
      ? `${th ? `ถนนที่เริ่มสัญจรไม่ได้ตั้งแต่ ${since}` : `Newly impassable since ${since}`}: ${commandRoadList(roads, language, 3)}`
      : th ? "ไม่มีถนนที่มีชื่อเริ่มสัญจรไม่ได้ในชั่วโมงนี้" : "No named road became impassable this hour",
    th ? "ที่มา: แบบจำลอง ความเชื่อมั่นต่ำ · ไม่ได้จำลองกระแสน้ำ" : "Source: model, low confidence · current not modelled",
    tag,
  ];
}

/** A road name as a line prints it: the known English label in English, the mapped name otherwise. */
export function commandRoadName(name: string | null, language: Language): string {
  if (!name) return language === "th" ? "ถนนไม่มีชื่อ" : "an unnamed road";
  return roadNameText(name, language).primary;
}
