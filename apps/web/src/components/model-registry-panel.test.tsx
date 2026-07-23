import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import maeSaiBundleJson from "../../public/offline-demo/mae-sai/bundle.json";
import type {
  EvidenceContext,
  FloodObservationProductV2,
  ModelEvaluationV2,
  ModelRegistryEntryV1,
} from "@floodguard/contracts";

import { validateModelEvidenceProjection } from "@/lib/model-registry";

import { ModelRegistryPanel } from "./model-registry-panel";

const TAMPER_CASES: Array<{
  label: string;
  tamper: (
    entries: ModelRegistryEntryV1[],
    evaluations: ModelEvaluationV2[],
    products: FloodObservationProductV2[],
  ) => void;
}> = [
  {
    label: "payload display text",
    tamper: (entries) => {
      entries[0].payload.reason_blocked =
        "tampered registry text that the browser cannot authenticate";
    },
  },
  {
    label: "evaluation content",
    tamper: (_entries, evaluations) => {
      evaluations[0].assumptions[0] =
        "tampered evaluation assumption that preserves the declared digest field";
    },
  },
  {
    label: "product asset metadata",
    tamper: (_entries, _evaluations, products) => {
      products[0].assets[0].band_name = "tampered_probability_band";
      products[0].assets[0].media_type = "image/tiff; tampered=true";
    },
  },
];

describe("ModelRegistryPanel", () => {
  it("renders the server-declared blocked envelope without implying browser cryptographic authority", () => {
    const html = renderToStaticMarkup(
      <ModelRegistryPanel
        context={maeSaiBundleJson.evidence_context as EvidenceContext}
        entries={maeSaiBundleJson.model_registry as ModelRegistryEntryV1[]}
        evaluations={
          maeSaiBundleJson.model_evaluations as ModelEvaluationV2[]
        }
        products={
          maeSaiBundleJson.observation_products as FloodObservationProductV2[]
        }
        evidenceState="blocked"
        evidenceReason="Qualified observed-event evidence is absent."
        language="en"
      />,
    );

    expect(html).toContain("Model registry &amp; evaluation");
    expect(html).toContain(
      "No model evaluation is bound to this evidence context",
    );
    expect(html).toContain("External algorithmic baseline");
    expect(html).toContain("No real-event evaluation");
    expect(html).toContain("Report only");
    expect(html).toContain("not eligible for FPPS or the decision layer");
    expect(html).toContain("Valid coverage");
    expect(html).toContain("Abstained");
    expect(html).toContain("0%");
    expect(html).toContain("100%");
    expect(html).toContain("Remain unknown; never treated as dry");
    expect(html).toContain("Browser cryptographic status: not verified");
    expect(html).toContain(
      "The browser does not recompute or authenticate the payload, evaluation, or product digests and does not verify the HMAC.",
    );
    expect(html).toContain("Declared signer key label");
    expect(html).toContain("declared payload_sha256");
    expect(html).not.toContain("Signature authority");
    expect(html).not.toContain("official flood warning");
  });

  it.each(TAMPER_CASES)(
    "never presents tampered $label as browser-verified or authoritative",
    ({ tamper }) => {
      const entries = structuredClone(
        maeSaiBundleJson.model_registry,
      ) as ModelRegistryEntryV1[];
      const evaluations = structuredClone(
        maeSaiBundleJson.model_evaluations,
      ) as ModelEvaluationV2[];
      const products = structuredClone(
        maeSaiBundleJson.observation_products,
      ) as FloodObservationProductV2[];
      tamper(entries, evaluations, products);

      // Shape and cross-record joins still pass because this browser validator
      // intentionally does not recompute the declared cryptographic digests.
      const projection = validateModelEvidenceProjection(
        maeSaiBundleJson.evidence_context as EvidenceContext,
        entries,
        evaluations,
        products,
      );
      expect(projection.state).toBe("blocked");

      const html = renderToStaticMarkup(
        <ModelRegistryPanel
          context={maeSaiBundleJson.evidence_context as EvidenceContext}
          entries={projection.entries}
          evaluations={projection.evaluations}
          products={projection.products}
          evidenceState={projection.state}
          evidenceReason={projection.reason}
          language="en"
        />,
      );

      expect(html).toContain("Browser cryptographic status: not verified");
      expect(html).toContain(
        "The API and repository are the authority for cryptographic verification.",
      );
      expect(html).toContain("Declared signer key label");
      expect(html).toContain("declared payload_sha256");
      expect(html).not.toContain("Signature authority");
      expect(html).not.toMatch(/browser (?:verified|authoritative)/iu);
      expect(html).not.toMatch(/cryptographically verified/iu);
    },
  );

  it("explains missing or mismatched model evidence instead of rendering details", () => {
    const html = renderToStaticMarkup(
      <ModelRegistryPanel
        context={maeSaiBundleJson.evidence_context as EvidenceContext}
        entries={[]}
        evaluations={[]}
        products={[]}
        evidenceState="unavailable"
        evidenceReason="Registry hash does not match the active package."
        language="en"
      />,
    );

    expect(html).toContain("Model evidence is unavailable for this package.");
    expect(html).toContain("Registry hash does not match the active package.");
    expect(html).not.toContain("EVIDENCE PRODUCT");
  });
});
