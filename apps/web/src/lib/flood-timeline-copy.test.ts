import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import { GLOSSARY, GLOSSARY_ORDER, KNOWN_THAI, localizedText, placeNameText, plainManifestText, roadNameText, STANDALONE_K, thaiManifestDate, thaiOnly } from "./flood-timeline-copy";

const manifest = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../public", TIMELINE_MANIFEST_URL.replace(/^\//, "")), "utf8")) as TimelineManifest;
const THAI = /[฀-๿]/;

describe("Mae Sai replay copy", () => {
  it("labels Thai-only place names in English with their type and keeps every other name as mapped", () => {
    expect(placeNameText("มัสยิดอันนุร แม่สาย", "en", "Place of worship")).toBe("Mosque · มัสยิดอันนุร แม่สาย");
    expect(placeNameText("วัดพรหมวิหาร", "en", "Place of worship")).toBe("Temple · วัดพรหมวิหาร");
    // Unknown leading word: the candidate's kind is the label.
    expect(placeNameText("บ้านป่าแดง", "en", "Community centre")).toBe("Community centre · บ้านป่าแดง");
    expect(placeNameText("มัสยิดอันนุร แม่สาย", "th", "Place of worship")).toBe("มัสยิดอันนุร แม่สาย");
    expect(placeNameText("Mae Sai School โรงเรียนแม่สาย", "en", "School")).toBe("Mae Sai School โรงเรียนแม่สาย");
    expect(thaiOnly("ถนนพหลโยธิน")).toBe(true);
    expect(thaiOnly("Mae Sai")).toBe(false);
  });

  it("gives the known roads an English label with the Thai name kept beside it in English only", () => {
    expect(roadNameText("ถนนพหลโยธิน", "en")).toEqual({ primary: "Phahonyothin Rd (Hwy 1)", secondary: "ถนนพหลโยธิน" });
    expect(roadNameText("ถนนเลี่ยงเมืองแม่สาย", "en")).toEqual({ primary: "Mae Sai bypass", secondary: "ถนนเลี่ยงเมืองแม่สาย" });
    expect(roadNameText("ถนนพหลโยธิน", "th")).toEqual({ primary: "ถนนพหลโยธิน", secondary: null });
    expect(roadNameText("Unknown Rd", "en")).toEqual({ primary: "Unknown Rd", secondary: null });
  });

  it("defines every glossary term in both languages, the page's technical terms included", () => {
    expect([...GLOSSARY_ORDER].sort()).toEqual(Object.keys(GLOSSARY).sort());
    for (const id of ["stage", "hand", "freeboard", "road_nodes", "t1"] as const) expect(GLOSSARY_ORDER).toContain(id);
    for (const id of GLOSSARY_ORDER) {
      const entry = GLOSSARY[id];
      expect(entry.term.en.length).toBeGreaterThan(0);
      expect(entry.definition.en.length).toBeGreaterThan(40);
      expect(entry.definition.th).toMatch(THAI);
      // Honesty: the stage and access terms say they are assumptions or model results.
      if (id === "stage") expect(entry.definition.en).toContain("not a gauge reading");
      if (id === "t1") expect(entry.definition.en).toContain("not observed evacuation outcomes");
    }
  });

  it("keeps internal ids out of user copy and translates the low-confidence sentences", () => {
    const rule = manifest.shelters!.reported_access_set_rule;
    expect(plainManifestText(rule)).not.toContain("reported_2024");
    expect(localizedText(rule, "th").lang).toBe("th");
    expect(plainManifestText(manifest.population!.source)).not.toContain("tha_ppp_2020");
    const meaning = manifest.hand.low_confidence!.meaning;
    expect(localizedText(meaning, "en")).toEqual({ text: meaning, lang: "en" });
    expect(localizedText(meaning, "th").text).toMatch(THAI);
    // Internal decision numbers ("per decision D3", "(D2)") are project bookkeeping, not reader copy.
    expect(plainManifestText("Season envelope (scenario per decision D3). The CC BY-SA 4.0 rights decision (D2) was signed on 30 Sep 2026; not a protocol case (decision D7)."))
      .toBe("Season envelope. The CC BY-SA 4.0 rights decision was signed on 30 Sep 2026; not a protocol case.");
    for (const reference of manifest.external_references ?? []) {
      if (reference.note) expect(plainManifestText(reference.note)).not.toMatch(/\bD\d+\b/);
    }
  });

  it("names the depth factor in words and writes it f, because k on this page is the plan size", () => {
    expect(plainManifestText("each cell's water rise is scaled by k = clip((A / A_Sai) ** 0.3, 0.35, 1), where A is the upstream area"))
      .toBe("each cell's water rise is scaled by the depth factor f = clip((A / A_Sai) ** 0.3, 0.35, 1), where A is the upstream area");
    expect(plainManifestText("(per-sample depth factor; the exported k makes h + 0.3/k equal the earliest sample closure)"))
      .toBe("(per-sample depth factor; the exported depth factor f makes h + 0.3/f equal the earliest sample closure)");
    expect(plainManifestText("The depth factor k = clip((A / A_Sai) ** 0.3, 0.35, 1) was added on 28 Sep 2026"))
      .toBe("The depth factor f = clip((A / A_Sai) ** 0.3, 0.35, 1) was added on 28 Sep 2026");
    expect(plainManifestText("tributaries rise k x stage (see the next assumption)")).toBe("tributaries rise to a fraction of the stage (see the next assumption)");
    // A formula that names no factor still gets the words, and ordinary words with a k in them are left alone.
    expect(plainManifestText("where k = clip(x, 0, 1)")).toBe("where depth factor f = clip(x, 0, 1)");
    expect(plainManifestText("Keyframes near the peak, 12 km from the bank")).toBe("Keyframes near the peak, 12 km from the bank");
    // Every sentence of the Sources panel: the manifest does use the symbol, the page never shows it, in either language.
    const disclosure = manifest.exploratory_knowledge!;
    const sentences = [
      ...manifest.assumptions, ...manifest.limitations, manifest.confidence_reason, manifest.model_coverage.reason,
      disclosure.purpose, disclosure.depth_factor, disclosure.rule, ...disclosure.items.map((item) => item.statement),
    ];
    expect(sentences.filter((sentence) => STANDALONE_K.test(sentence)).length).toBeGreaterThanOrEqual(3);
    for (const sentence of sentences) {
      expect(plainManifestText(sentence), sentence).not.toMatch(STANDALONE_K);
      const thai = localizedText(sentence, "th");
      expect(thai.lang, sentence).toBe("th");
      expect(thai.text, sentence).not.toMatch(STANDALONE_K);
    }
    for (const sentence of sentences.filter((item) => /depth factor k|scaled by k|exported k/.test(item))) {
      expect(plainManifestText(sentence), sentence).toContain("depth factor f");
      expect(localizedText(sentence, "th").text, sentence).toContain("ตัวคูณความลึก f");
    }
  });

  it("has a Thai rendering of every manifest sentence the page shows in its panels", () => {
    // Source names, published licence names and attributions stay as published; every sentence of explanation has a
    // translation (licence wording the project wrote itself has its own test below).
    const access = manifest.access!;
    const sentences = [
      ...manifest.assumptions, ...manifest.limitations, manifest.confidence_reason, manifest.model_coverage.reason,
      access.scenario_tier, access.definition, access.travel_mode, access.confidence_reason, access.source_timestamp,
      manifest.shelters!.confidence_reason, manifest.shelters!.reported_status, manifest.shelters!.source_timestamp,
      manifest.shelters!.reported_access_set_rule, ...manifest.shelters!.reported.map((shelter) => shelter.access_set_note),
      // The capacity-aware view and the what-if levels on the plan card: confidence reason, source timestamp, label.
      manifest.shelters!.capacitated!.confidence_reason, manifest.shelters!.capacitated!.source_timestamp,
      manifest.shelters!.robustness!.confidence_reason, manifest.shelters!.robustness!.source_timestamp, manifest.shelters!.robustness!.label,
      manifest.population!.note, manifest.rainfall!.note, manifest.rainfall!.units,
      manifest.viirs_daily!.nominal_overpass, manifest.viirs_daily!.comparison_rule, manifest.viirs_daily!.caveat,
      // The Sentinel-2 water check: what it measures, its rules, its caveat and what it is consistent with.
      manifest.s2_crosscheck!.index, manifest.s2_crosscheck!.water_rule, manifest.s2_crosscheck!.clear_rule,
      manifest.s2_crosscheck!.permanent_water_rule, manifest.s2_crosscheck!.comparison_rule, manifest.s2_crosscheck!.caveat,
      manifest.s2_crosscheck!.reading, manifest.s2_crosscheck!.confidence_reason, manifest.s2_crosscheck!.scope,
      ...(manifest.external_references ?? []).flatMap((reference) => (reference.note ? [reference.note] : [])),
      ...(manifest.gauge_note ? [manifest.gauge_note] : []),
      // The event chronology's source line under the "Reported:" narrative.
      ...manifest.sources.filter((source) => source.id === "chronology").flatMap((source) => [source.attribution, source.timestamp]),
      // The evidence envelope (r4): licence terms and conditions per input, the tuning disclosure, the permitted use
      // and what the source-timestamp span covers.
      manifest.permitted_use!, manifest.source_timestamp_note!,
      manifest.publication_eligibility!.scope, ...manifest.publication_eligibility!.conditions,
      ...manifest.publication_eligibility!.inputs.flatMap((input) => [input.terms, ...(input.status ? [input.status] : [])]),
      manifest.exploratory_knowledge!.purpose, ...manifest.exploratory_knowledge!.items.map((item) => item.statement),
      manifest.exploratory_knowledge!.depth_factor, manifest.exploratory_knowledge!.rule,
    ];
    expect(sentences.length).toBeGreaterThan(80);
    expect(localizedText("compiled 2026-09-27", "th")).toEqual({ text: "รวบรวมเมื่อ 2026-09-27", lang: "th" });
    expect(localizedText("compiled 2026-09-27", "en")).toEqual({ text: "compiled 2026-09-27", lang: "en" });
    const missing = sentences.filter((sentence) => localizedText(sentence, "th").lang !== "th");
    expect(missing).toEqual([]);
  });

  it("shows licence wording the project wrote itself in Thai and keeps published licence names as published", () => {
    const published = /^(CC BY(-[A-Z]+)*( \d\.\d)?|ODbL \d\.\d)$/;
    const licences = [
      ...manifest.publication_eligibility!.inputs.map((input) => input.licence),
      ...manifest.sources.map((source) => source.licence),
      manifest.viirs_daily!.licence, manifest.rainfall!.licence, manifest.population!.licence,
    ].map((licence) => licence.replace(/\.$/, ""));
    const names = [...new Set(licences.filter((licence) => published.test(licence)))].sort();
    expect(names).toEqual(["CC BY 4.0", "CC BY-IGO", "CC BY-NC", "CC BY-SA 4.0", "ODbL 1.0"]);
    for (const name of names) expect(localizedText(name, "th")).toEqual({ text: name, lang: "en" });
    // Everything else is a sentence or a description the project wrote: each has a Thai rendering.
    const written = [...new Set(licences.filter((licence) => !published.test(licence)))];
    expect(written.length).toBeGreaterThanOrEqual(8);
    expect(written).toEqual(expect.arrayContaining(["Project summary text", "Cited figures with links; no data copied", "No licence stated by the provider"]));
    expect(written.filter((licence) => localizedText(licence, "th").lang !== "th")).toEqual([]);
    for (const licence of written) expect(localizedText(licence, "th").text, licence).toMatch(THAI);
  });

  it("writes Thai dates with the Buddhist-era year and the CE year in brackets", () => {
    expect(thaiManifestDate("30 Sep 2026")).toBe("30 ก.ย. 2569 (2026)");
    expect(thaiManifestDate("1 Oct 2026")).toBe("1 ต.ค. 2569 (2026)");
    expect(thaiManifestDate("9 Jan 2027")).toBe("9 ม.ค. 2570 (2027)");
    // No Thai sentence of the page gives a Buddhist-era year on its own.
    const bare = Object.values(KNOWN_THAI).filter((text) => /25[67]\d(?! \(20\d\d\))/.test(text));
    expect(bare).toEqual([]);
    const reference = manifest.external_references!.find((item) => item.id === "unosat-4009")!;
    const thai = localizedText(reference.note!, "th");
    expect(thai.lang).toBe("th");
    expect(thai.text).toContain("ลงนามเมื่อ 30 ก.ย. 2569 (2026)");
    expect(thai.text).toContain('UNOSAT ตอบว่า "we approve the use" (เจ้าของโครงการแจ้งคำตอบนี้ต่อทีมเมื่อ 1 ต.ค. 2569 (2026))');
    const depthFactor = localizedText(manifest.exploratory_knowledge!.depth_factor, "th").text;
    expect(depthFactor).toContain("28 ก.ย. 2569 (2026)");
  });

  it("has Thai for the status of product 4009 once the owners confirm its rights record", () => {
    // The bake reads the status from the rights record: pending today, confirmed with a date after the owners
    // confirm it. Both wordings have a Thai rendering, whatever the date.
    const confirmed = [
      "Not shown in this revision; the owners confirmed the rights record on 9 Oct 2026.",
      "UNOSAT/GISTDA product 4009 (CC BY-SA 4.0) is not shown in this revision; the owners confirmed the rights record on 9 Oct 2026.",
      "Season envelope (scenario per decision D3). The CC BY-SA 4.0 rights decision (D2) was signed on 30 Sep 2026 and UNOSAT replied \"we approve the use\" (relayed by a project owner on 1 Oct 2026); the owners confirmed the rights record on 9 Oct 2026. Not shown in this revision.",
    ];
    for (const sentence of confirmed) {
      const thai = localizedText(sentence, "th");
      expect(thai.lang, sentence).toBe("th");
      expect(thai.text, sentence).toContain("เจ้าของโครงการยืนยันบันทึกสิทธิ์การใช้ข้อมูลเมื่อ 9 ต.ค. 2569 (2026)");
      expect(thai.text, sentence).toContain("ยังไม่แสดงในข้อมูลรุ่นนี้");
      expect(localizedText(sentence, "en").lang).toBe("en");
    }
    // Another relay or signing date is read the same way.
    const later = "Season envelope. The CC BY-SA 4.0 rights decision was signed on 2 Nov 2026 and UNOSAT replied \"we approve the use\" (relayed by a project owner on 3 Nov 2026); shown only after the owners confirm the rights record.";
    expect(localizedText(later, "th").text).toContain("ลงนามเมื่อ 2 พ.ย. 2569 (2026)");
  });
});
