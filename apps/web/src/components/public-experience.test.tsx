import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PublicExperience } from "./public-experience";

describe("PublicExperience", () => {
  it("puts household planning and official help ahead of technical evidence", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    const planAction = html.indexOf('data-action="build-household-plan"');
    const officialHelp = html.indexOf('data-testid="public-official-help"');
    const detailedEvidence = html.indexOf("public-evidence-details");

    expect(planAction).toBeGreaterThan(-1);
    expect(officialHelp).toBeGreaterThan(planAction);
    expect(detailedEvidence).toBeGreaterThan(officialHelp);
    expect(html).toContain("FloodGuard ไม่ใช่ประกาศทางการ");
    expect(html).toContain("ความช่วยเหลือและประกาศทางการ");
  });

  it("ships a Thai-first document surface with persistent navigation semantics", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    expect(html).toContain('<main class="public-page" lang="th">');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-controls="public-active-panel"');
  });
});
