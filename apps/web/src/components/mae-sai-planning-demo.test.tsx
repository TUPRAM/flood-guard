import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { maeSaiCase } from "@/lib/mae-sai-case";

import { MaeSaiPlanningDemo } from "./mae-sai-planning-demo";

describe("Mae Sai historical planning case", () => {
  it("presents a traceable historical exercise without operational or local accuracy claims", () => {
    const html = renderToStaticMarkup(<MaeSaiPlanningDemo />);
    expect(html).toContain("Historical case study");
    expect(html).toContain("Low · Historical planning exercise");
    expect(html).toContain("Not an official warning or route guidance");
    expect(html).toContain("Local accuracy not measured");
    expect(html).toContain(maeSaiCase.meta.case_version);
    expect(html).toContain(maeSaiCase.meta.package_sha256);
    expect(html).toContain(maeSaiCase.meta.source_timestamp);
    expect(html).toContain("Later context does not reconstruct every condition in 2024");
    expect(html).toContain("What has not been measured");
    expect(html).toContain("Required validation next steps");
  });

  it("shows the committed Ko Chang comparison and keeps existing disadvantage separate", () => {
    const html = renderToStaticMarkup(<MaeSaiPlanningDemo />);
    const area = maeSaiCase.areas.find((item) => item.area_id === "TH570903")!;
    const scenario = maeSaiCase.scenarios.find((item) => item.scenario_id === "add_temporary_shelter")!;
    const result = scenario.areas.find((item) => item.area_id === area.area_id)!;
    expect(html).toContain(`<strong>${result.baseline_people_losing_30_min_access.toLocaleString("en")}</strong>`);
    expect(html).toContain(`<strong>${result.scenario_people_losing_30_min_access.toLocaleString("en")}</strong>`);
    expect(html).toContain("Already outside the threshold before disruption");
    expect(html).toContain("People already underserved are not counted as newly losing access");
    expect(html).toContain("not recalculated by this scenario");
    expect(html).toContain("Class E reflects low confidence, not evidence of low potential impact");
    expect(html).toContain("It is not an approved shelter");
    expect(html).toContain("no capacity or transport allocation is calculated");
    expect(html).toContain("Fewer modelled people losing access");
  });

  it("provides accessible steps, explicit form labels and no prefilled approved record", () => {
    const html = renderToStaticMarkup(<MaeSaiPlanningDemo />);
    for (const id of ["main-content", "evidence", "compare", "record"]) expect(html).toContain(`id="${id}"`);
    expect(html).toContain('aria-live="polite"');
    expect(html).toContain('value="draft" selected=""');
    expect(html).toContain("Reviewed for exercise only");
    expect(html).toContain("Records are not sent to staff");
    expect(html).toContain("Do not enter personal or sensitive information");
    expect(html).toContain("Clearing browser storage can remove these records");
    expect(html).toContain('required="" maxLength="2000"');
    expect(html).not.toContain("Export evidence · JSON");
  });

  it("labels the source-derived outline as location context rather than flood extent", () => {
    const html = renderToStaticMarkup(<MaeSaiPlanningDemo />);
    expect(html).toContain('role="img" aria-labelledby="mae-sai-map-title"');
    expect(html).toContain("with Ko Chang highlighted");
    expect(html).toContain("This is a location map, not flood extent");
    expect(html).toContain("HDX COD-AB");
  });

  it("supports Thai navigation, evidence boundaries and the review form", () => {
    const html = renderToStaticMarkup(<MaeSaiPlanningDemo defaultLanguage="th" />);
    expect(html).toContain("จากหลักฐานน้ำท่วม สู่การตัดสินใจที่อธิบายได้");
    expect(html).toContain("ไม่ใช่คำเตือนทางการหรือคำแนะนำเส้นทาง");
    expect(html).toContain("ความแม่นยำในพื้นที่ยังไม่ได้วัด");
    expect(html).toContain("ทบทวนเพื่อแบบฝึกหัดเท่านั้น");
    expect(html).toContain("สมมติฐานการวางแผน");
    expect(html).toContain('lang="en"');
  });
});
