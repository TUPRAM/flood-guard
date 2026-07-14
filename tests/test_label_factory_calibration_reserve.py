from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.calibration_reserve import (
    CalibrationReserveError,
    DESIGN_SCHEMA_V1,
    DESIGN_SCHEMA_V2,
    LEGACY_BUILDER_ID,
    build_calibration_reserve_design,
    load_calibration_reserve_design_receipt,
    verify_calibration_reserve_design_package,
    verify_calibration_reserve_design_receipt,
)


def test_builds_provisional_context_only_reserve_without_query_selection(
    tmp_path: Path,
) -> None:
    grid, context = _fixture(tmp_path)

    paths = build_calibration_reserve_design(
        canonical_grid_directory=grid,
        context_alignment_manifest_path=context,
        output_directory=tmp_path / "design",
        design_id="fixture_design_v1",
        calibration_query_count=8,
        retest_query_count=8,
        reserve_tile_count=2,
        minimum_remaining_pool_queries=8,
        created_at_utc="2026-07-11T12:00:00Z",
    )

    receipt = load_calibration_reserve_design_receipt(paths.design_receipt)
    assert receipt["artifact_schema"] == DESIGN_SCHEMA_V2
    assert receipt["status"] == "provisional_authority_approval_pending"
    assert receipt["provisional_recommendation"]["reserved_query_capacity"] == 16
    assert len(receipt["provisional_recommendation"]["tile_ids"]) == 2
    assert receipt["safety"]["final_calibration_query_ids"] == []
    assert receipt["safety"]["final_retest_query_ids"] == []
    assert receipt["safety"]["uses_weak_or_reference_labels"] is False
    assert receipt["safety"]["uses_model_outputs"] is False
    assert receipt["safety"]["review_bundles_created"] is False
    assert receipt["safety"]["valid_tile_assignments_input"] is False
    assert receipt["near_tie_authority_review"]["authority_must_review_tradeoff"] is True

    candidates = pd.read_csv(paths.candidate_combinations)
    assert candidates["recommended_provisional_design"].sum() == 1
    assert candidates["final_query_selection_performed"].eq(False).all()  # noqa: E712
    assert candidates["eligible_for_query_model_training"].eq(False).all()  # noqa: E712
    assert candidates["eligible_for_decision_layer"].eq(False).all()  # noqa: E712
    assert candidates["eligible_for_fpps"].eq(False).all()  # noqa: E712
    assert candidates["eligible_for_warning"].eq(False).all()  # noqa: E712
    assert "query_region_id" not in candidates.columns
    assert "within_near_tie_threshold" in candidates.columns
    assert "authority_conservation_option" in candidates.columns

    roles = pd.read_csv(paths.authority_pending_role_allocation)
    assert set(roles["proposed_dataset_role_after_authority_approval"]) == {
        "reviewer_calibration",
        "training_and_query_pool",
    }
    assert roles["valid_tile_assignments_input"].eq(False).all()  # noqa: E712
    assert roles["eligible_for_human_annotation"].eq(False).all()  # noqa: E712
    assert roles["eligible_for_training_after_human_review"].eq("no").all()
    assert roles["final_calibration_query_ids_selected"].eq(False).all()  # noqa: E712


def test_rejects_any_model_or_selection_signal_column(tmp_path: Path) -> None:
    grid, context = _fixture(tmp_path, forbidden_signal=True)

    with pytest.raises(
        CalibrationReserveError,
        match="refuses label/model/selection signal columns: model_prediction",
    ):
        build_calibration_reserve_design(
            canonical_grid_directory=grid,
            context_alignment_manifest_path=context,
            output_directory=tmp_path / "design",
            design_id="fixture_design_v1",
            calibration_query_count=8,
            retest_query_count=8,
            reserve_tile_count=2,
            minimum_remaining_pool_queries=8,
        )


def test_rejects_a_preselected_or_reviewed_source_query(tmp_path: Path) -> None:
    grid, context = _fixture(tmp_path, selected=True)

    with pytest.raises(CalibrationReserveError, match="selected=false"):
        build_calibration_reserve_design(
            canonical_grid_directory=grid,
            context_alignment_manifest_path=context,
            output_directory=tmp_path / "design",
            design_id="fixture_design_v1",
            calibration_query_count=8,
            retest_query_count=8,
            reserve_tile_count=2,
            minimum_remaining_pool_queries=8,
        )


def test_rejects_tampered_release_and_tampered_design_receipt(tmp_path: Path) -> None:
    grid, context = _fixture(tmp_path)
    (grid / "canonical_tiles.csv").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(CalibrationReserveError, match="artifact size mismatch"):
        build_calibration_reserve_design(
            canonical_grid_directory=grid,
            context_alignment_manifest_path=context,
            output_directory=tmp_path / "design",
            design_id="fixture_design_v1",
            calibration_query_count=8,
            retest_query_count=8,
            reserve_tile_count=2,
            minimum_remaining_pool_queries=8,
        )

    grid, context = _fixture(tmp_path / "second")
    paths = build_calibration_reserve_design(
        canonical_grid_directory=grid,
        context_alignment_manifest_path=context,
        output_directory=tmp_path / "second" / "design",
        design_id="fixture_design_v1",
        calibration_query_count=8,
        retest_query_count=8,
        reserve_tile_count=2,
        minimum_remaining_pool_queries=8,
    )
    receipt = json.loads(paths.design_receipt.read_text(encoding="utf-8"))
    receipt["safety"]["eligible_for_fpps"] = True
    with pytest.raises(CalibrationReserveError, match="self-hash mismatch"):
        verify_calibration_reserve_design_receipt(receipt)


def test_legacy_schema_v1_without_near_tie_extension_remains_valid(
    tmp_path: Path,
) -> None:
    receipt = _current_receipt(tmp_path)
    receipt["artifact_schema"] = DESIGN_SCHEMA_V1
    receipt["builder"] = LEGACY_BUILDER_ID
    receipt.pop("near_tie_authority_review")
    receipt["planning_parameters"].pop("near_tie_score_delta")
    _rehash_receipt(receipt)

    verify_calibration_reserve_design_receipt(receipt)


def test_near_tie_extension_is_atomic_and_required_by_schema_v2(
    tmp_path: Path,
) -> None:
    partial_v1 = _current_receipt(tmp_path / "partial")
    partial_v1["artifact_schema"] = DESIGN_SCHEMA_V1
    partial_v1["builder"] = LEGACY_BUILDER_ID
    partial_v1.pop("near_tie_authority_review")
    _rehash_receipt(partial_v1)
    with pytest.raises(CalibrationReserveError, match="must appear together"):
        verify_calibration_reserve_design_receipt(partial_v1)

    incomplete_v2 = _current_receipt(tmp_path / "v2")
    incomplete_v2.pop("near_tie_authority_review")
    incomplete_v2["planning_parameters"].pop("near_tie_score_delta")
    _rehash_receipt(incomplete_v2)
    with pytest.raises(CalibrationReserveError, match="Schema v2 requires"):
        verify_calibration_reserve_design_receipt(incomplete_v2)


def test_real_immutable_design_v1_v2_v3_packages_when_configured() -> None:
    pilot_root_raw = os.environ.get("FLOODGUARD_MAE_SAI_PILOT_ROOT")
    if not pilot_root_raw:
        pytest.skip("Set FLOODGUARD_MAE_SAI_PILOT_ROOT for immutable-package regression.")
    designs = Path(pilot_root_raw) / "calibration_role_designs"
    receipts = {
        version: verify_calibration_reserve_design_package(
            designs / f"calibration_role_design_{version}"
        )
        for version in ("v1", "v2", "v3")
    }

    assert receipts["v1"]["artifact_schema"] == DESIGN_SCHEMA_V1
    assert receipts["v2"]["artifact_schema"] == DESIGN_SCHEMA_V1
    assert receipts["v3"]["artifact_schema"] == DESIGN_SCHEMA_V1
    assert "near_tie_authority_review" not in receipts["v1"]
    assert "near_tie_authority_review" not in receipts["v2"]
    assert receipts["v3"]["near_tie_authority_review"][
        "authority_must_review_tradeoff"
    ] is True


def _current_receipt(root: Path) -> dict[str, object]:
    grid, context = _fixture(root)
    paths = build_calibration_reserve_design(
        canonical_grid_directory=grid,
        context_alignment_manifest_path=context,
        output_directory=root / "design",
        design_id="schema_fixture_v2",
        calibration_query_count=8,
        retest_query_count=8,
        reserve_tile_count=2,
        minimum_remaining_pool_queries=8,
        created_at_utc="2026-07-11T12:00:00Z",
    )
    return json.loads(paths.design_receipt.read_text(encoding="utf-8"))


def _rehash_receipt(receipt: dict[str, object]) -> None:
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = _canonical_sha256(receipt)


def _fixture(
    root: Path,
    *,
    forbidden_signal: bool = False,
    selected: bool = False,
) -> tuple[Path, Path]:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    grid = root / "grid"
    grid.mkdir(parents=True)
    tile_rows: list[dict[str, object]] = []
    query_rows: list[dict[str, object]] = []
    for tile_index in range(4):
        tile_id = f"T{tile_index}"
        tile_rows.append(
            {
                "tile_id": tile_id,
                "event_id": "E1",
                "x_index": tile_index,
                "y_index": 0,
                "dataset_role": "training_and_query_pool",
                "valid_data_fraction": 1.0 - tile_index * 0.01,
                "eligible_for_human_annotation": True,
                "eligible_for_active_selection": True,
                "eligible_for_review_queue": True,
                "eligible_for_query_model_training": False,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
        for column in range(8):
            row = {
                "query_region_id": f"{tile_id}_Q{column}",
                "tile_id": tile_id,
                "event_id": "E1",
                "query_size_pixels": 1,
                "resolution_m": 1.0,
                "bbox_min_x": tile_index * 8 + column,
                "bbox_min_y": 1.0,
                "bbox_max_x": tile_index * 8 + column + 1.0,
                "bbox_max_y": 2.0,
                "crs": "EPSG:32647",
                "dataset_role": "training_and_query_pool",
                "review_status": "unreviewed",
                "selected": selected and tile_index == 0 and column == 0,
                "eligible_for_human_annotation": True,
                "eligible_for_active_selection": True,
                "eligible_for_review_queue": True,
                "eligible_for_query_model_training": False,
                "eligible_for_training_after_human_review": "conditional",
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
            if forbidden_signal:
                row["model_prediction"] = 0.5
            query_rows.append(row)
    pd.DataFrame(tile_rows).to_csv(grid / "canonical_tiles.csv", index=False)
    pd.DataFrame(query_rows).to_csv(
        grid / "canonical_query_regions.csv", index=False
    )

    manifest_rows = []
    for name in ("canonical_tiles.csv", "canonical_query_regions.csv"):
        path = grid / name
        manifest_rows.append(
            {
                "file_name": name,
                "file_size_bytes": path.stat().st_size,
                "sha256": _file_sha256(path),
                "artifact_role": "fixture",
                "immutable_status": "frozen_fixture",
            }
        )
    manifest_path = grid / "release_manifest.csv"
    pd.DataFrame(manifest_rows).to_csv(manifest_path, index=False)
    seal_payload = {
        "artifact_schema": "floodguard.canonical_grid_release.v1",
        "release_id": "fixture_canonical_v1",
        "sealed_at_utc": "2026-07-11T11:00:00Z",
        "release_manifest_sha256": _file_sha256(manifest_path),
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    seal = {**seal_payload, "seal_sha256": _canonical_sha256(seal_payload)}
    (grid / "release_seal.json").write_text(
        json.dumps(seal, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    context_dir = root / "context"
    context_dir.mkdir(parents=True)
    transform = from_origin(0, 2, 1, 1)
    layers = {
        "land_cover": np.asarray(
            [
                [10, 10, 40, 40, 50, 50, 80, 80] * 4,
                [10] * 32,
            ],
            dtype="uint8",
        ),
        "permanent_water_context": np.asarray(
            [[0, 0, 0, 0, 0, 0, 1, 1] * 4, [0] * 32], dtype="uint8"
        ),
        "slope": np.asarray(
            [list(range(32)), list(range(32))], dtype="float32"
        ),
    }
    nodata_by_role = {
        "land_cover": 0,
        "permanent_water_context": 255,
        "slope": -9999.0,
    }
    source_roles = {
        "land_cover": ["worldcover"],
        "permanent_water_context": ["jrc_occurrence", "jrc_seasonality"],
        "slope": ["copernicus_dem"],
    }
    layer_rows = []
    for role, array in layers.items():
        path = context_dir / f"{role}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=32,
            height=2,
            count=1,
            dtype=str(array.dtype),
            crs="EPSG:32647",
            transform=transform,
            nodata=nodata_by_role[role],
        ) as dataset:
            dataset.write(array, 1)
        layer_rows.append(
            {
                "layer_role": role,
                "path_hint": path.name,
                "processed_layer_sha256": _file_sha256(path),
                "allowed_for_blinded_review_candidate": True,
                "source_roles": source_roles[role],
            }
        )
    context_payload = {
        "artifact_schema": "floodguard.context_alignment_manifest.v1",
        "builder": "floodguard.label_factory.context_alignment@v1",
        "target_grid": {
            "crs": "EPSG:32647",
            "affine": [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f],
            "width": 32,
            "height": 2,
            "target_grid_sha256": "1" * 64,
        },
        "layers": layer_rows,
        "source_inputs": [
            {"source_role": "worldcover"},
            {"source_role": "jrc_occurrence"},
            {"source_role": "jrc_seasonality"},
            {"source_role": "copernicus_dem"},
        ],
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    context_manifest = {
        **context_payload,
        "manifest_sha256": _canonical_sha256(context_payload),
    }
    context_path = context_dir / "context_alignment_manifest.json"
    context_path.write_text(
        json.dumps(context_manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return grid, context_path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
