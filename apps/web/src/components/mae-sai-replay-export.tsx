"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  buildDepthLut,
  buildFactorDepthLut,
  CHANNEL_RGBA,
  coverageComplete,
  dateFromT,
  DEPTH_CLASSES,
  districtStats,
  FACTOR_LUT_SIZE,
  formatMoment,
  formatShortDate,
  hourIndex,
  latestObservation,
  lutEquals,
  manifestRevision,
  mercatorY,
  paintDepth,
  paintLowConfidence,
  phaseAt,
  projectToFrame,
  rgbaCss,
  roadState,
  stageAt,
  thaiYear,
  TIMELINE_END_T,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type Language,
  type LineGeometry,
  type ReportedShelter,
  type RoadProps,
  type RoadState,
  type TambonProps,
  type TimelineManifest,
} from "@/lib/flood-timeline";
import { reportedShelterCheck, reportedSiteRole } from "@/lib/flood-timeline-evacuation";

import styles from "./mae-sai-flood-timeline.module.css";

/** Replay seconds per day in the exported video (the whole 9–19 Sep window takes 22 s). */
export const VIDEO_SECONDS_PER_DAY = 2;
export const VIDEO_FPS = 30;
export const VIDEO_WIDTH = 720;
export const PNG_WIDTH = 1440;
/** Last moment in the video: 19 Sep 23:00 ICT, the final hour of the replay window. */
const VIDEO_END_T = TIMELINE_END_T - 1e-6;
/** Opening title card, the hold on the last replay frame, and the closing card, in seconds. */
export const VIDEO_TITLE_SECONDS = 1;
export const VIDEO_HOLD_SECONDS = 0.4;
export const VIDEO_END_CARD_SECONDS = 1;
const VIDEO_REPLAY_SECONDS = VIDEO_END_T * VIDEO_SECONDS_PER_DAY;
/** Whole video: title card, the 9–19 Sep replay, a short hold on its last frame, then the end card. */
export const VIDEO_TOTAL_SECONDS = VIDEO_TITLE_SECONDS + VIDEO_REPLAY_SECONDS + VIDEO_HOLD_SECONDS + VIDEO_END_CARD_SECONDS;

/**
 * Video shapes: "portrait" is the study area with the caption band under it (720 px wide); "landscape" is 16:9
 * (1280 x 720) with the map on the left and the caption and legend beside it, for slides and players.
 */
export type VideoFormat = "portrait" | "landscape";
export const VIDEO_FORMATS: Readonly<Record<VideoFormat, { width: number }>> = { portrait: { width: VIDEO_WIDTH }, landscape: { width: 1280 } };

/** Preferred recording formats, most compatible first. */
export const VIDEO_TYPES = [
  { mime: "video/mp4;codecs=avc1.42E01E", ext: "mp4", label: "MP4" },
  { mime: "video/webm;codecs=vp9", ext: "webm", label: "WebM" },
  { mime: "video/webm", ext: "webm", label: "WebM" },
] as const;
export type VideoType = (typeof VIDEO_TYPES)[number];

/** Map symbols shared with the live map: a 24-unit star (reported shelters), its strike, and a diamond (command site). */
export const STAR_PATH = "M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z";
export const STAR_SLASH_PATH = "M3.5 21 20.5 3";
export const DIAMOND_PATH = "M12 2.5l9.5 9.5-9.5 9.5L2.5 12z";

/** First recording format the browser supports, or null. */
export function pickVideoType(isTypeSupported: (mime: string) => boolean): VideoType | null {
  return VIDEO_TYPES.find((type) => {
    try {
      return isTypeSupported(type.mime);
    } catch {
      return false;
    }
  }) ?? null;
}

/** Replay position for a replay clock (seconds since the replay part began), clamped to the window's last hour. */
export function videoReplayT(elapsedSeconds: number): number {
  return Math.min(VIDEO_END_T, Math.max(0, elapsedSeconds / VIDEO_SECONDS_PER_DAY));
}

/** What the video shows `elapsed` seconds after recording began: the title card, a replay moment, the end card, or done. */
export type VideoPart = { part: "title" } | { part: "replay"; t: number } | { part: "end" } | { part: "done" };
export function videoPart(elapsed: number): VideoPart {
  if (elapsed < VIDEO_TITLE_SECONDS) return { part: "title" };
  const replay = elapsed - VIDEO_TITLE_SECONDS;
  if (replay < VIDEO_REPLAY_SECONDS + VIDEO_HOLD_SECONDS) return { part: "replay", t: videoReplayT(replay) };
  if (replay < VIDEO_REPLAY_SECONDS + VIDEO_HOLD_SECONDS + VIDEO_END_CARD_SECONDS) return { part: "end" };
  return { part: "done" };
}

/** Download name for a still of replay position `t`: mae-sai-flood-2024-09-12-1200-ict.png. */
export function pngFileName(t: number): string {
  const local = new Date(Date.UTC(2024, 8, 9) + hourIndex(t) * 3_600_000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `mae-sai-flood-2024-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}-${pad(local.getUTCHours())}00-ict.png`;
}

/** Download name for a recorded video: mae-sai-flood-2024.mp4, or mae-sai-flood-2024-16x9.webm for the 16:9 shape. */
export function videoFileName(format: VideoFormat, ext: string): string {
  return `mae-sai-flood-2024${format === "landscape" ? "-16x9" : ""}.${ext}`;
}

/** Everything the offscreen renderer needs; all of it is already loaded by the replay page. */
export interface ReplayExportSource {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  roadProps: readonly RoadProps[];
  facilityProps: readonly FacilityProps[];
  /** Subdistrict outlines, drawn thinly for orientation and used to place the Myanmar label north of the district. */
  tambons?: GeoCollection<AreaGeometry, TambonProps>;
  /**
   * HAND codes, depth-factor keys and wet-able cells; `lowCells`/`lowStripes` are the low-confidence cells and their
   * hatch, present only when the manifest declares the low-confidence channel.
   */
  hand: { codes: Uint8Array; factorKeys: Uint16Array | null; candidates: Uint32Array; lowCells?: Uint32Array | null; lowStripes?: Uint8Array | null };
}

export interface ExportRenderer {
  canvas: HTMLCanvasElement;
  /** Draw replay position `t` (days since 9 Sep 00:00 ICT) at the full area-of-interest extent. */
  draw: (t: number) => void;
  /** Opening card over the first frame: title, what the video shows, and that it is a model, not real-time or a warning. */
  drawTitle: () => void;
  /** Closing card over the last frame: end of the window, the model peak, sources and the study revision. */
  drawEnd: () => void;
}

/** A place label for the exported frame, positioned from the data (see `exportPlaceLabels`). */
export interface PlaceLabel {
  kind: "bridge" | "town" | "country";
  lon: number;
  lat: number;
  text: { en: string; th: string };
}

/** Mapped Thai name of Highway 1, whose northern end is the Mae Sai–Tachileik border bridge over the Sai River. */
const HIGHWAY_1 = "ถนนพหลโยธิน";

/** Ring vertices of a Polygon or MultiPolygon, as [lon, lat] pairs. */
function areaRings(geometry: AreaGeometry): [number, number][][] {
  if (geometry.type === "Polygon") return geometry.coordinates as [number, number][][];
  return (geometry.coordinates as [number, number][][][]).flat();
}

/**
 * Orientation labels for the exports, placed from the data rather than typed-in coordinates: the border bridge at the
 * northern end of Highway 1 (Phahonyothin Rd) over the Sai River, Mae Sai town beside it, and Myanmar (Tachileik) north
 * of the district's northernmost point. Empty when the road data has no Highway 1.
 */
export function exportPlaceLabels(
  roads: readonly { geometry: LineGeometry; properties: Pick<RoadProps, "n"> }[],
  tambons: readonly { geometry: AreaGeometry }[] = [],
  bounds?: TimelineManifest["bounds"],
): PlaceLabel[] {
  let bridge: [number, number] | null = null;
  for (const road of roads) {
    if (road.properties.n?.trim() !== HIGHWAY_1) continue;
    for (const [lon, lat] of road.geometry.coordinates) if (!bridge || lat > bridge[1]) bridge = [lon, lat];
  }
  if (!bridge) return [];
  const [lon, lat] = bridge;
  const labels: PlaceLabel[] = [
    { kind: "bridge", lon, lat, text: { en: "Border bridge over the Sai River", th: "สะพานข้ามแม่น้ำสาย (ชายแดน)" } },
    { kind: "town", lon, lat, text: { en: "Mae Sai town", th: "ตัวเมืองแม่สาย" } },
  ];
  let north = lat;
  for (const tambon of tambons) for (const ring of areaRings(tambon.geometry)) for (const [, y] of ring) north = Math.max(north, y);
  const myanmar = Math.min(north + 0.012, bounds ? bounds[1][0] - 0.008 : Infinity);
  if (myanmar > lat) labels.push({ kind: "country", lon, lat: myanmar, text: { en: "MYANMAR (Tachileik)", th: "เมียนมา (ท่าขี้เหล็ก)" } });
  return labels;
}

const EARTH_RADIUS_M = 6_378_137;

/**
 * Scale bar for an export frame: the largest round length (10, 5, 2 or 1 km) no wider than `maxPixels`, and its width
 * in pixels. The frame is linear in Web Mercator, so ground metres per pixel are taken at the frame's middle latitude.
 */
export function exportScaleBar(bounds: TimelineManifest["bounds"], frameWidth: number, maxPixels: number): { km: number; pixels: number } {
  const [[south, west], [north, east]] = bounds;
  const metresPerPixel = ((((east - west) * Math.PI) / 180) * EARTH_RADIUS_M * Math.cos((((south + north) / 2) * Math.PI) / 180)) / frameWidth;
  const km = [10, 5, 2, 1].find((value) => (value * 1000) / metresPerPixel <= maxPixels) ?? 1;
  return { km, pixels: (km * 1000) / metresPerPixel };
}

/** Words (Thai by dictionary segmentation where the browser supports it) and the spaces between them. */
function textSegments(text: string, language: Language): string[] {
  if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
    return [...new Intl.Segmenter(language === "th" ? "th" : "en", { granularity: "word" }).segment(text)].map((part) => part.segment);
  }
  return text.split(/(\s+)/);
}

/** Greedy line wrap of `text` to `maxWidth` as measured by `measure`; a single word wider than the line keeps its own line. */
export function wrapText(measure: (value: string) => number, text: string, maxWidth: number, language: Language): string[] {
  const lines: string[] = [];
  let line = "";
  for (const part of textSegments(text, language)) {
    const next = line + part;
    if (!line.trim() || measure(next.trimEnd()) <= maxWidth) {
      line = line.trim() ? next : part.trimStart();
      continue;
    }
    lines.push(line.trimEnd());
    line = part.trimStart();
  }
  if (line.trim()) lines.push(line.trimEnd());
  return lines;
}

const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
const FONT_STACK = '"Inter Variable", "Noto Sans Thai Variable", system-ui, sans-serif';
const EXPORT_ROAD_STYLES: Record<RoadState | "unmodelled", { color: string; width: number; alpha: number; dash?: number[] }> = {
  dry: { color: "#d7dde6", width: 0.7, alpha: 0.5 },
  wet: { color: "#e8a526", width: 1.6, alpha: 0.95 },
  impassable: { color: "#e53935", width: 2.2, alpha: 1 },
  unmodelled: { color: "#7b8595", width: 1.1, alpha: 0.9, dash: [4, 4] },
};
const even = (value: number) => Math.max(2, Math.round(value / 2) * 2);

function copy(language: Language, manifest: Pick<TimelineManifest, "confidence" | "model_coverage">) {
  const th = language === "th";
  const level = manifest.confidence.toLowerCase() === "low" ? (th ? "ต่ำ" : "low") : manifest.confidence;
  const modelled = Math.round(manifest.model_coverage.modelled_km2);
  const district = Math.round(manifest.model_coverage.district_km2);
  const complete = coverageComplete(manifest.model_coverage);
  return {
    level,
    // The picture covers the whole study frame (including Tachileik, Myanmar); the figures do not.
    scope: complete
      ? th
        ? `ตัวเลขครอบคลุมเฉพาะอำเภอแม่สาย (${district} ตร.กม. จำลองครบทั้งพื้นที่) ไม่ใช่ทั้งภาพ`
        : `Figures: Mae Sai district only (${district} km², fully modelled), not the whole image`
      : th
        ? `ตัวเลขครอบคลุมเฉพาะอำเภอแม่สาย ส่วนที่แบบจำลองครอบคลุม (${modelled} จาก ${district} ตร.กม.) ไม่ใช่ทั้งภาพ`
        : `Figures: Mae Sai district, modelled part only (${modelled} of ${district} km²), not the whole image`,
    title: th ? `น้ำท่วมแม่สาย กันยายน ${thaiYear(2024)} — ไล่เรียงรายวัน` : "Mae Sai flood, September 2024 — day by day",
    stage: th ? "ระดับน้ำสมมุติ" : "assumed stage",
    metres: th ? "ม." : "m",
    flooded: th ? "แบบจำลอง: น้ำท่วม ≈" : "Model: flooded ≈",
    km2: th ? "ตร.กม." : "km²",
    impassable: th ? "ถนนสัญจรไม่ได้ ≈" : "impassable roads ≈",
    km: th ? "กม." : "km",
    imagery: th ? "ภาพ" : "Imagery",
    noImagery: th ? "ไม่มีภาพ" : "no imagery",
    people: th ? "ผู้อยู่อาศัยตามแบบจำลองในพื้นที่น้ำท่วม ≈" : "Modelled residents in flood water ≈",
    peopleUnit: th ? "คน" : "",
    // No brackets around the Thai year label's own "(2024)", so brackets never nest.
    peopleSource: th ? `แบบจำลอง WorldPop 2020, CC BY 4.0 · ไม่ใช่ประชากรปี ${thaiYear(2024)}` : "(WorldPop 2020 model, CC BY 4.0; not the 2024 population)",
    notice: th
      ? `การจำลองจากแบบจำลอง — ไม่ใช่การสังเกตการณ์ · FloodGuard · ความเชื่อมั่น: ${level} · ไม่ใช่ข้อมูลเรียลไทม์หรือคำเตือนทางการ`
      : `Model reconstruction — not observed · FloodGuard · confidence: ${level} · not real-time, not an official warning`,
    legendDepth: th ? "ความลึก (แบบจำลอง)" : "Depth (model)",
    river: th ? "ร่องน้ำ" : "River",
    wet: th ? "ถนนมีน้ำ" : "Wet road",
    cut: th ? "สัญจรไม่ได้ ≥ 0.3 ม." : "Impassable ≥ 0.3 m",
    lowConfidence: th
      ? "น้ำที่มีความเชื่อมั่นต่ำ: พื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง"
      : "Low-confidence water: flat or filled low ground in the elevation model",
    reported: th ? `ที่พักพิงที่มีรายงาน ${thaiYear(2024)}` : "Shelter reported, 2024",
    reportedFloods: th ? "…ท่วมที่ระดับสูงสุดของแบบจำลอง" : "…floods at the model peak",
    command: th ? "ศูนย์บัญชาการ (ไม่ใช่ที่พักพิง)" : "Command site (not a shelter)",
    credits: "Contains modified Copernicus Sentinel data 2024 · © OpenStreetMap contributors · Copernicus DEM © DLR e.V., Airbus DS · WorldPop",
  };
}

/** Longest prefix of `text` (plus an ellipsis) that fits `maxWidth` in the current font. */
function fitText(context: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (context.measureText(text).width <= maxWidth) return text;
  let low = 0;
  let high = text.length;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (context.measureText(`${text.slice(0, mid)}…`).width <= maxWidth) low = mid;
    else high = mid - 1;
  }
  return `${text.slice(0, low)}…`;
}

async function loadImage(href: string): Promise<HTMLImageElement | null> {
  const image = new Image();
  image.decoding = "async";
  image.src = href;
  try {
    await image.decode();
    return image;
  } catch {
    return null;
  }
}

/**
 * Offscreen renderer at the full AOI extent (independent of the live map view): the automatically selected optical
 * image, the reconstructed water through the same LUT painter as the map (depth mode), roads coloured by state (lon/lat
 * projected linearly in Web Mercator over the manifest bounds, like the map's rasters), subdistrict outlines, the
 * reported 2024 shelters, orientation labels, a scale bar and north arrow, a legend and a caption carrying the moment,
 * figures (including modelled residents in flood water), the model disclaimer and source attribution. "portrait" puts
 * the caption under the map; "landscape" is 16:9 with the caption and legend beside it.
 */
export async function createExportRenderer(
  source: ReplayExportSource,
  { width, language, waterOpacity, format = "portrait" }: { width: number; language: Language; waterOpacity: number; format?: VideoFormat },
): Promise<ExportRenderer> {
  const { manifest, hand } = source;
  const th = language === "th";
  const [[south, west], [north, east]] = manifest.bounds;
  const aspect = (mercatorY(north) - mercatorY(south)) / (((east - west) * Math.PI) / 180);
  const landscape = format === "landscape";
  const canvasWidth = even(width);
  const canvasHeight0 = landscape ? even((width * 9) / 16) : 0;
  // Type sizes are set for a 720 px portrait frame and a 720 px tall 16:9 frame.
  const scale = landscape ? canvasHeight0 / 720 : width / VIDEO_WIDTH;
  const mapHeight = landscape ? canvasHeight0 : even(width * aspect);
  const mapWidth = landscape ? even(mapHeight / aspect) : canvasWidth;
  const band = landscape ? 0 : even(186 * scale);
  const canvas = document.createElement("canvas");
  canvas.width = canvasWidth;
  canvas.height = landscape ? canvasHeight0 : mapHeight + band;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas is unavailable");
  const text = copy(language, manifest);
  if (typeof document !== "undefined" && document.fonts) {
    await Promise.all([
      document.fonts.load(`700 16px "Inter Variable"`),
      document.fonts.load(`400 16px "Noto Sans Thai Variable"`, "ก"),
    ]).catch(() => undefined);
  }

  // Imagery: the optical scenes that Auto mode can select.
  const images = new Map<string, HTMLImageElement>();
  await Promise.all(manifest.observations
    .filter((observation) => observation.kind === "optical")
    .map(async (observation) => {
      const layer = manifest.layers.find((candidate) => candidate.id === observation.id);
      const image = layer ? await loadImage(layer.href) : null;
      if (image) images.set(observation.id, image);
    }));

  // Water: the same packed-LUT painter as the map, at the HAND grid resolution.
  const waterCanvas = document.createElement("canvas");
  waterCanvas.width = manifest.hand.width;
  waterCanvas.height = manifest.hand.height;
  const waterContext = waterCanvas.getContext("2d");
  if (!waterContext) throw new Error("Canvas is unavailable");
  const waterImage = waterContext.createImageData(waterCanvas.width, waterCanvas.height);
  const waterPixels = new Uint32Array(waterImage.data.buffer);
  const keys = hand.factorKeys ?? hand.codes;
  const lutSize = hand.factorKeys ? FACTOR_LUT_SIZE : 256;
  // Low-confidence water is washed out and hatched as on the map, only when the manifest declares its channel.
  const low = manifest.hand.low_confidence_channel && hand.lowCells && hand.lowStripes ? { cells: hand.lowCells, stripes: hand.lowStripes } : null;
  let lastLut: Uint32Array | null = null;
  let spareLut: Uint32Array = new Uint32Array(lutSize);
  const paintWater = (stage: number) => {
    const lut = hand.factorKeys
      ? buildFactorDepthLut(stage, manifest.hand.step_m, LITTLE_ENDIAN, spareLut)
      : buildDepthLut(stage, manifest.hand.step_m, LITTLE_ENDIAN, spareLut);
    if (lutEquals(lastLut, lut)) return;
    paintDepth(keys, hand.candidates, lut, waterPixels);
    if (low) paintLowConfidence(low.cells, low.stripes, waterPixels, LITTLE_ENDIAN);
    waterContext.putImageData(waterImage, 0, 0);
    spareLut = lastLut ?? new Uint32Array(lutSize);
    lastLut = lut;
  };

  const project = (lon: number, lat: number) => projectToFrame(lon, lat, manifest.bounds, mapWidth, mapHeight);

  // Roads, projected once.
  const roads = source.roads.features.map((feature) => {
    const points = new Float32Array(feature.geometry.coordinates.length * 2);
    feature.geometry.coordinates.forEach(([lon, lat], index) => {
      const [x, y] = project(lon, lat);
      points[index * 2] = x;
      points[index * 2 + 1] = y;
    });
    return { points, h: feature.properties.h, k: feature.properties.k ?? 1, modelled: feature.properties.m };
  });
  const drawRoads = (stage: number) => {
    const paths: Record<RoadState | "unmodelled", Path2D> = { dry: new Path2D(), wet: new Path2D(), impassable: new Path2D(), unmodelled: new Path2D() };
    for (const road of roads) {
      if (road.points.length < 4) continue;
      const path = paths[road.modelled ? roadState(road.h, stage, manifest.impassable_depth_m, road.k) : "unmodelled"];
      path.moveTo(road.points[0], road.points[1]);
      for (let index = 2; index < road.points.length; index += 2) path.lineTo(road.points[index], road.points[index + 1]);
    }
    context.lineCap = "round";
    context.lineJoin = "round";
    for (const key of ["unmodelled", "dry", "wet", "impassable"] as const) {
      const style = EXPORT_ROAD_STYLES[key];
      context.globalAlpha = style.alpha;
      context.strokeStyle = style.color;
      context.lineWidth = style.width * scale;
      context.setLineDash(style.dash ? style.dash.map((value) => value * scale) : []);
      context.stroke(paths[key]);
    }
    context.setLineDash([]);
    context.globalAlpha = 1;
  };

  // Subdistrict outlines (thin, dashed, as on the map), projected once.
  const outlines = new Path2D();
  for (const feature of source.tambons?.features ?? []) {
    for (const ring of areaRings(feature.geometry)) {
      ring.forEach(([lon, lat], index) => {
        const [x, y] = project(lon, lat);
        if (index === 0) outlines.moveTo(x, y);
        else outlines.lineTo(x, y);
      });
    }
  }
  const drawOutlines = () => {
    if (!source.tambons) return;
    context.save();
    context.globalAlpha = 0.7;
    context.strokeStyle = "#ffffff";
    context.lineWidth = Math.max(1, 1.1 * scale);
    context.setLineDash([5 * scale, 4 * scale]);
    context.stroke(outlines);
    context.restore();
  };

  // Reported 2024 shelters: stars, a struck-through pale star where the model floods the site at its peak, a diamond
  // for the relief and command site. Only located sites are drawn.
  const star = new Path2D(STAR_PATH);
  const slash = new Path2D(STAR_SLASH_PATH);
  const diamond = new Path2D(DIAMOND_PATH);
  type ShelterSymbol = "star" | "floods" | "command";
  const shelters = (manifest.shelters?.reported ?? [])
    .filter((shelter): shelter is ReportedShelter & { lat: number; lon: number } => shelter.lat !== null && shelter.lon !== null)
    .map((shelter) => {
      const [x, y] = project(shelter.lon, shelter.lat);
      const symbol: ShelterSymbol = reportedSiteRole(shelter).role === "relief_command" ? "command" : reportedShelterCheck(shelter).status === "floods" ? "floods" : "star";
      return { x, y, symbol };
    });
  const drawSymbol = (symbol: ShelterSymbol, x: number, y: number, size: number) => {
    context.save();
    context.translate(x - size / 2, y - size / 2);
    context.scale(size / 24, size / 24);
    context.lineJoin = "round";
    context.lineCap = "round";
    if (symbol === "command") {
      context.fillStyle = "#4a3f8f";
      context.strokeStyle = "#ffffff";
      context.lineWidth = 1.8;
      context.fill(diamond);
      context.stroke(diamond);
    } else {
      context.fillStyle = symbol === "floods" ? "#fbe7a1" : "#f5b700";
      context.strokeStyle = symbol === "floods" ? "#b3261e" : "#5a3d00";
      context.lineWidth = symbol === "floods" ? 1.8 : 1.4;
      context.fill(star);
      context.stroke(star);
      if (symbol === "floods") {
        context.lineWidth = 2.6;
        context.stroke(slash);
      }
    }
    context.restore();
  };
  const drawShelters = () => {
    for (const shelter of shelters) drawSymbol(shelter.symbol, shelter.x, shelter.y, 15 * scale);
  };

  const font = (weight: number, size: number) => `${weight} ${size * scale}px ${FONT_STACK}`;

  // Place labels: white text with a dark halo so it reads over imagery and water.
  const places = exportPlaceLabels(source.roads.features, source.tambons?.features ?? [], manifest.bounds).map((label) => {
    const [x, y] = project(label.lon, label.lat);
    return { ...label, x, y };
  });
  const haloText = (value: string, x: number, y: number, size: number, weight: number, align: CanvasTextAlign) => {
    context.font = font(weight, size);
    context.textAlign = align;
    context.textBaseline = "middle";
    context.lineJoin = "round";
    context.lineWidth = 3.2 * scale;
    context.strokeStyle = "rgb(12 39 64 / 88%)";
    context.strokeText(value, x, y);
    context.fillStyle = "#ffffff";
    context.fillText(value, x, y);
    context.textBaseline = "alphabetic";
  };
  const drawPlaces = () => {
    for (const place of places) {
      const label = place.text[language];
      if (place.kind === "bridge") {
        context.beginPath();
        context.arc(place.x, place.y, 3.6 * scale, 0, Math.PI * 2);
        context.fillStyle = "#ffffff";
        context.fill();
        context.lineWidth = 1.6 * scale;
        context.strokeStyle = "#0c2740";
        context.stroke();
        haloText(label, place.x + 8 * scale, place.y - 9 * scale, 10.5, 650, "left");
      } else if (place.kind === "town") {
        haloText(label, place.x + 8 * scale, place.y + 10 * scale, 12.5, 750, "left");
      } else {
        haloText(label, place.x, place.y, 12, 800, "center");
      }
    }
  };

  // Scale bar (bottom right of the map) and a north arrow (top right), so a shared frame keeps its orientation.
  const scaleBar = exportScaleBar(manifest.bounds, mapWidth, mapWidth * 0.22);
  const drawOrientation = () => {
    const right = mapWidth - 14 * scale;
    const bottom = mapHeight - 16 * scale;
    const left = right - scaleBar.pixels;
    context.save();
    context.fillStyle = "rgb(255 255 255 / 88%)";
    context.fillRect(left - 6 * scale, bottom - 24 * scale, scaleBar.pixels + 12 * scale, 32 * scale);
    context.fillStyle = "#0c2740";
    context.fillRect(left, bottom - 4 * scale, scaleBar.pixels, 4 * scale);
    context.fillRect(left, bottom - 9 * scale, 1.5 * scale, 9 * scale);
    context.fillRect(right - 1.5 * scale, bottom - 9 * scale, 1.5 * scale, 9 * scale);
    context.font = font(700, 10.5);
    context.textAlign = "center";
    context.textBaseline = "alphabetic";
    context.fillText(`${scaleBar.km} ${text.km}`, left + scaleBar.pixels / 2, bottom - 11 * scale);
    // North arrow: a filled triangle over "N".
    const x = mapWidth - 26 * scale;
    const y = 16 * scale;
    context.fillStyle = "rgb(255 255 255 / 88%)";
    context.beginPath();
    context.arc(x, y + 12 * scale, 14 * scale, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = "#0c2740";
    context.beginPath();
    context.moveTo(x, y);
    context.lineTo(x + 6 * scale, y + 12 * scale);
    context.lineTo(x - 6 * scale, y + 12 * scale);
    context.closePath();
    context.fill();
    context.font = font(800, 10);
    context.fillText("N", x, y + 23 * scale);
    context.restore();
  };

  const legendRows = 3 + (shelters.length > 0 ? 1 : 0) + (low ? 1 : 0);
  /** Legend box at (x0, y0), `boxWidth` wide: depth classes, roads, reported shelters and low-confidence water. */
  const drawLegend = (x0: number, y0: number, boxWidth: number) => {
    const rowHeight = 18 * scale;
    const boxHeight = (8 + 18 * legendRows) * scale;
    context.fillStyle = "rgb(255 255 255 / 90%)";
    context.fillRect(x0, y0, boxWidth, boxHeight);
    context.fillStyle = "#17253b";
    context.font = font(700, 10.5);
    context.textBaseline = "alphabetic";
    context.textAlign = "left";
    context.fillText(text.legendDepth, x0 + 7 * scale, y0 + 14 * scale);
    context.font = font(500, 9.5);
    let rowY = y0 + 20 * scale;
    const items = [...DEPTH_CLASSES.map((item) => ({ colour: rgbaCss(item.rgba), label: item.label.replace(" m", "") })), { colour: rgbaCss(CHANNEL_RGBA), label: text.river }];
    const itemWidth = (boxWidth - 14 * scale) / items.length;
    items.forEach((item, index) => {
      const x = x0 + 7 * scale + index * itemWidth;
      context.fillStyle = item.colour;
      context.fillRect(x, rowY, 12 * scale, 10 * scale);
      context.fillStyle = "#17253b";
      context.fillText(fitText(context, item.label, itemWidth - 16 * scale), x + 15 * scale, rowY + 9 * scale);
    });
    rowY += rowHeight;
    const roadItems = [{ style: EXPORT_ROAD_STYLES.wet, label: text.wet }, { style: EXPORT_ROAD_STYLES.impassable, label: text.cut }];
    const columnWidth = (boxWidth - 14 * scale) / 3;
    roadItems.forEach((item, index) => {
      const x = x0 + 7 * scale + index * columnWidth;
      const y = rowY + 9 * scale;
      context.strokeStyle = item.style.color;
      context.lineWidth = Math.max(2, item.style.width * 1.6 * scale);
      context.beginPath();
      context.moveTo(x, y - 3 * scale);
      context.lineTo(x + 18 * scale, y - 3 * scale);
      context.stroke();
      context.fillStyle = "#17253b";
      context.fillText(fitText(context, item.label, columnWidth - 26 * scale), x + 24 * scale, y);
    });
    rowY += rowHeight;
    if (shelters.length > 0) {
      const present = new Set(shelters.map((shelter) => shelter.symbol));
      const symbolItems = ([["star", text.reported], ["floods", text.reportedFloods], ["command", text.command]] as const)
        .filter(([symbol]) => present.has(symbol));
      // Symbols and labels one after another, each label at its own width, so short sets never truncate a label.
      context.font = font(500, 9.5);
      const end = x0 + boxWidth - 7 * scale;
      let x = x0 + 7 * scale;
      for (const [symbol, label] of symbolItems) {
        if (x + 30 * scale > end) break;
        drawSymbol(symbol, x + 6 * scale, rowY + 5 * scale, 13 * scale);
        context.fillStyle = "#17253b";
        context.font = font(500, 9.5);
        context.textAlign = "left";
        const shown = fitText(context, label, end - x - 15 * scale);
        context.fillText(shown, x + 15 * scale, rowY + 9 * scale);
        x += 15 * scale + context.measureText(shown).width + 14 * scale;
      }
      rowY += rowHeight;
    }
    if (low) {
      // Hatched pale-blue swatch, then the label.
      const x = x0 + 7 * scale;
      const size = { w: 12 * scale, h: 10 * scale };
      context.fillStyle = "rgb(214 222 234)";
      context.fillRect(x, rowY, size.w, size.h);
      context.save();
      context.beginPath();
      context.rect(x, rowY, size.w, size.h);
      context.clip();
      context.strokeStyle = "rgb(120 150 190)";
      context.lineWidth = Math.max(1, 1.6 * scale);
      for (let offset = -size.h; offset < size.w; offset += 4 * scale) {
        context.beginPath();
        context.moveTo(x + offset, rowY + size.h);
        context.lineTo(x + offset + size.h, rowY);
        context.stroke();
      }
      context.restore();
      context.fillStyle = "#17253b";
      context.font = font(500, 9.5);
      context.fillText(fitText(context, text.lowConfidence, boxWidth - 30 * scale), x + 15 * scale, rowY + 9 * scale);
    }
    return boxHeight;
  };
  const legendHeight = (8 + 18 * legendRows) * scale;

  /** Map part of a frame: imagery, water, outlines, roads, shelters and labels. */
  const opticalObservations = manifest.observations.filter((observation) => images.has(observation.id));
  const drawMap = (t: number, stage: number) => {
    context.fillStyle = "#e9eef5";
    context.fillRect(0, 0, mapWidth, mapHeight);
    const latest = latestObservation(t, opticalObservations, "optical");
    const image = latest ? images.get(latest.observation.id) : undefined;
    if (image) {
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = "high";
      context.drawImage(image, 0, 0, mapWidth, mapHeight);
    }
    paintWater(stage);
    context.globalAlpha = waterOpacity;
    context.drawImage(waterCanvas, 0, 0, mapWidth, mapHeight);
    context.globalAlpha = 1;
    drawOutlines();
    drawRoads(stage);
    drawShelters();
    drawPlaces();
    drawOrientation();
    return latest && image ? latest.observation.label[language] : text.noImagery;
  };

  const draw = (t: number) => {
    const stage = stageAt(t, manifest.stage_anchors);
    const imagery = drawMap(t, stage);
    const stats = districtStats(manifest, stage, source.roadProps, source.facilityProps);
    const phase = phaseAt(t, manifest.phases);
    const moment = `${formatMoment(t, language)} · ${phase.label[language]} · ${text.stage} ${stage.toFixed(2)} ${text.metres}`;
    const figures = `${text.flooded} ${stats.flooded_km2.toFixed(1)} ${text.km2} · ${text.impassable} ${stats.road_km_impassable.toFixed(1)} ${text.km}`;
    const people = stats.people_in_water !== undefined
      ? `${text.people} ${Math.round(stats.people_in_water).toLocaleString("en-US")}${text.peopleUnit ? ` ${text.peopleUnit}` : ""}`
      : null;
    const sourceLine = th
      ? `เวลาของข้อมูลต้นทาง ${manifest.source_timestamp} (UTC) · ${manifest.study_id} ${manifestRevision()} · เวลาประเทศไทย (UTC+7)`
      : `Source time ${manifest.source_timestamp} (UTC) · ${manifest.study_id} ${manifestRevision()} · Asia/Bangkok (ICT, UTC+7)`;

    if (landscape) {
      // Caption panel beside the map: text wrapped to the panel, the legend at its foot.
      const panelX = mapWidth;
      const panelWidth = canvasWidth - mapWidth;
      const left = panelX + 22 * scale;
      const inner = panelWidth - 44 * scale;
      context.fillStyle = "#0c2740";
      context.fillRect(panelX, 0, panelWidth, canvasHeight0);
      let y = 34 * scale;
      const block = (value: string, weight: number, size: number, colour: string, gap = 6) => {
        context.font = font(weight, size);
        context.fillStyle = colour;
        context.textAlign = "left";
        context.textBaseline = "alphabetic";
        for (const line of wrapText((part) => context.measureText(part).width, value, inner, language)) {
          context.fillText(fitText(context, line, inner), left, y);
          y += size * 1.32 * scale;
        }
        y += gap * scale;
      };
      block("FloodGuard", 800, 13, "#9ecae1", 2);
      block(text.title, 750, 19, "#ffffff", 8);
      block(moment, 650, 15, "#f6c453", 8);
      block(text.scope, 650, 12, "#9ecae1", 4);
      block(figures, 500, 13.5, "#e3ebf5", 2);
      if (people) {
        block(people, 750, 13.5, "#ffb4a8", 0);
        block(text.peopleSource, 450, 11, "#c9d5e4", 6);
      }
      block(`${text.imagery}: ${imagery}`, 500, 12, "#e3ebf5", 6);
      block(text.notice, 650, 12.5, "#ffd98a", 6);
      const legendY = canvasHeight0 - legendHeight - 70 * scale;
      if (y < legendY) drawLegend(left, legendY, inner);
      y = canvasHeight0 - 58 * scale;
      block(text.credits, 400, 10.5, "#b9c6d8", 2);
      block(sourceLine, 400, 10, "#9fb0c6", 0);
      return;
    }

    drawLegend(8 * scale, mapHeight - legendHeight - 8 * scale, 380 * scale);
    // Caption band under the map.
    const left = 14 * scale;
    const right = mapWidth - 14 * scale;
    const inner = right - left;
    context.fillStyle = "#0c2740";
    context.fillRect(0, mapHeight, mapWidth, band);
    context.textBaseline = "alphabetic";
    const line = (y: number, value: string, weight: number, size: number, colour: string, maxWidth = inner) => {
      context.font = font(weight, size);
      context.fillStyle = colour;
      context.textAlign = "left";
      context.fillText(fitText(context, value, maxWidth), left, mapHeight + y * scale);
    };
    context.font = font(800, 13);
    const brandWidth = context.measureText("FloodGuard").width;
    context.fillStyle = "#9ecae1";
    context.textAlign = "right";
    context.fillText("FloodGuard", right, mapHeight + 24 * scale);
    line(24, text.title, 750, 16.5, "#ffffff", inner - brandWidth - 16 * scale);
    line(47, moment, 650, 14, "#f6c453");
    line(68, text.scope, 650, 11.5, "#9ecae1");
    line(87, figures, 500, 12.5, "#e3ebf5");
    if (people) {
      context.font = font(750, 12.5);
      const peopleWidth = context.measureText(people).width;
      line(107, people, 750, 12.5, "#ffb4a8");
      context.font = font(450, 11);
      context.fillStyle = "#c9d5e4";
      context.fillText(fitText(context, text.peopleSource, Math.max(0, inner - peopleWidth - 8 * scale)), left + peopleWidth + 8 * scale, mapHeight + 107 * scale);
    }
    line(126, `${text.imagery}: ${imagery}`, 500, 11.5, "#e3ebf5");
    line(145, text.notice, 650, 12, "#ffd98a");
    line(163, text.credits, 400, 10.5, "#b9c6d8");
    line(179, sourceLine, 400, 10, "#9fb0c6");
  };

  /** A card over a dimmed frame: centred, wrapped lines. */
  const drawCard = (t: number, lines: { value: string; weight: number; size: number; colour: string; gap?: number }[]) => {
    draw(t);
    context.fillStyle = "rgb(12 39 64 / 86%)";
    context.fillRect(0, 0, canvas.width, canvas.height);
    const maxWidth = canvas.width * 0.82;
    const laid = lines.map((item) => {
      context.font = font(item.weight, item.size);
      return { ...item, rows: wrapText((part) => context.measureText(part).width, item.value, maxWidth, language) };
    });
    const height = laid.reduce((sum, item) => sum + item.rows.length * item.size * 1.34 * scale + (item.gap ?? 10) * scale, 0);
    let y = (canvas.height - height) / 2;
    context.textAlign = "center";
    context.textBaseline = "top";
    for (const item of laid) {
      context.font = font(item.weight, item.size);
      context.fillStyle = item.colour;
      for (const row of item.rows) {
        context.fillText(fitText(context, row, maxWidth), canvas.width / 2, y);
        y += item.size * 1.34 * scale;
      }
      y += (item.gap ?? 10) * scale;
    }
    context.textAlign = "left";
    context.textBaseline = "alphabetic";
  };
  const peakStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  const peakAnchor = manifest.stage_anchors.find((anchor) => anchor.stage_m === peakStage);
  const drawTitle = () => drawCard(0, [
    { value: "FloodGuard", weight: 800, size: 15, colour: "#9ecae1", gap: 8 },
    { value: text.title, weight: 800, size: 26, colour: "#ffffff", gap: 12 },
    {
      value: th
        ? "ย้อนดูวันที่ 9–19 ก.ย. ทีละชั่วโมง: น้ำที่จำลองจากแบบจำลองภูมิประเทศและระดับน้ำสมมุติ บนภาพดาวเทียมที่ระบุวันที่"
        : "9–19 September, hour by hour: water reconstructed from terrain and an assumed river level, over dated satellite images",
      weight: 550, size: 14, colour: "#e3ebf5", gap: 14,
    },
    {
      value: th
        ? `การจำลองจากแบบจำลอง ไม่ใช่การสังเกตการณ์ · ไม่ใช่ข้อมูลเรียลไทม์หรือคำเตือนทางการ · ความเชื่อมั่น: ${text.level}`
        : `Model reconstruction, not observed · not real-time, not an official warning · confidence: ${text.level}`,
      weight: 700, size: 13, colour: "#ffd98a",
    },
  ]);
  const drawEnd = () => {
    const peakStats = districtStats(manifest, peakStage, source.roadProps, source.facilityProps);
    const peakDate = peakAnchor ? formatShortDate(dateFromT(peakAnchor.t).toISOString(), language) : "";
    const peopleText = peakStats.people_in_water !== undefined ? Math.round(peakStats.people_in_water).toLocaleString("en-US") : null;
    drawCard(VIDEO_END_T, [
      { value: th ? `สิ้นสุดการย้อนดู: ${formatMoment(VIDEO_END_T, "th")}` : `End of the replay: ${formatMoment(VIDEO_END_T, "en")}`, weight: 750, size: 18, colour: "#ffffff", gap: 12 },
      {
        value: th
          ? `ระดับสูงสุดของแบบจำลอง (${peakDate}, ระดับน้ำสมมุติ ${peakStage.toFixed(2)} ม.): น้ำท่วม ≈ ${peakStats.flooded_km2.toFixed(1)} ตร.กม.${peopleText ? ` ผู้อยู่อาศัยตามแบบจำลองในพื้นที่น้ำท่วม ≈ ${peopleText} คน` : ""}`
          : `Model peak (${peakDate}, assumed stage ${peakStage.toFixed(2)} m): ≈ ${peakStats.flooded_km2.toFixed(1)} km² flooded${peopleText ? `, ≈ ${peopleText} modelled residents in flood water` : ""}`,
        weight: 650, size: 14, colour: "#f6c453", gap: 6,
      },
      { value: text.scope, weight: 550, size: 12, colour: "#9ecae1", gap: 12 },
      {
        value: th
          ? "น้ำ ถนน และผู้อยู่อาศัยในพื้นที่น้ำท่วมเป็นผลจากแบบจำลอง ภาพดาวเทียมเป็นการสังเกตการณ์ ดูแหล่งข้อมูล สมมติฐาน และข้อจำกัดได้ในหน้าการย้อนดูของ FloodGuard"
          : "Water, roads and residents in flood water are model outputs; the satellite images are observed. Sources, assumptions and limits are on the FloodGuard replay page.",
        weight: 500, size: 12.5, colour: "#e3ebf5", gap: 12,
      },
      { value: text.credits, weight: 400, size: 10.5, colour: "#b9c6d8", gap: 4 },
      { value: `${manifest.study_id} ${manifestRevision()} · ${th ? "ความเชื่อมั่น" : "confidence"}: ${text.level}`, weight: 400, size: 10.5, colour: "#9fb0c6" },
    ]);
  };
  return { canvas, draw, drawTitle, drawEnd };
}

// --- UI -----------------------------------------------------------------------------------------

type VideoState =
  | { status: "idle" }
  | { status: "preparing" }
  | { status: "recording"; progress: number; paused: boolean }
  | { status: "done"; url: string; ext: string; label: string; bytes: number; name: string }
  | { status: "error" }
  | { status: "cancelled" };
type StillState = { status: "idle" | "working" | "error" } | { status: "done"; url: string; name: string };

const noopSubscribe = () => () => undefined;
function detectRecordingSupport(): boolean {
  return typeof MediaRecorder !== "undefined"
    && typeof HTMLCanvasElement !== "undefined"
    && typeof HTMLCanvasElement.prototype.captureStream === "function"
    && typeof MediaRecorder.isTypeSupported === "function"
    && pickVideoType((mime) => MediaRecorder.isTypeSupported(mime)) !== null;
}
const megabytes = (bytes: number) => (bytes / 1_048_576).toFixed(1);

/** Start a download of `url` as `name` (the browser saves it; the page keeps a link to save it again). */
function triggerDownload(url: string, name: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

/**
 * "Save PNG of this moment" and "Record video" controls. Both render offscreen at the full AOI extent; the video
 * (portrait or 16:9) opens and closes with a one-second card, shows a live preview while it records, and downloads
 * itself when done. The video controls are hidden when the browser cannot record a canvas.
 */
export function ReplayExportPanel({ source, time, language, waterOpacity }: {
  /** Null until the water model is ready; exports are disabled until then. */
  source: ReplayExportSource | null;
  time: number;
  language: Language;
  waterOpacity: number;
}) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const canRecord = useSyncExternalStore(noopSubscribe, detectRecordingSupport, () => false);
  const [still, setStill] = useState<StillState>({ status: "idle" });
  const [video, setVideo] = useState<VideoState>({ status: "idle" });
  const [format, setFormat] = useState<VideoFormat>("portrait");
  /** Stops the recording in progress, or the one still being prepared, so it never starts. */
  const cancelRef = useRef<(() => void) | null>(null);
  const mountedRef = useRef(true);
  const urls = useRef(new Set<string>());
  /** Holds the recording canvas while it records, as a small live preview. */
  const previewRef = useRef<HTMLDivElement | null>(null);

  const revoke = useCallback((url: string) => {
    URL.revokeObjectURL(url);
    urls.current.delete(url);
  }, []);
  useEffect(() => {
    mountedRef.current = true;
    const owned = urls.current;
    return () => {
      mountedRef.current = false;
      cancelRef.current?.();
      for (const url of owned) URL.revokeObjectURL(url);
      owned.clear();
    };
  }, []);

  const savePng = async () => {
    if (!source) return;
    if (still.status === "done") revoke(still.url);
    setStill({ status: "working" });
    try {
      const renderer = await createExportRenderer(source, { width: PNG_WIDTH, language, waterOpacity });
      renderer.draw(hourIndex(time) / 24);
      const blob = await new Promise<Blob | null>((resolve) => renderer.canvas.toBlob(resolve, "image/png"));
      if (!mountedRef.current) return;
      if (!blob) throw new Error("PNG encoding failed");
      const url = URL.createObjectURL(blob);
      urls.current.add(url);
      const name = pngFileName(time);
      triggerDownload(url, name);
      setStill({ status: "done", url, name });
    } catch {
      setStill({ status: "error" });
    }
  };

  const record = async () => {
    if (!source || !canRecord) return;
    if (video.status === "done") revoke(video.url);
    setVideo({ status: "preparing" });
    const shape = format;
    // Cancel, or unmount, while the renderer is still being prepared must stop the recording from ever starting.
    const pending = { cancelled: false };
    cancelRef.current = () => {
      pending.cancelled = true;
    };
    const abandoned = () => pending.cancelled || !mountedRef.current;
    let renderer: ExportRenderer;
    try {
      renderer = await createExportRenderer(source, { width: VIDEO_FORMATS[shape].width, language, waterOpacity, format: shape });
    } catch {
      if (abandoned()) return;
      cancelRef.current = null;
      setVideo({ status: "error" });
      return;
    }
    if (abandoned()) return;
    cancelRef.current = null;
    renderer.drawTitle();
    const stream = renderer.canvas.captureStream(VIDEO_FPS);
    let recorder: MediaRecorder | null = null;
    let type: VideoType | null = null;
    for (const candidate of VIDEO_TYPES) {
      if (!MediaRecorder.isTypeSupported(candidate.mime)) continue;
      try {
        recorder = new MediaRecorder(stream, { mimeType: candidate.mime, videoBitsPerSecond: shape === "landscape" ? 7_000_000 : 5_000_000 });
        type = candidate;
        break;
      } catch {
        recorder = null;
      }
    }
    if (!recorder || !type) {
      stream.getTracks().forEach((track) => track.stop());
      setVideo({ status: "error" });
      return;
    }
    const activeRecorder = recorder;
    const activeType = type;
    const chunks: Blob[] = [];
    let cancelled = false;
    let frame = 0;
    let started = 0;
    let pausedAt: number | null = null;
    let pausedTotal = 0;
    let lastProgress = -1;
    const stopTracks = () => stream.getTracks().forEach((track) => track.stop());
    const clearPreview = () => previewRef.current?.replaceChildren();
    const onVisibility = () => {
      if (activeRecorder.state === "inactive") return;
      if (document.hidden && pausedAt === null) {
        pausedAt = performance.now();
        if (activeRecorder.state === "recording") activeRecorder.pause();
        setVideo({ status: "recording", progress: Math.max(0, lastProgress), paused: true });
      } else if (!document.hidden && pausedAt !== null) {
        pausedTotal += performance.now() - pausedAt;
        pausedAt = null;
        if (activeRecorder.state === "paused") activeRecorder.resume();
        setVideo({ status: "recording", progress: Math.max(0, lastProgress), paused: false });
      }
    };
    const finish = () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibility);
      cancelRef.current = null;
      clearPreview();
    };
    activeRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    activeRecorder.onerror = () => {
      cancelled = true;
      finish();
      stopTracks();
      setVideo({ status: "error" });
    };
    activeRecorder.onstop = () => {
      finish();
      stopTracks();
      if (cancelled || !mountedRef.current) return;
      const blob = new Blob(chunks, { type: activeType.mime.split(";")[0] });
      if (blob.size === 0) {
        setVideo({ status: "error" });
        return;
      }
      const url = URL.createObjectURL(blob);
      urls.current.add(url);
      const name = videoFileName(shape, activeType.ext);
      // Save it at once; the link stays for saving it again.
      triggerDownload(url, name);
      setVideo({ status: "done", url, ext: activeType.ext, label: activeType.label, bytes: blob.size, name });
    };
    cancelRef.current = () => {
      cancelled = true;
      finish();
      if (activeRecorder.state !== "inactive") activeRecorder.stop();
      stopTracks();
    };
    const tick = (now: number) => {
      if (pausedAt !== null) {
        frame = requestAnimationFrame(tick);
        return;
      }
      const elapsed = (now - started - pausedTotal) / 1000;
      const part = videoPart(elapsed);
      if (part.part === "done") {
        if (!cancelled && activeRecorder.state !== "inactive") activeRecorder.stop();
        return;
      }
      if (part.part === "title") renderer.drawTitle();
      else if (part.part === "end") renderer.drawEnd();
      else renderer.draw(part.t);
      const progress = Math.min(100, Math.round((elapsed / VIDEO_TOTAL_SECONDS) * 100));
      if (progress !== lastProgress) {
        lastProgress = progress;
        setVideo({ status: "recording", progress, paused: false });
      }
      frame = requestAnimationFrame(tick);
    };
    document.addEventListener("visibilitychange", onVisibility);
    try {
      activeRecorder.start(1000);
    } catch {
      finish();
      stopTracks();
      setVideo({ status: "error" });
      return;
    }
    started = performance.now();
    previewRef.current?.replaceChildren(renderer.canvas);
    setVideo({ status: "recording", progress: 0, paused: false });
    // A tab hidden before recording starts gets no animation frames; pause at once so the video neither holds frame 0
    // for the hidden time nor jumps ahead when the tab returns (onVisibility resumes it).
    onVisibility();
    frame = requestAnimationFrame(tick);
  };

  const cancel = () => {
    cancelRef.current?.();
    setVideo({ status: "cancelled" });
  };
  const discardVideo = () => {
    if (video.status === "done") revoke(video.url);
    setVideo({ status: "idle" });
  };

  const busy = video.status === "preparing" || video.status === "recording";
  const disabled = !source;
  const seconds = Math.round(VIDEO_TOTAL_SECONDS);
  let videoMessage = "";
  if (video.status === "preparing") videoMessage = t("Preparing the video…", "กำลังเตรียมวิดีโอ…");
  else if (video.status === "recording") {
    // Constant while recording: the <progress> element carries the percentage, so the live region is not flooded.
    videoMessage = video.paused
      ? t("Recording paused while this tab is hidden.", "หยุดบันทึกชั่วคราวขณะแท็บนี้ถูกซ่อน")
      : t("Recording the replay… the preview below shows the video as it is made.", "กำลังบันทึกการย้อนดู… ภาพตัวอย่างด้านล่างแสดงวิดีโอขณะบันทึก");
  } else if (video.status === "done") {
    videoMessage = t(
      `Video saved to your downloads (${video.label}, ${megabytes(video.bytes)} MB).`,
      `บันทึกวิดีโอลงในโฟลเดอร์ดาวน์โหลดแล้ว (${video.label}, ${megabytes(video.bytes)} MB)`,
    );
  } else if (video.status === "error") videoMessage = t("This browser could not record the video. Save a PNG instead.", "เบราว์เซอร์นี้บันทึกวิดีโอไม่สำเร็จ บันทึกเป็น PNG แทนได้");
  else if (video.status === "cancelled") videoMessage = t("Recording cancelled.", "ยกเลิกการบันทึกแล้ว");
  let stillMessage = "";
  if (still.status === "working") stillMessage = t("Rendering the PNG…", "กำลังสร้างภาพ PNG…");
  else if (still.status === "done") stillMessage = t("PNG saved.", "บันทึกภาพ PNG แล้ว");
  else if (still.status === "error") stillMessage = t("The PNG could not be created.", "สร้างภาพ PNG ไม่สำเร็จ");

  return (
    <div className={styles.exportPanel}>
      <div className={styles.actionRow}>
        <button type="button" className={styles.secondaryButton} onClick={() => void savePng()} disabled={disabled || still.status === "working"}
          title={t("Full study area at this hour, with the model disclaimer, figures and source attribution.", "ทั้งพื้นที่ศึกษา ณ ชั่วโมงนี้ พร้อมข้อความกำกับแบบจำลอง ตัวเลข และแหล่งที่มา")}>
          {t("Save PNG of this moment", "บันทึกภาพ PNG ของช่วงเวลานี้")}
        </button>
        {canRecord && (
          <button type="button" className={styles.secondaryButton} onClick={() => void record()} disabled={disabled || busy}
            title={t(
              `Records the whole replay, 9 → 19 Sep, with a one-second title and end card (${seconds} s, ${VIDEO_FPS} fps), as MP4 or WebM, whichever this browser supports, and saves it when done. The tab must stay visible while recording.`,
              `บันทึกการย้อนดูทั้งหมด 9 → 19 ก.ย. พร้อมหน้าเปิดและหน้าปิดอย่างละหนึ่งวินาที (${seconds} วินาที ${VIDEO_FPS} เฟรม/วินาที) เป็น MP4 หรือ WebM ตามที่เบราว์เซอร์รองรับ และบันทึกไฟล์ให้เมื่อเสร็จ ต้องเปิดแท็บนี้ไว้ระหว่างบันทึก`,
            )}>
            {t(`Record video (${seconds} s)`, `บันทึกวิดีโอ (${seconds} วินาที)`)}
          </button>
        )}
        {busy && (
          <button type="button" className={styles.linkButton} onClick={cancel}>{t("Cancel recording", "ยกเลิกการบันทึก")}</button>
        )}
      </div>
      {canRecord && (
        <fieldset className={styles.segmented} disabled={busy} data-testid="video-format">
          <legend>{t("Video shape", "รูปแบบวิดีโอ")}</legend>
          <div>
            <label>
              <input type="radio" name="mae-sai-video-format" value="portrait" checked={format === "portrait"} onChange={() => setFormat("portrait")} />
              <span>{t("Whole study area (portrait)", "ทั้งพื้นที่ศึกษา (แนวตั้ง)")}</span>
            </label>
            <label>
              <input type="radio" name="mae-sai-video-format" value="landscape" checked={format === "landscape"} onChange={() => setFormat("landscape")} />
              <span>{t("16:9 (1280 × 720)", "16:9 (1280 × 720)")}</span>
            </label>
          </div>
        </fieldset>
      )}
      {video.status === "recording" && (
        <progress className={styles.progress} max={100} value={video.progress} aria-label={t("Recording progress", "ความคืบหน้าการบันทึก")} />
      )}
      <div ref={previewRef} className={styles.videoPreview} aria-hidden="true" />
      {video.status === "done" && (
        <p className={styles.downloadRow}>
          <a href={video.url} download={video.name} className={styles.downloadLink}>
            {t(`Save the video again (${video.label}, ${megabytes(video.bytes)} MB)`, `บันทึกวิดีโออีกครั้ง (${video.label}, ${megabytes(video.bytes)} MB)`)}
          </a>
          <button type="button" className={styles.linkButton} onClick={discardVideo}>{t("Discard", "ทิ้ง")}</button>
        </p>
      )}
      {still.status === "done" && (
        <p className={styles.downloadRow}>
          <a href={still.url} download={still.name} className={styles.downloadLink}>{t("Save the PNG again", "บันทึกภาพ PNG อีกครั้ง")}</a>
        </p>
      )}
      <p className={styles.exportStatus} role="status" aria-live="polite">{[stillMessage, videoMessage].filter(Boolean).join(" ")}</p>
      {!source && <p className={styles.muted}>{t("Exports become available once the water model has loaded.", "ส่งออกได้เมื่อโหลดแบบจำลองน้ำเสร็จแล้ว")}</p>}
    </div>
  );
}
