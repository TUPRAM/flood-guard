/**
 * Map arithmetic of the Command exercise replay (Mae Sai, September 2024): the two tones of modelled water, the label
 * point of a subdistrict, the veil outside the eight subdistricts, the scale bar and the state of a reported shelter
 * at a replay hour. Pure functions; the map component applies them to Leaflet.
 *
 * Everything drawn from these functions is a T1 scenario (model) with low confidence, or static context. No DOM access.
 */

import {
  depthFactor,
  FACTOR_LUT_SIZE,
  type AreaGeometry,
  type ReportedShelter,
  type Rgba,
  ROAD_IMPORTANCE,
  type RoadProps,
  type RoadState,
  roadState,
} from "./flood-timeline";

// --- Modelled water in two tones of one blue -------------------------------------------------------------

/**
 * The two tones (the site's primary blue at 300 and 500): modelled water under the depth at which roads count as
 * impassable, and modelled water at that depth or more. The mapped river channel is always water and takes the deep tone.
 */
export const COMMAND_WATER_RGBA: { shallow: Rgba; deep: Rgba } = {
  shallow: [141, 192, 228, 222],
  deep: [47, 134, 196, 232],
};

/**
 * A wet road: the one amber of the map. It is dark enough to read on the white casing a wet road lies on (about 4 to
 * 1), because a wet road is by definition drawn over the pale water tone.
 */
export const COMMAND_WET_ROAD = "#b86e00";

/**
 * The hatch of the 2024 season envelope on this page (hindsight mode): dark ink stripes with a white edge and no wash,
 * so the layer adds no colour of its own and the two water tones and the roads stay readable under it. The Studio
 * replay keeps its own colours for the same layer; here it is told apart by the direction of its hatch.
 */
export const COMMAND_ENVELOPE_RGBA: { dark: Rgba; light: Rgba; wash: Rgba } = {
  dark: [18, 38, 45, 132],
  light: [255, 255, 255, 160],
  wash: [0, 0, 0, 0],
};

const pack = ([r, g, b, a]: Rgba, littleEndian: boolean): number =>
  (littleEndian ? ((a << 24) | (b << 16) | (g << 8) | r) : ((r << 24) | (g << 16) | (b << 8) | a)) >>> 0;

/** Depths are compared at 1e-6 m, like the road rule, so 3.5 − 3.2 counts as 0.3 m. */
const reaches = (depth: number, threshold: number): boolean => Math.round(depth * 1e6) / 1e6 >= threshold;

/**
 * 256-entry lookup of packed RGBA per HAND code at `stage`: dry codes transparent, wet codes in the shallow tone
 * under `thresholdM` and in the deep tone from it on. For a raster without a depth-factor channel.
 */
export function buildTwoToneLut(stage: number, step: number, thresholdM: number, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (out && out.length !== 256) throw new Error("LUT buffer must have 256 entries");
  const lut = out ?? new Uint32Array(256);
  if (out) lut.fill(0);
  const shallow = pack(COMMAND_WATER_RGBA.shallow, littleEndian);
  const deep = pack(COMMAND_WATER_RGBA.deep, littleEndian);
  lut[0] = deep;
  for (let code = 1; code < 255; code += 1) {
    const hand = code * step;
    if (hand < stage) lut[code] = reaches(stage - hand, thresholdM) ? deep : shallow;
  }
  return lut;
}

/**
 * The same lookup indexed by `code | factor << 8` (the painter keys of a raster with a depth-factor channel): the
 * tone follows the reconstructed depth f × (stage − code × step); wetness still depends on the code alone.
 */
export function buildTwoToneFactorLut(stage: number, step: number, thresholdM: number, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (out && out.length !== FACTOR_LUT_SIZE) throw new Error(`LUT buffer must have ${FACTOR_LUT_SIZE} entries`);
  const lut = out ?? new Uint32Array(FACTOR_LUT_SIZE);
  if (out) lut.fill(0);
  const shallow = pack(COMMAND_WATER_RGBA.shallow, littleEndian);
  const deep = pack(COMMAND_WATER_RGBA.deep, littleEndian);
  for (let factor = 0; factor < 256; factor += 1) {
    const base = factor << 8;
    const k = depthFactor(factor);
    lut[base] = deep;
    for (let code = 1; code < 255; code += 1) {
      const hand = code * step;
      if (hand < stage) lut[base | code] = reaches(k * (stage - hand), thresholdM) ? deep : shallow;
    }
  }
  return lut;
}

// --- Roads -----------------------------------------------------------------------------------------------

/** The four line styles of a road piece: the three modelled states, and "not modelled" outside the model grid. */
export type CommandRoadStyle = RoadState | "unmodelled";

export function commandRoadStyle(road: Pick<RoadProps, "h" | "k" | "m">, stage: number, impassableDepthM: number): CommandRoadStyle {
  return road.m ? roadState(road.h, stage, impassableDepthM, road.k ?? 1) : "unmodelled";
}

/**
 * How heavy the line of a road piece is. A major piece is a through road (tertiary class or above) or a piece that
 * carries a name; the rest (residential and unclassified streets) are minor and drawn thinner, so a town of flooded
 * streets does not read as one red patch. The rank is drawing weight only: it changes no state and no figure.
 */
export type CommandRoadRank = "major" | "minor";
export function commandRoadRank(road: Pick<RoadProps, "c" | "n">): CommandRoadRank {
  return (ROAD_IMPORTANCE[road.c] ?? 1) > 1 || Boolean(road.n?.trim()) ? "major" : "minor";
}

// --- Reported shelters -----------------------------------------------------------------------------------

/**
 * Whether the mapped location of a reported site is in modelled water at `stage`. A site without a point, outside
 * the terrain model or above the modelled flood range is never wet in the model. The state is a model result; that
 * the site was in use is reported, not surveyed.
 */
export function reportedSiteWetAt(shelter: Pick<ReportedShelter, "model_check">, stage: number): boolean {
  const check = shelter.model_check;
  return Boolean(check && check.m && check.h !== null && stage > check.h);
}

// --- Geometry: bounds, label points and the veil ---------------------------------------------------------

type Position = readonly [number, number];
type Ring = readonly Position[];
/** `[[south, west], [north, east]]`, as Leaflet and the manifest write bounds. */
export type LatLngBox = [[number, number], [number, number]];

/** The polygons of an area: each one its outer ring followed by its holes (lon, lat pairs). */
export function areaPolygons(geometry: AreaGeometry): Ring[][] {
  return (geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates) as Ring[][];
}

/** Bounds of one or more areas; null when they hold no point. */
export function areaBounds(geometries: readonly AreaGeometry[]): LatLngBox | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const geometry of geometries) {
    for (const rings of areaPolygons(geometry)) {
      for (const [lon, lat] of rings[0] ?? []) {
        if (lon < west) west = lon;
        if (lon > east) east = lon;
        if (lat < south) south = lat;
        if (lat > north) north = lat;
      }
    }
  }
  return Number.isFinite(west) ? [[south, west], [north, east]] : null;
}

/** Bounds of a set of points (`[lat, lon]`), `padDeg` degrees wider on every side; null without a point. */
export function pointsBounds(points: readonly (readonly [number, number])[], padDeg = 0): LatLngBox | null {
  if (points.length === 0) return null;
  let south = Infinity;
  let west = Infinity;
  let north = -Infinity;
  let east = -Infinity;
  for (const [lat, lon] of points) {
    south = Math.min(south, lat);
    north = Math.max(north, lat);
    west = Math.min(west, lon);
    east = Math.max(east, lon);
  }
  return [[south - padDeg, west - padDeg], [north + padDeg, east + padDeg]];
}

function ringArea(ring: Ring): number {
  let twice = 0;
  for (let a = 0, b = ring.length - 1; a < ring.length; b = a, a += 1) twice += (ring[b][0] - ring[a][0]) * (ring[b][1] + ring[a][1]);
  return Math.abs(twice) / 2;
}

function inRing(x: number, y: number, ring: Ring): boolean {
  let inside = false;
  for (let a = 0, b = ring.length - 1; a < ring.length; b = a, a += 1) {
    const [ax, ay] = ring[a];
    const [bx, by] = ring[b];
    if ((ay > y) !== (by > y) && x < ((bx - ax) * (y - ay)) / (by - ay) + ax) inside = !inside;
  }
  return inside;
}

/** Squared distance from a point to a segment, with x already scaled to the same ground unit as y. */
function segmentDistance2(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  let x = ax;
  let y = ay;
  const dx = bx - ax;
  const dy = by - ay;
  if (dx !== 0 || dy !== 0) {
    const along = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
    if (along > 1) {
      x = bx;
      y = by;
    } else if (along > 0) {
      x += dx * along;
      y += dy * along;
    }
  }
  return (px - x) ** 2 + (py - y) ** 2;
}

/**
 * The label point of an area: the point of its largest polygon that lies farthest from the polygon's edge (its
 * "pole of inaccessibility"), found by a grid search refined three times. A centroid can fall outside a curved
 * subdistrict or on its border; this point never does. Longitudes are scaled by the cosine of the latitude, so the
 * distance is the same in both directions on the ground. Returns `[lon, lat]`, or null for an empty geometry.
 */
export function areaLabelPoint(geometry: AreaGeometry, grid = 24): [number, number] | null {
  const polygons = areaPolygons(geometry).filter((rings) => (rings[0]?.length ?? 0) >= 3);
  if (polygons.length === 0) return null;
  const rings = polygons.reduce((largest, candidate) => (ringArea(candidate[0]) > ringArea(largest[0]) ? candidate : largest));
  const outer = rings[0];
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const [lon, lat] of outer) {
    west = Math.min(west, lon);
    east = Math.max(east, lon);
    south = Math.min(south, lat);
    north = Math.max(north, lat);
  }
  const scale = Math.cos((((south + north) / 2) * Math.PI) / 180);
  const inside = (lon: number, lat: number): boolean => inRing(lon, lat, outer) && !rings.slice(1).some((hole) => inRing(lon, lat, hole));
  const clearance = (lon: number, lat: number): number => {
    let best = Infinity;
    for (const ring of rings) {
      for (let a = 0, b = ring.length - 1; a < ring.length; b = a, a += 1) {
        const distance = segmentDistance2(lon * scale, lat, ring[a][0] * scale, ring[a][1], ring[b][0] * scale, ring[b][1]);
        if (distance < best) best = distance;
      }
    }
    return best;
  };
  let best: [number, number] | null = null;
  let bestClearance = -1;
  let box = { west, south, east, north };
  for (let pass = 0; pass < 4; pass += 1) {
    const stepLon = (box.east - box.west) / grid;
    const stepLat = (box.north - box.south) / grid;
    for (let row = 0; row <= grid; row += 1) {
      for (let column = 0; column <= grid; column += 1) {
        const lon = box.west + column * stepLon;
        const lat = box.south + row * stepLat;
        if (!inside(lon, lat)) continue;
        const value = clearance(lon, lat);
        if (value > bestClearance) {
          bestClearance = value;
          best = [lon, lat];
        }
      }
    }
    if (!best) break;
    // Refine around the best point: two cells of the last grid on each side.
    box = { west: best[0] - 2 * stepLon, east: best[0] + 2 * stepLon, south: best[1] - 2 * stepLat, north: best[1] + 2 * stepLat };
  }
  return best ?? [outer[0][0], outer[0][1]];
}

/**
 * The veil outside the subdistricts as one polygon with holes, in Leaflet's `[lat, lon]` order: an outer box `padDeg`
 * degrees around the areas, and the outer ring of every subdistrict polygon cut out of it (drawn with the even-odd
 * rule). What it greys out is not modelled: blank ground there must not read as dry.
 */
export function veilRings(geometries: readonly AreaGeometry[], padDeg = 3): [number, number][][] {
  const bounds = areaBounds(geometries);
  if (!bounds) return [];
  const [[south, west], [north, east]] = bounds;
  const outer: [number, number][] = [
    [south - padDeg, west - padDeg], [south - padDeg, east + padDeg], [north + padDeg, east + padDeg], [north + padDeg, west - padDeg],
  ];
  const holes = geometries.flatMap((geometry) => areaPolygons(geometry)
    .filter((rings) => (rings[0]?.length ?? 0) >= 3)
    .map((rings) => rings[0].map(([lon, lat]) => [lat, lon] as [number, number])));
  return [outer, ...holes];
}

/**
 * Where the "outside the district" label sits: the point of `box` that lies outside every subdistrict and farthest
 * from all of them, found on a grid. Returns `[lon, lat]`, or null when the subdistricts fill the box.
 */
export function outsideLabelPoint(geometries: readonly AreaGeometry[], box: LatLngBox, grid = 28): [number, number] | null {
  const [[south, west], [north, east]] = box;
  const scale = Math.cos((((south + north) / 2) * Math.PI) / 180);
  const outers = geometries.flatMap((geometry) => areaPolygons(geometry).map((rings) => rings[0]).filter((ring) => (ring?.length ?? 0) >= 3));
  let best: [number, number] | null = null;
  let bestClearance = 0;
  for (let row = 1; row < grid; row += 1) {
    for (let column = 1; column < grid; column += 1) {
      const lon = west + ((east - west) * column) / grid;
      const lat = south + ((north - south) * row) / grid;
      if (outers.some((ring) => inRing(lon, lat, ring))) continue;
      let clearance = Infinity;
      for (const ring of outers) {
        for (let a = 0, b = ring.length - 1; a < ring.length; b = a, a += 1) {
          const distance = segmentDistance2(lon * scale, lat, ring[a][0] * scale, ring[a][1], ring[b][0] * scale, ring[b][1]);
          if (distance < clearance) clearance = distance;
        }
      }
      // Keep the label inside the box too: its distance to the box edge counts like a distance to a subdistrict.
      const edge = Math.min((lon - west) * scale, (east - lon) * scale, lat - south, north - lat) ** 2;
      const value = Math.min(clearance, edge);
      if (value > bestClearance) {
        bestClearance = value;
        best = [lon, lat];
      }
    }
  }
  return best;
}

// --- Scale bar -------------------------------------------------------------------------------------------

const EARTH_RADIUS_M = 6_378_137;
/** Round lengths a scale bar may show (m). */
const SCALE_LENGTHS_M = [50, 100, 200, 500, 1000, 2000, 5000, 10_000, 20_000, 50_000] as const;

/** Ground metres per screen pixel of a Web Mercator map at `latitude` and `zoom` (256 px tiles). */
export function metresPerPixel(latitude: number, zoom: number): number {
  return (2 * Math.PI * EARTH_RADIUS_M * Math.cos((latitude * Math.PI) / 180)) / (256 * 2 ** zoom);
}

/** The longest round length no wider than `maxPixels` at this map scale, with its width in pixels. */
export function commandScaleBar(metresPerPx: number, maxPixels: number): { metres: number; pixels: number } {
  if (!(metresPerPx > 0) || !(maxPixels > 0)) return { metres: SCALE_LENGTHS_M[0], pixels: 0 };
  let metres: number = SCALE_LENGTHS_M[0];
  for (const length of SCALE_LENGTHS_M) if (length / metresPerPx <= maxPixels) metres = length;
  return { metres, pixels: metres / metresPerPx };
}

// --- Clipping the water to the district ------------------------------------------------------------------

/**
 * The cells of `cells` that lie inside a mask, and the same selection of a parallel array (the hatch stripe of each
 * low-confidence cell). `mask` holds one sample per cell, `stride` bytes apart starting at `offset` (the alpha bytes
 * of canvas image data are `stride` 4, `offset` 3); a sample of 128 or more is inside.
 *
 * The page draws modelled water inside the eight subdistricts only: the figures count nothing outside them, and the
 * veil there says "not modelled".
 */
export function cellsInMask(
  cells: Uint32Array,
  mask: ArrayLike<number>,
  stride = 1,
  offset = 0,
  parallel?: Uint8Array | null,
): { cells: Uint32Array; parallel: Uint8Array | null } {
  if (parallel && parallel.length !== cells.length) throw new Error("The parallel array must have one entry per cell");
  let count = 0;
  for (let index = 0; index < cells.length; index += 1) if (mask[cells[index] * stride + offset] >= 128) count += 1;
  const kept = new Uint32Array(count);
  const keptParallel = parallel ? new Uint8Array(count) : null;
  let cursor = 0;
  for (let index = 0; index < cells.length; index += 1) {
    if (!(mask[cells[index] * stride + offset] >= 128)) continue;
    kept[cursor] = cells[index];
    if (keptParallel && parallel) keptParallel[cursor] = parallel[index];
    cursor += 1;
  }
  return { cells: kept, parallel: keptParallel };
}
