/**
 * Figures of the Command exercise replay (Mae Sai, September 2024), as pure functions over the replay data.
 *
 * The Command page is an exercise and after-action tool: it replays a reconstructed 2024 event hour by hour. Everything
 * here is a T1 scenario (model) with low confidence, built on the replay's own libraries (`flood-timeline`,
 * `flood-timeline-evacuation`): the district figures at a replay hour, the per-subdistrict rows of the table, what
 * changed since the hour before, the rounding of modelled figures, and the rules that order the table's rows.
 *
 * Decision D7: the replay is not a scored case. No priority score, no position in a planning list and no action class
 * is computed per replay hour, and nothing here blends or compares the hourly count with a planning result.
 * No DOM access in this module.
 */

import {
  EVENT_HOURS,
  peopleInWaterStats,
  roadImportance,
  roadState,
  roundLikePython,
  stageAt,
  type AreaGeometry,
  type ReportedDepthReport,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import {
  accessSnapshot,
  planSetId,
  REPORTED_SET_ID,
  scopeTotals,
  summarizeAccessSets,
  tambonResidents,
  type AccessNodes,
  type AccessSetSummary,
} from "./flood-timeline-evacuation";

// --- The replay clock ------------------------------------------------------------------------------------

/** Last hourly position of the replay: hour 264 is 20 Sep 00:00 ICT, the end of 19 Sep. Positions run 0 … 264. */
export const COMMAND_LAST_HOUR = EVENT_HOURS;

/** A replay hour as a whole position inside 0 … 264. */
export function clampCommandHour(hour: number): number {
  if (!Number.isFinite(hour)) return 0;
  return Math.min(COMMAND_LAST_HOUR, Math.max(0, Math.round(hour)));
}

// --- Shelter sets ----------------------------------------------------------------------------------------

/**
 * Which shelters the access figures count: the located sites reported in use in 2024, or the first sites of the ranked
 * plan up to its knee (8 in r4). The figures change with the set; no set is graded.
 */
export type CommandShelterSet = "reported" | "plan";
export const COMMAND_SHELTER_SETS: readonly CommandShelterSet[] = ["reported", "plan"];

/** The access-set id of a choice (`reported_2024`, or `plan_8` at the knee of the ranked plan). */
export function commandSetId(set: CommandShelterSet, shelters: Pick<NonNullable<TimelineManifest["shelters"]>, "knee_k">): string {
  return set === "reported" ? REPORTED_SET_ID : planSetId(shelters.knee_k);
}

// --- The model the page holds once its files have loaded -------------------------------------------------

export interface CommandTambon { id: string; th: string; en: string }

/** One road piece as the figures need it. */
export type CommandRoad = Pick<RoadProps, "c" | "h" | "k" | "m" | "len" | "t" | "n">;

export interface CommandSetModel {
  set: CommandShelterSet;
  /** Access-set id in the node file. */
  setId: string;
  summary: AccessSetSummary;
  /** Residents with a shelter of the set within reach before the flood: the base of "lost shelter access". */
  withinReachBefore: number;
}

/** Located place records (news, not surveyed) per subdistrict, by point-in-polygon. */
export interface CommandPlaceRecords {
  /** In `tambons` order. */
  byTambon: number[];
  /** Records with a point. */
  located: number;
  /** Records without a point: they stay at district level. */
  unlocated: number;
  /** Located records whose point falls in none of the subdistricts. */
  outside: number;
}

export interface CommandModel {
  /** Assumed river stage (m) at every hourly position 0 … 264. */
  stages: Float64Array;
  /** Subdistricts in the order of the access node file. */
  tambons: CommandTambon[];
  sets: Record<CommandShelterSet, CommandSetModel>;
  /** All residents at road nodes: the scope of every access figure here. */
  residents: number;
  /** The same per subdistrict, in `tambons` order. */
  tambonResidents: number[];
  population: NonNullable<TimelineManifest["population"]>;
  levels: readonly number[];
  step: number;
  impassableDepth: number;
  roads: readonly CommandRoad[];
  /** Length (km) of the shipped road pieces inside the model. */
  roadKmTotal: number;
  placeRecords: CommandPlaceRecords;
}

type Ring = readonly (readonly [number, number])[];

/** Even-odd test of a point against one ring (lon, lat pairs). */
function inRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let a = 0, b = ring.length - 1; a < ring.length; b = a, a += 1) {
    const [ax, ay] = ring[a];
    const [bx, by] = ring[b];
    if ((ay > lat) !== (by > lat) && lon < ((bx - ax) * (lat - ay)) / (by - ay) + ax) inside = !inside;
  }
  return inside;
}

/** True when the point lies inside a Polygon or MultiPolygon (inside the outer ring and outside every hole). */
export function pointInArea(lon: number, lat: number, geometry: AreaGeometry): boolean {
  const polygons = (geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates) as Ring[][];
  return polygons.some((rings) => rings.length > 0 && inRing(lon, lat, rings[0]) && !rings.slice(1).some((hole) => inRing(lon, lat, hole)));
}

/** Located place records counted per subdistrict by point-in-polygon; a point on no subdistrict counts as outside. */
export function placeRecordsByTambon(
  reports: readonly Pick<ReportedDepthReport, "point">[],
  tambons: readonly { geometry: AreaGeometry }[],
): CommandPlaceRecords {
  const byTambon = tambons.map(() => 0);
  let located = 0;
  let outside = 0;
  for (const { point } of reports) {
    if (!point) continue;
    located += 1;
    const index = tambons.findIndex((tambon) => pointInArea(point.lon, point.lat, tambon.geometry));
    if (index < 0) outside += 1;
    else byTambon[index] += 1;
  }
  return { byTambon, located, unlocated: reports.length - located, outside };
}

/**
 * Everything the figures need, built once after the replay files have loaded: the hourly stages, the access summaries
 * of the two shelter sets counted over all residents at road nodes, the road pieces and the place records per
 * subdistrict. Fails closed when the manifest lacks the access scenario, the shelters or the residents.
 */
export function buildCommandModel(input: {
  manifest: TimelineManifest;
  roads: readonly { properties: CommandRoad }[];
  tambons: readonly { properties: TambonProps; geometry: AreaGeometry }[];
  nodes: AccessNodes;
}): CommandModel {
  const { manifest, nodes } = input;
  const { access, shelters, population } = manifest;
  if (!access || !shelters || !population) throw new Error("The manifest has no access scenario, shelters or residents");
  const stages = new Float64Array(COMMAND_LAST_HOUR + 1);
  for (let hour = 0; hour <= COMMAND_LAST_HOUR; hour += 1) stages[hour] = stageAt(hour / 24, manifest.stage_anchors);
  const features = access.tambons.map((id) => {
    const feature = input.tambons.find((tambon) => tambon.properties.id === id);
    if (!feature) throw new Error(`No boundary for subdistrict ${id}`);
    return feature;
  });
  const summaries = summarizeAccessSets(nodes, access);
  const residents = scopeTotals(nodes).population;
  const setModel = (set: CommandShelterSet): CommandSetModel => {
    const setId = commandSetId(set, shelters);
    const index = access.sets.indexOf(setId);
    if (index < 0) throw new Error(`The access scenario has no set ${setId}`);
    return { set, setId, summary: summaries[index], withinReachBefore: Math.max(0, residents - summaries[index].never.population) };
  };
  const roads = input.roads.map((road) => road.properties);
  return {
    stages,
    tambons: features.map(({ properties }) => ({ id: properties.id, th: properties.th, en: properties.en })),
    sets: { reported: setModel("reported"), plan: setModel("plan") },
    residents,
    tambonResidents: Array.from(tambonResidents(nodes, access.tambons.length)),
    population,
    levels: access.levels,
    step: manifest.hand.step_m,
    impassableDepth: manifest.impassable_depth_m,
    roads,
    roadKmTotal: roads.reduce((sum, road) => sum + (road.m ? road.len : 0), 0) / 1000,
    placeRecords: placeRecordsByTambon(manifest.reported_depths?.reports ?? [], features),
  };
}

/** Assumed river stage (m) at a replay hour (illustrative curve; no gauge record was used). */
export function commandStage(model: Pick<CommandModel, "stages">, hour: number): number {
  return model.stages[clampCommandHour(hour)];
}

// --- District figures ------------------------------------------------------------------------------------

/** The three model figures of the district at one replay hour. T1 scenario (model), low confidence. */
export interface CommandFigures {
  hour: number;
  stage: number;
  set: CommandShelterSet;
  /**
   * Residents who lost shelter access: they had a shelter of the set within a 2 km walk on passable roads before the
   * flood and have lost it at this hour. Counted over all residents at road nodes; whole residents, like the baked days.
   */
  lostAccess: number;
  /** The base of that count: residents who had a shelter of the set within reach before the flood. */
  withinReachBefore: number;
  /** All residents at road nodes. */
  residents: number;
  /** Residents whose home cell is in modelled water (whole residents, like the baked days). */
  inWater: number;
  /** Road length modelled as impassable (km, two decimals like the baked days) and the shipped total it is part of. */
  roadKmImpassable: number;
  roadKmTotal: number;
}

const isImpassable = (model: Pick<CommandModel, "impassableDepth">, road: CommandRoad, stage: number): boolean =>
  road.m && roadState(road.h, stage, model.impassableDepth, road.k ?? 1) === "impassable";

function impassableMetres(model: Pick<CommandModel, "roads" | "impassableDepth">, stage: number): number {
  let metres = 0;
  for (const road of model.roads) if (isImpassable(model, road, stage)) metres += road.len;
  return metres;
}

/** District figures at replay `hour` for a shelter set (the 2024 reported set unless another is chosen). */
export function districtFiguresAt(model: CommandModel, hour: number, set: CommandShelterSet = "reported"): CommandFigures {
  const at = clampCommandHour(hour);
  const stage = model.stages[at];
  const chosen = model.sets[set];
  return {
    hour: at,
    stage,
    set,
    lostAccess: roundLikePython(accessSnapshot(chosen.summary, stage, model.levels).lost.population, 0),
    withinReachBefore: chosen.withinReachBefore,
    residents: model.residents,
    inWater: peopleInWaterStats(model.population, stage, model.step).people_in_water,
    roadKmImpassable: roundLikePython(impassableMetres(model, stage) / 1000, 2),
    roadKmTotal: model.roadKmTotal,
  };
}

// --- The rows of the subdistrict table -------------------------------------------------------------------

/** Above this share of residents with no shelter of the set in reach before the flood, a row carries the "+" mark. */
export const NO_REACH_MARK_SHARE = 0.5;

/** One subdistrict at one replay hour. T1 scenario (model), low confidence; never a score or a class. */
export interface CommandTambonRow {
  id: string;
  th: string;
  en: string;
  /** Residents who lost shelter access at this hour (unrounded; all residents at road nodes). */
  lostAccess: number;
  /** Residents in modelled water (0.1, like the baked days). */
  inWater: number;
  /** All residents at road nodes in the subdistrict. */
  residents: number;
  /** Residents with no shelter of the set within reach even before the flood: they can never count as "lost". */
  noReachBefore: number;
  /** `noReachBefore / residents` to four decimals; null when the subdistrict has no resident node. */
  noReachShare: number | null;
  /** The "+" mark: most residents had no shelter of the set in reach before the flood. */
  mostHadNoReach: boolean;
  /** Located place records (news, not surveyed) inside the subdistrict. */
  placeRecords: number;
}

/** The rows of the table at replay `hour`, in the order of the access node file (ordering is a separate step). */
export function tambonRowsAt(model: CommandModel, hour: number, set: CommandShelterSet = "reported"): CommandTambonRow[] {
  const stage = model.stages[clampCommandHour(hour)];
  const snapshot = accessSnapshot(model.sets[set].summary, stage, model.levels);
  const water = peopleInWaterStats(model.population, stage, model.step).tambon_people_in_water;
  return model.tambons.map((tambon, place) => {
    const residents = model.tambonResidents[place] ?? 0;
    const noReachBefore = snapshot.neverByTambon[place] ?? 0;
    const noReachShare = residents > 0 ? roundLikePython(noReachBefore / residents, 4) : null;
    return {
      ...tambon,
      lostAccess: snapshot.lostByTambon[place] ?? 0,
      inWater: water[tambon.id] ?? 0,
      residents,
      noReachBefore,
      noReachShare,
      mostHadNoReach: noReachShare !== null && noReachShare > NO_REACH_MARK_SHARE,
      placeRecords: model.placeRecords.byTambon[place] ?? 0,
    };
  });
}

// --- What changed since the hour before ------------------------------------------------------------------

/** A named road with pieces whose state changed between two hours. */
export interface CommandRoadChange {
  name: string;
  /** Length (km, two decimals) of its pieces that changed state at this hour. */
  km: number;
  /** Subdistricts of those pieces, longest length first. */
  tambons: string[];
  /** Road classes of those pieces, the most important first. */
  classes: string[];
  /**
   * For a newly impassable road: no piece of it was impassable the hour before (the road is cut for the first time
   * in this run of hours). For a road passable again: no piece of it is impassable any more.
   */
  whole: boolean;
}

export interface CommandRoadChanges { named: CommandRoadChange[]; unnamedKm: number }

/** Differences of the three district figures against the hour before, and the roads whose modelled state changed. */
export interface CommandChange {
  hour: number;
  /** The hour compared with; null at hour 0, where every difference is 0. */
  sinceHour: number | null;
  lostAccess: number;
  inWater: number;
  roadKmImpassable: number;
  /** Pieces impassable at this hour that were not the hour before, grouped by road name. */
  newlyImpassable: CommandRoadChanges;
  /** Pieces impassable the hour before that are not at this hour, grouped by road name. */
  passableAgain: CommandRoadChanges;
}

function groupRoadChanges(pieces: readonly CommandRoad[], wholeNames: ReadonlySet<string>): CommandRoadChanges {
  interface Draft { metres: number; tambons: Map<string, number>; classes: Set<string> }
  const drafts = new Map<string, Draft>();
  let unnamed = 0;
  for (const piece of pieces) {
    const name = piece.n?.trim();
    if (!name) {
      unnamed += piece.len;
      continue;
    }
    const draft = drafts.get(name) ?? { metres: 0, tambons: new Map(), classes: new Set() };
    draft.metres += piece.len;
    draft.tambons.set(piece.t, (draft.tambons.get(piece.t) ?? 0) + piece.len);
    draft.classes.add(piece.c);
    drafts.set(name, draft);
  }
  const named = [...drafts].map(([name, draft]): CommandRoadChange => ({
    name,
    km: roundLikePython(draft.metres / 1000, 2),
    tambons: [...draft.tambons].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([id]) => id),
    classes: [...draft.classes].sort((a, b) => roadImportance([b]) - roadImportance([a]) || a.localeCompare(b)),
    whole: wholeNames.has(name),
  }));
  // Roads cut for the first time come first, then the more important class, then the longer change.
  named.sort((a, b) => Number(b.whole) - Number(a.whole) || roadImportance(b.classes) - roadImportance(a.classes) || b.km - a.km || a.name.localeCompare(b.name));
  return { named, unnamedKm: roundLikePython(unnamed / 1000, 2) };
}

/** `roundLikePython` for a difference of either sign (never a negative zero). */
const signedRound = (value: number, digits: number): number => (value < 0 ? -roundLikePython(-value, digits) : roundLikePython(value, digits)) || 0;

/** What changed at replay `hour` against the hour before: the three differences and the roads that changed state. */
export function changeSinceHourBefore(model: CommandModel, hour: number, set: CommandShelterSet = "reported"): CommandChange {
  const at = clampCommandHour(hour);
  if (at === 0) {
    return { hour: 0, sinceHour: null, lostAccess: 0, inWater: 0, roadKmImpassable: 0, newlyImpassable: { named: [], unnamedKm: 0 }, passableAgain: { named: [], unnamedKm: 0 } };
  }
  const now = districtFiguresAt(model, at, set);
  const before = districtFiguresAt(model, at - 1, set);
  const cut: CommandRoad[] = [];
  const reopened: CommandRoad[] = [];
  const impassableNow = new Set<string>();
  const impassableBefore = new Set<string>();
  for (const road of model.roads) {
    const isNow = isImpassable(model, road, now.stage);
    const wasBefore = isImpassable(model, road, before.stage);
    const name = road.n?.trim();
    if (name && isNow) impassableNow.add(name);
    if (name && wasBefore) impassableBefore.add(name);
    if (isNow && !wasBefore) cut.push(road);
    else if (!isNow && wasBefore) reopened.push(road);
  }
  const firstCut = new Set([...impassableNow].filter((name) => !impassableBefore.has(name)));
  const fullyOpen = new Set([...impassableBefore].filter((name) => !impassableNow.has(name)));
  return {
    hour: at,
    sinceHour: at - 1,
    lostAccess: now.lostAccess - before.lostAccess,
    inWater: now.inWater - before.inWater,
    roadKmImpassable: signedRound(now.roadKmImpassable - before.roadKmImpassable, 2),
    newlyImpassable: groupRoadChanges(cut, firstCut),
    passableAgain: groupRoadChanges(reopened, fullyOpen),
  };
}

// --- Rounding of modelled figures ------------------------------------------------------------------------

/** A modelled figure as the page prints it: never to the last digit, because the model is low confidence. */
export interface RoundedFigure {
  /** "0", "<10", "~560" or "~7,100" (Western digits, a comma between thousands). */
  text: string;
  /** The rounded number behind the text (0 for "0"; the whole number itself for "<10"). */
  value: number;
  kind: "zero" | "under_ten" | "rounded";
}

const grouped = (value: number): string => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ",");

/**
 * Rounding of a modelled count of residents: plain 0 when it rounds to nobody, "<10" below ten, then a tilde with the
 * nearest 10 below 1,000 and the nearest 100 from 1,000 on (434.9 reads "~430": the figure itself is rounded, not its
 * whole number). Counted things (exercise items, device reports) are never passed through this helper: they keep
 * plain digits.
 */
export function roundModelFigure(value: number): RoundedFigure {
  const count = Math.max(0, Number.isFinite(value) ? value : 0);
  const whole = Math.round(count);
  if (whole === 0) return { text: "0", value: 0, kind: "zero" };
  if (whole < 10) return { text: "<10", value: whole, kind: "under_ten" };
  const unit = count < 1000 ? 10 : 100;
  const rounded = Math.round(count / unit) * unit;
  return { text: `~${grouped(rounded)}`, value: rounded, kind: "rounded" };
}

/** Rounding of a modelled road length in km: plain 0, "<1" below one kilometre, else a tilde and whole kilometres. */
export function roundModelKm(value: number): RoundedFigure {
  const km = Math.max(0, Number.isFinite(value) ? value : 0);
  if (km < 0.005) return { text: "0", value: 0, kind: "zero" };
  if (km < 1) return { text: "<1", value: km, kind: "under_ten" };
  const rounded = Math.round(km);
  return { text: `~${grouped(rounded)}`, value: rounded, kind: "rounded" };
}

/**
 * A difference against the hour before, rounded like the figure itself and signed: "+~120", "−<10", or "0" when the
 * figure did not move by a whole unit. `round` is the helper of the figure (`roundModelFigure` or `roundModelKm`).
 */
export function roundModelChange(delta: number, round: (value: number) => RoundedFigure = roundModelFigure): { text: string; direction: -1 | 0 | 1 } {
  const figure = round(Math.abs(Number.isFinite(delta) ? delta : 0));
  if (figure.kind === "zero") return { text: "0", direction: 0 };
  return delta > 0 ? { text: `+${figure.text}`, direction: 1 } : { text: `−${figure.text}`, direction: -1 };
}

// --- Ordering the rows -----------------------------------------------------------------------------------

/** A row overtakes the row above it only when it leads by at least this many residents who lost shelter access. */
export const ORDER_LEAD_RESIDENTS = 25;

/** What the ordering rules read from a row. */
export type OrderRow = Pick<CommandTambonRow, "id" | "lostAccess" | "inWater">;

/** The rules compare whole residents, as the table prints them: 0.3 of a modelled resident is nobody. */
const wholeLost = (row: OrderRow): number => Math.round(row.lostAccess);
const byWaterThenCode = (a: OrderRow, b: OrderRow): number => b.inWater - a.inWater || a.id.localeCompare(b.id);
/** The figure of a row as the table prints it, as a number to compare: 0 for "0", 1 for every "<10", else the rounded count. */
const printedLost = (row: OrderRow): number => {
  const figure = roundModelFigure(row.lostAccess);
  return figure.kind === "under_ten" ? 1 : figure.value;
};

/**
 * The plain order: most residents who lost shelter access first; ties, including rows that are all zero, by residents
 * in modelled water and then by subdistrict code. Returns ids.
 */
export function plainTambonOrder(rows: readonly OrderRow[]): string[] {
  return [...rows].sort((a, b) => wholeLost(b) - wholeLost(a) || byWaterThenCode(a, b)).map((row) => row.id);
}

/**
 * One step of the ordering rules from the order of the hour before:
 *   1. rows are ordered by residents who lost shelter access, highest first;
 *   2. a row overtakes the row above it only when it leads by at least `lead` residents, so two rows a few residents
 *      apart do not swap back and forth; a row whose printed figure is higher always overtakes, so a row that reads
 *      "0" never stands over a row that reads "<10", nor "~1,600" over "~1,700";
 *   3. rows with the same count (all the zero rows among them) are ordered by residents in water, then by code.
 * Without an order to start from (the first hour, or other rows than before) the plain order is returned; a `lead` of 0
 * gives the plain order at every step.
 */
export function stepTambonOrder(previous: readonly string[] | null, rows: readonly OrderRow[], lead: number = ORDER_LEAD_RESIDENTS): string[] {
  const byId = new Map(rows.map((row) => [row.id, row]));
  if (!previous || previous.length !== rows.length || !previous.every((id) => byId.has(id)) || new Set(previous).size !== previous.length) {
    return plainTambonOrder(rows);
  }
  const order = previous.map((id) => byId.get(id)!);
  const overtakes = (below: OrderRow, above: OrderRow): boolean => {
    const gap = wholeLost(below) - wholeLost(above);
    if (gap === 0) return byWaterThenCode(below, above) < 0;
    // The lead applies between two rows that print the same figure. A row gives way to any row that prints a higher
    // one (a row with nobody counted to any row with somebody): the table never shows a lower figure over a higher one.
    return gap > 0 && (gap >= lead || printedLost(below) > printedLost(above));
  };
  // Adjacent swaps until nothing moves. A swap needs the lower row to lead (or to win a tie), and both relations are
  // strict orders, so the passes end; the bound is a safeguard only.
  for (let pass = 0; pass < order.length * order.length; pass += 1) {
    let moved = false;
    for (let index = 0; index + 1 < order.length; index += 1) {
      if (!overtakes(order[index + 1], order[index])) continue;
      [order[index], order[index + 1]] = [order[index + 1], order[index]];
      moved = true;
    }
    if (!moved) break;
  }
  return order.map((row) => row.id);
}

/** Order of the table as its reducer keeps it. */
export interface TambonOrderState {
  /** The order the table shows. */
  order: string[];
  /** The order the rules give at the latest hour; it keeps advancing while the shown order is held. */
  ruled: string[];
  /** True while the shown order is frozen (the pointer or the keyboard focus is in the table, or the time thumb is dragged). */
  held: boolean;
  /** True when the frozen order differs from the ruled one: the table says "Order held". */
  pending: boolean;
}

const sameOrder = (a: readonly string[], b: readonly string[]): boolean => a.length === b.length && a.every((id, index) => id === b[index]);

/**
 * The hold rule on its own: `ruled` is the order the rules give at the new hour (for example one entry of
 * `tambonOrderByHour`). With `hold` the shown order stays as it was while the numbers update; releasing the hold shows
 * the ruled order. A hold with nothing shown yet, or over other rows than before, shows the ruled order.
 */
export function holdTambonOrder(state: Pick<TambonOrderState, "order"> | null, ruled: readonly string[], hold: boolean): TambonOrderState {
  const next = [...ruled];
  const frozen = state && hold && state.order.length === next.length && state.order.every((id) => next.includes(id)) ? state.order : null;
  if (!frozen) return { order: next, ruled: next, held: false, pending: false };
  return { order: frozen, ruled: next, held: true, pending: !sameOrder(frozen, next) };
}

/**
 * The ordering rules as one reducer: `rows` are the rows of the new hour. The ruled order advances by
 * `stepTambonOrder` from the ruled order of the state; `hold` freezes only what is shown.
 */
export function reduceTambonOrder(
  state: TambonOrderState | null,
  rows: readonly OrderRow[],
  options: { hold?: boolean; lead?: number } = {},
): TambonOrderState {
  return holdTambonOrder(state, stepTambonOrder(state?.ruled ?? null, rows, options.lead ?? ORDER_LEAD_RESIDENTS), Boolean(options.hold));
}

/**
 * The ruled order at every hourly position 0 … 264, stepping the rules hour by hour from hour 0. The page reads the
 * order of an hour from this list, so a jump on the time bar shows the same order as playing up to that hour.
 */
export function tambonOrderByHour(model: CommandModel, set: CommandShelterSet = "reported", lead: number = ORDER_LEAD_RESIDENTS): string[][] {
  const orders: string[][] = [];
  let previous: string[] | null = null;
  for (let hour = 0; hour <= COMMAND_LAST_HOUR; hour += 1) {
    previous = stepTambonOrder(previous, tambonRowsAt(model, hour, set), lead);
    orders.push(previous);
  }
  return orders;
}

/** Hours at which the order differs from the hour before. */
export function orderChangeHours(orders: readonly (readonly string[])[]): number[] {
  const hours: number[] = [];
  for (let hour = 1; hour < orders.length; hour += 1) if (!sameOrder(orders[hour], orders[hour - 1])) hours.push(hour);
  return hours;
}
