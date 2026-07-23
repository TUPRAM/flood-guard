from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"
TYPESCRIPT = CONTRACTS / "src" / "index.ts"
OFFLINE_BUNDLE = ROOT / "apps" / "web" / "public" / "offline-demo" / "bundle.json"
MAE_SAI_PUBLIC_BUNDLE = (
    ROOT
    / "apps"
    / "web"
    / "public"
    / "offline-demo"
    / "mae-sai"
    / "public-bundle.json"
)

SCHEMA_NAMES = ("status", "area-decision", "layer", "model-run")
GEOAI_V2_SCHEMA_NAMES = (
    "model-run-v2",
    "model-evaluation-v2",
    "flood-observation-product-v2",
    "model-registry-entry-v1",
)
PILOT_SCHEMA_NAMES = (
    "pilot-readiness",
    "agency-acceptance-receipt",
    "field-validation-receipt",
)
EVIDENCE_SCHEMA_NAMES = (
    "proposal-evidence",
    "evidence-state",
    "source-component",
    "evidence-context",
    "evidence-record",
    "public-preparedness-area",
)
COMMON_FIELDS = {
    "schema_version",
    "dataset_mode",
    "operational_status",
    "source_timestamp",
    "generated_at",
    "confidence_class",
    "source_name",
    "assumptions",
    "official_warning",
    "data_version",
    "git_commit",
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict[str, Any]:
    return _load_json(SCHEMAS / f"{name}.schema.json")


def _validate(schema_name: str, payload: dict[str, Any]) -> None:
    registry = Registry()
    for schema_path in SCHEMAS.glob("*.schema.json"):
        schema = _load_json(schema_path)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    Draft202012Validator(
        _schema(schema_name),
        format_checker=FormatChecker(),
        registry=registry,
    ).validate(payload)


def _schema_name_for_example(path: Path) -> str:
    for name in sorted(
        SCHEMA_NAMES
        + PILOT_SCHEMA_NAMES
        + EVIDENCE_SCHEMA_NAMES
        + GEOAI_V2_SCHEMA_NAMES,
        key=len,
        reverse=True,
    ):
        if path.name.startswith(f"{name}."):
            return name
    raise AssertionError(f"No schema mapping for {path.name}")


def _typescript_array(source: str, constant: str) -> list[str]:
    match = re.search(
        rf"export const {constant} = \[(.*?)\] as const;",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"Missing TypeScript constant {constant}"
    return re.findall(r'"([^"]+)"', match.group(1))


@pytest.mark.parametrize(
    "schema_name",
    SCHEMA_NAMES
    + PILOT_SCHEMA_NAMES
    + EVIDENCE_SCHEMA_NAMES
    + GEOAI_V2_SCHEMA_NAMES,
)
def test_contract_schemas_are_valid_draft_2020_12(schema_name: str) -> None:
    schema = _schema(schema_name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_every_contract_example_validates_against_its_schema() -> None:
    example_paths = sorted(EXAMPLES.glob("*.json"))
    assert {path.name for path in example_paths} == {
        "area-decision.fixture-demo.json",
        "evidence-context.fixture-demo.json",
        "evidence-record.fixture-demo.json",
        "evidence-state.fixture-demo.json",
        "field-validation-receipt.fixture-demo.json",
        "layer.fixture-demo.json",
        "model-run.candidate.json",
        "model-run-v2.candidate.json",
        "model-evaluation-v2.blocked.json",
        "flood-observation-product-v2.candidate.json",
        "model-registry-entry-v1.candidate.json",
        "pilot-readiness.fixture-demo.json",
        "proposal-evidence.fixture-demo.json",
        "public-preparedness-area.fixture-demo.json",
        "source-component.fixture-demo.json",
        "status.candidate.json",
        "status.fixture-demo.json",
    }
    for path in example_paths:
        _validate(_schema_name_for_example(path), _load_json(path))


def test_passed_evidence_requires_recorded_authority_and_decision_time() -> None:
    payload = _load_json(EXAMPLES / "evidence-record.fixture-demo.json")
    payload["decision"] = "passed"
    with pytest.raises(ValidationError):
        _validate("evidence-record", payload)

    payload["decision_authority"] = "test-review-board"
    payload["decision_at"] = "2026-07-20T00:00:00Z"
    _validate("evidence-record", payload)


@pytest.mark.parametrize(
    ("authority", "decision_at"),
    [
        ("test-review-board", None),
        (None, "2026-07-20T00:00:00Z"),
    ],
)
def test_evidence_decision_authority_and_time_require_a_complete_pair(
    authority: str | None,
    decision_at: str | None,
) -> None:
    payload = _load_json(EXAMPLES / "evidence-record.fixture-demo.json")
    payload["decision_authority"] = authority
    payload["decision_at"] = decision_at
    with pytest.raises(ValidationError):
        _validate("evidence-record", payload)


def test_operational_evidence_requires_official_agency_context() -> None:
    payload = _load_json(EXAMPLES / "evidence-record.fixture-demo.json")
    payload.update(
        {
            "decision": "passed",
            "decision_authority": "test-review-board",
            "decision_at": "2026-07-20T00:00:00Z",
            "operational_authorized": True,
            "model_id": "qualified-flood-model",
            "model_version": "1.0.0",
            "model_sha256": "a" * 64,
            "evaluation_sha256": "b" * 64,
            "blockers": [],
        }
    )
    with pytest.raises(ValidationError):
        _validate("evidence-record", payload)

    payload["evidence_context"]["dataset_mode"] = "official_input"
    payload["evidence_context"]["operational_status"] = "agency_operational"
    payload["evidence_context"]["model_run_id"] = "qualified-model-run-v1"
    _validate("evidence-record", payload)

    payload["evidence_context"]["model_run_id"] = None
    with pytest.raises(ValidationError):
        _validate("evidence-record", payload)


def test_layer_evidence_gate_combinations_fail_closed() -> None:
    payload = _load_json(EXAMPLES / "layer.fixture-demo.json")
    payload["evidence_state"].update(
        {
            "permitted_use": "operational_authorized",
            "confidence_class": "low",
            "gate_state": "ready",
        }
    )
    with pytest.raises(ValidationError):
        _validate("layer", payload)

    payload = _load_json(EXAMPLES / "layer.fixture-demo.json")
    payload["evidence_state"].update(
        {
            "permitted_use": "operational_authorized",
            "confidence_class": "high",
            "gate_state": "ready",
        }
    )
    with pytest.raises(ValidationError):
        _validate("layer", payload)

    payload = _load_json(EXAMPLES / "layer.fixture-demo.json")
    payload["evidence_state"].update(
        {"gate_state": "blocked", "required_gate": None}
    )
    with pytest.raises(ValidationError):
        _validate("layer", payload)


def test_source_freshness_policy_is_explicit_and_structurally_coherent() -> None:
    payload = _load_json(EXAMPLES / "source-component.fixture-demo.json")
    payload.pop("freshness_as_of")
    with pytest.raises(ValidationError):
        _validate("source-component", payload)

    payload = _load_json(EXAMPLES / "source-component.fixture-demo.json")
    payload.update({"temporal_meaning": "unknown", "freshness": "historical"})
    with pytest.raises(ValidationError):
        _validate("source-component", payload)


def test_offline_judging_bundle_validates_against_shared_contracts() -> None:
    bundle = _load_json(OFFLINE_BUNDLE)
    _validate("status", bundle["status"])
    area_contract_fields = set(_schema("area-decision")["properties"])
    for area in bundle["areas"]:
        assert set(area) - area_contract_fields == {
            "total_population",
            "scenario_results",
        }
        _validate(
            "area-decision",
            {key: value for key, value in area.items() if key in area_contract_fields},
        )
    for layer in bundle["layers"]:
        _validate("layer", layer)
    for run in bundle["model_runs"]:
        _validate("model-run", run)
    _validate("pilot-readiness", bundle["pilot_readiness"])

    assert bundle["status"]["dataset_mode"] == "fixture_demo"
    assert bundle["status"]["operational_status"] == "non_operational"
    assert bundle["status"]["official_warning"] is False
    assert all(run["can_feed_decision_layer"] is False for run in bundle["model_runs"])
    assert (
        re.search(
            r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|/home/|/Users/|\\\\)",
            json.dumps(bundle),
        )
        is None
    )


def test_mae_sai_public_bundle_validates_against_shared_contracts() -> None:
    bundle = _load_json(MAE_SAI_PUBLIC_BUNDLE)
    _validate("evidence-context", bundle["evidence_context"])
    _validate("evidence-record", bundle["evidence_record"])
    _validate("status", bundle["status"])
    for area in bundle["public_areas"]:
        _validate("public-preparedness-area", area)
    for layer in bundle["layers"]:
        _validate("layer", layer)


def test_offline_area_decisions_match_locked_score_and_class_contract() -> None:
    from floodguard.scoring import (
        DEFAULT_WEIGHTS,
        assign_action_class,
        assign_action_reason_code,
    )

    bundle = _load_json(OFFLINE_BUNDLE)
    for area in bundle["areas"]:
        expected_score = round(
            sum(area[name] * weight for name, weight in DEFAULT_WEIGHTS.items()),
            2,
        )
        assert area["fpps_0_100"] == pytest.approx(expected_score, abs=0.011)
        assert area["action_class"] == assign_action_class(area)
        assert area["action_reason_code"] == assign_action_reason_code(area)


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_all_schemas_require_the_common_metadata_envelope(schema_name: str) -> None:
    schema = _schema(schema_name)
    assert COMMON_FIELDS.issubset(schema["required"])
    assert COMMON_FIELDS.issubset(schema["properties"])


@pytest.mark.parametrize(
    "example_name",
    [
        "status.fixture-demo.json",
        "status.candidate.json",
        "area-decision.fixture-demo.json",
        "layer.fixture-demo.json",
        "model-run.candidate.json",
    ],
)
def test_fixture_and_candidate_payloads_cannot_claim_official_warning(
    example_name: str,
) -> None:
    path = EXAMPLES / example_name
    payload = _load_json(path)
    payload["official_warning"] = True

    with pytest.raises(ValidationError):
        _validate(_schema_name_for_example(path), payload)


@pytest.mark.parametrize("schema_name", SCHEMA_NAMES)
def test_official_input_contract_may_carry_an_official_warning(
    schema_name: str,
) -> None:
    candidates = sorted(EXAMPLES.glob(f"{schema_name}.*.json"))
    payload = _load_json(candidates[0])
    payload["dataset_mode"] = "official_input"
    payload["official_warning"] = True

    _validate(schema_name, payload)


def test_model_run_fails_closed_for_candidate_and_blocked_inputs() -> None:
    payload = _load_json(EXAMPLES / "model-run.candidate.json")

    candidate_claim = deepcopy(payload)
    candidate_claim["can_feed_decision_layer"] = True
    with pytest.raises(ValidationError):
        _validate("model-run", candidate_claim)

    blocked_claim = deepcopy(payload)
    blocked_claim["dataset_mode"] = "official_input"
    blocked_claim["processing_allowed"] = False
    blocked_claim["can_feed_decision_layer"] = True
    with pytest.raises(ValidationError):
        _validate("model-run", blocked_claim)

    inconsistent_inputs = deepcopy(payload)
    inconsistent_inputs["processing_allowed"] = True
    inconsistent_inputs["input_manifest_rows"][0]["processing_allowed"] = False
    with pytest.raises(ValidationError):
        _validate("model-run", inconsistent_inputs)

    missing_reason = deepcopy(payload)
    missing_reason["reason_blocked"] = ""
    with pytest.raises(ValidationError):
        _validate("model-run", missing_reason)


def test_model_run_requires_complete_successful_evidence_for_decision_feed() -> None:
    eligible = _load_json(EXAMPLES / "model-run.candidate.json")
    eligible.update(
        {
            "dataset_mode": "official_input",
            "operational_status": "planning_only",
            "confidence_class": "high",
            "run_status": "completed",
            "reference_mask_status": "confirmed_for_model_purpose",
            "processing_allowed": True,
            "can_feed_decision_layer": True,
            "reason_blocked": "",
        }
    )
    eligible["validation_metrics"]["expected_calibration_error"] = 0.03
    _validate("model-run", eligible)

    for field, invalid_value in (
        ("dataset_mode", "candidate"),
        ("operational_status", "non_operational"),
        ("confidence_class", "low"),
        ("run_status", "blocked"),
        ("reference_mask_status", "synthetic_fixture_only"),
        ("processing_allowed", False),
        ("reason_blocked", "A gate is still blocked."),
    ):
        claim = deepcopy(eligible)
        claim[field] = invalid_value
        with pytest.raises(ValidationError):
            _validate("model-run", claim)

    incomplete_metrics = deepcopy(eligible)
    incomplete_metrics["validation_metrics"]["expected_calibration_error"] = None
    with pytest.raises(ValidationError):
        _validate("model-run", incomplete_metrics)


def test_blocked_geoai_run_can_expose_missing_model_provenance() -> None:
    payload = _load_json(EXAMPLES / "model-run.candidate.json")
    payload.update(
        {
            "run_status": "blocked",
            "geoai_commit": None,
            "model_id": None,
            "model_revision": None,
            "model_sha256": None,
            "architecture": None,
            "encoder": None,
            "num_channels": None,
            "channel_names": [],
            "reason_blocked": (
                "Immutable GeoAI source and a materialized model remain unavailable."
            ),
        }
    )
    _validate("model-run", payload)

    payload["run_status"] = "completed"
    with pytest.raises(ValidationError):
        _validate("model-run", payload)


def test_prepared_geoai_contract_requires_partition_and_tile_receipts() -> None:
    payload = _load_json(EXAMPLES / "model-run.candidate.json")

    missing_tile_receipt = deepcopy(payload)
    missing_tile_receipt["prepared_tile_manifest_sha256"] = None
    with pytest.raises(ValidationError):
        _validate("model-run", missing_tile_receipt)

    insufficient_partitions = deepcopy(payload)
    insufficient_partitions["spatial_partitions"] = [
        insufficient_partitions["spatial_partitions"][0]
    ]
    with pytest.raises(ValidationError):
        _validate("model-run", insufficient_partitions)

    prepared_without_model = deepcopy(payload)
    prepared_without_model["run_status"] = "prepared"
    prepared_without_model["model_sha256"] = None
    _validate("model-run", prepared_without_model)

    completed_without_model = deepcopy(payload)
    completed_without_model["model_sha256"] = None
    with pytest.raises(ValidationError):
        _validate("model-run", completed_without_model)


@pytest.mark.parametrize(
    "private_path",
    [
        r"C:\\Users\\operator\\geoai-output",
        "/home/operator/geoai-output",
        r"\\\\server\\private\\geoai-output",
    ],
)
def test_model_run_rejects_private_absolute_workspace_paths(private_path: str) -> None:
    payload = _load_json(EXAMPLES / "model-run.candidate.json")
    payload["external_output_workspace"] = private_path

    with pytest.raises(ValidationError):
        _validate("model-run", payload)


def test_geoai_v2_candidate_artifacts_remain_report_only() -> None:
    run = _load_json(EXAMPLES / "model-run-v2.candidate.json")
    evaluation = _load_json(EXAMPLES / "model-evaluation-v2.blocked.json")
    product = _load_json(EXAMPLES / "flood-observation-product-v2.candidate.json")
    registry = _load_json(EXAMPLES / "model-registry-entry-v1.candidate.json")

    for schema_name, payload in (
        ("model-run-v2", run),
        ("model-evaluation-v2", evaluation),
        ("flood-observation-product-v2", product),
    ):
        official_claim = deepcopy(payload)
        official_claim["official_warning"] = True
        with pytest.raises(ValidationError):
            _validate(schema_name, official_claim)

        feed_claim = deepcopy(payload)
        feed_claim["can_feed_decision_layer"] = True
        with pytest.raises(ValidationError):
            _validate(schema_name, feed_claim)

    registry_official = deepcopy(registry)
    registry_official["payload"]["official_warning"] = True
    with pytest.raises(ValidationError):
        _validate("model-registry-entry-v1", registry_official)

    registry_feed = deepcopy(registry)
    registry_feed["payload"]["can_feed_decision_layer"] = True
    with pytest.raises(ValidationError):
        _validate("model-registry-entry-v1", registry_feed)


def test_geoai_v2_completed_run_requires_materialized_lineage() -> None:
    payload = _load_json(EXAMPLES / "model-run-v2.candidate.json")

    for path in (
        ("model", "model_sha256"),
        ("training_lineage", "training_dataset_manifest_sha256"),
        ("training_lineage", "prepared_tile_manifest_sha256"),
        ("partition_contract", "final_holdout_partition_sha256"),
    ):
        claim = deepcopy(payload)
        claim[path[0]][path[1]] = None
        with pytest.raises(ValidationError):
            _validate("model-run-v2", claim)

    empty_holdout = deepcopy(payload)
    empty_holdout["partition_contract"]["final_holdout_ids"] = []
    with pytest.raises(ValidationError):
        _validate("model-run-v2", empty_holdout)


def test_geoai_v2_completed_evaluation_is_calibration_only_and_report_only() -> None:
    payload = _load_json(EXAMPLES / "model-evaluation-v2.blocked.json")
    payload.update(
        {
            "evaluation_status": "completed_report_only",
            "evaluation_scope": "final_holdout",
            "controlled_result_receipt_sha256": "a" * 64,
            "event_metrics": [
                {
                    "event_id": "synthetic_event_001",
                    "sample_count": 20,
                    "iou": 0.5,
                    "f1_dice": 0.66,
                    "precision": 0.7,
                    "recall": 0.62,
                    "absolute_area_error_ratio": 0.1,
                    "brier_score": 0.15,
                    "expected_calibration_error": 0.05,
                }
            ],
            "error_strata": [
                {
                    "category": "all",
                    "coverage_status": "measured",
                    "cell_count": 20,
                    "false_positive_count": 2,
                    "false_negative_count": 3,
                    "precision": 0.7,
                    "recall": 0.62,
                }
            ],
        }
    )
    payload["reference_evidence"].update(
        {
            "reference_mask_sha256": "b" * 64,
            "label_release_sha256": "c" * 64,
            "reviewer_qualification_receipt_sha256": "d" * 64,
        }
    )
    payload["partition_evidence"] = {
        "partition_manifest_sha256": "e" * 64,
        "training_partition_sha256": "f" * 64,
        "calibration_partition_sha256": "1" * 64,
        "final_holdout_partition_sha256": "2" * 64,
    }
    payload["threshold_evidence"] = {
        "threshold": 0.47,
        "threshold_selection_receipt_sha256": "3" * 64,
        "selection_scope": "verified_calibration_projection_only",
        "final_holdout_evaluated_during_selection": False,
    }
    payload["overall_metrics"] = {
        "sample_count": 20,
        "true_positive": 8,
        "false_positive": 2,
        "false_negative": 3,
        "true_negative": 7,
        "iou": 8 / 13,
        "f1_dice": 16 / 21,
        "precision": 0.8,
        "recall": 8 / 11,
        "boundary_f1": 0.6,
        "signed_area_error_ratio": -0.05,
        "absolute_area_error_ratio": 0.05,
        "brier_score": 0.15,
        "negative_log_likelihood": 0.4,
        "expected_calibration_error": 0.05,
    }
    payload["calibration"] = {
        "status": "evaluated",
        "method": "temperature_scaling",
        "reliability_asset_sha256": "4" * 64,
    }
    payload["selective_prediction"] = {
        "status": "evaluated",
        "risk_coverage_asset_sha256": "5" * 64,
    }
    payload["ood_evaluation"] = {
        "status": "passed",
        "method": "mahalanobis_distance",
        "threshold": 0.9,
        "score_asset_sha256": "6" * 64,
    }
    payload["downstream_impact"] = {
        "status": "evaluated",
        "population_absolute_error": 120.0,
        "critical_road_false_negative_count": 1,
        "access_classification_flip_count": 2,
        "equity_gap_absolute_error": 0.1,
        "fpps_mean_absolute_error": 3.0,
        "fpps_rank_correlation": 0.9,
        "action_class_flip_count": 1,
        "artifact_sha256": "7" * 64,
    }
    _validate("model-evaluation-v2", payload)

    leaked_holdout = deepcopy(payload)
    leaked_holdout["threshold_evidence"][
        "final_holdout_evaluated_during_selection"
    ] = True
    with pytest.raises(ValidationError):
        _validate("model-evaluation-v2", leaked_holdout)

    for section in ("selective_prediction", "ood_evaluation", "downstream_impact"):
        incomplete = deepcopy(payload)
        incomplete[section]["status"] = "not_evaluated"
        with pytest.raises(ValidationError):
            _validate("model-evaluation-v2", incomplete)


def test_flood_observation_product_requires_unknown_and_abstention_evidence() -> None:
    payload = _load_json(EXAMPLES / "flood-observation-product-v2.candidate.json")
    roles = {asset["role"] for asset in payload["assets"]}
    assert {
        "flood_probability",
        "validity_mask",
        "sensor_quality_mask",
        "model_uncertainty",
        "abstention_mask",
    }.issubset(roles)
    assert (
        payload["unknown_cell_policy"]
        == "preserve_nodata_and_abstention_never_fill_as_dry"
    )
    assert payload["grid"]["nodata"] < 0

    missing_abstention = deepcopy(payload)
    missing_abstention["assets"] = [
        asset
        for asset in missing_abstention["assets"]
        if asset["role"] != "abstention_mask"
    ]
    with pytest.raises(ValidationError):
        _validate("flood-observation-product-v2", missing_abstention)

    private_path = deepcopy(payload)
    private_path["assets"][0]["relative_path"] = r"C:\private\probability.tif"
    with pytest.raises(ValidationError):
        _validate("flood-observation-product-v2", private_path)

    blocked_product = deepcopy(payload)
    blocked_product.update(
        {
            "processing_allowed": False,
            "sensor_quality_status": "failed",
            "valid_coverage_fraction": 0.0,
            "abstained_fraction": 1.0,
            "review_required_reasons": ["No valid observation coverage."],
            "reason_blocked": "No valid observation coverage; all cells remain unknown.",
        }
    )
    _validate("flood-observation-product-v2", blocked_product)
    assert blocked_product["counts_as_observed_evidence"] is False

    duplicate_role = deepcopy(payload)
    duplicate = deepcopy(duplicate_role["assets"][0])
    duplicate["relative_path"] = "different/probability.tif"
    duplicate["sha256"] = "f" * 64
    duplicate_role["assets"].append(duplicate)
    with pytest.raises(ValidationError):
        _validate("flood-observation-product-v2", duplicate_role)

    missing_review = deepcopy(blocked_product)
    missing_review["review_required_reasons"] = []
    with pytest.raises(ValidationError):
        _validate("flood-observation-product-v2", missing_review)

    for field, value in (
        ("valid_coverage_fraction", 0.0),
        ("processing_allowed", False),
    ):
        unsafe_observed = deepcopy(payload)
        unsafe_observed.update(
            {
                "dataset_mode": "official_input",
                "operational_status": "planning_only",
                "valid_coverage_fraction": 0.5,
                "processing_allowed": True,
                "counts_as_observed_evidence": True,
            }
        )
        unsafe_observed[field] = value
        with pytest.raises(ValidationError):
            _validate("flood-observation-product-v2", unsafe_observed)


def test_registry_schema_requires_external_acceptance_for_decision_use() -> None:
    payload = _load_json(EXAMPLES / "model-registry-entry-v1.candidate.json")
    claim = deepcopy(payload)
    claim["payload"].update(
        {
            "dataset_mode": "official_input",
            "operational_status": "planning_only",
            "registry_status": "approved",
            "permitted_use": "decision_input",
            "can_feed_decision_layer": True,
            "reason_blocked": "",
        }
    )
    with pytest.raises(ValidationError):
        _validate("model-registry-entry-v1", claim)

    claim["payload"].update(
        {
            "controlled_result_receipt_sha256": "a" * 64,
            "promotion_acceptance_receipt_sha256": "b" * 64,
            "field_validation_receipt_sha256": "c" * 64,
            "agency_acceptance_receipt_sha256": "d" * 64,
        }
    )
    _validate("model-registry-entry-v1", claim)


def test_examples_do_not_contain_private_absolute_paths() -> None:
    private_path = re.compile(r"(?:[A-Za-z]:[\\/]|/home/|/Users/|\\\\)")
    for path in EXAMPLES.glob("*.json"):
        serialized = path.read_text(encoding="utf-8")
        assert private_path.search(serialized) is None, path.name


def test_proposal_evidence_artifacts_are_checksum_bound_and_repo_relative() -> None:
    payload = _load_json(EXAMPLES / "proposal-evidence.fixture-demo.json")
    for artifact in payload["artifacts"]:
        relative = Path(*artifact["relative_path"].split("/"))
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT.resolve())
        assert path.is_file()
        import hashlib

        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_proposal_evidence_candidate_proof_stays_fail_closed() -> None:
    payload = _load_json(EXAMPLES / "proposal-evidence.fixture-demo.json")
    assert payload["dataset_mode"] == "candidate"
    assert payload["operational_status"] == "non_operational"
    assert payload["geoai_proof"]["validation_status"] == "passed"
    assert payload["geoai_proof"]["aggregation_status"] == "report_only"
    assert payload["geoai_proof"]["can_feed_decision_layer"] is False

    claim = deepcopy(payload)
    claim["geoai_proof"]["can_feed_decision_layer"] = True
    claim["geoai_proof"]["reason_blocked"] = ""
    with pytest.raises(ValidationError):
        _validate("proposal-evidence", claim)

    operational_claim = deepcopy(payload)
    operational_claim["operational_status"] = "planning_only"
    with pytest.raises(ValidationError):
        _validate("proposal-evidence", operational_claim)


def test_pilot_contracts_fail_closed_without_signed_acceptance() -> None:
    readiness = _load_json(EXAMPLES / "pilot-readiness.fixture-demo.json")
    readiness["operational_status"] = "agency_operational"
    with pytest.raises(ValidationError):
        _validate("pilot-readiness", readiness)

    receipt = {
        "payload": {
            "schema_version": "1.0",
            "acceptance_id": "test-acceptance-v1",
            "study_area": "example_study_area",
            "dataset_mode": "official_input",
            "data_version": "example-official-v1",
            "artifact_manifest_sha256": "1" * 64,
            "source_timestamp": "2026-07-01T00:00:00Z",
            "requested_operational_status": "agency_operational",
            "acceptance_status": "accepted",
            "acceptance_criteria_ids": [
                "AC-SAFETY-01",
                "AC-DATA-02",
                "AC-OFFLINE-03",
                "AC-AUTH-04",
                "AC-FIELD-05",
            ],
            "field_validation_receipt_sha256": "2" * 64,
            "field_validation_protocol_version": "field-validation-v1",
            "issued_at": "2026-07-16T00:00:00Z",
            "expires_at": "2026-08-15T00:00:00Z",
            "issuer_subject": "test-pilot-admin",
        },
        "signature": {
            "algorithm": "HMAC-SHA256",
            "key_id": "test-key-id",
            "payload_sha256": "3" * 64,
            "value": "4" * 64,
        },
    }
    _validate("agency-acceptance-receipt", receipt)
    receipt["payload"]["dataset_mode"] = "fixture_demo"
    with pytest.raises(ValidationError):
        _validate("agency-acceptance-receipt", receipt)


def test_field_validation_fixture_is_explicitly_incomplete_and_non_operational() -> (
    None
):
    receipt = _load_json(EXAMPLES / "field-validation-receipt.fixture-demo.json")
    assert receipt["dataset_mode"] == "fixture_demo"
    assert receipt["operational_status"] == "non_operational"
    assert receipt["official_warning"] is False
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["status"] == "incomplete"
    assert all(value is None for value in receipt["metrics"].values())
    assert all(value is None for value in receipt["evidence_hashes"].values())

    receipt["metrics"]["signed_area_error_ratio"] = -0.25
    _validate("field-validation-receipt", receipt)
    receipt["metrics"]["absolute_area_error_ratio"] = -0.25
    with pytest.raises(ValidationError):
        _validate("field-validation-receipt", receipt)

    accepted_claim = _load_json(EXAMPLES / "field-validation-receipt.fixture-demo.json")
    accepted_claim["status"] = "accepted"
    with pytest.raises(ValidationError):
        _validate("field-validation-receipt", accepted_claim)


def test_pilot_readiness_fixture_exposes_exact_mandatory_criteria() -> None:
    readiness = _load_json(EXAMPLES / "pilot-readiness.fixture-demo.json")
    assert {item["criterion_id"] for item in readiness["acceptance_criteria"]} == {
        "AC-SAFETY-01",
        "AC-DATA-02",
        "AC-OFFLINE-03",
        "AC-AUTH-04",
        "AC-FIELD-05",
    }


def test_typescript_runtime_constants_match_schema_enums() -> None:
    source = TYPESCRIPT.read_text(encoding="utf-8")
    expected = {
        "DATASET_MODES": _schema("status")["properties"]["dataset_mode"]["enum"],
        "OPERATIONAL_STATUSES": _schema("status")["properties"]["operational_status"][
            "enum"
        ],
        "CONFIDENCE_CLASSES": _schema("status")["properties"]["confidence_class"][
            "enum"
        ],
        "DATA_STATES": _schema("status")["properties"]["data_state"]["enum"],
        "ACTION_CLASSES": _schema("area-decision")["properties"]["action_class"][
            "enum"
        ],
        "ACTION_REASON_CODES": _schema("area-decision")["properties"][
            "action_reason_code"
        ]["enum"],
        "ROLE_VISIBILITIES": _schema("layer")["properties"]["role_visibility"]["items"][
            "enum"
        ],
        "LAYER_FORMATS": _schema("layer")["properties"]["format"]["enum"],
        "EVIDENCE_TYPES": _schema("evidence-state")["properties"][
            "evidence_type"
        ]["enum"],
        "EVIDENCE_GRANULARITIES": _schema("evidence-state")["properties"][
            "granularity"
        ]["enum"],
        "PERMITTED_USES": _schema("evidence-state")["properties"][
            "permitted_use"
        ]["enum"],
        "EVIDENCE_GATE_STATES": _schema("evidence-state")["properties"][
            "gate_state"
        ]["enum"],
        "FRESHNESS_STATES": _schema("source-component")["properties"]["freshness"][
            "enum"
        ],
        "SOURCE_TEMPORAL_MEANINGS": _schema("source-component")["properties"][
            "temporal_meaning"
        ]["enum"],
        "EVIDENCE_DECISIONS": _schema("evidence-record")["properties"]["decision"][
            "enum"
        ],
        "MODEL_FAMILIES": _schema("model-run")["properties"]["model_family"]["enum"],
        "MODEL_RUN_STATUSES": _schema("model-run")["properties"]["run_status"]["enum"],
        "PREPROCESSING_VALUE_DOMAINS": _schema("model-run")["properties"][
            "preprocessing"
        ]["properties"]["value_domain"]["enum"],
        "EVIDENCE_KINDS": _schema("model-run-v2")["$defs"]["evidenceKind"]["enum"],
        "MODEL_BACKENDS": _schema("model-run-v2")["properties"]["model"][
            "properties"
        ]["backend"]["enum"],
        "MODEL_RUN_V2_FAMILIES": _schema("model-run-v2")["properties"]["model"][
            "properties"
        ]["model_family"]["enum"],
        "MODEL_EVALUATION_STATUSES": _schema("model-evaluation-v2")["properties"][
            "evaluation_status"
        ]["enum"],
        "OBSERVATION_ASSET_ROLES": _schema("flood-observation-product-v2")[
            "$defs"
        ]["asset"]["properties"]["role"]["enum"],
        "MODEL_REGISTRY_STATUSES": _schema("model-registry-entry-v1")["properties"][
            "payload"
        ]["properties"]["registry_status"]["enum"],
        "MODEL_PERMITTED_USES": _schema("model-registry-entry-v1")["properties"][
            "payload"
        ]["properties"]["permitted_use"]["enum"],
        "PILOT_ROLES": _schema("pilot-readiness")["properties"]["roles"]["items"][
            "enum"
        ],
        "ACCEPTANCE_RECEIPT_STATES": _schema("pilot-readiness")["properties"][
            "acceptance_receipt_state"
        ]["enum"],
        "EVIDENCE_RESULTS": _schema("proposal-evidence")["properties"][
            "test_suites"
        ]["items"]["properties"]["result"]["enum"],
        "GEOAI_VALIDATION_STATUSES": _schema("proposal-evidence")["properties"][
            "geoai_proof"
        ]["properties"]["validation_status"]["enum"],
        "GEOAI_AGGREGATION_STATUSES": _schema("proposal-evidence")["properties"][
            "geoai_proof"
        ]["properties"]["aggregation_status"]["enum"],
    }
    for constant, enum_values in expected.items():
        assert _typescript_array(source, constant) == enum_values
    assert 'export const FRESHNESS_POLICY_VERSION = "source-freshness-v1"' in source
    assert _schema("source-component")["properties"][
        "freshness_policy_version"
    ]["const"] == "source-freshness-v1"


def test_typescript_common_metadata_fields_match_all_schemas() -> None:
    source = TYPESCRIPT.read_text(encoding="utf-8")
    assert set(_typescript_array(source, "COMMON_METADATA_FIELDS")) == COMMON_FIELDS

    interface = re.search(
        r"export interface CommonMetadata \{(.*?)\n\}",
        source,
        flags=re.DOTALL,
    )
    assert interface is not None
    interface_fields = set(
        re.findall(r"^\s{2}([a-z_]+)(?:\?)?:", interface.group(1), flags=re.MULTILINE)
    )
    assert interface_fields == COMMON_FIELDS


def test_required_public_types_are_exported() -> None:
    source = TYPESCRIPT.read_text(encoding="utf-8")
    for type_name in (
        "DatasetMode",
        "OperationalStatus",
        "ConfidenceClass",
        "StatusResponse",
        "AreaDecision",
        "ActionReasonCode",
        "LayerCatalogItem",
        "EvidenceContext",
        "EvidenceState",
        "SourceComponent",
        "PublicPreparednessArea",
        "EvidenceRecord",
        "ModelRun",
        "PilotRole",
        "PilotReadiness",
        "SignedAcceptanceReceipt",
        "FieldValidationReceipt",
        "ProposalEvidenceManifest",
        "CommonMetadataV2",
        "EvidenceKind",
        "ModelRunV2",
        "ModelEvaluationV2",
        "FloodObservationProductV2",
        "ModelRegistryEntryV1",
    ):
        assert re.search(rf"export (?:type|interface) {type_name}\b", source)


def test_decision_feed_bridge_field_set_tracks_shared_model_run_schema() -> None:
    from floodguard.probability_aggregation import MODEL_RUN_FIELDS

    assert MODEL_RUN_FIELDS == frozenset(_schema("model-run")["required"])
