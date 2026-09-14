import { OPENING_PLACE_PROGRESS, STORY_CHAPTERS } from "./sample-story";

type Listener = () => void;

export interface StoryStore {
  getSnapshot: () => number;
  subscribe: (listener: Listener) => () => void;
  setProgress: (progress: number) => void;
}

export const STORY_PROGRESS_BOUNDARIES = [
  ...STORY_CHAPTERS.map((chapter) => chapter.start),
  1,
];

export const STORY_OPENING_BOUNDARIES = [
  0,
  STORY_CHAPTERS[0].end * OPENING_PLACE_PROGRESS,
  ...STORY_PROGRESS_BOUNDARIES.slice(1),
];

/** A per-story clock shared by the scene and discrete chapter controls. */
export function createStoryStore(): StoryStore {
  let progress = 0;
  const listeners = new Set<Listener>();

  return {
    getSnapshot: () => progress,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    setProgress(value) {
      const next = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
      if (next === progress) return;
      progress = next;
      listeners.forEach((listener) => listener());
    },
  };
}

/** Map measured scroll intervals onto the authored chapter fractions. */
export function mapStoryProgress(
  position: number,
  anchors: readonly number[],
  boundaries: readonly number[] = STORY_PROGRESS_BOUNDARIES,
): number {
  if (anchors.length !== boundaries.length || anchors.length < 2
    || anchors.some((anchor, index) => !Number.isFinite(anchor) || (index > 0 && anchor < anchors[index - 1]))) return 0;
  const clamped = Number.isFinite(position) ? Math.min(1, Math.max(0, position)) : 0;
  if (clamped === 1) return 1;

  for (let index = 0; index < anchors.length - 1; index += 1) {
    if (clamped > anchors[index + 1]) continue;
    const span = anchors[index + 1] - anchors[index];
    const local = span > 0 ? Math.min(1, Math.max(0, (clamped - anchors[index]) / span)) : 0;
    const start = boundaries[index];
    return start + local * (boundaries[index + 1] - start);
  }

  return 1;
}

export function storyChapterIndex(progress: number): number {
  for (let index = STORY_CHAPTERS.length - 1; index > 0; index -= 1) {
    if (progress >= STORY_CHAPTERS[index].start) return index;
  }
  return 0;
}
