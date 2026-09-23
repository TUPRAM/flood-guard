import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { evidenceFixtures } from "@/lib/evidence-library.fixtures";
import { EvidenceGaugeChart, EvidenceLibrary } from "./evidence-library";

describe("EvidenceLibrary", () => {
  it("renders candidate provenance and unavailable primary scoring without a fabricated decision", () => {
    const { catalog, evidence } = evidenceFixtures();
    catalog.events.push({ id: "unpublished-event", name: "Event without a package", start: "2025-01-01", end: "2025-01-31" });
    const html = renderToStaticMarkup(<EvidenceLibrary initialCatalog={catalog} initialPackage={evidence} />);
    expect(html).toContain('id="evidence-case"');
    expect(html).toContain("Synthetic test area — Synthetic test event");
    expect(html).not.toContain("Event without a package");
    expect(html).not.toContain('id="evidence-aoi"');
    expect(html).not.toContain('id="evidence-event"');
    expect(html).toContain("Study-area evidence library");
    expect(html).toContain("Non-operational");
    expect(html).toContain("Primary FPPS: unavailable");
    expect(html).toContain("Action class: unavailable");
    expect(html).toContain("No publishable gauge series");
    expect(html).toContain("Scenario outcomes only");
    expect(html).toContain('data-source-analysis-generated-at="unavailable"');
    expect(html).toContain('data-package-release-generated-at="2026-09-21T00:00:00Z"');
    expect(html).toContain("Main-road access: unavailable as a separate qualified service result");
    expect(html).toContain("test-report.md");
    expect(html).not.toContain("/api/");
  });

  it("shows an invalid selection without substituting the initial package", () => {
    const { catalog, evidence } = evidenceFixtures();
    const html = renderToStaticMarkup(<EvidenceLibrary initialCatalog={catalog} initialPackage={evidence} initialEventId="wrong-event" />);
    expect(html).toContain("No package exists for this area/event selection");
    expect(html).not.toContain("Scenario outcomes only");
    expect(html).not.toContain("Download report");
    expect(html).toContain('<option value="" disabled="" selected="">');
  });

  it("renders separate observed gauge segments and discloses unknown timezone", () => {
    const html = renderToStaticMarkup(<EvidenceGaugeChart th={false} gauge={{ id: "synthetic-gauge", name: "Test series", units: "m MSL", timezone: null, limitations: ["Synthetic fixture"], points: [
      { time: "2025-11-20T00:00:00", value: 1 }, { time: "2025-11-20T00:10:00", value: 2 },
      { time: "2025-11-20T00:20:00", value: null }, { time: "2025-11-20T00:30:00", value: 3 }, { time: "2025-11-20T00:40:00", value: 4 },
    ] }} />);
    expect(html.match(/data-gauge-segment/g)).toHaveLength(2);
    expect(html).toContain("not confirmed");
    expect(html).toContain("Gaps are not zero");
    expect(html).toContain("not flood depth");
  });

  it("includes Thai interface wording for the gauge evidence boundary", () => {
    const html = renderToStaticMarkup(<EvidenceGaugeChart th gauge={{ id: "test", name: "Test", units: "m", timezone: null, points: [], limitations: [] }} />);
    expect(html).toContain("ไม่มีค่าตรวจวัดที่แสดงได้");
    expect(html).toContain("ไม่มีการประมาณจุดสูงสุด");
  });
});
