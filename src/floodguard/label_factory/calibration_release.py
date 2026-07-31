"""Freeze an approved reviewer-calibration grid and query membership release.

This is the narrow bridge between an approved Reference Authority design
decision and later calibration-reference/reviewer-bundle construction.  It
changes whole parent tiles from ``training_and_query_pool`` to
``reviewer_calibration`` and deterministically freezes exactly twelve initial
calibration queries plus twelve disjoint fresh-retest queries.

The bridge consumes no label, reviewer, weak-mask, model, probability, entropy,
or acquisition-rank evidence.  Its output does not authorize reference labels,
calibration execution, reviewer bundles, formal review, training, evaluation,
the decision layer, FPPS, or warnings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any

import pandas as pd

from floodguard.label_factory.calibration_reserve import (
    CALIBRATION_ROLE,
    CANONICAL_QUERIES_NAME,
    CANONICAL_TILES_NAME,
    CANDIDATES_NAME,
    RELEASE_MANIFEST_NAME,
    RELEASE_SEAL_NAME,
    TRAINING_ROLE,
    CalibrationReserveError,
    _validate_canonical_pool,
    _verify_canonical_grid_release,
    verify_calibration_reserve_design_package,
)
from floodguard.label_factory.reference_authority_approval import (
    APPROVED_STATUS,
    MANIFEST_NAME as AUTHORITY_MANIFEST_NAME,
    ReferenceAuthorityApprovalError,
    validate_reference_authority_approval_package,
)


RECEIPT_SCHEMA = "floodguard.calibration_release_receipt.v1"
CANONICAL_RELEASE_SCHEMA = "floodguard.canonical_grid_release.v1"
BUILDER_ID = "floodguard.label_factory.calibration_release@v1"
RELEASE_STATUS = "frozen_membership_calibration_not_executed"
SELECTION_ALGORITHM = "sha256_domain_separated_round_robin_by_parent_tile_v1"

CALIBRATION_QUERY_COUNT = 12
FRESH_RETEST_QUERY_COUNT = 12

CALIBRATION_QUERIES_NAME = "calibration_queries.csv"
FRESH_RETEST_QUERIES_NAME = "fresh_retest_queries.csv"
RECEIPT_NAME = "calibration_release_receipt.json"
README_NAME = "README.md"

AUTHORITY_BINDING_PATH = PurePosixPath("bindings/reference_authority_approval")
PARENT_GRID_BINDING_PATH = PurePosixPath("bindings/parent_canonical_grid")

_UTC_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}")

_RECEIPT_KEYS = frozenset(
    {
        "artifact_schema",
        "builder",
        "release_id",
        "created_at_utc",
        "status",
        "event_id",
        "parent_canonical_grid_release",
        "authority_approval",
        "approved_reserve",
        "selection_contract",
        "role_counts",
        "authentication",
        "safety",
        "artifacts",
        "assumptions",
        "evidence_limitation",
        "receipt_sha256",
    }
)

_SAFETY_FALSE_FIELDS = (
    "uses_weak_or_reference_labels",
    "uses_reviewer_annotations",
    "uses_model_outputs",
    "uses_event_time_flood_claims",
    "creates_reference_geometry_or_labels",
    "creates_review_bundles",
    "review_bundle_authorized",
    "calibration_execution_authorized",
    "formal_review_authorized",
    "eligible_for_active_selection",
    "eligible_for_review_queue",
    "eligible_for_query_model_training",
    "eligible_for_training_after_human_review",
    "eligible_for_model_training",
    "eligible_for_model_evaluation",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_ROOT_RELEASE_ARTIFACTS = (
    CANONICAL_TILES_NAME,
    CANONICAL_QUERIES_NAME,
    CALIBRATION_QUERIES_NAME,
    FRESH_RETEST_QUERIES_NAME,
    README_NAME,
    RECEIPT_NAME,
)

_MUTABLE_TILE_FIELDS = frozenset(
    {
        "dataset_role",
        "eligible_for_active_selection",
        "eligible_for_review_queue",
    }
)
_MUTABLE_QUERY_FIELDS = frozenset(
    {
        "dataset_role",
        "eligible_for_active_selection",
        "eligible_for_review_queue",
        "eligible_for_training_after_human_review",
    }
)

_EVIDENCE_LIMITATION = (
    "This release validates copied bytes, SHA-256 bindings, deterministic query "
    "membership, and the approval package's declared attribution. It does not "
    "independently authenticate a person, verify a digital signature or opaque "
    "evidence semantics, create flood truth, or authorize calibration execution."
)


class CalibrationReleaseError(ValueError):
    """Raised when an approved calibration release cannot be frozen safely."""


@dataclass(frozen=True, slots=True)
class CalibrationReleasePaths:
    """Paths written by one immutable calibration-membership release."""

    directory: Path
    canonical_tiles: Path
    canonical_query_regions: Path
    calibration_queries: Path
    fresh_retest_queries: Path
    receipt: Path
    release_manifest: Path
    release_seal: Path

    def as_dict(self) -> dict[str, Path]:
        """Return stable artifact-role to path mappings."""

        return {
            "canonical_tiles": self.canonical_tiles,
            "canonical_query_regions": self.canonical_query_regions,
            "calibration_queries": self.calibration_queries,
            "fresh_retest_queries": self.fresh_retest_queries,
            "receipt": self.receipt,
            "release_manifest": self.release_manifest,
            "release_seal": self.release_seal,
        }


def build_calibration_release(
    *,
    reference_authority_approval_package: str | Path,
    canonical_grid_directory: str | Path,
    output_directory: str | Path,
    release_id: str,
    created_at_utc: str | datetime | None = None,
) -> CalibrationReleasePaths:
    """Freeze one approved whole-tile role release and 12/12 membership split.

    Selection is deterministic and uses only query identity, parent-tile
    membership, and immutable authority/parent release hashes.  It deliberately
    has no optional scoring or model inputs.
    """

    normalized_release_id = _identifier(release_id, "release_id")
    created_at = _created_at(created_at_utc)
    authority_root = _required_directory(
        Path(reference_authority_approval_package),
        "Reference Authority approval package",
    )
    parent_root = _required_directory(
        Path(canonical_grid_directory), "parent canonical grid release"
    )
    output = Path(output_directory)
    if output.exists():
        raise CalibrationReleaseError(
            f"Output directory is immutable and already exists: {output}"
        )

    evidence = _validate_inputs(
        authority_root=authority_root,
        parent_root=parent_root,
        created_at=created_at,
    )
    parent_tiles = evidence["parent_tiles"]
    parent_queries = evidence["parent_queries"]
    reserve_tile_ids = evidence["reserve_tile_ids"]
    selection_seed = evidence["selection_seed_sha256"]
    calibration_ids, retest_ids = _select_membership(
        parent_queries,
        reserve_tile_ids=reserve_tile_ids,
        selection_seed=selection_seed,
    )
    role_tiles, role_queries = _assign_calibration_roles(
        parent_tiles,
        parent_queries,
        reserve_tile_ids=reserve_tile_ids,
    )
    by_query_id = role_queries.set_index("query_region_id", drop=False)
    calibration = by_query_id.loc[list(calibration_ids)].reset_index(drop=True)
    retest = by_query_id.loc[list(retest_ids)].reset_index(drop=True)

    parent_existed = output.parent.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    )
    try:
        _copy_authority_package(
            authority_root, temporary / Path(AUTHORITY_BINDING_PATH.as_posix())
        )
        _copy_canonical_release(
            parent_root, temporary / Path(PARENT_GRID_BINDING_PATH.as_posix())
        )
        _write_frame(temporary / CANONICAL_TILES_NAME, role_tiles)
        _write_frame(temporary / CANONICAL_QUERIES_NAME, role_queries)
        _write_frame(temporary / CALIBRATION_QUERIES_NAME, calibration)
        _write_frame(temporary / FRESH_RETEST_QUERIES_NAME, retest)
        (temporary / README_NAME).write_text(
            _readme_text(
                release_id=normalized_release_id,
                event_id=str(evidence["authority_manifest"]["event_id"]),
                reserve_tile_ids=reserve_tile_ids,
            ),
            encoding="utf-8",
            newline="\n",
        )

        role_counts = _role_counts(role_tiles, role_queries)
        receipt_payload: dict[str, Any] = {
            "artifact_schema": RECEIPT_SCHEMA,
            "builder": BUILDER_ID,
            "release_id": normalized_release_id,
            "created_at_utc": _format_utc(created_at),
            "status": RELEASE_STATUS,
            "event_id": evidence["authority_manifest"]["event_id"],
            "parent_canonical_grid_release": {
                **evidence["parent_release"],
                "package_path": PARENT_GRID_BINDING_PATH.as_posix(),
            },
            "authority_approval": _authority_binding(
                evidence["authority_manifest"],
                manifest_file_sha256=evidence["authority_manifest_file_sha256"],
            ),
            "approved_reserve": {
                "design_id": evidence["design_receipt"]["design_id"],
                "design_receipt_sha256": evidence["design_receipt"]["receipt_sha256"],
                "chosen_candidate_id": evidence["candidate"]["candidate_id"],
                "parent_tile_ids": list(reserve_tile_ids),
                "reserved_query_capacity": int(
                    evidence["candidate"]["reserved_query_capacity"]
                ),
                "assigned_dataset_role": CALIBRATION_ROLE,
                "whole_parent_tile_role_isolation": True,
            },
            "selection_contract": {
                "algorithm": SELECTION_ALGORITHM,
                "selection_seed_sha256": selection_seed,
                "calibration_query_count": CALIBRATION_QUERY_COUNT,
                "fresh_retest_query_count": FRESH_RETEST_QUERY_COUNT,
                "calibration_query_ids": list(calibration_ids),
                "fresh_retest_query_ids": list(retest_ids),
                "sets_are_disjoint": True,
                "membership_frozen": True,
                "uses_labels_or_model_signals": False,
            },
            "role_counts": role_counts,
            "authentication": {
                "receipt_method": (
                    "sha256_self_hash_plus_copied_authority_evidence_binding"
                ),
                "digital_signature_verified": False,
                "opaque_evidence_semantics_verified_by_software": False,
            },
            "safety": {
                "creates_or_changes_dataset_roles": True,
                "selects_calibration_query_ids": True,
                "selects_retest_query_ids": True,
                "calibration_query_membership_frozen": True,
                "fresh_retest_membership_frozen": True,
                **{field: False for field in _SAFETY_FALSE_FIELDS},
            },
            "artifacts": _artifact_records(temporary),
            "assumptions": (
                "The approved reserve is a static-context design, not flood truth. "
                "Membership is identity-hash ordered within approved parent tiles. "
                "Calibration and fresh-retest queries are permanently excluded from "
                "training, development, active selection, model evaluation, FPPS, "
                "warnings, and operational decision products."
            ),
            "evidence_limitation": _EVIDENCE_LIMITATION,
        }
        receipt = {
            **receipt_payload,
            "receipt_sha256": _canonical_sha256(receipt_payload),
        }
        _write_json(temporary / RECEIPT_NAME, receipt)

        manifest = _root_release_manifest(temporary)
        _write_frame(temporary / RELEASE_MANIFEST_NAME, manifest)
        seal_payload: dict[str, Any] = {
            "artifact_schema": CANONICAL_RELEASE_SCHEMA,
            "builder": BUILDER_ID,
            "release_kind": "reviewer_calibration_role_and_membership_release",
            "release_id": normalized_release_id,
            "sealed_at_utc": _format_utc(created_at),
            "release_manifest_sha256": _file_sha256(temporary / RELEASE_MANIFEST_NAME),
            "calibration_release_receipt_sha256": receipt["receipt_sha256"],
            "calibration_release_receipt_file_sha256": _file_sha256(
                temporary / RECEIPT_NAME
            ),
            "parent_release_id": evidence["parent_release"]["release_id"],
            "authority_approval_manifest_sha256": evidence["authority_manifest"][
                "manifest_sha256"
            ],
            "tile_count": len(role_tiles),
            "query_count": len(role_queries),
            "reviewer_calibration_tile_count": len(reserve_tile_ids),
            "reviewer_calibration_query_capacity": role_counts[
                "reviewer_calibration_queries"
            ],
            "calibration_query_count": CALIBRATION_QUERY_COUNT,
            "fresh_retest_query_count": FRESH_RETEST_QUERY_COUNT,
            "overall_training_ready": False,
            "review_bundle_authorized": False,
            "calibration_execution_authorized": False,
            "formal_review_authorized": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        }
        seal = {**seal_payload, "seal_sha256": _canonical_sha256(seal_payload)}
        _write_json(temporary / RELEASE_SEAL_NAME, seal)

        validate_calibration_release_package(temporary)
        try:
            temporary.rename(output)
        except FileExistsError as exc:
            raise CalibrationReleaseError(
                f"Output directory is immutable and already exists: {output}"
            ) from exc
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if not parent_existed:
            try:
                output.parent.rmdir()
            except OSError:
                pass
        raise

    return _paths(output)


def load_calibration_release_receipt(path: str | Path) -> dict[str, Any]:
    """Load and verify one self-hashed calibration-release receipt."""

    receipt = _load_json(_required_file(Path(path), "calibration release receipt"))
    _validate_receipt_shape(receipt)
    return receipt


def validate_calibration_release_package(
    package_directory: str | Path,
) -> dict[str, Any]:
    """Revalidate copied authority/parent bytes, roles, and 12/12 membership."""

    root = _required_directory(Path(package_directory), "calibration release package")
    receipt = load_calibration_release_receipt(root / RECEIPT_NAME)
    _validate_artifact_inventory(root, receipt["artifacts"])

    authority_root = _resolve_below(
        root,
        _safe_relative_path(
            receipt["authority_approval"]["package_path"],
            "authority_approval.package_path",
        ),
        "copied authority package",
    )
    parent_root = _resolve_below(
        root,
        _safe_relative_path(
            receipt["parent_canonical_grid_release"]["package_path"],
            "parent_canonical_grid_release.package_path",
        ),
        "copied parent canonical grid",
    )
    created_at = _strict_utc(receipt["created_at_utc"], "created_at_utc")
    evidence = _validate_inputs(
        authority_root=authority_root,
        parent_root=parent_root,
        created_at=created_at,
    )

    if receipt["event_id"] != evidence["authority_manifest"]["event_id"]:
        raise CalibrationReleaseError("Release event differs from authority approval.")
    expected_parent = {
        **evidence["parent_release"],
        "package_path": PARENT_GRID_BINDING_PATH.as_posix(),
    }
    if receipt["parent_canonical_grid_release"] != expected_parent:
        raise CalibrationReleaseError("Parent canonical release binding differs.")
    if receipt["authority_approval"] != _authority_binding(
        evidence["authority_manifest"],
        manifest_file_sha256=evidence["authority_manifest_file_sha256"],
    ):
        raise CalibrationReleaseError("Reference Authority binding differs.")

    role_tiles = _read_csv(root / CANONICAL_TILES_NAME, "role-assigned tiles")
    role_queries = _read_csv(
        root / CANONICAL_QUERIES_NAME, "role-assigned query regions"
    )
    calibration = _read_csv(
        root / CALIBRATION_QUERIES_NAME, "calibration query membership"
    )
    retest = _read_csv(
        root / FRESH_RETEST_QUERIES_NAME, "fresh-retest query membership"
    )
    _validate_role_outputs(
        parent_tiles=evidence["parent_tiles"],
        parent_queries=evidence["parent_queries"],
        role_tiles=role_tiles,
        role_queries=role_queries,
        calibration=calibration,
        retest=retest,
        reserve_tile_ids=evidence["reserve_tile_ids"],
        selection_seed=evidence["selection_seed_sha256"],
    )

    expected_calibration_ids, expected_retest_ids = _select_membership(
        evidence["parent_queries"],
        reserve_tile_ids=evidence["reserve_tile_ids"],
        selection_seed=evidence["selection_seed_sha256"],
    )
    selection = receipt["selection_contract"]
    expected_selection = {
        "algorithm": SELECTION_ALGORITHM,
        "selection_seed_sha256": evidence["selection_seed_sha256"],
        "calibration_query_count": CALIBRATION_QUERY_COUNT,
        "fresh_retest_query_count": FRESH_RETEST_QUERY_COUNT,
        "calibration_query_ids": list(expected_calibration_ids),
        "fresh_retest_query_ids": list(expected_retest_ids),
        "sets_are_disjoint": True,
        "membership_frozen": True,
        "uses_labels_or_model_signals": False,
    }
    if selection != expected_selection:
        raise CalibrationReleaseError(
            "Calibration/retest membership differs from deterministic approved selection."
        )
    expected_reserve = {
        "design_id": evidence["design_receipt"]["design_id"],
        "design_receipt_sha256": evidence["design_receipt"]["receipt_sha256"],
        "chosen_candidate_id": evidence["candidate"]["candidate_id"],
        "parent_tile_ids": list(evidence["reserve_tile_ids"]),
        "reserved_query_capacity": int(
            evidence["candidate"]["reserved_query_capacity"]
        ),
        "assigned_dataset_role": CALIBRATION_ROLE,
        "whole_parent_tile_role_isolation": True,
    }
    if receipt["approved_reserve"] != expected_reserve:
        raise CalibrationReleaseError("Approved reserve binding differs.")
    if receipt["role_counts"] != _role_counts(role_tiles, role_queries):
        raise CalibrationReleaseError("Release role counts differ from its grid.")

    _validate_release_manifest_and_seal(root, receipt)
    return receipt


def _validate_inputs(
    *, authority_root: Path, parent_root: Path, created_at: datetime
) -> dict[str, Any]:
    try:
        authority = validate_reference_authority_approval_package(authority_root)
    except (ReferenceAuthorityApprovalError, OSError) as exc:
        raise CalibrationReleaseError(
            f"Reference Authority approval package is invalid: {exc}"
        ) from exc
    if authority.get("approval_status") != APPROVED_STATUS:
        raise CalibrationReleaseError(
            "Reference Authority package is not approved for next construction."
        )
    scope = authority.get("authorization_scope")
    if (
        not isinstance(scope, Mapping)
        or scope.get("may_start_separate_canonical_reserve_construction") is not True
    ):
        raise CalibrationReleaseError(
            "Reference Authority package does not authorize canonical reserve construction."
        )
    if any(
        scope.get(field) is not False
        for field in (
            "calibration_query_selection",
            "calibration_execution",
            "review_bundle_construction",
            "formal_review",
        )
    ):
        raise CalibrationReleaseError(
            "Authority package exceeds the bounded next-construction scope."
        )

    approval_created = _strict_utc(
        authority["created_at_utc"], "approval.created_at_utc"
    )
    if created_at < approval_created:
        raise CalibrationReleaseError(
            "Calibration release cannot predate the authority approval package."
        )
    try:
        parent_release = _verify_canonical_grid_release(parent_root)
        parent_tiles = _read_csv(parent_root / CANONICAL_TILES_NAME, "parent tiles")
        parent_queries = _read_csv(
            parent_root / CANONICAL_QUERIES_NAME, "parent query regions"
        )
        _validate_canonical_pool(parent_tiles, parent_queries)
    except (CalibrationReserveError, OSError) as exc:
        raise CalibrationReleaseError(
            f"Parent canonical grid release is invalid: {exc}"
        ) from exc
    sealed_at = _strict_utc(parent_release["sealed_at_utc"], "parent.sealed_at_utc")
    if created_at < sealed_at:
        raise CalibrationReleaseError(
            "Calibration release cannot predate the parent canonical grid."
        )

    design_binding = authority.get("reserve_design_binding")
    if not isinstance(design_binding, Mapping):
        raise CalibrationReleaseError("Authority package has no reserve binding.")
    design_root = _resolve_below(
        authority_root,
        _safe_relative_path(design_binding.get("package_path"), "design.package_path"),
        "bound reserve design",
    )
    try:
        design_receipt = verify_calibration_reserve_design_package(design_root)
    except (CalibrationReserveError, OSError) as exc:
        raise CalibrationReleaseError(
            f"Bound reserve design is invalid: {exc}"
        ) from exc
    if design_receipt.get("parent_canonical_grid_release") != parent_release:
        raise CalibrationReleaseError(
            "Current canonical grid is a substitution for the authority-bound parent release."
        )
    planning = design_receipt.get("planning_parameters")
    if not isinstance(planning, Mapping):
        raise CalibrationReleaseError("Reserve design has no planning parameters.")
    if (
        _integer(planning.get("calibration_query_count"), "calibration_query_count")
        != CALIBRATION_QUERY_COUNT
    ):
        raise CalibrationReleaseError(
            "Approved design must require exactly 12 calibration queries."
        )
    if (
        _integer(
            planning.get("fresh_retest_query_count"),
            "fresh_retest_query_count",
        )
        != FRESH_RETEST_QUERY_COUNT
    ):
        raise CalibrationReleaseError(
            "Approved design must require exactly 12 fresh-retest queries."
        )

    candidate = _find_candidate(
        design_root, str(design_binding.get("chosen_candidate_id", ""))
    )
    reserve_tile_ids = _parse_tile_ids(candidate.get("tile_ids"))
    all_tile_ids = set(parent_tiles["tile_id"].astype(str))
    if not set(reserve_tile_ids) <= all_tile_ids:
        raise CalibrationReleaseError(
            "Approved reserve references unknown parent tiles."
        )
    reserve_queries = parent_queries.loc[
        parent_queries["tile_id"].astype(str).isin(reserve_tile_ids)
    ]
    actual_capacity = len(reserve_queries)
    declared_capacity = _integer(
        candidate.get("reserved_query_capacity"), "reserved_query_capacity"
    )
    if actual_capacity != declared_capacity:
        raise CalibrationReleaseError(
            "Approved reserve capacity differs from the current parent grid."
        )
    if actual_capacity < CALIBRATION_QUERY_COUNT + FRESH_RETEST_QUERY_COUNT:
        raise CalibrationReleaseError(
            "Approved reserve lacks capacity for disjoint 12-query calibration and retest sets."
        )
    if set(parent_tiles["event_id"].astype(str)) != {authority["event_id"]} or set(
        parent_queries["event_id"].astype(str)
    ) != {authority["event_id"]}:
        raise CalibrationReleaseError(
            "Parent grid event membership differs from the authority approval."
        )
    selection_seed = _canonical_sha256(
        {
            "algorithm": SELECTION_ALGORITHM,
            "authority_manifest_sha256": authority["manifest_sha256"],
            "parent_release_id": parent_release["release_id"],
            "parent_tiles_sha256": parent_release["canonical_tiles_sha256"],
            "parent_queries_sha256": parent_release["canonical_query_regions_sha256"],
            "design_receipt_sha256": design_receipt["receipt_sha256"],
            "candidate_id": candidate["candidate_id"],
            "reserve_tile_ids": list(reserve_tile_ids),
            "calibration_query_count": CALIBRATION_QUERY_COUNT,
            "fresh_retest_query_count": FRESH_RETEST_QUERY_COUNT,
        }
    )
    return {
        "authority_manifest": authority,
        "authority_manifest_file_sha256": _file_sha256(
            authority_root / AUTHORITY_MANIFEST_NAME
        ),
        "parent_release": parent_release,
        "parent_tiles": parent_tiles,
        "parent_queries": parent_queries,
        "design_receipt": design_receipt,
        "candidate": candidate,
        "reserve_tile_ids": reserve_tile_ids,
        "selection_seed_sha256": selection_seed,
    }


def _select_membership(
    queries: pd.DataFrame,
    *,
    reserve_tile_ids: tuple[str, ...],
    selection_seed: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    reserved = queries.loc[queries["tile_id"].astype(str).isin(reserve_tile_ids)]
    if reserved["query_region_id"].astype(str).duplicated().any():
        raise CalibrationReleaseError("Reserved queries contain duplicate identifiers.")
    calibration = _round_robin_ids(
        reserved,
        tile_ids=reserve_tile_ids,
        count=CALIBRATION_QUERY_COUNT,
        seed=selection_seed,
        purpose="initial_calibration",
        excluded=frozenset(),
    )
    retest = _round_robin_ids(
        reserved,
        tile_ids=reserve_tile_ids,
        count=FRESH_RETEST_QUERY_COUNT,
        seed=selection_seed,
        purpose="fresh_retest",
        excluded=frozenset(calibration),
    )
    if set(calibration) & set(retest):
        raise CalibrationReleaseError(
            "Calibration and fresh-retest membership overlaps."
        )
    return calibration, retest


def _round_robin_ids(
    rows: pd.DataFrame,
    *,
    tile_ids: tuple[str, ...],
    count: int,
    seed: str,
    purpose: str,
    excluded: frozenset[str],
) -> tuple[str, ...]:
    tile_order = sorted(
        tile_ids,
        key=lambda tile_id: (_selection_hash(seed, purpose, "tile", tile_id), tile_id),
    )
    queues: dict[str, list[str]] = {}
    for tile_id in tile_order:
        ids = [
            query_id
            for query_id in rows.loc[
                rows["tile_id"].astype(str).eq(tile_id), "query_region_id"
            ].astype(str)
            if query_id not in excluded
        ]
        queues[tile_id] = sorted(
            ids,
            key=lambda query_id: (
                _selection_hash(seed, purpose, "query", query_id),
                query_id,
            ),
        )
    selected: list[str] = []
    while len(selected) < count:
        progressed = False
        for tile_id in tile_order:
            if queues[tile_id] and len(selected) < count:
                selected.append(queues[tile_id].pop(0))
                progressed = True
        if not progressed:
            raise CalibrationReleaseError(
                f"Approved reserve cannot supply {count} disjoint {purpose} queries."
            )
    return tuple(selected)


def _selection_hash(seed: str, purpose: str, kind: str, value: str) -> str:
    return hashlib.sha256(
        f"{SELECTION_ALGORITHM}|{seed}|{purpose}|{kind}|{value}".encode("utf-8")
    ).hexdigest()


def _assign_calibration_roles(
    tiles: pd.DataFrame,
    queries: pd.DataFrame,
    *,
    reserve_tile_ids: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    role_tiles = tiles.copy()
    role_queries = queries.copy()
    tile_mask = role_tiles["tile_id"].astype(str).isin(reserve_tile_ids)
    query_mask = role_queries["tile_id"].astype(str).isin(reserve_tile_ids)
    role_tiles.loc[tile_mask, "dataset_role"] = CALIBRATION_ROLE
    role_tiles.loc[tile_mask, "eligible_for_active_selection"] = False
    role_tiles.loc[tile_mask, "eligible_for_review_queue"] = False
    role_queries.loc[query_mask, "dataset_role"] = CALIBRATION_ROLE
    role_queries.loc[query_mask, "eligible_for_active_selection"] = False
    role_queries.loc[query_mask, "eligible_for_review_queue"] = False
    role_queries.loc[query_mask, "eligible_for_training_after_human_review"] = "no"
    return role_tiles, role_queries


def _validate_role_outputs(
    *,
    parent_tiles: pd.DataFrame,
    parent_queries: pd.DataFrame,
    role_tiles: pd.DataFrame,
    role_queries: pd.DataFrame,
    calibration: pd.DataFrame,
    retest: pd.DataFrame,
    reserve_tile_ids: tuple[str, ...],
    selection_seed: str,
) -> None:
    if list(role_tiles.columns) != list(parent_tiles.columns) or list(
        role_queries.columns
    ) != list(parent_queries.columns):
        raise CalibrationReleaseError(
            "Role-assigned grid columns differ from the parent canonical grid."
        )
    _validate_derived_frame(
        parent_tiles,
        role_tiles,
        id_column="tile_id",
        mutable_fields=_MUTABLE_TILE_FIELDS,
    )
    _validate_derived_frame(
        parent_queries,
        role_queries,
        id_column="query_region_id",
        mutable_fields=_MUTABLE_QUERY_FIELDS,
    )
    reserve = set(reserve_tile_ids)
    tile_reserved = role_tiles["tile_id"].astype(str).isin(reserve)
    query_reserved = role_queries["tile_id"].astype(str).isin(reserve)
    if set(role_tiles.loc[tile_reserved, "dataset_role"].astype(str)) != {
        CALIBRATION_ROLE
    } or set(role_queries.loc[query_reserved, "dataset_role"].astype(str)) != {
        CALIBRATION_ROLE
    }:
        raise CalibrationReleaseError(
            "Every approved parent tile and child query must be reviewer_calibration."
        )
    if set(role_tiles.loc[~tile_reserved, "dataset_role"].astype(str)) != {
        TRAINING_ROLE
    } or set(role_queries.loc[~query_reserved, "dataset_role"].astype(str)) != {
        TRAINING_ROLE
    }:
        raise CalibrationReleaseError(
            "Non-reserve parent tiles must remain only in the training/query pool."
        )
    if set(role_tiles["dataset_role"].astype(str)) - {
        TRAINING_ROLE,
        CALIBRATION_ROLE,
    } or set(role_queries["dataset_role"].astype(str)) - {
        TRAINING_ROLE,
        CALIBRATION_ROLE,
    }:
        raise CalibrationReleaseError(
            "Calibration release contains a formal/final/evaluation role."
        )
    for frame, mask, label in (
        (role_tiles, tile_reserved, "reserved tiles"),
        (role_queries, query_reserved, "reserved queries"),
    ):
        _require_boolean_subset(
            frame, mask, "eligible_for_human_annotation", True, label
        )
        _require_boolean_subset(
            frame, mask, "eligible_for_active_selection", False, label
        )
        _require_boolean_subset(frame, mask, "eligible_for_review_queue", False, label)
        _require_boolean_subset(
            frame, mask, "eligible_for_query_model_training", False, label
        )
        for field in (
            "eligible_for_decision_layer",
            "eligible_for_fpps",
            "eligible_for_warning",
        ):
            _require_boolean_subset(frame, mask, field, False, label)
    if set(
        role_queries.loc[
            query_reserved, "eligible_for_training_after_human_review"
        ].astype(str)
    ) != {"no"}:
        raise CalibrationReleaseError(
            "Reviewer-calibration queries must remain permanently training-ineligible."
        )
    _require_boolean_subset(
        role_queries, query_reserved, "selected", False, "reserved queries"
    )
    if set(role_queries.loc[query_reserved, "review_status"].astype(str)) != {
        "unreviewed"
    }:
        raise CalibrationReleaseError("Reserved queries must remain unreviewed.")

    expected_calibration, expected_retest = _select_membership(
        parent_queries,
        reserve_tile_ids=reserve_tile_ids,
        selection_seed=selection_seed,
    )
    _validate_membership_frame(
        calibration,
        canonical=role_queries,
        expected_ids=expected_calibration,
        label="calibration",
    )
    _validate_membership_frame(
        retest,
        canonical=role_queries,
        expected_ids=expected_retest,
        label="fresh-retest",
    )
    if set(expected_calibration) & set(expected_retest):
        raise CalibrationReleaseError("Calibration and fresh-retest sets overlap.")


def _validate_derived_frame(
    parent: pd.DataFrame,
    derived: pd.DataFrame,
    *,
    id_column: str,
    mutable_fields: frozenset[str],
) -> None:
    if len(parent) != len(derived):
        raise CalibrationReleaseError(f"Derived {id_column} row count differs.")
    if list(parent[id_column].astype(str)) != list(derived[id_column].astype(str)):
        raise CalibrationReleaseError(
            f"Derived {id_column} order/membership differs from the parent release."
        )
    for column in parent.columns:
        if column in mutable_fields:
            continue
        for parent_value, derived_value in zip(
            parent[column], derived[column], strict=True
        ):
            if not _scalar_equal(parent_value, derived_value):
                raise CalibrationReleaseError(
                    f"Role release changed non-role field {column!r}."
                )


def _validate_membership_frame(
    frame: pd.DataFrame,
    *,
    canonical: pd.DataFrame,
    expected_ids: tuple[str, ...],
    label: str,
) -> None:
    if list(frame.columns) != list(canonical.columns):
        raise CalibrationReleaseError(
            f"{label} membership columns differ from canonical queries."
        )
    observed = list(frame["query_region_id"].astype(str))
    if len(observed) != len(set(observed)):
        raise CalibrationReleaseError(
            f"{label} membership contains duplicate query ids."
        )
    if observed != list(expected_ids):
        raise CalibrationReleaseError(
            f"{label} membership differs from deterministic approved selection."
        )
    canonical_by_id = canonical.set_index("query_region_id", drop=False)
    for row in frame.to_dict("records"):
        query_id = str(row["query_region_id"])
        if query_id not in canonical_by_id.index:
            raise CalibrationReleaseError(
                f"{label} query {query_id!r} is not canonical."
            )
        source = canonical_by_id.loc[query_id]
        for column in canonical.columns:
            if not _scalar_equal(row[column], source[column]):
                raise CalibrationReleaseError(
                    f"{label} query {query_id!r} differs in {column}."
                )
        if str(row["dataset_role"]) != CALIBRATION_ROLE:
            raise CalibrationReleaseError(
                f"{label} query {query_id!r} is not reviewer_calibration."
            )


def _validate_receipt_shape(receipt: Mapping[str, Any]) -> None:
    if set(receipt) != set(_RECEIPT_KEYS):
        raise CalibrationReleaseError("Calibration release receipt keys differ.")
    if receipt.get("artifact_schema") != RECEIPT_SCHEMA:
        raise CalibrationReleaseError("Unknown calibration release receipt schema.")
    if receipt.get("builder") != BUILDER_ID:
        raise CalibrationReleaseError("Unknown calibration release builder.")
    if receipt.get("status") != RELEASE_STATUS:
        raise CalibrationReleaseError("Calibration release has an invalid status.")
    declared = _required_sha(receipt.get("receipt_sha256"), "receipt_sha256")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256", None)
    if _canonical_sha256(unsigned) != declared:
        raise CalibrationReleaseError("Calibration release receipt self-hash mismatch.")
    _identifier(receipt.get("release_id"), "release_id")
    _strict_utc(receipt.get("created_at_utc"), "created_at_utc")
    if receipt.get("evidence_limitation") != _EVIDENCE_LIMITATION:
        raise CalibrationReleaseError(
            "Calibration release lost its evidence limitation."
        )
    safety = receipt.get("safety")
    expected_keys = set(_SAFETY_FALSE_FIELDS) | {
        "creates_or_changes_dataset_roles",
        "selects_calibration_query_ids",
        "selects_retest_query_ids",
        "calibration_query_membership_frozen",
        "fresh_retest_membership_frozen",
    }
    if not isinstance(safety, Mapping) or set(safety) != expected_keys:
        raise CalibrationReleaseError(
            "Calibration release safety fields are incomplete."
        )
    if any(safety.get(field) is not False for field in _SAFETY_FALSE_FIELDS):
        raise CalibrationReleaseError(
            "Calibration release has an unsafe enabled capability."
        )
    for field in expected_keys - set(_SAFETY_FALSE_FIELDS):
        if safety.get(field) is not True:
            raise CalibrationReleaseError(
                "Calibration membership/role freeze is not explicit."
            )
    authentication = receipt.get("authentication")
    if authentication != {
        "receipt_method": "sha256_self_hash_plus_copied_authority_evidence_binding",
        "digital_signature_verified": False,
        "opaque_evidence_semantics_verified_by_software": False,
    }:
        raise CalibrationReleaseError(
            "Calibration release authentication is overstated."
        )
    _required_text(receipt.get("assumptions"), "assumptions")


def _validate_release_manifest_and_seal(root: Path, receipt: Mapping[str, Any]) -> None:
    manifest_path = _required_file(root / RELEASE_MANIFEST_NAME, "release manifest")
    manifest = _read_csv(manifest_path, "release manifest")
    required_columns = {
        "file_name",
        "file_size_bytes",
        "sha256",
        "artifact_role",
        "immutable_status",
    }
    if set(manifest.columns) != required_columns:
        raise CalibrationReleaseError("Release manifest columns differ.")
    if list(manifest["file_name"].astype(str)) != list(_ROOT_RELEASE_ARTIFACTS):
        raise CalibrationReleaseError(
            "Release manifest artifact membership/order differs."
        )
    for row in manifest.to_dict("records"):
        name = _safe_base_name(row["file_name"], "release file_name")
        path = _required_file(root / name, f"release artifact {name}")
        if path.is_symlink():
            raise CalibrationReleaseError("Release artifacts cannot be symbolic links.")
        if _integer(row["file_size_bytes"], "file_size_bytes") != path.stat().st_size:
            raise CalibrationReleaseError(f"Release artifact size mismatch: {name}")
        if _required_sha(row["sha256"], "sha256") != _file_sha256(path):
            raise CalibrationReleaseError(f"Release artifact checksum mismatch: {name}")
        if not str(row["immutable_status"]).startswith("frozen_"):
            raise CalibrationReleaseError(f"Release artifact is not frozen: {name}")

    seal = _load_json(_required_file(root / RELEASE_SEAL_NAME, "release seal"))
    declared = _required_sha(seal.get("seal_sha256"), "seal_sha256")
    unsigned = dict(seal)
    unsigned.pop("seal_sha256", None)
    if _canonical_sha256(unsigned) != declared:
        raise CalibrationReleaseError("Calibration release seal self-hash mismatch.")
    expected = {
        "artifact_schema": CANONICAL_RELEASE_SCHEMA,
        "builder": BUILDER_ID,
        "release_kind": "reviewer_calibration_role_and_membership_release",
        "release_id": receipt["release_id"],
        "sealed_at_utc": receipt["created_at_utc"],
        "release_manifest_sha256": _file_sha256(manifest_path),
        "calibration_release_receipt_sha256": receipt["receipt_sha256"],
        "calibration_release_receipt_file_sha256": _file_sha256(root / RECEIPT_NAME),
        "parent_release_id": receipt["parent_canonical_grid_release"]["release_id"],
        "authority_approval_manifest_sha256": receipt["authority_approval"][
            "manifest_sha256"
        ],
        "tile_count": receipt["role_counts"]["total_tiles"],
        "query_count": receipt["role_counts"]["total_queries"],
        "reviewer_calibration_tile_count": receipt["role_counts"][
            "reviewer_calibration_tiles"
        ],
        "reviewer_calibration_query_capacity": receipt["role_counts"][
            "reviewer_calibration_queries"
        ],
        "calibration_query_count": CALIBRATION_QUERY_COUNT,
        "fresh_retest_query_count": FRESH_RETEST_QUERY_COUNT,
        "overall_training_ready": False,
        "review_bundle_authorized": False,
        "calibration_execution_authorized": False,
        "formal_review_authorized": False,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    if unsigned != expected:
        raise CalibrationReleaseError("Calibration release seal contract differs.")


def _authority_binding(
    authority: Mapping[str, Any], *, manifest_file_sha256: str
) -> dict[str, Any]:
    return {
        "package_id": authority["package_id"],
        "approval_status": authority["approval_status"],
        "manifest_sha256": authority["manifest_sha256"],
        "manifest_file_sha256": _required_sha(
            manifest_file_sha256, "authority manifest file SHA-256"
        ),
        "reference_authority_role_id": authority["reference_authority"]["role_id"],
        "reference_authority_person_id": authority["reference_authority"]["person_id"],
        "decision_evidence_id": authority["decision_evidence"]["evidence_id"],
        "decision_evidence_file_sha256": authority["decision_evidence"]["file_sha256"],
        "evidence_verification_status": authority["decision_evidence"][
            "verification_status"
        ],
        "semantic_verification_status": authority["decision_evidence"][
            "semantic_verification_status"
        ],
        "reference_procedure_version": authority["reference_procedure_binding"][
            "document_version"
        ],
        "reference_procedure_file_sha256": authority["reference_procedure_binding"][
            "file_sha256"
        ],
        "package_path": AUTHORITY_BINDING_PATH.as_posix(),
    }


def _find_candidate(design_root: Path, candidate_id: str) -> dict[str, str]:
    if not candidate_id:
        raise CalibrationReleaseError(
            "Authority package has no chosen reserve candidate."
        )
    frame = _read_csv(design_root / CANDIDATES_NAME, "reserve candidates")
    if "query_region_id" in frame.columns:
        raise CalibrationReleaseError("Reserve candidates expose prohibited query ids.")
    matches = frame.loc[frame["candidate_id"].astype(str).eq(candidate_id)]
    if len(matches) != 1:
        raise CalibrationReleaseError(
            "Chosen reserve candidate is absent or duplicated in the bound design."
        )
    return {key: str(value) for key, value in matches.iloc[0].to_dict().items()}


def _parse_tile_ids(value: Any) -> tuple[str, ...]:
    text = _required_text(value, "candidate tile_ids")
    values = tuple(text.split("|"))
    if any(not value or value != value.strip() for value in values):
        raise CalibrationReleaseError("Candidate tile_ids are not canonical.")
    if len(values) != len(set(values)) or len(values) < 2:
        raise CalibrationReleaseError(
            "Candidate must contain at least two unique parent tiles."
        )
    return tuple(sorted(values))


def _copy_authority_package(source: Path, target: Path) -> None:
    validate_reference_authority_approval_package(source)
    _copy_tree_files(source, target)
    validate_reference_authority_approval_package(target)


def _copy_canonical_release(source: Path, target: Path) -> None:
    _verify_canonical_grid_release(source)
    manifest = _read_csv(source / RELEASE_MANIFEST_NAME, "parent release manifest")
    names = [
        _safe_base_name(value, "parent release file_name")
        for value in manifest["file_name"].astype(str)
    ]
    for name in (*names, RELEASE_MANIFEST_NAME, RELEASE_SEAL_NAME):
        _copy_file(
            _required_file(source / name, f"parent release artifact {name}"),
            target / name,
        )
    _verify_canonical_grid_release(target)


def _copy_tree_files(source: Path, target: Path) -> None:
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise CalibrationReleaseError(
                f"Symbolic-link inputs are not allowed: {path}"
            )
        if path.is_file():
            _copy_file(path, target / path.relative_to(source))


def _copy_file(source: Path, target: Path) -> None:
    if source.is_symlink():
        raise CalibrationReleaseError(f"Symbolic-link inputs are not allowed: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _artifact_records(root: Path) -> list[dict[str, Any]]:
    excluded = {RECEIPT_NAME, RELEASE_MANIFEST_NAME, RELEASE_SEAL_NAME}
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise CalibrationReleaseError(
                f"Package cannot contain a symbolic link: {path}"
            )
        if not path.is_file() or path.parent == root and path.name in excluded:
            continue
        record: dict[str, Any] = {
            "package_path": path.relative_to(root).as_posix(),
            "file_size_bytes": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
        if path.suffix.lower() == ".csv":
            record["row_count"] = len(_read_csv(path, f"artifact {path.name}"))
        records.append(record)
    return records


def _validate_artifact_inventory(root: Path, value: Any) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CalibrationReleaseError("Artifact inventory must be an array.")
    expected_paths: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise CalibrationReleaseError("Artifact inventory records must be objects.")
        expected_keys = {"package_path", "file_size_bytes", "sha256"}
        relative = _safe_relative_path(
            item.get("package_path"), "artifact package_path"
        )
        path = _required_file(_resolve_below(root, relative, "artifact"), "artifact")
        if path.suffix.lower() == ".csv":
            expected_keys.add("row_count")
        if set(item) != expected_keys:
            raise CalibrationReleaseError("Artifact inventory record keys differ.")
        if path.is_symlink():
            raise CalibrationReleaseError("Package artifacts cannot be symbolic links.")
        if (
            _integer(item.get("file_size_bytes"), "file_size_bytes")
            != path.stat().st_size
        ):
            raise CalibrationReleaseError(
                f"Artifact size mismatch: {relative.as_posix()}"
            )
        if _required_sha(item.get("sha256"), "artifact sha256") != _file_sha256(path):
            raise CalibrationReleaseError(
                f"Artifact checksum mismatch: {relative.as_posix()}"
            )
        if "row_count" in item and _integer(item["row_count"], "row_count") != len(
            _read_csv(path, f"artifact {path.name}")
        ):
            raise CalibrationReleaseError(
                f"Artifact row count mismatch: {relative.as_posix()}"
            )
        expected_paths.append(relative.as_posix())
    if expected_paths != sorted(set(expected_paths)):
        raise CalibrationReleaseError("Artifact inventory is duplicated or unsorted.")
    excluded = {RECEIPT_NAME, RELEASE_MANIFEST_NAME, RELEASE_SEAL_NAME}
    actual_paths: list[str] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CalibrationReleaseError("Package cannot contain symbolic links.")
        if path.is_file() and not (path.parent == root and path.name in excluded):
            actual_paths.append(path.relative_to(root).as_posix())
    if sorted(actual_paths) != expected_paths:
        raise CalibrationReleaseError(
            "Artifact inventory does not exactly cover package files."
        )


def _root_release_manifest(root: Path) -> pd.DataFrame:
    roles = {
        CANONICAL_TILES_NAME: "role_assigned_canonical_tiles",
        CANONICAL_QUERIES_NAME: "role_assigned_canonical_queries",
        CALIBRATION_QUERIES_NAME: "initial_calibration_membership",
        FRESH_RETEST_QUERIES_NAME: "fresh_retest_membership",
        README_NAME: "safety_readme",
        RECEIPT_NAME: "calibration_release_receipt",
    }
    return pd.DataFrame(
        [
            {
                "file_name": name,
                "file_size_bytes": (root / name).stat().st_size,
                "sha256": _file_sha256(root / name),
                "artifact_role": roles[name],
                "immutable_status": "frozen_calibration_release",
            }
            for name in _ROOT_RELEASE_ARTIFACTS
        ]
    )


def _role_counts(tiles: pd.DataFrame, queries: pd.DataFrame) -> dict[str, int]:
    tile_roles = tiles["dataset_role"].astype(str)
    query_roles = queries["dataset_role"].astype(str)
    return {
        "total_tiles": len(tiles),
        "total_queries": len(queries),
        "reviewer_calibration_tiles": int(tile_roles.eq(CALIBRATION_ROLE).sum()),
        "reviewer_calibration_queries": int(query_roles.eq(CALIBRATION_ROLE).sum()),
        "training_and_query_pool_tiles": int(tile_roles.eq(TRAINING_ROLE).sum()),
        "training_and_query_pool_queries": int(query_roles.eq(TRAINING_ROLE).sum()),
    }


def _readme_text(
    *, release_id: str, event_id: str, reserve_tile_ids: tuple[str, ...]
) -> str:
    tiles = ", ".join(f"`{tile_id}`" for tile_id in reserve_tile_ids)
    return f"""# Reviewer-calibration role and membership release

- Release: `{release_id}`
- Event: `{event_id}`
- Approved parent tiles: {tiles}

This immutable package assigns every query in the approved parent tiles to
`reviewer_calibration`. It freezes exactly 12 initial calibration queries and
12 disjoint fresh-retest queries using a model-free identity-hash algorithm.

It does **not** create a reference, reveal an answer, authorize reviewer
delivery or calibration execution, open formal review, train/evaluate a model,
feed the decision layer or FPPS, or issue a warning. The copied authority
package carries declared-attribution evidence, not software-verified identity,
expertise, semantics, or a verified digital signature.
"""


def _paths(root: Path) -> CalibrationReleasePaths:
    return CalibrationReleasePaths(
        directory=root,
        canonical_tiles=root / CANONICAL_TILES_NAME,
        canonical_query_regions=root / CANONICAL_QUERIES_NAME,
        calibration_queries=root / CALIBRATION_QUERIES_NAME,
        fresh_retest_queries=root / FRESH_RETEST_QUERIES_NAME,
        receipt=root / RECEIPT_NAME,
        release_manifest=root / RELEASE_MANIFEST_NAME,
        release_seal=root / RELEASE_SEAL_NAME,
    )


def _required_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise CalibrationReleaseError(f"{label} does not exist or is unsafe: {path}")
    return path


def _required_file(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CalibrationReleaseError(f"{label} does not exist or is unsafe: {path}")
    return path


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    _required_file(path, label)
    try:
        return pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeError) as exc:
        raise CalibrationReleaseError(f"Could not read {label}: {exc}") from exc


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _load_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CalibrationReleaseError(
                    f"JSON artifact contains duplicate key: {key}."
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationReleaseError(f"Could not read JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise CalibrationReleaseError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _created_at(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CalibrationReleaseError("created_at_utc must be timezone-aware.")
        return value.astimezone(timezone.utc).replace(microsecond=0)
    return _strict_utc(value, "created_at_utc")


def _strict_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise CalibrationReleaseError(
            f"{field} must use exact YYYY-MM-DDTHH:MM:SSZ UTC format."
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise CalibrationReleaseError(f"{field} is not a real UTC timestamp.") from exc


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _identifier(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if _ID_RE.fullmatch(text) is None:
        raise CalibrationReleaseError(f"{field} has an invalid format: {text!r}")
    return text


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CalibrationReleaseError(f"{field} must be a canonical non-blank string.")
    return value


def _required_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA_RE.fullmatch(value) is None:
        raise CalibrationReleaseError(f"{field} must be a lowercase SHA-256 digest.")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise CalibrationReleaseError(f"{field} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationReleaseError(f"{field} must be an integer.") from exc
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationReleaseError(f"{field} must be an integer.") from exc
    if not numeric.is_integer() or number < 0:
        raise CalibrationReleaseError(f"{field} must be a non-negative integer.")
    return number


def _safe_base_name(value: Any, field: str) -> str:
    text = _required_text(str(value), field)
    if Path(text).name != text or "/" in text or "\\" in text:
        raise CalibrationReleaseError(f"{field} must be a safe base name.")
    return text


def _safe_relative_path(value: Any, field: str) -> PurePosixPath:
    text = _required_text(value, field).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CalibrationReleaseError(f"{field} must be a safe relative path.")
    return path


def _resolve_below(root: Path, relative: PurePosixPath, label: str) -> Path:
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise CalibrationReleaseError(f"{label} escapes its package root.") from exc
    return candidate


def _require_boolean_subset(
    frame: pd.DataFrame,
    mask: pd.Series,
    column: str,
    expected: bool,
    label: str,
) -> None:
    if column not in frame.columns:
        raise CalibrationReleaseError(f"{label} omit required field {column}.")
    values = frame.loc[mask, column].map(lambda value: _strict_bool(value, column))
    if not values.map(lambda value: value is expected).all():
        raise CalibrationReleaseError(
            f"{label} require {column}={str(expected).lower()}."
        )


def _strict_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise CalibrationReleaseError(f"{field} must contain strict boolean values.")


def _scalar_equal(left: Any, right: Any) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return float(left) == float(right)
    return str(left) == str(right)
