"use client";

/**
 * The exercise of the Command exercise replay as this device keeps it: the facilitator's setup, how each invented
 * item is handled, and the exercise log. They are stored in the browser of this device and nowhere else; nothing is
 * sent anywhere. A change made in another tab of the same browser arrives as a `storage` event. Where the browser
 * gives no storage (a private window), the exercise still runs and lasts until the page is closed.
 */

import { useSyncExternalStore } from "react";

import {
  appendLog,
  COMMAND_STORAGE_KEYS,
  COMMAND_STORAGE_SLOTS,
  commandKeysToClear,
  DEFAULT_COMMAND_SETUP,
  parseCommandLog,
  parseCommandSetup,
  parseHandlingState,
  type CommandExerciseState,
  type CommandHandlingState,
  type CommandLogEntry,
  type CommandLogInput,
  type CommandSetup,
  type CommandStorageSlot,
} from "./flood-timeline-command-log";

type RawSlots = Record<CommandStorageSlot, string | null>;

/** What this device holds of the exercise. */
export interface CommandDeviceState {
  setup: CommandSetup;
  handling: CommandHandlingState;
  log: readonly CommandLogEntry[];
}

const EMPTY_RAW: RawSlots = { setup: null, handling: null, log: null };
const SERVER_STATE: CommandDeviceState = { setup: DEFAULT_COMMAND_SETUP, handling: {}, log: [] };

/** What was last written from this page: the truth when the browser gives no storage. */
let memory: RawSlots = { ...EMPTY_RAW };
let storageWorks = true;
let cache: { raw: RawSlots; state: CommandDeviceState } = { raw: { ...EMPTY_RAW }, state: SERVER_STATE };
const listeners = new Set<() => void>();

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function readRaw(): RawSlots {
  const storage = storageWorks ? browserStorage() : null;
  if (!storage) return memory;
  try {
    const raw = { ...EMPTY_RAW };
    for (const slot of COMMAND_STORAGE_SLOTS) raw[slot] = storage.getItem(COMMAND_STORAGE_KEYS[slot]);
    return raw;
  } catch {
    return memory;
  }
}

function parseJson(text: string | null): unknown {
  if (text === null) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

/** The state of the device as one object that stays the same until what is stored changes. */
function snapshot(): CommandDeviceState {
  const raw = readRaw();
  if (COMMAND_STORAGE_SLOTS.every((slot) => raw[slot] === cache.raw[slot])) return cache.state;
  cache = {
    raw: { ...raw },
    state: {
      setup: raw.setup === cache.raw.setup ? cache.state.setup : parseCommandSetup(parseJson(raw.setup)),
      handling: raw.handling === cache.raw.handling ? cache.state.handling : parseHandlingState(parseJson(raw.handling)),
      log: raw.log === cache.raw.log ? cache.state.log : parseCommandLog(parseJson(raw.log)),
    },
  };
  return cache.state;
}

function write(values: Partial<RawSlots>): void {
  memory = { ...readRaw(), ...values };
  const storage = storageWorks ? browserStorage() : null;
  if (storage) {
    try {
      for (const slot of COMMAND_STORAGE_SLOTS) {
        if (!(slot in values)) continue;
        const value = values[slot];
        if (value === null || value === undefined) storage.removeItem(COMMAND_STORAGE_KEYS[slot]);
        else storage.setItem(COMMAND_STORAGE_KEYS[slot], value);
      }
    } catch {
      // The browser refused the write (a private window, a full store): the exercise goes on in memory.
      storageWorks = false;
    }
  } else {
    storageWorks = false;
  }
  for (const notify of listeners) notify();
}

function subscribe(notify: () => void): () => void {
  listeners.add(notify);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || (Object.values(COMMAND_STORAGE_KEYS) as string[]).includes(event.key)) notify();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener("storage", onStorage);
  };
}

/** What this device holds of the exercise, read outside React (the first hour of the replay is set before anything renders). */
export const readCommandDevice = (): CommandDeviceState => snapshot();

/** What a change of the setup leaves in the log: the replay hour, the time of this device, and which part changed. */
export interface CommandSetupLog { replayHour: number; deviceTime: string; part: string; action?: "setup_changed" | "exercise_started" }

/** Change the setup, with a row in the log that says which part the facilitator changed and at which replay hour. */
export function writeCommandSetup(patch: Partial<CommandSetup>, log?: CommandSetupLog): void {
  const now = snapshot();
  const setup = { ...now.setup, ...patch };
  const values: Partial<RawSlots> = { setup: JSON.stringify(setup) };
  if (log) {
    values.log = JSON.stringify(appendLog(now.log, {
      replayHour: log.replayHour, deviceTime: log.deviceTime, role: "facilitator", callsign: null, action: log.action ?? "setup_changed", itemId: null, detail: log.part,
    }));
  }
  write(values);
}

/** Store how the items are handled, and the log. */
export function writeCommandExercise(state: CommandExerciseState): void {
  write({ handling: JSON.stringify(state.handling), log: JSON.stringify(state.log) });
}

/** One more row in the log. */
export function logCommandAction(input: CommandLogInput): void {
  write({ log: JSON.stringify(appendLog(snapshot().log, input)) });
}

/** What "Reset exercise" removed, so that it can be put back within the time an action can be undone. */
export interface CommandDeviceBackup { raw: RawSlots }

/**
 * "Reset exercise": every Command key of this device is removed (the setup with its roster, the handling of the
 * items and the log), and no other key. Returns what was there, for the undo.
 */
export function resetCommandDevice(): CommandDeviceBackup {
  const backup: CommandDeviceBackup = { raw: { ...readRaw() } };
  const storage = storageWorks ? browserStorage() : null;
  if (storage) {
    try {
      const keys: string[] = [];
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        if (key !== null) keys.push(key);
      }
      for (const key of commandKeysToClear(keys)) storage.removeItem(key);
    } catch {
      storageWorks = false;
    }
  }
  memory = { ...EMPTY_RAW };
  for (const notify of listeners) notify();
  return backup;
}

/** Put back what a reset removed. */
export function restoreCommandDevice(backup: CommandDeviceBackup): void {
  write(backup.raw);
}

/** The exercise as this device keeps it; the defaults until the page has read its storage. */
export function useCommandDevice(): CommandDeviceState {
  return useSyncExternalStore(subscribe, snapshot, () => SERVER_STATE);
}
