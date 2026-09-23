"""Publication checks exercise corruption and semantic lineage on open fixtures."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from shapely.geometry import box

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.evidence_context import (
    _NodeIndex,
    _osm_facilities,
    _road_graph,
    _snap_facilities,
)
from floodguard.evidence_finals import build_finals_analysis
from floodguard.evidence_finals_export import (
    load_finals,
    public_finals_database,
    verify_finals_analysis,
)
from floodguard.evidence_routes import build_pin_comparisons
from floodguard.evidence_validation import _finals_database


def resign(value):
    value["analysis_sha256"] = hashlib.sha256(
        canonical_bytes(
            {key: item for key, item in value.items() if key != "analysis_sha256"}
        )
    ).hexdigest()


@pytest.fixture
def finals():
    hashes = {
        key: str(index) * 64
        for index, key in enumerate(
            ("osm", "worldpop", "aoi_geometry", "routing_geometry"), 1
        )
    }
    roads = {
        "features": [
            {
                "type": "Feature",
                "properties": {"osm_id": "1", "highway": "residential"},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[100, 20], [100.001, 20], [100.002, 20]],
                },
            }
        ]
    }
    facilities = {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "2",
                    "amenity": "hospital",
                    "name": "Hospital",
                },
                "geometry": {"type": "Point", "coordinates": [100.002, 20]},
            },
            {
                "type": "Feature",
                "properties": {
                    "osm_id": "3",
                    "amenity": "pharmacy",
                    "name": "Pharmacy",
                },
                "geometry": {"type": "Point", "coordinates": [100.001, 20]},
            },
        ]
    }
    scope = box(99.99, 19.99, 100.01, 20.01)
    contexts = {}
    for mode in ("walking", "modelled_vehicle"):
        edges, nodes, _, coverage = _road_graph(
            roads,
            scope,
            travel_mode="walking" if mode == "walking" else "legacy_vehicle",
        )
        index = _NodeIndex(nodes)
        origin_node, _ = index.snap(100, 20, 100)
        context = {
            "population": [
                {
                    "population_id": "cell",
                    "subdistrict_id": "area",
                    "total_population": 100.0,
                    "node_id": origin_node,
                    "snap_distance_m": 0.0,
                    "longitude": 100,
                    "latitude": 20,
                    "population_reference_year": 2020,
                    "population_role": "modelled_residential_context",
                }
            ],
            "edges": edges,
            "node_coordinates": nodes,
            "osm_facilities": _snap_facilities(
                _osm_facilities(facilities), scope, index
            ),
            "coverage": coverage,
            "connectivity_review": coverage.pop("grade_connection_review"),
            "reviewed_junctions": [],
            "input_hashes": hashes.copy(),
            "assumptions": ["Synthetic non-operational test."],
            "official_warning": False,
            "source_metadata": {
                source: {
                    "download_url": f"https://example.test/{source}/download",
                    "license_status": "open_fixture",
                    "processing_scope": "context_only",
                    "retrieved_at_utc": "2026-09-21T00:00:00Z",
                    "sha256": hashes[source],
                    "source_name": source,
                    "source_url": f"https://example.test/{source}",
                }
                for source in ("osm", "worldpop")
            },
            "public_origins": [
                {
                    "origin_id": "official-municipality",
                    "name": "Municipal marker",
                    "longitude": 100,
                    "latitude": 20,
                    "node_id": origin_node,
                    "snap_distance_m": 0.0,
                    "source_url": "https://example.test/municipality",
                    "geometry_role": "official_site_marker_not_entrance",
                }
            ],
        }
        context["canonical_sha256"] = hashlib.sha256(
            canonical_bytes(context)
        ).hexdigest()
        contexts[mode] = context
    analysis, _ = build_finals_analysis(
        contexts,
        scope={
            "study_population": 105.0,
            "in_scope_population": 100.0,
            "excluded_population": 5.0,
        },
        timeline=[],
        generated_at="2026-09-21T00:00:00Z",
    )
    analysis["routes"] = build_pin_comparisons(contexts)
    resign(analysis)
    return deepcopy(analysis), contexts


def database_case(finals):
    analysis, contexts = finals
    payload = public_finals_database(analysis, contexts)
    package = {
        "aoi_id": "fixture-aoi",
        "decision_brief": {"finals_analysis": analysis},
        "input_hashes": contexts["walking"]["input_hashes"],
    }
    policies = {
        key: {"rights": {"public_derivatives": True}}
        for key in ("context-osm", "context-worldpop")
    }
    return payload, package, policies


def test_valid_finals_fixture_passes_both_semantic_gates(finals):
    verify_finals_analysis(finals[0])
    _finals_database(*database_case(finals))


def test_compact_report_binds_full_routes_without_duplicating_geometry(finals):
    from floodguard.evidence_pipeline import report_brief_projection

    analysis = deepcopy(finals[0])
    analysis["routes"] = {"large_route_coordinates": [[100, 20]] * 100000}
    analysis["flood_scenarios"] = {"walking": {
        "closed_edges": [{"edge_id": str(i)} for i in range(100000)],
        "impact": {"newly_unreachable_population": 30},
    }}
    brief = {"finals_analysis": analysis, "event_id": "fixture"}
    projected = report_brief_projection(brief)
    compact = projected["finals_analysis"]
    assert compact["analysis_sha256"] == analysis["analysis_sha256"]
    assert compact["services"] == analysis["services"]
    assert compact["flood_scenarios"]["walking"] == {
        "closed_edge_count": 100000, "impact": {"newly_unreachable_population": 30}}
    assert len(canonical_bytes(projected)) < 100000
    assert len(brief["finals_analysis"]["routes"]["large_route_coordinates"]) == 100000


def test_healthcare_exclusion_requires_matching_source_bound_review(finals):
    from floodguard.evidence_validation import DATABASE_KEYS, _database

    payload, package, policies = database_case(finals)
    context = payload["contexts"]["walking"]
    base = {key: value for key, value in context.items() if key in DATABASE_KEYS}
    site = base["osm_facilities"][0]
    site["candidate_destination_eligible"] = False
    with pytest.raises(ValueError, match="Destination eligibility"):
        _database(base, package, policies)
    review = {"osm_sha256": base["input_hashes"]["osm"], "exclusions": [
        {"facility_id": site["facility_id"], "reason": "Fixture role is unsuitable for general hospital access.",
         "source_url": "https://example.test/facility"}
    ]}
    with pytest.raises(ValueError, match="recorded review"):
        _database(base, package, policies, destination_review=review)
    site["identity_review_status"] = review["exclusions"][0]["reason"]
    _database(base, package, policies, destination_review=review)
    review["osm_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="another OSM"):
        _database(base, package, policies, destination_review=review)


def test_generic_shelter_cannot_be_enabled_by_destination_review(finals):
    from floodguard.evidence_validation import DATABASE_KEYS, _database

    payload, package, policies = database_case(finals)
    context = payload["contexts"]["walking"]
    base = {key: value for key, value in context.items() if key in DATABASE_KEYS}
    base["osm_facilities"][0]["facility_type"] = "shelter_context"
    with pytest.raises(ValueError, match="generic OSM shelter"):
        _database(base, package, policies, destination_review={"osm_sha256": base["input_hashes"]["osm"], "exclusions": []})


def test_connectivity_download_hash_binds_exported_not_local_only_fields(finals):
    from floodguard.evidence_connectivity import audit_connectivity

    analysis, contexts = finals
    analysis["connectivity_audits"] = {}
    for mode, context in contexts.items():
        context["population"][0]["local_review_note"] = "Not a published input"
        sites = [r for r in context["osm_facilities"] if r["service_type"] == "hospital"]
        analysis["connectivity_audits"][mode] = audit_connectivity(
            context["population"], context["edges"], sites,
            source_timestamp=context["source_metadata"]["osm"]["retrieved_at_utc"],
        )
    resign(analysis)
    payload, package, policies = database_case((analysis, contexts))
    assert "local_review_note" not in payload["contexts"]["walking"]["population"][0]
    assert payload["connectivity_audits"]["walking"]["baseline_input_sha256"] != analysis["connectivity_audits"]["walking"]["baseline_input_sha256"]
    _finals_database(payload, package, policies)


def test_corrupted_analysis_digest_rejected(finals):
    analysis = finals[0]
    analysis["question"] = "Changed without recomputing identity"
    with pytest.raises(ValueError, match="identity"):
        verify_finals_analysis(analysis)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda a: a["scope"].update(excluded_population=6), "conserve"),
        (lambda a: a["capacity"].update(site_id="hypothetical-wrong-node"), "location"),
        (lambda a: a["capacity"].update(actual_available_capacity=100), "actual"),
        (lambda a: a["capacity"]["experiments"][0].update(assigned=6), "conserve"),
        (
            lambda a: a["services"][0]["variants"][1]["interventions"][0].update(
                target_id="other-candidate"
            ),
            "shortlist",
        ),
    ],
)
def test_resigned_semantic_corruption_is_rejected(finals, mutation, message):
    analysis = finals[0]
    mutation(analysis)
    resign(analysis)
    with pytest.raises(ValueError, match=message):
        verify_finals_analysis(analysis)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda r: r["baseline"]["edge_ids"].__setitem__(0, "absent-edge"),
            "absent edge",
        ),
        (lambda r: r["baseline"].update(destination_id="OSM-node-3"), "service"),
        (lambda r: r["baseline"]["coordinates"][0].__setitem__(0, 101), "geometry"),
    ],
)
def test_route_edge_geometry_and_service_lineage_rejected(finals, mutation, message):
    analysis = finals[0]
    comparison = next(
        row
        for row in analysis["routes"]["comparisons"]
        if row["service_type"] == "hospital" and row["baseline"]["edge_ids"]
    )
    mutation(comparison)
    resign(analysis)
    with pytest.raises(ValueError, match=f"{message}|recomputation"):
        _finals_database(*database_case(finals))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


@pytest.fixture
def local_finals(finals, tmp_path):
    analysis, contexts = finals
    write(tmp_path / "analysis.json", analysis)
    for mode, context in contexts.items():
        write(tmp_path / "contexts" / mode / "context_inputs.json", context)
    receipt = {
        "aoi_sha256": "a" * 64,
        "generated_at": analysis["generated_at"],
        "builder_sha256": sha256_file(
            Path(__file__).resolve().parents[1] / "scripts/build_mae_sai_finals.py"
        ),
        "analysis_sha256": sha256_file(tmp_path / "analysis.json"),
        "context_hashes": {
            mode: ctx["canonical_sha256"] for mode, ctx in contexts.items()
        },
        "implementation": {},
        "files": {
            path.relative_to(tmp_path).as_posix(): sha256_file(path)
            for path in tmp_path.rglob("*.json")
        },
    }
    write(tmp_path / "build_receipt.json", receipt)
    return tmp_path, receipt


def test_local_load_checks_bytes_aoi_missing_parent_and_unsafe_path(local_finals):
    root, receipt = local_finals
    load_finals(root, aoi_sha256="a" * 64)
    with pytest.raises(ValueError, match="AOI"):
        load_finals(root, aoi_sha256="b" * 64)
    receipt["files"]["../outside.json"] = "0" * 64
    write(root / "build_receipt.json", receipt)
    with pytest.raises(ValueError, match="Unsafe"):
        load_finals(root, aoi_sha256="a" * 64)
    del receipt["files"]["../outside.json"]
    write(root / "build_receipt.json", receipt)
    (root / "contexts/walking/context_inputs.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        load_finals(root, aoi_sha256="a" * 64)


def test_local_changed_parent_bytes_are_rejected(local_finals):
    root, _ = local_finals
    with (root / "contexts/walking/context_inputs.json").open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="checksum"):
        load_finals(root, aoi_sha256="a" * 64)


def test_local_generation_time_is_bound_to_receipt(local_finals):
    root, receipt = local_finals
    receipt["generated_at"] = "2026-01-01T00:00:00Z"
    write(root / "build_receipt.json", receipt)
    with pytest.raises(ValueError, match="generation time"):
        load_finals(root, aoi_sha256="a" * 64)


def test_case_identity_cannot_override_receipt_geography(local_finals):
    root, receipt = local_finals
    analysis = json.loads((root / "analysis.json").read_bytes())
    analysis["case_identity"] = {"aoi_id": "another-area", "aoi_sha256": "b" * 64}
    resign(analysis)
    write(root / "analysis.json", analysis)
    receipt["analysis_sha256"] = receipt["files"]["analysis.json"] = sha256_file(root / "analysis.json")
    write(root / "build_receipt.json", receipt)
    with pytest.raises(ValueError, match="analysis AOI"):
        load_finals(root, aoi_sha256="a" * 64)


@pytest.mark.parametrize("missing", [True, False])
def test_local_builder_identity_is_required_and_bound(local_finals, missing):
    root, receipt = local_finals
    if missing:
        del receipt["builder_sha256"]
    else:
        receipt["builder_sha256"] = "0" * 64
    write(root / "build_receipt.json", receipt)
    with pytest.raises(ValueError, match="builder identity"):
        load_finals(root, aoi_sha256="a" * 64)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row["baseline"].update(total_minutes=777.0),
        lambda row: row["baseline"]["connectors"][0][0].__setitem__(0, 101.0),
        lambda row: row.update(delta_minutes=777.0),
        lambda row: row.update(changed_ids=["unknown-closed-edge"]),
    ],
)
def test_route_cost_connector_delta_and_change_recomputed(finals, mutation):
    comparison = next(
        row
        for row in finals[0]["routes"]["comparisons"]
        if row["service_type"] == "hospital" and row["scenario_kind"] == "close_edge"
    )
    mutation(comparison)
    resign(finals[0])
    with pytest.raises(ValueError):
        _finals_database(*database_case(finals))


def test_unrelated_public_origin_fields_are_excluded(finals):
    analysis, contexts = finals
    contexts["walking"]["public_origins"][0]["unrelated_private_notes"] = (
        "unrelated fixture content"
    )
    projected = public_finals_database(analysis, contexts)
    assert (
        "unrelated_private_notes"
        not in projected["contexts"]["walking"]["public_origins"][0]
    )


def test_variant_with_another_context_identity_is_rejected(finals):
    finals[0]["services"][0]["variants"][0]["context_sha256"] = "f" * 64
    resign(finals[0])
    with pytest.raises(ValueError, match="context"):
        _finals_database(*database_case(finals))


def test_capacity_service_cannot_substitute_another_linked_variant_service(finals):
    analysis = finals[0]
    assert analysis["capacity"]["linked_service"] == "hospital"
    analysis["capacity"]["linked_service"] = "pharmacy"
    resign(analysis)
    with pytest.raises(ValueError, match="Capacity service"):
        verify_finals_analysis(analysis)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda row: row.update(places=1), "exceeds scenario capacity"),
        (
            lambda row: row.update(assigned=row["assigned"] + 1, capacity_limited=-1),
            "nonnegative",
        ),
        (lambda row: row.update(participation_fraction=0.10), "participation"),
        (lambda row: row.update(participation_fraction=1.01), "participation"),
        (lambda row: row.update(places=-1), "nonnegative"),
        (lambda row: row.update(places=True), "nonnegative"),
    ],
)
def test_capacity_physical_bounds_and_declared_demand_are_checked(
    finals, mutation, message
):
    analysis = finals[0]
    experiment = analysis["capacity"]["experiments"][0]
    assert experiment["assumed_demand"] == 5
    mutation(experiment)
    resign(analysis)
    with pytest.raises(ValueError, match=message):
        verify_finals_analysis(analysis)
