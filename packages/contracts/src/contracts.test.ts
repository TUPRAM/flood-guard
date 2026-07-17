import { describe, expect, it } from "vitest";

import areaDecisionSchema from "../schemas/area-decision.schema.json";
import acceptanceReceiptSchema from "../schemas/agency-acceptance-receipt.schema.json";
import fieldValidationReceiptSchema from "../schemas/field-validation-receipt.schema.json";
import layerSchema from "../schemas/layer.schema.json";
import modelRunSchema from "../schemas/model-run.schema.json";
import pilotReadinessSchema from "../schemas/pilot-readiness.schema.json";
import proposalEvidenceSchema from "../schemas/proposal-evidence.schema.json";
import statusSchema from "../schemas/status.schema.json";
import {
  ACCEPTANCE_RECEIPT_STATES,
  ACTION_CLASSES,
  COMMON_METADATA_FIELDS,
  CONFIDENCE_CLASSES,
  DATASET_MODES,
  DATA_STATES,
  EVIDENCE_RESULTS,
  GEOAI_AGGREGATION_STATUSES,
  GEOAI_VALIDATION_STATUSES,
  LAYER_FORMATS,
  MODEL_FAMILIES,
  MODEL_RUN_STATUSES,
  OPERATIONAL_STATUSES,
  PILOT_ROLES,
  PREPROCESSING_VALUE_DOMAINS,
  ROLE_VISIBILITIES,
  SCHEMA_VERSION,
} from "./index";

const schemas = [
  statusSchema,
  areaDecisionSchema,
  layerSchema,
  modelRunSchema,
] as const;

describe("contract drift", () => {
  it("keeps the runtime constants aligned with JSON Schema enums", () => {
    expect(DATASET_MODES).toEqual(statusSchema.properties.dataset_mode.enum);
    expect(OPERATIONAL_STATUSES).toEqual(
      statusSchema.properties.operational_status.enum,
    );
    expect(CONFIDENCE_CLASSES).toEqual(
      statusSchema.properties.confidence_class.enum,
    );
    expect(DATA_STATES).toEqual(statusSchema.properties.data_state.enum);
    expect(ACTION_CLASSES).toEqual(
      areaDecisionSchema.properties.action_class.enum,
    );
    expect(ROLE_VISIBILITIES).toEqual(
      layerSchema.properties.role_visibility.items.enum,
    );
    expect(LAYER_FORMATS).toEqual(layerSchema.properties.format.enum);
    expect(MODEL_FAMILIES).toEqual(
      modelRunSchema.properties.model_family.enum,
    );
    expect(MODEL_RUN_STATUSES).toEqual(
      modelRunSchema.properties.run_status.enum,
    );
    expect(PREPROCESSING_VALUE_DOMAINS).toEqual(
      modelRunSchema.properties.preprocessing.properties.value_domain.enum,
    );
  });

  it("keeps the common metadata envelope mandatory in every schema", () => {
    for (const schema of schemas) {
      expect(schema.properties.schema_version.const).toBe(SCHEMA_VERSION);
      expect(schema.required).toEqual(
        expect.arrayContaining([...COMMON_METADATA_FIELDS]),
      );
      for (const field of COMMON_METADATA_FIELDS) {
        expect(schema.properties).toHaveProperty(field);
      }
    }
  });

  it("keeps fixture and candidate warning claims fail-closed", () => {
    for (const schema of schemas) {
      const nonOfficialRule = schema.allOf[0];
      expect(nonOfficialRule.if.properties.dataset_mode?.enum).toEqual([
        "fixture_demo",
        "candidate",
      ]);
      expect(nonOfficialRule.then.properties.official_warning?.const).toBe(false);
    }
  });

  it("keeps pilot roles and acceptance states aligned", () => {
    expect(PILOT_ROLES).toEqual(
      pilotReadinessSchema.properties.roles.items.enum,
    );
    expect(ACCEPTANCE_RECEIPT_STATES).toEqual(
      pilotReadinessSchema.properties.acceptance_receipt_state.enum,
    );
    expect(
      acceptanceReceiptSchema.properties.payload.properties.dataset_mode.const,
    ).toBe("official_input");
    expect(
      acceptanceReceiptSchema.properties.payload.properties
        .requested_operational_status.const,
    ).toBe("agency_operational");
    expect(fieldValidationReceiptSchema.properties.protocol_version.const).toBe(
      "field-validation-v1",
    );
  });

  it("keeps proposal evidence receipt states aligned", () => {
    const suite = proposalEvidenceSchema.properties.test_suites.items;
    const proof = proposalEvidenceSchema.properties.geoai_proof.properties;
    expect(EVIDENCE_RESULTS).toEqual(suite.properties.result.enum);
    expect(GEOAI_VALIDATION_STATUSES).toEqual(proof.validation_status.enum);
    expect(GEOAI_AGGREGATION_STATUSES).toEqual(
      proof.aggregation_status.enum,
    );
    expect(proposalEvidenceSchema.properties.schema_version.const).toBe(
      SCHEMA_VERSION,
    );
  });
});
