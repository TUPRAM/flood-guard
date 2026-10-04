/**
 * Offline copies of the evidence library's study areas.
 *
 * The blocking service-worker installation holds the library's catalogue only. A study area (its package file or
 * files, its terrain preview and the shared report) is saved when a reader opens it while connected, as the Mae Sai
 * replay saves its own data once it has rendered. An area larger than `EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES` is saved
 * only when the reader asks with its save button. Either way the page posts a message to the worker, the worker
 * stores each file only when its SHA-256 matches the build's list, and answers with what is saved. The database
 * archives a package offers for download are never part of a saved copy.
 *
 * This module holds no address of the evidence library, so it is safe to import anywhere.
 */

export type EvidenceAreaState = "saved" | "partial" | "none";

/** What the worker holds of one study area. `failed` counts files of the last save that did not pass. */
export interface EvidenceAreaStatus {
  aoiId: string;
  state: EvidenceAreaState;
  cached: number;
  failed: number;
  total: number;
  bytes: number;
}

/**
 * A study area up to this size (20 MB) is saved when a reader opens it while connected. A larger one is tens of
 * megabytes beyond the page the reader asked for, so it is saved only on request.
 */
export const EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES = 20_000_000;

/** Why a study area's package is not shown. */
export type EvidencePackageFailureKind = "offline_not_saved" | "unreachable" | "invalid";
export interface EvidencePackageFailure {
  kind: EvidencePackageFailureKind;
  message: string;
}

/** The package was not requested, or could not be reached, and no saved copy of the area answers for it. */
export class EvidencePackageUnavailableError extends Error {
  readonly kind: "offline_not_saved" | "unreachable";
  constructor(kind: "offline_not_saved" | "unreachable") {
    super(kind === "offline_not_saved" ? "Offline, and this study area is not saved on this device." : "The study area's data could not be reached, and it is not saved on this device.");
    this.name = "EvidencePackageUnavailableError";
    this.kind = kind;
  }
}

/** Sort a package failure for display: not saved while offline, unreachable, or a file that failed its checks. */
export function evidencePackageFailure(error: unknown): EvidencePackageFailure {
  if (error instanceof EvidencePackageUnavailableError) return { kind: error.kind, message: error.message };
  return { kind: "invalid", message: error instanceof Error ? error.message : "Package unavailable" };
}

const STATES: readonly EvidenceAreaState[] = ["saved", "partial", "none"];
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

/** One area record of a worker answer, or null when it is malformed. */
export function parseEvidenceAreaStatus(value: unknown): EvidenceAreaStatus | null {
  if (value === null || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.aoi_id !== "string" || record.aoi_id.length === 0 || !STATES.includes(record.state as EvidenceAreaState)
    || !count(record.cached) || !count(record.total) || !count(record.bytes) || record.cached > record.total) return null;
  const failed = count(record.failed) ? record.failed : 0;
  // "saved" is only ever every listed file, and an area without files is never saved.
  if (record.state === "saved" && (record.total === 0 || record.cached !== record.total)) return null;
  return { aoiId: record.aoi_id, state: record.state as EvidenceAreaState, cached: record.cached, failed, total: record.total, bytes: record.bytes };
}

/** True without a connection. Only a definite "offline" counts: an unknown state is treated as connected. */
export function deviceOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

/** True when the reader's browser asks sites to use less data. Nothing is then saved without a request. */
function dataSaverOn(): boolean {
  return typeof navigator !== "undefined" && (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData === true;
}

const WORKER_TIMEOUT_MS = 10_000;
/** How long the save control waits for a first installation (about 10 MB) before it gives up for this page view. */
export const WORKER_INSTALL_WAIT_MS = 300_000;
/** While a save or a removal runs, the page asks the worker this often whether it is still working on it. */
export const WORK_CHECK_INTERVAL_MS = 4_000;
/** This many checks in a row without the work (or without an answer) and it is reported as interrupted. */
const WORK_CHECK_MISSES = 2;

/**
 * The active service worker, or null where none runs (development, unsupported browsers) or none becomes active
 * within `waitMs` (a first visit whose installation is still downloading).
 */
async function activeWorker(waitMs: number): Promise<ServiceWorker | null> {
  if (process.env.NODE_ENV !== "production" || typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
  if (navigator.serviceWorker.controller) return navigator.serviceWorker.controller;
  const ready = navigator.serviceWorker.ready.then((registration) => registration.active).catch(() => null);
  const timeout = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), waitMs));
  return Promise.race([ready, timeout]);
}

/** One question to the worker. `close` gives up on an answer that will not come (the worker was stopped). */
function ask(worker: ServiceWorker, message: Record<string, unknown>, answerType: string, timeoutMs: number): { answer: Promise<Record<string, unknown> | null>; close: () => void } {
  const channel = new MessageChannel();
  let timer: number | null = null;
  const answer = new Promise<Record<string, unknown> | null>((resolve) => {
    if (timeoutMs > 0) timer = window.setTimeout(() => { channel.port1.close(); resolve(null); }, timeoutMs);
    channel.port1.onmessage = (event: MessageEvent<Record<string, unknown> | null>) => {
      if (timer !== null) window.clearTimeout(timer);
      channel.port1.close();
      resolve(event.data && event.data.type === answerType ? event.data : null);
    };
    worker.postMessage(message, [channel.port2]);
  });
  return { answer, close: () => { if (timer !== null) window.clearTimeout(timer); channel.port1.close(); } };
}

/**
 * The worker's status answer: every study area's saved state and, from a worker that reports it, the areas it is
 * still saving or removing (`working`; null from a worker of an earlier build, which cannot say).
 */
async function readEvidenceStatus(waitMs: number): Promise<{ areas: EvidenceAreaStatus[]; working: string[] | null } | null> {
  const worker = await activeWorker(waitMs);
  if (!worker) return null;
  const answer = await ask(worker, { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" }, "FLOODGUARD_EVIDENCE_AREAS_STATUS", WORKER_TIMEOUT_MS).answer;
  if (!answer || !Array.isArray(answer.areas)) return null;
  const areas = answer.areas.map(parseEvidenceAreaStatus);
  if (!areas.every((area): area is EvidenceAreaStatus => area !== null)) return null;
  const working = Array.isArray(answer.working) ? answer.working.filter((id): id is string => typeof id === "string") : null;
  return { areas, working };
}

/**
 * The saved state of every study area; null where no worker answers. Reads only. `waitMs` is how long to wait for a
 * worker that is still installing: short before a package request, long for the save control.
 */
export async function readEvidenceAreas(waitMs = WORKER_TIMEOUT_MS): Promise<EvidenceAreaStatus[] | null> {
  return (await readEvidenceStatus(waitMs))?.areas ?? null;
}

/** The end of a save or a removal. */
export interface EvidenceAreaChange {
  /** What is saved of the area afterwards; null where no worker answers. */
  status: EvidenceAreaStatus | null;
  /** The worker stopped before it answered, so the save or the removal did not finish. */
  interrupted: boolean;
}

/**
 * Watch a save or a removal the worker has not answered yet. The worker answers a status request at once and names
 * the areas it is still working on, so a slow save (tens of megabytes on a slow link) is told from a stopped worker:
 * `interrupted` resolves, with the area's state as last read, when the area is missing from that list or no answer
 * comes on `WORK_CHECK_MISSES` checks in a row. It never resolves for a save the worker is still running.
 */
function watchEvidenceAreaWork(aoiId: string): { interrupted: Promise<EvidenceAreaStatus | null>; stop: () => void } {
  let stopped = false;
  let timer: number | null = null;
  const interrupted = new Promise<EvidenceAreaStatus | null>((resolve) => {
    let misses = 0;
    const check = async () => {
      timer = null;
      if (stopped) return;
      const status = await readEvidenceStatus(WORKER_TIMEOUT_MS).catch(() => null);
      if (stopped) return;
      // A worker of an earlier build cannot say what it is working on: the page keeps waiting, as it did before.
      misses = status && (status.working === null || status.working.includes(aoiId)) ? 0 : misses + 1;
      if (misses >= WORK_CHECK_MISSES) {
        resolve(status?.areas.find((area) => area.aoiId === aoiId) ?? null);
        return;
      }
      timer = window.setTimeout(check, WORK_CHECK_INTERVAL_MS);
    };
    timer = window.setTimeout(check, WORK_CHECK_INTERVAL_MS);
  });
  return { interrupted, stop: () => { stopped = true; if (timer !== null) window.clearTimeout(timer); } };
}

async function changeEvidenceArea(type: "FLOODGUARD_SAVE_EVIDENCE_AREA" | "FLOODGUARD_REMOVE_EVIDENCE_AREA", aoiId: string): Promise<EvidenceAreaChange> {
  const worker = await activeWorker(WORKER_TIMEOUT_MS);
  if (!worker) return { status: null, interrupted: false };
  // No timeout: a study area is tens of megabytes and the worker answers when the last file is checked. Meanwhile
  // the worker is asked whether it is still working on it.
  const request = ask(worker, { type, aoi_id: aoiId }, "FLOODGUARD_EVIDENCE_AREA_STATUS", 0);
  const watch = watchEvidenceAreaWork(aoiId);
  const end = await Promise.race([
    request.answer.then((answer) => ({ answer, stopped: false as const })),
    watch.interrupted.then((status) => ({ status, stopped: true as const })),
  ]);
  watch.stop();
  if (end.stopped) {
    request.close();
    return { status: end.status, interrupted: true };
  }
  const status = parseEvidenceAreaStatus(end.answer);
  return { status: status && status.aoiId === aoiId ? status : null, interrupted: false };
}

export type EvidenceAreaWork = "saving" | "removing";

/** What this page view knows about saves and removals, for the save control. */
export interface EvidenceActivity {
  /** Areas with a save or a removal under way. */
  busy: Readonly<Record<string, EvidenceAreaWork>>;
  /** Files of an area's last save that did not pass their check or could not be downloaded. */
  failed: Readonly<Record<string, number>>;
  /** Areas whose last save or removal was interrupted (the worker stopped before it answered). */
  interrupted: Readonly<Record<string, EvidenceAreaWork>>;
}

const NO_ACTIVITY: EvidenceActivity = { busy: {}, failed: {}, interrupted: {} };
let activity: EvidenceActivity = NO_ACTIVITY;
const activityListeners = new Set<() => void>();
const running = new Map<string, { work: EvidenceAreaWork; promise: Promise<EvidenceAreaChange> }>();

const without = <Value>(record: Readonly<Record<string, Value>>, key: string): Record<string, Value> => {
  const next = { ...record };
  delete next[key];
  return next;
};

function publishActivity(next: EvidenceActivity) {
  activity = next;
  for (const listener of [...activityListeners]) listener();
}

/** The saves and removals of this page view (a stable object until one starts or ends). */
export function evidenceActivity(): EvidenceActivity {
  return activity;
}

/** Be told when a save or a removal starts or ends, whoever started it (the reader, or opening the area). */
export function subscribeEvidenceActivity(listener: () => void): () => void {
  activityListeners.add(listener);
  return () => { activityListeners.delete(listener); };
}

/** Run one save or removal: the same request twice on a page is one request, and the control hears of it. */
function runEvidenceAreaWork(work: EvidenceAreaWork, aoiId: string): Promise<EvidenceAreaChange> {
  const current = running.get(aoiId);
  if (current?.work === work) return current.promise;
  const promise: Promise<EvidenceAreaChange> = (current ? current.promise : Promise.resolve(null))
    .then(() => {
      publishActivity({ busy: { ...activity.busy, [aoiId]: work }, failed: without(activity.failed, aoiId), interrupted: without(activity.interrupted, aoiId) });
      return changeEvidenceArea(work === "saving" ? "FLOODGUARD_SAVE_EVIDENCE_AREA" : "FLOODGUARD_REMOVE_EVIDENCE_AREA", aoiId);
    })
    .catch((): EvidenceAreaChange => ({ status: null, interrupted: false }))
    .then((change) => {
      const last = running.get(aoiId)?.promise === promise;
      if (last) running.delete(aoiId);
      const failed = work === "saving" ? change.status?.failed ?? 0 : 0;
      publishActivity({
        busy: last ? without(activity.busy, aoiId) : activity.busy,
        failed: failed > 0 ? { ...activity.failed, [aoiId]: failed } : without(activity.failed, aoiId),
        interrupted: change.interrupted ? { ...activity.interrupted, [aoiId]: work } : without(activity.interrupted, aoiId),
      });
      return change;
    });
  running.set(aoiId, { work, promise });
  return promise;
}

// A reader who removes a saved area has said no to keeping it: it is not saved again on open until they ask.
const NOT_ON_OPEN_KEY = "floodguard:study-areas:not-saved-on-open:v1";

function areasNotSavedOnOpen(): string[] {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(NOT_ON_OPEN_KEY) ?? "[]");
    return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function setNotSavedOnOpen(aoiId: string, declined: boolean) {
  try {
    const others = areasNotSavedOnOpen().filter((id) => id !== aoiId);
    window.localStorage.setItem(NOT_ON_OPEN_KEY, JSON.stringify(declined ? [...others, aoiId] : others));
  } catch {
    // Storage may be unavailable; the choice then lasts for this page view only.
  }
}

/** The reader asks to save one study area ("Save this area for offline use"), whatever its size. */
export function saveEvidenceArea(aoiId: string): Promise<EvidenceAreaChange> {
  setNotSavedOnOpen(aoiId, false);
  return runEvidenceAreaWork("saving", aoiId);
}

/** The reader asks to remove one saved study area. It is then not saved again on open until the reader asks. */
export function removeEvidenceArea(aoiId: string): Promise<EvidenceAreaChange> {
  setNotSavedOnOpen(aoiId, true);
  return runEvidenceAreaWork("removing", aoiId);
}

const openedThisView = new Set<string>();

/**
 * A page has shown a study area's verified package while connected: keep the area for offline use, as the Mae Sai
 * replay keeps its data once it has rendered. Asked once for each area in a page view. Nothing is saved for an area
 * larger than `EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES`, for one the reader removed, when the browser asks to use less
 * data, or without a connection; the save button stays for those. Resolves with null when nothing was asked.
 */
export async function saveEvidenceAreaOnOpen(aoiId: string): Promise<EvidenceAreaChange | null> {
  if (openedThisView.has(aoiId) || deviceOffline() || dataSaverOn() || typeof window === "undefined" || areasNotSavedOnOpen().includes(aoiId)) return null;
  openedThisView.add(aoiId);
  // On a first visit the worker may still be installing: the area is saved once it is active, if the page is still open.
  const area = (await readEvidenceAreas(WORKER_INSTALL_WAIT_MS))?.find((item) => item.aoiId === aoiId);
  if (!area || area.total === 0 || area.state === "saved" || area.bytes > EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES || deviceOffline()) return null;
  return runEvidenceAreaWork("saving", aoiId);
}

/**
 * Before a package is requested without a connection: refuse when the worker says the area is not saved, so the page
 * can say so plainly instead of showing a failed download. Where no worker answers, the request goes ahead.
 */
export async function assertEvidenceAreaReachable(aoiId: string): Promise<void> {
  if (!deviceOffline()) return;
  const areas = await readEvidenceAreas();
  if (areas && areas.find((area) => area.aoiId === aoiId)?.state !== "saved") throw new EvidencePackageUnavailableError("offline_not_saved");
}

/** Size in decimal megabytes for a label, e.g. "9.3 MB". */
export function megabyteLabel(bytes: number): string {
  const megabytes = bytes / 1e6;
  return `${megabytes >= 10 ? megabytes.toFixed(0) : megabytes.toFixed(1)} MB`;
}
