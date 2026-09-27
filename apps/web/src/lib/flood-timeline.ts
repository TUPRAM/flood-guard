/**
 * Pure logic for the Mae Sai September 2024 day-by-day flood replay.
 *
 * Mirrors `floodguard.flood_timeline` (Python): water is a HAND threshold
 * reconstruction at an assumed, illustrative river stage. Nothing here is a
 * real-time detector or an official warning. No DOM access in this module.
 */

export type Language = "en" | "th";
export interface Localized { en: string; th: string }

export interface TimelineStats {
  flooded_km2: number;
  tambon_flooded_km2: Record<string, number>;
  road_km_impassable: number;
  road_km_wet: number;
  facilities_wet: number;
}

export interface TimelineDay { date: string; index: number; phase: string; stage_m: number; stats: TimelineStats }
export interface TimelinePhase { id: string; start: string; end: string; label: Localized; summary: Localized }

export interface TimelineObservation {
  id: string;
  sensor: string;
  kind: "optical" | "radar";
  utc: string;
  local: string;
  label: Localized;
  pass?: string;
  relative_orbit?: number;
}

export interface HashedAsset { href: string; sha256: string; bytes: number }

/** Interpolation knot of the assumed stage: `t` in days since 2024-09-09T00:00 ICT. */
export interface StageAnchor { t: number; stage_m: number }

/** Share of an area that lies inside the model grid. */
export interface AreaCoverage { modelled_km2: number; total_km2: number }

export interface TimelineLayer extends HashedAsset {
  id: string;
  kind: "terrain" | "sentinel-2" | "sentinel-1" | "sentinel-1-change";
  date: string | null;
  scene?: string;
}

export interface TimelineSource { id: string; name: string; licence: string; timestamp: string; attribution: string }

export interface TimelineManifest {
  study_id: string;
  revision: string;
  data_mode: string;
  official_warning: false;
  real_time: false;
  confidence: string;
  confidence_reason: string;
  source_timestamp: string;
  timezone: string;
  area: Localized;
  bounds: [[number, number], [number, number]];
  hand: HashedAsset & { width: number; height: number; step_m: number; channel_code: number; never_code: number; stream_threshold_km2?: number };
  impassable_depth_m: number;
  pixel_area_m2: number;
  /** Sorted stage knots (local-noon keyframes plus sub-daily anchors); the replay interpolates over these. */
  stage_anchors: StageAnchor[];
  /** Modelled versus total area per subdistrict id. */
  tambon_coverage: Record<string, AreaCoverage>;
  /** District land inside the model grid, and why the rest is not modelled. */
  model_coverage: { modelled_km2: number; district_km2: number; reason: string };
  facilities_count: { total: number; modelled: number };
  roads_not_modelled_km: number;
  phases: TimelinePhase[];
  days: TimelineDay[];
  observations: TimelineObservation[];
  layers: TimelineLayer[];
  vectors: Record<"tambons" | "roads" | "facilities", HashedAsset & { features: number }>;
  tambon_histograms: Record<string, number[]>;
  s1_anchor: {
    threshold_db_dn: number;
    newly_dark_km2: number;
    best_fit_stage_m: number;
    best_fit_model_km2: number;
    iou_at_best_fit: number;
    scope?: string;
    reconstruction_stage_at_pass_m: number;
  };
  sources: TimelineSource[];
  assumptions: string[];
  limitations: string[];
}

/** Minimal GeoJSON shapes used by the replay (avoids a hard dependency on @types/geojson). */
export interface GeoFeature<G, P> { type: "Feature"; geometry: G; properties: P }
export interface GeoCollection<G, P> { type: "FeatureCollection"; features: GeoFeature<G, P>[] }
export type LineGeometry = { type: "LineString"; coordinates: [number, number][] };
export type PointGeometry = { type: "Point"; coordinates: [number, number] };
export type AreaGeometry = { type: "Polygon" | "MultiPolygon"; coordinates: unknown };
/** Road piece: class, lowest sampled HAND (m, `null` never floods), `m` = inside the model grid, length (m), subdistrict. */
export interface RoadProps { c: string; h: number | null; m: boolean; len: number; t: string; n?: string }
/** Candidate facility: `m` = inside the model grid; `h` lowest HAND (m) or `null` when it never floods. */
export interface FacilityProps { id: string; type: string; n: string; t: string; h: number | null; m: boolean }
export interface TambonProps { id: string; en: string; th: string }

export type RoadState = "dry" | "wet" | "impassable";

export const DAY_MS = 86_400_000;
const ICT_OFFSET_MS = 7 * 3_600_000;
/** 2024-09-09T00:00+07:00, the replay origin (t = 0). */
export const TIMELINE_EPOCH_MS = Date.UTC(2024, 8, 8, 17);
/** Replay span in days (9 Sep 00:00 to 20 Sep 00:00 ICT). */
export const TIMELINE_END_T = 11;

/** Days since 2024-09-09T00:00 ICT for an instant (Date, ISO string with offset, or epoch ms). */
export function tFromDate(input: Date | string | number): number {
  const ms = input instanceof Date ? input.getTime() : typeof input === "string" ? Date.parse(input) : input;
  return (ms - TIMELINE_EPOCH_MS) / DAY_MS;
}

/** Days since the replay origin for local ICT midnight of a `YYYY-MM-DD` date. */
export function tFromLocalDate(isoDate: string): number {
  return tFromDate(`${isoDate}T00:00:00+07:00`);
}

/** Instant for a replay position. */
export function dateFromT(t: number): Date {
  return new Date(TIMELINE_EPOCH_MS + t * DAY_MS);
}

/**
 * Assumed stage at replay position `t`: linear interpolation over the sorted `stage_anchors`
 * knots, held constant outside them (same as `numpy.interp` in `floodguard.flood_timeline.stage_at`).
 */
export function stageAt(t: number, anchors: readonly StageAnchor[]): number {
  const n = anchors.length;
  if (n === 0) throw new Error("at least one stage anchor is required");
  if (Number.isNaN(t)) return Number.NaN;
  if (t <= anchors[0].t) return anchors[0].stage_m;
  if (t >= anchors[n - 1].t) return anchors[n - 1].stage_m;
  let lo = 0;
  let hi = n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (anchors[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = anchors[lo];
  const b = anchors[hi];
  if (t === a.t) return a.stage_m;
  const slope = (b.stage_m - a.stage_m) / (b.t - a.t);
  return slope * (t - a.t) + a.stage_m;
}

/** Whole local hours since the replay origin for `t`; the one quantiser used by the slider, readout and day buttons. */
export function hourIndex(t: number): number {
  return Math.floor(t * 24 + 1e-6);
}

/** Phase covering replay position `t` (phases span local start 00:00 to end 24:00), clamped to the ends. */
export function phaseAt<P extends Pick<TimelinePhase, "start" | "end">>(t: number, phases: readonly P[]): P {
  if (phases.length === 0) throw new Error("at least one phase is required");
  for (const phase of phases) {
    if (t >= tFromLocalDate(phase.start) && t < tFromLocalDate(phase.end) + 1) return phase;
  }
  return t < tFromLocalDate(phases[0].start) ? phases[0] : phases[phases.length - 1];
}

/** Out-of-channel flooded km² implied by a 256-bin HAND code histogram at `stage` (codes 1..254 only). */
export function floodedKm2(histogram: readonly number[], stage: number, step: number, pixelAreaM2: number): number {
  if (histogram.length !== 256) throw new Error("histogram must have 256 bins");
  let cells = 0;
  for (let code = 1; code < 255; code += 1) {
    if (code * step < stage) cells += histogram[code];
  }
  return (cells * pixelAreaM2) / 1e6;
}

/**
 * Road state from its lowest sampled HAND (m); `null` never floods under these keyframes.
 * Depth is rounded to 1e-6 m first, like Python `round(x, 6)`, so 3.5 - 3.2 counts as 0.3 m.
 */
export function roadState(minHandM: number | null, stage: number, impassableDepthM = 0.3): RoadState {
  if (minHandM === null) return "dry";
  const depth = Math.round((stage - minHandM) * 1e6) / 1e6;
  if (depth >= impassableDepthM) return "impassable";
  if (depth > 0) return "wet";
  return "dry";
}

/** Reconstructed depth (m) at a candidate facility, or 0 when dry / never flooding. */
export function facilityDepth(minHandM: number | null, stage: number): number {
  return minHandM === null ? 0 : Math.max(0, stage - minHandM);
}

/** True when a modelled candidate facility is in reconstructed water (same rule as the baked `facilities_wet`). */
export function facilityWet(facility: Pick<FacilityProps, "h" | "m">, stage: number): boolean {
  return facility.m && facility.h !== null && stage - facility.h > 0;
}

export interface FacilityInWater<F> { facility: F; depth: number }

/** Modelled candidate facilities in water at `stage`, deepest first (ties by name, then id). */
export function facilitiesInWater<F extends Pick<FacilityProps, "h" | "m" | "id" | "n">>(
  facilities: readonly F[],
  stage: number,
): FacilityInWater<F>[] {
  return facilities
    .filter((facility) => facilityWet(facility, stage))
    .map((facility) => ({ facility, depth: facilityDepth(facility.h, stage) }))
    .sort((a, b) => b.depth - a.depth || a.facility.n.localeCompare(b.facility.n) || a.facility.id.localeCompare(b.facility.id));
}

/** Modelled share (0-1) of a subdistrict, or 1 when coverage is unknown. */
export function coverageShare(coverage: AreaCoverage | undefined): number {
  if (!coverage || !(coverage.total_km2 > 0)) return 1;
  return Math.min(1, Math.max(0, coverage.modelled_km2 / coverage.total_km2));
}

/**
 * Python `round(value, digits)` for non-negative values: rounds the exact binary value
 * (like `toFixed`), with exact decimal ties going to the even digit.
 */
export function roundLikePython(value: number, digits: number): number {
  const exact = value.toFixed(100);
  const cut = exact.indexOf(".") + 1 + digits;
  if (/^50*$/.test(exact.slice(cut))) {
    const kept = exact.slice(0, cut);
    const lastDigit = Number(kept.replace(".", "").slice(-1));
    const truncated = Number(kept);
    return lastDigit % 2 === 0 ? truncated : Number((truncated + 10 ** -digits).toFixed(digits));
  }
  return Number(value.toFixed(digits));
}

const roundTo = roundLikePython;

/**
 * District statistics at `stage`, identical in shape and rounding to `timeline.json` `days[].stats`.
 * Roads and facilities outside the model grid (`m: false`) are excluded from every figure.
 */
export function districtStats(
  manifest: Pick<TimelineManifest, "tambon_histograms" | "hand" | "pixel_area_m2" | "impassable_depth_m">,
  stage: number,
  roads: readonly Pick<RoadProps, "h" | "len" | "m">[],
  facilities: readonly Pick<FacilityProps, "h" | "m">[],
): TimelineStats {
  const tambon: Record<string, number> = {};
  let total = 0;
  for (const [id, histogram] of Object.entries(manifest.tambon_histograms)) {
    tambon[id] = roundTo(floodedKm2(histogram, stage, manifest.hand.step_m, manifest.pixel_area_m2), 3);
    total += tambon[id];
  }
  let impassable = 0;
  let wet = 0;
  for (const road of roads) {
    if (!road.m) continue;
    const state = roadState(road.h, stage, manifest.impassable_depth_m);
    if (state === "impassable") impassable += road.len;
    else if (state === "wet") wet += road.len;
  }
  const facilitiesWet = facilities.filter((facility) => facilityWet(facility, stage)).length;
  return {
    flooded_km2: roundTo(total, 3),
    tambon_flooded_km2: tambon,
    road_km_impassable: roundTo(impassable / 1000, 2),
    road_km_wet: roundTo(wet / 1000, 2),
    facilities_wet: facilitiesWet,
  };
}

export interface DepthClass { min: number; max: number; rgba: [number, number, number, number]; label: string }

/** Five-class depth ramp (upper bound inclusive): (0,0.3], (0.3,1], (1,2], (2,3], >3 m. */
export const DEPTH_CLASSES: readonly DepthClass[] = [
  { min: 0, max: 0.3, rgba: [158, 202, 225, 225], label: "0–0.3 m" },
  { min: 0.3, max: 1, rgba: [107, 174, 214, 232], label: "0.3–1 m" },
  { min: 1, max: 2, rgba: [49, 130, 189, 238], label: "1–2 m" },
  { min: 2, max: 3, rgba: [8, 81, 156, 242], label: "2–3 m" },
  { min: 3, max: Infinity, rgba: [8, 48, 107, 246], label: "> 3 m" },
];
/** Mapped river channel (code 0), always water. */
export const CHANNEL_RGBA: readonly [number, number, number, number] = [0, 96, 107, 255];

export const rgbaCss = ([r, g, b, a]: readonly number[]) => `rgb(${r} ${g} ${b} / ${Math.round((a / 255) * 100)}%)`;

/** Depth class index for a positive depth. */
export function depthClassIndex(depth: number): number {
  for (let index = 0; index < DEPTH_CLASSES.length; index += 1) {
    if (depth <= DEPTH_CLASSES[index].max) return index;
  }
  return DEPTH_CLASSES.length - 1;
}

const pack = ([r, g, b, a]: readonly number[], littleEndian: boolean) =>
  (littleEndian ? ((a << 24) | (b << 16) | (g << 8) | r) : ((r << 24) | (g << 16) | (b << 8) | a)) >>> 0;

/**
 * 256-entry lookup of packed RGBA for each HAND code at `stage`, for a Uint32 view of ImageData
 * (little-endian ABGR by default). Code 255 and dry codes are transparent (0).
 * Pass `out` (length 256) to reuse a buffer instead of allocating one.
 */
export function buildDepthLut(stage: number, step: number, littleEndian = true, out?: Uint32Array): Uint32Array {
  if (out && out.length !== 256) throw new Error("LUT buffer must have 256 entries");
  const lut = out ?? new Uint32Array(256);
  if (out) lut.fill(0);
  lut[0] = pack(CHANNEL_RGBA, littleEndian);
  for (let code = 1; code < 255; code += 1) {
    const hand = code * step;
    if (hand < stage) lut[code] = pack(DEPTH_CLASSES[depthClassIndex(stage - hand)].rgba, littleEndian);
  }
  return lut;
}

/** True when two lookup tables would paint identical pixels. */
export function lutEquals(a: Uint32Array | null, b: Uint32Array): boolean {
  if (!a || a.length !== b.length) return false;
  for (let index = 0; index < a.length; index += 1) if (a[index] !== b[index]) return false;
  return true;
}

/** Pixel indices that can ever be wet up to `maxStage` (channel plus codes below it). */
export function waterCandidates(codes: Uint8Array, maxStage: number, step: number): Uint32Array {
  const limit = maxStage + step;
  let count = 0;
  for (let index = 0; index < codes.length; index += 1) {
    const code = codes[index];
    if (code === 0 || (code !== 255 && code * step < limit)) count += 1;
  }
  const out = new Uint32Array(count);
  let cursor = 0;
  for (let index = 0; index < codes.length; index += 1) {
    const code = codes[index];
    if (code === 0 || (code !== 255 && code * step < limit)) out[cursor++] = index;
  }
  return out;
}

/** Write `lut[code]` into `pixels` for candidate indices only (all other pixels stay untouched). */
export function paintDepth(codes: Uint8Array, candidates: Uint32Array, lut: Uint32Array, pixels: Uint32Array): void {
  for (let index = 0; index < candidates.length; index += 1) {
    const pixel = candidates[index];
    pixels[pixel] = lut[codes[pixel]];
  }
}

export interface LatestObservation<O> { observation: O; ageDays: number }

export interface ObservationGap<O> { before: O; after: O }

/**
 * The imagery gap containing `t`: the latest observation (any sensor) before `t` and the next one after it,
 * when they are more than `minGapDays` apart and `t` lies strictly between them. `null` otherwise
 * (including exactly at an acquisition).
 */
export function observationGap<O extends Pick<TimelineObservation, "local">>(
  t: number,
  observations: readonly O[],
  minGapDays = 1,
): ObservationGap<O> | null {
  let before: { observation: O; at: number } | null = null;
  let after: { observation: O; at: number } | null = null;
  for (const observation of observations) {
    const at = tFromDate(observation.local);
    if (at <= t && (!before || at > before.at)) before = { observation, at };
    if (at > t && (!after || at < after.at)) after = { observation, at };
  }
  if (!before || !after || before.at === t || after.at - before.at <= minGapDays) return null;
  return { before: before.observation, after: after.observation };
}

/** Most recent observation at or before `t` (optionally of one kind), with its age in days. */
export function latestObservation<O extends Pick<TimelineObservation, "local" | "kind">>(
  t: number,
  observations: readonly O[],
  kind?: TimelineObservation["kind"],
): LatestObservation<O> | null {
  let best: LatestObservation<O> | null = null;
  for (const observation of observations) {
    if (kind && observation.kind !== kind) continue;
    const at = tFromDate(observation.local);
    if (at > t) continue;
    if (!best || at > t - best.ageDays) best = { observation, ageDays: t - at };
  }
  return best;
}

const WEEKDAYS: Record<Language, string[]> = {
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
  th: ["อา.", "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส."],
};
const MONTHS: Record<Language, string[]> = {
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  th: ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."],
};

function ictParts(ms: number) {
  const local = new Date(ms + ICT_OFFSET_MS);
  return {
    weekday: local.getUTCDay(), day: local.getUTCDate(), month: local.getUTCMonth(), year: local.getUTCFullYear(),
    hour: local.getUTCHours(), minute: local.getUTCMinutes(),
  };
}

const pad2 = (value: number) => String(value).padStart(2, "0");

/** "Thu 12 Sep 2024 · 12:00 ICT" / "พฤ. 12 ก.ย. 2024 · 12:00 น." (CE year as elsewhere in Studio; time floored to the hour). */
export function formatMoment(t: number, language: Language): string {
  const hourT = hourIndex(t) / 24;
  const p = ictParts(TIMELINE_EPOCH_MS + hourT * DAY_MS);
  return language === "th"
    ? `${WEEKDAYS.th[p.weekday]} ${p.day} ${MONTHS.th[p.month]} ${p.year} · ${pad2(p.hour)}:00 น.`
    : `${WEEKDAYS.en[p.weekday]} ${p.day} ${MONTHS.en[p.month]} ${p.year} · ${pad2(p.hour)}:00 ICT`;
}

/** "12 Sep" / "12 ก.ย." for a local ISO date or instant. */
export function formatShortDate(input: string, language: Language): string {
  const p = ictParts(input.length === 10 ? Date.parse(`${input}T00:00:00+07:00`) : Date.parse(input));
  return `${p.day} ${MONTHS[language][p.month]}`;
}

/** "16 Sep 06:16" style local stamp for an observation. */
export function formatLocalStamp(input: string, language: Language): string {
  const p = ictParts(Date.parse(input));
  return `${p.day} ${MONTHS[language][p.month]} ${pad2(p.hour)}:${pad2(p.minute)}${language === "th" ? " น." : " ICT"}`;
}

/** Human age of an image relative to the replay moment (negative = image is later). */
export function formatAge(ageDays: number, language: Language): string {
  const before = ageDays >= 0;
  const magnitude = Math.abs(ageDays);
  const hours = Math.round(magnitude * 24);
  const days = Math.round(magnitude);
  if (hours < 1) return language === "th" ? "ตรงกับช่วงเวลานี้" : "at this moment";
  const amount = magnitude < 1
    ? language === "th" ? `${hours} ชั่วโมง` : `${hours} hour${hours === 1 ? "" : "s"}`
    : language === "th" ? `${days} วัน` : `${days} day${days === 1 ? "" : "s"}`;
  if (language === "th") return before ? `${amount}ก่อนช่วงเวลานี้` : `${amount}หลังช่วงเวลานี้`;
  return before ? `${amount} before this moment` : `${amount} after this moment`;
}

export interface GrayRaster { width: number; height: number; data: Uint8Array }
export type Inflate = (data: Uint8Array) => Promise<Uint8Array> | Uint8Array;

/**
 * Decode an 8-bit, non-interlaced grayscale PNG into exact byte codes.
 * Decoding the file directly avoids browser colour management and canvas read-back noise.
 */
export async function decodeGrayPng(bytes: Uint8Array, inflate: Inflate): Promise<GrayRaster> {
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (bytes.length < 8 || signature.some((value, index) => bytes[index] !== value)) throw new Error("Not a PNG file");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 8;
  let width = 0;
  let height = 0;
  const parts: Uint8Array[] = [];
  while (offset + 8 <= bytes.length) {
    const length = view.getUint32(offset);
    const type = String.fromCharCode(bytes[offset + 4], bytes[offset + 5], bytes[offset + 6], bytes[offset + 7]);
    if (type === "IHDR") {
      width = view.getUint32(offset + 8);
      height = view.getUint32(offset + 12);
      if (bytes[offset + 16] !== 8 || bytes[offset + 17] !== 0 || bytes[offset + 20] !== 0) {
        throw new Error("Expected an 8-bit non-interlaced grayscale PNG");
      }
    } else if (type === "IDAT") {
      parts.push(bytes.subarray(offset + 8, offset + 8 + length));
    } else if (type === "IEND") {
      break;
    }
    offset += 12 + length;
  }
  if (!width || !height || parts.length === 0) throw new Error("PNG is missing image data");
  const joined = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let cursor = 0;
  for (const part of parts) {
    joined.set(part, cursor);
    cursor += part.length;
  }
  const raw = await inflate(joined);
  const stride = width + 1;
  if (raw.length < height * stride) throw new Error("PNG image data is truncated");
  const out = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * stride];
    const source = y * stride + 1;
    const row = y * width;
    const previous = row - width;
    for (let x = 0; x < width; x += 1) {
      const value = raw[source + x];
      const left = x > 0 ? out[row + x - 1] : 0;
      const up = y > 0 ? out[previous + x] : 0;
      const upLeft = x > 0 && y > 0 ? out[previous + x - 1] : 0;
      let result: number;
      switch (filter) {
        case 0: result = value; break;
        case 1: result = value + left; break;
        case 2: result = value + up; break;
        case 3: result = value + ((left + up) >> 1); break;
        case 4: {
          const estimate = left + up - upLeft;
          const dLeft = Math.abs(estimate - left);
          const dUp = Math.abs(estimate - up);
          const dUpLeft = Math.abs(estimate - upLeft);
          result = value + (dLeft <= dUp && dLeft <= dUpLeft ? left : dUp <= dUpLeft ? up : upLeft);
          break;
        }
        default: throw new Error(`Unsupported PNG filter ${filter}`);
      }
      out[row + x] = result & 255;
    }
  }
  return { width, height, data: out };
}

/** zlib inflate using the platform DecompressionStream (browsers and Node 18+). */
export async function inflateZlib(data: Uint8Array): Promise<Uint8Array> {
  const copy = new Uint8Array(data);
  const stream = new Blob([copy]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}
