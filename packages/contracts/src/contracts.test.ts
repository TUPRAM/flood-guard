import { describe, expect, it } from "vitest";

import areaDecisionSchema from "../schemas/area-decision.schema.json";
import layerSchema from "../schemas/layer.schema.json";
import modelRunSchema from "../schemas/model-run.schema.json";
import statusSchema from "../schemas/status.schema.json";
import {
  ACTION_CLASSES,
  COMMON_METADATA_FIELDS,
  CONFIDENCE_CLASSES,
  DATASET_MODES,
  DATA_STATES,
  LAYER_FORMATS,
  MODEL_FAMILIES,
  MODEL_RUN_STATUSES,
  OPERATIONAL_STATUSES,
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
});
