from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.processing_alignment import (
    build_processing_alignment_receipt,
)
from floodguard.label_factory.review_derivative_generator import (
    ReviewDerivativeGenerationError,
    build_and_write_review_derivative_candidates,
    validate_review_derivative_candidate_outputs,
)
from floodguard.label_factory.review_derivatives import (
    build_review_derivative_lineage_receipt,
)
from label_factory_processing_fixtures import synthetic_processing_evidence
from test_label_factory_event_registry import event_row, source_row


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(
    tmp_path: Path,
) -> tuple[dict[str, object], dict[tuple[str, str], tuple[str, Path]]]:
    event = EventRecord.from_mapping(event_row())
    source_rows = []
    definitions = (
        ("pre_event", "VV", "S1-PRE-VV", "2024-09-01T12:00:00Z", "a"),
        ("pre_event", "VH", "S1-PRE-VH", "2024-09-01T12:00:00Z", "a"),
        ("event_time", "VV", "S1-EVENT-VV", "2024-09-12T12:00:00Z", "b"),
        ("event_time", "VH", "S1-EVENT-VH", "2024-09-12T12:00:00Z", "b"),
    )
    for role, polarization, asset_id, acquisition, hash_character in definitions:
        row = source_row(
            asset_id=asset_id,
            acquisition=acquisition,
            event_relative_role=role,
            sha=hash_character * 64,
        )
        row["polarizations"] = polarization
        row["product_id"] = f"PRODUCT-{'PRE' if role == 'pre_event' else 'EVENT'}"
        source_rows.append(row)
    sources = tuple(SourceAssetRecord.from_mapping(row) for row in source_rows)
    evidence = synthetic_processing_evidence(tmp_path / "processing", [event], sources)
    evidence["width_pixels"] = 32
    evidence["height_pixels"] = 32
    transform = Affine(
        event.analysis_resolution_m,
        0.0,
        event.grid_origin_x,
        0.0,
        -event.analysis_resolution_m,
        event.grid_origin_y + 32 * event.analysis_resolution_m,
    )
    values = {
        ("pre_event", "VV"): 5.0,
        ("event_time", "VV"): 1.0,
        ("pre_event", "VH"): -10.0,
        ("event_time", "VH"): -12.0,
    }
    source_paths: dict[tuple[str, str], tuple[str, Path]] = {}
    source_by_id = {source.asset_id: source for source in sources}
    for index, raw in evidence.iterrows():
        asset = source_by_id[str(raw["asset_id"])]
        polarization = asset.polarizations
        path = Path(str(raw["processed_file_path"]))
        array = np.full((32, 32), values[(asset.event_relative_role, polarization)], dtype=np.float32)
        if asset.event_relative_role == "event_time" and polarization == "VH":
            array[0, 0] = -9999.0
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=32,
            height=32,
            count=1,
            dtype="float32",
            crs=event.analysis_crs,
            transform=transform,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(array, 1)
            dataset.set_band_description(
                1, f"{asset.event_relative_role}_{polarization.lower()}_db"
            )
            dataset.update_tags(
                grid_contract_sha256=event.grid.contract_sha256,
                query_model_only="true",
                eligible_for_decision_layer="false",
                eligible_for_fpps="false",
                eligible_for_warning="false",
            )
        evidence.loc[index, "processed_file_sha256"] = _sha(path)
        evidence.loc[index, "affine_a"] = transform.a
        evidence.loc[index, "affine_b"] = transform.b
        evidence.loc[index, "affine_c"] = transform.c
        evidence.loc[index, "affine_d"] = transform.d
        evidence.loc[index, "affine_e"] = transform.e
        evidence.loc[index, "affine_f"] = transform.f
        source_paths[(asset.event_relative_role, polarization)] = (
            asset.asset_id,
            path,
        )
    receipt = build_processing_alignment_receipt(
        [event],
        sources,
        evidence,
        allow_ungoverned_fixture=True,
    )
    return receipt, source_paths


def _generate(tmp_path: Path) -> tuple[object, dict[str, object]]:
    receipt, sources = _fixture(tmp_path)
    paths = build_and_write_review_derivative_candidates(
        event_id="TH-MAESAI-2024-09",
        derivative_set_id="SYNTHETIC-CHANGE-CANDIDATE-V1",
        pre_vv_asset_id=sources[("pre_event", "VV")][0],
        pre_vv_path=sources[("pre_event", "VV")][1],
        event_vv_asset_id=sources[("event_time", "VV")][0],
        event_vv_path=sources[("event_time", "VV")][1],
        pre_vh_asset_id=sources[("pre_event", "VH")][0],
        pre_vh_path=sources[("pre_event", "VH")][1],
        event_vh_asset_id=sources[("event_time", "VH")][0],
        event_vh_path=sources[("event_time", "VH")][1],
        processing_alignment_receipt=receipt,
        output_directory=tmp_path / "candidate_v1",
        generated_at_utc="2024-09-21T00:00:00Z",
        fixed_stretch_min_db=-10.0,
        fixed_stretch_max_db=10.0,
        allow_ungoverned_fixture=True,
    )
    return paths, receipt


def test_generator_writes_fixed_change_rasters_and_four_source_receipt(
    tmp_path: Path,
) -> None:
    paths, processing = _generate(tmp_path)
    manifest = validate_review_derivative_candidate_outputs(
        paths.generation_manifest.parent
    )

    with rasterio.open(paths.vv_change) as vv:
        assert vv.read(1, masked=True)[1, 1] == pytest.approx(4.0)
        assert vv.nodata == -9999.0
    with rasterio.open(paths.vh_change) as vh:
        values = vh.read(1, masked=True)
        assert values[1, 1] == pytest.approx(2.0)
        assert values.mask[0, 0]
    with rasterio.open(paths.fixed_stretch_change_composite) as rgb:
        assert rgb.count == 3
        assert rgb.read(1)[1, 1] == 179
        assert rgb.read(2)[1, 1] == 153
        assert rgb.read(3)[1, 1] == 166
        assert rgb.dataset_mask()[0, 0] == 0
        assert rgb.dataset_mask()[1, 1] == 255

    assert manifest["authority_approval_status"] == "authority_approval_pending"
    assert manifest["fixed_display_parameters"][
        "statistics_influence_display"
    ] is False
    derivative_receipt = build_review_derivative_lineage_receipt(
        paths.build_spec,
        processing_alignment_receipt=processing,
        validated_at_utc="2024-09-21T01:00:00Z",
        allow_ungoverned_fixture=True,
    )
    assert len(derivative_receipt["source_rasters"]) == 4
    assert derivative_receipt["layer_count"] == 3


def test_generator_is_write_once_and_validation_detects_output_tampering(
    tmp_path: Path,
) -> None:
    paths, processing = _generate(tmp_path)
    with pytest.raises(ReviewDerivativeGenerationError, match="already exists"):
        build_and_write_review_derivative_candidates(
            event_id="TH-MAESAI-2024-09",
            derivative_set_id="SYNTHETIC-CHANGE-CANDIDATE-V1",
            pre_vv_asset_id="S1-PRE-VV",
            pre_vv_path=tmp_path / "missing.tif",
            event_vv_asset_id="S1-EVENT-VV",
            event_vv_path=tmp_path / "missing.tif",
            pre_vh_asset_id="S1-PRE-VH",
            pre_vh_path=tmp_path / "missing.tif",
            event_vh_asset_id="S1-EVENT-VH",
            event_vh_path=tmp_path / "missing.tif",
            processing_alignment_receipt=processing,
            output_directory=paths.generation_manifest.parent,
            allow_ungoverned_fixture=True,
        )

    paths.vv_change.write_bytes(b"tampered")
    with pytest.raises(ReviewDerivativeGenerationError, match="checksum/size"):
        validate_review_derivative_candidate_outputs(
            paths.generation_manifest.parent
        )


def test_generator_rejects_asymmetric_or_scene_adaptive_stretch_proxy(
    tmp_path: Path,
) -> None:
    receipt, sources = _fixture(tmp_path)
    with pytest.raises(ReviewDerivativeGenerationError, match="symmetric"):
        build_and_write_review_derivative_candidates(
            event_id="TH-MAESAI-2024-09",
            derivative_set_id="SYNTHETIC-CHANGE-CANDIDATE-V1",
            pre_vv_asset_id=sources[("pre_event", "VV")][0],
            pre_vv_path=sources[("pre_event", "VV")][1],
            event_vv_asset_id=sources[("event_time", "VV")][0],
            event_vv_path=sources[("event_time", "VV")][1],
            pre_vh_asset_id=sources[("pre_event", "VH")][0],
            pre_vh_path=sources[("pre_event", "VH")][1],
            event_vh_asset_id=sources[("event_time", "VH")][0],
            event_vh_path=sources[("event_time", "VH")][1],
            processing_alignment_receipt=receipt,
            output_directory=tmp_path / "bad",
            fixed_stretch_min_db=-2.0,
            fixed_stretch_max_db=8.0,
            allow_ungoverned_fixture=True,
        )


def test_candidate_generator_cli_is_governance_explicit() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_review_derivative_candidates.py"),
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "governance-package" in result.stdout
    assert "processing-alignment-receipt" in result.stdout
    assert "fixed-stretch-min-db" in result.stdout
