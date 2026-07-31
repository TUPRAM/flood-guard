from __future__ import annotations

import pandas as pd
import pytest

from floodguard.label_factory.candidate_builder import (
    CandidateBuilderError,
    build_region_candidate_manifest,
)
from floodguard.label_factory.review_bundle import (
    ReviewPurpose,
    build_blinded_review_manifest,
)


def _cell_scores() -> pd.DataFrame:
    rows = []
    for query in range(3):
        for cell in range(5):
            rows.append(
                {
                    "sample_id": f"S-{query}-{cell}",
                    "query_region_id": f"Q-{query}",
                    "tile_id": f"T-{query}",
                    "event_id": "TH-MAESAI-2024-09",
                    "grid_id": "UTM47N_10M",
                    "grid_contract_sha256": "c" * 64,
                    "source_registry_sha256": "d" * 64,
                    "processing_alignment_receipt_sha256": "e" * 64,
                    "pre_source_asset_ids": "S1-PRE",
                    "event_source_asset_ids": "S1-EVENT",
                    "pre_product_ids": "PRODUCT-PRE",
                    "event_product_ids": "PRODUCT-EVENT",
                    "pre_acquisition_utc": "2024-09-01T12:00:00Z",
                    "event_acquisition_utc": "2024-09-12T12:00:00Z",
                    "pre_source_sha256s": "a" * 64,
                    "event_source_sha256s": "b" * 64,
                    "feature_schema_version": "sar_change_v2",
                    "query_size_pixels": 64,
                    "resolution_m": 10.0,
                    "bbox_min_x": query * 1_000.0,
                    "bbox_min_y": 0.0,
                    "bbox_max_x": query * 1_000.0 + 640.0,
                    "bbox_max_y": 640.0,
                    "crs": "EPSG:32647",
                    "dataset_role": "training_and_query_pool",
                    "review_status": "unreviewed",
                    "eligible_for_human_annotation": True,
                    "eligible_for_active_selection": True,
                    "eligible_for_review_queue": True,
                    "eligible_for_training_after_human_review": "conditional",
                    "model_purpose": "query_ranking",
                    "query_model_only": True,
                    "eligible_for_decision_layer": False,
                    "eligible_for_fpps": False,
                    "eligible_for_warning": False,
                    "source_timestamp": "2024-09-15T23:16:01Z",
                    "confidence_class": "low",
                    "assumptions": "Query score, not flood truth.",
                    "logistic_query_score": [0.1, 0.2, 0.5, 0.8, 0.9][cell],
                    "boosted_query_score": [0.1, 0.3, 0.6, 0.7, 0.2][cell],
                    "boundary_impurity": 0.2 + query * 0.1,
                    "hard_stratum": query == 0,
                    "major_land_cover_stratum": "urban" if query == 0 else "cropland",
                    "diversity_vv_p90": 4.0 + query,
                    "diversity_slope_p90": 8.0 + query,
                }
            )
    return pd.DataFrame(rows)


def test_cell_scores_aggregate_to_one_auditable_region_candidate() -> None:
    candidates = build_region_candidate_manifest(
        _cell_scores(),
        diversity_columns=("diversity_vv_p90", "diversity_slope_p90"),
    )

    assert len(candidates) == 3
    assert candidates["supported_cell_count"].eq(5).all()
    assert candidates["uncertainty"].between(0, 1).all()
    assert candidates["absolute_disagreement"].between(0, 1).all()
    assert candidates["mean_logistic_probability"].eq(0.5).all()
    assert candidates["mean_boosted_probability"].eq(0.38).all()
    assert candidates["mean_committee_probability"].eq(0.44).all()
    assert candidates["committee_distance_from_0_5"].eq(0.06).all()
    assert candidates["top_tail_fraction"].eq(0.20).all()
    assert candidates["eligible_for_fpps"].eq(False).all()


def test_query_score_summaries_are_removed_from_blinded_review() -> None:
    candidates = build_region_candidate_manifest(
        _cell_scores(),
        diversity_columns=("diversity_vv_p90", "diversity_slope_p90"),
    )
    candidates["selected"] = True

    blinded = build_blinded_review_manifest(
        candidates,
        review_purpose=ReviewPurpose.ACQUISITION_PRIMARY,
    )

    assert len(blinded) == 3
    for column in (
        "mean_logistic_probability",
        "mean_boosted_probability",
        "mean_committee_probability",
        "committee_distance_from_0_5",
    ):
        assert column not in blinded.columns


def test_region_summary_fields_must_be_constant_within_query() -> None:
    scores = _cell_scores()
    scores.loc[0, "diversity_vv_p90"] = 999

    with pytest.raises(CandidateBuilderError, match="non-constant region field"):
        build_region_candidate_manifest(
            scores,
            diversity_columns=("diversity_vv_p90",),
        )


def test_relaxed_committee_safety_is_rejected() -> None:
    scores = _cell_scores()
    scores.loc[0, "eligible_for_fpps"] = True

    with pytest.raises(CandidateBuilderError, match="must remain False"):
        build_region_candidate_manifest(
            scores,
            diversity_columns=("diversity_vv_p90",),
        )
