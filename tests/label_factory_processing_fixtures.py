"""Synthetic-only helpers for processing/alignment contract tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.processing_alignment import (
    PROCESSING_EVIDENCE_COLUMNS,
    build_processing_alignment_receipt,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_processing_evidence(
    tmp_path: Path,
    events: tuple[EventRecord, ...] | list[EventRecord],
    sources: tuple[SourceAssetRecord, ...] | list[SourceAssetRecord],
) -> pd.DataFrame:
    """Create byte-backed synthetic artifacts; never representative raster data."""

    event_by_id = {event.event_id: event for event in events}
    rows: list[dict[str, object]] = []
    for asset in sorted(sources, key=lambda item: item.asset_id):
        if asset.event_relative_role == "static_context":
            continue
        event = event_by_id[asset.event_id]
        artifact_dir = tmp_path / asset.asset_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        processed = artifact_dir / "synthetic_processed.tif"
        coverage = artifact_dir / "synthetic_coverage.json"
        valid = artifact_dir / "synthetic_valid_data.json"
        registration = artifact_dir / "synthetic_registration.json"
        processed.write_bytes(
            f"synthetic processed bytes only:{asset.asset_id}".encode("utf-8")
        )
        coverage.write_text(
            '{"synthetic":true,"coverage_fraction":1.0}\n', encoding="utf-8"
        )
        valid.write_text(
            '{"synthetic":true,"valid_data_fraction":0.95}\n', encoding="utf-8"
        )
        registration.write_text(
            '{"synthetic":true,"registration_error_pixels":0.25}\n',
            encoding="utf-8",
        )
        resolution = event.analysis_resolution_m
        width = 2048
        height = 2048
        rows.append(
            {
                "asset_id": asset.asset_id,
                "processed_artifact_id": f"PROC-{asset.asset_id}",
                "processed_file_path": str(processed),
                "processed_file_sha256": file_sha256(processed),
                "processing_software": "synthetic_fixture_processor",
                "processing_software_version": "1.0.0-test",
                "rtc_terrain_correction_method": "synthetic_range_doppler_rtc_fixture",
                "output_crs": event.analysis_crs,
                "affine_a": resolution,
                "affine_b": 0.0,
                "affine_c": event.grid_origin_x,
                "affine_d": 0.0,
                "affine_e": -resolution,
                "affine_f": event.grid_origin_y + height * resolution,
                "width_pixels": width,
                "height_pixels": height,
                "pixel_size_x_m": resolution,
                "pixel_size_y_m": resolution,
                "nodata_convention": "synthetic nodata=-9999 with explicit valid mask",
                "resampling_method": "synthetic bilinear for continuous SAR fixture",
                "coverage_fraction": 1.0,
                "valid_data_fraction": 0.95,
                "coverage_evidence_path": str(coverage),
                "coverage_evidence_sha256": file_sha256(coverage),
                "valid_data_evidence_path": str(valid),
                "valid_data_evidence_sha256": file_sha256(valid),
                "registration_method": "synthetic phase-correlation fixture",
                "registration_error_pixels": 0.25,
                "registration_evidence_path": str(registration),
                "registration_evidence_sha256": file_sha256(registration),
                "grid_contract_sha256": event.grid.contract_sha256,
                "source_timestamp": "2024-09-21T00:00:00Z",
                "confidence_class": "low",
                "assumptions": (
                    "Synthetic byte and metadata fixture only; no real raster "
                    "processing, flood observation, or flood truth."
                ),
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    return pd.DataFrame(rows, columns=PROCESSING_EVIDENCE_COLUMNS)


def synthetic_processing_receipt(
    tmp_path: Path,
    events: tuple[EventRecord, ...] | list[EventRecord],
    sources: tuple[SourceAssetRecord, ...] | list[SourceAssetRecord],
) -> dict[str, object]:
    evidence = synthetic_processing_evidence(tmp_path, events, sources)
    return build_processing_alignment_receipt(
        events,
        sources,
        evidence,
        allow_ungoverned_fixture=True,
    )
