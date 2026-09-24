import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { GenerationTimes } from "./generation-times";

describe("case generation provenance", () => {
  it("labels a source analysis and a later release separately in English", () => {
    const html = renderToStaticMarkup(<GenerationTimes sourceAnalysisGeneratedAt="2026-09-22T06:00:00Z" releaseGeneratedAt="2026-09-23T12:00:00Z" th={false} />);
    expect(html).toContain('data-source-analysis-generated-at="2026-09-22T06:00:00Z"');
    expect(html).toContain('data-package-release-generated-at="2026-09-23T12:00:00Z"');
    expect(html).toContain("Source analysis generated");
    expect(html).toContain("Package release generated");
    expect(html).toContain('<time dateTime="2026-09-22T06:00:00Z">');
    expect(html).toContain('<time dateTime="2026-09-23T12:00:00Z">');
  });

  it("labels both times in Thai and leaves absent source analysis unavailable", () => {
    const html = renderToStaticMarkup(<GenerationTimes sourceAnalysisGeneratedAt={null} releaseGeneratedAt="2026-09-23T12:00:00Z" th />);
    expect(html).toContain('data-source-analysis-generated-at="unavailable"');
    expect(html).toContain("สร้างผลวิเคราะห์ต้นทางเมื่อ");
    expect(html).toContain("ยังไม่มีผลวิเคราะห์ต้นทาง");
    expect(html).toContain("สร้างแพ็กเกจเผยแพร่เมื่อ");
    expect(html).not.toContain('<time dateTime="unavailable">');
  });
});
