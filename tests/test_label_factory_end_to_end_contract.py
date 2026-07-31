from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.decision_safety import (
    DecisionInputSafetyError,
    reject_label_factory_query_input,
)
from floodguard.label_factory.acquisition import (
    select_active_learning_manifest,
    select_round_zero_manifest,
)
from floodguard.label_factory.candidate_builder import (
    QUERY_METADATA_COLUMNS,
    build_region_candidate_manifest,
)
from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY
from floodguard.label_factory.event_registry import (
    EventRecord,
    SourceAssetRecord,
    validate_event_source_registry,
)
from floodguard.label_factory.manifests import (
    build_grid_manifests,
    validate_grid_manifests,
)
from floodguard.label_factory.processing_alignment import processing_assets_by_id
from floodguard.label_factory.review_bundle import (
    SENSITIVE_REVIEW_COLUMNS,
    ReviewPurpose,
    build_annotation_template,
    build_blinded_review_manifest,
    write_blinded_review_bundle,
)
from floodguard.road_risk import score_road_disruption
from floodguard.scoring import score_subdistricts
from label_factory_processing_fixtures import synthetic_processing_receipt


EVENT_ID = "TH-SYNTHETIC-2024-09"
ROUND_ZERO_STRATA = (
    "weak_positive_interior",
    "weak_polygon_boundary",
    "likely_dry_land",
    "permanent_water_edge",
    "urban",
    "cropland_wet_soil",
    "forest_flooded_vegetation",
    "steep_terrain",
    "random_ordinary_landscape",
)


def _event() -> EventRecord:
    return EventRecord.from_mapping(
        {
            "event_id": EVENT_ID,
            "event_name": "Synthetic end-to-end label-factory contract",
            "country": "Thailand",
            "study_area": "Synthetic projected cells only",
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
            "dataset_role": "training_and_query_pool",
            "label_status": "unreviewed",
            "source_rights_status": "confirmed",
            "processing_allowed": True,
            "ml_label_derivation_allowed": True,
            "validation_allowed": True,
            "source_timestamp": "2024-09-20T00:00:00Z",
            "confidence_class": "low",
            "assumptions": (
                "Synthetic contract fixture only; it is not observed flood truth."
            ),
        }
    )


def _source_asset(
    *,
    role: str,
    acquisition: str,
    suffix: str,
    hash_character: str | None = None,
    sensor: str = "SAR",
) -> SourceAssetRecord:
    return SourceAssetRecord.from_mapping(
        {
            "asset_id": f"S1-{suffix}-SYNTHETIC",
            "event_id": EVENT_ID,
            "sensor": sensor,
            "platform": "Sentinel-1",
            "product_id": f"SYNTHETIC-PRODUCT-{suffix}",
            "acquisition_time_utc": acquisition,
            "event_relative_role": role,
            "orbit_direction": "descending",
            "relative_orbit": "142",
            "polarizations": "VV,VH",
            "processing_level": "terrain_corrected_aligned_fixture",
            "crs": "EPSG:32647",
            "pixel_spacing_m": 10,
            "local_path_hint": f"outside_git/S1-{suffix}-SYNTHETIC.tif",
            "sha256": (
                hash_character
                or ("a" if role == "pre_event" else "b")
            )
            * 64,
            "sha256_status": "recorded",
            "license_status": "confirmed",
            "processing_allowed": True,
            "ml_label_derivation_allowed": True,
            "redistribution_status": "reference_only",
            "georegistration_method": "synthetic_fixture_control_points",
            "georegistration_error_pixels": 0.25,
            "source_timestamp": "2024-09-20T00:00:00Z",
            "confidence_class": "low",
            "assumptions": (
                "Synthetic metadata and checksum only; no imagery or flood label."
            ),
        }
    )


def _synthetic_review_context(
    queries: pd.DataFrame,
    sources: tuple[SourceAssetRecord, ...],
    processing_receipt: dict[str, object],
) -> pd.DataFrame:
    lineage = queries.iloc[0]
    layers = (
        ("pre_event_vv", "PRE", "2024-09-01T12:00:00Z", "c"),
        ("pre_event_vh", "PRE", "2024-09-01T12:00:00Z", "d"),
        ("event_time_vv", "EVENT", "2024-09-12T12:00:00Z", "e"),
        ("event_time_vh", "EVENT", "2024-09-12T12:00:00Z", "f"),
        ("permanent_water_context", "PERMANENT", "2021-01-01T00:00:00Z", "0"),
        ("land_cover", "LAND", "2021-01-01T00:00:00Z", "2"),
        ("dem_hillshade", "DEM", "2021-01-01T00:00:00Z", "3"),
    )
    source_by_suffix = {
        source.asset_id.removeprefix("S1-").removesuffix("-SYNTHETIC"): source
        for source in sources
    }
    processed_by_asset = processing_assets_by_id(processing_receipt)
    return pd.DataFrame(
        [
            {
                "context_layer_id": f"SYNTHETIC-CONTEXT-{role.upper()}",
                "event_id": EVENT_ID,
                "layer_role": role,
                "source_registry_sha256": lineage["source_registry_sha256"],
                "source_asset_id": f"S1-{product}-SYNTHETIC",
                "source_product_id": f"SYNTHETIC-PRODUCT-{product}",
                "display_name": f"Synthetic {role}",
                "path_hint": f"synthetic_review/{role}.tif",
                "crs": "EPSG:32647",
                "acquisition_time_utc": acquisition,
                "source_sha256": source_by_suffix[product].sha256,
                "processed_layer_sha256": (
                    processed_by_asset[f"S1-{product}-SYNTHETIC"][
                        "processed_file_sha256"
                    ]
                    if product in {"PRE", "EVENT"}
                    else processed_hash_character * 64
                ),
                "allowed_for_blinded_review": True,
                "confidence_class": "low",
                "assumptions": (
                    "Synthetic context provenance only; no imagery or flood truth."
                ),
            }
            for role, product, acquisition, processed_hash_character in layers
        ]
    )


def _tile_assignment() -> dict[str, object]:
    return {
        "event_id": EVENT_ID,
        "x_index": 0,
        "y_index": 0,
        "dataset_role": "training_and_query_pool",
        "overlap_group_id": "SYNTHETIC-G000",
        "valid_data_fraction": 1.0,
        "feature_schema_version": "sar_change_v2",
        "source_timestamp": "2024-09-20T00:00:00Z",
        "confidence_class": "low",
        "assumptions": "Synthetic query lattice; not flood truth.",
    }


def _assert_query_only(frame: pd.DataFrame) -> None:
    assert frame["eligible_for_review_queue"].eq(True).all()
    assert frame["query_model_only"].eq(True).all()
    assert frame["eligible_for_decision_layer"].eq(False).all()
    assert frame["eligible_for_fpps"].eq(False).all()
    assert frame["eligible_for_warning"].eq(False).all()
    if "model_purpose" in frame:
        assert frame["model_purpose"].eq("query_ranking").all()
    if "selection_creates_flood_truth" in frame:
        assert frame["selection_creates_flood_truth"].eq(False).all()


def _synthetic_cell_scores(queries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    land_cover = ("urban", "cropland", "forest", "ordinary_landscape")
    safety = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()
    for query_index, query in queries.reset_index(drop=True).iterrows():
        metadata = {column: query[column] for column in QUERY_METADATA_COLUMNS}
        for cell_index in range(4):
            rows.append(
                {
                    "sample_id": f"CELL-{query_index:02d}-{cell_index:02d}",
                    **metadata,
                    **safety,
                    "logistic_query_score": (
                        0.12 + 0.025 * (query_index % 7) + 0.13 * cell_index
                    ),
                    "boosted_query_score": (
                        0.82 - 0.02 * (query_index % 5) - 0.11 * cell_index
                    ),
                    "boundary_impurity": 0.05 + 0.10 * (query_index % 8),
                    "hard_stratum": query_index % 4 == 0,
                    "major_land_cover_stratum": land_cover[
                        query_index % len(land_cover)
                    ],
                    "diversity_vv_p90": float(query_index),
                    "diversity_slope_p90": float((query_index * 7) % 13),
                }
            )
    return pd.DataFrame(rows)


def test_synthetic_label_factory_pipeline_stays_query_only(
    tmp_path: Path,
) -> None:
    """Integrate grid, acquisition, and blind-review contracts without labels."""

    event = _event()
    sources = (
        _source_asset(
            role="pre_event",
            acquisition="2024-09-01T12:00:00Z",
            suffix="PRE",
        ),
        _source_asset(
            role="event_time",
            acquisition="2024-09-12T12:00:00Z",
            suffix="EVENT",
        ),
        _source_asset(
            role="static_context",
            acquisition="2021-01-01T00:00:00Z",
            suffix="PERMANENT",
            hash_character="7",
            sensor="permanent-water context",
        ),
        _source_asset(
            role="static_context",
            acquisition="2021-01-01T00:00:00Z",
            suffix="LAND",
            hash_character="8",
            sensor="land-cover context",
        ),
        _source_asset(
            role="static_context",
            acquisition="2021-01-01T00:00:00Z",
            suffix="DEM",
            hash_character="9",
            sensor="terrain context",
        ),
    )
    validate_event_source_registry((event,), sources)
    processing_receipt = synthetic_processing_receipt(
        tmp_path / "processing",
        [event],
        list(sources),
    )

    manifests = build_grid_manifests(
        (event,),
        (_tile_assignment(),),
        sources,
        processing_receipt,
        allow_ungoverned_fixture=True,
    )
    validate_grid_manifests(
        (event,),
        sources,
        manifests.tiles,
        manifests.query_regions,
        processing_receipt,
        allow_ungoverned_fixture=True,
    )
    assert len(manifests.tiles) == 1
    assert len(manifests.query_regions) == 16
    assert manifests.tiles["grid_contract_sha256"].eq(
        event.grid.contract_sha256
    ).all()
    assert manifests.query_regions["grid_contract_sha256"].eq(
        event.grid.contract_sha256
    ).all()
    _assert_query_only(manifests.tiles)
    _assert_query_only(manifests.query_regions)

    # Round 0 consumes only explicit strata and canonical query metadata. It
    # must not require or emit committee confidence as a selection basis.
    round_zero_candidates = manifests.query_regions.copy()
    round_zero_candidates["round0_stratum"] = [
        ROUND_ZERO_STRATA[index % len(ROUND_ZERO_STRATA)]
        for index in range(len(round_zero_candidates))
    ]
    round_zero = select_round_zero_manifest(
        round_zero_candidates,
        round_id="R0-SYNTHETIC",
        batch_size=len(ROUND_ZERO_STRATA),
        random_seed=17,
    )
    round_zero_selected = round_zero.loc[round_zero["selected"]]
    assert len(round_zero_selected) == len(ROUND_ZERO_STRATA)
    assert round_zero_selected["round0_stratum"].nunique() == len(
        ROUND_ZERO_STRATA
    )
    assert round_zero["round_id"].eq("R0-SYNTHETIC").all()
    assert round_zero_selected["selection_lane"].eq("round0_stratified").all()
    assert round_zero_selected["selection_basis"].eq(
        "model_independent_stratification"
    ).all()
    assert "active_score" not in round_zero
    _assert_query_only(round_zero)

    # These are deterministic synthetic score fixtures, not outputs trained on
    # claimed human labels. They exercise the cell-to-query bridge only.
    candidates = build_region_candidate_manifest(
        _synthetic_cell_scores(manifests.query_regions),
        diversity_columns=("diversity_vv_p90", "diversity_slope_p90"),
    )
    assert len(candidates) == len(manifests.query_regions)
    assert candidates["supported_cell_count"].eq(4).all()
    _assert_query_only(candidates)

    later_round = select_active_learning_manifest(
        candidates,
        round_id="R1-SYNTHETIC",
        diversity_columns=("diversity_vv_p90", "diversity_slope_p90"),
        batch_size=10,
        random_seed=23,
    )
    later_selected = later_round.loc[later_round["selected"]]
    assert len(later_selected) == 10
    assert later_round["round_id"].eq("R1-SYNTHETIC").all()
    assert "random_control" in set(later_selected["selection_lane"])
    assert later_round["requested_random_control_quota"].gt(0).all()
    assert later_round["achieved_random_control_quota"].gt(0).all()
    _assert_query_only(later_round)

    review = build_blinded_review_manifest(
        later_round,
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
    )
    template = build_annotation_template(review)
    assert len(review) == len(later_selected)
    assert SENSITIVE_REVIEW_COLUMNS.isdisjoint(review.columns)
    assert {
        "active_score",
        "uncertainty",
        "absolute_disagreement",
        "jensen_shannon_disagreement",
        "selection_lane",
    }.isdisjoint(review.columns)
    assert template["annotation_id"].eq("").all()
    assert template["reviewer_id"].eq("").all()
    assert template["primary_class"].eq("").all()
    assert template["geometry_wkt"].eq("").all()
    assert template["review_complete"].eq(False).all()
    assert template["reviewed_extent_status"].eq("not_reviewed").all()
    assert template["model_predictions_visible"].eq(False).all()
    assert template["other_reviewer_annotations_visible"].eq(False).all()

    written = write_blinded_review_bundle(
        later_round,
        tmp_path / "review-bundle",
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
        processing_alignment_receipt=processing_receipt,
        allow_ungoverned_fixture=True,
        context_layers=_synthetic_review_context(
            later_round,
            sources,
            processing_receipt,
        ),
    )
    bundle_manifest = pd.read_csv(written["bundle_manifest"])
    reviewer_regions = pd.read_csv(written["review_regions"])
    assert bundle_manifest["eligible_for_decision_layer"].eq(False).all()
    assert bundle_manifest["eligible_for_fpps"].eq(False).all()
    assert bundle_manifest["eligible_for_warning"].eq(False).all()
    assert bundle_manifest["model_predictions_visible"].eq(False).all()
    assert "active_score" not in reviewer_regions
    assert "selection_lane" not in reviewer_regions

    # Every operational ingress must fail before schema conversion could make
    # a query score look like flood probability or preparedness evidence.
    with pytest.raises(DecisionInputSafetyError):
        score_subdistricts(later_round)
    with pytest.raises(DecisionInputSafetyError):
        score_road_disruption(pd.DataFrame(), later_round)
    with pytest.raises(DecisionInputSafetyError):
        reject_label_factory_query_input(
            later_round,
            ingress="warning generation",
        )
