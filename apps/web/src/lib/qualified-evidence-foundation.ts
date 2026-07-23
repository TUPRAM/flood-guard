import type {
  QualifiedEvidenceFoundation,
  QualifiedEvidenceStageId,
  QualifiedEvidenceStageState,
} from "./types";

const SHA256 = /^[0-9a-f]{64}$/;
const RFC3339_WITH_TIMEZONE =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const PRIVATE_PATH =
  /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;
const REQUIRED_STAGES: Array<{
  stageId: QualifiedEvidenceStageId;
  state: QualifiedEvidenceStageState;
}> = [
  { stageId: "engineering_foundation", state: "ready" },
  { stageId: "qualified_thai_reference", state: "blocked" },
  { stageId: "reviewer_calibration", state: "blocked" },
  { stageId: "blind_review_adjudication", state: "blocked" },
  { stageId: "frozen_label_release", state: "absent" },
];

export interface QualifiedEvidenceFoundationValidation {
  value: QualifiedEvidenceFoundation | null;
  error: string | null;
}

export function parseQualifiedEvidenceFoundation(
  candidate: unknown,
): QualifiedEvidenceFoundationValidation {
  try {
    assertQualifiedEvidenceFoundation(candidate);
    return { value: candidate, error: null };
  } catch (error) {
    return {
      value: null,
      error:
        error instanceof Error
          ? error.message
          : "Qualified-evidence status is invalid.",
    };
  }
}

export async function verifyQualifiedEvidenceFoundationHash(
  foundation: QualifiedEvidenceFoundation,
): Promise<boolean> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("SHA-256 verification is unavailable in this browser.");
  }
  const { canonical_sha256: declaredHash, ...canonicalPayload } = foundation;
  const encoded = new TextEncoder().encode(canonicalJson(canonicalPayload));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", encoded);
  const actualHash = Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return actualHash === declaredHash;
}

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map(
      (key) =>
        `${JSON.stringify(key)}:${canonicalJson(record[key])}`,
    )
    .join(",")}}`;
}

function assertQualifiedEvidenceFoundation(
  value: unknown,
): asserts value is QualifiedEvidenceFoundation {
  requireRecord(value, "qualified_evidence_foundation");
  requireExactKeys(value, "qualified_evidence_foundation", [
    "schema_version",
    "foundation_id",
    "study_area_id",
    "source_timestamp",
    "generated_at",
    "confidence_class",
    "status",
    "canonical_sha256",
    "authoritative_receipt",
    "reference_candidate_binding",
    "stages",
    "permissions",
    "blockers",
    "next_actions",
    "assumptions",
    "safety",
  ]);
  if (
    value.schema_version !==
      "floodguard.qualified-evidence-foundation.v1" ||
    value.foundation_id !==
      "qualified-thai-reference-frozen-label-release-v1" ||
    value.study_area_id !== "mae_sai_candidate_v1" ||
    value.confidence_class !== "low" ||
    value.status !== "blocked" ||
    value.authoritative_receipt !== false ||
    !isTimestamp(value.source_timestamp) ||
    !isTimestamp(value.generated_at) ||
    !SHA256.test(String(value.canonical_sha256))
  ) {
    throw new Error("Qualified-evidence identity or status contract failed.");
  }

  requireRecord(
    value.reference_candidate_binding,
    "reference_candidate_binding",
  );
  requireExactKeys(
    value.reference_candidate_binding,
    "reference_candidate_binding",
    [
      "manifest_schema",
      "product_id",
      "provider",
      "observation_start_utc",
      "observation_end_utc",
      "manifest_canonical_sha256",
      "manifest_file_sha256",
      "source_archive_sha256",
      "qualification_status",
      "processing_allowed",
    ],
  );
  const binding = value.reference_candidate_binding;
  if (
    binding.manifest_schema !==
      "floodguard.reference_candidate_manifest.v1" ||
    binding.product_id !== "AIT-VAP001-TH" ||
    binding.provider !==
      "Asian Institute of Technology via Sentinel Asia" ||
    binding.qualification_status !==
      "blocked_external_permission_and_scientific_review" ||
    binding.processing_allowed !== false ||
    !isTimestamp(binding.observation_start_utc) ||
    !isTimestamp(binding.observation_end_utc) ||
    !SHA256.test(String(binding.manifest_canonical_sha256)) ||
    !SHA256.test(String(binding.manifest_file_sha256)) ||
    !SHA256.test(String(binding.source_archive_sha256))
  ) {
    throw new Error("Reference-candidate binding is invalid or overclaims authority.");
  }
  if (
    Date.parse(String(binding.observation_end_utc)) <
    Date.parse(String(binding.observation_start_utc))
  ) {
    throw new Error("Reference-candidate observation window is invalid.");
  }

  if (
    !Array.isArray(value.stages) ||
    value.stages.length !== REQUIRED_STAGES.length
  ) {
    throw new Error("Qualified-evidence stages are incomplete.");
  }
  value.stages.forEach((stage, index) => {
    const expected = REQUIRED_STAGES[index];
    requireRecord(stage, `stages[${index}]`);
    requireExactKeys(stage, `stages[${index}]`, [
      "stage_id",
      "state",
      "label_en",
      "label_th",
      "detail_en",
      "detail_th",
    ]);
    if (
      stage.stage_id !== expected.stageId ||
      stage.state !== expected.state
    ) {
      throw new Error("Qualified-evidence stage order or state is invalid.");
    }
    requireLocalizedText(stage, `stages[${index}]`, "label");
    requireLocalizedText(stage, `stages[${index}]`, "detail");
  });

  requireRecord(value.permissions, "permissions");
  requireExactKeys(value.permissions, "permissions", [
    "source_processing_allowed",
    "source_processing_scope_en",
    "source_processing_scope_th",
    "experiment_processing_allowed",
    "qualified_reference_use_allowed",
    "training_allowed",
    "evaluation_allowed",
    "decision_layer_allowed",
    "operational_use_allowed",
  ]);
  if (
    value.permissions.source_processing_allowed !== true ||
    value.permissions.experiment_processing_allowed !== false ||
    value.permissions.qualified_reference_use_allowed !== false ||
    value.permissions.training_allowed !== false ||
    value.permissions.evaluation_allowed !== false ||
    value.permissions.decision_layer_allowed !== false ||
    value.permissions.operational_use_allowed !== false
  ) {
    throw new Error("Qualified-evidence permissions do not fail closed.");
  }
  requireText(
    value.permissions.source_processing_scope_en,
    "permissions.source_processing_scope_en",
  );
  requireText(
    value.permissions.source_processing_scope_th,
    "permissions.source_processing_scope_th",
  );

  requireLocalizedRows(value.blockers, "blockers", "detail");
  if (!Array.isArray(value.blockers) || value.blockers.length === 0) {
    throw new Error("Qualified-evidence blockers are missing.");
  }
  value.blockers.forEach((blocker, index) => {
    requireText(blocker.code, `blockers[${index}].code`);
  });

  if (
    !Array.isArray(value.next_actions) ||
    value.next_actions.length === 0
  ) {
    throw new Error("Qualified-evidence next actions are missing.");
  }
  value.next_actions.forEach((action, index) => {
    requireRecord(action, `next_actions[${index}]`);
    requireExactKeys(action, `next_actions[${index}]`, [
      "sequence",
      "action_en",
      "action_th",
    ]);
    if (action.sequence !== index + 1) {
      throw new Error("Qualified-evidence next-action sequence is invalid.");
    }
    requireLocalizedText(action, `next_actions[${index}]`, "action");
  });

  requireLocalizedRows(value.assumptions, "assumptions", "assumption");
  if (!Array.isArray(value.assumptions) || value.assumptions.length === 0) {
    throw new Error("Qualified-evidence assumptions are missing.");
  }

  requireRecord(value.safety, "safety");
  requireExactKeys(value.safety, "safety", [
    "official_warning",
    "operational_authorized",
    "can_feed_decision_layer",
    "can_feed_fpps",
    "can_assign_action_class",
  ]);
  if (
    value.safety.official_warning !== false ||
    value.safety.operational_authorized !== false ||
    value.safety.can_feed_decision_layer !== false ||
    value.safety.can_feed_fpps !== false ||
    value.safety.can_assign_action_class !== false
  ) {
    throw new Error("Qualified-evidence safety flags do not fail closed.");
  }

  if (containsPrivatePath(value)) {
    throw new Error("Qualified-evidence status contains a private path.");
  }
}

function requireLocalizedRows(
  rows: unknown,
  label: string,
  field: "detail" | "assumption",
): void {
  if (!Array.isArray(rows)) {
    throw new Error(`${label} must be an array.`);
  }
  rows.forEach((row, index) => {
    requireRecord(row, `${label}[${index}]`);
    const keys =
      field === "detail"
        ? ["code", "detail_en", "detail_th"]
        : ["assumption_en", "assumption_th"];
    requireExactKeys(row, `${label}[${index}]`, keys);
    requireLocalizedText(row, `${label}[${index}]`, field);
  });
}

function requireLocalizedText(
  value: Record<string, unknown>,
  label: string,
  field: "label" | "detail" | "action" | "assumption",
): void {
  requireText(value[`${field}_en`], `${label}.${field}_en`);
  requireText(value[`${field}_th`], `${label}.${field}_th`);
}

function requireText(value: unknown, label: string): void {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${label} must be non-empty text.`);
  }
}

function requireRecord(
  value: unknown,
  label: string,
): asserts value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
}

function requireExactKeys(
  value: Record<string, unknown>,
  label: string,
  expected: string[],
): void {
  const actual = Object.keys(value).sort();
  const canonicalExpected = [...expected].sort();
  if (
    actual.length !== canonicalExpected.length ||
    actual.some((key, index) => key !== canonicalExpected[index])
  ) {
    throw new Error(`${label} contains missing or unexpected fields.`);
  }
}

function isTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    RFC3339_WITH_TIMEZONE.test(value) &&
    Number.isFinite(Date.parse(value))
  );
}

function containsPrivatePath(value: unknown): boolean {
  const values: string[] = [];
  JSON.stringify(value, (key, candidate: unknown) => {
    values.push(key);
    if (typeof candidate === "string") values.push(candidate);
    return candidate;
  });
  return values.some((candidate) => PRIVATE_PATH.test(candidate));
}
