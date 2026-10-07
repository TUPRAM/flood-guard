import { describe, expect, it } from "vitest";

import {
  CLEAR_GAP_PX,
  CLEAR_MARGIN_PX,
  CLEAR_MIN_PX,
  clearRect,
  clearRectPadding,
  COMPARE_LABEL_GAP_PX,
  COMPARE_LABEL_MIN_PX,
  compareLabelRoom,
  panIntoRect,
  POPUP_CHROME_PX,
  POPUP_MAX_HEIGHT_PX,
  POPUP_MIN_HEIGHT_PX,
  POPUP_MIN_WIDTH_PX,
  POPUP_NARROW_MAP_PX,
  popupFit,
  popupFitInRect,
  ZOOM_CLEARANCE_PX,
  TIP_CLOSED,
  tipOpen,
  tipReducer,
  tooltipShift,
  type ScreenRect,
  type TipEvent,
} from "./flood-timeline-layout";

/** Zoom control on the map: 10 px margin, and 48 px wide (44 px buttons plus their border). */
const ZOOM_RIGHT_EDGE = 58;

describe("map popup fit", () => {
  it("keeps the page's usual paddings and popup widths on a wide map", () => {
    const fit = popupFit({ mapWidth: 900, mapHeight: 700, preferredWidth: 300, bottomReserved: 18 });
    expect(fit.autoPanPaddingTopLeft).toEqual([ZOOM_CLEARANCE_PX, 96]);
    expect(ZOOM_CLEARANCE_PX).toBeGreaterThan(ZOOM_RIGHT_EDGE);
    expect(fit.autoPanPaddingBottomRight).toEqual([24, 48]);
    expect(fit.maxWidth).toBe(300);
    expect(fit.maxHeight).toBe(POPUP_MAX_HEIGHT_PX);
    // A tall stack over the attribution (note and button) pushes the bottom padding up.
    expect(popupFit({ mapWidth: 900, mapHeight: 700, preferredWidth: 300, bottomReserved: 120 }).autoPanPaddingBottomRight).toEqual([24, 128]);
  });

  it("fits popup, paddings and tip inside a phone-sized map, clear of the zoom control and the bottom stack", () => {
    // Map widths at 360 and 390 px viewports (16 px page padding), and the page's phone map heights.
    for (const mapWidth of [328, 358]) {
      for (const mapHeight of [340, 371, 464, 490, 560]) {
        for (const bottomReserved of [18, 36, 52, 150]) {
          for (const preferredWidth of [280, 290, 300]) {
            const fit = popupFit({ mapWidth, mapHeight, preferredWidth, bottomReserved });
            const [left, top] = fit.autoPanPaddingTopLeft;
            const [right, bottom] = fit.autoPanPaddingBottomRight;
            const label = JSON.stringify({ mapWidth, mapHeight, bottomReserved, preferredWidth, fit });
            expect(mapWidth, label).toBeLessThan(POPUP_NARROW_MAP_PX);
            expect(left, label).toBeGreaterThan(ZOOM_RIGHT_EDGE);
            expect(bottom, label).toBeGreaterThanOrEqual(bottomReserved + 8);
            // Across: left padding, popup body with Leaflet's margins, right padding.
            expect(left + fit.maxWidth + POPUP_CHROME_PX.x + right, label).toBeLessThanOrEqual(mapWidth);
            // Down: top padding, popup body with its wrapper and tip, bottom padding.
            expect(top + fit.maxHeight + POPUP_CHROME_PX.y + bottom, label).toBeLessThanOrEqual(mapHeight);
            expect(fit.maxWidth, label).toBeLessThanOrEqual(preferredWidth);
            expect(fit.maxWidth, label).toBeGreaterThanOrEqual(POPUP_MIN_WIDTH_PX);
            expect(fit.maxHeight, label).toBeLessThanOrEqual(POPUP_MAX_HEIGHT_PX);
            expect(fit.maxHeight, label).toBeGreaterThanOrEqual(POPUP_MIN_HEIGHT_PX);
          }
        }
      }
    }
  });

  it("never asks for less than a readable popup, however small the map is", () => {
    const fit = popupFit({ mapWidth: 200, mapHeight: 120, preferredWidth: 300, bottomReserved: 60 });
    expect(fit.maxWidth).toBe(POPUP_MIN_WIDTH_PX);
    expect(fit.maxHeight).toBe(POPUP_MIN_HEIGHT_PX);
    // A negative or fractional reserve is treated as none, or rounded up.
    expect(popupFit({ mapWidth: 328, mapHeight: 464, preferredWidth: 300, bottomReserved: -5 }).autoPanPaddingBottomRight[1]).toBe(8);
    expect(popupFit({ mapWidth: 328, mapHeight: 464, preferredWidth: 300, bottomReserved: 35.2 }).autoPanPaddingBottomRight[1]).toBe(44);
  });
});

describe("glossary tooltip", () => {
  it("is moved sideways just enough to stay inside the viewport, at 360 px and wider", () => {
    for (const viewport of [360, 390, 1440]) {
      for (const width of [120, 252, 288]) {
        for (let left = -40; left <= viewport; left += 7) {
          const shift = tooltipShift(left, left + width, viewport);
          const label = JSON.stringify({ viewport, width, left, shift });
          expect(left + shift, label).toBeGreaterThanOrEqual(8);
          expect(left + width + shift, label).toBeLessThanOrEqual(viewport - 8);
          // A box that already fits is left where it is.
          if (left >= 8 && left + width <= viewport - 8) expect(shift, label).toBe(0);
        }
      }
    }
    // The case the phone audit found: a term near the right edge of a 360 px screen.
    expect(tooltipShift(230, 230 + 252, 360)).toBe(-130);
    expect(tooltipShift(4, 104, 360)).toBe(4);
    // Wider than the viewport: pinned to the left margin (it then wraps or scrolls, never starts off-screen).
    expect(tooltipShift(100, 500, 360)).toBe(-92);
    expect(tooltipShift(100, 500, 360, 16)).toBe(-84);
  });

  it("opens on hover or focus and closes on Escape without moving the pointer or the focus", () => {
    const run = (...events: TipEvent[]) => events.reduce(tipReducer, TIP_CLOSED);
    expect(tipOpen(TIP_CLOSED)).toBe(false);
    expect(tipOpen(run("enter"))).toBe(true);
    expect(tipOpen(run("focus"))).toBe(true);
    expect(tipOpen(run("enter", "leave"))).toBe(false);
    expect(tipOpen(run("focus", "blur"))).toBe(false);
    // Hover and focus each keep it open on their own.
    expect(tipOpen(run("enter", "focus", "leave"))).toBe(true);
    expect(tipOpen(run("enter", "focus", "blur"))).toBe(true);
    // Escape closes it whatever opened it, and it stays closed while the pointer and the focus stay put.
    expect(tipOpen(run("focus", "escape"))).toBe(false);
    expect(tipOpen(run("enter", "escape"))).toBe(false);
    expect(tipOpen(run("enter", "focus", "escape"))).toBe(false);
    // It opens again once the pointer comes back or the term is focused again.
    expect(tipOpen(run("focus", "escape", "blur", "focus"))).toBe(true);
    expect(tipOpen(run("enter", "escape", "leave", "enter"))).toBe(true);
    // Events that change nothing return the same state, so the page does not re-render.
    const open = run("enter");
    expect(tipReducer(open, "enter")).toBe(open);
    expect(tipReducer(TIP_CLOSED, "escape")).toBe(TIP_CLOSED);
    expect(tipReducer(TIP_CLOSED, "leave")).toBe(TIP_CLOSED);
    expect(tipReducer(TIP_CLOSED, "blur")).toBe(TIP_CLOSED);
  });
});

describe("imagery swipe side labels", () => {
  it("keeps the left label clear of the zoom control and both labels clear of the divider", () => {
    // A 326 px map (a 360 px phone) with the divider in the middle: 163 px a side.
    const half = compareLabelRoom(326, 50);
    expect(half).toEqual({ left: 163 - COMPARE_LABEL_GAP_PX.divider - ZOOM_CLEARANCE_PX, right: 163 - COMPARE_LABEL_GAP_PX.divider - COMPARE_LABEL_GAP_PX.edge });
    // The left label's box starts at the divider minus the gap minus its room: never left of the zoom clearance.
    for (const width of [326, 356, 600, 1016]) {
      for (const pct of [15, 30, 50, 70, 85]) {
        const room = compareLabelRoom(width, pct);
        const divider = (width * pct) / 100;
        expect(divider - COMPARE_LABEL_GAP_PX.divider - room.left, `${width}px ${pct}%`).toBeGreaterThanOrEqual(Math.min(ZOOM_CLEARANCE_PX, divider - COMPARE_LABEL_GAP_PX.divider));
        expect(divider + COMPARE_LABEL_GAP_PX.divider + room.right, `${width}px ${pct}%`).toBeLessThanOrEqual(width - COMPARE_LABEL_GAP_PX.edge + 1e-9);
      }
    }
    expect(ZOOM_CLEARANCE_PX).toBeGreaterThan(ZOOM_RIGHT_EDGE);
  });

  it("gives a side no label when less than the minimum width is left, instead of a tall sliver", () => {
    // On a phone the left side loses its label first, because the zoom control takes 64 px of it.
    expect(compareLabelRoom(326, 30).left).toBeLessThan(COMPARE_LABEL_MIN_PX);
    expect(compareLabelRoom(326, 30).right).toBeGreaterThanOrEqual(COMPARE_LABEL_MIN_PX);
    expect(compareLabelRoom(326, 50).left).toBeGreaterThanOrEqual(COMPARE_LABEL_MIN_PX);
    expect(compareLabelRoom(326, 80).right).toBeLessThan(COMPARE_LABEL_MIN_PX);
    // On a desktop map both sides have room over the whole 15–85 % range the labels are offered in.
    for (const pct of [15, 50, 85]) {
      const room = compareLabelRoom(1016, pct);
      expect(Math.min(room.left, room.right), `${pct}%`).toBeGreaterThanOrEqual(COMPARE_LABEL_MIN_PX);
    }
    // Never negative, whatever the input.
    expect(compareLabelRoom(0, 50)).toEqual({ left: 0, right: 0 });
    expect(compareLabelRoom(326, -20)).toEqual({ left: 0, right: 300 });
    expect(compareLabelRoom(326, 140)).toEqual({ left: 246, right: 0 });
  });
});

// The Command exercise replay at its two design sizes. The map fills the screen under the banner, so the boxes below
// are in the map's own coordinates: the screen's less the banner (36 px on the desktop, 44 px on the tablet).
const DESKTOP = { width: 1440, height: 764 };
const desktop = {
  clock: { left: 12, top: 12, right: 432, bottom: 176 },
  table: { left: 12, top: 184, right: 432, bottom: 656 },
  nav: { left: 1028, top: 12, right: 1428, bottom: 56 },
  rail: { left: 1384, top: 194, right: 1428, bottom: 522 },
  dock: { left: 12, top: 664, right: 1428, bottom: 752 },
} satisfies Record<string, ScreenRect>;
const TABLET = { width: 1024, height: 656 };
const tablet = {
  clock: { left: 12, top: 12, right: 332, bottom: 128 },
  table: { left: 12, top: 136, right: 332, bottom: 552 },
  menu: { left: 968, top: 12, right: 1012, bottom: 56 },
  rail: { left: 968, top: 186, right: 1012, bottom: 470 },
  dock: { left: 12, top: 572, right: 1012, bottom: 644 },
} satisfies Record<string, ScreenRect>;
const width = (rect: ScreenRect) => rect.right - rect.left;
const height = (rect: ScreenRect) => rect.bottom - rect.top;
const inside = (inner: ScreenRect, outer: ScreenRect) => inner.left >= outer.left && inner.top >= outer.top && inner.right <= outer.right && inner.bottom <= outer.bottom;
const overlaps = (a: ScreenRect, b: ScreenRect) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;

describe("clear rectangle of a map under floating panels", () => {
  it("is the map less its margin when nothing covers it", () => {
    expect(clearRect(DESKTOP, [])).toEqual({ left: CLEAR_MARGIN_PX, top: CLEAR_MARGIN_PX, right: 1440 - CLEAR_MARGIN_PX, bottom: 764 - CLEAR_MARGIN_PX });
    // A hidden panel has no area and takes nothing away.
    expect(clearRect(DESKTOP, [{ left: 0, top: 0, right: 0, bottom: 0 }])).toEqual(clearRect(DESKTOP, []));
  });

  it("leaves the plan's 928 px of clear map between the left column and the tool rail on the desktop", () => {
    const rect = clearRect(DESKTOP, Object.values(desktop));
    expect(rect).toEqual({ left: 432 + CLEAR_GAP_PX, top: 56 + CLEAR_GAP_PX, right: 1384 - CLEAR_GAP_PX, bottom: 664 - CLEAR_GAP_PX });
    expect(width(rect)).toBe(928);
    expect(height(rect)).toBe(584);
    for (const panel of Object.values(desktop)) expect(overlaps(rect, panel)).toBe(false);
    // The order of the panels does not change the result.
    expect(clearRect(DESKTOP, Object.values(desktop).reverse())).toEqual(rect);
  });

  it("gives up width, not height, for a card or an open legend beside the tool rail", () => {
    const rest = clearRect(DESKTOP, Object.values(desktop));
    // The right card of a later stage: 340 px wide, left of the rail, under the navigation.
    const card = { left: 1036, top: 64, right: 1376, bottom: 584 };
    const withCard = clearRect(DESKTOP, [...Object.values(desktop), card]);
    // With the card open the rectangle ends left of the navigation too, so it keeps the height under the banner.
    expect(withCard).toEqual({ ...rest, top: CLEAR_MARGIN_PX, right: desktop.nav.left - CLEAR_GAP_PX });
    expect(width(withCard)).toBe(572);
    for (const panel of [...Object.values(desktop), card]) expect(overlaps(withCard, panel)).toBe(false);
    // The open legend: 280 x 240 at the bottom right, left of the rail.
    const legend = { left: 1096, top: 416, right: 1376, bottom: 656 };
    const withLegend = clearRect(DESKTOP, [...Object.values(desktop), legend]);
    expect(withLegend).toEqual({ ...rest, right: legend.left - CLEAR_GAP_PX });
    expect(overlaps(withLegend, legend)).toBe(false);
  });

  it("opens up in focus mode, where the left column and the time dock are one line each", () => {
    const focus = [
      { left: 12, top: 12, right: 432, bottom: 56 }, { left: 12, top: 64, right: 432, bottom: 108 },
      desktop.nav, desktop.rail, { left: 12, top: 708, right: 1428, bottom: 752 },
    ];
    const rect = clearRect(DESKTOP, focus);
    expect(rect).toEqual({ left: CLEAR_MARGIN_PX, top: 108 + CLEAR_GAP_PX, right: 1384 - CLEAR_GAP_PX, bottom: 708 - CLEAR_GAP_PX });
    expect(width(rect) * height(rect)).toBeGreaterThan(1.4 * 928 * 584);
    for (const panel of focus) expect(overlaps(rect, panel)).toBe(false);
  });

  it("leaves the plan's 612 px on the tablet, with the menu button above the rail", () => {
    const rect = clearRect(TABLET, Object.values(tablet));
    expect(rect).toEqual({ left: 332 + CLEAR_GAP_PX, top: CLEAR_MARGIN_PX, right: 968 - CLEAR_GAP_PX, bottom: 572 - CLEAR_GAP_PX });
    expect(width(rect)).toBe(612);
    for (const panel of Object.values(tablet)) expect(overlaps(rect, panel)).toBe(false);
  });

  it("falls back to the map less its margin when the panels leave too little", () => {
    const small = { width: 400, height: 300 };
    const covered = [{ left: 0, top: 0, right: 300, bottom: 300 }, { left: 300, top: 0, right: 400, bottom: 250 }];
    const rect = clearRect(small, covered);
    expect(rect).toEqual({ left: CLEAR_MARGIN_PX, top: CLEAR_MARGIN_PX, right: 400 - CLEAR_MARGIN_PX, bottom: 300 - CLEAR_MARGIN_PX });
    expect(width(rect)).toBeGreaterThanOrEqual(CLEAR_MIN_PX.width);
    // A map smaller than twice the margin never gives a rectangle turned inside out.
    const tiny = clearRect({ width: 10, height: 10 }, []);
    expect(tiny.right).toBeGreaterThanOrEqual(tiny.left);
    expect(tiny.bottom).toBeGreaterThanOrEqual(tiny.top);
  });

  it("turns into Leaflet paddings for a fit or a pan", () => {
    const rect = clearRect(DESKTOP, Object.values(desktop));
    expect(clearRectPadding(rect, DESKTOP)).toEqual({ paddingTopLeft: [444, 68], paddingBottomRight: [1440 - 1372, 764 - 652] });
    expect(clearRectPadding({ left: -4, top: 2.4, right: 2000, bottom: 700.6 }, DESKTOP)).toEqual({ paddingTopLeft: [0, 2], paddingBottomRight: [0, 63] });
  });

  it("pans a point under a panel into the clear rectangle, and leaves a point inside it alone", () => {
    const rect = clearRect(DESKTOP, Object.values(desktop));
    expect(panIntoRect({ x: 700, y: 300 }, rect)).toEqual({ x: 0, y: 0 });
    // Under the table (left of the rectangle): the map content must move right, a negative pan.
    expect(panIntoRect({ x: 200, y: 300 }, rect, 24)).toEqual({ x: 200 - (444 + 24), y: 0 });
    // Under the dock and the rail at once.
    expect(panIntoRect({ x: 1400, y: 700 }, rect, 24)).toEqual({ x: 1400 - (1372 - 24), y: 700 - (652 - 24) });
    // After the pan the point lies inside the rectangle.
    for (const point of [{ x: 0, y: 0 }, { x: 1439, y: 763 }, { x: 200, y: 700 }]) {
      const pan = panIntoRect(point, rect, 24);
      const moved = { left: point.x - pan.x, top: point.y - pan.y, right: point.x - pan.x, bottom: point.y - pan.y };
      expect(inside(moved, rect)).toBe(true);
    }
    // A rectangle narrower than twice the inset brings the point to its middle.
    expect(panIntoRect({ x: 0, y: 0 }, { left: 100, top: 100, right: 120, bottom: 300 }, 24)).toEqual({ x: -110, y: -124 });
  });

  it("sizes a popup and its pan paddings for the clear rectangle", () => {
    const rect = clearRect(DESKTOP, Object.values(desktop));
    const fit = popupFitInRect(rect, DESKTOP, 300);
    expect(fit.maxWidth).toBe(300);
    expect(fit.maxHeight).toBe(POPUP_MAX_HEIGHT_PX);
    expect(fit.autoPanPaddingTopLeft).toEqual([444, 68]);
    expect(fit.autoPanPaddingBottomRight).toEqual([68, 112]);
    // A small rectangle caps the popup so that popup, chrome and tip fit inside it.
    const tight = popupFitInRect({ left: 20, top: 20, right: 260, bottom: 240 }, { width: 280, height: 260 }, 300);
    expect(tight.maxWidth).toBe(240 - POPUP_CHROME_PX.x);
    expect(tight.maxHeight).toBe(220 - POPUP_CHROME_PX.y);
    expect(popupFitInRect({ left: 0, top: 0, right: 100, bottom: 60 }, { width: 100, height: 60 }, 300)).toMatchObject({ maxWidth: POPUP_MIN_WIDTH_PX, maxHeight: POPUP_MIN_HEIGHT_PX });
  });
});
