import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import archive from "../../public/geoai/mae-sai-real.json";
import { parseGeoaiResearchBundle } from "@/lib/geoai-research-bundle";
import { GeoaiRealPanel, GeoaiResearchContent } from "./geoai-real-panel";

describe("research comparator claims", () => {
  it("directs Command to the current brief without a second score table", () => {
    const html = renderToStaticMarkup(<GeoaiRealPanel variant="command" />);
    expect(html).toContain("not accepted event-response priorities");
    expect(html).toContain("/studio/brief/?aoi=aoi-01_mae_sai_core&amp;event=mae_sai_2024");
    expect(html).not.toContain("<table");
    expect(html).not.toMatch(/Real GeoAI results|REAL OBSERVED|AI drives 55%/);
  });
  it("keeps the original arithmetic in a closed, neutral archive disclosure", () => {
    const bundle = parseGeoaiResearchBundle(archive);
    const html = renderToStaticMarkup(<GeoaiResearchContent bundle={bundle} th={false} />);
    expect(html).toContain("cannot feed the decision layer");
    expect(html).toContain("Archived class");
    expect(html).toContain("no accepted ranking");
    expect(html).toContain(bundle.generated_at);
    expect(html).not.toContain(" open=");
    expect(html).not.toMatch(/class-D|aD|Protect lives/);
  });
  it("preserves the boundary in Thai and on failed loads", () => {
    const thai = renderToStaticMarkup(<GeoaiResearchContent bundle={parseGeoaiResearchBundle(archive)} th />);
    expect(thai).toContain("ไม่ได้รับอนุญาตให้ป้อนชั้นการตัดสินใจ");
    const failed = renderToStaticMarkup(<GeoaiResearchContent bundle={null} th={false} failed />);
    expect(failed).toContain("numerical results are unavailable");
    expect(failed).not.toContain("<table");
  });
});
