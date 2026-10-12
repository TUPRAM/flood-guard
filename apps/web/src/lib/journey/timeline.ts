/**
 * The cinematic journey's story timeline: an ordered list of camera segments (scrubbed by scroll, touch or keys) and
 * stops where a real FloodGuard page takes over the viewport. Pure: no DOM, no Three.js, so the navigation rules are
 * unit-tested. Positions are in "story units"; a segment's length sets how much scrolling it takes.
 */

export type SegmentId =
  | "opening"
  | "everyday"
  | "enter-phone"
  | "conditions"
  | "return-phone"
  | "sos-signal"
  | "enter-monitor"
  | "aerial";

export type StopId = "public" | "public-sos" | "case" | "command";

export type ChapterId = "opening" | "everyday" | "conditions" | "affected" | "response";

export type TimelineItem =
  | { kind: "segment"; id: SegmentId; length: number; chapter: ChapterId }
  | { kind: "stop"; id: StopId; chapter: ChapterId };

export const TIMELINE: readonly TimelineItem[] = [
  { kind: "segment", id: "opening", length: 1, chapter: "opening" },
  { kind: "segment", id: "everyday", length: 1.4, chapter: "everyday" },
  { kind: "segment", id: "enter-phone", length: 1, chapter: "everyday" },
  { kind: "stop", id: "public", chapter: "everyday" },
  { kind: "segment", id: "conditions", length: 1.6, chapter: "conditions" },
  { kind: "segment", id: "return-phone", length: 1, chapter: "conditions" },
  { kind: "stop", id: "public-sos", chapter: "conditions" },
  { kind: "segment", id: "sos-signal", length: 2, chapter: "affected" },
  { kind: "segment", id: "enter-monitor", length: 1, chapter: "affected" },
  { kind: "stop", id: "case", chapter: "affected" },
  { kind: "segment", id: "aerial", length: 2.2, chapter: "response" },
  { kind: "stop", id: "command", chapter: "response" },
];

export const CHAPTERS: readonly ChapterId[] = ["opening", "everyday", "conditions", "affected", "response"];

interface Placed { item: TimelineItem; start: number; end: number }

const PLACED: readonly Placed[] = (() => {
  let at = 0;
  return TIMELINE.map((item) => {
    const start = at;
    if (item.kind === "segment") at += item.length;
    return { item, start, end: at };
  });
})();

/** Start and end of a camera segment on the timeline. */
export function segmentRange(id: SegmentId): { start: number; end: number } {
  const placed = PLACED.find((entry) => entry.item.kind === "segment" && entry.item.id === id)!;
  return { start: placed.start, end: placed.end };
}

/** Total story length in units (the position of the final stop). */
export const TIMELINE_END = PLACED[PLACED.length - 1].end;

/** Position of a stop on the timeline. */
export function stopPosition(id: StopId): number {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && entry.item.id === id);
  if (!placed) throw new Error(`Unknown stop: ${id}`);
  return placed.start;
}

/** Position where a chapter begins (its first item). */
export function chapterStart(chapter: ChapterId): number {
  const placed = PLACED.find((entry) => entry.item.chapter === chapter);
  if (!placed) throw new Error(`Unknown chapter: ${chapter}`);
  return placed.start;
}

export interface Location {
  segment: SegmentId;
  /** Progress within the segment, 0..1. */
  progress: number;
  chapter: ChapterId;
}

/** The segment and progress at timeline position `t` (clamped to the story). A stop resolves to the segment before it, at progress 1. */
export function locate(t: number): Location {
  const position = Math.min(TIMELINE_END, Math.max(0, t));
  const segments = PLACED.filter((entry): entry is Placed & { item: Extract<TimelineItem, { kind: "segment" }> } => entry.item.kind === "segment");
  for (const entry of segments) {
    if (position <= entry.end || entry === segments[segments.length - 1]) {
      const progress = entry.item.length > 0 ? (position - entry.start) / entry.item.length : 1;
      const clamped = Math.min(1, Math.max(0, progress));
      return { segment: entry.item.id, progress: clamped > 1 - 1e-9 ? 1 : clamped, chapter: entry.item.chapter };
    }
  }
  throw new Error("unreachable");
}

/** The chapter a timeline position belongs to; a stop belongs to the chapter of the segments that lead into it. */
export function chapterAt(t: number): ChapterId {
  const stop = stopAt(t);
  if (stop) return TIMELINE.find((item) => item.kind === "stop" && item.id === stop)!.chapter;
  return locate(t).chapter;
}

/** The stop exactly at `t` (within a small tolerance), if any. */
export function stopAt(t: number, tolerance = 1e-4): StopId | null {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && Math.abs(entry.start - t) <= tolerance);
  return placed && placed.item.kind === "stop" ? placed.item.id : null;
}

/** The first stop strictly after `t`, or null after the last stop. */
export function nextStopAfter(t: number, tolerance = 1e-4): StopId | null {
  const placed = PLACED.find((entry) => entry.item.kind === "stop" && entry.start > t + tolerance);
  return placed && placed.item.kind === "stop" ? placed.item.id : null;
}

/** The last stop strictly before `t`, or null before the first stop. */
export function previousStopBefore(t: number, tolerance = 1e-4): StopId | null {
  const stops = PLACED.filter((entry) => entry.item.kind === "stop" && entry.start < t - tolerance);
  const last = stops[stops.length - 1];
  return last && last.item.kind === "stop" ? last.item.id : null;
}

/**
 * Where a scroll-driven target may move to from `current`: scrolling forward cannot pass the next stop (the visitor
 * enters the real page there and continues with an explicit control); scrolling backward is free.
 */
export function clampScrollTarget(current: number, requested: number): number {
  const bounded = Math.min(TIMELINE_END, Math.max(0, requested));
  if (bounded <= current) return bounded;
  const next = nextStopAfter(current);
  if (next === null) return bounded;
  return Math.min(bounded, stopPosition(next));
}

/**
 * One animation step of the displayed position toward the target: an eased approach, capped at `maxSpeed` units per
 * second so fast scrolling or a chapter "continue" never whips the camera. Snaps when within `epsilon`.
 */
export function stepToward(display: number, target: number, dt: number, maxSpeed = 0.32, smoothing = 4, epsilon = 1e-4): number {
  const gap = target - display;
  if (Math.abs(gap) <= epsilon) return target;
  const eased = gap * (1 - Math.exp(-smoothing * Math.max(0, dt)));
  const cap = maxSpeed * Math.max(0, dt);
  const step = Math.sign(eased) * Math.min(Math.abs(eased), cap);
  // Never stall: guarantee a minimum crawl so the approach finishes.
  const minimum = Math.min(Math.abs(gap), 0.02 * Math.max(0, dt));
  return display + Math.sign(gap) * Math.max(Math.abs(step), minimum);
}

/**
 * Discrete story beats for reduced motion: each segment's start and middle, every chapter entry and every stop, in
 * order. Stepping beat to beat reaches every stop, including the last one.
 */
export function storyBeats(): number[] {
  const beats = new Set<number>();
  for (const entry of PLACED) {
    if (entry.item.kind === "segment") {
      beats.add(entry.start);
      beats.add(entry.start + entry.item.length / 2);
    } else beats.add(entry.start);
  }
  for (const chapter of CHAPTERS) beats.add(chapterEntry(chapter));
  return [...beats].map((beat) => Math.round(beat * 1e6) / 1e6).sort((a, b) => a - b);
}

/** Scene ids used in the address bar: every chapter start and every stop. */
export type SceneId = ChapterId | StopId;

const SCENE_IDS: readonly SceneId[] = [...CHAPTERS, "public", "public-sos", "case", "command"];

export function parseScene(search: string): SceneId | null {
  const value = new URLSearchParams(search).get("scene");
  return value && (SCENE_IDS as readonly string[]).includes(value) ? (value as SceneId) : null;
}

/**
 * Where navigating to a chapter lands: its start, nudged just past a stop that sits on the boundary (stops have no
 * length, so "the start of Conditions change" would otherwise be "the public-app stop" and dock that page instead).
 */
export function chapterEntry(chapter: ChapterId): number {
  const start = chapterStart(chapter);
  return stopAt(start) ? start + 0.002 : start;
}

export function scenePosition(scene: SceneId): number {
  return (CHAPTERS as readonly string[]).includes(scene) ? chapterEntry(scene as ChapterId) : stopPosition(scene as StopId);
}

/** Scene id to record for a position: the stop if exactly at one, otherwise the chapter. */
export function sceneAt(t: number): SceneId {
  return stopAt(t) ?? chapterAt(t);
}
