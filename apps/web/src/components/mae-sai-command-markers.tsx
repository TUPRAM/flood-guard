"use client";

/**
 * The reports on the map of the Command exercise replay (Mae Sai, September 2024): what each marker looks like, what
 * its popup says, and the layer that keeps them on the map as the replay hour moves.
 *
 * The marker grammar (each meaning has at least two cues, so colour is never the only one):
 *   - a speech bubble with a count: the 2024 place records news reported at that point (reported, not surveyed), with
 *     a small badge where the model shows dry ground at the point;
 *   - an octagon: an invented call for help of the exercise; a rounded square: an invented report of depth or of a road;
 *   - urgency of an invented item by symbol, size and colour together ("!!" 36 px, "!" 30 px, "i" 26 px);
 *   - its handling state by outline: dashed while new, solid with the callsign under it once assigned, grey with a tick
 *     when closed; an open item shows how long it has waited, in replay hours;
 *   - a dashed sign above a subdistrict's name: reports saved on this device. They carry the date they were saved and
 *     are outside the replay clock;
 *   - below zoom 13, markers that lie close together merge into a count mark, which shows "!!" and that count when it
 *     holds a life-at-risk item.
 * Popups are built from text nodes only. Invented items say that they are invented on their first line.
 */

import type { Layer, Map as LeafletMap, Marker, PopupOptions, Renderer } from "leaflet";
import { createElement, type ReactElement } from "react";

import type { Language, Localized, ReportedDepthReport, TimelineManifest } from "@/lib/flood-timeline";
import { placeRecordsAt, type CommandMode } from "@/lib/flood-timeline-command-feed";
import {
  arrivedExerciseItems,
  CLUSTER_BELOW_ZOOM,
  CLUSTER_RADIUS_PX,
  clusterMarkers,
  EXERCISE_COLOURS,
  EXERCISE_URGENCIES,
  exerciseHandling,
  exerciseMarkerSpec,
  isOpenStatus,
  waitingHours,
  type ExerciseHandlingMap,
  type ExerciseItem,
  type ExerciseMarkerSpec,
} from "@/lib/flood-timeline-command-incidents";
import {
  COMMAND_DEVICE,
  COMMAND_EXERCISE,
  COMMAND_MARKERS,
  commandClusterTitle,
  commandDeviceCount,
  commandDeviceMeta,
  commandDeviceSign,
  commandDeviceSignTitle,
  commandItemMarkerTitle,
  commandItemPlaceLine,
  commandItemStateLine,
  commandItemTitle,
  commandItemWhatLine,
  commandItemWhenLine,
  commandModelHereLine,
  commandWaitingShort,
} from "@/lib/flood-timeline-command-reports-copy";
import { groupNearbyPlaces, reportedDepthMarkerTitle, reportedDepthPlaces, reportedDepthPopup, shippableReportedDepths, type ReportedDepthPlace } from "@/lib/flood-timeline-reported-depths";
import { publicReportWaterDepthLabel, type PublicReport } from "@/lib/public-report";

import { MAP_POPUP_CLASS, MAP_POPUP_FRAME_CLASS, popupElement, tooltipElement, type PopupLine } from "./mae-sai-map-kit";
import styles from "./mae-sai-command-markers.module.css";

// --- The drawings ----------------------------------------------------------------------------------------

/** One element of a marker drawing: the page draws it on the map through the DOM and in the legend through React. */
export interface SvgNode { tag: "path" | "rect" | "circle" | "text"; attrs: Record<string, string | number>; text?: string }

const INK = "#12262d";
const two = (value: number): string => String(Math.round(value * 100) / 100);

/** A regular octagon `half` wide from its middle to a flat side. */
function octagonPath(half: number): string {
  const a = half * Math.tan(Math.PI / 8);
  const points: [number, number][] = [[a, -half], [half, -a], [half, a], [a, half], [-a, half], [-half, a], [-half, -a], [-a, -half]];
  return `M${points.map(([x, y]) => `${two(x)} ${two(y)}`).join("L")}Z`;
}

/**
 * An exercise marker, drawn around (0, 0) inside a 44 px box: the shape in the urgency colour over a white casing
 * (wider for a life-at-risk item: its halo), the outline of the handling state, and the urgency symbol. A closed item
 * is grey with a tick.
 */
export function exerciseMarkerNodes(spec: ExerciseMarkerSpec): SvgNode[] {
  const half = spec.size / 2;
  const shape = (attrs: Record<string, string | number>): SvgNode => (spec.shape === "octagon"
    ? { tag: "path", attrs: { d: octagonPath(half), "stroke-linejoin": "round", ...attrs } }
    : { tag: "rect", attrs: { x: two(2 - half), y: two(2 - half), width: two(spec.size - 4), height: two(spec.size - 4), rx: 5, ...attrs } });
  if (spec.closed) {
    return [
      shape({ fill: spec.fill, stroke: "#6b787b", "stroke-width": 1.4 }),
      { tag: "path", attrs: { d: "M-5.5 0.5l3.8 3.8 7.2-8.2", fill: "none", stroke: "#3d4a4d", "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" } },
    ];
  }
  const fontSize = spec.symbol === "!!" ? 15 : spec.symbol === "!" ? 15 : 14;
  return [
    shape({ fill: spec.fill, stroke: "#ffffff", "stroke-width": spec.halo ? 3.4 : 2 }),
    shape({ fill: "none", stroke: INK, "stroke-width": spec.outline === "solid" ? 1.7 : 1.4, ...(spec.outline === "dashed" ? { "stroke-dasharray": "3 2.5" } : {}) }),
    { tag: "text", attrs: { x: 0, y: 0.5, "font-size": fontSize, "text-anchor": "middle", "dominant-baseline": "central", fill: spec.symbolColour }, text: spec.symbol },
  ];
}
export const EXERCISE_MARKER_VIEWBOX = "-22 -22 44 44";

/**
 * A place-record marker: a white speech bubble whose tail points at the place, with the number of place records it
 * holds. The small dashed badge says that the model shows dry ground at the point of at least one of them.
 */
export function placeRecordMarkerNodes(count: number, modelDry: boolean): SvgNode[] {
  const nodes: SvgNode[] = [
    { tag: "path", attrs: { d: "M-9-14h18a4 4 0 0 1 4 4v11a4 4 0 0 1-4 4h-4.5L0 12l-4.5-7H-9a4 4 0 0 1-4-4v-11a4 4 0 0 1 4-4Z", fill: "#ffffff", stroke: INK, "stroke-width": 1.6, "stroke-linejoin": "round" } },
    { tag: "text", attrs: { x: 0, y: -4.2, "font-size": 12, "text-anchor": "middle", "dominant-baseline": "central", fill: INK }, text: String(count) },
  ];
  if (modelDry) {
    nodes.push(
      { tag: "circle", attrs: { cx: 13, cy: -15, r: 6.2, fill: "#ffffff", stroke: INK, "stroke-width": 1.1, "stroke-dasharray": "2 1.6" } },
      // A water drop struck through: no water in the model here.
      { tag: "path", attrs: { d: "M13-18.6c1.7 2 2.6 3.4 2.6 4.5a2.6 2.6 0 0 1-5.2 0c0-1.1.9-2.5 2.6-4.5Z", fill: "none", stroke: INK, "stroke-width": 1, "stroke-linejoin": "round" } },
      { tag: "path", attrs: { d: "M9.4-11.6 16.6-18.4", fill: "none", stroke: INK, "stroke-width": 1.3, "stroke-linecap": "round" } },
    );
  }
  return nodes;
}
/** The tail of the bubble ends at (0, 12): the marker is anchored there. */
export const PLACE_RECORD_VIEWBOX = "-22 -30 44 44";

/** A count mark of the district zoom: the total in a dark disc, and "!!" with its count in the life-at-risk colour beside it. */
export function clusterMarkerNodes(total: number, lifeAtRisk: number): SvgNode[] {
  const nodes: SvgNode[] = [
    { tag: "circle", attrs: { cx: lifeAtRisk > 0 ? -4 : 0, cy: lifeAtRisk > 0 ? 4 : 0, r: 14, fill: INK, stroke: "#ffffff", "stroke-width": 2.4 } },
    { tag: "text", attrs: { x: lifeAtRisk > 0 ? -4 : 0, y: lifeAtRisk > 0 ? 4.5 : 0.5, "font-size": 13, "text-anchor": "middle", "dominant-baseline": "central", fill: "#ffffff" }, text: String(total) },
  ];
  if (lifeAtRisk > 0) {
    nodes.push(
      { tag: "rect", attrs: { x: 0, y: -21, width: 22, height: 15, rx: 7.5, fill: EXERCISE_COLOURS.life_at_risk, stroke: "#ffffff", "stroke-width": 2 } },
      { tag: "text", attrs: { x: 11, y: -13.2, "font-size": 10, "text-anchor": "middle", "dominant-baseline": "central", fill: "#ffffff" }, text: `!!${lifeAtRisk}` },
    );
  }
  return nodes;
}

const SVG_NS = "http://www.w3.org/2000/svg";

/** The drawing as an SVG element, built node by node (no markup is parsed). */
function svgElement(nodes: readonly SvgNode[], viewBox: string, size: number): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", viewBox);
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  for (const node of nodes) {
    const element = document.createElementNS(SVG_NS, node.tag);
    for (const [name, value] of Object.entries(node.attrs)) element.setAttribute(name, String(value));
    if (node.text !== undefined) element.textContent = node.text;
    svg.append(element);
  }
  return svg;
}

const camel = (name: string): string => name.replace(/-([a-z])/g, (_, letter: string) => letter.toUpperCase());

/** The same drawing for the legend. */
export function MarkerGlyph({ nodes, viewBox, size = 22 }: { nodes: readonly SvgNode[]; viewBox: string; size?: number }): ReactElement {
  return createElement("svg", { viewBox, width: size, height: size, className: styles.glyph, "aria-hidden": true, focusable: false },
    ...nodes.map((node, index) => createElement(node.tag, { key: index, ...Object.fromEntries(Object.entries(node.attrs).map(([name, value]) => [camel(name), value])) }, node.text)));
}

// --- The layer -------------------------------------------------------------------------------------------

/** What the reader has selected among the reports: an invented item, or the sign of this device on a subdistrict. */
export type CommandReportSelection = { type: "exercise"; id: string } | { type: "device"; tambonId: string };
export type CommandReportAction = "assign" | "details";

/** What the layer draws at one moment. */
export interface CommandMarkerFrame {
  /** Whole replay hour, 0 … 264. */
  hour: number;
  mode: CommandMode;
  /** The invented items of the exercise; an empty list while they are switched off. */
  items: readonly ExerciseItem[];
  handling: ExerciseHandlingMap;
  /** The reports saved on this device, per subdistrict. */
  device: ReadonlyMap<string, readonly PublicReport[]>;
  /** The subdistricts that carry the "no reports received" mark. */
  noReports: readonly string[];
  selected: CommandReportSelection | null;
}

export interface CommandMarkerLayerOptions {
  L: typeof import("leaflet");
  map: LeafletMap;
  manifest: TimelineManifest;
  /** The eight subdistricts with the point their name stands at (`[lon, lat]`). */
  tambons: readonly { id: string; th: string; en: string; point: [number, number] | null }[];
  language: () => Language;
  /** Leaflet popup options that keep a popup of this width inside the clear rectangle. */
  popupFit: (width: number) => Partial<PopupOptions>;
  keyboardPopup: (marker: Marker) => void;
  /** The modelled depth (m) at a point at the replay hour on screen; null outside the grid, undefined before the raster has loaded. */
  depthAt: (lat: number, lon: number) => number | null | undefined;
  onAction: (selection: CommandReportSelection, action: CommandReportAction) => void;
  /** Fit a box inside the clear rectangle (a tap on a count mark). */
  fitBox: (box: [[number, number], [number, number]]) => void;
  panes: { markers: string; labels: string; selection: string };
  selectionRenderer: Renderer;
}

export interface CommandMarkerLayer {
  update: (frame: CommandMarkerFrame) => void;
  /** The language changed: every marker, sign and open popup is rebuilt in it. */
  refreshText: () => void;
  /** Where a selection is on the map (`[lat, lon]`), for bringing it inside the clear rectangle. */
  pointOf: (selection: CommandReportSelection) => [number, number] | null;
  remove: () => void;
}

const ITEM_POPUP_WIDTH = 286;
const RECORD_POPUP_WIDTH = 320;
/** At the town zoom, place records closer than this on screen share one bubble (as on the Studio replay). */
const RECORD_GROUP_PX = 28;

type Thing =
  | { type: "records"; key: string; lat: number; lon: number; places: ReportedDepthPlace[]; reports: ReportedDepthReport[] }
  | { type: "item"; key: string; lat: number; lon: number; item: ExerciseItem };

/**
 * Mount the layer of the reports on a map. `update` is called at every replay hour: the markers are rebuilt only when
 * what is on the map changes (an item arrives, a record is published, the zoom crosses a grouping), and otherwise only
 * the waiting clocks and the lines of an open popup are refreshed.
 */
export function mountCommandMarkers(options: CommandMarkerLayerOptions): CommandMarkerLayer {
  const { L, map, manifest, tambons, language, depthAt } = options;
  const depthBlock = shippableReportedDepths(manifest);
  const places = depthBlock ? reportedDepthPlaces(depthBlock) : [];
  const tambonNames = new Map<string, Localized>(tambons.map((tambon) => [tambon.id, { th: tambon.th, en: tambon.en }]));
  const group = L.layerGroup().addTo(map);
  const signGroup = L.layerGroup().addTo(map);
  let frame: CommandMarkerFrame | null = null;
  let signature = "";
  let signSignature = "";
  let itemEntries: { item: ExerciseItem; marker: Marker; line: HTMLElement }[] = [];
  let toleranceLayers: Layer[] = [];
  let toleranceKey = "";

  const text = (entry: Localized) => (language() === "th" ? entry.th : entry.en);

  // --- The tolerance of a selected or opened place: a faint dashed circle of the stated radius.
  const showTolerance = (key: string, lat: number, lon: number, metres: number) => {
    if (key === toleranceKey) return;
    hideTolerance();
    toleranceKey = key;
    toleranceLayers = [L.circle([lat, lon], { pane: options.panes.selection, renderer: options.selectionRenderer, interactive: false, radius: metres, color: INK, weight: 1.2, opacity: 0.7, dashArray: "4 4", fillColor: INK, fillOpacity: 0.04 }).addTo(map)];
  };
  const hideTolerance = () => {
    for (const layer of toleranceLayers) layer.remove();
    toleranceLayers = [];
    toleranceKey = "";
  };
  /** The circle stays for the selected item; it goes with a popup that closes on anything else. */
  const settleTolerance = () => {
    const selected = frame?.selected;
    const entry = selected?.type === "exercise" ? itemEntries.find((item) => item.item.id === selected.id) : undefined;
    if (entry) showTolerance(`item:${entry.item.id}`, entry.item.point.lat, entry.item.point.lon, entry.item.toleranceM);
    else hideTolerance();
  };

  // --- Popups ---------------------------------------------------------------------------------------------
  const namedLines = (lines: (PopupLine & { name: string })[], kind: string): HTMLElement => {
    const root = popupElement(lines);
    root.classList.add(styles.itemPopup);
    root.lang = language();
    root.dataset.kind = kind;
    [...root.children].forEach((child, index) => { (child as HTMLElement).dataset.line = lines[index].name; });
    return root;
  };
  const actionRow = (selection: CommandReportSelection): HTMLElement => {
    const row = document.createElement("div");
    row.className = styles.popupActions;
    for (const action of ["assign", "details"] as const) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text(action === "assign" ? COMMAND_EXERCISE.assign : COMMAND_EXERCISE.details);
      button.dataset.commandAction = action;
      button.addEventListener("click", () => {
        map.closePopup();
        options.onAction(selection, action);
      });
      row.append(button);
    }
    return row;
  };
  const itemLines = (item: ExerciseItem) => {
    const lang = language();
    const handling = exerciseHandling(frame?.handling, item.id);
    const waiting = isOpenStatus(handling.status) ? waitingHours(item, frame?.hour ?? item.hour) : null;
    return {
      when: commandItemWhenLine(item, waiting, lang),
      model: commandModelHereLine(depthAt(item.point.lat, item.point.lon), lang),
      state: commandItemStateLine(item, handling, lang),
    };
  };
  /** At most six lines, then Assign and Details. The first line says that the item is invented. */
  const itemPopup = (item: ExerciseItem): HTMLElement => {
    const lang = language();
    const lines = itemLines(item);
    const root = namedLines([
      { name: "title", text: commandItemTitle(item, lang), tone: "title" },
      { name: "place", text: commandItemPlaceLine(item, tambonNames.get(item.tambonId) ?? null, lang) },
      { name: "what", text: commandItemWhatLine(item, lang) },
      { name: "when", text: lines.when },
      { name: "model", text: lines.model },
      { name: "state", text: lines.state },
    ], "exercise");
    root.dataset.item = item.id;
    root.append(actionRow({ type: "exercise", id: item.id }));
    return root;
  };
  const devicePopup = (tambonId: string, reports: readonly PublicReport[]): HTMLElement => {
    const lang = language();
    const name = tambonNames.get(tambonId);
    const depths = [...new Set(reports.map((report) => publicReportWaterDepthLabel(report.water_depth, lang)))].join(lang === "th" ? " " : ", ");
    const root = namedLines([
      { name: "title", text: text(COMMAND_DEVICE.title), tone: "title" },
      { name: "place", text: name ? (lang === "th" ? `ต.${name.th}` : `${name.th} (${name.en})`) : tambonId },
      { name: "meta", text: commandDeviceMeta(reports[0].created_at, lang) },
      { name: "what", text: `${commandDeviceCount(reports.length, lang)} · ${text(COMMAND_DEVICE.depth)}: ${depths}` },
      { name: "model", text: text(COMMAND_DEVICE.notSent) },
    ], "device");
    root.dataset.tambon = tambonId;
    root.append(actionRow({ type: "device", tambonId }));
    return root;
  };
  /** A place record keeps the replay's own popup: one section per record, with the comparison with the model and the source. */
  const recordPopup = (reports: readonly ReportedDepthReport[]): HTMLElement => {
    const lang = language();
    const root = document.createElement("div");
    root.className = MAP_POPUP_CLASS;
    root.dataset.kind = "records";
    for (const report of reports) {
      const { lines, link } = reportedDepthPopup(report, depthBlock!, lang);
      const section = document.createElement("section");
      section.className = styles.recordSection;
      section.dataset.report = report.id;
      for (const line of lines) {
        const element = document.createElement(line.tone === "title" ? "strong" : "p");
        element.textContent = line.text;
        if (line.tone === "muted") element.dataset.tone = "muted";
        if (line.lang) element.lang = line.lang;
        section.append(element);
      }
      const anchor = document.createElement("a");
      anchor.href = link.href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = link.text;
      const title = document.createElement("span");
      title.lang = link.titleLang;
      title.textContent = link.title;
      anchor.append(title);
      const source = document.createElement("p");
      source.append(anchor);
      section.append(source);
      root.append(section);
    }
    return root;
  };
  const bindFitted = (marker: Marker, width: number, content: () => HTMLElement) => {
    marker.bindPopup(() => {
      const popup = marker.getPopup();
      if (popup) Object.assign(popup.options, options.popupFit(width));
      return content();
    }, { className: MAP_POPUP_FRAME_CLASS, autoPan: true });
    options.keyboardPopup(marker);
  };
  const pin = (nodes: readonly SvgNode[], viewBox: string, half: number): HTMLElement => {
    const root = document.createElement("span");
    root.className = styles.pin;
    root.style.setProperty("--half", `${half}px`);
    root.append(svgElement(nodes, viewBox, 44));
    return root;
  };
  const named = (marker: Marker, title: () => string, data: Record<string, string>) => {
    marker.bindTooltip(() => tooltipElement([[title(), "title"], [text(COMMAND_EXERCISE.select), "muted"]]), { direction: "top", offset: [0, -16] });
    marker.on("add", () => {
      const element = marker.getElement();
      if (!element) return;
      element.setAttribute("aria-label", title());
      for (const [key, value] of Object.entries(data)) element.dataset[key] = value;
    });
  };

  // --- Markers --------------------------------------------------------------------------------------------
  const lineText = (item: ExerciseItem): string => {
    const handling = exerciseHandling(frame?.handling, item.id);
    const spec = exerciseMarkerSpec(item, handling.status);
    const waiting = waitingHours(item, frame?.hour ?? item.hour);
    return [
      spec.showsCallsign && handling.callsign ? handling.callsign : "",
      spec.showsWaiting && waiting > 0 ? commandWaitingShort(waiting, language()) : "",
    ].filter(Boolean).join(" · ");
  };
  const itemMarker = (item: ExerciseItem): Marker => {
    const handling = exerciseHandling(frame?.handling, item.id);
    const spec = exerciseMarkerSpec(item, handling.status);
    const root = pin(exerciseMarkerNodes(spec), EXERCISE_MARKER_VIEWBOX, spec.size / 2);
    const line = document.createElement("span");
    line.className = styles.pinLine;
    line.lang = language();
    line.dataset.state = handling.status;
    line.textContent = lineText(item);
    root.append(line);
    const rank = spec.closed ? 0 : 3 - EXERCISE_URGENCIES.indexOf(item.urgency);
    const marker = L.marker([item.point.lat, item.point.lon], {
      pane: options.panes.markers,
      icon: L.divIcon({ className: styles.pinIcon, html: root, iconSize: [44, 44], iconAnchor: [22, 22], popupAnchor: [0, -spec.size / 2 - 2] }),
      keyboard: true,
      riseOnHover: true,
      zIndexOffset: 3000 + rank * 100,
    });
    bindFitted(marker, ITEM_POPUP_WIDTH, () => itemPopup(item));
    named(marker, () => commandItemMarkerTitle(item, exerciseHandling(frame?.handling, item.id), language()), { item: item.id, urgency: item.urgency, status: handling.status, kind: item.kind });
    marker.on("popupopen", () => showTolerance(`item:${item.id}`, item.point.lat, item.point.lon, item.toleranceM));
    marker.on("popupclose", settleTolerance);
    itemEntries.push({ item, marker, line });
    return marker;
  };
  const recordMarker = (thing: Extract<Thing, { type: "records" }>): Marker => {
    const { reports } = thing;
    const dry = reports.some((report) => report.consistency === "model_dry");
    const marker = L.marker([thing.lat, thing.lon], {
      pane: options.panes.markers,
      icon: L.divIcon({ className: styles.pinIcon, html: pin(placeRecordMarkerNodes(reports.length, dry), PLACE_RECORD_VIEWBOX, 0), iconSize: [44, 44], iconAnchor: [22, 42], popupAnchor: [0, -32] }),
      keyboard: true,
      riseOnHover: true,
      zIndexOffset: 2900,
    });
    bindFitted(marker, RECORD_POPUP_WIDTH, () => recordPopup(reports));
    named(marker, () => `${reportedDepthMarkerTitle({ reports }, language())}${dry ? ` · ${text(COMMAND_MARKERS.modelDry)}` : ""}`, { reports: reports.map((report) => report.id).join(" "), modelDry: dry ? "true" : "false" });
    const tolerance = Math.max(0, ...reports.map((report) => report.location_tolerance_m ?? 0));
    marker.on("popupopen", () => { if (tolerance > 0) showTolerance(`records:${thing.key}`, thing.lat, thing.lon, tolerance); });
    marker.on("popupclose", settleTolerance);
    return marker;
  };
  const clusterMarker = (things: readonly Thing[], total: number, lifeAtRisk: number): Marker => {
    const lat = things.reduce((sum, thing) => sum + thing.lat, 0) / things.length;
    const lon = things.reduce((sum, thing) => sum + thing.lon, 0) / things.length;
    const marker = L.marker([lat, lon], {
      pane: options.panes.markers,
      icon: L.divIcon({ className: styles.pinIcon, html: pin(clusterMarkerNodes(total, lifeAtRisk), EXERCISE_MARKER_VIEWBOX, 14), iconSize: [44, 44], iconAnchor: [22, 22] }),
      keyboard: true,
      riseOnHover: true,
      zIndexOffset: 3400,
    });
    const title = () => commandClusterTitle(total, lifeAtRisk, language());
    marker.bindTooltip(() => tooltipElement([[title(), "title"]]), { direction: "top", offset: [0, -16] });
    marker.on("add", () => {
      const element = marker.getElement();
      if (!element) return;
      element.setAttribute("aria-label", title());
      element.dataset.cluster = String(total);
      element.dataset.lifeAtRisk = String(lifeAtRisk);
    });
    // A tap, or Enter, zooms to what the mark holds: about 250 m around its members.
    const zoomIn = () => {
      const pad = 0.0024;
      options.fitBox([
        [Math.min(...things.map((thing) => thing.lat)) - pad, Math.min(...things.map((thing) => thing.lon)) - pad],
        [Math.max(...things.map((thing) => thing.lat)) + pad, Math.max(...things.map((thing) => thing.lon)) + pad],
      ]);
    };
    // Enter on a focused marker reaches Leaflet as a click, so the keyboard zooms in too.
    marker.on("click", zoomIn);
    return marker;
  };

  /** What each marker on the map holds: the keys of its place records or of its item. */
  const markerKeys = new Map<Marker, string[]>();
  const openPopupMarker = (): Marker | null => {
    for (const marker of markerKeys.keys()) if (marker.isPopupOpen()) return marker;
    return null;
  };
  const currentOpenKey = (): string | null => {
    const marker = openPopupMarker();
    const keys = marker ? markerKeys.get(marker) : null;
    return keys ? keys[0] : null;
  };

  const sync = (force = false) => {
    if (!frame) return;
    const now = frame;
    const things: Thing[] = [];
    for (const place of places) {
      const reports = placeRecordsAt(place.reports, now.hour, now.mode);
      if (reports.length > 0) things.push({ type: "records", key: place.key, lat: place.lat, lon: place.lon, places: [place], reports });
    }
    for (const item of arrivedExerciseItems(now.items, now.hour)) things.push({ type: "item", key: item.id, lat: item.point.lat, lon: item.point.lon, item });
    const points = things.map((thing) => map.latLngToLayerPoint([thing.lat, thing.lon]));
    const openLife = (thing: Thing) => thing.type === "item" && thing.item.urgency === "life_at_risk" && isOpenStatus(exerciseHandling(now.handling, thing.item.id).status);
    let groups: number[][];
    if (map.getZoom() < CLUSTER_BELOW_ZOOM) {
      groups = clusterMarkers(things.map((thing, index) => ({ x: points[index].x, y: points[index].y, count: thing.type === "records" ? thing.reports.length : 1, lifeAtRisk: openLife(thing) })), CLUSTER_RADIUS_PX).map((cluster) => cluster.members);
    } else {
      // At the town zoom every item stands alone; place records whose bubbles would overlap share one bubble.
      const recordIndices = things.flatMap((thing, index) => (thing.type === "records" ? [index] : []));
      const merged = groupNearbyPlaces(recordIndices.map((index) => points[index]), RECORD_GROUP_PX).map((members) => members.map((member) => recordIndices[member]));
      groups = [...merged, ...things.flatMap((thing, index) => (thing.type === "item" ? [[index]] : []))];
    }
    const sign = (thing: Thing) => (thing.type === "records"
      ? `${thing.key}:${thing.reports.map((report) => report.id).join(",")}`
      : `${thing.key}:${exerciseHandling(now.handling, thing.item.id).status}:${exerciseHandling(now.handling, thing.item.id).callsign ?? ""}`);
    const next = `${language()}|${map.getZoom() < CLUSTER_BELOW_ZOOM ? "far" : "near"}|${groups.map((members) => members.map((index) => sign(things[index])).join("+")).join("|")}`;
    if (force || next !== signature) {
      signature = next;
      // A popup open across the rebuild reopens on the marker that now holds its thing.
      const openKey = currentOpenKey();
      group.clearLayers();
      itemEntries = [];
      markerKeys.clear();
      for (const members of groups) {
        const held = members.map((index) => things[index]);
        let marker: Marker;
        if (held.length === 1 && held[0].type === "item") marker = itemMarker(held[0].item);
        else if (held.every((thing) => thing.type === "records") && (held.length === 1 || map.getZoom() >= CLUSTER_BELOW_ZOOM)) {
          const records = held as Extract<Thing, { type: "records" }>[];
          marker = recordMarker({ type: "records", key: records.map((thing) => thing.key).join("+"), lat: records[0].lat, lon: records[0].lon, places: records.flatMap((thing) => thing.places), reports: records.flatMap((thing) => thing.reports) });
        } else {
          marker = clusterMarker(held, held.reduce((sum, thing) => sum + (thing.type === "records" ? thing.reports.length : 1), 0), held.filter(openLife).length);
        }
        markerKeys.set(marker, held.map((thing) => thing.key));
        group.addLayer(marker);
      }
      if (openKey) {
        for (const [marker, keys] of markerKeys) if (keys.length === 1 && keys[0] === openKey && marker.getPopup()) marker.openPopup();
      }
    } else {
      // Nothing arrived and nothing changed state: only the waiting clocks and an open popup follow the hour.
      for (const entry of itemEntries) {
        const value = lineText(entry.item);
        if (entry.line.textContent !== value) entry.line.textContent = value;
        if (!entry.marker.isPopupOpen()) continue;
        const content = entry.marker.getPopup()?.getElement();
        const lines = itemLines(entry.item);
        for (const name of ["when", "model", "state"] as const) {
          const element = content?.querySelector<HTMLElement>(`[data-line="${name}"]`);
          if (element && element.textContent !== lines[name]) element.textContent = lines[name];
        }
      }
    }
    // The selected item wears a ring, and keeps its tolerance circle.
    for (const entry of itemEntries) entry.marker.getElement()?.classList.toggle(styles.selectedPin, now.selected?.type === "exercise" && now.selected.id === entry.item.id);
    if (!openPopupMarker()) settleTolerance();
    syncSigns(force);
  };

  // --- The sign of this device above a subdistrict's name, and "no reports received" below it.
  const signMarkers = new Map<string, Marker>();
  const syncSigns = (force: boolean) => {
    if (!frame) return;
    const now = frame;
    const selectedDevice = now.selected?.type === "device" ? now.selected.tambonId : "";
    const next = `${language()}|${tambons.map((tambon) => `${now.device.get(tambon.id)?.length ?? 0}:${now.device.get(tambon.id)?.[0]?.created_at ?? ""}:${now.noReports.includes(tambon.id) ? 1 : 0}`).join("|")}|${selectedDevice}`;
    if (!force && next === signSignature) return;
    signSignature = next;
    const openSign = [...signMarkers].find(([, marker]) => marker.isPopupOpen())?.[0];
    signGroup.clearLayers();
    signMarkers.clear();
    for (const tambon of tambons) {
      if (!tambon.point) continue;
      const at: [number, number] = [tambon.point[1], tambon.point[0]];
      const reports = now.device.get(tambon.id) ?? [];
      if (reports.length > 0) {
        const sign = document.createElement("span");
        sign.className = styles.deviceSign;
        sign.lang = language();
        sign.textContent = commandDeviceSign(reports.length, language());
        // The sign is pressed, so it stands above the shelter stars; the grey mark under the name is only read.
        const marker = L.marker(at, { pane: options.panes.markers, icon: L.divIcon({ className: styles.signIcon, html: sign, iconSize: [0, 0], popupAnchor: [0, -40] }), keyboard: true, zIndexOffset: 2000 });
        bindFitted(marker, ITEM_POPUP_WIDTH, () => devicePopup(tambon.id, reports));
        marker.on("add", () => {
          const element = marker.getElement();
          if (!element) return;
          element.setAttribute("aria-label", commandDeviceSignTitle(reports.length, tambon, language()));
          element.dataset.deviceSign = tambon.id;
          element.dataset.selected = selectedDevice === tambon.id ? "true" : "false";
        });
        signMarkers.set(tambon.id, marker);
        signGroup.addLayer(marker);
      }
      if (now.noReports.includes(tambon.id)) {
        const mark = document.createElement("span");
        mark.className = styles.noReports;
        mark.lang = language();
        mark.textContent = text(COMMAND_MARKERS.noReports);
        mark.title = text(COMMAND_MARKERS.noReportsMeaning);
        mark.dataset.noReports = tambon.id;
        signGroup.addLayer(L.marker(at, { pane: options.panes.labels, icon: L.divIcon({ className: styles.signIcon, html: mark, iconSize: [0, 0] }), interactive: false, keyboard: false }));
      }
    }
    if (openSign) signMarkers.get(openSign)?.openPopup();
  };

  const onZoom = () => sync();
  map.on("zoomend", onZoom);

  return {
    update(next) {
      frame = next;
      sync();
    },
    refreshText() {
      sync(true);
    },
    pointOf(selection) {
      if (selection.type === "exercise") {
        const item = frame?.items.find((entry) => entry.id === selection.id);
        return item ? [item.point.lat, item.point.lon] : null;
      }
      const tambon = tambons.find((entry) => entry.id === selection.tambonId);
      return tambon?.point ? [tambon.point[1], tambon.point[0]] : null;
    },
    remove() {
      map.off("zoomend", onZoom);
      hideTolerance();
      group.remove();
      signGroup.remove();
    },
  };
}
