/**
 * Offline copies of the evidence library's study areas.
 *
 * The blocking service-worker installation holds the library's catalogue only. A study area (its package file or
 * files, its terrain preview and the shared report) is saved when the reader asks, by the same kind of request the
 * Mae Sai replay uses for its own data: the page posts a message to the worker, the worker stores each file only when
 * its SHA-256 matches the build's list, and answers with what is saved. The database archives a package offers for
 * download are never part of a saved copy.
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

const WORKER_TIMEOUT_MS = 10_000;
/** How long the save control waits for a first installation (about 10 MB) before it gives up for this page view. */
export const WORKER_INSTALL_WAIT_MS = 300_000;

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

function ask(worker: ServiceWorker, message: Record<string, unknown>, answerType: string, timeoutMs: number): Promise<Record<string, unknown> | null> {
  return new Promise((resolve) => {
    const channel = new MessageChannel();
    const timer = timeoutMs > 0 ? window.setTimeout(() => { channel.port1.close(); resolve(null); }, timeoutMs) : null;
    channel.port1.onmessage = (event: MessageEvent<Record<string, unknown> | null>) => {
      if (timer !== null) window.clearTimeout(timer);
      channel.port1.close();
      resolve(event.data && event.data.type === answerType ? event.data : null);
    };
    worker.postMessage(message, [channel.port2]);
  });
}

/**
 * The saved state of every study area; null where no worker answers. Reads only. `waitMs` is how long to wait for a
 * worker that is still installing: short before a package request, long for the save control.
 */
export async function readEvidenceAreas(waitMs = WORKER_TIMEOUT_MS): Promise<EvidenceAreaStatus[] | null> {
  const worker = await activeWorker(waitMs);
  if (!worker) return null;
  const answer = await ask(worker, { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" }, "FLOODGUARD_EVIDENCE_AREAS_STATUS", WORKER_TIMEOUT_MS);
  if (!answer || !Array.isArray(answer.areas)) return null;
  const areas = answer.areas.map(parseEvidenceAreaStatus);
  return areas.every((area): area is EvidenceAreaStatus => area !== null) ? areas : null;
}

async function changeEvidenceArea(type: "FLOODGUARD_SAVE_EVIDENCE_AREA" | "FLOODGUARD_REMOVE_EVIDENCE_AREA", aoiId: string): Promise<EvidenceAreaStatus | null> {
  const worker = await activeWorker(WORKER_TIMEOUT_MS);
  if (!worker) return null;
  // No timeout: a study area is tens of megabytes and the worker answers when the last file is checked.
  const answer = await ask(worker, { type, aoi_id: aoiId }, "FLOODGUARD_EVIDENCE_AREA_STATUS", 0);
  const status = parseEvidenceAreaStatus(answer);
  return status && status.aoiId === aoiId ? status : null;
}

/** Ask the worker to save one study area; resolves with what is saved afterwards (null where no worker answers). */
export function saveEvidenceArea(aoiId: string): Promise<EvidenceAreaStatus | null> {
  return changeEvidenceArea("FLOODGUARD_SAVE_EVIDENCE_AREA", aoiId);
}

/** Ask the worker to remove one saved study area. */
export function removeEvidenceArea(aoiId: string): Promise<EvidenceAreaStatus | null> {
  return changeEvidenceArea("FLOODGUARD_REMOVE_EVIDENCE_AREA", aoiId);
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
