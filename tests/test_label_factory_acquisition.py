from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from floodguard.label_factory.acquisition import (
    AcquisitionManifestError,
    build_acquisition_summary,
    select_active_learning_manifest,
    select_round_zero_manifest,
    write_active_learning_selection,
)


def _candidates(count: int = 12) -> pd.DataFrame:
    rows = []
    for index in range(count):
        x_min = index * 1_000.0
        value = (index + 1) / (count + 1)
        rows.append(
            {
                "query_region_id": f"Q-{index:03d}",
                "tile_id": f"T-{index:03d}",
                "event_id": "TH-MAESAI-2024-09",
                "grid_id": "UTM47N_10M",
                "crs": "EPSG:32647",
                "dataset_role": "training_and_query_pool",
                "review_status": "pending_manual_review",
                "eligible_for_active_selection": True,
                "bbox_min_x": x_min,
                "bbox_min_y": 0.0,
                "bbox_max_x": x_min + 640.0,
                "bbox_max_y": 640.0,
                "uncertainty": value,
                "absolute_disagreement": value,
                "jensen_shannon_disagreement": value,
                "boundary_impurity": value,
                "hard_stratum": index < 4,
                "diversity_slope": float(index),
                "diversity_urban": float(index % 3),
                "eligible_for_review_queue": True,
                "query_model_only": True,
                "eligible_for_decision_layer": False,
                "eligible_for_fpps": False,
                "eligible_for_warning": False,
                "source_timestamp": "2024-09-15T23:16:01Z",
                "confidence_class": "low",
                "assumptions": "Candidate query, not flood truth.",
            }
        )
    return pd.DataFrame(rows)


def test_selection_writes_all_audit_fields_and_mandatory_random_lane() -> None:
    selected = select_active_learning_manifest(
        _candidates(),
        round_id="R1",
        diversity_columns=("diversity_slope", "diversity_urban"),
        batch_size=8,
        random_seed=9,
    )

    chosen = selected[selected["selected"]]
    assert len(chosen) == 8
    assert set(chosen["selection_lane"]) == {
        "active",
        "hard_stratum",
        "random_control",
    }
    assert chosen["selection_lane"].eq("random_control").sum() == 1
    assert selected["query_model_only"].eq(True).all()
    assert selected["eligible_for_fpps"].eq(False).all()
    assert selected["selection_creates_flood_truth"].eq(False).all()
    assert selected["active_score"].between(0, 1).all()
    assert selected["source_candidate_pool_sha256"].str.fullmatch(
        r"[0-9a-f]{64}"
    ).all()
    random_control = chosen[chosen["selection_lane"].eq("random_control")]
    assert random_control["sampling_stratum"].astype(str).str.strip().ne("").all()
    assert pd.to_numeric(
        random_control["sampling_stratum_population"], errors="raise"
    ).gt(0).all()
    assert pd.to_numeric(
        random_control["sampling_stratum_quota"], errors="raise"
    ).eq(1).all()
    assert pd.to_numeric(
        random_control["inclusion_probability"], errors="raise"
    ).between(0, 1, inclusive="right").all()


def test_selection_rejects_test_role_and_relaxed_safety() -> None:
    candidates = _candidates()
    candidates.loc[0, "dataset_role"] = "untouched_geographic_test"
    with pytest.raises(AcquisitionManifestError, match="must never enter acquisition"):
        select_active_learning_manifest(
            candidates,
            round_id="R1",
            diversity_columns=("diversity_slope",),
            batch_size=4,
        )

    candidates = _candidates()
    candidates.loc[0, "eligible_for_fpps"] = True
    with pytest.raises(AcquisitionManifestError, match="relaxes required safety"):
        select_active_learning_manifest(
            candidates,
            round_id="R1",
            diversity_columns=("diversity_slope",),
            batch_size=4,
        )


def test_writer_and_summary_keep_internal_and_reviewer_steps_separate(
    tmp_path: Path,
) -> None:
    written = write_active_learning_selection(
        _candidates(),
        round_id="R1",
        diversity_columns=("diversity_slope", "diversity_urban"),
        batch_size=8,
        random_seed=3,
        manifest_output_path=tmp_path / "selection.csv",
        summary_output_path=tmp_path / "selection.md",
    )

    result = pd.read_csv(written["manifest"])
    summary = written["summary"].read_text(encoding="utf-8")
    assert "active_score" in result.columns
    assert "query-model only" in summary
    assert "blinded review bundle" in summary
    assert build_acquisition_summary(result) == summary
    with pytest.raises(AcquisitionManifestError, match="cannot be overwritten"):
        write_active_learning_selection(
            _candidates(),
            round_id="R1",
            diversity_columns=("diversity_slope", "diversity_urban"),
            batch_size=8,
            random_seed=3,
            manifest_output_path=written["manifest"],
            summary_output_path=written["summary"],
        )


def test_round_zero_is_model_independent_and_covers_strata() -> None:
    candidates = _candidates()
    candidates["round0_stratum"] = [
        "weak_positive_interior",
        "weak_polygon_boundary",
        "likely_dry_land",
        "permanent_water_edge",
        "urban",
        "cropland_wet_soil",
        "forest_flooded_vegetation",
        "steep_terrain",
        "random_ordinary_landscape",
        "urban",
        "likely_dry_land",
        "weak_positive_interior",
    ]
    # Round zero deliberately needs no model-component or diversity columns.
    candidates = candidates.drop(
        columns=[
            "uncertainty",
            "absolute_disagreement",
            "jensen_shannon_disagreement",
            "boundary_impurity",
            "hard_stratum",
            "diversity_slope",
            "diversity_urban",
        ]
    )

    selected = select_round_zero_manifest(
        candidates,
        round_id="R0",
        batch_size=8,
        random_seed=17,
    )
    chosen = selected[selected["selected"]]

    assert len(chosen) == 8
    assert chosen["selection_lane"].eq("round0_stratified").all()
    assert chosen["selection_basis"].eq("model_independent_stratification").all()
    assert chosen["round0_stratum"].nunique() == 8
    assert "active_score" not in selected.columns
    assert selected["round_id"].eq("R0").all()
    assert selected["source_candidate_pool_sha256"].str.fullmatch(
        r"[0-9a-f]{64}"
    ).all()
