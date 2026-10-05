/**
 * Reports on the map of the Command exercise replay (Mae Sai, September 2024), as pure functions: the invented
 * exercise items and the rule that sets their urgency, how each marker is drawn in each handling state, the clusters
 * of the district zoom, the reports saved on this device counted per subdistrict, and the modelled depth at a point.
 *
 * Three kinds of thing are kept apart and never counted together:
 *   - exercise items are invented by the team for practice. Every id starts "EX-"; none is a real call, person or
 *     address, and none copies a plea made in 2024;
 *   - place records are what news reported in 2024 (reported, anecdotal, not surveyed); they live in the replay data;
 *   - reports saved on this device carry the date they were saved and a subdistrict only; they are outside the replay
 *     clock and are sent to nobody.
 * No DOM access in this module.
 */

import { cellDepth, projectToFrame, type Localized } from "./flood-timeline";
import { clampCommandHour, COMMAND_LAST_HOUR } from "./flood-timeline-command";

// --- The exercise file -----------------------------------------------------------------------------------

/** Where the page reads the invented items from. */
export const EXERCISE_FILE_URL = "/exercises/mae-sai-2024/injects.v1.json";
export const EXERCISE_SCHEMA = "floodguard.exercise_injects.v1";
/** Every id of an invented item starts with this, so an item is never mistaken for a real report. */
export const EXERCISE_ID_PREFIX = "EX-";

/** How urgent an invented item is. Set by its author from the facts it states, never by the model. */
export type ExerciseUrgency = "life_at_risk" | "urgent" | "information";
export const EXERCISE_URGENCIES: readonly ExerciseUrgency[] = ["life_at_risk", "urgent", "information"];
/** A call for help (drawn as an octagon) or a report of depth or of a road (drawn as a rounded square). */
export type ExerciseKind = "call" | "report";
export type ExerciseSubject = "help" | "depth" | "road";
/** The stated facts the urgency rule reads. */
export type ExerciseFact = "on_roof" | "chest_or_above_with_people" | "infant_or_bedridden" | "no_food_for_a_day";
export const EXERCISE_FACTS: readonly ExerciseFact[] = ["on_roof", "chest_or_above_with_people", "infant_or_bedridden", "no_food_for_a_day"];
export type ExerciseDepthBand = "not_stated" | "ankle" | "knee" | "waist" | "chest" | "over_head";
export const EXERCISE_DEPTH_BANDS: readonly ExerciseDepthBand[] = ["not_stated", "ankle", "knee", "waist", "chest", "over_head"];
export type ExercisePeopleBand = "none_stated" | "1-2" | "3-5" | "6-10" | "11-20" | "over_20";
export const EXERCISE_PEOPLE_BANDS: readonly ExercisePeopleBand[] = ["none_stated", "1-2", "3-5", "6-10", "11-20", "over_20"];
export type ExerciseNeed = "evacuation" | "medical" | "food_water" | "information" | "power" | "road_clearing";
export const EXERCISE_NEEDS: readonly ExerciseNeed[] = ["evacuation", "medical", "food_water", "information", "power", "road_clearing"];

/** One invented call or report. */
export interface ExerciseItem {
  /** "EX-nn". */
  id: string;
  /** The replay hour at which the item arrives (0 … 264). */
  hour: number;
  kind: ExerciseKind;
  subject: ExerciseSubject;
  urgency: ExerciseUrgency;
  facts: ExerciseFact[];
  /** A community or road that news named in 2024. No soi, no house, no person. */
  place: Localized;
  tambonId: string;
  point: { lat: number; lon: number };
  /** How closely the item is placed (m): the radius of the dashed circle drawn on selection. */
  toleranceM: number;
  depthBand: ExerciseDepthBand;
  peopleBand: ExercisePeopleBand;
  needs: ExerciseNeed[];
  /** What the invented message says, in one to three plain sentences. */
  text: Localized;
}

export interface ExerciseFile {
  schema: typeof EXERCISE_SCHEMA;
  exerciseId: string;
  /** Always true: the file holds invented items only. */
  simulated: true;
  label: Localized;
  notice: Localized;
  /** The urgency rule in words, as the page prints it. */
  rule: Localized;
  /** In the order of their arrival. */
  items: ExerciseItem[];
}

export class ExerciseFileError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExerciseFileError";
  }
}

/** The facts that make an item "life at risk", and those that make it "urgent". */
export const EXERCISE_URGENCY_RULE: Readonly<Record<Exclude<ExerciseUrgency, "information">, readonly ExerciseFact[]>> = {
  life_at_risk: ["on_roof", "chest_or_above_with_people"],
  urgent: ["infant_or_bedridden", "no_food_for_a_day"],
};

/**
 * The stated-fact rule. Life at risk: people on a roof, or people standing in water at chest height or above (people
 * who are dry on an upper floor above deep water are not in it, so the depth band alone never sets this level).
 * Urgent: an infant or a bedridden person, or no food for a day. Anything else is information. The rule reads only
 * what the item states; the model plays no part.
 */
export function exerciseUrgency(facts: readonly ExerciseFact[]): ExerciseUrgency {
  if (facts.some((fact) => EXERCISE_URGENCY_RULE.life_at_risk.includes(fact))) return "life_at_risk";
  if (facts.some((fact) => EXERCISE_URGENCY_RULE.urgent.includes(fact))) return "urgent";
  return "information";
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const isLocalized = (value: unknown): value is Localized => isRecord(value) && typeof value.en === "string" && typeof value.th === "string" && value.en.trim() !== "" && value.th.trim() !== "";

/**
 * True when a text holds something shaped like a phone number: seven or more digits in one run, with single spaces
 * or hyphens between its groups at most, or an area code in brackets. Counts of people and dates in words never are.
 */
export function hasPhonePattern(text: string): boolean {
  if (/\(0\d{1,2}\)/.test(text)) return true;
  for (const match of text.matchAll(/\+?\d+(?:[ -]\d+)*/g)) if (match[0].replace(/\D/g, "").length >= 7) return true;
  return false;
}

/** True when a text names a soi or a house number, or addresses a person by a title: an invented item holds none. */
export function hasAddressOrName(text: string): boolean {
  return /(?<![A-Za-z])soi(?![A-Za-z])/i.test(text)
    || /ซอย|บ้านเลขที่|เลขที่ ?\d/.test(text)
    || /(?<![A-Za-z])house (?:no\.?|number)(?![A-Za-z])/i.test(text)
    || /(?<![A-Za-z])(?:[Mm]rs?|[Mm]s|[Mm]iss|[Kk]hun)\.? [A-Z]/.test(text)
    || /(?:นางสาว|น\.ส\.|นาย|นาง) ?[ก-ฮ]/.test(text);
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], what: string): T {
  if (typeof value !== "string" || !allowed.includes(value as T)) throw new ExerciseFileError(`${what}: "${String(value)}" is not one of ${allowed.join(", ")}`);
  return value as T;
}

function listOf<T extends string>(value: unknown, allowed: readonly T[], what: string): T[] {
  if (!Array.isArray(value)) throw new ExerciseFileError(`${what} is not a list`);
  const items = value.map((item) => oneOf(item, allowed, what));
  if (new Set(items).size !== items.length) throw new ExerciseFileError(`${what} repeats an entry`);
  return items;
}

function localized(value: unknown, what: string, maxLength: number): Localized {
  if (!isLocalized(value)) throw new ExerciseFileError(`${what} needs English and Thai text`);
  for (const text of [value.en, value.th]) {
    if (text.length > maxLength) throw new ExerciseFileError(`${what} is longer than ${maxLength} characters`);
    if (hasPhonePattern(text)) throw new ExerciseFileError(`${what} holds something shaped like a phone number`);
    if (hasAddressOrName(text)) throw new ExerciseFileError(`${what} names a soi, a house or a person`);
  }
  return { en: value.en, th: value.th };
}

function parseItem(value: unknown, index: number): ExerciseItem {
  const what = `Exercise item ${index + 1}`;
  if (!isRecord(value)) throw new ExerciseFileError(`${what} is not an object`);
  const id = value.id;
  if (typeof id !== "string" || !/^EX-\d{2}$/.test(id)) throw new ExerciseFileError(`${what}: the id must read ${EXERCISE_ID_PREFIX}nn`);
  const hour = value.hour;
  if (typeof hour !== "number" || !Number.isInteger(hour) || hour < 0 || hour > COMMAND_LAST_HOUR) throw new ExerciseFileError(`${id}: the replay hour must be a whole hour from 0 to ${COMMAND_LAST_HOUR}`);
  const kind = oneOf(value.kind, ["call", "report"] as const, `${id} kind`);
  const subject = oneOf(value.subject, ["help", "depth", "road"] as const, `${id} subject`);
  if ((kind === "call") !== (subject === "help")) throw new ExerciseFileError(`${id}: a call is a call for help, and a report is of depth or of a road`);
  const facts = listOf(value.facts, EXERCISE_FACTS, `${id} facts`);
  const urgency = oneOf(value.urgency, EXERCISE_URGENCIES, `${id} urgency`);
  if (urgency !== exerciseUrgency(facts)) throw new ExerciseFileError(`${id}: the urgency "${urgency}" does not follow from its stated facts (the rule gives "${exerciseUrgency(facts)}")`);
  const depthBand = oneOf(value.depth_band, EXERCISE_DEPTH_BANDS, `${id} depth band`);
  const peopleBand = oneOf(value.people_band, EXERCISE_PEOPLE_BANDS, `${id} people band`);
  if (facts.length > 0 && peopleBand === "none_stated") throw new ExerciseFileError(`${id}: a stated fact about people needs a number of people`);
  if (facts.includes("chest_or_above_with_people") && depthBand !== "chest" && depthBand !== "over_head") throw new ExerciseFileError(`${id}: "people standing in water at chest height or above" needs that depth band`);
  if (kind === "report" && facts.length > 0) throw new ExerciseFileError(`${id}: a report of depth or of a road states no fact about people`);
  if (typeof value.tambon_id !== "string" || !/^TH\d{6}$/.test(value.tambon_id)) throw new ExerciseFileError(`${id}: the subdistrict code is missing`);
  const point = value.point;
  if (!isRecord(point) || typeof point.lat !== "number" || typeof point.lon !== "number" || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)
    || Math.abs(point.lat) > 90 || Math.abs(point.lon) > 180) throw new ExerciseFileError(`${id}: the point is missing`);
  const tolerance = value.tolerance_m;
  if (typeof tolerance !== "number" || !Number.isInteger(tolerance) || tolerance < 100 || tolerance > 400) throw new ExerciseFileError(`${id}: the tolerance must be 100 to 400 m`);
  return {
    id,
    hour,
    kind,
    subject,
    urgency,
    facts,
    place: localized(value.place, `${id} place`, 80),
    tambonId: value.tambon_id,
    point: { lat: point.lat, lon: point.lon },
    toleranceM: tolerance,
    depthBand,
    peopleBand,
    needs: listOf(value.needs, EXERCISE_NEEDS, `${id} needs`),
    text: localized(value.text, `${id} text`, 240),
  };
}

/**
 * Read the exercise file. It refuses a file that is not marked as simulated, an id that does not start "EX-", an
 * urgency that does not follow from the stated facts, and any text that holds something shaped like a phone number,
 * a soi, a house number or a person's title. A refused file shows no exercise item at all.
 */
export function parseExerciseFile(value: unknown): ExerciseFile {
  if (!isRecord(value) || value.schema !== EXERCISE_SCHEMA) throw new ExerciseFileError("Not an exercise file of this schema");
  if (value.simulated !== true) throw new ExerciseFileError("The exercise file is not marked as simulated");
  if (typeof value.exercise_id !== "string" || !value.exercise_id) throw new ExerciseFileError("The exercise file names no exercise");
  const rule = isRecord(value.urgency_rule) ? value.urgency_rule : null;
  if (!rule) throw new ExerciseFileError("The exercise file states no urgency rule");
  for (const level of ["life_at_risk", "urgent"] as const) {
    const stated = listOf(rule[level], EXERCISE_FACTS, `Urgency rule, ${level}`);
    const own = EXERCISE_URGENCY_RULE[level];
    if (stated.length !== own.length || !own.every((fact) => stated.includes(fact))) throw new ExerciseFileError(`The urgency rule of the file differs from the page's rule for "${level}"`);
  }
  if (!Array.isArray(value.items) || value.items.length === 0 || value.items.length > 40) throw new ExerciseFileError("The exercise file needs 1 to 40 items");
  const items = value.items.map(parseItem);
  if (new Set(items.map((item) => item.id)).size !== items.length) throw new ExerciseFileError("Two exercise items share an id");
  items.sort((a, b) => a.hour - b.hour || a.id.localeCompare(b.id));
  return {
    schema: EXERCISE_SCHEMA,
    exerciseId: value.exercise_id,
    simulated: true,
    label: localized(value.label, "The label", 80),
    notice: localized(value.notice, "The notice", 600),
    rule: localized(rule.text, "The urgency rule", 600),
    items,
  };
}

// --- Arrival, waiting and handling -----------------------------------------------------------------------

/**
 * How an item is being handled. Nothing is ever called checked or proven: an item is new, acknowledged, assigned to a
 * callsign, done, or dropped (a duplicate, or one that could not be reached).
 */
export type ExerciseStatus = "new" | "acknowledged" | "assigned" | "done" | "dropped";
export const EXERCISE_STATUSES: readonly ExerciseStatus[] = ["new", "acknowledged", "assigned", "done", "dropped"];
export interface ExerciseHandling { status: ExerciseStatus; callsign: string | null }
export const NEW_HANDLING: ExerciseHandling = { status: "new", callsign: null };
export type ExerciseHandlingMap = ReadonlyMap<string, ExerciseHandling>;

export const exerciseHandling = (handling: ExerciseHandlingMap | null | undefined, id: string): ExerciseHandling => handling?.get(id) ?? NEW_HANDLING;
/** An item is open until it is done or dropped. */
export const isOpenStatus = (status: ExerciseStatus): boolean => status !== "done" && status !== "dropped";

/** The items that have arrived by replay `hour`, in the order of their arrival. An item never shows before its hour. */
export function arrivedExerciseItems<T extends Pick<ExerciseItem, "hour">>(items: readonly T[], hour: number): T[] {
  const at = clampCommandHour(hour);
  return items.filter((item) => item.hour <= at);
}

/**
 * The selected item as the inspector may show it at replay `hour`: the item with that id once it has arrived, and
 * nothing before its hour (a step back in time takes a selected item off the screen with its marker).
 */
export function shownExerciseItem<T extends Pick<ExerciseItem, "id" | "hour">>(items: readonly T[], id: string | null | undefined, hour: number): T | null {
  if (!id) return null;
  return arrivedExerciseItems(items, hour).find((item) => item.id === id) ?? null;
}

/** The items that arrive after replay hour `after` and up to `upTo`: what a step forward brings. */
export function exerciseArrivals(items: readonly ExerciseItem[], after: number, upTo: number): ExerciseItem[] {
  return items.filter((item) => item.hour > after && item.hour <= upTo);
}

/** The replay hours at which a life-at-risk item arrives: playback pauses there when the page is asked to. */
export function lifeAtRiskHours(items: readonly ExerciseItem[]): Set<number> {
  return new Set(items.filter((item) => item.urgency === "life_at_risk").map((item) => item.hour));
}

/** Whole replay hours an item has waited at `hour`; 0 at the hour it arrives. The clock is the replay's, never today's. */
export function waitingHours(item: Pick<ExerciseItem, "hour">, hour: number): number {
  return Math.max(0, clampCommandHour(hour) - item.hour);
}

/** Counted exercise items at one replay hour. They are plain counts and are never added to any count of real reports. */
export interface ExerciseCounts {
  /** Items that have arrived by this hour. */
  arrived: number;
  /** Arrived items that are neither done nor dropped. */
  open: number;
  /** Open items at "life at risk". */
  lifeAtRisk: number;
}

export function exerciseCounts(items: readonly ExerciseItem[], hour: number, handling?: ExerciseHandlingMap | null): ExerciseCounts {
  const arrived = arrivedExerciseItems(items, hour);
  const open = arrived.filter((item) => isOpenStatus(exerciseHandling(handling, item.id).status));
  return { arrived: arrived.length, open: open.length, lifeAtRisk: open.filter((item) => item.urgency === "life_at_risk").length };
}

/** The most urgent of some items, the earliest first among equals; null for none. */
export function mostUrgentItem<T extends Pick<ExerciseItem, "urgency" | "hour" | "id">>(items: readonly T[]): T | null {
  const rank = (item: T) => EXERCISE_URGENCIES.indexOf(item.urgency);
  return [...items].sort((a, b) => rank(a) - rank(b) || a.hour - b.hour || a.id.localeCompare(b.id))[0] ?? null;
}

// --- How a marker is drawn -------------------------------------------------------------------------------

/**
 * The colours of the urgency levels: colour-blind safe, and on purpose not the red, yellow and green of medical
 * triage, so a marker is never read as a patient's condition. They are used on exercise markers and nowhere else.
 */
export const EXERCISE_COLOURS = { life_at_risk: "#D55E00", urgent: "#E69F00", information: "#0072B2", closed: "#c3cacb" } as const;

/** How one exercise marker is drawn. Each meaning has at least two cues, so colour is never the only one. */
export interface ExerciseMarkerSpec {
  /** Octagon: a call for help. Rounded square: a report of depth or of a road. */
  shape: "octagon" | "square";
  /** Urgency by size (px), symbol and colour together. */
  size: 36 | 30 | 26;
  symbol: "!!" | "!" | "i";
  fill: string;
  symbolColour: "#ffffff" | "#12262d";
  /** The white halo of a life-at-risk item. */
  halo: boolean;
  /** Handling state by outline: dashed while new, solid once acknowledged or assigned, none when closed. */
  outline: "dashed" | "solid" | "none";
  /** Done or dropped: grey, with a tick in place of the symbol. */
  closed: boolean;
  /** The line under the marker: the callsign once assigned, with the waiting clock while an urgent or life-at-risk item is open. */
  showsCallsign: boolean;
  showsWaiting: boolean;
}

const URGENCY_LOOK: Readonly<Record<ExerciseUrgency, Pick<ExerciseMarkerSpec, "size" | "symbol" | "fill" | "symbolColour" | "halo">>> = {
  life_at_risk: { size: 36, symbol: "!!", fill: EXERCISE_COLOURS.life_at_risk, symbolColour: "#ffffff", halo: true },
  urgent: { size: 30, symbol: "!", fill: EXERCISE_COLOURS.urgent, symbolColour: "#12262d", halo: false },
  information: { size: 26, symbol: "i", fill: EXERCISE_COLOURS.information, symbolColour: "#ffffff", halo: false },
};

export function exerciseMarkerSpec(item: Pick<ExerciseItem, "kind" | "urgency">, status: ExerciseStatus = "new"): ExerciseMarkerSpec {
  const look = URGENCY_LOOK[item.urgency];
  const closed = !isOpenStatus(status);
  return {
    shape: item.kind === "call" ? "octagon" : "square",
    ...look,
    fill: closed ? EXERCISE_COLOURS.closed : look.fill,
    symbolColour: closed ? "#12262d" : look.symbolColour,
    halo: look.halo && !closed,
    outline: closed ? "none" : status === "new" ? "dashed" : "solid",
    closed,
    showsCallsign: status === "assigned",
    // An item of information waits for nobody to be moved: its waiting clock is in its popup and in the inspector, not
    // on the map, where the lines of the urgent items need the room.
    showsWaiting: !closed && item.urgency !== "information",
  };
}

// --- Markers that would cover each other at the town zoom --------------------------------------------------

/** A box on screen, in pixels. */
export interface MarkerBox { left: number; top: number; right: number; bottom: number }

/** The box of a place-record bubble whose tail ends at (x, y): the bubble above the point, with room for its dry badge. */
export const recordBubbleBox = (x: number, y: number): MarkerBox => ({ left: x - 14, top: y - 28, right: x + 20, bottom: y + 1 });

/** The box of an exercise marker `size` px wide whose middle is at (x, y), with the line of `lineWidth` px under it. */
export function exerciseMarkerBox(x: number, y: number, size: number, lineWidth: number): MarkerBox {
  const half = Math.max(size / 2 + 2, lineWidth / 2);
  return { left: x - half, top: y - size / 2 - 2, right: x + half, bottom: y + size / 2 + 3 + (lineWidth > 0 ? 17 : 0) };
}

/** The area two boxes share, in square pixels; 0 when they do not touch. */
const sharedArea = (a: MarkerBox, b: MarkerBox): number => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));

/**
 * Where a marker may stand when its own point is taken, in the order they are tried: its point, then beside it, then
 * below it, then further out, and last above it (the bubbles of the place records stand above their points, so the
 * places above are seldom free).
 */
export const ITEM_MARKER_OFFSETS: readonly (readonly [number, number])[] = [
  [0, 0], [36, 4], [-36, 4], [0, 40], [40, 36], [-40, 36], [62, 0], [-62, 0], [0, 66], [66, 40], [-66, 40],
  [0, -46], [44, -40], [-44, -40], [88, 8], [-88, 8], [80, 56], [-80, 56],
];

/**
 * Places the exercise markers of the town zoom so that none covers a place-record bubble or another exercise marker.
 * `items` are taken in the order given (the caller puts the most urgent first, so those keep their own point); each
 * takes the first offset of `ITEM_MARKER_OFFSETS` at which its box is free. A marker moved off its point is drawn
 * with a thin line back to it; one that finds no free place takes the place where it covers least. The result depends
 * only on the distances on screen, so it changes with the zoom and never with a pan.
 */
export function placeItemMarkers(
  obstacles: readonly MarkerBox[],
  items: readonly { x: number; y: number; size: number; lineWidth: number }[],
): { dx: number; dy: number }[] {
  const taken: MarkerBox[] = [...obstacles];
  return items.map((item) => {
    let best: { dx: number; dy: number; box: MarkerBox; covered: number } | null = null;
    for (const [dx, dy] of ITEM_MARKER_OFFSETS) {
      const box = exerciseMarkerBox(item.x + dx, item.y + dy, item.size, item.lineWidth);
      const covered = taken.reduce((sum, other) => sum + sharedArea(box, other), 0);
      if (best === null || covered < best.covered) best = { dx, dy, box, covered };
      if (covered === 0) break;
    }
    taken.push(best!.box);
    return { dx: best!.dx, dy: best!.dy };
  });
}

// --- Clusters of the district zoom -----------------------------------------------------------------------

/** Below this zoom, markers that lie close together merge into one count mark. */
export const CLUSTER_BELOW_ZOOM = 13;
/** Markers within this many pixels of a cluster's first marker join it. */
export const CLUSTER_RADIUS_PX = 40;

/**
 * One marker as the clustering reads it: where it is on screen, how many 2024 place records it holds, how many
 * invented exercise items, and whether it is an open life-at-risk item.
 */
export interface ClusterPoint { x: number; y: number; records: number; items: number; lifeAtRisk: boolean }
export interface MarkerCluster {
  /** Indices into the points, in their order. */
  members: number[];
  /** The middle of the members on screen. */
  x: number;
  y: number;
  /** The 2024 place records the cluster holds (reported in news). */
  records: number;
  /**
   * The invented exercise items it holds. The two counts are never added: a count mark prints them apart, the
   * invented ones under the exercise tag, so no photo of the screen shows invented items as reports of 2024.
   */
  items: number;
  /** Open life-at-risk items among the exercise items: the mark then shows "!!" and this count. */
  lifeAtRisk: number;
}

/**
 * Group markers that lie within `radius` pixels of the first marker of a group; then merge groups whose middles lie
 * within `radius` of each other, so two count marks never stand on top of one another. A marker on its own is a group
 * of one. The result depends only on the order of the points, so the same view always clusters the same way.
 */
export function clusterMarkers(points: readonly ClusterPoint[], radius: number = CLUSTER_RADIUS_PX): MarkerCluster[] {
  let groups: number[][] = [];
  points.forEach((point, index) => {
    const group = groups.find((members) => Math.hypot(points[members[0]].x - point.x, points[members[0]].y - point.y) <= radius);
    if (group) group.push(index);
    else groups.push([index]);
  });
  const middle = (members: readonly number[]) => ({
    x: members.reduce((sum, index) => sum + points[index].x, 0) / members.length,
    y: members.reduce((sum, index) => sum + points[index].y, 0) / members.length,
  });
  for (let merged = true; merged;) {
    merged = false;
    for (let a = 0; a < groups.length && !merged; a += 1) {
      for (let b = a + 1; b < groups.length && !merged; b += 1) {
        const first = middle(groups[a]);
        const second = middle(groups[b]);
        if (Math.hypot(first.x - second.x, first.y - second.y) > radius) continue;
        groups = [...groups.slice(0, a), [...groups[a], ...groups[b]].sort((x, y) => x - y), ...groups.slice(a + 1, b), ...groups.slice(b + 1)];
        merged = true;
      }
    }
  }
  return groups.map((members) => ({
    members,
    x: members.reduce((sum, index) => sum + points[index].x, 0) / members.length,
    y: members.reduce((sum, index) => sum + points[index].y, 0) / members.length,
    records: members.reduce((sum, index) => sum + points[index].records, 0),
    items: members.reduce((sum, index) => sum + points[index].items, 0),
    lifeAtRisk: members.filter((index) => points[index].lifeAtRisk).length,
  }));
}

// --- Reports saved on this device ------------------------------------------------------------------------

/** What the page reads of a report saved by the Public page: its subdistrict, its depth band and the date it was saved. */
export interface DeviceReportLike { planning_area_id: string; created_at: string }

/**
 * The reports saved on this device, per subdistrict of the replay, newest first. A report names a subdistrict and no
 * point, so it is shown as a sign on the subdistrict's name; a report of another area is left out.
 */
export function deviceReportsByTambon<T extends DeviceReportLike>(reports: readonly T[], tambonIds: readonly string[]): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const report of reports) {
    if (!tambonIds.includes(report.planning_area_id)) continue;
    out.set(report.planning_area_id, [...(out.get(report.planning_area_id) ?? []), report]);
  }
  for (const list of out.values()) list.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return out;
}

// --- "No reports received" -------------------------------------------------------------------------------

/**
 * The subdistricts that carry the grey "no reports received" mark at one replay hour: residents in modelled water,
 * and neither a place record known by now nor an exercise item that has arrived. Silence is not safety, and the mark
 * says that the silence is there.
 */
export function tambonsWithoutReports(
  rows: readonly { id: string; inWater: number }[],
  withRecords: ReadonlySet<string>,
  withItems: ReadonlySet<string>,
): string[] {
  return rows.filter((row) => Math.round(row.inWater) > 0 && !withRecords.has(row.id) && !withItems.has(row.id)).map((row) => row.id);
}

// --- The model at a point --------------------------------------------------------------------------------

/** What the page needs of the terrain raster to read one cell. */
export interface PointDepthInput {
  codes: Uint8Array;
  /** `code | factor << 8` per cell, when the raster has a depth-factor channel. */
  factorKeys: Uint16Array | null;
  width: number;
  height: number;
  bounds: readonly [readonly [number, number], readonly [number, number]];
  step: number;
  channelCode?: number;
  neverCode?: number;
}

/**
 * The modelled depth (m) at a point and an assumed river stage: 0 where the model is dry, null outside the terrain
 * grid. A T1 scenario (model) value with low confidence; the current is not modelled.
 */
export function modelDepthAt(input: PointDepthInput, lat: number, lon: number, stage: number): number | null {
  const [x, y] = projectToFrame(lon, lat, input.bounds, input.width, input.height);
  const column = Math.floor(x);
  const row = Math.floor(y);
  if (column < 0 || row < 0 || column >= input.width || row >= input.height) return null;
  const cell = row * input.width + column;
  const factor = input.factorKeys ? input.factorKeys[cell] >> 8 : 255;
  return cellDepth(input.codes[cell], stage, input.step, factor, input.channelCode ?? 0, input.neverCode ?? 255) ?? 0;
}
