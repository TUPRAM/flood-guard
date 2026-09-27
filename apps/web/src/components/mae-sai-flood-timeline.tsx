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
  Path,
  PathOptions,
  Renderer,
} from "leaflet";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import {
  buildDepthLut,
  CHANNEL_RGBA,
  coverageShare,
  dateFromT,
  decodeGrayPng,
  DEPTH_CLASSES,
  districtStats,
  facilitiesInWater,
  facilityDepth,
  facilityWet,
  floodedKm2,
  formatAge,
  formatLocalStamp,
  formatMoment,
  formatShortDate,
  hourIndex,
  inflateZlib,
  latestObservation,
  lutEquals,
  observationGap,
  paintDepth,
  phaseAt,
  rgbaCss,
  roadState,
  stageAt,
  tFromDate,
  tFromLocalDate,
  TIMELINE_END_T,
  waterCandidates,
  type AreaGeometry,
  type FacilityProps,
  type GeoCollection,
  type GrayRaster,
  type Language,
  type LineGeometry,
  type PointGeometry,
  type RoadProps,
  type RoadState,
  type TambonProps,
  type TimelineManifest,
  type TimelineObservation,
} from "@/lib/flood-timeline";
import { useLanguage } from "@/lib/use-language";
import { WorkspaceHeader } from "./workspace-header";

import styles from "./mae-sai-flood-timeline.module.css";

export const MAE_SAI_TIMELINE_ROUTE = "/studio/cases/mae-sai-2024/";
const MANIFEST_URL = "/studies/mae-sai-2024-timeline/r1/timeline.json";
const SECONDS_PER_DAY = 2.5;
const START_T = 0.5;
const HOUR_STEPS = TIMELINE_END_T * 24;
/** During playback the map repaints at most this often, unless the stage has moved by PAINT_STAGE_STEP_M. */
const PAINT_INTERVAL_MS = 120;
const PAINT_STAGE_STEP_M = 0.1;
/** Matches the `.imageryLayer` opacity transition. */
const IMAGERY_FADE_MS = 900;
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
/** Short map credits; full attributions are listed in the Sources panel. */
const OSM_CREDIT = "© OpenStreetMap contributors";
const SENTINEL_CREDIT = "Modified Copernicus Sentinel data 2024";
const DEM_CREDIT = "Copernicus DEM © DLR, Airbus DS";
const WATER_CREDIT = "Water: FloodGuard model";
const NOT_MODELLED_GREY = "#7b8595";

interface ReplayData {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  facilities: GeoCollection<PointGeometry, FacilityProps>;
  tambons: GeoCollection<AreaGeometry, TambonProps>;
}
interface HandRaster { codes: Uint8Array; candidates: Uint32Array }
type LoadState = { status: "loading" } | { status: "error" } | { status: "ready"; data: ReplayData };
type ObservationEntry = { observation: TimelineObservation; at: number };

interface WaterLayer {
  overlay: ImageOverlay;
  context: CanvasRenderingContext2D;
  image: ImageData;
  pixels: Uint32Array;
  /** LUT currently on the canvas, and a second buffer the next LUT is built into (swapped on paint). */
  lastLut: Uint32Array | null;
  spareLut: Uint32Array;
}
interface RoadEntry { layer: Path; h: number | null; state: RoadState }
interface FacilityEntry { layer: CircleMarker; props: FacilityProps; wet: boolean }
/** Imperative map controller; all mutable Leaflet bookkeeping stays inside the mount closure. */
interface MapController {
  /** Apply a stage; `exact` forces a repaint, otherwise repaints are throttled for playback. */
  setStage: (stage: number, hand: HandRaster | null, exact: boolean) => void;
  showImagery: (id: string | null, instant: boolean) => void;
  setWaterOpacity: (opacity: number) => void;
  setVisibility: (tambons: boolean, roads: boolean, facilities: boolean) => void;
  /** Re-render the content of any open tooltip (stage or language changed). */
  refreshTooltips: () => void;
}

const ROAD_STYLES: Record<RoadState | "unmodelled", PathOptions> = {
  dry: { color: "#7d8ba0", weight: 1, opacity: 0.55 },
  wet: { color: "#e8a526", weight: 2.4, opacity: 0.95 },
  impassable: { color: "#c62828", weight: 3.2, opacity: 1 },
  unmodelled: { color: NOT_MODELLED_GREY, weight: 2, opacity: 1, dashArray: "4 4" },
};
const FACILITY_STYLES: Record<"dry" | "wet" | "unmodelled", CircleMarkerOptions> = {
  dry: { radius: 5, color: "#0c2740", weight: 1.5, fillColor: "#ffffff", fillOpacity: 1 },
  wet: { radius: 6.5, color: "#ffffff", weight: 2, fillColor: "#c62828", fillOpacity: 1 },
  unmodelled: { radius: 5, color: NOT_MODELLED_GREY, weight: 2, fillColor: "#ffffff", fillOpacity: 0 },
};
const PHASE_COLOURS: Record<string, string> = {
  dry: "#d6dee9", onset: "#f6c453", peak: "#d7301f", receding: "#f29e4c", gone: "#9cc9b3",
};
const PHASE_TEXT_DARK = "#17253b";
const FACILITY_TYPES: Record<string, [string, string]> = {
  shelter_candidate: ["Shelter candidate", "จุดพักพิงที่เป็นไปได้"],
  school: ["School", "โรงเรียน"],
  emergency_service: ["Emergency service", "หน่วยบริการฉุกเฉิน"],
  community_facility: ["Community facility", "สถานที่ชุมชน"],
  healthcare: ["Healthcare", "สถานพยาบาล"],
};
/** Thai renderings of known manifest sentences; unknown text falls back to the English original. */
const KNOWN_THAI: Record<string, string> = {
  "The Copernicus DEM tile used stops at 100°E; district land east of it is not modelled.":
    "แผ่นข้อมูล Copernicus DEM ที่ใช้สิ้นสุดที่ลองจิจูด 100°E พื้นที่ของอำเภอทางตะวันออกของเส้นนี้จึงไม่ได้จำลอง",
  "Low-HAND zone (HAND < 6 m, channel excluded) across the full image footprint, both sides of the border.":
    "พื้นที่ HAND ต่ำ (HAND < 6 ม. ไม่รวมร่องน้ำ) ทั่วทั้งขอบเขตภาพ ทั้งสองฝั่งชายแดน",
  "Water extents are a terrain-model reconstruction with illustrative stages; only the late-recession size is checked against radar, and spatial agreement there is weak.":
    "ขอบเขตน้ำจำลองจากแบบจำลองภูมิประเทศด้วยระดับน้ำสมมุติ ตรวจสอบกับเรดาร์ได้เฉพาะขนาดพื้นที่ช่วงน้ำลด และตำแหน่งยังสอดคล้องกันน้อย",
};
const IMAGERY_ORDER = ["auto", "s2-20240905", "s2-20240915", "s1-20240906", "s1-20240915", "s1-change", "hillshade", "none"] as const;
const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";
function subscribeReducedMotion(notify: () => void) {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", notify);
  return () => query.removeEventListener("change", notify);
}
function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeReducedMotion, () => window.matchMedia(REDUCED_MOTION_QUERY).matches, () => false);
}

async function fetchJson<T>(href: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(href, { signal });
  if (!response.ok) throw new Error(`${href}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

/** Fallback decoder for browsers without DecompressionStream. */
async function decodeWithCanvas(bytes: Uint8Array): Promise<GrayRaster> {
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
  const data = new Uint8Array(canvas.width * canvas.height);
  for (let index = 0; index < data.length; index += 1) data[index] = rgba[index * 4];
  return { width: canvas.width, height: canvas.height, data };
}

async function loadHand(manifest: TimelineManifest, signal: AbortSignal): Promise<HandRaster> {
  const response = await fetch(manifest.hand.href, { signal });
  if (!response.ok) throw new Error(`HAND raster: HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  const raster = typeof DecompressionStream === "function" ? await decodeGrayPng(bytes, inflateZlib) : await decodeWithCanvas(bytes);
  if (raster.width !== manifest.hand.width || raster.height !== manifest.hand.height) throw new Error("HAND raster size mismatch");
  const maxStage = Math.max(...manifest.stage_anchors.map((anchor) => anchor.stage_m));
  return { codes: raster.data, candidates: waterCandidates(raster.data, maxStage, manifest.hand.step_m) };
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
const sensorName = (observation: TimelineObservation) => (observation.kind === "optical" ? "Sentinel-2" : "Sentinel-1");

export function MaeSaiFloodTimeline() {
  const [language, setLanguage] = useLanguage("en");
  const t = useCallback((en: string, th: string) => (language === "th" ? th : en), [language]);
  const reducedMotion = useReducedMotion();

  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [reloadKey, setReloadKey] = useState(0);
  const [hand, setHand] = useState<HandRaster | null>(null);
  const [handFailed, setHandFailed] = useState(false);
  const [mapReady, setMapReady] = useState(false);
  const [time, setTime] = useState(START_T);
  const [playing, setPlaying] = useState(false);
  const [imagery, setImagery] = useState<string>("auto");
  const [waterOpacity, setWaterOpacity] = useState(0.85);
  const [showTambons, setShowTambons] = useState(true);
  const [showRoads, setShowRoads] = useState(true);
  const [showFacilities, setShowFacilities] = useState(true);

  const timeRef = useRef(START_T);
  const languageRef = useRef<Language>(language);
  const waterOpacityRef = useRef(waterOpacity);
  const mapElement = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<MapController | null>(null);

  const moveTo = useCallback((value: number) => {
    const next = Math.min(TIMELINE_END_T, Math.max(0, value));
    timeRef.current = next;
    setTime(next);
  }, []);

  // --- Data loading ---------------------------------------------------------------------------
  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    (async () => {
      try {
        const manifest = await fetchJson<TimelineManifest>(MANIFEST_URL, signal);
        loadHand(manifest, signal).then(
          (raster) => { if (!signal.aborted) setHand(raster); },
          () => { if (!signal.aborted) setHandFailed(true); },
        );
        const [roads, facilities, tambons] = await Promise.all([
          fetchJson<ReplayData["roads"]>(manifest.vectors.roads.href, signal),
          fetchJson<ReplayData["facilities"]>(manifest.vectors.facilities.href, signal),
          fetchJson<ReplayData["tambons"]>(manifest.vectors.tambons.href, signal),
        ]);
        if (!signal.aborted) setLoad({ status: "ready", data: { manifest, roads, facilities, tambons } });
      } catch {
        if (!signal.aborted) setLoad({ status: "error" });
      }
    })();
    return () => controller.abort();
  }, [reloadKey]);

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
    return { roadProps, facilityProps, names, tambonScale, observations, radar, hasUnmodelledRoads, hasUnmodelledFacilities };
  }, [data]);

  const stage = manifest ? stageAt(time, manifest.stage_anchors) : 0;
  const phase = manifest ? phaseAt(time, manifest.phases) : null;
  const hour = hourIndex(time);
  const stats = useMemo(
    () => (data && derived ? districtStats(data.manifest, stage, derived.roadProps, derived.facilityProps) : null),
    [data, derived, stage],
  );
  const latestOptical = manifest ? latestObservation(time, manifest.observations, "optical") : null;
  const activeImagery = imagery === "auto" ? latestOptical?.observation.id ?? null : imagery === "none" ? null : imagery;
  const gap = manifest ? observationGap(time, manifest.observations) : null;

  useEffect(() => {
    languageRef.current = language;
    waterOpacityRef.current = waterOpacity;
  }, [language, waterOpacity]);

  // --- Map mount ---------------------------------------------------------------------------------
  useEffect(() => {
    if (!data) return;
    const replay = data;
    const { manifest: m } = replay;
    let disposed = false;
    let mounted: LeafletMap | null = null;
    let resizeTimer: number | undefined;
    let resizeObserver: ResizeObserver | undefined;
    const timers = new Set<number>();
    const frames = new Set<number>();

    async function mount() {
      const L = await import("leaflet");
      if (disposed || !mapElement.current) return;
      mapElement.current.replaceChildren();
      const map = L.map(mapElement.current, { zoomControl: true, attributionControl: false, keyboard: true, zoomSnap: 0.25, maxZoom: 17 });
      mounted = map;
      L.control.attribution({ prefix: false }).addTo(map);
      const bounds = L.latLngBounds(m.bounds);
      const fit = () => {
        map.invalidateSize();
        map.fitBounds(bounds, { padding: [6, 6], animate: false });
        map.setMinZoom(Math.max(8, map.getZoom() - 1.5));
      };
      map.setMaxBounds(bounds.pad(0.35));
      fit();

      for (const [name, zIndex] of [["fg-imagery", 250], ["fg-water", 350], ["fg-tambons", 380], ["fg-roads", 400], ["fg-facilities", 450]] as const) {
        const pane = map.createPane(name);
        pane.style.zIndex = String(zIndex);
        pane.style.pointerEvents = "none";
      }

      L.tileLayer(OSM_TILES, {
        attribution: OSM_CREDIT,
        maxZoom: 19,
        opacity: 0.6,
        referrerPolicy: "strict-origin",
        className: styles.basemap,
      }).addTo(map);

      const thai = () => languageRef.current === "th";
      // Stage currently drawn on the map; tooltips describe this stage so they always match the picture.
      let appliedStage = 0;
      let appliedHand: HandRaster | null = null;
      let appliedAt = 0;
      let hasApplied = false;
      const tooltipLayers: Layer[] = [];
      const refreshTooltips = () => {
        for (const layer of tooltipLayers) if (layer.isTooltipOpen()) layer.getTooltip()?.update();
      };

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
        const layer = m.layers.find((candidate) => candidate.id === id);
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
      // The two optical scenes drive Auto mode; load them up front so the crossfade is seamless.
      createImagery("s2-20240905");
      createImagery("s2-20240915");

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
        water = { overlay, context, image, pixels: new Uint32Array(image.data.buffer), lastLut: null, spareLut: new Uint32Array(256) };
      }

      const tambonRenderer = L.svg({ pane: "fg-tambons" });
      const tambonOptions: GeoJSONOptions & { renderer: Renderer } = {
        renderer: tambonRenderer,
        style: () => ({ color: "#1c3d6e", weight: 1.4, opacity: 0.85, dashArray: "5 4", fill: true, fillOpacity: 0 }),
        onEachFeature: (feature, layer) => {
          const props = feature.properties as TambonProps;
          layer.bindTooltip(() => {
            const th = thai();
            const area = floodedKm2(m.tambon_histograms[props.id] ?? new Array(256).fill(0), appliedStage, m.hand.step_m, m.pixel_area_m2);
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

      const roads: RoadEntry[] = [];
      const modelledRoadOptions: GeoJSONOptions & { renderer: Renderer } = {
        renderer: L.canvas({ pane: "fg-roads", padding: 0.5 }),
        interactive: false,
        filter: (feature) => Boolean((feature.properties as RoadProps).m),
        style: () => ROAD_STYLES.dry,
        onEachFeature: (feature, layer) => roads.push({ layer: layer as Path, h: (feature.properties as RoadProps).h, state: "dry" }),
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
        const wet = facilityWet(props, appliedStage);
        const depth = facilityDepth(props.h, appliedStage);
        const status = props.h === null
          ? th ? "อยู่สูงกว่าช่วงน้ำท่วมของแบบจำลอง" : "Above the modelled flood range"
          : wet
            ? th ? `ความลึกจากแบบจำลอง ≈ ${formatDepth(depth)} ม.` : `Reconstructed depth ≈ ${formatDepth(depth)} m`
            : th ? `แห้งที่ระดับนี้ (สูงจากร่องน้ำ ${props.h.toFixed(1)} ม.)` : `Dry at this stage (${props.h.toFixed(1)} m above drainage)`;
        return tooltipElement([[title, "title"], [name], [status, wet ? "alert" : undefined]]);
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

      controllerRef.current = {
        setStage(stage, hand, exact) {
          const now = performance.now();
          if (hasApplied && hand === appliedHand) {
            if (stage === appliedStage) return;
            if (!exact && now - appliedAt < PAINT_INTERVAL_MS && Math.abs(stage - appliedStage) < PAINT_STAGE_STEP_M) return;
          }
          hasApplied = true;
          appliedStage = stage;
          appliedHand = hand;
          appliedAt = now;
          if (water && hand) {
            const lut = buildDepthLut(stage, m.hand.step_m, LITTLE_ENDIAN, water.spareLut);
            if (!lutEquals(water.lastLut, lut)) {
              paintDepth(hand.codes, hand.candidates, lut, water.pixels);
              water.context.putImageData(water.image, 0, 0);
              water.spareLut = water.lastLut ?? new Uint32Array(256);
              water.lastLut = lut;
            }
          }
          for (const entry of roads) {
            const state = roadState(entry.h, stage, m.impassable_depth_m);
            if (state !== entry.state) {
              entry.layer.setStyle(ROAD_STYLES[state]);
              entry.state = state;
            }
          }
          for (const entry of facilities) {
            const wet = facilityWet(entry.props, stage);
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
        setWaterOpacity(opacity) {
          water?.overlay.setOpacity(opacity);
        },
        setVisibility(tambons, roadsVisible, facilitiesVisible) {
          for (const [group, visible] of [[tambonGroup, tambons], [roadGroup, roadsVisible], [facilityGroup, facilitiesVisible]] as const) {
            if (visible && !map.hasLayer(group)) group.addTo(map);
            if (!visible && map.hasLayer(group)) group.remove();
          }
        },
        refreshTooltips,
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
      controllerRef.current = null;
      setMapReady(false);
      mounted?.stop();
      mounted?.remove();
    };
  }, [data]);

  // --- Map updates ------------------------------------------------------------------------------
  // Playback repaints are throttled; pausing, seeking and slider moves (playing === false) repaint exactly.
  useEffect(() => {
    if (mapReady) controllerRef.current?.setStage(stage, hand, !playing);
  }, [mapReady, hand, stage, playing]);

  useEffect(() => {
    if (mapReady) controllerRef.current?.showImagery(activeImagery, reducedMotion);
  }, [mapReady, activeImagery, reducedMotion]);

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
    return (
      <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
        {header}
        <div className={styles.container}>
          {intro}
          <div className={styles.errorBox} role="alert">
            <h2>{t("The replay data could not be loaded.", "โหลดข้อมูลการย้อนดูเหตุการณ์ไม่สำเร็จ")}</h2>
            <p>{t("Check your connection and try again. No figures are shown without their source data.", "ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง ระบบจะไม่แสดงตัวเลขใดหากไม่มีข้อมูลต้นทาง")}</p>
            <button type="button" className={styles.button} onClick={() => { setLoad({ status: "loading" }); setHandFailed(false); setHand(null); setReloadKey((key) => key + 1); }}>
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

  const imageryLabel = (id: string): string => {
    if (id === "auto") return t("Auto — latest optical image at this moment", "อัตโนมัติ — ภาพเชิงแสงล่าสุด ณ ช่วงเวลานี้");
    if (id === "none") return t("None (basemap only)", "ไม่แสดงภาพ (แผนที่ฐานเท่านั้น)");
    if (id === "hillshade") return t("Terrain (hillshade)", "ภูมิประเทศ (แสงเงา)");
    if (id === "s1-change") return t("Radar change (6 → 16 Sep)", "การเปลี่ยนแปลงเรดาร์ (6 → 16 ก.ย.)");
    return observationById.get(id)?.observation.label[lang] ?? id;
  };

  let caption = "";
  if (activeImagery && observationById.has(activeImagery)) {
    const entry = observationById.get(activeImagery)!;
    caption = `${entry.observation.label[lang]} · ${formatAge(time - entry.at, lang)}`;
  } else if (activeImagery === "s1-change") {
    caption = t(`Sentinel-1 radar change · ${radarSpan} (different orbit directions)`, `การเปลี่ยนแปลงเรดาร์ Sentinel-1 · ${radarSpan} (ทิศทางวงโคจรต่างกัน)`);
  } else if (activeImagery === "hillshade") {
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
  const confidenceText = manifest ? (isLowConfidence ? t("low", "ต่ำ") : manifest.confidence) : "";

  return (
    <main id="main-content" className={`studio-page ${styles.page}`} lang={language}>
      {header}
      <div className={styles.container}>
        {intro}
        <div className={styles.layout}>
          <section className={styles.stage} aria-label={t("Flood replay map and timeline", "แผนที่และเส้นเวลาการย้อนดูน้ำท่วม")}>
            <div className={styles.toolbar}>
              <label className={styles.field}>
                <span>{t("Imagery", "ภาพพื้นหลัง")}</span>
                <select value={imagery} onChange={(event) => setImagery(event.target.value)} disabled={!manifest}>
                  {IMAGERY_ORDER.map((id) => <option key={id} value={id}>{imageryLabel(id)}</option>)}
                </select>
              </label>
              <label className={styles.field}>
                <span>{t("Reconstructed water (model) opacity", "ความทึบของน้ำที่จำลอง (แบบจำลอง)")} · {Math.round(waterOpacity * 100)}%</span>
                <input type="range" min={0} max={1} step={0.05} value={waterOpacity} onChange={(event) => setWaterOpacity(Number(event.target.value))} />
              </label>
              <fieldset className={styles.toggles}>
                <legend>{t("Show", "แสดง")}</legend>
                <label><input type="checkbox" checked={showTambons} onChange={(event) => setShowTambons(event.target.checked)} /> {t("Subdistricts", "ขอบเขตตำบล")}</label>
                <label><input type="checkbox" checked={showRoads} onChange={(event) => setShowRoads(event.target.checked)} /> {t("Roads", "ถนน")}</label>
                <label><input type="checkbox" checked={showFacilities} onChange={(event) => setShowFacilities(event.target.checked)} /> {t("Candidate facilities", "สถานที่สำคัญที่เป็นไปได้")}</label>
              </fieldset>
            </div>

            <div className={styles.mapFrame}>
              <div ref={mapElement} className={styles.map} role="region" aria-label={t("Map of Mae Sai with imagery, reconstructed water, roads and candidate facilities", "แผนที่แม่สายพร้อมภาพดาวเทียม น้ำที่จำลอง ถนน และสถานที่สำคัญที่เป็นไปได้")} />
              {manifest && <p className={styles.caption}>{caption}</p>}
              {(!mapReady || (!hand && !handFailed)) && (
                <p className={styles.mapStatus} role="status">
                  {!mapReady ? t("Loading the replay…", "กำลังโหลดการย้อนดูเหตุการณ์…") : t("Preparing the water model…", "กำลังเตรียมแบบจำลองน้ำ…")}
                </p>
              )}
              {handFailed && <p className={`${styles.mapStatus} ${styles.mapWarning}`} role="alert">{t("The water model could not be loaded; imagery, roads and figures remain available.", "โหลดแบบจำลองน้ำไม่สำเร็จ แต่ยังดูภาพ ถนน และตัวเลขได้")}</p>}
            </div>

            {manifest && derived && (
              <div className={styles.dock}>
                <div className={styles.dockTop}>
                  <button type="button" className={styles.play} onClick={togglePlay} aria-keyshortcuts="Space">
                    <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>
                    {playing ? t("Pause", "หยุดชั่วคราว") : time >= TIMELINE_END_T - 1e-6 ? t("Replay", "เล่นอีกครั้ง") : t("Play", "เล่น")}
                  </button>
                  <div className={styles.readout}>
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
                      return (
                        <span key={item.id} className={styles.segment} data-active={active || undefined}
                          style={{
                            left: `${(start / TIMELINE_END_T) * 100}%`,
                            width: `${((end - start) / TIMELINE_END_T) * 100}%`,
                            background: active ? colour : tint(colour, 0.45),
                            color: active && item.id === "peak" ? "#fff" : PHASE_TEXT_DARK,
                          }}>
                          {item.label[lang]}
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

            <TimelineLegend language={lang} unmodelledRoads={!!derived?.hasUnmodelledRoads} unmodelledFacilities={!!derived?.hasUnmodelledFacilities} />
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
                  <p className={styles.muted}>{t(`Assumed river stage ${stage.toFixed(2)} m above the mapped channel (illustrative, not a gauge reading).`, `ระดับน้ำสมมุติ ${stage.toFixed(2)} ม. เหนือร่องน้ำ (เพื่อการอธิบาย ไม่ใช่ค่าจากสถานีวัดน้ำ)`)}</p>
                </div>

                <ImpactCard manifest={manifest} stats={stats} derived={derived} language={lang} />

                <WetFacilitiesCard facilities={derived.facilityProps} stage={stage} language={lang} />

                <div className={styles.card}>
                  <h2>{t("Evidence for this moment", "หลักฐานของช่วงเวลานี้")}</h2>
                  <dl className={styles.evidence}>
                    <div><dt>{t("Imagery", "ภาพ")}</dt><dd>{caption}</dd></div>
                    {gap && <div><dt>{t("Image gap", "ช่วงไม่มีภาพ")}</dt><dd>{gapText}</dd></div>}
                    <div><dt>{t("Water", "น้ำ")}</dt><dd>{t("Model reconstruction from terrain (height above nearest drainage) at the assumed stage — not an observation.", "การจำลองจากภูมิประเทศ (ความสูงเหนือร่องน้ำที่ใกล้ที่สุด) ที่ระดับน้ำสมมุติ — ไม่ใช่การสังเกตการณ์จริง")}</dd></div>
                    <div><dt>{t("Confidence", "ความเชื่อมั่น")}</dt><dd><span className={styles.confidence}>{isLowConfidence ? t("LOW", "ต่ำ") : manifest.confidence}</span> <Localized text={manifest.confidence_reason} language={lang} /></dd></div>
                  </dl>
                  <RadarCheck manifest={manifest} radarSpan={radarSpan} language={lang} />
                </div>

                <details className={styles.card}>
                  <summary>{t("Sources, assumptions and limits", "แหล่งข้อมูล สมมติฐาน และข้อจำกัด")}</summary>
                  {lang === "th" && <p className={styles.muted}>รายละเอียดด้านล่างคงไว้เป็นภาษาอังกฤษตามต้นฉบับ</p>}
                  <h3>{t("Sources", "แหล่งข้อมูล")}</h3>
                  <ul className={styles.list} lang="en">
                    {manifest.sources.map((source) => (
                      <li key={source.id}><strong>{source.name}</strong> — {source.licence}. {source.attribution}. <span className={styles.muted}>{source.timestamp}</span></li>
                    ))}
                  </ul>
                  <h3>{t("Assumptions", "สมมติฐาน")}</h3>
                  <ul className={styles.list} lang="en">{manifest.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
                  <h3>{t("Limitations", "ข้อจำกัด")}</h3>
                  <ul className={styles.list} lang="en">{manifest.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                  <p className={styles.muted}>
                    {t("Source timestamp", "เวลาของข้อมูลต้นทาง")}: {manifest.source_timestamp} · {manifest.timezone} · {manifest.study_id} {manifest.revision} · {t("confidence", "ความเชื่อมั่น")}: {confidenceText}
                  </p>
                </details>
              </>
            )}
          </aside>
        </div>
        <footer className={styles.footer}>{t(
          "FloodGuard supports preparedness and rapid post-event prioritisation. This replay is a report-only reconstruction and does not feed the planning decision layer.",
          "FloodGuard สนับสนุนการเตรียมพร้อมและการจัดลำดับความสำคัญอย่างรวดเร็วหลังเกิดเหตุ การย้อนดูนี้เป็นการจำลองเพื่อรายงานเท่านั้น และไม่ถูกนำไปใช้ในส่วนตัดสินใจเพื่อการวางแผน",
        )}</footer>
      </div>
    </main>
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

export function TimelineLegend({ language, unmodelledRoads, unmodelledFacilities }: { language: Language; unmodelledRoads: boolean; unmodelledFacilities: boolean }) {
  const th = language === "th";
  return (
    <div className={styles.legend} aria-label={th ? "คำอธิบายสัญลักษณ์" : "Legend"} role="group">
      <div>
        <strong>{th ? "ความลึกของน้ำ (แบบจำลอง)" : "Water depth (model)"}</strong>
        <ul>
          {DEPTH_CLASSES.map((item) => <li key={item.label}><i style={{ background: rgbaCss(item.rgba) }} />{item.label.replace(" m", th ? " ม." : " m")}</li>)}
          <li><i style={{ background: rgbaCss(CHANNEL_RGBA) }} />{th ? "ร่องน้ำ/แม่น้ำ" : "River channel"}</li>
        </ul>
      </div>
      <div>
        <strong>{th ? "ถนน" : "Roads"}</strong>
        <ul>
          <li><i className={styles.line} style={{ background: ROAD_STYLES.dry.color }} />{th ? "แห้ง" : "Dry"}</li>
          <li><i className={styles.line} style={{ background: ROAD_STYLES.wet.color }} />{th ? "มีน้ำ < 0.3 ม." : "Wet < 0.3 m"}</li>
          <li><i className={styles.line} style={{ background: ROAD_STYLES.impassable.color }} />{th ? "สัญจรไม่ได้ ≥ 0.3 ม." : "Impassable ≥ 0.3 m"}</li>
          {unmodelledRoads && <li><i className={styles.dash} style={{ borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
        </ul>
      </div>
      <div>
        <strong>{th ? "สถานที่สำคัญที่เป็นไปได้ (ข้อมูล OSM)" : "Candidate facilities (OSM)"}</strong>
        <ul>
          <li><i className={styles.dot} style={{ background: "#fff", borderColor: "#0c2740" }} />{th ? "แห้ง" : "Dry"}</li>
          <li><i className={styles.dot} style={{ background: "#c62828", borderColor: "#fff" }} />{th ? "อยู่ในน้ำ" : "In water"}</li>
          {unmodelledFacilities && <li><i className={styles.dot} style={{ background: "transparent", borderColor: NOT_MODELLED_GREY }} />{th ? "ไม่ได้จำลอง (นอกพื้นที่แบบจำลอง)" : "Not modelled (outside the model area)"}</li>}
        </ul>
      </div>
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
        <span>{th ? "ระดับน้ำในแม่น้ำเหนือร่องน้ำที่สมมุติ (ม.) — เพื่อการอธิบาย" : "Assumed river stage above channel (m) — illustrative"}</span>
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
