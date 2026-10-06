import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import catalogJson from "../../public/evidence-library/catalog.json";

import { EVIDENCE_CATALOG_URL, parseEvidenceCatalog } from "@/lib/evidence-library";

import { CASE_CATALOGUE_URL, CommandCaseNotice, CommandCaseNoticeLine, readCaseCatalogue } from "./command-case-notice";
import { CommandWorkspace } from "./command-workspace";

// The published catalogue, read as the page reads it: with the small reader, not with the evidence library's parser.
const catalog = readCaseCatalogue(catalogJson)!;
// The address the published Hat Yai brief gives its "Planning" link (apps/web/public/briefs/, "Same case").
const hatYai = `?aoi=aoi-03_hat_yai_core&event=hat_yai_2025&version=${catalog.package_version}`;
const escaped = (search: string) => search.replaceAll("&", "&amp;");

describe("CommandCaseNotice", () => {
  it("reads the names of the published cases from the catalogue the evidence library reads", () => {
    expect(CASE_CATALOGUE_URL).toBe(EVIDENCE_CATALOG_URL);
    const parsed = parseEvidenceCatalog(catalogJson);
    expect(catalog.package_version).toBe(parsed.package_version);
    expect(catalog.packages.map((item) => [item.id, item.aoi_id, item.event_id])).toEqual(parsed.packages.map((item) => [item.id, item.aoi_id, item.event_id]));
    expect(catalog.packages).toHaveLength(8);
    // Anything that is not the catalogue in its expected form gives no catalogue, and the line then names no case.
    for (const broken of [null, [], "catalog", {}, { ...catalogJson, package_version: 1 }, { ...catalogJson, aois: [{ id: "a" }] }, { ...catalogJson, packages: [{ id: "a", aoi_id: "b" }] }]) {
      expect(readCaseCatalogue(broken)).toBeNull();
    }
  });

  it("names the case of the address, says that the map does not show it, and leads to that case's planning overview", () => {
    const english = renderToStaticMarkup(<CommandCaseNoticeLine search={hatYai} language="en" catalog={catalog} />);
    expect(english).toContain('aria-label="Selected case" data-command-case-notice="aoi-03_hat_yai_core_hat_yai_2025"');
    expect(english).toContain("<strong>Selected case: Hat Yai core — Hat Yai · November 2025.</strong> This map does not show the results of that case. It shows the retained Mae Sai research comparison only.");
    expect(english).toContain(`<a href="/command/planning/${escaped(hatYai)}" data-command-case-overview-link="true">Planning overview of Hat Yai core — Hat Yai · November 2025</a>`);

    const thai = renderToStaticMarkup(<CommandCaseNoticeLine search={hatYai} language="th" catalog={catalog} />);
    expect(thai).toContain('aria-label="กรณีศึกษาที่เลือก"');
    expect(thai).toContain("<strong>กรณีศึกษาที่เลือก: หาดใหญ่ พื้นที่หลัก — หาดใหญ่ · พฤศจิกายน 2568</strong> แผนที่นี้ไม่ได้แสดงผลของกรณีศึกษานั้น แสดงเฉพาะผลเปรียบเทียบงานวิจัยแม่สายที่เก็บไว้เท่านั้น");
    expect(thai).toContain(`<a href="/command/planning/${escaped(hatYai)}" data-command-case-overview-link="true">ภาพรวมเพื่อการวางแผนของ หาดใหญ่ พื้นที่หลัก — หาดใหญ่ · พฤศจิกายน 2568</a>`);
  });

  it("says the same of the Mae Sai case: the workspace shows the retained comparison, not that case's results", () => {
    const html = renderToStaticMarkup(<CommandCaseNoticeLine search="?aoi=aoi-01_mae_sai_core&event=mae_sai_2024&service=pharmacy" language="en" catalog={catalog} />);
    expect(html).toContain("Selected case: Mae Sai core — Mae Sai · September 2024.");
    expect(html).toContain("This map does not show the results of that case.");
    // Every part of the selection goes on to the overview.
    expect(html).toContain('href="/command/planning/?aoi=aoi-01_mae_sai_core&amp;event=mae_sai_2024&amp;service=pharmacy"');
  });

  it("gives no name to a case the catalogue does not hold under this address, and still carries the address on", () => {
    for (const [search, loaded] of [
      [hatYai, null],
      ["?aoi=unknown&event=unknown", catalog],
      ["?aoi=aoi-03_hat_yai_core", catalog],
      ["?aoi=aoi-03_hat_yai_core&event=hat_yai_2025&version=another", catalog],
    ] as const) {
      const html = renderToStaticMarkup(<CommandCaseNoticeLine search={search} language="en" catalog={loaded} />);
      expect(html).toContain('data-command-case-notice="unnamed"');
      expect(html).toContain("<strong>The link that opened this page names a study case.</strong> This map does not show the results of that case.");
      expect(html).toContain(`<a href="/command/planning/${escaped(search)}" data-command-case-overview-link="true">Planning overview of that case</a>`);
      expect(html).not.toContain("Selected case:");
    }
    const thai = renderToStaticMarkup(<CommandCaseNoticeLine search="?aoi=unknown&event=unknown" language="th" catalog={catalog} />);
    expect(thai).toContain("<strong>ลิงก์ที่เปิดหน้านี้ระบุกรณีศึกษาไว้</strong> แผนที่นี้ไม่ได้แสดงผลของกรณีศึกษานั้น");
    expect(thai).toContain(">ภาพรวมเพื่อการวางแผนของกรณีศึกษานั้น</a>");
  });

  it("is absent when the address names no case, and before the page has read its address", () => {
    for (const search of ["", "?service=hospital&mode=walking", "?version=3385c9eacccd0d2d"]) {
      expect(renderToStaticMarkup(<CommandCaseNoticeLine search={search} language="en" catalog={catalog} />)).toBe("");
    }
    expect(renderToStaticMarkup(<CommandCaseNotice search={null} language="en" />)).toBe("");
    expect(renderToStaticMarkup(<CommandWorkspace />)).not.toContain("data-command-case-notice");
  });

  it("shows no score and no class", () => {
    for (const language of ["en", "th"] as const) {
      const text = renderToStaticMarkup(<CommandCaseNoticeLine search={hatYai} language={language} catalog={catalog} />).replace(/<[^>]*>/g, " ");
      expect(text).not.toMatch(/FPPS|[Cc]lass|ชั้น|ระดับ|\d+\.\d/);
    }
  });
});
