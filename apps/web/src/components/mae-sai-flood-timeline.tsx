"use client";

import type {
  CircleMarker,
  CircleMarkerOptions,
  GeoJSONOptions,
  ImageOverlay,
  ImageOverlayOptions,
  LatLngBounds,
  Layer,
  Map as LeafletMap,
  Marker,
  Path,
  PathOptions,
  Polyline,
  Renderer,
} from "leaflet";
import { memo, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";

import {
  ARRIVAL_PENDING_ALPHA,
  ARRIVAL_RAMP,
  arrivalClasses,
  assumptionCaveat,
  buildArrivalLut,
  buildDepthLut,
  buildDurationLut,
  buildFactorDepthLut,
  buildPeopleLut,
  buildResidentsLut,
  CHANNEL_RGBA,
  codeTimings,
  coverageShare,
  dateFromT,
  decodeGrayPng,
  decodePng,
  densityCandidates,
  densityColours,
  DEPTH_CLASSES,
  depthFactorKeys,
  districtStats,
  DURATION_CLASSES,
  FACTOR_LUT_SIZE,
  facilitiesInWater,
  facilityDepth,
  facilityWet,
  floodedKm2,
  formatAge,
  formatHourSpan,
  formatHourStamp,
  formatLocalStamp,
  formatMoment,
  formatShortDate,
  handGridFromRaster,
  hourIndex,
  hourlyStages,
  inflateZlib,
  latestObservation,
  lutEquals,
  manifestRevision,
  observationGap,
  paintDepth,
  peopleKeys,
  phaseAt,
  projectToFrame,
  rgbaCss,
  ROAD_CUT_CLASSES,
  roadCut,
  roadCutClassIndex,
  roadCutGroups,
  roadState,
  stageAt,
  tFromDate,
  tFromLocalDate,
  TIMELINE_END_T,
  TIMELINE_MANIFEST_URL,
  waterCandidates,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type HourClass,
  type Language,
  type LineGeometry,
  type PngRaster,
  type PointGeometry,
  type RoadCutGroup,
  type RoadProps,
  type RoadState,
  type ReportedShelter,
  type ShelterCandidate,
  type ShelterInfo,
  type TambonProps,
  type TimelineLayer,
  type TimelineManifest,
  type TimelineObservation,
  type TimelinePhase,
} from "@/lib/flood-timeline";
import {
  accessLevelIndex,
  accessLevelStep,
  accessLostSeries,
  accessSnapshot,
  buildCutoffRamp,
  candidateReasons,
  clampPlanK,
  cutoffWeight,
  nodeLostAccess,
  osmReference,
  parseAccessNodes,
  planSetId,
  planSites,
  REPORTED_SET_ID,
  reportedShelterCheck,
  reportedSiteRole,
  siteModelled,
  summarizeAccessSets,
  tambonResidents,
  type AccessNodes,
} from "@/lib/flood-timeline-evacuation";
import {
  defaultCompareSides,
  imageryChoices,
  mergeReplayLink,
  parseReplayLink,
  serializeReplayLink,
  type LayerVisibility,
  type ReplayLinkState,
  type RoadMode,
  type ShelterSetChoice,
  type WaterMode,
} from "@/lib/flood-timeline-link";
import { evacuationNeed, replayFpps, tambonImpassableRoads, tambonRoadWeights, tambonVulnerable } from "@/lib/replay-fpps";
import { useLanguage } from "@/lib/use-language";
import {
  AccessCard,
  candidateKindLabel,
  candidateTitle,
  capacityText,
  confidenceLabel,
  DensityLegend,
  evidenceLabel,
  ExternalChecks,
  formatPeople,
  freeboardText,
  ineligibleReasonText,
  locationMethodLabel,
  occupancyText,
  OtherCandidatesCard,
  PeopleInWaterCard,
  reportedCheckText,
  reportedName,
  reportedRoleText,
  ReportedSheltersCard,
  reportedTypeLabel,
  ShelterPlanCard,
  ThemeEyebrow,
} from "./mae-sai-evacuation-panels";
import { PriorityCard } from "./mae-sai-priority-card";
import { ReplayExportPanel, type ReplayExportSource } from "./mae-sai-replay-export";
import { WorkspaceHeader } from "./workspace-header";

import styles from "./mae-sai-flood-timeline.module.css";

export const MAE_SAI_TIMELINE_ROUTE = "/studio/cases/mae-sai-2024/";
const SECONDS_PER_DAY = 2.5;
const START_T = 0.5;
const HOUR_STEPS = TIMELINE_END_T * 24;
/** During playback the map repaints at most this often, unless the stage has moved by PAINT_STAGE_STEP_M. */
const PAINT_INTERVAL_MS = 120;
const PAINT_STAGE_STEP_M = 0.1;
/** Matches the `.imageryLayer` opacity transition. */
const IMAGERY_FADE_MS = 900;
/** The address bar is rewritten at most this often while the replay state changes. */
const LINK_WRITE_MS = 300;
const DEFAULT_WATER_OPACITY = 0.85;
/** Clip rectangles extend this far (px) past the map so a pane's 0 x 0 box never limits them. */
const CLIP_FAR = 100_000;
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
/** Short map credits; full attributions are listed in the Sources panel. */
const OSM_CREDIT = "© OpenStreetMap contributors";
const SENTINEL_CREDIT = "Modified Copernicus Sentinel data 2024";
const DEM_CREDIT = "Copernicus DEM © DLR, Airbus DS";
const WATER_CREDIT = "Water: FloodGuard model";
const ACCESS_CREDIT = "Access: FloodGuard scenario (model)";
const NOT_MODELLED_GREY = "#7b8595";

interface ReplayData {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  facilities: GeoCollection<PointGeometry, FacilityProps>;
  tambons: GeoCollection<AreaGeometry, TambonProps>;
}
/** HAND codes, optional depth-factor painter keys (`code | factor << 8`), and the cells that can ever be wet. */
interface HandRaster { codes: Uint8Array; factorKeys: Uint16Array | null; candidates: Uint32Array }
/** Residents on the water grid: density codes, people painter keys (`code | density << 8`), inhabited cells, colours per code. */
interface PeopleRaster { density: Uint8Array; keys: Uint16Array; inhabited: Uint32Array; colours: Uint32Array }
type LoadState = { status: "loading" } | { status: "error" } | { status: "ready"; data: ReplayData };
type ObservationEntry = { observation: TimelineObservation; at: number };
type AsyncPart<T> = { status: "loading" } | { status: "error" } | { status: "ready"; value: T } | { status: "absent" };

interface WaterLayer {
  overlay: ImageOverlay;
  context: CanvasRenderingContext2D;
  image: ImageData;
  pixels: Uint32Array;
  /** LUT, key array and painted cells currently on the canvas; spare LUT buffers by size are reused for the next paint. */
  lastLut: Uint32Array | null;
  lastKeys: Uint8Array | Uint16Array | null;
  lastCandidates: Uint32Array | null;
  spares: Map<number, Uint32Array>;
}
interface RoadEntry { layer: Path; h: number | null; k: number; cutClass: number; styleKey: string }
interface FacilityEntry { layer: CircleMarker; props: FacilityProps; wet: boolean }
/** Resident nodes that have lost access, for one shelter set and stage level. */
interface CutoffFrame { nodes: AccessNodes; setIndex: number; levelIndex: number }
/** Everything the map shows for one moment. */
interface MapFrame {
  stage: number;
  hour: number;
  hand: HandRaster | null;
  waterMode: WaterMode;
  roadMode: RoadMode;
  people: PeopleRaster | null;
  /** Null hides the "people cut off" heat. */
  cutoff: CutoffFrame | null;
}
interface CompareView { left: string | null; right: string | null; pct: number }
/** Which shelter layers show, and the plan size whose first k sites carry numbered badges. */
interface ShelterView { k: number; reported: boolean; candidates: boolean; ineligible: boolean }
/** Imperative map controller; all mutable Leaflet bookkeeping stays inside the mount closure. */
interface MapController {
  /** Apply a frame; `exact` forces a repaint, otherwise repaints are throttled for playback. */
  update: (frame: MapFrame, exact: boolean) => void;
  showImagery: (id: string | null, instant: boolean) => void;
  /** Two imagery layers side by side with a vertical split at `pct` % of the map width; null turns it off. */
  setCompare: (view: CompareView | null) => void;
  setWaterOpacity: (opacity: number) => void;
  setVisibility: (tambons: boolean, roads: boolean, facilities: boolean) => void;
  /** Highlight a road group and fit the map to it; null clears the highlight and shows the whole area. */
  focusRoads: (group: RoadCutGroup | null, instant: boolean) => void;
  setShelters: (view: ShelterView) => void;
  /** Centre a reported shelter or plan candidate and open its popup (its layer is shown if hidden). */
  focusShelter: (kind: "reported" | "candidate", id: string, instant: boolean) => void;
  /** Re-render the content of any open tooltip or popup (stage, plan size or language changed). */
  refreshTooltips: () => void;
}

const ROAD_STYLES: Record<RoadState | "unmodelled", PathOptions> = {
  dry: { color: "#7d8ba0", weight: 1, opacity: 0.55 },
  wet: { color: "#e8a526", weight: 2.4, opacity: 0.95 },
  impassable: { color: "#c62828", weight: 3.2, opacity: 1 },
  unmodelled: { color: NOT_MODELLED_GREY, weight: 2, opacity: 1, dashArray: "4 4" },
};
const ROAD_CUT_STYLES: PathOptions[] = ROAD_CUT_CLASSES.map((item, index) => ({
  color: item.color,
  weight: item.weight,
  opacity: index === 0 ? 0.5 : 1,
}));
const FACILITY_STYLES: Record<"dry" | "wet" | "unmodelled", CircleMarkerOptions> = {
  dry: { radius: 5, color: "#0c2740", weight: 1.5, fillColor: "#ffffff", fillOpacity: 1 },
  wet: { radius: 6.5, color: "#ffffff", weight: 2, fillColor: "#c62828", fillOpacity: 1 },
  unmodelled: { radius: 5, color: NOT_MODELLED_GREY, weight: 2, fillColor: "#ffffff", fillOpacity: 0 },
};
const PHASE_COLOURS: Record<string, string> = {
  dry: "#d6dee9", onset: "#f6c453", peak: "#d7301f", receding: "#f29e4c", gone: "#9cc9b3",
};
/** Short phase names for narrow band segments; the full label stays in the title and the legend line. */
const PHASE_SHORT: Record<string, [string, string]> = {
  dry: ["Dry", "ปกติ"], onset: ["Onset", "เริ่ม"], peak: ["Peak", "สูงสุด"], receding: ["Receding", "น้ำลด"], gone: ["Receded", "ลดแล้ว"],
};
const PHASE_TEXT_DARK = "#17253b";
const FACILITY_TYPES: Record<string, [string, string]> = {
  shelter_candidate: ["Shelter candidate", "จุดพักพิงที่เป็นไปได้"],
  school: ["School", "โรงเรียน"],
  emergency_service: ["Emergency service", "หน่วยบริการฉุกเฉิน"],
  community_facility: ["Community facility", "สถานที่ชุมชน"],
  healthcare: ["Healthcare", "สถานพยาบาล"],
};
const ROAD_CLASS_LABELS: Record<string, [string, string]> = {
  motorway: ["Motorway", "ทางหลวงพิเศษ"],
  trunk: ["Trunk road", "ทางหลวงสายหลัก"],
  primary: ["Primary road", "ถนนสายหลัก"],
  secondary: ["Secondary road", "ถนนสายรอง"],
  tertiary: ["Tertiary road", "ถนนสายย่อย"],
  unclassified: ["Minor road", "ถนนสายเล็ก"],
  residential: ["Residential street", "ถนนในชุมชน"],
};
/** Thai renderings of known manifest sentences; unknown text falls back to the English original. */
const KNOWN_THAI: Record<string, string> = {
  "The Copernicus DEM tile used stops at 100°E; district land east of it is not modelled.":
    "แผ่นข้อมูล Copernicus DEM ที่ใช้สิ้นสุดที่ลองจิจูด 100°E พื้นที่ของอำเภอทางตะวันออกของเส้นนี้จึงไม่ได้จำลอง",
  "Low-HAND zone (HAND < 6 m, channel excluded) across the full image footprint, both sides of the border.":
    "พื้นที่ HAND ต่ำ (HAND < 6 ม. ไม่รวมร่องน้ำ) ทั่วทั้งขอบเขตภาพ ทั้งสองฝั่งชายแดน",
  "Water extents are a terrain-model reconstruction with illustrative stages; only the late-recession size is checked against radar, and spatial agreement there is weak.":
    "ขอบเขตน้ำจำลองจากแบบจำลองภูมิประเทศด้วยระดับน้ำสมมุติ ตรวจสอบกับเรดาร์ได้เฉพาะขนาดพื้นที่ช่วงน้ำลด และตำแหน่งยังสอดคล้องกันน้อย",
  "No public hourly Sai River water-level record for Sep 2024 was found (HII MYA004 installed 2025; RID Kh.50 closed; DWR Ban Mae Sai EWS unverified), so stage values remain illustrative.":
    "ไม่พบข้อมูลระดับน้ำแม่น้ำสายรายชั่วโมงที่เปิดเผยสำหรับเดือน ก.ย. 2024 (สถานี MYA004 ของ สสน. ติดตั้งปี 2025 สถานี Kh.50 ของกรมชลประทานปิดแล้ว และระบบเตือนภัยบ้านแม่สายของกรมทรัพยากรน้ำยังไม่ได้ยืนยัน) ค่าระดับน้ำจึงยังเป็นค่าเพื่อการอธิบาย",
};
const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
const THAI_SCRIPT = /[฀-๿]/;

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
function subscribeReducedMotion(notify: () => void) {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}
function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReducedMotion, () => window.matchMedia(REDUCED_MOTION_QUERY).matches, () => false);
}
function subscribeOnline(notify: () => void) {
  window.addEventListener("online", notify);
  window.addEventListener("offline", notify);
  return () => {
    window.removeEventListener("online", notify);
    window.removeEventListener("offline", notify);
  };
}
/** Browser connectivity; the street basemap is the one online-only layer of the replay. */
function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

async function fetchJson<T>(href: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(href, { signal });
  if (!response.ok) throw new Error(`${href}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

/** Fallback decoder for browsers without DecompressionStream; keeps greyscale or RGB according to the file header. */
async function decodeWithCanvas(bytes: Uint8Array): Promise<PngRaster> {
  const colourType = bytes.length > 25 ? bytes[25] : 0;
  const channels = colourType === 0 || colourType === 4 ? 1 : 3;
  const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }), {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  });
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("Canvas is unavailable");
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const count = canvas.width * canvas.height;
  const data = new Uint8Array(count * channels);
  for (let cell = 0; cell < count; cell += 1) {
    for (let channel = 0; channel < channels; channel += 1) data[cell * channels + channel] = rgba[cell * 4 + channel];
  }
  return { width: canvas.width, height: canvas.height, channels, data };
}

async function loadHand(manifest: TimelineManifest, signal: AbortSignal): Promise<HandRaster> {
  const response = await fetch(manifest.hand.href, { signal });
  if (!response.ok) throw new Error(`HAND raster: HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const raster = typeof DecompressionStream === "function" ? await decodePng(bytes, inflateZlib) : await decodeWithCanvas(bytes);
  if (raster.width !== manifest.hand.width || raster.height !== manifest.hand.height) throw new Error("HAND raster size mismatch");
  const grid = handGridFromRaster(raster, manifest.hand.depth_factor_channel);
  const maxStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  return {
    codes: grid.codes,
    factorKeys: grid.factors ? depthFactorKeys(grid.codes, grid.factors) : null,
    candidates: waterCandidates(grid.codes, maxStage, manifest.hand.step_m),
  };
}

async function fetchBytes(href: string, signal: AbortSignal): Promise<Uint8Array> {
  const response = await fetch(href, { signal });
  if (!response.ok) throw new Error(`${href}: HTTP ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

/** WorldPop density codes on the water grid (greyscale PNG, decoded exactly). */
async function loadPopulation(manifest: TimelineManifest, signal: AbortSignal): Promise<Uint8Array> {
  const population = manifest.population!;
  const bytes = await fetchBytes(population.href, signal);
  const raster = typeof DecompressionStream === "function" ? await decodeGrayPng(bytes, inflateZlib) : await decodeWithCanvas(bytes);
  if (raster.width !== manifest.hand.width || raster.height !== manifest.hand.height) throw new Error("Population raster size mismatch");
  if (raster.data.length !== raster.width * raster.height) throw new Error("Population raster is not greyscale");
  return raster.data;
}

/** Resident nodes and their per-set cut codes, parsed per the manifest layout. */
async function loadAccessNodes(manifest: TimelineManifest, signal: AbortSignal): Promise<AccessNodes> {
  const access = manifest.access!;
  return parseAccessNodes(await fetchBytes(access.nodes.href, signal), access);
}

interface CanvasOverlayInternals { _url: HTMLCanvasElement; _image: HTMLCanvasElement; _zoomAnimated: boolean; options: ImageOverlayOptions }

/** ImageOverlay backed by a caller-owned canvas, following Leaflet's SVGOverlay pattern. */
function createCanvasOverlay(L: typeof import("leaflet"), canvas: HTMLCanvasElement, bounds: LatLngBounds, options: ImageOverlayOptions): ImageOverlay {
  const CanvasOverlay = L.ImageOverlay.extend({
    _initImage(this: CanvasOverlayInternals) {
      const element = (this._image = this._url);
      L.DomUtil.addClass(element, "leaflet-image-layer");
      if (this._zoomAnimated) L.DomUtil.addClass(element, "leaflet-zoom-animated");
      if (this.options.className) L.DomUtil.addClass(element, this.options.className);
      element.onselectstart = () => false;
      element.onmousemove = () => false;
    },
  });
  const Overlay = CanvasOverlay as unknown as new (element: HTMLCanvasElement, area: LatLngBounds, settings: ImageOverlayOptions) => ImageOverlay;
  return new Overlay(canvas, bounds, options);
}

function tooltipElement(lines: [string, string?][]): HTMLElement {
  const root = document.createElement("div");
  root.className = styles.tooltip;
  for (const [text, tone] of lines) {
    const line = document.createElement(tone === "title" ? "strong" : "span");
    line.textContent = text;
    if (tone && tone !== "title") line.dataset.tone = tone;
    root.append(line);
  }
  return root;
}

/**
 * One popup line. `value` is untranslated source text (e.g. an English manifest note) appended after the translated
 * label `text` in its own element, so screen readers use the right language for each part.
 */
interface PopupLine { text: string; tone?: "title" | "muted" | "alert"; lang?: string; value?: { text: string; lang: string } }

/** Popup content built from text nodes only (manifest strings are never parsed as HTML); links open in a new tab. */
function popupElement(lines: PopupLine[], links: { href: string; text: string }[] = []): HTMLElement {
  const root = document.createElement("div");
  root.className = styles.popup;
  for (const line of lines) {
    const element = document.createElement(line.tone === "title" ? "strong" : "p");
    element.textContent = line.text;
    if (line.value) {
      const value = document.createElement("span");
      value.lang = line.value.lang;
      value.textContent = line.value.text;
      element.append(value);
    }
    if (line.tone && line.tone !== "title") element.dataset.tone = line.tone;
    if (line.lang) element.lang = line.lang;
    root.append(element);
  }
  if (links.length > 0) {
    const list = document.createElement("ul");
    for (const link of links) {
      const item = document.createElement("li");
      const anchor = document.createElement("a");
      anchor.href = link.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = link.text;
      item.append(anchor);
      list.append(item);
    }
    root.append(list);
  }
  return root;
}

const STAR_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z"/></svg>';
/** Relief and command site (reported, not a shelter): a diamond, so it never reads as a shelter star. */
const COMMAND_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="M12 2.5l9.5 9.5-9.5 9.5L2.5 12z"/></svg>';
/** Plan candidates outside the terrain model: hollow, dashed grey, like the other not-modelled symbols. */
const UNMODELLED_CANDIDATE_STYLE: CircleMarkerOptions = { radius: 3.8, color: NOT_MODELLED_GREY, weight: 1.4, dashArray: "2 2", fillColor: "#ffffff", fillOpacity: 0.2 };

const km = (value: number, digits = 1) => value.toFixed(digits);
/** Depth to one decimal, without showing a shallow wet site as "0.0". */
const formatDepth = (depth: number) => (depth < 0.1 ? "< 0.1" : depth.toFixed(1));
/** Phase band tint: the colour mixed with white, for inactive segments that still carry dark text at >= 4.5:1. */
function tint(hex: string, share: number): string {
  const value = Number.parseInt(hex.slice(1), 16);
  const mix = (channel: number) => Math.round(channel * share + 255 * (1 - share));
  return `rgb(${mix((value >> 16) & 255)} ${mix((value >> 8) & 255)} ${mix(value & 255)})`;
}
function localized(text: string, language: Language): { text: string; lang: Language } {
  const thai = language === "th" ? KNOWN_THAI[text] : undefined;
  return thai ? { text: thai, lang: "th" } : { text, lang: "en" };
}
const facilityTypeLabel = (type: string, language: Language) => {
  const [en, th] = FACILITY_TYPES[type] ?? [type, type];
  return language === "th" ? th : en;
};
/**
 * Map tooltip status of a modelled candidate facility at `stage`. Its `h` is the effective HAND (terrain HAND ÷ k),
 * i.e. the assumed stage at which it floods; its height above drainage is the terrain value, h × k.
 */
export function facilityStatusText(props: Pick<FacilityProps, "h" | "m" | "k">, stage: number, language: Language): string {
  const th = language === "th";
  if (props.h === null) return th ? "อยู่สูงกว่าช่วงน้ำท่วมของแบบจำลอง" : "Above the modelled flood range";
  const k = props.k ?? 1;
  if (facilityWet(props, stage)) {
    const depth = facilityDepth(props.h, stage, k);
    return th ? `ความลึกจากแบบจำลอง ≈ ${formatDepth(depth)} ม.` : `Reconstructed depth ≈ ${formatDepth(depth)} m`;
  }
  return th
    ? `แห้งที่ระดับนี้ (สูงจากร่องน้ำ ≈ ${(props.h * k).toFixed(1)} ม. จะท่วมเมื่อระดับน้ำสมมุติเกิน ${props.h.toFixed(2)} ม.)`
    : `Dry at this stage (about ${(props.h * k).toFixed(1)} m above drainage; floods once the assumed stage exceeds ${props.h.toFixed(2)} m)`;
}
const roadClassLabel = (roadClass: string, language: Language) => {
  const [en, th] = ROAD_CLASS_LABELS[roadClass] ?? [roadClass, roadClass];
  return language === "th" ? th : en;
};
const sensorName = (observation: TimelineObservation) => (observation.kind === "optical" ? "Sentinel-2" : "Sentinel-1");
/** "9 Sep", "11–12 Sep" or "30 Sep – 1 Oct" for a phase's local start and end dates. */
function formatDateRange(start: string, end: string, language: Language): string {
  if (start === end) return formatShortDate(start, language);
  const [startDay, ...startMonth] = formatShortDate(start, language).split(" ");
  const endText = formatShortDate(end, language);
  const [, ...endMonth] = endText.split(" ");
  return startMonth.join(" ") === endMonth.join(" ") ? `${startDay}–${endText}` : `${formatShortDate(start, language)} – ${endText}`;
}
/** "Radar change (6 → 16 Sep)" style span for a layer date "a/b". */
function layerSpan(layer: TimelineLayer | undefined, language: Language): string {
  const [start, end] = (layer?.date ?? "").split("/");
  if (!start || !end) return "";
  const [startDay] = formatShortDate(start, language).split(" ");
  return `${startDay} → ${formatShortDate(end, language)}`;
}

const DEFAULT_LAYERS: LayerVisibility = {
  tambons: true, roads: true, facilities: true, reported: true, candidates: true, ineligible: false, cutoff: false,
};

function linkDefaults(language: Language, planK: number): ReplayLinkState {
  return {
    hour: hourIndex(START_T),
    imagery: "auto",
    waterMode: "depth",
    waterOpacity: Math.round(DEFAULT_WATER_OPACITY * 100),
    roadMode: "state",
    compare: null,
    language,
    layers: { ...DEFAULT_LAYERS },
    shelterSet: "reported",
    planK,
  };
}

export function MaeSaiFloodTimeline() {
  const [language, setLanguage] = useLanguage("en");
  const t = useCallback((en: string, th: string) => (language === "th" ? th : en), [language]);
  const reducedMotion = useReducedMotion();
  const online = useOnline();

  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [hand, setHand] = useState<HandRaster | null>(null);
  const [handFailed, setHandFailed] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [time, setTime] = useState(START_T);
  const [playing, setPlaying] = useState(false);
  const [imagery, setImagery] = useState<string>("auto");
  const [waterOpacity, setWaterOpacity] = useState(DEFAULT_WATER_OPACITY);
  const [waterMode, setWaterMode] = useState<WaterMode>("depth");
  const [roadMode, setRoadMode] = useState<RoadMode>("state");
  const [showTambons, setShowTambons] = useState(true);
  const [showRoads, setShowRoads] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);
  const [showReported, setShowReported] = useState(DEFAULT_LAYERS.reported);
  const [showCandidates, setShowCandidates] = useState(DEFAULT_LAYERS.candidates);
  const [showIneligible, setShowIneligible] = useState(DEFAULT_LAYERS.ineligible);
  const [showCutoff, setShowCutoff] = useState(DEFAULT_LAYERS.cutoff);
  const [shelterSet, setShelterSet] = useState<ShelterSetChoice>("reported");
  const [planK, setPlanK] = useState(1);
  const [population, setPopulation] = useState<AsyncPart<Uint8Array>>({ status: "loading" });
  const [accessNodes, setAccessNodes] = useState<AsyncPart<AccessNodes>>({ status: "loading" });
  const [compareOn, setCompareOn] = useState(false);
  const [compareSides, setCompareSides] = useState<readonly [string, string] | null>(null);
  const [comparePct, setComparePct] = useState(50);
  const [linkReady, setLinkReady] = useState(false);
  const [share, setShare] = useState<{ status: "idle" | "copied" | "manual"; url: string }>({ status: "idle", url: "" });
  const [basemapIssue, setBasemapIssue] = useState(false);
  const [offlineCopy, setOfflineCopy] = useState<{ cached: number; failed: number; total: number } | null>(null);
  const [focusedRoute, setFocusedRoute] = useState<string | null>(null);

  const timeRef = useRef(START_T);
  const languageRef = useRef<Language>(language);
  const waterOpacityRef = useRef(waterOpacity);
  /** Plan size the map's shelter popups describe. */
  const planKRef = useRef(planK);
  const mapElement = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<MapController | null>(null);
  const shareField = useRef<HTMLInputElement | null>(null);
  const lastLinkWrite = useRef(0);

  const moveTo = useCallback((value: number) => {
    const next = Math.min(TIMELINE_END_T, Math.max(0, value));
    timeRef.current = next;
    setTime(next);
  }, []);

  // --- Data loading, then the shared link (it needs the manifest to know which imagery exists) -----------
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      try {
        const manifest = await fetchJson<TimelineManifest>(TIMELINE_MANIFEST_URL, signal);
        loadHand(manifest, signal).then(
          (raster) => { if (!signal.aborted) setHand(raster); },
          () => { if (!signal.aborted) setHandFailed(true); },
        );
        // Residents and the access scenario load alongside; each part fails on its own without hiding the rest.
        if (manifest.population) {
          loadPopulation(manifest, signal).then(
            (value) => { if (!signal.aborted) setPopulation({ status: "ready", value }); },
            () => { if (!signal.aborted) setPopulation({ status: "error" }); },
          );
        } else setPopulation({ status: "absent" });
        if (manifest.access && manifest.shelters) {
          loadAccessNodes(manifest, signal).then(
            (value) => { if (!signal.aborted) setAccessNodes({ status: "ready", value }); },
            () => { if (!signal.aborted) setAccessNodes({ status: "error" }); },
          );
        } else setAccessNodes({ status: "absent" });
        const [roads, facilities, tambons] = await Promise.all([
          fetchJson<ReplayData["roads"]>(manifest.vectors.roads.href, signal),
          fetchJson<ReplayData["facilities"]>(manifest.vectors.facilities.href, signal),
          fetchJson<ReplayData["tambons"]>(manifest.vectors.tambons.href, signal),
        ]);
        if (signal.aborted) return;
        const choices = imageryChoices(manifest.layers);
        const planLength = manifest.shelters?.plan.length ?? 0;
        const link = parseReplayLink(window.location.search, linkDefaults(languageRef.current, manifest.shelters?.knee_k ?? 1), {
          maxHour: HOUR_STEPS,
          imageryIds: choices,
          compareIds: choices.filter((id) => id !== "none"),
          maxPlanK: planLength,
        });
        moveTo(link.hour / 24);
        setImagery(link.imagery);
        setWaterMode(link.waterMode);
        setWaterOpacity(link.waterOpacity / 100);
        setRoadMode(link.roadMode);
        setCompareOn(link.compare !== null);
        if (link.compare) setCompareSides(link.compare);
        setShowTambons(link.layers.tambons);
        setShowRoads(link.layers.roads);
        setShowFacilities(link.layers.facilities);
        setShowReported(link.layers.reported);
        setShowCandidates(link.layers.candidates);
        setShowIneligible(link.layers.ineligible);
        setShowCutoff(link.layers.cutoff);
        setShelterSet(link.shelterSet);
        setPlanK(manifest.shelters ? clampPlanK(link.planK, manifest.shelters) : 1);
        if (link.language !== languageRef.current) setLanguage(link.language);
        setLoad({ status: "ready", data: { manifest, roads, facilities, tambons } });
        setLinkReady(true);
      } catch {
        if (!signal.aborted) setLoad({ status: "error" });
      }
    })();
    return () => controller.abort();
  }, [reloadKey, moveTo, setLanguage]);

  const data = load.status === "ready" ? load.data : null;
  const manifest = data?.manifest ?? null;

  const derived = useMemo(() => {
    if (!data) return null;
    const { manifest: m } = data;
    const roadProps = data.roads.features.map((feature) => feature.properties);
    const facilityProps = data.facilities.features.map((feature) => feature.properties);
    const names = Object.fromEntries(data.tambons.features.map((feature) => [feature.properties.id, feature.properties]));
    const tambonScale = Math.max(...m.days.flatMap((day) => Object.values(day.stats.tambon_flooded_km2)), 0.001);
    const observations: ObservationEntry[] = m.observations
      .map((observation) => ({ observation, at: tFromDate(observation.local) }))
      .sort((a, b) => a.at - b.at);
    const radar = observations.filter((entry) => entry.observation.kind === "radar");
    const hasUnmodelledRoads = roadProps.some((road) => !road.m);
    const hasUnmodelledFacilities = facilityProps.some((facility) => !facility.m);
    const layersById = new Map(m.layers.map((layer) => [layer.id, layer]));
    const imageryIds = imageryChoices(m.layers);
    const compareIds = imageryIds.filter((id) => id !== "none");
    const defaultSides = defaultCompareSides(m.layers);
    const opticalIds = m.observations.filter((observation) => observation.kind === "optical" && layersById.has(observation.id)).map((observation) => observation.id);
    // Hourly samples of the assumed stage drive arrival, time under water and road-cut durations.
    const stages = hourlyStages(m.stage_anchors);
    const timings = codeTimings(stages, m.hand.step_m, m.hand.never_code);
    const arrival = arrivalClasses(timings.arrivalHour, ARRIVAL_RAMP, m.hand.channel_code);
    const roadCuts = data.roads.features.map((feature) => roadCut(
      feature.properties.m ? feature.properties.h : null, stages, m.impassable_depth_m, feature.properties.k ?? 1,
    ));
    const routeGroups = roadCutGroups(data.roads.features, roadCuts, 10);
    const peopleScale = Math.max(...m.days.flatMap((day) => Object.values(day.stats.tambon_people_in_water ?? {})), 1);
    const roadWeights = tambonRoadWeights(roadProps);
    return {
      roadProps, facilityProps, names, tambonScale, observations, radar, hasUnmodelledRoads, hasUnmodelledFacilities,
      layersById, imageryIds, compareIds, defaultSides, opticalIds, timings, arrival, roadCuts, routeGroups, stages, peopleScale, roadWeights,
    };
  }, [data]);

  // Residents raster: painter keys need both grids; colours depend only on the density cap.
  const populationRaster = population.status === "ready" ? population.value : null;
  const peopleRaster = useMemo<PeopleRaster | null>(() => {
    if (!hand || !populationRaster || !data?.manifest.population) return null;
    return {
      density: populationRaster,
      keys: peopleKeys(hand.codes, populationRaster),
      inhabited: densityCandidates(populationRaster),
      colours: densityColours(data.manifest.population.max_per_ha, LITTLE_ENDIAN),
    };
  }, [hand, populationRaster, data]);

  // Access scenario: per-set cumulative histograms once, then O(1) per stage.
  const nodes = accessNodes.status === "ready" ? accessNodes.value : null;
  const accessModel = useMemo(() => {
    const info = data?.manifest.access;
    if (!nodes || !info) return null;
    return {
      summaries: summarizeAccessSets(nodes, info),
      tambonTotals: tambonResidents(nodes, info.tambons.length),
      vulnerable: tambonVulnerable(nodes, info.tambons.length),
    };
  }, [nodes, data]);

  const stage = manifest ? stageAt(time, manifest.stage_anchors) : 0;
  const phase = manifest ? phaseAt(time, manifest.phases) : null;
  const hour = hourIndex(time);
  const stats = useMemo(
    () => (data && derived ? districtStats(data.manifest, stage, derived.roadProps, derived.facilityProps) : null),
    [data, derived, stage],
  );
  const shelterInfo = manifest?.shelters ?? null;
  const accessInfo = manifest?.access ?? null;
  const selectedSetId = shelterSet === "reported" ? REPORTED_SET_ID : planSetId(planK);
  const selectedSetIndex = accessInfo ? accessInfo.sets.indexOf(selectedSetId) : -1;
  const selectedSummary = accessModel && selectedSetIndex >= 0 ? accessModel.summaries[selectedSetIndex] : null;
  const accessLevel = accessInfo ? accessLevelIndex(stage, accessInfo.levels) : 0;
  const snapshot = selectedSummary && accessInfo ? accessSnapshot(selectedSummary, stage, accessInfo.levels) : null;
  const lostSeries = useMemo(
    () => (selectedSummary && accessInfo && derived ? accessLostSeries(selectedSummary, derived.stages, accessInfo.levels) : null),
    [selectedSummary, accessInfo, derived],
  );
  // Scenario FPPS: the five components per subdistrict at this stage and for the chosen shelter set, locked A–E rules.
  const priorityRows = useMemo(() => {
    const m = data?.manifest;
    if (!m?.population || !derived || !stats) return null;
    const need = nodes && accessInfo && selectedSetIndex >= 0
      ? evacuationNeed(nodes, selectedSetIndex, stage, accessInfo.levels, m.hand.step_m, accessInfo.tambons.length)
      : null;
    return replayFpps({
      tambonIds: Object.keys(m.tambon_coverage),
      accessTambons: accessInfo?.tambons ?? [],
      modelledKm2: Object.fromEntries(Object.entries(m.tambon_coverage).map(([id, coverage]) => [id, coverage.modelled_km2])),
      floodedKm2: stats.tambon_flooded_km2,
      residents: m.population.tambon_totals,
      peopleInWater: stats.tambon_people_in_water ?? {},
      need,
      nodeResidents: accessModel?.tambonTotals ?? null,
      vulnerable: accessModel?.vulnerable ?? null,
      roadWeightedKm: derived.roadWeights,
      roadWeightedImpassableKm: tambonImpassableRoads(derived.roadProps, stage, m.impassable_depth_m),
      confidence: m.confidence,
    });
  }, [data, derived, stats, nodes, accessInfo, selectedSetIndex, stage, accessModel]);
  const cutoffFrame = useMemo<CutoffFrame | null>(
    () => (showCutoff && nodes && selectedSetIndex >= 0 ? { nodes, setIndex: selectedSetIndex, levelIndex: accessLevel } : null),
    [showCutoff, nodes, selectedSetIndex, accessLevel],
  );
  const latestOptical = manifest ? latestObservation(time, manifest.observations, "optical") : null;
  const latestOpticalId = latestOptical?.observation.id ?? null;
  const resolveImagery = useCallback(
    (choice: string) => (choice === "auto" ? latestOpticalId : choice === "none" ? null : choice),
    [latestOpticalId],
  );
  const activeImagery = resolveImagery(imagery);
  const gap = manifest ? observationGap(time, manifest.observations) : null;
  const sides = compareSides ?? derived?.defaultSides ?? null;
  const compareLeft = compareOn && sides ? resolveImagery(sides[0]) : null;
  const compareRight = compareOn && sides ? resolveImagery(sides[1]) : null;
  const comparing = compareOn && sides !== null;

  const linkState = useMemo<ReplayLinkState>(() => ({
    hour,
    imagery,
    waterMode,
    waterOpacity: Math.round(waterOpacity * 100),
    roadMode,
    compare: comparing && sides ? sides : null,
    language,
    layers: {
      tambons: showTambons, roads: showRoads, facilities: showFacilities,
      reported: showReported, candidates: showCandidates, ineligible: showIneligible, cutoff: showCutoff,
    },
    shelterSet,
    planK,
  }), [hour, imagery, waterMode, waterOpacity, roadMode, comparing, sides, language, showTambons, showRoads, showFacilities,
    showReported, showCandidates, showIneligible, showCutoff, shelterSet, planK]);

  useEffect(() => {
    languageRef.current = language;
    waterOpacityRef.current = waterOpacity;
    planKRef.current = planK;
  }, [language, waterOpacity, planK]);

  // --- Deep link: rewrite the address bar at most every LINK_WRITE_MS (leading and trailing) -----------
  useEffect(() => {
    if (!linkReady) return;
    const write = () => {
      lastLinkWrite.current = performance.now();
      const query = mergeReplayLink(window.location.search, linkState);
      if (`?${query}` !== window.location.search) window.history.replaceState(null, "", `${window.location.pathname}?${query}${window.location.hash}`);
    };
    const wait = LINK_WRITE_MS - (performance.now() - lastLinkWrite.current);
    if (wait <= 0) {
      write();
      return;
    }
    const timer = window.setTimeout(write, wait);
    return () => window.clearTimeout(timer);
  }, [linkReady, linkState]);

  useEffect(() => {
    if (share.status === "manual") shareField.current?.select();
    if (share.status !== "copied") return;
    const timer = window.setTimeout(() => setShare((current) => (current.status === "copied" ? { status: "idle", url: "" } : current)), 5000);
    return () => window.clearTimeout(timer);
  }, [share.status]);

  // --- Offline copy: after the replay has rendered online, ask the service worker to keep its data ------
  const replayRendered = load.status === "ready" && mapReady && (hand !== null || handFailed);
  useEffect(() => {
    if (!replayRendered || process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    let active = true;
    let channel: MessageChannel | null = null;
    navigator.serviceWorker.ready.then((registration) => {
      const worker = registration.active;
      if (!active || !worker) return;
      channel = new MessageChannel();
      channel.port1.onmessage = (event: MessageEvent<{ type?: string; cached?: number; failed?: number; total?: number }>) => {
        channel?.port1.close();
        const result = event.data;
        if (!active || result?.type !== "FLOODGUARD_CASE_REPLAY_STATUS") return;
        setOfflineCopy({ cached: result.cached ?? 0, failed: result.failed ?? 0, total: result.total ?? 0 });
      };
      worker.postMessage({ type: "FLOODGUARD_CACHE_CASE_REPLAY" }, [channel.port2]);
    }).catch(() => undefined);
    return () => {
      active = false;
      channel?.port1.close();
    };
  }, [replayRendered]);

  // --- Map mount ---------------------------------------------------------------------------------
  useEffect(() => {
    if (!data || !derived) return;
    const replay = data;
    const analysis = derived;
    const { manifest: m } = replay;
    let disposed = false;
    let mounted: LeafletMap | null = null;
    let resizeTimer: number | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let attributionObserver: ResizeObserver | undefined;
    const timers = new Set<number>();
    const frames = new Set<number>();

    async function mount() {
      const L = await import("leaflet");
      if (disposed || !mapElement.current) return;
      mapElement.current.replaceChildren();
      const map = L.map(mapElement.current, { zoomControl: true, attributionControl: false, keyboard: true, zoomSnap: 0.25, maxZoom: 17 });
      mounted = map;
      const attribution = L.control.attribution({ prefix: false }).addTo(map);
      // The basemap note sits just above the attribution, which wraps to two or more lines on narrow maps.
      const attributionElement = attribution.getContainer();
      const frameElement = mapElement.current.parentElement;
      if (attributionElement && frameElement) {
        const syncAttribution = () => frameElement.style.setProperty("--fg-attribution-h", `${Math.ceil(attributionElement.offsetHeight)}px`);
        attributionObserver = new ResizeObserver(syncAttribution);
        attributionObserver.observe(attributionElement);
        syncAttribution();
      }
      const bounds = L.latLngBounds(m.bounds);
      const fit = () => {
        map.invalidateSize();
        map.fitBounds(bounds, { padding: [6, 6], animate: false });
        map.setMinZoom(Math.max(8, map.getZoom() - 1.5));
      };
      map.setMaxBounds(bounds.pad(0.35));
      fit();

      for (const [name, zIndex] of [
        ["fg-imagery", 250], ["fg-compare-left", 251], ["fg-compare-right", 252], ["fg-water", 350], ["fg-cutoff", 360],
        ["fg-tambons", 380], ["fg-highlight", 390], ["fg-roads", 400], ["fg-facilities", 450], ["fg-shelters", 460],
      ] as const) {
        const pane = map.createPane(name);
        pane.style.zIndex = String(zIndex);
        pane.style.pointerEvents = "none";
      }
      const imageryPane = map.getPane("fg-imagery")!;
      const comparePanes = { left: map.getPane("fg-compare-left")!, right: map.getPane("fg-compare-right")! };
      comparePanes.left.style.display = "none";
      comparePanes.right.style.display = "none";

      const basemap = L.tileLayer(OSM_TILES, {
        attribution: OSM_CREDIT,
        maxZoom: 19,
        opacity: 0.6,
        referrerPolicy: "strict-origin",
        className: styles.basemap,
      }).addTo(map);
      // The street basemap is online-only; imagery, water and roads come from this site (and the offline copy).
      basemap.on("tileerror", () => setBasemapIssue(true));
      basemap.on("tileload", () => setBasemapIssue(false));

      const thai = () => languageRef.current === "th";
      // Stage currently drawn on the map; tooltips describe this stage so they always match the picture.
      let applied: MapFrame | null = null;
      let appliedAt = 0;
      const tooltipLayers: Layer[] = [];
      const refreshTooltips = () => {
        for (const layer of tooltipLayers) if (layer.isTooltipOpen()) layer.getTooltip()?.update();
      };
      const appliedStage = () => applied?.stage ?? 0;
      const layerFor = (id: string) => m.layers.find((candidate) => candidate.id === id);

      // --- Imagery: the incoming image fades in on top; the outgoing one stays opaque underneath, then hides.
      const imagery = new Map<string, ImageOverlay>();
      const hideTimers = new Map<string, number>();
      let shownImagery: string | null = null;
      const cancelHide = (id: string) => {
        const timer = hideTimers.get(id);
        if (timer === undefined) return;
        window.clearTimeout(timer);
        timers.delete(timer);
        hideTimers.delete(id);
      };
      const createImagery = (id: string): { overlay: ImageOverlay; fresh: boolean } | null => {
        const existing = imagery.get(id);
        if (existing) return { overlay: existing, fresh: false };
        const layer = layerFor(id);
        if (!layer) return null;
        const overlay = L.imageOverlay(layer.href, bounds, {
          pane: "fg-imagery",
          opacity: 0,
          className: styles.imageryLayer,
          alt: "",
          attribution: layer.kind === "terrain" ? DEM_CREDIT : SENTINEL_CREDIT,
        }).addTo(map);
        imagery.set(id, overlay);
        return { overlay, fresh: true };
      };
      // The optical scenes drive Auto mode; load them up front so the crossfade is seamless.
      for (const id of analysis.opticalIds) createImagery(id);

      // --- Swipe comparison: one overlay per side in its own pane, each pane clipped at the divider.
      const compareOverlays: Record<"left" | "right", { overlay: ImageOverlay; id: string } | null> = { left: null, right: null };
      let compareView: CompareView | null = null;
      const updateClip = () => {
        if (!compareView) return;
        const size = map.getSize();
        // Panes move with the map pane, so the divider is expressed in layer (pane) pixels.
        const x = map.containerPointToLayerPoint(L.point((size.x * compareView.pct) / 100, 0)).x;
        comparePanes.left.style.clipPath = `inset(${-CLIP_FAR}px ${-x}px ${-CLIP_FAR}px ${-CLIP_FAR}px)`;
        comparePanes.right.style.clipPath = `inset(${-CLIP_FAR}px ${-CLIP_FAR}px ${-CLIP_FAR}px ${x}px)`;
      };
      const setCompareSide = (side: "left" | "right", id: string | null) => {
        const current = compareOverlays[side];
        if (current?.id === id) return;
        const layer = id ? layerFor(id) : undefined;
        if (!id || !layer) {
          current?.overlay.remove();
          compareOverlays[side] = null;
          return;
        }
        if (current) {
          current.overlay.setUrl(layer.href);
          compareOverlays[side] = { overlay: current.overlay, id };
          return;
        }
        const overlay = L.imageOverlay(layer.href, bounds, {
          pane: side === "left" ? "fg-compare-left" : "fg-compare-right",
          opacity: 1,
          alt: "",
          attribution: layer.kind === "terrain" ? DEM_CREDIT : SENTINEL_CREDIT,
        }).addTo(map);
        compareOverlays[side] = { overlay, id };
      };

      let water: WaterLayer | null = null;
      const canvas = document.createElement("canvas");
      canvas.width = m.hand.width;
      canvas.height = m.hand.height;
      const context = canvas.getContext("2d");
      if (context) {
        const image = context.createImageData(canvas.width, canvas.height);
        const overlay = createCanvasOverlay(L, canvas, bounds, {
          pane: "fg-water",
          opacity: waterOpacityRef.current,
          className: styles.waterLayer,
          attribution: WATER_CREDIT,
        }).addTo(map);
        water = {
          overlay, context, image, pixels: new Uint32Array(image.data.buffer), lastLut: null, lastKeys: null, lastCandidates: null, spares: new Map(),
        };
      }
      /**
       * Paint through the shared LUT path: one key array, one LUT, one set of cells, buffers reused between paints.
       * The residents view paints inhabited cells instead of wet-able ones, so the canvas is cleared when the cell set changes.
       */
      const paintWater = (layer: WaterLayer, raster: HandRaster, frame: MapFrame) => {
        let keys: Uint8Array | Uint16Array = raster.codes;
        let cells = raster.candidates;
        let size = 256;
        let build: (out: Uint32Array) => Uint32Array;
        const people = frame.people;
        if (frame.waterMode === "people" && people) {
          keys = people.keys;
          size = FACTOR_LUT_SIZE;
          build = (out) => buildPeopleLut(frame.stage, m.hand.step_m, people.colours, LITTLE_ENDIAN, out);
        } else if (frame.waterMode === "residents" && people) {
          keys = people.density;
          cells = people.inhabited;
          build = (out) => buildResidentsLut(people.colours, out);
        } else if (frame.waterMode === "arrival") {
          build = (out) => buildArrivalLut(analysis.timings.arrivalHour, analysis.arrival, frame.hour, LITTLE_ENDIAN, out);
        } else if (frame.waterMode === "duration") {
          build = (out) => buildDurationLut(analysis.timings.hoursUnder, LITTLE_ENDIAN, out);
        } else if (raster.factorKeys) {
          keys = raster.factorKeys;
          size = FACTOR_LUT_SIZE;
          build = (out) => buildFactorDepthLut(frame.stage, m.hand.step_m, LITTLE_ENDIAN, out);
        } else {
          build = (out) => buildDepthLut(frame.stage, m.hand.step_m, LITTLE_ENDIAN, out);
        }
        const spare = layer.spares.get(size) ?? new Uint32Array(size);
        const lut = build(spare);
        if (layer.lastKeys === keys && layer.lastCandidates === cells && lutEquals(layer.lastLut, lut)) {
          layer.spares.set(size, spare);
          return;
        }
        if (layer.lastCandidates !== cells) layer.pixels.fill(0);
        paintDepth(keys, cells, lut, layer.pixels);
        layer.context.putImageData(layer.image, 0, 0);
        if (layer.lastLut && layer.lastLut.length === size) layer.spares.set(size, layer.lastLut);
        else layer.spares.delete(size);
        layer.lastLut = lut;
        layer.lastKeys = keys;
        layer.lastCandidates = cells;
      };

      // --- "People cut off": resident nodes that lost access, drawn as population-weighted blobs on a canvas
      // overlay (half the water grid). Blob alpha accumulates on an offscreen canvas, then maps through a colour ramp.
      const CUTOFF_RADIUS = 7;
      const cutoffRamp = buildCutoffRamp(LITTLE_ENDIAN);
      let cutoff: {
        overlay: ImageOverlay; context: CanvasRenderingContext2D; image: ImageData; pixels: Uint32Array;
        heat: CanvasRenderingContext2D; sprite: HTMLCanvasElement; width: number; height: number;
        positions: Float32Array | null; nodes: AccessNodes | null; key: string;
      } | null = null;
      const createCutoff = () => {
        const width = Math.max(1, Math.round(m.hand.width / 2));
        const height = Math.max(1, Math.round(m.hand.height / 2));
        const canvasElement = document.createElement("canvas");
        canvasElement.width = width;
        canvasElement.height = height;
        const heatCanvas = document.createElement("canvas");
        heatCanvas.width = width;
        heatCanvas.height = height;
        const sprite = document.createElement("canvas");
        sprite.width = sprite.height = CUTOFF_RADIUS * 2 + 2;
        const target = canvasElement.getContext("2d");
        const heat = heatCanvas.getContext("2d", { willReadFrequently: true });
        const spriteContext = sprite.getContext("2d");
        if (!target || !heat || !spriteContext) return null;
        const centre = CUTOFF_RADIUS + 1;
        const gradient = spriteContext.createRadialGradient(centre, centre, 0, centre, centre, CUTOFF_RADIUS);
        gradient.addColorStop(0, "rgb(255 255 255 / 100%)");
        gradient.addColorStop(0.45, "rgb(255 255 255 / 70%)");
        gradient.addColorStop(1, "rgb(255 255 255 / 0%)");
        spriteContext.fillStyle = gradient;
        spriteContext.fillRect(0, 0, sprite.width, sprite.height);
        const image = target.createImageData(width, height);
        const overlay = createCanvasOverlay(L, canvasElement, bounds, {
          pane: "fg-cutoff", opacity: 0.85, className: styles.cutoffLayer, attribution: ACCESS_CREDIT,
        });
        return { overlay, context: target, image, pixels: new Uint32Array(image.data.buffer), heat, sprite, width, height, positions: null, nodes: null, key: "" };
      };
      const drawCutoff = (frame: CutoffFrame | null) => {
        if (!frame) {
          if (cutoff && map.hasLayer(cutoff.overlay)) cutoff.overlay.remove();
          return;
        }
        cutoff ??= createCutoff();
        if (!cutoff) return;
        if (!map.hasLayer(cutoff.overlay)) cutoff.overlay.addTo(map);
        const key = `${frame.setIndex}:${Math.max(-1, Math.min(frame.levelIndex, 253))}`;
        if (cutoff.nodes === frame.nodes && cutoff.key === key) return;
        const { nodes: points, setIndex, levelIndex } = frame;
        if (cutoff.nodes !== points || !cutoff.positions) {
          const positions = new Float32Array(points.count * 2);
          for (let node = 0; node < points.count; node += 1) {
            const [x, y] = projectToFrame(points.lon[node], points.lat[node], m.bounds, cutoff.width, cutoff.height);
            positions[node * 2] = x;
            positions[node * 2 + 1] = y;
          }
          cutoff.positions = positions;
          cutoff.nodes = points;
        }
        const { heat, sprite, positions, width, height, pixels } = cutoff;
        heat.globalCompositeOperation = "source-over";
        heat.globalAlpha = 1;
        heat.clearRect(0, 0, width, height);
        heat.globalCompositeOperation = "lighter";
        const row = setIndex * points.count;
        const offset = CUTOFF_RADIUS + 1;
        for (let node = 0; node < points.count; node += 1) {
          if (!nodeLostAccess(points.cutCodes[row + node], levelIndex)) continue;
          const weight = cutoffWeight(points.population[node]);
          if (weight <= 0) continue;
          heat.globalAlpha = weight;
          heat.drawImage(sprite, positions[node * 2] - offset, positions[node * 2 + 1] - offset);
        }
        heat.globalCompositeOperation = "source-over";
        heat.globalAlpha = 1;
        const alpha = heat.getImageData(0, 0, width, height).data;
        for (let pixel = 0, sample = 3; pixel < pixels.length; pixel += 1, sample += 4) pixels[pixel] = cutoffRamp[alpha[sample]];
        cutoff.context.putImageData(cutoff.image, 0, 0);
        cutoff.key = key;
      };

      const tambonRenderer = L.svg({ pane: "fg-tambons" });
      const tambonOptions: GeoJSONOptions & { renderer: Renderer } = {
        renderer: tambonRenderer,
        style: () => ({ color: "#1c3d6e", weight: 1.4, opacity: 0.85, dashArray: "5 4", fill: true, fillOpacity: 0 }),
        onEachFeature: (feature, layer) => {
          const props = feature.properties as TambonProps;
          layer.bindTooltip(() => {
            const th = thai();
            const area = floodedKm2(m.tambon_histograms[props.id] ?? new Array(256).fill(0), appliedStage(), m.hand.step_m, m.pixel_area_m2);
            const share = coverageShare(m.tambon_coverage?.[props.id]);
            const lines: [string, string?][] = [
              [th ? `ตำบล${props.th}` : `${props.en} subdistrict`, "title"],
              [th ? `น้ำท่วมตามแบบจำลอง ≈ ${km(area)} ตร.กม.` : `Model flooded area ≈ ${km(area)} km²`],
            ];
            if (share < 0.99) {
              const pct = Math.round(share * 100);
              lines.push([th ? `แบบจำลองครอบคลุม ${pct}% ของตำบลนี้` : `${pct}% of this subdistrict is modelled`, "muted"]);
            }
            return tooltipElement(lines);
          }, { sticky: true, direction: "top" });
          tooltipLayers.push(layer);
        },
      };
      const tambonGroup = L.geoJSON(replay.tambons as unknown as Parameters<typeof L.geoJSON>[0], tambonOptions);

      const featureIndex = new Map(replay.roads.features.map((feature, index) => [feature as unknown, index]));
      const roads: RoadEntry[] = [];
      const modelledRoadOptions: GeoJSONOptions & { renderer: Renderer } = {
        renderer: L.canvas({ pane: "fg-roads", padding: 0.5 }),
        interactive: false,
        filter: (feature) => Boolean((feature.properties as RoadProps).m),
        style: () => ROAD_STYLES.dry,
        onEachFeature: (feature, layer) => {
          const props = feature.properties as RoadProps;
          const cut = analysis.roadCuts[featureIndex.get(feature) ?? -1];
          roads.push({ layer: layer as Path, h: props.h, k: props.k ?? 1, cutClass: roadCutClassIndex(cut?.hours ?? 0), styleKey: "dry" });
        },
      };
      // Roads outside the model grid: fixed grey dashed style, never classified dry/wet.
      const unmodelledRoadOptions: GeoJSONOptions & { renderer: Renderer } = {
        renderer: L.svg({ pane: "fg-roads" }),
        filter: (feature) => !(feature.properties as RoadProps).m,
        style: () => ROAD_STYLES.unmodelled,
        onEachFeature: (_feature, layer) => {
          layer.bindTooltip(() => (thai()
            ? tooltipElement([["ถนนที่ไม่ได้จำลอง", "title"], ["อยู่นอกพื้นที่ที่แบบจำลองครอบคลุม จึงไม่นับรวมในตัวเลข", "muted"]])
            : tooltipElement([["Road not modelled", "title"], ["Outside the modelled area; excluded from the figures", "muted"]])), { sticky: true, direction: "top" });
          tooltipLayers.push(layer);
        },
      };
      const roadGroup = L.layerGroup([
        L.geoJSON(replay.roads as unknown as Parameters<typeof L.geoJSON>[0], modelledRoadOptions),
        L.geoJSON(replay.roads as unknown as Parameters<typeof L.geoJSON>[0], unmodelledRoadOptions),
      ]);
      let highlight: Polyline | null = null;

      const facilities: FacilityEntry[] = [];
      const facilityRenderer = L.svg({ pane: "fg-facilities" });
      const facilityTooltip = (props: FacilityProps) => {
        const th = thai();
        const language: Language = th ? "th" : "en";
        const title = facilityTypeLabel(props.type, language);
        const name = props.n || (th ? "ไม่มีชื่อ" : "Unnamed");
        if (!props.m) {
          return tooltipElement([[title, "title"], [name], [th ? "อยู่นอกพื้นที่ที่แบบจำลองครอบคลุม" : "Outside the modelled area", "muted"]]);
        }
        const wet = facilityWet(props, appliedStage());
        return tooltipElement([[title, "title"], [name], [facilityStatusText(props, appliedStage(), language), wet ? "alert" : undefined]]);
      };
      const facilityGroup = L.geoJSON(replay.facilities as unknown as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (feature, latlng) => {
          const props = feature.properties as FacilityProps;
          const style = props.m ? FACILITY_STYLES.dry : FACILITY_STYLES.unmodelled;
          const marker = L.circleMarker(latlng, { ...style, renderer: facilityRenderer, pane: "fg-facilities" });
          marker.bindTooltip(() => facilityTooltip(props), { direction: "top", offset: [0, -6] });
          tooltipLayers.push(marker);
          if (props.m) facilities.push({ layer: marker, props, wet: false });
          return marker;
        },
      });

      // --- Shelters: reported 2024 sites (stars) and ranked plan candidates (numbered top-k badges, eligible rings, ineligible grey).
      const shelterData: ShelterInfo | null = m.shelters ?? null;
      const shelterRenderer = L.svg({ pane: "fg-shelters" });
      const popupLanguage = (): Language => (thai() ? "th" : "en");
      const tr = (en: string, th: string) => (thai() ? th : en);
      const popupLayers: Layer[] = [];
      const titled: { element: () => HTMLElement | undefined; title: () => string }[] = [];
      const reportedMarkers = new Map<string, Marker>();
      const reportedGroup = L.layerGroup();
      const reportedPopup = (shelter: ReportedShelter) => {
        const lang = popupLanguage();
        const check = reportedShelterCheck(shelter);
        const command = reportedSiteRole(shelter).role === "relief_command";
        const role = reportedRoleText(shelter, lang);
        const status = command
          ? tr("relief and command site, Sep 2024 (not a shelter)", "ศูนย์บัญชาการและจุดช่วยเหลือ ก.ย. 2024 (ไม่ใช่ที่พักพิง)")
          : tr("reported in use, Sep 2024", "มีรายงานว่าใช้ ก.ย. 2024");
        const occupancy = occupancyText(shelter);
        const lines: PopupLine[] = [
          { text: reportedName(shelter, lang), tone: "title" },
          { text: lang === "th" ? shelter.name_en : shelter.name_th, tone: "muted", lang: lang === "th" ? "en" : "th" },
          { text: `${reportedTypeLabel(shelter.type, lang)} · ${status} · ${evidenceLabel(shelter.evidence_strength, lang)}` },
          ...(role ? [{ text: role, tone: "alert" as const }] : []),
          shelter.period_used
            ? { text: `${tr("Period used", "ช่วงที่ใช้")}: `, value: { text: shelter.period_used, lang: "en" } }
            : { text: `${tr("Period used", "ช่วงที่ใช้")}: ${tr("not reported", "ไม่มีรายงาน")}` },
          occupancy
            ? { text: `${tr("Occupancy", "จำนวนผู้พักพิง")}: `, value: { text: occupancy, lang: "en" } }
            : { text: `${tr("Occupancy", "จำนวนผู้พักพิง")}: ${tr("not reported", "ไม่มีรายงาน")}` },
          { text: `${tr("Location", "ตำแหน่ง")}: ${locationMethodLabel(shelter.location_method, lang)} · ${tr("confidence", "ความเชื่อมั่น")} ${confidenceLabel(shelter.location_confidence, lang)}`, tone: "muted" },
          { text: reportedCheckText(check, shelterData!, lang), tone: check.status === "floods" ? "alert" : undefined },
        ];
        return popupElement(lines, shelter.sources.map((source) => ({ href: source.url, text: `${source.publisher}, ${source.date}: ${source.title}` })));
      };
      for (const shelter of shelterData?.reported ?? []) {
        if (shelter.lat === null || shelter.lon === null) continue;
        const floods = reportedShelterCheck(shelter).status === "floods";
        const command = reportedSiteRole(shelter).role === "relief_command";
        const marker = L.marker([shelter.lat, shelter.lon], {
          pane: "fg-shelters",
          icon: command
            ? L.divIcon({ className: styles.commandIcon, html: COMMAND_ICON, iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -9] })
            : L.divIcon({ className: `${styles.starIcon}${floods ? ` ${styles.starIconFloods}` : ""}`, html: STAR_ICON, iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -10] }),
          keyboard: true,
          riseOnHover: true,
          zIndexOffset: 2000,
        });
        marker.bindPopup(() => reportedPopup(shelter), { maxWidth: 300, maxHeight: 300, className: styles.popupFrame });
        popupLayers.push(marker);
        titled.push({
          element: () => marker.getElement(),
          title: () => `${command ? tr("Relief and command site (2024), not a shelter", "ศูนย์บัญชาการและจุดช่วยเหลือ (2024) ไม่ใช่ที่พักพิง") : tr("Reported shelter (2024)", "ที่พักพิงที่มีรายงาน (2024)")}: ${reportedName(shelter, popupLanguage())}`,
        });
        reportedMarkers.set(shelter.id, marker);
        reportedGroup.addLayer(marker);
      }
      const planGroup = L.layerGroup();
      const eligibleGroup = L.layerGroup();
      const ineligibleGroup = L.layerGroup();
      const candidateMarkers = new Map<string, Marker | CircleMarker>();
      let candidatePopups: Layer[] = [];
      let candidateTitles: typeof titled = [];
      let builtK = -1;
      // Candidates off the DEM tile or the grid have no model result; the r2 build's flags for them are not shown.
      const unmodelledCandidates = new Set((shelterData?.candidates ?? []).filter((candidate) => !siteModelled(candidate)).map((candidate) => candidate.id));
      const candidatePopup = (candidate: ShelterCandidate) => {
        const lang = popupLanguage();
        const k = planKRef.current;
        const modelled = !unmodelledCandidates.has(candidate.id);
        const site = shelterData ? planSites(shelterData, k).find((item) => item.candidate.id === candidate.id) : undefined;
        const lines: PopupLine[] = [
          { text: candidateTitle(candidate, lang), tone: "title" },
          { text: `${candidateKindLabel(candidate.kind, lang)} · ${tr("OpenStreetMap candidate (planning scenario)", "สถานที่ที่เป็นไปได้จาก OpenStreetMap (สถานการณ์เพื่อการวางแผน)")}`, tone: "muted" },
        ];
        if (site) lines.push({ text: tr(`Plan rank ${site.rank} of the first ${k}`, `อันดับ ${site.rank} ใน ${k} แห่งแรกของแผน`) });
        else if (candidate.eligible) lines.push({ text: tr(`Eligible, not among the first ${k} ranked sites`, `เข้าเกณฑ์ แต่ไม่อยู่ใน ${k} แห่งแรกของแผน`), tone: "muted" });
        else lines.push({ text: `${tr("Not eligible", "ไม่เข้าเกณฑ์")}: ${candidateReasons(candidate).map((reason) => ineligibleReasonText(reason, shelterData!, lang)).join("; ")}`, tone: "alert" });
        lines.push({ text: capacityText(candidate, shelterData!, lang) });
        if (site) {
          lines.push({ text: tr(`Assigned ≈ ${formatPeople(site.load)} residents in a ${k}-site plan`, `รับผู้อพยพ ≈ ${formatPeople(site.load)} คนในแผน ${k} แห่ง`) });
          if (site.shortfall && site.capacity !== null) {
            lines.push({ text: tr(`Capacity shortfall: ≈ ${formatPeople(site.load - site.capacity)} more than the estimate`, `ความจุไม่พอ: เกินค่าประมาณ ≈ ${formatPeople(site.load - site.capacity)} คน`), tone: "alert" });
          }
        }
        lines.push({ text: freeboardText(candidate, lang), tone: modelled && candidate.freeboard_m !== null && candidate.freeboard_m < 0 ? "alert" : undefined });
        lines.push({ text: tr(`Nearest road node ${formatPeople(candidate.snap_m)} m away`, `จุดถนนที่ใกล้ที่สุดห่าง ${formatPeople(candidate.snap_m)} ม.`), tone: "muted" });
        const osm = osmReference(candidate.source);
        return popupElement(lines, osm ? [{ href: osm.url, text: `OpenStreetMap ${osm.type} ${osm.id}` }] : []);
      };
      const buildCandidates = (k: number) => {
        if (!shelterData) return;
        for (const group of [planGroup, eligibleGroup, ineligibleGroup]) group.clearLayers();
        candidateMarkers.clear();
        candidatePopups = [];
        candidateTitles = [];
        const ranks = new Map(planSites(shelterData, k).map((site) => [site.candidate.id, site.rank]));
        for (const candidate of shelterData.candidates) {
          const rank = ranks.get(candidate.id);
          let layer: Marker | CircleMarker;
          if (rank !== undefined) {
            const marker = L.marker([candidate.lat, candidate.lon], {
              pane: "fg-shelters",
              icon: L.divIcon({ className: styles.planBadgeIcon, html: `<span>${rank}</span>`, iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -11] }),
              keyboard: true,
              riseOnHover: true,
              zIndexOffset: 1000 - rank,
            });
            candidateTitles.push({ element: () => marker.getElement(), title: () => `${tr("Plan site", "ที่พักพิงในแผน")} ${rank}: ${candidateTitle(candidate, popupLanguage())}` });
            planGroup.addLayer(marker);
            layer = marker;
          } else {
            const eligible = candidate.eligible;
            layer = L.circleMarker([candidate.lat, candidate.lon], eligible
              ? { renderer: shelterRenderer, pane: "fg-shelters", radius: 4.5, color: "#0b6e4f", weight: 1.8, fillColor: "#ffffff", fillOpacity: 0.95 }
              : unmodelledCandidates.has(candidate.id)
                ? { ...UNMODELLED_CANDIDATE_STYLE, renderer: shelterRenderer, pane: "fg-shelters" }
                : { renderer: shelterRenderer, pane: "fg-shelters", radius: 3.6, color: "#6b7585", weight: 1.2, fillColor: "#a3acba", fillOpacity: 0.6 });
            (eligible ? eligibleGroup : ineligibleGroup).addLayer(layer);
          }
          layer.bindPopup(() => candidatePopup(candidate), { maxWidth: 290, className: styles.popupFrame });
          candidatePopups.push(layer);
          candidateMarkers.set(candidate.id, layer);
        }
        builtK = k;
      };
      const refreshTitles = () => {
        for (const entry of [...titled, ...candidateTitles]) {
          const element = entry.element();
          if (!element) continue;
          const title = entry.title();
          element.title = title;
          element.setAttribute("aria-label", title);
        }
      };
      const refreshPopups = () => {
        for (const layer of [...popupLayers, ...candidatePopups]) if (layer.isPopupOpen()) layer.getPopup()?.update();
      };
      const setGroup = (group: Layer, visible: boolean) => {
        if (visible && !map.hasLayer(group)) group.addTo(map);
        if (!visible && map.hasLayer(group)) group.remove();
      };

      controllerRef.current = {
        update(frame, exact) {
          const now = performance.now();
          if (applied && frame.hand === applied.hand && frame.waterMode === applied.waterMode && frame.roadMode === applied.roadMode
            && frame.people === applied.people && (frame.cutoff === null) === (applied.cutoff === null)) {
            const sameMoment = frame.stage === applied.stage && frame.cutoff === applied.cutoff
              && (frame.waterMode !== "arrival" || frame.hour === applied.hour);
            if (sameMoment) return;
            if (!exact && now - appliedAt < PAINT_INTERVAL_MS && Math.abs(frame.stage - applied.stage) < PAINT_STAGE_STEP_M) return;
          }
          applied = frame;
          appliedAt = now;
          if (water && frame.hand) paintWater(water, frame.hand, frame);
          drawCutoff(frame.cutoff);
          for (const entry of roads) {
            const styleKey = frame.roadMode === "hours" ? `cut${entry.cutClass}` : roadState(entry.h, frame.stage, m.impassable_depth_m, entry.k);
            if (styleKey === entry.styleKey) continue;
            entry.layer.setStyle(frame.roadMode === "hours" ? ROAD_CUT_STYLES[entry.cutClass] : ROAD_STYLES[styleKey as RoadState]);
            entry.styleKey = styleKey;
          }
          for (const entry of facilities) {
            const wet = facilityWet(entry.props, frame.stage);
            if (wet !== entry.wet) {
              const style = FACILITY_STYLES[wet ? "wet" : "dry"];
              entry.layer.setStyle(style);
              entry.layer.setRadius(style.radius ?? 5);
              entry.wet = wet;
            }
          }
          refreshTooltips();
        },
        showImagery(id, instant) {
          if (id === shownImagery) return;
          shownImagery = id;
          const incoming = id ? createImagery(id) : null;
          if (!id || !incoming) {
            for (const [key, overlay] of imagery) {
              cancelHide(key);
              overlay.setOpacity(0);
            }
            return;
          }
          const { overlay, fresh } = incoming;
          cancelHide(id);
          overlay.bringToFront();
          if (instant) {
            overlay.setOpacity(1);
            for (const [key, other] of imagery) {
              if (key === id) continue;
              cancelHide(key);
              other.setOpacity(0);
            }
            return;
          }
          if (fresh || (overlay.options.opacity ?? 0) < 1) {
            const frame = requestAnimationFrame(() => {
              frames.delete(frame);
              if (shownImagery !== id) return;
              const element = overlay.getElement();
              // Commit the transparent start state so the opacity transition runs from 0.
              if (element) void getComputedStyle(element).opacity;
              overlay.setOpacity(1);
            });
            frames.add(frame);
          }
          for (const [key, other] of imagery) {
            if (key === id || hideTimers.has(key) || (other.options.opacity ?? 0) === 0) continue;
            const timer = window.setTimeout(() => {
              timers.delete(timer);
              hideTimers.delete(key);
              if (shownImagery !== key) other.setOpacity(0);
            }, IMAGERY_FADE_MS + 50);
            timers.add(timer);
            hideTimers.set(key, timer);
          }
        },
        setCompare(view) {
          if (!view) {
            if (compareView) map.off("move zoom viewreset resize zoomend", updateClip);
            compareView = null;
            setCompareSide("left", null);
            setCompareSide("right", null);
            for (const pane of [comparePanes.left, comparePanes.right]) {
              pane.style.display = "none";
              pane.style.clipPath = "";
            }
            imageryPane.style.display = "";
            return;
          }
          if (!compareView) map.on("move zoom viewreset resize zoomend", updateClip);
          compareView = view;
          imageryPane.style.display = "none";
          comparePanes.left.style.display = "";
          comparePanes.right.style.display = "";
          setCompareSide("left", view.left);
          setCompareSide("right", view.right);
          updateClip();
        },
        setWaterOpacity(opacity) {
          water?.overlay.setOpacity(opacity);
        },
        setVisibility(tambons, roadsVisible, facilitiesVisible) {
          for (const [group, visible] of [[tambonGroup, tambons], [roadGroup, roadsVisible], [facilityGroup, facilitiesVisible]] as const) {
            if (visible && !map.hasLayer(group)) group.addTo(map);
            if (!visible && map.hasLayer(group)) group.remove();
          }
        },
        focusRoads(group, instant) {
          highlight?.remove();
          highlight = null;
          if (!group) {
            map.fitBounds(bounds, { padding: [6, 6], animate: !instant });
            return;
          }
          const lines = group.pieces.map((index) => replay.roads.features[index].geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]));
          highlight = L.polyline(lines, { pane: "fg-highlight", color: "#ffe066", weight: 11, opacity: 0.75, lineCap: "round", interactive: false }).addTo(map);
          map.fitBounds(L.latLngBounds(group.bounds), { padding: [36, 36], maxZoom: 16, animate: !instant });
        },
        setShelters(view) {
          if (!shelterData) return;
          if (view.k !== builtK) buildCandidates(view.k);
          setGroup(reportedGroup, view.reported);
          setGroup(planGroup, view.candidates);
          setGroup(eligibleGroup, view.candidates);
          setGroup(ineligibleGroup, view.ineligible);
          refreshTitles();
          refreshPopups();
        },
        focusShelter(kind, id, instant) {
          const layer = kind === "reported" ? reportedMarkers.get(id) : candidateMarkers.get(id);
          if (!layer) return;
          const group = kind === "reported" ? reportedGroup : [planGroup, eligibleGroup, ineligibleGroup].find((item) => item.hasLayer(layer));
          if (group) setGroup(group, true);
          map.setView(layer.getLatLng(), Math.max(map.getZoom(), 15), { animate: !instant });
          layer.openPopup();
          refreshTitles();
        },
        refreshTooltips() {
          refreshTooltips();
          refreshTitles();
          refreshPopups();
        },
      };
      setMapReady(true);
      // Refit once layout settles (fonts, panel), then keep Leaflet in sync with container resizes.
      resizeTimer = window.setTimeout(fit, 120);
      resizeObserver = new ResizeObserver(() => map.invalidateSize());
      resizeObserver.observe(mapElement.current);
    }

    void mount();
    return () => {
      disposed = true;
      if (resizeTimer !== undefined) window.clearTimeout(resizeTimer);
      for (const timer of timers) window.clearTimeout(timer);
      for (const frame of frames) cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      attributionObserver?.disconnect();
      controllerRef.current = null;
      setMapReady(false);
      mounted?.stop();
      mounted?.remove();
    };
  }, [data, derived]);

  // --- Map updates ------------------------------------------------------------------------------
  // Playback repaints are throttled; pausing, seeking and slider moves (playing === false) repaint exactly.
  useEffect(() => {
    if (mapReady) controllerRef.current?.update({ stage, hour, hand, waterMode, roadMode, people: peopleRaster, cutoff: cutoffFrame }, !playing);
  }, [mapReady, hand, stage, hour, waterMode, roadMode, playing, peopleRaster, cutoffFrame]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.setShelters({ k: planK, reported: showReported, candidates: showCandidates, ineligible: showIneligible });
  }, [mapReady, planK, showReported, showCandidates, showIneligible]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.showImagery(activeImagery, reducedMotion);
  }, [mapReady, activeImagery, reducedMotion]);

  useEffect(() => {
    if (!mapReady) return;
    controllerRef.current?.setCompare(comparing ? { left: compareLeft, right: compareRight, pct: comparePct } : null);
  }, [mapReady, comparing, compareLeft, compareRight, comparePct]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.setWaterOpacity(waterOpacity);
  }, [mapReady, waterOpacity]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.setVisibility(showTambons, showRoads, showFacilities);
  }, [mapReady, showTambons, showRoads, showFacilities]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.refreshTooltips();
  }, [mapReady, language]);

  // --- Playback --------------------------------------------------------------------------------
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last: number | null = null;
    let held = 0;
    const tick = (now: number) => {
      const elapsed = last === null ? 0 : Math.min(0.25, (now - last) / 1000);
      last = now;
      let next = timeRef.current;
      if (reducedMotion) {
        held += elapsed;
        if (held >= SECONDS_PER_DAY) {
          held = 0;
          next = Math.floor(timeRef.current - 0.5 + 1e-6) + 1.5;
        }
      } else {
        next += elapsed / SECONDS_PER_DAY;
      }
      if (next >= TIMELINE_END_T) {
        moveTo(TIMELINE_END_T);
        setPlaying(false);
        return;
      }
      if (next !== timeRef.current) moveTo(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, reducedMotion, moveTo]);

  const togglePlay = useCallback(() => {
    if (playing) {
      setPlaying(false);
      // Snap to the hour shown in the readout so slider, readout, day buttons and map agree.
      moveTo(hourIndex(timeRef.current) / 24);
      return;
    }
    if (timeRef.current >= TIMELINE_END_T - 1e-6) moveTo(0);
    setPlaying(true);
  }, [playing, moveTo]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== " " || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (target && (target.isContentEditable
        || target.closest("input, select, textarea, button, a, summary, [contenteditable]:not([contenteditable='false']), [role='button'], [role='slider']"))) return;
      if (!data) return;
      event.preventDefault();
      if (event.repeat) return;
      togglePlay();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [togglePlay, data]);

  const jumpTo = (value: number) => {
    setPlaying(false);
    moveTo(value);
  };

  const copyLink = async () => {
    const url = `${window.location.origin}${window.location.pathname}?${serializeReplayLink(linkState)}`;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(url);
      setShare({ status: "copied", url });
    } catch {
      setShare({ status: "manual", url });
    }
  };

  // Stable handlers: the time-independent cards below are memoised and must not re-render on every playback frame.
  const focusRoute = useCallback((group: RoadCutGroup) => {
    setFocusedRoute(group.key);
    setShowRoads(true);
    controllerRef.current?.focusRoads(group, reducedMotion);
    mapElement.current?.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }, [reducedMotion]);
  const resetRouteFocus = useCallback(() => {
    setFocusedRoute(null);
    controllerRef.current?.focusRoads(null, reducedMotion);
  }, [reducedMotion]);
  const showReportedOnMap = useCallback((id: string) => {
    setShowReported(true);
    controllerRef.current?.focusShelter("reported", id, reducedMotion);
    mapElement.current?.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }, [reducedMotion]);
  const showCandidateOnMap = useCallback((id: string) => {
    const candidate = shelterInfo?.candidates.find((item) => item.id === id);
    if (candidate && !candidate.eligible) setShowIneligible(true);
    else setShowCandidates(true);
    controllerRef.current?.focusShelter("candidate", id, reducedMotion);
    mapElement.current?.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }, [shelterInfo, reducedMotion]);
  const choosePlanK = useCallback((value: number) => setPlanK(shelterInfo ? clampPlanK(value, shelterInfo) : 1), [shelterInfo]);
  const unmodelledCandidates = useMemo<ReadonlySet<string>>(
    () => new Set(manifest?.shelters ? manifest.shelters.candidates.filter((candidate) => !siteModelled(candidate)).map((candidate) => candidate.id) : []),
    [manifest],
  );

  const exportSource = useMemo<ReplayExportSource | null>(
    () => (data && derived && hand ? { manifest: data.manifest, roads: data.roads, roadProps: derived.roadProps, facilityProps: derived.facilityProps, hand } : null),
    [data, derived, hand],
  );

  // --- Render ----------------------------------------------------------------------------------
  const lang: Language = language;
  const unit = { m: t("m", "ม."), km2: t("km²", "ตร.กม."), km: t("km", "กม.") };
  const header = <WorkspaceHeader activeSurface="studio" language={language} onLanguageChange={setLanguage} />;
  const intro = (
    <section className={styles.hero} aria-labelledby="mae-sai-replay-title">
      <nav className={styles.breadcrumbs} aria-label={t("Breadcrumb", "เส้นทางนำทาง")}>
        <a href="/studio/">{t("Studio", "สตูดิโอ")}</a><span aria-hidden="true">/</span><span>{t("Case replay", "การย้อนดูเหตุการณ์")}</span>
      </nav>
      <p className={styles.eyebrow}>{t("CASE REPLAY · MAE SAI · SEPTEMBER 2024", "ย้อนดูเหตุการณ์ · แม่สาย · กันยายน 2024")}</p>
      <h1 id="mae-sai-replay-title">{t("Mae Sai flood, September 2024 — day by day", "น้ำท่วมแม่สาย กันยายน 2024 — ไล่เรียงรายวัน")}</h1>
      <p className={styles.lead}>{t(
        "Replay the flood from 9 to 19 September (local time). Dated satellite images are layered with a terrain-model reconstruction of the water, and the modelled impact figures step through the event hour by hour.",
        "ย้อนดูน้ำท่วมตั้งแต่วันที่ 9 ถึง 19 กันยายน (เวลาท้องถิ่น) โดยซ้อนภาพดาวเทียมที่ระบุวันที่เข้ากับขอบเขตน้ำที่จำลองจากแบบจำลองภูมิประเทศ และตัวเลขผลกระทบจากแบบจำลองจะเปลี่ยนไปทีละชั่วโมงตลอดเหตุการณ์",
      )}</p>
      <p className={styles.banner} role="note">
        <strong>{t("Historical reconstruction for preparedness learning — not real-time, not an official warning.", "การจำลองย้อนหลังเพื่อการเรียนรู้ด้านการเตรียมพร้อม — ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่คำเตือนอย่างเป็นทางการ")}</strong>
      </p>
    </section>
  );

  if (load.status === "error") {
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    return (
      <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
        {header}
        <div className={styles.container}>
          {intro}
          <div className={styles.errorBox} role="alert">
            <h2>{t("The replay data could not be loaded.", "โหลดข้อมูลการย้อนดูเหตุการณ์ไม่สำเร็จ")}</h2>
            <p>{offline
              ? t("You are offline and this replay's data has not been saved on this device yet. Open the replay once while online to keep a copy for offline use.", "ขณะนี้ออฟไลน์ และยังไม่ได้บันทึกข้อมูลการย้อนดูนี้ไว้ในอุปกรณ์ เปิดการย้อนดูหนึ่งครั้งขณะออนไลน์เพื่อเก็บสำเนาไว้ใช้แบบออฟไลน์")
              : t("Check your connection and try again. No figures are shown without their source data.", "ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง ระบบจะไม่แสดงตัวเลขใดหากไม่มีข้อมูลต้นทาง")}</p>
            <button type="button" className={styles.button} onClick={() => {
              setLoad({ status: "loading" });
              setHandFailed(false);
              setHand(null);
              setPopulation({ status: "loading" });
              setAccessNodes({ status: "loading" });
              setLinkReady(false);
              setReloadKey((key) => key + 1);
            }}>
              {t("Try again", "ลองอีกครั้ง")}
            </button>
          </div>
        </div>
      </main>
    );
  }

  const phaseLabel = phase ? phase.label[lang] : "";
  const moment = formatMoment(time, lang);
  const stageText = `${t("assumed stage", "ระดับน้ำสมมุติ")} ${stage.toFixed(2)} ${unit.m}`;
  const valueText = `${moment} · ${phaseLabel} · ${stageText}`;
  const observationById = new Map(derived?.observations.map((entry) => [entry.observation.id, entry]) ?? []);
  const radarFirst = derived?.radar[0];
  const radarLast = derived?.radar.at(-1);
  const radarSpan = radarFirst && radarLast
    ? `${formatShortDate(radarFirst.observation.local, lang)} → ${formatLocalStamp(radarLast.observation.local, lang)}`
    : "";
  const layerOf = (id: string | null) => (id ? derived?.layersById.get(id) : undefined);

  const imageryLabel = (id: string): string => {
    if (id === "auto") return t("Auto — latest optical image at this moment", "อัตโนมัติ — ภาพเชิงแสงล่าสุด ณ ช่วงเวลานี้");
    if (id === "none") return t("None (basemap only)", "ไม่แสดงภาพ (แผนที่ฐานเท่านั้น)");
    const layer = layerOf(id);
    if (layer?.kind === "terrain") return t("Terrain (hillshade)", "ภูมิประเทศ (แสงเงา)");
    if (layer?.kind === "sentinel-1-change") return t(`Radar change (${layerSpan(layer, "en")})`, `การเปลี่ยนแปลงเรดาร์ (${layerSpan(layer, "th")})`);
    return observationById.get(id)?.observation.label[lang] ?? id;
  };
  /** Short dated label for a comparison side, date first so a narrow label still shows when the image was taken. */
  const sideLabel = (choice: string, resolved: string | null): string => {
    const layer = layerOf(resolved);
    const observation = resolved ? observationById.get(resolved)?.observation : undefined;
    const base = observation
      ? `${formatLocalStamp(observation.local, lang)} · ${sensorName(observation)}`
      : layer?.kind === "terrain"
        ? t("Terrain (static)", "ภูมิประเทศ (คงที่)")
        : layer?.kind === "sentinel-1-change"
          ? t(`Radar change ${layerSpan(layer, "en")}`, `การเปลี่ยนแปลงเรดาร์ ${layerSpan(layer, "th")}`)
          : t("No image", "ไม่มีภาพ");
    return choice === "auto" ? `${t("Auto", "อัตโนมัติ")}: ${base}` : base;
  };

  let caption = "";
  const activeLayer = layerOf(activeImagery);
  if (activeImagery && observationById.has(activeImagery)) {
    const entry = observationById.get(activeImagery)!;
    caption = `${entry.observation.label[lang]} · ${formatAge(time - entry.at, lang)}`;
  } else if (activeLayer?.kind === "sentinel-1-change") {
    caption = t(`Sentinel-1 radar change · ${radarSpan} (different orbit directions)`, `การเปลี่ยนแปลงเรดาร์ Sentinel-1 · ${radarSpan} (ทิศทางวงโคจรต่างกัน)`);
  } else if (activeLayer?.kind === "terrain") {
    caption = t("Terrain · Copernicus DEM hillshade (static)", "ภูมิประเทศ · แสงเงาจาก Copernicus DEM (ไม่เปลี่ยนตามเวลา)");
  } else {
    caption = t("No imagery · OpenStreetMap basemap", "ไม่แสดงภาพ · แผนที่ฐาน OpenStreetMap");
  }

  const preEvent = (derived?.observations ?? [])
    .filter((entry) => entry.at < 0)
    .map((entry) => `${sensorName(entry.observation)} ${formatShortDate(entry.observation.local, lang)}`)
    .join(", ");
  const gapText = gap
    ? t(
      `These inputs contain no satellite image between ${formatLocalStamp(gap.before.local, "en")} and ${formatLocalStamp(gap.after.local, "en")}. The water shown now is the model only.`,
      `ข้อมูลชุดนี้ไม่มีภาพดาวเทียมระหว่าง ${formatLocalStamp(gap.before.local, "th")} ถึง ${formatLocalStamp(gap.after.local, "th")} น้ำที่เห็นขณะนี้มาจากแบบจำลองเท่านั้น`,
    )
    : "";
  const isLowConfidence = manifest?.confidence.toLowerCase() === "low";
  const waterModes: [WaterMode, string][] = [
    ["depth", t("Depth at this moment", "ความลึก ณ ช่วงเวลานี้")],
    ["arrival", t("First flooded (hour)", "เวลาที่เริ่มท่วม (ชั่วโมง)")],
    ["duration", t("Hours under water", "จำนวนชั่วโมงที่จมน้ำ")],
    ...(manifest?.population ? [
      ["people", t("People in flood water", "ประชากรในพื้นที่น้ำท่วม")],
      ["residents", t("All residents", "ผู้อยู่อาศัยทั้งหมด")],
    ] as [WaterMode, string][] : []),
  ];
  const residentsMode = waterMode === "people" || waterMode === "residents";
  const residentsStatus = residentsMode && manifest?.population
    ? population.status === "error"
      ? t("The residents layer could not be loaded; the map shows water depth instead.", "โหลดชั้นข้อมูลผู้อยู่อาศัยไม่สำเร็จ แผนที่จึงแสดงความลึกของน้ำแทน")
      : !peopleRaster && hand ? t("Preparing the residents layer…", "กำลังเตรียมชั้นข้อมูลผู้อยู่อาศัย…") : ""
    : "";
  const roadModes: [RoadMode, string][] = [
    ["state", t("State now", "สถานะขณะนี้")],
    ["hours", t("Hours cut", "ชั่วโมงที่ถูกตัดขาด")],
  ];
  const updateSide = (index: 0 | 1, value: string) => {
    const base = sides ?? [value, value];
    setCompareSides(index === 0 ? [value, base[1]] : [base[0], value]);
  };

  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
      {header}
      <div className={styles.container}>
        {intro}
        <div className={styles.layout}>
          <section className={styles.stage} aria-label={t("Flood replay map and timeline", "แผนที่และเส้นเวลาการย้อนดูน้ำท่วม")}>
            <div className={styles.toolbar}>
              <div className={styles.toolGroup}>
                <label className={styles.field}>
                  <span>{t("Imagery", "ภาพพื้นหลัง")}</span>
                  <select value={imagery} onChange={(event) => setImagery(event.target.value)} disabled={!derived || comparing}>
                    {(derived?.imageryIds ?? ["auto", "none"]).map((id) => <option key={id} value={id}>{imageryLabel(id)}</option>)}
                  </select>
                </label>
                <button type="button" className={styles.toggleButton} aria-pressed={comparing} disabled={!derived?.defaultSides && !compareSides}
                  onClick={() => setCompareOn((value) => !value)}>
                  {t("Compare", "เปรียบเทียบ")}
                </button>
                {comparing && sides && derived && (
                  <div className={styles.compareFields}>
                    <label className={styles.field}>
                      <span>{t("Left of divider", "ด้านซ้ายของเส้นแบ่ง")}</span>
                      <select value={sides[0]} onChange={(event) => updateSide(0, event.target.value)}>
                        {derived.compareIds.map((id) => <option key={id} value={id}>{imageryLabel(id)}</option>)}
                      </select>
                    </label>
                    <label className={styles.field}>
                      <span>{t("Right of divider", "ด้านขวาของเส้นแบ่ง")}</span>
                      <select value={sides[1]} onChange={(event) => updateSide(1, event.target.value)}>
                        {derived.compareIds.map((id) => <option key={id} value={id}>{imageryLabel(id)}</option>)}
                      </select>
                    </label>
                  </div>
                )}
              </div>
              <div className={styles.toolGroup}>
                <fieldset className={styles.segmented}>
                  <legend>{t("Reconstructed water and residents (model) show", "น้ำที่จำลองและผู้อยู่อาศัย (แบบจำลอง) แสดงเป็น")}</legend>
                  <div>
                    {waterModes.map(([mode, label]) => (
                      <label key={mode}>
                        <input type="radio" name="mae-sai-water-mode" value={mode} checked={waterMode === mode} onChange={() => setWaterMode(mode)} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <label className={styles.field}>
                  <span>{t("Water opacity", "ความทึบของน้ำ")} · {Math.round(waterOpacity * 100)}%</span>
                  <input type="range" min={0} max={1} step={0.05} value={waterOpacity} onChange={(event) => setWaterOpacity(Number(event.target.value))} />
                </label>
              </div>
              <div className={styles.toolGroup}>
                <fieldset className={styles.segmented}>
                  <legend>{t("Roads (model) show", "ถนน (แบบจำลอง) แสดงเป็น")}</legend>
                  <div>
                    {roadModes.map(([mode, label]) => (
                      <label key={mode}>
                        <input type="radio" name="mae-sai-road-mode" value={mode} checked={roadMode === mode} onChange={() => setRoadMode(mode)} />
                        <span>{label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset className={styles.toggles}>
                  <legend>{t("Show", "แสดง")}</legend>
                  <label><input type="checkbox" checked={showTambons} onChange={(event) => setShowTambons(event.target.checked)} /> {t("Subdistricts", "ขอบเขตตำบล")}</label>
                  <label><input type="checkbox" checked={showRoads} onChange={(event) => setShowRoads(event.target.checked)} /> {t("Roads", "ถนน")}</label>
                  <label><input type="checkbox" checked={showFacilities} onChange={(event) => setShowFacilities(event.target.checked)} /> {t("Candidate facilities", "สถานที่สำคัญที่เป็นไปได้")}</label>
                  {shelterInfo && (
                    <>
                      <label><input type="checkbox" checked={showReported} onChange={(event) => setShowReported(event.target.checked)} /> {t("Shelters reported in 2024", "ที่พักพิงที่มีรายงานปี 2024")}</label>
                      <label><input type="checkbox" checked={showCandidates} onChange={(event) => setShowCandidates(event.target.checked)} /> {t("Ranked plan sites", "สถานที่ในแผนจัดอันดับ")}</label>
                      <label><input type="checkbox" checked={showIneligible} onChange={(event) => setShowIneligible(event.target.checked)} /> {t("Ineligible candidates", "สถานที่ที่ไม่เข้าเกณฑ์")}</label>
                    </>
                  )}
                  {accessInfo && (
                    <label><input type="checkbox" checked={showCutoff} onChange={(event) => setShowCutoff(event.target.checked)} /> {t("People cut off (scenario)", "ผู้ที่ถูกตัดขาด (สถานการณ์จำลอง)")}</label>
                  )}
                </fieldset>
              </div>
            </div>

            <div className={styles.mapFrame}>
              <div ref={mapElement} className={styles.map} role="region" aria-label={t("Map of Mae Sai with imagery, reconstructed water, roads and candidate facilities", "แผนที่แม่สายพร้อมภาพดาวเทียม น้ำที่จำลอง ถนน และสถานที่สำคัญที่เป็นไปได้")} />
              {manifest && !comparing && <p className={styles.caption}>{caption}</p>}
              {comparing && sides && mapReady && (
                <>
                  {/* A side narrower than ~15 % has no room for its label; the divider's value text still names both images. */}
                  {comparePct >= 15 && (
                    <p className={`${styles.compareLabel} ${styles.compareLabelLeft}`} style={{ right: `calc(${100 - comparePct}% + 16px)`, maxWidth: `max(0px, min(42%, calc(${comparePct}% - 72px)))` }}>
                      ◀ {sideLabel(sides[0], compareLeft)}
                    </p>
                  )}
                  {comparePct <= 85 && (
                    <p className={`${styles.compareLabel} ${styles.compareLabelRight}`} style={{ left: `calc(${comparePct}% + 16px)`, maxWidth: `max(0px, min(42%, calc(${100 - comparePct}% - 26px)))` }}>
                      {sideLabel(sides[1], compareRight)} ▶
                    </p>
                  )}
                  <CompareDivider
                    pct={comparePct}
                    onChange={setComparePct}
                    label={t("Imagery comparison divider", "เส้นแบ่งเปรียบเทียบภาพ")}
                    valueText={t(
                      `${Math.round(comparePct)}% · left: ${sideLabel(sides[0], compareLeft)}; right: ${sideLabel(sides[1], compareRight)}`,
                      `${Math.round(comparePct)}% · ซ้าย: ${sideLabel(sides[0], compareLeft)}; ขวา: ${sideLabel(sides[1], compareRight)}`,
                    )}
                  />
                </>
              )}
              {(!mapReady || (!hand && !handFailed)) && (
                <p className={styles.mapStatus} role="status">
                  {!mapReady ? t("Loading the replay…", "กำลังโหลดการย้อนดูเหตุการณ์…") : t("Preparing the water model…", "กำลังเตรียมแบบจำลองน้ำ…")}
                </p>
              )}
              {handFailed && <p className={`${styles.mapStatus} ${styles.mapWarning}`} role="alert">{t("The water model could not be loaded; imagery, roads and figures remain available.", "โหลดแบบจำลองน้ำไม่สำเร็จ แต่ยังดูภาพ ถนน และตัวเลขได้")}</p>}
              {mapReady && !handFailed && hand && residentsStatus && (
                <p className={`${styles.mapStatus}${population.status === "error" ? ` ${styles.mapWarning}` : ""}`} role={population.status === "error" ? "alert" : "status"}>{residentsStatus}</p>
              )}
              {mapReady && (basemapIssue || !online) && (
                <p className={styles.basemapNote} role="status" data-testid="basemap-note">{online
                  ? t(
                    "The street basemap could not load; it needs an internet connection. Imagery, the water model and roads still show from this device.",
                    "โหลดแผนที่ถนนพื้นฐานไม่ได้ เนื่องจากต้องใช้อินเทอร์เน็ต ภาพดาวเทียม แบบจำลองน้ำ และถนนยังแสดงจากอุปกรณ์นี้ได้",
                  )
                  : t(
                    "Offline: the street basemap is online-only. Imagery, the water model and roads still show from this device.",
                    "ออฟไลน์: แผนที่ถนนพื้นฐานใช้ได้เฉพาะเมื่อออนไลน์ ภาพดาวเทียม แบบจำลองน้ำ และถนนยังแสดงจากอุปกรณ์นี้ได้",
                  )}</p>
              )}
            </div>

            {manifest && derived && (
              <div className={styles.dock}>
                <div className={styles.dockTop}>
                  <button type="button" className={styles.play} onClick={togglePlay} aria-keyshortcuts="Space">
                    <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>
                    {playing ? t("Pause", "หยุดชั่วคราว") : time >= TIMELINE_END_T - 1e-6 ? t("Replay", "เล่นอีกครั้ง") : t("Play", "เล่น")}
                  </button>
                  <div className={styles.readout} data-testid="replay-readout">
                    <strong>{moment}</strong>
                    <span>{phaseLabel} · {stageText}</span>
                  </div>
                  {preEvent && <p className={styles.preEvent}>{t(`◂ Pre-event images: ${preEvent}`, `◂ ภาพก่อนเกิดเหตุ: ${preEvent}`)}</p>}
                </div>

                <div className={styles.track}>
                  <div className={styles.band} aria-hidden="true">
                    {manifest.phases.map((item) => {
                      const start = tFromLocalDate(item.start);
                      const end = tFromLocalDate(item.end) + 1;
                      const colour = PHASE_COLOURS[item.id] ?? "#cbd5e1";
                      const active = phase?.id === item.id;
                      const [shortEn, shortTh] = PHASE_SHORT[item.id] ?? [item.label.en.split(/[\s/]/)[0], item.label.th];
                      return (
                        <span key={item.id} className={styles.segment} data-active={active || undefined} title={`${item.label[lang]} · ${formatDateRange(item.start, item.end, lang)}`}
                          style={{
                            left: `${(start / TIMELINE_END_T) * 100}%`,
                            width: `${((end - start) / TIMELINE_END_T) * 100}%`,
                            background: active ? colour : tint(colour, 0.45),
                            color: active && item.id === "peak" ? "#fff" : PHASE_TEXT_DARK,
                          }}>
                          <span className={styles.segmentFull}>{item.label[lang]}</span>
                          <span className={styles.segmentShort}>{lang === "th" ? shortTh : shortEn}</span>
                        </span>
                      );
                    })}
                    {derived.observations.filter((entry) => entry.at >= 0 && entry.at <= TIMELINE_END_T).map((entry) => (
                      <span key={entry.observation.id} className={styles.obsMarker} data-kind={entry.observation.kind} style={{ left: `${(entry.at / TIMELINE_END_T) * 100}%` }}
                        title={entry.observation.label[lang]}>
                        {entry.observation.kind === "optical" ? "S2" : "S1"}
                      </span>
                    ))}
                  </div>
                  <input
                    className={styles.range}
                    type="range"
                    min={0}
                    max={HOUR_STEPS}
                    step={1}
                    value={hour}
                    aria-label={t("Replay time (hourly)", "เวลาในการย้อนดู (รายชั่วโมง)")}
                    aria-valuetext={valueText}
                    aria-keyshortcuts="Shift+ArrowLeft Shift+ArrowRight"
                    onChange={(event) => jumpTo(Number(event.target.value) / 24)}
                    onKeyDown={(event) => {
                      if (!event.shiftKey || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
                      event.preventDefault();
                      jumpTo((hourIndex(timeRef.current) + (event.key === "ArrowRight" ? 24 : -24)) / 24);
                    }}
                  />
                </div>
                <PhaseLegend phases={manifest.phases} activeId={phase?.id ?? null} language={lang} />
                <div className={styles.days} role="group" aria-label={t("Jump to a day (local noon)", "ไปยังวัน (เที่ยงวันเวลาท้องถิ่น)")}>
                  {manifest.days.map((day, index) => (
                    <button key={day.date} type="button" aria-pressed={hour === index * 24 + 12}
                      aria-label={t(`${formatShortDate(day.date, "en")}, noon`, `${formatShortDate(day.date, "th")} เที่ยงวัน`)}
                      onClick={() => jumpTo(index + 0.5)}>
                      {Number(day.date.slice(8))}
                    </button>
                  ))}
                </div>
                <p className={styles.hint}>{t("Space plays or pauses · arrow keys move one hour · Shift + arrows or the day buttons move one day", "Space เล่น/หยุด · ปุ่มลูกศรเลื่อนทีละชั่วโมง · Shift + ลูกศร หรือปุ่มวันเลื่อนทีละวัน")}</p>
                <Hydrograph manifest={manifest} time={time} stage={stage} observations={derived.observations} language={lang} />
              </div>
            )}

            {manifest && (
              <div className={styles.shareBar} role="group" aria-label={t("Share and export", "แชร์และส่งออก")}>
                <div className={styles.actionRow}>
                  <button type="button" className={styles.secondaryButton} onClick={() => void copyLink()} disabled={!linkReady}>
                    {t("Copy link to this moment", "คัดลอกลิงก์ของช่วงเวลานี้")}
                  </button>
                </div>
                {share.status === "manual" && (
                  <label className={styles.shareField}>
                    <span>{t("Link to this moment", "ลิงก์ของช่วงเวลานี้")}</span>
                    <input ref={shareField} type="text" readOnly value={share.url} onFocus={(event) => event.currentTarget.select()} />
                  </label>
                )}
                <p className={styles.exportStatus} role="status" aria-live="polite">
                  {share.status === "copied"
                    ? t("Link to this moment copied.", "คัดลอกลิงก์ของช่วงเวลานี้แล้ว")
                    : share.status === "manual"
                      ? t("Copying is not available here; select the link below and copy it.", "คัดลอกอัตโนมัติไม่ได้ในเบราว์เซอร์นี้ เลือกลิงก์ด้านล่างแล้วคัดลอกเอง")
                      : ""}
                </p>
                <ReplayExportPanel source={exportSource} time={time} language={lang} waterOpacity={waterOpacity} />
              </div>
            )}

            <TimelineLegend
              language={lang}
              unmodelledRoads={!!derived?.hasUnmodelledRoads}
              unmodelledFacilities={!!derived?.hasUnmodelledFacilities}
              waterMode={residentsMode && !peopleRaster ? "depth" : waterMode}
              roadMode={roadMode}
              arrival={derived?.arrival ?? []}
              densityMax={manifest?.population?.max_per_ha}
              shelters={shelterInfo ? {
                reported: showReported, candidates: showCandidates, ineligible: showIneligible,
                command: shelterInfo.reported.some((shelter) => shelter.lat !== null && reportedSiteRole(shelter).role === "relief_command"),
                unmodelled: unmodelledCandidates.size > 0,
              } : undefined}
              cutoff={showCutoff && !!accessInfo}
            />
          </section>

          <aside className={styles.panel} aria-label={t("Impact at this moment", "ผลกระทบ ณ ช่วงเวลานี้")}>
            {!manifest || !stats || !derived || !phase ? (
              <p className={styles.muted} role="status">{t("Loading figures…", "กำลังโหลดตัวเลข…")}</p>
            ) : (
              <>
                <div className={styles.card}>
                  <p className={styles.eyebrow}>{t("THIS MOMENT", "ช่วงเวลานี้")}</p>
                  <h2 className={styles.moment}>{moment}</h2>
                  <span className={styles.phaseBadge} style={{ background: PHASE_COLOURS[phase.id] ?? "#cbd5e1", color: phase.id === "peak" ? "#fff" : PHASE_TEXT_DARK }}>{phase.label[lang]}</span>
                  <p>{phase.summary[lang]}</p>
                  <p className={styles.muted}>{manifest.hand.depth_factor
                    ? t(
                      `Assumed Sai main-stem stage ${stage.toFixed(2)} m at the Mae Sai bridges (illustrative, not a gauge reading); tributary channels rise k × stage, less than this.`,
                      `ระดับน้ำสมมุติของลำน้ำหลักแม่น้ำสายที่สะพานแม่สาย ${stage.toFixed(2)} ม. (เพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ) ลำน้ำสาขาสูงขึ้น k × ระดับน้ำ ซึ่งน้อยกว่านี้`,
                    )
                    : t(`Assumed river stage ${stage.toFixed(2)} m above the mapped channel (illustrative, not a gauge reading).`, `ระดับน้ำสมมุติ ${stage.toFixed(2)} ม. เหนือร่องน้ำ (เพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ)`)}</p>
                </div>

                <ImpactCard manifest={manifest} stats={stats} derived={derived} language={lang} />

                {manifest.population && stats.people_in_water !== undefined && (
                  <PeopleInWaterCard population={manifest.population} stats={stats} names={derived.names} scale={derived.peopleScale} language={lang} />
                )}

                {accessInfo && shelterInfo && (
                  <AccessCard
                    access={accessInfo}
                    shelters={shelterInfo}
                    snapshot={snapshot}
                    series={lostSeries}
                    time={time}
                    names={derived.names}
                    tambonTotals={accessModel?.tambonTotals ?? null}
                    shelterSet={shelterSet}
                    planK={planK}
                    onShelterSet={setShelterSet}
                    onPlanK={choosePlanK}
                    showCutoff={showCutoff}
                    onShowCutoff={setShowCutoff}
                    language={lang}
                    status={accessNodes.status === "error" || (accessModel && selectedSetIndex < 0) ? "error" : accessModel ? "ready" : "loading"}
                  />
                )}

                {priorityRows && (
                  <PriorityCard
                    rows={priorityRows}
                    names={derived.names}
                    confidence={manifest.confidence}
                    confidenceReason={manifest.confidence_reason}
                    timestamp={manifest.source_timestamp}
                    shelterLabel={shelterSet === "reported"
                      ? t("the shelters reported in use in Sep 2024", "ที่พักพิงที่มีรายงานว่าใช้งานในเดือน ก.ย. 2024")
                      : t(`the first ${planK} sites of the ranked plan`, `สถานที่ ${planK} แห่งแรกของแผนที่จัดลำดับ`)}
                    moment={moment}
                    phaseId={phase?.id ?? null}
                    language={lang}
                  />
                )}

                {shelterInfo && (
                  <ShelterPlanCard shelters={shelterInfo} k={planK} onPlanK={choosePlanK}
                    language={lang} onShowCandidate={showCandidateOnMap} />
                )}

                {shelterInfo && (
                  <OtherCandidatesCard shelters={shelterInfo} k={planK} language={lang} onShowCandidate={showCandidateOnMap} />
                )}

                {shelterInfo && <ReportedSheltersCard shelters={shelterInfo} language={lang} onShowReported={showReportedOnMap} />}

                <RouteCutsCard groups={derived.routeGroups} names={derived.names} language={lang} focused={focusedRoute} onFocus={focusRoute} onReset={resetRouteFocus} />

                <WetFacilitiesCard facilities={derived.facilityProps} stage={stage} language={lang} />

                <div className={styles.card}>
                  <h2>{t("Evidence for this moment", "หลักฐานของช่วงเวลานี้")}</h2>
                  <dl className={styles.evidence}>
                    <div><dt>{t("Imagery", "ภาพ")}</dt><dd>{caption}</dd></div>
                    {gap && <div><dt>{t("Image gap", "ช่วงไม่มีภาพ")}</dt><dd>{gapText}</dd></div>}
                    <div><dt>{t("Water", "น้ำ")}</dt><dd>{t("Model reconstruction from terrain (height above nearest drainage) at the assumed stage — not an observation.", "การจำลองจากภูมิประเทศ (ความสูงเหนือร่องน้ำที่ใกล้ที่สุด) ที่ระดับน้ำสมมุติ — ไม่ใช่การสังเกตการณ์จริง")}</dd></div>
                    <div><dt>{t("Confidence", "ความเชื่อมั่น")}</dt><dd><span className={styles.confidence}>{isLowConfidence ? t("LOW", "ต่ำ") : manifest.confidence}</span> <Localized text={manifest.confidence_reason} language={lang} /></dd></div>
                    {manifest.population && (
                      <div><dt>{t("Residents", "ผู้อยู่อาศัย")}</dt><dd>{t(
                        `${manifest.population.source} (${manifest.population.timestamp}, ${manifest.population.licence}); modelled residents, not the 2024 population.`,
                        `${manifest.population.source} (${manifest.population.timestamp}, ${manifest.population.licence}) ผู้อยู่อาศัยตามแบบจำลอง ไม่ใช่ประชากรปี 2024`,
                      )}</dd></div>
                    )}
                    {accessInfo && (
                      <div><dt>{t("Access", "การเข้าถึง")}</dt><dd>{t(
                        "T1 scenario (model), not observed evacuation outcomes; same stage and road rules as the water above.",
                        "สถานการณ์จำลองระดับ T1 ไม่ใช่ผลการอพยพที่สังเกตได้ ใช้ระดับน้ำและเกณฑ์ถนนเดียวกับน้ำด้านบน",
                      )}</dd></div>
                    )}
                    {manifest.gauge_note && (
                      <div><dt>{t("Gauge", "สถานีวัดน้ำ")}</dt><dd><Localized text={manifest.gauge_note} language={lang} /></dd></div>
                    )}
                  </dl>
                  <RadarCheck manifest={manifest} radarSpan={radarSpan} language={lang} />
                  <ExternalChecks manifest={manifest} language={lang} />
                </div>

                <SourcesPanel manifest={manifest} language={lang} offlineCopy={offlineCopy} />
              </>
            )}
          </aside>
        </div>
        <footer className={styles.footer}>{t(
          "FloodGuard supports preparedness and rapid post-event prioritisation. This replay is a historical reconstruction and does not feed the planning decision layer. Its scenario Flood Preparedness Priority Score ranks subdistricts at each moment with the locked FPPS weights and A–E rules; while confidence is low every action class is E (Monitor and Verify). Card themes such as “Protect Lives Now” only name the planning theme a card relates to.",
          "FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญอย่างรวดเร็วหลังเกิดเหตุ การย้อนดูนี้เป็นการจำลองเหตุการณ์ในอดีต และไม่ถูกนำไปใช้ในส่วนตัดสินใจเพื่อการวางแผน คะแนนลำดับความสำคัญด้านการเตรียมพร้อมรับน้ำท่วม (FPPS) ตามสถานการณ์จำลองจัดลำดับตำบลในแต่ละช่วงเวลาด้วยน้ำหนักและกฎกลุ่ม A–E ที่โครงการกำหนดไว้ ขณะที่ความเชื่อมั่นต่ำ ทุกตำบลอยู่ในกลุ่ม E (เฝ้าระวังและตรวจสอบ) ประเด็นที่ระบุบนการ์ด เช่น “ปกป้องชีวิตทันที” บอกเพียงหัวข้อการวางแผนที่การ์ดนั้นเกี่ยวข้อง",
        )}</footer>
      </div>
    </main>
  );
}

/** Focusable vertical divider for the imagery swipe: pointer drag, arrow keys (Shift for 10 %), Home and End. */
function CompareDivider({ pct, onChange, label, valueText }: { pct: number; onChange: (pct: number) => void; label: string; valueText: string }) {
  const fromPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    const frame = event.currentTarget.parentElement?.getBoundingClientRect();
    if (!frame || frame.width <= 0) return;
    onChange(Math.min(100, Math.max(0, ((event.clientX - frame.left) / frame.width) * 100)));
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 10 : 2;
    const next = event.key === "ArrowLeft" || event.key === "ArrowDown" ? pct - step
      : event.key === "ArrowRight" || event.key === "ArrowUp" ? pct + step
        : event.key === "PageDown" ? pct - 10
          : event.key === "PageUp" ? pct + 10
            : event.key === "Home" ? 0
              : event.key === "End" ? 100
                : null;
    if (next === null) return;
    event.preventDefault();
    onChange(Math.min(100, Math.max(0, next)));
  };
  return (
    <div
      className={styles.compareDivider}
      style={{ left: `${pct}%` }}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-orientation="horizontal"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
      aria-valuetext={valueText}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        fromPointer(event);
      }}
      onPointerMove={(event) => {
        if (event.currentTarget.hasPointerCapture(event.pointerId)) fromPointer(event);
      }}
      onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
    >
      <span className={styles.compareHandle} aria-hidden="true">‹ ›</span>
    </div>
  );
}

/** Legend line under the phase band: every phase with its full label and local dates. */
function PhaseLegend({ phases, activeId, language }: { phases: readonly TimelinePhase[]; activeId: string | null; language: Language }) {
  return (
    <ul className={styles.phaseLegend} aria-label={language === "th" ? "ช่วงของเหตุการณ์" : "Event phases"}>
      {phases.map((item) => (
        <li key={item.id} data-active={item.id === activeId || undefined}>
          <i aria-hidden="true" style={{ background: PHASE_COLOURS[item.id] ?? "#cbd5e1" }} />
          {item.label[language]} · {formatDateRange(item.start, item.end, language)}
        </li>
      ))}
    </ul>
  );
}

type OfflineCopy = { cached: number; failed: number; total: number };

/**
 * Sources, assumptions and limits. Manifest assumptions stay in their English original; where this revision states
 * one too simply, the page adds a bilingual note under it. Memoised: it does not depend on the replay clock.
 */
const SourcesPanel = memo(function SourcesPanel({ manifest, language, offlineCopy }: { manifest: TimelineManifest; language: Language; offlineCopy: OfflineCopy | null }) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const accessInfo = manifest.access ?? null;
  const confidenceText = manifest.confidence.toLowerCase() === "low" ? t("low", "ต่ำ") : manifest.confidence;
  return (
    <details className={styles.card} data-testid="sources-panel">
      <summary>{t("Sources, assumptions and limits", "แหล่งข้อมูล สมมติฐาน และข้อจำกัด")}</summary>
      {th && <p className={styles.muted}>รายละเอียดด้านล่างคงไว้เป็นภาษาอังกฤษตามต้นฉบับ ยกเว้นหมายเหตุของหน้านี้</p>}
      <h3>{t("Sources", "แหล่งข้อมูล")}</h3>
      <ul className={styles.list} lang="en">
        {manifest.sources.map((source) => (
          <li key={source.id}><strong>{source.name}</strong> — {source.licence}. {source.attribution}. <span className={styles.muted}>{source.timestamp}</span></li>
        ))}
        {manifest.population && (
          <li><strong>{manifest.population.source}</strong> — {manifest.population.licence}. {manifest.population.note} <span className={styles.muted}>{manifest.population.timestamp}</span></li>
        )}
      </ul>
      {manifest.external_references && manifest.external_references.length > 0 && (
        <>
          <h3>{t("Other references (not ingested)", "เอกสารอ้างอิงอื่น (ยังไม่ได้นำเข้า)")}</h3>
          <ul className={styles.list} lang="en">
            {manifest.external_references.map((reference) => (
              <li key={reference.url}>
                {reference.name}{reference.note ? ` — ${reference.note}` : ""}{" "}
                <a href={reference.url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{reference.url}</a>
              </li>
            ))}
          </ul>
        </>
      )}
      {accessInfo && (
        <>
          <h3>{t("Evacuation access scenario", "สถานการณ์จำลองการเข้าถึงการอพยพ")}</h3>
          <ul className={styles.list} lang="en">
            <li>{accessInfo.scenario_tier}. {accessInfo.definition}</li>
            <li>Travel: {accessInfo.travel_mode}; threshold {accessInfo.threshold_m} m; levels {accessInfo.levels[0]}–{accessInfo.levels.at(-1)} m every {accessLevelStep(accessInfo.levels)} m.</li>
            <li>Residents: {formatPeople(accessInfo.totals.population)} at road nodes ({formatPeople(accessInfo.totals.vulnerable)} in the terrain/remoteness proxy group, {formatPeople(accessInfo.totals.non_vulnerable)} others).</li>
          </ul>
        </>
      )}
      <h3>{t("Assumptions", "สมมติฐาน")}</h3>
      <ul className={styles.list}>
        {manifest.assumptions.map((item) => {
          const caveat = assumptionCaveat(item);
          return (
            <li key={item}>
              <span lang="en">{item}</span>
              {caveat && <span className={styles.assumptionNote} data-testid="assumption-note">{t("Page note", "หมายเหตุของหน้านี้")}: {caveat[language]}</span>}
            </li>
          );
        })}
      </ul>
      <h3>{t("Limitations", "ข้อจำกัด")}</h3>
      <ul className={styles.list} lang="en">{manifest.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      <p className={styles.muted}>{t(
        "Arrival, time under water and road-cut hours are counted on the replay's hourly grid: the assumed stage sampled at the start of each local hour, 9 Sep 00:00 to 19 Sep 23:00.",
        "เวลาที่เริ่มท่วม ระยะเวลาที่จมน้ำ และชั่วโมงที่ถนนถูกตัดขาด นับตามช่วงรายชั่วโมงของการย้อนดู โดยใช้ระดับน้ำสมมุติ ณ ต้นชั่วโมงเวลาท้องถิ่น ตั้งแต่ 9 ก.ย. 00:00 ถึง 19 ก.ย. 23:00",
      )}</p>
      <p className={styles.muted}>
        {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: {manifest.source_timestamp} · {manifest.timezone} · {manifest.study_id} {manifestRevision()} · {t("confidence", "ความเชื่อมั่น")}: {confidenceText}
      </p>
      {offlineCopy && (
        <p className={styles.muted}>{offlineCopy.failed === 0 && offlineCopy.cached === offlineCopy.total
          ? t(`Offline copy: this replay's ${offlineCopy.total} data files are saved on this device (the street basemap still needs internet).`, `สำเนาออฟไลน์: บันทึกไฟล์ข้อมูลของการย้อนดูนี้ ${offlineCopy.total} ไฟล์ไว้ในอุปกรณ์แล้ว (แผนที่ถนนพื้นฐานยังต้องใช้อินเทอร์เน็ต)`)
          : t(`Offline copy incomplete: ${offlineCopy.cached} of ${offlineCopy.total} data files saved on this device.`, `สำเนาออฟไลน์ยังไม่ครบ: บันทึกไฟล์ข้อมูลแล้ว ${offlineCopy.cached} จาก ${offlineCopy.total} ไฟล์`)}</p>
      )}
    </details>
  );
});

/** Manifest sentence in Thai when a translation is known, otherwise the English original marked as such. */
function Localized({ text, language }: { text: string; language: Language }) {
  const value = localized(text, language);
  return <span lang={value.lang}>{value.text}</span>;
}

type ReplayDerived = {
  facilityProps: FacilityProps[];
  names: Record<string, TambonProps>;
  tambonScale: number;
};

/** District impact at the current stage, scoped honestly to the modelled part of the district. */
export function ImpactCard({ manifest, stats, derived, language }: {
  manifest: TimelineManifest;
  stats: ReturnType<typeof districtStats>;
  derived: ReplayDerived;
  language: Language;
}) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const unit = { km2: t("km²", "ตร.กม."), km: t("km", "กม.") };
  const coverage = manifest.model_coverage;
  const tambonCount = Object.keys(manifest.tambon_histograms).length;
  const modelled = Math.round(coverage.modelled_km2);
  const district = Math.round(coverage.district_km2);
  const scope = t(
    `Modelled parts of the ${tambonCount === 8 ? "eight" : tambonCount} Mae Sai subdistricts — ${modelled} of ${district} km²`,
    `ส่วนที่แบบจำลองครอบคลุมของ ${tambonCount} ตำบลในอำเภอแม่สาย — ${modelled} จาก ${district} ตร.กม.`,
  );
  const reason = localized(coverage.reason, language);
  const facilitiesOutside = manifest.facilities_count.total - manifest.facilities_count.modelled;
  return (
    <div className={styles.card}>
      <h2>{t("Impact (model)", "ผลกระทบ (แบบจำลอง)")}</h2>
      <p className={styles.scope} title={reason.text}>{scope}</p>
      <dl className={styles.kpis}>
        <div><dt>{t("Flooded area", "พื้นที่น้ำท่วม")}</dt><dd>{km(stats.flooded_km2)}<small> {unit.km2}</small></dd></div>
        <div><dt>{t("Roads impassable (≥ 0.3 m)", "ถนนสัญจรไม่ได้ (≥ 0.3 ม.)")}</dt><dd data-tone="alert">{km(stats.road_km_impassable)}<small> {unit.km}</small></dd></div>
        <div><dt>{t("Roads wet (< 0.3 m)", "ถนนมีน้ำ (< 0.3 ม.)")}</dt><dd data-tone="warn">{km(stats.road_km_wet)}<small> {unit.km}</small></dd></div>
        <div><dt>{t("Candidate facilities (OSM) in water", "สถานที่สำคัญที่เป็นไปได้ (ข้อมูล OSM) ที่อยู่ในน้ำ")}</dt><dd>{stats.facilities_wet}<small> / {manifest.facilities_count.modelled}</small></dd></div>
      </dl>
      <p className={styles.muted}>
        {t("Computed in your browser from the terrain model at this stage.", "คำนวณในเบราว์เซอร์ของคุณจากแบบจำลองภูมิประเทศ ณ ระดับน้ำนี้")}{" "}
        {t("Not modelled: ", "ส่วนที่ไม่ได้จำลอง: ")}<span lang={reason.lang}>{reason.text}</span>
        {manifest.roads_not_modelled_km > 0 && <>{" "}{t(
          `${km(manifest.roads_not_modelled_km, 2)} km of mapped road there is drawn grey and dashed and excluded from these figures.`,
          `ถนน ${km(manifest.roads_not_modelled_km, 2)} กม. ในส่วนนั้นแสดงเป็นเส้นประสีเทาและไม่นับรวมในตัวเลขเหล่านี้`,
        )}</>}
        {facilitiesOutside > 0 && <>{" "}{t(
          `${facilitiesOutside} candidate facilit${facilitiesOutside === 1 ? "y is" : "ies are"} outside the model (grey hollow markers) and excluded.`,
          `สถานที่สำคัญที่เป็นไปได้ ${facilitiesOutside} แห่งอยู่นอกแบบจำลอง (วงกลมกลวงสีเทา) และไม่นับรวม`,
        )}</>}
      </p>
      <h3>{t("Flooded area by subdistrict", "พื้นที่น้ำท่วมรายตำบล")}</h3>
      <ul className={styles.bars}>
        {Object.entries(stats.tambon_flooded_km2).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([id, value]) => {
          const share = coverageShare(manifest.tambon_coverage?.[id]);
          const pct = Math.round(share * 100);
          return (
            <li key={id}>
              <span className={styles.barName}>
                <span>{derived.names[id]?.[language] ?? id}</span>
                {share < 0.99 && <small>{t(`(${pct}% modelled)`, `(จำลองได้ ${pct}%)`)}</small>}
              </span>
              <span className={styles.barTrack} aria-hidden="true"><span style={{ width: `${Math.min(100, (value / derived.tambonScale) * 100)}%` }} /></span>
              <span className={styles.barValue}>{km(value)} {unit.km2}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * "Keep Routes Open" list: modelled road groups with the longest impassable spells over the replay.
 * Each entry fits the map to its cut pieces. Memoised: it does not depend on the replay clock.
 */
export const RouteCutsCard = memo(function RouteCutsCard({ groups, names, language, focused, onFocus, onReset }: {
  groups: readonly RoadCutGroup[];
  names: Record<string, TambonProps>;
  language: Language;
  focused: string | null;
  onFocus: (group: RoadCutGroup) => void;
  onReset: () => void;
}) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const tambonName = (id: string) => names[id]?.[language] ?? id;
  return (
    <section className={styles.card} aria-labelledby="mae-sai-route-cuts-title">
      <ThemeEyebrow theme="keep_routes" language={language} />
      <h2 id="mae-sai-route-cuts-title">{t("Longest-cut routes (Keep Routes Open)", "เส้นทางที่ถูกตัดขาดนานที่สุด (รักษาเส้นทางให้สัญจรได้)")}</h2>
      <p className={styles.muted}>{t(
        "Modelled, not observed closures: hours each road piece is impassable (reconstructed depth ≥ 0.3 m) at the assumed stages, 9–19 Sep. Named roads are grouped by name and listed first; unnamed pieces are grouped by class and subdistrict. Select one to show it on the map.",
        "การปิดถนนตามแบบจำลอง ไม่ใช่การปิดที่สังเกตได้จริง: จำนวนชั่วโมงที่ถนนแต่ละช่วงสัญจรไม่ได้ (ความลึกจำลอง ≥ 0.3 ม.) ที่ระดับน้ำสมมุติ 9–19 ก.ย. ถนนที่มีชื่อจัดกลุ่มตามชื่อและแสดงก่อน ถนนไม่มีชื่อจัดกลุ่มตามประเภทและตำบล เลือกเพื่อแสดงบนแผนที่",
      )}</p>
      {groups.length === 0 ? (
        <p>{t("No modelled road piece reaches 0.3 m at any hour of the replay.", "ไม่มีถนนช่วงใดในแบบจำลองที่น้ำลึกถึง 0.3 ม. ตลอดการย้อนดู")}</p>
      ) : (
        <ol className={styles.routeList}>
          {groups.map((group, index) => {
            const classText = group.classes.map((item) => roadClassLabel(item, language)).join(", ");
            const title = group.name ?? `${roadClassLabel(group.classes[0] ?? "", language)} ${t("(unnamed)", "(ไม่มีชื่อ)")}`;
            const titleLang = group.name && THAI_SCRIPT.test(group.name) ? "th" : language;
            const tambons = group.tambons.slice(0, 3).map(tambonName).join(", ") + (group.tambons.length > 3 ? ` +${group.tambons.length - 3}` : "");
            const reopen = group.reopenHour === null
              ? t("not reopened by 20 Sep 00:00", "ยังไม่เปิดถึง 20 ก.ย. 00:00 น.")
              : formatHourStamp(group.reopenHour, language);
            return (
              <li key={group.key}>
                <button type="button" aria-pressed={focused === group.key} onClick={() => onFocus(group)}>
                  <span className={styles.routeHead}>
                    <span className={styles.routeRank} aria-hidden="true">{index + 1}</span>
                    <strong lang={titleLang}>{title}</strong>
                  </span>
                  <span className={styles.routeMeta}>{group.name ? `${classText} · ` : ""}{t("Subdistrict", "ตำบล")}: {tambons}</span>
                  <span className={styles.routeFigures}>
                    <span>{t(`Up to ${group.maxHours} h cut`, `ตัดขาดสูงสุด ${group.maxHours} ชม.`)}</span>
                    <span>{t(`${km(group.kmCut, 2)} km cut`, `ตัดขาด ${km(group.kmCut, 2)} กม.`)}</span>
                  </span>
                  <span className={styles.routeTimes}>{t("First cut", "เริ่มตัดขาด")} {formatHourStamp(group.firstHour, language)} → {t("reopened", "เปิดอีกครั้ง")} {reopen}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
      {focused && (
        <button type="button" className={styles.linkButton} onClick={onReset}>{t("Show the whole area", "แสดงทั้งพื้นที่")}</button>
      )}
    </section>
  );
});

/**
 * Keyboard- and screen-reader-reachable list of modelled candidate facilities in water at `stage`, deepest first.
 * Renders nothing when none are wet.
 */
export function WetFacilitiesCard({ facilities, stage, language }: { facilities: readonly FacilityProps[]; stage: number; language: Language }) {
  const wet = facilitiesInWater(facilities, stage);
  if (wet.length === 0) return null;
  const th = language === "th";
  return (
    <section className={styles.card} aria-labelledby="mae-sai-wet-facilities-title">
      <h2 id="mae-sai-wet-facilities-title">{th ? `สถานที่สำคัญที่เป็นไปได้ที่อยู่ในน้ำขณะนี้ (${wet.length})` : `Candidate facilities in water now (${wet.length})`}</h2>
      <ol className={styles.facilityList}>
        {wet.map(({ facility, depth }) => (
          <li key={facility.id}>
            <span><strong>{facilityTypeLabel(facility.type, language)}</strong> · {facility.n || (th ? "ไม่มีชื่อ" : "Unnamed")}</span>
            <span className={styles.depth}>{th ? `ลึก ≈ ${formatDepth(depth)} ม.` : `depth ≈ ${formatDepth(depth)} m`}</span>
          </li>
        ))}
      </ol>
      <p className={styles.muted}>{th
        ? "ความลึกจากแบบจำลองที่สถานที่สำคัญที่เป็นไปได้จาก OpenStreetMap แต่ละแห่ง เรียงจากลึกที่สุด ยังไม่ได้ตรวจสอบในพื้นที่จริง"
        : "Reconstructed depth (model) at each OpenStreetMap candidate site, deepest first; not verified on the ground."}</p>
    </section>
  );
}

/** Sentinel-1 size check, rendered from `s1_anchor`; its scope is the whole image footprint, not the district. */
export function RadarCheck({ manifest, radarSpan, language }: { manifest: TimelineManifest; radarSpan: string; language: Language }) {
  const th = language === "th";
  const anchor = manifest.s1_anchor;
  const newlyDark = km(anchor.newly_dark_km2, 2);
  const modelSize = km(anchor.best_fit_model_km2, 2);
  const bestStage = anchor.best_fit_stage_m.toFixed(2);
  const passStage = anchor.reconstruction_stage_at_pass_m.toFixed(3);
  const iou = anchor.iou_at_best_fit.toFixed(2);
  const scope = anchor.scope ? localized(anchor.scope, language) : null;
  return (
    <div className={styles.anchor}>
      <p>{th
        ? `ตรวจสอบกับเรดาร์ (Sentinel-1, ${radarSpan}): พื้นที่ ${newlyDark} ตร.กม. เปลี่ยนเป็นลักษณะคล้ายน้ำใหม่ แบบจำลองให้ขนาดใกล้เคียงกันคือ ${modelSize} ตร.กม. ที่ระดับน้ำ ${bestStage} ม. (ระดับในการจำลองขณะดาวเทียมผ่านคือ ${passStage} ม.) ความสอดคล้องเชิงตำแหน่งต่ำ (IoU ${iou}) จึงใช้ตรวจสอบขนาดพื้นที่ได้ แต่ไม่ใช่ตำแหน่ง`
        : `Radar check (Sentinel-1, ${radarSpan}): ${newlyDark} km² turned newly water-like. The model reaches a similar size, ${modelSize} km², at a ${bestStage} m stage; the replay's stage at that pass is ${passStage} m. Spatial agreement is weak (IoU ${iou}), so this checks size, not location.`}</p>
      <p>
        {scope && <>{th ? "ขอบเขตการตรวจสอบ: " : "Scope: "}<span lang={scope.lang}>{scope.text}</span>{" "}</>}
        {th
          ? "การตรวจสอบนี้ครอบคลุมทั้งขอบเขตภาพ รวมถึงท่าขี้เหล็ก (เมียนมา) ซึ่งต่างจากตัวเลขผลกระทบระดับอำเภอด้านบน"
          : "Unlike the district impact figures above, this check covers the whole image footprint, including Tachileik (Myanmar)."}
      </p>
    </div>
  );
}

export function TimelineLegend({
  language, unmodelledRoads, unmodelledFacilities, waterMode = "depth", roadMode = "state", arrival = [], densityMax, shelters, cutoff = false,
}: {
  language: Language;
  unmodelledRoads: boolean;
  unmodelledFacilities: boolean;
  waterMode?: WaterMode;
  roadMode?: RoadMode;
  /** First-flooded hour classes (arrival mode). */
  arrival?: readonly HourClass[];
  /** Density cap (people/ha) of the residents raster, for the people and residents views. */
  densityMax?: number;
  /**
   * Shelter layers currently shown; `command` when a reported relief/command site is mapped, `unmodelled` when some
   * ineligible candidates lie outside the terrain model.
   */
  shelters?: { reported: boolean; candidates: boolean; ineligible: boolean; command?: boolean; unmodelled?: boolean };
  /** The "people cut off" heat is shown. */
  cutoff?: boolean;
}) {
  const th = language === "th";
  const channel = <li><i style={{ background: rgbaCss(CHANNEL_RGBA) }} />{th ? "ร่องน้ำ/แม่น้ำ (น้ำตลอดเวลา)" : "River channel (always water)"}</li>;
  const residentsView = (waterMode === "people" || waterMode === "residents") && densityMax !== undefined;
  const anyShelter = shelters && (shelters.reported || shelters.candidates || shelters.ineligible);
  return (
    <div className={styles.legend} aria-label={th ? "คำอธิบายสัญลักษณ์" : "Legend"} role="group">
      {residentsView ? (
        <DensityLegend maxPerHa={densityMax} language={language} wetOnly={waterMode === "people"} />
      ) : waterMode === "arrival" ? (
        <div>
          <strong>{th ? "เวลาที่เริ่มท่วม (แบบจำลอง เวลาท้องถิ่น)" : "First flooded (model, local time)"}</strong>
          <ul>
            {arrival.map((item) => <li key={item.from}><i style={{ background: rgbaCss(item.rgba) }} />{formatHourSpan(item.from, item.to, language)}</li>)}
            {arrival.length > 0 && (
              <li><i style={{ background: rgbaCss([...arrival[0].rgba.slice(0, 3), ARRIVAL_PENDING_ALPHA]) }} />{th ? "ยังไม่ท่วม ณ ช่วงเวลานี้ (จาง)" : "Not yet flooded at this moment (faded)"}</li>
            )}
            {channel}
          </ul>
        </div>
      ) : waterMode === "duration" ? (
        <div>
          <strong>{th ? "จำนวนชั่วโมงที่จมน้ำ 9–19 ก.ย. (แบบจำลอง)" : "Hours under water, 9–19 Sep (model)"}</strong>
          <ul>
            {DURATION_CLASSES.map((item) => <li key={item.min}><i style={{ background: rgbaCss(item.rgba) }} />{item.label[language]}</li>)}
            {channel}
          </ul>
        </div>
      ) : (
        <div>
          <strong>{th ? "ความลึกของน้ำ (แบบจำลอง)" : "Water depth (model)"}</strong>
          <ul>
            {DEPTH_CLASSES.map((item) => <li key={item.label}><i style={{ background: rgbaCss(item.rgba) }} />{item.label.replace(" m", th ? " ม." : " m")}</li>)}
            <li><i style={{ background: rgbaCss(CHANNEL_RGBA) }} />{th ? "ร่องน้ำ/แม่น้ำ" : "River channel"}</li>
          </ul>
        </div>
      )}
      <div>
        {roadMode === "hours" ? (
          <>
            <strong>{th ? "ถนน — ชั่วโมงที่สัญจรไม่ได้ ≥ 0.3 ม. (แบบจำลอง)" : "Roads — hours impassable ≥ 0.3 m (model)"}</strong>
            <ul>
              {ROAD_CUT_CLASSES.map((item) => <li key={item.min}><i className={styles.line} style={{ background: item.color }} />{item.label[language]}</li>)}
              {unmodelledRoads && <li><i className={styles.dash} style={{ borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
            </ul>
          </>
        ) : (
          <>
            <strong>{th ? "ถนน" : "Roads"}</strong>
            <ul>
              <li><i className={styles.line} style={{ background: ROAD_STYLES.dry.color }} />{th ? "แห้ง" : "Dry"}</li>
              <li><i className={styles.line} style={{ background: ROAD_STYLES.wet.color }} />{th ? "มีน้ำ < 0.3 ม." : "Wet < 0.3 m"}</li>
              <li><i className={styles.line} style={{ background: ROAD_STYLES.impassable.color }} />{th ? "สัญจรไม่ได้ ≥ 0.3 ม." : "Impassable ≥ 0.3 m"}</li>
              {unmodelledRoads && <li><i className={styles.dash} style={{ borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
            </ul>
          </>
        )}
      </div>
      <div>
        <strong>{th ? "สถานที่สำคัญที่เป็นไปได้ (ข้อมูล OSM)" : "Candidate facilities (OSM)"}</strong>
        <ul>
          <li><i className={styles.dot} style={{ background: "#fff", borderColor: "#0c2740" }} />{th ? "แห้ง" : "Dry"}</li>
          <li><i className={styles.dot} style={{ background: "#c62828", borderColor: "#fff" }} />{th ? "อยู่ในน้ำ" : "In water"}</li>
          {unmodelledFacilities && <li><i className={styles.dot} style={{ background: "transparent", borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
        </ul>
      </div>
      {anyShelter && (
        <div>
          <strong>{th ? "ที่พักพิง" : "Shelters"}</strong>
          <ul>
            {shelters.reported && <li><i className={styles.legendStar} aria-hidden="true">★</i>{th ? "มีรายงานว่าใช้ ก.ย. 2024" : "Reported in use, Sep 2024"}</li>}
            {shelters.reported && <li><i className={`${styles.legendStar} ${styles.legendStarFloods}`} aria-hidden="true">★</i>{th ? "มีรายงาน แต่แบบจำลองระบุว่าน้ำท่วมที่ระดับสูงสุด" : "Reported, but floods at the modelled peak"}</li>}
            {shelters.reported && shelters.command && <li><i className={styles.legendCommand} aria-hidden="true">◆</i>{th ? "ศูนย์บัญชาการและจุดช่วยเหลือ (ไม่ใช่ที่พักพิง)" : "Relief and command site (not a shelter)"}</li>}
            {shelters.candidates && <li><i className={styles.legendBadge} aria-hidden="true">1</i>{th ? "ลำดับในแผน (k แห่งแรก)" : "Plan rank (first k sites)"}</li>}
            {shelters.candidates && <li><i className={styles.dot} style={{ background: "#fff", borderColor: "#0b6e4f" }} />{th ? "เข้าเกณฑ์ ไม่อยู่ใน k แห่งแรก" : "Eligible, not in the first k"}</li>}
            {shelters.ineligible && <li><i className={styles.dot} style={{ background: "#a3acba", borderColor: "#6b7585" }} />{th ? "ไม่เข้าเกณฑ์ (เหตุผลอยู่ในป้ายและรายการสถานที่อื่น)" : "Not eligible (reasons in the popup and the other-candidates list)"}</li>}
            {shelters.ineligible && shelters.unmodelled && <li><i className={styles.dot} style={{ background: "transparent", borderColor: NOT_MODELLED_GREY, borderStyle: "dashed" }} />{th ? "ไม่ได้จำลอง (นอกแบบจำลองภูมิประเทศ)" : "Not modelled (outside the terrain model)"}</li>}
          </ul>
        </div>
      )}
      {cutoff && (
        <div>
          <strong>{th ? "ผู้ที่ถูกตัดขาดจากที่พักพิงที่แห้ง (สถานการณ์จำลอง)" : "People cut off from a dry shelter (scenario)"}</strong>
          <ul>
            <li><i className={styles.cutoffRamp} aria-hidden="true" />{th ? "น้อย → มาก (ถ่วงน้ำหนักตามประชากร)" : "Fewer → more people (population-weighted)"}</li>
          </ul>
        </div>
      )}
    </div>
  );
}

/** Assumed-stage curve: the `stage_anchors` polyline, the playhead, and dated image acquisitions (labelled in HTML). */
export function Hydrograph({ manifest, time, stage, observations, language }: {
  manifest: TimelineManifest;
  time: number;
  stage: number;
  observations: ObservationEntry[];
  language: Language;
}) {
  const th = language === "th";
  const width = 640;
  const height = 168;
  const margin = { left: 34, right: 12, top: 22, bottom: 24 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const anchors = manifest.stage_anchors;
  const maxStage = Math.max(...anchors.map((anchor) => anchor.stage_m));
  const yMax = Math.max(1, Math.ceil(maxStage));
  const x = (t: number) => margin.left + (t / TIMELINE_END_T) * plotW;
  const y = (s: number) => margin.top + plotH - (s / yMax) * plotH;
  const points: [number, number][] = [
    [0, stageAt(0, anchors)],
    ...anchors.filter((anchor) => anchor.t > 0 && anchor.t < TIMELINE_END_T).map((anchor) => [anchor.t, anchor.stage_m] as [number, number]),
    [TIMELINE_END_T, stageAt(TIMELINE_END_T, anchors)],
  ];
  const line = points.map(([t, s], index) => `${index ? "L" : "M"}${x(t).toFixed(1)} ${y(s).toFixed(1)}`).join(" ");
  const area = `${line} L${x(TIMELINE_END_T).toFixed(1)} ${y(0).toFixed(1)} L${x(0).toFixed(1)} ${y(0).toFixed(1)} Z`;
  const peak = anchors.reduce((best, anchor) => (anchor.stage_m > best.stage_m ? anchor : best), anchors[0]);
  const peakDate = formatShortDate(dateFromT(peak.t).toISOString(), language);
  const peakX = x(peak.t);
  const acquisitions = observations.filter((entry) => entry.at >= 0 && entry.at <= TIMELINE_END_T);
  const summary = th
    ? `กราฟระดับน้ำสมมุติ 9–19 ก.ย. สูงสุด ${peak.stage_m} ม. วันที่ ${peakDate} ขณะนี้ ${stage.toFixed(2)} ม.`
    : `Assumed stage curve for 9–19 Sep, peaking at ${peak.stage_m} m on ${peakDate}; now ${stage.toFixed(2)} m.`;
  return (
    <figure className={styles.hydrograph}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={summary}>
        {Array.from({ length: yMax + 1 }, (_, value) => (
          <g key={value}>
            <line x1={margin.left} x2={width - margin.right} y1={y(value)} y2={y(value)} className={styles.gridLine} />
            <text x={margin.left - 6} y={y(value) + 3.5} textAnchor="end" className={styles.axisText}>{value}</text>
          </g>
        ))}
        {manifest.days.map((day, index) => (
          <text key={day.date} x={x(index + 0.5)} y={height - 8} textAnchor="middle" className={styles.axisText}>{Number(day.date.slice(8))}</text>
        ))}
        <path d={area} className={styles.hydroArea} />
        <path d={line} className={styles.hydroLine} />
        {acquisitions.map((entry) => (
          <line key={entry.observation.id} x1={x(entry.at)} x2={x(entry.at)} y1={margin.top - 4} y2={y(0)} className={styles.obsLine} data-kind={entry.observation.kind} />
        ))}
        <circle cx={peakX} cy={y(peak.stage_m)} r={3.5} className={styles.peakDot} />
        <text x={peakX + 6} y={y(peak.stage_m) - 4} className={styles.peakText}>{th ? `สูงสุด ${peak.stage_m} ม. · ${peakDate}` : `Peak ${peak.stage_m} m · ${peakDate}`}</text>
        <line x1={x(time)} x2={x(time)} y1={margin.top - 8} y2={y(0)} className={styles.playhead} />
        <circle cx={x(time)} cy={y(stage)} r={4.5} className={styles.playDot} />
      </svg>
      <figcaption>
        <span>{manifest.hand.depth_factor
          ? th
            ? "ระดับน้ำสมมุติของลำน้ำหลักแม่น้ำสายที่สะพานแม่สาย (ม.) — เพื่อการอธิบาย ลำน้ำสาขาสูงขึ้น k × ระดับน้ำ"
            : "Assumed Sai main-stem stage at the Mae Sai bridges (m) — illustrative; tributaries rise k × stage"
          : th ? "ระดับน้ำในแม่น้ำเหนือร่องน้ำที่สมมุติ (ม.) — เพื่อการอธิบาย" : "Assumed river stage above channel (m) — illustrative"}</span>
        {acquisitions.length > 0 && (
          <ul className={styles.obsList} aria-label={th ? "เวลาที่บันทึกภาพ (เส้นประ)" : "Image acquisitions (dashed lines)"}>
            {acquisitions.map((entry) => (
              <li key={entry.observation.id} data-kind={entry.observation.kind}>
                <i aria-hidden="true" />{`${sensorName(entry.observation)} · ${formatLocalStamp(entry.observation.local, language)}`}
              </li>
            ))}
          </ul>
        )}
      </figcaption>
    </figure>
  );
}
