import { describe, expect, it } from "vitest";

import { PRACTICE_SCENARIOS } from "@/lib/public-practice-scenarios";

import { solveReach, type Point } from "./reach";
import { applyHomography, quadIsDrawable, quadToMatrix3d, squareToQuad, type Quad } from "./screen-projection";
import { LAYOUT, WATER_LEVEL, floodedRoadRanges, isUnderWater, roadHeight, terrainHeight } from "./terrain";
import {
  CHAPTERS,
  STOP_HOURS,
  STOP_IDS,
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
  phoneAt,
  practiceForHour,
  replayHourAt,
  segmentRange,
  storyBeats,
  storyHours,
  veilAt,
  skyHoursAt,
} from "./timeline";
import { nightAt, skyAt } from "./sky";

describe("journey timeline", () => {
  it("places the four real-page stops in story order, with the closing chapter after the last one", () => {
    const positions = STOP_IDS.map(stopPosition);
    expect(STOP_IDS).toEqual(["public", "public-prepare", "case", "command"]);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
    expect(segmentRange("after").start).toBeCloseTo(stopPosition("command"));
    expect(segmentRange("after").end).toBe(TIMELINE_END);
  });

  it("locates segments and progress", () => {
    expect(locate(0)).toMatchObject({ segment: "opening", progress: 0, chapter: "opening" });
    expect(locate(0.5).progress).toBeCloseTo(0.5);
    expect(locate(stopPosition("public"))).toMatchObject({ segment: "enter-phone", progress: 1 });
    expect(locate(TIMELINE_END + 5)).toMatchObject({ segment: "after", progress: 1 });
    expect(locate(-3)).toMatchObject({ segment: "opening", progress: 0 });
  });

  it("assigns stops to the chapter that leads into them", () => {
    expect(chapterAt(stopPosition("public"))).toBe("everyday");
    expect(chapterAt(stopPosition("public-prepare"))).toBe("conditions");
    expect(chapterAt(stopPosition("case"))).toBe("affected");
    expect(chapterAt(stopPosition("command"))).toBe("response");
    expect(chapterStart("conditions")).toBeCloseTo(stopPosition("public"));
  });

  it("enters a chapter inside its own picture: past a boundary stop and past a dip to dark", () => {
    for (const chapter of CHAPTERS) {
      const entry = chapterEntry(chapter);
      expect(stopAt(entry), chapter).toBeNull();
      expect(chapterAt(entry), chapter).toBe(chapter);
      expect(veilAt(entry), chapter).toBe(0);
      // Just past the dip to dark at most (6 to 7% of the first segment).
      expect(entry - chapterStart(chapter), chapter).toBeLessThan(0.3);
    }
    expect(chapterEntry("opening")).toBe(0);
    expect(stopAt(scenePosition("conditions"))).toBeNull();
    // 04 opens on the cut-off, not on the last frame of the night behind the dip to dark.
    expect(sceneAt(chapterEntry("affected"))).toBe("affected");
  });

  it("dips to dark smoothly: never more than a fifth darker or lighter between two close positions", () => {
    for (let t = 0; t <= TIMELINE_END; t += 0.002) expect(Math.abs(veilAt(t + 0.002) - veilAt(t)), `t ${t.toFixed(3)}`).toBeLessThan(0.2);
    // Each cut in time happens under full dark.
    expect(veilAt(segmentRange("cut-off").start + 1e-4)).toBeGreaterThan(0.99);
    expect(Math.max(...[0.02, 0.03, 0.04].map((p) => veilAt(segmentRange("after").start + p * 2.6)))).toBe(1);
  });

  it("blends the sky's light (not its hour) from the Public app into Tuesday afternoon, never through a night", () => {
    const { start, end } = segmentRange("conditions");
    const at = (p: number) => start + p * (end - start);
    const first = skyAt(at(1e-4)), settled = skyAt(at(0.12));
    expect(first.night).toBeCloseTo(nightAt(STOP_HOURS.public), 3);
    expect(settled.night).toBe(nightAt(replayHourAt(at(0.12))));
    const ceiling = Math.max(nightAt(STOP_HOURS.public), nightAt(replayHourAt(at(0.1))));
    let previousRain = first.rain;
    for (let p = 0.005; p <= 0.1; p += 0.005) {
      const sky = skyAt(at(p));
      expect(sky.night, `p ${p}`).toBeLessThanOrEqual(ceiling + 1e-9);
      expect(sky.rain, `p ${p}`).toBeGreaterThanOrEqual(previousRain - 1e-9);
      previousRain = sky.rain;
    }
    // Into chapter 06 the dip to dark covers the cut: no blend, and the clock skips only under full dark.
    const after = segmentRange("after");
    expect(skyHoursAt(after.start + 0.01).weight).toBe(1);
    expect(replayHourAt(after.start + 0.01)).toBe(STOP_HOURS.command);
    expect(replayHourAt(after.start + 0.05 * (after.end - after.start))).toBeGreaterThanOrEqual(130);
    expect(veilAt(after.start + 0.031 * (after.end - after.start))).toBe(1);
  });

  it("does not let scrolling pass a stop, but scrolling back is free", () => {
    const publicStop = stopPosition("public");
    expect(clampScrollTarget(0.2, 99)).toBeCloseTo(publicStop);
    expect(clampScrollTarget(publicStop, publicStop + 0.5)).toBeCloseTo(publicStop + 0.5);
    expect(clampScrollTarget(publicStop, 99)).toBeCloseTo(stopPosition("public-prepare"));
    expect(clampScrollTarget(stopPosition("case"), 0.3)).toBeCloseTo(0.3);
    expect(clampScrollTarget(stopPosition("command"), 99)).toBe(TIMELINE_END);
    expect(clampScrollTarget(1, -4)).toBe(0);
  });

  it("finds neighbouring stops", () => {
    expect(nextStopAfter(0)).toBe("public");
    expect(nextStopAfter(stopPosition("public"))).toBe("public-prepare");
    expect(previousStopBefore(stopPosition("case"))).toBe("public-prepare");
    expect(nextStopAfter(stopPosition("command"))).toBeNull();
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

  it("gives reduced motion beats that reach every stop and the closing scene, in order", () => {
    const beats = storyBeats();
    expect([...beats].sort((a, b) => a - b)).toEqual(beats);
    for (const stop of STOP_IDS) expect(beats).toContain(stopPosition(stop));
    expect(beats.at(-1)).toBe(TIMELINE_END);
  });

  it("round-trips scenes through the address bar, old chapter ids included", () => {
    expect(parseScene("?scene=case")).toBe("case");
    expect(parseScene("?scene=affected")).toBe("affected");
    expect(parseScene("?scene=night")).toBe("night");
    expect(parseScene("?scene=after")).toBe("after");
    expect(parseScene("?scene=nope")).toBeNull();
    expect(sceneAt(stopPosition("command"))).toBe("command");
    expect(sceneAt(scenePosition("conditions") + 0.3)).toBe("conditions");
  });
});

describe("journey replay time", () => {
  it("runs at the Public app's practice-scenario hours", () => {
    for (const scenario of PRACTICE_SCENARIOS.filter((entry) => entry.home === "dry")) {
      expect(storyHours(), scenario.id).toContain(scenario.hour);
      expect(practiceForHour(scenario.hour)).toBe(scenario.id);
    }
    expect(practiceForHour(49)).toBe("reach_at_risk");
    expect(practiceForHour(0)).toBe("normal");
  });

  it("opens each real page at the hour of the scene around it", () => {
    for (const stop of STOP_IDS) expect(replayHourAt(stopPosition(stop))).toBe(STOP_HOURS[stop]);
    expect(STOP_HOURS).toEqual({ public: 12, "public-prepare": 40, case: 84, command: 84 });
  });

  it("only moves forward in time, and only skips ahead behind a page or a dip to dark", () => {
    let previous = replayHourAt(0);
    for (let t = 0; t <= TIMELINE_END + 1e-9; t += 0.005) {
      const hour = replayHourAt(t);
      expect(hour).toBeGreaterThanOrEqual(previous - 1e-9);
      if (hour - previous > 1) {
        // A skip: the page that covers it, or a dark screen.
        const covered = STOP_IDS.some((stop) => Math.abs(stopPosition(stop) - (t - 0.0025)) < 0.006) || veilAt(t - 0.005) > 0.95 || veilAt(t) > 0.95;
        expect(covered, `time skips from ${previous} to ${hour} at ${t.toFixed(3)} with the scene in view`).toBe(true);
      }
      previous = hour;
    }
    expect(replayHourAt(TIMELINE_END)).toBe(132);
  });

  it("shows on the phone the scenario of the hour, on the page the story is about", () => {
    expect(phoneAt(stopPosition("public"))).toEqual({ tab: "home", practice: "normal" });
    expect(phoneAt(stopPosition("public-prepare"))).toEqual({ tab: "prepare", practice: "heads_up" });
    expect(phoneAt(segmentRange("night").start + 0.05)).toMatchObject({ tab: "report" });
    const peak = segmentRange("cut-off");
    expect(phoneAt((peak.start + peak.end) / 2)).toEqual({ tab: "home", practice: "cut_off" });
    expect(phoneAt(TIMELINE_END)).toEqual({ tab: "home", practice: "going_down" });
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
