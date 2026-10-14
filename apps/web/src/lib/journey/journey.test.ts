import { describe, expect, it } from "vitest";

import { solveReach, type Point } from "./reach";
import { applyHomography, quadIsDrawable, quadToMatrix3d, squareToQuad, type Quad } from "./screen-projection";
import { LAYOUT, WATER_LEVEL, floodedRoadRanges, isUnderWater, roadHeight, terrainHeight } from "./terrain";
import {
  TIMELINE_END,
  chapterAt,
  chapterEntry,
  chapterStart,
  clampScrollTarget,
  locate,
  nextStopAfter,
  parseScene,
  previousStopBefore,
  sceneAt,
  scenePosition,
  stepToward,
  stopAt,
  stopPosition,
  storyBeats,
} from "./timeline";

describe("journey timeline", () => {
  it("places the four real-page stops in story order", () => {
    const stops = ["public", "public-prepare", "case", "command"] as const;
    const positions = stops.map(stopPosition);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    expect(stopPosition("command")).toBe(TIMELINE_END);
  });

  it("locates segments and progress", () => {
    expect(locate(0)).toMatchObject({ segment: "opening", progress: 0, chapter: "opening" });
    expect(locate(0.5).progress).toBeCloseTo(0.5);
    expect(locate(stopPosition("public"))).toMatchObject({ segment: "enter-phone", progress: 1 });
    expect(locate(TIMELINE_END + 5)).toMatchObject({ segment: "aerial", progress: 1 });
    expect(locate(-3)).toMatchObject({ segment: "opening", progress: 0 });
  });

  it("assigns stops to the chapter that leads into them", () => {
    expect(chapterAt(stopPosition("public"))).toBe("everyday");
    expect(chapterAt(stopPosition("public-prepare"))).toBe("conditions");
    expect(chapterAt(stopPosition("case"))).toBe("affected");
    expect(chapterAt(stopPosition("command"))).toBe("response");
    expect(chapterStart("conditions")).toBeCloseTo(stopPosition("public"));
  });

  it("enters a chapter just past a boundary stop, so chapter links never dock the previous page", () => {
    for (const chapter of ["conditions", "affected", "response"] as const) {
      expect(stopAt(chapterEntry(chapter))).toBeNull();
      expect(chapterAt(chapterEntry(chapter))).toBe(chapter);
    }
    expect(chapterEntry("everyday")).toBe(chapterStart("everyday"));
    expect(stopAt(scenePosition("conditions"))).toBeNull();
  });

  it("does not let scrolling pass a stop, but scrolling back is free", () => {
    const publicStop = stopPosition("public");
    expect(clampScrollTarget(0.2, 99)).toBeCloseTo(publicStop);
    expect(clampScrollTarget(publicStop, publicStop + 0.5)).toBeCloseTo(publicStop + 0.5);
    expect(clampScrollTarget(publicStop, 99)).toBeCloseTo(stopPosition("public-prepare"));
    expect(clampScrollTarget(stopPosition("case"), 0.3)).toBeCloseTo(0.3);
    expect(clampScrollTarget(1, -4)).toBe(0);
  });

  it("finds neighbouring stops", () => {
    expect(nextStopAfter(0)).toBe("public");
    expect(nextStopAfter(stopPosition("public"))).toBe("public-prepare");
    expect(previousStopBefore(stopPosition("case"))).toBe("public-prepare");
    expect(nextStopAfter(TIMELINE_END)).toBeNull();
    expect(stopAt(stopPosition("case"))).toBe("case");
    expect(stopAt(stopPosition("case") - 0.01)).toBeNull();
  });

  it("moves the display toward the target without overshoot and within the speed cap", () => {
    let display = 0;
    const target = 2;
    for (let i = 0; i < 2000; i += 1) {
      const next = stepToward(display, target, 1 / 60);
      expect(next - display).toBeLessThanOrEqual(0.32 / 60 + 1e-9);
      expect(next).toBeLessThanOrEqual(target);
      display = next;
    }
    expect(display).toBe(target);
    expect(stepToward(1, 0.5, 1 / 60)).toBeLessThan(1);
  });

  it("gives reduced motion beats that reach every stop, in order", () => {
    const beats = storyBeats();
    expect([...beats].sort((a, b) => a - b)).toEqual(beats);
    for (const stop of ["public", "public-prepare", "case", "command"] as const) expect(beats).toContain(stopPosition(stop));
    expect(beats.at(-1)).toBe(TIMELINE_END);
  });

  it("round-trips scenes through the address bar", () => {
    expect(parseScene("?scene=case")).toBe("case");
    expect(parseScene("?scene=affected")).toBe("affected");
    expect(parseScene("?scene=nope")).toBeNull();
    expect(sceneAt(stopPosition("command"))).toBe("command");
    expect(sceneAt(scenePosition("conditions") + 0.3)).toBe("conditions");
  });
});

describe("screen projection", () => {
  const quad: Quad = [{ x: 120, y: 40 }, { x: 410, y: 70 }, { x: 390, y: 520 }, { x: 100, y: 470 }];

  it("maps the unit square corners onto the quad", () => {
    const m = squareToQuad(quad);
    const corners = [[0, 0], [1, 0], [1, 1], [0, 1]].map(([u, v]) => applyHomography(m, u, v));
    corners.forEach((corner, i) => {
      expect(corner.x).toBeCloseTo(quad[i].x, 6);
      expect(corner.y).toBeCloseTo(quad[i].y, 6);
    });
  });

  it("reduces to a plain scale and translation for an axis-aligned rectangle", () => {
    const css = quadToMatrix3d(390, 844, [{ x: 0, y: 0 }, { x: 390, y: 0 }, { x: 390, y: 844 }, { x: 0, y: 844 }]);
    expect(css).toBe("matrix3d(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)");
  });

  it("rejects degenerate and non-convex quads", () => {
    expect(quadIsDrawable(quad, 1440, 900)).toBe(true);
    expect(quadIsDrawable([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 0, y: 10 }, { x: 10, y: 10 }], 1440, 900)).toBe(false);
    expect(quadIsDrawable([{ x: 0, y: 0 }, { x: 0, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }], 1440, 900)).toBe(false);
  });
});

describe("illustrative terrain", () => {
  it("keeps the home and the clinic dry in every water state", () => {
    for (const place of [LAYOUT.home, LAYOUT.clinic, LAYOUT.resident]) {
      for (const level of Object.values(WATER_LEVEL)) {
        expect(terrainHeight(place.x, place.z)).toBeGreaterThan(level + 0.4);
      }
    }
  });

  it("keeps the road dry while conditions rise, then covers one stretch of it", () => {
    expect(floodedRoadRanges("dry")).toEqual([]);
    expect(floodedRoadRanges("rising")).toEqual([]);
    const affected = floodedRoadRanges("affected");
    expect(affected).toHaveLength(1);
    const [start, end] = affected[0];
    expect(end - start).toBeGreaterThan(3);
    expect(end - start).toBeLessThan(20);
    expect(start).toBeGreaterThan(LAYOUT.homeGate.x + 5);
    expect(end).toBeLessThan(LAYOUT.clinicGate.x - 5);
    // The covered stretch is a shallow crossing, not a deep channel.
    expect(WATER_LEVEL.affected - (roadHeight((start + end) / 2) - 0.06)).toBeLessThan(0.6);
  });

  it("puts standing water on the floodplain when conditions rise", () => {
    expect(isUnderWater(0, 26, "dry")).toBe(false);
    expect(isUnderWater(0, 26, "rising")).toBe(true);
  });
});

describe("two-bone reach", () => {
  const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  const shoulder: Point = { x: 0.2, y: 1.1, z: 0 };
  const upper = 0.28, lower = 0.23;

  it("puts the wrist on a target within reach and keeps both bone lengths", () => {
    const target: Point = { x: 0.1, y: 0.85, z: 0.3 };
    const reach = solveReach(shoulder, target, { x: 0.5, y: 0.2, z: -0.3 }, upper, lower);
    expect(reach.reached).toBe(true);
    expect(distance(reach.end, target)).toBeLessThan(1e-9);
    expect(distance(shoulder, reach.joint)).toBeCloseTo(upper, 9);
    expect(distance(reach.joint, reach.end)).toBeCloseTo(lower, 9);
  });

  it("bends the elbow toward the pole", () => {
    const target: Point = { x: 0.2, y: 1.1, z: 0.4 };
    const down = solveReach(shoulder, target, { x: 0.2, y: 0, z: 0.2 }, upper, lower);
    const out = solveReach(shoulder, target, { x: 1.2, y: 1.1, z: 0.2 }, upper, lower);
    expect(down.joint.y).toBeLessThan(shoulder.y - 0.05);
    expect(down.joint.x).toBeCloseTo(shoulder.x, 9);
    expect(out.joint.x).toBeGreaterThan(shoulder.x + 0.05);
    expect(out.joint.y).toBeCloseTo(shoulder.y, 9);
  });

  it("approaches a target that is too far along the same line, without straightening fully", () => {
    const target: Point = { x: 0.2, y: 1.1, z: 2 };
    const reach = solveReach(shoulder, target, { x: 0.2, y: 0, z: 0.2 }, upper, lower);
    expect(reach.reached).toBe(false);
    expect(reach.end.x).toBeCloseTo(shoulder.x, 9);
    expect(reach.end.y).toBeCloseTo(shoulder.y, 9);
    expect(reach.end.z).toBeGreaterThan(0.5);
    expect(distance(shoulder, reach.end)).toBeLessThan(upper + lower);
    expect(distance(shoulder, reach.joint)).toBeCloseTo(upper, 9);
    expect(distance(reach.joint, reach.end)).toBeCloseTo(lower, 9);
  });

  it("stays finite when the target or the pole gives no direction", () => {
    for (const reach of [
      solveReach(shoulder, shoulder, { x: 1, y: 1, z: 1 }, upper, lower),
      solveReach(shoulder, { x: 0.2, y: 0.8, z: 0 }, { x: 0.2, y: 0.3, z: 0 }, upper, lower),
    ]) {
      for (const value of [...Object.values(reach.joint), ...Object.values(reach.end)]) expect(Number.isFinite(value)).toBe(true);
      expect(distance(shoulder, reach.joint)).toBeCloseTo(upper, 9);
      expect(distance(reach.joint, reach.end)).toBeCloseTo(lower, 9);
    }
  });
});
