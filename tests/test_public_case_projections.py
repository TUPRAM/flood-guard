"""Build-time public projection boundaries for the competition profile."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "apps/web/public"
SOURCE_CATALOG = PUBLIC_DIR / "evidence-library/catalog.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_public_case_projections.py"
SPEC = importlib.util.spec_from_file_location("build_public_case_projections", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_case_projection = MODULE._case_projection
_source_package = MODULE._source_package
build = MODULE.build


def _source():
    catalog = json.loads(SOURCE_CATALOG.read_bytes())
    package, digest = _source_package(PUBLIC_DIR, catalog["packages"][0], catalog["package_version"])
    return catalog, package, digest


def test_real_public_projection_is_byte_bound_and_contains_only_candidate_decisions(tmp_path):
    source_digest = hashlib.sha256(SOURCE_CATALOG.read_bytes()).hexdigest()
    receipt = build(PUBLIC_DIR, tmp_path / "public-cases", source_digest)
    catalog = json.loads((tmp_path / "public-cases/catalog.json").read_bytes())
    assert receipt["cases"] == 8
    assert len(catalog["packages"]) == 8
    for reference in catalog["packages"]:
        case_bytes = (tmp_path / "public-cases/cases" / f"{reference['id']}.json").read_bytes()
        assert hashlib.sha256(case_bytes).hexdigest() == reference["sha256"]
        case = json.loads(case_bytes)
        assert case["source_package_sha256"] == reference["source_package_sha256"]
        assert (case["aoi_id"], case["event_id"]) == (reference["aoi_id"], reference["event_id"])
        assert case["fpps"] is case["action_class"] is case["affected_population"] is None
        assert case["official_warning"] is False
        assert case["dataset_mode"] == "candidate"
        source = json.loads((PUBLIC_DIR / "evidence-library/packages" / f"{reference['id']}.json").read_bytes())
        assert case["source_analysis_generated_at"] == source["decision_brief"].get("finals_analysis", {}).get("generated_at")
        assert case["access"] is None  # Generic legacy vehicle context has a different basis.
        main_road = next(service for service in case["services"] if service["id"] == "main_road")
        assert main_road["status"] == "unavailable"
        assert main_road["facilities"] is None
        assert main_road["variants"] == []
        source_services = (source["decision_brief"].get("finals_analysis") or {}).get("services", [])
        if any(service.get("variants") for service in source_services):
            assert any(service["variants"] for service in case["services"] if service["id"] != "main_road")
        assert "evidence_notes" not in case and "layers" not in case and "source_urls" not in case


def test_source_mismatch_and_unsafe_paths_fail_closed(tmp_path):
    catalog, package, _ = _source()
    with pytest.raises(ValueError, match="checksum"):
        build(PUBLIC_DIR, tmp_path, "0" * 64)
    bad_ref = dict(catalog["packages"][0], url="/evidence-library/../private.json")
    with pytest.raises(ValueError, match="Unsafe"):
        _source_package(PUBLIC_DIR, bad_ref, catalog["package_version"])
    accepted_looking = copy.deepcopy(package)
    accepted_looking["assessment"]["fpps"] = 42
    with pytest.raises(ValueError, match="accepted-looking"):
        # The complete builder also verifies source bytes; this probes its projection gate.
        _case_projection(accepted_looking, catalog["packages"][0]["sha256"], catalog)


def test_unresolved_derivative_rights_block_export():
    catalog, package, digest = _source()
    denied = copy.deepcopy(catalog)
    next(row for row in denied["datasets"] if row["id"] == "context-worldpop")["rights"]["public_derivatives"] = False
    with pytest.raises(ValueError, match="permission unresolved"):
        _case_projection(package, digest, denied)
