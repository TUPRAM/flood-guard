from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient
from jsonschema import FormatChecker
from pydantic import ValidationError as PydanticValidationError
from referencing import Registry, Resource

from floodguard_api.app import create_app
from floodguard_api.config import RepositoryPaths
from floodguard_api.models import (
    AreaDecision,
    EvidenceRecord,
    EvidenceState,
    LayerCatalogItem,
    ModelRun,
)
from floodguard_api.repository import ArtifactRepository
from floodguard_api.safety import PrivatePathError, assert_public_payload


def test_all_required_routes_are_registered(client: TestClient) -> None:
    openapi = client.get("/api/openapi.json")
    assert openapi.status_code == 200
    paths = set(openapi.json()["paths"])
    assert {
        "/api/v1/status",
        "/api/v1/evidence-context",
        "/api/v1/public-areas",
        "/api/v1/evidence-records/{evidence_context_id}",
        "/api/v1/study-areas",
        "/api/v1/areas",
        "/api/v1/areas/{area_id}",
        "/api/v1/layers",
        "/api/v1/briefs/{area_id}",
        "/api/v1/scenarios",
        "/api/v1/scenario-runs",
        "/api/v1/scenario-runs/{run_id}",
        "/api/v1/model-runs",
        "/api/v1/model-runs/{run_id}",
        "/api/v1/data-readiness",
        "/api/v1/health",
    }.issubset(paths)


def test_fixture_evidence_context_public_projection_and_record_are_bound(
    client: TestClient,
) -> None:
    status = client.get("/api/v1/status").json()
    context_response = client.get("/api/v1/evidence-context")
    public_areas_response = client.get("/api/v1/public-areas")
    assert context_response.status_code == 200
    assert public_areas_response.status_code == 200
    context = context_response.json()
    public_areas = public_areas_response.json()
    record_response = client.get(
        f"/api/v1/evidence-records/{context['evidence_context_id']}"
    )

    assert status["evidence_context_id"] == context["evidence_context_id"]
    assert context["dataset_mode"] == "fixture_demo"
    assert context["model_run_id"] is None
    assert len(public_areas) == 5
    assert all(
        item["evidence_context_id"] == context["evidence_context_id"]
        and item["current_conditions_confirmed"] is False
        for item in public_areas
    )
    assert all("action_class" not in item for item in public_areas)
    assert record_response.status_code == 200
    record = record_response.json()
    assert record["evidence_context"] == context
    assert record["decision"] == "blocked"
    assert record["operational_authorized"] is False
    assert client.get("/api/v1/evidence-records/unknown-context").status_code == 404


def test_fixture_evidence_record_is_stable_across_repository_restarts() -> None:
    paths = RepositoryPaths.discover()
    first = ArtifactRepository(paths).evidence_record().model_dump(mode="json")
    second = ArtifactRepository(paths).evidence_record().model_dump(mode="json")

    assert first == second
    assert first["generated_at"] == first["evidence_context"]["generated_at"]


def test_configured_judging_origin_passes_cors_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOODGUARD_CORS_ORIGINS", "https://judge.example.org")
    with TestClient(create_app()) as configured_client:
        response = configured_client.options(
            "/api/v1/status",
            headers={
                "Origin": "https://judge.example.org",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://judge.example.org"


def test_health_is_separate_from_dataset_freshness(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "service_status": "healthy",
        "api_version": "v1",
        "service_name": "floodguard-artifact-api",
    }
    assert "data_state" not in response.json()
    assert "source_timestamp" not in response.json()


def test_status_validates_against_shared_schema(client: TestClient) -> None:
    payload = client.get("/api/v1/status").json()
    _validate_shared_schema("status.schema.json", payload)
    assert payload["dataset_mode"] == "fixture_demo"
    assert payload["operational_status"] == "non_operational"
    assert payload["official_warning"] is False
    assert payload["data_state"] == "ready"
    assert payload["source_timestamp"] != payload["generated_at"]


def test_study_area_is_explicitly_non_operational(client: TestClient) -> None:
    response = client.get("/api/v1/study-areas")
    assert response.status_code == 200
    assert len(response.json()) == 1
    item = response.json()[0]
    assert item["study_area_id"] == "fixture_thailand_demo"
    assert item["area_count"] == 5
    assert item["official_warning"] is False


def test_area_list_uses_artifacts_and_shared_contract(client: TestClient) -> None:
    response = client.get("/api/v1/areas")
    assert response.status_code == 200
    payload = response.json()
    assert [row["area_id"] for row in payload] == [
        "FG-TB-001",
        "FG-TB-002",
        "FG-TB-003",
        "FG-TB-004",
        "FG-TB-005",
    ]
    for row in payload:
        _validate_shared_schema("area-decision.schema.json", row)
        assert row["official_warning"] is False
        assert "nearest-facility" in " ".join(row["assumptions"])
    assert payload[0]["fpps_0_100"] == pytest.approx(81.6)
    assert payload[1]["equity_gap_ratio"] == pytest.approx(5.999)
    assert payload[4]["equity_gap_ratio"] is None


def test_area_filters_are_bounded_and_server_side(client: TestClient) -> None:
    response = client.get(
        "/api/v1/areas",
        params=[("action_class", "A"), ("action_class", "B"), ("min_fpps", "70")],
    )
    assert response.status_code == 200
    assert [row["area_id"] for row in response.json()] == ["FG-TB-001"]
    assert client.get("/api/v1/areas", params={"min_fpps": 101}).status_code == 422
    assert client.get("/api/v1/areas", params={"action_class": "Z"}).status_code == 422


def test_area_detail_and_unknown_id(client: TestClient) -> None:
    detail = client.get("/api/v1/areas/FG-TB-002")
    assert detail.status_code == 200
    assert detail.json()["action_class"] == "B"
    missing = client.get("/api/v1/areas/NOPE")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"


def test_layers_validate_and_geojson_is_downloadable_without_network(
    client: TestClient,
) -> None:
    layers = client.get("/api/v1/layers")
    assert layers.status_code == 200
    assert {layer["layer_id"] for layer in layers.json()} == {
        "priority_areas",
        "road_risk",
    }
    for layer in layers.json():
        _validate_shared_schema("layer.schema.json", layer)
        data = client.get(layer["url"])
        assert data.status_code == 200
        assert data.json()["type"] == "FeatureCollection"
        assert data.headers["x-floodguard-official-warning"] == "false"


def test_brief_is_bilingual_and_has_download_mode(client: TestClient) -> None:
    response = client.get("/api/v1/briefs/FG-TB-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bilingual"] is True
    assert "## Priority / ลำดับความสำคัญ" in payload["content_markdown"]
    assert "not an official warning" in payload["content_markdown"]
    assert payload["official_warning"] is False

    download = client.get("/api/v1/briefs/FG-TB-001", params={"download": "true"})
    assert download.status_code == 200
    assert download.headers["content-disposition"].endswith('filename="action_brief_FG-TB-001.md"')
    assert "text/markdown" in download.headers["content-type"]


def test_brief_can_be_built_for_non_default_action_class(client: TestClient) -> None:
    response = client.get("/api/v1/briefs/FG-TB-005")
    assert response.status_code == 200
    assert "Action class: E" in response.json()["content_markdown"]


def test_model_runs_validate_and_remain_blocked_from_promotion(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/model-runs")
    assert response.status_code == 200
    runs = response.json()
    assert {run["model_family"] for run in runs} == {
        "deterministic_sar_baseline",
        "weak_label_logistic",
    }
    for run in runs:
        _validate_shared_schema("model-run.schema.json", run)
        assert run["official_warning"] is False
        assert run["can_feed_decision_layer"] is False
        assert run["reason_blocked"]
        assert not _contains_private_path(run)
    weak = next(run for run in runs if run["model_family"] == "weak_label_logistic")
    assert weak["processing_allowed"] is False
    assert all(row["processing_allowed"] is False for row in weak["input_manifest_rows"])
    assert weak["validation_metrics"]["brier_score"] is None


def test_model_run_detail_and_unknown_id(client: TestClient) -> None:
    run = client.get("/api/v1/model-runs/synthetic-sar-baseline-v1")
    assert run.status_code == 200
    assert run.json()["validation_metrics"]["brier_score"] == pytest.approx(0.3475396)
    assert client.get("/api/v1/model-runs/nope").status_code == 404


@pytest.mark.parametrize("layer_id", ["priority_areas", "road_risk"])
def test_layer_geojson_exposes_the_area_join_key(
    client: TestClient,
    layer_id: str,
) -> None:
    response = client.get(f"/api/v1/layer-data/{layer_id}")
    assert response.status_code == 200
    features = response.json()["features"]
    assert features
    assert all(feature["properties"].get("area_id") for feature in features)
    known_area_ids = {area["area_id"] for area in client.get("/api/v1/areas").json()}
    assert {feature["properties"]["area_id"] for feature in features}.issubset(known_area_ids)


def test_readiness_preserves_source_state_and_blocked_reasons(client: TestClient) -> None:
    response = client.get("/api/v1/data-readiness")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 8
    assert any(row["status"] == "ready" for row in rows)
    blocked = [row for row in rows if row["status"] == "blocked"]
    assert blocked
    assert all(row["reason_blocked"] for row in blocked)
    seed = next(row for row in rows if row["check_id"] == "weak_reference_seed_scope")
    assert seed["source_status"] == "ready_for_seed_only"
    assert seed["status"] == "blocked"


def test_no_api_json_response_exposes_private_paths(client: TestClient) -> None:
    paths = [
        "/api/v1/status",
        "/api/v1/study-areas",
        "/api/v1/areas",
        "/api/v1/layers",
        "/api/v1/model-runs",
        "/api/v1/data-readiness",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert not _contains_private_path(response.json()), path


def test_area_contract_rejects_score_or_class_drift(client: TestClient) -> None:
    payload = client.get("/api/v1/areas").json()[0]
    score_drift = dict(payload)
    score_drift["fpps_0_100"] += 1
    with pytest.raises(PydanticValidationError, match="locked 30/25/20/15/10"):
        AreaDecision.model_validate(score_drift)

    class_drift = dict(payload)
    class_drift["action_class"] = "A" if payload["action_class"] != "A" else "E"
    with pytest.raises(PydanticValidationError, match="locked A-E"):
        AreaDecision.model_validate(class_drift)


def test_evidence_models_reject_unowned_passes_and_invalid_gate_combinations() -> None:
    root = Path(__file__).resolve().parents[3]
    record = json.loads(
        (root / "packages" / "contracts" / "examples" / "evidence-record.fixture-demo.json")
        .read_text(encoding="utf-8")
    )
    record["decision"] = "passed"
    with pytest.raises(PydanticValidationError, match="decision authority and time"):
        EvidenceRecord.model_validate(record)

    with pytest.raises(PydanticValidationError, match="blocked gate identifier"):
        EvidenceState.model_validate(
            {
                "evidence_type": "modelled",
                "granularity": "area_summary",
                "confidence_class": "low",
                "confidence_reason": "Test only.",
                "permitted_use": "planning_only",
                "required_gate": None,
                "gate_state": "blocked",
            }
        )

    authorized = json.loads(
        (root / "packages" / "contracts" / "examples" / "evidence-record.fixture-demo.json")
        .read_text(encoding="utf-8")
    )
    authorized.update(
        {
            "model_id": "qualified-model",
            "model_version": "1.0.0",
            "model_sha256": "a" * 64,
            "evaluation_sha256": "b" * 64,
            "decision": "passed",
            "decision_authority": "agency-review-board",
            "decision_at": "2026-07-20T00:00:00Z",
            "operational_authorized": True,
            "blockers": [],
        }
    )
    authorized["evidence_context"].update(
        {
            "dataset_mode": "official_input",
            "operational_status": "agency_operational",
        }
    )
    with pytest.raises(PydanticValidationError, match="complete accepted authority"):
        EvidenceRecord.model_validate(authorized)
    authorized["evidence_context"]["model_run_id"] = "qualified-run-v1"
    EvidenceRecord.model_validate(authorized)

    layer = json.loads(
        (root / "packages" / "contracts" / "examples" / "layer.fixture-demo.json")
        .read_text(encoding="utf-8")
    )
    layer["evidence_state"].update(
        {
            "permitted_use": "operational_authorized",
            "confidence_class": "high",
            "gate_state": "ready",
        }
    )
    with pytest.raises(PydanticValidationError, match="operational layers require"):
        LayerCatalogItem.model_validate(layer)
    layer.update(
        {
            "dataset_mode": "official_input",
            "operational_status": "agency_operational",
            "model_run_id": "qualified-run-v1",
        }
    )
    LayerCatalogItem.model_validate(layer)


def test_safety_guard_rejects_windows_unc_and_private_posix_paths() -> None:
    for value in (
        r"C:\\Users\\person\\data.tif",
        r"\\\\server\\share\\data.tif",
        "/home/person/data.tif",
        "file:///tmp/data.tif",
        r"artifact at C:\\Users\\person\\secret.tif",
        "see /home/person/secret.tif",
        "receipt: file:///tmp/secret.tif",
    ):
        with pytest.raises(PrivatePathError):
            assert_public_payload({"value": value})
    assert_public_payload(
        {
            "url": "/api/v1/layer-data/priority_areas",
            "workspace": "external-data-workspace/run-1",
        }
    )


def test_pydantic_model_run_requires_completed_validated_promotion_evidence() -> None:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (root / "packages" / "contracts" / "examples" / "model-run.candidate.json").read_text(
            encoding="utf-8"
        )
    )
    payload.update(
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
    payload["validation_metrics"]["expected_calibration_error"] = 0.03
    ModelRun.model_validate(payload)

    for field, invalid_value in (
        ("dataset_mode", "candidate"),
        ("operational_status", "non_operational"),
        ("confidence_class", "low"),
        ("run_status", "blocked"),
        ("reference_mask_status", "synthetic_fixture_only"),
        ("processing_allowed", False),
        ("reason_blocked", "A gate is still blocked."),
    ):
        claim = dict(payload)
        claim[field] = invalid_value
        with pytest.raises(PydanticValidationError):
            ModelRun.model_validate(claim)

    incomplete_metrics = json.loads(json.dumps(payload))
    incomplete_metrics["validation_metrics"]["expected_calibration_error"] = None
    with pytest.raises(PydanticValidationError):
        ModelRun.model_validate(incomplete_metrics)

    missing_tile_receipt = json.loads(json.dumps(payload))
    missing_tile_receipt["prepared_tile_manifest_sha256"] = None
    with pytest.raises(PydanticValidationError, match="tile-manifest hashes"):
        ModelRun.model_validate(missing_tile_receipt)

    missing_model_receipt = json.loads(json.dumps(payload))
    missing_model_receipt["model_sha256"] = None
    with pytest.raises(PydanticValidationError, match="model checksum"):
        ModelRun.model_validate(missing_model_receipt)

    prepared_without_model = json.loads(json.dumps(payload))
    prepared_without_model["run_status"] = "prepared"
    prepared_without_model["model_sha256"] = None
    prepared_without_model["can_feed_decision_layer"] = False
    prepared_without_model["reason_blocked"] = "Training has not started."
    ModelRun.model_validate(prepared_without_model)

    duplicate_partition = json.loads(json.dumps(payload))
    duplicate_partition["spatial_partitions"][1]["spatial_group_id"] = duplicate_partition[
        "spatial_partitions"
    ][0]["spatial_group_id"]
    with pytest.raises(PydanticValidationError, match="partition IDs must be unique"):
        ModelRun.model_validate(duplicate_partition)

    holdout_mismatch = json.loads(json.dumps(payload))
    holdout_mismatch["spatial_holdout_ids"] = ["undeclared-holdout"]
    with pytest.raises(PydanticValidationError, match="holdout partition IDs"):
        ModelRun.model_validate(holdout_mismatch)

    overlapping_partitions = json.loads(json.dumps(payload))
    overlapping_partitions["spatial_partitions"][1]["bounds"][0] = 600100.0
    with pytest.raises(PydanticValidationError, match="interiors cannot overlap"):
        ModelRun.model_validate(overlapping_partitions)


def test_missing_data_does_not_make_service_unhealthy(tmp_path: Path) -> None:
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    with TestClient(create_app(repository)) as client:
        assert client.get("/api/v1/health").json()["service_status"] == "healthy"
        status = client.get("/api/v1/status")
        assert status.status_code == 200
        assert status.json()["data_state"] == "unavailable"
        unavailable = client.get("/api/v1/areas")
        assert unavailable.status_code == 503
        assert unavailable.json()["data_state"] == "unavailable"


def test_missing_scenario_artifacts_keep_core_area_catalog_available(tmp_path: Path) -> None:
    source = ArtifactRepository()
    target = ArtifactRepository(RepositoryPaths(root=tmp_path))
    for artifact in source.required_decision_artifacts:
        relative = artifact.relative_to(source.paths.root)
        destination = target.paths.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, destination)

    with TestClient(create_app(target)) as scenario_blocked_client:
        status = scenario_blocked_client.get("/api/v1/status")
        study_area = scenario_blocked_client.get("/api/v1/study-areas").json()[0]
        areas = scenario_blocked_client.get("/api/v1/areas")
        scenario = scenario_blocked_client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "close_road",
                "study_area": "fixture_thailand_demo",
                "parameters": {"road_id": "FG-RD-002"},
            },
        )

    assert status.json()["data_state"] == "blocked"
    assert study_area["area_count"] == 5
    assert study_area["data_state"] == "blocked"
    assert areas.status_code == 200
    assert scenario.status_code == 503


def test_malformed_decision_csv_is_advertised_unavailable_without_raw_500(
    tmp_path: Path,
) -> None:
    source = ArtifactRepository()
    target = ArtifactRepository(RepositoryPaths(root=tmp_path))
    _copy_repository_artifacts(
        source.paths.root, target.paths.root, source.required_decision_artifacts
    )
    malformed = target.paths.outputs / "sample_priority_scores.csv"
    malformed.write_text("unexpected_column\nvalue\n", encoding="utf-8")

    with TestClient(create_app(target)) as client:
        health = client.get("/api/v1/health")
        status = client.get("/api/v1/status")
        areas = client.get("/api/v1/areas")

    assert health.json()["service_status"] == "healthy"
    assert status.status_code == 200
    assert status.json()["data_state"] == "unavailable"
    assert areas.status_code == 503
    assert areas.json()["data_state"] == "unavailable"
    assert not _contains_private_path(areas.json())


def test_malformed_geojson_layer_is_catalogued_and_returned_as_unavailable(
    tmp_path: Path,
) -> None:
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    path = repository.paths.outputs / "road_risk.geojson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"type":"FeatureCollection","features":"invalid"}', encoding="utf-8")

    with TestClient(create_app(repository)) as client:
        catalog = client.get("/api/v1/layers")
        layer = client.get("/api/v1/layer-data/road_risk")

    road = next(item for item in catalog.json() if item["layer_id"] == "road_risk")
    assert road["data_state"] == "unavailable"
    assert layer.status_code == 503
    assert layer.json()["data_state"] == "unavailable"
    assert not _contains_private_path(layer.json())


def test_malformed_readiness_csv_returns_explicit_unavailable_row(tmp_path: Path) -> None:
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    path = repository.paths.outputs / "label_factory_readiness.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("wrong_column\nvalue\n", encoding="utf-8")

    with TestClient(create_app(repository)) as client:
        response = client.get("/api/v1/data-readiness")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "unavailable"
    assert "cannot be inferred" in response.json()[0]["reason_blocked"]
    assert not _contains_private_path(response.json())


def test_malformed_model_csv_returns_structured_unavailable(tmp_path: Path) -> None:
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    path = repository.paths.outputs / "sample_sar_validation_metrics.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("wrong_column\nvalue\n", encoding="utf-8")

    with TestClient(create_app(repository)) as client:
        response = client.get("/api/v1/model-runs")

    assert response.status_code == 503
    assert response.json()["data_state"] == "unavailable"
    assert not _contains_private_path(response.json())


def test_present_but_invalid_markdown_brief_returns_structured_unavailable(
    tmp_path: Path,
) -> None:
    source = ArtifactRepository()
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    _copy_repository_artifacts(
        source.paths.root,
        repository.paths.root,
        source.required_decision_artifacts,
    )
    path = repository.paths.outputs / "action_brief_FG-TB-001.md"
    path.write_text("not a valid planning brief", encoding="utf-8")

    with TestClient(create_app(repository)) as client:
        response = client.get("/api/v1/briefs/FG-TB-001")

    assert response.status_code == 503
    assert response.json()["data_state"] == "unavailable"
    assert not _contains_private_path(response.json())


def _validate_shared_schema(name: str, payload: Any) -> None:
    root = Path(__file__).resolve().parents[3]
    schema_directory = root / "packages" / "contracts" / "schemas"
    schema = json.loads((schema_directory / name).read_text(encoding="utf-8"))
    registry = Registry()
    for schema_path in schema_directory.glob("*.schema.json"):
        dependency = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            dependency["$id"],
            Resource.from_contents(dependency),
        )
    jsonschema.Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    ).validate(payload)


def _contains_private_path(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    return bool(
        re.search(r"[A-Za-z]:[\\\\/]", serialized)
        or re.search(r"/(?:Users|home|root|tmp|var)/", serialized, re.IGNORECASE)
        or "file://" in serialized.lower()
    )


def _copy_repository_artifacts(
    source_root: Path,
    target_root: Path,
    artifacts: tuple[Path, ...],
) -> None:
    for source_path in artifacts:
        destination = target_root / source_path.relative_to(source_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
