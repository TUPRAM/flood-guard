"""Optical-only automated label and receipt tests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from floodguard.automated_reference import (
    ASSET_FIELDS,
    RECEIPT_SCHEMA,
    AutomatedReferenceError,
    assign_label_codes,
    compute_cross_review,
    load_asset_manifest,
    load_preregistration,
    reflectance_from_dn,
    scl_unobservable_mask,
    spectral_water_rule,
    validate_automated_reference_receipt,
    write_receipt,
)
from floodguard.observation_evaluation import canonical_sha256


def test_label_codes_cover_disagreement_cloud_and_dry_context() -> None:
    arrays = {
        "event_a": [0, 1, 1, 1, 1, 1, 1, 1],
        "event_b": [0, 0, 1, 1, 1, 1, 1, 1],
        "dry_a": [0, 0, 0, 1, 1, 0, 0, 0],
        "dry_b": [0, 0, 0, 1, 0, 0, 0, 0],
        "event_observable": [1, 1, 1, 1, 1, 1, 0, 1],
        "dry_observable": [1, 1, 1, 1, 1, 0, 1, 1],
        "inside_aoi": [1, 1, 1, 1, 1, 1, 1, 0],
    }
    values = {name: np.array(row, dtype=bool).reshape(2, 4) for name, row in arrays.items()}
    labels = assign_label_codes(**values)
    assert labels.ravel().tolist() == [0, 3, 1, 2, 3, 3, 4, 255]


def test_scl_cloud_rule_uses_20m_euclidean_buffer() -> None:
    scl = np.full((5, 5), 4, dtype=np.uint8)
    scl[2, 2] = 9
    blocked = scl_unobservable_mask(scl)
    assert blocked[2, 2] and blocked[0, 2] and blocked[2, 4]
    assert blocked[1, 1] and not blocked[0, 0] and not blocked[0, 1]


def test_reflectance_and_fixed_multi_index_rule() -> None:
    reflectance, valid = reflectance_from_dn(np.array([[0, 1000, 2000]], dtype=np.uint16))
    assert valid.tolist() == [[False, True, True]]
    assert reflectance.tolist() == [[0.0, 0.0, pytest.approx(0.1)]]
    bands = {
        "blue": np.array([[0.4, 0.1]], dtype=np.float32),
        "green": np.array([[0.6, 0.1]], dtype=np.float32),
        "red": np.array([[0.2, 0.2]], dtype=np.float32),
        "nir": np.array([[0.05, 0.4]], dtype=np.float32),
        "swir16": np.array([[0.1, 0.3]], dtype=np.float32),
        "swir22": np.array([[0.1, 0.3]], dtype=np.float32),
    }
    water, usable = spectral_water_rule(bands)
    assert usable.tolist() == [[True, True]]
    assert water.tolist() == [[True, False]]


def test_cross_review_uses_agreement_metric_and_fixed_limits() -> None:
    method_a = np.array([[1, 0, 1, 0]], dtype=bool)
    method_b = np.array([[1, 0, 1, 0]], dtype=bool)
    report = compute_cross_review(method_a, method_b, np.ones((1, 4), dtype=bool),
                                  min_water_dice=0.6, min_cohen_kappa=0.5)
    assert report["water_dice"] == 1.0
    assert report["cohen_kappa"] == 1.0
    assert report["passes_limits"] is True
    assert report["human_reviewed"] is False


def test_rehashed_plan_that_differs_from_git_commit_is_rejected(tmp_path: Path) -> None:
    plan = load_preregistration()
    plan["methods"]["B"]["mndwi_gt"] = 0.11
    plan["preregistration_sha256"] = canonical_sha256({
        key: value for key, value in plan.items() if key != "preregistration_sha256"
    })
    changed = tmp_path / "preregistration_v1.json"
    changed.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(AutomatedReferenceError, match="Git commit mismatch"):
        load_preregistration(changed)


def _manifest(tmp_path: Path) -> Path:
    prereg = load_preregistration()
    path = tmp_path / "assets.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ASSET_FIELDS)
        writer.writeheader()
        for role in ("event", "dry"):
            item_key = "event_item_id" if role == "event" else "dry_context_item_id"
            product_key = "event_product_uri" if role == "event" else "dry_context_product_uri"
            for asset in prereg["source"]["assets"]:
                writer.writerow({
                    "scene_role": role,
                    "item_id": prereg["source"][item_key],
                    "product_uri": prereg["source"][product_key],
                    "asset": asset,
                    "asset_url": f"https://example.test/{role}/{asset}.tif",
                    "file_size_bytes": 1,
                    "sha256": "a" * 64,
                    "source_edition": "element84_cog_of_l2a",
                    "original_safe_sha256": "not_recorded",
                })
    return path


def test_reference_receipt_checks_prereg_manifest_and_raster(tmp_path: Path) -> None:
    prereg = load_preregistration()
    manifest = _manifest(tmp_path)
    raster = tmp_path / "labels.tif"
    raster.write_bytes(b"label-bytes")
    payload = {
        "schema": RECEIPT_SCHEMA,
        "evidence_tier": "automated_optical_reference",
        "preregistration_sha256": prereg["preregistration_sha256"],
        "preregistration_commit": "77833df9d595429c1cf903c9a841e86aa8668b79",
        "input_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "input_assets": load_asset_manifest(manifest),
        "label_raster_sha256": hashlib.sha256(raster.read_bytes()).hexdigest(),
        "class_counts": {"0": 1, "1": 1, "2": 0, "3": 0, "4": 0},
        "aoi_cell_count": 2,
        "ab_agreement": {
            "evidence_tier": "automated_cross_review", "human_reviewed": False,
            "water_dice": 0.8, "cohen_kappa": 0.7, "passes_limits": True,
        },
        "human_reviewed": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    receipt_path = tmp_path / "receipt.json"
    receipt = write_receipt(payload, receipt_path)
    assert validate_automated_reference_receipt(receipt_path, manifest=manifest, raster_path=raster) == receipt

    receipt["preregistration_sha256"] = "0" * 64
    write_receipt(receipt, receipt_path)
    with pytest.raises(AutomatedReferenceError, match="pre-registration hash mismatch"):
        validate_automated_reference_receipt(receipt_path, manifest=manifest, raster_path=raster)

    receipt["preregistration_sha256"] = prereg["preregistration_sha256"]
    receipt["ab_agreement"]["passes_limits"] = False
    write_receipt(receipt, receipt_path)
    with pytest.raises(AutomatedReferenceError, match="pass flag contradicts"):
        validate_automated_reference_receipt(receipt_path, manifest=manifest, raster_path=raster)

    receipt["ab_agreement"]["passes_limits"] = True
    write_receipt(receipt, receipt_path)
    raster.write_bytes(b"tampered")
    with pytest.raises(AutomatedReferenceError, match="raster SHA-256 mismatch"):
        validate_automated_reference_receipt(receipt_path, manifest=manifest, raster_path=raster)
