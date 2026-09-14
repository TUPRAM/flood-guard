import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import reportJson from "../../public/geoai/mae-sai-real.json";

import { GeoaiRealPanel } from "./geoai-real-panel";

vi.mock("react", async (importOriginal) => {
  const react = await importOriginal<typeof import("react")>();
  return { ...react, useState: vi.fn(react.useState) };
});

describe("GeoaiRealPanel evidence separation", () => {
  it("labels loaded research scores, confidence and provenance without promoting them to planning actions", () => {
    vi.mocked(useState).mockReturnValueOnce([reportJson, vi.fn()]);
    const html = renderToStaticMarkup(<GeoaiRealPanel variant="command" />);

    expect(reportJson.aggregation_status).toBe("report_only");
    expect(reportJson.can_feed_decision_layer).toBe(false);
    expect(html).toContain("Report only");
    expect(html).toContain("Research scores and classes; not action recommendations");
    expect(html).toContain("Research FPPS");
    expect(html).toContain("Research class");
    expect(html).toContain("Model confidence");
    expect(html).toContain("separate from the evidence confidence in the planning view");
    expect(html).toContain("Ko Chang</td>");
    expect(html).toMatch(/>44<\/td>/);
    expect(html).toContain('title="Build resilience">D</span>');
    expect(html).toMatch(/>medium<\/td>/);
    expect(html).toContain('href="/geoai/mae-sai-real.json"');
    expect(html).toContain("fpps_flood_anchor_v1");
    expect(html).toContain("fpps_exposure_anchor_v1");
    expect(html).toContain("2024-08-22");
    expect(html).toContain("2024-09-15");
    expect(html).not.toContain("Real data</span>");
    expect(html).not.toContain("AI drives 55%");
  });

  it("keeps the report-only boundary and confidence distinction visible in Thai", () => {
    vi.mocked(useState).mockReturnValueOnce([reportJson, vi.fn()]);
    const html = renderToStaticMarkup(<GeoaiRealPanel language="th" variant="command" />);

    expect(html).toContain("เพื่อรายงานเท่านั้น");
    expect(html).toContain("แยกจากการจัดลำดับเพื่อวางแผน");
    expect(html).toContain("ไม่ใช้กำหนดลำดับ สีแผนที่");
    expect(html).toContain("ความเชื่อมั่นแบบจำลอง");
    expect(html).toMatch(/>ปานกลาง<\/td>/);
    expect(html).toContain("ไม่ใช่ข้อเสนอการดำเนินการ");
  });
});
