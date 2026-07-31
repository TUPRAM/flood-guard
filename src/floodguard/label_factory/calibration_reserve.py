"""Plan an authority-approved, tile-level reviewer-calibration reserve.

This module deliberately stops before query selection.  It uses only a sealed
canonical grid, support metadata, and governed static context to compare
parent-tile reserve combinations.  It never reads weak labels, reference
labels, reviewer annotations, SAR change features, or model outputs.

The emitted package is therefore a *provisional design*, not a canonical grid,
not a tile-assignment input, and not a review bundle.  A named Reference
Authority must approve a reserve before a separate versioned grid release can
change any dataset role.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.context_alignment import (
    ContextAlignmentError,
    load_context_alignment_manifest,
)
from floodguard.label_factory.manifests import (
    QUERY_MANIFEST_COLUMNS,
    SUPPORTED_QUERY_LINEAGE_COLUMNS,
    SUPPORTED_TILE_LINEAGE_COLUMNS,
    TILE_MANIFEST_COLUMNS,
)


DESIGN_SCHEMA_V1 = "floodguard.calibration_reserve_design.v1"
DESIGN_SCHEMA_V2 = "floodguard.calibration_reserve_design.v2"
DESIGN_SCHEMA = DESIGN_SCHEMA_V2
LEGACY_BUILDER_ID = "floodguard.label_factory.calibration_reserve@v1"
BUILDER_ID = "floodguard.label_factory.calibration_reserve@v2"
PROVISIONAL_STATUS = "provisional_authority_approval_pending"

CANONICAL_TILES_NAME = "canonical_tiles.csv"
CANONICAL_QUERIES_NAME = "canonical_query_regions.csv"
RELEASE_MANIFEST_NAME = "release_manifest.csv"
RELEASE_SEAL_NAME = "release_seal.json"

TILE_SUMMARY_NAME = "tile_context_summary.csv"
CANDIDATES_NAME = "candidate_reserve_combinations.csv"
ROLE_ALLOCATION_NAME = "authority_pending_role_allocation.csv"
AUTHORITY_REQUEST_NAME = "authority_decision_request.md"
README_NAME = "README.md"
DESIGN_RECEIPT_NAME = "design_receipt.json"

TRAINING_ROLE = "training_and_query_pool"
CALIBRATION_ROLE = "reviewer_calibration"

REQUIRED_CONTEXT_ROLES = frozenset(
    {"land_cover", "permanent_water_context", "slope"}
)
OPTIONAL_CONTEXT_ROLES = frozenset({"dem_hillshade"})
ALLOWED_CONTEXT_ROLES = REQUIRED_CONTEXT_ROLES | OPTIONAL_CONTEXT_ROLES
KNOWN_CONTEXT_ROLES = ALLOWED_CONTEXT_ROLES | frozenset({"elevation"})
ALLOWED_CONTEXT_SOURCES = frozenset(
    {"worldcover", "jrc_occurrence", "jrc_seasonality", "copernicus_dem"}
)
WORLD_COVER_CODES: tuple[int, ...] = (
    10,
    20,
    30,
    40,
    50,
    60,
    70,
    80,
    90,
    95,
    100,
)

# These fields would let a supposedly context-only planner consume information
# derived from labels, review, or a model.  Fail closed if any are present.
FORBIDDEN_SIGNAL_COLUMNS = frozenset(
    {
        "weak_label",
        "weak_label_code",
        "weak_positive_fraction",
        "reference_label",
        "reference_label_code",
        "human_label",
        "label_code",
        "temporary_flood_probability",
        "flood_probability",
        "model_probability",
        "model_prediction",
        "logistic_prediction",
        "boosted_prediction",
        "prediction_entropy",
        "committee_disagreement",
        "disagreement_score",
        "acquisition_score",
        "selection_score",
        "selection_rank",
        "selection_reason",
    }
)

_TILE_REQUIRED_COLUMNS = (
    "tile_id",
    "event_id",
    "x_index",
    "y_index",
    "dataset_role",
    "valid_data_fraction",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)
_QUERY_REQUIRED_COLUMNS = (
    "query_region_id",
    "tile_id",
    "event_id",
    "query_size_pixels",
    "resolution_m",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "crs",
    "dataset_role",
    "review_status",
    "selected",
    "eligible_for_human_annotation",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "eligible_for_training_after_human_review",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_SCORE_WEIGHTS: Mapping[str, float] = {
    "capacity_efficiency": 0.40,
    "land_cover_coverage": 0.20,
    "context_dispersion": 0.15,
    "spatial_separation": 0.15,
    "source_coverage": 0.10,
}
NEAR_TIE_SCORE_DELTA = 0.005

_ALLOWED_TILE_INPUT_COLUMNS = frozenset(
    (*TILE_MANIFEST_COLUMNS, *SUPPORTED_TILE_LINEAGE_COLUMNS)
)
_ALLOWED_QUERY_INPUT_COLUMNS = frozenset(
    (*QUERY_MANIFEST_COLUMNS, *SUPPORTED_QUERY_LINEAGE_COLUMNS)
)


class CalibrationReserveError(ValueError):
    """Raised when a reserve design cannot be produced without leakage."""


@dataclass(frozen=True, slots=True)
class CalibrationReservePaths:
    """Paths written by one immutable provisional reserve-design build."""

    tile_context_summary: Path
    candidate_combinations: Path
    authority_pending_role_allocation: Path
    authority_decision_request: Path
    readme: Path
    design_receipt: Path

    def as_dict(self) -> dict[str, Path]:
        """Return stable artifact-role to path mappings."""

        return {
            "tile_context_summary": self.tile_context_summary,
            "candidate_combinations": self.candidate_combinations,
            "authority_pending_role_allocation": (
                self.authority_pending_role_allocation
            ),
            "authority_decision_request": self.authority_decision_request,
            "readme": self.readme,
            "design_receipt": self.design_receipt,
        }


def build_calibration_reserve_design(
    *,
    canonical_grid_directory: str | Path,
    context_alignment_manifest_path: str | Path,
    output_directory: str | Path,
    design_id: str,
    calibration_query_count: int = 12,
    retest_query_count: int = 12,
    reserve_tile_count: int = 2,
    candidate_limit: int = 20,
    minimum_remaining_pool_queries: int = 20,
    created_at_utc: str | datetime | None = None,
) -> CalibrationReservePaths:
    """Write a fail-closed, authority-pending parent-tile reserve design.

    Candidate combinations are scored with support capacity, source coverage,
    land-cover variety, static-context dispersion, and spatial separation.
    Those signals are useful for *reserve design only* and are not evidence of
    event-time flood.  The function emits no query shortlist and performs no
    final calibration selection.
    """

    normalized_design_id = _identifier(design_id, "design_id")
    calibration_count = _positive_integer(
        calibration_query_count, "calibration_query_count"
    )
    retest_count = _positive_integer(retest_query_count, "retest_query_count")
    tile_count = _positive_integer(reserve_tile_count, "reserve_tile_count")
    limit = _positive_integer(candidate_limit, "candidate_limit")
    remaining_minimum = _non_negative_integer(
        minimum_remaining_pool_queries, "minimum_remaining_pool_queries"
    )
    if calibration_count < 8:
        raise CalibrationReserveError(
            "calibration_query_count must be at least eight."
        )
    if retest_count < 8:
        raise CalibrationReserveError(
            "retest_query_count must reserve at least eight fresh queries."
        )
    if tile_count < 2:
        raise CalibrationReserveError(
            "reserve_tile_count must be at least two spatial blocks."
        )
    created_at = _created_at(created_at_utc)

    grid_directory = _required_directory(
        canonical_grid_directory, "canonical grid directory"
    )
    output = Path(output_directory)
    if output.exists():
        raise CalibrationReserveError(
            f"Output directory is immutable and already exists: {output}"
        )

    grid_evidence = _verify_canonical_grid_release(grid_directory)
    sealed_at = _created_at(str(grid_evidence["sealed_at_utc"]))
    if created_at < sealed_at:
        raise CalibrationReserveError(
            "created_at_utc cannot predate the parent canonical grid release."
        )
    tile_path = grid_directory / CANONICAL_TILES_NAME
    query_path = grid_directory / CANONICAL_QUERIES_NAME
    tiles = _read_csv(tile_path, "canonical tiles")
    queries = _read_csv(query_path, "canonical query regions")
    _validate_canonical_pool(tiles, queries)

    context_path = _required_file(
        context_alignment_manifest_path, "context alignment manifest"
    )
    try:
        context_manifest = load_context_alignment_manifest(context_path)
    except ContextAlignmentError as exc:
        raise CalibrationReserveError(str(exc)) from exc
    context_evidence, context_datasets = _open_context_layers(
        context_path, context_manifest, queries
    )
    try:
        tile_summary = _build_tile_context_summary(
            tiles,
            queries,
            context_datasets,
        )
    finally:
        for dataset in context_datasets.values():
            dataset.close()

    target_capacity = calibration_count + retest_count
    candidates = _build_candidate_combinations(
        tile_summary,
        reserve_tile_count=tile_count,
        target_capacity=target_capacity,
        minimum_remaining_pool_queries=remaining_minimum,
    )
    if candidates.empty:
        raise CalibrationReserveError(
            "No parent-tile reserve combination preserves both the requested "
            "calibration/retest capacity and the minimum remaining query pool."
        )
    candidates = candidates.head(limit).copy()
    candidates.insert(0, "candidate_rank", range(1, len(candidates) + 1))
    candidates["recommended_provisional_design"] = False
    candidates.loc[candidates.index[0], "recommended_provisional_design"] = True

    recommendation = candidates.iloc[0].to_dict()
    top_score = float(recommendation["candidate_score"])
    candidates["within_near_tie_threshold"] = (
        top_score - candidates["candidate_score"].astype(float)
        <= NEAR_TIE_SCORE_DELTA
    )
    near_ties = candidates.loc[candidates["within_near_tie_threshold"]].copy()
    conservative_row = near_ties.sort_values(
        ["reserved_query_capacity", "candidate_score", "tile_ids"],
        ascending=[True, False, True],
        kind="stable",
    ).iloc[0]
    conservation_alternative = conservative_row.to_dict()
    if conservation_alternative["candidate_id"] == recommendation["candidate_id"]:
        conservation_alternative = None
    candidates["authority_conservation_option"] = False
    if conservation_alternative is not None:
        candidates.loc[
            candidates["candidate_id"] == conservation_alternative["candidate_id"],
            "authority_conservation_option",
        ] = True
    recommended_tile_ids = frozenset(
        str(recommendation["tile_ids"]).split("|")
    )
    role_allocation = _build_authority_pending_role_allocation(
        tile_summary,
        recommended_tile_ids=recommended_tile_ids,
    )

    parent_existed = output.parent.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    )
    try:
        artifact_evidence: dict[str, dict[str, object]] = {}
        for role, file_name, frame in (
            ("tile_context_summary", TILE_SUMMARY_NAME, tile_summary),
            ("candidate_combinations", CANDIDATES_NAME, candidates),
            (
                "authority_pending_role_allocation",
                ROLE_ALLOCATION_NAME,
                role_allocation,
            ),
        ):
            path = temporary / file_name
            frame.to_csv(
                path,
                index=False,
                lineterminator="\n",
                float_format="%.12g",
            )
            artifact_evidence[role] = _artifact_record(path, len(frame))

        authority_text = _authority_request_text(
            design_id=normalized_design_id,
            parent_release_id=str(grid_evidence["release_id"]),
            recommendation=recommendation,
            calibration_count=calibration_count,
            retest_count=retest_count,
            conservation_alternative=conservation_alternative,
        )
        authority_path = temporary / AUTHORITY_REQUEST_NAME
        authority_path.write_text(
            authority_text, encoding="utf-8", newline="\n"
        )
        artifact_evidence["authority_decision_request"] = _artifact_record(
            authority_path
        )

        readme_path = temporary / README_NAME
        readme_path.write_text(
            _readme_text(
                design_id=normalized_design_id,
                parent_release_id=str(grid_evidence["release_id"]),
                recommendation=recommendation,
                calibration_count=calibration_count,
                retest_count=retest_count,
                conservation_alternative=conservation_alternative,
            ),
            encoding="utf-8",
            newline="\n",
        )
        artifact_evidence["readme"] = _artifact_record(readme_path)

        payload: dict[str, object] = {
            "artifact_schema": DESIGN_SCHEMA,
            "builder": BUILDER_ID,
            "design_id": normalized_design_id,
            "status": PROVISIONAL_STATUS,
            "created_at_utc": _format_utc(created_at),
            "parent_canonical_grid_release": grid_evidence,
            "context_alignment": context_evidence,
            "planning_parameters": {
                "calibration_query_count": calibration_count,
                "fresh_retest_query_count": retest_count,
                "minimum_reserved_query_capacity": target_capacity,
                "reserve_tile_count": tile_count,
                "candidate_limit": limit,
                "minimum_remaining_pool_queries": remaining_minimum,
                "score_weights": dict(_SCORE_WEIGHTS),
                "near_tie_score_delta": NEAR_TIE_SCORE_DELTA,
                "score_scope": (
                    "governed support and static non-label context only"
                ),
            },
            "provisional_recommendation": {
                "candidate_id": str(recommendation["candidate_id"]),
                "tile_ids": sorted(recommended_tile_ids),
                "reserved_query_capacity": int(
                    recommendation["reserved_query_capacity"]
                ),
                "remaining_training_pool_query_count": int(
                    recommendation["remaining_training_pool_query_count"]
                ),
                "authority_approval_required": True,
                "authority_approval_status": "pending",
            },
            "near_tie_authority_review": _near_tie_receipt_record(
                recommendation,
                conservation_alternative,
            ),
            "authority_decision_required": {
                "decision": (
                    "Approve one candidate parent-tile reserve, or reject all "
                    "and document a context-diversity concern."
                ),
                "must_confirm": [
                    "The reserved parent tiles provide adequate non-label context diversity for calibration design.",
                    "The reserve is not evidence that temporary flood exists in any query.",
                    "The final 12 calibration queries and any retest queries remain unselected and unseen.",
                ],
                "reference_authority_id": None,
                "decision_timestamp_utc": None,
                "approval_evidence_sha256": None,
            },
            "safety": {
                "uses_weak_or_reference_labels": False,
                "uses_reviewer_annotations": False,
                "uses_model_outputs": False,
                "uses_event_time_flood_claims": False,
                "final_calibration_query_ids": [],
                "final_retest_query_ids": [],
                "review_bundles_created": False,
                "human_evidence_created": False,
                "valid_tile_assignments_input": False,
                "eligible_for_human_annotation": False,
                "eligible_for_active_selection": False,
                "eligible_for_review_queue": False,
                "eligible_for_query_model_training": False,
                "eligible_for_training_after_human_review": "no",
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            },
            "outputs": artifact_evidence,
            "assumptions": (
                "Candidate scores compare reserve capacity, source coverage, "
                "WorldCover composition, JRC permanent-water context, terrain "
                "context, and spatial separation. Static context is not event-time "
                "flood truth. The provisional recommendation cannot change a "
                "dataset role or authorize review."
            ),
        }
        receipt = {**payload, "receipt_sha256": _canonical_sha256(payload)}
        receipt_path = temporary / DESIGN_RECEIPT_NAME
        receipt_path.write_text(
            json.dumps(
                receipt,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_calibration_reserve_design_receipt(receipt)
        verify_calibration_reserve_design_package(temporary)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if not parent_existed:
            try:
                output.parent.rmdir()
            except OSError:
                pass
        raise

    return CalibrationReservePaths(
        tile_context_summary=output / TILE_SUMMARY_NAME,
        candidate_combinations=output / CANDIDATES_NAME,
        authority_pending_role_allocation=output / ROLE_ALLOCATION_NAME,
        authority_decision_request=output / AUTHORITY_REQUEST_NAME,
        readme=output / README_NAME,
        design_receipt=output / DESIGN_RECEIPT_NAME,
    )


def load_calibration_reserve_design_receipt(path: str | Path) -> dict[str, Any]:
    """Load and verify one self-hashed provisional design receipt."""

    receipt_path = _required_file(path, "calibration reserve design receipt")
    try:
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationReserveError(
            f"Could not read calibration reserve design receipt: {receipt_path}"
        ) from exc
    if not isinstance(value, dict):
        raise CalibrationReserveError("Design receipt must be a JSON object.")
    verify_calibration_reserve_design_receipt(value)
    return value


def verify_calibration_reserve_design_package(
    directory: str | Path,
) -> dict[str, Any]:
    """Verify every file and fail-closed CSV field in a design package."""

    package = _required_directory(directory, "calibration reserve design package")
    receipt = load_calibration_reserve_design_receipt(package / DESIGN_RECEIPT_NAME)
    outputs = receipt.get("outputs")
    if not isinstance(outputs, Mapping):
        raise CalibrationReserveError("Design receipt has no outputs object.")
    expected = {
        "tile_context_summary": TILE_SUMMARY_NAME,
        "candidate_combinations": CANDIDATES_NAME,
        "authority_pending_role_allocation": ROLE_ALLOCATION_NAME,
        "authority_decision_request": AUTHORITY_REQUEST_NAME,
        "readme": README_NAME,
    }
    if set(outputs) != set(expected):
        raise CalibrationReserveError(
            "Design receipt output roles do not match the package contract."
        )
    for role, expected_name in expected.items():
        record = outputs[role]
        if not isinstance(record, Mapping):
            raise CalibrationReserveError(f"Output record must be an object: {role}")
        if record.get("file_name") != expected_name:
            raise CalibrationReserveError(f"Output file name mismatch: {role}")
        path = _required_file(package / expected_name, f"design output {role}")
        if _integer_value(record.get("file_size_bytes"), "file_size_bytes") != path.stat().st_size:
            raise CalibrationReserveError(f"Output file size mismatch: {role}")
        if not _is_sha256(record.get("sha256")) or _file_sha256(path) != record.get("sha256"):
            raise CalibrationReserveError(f"Output file hash mismatch: {role}")
        if "row_count" in record:
            observed_rows = len(_read_csv(path, f"design output {role}"))
            if observed_rows != _integer_value(record["row_count"], "row_count"):
                raise CalibrationReserveError(f"Output row count mismatch: {role}")

    candidates = _read_csv(package / CANDIDATES_NAME, "candidate combinations")
    if "query_region_id" in candidates.columns:
        raise CalibrationReserveError(
            "Candidate combinations must not expose final query IDs."
        )
    _require_boolean_column(
        candidates,
        "final_query_selection_performed",
        False,
        "candidate combinations",
    )
    for field in (
        "eligible_for_human_annotation",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        _require_boolean_column(candidates, field, False, "candidate combinations")
    _require_boolean_column(
        candidates,
        "authority_approval_required",
        True,
        "candidate combinations",
    )
    if candidates["recommended_provisional_design"].map(
        lambda value: _strict_bool(value, "recommended_provisional_design")
    ).sum() != 1:
        raise CalibrationReserveError(
            "Candidate combinations must contain one provisional recommendation."
        )
    near_tie_columns = {
        "within_near_tie_threshold",
        "authority_conservation_option",
    }
    present_near_tie_columns = near_tie_columns & set(candidates.columns)
    near_tie_enabled = _near_tie_extension_enabled(receipt)
    if near_tie_enabled and present_near_tie_columns != near_tie_columns:
        raise CalibrationReserveError(
            "Near-tie-capable candidate combinations must expose both near-tie "
            "and conservation fields."
        )
    if not near_tie_enabled and present_near_tie_columns:
        raise CalibrationReserveError(
            "Legacy candidate combinations contain an unbound near-tie extension."
        )
    if near_tie_enabled:
        for field in sorted(near_tie_columns):
            candidates[field].map(lambda value: _strict_bool(value, field))

    roles = _read_csv(
        package / ROLE_ALLOCATION_NAME,
        "authority-pending role allocation",
    )
    if "query_region_id" in roles.columns:
        raise CalibrationReserveError(
            "Authority-pending role allocation must remain parent-tile-only."
        )
    for field in (
        "valid_tile_assignments_input",
        "final_calibration_query_ids_selected",
        "eligible_for_human_annotation",
        "eligible_for_active_selection",
        "eligible_for_review_queue",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        _require_boolean_column(
            roles, field, False, "authority-pending role allocation"
        )
    if set(roles["eligible_for_training_after_human_review"].astype(str)) != {"no"}:
        raise CalibrationReserveError(
            "Authority-pending role allocation must remain training-ineligible."
        )
    if set(roles["authority_approval_status"].astype(str)) != {"pending"}:
        raise CalibrationReserveError(
            "Authority-pending role allocation must remain pending."
        )
    return receipt


def verify_calibration_reserve_design_receipt(
    receipt: Mapping[str, Any],
) -> None:
    """Verify the fail-closed safety state and self-hash of a design receipt."""

    schema = receipt.get("artifact_schema")
    if schema not in {DESIGN_SCHEMA_V1, DESIGN_SCHEMA_V2}:
        raise CalibrationReserveError("Unknown calibration reserve design schema.")
    expected_builder = (
        LEGACY_BUILDER_ID if schema == DESIGN_SCHEMA_V1 else BUILDER_ID
    )
    if receipt.get("builder") != expected_builder:
        raise CalibrationReserveError(
            "Calibration reserve design schema and builder version disagree."
        )
    if receipt.get("status") != PROVISIONAL_STATUS:
        raise CalibrationReserveError(
            "Calibration reserve design must remain authority-approval-pending."
        )
    declared = receipt.get("receipt_sha256")
    if not _is_sha256(declared):
        raise CalibrationReserveError("Design receipt has no complete self-hash.")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if _canonical_sha256(unsigned) != declared:
        raise CalibrationReserveError("Design receipt self-hash mismatch.")

    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        raise CalibrationReserveError("Design receipt is missing its safety object.")
    required_false = (
        "uses_weak_or_reference_labels",
        "uses_reviewer_annotations",
        "uses_model_outputs",
        "uses_event_time_flood_claims",
        "review_bundles_created",
        "human_evidence_created",
        "valid_tile_assignments_input",
        "eligible_for_human_annotation",
        "eligible_for_active_selection",
        "eligible_for_review_queue",
        "eligible_for_query_model_training",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    )
    if any(safety.get(field) is not False for field in required_false):
        raise CalibrationReserveError(
            "Provisional reserve design has an unsafe enabled capability."
        )
    if safety.get("eligible_for_training_after_human_review") != "no":
        raise CalibrationReserveError(
            "Provisional reserve design must be training-ineligible."
        )
    if safety.get("final_calibration_query_ids") != []:
        raise CalibrationReserveError(
            "Provisional reserve design must not select calibration queries."
        )
    if safety.get("final_retest_query_ids") != []:
        raise CalibrationReserveError(
            "Provisional reserve design must not select retest queries."
        )

    recommendation = receipt.get("provisional_recommendation")
    if not isinstance(recommendation, Mapping):
        raise CalibrationReserveError(
            "Design receipt is missing its provisional recommendation."
        )
    if recommendation.get("authority_approval_required") is not True:
        raise CalibrationReserveError("Reference Authority approval must be required.")
    if recommendation.get("authority_approval_status") != "pending":
        raise CalibrationReserveError("Reference Authority approval must be pending.")
    _validate_near_tie_extension(receipt)


def _validate_near_tie_extension(receipt: Mapping[str, Any]) -> None:
    """Validate the optional v1 extension or required v2 near-tie contract."""

    schema = receipt.get("artifact_schema")
    planning = receipt.get("planning_parameters")
    if not isinstance(planning, Mapping):
        raise CalibrationReserveError(
            "Design receipt is missing its planning parameters."
        )
    has_threshold = "near_tie_score_delta" in planning
    has_review = "near_tie_authority_review" in receipt
    if has_threshold != has_review:
        raise CalibrationReserveError(
            "Near-tie threshold and authority-review evidence must appear together."
        )
    if schema == DESIGN_SCHEMA_V2 and not has_review:
        raise CalibrationReserveError(
            "Schema v2 requires the conservation-versus-context near-tie contract."
        )
    if not has_review:
        # The original schema-v1 contract used by immutable design v1/v2 ended
        # here. Their complete self-hashes and output hashes still protect every
        # byte; absence of a later optional extension is not retroactive damage.
        return

    try:
        threshold = float(planning["near_tie_score_delta"])
    except (TypeError, ValueError) as exc:
        raise CalibrationReserveError(
            "near_tie_score_delta must be a finite positive number."
        ) from exc
    if not math.isfinite(threshold) or not 0 < threshold < 1:
        raise CalibrationReserveError(
            "near_tie_score_delta must be a finite number between zero and one."
        )
    near_tie = receipt.get("near_tie_authority_review")
    if not isinstance(near_tie, Mapping):
        raise CalibrationReserveError(
            "Design receipt near-tie authority review must be an object."
        )
    try:
        recorded_threshold = float(near_tie["near_tie_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationReserveError(
            "Near-tie authority review must repeat the declared threshold."
        ) from exc
    if not math.isclose(
        recorded_threshold,
        threshold,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise CalibrationReserveError(
            "Near-tie authority-review threshold disagrees with planning parameters."
        )
    if near_tie.get("authority_must_review_tradeoff") is not True:
        raise CalibrationReserveError(
            "Reference Authority must review the candidate tradeoff."
        )
    alternative_present = near_tie.get(
        "capacity_conserving_alternative_present"
    )
    if alternative_present not in {True, False}:
        raise CalibrationReserveError(
            "Near-tie authority review must declare whether an alternative exists."
        )
    if alternative_present:
        required = (
            "rank_1_candidate_id",
            "rank_1_score",
            "rank_1_reserved_query_capacity",
            "rank_1_remaining_training_pool_query_count",
            "capacity_conserving_candidate_id",
            "capacity_conserving_score",
            "capacity_conserving_reserved_query_capacity",
            "capacity_conserving_remaining_training_pool_query_count",
            "score_delta",
            "tradeoff",
        )
        missing = [field for field in required if field not in near_tie]
        if missing:
            raise CalibrationReserveError(
                "Near-tie authority review is missing: " + ", ".join(missing)
            )


def _near_tie_extension_enabled(receipt: Mapping[str, Any]) -> bool:
    """Return whether a verified receipt binds the near-tie extension."""

    return "near_tie_authority_review" in receipt


def _verify_canonical_grid_release(directory: Path) -> dict[str, object]:
    manifest_path = _required_file(
        directory / RELEASE_MANIFEST_NAME, "canonical release manifest"
    )
    seal_path = _required_file(directory / RELEASE_SEAL_NAME, "canonical release seal")
    try:
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationReserveError("Could not read canonical release seal.") from exc
    if not isinstance(seal, dict):
        raise CalibrationReserveError("Canonical release seal must be a JSON object.")
    if seal.get("artifact_schema") != "floodguard.canonical_grid_release.v1":
        raise CalibrationReserveError("Unknown canonical grid release schema.")
    declared = seal.get("seal_sha256")
    unsigned = dict(seal)
    unsigned.pop("seal_sha256", None)
    if not _is_sha256(declared) or _canonical_sha256(unsigned) != declared:
        raise CalibrationReserveError("Canonical grid release seal self-hash mismatch.")
    for field in ("eligible_for_decision_layer", "eligible_for_fpps", "eligible_for_warning"):
        if seal.get(field) is not False:
            raise CalibrationReserveError(
                f"Canonical grid release must have {field}=false."
            )
    if _file_sha256(manifest_path) != seal.get("release_manifest_sha256"):
        raise CalibrationReserveError(
            "Canonical release manifest does not match the release seal."
        )

    manifest = _read_csv(manifest_path, "canonical release manifest")
    _require_columns(
        manifest,
        ("file_name", "file_size_bytes", "sha256", "immutable_status"),
        "canonical release manifest",
    )
    seen: set[str] = set()
    for row in manifest.to_dict("records"):
        name = str(row["file_name"]).strip()
        if not name or Path(name).name != name or name in seen:
            raise CalibrationReserveError(
                "Canonical release manifest contains an unsafe or duplicate file name."
            )
        seen.add(name)
        path = _required_file(directory / name, f"canonical release artifact {name}")
        if path.stat().st_size != _integer_value(row["file_size_bytes"], "file_size_bytes"):
            raise CalibrationReserveError(
                f"Canonical release artifact size mismatch: {name}"
            )
        if _file_sha256(path) != str(row["sha256"]).strip():
            raise CalibrationReserveError(
                f"Canonical release artifact hash mismatch: {name}"
            )
        if not str(row["immutable_status"]).strip().startswith("frozen_"):
            raise CalibrationReserveError(
                f"Canonical release artifact is not frozen: {name}"
            )
    for required_name in (CANONICAL_TILES_NAME, CANONICAL_QUERIES_NAME):
        if required_name not in seen:
            raise CalibrationReserveError(
                f"Canonical release manifest omits {required_name}."
            )
    release_id = str(seal.get("release_id", "")).strip()
    if not release_id:
        raise CalibrationReserveError("Canonical release seal has no release_id.")
    sealed_at_utc = str(seal.get("sealed_at_utc", "")).strip()
    if not sealed_at_utc:
        raise CalibrationReserveError(
            "Canonical release seal has no sealed_at_utc timestamp."
        )
    _created_at(sealed_at_utc)
    return {
        "release_id": release_id,
        "sealed_at_utc": sealed_at_utc,
        "release_seal_sha256": str(declared),
        "release_seal_file_sha256": _file_sha256(seal_path),
        "release_manifest_sha256": _file_sha256(manifest_path),
        "canonical_tiles_sha256": _file_sha256(directory / CANONICAL_TILES_NAME),
        "canonical_query_regions_sha256": _file_sha256(
            directory / CANONICAL_QUERIES_NAME
        ),
    }


def _validate_canonical_pool(tiles: pd.DataFrame, queries: pd.DataFrame) -> None:
    _require_columns(tiles, _TILE_REQUIRED_COLUMNS, "canonical tiles")
    _require_columns(queries, _QUERY_REQUIRED_COLUMNS, "canonical query regions")
    forbidden = sorted(
        (set(tiles.columns) | set(queries.columns)) & FORBIDDEN_SIGNAL_COLUMNS
    )
    if forbidden:
        raise CalibrationReserveError(
            "Reserve planner refuses label/model/selection signal columns: "
            + ", ".join(forbidden)
        )
    unknown_tile_columns = sorted(set(tiles.columns) - _ALLOWED_TILE_INPUT_COLUMNS)
    unknown_query_columns = sorted(set(queries.columns) - _ALLOWED_QUERY_INPUT_COLUMNS)
    if unknown_tile_columns or unknown_query_columns:
        raise CalibrationReserveError(
            "Reserve planner accepts only canonical manifest columns; "
            f"unknown_tile_columns={unknown_tile_columns}; "
            f"unknown_query_columns={unknown_query_columns}."
        )
    if tiles.empty or queries.empty:
        raise CalibrationReserveError("Canonical grid must contain tiles and queries.")
    if tiles["tile_id"].duplicated().any():
        raise CalibrationReserveError("Canonical tiles contain duplicate tile_id values.")
    if queries["query_region_id"].duplicated().any():
        raise CalibrationReserveError(
            "Canonical queries contain duplicate query_region_id values."
        )
    if set(tiles["dataset_role"].astype(str).str.strip()) != {TRAINING_ROLE}:
        raise CalibrationReserveError(
            "Reserve planning requires a wholly unallocated training/query parent release."
        )
    if set(queries["dataset_role"].astype(str).str.strip()) != {TRAINING_ROLE}:
        raise CalibrationReserveError(
            "Reserve planning requires all source queries to remain in the training/query pool."
        )
    if set(queries["review_status"].astype(str).str.strip()) != {"unreviewed"}:
        raise CalibrationReserveError(
            "Reserve planning refuses previously reviewed query regions."
        )
    _require_boolean_column(queries, "selected", False)
    for frame, label in ((tiles, "canonical tiles"), (queries, "canonical queries")):
        _require_boolean_column(frame, "eligible_for_human_annotation", True, label)
        _require_boolean_column(frame, "eligible_for_active_selection", True, label)
        _require_boolean_column(frame, "eligible_for_review_queue", True, label)
        _require_boolean_column(frame, "eligible_for_query_model_training", False, label)
        _require_boolean_column(frame, "eligible_for_decision_layer", False, label)
        _require_boolean_column(frame, "eligible_for_fpps", False, label)
        _require_boolean_column(frame, "eligible_for_warning", False, label)
    if set(queries["eligible_for_training_after_human_review"].astype(str).str.strip()) != {"conditional"}:
        raise CalibrationReserveError(
            "Canonical query training eligibility must be conditional before review."
        )

    tile_ids = set(tiles["tile_id"].astype(str))
    query_tile_ids = set(queries["tile_id"].astype(str))
    if query_tile_ids != tile_ids:
        raise CalibrationReserveError(
            "Every canonical parent tile must contain at least one supported query and no query may reference an unknown tile."
        )
    tile_event = tiles.set_index("tile_id")["event_id"].astype(str).to_dict()
    for row in queries[["tile_id", "event_id"]].to_dict("records"):
        if tile_event[str(row["tile_id"])] != str(row["event_id"]):
            raise CalibrationReserveError(
                f"Query event_id disagrees with parent tile {row['tile_id']}."
            )


def _open_context_layers(
    manifest_path: Path,
    manifest: Mapping[str, Any],
    queries: pd.DataFrame,
) -> tuple[dict[str, object], dict[str, Any]]:
    if manifest.get("builder") != "floodguard.label_factory.context_alignment@v1":
        raise CalibrationReserveError(
            "Context manifest must come from the governed context-alignment builder."
        )
    for field in ("eligible_for_decision_layer", "eligible_for_fpps", "eligible_for_warning"):
        if manifest.get(field) is not False:
            raise CalibrationReserveError(
                f"Context alignment manifest must have {field}=false."
            )
    layer_rows = manifest.get("layers")
    if not isinstance(layer_rows, list):
        raise CalibrationReserveError("Context manifest layers must be a list.")
    by_role: dict[str, Mapping[str, Any]] = {}
    for raw in layer_rows:
        if not isinstance(raw, Mapping):
            raise CalibrationReserveError("Context layer records must be objects.")
        role = str(raw.get("layer_role", "")).strip()
        if role in by_role:
            raise CalibrationReserveError(f"Duplicate context layer role: {role}")
        by_role[role] = raw
    unknown_context_roles = sorted(set(by_role) - KNOWN_CONTEXT_ROLES)
    if unknown_context_roles:
        raise CalibrationReserveError(
            "Context manifest contains unknown or non-context layer roles: "
            + ", ".join(unknown_context_roles)
        )
    missing = sorted(REQUIRED_CONTEXT_ROLES - set(by_role))
    if missing:
        raise CalibrationReserveError(
            "Context manifest is missing required non-label roles: " + ", ".join(missing)
        )
    source_inputs = manifest.get("source_inputs")
    if not isinstance(source_inputs, list) or not source_inputs:
        raise CalibrationReserveError(
            "Context manifest must bind its governed static source inputs."
        )
    declared_source_roles: set[str] = set()
    for raw in source_inputs:
        if not isinstance(raw, Mapping):
            raise CalibrationReserveError("Context source inputs must be objects.")
        source_role = str(raw.get("source_role", "")).strip()
        if not source_role or source_role in declared_source_roles:
            raise CalibrationReserveError(
                "Context source roles must be non-blank and unique."
            )
        declared_source_roles.add(source_role)
    unknown_source_roles = sorted(declared_source_roles - ALLOWED_CONTEXT_SOURCES)
    if unknown_source_roles:
        raise CalibrationReserveError(
            "Context manifest binds non-static or unapproved sources: "
            + ", ".join(unknown_source_roles)
        )
    if declared_source_roles != ALLOWED_CONTEXT_SOURCES:
        raise CalibrationReserveError(
            "Context manifest must bind WorldCover, both JRC inputs, and Copernicus DEM."
        )

    try:
        import rasterio
    except ImportError as exc:
        raise CalibrationReserveError(
            "Calibration reserve planning requires rasterio."
        ) from exc

    target = manifest.get("target_grid")
    if not isinstance(target, Mapping):
        raise CalibrationReserveError("Context manifest has no target_grid object.")
    expected_crs = str(target.get("crs", "")).strip()
    expected_width = _integer_value(target.get("width"), "target_grid.width")
    expected_height = _integer_value(target.get("height"), "target_grid.height")
    expected_affine_raw = target.get("affine")
    if not isinstance(expected_affine_raw, Sequence) or isinstance(
        expected_affine_raw, (str, bytes)
    ) or len(expected_affine_raw) != 6:
        raise CalibrationReserveError("Context target affine must have six values.")
    expected_affine = tuple(float(value) for value in expected_affine_raw)
    if not all(math.isfinite(value) for value in expected_affine):
        raise CalibrationReserveError("Context target affine values must be finite.")
    from rasterio.transform import Affine

    opened: dict[str, Any] = {}
    layer_evidence: dict[str, object] = {}
    try:
        for role in sorted(ALLOWED_CONTEXT_ROLES & set(by_role)):
            row = by_role[role]
            if row.get("allowed_for_blinded_review_candidate") is not True:
                if role in REQUIRED_CONTEXT_ROLES:
                    raise CalibrationReserveError(
                        f"Required context role is not approved for blinded review: {role}"
                    )
                continue
            sources = row.get("source_roles")
            if not isinstance(sources, list) or not sources:
                raise CalibrationReserveError(
                    f"Context layer {role} has no source_roles."
                )
            unknown_sources = sorted(set(str(value) for value in sources) - ALLOWED_CONTEXT_SOURCES)
            if unknown_sources:
                raise CalibrationReserveError(
                    f"Context layer {role} uses unapproved sources: {', '.join(unknown_sources)}"
                )
            name = str(row.get("path_hint", "")).strip()
            if not name or Path(name).name != name:
                raise CalibrationReserveError(
                    f"Context layer {role} has an unsafe path_hint."
                )
            path = _required_file(manifest_path.parent / name, f"context layer {role}")
            declared_hash = str(row.get("processed_layer_sha256", "")).strip()
            if not _is_sha256(declared_hash) or _file_sha256(path) != declared_hash:
                raise CalibrationReserveError(
                    f"Context layer hash mismatch: {role}"
                )
            dataset = rasterio.open(path)
            opened[role] = dataset
            if (
                dataset.count != 1
                or dataset.crs is None
                or dataset.crs.to_string() != expected_crs
                or dataset.width != expected_width
                or dataset.height != expected_height
                or dataset.transform != Affine(*expected_affine)
            ):
                raise CalibrationReserveError(
                    f"Context layer grid mismatch: {role}"
                )
            layer_evidence[role] = {
                "file_name": name,
                "sha256": declared_hash,
                "source_roles": sorted(str(value) for value in sources),
                "static_context_only": True,
            }
        if REQUIRED_CONTEXT_ROLES - set(opened):
            raise CalibrationReserveError(
                "Not all required static context layers could be opened."
            )
        query_crs = set(queries["crs"].astype(str).str.strip())
        if query_crs != {expected_crs}:
            raise CalibrationReserveError(
                "Canonical query CRS does not match the context target grid."
            )
    except Exception:
        for dataset in opened.values():
            dataset.close()
        raise

    return (
        {
            "manifest_file_sha256": _file_sha256(manifest_path),
            "manifest_sha256": str(manifest["manifest_sha256"]),
            "target_grid_sha256": str(target.get("target_grid_sha256", "")),
            "layers": layer_evidence,
            "uses_static_non_label_context_only": True,
            "does_not_establish_event_time_flood_truth": True,
        },
        opened,
    )


def _build_tile_context_summary(
    tiles: pd.DataFrame,
    queries: pd.DataFrame,
    datasets: Mapping[str, Any],
) -> pd.DataFrame:
    np = _require_numpy()
    query_groups = {
        str(tile_id): group.sort_values("query_region_id", kind="stable")
        for tile_id, group in queries.groupby("tile_id", sort=True)
    }
    rows: list[dict[str, object]] = []
    for tile in tiles.sort_values(["y_index", "x_index"], kind="stable").to_dict("records"):
        tile_id = str(tile["tile_id"])
        group = query_groups[tile_id]
        arrays: dict[str, list[Any]] = {role: [] for role in datasets}
        for query in group.to_dict("records"):
            window = _query_window(query, datasets["land_cover"])
            for role, dataset in datasets.items():
                value = dataset.read(1, window=window)
                expected_size = _integer_value(
                    query["query_size_pixels"], "query_size_pixels"
                )
                if value.shape != (expected_size, expected_size):
                    raise CalibrationReserveError(
                        f"Context window shape mismatch for {query['query_region_id']}: {role}"
                    )
                if dataset.nodata is not None and bool(
                    np.any(_nodata_mask(value, dataset.nodata, np))
                ):
                    raise CalibrationReserveError(
                        f"Context layer {role} contains nodata in supported query {query['query_region_id']}."
                    )
                arrays[role].append(value.reshape(-1))
        flattened = {
            role: np.concatenate(parts) for role, parts in arrays.items()
        }
        land_cover = flattened["land_cover"].astype("int64", copy=False)
        unknown = sorted(set(int(value) for value in np.unique(land_cover)) - set(WORLD_COVER_CODES))
        if unknown:
            raise CalibrationReserveError(
                f"Tile {tile_id} contains unsupported WorldCover codes: {unknown}"
            )
        fractions = {
            code: float(np.mean(land_cover == code)) for code in WORLD_COVER_CODES
        }
        positive_fractions = [value for value in fractions.values() if value > 0]
        entropy = -sum(value * math.log(value) for value in positive_fractions)
        normalized_entropy = (
            entropy / math.log(len(positive_fractions))
            if len(positive_fractions) > 1
            else 0.0
        )
        permanent = flattened["permanent_water_context"].astype("int64", copy=False)
        if not set(int(value) for value in np.unique(permanent)) <= {0, 1}:
            raise CalibrationReserveError(
                f"Tile {tile_id} permanent-water context must be binary."
            )
        slope = flattened["slope"].astype("float64", copy=False)
        if not bool(np.isfinite(slope).all()) or bool((slope < 0).any()):
            raise CalibrationReserveError(
                f"Tile {tile_id} slope context contains invalid values."
            )
        hillshade_std = None
        if "dem_hillshade" in flattened:
            hillshade = flattened["dem_hillshade"].astype("float64", copy=False)
            hillshade_std = float(np.std(hillshade))
        row: dict[str, object] = {
            "tile_id": tile_id,
            "event_id": str(tile["event_id"]),
            "x_index": _integer_value(tile["x_index"], "x_index"),
            "y_index": _integer_value(tile["y_index"], "y_index"),
            "current_dataset_role": TRAINING_ROLE,
            "supported_query_count": len(group),
            "tile_valid_data_fraction": _bounded_fraction(
                tile["valid_data_fraction"], "valid_data_fraction"
            ),
            "supported_context_cell_count": int(len(land_cover)),
            "context_valid_data_fraction": 1.0,
            "worldcover_class_count": len(positive_fractions),
            "worldcover_class_codes": "|".join(
                str(code) for code, fraction in fractions.items() if fraction > 0
            ),
            "worldcover_normalized_entropy": normalized_entropy,
            "permanent_water_context_fraction": float(np.mean(permanent == 1)),
            "slope_mean_degrees": float(np.mean(slope)),
            "slope_p90_degrees": float(np.percentile(slope, 90)),
            "slope_ge_10deg_fraction": float(np.mean(slope >= 10.0)),
            "hillshade_standard_deviation": hillshade_std,
            "context_is_event_time_flood_truth": False,
            "uses_weak_or_model_signal": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        for code in WORLD_COVER_CODES:
            row[f"worldcover_{code}_fraction"] = fractions[code]
        signature = [
            *(fractions[code] for code in WORLD_COVER_CODES),
            row["permanent_water_context_fraction"],
            min(float(row["slope_mean_degrees"]) / 90.0, 1.0),
            min(float(row["slope_p90_degrees"]) / 90.0, 1.0),
            row["slope_ge_10deg_fraction"],
        ]
        row["context_signature"] = "|".join(f"{float(value):.12g}" for value in signature)
        rows.append(row)
    return pd.DataFrame(rows)


def _query_window(query: Mapping[str, object], dataset: Any) -> Any:
    from rasterio.windows import from_bounds

    left = float(query["bbox_min_x"])
    bottom = float(query["bbox_min_y"])
    right = float(query["bbox_max_x"])
    top = float(query["bbox_max_y"])
    window = from_bounds(left, bottom, right, top, transform=dataset.transform)
    rounded = window.round_offsets().round_lengths()
    size = _integer_value(query["query_size_pixels"], "query_size_pixels")
    tolerance = 1e-7
    if (
        abs(window.col_off - rounded.col_off) > tolerance
        or abs(window.row_off - rounded.row_off) > tolerance
        or abs(window.width - size) > tolerance
        or abs(window.height - size) > tolerance
        or int(rounded.width) != size
        or int(rounded.height) != size
        or rounded.col_off < 0
        or rounded.row_off < 0
        or rounded.col_off + rounded.width > dataset.width
        or rounded.row_off + rounded.height > dataset.height
    ):
        raise CalibrationReserveError(
            f"Query bounds are not an exact context-grid window: {query['query_region_id']}"
        )
    return rounded


def _build_candidate_combinations(
    tile_summary: pd.DataFrame,
    *,
    reserve_tile_count: int,
    target_capacity: int,
    minimum_remaining_pool_queries: int,
) -> pd.DataFrame:
    np = _require_numpy()
    records = tile_summary.to_dict("records")
    if len(records) < reserve_tile_count:
        raise CalibrationReserveError(
            "Not enough parent tiles for the requested reserve_tile_count."
        )
    total_queries = int(tile_summary["supported_query_count"].sum())
    global_classes = set()
    for value in tile_summary["worldcover_class_codes"]:
        global_classes.update(part for part in str(value).split("|") if part)
    if not global_classes:
        raise CalibrationReserveError("No WorldCover classes are present in the pool.")
    max_spatial_distance = max(
        abs(int(a["x_index"]) - int(b["x_index"]))
        + abs(int(a["y_index"]) - int(b["y_index"]))
        for a, b in combinations(records, 2)
    )
    if max_spatial_distance <= 0:
        raise CalibrationReserveError("Parent-tile grid has no spatial separation.")

    raw: list[dict[str, object]] = []
    for members in combinations(records, reserve_tile_count):
        capacity = sum(int(row["supported_query_count"]) for row in members)
        remaining = total_queries - capacity
        if capacity < target_capacity or remaining < minimum_remaining_pool_queries:
            continue
        tile_ids = tuple(sorted(str(row["tile_id"]) for row in members))
        signatures = [
            np.asarray(
                [float(value) for value in str(row["context_signature"]).split("|")],
                dtype="float64",
            )
            for row in members
        ]
        pair_distances = [
            float(np.linalg.norm(a - b)) for a, b in combinations(signatures, 2)
        ]
        spatial_distances = [
            abs(int(a["x_index"]) - int(b["x_index"]))
            + abs(int(a["y_index"]) - int(b["y_index"]))
            for a, b in combinations(members, 2)
        ]
        classes = set()
        for row in members:
            classes.update(
                value
                for value in str(row["worldcover_class_codes"]).split("|")
                if value
            )
        raw.append(
            {
                "candidate_id": "CALRES-" + _canonical_sha256(tile_ids)[:12].upper(),
                "tile_ids": "|".join(tile_ids),
                "reserve_tile_count": reserve_tile_count,
                "reserved_query_capacity": capacity,
                "minimum_required_query_capacity": target_capacity,
                "capacity_excess": capacity - target_capacity,
                "remaining_training_pool_query_count": remaining,
                "capacity_efficiency_score": target_capacity / capacity,
                "land_cover_class_coverage_score": len(classes) / len(global_classes),
                "worldcover_class_count_union": len(classes),
                "context_dispersion_raw": sum(pair_distances) / len(pair_distances),
                "spatial_separation_score": (
                    (sum(spatial_distances) / len(spatial_distances))
                    / max_spatial_distance
                ),
                "minimum_tile_valid_data_fraction": min(
                    float(row["tile_valid_data_fraction"]) for row in members
                ),
                "minimum_context_valid_data_fraction": min(
                    float(row["context_valid_data_fraction"]) for row in members
                ),
                "authority_approval_required": True,
                "status": PROVISIONAL_STATUS,
                "uses_event_time_flood_truth": False,
                "final_query_selection_performed": False,
                "eligible_for_human_annotation": False,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    if not raw:
        return pd.DataFrame()
    maximum_dispersion = max(float(row["context_dispersion_raw"]) for row in raw)
    for row in raw:
        dispersion_score = (
            float(row["context_dispersion_raw"]) / maximum_dispersion
            if maximum_dispersion > 0
            else 0.0
        )
        source_coverage = min(
            float(row["minimum_tile_valid_data_fraction"]),
            float(row["minimum_context_valid_data_fraction"]),
        )
        row["context_dispersion_score"] = dispersion_score
        row["source_coverage_score"] = source_coverage
        row["candidate_score"] = (
            _SCORE_WEIGHTS["capacity_efficiency"]
            * float(row["capacity_efficiency_score"])
            + _SCORE_WEIGHTS["land_cover_coverage"]
            * float(row["land_cover_class_coverage_score"])
            + _SCORE_WEIGHTS["context_dispersion"] * dispersion_score
            + _SCORE_WEIGHTS["spatial_separation"]
            * float(row["spatial_separation_score"])
            + _SCORE_WEIGHTS["source_coverage"] * source_coverage
        )
    frame = pd.DataFrame(raw)
    return frame.sort_values(
        [
            "candidate_score",
            "reserved_query_capacity",
            "tile_ids",
        ],
        ascending=[False, True, True],
        kind="stable",
        ignore_index=True,
    )


def _build_authority_pending_role_allocation(
    tile_summary: pd.DataFrame,
    *,
    recommended_tile_ids: frozenset[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for tile in tile_summary.to_dict("records"):
        tile_id = str(tile["tile_id"])
        proposed_role = (
            CALIBRATION_ROLE if tile_id in recommended_tile_ids else TRAINING_ROLE
        )
        rows.append(
            {
                "tile_id": tile_id,
                "event_id": str(tile["event_id"]),
                "x_index": int(tile["x_index"]),
                "y_index": int(tile["y_index"]),
                "current_dataset_role": TRAINING_ROLE,
                "proposed_dataset_role_after_authority_approval": proposed_role,
                "supported_query_capacity": int(tile["supported_query_count"]),
                "provisional_design_status": PROVISIONAL_STATUS,
                "authority_approval_required": True,
                "authority_approval_status": "pending",
                "valid_tile_assignments_input": False,
                "final_calibration_query_ids_selected": False,
                "eligible_for_human_annotation": False,
                "eligible_for_active_selection": False,
                "eligible_for_review_queue": False,
                "eligible_for_query_model_training": False,
                "eligible_for_training_after_human_review": "no",
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "assumptions": (
                    "Authority-pending design row only; not a canonical grid "
                    "assignment and not authorization to inspect or review queries."
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["y_index", "x_index"], kind="stable", ignore_index=True
    )


def _authority_request_text(
    *,
    design_id: str,
    parent_release_id: str,
    recommendation: Mapping[str, object],
    calibration_count: int,
    retest_count: int,
    conservation_alternative: Mapping[str, object] | None,
) -> str:
    tile_lines = "\n".join(
        f"- `{tile_id}`" for tile_id in str(recommendation["tile_ids"]).split("|")
    )
    tradeoff = _near_tie_markdown(recommendation, conservation_alternative)
    return f"""# Reference Authority decision request

Design: `{design_id}`  
Parent grid: `{parent_release_id}`  
Status: **PROVISIONAL - AUTHORITY APPROVAL PENDING**

The planner recommends candidate `{recommendation['candidate_id']}`:

{tile_lines}

These parent tiles reserve {int(recommendation['reserved_query_capacity'])} unseen supported query cores. The minimum design need is {calibration_count} calibration queries plus {retest_count} fresh retest queries. No final query IDs have been selected, shown, or frozen.

The recommendation used only governed support coverage, WorldCover composition, JRC permanent-water context, terrain context, and spatial separation. These are context-design signals, not evidence that temporary flood exists in any query.

## Conservation-versus-context tradeoff

{tradeoff}

## Exact decision required

The named Reference Authority must either:

1. approve this candidate parent-tile reserve as sufficiently varied for later calibration-query design; or
2. select a different candidate from `{CANDIDATES_NAME}` and explain why; or
3. reject all candidates and document what context or spatial coverage is missing.

Approval must explicitly confirm that:

- the authority has not treated static context as event-time flood truth;
- the final calibration and retest queries remain unselected and unseen;
- no reviewer bundle may be created from this provisional package; and
- a separate immutable grid release and receipt are required before dataset roles change.

The approval evidence must identify the authority, UTC decision time, selected candidate ID, rationale, and evidence-file SHA-256. Do not edit this directory to record the decision; create a new versioned approval package.
"""


def _readme_text(
    *,
    design_id: str,
    parent_release_id: str,
    recommendation: Mapping[str, object],
    calibration_count: int,
    retest_count: int,
    conservation_alternative: Mapping[str, object] | None,
) -> str:
    tradeoff = _near_tie_markdown(recommendation, conservation_alternative)
    return f"""# Provisional calibration-role grid design

Design `{design_id}` is a code-generated, authority-approval-pending comparison of parent-tile reserves derived from `{parent_release_id}`.

It recommends candidate `{recommendation['candidate_id']}` with {int(recommendation['reserved_query_capacity'])} supported query cores, enough capacity for a later {calibration_count}-query calibration and {retest_count}-query fresh retest. The recommendation is not approved, is not a canonical dataset-role assignment, and is not a reviewer deliverable.

## Authority attention: near-tied alternatives

{tradeoff}

## Safety boundary

- No weak label, reference label, human annotation, SAR change feature, or model output was read.
- Static context was used only to compare composition and terrain diversity. It does not establish event-time flood.
- No final calibration or retest query ID was selected.
- No query preview, review bundle, reference, or human evidence was created.
- Every ML-training, decision-layer, FPPS, warning, active-selection, and review eligibility field in this package is false.
- `{ROLE_ALLOCATION_NAME}` is explicitly not valid tile-assignment input.

The Reference Authority's exact unresolved decision is recorded in `{AUTHORITY_REQUEST_NAME}`. Any approval and canonical role reallocation must be written to a new immutable versioned package; never edit this directory or the parent grid.
"""


def _near_tie_markdown(
    recommendation: Mapping[str, object],
    alternative: Mapping[str, object] | None,
) -> str:
    if alternative is None:
        return (
            "No lower-capacity candidate falls within the declared near-tie score "
            f"delta of {NEAR_TIE_SCORE_DELTA:.3f}. The authority must still review "
            "the complete candidate table rather than treating rank as approval."
        )
    score_1 = float(recommendation["candidate_score"])
    score_2 = float(alternative["candidate_score"])
    delta = score_1 - score_2
    return (
        f"Rank 1 `{recommendation['candidate_id']}` scores {score_1:.12f}, "
        f"reserves {int(recommendation['reserved_query_capacity'])} queries, and "
        f"leaves {int(recommendation['remaining_training_pool_query_count'])}. "
        f"The capacity-conserving near-tie `{alternative['candidate_id']}` scores "
        f"{score_2:.12f}, reserves {int(alternative['reserved_query_capacity'])}, "
        f"and leaves {int(alternative['remaining_training_pool_query_count'])}. "
        f"Their score delta is only {delta:.12f}, within the declared "
        f"{NEAR_TIE_SCORE_DELTA:.3f} near-tie threshold. Rank 1 has stronger "
        "static-context dispersion/spatial-separation evidence; the alternative "
        "removes fewer queries from the future training/query pool. The planner "
        "does not resolve that scientific-governance tradeoff. The Reference "
        "Authority must choose explicitly and document the rationale."
    )


def _near_tie_receipt_record(
    recommendation: Mapping[str, object],
    alternative: Mapping[str, object] | None,
) -> dict[str, object]:
    if alternative is None:
        return {
            "near_tie_threshold": NEAR_TIE_SCORE_DELTA,
            "capacity_conserving_alternative_present": False,
            "authority_must_review_tradeoff": True,
        }
    return {
        "near_tie_threshold": NEAR_TIE_SCORE_DELTA,
        "capacity_conserving_alternative_present": True,
        "rank_1_candidate_id": str(recommendation["candidate_id"]),
        "rank_1_score": float(recommendation["candidate_score"]),
        "rank_1_reserved_query_capacity": int(
            recommendation["reserved_query_capacity"]
        ),
        "rank_1_remaining_training_pool_query_count": int(
            recommendation["remaining_training_pool_query_count"]
        ),
        "capacity_conserving_candidate_id": str(alternative["candidate_id"]),
        "capacity_conserving_score": float(alternative["candidate_score"]),
        "capacity_conserving_reserved_query_capacity": int(
            alternative["reserved_query_capacity"]
        ),
        "capacity_conserving_remaining_training_pool_query_count": int(
            alternative["remaining_training_pool_query_count"]
        ),
        "score_delta": float(recommendation["candidate_score"])
        - float(alternative["candidate_score"]),
        "tradeoff": (
            "rank 1 favors static-context dispersion/spatial separation; the "
            "near-tie alternative conserves more training/query capacity"
        ),
        "authority_must_review_tradeoff": True,
    }


def _artifact_record(path: Path, row_count: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "file_name": path.name,
        "file_size_bytes": path.stat().st_size,
        "sha256": _file_sha256(path),
    }
    if row_count is not None:
        result["row_count"] = row_count
    return result


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise CalibrationReserveError(
            f"{label} is missing required columns: {', '.join(missing)}."
        )


def _require_boolean_column(
    frame: pd.DataFrame,
    column: str,
    expected: bool,
    label: str = "canonical queries",
) -> None:
    values = [_strict_bool(value, column) for value in frame[column]]
    if any(value is not expected for value in values):
        raise CalibrationReserveError(
            f"{label} must have {column}={str(expected).lower()} for every row."
        )


def _strict_bool(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "true":
            return True
        if text == "false":
            return False
    raise CalibrationReserveError(f"{field} must be an exact boolean.")


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise CalibrationReserveError(f"Could not read {label}: {path}") from exc


def _required_directory(path: str | Path, label: str) -> Path:
    result = Path(path)
    if not result.is_dir():
        raise CalibrationReserveError(f"{label} does not exist: {result}")
    return result


def _required_file(path: str | Path, label: str) -> Path:
    result = Path(path)
    if not result.is_file():
        raise CalibrationReserveError(f"{label} does not exist: {result}")
    return result


def _identifier(value: object, field: str) -> str:
    text = str(value).strip()
    if not text or any(not (char.isalnum() or char in "-_.") for char in text):
        raise CalibrationReserveError(
            f"{field} must use only letters, digits, dash, underscore, or dot."
        )
    return text


def _positive_integer(value: object, field: str) -> int:
    number = _integer_value(value, field)
    if number <= 0:
        raise CalibrationReserveError(f"{field} must be positive.")
    return number


def _non_negative_integer(value: object, field: str) -> int:
    number = _integer_value(value, field)
    if number < 0:
        raise CalibrationReserveError(f"{field} must not be negative.")
    return number


def _integer_value(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise CalibrationReserveError(f"{field} must be an integer.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationReserveError(f"{field} must be an integer.") from exc
    if not math.isfinite(number) or not number.is_integer():
        raise CalibrationReserveError(f"{field} must be an integer.")
    return int(number)


def _bounded_fraction(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationReserveError(f"{field} must be a finite fraction.") from exc
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise CalibrationReserveError(f"{field} must be between zero and one.")
    return number


def _created_at(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise CalibrationReserveError(
                "created_at_utc must be an ISO-8601 timestamp."
            ) from exc
    else:
        raise CalibrationReserveError(
            "created_at_utc must be a datetime or ISO-8601 timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CalibrationReserveError("created_at_utc must be timezone-aware.")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:
        raise CalibrationReserveError(
            "Calibration reserve planning requires NumPy."
        ) from exc
    return np


def _nodata_mask(array: Any, nodata: object, np: Any) -> Any:
    try:
        if math.isnan(float(nodata)):
            return np.isnan(array)
    except (TypeError, ValueError):
        pass
    return array == nodata


def _file_sha256(path: Path, *, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise CalibrationReserveError(f"Could not hash file: {path}") from exc
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
