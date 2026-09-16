import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudyFrame } from "./c2s-study-shared";
import { HistoricalStudy } from "./historical-study";

const preference = vi.hoisted(() => ({ language: "en" as "en" | "th" }));
vi.mock("@/lib/use-language", () => ({ useLanguage: () => [preference.language, vi.fn()] }));

describe("study language and original evidence", () => {
  beforeEach(() => { preference.language = "en"; });

  it("retains the English benchmark identity and original evidence language", () => {
    const html = renderToStaticMarkup(<StudyFrame section="results"><p>Recorded evidence</p></StudyFrame>);
    expect(html).toContain("C2S-MS public benchmark");
    expect(html).toContain('lang="en"><p>Recorded evidence</p>');
  });

  it("translates the study navigation while identifying the English source results", () => {
    preference.language = "th";
    const html = renderToStaticMarkup(<StudyFrame section="results"><p>Recorded evidence</p></StudyFrame>);
    expect(html).toContain('lang="th"');
    expect(html).toContain("ผลการประเมิน");
    expect(html).toContain("ใช้เพื่อรายงานเท่านั้น");
    expect(html).toContain("หลักฐานต้นฉบับด้านล่างคงไว้เป็นภาษาอังกฤษ");
    expect(html).toContain('lang="en"><p>Recorded evidence</p>');
    expect(html).toContain('href="/studio/studies/c2s-ms-20260915/results/" aria-current="page"');
  });

  it("keeps Mae Sai accuracy unmeasured in Thai without importing a benchmark score", () => {
    preference.language = "th";
    const html = renderToStaticMarkup(<StudyFrame section="mae-sai"><p>Inference layers</p></StudyFrame>);
    expect(html).toContain("ยังไม่ได้วัดความแม่นยำในประเทศไทย");
    expect(html).toContain("ยังไม่มีข้อมูลอ้างอิงไทยที่ผ่านเกณฑ์");
    expect(html).toContain("22 ส.ค. / 15 ก.ย. ค.ศ. 2024");
    expect(html).not.toContain("IoU");
  });

  it("explains historical teacher agreement and unchanged source files in Thai", () => {
    preference.language = "th";
    const html = renderToStaticMarkup(<HistoricalStudy />);
    expect(html).toContain("ความสอดคล้องกับหน้ากากครูจาก OmniWaterMask");
    expect(html).toContain("ไม่ใช่ความแม่นยำ");
    expect(html).toContain("ไฟล์หลักฐานที่ดาวน์โหลดได้คงไว้เป็นภาษาอังกฤษ");
    expect(html).toContain('href="/studies/mae-sai-geoai/2026-07-30-r1/geoai_metrics.json"');
  });
});
