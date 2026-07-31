import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PublicReportPage } from "@/components/public-report-page";
import {
  PUBLIC_REPORT_DEPTH_MAX_CM,
  PUBLIC_REPORT_LIMIT,
  PUBLIC_REPORT_SCHEMA_VERSION,
  PUBLIC_REPORT_STORAGE_KEY,
  createPublicReport,
  publicReportDepthBand,
  parseStoredPublicReports,
  readStoredPublicReports,
  reportsForPlanningArea,
  writeStoredPublicReports,
  type PublicReport,
} from "./public-report";

const area = {
  area_id: "TH570901",
  area_name_th: "แม่สาย",
  area_name_en: "Mae Sai",
};

function report(
  id: string,
  areaId = area.area_id,
  timestamp = "2026-07-27T09:30:00.000Z",
): PublicReport {
  return createPublicReport(
    {
      area: { ...area, area_id: areaId },
      waterDepth: "knee",
      notes: "Water across one lane",
      photoAttached: true,
    },
    timestamp,
    id,
  );
}

describe("device-local public reports", () => {
  it("creates a bounded broad-area record without photo data or coordinates", () => {
    const created = createPublicReport(
      {
        area,
        waterDepth: "waist",
        notes: `  ${"n".repeat(600)}  `,
        photoAttached: true,
      },
      "2026-07-27T09:30:00.000Z",
      "public-report:abc123",
    );

    expect(created).toMatchObject({
      schema_version: "1.0",
      report_id: "public-report:abc123",
      planning_area_id: "TH570901",
      planning_area_name_th: "แม่สาย",
      planning_area_name_en: "Mae Sai",
      water_depth: "waist",
      photo_attached: true,
      storage_scope: "device_local",
    });
    expect(created.notes).toHaveLength(500);

    const serialized = JSON.stringify(created);
    expect(serialized).not.toMatch(/latitude|longitude|coordinates|filename|mime|blob|data_url/iu);
  });

  it("rejects malformed stored records while preserving valid records", () => {
    const valid = report("public-report:valid1");
    const malformed = {
      ...valid,
      report_id: "public-report:invalid1",
      water_depth: "roof",
      latitude: 20.36,
    };
    const validWithUnknownLocation = {
      ...valid,
      latitude: 20.36,
      longitude: 99.89,
    };

    expect(parseStoredPublicReports(JSON.stringify([
      malformed,
      validWithUnknownLocation,
    ]))).toEqual([valid]);
    expect(parseStoredPublicReports("{broken")).toEqual([]);
    expect(parseStoredPublicReports(JSON.stringify({ reports: [valid] }))).toEqual([]);
  });

  it("filters the feed to the selected broad planning area and orders newest first", () => {
    const older = report("public-report:older1", "TH570901", "2026-07-27T08:00:00.000Z");
    const newer = report("public-report:newer1", "TH570901", "2026-07-27T10:00:00.000Z");
    const elsewhere = report("public-report:other1", "TH570902", "2026-07-27T11:00:00.000Z");

    expect(reportsForPlanningArea([older, elsewhere, newer], "TH570901")).toEqual([
      newer,
      older,
    ]);
    expect(reportsForPlanningArea([older], "")).toEqual([]);
  });

  it("caps persisted records and tolerates unavailable browser storage", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    const reports = Array.from(
      { length: PUBLIC_REPORT_LIMIT + 4 },
      (_, index) => report(`public-report:item${String(index).padStart(3, "0")}`),
    );

    expect(() => writeStoredPublicReports(storage, reports)).not.toThrow();
    expect(JSON.parse(values.get(PUBLIC_REPORT_STORAGE_KEY) ?? "[]")).toHaveLength(
      PUBLIC_REPORT_LIMIT,
    );
    expect(readStoredPublicReports(storage)).toHaveLength(PUBLIC_REPORT_LIMIT);
    expect(readStoredPublicReports({ getItem: () => { throw new Error("blocked"); } })).toEqual([]);
    expect(() => writeStoredPublicReports({ setItem: () => { throw new Error("full"); } }, reports)).not.toThrow();
  });

  it("renders bilingual, semantic report controls without network or verification claims", () => {
    const html = renderToStaticMarkup(createElement(PublicReportPage, {
      language: "en",
      selectedArea: area,
      areas: [area],
      onSelectArea: () => {},
    }));

    expect(html).toContain('class="public-report-page"');
    expect(html).toContain('type="file"');
    expect(html).toContain('capture="environment"');
    // Depth is a continuous range now, and categories are gone, so the only
    // radios left would be any future grouped choice.
    expect(html.match(/type="radio"/gu)).toBeNull();
    expect(html).toContain('type="range"');
    expect(html).toContain('max="150"');
    expect(html).toContain('class="flood-height-stage"');
    expect(html).toContain("<fieldset");
    expect(html).toContain("Mae Sai");

    // The illustrative feed is the only place status vocabulary may appear, and
    // it must say so on screen. Everything outside it still may not imply that
    // a stored report was received, verified, or acted on.
    const exampleStart = html.indexOf('class="public-report-feed-example"');
    expect(exampleStart).toBeGreaterThan(-1);
    const example = html.slice(exampleStart);
    expect(example).toContain('data-example="true"');
    expect(example).toContain("Not real reports");
    const realContent = html.slice(0, exampleStart);
    expect(realContent).not.toMatch(
      /real[- ]time|verified|authority received|responders notified/iu,
    );
  });

  it("names the band a reported depth falls into", () => {
    expect(publicReportDepthBand(0)).toBe("ankle");
    expect(publicReportDepthBand(32)).toBe("ankle");
    expect(publicReportDepthBand(33)).toBe("knee");
    expect(publicReportDepthBand(75)).toBe("knee");
    expect(publicReportDepthBand(76)).toBe("waist");
    expect(publicReportDepthBand(115)).toBe("waist");
    expect(publicReportDepthBand(116)).toBe("chest");
    expect(publicReportDepthBand(PUBLIC_REPORT_DEPTH_MAX_CM)).toBe("chest");
    // Above the slider maximum still reads as the deepest band.
    expect(publicReportDepthBand(400)).toBe("chest");
  });

  it("keeps the reported depth in centimetres and rejects impossible values", () => {
    const saved = createPublicReport(
      { area, waterDepth: "waist", waterDepthCm: 97, photoAttached: false },
      "2026-07-28T09:00:00.000Z",
      "public-report:depth01",
    );
    expect(saved.water_depth_cm).toBe(97);

    for (const bad of [-1, 151, 12.5, Number.NaN]) {
      expect(() => createPublicReport(
        { area, waterDepth: "waist", waterDepthCm: bad, photoAttached: false },
        "2026-07-28T09:00:00.000Z",
        "public-report:depth02",
      )).toThrow();
    }
  });

  it("still loads reports saved before the depth slider existed", () => {
    const legacy = {
      schema_version: PUBLIC_REPORT_SCHEMA_VERSION,
      report_id: "public-report:legacy01",
      planning_area_id: area.area_id,
      planning_area_name_th: area.area_name_th,
      planning_area_name_en: area.area_name_en,
      water_depth: "knee",
      notes: "",
      photo_attached: false,
      created_at: "2026-07-01T09:00:00.000Z",
      storage_scope: "device_local",
    };
    const [parsed] = parseStoredPublicReports(JSON.stringify([legacy]));
    expect(parsed.water_depth).toBe("knee");
    expect(parsed.water_depth_cm).toBeUndefined();

    // A stored depth outside the allowed range drops the whole record.
    expect(parseStoredPublicReports(
      JSON.stringify([{ ...legacy, water_depth_cm: 999 }]),
    )).toHaveLength(0);
  });
});
