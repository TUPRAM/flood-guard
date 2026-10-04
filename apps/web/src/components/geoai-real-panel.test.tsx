import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import reportJson from "../../public/geoai/mae-sai-real.json";
import { parseGeoaiResearchBundle } from "@/lib/geoai-research-bundle";

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

  it("has a style for every class it uses, the five research class badges included", () => {
    // A class missing from the stylesheet is not a type error and not a failed render: the page shows
    // class="undefined" and an unstyled badge. The stylesheet and the component were once merged apart this way.
    const source = readFileSync(resolve(import.meta.dirname, "geoai-real-panel.tsx"), "utf8");
    const stylesheet = readFileSync(resolve(import.meta.dirname, "geoai-real-panel.module.css"), "utf8");
    const used = new Set([...source.matchAll(/styles\.([A-Za-z0-9_]+)/g)].map((match) => match[1]));
    expect(source).toContain("styles[`a${s.action}`]");
    for (const letter of "ABCDE") used.add(`a${letter}`);
    const styled = new Set([...stylesheet.matchAll(/\.([A-Za-z_][A-Za-z0-9_-]*)/g)].map((match) => match[1]));

    expect(used.size).toBeGreaterThan(20);
    expect([...used].filter((name) => !styled.has(name))).toEqual([]);
  });

  it("loads the report through the parser that refuses one without its report-only statements", () => {
    const source = readFileSync(resolve(import.meta.dirname, "geoai-real-panel.tsx"), "utf8");

    expect(source).toContain("parseGeoaiResearchBundle(JSON.parse(");
    expect(source).not.toMatch(/JSON\.parse\([^)]*\)\) as GeoaiRealBundle/);
    expect(parseGeoaiResearchBundle(reportJson)).toBe(reportJson);
    expect(() => parseGeoaiResearchBundle({ ...reportJson, can_feed_decision_layer: true })).toThrow(/provenance/);
  });
});
