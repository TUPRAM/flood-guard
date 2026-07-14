from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.event_registry import (
    EventRecord,
    EventRegistryError,
    MAX_GEOREGISTRATION_ERROR_PIXELS,
    SourceAssetRecord,
    load_events,
    load_source_assets,
    validate_event_source_registry,
)


def event_row(
    *, role: str = "training_and_query_pool"
) -> dict[str, object]:
    return {
        "event_id": "TH-MAESAI-2024-09",
        "event_name": "Mae Sai September 2024 contract fixture",
        "country": "Thailand",
        "study_area": "Synthetic contract bounds only",
        "event_start_utc": "2024-09-10T00:00:00Z",
        "event_end_utc": "2024-09-15T23:59:59Z",
        "pre_acquisition_utc": "2024-09-01T12:00:00Z",
        "post_acquisition_utc": "2024-09-12T12:00:00Z",
        "analysis_crs": "EPSG:32647",
        "analysis_resolution_m": 10,
        "grid_origin_x": 320000,
        "grid_origin_y": 2200000,
        "tile_size_pixels": 256,
        "query_size_pixels": 64,
        "dataset_role": role,
        "label_status": "unreviewed",
        "source_rights_status": "confirmed",
        "processing_allowed": True,
        "ml_label_derivation_allowed": True,
        "validation_allowed": True,
        "source_timestamp": "2024-09-20T00:00:00Z",
        "confidence_class": "medium",
        "assumptions": "Metadata-only open fixture; no claim of flood truth.",
    }


def source_row(
    *,
    asset_id: str = "S1-PRE-FIXTURE",
    acquisition: str = "2024-09-01T12:00:00Z",
    event_relative_role: str = "pre_event",
    sha: str = "a" * 64,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "event_id": "TH-MAESAI-2024-09",
        "sensor": "SAR",
        "platform": "Sentinel-1",
        "product_id": f"PRODUCT-{asset_id}",
        "acquisition_time_utc": acquisition,
        "event_relative_role": event_relative_role,
        "orbit_direction": "descending",
        "relative_orbit": "142",
        "polarizations": "VV,VH",
        "processing_level": "terrain_corrected_aligned_fixture",
        "crs": "EPSG:32647",
        "pixel_spacing_m": 10,
        "local_path_hint": f"outside_git/{asset_id}.tif",
        "sha256": sha,
        "sha256_status": "recorded",
        "license_status": "confirmed",
        "processing_allowed": True,
        "ml_label_derivation_allowed": True,
        "redistribution_status": "reference_only",
        "georegistration_method": "fixture_control_points",
        "georegistration_error_pixels": 0.25,
        "source_timestamp": "2024-09-20T00:00:00Z",
        "confidence_class": "medium",
        "assumptions": "Checksum is fixture metadata, not real Mae Sai imagery.",
    }


def valid_sources() -> list[dict[str, object]]:
    return [
        source_row(),
        source_row(
            asset_id="S1-EVENT-FIXTURE",
            acquisition="2024-09-12T12:00:00Z",
            event_relative_role="event_time",
            sha="b" * 64,
        ),
    ]


def test_typed_event_and_source_records_preserve_grid_and_provenance() -> None:
    event = EventRecord.from_mapping(event_row())
    asset = SourceAssetRecord.from_mapping(source_row())

    assert event.dataset_role is DatasetRole.TRAINING_AND_QUERY_POOL
    assert event.grid.grid_id.startswith("UTM47N_10M_G")
    assert event.grid.origin_x == 320000
    assert event.grid.tile_size_cells == 256
    assert event.as_manifest_row()["source_timestamp"].endswith("Z")
    assert asset.crs == event.analysis_crs
    assert asset.sha256 == "a" * 64
    assert asset.as_manifest_row()["acquisition_time_utc"].endswith("Z")


def test_loaders_accept_dataframes_and_csv_and_reject_duplicate_ids(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "events.csv"
    pd.DataFrame([event_row()]).to_csv(events_path, index=False)

    assert load_events(events_path)[0].event_id == "TH-MAESAI-2024-09"
    assert len(load_source_assets(pd.DataFrame(valid_sources()))) == 2
    with pytest.raises(EventRegistryError, match="Duplicate event_id"):
        load_events([event_row(), event_row()])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("analysis_crs", "EPSG:4326", "projected"),
        ("analysis_resolution_m", 0, "positive"),
        ("query_size_pixels", 60, "must divide"),
        ("event_start_utc", "2024-09-10T07:00:00+07:00", "UTC"),
        ("pre_acquisition_utc", "2024-09-11T00:00:00Z", "before event_start"),
        ("confidence_class", "unknown", "high, medium, or low"),
    ],
)
def test_event_contract_rejects_unsafe_grid_time_or_provenance(
    field: str, value: object, message: str
) -> None:
    row = event_row()
    row[field] = value
    with pytest.raises(EventRegistryError, match=message):
        EventRecord.from_mapping(row)


@pytest.mark.parametrize(
    "path_hint",
    [
        r"C:\Users\person\imagery.tif",
        "/home/person/imagery.tif",
        "../imagery.tif",
        "file:///data/imagery.tif",
        "~/imagery.tif",
    ],
)
def test_source_assets_never_store_absolute_or_traversing_paths(
    path_hint: str,
) -> None:
    row = source_row()
    row["local_path_hint"] = path_hint
    with pytest.raises(EventRegistryError, match="redacted relative hint"):
        SourceAssetRecord.from_mapping(row)


def test_source_requires_checksum_alignment_and_noncontradictory_rights() -> None:
    bad_checksum = source_row()
    bad_checksum["sha256"] = "not-a-checksum"
    with pytest.raises(EventRegistryError, match="64 hexadecimal"):
        SourceAssetRecord.from_mapping(bad_checksum)

    unresolved = source_row()
    unresolved["license_status"] = "unresolved"
    with pytest.raises(EventRegistryError, match="contradicts"):
        SourceAssetRecord.from_mapping(unresolved)

    ambiguous_bool = source_row()
    ambiguous_bool["processing_allowed"] = 1
    with pytest.raises(EventRegistryError, match="exactly true or false"):
        SourceAssetRecord.from_mapping(ambiguous_bool)


def test_cross_registry_requires_complete_aligned_rights_cleared_pair() -> None:
    events = load_events([event_row()])
    sources = load_source_assets(valid_sources())
    validate_event_source_registry(events, sources)

    with pytest.raises(EventRegistryError, match="post_acquisition_utc"):
        validate_event_source_registry(events, sources[:1])

    misaligned_rows = deepcopy(valid_sources())
    misaligned_rows[1]["pixel_spacing_m"] = 20
    with pytest.raises(EventRegistryError, match="pixel spacing"):
        validate_event_source_registry(events, load_source_assets(misaligned_rows))

    blocked_rows = deepcopy(valid_sources())
    blocked_rows[1]["processing_allowed"] = False
    blocked_rows[1]["ml_label_derivation_allowed"] = False
    with pytest.raises(EventRegistryError, match="not rights-cleared"):
        validate_event_source_registry(events, load_source_assets(blocked_rows))


def test_canonical_alignment_enforces_georegistration_error_ceiling() -> None:
    events = load_events([event_row()])
    boundary_rows = deepcopy(valid_sources())
    boundary_rows[1]["georegistration_error_pixels"] = (
        MAX_GEOREGISTRATION_ERROR_PIXELS
    )
    validate_event_source_registry(events, load_source_assets(boundary_rows))

    over_limit_rows = deepcopy(valid_sources())
    over_limit_rows[1]["georegistration_error_pixels"] = (
        MAX_GEOREGISTRATION_ERROR_PIXELS + 0.01
    )
    over_limit_sources = load_source_assets(over_limit_rows)
    with pytest.raises(EventRegistryError, match="georegistration error.*exceeds"):
        validate_event_source_registry(events, over_limit_sources)

    # Planning-only registry inspection may retain a measured poor-alignment
    # source, but it cannot pass the canonical build gate above.
    validate_event_source_registry(
        events,
        over_limit_sources,
        require_canonical_alignment=False,
    )


@pytest.mark.parametrize(
    ("field", "mismatched_value"),
    [
        ("orbit_direction", "ascending"),
        ("relative_orbit", "143"),
        ("polarizations", "VV"),
    ],
)
def test_declared_pre_post_sar_pair_rejects_incompatible_acquisition_metadata(
    field: str, mismatched_value: str
) -> None:
    rows = deepcopy(valid_sources())
    rows[1][field] = mismatched_value

    with pytest.raises(EventRegistryError, match=field):
        validate_event_source_registry(
            load_events([event_row()]),
            load_source_assets(rows),
        )


def test_sar_pair_compatibility_normalizes_polarization_order_and_orbit_format() -> None:
    rows = deepcopy(valid_sources())
    rows[0]["relative_orbit"] = "0142"
    rows[1]["polarizations"] = "vh; vv"

    validate_event_source_registry(
        load_events([event_row()]),
        load_source_assets(rows),
    )


def test_geographic_test_event_requires_explicit_validation_rights() -> None:
    row = event_row(role="untouched_geographic_test")
    row["validation_allowed"] = False
    event = EventRecord.from_mapping(row)

    with pytest.raises(EventRegistryError, match="validation_allowed=false"):
        validate_event_source_registry([event], load_source_assets(valid_sources()))
