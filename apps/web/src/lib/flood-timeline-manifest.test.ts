import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  evidenceBlocksFor,
  externalChecksByRole,
  formatGeneratedAt,
  licenceRows,
  manifestRevision,
  parseTimelineManifest,
  TIMELINE_MANIFEST_URL,
  TimelineManifestError,
  type EvidenceLane,
} from "./flood-timeline";
import { localizedText } from "./flood-timeline-copy";

const publicRoot = resolve(import.meta.dirname, "../../public");
const served = (): Record<string, unknown> => JSON.parse(readFileSync(resolve(publicRoot, TIMELINE_MANIFEST_URL.slice(1)), "utf8")) as Record<string, unknown>;
// The r3 shape, trimmed (see the fixture's own "trimmed" list). Its hrefs name files that are no longer in the tree.
const r3Fixture = JSON.parse(readFileSync(resolve(import.meta.dirname, "__fixtures__/mae-sai-timeline-r3-shape.json"), "utf8")) as {
  source: string;
  trimmed: string[];
  manifest: Record<string, unknown>;
};
const r3 = (): Record<string, unknown> => structuredClone(r3Fixture.manifest);
const ENVELOPE_KEYS = [
  "generated_at", "generated_at_basis", "git_commit", "data_version", "dataset_mode", "operational_status", "accepted_fpps",
  "accepted_action_class", "protocol_sha256", "permitted_use", "reason_blocked", "confidence_class", "confidence_basis", "source_name",
  "event_time", "lanes", "evidence_blocks", "exploratory_knowledge", "publication_eligibility", "input_sha256",
] as const;

describe("Mae Sai replay manifest reader: the served revision (r4 shape)", () => {
  const manifest = parseTimelineManifest(served());

  it("reads the evidence envelope: no score, no class, non-operational, a declared generation time", () => {
    expect(manifest.revision).toBe(manifestRevision());
    expect(manifest.schema_version).toBe(2);
    for (const key of ENVELOPE_KEYS) expect(manifest, key).toHaveProperty(key);
    expect(manifest.accepted_fpps).toBeNull();
    expect(manifest.accepted_action_class).toBeNull();
    expect(manifest.protocol_sha256).toBeNull();
    expect(manifest.protocol_sha256_reason).toBe("not_a_protocol_case");
    expect(manifest.operational_status).toBe("non_operational");
    expect(manifest.official_warning).toBe(false);
    expect(manifest.real_time).toBe(false);
    expect(manifest.can_feed_decision_layer).toBe(false);
    expect(manifest.dataset_mode).toBe("historical_reconstruction");
    expect(manifest.data_mode).toBe(manifest.dataset_mode);
    expect(manifest.confidence_class).toBe(manifest.confidence);
    expect(manifest.data_version).toBe(`${manifest.study_id}-${manifest.revision}`);
    // generated_at is a declared time with an offset, never a clock reading; the commit is found through Git.
    expect(manifest.generated_at).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$/);
    expect(manifest.generated_at_basis).toBe("declared");
    expect(manifest.git_commit).toBeNull();
    expect(manifest.git_commit_reason).toMatch(/^self_reference/);
    expect(manifest.input_sha256!.length).toBeGreaterThan(0);
    for (const input of manifest.input_sha256!) {
      expect(input.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(input.path).not.toMatch(/^[A-Za-z]:|^\/|%20|\\/);
    }
  });

  it("gives every part of the manifest a lane and a source timestamp", () => {
    const blocks = manifest.evidence_blocks!;
    expect(blocks.length).toBeGreaterThan(10);
    for (const block of blocks) {
      expect(block.lane, block.id).toBeTruthy();
      expect(block.source_timestamp, block.id).toBeTruthy();
      expect(block.evidence_tier, block.id).toBeTruthy();
      expect(block.temporal_relation, block.id).toBeTruthy();
      expect(manifest.lanes![block.lane], block.id).toBeTruthy();
    }
    const lane = (path: string): EvidenceLane[] => evidenceBlocksFor(manifest, path).map((block) => block.lane);
    // The water reconstruction, access and shelters are scenario (model) output.
    for (const path of ["hand", "days", "access", "shelters", "population"]) expect(lane(path), path).toEqual(["SCN"]);
    for (const block of blocks.filter((item) => item.lane === "SCN")) expect(block.evidence_tier).toBe("T1 scenario (model)");
    // Observations carry their own timestamps.
    expect(lane("viirs_daily")).toEqual(["OBS"]);
    expect(lane("rainfall")).toEqual(["OBS"]);
    expect(evidenceBlocksFor(manifest, "layers[s2-20240915]")[0]).toMatchObject({ lane: "OBS", source_timestamp: "2024-09-15T03:58:15Z" });
    expect(evidenceBlocksFor(manifest, "layers[s1-20240915]")[0]).toMatchObject({ lane: "OBS", source_timestamp: "2024-09-15T23:16:01Z" });
    // What was used, or known, while the model was tuned is calibration; nothing is an independent check.
    for (const path of ["s1_anchor", "external_checks[gistda-radarsat2-20240910]", "external_checks[unosat-3991]"]) expect(lane(path), path).toEqual(["CAL"]);
    expect(manifest.s1_anchor.role).toBe("calibration_informed_magnitude_check");
    expect(externalChecksByRole(manifest.external_checks!).independent).toEqual([]);
    // Product 4009 is a season envelope scenario and is not shown.
    expect(evidenceBlocksFor(manifest, "external_references[unosat-4009]")[0]).toMatchObject({ lane: "SCN-ENV", shown: false, season_window: "2024-08-01/2024-10-22" });
    expect(evidenceBlocksFor(manifest, "no_such_block")).toEqual([]);
  });

  it("lists a licence per input, with the input that is not shown last", () => {
    const rows = licenceRows(manifest);
    const licences = Object.fromEntries(rows.map((row) => [row.id, row.licence]));
    expect(licences).toMatchObject({
      "hii-rain": "CC BY-NC",
      osm: "ODbL 1.0",
      worldpop: "CC BY 4.0",
      "cod-ab": "CC BY-IGO",
      viirs: "No licence stated by the provider",
      "unosat-4009": "CC BY-SA 4.0",
    });
    expect(licences["copernicus-dem"]).toMatch(/Copernicus DEM licence/);
    expect(licences["sentinel-1"]).toMatch(/Copernicus Sentinel data terms/);
    expect(licences["sentinel-2"]).toMatch(/Copernicus Sentinel data terms/);
    expect(rows.find((row) => row.id === "viirs")!.licence_stated).toBe(false);
    expect(rows.filter((row) => !row.shown).map((row) => row.id)).toEqual(["unosat-4009"]);
    expect(rows.at(-1)).toMatchObject({ id: "unosat-4009", status: "Not yet shown; rights record pending owner confirmation." });
    // Every listed source has a licence row.
    for (const source of manifest.sources) expect(rows.some((row) => row.id === source.id), source.id).toBe(true);
    // The sources name both elevation tiles and the residents grid.
    expect(manifest.sources.find((source) => source.id === "copernicus-dem")!.name).toMatch(/N20 E099 and N20 E100/);
    expect(manifest.sources.find((source) => source.id === "worldpop")!.name).toBe(manifest.population!.source);
  });

  it("states what was used or known while the model was tuned, in step with the labels", () => {
    const items = Object.fromEntries(manifest.exploratory_knowledge!.items.map((item) => [item.id, item]));
    expect(items["gistda-radarsat2-20240910"].relation).toBe("used_for_tuning");
    expect(items["sentinel-1-20240916"].relation).toBe("used_for_tuning");
    expect(items["unosat-3991"].relation).toBe("known_during_tuning");
    // VIIRS: not used for tuning; whether it was known then is not recorded, so the field is null, never false.
    expect(items["viirs-daily"]).toMatchObject({ relation: "not_used_for_tuning", known_during_tuning: null });
    expect(items["viirs-daily"].statement).toContain("commit 129ff03");
    expect(items["unosat-4009"]).toMatchObject({ relation: "computed_after_keyframes_final", known_during_tuning: false });
    expect(manifest.s1_anchor.use).toMatch(/not an independent check/);
    expect(manifest.confidence_reason).toMatch(/tuned to one radar pass rather than checked independently/);
  });

  it("covers every dated event observation with the top-level source timestamp", () => {
    const [start, end] = manifest.source_timestamp.split("/").map((value) => Date.parse(value));
    const stamps = [
      ...manifest.observations.map((observation) => observation.utc),
      ...manifest.viirs_daily!.days.map((day) => day.nominal_local_time),
      manifest.event_time!.end,
    ].map((value) => Date.parse(value));
    expect(stamps.length).toBeGreaterThan(12);
    for (const stamp of stamps) {
      expect(stamp).toBeGreaterThanOrEqual(start);
      expect(stamp).toBeLessThanOrEqual(end);
    }
    expect(manifest.source_timestamp_note).toMatch(/VIIRS/);
    expect(manifest.source_timestamp_note).toMatch(/rain/);
  });

  it("formats the generation time in local time, in both languages", () => {
    expect(formatGeneratedAt("2026-10-01T16:10:00+07:00", "en")).toBe("1 Oct 2026, 16:10 ICT");
    expect(formatGeneratedAt("2026-10-01T09:10:00Z", "en")).toBe("1 Oct 2026, 16:10 ICT");
    expect(formatGeneratedAt("2026-10-01T16:10:00+07:00", "th")).toBe("1 ต.ค. 2569 (2026) 16:10 น.");
    expect(formatGeneratedAt(manifest.generated_at, "en")).toMatch(/^\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} ICT$/);
    expect(formatGeneratedAt(undefined, "en")).toBeNull();
    expect(formatGeneratedAt("not a date", "th")).toBeNull();
  });
});

describe("Mae Sai replay manifest reader: an r3-shaped manifest from a client's offline copy", () => {
  it("is a real r3 manifest without the evidence envelope", () => {
    expect(r3Fixture.source).toMatch(/r3\/timeline\.json/);
    expect(r3Fixture.trimmed.length).toBeGreaterThan(0);
    expect(r3Fixture.manifest.revision).toBe("r3");
    expect(r3Fixture.manifest.schema_version).toBe(1);
    for (const key of ENVELOPE_KEYS) expect(r3Fixture.manifest, key).not.toHaveProperty(key);
    expect(r3Fixture.manifest.data_mode).toBe("historical_reconstruction");
  });

  it("is read, with the defaults that revision implies filled in", () => {
    const manifest = parseTimelineManifest(r3());
    expect(manifest.revision).toBe("r3");
    expect(manifest.dataset_mode).toBe("historical_reconstruction");
    expect(manifest.data_mode).toBe("historical_reconstruction");
    expect(manifest.confidence_class).toBe("low");
    expect(manifest.operational_status).toBe("non_operational");
    expect(manifest.can_feed_decision_layer).toBe(false);
    expect(manifest.accepted_fpps).toBeNull();
    expect(manifest.accepted_action_class).toBeNull();
    // Data blocks are passed through untouched.
    expect(manifest.days).toEqual(r3Fixture.manifest.days);
    expect(manifest.stage_anchors).toEqual(r3Fixture.manifest.stage_anchors);
    expect(manifest.external_checks).toEqual(r3Fixture.manifest.external_checks);
    expect(manifest.viirs_daily).toEqual(r3Fixture.manifest.viirs_daily);
    // What r3 does not carry stays absent, and the helpers answer with nothing rather than throwing.
    expect(manifest.generated_at).toBeUndefined();
    expect(formatGeneratedAt(manifest.generated_at, "en")).toBeNull();
    expect(manifest.evidence_blocks).toBeUndefined();
    expect(evidenceBlocksFor(manifest, "access")).toEqual([]);
    expect(licenceRows(manifest)).toEqual([]);
    expect(manifest.exploratory_knowledge).toBeUndefined();
    expect(manifest.s1_anchor.role).toBeUndefined();
    // The input object is not changed.
    const input = r3();
    parseTimelineManifest(input);
    expect(input).toEqual(r3Fixture.manifest);
  });

  it("still has a Thai rendering of the r3 sentences that r4 reworded", () => {
    const manifest = parseTimelineManifest(r3());
    const sentences = [
      manifest.confidence_reason, ...manifest.assumptions, ...manifest.limitations,
      ...(manifest.external_references ?? []).flatMap((reference) => (reference.note ? [reference.note] : [])),
    ];
    expect(sentences.filter((sentence) => localizedText(sentence, "th").lang !== "th")).toEqual([]);
  });
});

describe("Mae Sai replay manifest reader: what it refuses", () => {
  const refused = (change: (manifest: Record<string, unknown>) => void, base: () => Record<string, unknown> = served): string => {
    const manifest = base();
    change(manifest);
    try {
      parseTimelineManifest(manifest);
    } catch (error) {
      expect(error).toBeInstanceOf(TimelineManifestError);
      return (error as Error).message;
    }
    return "accepted";
  };

  it("refuses a document that is not a replay manifest", () => {
    for (const value of [null, undefined, "timeline", 4, [], [served()]]) {
      expect(() => parseTimelineManifest(value)).toThrow(TimelineManifestError);
    }
    expect(refused((manifest) => { delete manifest.study_id; })).toMatch(/lacks study_id/);
    expect(refused((manifest) => { manifest.days = []; })).toMatch(/no stage anchors or no days/);
    expect(refused((manifest) => { manifest.sources = "none"; })).toMatch(/lacks the sources list/);
    expect(refused((manifest) => { manifest.hand = null; })).toMatch(/lacks hand/);
    expect(refused((manifest) => { delete manifest.source_timestamp; })).toMatch(/lacks source_timestamp/);
    expect(refused((manifest) => { delete manifest.confidence; })).toMatch(/lacks confidence/);
  });

  it("refuses an official alert, a current product, an operational status or a feed into the decision layer", () => {
    for (const base of [served, r3]) {
      expect(refused((manifest) => { manifest.official_warning = true; }, base)).toMatch(/not an official warning/);
      expect(refused((manifest) => { manifest.real_time = true; }, base)).toMatch(/historical/);
      expect(refused((manifest) => { delete manifest.official_warning; }, base)).toMatch(/not an official warning/);
      expect(refused((manifest) => { manifest.operational_status = "agency_operational"; }, base)).toMatch(/non-operational/);
      expect(refused((manifest) => { manifest.can_feed_decision_layer = true; }, base)).toMatch(/decision layer/);
    }
  });

  it("refuses an accepted priority score or action class, in either shape", () => {
    for (const base of [served, r3]) {
      expect(refused((manifest) => { manifest.accepted_fpps = 81.2; }, base)).toMatch(/accepted score or action class/);
      expect(refused((manifest) => { manifest.accepted_fpps = 0; }, base)).toMatch(/accepted score or action class/);
      expect(refused((manifest) => { manifest.accepted_action_class = "E"; }, base)).toMatch(/accepted score or action class/);
    }
  });

  it("refuses aliases that disagree", () => {
    expect(refused((manifest) => { manifest.data_mode = "fixture_demo"; })).toMatch(/data_mode must mirror dataset_mode/);
    expect(refused((manifest) => { manifest.confidence_class = "high"; })).toMatch(/confidence_class must mirror confidence/);
    expect(refused((manifest) => { delete manifest.data_mode; }, r3)).toMatch(/lacks dataset_mode/);
    // An r4 manifest without the alias is still read: dataset_mode is the field, data_mode the alias.
    expect(refused((manifest) => { delete manifest.data_mode; })).toBe("accepted");
  });
});
