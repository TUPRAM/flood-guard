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
