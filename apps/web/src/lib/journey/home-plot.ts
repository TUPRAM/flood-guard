/**
 * Lalita's plot: where the story's house kit stands on the real outline of the Public app's dry example home, and how
 * it faces its street. Pure (no Three.js), so the layout is unit-tested against the committed bake.
 *
 * The outline in the bake is a long building (about 20 m) between a narrow lane and a large neighbour, with its end on
 * the street the replay's walk starts from. The kit is a recognisable two-storey house set back from that street behind
 * a small front yard and a garden wall, sized so that its roof, the wall and the one-storey back wing on the rest of the
 * outline clear every other outline. The kit is illustrative; the plot is the real one.
 *
 * Frame: as the bake (x east, z south). A rotation r turns the house's local frame (x along the front, z toward the
 * street) into the world: F = (sin r, cos r) toward the street, S = (cos r, −sin r) along the front.
 */

import type { Pad, TownPack } from "./town-data";

export interface PlotRect {
  /** Centre (world). */
  x: number;
  z: number;
  /** Width along the front (S) and depth toward the street (F), metres. */
  w: number;
  d: number;
  rotation: number;
}

export interface HomePlot {
  rotation: number;
  /** Toward the street. */
  F: [number, number];
  /** Along the front (the house's local +x). */
  S: [number, number];
  /** The two-storey house (walls; the roof overhangs by `ROOF_OVERHANG`). */
  house: PlotRect;
  /** Front yard depth from the wall to the garden wall (m). */
  yard: number;
  /** The garden wall along the front: its local x extents (it returns along both sides to the house). */
  fence: { from: number; to: number };
  /** The gate and the front door, local x. */
  gateX: number;
  doorX: number;
  /** The one-storey back wing on the rest of the outline, if there is room for one. */
  annex: PlotRect | null;
  /** The street point the house faces (nearest centreline point to the home place) and that street's width. */
  street: { x: number; z: number; width: number };
  /** Everything the plot covers (house with roof, yard, wall, annex): roads and poles are not drawn here. */
  footprint: PlotRect[];
}

/** Roof overhang of the house kit beyond its walls (architecture.ts). */
export const ROOF_OVERHANG = 0.66;
const HOUSE_DEPTH = 9.0;
const MIN_DEPTH = 7.0;
const YARD = 3.0;
/** Clearance kept from other outlines and from the street's edge (m). */
const CLEAR = 0.25;

type Vec = [number, number];

const dot = (a: Vec, b: Vec) => a[0] * b[0] + a[1] * b[1];

/** Corners of a rect, world. */
export function rectCorners(rect: PlotRect): Vec[] {
  const F: Vec = [Math.sin(rect.rotation), Math.cos(rect.rotation)];
  const S: Vec = [Math.cos(rect.rotation), -Math.sin(rect.rotation)];
  return [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) => [
    rect.x + S[0] * (a * rect.w) / 2 + F[0] * (b * rect.d) / 2,
    rect.z + S[1] * (a * rect.w) / 2 + F[1] * (b * rect.d) / 2,
  ]);
}

function pointInRing(ring: ArrayLike<number>, x: number, z: number): boolean {
  let inside = false;
  const n = ring.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i, i += 1) {
    const xi = ring[i * 2], zi = ring[i * 2 + 1], xj = ring[j * 2], zj = ring[j * 2 + 1];
    if (zi > z !== zj > z && x < ((xj - xi) * (z - zi)) / (zj - zi) + xi) inside = !inside;
  }
  return inside;
}

function segmentsCross(a: Vec, b: Vec, c: Vec, d: Vec): boolean {
  const cross = (o: Vec, p: Vec, q: Vec) => (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0]);
  const d1 = cross(c, d, a), d2 = cross(c, d, b), d3 = cross(a, b, c), d4 = cross(a, b, d);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/** Whether a rect and a polygon ring overlap (any containment or edge crossing). */
export function rectHitsRing(rect: PlotRect, ring: ArrayLike<number>): boolean {
  const corners = rectCorners(rect);
  const n = ring.length / 2;
  const insideRect = (x: number, z: number) => {
    const F: Vec = [Math.sin(rect.rotation), Math.cos(rect.rotation)], S: Vec = [Math.cos(rect.rotation), -Math.sin(rect.rotation)];
    const p: Vec = [x - rect.x, z - rect.z];
    return Math.abs(dot(p, S)) <= rect.w / 2 && Math.abs(dot(p, F)) <= rect.d / 2;
  };
  for (let i = 0; i < n; i += 1) if (insideRect(ring[i * 2], ring[i * 2 + 1])) return true;
  for (const [x, z] of corners) if (pointInRing(ring, x, z)) return true;
  for (let i = 0; i < 4; i += 1) {
    const a = corners[i], b = corners[(i + 1) % 4];
    for (let j = 0; j < n; j += 1) {
      const c: Vec = [ring[j * 2], ring[j * 2 + 1]], d: Vec = [ring[((j + 1) % n) * 2], ring[((j + 1) % n) * 2 + 1]];
      if (segmentsCross(a, b, c, d)) return true;
    }
  }
  return false;
}

/** The interval a ring covers along `S` on the line {p : p·F = f}, or null if the line misses it. */
function lateralInterval(ring: ArrayLike<number>, F: Vec, S: Vec, f: number): [number, number] | null {
  const hits: number[] = [];
  const n = ring.length / 2;
  for (let i = 0; i < n; i += 1) {
    const a: Vec = [ring[i * 2], ring[i * 2 + 1]], b: Vec = [ring[((i + 1) % n) * 2], ring[((i + 1) % n) * 2 + 1]];
    const fa = dot(a, F), fb = dot(b, F);
    if ((fa - f) * (fb - f) > 0 || fa === fb) continue;
    const t = (f - fa) / (fb - fa);
    hits.push(dot(a, S) + t * (dot(b, S) - dot(a, S)));
  }
  return hits.length >= 2 ? [Math.min(...hits), Math.max(...hits)] : null;
}

/** World point of local (s along S, f along F). */
const at = (S: Vec, F: Vec, s: number, f: number): Vec => [S[0] * s + F[0] * f, S[1] * s + F[1] * f];

/**
 * Lay out Lalita's plot on the home outline of the bake: face the street nearest the home place, set the house back
 * behind a yard, and make it as wide as it can be (up to 7.2 m, so the lane beside it stays open) without its roof, wall or back wing touching another
 * outline.
 */
export function homePlot(pack: TownPack): HomePlot {
  const home = pack.buildings[pack.special.home];
  const ring = home.ring;
  const place = pack.manifest.places.find((entry) => entry.id === "home") ?? { x: home.obb.cx, z: home.obb.cz };
  const others = pack.buildings.filter((b) => b.index !== home.index && Math.hypot(b.obb.cx - home.obb.cx, b.obb.cz - home.obb.cz) < 80);

  // The street: the nearest centreline point to the home place.
  let street = { x: place.x, z: place.z, width: 5, d: Infinity };
  for (const road of pack.roads) {
    const p = road.points;
    for (let i = 0; i + 3 < p.length; i += 2) {
      const ax = p[i], az = p[i + 1], bx = p[i + 2], bz = p[i + 3];
      const len2 = (bx - ax) ** 2 + (bz - az) ** 2 || 1;
      const t = Math.min(1, Math.max(0, ((place.x - ax) * (bx - ax) + (place.z - az) * (bz - az)) / len2));
      const x = ax + t * (bx - ax), z = az + t * (bz - az);
      const d = Math.hypot(x - place.x, z - place.z);
      if (d < street.d) street = { x, z, width: road.width, d };
    }
  }

  // Facing: the outline axis that points most toward the street from the outline's centre.
  const a: Vec = [Math.cos(home.obb.angle), Math.sin(home.obb.angle)];
  const axes: Vec[] = [a, [-a[0], -a[1]], [-a[1], a[0]], [a[1], -a[0]]];
  const toStreet: Vec = [street.x - home.obb.cx, street.z - home.obb.cz];
  const F = axes.reduce((best, axis) => (dot(axis, toStreet) > dot(best, toStreet) ? axis : best));
  const rotation = Math.atan2(F[0], F[1]);
  const S: Vec = [Math.cos(rotation), -Math.sin(rotation)];

  // Along F: the garden wall a little short of the street's edge, the house a yard behind it, as deep as the outline
  // allows behind that.
  const fStreet = dot([street.x, street.z], F);
  const fFence = fStreet - street.width / 2 - CLEAR - 0.1;
  const fFront = fFence - YARD;
  let fOutlineBack = Infinity;
  for (let i = 0; i < ring.length; i += 2) fOutlineBack = Math.min(fOutlineBack, dot([ring[i], ring[i + 1]], F));
  const depth = Math.max(MIN_DEPTH, Math.min(HOUSE_DEPTH, fFront - fOutlineBack - 0.3));
  const fCentre = fFront - depth / 2;

  // Along S: the widest house (with its roof) that clears every other outline, near the outline's own middle.
  const middle = (() => {
    const span = lateralInterval(ring, F, S, fFront - depth / 2);
    return span ? (span[0] + span[1]) / 2 : dot([home.obb.cx, home.obb.cz], S);
  })();
  const roofRect = (s: number, w: number): PlotRect => {
    const [x, z] = at(S, F, s, fCentre);
    return { x, z, w: w + 2 * ROOF_OVERHANG + 2 * CLEAR, d: depth + 2 * ROOF_OVERHANG + 2 * CLEAR, rotation };
  };
  let best: { s: number; w: number; score: number } | null = null;
  for (let w = 7.2; w >= 5.4 - 1e-9; w -= 0.1) {
    for (let o = 0; o <= 3; o += 0.1) {
      for (const s of o === 0 ? [middle] : [middle - o, middle + o]) {
        const score = w * 2 - o;
        if (best && score <= best.score) continue;
        if (!others.some((b) => rectHitsRing(roofRect(s, w), b.ring))) best = { s, w, score };
      }
    }
  }
  if (!best) throw new Error("No room for Lalita's house on its plot");
  const [hx, hz] = at(S, F, best.s, fCentre);
  const house: PlotRect = { x: hx, z: hz, w: +best.w.toFixed(2), d: depth, rotation };

  // The gate faces the street point (where the walk starts), within the front; the door just inside it.
  const gateX = Math.max(-(house.w / 2 - 1.2), Math.min(house.w / 2 - 1.2, dot([street.x - hx, street.z - hz], S)));
  const doorX = Math.max(-(house.w / 2 - 0.9), Math.min(house.w / 2 - 0.9, gateX - 0.2));

  // The garden wall: 1.3 m past each side of the house, trimmed where it would meet another outline.
  const wallRect = (from: number, to: number): PlotRect => {
    const [x, z] = at(S, F, best!.s + (from + to) / 2, fFront + YARD / 2 + 0.1);
    return { x, z, w: to - from + 0.3, d: YARD + 0.5, rotation };
  };
  let from = -house.w / 2 - 1.3, to = house.w / 2 + 1.3;
  while (from < -house.w / 2 && others.some((b) => rectHitsRing(wallRect(from, -house.w / 2), b.ring))) from += 0.1;
  while (to > house.w / 2 && others.some((b) => rectHitsRing(wallRect(house.w / 2, to), b.ring))) to -= 0.1;
  from = Math.min(from, -house.w / 2);
  to = Math.max(to, house.w / 2);

  // The back wing: the rest of the outline behind the house (built against its back wall), inset, clear of others.
  let annex: PlotRect | null = null;
  const fAnnexBack = fOutlineBack + 0.3, fAnnexFront = fFront - depth;
  if (fAnnexFront - fAnnexBack >= 2.5) {
    let lo = -Infinity, hi = Infinity;
    for (let k = 0; k <= 8; k += 1) {
      const span = lateralInterval(ring, F, S, fAnnexBack + ((fAnnexFront - fAnnexBack) * k) / 8);
      if (!span) continue;
      lo = Math.max(lo, span[0] + CLEAR);
      hi = Math.min(hi, span[1] - CLEAR);
    }
    const rect = (l: number, h: number): PlotRect => {
      const [x, z] = at(S, F, (l + h) / 2, (fAnnexBack + fAnnexFront) / 2);
      return { x, z, w: h - l, d: fAnnexFront - fAnnexBack, rotation };
    };
    // Shrink from both sides until its roof (0.3 m eaves) clears every other outline.
    const eaves = (r: PlotRect): PlotRect => ({ ...r, w: r.w + 0.6, d: r.d + 0.6 });
    while (hi - lo >= 2.5 && others.some((b) => rectHitsRing(eaves(rect(lo, hi)), b.ring))) { lo += 0.1; hi -= 0.1; }
    if (hi - lo >= 2.5) annex = rect(lo, hi);
  }

  const yardRect = wallRect(from, to);
  return {
    rotation, F, S, house, yard: YARD, fence: { from, to }, gateX, doorX, annex,
    street: { x: street.x, z: street.z, width: street.width },
    footprint: [roofRect(best.s, house.w), yardRect, ...(annex ? [{ ...annex, w: annex.w + 0.6, d: annex.d + 0.6 }] : [])],
  };
}

/** Whether a point lies on the plot (under the house, its roof, the yard or the back wing). */
export function onPlot(plot: HomePlot, x: number, z: number, margin = 0): boolean {
  return plot.footprint.some((rect) => {
    const F: Vec = [Math.sin(rect.rotation), Math.cos(rect.rotation)], S: Vec = [Math.cos(rect.rotation), -Math.sin(rect.rotation)];
    const p: Vec = [x - rect.x, z - rect.z];
    return Math.abs(dot(p, S)) <= rect.w / 2 + margin && Math.abs(dot(p, F)) <= rect.d / 2 + margin;
  });
}

/** The flat pad that holds the house and its yard, out to the garden wall, at `height` (the home cell's ground). */
export function homePad(plot: HomePlot, height: number): Pad {
  const { house, S, F } = plot;
  const along = (plot.fence.from + plot.fence.to) / 2, across = (plot.yard + 0.4) / 2;
  return {
    x: house.x + S[0] * along + F[0] * across,
    z: house.z + S[1] * along + F[1] * across,
    radius: 0, blend: 1.5, height,
    rect: { w: plot.fence.to - plot.fence.from + 0.3, d: house.d + plot.yard + 0.4, rotation: plot.rotation },
  };
}
