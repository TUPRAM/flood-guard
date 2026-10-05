/**
 * The loaders of the Command exercise replay that decide what may reach the page: the file of invented exercise items
 * (shown only when its parser accepts it) and the two optional planning overlays (used only when the strict reader
 * accepts them). `fetch` is stubbed with the files of this repo, so the tests need no browser and no network.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import fixture from "./__fixtures__/planning-assessment-overlay.fixture.json";
import { loadCommandExercise, loadCommandOverlays } from "./flood-timeline-command-data";
import { EXERCISE_FILE_URL } from "./flood-timeline-command-incidents";
import { COMMAND_OVERLAY_HREFS, NO_COMMAND_OVERLAYS } from "./flood-timeline-command-table";

const publicRoot = resolve(import.meta.dirname, "../../public");
const exerciseFile = () => JSON.parse(readFileSync(resolve(publicRoot, EXERCISE_FILE_URL.replace(/^\//, "")), "utf8")) as { items: Record<string, unknown>[] } & Record<string, unknown>;
const signal = new AbortController().signal;

/** A `fetch` that serves the given bodies by address; an address it does not know is a 404. */
function serve(files: Record<string, unknown>): string[] {
  const asked: string[] = [];
  vi.stubGlobal("fetch", async (href: string) => {
    asked.push(href);
    if (!(href in files)) return { ok: false, status: 404, json: async () => ({}) };
    const body = files[href];
    return { ok: true, status: 200, json: async () => { if (body instanceof Error) throw body; return body; } };
  });
  return asked;
}

afterEach(() => vi.unstubAllGlobals());

describe("Loading the file of invented exercise items", () => {
  it("returns the parsed file of the repo, with its 14 items", async () => {
    const asked = serve({ [EXERCISE_FILE_URL]: exerciseFile() });
    const file = await loadCommandExercise(signal);
    expect(asked).toEqual([EXERCISE_FILE_URL]);
    expect(file?.simulated).toBe(true);
    expect(file?.items).toHaveLength(14);
    expect(file?.items.every((item) => /^EX-\d{2}$/.test(item.id))).toBe(true);
  });

  it("shows no item at all when the parser refuses the file", async () => {
    // An item without the "EX-" id: a reader could take it for a real report.
    const noTag = exerciseFile();
    noTag.items[0].id = "R-01";
    serve({ [EXERCISE_FILE_URL]: noTag });
    expect(await loadCommandExercise(signal)).toBeNull();
    // A text shaped like a phone number.
    const phone = exerciseFile();
    phone.items[2].text = { en: "Call 081-234-5678 for the boat.", th: "โทร 081-234-5678 เพื่อเรียกเรือ" };
    serve({ [EXERCISE_FILE_URL]: phone });
    expect(await loadCommandExercise(signal)).toBeNull();
    // A file that is not marked as simulated.
    const real = exerciseFile();
    real.simulated = false;
    serve({ [EXERCISE_FILE_URL]: real });
    expect(await loadCommandExercise(signal)).toBeNull();
  });

  it("shows no item when the file is missing or is not JSON", async () => {
    serve({});
    expect(await loadCommandExercise(signal)).toBeNull();
    serve({ [EXERCISE_FILE_URL]: new SyntaxError("Unexpected token") });
    expect(await loadCommandExercise(signal)).toBeNull();
  });
});

describe("Loading the planning overlays of the table", () => {
  it("keeps the empty state when neither file exists", async () => {
    const asked = serve({});
    expect(await loadCommandOverlays(signal)).toEqual(NO_COMMAND_OVERLAYS);
    expect([...asked].sort()).toEqual([COMMAND_OVERLAY_HREFS.O1, COMMAND_OVERLAY_HREFS.SE1].sort());
  });

  it("never puts the E11 fixture on the page, although the parser accepts it", async () => {
    // The fixture is a valid overlay of invented units: the reader of the page refuses it (a fixture, not a public
    // portfolio case), so serving it at the address of a case still leaves the table empty.
    serve({ [COMMAND_OVERLAY_HREFS.O1]: fixture, [COMMAND_OVERLAY_HREFS.SE1]: fixture });
    expect(await loadCommandOverlays(signal)).toEqual({ O1: null, SE1: null });
  });

  it("keeps the empty state for a file the parser refuses or that is not JSON", async () => {
    serve({ [COMMAND_OVERLAY_HREFS.O1]: { schema: "something else" }, [COMMAND_OVERLAY_HREFS.SE1]: new SyntaxError("Unexpected end of JSON input") });
    expect(await loadCommandOverlays(signal)).toEqual({ O1: null, SE1: null });
  });
});
