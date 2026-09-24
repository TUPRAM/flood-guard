"""Focused guards for the separately frozen automated optical v2 study."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pytest

import floodguard.automated_optical_v2 as v2
from floodguard.automated_optical_v2 import (
    ASSETS,
    AutomatedOpticalV2Error,
    assess_positive_feasibility,
    consume_holdout_marker,
    effective_model_tiling,
    expanded_scl_unobservable,
    load_asset_manifest,
    load_feasibility_gate,
    load_plan,
    model_input,
    spectral_validity_only,
    validate_result_artifacts,
    verify_receipt,
    write_self_hashed,
)
from floodguard.automated_reference import spectral_water_rule


def test_v2_plan_is_committed_and_tampering_refuses(tmp_path: Path) -> None:
    plan = load_plan()
    assert plan["cross_review_limits"]["min_water_dice"] == 0.6
    assert plan["final_holdout"]["event_item_id"] == "S2B_47PRT_20210928_1_L2A"
    plan["methods"]["A"]["overlap_size_pixels"] = 0
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(AutomatedOpticalV2Error, match="self-hash or frozen commit"):
        load_plan(changed)


def test_expanded_scl_mask_includes_new_classes_and_20m_buffer() -> None:
    scl = np.full((9, 9), 4, dtype=np.uint8)
    scl[4, 4] = 2
    scl[0, 0] = 1
    mask = expanded_scl_unobservable(scl)
    assert mask[4, 4] and mask[4, 6] and mask[6, 4]
    assert not mask[6, 6]
    assert mask[0, 0] and mask[0, 2]
    assert not mask[8, 8]


def test_native_model_input_keeps_full_grid_and_masked_pixels() -> None:
    bands = {name: np.full((9, 11), 0.2, dtype=np.float32) for name in ASSETS[:-1]}
    observable = np.ones((9, 11), dtype=bool)
    observable[4, 3] = False
    stack = model_input(bands, observable)
    assert stack.shape == (6, 9, 11)
    assert np.all(stack[:, 4, 3] == -9999)
    assert np.all(stack[:, 4, 4] == 0.2)


def test_preparation_validity_matches_rule_without_classifying_water() -> None:
    bands = {name: np.full((3, 4), 0.2, dtype=np.float32) for name in ASSETS[:-1]}
    bands["green"][0, 0] = 0
    bands["swir16"][0, 0] = 0
    bands["nir"][2, 3] = 0
    bands["red"][2, 3] = 0
    assert np.array_equal(spectral_validity_only(bands), spectral_water_rule(bands)[1])


def test_recorded_tiling_follows_pinned_nodata_rule() -> None:
    stack = np.ones((6, 957, 1109), dtype=np.float32)
    stack[:, :400] = -9999
    tiling = effective_model_tiling(stack)
    assert tiling["requested_patch_size_pixels"] == 512
    assert tiling["effective_patch_size_pixels"] == 478
    assert tiling["effective_overlap_size_pixels"] == 128


def test_manifest_retains_per_asset_radiometry_and_rejects_missing_offset(tmp_path: Path) -> None:
    plan = load_plan()
    episode = plan["final_holdout"]
    rows = []
    for scene_role, item_id, product in (
        ("event", episode["event_item_id"], episode["event_product_uri"]),
        ("dry", episode["dry_item_id"], episode["dry_product_uri"]),
    ):
        for asset in ASSETS:
            rows.append({
                "scene_role": scene_role, "item_id": item_id, "product_uri": product,
                "asset": asset, "asset_url": f"https://example.test/{item_id}/{asset}.tif",
                "file_size_bytes": "100", "sha256": "a" * 64,
                "scale": "" if asset == "scl" else "0.0001",
                "offset": "" if asset == "scl" else "-0.1",
                "source_edition": plan["source_edition"],
                "processing_baseline": "05.00",
                "sensing_utc": episode[f"{scene_role}_sensing_utc"],
                "preregistration_sha256": plan["preregistration_sha256"],
                "original_safe_sha256": "not_recorded",
            })
    path = tmp_path / "assets.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    parsed = load_asset_manifest(path, plan, "final_holdout")
    assert len(parsed) == 16
    assert parsed[0]["offset"] == -0.1
    rows[0]["offset"] = ""
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AutomatedOpticalV2Error, match="incomplete"):
        load_asset_manifest(path, plan, "final_holdout")


def test_manifest_rejects_wrong_sensing_time_even_with_correct_item(tmp_path: Path) -> None:
    plan = load_plan()
    episode = plan["final_holdout"]
    rows = []
    for scene_role in ("event", "dry"):
        for asset in ASSETS:
            rows.append({
                "scene_role": scene_role, "item_id": episode[f"{scene_role}_item_id"],
                "product_uri": episode[f"{scene_role}_product_uri"],
                "asset": asset, "asset_url": f"https://example.test/{asset}.tif",
                "file_size_bytes": "100", "sha256": "a" * 64,
                "scale": "" if asset == "scl" else "0.0001",
                "offset": "" if asset == "scl" else "-0.1",
                "source_edition": plan["source_edition"],
                "processing_baseline": "05.00",
                "sensing_utc": "2021-09-28T00:00:00Z" if scene_role == "event" else episode["dry_sensing_utc"],
                "preregistration_sha256": plan["preregistration_sha256"],
                "original_safe_sha256": "not_recorded",
            })
    path = tmp_path / "assets.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(AutomatedOpticalV2Error, match="sensing time differs"):
        load_asset_manifest(path, plan, "final_holdout")


def test_second_v2_holdout_consumption_refuses(tmp_path: Path) -> None:
    marker = tmp_path / "marker.json"
    plan = load_plan()
    gate = load_feasibility_gate(plan)
    first = consume_holdout_marker(
        marker, plan=plan, gate=gate, development_hash="a" * 64, preparation_hash="b" * 64,
    )
    assert first["preregistration_sha256"] == plan["preregistration_sha256"]
    with pytest.raises(AutomatedOpticalV2Error, match="already consumed"):
        consume_holdout_marker(
            marker, plan=plan, gate=gate, development_hash="a" * 64, preparation_hash="b" * 64,
        )


def test_positive_feasibility_requires_substantial_shared_water() -> None:
    gate = load_feasibility_gate(load_plan())
    both = np.ones((11, 11), dtype=bool)
    assert assess_positive_feasibility(both, both, both, gate)["passes"] is True
    a = both.copy()
    b = both.copy()
    a[0] = False
    b[-1] = False
    result = assess_positive_feasibility(a, b, both, gate)
    assert result["water_count_a"] == result["water_count_b"] == 110
    assert result["shared_water_count"] == 99
    assert result["passes"] is False


def test_feasibility_gate_tampering_refuses(tmp_path: Path) -> None:
    plan = load_plan()
    gate = load_feasibility_gate(plan)
    gate["minimum_shared_water_cells"] = 1
    changed = tmp_path / "gate.json"
    changed.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(AutomatedOpticalV2Error, match="frozen plan or commit"):
        load_feasibility_gate(plan, changed)


def test_v2_receipt_tampering_refuses(tmp_path: Path) -> None:
    plan = load_plan()
    path = tmp_path / "receipt.json"
    payload = {
        "schema": "floodguard.automated_optical_v2_preparation.v1",
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": "efc69f5f66dfe8c2d667a9827566126709f1cab9",
        "human_reviewed": False, "accepted_observation": False,
        "official_warning": False, "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    write_self_hashed(payload, path)
    assert verify_receipt(path, payload["schema"], plan)["human_reviewed"] is False
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["official_warning"] = True
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(AutomatedOpticalV2Error, match="does not verify"):
        verify_receipt(path, payload["schema"], plan)


def test_rehashed_false_pass_result_refuses(tmp_path: Path) -> None:
    plan = load_plan()
    development_path = Path(__file__).resolve().parents[1] / "outputs/automated_optical_v2_development.json"
    result = json.loads(development_path.read_text(encoding="utf-8"))
    result["passes_all_limits"] = True
    forged = tmp_path / "forged_result.json"
    write_self_hashed(result, forged)
    with pytest.raises(AutomatedOpticalV2Error, match="pass flag contradicts"):
        verify_receipt(forged, result["schema"], plan)


def test_result_artifact_validation_refuses_changed_method_raster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    result_path = root / "outputs/automated_optical_v2_development.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    expected_hashes = {
        "automated_optical_reference_v2.tif": result["label_raster_sha256"],
    }
    for scene in ("event", "dry"):
        for kind in ("input", "output"):
            expected_hashes[f"{scene}_native_model_{kind}.tif"] = result["model_raster_sha256"][scene][f"{kind}_sha256"]
        for method in ("a", "b"):
            expected_hashes[f"{scene}_method_{method}_water.tif"] = result["method_raster_sha256"][f"{scene}_{method}"]
    real_file_sha256 = v2.file_sha256

    def simulated_file_sha256(path: Path) -> str:
        if path.name == "event_method_a_water.tif":
            return "0" * 64
        return expected_hashes[path.name] if path.name in expected_hashes else real_file_sha256(path)

    monkeypatch.setattr(v2, "file_sha256", simulated_file_sha256)
    monkeypatch.setattr(v2, "load_asset_manifest", lambda *_args: result["input_assets"])
    monkeypatch.setattr(v2, "verify_asset_files", lambda *_args: None)
    with pytest.raises(AutomatedOpticalV2Error, match="method raster hash mismatch"):
        validate_result_artifacts(
            result_path=result_path,
            preparation_path=root / "outputs/automated_optical_v2_development_preparation.json",
            manifest_path=root / "outputs/earth_search_automated_optical_v2_development_assets.csv",
            external_root=tmp_path,
            output_dir=tmp_path,
            quicklook_path=root / "outputs/automated_optical_v2_development.png",
        )
