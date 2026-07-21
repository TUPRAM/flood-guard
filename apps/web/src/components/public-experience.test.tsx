import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PublicExperience } from "./public-experience";

describe("PublicExperience", () => {
  it("puts household planning and official help ahead of technical evidence", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    const boundaryBanner = html.indexOf("public-boundary-banner");
    const readinessCard = html.indexOf("public-readiness-card");
    const planAction = html.indexOf('data-action="build-household-plan"');
    const quickActions = html.indexOf("public-quick-actions");
    const officialHelp = html.indexOf('data-testid="public-official-help"');
    const detailedEvidence = html.indexOf("public-evidence-details");

    expect(boundaryBanner).toBeGreaterThan(-1);
    expect(readinessCard).toBeGreaterThan(boundaryBanner);
    expect(planAction).toBeGreaterThan(readinessCard);
    expect(quickActions).toBeGreaterThan(planAction);
    expect(officialHelp).toBeGreaterThan(quickActions);
    expect(detailedEvidence).toBeGreaterThan(officialHelp);
    expect(html).toContain("ข้อมูลเพื่อการเตรียมพร้อม");
    expect(html).toContain("ข้อมูลการวางแผนแม่สาย");
    expect(html).toContain("กำลังตรวจสอบข้อมูลล่าสุด");
    expect(html).toContain("เวลาข้อมูล");
    expect(html).toContain("ความเชื่อมั่น");
    expect(html).toContain("ความช่วยเหลือและประกาศทางการ");
    expect(html).toContain("public-official-help");
    expect(html).toContain("แม่สาย");
    expect(html).not.toMatch(/rehearsal|demo|fixture|candidate|synthetic|non-operational/iu);
  });

  it("ships a Thai-first document surface with persistent navigation semantics", () => {
    const html = renderToStaticMarkup(<PublicExperience />);

    expect(html).toContain('<main class="public-page" lang="th">');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain('aria-controls="public-active-panel"');
    expect(html.match(/id="public-tab-(?:home|map|shelters|prepare|data)"/g)).toHaveLength(5);
    for (const tab of ["home", "map", "shelters", "prepare", "data"]) {
      expect(html).toContain(`id="public-tab-${tab}"`);
    }
  });
});
