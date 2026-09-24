"""The SAR abstention diagnostic uses receipt bytes and grid geometry, not labels."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom

from floodguard.label_factory.sar_abstention_diagnostic import (
    DiagnosticError,
    aoi_reason_counts,
    canonical_sha256,
    diagnose,
    file_sha256,
    optical_receipt_sha256,
    summarize_windows,
)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    transform = from_origin(500000, 2000000, 10, 10)
    source = tmp_path / "abstention_code.tif"
    mask = tmp_path / "candidate_mask.tif"
    for path, values in (
        (source, np.array([[1, 2], [3, 255]], dtype=np.uint8)),
        (mask, np.full((2, 2), 255, dtype=np.uint8)),
    ):
        with rasterio.open(
            path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1],
            count=1, dtype="uint8", crs="EPSG:32647", transform=transform, nodata=255,
        ) as dataset:
            dataset.write(values, 1)
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [500000, 2000000], [500030, 2000000], [500030, 1999970],
            [500000, 1999970], [500000, 2000000],
        ]],
    }
    aoi = tmp_path / "aoi.geojson"
    aoi.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "geometry": transform_geom(
            "EPSG:32647", "EPSG:4326", polygon,
        ), "properties": {}}],
    }), encoding="utf-8")
    reference_receipt = {
        "schema": "floodguard.automated_optical_reference.v1",
        "reference_kind": "automated_optical_reference",
        "grid": {
            "crs": "EPSG:32647", "width": 3, "height": 3,
            "transform": list(tuple(transform)[:6]),
            "aoi_sha256": file_sha256(aoi),
        },
        "source_timestamp": "2024-09-15T03:45:29Z",
        "note": "แม่สาย",
    }
    reference_receipt["receipt_sha256"] = optical_receipt_sha256(reference_receipt)
    reference_receipt_path = tmp_path / "reference_receipt.json"
    reference_receipt_path.write_text(json.dumps(reference_receipt), encoding="utf-8")
    receipt = {
        "artifact_schema": "floodguard.sentinel1_adaptive_otsu_candidate.v1",
        "grid": {
            "crs": "EPSG:32647", "width": 2, "height": 2,
            "transform": list(tuple(transform)[:6]),
        },
        "outputs": {"abstention_code": {
            "file_name": source.name, "sha256": file_sha256(source),
        }, "candidate_mask": {
            "file_name": mask.name, "sha256": file_sha256(mask),
        }},
        "result_status": "abstained_no_classified_cells",
        "post_observed_at_utc": "2024-09-15T23:16:01Z",
        "configuration": {
            "min_valid_samples": 4,
            "min_class_fraction": 0.08,
            "min_mean_separation_db": 1.5,
            "min_between_variance_fraction": 0.72,
        },
        "window_receipts": [{
            "status": "abstained", "reason": "unimodal_or_unstable_histogram",
            "valid_samples": 20,
            "qc": {
                "class_fraction_min": 0.4,
                "mean_separation_db": 3.1,
                "between_variance_fraction": 0.65,
            },
        }],
        "counts": {"candidate_cells": 0},
    }
    receipt["manifest_sha256"] = canonical_sha256(receipt)
    receipt_path = tmp_path / "candidate_receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return receipt_path, reference_receipt_path, aoi, receipt


def test_window_summary_identifies_only_variance_veto(tmp_path: Path) -> None:
    _, _, _, receipt = _fixture(tmp_path)
    summary = summarize_windows(receipt)
    assert summary["sole_variance_veto_windows"] == 1
    assert summary["qualified_windows"] == 0
    assert summary["reason_counts"] == {"unimodal_or_unstable_histogram": 1}


def test_aoi_counts_separate_unsupported_and_outside_footprint(tmp_path: Path) -> None:
    receipt_path, reference_receipt_path, aoi, receipt = _fixture(tmp_path)
    reference_receipt = json.loads(reference_receipt_path.read_text(encoding="utf-8"))
    counts = aoi_reason_counts(
        receipt_path.parent / "abstention_code.tif", reference_receipt["grid"], aoi, receipt,
    )
    assert counts == {
        "aoi_cells": 9,
        "classified_cells": 0,
        "permanent_water_abstained_cells": 1,
        "terrain_abstained_cells": 1,
        "histogram_abstained_cells": 1,
        "unsupported_inside_source_footprint_cells": 1,
        "outside_source_footprint_cells": 5,
    }


def test_diagnosis_rejects_changed_receipt_and_reads_no_labels(tmp_path: Path) -> None:
    receipt_path, reference_receipt_path, aoi, _ = _fixture(tmp_path)
    expected_hash = file_sha256(receipt_path)
    result = diagnose(receipt_path, expected_hash, reference_receipt_path, aoi)
    assert result["reference_label_values_accessed"] is False
    assert result["candidate_rethresholded"] is False
    assert result["aoi_counts"]["classified_cells"] == 0
    assert result["receipt_sha256"] == canonical_sha256({
        key: value for key, value in result.items() if key != "receipt_sha256"
    })
    receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(DiagnosticError, match="receipt hash differs"):
        diagnose(receipt_path, expected_hash, reference_receipt_path, aoi)


def test_diagnosis_rejects_changed_candidate_mask(tmp_path: Path) -> None:
    receipt_path, reference_receipt_path, aoi, _ = _fixture(tmp_path)
    expected_hash = file_sha256(receipt_path)
    with rasterio.open(tmp_path / "candidate_mask.tif", "r+") as dataset:
        dataset.write(np.zeros((2, 2), dtype=np.uint8), 1)
    with pytest.raises(DiagnosticError, match="Candidate mask differs"):
        diagnose(receipt_path, expected_hash, reference_receipt_path, aoi)
