import * as THREE from "three";
import { mergeGeometries, mergeVertices } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { LAYOUT, ROAD_Z, riverZ, terrainHeight } from "@/lib/journey/terrain";

import { contactShadowTexture, fbm, seeded, valueNoise, type Quality } from "./materials";

/**
 * Vegetation: a few well-shaped tree variants (rain tree, round fruit tree, tall tree, coconut palm, shrub) built
 * from clumped, noise-displaced lobes with baked ambient occlusion in vertex colours, instanced with per-instance
 * scale, rotation and tint. Placement follows a clustering noise field and keeps clear of houses, roads and the
 * story's focal points, so trees frame the neighbourhood rather than fill it.
 */

type Variant = "rain" | "round" | "tall" | "palm" | "shrub";

interface VariantGeometry {
  canopy: THREE.BufferGeometry;
  trunk: THREE.BufferGeometry;
  /** Canopy footprint radius at scale 1 (for contact shadows and spacing). */
  radius: number;
}

function noise3(x: number, y: number, z: number, seed: number): number {
  return (valueNoise(x, y, 1 << 20, seed) + valueNoise(y + 31.7, z, 1 << 20, seed + 1) + valueNoise(z + 57.3, x, 1 << 20, seed + 2)) / 3;
}

/** A clump of displaced lobes with smooth normals and baked occlusion (darker underneath and inside). */
function clump(random: () => number, lobes: Array<{ c: THREE.Vector3; r: number }>, detail: number, seed: number, tint = 1): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  for (const lobe of lobes) {
    let g: THREE.BufferGeometry = new THREE.IcosahedronGeometry(lobe.r, detail);
    g.deleteAttribute("normal");
    g.deleteAttribute("uv");
    g = mergeVertices(g);
    const p = g.getAttribute("position") as THREE.BufferAttribute;
    const v = new THREE.Vector3();
    for (let i = 0; i < p.count; i += 1) {
      v.fromBufferAttribute(p, i);
      const dir = v.clone().normalize();
      const wx = v.x + lobe.c.x, wy = v.y + lobe.c.y, wz = v.z + lobe.c.z;
      const coarse = noise3(wx * 0.8, wy * 0.8, wz * 0.8, seed) - 0.5;
      const mid = noise3(wx * 2.1, wy * 2.1, wz * 2.1, seed + 3) - 0.5;
      const fine = noise3(wx * 4.6, wy * 4.6, wz * 4.6, seed + 7) - 0.5;
      v.addScaledVector(dir, lobe.r * (coarse * 0.7 + mid * 0.32 + fine * 0.16));
      // Leaf masses are wider than tall, with flatter undersides.
      v.y *= v.y < 0 ? 0.6 : 0.82;
      p.setXYZ(i, v.x + lobe.c.x, v.y + lobe.c.y, v.z + lobe.c.z);
    }
    parts.push(g);
  }
  const merged = mergeGeometries(parts)!;
  parts.forEach((part) => part.dispose());
  merged.computeVertexNormals();
  merged.computeBoundingBox();
  const box = merged.boundingBox!;
  const centre = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const p = merged.getAttribute("position") as THREE.BufferAttribute;
  const colors = new Float32Array(p.count * 3);
  const v = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 1) {
    v.fromBufferAttribute(p, i);
    const height = (v.y - box.min.y) / Math.max(1e-3, size.y);
    const outward = Math.min(1, Math.hypot(v.x - centre.x, v.z - centre.z) / Math.max(1e-3, Math.max(size.x, size.z) / 2));
    const ao = 0.42 + 0.48 * Math.pow(height, 0.8) + 0.16 * outward;
    const speckle = 0.94 + random() * 0.1;
    const warm = height * 0.06; // sunlit tops slightly warmer
    colors[i * 3] = Math.min(1.2, ao * speckle * (1 + warm)) * tint;
    colors[i * 3 + 1] = Math.min(1.2, ao * speckle) * tint;
    colors[i * 3 + 2] = Math.min(1.2, ao * speckle * (1 - warm)) * tint;
  }
  merged.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return merged;
}

/** A tapered limb from a to b. */
function limb(a: THREE.Vector3, b: THREE.Vector3, r0: number, r1: number, segments = 7): THREE.BufferGeometry {
  const length = a.distanceTo(b);
  const g = new THREE.CylinderGeometry(r1, r0, length, segments, 3);
  // A gentle flare at the base so trunks meet the ground convincingly.
  const p = g.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i += 1) {
    const t = (p.getY(i) + length / 2) / length;
    const flare = 1 + 0.5 * Math.max(0, 1 - t * 6);
    p.setX(i, p.getX(i) * flare);
    p.setZ(i, p.getZ(i) * flare);
  }
  g.translate(0, length / 2, 0);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize()));
  g.translate(a.x, a.y, a.z);
  g.deleteAttribute("uv");
  return g;
}

function broadleaf(kind: "rain" | "round" | "tall" | "shrub", detail: number, seed: number): VariantGeometry {
  const random = seeded(seed);
  const lobes: Array<{ c: THREE.Vector3; r: number }> = [];
  const limbs: THREE.BufferGeometry[] = [];
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);
  if (kind === "shrub") {
    for (let i = 0; i < 5; i += 1) {
      const a = (i / 5) * Math.PI * 2 + random();
      lobes.push({ c: v(Math.cos(a) * 0.42, 0.45 + random() * 0.25, Math.sin(a) * 0.42), r: 0.42 + random() * 0.18 });
    }
    lobes.push({ c: v(0, 0.75, 0), r: 0.5 });
    return { canopy: clump(random, lobes, detail, seed), trunk: limb(v(0, 0, 0), v(0, 0.3, 0), 0.04, 0.03, 5), radius: 1.1 };
  }
  const spec = {
    rain: { trunk: 2.9, height: 5.4, spread: 3.4, r: 2.0, n: 11, flat: 0.38 },
    round: { trunk: 1.8, height: 3.7, spread: 1.45, r: 1.45, n: 8, flat: 0.75 },
    tall: { trunk: 3.2, height: 6.2, spread: 1.0, r: 1.25, n: 8, flat: 1.9 },
  }[kind];
  const top = v(0, spec.trunk, 0);
  limbs.push(limb(v(0, -0.3, 0), top, kind === "rain" ? 0.34 : 0.22, kind === "rain" ? 0.24 : 0.15));
  const crown = v(0, spec.height, 0);
  for (let i = 0; i < spec.n; i += 1) {
    const a = (i / spec.n) * Math.PI * 2 + random() * 0.6;
    const d = spec.spread * (0.45 + random() * 0.55);
    const c = crown.clone().add(v(Math.cos(a) * d, (random() - 0.4) * spec.r * spec.flat, Math.sin(a) * d));
    lobes.push({ c, r: spec.r * (0.7 + random() * 0.4) });
    if (i % 2 === 0) limbs.push(limb(top, top.clone().lerp(c, 0.72), kind === "rain" ? 0.17 : 0.1, 0.05));
  }
  lobes.push({ c: crown.clone().add(v(0, spec.r * 0.35 * spec.flat, 0)), r: spec.r * 1.05 });
  const trunk = mergeGeometries(limbs)!;
  limbs.forEach((g) => g.dispose());
  return { canopy: clump(random, lobes, detail, seed), trunk, radius: spec.spread + spec.r * 0.8 };
}

/** Coconut palm: a gently curved trunk and arching, folded fronds. */
function palm(seed: number): VariantGeometry {
  const random = seeded(seed);
  const height = 7.2;
  const lean = new THREE.Vector3(0.9, 0, 0.3);
  const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(0, -0.3, 0), new THREE.Vector3(lean.x * 0.2, height * 0.55, lean.z * 0.2), new THREE.Vector3(lean.x, height, lean.z));
  const trunkPieces: THREE.BufferGeometry[] = [];
  const tube = new THREE.TubeGeometry(curve, 24, 0.17, 7, false);
  // Taper and ring the trunk.
  const p = tube.getAttribute("position") as THREE.BufferAttribute;
  const centre = new THREE.Vector3(), point = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 1) {
    const ring = Math.floor(i / 8);
    const t = ring / 24;
    curve.getPoint(t, centre);
    point.fromBufferAttribute(p, i).sub(centre);
    const scale = (1.25 - 0.45 * t) * (1 + 0.06 * Math.sin(t * 90));
    point.multiplyScalar(scale).add(centre);
    p.setXYZ(i, point.x, point.y, point.z);
  }
  tube.deleteAttribute("uv");
  trunkPieces.push(tube);
  const head = curve.getPoint(1);
  const fronds: THREE.BufferGeometry[] = [];
  const count = 11;
  for (let i = 0; i < count; i += 1) {
    const a = (i / count) * Math.PI * 2 + random() * 0.4;
    const length = 3.3 + random() * 0.8;
    const droop = 0.5 + random() * 0.5;
    const segments = 10;
    const positions: number[] = [];
    const indices: number[] = [];
    for (let s = 0; s <= segments; s += 1) {
      const t = s / segments;
      const r = length * t;
      const y = Math.sin(t * Math.PI * 0.55) * 1.0 - droop * t * t * 2.6;
      const half = 0.62 * Math.sin(Math.min(1, t * 1.4) * Math.PI * 0.9) * (1 - t * 0.35);
      const cx = Math.cos(a) * r, cz = Math.sin(a) * r;
      const sx = -Math.sin(a) * half, sz = Math.cos(a) * half;
      // Folded (V) cross-section: the edges sit lower than the rib.
      positions.push(head.x + cx - sx, head.y + y - half * 0.35, head.z + cz - sz);
      positions.push(head.x + cx, head.y + y + 0.02, head.z + cz);
      positions.push(head.x + cx + sx, head.y + y - half * 0.35, head.z + cz + sz);
      if (s < segments) {
        const b = s * 3;
        indices.push(b, b + 3, b + 1, b + 1, b + 3, b + 4, b + 1, b + 4, b + 2, b + 2, b + 4, b + 5);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    g.setIndex(indices);
    fronds.push(g.toNonIndexed());
  }
  for (let i = 0; i < 4; i += 1) {
    const nut = new THREE.SphereGeometry(0.14, 8, 6);
    nut.deleteAttribute("uv");
    const a = (i / 4) * Math.PI * 2;
    nut.translate(head.x + Math.cos(a) * 0.2, head.y - 0.25, head.z + Math.sin(a) * 0.2);
    trunkPieces.push(nut.toNonIndexed());
  }
  const canopy = mergeGeometries(fronds.map((g) => { g.computeVertexNormals(); return g; }))!;
  fronds.forEach((g) => g.dispose());
  // Baked tone: darker toward the frond base.
  const cp = canopy.getAttribute("position") as THREE.BufferAttribute;
  const colors = new Float32Array(cp.count * 3);
  for (let i = 0; i < cp.count; i += 1) {
    const d = Math.hypot(cp.getX(i) - head.x, cp.getZ(i) - head.z) / 3.5;
    const shade = 0.55 + 0.5 * Math.min(1, d);
    colors[i * 3] = colors[i * 3 + 1] = colors[i * 3 + 2] = shade;
  }
  canopy.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  const trunk = mergeGeometries(trunkPieces.map((g) => (g.index ? g.toNonIndexed() : g)))!;
  trunk.computeVertexNormals();
  return { canopy, trunk, radius: 3.4 };
}

// --- Placement -------------------------------------------------------------------------------------------------------

export interface Footprint { x: number; z: number; w: number; d: number }

export interface VegetationOptions {
  quality: Quality;
  /** Building footprints (with yards) to keep clear. */
  footprints: Footprint[];
  /** Camera positions along the story; trees that would block or brush the camera are left out. */
  clearance?: THREE.Vector3[];
}

const VARIANT_SIZE: Record<Variant, { radius: number; height: number }> = {
  rain: { radius: 5.0, height: 7.8 },
  round: { radius: 2.8, height: 5.8 },
  tall: { radius: 2.2, height: 8.6 },
  palm: { radius: 3.6, height: 8.2 },
  shrub: { radius: 1.0, height: 1.4 },
};

function blocksCamera(clearance: THREE.Vector3[] | undefined, variant: Variant, x: number, z: number, s: number): boolean {
  if (!clearance) return false;
  const { radius, height } = VARIANT_SIZE[variant];
  const r = radius * s + 3, h = height * s + 3;
  return clearance.some((c) => c.y < h && (c.x - x) ** 2 + (c.z - z) ** 2 < r * r);
}

interface Placement { variant: Variant; x: number; z: number; s: number; r: number; tint: number }

const GREENS = ["#6b8748", "#5c7a43", "#78904f", "#647f47", "#83975a", "#58733f", "#8a9a5b", "#4f6b3d", "#76884a"].map((c) => new THREE.Color(c));
const PALM_GREEN = new THREE.Color("#7f9650");

function onRoad(x: number, z: number, margin: number): boolean {
  if (Math.abs(z - ROAD_Z) < 6 + margin) return true;
  if (Math.abs(z + 16) < 3 + margin && x > -60 && x < 64) return true;
  for (const sx of [-46, -30, -14, 18, 34, 50]) if (Math.abs(x - sx) < 3 + margin && z < ROAD_Z && z > -46) return true;
  if (Math.abs(x - LAYOUT.operations.x) < 3.5 + margin && z < -16 && z > LAYOUT.operations.z) return true;
  return false;
}

function insideFootprint(footprints: Footprint[], x: number, z: number, margin: number): boolean {
  return footprints.some((f) => Math.abs(x - f.x) < f.w / 2 + margin && Math.abs(z - f.z) < f.d / 2 + margin);
}

function plan(options: VegetationOptions): Placement[] {
  const all = planAll(options);
  return all.filter((p) => !blocksCamera(options.clearance, p.variant, p.x, p.z, p.s));
}

function planAll(options: VegetationOptions): Placement[] {
  const random = seeded(23);
  const out: Placement[] = [];
  const high = options.quality === "high";
  const tooClose = (x: number, z: number, spacing: number) => out.some((p) => p.variant !== "shrub" && (p.x - x) ** 2 + (p.z - z) ** 2 < spacing * spacing);
  const pick = (): Variant => {
    const r = random();
    return r < 0.12 ? "rain" : r < 0.72 ? "round" : "tall";
  };
  // Hand-placed trees that frame the story's places (a mango tree by the home, a rain tree beside the clinic).
  out.push({ variant: "round", x: LAYOUT.home.x - 7.4, z: LAYOUT.home.z + 2.2, s: 1.05, r: 0.6, tint: 1 });
  out.push({ variant: "palm", x: LAYOUT.home.x + 6.2, z: LAYOUT.home.z - 3.4, s: 0.95, r: 2.2, tint: 1 });
  out.push({ variant: "rain", x: LAYOUT.clinic.x + 13, z: LAYOUT.clinic.z - 2, s: 1, r: 1.1, tint: 1 });
  out.push({ variant: "round", x: LAYOUT.clinic.x - 11, z: LAYOUT.clinic.z + 1, s: 0.9, r: 4.1, tint: 1 });
  for (const [x, z] of [[-29.6, 1.3], [-27.8, 1.6], [-18.6, 1.4], [20.6, 1.4], [31.4, 1.2], [33, 1.4]]) {
    out.push({ variant: "shrub", x, z, s: 0.8 + random() * 0.4, r: random() * 6, tint: 0.95 + random() * 0.1 });
  }

  // Woodland and gardens from a clustering noise field.
  const target = high ? 330 : 150;
  let guard = 0;
  let trees = 0;
  while (trees < target && guard < target * 60) {
    guard += 1;
    const x = (random() - 0.5) * 260, z = -125 + random() * 190;
    const y = terrainHeight(x, z);
    if (y < 0.5) continue;
    if (onRoad(x, z, 1.5)) continue;
    if (insideFootprint(options.footprints, x, z, 1.2)) continue;
    const density = fbm(x / 34, z / 34, 3, 1 << 20, 5);
    const inTown = z > -46 && z < 6 && Math.abs(x) < 72;
    const threshold = inTown ? 0.6 : z < -50 ? 0.34 : 0.52;
    if (density < threshold || random() > (inTown ? 0.55 : 0.92)) continue;
    // Keep the story's sight lines clear.
    if (Math.hypot(x - LAYOUT.resident.x, z - LAYOUT.resident.z) < 9) continue;
    if (Math.abs(x - 2) < 9 && z > -6 && z < 20) continue;
    const variant = pick();
    const forest = z < -50;
    const spacing = variant === "rain" ? 9 : forest ? 3.4 : 4.4;
    if (tooClose(x, z, spacing)) continue;
    const s = forest ? 1.0 + random() * 0.6 : 0.7 + random() * 0.6;
    out.push({ variant, x, z, s, r: random() * Math.PI * 2, tint: (forest ? 0.82 : 0.9) + random() * 0.2 });
    trees += 1;
  }

  // Riparian trees and palms along the channel banks and field edges.
  for (let x = -130; x <= 130; x += high ? 7 : 12) {
    const rz = riverZ(x);
    for (const side of [-1, 1]) {
      if (random() < 0.45) continue;
      const z = rz + side * (8.5 + random() * 4);
      if (terrainHeight(x, z) < -0.2) continue;
      if (Math.abs(x - 2) < 10 && side < 0) continue;
      out.push({ variant: random() < 0.45 ? "palm" : "round", x: x + (random() - 0.5) * 3, z, s: 0.75 + random() * 0.4, r: random() * 6, tint: 0.95 + random() * 0.1 });
    }
  }
  for (let i = 0; i < (high ? 26 : 12); i += 1) {
    const x = (random() - 0.5) * 230;
    const z = 17 + random() * 7;
    if (Math.abs(x - 2) < 12) continue;
    out.push({ variant: "palm", x, z, s: 0.85 + random() * 0.3, r: random() * 6, tint: 1 });
  }

  // Shrubs along garden walls and verges.
  for (let i = 0; i < (high ? 220 : 90); i += 1) {
    const x = (random() - 0.5) * 150, z = -44 + random() * 50;
    if (onRoad(x, z, 0.3) || insideFootprint(options.footprints, x, z, 0.2)) continue;
    if (!insideFootprint(options.footprints, x, z, 2.2)) continue; // near buildings only
    if (Math.hypot(x - LAYOUT.resident.x, z - LAYOUT.resident.z) < 3) continue;
    out.push({ variant: "shrub", x, z, s: 0.6 + random() * 0.7, r: random() * 6, tint: 0.9 + random() * 0.2 });
  }
  return out;
}

export interface Vegetation {
  group: THREE.Group;
  dispose(): void;
}

/** Banana plants: a short pseudo-stem and a few long, arching paddle leaves. */
function banana(seed: number): VariantGeometry {
  const random = seeded(seed);
  const stem = limb(new THREE.Vector3(0, -0.2, 0), new THREE.Vector3(0.05, 1.7, 0), 0.13, 0.1, 7);
  const leaves: THREE.BufferGeometry[] = [];
  const count = 7;
  for (let i = 0; i < count; i += 1) {
    const a = (i / count) * Math.PI * 2 + random() * 0.5;
    const length = 1.7 + random() * 0.6;
    const positions: number[] = [];
    const indices: number[] = [];
    const segments = 8;
    for (let s = 0; s <= segments; s += 1) {
      const t = s / segments;
      const r = length * t;
      const y = 1.7 + Math.sin(t * Math.PI * 0.6) * 0.8 - t * t * 1.1;
      const half = 0.32 * Math.sin(Math.min(1, t * 1.2) * Math.PI * 0.95);
      const cx = Math.cos(a) * r, cz = Math.sin(a) * r;
      const sx = -Math.sin(a) * half, sz = Math.cos(a) * half;
      positions.push(cx - sx, y - half * 0.15, cz - sz, cx, y + 0.03, cz, cx + sx, y - half * 0.15, cz + sz);
      if (s < segments) {
        const b = s * 3;
        indices.push(b, b + 3, b + 1, b + 1, b + 3, b + 4, b + 1, b + 4, b + 2, b + 2, b + 4, b + 5);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    g.setIndex(indices);
    const flat = g.toNonIndexed();
    flat.computeVertexNormals();
    leaves.push(flat);
  }
  const canopy = mergeGeometries(leaves)!;
  leaves.forEach((g) => g.dispose());
  const cp = canopy.getAttribute("position") as THREE.BufferAttribute;
  const colors = new Float32Array(cp.count * 3);
  for (let i = 0; i < cp.count; i += 1) {
    const shade = 0.75 + 0.35 * Math.min(1, Math.hypot(cp.getX(i), cp.getZ(i)) / 2);
    colors[i * 3] = shade * 1.05; colors[i * 3 + 1] = shade * 1.1; colors[i * 3 + 2] = shade * 0.8;
  }
  canopy.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return { canopy, trunk: stem, radius: 1.8 };
}

export interface TreePlacement {
  x: number;
  z: number;
  /** 0 broadleaf, 1 coconut palm, 2 banana, 3 mango or rain tree (the bake's kinds). */
  kind: number;
  scale: number;
}

export interface TreeOptions {
  quality: Quality;
  trees: TreePlacement[];
  height: (x: number, z: number) => number;
  /** Camera positions along the story; trees that would block or brush the camera are left out. */
  clearance?: THREE.Vector3[];
  /** Full-detail canopies only near these points (the story's close shots). */
  focus: Array<{ x: number; z: number; r: number }>;
}

/** Trees at the bake's points (real open ground of the town), instanced per variant and per 48 m tile. */
export function buildTrees(options: TreeOptions): Vegetation {
  const detail = options.quality === "high" ? 2 : 1;
  const variants: Record<string, VariantGeometry> = {
    round: broadleaf("round", detail, 202),
    rain: broadleaf("rain", detail, 101),
    palm: palm(404),
    banana: banana(606),
  };
  const far: Record<string, VariantGeometry> = { round: broadleaf("round", 1, 202), rain: broadleaf("rain", 1, 101) };
  const kindVariant = ["round", "palm", "banana", "rain"];
  const group = new THREE.Group();
  group.name = "Trees";
  const foliage = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0 });
  const fronds = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, side: THREE.DoubleSide });
  const bark = new THREE.MeshStandardMaterial({ color: "#6e5d4b", roughness: 0.92 });
  const palmBark = new THREE.MeshStandardMaterial({ color: "#8d7d68", roughness: 0.9 });
  const random = seeded(29);
  const tiles = new Map<string, Array<{ p: TreePlacement; r: number; tint: number }>>();
  for (const p of options.trees) {
    const variant = kindVariant[p.kind] ?? "round";
    const size = VARIANT_SIZE[(variant === "banana" ? "shrub" : variant) as Variant];
    if (options.clearance) {
      const r = (variant === "banana" ? 2 : size.radius) * p.scale + 3, h = (variant === "banana" ? 3.4 : size.height) * p.scale + 3;
      if (options.clearance.some((c) => c.y < h + options.height(p.x, p.z) && (c.x - p.x) ** 2 + (c.z - p.z) ** 2 < r * r)) continue;
    }
    const key = `${variant}:${Math.floor(p.x / 48)}:${Math.floor(p.z / 48)}`;
    if (!tiles.has(key)) tiles.set(key, []);
    tiles.get(key)!.push({ p, r: random() * Math.PI * 2, tint: 0.88 + random() * 0.24 });
  }
  const matrix = new THREE.Matrix4(), color = new THREE.Color(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  tiles.forEach((list, key) => {
    const [variant, tx, tz] = key.split(":");
    const cx = (Number(tx) + 0.5) * 48, cz = (Number(tz) + 0.5) * 48;
    const near = options.focus.some((f) => Math.hypot(f.x - cx, f.z - cz) < f.r);
    const geo = (!near ? far[variant] : undefined) ?? variants[variant];
    const leafy = variant === "palm" || variant === "banana";
    const canopy = new THREE.InstancedMesh(geo.canopy, leafy ? fronds : foliage, list.length);
    const trunk = new THREE.InstancedMesh(geo.trunk, variant === "palm" ? palmBark : bark, list.length);
    list.forEach(({ p, r, tint }, i) => {
      const y = options.height(p.x, p.z);
      matrix.compose(new THREE.Vector3(p.x, y - 0.05, p.z), q.setFromAxisAngle(up, r), new THREE.Vector3(p.scale, p.scale * (0.92 + ((i * 7919) % 13) / 60), p.scale));
      canopy.setMatrixAt(i, matrix);
      trunk.setMatrixAt(i, matrix);
      const base = leafy ? (variant === "banana" ? BANANA_GREEN : PALM_GREEN) : GREENS[(i * 5 + Math.floor(r * 10)) % GREENS.length];
      color.copy(base).multiplyScalar(tint);
      canopy.setColorAt(i, color);
    });
    canopy.castShadow = trunk.castShadow = near;
    canopy.receiveShadow = trunk.receiveShadow = true;
    canopy.computeBoundingSphere();
    trunk.computeBoundingSphere();
    canopy.name = `Canopy-${key}`;
    group.add(canopy, trunk);
  });
  return {
    group,
    dispose() {
      [...Object.values(variants), ...Object.values(far)].forEach((v) => { v.canopy.dispose(); v.trunk.dispose(); });
      [foliage, fronds, bark, palmBark].forEach((m) => m.dispose());
    },
  };
}

const BANANA_GREEN = new THREE.Color("#86a64e");

export function buildVegetation(options: VegetationOptions): Vegetation {
  const detail = options.quality === "high" ? 2 : 1;
  const variants: Record<Variant, VariantGeometry> = {
    rain: broadleaf("rain", detail, 101),
    round: broadleaf("round", detail, 202),
    tall: broadleaf("tall", detail, 303),
    palm: palm(404),
    shrub: broadleaf("shrub", 1, 505),
  };
  // The distant hill forest uses lighter canopies (same seeds and silhouettes, fewer triangles) and casts no shadow.
  const far: Partial<Record<Variant, VariantGeometry>> = detail > 1 ? {
    rain: broadleaf("rain", 1, 101),
    round: broadleaf("round", 1, 202),
    tall: broadleaf("tall", 1, 303),
  } : {};
  const placements = plan(options);
  const group = new THREE.Group();
  group.name = "Vegetation";
  const foliage = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.88, metalness: 0 });
  const fronds = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, side: THREE.DoubleSide });
  const bark = new THREE.MeshStandardMaterial({ color: "#6e5d4b", roughness: 0.92 });
  const palmBark = new THREE.MeshStandardMaterial({ color: "#8d7d68", roughness: 0.9 });
  const shadowTexture = contactShadowTexture(0.08, 0.4);
  const shadowMaterial = new THREE.MeshBasicMaterial({ color: "#1a2216", alphaMap: shadowTexture, transparent: true, opacity: 0.42, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const matrix = new THREE.Matrix4(), color = new THREE.Color(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0);
  const shadowPlacements: Array<{ x: number; z: number; r: number }> = [];

  const TILE = 48;
  const tiles = new Map<string, Placement[]>();
  for (const p of placements) {
    const key = `${p.variant}:${Math.floor(p.x / TILE)}:${Math.floor(p.z / TILE)}`;
    if (!tiles.has(key)) tiles.set(key, []);
    tiles.get(key)!.push(p);
  }
  tiles.forEach((list, key) => {
    const variant = key.split(":")[0] as Variant;
    const distant = list.every((p) => p.z < -52);
    // Full-detail canopies only in and around the town, where the camera comes close.
    const nearTown = list.some((p) => Math.abs(p.x) < 64 && p.z > -46 && p.z < 26);
    const geo = (!nearTown ? far[variant] : undefined) ?? variants[variant];
    const canopy = new THREE.InstancedMesh(geo.canopy, variant === "palm" ? fronds : foliage, list.length);
    const trunk = new THREE.InstancedMesh(geo.trunk, variant === "palm" ? palmBark : bark, list.length);
    list.forEach((p, i) => {
      const y = terrainHeight(p.x, p.z);
      const sy = p.s * (0.92 + ((i * 7919) % 13) / 60);
      matrix.compose(new THREE.Vector3(p.x, y - 0.05, p.z), q.setFromAxisAngle(up, p.r), new THREE.Vector3(p.s, sy, p.s));
      canopy.setMatrixAt(i, matrix);
      trunk.setMatrixAt(i, matrix);
      const base = variant === "palm" ? PALM_GREEN : GREENS[(i * 5 + Math.floor(p.r * 10)) % GREENS.length];
      color.copy(base).multiplyScalar(p.tint).offsetHSL((p.tint - 1) * 0.08, 0, 0);
      canopy.setColorAt(i, color);
      shadowPlacements.push({ x: p.x, z: p.z, r: geo.radius * p.s * (variant === "shrub" ? 0.9 : 0.75) });
    });
    canopy.castShadow = trunk.castShadow = !distant;
    canopy.receiveShadow = trunk.receiveShadow = true;
    // Per-tile bounds make frustum culling work (an instanced mesh is culled as a whole).
    canopy.computeBoundingSphere();
    trunk.computeBoundingSphere();
    canopy.name = `Canopy-${key}`;
    group.add(canopy, trunk);
  });

  // Soft contact shadows, tilted to the ground slope.
  const plane = new THREE.PlaneGeometry(1, 1);
  plane.rotateX(-Math.PI / 2);
  const contacts = new THREE.InstancedMesh(plane, shadowMaterial, shadowPlacements.length);
  const normal = new THREE.Vector3();
  shadowPlacements.forEach((s, i) => {
    const e = 0.5;
    normal.set(terrainHeight(s.x - e, s.z) - terrainHeight(s.x + e, s.z), 2 * e, terrainHeight(s.x, s.z - e) - terrainHeight(s.x, s.z + e)).normalize();
    q.setFromUnitVectors(up, normal);
    matrix.compose(new THREE.Vector3(s.x, terrainHeight(s.x, s.z) + 0.04, s.z), q, new THREE.Vector3(s.r * 2.2, 1, s.r * 2.2));
    contacts.setMatrixAt(i, matrix);
  });
  contacts.renderOrder = 1;
  contacts.name = "TreeContactShadows";
  group.add(contacts);

  return {
    group,
    dispose() {
      [...Object.values(variants), ...Object.values(far)].forEach((v) => { v.canopy.dispose(); v.trunk.dispose(); });
      plane.dispose();
      [foliage, fronds, bark, palmBark, shadowMaterial].forEach((m) => m.dispose());
      shadowTexture.dispose();
    },
  };
}
