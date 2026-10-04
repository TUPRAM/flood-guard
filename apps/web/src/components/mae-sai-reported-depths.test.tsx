import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type TimelineManifest } from "@/lib/flood-timeline";
import { describeWordingFindings, findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import { SourcesPanel, TimelineLegend } from "./mae-sai-flood-timeline";
import { REPORTED_DEPTH_ICON, REPORTED_DEPTH_ICON_BOX, ReportedDepthLegend, reportedDepthIconHtml, ReportedDepthsSources } from "./mae-sai-reported-depths";

const manifest = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../public", TIMELINE_MANIFEST_URL.replace(/^\//, "")), "utf8")) as TimelineManifest;
const block = manifest.reported_depths!;
const text = (html: string) => visibleText(html).replace(/\s+/g, " ");
const THAI = /[฀-๿]/;

describe("Reported depths on the page", () => {
  it("adds a small table of the consistency counts to the Sources panel, in English", () => {
    const html = renderToStaticMarkup(<ReportedDepthsSources block={block} language="en" />);
    const plain = text(html);
    expect(plain).toContain("Reported depths (news, not surveyed)");
    expect(plain).toContain("Status: reported (anecdotal, not surveyed).");
    expect(plain).toContain("21 place records from 17 statements in 14 news articles of 10–13 Sep 2024 give a depth at a named place.");
    expect(plain).toContain("A statement that names several communities is recorded once per community");
    expect(plain).toContain("12 records have a point on the map (9 points; location confidence medium or high)");
    expect(plain).not.toMatch(/\d+ news reports/);
    expect(plain).toContain("which is off until you turn it on");
    expect(plain).toContain("A consistency check of anecdotal reports, never a validation");
    expect(plain).toContain("The reports are never used to tune the model");
    // Outcomes as rows and three count columns (numbers, storey or body references, all place records); a dash where a
    // group cannot have the outcome, so "consistent" counts numbers only.
    const rows = [...html.matchAll(/<tr data-status="([a-z_]+)"><th scope="row">([^<]+)<\/th>((?:<td data-basis="[a-z]+"[^>]*>[^<]+<\/td>)+)<\/tr>/g)]
      .map((match) => [match[1], match[2], [...match[3].matchAll(/<td data-basis="([a-z]+)"[^>]*>([^<]+)<\/td>/g)].map((cell) => `${cell[1]}=${cell[2]}`).join(" ")]);
    expect(rows).toEqual([
      ["consistent", "Consistent", "numeric=1 qualitative=– all=1"],
      ["model_shallower", "Model shallower", "numeric=0 qualitative=– all=0"],
      ["model_wet", "Model wet (depth not compared)", "numeric=– qualitative=2 all=2"],
      ["model_dry", "Model dry", "numeric=6 qualitative=3 all=9"],
      ["not_comparable", "Not comparable", "numeric=5 qualitative=4 all=9"],
    ]);
    expect([...html.matchAll(/<th scope="col"[^>]*>([^<]+)<\/th>/g)].map((match) => match[1])).toEqual(["Outcome", "Numbers", "Storey or body references", "All place records"]);
    expect(html).toContain('aria-label="not applicable"');
    expect(plain).toContain("so the consistent count holds numbers only");
    expect(plain).toContain("Counted once per statement (17 statements): 0 consistent, 0 model shallower, 2 model wet (depth not compared), 6 model dry, 8 not comparable, 1 with different outcomes at its places.");
    expect(plain).toContain("Thai PBS, 11 Sep 2024: Mai Lung Khon market community, Mueang Daeng community, Pha Mak Khwai community (model dry, consistent, not comparable)");
    expect(html).toContain('data-testid="reported-depths-sensitivity"');
    expect(plain).toContain("All place records: 2 consistent, 3 model shallower, 4 model wet (depth not compared), 3 model dry, 9 not comparable.");
    // The data file's assumptions, the shared-statement rule among them.
    expect(html.match(/data-testid="reported-depths-assumptions"/g)).toHaveLength(1);
    expect(plain).toContain("Counts are given per place record and, separately, once per statement.");
    // The likely causes, said plainly; every report with its source link.
    expect(html.match(/data-cause="/g)).toHaveLength(4);
    expect(plain).toContain("Town ground: the 30 m surface model includes buildings and trees");
    expect(plain).toContain("and 2 sit above the highest level the model encodes");
    expect(plain).toContain("Timing: 5 of the 7 located numbers and 1 of the 5 located storey or body references");
    expect(plain).toContain("Local drainage: water came over the barrier under Friendship Bridge 1");
    expect(html.match(/data-report="ms-c2-\d\d"/g)).toHaveLength(21);
    for (const report of block.reports) expect(html).toContain(`href="${report.source.url.replace(/&/g, "&amp;")}"`);
    expect(plain).toContain("3 candidate reports were dropped by the second reader and 24 search hits were left out by rule");
    expect(describeWordingFindings(findWordingViolations(plain, "ReportedDepthsSources (en)"))).toBe("");
    expect(plain).not.toMatch(/confirm|validated|validation of/i);
  });

  it("is in Thai on the Thai page, with the CE year beside every Buddhist-era year", () => {
    const html = renderToStaticMarkup(<ReportedDepthsSources block={block} language="th" />);
    const plain = text(html);
    expect(plain).toContain("ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)");
    expect(plain).toContain("สถานะ: ตามรายงาน (คำบอกเล่า ไม่ได้สำรวจ)");
    expect(plain).toContain("21 รายการตามสถานที่ จาก 17 ข้อความใน 14 ข่าว ระหว่างวันที่ 10–13 ก.ย. 2567 (2024)");
    expect(plain).not.toMatch(/รายงานข่าว \d+ ชิ้น|รายงานทั้งหมด \d+ ฉบับ/);
    for (const header of ["สอดคล้อง", "แบบจำลองตื้นกว่า", "แบบจำลองมีน้ำ (ไม่ได้เทียบความลึก)", "แบบจำลองแห้ง", "เทียบไม่ได้", "ตัวเลข", "ทุกรายการ"]) expect(plain).toContain(header);
    for (const line of block.assumptions.th) expect(plain).toContain(line);
    expect(plain).toContain(block.use_rule.th);
    expect(plain).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    expect(plain).toContain("2567 (2024)");
    // The English page's sentences are not left untranslated (titles of Thai articles are Thai already).
    for (const sentence of ["Status: reported", "Consistent", "Likely causes", "Every place record", "Counted once", "Assumptions"]) expect(plain).not.toContain(sentence);
    expect(describeWordingFindings(findWordingViolations(plain, "ReportedDepthsSources (th)"))).toBe("");
  });

  it("sits in the Sources panel, and is absent when the manifest has no shippable block", () => {
    const html = renderToStaticMarkup(<SourcesPanel manifest={manifest} language="en" offlineCopy={null} />);
    expect(html).toContain('data-testid="reported-depths-sources"');
    expect(html).toContain('data-testid="reported-depth-counts"');
    const without = { ...manifest, reported_depths: { ...block, status: "surveyed" } } as TimelineManifest;
    expect(renderToStaticMarkup(<SourcesPanel manifest={without} language="en" offlineCopy={null} />)).not.toContain("reported-depths-sources");
    expect(renderToStaticMarkup(<SourcesPanel manifest={{ ...manifest, reported_depths: undefined }} language="th" offlineCopy={null} />)).not.toContain("reported-depths-sources");
  });

  it("has a legend entry with a marker of its own, only while the layer is on", () => {
    const on = text(renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities reportedDepths part="symbols" />));
    expect(on).toContain("Reported depth (news, not surveyed); select for the report. A number counts the place records a marker holds");
    const off = renderToStaticMarkup(<TimelineLegend language="en" unmodelledRoads unmodelledFacilities part="symbols" />);
    expect(off).not.toContain("reported-depth-legend");
    const thai = text(renderToStaticMarkup(<ReportedDepthLegend language="th" />));
    expect(thai).toMatch(THAI);
    expect(thai).toContain("ความลึกตามรายงานข่าว (ไม่ได้สำรวจ)");
    // The shared lint refuses a report "confirming" the model and a model "validated" by news, in either language.
    const rules = (value: string) => [...new Set(findWordingViolations(value).map((finding) => finding.rule))];
    expect(rules("The modelled depth is confirmed by reports")).toContain("report_confirmation");
    expect(rules("The model is validated by news")).toContain("validation_as_agreement");
    expect(rules("รายงานข่าวยืนยันความลึกของแบบจำลอง")).toContain("report_confirmation");
    // A speech bubble, unlike the shelter star, the command diamond and the rain drop.
    expect(REPORTED_DEPTH_ICON).toContain("<svg");
    expect(REPORTED_DEPTH_ICON).toContain('fill="none"');
    // A marker holding several place records shows how many; its box is 28 px, a hit target of at least 24 px.
    expect(reportedDepthIconHtml(1)).toBe(REPORTED_DEPTH_ICON);
    expect(reportedDepthIconHtml(3)).toBe(`${REPORTED_DEPTH_ICON}<b aria-hidden="true">3</b>`);
    expect(Math.min(...REPORTED_DEPTH_ICON_BOX.iconSize)).toBeGreaterThanOrEqual(24);
  });
});
