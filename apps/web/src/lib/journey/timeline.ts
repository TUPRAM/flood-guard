/**
 * The cinematic journey's story timeline: an ordered list of camera segments (scrubbed by scroll, touch or keys) and
 * stops where a real FloodGuard page takes over the viewport. Pure: no DOM, no Three.js, so the navigation rules are
 * unit-tested. Positions are in "story units"; a segment's length sets how much scrolling it takes.
 *
 * The story plays on the real map of Mae Sai with the water of the published replay (r5), so every position also has
 * a replay hour (whole hours since 9 Sep 2024 00:00 ICT, the unit of the case view's and the command exercise's `t`).
 * The hours are those of the Public app's practice scenarios: the phone in the story shows the same scenario as the
 * scene around it.
 */

import { PRACTICE_SCENARIOS, type PracticeState } from "@/lib/public-practice-scenarios";

export type SegmentId =
  | "opening"
  | "everyday"
  | "enter-phone"
  | "conditions"
  | "return-phone"
  | "night"
  | "cut-off"
  | "enter-monitor"
  | "aerial";

export type StopId = "public" | "public-prepare" | "case" | "command";

/** `affected` (the cut-off chapter) and `response` keep their old ids so existing `?scene=` links still open. */
export type ChapterId = "opening" | "everyday" | "conditions" | "night" | "affected" | "response";

export type TimelineItem =
  | { kind: "segment"; id: SegmentId; length: number; chapter: ChapterId }
  | { kind: "stop"; id: StopId; chapter: ChapterId };

export const TIMELINE: readonly TimelineItem[] = [
  { kind: "segment", id: "opening", length: 1, chapter: "opening" },
  // Long: the walk from above, then a slow move down Lalita's street to the family at the gate.
  { kind: "segment", id: "everyday", length: 2.6, chapter: "everyday" },
  { kind: "segment", id: "enter-phone", length: 1.3, chapter: "everyday" },
  { kind: "stop", id: "public", chapter: "everyday" },
  { kind: "segment", id: "conditions", length: 2, chapter: "conditions" },
  { kind: "segment", id: "return-phone", length: 1.8, chapter: "conditions" },
  { kind: "stop", id: "public-prepare", chapter: "conditions" },
  { kind: "segment", id: "night", length: 2.8, chapter: "night" },
  { kind: "segment", id: "cut-off", length: 3.6, chapter: "affected" },
  { kind: "segment", id: "enter-monitor", length: 1, chapter: "affected" },
  { kind: "stop", id: "case", chapter: "affected" },
  { kind: "segment", id: "aerial", length: 3, chapter: "response" },
  // The story ends on the planning table: Next there replays it from the start.
  { kind: "stop", id: "command", chapter: "response" },
];

export const CHAPTERS: readonly ChapterId[] = ["opening", "everyday", "conditions", "night", "affected", "response"];

/** Every stop, in story order. */
export const STOP_IDS: readonly StopId[] = TIMELINE.flatMap((item) => (item.kind === "stop" ? [item.id] : []));

/** Every segment, in story order. */
export const SEGMENT_IDS: readonly SegmentId[] = TIMELINE.flatMap((item) => (item.kind === "segment" ? [item.id] : []));

interface Placed { item: TimelineItem; start: number; end: number }

const PLACED: readonly Placed[] = (() => {
  let at = 0;
  return TIMELINE.map((item) => {
    const start = at;
    // Rounded, so positions are the decimals they look like (1 + 2.6 + … is otherwise 7.199999999999999).
    if (item.kind === "segment") at = Math.round((at + item.length) * 1e9) / 1e9;
    return { item, start, end: at };
  });
})();

/** Start and end of a camera segment on the timeline. */
export function segmentRange(id: SegmentId): { start: number; end: number } {
  const placed = PLACED.find((entry) => entry.item.kind === "segment" && entry.item.id === id)!;
  return { start: placed.start, end: placed.end };
}

/** Total story length in units: the position of the final stop, where the story ends. */
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
 * Discrete story beats for reduced motion: each segment's start and middle, every chapter entry, every stop and the
 * end of the story, in order. Stepping beat to beat reaches every stop and the closing scene.
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
  beats.add(TIMELINE_END);
  return [...beats].map((beat) => Math.round(beat * 1e6) / 1e6).sort((a, b) => a - b);
}

/** Scene ids used in the address bar: every chapter start and every stop. */
export type SceneId = ChapterId | StopId;

const SCENE_IDS: readonly SceneId[] = [...CHAPTERS, ...STOP_IDS];

export function parseScene(search: string): SceneId | null {
  const value = new URLSearchParams(search).get("scene");
  return value && (SCENE_IDS as readonly string[]).includes(value) ? (value as SceneId) : null;
}

/**
 * Where navigating to a chapter lands: its start, nudged just past a stop that sits on the boundary (stops have no
 * length, so "the start of Conditions change" would otherwise be "the public-app stop" and dock that page instead),
 * and on into the chapter's own picture: a boundary between segments resolves to the segment before it, and a chapter
 * that opens with a cut in time opens once the dip to dark has cleared.
 */
export function chapterEntry(chapter: ChapterId): number {
  let t = chapterStart(chapter);
  for (let i = 0; i < 1000 && (stopAt(t) || chapterAt(t) !== chapter || veilAt(t) > 0); i += 1) t += 0.002;
  return t;
}

export function scenePosition(scene: SceneId): number {
  return (CHAPTERS as readonly string[]).includes(scene) ? chapterEntry(scene as ChapterId) : stopPosition(scene as StopId);
}

/** Scene id to record for a position: the stop if exactly at one, otherwise the chapter. */
export function sceneAt(t: number): SceneId {
  return stopAt(t) ?? chapterAt(t);
}

// --- Replay time -----------------------------------------------------------------------------------------------------

/** A replay hour at a segment progress; hours are linear between keys. */
interface HourKey {
  at: number;
  hour: number;
}

/**
 * Replay hours along each segment. Between some segments the story skips ahead in time (12 → 38, 49 → 84):
 * those cuts happen while a real page is docked, or behind a short dip to dark (`veilAt`).
 */
const SEGMENT_HOURS: Record<SegmentId, readonly HourKey[]> = {
  opening: [{ at: 0, hour: 12 }],
  everyday: [{ at: 0, hour: 12 }],
  "enter-phone": [{ at: 0, hour: 12 }],
  conditions: [{ at: 0, hour: 38 }, { at: 1, hour: 40 }],
  "return-phone": [{ at: 0, hour: 40 }],
  // Dusk to the small hours of 11 September: roads under water (46), the walk nearly cut (48), then cut (49).
  // Dusk falls over about a second (p 0.12-0.30) before the 22:00 caption appears.
  // The clock reaches 22:00 as that caption appears (p 0.38) and holds it to the pause.
  night: [{ at: 0, hour: 40 }, { at: 0.12, hour: 41.6 }, { at: 0.3, hour: 43.5 }, { at: 0.38, hour: 46 }, { at: 0.42, hour: 46 }, { at: 0.66, hour: 48 }, { at: 0.88, hour: 49 }],
  "cut-off": [{ at: 0, hour: 84 }],
  "enter-monitor": [{ at: 0, hour: 84 }],
  aerial: [{ at: 0, hour: 84 }],
};

/** The replay hour a real page opens at: the hour of the scene around it. */
export const STOP_HOURS: Record<StopId, number> = { public: 12, "public-prepare": 40, case: 84, command: 84 };

function hourAlong(keys: readonly HourKey[], progress: number): number {
  if (progress <= keys[0].at) return keys[0].hour;
  for (let index = 1; index < keys.length; index += 1) {
    const a = keys[index - 1], b = keys[index];
    if (progress <= b.at) return a.hour + ((progress - a.at) / (b.at - a.at)) * (b.hour - a.hour);
  }
  return keys[keys.length - 1].hour;
}

/** Replay hour (fractional, since 9 Sep 2024 00:00 ICT) at a timeline position; a stop takes its own hour. */
export function replayHourAt(t: number): number {
  const stop = stopAt(t);
  if (stop) return STOP_HOURS[stop];
  const { segment, progress } = locate(t);
  return hourAlong(SEGMENT_HOURS[segment], progress);
}

/**
 * How the sky blends just after a page whose hour is earlier than the segment's (Monday 12:00 on the Public app, then
 * Tuesday afternoon): the light and weather of hour `from` turn into those of hour `to` with `weight` over the first
 * tenth of the segment, instead of switching in one frame as the page undocks. The light itself is blended, not the
 * hour (blending the hour would pass through the night between). Elsewhere `from` and `to` are the clock's hour.
 */
export function skyHoursAt(t: number): { from: number; to: number; weight: number } {
  const hour = replayHourAt(t);
  const none = { from: hour, to: hour, weight: 1 };
  if (stopAt(t)) return none;
  const { segment, progress } = locate(t);
  const index = PLACED.findIndex((entry) => entry.item.kind === "segment" && entry.item.id === segment);
  const before = index > 0 ? PLACED[index - 1].item : null;
  if (!before || before.kind !== "stop" || progress >= 0.1) return none;
  const from = STOP_HOURS[before.id];
  if (Math.abs(from - SEGMENT_HOURS[segment][0].hour) < 1e-9) return none;
  const w = progress / 0.1;
  return { from, to: hour, weight: w * w * (3 - 2 * w) };
}

/** Every distinct replay hour a segment key names, in story order (for tests and the text version). */
export function storyHours(): number[] {
  return [...new Set(SEGMENT_IDS.flatMap((id) => SEGMENT_HOURS[id].map((key) => key.hour)))];
}

/**
 * How dark the screen is for a cut in time (0 = clear, 1 = black): the end of the night fades out and the cut-off
 * chapter, two and a half days later, fades in. Other cuts happen while a page covers the scene.
 */
export function veilAt(t: number): number {
  const { segment, progress } = locate(t);
  const smooth = (x: number) => x * x * (3 - 2 * x);
  if (segment === "night" && progress > 0.94) return smooth(Math.min(1, (progress - 0.94) / 0.06));
  if (segment === "cut-off" && progress < 0.06) return smooth(1 - progress / 0.06);
  return 0;
}

// --- The phone ------------------------------------------------------------------------------------------------------

/** The Public app's pages the story switches its phone to (the app's own bottom navigation). */
export type PublicTab = "home" | "report" | "shelter" | "prepare" | "sos";

/**
 * The practice scenario of the dry example home for a replay hour: the latest scenario at or before the hour. The
 * story never shows the flooded home's scenario on Lalita's phone (her home stays dry).
 */
export function practiceForHour(hour: number): PracticeState {
  let state: PracticeState = PRACTICE_SCENARIOS[0].id;
  for (const scenario of PRACTICE_SCENARIOS) if (scenario.home === "dry" && scenario.hour <= hour + 1e-6) state = scenario.id;
  return state;
}

/** What Lalita's phone shows at a timeline position: a page of the Public app and a practice scenario. */
export function phoneAt(t: number): { tab: PublicTab; practice: PracticeState } {
  const hour = replayHourAt(t);
  const practice = practiceForHour(hour);
  const stop = stopAt(t);
  if (stop === "public-prepare") return { tab: "prepare", practice };
  if (stop) return { tab: "home", practice };
  const { segment, progress } = locate(t);
  // Prepare from the family's rest (p 0.45), while the phone is off screen: the app re-renders unseen.
  if (segment === "return-phone") return { tab: progress < 0.44 ? "home" : "prepare", practice };
  if (segment === "night" && progress < 0.3) return { tab: "report", practice };
  return { tab: "home", practice };
}
