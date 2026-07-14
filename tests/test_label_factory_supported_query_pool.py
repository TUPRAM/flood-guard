from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from floodguard.label_factory.context_alignment import (
    CONTEXT_ALIGNMENT_MANIFEST_SCHEMA,
)
from floodguard.label_factory.event_registry import EventRecord
from floodguard.label_factory.supported_query_pool import (
    ApprovedAoiWgs84,
    SupportedQueryPoolError,
    build_and_write_supported_query_pool,
    load_supported_query_derivation,
)

rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin
from rasterio.warp import transform


EVENT_ID = "TH-MAESAI-2024-09"
RESOLUTION = 10.0
TILE_SIZE = 256
QUERY_SIZE = 32
LEFT = 499_200.0  # 195 * 2,560: exact registered storage-tile edge.
TOP = 2_252_800.0
WIDTH = 512
HEIGHT = 256
GRID_TRANSFORM = from_origin(LEFT, TOP, RESOLUTION, RESOLUTION)


def test_build_support_pool_keeps_partial_tile_queries_provisional(
    tmp_path: Path,
) -> None:
    events = _write_event_registry(tmp_path / "events.csv", rights_confirmed=True)
    arrays = _sar_arrays()
    # One missing observation invalidates exactly one 32x32 query core in the
    # second tile, without being silently imputed.
    arrays["event_vh_db"][0, TILE_SIZE] = -9999.0
    sar = _write_sar_set(tmp_path / "sar", arrays)
    context = _write_context_package(tmp_path / "context")
    aoi = _covering_aoi()

    paths = build_and_write_supported_query_pool(
        event_registry_path=events,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        pre_layover_shadow_path=sar["pre_layover_shadow_mask"],
        event_layover_shadow_path=sar["event_layover_shadow_mask"],
        context_alignment_manifest_path=context,
        approved_aoi=aoi,
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )

    tiles = pd.read_csv(paths.tile_support)
    assignments = pd.read_csv(paths.provisional_tile_assignments)
    queries = pd.read_csv(paths.supported_queries)
    derivation = load_supported_query_derivation(paths.derivation)

    assert len(tiles) == 2
    assert len(assignments) == 2
    assert len(queries) == 127
    assert tiles["joint_valid_cell_count"].tolist() == [65_536, 65_535]
    assert tiles["fully_supported_query_core_count"].tolist() == [64, 63]
    assert tiles["eligible_for_tile_assignments_input"].tolist() == [True, True]
    assert tiles[
        "eligible_for_whole_tile_manifest_without_allowlist"
    ].tolist() == [True, False]
    assert assignments["valid_data_fraction"].tolist() == [
        1.0,
        round(65_535 / 65_536, 12),
    ]
    assert assignments["supported_query_allowlist_required"].eq(True).all()
    assert assignments["processing_alignment_receipt_validated"].eq(False).all()
    assert assignments["source_rights_gate_validated"].eq(False).all()
    assert assignments[
        "eligible_for_canonical_manifest_without_downstream_gates"
    ].eq(False).all()

    assert queries["valid_data_fraction"].eq(1.0).all()
    assert queries["fully_within_approved_aoi"].eq(True).all()
    assert queries["core_clipped"].eq(False).all()
    assert queries["processing_alignment_receipt_validated"].eq(False).all()
    assert queries["eligible_for_human_annotation"].eq(False).all()
    assert queries["eligible_for_active_selection"].eq(False).all()
    assert queries["eligible_for_review_queue"].eq(False).all()
    assert queries["query_model_only"].eq(True).all()
    assert queries["eligible_for_decision_layer"].eq(False).all()
    assert queries["eligible_for_fpps"].eq(False).all()
    assert queries["eligible_for_warning"].eq(False).all()
    assert queries["eligible_for_current_full_tile_manifest_bridge"].sum() == 64
    assert queries["eligible_for_supported_query_allowlist_bridge"].sum() == 127

    # Static context is useful for model-independent sampling, but it remains
    # context rather than flood truth. WorldCover water (80) is not merged into
    # JRC permanent-water context by these rules.
    assert set(queries["round0_stratum"]).issuperset(
        {"permanent_water_edge", "urban", "steep_terrain", "forest", "cropland"}
    )
    assert queries["round0_stratum_source"].eq(
        "aligned_static_context_no_weak_labels"
    ).all()
    assert derivation["context_strata"]["uses_weak_or_reference_labels"] is False
    assert "worldcover_water_fraction" in queries
    assert derivation["context_strata"]["context_derivation_parameters"][
        "permanent_occurrence_threshold_pct"
    ] == 50.0
    assert derivation["processing_alignment_receipt_consumed"] is False
    assert derivation["source_rights_gate_evaluated"] is False
    assert derivation["canonical_manifest_status"] == (
        "not_canonical_provisional_support_only"
    )
    assert derivation["manifest_sha256"] == _canonical_sha256(
        {key: value for key, value in derivation.items() if key != "manifest_sha256"}
    )


def test_aoi_containment_excludes_complete_cores_without_clipping(
    tmp_path: Path,
) -> None:
    events = _write_event_registry(tmp_path / "events.csv", rights_confirmed=False)
    sar = _write_sar_set(tmp_path / "sar", _sar_arrays())
    first_tile_aoi = _aoi_for_projected_bounds(
        LEFT,
        TOP - TILE_SIZE * RESOLUTION,
        LEFT + TILE_SIZE * RESOLUTION,
        TOP,
        padding_degrees=1e-8,
    )

    paths = build_and_write_supported_query_pool(
        event_registry_path=events,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        approved_aoi=first_tile_aoi,
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )

    tiles = pd.read_csv(paths.tile_support)
    queries = pd.read_csv(paths.supported_queries)
    assignments = pd.read_csv(paths.provisional_tile_assignments)
    assert len(assignments) == 1
    assert len(queries) == 64
    assert tiles["joint_valid_fraction"].eq(1.0).all()
    assert tiles["tile_fully_within_approved_aoi"].tolist() == [True, False]
    assert queries["wgs84_min_longitude"].ge(
        first_tile_aoi.min_longitude - 1e-10
    ).all()
    assert queries["wgs84_max_longitude"].le(
        first_tile_aoi.max_longitude + 1e-10
    ).all()
    assert queries["round0_stratum"].eq("unassigned").all()
    assert queries["round0_stratum_assignment_status"].eq(
        "unassigned_context_not_provided"
    ).all()
    assert queries["eligible_for_round0_stratified_selection"].eq(False).all()


def test_paired_masks_are_required_and_nonzero_mask_is_unsupported(
    tmp_path: Path,
) -> None:
    events = _write_event_registry(tmp_path / "events.csv", rights_confirmed=False)
    sar = _write_sar_set(tmp_path / "sar", _sar_arrays(masked_cell=(5, 5)))

    with pytest.raises(SupportedQueryPoolError, match="masks are paired"):
        build_and_write_supported_query_pool(
            event_registry_path=events,
            event_id=EVENT_ID,
            pre_vv_path=sar["pre_vv_db"],
            event_vv_path=sar["event_vv_db"],
            pre_vh_path=sar["pre_vh_db"],
            event_vh_path=sar["event_vh_db"],
            pre_layover_shadow_path=sar["pre_layover_shadow_mask"],
            approved_aoi=_covering_aoi(),
            output_directory=tmp_path / "blocked-pair",
            created_at_utc="2026-07-10T00:00:00Z",
        )

    paths = build_and_write_supported_query_pool(
        event_registry_path=events,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        pre_layover_shadow_path=sar["pre_layover_shadow_mask"],
        event_layover_shadow_path=sar["event_layover_shadow_mask"],
        approved_aoi=_covering_aoi(),
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )
    tiles = pd.read_csv(paths.tile_support)
    queries = pd.read_csv(paths.supported_queries)
    assert tiles.loc[0, "joint_valid_cell_count"] == 65_535
    assert len(queries) == 127


def test_grid_tag_and_derivation_tampering_fail_closed(tmp_path: Path) -> None:
    events = _write_event_registry(tmp_path / "events.csv", rights_confirmed=False)
    sar = _write_sar_set(tmp_path / "sar", _sar_arrays())
    with rasterio.open(sar["event_vv_db"], "r+") as dataset:
        dataset.update_tags(grid_contract_sha256="0" * 64)

    with pytest.raises(SupportedQueryPoolError, match="grid_contract_sha256"):
        build_and_write_supported_query_pool(
            event_registry_path=events,
            event_id=EVENT_ID,
            pre_vv_path=sar["pre_vv_db"],
            event_vv_path=sar["event_vv_db"],
            pre_vh_path=sar["pre_vh_db"],
            event_vh_path=sar["event_vh_db"],
            approved_aoi=_covering_aoi(),
            output_directory=tmp_path / "blocked-grid",
            created_at_utc="2026-07-10T00:00:00Z",
        )

    sar = _write_sar_set(tmp_path / "sar-good", _sar_arrays())
    paths = build_and_write_supported_query_pool(
        event_registry_path=events,
        event_id=EVENT_ID,
        pre_vv_path=sar["pre_vv_db"],
        event_vv_path=sar["event_vv_db"],
        pre_vh_path=sar["pre_vh_db"],
        event_vh_path=sar["event_vh_db"],
        approved_aoi=_covering_aoi(),
        output_directory=tmp_path / "support",
        created_at_utc="2026-07-10T00:00:00Z",
    )
    manifest = json.loads(paths.derivation.read_text(encoding="utf-8"))
    manifest["eligible_for_fpps"] = True
    paths.derivation.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SupportedQueryPoolError, match="self-hash mismatch"):
        load_supported_query_derivation(paths.derivation)


def _event_record(*, rights_confirmed: bool) -> EventRecord:
    return EventRecord.from_mapping(
        {
            "event_id": EVENT_ID,
            "event_name": "Mae Sai support bridge fixture",
            "country": "Thailand",
            "study_area": "Synthetic UTM fixture",
            "event_start_utc": "2024-09-14T00:00:00Z",
            "event_end_utc": "2024-09-16T00:00:00Z",
            "pre_acquisition_utc": "2024-09-03T23:16:00Z",
            "post_acquisition_utc": "2024-09-15T23:16:00Z",
            "analysis_crs": "EPSG:32647",
            "analysis_resolution_m": RESOLUTION,
            "grid_origin_x": 0,
            "grid_origin_y": 0,
            "tile_size_pixels": TILE_SIZE,
            "query_size_pixels": QUERY_SIZE,
            "dataset_role": "training_and_query_pool",
            "label_status": "unreviewed",
            "source_rights_status": "confirmed" if rights_confirmed else "pending",
            "processing_allowed": rights_confirmed,
            "ml_label_derivation_allowed": rights_confirmed,
            "validation_allowed": rights_confirmed,
            "source_timestamp": "2024-09-20T00:00:00Z",
            "confidence_class": "medium",
            "assumptions": "Synthetic test geometry only; not flood truth.",
        }
    )


def _write_event_registry(path: Path, *, rights_confirmed: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([_event_record(rights_confirmed=rights_confirmed).as_manifest_row()]).to_csv(
        path, index=False
    )
    return path


def _sar_arrays(
    *, masked_cell: tuple[int, int] | None = None
) -> dict[str, np.ndarray]:
    arrays = {
        "pre_vv_db": np.full((HEIGHT, WIDTH), -10.0, dtype="float32"),
        "event_vv_db": np.full((HEIGHT, WIDTH), -12.0, dtype="float32"),
        "pre_vh_db": np.full((HEIGHT, WIDTH), -16.0, dtype="float32"),
        "event_vh_db": np.full((HEIGHT, WIDTH), -18.0, dtype="float32"),
        "pre_layover_shadow_mask": np.zeros((HEIGHT, WIDTH), dtype="uint8"),
        "event_layover_shadow_mask": np.zeros((HEIGHT, WIDTH), dtype="uint8"),
    }
    if masked_cell is not None:
        arrays["event_layover_shadow_mask"][masked_cell] = 1
    return arrays


def _write_sar_set(
    directory: Path,
    arrays: dict[str, np.ndarray],
) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    contract_hash = _event_record(rights_confirmed=False).grid.contract_sha256
    paths: dict[str, Path] = {}
    for role, values in arrays.items():
        path = directory / f"{role}.tif"
        nodata = 255 if values.dtype == np.dtype("uint8") else -9999.0
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=WIDTH,
            height=HEIGHT,
            count=1,
            dtype=str(values.dtype),
            crs="EPSG:32647",
            transform=GRID_TRANSFORM,
            nodata=nodata,
        ) as dataset:
            dataset.write(values, 1)
            dataset.update_tags(
                grid_contract_sha256=contract_hash,
                floodguard_role=role,
                source_product_id=(
                    "S1-PRE" if role.startswith("pre_") else "S1-EVENT"
                ),
                query_model_only="true",
                eligible_for_decision_layer="false",
                eligible_for_fpps="false",
                eligible_for_warning="false",
            )
        paths[role] = path
    return paths


def _write_context_package(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    land_cover = np.full((HEIGHT, WIDTH), 80, dtype="uint8")
    permanent = np.zeros((HEIGHT, WIDTH), dtype="uint8")
    slope = np.zeros((HEIGHT, WIDTH), dtype="float32")

    # First tile, row 0: permanent edge, urban, steep, forest, cropland, then
    # ordinary/source code 80. Each query is exactly 32 columns.
    permanent[0, 0] = 1
    land_cover[0:QUERY_SIZE, QUERY_SIZE : 2 * QUERY_SIZE] = 50
    slope[0:QUERY_SIZE, 2 * QUERY_SIZE : 3 * QUERY_SIZE] = 20.0
    land_cover[0:QUERY_SIZE, 3 * QUERY_SIZE : 4 * QUERY_SIZE] = 10
    land_cover[0:QUERY_SIZE, 4 * QUERY_SIZE : 5 * QUERY_SIZE] = 40

    definitions = {
        "land_cover": (land_cover, 0, ["worldcover"]),
        "permanent_water_context": (
            permanent,
            255,
            ["jrc_occurrence", "jrc_seasonality"],
        ),
        "slope": (slope, -9999.0, ["copernicus_dem"]),
    }
    layers: list[dict[str, object]] = []
    for role, (values, nodata, source_roles) in definitions.items():
        path = directory / f"{role}.tif"
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=WIDTH,
            height=HEIGHT,
            count=1,
            dtype=str(values.dtype),
            crs="EPSG:32647",
            transform=GRID_TRANSFORM,
            nodata=nodata,
        ) as dataset:
            dataset.write(values, 1)
        source_hashes = {source: hashlib.sha256(source.encode()).hexdigest() for source in source_roles}
        layers.append(
            {
                "layer_role": role,
                "path_hint": path.name,
                "processed_layer_sha256": _file_sha256(path),
                "source_roles": source_roles,
                "source_sha256s": source_hashes,
                "derivation_method": "synthetic_context_fixture",
            }
        )
    payload = {
        "artifact_schema": CONTEXT_ALIGNMENT_MANIFEST_SCHEMA,
        "builder": "floodguard.label_factory.context_alignment@v1",
        "target_grid": {},
        "derivation_parameters": {
            "permanent_occurrence_threshold_pct": 50.0,
            "permanent_seasonality_threshold_months": 10,
            "permanent_water_operator": "logical_and",
        },
        "source_inputs": [
            {"source_role": "worldcover"},
            {"source_role": "jrc_occurrence"},
            {"source_role": "jrc_seasonality"},
            {"source_role": "copernicus_dem"},
        ],
        "layers": layers,
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
    }
    manifest = {**payload, "manifest_sha256": _canonical_sha256(payload)}
    path = directory / "context_alignment_manifest.json"
    path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _covering_aoi() -> ApprovedAoiWgs84:
    return _aoi_for_projected_bounds(
        LEFT,
        TOP - HEIGHT * RESOLUTION,
        LEFT + WIDTH * RESOLUTION,
        TOP,
        padding_degrees=0.001,
    )


def _aoi_for_projected_bounds(
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    *,
    padding_degrees: float,
) -> ApprovedAoiWgs84:
    points_x: list[float] = []
    points_y: list[float] = []
    for index in range(257):
        fraction = index / 256
        x = min_x + (max_x - min_x) * fraction
        y = min_y + (max_y - min_y) * fraction
        points_x.extend((x, x, min_x, max_x))
        points_y.extend((min_y, max_y, y, y))
    longitudes, latitudes = transform(
        "EPSG:32647", "EPSG:4326", points_x, points_y
    )
    return ApprovedAoiWgs84(
        min_longitude=min(longitudes) - padding_degrees,
        min_latitude=min(latitudes) - padding_degrees,
        max_longitude=max(longitudes) + padding_degrees,
        max_latitude=max(latitudes) + padding_degrees,
        cross_border_context_included=True,
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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
