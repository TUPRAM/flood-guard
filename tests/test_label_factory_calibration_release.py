from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from floodguard.label_factory.calibration_release import (
    CALIBRATION_QUERY_COUNT,
    FRESH_RETEST_QUERY_COUNT,
    CalibrationReleaseError,
    build_calibration_release,
    validate_calibration_release_package,
)
from floodguard.label_factory.calibration_reserve import (
    _verify_canonical_grid_release,
    build_calibration_reserve_design,
)
from floodguard.label_factory.reference_authority_approval import (
    build_reference_authority_approval_package,
)
from test_label_factory_calibration_reserve import (
    _canonical_sha256 as _reserve_json_sha,
    _fixture as _reserve_fixture,
)
from test_label_factory_reference_authority_approval import (
    CREATED_AT,
    EVENT_ID,
    _decision_inputs,
    _rewrite_fixture_event,
    _role_package,
)


RELEASED_AT = "2026-07-11T16:00:00Z"


def test_freezes_exact_disjoint_membership_with_whole_tile_isolation(
    tmp_path: Path,
) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    output = tmp_path / "calibration-release"

    paths = build_calibration_release(
        reference_authority_approval_package=approval,
        canonical_grid_directory=grid,
        output_directory=output,
        release_id="mae_sai_calibration_release_v1",
        created_at_utc=RELEASED_AT,
    )
    receipt = validate_calibration_release_package(paths.directory)
    canonical_release = _verify_canonical_grid_release(paths.directory)

    calibration = pd.read_csv(paths.calibration_queries)
    retest = pd.read_csv(paths.fresh_retest_queries)
    tiles = pd.read_csv(paths.canonical_tiles)
    queries = pd.read_csv(paths.canonical_query_regions)
    calibration_ids = set(calibration["query_region_id"].astype(str))
    retest_ids = set(retest["query_region_id"].astype(str))
    reserved_tiles = set(receipt["approved_reserve"]["parent_tile_ids"])

    assert len(calibration) == CALIBRATION_QUERY_COUNT == 12
    assert len(retest) == FRESH_RETEST_QUERY_COUNT == 12
    assert calibration_ids.isdisjoint(retest_ids)
    assert calibration["dataset_role"].eq("reviewer_calibration").all()
    assert retest["dataset_role"].eq("reviewer_calibration").all()
    assert calibration["selected"].eq(False).all()  # noqa: E712
    assert retest["selected"].eq(False).all()  # noqa: E712

    tile_mask = tiles["tile_id"].astype(str).isin(reserved_tiles)
    query_mask = queries["tile_id"].astype(str).isin(reserved_tiles)
    assert tiles.loc[tile_mask, "dataset_role"].eq("reviewer_calibration").all()
    assert queries.loc[query_mask, "dataset_role"].eq("reviewer_calibration").all()
    assert tiles.loc[~tile_mask, "dataset_role"].eq("training_and_query_pool").all()
    assert queries.loc[~query_mask, "dataset_role"].eq("training_and_query_pool").all()
    assert queries.loc[query_mask, "eligible_for_active_selection"].eq(False).all()  # noqa: E712
    assert queries.loc[query_mask, "eligible_for_review_queue"].eq(False).all()  # noqa: E712
    assert (
        queries.loc[query_mask, "eligible_for_training_after_human_review"]
        .eq("no")
        .all()
    )

    assert receipt["authority_approval"]["manifest_file_sha256"] == _sha(
        approval / "reference_authority_approval.json"
    )
    assert canonical_release["release_id"] == receipt["release_id"]
    assert receipt["selection_contract"]["uses_labels_or_model_signals"] is False
    assert receipt["authentication"]["digital_signature_verified"] is False
    assert receipt["safety"]["calibration_execution_authorized"] is False
    assert receipt["safety"]["formal_review_authorized"] is False
    assert receipt["safety"]["eligible_for_model_training"] is False
    assert receipt["safety"]["eligible_for_model_evaluation"] is False
    assert receipt["safety"]["eligible_for_decision_layer"] is False
    assert not any(
        word in set(queries.columns)
        for word in ("reference_label", "weak_label", "model_probability")
    )

    with pytest.raises(CalibrationReleaseError, match="immutable"):
        build_calibration_release(
            reference_authority_approval_package=approval,
            canonical_grid_directory=grid,
            output_directory=output,
            release_id="mae_sai_calibration_release_v1",
            created_at_utc=RELEASED_AT,
        )


def test_rejects_pending_or_rejected_authority_packages(tmp_path: Path) -> None:
    grid, approval, design = _approved_fixture(tmp_path)

    with pytest.raises(CalibrationReleaseError, match="approval package is invalid"):
        build_calibration_release(
            reference_authority_approval_package=design,
            canonical_grid_directory=grid,
            output_directory=tmp_path / "from-provisional-design",
            release_id="invalid_pending_release_v1",
            created_at_utc=RELEASED_AT,
        )

    roles = _role_package(tmp_path / "rejected-roles")
    request, evidence_root, procedure = _decision_inputs(
        tmp_path / "rejected-decision", design
    )
    request["reserve_design_decision"]["decision"] = "rejected"
    request["reserve_design_decision"]["rationale"] = (
        "Synthetic rejection keeps reserve construction closed."
    )
    rejected = tmp_path / "rejected-authority"
    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        output_directory=rejected,
    )
    with pytest.raises(CalibrationReleaseError, match="not approved"):
        build_calibration_release(
            reference_authority_approval_package=rejected,
            canonical_grid_directory=grid,
            output_directory=tmp_path / "from-rejected-package",
            release_id="invalid_rejected_release_v1",
            created_at_utc=RELEASED_AT,
        )

    assert approval.is_dir()  # The approved control remains independently valid.


def test_rejects_parent_release_substitution_and_duplicate_ids(
    tmp_path: Path,
) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    substituted = tmp_path / "substituted-grid"
    _copy_tree(grid, substituted)
    tiles = pd.read_csv(substituted / "canonical_tiles.csv")
    tiles.loc[0, "valid_data_fraction"] = 0.999
    tiles.to_csv(substituted / "canonical_tiles.csv", index=False)
    _reseal_parent_grid(substituted)

    with pytest.raises(CalibrationReleaseError, match="substitution"):
        build_calibration_release(
            reference_authority_approval_package=approval,
            canonical_grid_directory=substituted,
            output_directory=tmp_path / "substituted-output",
            release_id="invalid_substitution_v1",
            created_at_utc=RELEASED_AT,
        )

    duplicate = tmp_path / "duplicate-grid"
    _copy_tree(grid, duplicate)
    queries = pd.read_csv(duplicate / "canonical_query_regions.csv")
    queries.loc[1, "query_region_id"] = queries.loc[0, "query_region_id"]
    queries.to_csv(duplicate / "canonical_query_regions.csv", index=False)
    _reseal_parent_grid(duplicate)
    with pytest.raises(CalibrationReleaseError, match="duplicate query_region_id"):
        build_calibration_release(
            reference_authority_approval_package=approval,
            canonical_grid_directory=duplicate,
            output_directory=tmp_path / "duplicate-output",
            release_id="invalid_duplicate_v1",
            created_at_utc=RELEASED_AT,
        )


def test_rejects_parent_queries_already_allocated_to_evaluation(
    tmp_path: Path,
) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    allocated = tmp_path / "evaluation-allocated-grid"
    _copy_tree(grid, allocated)
    queries = pd.read_csv(allocated / "canonical_query_regions.csv")
    queries.loc[0, "dataset_role"] = "untouched_geographic_test"
    queries.loc[0, "eligible_for_active_selection"] = False
    queries.loc[0, "eligible_for_review_queue"] = False
    queries.loc[0, "eligible_for_training_after_human_review"] = "no"
    queries.to_csv(allocated / "canonical_query_regions.csv", index=False)
    _reseal_parent_grid(allocated)

    with pytest.raises(
        CalibrationReleaseError,
        match="all source queries to remain in the training/query pool",
    ):
        build_calibration_release(
            reference_authority_approval_package=approval,
            canonical_grid_directory=allocated,
            output_directory=tmp_path / "evaluation-reuse-output",
            release_id="invalid_evaluation_reuse_v1",
            created_at_utc=RELEASED_AT,
        )


def test_rejects_membership_substitution_even_after_all_local_hashes_are_rewritten(
    tmp_path: Path,
) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    output = tmp_path / "release"
    build_calibration_release(
        reference_authority_approval_package=approval,
        canonical_grid_directory=grid,
        output_directory=output,
        release_id="mae_sai_calibration_release_v1",
        created_at_utc=RELEASED_AT,
    )

    calibration_path = output / "calibration_queries.csv"
    calibration = pd.read_csv(calibration_path)
    retest = pd.read_csv(output / "fresh_retest_queries.csv")
    calibration.iloc[0] = retest.iloc[0]
    calibration.to_csv(calibration_path, index=False)
    _rewrite_release_hashes_without_rederiving_membership(output)

    with pytest.raises(
        CalibrationReleaseError,
        match="membership differs|sets overlap",
    ):
        validate_calibration_release_package(output)


def test_release_receipt_duplicate_key_is_rejected(tmp_path: Path) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    output = tmp_path / "duplicate-json-release"
    build_calibration_release(
        reference_authority_approval_package=approval,
        canonical_grid_directory=grid,
        output_directory=output,
        release_id="mae_sai_duplicate_json_release_v1",
        created_at_utc=RELEASED_AT,
    )
    receipt = output / "calibration_release_receipt.json"
    raw = receipt.read_text(encoding="utf-8")
    receipt.write_text(
        raw.replace("{\n", '{\n  "release_id": "substituted-release",\n', 1),
        encoding="utf-8",
    )

    with pytest.raises(CalibrationReleaseError, match="duplicate key: release_id"):
        validate_calibration_release_package(output)


def test_cli_build_and_validate_report_closed_gates(tmp_path: Path) -> None:
    grid, approval, _design = _approved_fixture(tmp_path)
    output = tmp_path / "cli-release"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build_label_factory_calibration_release.py"
    )
    built = subprocess.run(
        [
            sys.executable,
            str(script),
            "build",
            "--reference-authority-approval-package",
            str(approval),
            "--canonical-grid-directory",
            str(grid),
            "--output",
            str(output),
            "--release-id",
            "mae_sai_calibration_release_cli_v1",
            "--created-at-utc",
            RELEASED_AT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    assert "calibration=12; fresh-retest=12; disjoint=true" in built.stdout
    assert "calibration-execution=false" in built.stdout
    assert f"Wrote immutable calibration release: {output.name}" in built.stdout
    assert str(tmp_path) not in built.stdout

    validated = subprocess.run(
        [sys.executable, str(script), "validate", "--package", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0, validated.stderr
    assert "formal-review=false" in validated.stdout
    assert f"Validated immutable calibration release: {output.name}" in validated.stdout
    assert str(tmp_path) not in validated.stdout


def _approved_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    grid, context = _reserve_fixture(tmp_path / "reserve-input")
    _rewrite_fixture_event(grid, EVENT_ID)
    design = tmp_path / "reserve-design"
    build_calibration_reserve_design(
        canonical_grid_directory=grid,
        context_alignment_manifest_path=context,
        output_directory=design,
        design_id="mae_sai_reserve_design_12x12_v1",
        calibration_query_count=12,
        retest_query_count=12,
        reserve_tile_count=3,
        minimum_remaining_pool_queries=8,
        created_at_utc="2026-07-11T12:00:00Z",
    )
    roles = _role_package(tmp_path / "roles")
    request, evidence_root, procedure = _decision_inputs(tmp_path, design)
    assert request["created_at_utc"] == CREATED_AT
    approval = tmp_path / "authority-approval"
    build_reference_authority_approval_package(
        request,
        evidence_root=evidence_root,
        human_role_package=roles,
        calibration_reserve_design_package=design,
        reference_procedure_path=procedure,
        output_directory=approval,
    )
    return grid, approval, design


def _rewrite_release_hashes_without_rederiving_membership(root: Path) -> None:
    receipt_path = root / "calibration_release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    calibration_path = root / "calibration_queries.csv"
    for record in receipt["artifacts"]:
        if record["package_path"] == "calibration_queries.csv":
            record["file_size_bytes"] = calibration_path.stat().st_size
            record["sha256"] = _sha(calibration_path)
            record["row_count"] = len(pd.read_csv(calibration_path))
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = _canonical_json_sha(receipt)
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    manifest_path = root / "release_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    for name in ("calibration_queries.csv", "calibration_release_receipt.json"):
        path = root / name
        mask = manifest["file_name"].eq(name)
        manifest.loc[mask, "file_size_bytes"] = path.stat().st_size
        manifest.loc[mask, "sha256"] = _sha(path)
    manifest.to_csv(manifest_path, index=False)

    seal_path = root / "release_seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["release_manifest_sha256"] = _sha(manifest_path)
    seal["calibration_release_receipt_sha256"] = receipt["receipt_sha256"]
    seal["calibration_release_receipt_file_sha256"] = _sha(receipt_path)
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _canonical_json_sha(seal)
    seal_path.write_text(
        json.dumps(seal, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _reseal_parent_grid(grid: Path) -> None:
    manifest_path = grid / "release_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    for name in ("canonical_tiles.csv", "canonical_query_regions.csv"):
        path = grid / name
        mask = manifest["file_name"].eq(name)
        manifest.loc[mask, "file_size_bytes"] = path.stat().st_size
        manifest.loc[mask, "sha256"] = _sha(path)
    manifest.to_csv(manifest_path, index=False)
    seal_path = grid / "release_seal.json"
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    seal["release_manifest_sha256"] = _sha(manifest_path)
    seal.pop("seal_sha256")
    seal["seal_sha256"] = _reserve_json_sha(seal)
    seal_path.write_text(
        json.dumps(seal, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _copy_tree(source: Path, target: Path) -> None:
    import shutil

    shutil.copytree(source, target)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
