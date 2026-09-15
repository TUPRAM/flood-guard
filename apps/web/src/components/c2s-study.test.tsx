import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { StudySummary } from "@/lib/study-report-types";
import { StudyData, StudyResults } from "./c2s-study-benchmark";
import { StudyMaeSai } from "./c2s-study-inference";
import { ConfusionTable, isStudyVisualUrl, num, STUDY_ASSETS, StudyFigure, StudyFrame, studyVisualRequestUrl, Unavailable } from "./c2s-study-shared";

const summary = JSON.parse(readFileSync(resolve("public/studies/c2s-ms-20260915/r1/summary.json"), "utf8")) as StudySummary;

describe("C2S study presentation and evidence separation", () => {
  it("binds benchmark navigation to a separate study without the planning status context", () => {
    const html = renderToStaticMarkup(<StudyFrame section="results"><p>Recorded benchmark</p></StudyFrame>);
    expect(html).toContain("C2S-MS public benchmark");
    expect(html).toContain("Australia · Nigeria · Pakistan");
    expect(html).toContain("c2s-ms-20260915 · r1");
    expect(html).toContain("/studio/planning-evidence");
    expect(html).toContain("/command");
    expect(html).not.toContain("mae-sai-candidate-2024-09-15-v1");
    expect(html).not.toContain("status-bar");
  });

  it("shows every frozen event and role counts, with acquisition timing and source links", () => {
    const html = renderToStaticMarkup(<StudyData report={summary}/>);
    for (const event of summary.events) expect(html).toContain(event.event_id);
    for (const role of summary.roles) expect(html).toContain(String(role.n_chips));
    expect(summary.events).toHaveLength(18);
    expect(html).toContain("not an official publisher split or a chronological forecast test");
    expect(html).toContain("WorldCover");
    expect(html).toContain("ground truth");
  });

  it("renders recorded full-valid scores and confusion counts without inventing unavailable values", () => {
    const html = renderToStaticMarkup(<StudyResults report={summary}/>);
    const xgb = summary.benchmarks.find(b => b.id === "context/xgboost")!;
    expect(html).toContain(xgb.calibrated.full_valid.iou!.toFixed(4));
    expect(html).toContain(xgb.calibrated.full_valid.true_positive.toLocaleString("en-US"));
    expect(html).toContain("24,452,094");
    expect(html).toContain("27,693,531");
    expect(html).toContain("Eleven context test chips");
    expect(html).toContain("no confidence interval");
    expect(num(null)).toBe("Unavailable");
    expect(num(Number.NaN)).toBe("Unavailable");
    expect(num(0)).toBe("0.0000");
  });

  it("explains errors using the actual independent reference counts", () => {
    const metrics = summary.benchmarks.find(b => b.id === "context/xgboost")!.calibrated.full_valid;
    const html = renderToStaticMarkup(<ConfusionTable metrics={metrics}/>);
    expect(html).toContain("10,455,894");
    expect(html).toContain("839,297");
    expect(html).toContain("777,871");
    expect(html).toContain("False negative · missed water");
  });

  it("gives Mae Sai a separate header with no benchmark score presented as local accuracy", () => {
    const html = renderToStaticMarkup(<StudyFrame section="mae-sai"><StudyMaeSai report={summary}/></StudyFrame>);
    expect(html).toContain("No qualified reference mask");
    expect(html).toContain("local accuracy has not been measured");
    expect(html).toContain("residual extent");
    expect(html).not.toContain("0.8661");
    expect(html).not.toContain("Human water reference</strong>");
  });

  it("does not substitute historical or remote images for a missing study preview", () => {
    expect(isStudyVisualUrl(`${STUDY_ASSETS}visuals/chips/example/error.png`)).toBe(true);
    for (const url of ["/geoai/B_water_mask.png", "https://example.com/image.png", `${STUDY_ASSETS}visuals/../old.png`, `${STUDY_ASSETS}visuals/%2e%2e/old.png`]) {
      expect(isStudyVisualUrl(url)).toBe(false);
      const html = renderToStaticMarkup(<StudyFigure layer={{url}} title="Recorded prediction"/>);
      expect(html).not.toContain("<img");
      expect(html).toContain("No replacement image");
    }
    expect(renderToStaticMarkup(<Unavailable reason="Hash mismatch"/>)).toContain("does not substitute data from another study");
  });

  it("keys image requests by source checksum and refuses an incompatible overlay", () => {
    const layer = {url:`${STUDY_ASSETS}visuals/mae-sai/context/unet/probability.png`,sha256:"a".repeat(64),width:212,height:256};
    expect(studyVisualRequestUrl(layer)).toBe(`${layer.url}?sha256=${"a".repeat(64)}`);
    const html = renderToStaticMarkup(<StudyFigure layer={layer} title="Water probability" overlay={{url:`${STUDY_ASSETS}visuals/mae-sai/context/unet/abstention.png`,width:256,height:256}}/>);
    expect(html).toContain("Abstention overlay unavailable or incompatible");
    expect(html).not.toContain("Abstention overlay applied");
    expect(html).toContain("sha256=");
  });
});
