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
    (public / "report.html").write_text(
        "<html><pre>" + html.escape(json.dumps(appendix)) + "</pre></html>",
        encoding="utf-8",
    )
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
