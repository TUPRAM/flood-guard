import { describe, expect, it, vi } from "vitest";

import { createStoryStore, mapStoryProgress, STORY_OPENING_BOUNDARIES, STORY_PROGRESS_BOUNDARIES, storyChapterIndex } from "./story-store";

describe("the narrative clock", () => {
  it("notifies only on a change and releases unmounted subscribers", () => {
    const store = createStoryStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    store.setProgress(0.4);
    store.setProgress(0.4);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot()).toBe(0.4);
    unsubscribe();
    store.setProgress(0.8);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("clamps its boundaries and never publishes a non-finite frame", () => {
    const store = createStoryStore();
    store.setProgress(5);
    expect(store.getSnapshot()).toBe(1);
    store.setProgress(-2);
    expect(store.getSnapshot()).toBe(0);
    store.setProgress(Number.NaN);
    expect(store.getSnapshot()).toBe(0);
  });

  it("aligns authored chapters with unequal measured sections", () => {
    const anchors = [0, 0.08, 0.2, 0.4, 0.5, 0.65, 0.8, 0.9, 1];
    anchors.forEach((position, index) => {
      expect(mapStoryProgress(position, anchors)).toBeCloseTo(STORY_PROGRESS_BOUNDARIES[index]);
    });
    expect(mapStoryProgress(0.3, anchors)).toBeCloseTo((0.29 + 0.42) / 2);
  });

  it("maps the hero and place section onto distinct stops within one opening chapter", () => {
    const anchors = [0, 0.1, 0.25, 0.35, 0.45, 0.55, 0.65, 0.8, 0.9, 1];
    anchors.forEach((position, index) => {
      expect(mapStoryProgress(position, anchors, STORY_OPENING_BOUNDARIES)).toBeCloseTo(STORY_OPENING_BOUNDARIES[index]);
    });
    expect(storyChapterIndex(mapStoryProgress(0.1, anchors, STORY_OPENING_BOUNDARIES))).toBe(0);
    expect(storyChapterIndex(mapStoryProgress(0.25, anchors, STORY_OPENING_BOUNDARIES))).toBe(1);
  });

  it("rejects malformed measured anchors without publishing a non-finite frame", () => {
    expect(mapStoryProgress(0.5, [0, 1])).toBe(0);
    expect(mapStoryProgress(0.5, [0, 0.1, NaN, 0.4, 0.5, 0.65, 0.8, 0.9, 1])).toBe(0);
    expect(mapStoryProgress(0.5, [0, 0.3, 0.2, 0.4, 0.5, 0.65, 0.8, 0.9, 1])).toBe(0);
  });

  it("seeks in either direction without retaining presentation history", () => {
    const anchors = [0, 0.1, 0.2, 0.4, 0.5, 0.7, 0.8, 0.95, 1];
    const forward = [0.1, 0.65, 0.95].map((position) => mapStoryProgress(position, anchors));
    const reverse = [0.95, 0.65, 0.1].map((position) => mapStoryProgress(position, anchors));
    expect(reverse).toEqual(forward.reverse());
    expect(storyChapterIndex(mapStoryProgress(0.65, anchors))).toBe(4);
    expect(storyChapterIndex(1)).toBe(7);
  });
});
