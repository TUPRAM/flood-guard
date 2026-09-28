import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type TimelineManifest } from "./flood-timeline";
import { GLOSSARY, GLOSSARY_ORDER, localizedText, placeNameText, plainManifestText, roadNameText, thaiOnly } from "./flood-timeline-copy";

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
  });
});
