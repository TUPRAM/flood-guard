import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { PublicReportPage } from "@/components/public-report-page";
import {
  PUBLIC_REPORT_LIMIT,
  PUBLIC_REPORT_STORAGE_KEY,
  createPublicReport,
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
      category: "road",
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
        category: "drain",
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
      category: "drain",
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
    }));

    expect(html).toContain('class="public-report-page"');
    expect(html).toContain('type="file"');
    expect(html).toContain('capture="environment"');
    expect(html.match(/type="radio"/gu)).toHaveLength(8);
    expect(html).toContain("<fieldset");
    expect(html).toContain("Mae Sai");
    expect(html).toContain("This report stays on your device");
    expect(html).not.toMatch(/real[- ]time|verified|authority received|responders notified/iu);
  });
});
