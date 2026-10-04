/**
 * Layout arithmetic for the Mae Sai replay map: how large a map popup may be and how far it must stay from the map
 * edges, and where a glossary tooltip sits so it never leaves the viewport. Pure functions; the components measure
 * the page and apply the results.
 */

/** Maps narrower than this (phones) use the tight popup paddings. */
export const POPUP_NARROW_MAP_PX = 520;
/** Tallest popup body on any screen; taller content scrolls inside the popup. */
export const POPUP_MAX_HEIGHT_PX = 300;
/** Smallest popup body the page will ask for, however small the map is. */
export const POPUP_MIN_WIDTH_PX = 160;
export const POPUP_MIN_HEIGHT_PX = 96;
/**
 * What Leaflet adds around the popup body: the content margins and its 1 px width allowance across, and the content
 * margins, the wrapper padding and the 20 px tip below.
 */
export const POPUP_CHROME_PX = { x: 28, y: 46 } as const;
/**
 * Left edge the popup must clear: the zoom control (10 px margin; its two 44 px buttons and their border make it
 * 48 px wide) plus a 6 px gap.
 */
export const ZOOM_CLEARANCE_PX = 64;

/** A side label of the imagery swipe is shown only when at least this much width is left for it. */
export const COMPARE_LABEL_MIN_PX = 64;
/** Gap between the divider and each side label, and between the right label and the map edge. */
export const COMPARE_LABEL_GAP_PX = { divider: 16, edge: 10 } as const;

/**
 * Width (px) left for each side label of the imagery swipe on a map `frameWidth` wide with the divider at `pct` %.
 * The left label sits between the zoom control (`ZOOM_CLEARANCE_PX`) and the divider, the right one between the
 * divider and the map edge. A label with less than `COMPARE_LABEL_MIN_PX` is not shown: on a narrow map it would
 * wrap into a tall sliver, and the divider's value text still names both images.
 */
export function compareLabelRoom(frameWidth: number, pct: number): { left: number; right: number } {
  const divider = (Math.max(0, frameWidth) * Math.min(100, Math.max(0, pct))) / 100;
  return {
    left: Math.max(0, divider - COMPARE_LABEL_GAP_PX.divider - ZOOM_CLEARANCE_PX),
    right: Math.max(0, frameWidth - divider - COMPARE_LABEL_GAP_PX.divider - COMPARE_LABEL_GAP_PX.edge),
  };
}

export interface PopupFitInput {
  /** Size of the map container in CSS pixels. */
  mapWidth: number;
  mapHeight: number;
  /** Popup body width used on a wide map (each popup kind has its own). */
  preferredWidth: number;
  /** Height above the map's bottom edge taken by the attribution and, when shown, the note and button stack over it. */
  bottomReserved: number;
}

/** Leaflet popup options that keep a popup inside the map and clear of the zoom control and the bottom stack. */
export interface PopupFit {
  maxWidth: number;
  maxHeight: number;
  autoPanPaddingTopLeft: [number, number];
  autoPanPaddingBottomRight: [number, number];
}

/**
 * Size and auto-pan paddings for a popup on a map of this size. The left padding always clears the zoom control. On a
 * wide map the others are the page's usual ones (room for the notes above, the attribution below); on a phone-sized
 * map they shrink, and the popup body is capped so that paddings, popup and tip always fit inside the map together.
 */
export function popupFit({ mapWidth, mapHeight, preferredWidth, bottomReserved }: PopupFitInput): PopupFit {
  const narrow = mapWidth < POPUP_NARROW_MAP_PX;
  const left = ZOOM_CLEARANCE_PX;
  const top = narrow ? 8 : 96;
  const right = narrow ? 8 : 24;
  const bottom = Math.max(narrow ? 8 : 48, Math.ceil(Math.max(0, bottomReserved)) + 8);
  const width = Math.floor(mapWidth - left - right - POPUP_CHROME_PX.x);
  const height = Math.floor(mapHeight - top - bottom - POPUP_CHROME_PX.y);
  return {
    maxWidth: Math.max(POPUP_MIN_WIDTH_PX, Math.min(preferredWidth, width)),
    maxHeight: Math.max(POPUP_MIN_HEIGHT_PX, Math.min(POPUP_MAX_HEIGHT_PX, height)),
    autoPanPaddingTopLeft: [left, top],
    autoPanPaddingBottomRight: [right, bottom],
  };
}

/**
 * How far (px, negative is left) to move a tooltip that spans `tipLeft` … `tipRight` in viewport coordinates so that
 * it lies inside the viewport with `margin` to spare. 0 when it already fits; a tooltip wider than the viewport is
 * pinned to the left margin.
 */
export function tooltipShift(tipLeft: number, tipRight: number, viewportWidth: number, margin = 8): number {
  const width = tipRight - tipLeft;
  const furthestLeftEdge = viewportWidth - margin - width;
  const target = Math.max(margin, Math.min(tipLeft, furthestLeftEdge));
  return Math.round(target - tipLeft);
}

/** What keeps a glossary tooltip open: the pointer over the term, and keyboard focus on it. */
export interface TipState { hover: boolean; focus: boolean }
export type TipEvent = "enter" | "leave" | "focus" | "blur" | "escape";
export const TIP_CLOSED: TipState = { hover: false, focus: false };

/**
 * Next tooltip state. Escape closes the tooltip without moving the pointer or the focus (WCAG 1.4.13): it stays closed
 * until the pointer enters or the term is focused again.
 */
export function tipReducer(state: TipState, event: TipEvent): TipState {
  switch (event) {
    case "enter": return state.hover ? state : { ...state, hover: true };
    case "leave": return state.hover ? { ...state, hover: false } : state;
    case "focus": return state.focus ? state : { ...state, focus: true };
    case "blur": return state.focus ? { ...state, focus: false } : state;
    case "escape": return state.hover || state.focus ? TIP_CLOSED : state;
  }
}

/** A tooltip shows while the pointer is over its term or the term has focus. */
export const tipOpen = (state: TipState): boolean => state.hover || state.focus;

// --- The clear rectangle of a map that lies under floating panels (the Command exercise replay) ---------------

/** A rectangle in the pixel coordinates of the map container; `right` and `bottom` are edges, not sizes. */
export interface ScreenRect { left: number; top: number; right: number; bottom: number }

/** How close the clear rectangle may come to the map edge, and to a panel. */
export const CLEAR_MARGIN_PX = 12;
export const CLEAR_GAP_PX = 12;
/** A clear rectangle smaller than this is not used: the map falls back to its own edges less the margin. */
export const CLEAR_MIN_PX = { width: 160, height: 120 } as const;

export interface ClearRectOptions { margin?: number; gap?: number; minWidth?: number; minHeight?: number }

const rectArea = (rect: ScreenRect): number => Math.max(0, rect.right - rect.left) * Math.max(0, rect.bottom - rect.top);
const rectsOverlap = (a: ScreenRect, b: ScreenRect): boolean => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

/**
 * The part of a full-screen map that no panel covers, as one rectangle: every pan, fit and popup of the Command
 * exercise replay stays inside it, so a selected thing is never under a panel.
 *
 * `panels` are the measured boxes of the panels drawn over the map (in the map container's coordinates; a hidden
 * panel is left out or has no area). Starting from the map less `margin`, each panel that still reaches into the
 * rectangle takes one side of it away, `gap` clear of the panel: the side whose loss leaves the most map. Panels are
 * taken largest first, so the result does not depend on their order. When the panels leave less than the minimum
 * size, the map less its margin is returned.
 */
export function clearRect(map: { width: number; height: number }, panels: readonly ScreenRect[], options: ClearRectOptions = {}): ScreenRect {
  const margin = options.margin ?? CLEAR_MARGIN_PX;
  const gap = options.gap ?? CLEAR_GAP_PX;
  const base: ScreenRect = { left: margin, top: margin, right: Math.max(margin, map.width - margin), bottom: Math.max(margin, map.height - margin) };
  let rect = base;
  const ordered = panels
    .filter((panel) => panel.right > panel.left && panel.bottom > panel.top)
    .map((panel, index) => ({ panel, index }))
    .sort((a, b) => rectArea(b.panel) - rectArea(a.panel) || a.index - b.index);
  for (const { panel } of ordered) {
    // The panel with its gap; a panel that only touches the rectangle through its gap still moves the edge.
    const padded: ScreenRect = { left: panel.left - gap, top: panel.top - gap, right: panel.right + gap, bottom: panel.bottom + gap };
    if (!rectsOverlap(rect, padded)) continue;
    const cuts: ScreenRect[] = [
      { ...rect, left: Math.max(rect.left, padded.right) },
      { ...rect, right: Math.min(rect.right, padded.left) },
      { ...rect, top: Math.max(rect.top, padded.bottom) },
      { ...rect, bottom: Math.min(rect.bottom, padded.top) },
    ];
    rect = cuts.reduce((best, cut) => (rectArea(cut) > rectArea(best) ? cut : best));
  }
  const tooSmall = rect.right - rect.left < (options.minWidth ?? CLEAR_MIN_PX.width) || rect.bottom - rect.top < (options.minHeight ?? CLEAR_MIN_PX.height);
  return tooSmall ? base : rect;
}

/** Leaflet paddings (`paddingTopLeft`, `paddingBottomRight`) that keep a fit or a pan inside a clear rectangle. */
export function clearRectPadding(rect: ScreenRect, map: { width: number; height: number }): { paddingTopLeft: [number, number]; paddingBottomRight: [number, number] } {
  const whole = (value: number) => Math.max(0, Math.round(value));
  return {
    paddingTopLeft: [whole(rect.left), whole(rect.top)],
    paddingBottomRight: [whole(map.width - rect.right), whole(map.height - rect.bottom)],
  };
}

/**
 * How far the map must be panned (pixels, as Leaflet's `panBy` takes them) so that a point of the map container
 * lies inside `rect`, at least `inset` from its edges. `{ x: 0, y: 0 }` when the point already does. A rectangle
 * narrower than twice the inset brings the point to its middle.
 */
export function panIntoRect(point: { x: number; y: number }, rect: ScreenRect, inset = 0): { x: number; y: number } {
  const along = (value: number, low: number, high: number): number => {
    const from = low + inset;
    const to = high - inset;
    if (from > to) return value - (low + high) / 2;
    if (value < from) return value - from;
    if (value > to) return value - to;
    return 0;
  };
  // Panning by a positive x moves the map content to the left: a point right of the rectangle needs a positive pan.
  return { x: Math.round(along(point.x, rect.left, rect.right)) || 0, y: Math.round(along(point.y, rect.top, rect.bottom)) || 0 };
}

/**
 * Leaflet popup options that keep a popup inside a clear rectangle: the popup body is capped so that popup, chrome
 * and tip fit in it, and the auto-pan paddings are the panels around it.
 */
export function popupFitInRect(rect: ScreenRect, map: { width: number; height: number }, preferredWidth: number): PopupFit {
  const { paddingTopLeft, paddingBottomRight } = clearRectPadding(rect, map);
  const width = Math.floor(rect.right - rect.left - POPUP_CHROME_PX.x);
  const height = Math.floor(rect.bottom - rect.top - POPUP_CHROME_PX.y);
  return {
    maxWidth: Math.max(POPUP_MIN_WIDTH_PX, Math.min(preferredWidth, width)),
    maxHeight: Math.max(POPUP_MIN_HEIGHT_PX, Math.min(POPUP_MAX_HEIGHT_PX, height)),
    autoPanPaddingTopLeft: paddingTopLeft,
    autoPanPaddingBottomRight: paddingBottomRight,
  };
}
