export const DESKTOP_STORY_CHAPTERS = [
  { id: "place", label: "Connection", start: 0, end: 0.25 },
  { id: "flood", label: "Flood evidence", start: 0.25, end: 0.5 },
  { id: "access", label: "Access", start: 0.5, end: 0.75 },
  { id: "finding", label: "Finding", start: 0.75, end: 1 },
] as const;

export const DESKTOP_STORY_BOUNDARIES = [0, 0.25, 0.5, 0.75, 1] as const;
export const DESKTOP_STORY_OPENING_BOUNDARIES = [0, 0.2, 0.25, 0.5, 0.75, 1] as const;

export type DesktopChapterId = typeof DESKTOP_STORY_CHAPTERS[number]["id"];
export type DesktopStoryBeat = "far" | "approach" | "connection" | "flood" | "access" | "finding";

export interface DesktopStoryFrame {
  readonly progress: number;
  readonly chapterId: DesktopChapterId;
  readonly chapterIndex: number;
  readonly chapterProgress: number;
  readonly beat: DesktopStoryBeat;
  readonly flight: number;
  readonly flood: number;
  readonly network: number;
  readonly result: number;
  readonly coverProgress: number;
  readonly interludeOpacity: 0;
  readonly assumptionApplied: boolean;
  readonly origin: "synthetic_illustration";
  readonly operationalWriteAllowed: false;
  readonly currentConditionClaim: false;
}

function smooth(start: number, end: number, progress: number): number {
  const t = Math.min(1, Math.max(0, (progress - start) / (end - start)));
  return t * t * (3 - 2 * t);
}

/** One reversible presentation state; illustrated flooding never asserts an observed closure. */
export function sampleDesktopStory(value: unknown): DesktopStoryFrame {
  const progress = typeof value === "number" && !Number.isNaN(value) ? Math.min(1, Math.max(0, value)) : 0;
  const chapterIndex = Math.min(DESKTOP_STORY_CHAPTERS.length - 1, Math.floor(progress * DESKTOP_STORY_CHAPTERS.length));
  const chapter = DESKTOP_STORY_CHAPTERS[chapterIndex];
  const network = smooth(0.5, 0.64, progress);
  return Object.freeze({
    progress,
    chapterId: chapter.id,
    chapterIndex,
    chapterProgress: (progress - chapter.start) / (chapter.end - chapter.start),
    beat: progress < 0.04 ? "far" : progress < 0.2 ? "approach" : chapter.id === "place" ? "connection" : chapter.id,
    flight: smooth(0.04, 0.2, progress),
    flood: smooth(0.28, 0.44, progress),
    network,
    result: smooth(0.75, 0.84, progress),
    coverProgress: smooth(0, 0.04, progress),
    interludeOpacity: 0,
    assumptionApplied: network > 0,
    origin: "synthetic_illustration",
    operationalWriteAllowed: false,
    currentConditionClaim: false,
  });
}
