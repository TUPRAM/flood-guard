from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from floodguard_api.app import create_app
from floodguard_api.config import RepositoryPaths
from floodguard_api.repository import ArtifactRepository


def test_scenario_registry_declares_only_supported_scenarios(client: TestClient) -> None:
    response = client.get("/api/v1/scenarios")
    assert response.status_code == 200
    definitions = response.json()
    assert [item["scenario_id"] for item in definitions] == [
        "add_temporary_shelter",
        "close_road",
    ]
    shelter = definitions[0]
    capacity = next(
        parameter for parameter in shelter["parameters"] if parameter["name"] == "capacity"
    )
    assert capacity["minimum"] == 1
    assert capacity["maximum"] == 5000
    assert "does not model shelter capacity" in capacity["note"]
    assert all(
        item["access_method"] == "nearest_facility_shortest_path_threshold" for item in definitions
    )


def test_temporary_shelter_scenario_calls_backend_and_returns_deltas(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/scenario-runs",
        json={
            "scenario_id": "add_temporary_shelter",
            "study_area": "fixture_thailand_demo",
            "parameters": {"node_id": "P2A", "capacity": 500},
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["run_status"] == "completed"
    assert result["official_warning"] is False
    assert result["fpps_recalculated"] is False
    assert result["overall"]["change_people_losing_30_min_access"] == -30
    area = next(row for row in result["areas"] if row["area_id"] == "FG-TB-002")
    assert area["change_people_losing_30_min_access"] == -30
    assert result["run_id"] == "fixture-add-temporary-shelter-p2a-capacity-500-v1"

    fetched = client.get(f"/api/v1/scenario-runs/{result['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["overall"] == result["overall"]


def test_road_closure_scenario_returns_deterministic_delta(client: TestClient) -> None:
    response = client.post(
        "/api/v1/scenario-runs",
        json={
            "scenario_id": "close_road",
            "parameters": {"road_id": "FG-RD-002"},
        },
    )
    assert response.status_code == 201
    result = response.json()
    assert result["overall"]["change_people_losing_30_min_access"] == 50
    area = next(row for row in result["areas"] if row["area_id"] == "FG-TB-002")
    assert area["change_people_losing_30_min_access"] == 50


def test_scenario_request_rejects_unregistered_ids_and_parameters(
    client: TestClient,
) -> None:
    invalid_payloads = [
        {"scenario_id": "invented", "parameters": {}},
        {
            "scenario_id": "add_temporary_shelter",
            "parameters": {"node_id": "P9", "capacity": 500},
        },
        {
            "scenario_id": "add_temporary_shelter",
            "parameters": {"node_id": "P2A", "capacity": 0},
        },
        {
            "scenario_id": "add_temporary_shelter",
            "parameters": {"node_id": "P2A", "capacity": 5001},
        },
        {
            "scenario_id": "add_temporary_shelter",
            "parameters": {"node_id": "P2A", "capacity": 500, "formula": "ui"},
        },
        {
            "scenario_id": "close_road",
            "parameters": {"road_id": "ARBITRARY"},
        },
    ]
    for payload in invalid_payloads:
        response = client.post("/api/v1/scenario-runs", json=payload)
        assert response.status_code == 422, payload


def test_scenario_run_get_rejects_unknown_or_out_of_range_ids(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/scenario-runs/nope").status_code == 404
    assert (
        client.get(
            "/api/v1/scenario-runs/fixture-add-temporary-shelter-p2a-capacity-9999-v1"
        ).status_code
        == 404
    )


def test_missing_scenario_artifacts_return_structured_unavailable(
    tmp_path: Path,
) -> None:
    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    with TestClient(create_app(repository)) as client:
        response = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "add_temporary_shelter",
                "study_area": "fixture_thailand_demo",
                "parameters": {"node_id": "P2A", "capacity": 500},
            },
        )
    assert response.status_code == 503
    assert response.json()["data_state"] == "unavailable"
    assert "Scenario fixture artifacts unavailable" in response.json()["detail"]


def test_scenario_only_outage_keeps_area_decisions_available(
    tmp_path: Path,
) -> None:
    source = ArtifactRepository()
    for source_path in source.required_decision_artifacts:
        relative = source_path.relative_to(source.paths.root)
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    repository = ArtifactRepository(RepositoryPaths(root=tmp_path))
    with TestClient(create_app(repository)) as client:
        status = client.get("/api/v1/status")
        areas = client.get("/api/v1/areas")
        scenario = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "close_road",
                "study_area": "fixture_thailand_demo",
                "parameters": {"road_id": "FG-RD-002"},
            },
        )
    assert status.status_code == 200
    assert status.json()["data_state"] == "blocked"
    assert areas.status_code == 200
    assert len(areas.json()) == 5
    assert scenario.status_code == 503
