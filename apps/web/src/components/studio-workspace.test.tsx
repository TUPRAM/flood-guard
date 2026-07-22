import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import maeSaiBundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import type { EvidenceRecord } from "@floodguard/contracts";

import { evidenceRecordJson } from "@/lib/studio-evidence";

import { StudioWorkspace } from "./studio-workspace";

describe("StudioWorkspace", () => {
  it("renders a read-only Mae Sai validation report bound to one evidence context", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);
    const visibleText = html.replace(/<[^>]*>/g, " ");

    expect(html).toContain("Validation &amp; evidence report");
    expect(html).toContain("Read-only evidence report");
    expect(html).toContain("Mae Sai district, Chiang Rai");
    expect(html).toContain("mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1");
    expect(html).toContain("Blocking evidence gates");
    expect(html).toContain("Evidence decision matrix");
    expect(html).toContain("Observed-data validation");
    expect(html).toContain("Files &amp; history");
    expect(visibleText).not.toMatch(/open reviews|review held|assigned to|due date|comments?/i);
    expect(visibleText).not.toContain("Evidence-scoped comparison");
  });

  it("does not substitute a model leaderboard when the context has no bound evaluation", () => {
    const html = renderToStaticMarkup(<StudioWorkspace />);

    expect(html).toContain("No model evaluation is bound to this context.");
    expect(html).not.toContain("SAR reference model");
    expect(html).not.toContain("Logistic benchmark");
    expect(html).not.toContain("GeoAI model");
  });

  it("fails closed for an unknown context instead of loading another package", () => {
    const html = renderToStaticMarkup(<StudioWorkspace evidenceContextId="unknown-evidence-context" />);

    expect(html).toContain("Evaluation unavailable for this evidence package.");
    expect(html).toContain("will not substitute another study area, data version, or evaluation");
    expect(html).not.toContain("Evidence decision matrix");
  });

  it("exports the schema-shaped server evidence record without provenance rewriting", () => {
    const record = (maeSaiBundleJson as unknown as { evidence_record: EvidenceRecord }).evidence_record;
    const parsed = JSON.parse(evidenceRecordJson(record)) as EvidenceRecord;

    expect(parsed.evidence_record_id).toBe("mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1:blocked");
    expect(parsed.evidence_context.evidence_context_id).toBe("mae-sai:2024-09:mae-sai-candidate-2024-09-15-v1");
    expect(parsed.evidence_context.model_run_id).toBeNull();
    expect(parsed.evidence_context.dataset_mode).toBe("candidate");
    expect(parsed.evidence_context.operational_status).toBe("non_operational");
    expect(parsed.evidence_context.data_version).toBe("mae-sai-candidate-2024-09-15-v1");
    expect(parsed.evidence_context.evidence_package_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(parsed.model_id).toBeNull();
    expect(parsed.model_version).toBeNull();
    expect(parsed.model_sha256).toBeNull();
    expect(parsed.evaluation_sha256).toBeNull();
    expect(parsed.decision_authority).toBeNull();
    expect(parsed.decision_at).toBeNull();
    expect(parsed.operational_authorized).toBe(false);
    expect(parsed.blockers.length).toBeGreaterThan(0);
  });
});
