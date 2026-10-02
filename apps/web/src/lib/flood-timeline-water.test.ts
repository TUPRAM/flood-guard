import { describe, expect, it } from "vitest";

import {
  ARRIVAL_PENDING_ALPHA,
  ARRIVAL_RAMP,
  arrivalClasses,
  CHANNEL_RGBA,
  DENSITY_CLASSES,
  DEPTH_CLASSES,
  DURATION_CLASSES,
  hatchStripes,
  lowConfidenceRgba,
  type Rgba,
} from "./flood-timeline";
import type { WaterMode } from "./flood-timeline-link";
import {
  drawnWaterMode,
  exportWaterMode,
  hatchesLowConfidence,
  lowConfidenceKey,
  paintWaterPlan,
  residentsPendingText,
  WATER_LEGEND_COPY,
  waterPaintPlan,
  type ResidentsGrid,
  type WaterGrid,
  type WaterTimings,
} from "./flood-timeline-water";

const ALL_MODES: WaterMode[] = ["depth", "arrival", "duration", "people", "residents"];
const THAI = /[฀-๿]/;
const unpack = (value: number): Rgba => [value & 255, (value >>> 8) & 255, (value >>> 16) & 255, value >>> 24];

// A 6 x 2 grid. HAND codes: 0 is the channel, 255 never floods, the rest are 5 cm steps above the channel.
// Row 0 is ordinary ground, row 1 is the same ground flagged low-confidence (cell 8 lies on a hatch stripe).
const WIDTH = 6;
const codes = new Uint8Array([0, 10, 10, 20, 40, 255, 10, 10, 10, 20, 40, 255]);
const candidates = new Uint32Array([0, 1, 2, 3, 4, 6, 7, 8, 9, 10]);
const lowCells = new Uint32Array([6, 7, 8, 9, 10]);
const lowStripes = hatchStripes(lowCells, WIDTH, 3, 1);
const grid: WaterGrid = { codes, factorKeys: null, candidates, lowCells, lowStripes };
// Code 10 floods at hour 5 for 30 hours, code 20 at hour 40 for 8 hours, code 40 never.
const arrivalHour = new Int16Array(256).fill(-1);
const hoursUnder = new Uint16Array(256);
arrivalHour[10] = 5;
hoursUnder[10] = 30;
arrivalHour[20] = 40;
hoursUnder[20] = 8;
const timings: WaterTimings = { arrivalHour, hoursUnder, arrival: arrivalClasses(arrivalHour, ARRIVAL_RAMP, 0) };
const residents: ResidentsGrid = {
  density: new Uint8Array(codes.length).fill(3),
  keys: new Uint16Array(codes.length),
  inhabited: new Uint32Array([1, 2, 7, 8]),
  colours: new Uint32Array(256).fill(0xff336699),
};

function paint(mode: WaterMode, moment = { stage: 1.2, hour: 20 }, people: ResidentsGrid | null = null, on: WaterGrid = grid) {
  const plan = waterPaintPlan(mode, moment, on, people, timings, 0.05, true);
  const pixels = new Uint32Array(codes.length);
  paintWaterPlan(plan, plan.buildLut(new Uint32Array(plan.lutSize)), pixels, true);
  return { plan, pixels };
}

describe("water view shared by the map, its legend and the exports", () => {
  it("draws water depth for a resident view until the residents raster is ready, and every other view as chosen", () => {
    for (const mode of ALL_MODES) expect(drawnWaterMode(mode, true)).toBe(mode);
    expect(drawnWaterMode("people", false)).toBe("depth");
    expect(drawnWaterMode("residents", false)).toBe("depth");
    for (const mode of ["depth", "arrival", "duration"] as const) expect(drawnWaterMode(mode, false)).toBe(mode);
    // The paint plan and the legend take the drawn view from the same function, so they cannot disagree.
    for (const mode of ALL_MODES) {
      expect(waterPaintPlan(mode, { stage: 1, hour: 10 }, grid, null, timings, 0.05).mode).toBe(drawnWaterMode(mode, false));
      expect(waterPaintPlan(mode, { stage: 1, hour: 10 }, grid, residents, timings, 0.05).mode).toBe(drawnWaterMode(mode, true));
    }
  });

  it("hatches low-confidence water in every view that draws water, first flooded and hours under water included", () => {
    expect(ALL_MODES.filter(hatchesLowConfidence)).toEqual(["depth", "arrival", "duration", "people"]);
    for (const mode of ["depth", "arrival", "duration"] as const) expect(paint(mode).plan.low).toEqual({ cells: lowCells, stripes: lowStripes });
    expect(paint("people", undefined, residents).plan.low).not.toBeNull();
    // "All residents" draws where people live, not water: nothing to hatch, and it paints the inhabited cells.
    const all = paint("residents", undefined, residents).plan;
    expect(all.low).toBeNull();
    expect(all.cells).toBe(residents.inhabited);
    // A resident view that falls back to depth is hatched like depth.
    expect(paint("people").plan.low).not.toBeNull();
    expect(paint("residents").plan.low).not.toBeNull();
    // No hatch without the low-confidence cells (the manifest declares no channel).
    expect(paint("arrival", undefined, null, { codes, factorKeys: null, candidates }).plan.low).toBeNull();
  });

  it("paints first-flooded cells washed out and hatched where the ground is low-confidence", () => {
    const { pixels } = paint("arrival");
    const reached = unpack(pixels[1]);
    const pending = unpack(pixels[3]);
    // Ordinary ground keeps the class colours: reached at hour 5, still to flood at hour 40 (faded).
    expect(reached).toEqual(timings.arrival.find((item) => 5 >= item.from && 5 <= item.to)!.rgba);
    expect(pending[3]).toBe(ARRIVAL_PENDING_ALPHA);
    expect(unpack(pixels[0])).toEqual(CHANNEL_RGBA);
    expect(pixels[4]).toBe(0);
    // Low-confidence ground, same codes: cell 8 lies on a stripe, cells 6, 7 and 9 between stripes.
    expect([...lowStripes]).toEqual([0, 0, 1, 0, 0]);
    expect(unpack(pixels[7])).toEqual(lowConfidenceRgba(reached, false));
    expect(unpack(pixels[8])).toEqual(lowConfidenceRgba(reached, true));
    expect(unpack(pixels[9])).toEqual(lowConfidenceRgba(pending, false));
    // The stripe, the wash between stripes and ordinary water are three different colours.
    expect(new Set([pixels[1], pixels[7], pixels[8]]).size).toBe(3);
    // A low-confidence cell that never floods stays transparent: the hatch never adds water.
    expect(pixels[10]).toBe(0);
  });

  it("paints hours-under-water cells washed out and hatched where the ground is low-confidence", () => {
    const { pixels } = paint("duration");
    const long = DURATION_CLASSES.find((item) => 30 >= item.min && 30 <= item.max)!.rgba;
    const short = DURATION_CLASSES.find((item) => 8 >= item.min && 8 <= item.max)!.rgba;
    expect(unpack(pixels[1])).toEqual(long);
    expect(unpack(pixels[3])).toEqual(short);
    expect(unpack(pixels[7])).toEqual(lowConfidenceRgba(long, false));
    expect(unpack(pixels[8])).toEqual(lowConfidenceRgba(long, true));
    expect(unpack(pixels[9])).toEqual(lowConfidenceRgba(short, false));
    expect(new Set([pixels[1], pixels[7], pixels[8]]).size).toBe(3);
    expect(pixels[10]).toBe(0);
    // The same cells are hatched in the depth view of the same grid (every one of them is wet at a 5 m stage).
    const depth = paint("depth", { stage: 5, hour: 20 }).pixels;
    for (const cell of [7, 8, 9, 10]) expect(depth[cell], `cell ${cell}`).not.toBe(depth[cell - WIDTH]);
  });

  it("exports first flooded and hours under water as on the map, and water depth for the resident views", () => {
    expect(ALL_MODES.map(exportWaterMode)).toEqual(["depth", "arrival", "duration", "depth", "depth"]);
    // An export has no residents raster; its plan for the exported view is hatched like the map's.
    for (const mode of ALL_MODES) {
      const plan = waterPaintPlan(exportWaterMode(mode), { stage: 1, hour: 10 }, grid, null, timings, 0.05);
      expect(plan.mode).toBe(exportWaterMode(mode));
      expect(plan.low).not.toBeNull();
    }
  });

  it("words the legend the same on the map and in the exports, in English and Thai", () => {
    for (const [key, entry] of Object.entries(WATER_LEGEND_COPY)) {
      expect(entry.en.length, key).toBeGreaterThan(10);
      expect(entry.th, key).toMatch(THAI);
    }
    expect(WATER_LEGEND_COPY.lowConfidence.en).toBe("Low-confidence water: flat or filled low ground in the elevation model");
    expect(residentsPendingText("loading", "en")).toBe("The residents layer is still loading, so the map shows water depth until it is ready.");
    expect(residentsPendingText("error", "en")).toBe("The residents layer could not be loaded, so the map shows water depth instead.");
    expect(residentsPendingText("loading", "th")).toMatch(THAI);
    expect(residentsPendingText("error", "th")).not.toBe(residentsPendingText("loading", "th"));
  });
});

describe("low-confidence legend key", () => {
  it("takes its stripe and wash from the function that colours the map, per drawn view", () => {
    const classes = [{ rgba: ARRIVAL_RAMP[0] }, { rgba: ARRIVAL_RAMP[3] }];
    const expected: Record<WaterMode, Rgba> = {
      depth: DEPTH_CLASSES[1].rgba,
      arrival: ARRIVAL_RAMP[0],
      duration: DURATION_CLASSES[DURATION_CLASSES.length - 1].rgba,
      people: DENSITY_CLASSES[Math.floor(DENSITY_CLASSES.length / 2)].rgba,
      residents: DENSITY_CLASSES[Math.floor(DENSITY_CLASSES.length / 2)].rgba,
    };
    for (const mode of ALL_MODES) {
      const key = lowConfidenceKey(mode, classes);
      expect(key.stripe, mode).toEqual(lowConfidenceRgba(expected[mode], true));
      expect(key.wash, mode).toEqual(lowConfidenceRgba(expected[mode], false));
      // The stripe keeps more of the view's colour and more opacity than the wash, as on the map.
      expect(key.stripe[3], mode).toBeGreaterThan(key.wash[3]);
    }
    // First flooded uses the earliest class the map has (the ramp's first colour when no classes are given).
    expect(lowConfidenceKey("arrival")).toEqual(lowConfidenceKey("arrival", classes));
    expect(lowConfidenceKey("arrival", [{ rgba: ARRIVAL_RAMP[2] }]).stripe).toEqual(lowConfidenceRgba(ARRIVAL_RAMP[2], true));
  });

  it("is blue in the depth view and purple in the first-flooded and hours-under-water views", () => {
    const blueOverRed = (rgba: Rgba) => rgba[2] - rgba[0];
    const greenOverRed = (rgba: Rgba) => rgba[1] - rgba[0];
    const depth = lowConfidenceKey("depth").stripe;
    expect(blueOverRed(depth)).toBeGreaterThan(40);
    expect(greenOverRed(depth)).toBeGreaterThan(20);
    for (const mode of ["arrival", "duration"] as const) {
      const stripe = lowConfidenceKey(mode).stripe;
      // Purple: blue well above red, and green below both.
      expect(blueOverRed(stripe), mode).toBeGreaterThan(10);
      expect(greenOverRed(stripe), mode).toBeLessThan(0);
      expect(stripe, mode).not.toEqual(depth);
    }
  });
});
