import copy

import numpy as np
import pytest

from floodguard.observation_evaluation import (
    PARTITION_DEVELOPMENT,
    PARTITION_EXCLUDED,
    PARTITION_FINAL_HOLDOUT,
    ObservationEvaluationError,
    assign_partition,
    compare_to_limits,
    compute_observation_metrics,
    evaluate_observation,
    partition_sha256,
    validate_evaluation_plan,
)


def _plan(status="frozen"):
    return {
        "schema": "floodguard.observation_evaluation_plan.v1",
        "plan_id": "test_plan_v1",
        "status": status,
        "event_id": "TH-TEST-0001",
        "study_area_id": "aoi-test",
        "observation_target": "new inundation at the post acquisition",
        "candidate_products": [{"product_id": "cand", "description": "fixture", "sha256": None}],
        "reference": {"imagery_product_id": "img", "label_release_id": "release_v1"},
        "partition": {"block_size_m": 100, "halo_m": 10, "seed": "seed-1", "development_fraction": 0.5},
        "pixel_size_m": 10,
        "boundary_tolerance_m": 20,
        "strata": ["possible_recession"],
        "acceptance_limits": {
            "min_iou": 0.5, "min_precision": 0.5, "min_recall": 0.5,
            "max_abs_area_error_fraction": 0.5, "min_evaluated_coverage": 0.5,
        },
        "frozen": {"frozen_at_utc": "2026-09-24T00:00:00Z", "evaluation_lead_person_id": "FG-HUM-001", "decision_evidence_sha256": "a" * 64},
        "assumptions": "fixture",
    }


ELIGIBLE_GATE = {"eligible_for_real_experiment": True, "status": "test_only", "release_id": "release_v1", "qualified_label_release_sha256": "b" * 64}


def test_draft_plan_is_valid_as_draft_but_cannot_run():
    draft = _plan("draft")
    draft["acceptance_limits"] = dict.fromkeys(draft["acceptance_limits"])
    draft["frozen"] = dict.fromkeys(draft["frozen"])
    validate_evaluation_plan(draft, require_frozen=False)
    with pytest.raises(ObservationEvaluationError, match="frozen plan"):
        evaluate_observation(draft, ELIGIBLE_GATE, np.zeros((4, 4)), np.zeros((4, 4)), role="development", source_timestamp="t")


def test_frozen_plan_requires_every_limit_and_signer():
    plan = _plan()
    plan["acceptance_limits"]["min_iou"] = None
    with pytest.raises(ObservationEvaluationError, match="min_iou"):
        validate_evaluation_plan(plan, require_frozen=True)
    plan = _plan()
    plan["frozen"]["decision_evidence_sha256"] = "not-a-hash"
    with pytest.raises(ObservationEvaluationError, match="decision_evidence_sha256"):
        validate_evaluation_plan(plan, require_frozen=True)


def test_fixture_only_label_release_is_refused_before_any_metric():
    gate = {"eligible_for_real_experiment": False, "status": "validated_synthetic_fixture_only", "release_id": "release_v1"}
    with pytest.raises(ObservationEvaluationError, match="not eligible"):
        evaluate_observation(_plan(), gate, np.zeros((4, 4)), np.zeros((4, 4)), role="development", source_timestamp="t")


def test_label_release_must_match_the_plan():
    gate = dict(ELIGIBLE_GATE, release_id="other")
    with pytest.raises(ObservationEvaluationError, match="differs"):
        evaluate_observation(_plan(), gate, np.zeros((4, 4)), np.zeros((4, 4)), role="development", source_timestamp="t")


def test_metrics_count_only_reviewed_dry_or_flood_cells_and_abstention_lowers_coverage():
    # reference: 1 flood, 0 dry, 2 permanent water, 4 unobservable, 255 unreviewed
    ref = np.array([[1, 1, 1, 0, 0, 0, 2, 4, 255, 1]])
    cand = np.array([[1, 1, 0, 1, 0, 0, 1, 1, 1, 255]])
    m = compute_observation_metrics(ref, cand, np.ones_like(ref, dtype=bool), pixel_size_m=10, boundary_tolerance_m=20)
    assert m["confusion"] == {"true_positive": 2, "false_positive": 1, "false_negative": 1, "true_negative": 2}
    assert m["evaluable_cells"] == 7 and m["covered_cells"] == 6
    assert m["evaluated_coverage"] == pytest.approx(6 / 7)
    assert m["iou"] == pytest.approx(2 / 4)
    assert m["dice"] == pytest.approx(4 / 6)
    assert m["precision"] == pytest.approx(2 / 3) and m["recall"] == pytest.approx(2 / 3)
    assert m["signed_area_error_fraction"] == 0.0
    assert m["reference_flood_area_m2"] == 300.0


def test_zero_denominators_are_unavailable_not_zero():
    ref = np.zeros((3, 3), dtype=int)
    cand = np.zeros((3, 3), dtype=int)
    m = compute_observation_metrics(ref, cand, np.ones((3, 3), dtype=bool), pixel_size_m=10, boundary_tolerance_m=20)
    assert m["iou"] is None and m["recall"] is None and m["abs_area_error_fraction"] is None
    checks = compare_to_limits(m, _plan()["acceptance_limits"])
    assert checks["checks"]["min_iou"]["passed"] is False
    assert checks["meets_predeclared_limits"] is False


def test_partition_is_deterministic_with_halo_and_both_roles():
    kwargs = dict(pixel_size_m=10, block_size_m=100, halo_m=10, seed="seed-1", development_fraction=0.5)
    a = assign_partition((60, 60), **kwargs)
    assert np.array_equal(a, assign_partition((60, 60), **kwargs))
    assert {PARTITION_DEVELOPMENT, PARTITION_FINAL_HOLDOUT, PARTITION_EXCLUDED} <= set(np.unique(a).tolist())
    assert (a[0, :] == PARTITION_EXCLUDED).all()  # first row lies inside the 10 m halo
    assert (a[:, 9] == PARTITION_EXCLUDED).all() and (a[:, 10] == PARTITION_EXCLUDED).all()  # block edge at 100 m


def test_development_run_returns_safe_self_hashed_result():
    rng = np.random.default_rng(0)
    ref = rng.choice([0, 1], size=(60, 60))
    cand = ref.copy()
    result = evaluate_observation(_plan(), ELIGIBLE_GATE, ref, cand, role="development", source_timestamp="2024-09-15")
    assert result["metrics"]["iou"] == 1.0
    assert result["acceptance"]["meets_predeclared_limits"] is True
    assert result["accepted_observation"] is False
    assert result["official_warning"] is False and result["can_feed_decision_layer"] is False
    assert result["strata"]["possible_recession"] is None
    assert len(result["result_sha256"]) == 64


def test_final_holdout_requires_opening_bound_to_exact_membership():
    ref = np.ones((60, 60), dtype=int)
    with pytest.raises(ObservationEvaluationError, match="verified custodian opening"):
        evaluate_observation(_plan(), ELIGIBLE_GATE, ref, ref, role="final_holdout", source_timestamp="t")
    partition = assign_partition((60, 60), pixel_size_m=10, block_size_m=100, halo_m=10, seed="seed-1", development_fraction=0.5)
    opening = {
        "status": "signed_opening_verified_preflight_only",
        "receipt_sha256": "c" * 64,
        "signed_payload": {"final_holdout_partition_sha256": partition_sha256(partition, PARTITION_FINAL_HOLDOUT),
                           "qualified_release_set_sha256": "b" * 64},
    }
    result = evaluate_observation(_plan(), ELIGIBLE_GATE, ref, ref, role="final_holdout", holdout_opening=opening, source_timestamp="t")
    assert result["holdout_opening_receipt_sha256"] == "c" * 64
    wrong = copy.deepcopy(opening)
    wrong["signed_payload"]["final_holdout_partition_sha256"] = "d" * 64
    with pytest.raises(ObservationEvaluationError, match="exact final-holdout"):
        evaluate_observation(_plan(), ELIGIBLE_GATE, ref, ref, role="final_holdout", holdout_opening=wrong, source_timestamp="t")


def test_rejects_codes_outside_taxonomy():
    with pytest.raises(ObservationEvaluationError, match="candidate raster"):
        evaluate_observation(_plan(), ELIGIBLE_GATE, np.zeros((4, 4)), np.full((4, 4), 7), role="development", source_timestamp="t")


def test_committed_draft_plan_is_a_valid_draft_that_cannot_run():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "docs" / "proposal_execution" / "signing_forms" / "04_observation_evaluation_plan.draft.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    validate_evaluation_plan(plan, require_frozen=False)
    assert all(limit is None for limit in plan["acceptance_limits"].values())
    with pytest.raises(ObservationEvaluationError, match="draft"):
        validate_evaluation_plan(plan, require_frozen=True)
