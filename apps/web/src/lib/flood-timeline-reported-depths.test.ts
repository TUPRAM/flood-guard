import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type ReportedDepthReport, type ReportedDepths, type TimelineManifest } from "./flood-timeline";
import {
  groupNearbyPlaces,
  REPORTED_DEPTH_APPLIES,
  REPORTED_DEPTH_STATUSES,
  reportedDepthCountedText,
  reportedDepthMarkerTitle,
  reportedDepthSharedText,
  reportedDepthStatementTallyText,
  reportedDepthModelText,
  reportedDepthPlaces,
  reportedDepthPopup,
  reportedDepthStatusText,
  reportedDepthTallyText,
  reportedDepthText,
  reportedDepthWindow,
  shippableReportedDepths,
} from "./flood-timeline-reported-depths";
import { findWordingViolations, describeWordingFindings } from "./replay-wording-lint";

const manifest = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../public", TIMELINE_MANIFEST_URL.replace(/^\//, "")), "utf8")) as TimelineManifest;
const block = manifest.reported_depths!;
const report = (id: string) => block.reports.find((item) => item.id === id)!;
const THAI = /[฀-๿]/;
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

describe("Reported depths (news, not surveyed)", () => {
  it("are shown only with their status, their lane, the never-for-tuning rule and both languages", () => {
    expect(shippableReportedDepths(manifest)).toBe(block);
    expect(block.status).toBe("reported (anecdotal, not surveyed)");
    expect(block.lane).toBe("REP");
    const refused: [string, (value: ReportedDepths) => void][] = [
      ["another status", (value) => { value.status = "surveyed"; }],
      ["another lane", (value) => { (value as { lane: string }).lane = "OBS"; }],
      ["a use rule without the tuning rule", (value) => { value.use_rule.en = "A consistency check, never a validation."; }],
      ["a use rule that does not deny validation", (value) => { value.use_rule.en = "A consistency check; never used to tune the model."; }],
      ["a report without its Thai paraphrase", (value) => { value.reports[0].depth.statement.th = ""; }],
      ["a report with a broken point", (value) => { (value.reports[0] as { point: unknown }).point = { lat: "north" }; }],
      ["an unknown outcome", (value) => { (value.reports[0] as { consistency: string }).consistency = "validated"; }],
      ["counts without a row", (value) => { delete (value.counts as Partial<ReportedDepths["counts"]>).qualitative; }],
      ["counts without the model-wet outcome", (value) => { delete (value.counts.all as Partial<ReportedDepths["counts"]["all"]>).model_wet; }],
      ["no per-statement counts", (value) => { delete (value as Partial<ReportedDepths>).counts_by_statement; }],
      ["no record of what was counted", (value) => { delete (value as Partial<ReportedDepths>).counted; }],
      ["assumptions without their Thai lines", (value) => { value.assumptions.th = value.assumptions.th.slice(1); }],
      ["a place record without its statement", (value) => { (value.reports[0] as { statement_id?: string }).statement_id = ""; }],
    ];
    for (const [name, change] of refused) {
      const broken = clone(block);
      change(broken);
      expect(shippableReportedDepths({ reported_depths: broken }), name).toBeNull();
    }
    expect(shippableReportedDepths({})).toBeNull();
    expect(shippableReportedDepths(null)).toBeNull();
  });

  it("puts every located report on the map, one marker per point, and nothing without a point", () => {
    const located = block.reports.filter((item) => item.point);
    expect(located.map((item) => item.id)).toEqual(["ms-c2-01", "ms-c2-02", "ms-c2-07", "ms-c2-08", "ms-c2-09", "ms-c2-12", "ms-c2-14", "ms-c2-15",
      "ms-c2-18", "ms-c2-19", "ms-c2-20", "ms-c2-22"]);
    expect(located.every((item) => item.location_confidence !== "low")).toBe(true);
    expect(block.reports.filter((item) => !item.point).every((item) => item.location_confidence === "low" && item.model === null)).toBe(true);
    const places = reportedDepthPlaces(block);
    // Sai Lom Joy (two reports), Mai Lung Khon (two) and Mueang Daeng (two) share a point: nine markers.
    expect(places).toHaveLength(9);
    expect(places.map((place) => place.reports.map((item) => item.id).join("+"))).toEqual([
      "ms-c2-01+ms-c2-02", "ms-c2-07", "ms-c2-08+ms-c2-14", "ms-c2-09+ms-c2-15", "ms-c2-12", "ms-c2-18", "ms-c2-19", "ms-c2-20", "ms-c2-22"]);
    expect(reportedDepthMarkerTitle(places[0], "en")).toBe("Reported depth (news, not surveyed): Sai Lom Joy border market · Sai Lom Joy border market (Mae Sai trading area) (2 place records)");
    expect(reportedDepthMarkerTitle(places[0], "th")).toBe("ความลึกตามรายงานข่าว (ไม่ได้สำรวจ): ตลาดสายลมจอย · ตลาดสายลมจอย ย่านการค้าในเมืองแม่สาย (2 รายการ)");
  });

  it("merges places whose markers would overlap on screen, so every marker can be hit", () => {
    // Screen points in place order: the second lies 12 px from the first, the third 31 px, the fourth 29 px from the third.
    expect(groupNearbyPlaces([{ x: 100, y: 100 }, { x: 110, y: 107 }, { x: 131, y: 100 }, { x: 131, y: 129 }], 30)).toEqual([[0, 1], [2, 3]]);
    // A place joins the first group whose first place is within the radius (no chaining across the map).
    expect(groupNearbyPlaces([{ x: 0, y: 0 }, { x: 25, y: 0 }, { x: 50, y: 0 }, { x: 75, y: 0 }], 30)).toEqual([[0, 1], [2, 3]]);
    expect(groupNearbyPlaces([{ x: 0, y: 0 }, { x: 0, y: 30 }], 30)).toEqual([[0, 1]]);
    expect(groupNearbyPlaces([{ x: 0, y: 0 }, { x: 0, y: 30.5 }], 30)).toEqual([[0], [1]]);
    expect(groupNearbyPlaces([], 30)).toEqual([]);
    // Every located record sits in exactly one group, whatever the zoom.
    const places = reportedDepthPlaces(block);
    for (const scale of [1, 400, 4000, 40000]) {
      const groups = groupNearbyPlaces(places.map((place) => ({ x: place.lon * scale, y: -place.lat * scale })), 30);
      const ids = groups.flatMap((members) => members.flatMap((index) => places[index].reports.map((item) => item.id)));
      expect(ids.sort(), `scale ${scale}`).toEqual(block.reports.filter((item) => item.point).map((item) => item.id).sort());
    }
    expect(reportedDepthMarkerTitle({ reports: [...places[0].reports, ...places[1].reports] }, "en")).toBe(
      "Reported depth (news, not surveyed): Sai Lom Joy border market · Sai Lom Joy border market (Mae Sai trading area) · Ko Sai community (3 place records)");
  });

  it("keeps a lower bound, a range and a class apart, and never turns a body or storey reference into a number", () => {
    expect(reportedDepthText(report("ms-c2-01"), block, "en")).toBe("more than 1 m (lower bound)");
    expect(reportedDepthText(report("ms-c2-07"), block, "th")).toBe("ลึกเกิน 1.5 ม. (ค่าขั้นต่ำ)");
    expect(reportedDepthText(report("ms-c2-14"), block, "en")).toBe("2–3 m in places (lower bound 2 m)");
    expect(reportedDepthText(report("ms-c2-14"), block, "th")).toBe("บางจุด 2–3 ม. (ค่าขั้นต่ำ 2 ม.)");
    expect(reportedDepthText(report("ms-c2-12"), block, "en")).toBe("neck-deep (no number given)");
    expect(reportedDepthText(report("ms-c2-19"), block, "th")).toBe("สูงเกินศีรษะ (ไม่ระบุตัวเลข)");
    for (const item of block.reports.filter((entry) => entry.depth.kind === "class")) {
      expect(reportedDepthText(item, block, "en"), item.id).not.toMatch(/[0-9] ?m\b/);
    }
  });

  it("gives each report its time window in local time, in both languages", () => {
    expect(reportedDepthWindow(report("ms-c2-01"), "en")).toBe("10 Sep 00:00–05:32 ICT");
    expect(reportedDepthWindow(report("ms-c2-01"), "th")).toBe("10 ก.ย. 00:00–05:32 น.");
    expect(reportedDepthWindow(report("ms-c2-18"), "en")).toBe("10 Sep 18:00 – 11 Sep 01:23 ICT");
    expect(reportedDepthWindow(report("ms-c2-24"), "en")).toBeNull();
    // Buddhist-era years always carry the CE year.
    for (const item of block.reports) {
      const years = item.time.text.th.match(/25[67]\d(?! \(20\d\d\))/g);
      expect(years, item.id).toBeNull();
    }
  });

  it("says what the model has at the point over the window, and why a report is not compared", () => {
    const dry = reportedDepthModelText(report("ms-c2-01"), block, "en");
    expect(dry[0]).toBe("Model at this point, 10 Sep 00:00–05:32 ICT: dry (assumed river level up to 0.05 m, at 10 Sep 05:32 ICT).");
    expect(dry[1]).toMatch(/^At the modelled peak \(assumed river level 3\.5 m\): 0\.85 m; first wet 11 Sep 05:00 ICT; the point is 2\.64 m above its channel\.$/);
    expect(dry[2]).toMatch(/^Sensitivity: within 150 m of the point the deepest modelled water in that window is 0\.00 m\.$/);
    const wet = reportedDepthModelText(report("ms-c2-15"), block, "en");
    expect(wet[0]).toMatch(/: up to 2\.53 m deep \(assumed river level up to 2\.83 m, at 11 Sep 06:45 ICT\)\.$/);
    expect(reportedDepthModelText(report("ms-c2-07"), block, "en").some((line) => /^Read \d+ m from the point, outside the mapped river channel\.$/.test(line))).toBe(true);
    expect(reportedDepthModelText(report("ms-c2-18"), block, "en")[1]).toContain("the point is above the highest level the model encodes");
    expect(reportedDepthModelText(report("ms-c2-04"), block, "en")).toEqual(["Not compared with the model: the location confidence is low, so the report has no point on the map."]);
    expect(reportedDepthModelText(report("ms-c2-04"), block, "th")[0]).toMatch(THAI);
    expect(reportedDepthStatusText(report("ms-c2-15"), "en")).toBe("consistent: the model reaches the reported lower bound");
    // A storey or body reference is wet or dry only: never "consistent", even beside a body reference (Piyaphon, chest-deep, 0.78 m).
    expect(reportedDepthStatusText(report("ms-c2-22"), "en")).toBe("model wet: the model has water here over the report's time window; a storey or body reference has no number, so no depth is compared");
    expect(reportedDepthStatusText(report("ms-c2-19"), "th")).toMatch(/^แบบจำลองมีน้ำ: /);
    expect(reportedDepthStatusText(report("ms-c2-01"), "th")).toBe("แบบจำลองไม่มีน้ำที่จุดนี้ในช่วงเวลาของรายงาน");
  });

  it("builds each popup from the place, the paraphrase, the time, the location confidence, the model and the source link", () => {
    for (const language of ["en", "th"] as const) {
      for (const item of block.reports.filter((entry) => entry.point)) {
        const { lines, link } = reportedDepthPopup(item, block, language);
        const text = lines.map((line) => line.text).join("\n");
        expect(lines[0]).toEqual({ text: item.place[language], tone: "title" });
        expect(text).toContain(item.depth.statement[language]);
        expect(text).toContain(item.time.text[language]);
        expect(text).toContain(language === "th" ? "ความเชื่อมั่น" : "confidence");
        expect(link.href).toBe(item.source.url);
        expect(link.title).toBe(item.source.title);
        expect(link.text.startsWith(item.source.publisher)).toBe(true);
        if (language === "th") {
          expect(lines.filter((line) => !line.lang).every((line) => THAI.test(line.text)), item.id).toBe(true);
          expect(link.text).toMatch(/2567 \(2024\)/);
        }
        // Never validation, never confirmed: the popup is linted like the rest of the replay.
        expect(describeWordingFindings(findWordingViolations(text, `popup ${item.id} ${language}`))).toBe("");
        expect(text).not.toMatch(/confirm|validat|ยืนยันแล้ว/i);
      }
    }
  });

  it("counts every place record once per row and each statement once, and the counts match the outcomes", () => {
    for (const basis of ["numeric", "qualitative"] as const) {
      for (const status of REPORTED_DEPTH_STATUSES) {
        const tallied = block.reports.filter((item) => item.depth.basis === basis && item.consistency === status).length;
        expect(block.counts[basis][status], `${basis} ${status}`).toBe(tallied);
        // A group never has an outcome it cannot have: the consistent count of all records holds numbers only.
        if (!REPORTED_DEPTH_APPLIES[basis].includes(status)) expect(tallied, `${basis} ${status}`).toBe(0);
      }
    }
    expect(REPORTED_DEPTH_STATUSES.reduce((sum, status) => sum + block.counts.all[status], 0)).toBe(block.reports.length);
    expect(reportedDepthTallyText(block.counts.all, "en")).toBe("1 consistent, 0 model shallower, 2 model wet (depth not compared), 9 model dry, 9 not comparable");
    expect(reportedDepthTallyText(block.counts.all, "th")).toBe("สอดคล้อง 1 · แบบจำลองตื้นกว่า 0 · แบบจำลองมีน้ำ (ไม่ได้เทียบความลึก) 2 · แบบจำลองแห้ง 9 · เทียบไม่ได้ 9");
    // A report's outcome follows from its own figures.
    const outcome = (item: ReportedDepthReport) => {
      if (!item.model) return "not_comparable";
      if (item.model.depth_m <= 0) return "model_dry";
      if (item.depth.basis === "qualitative") return "model_wet";
      return item.model.depth_m >= (item.depth.lower_bound_m ?? Infinity) ? "consistent" : "model_shallower";
    };
    for (const item of block.reports) expect(item.consistency, item.id).toBe(outcome(item));
    // 21 place records from 17 statements in 14 articles; counted once per statement, a statement whose places differ is mixed.
    const statements = new Map<string, Set<string>>();
    for (const item of block.reports) statements.set(item.statement_id, (statements.get(item.statement_id) ?? new Set()).add(item.consistency));
    expect(block.counted).toEqual({ place_records: 21, statements: statements.size, articles: new Set(block.reports.map((item) => item.source.url)).size });
    expect([block.counted.statements, block.counted.articles]).toEqual([17, 14]);
    const byStatement = Object.fromEntries([...REPORTED_DEPTH_STATUSES, "mixed"].map((key) => [key, 0])) as Record<string, number>;
    for (const found of statements.values()) byStatement[found.size === 1 ? [...found][0] : "mixed"] += 1;
    expect(block.counts_by_statement).toEqual(byStatement);
    expect(reportedDepthCountedText(block.counted, "en")).toBe("21 place records from 17 statements in 14 news articles");
    expect(reportedDepthStatementTallyText(block.counts_by_statement, "en")).toBe(
      "0 consistent, 0 model shallower, 2 model wet (depth not compared), 6 model dry, 8 not comparable, 1 with different outcomes at its places");
    expect(reportedDepthSharedText(block, "en")).toEqual([
      "PPTV HD36, 10 Sep 2024: Ko Sai community, Mai Lung Khon community, Mueang Daeng community (model dry at each)",
      "Thai PBS, 11 Sep 2024: Mai Lung Khon market community, Mueang Daeng community, Pha Mak Khwai community (model dry, consistent, not comparable)",
    ]);
    for (const line of reportedDepthSharedText(block, "th")) expect(line).toMatch(/2567 \(2024\)/);
  });

  it("carries the use rule, the comparison rule and the likely causes in both languages, without a verdict", () => {
    for (const text of [block.use_rule, block.comparison_rule, block.tolerance_rule, block.confidence_reason, block.label, ...block.likely_causes.map((cause) => cause.text),
      ...block.assumptions.en.map((en, index) => ({ en, th: block.assumptions.th[index] }))]) {
      expect(text.en.length).toBeGreaterThan(0);
      expect(text.th).toMatch(THAI);
      expect(describeWordingFindings([...findWordingViolations(text.en), ...findWordingViolations(text.th)])).toBe("");
    }
    expect(block.use_rule.en).toContain("never a validation");
    expect(block.use_rule.en).toContain("never used to tune the model");
    for (const cause of block.likely_causes) expect(cause.text.en).not.toMatch(/wrong|too (low|high|shallow|deep)|validat|confirm/i);
    // The causes state the records' own counts: two points above the encoded range, five of seven located numbers early.
    const located = block.reports.filter((item) => item.model);
    const above = new Set(located.filter((item) => item.model!.height_above_channel_m === null).map((item) => `${item.point!.lat},${item.point!.lon}`));
    expect(above.size).toBe(2);
    const cause = (id: string) => block.likely_causes.find((item) => item.id === id)!;
    expect(cause("surface_model").text.en).toContain(`and ${above.size} sit above the highest level the model encodes`);
    const early = located.filter((item) => item.model!.window_max_stage_m <= 0.1);
    expect(cause("timing").text.en).toContain(`${early.filter((item) => item.depth.basis === "numeric").length} of the ${located.filter((item) => item.depth.basis === "numeric").length} located numbers`);
    expect(cause("timing").figures).toMatchObject({ located_numbers: 7, located_numbers_before_rise: 5, before_rise_model_dry: 6 });
    // The shared-statement rule is among the assumptions.
    expect(block.assumptions.en.some((line) => line.includes("recorded once per community"))).toBe(true);
  });
});
