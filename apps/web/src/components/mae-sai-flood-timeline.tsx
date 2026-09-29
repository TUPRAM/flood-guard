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
  LayerGroup,
  Path,
  PathOptions,
  Renderer,
} from "leaflet";
import { memo, useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

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
  coverageComplete,
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
  hatchStripes,
  hourIndex,
  hourlyStages,
  inflateZlib,
  latestObservation,
  lowConfidenceCells,
  lutEquals,
  manifestRevision,
  namedRoadLengths,
  observationGap,
  paintDepth,
  paintLowConfidence,
  peopleKeys,
  phaseAt,
  projectToFrame,
  rankRouteGroups,
  referencesNotIngested,
  rgbaCss,
  ROAD_CUT_CLASSES,
  roadCut,
  roadCutClassIndex,
  roadCutGroups,
  roadState,
  stageAt,
  tFromDate,
  tFromLocalDate,
  thaiYear,
  TIMELINE_END_T,
  TIMELINE_MANIFEST_URL,
  viirsDayAt,
  waterCandidates,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type HourClass,
  type Language,
  type LineGeometry,
  type PngRaster,
  type PointGeometry,
  type Rainfall,
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
  type ViirsDaily,
  type ViirsDay,
} from "@/lib/flood-timeline";
import { GLOSSARY, GLOSSARY_ORDER, localizedText, plainManifestText, roadNameText } from "@/lib/flood-timeline-copy";
import {
  accessLevelIndex,
  accessLevelStep,
  accessLostSeries,
  accessSnapshot,
  buildCutoffRamp,
  candidateReasons,
  capacityFlag,
  clampPlanK,
  cutoffWeight,
  floodedHomeMask,
  nodeLostAccess,
  osmReference,
  parseAccessNodes,
  planSetId,
  planSites,
  REPORTED_SET_ID,
  reportedShelterCheck,
  reportedSiteRole,
  scopeTotals,
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
  type AccessScopeChoice,
  type LayerVisibility,
  type ReplayLinkState,
  type RoadMode,
  type ShelterSetChoice,
  type WaterMode,
} from "@/lib/flood-timeline-link";
import { useLanguage } from "@/lib/use-language";
import {
  AccessCard,
  candidateKindLabel,
  candidateTitle,
  capacityFlagText,
  capacityText,
  confidenceLabel,
  DensityLegend,
  evidenceLabel,
  ExternalChecks,
  formatPeople,
  freeboardText,
  indefiniteArticle,
  ineligibleReasonText,
  locationMethodLabel,
  occupancyText,
  OtherCandidatesCard,
  PeopleInWaterCard,
  ProvenanceNote,
  reportedCheckText,
  reportedName,
  reportedRoleText,
  ReportedSheltersCard,
  reportedTypeLabel,
  ShelterPlanCard,
  Term,
  ThemeEyebrow,
} from "./mae-sai-evacuation-panels";
import { RainChart, rainStationName, ViirsComparisonCard, ViirsLegend, viirsMomentText } from "./mae-sai-observed-panels";
import { DIAMOND_PATH, ReplayExportPanel, STAR_PATH, STAR_SLASH_PATH, type ReplayExportSource } from "./mae-sai-replay-export";
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
const VIIRS_CREDIT = "VIIRS flood: NOAA JPSS / GMU";
const RAIN_CREDIT = "Rain: HII ThaiWater";
/** The VIIRS maps are coarse (~375 m) observations drawn above the model water; slightly see-through so the model stays legible. */
const VIIRS_OPACITY = 0.9;
const NOT_MODELLED_GREY = "#7b8595";

interface ReplayData {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  facilities: GeoCollection<PointGeometry, FacilityProps>;
  tambons: GeoCollection<AreaGeometry, TambonProps>;
}
/**
 * HAND codes, optional depth-factor painter keys (`code | factor << 8`), the cells that can ever be wet, and (when the
 * manifest declares a low-confidence channel) the low-confidence cells among them with their hatch stripes.
 */
interface HandRaster {
  codes: Uint8Array;
  factorKeys: Uint16Array | null;
  candidates: Uint32Array;
  lowCells: Uint32Array | null;
  lowStripes: Uint8Array | null;
}
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
  /** Whether the low-confidence cells were re-coloured on the canvas. */
  lastLow: boolean;
  spares: Map<number, Uint32Array>;
}
interface RoadEntry { layer: Path; h: number | null; k: number; cutClass: number; styleKey: string }
interface FacilityEntry { layer: CircleMarker; props: FacilityProps; wet: boolean }
/** Resident nodes that have lost access, for one shelter set and stage level; `mask` limits them to the counted scope. */
interface CutoffFrame { nodes: AccessNodes; setIndex: number; levelIndex: number; mask: Uint8Array | null; scope: AccessScopeChoice }
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
  /** Remove the route highlight without moving the map (another selection took over). */
  clearRouteHighlight: () => void;
  setShelters: (view: ShelterView) => void;
  /** Centre a reported shelter or plan candidate and open its popup (its layer is shown if hidden). */
  focusShelter: (kind: "reported" | "candidate", id: string, instant: boolean) => void;
  /** Show the observed VIIRS daily map of `day` (null hides it); the image is swapped, never recoloured. */
  setViirs: (day: Pick<ViirsDay, "href" | "date"> | null) => void;
  /** Show or hide the rain-gauge markers. */
  setGauges: (visible: boolean) => void;
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
  shelter_candidate: ["Possible shelter site", "จุดพักพิงที่เป็นไปได้"],
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
/** Phones: the map legend starts collapsed there, since an open legend would cover much of a small map. */
const NARROW_QUERY = "(max-width: 760px)";
function subscribeNarrow(notify: () => void) {
  const query = window.matchMedia(NARROW_QUERY);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}
function useNarrowScreen(): boolean {
  return useSyncExternalStore(subscribeNarrow, () => window.matchMedia(NARROW_QUERY).matches, () => false);
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
  // The B channel is read as a low-confidence flag only when the manifest declares it.
  const grid = handGridFromRaster(raster, manifest.hand.depth_factor_channel, manifest.hand.low_confidence_channel);
  const maxStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  const candidates = waterCandidates(grid.codes, maxStage, manifest.hand.step_m);
  const lowCells = grid.lowConfidence ? lowConfidenceCells(grid.codes, grid.lowConfidence, candidates, manifest.hand.channel_code) : null;
  return {
    codes: grid.codes,
    factorKeys: grid.factors ? depthFactorKeys(grid.codes, grid.factors) : null,
    candidates,
    lowCells,
    lowStripes: lowCells ? hatchStripes(lowCells, grid.width) : null,
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

const STAR_ICON = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="${STAR_PATH}"/></svg>`;
/** Reported shelter that floods at the modelled peak: a pale star struck through, so it never reads as a usable one. */
const STAR_FLOODS_ICON = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false"><path d="${STAR_PATH}"/><path class="slash" d="${STAR_SLASH_PATH}"/></svg>`;
/** Relief and command site (reported, not a shelter): a diamond, so it never reads as a shelter star. */
const COMMAND_ICON = `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false"><path d="${DIAMOND_PATH}"/></svg>`;
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
const localized = localizedText;
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

/** The 42 OpenStreetMap key facilities start hidden (the layer toggle keeps them available) to keep the town readable. */
const DEFAULT_LAYERS: LayerVisibility = {
  tambons: true, roads: true, facilities: false, reported: true, candidates: true, ineligible: false, cutoff: false, viirs: false, gauges: false,
};
/** Water opacity while the imagery swipe is on, so the two images stay comparable under the model water. */
const COMPARE_WATER_OPACITY = 0.3;
/** Popups pan clear of the zoom control and the imagery notes (top) and of the attribution and legend (bottom). */
const POPUP_PAN = { autoPan: true, autoPanPaddingTopLeft: [56, 96] as [number, number], autoPanPaddingBottomRight: [24, 48] as [number, number] };
/** Rain gauge marker: a small drop, so it never reads as a shelter or facility symbol. */
const GAUGE_PATH = "M12 2.5C9 7 5.5 10.6 5.5 14.6a6.5 6.5 0 0 0 13 0C18.5 10.6 15 7 12 2.5z";
const GAUGE_ICON = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="${GAUGE_PATH}"/></svg>`;

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
    accessScope: "flooded",
  };
}

/**
 * An optical image taken after the flood began (the first clear view after it): its brown areas are read as mud
 * left by the floodwater. Null for pre-event images, radar and terrain.
 */
export function postEventOptical(
  id: string | null,
  observations: readonly Pick<TimelineObservation, "id" | "kind" | "local">[],
  phases: readonly Pick<TimelinePhase, "id" | "start">[],
): Pick<TimelineObservation, "id" | "kind" | "local"> | null {
  if (!id) return null;
  const observation = observations.find((item) => item.id === id);
  const onset = phases.find((phase) => phase.id !== "dry");
  if (!observation || observation.kind !== "optical" || !onset) return null;
  return tFromDate(observation.local) >= tFromLocalDate(onset.start) ? observation : null;
}

/** Play button label: the whole window and its length at the start, "Play from here" mid-way, "Replay" at the end. */
export function playLabel(time: number, playing: boolean, language: Language): string {
  const th = language === "th";
  if (playing) return th ? "หยุดชั่วคราว" : "Pause";
  if (time >= TIMELINE_END_T - 1e-6) return th ? "เล่นอีกครั้ง" : "Replay";
  if (time <= START_T + 1e-6) {
    const seconds = Math.round((TIMELINE_END_T - time) * SECONDS_PER_DAY);
    return th ? `เล่น 9 → 19 ก.ย. (${seconds} วินาที)` : `Play 9 → 19 Sep (${seconds} s)`;
  }
  return th ? "เล่นต่อจากตรงนี้" : "Play from here";
}

export function MaeSaiFloodTimeline() {
  const [language, setLanguage] = useLanguage("en");
  const t = useCallback((en: string, th: string) => (language === "th" ? th : en), [language]);
  const reducedMotion = useReducedMotion();
  const online = useOnline();
  const narrow = useNarrowScreen();

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
  const [showTambons, setShowTambons] = useState(DEFAULT_LAYERS.tambons);
  const [showRoads, setShowRoads] = useState(DEFAULT_LAYERS.roads);
  const [showFacilities, setShowFacilities] = useState(DEFAULT_LAYERS.facilities);
  const [showReported, setShowReported] = useState(DEFAULT_LAYERS.reported);
  const [showCandidates, setShowCandidates] = useState(DEFAULT_LAYERS.candidates);
  const [showIneligible, setShowIneligible] = useState(DEFAULT_LAYERS.ineligible);
  const [showCutoff, setShowCutoff] = useState(DEFAULT_LAYERS.cutoff);
  const [showViirs, setShowViirs] = useState(DEFAULT_LAYERS.viirs);
  const [showGauges, setShowGauges] = useState(DEFAULT_LAYERS.gauges);
  const [shelterSet, setShelterSet] = useState<ShelterSetChoice>("reported");
  const [accessScope, setAccessScope] = useState<AccessScopeChoice>("flooded");
  const [planK, setPlanK] = useState(1);
  const [layersOpen, setLayersOpen] = useState(false);
  /** The reader's own open/closed choice for the map legend; until then it is open except on phones. */
  const [legendChoice, setLegendChoice] = useState<boolean | null>(null);
  const legendOpen = legendChoice ?? !narrow;
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
  const layersButton = useRef<HTMLButtonElement | null>(null);
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
        setShowViirs(link.layers.viirs && Boolean(manifest.viirs_daily));
        setShowGauges(link.layers.gauges && Boolean(manifest.rainfall));
        setShelterSet(link.shelterSet);
        setAccessScope(link.accessScope);
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
  // Confidence chip of the cards built on the water model (impact, people in water, road cuts).
  const modelProvenance = useMemo(
    () => (manifest ? { confidence: manifest.confidence, reason: manifest.confidence_reason, timestamp: manifest.source_timestamp } : null),
    [manifest],
  );

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
    // Every named road with a cut, then the six most important unnamed street groups, each ranked by importance x hours.
    const ranked = rankRouteGroups(roadCutGroups(data.roads.features, roadCuts, Infinity), { unnamedLimit: 6 });
    const routeGroups = [...ranked.named, ...ranked.unnamed];
    const roadLengths = namedRoadLengths(data.roads.features);
    const peopleScale = Math.max(...m.days.flatMap((day) => Object.values(day.stats.tambon_people_in_water ?? {})), 1);
    const dayLabels = m.days.map((day) => String(Number(day.date.slice(8))));
    return {
      roadProps, facilityProps, names, tambonScale, observations, radar, hasUnmodelledRoads, hasUnmodelledFacilities,
      layersById, imageryIds, compareIds, defaultSides, opticalIds, timings, arrival, roadCuts, routeGroups, roadLengths, stages, peopleScale, dayLabels,
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

  // Access scenario: per-set cumulative histograms once per population scope, then O(1) per stage. The "flooded" scope
  // counts the nodes whose home is wet at the modelled peak, the same residents the ranked plan is built for.
  const nodes = accessNodes.status === "ready" ? accessNodes.value : null;
  const accessModel = useMemo(() => {
    const m = data?.manifest;
    const info = m?.access;
    if (!nodes || !m || !info) return null;
    const peakStage = m.shelters?.method.peak_stage_m ?? Math.max(...m.stage_anchors.map((anchor) => anchor.stage_m));
    const mask = floodedHomeMask(nodes, peakStage, m.hand.step_m, m.hand.channel_code, m.hand.never_code);
    const scope = (scopeMask: Uint8Array | null) => ({
      mask: scopeMask,
      summaries: summarizeAccessSets(nodes, info, scopeMask),
      tambonTotals: tambonResidents(nodes, info.tambons.length, scopeMask),
      totals: scopeTotals(nodes, scopeMask),
    });
    return { all: scope(null), flooded: scope(mask) };
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
  const scoped = accessModel ? accessModel[accessScope] : null;
  const selectedSummary = scoped && selectedSetIndex >= 0 ? scoped.summaries[selectedSetIndex] : null;
  const accessLevel = accessInfo ? accessLevelIndex(stage, accessInfo.levels) : 0;
  const snapshot = selectedSummary && accessInfo ? accessSnapshot(selectedSummary, stage, accessInfo.levels) : null;
  const lostSeries = useMemo(
    () => (selectedSummary && accessInfo && derived ? accessLostSeries(selectedSummary, derived.stages, accessInfo.levels) : null),
    [selectedSummary, accessInfo, derived],
  );
  const scopeMask = scoped?.mask ?? null;
  const cutoffFrame = useMemo<CutoffFrame | null>(
    () => (showCutoff && nodes && selectedSetIndex >= 0 ? { nodes, setIndex: selectedSetIndex, levelIndex: accessLevel, mask: scopeMask, scope: accessScope } : null),
    [showCutoff, nodes, selectedSetIndex, accessLevel, scopeMask, accessScope],
  );
  const viirsInfo = manifest?.viirs_daily ?? null;
  const rainfall = manifest?.rainfall ?? null;
  // At most nine days to scan; the day object is stable, so the map and the card update only when the day changes.
  const viirsDay = viirsInfo ? viirsDayAt(time, viirsInfo.days) : null;
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
      viirs: showViirs, gauges: showGauges,
    },
    shelterSet,
    planK,
    accessScope,
  }), [hour, imagery, waterMode, waterOpacity, roadMode, comparing, sides, language, showTambons, showRoads, showFacilities,
    showReported, showCandidates, showIneligible, showCutoff, showViirs, showGauges, shelterSet, planK, accessScope]);

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
      if (frameElement) {
        map.on("popupopen", () => { frameElement.dataset.popup = "open"; });
        map.on("popupclose", () => { delete frameElement.dataset.popup; });
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
        ["fg-imagery", 250], ["fg-compare-left", 251], ["fg-compare-right", 252], ["fg-water", 350], ["fg-viirs", 355], ["fg-cutoff", 360],
        ["fg-tambons", 380], ["fg-highlight", 390], ["fg-roads", 400], ["fg-facilities", 450], ["fg-gauges", 455], ["fg-shelters", 460],
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
          overlay, context, image, pixels: new Uint32Array(image.data.buffer), lastLut: null, lastKeys: null, lastCandidates: null, lastLow: false, spares: new Map(),
        };
      }
      /**
       * Paint through the shared LUT path: one key array, one LUT, one set of cells, buffers reused between paints.
       * The residents view paints inhabited cells instead of wet-able ones, so the canvas is cleared when the cell set changes.
       * In the depth and people views, wet low-confidence cells (filled or dead-flat low ground) are then washed out and hatched.
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
        const low = (frame.waterMode === "depth" || frame.waterMode === "people") && raster.lowCells && raster.lowStripes
          ? { cells: raster.lowCells, stripes: raster.lowStripes }
          : null;
        const spare = layer.spares.get(size) ?? new Uint32Array(size);
        const lut = build(spare);
        if (layer.lastKeys === keys && layer.lastCandidates === cells && layer.lastLow === (low !== null) && lutEquals(layer.lastLut, lut)) {
          layer.spares.set(size, spare);
          return;
        }
        if (layer.lastCandidates !== cells) layer.pixels.fill(0);
        paintDepth(keys, cells, lut, layer.pixels);
        if (low) paintLowConfidence(low.cells, low.stripes, layer.pixels, LITTLE_ENDIAN);
        layer.lastLow = low !== null;
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
        const key = `${frame.setIndex}:${Math.max(-1, Math.min(frame.levelIndex, 253))}:${frame.scope}`;
        if (cutoff.nodes === frame.nodes && cutoff.key === key) return;
        const { nodes: points, setIndex, levelIndex, mask } = frame;
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
          if ((mask && !mask[node]) || !nodeLostAccess(points.cutCodes[row + node], levelIndex)) continue;
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
      let highlight: LayerGroup | null = null;

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
          ? tr("relief and command site, Sep 2024 (not a shelter)", `ศูนย์บัญชาการและจุดช่วยเหลือ ก.ย. ${thaiYear(2024)} (ไม่ใช่ที่พักพิง)`)
          : tr("reported in use, Sep 2024", `มีรายงานว่าใช้ ก.ย. ${thaiYear(2024)}`);
        const occupancy = occupancyText(shelter);
        const lines: PopupLine[] = [
          { text: reportedName(shelter, lang), tone: "title" },
          { text: lang === "th" ? shelter.name_en : shelter.name_th, tone: "muted", lang: lang === "th" ? "en" : "th" },
          { text: `${reportedTypeLabel(shelter.type, lang)} · ${status} · ${evidenceLabel(shelter.evidence_strength, lang)}`, tone: "muted" },
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
      /** Short hover tooltip for a marker that also has a popup (its label is refreshed on language change). */
      const hoverTip = (layer: Layer, text: () => string, offsetY = -12) => {
        layer.bindTooltip(() => tooltipElement([[text(), "title"], [tr("Select for details", "เลือกเพื่อดูรายละเอียด"), "muted"]]), { direction: "top", offset: [0, offsetY] });
        tooltipLayers.push(layer);
      };
      for (const shelter of shelterData?.reported ?? []) {
        if (shelter.lat === null || shelter.lon === null) continue;
        const floods = reportedShelterCheck(shelter).status === "floods";
        const command = reportedSiteRole(shelter).role === "relief_command";
        const marker = L.marker([shelter.lat, shelter.lon], {
          pane: "fg-shelters",
          icon: command
            ? L.divIcon({ className: styles.commandIcon, html: COMMAND_ICON, iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -9] })
            : L.divIcon({ className: `${styles.starIcon}${floods ? ` ${styles.starIconFloods}` : ""}`, html: floods ? STAR_FLOODS_ICON : STAR_ICON, iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -10] }),
          keyboard: true,
          riseOnHover: true,
          zIndexOffset: 2000,
        });
        marker.bindPopup(() => reportedPopup(shelter), { maxWidth: 300, maxHeight: 300, className: styles.popupFrame, ...POPUP_PAN });
        popupLayers.push(marker);
        const markerTitle = () => `${command
          ? tr("Relief and command site (2024), not a shelter", `ศูนย์บัญชาการและจุดช่วยเหลือ ปี ${thaiYear(2024)} ไม่ใช่ที่พักพิง`)
          : floods
            ? tr("Reported shelter (2024) that floods at the modelled peak", `ที่พักพิงที่มีรายงาน ปี ${thaiYear(2024)} ซึ่งแบบจำลองระบุว่าน้ำท่วมที่ระดับสูงสุด`)
            : tr("Reported shelter (2024)", `ที่พักพิงที่มีรายงาน ปี ${thaiYear(2024)}`)}: ${reportedName(shelter, popupLanguage())}`;
        hoverTip(marker, markerTitle);
        titled.push({ element: () => marker.getElement(), title: markerTitle });
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
      // Candidates outside the terrain model (manifest m = false) have no model result; the build's placeholder flags for them are not shown.
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
          lines.push({ text: tr(`Assigned ≈ ${formatPeople(site.load)} residents in ${indefiniteArticle(k)} ${k}-site plan`, `รับผู้อพยพ ≈ ${formatPeople(site.load)} คนในแผน ${k} แห่ง`) });
          const flag = capacityFlag(site);
          if (flag) lines.push({ text: capacityFlagText(site, lang), tone: "alert" });
          else if (site.shortfall && site.capacity !== null) {
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
        const planned = new Map(planSites(shelterData, k).map((site) => [site.candidate.id, site]));
        for (const candidate of shelterData.candidates) {
          const site = planned.get(candidate.id);
          let layer: Marker | CircleMarker;
          if (site) {
            // Plan badges sit above the reported stars and every other marker; a "!" corner flags an unknown or far-too-small capacity.
            const rank = site.rank;
            const flag = capacityFlag(site);
            const marker = L.marker([candidate.lat, candidate.lon], {
              pane: "fg-shelters",
              icon: L.divIcon({
                className: `${styles.planBadgeIcon}${flag ? ` ${styles.planBadgeFlag}` : ""}`,
                html: `<span>${rank}</span>${flag ? '<b aria-hidden="true">!</b>' : ""}`,
                iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -11],
              }),
              keyboard: true,
              riseOnHover: true,
              zIndexOffset: 3000 - rank,
            });
            const markerTitle = () => `${tr("Plan site", "ที่พักพิงในแผน")} ${rank}: ${candidateTitle(candidate, popupLanguage())}${flag ? ` · ${capacityFlagText(site, popupLanguage())}` : ""}`;
            candidateTitles.push({ element: () => marker.getElement(), title: markerTitle });
            hoverTip(marker, markerTitle);
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
            hoverTip(layer, () => `${eligible ? tr("Eligible shelter candidate", "สถานที่ที่เข้าเกณฑ์") : tr("Candidate, not eligible", "สถานที่ที่ไม่เข้าเกณฑ์")}: ${candidateTitle(candidate, popupLanguage())}`, -6);
          }
          layer.bindPopup(() => candidatePopup(candidate), { maxWidth: 290, className: styles.popupFrame, ...POPUP_PAN });
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
          // The hover tooltip shows the name; the label keeps it for screen readers without a second native tooltip.
          element.removeAttribute("title");
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

      // --- Observed VIIRS daily flood map: one pre-coloured ~375 m image on the replay bounds, swapped per day and drawn
      // with pixelated rendering so its coarse pixels stay visible. All days are small and preloaded on first use.
      const viirsDays = m.viirs_daily?.days ?? [];
      let viirsOverlay: ImageOverlay | null = null;
      let viirsShown: string | null = null;
      let viirsPreloaded = false;
      const preloadViirs = () => {
        if (viirsPreloaded) return;
        viirsPreloaded = true;
        for (const day of viirsDays) {
          const image = new Image();
          image.decoding = "async";
          image.src = day.href;
        }
      };

      // --- Rain gauges (observed forcing): small drops with a popup of each station's record.
      const gaugeGroup = L.layerGroup();
      const rain: Rainfall | null = m.rainfall ?? null;
      for (const station of rain?.stations ?? []) {
        const marker = L.marker([station.lat, station.lon], {
          pane: "fg-gauges",
          icon: L.divIcon({ className: styles.gaugeIcon, html: GAUGE_ICON, iconSize: [20, 20], iconAnchor: [10, 16], popupAnchor: [0, -14] }),
          keyboard: true,
          riseOnHover: true,
          attribution: RAIN_CREDIT,
        });
        marker.bindPopup(() => {
          const lang = popupLanguage();
          const lines: PopupLine[] = [
            { text: rainStationName(station, lang), tone: "title" },
            { text: rainStationName(station, lang === "th" ? "en" : "th"), tone: "muted", lang: lang === "th" ? "en" : "th" },
            { text: `${tr("Rain gauge", "สถานีวัดฝน")} ${station.code} · ${tr("observed hourly rain (forcing), not flooding", "ฝนรายชั่วโมงที่ตรวจวัดได้ (ปัจจัยที่ทำให้เกิดน้ำ) ไม่ใช่น้ำท่วม")}` },
            { text: tr(`9–19 Sep total: ${station.total_mm.toFixed(1)} mm`, `รวม 9–19 ก.ย.: ${station.total_mm.toFixed(1)} มม.`) },
            { text: tr(`Wettest hour: ${station.max_hour_mm.toFixed(1)} mm`, `ชั่วโมงที่ฝนหนักที่สุด: ${station.max_hour_mm.toFixed(1)} มม.`) },
            { text: tr(`Missing hours: ${station.missing_hours}`, `ชั่วโมงที่ไม่มีข้อมูล: ${station.missing_hours}`), tone: "muted" },
            { text: `${tr("Source", "แหล่งข้อมูล")}: `, value: { text: `${rain!.source} (${rain!.licence})`, lang: "en" }, tone: "muted" },
          ];
          return popupElement(lines, [{ href: rain!.source_url, text: rain!.source_url }]);
        }, { maxWidth: 280, className: styles.popupFrame, ...POPUP_PAN });
        popupLayers.push(marker);
        const gaugeTitle = () => `${tr("Rain gauge (observed)", "สถานีวัดฝน (ตรวจวัดจริง)")}: ${station.code} ${rainStationName(station, popupLanguage())}`;
        hoverTip(marker, gaugeTitle);
        titled.push({ element: () => marker.getElement(), title: gaugeTitle });
        gaugeGroup.addLayer(marker);
      }

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
          // A cyan halo with a white core under the road lines: neither colour is used by any road state.
          highlight = L.layerGroup([
            L.polyline(lines, { pane: "fg-highlight", color: "#00b8d9", weight: 14, opacity: 0.55, lineCap: "round", interactive: false }),
            L.polyline(lines, { pane: "fg-highlight", color: "#ffffff", weight: 7, opacity: 0.95, lineCap: "round", interactive: false }),
          ]).addTo(map);
          map.fitBounds(L.latLngBounds(group.bounds), { padding: [36, 36], maxZoom: 16, animate: !instant });
        },
        clearRouteHighlight() {
          highlight?.remove();
          highlight = null;
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
          highlight?.remove();
          highlight = null;
          const group = kind === "reported" ? reportedGroup : [planGroup, eligibleGroup, ineligibleGroup].find((item) => item.hasLayer(layer));
          if (group) setGroup(group, true);
          map.setView(layer.getLatLng(), Math.max(map.getZoom(), 15), { animate: !instant });
          layer.openPopup();
          refreshTitles();
        },
        setViirs(day) {
          const href = day?.href ?? null;
          if (href === viirsShown) return;
          viirsShown = href;
          if (!href) {
            viirsOverlay?.remove();
            return;
          }
          preloadViirs();
          if (!viirsOverlay) {
            viirsOverlay = L.imageOverlay(href, bounds, {
              pane: "fg-viirs",
              opacity: VIIRS_OPACITY,
              className: styles.viirsLayer,
              alt: "",
              attribution: VIIRS_CREDIT,
            });
          } else {
            viirsOverlay.setUrl(href);
          }
          if (!map.hasLayer(viirsOverlay)) viirsOverlay.addTo(map);
        },
        setGauges(visible) {
          setGroup(gaugeGroup, visible);
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

  // While the imagery swipe is on, the model water is drawn faintly so the two images stay comparable.
  const shownWaterOpacity = comparing ? Math.min(waterOpacity, COMPARE_WATER_OPACITY) : waterOpacity;
  useEffect(() => {
    if (mapReady) controllerRef.current?.setWaterOpacity(shownWaterOpacity);
  }, [mapReady, shownWaterOpacity]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.setVisibility(showTambons, showRoads, showFacilities);
  }, [mapReady, showTambons, showRoads, showFacilities]);

  // The VIIRS image changes at most once per replay day; the effect runs only when the day on show changes.
  const viirsOnMap = showViirs ? viirsDay : null;
  useEffect(() => {
    if (mapReady) controllerRef.current?.setViirs(viirsOnMap);
  }, [mapReady, viirsOnMap]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.setGauges(showGauges);
  }, [mapReady, showGauges]);

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
    // Showing a shelter replaces any route highlight (the map clears it too).
    setFocusedRoute(null);
    setShowReported(true);
    controllerRef.current?.focusShelter("reported", id, reducedMotion);
    mapElement.current?.scrollIntoView({ block: "nearest", behavior: reducedMotion ? "auto" : "smooth" });
  }, [reducedMotion]);
  const showCandidateOnMap = useCallback((id: string) => {
    const candidate = shelterInfo?.candidates.find((item) => item.id === id);
    setFocusedRoute(null);
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
    () => (data && derived && hand
      ? { manifest: data.manifest, roads: data.roads, roadProps: derived.roadProps, facilityProps: derived.facilityProps, tambons: data.tambons, hand }
      : null),
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
      <p className={styles.eyebrow}>{t("CASE REPLAY · MAE SAI · SEPTEMBER 2024", `ย้อนดูเหตุการณ์ · แม่สาย · กันยายน ${thaiYear(2024)}`)}</p>
      <h1 id="mae-sai-replay-title">{t("Mae Sai flood, September 2024 — day by day", `น้ำท่วมแม่สาย กันยายน ${thaiYear(2024)} — ไล่เรียงรายวัน`)}</h1>
      <p className={styles.lead}>{t(
        "Replay 9–19 September hour by hour: dated satellite images under a terrain-model reconstruction of the water and its modelled impacts, with daily satellite flood maps and rain gauges where they observed something.",
        "ย้อนดูวันที่ 9–19 กันยายนทีละชั่วโมง: ภาพดาวเทียมที่ระบุวันที่ใต้ขอบเขตน้ำที่จำลองจากแบบจำลองภูมิประเทศและผลกระทบตามแบบจำลอง พร้อมแผนที่น้ำท่วมรายวันจากดาวเทียมและสถานีวัดฝนในช่วงที่สังเกตได้",
      )}</p>
      <div className={styles.heroNotes}>
        <p className={styles.banner} role="note">
          <strong>{t("Historical reconstruction for preparedness learning — not real-time, not an official warning.", "การจำลองย้อนหลังเพื่อการเรียนรู้ด้านการเตรียมพร้อม — ไม่ใช่ข้อมูลเรียลไทม์ และไม่ใช่คำเตือนอย่างเป็นทางการ")}</strong>
        </p>
        <HowToRead manifest={manifest} language={lang} />
      </div>
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
  const stageText = `${t("assumed stage", "ระดับน้ำสมมุติ")} ${stage.toFixed(2)}\u00a0${unit.m}`;
  const valueText = `${moment} · ${phaseLabel} · ${stageText}`;
  const observationById = new Map(derived?.observations.map((entry) => [entry.observation.id, entry]) ?? []);
  const radarFirst = derived?.radar[0];
  const radarLast = derived?.radar.at(-1);
  const radarSpan = radarFirst && radarLast
    ? `${formatShortDate(radarFirst.observation.local, lang)} → ${formatLocalStamp(radarLast.observation.local, lang)}`
    : "";
  const layerOf = (id: string | null) => (id ? derived?.layersById.get(id) : undefined);

  const imageryLabel = (id: string): string => {
    if (id === "auto") return t("Auto — latest optical image at this replay hour", "อัตโนมัติ — ภาพเชิงแสงล่าสุด ณ ชั่วโมงนี้ของการย้อนดู");
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

  // The image under the water at the playhead; it changes as the replay passes each acquisition.
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
  // The first clear optical image after the flood began shows the mud the water left: say so wherever it is on screen.
  const postEvent = manifest
    ? (comparing ? [compareLeft, compareRight] : [activeImagery]).map((id) => postEventOptical(id, manifest.observations, manifest.phases)).find(Boolean) ?? null
    : null;
  const mudText = postEvent
    ? t(
      `First clear satellite view after the flood (${formatShortDate(postEvent.local, "en")}): brown = mud left by floodwater`,
      `ภาพดาวเทียมที่ชัดเจนภาพแรกหลังน้ำท่วม (${formatShortDate(postEvent.local, "th")}): สีน้ำตาล = โคลนที่น้ำท่วมทิ้งไว้`,
    )
    : "";
  const mudCue = mudText ? `${mudText} ${t("(observed)", "(การสังเกตการณ์)")}` : "";

  const gapText = gap
    ? t(
      `These inputs contain no high-resolution satellite image between ${formatLocalStamp(gap.before.local, "en")} and ${formatLocalStamp(gap.after.local, "en")}. The water shown at this replay hour is the model only.${viirsInfo ? " Coarse VIIRS daily flood maps (375 m) are the observed view in this window, where cloud allows (see VIIRS below)." : ""}`,
      `ข้อมูลชุดนี้ไม่มีภาพดาวเทียมความละเอียดสูงระหว่าง ${formatLocalStamp(gap.before.local, "th")} ถึง ${formatLocalStamp(gap.after.local, "th")} น้ำที่เห็น ณ ชั่วโมงนี้ของการย้อนดูมาจากแบบจำลองเท่านั้น${viirsInfo ? " ในช่วงนี้มีเพียงแผนที่น้ำท่วมรายวัน VIIRS แบบหยาบ (375 ม.) เป็นการสังเกตการณ์ เท่าที่เมฆไม่บัง (ดู VIIRS ด้านล่าง)" : ""}`,
    )
    : "";
  const viirsNote = showViirs && viirsInfo
    ? viirsDay
      ? t(
        `VIIRS daily flood map (observed, 375 m) · ${formatLocalStamp(viirsDay.nominal_local_time, "en")} nominal · ${Math.round(viirsDay.cloud_share * 100)}% cloud`,
        `แผนที่น้ำท่วมรายวัน VIIRS (สังเกตการณ์ 375 ม.) · ${formatLocalStamp(viirsDay.nominal_local_time, "th")} โดยประมาณ · เมฆ ${Math.round(viirsDay.cloud_share * 100)}%`,
      )
      : t("VIIRS: no daily map at this moment", "VIIRS: ไม่มีแผนที่รายวันในช่วงเวลานี้")
    : "";
  const compareNote = comparing
    ? t(
      `Swipe comparison: the water is drawn at ${Math.round(shownWaterOpacity * 100)}% so both images show. It is the model at the selected hour, not part of either image.`,
      `การเปรียบเทียบภาพ: แสดงน้ำที่ความทึบ ${Math.round(shownWaterOpacity * 100)}% เพื่อให้เห็นภาพทั้งสองฝั่ง น้ำนี้เป็นแบบจำลอง ณ ชั่วโมงที่เลือก ไม่ได้อยู่ในภาพใดภาพหนึ่ง`,
    )
    : "";
  const isLowConfidence = manifest?.confidence.toLowerCase() === "low";
  // Low-confidence water is decoded (and described) only when the manifest declares its raster channel.
  const lowConfidence = manifest?.hand.low_confidence_channel ? manifest.hand : null;
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
  const legendWaterMode = residentsMode && !peopleRaster ? "depth" : waterMode;
  const residentsStatus = residentsMode && manifest?.population
    ? population.status === "error"
      ? t("The residents layer could not be loaded; the map shows water depth instead.", "โหลดชั้นข้อมูลผู้อยู่อาศัยไม่สำเร็จ แผนที่จึงแสดงความลึกของน้ำแทน")
      : !peopleRaster && hand ? t("Preparing the residents layer…", "กำลังเตรียมชั้นข้อมูลผู้อยู่อาศัย…") : ""
    : "";
  const roadModes: [RoadMode, string][] = [
    ["state", t("State at this replay hour", "สถานะ ณ ชั่วโมงนี้ของการย้อนดู")],
    ["hours", t("Hours cut", "ชั่วโมงที่ถูกตัดขาด")],
  ];
  const updateSide = (index: 0 | 1, value: string) => {
    const base = sides ?? [value, value];
    setCompareSides(index === 0 ? [value, base[1]] : [base[0], value]);
  };
  const shelterLegend = shelterInfo ? {
    reported: showReported, candidates: showCandidates, ineligible: showIneligible,
    command: shelterInfo.reported.some((shelter) => shelter.lat !== null && reportedSiteRole(shelter).role === "relief_command"),
    unmodelled: unmodelledCandidates.size > 0,
  } : undefined;
  const legendProps = {
    language: lang,
    unmodelledRoads: !!derived?.hasUnmodelledRoads,
    unmodelledFacilities: !!derived?.hasUnmodelledFacilities,
    waterMode: legendWaterMode,
    roadMode,
    arrival: derived?.arrival ?? [],
    densityMax: manifest?.population?.max_per_ha,
    shelters: shelterLegend,
    cutoff: showCutoff && !!accessInfo,
    viirs: showViirs ? viirsInfo : null,
    gauges: showGauges && !!rainfall,
    facilities: showFacilities,
    lowConfidence: !!lowConfidence && !!hand?.lowCells && (legendWaterMode === "depth" || legendWaterMode === "people"),
  };
  const chronology = manifest?.sources.find((source) => source.id === "chronology") ?? null;
  // One-line "this moment" summary under the readout; phones show it because the story card sits far below the map.
  const momentLine = manifest && stats && phase
    ? `${phaseLabel} · ${t("Model", "แบบจำลอง")}: ${km(stats.flooded_km2)}\u00a0${unit.km2} ${t("flooded", "น้ำท่วม")}${stats.people_in_water !== undefined ? ` · ${formatPeople(stats.people_in_water)} ${t("residents in flood water", "คนในพื้นที่น้ำท่วม")}` : ""}`
    : "";
  const layerToggle = (checked: boolean, onChange: (value: boolean) => void, label: string, swatch: ReactNode) => (
    <label>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span className={styles.toggleSwatch} aria-hidden="true">{swatch}</span>
      <span>{label}</span>
    </label>
  );
  const closeLayers = () => {
    setLayersOpen(false);
    layersButton.current?.focus();
  };

  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
      {header}
      <div className={styles.container}>
        {intro}
        <div className={styles.layout}>
          <section className={styles.stage} aria-label={t("Flood replay map and timeline", "แผนที่และเส้นเวลาการย้อนดูน้ำท่วม")}>
            <div className={styles.stageBar}>
              <button type="button" className={styles.play} onClick={togglePlay} aria-keyshortcuts="Space" disabled={!manifest || !derived} data-testid="play-button">
                <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>
                {playLabel(time, playing, lang)}
              </button>
              <div className={styles.readout} data-testid="replay-readout">
                <strong>{manifest ? moment : t("Loading the replay…", "กำลังโหลดการย้อนดูเหตุการณ์…")}</strong>
                <span>{manifest ? `${phaseLabel} · ${stageText}` : "\u00a0"}</span>
              </div>
              <button ref={layersButton} type="button" className={styles.layersButton} aria-expanded={layersOpen} aria-controls="mae-sai-map-layers"
                onClick={() => setLayersOpen((value) => !value)} disabled={!derived}>
                <span aria-hidden="true">≡</span>{t("Map layers", "ชั้นแผนที่")}
              </button>
              <p className={styles.momentLine} data-testid="moment-line">{momentLine || "\u00a0"}</p>
            </div>

            <div className={styles.mapFrame}>
              <div ref={mapElement} className={styles.map} role="region" aria-label={t("Map of Mae Sai with imagery, reconstructed water, roads, shelters and key facilities", "แผนที่แม่สายพร้อมภาพดาวเทียม น้ำที่จำลอง ถนน ที่พักพิง และสถานที่สำคัญ")} />
              {manifest && (
                <div className={styles.mapNotes} data-compare={comparing || undefined}>
                  {!comparing && <p className={styles.caption} data-testid="imagery-caption">{caption}</p>}
                  {mudCue && <p className={styles.mudCue} data-testid="mud-cue">{mudCue}</p>}
                  {compareNote && <p className={styles.compareNote} data-testid="compare-note">{compareNote}</p>}
                  {viirsNote && <p className={styles.viirsNote} data-testid="viirs-note">{viirsNote}</p>}
                </div>
              )}
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
              {mapReady && focusedRoute && (
                <button type="button" className={styles.clearSelection} onClick={resetRouteFocus}>
                  <span aria-hidden="true">✕</span> {t("Clear route selection", "ล้างเส้นทางที่เลือก")}
                </button>
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
              <details className={styles.mapLegend} open={legendOpen} onToggle={(event) => setLegendChoice(event.currentTarget.open)} data-testid="map-legend">
                <summary>{t("Legend", "คำอธิบายสัญลักษณ์")}</summary>
                <TimelineLegend {...legendProps} part="overlay" />
                <details className={styles.symbolKey}>
                  <summary>{t("Map symbols", "สัญลักษณ์บนแผนที่")}</summary>
                  <TimelineLegend {...legendProps} part="symbols" />
                </details>
              </details>
              <div id="mae-sai-map-layers" className={styles.layersPanel} hidden={!layersOpen} role="group" aria-label={t("Map layers", "ชั้นแผนที่")}
                onKeyDown={(event) => {
                  if (event.key !== "Escape") return;
                  event.stopPropagation();
                  closeLayers();
                }}>
                <div className={styles.layersHead}>
                  <strong>{t("Map layers", "ชั้นแผนที่")}</strong>
                  <button type="button" className={styles.linkButton} onClick={closeLayers}>{t("Close", "ปิด")}</button>
                </div>
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
                  <span>{t("Water opacity", "ความทึบของน้ำ")} · {Math.round(waterOpacity * 100)}%{comparing ? t(` (${Math.round(shownWaterOpacity * 100)}% while comparing)`, ` (${Math.round(shownWaterOpacity * 100)}% ขณะเปรียบเทียบ)`) : ""}</span>
                  <input type="range" min={0} max={1} step={0.05} value={waterOpacity} onChange={(event) => setWaterOpacity(Number(event.target.value))} />
                </label>
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
                  <legend>{t("Show on the map", "แสดงบนแผนที่")}</legend>
                  {layerToggle(showTambons, setShowTambons, t("Subdistricts", "ขอบเขตตำบล"), <i className={styles.dash} style={{ borderColor: "#1c3d6e" }} />)}
                  {layerToggle(showRoads, setShowRoads, t("Roads", "ถนน"), <i className={styles.line} style={{ background: ROAD_STYLES.impassable.color }} />)}
                  {layerToggle(showFacilities, setShowFacilities, t("Key facilities (OSM)", "สถานที่สำคัญ (ข้อมูล OSM)"), <i className={styles.dot} style={{ background: "#fff", borderColor: "#0c2740" }} />)}
                  {shelterInfo && (
                    <>
                      {layerToggle(showReported, setShowReported, t("Shelters reported in 2024", `ที่พักพิงที่มีรายงานปี ${thaiYear(2024)}`), <i className={styles.legendStar}>★</i>)}
                      {layerToggle(showCandidates, setShowCandidates, t("Ranked plan sites", "สถานที่ในแผนจัดอันดับ"), <i className={styles.legendBadge}>1</i>)}
                      {layerToggle(showIneligible, setShowIneligible, t("Ineligible candidates", "สถานที่ที่ไม่เข้าเกณฑ์"), <i className={styles.dot} style={{ background: "#a3acba", borderColor: "#6b7585" }} />)}
                    </>
                  )}
                  {accessInfo && layerToggle(showCutoff, setShowCutoff, t("People cut off (scenario)", "ผู้ที่ถูกตัดขาด (สถานการณ์จำลอง)"), <i className={styles.cutoffRamp} />)}
                  {viirsInfo && layerToggle(showViirs, setShowViirs, t("VIIRS daily flood map (375 m, observed)", "แผนที่น้ำท่วมรายวัน VIIRS (375 ม. สังเกตการณ์)"), <i style={{ background: rgbaCss([118, 42, 131, 245]) }} />)}
                  {rainfall && layerToggle(showGauges, setShowGauges, t("Rain gauges (observed)", "สถานีวัดฝน (ตรวจวัดจริง)"), <i className={styles.legendGauge}><svg viewBox="0 0 24 24" width="14" height="14" focusable="false"><path d={GAUGE_PATH} /></svg></i>)}
                </fieldset>
              </div>
            </div>

            <div className={styles.dock}>
              {manifest && derived && (
                <>
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
                  <p className={styles.hint} data-testid="keyboard-hint">{t(
                    "Keyboard: Space plays or pauses · arrow keys move one hour · Shift + arrows or the day buttons move one day",
                    "แป้นพิมพ์: แป้นเว้นวรรคเล่นหรือหยุด · แป้นลูกศรเลื่อนทีละชั่วโมง · ปุ่มวันที่เลื่อนทีละวัน",
                  )}</p>
                </>
              )}
            </div>
          </section>

          <aside className={styles.panel} aria-label={t("Impact at this moment", "ผลกระทบ ณ ช่วงเวลานี้")}>
            {!manifest || !stats || !derived || !phase ? (
              <p className={styles.muted} role="status">{t("Loading figures…", "กำลังโหลดตัวเลข…")}</p>
            ) : (
              <>
                <section className={styles.card} data-testid="this-moment" aria-labelledby="mae-sai-moment-title">
                  <p className={styles.eyebrow}>{t("THIS MOMENT", "ช่วงเวลานี้")}</p>
                  <h2 id="mae-sai-moment-title" className={styles.moment}>{moment}</h2>
                  <span className={styles.phaseBadge} style={{ background: PHASE_COLOURS[phase.id] ?? "#cbd5e1", color: phase.id === "peak" ? "#fff" : PHASE_TEXT_DARK }}>{phase.label[lang]}</span>
                  <p data-testid="reported-narrative">
                    <strong className={styles.tagReported}>{t("Reported:", "รายงาน:")}</strong> {phase.summary[lang]}
                    {chronology && <span className={styles.cite}> {t("Source", "ที่มา")}: <Localized text={chronology.attribution} language={lang} /> (<Localized text={chronology.timestamp} language={lang} />)</span>}
                  </p>
                  {mudText && (
                    <p className={styles.cue} data-testid="mud-cue-card"><strong className={styles.tagObserved}>{t("Observed:", "การสังเกตการณ์:")}</strong> {mudText}.</p>
                  )}
                  <p className={styles.muted}>
                    <strong className={styles.tagModel}>{t("Model:", "แบบจำลอง:")}</strong>{" "}
                    {manifest.hand.depth_factor
                      ? <>{t("assumed Sai main-stem ", "ระดับน้ำสมมุติของลำน้ำหลักแม่น้ำสาย ")}<Term id="stage" language={lang}>{t("stage", "(ระดับน้ำ)")}</Term>{t(
                        ` ${stage.toFixed(2)}\u00a0m at the Mae Sai bridges (illustrative, not a gauge reading); tributaries rise to a fraction of this level.`,
                        ` ${stage.toFixed(2)}\u00a0ม. ที่สะพานแม่สาย (เพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ) ลำน้ำสาขาสูงขึ้นเพียงบางส่วนของระดับนี้`,
                      )}</>
                      : <>{t("assumed river ", "ระดับน้ำสมมุติ ")}<Term id="stage" language={lang}>{t("stage", "(ระดับน้ำ)")}</Term>{t(` ${stage.toFixed(2)}\u00a0m above the mapped channel (illustrative, not a gauge reading).`, ` ${stage.toFixed(2)}\u00a0ม. เหนือร่องน้ำ (เพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ)`)}</>}
                  </p>
                </section>

                <section className={styles.card} aria-labelledby="mae-sai-stage-title">
                  <h2 id="mae-sai-stage-title">{t("River stage (assumed) and rain (observed)", "ระดับน้ำ (สมมุติ) และฝน (ตรวจวัดจริง)")}</h2>
                  <Hydrograph manifest={manifest} time={time} stage={stage} observations={derived.observations} language={lang} />
                  {rainfall && <RainChart rainfall={rainfall} time={time} dayLabels={derived.dayLabels} language={lang} />}
                </section>

                <ImpactCard manifest={manifest} stats={stats} derived={derived} language={lang} />

                {manifest.population && stats.people_in_water !== undefined && (
                  <PeopleInWaterCard population={manifest.population} stats={stats} names={derived.names} scale={derived.peopleScale} language={lang}
                    accessResidents={accessInfo ? accessModel?.all.totals.population ?? accessInfo.totals.population : undefined}
                    demandPeople={accessInfo ? shelterInfo?.demand_people : undefined} provenance={modelProvenance ?? undefined} />
                )}

                {accessInfo && shelterInfo && (
                  <AccessCard
                    access={accessInfo}
                    shelters={shelterInfo}
                    snapshot={snapshot}
                    series={lostSeries}
                    time={time}
                    names={derived.names}
                    tambonTotals={scoped?.tambonTotals ?? null}
                    shelterSet={shelterSet}
                    planK={planK}
                    onShelterSet={setShelterSet}
                    onPlanK={choosePlanK}
                    showCutoff={showCutoff}
                    onShowCutoff={setShowCutoff}
                    scope={accessScope}
                    onScope={setAccessScope}
                    scopeTotals={scoped?.totals ?? null}
                    allResidents={accessModel?.all.totals.population ?? accessInfo.totals.population}
                    floodedResidents={accessModel?.flooded.totals.population ?? shelterInfo.demand_people}
                    language={lang}
                    status={accessNodes.status === "error" || (accessModel && selectedSetIndex < 0) ? "error" : accessModel ? "ready" : "loading"}
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

                <RouteCutsCard groups={derived.routeGroups} names={derived.names} language={lang} focused={focusedRoute} onFocus={focusRoute} onReset={resetRouteFocus}
                  roadLengths={derived.roadLengths} provenance={modelProvenance ?? undefined} />

                <WetFacilitiesCard facilities={derived.facilityProps} stage={stage} language={lang} />

                <section className={styles.card} aria-labelledby="mae-sai-evidence-title">
                  <h2 id="mae-sai-evidence-title">{t("Evidence for this moment", "หลักฐานของช่วงเวลานี้")}</h2>
                  <dl className={styles.evidence}>
                    <div><dt>{t("Imagery", "ภาพ")}</dt><dd>{caption}{mudCue ? ` · ${mudCue}` : ""}</dd></div>
                    {gap && <div><dt>{t("Image gap", "ช่วงไม่มีภาพ")}</dt><dd>{gapText}</dd></div>}
                    <div><dt>{t("Water", "น้ำ")}</dt><dd>{t("Model reconstruction from terrain (", "การจำลองจากภูมิประเทศ (")}<Term id="hand" language={lang}>HAND</Term>{t(", height above nearest drainage) at the assumed stage — not an observation.", " ความสูงเหนือร่องน้ำที่ใกล้ที่สุด) ที่ระดับน้ำสมมุติ — ไม่ใช่การสังเกตการณ์จริง")}</dd></div>
                    <LowConfidenceEvidence hand={manifest.hand} language={lang} />
                    {viirsInfo && (
                      <div data-testid="viirs-evidence"><dt>{t("VIIRS (observed)", "VIIRS (สังเกตการณ์)")}</dt><dd>{viirsMomentText(viirsDay, viirsInfo, lang)}</dd></div>
                    )}
                    {rainfall && (
                      <div><dt>{t("Rain (observed)", "ฝน (ตรวจวัดจริง)")}</dt><dd>{t(
                        `Hourly rain at ${rainfall.stations.length} HII gauges is charted under the stage curve; it is the forcing, not a measure of flooding.`,
                        `ปริมาณฝนรายชั่วโมงจากสถานีของ สสน. ${rainfall.stations.length} แห่งแสดงในกราฟใต้กราฟระดับน้ำ เป็นปัจจัยที่ทำให้เกิดน้ำ ไม่ใช่ตัววัดน้ำท่วม`,
                      )}</dd></div>
                    )}
                    <div><dt>{t("Confidence", "ความเชื่อมั่น")}</dt><dd><span className={styles.confidence}>{isLowConfidence ? t("LOW", "ต่ำ") : manifest.confidence}</span> <Localized text={manifest.confidence_reason} language={lang} /></dd></div>
                    {manifest.population && (
                      <div><dt>{t("Residents", "ผู้อยู่อาศัย")}</dt><dd>{t(
                        `${plainManifestText(manifest.population.source)} (${manifest.population.timestamp}, ${manifest.population.licence}); modelled residents, not the 2024 population.`,
                        `${plainManifestText(manifest.population.source)} (${manifest.population.timestamp}, ${manifest.population.licence}) ผู้อยู่อาศัยตามแบบจำลอง ไม่ใช่ประชากรปี 2567 (2024)`,
                      )}</dd></div>
                    )}
                    {accessInfo && (
                      <div><dt>{t("Access", "การเข้าถึง")}</dt><dd><Term id="t1" language={lang}>{t("T1 scenario", "สถานการณ์จำลองระดับ T1")}</Term>{t(
                        " (model), not observed evacuation outcomes; same stage and road rules as the water above.",
                        " ไม่ใช่ผลการอพยพที่สังเกตได้ ใช้ระดับน้ำและเกณฑ์ถนนเดียวกับน้ำด้านบน",
                      )}</dd></div>
                    )}
                    {manifest.gauge_note && (
                      <div><dt>{t("River gauge", "สถานีวัดระดับน้ำ")}</dt><dd><Localized text={manifest.gauge_note} language={lang} /></dd></div>
                    )}
                  </dl>
                  <RadarCheck manifest={manifest} radarSpan={radarSpan} language={lang} />
                  <ExternalChecks manifest={manifest} language={lang} />
                </section>

                {viirsInfo && (
                  <ViirsComparisonCard viirs={viirsInfo} activeDate={viirsDay?.date ?? null} showOnMap={showViirs} onShowOnMap={setShowViirs} language={lang} />
                )}

                <section className={styles.card} aria-labelledby="mae-sai-share-title">
                  <h2 id="mae-sai-share-title">{t("Share and export", "แชร์และส่งออก")}</h2>
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
                </section>

                <SourcesPanel manifest={manifest} language={lang} offlineCopy={offlineCopy} />
              </>
            )}
          </aside>
        </div>
        <footer className={styles.footer}>{t(
          "FloodGuard supports preparedness and rapid post-event prioritisation. This replay is a report-only reconstruction and does not feed the planning decision layer: it computes no Flood Preparedness Priority Score and assigns no action class (A–E). Card themes such as “Protect Lives Now” only name the planning theme a card relates to.",
          "FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญอย่างรวดเร็วหลังเกิดเหตุ การย้อนดูนี้เป็นการจำลองเพื่อรายงานเท่านั้น และไม่ถูกนำไปใช้ในส่วนตัดสินใจเพื่อการวางแผน ไม่มีการคำนวณคะแนนลำดับความสำคัญด้านการเตรียมพร้อมรับน้ำท่วม (FPPS) และไม่มีการกำหนดกลุ่มการดำเนินการ (A–E) ประเด็นที่ระบุบนการ์ด เช่น “ปกป้องชีวิตทันที” บอกเพียงหัวข้อการวางแผนที่การ์ดนั้นเกี่ยวข้อง",
        )}</footer>
      </div>
    </main>
  );
}

/**
 * The shared "How to read these numbers" box near the top: what is model, observed or reported, the replay's
 * confidence, how timestamps work, where the assumptions are, and a short glossary. Collapsed to one line.
 */
export function HowToRead({ manifest, language }: { manifest: TimelineManifest | null; language: Language }) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const openSources = () => {
    const sources = document.getElementById("mae-sai-sources");
    if (sources instanceof HTMLDetailsElement) sources.open = true;
  };
  return (
    <details className={styles.howTo} data-testid="how-to-read">
      <summary>{t("How to read these numbers", "วิธีอ่านตัวเลขเหล่านี้")}</summary>
      <ul className={styles.list}>
        <li>{t(
          "Model: the blue water, impacts, access and shelter plans are model outputs from an assumed river level. Observed: satellite images, VIIRS daily flood maps and rain gauges. Reported: the event narrative and the 2024 shelter list come from public reporting.",
          "แบบจำลอง: น้ำสีน้ำเงิน ผลกระทบ การเข้าถึง และแผนที่พักพิง มาจากแบบจำลองที่ใช้ระดับน้ำสมมุติ การสังเกตการณ์: ภาพดาวเทียม แผนที่น้ำท่วมรายวัน VIIRS และสถานีวัดฝน รายงาน: เรื่องราวเหตุการณ์และรายชื่อที่พักพิงปี 2567 (2024) มาจากรายงานสาธารณะ",
        )}</li>
        <li>
          {t("Confidence: ", "ความเชื่อมั่น: ")}<strong>{!manifest || manifest.confidence.toLowerCase() === "low" ? t("low", "ต่ำ") : manifest.confidence}</strong>
          {manifest && <>{" — "}<Localized text={manifest.confidence_reason} language={language} /></>}
          {t(" The scenario cards state their own confidence and source dates.", " การ์ดสถานการณ์จำลองระบุความเชื่อมั่นและวันที่ของข้อมูลต้นทางของตนเอง")}
        </li>
        <li>{t(
          "Timestamps: every figure is for the replay hour shown above the map (local time, ICT, UTC+7), not for today.",
          "เวลา: ตัวเลขทุกตัวเป็นค่า ณ ชั่วโมงของการย้อนดูที่แสดงเหนือแผนที่ (เวลาประเทศไทย UTC+7) ไม่ใช่เวลาปัจจุบัน",
        )}{manifest && <> {t("Source data", "ข้อมูลต้นทาง")}: <span lang="en">{manifest.source_timestamp}</span>.</>}</li>
        <li>{t("Assumptions and limits are listed in full under ", "สมมติฐานและข้อจำกัดทั้งหมดอยู่ใน ")}<a href="#mae-sai-sources" className={styles.inlineLink} onClick={openSources}>{t("Sources, assumptions and limits", "แหล่งข้อมูล สมมติฐาน และข้อจำกัด")}</a>.</li>
      </ul>
      <dl className={styles.glossary}>
        {GLOSSARY_ORDER.map((id) => (
          <div key={id}><dt>{GLOSSARY[id].term[language]}</dt><dd>{GLOSSARY[id].definition[language]}</dd></div>
        ))}
      </dl>
    </details>
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
 * Sources, assumptions and limits. Manifest sentences are shown in Thai where the page knows a translation (source
 * names, licences and attributions stay as published, marked English); where this revision states an assumption too
 * simply, the page adds a bilingual note under it. Memoised: it does not depend on the replay clock.
 */
export const SourcesPanel = memo(function SourcesPanel({ manifest, language, offlineCopy }: { manifest: TimelineManifest; language: Language; offlineCopy: OfflineCopy | null }) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const accessInfo = manifest.access ?? null;
  const confidenceText = manifest.confidence.toLowerCase() === "low" ? t("low", "ต่ำ") : manifest.confidence;
  const pendingReferences = referencesNotIngested(manifest);
  const viirs = manifest.viirs_daily ?? null;
  const rain = manifest.rainfall ?? null;
  return (
    <details className={styles.card} data-testid="sources-panel" id="mae-sai-sources">
      <summary>{t("Sources, assumptions and limits", "แหล่งข้อมูล สมมติฐาน และข้อจำกัด")}</summary>
      {th && <p className={styles.muted}>ชื่อแหล่งข้อมูล สัญญาอนุญาต และข้อความที่ยังไม่มีคำแปลคงไว้เป็นภาษาอังกฤษตามต้นฉบับ</p>}
      <h3>{t("Sources", "แหล่งข้อมูล")}</h3>
      {/* Source names, licences and attributions stay as their publishers give them; known sentences are in Thai. */}
      <ul className={styles.list}>
        {manifest.sources.map((source) => (
          <li key={source.id}><strong lang="en">{source.name}</strong> — <span lang="en">{source.licence}. {source.attribution}.</span> <span className={styles.muted} lang="en">{source.timestamp}</span></li>
        ))}
        {manifest.population && (
          <li><strong lang="en">{plainManifestText(manifest.population.source)}</strong> — <span lang="en">{manifest.population.licence}.</span> <Localized text={manifest.population.note} language={language} /> <span className={styles.muted}>{manifest.population.timestamp}</span></li>
        )}
      </ul>
      {(viirs || rain) && (
        <>
          <h3>{t("Observed data shown with the model", "ข้อมูลที่สังเกตได้ซึ่งแสดงคู่กับแบบจำลอง")}</h3>
          <ul className={styles.list} data-testid="observed-sources">
            {viirs && (
              <li>
                <strong lang="en">{viirs.product}</strong> — <span lang="en">{viirs.licence}. {viirs.attribution}.</span>{" "}
                <Localized text={viirs.nominal_overpass} language={language} />{" "}
                <Localized text={viirs.comparison_rule} language={language} />{" "}
                <Localized text={viirs.caveat} language={language} />{" "}
                <a href={viirs.source_url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{viirs.source_url}</a>
              </li>
            )}
            {rain && (
              <li>
                <strong lang="en">{rain.source}</strong> — <span lang="en">{rain.licence}.</span> <Localized text={rain.note} language={language} />{" "}
                {t("Units", "หน่วย")}: <Localized text={rain.units} language={language} />{th ? " " : ". "}
                {t("Stations", "สถานี")}: {rain.stations.map((station) => `${station.code} ${rainStationName(station, language)} (${station.lat.toFixed(3)}, ${station.lon.toFixed(3)}; ${t(`${station.missing_hours} missing hours`, `ไม่มีข้อมูล ${station.missing_hours} ชั่วโมง`)})`).join("; ")}{th ? "" : "."}{" "}
                <a href={rain.source_url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{rain.source_url}</a>
              </li>
            )}
          </ul>
        </>
      )}
      {pendingReferences.length > 0 && (
        <>
          <h3>{t("Other references (not ingested)", "เอกสารอ้างอิงอื่น (ยังไม่ได้นำเข้า)")}</h3>
          <ul className={styles.list}>
            {pendingReferences.map((reference) => (
              <li key={reference.url}>
                <span lang="en">{reference.name}</span>{reference.note ? <>{" — "}<Localized text={reference.note} language={language} /></> : null}{" "}
                <a href={reference.url} target="_blank" rel="noopener noreferrer" className={styles.inlineLink}>{reference.url}</a>
              </li>
            ))}
          </ul>
        </>
      )}
      {accessInfo && (
        <>
          <h3>{t("Evacuation access scenario", "สถานการณ์จำลองการเข้าถึงการอพยพ")}</h3>
          <ul className={styles.list}>
            <li><Localized text={accessInfo.scenario_tier} language={language} />{th ? " " : ". "}<Localized text={accessInfo.definition} language={language} /></li>
            <li>{t("Travel", "การเดินทาง")}: <Localized text={accessInfo.travel_mode} language={language} />{t(
              `; threshold ${accessInfo.threshold_m} m; levels ${accessInfo.levels[0]}–${accessInfo.levels.at(-1)} m every ${accessLevelStep(accessInfo.levels)} m.`,
              ` ระยะเกณฑ์ ${accessInfo.threshold_m} ม. ประเมินระดับน้ำ ${accessInfo.levels[0]}–${accessInfo.levels.at(-1)} ม. ทุก ${accessLevelStep(accessInfo.levels)} ม.`,
            )}</li>
            <li>{t(
              `Residents: ${formatPeople(accessInfo.totals.population)} at road nodes (${formatPeople(accessInfo.totals.vulnerable)} in the terrain/remoteness proxy group, ${formatPeople(accessInfo.totals.non_vulnerable)} others).`,
              `ผู้อยู่อาศัย: ${formatPeople(accessInfo.totals.population)} คนที่จุดถนน (กลุ่มตัวแทนความเปราะบางจากภูมิประเทศและความห่างไกล ${formatPeople(accessInfo.totals.vulnerable)} คน กลุ่มอื่น ${formatPeople(accessInfo.totals.non_vulnerable)} คน)`,
            )}</li>
          </ul>
        </>
      )}
      <h3>{t("Assumptions", "สมมติฐาน")}</h3>
      <ul className={styles.list}>
        {manifest.assumptions.map((item) => {
          const caveat = assumptionCaveat(item);
          return (
            <li key={item}>
              <Localized text={item} language={language} />
              {caveat && <span className={styles.assumptionNote} data-testid="assumption-note">{t("Page note", "หมายเหตุของหน้านี้")}: {caveat[language]}</span>}
            </li>
          );
        })}
      </ul>
      <h3>{t("Limitations", "ข้อจำกัด")}</h3>
      <ul className={styles.list}>{manifest.limitations.map((item) => <li key={item}><Localized text={item} language={language} /></li>)}</ul>
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

/**
 * Evidence row for low-confidence water: how much of the modelled peak it is and what it means. Rendered only when the
 * manifest declares the raster channel that flags it (the page decodes that channel only then).
 */
export function LowConfidenceEvidence({ hand, language }: { hand: TimelineManifest["hand"]; language: Language }) {
  if (!hand.low_confidence_channel) return null;
  const th = language === "th";
  const share = hand.low_confidence_share;
  return (
    <div data-testid="low-confidence-evidence">
      <dt>{th ? "น้ำที่มีความเชื่อมั่นต่ำ" : "Low-confidence water"}</dt>
      <dd>
        {share && (th
          ? `${km(share.low_confidence_km2)} จาก ${km(share.peak_flooded_km2)}\u00a0ตร.กม. ที่เปียกในช่วงระดับน้ำสูงสุดของแบบจำลองเป็นพื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง แผนที่และภาพที่ส่งออกแสดงส่วนนี้เป็นสีจางพร้อมลายเส้นทแยงในมุมมองความลึกและประชากร `
          : `${km(share.low_confidence_km2)} of the ${km(share.peak_flooded_km2)}\u00a0km² wet at the modelled peak is flat or filled low ground in the elevation model; the map and the exports draw it paler and hatched in the depth and people views. `)}
        {hand.low_confidence && <Localized text={hand.low_confidence.meaning} language={language} />}
      </dd>
    </div>
  );
}

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
  // Only when some district land lies outside the model grid does the card speak of "modelled parts".
  const complete = coverageComplete(coverage);
  const count = tambonCount === 8 ? "eight" : String(tambonCount);
  const scope = complete
    ? t(`All ${count} Mae Sai subdistricts, fully modelled — ${district} km²`, `ทั้ง ${tambonCount} ตำบลในอำเภอแม่สาย จำลองครบทั้งพื้นที่ — ${district} ตร.กม.`)
    : t(
      `Modelled parts of the ${count} Mae Sai subdistricts — ${modelled} of ${district} km²`,
      `ส่วนที่แบบจำลองครอบคลุมของ ${tambonCount} ตำบลในอำเภอแม่สาย — ${modelled} จาก ${district} ตร.กม.`,
    );
  const reason = localized(coverage.reason, language);
  const facilitiesOutside = manifest.facilities_count.total - manifest.facilities_count.modelled;
  const coverageNote = (
    <>
      {complete ? t("Model coverage: ", "ขอบเขตแบบจำลอง: ") : t("Not modelled: ", "ส่วนที่ไม่ได้จำลอง: ")}<span lang={reason.lang}>{reason.text}</span>
      {manifest.roads_not_modelled_km > 0 && <>{" "}{t(
        `${km(manifest.roads_not_modelled_km, 2)} km of mapped road there is drawn grey and dashed and excluded from these figures.`,
        `ถนน ${km(manifest.roads_not_modelled_km, 2)} กม. ในส่วนนั้นแสดงเป็นเส้นประสีเทาและไม่นับรวมในตัวเลขเหล่านี้`,
      )}</>}
      {facilitiesOutside > 0 && <>{" "}{t(
        `${facilitiesOutside} key facilit${facilitiesOutside === 1 ? "y (OSM) is" : "ies (OSM) are"} outside the model (grey hollow markers) and excluded.`,
        `สถานที่สำคัญ (ข้อมูล OSM) ${facilitiesOutside} แห่งอยู่นอกแบบจำลอง (วงกลมกลวงสีเทา) และไม่นับรวม`,
      )}</>}
    </>
  );
  return (
    <div className={styles.card}>
      <h2>{t("Impact (model)", "ผลกระทบ (แบบจำลอง)")}</h2>
      <p className={styles.scope} title={reason.text}>{scope}</p>
      <dl className={styles.kpis}>
        <div><dt>{t("Flooded area", "พื้นที่น้ำท่วม")}</dt><dd>{km(stats.flooded_km2)}<small> {unit.km2}</small></dd></div>
        <div><dt>{t("Roads impassable (≥ 0.3\u00a0m)", "ถนนสัญจรไม่ได้ (≥ 0.3\u00a0ม.)")}</dt><dd data-tone="alert">{km(stats.road_km_impassable)}<small> {unit.km}</small></dd></div>
        <div><dt>{t("Roads wet (< 0.3\u00a0m)", "ถนนมีน้ำ (< 0.3\u00a0ม.)")}</dt><dd data-tone="warn">{km(stats.road_km_wet)}<small> {unit.km}</small></dd></div>
        <div><dt>{t("Key facilities (OSM) in water", "สถานที่สำคัญ (ข้อมูล OSM) ที่อยู่ในน้ำ")}</dt><dd>{stats.facilities_wet}<small> / {manifest.facilities_count.modelled}</small></dd></div>
      </dl>
      {/* Unmodelled land limits the figures, so it stays in view; a fully modelled district is a method note in the chip. */}
      {!complete && <p className={styles.muted}>{coverageNote}</p>}
      <ProvenanceNote kind="impact" confidence={manifest.confidence} reason={manifest.confidence_reason} timestamp={manifest.source_timestamp} language={language}>
        {t("Computed in your browser from the terrain model at this stage.", "คำนวณในเบราว์เซอร์ของคุณจากแบบจำลองภูมิประเทศ ณ ระดับน้ำนี้")}
        {complete && <>{" "}{coverageNote}</>}
      </ProvenanceNote>
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
 * "Keep Routes Open" list: modelled road groups with the longest impassable spells over the replay, named roads first
 * and unnamed street groups after, each ranked by road importance × longest cut. Named roads show an English label with
 * the Thai name in brackets where one is known. Each entry fits the map to its cut pieces. Memoised: it does not depend
 * on the replay clock.
 */
export const RouteCutsCard = memo(function RouteCutsCard({ groups, names, language, focused, onFocus, onReset, roadLengths, provenance }: {
  groups: readonly RoadCutGroup[];
  names: Record<string, TambonProps>;
  language: Language;
  focused: string | null;
  onFocus: (group: RoadCutGroup) => void;
  onReset: () => void;
  /** Total modelled length (km) of each named road, cut or not. */
  roadLengths?: ReadonlyMap<string, number>;
  /** Confidence, reason and source timestamp of the water model behind the cuts, for the card's confidence chip. */
  provenance?: { confidence: string; reason: string; timestamp: string };
}) {
  const th = language === "th";
  const t = (en: string, thai: string) => (th ? thai : en);
  const tambonName = (id: string) => names[id]?.[language] ?? id;
  const named = groups.filter((group) => group.name !== null);
  const unnamed = groups.filter((group) => group.name === null);
  const item = (group: RoadCutGroup, index: number) => {
    const classText = group.classes.map((value) => roadClassLabel(value, language)).join(", ");
    const label = group.name ? roadNameText(group.name, language) : null;
    const title = label?.primary ?? `${roadClassLabel(group.classes[0] ?? "", language)} ${t("(unnamed)", "(ไม่มีชื่อ)")}`;
    const titleLang = THAI_SCRIPT.test(title) ? "th" : language;
    const tambons = group.tambons.slice(0, 3).map(tambonName).join(", ") + (group.tambons.length > 3 ? ` +${group.tambons.length - 3}` : "");
    const reopen = group.reopenHour === null
      ? t("not reopened by the end of 19 Sep", "ยังไม่เปิดจนสิ้นวันที่ 19 ก.ย.")
      : formatHourStamp(group.reopenHour, language);
    const length = group.name ? roadLengths?.get(group.name.trim()) : undefined;
    return (
      <li key={group.key}>
        <button type="button" aria-pressed={focused === group.key} onClick={() => onFocus(group)}>
          <span className={styles.routeHead}>
            <span className={styles.routeRank} aria-hidden="true">{index + 1}</span>
            <strong lang={titleLang}>{title}{label?.secondary && <span className={styles.routeThai} lang="th"> ({label.secondary})</span>}</strong>
          </span>
          <span className={styles.routeMeta}>{group.name ? `${classText} · ` : ""}{t("Subdistrict", "ตำบล")}: {tambons}</span>
          <span className={styles.routeFigures}>
            <span>{t(`Up to ${group.maxHours}\u00a0h cut`, `ตัดขาดสูงสุด ${group.maxHours}\u00a0ชม.`)}</span>
            <span>{length !== undefined && length > 0
              ? t(`${km(group.kmCut, 2)} of ${km(length, 1)}\u00a0km modelled cut`, `ตัดขาด ${km(group.kmCut, 2)} จาก ${km(length, 1)}\u00a0กม. ที่จำลอง`)
              : t(`${km(group.kmCut, 2)}\u00a0km cut`, `ตัดขาด ${km(group.kmCut, 2)}\u00a0กม.`)}</span>
          </span>
          <span className={styles.routeTimes}>{t("First cut", "เริ่มตัดขาด")} {formatHourStamp(group.firstHour, language)} → {t("reopened", "เปิดอีกครั้ง")} {reopen}</span>
        </button>
      </li>
    );
  };
  return (
    <section className={styles.card} aria-labelledby="mae-sai-route-cuts-title">
      <ThemeEyebrow theme="keep_routes" language={language} />
      <h2 id="mae-sai-route-cuts-title">{t("Longest-cut routes (Keep Routes Open)", "เส้นทางที่ถูกตัดขาดนานที่สุด (รักษาเส้นทางให้สัญจรได้)")}</h2>
      <p className={styles.muted}>{t(
        "Modelled, not observed closures: hours each road piece is impassable (reconstructed depth ≥ 0.3\u00a0m) at the assumed stages, 9–19 Sep. Named roads come first, ranked by road importance (trunk and primary roads first) × longest cut; unnamed pieces are grouped by class and subdistrict. Select one to show it on the map.",
        "การปิดถนนตามแบบจำลอง ไม่ใช่การปิดที่สังเกตได้จริง: จำนวนชั่วโมงที่ถนนแต่ละช่วงสัญจรไม่ได้ (ความลึกจำลอง ≥ 0.3\u00a0ม.) ที่ระดับน้ำสมมุติ 9–19 ก.ย. ถนนที่มีชื่อแสดงก่อน เรียงตามความสำคัญของถนน (ทางหลวงสายหลักก่อน) × ระยะเวลาที่ถูกตัดขาดนานที่สุด ถนนไม่มีชื่อจัดกลุ่มตามประเภทและตำบล เลือกเพื่อแสดงบนแผนที่",
      )}</p>
      {provenance && (
        <ProvenanceNote kind="routes" confidence={provenance.confidence} reason={provenance.reason} timestamp={provenance.timestamp} language={language}>
          {t(
            "Hours are counted on the replay's hourly grid (the assumed stage at the start of each local hour, 9 Sep 00:00 to 19 Sep 23:00); a road piece is 120 m long.",
            "นับชั่วโมงตามช่วงรายชั่วโมงของการย้อนดู (ระดับน้ำสมมุติ ณ ต้นชั่วโมงเวลาท้องถิ่น ตั้งแต่ 9 ก.ย. 00:00 ถึง 19 ก.ย. 23:00) ถนนแต่ละช่วงยาว 120 ม.",
          )}
        </ProvenanceNote>
      )}
      {groups.length === 0 ? (
        <p>{t("No modelled road piece reaches 0.3 m at any hour of the replay.", "ไม่มีถนนช่วงใดในแบบจำลองที่น้ำลึกถึง 0.3 ม. ตลอดการย้อนดู")}</p>
      ) : (
        <>
          {named.length > 0 && (
            <>
              <h3>{t(`Named roads (${named.length})`, `ถนนที่มีชื่อ (${named.length})`)}</h3>
              <ol className={styles.routeList}>{named.map(item)}</ol>
            </>
          )}
          {unnamed.length > 0 && (
            <>
              <h3>{t(`Unnamed street groups (top ${unnamed.length})`, `กลุ่มถนนไม่มีชื่อ (${unnamed.length} อันดับแรก)`)}</h3>
              <ol className={styles.routeList}>{unnamed.map(item)}</ol>
            </>
          )}
        </>
      )}
      {focused && (
        <button type="button" className={styles.linkButton} onClick={onReset}>{t("Show the whole area", "แสดงทั้งพื้นที่")}</button>
      )}
    </section>
  );
});

/**
 * Keyboard- and screen-reader-reachable list of the modelled key facilities (OSM) in water at `stage`, deepest first.
 * Renders nothing when none are wet.
 */
export function WetFacilitiesCard({ facilities, stage, language }: { facilities: readonly FacilityProps[]; stage: number; language: Language }) {
  const wet = facilitiesInWater(facilities, stage);
  if (wet.length === 0) return null;
  const th = language === "th";
  return (
    <section className={styles.card} aria-labelledby="mae-sai-wet-facilities-title">
      <h2 id="mae-sai-wet-facilities-title">{th ? `สถานที่สำคัญ (ข้อมูล OSM) ที่อยู่ในน้ำ ณ ชั่วโมงนี้ของการย้อนดู (${wet.length})` : `Key facilities (OSM) in water at this replay hour (${wet.length})`}</h2>
      <ol className={styles.facilityList}>
        {wet.map(({ facility, depth }) => (
          <li key={facility.id}>
            <span><strong>{facilityTypeLabel(facility.type, language)}</strong> · {facility.n || (th ? "ไม่มีชื่อ" : "Unnamed")}</span>
            <span className={styles.depth}>{th ? `ลึก ≈ ${formatDepth(depth)} ม.` : `depth ≈ ${formatDepth(depth)} m`}</span>
          </li>
        ))}
      </ol>
      <p className={styles.muted}>{th
        ? "ความลึกจากแบบจำลองที่สถานที่สำคัญจาก OpenStreetMap แต่ละแห่ง เรียงจากลึกที่สุด ยังไม่ได้ตรวจสอบในพื้นที่จริง"
        : "Reconstructed depth (model) at each OpenStreetMap key facility, deepest first; not verified on the ground."}</p>
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

/** Swatch of low-confidence water: a pale, hatched version of the water colour. */
function LowConfidenceSwatch() {
  return <i className={styles.lowConfidenceSwatch} aria-hidden="true" />;
}

/**
 * Map legend. `part` "overlay" is the compact on-map legend for what is drawn at this moment (the active water and
 * road modes, low-confidence water, and the scenario or observed layers the reader switched on); "symbols" is the
 * marker key (key facilities, shelters, gauges); the default draws both.
 */
export function TimelineLegend({
  language, unmodelledRoads, unmodelledFacilities, waterMode = "depth", roadMode = "state", arrival = [], densityMax, shelters, cutoff = false,
  viirs = null, gauges = false, facilities = true, lowConfidence = false, part = "all",
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
  /** The observed VIIRS daily map is shown (its legend labels come from the manifest). */
  viirs?: Pick<ViirsDaily, "legend"> | null;
  /** The rain-gauge markers are shown. */
  gauges?: boolean;
  /** The key facilities (OSM) layer is shown. */
  facilities?: boolean;
  /** Low-confidence water is drawn (the manifest declares its channel and the view is depth or people). */
  lowConfidence?: boolean;
  part?: "overlay" | "symbols" | "all";
}) {
  const th = language === "th";
  const channel = <li><i style={{ background: rgbaCss(CHANNEL_RGBA) }} />{th ? "ร่องน้ำ/แม่น้ำ (น้ำตลอดเวลา)" : "River channel (always water)"}</li>;
  const lowConfidenceItem = lowConfidence && (
    <li data-testid="low-confidence-legend"><LowConfidenceSwatch />{th
      ? "น้ำที่มีความเชื่อมั่นต่ำ: พื้นที่ต่ำที่ราบเรียบหรือถูกถมในแบบจำลองความสูง"
      : "Low-confidence water: flat or filled low ground in the elevation model"}</li>
  );
  const residentsView = (waterMode === "people" || waterMode === "residents") && densityMax !== undefined;
  const anyShelter = shelters && (shelters.reported || shelters.candidates || shelters.ineligible);
  const overlay = part !== "symbols";
  const symbols = part !== "overlay";
  return (
    <div className={styles.legend} aria-label={th ? (part === "symbols" ? "สัญลักษณ์บนแผนที่" : "คำอธิบายสัญลักษณ์") : (part === "symbols" ? "Map symbols" : "Legend")} role="group">
      {overlay && (residentsView ? (
        <div>
          <DensityLegend maxPerHa={densityMax} language={language} wetOnly={waterMode === "people"} />
          {lowConfidenceItem && <ul>{lowConfidenceItem}</ul>}
        </div>
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
            {DEPTH_CLASSES.map((item) => <li key={item.label}><i style={{ background: rgbaCss(item.rgba) }} />{item.label.replace(" m", th ? "\u00a0ม." : "\u00a0m")}</li>)}
            <li><i style={{ background: rgbaCss(CHANNEL_RGBA) }} />{th ? "ร่องน้ำ/แม่น้ำ" : "River channel"}</li>
            {lowConfidenceItem}
          </ul>
        </div>
      ))}
      {overlay && (
        <div>
          {roadMode === "hours" ? (
            <>
              <strong>{th ? "ถนน — ชั่วโมงที่สัญจรไม่ได้ ≥ 0.3 ม. (แบบจำลอง)" : "Roads — hours impassable ≥ 0.3 m (model)"}</strong>
              <ul>
                {ROAD_CUT_CLASSES.map((item) => <li key={item.min}><i className={styles.line} style={{ background: item.color }} />{item.label[language]}</li>)}
                {unmodelledRoads && <li><i className={styles.dash} style={{ borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
              </ul>
            </>
          ) : (
            <>
              <strong>{th ? "ถนน (แบบจำลอง)" : "Roads (model)"}</strong>
              <ul>
                <li><i className={styles.line} style={{ background: ROAD_STYLES.dry.color }} />{th ? "แห้ง" : "Dry"}</li>
                <li><i className={styles.line} style={{ background: ROAD_STYLES.wet.color }} />{th ? "มีน้ำ < 0.3\u00a0ม." : "Wet < 0.3\u00a0m"}</li>
                <li><i className={styles.line} style={{ background: ROAD_STYLES.impassable.color }} />{th ? "สัญจรไม่ได้ ≥ 0.3\u00a0ม." : "Impassable ≥ 0.3\u00a0m"}</li>
                {unmodelledRoads && <li><i className={styles.dash} style={{ borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
              </ul>
            </>
          )}
        </div>
      )}
      {overlay && cutoff && (
        <div>
          <strong>{th ? "ผู้ที่ถูกตัดขาดจากที่พักพิงที่แห้ง (สถานการณ์จำลอง)" : "People cut off from a dry shelter (scenario)"}</strong>
          <ul>
            <li><i className={styles.cutoffRamp} aria-hidden="true" />{th ? "น้อย → มาก (ถ่วงน้ำหนักตามประชากร)" : "Fewer → more people (population-weighted)"}</li>
          </ul>
        </div>
      )}
      {overlay && viirs && <ViirsLegend viirs={viirs} language={language} />}
      {symbols && facilities && (
        <div>
          <strong>{th ? "สถานที่สำคัญ (ข้อมูล OSM)" : "Key facilities (OSM)"}</strong>
          <ul>
            <li><i className={styles.dot} style={{ background: "#fff", borderColor: "#0c2740" }} />{th ? "แห้ง" : "Dry"}</li>
            <li><i className={styles.dot} style={{ background: "#c62828", borderColor: "#fff" }} />{th ? "อยู่ในน้ำ" : "In water"}</li>
            {unmodelledFacilities && <li><i className={styles.dot} style={{ background: "transparent", borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
          </ul>
        </div>
      )}
      {symbols && anyShelter && (
        <div>
          <strong>{th ? "ที่พักพิง" : "Shelters"}</strong>
          <ul>
            {shelters.reported && <li><i className={styles.legendStar} aria-hidden="true">★</i>{th ? `มีรายงานว่าใช้ ก.ย. ${thaiYear(2024)}` : "Reported in use, Sep 2024"}</li>}
            {shelters.reported && <li><i className={`${styles.legendStar} ${styles.legendStarFloods}`} aria-hidden="true">★</i>{th ? "มีรายงาน แต่แบบจำลองระบุว่าน้ำท่วมที่ระดับสูงสุด (ดาวมีขีดทับ)" : "Reported, but floods at the modelled peak (struck-through star)"}</li>}
            {shelters.reported && shelters.command && <li><i className={styles.legendCommand} aria-hidden="true">◆</i>{th ? "ศูนย์บัญชาการและจุดช่วยเหลือ (ไม่ใช่ที่พักพิง)" : "Relief and command site (not a shelter)"}</li>}
            {shelters.candidates && <li><i className={styles.legendBadge} aria-hidden="true">1</i>{th ? "ลำดับในแผน (k แห่งแรก)" : "Plan rank (first k sites)"}</li>}
            {shelters.candidates && <li><i className={`${styles.legendBadge} ${styles.legendBadgeFlag}`} aria-hidden="true">1</i>{th ? "“!” ไม่ทราบความจุ หรือความจุต่ำกว่าภาระมาก" : "“!” capacity unknown or far below its load"}</li>}
            {shelters.candidates && <li><i className={styles.dot} style={{ background: "#fff", borderColor: "#0b6e4f" }} />{th ? "เข้าเกณฑ์ ไม่อยู่ใน k แห่งแรก" : "Eligible, not in the first k"}</li>}
            {shelters.ineligible && <li><i className={styles.dot} style={{ background: "#a3acba", borderColor: "#6b7585" }} />{th ? "ไม่เข้าเกณฑ์ (เหตุผลอยู่ในป้ายและรายการสถานที่อื่น)" : "Not eligible (reasons in the popup and the other-candidates list)"}</li>}
            {shelters.ineligible && shelters.unmodelled && <li><i className={styles.dot} style={{ background: "transparent", borderColor: NOT_MODELLED_GREY, borderStyle: "dashed" }} />{th ? "ไม่ได้จำลอง (นอกแบบจำลองภูมิประเทศ)" : "Not modelled (outside the terrain model)"}</li>}
          </ul>
        </div>
      )}
      {symbols && gauges && (
        <div>
          <strong>{th ? "ฝน (ตรวจวัดจริง)" : "Rain (observed)"}</strong>
          <ul>
            <li><i className={styles.legendGauge} aria-hidden="true"><svg viewBox="0 0 24 24" width="14" height="14" focusable="false"><path d={GAUGE_PATH} /></svg></i>{th ? "สถานีวัดฝนรายชั่วโมง (ปัจจัยที่ทำให้เกิดน้ำ ไม่ใช่น้ำท่วม)" : "Hourly rain gauge (forcing, not flooding)"}</li>
          </ul>
        </div>
      )}
      {symbols && !facilities && !anyShelter && !gauges && (
        <p className={styles.muted}>{th ? "ไม่มีสัญลักษณ์เปิดอยู่ เปิดได้ที่ “ชั้นแผนที่”" : "No marker layers are on; turn them on under “Map layers”."}</p>
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
    ? `กราฟระดับน้ำสมมุติ 9–19 ก.ย. สูงสุด ${peak.stage_m} ม. วันที่ ${peakDate} ณ ชั่วโมงนี้ของการย้อนดู ${stage.toFixed(2)} ม.`
    : `Assumed stage curve for 9–19 Sep, peaking at ${peak.stage_m} m on ${peakDate}; ${stage.toFixed(2)} m at this replay hour.`;
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
            ? "ระดับน้ำสมมุติของลำน้ำหลักแม่น้ำสายที่สะพานแม่สาย (ม.) — เพื่อการอธิบาย ลำน้ำสาขาสูงขึ้นเพียงบางส่วนของระดับนี้"
            : "Assumed Sai main-stem stage at the Mae Sai bridges (m) — illustrative; tributaries rise to a fraction of this level"
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
