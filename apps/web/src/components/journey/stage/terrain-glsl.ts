import { ROAD_BENCH, ROAD_Z, SWALE_X } from "@/lib/journey/terrain";

/**
 * GLSL mirror of `terrainHeight` in `@/lib/journey/terrain` (keep the two in step). The water shader uses it to know
 * the depth under every water pixel, so shorelines are soft and flood water meets the ground exactly, and shallow
 * water reads differently from the deep channel. The constants come from the TypeScript module.
 */
const f = (value: number) => (Number.isInteger(value) ? `${value}.0` : String(value));

export const TERRAIN_GLSL = /* glsl */ `
float fgStep(float e0, float e1, float v) { float t = clamp((v - e0) / (e1 - e0), 0.0, 1.0); return t * t * (3.0 - 2.0 * t); }
float fgRiverZ(float x) { return 34.0 + 5.0 * sin(x / 26.0) + 2.0 * sin(x / 9.0 + 1.3); }
float fgNatural(float x, float z) {
  float river = fgRiverZ(x);
  float slope = 1.7 - 1.35 * fgStep(4.0, 15.0, z);
  float plain = 0.35 - 0.28 * fgStep(15.0, river - 7.0, z);
  float h = z < 15.0 ? slope : plain;
  h -= 2.75 * (1.0 - fgStep(2.5, 7.5, abs(z - river)));
  float across = exp(-pow((x - ${f(SWALE_X)}) / 6.5, 2.0));
  float alongNorth = fgStep(-22.0, 2.0, z);
  h -= 0.92 * across * alongNorth * (z < 15.0 ? 1.0 : 1.0 - fgStep(15.0, 22.0, z));
  h += 0.08 * sin(x * 0.13 + z * 0.07) + 0.05 * sin(x * 0.31 - z * 0.23);
  h += 6.0 * fgStep(-45.0, -95.0, z) * (0.6 + 0.4 * sin(x * 0.05));
  return h;
}
float fgTerrain(float x, float z) {
  float n = fgNatural(x, z);
  float bench = 1.0 - fgStep(${f(ROAD_BENCH.flat)}, ${f(ROAD_BENCH.blend)}, abs(z - ${f(ROAD_Z)}));
  return n + (fgNatural(x, ${f(ROAD_Z)}) - n) * bench;
}
`;
