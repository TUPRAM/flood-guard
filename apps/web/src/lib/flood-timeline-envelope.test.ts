/**
 * The 2024 season envelope (UNOSAT and GISTDA product 4009) as a scenario layer of the replay: it ships only with
 * its label, its standard sentence, its licence and a credit that names its holders; no replay day selects it; its
 * credit is added while it is visible and gone while it is hidden; a statistics file that lacks anything the page
 * reads is refused; and it is drawn hatched, not by colour alone.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { deflateSync, inflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";

import {
  decodePng,
  EVENT_HOURS,
  hatchStripes,
  latestObservation,
  LOW_CONFIDENCE_HATCH,
  s2CrosscheckAt,
  SEASON_ENVELOPE_ROLE,
  TIMELINE_MANIFEST_URL,
  viirsDayAt,
  type TimelineManifest,
} from "./flood-timeline";
import {
  creditHolders,
  ENVELOPE_COPY,
  ENVELOPE_EXPORT_CHANGE,
  ENVELOPE_HATCH_STEADY_SCALE,
  ENVELOPE_RGBA,
  envelopeCells,
  envelopeCredit,
  envelopeDifferenceList,
  envelopeExportCredit,
  envelopeExportCreditParts,
  envelopeHatch,
  envelopeHatchClass,
  envelopeIou,
  envelopeShare,
  paintEnvelope,
  parseSeasonEnvelopeDocument,
  SEASON_ENVELOPE_LICENCE,
  seasonEnvelopeDrawn,
  SeasonEnvelopeError,
  shippableEnvelope,
} from "./flood-timeline-envelope";
import { imageryChoices } from "./flood-timeline-link";
import { findWordingViolations } from "./replay-wording-lint";

const publicRoot = resolve(import.meta.dirname, "../../public");
const publicFile = (href: string) => resolve(publicRoot, href.replace(/^\//, ""));
const manifest = JSON.parse(readFileSync(publicFile(TIMELINE_MANIFEST_URL), "utf8")) as TimelineManifest;
const block = shippableEnvelope(manifest)!;
const served = (): Record<string, unknown> => JSON.parse(readFileSync(publicFile(block.files.statistics.href), "utf8")) as Record<string, unknown>;
const document = parseSeasonEnvelopeDocument(served(), block);
const inflate = (data: Uint8Array) => new Uint8Array(inflateSync(data));

/** A PNG file from raw scanlines (each row starts with its filter byte); chunk checksums are not read by the decoder. */
function png(width: number, height: number, bitDepth: number, colourType: number, scanlines: Uint8Array): Uint8Array {
  const chunk = (type: string, data: Uint8Array) => {
    const out = new Uint8Array(12 + data.length);
    new DataView(out.buffer).setUint32(0, data.length);
    out.set([...type].map((letter) => letter.charCodeAt(0)), 4);
    out.set(data, 8);
    return out;
  };
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  header.set([bitDepth, colourType, 0, 0, 0], 8);
  const parts = [new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", new Uint8Array(deflateSync(scanlines))), chunk("IEND", new Uint8Array(0))];
  const file = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let cursor = 0;
  for (const part of parts) {
    file.set(part, cursor);
    cursor += part.length;
  }
  return file;
}

describe("Season envelope: what ships", () => {
  it("ships with its scenario label, caption, licence and credit, and its three hashed files", () => {
    expect(block.label).toBe("Scenario (SCN-ENV): 2024 season envelope");
    expect(block.caption).toBe("UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; the product is described to 22 Oct); includes August and early-October water; not an observation for any replay day. Clipped to Mae Sai district and rasterised to the replay grid by FloodGuard.");
    expect(block.licence).toBe(SEASON_ENVELOPE_LICENCE);
    expect(block.map_credit).toBe("UNOSAT and GISTDA · CC BY-SA 4.0");
    for (const file of Object.values(block.files)) {
      const bytes = readFileSync(publicFile(file.href));
      expect(createHash("sha256").update(bytes).digest("hex"), file.href).toBe(file.sha256);
      expect(bytes.byteLength, file.href).toBe(file.bytes);
    }
    // The wording never calls the layer the September extent or GISTDA's map, and passes the shared lint.
    for (const sentence of [block.label, block.caption, block.standard_sentence, block.day_rule, ...block.assumptions]) {
      expect(findWordingViolations(sentence, "season_envelope")).toEqual([]);
      expect(sentence).not.toMatch(/September extent|GISTDA's map/i);
    }
  });

  it("does not ship without its label, its standard sentence, its licence, or a credit that names its holders", () => {
    const shipped = (change: (value: Record<string, unknown>) => void): boolean => {
      const value = JSON.parse(JSON.stringify(manifest.season_envelope)) as Record<string, unknown>;
      change(value);
      return shippableEnvelope({ season_envelope: value as unknown as TimelineManifest["season_envelope"] }) !== null;
    };
    expect(shipped(() => undefined)).toBe(true);
    // The caption under the map shows the standard sentence: without it nothing by the map says "preliminary, not validated".
    expect(block.standard_sentence).toBe("Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.");
    expect(shipped((value) => { delete value.standard_sentence; })).toBe(false);
    expect(shipped((value) => { value.standard_sentence = " "; })).toBe(false);
    expect(shipped((value) => { value.standard_sentence = "Agency extent, used as provided under CC BY-SA 4.0."; })).toBe(false);
    // A map credit that names the licence and nobody, or only one of the holders, credits nobody.
    expect(creditHolders(block.credit)).toBe("UNOSAT and GISTDA");
    expect(creditHolders("One holder")).toBe("One holder");
    expect(shipped((value) => { value.map_credit = "CC BY-SA 4.0"; })).toBe(false);
    expect(shipped((value) => { value.map_credit = "GISTDA · CC BY-SA 4.0"; })).toBe(false);
    expect(shipped((value) => { value.map_credit = "UNOSAT and GISTDA"; })).toBe(false);
    expect(shipped((value) => { value.credit = ", FL20240912THA"; })).toBe(false);
    for (const key of ["label", "caption", "licence", "licence_url", "credit", "map_credit", "files"]) expect(shipped((value) => { delete value[key]; }), key).toBe(false);
    expect(shipped((value) => { value.label = "2024 season envelope"; })).toBe(false);
    expect(shipped((value) => { value.caption = "Accumulated water, August to October 2024."; })).toBe(false);
    expect(shipped((value) => { value.licence = "CC BY 4.0"; })).toBe(false);
    expect(shipped((value) => { value.lane = "OBS"; })).toBe(false);
    expect(shipped((value) => { value.day_independent = false; })).toBe(false);
    expect(shippableEnvelope(null)).toBeNull();
    expect(shippableEnvelope({})).toBeNull();
  });

  it("reads the statistics file only when it is the scenario envelope the manifest names", () => {
    expect(document.lane).toBe("SCN-ENV");
    expect(document.not_an_observation_for_any_replay_day).toBe(true);
    expect(document.licence.name).toBe("CC BY-SA 4.0");
    expect(document.credit).toBe("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009");
    expect(document.change_notice).toMatch(/^Changed by FloodGuard: clipped to Mae Sai district \(.+\); geometry repaired \(make_valid; \d+ parts repaired\); reprojected from EPSG:4326 to EPSG:3857; rasterised to about 15 m cells\. Source: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009, CC BY-SA 4\.0\.$/);
    expect(document.generated_at).toBe(manifest.generated_at);
    expect(document.source_timestamp).toBe("2024-08-01/2024-10-22");
    expect(document.confidence).toBe("low");
    expect(document.assumptions.length).toBeGreaterThanOrEqual(6);
    expect(document.comparison.role).toBe(SEASON_ENVELOPE_ROLE);
    expect(document.comparison.use).toMatch(/^Plausibility against a season envelope, not a validation\./);
    const refused = (change: (value: Record<string, unknown>) => void): string => {
      const value = served();
      change(value);
      try {
        parseSeasonEnvelopeDocument(value, block);
      } catch (error) {
        expect(error).toBeInstanceOf(SeasonEnvelopeError);
        return (error as Error).message;
      }
      return "accepted";
    };
    expect(refused(() => undefined)).toBe("accepted");
    expect(refused((value) => { value.lane = "OBS"; })).toMatch(/scenario envelope/);
    expect(refused((value) => { value.not_an_observation_for_any_replay_day = false; })).toMatch(/no observation for a replay day/);
    expect(refused((value) => { value.licence = { name: "CC BY 4.0", url: "https://creativecommons.org/licenses/by/4.0/" }; })).toMatch(/CC BY-SA 4\.0/);
    expect(refused((value) => { delete value.licence; })).toMatch(/CC BY-SA 4\.0/);
    expect(refused((value) => { value.credit = "GISTDA"; })).toMatch(/different credits/);
    expect(refused((value) => { value.map_credit = "UNOSAT and GISTDA"; })).toMatch(/different credits/);
    expect(refused((value) => { value.change_notice = ""; })).toMatch(/change notice/);
    expect(refused((value) => { delete value.label; })).toMatch(/label/);
    expect(refused((value) => { value.official_warning = true; })).toMatch(/not an official warning/);
    expect(refused((value) => { (value.raster as Record<string, unknown>).sha256 = "0".repeat(64); })).toMatch(/another raster/);
    expect(refused((value) => { (value.comparison as Record<string, unknown>).role = "independent_magnitude_check"; })).toMatch(/plausibility comparison/);
    expect(refused((value) => { (value.comparison as Record<string, unknown>).use = "A validation of the model."; })).toMatch(/plausibility comparison/);
    expect(refused((value) => { value.assumptions = []; })).toMatch(/assumptions/);
    expect(() => parseSeasonEnvelopeDocument(null, block)).toThrow(SeasonEnvelopeError);
    expect(() => parseSeasonEnvelopeDocument([], block)).toThrow(SeasonEnvelopeError);
  });

  it("refuses a statistics file that lacks anything the page reads, so the page says 'not shown' and never fails while drawing", () => {
    const comparison = (value: Record<string, unknown>) => value.comparison as Record<string, unknown>;
    const part = (value: Record<string, unknown>, key: string) => comparison(value)[key] as Record<string, unknown>;
    const rows = (value: Record<string, unknown>, key: string) => comparison(value)[key] as Record<string, unknown>[];
    const cases: [string, (value: Record<string, unknown>) => void, RegExp][] = [
      ["no residents block", (value) => { delete comparison(value).residents; }, /both counts of residents/],
      ["one count of residents only", (value) => { delete part(value, "residents").residents_in_envelope_replay_rule; }, /both counts of residents/],
      ["a count without its rule", (value) => { delete part(value, "residents").rule; }, /both counts of residents/],
      ["no residents of the model", (value) => { part(value, "residents").model_residents_in_water = "16060"; }, /both counts of residents/],
      ["no lists of differences", (value) => { delete comparison(value).disagreement; }, /lists of largest differences/],
      ["a list that is not a list", (value) => { part(value, "disagreement").envelope_water_the_model_lacks = "TH570903"; }, /lists of largest differences/],
      ["no low-confidence block", (value) => { delete comparison(value).low_confidence; }, /low-confidence shares/],
      ["a share above 1", (value) => { part(value, "low_confidence").share_inside_envelope_other = 60.8; }, /low-confidence shares/],
      ["no land-cover note", (value) => { delete comparison(value).land_cover; }, /land-cover split/],
      ["a land-cover split left out without a reason", (value) => { part(value, "land_cover").reason = ""; }, /land-cover split/],
      ["no tuning rule", (value) => { delete part(value, "tuning").rule; }, /tuning statement and rule/],
      ["no tuning block", (value) => { delete comparison(value).tuning; }, /tuning statement and rule/],
      ["a district row without an area", (value) => { delete rows(value, "district")[0].model_km2; }, /areas, its ratios or its name/],
      ["a district row with a text area", (value) => { rows(value, "district")[1].overlap_km2 = "55.1"; }, /areas, its ratios or its name/],
      ["a district row without its extent", (value) => { delete rows(value, "district")[0].model_extent; }, /areas, its ratios or its name/],
      ["a district row without its stage", (value) => { delete rows(value, "district")[0].model_stage_m; }, /areas, its ratios or its name/],
      ["a subdistrict row without a ratio", (value) => { delete rows(value, "by_tambon")[2].agreement_iou; }, /areas, its ratios or its name/],
      ["a subdistrict row with a ratio above 1", (value) => { rows(value, "by_tambon")[2].agreement_iou = 1.4; }, /areas, its ratios or its name/],
      ["a subdistrict row without its difference", (value) => { delete rows(value, "by_tambon")[0].envelope_only_km2; }, /areas, its ratios or its name/],
      ["a subdistrict row without its id", (value) => { delete rows(value, "by_tambon")[0].tambon_id; }, /areas, its ratios or its name/],
      ["limits that are not a list", (value) => { value.limitations = "None."; }, /limits/],
      ["no limits", (value) => { delete value.limitations; }, /limits/],
      ["an assumption that is not text", (value) => { value.assumptions = [1]; }, /assumptions/],
      ["no other inputs", (value) => { delete value.other_inputs; }, /other inputs/],
      ["an other input without its credit", (value) => { (value.other_inputs as Record<string, unknown>[])[1].attribution = ""; }, /other inputs/],
      ["an other input without its licence", (value) => { delete (value.other_inputs as Record<string, unknown>[])[0].licence; }, /other inputs/],
    ];
    for (const [name, change, message] of cases) {
      const value = served();
      change(value);
      expect(() => parseSeasonEnvelopeDocument(value, block), name).toThrow(SeasonEnvelopeError);
      expect(() => parseSeasonEnvelopeDocument(value, block), name).toThrow(message);
    }
    // A subdistrict without modelled water has no share to state: null is not a missing figure.
    expect(document.comparison.by_tambon.some((row) => row.containment_envelope_in_model === null)).toBe(true);
  });
});

describe("Season envelope: independent of the day slider", () => {
  it("is drawn by its own toggle only: no day index, hour or imagery choice selects it", () => {
    // The one function that decides takes the toggle and whether the files have loaded, and no replay time.
    expect(seasonEnvelopeDrawn.length).toBe(2);
    expect(seasonEnvelopeDrawn(true, true)).toBe(true);
    expect(seasonEnvelopeDrawn(false, true)).toBe(false);
    expect(seasonEnvelopeDrawn(true, false)).toBe(false);
    // Everything the replay selects by time is something else: for every replay hour and every day index, the image,
    // the VIIRS day and the Sentinel-2 check that the hour selects are never the envelope or one of its files.
    const folder = block.files.raster.href.slice(0, block.files.raster.href.lastIndexOf("/") + 1);
    const envelopeHrefs = new Set(Object.values(block.files).map((file) => file.href));
    const selectedByTime = (t: number): string => JSON.stringify([
      latestObservation(t, manifest.observations, "optical"), latestObservation(t, manifest.observations),
      viirsDayAt(t, manifest.viirs_daily!.days), s2CrosscheckAt(t, manifest.s2_crosscheck)?.scenes ?? null,
    ]);
    for (let hour = 0; hour <= EVENT_HOURS; hour += 1) {
      const selected = selectedByTime(hour / 24);
      expect(selected.includes(folder), `hour ${hour}`).toBe(false);
      expect(selected, `hour ${hour}`).not.toMatch(/4009|envelope/i);
    }
    for (const day of manifest.days) {
      expect(JSON.stringify(day), day.date).not.toMatch(/4009|envelope/i);
      expect(selectedByTime(day.index + 0.5), day.date).not.toMatch(/4009|envelope/i);
    }
    // It is not an imagery layer, so neither "Auto" nor the imagery list nor the swipe comparison can show it.
    expect(imageryChoices(manifest.layers).filter((id) => /4009|envelope/i.test(id))).toEqual([]);
    expect(manifest.layers.filter((layer) => envelopeHrefs.has(layer.href))).toEqual([]);
    // The block itself carries no date, hour or day index that could place it on the slider.
    for (const key of ["date", "utc", "local", "t", "index", "hour", "nominal_local_time"]) expect(block, key).not.toHaveProperty(key);
    expect(block.day_independent).toBe(true);
    expect(block.day_rule).toBe("The layer has its own toggle: no replay day selects it, and it is not among the day observations.");
  });

  it("is absent from the day observation chips", () => {
    // The chips on the timeline band and under the stage curve come from `observations`; the day buttons from `days`.
    expect(manifest.observations.map((observation) => observation.id)).toEqual(["s2-20240905", "s1-20240906", "s2-20240915", "s1-20240915"]);
    expect(manifest.observations.filter((observation) => /4009|envelope|UNOSAT|GISTDA/i.test(JSON.stringify(observation)))).toEqual([]);
    expect(manifest.viirs_daily!.days.filter((day) => /4009|envelope/i.test(JSON.stringify(day)))).toEqual([]);
    expect(manifest.days).toHaveLength(11);
    // Its evidence block is a season envelope, never an observed lane with a day.
    const blocks = manifest.evidence_blocks!.filter((item) => item.covers.includes("season_envelope"));
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({ lane: "SCN-ENV", temporal_relation: "season_envelope", shown: true });
    expect(manifest.evidence_blocks!.filter((item) => item.lane === "OBS" && /4009|envelope/i.test(JSON.stringify(item)))).toEqual([]);
  });
});

describe("Season envelope: credit while visible", () => {
  it("gives the map the holders and CC BY-SA 4.0 while the layer is visible, and nothing while it is hidden", () => {
    expect(envelopeCredit(block, true)).toBe("UNOSAT and GISTDA · CC BY-SA 4.0");
    expect(envelopeCredit(block, true)).toContain("CC BY-SA 4.0");
    expect(envelopeCredit(block, false)).toBeNull();
    expect(envelopeCredit(null, true)).toBeNull();
    expect(envelopeCredit(undefined, true)).toBeNull();
    // The short credit names the holders the full credit begins with, and the licence.
    expect(envelopeCredit(block, true)).toBe(`${creditHolders(block.credit)} · ${block.licence}`);
  });

  it("gives an exported picture the product's full credit, the licence with its address and a change note", () => {
    // A PNG or a video leaves the page, so the short map credit is not enough for it.
    expect(envelopeExportCredit(block, "en")).toBe(
      "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · clipped to Mae Sai district and rasterised by FloodGuard");
    expect(envelopeExportCredit(block, "en").startsWith(`${block.credit} · ${block.licence} (`)).toBe(true);
    expect(envelopeExportCredit(block, "th")).toBe(
      "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · FloodGuard ตัดตามขอบเขตอำเภอแม่สายและแปลงเป็นราสเตอร์");
    expect(envelopeExportCreditParts(block, "th")).toEqual({
      published: "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0)",
      change: ENVELOPE_EXPORT_CHANGE.th,
    });
    expect(block.licence_url).toBe("https://creativecommons.org/licenses/by-sa/4.0/");
    expect(findWordingViolations(`${ENVELOPE_EXPORT_CHANGE.en} ${ENVELOPE_EXPORT_CHANGE.th}`, "ENVELOPE_EXPORT_CHANGE")).toEqual([]);
  });
});

describe("Season envelope: the raster and its hatch", () => {
  it("decodes a 1-bit greyscale PNG bit by bit, for any width and filter", async () => {
    // 10 x 3 mask: eight pixels to a byte, most significant bit first; the last byte of a row is padded.
    const rows = [
      [1, 0, 1, 1, 0, 0, 0, 1, 1, 0],
      [0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
      [1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
    ];
    const packed = rows.map((row) => [0, 8].map((start) => row.slice(start, start + 8).reduce((byte, bit, index) => byte | (bit << (7 - index)), 0)));
    const plain = new Uint8Array(packed.flatMap((bytes) => [0, ...bytes]));
    const raster = await decodePng(png(10, 3, 1, 0, plain), inflate);
    expect([raster.width, raster.height, raster.channels]).toEqual([10, 3, 1]);
    expect([...raster.data]).toEqual(rows.flat().map((bit) => bit * 255));
    // The "up" filter (2) stores each byte as the difference from the byte above.
    const up = new Uint8Array(packed.flatMap((bytes, y) => [2, ...bytes.map((value, index) => (value - (y > 0 ? packed[y - 1][index] : 0)) & 255)]));
    expect([...(await decodePng(png(10, 3, 1, 0, up), inflate)).data]).toEqual(rows.flat().map((bit) => bit * 255));
    expect([...envelopeCells(raster, 10, 3)]).toEqual(rows.flat().flatMap((bit, cell) => (bit ? [cell] : [])));
    expect(() => envelopeCells(raster, 10, 4)).toThrow(SeasonEnvelopeError);
    // Other bit depths, and a 1-bit image that is not greyscale, are still refused.
    await expect(decodePng(png(10, 3, 2, 0, plain), inflate)).rejects.toThrow(/1-bit greyscale mask/);
    await expect(decodePng(png(10, 3, 1, 3, plain), inflate)).rejects.toThrow(/1-bit greyscale mask/);
  });

  it("is the 1-bit raster on the water grid that the statistics file describes", async () => {
    const bytes = new Uint8Array(readFileSync(publicFile(block.files.raster.href)));
    expect([bytes[24], bytes[25]]).toEqual([1, 0]); // Bit depth 1, colour type 0 (greyscale).
    const raster = await decodePng(bytes, inflate);
    expect([raster.width, raster.height]).toEqual([manifest.hand.width, manifest.hand.height]);
    expect([document.raster.width, document.raster.height, document.raster.bit_depth]).toEqual([manifest.hand.width, manifest.hand.height, 1]);
    expect(new Set(raster.data)).toEqual(new Set([0, 255]));
    const cells = envelopeCells(raster, manifest.hand.width, manifest.hand.height);
    // About 15 m cells: the raster holds the district's envelope (the statistics file counts it on the 10 m grid).
    const km2 = (cells.length * 15 * 15) / 1e6;
    expect(Math.abs(km2 - document.area.district_km2)).toBeLessThan(0.5);
    expect(document.raster.bounds).toEqual(manifest.bounds);
  });

  it("draws the layer hatched: about 9 px on screen up to two pixels per cell, and four cells wide closer in", () => {
    // At 1 screen pixel per cell: a 9 px period, a 2 px dark stripe and a yellow edge beside it.
    expect(envelopeHatch(1)).toEqual({ period: 9, dark: 2, light: 2 });
    expect(ENVELOPE_HATCH_STEADY_SCALE).toBe(2);
    // On a phone the raster is drawn at about a quarter of its size, on a wide map at one to two pixels per cell: the
    // hatch is painted in whole cells, and up to two pixels per cell its period stays between 8 and 10 px on screen.
    for (const scale of [0.2, 0.25, 0.5, 0.75, 1, 1.5, 2]) {
      const hatch = envelopeHatch(scale);
      expect(hatch.period * scale, `period at ${scale}`).toBeGreaterThanOrEqual(8);
      expect(hatch.period * scale, `period at ${scale}`).toBeLessThanOrEqual(10);
      expect(hatch.dark * scale, `stripe at ${scale}`).toBeGreaterThanOrEqual(Math.min(1.5, scale));
      expect(hatch.period).toBeGreaterThan(hatch.dark + hatch.light);
    }
    // Closer in, a stripe cannot be thinner than one cell nor the period shorter than four cells: the hatch then grows
    // with the zoom (22.5 px at 5.63 px per cell, about 45 px at 11 px per cell). It stays a hatch; its width is not constant.
    for (const scale of [2.5, 4, 5.63, 11.25]) {
      expect(envelopeHatch(scale), `hatch at ${scale}`).toEqual({ period: 4, dark: 1, light: 1 });
      expect(envelopeHatch(scale).period * scale, `period at ${scale}`).toBeGreaterThan(9);
    }
    expect(envelopeHatch(5.63).period * 5.63).toBeCloseTo(22.5, 1);
    expect(envelopeHatch(0)).toEqual(envelopeHatch(1));
    expect(envelopeHatch(Number.NaN)).toEqual(envelopeHatch(1));
    // Stripes run "\\": a cell and the one below and to its right are on the same stripe. The low-confidence hatch runs "/".
    const hatch = envelopeHatch(1);
    for (let x = 0; x < 20; x += 1) for (let y = 0; y < 20; y += 1) expect(envelopeHatchClass(x + 1, y + 1, hatch)).toBe(envelopeHatchClass(x, y, hatch));
    expect([...Array(9).keys()].map((x) => envelopeHatchClass(x, 0, hatch))).toEqual([0, 0, 1, 1, 2, 2, 2, 2, 2]);
    const width = 30;
    const lowStripes = hatchStripes(Uint32Array.from({ length: width * 2 }, (_, cell) => cell), width);
    expect([lowStripes[1], lowStripes[width]]).toEqual([1, 1]); // "/": the same stripe one row down is one column to the left.
    expect(envelopeHatchClass(1, 0, hatch)).not.toBe(envelopeHatchClass(0, 1, hatch));
    expect(LOW_CONFIDENCE_HATCH.period).not.toBe(hatch.period);
  });

  it("paints every envelope cell with a stripe or the wash, and nothing outside it", () => {
    const width = 40;
    const height = 30;
    const cells = Uint32Array.from({ length: 20 * 18 }, (_, index) => (5 + Math.floor(index / 20)) * width + 10 + (index % 20));
    const pixels = new Uint32Array(width * height);
    paintEnvelope(cells, width, pixels, envelopeHatch(1));
    const colour = ([r, g, b, a]: readonly number[]) => ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
    const [dark, light, wash] = [colour(ENVELOPE_RGBA.dark), colour(ENVELOPE_RGBA.light), colour(ENVELOPE_RGBA.wash)];
    const inside = new Set(cells);
    const counts = new Map<number, number>();
    for (let cell = 0; cell < pixels.length; cell += 1) {
      if (!inside.has(cell)) expect(pixels[cell], `cell ${cell}`).toBe(0);
      else counts.set(pixels[cell], (counts.get(pixels[cell]) ?? 0) + 1);
    }
    // Not a flat fill: three colours, the two stripe colours opaque enough to read and the wash nearly clear.
    expect([...counts.keys()].sort()).toEqual([dark, light, wash].sort());
    expect(counts.get(dark)! + counts.get(light)!).toBeGreaterThan(cells.length * 0.3);
    expect(counts.get(wash)!).toBeGreaterThan(cells.length * 0.3);
    expect(ENVELOPE_RGBA.dark[3]).toBeGreaterThan(200);
    expect(ENVELOPE_RGBA.light[3]).toBeGreaterThan(200);
    expect(ENVELOPE_RGBA.wash[3]).toBeLessThan(64);
    // The stripe and its edge differ strongly in lightness, so the pattern reads on dark imagery and on a pale basemap.
    const luminance = ([r, g, b]: readonly number[]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
    expect(luminance(ENVELOPE_RGBA.light) - luminance(ENVELOPE_RGBA.dark)).toBeGreaterThan(120);
    // Big-endian pixels hold the same colours in the other byte order.
    const swapped = new Uint32Array(width * height);
    paintEnvelope(cells, width, swapped, envelopeHatch(1), false);
    const darkCell = cells.find((cell) => pixels[cell] === dark)!;
    expect(swapped[darkCell]).toBe((((ENVELOPE_RGBA.dark[0] << 24) | (ENVELOPE_RGBA.dark[1] << 16) | (ENVELOPE_RGBA.dark[2] << 8) | ENVELOPE_RGBA.dark[3]) >>> 0));
  });
});

describe("Season envelope: figures as the page writes them", () => {
  it("writes shares as percentages to one decimal and the agreement ratio to two decimals", () => {
    expect(envelopeShare(0.605)).toBe("60.5%");
    expect(envelopeShare(0.704)).toBe("70.4%");
    expect(envelopeShare(0)).toBe("0.0%");
    expect(envelopeShare(null)).toBe("–");
    expect(envelopeIou(0.483)).toBe("0.48");
    expect(envelopeIou(null)).toBe("–");
    const rows = document.comparison.by_tambon;
    const names: Record<string, string> = { TH570903: "Ko Chang", TH570901: "Mae Sai", TH570905: "Si Mueang Chum" };
    const list = envelopeDifferenceList(["TH570903", "TH570901", "TH570905"], rows, "envelope_only_km2", (id) => names[id] ?? id, "en");
    expect(list).toMatch(/^Ko Chang \(\d+\.\d km²\), Mae Sai \(\d+\.\d km²\) and Si Mueang Chum \(\d+\.\d km²\)$/);
    expect(envelopeDifferenceList(["TH570903"], rows, "model_only_km2", (id) => names[id] ?? id, "en")).toMatch(/^Ko Chang \(\d+\.\d km²\)$/);
    expect(envelopeDifferenceList(["TH570903", "TH570901"], rows, "model_only_km2", (id) => id, "th")).toMatch(/^TH570903 \(\d+\.\d ตร\.กม\.\) และTH570901 \(\d+\.\d ตร\.กม\.\)$/);
    expect(envelopeDifferenceList([], rows, "model_only_km2", (id) => id, "en")).toBe("");
    for (const entry of Object.values(ENVELOPE_COPY)) {
      expect(entry.th).toMatch(/[฀-๿]/);
      expect(entry.th).not.toMatch(/25[67]\d(?! \(20\d\d\))/); // A Buddhist-era year carries its CE year.
      expect(findWordingViolations(`${entry.en} ${entry.th}`, "ENVELOPE_COPY")).toEqual([]);
    }
  });
});
