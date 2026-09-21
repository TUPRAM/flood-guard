"""Builder identity and cache behavior use small, deterministic source fixtures."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from floodguard import evidence_context as context
from floodguard import evidence_pipeline as pipeline
from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_scenarios import (
    build_illustrative_scenarios,
    evidence_assessment,
)


def test_runtime_identity_is_stable_and_changes_with_lock_and_native_versions(
    tmp_path, monkeypatch
):
    lock = tmp_path / "uv.lock"
    lock.write_text("locked dependencies", encoding="utf-8")
    first = pipeline.build_runtime_identity(context_enabled=False, lock_path=lock)
    assert first == pipeline.build_runtime_identity(
        context_enabled=False, lock_path=lock
    )
    assert str(tmp_path) not in json.dumps(first)
    lock.write_text("different locked dependencies", encoding="utf-8")
    changed_lock = pipeline.build_runtime_identity(
        context_enabled=False, lock_path=lock
    )
    assert first["uv_lock_sha256"] != changed_lock["uv_lock_sha256"]
    assert first["sha256"] != changed_lock["sha256"]
    import pyproj

    monkeypatch.setattr(pyproj, "proj_version_str", "different-native-proj")
    assert (
        pipeline.build_runtime_identity(context_enabled=False, lock_path=lock)["sha256"]
        != changed_lock["sha256"]
    )


def test_installed_versions_and_external_ogr_are_independent_runtime_inputs(
    tmp_path, monkeypatch
):
    lock = tmp_path / "uv.lock"
    lock.write_text("same lock", encoding="utf-8")
    monkeypatch.setattr(
        context,
        "ogr_runtime_identity",
        lambda: {"gdal_version": "3.13.0", "executable_sha256": "b" * 64},
    )
    first = pipeline.build_runtime_identity(context_enabled=True, lock_path=lock)
    original_version = pipeline.metadata.version
    monkeypatch.setattr(
        pipeline.metadata,
        "version",
        lambda name: "changed" if name == "pyproj" else original_version(name),
    )
    installed_change = pipeline.build_runtime_identity(
        context_enabled=True, lock_path=lock
    )
    assert first["sha256"] != installed_change["sha256"]
    monkeypatch.setattr(
        context,
        "ogr_runtime_identity",
        lambda: {"gdal_version": "3.14.0", "executable_sha256": "c" * 64},
    )
    external_change = pipeline.build_runtime_identity(
        context_enabled=True, lock_path=lock
    )
    assert external_change["sha256"] != installed_change["sha256"]
    assert (
        external_change["native"]["rasterio_gdal"] == first["native"]["rasterio_gdal"]
    )


def test_scenario_cache_requires_same_runtime_and_intact_bytes(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        context,
        "build_context_scenarios",
        lambda *args, **kwargs: calls.append(1) or {"result": len(calls)},
    )
    inputs = {"canonical_sha256": "a" * 64}
    path = tmp_path / "scenarios.json"
    runtime = {"sha256": "b" * 64}
    first = pipeline._context_scenarios(inputs, "aoi-01", "osm", path, False, runtime)
    assert (
        pipeline._context_scenarios(inputs, "aoi-01", "osm", path, True, runtime)
        == first
    )
    assert len(calls) == 1
    changed_runtime = {"sha256": "c" * 64}
    pipeline._context_scenarios(inputs, "aoi-01", "osm", path, True, changed_runtime)
    assert len(calls) == 2
    path.write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(ValueError, match="checksum changed"):
        pipeline._context_scenarios(
            inputs, "aoi-01", "osm", path, True, changed_runtime
        )
    receipt_path = path.with_suffix(".receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    del receipt["binding"]["build_runtime_sha256"]
    receipt_path.write_bytes(canonical_bytes(receipt))
    pipeline._context_scenarios(inputs, "aoi-01", "osm", path, True, changed_runtime)
    assert len(calls) == 3


@pytest.mark.parametrize("changed_field", ["gdal_version", "executable_sha256"])
def test_osm_extraction_cache_is_invalidated_by_native_tool_change(
    tmp_path, monkeypatch, changed_field
):
    identity = {"gdal_version": "3.13.0", "executable_sha256": "a" * 64}
    calls = []
    monkeypatch.setattr(context, "find_qgis_bin", lambda: tmp_path)
    monkeypatch.setattr(context, "ogr_runtime_identity", lambda _: dict(identity))

    def extract(_bin_dir, args):
        calls.append(args)
        destination = next(Path(arg) for arg in args if arg.endswith(".geojson"))
        destination.write_bytes(
            canonical_bytes({"type": "FeatureCollection", "features": []})
        )

    monkeypatch.setattr(context, "_run_ogr2ogr", extract)
    args = (
        tmp_path / "source.osm.pbf",
        [99, 14, 100, 15],
        tmp_path,
        "b" * 64,
        "c" * 64,
    )
    first = context._extract_osm(*args)
    assert context._extract_osm(*args) == first and len(calls) == 2
    identity[changed_field] = "3.14.0" if changed_field == "gdal_version" else "d" * 64
    assert context._extract_osm(*args) == first and len(calls) == 4


def test_external_ogr_identity_does_not_expose_installation_path(tmp_path, monkeypatch):
    executable = tmp_path / ("ogr2ogr.exe" if context.os.name == "nt" else "ogr2ogr")
    executable.write_bytes(b"test executable")
    monkeypatch.setattr(
        context.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="GDAL 3.13.0, released 2026/05/08"
        ),
    )
    identity = context.ogr_runtime_identity(tmp_path)
    assert identity == {
        "gdal_version": "3.13.0",
        "executable_sha256": context._sha256(executable),
    }
    assert str(tmp_path) not in json.dumps(identity)


def test_scenario_summaries_are_identical_after_canonical_cache_reload():
    details = build_illustrative_scenarios("aoi-01", [99, 14, 100, 15])
    # Modelled summaries have additional access-derived score families and may
    # receive a keyed capacity collection; canonical JSON sorts these mappings.
    details["synthetic"] = False
    details["capacity_scenarios"] = {
        f"preset-{9 - index}": value
        for index, value in enumerate(details["capacity_scenarios"])
    }
    details["scenario_assessments"] = {
        key: evidence_assessment({"access_gap_0_100": gap}, area_id="aoi-01")
        for key, gap in (("z_scenario", 60), ("a_scenario", 10))
    }
    first = pipeline.scenario_summaries(details)
    reloaded = json.loads(canonical_bytes(details))
    assert canonical_bytes(first) == canonical_bytes(
        pipeline.scenario_summaries(reloaded)
    )


@pytest.mark.parametrize("change", ["runtime", "lock"])
def test_library_normalization_and_version_reject_changed_builder_identity(
    tmp_path, monkeypatch, change
):
    from floodguard import (
        evidence_adapters,
        evidence_local_report,
        evidence_population_review,
        evidence_review,
    )

    lock = tmp_path / "uv.lock"
    lock.write_text("first lock", encoding="utf-8")
    runtime = pipeline.build_runtime_identity(context_enabled=False, lock_path=lock)
    original_identity = pipeline.build_runtime_identity
    monkeypatch.setattr(
        pipeline, "build_runtime_identity", lambda **kwargs: copy.deepcopy(runtime)
    )
    monkeypatch.setattr(pipeline, "load_aois", lambda _: [])
    monkeypatch.setattr(
        pipeline,
        "build_registry",
        lambda *args: {
            "source_inventory_sha256": "a" * 64,
            "datasets": [],
            "assets": [],
            "events": [],
            "generated_at": args[-1],
            "verified_asset_count": 0,
        },
    )
    calls = []

    def normalize(_root, output, _aois):
        calls.append(1)
        summary = {"outputs": {}, "aois": {}}
        pipeline.write_json(output / "adapter_summary.json", summary)
        return summary

    monkeypatch.setattr(evidence_adapters, "normalize_bundle", normalize)
    monkeypatch.setattr(
        evidence_review, "enrich_registry", lambda registry, *_: registry
    )
    monkeypatch.setattr(
        evidence_review, "build_facility_crosswalk", lambda *_: {"rows": []}
    )
    monkeypatch.setattr(evidence_local_report, "render_local_report", lambda *_: None)
    monkeypatch.setattr(
        evidence_population_review,
        "build_population_review",
        lambda *args, **kwargs: {"fixture": "no population rows in this cache test"},
    )
    monkeypatch.setattr(
        pipeline, "render_report", lambda *_: "<html>deterministic fixture</html>"
    )
    kwargs = {
        "bundle_root": tmp_path,
        "locations_csv": tmp_path / "locations.csv",
        "inventory_csv": tmp_path / "inventory.csv",
        "aoi_dir": tmp_path,
        "output_dir": tmp_path / "local",
        "public_dir": tmp_path / "public",
        "generated_at": "2026-09-21T00:00:00Z",
    }
    first = pipeline.build_library(**kwargs)
    assert pipeline.build_library(**kwargs, reuse_normalized=True) == first
    assert len(calls) == 1
    if change == "lock":
        lock.write_text("changed lock", encoding="utf-8")
        runtime = original_identity(context_enabled=False, lock_path=lock)
    else:
        import pyproj

        monkeypatch.setattr(pyproj, "proj_version_str", "changed-native-runtime")
        runtime = original_identity(context_enabled=False, lock_path=lock)
    changed = pipeline.build_library(**kwargs, reuse_normalized=True)
    assert len(calls) == 2
    assert changed["package_version"] != first["package_version"]
    receipt = json.loads(
        (kwargs["output_dir"] / "normalization_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["build_runtime"] == runtime
    assert changed["build_runtime"] == runtime
