import * as THREE from "three";

import { COVER, FloodField, type TownBuilding, type TownPack, type TownRoad } from "@/lib/journey/town-data";

import { buildFacadeAtlas, type FacadeAtlas } from "./facade-atlas";
import { asphaltTexture, concreteTexture, groundDetailTexture, rippleNormalTexture, seamRoofTexture, seeded, type Quality } from "./materials";
import {
  FACADE,
  FACADE_STOREY,
  createTownUniforms,
  facadeMaterial,
  groundMaterial,
  roadMaterial,
  roofMaterial,
  waterMaterial,
  type TownUniforms,
} from "./town-materials";

/**
 * The real-map town: Mae Sai around the Public app's example home, built from the bake (`public/journey/town/`).
 * Outlines are real (open building outlines); heights, roofs and facades are illustrative, chosen from the outline's
 * size, shape and street. Ground and water follow the replay's cells (see FloodField). Built once, merged per material
 * and per 300 m tile so frustum culling works.
 */

const TILE = 300;

export interface Town {
  group: THREE.Group;
  uniforms: TownUniforms;
  field: FloodField;
  /** Where the story's places are (at about roof height, for labels). */
  anchors: Record<"home" | "neighbour" | "shelter" | "office" | "wat" | "river" | "cut", THREE.Vector3>;
  /** Lalita's home: the outline's box, facing its street (the stage builds the detailed house there). */
  home: { x: number; z: number; w: number; d: number; rotation: number; yard: number; ground: number };
  /** Where the operations room stands, in the District Office's outline. */
  office: { x: number; z: number; ground: number };
  route: RouteBand;
  lamps: Lamps;
  /** The route's first edge to close (for its label), and the stage it closes at. */
  firstCut: { point: THREE.Vector3; stage: number };
  dispose(): void;
}

// --- Helpers ---------------------------------------------------------------------------------------------------------------

function ringArea(ring: Float32Array): number {
  let area = 0;
  const n = ring.length / 2;
  for (let i = 0; i < n; i += 1) {
    const j = (i + 1) % n;
    area += ring[i * 2] * ring[j * 2 + 1] - ring[j * 2] * ring[i * 2 + 1];
  }
  return area / 2;
}

/** Reverse a ring in place when needed so its signed area is positive (walls then face out); returns the new front. */
function orient(ring: Float32Array, front: number): number {
  if (ringArea(ring) > 0) return front;
  const n = ring.length / 2;
  for (let i = 0; i < Math.floor(n / 2); i += 1) {
    const j = n - 1 - i;
    const x = ring[i * 2], z = ring[i * 2 + 1];
    ring[i * 2] = ring[j * 2];
    ring[i * 2 + 1] = ring[j * 2 + 1];
    ring[j * 2] = x;
    ring[j * 2 + 1] = z;
  }
  return (((n - 2 - front) % n) + n) % n;
}

class Buffers {
  position: number[] = [];
  normal: number[] = [];
  color: number[] = [];
  uv: number[] = [];
  extra: Record<string, { size: number; data: number[] }> = {};
  index: number[] = [];
  get count(): number {
    return this.position.length / 3;
  }
  attr(name: string, size: number, ...values: number[]): void {
    (this.extra[name] ??= { size, data: [] }).data.push(...values);
  }
  geometry(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.position, 3));
    if (this.normal.length) g.setAttribute("normal", new THREE.Float32BufferAttribute(this.normal, 3));
    if (this.color.length) g.setAttribute("color", new THREE.Float32BufferAttribute(this.color, 3));
    if (this.uv.length) g.setAttribute("uv", new THREE.Float32BufferAttribute(this.uv, 2));
    for (const [name, { size, data }] of Object.entries(this.extra)) g.setAttribute(name, new THREE.Float32BufferAttribute(data, size));
    if (this.index.length) g.setIndex(this.index);
    if (!this.normal.length) g.computeVertexNormals();
    g.computeBoundingSphere();
    return g;
  }
}

const PLASTER = ["#e9e0cc", "#ece0b8", "#d3dfcc", "#e8cdb8", "#d0dce2", "#eeebe4", "#d8d3ca", "#ecd5bf", "#d6e0c4", "#e2d8c4"].map((c) => new THREE.Color(c));
// Mostly grey and faded corrugated metal, as in a northern Thai town; some blue, green and red sheets.
const METAL_ROOF = ["#8b908f", "#7d8584", "#9a9893", "#5f7486", "#8f5a46", "#5e7564", "#a0a3a0", "#7a6a58", "#6f7b80"].map((c) => new THREE.Color(c));
const TILE_ROOF = ["#a85f42", "#9c5a40", "#8f5843"].map((c) => new THREE.Color(c));
const FLAT_ROOF = ["#b8b3a8", "#a9a59b", "#c2bdb1", "#9f9b92"].map((c) => new THREE.Color(c));

function pick<T>(list: readonly T[], seed: number): T {
  return list[Math.abs(Math.floor(seed)) % list.length];
}

/** Facade type of a building's wall: its front gets the kind's face, the others its sides. */
function facadeFor(building: TownBuilding, isFront: boolean): number {
  switch (building.kind) {
    case "shophouse": return isFront ? FACADE.shopFront : FACADE.shopSide;
    case "house": return FACADE.house;
    case "large": return building.index % 3 === 0 ? FACADE.largeMetal : FACADE.largePlaster;
    case "market": return FACADE.largeMetal;
    case "shed": return FACADE.shed;
    case "temple": return FACADE.temple;
    case "government": return FACADE.government;
    case "school": return FACADE.school;
  }
}

function roofStyle(building: TownBuilding): "flat" | "hip" | "gable" | "temple" {
  if (building.kind === "temple") return building.area > 120 ? "temple" : "gable";
  if (building.kind === "shed") return "gable";
  if (building.kind === "house" && building.rect > 0.78 && building.area < 360) return building.index % 3 === 0 ? "gable" : "hip";
  if ((building.kind === "large" || building.kind === "market") && building.rect > 0.8) return "gable";
  if (building.kind === "government" && building.rect > 0.8) return "hip";
  return "flat";
}

// --- Buildings -----------------------------------------------------------------------------------------------------------

interface TileParts {
  walls: Buffers;
  pitched: Buffers;
  flat: Buffers;
  details: Buffers;
}

function addWall(walls: Buffers, ax: number, az: number, bx: number, bz: number, bottom: number, top: number, base: number, u0: number, facade: number, seed: number, storeys: number, tint: THREE.Color, inward = false): void {
  const dx = bx - ax, dz = bz - az;
  const length = Math.hypot(dx, dz);
  if (length < 0.05) return;
  let nx = dz / length, nz = -dx / length;
  if (inward) { nx = -nx; nz = -nz; }
  const i = walls.count;
  const corners: Array<[number, number, number, number]> = [[ax, bottom, az, u0], [ax, top, az, u0], [bx, bottom, bz, u0 + length], [bx, top, bz, u0 + length]];
  for (const [x, y, z, u] of corners) {
    walls.position.push(x, y, z);
    walls.normal.push(nx, 0, nz);
    walls.color.push(tint.r, tint.g, tint.b);
    walls.attr("aWall", 4, u, facade, seed, storeys);
    walls.attr("aBase", 1, base);
  }
  // (a_bottom, a_top, b_bottom), (b_bottom, a_top, b_top) face +n; reversed for an inner face.
  if (inward) walls.index.push(i, i + 2, i + 1, i + 2, i + 3, i + 1);
  else walls.index.push(i, i + 1, i + 2, i + 2, i + 1, i + 3);
}

function addCap(target: Buffers, ring: Float32Array, y: number, color: THREE.Color, uvScale: number): void {
  const n = ring.length / 2;
  const contour: THREE.Vector2[] = [];
  for (let i = 0; i < n; i += 1) contour.push(new THREE.Vector2(ring[i * 2], ring[i * 2 + 1]));
  const faces = THREE.ShapeUtils.triangulateShape(contour, []);
  const i0 = target.count;
  for (let i = 0; i < n; i += 1) {
    target.position.push(ring[i * 2], y, ring[i * 2 + 1]);
    target.normal.push(0, 1, 0);
    target.color.push(color.r, color.g, color.b);
    target.uv.push(ring[i * 2] * uvScale, ring[i * 2 + 1] * uvScale);
  }
  for (const [a, b, c] of faces) {
    const ax = ring[a * 2], az = ring[a * 2 + 1];
    const cross = (ring[b * 2 + 1] - az) * (ring[c * 2] - ax) - (ring[b * 2] - ax) * (ring[c * 2 + 1] - az);
    if (cross >= 0) target.index.push(i0 + a, i0 + b, i0 + c);
    else target.index.push(i0 + a, i0 + c, i0 + b);
  }
}

function pushTri(target: Buffers, a: THREE.Vector3, b: THREE.Vector3, c: THREE.Vector3, color: THREE.Color, uvScale: number, uvAxis?: THREE.Vector2): void {
  const n = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a));
  if (n.y < 0 || (n.y === 0 && n.lengthSq() > 0 && false)) { const t = b; b = c; c = t; n.negate(); }
  n.normalize();
  const i = target.count;
  for (const p of [a, b, c]) {
    target.position.push(p.x, p.y, p.z);
    target.normal.push(n.x, n.y, n.z);
    target.color.push(color.r, color.g, color.b);
    // Ridges run down the slope: u across the slope, v down it.
    const u = uvAxis ? (p.x * uvAxis.x + p.z * uvAxis.y) : p.x;
    const v = uvAxis ? (p.z * uvAxis.x - p.x * uvAxis.y) : p.z;
    target.uv.push(u * uvScale, v * uvScale + p.y * uvScale);
  }
  target.index.push(i, i + 1, i + 2);
}

/** A hip or gable roof on a rotated rectangle (with overhang), its eaves at `y`. */
function addPitchedRoof(target: Buffers, walls: Buffers, building: TownBuilding, y: number, style: "hip" | "gable" | "temple", color: THREE.Color, wallTint: THREE.Color, base: number, storeys: number): void {
  const { cx, cz } = building.obb;
  let { w, d, angle } = building.obb;
  // Ridge along the longer side.
  if (d > w) { const t = w; w = d; d = t; angle += Math.PI / 2; }
  const over = style === "temple" ? 0.9 : 0.55;
  const W = w / 2 + over, D = d / 2 + over;
  const pitch = style === "temple" ? 0.95 : style === "gable" ? 0.5 : 0.48;
  const rise = Math.min(d / 2 * pitch, style === "temple" ? 7 : 3.4);
  const ax = Math.cos(angle), az = Math.sin(angle);
  const bx = -az, bz = ax;
  const P = (u: number, v: number, h: number) => new THREE.Vector3(cx + ax * u + bx * v, y + h, cz + az * u + bz * v);
  const axis = new THREE.Vector2(ax, az);
  const hip = style === "hip" ? Math.min(D, W * 0.45) : 0;
  const r0 = P(-W + hip, 0, rise), r1 = P(W - hip, 0, rise);
  const e00 = P(-W, -D, 0), e10 = P(W, -D, 0), e11 = P(W, D, 0), e01 = P(-W, D, 0);
  const s = 0.5;
  // Two long slopes.
  pushTri(target, e00, e10, r1, color, s, axis); pushTri(target, e00, r1, r0, color, s, axis);
  pushTri(target, e11, e01, r0, color, s, axis); pushTri(target, e11, r0, r1, color, s, axis);
  if (style === "hip") {
    pushTri(target, e10, e11, r1, color, s, axis);
    pushTri(target, e01, e00, r0, color, s, axis);
  } else {
    // Gable ends: wall-coloured triangles from the wall top to the ridge.
    const g0 = P(-w / 2, -d / 2, 0), g1 = P(-w / 2, d / 2, 0), gr0 = P(-w / 2, 0, rise - over * pitch);
    const g2 = P(w / 2, d / 2, 0), g3 = P(w / 2, -d / 2, 0), gr1 = P(w / 2, 0, rise - over * pitch);
    for (const [a, b, c, nxs] of [[g0, g1, gr0, -1], [g2, g3, gr1, 1]] as const) {
      const i = walls.count;
      const nx = ax * nxs, nz = az * nxs;
      for (const p of [a, b, c]) {
        walls.position.push(p.x, p.y, p.z);
        walls.normal.push(nx, 0, nz);
        walls.color.push(wallTint.r, wallTint.g, wallTint.b);
        walls.attr("aWall", 4, 0, FACADE.shopSide, 0, storeys);
        walls.attr("aBase", 1, base - 1000); // far below: reads as plain upper wall
      }
      const n = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a));
      if (n.x * nx + n.z * nz >= 0) walls.index.push(i, i + 1, i + 2);
      else walls.index.push(i, i + 2, i + 1);
    }
    if (style === "temple") {
      // A lower skirt roof all round, the second tier of a northern Thai hall.
      const skirt = 1.4;
      const k0 = P(-W - skirt, -D - skirt, -1.2), k1 = P(W + skirt, -D - skirt, -1.2), k2 = P(W + skirt, D + skirt, -1.2), k3 = P(-W - skirt, D + skirt, -1.2);
      pushTri(target, k0, k1, e10, color, s, axis); pushTri(target, k0, e10, e00, color, s, axis);
      pushTri(target, k2, k3, e01, color, s, axis); pushTri(target, k2, e01, e11, color, s, axis);
      pushTri(target, k1, k2, e11, color, s, axis); pushTri(target, k1, e11, e10, color, s, axis);
      pushTri(target, k3, k0, e00, color, s, axis); pushTri(target, k3, e00, e01, color, s, axis);
    }
  }
}

function buildBuildings(pack: TownPack, field: FloodField, atlas: FacadeAtlas, uniforms: TownUniforms, exclude: Set<number>): { group: THREE.Group; tanks: THREE.InstancedMesh; dispose(): void } {
  const tiles = new Map<string, TileParts>();
  const tankSpots: THREE.Vector3[] = [];
  const random = seeded(7177);
  for (const building of pack.buildings) {
    if (exclude.has(building.index)) continue;
    const ring = new Float32Array(building.ring);
    const n = ring.length / 2;
    if (n < 3) continue;
    const front = orient(ring, building.front);
    let lowest = Infinity, highest = -Infinity;
    for (let i = 0; i < n; i += 1) {
      const g = field.groundAt(ring[i * 2], ring[i * 2 + 1]);
      lowest = Math.min(lowest, g);
      highest = Math.max(highest, g);
    }
    const plinth = building.kind === "temple" || building.kind === "government" ? 0.6 : 0.25;
    const base = highest + plinth;
    const frontType = facadeFor(building, true);
    const storey = FACADE_STOREY[frontType];
    const storeys = Math.max(1, building.floors);
    const top = base + storeys * storey;
    const style = roofStyle(building);
    const parapet = style === "flat" ? (building.kind === "shophouse" ? 0.9 : 0.5) : 0;
    const key = `${Math.floor(building.obb.cx / TILE)}:${Math.floor(building.obb.cz / TILE)}`;
    const tile = tiles.get(key) ?? { walls: new Buffers(), pitched: new Buffers(), flat: new Buffers(), details: new Buffers() };
    tiles.set(key, tile);
    const seed = (building.index * 7919) % 9973;
    const tint = pick(PLASTER, seed);
    let u = (seed % 13) * 1.7;
    for (let i = 0; i < n; i += 1) {
      const j = (i + 1) % n;
      const isFront = i === front;
      addWall(tile.walls, ring[i * 2], ring[i * 2 + 1], ring[j * 2], ring[j * 2 + 1], lowest - 0.6, top + parapet, base, u, facadeFor(building, isFront), seed + i * 31, storeys, tint);
      if (parapet > 0) addWall(tile.walls, ring[i * 2], ring[i * 2 + 1], ring[j * 2], ring[j * 2 + 1], top, top + parapet, base - 1000, u, FACADE.shopSide, seed, storeys, tint, true);
      u += Math.hypot(ring[j * 2] - ring[i * 2], ring[j * 2 + 1] - ring[i * 2 + 1]);
      // Shop fronts: a metal awning over the ground floor.
      if (isFront && building.kind === "shophouse") {
        const ax = ring[i * 2], az = ring[i * 2 + 1], bx = ring[j * 2], bz = ring[j * 2 + 1];
        const len = Math.hypot(bx - ax, bz - az);
        if (len > 2) {
          const nx = (bz - az) / len, nz = -(bx - ax) / len;
          const color = pick(METAL_ROOF, seed + 3);
          const y0 = base + 3.0, depth = 1.15;
          const a = new THREE.Vector3(ax, y0, az), b = new THREE.Vector3(bx, y0, bz);
          const c = new THREE.Vector3(bx + nx * depth, y0 - 0.38, bz + nz * depth), d = new THREE.Vector3(ax + nx * depth, y0 - 0.38, az + nz * depth);
          pushTri(tile.details, a, b, c, color, 1); pushTri(tile.details, a, c, d, color, 1);
        }
      }
    }
    if (style === "flat") {
      addCap(tile.flat, ring, top + 0.02, pick(FLAT_ROOF, seed), 0.25);
      if (building.area > 30 && random() < 0.4) {
        // A water tank near a corner of the roof.
        const k = Math.floor(random() * n);
        const cx = building.obb.cx, cz = building.obb.cz;
        const px = ring[k * 2] + (cx - ring[k * 2]) * 0.25, pz = ring[k * 2 + 1] + (cz - ring[k * 2 + 1]) * 0.25;
        tankSpots.push(new THREE.Vector3(px, top + 0.05, pz));
      }
    } else {
      const color = style === "temple" ? new THREE.Color("#b4462f") : building.kind === "house" && seed % 3 === 0 ? pick(TILE_ROOF, seed) : pick(METAL_ROOF, seed);
      addPitchedRoof(tile.pitched, tile.walls, building, top, style, color, tint, base, storeys);
    }
  }
  const atlasWalls = facadeMaterial(atlas, uniforms);
  const seam = seamRoofTexture();
  seam.wrapS = seam.wrapT = THREE.RepeatWrapping;
  const concrete = concreteTexture();
  concrete.wrapS = concrete.wrapT = THREE.RepeatWrapping;
  const pitchedMaterial = roofMaterial(seam, uniforms, 0.55);
  const flatMaterial = roofMaterial(concrete, uniforms, 0.9);
  const detailMaterial = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.5, metalness: 0.2, side: THREE.DoubleSide, map: seam });
  const group = new THREE.Group();
  group.name = "Buildings";
  tiles.forEach((tile, key) => {
    const add = (buffers: Buffers, material: THREE.Material, name: string) => {
      if (!buffers.count) return;
      const mesh = new THREE.Mesh(buffers.geometry(), material);
      mesh.name = `${name}-${key}`;
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
    };
    add(tile.walls, atlasWalls, "Walls");
    add(tile.pitched, pitchedMaterial, "Roofs");
    add(tile.flat, flatMaterial, "FlatRoofs");
    add(tile.details, detailMaterial, "Awnings");
  });
  // Rooftop water tanks (stainless steel or blue plastic).
  const tankGeometry = new THREE.CylinderGeometry(0.55, 0.55, 1.15, 14);
  tankGeometry.translate(0, 0.575 + 0.35, 0);
  const tankMaterial = new THREE.MeshStandardMaterial({ color: "#c9cdd0", roughness: 0.35, metalness: 0.65 });
  const tanks = new THREE.InstancedMesh(tankGeometry, tankMaterial, Math.max(1, tankSpots.length));
  const m = new THREE.Matrix4(), c = new THREE.Color();
  tankSpots.forEach((spot, i) => {
    m.makeTranslation(spot.x, spot.y, spot.z);
    tanks.setMatrixAt(i, m);
    tanks.setColorAt(i, c.set(i % 4 === 0 ? "#3f6fb0" : "#ffffff"));
  });
  tanks.count = tankSpots.length;
  tanks.castShadow = true;
  tanks.computeBoundingSphere();
  group.add(tanks);
  return {
    group,
    tanks,
    dispose() {
      group.traverse((object) => { if (object instanceof THREE.Mesh) object.geometry.dispose(); });
      [atlasWalls, pitchedMaterial, flatMaterial, detailMaterial, tankMaterial].forEach((material) => material.dispose());
      seam.dispose();
      concrete.dispose();
    },
  };
}

// --- Ground and water --------------------------------------------------------------------------------------------------

interface CoverSampler {
  classAt(x: number, z: number): number;
  /** Distance (m) inside the water cover to its bank, 0 outside the water. */
  waterDepthAt(x: number, z: number): number;
}

function coverSampler(pack: TownPack): CoverSampler {
  const { cover } = pack;
  const { cols, rows } = cover;
  // Distance (in cells) from each water cell to the nearest non-water cell: a two-pass chamfer transform.
  const dist = new Float32Array(cols * rows);
  for (let i = 0; i < dist.length; i += 1) dist[i] = cover.data[i] === COVER.water ? 1e6 : 0;
  const relax = (i: number, j: number, cost: number) => { if (dist[j] + cost < dist[i]) dist[i] = dist[j] + cost; };
  for (let r = 0; r < rows; r += 1) for (let c = 0; c < cols; c += 1) {
    const i = r * cols + c;
    if (c > 0) relax(i, i - 1, 1);
    if (r > 0) relax(i, i - cols, 1);
    if (r > 0 && c > 0) relax(i, i - cols - 1, 1.414);
    if (r > 0 && c < cols - 1) relax(i, i - cols + 1, 1.414);
  }
  for (let r = rows - 1; r >= 0; r -= 1) for (let c = cols - 1; c >= 0; c -= 1) {
    const i = r * cols + c;
    if (c < cols - 1) relax(i, i + 1, 1);
    if (r < rows - 1) relax(i, i + cols, 1);
    if (r < rows - 1 && c < cols - 1) relax(i, i + cols + 1, 1.414);
    if (r < rows - 1 && c > 0) relax(i, i + cols - 1, 1.414);
  }
  const index = (x: number, z: number) => {
    const c = Math.round((x - cover.x0) / cover.dx), r = Math.round((z - cover.z0) / cover.dz);
    if (c < 0 || r < 0 || c >= cols || r >= rows) return -1;
    return r * cols + c;
  };
  return {
    classAt(x, z) {
      const i = index(x, z);
      return i < 0 ? -1 : cover.data[i];
    },
    waterDepthAt(x, z) {
      const i = index(x, z);
      return i < 0 || cover.data[i] !== COVER.water ? 0 : Math.min(40, dist[i] * cover.dx);
    },
  };
}

/** The drawn ground: the field's ground with the river's bed carved under the OSM water cover. */
function groundHeight(field: FloodField, cover: CoverSampler, x: number, z: number): number {
  const ground = field.groundAt(x, z);
  const inWater = cover.waterDepthAt(x, z);
  if (inWater <= 0) return ground;
  const bed = -0.8 - Math.min(2.2, inWater * 0.18);
  return Math.min(ground, bed);
}

interface GridSpec {
  x0: number; z0: number; x1: number; z1: number; step: number;
}

function gridGeometry(spec: GridSpec, height: (x: number, z: number) => number, keepQuad?: (x: number, z: number, step: number) => boolean, drop = 0): THREE.BufferGeometry {
  const cols = Math.round((spec.x1 - spec.x0) / spec.step) + 1;
  const rows = Math.round((spec.z1 - spec.z0) / spec.step) + 1;
  const positions = new Float32Array(cols * rows * 3);
  const uvs = new Float32Array(cols * rows * 2);
  for (let r = 0; r < rows; r += 1) for (let c = 0; c < cols; c += 1) {
    const x = spec.x0 + c * spec.step, z = spec.z0 + r * spec.step;
    const i = (r * cols + c) * 3;
    positions[i] = x;
    positions[i + 1] = height(x, z) - drop;
    positions[i + 2] = z;
    // Metres: the water's ripple texture repeats on them.
    uvs[(r * cols + c) * 2] = x;
    uvs[(r * cols + c) * 2 + 1] = z;
  }
  const index: number[] = [];
  for (let r = 0; r < rows - 1; r += 1) for (let c = 0; c < cols - 1; c += 1) {
    const x = spec.x0 + c * spec.step, z = spec.z0 + r * spec.step;
    if (keepQuad && !keepQuad(x, z, spec.step)) continue;
    const a = r * cols + c, b = a + 1, d = a + cols, e = d + 1;
    index.push(a, d, b, b, d, e);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  g.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  g.setIndex(index);
  g.computeVertexNormals();
  g.computeBoundingSphere();
  return g;
}

export const INNER: GridSpec = { x0: -780, z0: -660, x1: 780, z1: 1740, step: 6 };

// --- Roads ---------------------------------------------------------------------------------------------------------------

const ROAD_STYLE: Record<string, { surface: "asphalt" | "concrete" | "dirt"; lift: number; lamps: boolean; poles: boolean; marking: boolean }> = {
  trunk: { surface: "asphalt", lift: 0.11, lamps: true, poles: true, marking: true },
  primary: { surface: "asphalt", lift: 0.11, lamps: true, poles: true, marking: true },
  secondary: { surface: "asphalt", lift: 0.1, lamps: true, poles: true, marking: true },
  tertiary: { surface: "asphalt", lift: 0.09, lamps: true, poles: true, marking: false },
  unclassified: { surface: "concrete", lift: 0.08, lamps: false, poles: true, marking: false },
  residential: { surface: "concrete", lift: 0.08, lamps: false, poles: true, marking: false },
  living_street: { surface: "concrete", lift: 0.08, lamps: false, poles: true, marking: false },
  service: { surface: "concrete", lift: 0.07, lamps: false, poles: false, marking: false },
  track: { surface: "dirt", lift: 0.05, lamps: false, poles: false, marking: false },
};

function densify(points: Float32Array, step: number): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  const n = points.length / 2;
  for (let i = 0; i < n - 1; i += 1) {
    const ax = points[i * 2], az = points[i * 2 + 1], bx = points[i * 2 + 2], bz = points[i * 2 + 3];
    const len = Math.hypot(bx - ax, bz - az);
    const parts = Math.max(1, Math.ceil(len / step));
    for (let k = 0; k < parts; k += 1) out.push([ax + ((bx - ax) * k) / parts, az + ((bz - az) * k) / parts]);
  }
  if (n > 0) out.push([points[(n - 1) * 2], points[(n - 1) * 2 + 1]]);
  return out;
}

function addRibbon(target: Buffers, pts: Array<[number, number]>, width: number, heights: number[], vScale: number, uWidth = width): void {
  const n = pts.length;
  if (n < 2) return;
  let along = 0;
  const i0 = target.count;
  for (let i = 0; i < n; i += 1) {
    const [x, z] = pts[i];
    const [px, pz] = pts[Math.max(0, i - 1)];
    const [nx2, nz2] = pts[Math.min(n - 1, i + 1)];
    let tx = nx2 - px, tz = nz2 - pz;
    const tl = Math.hypot(tx, tz) || 1;
    tx /= tl; tz /= tl;
    const ox = -tz * width / 2, oz = tx * width / 2;
    if (i > 0) along += Math.hypot(x - pts[i - 1][0], z - pts[i - 1][1]);
    const y = heights[i];
    target.position.push(x + ox, y, z + oz, x - ox, y, z - oz);
    target.normal.push(0, 1, 0, 0, 1, 0);
    target.uv.push(0, along / vScale, uWidth / vScale, along / vScale);
    if (i < n - 1) {
      const a = i0 + i * 2;
      target.index.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  }
}

function dashTexture(): THREE.DataTexture {
  const size = 64;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) {
    const i = (y * size + x) * 4;
    const on = y < size / 2 ? 255 : 0;
    data[i] = 236; data[i + 1] = 233; data[i + 2] = 222; data[i + 3] = on;
  }
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.needsUpdate = true;
  return t;
}

// --- Poles, cables and lamps -------------------------------------------------------------------------------------------

export interface Lamps {
  group: THREE.Group;
  setNight(night: number): void;
}

function poleGeometry(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  const pole = new THREE.CylinderGeometry(0.1, 0.15, 9.2, 8);
  pole.translate(0, 4.6, 0);
  parts.push(pole);
  const arm = new THREE.BoxGeometry(1.7, 0.1, 0.1);
  arm.translate(0, 8.4, 0);
  parts.push(arm);
  const arm2 = new THREE.BoxGeometry(1.1, 0.08, 0.08);
  arm2.translate(0, 6.6, 0);
  parts.push(arm2);
  for (const x of [-0.7, -0.25, 0.25, 0.7]) {
    const insulator = new THREE.CylinderGeometry(0.035, 0.05, 0.16, 6);
    insulator.translate(x, 8.53, 0);
    parts.push(insulator);
  }
  const merged = mergeAll(parts);
  return merged;
}

function mergeAll(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const buffers = new Buffers();
  for (const part of parts) {
    const g = part.index ? part.toNonIndexed() : part;
    const p = g.getAttribute("position"), n = g.getAttribute("normal");
    const i0 = buffers.count;
    for (let i = 0; i < p.count; i += 1) {
      buffers.position.push(p.getX(i), p.getY(i), p.getZ(i));
      buffers.normal.push(n.getX(i), n.getY(i), n.getZ(i));
      buffers.index.push(i0 + i);
    }
    part.dispose();
  }
  return buffers.geometry();
}

function glowTexture(): THREE.DataTexture {
  const size = 64;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) for (let x = 0; x < size; x += 1) {
    const d = Math.hypot(x - size / 2 + 0.5, y - size / 2 + 0.5) / (size / 2);
    const a = Math.max(0, 1 - d) ** 2;
    const i = (y * size + x) * 4;
    data[i] = 255; data[i + 1] = 196; data[i + 2] = 120; data[i + 3] = Math.round(a * 255);
  }
  const t = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  t.needsUpdate = true;
  return t;
}

function buildUtilities(pack: TownPack, height: (x: number, z: number) => number, cover: CoverSampler, quality: Quality): { group: THREE.Group; lamps: Lamps; dispose(): void } {
  const random = seeded(6151);
  const poles: Array<{ x: number; z: number; ry: number; lamp: boolean; road: number }> = [];
  const inner = (x: number, z: number) => x > INNER.x0 + 20 && x < INNER.x1 - 20 && z > INNER.z0 + 20 && z < INNER.z1 - 20;
  pack.roads.forEach((road, roadIndex) => {
    const style = ROAD_STYLE[road.cls];
    if (!style?.poles) return;
    const pts = densify(road.points, 2);
    let since = 14 + random() * 20;
    const spacing = style.lamps ? 32 : 38;
    let lampToggle = 0;
    for (let i = 1; i < pts.length; i += 1) {
      since += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      if (since < spacing) continue;
      since = 0;
      const [x, z] = pts[i];
      const [px, pz] = pts[i - 1];
      const tl = Math.hypot(x - px, z - pz) || 1;
      const nx = -(z - pz) / tl, nz = (x - px) / tl;
      const off = road.width / 2 + 0.7;
      const sx = x + nx * off, sz = z + nz * off;
      if (!inner(sx, sz) || cover.classAt(sx, sz) === COVER.building || cover.classAt(sx, sz) === COVER.water) continue;
      lampToggle += 1;
      // Main roads light every other pole; lanes every third (a lamp on a pole is common in Thai sois).
      const lamp = style.lamps ? lampToggle % 2 === 0 : lampToggle % 3 === 0;
      poles.push({ x: sx, z: sz, ry: Math.atan2(nx, nz), lamp, road: roadIndex });
    }
  });
  const group = new THREE.Group();
  group.name = "Utilities";
  const poleMaterial = new THREE.MeshStandardMaterial({ color: "#bdb8ac", roughness: 0.85 });
  const geometry = poleGeometry();
  const poleMesh = new THREE.InstancedMesh(geometry, poleMaterial, Math.max(1, poles.length));
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), one = new THREE.Vector3(1, 1, 1);
  poles.forEach((pole, i) => {
    m.compose(new THREE.Vector3(pole.x, height(pole.x, pole.z) - 0.2, pole.z), q.setFromAxisAngle(up, pole.ry), one);
    poleMesh.setMatrixAt(i, m);
  });
  poleMesh.count = poles.length;
  poleMesh.castShadow = quality === "high";
  poleMesh.computeBoundingSphere();
  group.add(poleMesh);

  // Cables between consecutive poles of a road: power on the top arm, a sagging bundle of telecom lines below.
  const cable: number[] = [];
  for (let i = 1; i < poles.length; i += 1) {
    const a = poles[i - 1], b = poles[i];
    if (a.road !== b.road || Math.hypot(a.x - b.x, a.z - b.z) > 60) continue;
    const ya = height(a.x, a.z) - 0.2, yb = height(b.x, b.z) - 0.2;
    const lines: Array<[number, number, number]> = [[-0.7, 8.5, 0.5], [0.7, 8.5, 0.5], [-0.25, 8.5, 0.45], [-0.45, 6.6, 0.9], [-0.3, 6.5, 1.1], [-0.15, 6.55, 1.3], [0.0, 6.4, 1.5]];
    for (const [offset, h, sagBase] of lines) {
      const sag = sagBase + random() * 0.35;
      const ax = a.x + Math.cos(a.ry) * offset, az = a.z - Math.sin(a.ry) * offset;
      const bx = b.x + Math.cos(b.ry) * offset, bz = b.z - Math.sin(b.ry) * offset;
      const segments = 8;
      for (let s = 0; s < segments; s += 1) {
        for (const t of [s / segments, (s + 1) / segments]) {
          const y = ya + h + (yb - ya) * t - sag * 4 * t * (1 - t);
          cable.push(ax + (bx - ax) * t, y, az + (bz - az) * t);
        }
      }
    }
  }
  const cableGeometry = new THREE.BufferGeometry();
  cableGeometry.setAttribute("position", new THREE.Float32BufferAttribute(cable, 3));
  cableGeometry.computeBoundingSphere();
  // Cables are one pixel wide at any distance: they fade out beyond the street (aerial shots would show black lines).
  const cableMaterial = new THREE.LineBasicMaterial({ color: "#1d1f1f", transparent: true, opacity: 0.85 });
  cableMaterial.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying float vCableFade;")
      .replace("#include <project_vertex>", "#include <project_vertex>\nvCableFade = 1.0 - smoothstep(60.0, 160.0, -mvPosition.z);");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying float vCableFade;")
      .replace("#include <color_fragment>", "#include <color_fragment>\ndiffuseColor.a *= vCableFade;\nif (diffuseColor.a < 0.02) discard;");
  };
  cableMaterial.customProgramCacheKey = () => "fg-cable-v1";
  const cables = new THREE.LineSegments(cableGeometry, cableMaterial);
  cables.name = "Cables";
  group.add(cables);

  // Street lamps on every other pole of the main roads: a head that glows at night and a pool of light below.
  const lampPoles = poles.filter((pole) => pole.lamp);
  const headGeometry = new THREE.BoxGeometry(0.5, 0.14, 0.24);
  headGeometry.translate(0, 7.6, 1.15);
  const armGeometry = new THREE.BoxGeometry(0.06, 0.06, 1.25);
  armGeometry.translate(0, 7.7, 0.6);
  const headMaterial = new THREE.MeshBasicMaterial({ color: "#5a5a55", toneMapped: false });
  const armMaterial = new THREE.MeshStandardMaterial({ color: "#7b7d7a", roughness: 0.6, metalness: 0.4 });
  const heads = new THREE.InstancedMesh(headGeometry, headMaterial, Math.max(1, lampPoles.length));
  const arms = new THREE.InstancedMesh(armGeometry, armMaterial, Math.max(1, lampPoles.length));
  const glow = glowTexture();
  const poolMaterial = new THREE.MeshBasicMaterial({ map: glow, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -6, polygonOffsetUnits: -6 });
  const poolPlane = new THREE.PlaneGeometry(1, 1);
  poolPlane.rotateX(-Math.PI / 2);
  const pools = new THREE.InstancedMesh(poolPlane, poolMaterial, Math.max(1, lampPoles.length));
  lampPoles.forEach((pole, i) => {
    const y = height(pole.x, pole.z) - 0.2;
    // The lamp leans toward the road (back along the pole's normal).
    m.compose(new THREE.Vector3(pole.x, y, pole.z), q.setFromAxisAngle(up, pole.ry + Math.PI), one);
    heads.setMatrixAt(i, m);
    arms.setMatrixAt(i, m);
    const fx = pole.x - Math.sin(pole.ry) * 1.2, fz = pole.z - Math.cos(pole.ry) * 1.2;
    m.compose(new THREE.Vector3(fx, height(fx, fz) + 0.12, fz), q.identity(), new THREE.Vector3(12, 1, 12));
    pools.setMatrixAt(i, m);
  });
  for (const mesh of [heads, arms, pools]) {
    mesh.count = lampPoles.length;
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
  pools.renderOrder = 4;
  const off = new THREE.Color("#5a5a55"), on = new THREE.Color("#ffd9a0").multiplyScalar(2.2);
  const lamps: Lamps = {
    group,
    setNight(night: number) {
      headMaterial.color.copy(off).lerp(on, night);
      poolMaterial.opacity = 0.55 * night;
      pools.visible = night > 0.01;
    },
  };
  lamps.setNight(0);
  return {
    group,
    lamps,
    dispose() {
      [geometry, cableGeometry, headGeometry, armGeometry, poolPlane].forEach((g) => g.dispose());
      [poleMaterial, cableMaterial, headMaterial, armMaterial, poolMaterial].forEach((material) => material.dispose());
      glow.dispose();
    },
  };
}

// --- The walk to the shelter -----------------------------------------------------------------------------------------

export interface RouteBand {
  mesh: THREE.Mesh;
  /** 0..1 */
  setOpacity(opacity: number): void;
  /** Where the band is at an index along its points (on the water when wet). */
  points: Array<[number, number]>;
}

function bandTexture(): THREE.DataTexture {
  const w = 8, h = 64;
  const data = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y += 1) for (let x = 0; x < w; x += 1) {
    const across = Math.abs((x + 0.5) / w - 0.5) * 2;
    const i = (y * w + x) * 4;
    data[i] = data[i + 1] = data[i + 2] = 255;
    data[i + 3] = Math.round(255 * Math.max(0, 1 - Math.pow(across, 3)));
  }
  const t = new THREE.DataTexture(data, w, h, THREE.RGBAFormat);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.magFilter = THREE.LinearFilter;
  t.needsUpdate = true;
  return t;
}

function buildRoute(pack: TownPack, field: FloodField, height: (x: number, z: number) => number, uniforms: TownUniforms): { band: RouteBand; firstCut: { point: THREE.Vector3; stage: number }; dispose(): void } {
  const route = pack.route;
  const n = route.points.length / 2;
  // Closure stage per point: the edge it starts (the last point takes its edge's).
  const closureAt = new Float32Array(n).fill(Infinity);
  for (const edge of route.edges) for (let i = edge.from; i <= edge.to; i += 1) closureAt[i] = Math.min(closureAt[i], edge.closure);
  const raw = Array.from({ length: n }, (_, i) => [route.points[i * 2], route.points[i * 2 + 1]] as [number, number]);
  const pts: Array<[number, number]> = [];
  const closures: number[] = [];
  for (let i = 0; i < n - 1; i += 1) {
    const [ax, az] = raw[i], [bx, bz] = raw[i + 1];
    const len = Math.hypot(bx - ax, bz - az);
    const parts = Math.max(1, Math.ceil(len / 3));
    for (let k = 0; k < parts; k += 1) {
      pts.push([ax + ((bx - ax) * k) / parts, az + ((bz - az) * k) / parts]);
      closures.push(Math.min(closureAt[i], closureAt[i + 1]));
    }
  }
  pts.push(raw[n - 1]);
  closures.push(closureAt[n - 1]);
  const buffers = new Buffers();
  addRibbon(buffers, pts, 2.6, pts.map(([x, z]) => height(x, z)), 4, 1);
  // Per vertex: ground, k_s and the closure stage (twice: the ribbon has two vertices per point).
  for (let i = 0; i < pts.length; i += 1) {
    const [x, z] = pts[i];
    for (let s = 0; s < 2; s += 1) buffers.attr("aRoute", 3, height(x, z), field.kAt(x, z), Number.isFinite(closures[i]) ? closures[i] : 99);
  }
  const texture = bandTexture();
  const material = new THREE.MeshBasicMaterial({ color: "#ffffff", map: texture, transparent: true, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -8, polygonOffsetUnits: -8 });
  const opacity = { value: 0 };
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms, { uRouteOpacity: opacity });
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute vec3 aRoute;\nuniform float uStage;\nvarying float vCut;\nvarying float vAlong;")
      .replace(
        "#include <begin_vertex>",
        "#include <begin_vertex>\nfloat waterTop = aRoute.y * uStage;\ntransformed.y = max(aRoute.x, waterTop) + 0.14;\nvCut = step(aRoute.z, uStage);\nvAlong = uv.y;",
      );
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform float uRouteOpacity;\nuniform float uTime;\nvarying float vCut;\nvarying float vAlong;")
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec3 teal = vec3(0.16, 0.62, 0.62);
        vec3 amber = vec3(0.98, 0.62, 0.16);
        float dash = step(0.45, fract(vAlong * 1.2 - uTime * 0.6));
        diffuseColor.rgb = mix(teal, amber, vCut);
        diffuseColor.a *= uRouteOpacity * mix(0.9, mix(0.35, 1.0, dash), vCut);
        `,
      );
  };
  material.customProgramCacheKey = () => "fg-route-v1";
  const mesh = new THREE.Mesh(buffers.geometry(), material);
  mesh.name = "Route";
  mesh.renderOrder = 5;
  mesh.frustumCulled = false;
  // The first edge to close, by stage.
  let best = route.edges[0];
  for (const edge of route.edges) if (edge.closure < best.closure) best = edge;
  const mid = Math.floor((best.from + best.to) / 2);
  const cx = route.points[mid * 2], cz = route.points[mid * 2 + 1];
  return {
    band: {
      mesh,
      points: pts,
      setOpacity(value) {
        opacity.value = value;
        mesh.visible = value > 0.005;
      },
    },
    firstCut: { point: new THREE.Vector3(cx, height(cx, cz) + 3, cz), stage: best.closure },
    dispose() {
      mesh.geometry.dispose();
      material.dispose();
      texture.dispose();
    },
  };
}

// --- The town ----------------------------------------------------------------------------------------------------------

export interface TownOptions {
  quality: Quality;
  /** Outlines the stage replaces with its own buildings (Lalita's house, the operations room). */
  exclude?: number[];
}

export function buildTown(pack: TownPack, options: TownOptions): Town {
  const field = new FloodField(pack);
  const cover = coverSampler(pack);
  const special = pack.special;
  const place = (id: string) => pack.manifest.places.find((entry) => entry.id === id);

  // Lalita's home: the outline's box, turned to face its street; a pad holds it at its own cell's height.
  const homeBuilding = pack.buildings[special.home];
  const homeRing = new Float32Array(homeBuilding.ring);
  const homeFront = orient(homeRing, homeBuilding.front);
  const hn = homeRing.length / 2;
  const fa = homeFront, fb = (homeFront + 1) % hn;
  const ex = homeRing[fb * 2] - homeRing[fa * 2], ez = homeRing[fb * 2 + 1] - homeRing[fa * 2 + 1];
  const el = Math.hypot(ex, ez) || 1;
  const nx = ez / el, nz = -ex / el;
  const rotation = Math.atan2(nx, nz);
  let { w, d } = homeBuilding.obb;
  const axis = Math.abs(Math.cos(homeBuilding.obb.angle) * nx + Math.sin(homeBuilding.obb.angle) * nz);
  if (axis > 0.7) { const t = w; w = d; d = t; }
  w = Math.min(Math.max(w, 7.2), 10.5);
  d = Math.min(Math.max(d, 6.0), 9.0);
  const homePlace = place("home");
  const homeCell = field.cellIndex(homePlace?.x ?? 0, homePlace?.z ?? 0);
  const homeGround = homeCell >= 0 ? field.ground[homeCell] : field.groundAt(homeBuilding.obb.cx, homeBuilding.obb.cz);
  field.addPad({ x: homeBuilding.obb.cx, z: homeBuilding.obb.cz, radius: Math.max(w, d) / 2 + 4.5, blend: 7, height: homeGround });

  const height = (x: number, z: number) => groundHeight(field, cover, x, z);
  const uniforms = createTownUniforms(field);
  const group = new THREE.Group();
  group.name = "Town";
  const disposers: Array<() => void> = [];

  // Ground: a fine grid over the story's area, a coarser one over the rest of the bake, the hills beyond.
  const detail = groundDetailTexture();
  detail.wrapS = detail.wrapT = THREE.RepeatWrapping;
  const coverTexture = new THREE.DataTexture(pack.cover.data, pack.cover.cols, pack.cover.rows, THREE.RedFormat, THREE.UnsignedByteType);
  coverTexture.magFilter = coverTexture.minFilter = THREE.NearestFilter;
  coverTexture.needsUpdate = true;
  const coverXform = new THREE.Vector4(pack.cover.x0 - pack.cover.dx / 2, pack.cover.z0 - pack.cover.dz / 2, 1 / (pack.cover.cols * pack.cover.dx), 1 / (pack.cover.rows * pack.cover.dz));
  const ground = groundMaterial(coverTexture, coverXform, detail, uniforms);
  const step = options.quality === "high" ? INNER.step : 9;
  const innerSpec = { ...INNER, step };
  const innerGeometry = gridGeometry(innerSpec, height);
  const innerMesh = new THREE.Mesh(innerGeometry, ground);
  innerMesh.receiveShadow = true;
  innerMesh.name = "GroundInner";
  group.add(innerMesh);
  const extent = { x0: pack.cover.x0, z0: pack.cover.z0, x1: pack.cover.x0 + (pack.cover.cols - 1) * pack.cover.dx, z1: pack.cover.z0 + (pack.cover.rows - 1) * pack.cover.dz };
  const outerSpec: GridSpec = { x0: Math.floor(extent.x0 / 24) * 24, z0: Math.floor(extent.z0 / 24) * 24, x1: Math.ceil(extent.x1 / 24) * 24, z1: Math.ceil(extent.z1 / 24) * 24, step: 24 };
  const insideInner = (x: number, z: number, s: number) => x >= INNER.x0 + 12 && x + s <= INNER.x1 - 12 && z >= INNER.z0 + 12 && z + s <= INNER.z1 - 12;
  const outerGeometry = gridGeometry(outerSpec, height, (x, z, s) => !insideInner(x, z, s), 0.15);
  const outerMesh = new THREE.Mesh(outerGeometry, ground);
  outerMesh.receiveShadow = true;
  outerMesh.name = "GroundOuter";
  group.add(outerMesh);
  // Hills beyond the bake, from the backdrop relief.
  const bd = pack.backdrop;
  const backdropHeight = (x: number, z: number) => {
    const fc = Math.min(bd.cols - 1, Math.max(0, (x - bd.x0) / bd.dx)), fr = Math.min(bd.rows - 1, Math.max(0, (z - bd.z0) / bd.dz));
    const c0 = Math.floor(fc), r0 = Math.floor(fr), c1 = Math.min(bd.cols - 1, c0 + 1), r1 = Math.min(bd.rows - 1, r0 + 1);
    const tx = fc - c0, tz = fr - r0;
    const v = (c: number, r: number) => bd.height[r * bd.cols + c];
    return (v(c0, r0) * (1 - tx) + v(c1, r0) * tx) * (1 - tz) + (v(c0, r1) * (1 - tx) + v(c1, r1) * tx) * tz;
  };
  const backdropSpec: GridSpec = { x0: bd.x0, z0: bd.z0, x1: bd.x0 + (bd.cols - 1) * bd.dx, z1: bd.z0 + (bd.rows - 1) * bd.dz, step: bd.dx };
  const insideDetail = (x: number, z: number, s: number) => x >= outerSpec.x0 + 24 && x + s <= outerSpec.x1 - 24 && z >= outerSpec.z0 + 24 && z + s <= outerSpec.z1 - 24;
  const backdropGeometry = gridGeometry(backdropSpec, (x, z) => (insideDetail(x, z, 0) ? height(x, z) : backdropHeight(x, z)), (x, z, s) => !insideDetail(x, z, s), 0.4);
  const backdropMesh = new THREE.Mesh(backdropGeometry, ground);
  backdropMesh.name = "GroundBackdrop";
  group.add(backdropMesh);
  disposers.push(() => { innerGeometry.dispose(); outerGeometry.dispose(); backdropGeometry.dispose(); ground.dispose(); detail.dispose(); coverTexture.dispose(); });

  // Water: where the replay can wet the ground (h below the highest stage) and on the river.
  const maxStage = Math.max(...pack.manifest.replay.stage_anchors.map((anchor) => anchor.stage_m));
  const ripple = rippleNormalTexture();
  ripple.wrapS = ripple.wrapT = THREE.RepeatWrapping;
  ripple.repeat.set(1 / 14, 1 / 14);
  const water = waterMaterial(uniforms, { normalMap: ripple });
  const waterMeshes: THREE.Mesh[] = [];
  const canWet = (x: number, z: number) => {
    const i = field.cellIndex(x, z);
    if (cover.waterDepthAt(x, z) > 0) return true;
    return i >= 0 && field.hand[i] < maxStage + 0.25;
  };
  for (const [spec, keep] of [
    [innerSpec, (x: number, z: number, s: number) => canWet(x, z) || canWet(x + s, z) || canWet(x, z + s) || canWet(x + s, z + s)],
    [outerSpec, (x: number, z: number, s: number) => !insideInner(x, z, s) && (canWet(x, z) || canWet(x + s, z + s))],
  ] as const) {
    const geometry = gridGeometry(spec, height, keep);
    const p = geometry.getAttribute("position") as THREE.BufferAttribute;
    const floodAttr = new Float32Array(p.count * 3);
    const riverAttr = new Float32Array(p.count * 2);
    for (let i = 0; i < p.count; i += 1) {
      const x = p.getX(i), z = p.getZ(i);
      const cell = field.cellIndex(x, z);
      floodAttr[i * 3] = field.kAt(x, z);
      floodAttr[i * 3 + 1] = p.getY(i);
      floodAttr[i * 3 + 2] = cell >= 0 ? field.low[cell] : 0;
      const inRiver = cover.waterDepthAt(x, z) > 0;
      riverAttr[i * 2] = inRiver ? 1 : 0;
      riverAttr[i * 2 + 1] = -0.45;
    }
    geometry.setAttribute("aFlood", new THREE.BufferAttribute(floodAttr, 3));
    geometry.setAttribute("aRiver", new THREE.BufferAttribute(riverAttr, 2));
    // The vertex shader lifts the surface; keep culling bounds generous.
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3((spec.x0 + spec.x1) / 2, 2, (spec.z0 + spec.z1) / 2), Math.hypot(spec.x1 - spec.x0, spec.z1 - spec.z0) / 2 + 10);
    const mesh = new THREE.Mesh(geometry, water);
    mesh.renderOrder = 2;
    mesh.name = "Water";
    mesh.receiveShadow = true;
    group.add(mesh);
    waterMeshes.push(mesh);
  }
  disposers.push(() => { waterMeshes.forEach((mesh) => mesh.geometry.dispose()); water.dispose(); ripple.dispose(); });

  // Buildings.
  const atlas = buildFacadeAtlas(options.quality === "low");
  const exclude = new Set(options.exclude ?? []);
  exclude.add(special.home);
  exclude.add(special.office);
  const buildings = buildBuildings(pack, field, atlas, uniforms, exclude);
  group.add(buildings.group);
  disposers.push(() => { buildings.dispose(); atlas.dispose(); });

  // Roads.
  const asphalt = asphaltTexture();
  const concrete = concreteTexture();
  for (const t of [asphalt, concrete]) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  const surfaces = {
    asphalt: { buffers: new Buffers(), material: roadMaterial(asphalt, uniforms, "#7c7b77") },
    concrete: { buffers: new Buffers(), material: roadMaterial(concrete, uniforms, "#b9b5ab") },
    dirt: { buffers: new Buffers(), material: roadMaterial(concrete, uniforms, "#9a8a70") },
  };
  const markings = new Buffers();
  pack.roads.forEach((road: TownRoad) => {
    const style = ROAD_STYLE[road.cls];
    if (!style) return;
    const pts = densify(road.points, 4);
    let heights = pts.map(([x, z]) => height(x, z) + style.lift);
    if (road.bridge && pts.length > 1) {
      const y0 = heights[0], y1 = heights[heights.length - 1];
      const deck = Math.max(y0, y1, 1.6);
      heights = heights.map((_, i) => {
        const t = i / (heights.length - 1);
        const ramp = Math.min(1, Math.min(t, 1 - t) * 8);
        return (y0 * (1 - t) + y1 * t) * (1 - ramp) + deck * ramp;
      });
    }
    addRibbon(surfaces[style.surface].buffers, pts, road.width, heights, 4);
    if (style.marking && road.width >= 8) addRibbon(markings, pts, 0.14, heights.map((y) => y + 0.015), 6, 1);
  });
  for (const { buffers, material } of Object.values(surfaces)) {
    if (!buffers.count) continue;
    const mesh = new THREE.Mesh(buffers.geometry(), material);
    mesh.receiveShadow = true;
    mesh.renderOrder = 1;
    mesh.name = "Roads";
    group.add(mesh);
  }
  const dash = dashTexture();
  const markingMaterial = new THREE.MeshStandardMaterial({ map: dash, transparent: true, alphaTest: 0.5, roughness: 0.6, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -8 });
  if (markings.count) {
    const mesh = new THREE.Mesh(markings.geometry(), markingMaterial);
    mesh.renderOrder = 1;
    mesh.name = "Markings";
    group.add(mesh);
  }
  disposers.push(() => {
    for (const { material } of Object.values(surfaces)) material.dispose();
    group.children.filter((child) => child.name === "Roads" || child.name === "Markings").forEach((child) => (child as THREE.Mesh).geometry.dispose());
    asphalt.dispose(); concrete.dispose(); dash.dispose(); markingMaterial.dispose();
  });

  const utilities = buildUtilities(pack, height, cover, options.quality);
  group.add(utilities.group);
  disposers.push(utilities.dispose);

  const route = buildRoute(pack, field, height, uniforms);
  group.add(route.band.mesh);
  disposers.push(route.dispose);

  const anchorAt = (id: string, lift: number) => {
    const entry = place(id);
    const x = entry?.x ?? 0, z = entry?.z ?? 0;
    return new THREE.Vector3(x, height(x, z) + lift, z);
  };
  const officeBuilding = pack.buildings[special.office];
  const officeGround = field.groundAt(officeBuilding.obb.cx, officeBuilding.obb.cz);
  const neighbour = pack.buildings[special.neighbour];

  return {
    group,
    uniforms,
    field,
    anchors: {
      home: new THREE.Vector3(homeBuilding.obb.cx, homeGround + 10.5, homeBuilding.obb.cz),
      neighbour: new THREE.Vector3(neighbour.obb.cx, field.groundAt(neighbour.obb.cx, neighbour.obb.cz) + 8.5, neighbour.obb.cz),
      shelter: anchorAt(pack.route.destination, 14),
      office: new THREE.Vector3(officeBuilding.obb.cx, officeGround + 12, officeBuilding.obb.cz),
      wat: anchorAt("R04", 16),
      river: anchorAt("sai_river", 6),
      cut: route.firstCut.point,
    },
    home: { x: homeBuilding.obb.cx, z: homeBuilding.obb.cz, w, d, rotation, yard: 3.0, ground: homeGround },
    office: { x: officeBuilding.obb.cx, z: officeBuilding.obb.cz, ground: officeGround },
    route: route.band,
    lamps: utilities.lamps,
    firstCut: route.firstCut,
    dispose() {
      disposers.forEach((dispose) => dispose());
      (uniforms.uFlood.value as THREE.Texture).dispose();
    },
  };
}

export { TILE as TOWN_TILE };
// For the stage's tree placement and tests.
export { coverSampler, groundHeight };
export type { CoverSampler };
