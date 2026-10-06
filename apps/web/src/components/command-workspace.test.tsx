import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import areasJson from "../../public/offline-demo/mae-sai/areas.json";
import facilitiesJson from "../../public/offline-demo/mae-sai/facilities.json";

import type { FloodGuardData } from "@/lib/types";

import { buildFilteredAreaGeoJson, buildVerificationQueueExport, CommandWorkspace, offlineBrief } from "./command-workspace";
import { ResearchReportNotice } from "./research-report-notice";

describe("CommandWorkspace", () => {
  it("renders the Mae Sai map workspace, the default Planning page, with explicit research boundaries", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain('aria-label="Planning data context"');
    expect(html).toContain("Planning intelligence");
    expect(html).toContain("Planning workspace");
    // Served at /command/ (owner request of 5 Oct 2026, R19): the header's Planning link names the current page.
    expect(html).toContain('<a href="/command/" aria-current="page">Planning</a>');
    expect(html).not.toContain('aria-current="true">Planning');
    expect(html).toContain('aria-label="Use English" aria-pressed="true"');
    expect(html).toContain("Source time");
    expect(html).toContain("Confidence");
    expect(html).toContain("Historical research workspace");
    expect(html).toContain("Historical Mae Sai research archive");
    expect(html).toContain("2020 population context");
    expect(html).toContain("Data version: mae-sai-candidate-2024-09-15-v1");
    // The link to the other Planning page, the candidate overview at /command/ver2/, in the banner and in the
    // small-screen summary. It is a link before the page has read its own address too; it never points at this page.
    expect(html).toContain('<a href="/command/ver2/" data-planning-overview-link="true">Current planning overview</a>');
    expect(html).toContain('<a href="/command/ver2/">Open the current candidate overview</a>');
    expect(html).not.toContain('href="/command/archive/');
    expect(html).toContain("not accepted event-response priorities");
    expect(html).toContain("Open shared case comparisons");
    expect(html).not.toContain('href="/command/cases/"');
    expect(html).toContain("follow DDPM and local-authority instructions before action");
    expect(html).toContain("TH570903");
    expect(html).toContain("Ko Chang");
    expect(html).toContain('class="tablet-evidence-drawer open"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('data-scenario-id="baseline"');
    expect(html).toContain('aria-label="Planning evidence"');
    expect(html).toContain('role="tablist"');
    for (const label of ["Summary", "Facilities &amp; access", "Verification", "Data &amp; method"]) expect(html).toContain(`>${label}</button>`);
    expect(html).not.toContain('id="command-tab-scenario"');
    expect(html).toContain('placeholder="Name or area ID"');
    expect(html).not.toContain('aria-label="Select reporting area"');
    expect(html).not.toContain('class="rail-section class-filters"');
    expect(html).toContain('data-map-audience="staff"');
    expect(html).toContain('data-road-evidence="network_context"');
    expect(html).toContain("View map results as a list");
    expect(html).toContain('aria-label="Choose map background"');
    expect(html).toContain("Street");
    expect(html).toContain("Satellite");
    expect(html).toContain("Terrain");
    expect(html).toContain('aria-label="Map data attribution"');
    expect(html).toContain("HDX Thailand COD-AB");
    expect(html).toContain("FloodGuard");
    expect(visibleText.replaceAll(bundleJson.status.data_version, "")).not.toMatch(/\b(?:rehearsal|demo|fixture|synthetic|server-produced|FastAPI)\b/i);
    expect(html).not.toContain("can_feed_decision_layer");
    expect(html).not.toContain("processing_scope");
  });

  it("shows a notice where the research report was, with the report's address in Studio's archive", () => {
    // Owner decision of 4 Oct 2026 (R17): the GeoAI research report, with its per-subdistrict research FPPS and
    // A–E classes, is not on Command. The table is tested where it is shown, in geoai-real-panel.test.tsx.
    const html = renderToStaticMarkup(<CommandWorkspace />);
    const notice = html.slice(html.indexOf('<div class="command-geoai-layer">'), html.indexOf("<footer"));

    expect(notice).toContain('data-research-report-notice="true"');
    expect(notice).toContain("Earlier research scores and classes are not accepted event-response priorities.");
    expect(notice).toContain("The score table of the earlier Mae Sai GeoAI report, with a research score and class for each subdistrict, is not shown on Planning");
    expect(notice).toContain("kept, as historical research, only in Studio&#x27;s archive");
    expect(notice).toContain('href="/studio/archive/mae-sai-geoai/"');
    // This workspace keeps its own ranking, scores and classes (the page says "retained research comparisons"), so
    // the notice must not read as if no per-subdistrict research score were shown here: it names them as a separate
    // retained comparison whose values differ from the report's.
    expect(html).toContain("FPPS ranking");
    expect(html).toMatch(/<small>Class<!-- --> <!-- -->[A-E]<\/small>|<small>Class [A-E]<\/small>/);
    expect(notice).toContain('data-research-retained-ranking="true"');
    expect(notice).toContain("The ranking, FPPS and classes still shown on this page are a separate retained research comparison, not that report&#x27;s table.");
    expect(notice).toContain("Their values differ from the report&#x27;s, and they are not accepted priorities either.");
    expect(notice).not.toMatch(/no longer shown on Planning|per-subdistrict research score table/);
    // Where no such ranking is shown (the Planning overview), the notice does not speak of one.
    expect(renderToStaticMarkup(<ResearchReportNotice />)).not.toContain("data-research-retained-ranking");
    const thaiArchive = renderToStaticMarkup(<ResearchReportNotice language="th" retainedRanking />);
    expect(thaiArchive).toContain("ลำดับ คะแนน FPPS และชั้นของตำบลที่ยังแสดงในหน้านี้เป็นผลเปรียบเทียบงานวิจัยเดิมอีกชุดหนึ่ง");
    expect(notice).not.toContain("<table");
    expect(notice).not.toMatch(/\d+\.\d|Class [A-E]|FPPS \d/);
    expect(html).not.toMatch(/GEOAI RESEARCH|GeoAI research report|geoai-real-title|Research FPPS|Research class|Sub-district research results/);
    expect(html).not.toContain("Data version used by the ranking and area evidence above");

    const thai = renderToStaticMarkup(<ResearchReportNotice language="th" />);
    expect(thai).toContain("ไม่ใช่ลำดับความสำคัญในการรับมือเหตุการณ์ที่ได้รับการยอมรับ");
    expect(thai).toContain('href="/studio/archive/mae-sai-geoai/"');
  });

  it("keeps unavailable scenario controls clear without exposing implementation notes", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);

    expect(html).toContain("Planning scenario");
    expect(html).toContain('select disabled="" aria-label="Select scenario"');
    expect(html).not.toContain('class="scenario-delta-strip"');
    expect(html).not.toContain('id="command-tab-scenario"');
    expect(html).toContain('aria-selected="true" aria-controls="command-tab-panel"');
    expect(html).not.toContain("FastAPI");
    expect(html).not.toContain("Static bundle");
  });

  it("keeps canonical evidence state intact in downloaded briefs", () => {
    const bundle = bundleJson as unknown as FloodGuardData;
    const brief = offlineBrief(bundle.areas[0], bundle.status);

    expect(brief).toContain("Dataset mode: candidate");
    expect(brief).toContain("Operational status: non_operational");
    expect(brief).toContain("Official warning: false");
    expect(brief).toContain(`Action reason code: ${bundle.areas[0].action_reason_code}`);
    expect(brief).toContain(`Canonical reason: ${bundle.areas[0].top_reason}`);
    expect(brief).toContain("Data version: mae-sai-candidate-2024-09-15-v1");
    expect(brief).toContain("Study area: mae_sai_candidate_v1");
    expect(brief).toContain("Retained Mae Sai research comparison");
    expect(brief).toContain("not accepted event-response priorities");
    expect(brief).toContain(bundle.areas[0].assumptions[0]);
  });

  it("preserves canonical boundary and verification records in JSON exports", () => {
    const rawBundle = bundleJson as typeof bundleJson;
    const data = {
      ...rawBundle,
      evidenceContext: rawBundle.evidence_context,
      evidenceRecord: rawBundle.evidence_record,
      areaFeatures: areasJson,
      facilityFeatures: facilitiesJson,
    } as unknown as FloodGuardData;

    const filtered = buildFilteredAreaGeoJson(data, new Set(["E"]));
    expect((filtered.features[0].properties as Record<string, unknown>).candidate_status).toBe(areasJson.features[0].properties.candidate_status);
    expect(filtered.features[0].properties.fpps_0_100).toBe(data.areas[0].fpps_0_100);
    expect(filtered.evidence_context).toEqual(rawBundle.evidence_context);

    const queue = buildVerificationQueueExport(data, "TH570901");
    expect(queue.readiness_checks).toEqual(rawBundle.readiness.filter((row) => row.status !== "ready"));
    expect(queue.facility_records.length).toBeGreaterThan(0);
    expect(queue.facility_records[0].properties.verification_status).toBe("open_context_candidate");
    expect(JSON.stringify(queue)).toContain("unverified_osm_candidate");
  });
});
