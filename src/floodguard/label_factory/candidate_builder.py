"""Aggregate cell-level query-committee scores into region candidates.

Committee scoring is one row per supported cell; acquisition selects one row
per non-overlapping query core.  This module is the explicit bridge.  It uses
top-tail entropy/disagreement, requires a separately supplied region boundary
diagnostic, and rejects metadata or diversity summaries that vary within a
query region.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY
from floodguard.label_factory.sampling import compute_region_acquisition_components


QUERY_METADATA_COLUMNS = (
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

SCORE_COLUMNS = (
    "logistic_query_score",
    "boosted_query_score",
)


class CandidateBuilderError(ValueError):
    """Raised when cell scores cannot become safe region candidates."""


def build_region_candidate_manifest(
    cell_scores: pd.DataFrame,
    *,
    diversity_columns: tuple[str, ...],
    boundary_impurity_column: str = "boundary_impurity",
    hard_stratum_column: str = "hard_stratum",
    land_cover_stratum_column: str = "major_land_cover_stratum",
    top_tail_fraction: float = 0.20,
) -> pd.DataFrame:
    """Aggregate one or more supported cell scores per query region.

    Diversity, boundary, stratum, and query metadata fields must be constant
    within each query.  This function does not guess an aggregation rule for
    them; upstream feature construction must explicitly provide versioned
    region summaries such as VV/VH percentiles and land-cover fractions.
    """

    required = (
        *QUERY_METADATA_COLUMNS,
        *SCORE_COLUMNS,
        boundary_impurity_column,
        hard_stratum_column,
        land_cover_stratum_column,
        *diversity_columns,
    )
    _require_columns(cell_scores, required)
    if cell_scores.empty:
        raise CandidateBuilderError("Cell score input must not be empty.")
    if not diversity_columns:
        raise CandidateBuilderError("At least one diversity summary is required.")
    _validate_score_safety(cell_scores)

    rows: list[dict[str, object]] = []
    for query_region_id, group in cell_scores.groupby(
        "query_region_id", sort=True, dropna=False
    ):
        if not str(query_region_id).strip():
            raise CandidateBuilderError("query_region_id must not be blank.")
        constant_columns = (
            *QUERY_METADATA_COLUMNS[1:],
            boundary_impurity_column,
            hard_stratum_column,
            land_cover_stratum_column,
            *diversity_columns,
        )
        constants: dict[str, object] = {}
        for column in constant_columns:
            values = group[column].drop_duplicates().tolist()
            if len(values) != 1:
                raise CandidateBuilderError(
                    f"Query {query_region_id!r} has non-constant region field {column!r}."
                )
            constants[column] = values[0]
        try:
            logistic_probabilities = pd.to_numeric(
                group["logistic_query_score"], errors="raise"
            ).tolist()
            boosted_probabilities = pd.to_numeric(
                group["boosted_query_score"], errors="raise"
            ).tolist()
            components = compute_region_acquisition_components(
                logistic_probabilities,
                boosted_probabilities,
                boundary_impurity=float(constants[boundary_impurity_column]),
                top_tail_fraction=top_tail_fraction,
            )
        except (TypeError, ValueError) as exc:
            raise CandidateBuilderError(
                f"Query {query_region_id!r} has invalid score evidence: {exc}"
            ) from exc
        mean_logistic_probability = sum(logistic_probabilities) / len(
            logistic_probabilities
        )
        mean_boosted_probability = sum(boosted_probabilities) / len(
            boosted_probabilities
        )
        mean_committee_probability = 0.5 * (
            mean_logistic_probability + mean_boosted_probability
        )
        row = {
            "query_region_id": str(query_region_id),
            **{column: constants[column] for column in QUERY_METADATA_COLUMNS[1:]},
            **components.to_dict(),
            # Internal operator diagnostics only. The blinded-review builder
            # removes these fields before reviewer delivery.
            "mean_logistic_probability": mean_logistic_probability,
            "mean_boosted_probability": mean_boosted_probability,
            "mean_committee_probability": mean_committee_probability,
            "committee_distance_from_0_5": abs(
                mean_committee_probability - 0.5
            ),
            "hard_stratum": _strict_bool(
                constants[hard_stratum_column],
                hard_stratum_column,
            ),
            "major_land_cover_stratum": _non_blank(
                constants[land_cover_stratum_column],
                land_cover_stratum_column,
            ),
            **{column: constants[column] for column in diversity_columns},
            "supported_cell_count": len(group),
            "top_tail_fraction": top_tail_fraction,
            "score_aggregation": "mean_top_tail",
            "selection_creates_flood_truth": False,
        }
        for field, value in QUERY_MODEL_ELIGIBILITY.as_manifest_fields().items():
            row[field] = value
        rows.append(row)
    return pd.DataFrame(rows)


def write_region_candidate_manifest(
    cell_scores: pd.DataFrame | str | Path,
    *,
    diversity_columns: tuple[str, ...],
    output_path: str | Path,
    boundary_impurity_column: str = "boundary_impurity",
    hard_stratum_column: str = "hard_stratum",
    land_cover_stratum_column: str = "major_land_cover_stratum",
    top_tail_fraction: float = 0.20,
) -> Path:
    """Build and write a region candidate CSV."""

    frame = (
        cell_scores.copy()
        if isinstance(cell_scores, pd.DataFrame)
        else pd.read_csv(cell_scores).fillna("")
    )
    candidates = build_region_candidate_manifest(
        frame,
        diversity_columns=diversity_columns,
        boundary_impurity_column=boundary_impurity_column,
        hard_stratum_column=hard_stratum_column,
        land_cover_stratum_column=land_cover_stratum_column,
        top_tail_fraction=top_tail_fraction,
    )
    output = Path(output_path)
    if output.suffix.lower() != ".csv":
        raise CandidateBuilderError("Candidate manifest output must be CSV.")
    output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output, index=False)
    return output


def _validate_score_safety(frame: pd.DataFrame) -> None:
    expected = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()
    for field, required in expected.items():
        if field not in frame:
            raise CandidateBuilderError(
                f"Cell score input is missing query-model safety field {field}."
            )
        for value in frame[field]:
            if isinstance(required, bool):
                if _strict_bool(value, field) is not required:
                    raise CandidateBuilderError(
                        f"Cell score safety field {field} must remain {required}."
                    )
            elif str(value) != required:
                raise CandidateBuilderError(
                    f"Cell score safety field {field} must remain {required!r}."
                )


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise CandidateBuilderError(
            f"Cell score input is missing columns: {', '.join(missing)}"
        )


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise CandidateBuilderError(f"{field} must be an explicit boolean.")


def _non_blank(value: object, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise CandidateBuilderError(f"{field} must not be blank.")
    return text
