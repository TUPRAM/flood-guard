/**
 * The layers of the practice replay on the Public home map: the modelled water of one replay hour, the road pieces
 * with water on them, the invented exercise items that have arrived, and the example home with the circle its roads
 * are counted in. Drawn on the map `GeoMap` owns, through its `overlay` hook.
 *
 * The water and the roads are the replay's own (revision r5), painted with the two tones and the road rule of the
 * Command exercise replay. A T1 scenario (model) with low confidence: not an observation, and nothing about today.
 */

import type { Layer, Map as LeafletMap } from "leaflet";

import { FACTOR_LUT_SIZE, paintDepth, paintLowConfidence, projectToFrame, type AreaGeometry, type GeoCollection, type LineGeometry, type RoadProps, type TambonProps, type TimelineManifest } from "@/lib/flood-timeline";
import type { CommandHandRaster } from "@/lib/flood-timeline-command-data";
import type { ExerciseItem } from "@/lib/flood-timeline-command-incidents";
import { areaPolygons, buildTwoToneFactorLut, buildTwoToneLut, cellsInMask, commandRoadStyle, COMMAND_WET_ROAD } from "@/lib/flood-timeline-command-map";
import { PRACTICE_COPY, PRACTICE_RADIUS_M, practiceReportLabel, practiceReportLines } from "@/lib/public-practice";
import { cellOutlines, frameToLatLng } from "@/lib/public-practice-outline";
import type { Language } from "@/lib/types";

import { createGeoMapRenderer, OSM_ATTRIBUTION_HTML } from "./geo-map";
import { createCanvasOverlay, MAP_POPUP_FRAME_CLASS, popupElement } from "./mae-sai-map-kit";

type LeafletModule = typeof import("leaflet");

/** The replay files the layers are drawn from. Without the terrain raster the roads and the reports are still drawn. */
export interface PracticeMapData {
  manifest: TimelineManifest;
  roads: GeoCollection<LineGeometry, RoadProps>;
  tambons: GeoCollection<AreaGeometry, TambonProps>;
  hand: CommandHandRaster | null;
}

/** What is drawn for one scenario. */
export interface PracticeMapFrame {
  home: { latitude: number; longitude: number };
  /** Assumed river stage of the replay hour (m). */
  stage: number;
  showPeakExtent: boolean;
  reports: readonly ExerciseItem[];
  language: Language;
}

const LITTLE_ENDIAN = new Uint8Array(new Uint32Array([1]).buffer)[0] === 1;
const IMPASSABLE_ROAD = "#c62f24";
/**
 * The furthest water of the replay: a faint wash of the water's deep tone inside a dashed outline. The outline is
 * traced from the cells and drawn as a line, so it stays crisp at every zoom (owner request of 13 Oct 2026: the
 * hatch it replaces blurred into dots when the map was zoomed in).
 */
const PEAK_WASH_RGBA = [47, 134, 196, 26] as const;
const PEAK_OUTLINE = "#2f6fb5";
/** How far, in cells, the drawn outline may leave the edges of the cells: it turns their stair steps into slopes. */
const PEAK_OUTLINE_TOLERANCE = 1.5;
/** From this zoom on a practice report shows the depth it states beside its "EX" tag; below it, the tag alone. */
const REPORT_DETAIL_ZOOM = 16;
const REPORT_DETAIL_CLASS = "public-practice-detail";

const pack = ([r, g, b, a]: readonly number[], littleEndian: boolean): number =>
  (littleEndian ? ((a << 24) | (b << 16) | (g << 8) | r) : ((r << 24) | (g << 16) | (b << 8) | a)) >>> 0;

interface ClippedCells { candidates: Uint32Array; lowCells: Uint32Array | null; lowStripes: Uint8Array | null }
const clippedByRaster = new WeakMap<CommandHandRaster, ClippedCells>();

/**
 * The wet-able cells inside the eight subdistricts. The figures count nothing outside them, so no water is drawn
 * there either. The subdistricts are rasterised once per raster on the terrain grid (linear in Web Mercator, like
 * the overlay).
 */
function districtCells(data: PracticeMapData, raster: CommandHandRaster): ClippedCells {
  const known = clippedByRaster.get(raster);
  if (known) return known;
  const { manifest } = data;
  const canvas = document.createElement("canvas");
  canvas.width = manifest.hand.width;
  canvas.height = manifest.hand.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  let clipped: ClippedCells = { candidates: raster.candidates, lowCells: raster.lowCells, lowStripes: raster.lowStripes };
  if (context) {
    context.fillStyle = "#000000";
    for (const feature of data.tambons.features) {
      for (const rings of areaPolygons(feature.geometry)) {
        context.beginPath();
        for (const ring of rings) {
          ring.forEach(([lon, lat], index) => {
            const [x, y] = projectToFrame(lon, lat, manifest.bounds, canvas.width, canvas.height);
            if (index === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
          });
          context.closePath();
        }
        context.fill("evenodd");
      }
    }
    const mask = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const low = raster.lowCells ? cellsInMask(raster.lowCells, mask, 4, 3, raster.lowStripes) : null;
    clipped = { candidates: cellsInMask(raster.candidates, mask, 4, 3).cells, lowCells: low?.cells ?? null, lowStripes: low?.parallel ?? null };
  }
  clippedByRaster.set(raster, clipped);
  return clipped;
}

const peakOutlineByRaster = new WeakMap<CommandHandRaster, [number, number][][]>();

/**
 * The outline of the furthest water of the replay inside the eight subdistricts, as rings of latitude and longitude.
 * It does not depend on the hour, so it is traced once per raster.
 */
function peakOutline(L: LeafletModule, data: PracticeMapData, raster: CommandHandRaster): [number, number][][] {
  const known = peakOutlineByRaster.get(raster);
  if (known) return known;
  const { bounds, hand } = data.manifest;
  const rings = cellOutlines(districtCells(data, raster).candidates, hand.width, hand.height).map((loop) => {
    const corners = [];
    for (let index = 0; index < loop.length; index += 2) corners.push(L.point(loop[index], loop[index + 1]));
    corners.push(corners[0]);
    return L.LineUtil.simplify(corners, PEAK_OUTLINE_TOLERANCE).map((corner) => frameToLatLng(corner.x, corner.y, bounds, hand.width, hand.height));
  }).filter((ring) => ring.length >= 4);
  peakOutlineByRaster.set(raster, rings);
  return rings;
}

const HOME_PIN_HTML = [
  '<svg class="public-area-pin" viewBox="0 0 32 40" aria-hidden="true" focusable="false">',
  '<path d="M16 38.4c0 0 11.2-15.6 11.2-22.6a11.2 11.2 0 1 0-22.4 0c0 7 11.2 22.6 11.2 22.6Z"',
  ' fill="currentColor" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/>',
  '<circle cx="16" cy="15.6" r="4.4" fill="#fff"/>',
  "</svg>",
].join("");

/**
 * Draw one scenario on `map` and frame the example home. Returns the function that takes everything away again and
 * puts the map back where it was.
 */
export function mountPracticeLayers(L: LeafletModule, map: LeafletMap, data: PracticeMapData, frame: PracticeMapFrame): () => void {
  const { manifest } = data;
  const layers: Layer[] = [];
  const before = { centre: map.getCenter(), zoom: map.getZoom() };
  const pane = (name: string, zIndex: number): string => {
    const element = map.getPane(name) ?? map.createPane(name);
    element.style.zIndex = String(zIndex);
    element.style.pointerEvents = "none";
    return name;
  };
  // Under the subdistrict outlines (400) the water; over them the roads; the markers stay in Leaflet's marker pane.
  const waterPane = pane("fg-practice-water", 350);
  const roadPane = pane("fg-practice-roads", 420);
  const home: [number, number] = [frame.home.latitude, frame.home.longitude];
  const renderer = createGeoMapRenderer(L, { pane: roadPane, padding: 0.4 });

  // --- Modelled water of the hour, with the furthest water of the replay washed in under it while the water is low.
  if (data.hand) {
    const raster = data.hand;
    const canvas = document.createElement("canvas");
    canvas.width = manifest.hand.width;
    canvas.height = manifest.hand.height;
    const context = canvas.getContext("2d");
    const image = context?.createImageData(canvas.width, canvas.height);
    if (context && image) {
      const pixels = new Uint32Array(image.data.buffer);
      const cells = districtCells(data, raster);
      if (frame.showPeakExtent) {
        const wash = pack(PEAK_WASH_RGBA, LITTLE_ENDIAN);
        for (let index = 0; index < cells.candidates.length; index += 1) pixels[cells.candidates[index]] = wash;
      }
      const lut = raster.factorKeys
        ? buildTwoToneFactorLut(frame.stage, manifest.hand.step_m, manifest.impassable_depth_m, LITTLE_ENDIAN, new Uint32Array(FACTOR_LUT_SIZE), raster.factorScale)
        : buildTwoToneLut(frame.stage, manifest.hand.step_m, manifest.impassable_depth_m, LITTLE_ENDIAN);
      // A dry cell has a transparent entry in the lookup table and would wipe the wash, so only wet cells are painted.
      // On a dry day (stage 0) nothing is: the model counts its mapped stream channels as water at every stage, and
      // their blue blocks beside "No water near this home" read as a contradiction (owner request of 13 Oct 2026).
      const keys = raster.factorKeys ?? raster.codes;
      const wet = frame.stage > 0 ? cells.candidates.filter((cell) => lut[keys[cell]] !== 0) : new Uint32Array(0);
      paintDepth(keys, wet, lut, pixels);
      if (frame.stage > 0 && cells.lowCells && cells.lowStripes) {
        const lowWet: number[] = [];
        const lowStripes: number[] = [];
        cells.lowCells.forEach((cell, index) => {
          if (lut[keys[cell]] === 0) return;
          lowWet.push(cell);
          lowStripes.push(cells.lowStripes![index]);
        });
        paintLowConfidence(Uint32Array.from(lowWet), Uint8Array.from(lowStripes), pixels, LITTLE_ENDIAN);
      }
      context.putImageData(image, 0, 0);
      layers.push(createCanvasOverlay(L, canvas, L.latLngBounds(manifest.bounds), { pane: waterPane, opacity: 0.74, className: "public-practice-water" }).addTo(map));
    }
  }

  // --- The outline of that furthest water: a dashed line on a white edge, under the roads.
  if (data.hand && frame.showPeakExtent) {
    const rings = peakOutline(L, data, data.hand);
    layers.push(L.polyline(rings, { renderer, interactive: false, color: "#ffffff", opacity: 0.85, weight: 3.6, lineJoin: "round" }).addTo(map));
    layers.push(L.polyline(rings, { renderer, interactive: false, color: PEAK_OUTLINE, opacity: 1, weight: 1.6, dashArray: "6 5", lineJoin: "round" }).addTo(map));
  }

  // --- Road pieces with water on them: impassable in red, shallower water in dashed amber, each on a white casing.
  const casings: Layer[] = [];
  const lines: Layer[] = [];
  for (const road of data.roads.features) {
    const style = commandRoadStyle(road.properties, frame.stage, manifest.impassable_depth_m);
    if (style !== "impassable" && style !== "wet") continue;
    const path = road.geometry.coordinates.map(([lon, lat]) => [lat, lon] as [number, number]);
    const impassable = style === "impassable";
    casings.push(L.polyline(path, { renderer, interactive: false, color: "#ffffff", opacity: 0.9, weight: impassable ? 5.5 : 4.5, lineCap: "round" }));
    lines.push(L.polyline(path, {
      renderer,
      interactive: false,
      color: impassable ? IMPASSABLE_ROAD : COMMAND_WET_ROAD,
      opacity: 1,
      weight: impassable ? 3.2 : 2.4,
      dashArray: impassable ? undefined : "6 5",
      lineCap: impassable ? "round" : "butt",
      attribution: OSM_ATTRIBUTION_HTML,
    }));
  }
  for (const layer of [...casings, ...lines]) layers.push(layer.addTo(map));

  // --- The circle the roads and the reports are counted in.
  layers.push(L.circle(home, { renderer, interactive: false, radius: PRACTICE_RADIUS_M, color: "#0f4c81", weight: 1.6, opacity: 0.85, dashArray: "7 6", fill: false }).addTo(map));

  // --- The invented exercise items that have arrived. Each wears the "EX" tag, and its popup says it is invented.
  // Around the example home several lie within a few hundred metres, so the depth word is shown from a close zoom on.
  const container = map.getContainer();
  const showReportDetail = () => container.classList.toggle(REPORT_DETAIL_CLASS, map.getZoom() >= REPORT_DETAIL_ZOOM);
  map.on("zoomend", showReportDetail);
  for (const item of frame.reports) {
    const element = document.createElement("span");
    element.className = "public-practice-report";
    element.dataset.urgency = item.urgency;
    const tag = document.createElement("b");
    tag.textContent = "EX";
    const word = document.createElement("span");
    word.textContent = practiceReportLabel(item, frame.language);
    element.append(tag, word);
    const text = practiceReportLines(item, frame.language);
    const marker = L.marker([item.point.lat, item.point.lon], {
      icon: L.divIcon({ className: "public-practice-report-shell", html: element, iconSize: [44, 44], iconAnchor: [22, 22] }),
      keyboard: true,
      title: `${text.title} · ${text.depth}`,
      alt: `${text.title} · ${text.depth}`,
      zIndexOffset: 300,
    });
    marker.bindPopup(
      popupElement([
        { text: text.title, tone: "title" },
        { text: text.text },
        { text: text.depth, tone: "muted" },
        { text: text.tag, tone: "muted" },
      ]),
      { className: MAP_POPUP_FRAME_CLASS, maxWidth: 260, autoPanPaddingTopLeft: [12, 190], autoPanPaddingBottomRight: [72, 96] },
    );
    layers.push(marker.addTo(map));
  }

  // --- The example home.
  const pin = L.marker(home, {
    interactive: false,
    keyboard: false,
    zIndexOffset: 900,
    icon: L.divIcon({ className: "public-area-pin-shell", html: HOME_PIN_HTML, iconSize: [34, 42], iconAnchor: [17, 41] }),
  }).addTo(map);
  const label = document.createElement("span");
  label.className = "public-area-pin-label";
  label.textContent = PRACTICE_COPY.homeLabel[frame.language];
  pin.bindTooltip(label, { permanent: true, direction: "bottom", offset: [0, 6], className: "public-area-pin-tooltip", interactive: false }).openTooltip();
  layers.push(pin);

  // --- Frame the circle, clear of the search field and the banner above and of the tools on the right.
  const north = PRACTICE_RADIUS_M / 110_540;
  const east = PRACTICE_RADIUS_M / (111_320 * Math.cos((frame.home.latitude * Math.PI) / 180));
  map.fitBounds(
    [[frame.home.latitude - north, frame.home.longitude - east], [frame.home.latitude + north, frame.home.longitude + east]],
    { animate: false, maxZoom: 16, paddingTopLeft: [12, 176], paddingBottomRight: [68, 84] },
  );
  showReportDetail();

  return () => {
    map.closePopup();
    map.off("zoomend", showReportDetail);
    container.classList.remove(REPORT_DETAIL_CLASS);
    for (const layer of layers) layer.remove();
    renderer.remove();
    map.setView(before.centre, before.zoom, { animate: false });
  };
}
