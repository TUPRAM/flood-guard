/**
 * The exercise as one device keeps it on the Command exercise replay (Mae Sai, September 2024), as pure functions:
 * the callsign rule and the roster, the facilitator's setup, the handling states of an invented item and the actions
 * that move between them, the undo of an action, the exercise log with its export, and the storage keys.
 *
 * Everything here is exercise state: invented items handled by teams that exist as callsigns only. Nothing is sent
 * anywhere, and every exported row is marked as simulated. The roster takes callsigns, never names or phone numbers:
 * at most 12 characters, and an entry with seven or more digits is refused. A log row holds a replay time, the time
 * of this device, a role, a callsign and an action; it never holds a rain value, a note of a report or the text of
 * a place record. No DOM access in this module.
 */

import { TIMELINE_EPOCH_MS } from "./flood-timeline";
import { clampCommandHour } from "./flood-timeline-command";
import { COMMAND_MODES, DEFAULT_COMMAND_MODE, type CommandMode } from "./flood-timeline-command-feed";
import {
  EXERCISE_STATUSES,
  EXERCISE_URGENCIES,
  isOpenStatus,
  type ExerciseHandling,
  type ExerciseItem,
  type ExerciseStatus,
  type ExerciseUrgency,
} from "./flood-timeline-command-incidents";
import { COMMAND_SPEEDS, COMMAND_START_HOUR, DEFAULT_COMMAND_SPEED, type CommandSpeedId } from "./flood-timeline-command-replay";

// --- Storage keys ----------------------------------------------------------------------------------------

/** Every key the Command exercise keeps on a device starts with this, so "Reset exercise" can clear them all. */
export const COMMAND_STORAGE_PREFIX = "floodguard:command-exercise:";
export const COMMAND_STORAGE_KEYS = {
  setup: `${COMMAND_STORAGE_PREFIX}setup:v1`,
  handling: `${COMMAND_STORAGE_PREFIX}handling:v1`,
  log: `${COMMAND_STORAGE_PREFIX}log:v1`,
} as const;
export type CommandStorageSlot = keyof typeof COMMAND_STORAGE_KEYS;
export const COMMAND_STORAGE_SLOTS: readonly CommandStorageSlot[] = ["setup", "handling", "log"];

/** Of the keys a device holds, the ones "Reset exercise" removes: every Command key, and nothing else. */
export function commandKeysToClear(keys: readonly string[]): string[] {
  return keys.filter((key) => key.startsWith(COMMAND_STORAGE_PREFIX));
}

// --- Callsigns and the roster ----------------------------------------------------------------------------

/** The kind of a team, as its callsign's chip shows it. The page never suggests which kind to send. */
export type TeamType = "boat" | "wading" | "vehicle" | "medical";
export const TEAM_TYPES: readonly TeamType[] = ["boat", "wading", "vehicle", "medical"];
export interface RosterTeam { callsign: string; type: TeamType }

export const CALLSIGN_MAX_LENGTH = 12;
/** An entry with this many digits or more is refused: it could be a phone number or an identity number. */
export const CALLSIGN_DIGIT_LIMIT = 7;
export const ROSTER_MAX_TEAMS = 12;

/** A callsign starts with a letter or a digit and holds letters, digits, spaces and hyphens only. */
const CALLSIGN_SHAPE = /^[\p{L}\p{Nd}][\p{L}\p{M}\p{Nd} -]*$/u;

/** A callsign as the roster keeps it: one space between its words, no space around it, Latin letters in capitals. */
export function normaliseCallsign(text: string): string {
  return text.normalize("NFC").replace(/\s+/g, " ").trim().toUpperCase();
}

export type CallsignProblem = "empty" | "digits" | "too_long" | "characters" | "duplicate" | "roster_full";

/**
 * Why an entry cannot join the roster, or null when it can. The digit rule comes first: an entry with seven or more
 * digits is refused whatever else it holds, so a phone number is never stored, not even for a moment.
 */
export function callsignProblem(text: string, roster: readonly RosterTeam[] = []): CallsignProblem | null {
  const callsign = normaliseCallsign(text);
  if (!callsign) return "empty";
  if ((callsign.match(/\p{Nd}/gu) ?? []).length >= CALLSIGN_DIGIT_LIMIT) return "digits";
  if ([...callsign].length > CALLSIGN_MAX_LENGTH) return "too_long";
  if (!CALLSIGN_SHAPE.test(callsign)) return "characters";
  if (roster.some((team) => team.callsign === callsign)) return "duplicate";
  if (roster.length >= ROSTER_MAX_TEAMS) return "roster_full";
  return null;
}

/** The roster with one more team; the roster itself when the entry is refused. */
export function addRosterTeam(roster: readonly RosterTeam[], text: string, type: TeamType): RosterTeam[] {
  if (callsignProblem(text, roster) !== null) return [...roster];
  return [...roster, { callsign: normaliseCallsign(text), type }];
}

export function removeRosterTeam(roster: readonly RosterTeam[], callsign: string): RosterTeam[] {
  return roster.filter((team) => team.callsign !== callsign);
}

export function setRosterTeamType(roster: readonly RosterTeam[], callsign: string, type: TeamType): RosterTeam[] {
  return roster.map((team) => (team.callsign === callsign ? { ...team, type } : team));
}

/**
 * The roster a device starts with: five example callsigns, one or two of each kind, so that an item can be assigned
 * before the facilitator has typed a roster. They name no real unit.
 */
export const EXAMPLE_ROSTER: readonly RosterTeam[] = [
  { callsign: "BOAT-1", type: "boat" },
  { callsign: "BOAT-2", type: "boat" },
  { callsign: "WADE-1", type: "wading" },
  { callsign: "TRUCK-1", type: "vehicle" },
  { callsign: "MED-1", type: "medical" },
];

// --- The facilitator's setup -----------------------------------------------------------------------------

/**
 * Where the team starts: one of two sites reported in use in 2024 (the district office that held the incident command
 * centre, R05, or the municipality office, R01), or a point the facilitator tapped on the map.
 */
export type StagingChoice = { type: "site"; id: string } | { type: "point"; lat: number; lon: number };
export const STAGING_SITE_IDS: readonly string[] = ["R05", "R01"];
export const DEFAULT_STAGING: StagingChoice = { type: "site", id: "R05" };

export interface CommandSetup {
  roster: RosterTeam[];
  staging: StagingChoice;
  /** The replay hour the exercise starts at (0 … 264). */
  startHour: number;
  mode: CommandMode;
  /** The invented items are on the map and in the counts. */
  itemsOn: boolean;
  speed: CommandSpeedId;
  /** Playback pauses at the hour a life-at-risk item arrives. */
  pauseOnLife: boolean;
}

export const DEFAULT_COMMAND_SETUP: CommandSetup = {
  roster: [...EXAMPLE_ROSTER],
  staging: DEFAULT_STAGING,
  startHour: COMMAND_START_HOUR,
  mode: DEFAULT_COMMAND_MODE,
  itemsOn: true,
  speed: DEFAULT_COMMAND_SPEED,
  pauseOnLife: true,
};

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);

function parseRoster(value: unknown): RosterTeam[] | null {
  if (!Array.isArray(value)) return null;
  let roster: RosterTeam[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.callsign !== "string" || !TEAM_TYPES.includes(entry.type as TeamType)) continue;
    // A stored entry passes the same rule as a typed one: what the rule refuses is dropped.
    roster = addRosterTeam(roster, entry.callsign, entry.type as TeamType);
  }
  return roster;
}

function parseStaging(value: unknown): StagingChoice | null {
  if (!isRecord(value)) return null;
  if (value.type === "site" && typeof value.id === "string" && STAGING_SITE_IDS.includes(value.id)) return { type: "site", id: value.id };
  if (value.type === "point" && typeof value.lat === "number" && typeof value.lon === "number" && Number.isFinite(value.lat) && Number.isFinite(value.lon)
    && Math.abs(value.lat) <= 90 && Math.abs(value.lon) <= 180) return { type: "point", lat: value.lat, lon: value.lon };
  return null;
}

/** A stored setup, field by field: a field that is missing or not understood takes its default. */
export function parseCommandSetup(value: unknown): CommandSetup {
  if (!isRecord(value)) return { ...DEFAULT_COMMAND_SETUP, roster: [...EXAMPLE_ROSTER] };
  const startHour = typeof value.startHour === "number" && Number.isFinite(value.startHour) ? clampCommandHour(value.startHour) : DEFAULT_COMMAND_SETUP.startHour;
  return {
    roster: parseRoster(value.roster) ?? [...EXAMPLE_ROSTER],
    staging: parseStaging(value.staging) ?? DEFAULT_STAGING,
    startHour,
    mode: COMMAND_MODES.includes(value.mode as CommandMode) ? (value.mode as CommandMode) : DEFAULT_COMMAND_SETUP.mode,
    itemsOn: typeof value.itemsOn === "boolean" ? value.itemsOn : DEFAULT_COMMAND_SETUP.itemsOn,
    speed: COMMAND_SPEEDS.some((speed) => speed.id === value.speed) ? (value.speed as CommandSpeedId) : DEFAULT_COMMAND_SETUP.speed,
    pauseOnLife: typeof value.pauseOnLife === "boolean" ? value.pauseOnLife : DEFAULT_COMMAND_SETUP.pauseOnLife,
  };
}

// --- Handling states -------------------------------------------------------------------------------------

/** Why an item was dropped: it repeats another item, or the team could not reach the place. */
export type DropReason = "duplicate" | "unreachable";
export const DROP_REASONS: readonly DropReason[] = ["duplicate", "unreachable"];

/** How one invented item is being handled on this device. */
export interface CommandHandlingRecord {
  status: ExerciseStatus;
  /** The callsign of the team the item is assigned to; kept when the item is closed. */
  callsign: string | null;
  /** The urgency the operator set in place of the author's; null while the author's stands. */
  urgency: ExerciseUrgency | null;
  reason: DropReason | null;
}
/** The handling of every item that is no longer simply "new", by item id. */
export type CommandHandlingState = Readonly<Record<string, CommandHandlingRecord>>;
export const NEW_RECORD: CommandHandlingRecord = { status: "new", callsign: null, urgency: null, reason: null };

export const handlingRecord = (state: CommandHandlingState, id: string): CommandHandlingRecord => state[id] ?? NEW_RECORD;

/** The handling as the markers and the counts read it: the state and the callsign of each item. */
export function handlingMap(state: CommandHandlingState): Map<string, ExerciseHandling> {
  return new Map(Object.entries(state).map(([id, record]) => [id, { status: record.status, callsign: record.callsign }]));
}

/**
 * The items with the urgency the operator set, where there is one. An item whose urgency stands is the same object,
 * and a list without any change is the same list.
 */
export function withOperatorUrgency(items: readonly ExerciseItem[], state: CommandHandlingState): readonly ExerciseItem[] {
  if (!items.some((item) => state[item.id]?.urgency)) return items;
  return items.map((item) => {
    const urgency = state[item.id]?.urgency;
    return urgency && urgency !== item.urgency ? { ...item, urgency } : item;
  });
}

export type CommandItemAction =
  | { type: "acknowledge" }
  | { type: "assign"; callsign: string }
  | { type: "done" }
  | { type: "drop"; reason: DropReason }
  | { type: "reopen" }
  /** One step more urgent (1) or less urgent (-1). */
  | { type: "urgency"; direction: 1 | -1 };

/** Why an action does nothing: the item is closed, is not closed, is in that state already, or the callsign is not on the roster. */
export type CommandActionRefusal = "closed" | "not_closed" | "already" | "unknown_callsign" | "at_limit";

/**
 * The state machine of an item. New → acknowledged → assigned → done or dropped; an item can be assigned without
 * being acknowledged first, assigned again to another callsign, and closed from any open state. A closed item can be
 * reopened: it returns to "assigned" when it has a callsign, otherwise to "acknowledged". The urgency moves one step
 * at a time between information, urgent and life at risk, on an open item only.
 */
export function nextHandling(
  record: CommandHandlingRecord,
  action: CommandItemAction,
  context: { roster: readonly RosterTeam[]; authorUrgency: ExerciseUrgency },
): { record: CommandHandlingRecord } | { refused: CommandActionRefusal } {
  const open = isOpenStatus(record.status);
  switch (action.type) {
    case "acknowledge":
      if (!open) return { refused: "closed" };
      if (record.status !== "new") return { refused: "already" };
      return { record: { ...record, status: "acknowledged" } };
    case "assign": {
      if (!open) return { refused: "closed" };
      const callsign = normaliseCallsign(action.callsign);
      if (!context.roster.some((team) => team.callsign === callsign)) return { refused: "unknown_callsign" };
      if (record.status === "assigned" && record.callsign === callsign) return { refused: "already" };
      return { record: { ...record, status: "assigned", callsign } };
    }
    case "done":
      if (!open) return { refused: "closed" };
      return { record: { ...record, status: "done", reason: null } };
    case "drop":
      if (!open) return { refused: "closed" };
      return { record: { ...record, status: "dropped", reason: action.reason } };
    case "reopen":
      if (open) return { refused: "not_closed" };
      return { record: { ...record, status: record.callsign ? "assigned" : "acknowledged", reason: null } };
    case "urgency": {
      if (!open) return { refused: "closed" };
      const now = EXERCISE_URGENCIES.indexOf(record.urgency ?? context.authorUrgency);
      // The list runs from the most urgent to the least, so "more urgent" is one place towards its start.
      const next = EXERCISE_URGENCIES[now - action.direction];
      if (!next) return { refused: "at_limit" };
      return { record: { ...record, urgency: next === context.authorUrgency ? null : next } };
    }
  }
}

// --- The exercise log ------------------------------------------------------------------------------------

/** The role an action belongs to: the coordinator handles items; the facilitator sets the exercise up. */
export type CommandRole = "coordinator" | "facilitator";
export const COMMAND_ROLES: readonly CommandRole[] = ["coordinator", "facilitator"];

export type CommandLogAction =
  | "acknowledged" | "assigned" | "done" | "dropped" | "reopened" | "urgency_raised" | "urgency_lowered" | "undone"
  | "brief_shown" | "brief_shared" | "brief_copied" | "brief_sms" | "situation_brief"
  | "setup_changed" | "exercise_started" | "log_exported";
export const COMMAND_LOG_ACTIONS: readonly CommandLogAction[] = [
  "acknowledged", "assigned", "done", "dropped", "reopened", "urgency_raised", "urgency_lowered", "undone",
  "brief_shown", "brief_shared", "brief_copied", "brief_sms", "situation_brief", "setup_changed", "exercise_started", "log_exported",
];

/** One row of the exercise log. `detail` is a short code (a drop reason, the two urgency levels, a language), never free text. */
export interface CommandLogEntry {
  seq: number;
  /** Whole replay hour, 0 … 264. */
  replayHour: number;
  /** The time of this device when the action was taken, as an ISO instant. It is a time of today's world, not of the replay. */
  deviceTime: string;
  role: CommandRole;
  callsign: string | null;
  action: CommandLogAction;
  /** The invented item the action is about ("EX-nn"); null for an action about the exercise as a whole. */
  itemId: string | null;
  detail: string | null;
}

/** The log keeps its newest rows; older ones fall away. */
export const COMMAND_LOG_LIMIT = 500;
const DETAIL_SHAPE = /^[a-z0-9_>|:.,-]{1,48}$/i;

export type CommandLogInput = Omit<CommandLogEntry, "seq">;

/** The log with one more row at its end. A detail that is not a short code is left out, so no free text enters the log. */
export function appendLog(log: readonly CommandLogEntry[], input: CommandLogInput): CommandLogEntry[] {
  const seq = (log[log.length - 1]?.seq ?? 0) + 1;
  const entry: CommandLogEntry = {
    seq,
    replayHour: clampCommandHour(input.replayHour),
    deviceTime: input.deviceTime,
    role: input.role,
    callsign: input.callsign,
    action: input.action,
    itemId: input.itemId,
    detail: input.detail !== null && DETAIL_SHAPE.test(input.detail) ? input.detail : null,
  };
  return [...log, entry].slice(-COMMAND_LOG_LIMIT);
}

const ACTION_OF: Readonly<Record<Exclude<CommandItemAction["type"], "urgency">, CommandLogAction>> = {
  acknowledge: "acknowledged", assign: "assigned", done: "done", drop: "dropped", reopen: "reopened",
};

/** The exercise on this device: how each item is handled, and what was done. */
export interface CommandExerciseState { handling: CommandHandlingState; log: readonly CommandLogEntry[] }
export const EMPTY_EXERCISE_STATE: CommandExerciseState = { handling: {}, log: [] };

/** How long an action can be undone (ms). */
export const COMMAND_UNDO_MS = 10_000;

/** What undoing an action needs: the record of the item before and after it, and when it was taken. */
export interface CommandUndo {
  itemId: string;
  action: CommandLogAction;
  before: CommandHandlingRecord | null;
  after: CommandHandlingRecord;
  /** The time of this device when the action was taken (ms). */
  atMs: number;
}

export interface CommandActionContext {
  /** Whole replay hour at which the action is taken. */
  replayHour: number;
  /** The time of this device (ms). */
  nowMs: number;
  roster: readonly RosterTeam[];
}

const sameRecord = (a: CommandHandlingRecord, b: CommandHandlingRecord): boolean =>
  a.status === b.status && a.callsign === b.callsign && a.urgency === b.urgency && a.reason === b.reason;

/**
 * Take an action on one invented item: the new state of the exercise, with the action in the log and what is needed to
 * undo it; or why nothing was done. An action that is refused leaves no row in the log.
 */
export function applyItemAction(
  state: CommandExerciseState,
  item: Pick<ExerciseItem, "id" | "urgency">,
  action: CommandItemAction,
  context: CommandActionContext,
): { state: CommandExerciseState; undo: CommandUndo } | { refused: CommandActionRefusal } {
  const before = state.handling[item.id] ?? null;
  const result = nextHandling(before ?? NEW_RECORD, action, { roster: context.roster, authorUrgency: item.urgency });
  if ("refused" in result) return result;
  const after = result.record;
  const logged: CommandLogAction = action.type === "urgency" ? (action.direction > 0 ? "urgency_raised" : "urgency_lowered") : ACTION_OF[action.type];
  const detail = action.type === "urgency"
    ? `${before?.urgency ?? item.urgency}>${after.urgency ?? item.urgency}`
    : action.type === "drop" ? action.reason : null;
  return {
    state: {
      handling: { ...state.handling, [item.id]: after },
      log: appendLog(state.log, { replayHour: context.replayHour, deviceTime: new Date(context.nowMs).toISOString(), role: "coordinator", callsign: after.callsign, action: logged, itemId: item.id, detail }),
    },
    undo: { itemId: item.id, action: logged, before, after, atMs: context.nowMs },
  };
}

/** True while an action can still be undone: within ten seconds of taking it. */
export function undoOpen(undo: Pick<CommandUndo, "atMs">, nowMs: number): boolean {
  return nowMs - undo.atMs >= 0 && nowMs - undo.atMs <= COMMAND_UNDO_MS;
}

/**
 * Undo an action: the item returns to the record it had before, and the log gains a row that says so (a log is never
 * rewritten). Null when the ten seconds have passed, or when the item has been handled again since.
 */
export function undoItemAction(state: CommandExerciseState, undo: CommandUndo, context: Pick<CommandActionContext, "replayHour" | "nowMs">): CommandExerciseState | null {
  if (!undoOpen(undo, context.nowMs)) return null;
  const current = state.handling[undo.itemId];
  if (!current || !sameRecord(current, undo.after)) return null;
  const handling = { ...state.handling };
  if (undo.before) handling[undo.itemId] = undo.before;
  else delete handling[undo.itemId];
  return {
    handling,
    log: appendLog(state.log, { replayHour: context.replayHour, deviceTime: new Date(context.nowMs).toISOString(), role: "coordinator", callsign: undo.after.callsign, action: "undone", itemId: undo.itemId, detail: undo.action }),
  };
}

// --- What a device has stored ----------------------------------------------------------------------------

/** Stored handling, record by record: a record that is not understood is dropped, and its item reads as new. */
export function parseHandlingState(value: unknown): CommandHandlingState {
  if (!isRecord(value)) return {};
  const out: Record<string, CommandHandlingRecord> = {};
  for (const [id, entry] of Object.entries(value)) {
    if (!/^EX-\d{2}$/.test(id) || !isRecord(entry) || !EXERCISE_STATUSES.includes(entry.status as ExerciseStatus)) continue;
    const callsign = typeof entry.callsign === "string" && callsignProblem(entry.callsign) === null ? normaliseCallsign(entry.callsign) : null;
    const status = entry.status as ExerciseStatus;
    // An item cannot be assigned to nobody.
    if (status === "assigned" && !callsign) continue;
    out[id] = {
      status,
      callsign,
      urgency: EXERCISE_URGENCIES.includes(entry.urgency as ExerciseUrgency) ? (entry.urgency as ExerciseUrgency) : null,
      reason: status === "dropped" && DROP_REASONS.includes(entry.reason as DropReason) ? (entry.reason as DropReason) : null,
    };
  }
  return out;
}

/** A stored log, row by row: a row that is not understood is dropped. */
export function parseCommandLog(value: unknown): CommandLogEntry[] {
  if (!Array.isArray(value)) return [];
  const out: CommandLogEntry[] = [];
  for (const entry of value) {
    if (!isRecord(entry) || typeof entry.seq !== "number" || !Number.isInteger(entry.seq) || entry.seq < 1) continue;
    if (typeof entry.replayHour !== "number" || !Number.isFinite(entry.replayHour)) continue;
    if (typeof entry.deviceTime !== "string" || Number.isNaN(Date.parse(entry.deviceTime))) continue;
    if (!COMMAND_ROLES.includes(entry.role as CommandRole) || !COMMAND_LOG_ACTIONS.includes(entry.action as CommandLogAction)) continue;
    out.push({
      seq: entry.seq,
      replayHour: clampCommandHour(entry.replayHour),
      deviceTime: new Date(Date.parse(entry.deviceTime)).toISOString(),
      role: entry.role as CommandRole,
      callsign: typeof entry.callsign === "string" && callsignProblem(entry.callsign) === null ? normaliseCallsign(entry.callsign) : null,
      action: entry.action as CommandLogAction,
      itemId: typeof entry.itemId === "string" && /^EX-\d{2}$/.test(entry.itemId) ? entry.itemId : null,
      detail: typeof entry.detail === "string" && DETAIL_SHAPE.test(entry.detail) ? entry.detail : null,
    });
  }
  return out.sort((a, b) => a.seq - b.seq).slice(-COMMAND_LOG_LIMIT);
}

// --- Export ----------------------------------------------------------------------------------------------

export const COMMAND_LOG_FILE_NAME = "floodguard-command-exercise-log-simulated.csv";
/** The last column of the export: true on every row, because the log holds exercise actions only. */
export const COMMAND_LOG_SIMULATED_COLUMN = "simulated";
export const COMMAND_LOG_COLUMNS = ["seq", "replay_hour", "replay_time_ict", "device_time_utc", "role", "callsign", "action", "item_id", "detail", COMMAND_LOG_SIMULATED_COLUMN] as const;

/** "2024-09-12 12:00": the local date and hour (ICT) of a replay hour. */
export function replayTimeIct(hour: number): string {
  return new Date(TIMELINE_EPOCH_MS + clampCommandHour(hour) * 3_600_000 + 7 * 3_600_000).toISOString().slice(0, 16).replace("T", " ");
}

/** One CSV field: quoted when it holds a comma, a quote or a line break, and never read as a formula by a spreadsheet. */
function csvField(value: string | number | null): string {
  if (value === null) return "";
  const text = String(value);
  const safe = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return /[",\r\n]/.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

/** The log as a CSV file: a header row, then one row per action in the order they were taken. */
export function commandLogCsv(log: readonly CommandLogEntry[]): string {
  const rows = log.map((entry) => [
    entry.seq, entry.replayHour, replayTimeIct(entry.replayHour), entry.deviceTime, entry.role, entry.callsign, entry.action, entry.itemId, entry.detail, "true",
  ].map(csvField).join(","));
  return `${[COMMAND_LOG_COLUMNS.join(","), ...rows].join("\r\n")}\r\n`;
}
