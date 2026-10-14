/**
 * Illustrative terrain for the cinematic journey, in metres (x east, z south, y up). Pure, so the story's spatial
 * claims are unit-tested: the home and the clinic stay on dry ground in every water state, while one stretch of the
 * road between them dips through a swale that the "affected" water state covers.
 *
 * This is a fictional, explanatory landscape. It is not the Mae Sai evidence map, a forecast or measured data.
 */

export type WaterState = "dry" | "rising" | "affected";

/** Water surface elevation per state (m). The channel bed is about -2.4 m. */
export const WATER_LEVEL: Record<WaterState, number> = {
  dry: -0.7,
  rising: 0.32,
  affected: 0.78,
};

/** Road centre line runs east–west at this z. */
export const ROAD_Z = 8;
/** Centre of the swale where the road dips (x, m). */
export const SWALE_X = 2;

export const LAYOUT = {
  home: { x: -24, z: -3.6 },
  homeGate: { x: -24, z: ROAD_Z },
  resident: { x: -22.4, z: 2.9 },
  clinic: { x: 26, z: -5 },
  clinicGate: { x: 26, z: ROAD_Z },
  operations: { x: 6, z: -34 },
} as const;

/** Side streets (concrete sois) run north from the road at these x positions; a back street runs east–west. */
export const SIDE_STREETS_X: readonly number[] = [-46, -30, -14, 14, 40, 56];
export const BACK_STREET_Z = -16;

/** River centre line (z as a function of x). */
export function riverZ(x: number): number {
  return 34 + 5 * Math.sin(x / 26) + 2 * Math.sin(x / 9 + 1.3);
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const t = Math.min(1, Math.max(0, (value - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/** Half-width of the flat road bench (carriageway, kerb and footpath) and where it blends back into the land. */
export const ROAD_BENCH = { flat: 5, blend: 8 } as const;

/**
 * Ground elevation (m) at (x, z). Near the road the land is graded to the road's own centre-line level (a cut/fill
 * bench), so the road sits on the ground instead of floating over a cross-slope; at the centre line the bench equals
 * the natural ground, so road heights and the flooded stretch are unchanged by it.
 */
export function terrainHeight(x: number, z: number): number {
  const natural = naturalHeight(x, z);
  const bench = 1 - smoothstep(ROAD_BENCH.flat, ROAD_BENCH.blend, Math.abs(z - ROAD_Z));
  if (bench <= 0) return natural;
  return natural + (naturalHeight(x, ROAD_Z) - natural) * bench;
}

function naturalHeight(x: number, z: number): number {
  const river = riverZ(x);
  // North plateau → slope → floodplain → channel.
  const slope = 1.7 - 1.35 * smoothstep(4, 15, z);
  const plain = 0.35 - 0.28 * smoothstep(15, river - 7, z);
  let height = z < 15 ? slope : plain;
  // Channel: smooth trough around the river line.
  const distance = Math.abs(z - river);
  height -= 2.75 * (1 - smoothstep(2.5, 7.5, distance));
  // Swale: a shallow drainage valley crossing the road; deepest near the road, fading northward.
  const across = Math.exp(-(((x - SWALE_X) / 6.5) ** 2));
  const alongNorth = smoothstep(-22, 2, z);
  height -= 0.92 * across * alongNorth * (z < 15 ? 1 : 1 - smoothstep(15, 22, z));
  // Gentle undulation so the land does not read as a tabletop.
  height += 0.08 * Math.sin(x * 0.13 + z * 0.07) + 0.05 * Math.sin(x * 0.31 - z * 0.23);
  // The far north rises into low hills (depth for the establishing shot).
  height += 6 * smoothstep(-45, -95, z) * (0.6 + 0.4 * Math.sin(x * 0.05));
  return height;
}

/** Road surface height (m) at x along the road. */
export function roadHeight(x: number): number {
  return terrainHeight(x, ROAD_Z) + 0.06;
}

/** True when the ground at (x, z) is under water in a state. */
export function isUnderWater(x: number, z: number, state: WaterState): boolean {
  return terrainHeight(x, z) < WATER_LEVEL[state];
}

/** The x range of the usual connection between the home gate and the clinic gate. */
export const CONNECTION_X: readonly [number, number] = [LAYOUT.homeGate.x, LAYOUT.clinicGate.x];

/** Sample the road along the connection and return the sub-ranges (x) that are under water. */
export function floodedRoadRanges(state: WaterState, step = 0.25): Array<[number, number]> {
  const ranges: Array<[number, number]> = [];
  let open: number | null = null;
  for (let x = CONNECTION_X[0]; x <= CONNECTION_X[1] + 1e-9; x += step) {
    const wet = roadHeight(x) - 0.06 < WATER_LEVEL[state];
    if (wet && open === null) open = x;
    if (!wet && open !== null) {
      ranges.push([open, x - step]);
      open = null;
    }
  }
  if (open !== null) ranges.push([open, CONNECTION_X[1]]);
  return ranges;
}

/** Smooth interpolation of the water level between two states. */
export function waterLevelBetween(from: WaterState, to: WaterState, t: number): number {
  const k = smoothstep(0, 1, t);
  return WATER_LEVEL[from] + (WATER_LEVEL[to] - WATER_LEVEL[from]) * k;
}
