from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.processing_alignment import (
    PROCESSING_EVIDENCE_COLUMNS,
    ProcessingAlignmentError,
    build_processing_alignment_receipt,
)
from floodguard.label_factory.registration_evidence import (
    RegistrationEvidenceError,
    RegistrationParameters,
    build_and_write_processing_evidence,
)
from test_label_factory_event_registry import event_row, source_row


def _write_raster(
    path: Path,
    values: np.ndarray,
    *,
    grid_hash: str,
    transform: object | None = None,
    nodata: float | int = -9999.0,
) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs="EPSG:32647",
        transform=transform or from_origin(581120, 2255680, 10, 10),
        nodata=nodata,
    ) as dataset:
        dataset.write(values, 1)
        dataset.update_tags(grid_contract_sha256=grid_hash)


def _inputs(
    tmp_path: Path,
    *,
    event_column_shift: int = 0,
) -> tuple[dict[str, Path], str]:
    event = EventRecord.from_mapping(event_row())
    grid_hash = event.grid.contract_sha256
    random = np.random.default_rng(20240915)
    base = random.normal(-12.0, 3.0, size=(192, 192)).astype("float32")
    vh = (0.72 * base + random.normal(0, 0.3, base.shape)).astype("float32")
    event_vv = np.roll(base * 1.08 + 1.5, event_column_shift, axis=1)
    event_vh = np.roll(vh * 0.95 - 0.7, event_column_shift, axis=1)
    values = {
        "pre_vv": base,
        "pre_vh": vh,
        "event_vv": event_vv,
        "event_vh": event_vh,
    }
    paths: dict[str, Path] = {}
    for role, array in values.items():
        path = tmp_path / f"{role}.tif"
        _write_raster(path, array, grid_hash=grid_hash)
        paths[role] = path
    for acquisition in ("pre", "event"):
        mask = np.zeros(base.shape, dtype="uint8")
        mask[0:2, :] = 2
        path = tmp_path / f"{acquisition}_mask.tif"
        _write_raster(path, mask, grid_hash=grid_hash, nodata=255)
        paths[f"{acquisition}_mask"] = path
    return paths, grid_hash


def _build(tmp_path: Path, *, shift: int = 0):
    paths, _grid_hash = _inputs(tmp_path, event_column_shift=shift)
    outputs = build_and_write_processing_evidence(
        pre_vv_path=paths["pre_vv"],
        pre_vh_path=paths["pre_vh"],
        event_vv_path=paths["event_vv"],
        event_vh_path=paths["event_vh"],
        pre_layover_shadow_mask_path=paths["pre_mask"],
        event_layover_shadow_mask_path=paths["event_mask"],
        asset_ids={
            "pre_vv": "S1-PRE-VV",
            "pre_vh": "S1-PRE-VH",
            "event_vv": "S1-EVENT-VV",
            "event_vh": "S1-EVENT-VH",
        },
        output_directory=tmp_path / "evidence",
        source_timestamp_utc="2024-09-20T00:00:00Z",
        processing_software="ESA SNAP GPT",
        processing_software_version="13.0.0",
        rtc_terrain_correction_method=(
            "pinned SNAP Terrain-Flattening and Range-Doppler Terrain-Correction"
        ),
        parameters=RegistrationParameters(
            window_size_pixels=64,
            minimum_windows_per_polarization=3,
        ),
    )
    return paths, outputs


def _four_sources(registration_error: float) -> tuple[SourceAssetRecord, ...]:
    rows: list[dict[str, object]] = []
    for asset_id, acquisition, role, sha, polarization in (
        ("S1-PRE-VV", "2024-09-01T12:00:00Z", "pre_event", "a", "VV"),
        ("S1-PRE-VH", "2024-09-01T12:00:00Z", "pre_event", "a", "VH"),
        ("S1-EVENT-VV", "2024-09-12T12:00:00Z", "event_time", "b", "VV"),
        ("S1-EVENT-VH", "2024-09-12T12:00:00Z", "event_time", "b", "VH"),
    ):
        row = source_row(
            asset_id=asset_id,
            acquisition=acquisition,
            event_relative_role=role,
            sha=sha * 64,
        )
        row["polarizations"] = polarization
        row["georegistration_method"] = "dual-polarization phase correlation"
        row["georegistration_error_pixels"] = registration_error
        rows.append(row)
    return tuple(SourceAssetRecord.from_mapping(row) for row in rows)


def test_builder_emits_receipt_compatible_byte_bound_evidence(tmp_path: Path) -> None:
    _paths, outputs = _build(tmp_path)
    evidence = pd.read_csv(outputs.processing_evidence_csv)
    registration = json.loads(outputs.registration_evidence.read_text("utf-8"))

    assert tuple(evidence.columns) == PROCESSING_EVIDENCE_COLUMNS
    assert len(evidence) == 4
    assert registration["registration_gate_passed"] is True
    assert registration["registration_error_pixels"] <= 0.5
    assert registration["accepted_window_count_by_polarization"] == {
        "VH": 9,
        "VV": 9,
    }
    assert evidence["query_model_only"].eq(True).all()  # noqa: E712
    assert evidence["eligible_for_decision_layer"].eq(False).all()  # noqa: E712
    assert evidence["eligible_for_fpps"].eq(False).all()  # noqa: E712
    assert evidence["eligible_for_warning"].eq(False).all()  # noqa: E712

    event = EventRecord.from_mapping(event_row())
    sources = _four_sources(float(registration["registration_error_pixels"]))
    receipt = build_processing_alignment_receipt(
        (event,),
        sources,
        outputs.processing_evidence_csv,
        allow_ungoverned_fixture=True,
    )
    assert receipt["source_asset_count"] == 4
    assert receipt["eligible_for_fpps"] is False


def test_one_pixel_scene_shift_is_recorded_and_fails_receipt_gate(
    tmp_path: Path,
) -> None:
    _paths, outputs = _build(tmp_path, shift=1)
    registration = json.loads(outputs.registration_evidence.read_text("utf-8"))
    evidence = pd.read_csv(outputs.processing_evidence_csv)

    assert registration["registration_gate_passed"] is False
    assert registration["registration_error_pixels"] > 0.5
    assert abs(registration["combined_median_shift_pixels"]["column"]) > 0.8
    with pytest.raises(ProcessingAlignmentError, match="exceeds"):
        build_processing_alignment_receipt(
            (EventRecord.from_mapping(event_row()),),
            _four_sources(0.5),
            evidence,
            allow_ungoverned_fixture=True,
        )


def test_builder_rejects_grid_mismatch_before_measurement(tmp_path: Path) -> None:
    paths, grid_hash = _inputs(tmp_path)
    with rasterio.open(paths["event_vh"], "r+") as dataset:
        dataset.update_tags(grid_contract_sha256="f" * 64)

    with pytest.raises(RegistrationEvidenceError, match="does not exactly match"):
        build_and_write_processing_evidence(
            pre_vv_path=paths["pre_vv"],
            pre_vh_path=paths["pre_vh"],
            event_vv_path=paths["event_vv"],
            event_vh_path=paths["event_vh"],
            asset_ids={role: f"A-{role}" for role in ("pre_vv", "pre_vh", "event_vv", "event_vh")},
            output_directory=tmp_path / "evidence",
            source_timestamp_utc="2024-09-20T00:00:00Z",
            processing_software="ESA SNAP GPT",
            processing_software_version="13.0.0",
            rtc_terrain_correction_method="specific pinned RTC graph",
            parameters=RegistrationParameters(window_size_pixels=64),
        )
    assert grid_hash != "f" * 64


def test_builder_rejects_uninformative_constant_scene(tmp_path: Path) -> None:
    event = EventRecord.from_mapping(event_row())
    paths: dict[str, Path] = {}
    for role in ("pre_vv", "pre_vh", "event_vv", "event_vh"):
        path = tmp_path / f"{role}.tif"
        _write_raster(
            path,
            np.full((64, 64), -10, dtype="float32"),
            grid_hash=event.grid.contract_sha256,
        )
        paths[role] = path

    with pytest.raises(RegistrationEvidenceError, match="accepted VV windows"):
        build_and_write_processing_evidence(
            pre_vv_path=paths["pre_vv"],
            pre_vh_path=paths["pre_vh"],
            event_vv_path=paths["event_vv"],
            event_vh_path=paths["event_vh"],
            asset_ids={role: f"A-{role}" for role in paths},
            output_directory=tmp_path / "evidence",
            source_timestamp_utc="2024-09-20T00:00:00Z",
            processing_software="ESA SNAP GPT",
            processing_software_version="13.0.0",
            rtc_terrain_correction_method="specific pinned RTC graph",
            parameters=RegistrationParameters(
                window_size_pixels=64,
                minimum_windows_per_polarization=1,
            ),
        )


def test_registration_evidence_cli_help() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_label_factory_registration_evidence.py"),
            "--help",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "pre-vv-asset-id" in result.stdout
    assert "minimum-psr" in result.stdout
