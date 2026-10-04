import { describe, expect, it } from "vitest";
import { DESKTOP_STORY_BOUNDARIES, DESKTOP_STORY_CHAPTERS, DESKTOP_STORY_OPENING_BOUNDARIES, sampleDesktopStory } from "./sample-desktop-story";
import { mapStoryProgress } from "./story-store";

describe("four-chapter evidence-to-access presentation", () => {
  it("owns exactly four semantic chapters, including the terminal finding", () => {
    expect(DESKTOP_STORY_CHAPTERS.map(({ id }) => id)).toEqual(["place", "flood", "access", "finding"]);
    expect(DESKTOP_STORY_BOUNDARIES).toEqual([0, 0.25, 0.5, 0.75, 1]);
    for (const [index, chapter] of DESKTOP_STORY_CHAPTERS.entries()) {
      expect(sampleDesktopStory(chapter.start)).toMatchObject({ chapterId: chapter.id, chapterIndex: index, chapterProgress: 0 });
    }
    expect(sampleDesktopStory(1)).toMatchObject({ chapterId: "finding", chapterIndex: 3, chapterProgress: 1 });
  });

  it("approaches one connected neighborhood and then holds its camera", () => {
    expect(sampleDesktopStory(0)).toMatchObject({ beat: "far", flight: 0, flood: 0, coverProgress: 0 });
    expect(sampleDesktopStory(0.04)).toMatchObject({ beat: "approach", flight: 0, coverProgress: 1 });
    expect(sampleDesktopStory(0.12).flight).toBeCloseTo(0.5);
    expect(sampleDesktopStory(0.2)).toMatchObject({ beat: "connection", flight: 1, flood: 0 });
    for (const progress of [0.25, 0.36, 0.5, 0.64, 0.75, 0.84, 1]) expect(sampleDesktopStory(progress).flight).toBe(1);
  });

  it("separates illustrated flood evidence from the later network assumption", () => {
    expect(sampleDesktopStory(0.28)).toMatchObject({ flood: 0, network: 0, assumptionApplied: false });
    expect(sampleDesktopStory(0.36).flood).toBeCloseTo(0.5);
    expect(sampleDesktopStory(0.44)).toMatchObject({ flood: 1, network: 0, assumptionApplied: false });
    expect(sampleDesktopStory(0.5)).toMatchObject({ flood: 1, network: 0, result: 0, assumptionApplied: false });
    expect(sampleDesktopStory(0.57).network).toBeCloseTo(0.5);
    expect(sampleDesktopStory(0.57).assumptionApplied).toBe(true);
    expect(sampleDesktopStory(0.64)).toMatchObject({ flood: 1, network: 1, result: 0 });
  });

  it("reveals a finding without clearing the water or restoring the connection", () => {
    expect(sampleDesktopStory(0.75)).toMatchObject({ flood: 1, network: 1, result: 0 });
    expect(sampleDesktopStory(0.795).result).toBeCloseTo(0.5);
    for (const progress of [0.84, 0.9, 1]) expect(sampleDesktopStory(progress)).toMatchObject({ flood: 1, network: 1, result: 1 });
  });

  it("maps the opening to the close connection anchor and four measured sections", () => {
    const anchors = [0, 0.2, 0.35, 0.55, 0.8, 1];
    for (const [index, position] of anchors.entries()) {
      expect(mapStoryProgress(position, anchors, DESKTOP_STORY_OPENING_BOUNDARIES)).toBeCloseTo(DESKTOP_STORY_OPENING_BOUNDARIES[index]);
    }
    expect(sampleDesktopStory(mapStoryProgress(anchors[1], anchors, DESKTOP_STORY_OPENING_BOUNDARIES)).flight).toBe(1);
  });

  it("is bounded, immutable, and identical for forward, reverse, and arbitrary jumps", () => {
    const positions = Array.from({ length: 1001 }, (_, index) => index / 1000);
    const frames = positions.map(sampleDesktopStory);
    expect([...positions].reverse().map(sampleDesktopStory).reverse()).toEqual(frames);
    for (const index of [999, 0, 501, 283, 840, 750, 200]) expect(sampleDesktopStory(positions[index])).toEqual(frames[index]);
    for (const frame of frames) {
      expect(Object.isFrozen(frame)).toBe(true);
      expect(frame).toMatchObject({ origin: "synthetic_illustration", operationalWriteAllowed: false, currentConditionClaim: false, interludeOpacity: 0 });
      for (const amount of [frame.chapterProgress, frame.flight, frame.flood, frame.network, frame.result, frame.coverProgress]) {
        expect(amount).toBeGreaterThanOrEqual(0);
        expect(amount).toBeLessThanOrEqual(1);
      }
    }
  });

  it("normalizes invalid and out-of-range input", () => {
    for (const value of [undefined, null, NaN, -Infinity, -1, "0.5", {}, true]) expect(sampleDesktopStory(value).progress).toBe(0);
    for (const value of [1, 2, Infinity]) expect(sampleDesktopStory(value).progress).toBe(1);
  });
});
