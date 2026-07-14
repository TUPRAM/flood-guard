"""Build an internal-only active-learning operator queue.

The operator queue deliberately combines evidence that must never be shown to
first-pass reviewers: weak-reference summaries, query-committee scores,
acquisition ranks, and selection-lane metadata.  It is an audit/report artifact
for deciding which already-selected query cores should be packaged for blinded
human review.  It creates no flood truth and is permanently ineligible for the
decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Mapping, Sequence

import pandas as pd

from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY


OPERATOR_QUEUE_SCHEMA = "floodguard.active_learning_operator_queue.v1"
OPERATOR_QUEUE_MANIFEST_SCHEMA = (
    "floodguard.active_learning_operator_queue_manifest.v1"
)

IDENTITY_COLUMNS = (
    "query_region_id",
    "event_id",
    "tile_id",
    "grid_contract_sha256",
)

PROJECTED_BOUNDS_COLUMNS = (
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
)
WGS84_BOUNDS_COLUMNS = (
    "wgs84_min_longitude",
    "wgs84_min_latitude",
    "wgs84_max_longitude",
    "wgs84_max_latitude",
)

CONTEXT_COLUMNS = (
    "permanent_water_fraction",
    "worldcover_water_fraction",
    "urban_fraction",
    "forest_fraction",
    "cropland_fraction",
    "steep_terrain_fraction",
    "slope_p90_degrees",
    "round0_stratum",
    "major_land_cover_stratum",
    "hard_stratum",
)
CONTEXT_FRACTION_COLUMNS = (
    "permanent_water_fraction",
    "worldcover_water_fraction",
    "urban_fraction",
    "forest_fraction",
    "cropland_fraction",
    "steep_terrain_fraction",
)

WEAK_COLUMNS = (
    "weak_label",
    "weak_positive_fraction",
    "weak_uncertain_fraction",
    "weak_unreviewed_fraction",
    "weak_boundary_query",
    "weak_source_type",
    "weak_source_sha256",
    "weak_summary_manifest_sha256",
)
PREVIEW_COLUMNS = (
    "preview_path",
    "preview_sha256",
    "preview_manifest_sha256",
)

MODEL_SCORE_ALIASES: Mapping[str, tuple[str, ...]] = {
    "mean_logistic_query_score": (
        "mean_logistic_query_score",
        "mean_logistic_probability",
        "logistic_query_score",
    ),
    "mean_boosted_query_score": (
        "mean_boosted_query_score",
        "mean_boosted_probability",
        "boosted_query_score",
    ),
    "entropy_score": (
        "entropy_score",
        "uncertainty",
        "normalized_entropy",
        "entropy",
    ),
}

REQUIRED_ACQUISITION_COLUMNS = (
    *IDENTITY_COLUMNS,
    "grid_id",
    "crs",
    *PROJECTED_BOUNDS_COLUMNS,
    "selected",
    "selection_lane",
    "selection_order",
    "absolute_disagreement",
    "jensen_shannon_disagreement",
    "active_score",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
    "selection_creates_flood_truth",
)

# Standard query/source lineage is copied only from an explicit allow-list.
# This keeps arbitrary local columns, secrets, and paths out of the package.
SOURCE_PASSTHROUGH_COLUMNS = (
    "grid_id",
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
    "crs",
    "dataset_role",
    "review_status",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "source_timestamp",
    "confidence_class",
    "assumptions",
    "round_id",
    "source_candidate_pool_sha256",
    "uncertainty_rank",
    "disagreement_rank",
    "boundary_rank",
    "boundary_impurity",
    "disagreement_metric",
    "sampling_stratum",
    "sampling_stratum_population",
    "sampling_stratum_quota",
    "inclusion_probability",
)

PRIORITY_BY_LANE: Mapping[str, str] = {
    "active": "high_active_learning",
    "hard_stratum": "high_systematic_error",
    "random_control": "required_random_control",
    "round0_stratified": "required_cold_start",
}

FIXED_SAFETY_FIELDS: Mapping[str, bool | str] = {
    "operator_internal_only": True,
    "reviewer_delivery_allowed": False,
    "selection_creates_flood_truth": False,
    **QUERY_MODEL_ELIGIBILITY.as_manifest_fields(),
}


class OperatorQueueError(ValueError):
    """Raised when an operator queue cannot be built without ambiguity."""


def build_operator_queue(
    acquisition_manifest: pd.DataFrame | str | Path,
    *,
    context_evidence: pd.DataFrame | str | Path | None = None,
    weak_summary: pd.DataFrame | str | Path | None = None,
    preview_manifest: pd.DataFrame | str | Path | None = None,
) -> pd.DataFrame:
    """Return one internal-only row for every selected acquisition query.

    Every supplied auxiliary table must uniquely and exactly identify all
    selected queries by query, event, tile, and grid-contract identity.  Extra
    unselected pool rows are allowed, but missing selected rows, duplicate query
    ids, or identity mismatches fail closed.
    """

    acquisition = _coerce_frame(acquisition_manifest, "acquisition manifest")
    _require_columns(acquisition, REQUIRED_ACQUISITION_COLUMNS, "acquisition manifest")
    if acquisition.empty:
        raise OperatorQueueError("Acquisition manifest must not be empty.")
    _require_unique_query_ids(acquisition, "acquisition manifest")
    _validate_acquisition_safety(acquisition)
    _require_model_score_aliases(acquisition)

    selected_mask = acquisition["selected"].map(
        lambda value: _strict_bool(value, "selected")
    )
    selected = acquisition.loc[selected_mask].copy()
    if selected.empty:
        raise OperatorQueueError("Acquisition manifest contains no selected queries.")
    _validate_identity(selected, "selected acquisition rows")
    _validate_projected_bounds(selected)
    _validate_selection(selected)

    context = _prepare_auxiliary(
        context_evidence,
        selected,
        label="context evidence",
        required_payload=(),
        require_any_payload=(*WGS84_BOUNDS_COLUMNS, *CONTEXT_COLUMNS),
    )
    weak = _prepare_auxiliary(
        weak_summary,
        selected,
        label="weak summary",
        required_payload=WEAK_COLUMNS,
    )
    previews = _prepare_auxiliary(
        preview_manifest,
        selected,
        label="preview manifest",
        required_payload=("preview_path", "preview_sha256"),
    )

    rows: list[dict[str, object]] = []
    for _, source_row in selected.iterrows():
        query_id = str(source_row["query_region_id"])
        context_row = _row_for_query(context, query_id)
        weak_row = _row_for_query(weak, query_id)
        preview_row = _row_for_query(previews, query_id)

        row: dict[str, object] = {
            "artifact_schema": OPERATOR_QUEUE_SCHEMA,
            **{column: source_row[column] for column in IDENTITY_COLUMNS},
            **{column: source_row[column] for column in PROJECTED_BOUNDS_COLUMNS},
        }
        for column in SOURCE_PASSTHROUGH_COLUMNS:
            if column in source_row.index:
                row[column] = source_row[column]

        for column in WGS84_BOUNDS_COLUMNS:
            row[column] = _resolved_value(
                source_row,
                context_row,
                column,
                query_id=query_id,
                numeric=True,
            )
        for column in CONTEXT_COLUMNS:
            row[column] = _resolved_value(
                source_row,
                context_row,
                column,
                query_id=query_id,
                numeric=column in (*CONTEXT_FRACTION_COLUMNS, "slope_p90_degrees"),
            )
        row["context_stratum"] = (
            _optional_text(row.get("round0_stratum"))
            or _optional_text(row.get("major_land_cover_stratum"))
            or "unspecified"
        )
        row["context_evidence_supplied"] = context_row is not None

        for output_column, aliases in MODEL_SCORE_ALIASES.items():
            row[output_column] = _resolve_alias_score(source_row, output_column, aliases)
        row["mean_committee_query_score"] = 0.5 * (
            float(row["mean_logistic_query_score"])
            + float(row["mean_boosted_query_score"])
        )
        for column in (
            "absolute_disagreement",
            "jensen_shannon_disagreement",
            "active_score",
        ):
            row[column] = _probability(source_row[column], column, query_id)

        lane = _non_blank(source_row["selection_lane"], "selection_lane", query_id)
        row["selected"] = True
        row["selection_lane"] = lane
        row["selection_order"] = _positive_integer(
            source_row["selection_order"], "selection_order", query_id
        )
        row["recommended_review_priority"] = PRIORITY_BY_LANE[lane]

        for column in WEAK_COLUMNS:
            row[column] = weak_row[column] if weak_row is not None else ""
        row["weak_summary_supplied"] = weak_row is not None
        row["weak_evidence_semantics"] = (
            "positive_unlabeled_operator_context_only"
            if weak_row is not None
            else "not_supplied"
        )

        for column in PREVIEW_COLUMNS:
            row[column] = (
                preview_row[column]
                if preview_row is not None and column in preview_row.index
                else ""
            )
        row["preview_supplied"] = preview_row is not None

        row.update(FIXED_SAFETY_FIELDS)
        row["operator_use"] = "human_review_queue_prioritisation_report_only"
        rows.append(row)

    output = pd.DataFrame(rows)
    _validate_wgs84_bounds(output)
    _validate_context_values(output)
    _validate_weak_values(output)
    _validate_preview_values(output)
    _validate_preview_files(output, preview_manifest)
    _validate_fixed_safety(output)
    if output["selection_order"].duplicated().any():
        raise OperatorQueueError("Selected acquisition rows have duplicate selection_order.")
    output = output.sort_values(
        ["selection_order", "query_region_id"], kind="stable"
    ).reset_index(drop=True)
    return output


def write_operator_queue_package(
    acquisition_manifest: pd.DataFrame | str | Path,
    *,
    output_dir: str | Path,
    context_evidence: pd.DataFrame | str | Path | None = None,
    weak_summary: pd.DataFrame | str | Path | None = None,
    preview_manifest: pd.DataFrame | str | Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Path]:
    """Atomically write a queue CSV and checksum/self-hashed JSON manifest."""

    target = Path(output_dir)
    if target.exists():
        raise OperatorQueueError(
            f"Operator queue package is write-once and already exists: {target}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    queue = build_operator_queue(
        acquisition_manifest,
        context_evidence=context_evidence,
        weak_summary=weak_summary,
        preview_manifest=preview_manifest,
    )
    created_at = _utc_timestamp(generated_at_utc)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=str(target.parent))
    )
    try:
        queue_path = temporary / "operator_queue.csv"
        manifest_path = temporary / "operator_queue_manifest.json"
        queue.to_csv(queue_path, index=False, lineterminator="\n")
        manifest: dict[str, object] = {
            "artifact_schema": OPERATOR_QUEUE_MANIFEST_SCHEMA,
            "generated_at_utc": created_at,
            "queue_file": queue_path.name,
            "queue_sha256": _sha256_file(queue_path),
            "row_count": len(queue),
            "query_region_ids": queue["query_region_id"].astype(str).tolist(),
            "source_inputs": [
                _source_descriptor("acquisition_manifest", acquisition_manifest),
                *(
                    [_source_descriptor("context_evidence", context_evidence)]
                    if context_evidence is not None
                    else []
                ),
                *(
                    [_source_descriptor("weak_summary", weak_summary)]
                    if weak_summary is not None
                    else []
                ),
                *(
                    [_source_descriptor("preview_manifest", preview_manifest)]
                    if preview_manifest is not None
                    else []
                ),
            ],
            "safety": dict(FIXED_SAFETY_FIELDS),
            "operator_use": "human_review_queue_prioritisation_report_only",
        }
        manifest["manifest_sha256"] = _canonical_sha256(manifest)
        manifest_path.write_text(_json_text(manifest), encoding="utf-8")
        validate_operator_queue_manifest(manifest_path, queue_path=queue_path)
        if target.exists():
            raise OperatorQueueError(
                f"Operator queue package appeared during build: {target}"
            )
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "queue": target / "operator_queue.csv",
        "manifest": target / "operator_queue_manifest.json",
    }


def validate_operator_queue_manifest(
    manifest_path: str | Path,
    *,
    queue_path: str | Path | None = None,
) -> dict[str, object]:
    """Verify a package manifest, its self-hash, queue hash, rows, and safety."""

    manifest_file = Path(manifest_path)
    try:
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatorQueueError(f"Cannot read operator queue manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise OperatorQueueError("Operator queue manifest must be a JSON object.")
    if payload.get("artifact_schema") != OPERATOR_QUEUE_MANIFEST_SCHEMA:
        raise OperatorQueueError("Unsupported operator queue manifest schema.")
    observed_self_hash = payload.get("manifest_sha256")
    without_hash = dict(payload)
    without_hash.pop("manifest_sha256", None)
    if observed_self_hash != _canonical_sha256(without_hash):
        raise OperatorQueueError("Operator queue manifest self-hash mismatch.")
    resolved_queue = (
        Path(queue_path)
        if queue_path is not None
        else manifest_file.parent / str(payload.get("queue_file", ""))
    )
    if resolved_queue.name != payload.get("queue_file"):
        raise OperatorQueueError("Operator queue file name does not match its manifest.")
    if not resolved_queue.is_file():
        raise OperatorQueueError(f"Operator queue CSV does not exist: {resolved_queue}")
    if _sha256_file(resolved_queue) != payload.get("queue_sha256"):
        raise OperatorQueueError("Operator queue CSV checksum mismatch.")
    queue = pd.read_csv(resolved_queue, dtype=str, keep_default_na=False)
    if len(queue) != payload.get("row_count"):
        raise OperatorQueueError("Operator queue row count does not match its manifest.")
    if queue.get("query_region_id", pd.Series(dtype=str)).astype(str).tolist() != payload.get(
        "query_region_ids"
    ):
        raise OperatorQueueError("Operator queue query ids do not match its manifest.")
    _validate_fixed_safety(queue)
    if payload.get("safety") != dict(FIXED_SAFETY_FIELDS):
        raise OperatorQueueError("Operator queue manifest safety contract is invalid.")
    return payload


def _prepare_auxiliary(
    source: pd.DataFrame | str | Path | None,
    selected: pd.DataFrame,
    *,
    label: str,
    required_payload: Sequence[str],
    require_any_payload: Sequence[str] = (),
) -> pd.DataFrame | None:
    if source is None:
        return None
    frame = _coerce_frame(source, label)
    _require_columns(frame, IDENTITY_COLUMNS, label)
    _require_columns(frame, required_payload, label)
    if require_any_payload and not any(column in frame.columns for column in require_any_payload):
        raise OperatorQueueError(
            f"{label} must contain at least one context or WGS84 payload column."
        )
    if frame.empty:
        raise OperatorQueueError(f"{label} must not be empty when supplied.")
    _require_unique_query_ids(frame, label)
    _validate_identity(frame, label)
    indexed = frame.set_index("query_region_id", drop=False)
    for _, base_row in selected.iterrows():
        query_id = str(base_row["query_region_id"])
        if query_id not in indexed.index:
            raise OperatorQueueError(f"{label} is missing selected query {query_id!r}.")
        auxiliary_row = indexed.loc[query_id]
        for column in IDENTITY_COLUMNS[1:]:
            if str(auxiliary_row[column]).strip() != str(base_row[column]).strip():
                raise OperatorQueueError(
                    f"{label} identity mismatch for {query_id!r}: {column}."
                )
        if "grid_id" in frame.columns and str(auxiliary_row["grid_id"]).strip() != str(
            base_row["grid_id"]
        ).strip():
            raise OperatorQueueError(
                f"{label} identity mismatch for {query_id!r}: grid_id."
            )
    return frame


def _row_for_query(frame: pd.DataFrame | None, query_id: str) -> pd.Series | None:
    if frame is None:
        return None
    return frame.loc[frame["query_region_id"].astype(str).eq(query_id)].iloc[0]


def _resolved_value(
    base: pd.Series,
    auxiliary: pd.Series | None,
    column: str,
    *,
    query_id: str,
    numeric: bool,
) -> object:
    base_value = base[column] if column in base.index else ""
    auxiliary_value = (
        auxiliary[column]
        if auxiliary is not None and column in auxiliary.index
        else ""
    )
    base_present = _has_value(base_value)
    auxiliary_present = _has_value(auxiliary_value)
    if base_present and auxiliary_present:
        if numeric:
            left = _finite_number(base_value, column, query_id)
            right = _finite_number(auxiliary_value, column, query_id)
            if not math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12):
                raise OperatorQueueError(
                    f"Conflicting {column} for selected query {query_id!r}."
                )
        elif str(base_value).strip() != str(auxiliary_value).strip():
            raise OperatorQueueError(
                f"Conflicting {column} for selected query {query_id!r}."
            )
    if auxiliary_present:
        return auxiliary_value
    return base_value if base_present else ""


def _resolve_alias_score(
    row: pd.Series,
    output_column: str,
    aliases: Sequence[str],
) -> float:
    values: list[tuple[str, float]] = []
    query_id = str(row["query_region_id"])
    for alias in aliases:
        if alias in row.index and _has_value(row[alias]):
            values.append((alias, _probability(row[alias], alias, query_id)))
    if not values:
        raise OperatorQueueError(
            f"Selected query {query_id!r} is missing {output_column}."
        )
    reference = values[0][1]
    if any(
        not math.isclose(reference, value, rel_tol=1e-12, abs_tol=1e-12)
        for _, value in values[1:]
    ):
        names = ", ".join(name for name, _ in values)
        raise OperatorQueueError(
            f"Selected query {query_id!r} has conflicting aliases for "
            f"{output_column}: {names}."
        )
    return reference


def _require_model_score_aliases(frame: pd.DataFrame) -> None:
    missing = [
        output
        for output, aliases in MODEL_SCORE_ALIASES.items()
        if not any(alias in frame.columns for alias in aliases)
    ]
    if missing:
        raise OperatorQueueError(
            "Acquisition manifest is missing model score summaries: "
            + ", ".join(missing)
            + "."
        )


def _validate_acquisition_safety(frame: pd.DataFrame) -> None:
    expected = {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "selection_creates_flood_truth": False,
    }
    for column, required in expected.items():
        observed = frame[column].map(lambda value: _strict_bool(value, column))
        if not observed.eq(required).all():
            raise OperatorQueueError(
                f"Acquisition safety field {column} must remain {required}."
            )


def _validate_fixed_safety(frame: pd.DataFrame) -> None:
    for column, required in FIXED_SAFETY_FIELDS.items():
        if column not in frame.columns:
            raise OperatorQueueError(f"Operator queue is missing safety field {column}.")
        if isinstance(required, bool):
            observed = frame[column].map(lambda value: _strict_bool(value, column))
            if not observed.eq(required).all():
                raise OperatorQueueError(
                    f"Operator queue safety field {column} must remain {required}."
                )
        elif not frame[column].astype(str).eq(str(required)).all():
            raise OperatorQueueError(
                f"Operator queue safety field {column} must remain {required!r}."
            )


def _validate_identity(frame: pd.DataFrame, label: str) -> None:
    for column in (*IDENTITY_COLUMNS, "grid_id"):
        if column not in frame.columns and column == "grid_id":
            continue
        if frame[column].map(_optional_text).eq("").any():
            raise OperatorQueueError(f"{label} contains a blank {column}.")
    if not frame["grid_contract_sha256"].astype(str).str.fullmatch(r"[0-9a-f]{64}").all():
        raise OperatorQueueError(f"{label} grid_contract_sha256 must be lowercase SHA-256.")


def _validate_projected_bounds(frame: pd.DataFrame) -> None:
    values = {
        column: frame[column].map(
            lambda value, name=column: _finite_number(value, name, "selected query")
        )
        for column in PROJECTED_BOUNDS_COLUMNS
    }
    if not (values["bbox_min_x"] < values["bbox_max_x"]).all() or not (
        values["bbox_min_y"] < values["bbox_max_y"]
    ).all():
        raise OperatorQueueError("Selected queries must have positive projected bounds.")


def _validate_wgs84_bounds(frame: pd.DataFrame) -> None:
    for column in WGS84_BOUNDS_COLUMNS:
        if frame[column].map(_optional_text).eq("").any():
            raise OperatorQueueError(
                "Selected operator rows require complete WGS84 bounds; provide them "
                "in the acquisition manifest or context evidence."
            )
    lon_min = pd.to_numeric(frame["wgs84_min_longitude"], errors="coerce")
    lon_max = pd.to_numeric(frame["wgs84_max_longitude"], errors="coerce")
    lat_min = pd.to_numeric(frame["wgs84_min_latitude"], errors="coerce")
    lat_max = pd.to_numeric(frame["wgs84_max_latitude"], errors="coerce")
    if any(series.isna().any() for series in (lon_min, lon_max, lat_min, lat_max)):
        raise OperatorQueueError("WGS84 bounds must be finite numbers.")
    if not lon_min.between(-180, 180).all() or not lon_max.between(-180, 180).all():
        raise OperatorQueueError("WGS84 longitudes must be in [-180, 180].")
    if not lat_min.between(-90, 90).all() or not lat_max.between(-90, 90).all():
        raise OperatorQueueError("WGS84 latitudes must be in [-90, 90].")
    if not (lon_min < lon_max).all() or not (lat_min < lat_max).all():
        raise OperatorQueueError("Selected queries must have positive WGS84 bounds.")


def _validate_selection(frame: pd.DataFrame) -> None:
    orders: list[int] = []
    for _, row in frame.iterrows():
        query_id = str(row["query_region_id"])
        lane = _non_blank(row["selection_lane"], "selection_lane", query_id)
        if lane not in PRIORITY_BY_LANE:
            raise OperatorQueueError(
                f"Selected query {query_id!r} has unknown selection_lane {lane!r}."
            )
        orders.append(_positive_integer(row["selection_order"], "selection_order", query_id))
        for column in (
            "absolute_disagreement",
            "jensen_shannon_disagreement",
            "active_score",
        ):
            _probability(row[column], column, query_id)
    if len(orders) != len(set(orders)):
        raise OperatorQueueError("Selected acquisition rows have duplicate selection_order.")


def _validate_context_values(frame: pd.DataFrame) -> None:
    for column in CONTEXT_FRACTION_COLUMNS:
        for query_id, value in zip(frame["query_region_id"], frame[column]):
            if _has_value(value):
                _probability(value, column, str(query_id))
    for query_id, value in zip(frame["query_region_id"], frame["slope_p90_degrees"]):
        if _has_value(value) and _finite_number(
            value, "slope_p90_degrees", str(query_id)
        ) < 0:
            raise OperatorQueueError("slope_p90_degrees must be non-negative.")


def _validate_weak_values(frame: pd.DataFrame) -> None:
    for _, row in frame.loc[frame["weak_summary_supplied"]].iterrows():
        query_id = str(row["query_region_id"])
        fractions = [
            _probability(row[column], column, query_id)
            for column in (
                "weak_positive_fraction",
                "weak_uncertain_fraction",
                "weak_unreviewed_fraction",
            )
        ]
        if not math.isclose(sum(fractions), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise OperatorQueueError(
                f"Weak fractions for selected query {query_id!r} must sum to 1."
            )
        _non_blank(row["weak_label"], "weak_label", query_id)
        _strict_bool(row["weak_boundary_query"], "weak_boundary_query")
        _non_blank(row["weak_source_type"], "weak_source_type", query_id)
        for column in ("weak_source_sha256", "weak_summary_manifest_sha256"):
            _sha256_text(row[column], column, query_id)


def _validate_preview_values(frame: pd.DataFrame) -> None:
    for _, row in frame.loc[frame["preview_supplied"]].iterrows():
        query_id = str(row["query_region_id"])
        _non_blank(row["preview_path"], "preview_path", query_id)
        _sha256_text(row["preview_sha256"], "preview_sha256", query_id)
        if _has_value(row["preview_manifest_sha256"]):
            _sha256_text(
                row["preview_manifest_sha256"],
                "preview_manifest_sha256",
                query_id,
            )


def _validate_preview_files(
    frame: pd.DataFrame,
    preview_manifest: pd.DataFrame | str | Path | None,
) -> None:
    """Verify selected preview bytes when their manifest came from a CSV file."""

    if preview_manifest is None or isinstance(preview_manifest, pd.DataFrame):
        return
    manifest_parent = Path(preview_manifest).resolve().parent
    for _, row in frame.loc[frame["preview_supplied"]].iterrows():
        query_id = str(row["query_region_id"])
        declared = Path(str(row["preview_path"]))
        preview_path = (
            declared.resolve()
            if declared.is_absolute()
            else (manifest_parent / declared).resolve()
        )
        if not preview_path.is_file():
            raise OperatorQueueError(
                f"Preview file for selected query {query_id!r} does not exist: "
                f"{preview_path}"
            )
        if _sha256_file(preview_path) != str(row["preview_sha256"]):
            raise OperatorQueueError(
                f"Preview file checksum mismatch for selected query {query_id!r}."
            )


def _coerce_frame(source: pd.DataFrame | str | Path, label: str) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    try:
        return pd.read_csv(Path(source), dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise OperatorQueueError(f"Cannot read {label}: {exc}") from exc


def _require_columns(frame: pd.DataFrame, required: Sequence[str], label: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise OperatorQueueError(f"{label} is missing columns: {', '.join(missing)}.")


def _require_unique_query_ids(frame: pd.DataFrame, label: str) -> None:
    values = frame.get("query_region_id", pd.Series(dtype=str)).astype(str)
    if values.duplicated().any():
        duplicate = values.loc[values.duplicated(keep=False)].iloc[0]
        raise OperatorQueueError(f"{label} has duplicate query_region_id {duplicate!r}.")


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise OperatorQueueError(f"{field} must be a strict boolean.")


def _probability(value: object, field: str, query_id: str) -> float:
    number = _finite_number(value, field, query_id)
    if not 0.0 <= number <= 1.0:
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must be in [0, 1]."
        )
    return number


def _finite_number(value: object, field: str, query_id: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must be numeric."
        ) from exc
    if not math.isfinite(number):
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must be finite."
        )
    return number


def _positive_integer(value: object, field: str, query_id: str) -> int:
    number = _finite_number(value, field, query_id)
    if not number.is_integer() or number <= 0:
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must be a positive integer."
        )
    return int(number)


def _sha256_text(value: object, field: str, query_id: str) -> str:
    text = str(value).strip()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must be lowercase SHA-256."
        )
    return text


def _non_blank(value: object, field: str, query_id: str) -> str:
    text = str(value).strip()
    if not text:
        raise OperatorQueueError(
            f"{field} for selected query {query_id!r} must not be blank."
        )
    return text


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _has_value(value: object) -> bool:
    return _optional_text(value) != ""


def _source_descriptor(
    role: str,
    source: pd.DataFrame | str | Path,
) -> dict[str, str]:
    if isinstance(source, pd.DataFrame):
        payload = source.to_csv(index=False, lineterminator="\n").encode("utf-8")
        return {
            "role": role,
            "file_name": "<in_memory_dataframe>",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    path = Path(source)
    return {"role": role, "file_name": path.name, "sha256": _sha256_file(path)}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Mapping[str, object]) -> str:
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _utc_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    if not text or text != value:
        raise OperatorQueueError("generated_at_utc must be canonical UTC text.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperatorQueueError("generated_at_utc must be a valid timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise OperatorQueueError("generated_at_utc must use UTC.")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")
