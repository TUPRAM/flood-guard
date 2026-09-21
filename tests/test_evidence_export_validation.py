"""Small complete exports exercise byte integrity and publication boundaries."""

from __future__ import annotations

import copy
import gzip
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

import pytest

from floodguard.evidence_catalog import canonical_bytes, sha256_file
from floodguard.evidence_pipeline import SUPPORTING, _assessment
from floodguard.evidence_validation import (
    EvidenceValidationError,
    _geometry_hash,
    verify_evidence_library,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


@pytest.fixture
def exported(tmp_path):
    public, local = tmp_path / "public", tmp_path / "local"
    aoi_id, event = "aoi-01_mae_sai_core", "mae_sai_2024"
    identifier = aoi_id + "_" + event
    geometry = {
        "type": "Polygon",
        "coordinates": [[[99, 20], [100, 20], [100, 21], [99, 21], [99, 20]]],
    }
    aoi = {
        "id": aoi_id,
        "name": "Mae Sai core",
        "geometry": geometry,
        "event_ids": [event],
        "sha256": "a" * 64,
    }
    scenarios = {"aoi_id": aoi_id, "synthetic": True}
    scenario_hash = hashlib.sha256(canonical_bytes(scenarios)).hexdigest()
    hashes = {
        "osm": "1" * 64,
        "worldpop": "2" * 64,
        "aoi_geometry": _geometry_hash(geometry),
        "routing_geometry": "3" * 64,
    }
    database = {
        "license": "ODbL 1.0 and CC BY 4.0",
        "source_urls": ["https://www.openstreetmap.org/copyright"],
        "attribution": ["OpenStreetMap contributors", "WorldPop"],
        "confidence_class": "low",
        "source_timestamp": None,
        "source_metadata": {
            source: {
                "download_url": f"https://example.org/{source}/source",
                "license_status": "fixture_public_context",
                "processing_scope": "historical_context_only",
                "retrieved_at_utc": "2026-07-10T02:46:49Z",
                "sha256": hashes[source],
                "source_name": source,
                "source_url": f"https://example.org/{source}",
            }
            for source in ("osm", "worldpop")
        },
        "non_operational": True,
        "official_warning": False,
        "dataset_mode": "candidate",
        "assumptions": ["Modelled context"],
        "input_hashes": hashes,
        "analysis_crs": "EPSG:32647",
        "node_coordinates": {},
        "population": [],
        "edges": [],
        "osm_facilities": [],
        "coverage": {},
    }
    package = {
        "schema_version": "1.0",
        "package_version": "fixture-v1",
        "id": identifier,
        "aoi_id": aoi_id,
        "event_id": event,
        "generated_at": "2026-09-21T00:00:00Z",
        "input_hashes": {
            **hashes,
            "aoi_sha256": aoi["sha256"],
            "source_inventory_sha256": "b" * 64,
            "scenario_sha256": scenario_hash,
        },
        "dataset_mode": "candidate",
        "official_warning": False,
        "operational_status": "non_operational",
        "datasets": [],
        "layers": [],
        "gauges": [],
        "assessment": _assessment(aoi_id),
        "scenarios": [],
        "report_url": "/evidence-library/report.html",
        "source_timestamp": None,
        "confidence_class": "low",
        "assumptions": [],
    }
    catalog = {
        "schema_version": "1.0",
        "generated_at": package["generated_at"],
        "package_version": "fixture-v1",
        "non_operational": True,
        "aois": [aoi],
        "events": [
            {
                "id": event,
                "name": "September flood",
                "start": "2024-09-01",
                "end": "2024-09-30",
            }
        ],
        "datasets": copy.deepcopy(SUPPORTING),
        "packages": [
            {
                "id": identifier,
                "aoi_id": aoi_id,
                "event_id": event,
                "url": "/evidence-library/packages/" + identifier + ".json",
                "sha256": "0" * 64,
            }
        ],
    }
    registry = {
        "source_inventory_sha256": "b" * 64,
        "aois": [aoi],
        "datasets": [],
        "assets": [
            {
                "id": "raw",
                "relative_path": "source.csv",
                "sha256": "c" * 64,
                "parent_asset_ids": [],
                "parent_hashes": [],
            },
            {
                "id": "derived",
                "relative_path": "derived.csv",
                "sha256": "d" * 64,
                "parent_asset_ids": ["raw"],
                "parent_hashes": ["c" * 64],
            },
        ],
    }
    write(local / "scenarios" / f"{aoi_id}.json", scenarios)
    write(local / "normalized" / "summary.json", {"observations": None})
    write(
        local / "normalization_receipt.json",
        {
            "key": "e" * 64,
            "outputs": {
                "normalized/summary.json": sha256_file(
                    local / "normalized/summary.json"
                )
            },
        },
    )
    value = {
        "public": public,
        "local": local,
        "package": package,
        "catalog": catalog,
        "registry": registry,
        "database": database,
    }
    refresh(value)
    return value


def refresh(value):
    public, local, package, catalog = (
        value[k] for k in ("public", "local", "package", "catalog")
    )
    database = public / "databases" / f"{package['aoi_id']}.json.gz"
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(gzip.compress(canonical_bytes(value["database"]), mtime=0))
    package["downloads"] = [
        {
            "title": "Public scenario database",
            "url": "/evidence-library/databases/" + database.name,
            "sha256": sha256_file(database),
        }
    ]
    package_path = public / "packages" / f"{package['id']}.json"
    write(package_path, package)
    catalog["packages"][0]["sha256"] = sha256_file(package_path)
    write(public / "catalog.json", catalog)
    appendix = {
        "package_version": catalog["package_version"],
        "aois": catalog["aois"],
        "datasets": catalog["datasets"],
        "downloadable_packages": catalog["packages"],
    }
    if "decision_brief" in package:
        appendix["decision_briefs"] = [package["decision_brief"]]
    report = "<html><pre>" + html.escape(json.dumps(appendix)) + "</pre></html>"
    if value.get("compact_report"):
        from floodguard.evidence_pipeline import render_report

        details = json.loads(
            (local / "scenarios" / f"{package['aoi_id']}.json").read_text(
                encoding="utf-8"
            )
        )
        report = render_report(
            catalog,
            [package],
            value["registry"] | {"verified_asset_count": 2},
            {},
            {"routes": []},
            {package["aoi_id"]: details},
        )
    (public / "report.html").write_text(report, encoding="utf-8")
    write(local / "evidence_registry.json", value["registry"])
    write(
        local / "packages" / f"{package['id']}.json",
        {
            **package,
            "local_detail_files": {"scenarios": f"scenarios/{package['aoi_id']}.json"},
        },
    )
    write(
        local / "public_export_report.json",
        {
            "package_version": catalog["package_version"],
            "files": {
                p.relative_to(public).as_posix(): sha256_file(p)
                for p in public.rglob("*")
                if p.is_file()
            },
        },
    )


def test_complete_export_and_optional_local_receipts(exported):
    result = verify_evidence_library(exported["public"], local_dir=exported["local"])
    assert result["status"] == "passed" and result["public_files"] == 4
    assert result["gzip_databases"] == 1 and result["local_verification"]["assets"] == 2
    assert result["scientific_or_operational_acceptance"] is False
    assert verify_evidence_library(exported["public"])["local_verification"] is None


@pytest.mark.parametrize(
    "change,match",
    [
        (lambda p: p.update(package_version="mixed-v2"), "Mixed package version"),
        (
            lambda p: p["input_hashes"].update(aoi_sha256="f" * 64),
            "AOI geometry source",
        ),
        (
            lambda p: p["input_hashes"].update(aoi_geometry="f" * 64),
            "AOI geometry content",
        ),
        (lambda p: p.update(event_id="hat_yai_2025"), "Mixed package event_id"),
        (lambda p: p["assessment"].update(fpps=50), "Schema"),
        (lambda p: p["assessment"]["components"][0].update(weight=0.5), "weights"),
    ],
)
def test_resealed_inconsistent_package_is_rejected(exported, change, match):
    change(exported["package"])
    refresh(exported)
    with pytest.raises(EvidenceValidationError, match=match):
        verify_evidence_library(exported["public"])


@pytest.mark.parametrize(
    "url",
    [
        "/evidence-library/../private.json",
        "//evil.test/package.json",
        "/evidence-library/packages//entry.json",
        "file:///private.json",
    ],
)
def test_unsafe_public_paths_rejected(exported, url):
    exported["catalog"]["packages"][0]["url"] = url
    refresh(exported)
    with pytest.raises(ValueError, match="Schema|Unsafe|Missing public"):
        verify_evidence_library(exported["public"])


@pytest.mark.parametrize("alter", ["missing", "hash"])
def test_missing_parent_and_wrong_parent_hash_rejected(exported, alter):
    child = exported["registry"]["assets"][1]
    child["parent_asset_ids" if alter == "missing" else "parent_hashes"] = [
        "absent" if alter == "missing" else "e" * 64
    ]
    refresh(exported)
    with pytest.raises(ValueError, match="parent asset"):
        verify_evidence_library(exported["public"], local_dir=exported["local"])


def test_scenario_role_never_bypasses_source_publication_rights(exported):
    restricted = copy.deepcopy(SUPPORTING[0])
    restricted.update(id="dataset-12", role="historical_context")
    restricted["rights"]["public_derivatives"] = False
    exported["catalog"]["datasets"].append(restricted)
    exported["package"]["layers"] = [
        {
            "id": "restricted",
            "title": "Relabelled source",
            "dataset_id": "dataset-12",
            "role": "scenario",
            "availability": "available",
            "reason": None,
            "data": {"type": "FeatureCollection", "features": []},
        }
    ]
    refresh(exported)
    with pytest.raises(ValueError, match="not permitted"):
        verify_evidence_library(exported["public"])
    restricted["rights"]["public_derivatives"] = True
    refresh(exported)
    with pytest.raises(ValueError, match="self-authorize"):
        verify_evidence_library(exported["public"])


def test_gzip_strict_source_projection_and_personal_fields(exported):
    exported["database"]["supplied_facilities"] = []
    refresh(exported)
    with pytest.raises(ValueError, match="Unexpected source keys"):
        verify_evidence_library(exported["public"])
    del exported["database"]["supplied_facilities"]
    exported["database"]["coverage"]["phone"] = "private"
    refresh(exported)
    with pytest.raises(ValueError, match="Private field"):
        verify_evidence_library(exported["public"])


def test_gzip_bytes_and_unlisted_files_rejected(exported):
    file = next((exported["public"] / "databases").glob("*.gz"))
    file.write_bytes(file.read_bytes() + b"altered")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_evidence_library(exported["public"])
    refresh(exported)
    (exported["public"] / "unlisted.csv").write_text("raw source")
    with pytest.raises(ValueError, match="Unlisted"):
        verify_evidence_library(exported["public"])


def test_normalized_bytes_and_local_selection_cannot_drift(exported):
    (exported["local"] / "normalized/summary.json").write_text("{}")
    with pytest.raises(ValueError, match="normalized output"):
        verify_evidence_library(exported["public"], local_dir=exported["local"])
    write(exported["local"] / "normalized/summary.json", {"observations": None})
    path = next((exported["local"] / "packages").glob("*.json"))
    package = json.loads(path.read_text())
    package["datasets"] = [{"dataset_id": "other-selection"}]
    write(path, package)
    with pytest.raises(ValueError, match="Mixed local/public package datasets"):
        verify_evidence_library(exported["public"], local_dir=exported["local"])


def test_cli_writes_external_receipt(exported, tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/verify_evidence_library.py"
    output = tmp_path / "verification.json"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--public-dir",
            str(exported["public"]),
            "--local-dir",
            str(exported["local"]),
            "--output-receipt",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())["status"] == "passed"


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("unexpected", "not projected", "Unexpected source metadata keys"),
        ("source_url", "http://example.org/source", "must use HTTPS"),
        ("download_url", "https:///source", "must use HTTPS"),
        ("download_url", "https://user:secret@example.org/source", "must use HTTPS"),
        ("retrieved_at_utc", "2026-07-10T02:46:49+08:00", "valid UTC"),
        ("retrieved_at_utc", "2026-07-10T02:46:49", "valid UTC"),
        ("retrieved_at_utc", "2026-02-30T02:46:49Z", "valid UTC"),
        ("sha256", "f" * 64, "SHA256 mismatch: source metadata"),
    ],
)
def test_source_metadata_cannot_claim_unbound_retrieval_or_sources(
    exported, field, value, match
):
    exported["database"]["source_metadata"]["osm"][field] = value
    refresh(exported)
    with pytest.raises(ValueError, match=match):
        verify_evidence_library(exported["public"])


def test_source_metadata_requires_both_sources_and_keeps_observation_time_unknown(
    exported,
):
    exported["database"]["source_metadata"]["osm"]["retrieved_at_utc"] = (
        "2026-07-10T02:46:49+00:00"
    )
    refresh(exported)
    assert verify_evidence_library(exported["public"])["status"] == "passed"
    assert exported["database"]["source_timestamp"] is None
    del exported["database"]["source_metadata"]["worldpop"]
    refresh(exported)
    with pytest.raises(ValueError, match="exactly OSM and WorldPop"):
        verify_evidence_library(exported["public"])


@pytest.fixture
def brief_export(exported, monkeypatch):
    from floodguard.evidence_decision_brief import build_decision_brief
    from floodguard.evidence_event_review import BOUNDARY_SOURCE
    from floodguard.evidence_pipeline import _supporting_dataset

    package, local = exported["package"], exported["local"]
    brief = build_decision_brief(
        aoi_id=package["aoi_id"],
        event_id=package["event_id"],
        generated_at=package["generated_at"],
        context=None,
        details={},
    )
    brief.update(
        status="scenario_only",
        population_reference_year=2020,
        access={
            "modelled_population": 100,
            "unknown_access_population": 10,
            "connected_without_route_population": 20,
            "over_30_minutes_population": 30,
            "within_30_minutes_population": 40,
        },
    )
    brief["reporting"].update(
        status="available",
        source_url=BOUNDARY_SOURCE["source_url"],
        reference_date="2022-01-22",
        coverage_fraction=0.5,
        unassigned_modelled_population=10,
        units=[
            {
                "id": "TH570901",
                "name": "Fixture unit",
                "name_th": "Fixture unit",
                "scope": "full_unit",
                "unit_coverage_fraction": 1,
                "intersection_area_km2": 1,
                "population_context": {
                    **brief["access"],
                    "modelled_population": 90,
                    "unknown_access_population": 0,
                },
                "affected_population": None,
                "fpps": None,
                "action_class": None,
                "interventions": [],
            }
        ],
    )
    brief["capacity_experiments"] = [
        {
            "id": "capacity-test",
            "title": "Hypothetical fixture",
            "participation_fraction": 0.1,
            "residential_population": 100,
            "demand_basis": "residential_participation",
            "actual_evacuation_demand": None,
            "actual_available_capacity": None,
            "assumed_demand": 10,
            "assigned": 4,
            "capacity_limited": 3,
            "unreachable": 2,
            "coverage_excluded": 1,
            "unknown_capacity": 0,
        }
    ]
    package["decision_brief"] = brief
    boundary = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"adm3_pcode": "TH570901"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[99, 20], [99.5, 20], [99.5, 21], [99, 21], [99, 20]]
                    ],
                },
            }
        ],
    }
    package["layers"].append(
        {
            "id": "reporting-subdistricts",
            "title": "Fixture reporting boundaries",
            "role": "static_context",
            "dataset_id": "context-admin",
            "availability": "partial",
            "reason": "Partial coverage",
            "data": boundary,
        }
    )
    exported["catalog"]["datasets"].append(
        _supporting_dataset(
            "context-admin",
            "Fixture reporting units",
            "CC BY 3.0 IGO",
            BOUNDARY_SOURCE["source_url"],
            "static_context",
            ["Synthetic test geometry"],
        )
    )
    proof_files = [
        "population_group_review.json",
        "destination_identity_review.json",
        "capacity_assumptions.json",
    ]
    for name in proof_files:
        write(local / "review" / name, {"fixture": name})
    population = {
        "local_review_files": {
            name: sha256_file(local / "review" / name) for name in proof_files
        }
    }
    write(local / "review/population_review_summary.json", population)
    write(local / "event_review/reporting_units.geojson", boundary)
    write(
        local / "event_review/reporting_crosswalk.json",
        {
            "aois": [
                {
                    "aoi_id": package["aoi_id"],
                    "coverage_fraction": 0.5,
                    "units": [
                        {
                            "adm3_pcode": "TH570901",
                            "scope": "full_unit",
                            "unit_coverage_fraction": 1,
                            "intersection_area_km2": 1,
                        }
                    ],
                }
            ]
        },
    )
    write(
        local / "event_review/event_evidence_review.json",
        {"event_context_eligible_count": 0},
    )
    write(
        local / "acquisition/event_review/hdx_cod_ab_metadata.json",
        {"fixture": "metadata"},
    )
    legal = local / "acquisition/event_review/cc_by_igo_3_legalcode.html"
    legal.write_bytes(b"fixture terms, not an actual legal instrument")
    monkeypatch.setitem(BOUNDARY_SOURCE, "license_snapshot_sha256", sha256_file(legal))
    event = {
        "boundary_source": dict(BOUNDARY_SOURCE),
        "input_hashes": {
            "boundary_archive": BOUNDARY_SOURCE["source_sha256"],
            "boundary_metadata": sha256_file(
                local / "acquisition/event_review/hdx_cod_ab_metadata.json"
            ),
            "boundary_license": sha256_file(legal),
        },
        **{
            key: {"path": name, "sha256": sha256_file(local / "event_review" / name)}
            for key, name in (
                ("reporting_units", "reporting_units.geojson"),
                ("crosswalk", "reporting_crosswalk.json"),
                ("event_evidence", "event_evidence_review.json"),
            )
        },
    }
    write(local / "event_review/summary.json", event)
    package["input_hashes"].update(
        population_review_sha256=hashlib.sha256(
            canonical_bytes(population)
        ).hexdigest(),
        event_review_sha256=hashlib.sha256(canonical_bytes(event)).hexdigest(),
    )
    exported["registry"]["supplementary_evidence_hashes"] = {
        path.relative_to(local).as_posix(): sha256_file(path)
        for directory in ("review", "event_review", "acquisition/event_review")
        for path in (local / directory).rglob("*")
        if path.is_file()
    }
    refresh(exported)
    return exported


def test_new_brief_and_review_proofs_pass_independent_and_local_checks(brief_export):
    assert verify_evidence_library(brief_export["public"])["status"] == "passed"
    result = verify_evidence_library(
        brief_export["public"], local_dir=brief_export["local"]
    )
    assert result["local_verification"]["supplementary_proofs"] == 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("aoi_id", "another-aoi"),
        ("event_id", "another-event"),
        ("generated_at", "2026-09-20T00:00:00Z"),
    ],
)
def test_resealed_brief_identity_cannot_differ_from_package(brief_export, field, value):
    brief_export["package"]["decision_brief"][field] = value
    refresh(brief_export)
    with pytest.raises(ValueError, match="Mixed decision brief"):
        verify_evidence_library(brief_export["public"])


@pytest.mark.parametrize("part", ["aoi", "unit", "reporting", "capacity"])
def test_resealed_brief_inconsistent_partitions_rejected(brief_export, part):
    brief = brief_export["package"]["decision_brief"]
    if part == "aoi":
        brief["access"]["unknown_access_population"] = 20
    elif part == "unit":
        brief["reporting"]["units"][0]["population_context"][
            "unknown_access_population"
        ] = 5
    elif part == "reporting":
        brief["reporting"]["unassigned_modelled_population"] = 20
    else:
        brief["capacity_experiments"][0]["assigned"] = 8
    refresh(brief_export)
    with pytest.raises(ValueError, match="partition differs"):
        verify_evidence_library(brief_export["public"])


@pytest.mark.parametrize("change", ["duplicate", "wrong_code"])
def test_reporting_identity_binds_published_geometry(brief_export, change):
    units = brief_export["package"]["decision_brief"]["reporting"]["units"]
    if change == "duplicate":
        units.append(copy.deepcopy(units[0]))
    else:
        units[0]["id"] = "TH570999"
    refresh(brief_export)
    with pytest.raises(ValueError, match="reporting unit"):
        verify_evidence_library(brief_export["public"])


def test_local_brief_cannot_differ_even_when_other_package_fields_match(brief_export):
    path = brief_export["local"] / "packages" / f"{brief_export['package']['id']}.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    package["decision_brief"]["limitations"].append("Changed local proof")
    write(path, package)
    with pytest.raises(ValueError, match="Mixed local/public package decision_brief"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


@pytest.mark.parametrize("name", ["population_review_sha256", "event_review_sha256"])
def test_review_summary_hash_binding_cannot_be_dropped_or_changed(brief_export, name):
    brief_export["package"]["input_hashes"][name] = "f" * 64
    refresh(brief_export)
    with pytest.raises(ValueError, match="review summary"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])
    del brief_export["package"]["input_hashes"][name]
    refresh(brief_export)
    with pytest.raises(ValueError, match="lacks .* review binding"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


@pytest.mark.parametrize(
    "name",
    [
        "review/population_group_review.json",
        "event_review/reporting_units.geojson",
        "acquisition/event_review/cc_by_igo_3_legalcode.html",
    ],
)
def test_supplementary_bytes_are_reverified(brief_export, name):
    path = brief_export["local"] / name
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="supplementary evidence"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


def test_unlisted_or_removed_supplementary_manifest_entries_rejected(brief_export):
    del brief_export["registry"]["supplementary_evidence_hashes"][
        "review/capacity_assumptions.json"
    ]
    refresh(brief_export)
    with pytest.raises(ValueError, match="proof inventory differs"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


@pytest.mark.parametrize(
    "name,match",
    [
        ("review/population_group_review.json", "population review proof"),
        ("event_review/reporting_units.geojson", "event review proof"),
        ("acquisition/event_review/cc_by_igo_3_legalcode.html", "event review input"),
    ],
)
def test_resealed_registry_does_not_override_review_proof_hashes(
    brief_export, name, match
):
    path = brief_export["local"] / name
    path.write_bytes(path.read_bytes() + b" ")
    brief_export["registry"]["supplementary_evidence_hashes"][name] = sha256_file(path)
    refresh(brief_export)
    with pytest.raises(ValueError, match=match):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


def test_report_brief_cannot_drift_from_verified_package(brief_export):
    path = brief_export["public"] / "report.html"
    data = {
        "package_version": brief_export["catalog"]["package_version"],
        "aois": brief_export["catalog"]["aois"],
        "datasets": brief_export["catalog"]["datasets"],
        "downloadable_packages": brief_export["catalog"]["packages"],
        "decision_briefs": [],
    }
    path.write_text(
        "<html><pre>" + html.escape(json.dumps(data)) + "</pre></html>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Mixed report decision briefs"):
        verify_evidence_library(brief_export["public"])


def test_resealed_public_geometry_cannot_drift_from_local_reporting_proof(brief_export):
    geometry = brief_export["package"]["layers"][0]["data"]["features"][0]["geometry"]
    geometry["coordinates"][0][1][0] = 99.6
    refresh(brief_export)
    with pytest.raises(ValueError, match="Public reporting geometry differs"):
        verify_evidence_library(brief_export["public"], local_dir=brief_export["local"])


@pytest.fixture
def compact_export(exported):
    exported["compact_report"] = True
    refresh(exported)
    return exported


def report_appendix(value):
    from floodguard.evidence_validation import _ReportParser

    parser = _ReportParser()
    parser.feed((value["public"] / "report.html").read_text(encoding="utf-8"))
    assert len(parser.receipts) == 1
    return json.loads(parser.receipts[0])


def replace_appendix(value, appendix):
    (value["public"] / "report.html").write_text(
        "<html><pre>" + html.escape(json.dumps(appendix)) + "</pre></html>",
        encoding="utf-8",
    )


def test_compact_report_binds_downloads_inputs_and_exact_local_aggregates(
    compact_export,
):
    result = verify_evidence_library(
        compact_export["public"], local_dir=compact_export["local"]
    )
    assert result["status"] == "passed"
    appendix = report_appendix(compact_export)
    package = compact_export["package"]
    assert appendix["package_inputs"][package["id"]] == package["input_hashes"]
    assert appendix["package_downloads"][package["id"]] == package["downloads"]
    html_text = (compact_export["public"] / "report.html").read_text(encoding="utf-8")
    assert compact_export["catalog"]["packages"][0]["url"] in html_text
    assert compact_export["catalog"]["packages"][0]["sha256"] in html_text


@pytest.mark.parametrize(
    "change,match",
    [
        ("details", "Detailed records"),
        ("inputs", "Mixed report input"),
        ("downloads", "Mixed report database"),
        ("summaries", "Mixed report scenario"),
        ("unknown_projection", "Unknown report projection"),
        ("private", "Private field"),
    ],
)
def test_compact_projection_cannot_reintroduce_rows_or_lose_bindings(
    compact_export, change, match
):
    appendix = report_appendix(compact_export)
    package = compact_export["package"]
    if change == "details":
        appendix["scenarios"][package["aoi_id"]][
            "capacity_participation_sensitivity"
        ] = [{"population_results": []}]
    elif change == "inputs":
        appendix["package_inputs"][package["id"]]["scenario_sha256"] = "f" * 64
    elif change == "downloads":
        appendix["package_downloads"][package["id"]] = []
    elif change == "summaries":
        appendix["scenarios"][package["aoi_id"]]["summaries"] = [{"invented": "result"}]
    elif change == "private":
        appendix["scenarios"][package["aoi_id"]]["phone"] = "private"
    else:
        appendix["projection"] = "unrecognized"
    replace_appendix(compact_export, appendix)
    with pytest.raises(ValueError, match=match):
        verify_evidence_library(compact_export["public"])


def test_compact_report_exact_settings_are_bound_to_local_scenario_proof(
    compact_export,
):
    appendix = report_appendix(compact_export)
    appendix["scenarios"][compact_export["package"]["aoi_id"]]["synthetic"] = False
    replace_appendix(compact_export, appendix)
    with pytest.raises(ValueError, match="aggregate results differ"):
        verify_evidence_library(
            compact_export["public"], local_dir=compact_export["local"]
        )


def test_compact_report_size_budget_enforced(compact_export):
    path = compact_export["public"] / "report.html"
    path.write_bytes(path.read_bytes() + b" " * (5 * 1024 * 1024))
    with pytest.raises(ValueError, match="5 MiB budget"):
        verify_evidence_library(compact_export["public"])


def test_large_capacity_sensitivity_rows_do_not_inflate_report(compact_export):
    from floodguard.evidence_pipeline import _compact_details, scenario_summaries
    from floodguard.evidence_scenarios import build_illustrative_scenarios

    package = compact_export["package"]
    details = build_illustrative_scenarios(package["aoi_id"], [99, 20, 100, 21])
    details["capacity_participation_sensitivity"] = [
        copy.deepcopy(details["capacity_scenarios"][0])
    ]
    sensitivity = details["capacity_participation_sensitivity"][0]
    sensitivity["demand_assumptions"] = {
        "participation_fraction": 0.05,
        "actual_evacuation_demand": None,
    }
    large_rows = [
        {"population_id": "fixture-cell-" + "x" * 400, "scenario_demand": 1.23456789}
    ] * 20000
    sensitivity["population_results"] = large_rows
    details["capacity_scenarios"][0]["population_results"] = large_rows
    assert len(canonical_bytes(details)) > 5 * 1024 * 1024
    projected = _compact_details(details)
    assert projected == _compact_details(projected)
    for family in ("capacity_scenarios", "capacity_participation_sensitivity"):
        assert "population_results" not in projected[family][0]
        assert "allocations" not in projected[family][0]
        assert (
            projected[family][0]["served_population"]
            == details[family][0]["served_population"]
        )
    assert (
        projected["capacity_participation_sensitivity"][0]["demand_assumptions"]
        == sensitivity["demand_assumptions"]
    )
    assert scenario_summaries(details) == scenario_summaries(projected)
    package["scenarios"] = scenario_summaries(details)
    package["input_hashes"]["scenario_sha256"] = hashlib.sha256(
        canonical_bytes(details)
    ).hexdigest()
    write(compact_export["local"] / "scenarios" / f"{package['aoi_id']}.json", details)
    refresh(compact_export)
    report = compact_export["public"] / "report.html"
    assert report.stat().st_size < 5 * 1024 * 1024
    assert report.stat().st_size < len(canonical_bytes(details)) / 10
    assert (
        verify_evidence_library(
            compact_export["public"], local_dir=compact_export["local"]
        )["status"]
        == "passed"
    )
