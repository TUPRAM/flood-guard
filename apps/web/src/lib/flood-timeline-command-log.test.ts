/**
 * The exercise as one device keeps it: the callsign rule, the roster, the stored setup, the state machine of an
 * invented item, the undo of an action, the log and its export, and the keys "Reset exercise" clears.
 */

import { describe, expect, it } from "vitest";

import { EXERCISE_STATUSES, type ExerciseItem } from "./flood-timeline-command-incidents";
import {
  addRosterTeam,
  appendLog,
  applyItemAction,
  CALLSIGN_MAX_LENGTH,
  callsignProblem,
  COMMAND_LOG_COLUMNS,
  COMMAND_LOG_LIMIT,
  COMMAND_STORAGE_KEYS,
  COMMAND_STORAGE_PREFIX,
  COMMAND_UNDO_MS,
  commandKeysToClear,
  commandLogCsv,
  DEFAULT_COMMAND_SETUP,
  EMPTY_EXERCISE_STATE,
  EXAMPLE_ROSTER,
  handlingMap,
  handlingRecord,
  NEW_RECORD,
  nextHandling,
  normaliseCallsign,
  parseCommandLog,
  parseCommandSetup,
  parseHandlingState,
  removeRosterTeam,
  replayTimeIct,
  ROSTER_MAX_TEAMS,
  setRosterTeamType,
  undoItemAction,
  undoOpen,
  withOperatorUrgency,
  type CommandExerciseState,
  type CommandHandlingRecord,
  type CommandItemAction,
  type CommandLogEntry,
  type RosterTeam,
} from "./flood-timeline-command-log";

const roster: RosterTeam[] = [{ callsign: "BOAT-1", type: "boat" }, { callsign: "MED-1", type: "medical" }];
const urgent: Pick<ExerciseItem, "id" | "urgency"> = { id: "EX-02", urgency: "urgent" };
const T0 = Date.parse("2026-10-05T03:00:00.000Z");
const context = (nowMs = T0, replayHour = 60) => ({ replayHour, nowMs, roster });
const next = (record: CommandHandlingRecord, action: CommandItemAction) => nextHandling(record, action, { roster, authorUrgency: "urgent" });
const record = (more: Partial<CommandHandlingRecord>): CommandHandlingRecord => ({ ...NEW_RECORD, ...more });
const act = (state: CommandExerciseState, action: CommandItemAction, nowMs = T0) => {
  const result = applyItemAction(state, urgent, action, context(nowMs));
  if ("refused" in result) throw new Error(`refused: ${result.refused}`);
  return result;
};

describe("The callsign rule", () => {
  it("takes a callsign of letters, digits, spaces and hyphens, in any script", () => {
    for (const callsign of ["BOAT-2", "med 1", "เรือ 1", "กู้ภัย-3", "T1", "A123456"]) expect(callsignProblem(callsign), callsign).toBeNull();
    expect(normaliseCallsign("  med   1 ")).toBe("MED 1");
    expect(normaliseCallsign("เรือ 1")).toBe("เรือ 1");
  });

  it("refuses an entry of more than 12 characters", () => {
    expect(CALLSIGN_MAX_LENGTH).toBe(12);
    expect(callsignProblem("ABCDEFGHIJKL")).toBeNull();
    expect(callsignProblem("ABCDEFGHIJKLM")).toBe("too_long");
    // Thai letters with their vowels and tone marks are counted one by one, like any other character.
    expect(callsignProblem("ชุดกู้ภัยแม่สาย")).toBe("too_long");
  });

  it("refuses any entry with seven or more digits, however they are spaced, before anything else", () => {
    for (const entry of ["0812345678", "081-234-5678", "T 123 456 7", "A1234567", "1234567", "๐๘๑๒๓๔๕๖๗", "+66812345678", "12345678901234567890"]) {
      expect(callsignProblem(entry), entry).toBe("digits");
    }
    expect(callsignProblem("A123456")).toBeNull();
    // A stored phone number never returns to the roster either.
    expect(addRosterTeam([], "0812345678", "boat")).toEqual([]);
  });

  it("refuses an empty entry, other characters, a second entry of the same callsign and a thirteenth team", () => {
    expect(callsignProblem("   ")).toBe("empty");
    for (const entry of ["boat_1", "-BOAT", " -1", "A/B", "name@x", "B.1"]) expect(callsignProblem(entry), entry).toBe("characters");
    expect(callsignProblem("boat-1", roster)).toBe("duplicate");
    const full = Array.from({ length: ROSTER_MAX_TEAMS }, (_, index) => ({ callsign: `T${index}`, type: "boat" as const }));
    expect(callsignProblem("NEW", full)).toBe("roster_full");
  });

  it("adds, removes and retypes a team without touching the others", () => {
    const added = addRosterTeam(roster, "wade 1", "wading");
    expect(added).toEqual([...roster, { callsign: "WADE 1", type: "wading" }]);
    expect(addRosterTeam(roster, "BOAT-1", "boat")).toEqual(roster);
    expect(removeRosterTeam(added, "BOAT-1").map((team) => team.callsign)).toEqual(["MED-1", "WADE 1"]);
    expect(setRosterTeamType(roster, "MED-1", "vehicle")[1]).toEqual({ callsign: "MED-1", type: "vehicle" });
  });
});

describe("The stored setup", () => {
  it("starts with the example roster, the district office as the staging point, trainee mode and the pause on", () => {
    expect(DEFAULT_COMMAND_SETUP).toMatchObject({ staging: { type: "site", id: "R05" }, startHour: 36, mode: "trainee", itemsOn: true, speed: "hour_per_second", pauseOnLife: true });
    expect(DEFAULT_COMMAND_SETUP.roster).toEqual(EXAMPLE_ROSTER);
    for (const team of EXAMPLE_ROSTER) expect(callsignProblem(team.callsign), team.callsign).toBeNull();
    expect(parseCommandSetup(null)).toEqual(DEFAULT_COMMAND_SETUP);
    expect(parseCommandSetup("nonsense")).toEqual(DEFAULT_COMMAND_SETUP);
  });

  it("reads a stored setup field by field, and drops what the callsign rule refuses", () => {
    const setup = parseCommandSetup({
      roster: [{ callsign: "boat-9", type: "boat" }, { callsign: "0812345678", type: "boat" }, { callsign: "X", type: "plane" }, { callsign: "boat-9", type: "medical" }],
      staging: { type: "point", lat: 20.43, lon: 99.88 }, startHour: 300.4, mode: "hindsight", itemsOn: false, speed: "drill", pauseOnLife: false,
    });
    expect(setup.roster).toEqual([{ callsign: "BOAT-9", type: "boat" }]);
    expect(setup).toMatchObject({ staging: { type: "point", lat: 20.43, lon: 99.88 }, startHour: 264, mode: "hindsight", itemsOn: false, speed: "drill", pauseOnLife: false });
    // An empty roster is a roster: the facilitator removed every team.
    expect(parseCommandSetup({ roster: [] }).roster).toEqual([]);
  });

  it("falls back to the default of a field it does not understand", () => {
    const setup = parseCommandSetup({ roster: "x", staging: { type: "site", id: "R19" }, startHour: "36", mode: "expert", itemsOn: 1, speed: "fast", pauseOnLife: null });
    expect(setup).toEqual(DEFAULT_COMMAND_SETUP);
    expect(parseCommandSetup({ staging: { type: "point", lat: 120, lon: 99 } }).staging).toEqual({ type: "site", id: "R05" });
    expect(parseCommandSetup({ staging: { type: "site", id: "R01" } }).staging).toEqual({ type: "site", id: "R01" });
  });
});

describe("The state machine of an invented item", () => {
  it("has the five states of the plan, and never a state that calls an item checked", () => {
    expect(EXERCISE_STATUSES).toEqual(["new", "acknowledged", "assigned", "done", "dropped"]);
  });

  it("moves new → acknowledged → assigned → done", () => {
    const acknowledged = next(NEW_RECORD, { type: "acknowledge" });
    expect(acknowledged).toEqual({ record: record({ status: "acknowledged" }) });
    const assigned = next(record({ status: "acknowledged" }), { type: "assign", callsign: "boat-1" });
    expect(assigned).toEqual({ record: record({ status: "assigned", callsign: "BOAT-1" }) });
    expect(next(record({ status: "assigned", callsign: "BOAT-1" }), { type: "done" })).toEqual({ record: record({ status: "done", callsign: "BOAT-1" }) });
  });

  it("assigns a new item at once, and assigns an assigned item to another callsign", () => {
    expect(next(NEW_RECORD, { type: "assign", callsign: "MED-1" })).toEqual({ record: record({ status: "assigned", callsign: "MED-1" }) });
    expect(next(record({ status: "assigned", callsign: "MED-1" }), { type: "assign", callsign: "BOAT-1" })).toEqual({ record: record({ status: "assigned", callsign: "BOAT-1" }) });
    expect(next(record({ status: "assigned", callsign: "MED-1" }), { type: "assign", callsign: "MED-1" })).toEqual({ refused: "already" });
  });

  it("refuses a callsign that is not on the roster", () => {
    expect(next(NEW_RECORD, { type: "assign", callsign: "GHOST-9" })).toEqual({ refused: "unknown_callsign" });
    expect(next(NEW_RECORD, { type: "assign", callsign: "0812345678" })).toEqual({ refused: "unknown_callsign" });
  });

  it("closes an open item from any state, as done or as dropped with its reason", () => {
    for (const status of ["new", "acknowledged", "assigned"] as const) {
      const open = record({ status, callsign: status === "assigned" ? "BOAT-1" : null });
      expect(next(open, { type: "done" })).toEqual({ record: { ...open, status: "done" } });
      expect(next(open, { type: "drop", reason: "duplicate" })).toEqual({ record: { ...open, status: "dropped", reason: "duplicate" } });
      expect(next(open, { type: "drop", reason: "unreachable" })).toEqual({ record: { ...open, status: "dropped", reason: "unreachable" } });
      expect(next(open, { type: "reopen" })).toEqual({ refused: "not_closed" });
    }
  });

  it("does nothing to a closed item except reopening it", () => {
    for (const status of ["done", "dropped"] as const) {
      const closed = record({ status, callsign: "BOAT-1", reason: status === "dropped" ? "duplicate" : null });
      for (const action of [{ type: "acknowledge" }, { type: "assign", callsign: "MED-1" }, { type: "done" }, { type: "drop", reason: "duplicate" }, { type: "urgency", direction: 1 }] as CommandItemAction[]) {
        expect(next(closed, action), `${status} ${action.type}`).toEqual({ refused: "closed" });
      }
      expect(next(closed, { type: "reopen" })).toEqual({ record: record({ status: "assigned", callsign: "BOAT-1" }) });
    }
    // Without a callsign a reopened item is acknowledged: somebody has looked at it.
    expect(next(record({ status: "dropped", reason: "unreachable" }), { type: "reopen" })).toEqual({ record: record({ status: "acknowledged" }) });
    expect(next(record({ status: "acknowledged" }), { type: "acknowledge" })).toEqual({ refused: "already" });
  });

  it("raises and lowers the urgency one step, and forgets the change when it is back at the author's", () => {
    const raised = next(NEW_RECORD, { type: "urgency", direction: 1 });
    expect(raised).toEqual({ record: record({ urgency: "life_at_risk" }) });
    expect(next(record({ urgency: "life_at_risk" }), { type: "urgency", direction: 1 })).toEqual({ refused: "at_limit" });
    expect(next(record({ urgency: "life_at_risk" }), { type: "urgency", direction: -1 })).toEqual({ record: NEW_RECORD });
    expect(next(NEW_RECORD, { type: "urgency", direction: -1 })).toEqual({ record: record({ urgency: "information" }) });
    expect(next(record({ urgency: "information" }), { type: "urgency", direction: -1 })).toEqual({ refused: "at_limit" });
  });

  it("shows the operator's urgency on the item, and leaves a list without a change as it is", () => {
    const items = [{ id: "EX-02", urgency: "urgent" }, { id: "EX-05", urgency: "life_at_risk" }] as ExerciseItem[];
    expect(withOperatorUrgency(items, {})).toBe(items);
    expect(withOperatorUrgency(items, { "EX-02": record({ status: "acknowledged" }) })).toBe(items);
    const changed = withOperatorUrgency(items, { "EX-02": record({ urgency: "life_at_risk" }) });
    expect(changed.map((item) => item.urgency)).toEqual(["life_at_risk", "life_at_risk"]);
    expect(changed[1]).toBe(items[1]);
    expect(items[0].urgency).toBe("urgent");
  });
});

describe("Actions, their undo and the log", () => {
  it("logs an action with the replay hour, the time of the device, the role and the callsign", () => {
    const { state, undo } = act(EMPTY_EXERCISE_STATE, { type: "assign", callsign: "BOAT-1" });
    expect(handlingRecord(state.handling, "EX-02")).toEqual(record({ status: "assigned", callsign: "BOAT-1" }));
    expect(state.log).toEqual([{ seq: 1, replayHour: 60, deviceTime: "2026-10-05T03:00:00.000Z", role: "coordinator", callsign: "BOAT-1", action: "assigned", itemId: "EX-02", detail: null }]);
    expect(undo).toMatchObject({ itemId: "EX-02", action: "assigned", before: null, atMs: T0 });
    expect(handlingMap(state.handling).get("EX-02")).toEqual({ status: "assigned", callsign: "BOAT-1" });
  });

  it("leaves no row for an action that is refused", () => {
    const closed = act(EMPTY_EXERCISE_STATE, { type: "done" }).state;
    expect(applyItemAction(closed, urgent, { type: "done" }, context())).toEqual({ refused: "closed" });
    expect(closed.log).toHaveLength(1);
  });

  it("logs a drop with its reason and a change of urgency with both levels", () => {
    const dropped = act(EMPTY_EXERCISE_STATE, { type: "drop", reason: "unreachable" }).state;
    expect(dropped.log[0]).toMatchObject({ action: "dropped", detail: "unreachable" });
    const raised = act(EMPTY_EXERCISE_STATE, { type: "urgency", direction: 1 }).state;
    expect(raised.log[0]).toMatchObject({ action: "urgency_raised", detail: "urgent>life_at_risk" });
    const lowered = act(raised, { type: "urgency", direction: -1 }).state;
    expect(lowered.log[1]).toMatchObject({ action: "urgency_lowered", detail: "life_at_risk>urgent" });
    expect(lowered.handling["EX-02"].urgency).toBeNull();
  });

  it("undoes an action within ten seconds, and writes a row that says so", () => {
    expect(COMMAND_UNDO_MS).toBe(10_000);
    const { state, undo } = act(EMPTY_EXERCISE_STATE, { type: "assign", callsign: "BOAT-1" });
    expect(undoOpen(undo, T0 + 10_000)).toBe(true);
    expect(undoOpen(undo, T0 + 10_001)).toBe(false);
    const undone = undoItemAction(state, undo, { replayHour: 61, nowMs: T0 + 4_000 })!;
    expect(undone.handling).toEqual({});
    expect(undone.log.map((entry) => entry.action)).toEqual(["assigned", "undone"]);
    expect(undone.log[1]).toMatchObject({ seq: 2, replayHour: 61, deviceTime: "2026-10-05T03:00:04.000Z", itemId: "EX-02", detail: "assigned", callsign: "BOAT-1" });
    // After ten seconds the action stands.
    expect(undoItemAction(state, undo, { replayHour: 61, nowMs: T0 + 10_001 })).toBeNull();
  });

  it("returns an item to the record it had before, not to new", () => {
    const assigned = act(EMPTY_EXERCISE_STATE, { type: "assign", callsign: "BOAT-1" }).state;
    const { state, undo } = act(assigned, { type: "done" }, T0 + 1_000);
    const undone = undoItemAction(state, undo, { replayHour: 60, nowMs: T0 + 2_000 })!;
    expect(undone.handling["EX-02"]).toEqual(record({ status: "assigned", callsign: "BOAT-1" }));
  });

  it("does not undo an action once the item has been handled again", () => {
    const first = act(EMPTY_EXERCISE_STATE, { type: "acknowledge" });
    const second = act(first.state, { type: "assign", callsign: "MED-1" }, T0 + 1_000);
    expect(undoItemAction(second.state, first.undo, { replayHour: 60, nowMs: T0 + 2_000 })).toBeNull();
    expect(undoItemAction(second.state, second.undo, { replayHour: 60, nowMs: T0 + 2_000 })!.handling["EX-02"].status).toBe("acknowledged");
  });

  it("keeps the newest rows of a long log, numbered on", () => {
    let log: CommandLogEntry[] = [];
    for (let index = 0; index < COMMAND_LOG_LIMIT + 20; index += 1) {
      log = appendLog(log, { replayHour: 10, deviceTime: "2026-10-05T03:00:00.000Z", role: "coordinator", callsign: null, action: "brief_shown", itemId: "EX-01", detail: "th" });
    }
    expect(log).toHaveLength(COMMAND_LOG_LIMIT);
    expect(log[0].seq).toBe(21);
    expect(log[log.length - 1].seq).toBe(COMMAND_LOG_LIMIT + 20);
  });

  it("never lets free text into the log: a detail is a short code or nothing", () => {
    const log = appendLog([], { replayHour: 500, deviceTime: "2026-10-05T03:00:00.000Z", role: "facilitator", callsign: null, action: "setup_changed", itemId: null, detail: "Somebody typed a sentence here." });
    expect(log[0].detail).toBeNull();
    expect(log[0].replayHour).toBe(264);
    expect(appendLog([], { ...log[0], detail: "roster" })[0].detail).toBe("roster");
  });
});

describe("What a device has stored", () => {
  it("reads stored handling record by record", () => {
    const state = parseHandlingState({
      "EX-02": { status: "assigned", callsign: "boat-1", urgency: "life_at_risk", reason: "duplicate" },
      "EX-03": { status: "dropped", callsign: null, urgency: null, reason: "unreachable" },
      "EX-04": { status: "assigned", callsign: "0812345678" },
      "EX-05": { status: "checked" },
      "REAL-1": { status: "done" },
    });
    expect(state).toEqual({
      "EX-02": { status: "assigned", callsign: "BOAT-1", urgency: "life_at_risk", reason: null },
      "EX-03": { status: "dropped", callsign: null, urgency: null, reason: "unreachable" },
    });
    expect(parseHandlingState([])).toEqual({});
  });

  it("reads a stored log row by row, in the order the actions were taken", () => {
    const rows = [
      { seq: 2, replayHour: 61, deviceTime: "2026-10-05T03:00:04Z", role: "coordinator", callsign: "boat-1", action: "done", itemId: "EX-02", detail: null },
      { seq: 1, replayHour: 60, deviceTime: "2026-10-05T03:00:00Z", role: "facilitator", callsign: null, action: "setup_changed", itemId: null, detail: "roster" },
      { seq: 3, replayHour: 60, deviceTime: "not a time", role: "coordinator", callsign: null, action: "done", itemId: "EX-02", detail: null },
      { seq: 4, replayHour: 60, deviceTime: "2026-10-05T03:00:00Z", role: "caller", callsign: null, action: "done", itemId: "EX-02", detail: null },
      { seq: 5, replayHour: 60, deviceTime: "2026-10-05T03:00:00Z", role: "coordinator", callsign: "0812345678", action: "sent", itemId: "EX-02", detail: null },
    ];
    const log = parseCommandLog(rows);
    expect(log.map((entry) => entry.seq)).toEqual([1, 2]);
    expect(log[1]).toMatchObject({ callsign: "BOAT-1", deviceTime: "2026-10-05T03:00:04.000Z" });
    expect(parseCommandLog({})).toEqual([]);
  });

  it("clears every Command key on a reset, and no other key", () => {
    const keys = [...Object.values(COMMAND_STORAGE_KEYS), `${COMMAND_STORAGE_PREFIX}later:v2`, "floodguard:language:v1", "floodguard:public-reports:v1", "floodguard:household-plan:v2", "other"];
    expect(commandKeysToClear(keys)).toEqual([...Object.values(COMMAND_STORAGE_KEYS), `${COMMAND_STORAGE_PREFIX}later:v2`]);
    for (const key of Object.values(COMMAND_STORAGE_KEYS)) expect(key.startsWith(COMMAND_STORAGE_PREFIX)).toBe(true);
  });
});

describe("The export", () => {
  const log = [
    act(EMPTY_EXERCISE_STATE, { type: "assign", callsign: "BOAT-1" }).state.log[0],
    { seq: 2, replayHour: 84, deviceTime: "2026-10-05T03:01:00.000Z", role: "facilitator" as const, callsign: null, action: "setup_changed" as const, itemId: null, detail: "roster" },
  ];

  it("has a header row, one row per action and a column that marks every row as simulated", () => {
    const csv = commandLogCsv(log);
    const rows = csv.trimEnd().split("\r\n");
    expect(rows[0]).toBe("seq,replay_hour,replay_time_ict,device_time_utc,role,callsign,action,item_id,detail,simulated");
    expect(COMMAND_LOG_COLUMNS[COMMAND_LOG_COLUMNS.length - 1]).toBe("simulated");
    expect(rows).toHaveLength(3);
    expect(rows[1]).toBe("1,60,2024-09-11 12:00,2026-10-05T03:00:00.000Z,coordinator,BOAT-1,assigned,EX-02,,true");
    expect(rows[2]).toBe("2,84,2024-09-12 12:00,2026-10-05T03:01:00.000Z,facilitator,,setup_changed,,roster,true");
    for (const row of rows.slice(1)) expect(row.endsWith(",true")).toBe(true);
    expect(csv.endsWith("\r\n")).toBe(true);
    expect(commandLogCsv([])).toBe(`${COMMAND_LOG_COLUMNS.join(",")}\r\n`);
  });

  it("holds no column for rain, for a note or for a name", () => {
    for (const column of COMMAND_LOG_COLUMNS) expect(column).not.toMatch(/rain|note|text|name|phone|latitude|longitude/);
  });

  it("writes the replay time in local time, and the end of the replay as 20 Sep 00:00", () => {
    expect(replayTimeIct(0)).toBe("2024-09-09 00:00");
    expect(replayTimeIct(84)).toBe("2024-09-12 12:00");
    expect(replayTimeIct(264)).toBe("2024-09-20 00:00");
  });

  it("quotes a field with a comma, and never lets a spreadsheet read a field as a formula", () => {
    const odd = [{ ...log[0], callsign: "A,B", detail: "x" }, { ...log[0], seq: 3, callsign: "=SUM(A1)", detail: null }, { ...log[0], seq: 4, callsign: 'Q"1', detail: null }];
    const rows = commandLogCsv(odd).trimEnd().split("\r\n");
    expect(rows[1]).toContain(',"A,B",');
    expect(rows[2]).toContain(",'=SUM(A1),");
    expect(rows[3]).toContain(',"Q""1",');
  });
});
