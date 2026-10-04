/**
 * The wording of the Command exercise replay: the banner the owner approved, a Thai rendering of every string, the
 * figures as the situation card prints them from the served replay data, and no wording the shared lint refuses.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  formatHourStamp,
  formatMoment,
  TIMELINE_MANIFEST_URL,
  type AreaGeometry,
  type GeoCollection,
  type Language,
  type Localized,
  type RoadProps,
  type TambonProps,
  type TimelineManifest,
} from "./flood-timeline";
import { buildCommandModel, changeSinceHourBefore, districtFiguresAt } from "./flood-timeline-command";
import {
  COMMAND_BANNER,
  COMMAND_CLOCK,
  COMMAND_DRAWER,
  COMMAND_DRAWER_NOT,
  COMMAND_FIGURES,
  COMMAND_LANE_OF,
  COMMAND_LANE_ORDER,
  COMMAND_LANES,
  commandBannerLine,
  commandBannerParts,
  commandBaseText,
  commandChangeLine,
  commandDataLine,
  commandDrawerHeading,
  commandFigureCells,
  commandHourOf,
  commandHourShort,
  commandLaneMeaning,
  commandLaneTag,
  commandLifeAtRisk,
  commandMoment,
  commandMomentShort,
  commandOpenItems,
  commandPhaseLine,
  commandPlaceRecordLine,
  commandRoadList,
  commandStageText,
  commandText,
} from "./flood-timeline-command-copy";
import { localizedText } from "./flood-timeline-copy";
import { parseAccessNodes } from "./flood-timeline-evacuation";
import { describeWordingFindings, findWordingViolations, REPLAY_WORDING_RULES } from "./replay-wording-lint";

const publicRoot = resolve(import.meta.dirname, "../../public");
const read = (href: string) => readFileSync(resolve(publicRoot, href.replace(/^\//, "")));
const manifest = JSON.parse(read(TIMELINE_MANIFEST_URL).toString("utf8")) as TimelineManifest;
const roads = JSON.parse(read(manifest.vectors.roads.href).toString("utf8")) as GeoCollection<unknown, RoadProps>;
const tambons = JSON.parse(read(manifest.vectors.tambons.href).toString("utf8")) as GeoCollection<AreaGeometry, TambonProps>;
const model = buildCommandModel({ manifest, roads: roads.features, tambons: tambons.features, nodes: parseAccessNodes(read(manifest.access!.nodes.href), manifest.access!) });

const LANGUAGES: readonly Language[] = ["en", "th"];
const THAI = /[฀-๿]/;
const THAI_DIGIT = /[๐-๙]/;
const EMOJI = /\p{Extended_Pictographic}/u;

/** Every `{ en, th }` entry of the copy, with a name for the failure message. */
function entries(): { name: string; text: Localized }[] {
  const blocks: Record<string, Record<string, Localized>> = { COMMAND_BANNER, COMMAND_CLOCK, COMMAND_FIGURES, COMMAND_DRAWER };
  return [
    ...Object.entries(blocks).flatMap(([block, items]) => Object.entries(items).map(([key, text]) => ({ name: `${block}.${key}`, text }))),
    ...COMMAND_LANE_ORDER.flatMap((lane) => [
      { name: `COMMAND_LANES.${lane}.tag`, text: COMMAND_LANES[lane].tag },
      { name: `COMMAND_LANES.${lane}.meaning`, text: COMMAND_LANES[lane].meaning },
    ]),
  ];
}

/** Every line the copy's functions build, from the served replay data, in one language. */
function builtLines(language: Language): string[] {
  const hourText = (hour: number | null) => (hour === null ? "" : formatHourStamp(hour, language));
  const changes = [0, 44, 45, 84, 85, 153, 200].map((hour) => changeSinceHourBefore(model, hour));
  return [
    commandBannerLine(language),
    ...[0, 84, 264].flatMap((hour) => [commandMoment(hour, language), commandMomentShort(hour, language), commandHourOf(hour, language), commandHourShort(hour, language)]),
    ...manifest.phases.map((phase) => commandPhaseLine(phase.label, 3.5, language)),
    ...[0, 0.02, 0.1, 3.4875].map((stage) => commandStageText(stage, language)),
    ...[0, 44, 84, 200].flatMap((hour) => commandFigureCells(districtFiguresAt(model, hour), language).flatMap((cell) => [cell.value, cell.caption, cell.sub ?? "", cell.meaning])),
    commandBaseText(34525, language), commandBaseText(34525, language, true),
    commandOpenItems(3, language), commandLifeAtRisk(1, language),
    commandPlaceRecordLine({ located: 12, consistent: 1, wet: 2, dry: 9 }, language),
    ...changes.map((change) => commandChangeLine(change, hourText(change.sinceHour), language).text),
    ...(["assumptions", "limits", "sources"] as const).map((list) => commandDrawerHeading(list, 4, language)),
    commandDataLine("r4", "3 Oct 2026", "3–19 Sep 2024", language),
  ];
}

describe("Command exercise copy", () => {
  it("carries the banner the owner approved on 5 Oct 2026, word for word, and its Thai rendering", () => {
    expect(commandBannerLine("en")).toBe("Exercise replay · Mae Sai, September 2024 · reconstructed, not real-time · not an official warning");
    expect(commandBannerLine("th")).toBe("ฝึกซ้อมย้อนดูเหตุการณ์ · แม่สาย กันยายน 2567 (2024) · จำลองย้อนหลัง ไม่ใช่ข้อมูลเรียลไทม์ · ไม่ใช่คำเตือนทางการ");
    expect(commandBannerParts("en")).toHaveLength(4);
    // The watermark shows both languages at once, whatever the page language.
    expect(COMMAND_BANNER.watermark.en).toBe(COMMAND_BANNER.watermark.th);
    expect(COMMAND_BANNER.watermark.en).toBe("EXERCISE · ฝึกซ้อม");
  });

  it("has an English and a Thai text for every entry, in Western digits, without emoji or stray spaces", () => {
    const all = entries();
    expect(all.length).toBeGreaterThanOrEqual(69);
    for (const { name, text } of all) {
      expect(Object.keys(text).sort(), name).toEqual(["en", "th"]);
      for (const language of LANGUAGES) {
        const value = text[language];
        expect(value, `${name} ${language}`).toBeTruthy();
        expect(value, `${name} ${language}`).toBe(value.trim());
        expect(value, `${name} ${language}`).not.toMatch(/ {2}/);
        expect(value, `${name} ${language}`).not.toMatch(THAI_DIGIT);
        expect(value, `${name} ${language}`).not.toMatch(EMOJI);
      }
      expect(text.th, name).toMatch(THAI);
      // Thai sentences carry no full stop.
      expect(text.th, name).not.toMatch(/\.$/);
      if (name !== "COMMAND_BANNER.watermark") expect(text.en, name).not.toMatch(THAI);
    }
    expect(commandText(COMMAND_CLOCK.label, "th")).toBe("เวลาในการย้อนดู");
    expect(commandText(COMMAND_CLOCK.label, "en")).toBe("Replay time");
  });

  it("passes the shared wording lint, entry by entry and line by line, in both languages", () => {
    for (const { name, text } of entries()) {
      for (const language of LANGUAGES) expect(describeWordingFindings(findWordingViolations(text[language], `${name} ${language}`)), name).toBe("");
    }
    for (const language of LANGUAGES) {
      const lines = builtLines(language);
      expect(lines.length).toBeGreaterThan(60);
      for (const line of lines) expect(describeWordingFindings(findWordingViolations(line, language)), line).toBe("");
      // The lines hold the real figures, so the check is not an empty one.
      expect(lines).toContain("~7,100");
      if (language === "th") expect(lines.filter((line) => line.length > 4 && !/^[~<0-9]/.test(line)).every((line) => THAI.test(line))).toBe(true);
    }
    // A banned claim planted in a line is still found.
    expect(findWordingViolations(`${commandBannerLine("en")} Live map`).map((finding) => finding.rule)).toEqual(["live"]);
  });

  it("says in the drawer that the Thai text was not reviewed by a native speaker, in both languages", () => {
    expect(COMMAND_DRAWER.thaiNote.en).toContain("has not been reviewed by a native speaker");
    expect(COMMAND_DRAWER.thaiNote.th).toContain("ยังไม่มีเจ้าของภาษาตรวจทาน");
    expect(COMMAND_DRAWER_NOT.map((key) => COMMAND_DRAWER[key].en.split(".")[0])).toEqual([
      "Not real-time", "Not an official warning, and not a dispatch system", "Not for operational decisions", "Not a scored case",
    ]);
    // The official routes stay named, and the terrain bias is stated in the one wording the lint allows.
    expect(COMMAND_DRAWER.notWarning.en).toContain("1784");
    expect(COMMAND_DRAWER.notWarning.th).toContain("1784");
    expect(COMMAND_DRAWER.townBias.en).toBe(REPLAY_WORDING_RULES.allow.find((item) => item.id === "dsm_bias_assumption")!.ok[0]);
    // The drawer's lists come from the replay data: their headings carry the counts, and the permitted use has a Thai rendering.
    expect(commandDrawerHeading("assumptions", manifest.assumptions.length, "en")).toBe("Assumptions (26)");
    expect(commandDrawerHeading("limits", manifest.limitations.length, "en")).toBe("Limits (4)");
    expect(commandDrawerHeading("sources", manifest.sources.length, "th")).toBe("แหล่งข้อมูลและสัญญาอนุญาต (10)");
    expect(localizedText(manifest.permitted_use!, "th").lang).toBe("th");
    expect(commandDataLine("r4", "3 Oct 2026", "3–19 Sep 2024", "en")).toBe("Data r4 · built 3 Oct 2026 · sources 3–19 Sep 2024");
    expect(commandDataLine("r4", "3 ต.ค. 2569 (2026)", "3–19 ก.ย. 2567 (2024)", "th")).toBe("ข้อมูลชุด r4 · จัดทำเมื่อ 3 ต.ค. 2569 (2026) · แหล่งข้อมูลช่วง 3–19 ก.ย. 2567 (2024)");
  });
});

describe("Command clock wording", () => {
  it("prints the replay time without a weekday, in Western digits and 24-hour time, with the Buddhist year in Thai", () => {
    expect(commandMoment(84, "en")).toBe("12 Sep 2024 · 12:00 ICT");
    expect(commandMoment(84, "th")).toBe("12 ก.ย. 2567 (2024) · 12:00 น.");
    expect(commandMomentShort(84, "en")).toBe("12 Sep 12:00 ICT");
    expect(commandMomentShort(84, "th")).toBe("12 ก.ย. 12:00 น.");
    expect(commandMoment(0, "en")).toBe("9 Sep 2024 · 00:00 ICT");
    expect(commandMoment(23, "en")).toBe("9 Sep 2024 · 23:00 ICT");
    expect(commandMoment(24, "th")).toBe("10 ก.ย. 2567 (2024) · 00:00 น.");
    // The end of the replay is the end of 19 Sep, the last day it covers; hours outside the replay are clamped.
    expect(commandMoment(264, "en")).toBe("19 Sep 2024 · 24:00 ICT");
    expect(commandMomentShort(264, "th")).toBe("19 ก.ย. 24:00 น.");
    expect(commandMoment(999, "en")).toBe("19 Sep 2024 · 24:00 ICT");
    expect(commandMoment(-5, "en")).toBe("9 Sep 2024 · 00:00 ICT");
    // The same hour as the replay's own long form, which adds the weekday.
    for (const hour of [0, 43, 84, 153, 263]) expect(formatMoment(hour / 24, "en")).toBe(`${formatMoment(hour / 24, "en").slice(0, 4)}${commandMoment(hour, "en")}`);
  });

  it("prints the replay hour, the phase and the assumed stage", () => {
    expect(commandHourOf(84, "en")).toBe("hour 84 of 264");
    expect(commandHourOf(84, "th")).toBe("ชั่วโมงที่ 84 จาก 264");
    expect(commandHourShort(84, "en")).toBe("h 84");
    expect(commandHourShort(84, "th")).toBe("ชม. 84");
    const peak = manifest.phases.find((phase) => phase.id === "peak")!;
    expect(commandPhaseLine(peak.label, 3.5, "en")).toBe("Phase: Peak · assumed river stage 3.5 m (illustrative curve)");
    expect(commandPhaseLine(peak.label, 3.5, "th")).toBe("ระยะ: ระดับสูงสุด · ระดับแม่น้ำสมมุติ 3.5 ม. (ค่าเพื่อการอธิบาย)");
    expect([0, 0.02, 0.04, 0.05, 0.1, 3.4875, 3.5].map((stage) => commandStageText(stage, "en"))).toEqual(["0 m", "<0.1 m", "<0.1 m", "0.1 m", "0.1 m", "3.5 m", "3.5 m"]);
    expect(commandStageText(Number.NaN, "th")).toBe("0 ม.");
  });
});

describe("Command figures wording", () => {
  it("prints the three model figures of replay hour 84 as the plan draws them", () => {
    const cells = commandFigureCells(districtFiguresAt(model, 84), "en");
    expect(cells.map((cell) => [cell.id, cell.value, cell.caption, cell.sub])).toEqual([
      ["lostAccess", "~7,100", "lost shelter access", "of ~34,500 in reach"],
      ["inWater", "~16,100", "residents in modelled water", null],
      ["roads", "~164 km", "roads impassable", "of 307 km"],
    ]);
    expect(cells[0].meaning).toContain("It is not a count of people stranded.");
    expect(cells[0].meaning).toContain("Counted over all residents at road nodes.");
    const thai = commandFigureCells(districtFiguresAt(model, 84), "th");
    expect(thai.map((cell) => [cell.value, cell.caption, cell.sub])).toEqual([
      ["~7,100", "สูญเสียการเข้าถึงที่พักพิง", "จาก ~34,500 คนในระยะเดิน"],
      ["~16,100", "ผู้อยู่อาศัยในน้ำตามแบบจำลอง", null],
      ["~164 กม.", "ถนนสัญจรไม่ได้", "จาก 307 กม."],
    ]);
    // Before the flood: plain zeros, never "~0".
    expect(commandFigureCells(districtFiguresAt(model, 0), "en").map((cell) => cell.value)).toEqual(["0", "0", "0 km"]);
    // With the ranked plan's sites the base changes with the count.
    expect(commandFigureCells(districtFiguresAt(model, 84, "plan"), "en")[0]).toMatchObject({ value: "~13,400", sub: "of ~24,900 in reach" });
    expect(commandBaseText(34525, "en")).toBe("of ~34,500 who had one in reach");
    expect(commandBaseText(34525, "th")).toBe("จาก ~34,500 คนที่เดินถึงที่พักพิงได้ก่อนน้ำท่วม");
  });

  it("keeps counted exercise items as plain digits", () => {
    expect([commandOpenItems(3, "en"), commandLifeAtRisk(1, "en")]).toEqual(["3 open", "1 life at risk"]);
    expect([commandOpenItems(3, "th"), commandLifeAtRisk(1, "th")]).toEqual(["เปิดอยู่ 3", "เสี่ยงต่อชีวิต 1"]);
  });

  it("states what the model shows at the located place records, from the replay data's own counts", () => {
    const counts = manifest.reported_depths!.counts.all;
    const located = manifest.reported_depths!.reports.filter((report) => report.point).length;
    const line = commandPlaceRecordLine({ located, consistent: counts.consistent, wet: counts.model_wet, dry: counts.model_dry }, "en");
    expect(line).toBe("Place records with a point: 12. At the point, the model is consistent with 1, wet at 2 and dry at 9.");
    expect(counts.consistent + counts.model_wet + counts.model_dry).toBe(located);
  });

  it("says what changed since the hour before, with the roads newly impassable as a whole", () => {
    const line = (hour: number, language: Language) => {
      const change = changeSinceHourBefore(model, hour);
      return commandChangeLine(change, change.sinceHour === null ? "" : formatHourStamp(change.sinceHour, language), language);
    };
    expect(line(0, "en")).toEqual({ lead: "Start of the replay: no hour before to compare with", figures: [], roads: null, text: "Start of the replay: no hour before to compare with" });
    expect(line(44, "en")).toEqual({
      lead: "Since 10 Sep 19:00",
      figures: ["+~1,400 lost access", "+~1,500 in water", "+~20 km impassable"],
      roads: "newly impassable: Mae Sai bypass, Phahonyothin Rd (Hwy 1) and 1 more",
      text: "Since 10 Sep 19:00: +~1,400 lost access · +~1,500 in water · +~20 km impassable · newly impassable: Mae Sai bypass, Phahonyothin Rd (Hwy 1) and 1 more",
    });
    expect(line(44, "th").text).toBe("ตั้งแต่ 10 ก.ย. 19:00 น.: +~1,400 สูญเสียการเข้าถึง · +~1,500 ในน้ำ · +~20 กม. สัญจรไม่ได้ · ถนนที่เริ่มสัญจรไม่ได้: ถนนเลี่ยงเมืองแม่สาย ถนนพหลโยธิน และอีก 1 สาย");
    // An hour later the same roads lose more length: they are no longer named as newly impassable.
    expect(line(45, "en").roads).toBeNull();
    expect(line(85, "en").text).toBe("Since 12 Sep 12:00: −~150 lost access · −~180 in water · −~4 km impassable");
    expect(line(153, "en").roads).toMatch(/^passable again: /);
    expect(line(200, "en").text).toBe("Since 17 Sep 07:00: no change in the model figures");
    expect(line(200, "th").text).toBe("ตั้งแต่ 17 ก.ย. 07:00 น.: ตัวเลขจากแบบจำลองไม่เปลี่ยน");
    // Road lists: every name when they fit, a count of the rest when they do not.
    const names = [{ name: "ถนนพหลโยธิน" }, { name: "ถนนเหมืองแดง" }, { name: "ซอย 4" }];
    expect(commandRoadList(names, "en", 3)).toBe("Phahonyothin Rd (Hwy 1), Mueang Daeng Rd, ซอย 4");
    expect(commandRoadList(names, "en", 1)).toBe("Phahonyothin Rd (Hwy 1) and 2 more");
    expect(commandRoadList(names, "th", 2)).toBe("ถนนพหลโยธิน ถนนเหมืองแดง และอีก 1 สาย");
  });
});

describe("Command lane tags", () => {
  it("names the eight lanes with a short tag and one sentence each", () => {
    expect(COMMAND_LANE_ORDER).toEqual(["model", "observed", "reported", "calibration", "scenario", "context", "exercise", "device"]);
    expect(Object.keys(COMMAND_LANES).sort()).toEqual([...COMMAND_LANE_ORDER].sort());
    expect(COMMAND_LANE_ORDER.map((lane) => commandLaneTag(lane, "en"))).toEqual(["Model", "Observed", "Reported", "Calibration", "Scenario", "Context", "Exercise · invented", "This device"]);
    expect(COMMAND_LANE_ORDER.map((lane) => commandLaneTag(lane, "th"))).toEqual(["แบบจำลอง", "สังเกตการณ์", "ตามรายงาน", "ใช้ปรับแบบจำลอง", "สถานการณ์จำลอง", "ข้อมูลประกอบ", "ฝึกซ้อม · สมมุติขึ้น", "อุปกรณ์เครื่องนี้"]);
    // A tag is short enough for a chip; its sentence is one or two short sentences.
    for (const lane of COMMAND_LANE_ORDER) {
      for (const language of LANGUAGES) {
        expect(commandLaneTag(lane, language).length, lane).toBeLessThanOrEqual(20);
        expect(commandLaneMeaning(lane, language).length, lane).toBeLessThanOrEqual(140);
      }
    }
    expect(commandLaneMeaning("model", "en")).toContain("Low confidence");
    expect(commandLaneMeaning("exercise", "en")).toContain("never counted with real reports");
    expect(COMMAND_FIGURES.exerciseTag).toEqual(COMMAND_LANES.exercise.tag);
  });

  it("maps every lane code of the replay data to a lane of the page", () => {
    const codes = Object.keys(manifest.lanes!);
    expect(codes.sort()).toEqual(Object.keys(COMMAND_LANE_OF).sort());
    for (const code of codes) expect(COMMAND_LANES[COMMAND_LANE_OF[code as keyof typeof COMMAND_LANE_OF]], code).toBeDefined();
    expect(COMMAND_LANE_OF.SCN).toBe("model");
    expect(COMMAND_LANE_OF["SCN-ENV"]).toBe("scenario");
  });
});
