"""File-backed preflight for qualified-label inputs to multi-event experiments.

The current qualified-label release and partition contracts remain fixture-only.
This loader cannot turn a fixture or candidate into real training authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from floodguard.label_factory.qualified_label_release import (
    QualifiedLabelReleaseError,
    validate_qualified_label_release,
)
from floodguard.label_factory.qualified_reference_release import (
    QualifiedReferenceReleaseError,
    load_qualified_reference_release,
)


class MultiEventPreflightError(ValueError):
    """Raised when a file-backed label/source chain cannot be revalidated."""


@dataclass(frozen=True)
class QualifiedReleaseFiles:
    """Exact frozen files for one purpose-specific qualified-label release."""

    release_json: Path
    formal_review_json: Path
    human_role_package: Path
    reviewer_calibration: Path
    labelset_manifest: Path
    labelset_validation: Path
    review_pair_json: tuple[Path, ...]
    qualified_reference_json: Path
    reference_raster: Path
    analysis_grid: Path
    acquisition_source_by_role: dict[str, Path] = field(default_factory=dict)


def revalidate_qualified_release_files(files: QualifiedReleaseFiles) -> dict[str, Any]:
    """Reopen exact files and invoke the canonical purpose/lineage validator.

    Candidate/official inputs are still rejected by the upstream release
    contract until its independently authorized authority validator exists.
    The returned receipt only describes this preflight, not model permission.
    """

    release, release_file_sha = _read_json(
        files.release_json, "qualified label release"
    )
    formal, formal_file_sha = _read_json(files.formal_review_json, "formal review")
    reference, reference_file_sha = _read_json(
        files.qualified_reference_json, "qualified reference release"
    )
    if not files.review_pair_json:
        raise MultiEventPreflightError("at least one review-pair file is required")
    pairs = []
    pair_file_hashes = {}
    for index, path in enumerate(files.review_pair_json):
        pair, file_sha = _read_json(path, f"review pair {index}")
        pairs.append(pair)
        pair_file_hashes[str(index)] = file_sha

    try:
        reference = load_qualified_reference_release(files.qualified_reference_json)
    except (QualifiedReferenceReleaseError, OSError) as error:
        raise MultiEventPreflightError(
            f"qualified reference failed its canonical validator: {error}"
        ) from error
    artifact = reference.get("reference_artifact")
    grid = reference.get("analysis_grid")
    if not isinstance(artifact, dict) or not isinstance(grid, dict):
        raise MultiEventPreflightError("qualified reference has no source raster/grid")
    reference_raster_sha = _hash_file(files.reference_raster, "reference raster")
    analysis_grid_sha = _hash_file(files.analysis_grid, "analysis grid")
    if reference_raster_sha != artifact["sha256"]:
        raise MultiEventPreflightError("reference raster source bytes changed")
    if analysis_grid_sha != grid["sha256"]:
        raise MultiEventPreflightError("analysis grid source bytes changed")
    if (
        files.reference_raster.name != artifact["file_name"]
        or files.analysis_grid.name != grid["file_name"]
    ):
        raise MultiEventPreflightError("reference source file names changed")

    lineage = reference["acquisition_lineage"]
    expected_source_hashes = lineage["sha256_by_role"]
    source_paths = files.acquisition_source_by_role
    required_source_roles = {
        role for role, digest in expected_source_hashes.items() if digest is not None
    }
    if set(source_paths) != required_source_roles:
        raise MultiEventPreflightError(
            "acquisition source files do not exactly cover the reference lineage"
        )
    actual_source_hashes = {}
    for role in sorted(required_source_roles):
        digest = _hash_file(source_paths[role], f"acquisition source {role}")
        if digest != expected_source_hashes[role]:
            raise MultiEventPreflightError(f"acquisition source {role} bytes changed")
        actual_source_hashes[role] = digest

    mode = release.get("dataset_mode")
    if mode == "fixture_demo":
        human, human_sha = _read_json(files.human_role_package, "human roles")
        calibration, calibration_sha = _read_json(
            files.reviewer_calibration, "reviewer calibration"
        )
        labelset, labelset_sha = _read_json(files.labelset_manifest, "labelset")
        validation, validation_sha = _read_json(
            files.labelset_validation, "labelset validation"
        )
    else:
        human = _checked_path(
            files.human_role_package, "human role package", directory=True
        )
        calibration = _checked_path(files.reviewer_calibration, "reviewer calibration")
        labelset = _checked_path(files.labelset_manifest, "labelset manifest")
        validation = _checked_path(files.labelset_validation, "labelset validation")
        human_sha = None
        calibration_sha = _hash_file(calibration, "reviewer calibration")
        labelset_sha = _hash_file(labelset, "labelset manifest")
        validation_sha = _hash_file(validation, "labelset validation")

    try:
        validated = validate_qualified_label_release(
            release,
            formal_review_authorization=formal,
            human_role_package=human,
            reviewer_calibration_receipt=calibration,
            labelset_manifest=labelset,
            labelset_validation_receipt=validation,
            review_pair_receipts=pairs,
            qualified_reference_release_receipt=files.qualified_reference_json,
        )
    except (QualifiedLabelReleaseError, OSError) as error:
        raise MultiEventPreflightError(
            f"qualified label release failed its canonical validator: {error}"
        ) from error

    # A successful v1 preflight is necessarily a non-authoritative fixture.
    if validated["dataset_mode"] != "fixture_demo":
        raise MultiEventPreflightError(
            "real multi-event release needs independent authority validation"
        )
    return {
        "schema_version": "floodguard.qualified_release_file_preflight.v1",
        "status": "validated_synthetic_fixture_only",
        "eligible_for_real_experiment": False,
        "eligible_for_downstream_decision": False,
        "release_id": validated["release_id"],
        "event_id": validated["event_id"],
        "purpose": validated["purpose"],
        "qualified_label_release_sha256": validated["release_sha256"],
        "qualified_reference_release_sha256": reference["release_sha256"],
        "reference_raster_sha256": reference_raster_sha,
        "analysis_grid_sha256": analysis_grid_sha,
        "acquisition_source_sha256_by_role": actual_source_hashes,
        "file_sha256_by_role": {
            "qualified_label_release": release_file_sha,
            "formal_review_authorization": formal_file_sha,
            "human_role_package": human_sha,
            "reviewer_calibration": calibration_sha,
            "labelset_manifest": labelset_sha,
            "labelset_validation": validation_sha,
            "qualified_reference_release": reference_file_sha,
            "review_pairs_by_index": pair_file_hashes,
        },
    }


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    source = _checked_path(path, label)
    before = source.stat()
    if before.st_size > 16 * 1024 * 1024:
        raise MultiEventPreflightError(f"{label} JSON exceeds 16 MiB")
    try:
        raw = source.read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError, UnicodeDecodeError) as error:
        raise MultiEventPreflightError(f"cannot read {label} JSON: {error}") from error
    if not isinstance(value, dict):
        raise MultiEventPreflightError(f"{label} JSON root must be an object")
    if _file_identity(source.stat()) != _file_identity(before):
        raise MultiEventPreflightError(f"{label} changed during read")
    return value, hashlib.sha256(raw).hexdigest()


def _hash_file(path: Path, label: str) -> str:
    source = _checked_path(path, label)
    before = source.stat()
    digest = hashlib.sha256()
    try:
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise MultiEventPreflightError(f"cannot read {label}: {error}") from error
    if _file_identity(source.stat()) != _file_identity(before):
        raise MultiEventPreflightError(f"{label} changed during hashing")
    return digest.hexdigest()


def _checked_path(path: Path, label: str, *, directory: bool = False) -> Path:
    source = Path(path)
    if any(part == ".." for part in source.parts):
        raise MultiEventPreflightError(f"{label} path contains parent traversal")
    current = source
    try:
        while True:
            if current.is_symlink():
                raise MultiEventPreflightError(f"{label} path contains a symlink")
            if current.parent == current:
                break
            current = current.parent
        metadata = source.stat()
    except OSError as error:
        raise MultiEventPreflightError(
            f"{label} path is unavailable: {error}"
        ) from error
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_kind(metadata.st_mode):
        raise MultiEventPreflightError(
            f"{label} must be a regular {'directory' if directory else 'file'}"
        )
    return source


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns
