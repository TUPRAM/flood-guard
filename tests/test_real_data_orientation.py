from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.real_data_orientation import (
    OUTPUT_FILENAMES,
    RealDataOrientationError,
    build_real_data_orientation,
    verify_real_data_orientation_artifact,
)
from floodguard.label_factory.sar_change_features import FEATURE_COLUMNS


SHA_GRID = "a" * 64
SHA_SOURCE = "b" * 64
SHA_PROCESSING = "c" * 64
CREATED_AT = "2026-07-13T00:00:00Z"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _self_hash(payload: dict[str, object], field: str) -> dict[str, object]:
    result = dict(payload)
    result[field] = _canonical_hash(result)
    return result


def _fixture(tmp_path: Path) -> dict[str, Path]:
    source = tmp_path / "source"
    grid = source / "grid"
    context_dir = source / "context"
    feature_dir = source / "features"
    grid.mkdir(parents=True)
    context_dir.mkdir()
    feature_dir.mkdir()
    query_path = grid / "canonical_query_regions.csv"
    context_path = context_dir / "supported_query_evidence.csv"
    feature_path = feature_dir / "sar_change_v2_cells.csv"
    receipt_path = grid / "grid_validation_receipt_v3.json"
    seal_path = grid / "release_seal.json"

    query_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    query_ids: list[str] = []
    for query_index in range(8):
        query_id = f"Q{query_index:03d}"
        query_ids.append(query_id)
        tile = f"T{query_index // 4}"
        group = f"G{query_index // 4}"
        query_rows.append(
            {
                "query_region_id": query_id,
                "tile_id": tile,
                "event_id": "EVENT",
                "grid_contract_sha256": SHA_GRID,
                "source_registry_sha256": SHA_SOURCE,
                "processing_alignment_receipt_sha256": SHA_PROCESSING,
                "query_size_pixels": 32,
                "dataset_role": "training_and_query_pool",
                "overlap_group_id": group,
                "feature_schema_version": "sar_change_v2",
                "review_status": "unreviewed",
                "selected": False,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
        context_rows.append(
            {
                "query_region_id": query_id,
                "event_id": "EVENT",
                "grid_contract_sha256": SHA_GRID,
                "query_size_pixels": 32,
                "dataset_role": "training_and_query_pool",
                "overlap_group_id": group,
                "feature_schema_version": "sar_change_v2",
                "valid_data_fraction": 1.0,
                "permanent_water_fraction": (query_index % 3) / 10,
                "worldcover_water_fraction": (query_index % 2) / 10,
                "urban_fraction": query_index / 10,
                "forest_fraction": (7 - query_index) / 10,
                "cropland_fraction": (query_index % 4) / 10,
                "steep_terrain_fraction": (query_index % 5) / 10,
                "slope_p90_degrees": 5 + query_index,
                "round0_stratum": "urban" if query_index % 2 else "forest",
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
        for row in range(32):
            for column in range(32):
                cell_id = f"{query_id}_R{row:04d}_C{column:04d}"
                pre_vv = -15.0 + query_index * 0.4 + row * 0.01
                event_vv = pre_vv - (query_index - 3.5) * 0.2 - column * 0.001
                pre_vh = -21.0 + query_index * 0.3 + column * 0.01
                event_vh = pre_vh - (3.5 - query_index) * 0.15 - row * 0.001
                feature_rows.append(
                    {
                        "sample_id": cell_id,
                        "query_region_id": query_id,
                        "cell_id": cell_id,
                        "grid_contract_sha256": SHA_GRID,
                        "event_id": "EVENT",
                        "tile_id": tile,
                        "source_registry_sha256": SHA_SOURCE,
                        "processing_alignment_receipt_sha256": SHA_PROCESSING,
                        "row_index": row,
                        "column_index": column,
                        "spatial_group_id": group,
                        "dataset_role": "training_and_query_pool",
                        "feature_schema_version": "sar_change_v2",
                        "pre_vv_db": pre_vv,
                        "event_vv_db": event_vv,
                        "pre_vh_db": pre_vh,
                        "event_vh_db": event_vh,
                        "vv_change_db": pre_vv - event_vv,
                        "vh_change_db": pre_vh - event_vh,
                        "valid_data_fraction": 1.0,
                    }
                )
    queries = pd.DataFrame(query_rows)
    queries.to_csv(query_path, index=False, lineterminator="\n")
    context = pd.DataFrame(context_rows)
    context.to_csv(context_path, index=False, lineterminator="\n")
    features = pd.DataFrame(feature_rows, columns=FEATURE_COLUMNS)
    features.to_csv(feature_path, index=False, lineterminator="\n")

    context_derivation = _self_hash(
        {
            "artifact_schema": "floodguard.supported_query_pool_derivation.v1",
            "outputs": {
                "supported_queries": {
                    "file_name": context_path.name,
                    "row_count": 8,
                    "sha256": _file_hash(context_path),
                }
            },
            "query_model_only": True,
            "eligible_for_human_annotation": False,
            "eligible_for_active_selection": False,
            "eligible_for_review_queue": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        },
        "manifest_sha256",
    )
    _write_json(context_dir / "supported_query_derivation.json", context_derivation)

    feature_derivation = _self_hash(
        {
            "artifact_schema": "floodguard.sar_change_v2_features.v1",
            "feature_schema_version": "sar_change_v2",
            "feature_order": [
                "pre_vv_db",
                "event_vv_db",
                "pre_vh_db",
                "event_vh_db",
                "vv_change_db",
                "vh_change_db",
                "valid_data_fraction",
            ],
            "grid_contract_sha256": SHA_GRID,
            "formulas": {
                "vv_change_db": "pre_vv_db - event_vv_db",
                "vh_change_db": "pre_vh_db - event_vh_db",
                "valid_data_fraction": (
                    "1.0 only after all four source observations are valid; otherwise extraction blocks"
                ),
            },
            "sources": {
                "query_manifest": {
                    "file_sha256": _file_hash(query_path),
                    "row_count": 8,
                    "query_region_ids": query_ids,
                }
            },
            "output": {
                "feature_csv_sha256": _file_hash(feature_path),
                "row_count": 8192,
                "query_region_ids": query_ids,
                "columns": list(FEATURE_COLUMNS),
            },
            "safety": {
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "allowed_output_use": "query_committee_features_only",
            },
        },
        "manifest_sha256",
    )
    derivation_path = feature_dir / "sar_change_v2_derivation.json"
    _write_json(derivation_path, feature_derivation)

    receipt = _self_hash(
        {
            "artifact_schema": "floodguard.grid_validation_receipt.v3",
            "grid_contract_sha256s": [SHA_GRID],
            "processing_alignment_receipt_sha256": SHA_PROCESSING,
            "source_registry_sha256": "d" * 64,
            "query_count": 8,
            "tile_count": 2,
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
        },
        "receipt_sha256",
    )
    _write_json(receipt_path, receipt)
    release_manifest_path = grid / "release_manifest.csv"
    pd.DataFrame(
        [
            {
                "file_name": query_path.name,
                "file_size_bytes": query_path.stat().st_size,
                "sha256": _file_hash(query_path),
                "immutable_status": "frozen_test",
            }
        ]
    ).to_csv(release_manifest_path, index=False, lineterminator="\n")
    seal = _self_hash(
        {
            "artifact_schema": "floodguard.canonical_grid_release.v1",
            "grid_validation_receipt_file_sha256": _file_hash(receipt_path),
            "grid_validation_receipt_sha256": receipt["receipt_sha256"],
            "processing_alignment_receipt_sha256": SHA_PROCESSING,
            "query_count": 8,
            "tile_count": 2,
            "overall_training_ready": False,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "release_manifest_sha256": _file_hash(release_manifest_path),
        },
        "seal_sha256",
    )
    _write_json(seal_path, seal)
    return {
        "feature": feature_path,
        "derivation": derivation_path,
        "queries": query_path,
        "context": context_path,
        "receipt": receipt_path,
        "seal": seal_path,
    }


def _build(paths: dict[str, Path], output: Path):
    return build_real_data_orientation(
        feature_csv=paths["feature"],
        derivation_manifest_path=paths["derivation"],
        canonical_query_csv=paths["queries"],
        context_evidence_csv=paths["context"],
        grid_validation_receipt_path=paths["receipt"],
        release_seal_path=paths["seal"],
        output_directory=output,
        expected_cell_count=8192,
        expected_query_count=8,
        expected_cells_per_query=1024,
        expected_spatial_group_count=2,
        chunk_size=257,
        random_seed=19,
        created_at_utc=CREATED_AT,
    )


def _rehash_feature_derivation(paths: dict[str, Path]) -> None:
    payload = json.loads(paths["derivation"].read_text(encoding="utf-8"))
    payload.pop("manifest_sha256")
    payload["output"]["feature_csv_sha256"] = _file_hash(paths["feature"])
    payload["manifest_sha256"] = _canonical_hash(payload)
    _write_json(paths["derivation"], payload)


def _rehash_context_derivation(paths: dict[str, Path]) -> None:
    manifest_path = paths["context"].parent / "supported_query_derivation.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.pop("manifest_sha256")
    payload["outputs"]["supported_queries"]["sha256"] = _file_hash(paths["context"])
    payload["manifest_sha256"] = _canonical_hash(payload)
    _write_json(manifest_path, payload)


def test_builds_only_aggregate_reviewer_safe_deterministic_outputs(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    first = _build(paths, tmp_path / "first")
    second = _build(paths, tmp_path / "second")
    summary = verify_real_data_orientation_artifact(first.directory)
    assert summary["training_gate_status"] == "blocked_missing_released_training_labels"
    assert summary["safety"]["formal_review_authorized"] is False
    assert summary["safety"]["eligible_for_fpps"] is False
    forbidden = {"query_region_id", "tile_id", "priority", "label", "model_score"}
    for name in OUTPUT_FILENAMES:
        left = first.directory / name
        right = second.directory / name
        assert left.read_bytes() == right.read_bytes()
        assert forbidden.isdisjoint(pd.read_csv(left).columns)
    assert len(pd.read_csv(first.cluster_sensitivity)) == 4
    assert set(pd.read_csv(first.cluster_sensitivity)["k"]) == {3, 4, 5, 6}


def test_fails_closed_on_feature_hash_tamper(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["feature"].write_bytes(paths["feature"].read_bytes() + b"\n")
    with pytest.raises(RealDataOrientationError, match="does not match its derivation"):
        _build(paths, tmp_path / "output")


def test_fails_closed_on_wrong_grain(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    frame = pd.read_csv(paths["feature"])
    frame.loc[1, ["row_index", "column_index"]] = [0, 0]
    frame.loc[1, "cell_id"] = frame.loc[0, "cell_id"]
    frame.loc[1, "sample_id"] = frame.loc[0, "sample_id"]
    frame.to_csv(paths["feature"], index=False, lineterminator="\n")
    _rehash_feature_derivation(paths)
    with pytest.raises(RealDataOrientationError, match="duplicate cell"):
        _build(paths, tmp_path / "output")


def test_fails_closed_on_change_formula_error(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    frame = pd.read_csv(paths["feature"])
    frame.loc[10, "vv_change_db"] += 0.25
    frame.to_csv(paths["feature"], index=False, lineterminator="\n")
    _rehash_feature_derivation(paths)
    with pytest.raises(RealDataOrientationError, match="formula validation"):
        _build(paths, tmp_path / "output")


def test_fails_closed_on_context_join_error(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    frame = pd.read_csv(paths["context"])
    frame.loc[0, "event_id"] = "OTHER"
    frame.to_csv(paths["context"], index=False, lineterminator="\n")
    _rehash_context_derivation(paths)
    with pytest.raises(RealDataOrientationError, match="join disagrees"):
        _build(paths, tmp_path / "output")


def test_fails_closed_on_source_safety_violation(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    payload = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    payload.pop("receipt_sha256")
    payload["eligible_for_warning"] = True
    payload["receipt_sha256"] = _canonical_hash(payload)
    _write_json(paths["receipt"], payload)
    seal = json.loads(paths["seal"].read_text(encoding="utf-8"))
    seal.pop("seal_sha256")
    seal["grid_validation_receipt_file_sha256"] = _file_hash(paths["receipt"])
    seal["grid_validation_receipt_sha256"] = payload["receipt_sha256"]
    seal["seal_sha256"] = _canonical_hash(seal)
    _write_json(paths["seal"], seal)
    with pytest.raises(RealDataOrientationError, match="receipt contract"):
        _build(paths, tmp_path / "output")


def test_verifier_rejects_output_tamper_and_output_overwrite(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    built = _build(paths, tmp_path / "output")
    with pytest.raises(RealDataOrientationError, match="new or empty"):
        _build(paths, built.directory)
    built.cluster_summary.write_bytes(built.cluster_summary.read_bytes() + b"\n")
    with pytest.raises(RealDataOrientationError, match="hash mismatch"):
        verify_real_data_orientation_artifact(built.directory)
