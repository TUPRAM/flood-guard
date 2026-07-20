from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from floodguard_api.app import create_app
from floodguard_api.config import RepositoryPaths
from floodguard_api.dataset_registry import (
    MAE_SAI_MANIFEST_RELATIVE_PATH,
    MAE_SAI_SCENARIO_MANIFEST_RELATIVE_PATH,
    DatasetRegistry,
)

MAE_SAI = "mae_sai_candidate_v1"


def test_registry_advertises_fixture_and_real_coordinate_candidate() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        response = client.get("/api/v1/study-areas")
        candidate_status = client.get("/api/v1/status", params={"study_area": MAE_SAI})

    assert response.status_code == 200
    areas = {item["study_area_id"]: item for item in response.json()}
    assert set(areas) == {"fixture_thailand_demo", MAE_SAI}
    assert areas[MAE_SAI]["area_count"] == 8
    assert areas[MAE_SAI]["dataset_mode"] == "candidate"
    assert areas[MAE_SAI]["operational_status"] == "non_operational"
    assert areas[MAE_SAI]["official_warning"] is False

    assert candidate_status.status_code == 200
    status = candidate_status.json()
    assert status["data_state"] == "stale"
    assert status["dataset_mode"] == "candidate"
    assert status["official_warning"] is False
    assert "historic" in status["message_en"].lower()


def test_mae_sai_candidate_area_decisions_are_joined_without_formula_changes() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        response = client.get("/api/v1/areas", params={"study_area": MAE_SAI})
        detail = client.get(
            "/api/v1/areas/TH570901",
            params={"study_area": MAE_SAI},
        )

    assert response.status_code == 200
    rows = response.json()
    assert [row["area_id"] for row in rows] == [
        "TH570901",
        "TH570902",
        "TH570903",
        "TH570904",
        "TH570905",
        "TH570906",
        "TH570908",
        "TH570909",
    ]
    assert all(row["dataset_mode"] == "candidate" for row in rows)
    assert all(row["operational_status"] == "non_operational" for row in rows)
    assert all(row["official_warning"] is False for row in rows)
    assert all("scenario_delta" not in row for row in rows)
    assert sum(row["facility_evidence"]["facility_count"] for row in rows) == 42
    assert sum(row["road_evidence"]["at_risk_segments"] for row in rows) == 4458

    assert detail.status_code == 200
    item = detail.json()
    assert item["area_name_en"] == "Mae Sai"
    assert item["area_name_th"] == "แม่สาย"
    assert item["fpps_0_100"] == 18.01
    assert item["action_class"] == "E"
    assert item["road_evidence"]["bridge_count"] == 55
    assert "unverified" in item["facility_evidence"]["summary"].lower()


def test_candidate_layer_catalog_and_filters_preserve_safety_semantics() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        catalog_response = client.get("/api/v1/layers", params={"study_area": MAE_SAI})
        facilities = client.get(
            "/api/v1/layer-data/facilities",
            params={
                "study_area": MAE_SAI,
                "area_id": "TH570901",
                "verification_status": "open_context_candidate",
                "facility_type": "healthcare",
            },
        )
        roads = client.get(
            "/api/v1/layer-data/road_risk",
            params={"study_area": MAE_SAI, "minimum_risk": 0.2},
        )
        selected_roads = client.get(
            "/api/v1/layer-data/road_risk",
            params={
                "study_area": MAE_SAI,
                "area_id": "TH570901",
                "detail": "selected_area",
            },
        )

    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert {item["layer_id"] for item in catalog} == {
        "administrative_boundaries",
        "priority_areas",
        "road_risk",
        "facilities",
        "access_hotspots",
    }
    assert all(item["data_state"] == "stale" for item in catalog)
    assert all(item["dataset_mode"] == "candidate" for item in catalog)
    assert all(f"study_area={MAE_SAI}" in item["url"] for item in catalog)

    assert facilities.status_code == 200
    facility_payload = facilities.json()
    assert facility_payload["floodguard_query"]["returned_feature_count"] == len(
        facility_payload["features"]
    )
    for feature in facility_payload["features"]:
        properties = feature["properties"]
        assert properties["area_id"] == "TH570901"
        assert properties["verification_status"] == "open_context_candidate"
        assert properties["emergency_role"] == "no_confirmed_emergency_role"
        assert properties["public_visibility"] is False
        assert properties["official_warning"] is False
        assert properties["can_feed_decision_layer"] is False

    assert roads.status_code == 200
    assert len(roads.json()["features"]) <= 750
    assert all(
        feature["properties"]["road_disruption_probability_0_1"] >= 0.2
        for feature in roads.json()["features"]
    )
    assert all(
        feature["properties"]["observation_status"]
        == "modelled_candidate_not_observed"
        for feature in roads.json()["features"]
    )

    assert selected_roads.status_code == 200
    assert selected_roads.json()["features"]
    assert all(
        feature["properties"]["area_id"] == "TH570901"
        for feature in selected_roads.json()["features"]
    )


def test_candidate_layer_response_has_content_identity_and_conditional_cache() -> None:
    registry = DatasetRegistry()
    with TestClient(create_app(registry)) as client:
        response = client.get(
            "/api/v1/layer-data/access_hotspots",
            params={"study_area": MAE_SAI},
            headers={"Accept-Encoding": "gzip"},
        )
        cached = client.get(
            "/api/v1/layer-data/access_hotspots",
            params={"study_area": MAE_SAI},
            headers={"If-None-Match": response.headers["etag"]},
        )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert "Accept-Encoding" in response.headers["vary"]
    assert response.headers["x-floodguard-dataset-mode"] == "candidate"
    assert response.headers["x-floodguard-official-warning"] == "false"
    assert response.headers["x-floodguard-artifact-sha256"] == (
        registry.layer_artifact_sha256("access_hotspots", MAE_SAI)
    )
    assert response.headers["x-floodguard-content-sha256"] == hashlib.sha256(
        response.content
    ).hexdigest()
    assert response.headers["etag"].startswith('"sha256-')
    assert cached.status_code == 304
    assert cached.content == b""


def test_candidate_api_payloads_do_not_expose_private_paths() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        payloads = [
            client.get("/api/v1/status", params={"study_area": MAE_SAI}).json(),
            client.get("/api/v1/areas", params={"study_area": MAE_SAI}).json(),
            client.get("/api/v1/layers", params={"study_area": MAE_SAI}).json(),
            client.get(
                "/api/v1/layer-data/facilities",
                params={"study_area": MAE_SAI},
            ).json(),
        ]

    serialized = json.dumps(payloads, ensure_ascii=False).lower()
    assert "c:\\users\\" not in serialized
    assert "/home/" not in serialized
    assert "external_data_workspace" not in serialized


def test_candidate_filters_are_bounded_and_reject_cross_layer_parameters() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        invalid_selected = client.get(
            "/api/v1/layer-data/road_risk",
            params={"study_area": MAE_SAI, "detail": "selected_area"},
        )
        wrong_filter = client.get(
            "/api/v1/layer-data/priority_areas",
            params={"study_area": MAE_SAI, "minimum_risk": 0.1},
        )
        malformed_bbox = client.get(
            "/api/v1/layer-data/facilities",
            params={"study_area": MAE_SAI, "bbox": "99,20,100"},
        )
        unknown_study_area = client.get(
            "/api/v1/areas",
            params={"study_area": "substituted"},
        )

    assert invalid_selected.status_code == 422
    assert invalid_selected.json()["error"] == "invalid_layer_filter"
    assert wrong_filter.status_code == 422
    assert malformed_bbox.status_code == 422
    assert unknown_study_area.status_code == 422


def test_mae_sai_scenarios_use_only_pinned_graph_inputs_and_return_real_deltas() -> None:
    with TestClient(create_app(DatasetRegistry())) as client:
        catalog = client.get("/api/v1/scenarios", params={"study_area": MAE_SAI})
        shelter = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "add_temporary_shelter",
                "study_area": MAE_SAI,
                "parameters": {
                    "node_id": "N-99.9742609-20.4457677",
                    "capacity": 500,
                },
            },
        )
        closure = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "close_road",
                "study_area": MAE_SAI,
                "parameters": {"edge_id": "MS-EDGE-0008687"},
            },
        )
        invalid_node = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "add_temporary_shelter",
                "study_area": MAE_SAI,
                "parameters": {"node_id": "arbitrary", "capacity": 500},
            },
        )
        invalid_edge = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "close_road",
                "study_area": MAE_SAI,
                "parameters": {"edge_id": "arbitrary"},
            },
        )
        fetched = client.get(
            f"/api/v1/scenario-runs/{shelter.json()['run_id']}"
        )

    assert catalog.status_code == 200
    definitions = catalog.json()
    assert [item["scenario_id"] for item in definitions] == [
        "add_temporary_shelter",
        "close_road",
    ]
    assert definitions[0]["parameters"][0]["allowed_values"] == [
        "N-99.9742609-20.4457677"
    ]
    assert definitions[1]["parameters"][0]["allowed_values"] == [
        "MS-EDGE-0008687"
    ]
    assert all(
        item["backend_config_version"] == "mae-sai-candidate-access-scenarios-v1"
        for item in definitions
    )

    assert shelter.status_code == 201
    shelter_result = shelter.json()
    assert shelter_result["dataset_mode"] == "candidate"
    assert shelter_result["operational_status"] == "non_operational"
    assert shelter_result["official_warning"] is False
    assert shelter_result["fpps_recalculated"] is False
    assert shelter_result["result_state"] == "stale"
    assert shelter_result["input_manifest_sha256"] == (
        "20ce7a6d7007daeccbb64afcbabc00e447bb96de8c66eb44776a827be6c61a04"
    )
    assert shelter_result["input_receipt_sha256"] == (
        "b25fd06ab5f20f553acf252b63531d5355a63c1806e5bd647782bf2908dcc7a0"
    )
    assert shelter_result["overall"]["baseline_people_losing_30_min_access"] == 11114
    assert shelter_result["overall"]["scenario_people_losing_30_min_access"] == 10197
    assert shelter_result["overall"]["change_people_losing_30_min_access"] == -917
    assert shelter_result["overall"]["change_max_equity_gap_ratio"] == 0.0
    assert "capacity" in " ".join(shelter_result["assumptions"]).lower()
    assert fetched.status_code == 200
    assert fetched.json()["overall"] == shelter_result["overall"]

    assert closure.status_code == 201
    closure_result = closure.json()
    assert closure_result["run_id"] == (
        "mae-sai-candidate-close-edge-ms-edge-0008687-v1"
    )
    assert closure_result["overall"]["baseline_people_losing_30_min_access"] == 11114
    assert closure_result["overall"]["scenario_people_losing_30_min_access"] == 11212
    assert closure_result["overall"]["change_people_losing_30_min_access"] == 98
    assert closure_result["overall"]["change_max_equity_gap_ratio"] == 0.0
    assert "not an observed closure" in " ".join(closure_result["assumptions"])

    assert invalid_node.status_code == 422
    assert invalid_edge.status_code == 422


def test_candidate_artifact_substitution_blocks_status_decisions_and_layers(
    tmp_path: Path,
) -> None:
    paths = _copy_candidate_bundle(tmp_path)
    facility_path = paths.root / "outputs" / "mae_sai_facilities.geojson"
    facility_path.write_text(
        facility_path.read_text(encoding="utf-8").replace(
            "unverified_osm_candidate",
            "agency_verified",
            1,
        ),
        encoding="utf-8",
    )
    registry = DatasetRegistry(paths)

    with TestClient(create_app(registry)) as client:
        status = client.get("/api/v1/status", params={"study_area": MAE_SAI})
        decisions = client.get("/api/v1/areas", params={"study_area": MAE_SAI})
        layer = client.get(
            "/api/v1/layer-data/priority_areas",
            params={"study_area": MAE_SAI},
        )

    assert status.status_code == 200
    assert status.json()["data_state"] == "unavailable"
    assert status.json()["official_warning"] is False
    assert decisions.status_code == 503
    assert "checksum validation failed" in decisions.json()["detail"]
    assert layer.status_code == 503
    assert "checksum validation failed" in layer.json()["detail"]


def test_candidate_manifest_substitution_is_rejected_without_breaking_fixture(
    tmp_path: Path,
) -> None:
    paths = _copy_candidate_bundle(tmp_path)
    manifest_path = paths.root / MAE_SAI_MANIFEST_RELATIVE_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["official_warning"] = True
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    registry = DatasetRegistry(paths)

    with TestClient(create_app(registry)) as client:
        candidate = client.get("/api/v1/status", params={"study_area": MAE_SAI})
        fixture = client.get("/api/v1/status")

    assert candidate.status_code == 200
    assert candidate.json()["data_state"] == "unavailable"
    assert candidate.json()["official_warning"] is False
    assert "manifest checksum" in " ".join(candidate.json()["assumptions"])
    assert fixture.status_code == 200
    assert fixture.json()["dataset_mode"] == "fixture_demo"


def test_candidate_scenario_input_substitution_removes_catalog_and_blocks_run(
    tmp_path: Path,
) -> None:
    paths = _copy_candidate_bundle(tmp_path)
    edge_path = paths.outputs / "mae_sai_access_edges.csv"
    edge_path.write_text(
        edge_path.read_text(encoding="utf-8").replace(
            "MS-EDGE-0008687",
            "MS-EDGE-SUBSTITUTED",
            1,
        ),
        encoding="utf-8",
    )
    registry = DatasetRegistry(paths)

    with TestClient(create_app(registry)) as client:
        catalog = client.get("/api/v1/scenarios", params={"study_area": MAE_SAI})
        run = client.post(
            "/api/v1/scenario-runs",
            json={
                "scenario_id": "close_road",
                "study_area": MAE_SAI,
                "parameters": {"edge_id": "MS-EDGE-0008687"},
            },
        )

    assert catalog.status_code == 200
    assert catalog.json() == []
    assert run.status_code == 503
    assert "access_edges checksum validation failed" in run.json()["detail"]


def _copy_candidate_bundle(tmp_path: Path) -> RepositoryPaths:
    source = RepositoryPaths.discover()
    manifest_source = source.root / MAE_SAI_MANIFEST_RELATIVE_PATH
    manifest_payload = json.loads(manifest_source.read_text(encoding="utf-8"))
    scenario_manifest_source = source.root / MAE_SAI_SCENARIO_MANIFEST_RELATIVE_PATH
    scenario_payload = json.loads(scenario_manifest_source.read_text(encoding="utf-8"))
    relative_paths = [
        MAE_SAI_MANIFEST_RELATIVE_PATH,
        *(layer["relative_path"] for layer in manifest_payload["layers"]),
        MAE_SAI_SCENARIO_MANIFEST_RELATIVE_PATH,
        *(f"outputs/{artifact['relative_path']}" for artifact in scenario_payload["artifacts"]),
    ]
    for relative_path in relative_paths:
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.root / relative_path, destination)
    return RepositoryPaths(root=tmp_path)
