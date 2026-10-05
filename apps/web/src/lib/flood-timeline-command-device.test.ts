/**
 * What a device stores of the exercise: the setup, the handling of the items and the log, in the browser of that device
 * and nowhere else. A reset clears every Command key and no other key, and can be put back; a browser that gives no
 * storage keeps the exercise in memory until the page is closed.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { COMMAND_STORAGE_KEYS, DEFAULT_COMMAND_SETUP } from "./flood-timeline-command-log";

/** A browser storage that keeps its keys in order, as `localStorage` does. */
function fakeStorage(seed: Record<string, string> = {}, options: { failWrites?: boolean } = {}) {
  const store = new Map<string, string>(Object.entries(seed));
  return {
    store,
    get length() { return store.size; },
    key: (index: number) => [...store.keys()][index] ?? null,
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      if (options.failWrites) throw new Error("QuotaExceededError");
      store.set(key, value);
    },
    removeItem: (key: string) => { store.delete(key); },
  };
}

/** The device store, loaded fresh on a browser with this storage: the module keeps what it last wrote. */
async function load(storage: ReturnType<typeof fakeStorage> | null) {
  vi.resetModules();
  vi.stubGlobal("window", {
    get localStorage() {
      if (!storage) throw new Error("SecurityError");
      return storage;
    },
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  });
  return import("./flood-timeline-command-device");
}

const LOG = { replayHour: 60, deviceTime: "2026-10-05T03:00:00.000Z", part: "roster" };
const HANDLED = { handling: { "EX-05": { status: "assigned" as const, callsign: "BOAT-2", urgency: null, reason: null } }, log: [] };

describe("The exercise as a device keeps it", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => vi.unstubAllGlobals());

  it("starts with the default setup, nothing handled and an empty log", async () => {
    const device = await load(fakeStorage());
    const state = device.readCommandDevice();
    expect(state.setup).toEqual(DEFAULT_COMMAND_SETUP);
    expect(state.handling).toEqual({});
    expect(state.log).toEqual([]);
    // What is read stays the same object until what is stored changes: a render never loops on it.
    expect(device.readCommandDevice()).toBe(state);
  });

  it("stores a change of the setup at once, with a row that says which part the facilitator changed", async () => {
    const storage = fakeStorage();
    const device = await load(storage);
    device.writeCommandSetup({ mode: "hindsight", roster: [{ callsign: "RESCUE 7", type: "boat" }] }, LOG);
    const state = device.readCommandDevice();
    expect(state.setup).toMatchObject({ mode: "hindsight", roster: [{ callsign: "RESCUE 7", type: "boat" }], startHour: 36 });
    expect(state.log).toEqual([{ seq: 1, replayHour: 60, deviceTime: "2026-10-05T03:00:00.000Z", role: "facilitator", callsign: null, action: "setup_changed", itemId: null, detail: "roster" }]);
    expect(JSON.parse(storage.store.get(COMMAND_STORAGE_KEYS.setup)!).mode).toBe("hindsight");
    // A change without a row (the page restoring itself) leaves the log alone.
    device.writeCommandSetup({ speed: "drill" });
    expect(device.readCommandDevice().log).toHaveLength(1);
    device.writeCommandSetup({}, { ...LOG, part: "start", action: "exercise_started" });
    expect(device.readCommandDevice().log[1]).toMatchObject({ seq: 2, action: "exercise_started", detail: "start" });
  });

  it("reads what the browser has stored through the same rules as a typed entry", async () => {
    const device = await load(fakeStorage({
      [COMMAND_STORAGE_KEYS.setup]: JSON.stringify({ roster: [{ callsign: "0812345678", type: "boat" }, { callsign: "med 1", type: "medical" }], speed: "warp" }),
      [COMMAND_STORAGE_KEYS.handling]: "not json",
      [COMMAND_STORAGE_KEYS.log]: JSON.stringify([{ seq: 1, replayHour: 60, deviceTime: "2026-10-05T03:00:00Z", role: "coordinator", callsign: "MED 1", action: "done", itemId: "EX-02", detail: null }]),
    }));
    const state = device.readCommandDevice();
    expect(state.setup.roster).toEqual([{ callsign: "MED 1", type: "medical" }]);
    expect(state.setup.speed).toBe("hour_per_second");
    expect(state.handling).toEqual({});
    expect(state.log).toHaveLength(1);
  });

  it("clears every Command key on a reset and no other key, and puts them back on its undo", async () => {
    const storage = fakeStorage({ "floodguard:language:v1": "th", "floodguard:public-reports:v1": "[]", "floodguard:command-exercise:later:v2": "x" });
    const device = await load(storage);
    device.writeCommandSetup({ mode: "hindsight" }, LOG);
    device.writeCommandExercise({ ...HANDLED, log: device.readCommandDevice().log });
    expect(Object.keys(device.readCommandDevice().handling)).toEqual(["EX-05"]);
    const backup = device.resetCommandDevice();
    expect([...storage.store.keys()].sort()).toEqual(["floodguard:language:v1", "floodguard:public-reports:v1"]);
    expect(device.readCommandDevice().setup).toEqual(DEFAULT_COMMAND_SETUP);
    expect(device.readCommandDevice().handling).toEqual({});
    expect(device.readCommandDevice().log).toEqual([]);
    device.restoreCommandDevice(backup);
    const restored = device.readCommandDevice();
    expect(restored.setup.mode).toBe("hindsight");
    expect(restored.handling["EX-05"]).toMatchObject({ status: "assigned", callsign: "BOAT-2" });
    expect(restored.log).toHaveLength(1);
    expect(storage.store.get("floodguard:language:v1")).toBe("th");
  });

  it("adds a row to the log without touching the rest", async () => {
    const device = await load(fakeStorage());
    device.writeCommandExercise(HANDLED);
    device.logCommandAction({ replayHour: 61, deviceTime: "2026-10-05T03:01:00.000Z", role: "coordinator", callsign: "BOAT-2", action: "brief_copied", itemId: "EX-05", detail: "th" });
    const state = device.readCommandDevice();
    expect(state.log).toEqual([{ seq: 1, replayHour: 61, deviceTime: "2026-10-05T03:01:00.000Z", role: "coordinator", callsign: "BOAT-2", action: "brief_copied", itemId: "EX-05", detail: "th" }]);
    expect(state.handling["EX-05"].callsign).toBe("BOAT-2");
  });

  it("keeps the exercise in memory where the browser gives no storage, or refuses to write", async () => {
    for (const storage of [null, fakeStorage({}, { failWrites: true })]) {
      const device = await load(storage);
      expect(device.readCommandDevice().setup).toEqual(DEFAULT_COMMAND_SETUP);
      device.writeCommandSetup({ pauseOnLife: false }, LOG);
      device.writeCommandExercise({ ...HANDLED, log: device.readCommandDevice().log });
      const state = device.readCommandDevice();
      expect(state.setup.pauseOnLife).toBe(false);
      expect(state.handling["EX-05"].status).toBe("assigned");
      expect(state.log).toHaveLength(1);
      device.resetCommandDevice();
      expect(device.readCommandDevice().handling).toEqual({});
      expect(device.readCommandDevice().setup).toEqual(DEFAULT_COMMAND_SETUP);
    }
  });
});
