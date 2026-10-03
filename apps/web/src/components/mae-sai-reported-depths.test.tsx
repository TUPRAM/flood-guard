import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { TIMELINE_MANIFEST_URL, type TimelineManifest } from "@/lib/flood-timeline";
import { describeWordingFindings, findWordingViolations, visibleText } from "@/lib/replay-wording-lint";
import { SourcesPanel, TimelineLegend } from "./mae-sai-flood-timeline";
import { REPORTED_DEPTH_ICON, ReportedDepthLegend, ReportedDepthsSources } from "./mae-sai-reported-depths";

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
    expect(plain).toContain("21 news reports of 10–13 Sep 2024 give a depth at a named place");
    expect(plain).toContain("12 have a point on the map (location confidence medium or high)");
    expect(plain).toContain("which is off until you turn it on");
    expect(plain).toContain("A consistency check of anecdotal reports, never a validation");
    expect(plain).toContain("The reports are never used to tune the model");
    // Rows and columns of the table: numbers and storey or body references, by outcome, and both together.
    const rows = [...html.matchAll(/<tr data-basis="([a-z]+)"><th scope="row">([^<]+)<\/th>((?:<td data-status="[a-z_]+">\d+<\/td>)+)<\/tr>/g)]
      .map((match) => [match[1], match[2], [...match[3].matchAll(/<td data-status="([a-z_]+)">(\d+)<\/td>/g)].map((cell) => `${cell[1]}=${cell[2]}`).join(" ")]);
    expect(rows).toEqual([
      ["numeric", "Numbers (lower bounds and ranges)", "consistent=1 model_shallower=0 model_dry=6 not_comparable=5"],
      ["qualitative", "Storey or body references (wet or dry only)", "consistent=2 model_shallower=0 model_dry=3 not_comparable=4"],
      ["all", "All reports", "consistent=3 model_shallower=0 model_dry=9 not_comparable=9"],
    ]);
    for (const header of ["Consistent", "Model shallower", "Model dry", "Not comparable"]) expect(plain).toContain(header);
    expect(html).toContain('data-testid="reported-depths-sensitivity"');
    expect(plain).toContain("All reports: 6 consistent, 3 model shallower, 3 model dry, 9 not comparable.");
    // The likely causes, said plainly; every report with its source link.
    expect(html.match(/data-cause="/g)).toHaveLength(4);
    expect(plain).toContain("Town ground: the 30 m surface model includes buildings and trees");
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
    expect(plain).toContain("รายงานข่าว 21 ชิ้นระหว่างวันที่ 10–13 ก.ย. 2567 (2024)");
    for (const header of ["สอดคล้อง", "แบบจำลองตื้นกว่า", "แบบจำลองแห้ง", "เทียบไม่ได้"]) expect(plain).toContain(header);
    expect(plain).toContain(block.use_rule.th);
    expect(plain).not.toMatch(/25[67]\d(?! \(20\d\d\))/);
    expect(plain).toContain("2567 (2024)");
    // The English page's sentences are not left untranslated (titles of Thai articles are Thai already).
    for (const sentence of ["Status: reported", "Consistent", "Likely causes", "Every report"]) expect(plain).not.toContain(sentence);
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
    expect(on).toContain("Reported depth (news, not surveyed); select for the report");
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
  });
});
