"""Build model-blinded, QGIS-compatible label-factory review bundles."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

import pandas as pd

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.event_registry import (
    EventRegistryError,
    reject_absolute_local_path,
)
from floodguard.label_factory.human_roles import (
    HumanRolePackageError,
    validate_human_role_package,
)
from floodguard.label_factory.processing_alignment import (
    ProcessingAlignmentError,
    ReceiptInput,
    load_processing_alignment_receipt,
    processed_bounds,
    processing_assets_by_id,
    validate_processing_alignment_receipt,
)
from floodguard.label_factory.rights_clearance import (
    RightsClearanceError,
    validate_rights_clearance_package,
)
from floodguard.label_factory.review_derivatives import (
    DERIVATIVE_CONTEXT_LAYER_ROLES,
    ReviewDerivativeLineageError,
    ReceiptInput as DerivativeReceiptInput,
    validate_derivative_context_against_receipt,
    validate_review_derivative_lineage_receipt,
)
from floodguard.label_factory.supported_query_pool import (
    SupportedQueryPoolError,
    load_supported_query_derivation,
)
from floodguard.label_factory.tiling import GridContractError, validate_projected_metre_crs

REVIEW_INPUT_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "tile_id",
    "event_id",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "pre_source_asset_ids",
    "event_source_asset_ids",
    "pre_product_ids",
    "event_product_ids",
    "pre_acquisition_utc",
    "event_acquisition_utc",
    "pre_source_sha256s",
    "event_source_sha256s",
    "feature_schema_version",
    "query_size_pixels",
    "resolution_m",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "crs",
    "dataset_role",
    "review_status",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

REVIEW_VISIBLE_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "tile_id",
    "event_id",
    "grid_id",
    "grid_contract_sha256",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "pre_source_asset_ids",
    "event_source_asset_ids",
    "pre_product_ids",
    "event_product_ids",
    "pre_acquisition_utc",
    "event_acquisition_utc",
    "pre_source_sha256s",
    "event_source_sha256s",
    "feature_schema_version",
    "query_size_pixels",
    "resolution_m",
    "dataset_role",
    "review_purpose",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "geometry_wkt",
    "crs",
    "review_status",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

ANNOTATION_TEMPLATE_COLUMNS: tuple[str, ...] = (
    "annotation_id",
    "event_id",
    "tile_id",
    "query_region_id",
    "reviewer_id",
    "review_revision",
    "review_stage",
    "review_purpose",
    "primary_class",
    "class_code",
    "confidence",
    "ambiguity_reason_codes",
    "evidence_layers_used",
    "review_complete",
    "reviewed_extent_status",
    "reviewed_extent",
    "geometry_wkt",
    "review_started_at_utc",
    "review_finished_at_utc",
    "protocol_version",
    "tool_version",
    "model_predictions_visible",
    "other_reviewer_annotations_visible",
    "created_at_utc",
    "locked_at_utc",
    "supersedes_annotation_id",
    "source_timestamp",
    "assumptions",
)

SENSITIVE_REVIEW_COLUMNS: frozenset[str] = frozenset(
    {
        "weak_label",
        "weak_label_fraction",
        "weak_reference_fraction",
        "weak_positive_fraction",
        "weak_uncertain_fraction",
        "weak_unreviewed_fraction",
        "weak_boundary_query",
        "weak_summary_manifest_sha256",
        "logistic_probability",
        "boosted_probability",
        "mean_logistic_probability",
        "mean_boosted_probability",
        "mean_committee_probability",
        "committee_distance_from_0_5",
        "mean_logistic_query_score",
        "mean_boosted_query_score",
        "mean_committee_query_score",
        "entropy",
        "entropy_p90",
        "entropy_score",
        "absolute_disagreement",
        "jensen_shannon_disagreement",
        "active_score",
        "model_disagreement",
        "probability_disagreement_p90",
        "binary_disagreement_fraction",
        "boundary_score",
        "diversity_score",
        "selection_score",
        "selection_rank",
        "selection_reason",
        "priority_score",
        "recommended_review_priority",
        "operator_internal_only",
        "reviewer_delivery_allowed",
        "operator_use",
        "preview_path",
        "preview_sha256",
        "preview_manifest_sha256",
    }
)

ACTIVE_SELECTION_COLUMNS: frozenset[str] = frozenset(
    {
        "active_score",
        "uncertainty",
        "absolute_disagreement",
        "jensen_shannon_disagreement",
        "logistic_probability",
        "boosted_probability",
        "mean_logistic_probability",
        "mean_boosted_probability",
        "mean_committee_probability",
        "committee_distance_from_0_5",
        "mean_logistic_query_score",
        "mean_boosted_query_score",
        "mean_committee_query_score",
        "entropy",
        "entropy_p90",
        "entropy_score",
        "model_disagreement",
        "probability_disagreement_p90",
        "binary_disagreement_fraction",
        "boundary_score",
        "diversity_score",
        "priority_score",
        "recommended_review_priority",
        "operator_internal_only",
        "reviewer_delivery_allowed",
        "operator_use",
        "selection_lane",
        "selection_basis",
        "selection_order",
        "selection_purpose",
        "selection_policy_version",
        "selection_creates_flood_truth",
        "selection_score",
        "selection_rank",
        "selection_reason",
        "uncertainty_rank",
        "disagreement_rank",
        "boundary_rank",
        "sampling_stratum",
        "sampling_stratum_population",
        "sampling_stratum_quota",
        "inclusion_probability",
        "round0_stratum",
        "hard_stratum",
        "round_id",
        "requested_active_quota",
        "requested_hard_stratum_quota",
        "requested_random_control_quota",
        "achieved_active_quota",
        "achieved_hard_stratum_quota",
        "achieved_random_control_quota",
    }
)

APPROVED_CONTEXT_LAYER_ROLES: frozenset[str] = frozenset(
    {
        "pre_event_vv",
        "event_time_vv",
        "pre_event_vh",
        "event_time_vh",
        "permanent_water_context",
        "dem_hillshade",
        "slope",
        "land_cover",
        "rivers",
        "roads",
        "settlements",
        "approved_optical_context",
    }
    | set(DERIVATIVE_CONTEXT_LAYER_ROLES)
)

REQUIRED_SAR_CONTEXT_LAYER_ROLES: frozenset[str] = frozenset(
    {
        "pre_event_vv",
        "event_time_vv",
        "pre_event_vh",
        "event_time_vh",
    }
)

REQUIRED_STATIC_CONTEXT_LAYER_ROLES: frozenset[str] = frozenset(
    {"permanent_water_context", "land_cover"}
)

REQUIRED_TERRAIN_CONTEXT_ALTERNATIVES: frozenset[str] = frozenset(
    {"dem_hillshade", "slope"}
)

GOVERNED_STATIC_CONTEXT_ROLES: frozenset[str] = frozenset(
    set(REQUIRED_STATIC_CONTEXT_LAYER_ROLES)
    | set(REQUIRED_TERRAIN_CONTEXT_ALTERNATIVES)
)

# Two-date change layers are admitted only when a self-hashed derivative
# receipt names both source acquisitions, exact transformations/fixed display
# parameters, common grid, and output bytes. They remain display-only evidence.

CONTEXT_LAYER_COLUMNS: tuple[str, ...] = (
    "context_layer_id",
    "event_id",
    "layer_role",
    "source_registry_sha256",
    "source_asset_id",
    "source_product_id",
    "display_name",
    "path_hint",
    "crs",
    "acquisition_time_utc",
    "source_sha256",
    "processed_layer_sha256",
    "allowed_for_blinded_review",
    "confidence_class",
    "assumptions",
)

QUERY_SOURCE_LINEAGE_COLUMNS: tuple[str, ...] = (
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "pre_source_asset_ids",
    "event_source_asset_ids",
    "pre_product_ids",
    "event_product_ids",
    "pre_acquisition_utc",
    "event_acquisition_utc",
    "pre_source_sha256s",
    "event_source_sha256s",
)

SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS: tuple[str, ...] = (
    "supported_query_allowlist_applied",
    "supported_query_derivation_sha256",
    "supported_query_csv_sha256",
)

CANONICAL_REVIEW_VISIBLE_COLUMNS: tuple[str, ...] = tuple(
    column
    for column in REVIEW_VISIBLE_COLUMNS
    if column not in {"review_purpose", "geometry_wkt"}
)


class ReviewBundleError(ValueError):
    """Raised when a blinded review bundle cannot be built safely."""


class ReviewPurpose(str, Enum):
    """Why a region is entering review and which role may supply it."""

    ACQUISITION_PRIMARY = "acquisition_primary"
    REVIEWER_CALIBRATION = "reviewer_calibration"
    FIXED_EVALUATION = "fixed_evaluation"


REVIEW_PURPOSE_ALLOWED_ROLES: dict[ReviewPurpose, frozenset[DatasetRole]] = {
    ReviewPurpose.ACQUISITION_PRIMARY: frozenset(
        {DatasetRole.TRAINING_AND_QUERY_POOL}
    ),
    ReviewPurpose.REVIEWER_CALIBRATION: frozenset(
        {DatasetRole.REVIEWER_CALIBRATION}
    ),
    ReviewPurpose.FIXED_EVALUATION: frozenset(
        {
            DatasetRole.FIXED_WITHIN_EVENT_DEVELOPMENT,
            DatasetRole.UNTOUCHED_GEOGRAPHIC_TEST,
        }
    ),
}


def build_blinded_review_manifest(
    queries: pd.DataFrame,
    *,
    review_purpose: ReviewPurpose | str,
    selected_column: str = "selected",
) -> pd.DataFrame:
    """Return selected query cores with model and weak-label evidence removed."""

    purpose = _coerce_review_purpose(review_purpose)
    _require_columns(queries, REVIEW_INPUT_COLUMNS, "query manifest")
    frame = queries.copy().fillna("")
    if purpose is ReviewPurpose.ACQUISITION_PRIMARY:
        if selected_column not in frame.columns:
            raise ReviewBundleError(
                "acquisition_primary requires an explicit selected column."
            )
        selected_mask = frame[selected_column].map(
            lambda value: _strict_bool(value, selected_column)
        )
        frame = frame.loc[selected_mask].copy()
    else:
        _reject_active_selection_fields(frame, selected_column=selected_column)
    if frame.empty:
        raise ReviewBundleError("No selected review regions were supplied.")
    supported_columns_present = [
        column
        for column in SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS
        if column in frame.columns
    ]
    if supported_columns_present and len(supported_columns_present) != len(
        SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS
    ):
        missing = sorted(
            set(SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS) - set(frame.columns)
        )
        raise ReviewBundleError(
            "Supported-query review lineage is partial; missing: "
            + ", ".join(missing)
        )
    has_supported_lineage = bool(supported_columns_present)
    if frame["query_region_id"].astype(str).str.strip().eq("").any():
        raise ReviewBundleError("query_region_id must not be blank.")
    if frame["query_region_id"].duplicated().any():
        duplicates = sorted(
            frame.loc[frame["query_region_id"].duplicated(), "query_region_id"]
            .astype(str)
            .unique()
        )
        raise ReviewBundleError(
            f"Review manifest has duplicate query_region_id values: {', '.join(duplicates)}"
        )
    for row in frame.to_dict(orient="records"):
        _validate_query_safety(row, review_purpose=purpose)
        _validate_query_source_lineage(row)
        if has_supported_lineage:
            _validate_supported_query_review_lineage(row)
    _require_consistent_event_source_lineage(frame)
    for column in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ReviewBundleError(f"{column} must be numeric.")
    if (frame["bbox_max_x"] <= frame["bbox_min_x"]).any() or (
        frame["bbox_max_y"] <= frame["bbox_min_y"]
    ).any():
        raise ReviewBundleError("Every query region must have positive projected bounds.")
    if not frame["grid_contract_sha256"].astype(str).str.fullmatch(
        r"[0-9a-fA-F]{64}"
    ).all():
        raise ReviewBundleError("grid_contract_sha256 must be a complete SHA-256.")
    frame["query_size_pixels"] = pd.to_numeric(
        frame["query_size_pixels"], errors="coerce"
    )
    frame["resolution_m"] = pd.to_numeric(frame["resolution_m"], errors="coerce")
    if frame["query_size_pixels"].isna().any() or (
        frame["query_size_pixels"] <= 0
    ).any():
        raise ReviewBundleError("query_size_pixels must be positive numeric values.")
    if frame["resolution_m"].isna().any() or (frame["resolution_m"] <= 0).any():
        raise ReviewBundleError("resolution_m must be positive numeric values.")
    frame["geometry_wkt"] = frame.apply(_rectangle_wkt, axis=1)
    frame["review_purpose"] = purpose.value
    visible_columns = (
        (*REVIEW_VISIBLE_COLUMNS, *SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS)
        if has_supported_lineage
        else REVIEW_VISIBLE_COLUMNS
    )
    visible = frame.loc[:, visible_columns].copy()
    _assert_blinded_columns(visible)
    return visible.reset_index(drop=True)


def build_annotation_template(
    review_manifest: pd.DataFrame,
    *,
    protocol_version: str = "label_factory_protocol_v1",
    tool_version: str = "qgis_manual_review_v1",
    review_stage: str = "primary",
    reviewer_id: str = "",
) -> pd.DataFrame:
    """Create a blank append-only annotation form for a blinded review manifest."""

    _require_columns(review_manifest, REVIEW_VISIBLE_COLUMNS, "review manifest")
    if review_stage not in {"primary", "secondary"}:
        raise ReviewBundleError("review_stage must be 'primary' or 'secondary'.")
    if reviewer_id != reviewer_id.strip():
        raise ReviewBundleError("reviewer_id must not contain surrounding whitespace.")
    rows: list[dict[str, object]] = []
    for row in review_manifest.to_dict(orient="records"):
        rows.append(
            {
                "annotation_id": "",
                "event_id": row["event_id"],
                "tile_id": row["tile_id"],
                "query_region_id": row["query_region_id"],
                "reviewer_id": reviewer_id,
                "review_revision": 1,
                "review_stage": review_stage,
                "review_purpose": row["review_purpose"],
                "primary_class": "",
                "class_code": "",
                "confidence": "",
                "ambiguity_reason_codes": "",
                "evidence_layers_used": "",
                "review_complete": False,
                "reviewed_extent_status": "not_reviewed",
                "reviewed_extent": "",
                "geometry_wkt": "",
                "review_started_at_utc": "",
                "review_finished_at_utc": "",
                "protocol_version": protocol_version,
                "tool_version": tool_version,
                "model_predictions_visible": False,
                "other_reviewer_annotations_visible": False,
                "created_at_utc": "",
                "locked_at_utc": "",
                "supersedes_annotation_id": "",
                "source_timestamp": row["source_timestamp"],
                "assumptions": (
                    "Blinded human annotation template; blank geometry is unreviewed, "
                    "not dry land. Query-model outputs are not visible and cannot feed FPPS."
                ),
            }
        )
    return pd.DataFrame(rows, columns=ANNOTATION_TEMPLATE_COLUMNS)


def build_blinded_context_manifest(
    context_layers: pd.DataFrame,
    review_manifest: pd.DataFrame,
    *,
    derivative_lineage_receipt: DerivativeReceiptInput | None = None,
) -> pd.DataFrame:
    """Validate the reviewer-visible source-evidence manifest fail closed."""

    _require_columns(context_layers, CONTEXT_LAYER_COLUMNS, "context-layer manifest")
    _require_columns(review_manifest, REVIEW_VISIBLE_COLUMNS, "review manifest")
    allowed_events = {
        str(event_id).strip() for event_id in review_manifest["event_id"]
    }
    if "" in allowed_events:
        raise ReviewBundleError("Review manifest event_id must not be blank.")
    review_crs_values = {
        str(crs).strip() for crs in review_manifest["crs"]
    }
    if "" in review_crs_values:
        raise ReviewBundleError("Review manifest CRS must not be blank.")
    if len(review_crs_values) != 1:
        raise ReviewBundleError(
            "A formal review bundle must contain exactly one projected CRS."
        )
    bundle_crs = next(iter(review_crs_values))
    event_lineage = _require_consistent_event_source_lineage(review_manifest)

    frame = context_layers.copy().fillna("")
    if frame.empty:
        raise ReviewBundleError(
            "The context-layer source-evidence manifest must not be empty."
        )
    derivative_rows_present = frame["layer_role"].astype(str).isin(
        DERIVATIVE_CONTEXT_LAYER_ROLES
    ).any()
    if derivative_rows_present and derivative_lineage_receipt is None:
        raise ReviewBundleError(
            "Reviewer-visible VV/VH change derivatives require their exact "
            "self-hashed derivative-lineage receipt."
        )
    if not derivative_rows_present and derivative_lineage_receipt is not None:
        raise ReviewBundleError(
            "A derivative-lineage receipt was supplied but no governed derivative "
            "layers are present in context."
        )
    context_events = {str(event_id).strip() for event_id in frame["event_id"]}
    unexpected_events = sorted(context_events - allowed_events)
    if unexpected_events:
        raise ReviewBundleError(
            "Context layers include events outside the selected review queries: "
            + ", ".join(unexpected_events)
        )
    missing_events = sorted(allowed_events - context_events)
    if missing_events:
        raise ReviewBundleError(
            "Context layers are missing selected review events: "
            + ", ".join(missing_events)
        )
    normalized_layer_ids = frame["context_layer_id"].astype(str).str.strip()
    if normalized_layer_ids.eq("").any():
        raise ReviewBundleError("context_layer_id must not be blank.")
    if normalized_layer_ids.duplicated().any():
        raise ReviewBundleError("context_layer_id must be unique.")
    for row in frame.to_dict(orient="records"):
        context_layer_id = str(row["context_layer_id"]).strip()
        event_id = str(row["event_id"]).strip()
        layer_role = str(row["layer_role"]).strip()
        for exact_field in (
            "context_layer_id",
            "event_id",
            "layer_role",
            "source_registry_sha256",
            "source_asset_id",
            "crs",
        ):
            if str(row[exact_field]) != str(row[exact_field]).strip():
                raise ReviewBundleError(
                    f"Context layer {context_layer_id} has non-canonical whitespace "
                    f"in {exact_field}."
                )
        if layer_role not in APPROVED_CONTEXT_LAYER_ROLES:
            raise ReviewBundleError(
                f"Context layer role is not approved for blinded review: {layer_role!r}."
            )
        if not _strict_bool(row["allowed_for_blinded_review"], "allowed_for_blinded_review"):
            raise ReviewBundleError(
                f"Context layer is not cleared for blinded review: {row['context_layer_id']}"
            )
        try:
            reject_absolute_local_path(str(row["path_hint"]))
        except EventRegistryError as exc:
            raise ReviewBundleError(
                f"Unsafe context path_hint for {context_layer_id}: {exc}"
            ) from exc
        for field in (
            "source_asset_id",
            "source_product_id",
            "display_name",
            "path_hint",
            "crs",
            "acquisition_time_utc",
            "assumptions",
        ):
            if not str(row[field]).strip():
                raise ReviewBundleError(
                    f"Context layer {context_layer_id} has blank {field}."
                )
        source_asset_id = str(row["source_asset_id"])
        if (
            source_asset_id != source_asset_id.strip()
            or source_asset_id.strip().lower()
            in {"unknown", "n/a", "na", "none", "pending", "tbd"}
            or re.search(r"[\\/]", source_asset_id) is not None
            or "://" in source_asset_id
        ):
            raise ReviewBundleError(
                f"Context layer {context_layer_id} must name one exact "
                "source_asset_id, not a placeholder or path."
            )
        source_product_id = str(row["source_product_id"])
        if (
            source_product_id != source_product_id.strip()
            or source_product_id.strip().lower()
            in {"unknown", "n/a", "na", "none", "pending", "tbd"}
            or re.search(r"[\\/]", source_product_id) is not None
            or "://" in source_product_id
        ):
            raise ReviewBundleError(
                f"Context layer {context_layer_id} must name one exact "
                "source_product_id, not a placeholder or path."
            )
        if str(row["confidence_class"]).strip().lower() not in {
            "high",
            "medium",
            "low",
        }:
            raise ReviewBundleError(
                f"Context layer {context_layer_id} has invalid confidence_class."
            )
        if str(row["crs"]).strip() != bundle_crs:
            raise ReviewBundleError(
                f"Context layer {context_layer_id} CRS does not match selected "
                f"queries for {event_id}: expected {bundle_crs}."
            )
        if re.fullmatch(r"[0-9a-f]{64}", str(row["source_registry_sha256"])) is None:
            raise ReviewBundleError(
                f"Context layer {context_layer_id} has invalid "
                "source_registry_sha256."
            )
        _validate_context_utc_timestamp(
            row["acquisition_time_utc"],
            context_layer_id=context_layer_id,
        )
        for hash_field in ("source_sha256", "processed_layer_sha256"):
            if re.fullmatch(r"[0-9a-f]{64}", str(row[hash_field])) is None:
                raise ReviewBundleError(
                    f"Context layer {context_layer_id} has invalid {hash_field}; "
                    "a lowercase complete SHA-256 is required."
                )
        _validate_context_against_event_lineage(
            row,
            event_lineage=event_lineage[event_id],
        )

    for event_id in sorted(allowed_events):
        event_roles = frame.loc[
            frame["event_id"].astype(str).str.strip().eq(event_id), "layer_role"
        ].astype(str).str.strip()
        missing_roles = sorted(REQUIRED_SAR_CONTEXT_LAYER_ROLES - set(event_roles))
        if missing_roles:
            raise ReviewBundleError(
                f"Context source evidence for {event_id} is missing required SAR "
                f"roles: {', '.join(missing_roles)}"
            )
        missing_static_roles = sorted(
            REQUIRED_STATIC_CONTEXT_LAYER_ROLES - set(event_roles)
        )
        if missing_static_roles:
            raise ReviewBundleError(
                f"Context source evidence for {event_id} is missing required "
                f"review context roles: {', '.join(missing_static_roles)}"
            )
        if not REQUIRED_TERRAIN_CONTEXT_ALTERNATIVES.intersection(event_roles):
            raise ReviewBundleError(
                f"Context source evidence for {event_id} requires at least one "
                "terrain role: dem_hillshade or slope."
            )
        duplicated_required_roles = sorted(
            role
            for role in REQUIRED_SAR_CONTEXT_LAYER_ROLES
            if int(event_roles.eq(role).sum()) > 1
        )
        if duplicated_required_roles:
            raise ReviewBundleError(
                f"Context source evidence for {event_id} has ambiguous duplicate "
                f"required SAR roles: {', '.join(duplicated_required_roles)}"
            )

    for (event_id, source_asset_id, source_product_id), product_rows in frame.groupby(
        ["event_id", "source_asset_id", "source_product_id"],
        sort=False,
        dropna=False,
    ):
        acquisition_times = set(product_rows["acquisition_time_utc"].astype(str))
        source_hashes = set(product_rows["source_sha256"].astype(str))
        if len(acquisition_times) != 1 or len(source_hashes) != 1:
            raise ReviewBundleError(
                f"Source asset {source_asset_id!r} / product {source_product_id!r} "
                f"for event {event_id!r} has "
                "inconsistent acquisition time or source checksum across layers."
            )

    visible = frame.loc[:, CONTEXT_LAYER_COLUMNS].reset_index(drop=True)
    _assert_blinded_columns(visible)
    if derivative_lineage_receipt is not None:
        try:
            validate_derivative_context_against_receipt(
                derivative_lineage_receipt,
                review_manifest=review_manifest,
                context_manifest=visible,
            )
        except ReviewDerivativeLineageError as exc:
            raise ReviewBundleError(str(exc)) from exc
    return visible


def validate_review_queries_against_canonical_grid(
    query_source: pd.DataFrame | str | Path,
    review_manifest: pd.DataFrame,
    *,
    governance_package: str | Path,
    processing_alignment_receipt: ReceiptInput,
    grid_validation_receipt: str | Path,
    canonical_tile_manifest: str | Path,
    canonical_query_manifest: str | Path,
    supported_query_derivation: str | Path | None = None,
) -> dict[str, object]:
    """Rebuild grid evidence and prove every review query is canonical."""

    # Local import avoids a module cycle: readiness also evaluates completed
    # review-workflow evidence.
    from floodguard.label_factory.readiness import (
        LabelFactoryReadinessError,
        validate_grid_validation_receipt_against_evidence,
    )

    governance_root = Path(governance_package)
    try:
        grid_receipt = validate_grid_validation_receipt_against_evidence(
            grid_validation_receipt,
            governance_root / "events.csv",
            governance_root / "source_assets.csv",
            processing_alignment_receipt,
            canonical_tile_manifest,
            canonical_query_manifest,
            governance_package=governance_root,
            supported_query_derivation=supported_query_derivation,
        )
    except LabelFactoryReadinessError as exc:
        raise ReviewBundleError(str(exc)) from exc

    canonical = _coerce_frame(canonical_query_manifest)
    source = _coerce_frame(query_source)
    canonical_ids = canonical["query_region_id"].astype(str)
    if canonical_ids.duplicated().any():
        raise ReviewBundleError("Canonical query manifest has duplicate query ids.")
    selected_ids = set(review_manifest["query_region_id"].astype(str))
    selected_source = source.loc[
        source["query_region_id"].astype(str).isin(selected_ids)
    ].copy()
    if set(selected_source["query_region_id"].astype(str)) != selected_ids:
        raise ReviewBundleError(
            "Selected review queries are missing from the supplied selection source."
        )
    canonical_selected = canonical.loc[canonical_ids.isin(selected_ids)].copy()
    if set(canonical_selected["query_region_id"].astype(str)) != selected_ids:
        raise ReviewBundleError(
            "Selected review queries are not a subset of the canonical query manifest."
        )

    comparison_columns = (
        list(REVIEW_INPUT_COLUMNS)
        if all(column in selected_source for column in REVIEW_INPUT_COLUMNS)
        else list(CANONICAL_REVIEW_VISIBLE_COLUMNS)
    )
    source_has_supported = all(
        column in selected_source.columns
        for column in SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS
    )
    canonical_has_supported = all(
        column in canonical_selected.columns
        for column in SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS
    )
    if source_has_supported != canonical_has_supported:
        raise ReviewBundleError(
            "Selection and canonical query manifests disagree on supported-query "
            "lineage presence."
        )
    if source_has_supported:
        comparison_columns.extend(SUPPORTED_QUERY_REVIEW_LINEAGE_COLUMNS)
    _require_columns(selected_source, tuple(comparison_columns), "query selection")
    _require_columns(
        canonical_selected,
        tuple(comparison_columns),
        "canonical query manifest",
    )
    source_by_id = selected_source.set_index("query_region_id", drop=False)
    canonical_by_id = canonical_selected.set_index("query_region_id", drop=False)
    numeric_fields = {
        "query_size_pixels",
        "resolution_m",
        "bbox_min_x",
        "bbox_min_y",
        "bbox_max_x",
        "bbox_max_y",
    }
    boolean_fields = {
        "eligible_for_human_annotation",
        "eligible_for_active_selection",
        "eligible_for_review_queue",
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
        "supported_query_allowlist_applied",
    }
    for query_id in sorted(selected_ids):
        for field in comparison_columns:
            left = source_by_id.at[query_id, field]
            right = canonical_by_id.at[query_id, field]
            if field in numeric_fields:
                equal = float(left) == float(right)
            elif field in boolean_fields:
                equal = _strict_bool(left, field) is _strict_bool(right, field)
            else:
                equal = str(left) == str(right)
            if not equal:
                raise ReviewBundleError(
                    f"Selected query {query_id!r} differs from the canonical "
                    f"manifest in {field}."
                )

    supported_query_csv_sha256 = ""
    if source_has_supported:
        if supported_query_derivation is None:
            raise ReviewBundleError(
                "Allowlisted review queries require supported_query_derivation."
            )
        try:
            derivation = load_supported_query_derivation(
                supported_query_derivation,
                verify_outputs=True,
            )
        except SupportedQueryPoolError as exc:
            raise ReviewBundleError(str(exc)) from exc
        derivation_sha = str(derivation["manifest_sha256"])
        if grid_receipt["supported_query_derivation_sha256"] != derivation_sha:
            raise ReviewBundleError(
                "Grid receipt does not bind the supplied supported-query derivation."
            )
        output_record = derivation.get("outputs", {}).get("supported_queries", {})
        supported_query_csv_sha256 = str(output_record.get("sha256", ""))
        if re.fullmatch(r"[0-9a-f]{64}", supported_query_csv_sha256) is None:
            raise ReviewBundleError(
                "Supported-query derivation has no valid supported-query CSV hash."
            )
        if set(
            canonical_selected["supported_query_derivation_sha256"].astype(str)
        ) != {derivation_sha} or set(
            canonical_selected["supported_query_csv_sha256"].astype(str)
        ) != {supported_query_csv_sha256}:
            raise ReviewBundleError(
                "Canonical review queries do not retain the supplied allowlist lineage."
            )
    elif grid_receipt["supported_query_derivation_sha256"] != "":
        raise ReviewBundleError(
            "Grid receipt declares an allowlist but canonical queries omit its lineage."
        )

    return {
        "grid_receipt": grid_receipt,
        "supported_query_csv_sha256": supported_query_csv_sha256,
    }


def validate_review_human_role_gate(
    human_role_package: str | Path,
    *,
    review_purpose: ReviewPurpose | str,
    review_stage: str,
    target_reviewer_id: str,
    planned_review_start_utc: str,
    event_id: str,
    protocol_version: str = "label_factory_protocol_v1",
    taxonomy_version: str = "flood_label_v1",
) -> dict[str, object]:
    """Bind a bundle lane to an appointed reviewer and the correct role gate.

    Calibration consumes an evidence-complete frozen *pre-calibration* package.
    Acquisition and fixed evaluation consume a later package that binds a
    passing calibration receipt and explicitly opens formal review.  A target
    reviewer id is never inferred from file order or supplied independently of
    the package.
    """

    purpose = _coerce_review_purpose(review_purpose)
    if review_stage not in {"primary", "secondary"}:
        raise ReviewBundleError("review_stage must be 'primary' or 'secondary'.")
    reviewer_id = str(target_reviewer_id)
    if not reviewer_id or reviewer_id != reviewer_id.strip():
        raise ReviewBundleError(
            "target_reviewer_id must be a non-empty canonical role id without "
            "surrounding whitespace."
        )
    package_event_id = str(event_id)
    if not package_event_id or package_event_id != package_event_id.strip():
        raise ReviewBundleError("event_id must be non-empty and canonical.")
    if not protocol_version or protocol_version != protocol_version.strip():
        raise ReviewBundleError("protocol_version must be non-empty and canonical.")
    if not taxonomy_version or taxonomy_version != taxonomy_version.strip():
        raise ReviewBundleError("taxonomy_version must be non-empty and canonical.")

    planned_start_text = str(planned_review_start_utc)
    planned_start = _validate_utc_timestamp(
        planned_start_text,
        label="planned_review_start_utc",
    )
    package_root = Path(human_role_package)
    try:
        package = validate_human_role_package(package_root)
    except HumanRolePackageError as exc:
        raise ReviewBundleError(f"Human-role package is invalid: {exc}") from exc

    if package["event_id"] != package_event_id:
        raise ReviewBundleError(
            "Human-role package event_id does not match the review bundle event."
        )
    if package["protocol_version"] != protocol_version:
        raise ReviewBundleError(
            "Human-role package protocol_version does not match the review bundle."
        )
    if package["taxonomy_version"] != taxonomy_version:
        raise ReviewBundleError(
            "Human-role package taxonomy_version does not match the review bundle."
        )

    expected_category = "reviewer_a" if review_stage == "primary" else "reviewer_b"
    appointments = [
        row
        for row in package["appointments"]
        if row["role_category"] == expected_category
    ]
    if len(appointments) != 1:
        raise ReviewBundleError(
            f"Human-role package must appoint exactly one {expected_category}."
        )
    appointment = appointments[0]
    if appointment["role_id"] != reviewer_id:
        raise ReviewBundleError(
            f"target_reviewer_id {reviewer_id!r} is not the appointed "
            f"{expected_category} {appointment['role_id']!r}."
        )
    if (
        appointment["appointment_status"]
        != "accepted_with_attributable_local_evidence"
    ):
        raise ReviewBundleError(
            f"Target {expected_category} does not have an attributable "
            "accepted appointment."
        )

    package_created_text = str(package["created_at_utc"])
    package_created = _validate_utc_timestamp(
        package_created_text,
        label="human-role package created_at_utc",
    )

    formal_authorized_from = ""
    calibration_receipt_sha256 = ""
    calibration_receipt_file_sha256 = ""
    effective_not_before = package_created
    if purpose is ReviewPurpose.REVIEWER_CALIBRATION:
        if (
            package["formal_review_authorized"] is not False
            or package["calibration_receipt"] is not None
        ):
            raise ReviewBundleError(
                "reviewer_calibration requires an evidence-complete frozen "
                "pre-calibration human-role package with no calibration receipt "
                "and formal_review_authorized=false."
            )
        if planned_start < package_created:
            raise ReviewBundleError(
                "planned_review_start_utc precedes the frozen pre-calibration "
                f"package not-before time {package_created_text}."
            )
        gate_status = "precalibration_appointments_frozen"
    else:
        if package["formal_review_authorized"] is not True:
            raise ReviewBundleError(
                f"{purpose.value} requires a post-calibration human-role package "
                "with formal_review_authorized=true."
            )
        receipt_binding = package["calibration_receipt"]
        if not isinstance(receipt_binding, dict):
            raise ReviewBundleError(
                "Formal human-role authorization is missing its calibration "
                "receipt binding."
            )
        formal_authorized_from = str(package["formal_review_authorized_from_utc"])
        authorized_from = _validate_utc_timestamp(
            formal_authorized_from,
            label="formal_review_authorized_from_utc",
        )
        effective_not_before = max(package_created, authorized_from)
        if planned_start < authorized_from:
            raise ReviewBundleError(
                "planned_review_start_utc precedes formal_review_authorized_from_utc "
                f"{formal_authorized_from}."
            )
        if planned_start < package_created:
            raise ReviewBundleError(
                "planned_review_start_utc precedes the frozen post-calibration "
                f"package created_at_utc {package_created_text}."
            )
        calibration_receipt_sha256 = str(receipt_binding["receipt_sha256"])
        calibration_receipt_file_sha256 = str(receipt_binding["file_sha256"])
        gate_status = "formal_review_authorized"

    return {
        "human_role_package_id": str(package["package_id"]),
        "human_role_package_manifest_sha256": str(package["manifest_sha256"]),
        "human_role_package_file_sha256": _sha256(
            package_root / "human_role_package.json"
        ),
        "human_role_package_status": str(package["package_status"]),
        "human_role_binding_status": gate_status,
        "human_role_formal_review_authorized": bool(
            package["formal_review_authorized"]
        ),
        "formal_review_authorized_from_utc": formal_authorized_from,
        "human_role_effective_not_before_utc": (
            effective_not_before.isoformat().replace("+00:00", "Z")
        ),
        "target_reviewer_id": reviewer_id,
        "target_reviewer_role_category": expected_category,
        "target_reviewer_appointment_status": str(
            appointment["appointment_status"]
        ),
        "planned_review_start_utc": planned_start_text,
        "calibration_receipt_sha256": calibration_receipt_sha256,
        "calibration_receipt_file_sha256": calibration_receipt_file_sha256,
        "human_role_package_event_id": package_event_id,
        "taxonomy_version": taxonomy_version,
        "participation_mode": str(package["participation_mode"]),
        "annotation_use_scope": str(package["annotation_use_scope"]),
    }


def write_blinded_review_bundle(
    queries: pd.DataFrame | str | Path,
    output_directory: str | Path,
    *,
    review_purpose: ReviewPurpose | str,
    processing_alignment_receipt: ReceiptInput,
    selected_column: str = "selected",
    protocol_version: str = "label_factory_protocol_v1",
    taxonomy_version: str = "flood_label_v1",
    tool_version: str = "qgis_manual_review_v1",
    review_stage: str = "primary",
    human_role_package: str | Path | None = None,
    target_reviewer_id: str | None = None,
    planned_review_start_utc: str | None = None,
    context_layers: pd.DataFrame | str | Path | None = None,
    derivative_lineage_receipt: DerivativeReceiptInput | None = None,
    governance_package: str | Path | None = None,
    grid_validation_receipt: str | Path | None = None,
    canonical_tile_manifest: str | Path | None = None,
    canonical_query_manifest: str | Path | None = None,
    supported_query_derivation: str | Path | None = None,
    allow_ungoverned_fixture: bool = False,
) -> dict[str, Path]:
    """Write a blinded bundle backed by complete source and rights evidence.

    Formal bundles require a semantically validated governance package.  The
    explicit fixture escape hatch exists only for synthetic unit tests; bundles
    produced through it record that they are ineligible for formal review.
    """

    source = _coerce_frame(queries)
    purpose = _coerce_review_purpose(review_purpose)
    review = build_blinded_review_manifest(
        source,
        review_purpose=purpose,
        selected_column=selected_column,
    )
    if context_layers is None:
        raise ReviewBundleError(
            "A formal review bundle requires --context-layers source evidence."
        )
    if derivative_lineage_receipt is not None and not allow_ungoverned_fixture:
        raise ReviewBundleError(
            "Production derivative context remains blocked: technical lineage "
            "and Reference Authority design approval do not authorize reviewer "
            "delivery. A later canonical derivative-context release authorization "
            "must be implemented and supplied before a production bundle may "
            "include VV/VH change displays."
        )
    # Validate every source-evidence field before creating the target parent or
    # a temporary bundle directory. Failed builds therefore leave no residue.
    context = build_blinded_context_manifest(
        _coerce_frame(context_layers),
        review,
        derivative_lineage_receipt=derivative_lineage_receipt,
    )
    try:
        if governance_package is None:
            if not allow_ungoverned_fixture:
                raise ReviewBundleError(
                    "A validated --governance-package is required for a formal "
                    "review bundle. Synthetic tests must opt in explicitly."
                )
            processing_receipt = load_processing_alignment_receipt(
                processing_alignment_receipt
            )
            governance_binding: dict[str, object] = {
                "governance_package_id": "",
                "governance_package_manifest_sha256": "",
                "governance_package_seal_sha256": "",
                "aligned_context_inventory_sha256": "",
                "grid_validation_receipt_sha256": "",
                "grid_validation_receipt_file_sha256": "",
                "canonical_tile_manifest_file_sha256": "",
                "canonical_query_manifest_file_sha256": "",
                "supported_query_derivation_file_sha256": "",
                "supported_query_derivation_sha256": "",
                "supported_query_csv_sha256": "",
                "governance_binding_status": "synthetic_fixture_only",
                "production_review_eligible": False,
            }
        else:
            governance_root = Path(governance_package)
            required_grid_inputs = {
                "grid_validation_receipt": grid_validation_receipt,
                "canonical_tile_manifest": canonical_tile_manifest,
                "canonical_query_manifest": canonical_query_manifest,
            }
            missing_grid_inputs = [
                name for name, value in required_grid_inputs.items() if value is None
            ]
            if missing_grid_inputs:
                raise ReviewBundleError(
                    "A formal governed bundle requires canonical grid evidence: "
                    + ", ".join(missing_grid_inputs)
                )
            processing_receipt = validate_processing_alignment_receipt(
                processing_alignment_receipt,
                governance_root / "events.csv",
                governance_root / "source_assets.csv",
                governance_package=governance_root,
            )
            governance_seal = validate_rights_clearance_package(governance_root)
            validate_static_review_context_against_governance(
                context,
                governance_root,
            )
            grid_binding = validate_review_queries_against_canonical_grid(
                source,
                review,
                governance_package=governance_root,
                processing_alignment_receipt=processing_receipt,
                grid_validation_receipt=grid_validation_receipt,  # type: ignore[arg-type]
                canonical_tile_manifest=canonical_tile_manifest,  # type: ignore[arg-type]
                canonical_query_manifest=canonical_query_manifest,  # type: ignore[arg-type]
                supported_query_derivation=supported_query_derivation,
            )
            grid_receipt = grid_binding["grid_receipt"]
            assert isinstance(grid_receipt, dict)
            governance_binding = {
                "governance_package_id": str(governance_seal["package_id"]),
                "governance_package_manifest_sha256": str(
                    governance_seal["package_manifest_sha256"]
                ),
                "governance_package_seal_sha256": str(
                    governance_seal["seal_sha256"]
                ),
                "aligned_context_inventory_sha256": _sha256(
                    governance_root / "aligned_context_inventory.csv"
                ),
                "grid_validation_receipt_sha256": str(
                    grid_receipt["receipt_sha256"]
                ),
                "grid_validation_receipt_file_sha256": _sha256(
                    Path(grid_validation_receipt)  # type: ignore[arg-type]
                ),
                "canonical_tile_manifest_file_sha256": _sha256(
                    Path(canonical_tile_manifest)  # type: ignore[arg-type]
                ),
                "canonical_query_manifest_file_sha256": _sha256(
                    Path(canonical_query_manifest)  # type: ignore[arg-type]
                ),
                "supported_query_derivation_file_sha256": (
                    _sha256(Path(supported_query_derivation))
                    if supported_query_derivation is not None
                    else ""
                ),
                "supported_query_derivation_sha256": str(
                    grid_receipt["supported_query_derivation_sha256"]
                ),
                "supported_query_csv_sha256": str(
                    grid_binding["supported_query_csv_sha256"]
                ),
                "governance_binding_status": "validated",
                "production_review_eligible": True,
            }
        validate_processing_receipt_for_review_bundle(
            processing_receipt,
            review_manifest=review,
            context_manifest=context,
        )
        derivative_receipt: dict[str, object] | None = None
        if derivative_lineage_receipt is not None:
            derivative_receipt = validate_review_derivative_lineage_receipt(
                derivative_lineage_receipt,
                processing_alignment_receipt=processing_receipt,
                review_manifest=review,
                context_manifest=context,
                governance_package=governance_package,
                allow_ungoverned_fixture=allow_ungoverned_fixture,
            )
    except (
        ProcessingAlignmentError,
        RightsClearanceError,
        ReviewDerivativeLineageError,
    ) as exc:
        raise ReviewBundleError(str(exc)) from exc

    role_inputs = {
        "human_role_package": human_role_package,
        "target_reviewer_id": target_reviewer_id,
        "planned_review_start_utc": planned_review_start_utc,
    }
    missing_role_inputs = [
        name for name, value in role_inputs.items() if value is None
    ]
    if missing_role_inputs:
        if not allow_ungoverned_fixture or len(missing_role_inputs) != len(role_inputs):
            raise ReviewBundleError(
                "A production review bundle requires a complete frozen human-role "
                "binding: "
                + ", ".join(missing_role_inputs)
                + ". The explicit omission escape is synthetic-fixture-only."
            )
        human_role_binding: dict[str, object] = {
            "human_role_package_id": "",
            "human_role_package_manifest_sha256": "",
            "human_role_package_file_sha256": "",
            "human_role_package_status": "",
            "human_role_binding_status": "synthetic_fixture_only",
            "human_role_formal_review_authorized": False,
            "formal_review_authorized_from_utc": "",
            "human_role_effective_not_before_utc": "",
            "target_reviewer_id": "",
            "target_reviewer_role_category": "",
            "target_reviewer_appointment_status": "",
            "planned_review_start_utc": "",
            "calibration_receipt_sha256": "",
            "calibration_receipt_file_sha256": "",
            "human_role_package_event_id": "",
            "taxonomy_version": taxonomy_version,
            "participation_mode": "",
            "annotation_use_scope": "",
        }
        bound_reviewer_id = ""
    else:
        event_ids = {str(value).strip() for value in review["event_id"]}
        if len(event_ids) != 1 or "" in event_ids:
            raise ReviewBundleError(
                "A human-role-bound review bundle must contain exactly one event_id."
            )
        human_role_binding = validate_review_human_role_gate(
            human_role_package,  # type: ignore[arg-type]
            review_purpose=purpose,
            review_stage=review_stage,
            target_reviewer_id=target_reviewer_id,  # type: ignore[arg-type]
            planned_review_start_utc=planned_review_start_utc,  # type: ignore[arg-type]
            event_id=next(iter(event_ids)),
            protocol_version=protocol_version,
            taxonomy_version=taxonomy_version,
        )
        bound_reviewer_id = str(target_reviewer_id)

    template = build_annotation_template(
        review,
        protocol_version=protocol_version,
        tool_version=tool_version,
        review_stage=review_stage,
        reviewer_id=bound_reviewer_id,
    )
    target = Path(output_directory)
    if target.exists():
        raise ReviewBundleError(
            f"Review bundle directory already exists and cannot be reused: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent)
    )
    review_path = temporary / "review_regions.csv"
    annotation_path = temporary / "annotation_template.csv"
    instructions_path = temporary / "README.md"
    manifest_path = temporary / "bundle_manifest.csv"
    context_path = temporary / "context_layers.csv"
    processing_receipt_path = temporary / "processing_alignment_receipt.json"
    derivative_receipt_path = temporary / "review_derivative_lineage_receipt.json"
    try:
        review.to_csv(review_path, index=False)
        template.to_csv(annotation_path, index=False)
        instructions_path.write_text(
            _bundle_instructions(
                protocol_version=protocol_version,
                taxonomy_version=taxonomy_version,
                target_reviewer_id=str(human_role_binding["target_reviewer_id"]),
                target_reviewer_role_category=str(
                    human_role_binding["target_reviewer_role_category"]
                ),
                planned_review_start_utc=str(
                    human_role_binding["planned_review_start_utc"]
                ),
                human_role_binding_status=str(
                    human_role_binding["human_role_binding_status"]
                ),
            ),
            encoding="utf-8",
        )
        context.to_csv(context_path, index=False)
        processing_receipt_path.write_text(
            json.dumps(
                processing_receipt,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        if derivative_receipt is not None:
            derivative_receipt_path.write_text(
                json.dumps(
                    derivative_receipt,
                    ensure_ascii=True,
                    sort_keys=True,
                    indent=2,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
        created_at = (
            datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        rows = []
        artifact_roles: list[tuple[Path, str]] = [
            (review_path, "reviewer_visible_regions"),
            (annotation_path, "blank_annotation_template"),
            (instructions_path, "review_instructions"),
            (context_path, "approved_context_source_evidence"),
            (processing_receipt_path, "processing_alignment_provenance"),
        ]
        if derivative_receipt is not None:
            artifact_roles.append(
                (derivative_receipt_path, "review_derivative_lineage_provenance")
            )
        derivative_binding = {
            "review_derivative_lineage_receipt_sha256": (
                str(derivative_receipt["receipt_sha256"])
                if derivative_receipt is not None
                else ""
            ),
            "review_derivative_lineage_receipt_file_sha256": (
                _sha256(derivative_receipt_path)
                if derivative_receipt is not None
                else ""
            ),
            "governed_derivative_layers_included": derivative_receipt is not None,
        }
        for path, role in artifact_roles:
            rows.append(
                {
                    "file_name": path.name,
                    "bundle_role": role,
                    "sha256": _sha256(path),
                    "created_at_utc": created_at,
                    "model_predictions_visible": False,
                    "review_stage": review_stage,
                    "review_purpose": purpose.value,
                    **governance_binding,
                    **human_role_binding,
                    **derivative_binding,
                    "processing_alignment_receipt_sha256": processing_receipt[
                        "receipt_sha256"
                    ],
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                    "assumptions": (
                        "Model-blinded review artifact with checksum-tracked "
                        "source evidence; no source rasters are copied."
                    ),
                }
            )
        pd.DataFrame(rows).to_csv(manifest_path, index=False)
        if target.exists():
            raise ReviewBundleError(
                f"Review bundle directory appeared during build: {target}"
            )
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    written = {
        "review_regions": target / review_path.name,
        "annotation_template": target / annotation_path.name,
        "instructions": target / instructions_path.name,
        "bundle_manifest": target / manifest_path.name,
        "context_layers": target / context_path.name,
        "processing_alignment_receipt": target / processing_receipt_path.name,
    }
    if derivative_receipt is not None:
        written["review_derivative_lineage_receipt"] = (
            target / derivative_receipt_path.name
        )
    return written


def validate_static_review_context_against_governance(
    context_manifest: pd.DataFrame | str | Path,
    governance_package: str | Path,
) -> None:
    """Bind reviewer-visible static context to the sealed governed inventory."""

    context = _coerce_frame(context_manifest)
    inventory_path = Path(governance_package) / "aligned_context_inventory.csv"
    inventory = _coerce_frame(inventory_path)
    _require_columns(
        inventory,
        (
            "context_layer_id",
            "event_id",
            "layer_role",
            "processed_path_hint",
            "processed_sha256",
            "source_sha256s",
            "output_crs",
            "allowed_for_blinded_review_candidate",
            "eligible_for_current_context_layers_csv",
            "rights_review_status",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "query_model_only",
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ),
        "governed aligned-context inventory",
    )
    governed_roles = (
        REQUIRED_SAR_CONTEXT_LAYER_ROLES
        | GOVERNED_STATIC_CONTEXT_ROLES
        | DERIVATIVE_CONTEXT_LAYER_ROLES
    )
    unsupported = sorted(
        set(context["layer_role"].astype(str)) - set(governed_roles)
    )
    if unsupported:
        raise ReviewBundleError(
            "Reviewer context contains roles not governed by the current rights "
            f"package: {', '.join(unsupported)}."
        )
    for row in context.loc[
        context["layer_role"].astype(str).isin(GOVERNED_STATIC_CONTEXT_ROLES)
    ].to_dict(orient="records"):
        context_layer_id = str(row["context_layer_id"])
        matches = inventory.loc[
            inventory["context_layer_id"].astype(str).eq(context_layer_id)
            & inventory["event_id"].astype(str).eq(str(row["event_id"]))
            & inventory["layer_role"].astype(str).eq(str(row["layer_role"]))
        ]
        if len(matches) != 1:
            raise ReviewBundleError(
                f"Static context layer {context_layer_id!r} does not have one exact "
                "governed inventory row."
            )
        governed = matches.iloc[0]
        expected_text = {
            "path_hint": "processed_path_hint",
            "processed_layer_sha256": "processed_sha256",
            "crs": "output_crs",
        }
        mismatches = [
            review_field
            for review_field, inventory_field in expected_text.items()
            if str(row[review_field]) != str(governed[inventory_field])
        ]
        if mismatches:
            raise ReviewBundleError(
                f"Static context layer {context_layer_id!r} disagrees with its "
                "governed inventory: "
                + ", ".join(mismatches)
                + "."
            )
        source_hashes = {
            token.split(":", 1)[1]
            for token in str(governed["source_sha256s"]).split(";")
            if ":" in token
        }
        if str(row["source_sha256"]) not in source_hashes:
            raise ReviewBundleError(
                f"Static context layer {context_layer_id!r} source checksum is not "
                "present in its governed inventory."
            )
        required_true = (
            "allowed_for_blinded_review_candidate",
            "eligible_for_current_context_layers_csv",
            "processing_allowed",
            "ml_label_derivation_allowed",
            "query_model_only",
        )
        required_false = (
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        )
        if (
            str(governed["rights_review_status"])
            != "approved_with_provider_conditions"
            or any(not _strict_bool(governed[field], field) for field in required_true)
            or any(_strict_bool(governed[field], field) for field in required_false)
            or not _strict_bool(
                row["allowed_for_blinded_review"],
                "allowed_for_blinded_review",
            )
        ):
            raise ReviewBundleError(
                f"Static context layer {context_layer_id!r} is not approved for "
                "blinded query-model review under the governed inventory."
            )


def _validate_query_safety(
    row: dict[str, object],
    *,
    review_purpose: ReviewPurpose,
) -> None:
    if not _strict_bool(
        row["eligible_for_human_annotation"], "eligible_for_human_annotation"
    ):
        raise ReviewBundleError(
            f"Query is not eligible for human annotation: {row['query_region_id']}"
        )
    active_selection_eligible = _strict_bool(
        row["eligible_for_active_selection"], "eligible_for_active_selection"
    )
    expected_active_selection_eligibility = (
        review_purpose is ReviewPurpose.ACQUISITION_PRIMARY
    )
    if active_selection_eligible is not expected_active_selection_eligibility:
        raise ReviewBundleError(
            f"Query active-selection eligibility contradicts {review_purpose.value}: "
            f"{row['query_region_id']}"
        )
    review_queue_eligible = _strict_bool(
        row["eligible_for_review_queue"], "eligible_for_review_queue"
    )
    expected_review_queue_eligibility = (
        review_purpose is ReviewPurpose.ACQUISITION_PRIMARY
    )
    if review_queue_eligible is not expected_review_queue_eligibility:
        raise ReviewBundleError(
            f"Query review-queue eligibility contradicts {review_purpose.value}: "
            f"{row['query_region_id']}"
        )
    if _strict_bool(row["query_model_only"], "query_model_only") is not True:
        raise ReviewBundleError(
            f"Query must remain query_model_only: {row['query_region_id']}"
        )
    forbidden = (
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    )
    active = [name for name in forbidden if _strict_bool(row[name], name)]
    if active:
        raise ReviewBundleError(
            f"Review query has forbidden eligibility ({', '.join(active)}): "
            f"{row['query_region_id']}"
        )
    if not str(row["source_timestamp"]).strip():
        raise ReviewBundleError(
            f"Review query has no source_timestamp: {row['query_region_id']}"
        )
    if not str(row["assumptions"]).strip():
        raise ReviewBundleError(
            f"Review query has no assumptions: {row['query_region_id']}"
        )
    try:
        role = DatasetRole(str(row["dataset_role"]).strip())
    except ValueError as exc:
        raise ReviewBundleError(
            f"Review query has unknown dataset_role: {row['query_region_id']}"
        ) from exc
    allowed_roles = REVIEW_PURPOSE_ALLOWED_ROLES[review_purpose]
    if role not in allowed_roles:
        raise ReviewBundleError(
            f"dataset_role {role.value!r} is not allowed for review purpose "
            f"{review_purpose.value!r}: {row['query_region_id']}"
        )
    if str(row["review_status"]).strip() not in {"unreviewed", "pending_manual_review"}:
        raise ReviewBundleError(
            f"Review query is not unreviewed: {row['query_region_id']}"
        )
    if str(row["confidence_class"]).strip().lower() not in {"high", "medium", "low"}:
        raise ReviewBundleError(
            f"Review query has invalid confidence_class: {row['query_region_id']}"
        )
    try:
        timestamp = datetime.fromisoformat(
            str(row["source_timestamp"]).strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ReviewBundleError(
            f"Review query has invalid source_timestamp: {row['query_region_id']}"
        ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ReviewBundleError(
            f"Review query source_timestamp must be timezone-aware: {row['query_region_id']}"
        )
    try:
        validate_projected_metre_crs(str(row["crs"]).strip())
    except GridContractError as exc:
        raise ReviewBundleError(str(exc)) from exc


def _validate_query_source_lineage(row: dict[str, object]) -> None:
    query_region_id = str(row.get("query_region_id", "")).strip() or "<unknown>"
    if re.fullmatch(r"[0-9a-f]{64}", str(row["source_registry_sha256"])) is None:
        raise ReviewBundleError(
            f"Review query {query_region_id} has invalid source_registry_sha256."
        )
    if re.fullmatch(
        r"[0-9a-f]{64}",
        str(row["processing_alignment_receipt_sha256"]),
    ) is None:
        raise ReviewBundleError(
            f"Review query {query_region_id} has invalid "
            "processing_alignment_receipt_sha256."
        )
    for field in (
        "pre_source_asset_ids",
        "event_source_asset_ids",
        "pre_product_ids",
        "event_product_ids",
    ):
        _split_lineage_values(
            row[field],
            label=f"Review query {query_region_id} {field}",
        )
    for field in ("pre_source_sha256s", "event_source_sha256s"):
        values = _split_lineage_values(
            row[field],
            label=f"Review query {query_region_id} {field}",
        )
        if any(re.fullmatch(r"[0-9a-f]{64}", value) is None for value in values):
            raise ReviewBundleError(
                f"Review query {query_region_id} {field} must contain only "
                "lowercase complete SHA-256 values."
            )
    for field in ("pre_acquisition_utc", "event_acquisition_utc"):
        _validate_utc_timestamp(
            row[field],
            label=f"Review query {query_region_id} {field}",
        )


def _validate_supported_query_review_lineage(row: dict[str, object]) -> None:
    """Require complete allowlist lineage before it becomes reviewer-visible."""

    query_region_id = str(row.get("query_region_id", "")).strip() or "<unknown>"
    if not _strict_bool(
        row["supported_query_allowlist_applied"],
        "supported_query_allowlist_applied",
    ):
        raise ReviewBundleError(
            f"Review query {query_region_id} is not covered by its declared "
            "supported-query allowlist."
        )
    for field in (
        "supported_query_derivation_sha256",
        "supported_query_csv_sha256",
    ):
        value = str(row[field])
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ReviewBundleError(
                f"Review query {query_region_id} has invalid {field}."
            )


def _require_consistent_event_source_lineage(
    review_manifest: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    """Return one immutable source-lineage contract per selected event."""

    _require_columns(
        review_manifest,
        QUERY_SOURCE_LINEAGE_COLUMNS,
        "review manifest source lineage",
    )
    lineage_by_event: dict[str, dict[str, str]] = {}
    for event_id, event_rows in review_manifest.groupby("event_id", sort=False):
        for row in event_rows.to_dict(orient="records"):
            _validate_query_source_lineage(row)
        lineage: dict[str, str] = {}
        for field in QUERY_SOURCE_LINEAGE_COLUMNS:
            values = set(event_rows[field].astype(str))
            if len(values) != 1:
                raise ReviewBundleError(
                    f"Selected queries for event {event_id!r} disagree on {field}."
                )
            lineage[field] = next(iter(values))
        lineage_by_event[str(event_id).strip()] = lineage
    return lineage_by_event


def _validate_context_against_event_lineage(
    row: dict[str, object],
    *,
    event_lineage: dict[str, str],
) -> None:
    context_layer_id = str(row["context_layer_id"]).strip()
    if str(row["source_registry_sha256"]) != event_lineage["source_registry_sha256"]:
        raise ReviewBundleError(
            f"Context layer {context_layer_id} source_registry_sha256 does not "
            "match its selected queries."
        )
    role = str(row["layer_role"]).strip()
    if role in {"pre_event_vv", "pre_event_vh"}:
        prefix = "pre"
    elif role in {"event_time_vv", "event_time_vh"}:
        prefix = "event"
    else:
        # Derived and static context still bind to the same source-registry
        # digest. Their detailed lineage is held in that external registry.
        return
    expected = {
        "source_asset_id": _split_lineage_values(
            event_lineage[f"{prefix}_source_asset_ids"],
            label=f"{prefix} source asset ids",
        ),
        "source_product_id": _split_lineage_values(
            event_lineage[f"{prefix}_product_ids"],
            label=f"{prefix} product ids",
        ),
        "source_sha256": _split_lineage_values(
            event_lineage[f"{prefix}_source_sha256s"],
            label=f"{prefix} source checksums",
        ),
    }
    for field, allowed_values in expected.items():
        if str(row[field]) not in allowed_values:
            raise ReviewBundleError(
                f"Context layer {context_layer_id} {field} is not present in "
                f"the selected queries' {prefix}-event source lineage."
            )
    expected_acquisition = event_lineage[f"{prefix}_acquisition_utc"]
    if str(row["acquisition_time_utc"]) != expected_acquisition:
        raise ReviewBundleError(
            f"Context layer {context_layer_id} acquisition_time_utc does not "
            f"match the selected queries' {prefix}-event acquisition."
        )


def validate_processing_receipt_for_review_bundle(
    receipt: dict[str, object],
    *,
    review_manifest: pd.DataFrame,
    context_manifest: pd.DataFrame,
) -> None:
    """Bind formal review inputs to the verified processed-raster receipt."""

    receipt_sha = str(receipt["receipt_sha256"])
    query_receipt_hashes = set(
        review_manifest["processing_alignment_receipt_sha256"].astype(str)
    )
    if query_receipt_hashes != {receipt_sha}:
        raise ReviewBundleError(
            "Selected queries do not bind to the supplied processing/alignment receipt."
        )
    assets = processing_assets_by_id(receipt)
    assets_by_event: dict[str, list[dict[str, object]]] = {}
    for asset in assets.values():
        assets_by_event.setdefault(str(asset["event_id"]), []).append(asset)

    for event_id, event_queries in review_manifest.groupby("event_id", sort=False):
        event_id = str(event_id)
        event_assets = assets_by_event.get(event_id)
        if not event_assets:
            raise ReviewBundleError(
                f"Processing receipt has no non-static source assets for selected "
                f"event {event_id!r}."
            )
        grid_hashes = set(event_queries["grid_contract_sha256"].astype(str))
        receipt_grid_hashes = {
            str(asset["grid_contract_sha256"]) for asset in event_assets
        }
        if len(grid_hashes) != 1 or receipt_grid_hashes != grid_hashes:
            raise ReviewBundleError(
                f"Processing receipt grid does not match selected queries for {event_id!r}."
            )
        expected_asset_ids = set()
        expected_products = set()
        expected_source_hashes = set()
        expected_acquisitions = set()
        for prefix in ("pre", "event"):
            for value in event_queries[f"{prefix}_source_asset_ids"].astype(str):
                expected_asset_ids.update(value.split("|"))
            for value in event_queries[f"{prefix}_product_ids"].astype(str):
                expected_products.update(value.split("|"))
            for value in event_queries[f"{prefix}_source_sha256s"].astype(str):
                expected_source_hashes.update(value.split("|"))
            expected_acquisitions.update(
                event_queries[f"{prefix}_acquisition_utc"].astype(str)
            )
        actual_asset_ids = {str(asset["asset_id"]) for asset in event_assets}
        actual_products = {str(asset["product_id"]) for asset in event_assets}
        actual_source_hashes = {str(asset["source_sha256"]) for asset in event_assets}
        actual_acquisitions = {
            str(asset["acquisition_time_utc"]) for asset in event_assets
        }
        if (
            expected_asset_ids != actual_asset_ids
            or expected_products != actual_products
            or expected_source_hashes != actual_source_hashes
            or expected_acquisitions != actual_acquisitions
        ):
            raise ReviewBundleError(
                f"Processing receipt source lineage does not exactly match selected "
                f"queries for {event_id!r}."
            )
        for query in event_queries.to_dict(orient="records"):
            query_bounds = (
                float(query["bbox_min_x"]),
                float(query["bbox_min_y"]),
                float(query["bbox_max_x"]),
                float(query["bbox_max_y"]),
            )
            for asset in event_assets:
                if not _bounds_contain(processed_bounds(asset), query_bounds):
                    raise ReviewBundleError(
                        f"Processed asset {asset['asset_id']!r} does not cover review "
                        f"query {query['query_region_id']!r}."
                    )

    raw_roles = REQUIRED_SAR_CONTEXT_LAYER_ROLES
    for row in context_manifest.to_dict(orient="records"):
        if str(row["layer_role"]) not in raw_roles:
            continue
        asset_id = str(row["source_asset_id"])
        receipt_asset = assets.get(asset_id)
        if receipt_asset is None:
            raise ReviewBundleError(
                f"Raw SAR context asset {asset_id!r} is absent from the processing receipt."
            )
        expected = {
            "event_id": receipt_asset["event_id"],
            "source_product_id": receipt_asset["product_id"],
            "acquisition_time_utc": receipt_asset["acquisition_time_utc"],
            "source_sha256": receipt_asset["source_sha256"],
            "processed_layer_sha256": receipt_asset["processed_file_sha256"],
            "crs": receipt_asset["output_crs"],
        }
        mismatches = [
            field for field, value in expected.items() if row[field] != value
        ]
        if mismatches:
            raise ReviewBundleError(
                f"Raw SAR context layer {row['context_layer_id']!r} does not match "
                "the processing receipt: "
                + ", ".join(mismatches)
            )


def _bounds_contain(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    tolerance = 1e-7
    return (
        outer[0] <= inner[0] + tolerance
        and outer[1] <= inner[1] + tolerance
        and outer[2] + tolerance >= inner[2]
        and outer[3] + tolerance >= inner[3]
    )


def _split_lineage_values(value: object, *, label: str) -> frozenset[str]:
    text = str(value)
    values = text.split("|")
    if (
        not text
        or text != text.strip()
        or any(not item or item != item.strip() for item in values)
        or len(values) != len(set(values))
    ):
        raise ReviewBundleError(
            f"{label} must be a non-empty, canonical pipe-delimited value set."
        )
    return frozenset(values)


def _rectangle_wkt(row: pd.Series) -> str:
    xmin = float(row["bbox_min_x"])
    ymin = float(row["bbox_min_y"])
    xmax = float(row["bbox_max_x"])
    ymax = float(row["bbox_max_y"])
    return (
        "POLYGON (("
        f"{xmin:g} {ymin:g}, {xmax:g} {ymin:g}, {xmax:g} {ymax:g}, "
        f"{xmin:g} {ymax:g}, {xmin:g} {ymin:g}"
        "))"
    )


def _assert_blinded_columns(frame: pd.DataFrame) -> None:
    leaking = sorted(SENSITIVE_REVIEW_COLUMNS.intersection(frame.columns))
    if leaking:
        raise ReviewBundleError(
            f"Reviewer-visible output contains model/weak-label fields: {', '.join(leaking)}"
        )


def _coerce_review_purpose(value: ReviewPurpose | str) -> ReviewPurpose:
    if isinstance(value, ReviewPurpose):
        return value
    try:
        return ReviewPurpose(str(value).strip())
    except ValueError as exc:
        allowed = ", ".join(purpose.value for purpose in ReviewPurpose)
        raise ReviewBundleError(
            f"Unknown review_purpose {value!r}; expected one of: {allowed}."
        ) from exc


def _reject_active_selection_fields(
    frame: pd.DataFrame,
    *,
    selected_column: str,
) -> None:
    """Prevent active-selection output from activating calibration/test roles."""

    for selection_flag in {selected_column, "selected"}:
        if selection_flag not in frame.columns:
            continue
        selected = frame[selection_flag].map(
            lambda value: _strict_bool(value, selection_flag)
        )
        if selected.any():
            raise ReviewBundleError(
                "Calibration and fixed-evaluation bundles cannot consume rows "
                "activated by a selected flag. Their membership is fixed by "
                "dataset_role before review."
            )
    populated = sorted(
        column
        for column in ACTIVE_SELECTION_COLUMNS
        if column in frame.columns
        and frame[column].astype(str).str.strip().ne("").any()
    )
    if populated:
        raise ReviewBundleError(
            "Calibration and fixed-evaluation bundles cannot contain active-selection "
            f"evidence: {', '.join(populated)}."
        )


def _validate_context_utc_timestamp(
    value: object,
    *,
    context_layer_id: str,
) -> None:
    _validate_utc_timestamp(
        value,
        label=f"Context layer {context_layer_id} acquisition_time_utc",
    )


def _validate_utc_timestamp(value: object, *, label: str) -> datetime:
    raw = str(value)
    text = raw.strip()
    if (
        raw != text
        or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z",
            text,
        )
        is None
    ):
        raise ReviewBundleError(
            f"{label} must be an "
            "ISO-8601 UTC timestamp with seconds ending in Z."
        )
    try:
        timestamp = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ReviewBundleError(
            f"{label} is invalid."
        ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ReviewBundleError(
            f"{label} must be UTC."
        )
    return timestamp


def _bundle_instructions(
    *,
    protocol_version: str,
    taxonomy_version: str,
    target_reviewer_id: str,
    target_reviewer_role_category: str,
    planned_review_start_utc: str,
    human_role_binding_status: str,
) -> str:
    return f"""# FloodGuard blinded flood-label review bundle

Protocol: `{protocol_version}`
Taxonomy: `{taxonomy_version}`
Target reviewer: `{target_reviewer_id or 'synthetic fixture: unbound'}`
Target role: `{target_reviewer_role_category or 'synthetic fixture: unbound'}`
Do not start before: `{planned_review_start_utc or 'synthetic fixture: not authorized'}`
Human-role gate: `{human_role_binding_status}`

1. Confirm that your stable role id and lane above are correct. Do not transfer this bundle to another reviewer or start before the declared UTC time.
2. Verify `context_layers.csv` against its exact product ids, UTC acquisitions, source checksums, processed-layer checksums, event, and CRS before opening external rasters.
3. Load `review_regions.csv` in QGIS as delimited text using `geometry_wkt` and the row's declared CRS.
4. Do not open model predictions, weak labels, entropy, disagreement, selection rank, or another reviewer's work during first-pass annotation.
5. Blank annotation geometry means unreviewed, never dry land.
6. Use only the label taxonomy defined in `docs/label_factory_protocol.md`.
7. Do not replace the prefilled reviewer id. Complete stage, purpose, timestamps, reviewed extent, class, confidence, evidence layers, both blinding flags, creation time, and lock time before import.
8. Keep source rasters and completed annotation geometry in the controlled external workspace; bundle path hints are deliberately redacted.

This bundle is for research annotation only. It is not a flood observation, FPPS input, warning, or field validation.
"""


def _coerce_frame(source: pd.DataFrame | str | Path) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ReviewBundleError(f"{label} is missing columns: {', '.join(missing)}")


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise ReviewBundleError(f"{field} must be an explicit boolean.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_absolute_local_path(value: object) -> bool:
    """Return whether a value resembles an absolute Windows or POSIX path."""

    text = str(value).strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("/"))
