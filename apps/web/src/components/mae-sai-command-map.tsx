"use client";

/**
 * The map of the Command exercise replay (Mae Sai, September 2024): a pale full-screen Leaflet map under the page's
 * floating panels. It draws the modelled water of the replay hour in two tones of one blue (hatched where confidence
 * is lowest), a grey veil outside the eight subdistricts, the roads in four line styles, the subdistrict outlines with
 * their Thai-first names, the shelters reported in use in 2024 and the district command centre, and the reports: the
 * 2024 place records, the invented items of the exercise and the sign of the reports saved on this device. In
 * hindsight mode it also draws the 2024 season envelope, a scenario layer that is not an observation for any replay hour.
 *
 * Everything that follows the replay hour is a T1 scenario (model) with low confidence. The map moves only when the
 * reader asks: every fit, zoom and popup stays inside the clear rectangle the page measures between its panels.
 */

import type { CircleMarker, GeoJSONOptions, ImageOverlay, LatLng, LatLngBoundsExpression, Layer, Map as LeafletMap, Marker, Path, PathOptions, Polyline, Renderer } from "leaflet";
import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";

import { FACTOR_LUT_SIZE, facilityWet, formatDateWithYear, lutEquals, paintDepth, paintLowConfidence, projectToFrame, type FacilityProps, type Language, type ReportedShelter, type RoadProps } from "@/lib/flood-timeline";
import { COMMAND_CREDITS, COMMAND_FIGURES, COMMAND_MAP, commandFacilityType, commandSiteGroupTitle, commandText } from "@/lib/flood-timeline-command-copy";
import type { CommandHandRaster, CommandReplayData } from "@/lib/flood-timeline-command-data";
import { reportedSiteHour } from "@/lib/flood-timeline-command-feed";
import { CLUSTER_BELOW_ZOOM, modelDepthAt } from "@/lib/flood-timeline-command-incidents";
import {
  areaBounds,
  areaLabelPoint,
  areaPolygons,
  buildTwoToneFactorLut,
  buildTwoToneLut,
  cellsInMask,
  commandRoadRank,
  commandRoadStyle,
  metresPerPixel,
  outsideLabelPoint,
  pointsBounds,
  reportedSiteWetAt,
  veilRings,
  type CommandRoadRank,
  type CommandRoadStyle,
  type LatLngBox,
} from "@/lib/flood-timeline-command-map";
import { COMMAND_MARKERS } from "@/lib/flood-timeline-command-reports-copy";
import type { CommandFindTarget } from "@/lib/flood-timeline-command-table";
import { envelopeHatch, paintEnvelope } from "@/lib/flood-timeline-envelope";
import { countedInReportedSet, reportedSiteRole } from "@/lib/flood-timeline-evacuation";
import { groupNearbyPlaces } from "@/lib/flood-timeline-reported-depths";
import { clearRectPadding, panIntoRect, popupFitInRect, type ScreenRect } from "@/lib/flood-timeline-layout";

import { mountCommandMarkers, type CommandMarkerFrame, type CommandReportAction, type CommandReportSelection } from "./mae-sai-command-markers";
import { createCanvasOverlay, keyboardPopups, MAP_POPUP_FRAME_CLASS, popupElement, tooltipElement, type PopupLine } from "./mae-sai-map-kit";
import styles from "./mae-sai-command-exercise.module.css";

/** During playback the map repaints at most this often, unless the stage has moved by PAINT_STAGE_STEP_M (as on the Studio replay). */
const PAINT_INTERVAL_MS = 120;
const PAINT_STAGE_STEP_M = 0.1;
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
/** How far past the replay area the map may be panned: the panels cover up to half of the screen beside the district. */
const MAP_BOUNDS_PAD = 1.6;
const POPUP_WIDTH = 300;
/** Margin around the town's points when the map shows the town (about 500 m). */
const TOWN_PAD_DEG = 0.0045;
const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;

export type CommandBasemap = "street" | "terrain";
export type CommandFitTarget = "town" | "district";

/** A place the find-place box shows on the map: where it is, its name and the lines under the name. */
export interface CommandMapPlace {
  target: Exclude<CommandFindTarget, { type: "tambon" }>;
  title: string;
  lines: readonly string[];
}

/** What the page can ask of the map. */
export interface CommandMapHandle {
  zoomBy: (delta: number) => void;
  fit: (target: CommandFitTarget) => void;
  /** Fit one subdistrict inside the clear rectangle. */
  fitTambon: (id: string) => void;
  /** Mark a found place and, when asked, bring it inside the clear rectangle; null takes the mark away. */
  showPlace: (place: CommandMapPlace | null, fit?: boolean) => void;
  /** Bring a selected report inside the clear rectangle, so it is never under a panel. */
  focusReport: (selection: CommandReportSelection) => void;
  /** Close the open popup, if there is one; true when one was closed (Escape then does nothing else). */
  closePopup: () => boolean;
}

/** The 2024 season envelope as the map draws it in hindsight mode: its cells on the water grid, and its short credit. */
export interface CommandEnvelopeLayer { cells: Uint32Array; credit: string }

/** The scale of the map as the page prints it under the scale bar. */
export interface CommandMapView { metresPerPixel: number; zoom: number }

interface MapFrame { stage: number; hour: number; hand: CommandHandRaster | null }
interface MapController {
  update: (frame: MapFrame, exact: boolean) => void;
  setSelected: (id: string | null) => void;
  setBasemap: (basemap: CommandBasemap, fallback: boolean) => void;
  setFacilities: (visible: boolean) => void;
  setReports: (frame: CommandMarkerFrame) => void;
  setEnvelope: (envelope: CommandEnvelopeLayer | null) => void;
  refreshText: () => void;
}
interface RoadEntry { layer: Path; props: RoadProps; style: CommandRoadStyle; rank: CommandRoadRank; casing: Path | null }
interface FacilityEntry { layer: CircleMarker; props: FacilityProps; wet: boolean }

/**
 * Line styles per road state, at the district zoom and closer in. Red is used for impassable roads only, and it is
 * used sparingly: a through road or a named road (major) keeps a heavy line, the other streets (minor) a thin one, so
 * a flooded town reads as a net of lines over the water and not as one red patch. Flat line ends keep the pieces from
 * swelling where they meet.
 */
const ROAD_STYLES: Record<"far" | "near", Record<CommandRoadRank, Record<CommandRoadStyle, PathOptions>>> = {
  far: {
    major: {
      dry: { color: "#98a3a4", weight: 1, opacity: 0.8, dashArray: undefined, lineCap: "butt" },
      wet: { color: "#d98a1e", weight: 1.8, opacity: 1, dashArray: "5 4", lineCap: "butt" },
      impassable: { color: "#c62f24", weight: 2.2, opacity: 1, dashArray: undefined, lineCap: "butt" },
      unmodelled: { color: "#98a3a4", weight: 1.4, opacity: 1, dashArray: "1 5", lineCap: "butt" },
    },
    minor: {
      dry: { color: "#98a3a4", weight: 0.7, opacity: 0.7, dashArray: undefined, lineCap: "butt" },
      wet: { color: "#d98a1e", weight: 1.2, opacity: 1, dashArray: "4 4", lineCap: "butt" },
      impassable: { color: "#c62f24", weight: 1.2, opacity: 0.95, dashArray: undefined, lineCap: "butt" },
      unmodelled: { color: "#98a3a4", weight: 1.1, opacity: 1, dashArray: "1 5", lineCap: "butt" },
    },
  },
  near: {
    major: {
      dry: { color: "#98a3a4", weight: 1.5, opacity: 0.85, dashArray: undefined, lineCap: "butt" },
      wet: { color: "#d98a1e", weight: 2.6, opacity: 1, dashArray: "7 5", lineCap: "butt" },
      impassable: { color: "#c62f24", weight: 3.2, opacity: 1, dashArray: undefined, lineCap: "butt" },
      unmodelled: { color: "#98a3a4", weight: 1.8, opacity: 1, dashArray: "1 6", lineCap: "butt" },
    },
    minor: {
      dry: { color: "#98a3a4", weight: 1.1, opacity: 0.8, dashArray: undefined, lineCap: "butt" },
      wet: { color: "#d98a1e", weight: 1.8, opacity: 1, dashArray: "6 5", lineCap: "butt" },
      impassable: { color: "#c62f24", weight: 2.1, opacity: 1, dashArray: undefined, lineCap: "butt" },
      unmodelled: { color: "#98a3a4", weight: 1.5, opacity: 1, dashArray: "1 6", lineCap: "butt" },
    },
  },
};
/** A major road that is impassable lies on a thin white casing, so its red line keeps an edge over the water. */
const CASING_EXTRA_PX = 1.5;
/** From this zoom on the roads take the heavier line weights. */
const NEAR_ZOOM = 13;
const FACILITY_STYLES = {
  dry: { radius: 4.5, color: "#12262d", weight: 1.4, fillColor: "#ffffff", fillOpacity: 1 },
  wet: { radius: 5.5, color: "#ffffff", weight: 1.8, fillColor: "#2f86c4", fillOpacity: 1 },
  unmodelled: { radius: 4.5, color: "#98a3a4", weight: 1.6, fillColor: "#ffffff", fillOpacity: 0 },
} as const;

const STAR_PATH = "M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5L7 14.3l-5.3-5 7.2-.9z";
const DIAMOND_PATH = "M12 2.5l9.5 9.5-9.5 9.5L2.5 12z";
/**
 * A reported shelter is a star. One whose mapped point is in modelled water at this hour is a hollow star struck
 * through; in trainee mode, one no source has reported yet at the replay hour is a dashed outline (by its class).
 */
const starIcon = (size: number, wet: boolean): string =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false"><path d="${STAR_PATH}"/>${wet ? '<path data-part="slash" d="M3.5 21 20.5 3"/>' : ""}</svg>`;
const diamondIcon = (size: number): string => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false"><path d="${DIAMOND_PATH}"/></svg>`;
/** Below this zoom (the district view) the signs of the reported sites are small, and sites that would cover each other share one count. */
const SITE_FAR_BELOW_ZOOM = 12.5;
const SITE_MERGE_PX = 24;

/** "15 Sep 2024", or "15 Sep 2024 or earlier" for a bound; the text itself when it is not a date. */
function firstUseText(value: string, language: Language): string {
  const match = /^(\d{4}-\d{2}-\d{2})( or earlier)?$/.exec(value);
  if (!match) return value;
  const date = formatDateWithYear(match[1], language);
  if (!match[2]) return date;
  return language === "th" ? `${date} หรือก่อนหน้านั้น` : `${date} or earlier`;
}

/** Two-line label built from text nodes: the Thai name first, the romanised name smaller under it. */
function placeLabel(thai: string, roman: string): HTMLElement {
  const root = document.createElement("div");
  root.className = styles.placeLabel;
  const first = document.createElement("span");
  first.lang = "th";
  first.textContent = thai;
  const second = document.createElement("span");
  second.lang = "en";
  second.textContent = roman;
  root.append(first, second);
  return root;
}

export function MaeSaiCommandMap({ data, hand, hour, stage, playing, language, basemap, facilities, selected = null, reports = null, envelope = null, getClear, reducedMotion, onReady, onBasemapIssue, onView, onReportAction, onWatermarkPane, handle }: {
  data: CommandReplayData;
  /** The terrain raster of the water layer; null until it has loaded (the roads and the figures do not wait for it). */
  hand: CommandHandRaster | null;
  hour: number;
  /** Assumed river stage (m) at the replay hour. */
  stage: number;
  playing: boolean;
  language: Language;
  basemap: CommandBasemap;
  /** The 42 key facilities are hidden until the reader asks for them. */
  facilities: boolean;
  /** The subdistrict selected in the table: it is outlined on the map. */
  selected?: string | null;
  /** The reports on the map at this replay hour: place records, invented items and the signs of this device; null until they are known. */
  reports?: CommandMarkerFrame | null;
  /** The 2024 season envelope (a scenario layer): drawn in hindsight mode only, so null in trainee mode. */
  envelope?: CommandEnvelopeLayer | null;
  /** The clear rectangle between the page's panels, in the map's own pixels, measured when it is asked for. */
  getClear: () => ScreenRect;
  reducedMotion: boolean;
  onReady?: () => void;
  /** True while the street tiles fail to load: the terrain shading is shown in their place. */
  onBasemapIssue?: (issue: boolean) => void;
  onView?: (view: CommandMapView) => void;
  /** "Assign" or "Details" was pressed in the popup of an invented item or of a device sign. */
  onReportAction?: (selection: CommandReportSelection, action: CommandReportAction) => void;
  /**
   * The layer of the map that holds the exercise watermark: above the water and the roads, under the names, the
   * markers and the popups, and fixed to the screen while the map moves. The page draws the watermark into it; null
   * when the map goes away.
   */
  onWatermarkPane?: (pane: HTMLElement | null) => void;
  handle?: Ref<CommandMapHandle>;
}) {
  const element = useRef<HTMLDivElement | null>(null);
  const controller = useRef<MapController | null>(null);
  const mapHandle = useRef<CommandMapHandle | null>(null);
  const [ready, setReady] = useState(false);
  const [tileIssue, setTileIssue] = useState(false);
  const languageRef = useRef(language);
  const clearRef = useRef(getClear);
  const motionRef = useRef(reducedMotion);
  const callbacks = useRef({ onReady, onBasemapIssue, onView, onReportAction, onWatermarkPane });
  useEffect(() => {
    languageRef.current = language;
    clearRef.current = getClear;
    motionRef.current = reducedMotion;
    callbacks.current = { onReady, onBasemapIssue, onView, onReportAction, onWatermarkPane };
  });
  useImperativeHandle(handle, () => ({
    zoomBy: (delta) => mapHandle.current?.zoomBy(delta),
    fit: (target) => mapHandle.current?.fit(target),
    fitTambon: (id) => mapHandle.current?.fitTambon(id),
    showPlace: (place, fit) => mapHandle.current?.showPlace(place, fit),
    focusReport: (selection) => mapHandle.current?.focusReport(selection),
    closePopup: () => mapHandle.current?.closePopup() ?? false,
  }), []);

  // --- Mount -------------------------------------------------------------------------------------------
  useEffect(() => {
    const { manifest: m } = data;
    let disposed = false;
    let mounted: LeafletMap | null = null;
    let resizeObserver: ResizeObserver | undefined;
    let removeMapKeys: (() => void) | undefined;
    let removeMarkers: (() => void) | undefined;
    let removeFocusPan: (() => void) | undefined;

    async function mount() {
      const L = await import("leaflet");
      if (disposed || !element.current) return;
      element.current.replaceChildren();
      // The page's own keys step the replay, so the map takes no arrow keys; its zoom buttons are in the tool rail.
      const map = L.map(element.current, { zoomControl: false, attributionControl: false, keyboard: false, zoomSnap: 0.25, maxZoom: 17 });
      mounted = map;
      const thai = () => languageRef.current === "th";
      const text = (entry: { en: string; th: string }) => commandText(entry, languageRef.current);
      const size = () => {
        const { x, y } = map.getSize();
        return { width: x, height: y };
      };
      const padding = () => clearRectPadding(clearRef.current(), size());

      const modelBounds = L.latLngBounds(m.bounds);
      const geometries = data.tambons.features.map((feature) => feature.geometry);
      const districtBox: LatLngBox = areaBounds(geometries) ?? m.bounds;
      // The town: the places news reported water at in 2024 and the district command centre, with about 500 m around them.
      const centre = m.shelters?.reported.find((site) => reportedSiteRole(site).role === "relief_command" && site.lat !== null && site.lon !== null);
      const townPoints: [number, number][] = [
        ...(m.reported_depths?.reports ?? []).flatMap((report) => (report.point ? [[report.point.lat, report.point.lon] as [number, number]] : [])),
        ...(centre ? [[centre.lat!, centre.lon!] as [number, number]] : []),
      ];
      const townBox: LatLngBox = pointsBounds(townPoints, TOWN_PAD_DEG) ?? districtBox;
      const fitTo = (box: LatLngBox, animate: boolean) => {
        map.invalidateSize();
        map.fitBounds(box as LatLngBoundsExpression, { ...padding(), animate, maxZoom: 16 });
      };
      map.setMaxBounds(L.latLngBounds(districtBox[0], districtBox[1]).pad(MAP_BOUNDS_PAD));
      fitTo(districtBox, false);
      map.setMinZoom(Math.max(8, map.getZoom() - 1.5));

      for (const [name, zIndex] of [
        ["fg-imagery", 250], ["fg-water", 350], ["fg-envelope", 352], ["fg-veil", 370], ["fg-tambons", 380], ["fg-highlight", 390], ["fg-roads", 400],
        ["fg-selection", 430], ["fg-labels", 440], ["fg-facilities", 450], ["fg-shelters", 460], ["fg-reported-depths", 462],
      ] as const) {
        const pane = map.createPane(name);
        pane.style.zIndex = String(zIndex);
        pane.style.pointerEvents = "none";
      }
      // The exercise watermark: over the water and the roads, under the names, the markers, the tooltips and the
      // popups, so it never runs across a name or the text of a popup. The pane is as large as the map and is moved
      // back to the corner of the screen whenever the map moves, so the watermark stays where it is.
      const watermarkPane = map.createPane("fg-watermark");
      watermarkPane.style.zIndex = "436";
      watermarkPane.style.pointerEvents = "none";
      const placeWatermark = () => {
        const { x, y } = map.getSize();
        watermarkPane.style.width = `${x}px`;
        watermarkPane.style.height = `${y}px`;
        L.DomUtil.setPosition(watermarkPane, map.containerPointToLayerPoint([0, 0]));
      };
      map.on("move zoom zoomend viewreset resize", placeWatermark);
      placeWatermark();
      callbacks.current.onWatermarkPane?.(watermarkPane);

      // --- Basemap: grey street tiles (online only), with the terrain shading of the replay data under the water
      // whenever the tiles are not there.
      const tiles = L.tileLayer(OSM_TILES, { attribution: COMMAND_CREDITS.osm, maxZoom: 19, opacity: 0.55, referrerPolicy: "strict-origin", className: styles.basemapTiles }).addTo(map);
      tiles.on("tileerror", () => setTileIssue(true));
      tiles.on("tileload", () => setTileIssue(false));
      const terrain = m.layers.find((layer) => layer.kind === "terrain");
      const hillshade: ImageOverlay | null = terrain
        ? L.imageOverlay(terrain.href, modelBounds, { pane: "fg-imagery", opacity: 0, className: styles.hillshade, alt: "", attribution: COMMAND_CREDITS.terrain }).addTo(map)
        : null;
      // The shading is shown inside the eight subdistricts only, like the water: its image is masked with their
      // outlines (in the image's own frame), so no edge of the image shows through the veil.
      const shade = hillshade?.getElement();
      if (shade) {
        const outline = geometries.flatMap((geometry) => areaPolygons(geometry).map((rings) => `${(rings[0] ?? []).map(([lon, lat], index) => {
          const [x, y] = projectToFrame(lon, lat, m.bounds, 1000, 1000);
          return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
        }).join("")}Z`)).join("");
        const mask = `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" preserveAspectRatio="none"><path d="${outline}"/></svg>`)}")`;
        shade.style.maskImage = mask;
        shade.style.maskSize = "100% 100%";
        shade.style.maskRepeat = "no-repeat";
        shade.style.setProperty("-webkit-mask-image", mask);
        shade.style.setProperty("-webkit-mask-size", "100% 100%");
        shade.style.setProperty("-webkit-mask-repeat", "no-repeat");
      }

      // --- Modelled water: one canvas on the terrain grid, repainted through a lookup table per replay hour.
      const canvas = document.createElement("canvas");
      canvas.width = m.hand.width;
      canvas.height = m.hand.height;
      const context = canvas.getContext("2d");
      const image = context?.createImageData(canvas.width, canvas.height) ?? null;
      const pixels = image ? new Uint32Array(image.data.buffer) : null;
      if (context) createCanvasOverlay(L, canvas, modelBounds, { pane: "fg-water", opacity: 1, className: styles.waterLayer }).addTo(map);
      // The water is drawn inside the eight subdistricts only: the figures count nothing outside them, and the veil
      // there says "not modelled". The subdistricts are rasterised once on the terrain grid (linear in Web Mercator,
      // like the overlay) and the wet-able cells outside them are dropped.
      const districtMask = (() => {
        const maskCanvas = document.createElement("canvas");
        maskCanvas.width = m.hand.width;
        maskCanvas.height = m.hand.height;
        const maskContext = maskCanvas.getContext("2d", { willReadFrequently: true });
        if (!maskContext) return null;
        maskContext.fillStyle = "#000000";
        for (const geometry of geometries) {
          for (const rings of areaPolygons(geometry)) {
            maskContext.beginPath();
            for (const ring of rings) {
              ring.forEach(([lon, lat], index) => {
                const [x, y] = projectToFrame(lon, lat, m.bounds, maskCanvas.width, maskCanvas.height);
                if (index === 0) maskContext.moveTo(x, y);
                else maskContext.lineTo(x, y);
              });
              maskContext.closePath();
            }
            maskContext.fill("evenodd");
          }
        }
        return maskContext.getImageData(0, 0, maskCanvas.width, maskCanvas.height).data;
      })();
      const clipped = new WeakMap<CommandHandRaster, { candidates: Uint32Array; lowCells: Uint32Array | null; lowStripes: Uint8Array | null }>();
      const clip = (raster: CommandHandRaster) => {
        let entry = clipped.get(raster);
        if (!entry) {
          if (districtMask) {
            const low = raster.lowCells ? cellsInMask(raster.lowCells, districtMask, 4, 3, raster.lowStripes) : null;
            entry = { candidates: cellsInMask(raster.candidates, districtMask, 4, 3).cells, lowCells: low?.cells ?? null, lowStripes: low?.parallel ?? null };
          } else {
            entry = { candidates: raster.candidates, lowCells: raster.lowCells, lowStripes: raster.lowStripes };
          }
          clipped.set(raster, entry);
        }
        return entry;
      };
      let lastLut: Uint32Array | null = null;
      let spareLut: Uint32Array | null = null;
      let lastHand: CommandHandRaster | null = null;
      const paintWater = (raster: CommandHandRaster, frame: MapFrame) => {
        if (!context || !image || !pixels) return;
        const cells = clip(raster);
        const factor = raster.factorKeys !== null;
        const length = factor ? FACTOR_LUT_SIZE : 256;
        const buffer = spareLut && spareLut.length === length ? spareLut : new Uint32Array(length);
        const lut = factor
          ? buildTwoToneFactorLut(frame.stage, m.hand.step_m, m.impassable_depth_m, LITTLE_ENDIAN, buffer)
          : buildTwoToneLut(frame.stage, m.hand.step_m, m.impassable_depth_m, LITTLE_ENDIAN, buffer);
        if (lastHand === raster && lutEquals(lastLut, lut)) {
          spareLut = lut;
          return;
        }
        if (lastHand !== raster) pixels.fill(0);
        paintDepth(raster.factorKeys ?? raster.codes, cells.candidates, lut, pixels);
        // Wet cells on filled pits and dead-flat ground are washed out and hatched: the lowest confidence of the layer.
        if (cells.lowCells && cells.lowStripes) paintLowConfidence(cells.lowCells, cells.lowStripes, pixels, LITTLE_ENDIAN);
        context.putImageData(image, 0, 0);
        spareLut = lastLut;
        lastLut = lut;
        lastHand = raster;
      };

      // --- The veil outside the eight subdistricts: what lies under it is not modelled.
      const veil = veilRings(geometries);
      if (veil.length > 0) {
        L.polygon(veil, { pane: "fg-veil", renderer: L.svg({ pane: "fg-veil", padding: 0.6 }), stroke: false, fillColor: "#c9d1da", fillOpacity: 0.5, interactive: false }).addTo(map);
      }
      const labelIcon = (content: HTMLElement) => L.divIcon({ className: styles.labelIcon, html: content, iconSize: [0, 0] });
      const outside = outsideLabelPoint(geometries, m.bounds);
      const outsideLabel = document.createElement("div");
      outsideLabel.className = styles.outsideLabel;
      if (outside) L.marker([outside[1], outside[0]], { pane: "fg-labels", icon: labelIcon(outsideLabel), interactive: false, keyboard: false }).addTo(map);

      // --- Subdistrict outlines and their names (Thai first, at a point well inside each one).
      L.geoJSON(data.tambons as unknown as Parameters<typeof L.geoJSON>[0], {
        renderer: L.svg({ pane: "fg-tambons", padding: 0.6 }),
        interactive: false,
        style: () => ({ color: "#5f6f73", weight: 1.2, opacity: 0.9, dashArray: "6 5", fill: false }),
      } as GeoJSONOptions & { renderer: Renderer }).addTo(map);
      const labelPoints = data.tambons.features.map((feature) => ({ ...feature.properties, point: areaLabelPoint(feature.geometry) }));
      for (const { th, en, point } of labelPoints) {
        if (!point) continue;
        L.marker([point[1], point[0]], { pane: "fg-labels", icon: labelIcon(placeLabel(th, en)), interactive: false, keyboard: false }).addTo(map);
      }

      // --- Roads: one canvas, restyled piece by piece when the modelled state changes.
      const roads: RoadEntry[] = [];
      let roadScale: "far" | "near" = map.getZoom() >= NEAR_ZOOM ? "near" : "far";
      const roadRenderer = L.canvas({ pane: "fg-roads", padding: 0.5 });
      const roadGroup = L.geoJSON(data.roads as unknown as Parameters<typeof L.geoJSON>[0], {
        renderer: roadRenderer,
        interactive: false,
        style: (feature) => {
          const props = feature?.properties as RoadProps;
          return ROAD_STYLES[roadScale][commandRoadRank(props)][props.m ? "dry" : "unmodelled"];
        },
        onEachFeature: (feature, layer) => {
          const props = feature.properties as RoadProps;
          roads.push({ layer: layer as Path, props, style: props.m ? "dry" : "unmodelled", rank: commandRoadRank(props), casing: null });
        },
      } as GeoJSONOptions & { renderer: Renderer });
      // The white casing of a major road, drawn only while the road is impassable. The casings go on the map first,
      // so each lies under its road.
      const casingGroup = L.layerGroup();
      for (const entry of roads) {
        if (entry.rank !== "major" || !entry.props.m) continue;
        entry.casing = L.polyline((entry.layer as Polyline).getLatLngs() as LatLng[], { renderer: roadRenderer, interactive: false, stroke: false, color: "#ffffff", opacity: 0.92, weight: 0, lineCap: "butt" });
        casingGroup.addLayer(entry.casing);
      }
      casingGroup.addTo(map);
      roadGroup.addTo(map);
      const styleRoads = (stageNow: number, all: boolean) => {
        for (const entry of roads) {
          const style = commandRoadStyle(entry.props, stageNow, m.impassable_depth_m);
          if (!all && style === entry.style) continue;
          const options = ROAD_STYLES[roadScale][entry.rank][style];
          entry.casing?.setStyle({ stroke: style === "impassable", weight: (options.weight ?? 0) + CASING_EXTRA_PX });
          entry.layer.setStyle(options);
          // Wet and impassable pieces are drawn over the dry ones, each over its own casing.
          if (style !== entry.style && (style === "wet" || style === "impassable")) {
            entry.casing?.bringToFront();
            entry.layer.bringToFront();
          }
          entry.style = style;
        }
      };

      // --- Key facilities (hidden until asked for): dry or in modelled water.
      const facilityEntries: FacilityEntry[] = [];
      const tooltipLayers: Layer[] = [];
      let applied: MapFrame | null = null;
      let appliedAt = 0;
      const appliedStage = () => applied?.stage ?? 0;
      const facilityRenderer = L.svg({ pane: "fg-facilities" });
      const facilityGroup = L.geoJSON(data.facilities as unknown as Parameters<typeof L.geoJSON>[0], {
        pointToLayer: (feature, latlng) => {
          const props = feature.properties as FacilityProps;
          const marker = L.circleMarker(latlng, { ...(props.m ? FACILITY_STYLES.dry : FACILITY_STYLES.unmodelled), renderer: facilityRenderer, pane: "fg-facilities" });
          marker.bindTooltip(() => tooltipElement([
            [commandFacilityType(props.type, languageRef.current), "title"],
            [props.n || text(COMMAND_MAP.unnamed)],
            props.m
              ? [text(facilityWet(props, appliedStage()) ? COMMAND_MAP.wetNow : COMMAND_MAP.dryNow), "muted"]
              : [text(COMMAND_MAP.notModelled), "muted"],
          ]), { direction: "top", offset: [0, -6] });
          tooltipLayers.push(marker);
          if (props.m) facilityEntries.push({ layer: marker, props, wet: false });
          return marker;
        },
      });

      // --- The shelters reported in use in 2024 (stars) and the district command centre (diamond).
      let openPopups = 0;
      map.on("popupopen", () => { openPopups += 1; });
      map.on("popupclose", () => { openPopups = Math.max(0, openPopups - 1); });
      // Escape closes an open popup and does nothing else on that key press: the page's own Escape (clearing the
      // selection, leaving focus mode) waits for the next one.
      const { keyboardPopup, remove } = keyboardPopups(map, () => openPopups > 0, { consumeEscape: true });
      removeMapKeys = remove;
      // A marker that takes the keyboard focus is brought inside the clear rectangle, so its focus ring is never
      // under a panel. The pointer does not move the map: only focus that came from the keyboard does.
      const container = map.getContainer();
      const onMarkerFocus = (event: FocusEvent) => {
        const target = event.target instanceof HTMLElement ? event.target : null;
        if (!target?.classList.contains("leaflet-marker-icon") || !target.matches(":focus-visible")) return;
        const box = container.getBoundingClientRect();
        const rect = target.getBoundingClientRect();
        const pan = panIntoRect({ x: rect.left + rect.width / 2 - box.left, y: rect.top + rect.height / 2 - box.top }, clearRef.current(), 28);
        if (pan.x !== 0 || pan.y !== 0) map.panBy([pan.x, pan.y], { animate: !motionRef.current });
      };
      container.addEventListener("focusin", onMarkerFocus);
      removeFocusPan = () => container.removeEventListener("focusin", onMarkerFocus);
      // In trainee mode a site is known from the day of its first dated 2024 source: before it a shelter is a dashed
      // outline and the command centre is not on the map.
      const siteMarkers: { marker: Marker; site: ReportedShelter; command: boolean; wet: boolean; fromHour: number | null; pending: boolean; merged: boolean }[] = [];
      const sitePending = (site: ReportedShelter) => siteMarkers.find((entry) => entry.site === site)?.pending ?? false;
      const siteTitle = (site: ReportedShelter, command: boolean) => `${text(command ? COMMAND_MAP.commandCentre : COMMAND_MAP.shelter)}: ${thai() ? site.name_th : site.name_en}`;
      const sitePopup = (site: ReportedShelter, command: boolean) => {
        const lang = languageRef.current;
        const wet = reportedSiteWetAt(site, appliedStage());
        // The replay data's occupancy text without its own leading label: the page supplies a translated one.
        const occupancy = site.reported_capacity_or_occupancy?.replace(/^\s*occupancy\s*:\s*/i, "") || null;
        const lines: PopupLine[] = [
          { text: site.name_th, tone: "title", lang: "th" },
          { text: site.name_en, tone: "muted", lang: "en" },
          ...(sitePending(site) ? [{ text: text(COMMAND_MARKERS.siteNotYet), tone: "alert" as const }] : []),
          { text: `${text(command ? COMMAND_MAP.commandCentre : COMMAND_MAP.shelter)} · ${text(COMMAND_MAP.reported)}` },
          { text: `${text(COMMAND_MAP.firstUse)}: ${firstUseText(site.first_use, lang)}`, tone: "muted" },
          ...(command ? [] : [occupancy
            ? { text: `${text(COMMAND_MAP.occupancy)}: `, value: { text: occupancy, lang: "en" } }
            : { text: `${text(COMMAND_MAP.occupancy)}: ${text(COMMAND_MAP.notReported)}`, tone: "muted" as const }]),
          site.model_check?.m === false
            ? { text: text(COMMAND_MAP.notModelled), tone: "muted" }
            : { text: `${text(wet ? COMMAND_MAP.wetNow : COMMAND_MAP.dryNow)} (${text(COMMAND_FIGURES.modelTag)})`, tone: wet ? "alert" : undefined },
          ...(command ? [] : [{ text: text(countedInReportedSet(site) ? COMMAND_MAP.counted : COMMAND_MAP.notCounted), tone: "muted" as const }]),
        ];
        return popupElement(lines, site.sources.map((source) => ({ href: source.url, text: `${source.publisher}, ${source.date}: ${source.title}` })));
      };
      // From the town zoom on a site is a 22 px sign in a 44 px target. At the district zoom the signs are smaller
      // (14 px in 28 px), and the command centre stands a little above its point, so it does not sit on a star.
      const siteFar = () => map.getZoom() < SITE_FAR_BELOW_ZOOM;
      const siteIcon = (command: boolean, wet: boolean, pending = false, far = false) => {
        const box = far ? 28 : 44;
        const farClass = far ? ` ${styles.siteFar}` : "";
        if (command) {
          return L.divIcon({ className: `${styles.commandIcon}${farClass}`, html: diamondIcon(far ? 13 : 20), iconSize: [box, box], iconAnchor: far ? [14, 22] : [22, 22], popupAnchor: [0, far ? -15 : -10] });
        }
        return L.divIcon({
          className: `${styles.shelterIcon}${pending ? ` ${styles.shelterIconPending}` : wet ? ` ${styles.shelterIconWet}` : ""}${farClass}`,
          html: starIcon(far ? 14 : 22, wet && !pending), iconSize: [box, box], iconAnchor: [box / 2, box / 2], popupAnchor: [0, far ? -7 : -11],
        });
      };
      const labelSite = (entry: (typeof siteMarkers)[number]) => entry.marker.getElement()?.setAttribute("aria-label", siteTitle(entry.site, entry.command));
      /** One site as the map draws it now: its sign, or nothing while it is merged into a count or not yet on the map. */
      const showSite = (entry: (typeof siteMarkers)[number]) => {
        if (entry.merged || (entry.command && entry.pending)) {
          if (map.hasLayer(entry.marker)) entry.marker.remove();
          return;
        }
        entry.marker.setIcon(siteIcon(entry.command, entry.wet, entry.pending, siteFar()));
        if (!map.hasLayer(entry.marker)) entry.marker.addTo(map);
        labelSite(entry);
      };
      // At the district zoom, shelters closer than 24 px on screen share one count; a tap shows them apart.
      let siteBadges: { marker: Marker; count: number; centre: boolean }[] = [];
      const badgeTitle = (badge: Pick<(typeof siteBadges)[number], "count" | "centre">) => commandSiteGroupTitle(badge.count, badge.centre, languageRef.current);
      const labelBadge = (badge: (typeof siteBadges)[number]) => badge.marker.getElement()?.setAttribute("aria-label", `${badgeTitle(badge)} ${text(COMMAND_MARKERS.clusterZoom)}`);
      const glyph = (path: string, size: number): SVGSVGElement => {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24");
        svg.setAttribute("width", String(size));
        svg.setAttribute("height", String(size));
        svg.setAttribute("aria-hidden", "true");
        const shape = document.createElementNS("http://www.w3.org/2000/svg", "path");
        shape.setAttribute("d", path);
        svg.append(shape);
        return svg;
      };
      const layoutSites = () => {
        for (const badge of siteBadges) badge.marker.remove();
        siteBadges = [];
        const far = siteFar();
        const stars = siteMarkers.filter((entry) => !entry.command);
        const centreEntry = siteMarkers.find((entry) => entry.command && !entry.pending);
        if (centreEntry) centreEntry.merged = false;
        const at = (entry: (typeof siteMarkers)[number]) => map.latLngToLayerPoint(entry.marker.getLatLng());
        const groups = far ? groupNearbyPlaces(stars.map(at), SITE_MERGE_PX) : stars.map((_, index) => [index]);
        for (const members of groups) {
          const held = members.map((index) => stars[index]);
          for (const entry of held) entry.merged = held.length > 1;
          if (held.length === 1) continue;
          const points = held.map((entry) => entry.marker.getLatLng());
          const middle = L.latLng(points.reduce((sum, point) => sum + point.lat, 0) / points.length, points.reduce((sum, point) => sum + point.lng, 0) / points.length);
          // The command centre joins the count it would otherwise lie under: the count then shows its diamond too.
          const centre = Boolean(centreEntry && !centreEntry.merged && map.latLngToLayerPoint(middle).distanceTo(at(centreEntry)) <= SITE_MERGE_PX * 1.5);
          if (centre && centreEntry) {
            centreEntry.merged = true;
            points.push(centreEntry.marker.getLatLng());
          }
          const mark = document.createElement("span");
          mark.className = styles.siteBadge;
          mark.dataset.pending = held.every((entry) => entry.pending) && !centre ? "true" : "false";
          if (centre) mark.append(glyph(DIAMOND_PATH, 11));
          mark.append(glyph(STAR_PATH, 12), String(held.length));
          const marker = L.marker(middle, {
            pane: "fg-shelters", icon: L.divIcon({ className: styles.siteBadgeIcon, html: mark, iconSize: [44, 44], iconAnchor: [22, 22] }), keyboard: true, riseOnHover: true, zIndexOffset: 2050,
          });
          const badge = { marker, count: held.length, centre };
          marker.bindTooltip(() => tooltipElement([[badgeTitle(badge), "title"], [text(COMMAND_MARKERS.clusterZoom), "muted"]]), { direction: "top", offset: [0, -12] });
          marker.on("add", () => {
            labelBadge(badge);
            const element = marker.getElement();
            element?.setAttribute("data-site-group", String(held.length));
            element?.setAttribute("data-site-centre", centre ? "true" : "false");
          });
          // A tap, or Enter, shows the sites apart: about 400 m around them.
          marker.on("click", () => {
            const pad = 0.004;
            map.closePopup();
            fitTo([
              [Math.min(...points.map((point) => point.lat)) - pad, Math.min(...points.map((point) => point.lng)) - pad],
              [Math.max(...points.map((point) => point.lat)) + pad, Math.max(...points.map((point) => point.lng)) + pad],
            ], !motionRef.current);
          });
          marker.addTo(map);
          siteBadges.push(badge);
        }
        for (const entry of siteMarkers) showSite(entry);
      };
      for (const site of m.shelters?.reported ?? []) {
        if (site.lat === null || site.lon === null) continue;
        const command = reportedSiteRole(site).role === "relief_command";
        const marker = L.marker([site.lat, site.lon], { pane: "fg-shelters", icon: siteIcon(command, false), keyboard: true, riseOnHover: true, zIndexOffset: command ? 2100 : 2000 });
        marker.bindPopup(() => {
          const popup = marker.getPopup();
          if (popup) Object.assign(popup.options, popupFitInRect(clearRef.current(), size(), POPUP_WIDTH));
          return sitePopup(site, command);
        }, { className: MAP_POPUP_FRAME_CLASS, autoPan: true });
        keyboardPopup(marker);
        marker.bindTooltip(() => tooltipElement([[siteTitle(site, command), "title"], [text(COMMAND_MAP.select), "muted"]]), { direction: "top", offset: [0, -12] });
        tooltipLayers.push(marker);
        const entry = { marker, site, command, wet: false, fromHour: reportedSiteHour(site), pending: false, merged: false };
        marker.on("add", () => labelSite(entry));
        siteMarkers.push(entry);
      }
      layoutSites();
      const refreshText = () => {
        outsideLabel.textContent = text(COMMAND_MAP.outside);
        for (const badge of siteBadges) labelBadge(badge);
        for (const entry of siteMarkers) {
          labelSite(entry);
          if (entry.marker.isPopupOpen()) entry.marker.getPopup()?.update();
        }
        for (const layer of tooltipLayers) if (layer.isTooltipOpen()) layer.getTooltip()?.update();
      };
      refreshText();

      // --- The selected subdistrict, a found place and the tolerance of a report share one layer above the roads.
      const selectionRenderer = L.svg({ pane: "fg-selection", padding: 0.6 });

      // --- The reports: place records, invented items of the exercise, and the signs of this device.
      const depthAt = (lat: number, lon: number): number | null | undefined => {
        const raster = applied?.hand;
        if (!raster) return undefined;
        return modelDepthAt({ codes: raster.codes, factorKeys: raster.factorKeys, width: m.hand.width, height: m.hand.height, bounds: m.bounds, step: m.hand.step_m, channelCode: m.hand.channel_code, neverCode: m.hand.never_code }, lat, lon, applied?.stage ?? 0);
      };
      const markerLayer = mountCommandMarkers({
        L, map, manifest: m, tambons: labelPoints,
        language: () => languageRef.current,
        popupFit: (width) => popupFitInRect(clearRef.current(), size(), width),
        keyboardPopup,
        depthAt,
        onAction: (selection, action) => callbacks.current.onReportAction?.(selection, action),
        fitBox: (box) => {
          map.closePopup();
          fitTo(box, !motionRef.current);
        },
        panes: { markers: "fg-reported-depths", labels: "fg-labels", selection: "fg-selection" },
        selectionRenderer,
      });
      removeMarkers = markerLayer.remove;
      let reportFrame: CommandMarkerFrame | null = null;
      const syncSites = () => {
        if (!reportFrame) return;
        let changed = false;
        for (const entry of siteMarkers) {
          const pending = reportFrame.mode === "trainee" && entry.fromHour !== null && reportFrame.hour < entry.fromHour;
          if (pending === entry.pending) continue;
          entry.pending = pending;
          changed = true;
        }
        if (!changed) return;
        // A count of the district zoom is dashed while every site it holds is still unreported, so the counts are drawn again.
        layoutSites();
        for (const entry of siteMarkers) if (entry.marker.isPopupOpen()) entry.marker.getPopup()?.update();
      };

      // --- The 2024 season envelope (scenario): its cells on the water grid, hatched on a canvas of its own above the
      // water. Nothing here reads the replay hour: the layer is on in hindsight mode and off in trainee mode.
      let envelopeLayer: { overlay: ImageOverlay; context: CanvasRenderingContext2D; image: ImageData; pixels: Uint32Array; cells: Uint32Array; hatchKey: string } | null = null;
      const paintEnvelopeLayer = () => {
        if (!envelopeLayer) return;
        const west = map.latLngToLayerPoint(modelBounds.getNorthWest()).x;
        const east = map.latLngToLayerPoint(modelBounds.getSouthEast()).x;
        const hatch = envelopeHatch(Math.abs(east - west) / m.hand.width);
        const key = `${hatch.period}:${hatch.dark}:${hatch.light}`;
        if (key === envelopeLayer.hatchKey) return;
        paintEnvelope(envelopeLayer.cells, m.hand.width, envelopeLayer.pixels, hatch, LITTLE_ENDIAN);
        envelopeLayer.context.putImageData(envelopeLayer.image, 0, 0);
        envelopeLayer.hatchKey = key;
      };
      const setEnvelope = (next: CommandEnvelopeLayer | null) => {
        if (envelopeLayer && (!next || next.cells !== envelopeLayer.cells)) {
          envelopeLayer.overlay.remove();
          envelopeLayer = null;
        }
        if (!next || envelopeLayer) return;
        const element = document.createElement("canvas");
        element.width = m.hand.width;
        element.height = m.hand.height;
        const target = element.getContext("2d");
        if (!target) return;
        const picture = target.createImageData(element.width, element.height);
        const overlay = createCanvasOverlay(L, element, modelBounds, { pane: "fg-envelope", opacity: 1, className: styles.envelopeLayer, attribution: next.credit }).addTo(map);
        envelopeLayer = { overlay, context: target, image: picture, pixels: new Uint32Array(picture.data.buffer), cells: next.cells, hatchKey: "" };
        paintEnvelopeLayer();
      };

      // --- The selected subdistrict: a dark outline over a white casing, above the roads and under the names.
      let selectionLayers: Layer[] = [];
      let shownSelection: string | null = null;
      const setSelected = (id: string | null) => {
        if (id === shownSelection) return;
        shownSelection = id;
        for (const layer of selectionLayers) layer.remove();
        selectionLayers = [];
        const feature = id ? data.tambons.features.find((item) => item.properties.id === id) : null;
        if (!feature) return;
        const rings = areaPolygons(feature.geometry).map((polygon) => polygon.map((ring) => ring.map(([lon, lat]) => [lat, lon] as [number, number])));
        const shared = { pane: "fg-selection", renderer: selectionRenderer, interactive: false, lineJoin: "round" as const };
        selectionLayers = [
          L.polygon(rings, { ...shared, color: "#ffffff", weight: 6.5, opacity: 0.92, fill: false }).addTo(map),
          L.polygon(rings, { ...shared, color: "#12262d", weight: 2.6, opacity: 1, fillColor: "#12262d", fillOpacity: 0.035 }).addTo(map),
        ];
      };
      const fitTambon = (id: string) => {
        const feature = data.tambons.features.find((item) => item.properties.id === id);
        const box = feature ? areaBounds([feature.geometry]) : null;
        if (!box) return;
        map.closePopup();
        fitTo(box, !motionRef.current);
      };

      // --- A place found with the find-place box: a ring at its point (with the stated tolerance of a place record
      // as a dashed circle), or a pale casing along a named road, and its name beside it.
      let placeLayers: Layer[] = [];
      const showPlace = (place: CommandMapPlace | null, fit = false) => {
        for (const layer of placeLayers) layer.remove();
        placeLayers = [];
        if (!place) return;
        const { target } = place;
        const label = () => tooltipElement([[place.title, "title"], ...place.lines.map((line) => [line, "muted"] as [string, string])]);
        const shared = { pane: "fg-selection", renderer: selectionRenderer, interactive: false };
        if (target.type === "road") {
          const pieces = roads.filter((entry) => entry.props.n?.trim() === target.name).map((entry) => (entry.layer as Polyline).getLatLngs() as LatLng[]);
          const casing = L.polyline(pieces, { ...shared, color: "#12262d", weight: 10, opacity: 0.2, lineCap: "round", lineJoin: "round" }).addTo(map);
          casing.bindTooltip(label, { permanent: true, direction: "top", offset: [0, -6] });
          placeLayers = [casing];
          if (fit) {
            map.closePopup();
            fitTo(target.box, !motionRef.current);
          }
          return;
        }
        const site = target.siteId ? siteMarkers.find((entry) => entry.site.id === target.siteId) : undefined;
        if (fit) {
          map.closePopup();
          // About 800 m around the point, or the stated tolerance of a place record when that is wider.
          const span = Math.max(0.0075, ((target.toleranceM ?? 0) * 1.7) / 111_320);
          fitTo([[target.lat - span, target.lon - span], [target.lat + span, target.lon + span]], !site && !motionRef.current);
        }
        // A reported site has its own marker: its popup says what the data holds.
        if (site) {
          if (fit) site.marker.openPopup();
          return;
        }
        const at: [number, number] = [target.lat, target.lon];
        if (target.toleranceM) placeLayers.push(L.circle(at, { ...shared, radius: target.toleranceM, color: "#12262d", weight: 1.2, opacity: 0.7, dashArray: "4 4", fill: false }).addTo(map));
        placeLayers.push(L.circleMarker(at, { ...shared, radius: 12, color: "#ffffff", weight: 5.5, opacity: 0.95, fill: false }).addTo(map));
        const ring = L.circleMarker(at, { ...shared, radius: 12, color: "#12262d", weight: 2.4, fill: false }).addTo(map);
        ring.bindTooltip(label, { permanent: true, direction: "top", offset: [0, -12] });
        placeLayers.push(ring);
      };

      const reportView = () => callbacks.current.onView?.({ metresPerPixel: metresPerPixel(map.getCenter().lat, map.getZoom()), zoom: map.getZoom() });
      map.on("zoomend", () => {
        const next = map.getZoom() >= NEAR_ZOOM ? "near" : "far";
        if (next !== roadScale) {
          roadScale = next;
          styleRoads(appliedStage(), true);
        }
        paintEnvelopeLayer();
        layoutSites();
        reportView();
      });
      map.on("moveend", reportView);
      reportView();

      let shownBasemap: string | null = null;
      controller.current = {
        update(frame, exact) {
          const now = performance.now();
          if (applied && frame.hand === applied.hand) {
            if (frame.stage === applied.stage) {
              applied = frame;
              return;
            }
            if (!exact && now - appliedAt < PAINT_INTERVAL_MS && Math.abs(frame.stage - applied.stage) < PAINT_STAGE_STEP_M) return;
          }
          applied = frame;
          appliedAt = now;
          if (frame.hand) paintWater(frame.hand, frame);
          styleRoads(frame.stage, false);
          for (const entry of facilityEntries) {
            const wet = facilityWet(entry.props, frame.stage);
            if (wet === entry.wet) continue;
            const style = FACILITY_STYLES[wet ? "wet" : "dry"];
            entry.layer.setStyle(style);
            entry.layer.setRadius(style.radius);
            entry.wet = wet;
          }
          for (const entry of siteMarkers) {
            const wet = !entry.command && reportedSiteWetAt(entry.site, frame.stage);
            if (wet === entry.wet) continue;
            entry.wet = wet;
            showSite(entry);
          }
          refreshText();
        },
        setBasemap(choice, fallback) {
          const street = choice === "street";
          const key = `${choice}:${fallback}`;
          if (key === shownBasemap) return;
          shownBasemap = key;
          if (street && !map.hasLayer(tiles)) tiles.addTo(map);
          if (!street && map.hasLayer(tiles)) tiles.remove();
          // The shading stands in for the street tiles when they fail; chosen on its own it is drawn a little stronger.
          hillshade?.setOpacity(street ? (fallback ? 0.5 : 0) : 0.62);
        },
        setFacilities(visible) {
          if (visible && !map.hasLayer(facilityGroup)) facilityGroup.addTo(map);
          if (!visible && map.hasLayer(facilityGroup)) facilityGroup.remove();
        },
        setSelected,
        setReports(frame) {
          reportFrame = frame;
          markerLayer.update(frame);
          syncSites();
        },
        setEnvelope,
        refreshText() {
          refreshText();
          markerLayer.refreshText();
        },
      };
      mapHandle.current = {
        zoomBy(delta) {
          // Zoom about the middle of the clear rectangle, not of the screen: the panels cover the left of the map.
          const rect = clearRef.current();
          map.setZoomAround(L.point((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2), map.getZoom() + delta, { animate: !motionRef.current });
        },
        fit(target) {
          map.closePopup();
          fitTo(target === "town" ? townBox : districtBox, !motionRef.current);
        },
        fitTambon,
        showPlace,
        focusReport(selection) {
          const point = markerLayer.pointOf(selection);
          if (!point) return;
          map.closePopup();
          // At the district zoom an item is inside a count mark: the map goes to the town zoom around it.
          if (selection.type === "exercise" && map.getZoom() < CLUSTER_BELOW_ZOOM) {
            fitTo([[point[0] - 0.0075, point[1] - 0.0075], [point[0] + 0.0075, point[1] + 0.0075]], !motionRef.current);
            return;
          }
          const pan = panIntoRect(map.latLngToContainerPoint(point), clearRef.current(), 64);
          if (pan.x !== 0 || pan.y !== 0) map.panBy([pan.x, pan.y], { animate: !motionRef.current });
        },
        closePopup() {
          if (openPopups === 0) return false;
          map.closePopup();
          return true;
        },
      };
      resizeObserver = new ResizeObserver(() => map.invalidateSize());
      resizeObserver.observe(element.current);
      setReady(true);
      callbacks.current.onReady?.();
    }

    void mount();
    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      removeMapKeys?.();
      removeMarkers?.();
      removeFocusPan?.();
      callbacks.current.onWatermarkPane?.(null);
      controller.current = null;
      mapHandle.current = null;
      setReady(false);
      mounted?.stop();
      mounted?.remove();
    };
  }, [data]);

  // --- Updates: playback repaints are throttled; a pause, a step or a jump repaints exactly.
  useEffect(() => {
    if (ready) controller.current?.update({ stage, hour, hand }, !playing);
  }, [ready, hand, stage, hour, playing]);
  useEffect(() => {
    if (ready) controller.current?.setBasemap(basemap, tileIssue);
  }, [ready, basemap, tileIssue]);
  useEffect(() => {
    callbacks.current.onBasemapIssue?.(tileIssue);
  }, [tileIssue]);
  useEffect(() => {
    if (ready) controller.current?.setFacilities(facilities);
  }, [ready, facilities]);
  useEffect(() => {
    if (ready) controller.current?.setSelected(selected);
  }, [ready, selected]);
  // The reports follow every replay hour: they are not throttled like the water, and they read the depth the water shows.
  useEffect(() => {
    if (ready && reports) controller.current?.setReports(reports);
  }, [ready, reports, hand, stage]);
  useEffect(() => {
    if (ready) controller.current?.setEnvelope(envelope);
  }, [ready, envelope]);
  useEffect(() => {
    if (ready) controller.current?.refreshText();
  }, [ready, language]);

  return <div ref={element} className={styles.map} role="region" aria-label={commandText(COMMAND_MAP.label, language)} data-map-ready={ready ? "true" : "false"} />;
}
