/**
 * Replay controls of the Command exercise replay: the stops of the event buttons from the served replay data, the
 * replay state under play, steps and speeds, the keys of the page, and the hour kept in the address bar with the same
 * `t` parameter as the Studio replay.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { hourlyStages, TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import { COMMAND_LAST_HOUR } from "./flood-timeline-command";
import {
  COMMAND_DAY_HOURS,
  COMMAND_SPEEDS,
  COMMAND_START_HOUR,
  commandDayChips,
  commandDayIndex,
  commandEventStops,
  commandHourShare,
  commandKeyAction,
  commandPhaseSpans,
  commandReplayReducer,
  commandSpeed,
  DEFAULT_COMMAND_SPEED,
  initialCommandReplay,
  mergeCommandLink,
  nextEventStop,
  parseCommandLink,
  previousEventStop,
  studioReplayHref,
  type CommandReplayState,
} from "./flood-timeline-command-replay";
import { parseReplayLink, type ReplayLinkState } from "./flood-timeline-link";
import { MAE_SAI_REPLAY_ROUTE } from "./policy-links";

const publicRoot = resolve(import.meta.dirname, "../../public");
const manifest = JSON.parse(readFileSync(resolve(publicRoot, TIMELINE_MANIFEST_URL.replace(/^\//, "")), "utf8")) as TimelineManifest;
// Hourly positions 0 … 264, like the page's own model.
const stages = hourlyStages(manifest.stage_anchors, COMMAND_LAST_HOUR + 1);
const stops = commandEventStops(manifest, stages);

describe("Command replay: speeds", () => {
  it("offers one replay hour per second, four per second and the drill speed of one per minute", () => {
    expect(COMMAND_SPEEDS.map((speed) => [speed.id, speed.hourMs])).toEqual([["hour_per_second", 1000], ["four_per_second", 250], ["drill", 60_000]]);
    expect(DEFAULT_COMMAND_SPEED).toBe("hour_per_second");
    expect(commandSpeed("drill").hourMs).toBe(60_000);
  });
});

describe("Command replay: stops of the event buttons", () => {
  it("stops at the start, the first hour of each phase, the hour of the highest assumed stage and the end", () => {
    expect(stops.map((stop) => [stop.hour, stop.kind, stop.phaseId ?? null])).toEqual([
      [0, "start", null], [24, "phase", "onset"], [48, "phase", "peak"], [84, "peak", null], [96, "phase", "receding"], [168, "phase", "gone"], [264, "end", null],
    ]);
    // The peak stop is the first hour at the highest stage of the illustrative curve.
    expect(stages[84]).toBe(Math.max(...stages));
    expect(stages[83]).toBeLessThan(stages[84]);
  });

  it("goes to the stop after or before a replay hour", () => {
    expect(nextEventStop(stops, 36)?.hour).toBe(48);
    expect(nextEventStop(stops, 48)?.hour).toBe(84);
    expect(nextEventStop(stops, 264)).toBeNull();
    expect(previousEventStop(stops, 84)?.hour).toBe(48);
    expect(previousEventStop(stops, 85)?.hour).toBe(84);
    expect(previousEventStop(stops, 0)).toBeNull();
  });
});

describe("Command replay: days and phases of the time bar", () => {
  it("has eleven day chips, 9 to 19 September, each at the first hour of its day", () => {
    const chips = commandDayChips(manifest.days);
    expect(chips.map((chip) => chip.day)).toEqual([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
    expect(chips.map((chip) => chip.hour)).toEqual([0, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240]);
    expect(commandDayIndex(84, chips.length)).toBe(3);
    expect(commandDayIndex(0, chips.length)).toBe(0);
    // The end of the replay, 20 Sep 00:00, belongs to 19 Sep.
    expect(commandDayIndex(264, chips.length)).toBe(10);
  });

  it("lays the five phases end to end over the 264 hours", () => {
    const spans = commandPhaseSpans(manifest.phases);
    expect(spans.map((span) => [span.id, span.from, span.to])).toEqual([["dry", 0, 24], ["onset", 24, 48], ["peak", 48, 96], ["receding", 96, 168], ["gone", 168, 264]]);
    expect(commandHourShare(0)).toBe(0);
    expect(commandHourShare(132)).toBe(0.5);
    expect(commandHourShare(264)).toBe(1);
  });
});

describe("Command replay: the replay state", () => {
  const at = (hour: number, more: Partial<CommandReplayState> = {}): CommandReplayState => ({ ...initialCommandReplay(hour), ...more });

  it("opens paused on 10 Sep 12:00 at one replay hour per second, outside focus mode", () => {
    expect(COMMAND_START_HOUR).toBe(36);
    expect(initialCommandReplay()).toEqual({ hour: 36, playing: false, speed: "hour_per_second", focus: false });
    expect(initialCommandReplay(999).hour).toBe(COMMAND_LAST_HOUR);
  });

  it("steps by one hour and by one day, and never leaves 0 … 264", () => {
    expect(commandReplayReducer(at(84), { type: "step", hours: 1 }).hour).toBe(85);
    expect(commandReplayReducer(at(84), { type: "step", hours: -1 }).hour).toBe(83);
    expect(commandReplayReducer(at(84), { type: "step", hours: COMMAND_DAY_HOURS }).hour).toBe(108);
    expect(commandReplayReducer(at(84), { type: "step", hours: -COMMAND_DAY_HOURS }).hour).toBe(60);
    expect(commandReplayReducer(at(0), { type: "step", hours: -1 }).hour).toBe(0);
    expect(commandReplayReducer(at(260), { type: "step", hours: 24 }).hour).toBe(264);
    expect(commandReplayReducer(at(84), { type: "seek", hour: 130.4 }).hour).toBe(130);
    // A step that changes nothing returns the same state, so nothing re-renders.
    const start = at(0);
    expect(commandReplayReducer(start, { type: "step", hours: -1 })).toBe(start);
  });

  it("plays hour by hour, stops by itself at the end and starts again from the first hour", () => {
    let state = commandReplayReducer(at(262), { type: "toggle_play" });
    expect(state).toMatchObject({ hour: 262, playing: true });
    state = commandReplayReducer(state, { type: "tick" });
    expect(state).toMatchObject({ hour: 263, playing: true });
    state = commandReplayReducer(state, { type: "tick" });
    expect(state).toMatchObject({ hour: 264, playing: false });
    // A tick while paused does nothing.
    expect(commandReplayReducer(state, { type: "tick" })).toBe(state);
    expect(commandReplayReducer(state, { type: "toggle_play" })).toMatchObject({ hour: 0, playing: true });
    expect(commandReplayReducer(at(84, { playing: true }), { type: "toggle_play" })).toMatchObject({ hour: 84, playing: false });
    expect(commandReplayReducer(at(84, { playing: true }), { type: "pause" }).playing).toBe(false);
    // A step while playing keeps playing.
    expect(commandReplayReducer(at(84, { playing: true }), { type: "step", hours: 1 })).toMatchObject({ hour: 85, playing: true });
  });

  it("jumps to the previous and the next event", () => {
    expect(commandReplayReducer(at(36), { type: "event", direction: 1, stops }).hour).toBe(48);
    expect(commandReplayReducer(at(36), { type: "event", direction: -1, stops }).hour).toBe(24);
    const end = at(264);
    expect(commandReplayReducer(end, { type: "event", direction: 1, stops })).toBe(end);
  });

  it("changes speed and focus mode without touching the hour", () => {
    expect(commandReplayReducer(at(84), { type: "speed", speed: "drill" })).toMatchObject({ hour: 84, speed: "drill" });
    expect(commandReplayReducer(at(84), { type: "focus" })).toMatchObject({ hour: 84, focus: true });
    expect(commandReplayReducer(at(84, { focus: true }), { type: "focus" }).focus).toBe(false);
    expect(commandReplayReducer(at(84, { focus: true }), { type: "focus", on: false }).focus).toBe(false);
    const focused = at(84, { focus: true });
    expect(commandReplayReducer(focused, { type: "focus", on: true })).toBe(focused);
  });
});

describe("Command replay: keys", () => {
  it("maps Space, the arrow keys, the brackets, F, the question mark and Escape", () => {
    expect(commandKeyAction({ key: " " })).toEqual({ type: "toggle_play" });
    expect(commandKeyAction({ key: "ArrowRight" })).toEqual({ type: "step", hours: 1 });
    expect(commandKeyAction({ key: "ArrowLeft" })).toEqual({ type: "step", hours: -1 });
    expect(commandKeyAction({ key: "ArrowRight", shiftKey: true })).toEqual({ type: "step", hours: 24 });
    expect(commandKeyAction({ key: "ArrowLeft", shiftKey: true })).toEqual({ type: "step", hours: -24 });
    expect(commandKeyAction({ key: "[" })).toEqual({ type: "event", direction: -1 });
    expect(commandKeyAction({ key: "]" })).toEqual({ type: "event", direction: 1 });
    expect(commandKeyAction({ key: "f" })).toEqual({ type: "toggle_focus" });
    expect(commandKeyAction({ key: "F", shiftKey: true })).toEqual({ type: "toggle_focus" });
    expect(commandKeyAction({ key: "?", shiftKey: true })).toEqual({ type: "help" });
    expect(commandKeyAction({ key: "Escape" })).toEqual({ type: "escape" });
    expect(commandKeyAction({ key: "ArrowUp" })).toBeNull();
    expect(commandKeyAction({ key: "a" })).toBeNull();
  });

  it("leaves keys held with Ctrl, Alt or the Command key to the browser", () => {
    for (const held of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }]) {
      expect(commandKeyAction({ key: "f", ...held })).toBeNull();
      expect(commandKeyAction({ key: "ArrowLeft", ...held })).toBeNull();
      expect(commandKeyAction({ key: "Escape", ...held })).toBeNull();
    }
  });

  it("does not take a key from a text field, a button or the slider", () => {
    // A text field keeps every key but Escape.
    for (const key of [" ", "ArrowRight", "f", "?", "["]) expect(commandKeyAction({ key }, "field")).toBeNull();
    expect(commandKeyAction({ key: "Escape" }, "field")).toEqual({ type: "escape" });
    // Space presses the button or the link it is on; the other keys still work there.
    expect(commandKeyAction({ key: " " }, "control")).toBeNull();
    expect(commandKeyAction({ key: "ArrowRight" }, "control")).toEqual({ type: "step", hours: 1 });
    expect(commandKeyAction({ key: "f" }, "control")).toEqual({ type: "toggle_focus" });
    // The slider moves by one hour on its own arrow keys; with Shift the page steps a day.
    expect(commandKeyAction({ key: "ArrowRight" }, "slider")).toBeNull();
    expect(commandKeyAction({ key: "ArrowRight", shiftKey: true }, "slider")).toEqual({ type: "step", hours: 24 });
    expect(commandKeyAction({ key: " " }, "slider")).toEqual({ type: "toggle_play" });
  });

  it("steps the replay through the reducer: arrows one hour, Shift one day", () => {
    let state = initialCommandReplay(84);
    const press = (key: string, shiftKey = false) => {
      const action = commandKeyAction({ key, shiftKey });
      if (action?.type === "step") state = commandReplayReducer(state, action);
      else if (action?.type === "event") state = commandReplayReducer(state, { ...action, stops });
      else if (action?.type === "toggle_play") state = commandReplayReducer(state, { type: "toggle_play" });
      else if (action?.type === "toggle_focus") state = commandReplayReducer(state, { type: "focus" });
    };
    press("ArrowRight");
    expect(state.hour).toBe(85);
    press("ArrowLeft");
    press("ArrowLeft");
    expect(state.hour).toBe(83);
    press("ArrowRight", true);
    expect(state.hour).toBe(107);
    press("ArrowLeft", true);
    press("ArrowLeft", true);
    expect(state.hour).toBe(59);
    press("]");
    expect(state.hour).toBe(84);
    press("[");
    expect(state.hour).toBe(48);
    press(" ");
    expect(state.playing).toBe(true);
    press("f");
    expect(state.focus).toBe(true);
  });
});

describe("Command replay: the hour in the address bar", () => {
  const studioDefaults: ReplayLinkState = {
    hour: 12, imagery: "auto", waterMode: "depth", waterOpacity: 85, roadMode: "state", compare: null, language: "en",
    layers: { tambons: true, roads: true, facilities: false, reported: true, candidates: true, ineligible: false, cutoff: false, viirs: false, gauges: false, envelope: false, reportedDepths: false },
    shelterSet: "reported", planK: 8, accessScope: "flooded",
  };
  const studioOptions = { maxHour: COMMAND_LAST_HOUR, imageryIds: ["auto", "none"], compareIds: ["auto"], maxPlanK: 12 };

  it("reads the same t parameter as the Studio replay", () => {
    for (const search of ["?t=84", "?t=0", "?t=264", "?lang=th&t=130", "?t=84&wm=depth&pop=all"]) {
      expect(parseCommandLink(search).hour).toBe(parseReplayLink(search, studioDefaults, studioOptions).hour);
    }
    expect(parseCommandLink("?t=84")).toEqual({ hour: 84, language: null });
    expect(parseCommandLink("?t=130&lang=th")).toEqual({ hour: 130, language: "th" });
  });

  it("ignores a missing or invalid hour, as the Studio replay does", () => {
    for (const search of ["", "?t=", "?t=265", "?t=-1", "?t=8.5", "?t=abc", "?t=123456", "?lang=fr"]) {
      expect(parseCommandLink(search), search).toEqual({ hour: null, language: null });
      expect(parseReplayLink(search, studioDefaults, studioOptions).hour, search).toBe(studioDefaults.hour);
    }
  });

  it("writes the hour and the language, and keeps other parameters", () => {
    expect(mergeCommandLink("", { hour: 84, language: "en" })).toBe("t=84&lang=en");
    expect(mergeCommandLink("?t=30&lang=en", { hour: 130, language: "th" })).toBe("t=130&lang=th");
    expect(mergeCommandLink("?case=mae-sai&t=30", { hour: 85, language: "en" })).toBe("t=85&lang=en&case=mae-sai");
    expect(mergeCommandLink("", { hour: 300.2, language: "en" })).toBe("t=264&lang=en");
    // What is written reads back as the same hour, on this page and on the Studio replay.
    for (const hour of [0, 30, 84, 130, 264]) {
      const search = `?${mergeCommandLink("", { hour, language: "th" })}`;
      expect(parseCommandLink(search)).toEqual({ hour, language: "th" });
      expect(parseReplayLink(search, studioDefaults, studioOptions)).toMatchObject({ hour, language: "th" });
    }
  });

  it("links to the Studio replay at the same hour, counting all residents at road nodes", () => {
    expect(studioReplayHref(84, "en")).toBe(`${MAE_SAI_REPLAY_ROUTE}?t=84&pop=all&lang=en`);
    const link = parseReplayLink(studioReplayHref(130, "th").split("?")[1], studioDefaults, studioOptions);
    expect(link).toMatchObject({ hour: 130, accessScope: "all", language: "th" });
  });
});
