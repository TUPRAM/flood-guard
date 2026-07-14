from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin

from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.manifests import QUERY_MANIFEST_COLUMNS
from floodguard.label_factory.sar_change_features import (
    FEATURE_COLUMNS,
    FEATURE_CSV_FILENAME,
    FEATURE_MANIFEST_FILENAME,
    SarChangeFeatureError,
    build_and_write_sar_change_v2_features,
    build_sar_change_v2_features,
    verify_sar_change_v2_feature_artifact,
)
from floodguard.label_factory.training_join import FEATURE_METADATA_COLUMNS


REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_HASH = "a" * 64
SOURCE_HASH = "b" * 64
RECEIPT_HASH = "c" * 64
TRANSFORM = from_origin(100.0, 200.0, 10.0, 10.0)
CRS = "EPSG:32647"
NODATA = -9999.0


def _write_raster(
    path: Path,
    values: np.ndarray,
    *,
    transform=TRANSFORM,
    crs: str = CRS,
    nodata: float = NODATA,
    grid_hash: str | None = GRID_HASH,
    count: int = 1,
    dtype: str = "float32",
) -> Path:
    array = np.asarray(values, dtype=dtype)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=array.shape[1],
        height=array.shape[0],
        count=count,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as target:
        for band in range(1, count + 1):
            target.write(array, band)
        if grid_hash is not None:
            target.update_tags(grid_contract_sha256=grid_hash)
    return path


def _query_row(
    query_id: str,
    *,
    tile_id: str,
    query_row: int,
    query_col: int,
    bounds: tuple[float, float, float, float],
    overlap_group: str,
) -> dict[str, object]:
    min_x, min_y, max_x, max_y = bounds
    return {
        "query_region_id": query_id,
        "tile_id": tile_id,
        "event_id": "TH-MAESAI-2024-09",
        "grid_id": "mae-sai-grid-v1",
        "grid_contract_sha256": GRID_HASH,
        "source_registry_sha256": SOURCE_HASH,
        "processing_alignment_receipt_sha256": RECEIPT_HASH,
        "pre_source_asset_ids": "S1-PRE-VV|S1-PRE-VH",
        "event_source_asset_ids": "S1-EVENT-VV|S1-EVENT-VH",
        "pre_product_ids": "PRODUCT-PRE",
        "event_product_ids": "PRODUCT-EVENT",
        "pre_acquisition_utc": "2024-09-03T23:16:00Z",
        "event_acquisition_utc": "2024-09-15T23:16:00Z",
        "pre_source_sha256s": "d" * 64,
        "event_source_sha256s": "e" * 64,
        "query_row": query_row,
        "query_col": query_col,
        "query_size_pixels": 2,
        "resolution_m": 10.0,
        "bbox_min_x": min_x,
        "bbox_min_y": min_y,
        "bbox_max_x": max_x,
        "bbox_max_y": max_y,
        "crs": CRS,
        "dataset_role": "training_and_query_pool",
        "overlap_group_id": overlap_group,
        "feature_schema_version": "sar_change_v2",
        "review_status": "unreviewed",
        "selected": False,
        "eligible_for_human_annotation": True,
        "eligible_for_active_selection": True,
        "eligible_for_review_queue": True,
        "eligible_for_query_model_training": False,
        "eligible_for_training_after_human_review": "conditional",
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "source_timestamp": "2026-07-10T00:00:00Z",
        "confidence_class": "medium",
        "assumptions": "Synthetic aligned-raster contract fixture only.",
    }


def _make_case(tmp_path: Path) -> dict[str, Path]:
    base = np.arange(16, dtype=np.float32).reshape(4, 4)
    paths = {
        "pre_vv": _write_raster(tmp_path / "pre_vv.tif", base - 20.0),
        "event_vv": _write_raster(tmp_path / "event_vv.tif", base - 22.0),
        "pre_vh": _write_raster(tmp_path / "pre_vh.tif", base - 30.0),
        "event_vh": _write_raster(tmp_path / "event_vh.tif", base - 31.0),
    }
    queries = pd.DataFrame(
        [
            _query_row(
                "QUERY-B",
                tile_id="TILE-B",
                query_row=1,
                query_col=1,
                bounds=(120.0, 160.0, 140.0, 180.0),
                overlap_group="GROUP-B",
            ),
            _query_row(
                "QUERY-A",
                tile_id="TILE-A",
                query_row=0,
                query_col=0,
                bounds=(100.0, 180.0, 120.0, 200.0),
                overlap_group="GROUP-A",
            ),
        ],
        columns=QUERY_MANIFEST_COLUMNS,
    )
    query_path = tmp_path / "queries.csv"
    queries.to_csv(query_path, index=False, lineterminator="\n")
    paths["queries"] = query_path
    return paths


def _build(case: dict[str, Path], output: Path):
    return build_and_write_sar_change_v2_features(
        pre_vv_path=case["pre_vv"],
        event_vv_path=case["event_vv"],
        pre_vh_path=case["pre_vh"],
        event_vh_path=case["event_vh"],
        query_manifest_path=case["queries"],
        output_directory=output,
        created_at_utc="2026-07-10T12:00:00Z",
    )


def test_builds_deterministic_training_join_compatible_features(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    written = _build(case, tmp_path / "features-a")
    features = pd.read_csv(written.feature_csv)

    assert tuple(features.columns) == FEATURE_COLUMNS
    assert len(features) == 8
    assert features["query_region_id"].tolist()[:4] == ["QUERY-A"] * 4
    assert features["cell_id"].iloc[0] == "QUERY-A_R0000_C0000"
    assert features["sample_id"].equals(features["cell_id"])
    assert features.loc[0, "spatial_group_id"] == "GROUP-A"
    assert features.loc[4, "spatial_group_id"] == "GROUP-B"
    assert features["vv_change_db"].eq(2.0).all()
    assert features["vh_change_db"].eq(1.0).all()
    assert features["valid_data_fraction"].eq(1.0).all()
    assert set(FEATURE_METADATA_COLUMNS).issubset(features.columns)
    assert set(
        get_feature_schema("sar_change_v2").required_feature_names
    ).issubset(features.columns)

    manifest = json.loads(written.derivation_manifest.read_text(encoding="utf-8"))
    assert manifest["feature_schema_version"] == "sar_change_v2"
    assert manifest["grid_contract_sha256"] == GRID_HASH
    assert manifest["sources"]["rasters"]["pre_vv_db"]["file_sha256"] == hashlib.sha256(
        case["pre_vv"].read_bytes()
    ).hexdigest()
    assert manifest["output"]["query_region_ids"] == ["QUERY-A", "QUERY-B"]
    assert manifest["safety"]["eligible_for_fpps"] is False

    verified = verify_sar_change_v2_feature_artifact(
        feature_csv=written.feature_csv,
        derivation_manifest_path=written.derivation_manifest,
        query_manifest_path=case["queries"],
        pre_vv_path=case["pre_vv"],
        event_vv_path=case["event_vv"],
        pre_vh_path=case["pre_vh"],
        event_vh_path=case["event_vh"],
    )
    assert verified.row_count == 8
    assert verified.query_region_ids == ("QUERY-A", "QUERY-B")

    second = _build(case, tmp_path / "features-b")
    assert written.feature_csv.read_bytes() == second.feature_csv.read_bytes()
    assert written.derivation_manifest.read_bytes() == second.derivation_manifest.read_bytes()


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"crs": "EPSG:32648"}, "CRS"),
        ({"transform": from_origin(101.0, 200.0, 10.0, 10.0)}, "affine"),
        ({"shape": (3, 4)}, "dimensions"),
        ({"nodata": -32768.0}, "nodata"),
        ({"grid_hash": "f" * 64}, "grid contract"),
        ({"grid_hash": None}, "lacks required"),
        ({"count": 2}, "exactly one band"),
    ],
)
def test_fails_closed_on_raster_contract_mismatch(
    tmp_path: Path,
    replacement: dict[str, object],
    message: str,
) -> None:
    case = _make_case(tmp_path)
    shape = replacement.get("shape", (4, 4))
    values = np.ones(shape, dtype=np.float32)  # type: ignore[arg-type]
    _write_raster(
        case["event_vh"],
        values,
        transform=replacement.get("transform", TRANSFORM),
        crs=str(replacement.get("crs", CRS)),
        nodata=float(replacement.get("nodata", NODATA)),
        grid_hash=replacement.get("grid_hash", GRID_HASH),  # type: ignore[arg-type]
        count=int(replacement.get("count", 1)),
    )

    with pytest.raises(SarChangeFeatureError, match=message):
        build_sar_change_v2_features(
            pre_vv_path=case["pre_vv"],
            event_vv_path=case["event_vv"],
            pre_vh_path=case["pre_vh"],
            event_vh_path=case["event_vh"],
            query_manifest=case["queries"],
        )


def test_rejects_nodata_or_nonfinite_cells_in_any_query(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    values = np.full((4, 4), -25.0, dtype=np.float32)
    values[0, 0] = NODATA
    _write_raster(case["event_vv"], values)
    with pytest.raises(SarChangeFeatureError, match="nodata is never imputed"):
        build_sar_change_v2_features(
            pre_vv_path=case["pre_vv"],
            event_vv_path=case["event_vv"],
            pre_vh_path=case["pre_vh"],
            event_vh_path=case["event_vh"],
            query_manifest=case["queries"],
        )


@pytest.mark.parametrize(
    ("row_index", "column", "value", "message"),
    [
        (0, "bbox_min_x", 101.0, "bounds do not equal|not aligned"),
        (0, "crs", "EPSG:32648", "CRS"),
        (0, "grid_contract_sha256", "f" * 64, "mix grid"),
        (0, "feature_schema_version", "legacy_real_weak_sar_v1", "sar_change_v2"),
        (0, "eligible_for_fpps", True, "eligible_for_fpps"),
    ],
)
def test_rejects_noncanonical_or_misaligned_queries(
    tmp_path: Path,
    row_index: int,
    column: str,
    value: object,
    message: str,
) -> None:
    case = _make_case(tmp_path)
    queries = pd.read_csv(case["queries"])
    queries.loc[row_index, column] = value
    queries.to_csv(case["queries"], index=False, lineterminator="\n")

    with pytest.raises(SarChangeFeatureError, match=message):
        build_sar_change_v2_features(
            pre_vv_path=case["pre_vv"],
            event_vv_path=case["event_vv"],
            pre_vh_path=case["pre_vh"],
            event_vh_path=case["event_vh"],
            query_manifest=case["queries"],
        )


def test_rejects_overlapping_query_windows(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    queries = pd.read_csv(case["queries"])
    for column in ("bbox_min_x", "bbox_min_y", "bbox_max_x", "bbox_max_y"):
        queries.loc[0, column] = queries.loc[1, column]
    queries.to_csv(case["queries"], index=False, lineterminator="\n")

    with pytest.raises(SarChangeFeatureError, match="overlap"):
        build_sar_change_v2_features(
            pre_vv_path=case["pre_vv"],
            event_vv_path=case["event_vv"],
            pre_vh_path=case["pre_vh"],
            event_vh_path=case["event_vh"],
            query_manifest=case["queries"],
        )


def test_immutable_writer_and_verifier_reject_mutated_output(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    output = tmp_path / "features"
    written = _build(case, output)
    with pytest.raises(SarChangeFeatureError, match="cannot be overwritten"):
        _build(case, output)

    frame = pd.read_csv(written.feature_csv)
    frame.loc[0, "vv_change_db"] = 999.0
    frame.to_csv(written.feature_csv, index=False, lineterminator="\n")
    with pytest.raises(SarChangeFeatureError, match="declared SHA-256"):
        verify_sar_change_v2_feature_artifact(
            feature_csv=written.feature_csv,
            derivation_manifest_path=written.derivation_manifest,
            query_manifest_path=case["queries"],
            pre_vv_path=case["pre_vv"],
            event_vv_path=case["event_vv"],
            pre_vh_path=case["pre_vh"],
            event_vh_path=case["event_vh"],
        )


def test_cli_help_and_missing_input_fail_closed(tmp_path: Path) -> None:
    script = REPO_ROOT / "scripts" / "build_sar_change_v2_features.py"
    help_result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--pre-vv" in help_result.stdout
    assert "--event-vh" in help_result.stdout
    assert "--query-manifest" in help_result.stdout

    blocked = subprocess.run(
        [
            sys.executable,
            str(script),
            "--pre-vv",
            "missing-pre-vv.tif",
            "--event-vv",
            "missing-event-vv.tif",
            "--pre-vh",
            "missing-pre-vh.tif",
            "--event-vh",
            "missing-event-vh.tif",
            "--query-manifest",
            "missing.csv",
            "--output-directory",
            str(tmp_path / "blocked"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 2
    assert "BLOCKED:" in blocked.stderr
    assert not (tmp_path / "blocked").exists()
