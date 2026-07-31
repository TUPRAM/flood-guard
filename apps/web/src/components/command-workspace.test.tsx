import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import bundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import areasJson from "../../public/offline-demo/mae-sai/areas.json";
import facilitiesJson from "../../public/offline-demo/mae-sai/facilities.json";

import type { FloodGuardData } from "@/lib/types";

import { buildFilteredAreaGeoJson, buildVerificationQueueExport, CommandWorkspace, offlineBrief } from "./command-workspace";

describe("CommandWorkspace", () => {
  it("renders the Mae Sai planning workspace with final-product context and safeguards", () => {
    const html = renderToStaticMarkup(<CommandWorkspace />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain('aria-label="Planning data context"');
    expect(html).toContain("Planning intelligence");
    expect(html).toContain("Planning workspace");
    expect(html).toContain('<a class="active" href="/command/">Planning</a>');
    expect(html).not.toContain('<a class="active" href="/command/">Command</a>');
    expect(html).toContain("Source time");
    expect(html).toContain("Confidence");
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
    expect(visibleText).not.toMatch(/\b(?:rehearsal|demo|fixture|candidate|synthetic|non-operational|server-produced|FastAPI)\b/i);
    expect(html).not.toContain("can_feed_decision_layer");
    expect(html).not.toContain("processing_scope");
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
