/**
 * The story's sky: how dark it is at a replay hour (local time) and the illustrative weather, and their blend across a
 * page whose hour differs from the segment after it. Pure, unit-tested.
 */

import { skyHoursAt } from "./timeline";

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ramp = (x: number, a: number, b: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/** 0 by day, 1 at night, for a replay hour (local time); dusk and dawn take about an hour and a half. */
export function nightAt(hour: number): number {
  const hd = ((hour % 24) + 24) % 24;
  const dusk = ramp(hd, 18.0, 19.4);
  const dawn = 1 - ramp(hd, 5.2, 6.6);
  return hd >= 12 ? dusk : dawn;
}

/** Illustrative weather by replay hour: rain set in on 10 September and eased after the peak (not data). */
export function weatherAt(hour: number): { rain: number; overcast: number } {
  const points: Array<[number, number, number]> = [
    [0, 0, 0.3], [30, 0, 0.35], [36, 0.55, 0.75], [40, 0.85, 0.85], [50, 0.8, 0.85], [60, 0.45, 0.75], [84, 0.25, 0.65], [100, 0.05, 0.5], [130, 0, 0.32], [200, 0, 0.3],
  ];
  for (let i = 1; i < points.length; i += 1) {
    if (hour <= points[i][0]) {
      const [h0, r0, o0] = points[i - 1], [h1, r1, o1] = points[i];
      const t = (hour - h0) / (h1 - h0);
      return { rain: lerp(r0, r1, t), overcast: lerp(o0, o1, t) };
    }
  }
  return { rain: 0, overcast: 0.3 };
}

/** The sky at story position `t`: night (0..1), rain and overcast, blended across a page's change of hour. */
export function skyAt(t: number): { night: number; rain: number; overcast: number } {
  const { from, to, weight } = skyHoursAt(t);
  const a = weatherAt(from), b = weatherAt(to);
  return { night: lerp(nightAt(from), nightAt(to), weight), rain: lerp(a.rain, b.rain, weight), overcast: lerp(a.overcast, b.overcast, weight) };
}
