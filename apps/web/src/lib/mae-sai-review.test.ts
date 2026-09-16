import { describe, expect, it } from "vitest";

import { maeSaiCase } from "./mae-sai-case";
import { exportMaeSaiReview, loadMaeSaiReviews, MAE_SAI_REVIEW_STORAGE_KEY, saveMaeSaiReview, type MaeSaiReviewInput } from "./mae-sai-review";

function memoryStorage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
}

const input: MaeSaiReviewInput = {
  areaId: "TH570903",
  scenarioId: "close_road",
  decision: "Request a road-condition check before selecting a continuity option.",
  reasoning: "The assumed connection outage changes modelled access, but passability has not been measured.",
  verificationNeed: "Confirm the named road connection and facility operating role.",
  owner: "Planning team",
  role: "Exercise participant",
  status: "reviewed_for_exercise",
};

describe("Mae Sai local decision records", () => {
  it("preserves previous snapshots when the same scenario is reviewed again", () => {
    const storage = memoryStorage();
    const first = saveMaeSaiReview(input, storage).record;
    const second = saveMaeSaiReview({ ...input, reasoning: "Revised reasoning after discussing the uncertainty." }, storage).record;
    const loaded = loadMaeSaiReviews(storage);
    expect(loaded.warning).toBeUndefined();
    expect(loaded.records.map((item) => item.id)).toEqual([second.id, first.id]);
    expect(loaded.records[1].reasoning).toBe(input.reasoning);
    expect(first.packageSha256).toBe(maeSaiCase.meta.package_sha256);
    expect(first.officialWarning).toBe(false);
  });

  it("does not overwrite unreadable or different-version history", () => {
    const storage = memoryStorage();
    storage.setItem(MAE_SAI_REVIEW_STORAGE_KEY, "corrupt bytes");
    expect(loadMaeSaiReviews(storage).warning).toBeTruthy();
    expect(() => saveMaeSaiReview(input, storage)).toThrow(/not been overwritten/);
    expect(storage.getItem(MAE_SAI_REVIEW_STORAGE_KEY)).toBe("corrupt bytes");
    const other = memoryStorage();
    const record = saveMaeSaiReview(input, other).record;
    const raw = JSON.stringify({ schema: "floodguard.mae-sai-review.v1", records: [{ ...record, packageSha256: "0".repeat(64) }] });
    other.setItem(MAE_SAI_REVIEW_STORAGE_KEY, raw);
    expect(() => saveMaeSaiReview(input, other)).toThrow(/not been overwritten/);
    expect(other.getItem(MAE_SAI_REVIEW_STORAGE_KEY)).toBe(raw);
  });

  it("does not acknowledge storage failure as a saved review", () => {
    const storage = { getItem: () => null, setItem: () => { throw new Error("Quota exceeded"); } };
    expect(() => saveMaeSaiReview(input, storage)).toThrow(/could not confirm the save/);
    const discard = { getItem: () => null, setItem: () => undefined };
    expect(() => saveMaeSaiReview(input, discard)).toThrow(/could not confirm the save/);
  });

  it("rejects unknown scenarios, empty reasoning and unsupported approval status", () => {
    const storage = memoryStorage();
    expect(() => saveMaeSaiReview({ ...input, scenarioId: "invented" }, storage)).toThrow(/Select a scenario/);
    expect(() => saveMaeSaiReview({ ...input, areaId: "invented" }, storage)).toThrow(/Select a reporting area/);
    expect(() => saveMaeSaiReview({ ...input, reasoning: " " }, storage)).toThrow(/Decision reasoning/);
    expect(() => saveMaeSaiReview({ ...input, status: "agency_approved" as MaeSaiReviewInput["status"] }, storage)).toThrow(/Review status/);
    expect(loadMaeSaiReviews(storage).records).toEqual([]);
  });

  it("exports saved scenario results and provenance without recalculating FPPS", () => {
    const record = saveMaeSaiReview(input, memoryStorage()).record;
    const brief = JSON.parse(exportMaeSaiReview(record, "json"));
    expect(brief.evidence_package).toEqual(maeSaiCase);
    expect(brief.selected_scenario).toEqual(maeSaiCase.scenarios.find((item) => item.scenario_id === input.scenarioId));
    expect(brief.operational_status).toBe("non_operational");
    expect(brief.official_warning).toBe(false);
    const markdown = exportMaeSaiReview(record, "markdown");
    expect(markdown).toContain(record.packageSha256);
    expect(markdown).toContain("FPPS recalculated: false");
    expect(markdown).toContain("no authenticated staff approval or server receipt");
    expect(markdown).toContain(input.verificationNeed);
  });

  it("cannot export a record under another evidence revision", () => {
    const record = saveMaeSaiReview(input, memoryStorage()).record;
    expect(() => exportMaeSaiReview({ ...record, caseVersion: "other" }, "json")).toThrow(/does not match/);
  });
});
