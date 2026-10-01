/**
 * Which water view the Mae Sai replay draws, and how. The map, its legend and the PNG and video exports all take their
 * view from here, so they paint the same pixels, hatch the same low-confidence cells and name the same view.
 */

import {
  buildArrivalLut,
  buildDepthLut,
  buildDurationLut,
  buildFactorDepthLut,
  buildPeopleLut,
  buildResidentsLut,
  FACTOR_LUT_SIZE,
  paintDepth,
  paintLowConfidence,
  type HourClass,
  type Language,
  type Localized,
} from "./flood-timeline";
import type { WaterMode } from "./flood-timeline-link";

/** HAND codes, optional depth-factor keys, the cells that can ever be wet, and the low-confidence cells with their hatch. */
export interface WaterGrid {
  codes: Uint8Array;
  factorKeys: Uint16Array | null;
  candidates: Uint32Array;
  lowCells?: Uint32Array | null;
  lowStripes?: Uint8Array | null;
}
/** Residents on the water grid: density codes, people painter keys, inhabited cells and a colour per density code. */
export interface ResidentsGrid { density: Uint8Array; keys: Uint16Array; inhabited: Uint32Array; colours: Uint32Array }
/** Per HAND code: first flooded hour and hours under water, with the first-flooded colour classes. */
export interface WaterTimings { arrivalHour: Int16Array; hoursUnder: Uint16Array; arrival: readonly HourClass[] }
/** The replay moment a frame is painted for: the assumed stage (m) and the whole replay hour. */
export interface WaterMoment { stage: number; hour: number }

const needsResidents = (mode: WaterMode) => mode === "people" || mode === "residents";

/**
 * The view that is actually drawn for the view the reader chose. The two resident views need the residents raster;
 * until it has loaded (or when it cannot load) the map draws water depth, and the legend must say the same.
 */
export function drawnWaterMode(requested: WaterMode, residentsReady: boolean): WaterMode {
  return needsResidents(requested) && !residentsReady ? "depth" : requested;
}

/**
 * Whether wet low-confidence cells are washed out and hatched in a drawn view: in every view that draws water.
 * "All residents" draws where people live, not water, so it has nothing to hatch.
 */
export function hatchesLowConfidence(drawn: WaterMode): boolean {
  return drawn !== "residents";
}

/** Water views the PNG and video exports can draw. */
export type ExportWaterMode = "depth" | "arrival" | "duration";

/**
 * The view an export draws for the view on the page: first flooded and hours under water as on the map, depth for
 * every other view (the exports carry no residents raster).
 */
export function exportWaterMode(requested: WaterMode): ExportWaterMode {
  return requested === "arrival" || requested === "duration" ? requested : "depth";
}

/** What the reader should be told while a resident view is chosen but water depth is drawn; null when nothing is pending. */
export type ResidentsPending = "loading" | "error" | null;

/** One paint of the water canvas: the key array, the cells to paint, the lookup table and the cells to hatch. */
export interface WaterPaintPlan {
  /** The view drawn (see `drawnWaterMode`). */
  mode: WaterMode;
  keys: Uint8Array | Uint16Array;
  cells: Uint32Array;
  /** Entries in the lookup table `buildLut` fills. */
  lutSize: number;
  buildLut: (out: Uint32Array) => Uint32Array;
  /** Low-confidence cells to wash out and hatch after the paint; null when the view has none. */
  low: { cells: Uint32Array; stripes: Uint8Array } | null;
}

/**
 * Plan the paint of `requested` at `moment`. The hatch follows the view that is drawn, never the one that was asked
 * for, so a resident view that falls back to depth is hatched like depth.
 */
export function waterPaintPlan(
  requested: WaterMode,
  moment: WaterMoment,
  grid: WaterGrid,
  residents: ResidentsGrid | null,
  timings: WaterTimings,
  stepM: number,
  littleEndian = true,
): WaterPaintPlan {
  const mode = drawnWaterMode(requested, residents !== null);
  const low = hatchesLowConfidence(mode) && grid.lowCells && grid.lowStripes ? { cells: grid.lowCells, stripes: grid.lowStripes } : null;
  if (mode === "people" && residents) {
    return {
      mode, keys: residents.keys, cells: grid.candidates, lutSize: FACTOR_LUT_SIZE, low,
      buildLut: (out) => buildPeopleLut(moment.stage, stepM, residents.colours, littleEndian, out),
    };
  }
  if (mode === "residents" && residents) {
    return { mode, keys: residents.density, cells: residents.inhabited, lutSize: 256, low, buildLut: (out) => buildResidentsLut(residents.colours, out) };
  }
  if (mode === "arrival") {
    return {
      mode, keys: grid.codes, cells: grid.candidates, lutSize: 256, low,
      buildLut: (out) => buildArrivalLut(timings.arrivalHour, timings.arrival, moment.hour, littleEndian, out),
    };
  }
  if (mode === "duration") {
    return { mode, keys: grid.codes, cells: grid.candidates, lutSize: 256, low, buildLut: (out) => buildDurationLut(timings.hoursUnder, littleEndian, out) };
  }
  if (grid.factorKeys) {
    return {
      mode, keys: grid.factorKeys, cells: grid.candidates, lutSize: FACTOR_LUT_SIZE, low,
      buildLut: (out) => buildFactorDepthLut(moment.stage, stepM, littleEndian, out),
    };
  }
  return { mode, keys: grid.codes, cells: grid.candidates, lutSize: 256, low, buildLut: (out) => buildDepthLut(moment.stage, stepM, littleEndian, out) };
}

/** Paint a plan with its built lookup table: the view's own colours, then the low-confidence wash and hatch. */
export function paintWaterPlan(plan: WaterPaintPlan, lut: Uint32Array, pixels: Uint32Array, littleEndian = true): void {
  paintDepth(plan.keys, plan.cells, lut, pixels);
  if (plan.low) paintLowConfidence(plan.low.cells, plan.low.stripes, pixels, littleEndian);
}

/** Legend wording shared by the on-map legend and the legend drawn into the exports. */
export const WATER_LEGEND_COPY = {
  depthTitle: { en: "Water depth (model)", th: "ความลึกของน้ำ (แบบจำลอง)" },
  arrivalTitle: { en: "First flooded (model, local time)", th: "เวลาที่เริ่มท่วม (แบบจำลอง เวลาท้องถิ่น)" },
  arrivalPending: { en: "Not yet flooded at this moment (faded)", th: "ยังไม่ท่วม ณ ช่วงเวลานี้ (จาง)" },
  durationTitle: { en: "Hours under water, 9–19 Sep (model)", th: "จำนวนชั่วโมงที่จมน้ำ 9–19 ก.ย. (แบบจำลอง)" },
  lowConfidence: {
    en: "Low-confidence water: flat or filled low ground in the elevation model",
    th: "น้ำที่มีความเชื่อมั่นต่ำ: พื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง",
  },
  residentsLoading: {
    en: "The residents layer is still loading, so the map shows water depth until it is ready.",
    th: "ชั้นข้อมูลผู้อยู่อาศัยยังโหลดไม่เสร็จ แผนที่จึงแสดงความลึกของน้ำไปก่อนจนกว่าจะพร้อม",
  },
  residentsError: {
    en: "The residents layer could not be loaded, so the map shows water depth instead.",
    th: "โหลดชั้นข้อมูลผู้อยู่อาศัยไม่สำเร็จ แผนที่จึงแสดงความลึกของน้ำแทน",
  },
} as const satisfies Record<string, Localized>;

/** The sentence under the legend while a resident view is chosen but water depth is drawn. */
export function residentsPendingText(pending: Exclude<ResidentsPending, null>, language: Language): string {
  return (pending === "error" ? WATER_LEGEND_COPY.residentsError : WATER_LEGEND_COPY.residentsLoading)[language];
}
