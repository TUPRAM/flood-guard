/**
 * The 2024 season envelope on the replay page: the scenario chip and caption, the legend entry, the third group of
 * the checks ("Season envelope comparison (scenario; plausibility, not validation)"), its entry in the Sources panel
 * and the credit of the exported PNG and video. The figures are read from the envelope's own statistics file.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { externalChecksByRole, TIMELINE_MANIFEST_URL, type GeoCollection, type TambonProps, type TimelineManifest } from "@/lib/flood-timeline";
import { ENVELOPE_COPY, parseSeasonEnvelopeDocument, shippableEnvelope } from "@/lib/flood-timeline-envelope";
import { localizedText } from "@/lib/flood-timeline-copy";
import { findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import { ExternalChecks } from "./mae-sai-evacuation-panels";
import { HowToRead, LicencesByInput, SourcesPanel, TimelineLegend } from "./mae-sai-flood-timeline";
import {
  createExportRenderer, EXPORT_CREDITS, exportCreditLines, PNG_WIDTH, ReplayExportPanel, VIDEO_FORMATS, type ExportEnvelope, type ReplayExportSource,
} from "./mae-sai-replay-export";
import {
  ENVELOPE_SWATCH_BACKGROUND,
  SeasonEnvelopeCaption,
  SeasonEnvelopeChip,
  SeasonEnvelopeComparison,
  SeasonEnvelopeLegend,
  SeasonEnvelopeSources,
  envelopeDocument,
  envelopeFailure,
  settledSeasonEnvelope,
  type SeasonEnvelopeState,
} from "./mae-sai-season-envelope";

const publicRoot = resolve(import.meta.dirname, "../../public");
const readJson = <T,>(href: string): T => JSON.parse(readFileSync(resolve(publicRoot, href.replace(/^\//, "")), "utf8")) as T;
const manifest = readJson<TimelineManifest>(TIMELINE_MANIFEST_URL);
const block = shippableEnvelope(manifest)!;
const document = parseSeasonEnvelopeDocument(readJson<unknown>(block.files.statistics.href), block);
const ready: SeasonEnvelopeState = { status: "ready", block, document, cells: new Uint32Array(0) };
const loading: SeasonEnvelopeState = { status: "loading", block };
const failed: SeasonEnvelopeState = { status: "error", block };
/** The statistics loaded and the raster did not: the comparison is shown, the layer is not. */
const rasterFailed: SeasonEnvelopeState = { status: "error", block, document };
const STANDARD = "Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.";
const names = Object.fromEntries(readJson<GeoCollection<unknown, TambonProps>>(manifest.vectors.tambons.href).features.map((feature) => [feature.properties.id, feature.properties]));
const check = externalChecksByRole(manifest.external_checks!).envelope[0];
const text = (html: string) => html.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, "\"").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/ /g, " ");
const THAI = /[฀-๿]/;
const CAPTION = "UNOSAT and GISTDA product 4009: accumulated water, August to October 2024 (the layer name ends 12 Oct; the product is described to 22 Oct); includes August and early-October water; not an observation for any replay day. Clipped to Mae Sai district and rasterised to the replay grid by FloodGuard.";
/** Words the season-envelope text never shows, beside the shared lint. */
const NEVER = /\b(precision|recall|accuracy|validated|corroborat\w*|September extent|GISTDA's map|too low|too high)\b/i;

describe("Season envelope on the map: chip, caption and legend", () => {
  it("shows the scenario chip and the full caption, with the licence and the credit, in both languages", () => {
    const chip = renderToStaticMarkup(<SeasonEnvelopeChip envelope={block} language="en" />);
    expect(text(chip)).toBe("Scenario (SCN-ENV): 2024 season envelope");
    // The chip carries the hatched key, so the layer is named by its pattern as well as by its words.
    expect(chip).toContain("repeating-linear-gradient");
    const caption = renderToStaticMarkup(<SeasonEnvelopeCaption envelope={block} language="en" />);
    const plain = text(caption);
    // The standard sentence leads the caption: the reader who switches the layer on is told, under the map, that the
    // agency extent is preliminary and that FloodGuard did not validate it.
    expect(block.standard_sentence).toBe(STANDARD);
    expect(plain).toContain(`Scenario (SCN-ENV): 2024 season envelope. ${STANDARD} ${CAPTION}`);
    expect(caption).toContain('data-testid="envelope-caption-standard"');
    expect(plain).toContain("Licence: CC BY-SA 4.0 · Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.");
    expect(caption).toContain('href="https://creativecommons.org/licenses/by-sa/4.0/"');
    expect(plain.replace("Unvalidated", "")).not.toMatch(NEVER);
    expect(findWordingViolations(visibleText(caption), "caption")).toEqual([]);
    const thaiChip = renderToStaticMarkup(<SeasonEnvelopeChip envelope={block} language="th" />);
    expect(text(thaiChip)).toBe("สถานการณ์จำลอง (SCN-ENV): ขอบเขตน้ำตลอดฤดูปี 2567 (2024)");
    expect(thaiChip).toContain('lang="th"');
    const thai = text(renderToStaticMarkup(<SeasonEnvelopeCaption envelope={block} language="th" />));
    expect(thai).toContain("ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู");
    expect(thai).toContain(localizedText(STANDARD, "th").text);
    expect(thai).toContain("FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน");
    expect(thai).not.toContain(STANDARD);
    expect(thai).toContain("FloodGuard ตัดให้เหลือเฉพาะอำเภอแม่สายและแปลงเป็นราสเตอร์บนกริดของการย้อนดู");
    // The published licence name and the credit stay as published; the Buddhist-era year carries its CE year.
    expect(thai).toContain("สัญญาอนุญาต: CC BY-SA 4.0 · เครดิต: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009");
    // The Thai label takes no Latin full stop.
    expect(thai).toContain("สถานการณ์จำลอง (SCN-ENV): ขอบเขตน้ำตลอดฤดูปี 2567 (2024) ");
    expect(thai).not.toContain("2567 (2024).");
    expect(thai).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    expect(thai).not.toContain(CAPTION);
  });

  it("has a hatched legend entry only while the layer is shown", () => {
    const legend = renderToStaticMarkup(<SeasonEnvelopeLegend language="en" />);
    expect(text(legend)).toBe("Season envelope (scenario)Hatched: water mapped at some time from August to October 2024; not an observation for any replay day");
    expect(legend).toContain("repeating-linear-gradient(45deg");
    // The key is a pattern of two stripe colours over a wash, not one flat colour.
    expect(ENVELOPE_SWATCH_BACKGROUND.match(/rgb\(/g)).toHaveLength(3);
    const shown = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} envelope part="overlay" />);
    const hidden = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} part="overlay" />);
    expect(shown).toContain('data-testid="envelope-legend"');
    expect(text(shown)).toContain("not an observation for any replay day");
    expect(hidden).not.toContain("envelope-legend");
    expect(text(hidden)).not.toMatch(/envelope|UNOSAT|GISTDA/i);
    // It is a layer entry, not a marker: the symbol key never carries it.
    expect(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads={false} unmodelledFacilities={false} envelope part="symbols" />)).not.toContain("envelope-legend");
    const thai = text(renderToStaticMarkup(<TimelineLegend language="th" unmodelledRoads={false} unmodelledFacilities={false} envelope part="overlay" />));
    expect(thai).toContain("ขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง)");
    expect(thai).toContain("ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู");
  });

  it("explains the scenario envelope in the reading guide when the manifest carries one", () => {
    const plain = text(renderToStaticMarkup(<HowToRead manifest={manifest} language="en" />));
    expect(plain).toContain("Scenario envelope: the hatched 2024 season envelope (UNOSAT and GISTDA product 4009) is water mapped at some time from August to October 2024.");
    expect(plain).toContain("is not an observation for any replay day");
    const without = { ...manifest, season_envelope: undefined };
    expect(renderToStaticMarkup(<HowToRead manifest={without} language="en" />)).not.toContain("how-to-envelope");
    expect(text(renderToStaticMarkup(<HowToRead manifest={manifest} language="th" />))).toContain("ไม่ใช่การสังเกตการณ์ของวันใดในการย้อนดู");
  });
});

describe("Season envelope comparison: the third group of the checks", () => {
  const html = renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" envelope={ready} names={names} />);
  const plain = text(html);
  const comparison = document.comparison;

  it("comes after the calibration groups under its own heading and is never listed as independent", () => {
    const calibration = plain.indexOf("Calibration anchor (not an independent check)");
    const informed = plain.indexOf("Size checks (calibration-informed, not independent)");
    const envelope = plain.indexOf("Season envelope comparison (scenario; plausibility, not validation)");
    expect(calibration).toBeGreaterThanOrEqual(0);
    expect(informed).toBeGreaterThan(calibration);
    expect(envelope).toBeGreaterThan(informed);
    expect(plain).not.toContain("Independent size checks");
    expect(plain).toContain("Plausibility against a season envelope, not a validation. The envelope also holds August and early-October water and the modelled peak is illustrative, so the figures say where the two differ, not which one is right.");
    // The group exists only with a shippable envelope: without one the checks keep their two groups and say nothing of it.
    for (const none of [undefined, { status: "absent" } as const]) {
      expect(text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" envelope={none} names={names} />))).not.toMatch(/Season envelope|4009/);
    }
    // A manifest whose only check is the envelope comparison still renders it (and nothing claims a size check).
    const only = { ...manifest, external_checks: manifest.external_checks!.filter((item) => item.role === "season_envelope_plausibility") };
    const alone = text(renderToStaticMarkup(<ExternalChecks manifest={only} language="en" envelope={ready} names={names} />));
    expect(alone).toContain("Season envelope comparison (scenario; plausibility, not validation)");
    expect(alone).not.toMatch(/Calibration anchor|Size checks|Independent/);
  });

  it("states the district figures at the 3.5 m peak and at the largest extent inside 13-19 Sep, from the statistics file", () => {
    const [peak, window] = comparison.district;
    expect([peak.id, peak.model_stage_m, window.id]).toEqual(["modelled_peak", 3.5, "largest_extent_13_19_sep"]);
    // The values the scouts measured before the layer was built: 0.483, 0.605 and 0.704 at the peak.
    expect([peak.agreement_iou, peak.containment_model_in_envelope, peak.containment_envelope_in_model]).toEqual([0.483, 0.605, 0.704]);
    expect(window.model_stage_m).toBe(2.65);
    expect(window.agreement_iou).toBeCloseTo(0.457, 3);
    for (const row of comparison.district) {
      expect(plain).toContain(`(${row.model_stage_m} m stage): agreement (IoU) ${row.agreement_iou!.toFixed(2)}; ${(row.containment_model_in_envelope! * 100).toFixed(1)}% of the modelled water lies inside the envelope; the modelled water reaches ${(row.containment_envelope_in_model! * 100).toFixed(1)}% of the envelope.`);
      expect(plain).toContain(`Modelled water ${row.model_km2.toFixed(1)} km², envelope ${row.envelope_km2.toFixed(1)} km², both ${row.overlap_km2.toFixed(1)} km².`);
    }
    expect(plain).toContain("The modelled peak (illustrative stage, 12 Sep 2024) (3.5 m stage): agreement (IoU) 0.48; 60.5% of the modelled water lies inside the envelope; the modelled water reaches 70.4% of the envelope.");
    expect(plain).toContain("Largest modelled extent within 13-19 Sep ICT (2.65 m stage): agreement (IoU) 0.46;");
    // The model figures are the replay's own: the peak area is the manifest's peak day.
    expect(peak.model_km2).toBeCloseTo(Math.max(...manifest.days.map((day) => day.stats.flooded_km2)), 1);
    expect(comparison.residents.model_residents_in_water).toBe(Math.max(...manifest.days.map((day) => day.stats.people_in_water ?? 0)));
  });

  it("gives the agreement by subdistrict and says where the two differ most, without a verdict on the model", () => {
    expect(comparison.by_tambon).toHaveLength(8);
    const byName = Object.fromEntries(comparison.by_tambon.map((row) => [names[row.tambon_id].en, row]));
    // The scouts' range across the six subdistricts with envelope water: 0.38 to 0.74.
    const six = ["Pong Ngam", "Si Mueang Chum", "Ban Dai", "Mae Sai", "Pong Pha", "Ko Chang"].map((name) => byName[name].agreement_iou!);
    expect(six.map((value) => Number(value.toFixed(2)))).toEqual([0.74, 0.65, 0.48, 0.43, 0.4, 0.38]);
    for (const row of comparison.by_tambon) expect(plain).toContain(`${names[row.tambon_id].en} ${row.agreement_iou === null ? "–" : row.agreement_iou.toFixed(2)}`);
    expect(plain).toContain("Agreement (IoU) by subdistrict at the modelled peak: Pong Ngam 0.74 · Si Mueang Chum 0.65 · Ban Dai 0.48 · Mae Sai 0.43 · Pong Pha 0.40 · Ko Chang 0.38");
    // Envelope water the model lacks: Ko Chang and the town first. Modelled water outside the envelope: Ban Dai and Pong Pha first.
    expect(comparison.disagreement.envelope_water_the_model_lacks.map((id) => names[id].en).slice(0, 2)).toEqual(["Ko Chang", "Mae Sai"]);
    expect(comparison.disagreement.modelled_water_outside_the_envelope.map((id) => names[id].en).slice(0, 2)).toEqual(["Ban Dai", "Pong Pha"]);
    expect(plain).toMatch(/envelope water the modelled peak does not reach is largest in Ko Chang \(\d+\.\d km²\), Mae Sai \(\d+\.\d km²\) and Si Mueang Chum \(\d+\.\d km²\)/);
    expect(plain).toMatch(/modelled water outside the envelope is largest in Ban Dai \(\d+\.\d km²\), Pong Pha \(\d+\.\d km²\) and Ko Chang \(\d+\.\d km²\)/);
    expect(plain).toContain("These are the places to check evacuation and shelter figures first; the comparison does not say which of the two is right.");
    // None of the five words, and no verdict, anywhere in the envelope's group (UNOSAT 3991's own caveat sits above it).
    const group = plain.slice(plain.indexOf("Season envelope comparison"));
    expect(group).not.toMatch(NEVER);
    expect(group).not.toMatch(/undefined|NaN|null/);
    expect(findWordingViolations(visibleText(html), "ExternalChecks with the envelope")).toEqual([]);
  });

  it("adds the low-confidence shares, the residents as a district total, the missing land-cover split, the surface-model assumption and the tuning rule", () => {
    const low = comparison.low_confidence;
    // The scouts measured 59.4% for the low-confidence water and 60.5% for all modelled water; this compares it with the other water.
    expect(low.share_inside_envelope_low_confidence).toBeCloseTo(0.593, 2);
    expect(low.share_inside_envelope_other).toBeCloseTo(0.608, 2);
    expect(plain).toContain(`Low-confidence modelled water: ${(low.share_inside_envelope_low_confidence! * 100).toFixed(1)}% of it lies inside the envelope, against ${(low.share_inside_envelope_other! * 100).toFixed(1)}% of the other modelled water.`);
    const residents = comparison.residents;
    // Two counts, each with its rule: whole WorldPop cells by their centre (the exposure definition stated for the planning
    // overlay) lead; the count by the replay's own rule is the one set beside the model's residents in water.
    expect([residents.residents_in_envelope, residents.residents_in_envelope_replay_rule]).toEqual([17_927, 17_344]);
    expect(plain).toContain("Residents inside the envelope, district total: about 17,927 (WorldPop 2020 modelled estimates; cells of about 100 m whose centre lies inside the envelope, the exposure definition stated for the planning overlay). Counted like the replay's residents in water (10 m cells, mapped channels left out), the envelope holds about 17,344; by that rule the modelled peak has "
      + `${residents.model_residents_in_water.toLocaleString("en-US")} residents in water.`);
    expect(residents.rule).toContain("whose centre lies inside the clipped envelope");
    expect(residents.replay_rule).toContain("the replay's exposure rule");
    // A district total only: the statistics file holds no per-subdistrict residents.
    expect(JSON.stringify(comparison.by_tambon)).not.toMatch(/resident/);
    expect(Object.keys(residents).sort()).toEqual(["model_residents_in_water", "model_stage", "replay_rule", "residents_in_envelope", "residents_in_envelope_replay_rule", "rule", "rules_note", "scope", "source"]);
    // No land-cover map is among the bake's inputs, so the built-up and cropland split is left out, and the page says so.
    expect(comparison.land_cover).toEqual({ computed: false, reason: "Not computed: no land-cover map is among the replay's inputs, so the share of the envelope reached is not split by built-up land and cropland." });
    expect(plain).toContain(comparison.land_cover.reason);
    expect(manifest.input_sha256!.filter((input) => /worldcover|land.?cover/i.test(input.path))).toEqual([]);
    expect(plain).toContain("The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.");
    expect(plain).toContain("The comparison was computed after the stage keyframes were final and was not used for tuning. No keyframe or elevation change is tuned to product 4009 afterwards; if one is, this comparison is relabelled as calibration.");
    expect(plain).toContain("Confidence: low — A preliminary agency product that was not checked in the field");
    expect(plain).toContain("Source timestamp: 2024-08-01/2024-10-22 · licence: CC BY-SA 4.0 · credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009");
    for (const url of check.urls) expect(html).toContain(`href="${url}"`);
  });

  it("shows no figure while the statistics file loads or when it cannot be read", () => {
    for (const [state, sentence] of [[loading, "Loading the season envelope…"], [failed, "The figures of this comparison are not shown: its statistics file could not be loaded."]] as const) {
      const pending = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" envelope={state} names={names} />));
      expect(pending).toContain("Season envelope comparison (scenario; plausibility, not validation)");
      expect(pending).toContain("Plausibility against a season envelope, not a validation.");
      expect(pending).toContain(sentence);
      expect(pending).not.toMatch(/agreement \(IoU\)|Residents inside the envelope|km², envelope/);
    }
  });

  it("keeps its figures when only the raster failed or is still loading: the comparison needs the statistics file alone", () => {
    for (const state of [rasterFailed, { status: "loading", block, document } as SeasonEnvelopeState]) {
      const shown = text(renderToStaticMarkup(<ExternalChecks manifest={manifest} language="en" envelope={state} names={names} />));
      expect(shown).toBe(plain);
      expect(shown).not.toMatch(/could not be loaded|Loading the season envelope/);
    }
    // The two files settle on their own. The statistics decide the comparison; the layer needs both.
    const cells = new Uint32Array([1, 2]);
    const ok = <T,>(value: T): PromiseFulfilledResult<T> => ({ status: "fulfilled", value });
    const no: PromiseRejectedResult = { status: "rejected", reason: new Error("HTTP 404") };
    expect(settledSeasonEnvelope(block, ok(document), ok(cells))).toEqual({ status: "ready", block, document, cells });
    expect(settledSeasonEnvelope(block, ok(document), no)).toEqual({ status: "error", block, document });
    expect(settledSeasonEnvelope(block, no, ok(cells))).toEqual({ status: "error", block });
    expect(settledSeasonEnvelope(block, no, no)).toEqual({ status: "error", block });
    expect([ready, rasterFailed, failed, loading, { status: "absent" } as const].map(envelopeDocument)).toEqual([document, document, null, null, null]);
    // Each failure has its own, accurate sentence, in both languages.
    expect(envelopeFailure(rasterFailed, "en")).toBe("The season envelope's map layer could not be loaded, so the layer is not shown. Its comparison figures are still shown under “Evidence for this moment”.");
    expect(envelopeFailure(failed, "en")).toBe("The season envelope could not be loaded, so its layer and its comparison are not shown.");
    expect(envelopeFailure(rasterFailed, "th")).toContain("ตัวเลขการเทียบยังแสดงอยู่ในหัวข้อ “หลักฐานของช่วงเวลานี้”");
    expect(envelopeFailure(failed, "th")).toContain("จึงไม่แสดงชั้นข้อมูลและการเทียบของขอบเขตนี้");
    for (const state of [ready, loading, { status: "absent" } as const]) expect(envelopeFailure(state, "en")).toBeNull();
  });

  it("reads the same in Thai, with the published names kept as published", () => {
    const thaiHtml = renderToStaticMarkup(<SeasonEnvelopeComparison check={check} envelope={ready} names={names} language="th" />);
    const thai = text(thaiHtml);
    expect(thai).toContain("การเทียบกับขอบเขตน้ำตลอดฤดู (สถานการณ์จำลอง; ดูความสมเหตุสมผล ไม่ใช่การยืนยันความถูกต้อง)");
    expect(thai).toContain("เป็นการดูความสมเหตุสมผลเทียบกับขอบเขตน้ำตลอดฤดู ไม่ใช่การยืนยันความถูกต้อง");
    expect(thai).toContain("ความสอดคล้อง (IoU) 0.48");
    expect(thai).toContain(names.TH570903.th);
    expect(thai).toContain("การเทียบนี้ไม่ได้บอกว่าข้อมูลใดถูกต้อง");
    expect(thai).toContain("แบบจำลองพื้นผิวความละเอียด 30 ม. ทำให้ระดับพื้นดินในเขตสิ่งปลูกสร้างสูงกว่าจริง");
    expect(thai).toContain("ความเชื่อมั่น: ต่ำ");
    // Every sentence of the statistics file that the group shows has a Thai rendering.
    for (const sentence of [check.title, check.use, comparison.land_cover.reason, comparison.tuning.statement, comparison.tuning.rule, document.confidence_reason,
      ...comparison.district.map((row) => row.model_extent)]) expect(thai, sentence).not.toContain(sentence);
    expect(thai).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    expect(thai).toMatch(THAI);
    expect(findWordingViolations(visibleText(thaiHtml), "comparison th")).toEqual([]);
  });
});

describe("Season envelope in the Sources panel", () => {
  it("lists the licence, the credit, the change notice and the three files, the licence notice among them", () => {
    const html = renderToStaticMarkup(<SeasonEnvelopeSources envelope={ready} language="en" />);
    const plain = text(html);
    expect(plain).toContain("Season envelope (scenario layer)");
    expect(plain).toContain(`Scenario (SCN-ENV): 2024 season envelope. ${CAPTION}`);
    expect(plain).toContain("Unvalidated preliminary agency extent (UNOSAT product 4009 with GISTDA; Field_Validation=0), used as provided under CC BY-SA 4.0. FloodGuard did not validate it.");
    expect(plain).toContain("Licence: CC BY-SA 4.0 · Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.");
    expect(plain).toContain(`Change notice: ${document.change_notice}`);
    // The statistics file's other inputs, with the licences and credits they keep.
    expect(plain).toContain("The statistics file also holds figures from other open data, which keep their own credits and licences; give these credits as well when you reuse it: "
      + "Copernicus DEM GLO-30 (tiles N20 E099 and N20 E100) (Copernicus DEM licence (free, attribution); © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA)"
      + " · WorldPop Thailand 100 m population 2020, unconstrained top-down (CC BY 4.0; WorldPop (www.worldpop.org), University of Southampton)"
      + " · HDX Thailand COD-AB subdistrict boundaries v01 (CC BY-IGO; OCHA / HDX Thailand COD-AB).");
    expect(document.other_inputs.map((item) => item.id)).toEqual(["copernicus-dem", "worldpop", "cod-ab"]);
    for (const [name, file] of [["envelope.png", block.files.raster], ["envelope.json", block.files.statistics], ["LICENSE", block.files.licence]] as const) {
      expect(html).toContain(`<a href="${file.href}" download="${name}"`);
    }
    for (const limit of document.limitations) expect(plain, limit).toContain(limit);
    expect(plain).toContain("the owners confirmed the rights record on 2 Oct 2026. Shown from this revision as a scenario layer.");
    // Internal decision numbers and repository paths are not reader copy.
    expect(plain).not.toMatch(/\bD\d+\b|docs\/|rights_basis/);
    expect(plain).not.toMatch(NEVER);
    expect(findWordingViolations(visibleText(html), "SeasonEnvelopeSources")).toEqual([]);
    expect(renderToStaticMarkup(<SeasonEnvelopeSources envelope={{ status: "absent" }} language="en" />)).toBe("");
    // While the files load, or when they cannot be read, the entry still gives the licence, the credit and the files.
    const pending = text(renderToStaticMarkup(<SeasonEnvelopeSources envelope={failed} language="en" />));
    expect(pending).toContain("Credit: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.");
    expect(pending).toContain("The season envelope could not be loaded, so its layer and its comparison are not shown.");
    expect(pending).not.toContain("Change notice:");
    // With the statistics and without the raster the entry keeps the change notice and says that only the layer is missing.
    const noRaster = text(renderToStaticMarkup(<SeasonEnvelopeSources envelope={rasterFailed} language="en" />));
    expect(noRaster).toContain(`Change notice: ${document.change_notice}`);
    expect(noRaster).toContain("The season envelope's map layer could not be loaded, so the layer is not shown.");
    expect(noRaster).not.toContain("its layer and its comparison are not shown");
    const thaiHtml = renderToStaticMarkup(<SeasonEnvelopeSources envelope={ready} language="th" />);
    const thai = text(thaiHtml);
    expect(thai).toContain("ขอบเขตน้ำตลอดฤดู (ชั้นข้อมูลสถานการณ์จำลอง)");
    expect(thai).toContain("FloodGuard ก็ไม่ได้ตรวจสอบเช่นกัน");
    // What FloodGuard changed is readable in Thai: the notice in Thai first, then the English notice as published.
    const thaiNotice = localizedText(document.change_notice, "th");
    expect(thaiNotice.lang).toBe("th");
    expect(thaiNotice.text).toBe("FloodGuard เปลี่ยนแปลงดังนี้: ตัดตามขอบเขตอำเภอแม่สาย (ตำบลทั้งแปดตาม HDX Thailand COD-AB v01) ซ่อมแซมรูปทรงเรขาคณิต (make_valid ซ่อมแซม 3 ส่วน) "
      + "แปลงระบบพิกัดจาก EPSG:4326 เป็น EPSG:3857 และแปลงเป็นราสเตอร์ขนาดเซลล์ ประมาณ 15 ม. แหล่งข้อมูล: UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009, CC BY-SA 4.0");
    expect(thai).toContain(`ประกาศการเปลี่ยนแปลง: ${thaiNotice.text} (ข้อความตามที่เผยแพร่: ${document.change_notice})`);
    expect(thaiHtml).toContain(`<span lang="th">${thaiNotice.text}</span>`);
    // The same Thai sentences are in the Thai half of the licence file that ships beside the layer, for both derived files.
    const licence = readFileSync(resolve(publicRoot, block.files.licence.href.replace(/^\//, "")), "utf8").split("-".repeat(80));
    expect(licence).toHaveLength(2);
    expect(licence[1]).toContain(thaiNotice.text);
    expect(licence[1]).toContain(localizedText(document.comparison.change_notice, "th").text);
    expect(localizedText(document.comparison.change_notice, "th").text).toContain("เพื่อจัดทำตารางนี้");
    expect(licence[0]).not.toContain(thaiNotice.text);
    expect(thai).toContain("ไฟล์สถิติมีตัวเลขที่มาจากข้อมูลเปิดอื่นด้วย ซึ่งมีเครดิตและสัญญาอนุญาตของตนเอง");
    for (const limit of document.limitations) expect(thai, limit).not.toContain(limit);
    expect(thai).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
  });

  it("sits in the Sources panel with the product's own source line and licence row", () => {
    const panel = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} envelope={ready} />);
    const plain = text(panel);
    expect(panel).toContain('data-testid="envelope-sources"');
    expect(plain).toContain("UNOSAT/GISTDA product 4009: water extents 1 Aug-22 Oct 2024, Chiang Rai — CC BY-SA 4.0. UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009.");
    expect(plain).toContain("The 30 m surface model raises the ground in built-up areas, so modelled water and residents in town are likely underestimated.");
    expect(plain).toContain("Recorded rule: no keyframe or elevation change is tuned to product 4009 afterwards; if one is, the comparison is relabelled as calibration.");
    // Product 4009 is no longer among the references waiting to be ingested.
    expect(plain.split("Other references (not ingested)")[1]?.split("Evacuation access scenario")[0] ?? "").not.toMatch(/4009/);
    expect(renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />)).not.toContain("envelope-sources");
    const licences = text(renderToStaticMarkup(<LicencesByInput manifest={manifest} language="en" />));
    expect(licences).toMatch(/UNOSAT\/GISTDA product 4009: water extents 1 Aug-22 Oct 2024, Chiang Rai — CC BY-SA 4\.0\. Attribution, share-alike and a change notice on every derived file; kept in its own folder\. Shown as a season envelope scenario layer; the owners confirmed the rights record on 2 Oct 2026\./);
    expect(licences).toContain("UNOSAT/GISTDA product 4009 (CC BY-SA 4.0) is shown as a season envelope scenario layer: its derived files keep their own folder, credit, licence and change notice");
  });
});

describe("Season envelope in the exported PNG and video", () => {
  const FULL = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · clipped to Mae Sai district and rasterised by FloodGuard";
  const visible: ExportEnvelope = { cells: new Uint32Array([5, 6, 7]), credit: block.credit, licence: block.licence, licence_url: block.licence_url };

  it("credits the product in full while the layer is visible, and not at all while it is hidden", () => {
    // An exported picture leaves the page: it carries the rights record's attribution (holders, event code, product
    // number), the licence with its address and what FloodGuard changed, not the short credit of the map.
    expect(exportCreditLines(visible, "en")).toEqual([EXPORT_CREDITS, FULL]);
    expect(exportCreditLines(visible, "en")[1]).toContain(block.credit);
    expect(exportCreditLines(visible, "en")[1]).not.toBe(block.map_credit);
    expect(exportCreditLines(visible, "th")[1]).toBe(
      "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · FloodGuard ตัดตามขอบเขตอำเภอแม่สายและแปลงเป็นราสเตอร์");
    for (const hidden of [null, undefined]) {
      expect(exportCreditLines(hidden, "en")).toEqual([EXPORT_CREDITS]);
      expect(exportCreditLines(hidden, "en").join(" ")).not.toMatch(/CC BY-SA|UNOSAT|GISTDA/);
    }
    // The standing credits are unchanged by the layer.
    expect(EXPORT_CREDITS).toBe("Contains modified Copernicus Sentinel data 2024 · © OpenStreetMap contributors · Copernicus DEM © DLR e.V., Airbus DS · WorldPop");
  });

  it("says under the export buttons which credits the frame carries, with and without the layer", () => {
    const on = renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="en" waterOpacity={0.85} envelope={visible} />);
    const off = renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="en" waterOpacity={0.85} />);
    const credits = (html: string) => text(html.split('data-testid="export-credits">')[1].split("</p>")[0]);
    expect(credits(on)).toBe(`Credits drawn into the PNG and the video: ${EXPORT_CREDITS} · ${FULL}`);
    expect(credits(off)).toBe(`Credits drawn into the PNG and the video: ${EXPORT_CREDITS}`);
    expect(text(on)).toContain("The season envelope (scenario) is on the map, so the PNG and the video draw it hatched, with its legend entry, its full credit, its licence and a note of what FloodGuard changed.");
    expect(off).not.toContain("export-envelope");
    expect(text(off)).not.toMatch(/CC BY-SA|UNOSAT|GISTDA|season envelope/i);
    const thaiHtml = renderToStaticMarkup(<ReplayExportPanel source={null} time={3.5} language="th" waterOpacity={0.85} envelope={visible} />);
    const thai = text(thaiHtml);
    expect(thai).toContain("เครดิตที่วาดลงในภาพ PNG และวิดีโอ");
    expect(thai).toContain("UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0) · FloodGuard ตัดตามขอบเขตอำเภอแม่สายและแปลงเป็นราสเตอร์");
    // The published credit and licence are marked as English; the change note is in the page's language.
    expect(thaiHtml).toContain('<span lang="en">UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009 · CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0)</span>');
  });

  /**
   * The renderer itself, on a canvas that records what is drawn: text is as wide as its characters (half the font size
   * each), so wrapping and fitting behave as in a browser, and every `fillText` and `drawImage` call is kept.
   */
  interface Recorded { texts: string[]; images: unknown[]; canvases: StubCanvas[] }
  interface StubCanvas { width: number; height: number; getContext: () => unknown }
  function recordingCanvas(): Recorded {
    const recorded: Recorded = { texts: [], images: [], canvases: [] };
    const context = (canvas: StubCanvas) => {
      const state: Record<string, unknown> = { font: "400 10px sans-serif" };
      const size = () => Number(/(\d+(?:\.\d+)?)px/.exec(String(state.font))?.[1] ?? 10);
      const methods: Record<string, (...values: unknown[]) => unknown> = {
        measureText: (value) => ({ width: String(value).length * size() * 0.5 }),
        fillText: (value) => { if (canvas === recorded.canvases[0]) recorded.texts.push(String(value)); },
        drawImage: (image) => { if (canvas === recorded.canvases[0]) recorded.images.push(image); },
        createImageData: (width, height) => ({ data: new Uint8ClampedArray(Number(width) * Number(height) * 4), width, height }),
      };
      return new Proxy(state, {
        get: (target, key: string) => (key in methods ? methods[key] : key in target ? target[key] : () => undefined),
        set: (target, key: string, value) => { target[key] = value; return true; },
      });
    };
    const stub = {
      createElement: () => {
        const canvas: StubCanvas = { width: 0, height: 0, getContext: () => held };
        const held = context(canvas);
        recorded.canvases.push(canvas);
        return canvas;
      },
    };
    vi.stubGlobal("document", stub);
    vi.stubGlobal("Image", class { decoding = ""; src = ""; decode() { return Promise.reject(new Error("no image in this test")); } });
    vi.stubGlobal("Path2D", class { moveTo() {} lineTo() {} closePath() {} });
    return recorded;
  }
  const exportSource = (): ReplayExportSource => ({
    manifest,
    roads: { type: "FeatureCollection", features: [] },
    roadProps: [],
    facilityProps: [],
    hand: { codes: new Uint8Array(manifest.hand.width * manifest.hand.height).fill(manifest.hand.never_code), factorKeys: null, candidates: new Uint32Array(0) },
  });
  const squeeze = (value: string) => value.replace(/\s+/g, "");
  /** Whether `rows`, drawn one after another, hold `whole` in order with nothing cut. */
  const drawnWhole = (texts: string[], whole: string) => squeeze(texts.join("")).includes(squeeze(whole));

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ["portrait", "en"], ["portrait", "th"], ["landscape", "en"], ["landscape", "th"],
  ] as const)("draws the hatch, the whole legend entry and the whole credit into a %s frame (%s) only while the layer is passed", async (format, language) => {
    const legend = ENVELOPE_COPY.exportLegend[language];
    const credit = exportCreditLines(visible, language)[1];
    for (const width of format === "portrait" ? [VIDEO_FORMATS.portrait.width, PNG_WIDTH] : [VIDEO_FORMATS.landscape.width]) {
      const withLayer = recordingCanvas();
      const renderer = await createExportRenderer(exportSource(), { width, language, waterOpacity: 0.85, format, envelope: visible });
      // The frame: the envelope's own canvas is drawn over the water (two pictures: the water, then the envelope).
      renderer.draw(3.5);
      const envelopeCanvas = withLayer.canvases[2];
      expect(withLayer.canvases).toHaveLength(3);
      expect(withLayer.images).toEqual([withLayer.canvases[1], envelopeCanvas]);
      // Its legend entry and its credit are drawn whole: wrapped onto further rows, never cut with an ellipsis.
      expect(drawnWhole(withLayer.texts, legend), `${format} ${language} ${width}: legend`).toBe(true);
      expect(drawnWhole(withLayer.texts, credit), `${format} ${language} ${width}: credit`).toBe(true);
      const ownRows = withLayer.texts.filter((row) => /UNOSAT|CC BY-SA|FloodGuard ตัด|clipped to|season envelope|ขอบเขตน้ำตลอดฤดู|การสังเกตการณ์ของวันใด|replay day/.test(row));
      expect(ownRows.length).toBeGreaterThanOrEqual(2);
      expect(ownRows.filter((row) => row.includes("…"))).toEqual([]);
      expect(withLayer.texts.join(" ")).toContain("FL20240912THA");
      // The standing credits stay on the frame beside it.
      expect(withLayer.texts.some((row) => row.startsWith("Contains modified Copernicus Sentinel data 2024"))).toBe(true);
      // The portrait frame grows by the credit's rows; the 16:9 frame keeps its shape.
      const frameHeight = renderer.canvas.height;
      // The end card of the video carries the credit too.
      withLayer.texts.length = 0;
      renderer.drawEnd();
      expect(drawnWhole(withLayer.texts, credit), `${format} ${language} ${width}: end card`).toBe(true);
      vi.unstubAllGlobals();

      const without = recordingCanvas();
      const plain = await createExportRenderer(exportSource(), { width, language, waterOpacity: 0.85, format });
      plain.draw(3.5);
      plain.drawEnd();
      expect(without.canvases).toHaveLength(2);
      expect(without.images.every((image) => image === without.canvases[1])).toBe(true);
      expect(without.texts.join(" ")).not.toMatch(/UNOSAT|GISTDA|CC BY-SA|FL20240912THA|season envelope|ขอบเขตน้ำตลอดฤดู/);
      if (format === "portrait") expect(frameHeight).toBeGreaterThan(plain.canvas.height);
      else expect(frameHeight).toBe(plain.canvas.height);
      vi.unstubAllGlobals();
    }
  });

  it("wraps the Thai legend entry of the portrait frame onto a second row instead of cutting it", async () => {
    // The portrait legend is 380 px wide at a 720 px frame; the Thai entry is wider than the 350 px its row has.
    const recorded = recordingCanvas();
    const renderer = await createExportRenderer(exportSource(), { width: VIDEO_FORMATS.portrait.width, language: "th", waterOpacity: 0.85, envelope: visible });
    renderer.draw(3.5);
    const rows = recorded.texts.filter((row) => /ขอบเขตน้ำตลอดฤดูปี|ในการย้อนดู\)/.test(row));
    expect(rows.length).toBeGreaterThanOrEqual(2);
    expect(squeeze(rows.join(""))).toBe(squeeze(ENVELOPE_COPY.exportLegend.th));
    expect(rows.join("")).toContain("ในการย้อนดู)");
    expect(rows.join("")).not.toContain("…");
  });
});
