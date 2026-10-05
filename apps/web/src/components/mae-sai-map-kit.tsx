/**
 * Map helpers shared by the Mae Sai replay in Studio and the Command exercise replay: a canvas-backed image overlay,
 * the popup and tooltip builders, and the keyboard handling of marker popups. They hold no replay state; each page
 * keeps its own map. Leaflet is passed in or reached through the map it is given, so this file loads without a
 * browser.
 */

import type { ImageOverlay, ImageOverlayOptions, LatLngBounds, Map as LeafletMap, Marker } from "leaflet";

import styles from "./mae-sai-map-kit.module.css";

/** Class of a popup's content built by `popupElement` (a page that builds its own popup content gives it this class). */
export const MAP_POPUP_CLASS = styles.popup;
/** Class for Leaflet's popup frame (`bindPopup(…, { className })`): the content margin of the replay popups. */
export const MAP_POPUP_FRAME_CLASS = styles.popupFrame;

interface CanvasOverlayInternals { _url: HTMLCanvasElement; _image: HTMLCanvasElement; _zoomAnimated: boolean; options: ImageOverlayOptions }

/** ImageOverlay backed by a caller-owned canvas, following Leaflet's SVGOverlay pattern. */
export function createCanvasOverlay(L: typeof import("leaflet"), canvas: HTMLCanvasElement, bounds: LatLngBounds, options: ImageOverlayOptions): ImageOverlay {
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

/** Tooltip content built from text nodes only: one line per entry, the "title" tone in bold. */
export function tooltipElement(lines: [string, string?][]): HTMLElement {
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
export interface PopupLine { text: string; tone?: "title" | "muted" | "alert"; lang?: string; value?: { text: string; lang: string } }

/** Popup content built from text nodes only (manifest strings are never parsed as HTML); links open in a new tab. */
export function popupElement(lines: PopupLine[], links: { href: string; text: string }[] = []): HTMLElement {
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

/**
 * Keeps the tooltip of a marker out of the way: it closes when the marker's popup opens, and it does not open while
 * the popup is open or while `selected` says that the marker's thing is already selected (its details are then in a
 * panel, and the tooltip would only cover its neighbours). Closing a popup hands the keyboard focus back to its
 * marker, and Leaflet opens a tooltip on focus: without this the tooltip would stand there with the pointer elsewhere.
 */
export function quietTooltip(marker: Marker, selected: () => boolean = () => false): void {
  marker.on("popupopen", () => marker.closeTooltip());
  marker.on("tooltipopen", () => {
    if (marker.isPopupOpen() || selected()) marker.closeTooltip();
  });
}

/**
 * Keyboard handling of marker popups on one map. Enter on a focused marker opens its popup (Leaflet turns it into a
 * click). Focus then moves into the popup so its links can be reached and a screen reader reads it; Escape closes it
 * from the marker or from inside it (Leaflet listens for keys only while the map container itself has focus), and
 * closing hands focus back to the marker. A popup opened with the pointer leaves focus where it is.
 *
 * `popupsOpen` tells whether the map has a popup open (the page counts them). `keyboardPopup` wires one marker that
 * already has a popup bound; `remove` takes the map's key listener away again. With `consumeEscape` the Escape that
 * closes a popup is marked as handled (`preventDefault`), so a page whose own Escape does something else (clearing a
 * selection, say) does one thing per key press.
 */
export function keyboardPopups(map: LeafletMap, popupsOpen: () => boolean, options: { consumeEscape?: boolean } = {}): { keyboardPopup: (marker: Marker) => void; remove: () => void } {
  let keyedMarker: HTMLElement | null = null;
  const mapContainer = map.getContainer();
  const onMapKey = (event: KeyboardEvent) => {
    const target = event.target instanceof HTMLElement ? event.target : null;
    if (event.key === "Enter" && target?.classList.contains("leaflet-marker-icon")) keyedMarker = target;
    if (event.key === "Escape" && popupsOpen()) {
      map.closePopup();
      if (options.consumeEscape) event.preventDefault();
    }
  };
  mapContainer.addEventListener("keydown", onMapKey);
  const keyboardPopup = (marker: Marker) => {
    let keyed = false;
    marker.on("popupopen", () => {
      const element = marker.getElement();
      keyed = Boolean(element) && keyedMarker === element;
      keyedMarker = null;
      if (!keyed) return;
      const content = marker.getPopup()?.getElement()?.querySelector<HTMLElement>(".leaflet-popup-content");
      if (!content) return;
      content.tabIndex = -1;
      content.focus({ preventScroll: true });
    });
    marker.on("popupclose", () => {
      const popup = marker.getPopup()?.getElement();
      const focused = document.activeElement;
      const inside = Boolean(popup && focused && popup.contains(focused));
      if (keyed || inside) marker.getElement()?.focus({ preventScroll: true });
      keyed = false;
    });
  };
  return { keyboardPopup, remove: () => mapContainer.removeEventListener("keydown", onMapKey) };
}
