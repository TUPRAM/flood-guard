import { describe, expect, it, vi } from "vitest";
import { evidenceFixtures } from "./evidence-library.fixtures";
import { finalsAnalysisFixture } from "./finals-analysis.fixtures";
import { caseHref, pushCaseSelection, readCaseSelection, resolveAnalysisSelection, resolveEvidenceCase } from "./case-selection";

describe("case selection", () => {
  it("round-trips the same case and optional result identity through role links", () => {
    const selection = { aoi: "aoi-01", event: "event-2024", version: "v1", service: "hospital", mode: "walking", scenario: "candidate_flood", origin: "prepared-origin" };
    const href = caseHref("/studio/", selection);
    expect(readCaseSelection(href.split("?")[1])).toEqual(selection);
    expect(href).toContain("aoi=aoi-01&event=event-2024&version=v1");
  });

  it("notifies every same-page role view when a case or scenario is pushed", () => {
    const pushState = vi.fn();
    const dispatchEvent = vi.fn();
    vi.stubGlobal("window", { location: { pathname: "/command/" }, history: { pushState }, dispatchEvent });
    try {
      pushCaseSelection({ aoi: "aoi-05", event: "event-2025", version: "v2", service: "hospital", mode: "walking", scenario: "candidate" });
      expect(pushState).toHaveBeenCalledWith(null, "", "/command/?aoi=aoi-05&event=event-2025&version=v2&service=hospital&mode=walking&scenario=candidate");
      expect(dispatchEvent).toHaveBeenCalledOnce();
      expect(dispatchEvent.mock.calls[0][0]).toHaveProperty("type", "popstate");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("rejects incomplete, unknown and mixed-version deep links", () => {
    const { catalog } = evidenceFixtures();
    expect(resolveEvidenceCase(catalog, { aoi: catalog.packages[0].aoi_id }).reason).toBe("incomplete_case");
    expect(resolveEvidenceCase(catalog, { aoi: "unknown", event: "unknown" }).reason).toBe("unknown_case");
    expect(resolveEvidenceCase(catalog, { version: "stale" }).reason).toBe("version_mismatch");
    expect(resolveEvidenceCase(catalog, {}).reference?.id).toBe(catalog.packages[0].id);
  });

  it("does not substitute another service, mode or prepared origin", () => {
    const analysis = finalsAnalysisFixture();
    expect(resolveAnalysisSelection(analysis, { service: "hospital", mode: "helicopter" }).reason).toBe("unknown_mode");
    expect(resolveAnalysisSelection(analysis, { service: "fire-station" }).reason).toBe("unknown_service");
    expect(resolveAnalysisSelection(analysis, { origin: "private-pin" }).reason).toBe("unknown_origin");
    expect(resolveAnalysisSelection(analysis, { scenario: "other-event" }).reason).toBe("unknown_scenario");
  });
});
