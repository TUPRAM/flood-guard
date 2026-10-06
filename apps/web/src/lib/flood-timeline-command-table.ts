/**
 * The subdistrict table and the inspector of the Command exercise replay (Mae Sai, September 2024), as pure functions.
 *
 * The table shows two rankings side by side that are never merged (decision D7):
 *   - the left group is a count from the replay model at one replay hour (T1 scenario, model, low confidence). It holds
 *     no score, no priority and no class;
 *   - the right group is the planning class of the signed protocol's cases O1 and SE1, fixed in time. It is read from a
 *     planning assessment overlay and from nothing else. No overlay exists for Mae Sai yet, so every cell is empty.
 * Nothing here blends the two, compares them or derives a mark from both.
 *
 * Also here: the figures of one subdistrict for the inspector, and the index of the find-place box, which searches only
 * the names the replay data holds. No DOM access in this module.
 */

import {
  facilityWet,
  roundLikePython,
  roadState,
  type AreaGeometry,
  type FacilityProps,
  type LineGeometry,
  type ReportedDepthReport,
  type TimelineManifest,
} from "./flood-timeline";
import {
  clampCommandHour,
  COMMAND_LAST_HOUR,
  COMMAND_SHELTER_SETS,
  pointInArea,
  roundModelChange,
  roundModelFigure,
  tambonRowsAt,
  type CommandModel,
  type CommandShelterSet,
  type CommandTambonRow,
  type RoundedFigure,
} from "./flood-timeline-command";
import { placeRecordsAt, reportedSitePendingAt, type CommandMode } from "./flood-timeline-command-feed";
import type { LatLngBox } from "./flood-timeline-command-map";
import { roadNameText } from "./flood-timeline-copy";
import { accessSnapshot, reportedSiteRole } from "./flood-timeline-evacuation";
import {
  parsePlanningAssessmentOverlay,
  PLANNING_PROTOCOL_BINDING,
  type AssignedConfidenceClass,
  type EvidenceTier,
  type HeadlineStatus,
  type PlanningActionClass,
  type PlanningAssessmentOverlay,
  type PlanningLane,
  type PlanningOverlayRow,
  type PlanningReasonCode,
} from "./planning-assessment-overlay";

// --- The protocol cases of the right column group --------------------------------------------------------

/**
 * The two protocol cases the table shows: O1 (own radar candidates of 16 Sep 2024, observed lane, tier T2) and SE1
 * (the Aug-Oct 2024 season envelope, scenario lane). Each is fixed in time; neither is computed from a replay hour.
 */
export type CommandPlanningCase = "O1" | "SE1";
export const COMMAND_PLANNING_CASES: readonly CommandPlanningCase[] = ["O1", "SE1"];
/** The case the planning position is taken from unless the reader chooses the other (owner decision 3, provisional). */
export const DEFAULT_POSITION_CASE: CommandPlanningCase = "SE1";

/**
 * The list of the published overlays of the study (written by scripts/publish_planning_overlay.py). The page reads
 * it first and asks only for the cases it lists, so a case that is not published costs no failed request.
 */
export const COMMAND_OVERLAY_INDEX_HREF = "/planning-overlays/mae-sai-2024/index.json";

/** The cases an index lists, by their protocol id; nothing for a file that is not such an index. */
export function publishedOverlayCases(value: unknown): CommandPlanningCase[] {
  if (typeof value !== "object" || value === null) return [];
  const { schema, cases } = value as { schema?: unknown; cases?: unknown };
  if (schema !== "floodguard.published_planning_overlays.v1" || !Array.isArray(cases)) return [];
  const listed = new Set(cases.map((item) => (typeof item === "object" && item !== null ? (item as { case_id?: unknown }).case_id : null)));
  return COMMAND_PLANNING_CASES.filter((planningCase) => listed.has(planningCase));
}

/** Where the overlay of each case is published. A case the index does not list is not asked for: its chip stays empty. */
export const COMMAND_OVERLAY_HREFS: Readonly<Record<CommandPlanningCase, string>> = {
  O1: "/planning-overlays/mae-sai-2024/o1.json",
  SE1: "/planning-overlays/mae-sai-2024/se1.json",
};

export type CommandOverlays = Record<CommandPlanningCase, PlanningAssessmentOverlay | null>;
export const NO_COMMAND_OVERLAYS: CommandOverlays = { O1: null, SE1: null };

/** Why a file is not used for a case. */
export type CommandOverlayRefusal = "refused_by_parser" | "fixture" | "other_case" | "not_public";

/**
 * Read one overlay file for one case. The page uses it only when the strict parser accepts it, it is a portfolio case
 * (a fixture never appears on the page), it is the case asked for, and its publication level is public. Anything else
 * is refused and the table keeps its empty state.
 */
export function readCommandOverlay(value: unknown, planningCase: CommandPlanningCase): { overlay: PlanningAssessmentOverlay | null; refusal: CommandOverlayRefusal | null } {
  let overlay: PlanningAssessmentOverlay;
  try {
    overlay = parsePlanningAssessmentOverlay(value);
  } catch {
    return { overlay: null, refusal: "refused_by_parser" };
  }
  const refusal = commandOverlayRefusal(overlay, planningCase);
  return refusal ? { overlay: null, refusal } : { overlay, refusal: null };
}

/** Why the page does not use an overlay the parser accepted, or null when it does. */
export function commandOverlayRefusal(
  overlay: Pick<PlanningAssessmentOverlay, "case" | "dataset_mode" | "publication_eligibility">,
  planningCase: CommandPlanningCase,
): Exclude<CommandOverlayRefusal, "refused_by_parser"> | null {
  if (overlay.case.kind !== "portfolio_case" || overlay.dataset_mode === "fixture_demo") return "fixture";
  if (overlay.case.case_id !== planningCase) return "other_case";
  if (overlay.publication_eligibility !== "public") return "not_public";
  return null;
}

/** What one chip of the right group shows for one subdistrict and one case. */
export interface CommandPlanningCell {
  planningCase: CommandPlanningCase;
  unitId: string;
  rowId: string;
  /**
   * The binding class of the row (class rule v1); null when the protocol gives none (guardrail GR1: under 100
   * residents). A low-confidence row is E by the protocol. The would-be class of such a row is never read here: the
   * protocol shows it only in the Studio verification queue.
   */
  letter: PlanningActionClass | null;
  reasonCode: PlanningReasonCode | null;
  /** The planning score of the row, 0-100; null when a component was not computed. */
  fpps: number | null;
  tier: EvidenceTier;
  lane: PlanningLane | null;
  confidenceClass: AssignedConfidenceClass | null;
  /** Guardrail GR8: the chip is filled only when the class is headline-eligible. */
  headline: HeadlineStatus;
  filled: boolean;
  floodInput: string | null;
  scenarioId: string | null;
  /** Rows of the same unit and case with another flood input: they are not shown, and the card says so. */
  otherRows: number;
  sourceTimestamp: string;
}

/** The lane and tier a row of a case carries, and the order of its flood inputs, from the protocols in force. */
function caseSpec(planningCase: CommandPlanningCase) {
  const spec = PLANNING_PROTOCOL_BINDING.cases.find((item) => item.id === planningCase);
  if (!spec) throw new Error(`The protocol binding has no case ${planningCase}`);
  return spec;
}

/** The cell of one overlay row. */
export function planningCellOfRow(row: PlanningOverlayRow, planningCase: CommandPlanningCase, otherRows = 0): CommandPlanningCell {
  return {
    planningCase,
    unitId: row.unit_id,
    rowId: row.row_id,
    letter: row.action_class,
    reasonCode: row.action_reason_code,
    fpps: row.fpps_0_100,
    tier: row.tier,
    lane: row.lane,
    confidenceClass: row.confidence?.confidence_class ?? null,
    headline: row.headline_stability.status,
    filled: row.headline_stability.status === "headline_eligible",
    floodInput: row.flood_input,
    scenarioId: row.scenario?.id ?? null,
    otherRows,
    sourceTimestamp: row.source_timestamp,
  };
}

/**
 * The cells of one case, by unit: the rows of the overlay in the lane and tier the protocol gives that case. A unit
 * with several rows (one per flood input) shows the row of the first flood input in the protocol's own order; the
 * others are counted, never merged.
 */
export function planningCells(overlay: PlanningAssessmentOverlay | null, planningCase: CommandPlanningCase): Map<string, CommandPlanningCell> {
  const cells = new Map<string, CommandPlanningCell>();
  if (!overlay) return cells;
  const spec = caseSpec(planningCase);
  const inputOrder = (row: PlanningOverlayRow): number => {
    const index = row.flood_input === null ? -1 : spec.flood_inputs.indexOf(row.flood_input);
    return index < 0 ? spec.flood_inputs.length : index;
  };
  const byUnit = new Map<string, PlanningOverlayRow[]>();
  for (const row of overlay.rows) {
    if (row.lane !== spec.lane || row.tier !== spec.tier) continue;
    byUnit.set(row.unit_id, [...(byUnit.get(row.unit_id) ?? []), row]);
  }
  for (const [unitId, rows] of byUnit) {
    const first = rows.reduce((best, row) => (inputOrder(row) < inputOrder(best) ? row : best));
    cells.set(unitId, planningCellOfRow(first, planningCase, rows.length - 1));
  }
  return cells;
}

/**
 * The planning position of each unit inside one case: units ordered by their planning score, highest first. Units with
 * the same score share a position; a unit without a score has none. The position is derived here; it is not a field of
 * the overlay, and it never mixes two cases.
 */
export function planningPositions(cells: Iterable<CommandPlanningCell>): Map<string, number> {
  const scored = [...cells].filter((cell): cell is CommandPlanningCell & { fpps: number } => cell.fpps !== null);
  const positions = new Map<string, number>();
  for (const cell of scored) positions.set(cell.unitId, 1 + scored.filter((other) => other.fpps > cell.fpps).length);
  return positions;
}

/** What the inspector card prints beside a class: its tier, the protocol versions and the anchors (decision-log rule R2). */
export interface CommandPlanningFacts {
  caseId: string;
  protocol: { v1a: string; v1b: string };
  classRule: string;
  confidenceRule: string;
  normalisation: string;
  /** Flooded share of land at which the flood component reaches 100. */
  floodAnchor: number;
  vulnerabilityAnchors: { lower: string; lowerValue: number; upper: string; upperValue: number };
  sourceTimestamp: string;
  generatedAt: string;
  dataVersion: string;
}

export function planningFacts(overlay: PlanningAssessmentOverlay): CommandPlanningFacts {
  const { vulnerability_anchors: anchors } = overlay.scoring_frame;
  return {
    caseId: overlay.case.case_id,
    protocol: { v1a: overlay.protocol_sha256.v1a, v1b: overlay.protocol_sha256.v1b },
    classRule: overlay.class_rule_version,
    confidenceRule: overlay.confidence_rule_version,
    normalisation: overlay.normalisation_version,
    floodAnchor: overlay.scoring_frame.flood_anchor,
    vulnerabilityAnchors: { lower: anchors.lower, lowerValue: anchors.values[anchors.lower], upper: anchors.upper, upperValue: anchors.values[anchors.upper] },
    sourceTimestamp: overlay.source_timestamp,
    generatedAt: overlay.generated_at,
    dataVersion: overlay.data_version,
  };
}

// --- The rows of the table as it prints them --------------------------------------------------------------

/** What the rows are ordered by: the count of this replay hour, or the planning position of the chosen case. */
export type CommandOrderBy = "hour" | "planning";

/** One row of the table. The left half is a model count of this replay hour; the right half is fixed in time. */
export interface CommandTableRow {
  row: CommandTambonRow;
  /** Place of the row in this hour's order as the table shows it, from 1. A count order, never a score. */
  position: number;
  lost: RoundedFigure;
  water: RoundedFigure;
  /** Lost shelter access against the hour before, rounded like the figure; direction 0 when it did not move. */
  change: { text: string; direction: -1 | 0 | 1 };
  /** Lost shelter access as a share of the fixed scale of the bar, 0 … 1. */
  bar: number;
  cells: Record<CommandPlanningCase, CommandPlanningCell | null>;
  /** Position in the planning list of the chosen case; null when that case gives the unit no score. */
  planningPosition: number | null;
}

export interface CommandTableInput {
  /** The rows of this replay hour, in any order. */
  rows: readonly CommandTambonRow[];
  /** The rows of the hour before; null at the first hour. */
  before: readonly CommandTambonRow[] | null;
  /** This hour's order as the table shows it (held or ruled): ids. */
  order: readonly string[];
  /** The fixed scale of the bar, in residents. */
  scale: number;
  orderBy: CommandOrderBy;
  positionFrom: CommandPlanningCase;
  cells: Record<CommandPlanningCase, ReadonlyMap<string, CommandPlanningCell>>;
}

/**
 * The rows as the table prints them. Ordered by this hour, they follow `order`. Ordered by planning, they follow the
 * planning position of the chosen case; units that share a position, and units without one (they come last), stand in
 * the order of their subdistrict codes. So the planning order is fixed in time: it never reads this hour's count, and
 * nothing is derived from both orders (decision D7).
 */
export function commandTableRows(input: CommandTableInput): CommandTableRow[] {
  const byId = new Map(input.rows.map((row) => [row.id, row]));
  const beforeById = new Map((input.before ?? []).map((row) => [row.id, row]));
  const positions = planningPositions(input.cells[input.positionFrom].values());
  const ordered = input.order.filter((id) => byId.has(id));
  // A row the order does not name still shows, after the others.
  for (const row of input.rows) if (!ordered.includes(row.id)) ordered.push(row.id);
  const built = ordered.map((id, index): CommandTableRow => {
    const row = byId.get(id)!;
    const previous = beforeById.get(id);
    return {
      row,
      position: index + 1,
      lost: roundModelFigure(row.lostAccess),
      water: roundModelFigure(row.inWater),
      change: previous ? roundModelChange(Math.round(row.lostAccess) - Math.round(previous.lostAccess)) : { text: "0", direction: 0 },
      bar: input.scale > 0 ? Math.min(1, Math.max(0, row.lostAccess / input.scale)) : 0,
      cells: { O1: input.cells.O1.get(id) ?? null, SE1: input.cells.SE1.get(id) ?? null },
      planningPosition: positions.get(id) ?? null,
    };
  });
  if (input.orderBy === "hour") return built;
  const place = (row: CommandTableRow): number => row.planningPosition ?? Number.MAX_SAFE_INTEGER;
  return [...built].sort((a, b) => place(a) - place(b) || a.row.id.localeCompare(b.row.id));
}

/** True when the chosen case gives at least one unit a planning position: only then can the rows be ordered by it. */
export function hasPlanningPositions(cells: ReadonlyMap<string, CommandPlanningCell>): boolean {
  return planningPositions(cells.values()).size > 0;
}

// --- Holding the order -----------------------------------------------------------------------------------

/** What can hold the order of the rows: the pointer or the keyboard in the table, or the time thumb being dragged. */
export type CommandHoldSource = "pointer" | "focus" | "drag";
export interface CommandHoldState {
  pointer: boolean;
  focus: boolean;
  drag: boolean;
  /** The order shown when the first hold began; null while nothing holds the order. */
  frozen: string[] | null;
}
export const NO_COMMAND_HOLD: CommandHoldState = { pointer: false, focus: false, drag: false, frozen: null };

/**
 * A hold begins or ends. The first hold freezes the order the table shows at that moment (`order`); further holds
 * keep that order; the last hold to end releases it. The figures are never held: only the order of the rows is.
 */
export function commandHoldReducer(state: CommandHoldState, action: { source: CommandHoldSource; held: boolean; order: readonly string[] | null }): CommandHoldState {
  if (state[action.source] === action.held) return state;
  const next = { ...state, [action.source]: action.held };
  const any = next.pointer || next.focus || next.drag;
  return { ...next, frozen: any ? state.frozen ?? (action.order ? [...action.order] : null) : null };
}

/** The next round number at or above a value: 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8 or 10 times a power of ten. */
export function niceCeiling(value: number): number {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (step * power >= value) return step * power;
  return 10 * power;
}

/**
 * The fixed scale of the bar: the highest count of residents who lost shelter access that any subdistrict reaches at
 * any replay hour with either shelter set, rounded up to a round number. One scale for the whole replay and for both
 * sets, so a bar never grows because the scale shrank.
 */
export function lostAccessScale(model: Pick<CommandModel, "stages" | "sets" | "levels">): number {
  let peak = 0;
  for (const set of COMMAND_SHELTER_SETS) {
    for (let hour = 0; hour <= COMMAND_LAST_HOUR; hour += 1) {
      for (const lost of accessSnapshot(model.sets[set].summary, model.stages[hour], model.levels).lostByTambon) if (lost > peak) peak = lost;
    }
  }
  return niceCeiling(peak);
}

/** The rows of the hour before `hour`; null at the first hour. */
export function tambonRowsBefore(model: CommandModel, hour: number, set: CommandShelterSet): CommandTambonRow[] | null {
  const at = clampCommandHour(hour);
  return at === 0 ? null : tambonRowsAt(model, at - 1, set);
}

// --- One subdistrict in the inspector ---------------------------------------------------------------------

/** A key facility of a subdistrict in modelled water at the replay hour. */
export interface CommandFacilityInWater { id: string; name: string; type: string }

/** The model figures of one subdistrict at one replay hour. T1 scenario (model), low confidence. */
export interface CommandTambonDetail {
  row: CommandTambonRow;
  /** Residents with a shelter of the set within reach before the flood: the base of "lost shelter access". */
  withinReachBefore: number;
  /** Road length modelled as impassable in the subdistrict (km, two decimals), and the modelled road length it is part of. */
  roadKmImpassable: number;
  roadKmModelled: number;
  /** Named roads with impassable pieces in the subdistrict at this hour, the longest length first. */
  roadsImpassable: { name: string; km: number }[];
  /** Key facilities of the subdistrict (OpenStreetMap): how many the model covers, and those in modelled water. */
  facilities: { total: number; modelled: number; inWater: CommandFacilityInWater[] };
}

type DetailFacility = Pick<FacilityProps, "id" | "type" | "n" | "t" | "h" | "m">;

export function tambonDetailAt(
  model: CommandModel,
  facilities: readonly DetailFacility[],
  hour: number,
  set: CommandShelterSet,
  tambonId: string,
): CommandTambonDetail | null {
  const at = clampCommandHour(hour);
  const stage = model.stages[at];
  const row = tambonRowsAt(model, at, set).find((item) => item.id === tambonId);
  if (!row) return null;
  let impassable = 0;
  let modelled = 0;
  const named = new Map<string, number>();
  for (const road of model.roads) {
    if (road.t !== tambonId || !road.m) continue;
    modelled += road.len;
    if (roadState(road.h, stage, model.impassableDepth, road.k ?? 1) !== "impassable") continue;
    impassable += road.len;
    const name = road.n?.trim();
    if (name) named.set(name, (named.get(name) ?? 0) + road.len);
  }
  const here = facilities.filter((facility) => facility.t === tambonId);
  return {
    row,
    withinReachBefore: Math.max(0, row.residents - row.noReachBefore),
    roadKmImpassable: roundLikePython(impassable / 1000, 2),
    roadKmModelled: roundLikePython(modelled / 1000, 2),
    roadsImpassable: [...named].map(([name, metres]) => ({ name, km: roundLikePython(metres / 1000, 2) })).sort((a, b) => b.km - a.km || a.name.localeCompare(b.name)),
    facilities: {
      total: here.length,
      modelled: here.filter((facility) => facility.m).length,
      inWater: here.filter((facility) => facilityWet(facility, stage)).map((facility) => ({ id: facility.id, name: facility.n, type: facility.type })),
    },
  };
}

/** A place that news reported water at, with the records made at its point (reported, anecdotal, not surveyed). */
export interface CommandRecordPlace { key: string; lat: number; lon: number; reports: ReportedDepthReport[] }

/**
 * The located place records of every subdistrict, grouped by their point, by point-in-polygon. A record without a
 * point stays at district level and is in no list. Records are listed as they are in the data: none is tagged or
 * ranked, and none is a call received by FloodGuard.
 */
export function placeRecordsOfTambons(
  reports: readonly ReportedDepthReport[],
  tambons: readonly { properties: { id: string }; geometry: AreaGeometry }[],
): Map<string, CommandRecordPlace[]> {
  const out = new Map<string, CommandRecordPlace[]>(tambons.map((tambon) => [tambon.properties.id, []]));
  for (const report of reports) {
    const { point } = report;
    if (!point) continue;
    const tambon = tambons.find((item) => pointInArea(point.lon, point.lat, item.geometry));
    if (!tambon) continue;
    const places = out.get(tambon.properties.id)!;
    const key = `${point.lat},${point.lon}`;
    const place = places.find((item) => item.key === key);
    if (place) place.reports.push(report);
    else places.push({ key, lat: point.lat, lon: point.lon, reports: [report] });
  }
  return out;
}

/** The record of one subdistrict in the export pack's `tambon_replay_summary.json`: its figures at the modelled peak. */
export interface CommandPeakRecord {
  tambonId: string;
  peakStage: number;
  /** Local time of the peak keyframe, as the file writes it. */
  peakLocalTime: string;
  floodedKm2: number;
  floodedShare: number | null;
  residentsInWater: number;
  roadKmImpassable: number;
  /** Walking access at the peak, all residents at road nodes, for each shelter set. */
  access: Record<CommandShelterSet, { withinReachBefore: number; lostAccess: number; lostShare: number | null } | null>;
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const finite = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);

/**
 * Read the per-subdistrict summary of the export pack. Only the fields the inspector prints are read, and a record
 * with a missing figure is left out: the inspector then says that the peak summary is not there.
 */
export function parsePeakSummary(value: unknown): Map<string, CommandPeakRecord> {
  const out = new Map<string, CommandPeakRecord>();
  if (!isRecord(value) || !Array.isArray(value.records)) return out;
  for (const item of value.records) {
    if (!isRecord(item) || typeof item.tambon_id !== "string" || typeof item.modelled_peak_local_time !== "string") continue;
    const stage = finite(item.modelled_peak_stage_m);
    const km2 = finite(item.modelled_flooded_km2_at_peak);
    const residents = finite(item.modelled_residents_in_water_at_peak);
    const roadKm = finite(item.modelled_road_km_impassable_at_peak);
    if (stage === null || km2 === null || residents === null || roadKm === null) continue;
    const access = isRecord(item.modelled_access_at_peak) ? item.modelled_access_at_peak : {};
    const counted = (key: string): CommandPeakRecord["access"][CommandShelterSet] => {
      const set = access[key];
      const all = isRecord(set) ? set.all_residents_at_road_nodes : null;
      if (!isRecord(all)) return null;
      const within = finite(all.within_reach_before_flood);
      const lost = finite(all.lost_access);
      return within === null || lost === null ? null : { withinReachBefore: within, lostAccess: lost, lostShare: finite(all.lost_share_of_within_reach) };
    };
    out.set(item.tambon_id, {
      tambonId: item.tambon_id,
      peakStage: stage,
      peakLocalTime: item.modelled_peak_local_time,
      floodedKm2: km2,
      floodedShare: finite(item.modelled_flooded_share_of_subdistrict),
      residentsInWater: residents,
      roadKmImpassable: roadKm,
      access: { reported: counted("reported_2024"), plan: counted("knee_plan") },
    });
  }
  return out;
}

// --- Find a place -----------------------------------------------------------------------------------------

/**
 * The find-place box searches the names the replay data holds and nothing else: the eight subdistricts, the shelters
 * reported in use in 2024 and the command centre, the places of the place records, the named key facilities and the
 * named roads. The data holds no village or soi gazetteer.
 */
export type CommandFindKind = "tambon" | "shelter" | "command_centre" | "place_record" | "facility" | "road";
export const COMMAND_FIND_KINDS: readonly CommandFindKind[] = ["tambon", "shelter", "command_centre", "place_record", "facility", "road"];

/** Where a found name is on the map. */
export type CommandFindTarget =
  | { type: "tambon"; id: string }
  | { type: "point"; lat: number; lon: number; toleranceM: number | null; siteId: string | null }
  | { type: "road"; name: string; box: LatLngBox };

export interface CommandFindEntry {
  id: string;
  kind: CommandFindKind;
  /** The Thai name; null when the data holds none. */
  th: string | null;
  /** The romanised or English name; null when the data holds none. */
  en: string | null;
  /** The type of a key facility (OpenStreetMap). */
  facilityType: string | null;
  /** Place records made at this place. */
  records: number;
  /** Null when the data holds no location for the name: it is listed, and cannot be shown on the map. */
  target: CommandFindTarget | null;
}

const THAI_LETTERS = /[฀-๿]/u;

/** A name as the search compares it: lower case, without spaces, punctuation or zero-width marks. */
export function normaliseFindText(text: string): string {
  return text.normalize("NFKC").toLowerCase().replace(/[\s​-‍.,()'"\/·:;-]+/gu, "");
}

function lineBox(geometries: readonly LineGeometry[]): LatLngBox | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const geometry of geometries) {
    for (const [lon, lat] of geometry.coordinates) {
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return Number.isFinite(west) ? [[south, west], [north, east]] : null;
}

/**
 * The reported sites and the place records the find-place box may list at a replay hour. In hindsight mode: all of
 * them. In trainee mode: the sites reported by the replay day and the place records published by the replay hour, so
 * the box names nothing that lies after the hour (a place record of a later article, or a shelter before its first
 * report). Subdistricts, key facilities and roads are places of the base map and are always listed.
 */
export function commandFindManifestAt(manifest: Pick<TimelineManifest, "shelters" | "reported_depths">, hour: number, mode: CommandMode): Pick<TimelineManifest, "shelters" | "reported_depths"> {
  if (mode === "hindsight") return manifest;
  return {
    shelters: manifest.shelters ? { ...manifest.shelters, reported: manifest.shelters.reported.filter((site) => !reportedSitePendingAt(site, hour, mode)) } : manifest.shelters,
    reported_depths: manifest.reported_depths ? { ...manifest.reported_depths, reports: placeRecordsAt(manifest.reported_depths.reports, hour, mode) } : manifest.reported_depths,
  };
}

/** The names the find-place box searches: subdistricts, reported sites, the places of the place records, named facilities and named roads. */
export function buildCommandFindIndex(input: {
  manifest: Pick<TimelineManifest, "shelters" | "reported_depths">;
  tambons: readonly { properties: { id: string; th: string; en: string } }[];
  facilities: readonly { properties: Pick<FacilityProps, "id" | "type" | "n">; geometry: { coordinates: readonly number[] } }[];
  roads: readonly { properties: { n?: string }; geometry: LineGeometry }[];
}): CommandFindEntry[] {
  const entries: CommandFindEntry[] = [];
  for (const { properties } of input.tambons) {
    entries.push({ id: `tambon:${properties.id}`, kind: "tambon", th: properties.th, en: properties.en, facilityType: null, records: 0, target: { type: "tambon", id: properties.id } });
  }
  for (const site of input.manifest.shelters?.reported ?? []) {
    const located = site.lat !== null && site.lon !== null;
    entries.push({
      id: `site:${site.id}`,
      kind: reportedSiteRole(site).role === "relief_command" ? "command_centre" : "shelter",
      th: site.name_th,
      en: site.name_en,
      facilityType: null,
      records: 0,
      target: located ? { type: "point", lat: site.lat!, lon: site.lon!, toleranceM: null, siteId: site.id } : null,
    });
  }
  // One entry per place name at one point (two records at one point can name it differently), and one per name without a point.
  const places = new Map<string, CommandFindEntry>();
  for (const report of input.manifest.reported_depths?.reports ?? []) {
    const key = `${report.point ? `${report.point.lat},${report.point.lon}` : "none"}|${report.place.en}`;
    const known = places.get(key);
    if (known) {
      known.records += 1;
      if (known.target?.type === "point" && report.location_tolerance_m !== null) known.target.toleranceM = Math.max(known.target.toleranceM ?? 0, report.location_tolerance_m);
      continue;
    }
    places.set(key, {
      id: `place:${report.id}`,
      kind: "place_record",
      th: report.place.th,
      en: report.place.en,
      facilityType: null,
      records: 1,
      target: report.point ? { type: "point", lat: report.point.lat, lon: report.point.lon, toleranceM: report.location_tolerance_m, siteId: null } : null,
    });
  }
  entries.push(...places.values());
  for (const { properties, geometry } of input.facilities) {
    const name = properties.n?.trim();
    if (!name) continue;
    const thai = THAI_LETTERS.test(name);
    const [lon, lat] = geometry.coordinates;
    entries.push({
      id: `facility:${properties.id}`,
      kind: "facility",
      th: thai ? name : null,
      en: thai ? null : name,
      facilityType: properties.type,
      records: 0,
      target: Number.isFinite(lat) && Number.isFinite(lon) ? { type: "point", lat, lon, toleranceM: null, siteId: null } : null,
    });
  }
  const roads = new Map<string, LineGeometry[]>();
  for (const { properties, geometry } of input.roads) {
    const name = properties.n?.trim();
    if (name) roads.set(name, [...(roads.get(name) ?? []), geometry]);
  }
  for (const [name, geometries] of roads) {
    const thai = THAI_LETTERS.test(name);
    const english = roadNameText(name, "en");
    const box = lineBox(geometries);
    entries.push({
      id: `road:${name}`,
      kind: "road",
      th: thai ? name : null,
      en: thai ? (english.secondary ? english.primary : null) : name,
      facilityType: null,
      records: 0,
      target: box ? { type: "road", name, box } : null,
    });
  }
  return entries;
}

/**
 * The names that hold `query`, in either language: names the map can show before names without a point in the data,
 * then names that start with the query, then subdistricts before shelters, places, facilities and roads, then the
 * shorter name. An empty query finds nothing.
 */
export function searchCommandPlaces(index: readonly CommandFindEntry[], query: string, limit = 8): CommandFindEntry[] {
  const needle = normaliseFindText(query);
  if (!needle) return [];
  const scored: { entry: CommandFindEntry; located: number; starts: number; kind: number; length: number; order: number }[] = [];
  index.forEach((entry, order) => {
    const names = [entry.th, entry.en].filter((name): name is string => name !== null).map(normaliseFindText);
    if (!names.some((name) => name.includes(needle))) return;
    scored.push({
      entry,
      located: entry.target ? 0 : 1,
      starts: names.some((name) => name.startsWith(needle)) ? 0 : 1,
      kind: COMMAND_FIND_KINDS.indexOf(entry.kind),
      length: Math.min(...names.filter((name) => name.includes(needle)).map((name) => name.length)),
      order,
    });
  });
  scored.sort((a, b) => a.located - b.located || a.starts - b.starts || a.kind - b.kind || a.length - b.length || a.order - b.order);
  return scored.slice(0, Math.max(0, limit)).map((item) => item.entry);
}
