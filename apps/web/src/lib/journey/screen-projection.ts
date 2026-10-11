/**
 * Maps a DOM element onto a projected 3D screen quad with a CSS `matrix3d` homography, so a real page (in an iframe)
 * can sit on a phone or monitor in the WebGL scene and become the full viewport when the camera aligns with it.
 * The element must use `position: absolute; left: 0; top: 0; transform-origin: 0 0`.
 */

export interface Point { x: number; y: number }

/** Corners in screen pixels: top-left, top-right, bottom-right, bottom-left. */
export type Quad = readonly [Point, Point, Point, Point];

export interface Homography { a: number; b: number; c: number; d: number; e: number; f: number; g: number; h: number }

/** Projective map of the unit square onto `quad` (Heckbert's square-to-quad), as (u, v) → quad. */
export function squareToQuad(quad: Quad): Homography {
  const [p0, p1, p2, p3] = quad;
  const dx1 = p1.x - p2.x, dx2 = p3.x - p2.x, dx3 = p0.x - p1.x + p2.x - p3.x;
  const dy1 = p1.y - p2.y, dy2 = p3.y - p2.y, dy3 = p0.y - p1.y + p2.y - p3.y;
  if (Math.abs(dx3) < 1e-9 && Math.abs(dy3) < 1e-9) {
    return { a: p1.x - p0.x, b: p3.x - p0.x, c: p0.x, d: p1.y - p0.y, e: p3.y - p0.y, f: p0.y, g: 0, h: 0 };
  }
  const det = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(det) < 1e-12) throw new Error("Degenerate quad");
  const g = (dx3 * dy2 - dx2 * dy3) / det;
  const h = (dx1 * dy3 - dx3 * dy1) / det;
  return {
    a: p1.x - p0.x + g * p1.x, b: p3.x - p0.x + h * p3.x, c: p0.x,
    d: p1.y - p0.y + g * p1.y, e: p3.y - p0.y + h * p3.y, f: p0.y,
    g, h,
  };
}

export function applyHomography(m: Homography, u: number, v: number): Point {
  const w = m.g * u + m.h * v + 1;
  return { x: (m.a * u + m.b * v + m.c) / w, y: (m.d * u + m.e * v + m.f) / w };
}

/** CSS `matrix3d(...)` that maps an element of `width` × `height` CSS pixels onto `quad`. */
export function quadToMatrix3d(width: number, height: number, quad: Quad): string {
  const m = squareToQuad(quad);
  const a = m.a / width, b = m.b / height, d = m.d / width, e = m.e / height, g = m.g / width, h = m.h / height;
  // Column-major 4x4: x' = a x + b y + c, y' = d x + e y + f, w' = g x + h y + 1.
  const values = [a, d, 0, g, b, e, 0, h, 0, 0, 1, 0, m.c, m.f, 0, 1];
  return `matrix3d(${values.map((value) => (Math.abs(value) < 1e-12 ? 0 : Number(value.toPrecision(10)))).join(",")})`;
}

/** True when a quad is a plausible on-screen shape (convex, non-degenerate, not absurdly large). */
export function quadIsDrawable(quad: Quad, viewportWidth: number, viewportHeight: number): boolean {
  const limit = 40 * Math.max(viewportWidth, viewportHeight);
  if (quad.some((p) => !Number.isFinite(p.x) || !Number.isFinite(p.y) || Math.abs(p.x) > limit || Math.abs(p.y) > limit)) return false;
  let sign = 0;
  for (let i = 0; i < 4; i += 1) {
    const p = quad[i], q = quad[(i + 1) % 4], r = quad[(i + 2) % 4];
    const cross = (q.x - p.x) * (r.y - q.y) - (q.y - p.y) * (r.x - q.x);
    if (Math.abs(cross) < 1e-6) return false;
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

/** Axis-aligned bounds of a quad. */
export function quadBounds(quad: Quad): { left: number; top: number; width: number; height: number } {
  const xs = quad.map((p) => p.x), ys = quad.map((p) => p.y);
  const left = Math.min(...xs), top = Math.min(...ys);
  return { left, top, width: Math.max(...xs) - left, height: Math.max(...ys) - top };
}
