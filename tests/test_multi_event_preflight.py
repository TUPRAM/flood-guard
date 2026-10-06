"""Synthetic and adversarial file-backed release preflight fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from test_label_factory_qualified_label_release import _release_context

from floodguard.label_factory.multi_event_preflight import (
    MultiEventPreflightError,
    QualifiedReleaseFiles,
    revalidate_qualified_release_files,
)


def _write_json(root: Path, name: str, value: object) -> Path:
    path = root / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _bundle(root: Path) -> QualifiedReleaseFiles:
    context = _release_context()
    raster = root / "synthetic_reference.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs="EPSG:6933",
        transform=from_origin(0.0, 20.0, 10.0, 10.0),
        nodata=255,
    ) as dataset:
        dataset.write(np.array([[0, 1], [1, 0]], dtype=np.uint8), 1)
    grid = _write_json(
        root,
        "analysis_grid.json",
        {
            "target_crs": "EPSG:6933",
            "transform": [10.0, 0.0, 0.0, 0.0, -10.0, 20.0],
            "width": 2,
            "height": 2,
        },
    )
    return QualifiedReleaseFiles(
        release_json=_write_json(root, "release.json", context["release"]),
        formal_review_json=_write_json(root, "formal.json", context["authorization"]),
        human_role_package=_write_json(root, "human.json", context["package"]),
        reviewer_calibration=_write_json(
            root, "calibration.json", context["calibration"]
        ),
        labelset_manifest=_write_json(root, "labelset.json", context["labelset"]),
        labelset_validation=_write_json(root, "validation.json", context["validation"]),
        review_pair_json=(_write_json(root, "pair.json", context["pair"]),),
        qualified_reference_json=_write_json(
            root, "reference.json", context["reference"]
        ),
        reference_raster=raster,
        analysis_grid=grid,
    )


def test_fixture_chain_revalidates_exact_files_and_remains_non_authoritative(tmp_path):
    result = revalidate_qualified_release_files(_bundle(tmp_path))
    assert result["status"] == "validated_synthetic_fixture_only"
    assert result["eligible_for_real_experiment"] is False
    assert result["eligible_for_downstream_decision"] is False
    assert result["purpose"] == "flood_model_training_labels"
    assert len(result["reference_raster_sha256"]) == 64
    assert result["acquisition_source_sha256_by_role"] == {}


def test_source_byte_substitution_fails_even_with_unchanged_release_json(tmp_path):
    files = _bundle(tmp_path)
    with files.reference_raster.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(
        MultiEventPreflightError, match="reference raster source bytes changed"
    ):
        revalidate_qualified_release_files(files)


def test_grid_or_lineage_file_substitution_fails(tmp_path):
    files = _bundle(tmp_path)
    files.analysis_grid.write_text("{}", encoding="utf-8")
    with pytest.raises(
        MultiEventPreflightError, match="analysis grid source bytes changed"
    ):
        revalidate_qualified_release_files(files)

    files = _bundle(tmp_path)
    pair = json.loads(files.review_pair_json[0].read_text(encoding="utf-8"))
    pair["agreement_evidence_sha256"] = "a" * 64
    files.review_pair_json[0].write_text(json.dumps(pair), encoding="utf-8")
    with pytest.raises(MultiEventPreflightError, match="canonical validator"):
        revalidate_qualified_release_files(files)


def test_missing_source_or_review_pair_fails(tmp_path):
    files = _bundle(tmp_path)
    files.reference_raster.unlink()
    with pytest.raises(MultiEventPreflightError, match="unavailable"):
        revalidate_qualified_release_files(files)

    files = _bundle(tmp_path)
    files = QualifiedReleaseFiles(**{**vars(files), "review_pair_json": ()})
    with pytest.raises(MultiEventPreflightError, match="at least one review-pair"):
        revalidate_qualified_release_files(files)


def test_source_role_substitution_and_parent_traversal_fail(tmp_path):
    files = _bundle(tmp_path)
    files = QualifiedReleaseFiles(
        **{
            **vars(files),
            "acquisition_source_by_role": {"pre_event_sar": files.reference_raster},
        }
    )
    with pytest.raises(MultiEventPreflightError, match="exactly cover"):
        revalidate_qualified_release_files(files)

    files = _bundle(tmp_path)
    files = QualifiedReleaseFiles(
        **{**vars(files), "release_json": tmp_path / "sub" / ".." / "release.json"}
    )
    with pytest.raises(MultiEventPreflightError, match="parent traversal"):
        revalidate_qualified_release_files(files)
