import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { LAYOUT, terrainHeight } from "@/lib/journey/terrain";

import {
  PALETTE,
  box,
  concreteTexture,
  cylinder,
  fixWinding,
  normalise,
  paint,
  plasterTexture,
  prism,
  roofTileTexture,
  seamRoofTexture,
  seeded,
  worldUV,
  type Quality,
} from "./materials";

/**
 * Procedural architecture for the illustrative neighbourhood: houses with real roof solids (thickness, overhang,
 * fascia, soffit), framed and recessed-looking windows, doors with steps and canopies, porches, garden walls, water
 * tanks and AC units; and a clinic that reads as an essential service (raised floor, entrance portico, ramp, signage).
 * Parts are collected per material and merged, so the whole neighbourhood is a handful of draw calls.
 */

export type Bucket = "plaster" | "trim" | "roof" | "glass" | "wood" | "concrete" | "metal" | "dark";

export class Parts {
  readonly lists: Record<Bucket, THREE.BufferGeometry[]> = {
    plaster: [], trim: [], roof: [], glass: [], wood: [], concrete: [], metal: [], dark: [],
  };

  add(bucket: Bucket, geometry: THREE.BufferGeometry, color: THREE.Color, matrix: THREE.Matrix4, shade = 1): void {
    const g = normalise(geometry);
    paint(g, color, shade);
    g.applyMatrix4(matrix);
    this.lists[bucket].push(g);
  }
}

export interface ArchitectureTextures {
  plaster: THREE.Texture;
  roof: THREE.Texture;
  concrete: THREE.Texture;
  seam: THREE.Texture;
}

export function architectureTextures(): ArchitectureTextures {
  return { plaster: plasterTexture(), roof: roofTileTexture(), concrete: concreteTexture(), seam: seamRoofTexture() };
}

/** One shared material per bucket (vertex colours carry per-part colour). */
export function architectureMaterials(textures: ArchitectureTextures): Record<Bucket, THREE.Material> {
  return {
    plaster: new THREE.MeshStandardMaterial({ vertexColors: true, map: textures.plaster, roughness: 0.92 }),
    trim: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.66 }),
    roof: new THREE.MeshStandardMaterial({ vertexColors: true, map: textures.roof, bumpMap: textures.roof, bumpScale: 1.6, roughness: 0.82 }),
    glass: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.05, metalness: 0.15, envMapIntensity: 1.6 }),
    wood: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.62 }),
    concrete: new THREE.MeshStandardMaterial({ vertexColors: true, map: textures.concrete, roughness: 0.95 }),
    metal: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.34, metalness: 0.75 }),
    dark: new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.6 }),
  };
}

export function mergeParts(parts: Parts, materials: Record<Bucket, THREE.Material>, name: string): THREE.Group {
  const group = new THREE.Group();
  group.name = name;
  (Object.keys(parts.lists) as Bucket[]).forEach((bucket) => {
    const list = parts.lists[bucket];
    if (!list.length) return;
    const mesh = new THREE.Mesh(mergeGeometries(list)!, materials[bucket]);
    mesh.name = `${name}-${bucket}`;
    mesh.castShadow = bucket !== "glass";
    mesh.receiveShadow = true;
    group.add(mesh);
    list.forEach((g) => g.dispose());
  });
  return group;
}

// --- Matrices --------------------------------------------------------------------------------------------------------

const M = (x: number, y: number, z: number, ry = 0, rx = 0, rz = 0) =>
  new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz, "YXZ")), new THREE.Vector3(1, 1, 1));

/** Collects parts in a local frame, then hands them to `Parts` in world space. */
class Frame {
  constructor(private readonly parts: Parts, readonly matrix: THREE.Matrix4) {}
  add(bucket: Bucket, geometry: THREE.BufferGeometry, color: THREE.Color, local: THREE.Matrix4, shade = 1): void {
    this.parts.add(bucket, geometry, color, this.matrix.clone().multiply(local), shade);
  }
  child(local: THREE.Matrix4): Frame {
    return new Frame(this.parts, this.matrix.clone().multiply(local));
  }
}

// --- Roof solids -----------------------------------------------------------------------------------------------------

/**
 * Hip roof solid: eave rectangle W × D at y = 0 (ridge along x), pitched faces, a fascia of depth `fascia` below the
 * eave and a soffit underneath. UVs: u along the eave, v up the slope, in metres / `tile`.
 */
export function hipRoof(W: number, D: number, pitch: number, fascia: number, tile: number): THREE.BufferGeometry {
  if (W < D) {
    const g = hipRoof(D, W, pitch, fascia, tile);
    g.rotateY(Math.PI / 2);
    return g;
  }
  const h = (D / 2) * Math.tan(pitch), r = (W - D) / 2, k = 1 / Math.cos(pitch), f = fascia;
  const positions: number[] = [];
  const uvs: number[] = [];
  const P = (x: number, y: number, z: number, u: number, v: number) => {
    positions.push(x, y, z);
    uvs.push(u / tile, v / tile);
  };
  const A = [-W / 2, 0, D / 2], B = [W / 2, 0, D / 2], C = [W / 2, 0, -D / 2], Dv = [-W / 2, 0, -D / 2];
  const R1 = [-r, h, 0], R2 = [r, h, 0];
  const front = (p: number[]) => P(p[0], p[1], p[2], p[0], (D / 2 - p[2]) * k);
  const back = (p: number[]) => P(p[0], p[1], p[2], -p[0], (D / 2 + p[2]) * k);
  const right = (p: number[]) => P(p[0], p[1], p[2], -p[2], (W / 2 - p[0]) * k);
  const left = (p: number[]) => P(p[0], p[1], p[2], p[2], (W / 2 + p[0]) * k);
  [A, B, R2, A, R2, R1].forEach(front);
  [C, Dv, R1, C, R1, R2].forEach(back);
  [B, C, R2].forEach(right);
  [Dv, A, R1].forEach(left);
  // Fascia band and soffit.
  const ring = [A, B, C, Dv];
  for (let i = 0; i < 4; i += 1) {
    const p = ring[i], q = ring[(i + 1) % 4];
    const len = Math.hypot(q[0] - p[0], q[2] - p[2]);
    P(p[0], 0, p[2], 0, 0); P(q[0], 0, q[2], len, 0); P(q[0], -f, q[2], len, f);
    P(p[0], 0, p[2], 0, 0); P(q[0], -f, q[2], len, f); P(p[0], -f, p[2], 0, f);
  }
  P(A[0], -f, A[2], A[0], A[2]); P(Dv[0], -f, Dv[2], Dv[0], Dv[2]); P(C[0], -f, C[2], C[0], C[2]);
  P(A[0], -f, A[2], A[0], A[2]); P(C[0], -f, C[2], C[0], C[2]); P(B[0], -f, B[2], B[0], B[2]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  return fixWinding(geometry);
}

/** Gable roof: an inverted-V slab (thickness `t`) over a W × D footprint, ridge along x. */
function gableRoof(W: number, D: number, pitch: number, t: number, tile: number): { geometry: THREE.BufferGeometry; h: number; tv: number } {
  const Dz = D / 2, h = Dz * Math.tan(pitch), tv = t / Math.cos(pitch);
  const geometry = prism([[Dz, 0], [0, h], [-Dz, 0], [-Dz, -tv], [0, h - tv], [Dz, -tv]], -W / 2, W / 2, tile);
  return { geometry, h, tv };
}

// --- Facade items (local frame: origin on the wall surface, +z outward) -----------------------------------------------

function windowItem(frame: Frame, ww: number, wh: number, opts: { trim: THREE.Color; hood: boolean; curtain: number }): void {
  const f = 0.075;
  const glass = new THREE.Color("#26343b").lerp(new THREE.Color("#5b5f5a"), opts.curtain);
  frame.add("glass", box(ww, wh, 0.03), glass, M(0, 0, 0.015));
  frame.add("trim", box(ww + 2 * f, f, 0.09), opts.trim, M(0, wh / 2 + f / 2, 0.045));
  frame.add("trim", box(ww + 2 * f, f, 0.09), opts.trim, M(0, -wh / 2 - f / 2, 0.045));
  frame.add("trim", box(f, wh, 0.09), opts.trim, M(-(ww / 2 + f / 2), 0, 0.045));
  frame.add("trim", box(f, wh, 0.09), opts.trim, M(ww / 2 + f / 2, 0, 0.045));
  if (ww > 0.95) frame.add("trim", box(0.045, wh, 0.055), opts.trim, M(0, 0, 0.03));
  frame.add("trim", box(ww, 0.04, 0.05), opts.trim, M(0, wh * 0.18, 0.03));
  frame.add("concrete", box(ww + 0.32, 0.07, 0.2), PALETTE.concrete, M(0, -wh / 2 - f - 0.035, 0.1));
  if (opts.hood) frame.add("trim", box(ww + 0.5, 0.08, 0.46), opts.trim, M(0, wh / 2 + f + 0.24, 0.23));
}

function doorItem(frame: Frame, trim: THREE.Color, wood: THREE.Color): void {
  const dw = 0.94, dh = 2.08, f = 0.085;
  frame.add("wood", box(dw, dh, 0.045), wood, M(0, dh / 2, 0.02));
  // Two recessed panels read through slightly darker inlays.
  for (const y of [0.55, 1.45]) frame.add("wood", box(dw * 0.66, 0.62, 0.02), wood, M(0, y, 0.048), 0.86);
  frame.add("metal", box(0.03, 0.16, 0.04), PALETTE.metal, M(dw * 0.36, 1.02, 0.07));
  frame.add("trim", box(dw + 2 * f, f, 0.1), trim, M(0, dh + f / 2, 0.05));
  frame.add("trim", box(f, dh, 0.1), trim, M(-(dw / 2 + f / 2), dh / 2, 0.05));
  frame.add("trim", box(f, dh, 0.1), trim, M(dw / 2 + f / 2, dh / 2, 0.05));
}

/** Ground height the kit builds on: the illustrative terrain by default, the real town's ground once set. */
let groundHeight: (x: number, z: number) => number = terrainHeight;

/** Build on another ground (the real-map town's drawn ground). */
export function setArchitectureGround(height: (x: number, z: number) => number = terrainHeight): void {
  groundHeight = height;
}

/** Sample the lowest ground under a rotated footprint. */
function groundUnder(x: number, z: number, w: number, d: number, rotation: number): number {
  let lowest = Infinity;
  const c = Math.cos(rotation), s = Math.sin(rotation);
  for (const [lx, lz] of [[-w / 2, -d / 2], [w / 2, -d / 2], [-w / 2, d / 2], [w / 2, d / 2], [0, 0]]) {
    lowest = Math.min(lowest, groundHeight(x + lx * c + lz * s, z - lx * s + lz * c));
  }
  return lowest;
}

// --- Houses ----------------------------------------------------------------------------------------------------------

export interface HouseSpec {
  x: number;
  z: number;
  w: number;
  d: number;
  storeys: 1 | 2;
  roof: "hip" | "gable";
  pitch: number;
  rotation: number;
  wall: THREE.Color;
  roofColor: THREE.Color;
  trim: THREE.Color;
  porch: boolean;
  hoods: boolean;
  tank: boolean;
  ac: boolean;
  fence: boolean;
  /** Front yard depth to the garden wall (m) and the gate's offset along the front (local x). */
  yard: number;
  gateX: number;
  doorX: number;
  seed: number;
}

const PLINTH = 0.38;
const STOREY = 2.95;

export function houseTopHeight(spec: HouseSpec): number {
  return groundUnder(spec.x, spec.z, spec.w, spec.d, spec.rotation) + PLINTH + spec.storeys * STOREY;
}

/** The porch's width, depth and centre along the front, in the house's frame. */
function porchLayout(spec: HouseSpec): { pw: number; pd: number; px: number } {
  const pw = Math.min(spec.w * 0.62, 4.6);
  return { pw, pd: 2.3, px: THREE.MathUtils.clamp(spec.doorX, -spec.w / 2 + pw / 2, spec.w / 2 - pw / 2) };
}

/** Height of the porch slab or its step at a world point (for someone standing on it), or null off the porch. */
export function porchSurfaceAt(spec: HouseSpec, x: number, z: number): number | null {
  if (!spec.porch) return null;
  const c = Math.cos(spec.rotation), s = Math.sin(spec.rotation);
  const dx = x - spec.x, dz = z - spec.z;
  const lx = dx * c - dz * s, lz = dx * s + dz * c;
  const { pw, pd, px } = porchLayout(spec);
  const base = groundUnder(spec.x, spec.z, spec.w, spec.d, spec.rotation) - 0.04;
  if (Math.abs(lx - px) <= pw / 2 && lz >= spec.d / 2 && lz <= spec.d / 2 + pd) return base + PLINTH;
  if (Math.abs(lx - spec.doorX) <= 0.7 && lz > spec.d / 2 + pd && lz <= spec.d / 2 + pd + 0.5) return base + PLINTH * 0.5;
  return null;
}

export function buildHouse(parts: Parts, spec: HouseSpec): void {
  const random = seeded(spec.seed);
  const base = groundUnder(spec.x, spec.z, spec.w, spec.d, spec.rotation) - 0.04;
  const F = new Frame(parts, M(spec.x, base, spec.z, spec.rotation));
  const { w, d } = spec;
  const P = PLINTH;
  const Hw = spec.storeys * STOREY;
  const eave = P + Hw;

  F.add("concrete", box(w + 0.26, P + 0.6, d + 0.26), PALETTE.plinth, M(0, (P - 0.6) / 2, 0));
  F.add("plaster", worldUV(box(w, Hw, d), 2.2), spec.wall, M(0, P + Hw / 2, 0));
  if (spec.storeys === 2) F.add("trim", box(w + 0.1, 0.16, d + 0.1), spec.trim, M(0, P + STOREY, 0));
  F.add("trim", box(w + 0.06, 0.24, d + 0.06), spec.trim, M(0, eave - 0.12, 0));

  // Facades. Face frames: origin on the wall surface, +z outward.
  const faces = {
    front: (along: number, y: number) => F.child(M(along, y, d / 2)),
    back: (along: number, y: number) => F.child(M(-along, y, -d / 2, Math.PI)),
    right: (along: number, y: number) => F.child(M(w / 2, y, -along, Math.PI / 2)),
    left: (along: number, y: number) => F.child(M(-w / 2, y, along, -Math.PI / 2)),
  };
  const win = (frame: Frame, ww: number, wh: number) => windowItem(frame, ww, wh, { trim: spec.trim, hood: spec.hoods, curtain: random() < 0.4 ? 0.55 + random() * 0.3 : random() * 0.15 });
  for (let storey = 0; storey < spec.storeys; storey += 1) {
    const y = P + storey * STOREY + 1.5;
    if (storey === 0) {
      win(faces.front(spec.doorX > 0 ? -w * 0.22 : w * 0.22, y), Math.min(1.7, w * 0.24), 1.3);
    } else {
      for (const along of [-w * 0.24, w * 0.24]) win(faces.front(along, y), 1.2, 1.3);
    }
    for (const along of [-w * 0.22, w * 0.22]) win(faces.back(along, y), 1.0, 1.2);
    const sideCount = Math.max(1, Math.floor(d / 2.8));
    for (let i = 0; i < sideCount; i += 1) {
      const along = (i - (sideCount - 1) / 2) * (d / sideCount);
      win(faces.right(along, y), 0.9, 1.2);
      win(faces.left(along, y), 0.9, 1.2);
    }
  }
  doorItem(faces.front(spec.doorX, P), spec.trim, random() < 0.5 ? PALETTE.wood : PALETTE.woodLight);

  if (spec.porch) {
    // Covered veranda in front of the door: slab, two slim columns, a shallow lean-to roof.
    const { pw, pd, px } = porchLayout(spec);
    F.add("concrete", box(pw, P, pd), PALETTE.concrete, M(px, P / 2, d / 2 + pd / 2));
    F.add("concrete", box(1.4, P * 0.5, 0.5), PALETTE.concrete, M(spec.doorX, P * 0.25, d / 2 + pd + 0.25));
    for (const side of [-1, 1]) {
      F.add("trim", box(0.17, 2.62, 0.17), spec.trim, M(px + side * (pw / 2 - 0.16), P + 1.31, d / 2 + pd - 0.16));
    }
    F.add("trim", box(pw, 0.16, 0.12), spec.trim, M(px, P + 2.62, d / 2 + pd - 0.16));
    F.add("roof", box(pw + 0.5, 0.11, pd + 0.45, 1.6), spec.roofColor, M(px, P + 2.84, d / 2 + pd / 2 + 0.1, 0, 0.16));
  } else {
    F.add("concrete", box(1.5, P, 0.75), PALETTE.concrete, M(spec.doorX, P / 2, d / 2 + 0.37));
    F.add("trim", box(1.6, 0.09, 0.85), spec.trim, M(spec.doorX, P + 2.42, d / 2 + 0.42));
    for (const side of [-1, 1]) F.add("trim", box(0.05, 0.05, 0.7), spec.trim, M(spec.doorX + side * 0.7, P + 2.3, d / 2 + 0.32, 0, -0.5));
  }

  // Roof.
  const ov = 0.66;
  if (spec.roof === "hip") {
    F.add("roof", hipRoof(w + 2 * ov, d + 2 * ov, spec.pitch, 0.2, 1.6), spec.roofColor, M(0, eave + 0.06, 0));
  } else {
    const { geometry, h, tv } = gableRoof(w + 2 * ov, d + 2 * ov, spec.pitch, 0.14, 1.6);
    const y0 = eave - ov * Math.tan(spec.pitch) + tv + 0.02;
    F.add("roof", geometry, spec.roofColor, M(0, y0, 0));
    F.add("roof", box(w + 2 * ov + 0.04, 0.12, 0.32), spec.roofColor, M(0, y0 + h + 0.02, 0), 0.82);
    const attic = (d / 2) * Math.tan(spec.pitch);
    F.add("plaster", worldUV(prism([[d / 2, 0], [0, attic], [-d / 2, 0]], -w / 2, w / 2), 2.2), spec.wall, M(0, eave, 0));
  }

  if (spec.ac) {
    F.add("metal", box(0.84, 0.56, 0.3), PALETTE.metal, M(w / 2 + 0.2, P + 0.42, -d * 0.18, Math.PI / 2));
    F.add("dark", cylinder(0.19, 0.19, 0.03, 18), PALETTE.metalDark, M(w / 2 + 0.36, P + 0.42, -d * 0.18 + 0.12, 0, 0, Math.PI / 2));
    F.add("concrete", box(0.95, 0.12, 0.45), PALETTE.concrete, M(w / 2 + 0.2, P + 0.08, -d * 0.18));
  }
  if (spec.tank) {
    const tx = -w / 2 - 0.85, tz = -d / 2 + 0.9;
    const stainless = random() < 0.6;
    F.add("concrete", box(1.4, P + 0.25, 1.4), PALETTE.concrete, M(tx, (P + 0.25) / 2 - 0.12, tz));
    F.add(stainless ? "metal" : "trim", new THREE.CylinderGeometry(0.56, 0.56, 1.3, 22).toNonIndexed(), stainless ? PALETTE.metal : new THREE.Color("#d8cdb4"), M(tx, P + 0.13 + 0.65, tz));
    F.add(stainless ? "metal" : "trim", new THREE.SphereGeometry(0.56, 22, 6, 0, Math.PI * 2, 0, Math.PI / 2).toNonIndexed(), stainless ? PALETTE.metal : new THREE.Color("#d8cdb4"), M(tx, P + 0.13 + 1.3, tz, 0, 0, 0), 0.95);
  }

  if (spec.fence) {
    // Garden wall along the front with posts and a gate opening; short returns along the sides.
    const fz = d / 2 + spec.yard;
    const half = w / 2 + 1.3;
    const gate = 3.2;
    const g0 = spec.gateX - gate / 2, g1 = spec.gateX + gate / 2;
    const runs: Array<[number, number]> = [[-half, g0], [g1, half]].filter(([a, b]) => b - a > 0.3) as Array<[number, number]>;
    for (const [a, b] of runs) {
      const len = b - a;
      const cx = (a + b) / 2;
      F.add("plaster", worldUV(box(len, 0.95, 0.16), 2.2), spec.wall, M(cx, 0.475 - 0.1, fz));
      F.add("trim", box(len + 0.04, 0.06, 0.24), spec.trim, M(cx, 0.88, fz));
      const posts = Math.max(2, Math.round(len / 2.4) + 1);
      for (let i = 0; i < posts; i += 1) {
        const px = a + (len * i) / (posts - 1);
        F.add("plaster", worldUV(box(0.3, 1.25, 0.3), 2.2), spec.wall, M(px, 0.62 - 0.1, fz));
        F.add("trim", box(0.38, 0.07, 0.38), spec.trim, M(px, 1.22, fz));
      }
    }
    for (const side of [-1, 1]) {
      const len = spec.yard + 1;
      F.add("plaster", worldUV(box(0.16, 0.95, len), 2.2), spec.wall, M(side * half, 0.375, fz - len / 2));
      F.add("trim", box(0.24, 0.06, len), spec.trim, M(side * half, 0.88, fz - len / 2));
    }
  }
}

/**
 * The neighbourhood's house specs (deterministic). Houses fill the blocks between the side streets: the front row
 * faces the main road, the second row faces the back street, the third row backs onto it.
 */
export function neighbourhoodSpecs(quality: Quality, avoid: (x: number, z: number) => boolean, streets: readonly number[]): HouseSpec[] {
  const random = seeded(11);
  const specs: HouseSpec[] = [];
  const edges = [-86, ...[...streets].sort((a, b) => a - b), 86];
  const rows: Array<{ z: number; fence: number }> = [{ z: -4, fence: 0.9 }, { z: -26.5, fence: 0.7 }, { z: -39, fence: 0 }];
  for (const row of rows) {
    for (let b = 0; b < edges.length - 1; b += 1) {
      const a0 = edges[b] + 2.2 + 0.8, a1 = edges[b + 1] - 2.2 - 0.8;
      const width = a1 - a0;
      const count = Math.floor(width / 11);
      for (let k = 0; k < count; k += 1) {
        const slot = width / count;
        const cx = a0 + (k + 0.5) * slot + (random() - 0.5) * 0.8;
        if (avoid(cx, row.z)) continue;
        if (quality === "low" && random() < 0.3) continue;
        const storeys: 1 | 2 = random() < 0.5 ? 2 : 1;
        const w = Math.min(slot - 3.2, 6.4 + random() * 2.0), d = 5.6 + random() * 1.5;
        const fence = random() < row.fence;
        specs.push({
          x: cx,
          z: row.z + (random() - 0.5) * 1.2,
          w,
          d,
          storeys,
          roof: random() < 0.62 ? "hip" : "gable",
          pitch: THREE.MathUtils.degToRad(24 + random() * 8),
          rotation: (random() - 0.5) * 0.05,
          wall: PALETTE.plaster[Math.floor(random() * PALETTE.plaster.length)],
          roofColor: PALETTE.roof[Math.floor(random() * PALETTE.roof.length)].clone().offsetHSL(0, (random() - 0.5) * 0.04, (random() - 0.5) * 0.04),
          trim: random() < 0.8 ? PALETTE.trim : new THREE.Color("#d9d2c3"),
          porch: random() < 0.45,
          hoods: random() < 0.5,
          tank: random() < 0.55,
          ac: random() < 0.6,
          fence,
          yard: 2.6 + random() * 0.6,
          gateX: (random() - 0.5) * 2,
          doorX: (random() < 0.5 ? -1 : 1) * w * 0.18,
          seed: Math.floor(random() * 1e6),
        });
      }
    }
  }
  return specs;
}

/** The resident's home: a recognisable two-storey house with a porch, its gate where the resident stands. */
export function homeSpec(): HouseSpec {
  return {
    x: LAYOUT.home.x,
    z: LAYOUT.home.z,
    w: 8.2,
    d: 6.6,
    storeys: 2,
    roof: "hip",
    pitch: THREE.MathUtils.degToRad(27),
    rotation: 0,
    wall: new THREE.Color("#efe7d6"),
    roofColor: new THREE.Color("#a35f45"),
    trim: PALETTE.trim,
    porch: true,
    hoods: true,
    tank: true,
    ac: true,
    fence: true,
    yard: 3.0,
    gateX: LAYOUT.resident.x - LAYOUT.home.x,
    doorX: 1.4,
    seed: 4242,
  };
}

// --- Clinic ----------------------------------------------------------------------------------------------------------

function clinicSignTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 160;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#f4f1ea";
  c.fillRect(0, 0, 1024, 160);
  c.fillStyle = "#2e7f5b";
  c.fillRect(34, 30, 100, 100);
  c.fillStyle = "#f4f1ea";
  c.fillRect(70, 44, 28, 72);
  c.fillRect(48, 66, 72, 28);
  c.fillStyle = "#1d2a2b";
  c.font = "600 54px Inter, 'Noto Sans Thai', sans-serif";
  c.fillText("Community Health Clinic", 168, 86);
  c.fillStyle = "#4d6264";
  c.font = "500 30px 'Noto Sans Thai', Inter, sans-serif";
  c.fillText("คลินิกสุขภาพชุมชน · illustrative", 170, 130);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

export interface ClinicBuild {
  group: THREE.Group;
  /** Height of the roof ridge above sea level, for labels. */
  top: number;
}

export function buildClinic(materials: Record<Bucket, THREE.Material>, textures: ArchitectureTextures): ClinicBuild {
  const parts = new Parts();
  const { x, z } = LAYOUT.clinic;
  const w = 16, d = 9, P = 0.62, Hw = 3.5;
  const base = groundUnder(x, z, w, d, 0) - 0.05;
  const F = new Frame(parts, M(x, base, z));
  const wall = new THREE.Color("#f3f0e8");
  const trim = PALETTE.trim;
  const frameMetal = new THREE.Color("#55625f");

  // Raised floor: an essential service kept above typical ponding.
  F.add("concrete", box(w + 0.4, P + 0.6, d + 0.4), PALETTE.plinth, M(0, (P - 0.6) / 2, 0));
  F.add("plaster", worldUV(box(w, Hw, d), 2.2), wall, M(0, P + Hw / 2, 0));
  F.add("trim", box(w + 0.08, 0.28, d + 0.08), PALETTE.tealMuted, M(0, P + Hw - 0.14, 0));
  F.add("trim", box(w + 0.06, 0.5, d + 0.06), new THREE.Color("#c9c4b8"), M(0, P + 0.25, 0));

  const front = (along: number, y: number) => F.child(M(along, y, d / 2));
  const back = (along: number, y: number) => F.child(M(-along, y, -d / 2, Math.PI));
  const side = (s: number, along: number, y: number) => F.child(M(s * w / 2, y, -along * s, s * Math.PI / 2));
  for (const along of [-6.1, -3.7, 3.7, 6.1]) windowItem(front(along, P + 1.7), 1.6, 1.45, { trim, hood: true, curtain: 0.2 });
  for (const along of [-5.5, -1.8, 1.8, 5.5]) windowItem(back(along, P + 1.7), 1.5, 1.3, { trim, hood: false, curtain: 0.15 });
  for (const s of [-1, 1]) for (const along of [-2.2, 2.2]) windowItem(side(s, along, P + 1.7), 1.3, 1.3, { trim, hood: true, curtain: 0.1 });

  // Entrance: glazed doors with aluminium frames under a deep portico.
  const ex = 0;
  F.add("glass", box(2.8, 2.4, 0.04), new THREE.Color("#2a3a40"), M(ex, P + 1.2, d / 2 + 0.02));
  for (const fx of [-1.4, -0.02, 1.4]) F.add("metal", box(0.07, 2.4, 0.08), frameMetal, M(ex + fx, P + 1.2, d / 2 + 0.05));
  F.add("metal", box(2.94, 0.08, 0.08), frameMetal, M(ex, P + 2.42, d / 2 + 0.05));
  F.add("metal", box(2.94, 0.06, 0.08), frameMetal, M(ex, P + 0.03, d / 2 + 0.05));
  F.add("glass", box(2.8, 0.55, 0.04), new THREE.Color("#2a3a40"), M(ex, P + 2.85, d / 2 + 0.02));
  const porchD = 2.8, porchW = 6.4;
  F.add("concrete", box(porchW, P, porchD), PALETTE.concrete, M(ex, P / 2, d / 2 + porchD / 2));
  for (const cx of [-porchW / 2 + 0.25, -1.1, 1.1, porchW / 2 - 0.25]) {
    F.add("trim", cylinder(0.12, 0.13, 3.2, 16), trim, M(ex + cx, P + 1.6, d / 2 + porchD - 0.3));
  }
  F.add("concrete", box(porchW + 0.5, 0.8, porchD + 0.3), new THREE.Color("#eeeae1"), M(ex, P + 3.6, d / 2 + porchD / 2 - 0.1));
  F.add("trim", box(porchW + 0.56, 0.12, porchD + 0.36), PALETTE.tealMuted, M(ex, P + 3.2, d / 2 + porchD / 2 - 0.1));
  // Steps and an accessible ramp with handrails.
  for (let i = 0; i < 3; i += 1) {
    F.add("concrete", box(2.6, (P / 3) * (i + 1), 0.34), PALETTE.concrete, M(ex, ((P / 3) * (i + 1)) / 2, d / 2 + porchD + 0.17 + (2 - i) * 0.34));
  }
  const rampLen = 5.2, rampAngle = Math.atan2(P, rampLen);
  F.add("concrete", box(rampLen, 0.14, 1.3), PALETTE.concrete, M(ex + porchW / 2 + rampLen / 2 - 0.05, P / 2 - 0.05, d / 2 + porchD - 0.75, 0, 0, -rampAngle));
  for (const rz of [-0.6, 0.6]) {
    F.add("metal", box(rampLen + 0.1, 0.04, 0.04), PALETTE.metal, M(ex + porchW / 2 + rampLen / 2, P / 2 + 0.9, d / 2 + porchD - 0.75 + rz, 0, 0, -rampAngle));
    for (let i = 0; i <= 3; i += 1) {
      const t = i / 3;
      const px = ex + porchW / 2 + t * rampLen;
      F.add("metal", cylinder(0.022, 0.022, 0.9, 8), PALETTE.metal, M(px, P * (1 - t) + 0.45, d / 2 + porchD - 0.75 + rz));
    }
  }
  // Gable-end vents on the roof are omitted on purpose: a quiet roofline reads better from the air.
  const group = mergeParts(parts, materials, "Clinic");

  // Standing-seam metal roof (own material) and the sign on the portico fascia.
  const roofMaterial = new THREE.MeshStandardMaterial({ color: "#5d7f7c", map: textures.seam, bumpMap: textures.seam, bumpScale: 1.2, roughness: 0.48, metalness: 0.45 });
  const roof = new THREE.Mesh(hipRoof(w + 1.5, d + 1.5, THREE.MathUtils.degToRad(22), 0.22, 2.5), roofMaterial);
  roof.position.set(x, base + P + Hw + 0.08, z);
  roof.castShadow = roof.receiveShadow = true;
  group.add(roof);
  const sign = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 0.66), new THREE.MeshStandardMaterial({ map: clinicSignTexture(), roughness: 0.6 }));
  sign.position.set(x + ex, base + P + 3.62, z + d / 2 + porchD + 0.06);
  group.add(sign);
  const top = base + P + Hw + 0.08 + ((d + 1.5) / 2) * Math.tan(THREE.MathUtils.degToRad(22));
  return { group, top };
}
