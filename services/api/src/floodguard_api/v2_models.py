"""Additive GeoAI v2 and signed model-registry response contracts.

These models deliberately do not widen the established v1 ``ModelRun`` API.
They mirror the additive shared JSON Schemas and keep candidate evidence
report-only until separate promotion, field-validation, and agency receipts
are present.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$"
COMMIT_PATTERN = r"^[0-9a-fA-F]{7,40}$"

Sha256 = str
SafeId = str


class V2StrictModel(BaseModel):
    """Reject response drift at the API boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class V2CommonMetadata(V2StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    dataset_mode: Literal["fixture_demo", "candidate", "official_input"]
    operational_status: Literal[
        "non_operational",
        "planning_only",
        "agency_operational",
    ]
    source_timestamp: datetime
    generated_at: datetime
    confidence_class: Literal["low", "medium", "high"]
    source_name: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    official_warning: Literal[False] = False
    data_version: SafeId = Field(pattern=SAFE_ID_PATTERN)
    git_commit: str = Field(pattern=COMMIT_PATTERN)

    @model_validator(mode="after")
    def preserve_common_boundary(self) -> V2CommonMetadata:
        if len(self.assumptions) != len(set(self.assumptions)):
            raise ValueError("assumptions must be unique")
        if (
            self.dataset_mode in {"fixture_demo", "candidate"}
            and self.operational_status != "non_operational"
        ):
            raise ValueError("fixture and candidate v2 artifacts must be non-operational")
        return self


class ModelIdentityV2(V2StrictModel):
    model_id: SafeId | None = Field(default=None, pattern=SAFE_ID_PATTERN)
    model_revision: str | None = Field(default=None, min_length=1)
    model_family: Literal[
        "deterministic_sar_baseline",
        "weak_label_logistic",
        "geoai_unet_fpn",
        "segformer",
        "terramind",
        "prithvi_optical",
        "ensemble",
    ]
    backend: Literal[
        "deterministic",
        "sklearn",
        "smp",
        "segformer",
        "terramind",
        "prithvi",
        "ensemble",
    ]
    architecture: str | None = Field(default=None, min_length=1)
    encoder: str | None = Field(default=None, min_length=1)
    encoder_weights: str | None = Field(default=None, min_length=1)
    framework: str | None = Field(default=None, min_length=1)
    framework_version: str | None = Field(default=None, min_length=1)
    framework_commit: str | None = Field(default=None, pattern=COMMIT_PATTERN)
    model_sha256: Sha256 | None = Field(default=None, pattern=SHA256_PATTERN)


class ModelInputRowV2(V2StrictModel):
    role: SafeId = Field(pattern=SAFE_ID_PATTERN)
    modality: Literal[
        "sentinel_1_sar",
        "sentinel_2_optical",
        "terrain",
        "hydrology",
        "permanent_water",
        "land_cover",
        "rainfall",
        "reference_mask",
        "other_context",
    ]
    product_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    source_timestamp: datetime
    processing_allowed: bool


class FeatureContractV2(V2StrictModel):
    feature_schema_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    value_domain: Literal[
        "encoded_uint8",
        "normalized_float32",
        "physical_float32",
    ]
    dtype: Literal["uint8", "float32"]
    channel_count: int = Field(ge=1, le=64)
    channel_names: list[SafeId] = Field(min_length=1, max_length=64)
    preprocessing_sidecar_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    feature_stack_sha256: Sha256 = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def preserve_channel_contract(self) -> FeatureContractV2:
        if len(self.channel_names) != len(set(self.channel_names)):
            raise ValueError("channel_names must be unique")
        if self.channel_count != len(self.channel_names):
            raise ValueError("channel_count must equal channel_names length")
        return self


class TargetClassV2(V2StrictModel):
    index: int = Field(ge=0, le=255)
    name: SafeId = Field(pattern=SAFE_ID_PATTERN)
    training_role: Literal["positive", "negative", "ignore"]


class TargetContractV2(V2StrictModel):
    task: Literal["semantic_segmentation"] = "semantic_segmentation"
    class_schema_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    classes: list[TargetClassV2] = Field(min_length=2)
    positive_class_index: Literal[1] = 1
    ignore_index: Literal[255] = 255
    reference_mask_status: Literal[
        "blocked",
        "synthetic_fixture_only",
        "qualified_expert_or_adjudicated",
        "confirmed_for_model_purpose",
    ]
    label_release_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )

    @model_validator(mode="after")
    def preserve_class_contract(self) -> TargetContractV2:
        identities = {(item.index, item.name) for item in self.classes}
        if len(identities) != len(self.classes):
            raise ValueError("target classes must be unique")
        if not any(
            item.index == self.positive_class_index
            and item.training_role == "positive"
            for item in self.classes
        ):
            raise ValueError("positive_class_index must identify the positive class")
        return self


class TrainingLineageV2(V2StrictModel):
    input_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    training_dataset_manifest_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    label_release_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    prepared_tile_manifest_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    controlled_model_run_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    threshold_selection_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    calibration_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class PartitionContractV2(V2StrictModel):
    partition_manifest_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    training_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    calibration_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    final_holdout_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    train_ids: list[SafeId]
    calibration_ids: list[SafeId]
    final_holdout_ids: list[SafeId]

    @model_validator(mode="after")
    def preserve_partition_identity(self) -> PartitionContractV2:
        groups = (self.train_ids, self.calibration_ids, self.final_holdout_ids)
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("partition IDs must be unique within each partition")
        if set(self.train_ids) & set(self.calibration_ids):
            raise ValueError("training and calibration partitions overlap")
        if set(self.train_ids) & set(self.final_holdout_ids):
            raise ValueError("training and final-holdout partitions overlap")
        if set(self.calibration_ids) & set(self.final_holdout_ids):
            raise ValueError("calibration and final-holdout partitions overlap")
        return self


class InferenceContractV2(V2StrictModel):
    target_crs: str = Field(pattern=r"^EPSG:\d+$")
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    tile_size: int = Field(ge=1)
    overlap: int = Field(ge=0)
    stride: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    device: str = Field(min_length=1)
    probability_threshold: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def preserve_grid_order(self) -> InferenceContractV2:
        if any(value <= 0 for value in self.resolution):
            raise ValueError("resolution values must be positive")
        min_x, min_y, max_x, max_y = self.bounds
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("bounds must have positive area")
        if self.overlap >= self.tile_size or self.stride > self.tile_size:
            raise ValueError("tiling overlap and stride must fit the tile size")
        return self


class ModelRunV2(V2CommonMetadata):
    run_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    study_area_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    event_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    evidence_kind: Literal[
        "satellite_observed_extent",
        "optical_corroboration",
        "susceptibility_forecast",
        "scenario_assumption",
        "external_algorithmic_baseline",
        "human_field_observation",
    ]
    run_status: Literal["blocked", "prepared", "running", "completed", "failed"]
    model: ModelIdentityV2
    input_manifest_rows: list[ModelInputRowV2] = Field(min_length=1)
    feature_contract: FeatureContractV2
    target_contract: TargetContractV2
    training_lineage: TrainingLineageV2
    partition_contract: PartitionContractV2
    inference_contract: InferenceContractV2
    processing_allowed: bool
    can_feed_decision_layer: Literal[False] = False
    reason_blocked: str = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_run_gates(self) -> ModelRunV2:
        if self.processing_allowed and any(
            not row.processing_allowed for row in self.input_manifest_rows
        ):
            raise ValueError("all inputs must permit processing")
        if self.run_status == "completed":
            required_model = (
                self.model.model_id,
                self.model.model_revision,
                self.model.architecture,
                self.model.framework,
                self.model.framework_version,
                self.model.model_sha256,
            )
            required_lineage = (
                self.training_lineage.training_dataset_manifest_sha256,
                self.training_lineage.prepared_tile_manifest_sha256,
                self.partition_contract.partition_manifest_sha256,
                self.partition_contract.training_partition_sha256,
                self.partition_contract.calibration_partition_sha256,
                self.partition_contract.final_holdout_partition_sha256,
            )
            if any(value is None for value in (*required_model, *required_lineage)):
                raise ValueError("completed model runs require immutable model and lineage hashes")
            if not all(
                (
                    self.partition_contract.train_ids,
                    self.partition_contract.calibration_ids,
                    self.partition_contract.final_holdout_ids,
                )
            ):
                raise ValueError("completed model runs require train, calibration, and holdout IDs")
        return self


class EvaluationReferenceEvidenceV2(V2StrictModel):
    reference_mask_status: Literal[
        "blocked",
        "synthetic_fixture_only",
        "qualified_expert_or_adjudicated",
        "confirmed_for_model_purpose",
    ]
    reference_mask_sha256: Sha256 | None = Field(default=None, pattern=SHA256_PATTERN)
    label_release_sha256: Sha256 | None = Field(default=None, pattern=SHA256_PATTERN)
    reviewer_qualification_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class EvaluationPartitionEvidenceV2(V2StrictModel):
    partition_manifest_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    training_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    calibration_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    final_holdout_partition_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class EvaluationThresholdEvidenceV2(V2StrictModel):
    threshold: float | None = Field(default=None, ge=0, le=1)
    threshold_selection_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    selection_scope: Literal[
        "not_selected",
        "verified_calibration_projection_only",
    ]
    final_holdout_evaluated_during_selection: bool


class EvaluationMetricsV2(V2StrictModel):
    sample_count: int | None = Field(default=None, ge=1)
    true_positive: int | None = Field(default=None, ge=0)
    false_positive: int | None = Field(default=None, ge=0)
    false_negative: int | None = Field(default=None, ge=0)
    true_negative: int | None = Field(default=None, ge=0)
    iou: float | None = Field(default=None, ge=0, le=1)
    f1_dice: float | None = Field(default=None, ge=0, le=1)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    boundary_f1: float | None = Field(default=None, ge=0, le=1)
    signed_area_error_ratio: float | None = None
    absolute_area_error_ratio: float | None = Field(default=None, ge=0)
    brier_score: float | None = Field(default=None, ge=0, le=1)
    negative_log_likelihood: float | None = Field(default=None, ge=0)
    expected_calibration_error: float | None = Field(default=None, ge=0, le=1)

    def is_complete(self) -> bool:
        return all(value is not None for value in self.__dict__.values())


class EvaluationEventMetricsV2(V2StrictModel):
    event_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    sample_count: int = Field(ge=1)
    iou: float = Field(ge=0, le=1)
    f1_dice: float = Field(ge=0, le=1)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    absolute_area_error_ratio: float = Field(ge=0)
    brier_score: float = Field(ge=0, le=1)
    expected_calibration_error: float = Field(ge=0, le=1)


class EvaluationErrorStratumV2(V2StrictModel):
    category: SafeId = Field(pattern=SAFE_ID_PATTERN)
    coverage_status: Literal["measured", "insufficient", "absent"]
    cell_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)


class EvaluationCalibrationV2(V2StrictModel):
    status: Literal["not_evaluated", "evaluated", "failed"]
    method: str | None = Field(default=None, min_length=1)
    reliability_asset_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class EvaluationSelectivePredictionV2(V2StrictModel):
    status: Literal["not_evaluated", "evaluated", "failed"]
    risk_coverage_asset_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class EvaluationOodV2(V2StrictModel):
    status: Literal["not_evaluated", "passed", "failed"]
    method: str | None = Field(default=None, min_length=1)
    threshold: float | None = None
    score_asset_sha256: Sha256 | None = Field(default=None, pattern=SHA256_PATTERN)


class EvaluationDownstreamImpactV2(V2StrictModel):
    status: Literal["not_evaluated", "evaluated", "failed"]
    population_absolute_error: float | None = Field(default=None, ge=0)
    critical_road_false_negative_count: int | None = Field(default=None, ge=0)
    access_classification_flip_count: int | None = Field(default=None, ge=0)
    equity_gap_absolute_error: float | None = Field(default=None, ge=0)
    fpps_mean_absolute_error: float | None = Field(default=None, ge=0)
    fpps_rank_correlation: float | None = Field(default=None, ge=-1, le=1)
    action_class_flip_count: int | None = Field(default=None, ge=0)
    artifact_sha256: Sha256 | None = Field(default=None, pattern=SHA256_PATTERN)


class EvaluationRuntimeV2(V2StrictModel):
    training_seconds: float | None = Field(default=None, ge=0)
    calibration_seconds: float | None = Field(default=None, ge=0)
    inference_seconds: float | None = Field(default=None, ge=0)
    total_seconds: float | None = Field(default=None, ge=0)
    peak_memory_mb: float | None = Field(default=None, ge=0)
    device: str | None = Field(default=None, min_length=1)
    hardware_class: str | None = Field(default=None, min_length=1)


class ModelEvaluationV2(V2CommonMetadata):
    operational_status: Literal[
        "non_operational",
        "planning_only",
        "agency_operational",
    ]
    evaluation_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    experiment_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    study_area_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    event_ids: list[SafeId] = Field(min_length=1)
    model_run_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    model_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    model_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    model_run_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    controlled_result_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    evaluation_status: Literal["blocked", "completed_report_only", "failed"]
    evaluation_scope: Literal["not_evaluated", "final_holdout"]
    reference_evidence: EvaluationReferenceEvidenceV2
    partition_evidence: EvaluationPartitionEvidenceV2
    threshold_evidence: EvaluationThresholdEvidenceV2
    overall_metrics: EvaluationMetricsV2
    event_metrics: list[EvaluationEventMetricsV2]
    error_strata: list[EvaluationErrorStratumV2]
    calibration: EvaluationCalibrationV2
    selective_prediction: EvaluationSelectivePredictionV2
    ood_evaluation: EvaluationOodV2
    downstream_impact: EvaluationDownstreamImpactV2
    runtime: EvaluationRuntimeV2
    processing_allowed: bool
    can_feed_decision_layer: Literal[False] = False
    reason_blocked: str = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_evaluation_gates(self) -> ModelEvaluationV2:
        if len(self.event_ids) != len(set(self.event_ids)):
            raise ValueError("event_ids must be unique")
        if self.evaluation_status == "completed_report_only":
            evidence_hashes = (
                self.controlled_result_receipt_sha256,
                self.reference_evidence.reference_mask_sha256,
                self.reference_evidence.label_release_sha256,
                self.reference_evidence.reviewer_qualification_receipt_sha256,
                self.partition_evidence.partition_manifest_sha256,
                self.partition_evidence.training_partition_sha256,
                self.partition_evidence.calibration_partition_sha256,
                self.partition_evidence.final_holdout_partition_sha256,
                self.threshold_evidence.threshold_selection_receipt_sha256,
                self.calibration.reliability_asset_sha256,
                self.selective_prediction.risk_coverage_asset_sha256,
                self.ood_evaluation.score_asset_sha256,
                self.downstream_impact.artifact_sha256,
            )
            downstream_values = (
                self.downstream_impact.population_absolute_error,
                self.downstream_impact.critical_road_false_negative_count,
                self.downstream_impact.access_classification_flip_count,
                self.downstream_impact.equity_gap_absolute_error,
                self.downstream_impact.fpps_mean_absolute_error,
                self.downstream_impact.fpps_rank_correlation,
                self.downstream_impact.action_class_flip_count,
            )
            if self.evaluation_scope != "final_holdout":
                raise ValueError("completed report-only evaluation requires final holdout")
            if any(value is None for value in evidence_hashes):
                raise ValueError("completed report-only evaluation requires all evidence hashes")
            if (
                self.threshold_evidence.threshold is None
                or self.threshold_evidence.selection_scope
                != "verified_calibration_projection_only"
                or self.threshold_evidence.final_holdout_evaluated_during_selection
                or not self.overall_metrics.is_complete()
                or not self.event_metrics
                or not self.error_strata
                or self.calibration.status != "evaluated"
                or not self.calibration.method
                or self.selective_prediction.status != "evaluated"
                or self.ood_evaluation.status != "passed"
                or not self.ood_evaluation.method
                or self.ood_evaluation.threshold is None
                or self.downstream_impact.status != "evaluated"
                or any(value is None for value in downstream_values)
            ):
                raise ValueError("completed report-only evaluation is incomplete")
        return self


class ObservationGridV2(V2StrictModel):
    crs: str = Field(pattern=r"^EPSG:\d+$")
    resolution: tuple[float, float]
    bounds: tuple[float, float, float, float]
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    transform: tuple[float, float, float, float, float, float]
    nodata: float
    grid_sha256: Sha256 = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def preserve_grid_contract(self) -> ObservationGridV2:
        if any(value <= 0 for value in self.resolution):
            raise ValueError("resolution values must be positive")
        min_x, min_y, max_x, max_y = self.bounds
        if max_x <= min_x or max_y <= min_y:
            raise ValueError("bounds must have positive area")
        return self


class ObservationAssetV2(V2StrictModel):
    role: Literal[
        "flood_probability",
        "hard_extent",
        "validity_mask",
        "sensor_quality_mask",
        "model_uncertainty",
        "ood_score",
        "abstention_mask",
        "permanent_water_context",
        "preview",
        "stac_item",
    ]
    relative_path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    dtype: Literal["uint8", "float32", "json", "png"]
    band_name: str | None = Field(default=None, min_length=1)
    nodata: float | None = None
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def preserve_public_relative_path(self) -> ObservationAssetV2:
        normalized = self.relative_path.replace("\\", "/")
        if (
            self.relative_path.startswith(("/", "\\\\"))
            or "://" in self.relative_path
            or (len(self.relative_path) >= 2 and self.relative_path[1] == ":")
            or ".." in normalized.split("/")
        ):
            raise ValueError("observation assets require repository-relative paths")
        return self


class FloodObservationProductV2(V2CommonMetadata):
    product_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    run_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    study_area_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    event_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    evidence_kind: Literal[
        "satellite_observed_extent",
        "optical_corroboration",
        "susceptibility_forecast",
        "scenario_assumption",
        "external_algorithmic_baseline",
        "human_field_observation",
    ]
    source_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    model_run_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    model_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    evaluation_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    grid: ObservationGridV2
    assets: list[ObservationAssetV2] = Field(min_length=5)
    valid_coverage_fraction: float = Field(ge=0, le=1)
    abstained_fraction: float = Field(ge=0, le=1)
    sensor_quality_status: Literal["not_evaluated", "passed", "degraded", "failed"]
    ood_status: Literal["not_evaluated", "in_domain", "out_of_distribution"]
    review_required_reasons: list[str]
    unknown_cell_policy: Literal[
        "preserve_nodata_and_abstention_never_fill_as_dry"
    ] = "preserve_nodata_and_abstention_never_fill_as_dry"
    counts_as_observed_evidence: bool
    processing_allowed: bool
    can_feed_decision_layer: Literal[False] = False
    reason_blocked: str = Field(min_length=1)

    @model_validator(mode="after")
    def preserve_product_gates(self) -> FloodObservationProductV2:
        roles = {asset.role for asset in self.assets}
        required_roles = {
            "flood_probability",
            "validity_mask",
            "sensor_quality_mask",
            "model_uncertainty",
            "abstention_mask",
        }
        if not required_roles.issubset(roles):
            raise ValueError("observation product is missing a required uncertainty/QA asset")
        if len(self.assets) != len(roles):
            raise ValueError("observation asset roles must be unique")
        if len(self.review_required_reasons) != len(set(self.review_required_reasons)):
            raise ValueError("review_required_reasons must be unique")
        if self.dataset_mode in {"fixture_demo", "candidate"} and (
            self.counts_as_observed_evidence
            or self.operational_status != "non_operational"
        ):
            raise ValueError("fixture and candidate products cannot count as observed evidence")
        if (
            self.sensor_quality_status == "failed"
            or self.ood_status == "out_of_distribution"
            or self.valid_coverage_fraction == 0
            or not self.processing_allowed
        ) and self.counts_as_observed_evidence:
            raise ValueError(
                "failed, OOD, uncovered, or processing-blocked products "
                "cannot count as observations"
            )
        if self.abstained_fraction > 0 and not self.review_required_reasons:
            raise ValueError("abstained products require a review reason")
        return self


class ModelRegistryPayloadV1(V2StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    registry_entry_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    study_area_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    event_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    evidence_kind: Literal[
        "satellite_observed_extent",
        "optical_corroboration",
        "susceptibility_forecast",
        "scenario_assumption",
        "external_algorithmic_baseline",
        "human_field_observation",
    ]
    source_bundle_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    model_run_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    model_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    model_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    model_run_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    evaluation_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    evaluation_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    controlled_result_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    product_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    product_manifest_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    promotion_acceptance_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    field_validation_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    agency_acceptance_receipt_sha256: Sha256 | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    dataset_mode: Literal["fixture_demo", "candidate", "official_input"]
    operational_status: Literal[
        "non_operational",
        "planning_only",
        "agency_operational",
    ]
    registry_status: Literal[
        "candidate",
        "shadow",
        "approved",
        "revoked",
        "expired",
        "blocked",
    ]
    permitted_use: Literal["report_only", "shadow_only", "decision_input"]
    issued_at: datetime
    valid_from: datetime
    expires_at: datetime
    official_warning: Literal[False] = False
    can_feed_decision_layer: bool
    reason_blocked: str

    @model_validator(mode="after")
    def preserve_registry_gates(self) -> ModelRegistryPayloadV1:
        if self.valid_from < self.issued_at or self.expires_at <= self.valid_from:
            raise ValueError("registry validity window is invalid")
        if self.registry_status == "candidate":
            if (
                self.dataset_mode not in {"fixture_demo", "candidate"}
                or self.operational_status != "non_operational"
                or self.permitted_use != "report_only"
                or self.can_feed_decision_layer
            ):
                raise ValueError("candidate registry entries must remain report-only")
            if any(
                value is not None
                for value in (
                    self.promotion_acceptance_receipt_sha256,
                    self.field_validation_receipt_sha256,
                    self.agency_acceptance_receipt_sha256,
                )
            ):
                raise ValueError("candidate registry entries cannot carry acceptance receipts")
        if self.registry_status == "shadow" and (
            self.permitted_use != "shadow_only" or self.can_feed_decision_layer
        ):
            raise ValueError("shadow registry entries must remain shadow-only")
        if self.registry_status in {"revoked", "expired", "blocked"} and (
            self.can_feed_decision_layer
        ):
            raise ValueError("blocked registry states cannot feed the decision layer")
        if not self.can_feed_decision_layer and not self.reason_blocked:
            raise ValueError("non-eligible registry entries require reason_blocked")
        if self.can_feed_decision_layer:
            receipts = (
                self.controlled_result_receipt_sha256,
                self.promotion_acceptance_receipt_sha256,
                self.field_validation_receipt_sha256,
                self.agency_acceptance_receipt_sha256,
            )
            if (
                self.dataset_mode != "official_input"
                or self.operational_status
                not in {"planning_only", "agency_operational"}
                or self.registry_status != "approved"
                or self.permitted_use != "decision_input"
                or any(value is None for value in receipts)
                or self.reason_blocked
            ):
                raise ValueError("decision-input registry entry is missing approval evidence")
        return self


class ModelRegistrySignatureV1(V2StrictModel):
    algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"
    key_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    payload_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    value: Sha256 = Field(pattern=SHA256_PATTERN)


class SignedModelRegistryEntryV1(V2StrictModel):
    payload: ModelRegistryPayloadV1
    signature: ModelRegistrySignatureV1


class ModelRegistryEvidenceBundleV1(V2StrictModel):
    """Public-safe, context-bound expansion of one signed registry entry."""

    schema_version: Literal["1.0"] = "1.0"
    evidence_context_id: SafeId = Field(pattern=SAFE_ID_PATTERN)
    source_bundle_sha256: Sha256 = Field(pattern=SHA256_PATTERN)
    entry: SignedModelRegistryEntryV1
    model_run: ModelRunV2
    evaluation: ModelEvaluationV2
    product: FloodObservationProductV2
    official_warning: Literal[False] = False
    can_feed_decision_layer: Literal[False] = False
    reason_blocked: str = Field(min_length=1)
