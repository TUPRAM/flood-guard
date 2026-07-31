from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.weak_query_summary import (
    WeakQuerySummaryError,
    build_weak_query_summary,
    verify_weak_query_summary,
    write_weak_query_summary,
)


GRID_HASH = "a" * 64


def _queries() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for index, (xmin, xmax) in enumerate(((0.0, 20.0), (20.0, 40.0))):
        rows.append(
            {
                "query_region_id": f"Q{index + 1}",
                "event_id": "TH-SYNTHETIC-2024",
                "tile_id": "T1",
                "grid_contract_sha256": GRID_HASH,
                "query_size_pixels": 2,
                "resolution_m": 10.0,
                "bbox_min_x": xmin,
                "bbox_min_y": 0.0,
                "bbox_max_x": xmax,
                "bbox_max_y": 20.0,
                "crs": "EPSG:32647",
                "dataset_role": "training_and_query_pool",
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    return pd.DataFrame(rows)


def _write_weak_vector(tmp_path: Path, *, invalid: bool = False) -> Path:
    gpd = pytest.importorskip("geopandas")
    shapely = pytest.importorskip("shapely")
    path = tmp_path / "weak.gpkg"
    geometry = (
        shapely.Polygon([(0, 0), (10, 20), (0, 20), (10, 0), (0, 0)])
        if invalid
        else shapely.box(0.0, 0.0, 10.0, 20.0)
    )
    frame = gpd.GeoDataFrame(
        {"not_official": [True]},
        geometry=[geometry],
        crs="EPSG:32647",
    )
    frame.to_file(path, layer="weak_extent", driver="GPKG")
    return path


def _source_manifest(path: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "file_name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "reference_mask_status": "weak_reference_candidate",
                "candidate_validation_metrics_allowed": True,
                "official_validation_truth_allowed": False,
                "unqualified_ml_label_allowed": False,
                "inspected_at_utc": "2026-07-12T00:00:00Z",
            }
        ]
    )


def test_build_weak_query_summary_preserves_positive_unlabeled_semantics(
    tmp_path: Path,
) -> None:
    vector = _write_weak_vector(tmp_path)
    summary, manifest = build_weak_query_summary(
        weak_vector_path=vector,
        weak_source_manifest=_source_manifest(vector),
        query_manifest=_queries(),
        vector_layer="weak_extent",
        generated_at_utc="2026-07-12T01:02:03Z",
    )

    by_id = summary.set_index("query_region_id")
    assert by_id.loc["Q1", "weak_label"] == "weak_positive_present"
    assert by_id.loc["Q1", "weak_positive_fraction"] == pytest.approx(0.5)
    assert by_id.loc["Q1", "weak_unreviewed_fraction"] == pytest.approx(0.5)
    assert bool(by_id.loc["Q1", "weak_boundary_query"]) is True
    assert by_id.loc["Q2", "weak_label"] == "unreviewed"
    assert by_id.loc["Q2", "weak_positive_fraction"] == 0.0
    assert by_id.loc["Q2", "weak_unreviewed_fraction"] == 1.0
    assert bool(by_id.loc["Q2", "weak_boundary_query"]) is False
    assert summary["weak_uncertain_fraction"].eq(0.0).all()
    assert summary["eligible_for_query_model_training"].eq(False).all()
    assert summary["query_model_only"].eq(True).all()
    assert summary["eligible_for_decision_layer"].eq(False).all()
    assert summary["eligible_for_fpps"].eq(False).all()
    assert summary["eligible_for_warning"].eq(False).all()
    assert manifest["interpretation"]["exterior_cell_centres"] == "unreviewed_not_dry"
    assert manifest["created_at_utc"] == "2026-07-12T01:02:03Z"
    assert summary["source_timestamp"].eq("2026-07-12T00:00:00Z").all()


def test_write_and_verify_weak_query_summary_detects_row_tampering(
    tmp_path: Path,
) -> None:
    vector = _write_weak_vector(tmp_path)
    written = write_weak_query_summary(
        weak_vector_path=vector,
        weak_source_manifest=_source_manifest(vector),
        query_manifest=_queries(),
        output_directory=tmp_path / "summary",
        vector_layer="weak_extent",
    )

    verified = verify_weak_query_summary(
        summary_csv=written.summary_csv,
        manifest_json=written.manifest_json,
    )
    assert len(verified) == 2
    assert verified["weak_summary_manifest_sha256"].str.fullmatch(
        r"[0-9a-f]{64}"
    ).all()

    tampered = pd.read_csv(written.summary_csv)
    tampered.loc[0, "weak_positive_fraction"] = 0.25
    tampered.to_csv(written.summary_csv, index=False)
    with pytest.raises(WeakQuerySummaryError, match="logical row hash"):
        verify_weak_query_summary(
            summary_csv=written.summary_csv,
            manifest_json=written.manifest_json,
        )


def test_weak_query_summary_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    vector = _write_weak_vector(tmp_path)
    source = _source_manifest(vector)
    source.loc[0, "sha256"] = "b" * 64

    with pytest.raises(WeakQuerySummaryError, match="hash differs"):
        build_weak_query_summary(
            weak_vector_path=vector,
            weak_source_manifest=source,
            query_manifest=_queries(),
            vector_layer="weak_extent",
        )


def test_weak_query_summary_refuses_to_turn_exterior_into_training_truth(
    tmp_path: Path,
) -> None:
    vector = _write_weak_vector(tmp_path)
    unsafe = _queries()
    unsafe["eligible_for_fpps"] = True

    with pytest.raises(WeakQuerySummaryError, match="eligible_for_fpps"):
        build_weak_query_summary(
            weak_vector_path=vector,
            weak_source_manifest=_source_manifest(vector),
            query_manifest=unsafe,
            vector_layer="weak_extent",
        )


def test_invalid_weak_geometry_requires_explicit_recorded_repair(
    tmp_path: Path,
) -> None:
    vector = _write_weak_vector(tmp_path, invalid=True)

    with pytest.raises(WeakQuerySummaryError, match="Self-intersection"):
        build_weak_query_summary(
            weak_vector_path=vector,
            weak_source_manifest=_source_manifest(vector),
            query_manifest=_queries(),
            vector_layer="weak_extent",
        )

    _, manifest = build_weak_query_summary(
        weak_vector_path=vector,
        weak_source_manifest=_source_manifest(vector),
        query_manifest=_queries(),
        vector_layer="weak_extent",
        repair_invalid_geometry=True,
    )
    validation = manifest["source"]["geometry_validation"]
    assert validation["invalid_feature_count"] == 1
    assert validation["repair_method"] == "shapely.make_valid"
    assert validation["repaired_geometry_is_not_new_truth"] is True
