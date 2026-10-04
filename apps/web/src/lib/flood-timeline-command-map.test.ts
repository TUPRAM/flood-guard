/**
 * Map arithmetic of the Command exercise replay, on small shapes and on the served r4 files: the two water tones, the
 * four road styles, the state of the reported shelters, the label points of the eight subdistricts, the veil outside
 * them and the scale bar.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  buildDepthLut,
  buildFactorDepthLut,
  FACTOR_LUT_SIZE,
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type GeoCollection,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import { pointInArea } from "./flood-timeline-command";
import {
  areaBounds,
  areaLabelPoint,
  areaPolygons,
  buildTwoToneFactorLut,
  buildTwoToneLut,
  cellsInMask,
  COMMAND_WATER_RGBA,
  commandRoadStyle,
  commandScaleBar,
  metresPerPixel,
  outsideLabelPoint,
  pointsBounds,
  reportedSiteWetAt,
  veilRings,
} from "./flood-timeline-command-map";

const publicRoot = resolve(import.meta.dirname, "../../public");
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const tambons = readJson<GeoCollection<AreaGeometry, TambonProps>>(manifest.vectors.tambons.href);
const roads = readJson<GeoCollection<unknown, RoadProps>>(manifest.vectors.roads.href);

const packed = ([r, g, b, a]: readonly number[]) => ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
const SHALLOW = packed(COMMAND_WATER_RGBA.shallow);
const DEEP = packed(COMMAND_WATER_RGBA.deep);

describe("Command map: modelled water in two tones", () => {
  it("uses two tones of one blue, the deeper one darker", () => {
    const [sr, sg, sb] = COMMAND_WATER_RGBA.shallow;
    const [dr, dg, db] = COMMAND_WATER_RGBA.deep;
    // Both are blue (blue is the strongest channel, red the weakest) and the deep tone is darker in every channel.
    for (const [r, g, b] of [[sr, sg, sb], [dr, dg, db]]) {
      expect(b).toBeGreaterThan(g);
      expect(g).toBeGreaterThan(r);
    }
    expect(dr).toBeLessThan(sr);
    expect(dg).toBeLessThan(sg);
    expect(db).toBeLessThan(sb);
  });

  it("paints water under 0.3 m in the shallow tone and 0.3 m or more in the deep tone", () => {
    const step = manifest.hand.step_m;
    const lut = buildTwoToneLut(3.5, step, manifest.impassable_depth_m);
    expect(step).toBe(0.05);
    // The mapped channel is always water.
    expect(lut[0]).toBe(DEEP);
    // Code 64 is 3.2 m above drainage: 0.3 m of water at a 3.5 m stage, the first deep cell.
    expect(lut[64]).toBe(DEEP);
    expect(lut[65]).toBe(SHALLOW);
    expect(lut[69]).toBe(SHALLOW);
    // Code 70 is 3.5 m: dry at a 3.5 m stage, like every higher code and the never-wet code.
    expect(lut[70]).toBe(0);
    expect(lut[254]).toBe(0);
    expect(lut[255]).toBe(0);
    expect(new Set(lut).size).toBe(3);
  });

  it("is wet exactly where the Studio depth ramp is wet, at every replay stage", () => {
    for (const stage of [0, 0.02, 0.1, 0.64, 2.5, 3.5]) {
      const two = buildTwoToneLut(stage, manifest.hand.step_m, manifest.impassable_depth_m);
      const five = buildDepthLut(stage, manifest.hand.step_m);
      for (let code = 0; code < 256; code += 1) expect(two[code] !== 0, `stage ${stage} code ${code}`).toBe(five[code] !== 0);
    }
  });

  it("follows the depth factor of a cell for the tone, never for wetness", () => {
    const stage = 3.5;
    const lut = buildTwoToneFactorLut(stage, manifest.hand.step_m, manifest.impassable_depth_m);
    expect(lut.length).toBe(FACTOR_LUT_SIZE);
    const plain = buildTwoToneLut(stage, manifest.hand.step_m, manifest.impassable_depth_m);
    // A factor of 1 (byte 255) is the plain lookup.
    for (let code = 0; code < 256; code += 1) expect(lut[(255 << 8) | code]).toBe(plain[code]);
    // Code 60 is 3.0 m: 0.5 m of water at full depth (deep), 0.25 m at half depth (shallow), still wet at a tiny factor.
    expect(lut[(255 << 8) | 60]).toBe(DEEP);
    expect(lut[(128 << 8) | 60]).toBe(SHALLOW);
    expect(lut[(1 << 8) | 60]).toBe(SHALLOW);
    // The same cells are wet as in the Studio painter, whatever the factor.
    const studio = buildFactorDepthLut(stage, manifest.hand.step_m);
    for (let key = 0; key < FACTOR_LUT_SIZE; key += 257) expect(lut[key] !== 0).toBe(studio[key] !== 0);
  });

  it("reuses a buffer of the right size and refuses another", () => {
    const buffer = new Uint32Array(256).fill(7);
    expect(buildTwoToneLut(0, 0.05, 0.3, true, buffer)).toBe(buffer);
    expect(buffer[1]).toBe(0);
    expect(() => buildTwoToneLut(1, 0.05, 0.3, true, new Uint32Array(10))).toThrow();
    expect(() => buildTwoToneFactorLut(1, 0.05, 0.3, true, new Uint32Array(256))).toThrow();
  });
});

describe("Command map: roads and reported shelters", () => {
  it("gives a road piece one of four line styles", () => {
    expect(commandRoadStyle({ h: 3.2, k: 1, m: true }, 3.5, 0.3)).toBe("impassable");
    expect(commandRoadStyle({ h: 3.3, k: 1, m: true }, 3.5, 0.3)).toBe("wet");
    expect(commandRoadStyle({ h: 3.6, k: 1, m: true }, 3.5, 0.3)).toBe("dry");
    expect(commandRoadStyle({ h: null, m: true }, 3.5, 0.3)).toBe("dry");
    expect(commandRoadStyle({ h: 0.1, k: 1, m: false }, 3.5, 0.3)).toBe("unmodelled");
  });

  it("styles the served road pieces: some impassable at the peak, none before the flood", () => {
    const styles = (stage: number) => roads.features.map((road) => commandRoadStyle(road.properties, stage, manifest.impassable_depth_m));
    const peak = styles(3.5);
    expect(peak.filter((style) => style === "impassable").length).toBeGreaterThan(500);
    expect(peak.filter((style) => style === "wet").length).toBeGreaterThan(20);
    expect(new Set(styles(0))).toEqual(new Set(["dry"]));
  });

  it("marks a reported site wet only when its mapped point is in modelled water", () => {
    expect(reportedSiteWetAt({ model_check: null }, 3.5)).toBe(false);
    const check = { h: 2, k: 1, freeboard_m: 0, snap_m: 5, m: true, high_ground: false, floods_at_modelled_peak: true };
    expect(reportedSiteWetAt({ model_check: check }, 2)).toBe(false);
    expect(reportedSiteWetAt({ model_check: check }, 2.05)).toBe(true);
    expect(reportedSiteWetAt({ model_check: { ...check, m: false } }, 3.5)).toBe(false);
    expect(reportedSiteWetAt({ model_check: { ...check, h: null } }, 3.5)).toBe(false);
    // In the r4 data no reported site is in modelled water at the peak stage.
    expect(manifest.shelters!.reported.filter((shelter) => reportedSiteWetAt(shelter, 3.5))).toEqual([]);
  });
});

describe("Command map: bounds, label points and the veil", () => {
  const square: AreaGeometry = { type: "Polygon", coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] };

  it("finds the bounds of one or more areas", () => {
    expect(areaBounds([square])).toEqual([[0, 0], [2, 2]]);
    const other: AreaGeometry = { type: "MultiPolygon", coordinates: [[[[5, 5], [6, 5], [6, 7], [5, 5]]]] };
    expect(areaBounds([square, other])).toEqual([[0, 0], [7, 6]]);
    expect(areaBounds([])).toBeNull();
    expect(areaPolygons(other)).toHaveLength(1);
  });

  it("puts the label of a simple shape at its middle", () => {
    const [lon, lat] = areaLabelPoint(square)!;
    expect(lon).toBeCloseTo(1, 1);
    expect(lat).toBeCloseTo(1, 1);
    expect(areaLabelPoint({ type: "Polygon", coordinates: [] })).toBeNull();
  });

  it("keeps the label inside a curved shape, where a centroid falls outside", () => {
    // A "C" open to the east: the middle of its bounding box (2, 2) is not part of it.
    const c: AreaGeometry = { type: "Polygon", coordinates: [[[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [4, 3], [4, 4], [0, 4], [0, 0]]] };
    expect(pointInArea(2, 2, c)).toBe(false);
    const [lon, lat] = areaLabelPoint(c)!;
    expect(pointInArea(lon, lat, c)).toBe(true);
    // In the largest part of a MultiPolygon, and clear of a hole.
    const multi: AreaGeometry = {
      type: "MultiPolygon",
      coordinates: [[[[10, 10], [10.2, 10], [10.2, 10.2], [10, 10.2], [10, 10]]], [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1.5, 1.5], [2.5, 1.5], [2.5, 2.5], [1.5, 2.5], [1.5, 1.5]]]],
    };
    const [x, y] = areaLabelPoint(multi)!;
    expect(pointInArea(x, y, multi)).toBe(true);
    expect(x).toBeLessThan(5);
    expect(Math.abs(x - 2) > 0.5 || Math.abs(y - 2) > 0.5).toBe(true);
  });

  it("gives each of the eight subdistricts a label point inside it, well clear of its border", () => {
    expect(tambons.features).toHaveLength(8);
    for (const tambon of tambons.features) {
      const point = areaLabelPoint(tambon.geometry)!;
      expect(pointInArea(point[0], point[1], tambon.geometry), tambon.properties.en).toBe(true);
      // No label sits within about 500 m of its own border: a nudge of 0.005 degrees stays inside.
      for (const [dx, dy] of [[0.005, 0], [-0.005, 0], [0, 0.005], [0, -0.005]]) {
        expect(pointInArea(point[0] + dx, point[1] + dy, tambon.geometry), tambon.properties.en).toBe(true);
      }
    }
  });

  it("cuts the eight subdistricts out of the veil", () => {
    const rings = veilRings(tambons.features.map((tambon) => tambon.geometry));
    expect(rings).toHaveLength(9);
    const [[south, west], [north, east]] = areaBounds(tambons.features.map((tambon) => tambon.geometry))!;
    // The outer box lies well outside the district, in [lat, lon] order.
    expect(rings[0]).toEqual([[south - 3, west - 3], [south - 3, east + 3], [north + 3, east + 3], [north + 3, west - 3]]);
    // Each hole is a subdistrict's outer ring, turned to [lat, lon].
    const first = tambons.features[0].geometry.coordinates as [number, number][][];
    expect(rings[1][0]).toEqual([first[0][0][1], first[0][0][0]]);
    expect(veilRings([])).toEqual([]);
  });

  it("puts the veil's label outside every subdistrict and inside the replay area", () => {
    const geometries = tambons.features.map((tambon) => tambon.geometry);
    const point = outsideLabelPoint(geometries, manifest.bounds)!;
    expect(point).not.toBeNull();
    expect(geometries.some((geometry) => pointInArea(point[0], point[1], geometry))).toBe(false);
    const [[south, west], [north, east]] = manifest.bounds;
    expect(point[0]).toBeGreaterThan(west);
    expect(point[0]).toBeLessThan(east);
    expect(point[1]).toBeGreaterThan(south);
    expect(point[1]).toBeLessThan(north);
    // A box filled by one area has no outside.
    const square5: AreaGeometry = { type: "Polygon", coordinates: [[[-1, -1], [3, -1], [3, 3], [-1, 3], [-1, -1]]] };
    expect(outsideLabelPoint([square5], [[0, 0], [2, 2]])).toBeNull();
  });
});

describe("Command map: scale bar", () => {
  it("knows the ground size of a pixel at Mae Sai", () => {
    // Zoom 12 at 20.4° N: about 35.8 m per pixel.
    expect(metresPerPixel(20.4, 12)).toBeCloseTo(35.82, 1);
    expect(metresPerPixel(20.4, 13)).toBeCloseTo(metresPerPixel(20.4, 12) / 2, 6);
  });

  it("picks the longest round length that fits", () => {
    expect(commandScaleBar(35.82, 120)).toEqual({ metres: 2000, pixels: 2000 / 35.82 });
    expect(commandScaleBar(35.82, 60).metres).toBe(2000);
    expect(commandScaleBar(35.82, 50).metres).toBe(1000);
    expect(commandScaleBar(2.2, 120).metres).toBe(200);
    expect(commandScaleBar(0, 120)).toEqual({ metres: 50, pixels: 0 });
    for (const scale of [0.6, 4.5, 35.8, 70, 143]) expect(commandScaleBar(scale, 120).pixels).toBeLessThanOrEqual(120);
  });
});

describe("Command map: the town and the water inside the district", () => {
  it("bounds a set of points with a margin", () => {
    expect(pointsBounds([[20.43, 99.88], [20.44, 99.87], [20.435, 99.9]])).toEqual([[20.43, 99.87], [20.44, 99.9]]);
    expect(pointsBounds([[20.5, 99.5]], 0.25)).toEqual([[20.25, 99.25], [20.75, 99.75]]);
    expect(pointsBounds([])).toBeNull();
    // The town of the page: the located place records of the replay data lie within about 3 km of each other.
    const points = manifest.reported_depths!.reports.flatMap((report) => (report.point ? [[report.point.lat, report.point.lon] as [number, number]] : []));
    const [[south, west], [north, east]] = pointsBounds(points)!;
    expect(points).toHaveLength(12);
    expect(north - south).toBeLessThan(0.03);
    expect(east - west).toBeLessThan(0.03);
  });

  it("keeps the cells inside a mask, with their hatch stripes", () => {
    // A 4 x 2 grid; the mask (one byte per cell) holds the left half.
    const mask = new Uint8Array([255, 255, 0, 0, 255, 200, 127, 0]);
    const cells = new Uint32Array([0, 2, 3, 5, 6]);
    expect(cellsInMask(cells, mask)).toEqual({ cells: new Uint32Array([0, 5]), parallel: null });
    const stripes = new Uint8Array([1, 0, 1, 1, 0]);
    expect(cellsInMask(cells, mask, 1, 0, stripes)).toEqual({ cells: new Uint32Array([0, 5]), parallel: new Uint8Array([1, 1]) });
    // The alpha bytes of canvas image data: four bytes per cell, the fourth is the mask.
    const rgba = new Uint8ClampedArray(8 * 4);
    for (const cell of [0, 1, 4, 5]) rgba[cell * 4 + 3] = 255;
    expect(cellsInMask(cells, rgba, 4, 3).cells).toEqual(new Uint32Array([0, 5]));
    expect(cellsInMask(new Uint32Array(0), mask).cells).toHaveLength(0);
    expect(() => cellsInMask(cells, mask, 1, 0, new Uint8Array(2))).toThrow();
  });
});
