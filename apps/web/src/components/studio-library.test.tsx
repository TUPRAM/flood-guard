import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import archive from "../../public/studies/mae-sai-geoai/2026-07-30-r1/manifest.json";
import { HistoricalStudy } from "./historical-study";
import { StudioLibrary } from "./studio-library";

describe("separate Studio evidence homes", () => {
  it("directs visitors to each study without borrowing Mae Sai planning status or model scores", () => {
    const html = renderToStaticMarkup(<StudioLibrary />);
    for (const href of ["/studio/studies/c2s-ms-20260915/", "/studio/studies/c2s-ms-20260915/mae-sai/", "/studio/planning-evidence/", "/studio/archive/mae-sai-geoai/"]) {
      expect(html).toContain(`href="${href}"`);
    }
    expect(html).toContain("Local accuracy unmeasured");
    expect(html).not.toMatch(/IoU|evidence-context-title|mae-sai-candidate-2024-09-15-v1/);
  });

  it("explains the historical teacher score and its distinct evaluation context", () => {
    const html = renderToStaticMarkup(<HistoricalStudy />);
    expect(html).toContain("agreement with an OmniWaterMask teacher mask");
    expect(html).toContain("30 July 2026");
    expect(html).toContain("prevent a direct old-score-to-new-score improvement claim");
    expect(html).not.toContain("evidence-context-title");
    expect(html).not.toContain("Qualified Thai Reference &amp; Frozen Label Release");
  });

  it("preserves all archived bytes and points previews only at the frozen historical revision", () => {
    const publicRoot = resolve(import.meta.dirname, "../../public");
    const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
    for (const asset of [archive.report, ...archive.assets]) {
      expect(asset.href).toMatch(/^\/studies\/mae-sai-geoai\/2026-07-30-r1\//);
      const bytes = readFileSync(resolve(publicRoot, asset.href.slice(1)));
      expect(bytes.length).toBe(asset.bytes);
      expect(sha(bytes)).toBe(asset.sha256);
    }
    const report = readFileSync(resolve(publicRoot, archive.report.href.slice(1)), "utf8");
    expect(report).not.toContain('"/geoai/');
    expect(JSON.parse(report).can_feed_decision_layer).toBe(false);
    expect(archive.can_feed_decision_layer).toBe(false);
  });
});
