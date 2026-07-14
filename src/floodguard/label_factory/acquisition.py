"""CSV integration for transparent active-learning review-batch selection.

This layer converts region-level acquisition evidence into the typed sampling
contracts, writes an internal audit manifest, and preserves the hard query-only
safety fields.  The internal manifest may contain model evidence; the separate
review-bundle builder applies the reviewer-visible allow-list.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import pandas as pd

from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY
from floodguard.label_factory.sampling import (
    AcquisitionComponents,
    QueryCandidate,
    SamplingError,
    select_review_batch,
)


ACQUISITION_COMPONENT_COLUMNS = (
    "uncertainty",
    "absolute_disagreement",
    "jensen_shannon_disagreement",
    "boundary_impurity",
)
REQUIRED_CANDIDATE_COLUMNS = (
    "query_region_id",
    "event_id",
    "crs",
    "dataset_role",
    "review_status",
    "eligible_for_active_selection",
    *ACQUISITION_COMPONENT_COLUMNS,
    "hard_stratum",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
)


class AcquisitionManifestError(ValueError):
    """Raised when a candidate or selected-query manifest is unsafe."""


ROUND_ZERO_REQUIRED_COLUMNS = (
    "query_region_id",
    "event_id",
    "crs",
    "dataset_role",
    "review_status",
    "eligible_for_active_selection",
    "round0_stratum",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
)


def select_round_zero_manifest(
    candidates: pd.DataFrame,
    *,
    round_id: str,
    batch_size: int,
    random_seed: int = 0,
    minimum_center_distance_m: float = 0.0,
) -> pd.DataFrame:
    """Select a model-independent, stratum-balanced cold-start batch.

    Round 0 must not use logistic/boosted scores.  Candidates are ordered by a
    stable hash inside each explicitly supplied stratum, then chosen in a
    round-robin across strata.  This gives broad initial evidence while keeping
    the selection fully reproducible and independent of weak-model confidence.
    """

    _require_columns(candidates, ROUND_ZERO_REQUIRED_COLUMNS)
    normalized_round_id = _non_blank(round_id, "round_id", 0)
    if candidates.empty:
        raise AcquisitionManifestError("Round-zero candidates must not be empty.")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
        raise AcquisitionManifestError("batch_size must be a positive integer.")
    if batch_size > len(candidates):
        raise AcquisitionManifestError("batch_size exceeds round-zero candidates.")
    if not math.isfinite(minimum_center_distance_m) or minimum_center_distance_m < 0:
        raise AcquisitionManifestError(
            "minimum_center_distance_m must be finite and non-negative."
        )
    if candidates["query_region_id"].astype(str).duplicated().any():
        raise AcquisitionManifestError("query_region_id must be unique.")
    _validate_existing_safety_fields(candidates)
    if not candidates["eligible_for_active_selection"].map(
        lambda value: _boolean(value, "eligible_for_active_selection", 0)
    ).all():
        raise AcquisitionManifestError(
            "Every round-zero candidate must be eligible_for_active_selection=true."
        )

    normalized: list[dict[str, object]] = []
    for row_number, row in candidates.reset_index(drop=True).iterrows():
        region_id = _non_blank(row["query_region_id"], "query_region_id", row_number)
        role = _non_blank(row["dataset_role"], "dataset_role", row_number)
        if role != "training_and_query_pool":
            raise AcquisitionManifestError(
                f"Row {row_number} role {role!r} must never enter round-zero selection."
            )
        review_status = _non_blank(
            row.get("review_status", ""), "review_status", row_number
        )
        if review_status not in {"unreviewed", "pending_manual_review"}:
            raise AcquisitionManifestError(
                f"Row {row_number} is not eligible for primary review: {review_status!r}."
            )
        stratum = _non_blank(row["round0_stratum"], "round0_stratum", row_number)
        bounds = tuple(
            _number(row[column], column, row_number)
            for column in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")
        )
        if not bounds[0] < bounds[2] or not bounds[1] < bounds[3]:
            raise AcquisitionManifestError(
                f"Row {row_number} has invalid projected query bounds."
            )
        normalized.append(
            {
                "query_region_id": region_id,
                "round0_stratum": stratum,
                "bounds": bounds,
            }
        )
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if _bounds_overlap(left["bounds"], right["bounds"]):  # type: ignore[arg-type]
                raise AcquisitionManifestError(
                    "Round-zero candidate query cores overlap: "
                    f"{left['query_region_id']} and {right['query_region_id']}."
                )

    pools: dict[str, list[dict[str, object]]] = {}
    for item in normalized:
        pools.setdefault(str(item["round0_stratum"]), []).append(item)
    for stratum, pool in pools.items():
        pool.sort(
            key=lambda item: (
                _stable_key(random_seed, str(item["query_region_id"])),
                str(item["query_region_id"]),
            )
        )
    strata = sorted(
        pools,
        key=lambda stratum: (_stable_key(random_seed, stratum), stratum),
    )
    selected: list[dict[str, object]] = []
    while len(selected) < batch_size:
        progress = False
        for stratum in strata:
            pool = pools[stratum]
            while pool:
                candidate = pool.pop(0)
                if _too_close(
                    candidate,
                    selected,
                    minimum_center_distance_m=minimum_center_distance_m,
                ):
                    continue
                selected.append(candidate)
                progress = True
                break
            if len(selected) == batch_size:
                break
        if not progress:
            raise AcquisitionManifestError(
                "Could not fill round-zero batch without violating spatial separation."
            )

    order_by_id = {
        str(item["query_region_id"]): index
        for index, item in enumerate(selected, start=1)
    }
    population_by_stratum = {
        stratum: int(
            candidates["round0_stratum"].astype(str).eq(stratum).sum()
        )
        for stratum in set(candidates["round0_stratum"].astype(str))
    }
    selected_strata = [str(item["round0_stratum"]) for item in selected]
    quota_by_stratum = {
        stratum: selected_strata.count(stratum) for stratum in set(selected_strata)
    }
    output = candidates.copy().reset_index(drop=True)
    output["selected"] = output["query_region_id"].astype(str).isin(order_by_id)
    output["selection_lane"] = output["selected"].map(
        lambda value: "round0_stratified" if value else ""
    )
    output["selection_order"] = output["query_region_id"].map(
        lambda value: order_by_id.get(str(value), "")
    )
    output["sampling_stratum"] = output["round0_stratum"].astype(str)
    output["sampling_stratum_population"] = output["sampling_stratum"].map(
        population_by_stratum
    )
    output["sampling_stratum_quota"] = output["sampling_stratum"].map(
        quota_by_stratum
    ).fillna(0).astype(int)
    output["inclusion_probability"] = output.apply(
        lambda row: (
            row["sampling_stratum_quota"] / row["sampling_stratum_population"]
            if row["sampling_stratum_population"]
            else 0.0
        ),
        axis=1,
    )
    output["random_seed"] = random_seed
    output["round_id"] = normalized_round_id
    output["source_candidate_pool_sha256"] = _frame_sha256(candidates)
    output["selection_purpose"] = "human_review_queue_only"
    output["selection_basis"] = "model_independent_stratification"
    output["selection_policy_version"] = "round0_stratified_v1"
    output["selection_creates_flood_truth"] = False
    for field, value in QUERY_MODEL_ELIGIBILITY.as_manifest_fields().items():
        output[field] = value
    return output


def select_active_learning_manifest(
    candidates: pd.DataFrame,
    *,
    round_id: str,
    diversity_columns: tuple[str, ...],
    batch_size: int,
    random_seed: int = 0,
    disagreement_metric: str = "absolute",
    minimum_center_distance_m: float = 0.0,
    near_duplicate_feature_distance: float | None = 1e-9,
    maximum_per_event: int | None = None,
    maximum_per_land_cover_stratum: int | None = None,
) -> pd.DataFrame:
    """Return all candidate rows with deterministic selection audit fields.

    ``candidates`` is one row per non-overlapping query core.  All coordinates
    must be in one declared projected metre CRS per event.  Diversity columns
    are explicit and versionable; they are never inferred from arbitrary
    numeric columns.
    """

    _require_columns(candidates, REQUIRED_CANDIDATE_COLUMNS)
    normalized_round_id = _non_blank(round_id, "round_id", 0)
    if not diversity_columns:
        raise AcquisitionManifestError("At least one diversity column is required.")
    _require_columns(candidates, diversity_columns)
    if candidates.empty:
        raise AcquisitionManifestError("Candidate manifest must not be empty.")
    if candidates["query_region_id"].astype(str).duplicated().any():
        raise AcquisitionManifestError("query_region_id must be unique.")
    _validate_existing_safety_fields(candidates)
    if not candidates["eligible_for_active_selection"].map(
        lambda value: _boolean(value, "eligible_for_active_selection", 0)
    ).all():
        raise AcquisitionManifestError(
            "Every active-learning candidate must be eligible_for_active_selection=true."
        )

    typed: list[QueryCandidate] = []
    for row_number, row in candidates.reset_index(drop=True).iterrows():
        region_id = _non_blank(row["query_region_id"], "query_region_id", row_number)
        review_status = _non_blank(
            row.get("review_status", ""), "review_status", row_number
        )
        if review_status not in {"unreviewed", "pending_manual_review"}:
            raise AcquisitionManifestError(
                f"Row {row_number} is not eligible for primary review: {review_status!r}."
            )
        bounds = tuple(
            _number(row[column], column, row_number)
            for column in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y")
        )
        typed.append(
            QueryCandidate(
                region_id=region_id,
                event_id=_non_blank(row["event_id"], "event_id", row_number),
                crs=_non_blank(row.get("crs", ""), "crs", row_number),
                major_land_cover_stratum=(
                    _optional_text(row.get("major_land_cover_stratum"))
                    or "unspecified"
                ),
                dataset_role=_non_blank(
                    row["dataset_role"], "dataset_role", row_number
                ),
                components=AcquisitionComponents(
                    **{
                        column: _number(row[column], column, row_number)
                        for column in ACQUISITION_COMPONENT_COLUMNS
                    }
                ),
                diversity_features=tuple(
                    _number(row[column], column, row_number)
                    for column in diversity_columns
                ),
                hard_stratum=_boolean(row["hard_stratum"], "hard_stratum", row_number),
                bounds=bounds,  # type: ignore[arg-type]
                overlap_group=_optional_text(row.get("overlap_group_id")),
                near_duplicate_group=_optional_text(row.get("near_duplicate_group_id")),
            )
        )
    try:
        selection = select_review_batch(
            typed,
            batch_size=batch_size,
            random_seed=random_seed,
            disagreement_metric=disagreement_metric,  # type: ignore[arg-type]
            minimum_center_distance=minimum_center_distance_m,
            near_duplicate_feature_distance=near_duplicate_feature_distance,
            maximum_per_event=maximum_per_event,
            maximum_per_land_cover_stratum=maximum_per_land_cover_stratum,
        )
    except SamplingError as exc:
        raise AcquisitionManifestError(str(exc)) from exc

    selected_by_id = {item.region_id: item for item in selection.selected}
    score_by_id = {
        item.region_id: item.scored_candidate for item in selection.selected
    }
    # Calculate scores for every candidate through the same sampling API so
    # rejection remains auditable, not merely absent from the selected subset.
    from floodguard.label_factory.sampling import score_query_candidates

    try:
        all_scores = score_query_candidates(
            typed,
            disagreement_metric=disagreement_metric,  # type: ignore[arg-type]
        )
    except SamplingError as exc:
        raise AcquisitionManifestError(str(exc)) from exc
    score_by_id.update({item.region_id: item for item in all_scores})

    output = candidates.copy().reset_index(drop=True)
    output["uncertainty_rank"] = output["query_region_id"].map(
        lambda value: score_by_id[str(value)].uncertainty_rank
    )
    output["disagreement_rank"] = output["query_region_id"].map(
        lambda value: score_by_id[str(value)].disagreement_rank
    )
    output["boundary_rank"] = output["query_region_id"].map(
        lambda value: score_by_id[str(value)].boundary_rank
    )
    output["active_score"] = output["query_region_id"].map(
        lambda value: score_by_id[str(value)].active_score
    )
    output["disagreement_metric"] = disagreement_metric
    output["selected"] = output["query_region_id"].astype(str).isin(selected_by_id)
    output["selection_lane"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].lane
        if str(value) in selected_by_id
        else ""
    )
    output["selection_order"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].selection_order
        if str(value) in selected_by_id
        else ""
    )
    output["sampling_stratum"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].sampling_stratum
        if str(value) in selected_by_id
        else ""
    )
    output["sampling_stratum_population"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].sampling_stratum_population
        if str(value) in selected_by_id
        else ""
    )
    output["sampling_stratum_quota"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].sampling_stratum_quota
        if str(value) in selected_by_id
        else ""
    )
    output["inclusion_probability"] = output["query_region_id"].map(
        lambda value: selected_by_id[str(value)].inclusion_probability
        if str(value) in selected_by_id
        else ""
    )
    output["random_seed"] = random_seed
    output["round_id"] = normalized_round_id
    output["source_candidate_pool_sha256"] = _frame_sha256(candidates)
    output["requested_active_quota"] = selection.requested_quotas.active
    output["requested_hard_stratum_quota"] = (
        selection.requested_quotas.hard_stratum
    )
    output["requested_random_control_quota"] = (
        selection.requested_quotas.random_control
    )
    output["achieved_active_quota"] = selection.achieved_quotas.active
    output["achieved_hard_stratum_quota"] = selection.achieved_quotas.hard_stratum
    output["achieved_random_control_quota"] = selection.achieved_quotas.random_control
    output["selection_policy_version"] = "uncertainty_disagreement_diversity_v1"
    for field, value in QUERY_MODEL_ELIGIBILITY.as_manifest_fields().items():
        output[field] = value
    output["selection_purpose"] = "human_review_queue_only"
    output["selection_creates_flood_truth"] = False
    return output


def build_acquisition_summary(selection_manifest: pd.DataFrame) -> str:
    """Render a short safety-first Markdown summary for one selection run."""

    _require_columns(
        selection_manifest,
        ("query_region_id", "selected", "selection_lane"),
    )
    selected = selection_manifest[
        selection_manifest["selected"].map(
            lambda value: _boolean(value, "selected", 0)
        )
    ]
    counts = selected["selection_lane"].value_counts().to_dict()
    lines = [
        "# Active-learning review queue",
        "",
        "Status: query-model only; this queue creates no flood truth and is ineligible for FPPS.",
        "",
        f"Candidates evaluated: {len(selection_manifest)}",
        f"Regions selected: {len(selected)}",
        f"Round-0 stratified lane: {int(counts.get('round0_stratified', 0))}",
        f"Active lane: {int(counts.get('active', 0))}",
        f"Hard-stratum lane: {int(counts.get('hard_stratum', 0))}",
        f"Random-control lane: {int(counts.get('random_control', 0))}",
        "",
        "Only the separately generated blinded review bundle should be given to reviewers.",
    ]
    return "\n".join(lines) + "\n"


def write_active_learning_selection(
    candidates: pd.DataFrame | str | Path,
    *,
    round_id: str,
    diversity_columns: tuple[str, ...],
    batch_size: int,
    manifest_output_path: str | Path,
    summary_output_path: str | Path,
    random_seed: int = 0,
    disagreement_metric: str = "absolute",
    minimum_center_distance_m: float = 0.0,
    near_duplicate_feature_distance: float | None = 1e-9,
    maximum_per_event: int | None = None,
    maximum_per_land_cover_stratum: int | None = None,
) -> dict[str, Path]:
    """Select a batch and write the internal manifest plus safe summary."""

    frame = (
        candidates.copy()
        if isinstance(candidates, pd.DataFrame)
        else pd.read_csv(candidates).fillna("")
    )
    selected = select_active_learning_manifest(
        frame,
        round_id=round_id,
        diversity_columns=diversity_columns,
        batch_size=batch_size,
        random_seed=random_seed,
        disagreement_metric=disagreement_metric,
        minimum_center_distance_m=minimum_center_distance_m,
        near_duplicate_feature_distance=near_duplicate_feature_distance,
        maximum_per_event=maximum_per_event,
        maximum_per_land_cover_stratum=maximum_per_land_cover_stratum,
    )
    manifest_path = Path(manifest_output_path)
    summary_path = Path(summary_output_path)
    if manifest_path.suffix.lower() != ".csv":
        raise AcquisitionManifestError("Selection manifest output must be CSV.")
    if summary_path.suffix.lower() not in {".md", ".markdown"}:
        raise AcquisitionManifestError("Selection summary output must be Markdown.")
    _require_new_output_paths(manifest_path, summary_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(manifest_path, index=False)
    summary_path.write_text(build_acquisition_summary(selected), encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}


def write_round_zero_selection(
    candidates: pd.DataFrame | str | Path,
    *,
    round_id: str,
    batch_size: int,
    manifest_output_path: str | Path,
    summary_output_path: str | Path,
    random_seed: int = 0,
    minimum_center_distance_m: float = 0.0,
) -> dict[str, Path]:
    """Write a model-independent cold-start selection and its summary."""

    frame = (
        candidates.copy()
        if isinstance(candidates, pd.DataFrame)
        else pd.read_csv(candidates).fillna("")
    )
    selection = select_round_zero_manifest(
        frame,
        round_id=round_id,
        batch_size=batch_size,
        random_seed=random_seed,
        minimum_center_distance_m=minimum_center_distance_m,
    )
    manifest_path = Path(manifest_output_path)
    summary_path = Path(summary_output_path)
    if manifest_path.suffix.lower() != ".csv":
        raise AcquisitionManifestError("Selection manifest output must be CSV.")
    if summary_path.suffix.lower() not in {".md", ".markdown"}:
        raise AcquisitionManifestError("Selection summary output must be Markdown.")
    _require_new_output_paths(manifest_path, summary_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    selection.to_csv(manifest_path, index=False)
    summary_path.write_text(build_acquisition_summary(selection), encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}


def _validate_existing_safety_fields(frame: pd.DataFrame) -> None:
    expected = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()
    for field, required in expected.items():
        if field not in frame.columns:
            continue
        for row_number, value in enumerate(frame[field]):
            if isinstance(required, bool):
                if _boolean(value, field, row_number) is not required:
                    raise AcquisitionManifestError(
                        f"Row {row_number} relaxes required safety field {field}."
                    )
            elif str(value).strip() != required:
                raise AcquisitionManifestError(
                    f"Row {row_number} has unsafe {field}={value!r}; expected {required!r}."
                )


def _require_new_output_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise AcquisitionManifestError("Selection output paths must be distinct.")
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise AcquisitionManifestError(
            "Selection outputs are immutable and cannot be overwritten: "
            + ", ".join(existing)
        )


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise AcquisitionManifestError(
            f"Candidate manifest is missing columns: {', '.join(missing)}"
        )


def _non_blank(value: object, field: str, row: int) -> str:
    text = str(value).strip()
    if not text:
        raise AcquisitionManifestError(f"Row {row} has blank {field}.")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _number(value: object, field: str, row: int) -> float:
    if isinstance(value, bool):
        raise AcquisitionManifestError(f"Row {row} {field} must be numeric.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise AcquisitionManifestError(
            f"Row {row} {field} must be numeric."
        ) from exc
    if not pd.notna(numeric) or numeric in {float("inf"), float("-inf")}:
        raise AcquisitionManifestError(f"Row {row} {field} must be finite.")
    return numeric


def _boolean(value: object, field: str, row: int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no", ""}:
        return False
    raise AcquisitionManifestError(f"Row {row} {field} must be boolean.")


def _stable_key(random_seed: int, value: str) -> str:
    return hashlib.sha256(f"{random_seed}:{value}".encode("utf-8")).hexdigest()


def _frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.copy()
    canonical.columns = [str(column) for column in canonical.columns]
    canonical = canonical.reindex(sorted(canonical.columns), axis=1)
    if "query_region_id" in canonical.columns:
        canonical = canonical.sort_values("query_region_id", kind="stable")
    encoded = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bounds_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return (
        min(first[2], second[2]) > max(first[0], second[0])
        and min(first[3], second[3]) > max(first[1], second[1])
    )


def _too_close(
    candidate: dict[str, object],
    selected: list[dict[str, object]],
    *,
    minimum_center_distance_m: float,
) -> bool:
    if minimum_center_distance_m <= 0:
        return False
    bounds = candidate["bounds"]
    assert isinstance(bounds, tuple)
    center = (0.5 * (bounds[0] + bounds[2]), 0.5 * (bounds[1] + bounds[3]))
    for item in selected:
        other = item["bounds"]
        assert isinstance(other, tuple)
        other_center = (
            0.5 * (other[0] + other[2]),
            0.5 * (other[1] + other[3]),
        )
        if math.dist(center, other_center) < minimum_center_distance_m:
            return True
    return False
