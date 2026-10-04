import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { evidenceFixtures } from "./evidence-library.fixtures";
import { fetchEvidencePackage } from "./evidence-library";
import {
  assertEvidenceAreaReachable, deviceOffline, evidencePackageFailure, EvidencePackageUnavailableError, megabyteLabel,
  parseEvidenceAreaStatus, readEvidenceAreas, saveEvidenceArea,
} from "./evidence-offline";

const app = resolve(import.meta.dirname, "../..");

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

/** A stand-in for the browser's worker channel: `answer` is what the worker posts back for one message. */
function stubWorker(answer: (message: Record<string, unknown>) => unknown, online: boolean) {
  const posted: Record<string, unknown>[] = [];
  class Channel {
    port1: { onmessage: ((event: { data: unknown }) => void) | null; close: () => void } = { onmessage: null, close: () => undefined };
    port2 = {};
  }
  const channels: Channel[] = [];
  vi.stubGlobal("MessageChannel", class extends Channel { constructor() { super(); channels.push(this); } });
  vi.stubGlobal("window", { setTimeout: () => 1, clearTimeout: () => undefined });
  const controller = {
    postMessage: (message: Record<string, unknown>) => {
      posted.push(message);
      const channel = channels.at(-1)!;
      queueMicrotask(() => channel.port1.onmessage?.({ data: answer(message) }));
    },
  };
  vi.stubGlobal("navigator", { onLine: online, serviceWorker: { controller } });
  vi.stubEnv("NODE_ENV", "production");
  return posted;
}

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
    expect(await saveEvidenceArea("aoi-02")).toEqual({ aoiId: "aoi-02", state: "partial", cached: 2, failed: 1, total: 3, bytes: 20 });
    expect(posted).toEqual([{ type: "FLOODGUARD_EVIDENCE_AREAS_STATUS_REQUEST" }, { type: "FLOODGUARD_SAVE_EVIDENCE_AREA", aoi_id: "aoi-02" }]);
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
