"""Mae Sai development diagnostics for the separately preregistered optical v2.

This module never opens the v2 final holdout or changes an evidence receipt.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.automated_optical_diagnostics import (
    PAIR_NAMES,
    _quantiles,
    _raw_dn_summary,
    _read_frozen_method,
    _write_chips,
    _write_quicklook,
    pair_codes,
    summarize_pairs,
)
from floodguard.automated_optical_v2 import (
    file_sha256,
    load_asset_manifest,
    load_plan,
    read_scene,
    reference_grid,
    scene_root,
    verify_asset_files,
    verify_receipt,
)
from floodguard.automated_reference import compute_cross_review, spectral_water_rule


def summarize_dry_change(
    event_pairs: np.ndarray, dry_pairs: np.ndarray,
    event_green: np.ndarray, event_swir16: np.ndarray,
    dry_green: np.ndarray, dry_swir16: np.ndarray,
) -> dict[str, Any]:
    """Summarize 5-to-15 September optical change by observable event pair."""
    if not all(value.shape == event_pairs.shape for value in (
        dry_pairs, event_green, event_swir16, dry_green, dry_swir16,
    )):
        raise ValueError("Event and dry grids must share one shape.")
    if not np.isin(event_pairs, (0, 1, 2, 3, 255)).all() or not np.isin(dry_pairs, (0, 1, 2, 3, 255)).all():
        raise ValueError("Event or dry pair grid contains an unexpected code.")
    event_mndwi = (event_green - event_swir16) / np.maximum(event_green + event_swir16, 1e-6)
    dry_mndwi = (dry_green - dry_swir16) / np.maximum(dry_green + dry_swir16, 1e-6)
    summary: dict[str, Any] = {}
    for code, name in enumerate(PAIR_NAMES):
        event = event_pairs == code
        comparable = event & (dry_pairs != 255)
        summary[name] = {
            "event_cells": int(event.sum()),
            "dry_observable_cells": int(comparable.sum()),
            "dry_pair_counts": {
                dry_name: int(np.count_nonzero(comparable & (dry_pairs == dry_code)))
                for dry_code, dry_name in enumerate(PAIR_NAMES)
            },
            "delta_mndwi_event_minus_dry": _quantiles((event_mndwi - dry_mndwi)[comparable]),
            "delta_swir16_event_minus_dry": _quantiles((event_swir16 - dry_swir16)[comparable]),
        }
    return summary


def build_v2_development_diagnostics(
    *, repo_root: Path, external_data_root: Path, result_path: Path,
    quicklook_path: Path, chips_path: Path,
) -> dict[str, Any]:
    """Verify and diagnose Mae Sai v2 development rasters without opening holdout data."""
    plan = load_plan()
    manifest_path = repo_root / "outputs" / "earth_search_automated_optical_v2_development_assets.csv"
    preparation_path = repo_root / "outputs" / "automated_optical_v2_development_preparation.json"
    receipt_path = repo_root / "outputs" / "automated_optical_v2_development.json"
    preparation = verify_receipt(preparation_path, "floodguard.automated_optical_v2_preparation.v1", plan)
    receipt = verify_receipt(receipt_path, "floodguard.automated_optical_v2_result.v1", plan)
    if receipt.get("role") != "development" or preparation.get("role") != "development":
        raise ValueError("This diagnostic only accepts Mae Sai development receipts.")
    if receipt.get("preparation_receipt_sha256") != preparation["receipt_sha256"]:
        raise ValueError("V2 development preparation hash differs from its result.")
    rows = load_asset_manifest(manifest_path, plan, "development")
    if file_sha256(manifest_path) != receipt["input_manifest_sha256"] or rows != receipt["input_assets"]:
        raise ValueError("Development asset manifest differs from the v2 result receipt.")
    root = scene_root(external_data_root, "development")
    verify_asset_files(rows, root)
    output_dir = external_data_root / "proposal_execution" / "automated_track" / "v2" / "development"
    transform, shape, inside_aoi = reference_grid(
        plan, "development", root / plan["development"]["event_item_id"] / "blue.tif",
    )
    if list(transform)[:6] != receipt["grid"]["transform"] or [shape[1], shape[0]] != [receipt["grid"]["width"], receipt["grid"]["height"]]:
        raise ValueError("Development grid differs from the v2 result receipt.")
    if file_sha256(output_dir / "automated_optical_reference_v2.tif") != receipt["label_raster_sha256"]:
        raise ValueError("Development label raster differs from the v2 result receipt.")
    scenes: dict[str, tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]] = {}
    for scene_role in ("event", "dry"):
        bands, observable, scl = read_scene(rows, root, scene_role, transform, shape, inside_aoi)
        if int(observable.sum()) != receipt["quality"][scene_role]["observable_aoi_cells"]:
            raise ValueError("V2 development observability differs from its result.")
        a = _read_frozen_method(
            output_dir / f"{scene_role}_method_a_water.tif",
            receipt["method_raster_sha256"][f"{scene_role}_a"], shape, transform,
        )
        b = _read_frozen_method(
            output_dir / f"{scene_role}_method_b_water.tif",
            receipt["method_raster_sha256"][f"{scene_role}_b"], shape, transform,
        )
        spectral_water, spectral_valid = spectral_water_rule(bands)
        if (not np.array_equal(a != 255, observable) or not np.array_equal(b != 255, observable)
                or not np.array_equal(b[observable] == 1, spectral_water[observable])
                or np.any(observable & ~spectral_valid)):
            raise ValueError("Development method raster disagrees with source-derived v2 observability or spectral rule.")
        scenes[scene_role] = bands, pair_codes(a == 1, b == 1, observable), observable, scl
    event_bands, event_pairs, event_observable, event_scl = scenes["event"]
    dry_bands, dry_pairs, _, _ = scenes["dry"]
    a = (event_pairs == 1) | (event_pairs == 3)
    b = (event_pairs == 2) | (event_pairs == 3)
    review = compute_cross_review(
        a, b, event_observable,
        min_water_dice=plan["cross_review_limits"]["min_water_dice"],
        min_cohen_kappa=plan["cross_review_limits"]["min_cohen_kappa"],
    )
    if review != receipt["ab_agreement"]:
        raise ValueError("Development agreement differs from the v2 result receipt.")
    summary = summarize_pairs(event_pairs, event_scl, event_bands)
    summary["raw_dn_by_pair"] = _raw_dn_summary(
        root / plan["development"]["event_item_id"], transform, shape, event_pairs,
    )
    summary["dry_change_by_event_pair"] = summarize_dry_change(
        event_pairs, dry_pairs,
        event_bands["green"], event_bands["swir16"],
        dry_bands["green"], dry_bands["swir16"],
    )
    result = {
        "schema": "floodguard.automated_optical_v2_development_diagnostics.v1",
        "evidence_tier": "exploratory_development_diagnostic_only",
        "role": "development",
        "event_id": receipt["event_id"],
        "source_timestamp": receipt["source_timestamp"],
        "processed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "confidence": "limited: automated pair and spectral strata, no independent pixelwise truth",
        "assumptions": ["Uses only frozen Mae Sai v2 development artifacts and both declared Sentinel-2 scenes."],
        "development_receipt_sha256": receipt["receipt_sha256"],
        "preparation_receipt_sha256": preparation["receipt_sha256"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "event_asset_sha256": {row["asset"]: row["sha256"] for row in rows if row["scene_role"] == "event"},
        "method_raster_sha256": receipt["method_raster_sha256"],
        "cross_review": review,
        **summary,
        "limitations": [
            "Mae Sai has already been inspected; this is development diagnosis, not fresh confirmation.",
            "SCL and visual chips are diagnostic context, not independent flood truth.",
            "The 5 September scene is dry context, not proof that any 15 September cell flooded.",
            "This report does not change v2 methods or inspect the separate event holdout.",
        ],
        "human_reviewed": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    _write_quicklook(
        quicklook_path, event_bands, inside_aoi, event_pairs,
        pair_title="Mae Sai v2 development method pairs",
    )
    result["sample_chips"] = _write_chips(chips_path, event_bands, inside_aoi, event_pairs, transform)
    result["quicklook_sha256"] = file_sha256(quicklook_path)
    result["chips_sha256"] = file_sha256(chips_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
