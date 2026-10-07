/**
 * Replay controls of the Command exercise replay (Mae Sai, September 2024) as pure functions: the replay hour and
 * how it moves (play, steps, speeds), the stops of the "previous event" and "next event" buttons, the keys of the
 * page, and the hour kept in the address bar.
 *
 * The hour in the address is the same `t` parameter as on the Studio replay (`flood-timeline-link`), so one address
 * names one replay moment on both pages. The replay is a reconstructed 2024 event; nothing here reads a clock of today.
 * No DOM access in this module.
 */

import { tFromLocalDate, type Language, type TimelineManifest } from "./flood-timeline";
import { clampCommandHour, COMMAND_LAST_HOUR } from "./flood-timeline-command";
import { LINK_PARAMS } from "./flood-timeline-link";
import { MAE_SAI_REPLAY_ROUTE } from "./policy-links";

// --- Speeds ----------------------------------------------------------------------------------------------

/** The three playback speeds: one replay hour per second, four per second, and the drill speed of one per minute. */
export type CommandSpeedId = "hour_per_second" | "four_per_second" | "drill";
export interface CommandSpeed {
  id: CommandSpeedId;
  /** How long one replay hour stays on screen (ms). */
  hourMs: number;
}
export const COMMAND_SPEEDS: readonly CommandSpeed[] = [
  { id: "hour_per_second", hourMs: 1000 },
  { id: "four_per_second", hourMs: 250 },
  // Drill: a team has a minute to act on each replay hour.
  { id: "drill", hourMs: 60_000 },
];
export const DEFAULT_COMMAND_SPEED: CommandSpeedId = "hour_per_second";
export const commandSpeed = (id: CommandSpeedId): CommandSpeed => COMMAND_SPEEDS.find((speed) => speed.id === id) ?? COMMAND_SPEEDS[0];

/** Where the replay opens without an hour in the address: 10 Sep 12:00, the midday before the river rises. */
export const COMMAND_START_HOUR = 36;

// --- Stops of the event buttons --------------------------------------------------------------------------

/** A replay hour the "previous event" and "next event" buttons stop at. */
export interface CommandEventStop {
  hour: number;
  /** The start or the end of the replay, the first hour of a phase, the hour of the highest assumed stage, or an hour with a mark on the time track. */
  kind: "start" | "phase" | "peak" | "end" | "mark";
  /** The phase that starts at this hour, for a phase stop. */
  phaseId?: string;
}

/**
 * The stops in time order: the start of the replay, the first hour of every later phase, the first hour at which the
 * assumed river stage is at its highest (a model event), and the end of the replay. Two stops never share an hour;
 * a phase start wins over the peak hour.
 */
export function commandEventStops(manifest: Pick<TimelineManifest, "phases" | "stage_anchors">, stages: ArrayLike<number>): CommandEventStop[] {
  const stops = new Map<number, CommandEventStop>();
  stops.set(0, { hour: 0, kind: "start" });
  for (const phase of manifest.phases) {
    const hour = clampCommandHour(tFromLocalDate(phase.start) * 24);
    if (hour > 0 && hour < COMMAND_LAST_HOUR && !stops.has(hour)) stops.set(hour, { hour, kind: "phase", phaseId: phase.id });
  }
  let peak = 0;
  for (let hour = 1; hour < stages.length; hour += 1) if (stages[hour] > stages[peak]) peak = hour;
  if (stages.length > 0 && stages[peak] > 0 && !stops.has(peak)) stops.set(peak, { hour: peak, kind: "peak" });
  stops.set(COMMAND_LAST_HOUR, { hour: COMMAND_LAST_HOUR, kind: "end" });
  return [...stops.values()].sort((a, b) => a.hour - b.hour);
}

/**
 * The stops of the event buttons once the marks of the time track are known: the start, every hour that has a mark
 * (a reported or observed item, or an event of the model) and the end.
 */
export function commandMarkStops(hours: readonly number[]): CommandEventStop[] {
  const unique = [...new Set([0, ...hours.map(clampCommandHour), COMMAND_LAST_HOUR])].sort((a, b) => a - b);
  return unique.map((hour) => ({ hour, kind: hour === 0 ? "start" : hour === COMMAND_LAST_HOUR ? "end" : "mark" }));
}

/** The first stop after `hour`, or null at the last one. */
export function nextEventStop(stops: readonly CommandEventStop[], hour: number): CommandEventStop | null {
  return stops.find((stop) => stop.hour > hour) ?? null;
}

/** The last stop before `hour`, or null at the first one. */
export function previousEventStop(stops: readonly CommandEventStop[], hour: number): CommandEventStop | null {
  for (let index = stops.length - 1; index >= 0; index -= 1) if (stops[index].hour < hour) return stops[index];
  return null;
}

// --- Days and phases on the time bar ---------------------------------------------------------------------

/** One chip of the day row: the day of the month, its first replay hour and its local date. */
export interface CommandDayChip { day: number; hour: number; date: string }

/** The eleven day chips (9 … 19 September), each at the first hour of its local day. */
export function commandDayChips(days: readonly { date: string }[]): CommandDayChip[] {
  return days.map(({ date }) => ({ day: Number(date.slice(8, 10)), hour: clampCommandHour(tFromLocalDate(date) * 24), date }));
}

/** Index of the day a replay hour falls in; the end of the replay (20 Sep 00:00) belongs to the last day. */
export function commandDayIndex(hour: number, dayCount: number): number {
  return Math.max(0, Math.min(dayCount - 1, Math.floor(clampCommandHour(hour) / 24)));
}

/** A phase as the band of the time bar draws it: from its first replay hour to the first hour of the next one. */
export interface CommandPhaseSpan { id: string; from: number; to: number }

export function commandPhaseSpans(phases: readonly { id: string; start: string; end: string }[]): CommandPhaseSpan[] {
  return phases.map((phase) => ({
    id: phase.id,
    from: clampCommandHour(tFromLocalDate(phase.start) * 24),
    to: clampCommandHour((tFromLocalDate(phase.end) + 1) * 24),
  }));
}

/** Position of a replay hour along the track, 0 … 1. */
export const commandHourShare = (hour: number): number => clampCommandHour(hour) / COMMAND_LAST_HOUR;

// --- The replay state ------------------------------------------------------------------------------------

export interface CommandReplayState {
  /** Whole replay hour, 0 … 264. */
  hour: number;
  playing: boolean;
  speed: CommandSpeedId;
  /** Focus mode: the left column and the time dock collapse to one line each. */
  focus: boolean;
}

export type CommandReplayAction =
  | { type: "seek"; hour: number }
  | { type: "step"; hours: number }
  /** One beat of playback: the next replay hour. Playback pauses when that hour is one of `pauseAt` (a life-at-risk item of the exercise arrives). */
  | { type: "tick"; pauseAt?: ReadonlySet<number> }
  | { type: "toggle_play" }
  | { type: "pause" }
  | { type: "speed"; speed: CommandSpeedId }
  | { type: "event"; direction: -1 | 1; stops: readonly CommandEventStop[] }
  | { type: "focus"; on?: boolean };

export function initialCommandReplay(hour: number = COMMAND_START_HOUR): CommandReplayState {
  return { hour: clampCommandHour(hour), playing: false, speed: DEFAULT_COMMAND_SPEED, focus: false };
}

/**
 * The replay state after an action. The hour never leaves 0 … 264. Playback stops by itself at the end of the
 * replay; "play" at the end starts again from the first hour. A step or a jump while playing keeps playing, unless it
 * reaches the end.
 */
export function commandReplayReducer(state: CommandReplayState, action: CommandReplayAction): CommandReplayState {
  const at = (hour: number): CommandReplayState => {
    const next = clampCommandHour(hour);
    const playing = state.playing && next < COMMAND_LAST_HOUR;
    return next === state.hour && playing === state.playing ? state : { ...state, hour: next, playing };
  };
  switch (action.type) {
    case "seek": return at(action.hour);
    case "step": return at(state.hour + action.hours);
    case "tick": {
      if (!state.playing) return state;
      const next = at(state.hour + 1);
      return action.pauseAt?.has(next.hour) && next.playing ? { ...next, playing: false } : next;
    }
    case "toggle_play":
      if (state.playing) return { ...state, playing: false };
      return state.hour >= COMMAND_LAST_HOUR ? { ...state, hour: 0, playing: true } : { ...state, playing: true };
    case "pause": return state.playing ? { ...state, playing: false } : state;
    case "speed": return action.speed === state.speed ? state : { ...state, speed: action.speed };
    case "event": {
      const stop = action.direction > 0 ? nextEventStop(action.stops, state.hour) : previousEventStop(action.stops, state.hour);
      return stop ? at(stop.hour) : state;
    }
    case "focus": {
      const focus = action.on ?? !state.focus;
      return focus === state.focus ? state : { ...state, focus };
    }
  }
}

// --- Keys ------------------------------------------------------------------------------------------------

/** What a key of the page does. */
export type CommandKeyAction =
  | { type: "toggle_play" }
  | { type: "step"; hours: number }
  | { type: "event"; direction: -1 | 1 }
  | { type: "toggle_focus" }
  | { type: "escape" }
  | { type: "help" }
  | { type: "undo" };

export interface CommandKeyInput { key: string; shiftKey?: boolean; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }

/**
 * Where the key was pressed: on the page, in a text field (it keeps its keys), on a control that Space or Enter
 * presses (a button, a link), or on the time slider (it moves by one hour on its own arrow keys).
 */
export type CommandKeyTarget = "page" | "field" | "control" | "slider";

export const COMMAND_DAY_HOURS = 24;

/**
 * The action of a key press, or null when the key is not one of the page's:
 *   Space plays or pauses; the arrow keys step one replay hour, with Shift one day; `[` and `]` go to the previous
 *   and the next event; F switches focus mode; `?` opens the help; U takes back the last action of the exercise
 *   while its line with "Undo" is on screen; Escape closes what is open.
 * Keys held with Alt, Ctrl or the Command key are left to the browser.
 */
export function commandKeyAction(input: CommandKeyInput, target: CommandKeyTarget = "page"): CommandKeyAction | null {
  if (input.altKey || input.ctrlKey || input.metaKey) return null;
  if (input.key === "Escape") return { type: "escape" };
  if (target === "field") return null;
  switch (input.key) {
    case " ":
    case "Spacebar":
      // On a button or a link, Space presses it.
      return target === "control" ? null : { type: "toggle_play" };
    case "ArrowRight":
    case "ArrowLeft": {
      const direction = input.key === "ArrowRight" ? 1 : -1;
      if (input.shiftKey) return { type: "step", hours: direction * COMMAND_DAY_HOURS };
      // The slider moves by one hour on its own.
      return target === "slider" ? null : { type: "step", hours: direction };
    }
    case "[": return { type: "event", direction: -1 };
    case "]": return { type: "event", direction: 1 };
    case "f":
    case "F": return { type: "toggle_focus" };
    case "?": return { type: "help" };
    case "u":
    case "U": return { type: "undo" };
    default: return null;
  }
}

// --- The hour in the address bar -------------------------------------------------------------------------

/** The replay hour and the language are the Studio replay's own parameters: one address, one moment, on both pages. */
const HOUR_PARAM: (typeof LINK_PARAMS)[number] = "t";
const LANGUAGE_PARAM: (typeof LINK_PARAMS)[number] = "lang";

/** What the Command page reads from its address. */
export interface CommandLink {
  /** Whole replay hour, or null when the address names none (or an invalid one). */
  hour: number | null;
  language: Language | null;
}

/** Read `t` (whole hours since 9 Sep 00:00 ICT, 0 … 264) and `lang` from a query string, as the Studio replay does. */
export function parseCommandLink(search: string): CommandLink {
  const params = new URLSearchParams(search);
  const t = params.get(HOUR_PARAM)?.trim() ?? "";
  const hour = /^\d{1,5}$/.test(t) && Number(t) <= COMMAND_LAST_HOUR ? Number(t) : null;
  const lang = params.get(LANGUAGE_PARAM)?.trim();
  return { hour, language: lang === "en" || lang === "th" ? lang : null };
}

/** The query string (without "?") with the replay hour and the language set; other parameters are kept. */
export function mergeCommandLink(search: string, state: { hour: number; language: Language }): string {
  const rest = new URLSearchParams(search);
  rest.delete(HOUR_PARAM);
  rest.delete(LANGUAGE_PARAM);
  const own = new URLSearchParams();
  own.set(HOUR_PARAM, String(clampCommandHour(state.hour)));
  own.set(LANGUAGE_PARAM, state.language);
  const tail = rest.toString();
  return tail ? `${own.toString()}&${tail}` : own.toString();
}

/**
 * The Studio replay at the same replay hour. The Command figures count all residents at road nodes, so the address
 * asks the Studio page for that scope too (`pop=all`); its own default counts homes that flood at the peak.
 */
export function studioReplayHref(hour: number, language: Language): string {
  return `${MAE_SAI_REPLAY_ROUTE}?${HOUR_PARAM}=${clampCommandHour(hour)}&pop=all&${LANGUAGE_PARAM}=${language}`;
}
