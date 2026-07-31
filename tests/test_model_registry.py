from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from floodguard.model_registry import (
    ModelRegistryError,
    canonical_sha256,
    resolve_model_registry_entry,
    sign_registry_payload,
    validate_observation_product,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "packages" / "contracts" / "examples"
FIXTURE_KEY_ID = "synthetic-registry-authority"
# Public, non-secret test material. It is documented beside the fixtures and
# must never be accepted by a deployed authority service.
FIXTURE_SIGNING_KEY = b"floodguard-contract-fixture-signing-key-v1"
EVALUATED_AT = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _load("model-run-v2.candidate.json"),
        _load("model-evaluation-v2.blocked.json"),
        _load("flood-observation-product-v2.candidate.json"),
    )


def _bind_and_sign(
    run: dict[str, Any],
    evaluation: dict[str, Any],
    product: dict[str, Any],
    *,
    payload_updates: dict[str, Any] | None = None,
) -> dict[str, object]:
    """Bind mutable test artifacts and return a newly signed registry entry."""

    run_sha256 = canonical_sha256(run)
    evaluation["model_run_manifest_sha256"] = run_sha256
    evaluation_sha256 = canonical_sha256(evaluation)
    product["model_run_manifest_sha256"] = run_sha256
    product["evaluation_manifest_sha256"] = evaluation_sha256

    payload = deepcopy(_load("model-registry-entry-v1.candidate.json")["payload"])
    payload.update(
        {
            "study_area_id": run["study_area_id"],
            "event_id": run["event_id"],
            "evidence_kind": run["evidence_kind"],
            "source_bundle_sha256": product["source_manifest_sha256"],
            "model_run_id": run["run_id"],
            "model_id": run["model"]["model_id"],
            "model_sha256": run["model"]["model_sha256"],
            "model_run_manifest_sha256": run_sha256,
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_manifest_sha256": evaluation_sha256,
            "controlled_result_receipt_sha256": evaluation[
                "controlled_result_receipt_sha256"
            ],
            "product_id": product["product_id"],
            "product_manifest_sha256": canonical_sha256(product),
        }
    )
    if payload_updates is not None:
        payload.update(payload_updates)
    return sign_registry_payload(
        payload,
        key_id=FIXTURE_KEY_ID,
        signing_key=FIXTURE_SIGNING_KEY,
    )


def _resolve(
    entry: dict[str, object],
    run: dict[str, Any],
    evaluation: dict[str, Any],
    product: dict[str, Any],
    *,
    evaluated_at: datetime = EVALUATED_AT,
    known_study_area_ids: set[str] | None = None,
):
    return resolve_model_registry_entry(
        entry,
        model_run=run,
        evaluation=evaluation,
        product=product,
        source_bundle_sha256=product["source_manifest_sha256"],
        known_study_area_ids=known_study_area_ids or {run["study_area_id"]},
        signing_keys={FIXTURE_KEY_ID: FIXTURE_SIGNING_KEY},
        evaluated_at=evaluated_at,
    )


def test_checked_in_candidate_chain_is_exactly_bound_and_report_only() -> None:
    run, evaluation, product = _artifacts()
    registry = _load("model-registry-entry-v1.candidate.json")

    run_sha256 = canonical_sha256(run)
    assert evaluation["model_run_manifest_sha256"] == run_sha256
    assert product["model_run_manifest_sha256"] == run_sha256
    assert product["evaluation_manifest_sha256"] == canonical_sha256(evaluation)
    assert registry["payload"]["model_run_manifest_sha256"] == run_sha256
    assert (
        registry["payload"]["evaluation_manifest_sha256"]
        == canonical_sha256(evaluation)
    )
    assert registry["payload"]["product_manifest_sha256"] == canonical_sha256(product)
    assert registry == sign_registry_payload(
        registry["payload"],
        key_id=FIXTURE_KEY_ID,
        signing_key=FIXTURE_SIGNING_KEY,
    )

    resolution = _resolve(registry, run, evaluation, product)

    assert resolution.registry_status == "candidate"
    assert resolution.permitted_use == "report_only"
    assert resolution.effective_use == "report_only"
    assert resolution.can_feed_decision_layer is False


def test_dynamic_blocked_product_remains_valid_but_report_only() -> None:
    run, evaluation, product = _artifacts()
    product.update(
        {
            "processing_allowed": False,
            "sensor_quality_status": "failed",
            "valid_coverage_fraction": 0.0,
            "abstained_fraction": 1.0,
            "review_required_reasons": ["No valid observation coverage."],
            "reason_blocked": "No valid observation coverage; all cells remain unknown.",
        }
    )
    entry = _bind_and_sign(run, evaluation, product)

    validate_observation_product(product)
    resolution = _resolve(entry, run, evaluation, product)

    assert product["counts_as_observed_evidence"] is False
    assert resolution.effective_use == "report_only"
    assert resolution.can_feed_decision_layer is False


def test_registry_rejects_study_area_substitution() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(
        run,
        evaluation,
        product,
        payload_updates={"study_area_id": "other_known_area"},
    )

    with pytest.raises(ModelRegistryError, match="study_area_id does not match"):
        _resolve(
            entry,
            run,
            evaluation,
            product,
            known_study_area_ids={"synthetic_contract_grid", "other_known_area"},
        )


def test_registry_rejects_model_identity_substitution_even_when_resigned() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(
        run,
        evaluation,
        product,
        payload_updates={"model_sha256": "f" * 64},
    )

    with pytest.raises(ModelRegistryError, match="model_sha256 does not match"):
        _resolve(entry, run, evaluation, product)


def test_registry_rejects_exact_artifact_hash_substitution() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(
        run,
        evaluation,
        product,
        payload_updates={"product_manifest_sha256": "f" * 64},
    )

    with pytest.raises(ModelRegistryError, match="does not match the exact artifact"):
        _resolve(entry, run, evaluation, product)


def test_registry_rejects_expired_entry() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(run, evaluation, product)

    with pytest.raises(ModelRegistryError, match="has expired"):
        _resolve(
            entry,
            run,
            evaluation,
            product,
            evaluated_at=datetime(2028, 1, 1, tzinfo=timezone.utc),
        )


def test_registry_rejects_signature_tampering() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(run, evaluation, product)
    signature = entry["signature"]
    assert isinstance(signature, dict)
    value = signature["value"]
    assert isinstance(value, str)
    signature["value"] = ("0" if value[0] != "0" else "1") + value[1:]

    with pytest.raises(ModelRegistryError, match="signature verification failed"):
        _resolve(entry, run, evaluation, product)


def test_product_rejects_unknown_cell_and_abstention_semantic_loss() -> None:
    _, _, product = _artifacts()

    missing_abstention = deepcopy(product)
    missing_abstention["assets"] = [
        asset
        for asset in missing_abstention["assets"]
        if asset["role"] != "abstention_mask"
    ]
    with pytest.raises(ModelRegistryError, match="abstention_mask"):
        validate_observation_product(missing_abstention)

    probability_nodata_as_dry = deepcopy(product)
    probability_nodata_as_dry["grid"]["nodata"] = 0
    with pytest.raises(ModelRegistryError, match="outside the .0,1. range"):
        validate_observation_product(probability_nodata_as_dry)

    mask_nodata_as_dry = deepcopy(product)
    next(
        asset
        for asset in mask_nodata_as_dry["assets"]
        if asset["role"] == "validity_mask"
    )["nodata"] = 0
    with pytest.raises(ModelRegistryError, match="nodata=255"):
        validate_observation_product(mask_nodata_as_dry)

    filled_unknowns = deepcopy(product)
    filled_unknowns["unknown_cell_policy"] = "fill_unknown_as_dry"
    with pytest.raises(ModelRegistryError, match="preserve nodata and abstention"):
        validate_observation_product(filled_unknowns)


def test_approved_registry_cannot_elevate_candidate_artifacts() -> None:
    run, evaluation, product = _artifacts()
    entry = _bind_and_sign(
        run,
        evaluation,
        product,
        payload_updates={
            "dataset_mode": "official_input",
            "operational_status": "planning_only",
            "registry_status": "approved",
            "permitted_use": "decision_input",
            "controlled_result_receipt_sha256": "1" * 64,
            "promotion_acceptance_receipt_sha256": "2" * 64,
            "field_validation_receipt_sha256": "3" * 64,
            "agency_acceptance_receipt_sha256": "4" * 64,
            "can_feed_decision_layer": True,
            "reason_blocked": "",
        },
    )

    with pytest.raises(
        ModelRegistryError,
        match="model run dataset_mode=official_input",
    ):
        _resolve(entry, run, evaluation, product)


def test_fabricated_acceptance_digests_cannot_authorize_decision_use() -> None:
    run, evaluation, product = _artifacts()
    for artifact in (run, evaluation, product):
        artifact["dataset_mode"] = "official_input"
        artifact["operational_status"] = "planning_only"
        artifact["processing_allowed"] = True

    evaluation.update(
        {
            "evaluation_status": "completed_report_only",
            "evaluation_scope": "final_holdout",
            "controlled_result_receipt_sha256": "1" * 64,
        }
    )
    evaluation["threshold_evidence"].update(
        {
            "threshold": 0.5,
            "threshold_selection_receipt_sha256": "2" * 64,
            "selection_scope": "verified_calibration_projection_only",
        }
    )
    evaluation["reference_evidence"].update(
        {
            "reference_mask_sha256": "6" * 64,
            "label_release_sha256": "7" * 64,
            "reviewer_qualification_receipt_sha256": "8" * 64,
        }
    )
    evaluation["partition_evidence"].update(
        {
            "partition_manifest_sha256": "9" * 64,
            "training_partition_sha256": "a" * 64,
            "calibration_partition_sha256": "b" * 64,
            "final_holdout_partition_sha256": "c" * 64,
        }
    )
    evaluation["overall_metrics"] = {
        field: 1 if field.endswith("count") or field == "sample_count" else 0.5
        for field in evaluation["overall_metrics"]
    }
    evaluation["event_metrics"] = [{"event_id": run["event_id"]}]
    evaluation["error_strata"] = [{"category": "all"}]
    evaluation["calibration"] = {
        "status": "evaluated",
        "method": "fabricated",
        "reliability_asset_sha256": "d" * 64,
    }
    evaluation["selective_prediction"] = {
        "status": "evaluated",
        "risk_coverage_asset_sha256": "e" * 64,
    }
    evaluation["ood_evaluation"] = {
        "status": "passed",
        "method": "fabricated",
        "threshold": 0.5,
        "score_asset_sha256": "f" * 64,
    }
    evaluation["downstream_impact"] = {
        "status": "evaluated",
        "population_absolute_error": 0.0,
        "critical_road_false_negative_count": 0,
        "access_classification_flip_count": 0,
        "equity_gap_absolute_error": 0.0,
        "fpps_mean_absolute_error": 0.0,
        "fpps_rank_correlation": 1.0,
        "action_class_flip_count": 0,
        "artifact_sha256": "0" * 64,
    }
    product.update(
        {
            "counts_as_observed_evidence": True,
            "sensor_quality_status": "passed",
            "ood_status": "in_domain",
            "valid_coverage_fraction": 0.01,
        }
    )
    entry = _bind_and_sign(
        run,
        evaluation,
        product,
        payload_updates={
            "dataset_mode": "official_input",
            "operational_status": "planning_only",
            "registry_status": "approved",
            "permitted_use": "decision_input",
            "controlled_result_receipt_sha256": "1" * 64,
            "promotion_acceptance_receipt_sha256": "3" * 64,
            "field_validation_receipt_sha256": "4" * 64,
            "agency_acceptance_receipt_sha256": "5" * 64,
            "can_feed_decision_layer": True,
            "reason_blocked": "",
        },
    )

    with pytest.raises(ModelRegistryError, match="digest strings alone cannot authorize"):
        _resolve(entry, run, evaluation, product)
