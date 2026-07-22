"""Pydantic request and response models for the public API boundary."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from floodguard.scoring import (
    DEFAULT_WEIGHTS,
    assign_action_class,
    assign_action_reason_code,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Forbid accidental response drift and unreviewed request parameters."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DatasetMode(str, Enum):
    FIXTURE_DEMO = "fixture_demo"
    CANDIDATE = "candidate"
    OFFICIAL_INPUT = "official_input"


class OperationalStatus(str, Enum):
    NON_OPERATIONAL = "non_operational"
    PLANNING_ONLY = "planning_only"
    AGENCY_OPERATIONAL = "agency_operational"


class ConfidenceClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DataState(str, Enum):
    READY = "ready"
    STALE = "stale"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class ActionClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"


class ActionReasonCode(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    LOW_PRIORITY_SCORE = "low_priority_score"
    LIFE_SAFETY_EXPOSURE = "life_safety_exposure"
    CRITICAL_ROUTE_ACCESS = "critical_route_access"
    ESSENTIAL_SERVICE_ACCESS = "essential_service_access"
    RESILIENCE = "resilience"


class FreshnessState(str, Enum):
    CURRENT = "current"
    AGING = "aging"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


FRESHNESS_POLICY_VERSION = "source-freshness-v1"


class SourceComponent(StrictModel):
    source_component_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    source_version: str | None = Field(default=None, min_length=1)
    source_timestamp: datetime | None = None
    last_checked_at: datetime | None = None
    temporal_meaning: Literal[
        "observation_time",
        "valid_from",
        "publication_year",
        "extract_time",
        "generation_time",
        "unknown",
    ]
    freshness: FreshnessState
    freshness_policy_version: Literal["source-freshness-v1"]
    freshness_as_of: datetime
    attribution: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_freshness_semantics(self) -> SourceComponent:
        if self.freshness_as_of.tzinfo is None:
            raise ValueError("freshness_as_of must include a timezone")
        if self.source_timestamp is not None and self.source_timestamp.tzinfo is None:
            raise ValueError("source_timestamp must include a timezone")
        if self.last_checked_at is not None and self.last_checked_at.tzinfo is None:
            raise ValueError("last_checked_at must include a timezone")
        if self.source_timestamp is None and (
            self.temporal_meaning != "unknown"
            or self.freshness != FreshnessState.UNKNOWN
        ):
            raise ValueError(
                "sources without a timestamp require unknown temporal meaning and freshness"
            )
        if self.temporal_meaning == "unknown" and (
            self.source_timestamp is not None
            or self.freshness != FreshnessState.UNKNOWN
        ):
            raise ValueError(
                "unknown temporal meaning requires a missing timestamp and unknown freshness"
            )
        if self.freshness == FreshnessState.CURRENT and (
            self.source_timestamp is None or self.last_checked_at is None
        ):
            raise ValueError("current sources require source and last-checked timestamps")
        return self


class EvidenceState(StrictModel):
    evidence_type: Literal["modelled", "observed", "locally_confirmed"]
    granularity: Literal["area_summary", "road_segment", "facility"]
    confidence_class: ConfidenceClass
    confidence_reason: str = Field(min_length=1)
    permitted_use: Literal[
        "public_preparedness",
        "planning_only",
        "operational_authorized",
    ]
    required_gate: str | None = Field(default=None, min_length=1)
    gate_state: Literal["ready", "blocked", "not_applicable"]

    @model_validator(mode="after")
    def preserve_operational_gate(self) -> EvidenceState:
        if self.permitted_use == "operational_authorized" and (
            self.gate_state != "ready" or self.confidence_class != ConfidenceClass.HIGH
        ):
            raise ValueError("operational evidence requires a ready gate and high confidence")
        if self.gate_state == "blocked" and not self.required_gate:
            raise ValueError("blocked evidence requires the blocked gate identifier")
        if self.gate_state == "not_applicable" and self.required_gate is not None:
            raise ValueError("not-applicable evidence cannot declare a required gate")
        return self


class EvidenceContext(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_context_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
    study_area_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    evidence_package_id: str = Field(min_length=1)
    evidence_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_run_id: str | None = Field(default=None, min_length=1)
    dataset_mode: DatasetMode
    operational_status: OperationalStatus
    official_warning: bool
    generated_at: datetime
    source_components: list[SourceComponent] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_context_boundary(self) -> EvidenceContext:
        if self.dataset_mode in {DatasetMode.FIXTURE_DEMO, DatasetMode.CANDIDATE}:
            if self.official_warning:
                raise ValueError("fixture and candidate contexts cannot be official warnings")
            if self.operational_status == OperationalStatus.AGENCY_OPERATIONAL:
                raise ValueError("fixture and candidate contexts cannot be agency operational")
        component_ids = [item.source_component_id for item in self.source_components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("source component IDs must be unique")
        return self


class CommonMetadata(StrictModel):
    """Fields shared by decision, layer, model, and scenario artifacts."""

    schema_version: Literal["1.0"] = "1.0"
    dataset_mode: DatasetMode
    operational_status: OperationalStatus
    source_timestamp: datetime
    generated_at: datetime
    confidence_class: ConfidenceClass
    source_name: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    official_warning: bool
    data_version: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-fA-F]{7,40}$")

    @model_validator(mode="after")
    def preserve_non_official_boundary(self) -> CommonMetadata:
        if (
            self.dataset_mode
            in {
                DatasetMode.FIXTURE_DEMO,
                DatasetMode.CANDIDATE,
            }
            and self.official_warning
        ):
            raise ValueError("fixture and candidate artifacts cannot be official warnings")
        if (
            self.operational_status == OperationalStatus.AGENCY_OPERATIONAL
            and self.dataset_mode != DatasetMode.OFFICIAL_INPUT
        ):
            raise ValueError("agency-operational artifacts require official input")
        return self


class StatusResponse(CommonMetadata):
    evidence_context_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    evidence_package_id: str = Field(min_length=1)
    study_area: str = Field(min_length=1)
    data_state: DataState
    message_th: str = Field(min_length=1)
    message_en: str = Field(min_length=1)


class RoadEvidence(StrictModel):
    at_risk_segments: int = Field(ge=0)
    bridge_count: int = Field(ge=0)
    summary: str = Field(min_length=1)


class FacilityEvidence(StrictModel):
    facility_count: int = Field(ge=0)
    summary: str = Field(min_length=1)


class ScenarioDelta(StrictModel):
    scenario_id: str = Field(min_length=1)
    fpps_delta: float = Field(ge=-100, le=100)
    access_loss_delta: int


class AreaDecision(CommonMetadata):
    evidence_context_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    area_id: str = Field(min_length=1)
    area_name_th: str = Field(min_length=1)
    area_name_en: str = Field(min_length=1)
    fpps_0_100: float = Field(ge=0, le=100)
    action_class: ActionClass
    action_reason_code: ActionReasonCode
    top_reason: str = Field(min_length=1)
    flood_likelihood_0_100: float = Field(ge=0, le=100)
    exposure_0_100: float = Field(ge=0, le=100)
    access_gap_0_100: float = Field(ge=0, le=100)
    road_criticality_0_100: float = Field(ge=0, le=100)
    vulnerability_context_0_100: float = Field(ge=0, le=100)
    people_losing_30_min_access: int = Field(ge=0)
    equity_gap_ratio: float | None = Field(default=None, ge=0)
    road_evidence: RoadEvidence | None = None
    facility_evidence: FacilityEvidence | None = None
    scenario_delta: ScenarioDelta | None = None

    @model_validator(mode="after")
    def preserve_locked_fpps_contract(self) -> AreaDecision:
        components = {
            "flood_likelihood_0_100": self.flood_likelihood_0_100,
            "exposure_0_100": self.exposure_0_100,
            "access_gap_0_100": self.access_gap_0_100,
            "road_criticality_0_100": self.road_criticality_0_100,
            "vulnerability_context_0_100": self.vulnerability_context_0_100,
        }
        expected_score = round(
            sum(components[name] * weight for name, weight in DEFAULT_WEIGHTS.items()),
            2,
        )
        if abs(self.fpps_0_100 - expected_score) > 0.011:
            raise ValueError("fpps_0_100 is inconsistent with the locked 30/25/20/15/10 weights")
        expected_class = assign_action_class(
            {
                **components,
                "fpps_0_100": self.fpps_0_100,
                "confidence_class": self.confidence_class.value,
            }
        )
        if self.action_class.value != expected_class:
            raise ValueError("action_class is inconsistent with the locked A-E rules")
        expected_reason = assign_action_reason_code(
            {
                **components,
                "fpps_0_100": self.fpps_0_100,
                "confidence_class": self.confidence_class.value,
                "action_class": self.action_class.value,
            }
        )
        if self.action_reason_code.value != expected_reason:
            raise ValueError("action_reason_code is inconsistent with the locked A-E rules")
        return self


class LayerCatalogItem(CommonMetadata):
    evidence_context_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    evidence_package_id: str = Field(min_length=1)
    layer_id: str = Field(min_length=1)
    title_th: str = Field(min_length=1)
    title_en: str = Field(min_length=1)
    role_visibility: list[Literal["public", "command", "studio"]] = Field(min_length=1)
    format: Literal["geojson", "cog", "pmtiles"]
    url: str = Field(min_length=1)
    data_state: DataState
    model_run_id: str | None = None
    evidence_state: EvidenceState
    source_components: list[SourceComponent] = Field(min_length=1)
    attribution: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_role_and_use_boundary(self) -> LayerCatalogItem:
        if "public" in self.role_visibility and self.evidence_state.permitted_use not in {
            "public_preparedness",
            "operational_authorized",
        }:
            raise ValueError("public layers require public-preparedness permission")
        if self.evidence_state.permitted_use == "operational_authorized" and (
            self.dataset_mode != DatasetMode.OFFICIAL_INPUT
            or self.operational_status != OperationalStatus.AGENCY_OPERATIONAL
            or not self.model_run_id
        ):
            raise ValueError(
                "operational layers require official agency context and a bound model run"
            )
        return self


class PublicPreparednessArea(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_context_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    area_id: str = Field(min_length=1)
    area_name_th: str = Field(min_length=1)
    area_name_en: str = Field(min_length=1)
    planning_priority_0_100: float = Field(ge=0, le=100)
    evidence_sufficiency: ConfidenceClass
    recommendation_code: ActionReasonCode
    source_timestamp: datetime
    freshness: FreshnessState
    current_conditions_confirmed: bool


class EvidenceRecord(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    evidence_record_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
    )
    evidence_context: EvidenceContext
    evidence_scope: str = Field(min_length=1)
    model_id: str | None = Field(default=None, min_length=1)
    model_version: str | None = Field(default=None, min_length=1)
    model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evaluation_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision: Literal["not_evaluated", "passed", "failed", "blocked"]
    decision_authority: str | None = Field(default=None, min_length=1)
    decision_at: datetime | None = None
    operational_authorized: bool
    blockers: list[str]
    generated_at: datetime

    @model_validator(mode="after")
    def preserve_audit_boundary(self) -> EvidenceRecord:
        if self.decision == "passed" and (
            not self.decision_authority or self.decision_at is None
        ):
            raise ValueError("passed evidence requires decision authority and time")
        if (self.decision_authority is None) != (self.decision_at is None):
            raise ValueError("decision authority and time must be recorded together")
        if self.operational_authorized:
            if (
                self.evidence_context.dataset_mode != DatasetMode.OFFICIAL_INPUT
                or self.evidence_context.operational_status
                != OperationalStatus.AGENCY_OPERATIONAL
                or not self.evidence_context.model_run_id
                or self.decision != "passed"
                or not self.decision_authority
                or self.decision_at is None
                or not self.model_id
                or not self.model_version
                or not self.model_sha256
                or not self.evaluation_sha256
                or self.blockers
            ):
                raise ValueError("operational evidence requires complete accepted authority")
        elif not self.blockers:
            raise ValueError("non-authorized evidence records must expose blockers")
        return self


class StudyArea(CommonMetadata):
    study_area_id: str = Field(min_length=1)
    title_th: str = Field(min_length=1)
    title_en: str = Field(min_length=1)
    area_count: int = Field(ge=0)
    data_state: DataState


class ScenarioParameterDefinition(StrictModel):
    name: str = Field(min_length=1)
    value_type: Literal["integer", "string"]
    required: bool
    default: str | int
    minimum: int | None = None
    maximum: int | None = None
    allowed_values: list[str] | None = None
    note: str = Field(min_length=1)


class ScenarioDefinition(StrictModel):
    scenario_id: Literal["add_temporary_shelter", "close_road"]
    title_th: str = Field(min_length=1)
    title_en: str = Field(min_length=1)
    description_th: str = Field(min_length=1)
    description_en: str = Field(min_length=1)
    parameters: list[ScenarioParameterDefinition]
    backend_config_version: Literal[
        "fixture-access-scenarios-v1",
        "mae-sai-candidate-access-scenarios-v1",
    ]
    access_method: Literal["nearest_facility_shortest_path_threshold"]


class TemporaryShelterParameters(StrictModel):
    node_id: Literal["P2A"] = "P2A"
    capacity: int = Field(default=500, ge=1, le=5000)


class CloseRoadParameters(StrictModel):
    road_id: Literal["FG-RD-002"] = "FG-RD-002"


class MaeSaiTemporaryShelterParameters(StrictModel):
    node_id: Literal["N-99.9742609-20.4457677"] = "N-99.9742609-20.4457677"
    capacity: int = Field(default=500, ge=1, le=5000)


class MaeSaiCloseRoadParameters(StrictModel):
    edge_id: Literal["MS-EDGE-0008687"] = "MS-EDGE-0008687"


class ScenarioRunRequest(StrictModel):
    scenario_id: Literal["add_temporary_shelter", "close_road"]
    study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"] = (
        "fixture_thailand_demo"
    )
    parameters: dict[str, str | int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_server_owned_parameters(self) -> ScenarioRunRequest:
        if (
            self.study_area == "mae_sai_candidate_v1"
            and self.scenario_id == "add_temporary_shelter"
        ):
            validated = MaeSaiTemporaryShelterParameters.model_validate(self.parameters)
        elif self.study_area == "mae_sai_candidate_v1":
            validated = MaeSaiCloseRoadParameters.model_validate(self.parameters)
        elif self.scenario_id == "add_temporary_shelter":
            validated = TemporaryShelterParameters.model_validate(self.parameters)
        else:
            validated = CloseRoadParameters.model_validate(self.parameters)
        self.parameters = validated.model_dump()
        return self


class ScenarioAreaResult(StrictModel):
    area_id: str = Field(min_length=1)
    baseline_people_losing_30_min_access: int = Field(ge=0)
    scenario_people_losing_30_min_access: int = Field(ge=0)
    change_people_losing_30_min_access: int
    baseline_equity_gap_ratio: float | None = Field(default=None, ge=0)
    scenario_equity_gap_ratio: float | None = Field(default=None, ge=0)
    change_equity_gap_ratio: float | None = None


class ScenarioOverallResult(StrictModel):
    baseline_people_losing_30_min_access: int = Field(ge=0)
    scenario_people_losing_30_min_access: int = Field(ge=0)
    change_people_losing_30_min_access: int
    baseline_max_equity_gap_ratio: float | None = Field(default=None, ge=0)
    scenario_max_equity_gap_ratio: float | None = Field(default=None, ge=0)
    change_max_equity_gap_ratio: float | None = None


class ScenarioRunResponse(CommonMetadata):
    run_id: str = Field(min_length=1)
    scenario_id: Literal["add_temporary_shelter", "close_road"]
    study_area: Literal["fixture_thailand_demo", "mae_sai_candidate_v1"]
    parameters: dict[str, str | int]
    run_status: Literal["completed"]
    result_state: DataState
    backend_config_version: Literal[
        "fixture-access-scenarios-v1",
        "mae-sai-candidate-access-scenarios-v1",
    ]
    access_method: Literal["nearest_facility_shortest_path_threshold"]
    fpps_recalculated: Literal[False]
    input_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    input_receipt_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    overall: ScenarioOverallResult
    areas: list[ScenarioAreaResult]

    @model_validator(mode="after")
    def preserve_candidate_scenario_lineage(self) -> ScenarioRunResponse:
        if self.study_area == "mae_sai_candidate_v1" and (
            self.input_manifest_sha256 is None or self.input_receipt_sha256 is None
        ):
            raise ValueError("Mae Sai candidate scenarios require immutable input lineage")
        return self


class ModelInputManifestRow(StrictModel):
    product_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    source_timestamp: datetime
    processing_allowed: bool


class BandTransform(StrictModel):
    name: str = Field(min_length=1)
    physical_min: float
    physical_max: float
    units: str = Field(min_length=1)
    description: str = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_physical_range(self) -> BandTransform:
        if self.physical_max <= self.physical_min:
            raise ValueError("physical_max must be greater than physical_min")
        return self


class PreprocessingContract(StrictModel):
    method: str = Field(min_length=1)
    value_domain: Literal["uint8_0_255", "float_0_1", "physical_units"]
    sidecar_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    transforms: list[BandTransform] = Field(max_length=8)


class SpatialPartition(StrictModel):
    spatial_group_id: str = Field(min_length=1)
    split: Literal["train", "holdout"]
    bounds: tuple[float, float, float, float]

    @model_validator(mode="after")
    def preserve_ordered_bounds(self) -> SpatialPartition:
        min_x, min_y, max_x, max_y = self.bounds
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("spatial partition bounds must have positive area")
        return self


class ValidationMetrics(StrictModel):
    iou: float | None = Field(default=None, ge=0, le=1)
    f1_dice: float | None = Field(default=None, ge=0, le=1)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    area_error_ratio: float | None = Field(default=None, ge=0)
    brier_score: float | None = Field(default=None, ge=0, le=1)
    expected_calibration_error: float | None = Field(default=None, ge=0, le=1)


class ModelRun(CommonMetadata):
    run_id: str = Field(min_length=1)
    study_area: str = Field(min_length=1)
    model_family: Literal[
        "deterministic_sar_baseline",
        "weak_label_logistic",
        "geoai",
    ]
    run_status: Literal["blocked", "prepared", "running", "completed", "failed"]
    geoai_version: str | None = None
    geoai_commit: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{7,40}$")
    model_id: str | None = None
    model_revision: str | None = None
    model_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{64}$",
    )
    architecture: str | None = None
    encoder: str | None = None
    encoder_weights: str | None = None
    num_channels: int | None = Field(default=None, ge=1, le=8)
    channel_names: list[str]
    preprocessing: PreprocessingContract
    input_manifest_rows: list[ModelInputManifestRow] = Field(min_length=1)
    encoded_feature_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    reference_mask_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    prepared_tile_manifest_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    spatial_holdout_ids: list[str]
    spatial_partitions: list[SpatialPartition]
    reference_mask_id: str = Field(min_length=1)
    reference_mask_status: str = Field(min_length=1)
    target_crs: str = Field(min_length=1)
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    tile_size: int = Field(ge=1)
    overlap: int = Field(ge=0)
    stride: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    device: str = Field(min_length=1)
    flood_class_index: int = Field(ge=0)
    probability_threshold: float = Field(ge=0, le=1)
    external_output_workspace: str = Field(min_length=1)
    processing_scope: str = Field(min_length=1)
    processing_allowed: bool
    can_feed_decision_layer: bool
    reason_blocked: str
    validation_metrics: ValidationMetrics
    error_categories: list[str]

    @model_validator(mode="after")
    def preserve_model_promotion_gates(self) -> ModelRun:
        if (
            self.dataset_mode
            in {
                DatasetMode.FIXTURE_DEMO,
                DatasetMode.CANDIDATE,
            }
            and self.can_feed_decision_layer
        ):
            raise ValueError("fixture and candidate runs cannot feed the decision layer")
        if not self.processing_allowed and self.can_feed_decision_layer:
            raise ValueError("blocked processing cannot feed the decision layer")
        if not self.can_feed_decision_layer and not self.reason_blocked:
            raise ValueError("non-promotable model runs require reason_blocked")
        if self.can_feed_decision_layer:
            if self.dataset_mode is not DatasetMode.OFFICIAL_INPUT:
                raise ValueError("only official input runs can feed the decision layer")
            if self.operational_status is OperationalStatus.NON_OPERATIONAL:
                raise ValueError("non-operational runs cannot feed the decision layer")
            if self.confidence_class is ConfidenceClass.LOW:
                raise ValueError("low-confidence runs cannot feed the decision layer")
            if self.run_status != "completed":
                raise ValueError("only completed runs can feed the decision layer")
            if self.reference_mask_status != "confirmed_for_model_purpose":
                raise ValueError(
                    "decision-eligible runs require a reference mask confirmed "
                    "for the model purpose"
                )
            if self.reason_blocked:
                raise ValueError("decision-eligible runs cannot retain a blocked reason")
            if any(
                metric is None
                for metric in (
                    self.validation_metrics.iou,
                    self.validation_metrics.f1_dice,
                    self.validation_metrics.precision,
                    self.validation_metrics.recall,
                    self.validation_metrics.area_error_ratio,
                    self.validation_metrics.brier_score,
                    self.validation_metrics.expected_calibration_error,
                )
            ):
                raise ValueError("decision-eligible runs require complete validation metrics")
        if self.processing_allowed and any(
            not row.processing_allowed for row in self.input_manifest_rows
        ):
            raise ValueError("all manifest rows must permit processing")
        if self.model_family == "geoai" and self.run_status in {
            "prepared",
            "running",
            "completed",
        }:
            if self.run_status == "completed" and self.model_sha256 is None:
                raise ValueError("completed GeoAI runs require a model checksum")
            if (
                self.encoded_feature_sha256 is None
                or self.reference_mask_sha256 is None
                or self.prepared_tile_manifest_sha256 is None
            ):
                raise ValueError(
                    "prepared GeoAI runs require feature, mask, and tile-manifest hashes"
                )
            if not 6 <= len(self.preprocessing.transforms) <= 8:
                raise ValueError("prepared GeoAI runs require six to eight band transforms")
            if [item.name for item in self.preprocessing.transforms] != self.channel_names:
                raise ValueError("GeoAI transform order must match channel_names")
            if not self.spatial_holdout_ids:
                raise ValueError("prepared GeoAI runs require spatial_holdout_ids")
            if len(self.spatial_partitions) < 2:
                raise ValueError("prepared GeoAI runs require at least two partitions")
            partition_ids = [item.spatial_group_id for item in self.spatial_partitions]
            if len(partition_ids) != len(set(partition_ids)):
                raise ValueError("spatial partition IDs must be unique")
            if not any(item.split == "train" for item in self.spatial_partitions):
                raise ValueError("prepared GeoAI runs require a training partition")
            holdout_ids = {
                item.spatial_group_id for item in self.spatial_partitions if item.split == "holdout"
            }
            if holdout_ids != set(self.spatial_holdout_ids):
                raise ValueError("holdout partition IDs must match spatial_holdout_ids")
            run_min_x, run_min_y, run_max_x, run_max_y = self.bounds
            for partition in self.spatial_partitions:
                min_x, min_y, max_x, max_y = partition.bounds
                if min_x < run_min_x or min_y < run_min_y or max_x > run_max_x or max_y > run_max_y:
                    raise ValueError("spatial partitions must stay within run bounds")
            for index, first in enumerate(self.spatial_partitions):
                for second in self.spatial_partitions[index + 1 :]:
                    if _bounds_have_overlapping_interior(first.bounds, second.bounds):
                        raise ValueError("spatial partition interiors cannot overlap")
            roles = {row.role for row in self.input_manifest_rows}
            if not {"pre_event_sar", "post_event_sar", "reference_mask"}.issubset(roles):
                raise ValueError("GeoAI runs require pre, post, and reference-mask receipts")
        return self


def _bounds_have_overlapping_interior(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return max(first[0], second[0]) < min(first[2], second[2]) and max(first[1], second[1]) < min(
        first[3], second[3]
    )


class ReadinessItem(StrictModel):
    check_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    status: DataState
    source_status: str = Field(min_length=1)
    severity: Literal["critical", "high", "medium", "low"]
    observed: str = Field(min_length=1)
    required: str = Field(min_length=1)
    reason_blocked: str
    source_timestamp: datetime
    confidence_class: ConfidenceClass
    assumptions: list[str] = Field(min_length=1)


class BriefResponse(CommonMetadata):
    area_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    bilingual: Literal[True]
    media_type: Literal["text/markdown; charset=utf-8"]
    content_markdown: str = Field(min_length=1)


class HealthResponse(StrictModel):
    """Process health only; this intentionally has no data-freshness fields."""

    service_status: Literal["healthy"]
    api_version: Literal["v1"]
    service_name: Literal["floodguard-artifact-api"]


class ApiError(StrictModel):
    error: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    data_state: DataState | None = None
