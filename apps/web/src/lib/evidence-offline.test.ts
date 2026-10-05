import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { evidenceFixtures } from "./evidence-library.fixtures";
import { fetchEvidencePackage } from "./evidence-library";
import {
  assertEvidenceAreaReachable, deviceOffline, evidenceActivity, evidencePackageFailure, EvidencePackageUnavailableError,
  EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES, megabyteLabel, parseEvidenceAreaStatus, readEvidenceAreas, removeEvidenceArea,
  saveEvidenceArea, saveEvidenceAreaOnOpen, subscribeEvidenceActivity, WORK_CHECK_INTERVAL_MS,
} from "./evidence-offline";

const app = resolve(import.meta.dirname, "../..");

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

/**
 * A stand-in for the browser's worker channel: `answer` is what the worker posts back for one message. A worker that
 * was stopped posts nothing: `answer` then returns undefined. The page's timers are the test's (fake) timers, and
 * its storage is a map.
 */
function stubWorker(answer: (message: Record<string, unknown>) => unknown, online: boolean, device: Record<string, unknown> = {}) {
  const posted: Record<string, unknown>[] = [];
  class Channel {
    port1: { onmessage: ((event: { data: unknown }) => void) | null; close: () => void } = { onmessage: null, close: () => undefined };
    port2 = {};
  }
  const channels: Channel[] = [];
  vi.stubGlobal("MessageChannel", class extends Channel { constructor() { super(); channels.push(this); } });
  const stored = new Map<string, string>();
  vi.stubGlobal("window", {
    setTimeout: (task: () => void, delay: number) => setTimeout(task, delay),
    clearTimeout: (timer: ReturnType<typeof setTimeout>) => clearTimeout(timer),
    localStorage: { getItem: (key: string) => stored.get(key) ?? null, setItem: (key: string, value: string) => { stored.set(key, value); } },
  });
  const controller = {
    postMessage: (message: Record<string, unknown>) => {
      posted.push(message);
      const channel = channels.at(-1)!;
      queueMicrotask(() => {
        const data = answer(message);
        if (data !== undefined) channel.port1.onmessage?.({ data });
      });
    },
  };
  vi.stubGlobal("navigator", { onLine: online, serviceWorker: { controller }, ...device });
  vi.stubEnv("NODE_ENV", "production");
  return posted;
}

const STATUS_REQUEST = "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST";
const areaAnswer = (aoiId: string, state: string, cached: number, bytes = 9_300_000, failed = 0) => ({ aoi_id: aoiId, state, cached, failed, total: 3, bytes });
const statusAnswer = (areas: unknown[], working: string[] = []) => ({ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas, working });
const saved = (aoiId: string, bytes = 9_300_000) => ({ type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaAnswer(aoiId, "saved", 3, bytes) });

describe("offline copies of study areas", () => {
  it("accepts only well-formed worker answers", () => {
    const saved = { aoi_id: "aoi-01", state: "saved", cached: 3, failed: 0, total: 3, bytes: 9_300_000 };
    expect(parseEvidenceAreaStatus(saved)).toEqual({ aoiId: "aoi-01", state: "saved", cached: 3, failed: 0, total: 3, bytes: 9_300_000 });
    expect(parseEvidenceAreaStatus({ ...saved, state: "partial", cached: 1, failed: 2 })?.failed).toBe(2);
    // "saved" means every listed file, and an area without files is never saved.
    expect(parseEvidenceAreaStatus({ ...saved, cached: 2 })).toBeNull();
    expect(parseEvidenceAreaStatus({ ...saved, cached: 0, total: 0 })).toBeNull();
    expect(parseEvidenceAreaStatus({ ...saved, cached: 4 })).toBeNull();
    expect(parseEvidenceAreaStatus({ ...saved, state: "ready" })).toBeNull();
    expect(parseEvidenceAreaStatus({ ...saved, aoi_id: "" })).toBeNull();
    expect(parseEvidenceAreaStatus({ ...saved, bytes: -1 })).toBeNull();
    expect(parseEvidenceAreaStatus(null)).toBeNull();
    expect(parseEvidenceAreaStatus({ aoi_id: "unknown", state: "none", cached: 0, failed: 0, total: 0, bytes: 0 })?.state).toBe("none");
  });

  it("sorts a failure into not saved while offline, unreachable, or a file that failed its checks", () => {
    expect(evidencePackageFailure(new EvidencePackageUnavailableError("offline_not_saved")).kind).toBe("offline_not_saved");
    expect(evidencePackageFailure(new EvidencePackageUnavailableError("unreachable")).kind).toBe("unreachable");
    expect(evidencePackageFailure(new Error("Evidence package checksum does not match the catalog."))).toEqual({ kind: "invalid", message: "Evidence package checksum does not match the catalog." });
    expect(evidencePackageFailure("nonsense")).toEqual({ kind: "invalid", message: "Package unavailable" });
  });

  it("labels sizes in decimal megabytes", () => {
    expect(megabyteLabel(9_278_000)).toBe("9.3 MB");
    expect(megabyteLabel(51_300_000)).toBe("51 MB");
  });

  it("treats only a definite offline state as offline, and answers null where no worker runs", async () => {
    expect(deviceOffline()).toBe(false);
    vi.stubGlobal("navigator", { onLine: false });
    expect(deviceOffline()).toBe(true);
    // Outside a production build there is no worker: nothing is asked and nothing is refused.
    expect(await readEvidenceAreas()).toBeNull();
    await expect(assertEvidenceAreaReachable("aoi-01")).resolves.toBeUndefined();
  });

  it("reads the saved state from the worker and asks it to save one area", async () => {
    const posted = stubWorker((message) => message.type === "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST"
      ? { type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas: [{ aoi_id: "aoi-01", state: "saved", cached: 3, failed: 0, total: 3, bytes: 10 }, { aoi_id: "aoi-02", state: "none", cached: 1, failed: 0, total: 3, bytes: 20 }] }
      : { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", aoi_id: message.aoi_id, state: "partial", cached: 2, failed: 1, total: 3, bytes: 20 }, true);
    expect((await readEvidenceAreas())?.map((area) => `${area.aoiId}:${area.state}`)).toEqual(["aoi-01:saved", "aoi-02:none"]);
    const heard: string[] = [];
    const stopHearing = subscribeEvidenceActivity(() => heard.push(evidenceActivity().busy["aoi-02"] ?? "idle"));
    expect(await saveEvidenceArea("aoi-02")).toEqual({ status: { aoiId: "aoi-02", state: "partial", cached: 2, failed: 1, total: 3, bytes: 20 }, interrupted: false });
    stopHearing();
    expect(posted).toEqual([{ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" }, { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "aoi-02" }]);
    // The save control hears when the save starts and when it ends, and how many files did not pass.
    expect(heard).toEqual(["saving", "idle"]);
    expect(evidenceActivity().failed["aoi-02"]).toBe(1);
    expect(evidenceActivity().interrupted["aoi-02"]).toBeUndefined();
  });

  it("saves an area the reader opens while connected, once, when it is within the size limit", async () => {
    expect(EVIDENCE_SAVE_ON_OPEN_LIMIT_BYTES).toBe(20_000_000);
    const within = "open-within";
    const posted = stubWorker((message) => message.type === STATUS_REQUEST
      ? statusAnswer([areaAnswer(within, "none", 0, 14_150_004), areaAnswer("open-large", "none", 0, 30_987_289), areaAnswer("open-saved", "saved", 3)])
      : saved(String(message.aoi_id), 14_150_004), true);
    expect((await saveEvidenceAreaOnOpen(within))?.status?.state).toBe("saved");
    expect(posted.filter((message) => message.type === "FLOODGUARD_SAVE_EVIDENCE_AREA")).toEqual([{ type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: within }]);
    // Opening it again in the same page view asks nothing more.
    expect(await saveEvidenceAreaOnOpen(within)).toBeNull();
    // An area above the limit is left for the reader's request; one that is saved already needs nothing.
    expect(await saveEvidenceAreaOnOpen("open-large")).toBeNull();
    expect(await saveEvidenceAreaOnOpen("open-saved")).toBeNull();
    expect(posted.filter((message) => message.type === "FLOODGUARD_SAVE_EVIDENCE_AREA")).toHaveLength(1);
    // The reader can still ask for the large one.
    expect((await saveEvidenceArea("open-large")).status?.state).toBe("saved");
  });

  it("does not save on open without a connection, when the browser asks to use less data, or after the reader removed the copy", async () => {
    const answer = (message: Record<string, unknown>) => message.type === STATUS_REQUEST
      ? statusAnswer([areaAnswer("open-offline", "none", 0), areaAnswer("open-saver", "none", 0), areaAnswer("open-removed", "none", 0)])
      : message.type === "FLOODGUARD_REMOVE_EVIDENCE_AREA"
        ? { type: "FLOODGUARD_EVIDENCE_AREA_STATUS", ...areaAnswer(String(message.aoi_id), "none", 0) }
        : saved(String(message.aoi_id));
    let posted = stubWorker(answer, false);
    expect(await saveEvidenceAreaOnOpen("open-offline")).toBeNull();
    expect(posted).toEqual([]);
    posted = stubWorker(answer, true, { connection: { saveData: true } });
    expect(await saveEvidenceAreaOnOpen("open-saver")).toBeNull();
    expect(posted).toEqual([]);

    // The reader removes a saved copy: it is not saved again on open, until the reader asks for it.
    posted = stubWorker(answer, true);
    await removeEvidenceArea("open-removed");
    expect(await saveEvidenceAreaOnOpen("open-removed")).toBeNull();
    expect(posted.map((message) => message.type)).toEqual(["FLOODGUARD_REMOVE_EVIDENCE_AREA"]);
    expect((await saveEvidenceArea("open-removed")).status?.state).toBe("saved");
    expect(JSON.parse(window.localStorage.getItem("floodguard:study-areas:not-saved-on-open:v1") ?? "null")).toEqual([]);
  });

  it("reports a save as interrupted when the worker was stopped, instead of waiting for ever", async () => {
    vi.useFakeTimers();
    const aoiId = "stopped-area";
    // The worker takes the save and is stopped: it never answers. Started again, it lists nothing in work.
    const posted = stubWorker((message) => message.type === STATUS_REQUEST ? statusAnswer([areaAnswer(aoiId, "partial", 1)], []) : undefined, true);
    const end: { change: Awaited<ReturnType<typeof saveEvidenceArea>> | null } = { change: null };
    void saveEvidenceArea(aoiId).then((change) => { end.change = change; });
    await vi.advanceTimersByTimeAsync(0);
    expect(evidenceActivity().busy[aoiId]).toBe("saving");
    // One check that does not find the work is not enough: its answer may be on its way.
    await vi.advanceTimersByTimeAsync(WORK_CHECK_INTERVAL_MS);
    expect(end.change).toBeNull();
    await vi.advanceTimersByTimeAsync(WORK_CHECK_INTERVAL_MS);
    expect(end.change).toEqual({ status: { aoiId, state: "partial", cached: 1, failed: 0, total: 3, bytes: 9_300_000 }, interrupted: true });
    expect(evidenceActivity().busy[aoiId]).toBeUndefined();
    expect(evidenceActivity().interrupted[aoiId]).toBe("saving");
    expect(posted.filter((message) => message.type === STATUS_REQUEST)).toHaveLength(2);
    // The next request clears the note.
    stubWorker((message) => message.type === STATUS_REQUEST ? statusAnswer([areaAnswer(aoiId, "saved", 3)]) : saved(String(message.aoi_id)), true);
    const retry = saveEvidenceArea(aoiId);
    await vi.advanceTimersByTimeAsync(0);
    expect((await retry).interrupted).toBe(false);
    expect(evidenceActivity().interrupted[aoiId]).toBeUndefined();
  });

  it("keeps waiting for a slow save while the worker says it is still working on it", async () => {
    vi.useFakeTimers();
    const aoiId = "slow-area";
    const slow: { finish: (() => void) | null } = { finish: null };
    class Channel {
      port1: { onmessage: ((event: { data: unknown }) => void) | null; close: () => void } = { onmessage: null, close: () => undefined };
      port2 = {};
    }
    stubWorker(() => undefined, true);
    const channels: Channel[] = [];
    vi.stubGlobal("MessageChannel", class extends Channel { constructor() { super(); channels.push(this); } });
    vi.stubGlobal("navigator", { onLine: true, serviceWorker: { controller: { postMessage: (message: Record<string, unknown>) => {
      const channel = channels.at(-1)!;
      if (message.type === STATUS_REQUEST) queueMicrotask(() => channel.port1.onmessage?.({ data: statusAnswer([areaAnswer(aoiId, "none", 0)], slow.finish ? [aoiId] : []) }));
      else slow.finish = () => channel.port1.onmessage?.({ data: saved(aoiId) });
    } } } });
    const end: { change: Awaited<ReturnType<typeof saveEvidenceArea>> | null } = { change: null };
    void saveEvidenceArea(aoiId).then((change) => { end.change = change; });
    // Five minutes of a slow download: every check finds the area in work, so nothing is reported.
    await vi.advanceTimersByTimeAsync(300_000);
    expect(end.change).toBeNull();
    expect(evidenceActivity().busy[aoiId]).toBe("saving");
    slow.finish?.();
    await vi.advanceTimersByTimeAsync(0);
    expect(end.change).toEqual({ status: { aoiId, state: "saved", cached: 3, failed: 0, total: 3, bytes: 9_300_000 }, interrupted: false });
  });

  it("offline, does not request the package of an area that is not saved, and requests a saved one", async () => {
    const { catalog } = evidenceFixtures();
    const reference = catalog.packages[0];
    const fetcher = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetcher);
    stubWorker(() => ({ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas: [{ aoi_id: reference.aoi_id, state: "none", cached: 0, failed: 0, total: 3, bytes: 10 }] }), false);
    await expect(fetchEvidencePackage(catalog, reference)).rejects.toMatchObject({ name: "EvidencePackageUnavailableError", kind: "offline_not_saved" });
    expect(fetcher).not.toHaveBeenCalled();
    // An incomplete copy does not open offline either.
    stubWorker(() => ({ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas: [{ aoi_id: reference.aoi_id, state: "partial", cached: 2, failed: 0, total: 3, bytes: 10 }] }), false);
    await expect(fetchEvidencePackage(catalog, reference)).rejects.toMatchObject({ kind: "offline_not_saved" });
    expect(fetcher).not.toHaveBeenCalled();
    // A saved area is requested; the worker answers it from the saved copy (here the request simply fails).
    stubWorker(() => ({ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS", areas: [{ aoi_id: reference.aoi_id, state: "saved", cached: 3, failed: 0, total: 3, bytes: 10 }] }), false);
    await expect(fetchEvidencePackage(catalog, reference)).rejects.toMatchObject({ kind: "offline_not_saved" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("asks to save a study area once its package has opened and passed its checks, and not when it failed them", async () => {
    const { catalog, evidence } = evidenceFixtures();
    const reference = catalog.packages[0];
    const body = new TextEncoder().encode(JSON.stringify(evidence));
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", body)), (byte) => byte.toString(16).padStart(2, "0")).join("");
    const posted = stubWorker((message) => message.type === STATUS_REQUEST ? statusAnswer([areaAnswer(reference.aoi_id, "none", 0)]) : saved(String(message.aoi_id)), true);
    // A package that does not match the catalogue is not shown, and the area is not saved for it.
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body)));
    await expect(fetchEvidencePackage(catalog, reference)).rejects.toThrow("checksum does not match");
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(posted).toEqual([]);
    // The package the catalogue pins opens, and the page asks the worker to keep its area.
    const pinned = { ...catalog, packages: [{ ...reference, sha256: digest }] };
    expect((await fetchEvidencePackage(pinned, pinned.packages[0])).id).toBe(evidence.id);
    await vi.waitFor(() => expect(posted.map((message) => message.type)).toEqual([STATUS_REQUEST, "FLOODGUARD_SAVE_EVIDENCE_AREA"]));
    expect(posted[1]).toEqual({ type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: reference.aoi_id });
  });

  it("online, reports a package that cannot be reached as unreachable, not as a failed check", async () => {
    const { catalog } = evidenceFixtures();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(fetchEvidencePackage(catalog, catalog.packages[0])).rejects.toMatchObject({ kind: "unreachable" });
    // A cancelled request stays a cancelled request.
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError")));
    await expect(fetchEvidencePackage(catalog, catalog.packages[0], controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("uses the message names and the cache name the service worker uses, and names no address of the library", () => {
    const worker = readFileSync(resolve(app, "public/sw.js"), "utf8");
    const client = readFileSync(resolve(app, "src/lib/evidence-offline.ts"), "utf8");
    for (const name of ["FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST", "FLOODGUARD_EVIDENCE_AREAS_STATUS", "FLOODGUARD_SAVE_EVIDENCE_AREA", "FLOODGUARD_REMOVE_EVIDENCE_AREA", "FLOODGUARD_EVIDENCE_AREA_STATUS"]) {
      expect(worker).toContain(`"${name}"`);
      expect(client).toContain(`"${name}"`);
    }
    // The worker's status names the areas it is still working on, and the page reads that list.
    expect(worker).toContain("working: [...evidenceAreaWork.keys()]");
    expect(client).toContain("answer.working");
    expect(worker).toContain("const OPTIONAL_EVIDENCE_AREAS = []; /* __OPTIONAL_EVIDENCE_AREAS__ */");
    expect(readFileSync(resolve(app, "scripts/write-offline-assets.mjs"), "utf8")).toContain('"const OPTIONAL_EVIDENCE_AREAS = []; /* __OPTIONAL_EVIDENCE_AREAS__ */"');
    // The saved areas live outside the build cache (floodguard-offline-<build>), so a new deployment keeps them.
    const cacheName = worker.match(/const EVIDENCE_AREA_CACHE = "([^"]+)";/)?.[1];
    expect(cacheName).toBe("floodguard-saved-areas-v1");
    expect(cacheName).not.toMatch(/^floodguard-offline-/);
    expect(readFileSync(resolve(app, "scripts/evidence-library-assets.mjs"), "utf8")).toContain(`export const EVIDENCE_AREA_CACHE = "${cacheName}";`);
    expect(readFileSync(resolve(app, "src/components/pwa-register.tsx"), "utf8")).toContain(`const SAVED_AREAS_CACHE = "${cacheName}";`);
    // The Public build imports nothing of the library; this module must not carry its addresses there either.
    expect(client).not.toContain("/evidence-library/");
    expect(worker).not.toContain("/evidence-library/");
  });
});
