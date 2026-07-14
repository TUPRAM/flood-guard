"""Fail-closed Sentinel-1 and optical late-fusion research contracts.

This module combines probabilities produced by separately trained SAR and
optical encoders.  It does not train either encoder, read source rasters, or
claim that fusion improves flood mapping.  Optical evidence is used only after
an explicit quality policy passes; otherwise the SAR probability is preserved
bit-for-bit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

import pandas as pd


SAR_ONLY_MODE = "SAR only"
SAR_OPTICAL_MODE = "SAR + optical"
OPTICAL_ONLY_VALIDATION_MODE = "Optical only"

QUALITY_POLICY_SCHEMA = "floodguard.fusion_quality_policy.v1"
MODEL_CONTRACT_SCHEMA = "floodguard.sar_optical_late_fusion_model.v1"
DECISION_OUTPUT_SCHEMA = "floodguard.sar_optical_fusion_decision.v1"
EVALUATION_OUTPUT_SCHEMA = "floodguard.sar_optical_fusion_evaluation.v1"

OPTICAL_SOURCE_FAMILIES: tuple[str, ...] = ("sentinel2", "theos2")
CONFIDENCE_CLASSES: tuple[str, ...] = ("low", "medium", "high")
VALIDATION_MODES: tuple[str, ...] = (
    SAR_ONLY_MODE,
    OPTICAL_ONLY_VALIDATION_MODE,
    SAR_OPTICAL_MODE,
)

SAR_INPUT_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "sar_probability_0_1",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

OPTICAL_INPUT_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "optical_candidate_id",
    "optical_source_family",
    "optical_probability_0_1",
    "cloud_shadow_fraction_0_1",
    "temporal_offset_hours",
    "valid_fraction_0_1",
    "overlap_fraction_0_1",
    "grid_alignment_status",
    "calibration_status",
    "provenance_status",
    "rights_status",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

THEOS2_GATE_COLUMNS: tuple[str, ...] = (
    "theos2_permission_status",
    "theos2_event_overlap_status",
    "theos2_temporal_alignment_status",
    "theos2_grid_alignment_status",
)

OPTICAL_ASSESSMENT_COLUMNS: tuple[str, ...] = (
    *OPTICAL_INPUT_COLUMNS,
    *THEOS2_GATE_COLUMNS,
    "optical_eligible",
    "optical_eligibility_reason",
    "fusion_fallback_reason",
    "quality_policy_schema",
    "quality_policy_sha256",
    "quality_policy_json",
)

DECISION_OUTPUT_COLUMNS: tuple[str, ...] = (
    "cell_id",
    "flood_probability_0_1",
    "decision_input_mode",
    "decision_layer_use_status",
    "sar_probability_0_1",
    "optical_probability_0_1",
    "selected_optical_candidate_id",
    "selected_optical_source_family",
    "optical_candidate_count",
    "fusion_fallback_reason",
    "fallback_equivalence_status",
    "cloud_shadow_fraction_0_1",
    "temporal_offset_hours",
    "valid_fraction_0_1",
    "overlap_fraction_0_1",
    "sar_source_timestamp",
    "optical_source_timestamp",
    "source_timestamp",
    "confidence_class",
    "assumptions",
    "quality_policy_schema",
    "quality_policy_sha256",
    "quality_policy_json",
    "model_contract_schema",
    "model_contract_sha256",
    "model_contract_json",
    "output_schema",
)

EVALUATION_OUTPUT_COLUMNS: tuple[str, ...] = (
    "evaluation_slice",
    "validation_mode",
    "sample_count",
    "true_positive",
    "false_positive",
    "false_negative",
    "true_negative",
    "iou",
    "f1_dice",
    "precision",
    "recall",
    "area_error_ratio",
    "decision_threshold",
    "fallback_equivalence_passed",
    "fusion_fallback_reason",
    "improvement_claim_status",
    "source_timestamp",
    "confidence_class",
    "assumptions",
    "quality_policy_schema",
    "quality_policy_sha256",
    "quality_policy_json",
    "model_contract_schema",
    "model_contract_sha256",
    "model_contract_json",
    "output_schema",
)


class FusionError(ValueError):
    """Raised when a fusion policy, contract, or input violates its contract."""


@dataclass(frozen=True)
class FusionQualityPolicy:
    """Explicit optical eligibility limits persisted with each fusion result."""

    max_cloud_shadow_fraction_0_1: float
    max_temporal_offset_hours: float
    min_valid_fraction_0_1: float
    min_overlap_fraction_0_1: float
    required_grid_alignment_status: str = "aligned_to_sar_grid"
    required_calibration_status: str = "calibrated"
    required_provenance_status: str = "verified"
    required_rights_status: str = "approved_for_model_input"
    required_theos2_permission_status: str = "approved_for_model_input"
    required_theos2_event_overlap_status: str = "confirmed"
    required_theos2_temporal_alignment_status: str = "confirmed"
    required_theos2_grid_alignment_status: str = "confirmed"
    optical_source_priority: tuple[str, ...] = OPTICAL_SOURCE_FAMILIES
    schema: str = QUALITY_POLICY_SCHEMA

    def __post_init__(self) -> None:
        _validate_fraction(
            self.max_cloud_shadow_fraction_0_1,
            "max_cloud_shadow_fraction_0_1",
        )
        _validate_fraction(
            self.min_valid_fraction_0_1,
            "min_valid_fraction_0_1",
        )
        _validate_fraction(
            self.min_overlap_fraction_0_1,
            "min_overlap_fraction_0_1",
        )
        if (
            isinstance(self.max_temporal_offset_hours, bool)
            or not math.isfinite(float(self.max_temporal_offset_hours))
            or float(self.max_temporal_offset_hours) < 0
        ):
            raise FusionError("max_temporal_offset_hours must be finite and non-negative.")
        if self.schema != QUALITY_POLICY_SCHEMA:
            raise FusionError(f"Fusion quality policy schema must be {QUALITY_POLICY_SCHEMA!r}.")
        status_fields = (
            "required_grid_alignment_status",
            "required_calibration_status",
            "required_provenance_status",
            "required_rights_status",
            "required_theos2_permission_status",
            "required_theos2_event_overlap_status",
            "required_theos2_temporal_alignment_status",
            "required_theos2_grid_alignment_status",
        )
        for field_name in status_fields:
            if not str(getattr(self, field_name)).strip():
                raise FusionError(f"{field_name} must not be blank.")
        priority = tuple(self.optical_source_priority)
        if len(priority) != len(set(priority)):
            raise FusionError("optical_source_priority must not contain duplicates.")
        if set(priority) != set(OPTICAL_SOURCE_FAMILIES):
            raise FusionError(
                "optical_source_priority must list sentinel2 and theos2 exactly once."
            )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible, fully explicit policy record."""

        return {
            "schema": self.schema,
            "max_cloud_shadow_fraction_0_1": float(
                self.max_cloud_shadow_fraction_0_1
            ),
            "max_temporal_offset_hours": float(self.max_temporal_offset_hours),
            "min_valid_fraction_0_1": float(self.min_valid_fraction_0_1),
            "min_overlap_fraction_0_1": float(self.min_overlap_fraction_0_1),
            "required_grid_alignment_status": self.required_grid_alignment_status,
            "required_calibration_status": self.required_calibration_status,
            "required_provenance_status": self.required_provenance_status,
            "required_rights_status": self.required_rights_status,
            "required_theos2_permission_status": (
                self.required_theos2_permission_status
            ),
            "required_theos2_event_overlap_status": (
                self.required_theos2_event_overlap_status
            ),
            "required_theos2_temporal_alignment_status": (
                self.required_theos2_temporal_alignment_status
            ),
            "required_theos2_grid_alignment_status": (
                self.required_theos2_grid_alignment_status
            ),
            "optical_source_priority": list(self.optical_source_priority),
        }

    @property
    def canonical_json(self) -> str:
        """Return the canonical JSON persisted in result rows and manifests."""

        return _canonical_json(self.to_dict())

    @property
    def sha256(self) -> str:
        """Return the canonical policy hash."""

        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FusionModelContract:
    """Versioned research contract for separate encoders and late fusion."""

    sar_model_id: str
    optical_model_id: str
    fusion_model_id: str
    sar_input_features: tuple[str, ...]
    optical_input_features: tuple[str, ...]
    sar_weight: float
    optical_weight: float
    modality_dropout_probability: float
    optical_source_family: str = "sentinel2"
    sar_encoder_role: str = "separate_sar_encoder"
    optical_encoder_role: str = "separate_optical_encoder"
    late_fusion_method: str = "weighted_probability_average_after_encoders"
    modality_dropout_rule: str = "optical_branch_only_sar_branch_never_dropped"
    validation_modes: tuple[str, ...] = VALIDATION_MODES
    training_status: str = "contract_only_no_training_or_improvement_claim"
    schema: str = MODEL_CONTRACT_SCHEMA

    def __post_init__(self) -> None:
        for field_name in (
            "sar_model_id",
            "optical_model_id",
            "fusion_model_id",
            "sar_encoder_role",
            "optical_encoder_role",
            "late_fusion_method",
            "modality_dropout_rule",
            "training_status",
            "optical_source_family",
        ):
            if not str(getattr(self, field_name)).strip():
                raise FusionError(f"{field_name} must not be blank.")
        if self.schema != MODEL_CONTRACT_SCHEMA:
            raise FusionError(f"Fusion model schema must be {MODEL_CONTRACT_SCHEMA!r}.")
        if self.optical_source_family not in OPTICAL_SOURCE_FAMILIES:
            raise FusionError(
                "optical_source_family must be either sentinel2 or theos2."
            )
        _validate_feature_names(self.sar_input_features, "sar_input_features")
        _validate_feature_names(self.optical_input_features, "optical_input_features")
        for value, name in (
            (self.sar_weight, "sar_weight"),
            (self.optical_weight, "optical_weight"),
        ):
            if (
                isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise FusionError(f"{name} must be finite and greater than zero.")
        if not math.isclose(
            float(self.sar_weight) + float(self.optical_weight),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise FusionError("sar_weight and optical_weight must sum to 1.0.")
        _validate_fraction(
            self.modality_dropout_probability,
            "modality_dropout_probability",
        )
        if not 0.0 < float(self.modality_dropout_probability) < 1.0:
            raise FusionError(
                "modality_dropout_probability must be greater than zero and below one."
            )
        if self.sar_encoder_role != "separate_sar_encoder":
            raise FusionError("sar_encoder_role must declare a separate SAR encoder.")
        if self.optical_encoder_role != "separate_optical_encoder":
            raise FusionError("optical_encoder_role must declare a separate optical encoder.")
        if self.late_fusion_method != "weighted_probability_average_after_encoders":
            raise FusionError(
                "late_fusion_method must match the weighted probability implementation."
            )
        if tuple(self.validation_modes) != VALIDATION_MODES:
            raise FusionError(
                "validation_modes must be SAR only, Optical only, SAR + optical."
            )
        if self.modality_dropout_rule != "optical_branch_only_sar_branch_never_dropped":
            raise FusionError(
                "Modality dropout must affect only the optical branch; SAR cannot be dropped."
            )
        if self.training_status != "contract_only_no_training_or_improvement_claim":
            raise FusionError(
                "training_status must preserve the no-training/no-improvement boundary."
            )

    def to_dict(self) -> dict[str, object]:
        """Return the complete model/training contract as JSON-compatible data."""

        return {
            "schema": self.schema,
            "sar_model_id": self.sar_model_id,
            "optical_model_id": self.optical_model_id,
            "fusion_model_id": self.fusion_model_id,
            "encoders": {
                "sar": {
                    "role": self.sar_encoder_role,
                    "input_features": list(self.sar_input_features),
                },
                "optical": {
                    "role": self.optical_encoder_role,
                    "source_family": self.optical_source_family,
                    "input_features": list(self.optical_input_features),
                },
            },
            "late_fusion": {
                "method": self.late_fusion_method,
                "sar_weight": float(self.sar_weight),
                "optical_weight": float(self.optical_weight),
            },
            "modality_dropout": {
                "probability": float(self.modality_dropout_probability),
                "rule": self.modality_dropout_rule,
            },
            "validation_modes": list(self.validation_modes),
            "training_status": self.training_status,
        }

    @property
    def canonical_json(self) -> str:
        """Return canonical JSON suitable for persistence and hashing."""

        return _canonical_json(self.to_dict())

    @property
    def sha256(self) -> str:
        """Return the canonical model-contract hash."""

        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()


def write_fusion_quality_policy(
    policy: FusionQualityPolicy,
    output_path: str | Path,
) -> Path:
    """Persist an immutable quality-policy JSON document."""

    return _write_contract_json(
        policy.to_dict(),
        content_sha256=policy.sha256,
        output_path=output_path,
        label="Fusion quality policy",
    )


def write_fusion_model_contract(
    contract: FusionModelContract,
    output_path: str | Path,
) -> Path:
    """Persist an immutable model/training-contract JSON document."""

    return _write_contract_json(
        contract.to_dict(),
        content_sha256=contract.sha256,
        output_path=output_path,
        label="Fusion model contract",
    )


def assess_optical_candidates(
    optical_candidates: pd.DataFrame | None,
    policy: FusionQualityPolicy,
) -> pd.DataFrame:
    """Assess every optical candidate independently against the quality policy.

    THEOS-2 candidates must pass four additional permission, event-overlap,
    temporal-alignment, and grid-alignment gates.  A failed THEOS-2 candidate
    does not prevent a separate eligible Sentinel-2 candidate from being used.
    """

    if optical_candidates is None or optical_candidates.empty:
        return pd.DataFrame(columns=OPTICAL_ASSESSMENT_COLUMNS)
    _require_columns(optical_candidates, OPTICAL_INPUT_COLUMNS, "optical candidate")
    frame = optical_candidates.copy()
    for column in THEOS2_GATE_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    _require_nonblank(frame, "cell_id", "optical candidate")
    _require_nonblank(frame, "optical_candidate_id", "optical candidate")
    _require_common_output_fields(frame, "optical candidate")
    if frame.duplicated(["cell_id", "optical_candidate_id"]).any():
        raise FusionError(
            "Optical candidates must have unique cell_id/optical_candidate_id pairs."
        )
    invalid_families = sorted(
        set(frame["optical_source_family"].astype(str))
        - set(OPTICAL_SOURCE_FAMILIES)
    )
    if invalid_families:
        raise FusionError(
            "Unsupported optical_source_family value(s): " + ", ".join(invalid_families)
        )

    assessed: list[dict[str, object]] = []
    for record in frame.to_dict(orient="records"):
        reasons = _optical_ineligibility_reasons(record, policy)
        reason_text = "eligible" if not reasons else "|".join(reasons)
        assessed.append(
            {
                **record,
                "optical_eligible": not reasons,
                "optical_eligibility_reason": reason_text,
                "fusion_fallback_reason": (
                    "none" if not reasons else f"optical_candidate_ineligible:{reason_text}"
                ),
                "quality_policy_schema": policy.schema,
                "quality_policy_sha256": policy.sha256,
                "quality_policy_json": policy.canonical_json,
            }
        )
    return pd.DataFrame(assessed).loc[:, OPTICAL_ASSESSMENT_COLUMNS]


def run_late_fusion(
    sar_inputs: pd.DataFrame,
    optical_candidates: pd.DataFrame | None,
    *,
    policy: FusionQualityPolicy,
    contract: FusionModelContract,
) -> pd.DataFrame:
    """Fuse separately supplied probabilities or preserve SAR exactly.

    Candidate selection is deterministic and policy-controlled.  Only an
    independently eligible optical candidate may alter a SAR probability.
    """

    sar = _validated_sar_inputs(sar_inputs)
    optical = assess_optical_candidates(optical_candidates, policy)
    if not optical.empty:
        extra_cells = sorted(set(optical["cell_id"].astype(str)) - set(sar["cell_id"]))
        if extra_cells:
            raise FusionError(
                "Optical candidates reference unknown SAR cell_id value(s): "
                + ", ".join(extra_cells)
            )
        incompatible = (
            optical["optical_eligible"].astype(bool)
            & optical["optical_source_family"].ne(contract.optical_source_family)
        )
        if incompatible.any():
            reason = (
                "optical_source_family_not_supported_by_model_contract:"
                + contract.optical_source_family
            )
            optical.loc[incompatible, "optical_eligible"] = False
            optical.loc[incompatible, "optical_eligibility_reason"] = reason
            optical.loc[incompatible, "fusion_fallback_reason"] = (
                "optical_candidate_ineligible:" + reason
            )

    priority = {
        source: index for index, source in enumerate(policy.optical_source_priority)
    }
    rows: list[dict[str, object]] = []
    for sar_record in sar.to_dict(orient="records"):
        cell_id = str(sar_record["cell_id"])
        candidates = optical.loc[optical["cell_id"].astype(str) == cell_id].copy()
        eligible = candidates.loc[candidates["optical_eligible"].astype(bool)].copy()
        selected: Mapping[str, object] | None = None
        if not eligible.empty:
            eligible["_source_priority"] = eligible["optical_source_family"].map(priority)
            eligible["_cloud_shadow_fraction"] = eligible[
                "cloud_shadow_fraction_0_1"
            ].map(float)
            eligible["_absolute_offset"] = eligible["temporal_offset_hours"].map(
                lambda value: abs(float(value))
            )
            eligible["_negative_valid"] = eligible["valid_fraction_0_1"].map(
                lambda value: -float(value)
            )
            eligible["_negative_overlap"] = eligible["overlap_fraction_0_1"].map(
                lambda value: -float(value)
            )
            eligible = eligible.sort_values(
                by=[
                    "_source_priority",
                    "_cloud_shadow_fraction",
                    "_absolute_offset",
                    "_negative_valid",
                    "_negative_overlap",
                    "optical_candidate_id",
                ],
                kind="mergesort",
            )
            selected = eligible.iloc[0].to_dict()

        sar_probability = float(sar_record["sar_probability_0_1"])
        if selected is None:
            probability = sar_probability
            mode = SAR_ONLY_MODE
            optical_probability: float | None = None
            selected_id = ""
            selected_family = ""
            optical_timestamp = ""
            source_timestamp = str(sar_record["source_timestamp"])
            confidence = str(sar_record["confidence_class"])
            fallback_reason = _candidate_fallback_reason(candidates)
            fallback_status = (
                "passed" if _float_bits_equal(probability, sar_probability) else "failed"
            )
            assumptions = (
                f"{sar_record['assumptions']} Optical evidence did not pass the "
                "declared fusion policy; the SAR probability is preserved exactly. "
                "Research-only; no fusion-improvement claim."
            )
            quality_values: dict[str, object] = {
                "cloud_shadow_fraction_0_1": None,
                "temporal_offset_hours": None,
                "valid_fraction_0_1": None,
                "overlap_fraction_0_1": None,
            }
        else:
            optical_probability = float(selected["optical_probability_0_1"])
            probability = (
                float(contract.sar_weight) * sar_probability
                + float(contract.optical_weight) * optical_probability
            )
            mode = SAR_OPTICAL_MODE
            selected_id = str(selected["optical_candidate_id"])
            selected_family = str(selected["optical_source_family"])
            optical_timestamp = str(selected["source_timestamp"])
            source_timestamp = max(
                str(sar_record["source_timestamp"]),
                optical_timestamp,
            )
            confidence = _conservative_confidence(
                str(sar_record["confidence_class"]),
                str(selected["confidence_class"]),
            )
            fallback_reason = "none"
            fallback_status = "not_applicable_fused"
            assumptions = (
                f"{sar_record['assumptions']} Optical candidate {selected_id}: "
                f"{selected['assumptions']} Separate encoder probabilities combined "
                "by versioned late fusion. Research-only; no improvement claim."
            )
            quality_values = {
                "cloud_shadow_fraction_0_1": float(
                    selected["cloud_shadow_fraction_0_1"]
                ),
                "temporal_offset_hours": float(selected["temporal_offset_hours"]),
                "valid_fraction_0_1": float(selected["valid_fraction_0_1"]),
                "overlap_fraction_0_1": float(selected["overlap_fraction_0_1"]),
            }

        rows.append(
            {
                "cell_id": cell_id,
                "flood_probability_0_1": probability,
                "decision_input_mode": mode,
                "decision_layer_use_status": "research_sidecar_not_used_by_fpps",
                "sar_probability_0_1": sar_probability,
                "optical_probability_0_1": optical_probability,
                "selected_optical_candidate_id": selected_id,
                "selected_optical_source_family": selected_family,
                "optical_candidate_count": len(candidates),
                "fusion_fallback_reason": fallback_reason,
                "fallback_equivalence_status": fallback_status,
                **quality_values,
                "sar_source_timestamp": str(sar_record["source_timestamp"]),
                "optical_source_timestamp": optical_timestamp,
                "source_timestamp": source_timestamp,
                "confidence_class": confidence,
                "assumptions": assumptions,
                "quality_policy_schema": policy.schema,
                "quality_policy_sha256": policy.sha256,
                "quality_policy_json": policy.canonical_json,
                "model_contract_schema": contract.schema,
                "model_contract_sha256": contract.sha256,
                "model_contract_json": contract.canonical_json,
                "output_schema": DECISION_OUTPUT_SCHEMA,
            }
        )

    decisions = pd.DataFrame(rows, columns=DECISION_OUTPUT_COLUMNS)
    verify_sar_fallback_equivalence(decisions)
    return decisions


def verify_sar_fallback_equivalence(decisions: pd.DataFrame) -> bool:
    """Raise if any ``SAR only`` decision differs from its SAR probability."""

    _require_columns(
        decisions,
        (
            "decision_input_mode",
            "flood_probability_0_1",
            "sar_probability_0_1",
            "fallback_equivalence_status",
        ),
        "fusion decision",
    )
    invalid_modes = sorted(
        set(decisions["decision_input_mode"].astype(str))
        - {SAR_ONLY_MODE, SAR_OPTICAL_MODE}
    )
    if invalid_modes:
        raise FusionError(
            "Fusion decisions contain invalid decision_input_mode value(s): "
            + ", ".join(invalid_modes)
        )
    for row in decisions.loc[
        decisions["decision_input_mode"] == SAR_ONLY_MODE
    ].to_dict(orient="records"):
        if not _float_bits_equal(
            row["flood_probability_0_1"], row["sar_probability_0_1"]
        ):
            raise FusionError(
                f"SAR fallback changed probability bytes for cell_id={row.get('cell_id', '')}."
            )
        if row["fallback_equivalence_status"] != "passed":
            raise FusionError("SAR fallback must record fallback_equivalence_status=passed.")
    return True


def evaluate_fusion_modes(
    sar_inputs: pd.DataFrame,
    optical_candidates: pd.DataFrame | None,
    *,
    policy: FusionQualityPolicy,
    contract: FusionModelContract,
    reference_column: str = "reference_flood_extent",
    decision_threshold: float = 0.5,
) -> pd.DataFrame:
    """Evaluate SAR-all, paired SAR, optical-only, and fused probabilities.

    SAR paired-subset, optical-only, and fused rows use the same optical-eligible
    cells.  Metrics are descriptive research evidence and never assert that
    fusion improves the SAR baseline.
    """

    _validate_fraction(decision_threshold, "decision_threshold")
    _require_columns(sar_inputs, (reference_column,), "fusion evaluation SAR")
    sar = _validated_sar_inputs(sar_inputs)
    references = _validated_reference_labels(sar_inputs[reference_column], reference_column)
    sar[reference_column] = references.to_numpy()
    decisions = run_late_fusion(
        sar,
        optical_candidates,
        policy=policy,
        contract=contract,
    )
    fallback_passed = verify_sar_fallback_equivalence(decisions)
    fallback_reasons = sorted(
        set(
            decisions.loc[
                decisions["decision_input_mode"] == SAR_ONLY_MODE,
                "fusion_fallback_reason",
            ].astype(str)
        )
    )
    fallback_reason = "none" if not fallback_reasons else "|".join(fallback_reasons)
    indexed_sar = sar.set_index("cell_id", drop=False)
    indexed_decisions = decisions.set_index("cell_id", drop=False)
    paired_ids = list(
        decisions.loc[
            decisions["decision_input_mode"] == SAR_OPTICAL_MODE,
            "cell_id",
        ].astype(str)
    )

    slices: tuple[tuple[str, str, Sequence[object], Sequence[int]], ...] = (
        (
            "sar_all",
            SAR_ONLY_MODE,
            list(sar["sar_probability_0_1"]),
            list(sar[reference_column]),
        ),
        (
            "sar_paired_subset",
            SAR_ONLY_MODE,
            list(indexed_sar.loc[paired_ids, "sar_probability_0_1"])
            if paired_ids
            else [],
            list(indexed_sar.loc[paired_ids, reference_column]) if paired_ids else [],
        ),
        (
            "optical_only",
            OPTICAL_ONLY_VALIDATION_MODE,
            list(indexed_decisions.loc[paired_ids, "optical_probability_0_1"])
            if paired_ids
            else [],
            list(indexed_sar.loc[paired_ids, reference_column]) if paired_ids else [],
        ),
        (
            "fused",
            SAR_OPTICAL_MODE,
            list(indexed_decisions.loc[paired_ids, "flood_probability_0_1"])
            if paired_ids
            else [],
            list(indexed_sar.loc[paired_ids, reference_column]) if paired_ids else [],
        ),
    )

    timestamp = max(decisions["source_timestamp"].astype(str))
    confidence = _lowest_confidence(decisions["confidence_class"].astype(str))
    assumptions = (
        "Descriptive held-out fusion comparison contract. SAR-all and paired-SAR "
        "are reported separately; optical-only and fused use the same eligible "
        "paired cells. Research-only; no improvement or operational-readiness claim."
    )
    rows: list[dict[str, object]] = []
    for slice_name, validation_mode, probabilities, labels in slices:
        metrics = _binary_probability_metrics(
            probabilities,
            labels,
            threshold=float(decision_threshold),
        )
        rows.append(
            {
                "evaluation_slice": slice_name,
                "validation_mode": validation_mode,
                **metrics,
                "decision_threshold": float(decision_threshold),
                "fallback_equivalence_passed": fallback_passed,
                "fusion_fallback_reason": fallback_reason,
                "improvement_claim_status": "not_claimed_descriptive_metrics_only",
                "source_timestamp": timestamp,
                "confidence_class": confidence,
                "assumptions": assumptions,
                "quality_policy_schema": policy.schema,
                "quality_policy_sha256": policy.sha256,
                "quality_policy_json": policy.canonical_json,
                "model_contract_schema": contract.schema,
                "model_contract_sha256": contract.sha256,
                "model_contract_json": contract.canonical_json,
                "output_schema": EVALUATION_OUTPUT_SCHEMA,
            }
        )
    return pd.DataFrame(rows, columns=EVALUATION_OUTPUT_COLUMNS)


def _validated_sar_inputs(sar_inputs: pd.DataFrame) -> pd.DataFrame:
    _require_columns(sar_inputs, SAR_INPUT_COLUMNS, "SAR input")
    if sar_inputs.empty:
        raise FusionError("SAR inputs must not be empty.")
    frame = sar_inputs.copy()
    _require_nonblank(frame, "cell_id", "SAR input")
    _require_common_output_fields(frame, "SAR input")
    if frame["cell_id"].astype(str).duplicated().any():
        raise FusionError("SAR inputs must have unique cell_id values.")
    frame["cell_id"] = frame["cell_id"].astype(str)
    frame["sar_probability_0_1"] = frame["sar_probability_0_1"].map(
        lambda value: _required_probability(value, "sar_probability_0_1")
    )
    return frame


def _optical_ineligibility_reasons(
    record: Mapping[str, object],
    policy: FusionQualityPolicy,
) -> list[str]:
    reasons: list[str] = []
    probability = _optional_number(
        record.get("optical_probability_0_1"), "optical_probability_0_1"
    )
    if probability is None:
        reasons.append("missing_optical_probability")
    elif not 0 <= probability <= 1:
        raise FusionError("optical_probability_0_1 must be between 0 and 1.")

    cloud = _quality_number(
        record,
        "cloud_shadow_fraction_0_1",
        reasons,
        minimum=0.0,
        maximum=1.0,
    )
    if cloud is not None and cloud > policy.max_cloud_shadow_fraction_0_1:
        reasons.append("cloud_shadow_exceeds_limit")
    offset = _quality_number(
        record,
        "temporal_offset_hours",
        reasons,
        minimum=None,
        maximum=None,
    )
    if offset is not None and abs(offset) > policy.max_temporal_offset_hours:
        reasons.append("temporal_offset_exceeds_limit")
    valid = _quality_number(
        record,
        "valid_fraction_0_1",
        reasons,
        minimum=0.0,
        maximum=1.0,
    )
    if valid is not None and valid < policy.min_valid_fraction_0_1:
        reasons.append("valid_fraction_below_limit")
    overlap = _quality_number(
        record,
        "overlap_fraction_0_1",
        reasons,
        minimum=0.0,
        maximum=1.0,
    )
    if overlap is not None and overlap < policy.min_overlap_fraction_0_1:
        reasons.append("overlap_fraction_below_limit")

    _status_reason(
        record,
        "grid_alignment_status",
        policy.required_grid_alignment_status,
        "grid_alignment_not_approved",
        reasons,
    )
    _status_reason(
        record,
        "calibration_status",
        policy.required_calibration_status,
        "calibration_not_approved",
        reasons,
    )
    _status_reason(
        record,
        "provenance_status",
        policy.required_provenance_status,
        "provenance_not_approved",
        reasons,
    )
    _status_reason(
        record,
        "rights_status",
        policy.required_rights_status,
        "rights_not_approved",
        reasons,
    )

    if str(record.get("optical_source_family", "")) == "theos2":
        for column, required, reason in (
            (
                "theos2_permission_status",
                policy.required_theos2_permission_status,
                "theos2_permission_not_approved",
            ),
            (
                "theos2_event_overlap_status",
                policy.required_theos2_event_overlap_status,
                "theos2_event_overlap_not_confirmed",
            ),
            (
                "theos2_temporal_alignment_status",
                policy.required_theos2_temporal_alignment_status,
                "theos2_temporal_alignment_not_confirmed",
            ),
            (
                "theos2_grid_alignment_status",
                policy.required_theos2_grid_alignment_status,
                "theos2_grid_alignment_not_confirmed",
            ),
        ):
            _status_reason(record, column, required, reason, reasons)
    return reasons


def _quality_number(
    record: Mapping[str, object],
    column: str,
    reasons: list[str],
    *,
    minimum: float | None,
    maximum: float | None,
) -> float | None:
    value = _optional_number(record.get(column), column)
    if value is None:
        reasons.append(f"missing_{column}")
        return None
    if minimum is not None and value < minimum:
        raise FusionError(f"{column} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise FusionError(f"{column} must be at most {maximum}.")
    return value


def _status_reason(
    record: Mapping[str, object],
    column: str,
    required: str,
    reason: str,
    reasons: list[str],
) -> None:
    if str(record.get(column, "")).strip() != required:
        reasons.append(reason)


def _candidate_fallback_reason(candidates: pd.DataFrame) -> str:
    if candidates.empty:
        return "no_optical_candidate"
    parts = []
    for row in candidates.sort_values(
        ["optical_source_family", "optical_candidate_id"], kind="mergesort"
    ).to_dict(orient="records"):
        parts.append(
            f"{row['optical_source_family']}:{row['optical_candidate_id']}:"
            f"{row['optical_eligibility_reason']}"
        )
    return "no_eligible_optical_candidate;" + ";".join(parts)


def _binary_probability_metrics(
    probabilities: Sequence[object],
    references: Sequence[int],
    *,
    threshold: float,
) -> dict[str, object]:
    if len(probabilities) != len(references):
        raise FusionError("Probabilities and reference labels must have equal length.")
    if not probabilities:
        return {
            "sample_count": 0,
            "true_positive": None,
            "false_positive": None,
            "false_negative": None,
            "true_negative": None,
            "iou": None,
            "f1_dice": None,
            "precision": None,
            "recall": None,
            "area_error_ratio": None,
        }
    numeric = [_required_probability(value, "evaluation probability") for value in probabilities]
    labels = [int(value) for value in references]
    predictions = [int(value >= threshold) for value in numeric]
    true_positive = sum(
        prediction == 1 and reference == 1
        for prediction, reference in zip(predictions, labels, strict=True)
    )
    false_positive = sum(
        prediction == 1 and reference == 0
        for prediction, reference in zip(predictions, labels, strict=True)
    )
    false_negative = sum(
        prediction == 0 and reference == 1
        for prediction, reference in zip(predictions, labels, strict=True)
    )
    true_negative = sum(
        prediction == 0 and reference == 0
        for prediction, reference in zip(predictions, labels, strict=True)
    )
    predicted_area = true_positive + false_positive
    reference_area = true_positive + false_negative
    return {
        "sample_count": len(numeric),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "iou": _safe_ratio(
            true_positive,
            true_positive + false_positive + false_negative,
        ),
        "f1_dice": _safe_ratio(
            2 * true_positive,
            2 * true_positive + false_positive + false_negative,
        ),
        "precision": _safe_ratio(true_positive, true_positive + false_positive),
        "recall": _safe_ratio(true_positive, true_positive + false_negative),
        "area_error_ratio": _safe_ratio(
            predicted_area - reference_area,
            reference_area,
        ),
    }


def _validated_reference_labels(values: pd.Series, column: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any() or not set(numeric.astype(float)).issubset({0.0, 1.0}):
        raise FusionError(f"{column} must contain only binary 0/1 values.")
    return numeric.astype(int)


def _require_common_output_fields(frame: pd.DataFrame, label: str) -> None:
    for column in ("source_timestamp", "assumptions"):
        _require_nonblank(frame, column, label)
    invalid_confidence = sorted(
        set(frame["confidence_class"].astype(str)) - set(CONFIDENCE_CLASSES)
    )
    if invalid_confidence:
        raise FusionError(
            f"{label} has invalid confidence_class value(s): "
            + ", ".join(invalid_confidence)
        )
    frame["source_timestamp"] = frame["source_timestamp"].map(
        lambda value: _normalized_timestamp(value, f"{label} source_timestamp")
    )


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise FusionError(f"Missing required {label} column(s): {', '.join(missing)}")


def _require_nonblank(frame: pd.DataFrame, column: str, label: str) -> None:
    values = frame[column]
    blank = values.isna() | values.astype(str).str.strip().eq("")
    if blank.any():
        raise FusionError(f"{label} {column} must not be blank.")


def _required_probability(value: object, label: str) -> float:
    numeric = _optional_number(value, label)
    if numeric is None or not 0 <= numeric <= 1:
        raise FusionError(f"{label} must be between 0 and 1.")
    return numeric


def _optional_number(value: object, label: str) -> float | None:
    if value is None or (not isinstance(value, (list, tuple, dict)) and pd.isna(value)):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if _is_boolean(value):
        raise FusionError(f"{label} must be numeric, not boolean.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise FusionError(f"{label} must be numeric.") from exc
    if not math.isfinite(numeric):
        raise FusionError(f"{label} must be finite.")
    return numeric


def _validate_fraction(value: object, label: str) -> None:
    numeric = _optional_number(value, label)
    if numeric is None or not 0 <= numeric <= 1:
        raise FusionError(f"{label} must be between 0 and 1.")


def _validate_feature_names(features: Sequence[str], label: str) -> None:
    names = tuple(str(feature).strip() for feature in features)
    if not names or any(not name for name in names):
        raise FusionError(f"{label} must contain non-blank feature names.")
    if len(names) != len(set(names)):
        raise FusionError(f"{label} must not contain duplicates.")


def _conservative_confidence(first: str, second: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return first if rank[first] <= rank[second] else second


def _lowest_confidence(values: Sequence[str]) -> str:
    result = "high"
    for value in values:
        result = _conservative_confidence(result, str(value))
    return result


def _float_bits_equal(first: object, second: object) -> bool:
    return struct.pack("!d", float(first)) == struct.pack("!d", float(second))


def _is_boolean(value: object) -> bool:
    value_type = type(value)
    return isinstance(value, bool) or (
        value_type.__module__ == "numpy" and value_type.__name__ in {"bool", "bool_"}
    )


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return 0.0 if numerator == 0 else None
    return round(float(numerator) / float(denominator), 6)


def _normalized_timestamp(value: object, label: str) -> str:
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FusionError(f"{label} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FusionError(f"{label} must include an explicit timezone.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _write_contract_json(
    payload: Mapping[str, object],
    *,
    content_sha256: str,
    output_path: str | Path,
    label: str,
) -> Path:
    target = Path(output_path)
    if target.suffix.lower() != ".json":
        raise FusionError(f"{label} output must use .json.")
    if target.exists():
        raise FusionError(f"{label} output is immutable and already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {**payload, "content_sha256": content_sha256}
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
