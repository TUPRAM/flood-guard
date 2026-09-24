import { describe, expect, it } from "vitest";
import catalog from "../schemas/evidence-library-catalog.schema.json";
import evidence from "../schemas/evidence-library-package.schema.json";
import assessment from "../schemas/evidence-assessment.schema.json";
import { EVIDENCE_AVAILABILITIES } from "./evidence-library";

describe("evidence-library contracts", () => {
  it("preserves the candidate boundary separately from decision contracts", () => {
    expect(catalog.properties.non_operational.const).toBe(true);
    expect(evidence.properties.dataset_mode.const).toBe("candidate");
    expect(evidence.properties.official_warning.const).toBe(false);
    expect(evidence.properties.operational_status.const).toBe("non_operational");
    expect(assessment.properties.fpps.type).toBe("null");
    expect(assessment.properties.action_class.type).toBe("null");
    expect(evidence.required).toContain("package_version");
    expect(evidence.properties.assessment).toMatchObject({ properties: assessment.properties });
  });

  it("keeps availability values consistent and prevents metadata-only map assets", () => {
    expect(evidence.properties.datasets.items.properties.availability.enum).toEqual(EVIDENCE_AVAILABILITIES);
    expect(evidence.properties.layers.items.properties.availability.enum).toEqual(EVIDENCE_AVAILABILITIES);
    expect(evidence.properties.layers.items.allOf[0].then.not).toMatchObject({ anyOf: [{ required: ["data"] }, { required: ["image_url"] }] });
  });
});
