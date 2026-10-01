import { describe, expect, it } from "vitest";

import {
  POPUP_CHROME_PX,
  POPUP_MAX_HEIGHT_PX,
  POPUP_MIN_HEIGHT_PX,
  POPUP_MIN_WIDTH_PX,
  POPUP_NARROW_MAP_PX,
  popupFit,
  ZOOM_CLEARANCE_PX,
  TIP_CLOSED,
  tipOpen,
  tipReducer,
  tooltipShift,
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
