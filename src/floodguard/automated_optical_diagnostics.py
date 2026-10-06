"""Exploratory diagnostics for the frozen Mae Sai automated optical reference.

These measurements explain disagreement between two automated methods. They
do not revise the pre-registered reference or establish flood-map accuracy.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.automated_reference import (
    AutomatedReferenceError,
    _file_sha256,
    _read_scene,
    _reference_grid,
    compute_cross_review,
    load_asset_manifest,
    load_preregistration,
    validate_automated_reference_receipt,
)

PAIR_NAMES = ("neither", "a_only", "b_only", "both")
PAIR_COLORS = np.array(
    [[0, 0, 0], [255, 183, 50], [62, 205, 238], [241, 94, 183]], dtype=np.uint8,
)


def pair_codes(a: np.ndarray, b: np.ndarray, observable: np.ndarray) -> np.ndarray:
    """Code observable A/B dry and water pairs as 0-3, and other cells as 255."""
    a, b, observable = (np.asarray(value) for value in (a, b, observable))
    if a.shape != b.shape or a.shape != observable.shape or a.ndim != 2:
        raise ValueError("A, B, and observable must share one two-dimensional grid.")
    if a.dtype != np.bool_ or b.dtype != np.bool_ or observable.dtype != np.bool_:
        raise ValueError("A, B, and observable must be Boolean masks.")
    return np.where(observable, a.astype(bool).astype(np.uint8) + 2 * b.astype(bool), 255).astype(np.uint8)


def _dilate_pixels(mask: np.ndarray, radius: int) -> np.ndarray:
    """Dilate a Boolean grid by a Euclidean pixel-center radius."""
    if radius < 0:
        raise ValueError("The radius must be nonnegative.")
    height, width = mask.shape
    padded = np.pad(mask, radius, constant_values=False)
    result = np.zeros((height, width), dtype=bool)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                result |= padded[radius + dy:radius + dy + height, radius + dx:radius + dx + width]
    return result


def _quantiles(values: np.ndarray) -> dict[str, float | None]:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return {"p10": None, "median": None, "p90": None}
    p10, median, p90 = np.quantile(finite, [0.1, 0.5, 0.9])
    return {"p10": float(p10), "median": float(median), "p90": float(p90)}


def summarize_pairs(
    pairs: np.ndarray,
    scl: np.ndarray,
    reflectance: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Count pair types by SCL and spectral conditions on the frozen event grid."""
    if pairs.shape != scl.shape or any(band.shape != pairs.shape for band in reflectance.values()):
        raise ValueError("Pair, SCL, and reflectance grids must agree.")
    if not np.isin(pairs, (0, 1, 2, 3, 255)).all():
        raise ValueError("Pair grid contains an unexpected code.")
    blue, green, red = (reflectance[name] for name in ("blue", "green", "red"))
    nir, swir16, swir22 = (reflectance[name] for name in ("nir", "swir16", "swir22"))
    mndwi = (green - swir16) / np.maximum(green + swir16, 1e-6)
    awei_sh = blue + 2.5 * green - 1.5 * (nir + swir16) - 0.25 * swir22
    ndvi = (nir - red) / np.maximum(nir + red, 1e-6)
    conditions = {"mndwi_gt_0_1": mndwi > 0.1, "awei_sh_gt_0": awei_sh > 0, "ndvi_lt_0_2": ndvi < 0.2}
    pair_counts = {name: int(np.count_nonzero(pairs == code)) for code, name in enumerate(PAIR_NAMES)}
    scl_counts: dict[str, dict[str, int]] = {}
    spectral: dict[str, Any] = {}
    zero_reflectance: dict[str, dict[str, int]] = {}
    for code, name in enumerate(PAIR_NAMES):
        selected = pairs == code
        values, counts = np.unique(scl[selected], return_counts=True)
        scl_counts[name] = {str(int(value)): int(count) for value, count in zip(values, counts, strict=True)}
        spectral[name] = {
            "predicate_pass_counts": {key: int(np.count_nonzero(value & selected)) for key, value in conditions.items()},
            "predicate_fail_counts": {key: int(np.count_nonzero(~value & selected)) for key, value in conditions.items()},
            "indices": {"mndwi": _quantiles(mndwi[selected]), "awei_sh": _quantiles(awei_sh[selected]), "ndvi": _quantiles(ndvi[selected])},
        }
        zero_reflectance[name] = {
            band: int(np.count_nonzero((value == 0) & selected))
            for band, value in reflectance.items()
        }
    a = (pairs == 1) | (pairs == 3)
    b = (pairs == 2) | (pairs == 3)
    nearby = {
        "b_water_within_20m_of_a_water": int(np.count_nonzero(b & _dilate_pixels(a, 2))),
        "a_water_within_20m_of_b_water": int(np.count_nonzero(a & _dilate_pixels(b, 2))),
        "b_only_within_20m_of_a_water": int(np.count_nonzero((pairs == 2) & _dilate_pixels(a, 2))),
        "a_only_within_20m_of_b_water": int(np.count_nonzero((pairs == 1) & _dilate_pixels(b, 2))),
    }
    return {
        "comparable_cell_count": int(np.count_nonzero(pairs != 255)),
        "pair_counts": pair_counts,
        "scl_counts_by_pair": scl_counts,
        "spectral_by_pair": spectral,
        "zero_reflectance_after_conversion_by_pair": zero_reflectance,
        "nearby_20m": nearby,
    }


def _raw_dn_summary(
    scene_dir: Path, transform: Any, shape: tuple[int, int], pairs: np.ndarray,
) -> dict[str, dict[str, dict[str, float | None]]]:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    result: dict[str, dict[str, dict[str, float | None]]] = {name: {} for name in PAIR_NAMES}
    for band in ("blue", "green", "red", "nir", "swir16", "swir22"):
        dn = np.zeros(shape, dtype=np.float32)
        with rasterio.open(scene_dir / f"{band}.tif") as source:
            reproject(
                source=rasterio.band(source, 1), destination=dn,
                src_transform=source.transform, src_crs=source.crs, src_nodata=0,
                dst_transform=transform, dst_crs="EPSG:32647", dst_nodata=0,
                resampling=Resampling.nearest if band in {"blue", "green", "red", "nir"} else Resampling.bilinear,
            )
        for code, name in enumerate(PAIR_NAMES):
            result[name][band] = {
                **_quantiles(dn[pairs == code]),
                "valid_dn_at_or_below_offset_count": int(np.count_nonzero((dn > 0) & (dn <= 1000) & (pairs == code))),
            }
    return result


def _densest_chip(pairs: np.ndarray, code: int, size: int) -> tuple[int, int, int]:
    """Select a deterministic, high-density crop for one pair type."""
    mask = (pairs == code).astype(np.int64)
    height, width = mask.shape
    if size > min(height, width):
        raise ValueError("Chip cannot be larger than the grid.")
    integral = np.pad(mask, ((1, 0), (1, 0))).cumsum(axis=0).cumsum(axis=1)
    counts = integral[size:, size:] - integral[:-size, size:] - integral[size:, :-size] + integral[:-size, :-size]
    row, col = np.unravel_index(int(np.argmax(counts)), counts.shape)
    return int(row), int(col), int(counts[row, col])


def _write_chips(
    path: Path, reflectance: Mapping[str, np.ndarray], inside_aoi: np.ndarray,
    pairs: np.ndarray, transform: Any,
) -> list[dict[str, Any]]:
    from PIL import Image, ImageDraw, ImageFont

    rgb = _true_color(reflectance, pairs != 255)
    side = 180
    scale = 2
    canvas = Image.new("RGB", (2 * side * scale + 36, 3 * side * scale + 120), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    windows = []
    for index, code in enumerate((1, 2, 3)):
        row, col, count = _densest_chip(pairs, code, side)
        cut_rgb = rgb[row:row + side, col:col + side]
        cut_inside = inside_aoi[row:row + side, col:col + side]
        cut_pairs = pairs[row:row + side, col:col + side]
        left = np.where(cut_inside[..., None], cut_rgb, 235).astype(np.uint8)
        right = np.round(left.astype(np.float32) * 0.42).astype(np.uint8)
        right[cut_pairs == 255] = [125, 128, 131]
        for pair_code in (1, 2, 3):
            right[cut_pairs == pair_code] = PAIR_COLORS[pair_code]
        y = 38 + index * (side * scale + 26)
        canvas.paste(Image.fromarray(left).resize((side * scale, side * scale), Image.Resampling.NEAREST), (12, y))
        canvas.paste(Image.fromarray(right).resize((side * scale, side * scale), Image.Resampling.NEAREST), (side * scale + 24, y))
        draw.text((12, y - 16), f"Densest {PAIR_NAMES[code]} chip; {count} matching cells", fill="black", font=font)
        center_x, center_y = transform * (col + side / 2, row + side / 2)
        windows.append({
            "pair": PAIR_NAMES[code], "top_row": row, "left_column": col,
            "size_pixels": side, "matching_cell_count": count,
            "center_easting_m": float(center_x), "center_northing_m": float(center_y),
        })
    draw.text((12, 9), "True colour (left) and frozen method overlay (right); 10 m source pixels shown at 2x", fill="black", font=font)
    draw.text((12, canvas.height - 35), "Exploratory automated classifications, not flood truth.", fill="black", font=font)
    draw.text((12, canvas.height - 18), "Contains modified Copernicus Sentinel data 2024", fill="black", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, optimize=True)
    return windows


def _read_frozen_method(path: Path, expected_hash: str, shape: tuple[int, int], transform: Any) -> np.ndarray:
    import rasterio

    if _file_sha256(path) != expected_hash:
        raise AutomatedReferenceError(f"Frozen method raster SHA-256 mismatch: {path.name}.")
    with rasterio.open(path) as source:
        if source.count != 1 or source.shape != shape or source.crs.to_string() != "EPSG:32647":
            raise AutomatedReferenceError(f"Frozen method raster grid differs: {path.name}.")
        if not source.transform.almost_equals(transform):
            raise AutomatedReferenceError(f"Frozen method raster transform differs: {path.name}.")
        return source.read(1)


def _true_color(reflectance: Mapping[str, np.ndarray], observable: np.ndarray) -> np.ndarray:
    rgb = np.stack([reflectance[name] for name in ("red", "green", "blue")], axis=-1)
    valid = observable & np.all(np.isfinite(rgb), axis=-1)
    if not valid.any():
        raise AutomatedReferenceError("No observable true-color pixels exist.")
    low = np.percentile(rgb[valid], 2, axis=0)
    high = np.percentile(rgb[valid], 98, axis=0)
    image = np.clip((rgb - low) / np.maximum(high - low, 1e-6), 0, 1) ** 0.75
    return np.round(255 * image).astype(np.uint8)


def _write_quicklook(
    path: Path, reflectance: Mapping[str, np.ndarray], inside_aoi: np.ndarray,
    pairs: np.ndarray, *, pair_title: str = "Frozen v1 automated method pairs",
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    rgb = _true_color(reflectance, pairs != 255)
    faded = np.where(inside_aoi[..., None], rgb, 235).astype(np.uint8)
    overlay = np.round(faded.astype(np.float32) * 0.42).astype(np.uint8)
    overlay[pairs == 255] = [125, 128, 131]
    for code in (1, 2, 3):
        overlay[pairs == code] = PAIR_COLORS[code]
    h, w = pairs.shape
    canvas = Image.new("RGB", (2 * w + 36, h + 104), "white")
    canvas.paste(Image.fromarray(faded), (12, 54))
    canvas.paste(Image.fromarray(overlay), (w + 24, 54))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((12, 10), "15 Sep 2024 Sentinel-2 true colour", fill="black", font=font)
    draw.text((w + 24, 10), pair_title, fill="black", font=font)
    x = w + 24
    for label, color in (("A only", PAIR_COLORS[1]), ("B only", PAIR_COLORS[2]), ("both", PAIR_COLORS[3]), ("unobservable", [125, 128, 131])):
        draw.rectangle((x, 32, x + 10, 42), fill=tuple(int(value) for value in color))
        draw.text((x + 14, 31), label, fill="black", font=font)
        x += 105
    draw.text((12, h + 66), "Exploratory disagreement map; colours are automated classifications, not flood truth.", fill="black", font=font)
    draw.text((12, h + 83), "Contains modified Copernicus Sentinel data 2024", fill="black", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, optimize=True)


def build_diagnostics(
    *, repo_root: Path, external_data_root: Path, output_dir: Path,
    result_path: Path, quicklook_path: Path, chips_path: Path,
) -> dict[str, Any]:
    """Verify frozen v1 inputs and write a separate, exploratory disagreement report."""
    prereg = load_preregistration()
    manifest_path = repo_root / "outputs" / "earth_search_mae_sai_sentinel2_reference_assets.csv"
    receipt_path = repo_root / "outputs" / "automated_optical_reference_v1.json"
    label_path = output_dir / "automated_optical_reference_v1.tif"
    receipt = validate_automated_reference_receipt(receipt_path, manifest=manifest_path, raster_path=label_path)
    manifest = load_asset_manifest(manifest_path)
    scene_dir = external_data_root / "earth_search" / "mae_sai_2024" / prereg["source"]["event_item_id"]
    for row in manifest:
        if row["scene_role"] == "event":
            asset_path = scene_dir / f"{row['asset']}.tif"
            if asset_path.stat().st_size != row["file_size_bytes"] or _file_sha256(asset_path) != row["sha256"]:
                raise AutomatedReferenceError(f"Event optical asset differs from its frozen manifest: {row['asset']}.")
    transform, shape, inside_aoi = _reference_grid(repo_root / prereg["grid"]["aoi_path"], scene_dir / "blue.tif")
    if list(transform)[:6] != receipt["grid"]["transform"] or list(shape) != [receipt["grid"]["height"], receipt["grid"]["width"]]:
        raise AutomatedReferenceError("Diagnostic grid differs from the frozen reference receipt.")
    reflectance, spectral_water, observable, scl = _read_scene(
        scene_dir, grid_transform=transform, grid_shape=shape, inside_aoi=inside_aoi,
    )
    a = _read_frozen_method(output_dir / "event_method_a_water.tif", receipt["method_raster_sha256"]["event_a"], shape, transform)
    b = _read_frozen_method(output_dir / "event_method_b_water.tif", receipt["method_raster_sha256"]["event_b"], shape, transform)
    if not np.array_equal(a != 255, observable) or not np.array_equal(b != 255, observable):
        raise AutomatedReferenceError("Frozen method observability differs from source-derived observability.")
    if not np.array_equal(b[observable] > 0, spectral_water[observable]):
        raise AutomatedReferenceError("Frozen spectral method differs from source-derived spectral rule.")
    pairs = pair_codes(a == 1, b == 1, observable)
    review = compute_cross_review(
        a == 1, b == 1, observable,
        min_water_dice=prereg["cross_review_limits"]["min_water_dice"],
        min_cohen_kappa=prereg["cross_review_limits"]["min_cohen_kappa"],
    )
    if review != receipt["ab_agreement"]:
        raise AutomatedReferenceError("Computed method agreement differs from frozen reference receipt.")
    summary = summarize_pairs(pairs, scl, reflectance)
    summary["raw_dn_by_pair"] = _raw_dn_summary(scene_dir, transform, shape, pairs)
    values, counts = np.unique(scl[inside_aoi], return_counts=True)
    summary["raw_scl_aoi_counts"] = {str(int(value)): int(count) for value, count in zip(values, counts, strict=True)}
    scale = min(1.0, prereg["methods"]["A"]["max_input_dimension_pixels"] / max(shape))
    model_grid = {"width": round(shape[1] * scale), "height": round(shape[0] * scale)}
    result = {
        "schema": "floodguard.automated_optical_diagnostics.v1",
        "evidence_tier": "exploratory_diagnostic_only",
        "source_timestamp": prereg["source"]["event_sensing_utc"],
        "processed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "confidence": "limited: automated pair and SCL strata; no independent pixelwise flood truth",
        "assumptions": ["Uses the frozen v1 observability mask, grid, method rasters, and Element84 COG inputs."],
        "reference_receipt_sha256": receipt["receipt_sha256"],
        "preregistration_sha256": prereg["preregistration_sha256"],
        "event_asset_sha256": {row["asset"]: row["sha256"] for row in manifest if row["scene_role"] == "event"},
        "method_raster_sha256": {name: receipt["method_raster_sha256"][name] for name in ("event_a", "event_b")},
        "model_input_grid_pixels": model_grid,
        "reference_grid_pixels": {"width": shape[1], "height": shape[0]},
        "cross_review": review,
        **summary,
        "limitations": [
            "SCL is an automated scene class and is not independent flood truth.",
            "Disagreement strata use the v1 observable cells; masking difficult cells can change apparent agreement.",
            "The RGB preview is percentile-stretched for display and cannot identify flood truth by itself.",
            "This report does not revise v1 or authorize reopening its consumed final holdout.",
        ],
        "human_reviewed": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    _write_quicklook(quicklook_path, reflectance, inside_aoi, pairs)
    result["sample_chips"] = _write_chips(chips_path, reflectance, inside_aoi, pairs, transform)
    result["quicklook_sha256"] = _file_sha256(quicklook_path)
    result["chips_sha256"] = _file_sha256(chips_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
