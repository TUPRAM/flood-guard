import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type ReportedDepthReport, type ReportedDepths, type TimelineManifest } from "./flood-timeline";
import {
  REPORTED_DEPTH_STATUSES,
  reportedDepthMarkerTitle,
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
    expect(reportedDepthMarkerTitle(places[0], "en")).toBe("Reported depth (news, not surveyed): Sai Lom Joy border market · Sai Lom Joy border market (Mae Sai trading area) (2 reports)");
    expect(reportedDepthMarkerTitle(places[0], "th")).toBe("ความลึกตามรายงานข่าว (ไม่ได้สำรวจ): ตลาดสายลมจอย · ตลาดสายลมจอย ย่านการค้าในเมืองแม่สาย (2 รายงาน)");
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
    expect(reportedDepthStatusText(report("ms-c2-19"), "en")).toBe("consistent: the model has water here (no depth is compared)");
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

  it("counts every report once per row, and the counts match the outcomes", () => {
    for (const basis of ["numeric", "qualitative"] as const) {
      for (const status of REPORTED_DEPTH_STATUSES) {
        const tallied = block.reports.filter((item) => item.depth.basis === basis && item.consistency === status).length;
        expect(block.counts[basis][status], `${basis} ${status}`).toBe(tallied);
      }
    }
    expect(REPORTED_DEPTH_STATUSES.reduce((sum, status) => sum + block.counts.all[status], 0)).toBe(block.reports.length);
    expect(reportedDepthTallyText(block.counts.all, "en")).toBe("3 consistent, 0 model shallower, 9 model dry, 9 not comparable");
    expect(reportedDepthTallyText(block.counts.all, "th")).toBe("สอดคล้อง 3 · แบบจำลองตื้นกว่า 0 · แบบจำลองแห้ง 9 · เทียบไม่ได้ 9");
    // A report's outcome follows from its own figures.
    const outcome = (item: ReportedDepthReport) => {
      if (!item.model) return "not_comparable";
      if (item.model.depth_m <= 0) return "model_dry";
      if (item.depth.basis === "qualitative") return "consistent";
      return item.model.depth_m >= (item.depth.lower_bound_m ?? Infinity) ? "consistent" : "model_shallower";
    };
    for (const item of block.reports) expect(item.consistency, item.id).toBe(outcome(item));
  });

  it("carries the use rule, the comparison rule and the likely causes in both languages, without a verdict", () => {
    for (const text of [block.use_rule, block.comparison_rule, block.tolerance_rule, block.confidence_reason, block.label, ...block.likely_causes.map((cause) => cause.text)]) {
      expect(text.en.length).toBeGreaterThan(0);
      expect(text.th).toMatch(THAI);
      expect(describeWordingFindings([...findWordingViolations(text.en), ...findWordingViolations(text.th)])).toBe("");
    }
    expect(block.use_rule.en).toContain("never a validation");
    expect(block.use_rule.en).toContain("never used to tune the model");
    for (const cause of block.likely_causes) expect(cause.text.en).not.toMatch(/wrong|too (low|high|shallow|deep)|validat|confirm/i);
  });
});
