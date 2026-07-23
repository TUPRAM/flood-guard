from __future__ import annotations

import hashlib
import hmac
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient
from floodguard.model_registry import (
    ModelRegistryError,
    resolve_model_registry_entry,
    validate_model_evaluation,
    validate_observation_product,
)
from jsonschema import FormatChecker
from pydantic import ValidationError

from floodguard_api.app import create_app
from floodguard_api.dataset_registry import (
    FIXTURE_STUDY_AREA,
    MAE_SAI_STUDY_AREA,
    DatasetRegistry,
)
from floodguard_api.model_registry import (
    PROJECTION_KEY_ID,
    PUBLIC_PROJECTION_TEST_KEY,
    build_model_registry_bundles,
    canonical_json,
    observation_asset_descriptors,
    validate_registry_bundle,
)
from floodguard_api.repository import ArtifactUnavailable
from floodguard_api.v2_models import FloodObservationProductV2, ModelEvaluationV2

NOW = datetime(2026, 7, 23, tzinfo=UTC)


def test_fixture_registry_and_bound_v2_artifacts_match_shared_schemas() -> None:
    with TestClient(create_app()) as client:
        context = client.get("/api/v1/evidence-context").json()
        registry_response = client.get("/api/v1/model-registry")
        evaluation_response = client.get("/api/v1/model-evaluations")
        product_response = client.get("/api/v1/observation-products")

    assert registry_response.status_code == 200
    assert evaluation_response.status_code == 200
    assert product_response.status_code == 200
    assert len(registry_response.json()) == 1
    assert len(evaluation_response.json()) == 1
    assert len(product_response.json()) == 1
    entry = registry_response.json()[0]
    payload = entry["payload"]
    evaluation = evaluation_response.json()[0]
    product = product_response.json()[0]

    _validate_shared_schema("model-registry-entry-v1.schema.json", entry)
    _validate_shared_schema("model-evaluation-v2.schema.json", evaluation)
    _validate_shared_schema("flood-observation-product-v2.schema.json", product)
    validate_observation_product(product)
    assert payload["study_area_id"] == context["study_area_id"]
    assert payload["source_bundle_sha256"] == context["evidence_package_sha256"]
    assert payload["registry_status"] == "candidate"
    assert payload["permitted_use"] == "report_only"
    assert payload["evidence_kind"] == "external_algorithmic_baseline"
    assert payload["official_warning"] is False
    assert payload["can_feed_decision_layer"] is False
    assert payload["promotion_acceptance_receipt_sha256"] is None
    assert payload["field_validation_receipt_sha256"] is None
    assert payload["agency_acceptance_receipt_sha256"] is None
    assert "non-authoritative" in payload["reason_blocked"]
    assert evaluation["evaluation_id"] == payload["evaluation_id"]
    assert _sha256_json(evaluation) == payload["evaluation_manifest_sha256"]
    assert product["product_id"] == payload["product_id"]
    assert _sha256_json(product) == payload["product_manifest_sha256"]
    assert product["counts_as_observed_evidence"] is False
    assert product["unknown_cell_policy"] == (
        "preserve_nodata_and_abstention_never_fill_as_dry"
    )
    assert not _contains_private_path(
        {
            "entry": entry,
            "evaluation": evaluation,
            "product": product,
        }
    )


def test_registry_evidence_endpoint_returns_the_exact_hashed_story() -> None:
    route = "/api/v1/model-registry/fixture-sar-accepted-candidate-v1/evidence"
    with TestClient(create_app()) as client:
        response = client.get(route)

    assert response.status_code == 200
    bundle = response.json()
    payload = bundle["entry"]["payload"]
    assert bundle["evidence_context_id"] == "fixture-thailand-demo:fixture-2026-06-29-v1"
    assert bundle["source_bundle_sha256"] == payload["source_bundle_sha256"]
    assert _sha256_json(bundle["model_run"]) == payload["model_run_manifest_sha256"]
    assert _sha256_json(bundle["evaluation"]) == payload["evaluation_manifest_sha256"]
    assert _sha256_json(bundle["product"]) == payload["product_manifest_sha256"]
    assert bundle["model_run"]["model"]["model_sha256"] == payload["model_sha256"]
    assert bundle["evaluation"]["model_run_id"] == payload["model_run_id"]
    assert bundle["product"]["evaluation_manifest_sha256"] == (
        payload["evaluation_manifest_sha256"]
    )
    assert bundle["official_warning"] is False
    assert bundle["can_feed_decision_layer"] is False
    assert not _contains_private_path(bundle)


def test_registry_is_deterministic_across_repository_restarts() -> None:
    first = DatasetRegistry()
    second = DatasetRegistry()
    with TestClient(create_app(first)) as first_client:
        first_payload = {
            "registry": first_client.get("/api/v1/model-registry").json(),
            "evaluations": first_client.get("/api/v1/model-evaluations").json(),
            "products": first_client.get("/api/v1/observation-products").json(),
        }
    with TestClient(create_app(second)) as second_client:
        second_payload = {
            "registry": second_client.get("/api/v1/model-registry").json(),
            "evaluations": second_client.get("/api/v1/model-evaluations").json(),
            "products": second_client.get("/api/v1/observation-products").json(),
        }

    assert first_payload == second_payload


def test_mae_sai_registry_is_blocked_unbound_and_all_abstain() -> None:
    params = {"study_area": MAE_SAI_STUDY_AREA}
    with TestClient(create_app()) as client:
        context_response = client.get("/api/v1/evidence-context", params=params)
        context = context_response.json()
        record = client.get(
            f"/api/v1/evidence-records/{context['evidence_context_id']}"
        ).json()
        model_runs = client.get("/api/v1/model-runs", params=params)
        registry = client.get("/api/v1/model-registry", params=params)
        evaluations = client.get("/api/v1/model-evaluations", params=params)
        products = client.get("/api/v1/observation-products", params=params)

    assert context_response.status_code == 200
    assert context["model_run_id"] is None
    assert record["model_id"] is None
    assert record["evaluation_sha256"] is None
    assert record["decision"] == "blocked"
    assert model_runs.status_code == 200
    assert model_runs.json() == []
    entry = registry.json()[0]
    payload = entry["payload"]
    evaluation = evaluations.json()[0]
    product = products.json()[0]
    _validate_shared_schema("model-registry-entry-v1.schema.json", entry)
    _validate_shared_schema("model-evaluation-v2.schema.json", evaluation)
    _validate_shared_schema("flood-observation-product-v2.schema.json", product)
    assert payload["study_area_id"] == MAE_SAI_STUDY_AREA
    assert payload["source_bundle_sha256"] == context["evidence_package_sha256"]
    assert payload["registry_status"] == "blocked"
    assert payload["controlled_result_receipt_sha256"] is None
    assert payload["promotion_acceptance_receipt_sha256"] is None
    assert payload["field_validation_receipt_sha256"] is None
    assert payload["agency_acceptance_receipt_sha256"] is None
    assert payload["official_warning"] is False
    assert payload["can_feed_decision_layer"] is False
    assert evaluation["evaluation_status"] == "blocked"
    assert evaluation["evaluation_scope"] == "not_evaluated"
    assert all(value is None for value in evaluation["overall_metrics"].values())
    assert product["valid_coverage_fraction"] == 0.0
    assert product["abstained_fraction"] == 1.0
    assert product["counts_as_observed_evidence"] is False
    assert product["processing_allowed"] is False
    assert "not observed flood evidence" in product["reason_blocked"]


def test_mae_sai_static_projection_is_exactly_the_api_and_core_chain() -> None:
    repository = DatasetRegistry()
    projection = build_model_registry_bundles(
        repository,
        MAE_SAI_STUDY_AREA,
        now=NOW,
    )[0]
    root = Path(__file__).resolve().parents[3]
    static_bundle = json.loads(
        (
            root
            / "apps"
            / "web"
            / "public"
            / "offline-demo"
            / "mae-sai"
            / "bundle.json"
        ).read_text(encoding="utf-8")
    )
    run = projection.model_run.model_dump(mode="json")
    evaluation = projection.evaluation.model_dump(mode="json")
    product = projection.product.model_dump(mode="json")
    entry = projection.entry.model_dump(mode="json")

    assert static_bundle["model_runs_v2"] == [run]
    assert static_bundle["model_evaluations"] == [evaluation]
    assert static_bundle["observation_products"] == [product]
    assert static_bundle["model_registry"] == [entry]
    validate_observation_product(product)
    resolution = resolve_model_registry_entry(
        entry,
        model_run=run,
        evaluation=evaluation,
        product=product,
        source_bundle_sha256=static_bundle["evidence_context"][
            "evidence_package_sha256"
        ],
        known_study_area_ids={MAE_SAI_STUDY_AREA},
        signing_keys={PROJECTION_KEY_ID: PUBLIC_PROJECTION_TEST_KEY},
        evaluated_at=NOW,
    )
    assert resolution.registry_status == "blocked"
    assert resolution.effective_use == "report_only"
    assert resolution.can_feed_decision_layer is False

    descriptors = observation_asset_descriptors(projection.product)
    assert static_bundle["model_asset_descriptors"] == descriptors
    for relative_path, descriptor in descriptors.items():
        descriptor_path = root / "apps" / "web" / "public" / Path(relative_path)
        payload = descriptor_path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == next(
            asset.sha256
            for asset in projection.product.assets
            if asset.relative_path == relative_path
        )
        assert json.loads(payload) == descriptor


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_role",
        "abstention_without_review",
        "zero_coverage_observed",
        "processing_blocked_observed",
    ],
)
def test_product_safety_rejections_match_schema_pydantic_and_core(
    mutation: str,
) -> None:
    product = build_model_registry_bundles(
        DatasetRegistry(),
        MAE_SAI_STUDY_AREA,
        now=NOW,
    )[0].product.model_dump(mode="json")
    if mutation == "duplicate_role":
        duplicate = deepcopy(product["assets"][0])
        duplicate["relative_path"] = "different/probability.descriptor.json"
        duplicate["sha256"] = "f" * 64
        product["assets"].append(duplicate)
    elif mutation == "abstention_without_review":
        product["review_required_reasons"] = []
    else:
        product.update(
            {
                "dataset_mode": "official_input",
                "operational_status": "planning_only",
                "counts_as_observed_evidence": True,
                "valid_coverage_fraction": 0.5,
                "processing_allowed": True,
            }
        )
        if mutation == "zero_coverage_observed":
            product["valid_coverage_fraction"] = 0.0
        else:
            product["processing_allowed"] = False

    with pytest.raises(jsonschema.ValidationError):
        _validate_shared_schema("flood-observation-product-v2.schema.json", product)
    with pytest.raises(ValidationError):
        FloodObservationProductV2.model_validate(product)
    with pytest.raises(ModelRegistryError):
        validate_observation_product(product)


def test_completed_evaluation_requires_selective_ood_and_downstream_evidence_everywhere() -> None:
    evaluation = build_model_registry_bundles(
        DatasetRegistry(),
        FIXTURE_STUDY_AREA,
        now=NOW,
    )[0].evaluation.model_dump(mode="json")
    evaluation["evaluation_status"] = "completed_report_only"

    with pytest.raises(jsonschema.ValidationError):
        _validate_shared_schema("model-evaluation-v2.schema.json", evaluation)
    with pytest.raises(ValidationError):
        ModelEvaluationV2.model_validate(evaluation)
    with pytest.raises(ModelRegistryError):
        validate_model_evaluation(evaluation)


def test_model_and_registry_details_cannot_cross_study_areas() -> None:
    fixture_entry = "fixture-sar-accepted-candidate-v1"
    mae_sai_entry = "mae-sai-model-evaluation-blocked-v1"
    with TestClient(create_app()) as client:
        assert (
            client.get(
                f"/api/v1/model-registry/{fixture_entry}",
                params={"study_area": MAE_SAI_STUDY_AREA},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/model-registry/{mae_sai_entry}",
                params={"study_area": FIXTURE_STUDY_AREA},
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/model-registry/{fixture_entry}/evidence",
                params={"study_area": MAE_SAI_STUDY_AREA},
            ).status_code
            == 404
        )
        assert (
            client.get(
                "/api/v1/model-runs/synthetic-sar-baseline-v1",
                params={"study_area": MAE_SAI_STUDY_AREA},
            ).status_code
            == 404
        )


def test_registry_validator_rejects_signature_and_source_substitution() -> None:
    repository = DatasetRegistry()
    context = repository.evidence_context(FIXTURE_STUDY_AREA)
    runs = repository.model_runs(FIXTURE_STUDY_AREA)
    bundle = build_model_registry_bundles(
        repository,
        FIXTURE_STUDY_AREA,
        now=NOW,
    )[0]
    bad_signature = bundle.entry.signature.model_copy(update={"value": "0" * 64})
    signature_tamper = replace(
        bundle,
        entry=bundle.entry.model_copy(update={"signature": bad_signature}),
    )
    with pytest.raises(ArtifactUnavailable, match="signature"):
        validate_registry_bundle(
            signature_tamper,
            context=context,
            scoped_runs=runs,
            requested_study_area=FIXTURE_STUDY_AREA,
            now=NOW,
        )

    source_substitution = bundle.entry.payload.model_copy(
        update={"source_bundle_sha256": "0" * 64}
    )
    substituted = replace(bundle, entry=_resign(bundle.entry, source_substitution))
    with pytest.raises(ArtifactUnavailable, match="source bundle"):
        validate_registry_bundle(
            substituted,
            context=context,
            scoped_runs=runs,
            requested_study_area=FIXTURE_STUDY_AREA,
            now=NOW,
        )


def test_registry_validator_rejects_model_hash_substitution_and_expiry() -> None:
    repository = DatasetRegistry()
    context = repository.evidence_context(FIXTURE_STUDY_AREA)
    runs = repository.model_runs(FIXTURE_STUDY_AREA)
    bundle = build_model_registry_bundles(
        repository,
        FIXTURE_STUDY_AREA,
        now=NOW,
    )[0]
    model_substitution = bundle.entry.payload.model_copy(
        update={"model_sha256": "0" * 64}
    )
    substituted = replace(bundle, entry=_resign(bundle.entry, model_substitution))
    with pytest.raises(ArtifactUnavailable, match="model-run binding"):
        validate_registry_bundle(
            substituted,
            context=context,
            scoped_runs=runs,
            requested_study_area=FIXTURE_STUDY_AREA,
            now=NOW,
        )

    expired_payload = bundle.entry.payload.model_copy(
        update={"expires_at": datetime(2026, 7, 22, tzinfo=UTC)}
    )
    expired = replace(bundle, entry=_resign(bundle.entry, expired_payload))
    with pytest.raises(ArtifactUnavailable, match="expired"):
        validate_registry_bundle(
            expired,
            context=context,
            scoped_runs=runs,
            requested_study_area=FIXTURE_STUDY_AREA,
            now=NOW,
        )


def _resign(entry: Any, payload: Any) -> Any:
    payload_bytes = canonical_json(payload.model_dump(mode="json"))
    signature = entry.signature.model_copy(
        update={
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "value": hmac.new(
                PUBLIC_PROJECTION_TEST_KEY,
                payload_bytes,
                hashlib.sha256,
            ).hexdigest(),
        }
    )
    return entry.model_copy(update={"payload": payload, "signature": signature})


def _validate_shared_schema(name: str, payload: Any) -> None:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (root / "packages" / "contracts" / "schemas" / name).read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(payload)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _contains_private_path(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    return bool(
        re.search(r"[A-Za-z]:[\\/]", serialized)
        or re.search(r"/(?:Users|home|root|tmp|var)/", serialized, re.IGNORECASE)
        or "file://" in serialized.lower()
    )
