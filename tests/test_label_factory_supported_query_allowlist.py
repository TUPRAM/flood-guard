from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from floodguard.label_factory.event_registry import EventRecord, SourceAssetRecord
from floodguard.label_factory.manifests import (
    ManifestContractError,
    build_grid_manifests,
    validate_grid_manifests,
)
from floodguard.label_factory.processing_alignment import (
    PROCESSING_EVIDENCE_COLUMNS,
    build_processing_alignment_receipt,
)
from floodguard.label_factory.supported_query_pool import (
    ApprovedAoiWgs84,
    build_and_write_supported_query_pool,
)

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from rasterio.warp import transform


EVENT_ID = "TH-MAESAI-ALLOWLIST-TEST"
RESOLUTION = 10.0
SIZE = 256
LEFT = 499_200.0
TOP = 2_252_800.0
TRANSFORM = from_origin(LEFT, TOP, RESOLUTION, RESOLUTION)


def test_allowlisted_grid_keeps_parent_tile_and_only_supported_children(
    tmp_path: Path,
) -> None:
    event = _event(cleared=True)
    events_path = _write_events(tmp_path / "events.csv", event)
    sar = _write_sar(tmp_path / "sar", event)
    sources = _sources(cleared=True)
    receipt = _processing_receipt(tmp_path / "receipt-evidence", event, sources, sar)
    support = build_and_write_supported_query_pool(
        event_registry_path=events_path,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        approved_aoi=_covering_aoi(),
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )

    canonical = build_grid_manifests(
        (event,),
        support.provisional_tile_assignments,
        sources,
        receipt,
        allow_ungoverned_fixture=True,
        supported_query_derivation=support.derivation,
    )

    # The parent tile is retained for source/receipt lineage. Exactly one
    # unsupported 32x32 child was omitted; no nodata was imputed.
    assert len(canonical.tiles) == 1
    assert len(canonical.query_regions) == 63
    assert canonical.tiles.loc[0, "allowlisted_query_count"] == 63
    assert canonical.tiles["supported_query_allowlist_applied"].eq(True).all()
    assert canonical.query_regions["supported_query_allowlist_applied"].eq(
        True
    ).all()
    omitted = canonical.tiles.loc[0, "tile_id"] + "_R00_C00_S32"
    assert omitted not in set(canonical.query_regions["query_region_id"])
    assert canonical.query_regions["processing_alignment_receipt_sha256"].eq(
        receipt["receipt_sha256"]
    ).all()
    assert canonical.query_regions["supported_query_derivation_sha256"].eq(
        canonical.tiles.loc[0, "supported_query_derivation_sha256"]
    ).all()
    assert canonical.query_regions["supported_query_csv_sha256"].eq(
        canonical.tiles.loc[0, "supported_query_csv_sha256"]
    ).all()
    assert canonical.query_regions["eligible_for_decision_layer"].eq(False).all()
    assert canonical.query_regions["eligible_for_fpps"].eq(False).all()
    assert canonical.query_regions["eligible_for_warning"].eq(False).all()

    # The provisional assignment file cannot be reused without its required
    # allowlist to silently restore the historical whole-tile behavior.
    with pytest.raises(ManifestContractError, match="require supported_query_derivation"):
        build_grid_manifests(
            (event,),
            support.provisional_tile_assignments,
            sources,
            receipt,
            allow_ungoverned_fixture=True,
        )

    validated = validate_grid_manifests(
        (event,),
        sources,
        canonical.tiles,
        canonical.query_regions,
        receipt,
        allow_ungoverned_fixture=True,
        supported_query_derivation=support.derivation,
    )
    assert len(validated.query_regions) == 63

    # An allowlisted canonical manifest cannot be silently reinterpreted under
    # the historical full-tile contract.
    with pytest.raises(ManifestContractError, match="lineage columns require"):
        validate_grid_manifests(
            (event,),
            sources,
            canonical.tiles,
            canonical.query_regions,
            receipt,
            allow_ungoverned_fixture=True,
        )


def test_pending_rights_block_before_missing_allowlist_is_opened(
    tmp_path: Path,
) -> None:
    cleared_event = _event(cleared=True)
    cleared_sources = _sources(cleared=True)
    sar = _write_sar(tmp_path / "sar", cleared_event)
    receipt = _processing_receipt(
        tmp_path / "receipt-evidence",
        cleared_event,
        cleared_sources,
        sar,
    )
    pending_event = _event(cleared=False)
    pending_sources = _sources(cleared=False)

    with pytest.raises(ManifestContractError, match="not rights-cleared") as caught:
        build_grid_manifests(
            (pending_event,),
            (_assignment(),),
            pending_sources,
            receipt,
            allow_ungoverned_fixture=True,
            supported_query_derivation=tmp_path / "missing-allowlist.json",
        )
    assert "supported-query" not in str(caught.value).lower()


def test_resigned_wgs84_evidence_cannot_replace_canonical_query_geometry(
    tmp_path: Path,
) -> None:
    event, sources, receipt, support = _allowlist_fixture(tmp_path)
    queries = pd.read_csv(support.supported_queries)
    queries.loc[0, "wgs84_min_longitude"] += 0.0001
    queries.to_csv(support.supported_queries, index=False)
    manifest = json.loads(support.derivation.read_text(encoding="utf-8"))
    manifest["outputs"]["supported_queries"]["sha256"] = _sha256(
        support.supported_queries
    )
    manifest["manifest_sha256"] = _canonical_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    support.derivation.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ManifestContractError, match="non-canonical wgs84"):
        build_grid_manifests(
            (event,),
            support.provisional_tile_assignments,
            sources,
            receipt,
            allow_ungoverned_fixture=True,
            supported_query_derivation=support.derivation,
        )


def test_resigned_aoi_requires_explicit_cross_border_boolean(tmp_path: Path) -> None:
    event, sources, receipt, support = _allowlist_fixture(tmp_path)
    manifest = json.loads(support.derivation.read_text(encoding="utf-8"))
    manifest["approved_aoi_wgs84"]["cross_border_context_included"] = "true"
    manifest["manifest_sha256"] = _canonical_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    support.derivation.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(ManifestContractError, match="explicit JSON boolean"):
        build_grid_manifests(
            (event,),
            support.provisional_tile_assignments,
            sources,
            receipt,
            allow_ungoverned_fixture=True,
            supported_query_derivation=support.derivation,
        )


def _allowlist_fixture(tmp_path: Path):
    event = _event(cleared=True)
    events_path = _write_events(tmp_path / "events.csv", event)
    sar = _write_sar(tmp_path / "sar", event)
    sources = _sources(cleared=True)
    receipt = _processing_receipt(tmp_path / "receipt-evidence", event, sources, sar)
    support = build_and_write_supported_query_pool(
        event_registry_path=events_path,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        approved_aoi=_covering_aoi(),
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )
    return event, sources, receipt, support


def _event(*, cleared: bool) -> EventRecord:
    return EventRecord.from_mapping(
        {
            "event_id": EVENT_ID,
            "event_name": "Synthetic supported-query allowlist test",
            "country": "Thailand",
            "study_area": "Synthetic UTM cells only",
            "event_start_utc": "2024-09-14T00:00:00Z",
            "event_end_utc": "2024-09-16T00:00:00Z",
            "pre_acquisition_utc": "2024-09-03T23:16:00Z",
            "post_acquisition_utc": "2024-09-15T23:16:00Z",
            "analysis_crs": "EPSG:32647",
            "analysis_resolution_m": RESOLUTION,
            "grid_origin_x": 0,
            "grid_origin_y": 0,
            "tile_size_pixels": SIZE,
            "query_size_pixels": 32,
            "dataset_role": "training_and_query_pool",
            "label_status": "unreviewed",
            "source_rights_status": "confirmed" if cleared else "pending",
            "processing_allowed": cleared,
            "ml_label_derivation_allowed": cleared,
            "validation_allowed": cleared,
            "source_timestamp": "2024-09-20T00:00:00Z",
            "confidence_class": "low",
            "assumptions": "Synthetic contract fixture; not observed flood truth.",
        }
    )


def _sources(*, cleared: bool) -> tuple[SourceAssetRecord, ...]:
    rows: list[SourceAssetRecord] = []
    for prefix, acquisition, temporal_role, product_id, source_hash in (
        ("pre", "2024-09-03T23:16:00Z", "pre_event", "S1-PRE", "a" * 64),
        (
            "event",
            "2024-09-15T23:16:00Z",
            "event_time",
            "S1-EVENT",
            "b" * 64,
        ),
    ):
        for polarization in ("VV", "VH"):
            rows.append(
                SourceAssetRecord.from_mapping(
                    {
                        "asset_id": f"{prefix}_{polarization.lower()}",
                        "event_id": EVENT_ID,
                        "sensor": "C-band SAR",
                        "platform": "Sentinel-1A",
                        "product_id": product_id,
                        "acquisition_time_utc": acquisition,
                        "event_relative_role": temporal_role,
                        "orbit_direction": "descending",
                        "relative_orbit": "135",
                        "polarizations": polarization,
                        "processing_level": "synthetic aligned Gamma0 dB",
                        "crs": "EPSG:32647",
                        "pixel_spacing_m": RESOLUTION,
                        "local_path_hint": f"synthetic/{prefix}_{polarization}.tif",
                        "sha256": source_hash,
                        "sha256_status": "verified",
                        "license_status": "confirmed" if cleared else "pending",
                        "processing_allowed": cleared,
                        "ml_label_derivation_allowed": cleared,
                        "redistribution_status": "reference_only",
                        "georegistration_method": "synthetic phase correlation",
                        "georegistration_error_pixels": 0.25,
                        "source_timestamp": "2024-09-20T00:00:00Z",
                        "confidence_class": "low",
                        "assumptions": "Synthetic source metadata only.",
                    }
                )
            )
    return tuple(rows)


def _write_events(path: Path, event: EventRecord) -> Path:
    pd.DataFrame([event.as_manifest_row()]).to_csv(path, index=False)
    return path


def _write_sar(directory: Path, event: EventRecord) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    arrays = {
        "pre_vv_db": np.full((SIZE, SIZE), -10.0, dtype="float32"),
        "event_vv_db": np.full((SIZE, SIZE), -12.0, dtype="float32"),
        "pre_vh_db": np.full((SIZE, SIZE), -16.0, dtype="float32"),
        "event_vh_db": np.full((SIZE, SIZE), -18.0, dtype="float32"),
    }
    # Invalidate one cell in the north-west query core.
    arrays["event_vh_db"][0, 0] = -9999.0
    paths: dict[str, Path] = {}
    for role, values in arrays.items():
        path = directory / f"{role}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=SIZE,
            height=SIZE,
            count=1,
            dtype="float32",
            crs=event.analysis_crs,
            transform=TRANSFORM,
            nodata=-9999.0,
        ) as dataset:
            dataset.write(values, 1)
            dataset.update_tags(
                grid_contract_sha256=event.grid.contract_sha256,
                floodguard_role=role,
                source_product_id="S1-PRE" if role.startswith("pre_") else "S1-EVENT",
                query_model_only="true",
                eligible_for_decision_layer="false",
                eligible_for_fpps="false",
                eligible_for_warning="false",
            )
        paths[role] = path
    return paths


def _processing_receipt(
    directory: Path,
    event: EventRecord,
    sources: tuple[SourceAssetRecord, ...],
    sar: dict[str, Path],
) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    registration = directory / "registration.json"
    registration.write_text('{"synthetic":true}\n', encoding="utf-8")
    rows: list[dict[str, object]] = []
    for source in sources:
        prefix = "pre" if source.event_relative_role == "pre_event" else "event"
        role = f"{prefix}_{source.polarizations.lower()}_db"
        coverage = directory / f"{source.asset_id}_coverage.json"
        valid = directory / f"{source.asset_id}_valid.json"
        coverage.write_text('{"coverage_fraction":1.0}\n', encoding="utf-8")
        valid.write_text('{"valid_data_fraction":0.99}\n', encoding="utf-8")
        rows.append(
            {
                "asset_id": source.asset_id,
                "processed_artifact_id": f"PROC-{source.asset_id}",
                "processed_file_path": str(sar[role]),
                "processed_file_sha256": _sha256(sar[role]),
                "processing_software": "synthetic_fixture",
                "processing_software_version": "1.0-test",
                "rtc_terrain_correction_method": "synthetic RTC fixture",
                "output_crs": event.analysis_crs,
                "affine_a": RESOLUTION,
                "affine_b": 0.0,
                "affine_c": LEFT,
                "affine_d": 0.0,
                "affine_e": -RESOLUTION,
                "affine_f": TOP,
                "width_pixels": SIZE,
                "height_pixels": SIZE,
                "pixel_size_x_m": RESOLUTION,
                "pixel_size_y_m": RESOLUTION,
                "nodata_convention": "synthetic nodata=-9999; no imputation",
                "resampling_method": "synthetic fixture",
                "coverage_fraction": 1.0,
                "valid_data_fraction": (SIZE * SIZE - 1) / (SIZE * SIZE),
                "coverage_evidence_path": str(coverage),
                "coverage_evidence_sha256": _sha256(coverage),
                "valid_data_evidence_path": str(valid),
                "valid_data_evidence_sha256": _sha256(valid),
                "registration_method": "synthetic phase correlation",
                "registration_error_pixels": 0.25,
                "registration_evidence_path": str(registration),
                "registration_evidence_sha256": _sha256(registration),
                "grid_contract_sha256": event.grid.contract_sha256,
                "source_timestamp": "2024-09-21T00:00:00Z",
                "confidence_class": "low",
                "assumptions": "Synthetic byte-backed processing fixture.",
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
            }
        )
    return build_processing_alignment_receipt(
        (event,),
        sources,
        pd.DataFrame(rows, columns=PROCESSING_EVIDENCE_COLUMNS),
        allow_ungoverned_fixture=True,
    )


def _assignment() -> dict[str, object]:
    return {
        "event_id": EVENT_ID,
        "x_index": 195,
        "y_index": 879,
        "dataset_role": "training_and_query_pool",
        "overlap_group_id": "SYNTHETIC-BLOCK",
        "valid_data_fraction": 0.99,
        "feature_schema_version": "sar_change_v2",
        "source_timestamp": "2026-07-10T00:00:00Z",
        "confidence_class": "low",
        "assumptions": "Synthetic parent tile only.",
    }


def _covering_aoi() -> ApprovedAoiWgs84:
    min_y = TOP - SIZE * RESOLUTION
    max_x = LEFT + SIZE * RESOLUTION
    longitudes, latitudes = transform(
        "EPSG:32647",
        "EPSG:4326",
        [LEFT, LEFT, max_x, max_x],
        [min_y, TOP, min_y, TOP],
    )
    return ApprovedAoiWgs84(
        min_longitude=min(longitudes) - 0.001,
        min_latitude=min(latitudes) - 0.001,
        max_longitude=max(longitudes) + 0.001,
        max_latitude=max(latitudes) + 0.001,
        cross_border_context_included=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
