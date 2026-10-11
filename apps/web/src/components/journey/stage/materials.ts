import * as THREE from "three";

/**
 * Shared art direction for the journey: a controlled palette, small procedural textures (generated at start-up, no
 * downloaded assets) and geometry helpers that every part of the scene uses, so the neighbourhood, the people and the
 * operations room read as one production.
 */

export type Quality = "high" | "low";

/** Muted, warm palette derived from the FloodGuard brand (cream, muted green, teal, dark neutral). */
export const PALETTE = {
  // Ground
  grass: new THREE.Color("#8d9b67"),
  grassDeep: new THREE.Color("#6e7f4f"),
  grassDry: new THREE.Color("#ada677"),
  paddy: new THREE.Color("#9aa86a"),
  paddyYoung: new THREE.Color("#b2b97a"),
  bund: new THREE.Color("#8a7d5c"),
  soil: new THREE.Color("#8f7f61"),
  bank: new THREE.Color("#776b52"),
  bankWet: new THREE.Color("#5f574a"),
  yard: new THREE.Color("#b9ad92"),
  hill: new THREE.Color("#788c5c"),
  // Built
  plaster: [new THREE.Color("#efe8d8"), new THREE.Color("#f3efe6"), new THREE.Color("#e6dac2"), new THREE.Color("#dfe0d0"), new THREE.Color("#e9e1d3")],
  roof: [new THREE.Color("#a35f45"), new THREE.Color("#8e8a82"), new THREE.Color("#5f7370"), new THREE.Color("#7f4d3d"), new THREE.Color("#68757b")],
  trim: new THREE.Color("#f6f2ea"),
  trimDark: new THREE.Color("#4a5a5c"),
  concrete: new THREE.Color("#b8b2a6"),
  concreteDark: new THREE.Color("#9c968b"),
  plinth: new THREE.Color("#a9a296"),
  wood: new THREE.Color("#7b5a40"),
  woodLight: new THREE.Color("#b08a64"),
  metal: new THREE.Color("#c3c5c2"),
  metalDark: new THREE.Color("#3b4244"),
  asphalt: new THREE.Color("#7b7a75"),
  marking: new THREE.Color("#efeadb"),
  pole: new THREE.Color("#a7a399"),
  // Brand
  teal: new THREE.Color("#1f7f86"),
  tealMuted: new THREE.Color("#4d7d7b"),
  clinicGreen: new THREE.Color("#2e7f5b"),
  amber: new THREE.Color("#c4721c"),
  ink: new THREE.Color("#1d2a2b"),
};

export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

// --- Noise -----------------------------------------------------------------------------------------------------------

function hash2(ix: number, iy: number, seed: number): number {
  let h = Math.imul(ix, 374761393) ^ Math.imul(iy, 668265263) ^ Math.imul(seed, 1442695041);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}

/** Value noise in [0, 1], tileable with integer `period`. */
export function valueNoise(x: number, y: number, period = 1 << 20, seed = 1): number {
  const x0 = Math.floor(x), y0 = Math.floor(y);
  const fx = x - x0, fy = y - y0;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const w = (ix: number, iy: number) => hash2(((ix % period) + period) % period, ((iy % period) + period) % period, seed);
  const a = w(x0, y0), b = w(x0 + 1, y0), c = w(x0, y0 + 1), d = w(x0 + 1, y0 + 1);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

/** Fractal value noise in [0, 1]. */
export function fbm(x: number, y: number, octaves = 4, period = 1 << 20, seed = 1): number {
  let sum = 0, amplitude = 0.5, total = 0, frequency = 1;
  for (let i = 0; i < octaves; i += 1) {
    sum += amplitude * valueNoise(x * frequency, y * frequency, period * frequency, seed + i * 17);
    total += amplitude;
    amplitude *= 0.5;
    frequency *= 2;
  }
  return sum / total;
}

// --- Textures --------------------------------------------------------------------------------------------------------

function dataTexture(size: number, paint: (u: number, v: number, out: [number, number, number, number]) => void, srgb: boolean): THREE.DataTexture {
  const data = new Uint8Array(size * size * 4);
  const px: [number, number, number, number] = [0, 0, 0, 1];
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      paint(x / size, y / size, px);
      const i = (y * size + x) * 4;
      data[i] = Math.max(0, Math.min(255, px[0] * 255));
      data[i + 1] = Math.max(0, Math.min(255, px[1] * 255));
      data[i + 2] = Math.max(0, Math.min(255, px[2] * 255));
      data[i + 3] = Math.max(0, Math.min(255, px[3] * 255));
    }
  }
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = 8;
  if (srgb) texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  return texture;
}

const grey = (out: [number, number, number, number], value: number, alpha = 1) => {
  out[0] = out[1] = out[2] = value;
  out[3] = alpha;
};

/** Fine grass/soil detail, grey around 0.9 (multiplies the painted ground). */
export function groundDetailTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const n = fbm(u * 16, v * 16, 4, 16, 3);
    const blades = valueNoise(u * 96, v * 96, 96, 9);
    const speck = valueNoise(u * 180, v * 180, 180, 5) > 0.82 ? -0.06 : 0;
    grey(out, 0.8 + n * 0.16 + blades * 0.06 + speck);
  }, true);
}

/** Asphalt aggregate, grey around 0.95. */
export function asphaltTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const n = fbm(u * 8, v * 8, 3, 8, 21);
    const grain = valueNoise(u * 200, v * 200, 200, 4);
    const patch = fbm(u * 3, v * 3, 2, 3, 40) > 0.62 ? -0.05 : 0;
    grey(out, 0.86 + n * 0.1 + (grain - 0.5) * 0.12 + patch);
  }, true);
}

/** Concrete slabs with expansion joints: the tile is one 4 m slab. */
export function concreteTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const n = fbm(u * 6, v * 6, 3, 6, 33);
    const grain = valueNoise(u * 160, v * 160, 160, 8);
    const joint = v < 0.012 || v > 0.988 ? -0.22 : 0;
    grey(out, 0.9 + n * 0.08 + (grain - 0.5) * 0.06 + joint);
  }, true);
}

/** Subtle plaster variation for walls (world-projected). */
export function plasterTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const n = fbm(u * 6, v * 6, 4, 6, 51);
    const fine = valueNoise(u * 128, v * 128, 128, 52);
    // Faint rain streaks running down the wall.
    const streak = fbm(u * 40, v * 2, 2, 40, 53) > 0.63 ? -0.025 : 0;
    grey(out, 0.92 + n * 0.07 + (fine - 0.5) * 0.03 + streak);
  }, true);
}

/** Roof tile rows (u along the eave, v up the slope); the tile is 1.6 m (8 rows). */
export function roofTileTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const rows = 8;
    const row = Math.floor(v * rows);
    const inRow = v * rows - row;
    const cols = 6;
    const offset = row % 2 ? 0.5 : 0;
    const inCol = (u * cols + offset) % 1;
    const tone = 0.86 + hash2(row, Math.floor(u * cols + offset), 61) * 0.12;
    // Overlap shadow at the lower edge of each row, rounded tile profile across.
    const lap = THREE.MathUtils.smoothstep(inRow, 0, 0.16);
    const profile = 0.9 + 0.1 * Math.sin(inCol * Math.PI);
    const weather = fbm(u * 4, v * 4, 3, 4, 62) * 0.1;
    grey(out, tone * (0.72 + 0.28 * lap) * profile + weather - 0.04);
  }, true);
}

/** Standing-seam metal roof: seams run up the slope (constant u). */
export function seamRoofTexture(): THREE.DataTexture {
  return dataTexture(256, (u, v, out) => {
    const seam = (u * 5) % 1;
    const ridge = seam < 0.06 ? 1.08 : seam < 0.1 ? 0.84 : 1;
    const weather = fbm(u * 3, v * 3, 3, 3, 70) * 0.06;
    grey(out, 0.9 * ridge + weather);
  }, true);
}

/** Warm timber floor planks for the operations room. */
export function woodFloorTexture(): THREE.DataTexture {
  const base = new THREE.Color("#a78462"), dark = new THREE.Color("#7f5f43");
  const color = new THREE.Color();
  return dataTexture(256, (u, v, out) => {
    const planks = 6;
    const plank = Math.floor(v * planks);
    const along = (u + hash2(plank, 0, 80) * 3) % 1;
    const butt = (along * 2) % 1 < 0.008 ? 0.75 : 1;
    const gap = (v * planks) % 1 < 0.035 ? 0.62 : 1;
    const grain = valueNoise(u * 4 + plank * 7, v * 160, 1 << 20, 81);
    color.copy(base).lerp(dark, hash2(plank, Math.floor(along * 2), 82) * 0.5 + grain * 0.25);
    out[0] = color.r * gap * butt * 1.25;
    out[1] = color.g * gap * butt * 1.25;
    out[2] = color.b * gap * butt * 1.25;
    out[3] = 1;
  }, false);
}

/** Soft contact shadow: alpha falls off from a rounded rectangle (`inset` 0..0.5 of the texture). */
export function contactShadowTexture(inset = 0.28, softness = 0.22): THREE.DataTexture {
  return dataTexture(128, (u, v, out) => {
    const dx = Math.max(0, Math.abs(u - 0.5) - (0.5 - inset - softness));
    const dy = Math.max(0, Math.abs(v - 0.5) - (0.5 - inset - softness));
    const d = Math.hypot(dx, dy) / softness;
    const a = 1 - THREE.MathUtils.smoothstep(d, 0, 1);
    grey(out, a * a); // alphaMap samples the green channel
  }, false);
}

/** Procedural tiling normal map for gentle ripples on water. */
export function rippleNormalTexture(): THREE.DataTexture {
  const size = 128;
  const height = (x: number, y: number) => {
    const u = (x / size) * Math.PI * 2, v = (y / size) * Math.PI * 2;
    return Math.sin(u * 3 + Math.sin(v * 2) * 0.8) * 0.5 + Math.sin(v * 5 + u) * 0.3 + Math.sin((u + v) * 7) * 0.15 + Math.sin(u * 11 - v * 4) * 0.06;
  };
  const n = new THREE.Vector3();
  const texture = dataTexture(size, (u, v, out) => {
    const x = u * size, y = v * size;
    const dx = height(x + 1, y) - height(x - 1, y);
    const dy = height(x, y + 1) - height(x, y - 1);
    n.set(-dx * 0.9, -dy * 0.9, 1).normalize();
    out[0] = n.x * 0.5 + 0.5;
    out[1] = n.y * 0.5 + 0.5;
    out[2] = n.z * 0.5 + 0.5;
    out[3] = 1;
  }, false);
  return texture;
}

// --- Geometry helpers ------------------------------------------------------------------------------------------------

export function paint(geometry: THREE.BufferGeometry, color: THREE.Color, shade = 1): THREE.BufferGeometry {
  const count = geometry.getAttribute("position").count;
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    colors[i * 3] = color.r * shade;
    colors[i * 3 + 1] = color.g * shade;
    colors[i * 3 + 2] = color.b * shade;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

/** Non-indexed box whose UVs are in metres / `tile` (so textures keep one density across sizes). */
export function box(w: number, h: number, d: number, tile = 1): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(w, h, d);
  const uv = geometry.getAttribute("uv") as THREE.BufferAttribute;
  // BoxGeometry face order: +x, -x, +y, -y, +z, -z; 4 vertices each.
  const dims: Array<[number, number]> = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
  for (let face = 0; face < 6; face += 1) {
    for (let k = 0; k < 4; k += 1) {
      const i = face * 4 + k;
      uv.setXY(i, (uv.getX(i) * dims[face][0]) / tile, (uv.getY(i) * dims[face][1]) / tile);
    }
  }
  return geometry.toNonIndexed();
}

/** Non-indexed cylinder. */
export function cylinder(rTop: number, rBottom: number, h: number, segments = 12): THREE.BufferGeometry {
  return new THREE.CylinderGeometry(rTop, rBottom, h, segments).toNonIndexed();
}

/** Place a geometry: translate, rotate about y, optional extra rotation (applied first) and scale. */
export function placed(
  geometry: THREE.BufferGeometry,
  x: number,
  y: number,
  z: number,
  rotationY = 0,
  pre?: THREE.Euler,
  scale?: THREE.Vector3,
): THREE.BufferGeometry {
  if (pre) geometry.applyMatrix4(new THREE.Matrix4().makeRotationFromEuler(pre));
  const matrix = new THREE.Matrix4().compose(
    new THREE.Vector3(x, y, z),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotationY),
    scale ?? new THREE.Vector3(1, 1, 1),
  );
  return geometry.applyMatrix4(matrix);
}

/**
 * A prism: a closed 2D profile in the (z, y) plane extruded along x from x0 to x1. Side UVs run along x (u) and along
 * the profile perimeter (v), in metres / `tile`; caps use (z, y). Returns non-indexed geometry with flat normals.
 */
export function prism(profile: Array<[number, number]>, x0: number, x1: number, tile = 1, caps = true): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  type V = [number, number, number, number, number]; // x, y, z, u, v
  const ab = new THREE.Vector3(), ac = new THREE.Vector3();
  /** Emit a triangle wound so that its normal agrees with `outward`. */
  const tri = (p: V, q: V, r: V, outward: THREE.Vector3) => {
    ab.set(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
    ac.set(r[0] - p[0], r[1] - p[1], r[2] - p[2]);
    const order = ab.cross(ac).dot(outward) >= 0 ? [p, q, r] : [p, r, q];
    for (const [x, y, z, u, v] of order) {
      positions.push(x, y, z);
      uvs.push(u / tile, v / tile);
    }
  };
  // Signed area tells which side of each edge is outside.
  let area = 0;
  for (let i = 0; i < profile.length; i += 1) {
    const [z0, y0] = profile[i], [z1, y1] = profile[(i + 1) % profile.length];
    area += z0 * y1 - z1 * y0;
  }
  const pts = area < 0 ? profile.slice().reverse() : profile; // now counter-clockwise in (z, y)
  const outward = new THREE.Vector3();
  let run = 0;
  for (let i = 0; i < pts.length; i += 1) {
    const [z0, y0] = pts[i], [z1, y1] = pts[(i + 1) % pts.length];
    const length = Math.hypot(z1 - z0, y1 - y0);
    if (length < 1e-6) continue;
    // For a counter-clockwise polygon in (z, y), the outward normal of edge (dz, dy) is (dy, -dz).
    outward.set(0, -(z1 - z0), y1 - y0);
    const a: V = [x0, y0, z0, x0, run], b: V = [x1, y0, z0, x1, run];
    const c: V = [x1, y1, z1, x1, run + length], d: V = [x0, y1, z1, x0, run + length];
    tri(a, b, c, outward);
    tri(a, c, d, outward);
    run += length;
  }
  if (caps) {
    const contour = pts.map(([z, y]) => new THREE.Vector2(z, y));
    const triangles = THREE.ShapeUtils.triangulateShape(contour, []);
    const px = new THREE.Vector3(1, 0, 0), nx = new THREE.Vector3(-1, 0, 0);
    for (const [i, j, k] of triangles) {
      const cap = (x: number, n: THREE.Vector3) => tri(
        [x, pts[i][1], pts[i][0], pts[i][0], pts[i][1]],
        [x, pts[j][1], pts[j][0], pts[j][0], pts[j][1]],
        [x, pts[k][1], pts[k][0], pts[k][0], pts[k][1]],
        n,
      );
      cap(x1, px);
      cap(x0, nx);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.computeVertexNormals();
  return geometry;
}

/**
 * Make every triangle of a closed, convex-ish part face away from its centroid. Procedural builders then need not get
 * every winding right by hand (back-face culling would otherwise hide wrongly wound faces).
 */
export function fixWinding(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  const position = geometry.getAttribute("position") as THREE.BufferAttribute;
  const uv = geometry.getAttribute("uv") as THREE.BufferAttribute | undefined;
  geometry.computeBoundingBox();
  const centre = geometry.boundingBox!.getCenter(new THREE.Vector3());
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3(), m = new THREE.Vector3();
  for (let i = 0; i < position.count; i += 3) {
    a.fromBufferAttribute(position, i);
    b.fromBufferAttribute(position, i + 1);
    c.fromBufferAttribute(position, i + 2);
    n.subVectors(c, b).cross(m.subVectors(a, b));
    m.copy(a).add(b).add(c).divideScalar(3).sub(centre);
    if (n.dot(m) < 0) {
      position.setXYZ(i + 1, c.x, c.y, c.z);
      position.setXYZ(i + 2, b.x, b.y, b.z);
      if (uv) {
        const u1 = uv.getX(i + 1), v1 = uv.getY(i + 1);
        uv.setXY(i + 1, uv.getX(i + 2), uv.getY(i + 2));
        uv.setXY(i + 2, u1, v1);
      }
    }
  }
  geometry.computeVertexNormals();
  return geometry;
}

/** World-projected UVs (metres / tile) chosen per triangle by its dominant normal axis. Non-indexed geometry only. */
export function worldUV(geometry: THREE.BufferGeometry, tile = 1): THREE.BufferGeometry {
  const position = geometry.getAttribute("position") as THREE.BufferAttribute;
  const uvs = new Float32Array(position.count * 2);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3(), e = new THREE.Vector3();
  for (let i = 0; i < position.count; i += 3) {
    a.fromBufferAttribute(position, i);
    b.fromBufferAttribute(position, i + 1);
    c.fromBufferAttribute(position, i + 2);
    n.subVectors(b, a).cross(e.subVectors(c, a));
    const ax = Math.abs(n.x), ay = Math.abs(n.y), az = Math.abs(n.z);
    for (let k = 0; k < 3; k += 1) {
      const p = k === 0 ? a : k === 1 ? b : c;
      const [u, v] = ay >= ax && ay >= az ? [p.x, p.z] : ax >= az ? [p.z, p.y] : [p.x, p.y];
      uvs[(i + k) * 2] = u / tile;
      uvs[(i + k) * 2 + 1] = v / tile;
    }
  }
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  return geometry;
}

/** Keep only position, normal, uv and color so heterogeneous parts merge. */
export function normalise(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  const g = geometry.index ? geometry.toNonIndexed() : geometry;
  for (const name of Object.keys(g.attributes)) {
    if (!["position", "normal", "uv", "color"].includes(name)) g.deleteAttribute(name);
  }
  if (!g.getAttribute("normal")) g.computeVertexNormals();
  if (!g.getAttribute("uv")) g.setAttribute("uv", new THREE.BufferAttribute(new Float32Array(g.getAttribute("position").count * 2), 2));
  if (!g.getAttribute("color")) paint(g, new THREE.Color(1, 1, 1));
  return g;
}
