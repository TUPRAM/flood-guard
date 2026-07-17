import {
  EVIDENCE_RESULTS,
  GEOAI_AGGREGATION_STATUSES,
  GEOAI_VALIDATION_STATUSES,
  type DatasetMode,
  type OperationalStatus,
  type ProposalEvidenceArtifact,
  type ProposalEvidenceManifest,
  type ProposalTestSuiteReceipt,
} from "@floodguard/contracts";

import {
  type GeoAiProofReceipt,
  validateGeoAiProofReceipt,
} from "./geoai-proof-receipt";

export type { ProposalEvidenceManifest } from "@floodguard/contracts";
export type { GeoAiProofReceipt } from "./geoai-proof-receipt";

const SHA256 = /^[a-f0-9]{64}$/i;
const PRIVATE_PATH = /(?:^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|\\\\|file:\/\/|(?:^|[^A-Za-z0-9_.-])\/(?:Users|home|root|tmp|var|opt|mnt|srv)(?:\/|$)/i;

export type ProposalEvidenceResult =
  | { state: "ready"; manifest: ProposalEvidenceManifest; proofReceipt: GeoAiProofReceipt | null }
  | { state: "unavailable"; reason: string };

export function validateProposalEvidenceManifest(value: unknown): ProposalEvidenceManifest {
  if (!isRecord(value)) throw new Error("Evidence manifest must be an object.");
  if (value.schema_version !== "1.0") throw new Error("Evidence manifest schema_version is invalid.");
  requireTimestamp(value.generated_at, "generated_at");
  requireString(value.git_commit, "git_commit");
  if (!isDatasetMode(value.dataset_mode)) throw new Error("Evidence manifest dataset_mode is invalid.");
  if (!isOperationalStatus(value.operational_status)) throw new Error("Evidence manifest operational_status is invalid.");
  if (!Array.isArray(value.artifacts) || !Array.isArray(value.test_suites)) {
    throw new Error("Evidence manifest artifact and test collections are required.");
  }

  const artifacts = value.artifacts.map((candidate, index) => validateArtifact(candidate, index));
  const testSuites = value.test_suites.map((candidate, index) => validateTestSuite(candidate, index));
  const proof = validateGeoAiProof(value.geoai_proof);

  if (value.dataset_mode !== "official_input" && value.operational_status === "agency_operational") {
    throw new Error("Fixture or candidate evidence cannot claim agency operation.");
  }
  if (value.dataset_mode !== "official_input" && proof.can_feed_decision_layer) {
    throw new Error("Fixture or candidate evidence cannot feed the decision layer.");
  }
  if (!proof.processing_allowed && proof.can_feed_decision_layer) {
    throw new Error("Blocked processing cannot feed the decision layer.");
  }
  if (!proof.can_feed_decision_layer && !proof.reason_blocked.trim()) {
    throw new Error("Blocked GeoAI evidence requires reason_blocked.");
  }

  const manifest = {
    schema_version: value.schema_version,
    generated_at: value.generated_at,
    git_commit: value.git_commit,
    dataset_mode: value.dataset_mode,
    operational_status: value.operational_status,
    artifacts,
    test_suites: testSuites,
    geoai_proof: proof,
  } satisfies ProposalEvidenceManifest;
  if (PRIVATE_PATH.test(JSON.stringify(manifest))) {
    throw new Error("Evidence manifest contains a private absolute path.");
  }
  return manifest;
}

export async function loadProposalEvidence(
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<ProposalEvidenceResult> {
  try {
    const statusResponse = await fetcher("/proposal-evidence-status.json", { cache: "no-store", signal });
    if (!statusResponse.ok) {
      return { state: "unavailable", reason: `Evidence availability returned ${statusResponse.status}.` };
    }
    const status = await statusResponse.json() as unknown;
    if (!isRecord(status) || status.available !== true) {
      return { state: "unavailable", reason: "No proposal evidence manifest was published with this build." };
    }
    const response = await fetcher("/proposal-evidence.json", { cache: "no-store", signal });
    if (!response.ok) {
      return { state: "unavailable", reason: `Evidence manifest returned ${response.status}.` };
    }
    const manifest = validateProposalEvidenceManifest(await response.json());
    const proofReceipt = await loadValidatedProofReceipt(manifest, fetcher, signal);
    return { state: "ready", manifest, proofReceipt };
  } catch (error) {
    return {
      state: "unavailable",
      reason: error instanceof Error ? error.message : "Evidence manifest is unavailable.",
    };
  }
}

async function loadValidatedProofReceipt(
  manifest: ProposalEvidenceManifest,
  fetcher: typeof fetch,
  signal?: AbortSignal,
): Promise<GeoAiProofReceipt | null> {
  if (manifest.geoai_proof.validation_status !== "passed") return null;
  const receiptArtifacts = manifest.artifacts.filter((artifact) => artifact.kind === "geoai_proof_receipt");
  if (receiptArtifacts.length !== 1) throw new Error("Validated GeoAI proof requires exactly one receipt artifact.");
  const artifact = receiptArtifacts[0];
  if (artifact.media_type !== "application/json") throw new Error("GeoAI proof receipt must use application/json.");
  const href = publicArtifactHref(artifact.relative_path, artifact.sha256);
  if (!href) throw new Error("GeoAI proof receipt does not have a public-safe artifact path.");
  const response = await fetcher(href, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`GeoAI proof receipt returned ${response.status}.`);
  const bytes = await response.arrayBuffer();
  const actualSha256 = await sha256Hex(bytes);
  if (actualSha256 !== artifact.sha256.toLowerCase()) {
    throw new Error("GeoAI proof receipt file checksum does not match the evidence manifest.");
  }
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Error("GeoAI proof receipt is not valid UTF-8 JSON.");
  }
  return validateGeoAiProofReceipt(value, manifest);
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error("SHA-256 verification is unavailable in this browser.");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
}

export function publicArtifactHref(relativePath: string, sha256?: string | null): string | null {
  const normalized = relativePath.replaceAll("\\", "/").replace(/^\.\//, "");
  if (normalized.includes("..") || PRIVATE_PATH.test(normalized)) return null;
  if (normalized.startsWith("apps/web/public/")) return `/${normalized.slice("apps/web/public/".length)}`;
  if (normalized.startsWith("public/")) return `/${normalized.slice("public/".length)}`;
  if (normalized.startsWith("services/geoai-runner/evidence/") && sha256 && SHA256.test(sha256)) {
    const fileName = normalized.split("/").at(-1);
    if (fileName && /^[A-Za-z0-9._-]+$/.test(fileName)) {
      return `/proposal-evidence-assets/${sha256.slice(0, 12).toLowerCase()}-${fileName}`;
    }
  }
  if (normalized.startsWith("/")) return normalized;
  return null;
}

function validateArtifact(value: unknown, index: number): ProposalEvidenceArtifact {
  if (!isRecord(value)) throw new Error(`Artifact ${index} must be an object.`);
  requireString(value.kind, `artifacts[${index}].kind`);
  requireString(value.relative_path, `artifacts[${index}].relative_path`);
  requireString(value.media_type, `artifacts[${index}].media_type`);
  requireSha(value.sha256, `artifacts[${index}].sha256`);
  if (
    value.relative_path.includes("..")
    || PRIVATE_PATH.test(value.relative_path)
    || /^[a-z][a-z0-9+.-]*:\/\//i.test(value.relative_path)
  ) {
    throw new Error(`Artifact ${index} path is not public and relative.`);
  }
  return value as unknown as ProposalEvidenceArtifact;
}

function validateTestSuite(value: unknown, index: number): ProposalTestSuiteReceipt {
  if (!isRecord(value)) throw new Error(`Test suite ${index} must be an object.`);
  requireString(value.name, `test_suites[${index}].name`);
  requireString(value.command, `test_suites[${index}].command`);
  if (!EVIDENCE_RESULTS.includes(value.result as never)) throw new Error(`test_suites[${index}].result is invalid.`);
  if (!Number.isInteger(value.passed) || Number(value.passed) < 0) throw new Error(`test_suites[${index}].passed is invalid.`);
  if (!Number.isInteger(value.skipped) || Number(value.skipped) < 0) throw new Error(`test_suites[${index}].skipped is invalid.`);
  return value as unknown as ProposalTestSuiteReceipt;
}

function validateGeoAiProof(value: unknown): ProposalEvidenceManifest["geoai_proof"] {
  if (!isRecord(value)) throw new Error("geoai_proof is required.");
  for (const key of [
    "feature_stack_id",
    "preprocessing_id",
    "reason_blocked",
  ] as const) requireString(value[key], `geoai_proof.${key}`, key === "reason_blocked");
  if (value.geoai_version !== "0.41.1") throw new Error("geoai_proof.geoai_version is invalid.");
  if (!GEOAI_VALIDATION_STATUSES.includes(value.validation_status as never)) throw new Error("geoai_proof.validation_status is invalid.");
  if (!GEOAI_AGGREGATION_STATUSES.includes(value.aggregation_status as never)) throw new Error("geoai_proof.aggregation_status is invalid.");
  requireNullableSha(value.input_manifest_sha256, "geoai_proof.input_manifest_sha256");
  requireNullableSha(value.output_probability_sha256, "geoai_proof.output_probability_sha256");
  if (value.validation_status === "passed") {
    requireSha(value.input_manifest_sha256, "geoai_proof.input_manifest_sha256");
    requireSha(value.output_probability_sha256, "geoai_proof.output_probability_sha256");
  }
  if (typeof value.processing_allowed !== "boolean" || typeof value.can_feed_decision_layer !== "boolean") {
    throw new Error("GeoAI proof gate states must be boolean.");
  }
  return value as unknown as ProposalEvidenceManifest["geoai_proof"];
}

function requireString(value: unknown, label: string, allowEmpty = false): asserts value is string {
  if (typeof value !== "string" || (!allowEmpty && !value.trim())) throw new Error(`${label} is required.`);
}

function requireTimestamp(value: unknown, label: string): asserts value is string {
  requireString(value, label);
  if (!Number.isFinite(Date.parse(value))) throw new Error(`${label} must be an ISO timestamp.`);
}

function requireSha(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !SHA256.test(value)) throw new Error(`${label} must be a SHA-256 digest.`);
}

function requireNullableSha(value: unknown, label: string): asserts value is string | null {
  if (value !== null) requireSha(value, label);
}

function isDatasetMode(value: unknown): value is DatasetMode {
  return value === "fixture_demo" || value === "candidate" || value === "official_input";
}

function isOperationalStatus(value: unknown): value is OperationalStatus {
  return value === "non_operational" || value === "planning_only" || value === "agency_operational";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
