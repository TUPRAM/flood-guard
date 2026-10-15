/**
 * The real-map town of the journey: Mae Sai around the Public app's example home, baked by
 * `scripts/build_journey_town.py` into `public/journey/town/` (see docs/journey-v2-real-map.md). This module decodes
 * the bake and builds the flood field every 3D surface shares. Pure: no DOM, no Three.js (the PNGs are decoded with
 * the replay's own decoder), so the rules the story rests on are unit-tested against the published files.
 *
 * Frame: metres on a local plane at the dry example home; x east, z south, y up.
 *
 * The flood field follows the replay (r5) cell for cell. A cell's effective HAND is h = code × 0.05 m and its depth
 * factor k = byte / 255 × 2.5; it is wet exactly when stage > h, with depth k × (stage − h) (`cellDepth`). For drawing,
 * k is smoothed over about 30 m (k_s), the ground of a floodable cell is k_s × h and the water surface k_s × stage, so
 * the surface is level within a reach and the shore falls where the model puts it.
 */

import { stageAt, type StageAnchor } from "@/lib/flood-timeline";

// --- The baked manifest -------------------------------------------------------------------------------------------------

export type Localized = { en: string; th: string };

export interface TownPlace {
  id: string;
  kind: string;
  x: number;
  z: number;
  name: Localized;
  cell?: { code: number; k: number };
  [key: string]: unknown;
}

export interface TownBeat {
  hour: number;
  stage_m: number;
  [key: string]: unknown;
}

export interface TownManifest {
  schema: string;
  generated_at: { value: string; basis: string } | string;
  confidence: string;
  source_timestamp: string;
  credits: Localized;
  replay: { revision: string; stage_anchors: StageAnchor[]; impassable_depth_m: number; hand: { step_m: number; byte_scale: number; channel_code: number; never_code: number } };
  places: TownPlace[];
  beats: TownBeat[];
  [key: string]: unknown;
}

export type BuildingKind = "shophouse" | "house" | "large" | "shed" | "temple" | "government" | "school" | "market";
export const BUILDING_KINDS: readonly BuildingKind[] = ["shophouse", "house", "large", "shed", "temple", "government", "school", "market"];

export interface TownBuilding {
  index: number;
  /** Outline, x/z pairs in metres (closing vertex not repeated). */
  ring: Float32Array;
  kind: BuildingKind;
  floors: number;
  /** Index of the edge (vertex i → i+1) that faces the street. */
  front: number;
  obb: { cx: number; cz: number; w: number; d: number; angle: number };
  /** Rectangularity, 0..1. */
  rect: number;
  area: number;
  compound: number;
}

export interface TownRoad {
  points: Float32Array;
  cls: string;
  width: number;
  bridge: boolean;
}

export interface TownTree {
  x: number;
  z: number;
  kind: number;
  scale: number;
}

export interface RouteEdge {
  from: number;
  to: number;
  /** Stage (m) at which the edge becomes impassable (water 0.3 m or more); Infinity if never. */
  closure: number;
}

export interface TownRoute {
  destination: string;
  points: Float32Array;
  length: number;
  edges: RouteEdge[];
  cutStage: number;
  /** The sample of the first closing edge that closes the walk (where the "low point" and "walk cut" labels sit). */
  lowPoint: { x: number; z: number; along: number };
}

export interface Grid {
  cols: number;
  rows: number;
  /** Centre of the first cell. */
  x0: number;
  z0: number;
  dx: number;
  dz: number;
}

export interface TownPack {
  manifest: TownManifest;
  cells: Grid & { code: Uint8Array; kByte: Uint8Array; low: Uint8Array };
  /** Height (m) of cells that never flood, from the DEM above the drainage datum; NaN elsewhere. */
  relief: Float32Array;
  cover: Grid & { data: Uint8Array };
  backdrop: Grid & { height: Float32Array };
  buildings: TownBuilding[];
  roads: TownRoad[];
  trees: TownTree[];
  route: TownRoute;
  /** Building indices with a role in the story. */
  special: { home: number; neighbour: number; office: number; shelter: number };
}

export const COVER = { open: 0, water: 1, road: 2, building: 3, green: 4, field: 5 } as const;

// --- Decoding -------------------------------------------------------------------------------------------------------------

/** Delta-decoded integer decimetres → metres. Each run starts with an absolute pair. */
export function decodeRuns(coords: readonly number[], starts: readonly number[]): Float32Array[] {
  const runs: Float32Array[] = [];
  for (let r = 0; r < starts.length; r += 1) {
    const begin = starts[r];
    const end = r + 1 < starts.length ? starts[r + 1] : coords.length / 2;
    const out = new Float32Array((end - begin) * 2);
    let x = 0, z = 0;
    for (let i = begin; i < end; i += 1) {
      x = i === begin ? coords[i * 2] : x + coords[i * 2];
      z = i === begin ? coords[i * 2 + 1] : z + coords[i * 2 + 1];
      out[(i - begin) * 2] = x / 10;
      out[(i - begin) * 2 + 1] = z / 10;
    }
    runs.push(out);
  }
  return runs;
}

/** One delta-encoded run (absolute first pair) → metres. */
export function decodeRun(coords: readonly number[]): Float32Array {
  return decodeRuns(coords, [0])[0];
}

// --- The flood field ------------------------------------------------------------------------------------------------------

export interface Pad {
  x: number;
  z: number;
  /** Radius (m) of the flat top (0 for a rectangular pad: `rect` gives its top) and of the blend around it. */
  radius: number;
  blend: number;
  height: number;
  /** A rectangular flat top instead of a round one: width along S, depth along F, rotation as a house's. */
  rect?: { w: number; d: number; rotation: number };
}

/** Distance (m) from a point to a pad's flat top (0 on it). */
function padDistance(pad: Pad, x: number, z: number): number {
  const dx = x - pad.x, dz = z - pad.z;
  if (!pad.rect) return Math.max(0, Math.hypot(dx, dz) - pad.radius);
  const { w, d, rotation } = pad.rect;
  const along = Math.abs(dx * Math.cos(rotation) - dz * Math.sin(rotation)) - w / 2;
  const across = Math.abs(dx * Math.sin(rotation) + dz * Math.cos(rotation)) - d / 2;
  return Math.hypot(Math.max(0, along), Math.max(0, across));
}

/**
 * The replay's cells as fields for drawing: smoothed depth factor, effective HAND, ground height, low-confidence flag.
 * Sampling is bilinear between cell centres, so at a cell centre the values are the model's own.
 */
export class FloodField implements Grid {
  readonly cols: number;
  readonly rows: number;
  readonly x0: number;
  readonly z0: number;
  readonly dx: number;
  readonly dz: number;
  /** k_s per cell. */
  readonly kSmooth: Float32Array;
  /** Effective HAND per cell (m); 0 for channel cells, 99 for cells that never flood. */
  readonly hand: Float32Array;
  readonly ground: Float32Array;
  readonly low: Float32Array;
  readonly code: Uint8Array;
  readonly k: Float32Array;
  private readonly pads: Pad[] = [];
  readonly step: number;

  constructor(pack: Pick<TownPack, "cells" | "relief" | "manifest">, smoothCells = 2) {
    const { cells } = pack;
    // Grid edges: the field's x0/z0 are the outer edge of the first cell.
    this.cols = cells.cols;
    this.rows = cells.rows;
    this.dx = cells.dx;
    this.dz = cells.dz;
    this.x0 = cells.x0 - cells.dx / 2;
    this.z0 = cells.z0 - cells.dz / 2;
    this.code = cells.code;
    const hand = pack.manifest.replay.hand;
    this.step = hand.step_m;
    const n = this.cols * this.rows;
    this.k = new Float32Array(n);
    this.hand = new Float32Array(n);
    this.low = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      const code = cells.code[i];
      this.k[i] = (cells.kByte[i] / 255) * hand.byte_scale;
      this.hand[i] = code === hand.never_code ? 99 : code === hand.channel_code ? 0 : code * hand.step_m;
      this.low[i] = cells.low[i] >= 128 ? 1 : 0;
    }
    this.kSmooth = gaussian(this.k, this.cols, this.rows, smoothCells, (i) => cells.code[i] !== hand.never_code && cells.kByte[i] > 0);
    this.ground = new Float32Array(n);
    // Channel cells are HAND 0, so k_s × 0: the model's own depth there is k × stage. They are the replay's drainage
    // lines, not the mapped river (which is carved from the OSM water cover when drawn).
    for (let i = 0; i < n; i += 1) if (cells.code[i] !== hand.never_code) this.ground[i] = this.kSmooth[i] * this.hand[i];
    this.rampNeverCells(pack.relief, hand.never_code, Math.max(...pack.manifest.replay.stage_anchors.map((a) => a.stage_m)));
  }

  /**
   * Cells that never flood stand on the DEM above the drainage datum, a different base from k_s × HAND: met directly,
   * the two make cliffs of several metres. Each such cell rises from the height of the nearest floodable ground (and at
   * least 0.5 m above the highest water there) to its relief over about four cells.
   */
  private rampNeverCells(relief: Float32Array, neverCode: number, maxStage: number): void {
    const { cols, rows } = this;
    const n = cols * rows;
    const dist = new Float32Array(n), edge = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      if (this.code[i] === neverCode) { dist[i] = 1e6; continue; }
      dist[i] = 0;
      edge[i] = Math.max(this.ground[i], this.kSmooth[i] * maxStage) + 0.5;
    }
    // Two-pass chamfer distance (in cells), carrying the floor of the nearest floodable cell.
    const relax = (i: number, j: number, cost: number) => {
      if (dist[j] + cost < dist[i]) { dist[i] = dist[j] + cost; edge[i] = edge[j]; }
    };
    for (let r = 0; r < rows; r += 1) for (let c = 0; c < cols; c += 1) {
      const i = r * cols + c;
      if (c > 0) relax(i, i - 1, 1);
      if (r > 0) relax(i, i - cols, 1);
      if (r > 0 && c > 0) relax(i, i - cols - 1, Math.SQRT2);
      if (r > 0 && c < cols - 1) relax(i, i - cols + 1, Math.SQRT2);
    }
    for (let r = rows - 1; r >= 0; r -= 1) for (let c = cols - 1; c >= 0; c -= 1) {
      const i = r * cols + c;
      if (c < cols - 1) relax(i, i + 1, 1);
      if (r < rows - 1) relax(i, i + cols, 1);
      if (r < rows - 1 && c < cols - 1) relax(i, i + cols + 1, Math.SQRT2);
      if (r < rows - 1 && c > 0) relax(i, i + cols - 1, Math.SQRT2);
    }
    for (let i = 0; i < n; i += 1) {
      if (this.code[i] !== neverCode) continue;
      const top = Number.isFinite(relief[i]) ? relief[i] : 12.8;
      if (dist[i] >= 1e6) { this.ground[i] = top; continue; }
      const t = Math.min(1, Math.max(0, (dist[i] - 0.5) / 4));
      const floor = edge[i];
      this.ground[i] = floor + (Math.max(top, floor) - floor) * t * t * (3 - 2 * t);
    }
  }

  /** Index of the cell containing (x, z), or -1 outside. */
  cellIndex(x: number, z: number): number {
    const c = Math.floor((x - this.x0) / this.dx);
    const r = Math.floor((z - this.z0) / this.dz);
    if (c < 0 || r < 0 || c >= this.cols || r >= this.rows) return -1;
    return r * this.cols + c;
  }

  private bilinear(values: Float32Array, x: number, z: number): number {
    const fx = Math.min(this.cols - 1, Math.max(0, (x - this.x0) / this.dx - 0.5));
    const fz = Math.min(this.rows - 1, Math.max(0, (z - this.z0) / this.dz - 0.5));
    const c0 = Math.floor(fx), r0 = Math.floor(fz);
    const c1 = Math.min(this.cols - 1, c0 + 1), r1 = Math.min(this.rows - 1, r0 + 1);
    const tx = fx - c0, tz = fz - r0;
    const a = values[r0 * this.cols + c0], b = values[r0 * this.cols + c1];
    const c = values[r1 * this.cols + c0], d = values[r1 * this.cols + c1];
    return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz;
  }

  kAt(x: number, z: number): number {
    return this.bilinear(this.kSmooth, x, z);
  }

  /** Ground height (m) for drawing, including pads that hold the story's dry places at their cell's height. */
  groundAt(x: number, z: number): number {
    let y = this.bilinear(this.ground, x, z);
    for (const pad of this.pads) {
      const d = padDistance(pad, x, z);
      // On the flat top the pad holds fully; around it, it fades out over `blend` (none with a blend of 0).
      if (d > 0 && d >= pad.blend) continue;
      const w = d === 0 || pad.blend <= 0 ? 1 : 1 - d / pad.blend;
      y = Math.max(y, y + (pad.height - y) * w * w * (3 - 2 * w));
    }
    return y;
  }

  /** Water surface (m) at a stage: level within a reach. */
  surfaceAt(x: number, z: number, stage: number): number {
    return this.kAt(x, z) * stage;
  }

  /** Drawn water depth (m) at a point and stage; 0 when dry. */
  depthAt(x: number, z: number, stage: number): number {
    return Math.max(0, this.surfaceAt(x, z, stage) - this.groundAt(x, z));
  }

  /**
   * Hold a place at the height of its own cell: the drawn ground is bilinear between cell centres, so a house a few
   * metres off its cell's centre could otherwise dip toward a lower neighbour and show water the model does not have.
   */
  addPad(pad: Pad): void {
    this.pads.push(pad);
  }

  /** The model's own depth at a cell (cellDepth): null when dry. */
  cellDepth(index: number, stage: number): number | null {
    const code = this.code[index];
    if (code === 255) return null;
    if (code === 0) return this.k[index] * Math.max(0, stage);
    if (!(code * this.step < stage)) return null;
    return this.k[index] * (stage - code * this.step);
  }
}

/** Separable Gaussian blur of `values`, reading and writing only cells where `included(i)`; other cells keep their value. */
function gaussian(values: Float32Array, cols: number, rows: number, sigma: number, included: (i: number) => boolean): Float32Array {
  const radius = Math.ceil(sigma * 2.5);
  const weights = Array.from({ length: radius * 2 + 1 }, (_, i) => Math.exp(-((i - radius) ** 2) / (2 * sigma * sigma)));
  const pass = (input: Float32Array, horizontal: boolean): Float32Array => {
    const out = new Float32Array(input.length);
    for (let r = 0; r < rows; r += 1) {
      for (let c = 0; c < cols; c += 1) {
        const i = r * cols + c;
        let sum = 0, weight = 0;
        for (let o = -radius; o <= radius; o += 1) {
          const cc = horizontal ? c + o : c, rr = horizontal ? r : r + o;
          if (cc < 0 || rr < 0 || cc >= cols || rr >= rows) continue;
          const j = rr * cols + cc;
          if (!included(j)) continue;
          sum += input[j] * weights[o + radius];
          weight += weights[o + radius];
        }
        out[i] = weight > 0 ? sum / weight : input[i];
      }
    }
    return out;
  };
  const blurred = pass(pass(values, true), false);
  const out = new Float32Array(values.length);
  for (let i = 0; i < values.length; i += 1) out[i] = included(i) ? blurred[i] : values[i];
  return out;
}

/** Replay stage (m) at a replay hour, with the replay's own interpolation. */
export function stageAtHour(manifest: Pick<TownManifest, "replay">, hour: number): number {
  return stageAt(hour / 24, manifest.replay.stage_anchors);
}

// --- Reading the bake -------------------------------------------------------------------------------------------------------

/** The raw JSON vectors of the bake (see the `encoding` fields of mae-sai-town.json). */
interface RawManifest extends TownManifest {
  cells: { href: string; cols: number; rows: number; x0: number; z0: number; dx: number; dz: number };
  relief: { href: string };
  cover: { href: string; cols: number; rows: number; x0: number; z0: number; cell_m: number };
  backdrop: { href: string; cols: number; rows: number; x0: number; z0: number; cell_m: number };
  buildings: {
    count: number; ring_start: number[]; coords: number[]; kinds: BuildingKind[]; kind: number[]; floors: number[];
    front: number[]; obb: number[]; rect: number[]; area_m2: number[]; compound: number[];
    home: number; neighbour: number; [key: string]: unknown;
  };
  roads: { count: number; line_start: number[]; coords: number[]; classes: string[]; class: number[]; width_dm: number[]; bridge: number[] };
  trees: { count: number; coords: number[]; kind: number[]; scale: number[] };
  route: {
    destination: string; length_m: number; points: number[]; edges: Array<[number, number, number | null]>; cut_stage_m: number;
    first_cut: { low_point: { x: number; z: number; along_m: number } };
  };
}

/** Decoded PNG pixels: `channels` bytes per pixel, rows top to bottom. */
export interface Pixels {
  width: number;
  height: number;
  channels: number;
  data: Uint8Array;
}

/** Big-endian uint16 in R, G of each pixel minus the offset, in decimetres → metres. */
function heights16(pixels: Pixels, empty: number): Float32Array {
  const out = new Float32Array(pixels.width * pixels.height);
  for (let i = 0; i < out.length; i += 1) {
    const raw = (pixels.data[i * pixels.channels] << 8) | pixels.data[i * pixels.channels + 1];
    out[i] = raw === 0 ? empty : (raw - 2000) / 10;
  }
  return out;
}

function channel(pixels: Pixels, index: number): Uint8Array {
  const out = new Uint8Array(pixels.width * pixels.height);
  for (let i = 0; i < out.length; i += 1) out[i] = pixels.data[i * pixels.channels + index];
  return out;
}

/** The building indices the bake names (Lalita's home, her neighbour, the District Office, the shelter). */
function namedBuilding(raw: RawManifest, ...keys: string[]): number {
  for (const key of keys) {
    const value = raw.buildings[key];
    if (typeof value === "number" && value >= 0) return value;
    if (value && typeof value === "object" && typeof (value as { index?: unknown }).index === "number") return (value as { index: number }).index;
  }
  return -1;
}

/**
 * Decode the bake from its manifest text and its four PNGs (already decoded to pixels). Kept free of fetching and of
 * image decoding, so tests can feed it the committed files.
 */
export function decodeTownPack(manifestText: string, images: { cells: Pixels; relief: Pixels; cover: Pixels; backdrop: Pixels }): TownPack {
  const raw = JSON.parse(manifestText) as RawManifest;
  const { cells: c } = raw;
  if (images.cells.width !== c.cols || images.cells.height !== c.rows) throw new Error("Town cells size mismatch");
  const cells = { cols: c.cols, rows: c.rows, x0: c.x0, z0: c.z0, dx: c.dx, dz: c.dz, code: channel(images.cells, 0), kByte: channel(images.cells, 1), low: channel(images.cells, 2) };
  const relief = heights16(images.relief, Number.NaN);
  const cover = { cols: raw.cover.cols, rows: raw.cover.rows, x0: raw.cover.x0, z0: raw.cover.z0, dx: raw.cover.cell_m, dz: raw.cover.cell_m, data: channel(images.cover, 0) };
  const backdrop = { cols: raw.backdrop.cols, rows: raw.backdrop.rows, x0: raw.backdrop.x0, z0: raw.backdrop.z0, dx: raw.backdrop.cell_m, dz: raw.backdrop.cell_m, height: heights16(images.backdrop, 0) };

  const b = raw.buildings;
  const rings = decodeRuns(b.coords, b.ring_start.slice(0, b.count));
  const buildings: TownBuilding[] = rings.map((ring, index) => {
    const [cx, cz, w, d, angle] = b.obb.slice(index * 5, index * 5 + 5);
    return {
      index,
      ring,
      kind: b.kinds[b.kind[index]],
      floors: b.floors[index],
      front: b.front[index],
      obb: { cx: cx / 10, cz: cz / 10, w: w / 10, d: d / 10, angle: (angle / 100) * (Math.PI / 180) },
      rect: b.rect[index] > 1 ? b.rect[index] / 100 : b.rect[index],
      area: b.area_m2[index],
      compound: b.compound[index],
    };
  });

  const r = raw.roads;
  const lines = decodeRuns(r.coords, r.line_start.slice(0, r.count));
  const roads: TownRoad[] = lines.map((points, index) => ({ points, cls: r.classes[r.class[index]], width: r.width_dm[index] / 10, bridge: r.bridge[index] === 1 }));

  const treePoints = decodeRun(raw.trees.coords);
  const trees: TownTree[] = raw.trees.kind.map((kind, index) => ({ x: treePoints[index * 2], z: treePoints[index * 2 + 1], kind, scale: raw.trees.scale[index] / 100 }));

  const rt = raw.route;
  const route: TownRoute = {
    destination: rt.destination,
    points: decodeRun(rt.points),
    length: rt.length_m,
    edges: rt.edges.map(([from, to, closure]) => ({ from, to, closure: closure ?? Number.POSITIVE_INFINITY })),
    cutStage: rt.cut_stage_m,
    lowPoint: { x: rt.first_cut.low_point.x, z: rt.first_cut.low_point.z, along: rt.first_cut.low_point.along_m },
  };
  const shelterPlace = raw.places.find((place) => place.id === rt.destination);
  const nearestBuilding = (x: number, z: number) => {
    let best = -1, bestD = Infinity;
    for (const building of buildings) {
      const d = Math.hypot(building.obb.cx - x, building.obb.cz - z);
      if (d < bestD) { bestD = d; best = building.index; }
    }
    return best;
  };
  const office = raw.places.find((place) => place.id === "R05");
  const special = {
    home: b.home,
    neighbour: b.neighbour,
    office: namedBuilding(raw, "district_office", "office", "R05") >= 0 ? namedBuilding(raw, "district_office", "office", "R05") : office ? nearestBuilding(office.x, office.z) : -1,
    shelter: namedBuilding(raw, "municipality_office", "shelter", rt.destination) >= 0 ? namedBuilding(raw, "municipality_office", "shelter", rt.destination) : shelterPlace ? nearestBuilding(shelterPlace.x, shelterPlace.z) : -1,
  };
  // The story needs all of these; an incomplete bake stops here with a clear reason (the page then shows the text
  // version) rather than failing somewhere inside the scene.
  const missing = [
    raw.replay.stage_anchors.length === 0 && "replay stage anchors",
    route.edges.length === 0 && "walk edges",
    !Number.isFinite(route.cutStage) && "the walk's cut stage",
    special.home < 0 && "the home's building",
    special.neighbour < 0 && "the neighbours' building",
    special.office < 0 && "the District Office building",
  ].filter(Boolean);
  if (missing.length) throw new Error(`Town bake is incomplete: no ${missing.join(", ")}`);
  return { manifest: raw, cells, relief, cover, backdrop, buildings, roads, trees, route, special };
}

export const TOWN_BASE = "/journey/town/";

/**
 * Fetch and decode the bake. `decode` turns PNG bytes into pixels (the stage passes the replay's own PNG decoder with
 * the browser's inflate, the tests pass Node's zlib).
 */
export async function loadTownPack(decode: (bytes: Uint8Array) => Promise<Pixels>, base = TOWN_BASE, signal?: AbortSignal): Promise<TownPack> {
  const get = async (href: string) => {
    const response = await fetch(href.startsWith("/") ? href : `${base}${href}`, { signal });
    if (!response.ok) throw new Error(`Town file ${href}: ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  };
  const manifestText = new TextDecoder().decode(await get(`${base}mae-sai-town.json`));
  const raw = JSON.parse(manifestText) as RawManifest;
  const [cells, relief, cover, backdrop] = await Promise.all([raw.cells.href, raw.relief.href, raw.cover.href, raw.backdrop.href].map(async (href) => decode(await get(href))));
  return decodeTownPack(manifestText, { cells, relief, cover, backdrop });
}
