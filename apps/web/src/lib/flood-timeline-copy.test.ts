import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import { GLOSSARY, GLOSSARY_ORDER, localizedText, placeNameText, plainManifestText, roadNameText, STANDALONE_K, thaiOnly } from "./flood-timeline-copy";

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
    // Source names, licences and attributions stay as published; every sentence of explanation has a translation.
    const access = manifest.access!;
    const sentences = [
      ...manifest.assumptions, ...manifest.limitations, manifest.confidence_reason, manifest.model_coverage.reason,
      access.scenario_tier, access.definition, access.travel_mode, access.confidence_reason, access.source_timestamp,
      manifest.shelters!.confidence_reason, manifest.shelters!.reported_status, manifest.shelters!.source_timestamp,
      manifest.shelters!.reported_access_set_rule, ...manifest.shelters!.reported.map((shelter) => shelter.access_set_note),
      manifest.population!.note, manifest.rainfall!.note, manifest.rainfall!.units,
      manifest.viirs_daily!.nominal_overpass, manifest.viirs_daily!.comparison_rule, manifest.viirs_daily!.caveat,
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
    expect(sentences.length).toBeGreaterThan(70);
    expect(localizedText("compiled 2026-09-27", "th")).toEqual({ text: "รวบรวมเมื่อ 2026-09-27", lang: "th" });
    expect(localizedText("compiled 2026-09-27", "en")).toEqual({ text: "compiled 2026-09-27", lang: "en" });
    const missing = sentences.filter((sentence) => localizedText(sentence, "th").lang !== "th");
    expect(missing).toEqual([]);
  });
});
