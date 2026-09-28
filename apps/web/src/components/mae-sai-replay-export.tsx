"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  buildDepthLut,
  buildFactorDepthLut,
  CHANNEL_RGBA,
  DEPTH_CLASSES,
  districtStats,
  FACTOR_LUT_SIZE,
  formatMoment,
  hourIndex,
  latestObservation,
  lutEquals,
  manifestRevision,
  mercatorY,
  paintDepth,
  phaseAt,
  projectToFrame,
  rgbaCss,
  roadState,
  stageAt,
  TIMELINE_END_T,
  type FacilityProps,
  type GeoCollection,
  type Language,
  type LineGeometry,
  type RoadProps,
  type RoadState,
  type TimelineManifest,
} from "@/lib/flood-timeline";

import styles from "./mae-sai-flood-timeline.module.css";

/** Replay seconds per day in the exported video (the whole 9–19 Sep window takes 22 s). */
export const VIDEO_SECONDS_PER_DAY = 2;
export const VIDEO_FPS = 30;
export const VIDEO_WIDTH = 720;
export const PNG_WIDTH = 1440;
/** Last moment in the video: 19 Sep 23:00 ICT, the final hour of the replay window. */
const VIDEO_END_T = TIMELINE_END_T - 1e-6;

/** Preferred recording formats, most compatible first. */
export const VIDEO_TYPES = [
  { mime: "video/mp4;codecs=avc1.42E01E", ext: "mp4", label: "MP4" },
  { mime: "video/webm;codecs=vp9", ext: "webm", label: "WebM" },
  { mime: "video/webm", ext: "webm", label: "WebM" },
] as const;
export type VideoType = (typeof VIDEO_TYPES)[number];

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

/** Replay position for a recording clock (seconds since recording began), clamped to the window's last hour. */
export function videoReplayT(elapsedSeconds: number): number {
  return Math.min(VIDEO_END_T, Math.max(0, elapsedSeconds / VIDEO_SECONDS_PER_DAY));
}

/** Download name for a still of replay position `t`: mae-sai-flood-2024-09-12-1200-ict.png. */
export function pngFileName(t: number): string {
  const local = new Date(Date.UTC(2024, 8, 9) + hourIndex(t) * 3_600_000);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `mae-sai-flood-2024-${pad(local.getUTCMonth() + 1)}-${pad(local.getUTCDate())}-${pad(local.getUTCHours())}00-ict.png`;
}

/** Everything the offscreen renderer needs; all of it is already loaded by the replay page. */
export interface ReplayExportSource {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  roadProps: readonly RoadProps[];
  facilityProps: readonly FacilityProps[];
  hand: { codes: Uint8Array; factorKeys: Uint16Array | null; candidates: Uint32Array };
}

export interface ExportRenderer {
  canvas: HTMLCanvasElement;
  /** Draw replay position `t` (days since 9 Sep 00:00 ICT) at the full area-of-interest extent. */
  draw: (t: number) => void;
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
  return {
    // The picture covers the whole study frame (including Tachileik, Myanmar); the figures do not.
    scope: th
      ? `ตัวเลขครอบคลุมเฉพาะอำเภอแม่สาย ส่วนที่แบบจำลองครอบคลุม (${modelled} จาก ${district} ตร.กม.) ไม่ใช่ทั้งภาพ`
      : `Figures: Mae Sai district, modelled part only (${modelled} of ${district} km²), not the whole image`,
    title: th ? "น้ำท่วมแม่สาย กันยายน 2024 — ไล่เรียงรายวัน" : "Mae Sai flood, September 2024 — day by day",
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
    peopleSource: th ? "(แบบจำลอง WorldPop 2020, CC BY 4.0; ไม่ใช่ประชากรปี 2024)" : "(WorldPop 2020 model, CC BY 4.0; not the 2024 population)",
    notice: th
      ? `การจำลองจากแบบจำลอง — ไม่ใช่การสังเกตการณ์ · FloodGuard · ความเชื่อมั่น: ${level} · ไม่ใช่ข้อมูลเรียลไทม์หรือคำเตือนทางการ`
      : `Model reconstruction — not observed · FloodGuard · confidence: ${level} · not real-time, not an official warning`,
    legendDepth: th ? "ความลึก (แบบจำลอง)" : "Depth (model)",
    river: th ? "ร่องน้ำ" : "River",
    wet: th ? "ถนนมีน้ำ" : "Wet road",
    cut: th ? "สัญจรไม่ได้ ≥ 0.3 ม." : "Impassable ≥ 0.3 m",
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
 * Offscreen renderer at the full AOI extent (independent of the live map view): the automatically selected
 * optical image, the reconstructed water through the same LUT painter as the map (depth mode), roads coloured
 * by state (lon/lat projected linearly in Web Mercator over the manifest bounds, like the map's rasters), a
 * legend and a caption band carrying the moment, figures (including modelled residents in flood water), the model
 * disclaimer and source attribution.
 */
export async function createExportRenderer(
  source: ReplayExportSource,
  { width, language, waterOpacity }: { width: number; language: Language; waterOpacity: number },
): Promise<ExportRenderer> {
  const { manifest, hand } = source;
  const [[south, west], [north, east]] = manifest.bounds;
  const aspect = (mercatorY(north) - mercatorY(south)) / (((east - west) * Math.PI) / 180);
  const scale = width / VIDEO_WIDTH;
  const mapWidth = even(width);
  const mapHeight = even(width * aspect);
  const band = even(186 * scale);
  const canvas = document.createElement("canvas");
  canvas.width = mapWidth;
  canvas.height = mapHeight + band;
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
  let lastLut: Uint32Array | null = null;
  let spareLut: Uint32Array = new Uint32Array(lutSize);
  const paintWater = (stage: number) => {
    const lut = hand.factorKeys
      ? buildFactorDepthLut(stage, manifest.hand.step_m, LITTLE_ENDIAN, spareLut)
      : buildDepthLut(stage, manifest.hand.step_m, LITTLE_ENDIAN, spareLut);
    if (lutEquals(lastLut, lut)) return;
    paintDepth(keys, hand.candidates, lut, waterPixels);
    waterContext.putImageData(waterImage, 0, 0);
    spareLut = lastLut ?? new Uint32Array(lutSize);
    lastLut = lut;
  };

  // Roads, projected once.
  const roads = source.roads.features.map((feature) => {
    const points = new Float32Array(feature.geometry.coordinates.length * 2);
    feature.geometry.coordinates.forEach(([lon, lat], index) => {
      const [x, y] = projectToFrame(lon, lat, manifest.bounds, mapWidth, mapHeight);
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

  const font = (weight: number, size: number) => `${weight} ${size * scale}px ${FONT_STACK}`;
  const drawLegend = () => {
    const pad = 8 * scale;
    const boxWidth = 330 * scale;
    const boxHeight = 62 * scale;
    const x0 = pad;
    const y0 = mapHeight - boxHeight - pad;
    context.fillStyle = "rgb(255 255 255 / 88%)";
    context.fillRect(x0, y0, boxWidth, boxHeight);
    context.fillStyle = "#17253b";
    context.font = font(700, 10.5);
    context.textBaseline = "alphabetic";
    context.fillText(text.legendDepth, x0 + 7 * scale, y0 + 14 * scale);
    context.font = font(500, 9.5);
    const items = [...DEPTH_CLASSES.map((item) => ({ colour: rgbaCss(item.rgba), label: item.label.replace(" m", "") })), { colour: rgbaCss(CHANNEL_RGBA), label: text.river }];
    const itemWidth = (boxWidth - 14 * scale) / items.length;
    items.forEach((item, index) => {
      const x = x0 + 7 * scale + index * itemWidth;
      context.fillStyle = item.colour;
      context.fillRect(x, y0 + 20 * scale, 12 * scale, 10 * scale);
      context.fillStyle = "#17253b";
      context.fillText(fitText(context, item.label, itemWidth - 16 * scale), x + 15 * scale, y0 + 29 * scale);
    });
    const roadItems = [{ style: EXPORT_ROAD_STYLES.wet, label: text.wet }, { style: EXPORT_ROAD_STYLES.impassable, label: text.cut }];
    roadItems.forEach((item, index) => {
      const x = x0 + 7 * scale + index * 150 * scale;
      const y = y0 + 48 * scale;
      context.strokeStyle = item.style.color;
      context.lineWidth = Math.max(2, item.style.width * 1.6 * scale);
      context.beginPath();
      context.moveTo(x, y - 3 * scale);
      context.lineTo(x + 18 * scale, y - 3 * scale);
      context.stroke();
      context.fillStyle = "#17253b";
      context.fillText(item.label, x + 24 * scale, y);
    });
  };

  const opticalObservations = manifest.observations.filter((observation) => images.has(observation.id));
  const draw = (t: number) => {
    const stage = stageAt(t, manifest.stage_anchors);
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
    drawRoads(stage);
    drawLegend();

    // Caption band.
    const stats = districtStats(manifest, stage, source.roadProps, source.facilityProps);
    const phase = phaseAt(t, manifest.phases);
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
    line(47, `${formatMoment(t, language)} · ${phase.label[language]} · ${text.stage} ${stage.toFixed(2)} ${text.metres}`, 650, 14, "#f6c453");
    const imagery = latest && image ? latest.observation.label[language] : text.noImagery;
    line(68, text.scope, 650, 11.5, "#9ecae1");
    line(87, `${text.flooded} ${stats.flooded_km2.toFixed(1)} ${text.km2} · ${text.impassable} ${stats.road_km_impassable.toFixed(1)} ${text.km}`, 500, 12.5, "#e3ebf5");
    if (stats.people_in_water !== undefined) {
      const people = `${text.people} ${Math.round(stats.people_in_water).toLocaleString("en-US")}${text.peopleUnit ? ` ${text.peopleUnit}` : ""}`;
      context.font = font(750, 12.5);
      const peopleWidth = context.measureText(people).width;
      line(107, people, 750, 12.5, "#ffb4a8");
      context.font = font(450, 11);
      context.fillStyle = "#c9d5e4";
      context.fillText(fitText(context, text.peopleSource, Math.max(0, inner - peopleWidth - 8 * scale)), left + peopleWidth + 8 * scale, mapHeight + 107 * scale);
    }
    line(126, `${text.imagery}: ${imagery}`, 500, 11.5, "#e3ebf5");
    line(145, text.notice, 650, 12, "#ffd98a");
    line(163, "Contains modified Copernicus Sentinel data 2024 · © OpenStreetMap contributors · Copernicus DEM © DLR e.V., Airbus DS · WorldPop", 400, 10.5, "#b9c6d8");
    line(179, `Source time ${manifest.source_timestamp} (UTC) · ${manifest.study_id} ${manifestRevision()} · Asia/Bangkok (ICT, UTC+7)`, 400, 10, "#9fb0c6");
  };
  return { canvas, draw };
}

// --- UI -----------------------------------------------------------------------------------------

type VideoState =
  | { status: "idle" }
  | { status: "preparing" }
  | { status: "recording"; progress: number; paused: boolean }
  | { status: "done"; url: string; ext: string; label: string; bytes: number }
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

/**
 * "Save PNG of this moment" and "Record video" controls. Both render offscreen at the full AOI extent;
 * the video button is hidden when the browser cannot record a canvas.
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
  /** Stops the recording in progress, or the one still being prepared, so it never starts. */
  const cancelRef = useRef<(() => void) | null>(null);
  const mountedRef = useRef(true);
  const urls = useRef(new Set<string>());

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
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = name;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setStill({ status: "done", url, name });
    } catch {
      setStill({ status: "error" });
    }
  };

  const record = async () => {
    if (!source || !canRecord) return;
    if (video.status === "done") revoke(video.url);
    setVideo({ status: "preparing" });
    // Cancel, or unmount, while the renderer is still being prepared must stop the recording from ever starting.
    const pending = { cancelled: false };
    cancelRef.current = () => {
      pending.cancelled = true;
    };
    const abandoned = () => pending.cancelled || !mountedRef.current;
    let renderer: ExportRenderer;
    try {
      renderer = await createExportRenderer(source, { width: VIDEO_WIDTH, language, waterOpacity });
    } catch {
      if (abandoned()) return;
      cancelRef.current = null;
      setVideo({ status: "error" });
      return;
    }
    if (abandoned()) return;
    cancelRef.current = null;
    renderer.draw(0);
    const stream = renderer.canvas.captureStream(VIDEO_FPS);
    let recorder: MediaRecorder | null = null;
    let type: VideoType | null = null;
    for (const candidate of VIDEO_TYPES) {
      if (!MediaRecorder.isTypeSupported(candidate.mime)) continue;
      try {
        recorder = new MediaRecorder(stream, { mimeType: candidate.mime, videoBitsPerSecond: 5_000_000 });
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
      setVideo({ status: "done", url, ext: activeType.ext, label: activeType.label, bytes: blob.size });
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
      const replayT = videoReplayT((now - started - pausedTotal) / 1000);
      renderer.draw(replayT);
      const progress = Math.round((replayT / VIDEO_END_T) * 100);
      if (progress !== lastProgress) {
        lastProgress = progress;
        setVideo({ status: "recording", progress, paused: false });
      }
      if (replayT >= VIDEO_END_T) {
        // Hold the last frame briefly so players show it, then stop.
        window.setTimeout(() => {
          if (!cancelled && activeRecorder.state !== "inactive") activeRecorder.stop();
        }, 400);
        return;
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
  const seconds = Math.round(VIDEO_END_T * VIDEO_SECONDS_PER_DAY);
  let videoMessage = "";
  if (video.status === "preparing") videoMessage = t("Preparing the video…", "กำลังเตรียมวิดีโอ…");
  else if (video.status === "recording") {
    // Constant while recording: the <progress> element carries the percentage, so the live region is not flooded.
    videoMessage = video.paused
      ? t("Recording paused while this tab is hidden.", "หยุดบันทึกชั่วคราวขณะแท็บนี้ถูกซ่อน")
      : t("Recording the replay…", "กำลังบันทึกการย้อนดู…");
  } else if (video.status === "done") videoMessage = t("Video ready to save.", "วิดีโอพร้อมบันทึกแล้ว");
  else if (video.status === "error") videoMessage = t("This browser could not record the video. Save a PNG instead.", "เบราว์เซอร์นี้บันทึกวิดีโอไม่สำเร็จ บันทึกเป็น PNG แทนได้");
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
              `Records the whole replay, 9 → 19 Sep (${seconds} s, ${VIDEO_FPS} fps), as MP4 or WebM, whichever this browser supports. The tab must stay visible while recording.`,
              `บันทึกการย้อนดูทั้งหมด 9 → 19 ก.ย. (${seconds} วินาที ${VIDEO_FPS} เฟรม/วินาที) เป็น MP4 หรือ WebM ตามที่เบราว์เซอร์รองรับ ต้องเปิดแท็บนี้ไว้ระหว่างบันทึก`,
            )}>
            {t(`Record video (${seconds} s)`, `บันทึกวิดีโอ (${seconds} วินาที)`)}
          </button>
        )}
        {busy && (
          <button type="button" className={styles.linkButton} onClick={cancel}>{t("Cancel recording", "ยกเลิกการบันทึก")}</button>
        )}
      </div>
      {video.status === "recording" && (
        <progress className={styles.progress} max={100} value={video.progress} aria-label={t("Recording progress", "ความคืบหน้าการบันทึก")} />
      )}
      {video.status === "done" && (
        <p className={styles.downloadRow}>
          <a href={video.url} download={`mae-sai-flood-2024.${video.ext}`} className={styles.downloadLink}>
            {t(`Download video (${video.label}, ${megabytes(video.bytes)} MB)`, `ดาวน์โหลดวิดีโอ (${video.label}, ${megabytes(video.bytes)} MB)`)}
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
