"""Strict contracts for the bounded FloodGuard agency pilot control plane."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
SAFE_ID = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")]
MANDATORY_ACCEPTANCE_CRITERIA = frozenset(
    {"AC-SAFETY-01", "AC-DATA-02", "AC-OFFLINE-03", "AC-AUTH-04", "AC-FIELD-05"}
)
MANDATORY_RETENTION_ARTIFACTS = {
    "pilot-acceptance-receipt": "acceptance_receipt",
    "pilot-audit-ledger": "audit_log",
    "pilot-audit-anchor": "audit_log",
    "current-served-artifact-manifest": "source_manifest",
    "current-field-validation-receipt": "source_manifest",
}


class StrictPilotModel(BaseModel):
    """Reject unknown fields at every pilot trust boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PilotRole(str, Enum):
    PUBLIC_VIEWER = "public_viewer"
    COMMAND_VIEWER = "command_viewer"
    ANALYST = "analyst"
    DATA_STEWARD = "data_steward"
    PILOT_ADMIN = "pilot_admin"


class PilotCredential(StrictPilotModel):
    """Externally issued, short-lived identity assertion."""

    schema_version: Literal["1.0"] = "1.0"
    subject: SAFE_ID
    roles: list[PilotRole] = Field(min_length=1)
    issued_at: datetime
    expires_at: datetime
    token_id: SAFE_ID
    key_id: SAFE_ID

    @model_validator(mode="after")
    def validate_lifetime(self) -> PilotCredential:
        if self.expires_at <= self.issued_at:
            raise ValueError("Credential expiry must follow issue time.")
        if self.expires_at - self.issued_at > timedelta(hours=1):
            raise ValueError("Pilot credentials may be valid for at most one hour.")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Credential roles must be unique.")
        return self


class PilotSessionResponse(StrictPilotModel):
    subject: str
    roles: list[PilotRole]
    expires_at: datetime
    granted_capabilities: list[str]


class BilingualAcceptanceCriterion(StrictPilotModel):
    criterion_id: SAFE_ID
    required: Literal[True] = True
    status: Literal["pending", "accepted"]
    text_th: str = Field(min_length=1)
    text_en: str = Field(min_length=1)


class PilotReadiness(StrictPilotModel):
    schema_version: Literal["1.0"] = "1.0"
    operational_status: Literal["non_operational", "planning_only", "agency_operational"]
    agency_operational_allowed: bool
    identity_state: Literal["unconfigured", "configured"]
    acceptance_receipt_state: Literal["missing", "invalid", "expired", "accepted"]
    audit_state: Literal["unconfigured", "valid", "invalid"]
    retention_state: Literal["unconfigured", "configured"]
    deployment_state: Literal[
        "pilot_not_configured",
        "pilot_ready_non_operational",
        "degraded",
        "accepted_for_agency_operation",
    ]
    acceptance_criteria: list[BilingualAcceptanceCriterion] = Field(min_length=1)
    field_validation_protocol_version: Literal["field-validation-v1"]
    roles: list[PilotRole] = Field(min_length=5)
    reason_blocked_th: str
    reason_blocked_en: str

    @model_validator(mode="after")
    def preserve_operational_boundary(self) -> PilotReadiness:
        operational = self.operational_status == "agency_operational"
        if self.agency_operational_allowed != operational:
            raise ValueError("Agency-operational allowance must exactly match operating state.")
        if self.acceptance_receipt_state != "accepted" and self.agency_operational_allowed:
            raise ValueError("Only an accepted receipt may allow agency operation.")
        criterion_ids = {item.criterion_id for item in self.acceptance_criteria}
        if criterion_ids != MANDATORY_ACCEPTANCE_CRITERIA:
            raise ValueError("Pilot readiness must expose every mandatory acceptance criterion.")
        if operational and (
            self.identity_state != "configured"
            or self.audit_state != "valid"
            or self.retention_state != "configured"
            or self.deployment_state != "accepted_for_agency_operation"
            or any(item.status != "accepted" for item in self.acceptance_criteria)
        ):
            raise ValueError(
                "Agency operation requires every control and criterion to be accepted."
            )
        if not operational and self.deployment_state == "accepted_for_agency_operation":
            raise ValueError("An unaccepted pilot cannot report an accepted deployment state.")
        return self


class AcceptanceReceiptRequest(StrictPilotModel):
    acceptance_id: SAFE_ID
    study_area: SAFE_ID
    dataset_mode: Literal["fixture_demo", "candidate", "official_input"]
    data_version: SAFE_ID
    artifact_manifest_sha256: SHA256
    source_timestamp: datetime
    acceptance_criteria_ids: list[SAFE_ID] = Field(min_length=1)
    field_validation_receipt_sha256: SHA256
    field_validation_protocol_version: Literal["field-validation-v1"]
    expires_at: datetime

    @field_validator("acceptance_criteria_ids")
    @classmethod
    def unique_criteria(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Acceptance criteria must be unique.")
        return value


class AcceptanceReceiptPayload(StrictPilotModel):
    schema_version: Literal["1.0"] = "1.0"
    acceptance_id: SAFE_ID
    study_area: SAFE_ID
    dataset_mode: Literal["official_input"]
    data_version: SAFE_ID
    artifact_manifest_sha256: SHA256
    source_timestamp: datetime
    requested_operational_status: Literal["agency_operational"] = "agency_operational"
    acceptance_status: Literal["accepted"] = "accepted"
    acceptance_criteria_ids: list[SAFE_ID] = Field(min_length=1)
    field_validation_receipt_sha256: SHA256
    field_validation_protocol_version: Literal["field-validation-v1"]
    issued_at: datetime
    expires_at: datetime
    issuer_subject: SAFE_ID

    @model_validator(mode="after")
    def validate_acceptance_window(self) -> AcceptanceReceiptPayload:
        if self.expires_at <= self.issued_at:
            raise ValueError("Acceptance receipt expiry must follow issue time.")
        if self.expires_at - self.issued_at > timedelta(days=30):
            raise ValueError("Acceptance receipts may be valid for at most 30 days.")
        if self.source_timestamp > self.issued_at:
            raise ValueError("Acceptance source time cannot follow receipt issue time.")
        if len(set(self.acceptance_criteria_ids)) != len(self.acceptance_criteria_ids):
            raise ValueError("Acceptance criteria must be unique.")
        return self


class ManifestSignature(StrictPilotModel):
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: SAFE_ID
    payload_sha256: SHA256
    value: SHA256


class SignedAcceptanceReceipt(StrictPilotModel):
    payload: AcceptanceReceiptPayload
    signature: ManifestSignature


class FieldObservationWindow(StrictPilotModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_window(self) -> FieldObservationWindow:
        if self.end <= self.start:
            raise ValueError("Field observation window end must follow start.")
        return self


class FieldEvidenceHashes(StrictPilotModel):
    product_manifest_sha256: SHA256 | None
    model_manifest_sha256: SHA256 | None
    probability_raster_sha256: SHA256 | None
    zonal_receipt_sha256: SHA256 | None
    reporting_geometry_sha256: SHA256 | None
    sampling_plan_sha256: SHA256 | None
    holdout_geometry_sha256: SHA256 | None


class FieldStratumCount(StrictPilotModel):
    stratum_id: SAFE_ID
    observed: int = Field(ge=0)
    usable: int = Field(ge=0)
    excluded: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> FieldStratumCount:
        if self.usable + self.excluded != self.observed:
            raise ValueError("Usable and excluded counts must equal observed count.")
        return self


class ReviewerCalibrationReceipt(StrictPilotModel):
    status: Literal["passed", "failed", "not_evaluated"]
    metric: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)
    evidence_sha256: SHA256 | None

    @model_validator(mode="after")
    def validate_calibration_decision(self) -> ReviewerCalibrationReceipt:
        if self.status == "passed":
            if (
                not self.metric
                or self.score is None
                or self.threshold is None
                or self.evidence_sha256 is None
            ):
                raise ValueError("Passing calibration requires complete evidence.")
            if self.score < self.threshold:
                raise ValueError("Passing calibration score must meet its threshold.")
        return self


class FieldValidationMetrics(StrictPilotModel):
    iou: float | None = Field(default=None, ge=0, le=1)
    f1_dice: float | None = Field(default=None, ge=0, le=1)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    signed_area_error_ratio: float | None = None
    absolute_area_error_ratio: float | None = Field(default=None, ge=0)
    brier_score: float | None = Field(default=None, ge=0, le=1)
    expected_calibration_error: float | None = Field(default=None, ge=0, le=1)


class FieldErrorCategory(StrictPilotModel):
    category: SAFE_ID
    count: int = Field(ge=0)


class FieldValidationReceipt(StrictPilotModel):
    schema_version: Literal["1.0"] = "1.0"
    protocol_version: Literal["field-validation-v1"]
    receipt_id: SAFE_ID
    dataset_mode: Literal["fixture_demo", "candidate", "official_input"]
    operational_status: Literal["non_operational", "planning_only"]
    source_timestamp: datetime
    generated_at: datetime
    confidence_class: Literal["low", "medium", "high"]
    source_name: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    official_warning: Literal[False]
    git_commit: str = Field(pattern=r"^[0-9a-fA-F]{7,40}$")
    can_feed_decision_layer: Literal[False]
    study_area: SAFE_ID
    event_id: SAFE_ID
    data_version: SAFE_ID
    observation_window: FieldObservationWindow
    evidence_hashes: FieldEvidenceHashes
    stratum_counts: list[FieldStratumCount]
    reviewer_calibration: ReviewerCalibrationReceipt
    metrics: FieldValidationMetrics
    error_categories: list[FieldErrorCategory]
    safety_incidents: int = Field(ge=0)
    stop_work_events: int = Field(ge=0)
    data_protection_confirmed: bool
    licensing_confirmed: bool
    decision_th: str = Field(min_length=1)
    decision_en: str = Field(min_length=1)
    issued_at: datetime
    review_due_at: datetime
    accountable_role_ids: list[SAFE_ID] = Field(min_length=2)
    status: Literal["accepted", "rejected", "incomplete"]

    @model_validator(mode="after")
    def validate_acceptance(self) -> FieldValidationReceipt:
        if self.review_due_at <= self.issued_at:
            raise ValueError("Field-validation review date must follow issue time.")
        if self.review_due_at - self.issued_at > timedelta(days=30):
            raise ValueError("Field-validation receipts may be current for at most 30 days.")
        if self.generated_at < self.source_timestamp:
            raise ValueError("Field receipt generation cannot precede its source timestamp.")
        if self.issued_at < self.generated_at:
            raise ValueError("Field receipt issue time cannot precede generation time.")
        if self.source_timestamp < self.observation_window.end:
            raise ValueError("Field receipt source time cannot precede observation-window end.")
        if len(set(self.accountable_role_ids)) != len(self.accountable_role_ids):
            raise ValueError("Accountable role IDs must be unique.")
        if self.dataset_mode in {"fixture_demo", "candidate"} and (
            self.operational_status != "non_operational"
        ):
            raise ValueError("Fixture and candidate field receipts are non-operational.")
        if self.status == "accepted" and (
            self.reviewer_calibration.status != "passed"
            or not self.data_protection_confirmed
            or not self.licensing_confirmed
            or self.dataset_mode != "official_input"
            or self.operational_status != "planning_only"
            or any(value is None for value in self.evidence_hashes.model_dump().values())
            or any(value is None for value in self.metrics.model_dump().values())
            or not self.stratum_counts
            or sum(item.usable for item in self.stratum_counts) == 0
        ):
            raise ValueError(
                "Accepted field validation requires complete official-input planning evidence."
            )
        return self


class ReceiptVerificationResponse(StrictPilotModel):
    valid: bool
    acceptance_id: str | None = None
    acceptance_status: Literal["accepted", "rejected"]
    reason: str


class OperationalAssessmentRequest(StrictPilotModel):
    dataset_mode: Literal["fixture_demo", "candidate", "official_input"]
    study_area: SAFE_ID
    data_version: SAFE_ID
    expected_artifact_manifest_sha256: SHA256
    expected_field_validation_receipt_sha256: SHA256
    receipt: SignedAcceptanceReceipt | None = None


class OperationalAssessmentResponse(StrictPilotModel):
    operational_status: Literal["non_operational", "planning_only", "agency_operational"]
    acceptance_receipt_valid: bool
    reason: str


class AuditEntry(StrictPilotModel):
    sequence: int = Field(ge=1)
    occurred_at: datetime
    actor_subject: str
    actor_roles: list[PilotRole]
    action: SAFE_ID
    outcome: Literal["allowed", "denied", "completed", "failed"]
    details: dict[str, Any]
    previous_hash: SHA256
    event_hash: SHA256
    key_id: SAFE_ID
    authentication_code: SHA256


class AuditLogResponse(StrictPilotModel):
    chain_valid: bool
    entry_count: int = Field(ge=0)
    entries: list[AuditEntry]


class RetentionCategory(str, Enum):
    ACCEPTANCE_RECEIPT = "acceptance_receipt"
    AUDIT_LOG = "audit_log"
    SOURCE_MANIFEST = "source_manifest"
    DERIVED_CANDIDATE = "derived_candidate"
    TEMPORARY = "temporary"


class RetentionCatalogArtifact(StrictPilotModel):
    artifact_id: SAFE_ID
    relative_path: str = Field(min_length=1, max_length=240)
    category: RetentionCategory
    created_at: datetime
    legal_hold: bool = False
    sha256: SHA256
    evidence_binding_sha256: SHA256

    @field_validator("relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if (
            value != normalized
            or normalized.startswith("/")
            or ":" in normalized
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("Artifact path must be a normalized relative path.")
        return normalized

    @model_validator(mode="after")
    def require_category_namespace(self) -> RetentionCatalogArtifact:
        prefixes = {
            RetentionCategory.ACCEPTANCE_RECEIPT: "acceptance/",
            RetentionCategory.AUDIT_LOG: "audit/",
            RetentionCategory.SOURCE_MANIFEST: "source-manifests/",
            RetentionCategory.DERIVED_CANDIDATE: "derived-candidates/",
            RetentionCategory.TEMPORARY: "temporary/",
        }
        if not self.relative_path.startswith(prefixes[self.category]):
            raise ValueError("Artifact path does not match its server-defined category namespace.")
        return self


class RetentionCatalogPayload(StrictPilotModel):
    schema_version: Literal["1.0"] = "1.0"
    catalog_id: SAFE_ID
    generated_at: datetime
    review_due_at: datetime
    artifacts: list[RetentionCatalogArtifact] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def require_unique_artifact_ids_and_paths(self) -> RetentionCatalogPayload:
        if self.review_due_at <= self.generated_at:
            raise ValueError("Retention catalog review time must follow generation time.")
        if self.review_due_at - self.generated_at > timedelta(days=30):
            raise ValueError("Retention catalogs may be current for at most 30 days.")
        artifact_ids = [item.artifact_id for item in self.artifacts]
        paths = [item.relative_path for item in self.artifacts]
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Retention catalog artifact IDs must be unique.")
        if len(set(paths)) != len(paths):
            raise ValueError("Retention catalog paths must be unique.")
        categories = {item.artifact_id: item.category.value for item in self.artifacts}
        if any(
            categories.get(artifact_id) != category
            for artifact_id, category in MANDATORY_RETENTION_ARTIFACTS.items()
        ):
            raise ValueError(
                "Retention catalog must cover every mandatory pilot evidence artifact."
            )
        return self


class SignedRetentionCatalog(StrictPilotModel):
    payload: RetentionCatalogPayload
    signature: ManifestSignature


class RetentionRequest(StrictPilotModel):
    mode: Literal["dry_run", "execute"]
    artifact_ids: list[SAFE_ID] = Field(min_length=1, max_length=500)
    approval_phrase: str | None = None

    @field_validator("artifact_ids")
    @classmethod
    def require_unique_artifact_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("Retention request artifact IDs must be unique.")
        return value


class RetentionDecision(StrictPilotModel):
    artifact_id: str
    relative_path: str
    category: RetentionCategory
    disposition: Literal["retain", "delete", "missing", "blocked"]
    reason: str
    deleted: bool


class RetentionResponse(StrictPilotModel):
    policy_version: Literal["agency-pilot-retention-v1"]
    catalog_sha256: SHA256
    mode: Literal["dry_run", "execute"]
    evaluated_at: datetime
    decisions: list[RetentionDecision]
    deleted_count: int = Field(ge=0)


class DeploymentMonitoringResponse(StrictPilotModel):
    service_health: Literal["healthy", "degraded"]
    deployment_state: str
    identity_state: Literal["unconfigured", "configured"]
    audit_chain_state: Literal["unconfigured", "valid", "invalid"]
    retention_state: Literal["unconfigured", "configured"]
    acceptance_receipt_state: Literal["missing", "invalid", "expired", "accepted"]
    data_freshness_state: Literal["ready", "stale", "blocked", "unavailable"]
    data_source_timestamp: datetime
    checked_at: datetime
    operational_status: Literal["non_operational", "planning_only", "agency_operational"]


class ServedArtifactDigest(StrictPilotModel):
    artifact_id: SAFE_ID
    sha256: SHA256


class ServedResponseLineage(StrictPilotModel):
    response_id: SAFE_ID
    response_sha256: SHA256
    source_timestamp: datetime
    data_version: SAFE_ID
    artifacts: list[ServedArtifactDigest] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_artifacts(self) -> ServedResponseLineage:
        artifact_ids = [item.artifact_id for item in self.artifacts]
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Served-response artifact IDs must be unique.")
        return self


class OperationalArtifactManifest(StrictPilotModel):
    schema_version: Literal["1.0"] = "1.0"
    manifest_type: Literal["floodguard.served-responses.v1"]
    manifest_id: SAFE_ID
    dataset_mode: Literal["official_input"]
    study_area: SAFE_ID
    data_version: SAFE_ID
    source_timestamp: datetime
    served_responses: list[ServedResponseLineage] = Field(min_length=1)

    @model_validator(mode="after")
    def bind_every_response_to_manifest_scope(self) -> OperationalArtifactManifest:
        response_ids = [item.response_id for item in self.served_responses]
        response_hashes = [item.response_sha256 for item in self.served_responses]
        if len(set(response_ids)) != len(response_ids):
            raise ValueError("Served-response IDs must be unique.")
        if len(set(response_hashes)) != len(response_hashes):
            raise ValueError("Served-response digests must be unique.")
        if any(
            item.data_version != self.data_version or item.source_timestamp != self.source_timestamp
            for item in self.served_responses
        ):
            raise ValueError(
                "Every served response must match the manifest data version and source time."
            )
        return self
