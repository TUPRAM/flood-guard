from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.label_factory.sentinel1_processing import (
    AdaptiveOtsuConfig,
    Sentinel1ProcessingError,
    _otsu_threshold,
    build_adaptive_otsu_candidate,
)

GRID_HASH = hashlib.sha256(b"threshold-grid").hexdigest()
PRE_ID = "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_TEST.SAFE"
POST_ID = "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_TEST.SAFE"
CONFIG = AdaptiveOtsuConfig(
    window_pixels=8,
    stride_pixels=4,
    min_valid_samples=16,
    histogram_bins=32,
)


def _write_raster(
    path: Path,
    values: np.ndarray,
    *,
    source_id: str = "",
    shifted: bool = False,
) -> Path:
    transform = from_origin(581125 if shifted else 581120, 2255680, 10, 10)
    nodata = 255 if values.dtype == np.uint8 else -9999.0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs="EPSG:32647",
        transform=transform,
        nodata=nodata,
    ) as dataset:
        dataset.write(values, 1)
        dataset.update_tags(grid_contract_sha256=GRID_HASH, source_product_id=source_id)
    return path


def _inputs(tmp_path: Path) -> dict[str, Path]:
    checker = (np.indices((16, 16)).sum(axis=0) // 2) % 2 == 0
    pre = np.full((16, 16), -10, dtype="float32")
    post = pre.copy()
    post[checker] = -14
    post[0, 2] = -9999
    geometry = np.zeros((16, 16), dtype="uint8")
    geometry[0, 3] = 2
    water = np.zeros((16, 16), dtype="uint8")
    water[0, 0] = 1
    slope = np.full((16, 16), 5.0, dtype="float32")
    slope[0, 1] = 30
    inputs = {
        "pre_vv_db": _write_raster(tmp_path / "pre_vv.tif", pre, source_id=PRE_ID),
        "pre_vh_db": _write_raster(tmp_path / "pre_vh.tif", pre, source_id=PRE_ID),
        "post_vv_db": _write_raster(tmp_path / "post_vv.tif", post, source_id=POST_ID),
        "post_vh_db": _write_raster(tmp_path / "post_vh.tif", post, source_id=POST_ID),
        "pre_layover_shadow": _write_raster(tmp_path / "pre_geom.tif", geometry),
        "post_layover_shadow": _write_raster(tmp_path / "post_geom.tif", geometry),
        "permanent_water": _write_raster(tmp_path / "water.tif", water),
        "terrain_slope_degrees": _write_raster(tmp_path / "slope.tif", slope),
    }
    inputs.update(_write_test_manifests(tmp_path, inputs))
    return inputs


def _write_manifest(path: Path, payload: dict[str, object]) -> Path:
    payload["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_test_manifests(tmp_path: Path, inputs: dict[str, Path]) -> dict[str, Path]:
    manifests = {}
    for prefix, source_id in (("pre", PRE_ID), ("post", POST_ID)):
        layers = {
            "vv": inputs[f"{prefix}_vv_db"],
            "vh": inputs[f"{prefix}_vh_db"],
            "layover_shadow_mask": inputs[f"{prefix}_layover_shadow"],
        }
        payload = {
            "artifact_schema": "floodguard.sentinel1_processing_run.v1",
            "canonical_layers": {
                "grid": {"grid_contract_sha256": GRID_HASH},
                "source_product_id": source_id,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "outputs": {
                    role: {
                        "file_name": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                    for role, path in layers.items()
                },
            },
            "snap_execution": {
                "snap_version": "13.0.0",
                "orbit_auxiliary_name": "S1A_TEST_POEORB.EOF.zip",
                "source_product_name": source_id,
            },
        }
        manifests[f"{prefix}_processing_manifest"] = _write_manifest(
            tmp_path / f"{prefix}_processing.json", payload
        )
    layers = {
        "permanent_water_context": inputs["permanent_water"],
        "slope": inputs["terrain_slope_degrees"],
    }
    manifests["context_alignment_manifest"] = _write_manifest(
        tmp_path / "context_alignment.json",
        {
            "artifact_schema": "floodguard.context_alignment_manifest.v1",
            "layers": [
                {
                    "layer_role": role,
                    "path_hint": path.name,
                    "target_grid_sha256": GRID_HASH,
                    "processed_layer_sha256": hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest(),
                }
                for role, path in layers.items()
            ],
        },
    )
    return manifests


def _build(tmp_path: Path, inputs: dict[str, Path]) -> Path:
    return build_adaptive_otsu_candidate(
        **inputs,
        pre_observed_at_utc="2024-09-03T23:16:00Z",
        post_observed_at_utc="2024-09-15T23:16:01Z",
        event_id="mae_sai_2024",
        study_area_id="aoi-01_mae_sai_core",
        output_directory=tmp_path / "candidate",
        config=CONFIG,
    )


def test_candidate_bundle_distinguishes_observation_abstention_and_unsupported(
    tmp_path: Path,
) -> None:
    receipt_path = _build(tmp_path, _inputs(tmp_path))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert (
        receipt["artifact_schema"] == "floodguard.sentinel1_adaptive_otsu_candidate.v1"
    )
    assert receipt["dataset_mode"] == "candidate"
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["official_warning"] is False
    assert receipt["counts"]["candidate_cells"] > 0
    assert receipt["counts"]["classified_non_candidate_cells"] > 0
    assert receipt["counts"]["unsupported_cells"] == 2
    assert receipt["counts"]["permanent_water_abstained_cells"] == 1
    assert receipt["counts"]["terrain_abstained_cells"] == 1
    assert receipt["counts"]["histogram_abstained_cells"] == 0
    assert all(row["threshold_db"] is not None for row in receipt["window_receipts"])
    manifest_sha = receipt.pop("manifest_sha256")
    assert (
        manifest_sha
        == hashlib.sha256(
            json.dumps(
                receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
    )
    with rasterio.open(receipt_path.parent / "candidate_mask.tif") as dataset:
        candidate = dataset.read(1)
        assert dataset.tags()["official_warning"] == "false"
        assert candidate[0, 0] == 255  # permanent water abstention
        assert candidate[0, 1] == 255  # steep terrain abstention
        assert candidate[0, 2] == 255  # invalid SAR is unsupported
        assert candidate[0, 3] == 255  # layover/shadow is unsupported
        assert 0 in candidate and 1 in candidate
    with rasterio.open(receipt_path.parent / "abstention_code.tif") as dataset:
        codes = dataset.read(1)
        assert list(codes[0, :4]) == [1, 2, 255, 255]
    with pytest.raises(Sentinel1ProcessingError, match="immutable"):
        _build(tmp_path, _inputs(tmp_path))


def test_sparse_and_unimodal_histograms_abstain() -> None:
    sparse = np.array([0, 0, 4], dtype="float64")
    threshold, reason, _ = _otsu_threshold(sparse, CONFIG)
    assert threshold is None and reason == "insufficient_valid_support"
    narrow = np.full(64, 0.1)
    threshold, reason, _ = _otsu_threshold(narrow, CONFIG)
    assert threshold is None and reason == "narrow_or_invalid_distribution"
    unimodal = np.random.default_rng(11).normal(0, 1, 1024)
    threshold, reason, _ = _otsu_threshold(unimodal, CONFIG)
    assert threshold is None and reason == "unimodal_or_unstable_histogram"


def test_whole_scene_abstention_is_not_reported_as_zero_flood(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    uniform = np.full((16, 16), -10, dtype="float32")
    for role in ("post_vv_db", "post_vh_db"):
        _write_raster(inputs[role], uniform, source_id=POST_ID)
    inputs.update(_write_test_manifests(tmp_path, inputs))
    receipt_path = _build(tmp_path, inputs)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["result_status"] == "abstained_no_classified_cells"
    assert receipt["candidate_grid_area_km2"] is None
    assert receipt["counts"]["candidate_cells"] == 0
    assert receipt["counts"]["classified_non_candidate_cells"] == 0
    with rasterio.open(receipt_path.parent / "candidate_mask.tif") as dataset:
        assert np.all(dataset.read(1) == 255)


def test_grid_mismatch_and_unknown_permanent_water_fail_closed(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    _write_raster(
        inputs["post_vh_db"],
        np.full((16, 16), -10, dtype="float32"),
        source_id=POST_ID,
        shifted=True,
    )
    with pytest.raises(Sentinel1ProcessingError, match="exact canonical grid"):
        _build(tmp_path, inputs)
    _inputs(tmp_path)
    with rasterio.open(inputs["permanent_water"], "r+") as dataset:
        values = dataset.read(1)
        values[3, 3] = 2
        dataset.write(values, 1)
    inputs.update(_write_test_manifests(tmp_path, inputs))
    with pytest.raises(Sentinel1ProcessingError, match="0/1 and nodata"):
        _build(tmp_path, inputs)


def test_changed_raster_bytes_cannot_reuse_processing_receipt(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    with rasterio.open(inputs["post_vv_db"], "r+") as dataset:
        values = dataset.read(1)
        values[5, 5] = -30
        dataset.write(values, 1)
    with pytest.raises(Sentinel1ProcessingError, match="differs from its receipt"):
        _build(tmp_path, inputs)
    assert not (tmp_path / "candidate").exists()
