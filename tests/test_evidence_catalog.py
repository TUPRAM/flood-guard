import csv
import json

import pytest

from floodguard.evidence_catalog import (
    assert_public_safe,
    build_registry,
    canonical_bytes,
    dataset_applies,
    safe_asset_path,
    sha256_file,
    validate_layer_export,
    verify_bundle,
)
from floodguard.evidence_pipeline import _assessment, scenario_summaries
from floodguard.evidence_scenarios import build_illustrative_scenarios


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "data.csv").write_text("code,value\n001,4\n", encoding="utf-8")
    write_csv(
        tmp_path / "FILES_SHA256.csv",
        [
            {
                "path": "data.csv",
                "bytes": (tmp_path / "data.csv").stat().st_size,
                "sha256": sha256_file(tmp_path / "data.csv"),
            }
        ],
    )
    return tmp_path


def test_integrity_rejects_mutation_and_missing(bundle):
    assert len(verify_bundle(bundle)) == 1
    (bundle / "data.csv").write_text("code,value\n001,9\n", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        verify_bundle(bundle)
    (bundle / "data.csv").unlink()
    with pytest.raises(ValueError, match="integrity"):
        verify_bundle(bundle)


@pytest.mark.parametrize(
    "value", ["../secret", "a/../../secret", "C:/secret", "/secret", "\\\\server\\file"]
)
def test_unsafe_paths(tmp_path, value):
    with pytest.raises(ValueError):
        safe_asset_path(tmp_path, value)


def test_selections_share_physical_asset_and_keep_temporal_conflicts(bundle):
    locations = bundle / "locations.csv"
    inventory = bundle / "inventory.csv"
    write_csv(
        locations,
        [
            {"dataset_row": n, "absolute_file_path": r"D:\external\data.csv"}
            for n in range(1, 18)
        ],
    )
    write_csv(
        inventory,
        [
            {
                "#": n,
                "Upload / data acquired": f"Dataset {n}",
                "Record selection": f"Selection {n}",
                "Purpose": "Context",
                "Dataset type": "CSV",
            }
            for n in range(1, 18)
        ],
    )
    # commonpath of one identical file resolves to that file; the real manifest
    # contains multiple paths. Add another verified source for this test.
    second = bundle / "second.csv"
    second.write_text("value\n1\n", encoding="utf-8")
    rows = list(csv.DictReader((bundle / "FILES_SHA256.csv").open()))
    rows.append(
        {
            "path": "second.csv",
            "bytes": second.stat().st_size,
            "sha256": sha256_file(second),
        }
    )
    write_csv(bundle / "FILES_SHA256.csv", rows)
    write_csv(
        locations,
        [
            {
                "dataset_row": n,
                "absolute_file_path": r"D:\external\data.csv"
                if n != 17
                else r"D:\external\second.csv",
            }
            for n in range(1, 18)
        ],
    )
    registry = build_registry(bundle, locations, inventory, [], "2026-09-21T00:00:00Z")
    assert len(registry["datasets"]) == 17 and len(registry["assets"]) == 2
    six, seven = registry["datasets"][5:7]
    assert (
        six["asset_ids"] == seven["asset_ids"]
        and six["selection"] != seven["selection"]
    )
    flood = registry["datasets"][0]["temporal"]
    assert {a["value"] for a in flood["assertions"]} == {"2024-10-12", "2024-10-22"}
    assert registry["datasets"][11]["temporal"]["activation_date"] is None
    assert registry["datasets"][13]["temporal"]["start"] is None
    assert 2024 not in six["temporal"]["reference_years"]
    assert json.loads(canonical_bytes(registry)) == registry


@pytest.mark.parametrize(
    "payload",
    [
        {"path": r"C:\Users\private\x"},
        {"phone": "123"},
        {"records": [{"coordinator_name": "Private"}]},
        {"value": float("nan")},
    ],
)
def test_public_export_rejects_personal_data(payload):
    with pytest.raises(ValueError):
        assert_public_safe(payload)


def test_export_requires_explicit_source_permission():
    layer = {
        "id": "x",
        "role": "historical_context",
        "dataset_id": "unclear",
        "data": {"type": "FeatureCollection", "features": []},
    }
    with pytest.raises(ValueError):
        validate_layer_export(
            layer, {"unclear": {"rights": {"public_derivatives": False}}}
        )
    # Calling a source-derived geometry scenario does not bypass permission.
    with pytest.raises(ValueError):
        validate_layer_export({**layer, "role": "scenario"}, {})
    validate_layer_export({**layer, "data": None}, {})


def test_unavailable_pairs_and_partial_assessment():
    assert not dataset_applies(3, "aoi-05_lower", "chao_phraya_2025")
    assert not dataset_applies(1, "aoi-03_hat_yai_core", "hat_yai_2025")
    assessment = _assessment("aoi-test")
    assert assessment["fpps"] is None and assessment["action_class"] is None
    assert assessment["bounds"] == {"lower": 0, "upper": 100}
    assert sum(row["weight"] for row in assessment["components"]) == 1


def test_scenarios_are_explicit_and_stable():
    details = build_illustrative_scenarios("aoi-test", [99, 20, 100, 21])
    first = scenario_summaries(details)
    assert canonical_bytes(first) == canonical_bytes(scenario_summaries(details))
    assert len([row for row in first if row["kind"] == "synthetic_access"]) == 4
    assert all(
        row["metrics"][1]["value"] == "E"
        for row in first
        if row["kind"] == "score_sensitivity"
    )
