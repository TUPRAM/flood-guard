import { describe, expect, it } from "vitest";
import { scenes } from "./story";
import { artworkWeights, opening, sampleTimeline, timelineLength, timelinePosition, timelineStops } from "./timeline";

describe("continuous story timeline", () => {
  it("finishes the drone approach before moving the artwork window, then introduces paper before content", () => {
    expect(opening.camera[1]).toBeLessThanOrEqual(opening.window[0]);
    expect(opening.window[1]).toBeLessThanOrEqual(opening.background[0]);
    expect(opening.background[1]).toBeLessThan(opening.portrait[0]);
    const background = sampleTimeline((opening.background[0] + opening.portrait[0]) / 2);
    expect(background.camera).toBe(1);
    expect(background.window).toBe(1);
    expect(background.background).toBeGreaterThan(0);
    expect(background.residentOpacity).toBe(0);
    expect(background.textOpacity).toBe(0);
  });

  it("has a settled, directly addressable reading position for all nine scenes", () => {
    expect(timelineStops).toHaveLength(9);
    for (const scene of scenes) {
      const frame = sampleTimeline(timelinePosition(scene.id));
      expect(frame.scene.id).toBe(scene.id);
      expect(frame.readingHold).toBe(true);
      if (scene.id !== "H-01") expect(frame.textOpacity).toBe(1);
    }
  });

  it("keeps the same resident fully present when only the story text changes", () => {
    for (const stop of timelineStops.filter((item) => ["S2-01", "S3A-01", "S3B-OBS"].includes(item.scene.id))) {
      const frame = sampleTimeline((stop.enter + stop.hold) / 2);
      expect(frame.residentOpacity).toBe(1);
      expect(frame.plannerOpacity).toBe(0);
      expect(frame.textOpacity).toBe(0);
      expect(frame.background).toBe(1);
      expect(frame.window).toBe(1);
    }
  });

  it("changes the portrait only at the resident/planner boundary and preserves the later W2 footprint", () => {
    const stop = timelineStops.find((item) => item.scene.id === "S3B-01")!;
    const change = sampleTimeline((stop.enter + stop.hold) / 2);
    expect(change.residentOpacity).toBeCloseTo(0.5);
    expect(change.plannerOpacity).toBeCloseTo(0.5);
    for (const item of timelineStops.filter((candidate) => candidate.scene.waterState === "W2")) {
      expect(sampleTimeline(item.hold).water).toBe(2);
    }
  });

  it("preserves unchanged headings while a card or the person changes", () => {
    for (const id of ["S3B-01", "S4-PUBLIC"]) {
      const stop = timelineStops.find((item) => item.scene.id === id)!;
      const frame = sampleTimeline((stop.enter + stop.hold) / 2);
      expect(frame.narrativeOpacity).toBe(1);
      expect(frame.textOpacity).toBe(0);
    }
  });

  it("holds camera, window, water and content still while a scene is read", () => {
    for (const stop of timelineStops.slice(1)) {
      const first = sampleTimeline(stop.hold + 0.1);
      const last = sampleTimeline(stop.leave - 0.1);
      expect([last.scene.id, last.camera, last.window, last.water, last.textOpacity]).toEqual(
        [first.scene.id, first.camera, first.window, first.water, first.textOpacity],
      );
    }
  });

  it("reverses exactly without stale callbacks or a direction-dependent state", () => {
    const positions = [0.2, 1.2, 2.7, 3.5, 4.3, 6.4, 9.8, timelineLength - 0.1];
    const forward = positions.map(sampleTimeline);
    const backward = [...positions].reverse().map(sampleTimeline).reverse();
    expect(backward).toEqual(forward);
  });

  it("clamps out-of-range or invalid scroll inputs to a meaningful endpoint", () => {
    expect(sampleTimeline(-100).scene.id).toBe("H-01");
    expect(sampleTimeline(Number.NaN).scene.id).toBe("H-01");
    expect(sampleTimeline(timelineLength + 100).scene.id).toBe("S4-END");
    expect(sampleTimeline(timelineLength + 100).progress).toBe(1);
  });
});

describe("transparent artwork compositing", () => {
  it("keeps one unit of alpha across camera and water cross-fades", () => {
    for (const water of [0, 0.15, 0.5, 1, 1.35, 1.8, 2]) {
      for (const camera of [0, 0.25, 0.5, 1]) {
        const weights = Object.values(artworkWeights(water, camera, true));
        expect(weights.reduce((sum, weight) => sum + weight, 0)).toBeCloseTo(1);
        expect(weights.every((weight) => weight >= 0 && weight <= 1)).toBe(true);
        expect(weights.reduce((alpha, weight) => alpha + 0.37 * weight, 0)).toBeCloseTo(0.37);
      }
    }
  });

  it("shows one physical plate at every water-state rest", () => {
    expect(artworkWeights(0, 0, true)).toEqual({ poster: 0, camera: 1, next: 0, w1: 0, w2: 0 });
    expect(artworkWeights(1, 0, true)).toEqual({ poster: 0, camera: 0, next: 0, w1: 1, w2: 0 });
    expect(artworkWeights(2, 0, true)).toEqual({ poster: 0, camera: 0, next: 0, w1: 0, w2: 1 });
  });

  it("shows only the retained poster until the requested layer set is decoded", () => {
    expect(artworkWeights(1.5, 0.5, false)).toEqual({ poster: 1, camera: 0, next: 0, w1: 0, w2: 0 });
  });
});
