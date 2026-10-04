"""Prospective optical cross-review separate from the frozen Mae Sai v1 track."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.automated_reference import (
    assign_label_codes,
    compute_cross_review,
    count_aoi_classes,
    spectral_water_rule,
    validate_automated_reference_receipt,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = REPO_ROOT / "docs/proposal_execution/automated_track/preregistration_v2.json"
PLAN_COMMIT = "efc69f5f66dfe8c2d667a9827566126709f1cab9"
PLAN_REPO_PATH = "docs/proposal_execution/automated_track/preregistration_v2.json"
FEASIBILITY_PATH = REPO_ROOT / "docs/proposal_execution/automated_track/preregistration_v2_feasibility_gate.json"
FEASIBILITY_COMMIT = "09a4e03c14da9a9bd72cb70f0c7711f703fc9c0d"
FEASIBILITY_REPO_PATH = "docs/proposal_execution/automated_track/preregistration_v2_feasibility_gate.json"
ASSETS = ("blue", "green", "red", "nir", "nir08", "swir16", "swir22", "scl")
REFLECTANCE_ASSETS = ASSETS[:-1]


class AutomatedOpticalV2Error(ValueError):
    """Raised when a v2 plan, input, or one-use study contract is invalid."""


def canonical_sha256(value: Mapping[str, Any], *, omit: str) -> str:
    """Hash a JSON object without its designated self-hash field."""
    encoded = json.dumps(
        {key: item for key, item in value.items() if key != omit},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    """Hash file bytes in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_plan(path: Path = PLAN_PATH) -> dict[str, Any]:
    """Verify the immutable v2 plan, including its original Git commit."""
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
        shown = subprocess.run(
            ["git", "show", f"{PLAN_COMMIT}:{PLAN_REPO_PATH}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout
        committed = json.loads(shown.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
        raise AutomatedOpticalV2Error("V2 pre-registration or its Git commit is unavailable.") from exc
    digest = plan.get("preregistration_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise AutomatedOpticalV2Error("V2 pre-registration digest is invalid.")
    if digest != canonical_sha256(plan, omit="preregistration_sha256") or plan != committed:
        raise AutomatedOpticalV2Error("V2 pre-registration differs from its self-hash or frozen commit.")
    if plan.get("schema") != "floodguard.automated_optical_preregistration.v2":
        raise AutomatedOpticalV2Error("Unexpected v2 pre-registration schema.")
    for field, expected in (
        ("human_reviewed", False), ("accepted_observation", False),
        ("official_warning", False), ("can_feed_decision_layer", False),
        ("operational_status", "non_operational"),
    ):
        if plan.get(field) != expected:
            raise AutomatedOpticalV2Error(f"Unsafe v2 pre-registration field: {field}.")
    return plan


def load_feasibility_gate(plan: Mapping[str, Any], path: Path = FEASIBILITY_PATH) -> dict[str, Any]:
    """Verify the stricter positive-count rule committed before holdout inference."""
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
        shown = subprocess.run(
            ["git", "show", f"{FEASIBILITY_COMMIT}:{FEASIBILITY_REPO_PATH}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout
        committed = json.loads(shown.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError, subprocess.CalledProcessError) as exc:
        raise AutomatedOpticalV2Error("V2 holdout feasibility gate or its commit is unavailable.") from exc
    digest = gate.get("feasibility_gate_sha256")
    if (gate != committed or not isinstance(digest, str)
            or digest != canonical_sha256(gate, omit="feasibility_gate_sha256")
            or gate.get("schema") != "floodguard.automated_optical_v2_feasibility_gate.v1"
            or gate.get("base_preregistration_sha256") != plan["preregistration_sha256"]
            or gate.get("base_preregistration_commit") != PLAN_COMMIT
            or gate.get("holdout_event_id") != plan["final_holdout"]["event_id"]):
        raise AutomatedOpticalV2Error("V2 holdout feasibility gate differs from the frozen plan or commit.")
    for key in ("minimum_event_water_cells_each_method", "minimum_shared_water_cells"):
        if not isinstance(gate.get(key), int) or isinstance(gate[key], bool) or gate[key] <= 0:
            raise AutomatedOpticalV2Error("V2 holdout positive-count gate is invalid.")
    for field, expected in (
        ("human_reviewed", False), ("accepted_observation", False),
        ("official_warning", False), ("can_feed_decision_layer", False),
        ("operational_status", "non_operational"),
    ):
        if gate.get(field) != expected:
            raise AutomatedOpticalV2Error(f"Unsafe v2 feasibility gate field: {field}.")
    return gate


def assess_positive_feasibility(
    a: np.ndarray, b: np.ndarray, observable: np.ndarray, gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Require enough positive water cells before interpreting holdout agreement."""
    a_values = np.asarray(a, dtype=bool)
    b_values = np.asarray(b, dtype=bool)
    mask = np.asarray(observable, dtype=bool)
    if a_values.shape != b_values.shape or a_values.shape != mask.shape:
        raise AutomatedOpticalV2Error("V2 positive-feasibility rasters do not align.")
    count_a = int(np.sum(a_values & mask))
    count_b = int(np.sum(b_values & mask))
    shared = int(np.sum(a_values & b_values & mask))
    minimum_each = gate["minimum_event_water_cells_each_method"]
    minimum_shared = gate["minimum_shared_water_cells"]
    return {
        "water_count_a": count_a, "water_count_b": count_b,
        "shared_water_count": shared,
        "minimum_event_water_cells_each_method": minimum_each,
        "minimum_shared_water_cells": minimum_shared,
        "passes": count_a >= minimum_each and count_b >= minimum_each and shared >= minimum_shared,
    }


def load_asset_manifest(path: Path, plan: Mapping[str, Any], role: str) -> list[dict[str, Any]]:
    """Verify exact scene identities and per-asset radiometry metadata."""
    if role not in {"development", "final_holdout"}:
        raise AutomatedOpticalV2Error("Unknown v2 study role.")
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise AutomatedOpticalV2Error("V2 asset manifest is unavailable.") from exc
    if len(rows) != 16:
        raise AutomatedOpticalV2Error("V2 asset manifest needs exactly 16 assets.")
    episode = plan[role]
    expected_ids = {"event": episode["event_item_id"], "dry": episode["dry_item_id"]}
    expected_products = {
        "event": episode.get("event_product_uri"), "dry": episode.get("dry_product_uri"),
    }
    parsed = []
    seen: set[tuple[str, str]] = set()
    scene_times: dict[str, datetime] = {}
    for raw in rows:
        try:
            scene_role, asset = raw["scene_role"], raw["asset"]
            item_id, product_uri = raw["item_id"], raw["product_uri"]
            size, digest = int(raw["file_size_bytes"]), raw["sha256"]
            url, edition = raw["asset_url"], raw["source_edition"]
            scale = float(raw["scale"]) if asset != "scl" else None
            offset = float(raw["offset"]) if asset != "scl" else None
            baseline = raw["processing_baseline"]
            sensing_utc = raw["sensing_utc"]
            sensing_time = datetime.fromisoformat(sensing_utc.replace("Z", "+00:00"))
            preregistration_sha256 = raw["preregistration_sha256"]
            original_safe_sha256 = raw["original_safe_sha256"]
        except (KeyError, ValueError, TypeError) as exc:
            raise AutomatedOpticalV2Error("V2 asset row is incomplete.") from exc
        product_baseline = re.search(r"_N([0-9]{4})_", product_uri)
        expected_baseline = (
            f"{product_baseline.group(1)[:2]}.{product_baseline.group(1)[2:]}"
            if product_baseline else None
        )
        key = (scene_role, asset)
        if (key in seen or scene_role not in expected_ids or asset not in ASSETS
                or item_id != expected_ids[scene_role]
                or (expected_products[scene_role] is not None and product_uri != expected_products[scene_role])
                or edition != plan["source_edition"]
                or baseline != expected_baseline
                or sensing_time.tzinfo is None
                or preregistration_sha256 != plan["preregistration_sha256"]
                or original_safe_sha256 != "not_recorded"):
            raise AutomatedOpticalV2Error("V2 asset identity or source edition differs from the plan.")
        if scene_role in scene_times and sensing_time != scene_times[scene_role]:
            raise AutomatedOpticalV2Error("V2 asset sensing times disagree within a scene.")
        scene_times[scene_role] = sensing_time
        if (size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not url.startswith("https://")
                or (asset != "scl" and (not math.isfinite(scale) or not math.isfinite(offset) or scale <= 0))):
            raise AutomatedOpticalV2Error("V2 asset size, hash, URL or radiometry is invalid.")
        seen.add(key)
        parsed.append({
            "scene_role": scene_role, "asset": asset, "item_id": item_id,
            "product_uri": product_uri, "asset_url": url, "file_size_bytes": size,
            "sha256": digest, "scale": scale, "offset": offset,
            "source_edition": edition, "processing_baseline": baseline,
            "sensing_utc": sensing_utc, "original_safe_sha256": original_safe_sha256,
        })
    if seen != {(scene, asset) for scene in ("event", "dry") for asset in ASSETS}:
        raise AutomatedOpticalV2Error("V2 asset manifest is missing an asset.")
    if role == "final_holdout":
        for scene_role in ("event", "dry"):
            expected_time = datetime.fromisoformat(
                episode[f"{scene_role}_sensing_utc"].replace("Z", "+00:00")
            )
            if scene_times[scene_role] != expected_time:
                raise AutomatedOpticalV2Error("V2 holdout sensing time differs from the frozen plan.")
    if role == "development" and file_sha256(path) == plan[role]["asset_manifest_sha256"]:
        raise AutomatedOpticalV2Error("V2 metadata manifest must be separate from the v1 asset manifest.")
    if role == "development":
        original_path = REPO_ROOT / plan[role]["asset_manifest_path"]
        if file_sha256(original_path) != plan[role]["asset_manifest_sha256"]:
            raise AutomatedOpticalV2Error("Frozen v1 asset manifest changed.")
        with original_path.open(newline="", encoding="utf-8") as stream:
            original = {(row["scene_role"], row["asset"]): row for row in csv.DictReader(stream)}
        for row in parsed:
            old = original.get((row["scene_role"], row["asset"]))
            if (old is None or old["item_id"] != row["item_id"]
                    or old["product_uri"] != row["product_uri"]
                    or old["asset_url"] != row["asset_url"]
                    or int(old["file_size_bytes"]) != row["file_size_bytes"]
                    or old["sha256"] != row["sha256"]):
                raise AutomatedOpticalV2Error("V2 development asset differs from frozen v1 source.")
    return sorted(parsed, key=lambda row: (row["scene_role"], row["asset"]))


def scene_root(external_root: Path, role: str) -> Path:
    """Return the isolated source directory for one planned episode."""
    edition = "mae_sai_2024" if role == "development" else "chaiyaphum_2021_v2"
    return external_root / "earth_search" / edition


def verify_asset_files(rows: list[dict[str, Any]], source_root: Path) -> None:
    """Refuse missing or byte-different optical COGs before a model run."""
    for row in rows:
        path = source_root / row["item_id"] / f"{row['asset']}.tif"
        if not path.is_file() or path.stat().st_size != row["file_size_bytes"]:
            raise AutomatedOpticalV2Error(f"V2 asset missing or size mismatch: {row['scene_role']}/{row['asset']}.")
        if file_sha256(path) != row["sha256"]:
            raise AutomatedOpticalV2Error(f"V2 asset hash mismatch: {row['scene_role']}/{row['asset']}.")


def expanded_scl_unobservable(scl: np.ndarray, *, pixel_size_m: int = 10) -> np.ndarray:
    """Apply frozen v2 SCL 0/1/2/3/8/9/10 and 20 m Euclidean buffer."""
    values = np.asarray(scl)
    if values.ndim != 2 or pixel_size_m != 10:
        raise AutomatedOpticalV2Error("V2 SCL mask requires a 10 m two-dimensional grid.")
    seed = np.isin(values, (0, 1, 2, 3, 8, 9, 10))
    result = np.zeros_like(seed)
    height, width = seed.shape
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dx * dx + dy * dy > 4:
                continue
            source_y = slice(max(0, -dy), min(height, height - dy))
            source_x = slice(max(0, -dx), min(width, width - dx))
            target_y = slice(max(0, dy), min(height, height + dy))
            target_x = slice(max(0, dx), min(width, width + dx))
            result[target_y, target_x] |= seed[source_y, source_x]
    return result


def spectral_validity_only(bands: Mapping[str, np.ndarray]) -> np.ndarray:
    """Find valid index denominators without producing holdout water predictions."""
    needed = ("blue", "green", "red", "nir", "swir16", "swir22")
    values = [np.asarray(bands[name], dtype=np.float32) for name in needed]
    if any(value.shape != values[0].shape for value in values):
        raise AutomatedOpticalV2Error("V2 spectral bands do not align.")
    return (
        np.logical_and.reduce([np.isfinite(value) for value in values])
        & (values[1] + values[4] > 1e-6)
        & (values[3] + values[2] > 1e-6)
    )


def reference_grid(plan: Mapping[str, Any], role: str, blue_path: Path) -> tuple[Any, tuple[int, int], np.ndarray]:
    """Snap the planned AOI to its event T47 tile's exact 10 m origin."""
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from shapely.geometry import box, shape
    from shapely.ops import transform, unary_union

    if role == "development":
        aoi_path = REPO_ROOT / plan[role]["aoi_path"]
        if file_sha256(aoi_path) != plan[role]["aoi_sha256"]:
            raise AutomatedOpticalV2Error("V2 development AOI differs from the plan.")
        content = json.loads(aoi_path.read_text(encoding="utf-8"))
        features = content["features"] if content.get("type") == "FeatureCollection" else [content]
        geometry = unary_union([shape(feature["geometry"]) for feature in features])
    else:
        geometry = box(*plan[role]["aoi_bbox_wgs84"])
    projected = transform(Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform, geometry)
    with rasterio.open(blue_path) as source:
        if source.crs.to_string() != "EPSG:32647" or source.res != (10.0, 10.0):
            raise AutomatedOpticalV2Error("Event blue asset does not define the planned 10 m UTM grid.")
        origin_x, origin_y = source.transform.c, source.transform.f
        min_x, min_y, max_x, max_y = projected.bounds
        left = math.floor((min_x - origin_x) / 10)
        right = math.ceil((max_x - origin_x) / 10)
        top = math.floor((origin_y - max_y) / 10)
        bottom = math.ceil((origin_y - min_y) / 10)
        if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
            raise AutomatedOpticalV2Error("Planned AOI lies outside the event tile.")
        grid_transform = source.transform * rasterio.Affine.translation(left, top)
    grid_shape = (bottom - top, right - left)
    inside = geometry_mask([projected], out_shape=grid_shape, transform=grid_transform, invert=True, all_touched=False)
    if not np.any(inside):
        raise AutomatedOpticalV2Error("Planned AOI has no grid cells.")
    return grid_transform, grid_shape, inside


def read_scene(
    rows: list[dict[str, Any]], source_root: Path, scene_role: str,
    grid_transform: Any, grid_shape: tuple[int, int], inside_aoi: np.ndarray,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Read one scene with each asset's pinned STAC radiometry and v2 quality mask."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    row_map = {row["asset"]: row for row in rows if row["scene_role"] == scene_role}
    bands: dict[str, np.ndarray] = {}
    valid_bands = []
    for asset in REFLECTANCE_ASSETS:
        row = row_map[asset]
        digital_numbers = np.zeros(grid_shape, dtype=np.float32)
        with rasterio.open(source_root / row["item_id"] / f"{asset}.tif") as source:
            if source.crs.to_string() != "EPSG:32647":
                raise AutomatedOpticalV2Error("Optical asset CRS differs from the plan.")
            reproject(
                source=rasterio.band(source, 1), destination=digital_numbers,
                src_transform=source.transform, src_crs=source.crs, src_nodata=0,
                dst_transform=grid_transform, dst_crs="EPSG:32647", dst_nodata=0,
                resampling=Resampling.nearest if asset in {"blue", "green", "red", "nir"} else Resampling.bilinear,
            )
        physical = digital_numbers * row["scale"] + row["offset"]
        bands[asset] = np.clip(physical, 0, 1).astype(np.float32)
        valid_bands.append((digital_numbers > 0) & np.isfinite(physical))
    scl = np.zeros(grid_shape, dtype=np.uint8)
    row = row_map["scl"]
    with rasterio.open(source_root / row["item_id"] / "scl.tif") as source:
        reproject(
            source=rasterio.band(source, 1), destination=scl,
            src_transform=source.transform, src_crs=source.crs, src_nodata=0,
            dst_transform=grid_transform, dst_crs="EPSG:32647", dst_nodata=0,
            resampling=Resampling.nearest,
        )
    spectral_valid = spectral_validity_only(bands)
    observable = inside_aoi & ~expanded_scl_unobservable(scl) & np.logical_and.reduce(valid_bands) & spectral_valid
    return bands, observable, scl


def model_input(bands: Mapping[str, np.ndarray], observable: np.ndarray) -> np.ndarray:
    """Build the full-resolution six-band model stack with masked no-data cells."""
    stack = np.stack([bands[name] for name in ("blue", "green", "red", "nir", "swir16", "swir22")])
    if stack.shape[1:] != observable.shape:
        raise AutomatedOpticalV2Error("V2 model bands and quality mask do not align.")
    stack[:, ~observable] = -9999.0
    return stack.astype(np.float32)


def effective_model_tiling(input_stack: np.ndarray) -> dict[str, Any]:
    """Record the pinned OmniCloudMask 1.7.1 nodata patch adjustment."""
    if input_stack.ndim != 3 or input_stack.shape[0] != 6:
        raise AutomatedOpticalV2Error("V2 model input must contain six bands.")
    height, width = input_stack.shape[1:]
    if min(height, width) < 32:
        raise AutomatedOpticalV2Error("V2 model grid is smaller than the package minimum.")
    nodata_fraction = float(np.count_nonzero(input_stack == -9999.0) / input_stack.size)
    requested_patch, requested_overlap = 512, 128
    effective_patch, effective_overlap = requested_patch, requested_overlap
    if nodata_fraction > 0.3 and effective_patch > min(height, width) / 2:
        effective_patch = max(min(height, width) // 2, 32)
        effective_overlap = min(effective_overlap, effective_patch // 2)
    if effective_patch > min(height, width):
        effective_patch = max(min(height, width), 32)
        effective_overlap = min(effective_overlap, effective_patch // 2)
    return {
        "requested_patch_size_pixels": requested_patch,
        "requested_overlap_size_pixels": requested_overlap,
        "effective_patch_size_pixels": effective_patch,
        "effective_overlap_size_pixels": effective_overlap,
        "nodata_fraction": nodata_fraction,
        "effective_size_rule": "OmniCloudMask 1.7.1 cloud_mask.py nodata adjustment",
    }


def write_raster(path: Path, values: np.ndarray, grid_transform: Any, *, nodata: float) -> None:
    """Write compressed UTM raster bytes outside Git."""
    import rasterio

    data = values[np.newaxis, :, :] if values.ndim == 2 else values
    if data.ndim != 3:
        raise AutomatedOpticalV2Error("V2 raster must have two or three dimensions.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=data.shape[2], height=data.shape[1],
        count=data.shape[0], dtype=data.dtype, crs="EPSG:32647", transform=grid_transform,
        nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256,
    ) as target:
        target.write(data)


def run_native_model(input_path: Path, output_path: Path, *, model_dir: Path, cache_dir: Path) -> None:
    """Run the pinned package on native 10 m tiles with frozen overlap."""
    import geoai
    import omniwatermask

    if geoai.__version__ != "0.41.1" or omniwatermask.__version__ != "0.5.0":
        raise AutomatedOpticalV2Error("Research environment differs from frozen model versions.")
    if importlib.metadata.version("omnicloudmask") != "1.7.1":
        raise AutomatedOpticalV2Error("Research tiling dependency differs from recorded version.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    geoai.segment_water(
        str(input_path), band_order=[3, 2, 1, 4], output_raster=str(output_path),
        batch_size=1, device="cpu", dtype="float32", no_data_value=-9999,
        patch_size=512, overlap_size=128, use_osm_water=False,
        use_osm_building=False, use_osm_roads=False, use_cache=False,
        cache_dir=str(cache_dir), model_dir=str(model_dir),
        version="OmniWaterMask_0.5.0", model_download_source="hugging_face",
        verbose=True,
    )
    if not output_path.is_file():
        raise AutomatedOpticalV2Error("Native model produced no output raster.")


def model_water(input_path: Path, output_path: Path, grid_shape: tuple[int, int], grid_transform: Any) -> np.ndarray:
    """Validate native model alignment and read its binary water band."""
    import rasterio

    with rasterio.open(input_path) as source, rasterio.open(output_path) as result:
        if (source.shape != grid_shape or result.shape != grid_shape or result.count != 1
                or result.crs.to_string() != "EPSG:32647"
                or not source.transform.almost_equals(grid_transform)
                or not result.transform.almost_equals(grid_transform)):
            raise AutomatedOpticalV2Error("Native model output grid differs from the planned grid.")
        values = result.read(1)
    if not np.all(np.isin(values, (0, 1))):
        raise AutomatedOpticalV2Error("Native model output has unexpected water codes.")
    return values > 0


def write_self_hashed(payload: Mapping[str, Any], path: Path) -> dict[str, Any]:
    """Write a self-hashed small receipt."""
    value = dict(payload)
    value["receipt_sha256"] = canonical_sha256(value, omit="receipt_sha256")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return value


def verify_receipt(path: Path, schema: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a v2 receipt's self-hash, frozen plan, and safety fields."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomatedOpticalV2Error("V2 receipt is unavailable or malformed.") from exc
    if (value.get("schema") != schema
            or value.get("receipt_sha256") != canonical_sha256(value, omit="receipt_sha256")
            or value.get("preregistration_sha256") != plan["preregistration_sha256"]
            or value.get("preregistration_commit") != PLAN_COMMIT):
        raise AutomatedOpticalV2Error("V2 receipt, plan hash, or Git commit does not verify.")
    for field, expected in (
        ("human_reviewed", False), ("accepted_observation", False),
        ("official_warning", False), ("can_feed_decision_layer", False),
        ("operational_status", "non_operational"),
    ):
        if value.get(field) != expected:
            raise AutomatedOpticalV2Error(f"Unsafe v2 receipt field: {field}.")
    if value.get("role") == "final_holdout":
        gate = load_feasibility_gate(plan)
        if (value.get("feasibility_gate_sha256") != gate["feasibility_gate_sha256"]
                or value.get("feasibility_gate_commit") != FEASIBILITY_COMMIT):
            raise AutomatedOpticalV2Error("V2 holdout receipt lacks its frozen positive-count gate.")
    if schema == "floodguard.automated_optical_v2_result.v1":
        verify_result_consistency(value, plan)
    return value


def verify_result_consistency(value: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
    """Refuse a rehashed result whose counts, scores, or pass flag contradict its plan."""
    role = value.get("role")
    if role not in {"development", "final_holdout"}:
        raise AutomatedOpticalV2Error("V2 result role is invalid.")
    limits = plan["cross_review_limits"]
    agreement = value.get("ab_agreement")
    grid = value.get("grid")
    counts = value.get("class_counts")
    quality = value.get("quality")
    if (value.get("cross_review_limits") != limits
            or value.get("metric_interpretation") != plan["metric_interpretation"]
            or value.get("event_id") != plan[role]["event_id"]
            or not isinstance(agreement, dict) or not isinstance(grid, dict)
            or not isinstance(counts, dict) or not isinstance(quality, dict)):
        raise AutomatedOpticalV2Error("V2 result does not match its frozen method contract.")
    try:
        n = agreement["valid_pair_count"]
        a, b = agreement["water_count_a"], agreement["water_count_b"]
        dice, kappa = agreement["water_dice"], agreement["cohen_kappa"]
        observable = quality["event"]["observable_aoi_cells"]
        aoi = grid["aoi_cells"]
        coverage = value["event_observable_fraction_of_aoi"]
        class_total = sum(counts[str(code)] for code in range(5))
    except (KeyError, TypeError, ValueError) as exc:
        raise AutomatedOpticalV2Error("V2 result counts are incomplete.") from exc
    if (not all(type(number) is int for number in (n, a, b, observable, aoi, class_total))
            or not 0 < n == observable <= aoi or not 0 <= a <= n or not 0 <= b <= n
            or class_total != aoi or counts["4"] != aoi - n
            or agreement.get("ignored_pair_count") != 0
            or agreement.get("human_reviewed") is not False
            or agreement.get("evidence_tier") != "automated_cross_review"
            or not isinstance(coverage, (int, float)) or not math.isfinite(coverage)
            or not math.isclose(coverage, n / aoi, rel_tol=0, abs_tol=1e-12)):
        raise AutomatedOpticalV2Error("V2 result area or pair counts are inconsistent.")
    if dice is not None and (not isinstance(dice, (int, float)) or not math.isfinite(dice)
                             or not 0 <= dice <= 1):
        raise AutomatedOpticalV2Error("V2 Dice value is invalid.")
    if kappa is not None and (not isinstance(kappa, (int, float)) or not math.isfinite(kappa)
                              or not -1 <= kappa <= 1):
        raise AutomatedOpticalV2Error("V2 kappa value is invalid.")
    positive = value.get("positive_feasibility")
    if role == "final_holdout":
        gate = load_feasibility_gate(plan)
        if (not isinstance(positive, dict)
                or positive.get("water_count_a") != a or positive.get("water_count_b") != b
                or positive.get("minimum_event_water_cells_each_method")
                != gate["minimum_event_water_cells_each_method"]
                or positive.get("minimum_shared_water_cells") != gate["minimum_shared_water_cells"]
                or not isinstance(positive.get("shared_water_count"), int)
                or not 0 <= positive["shared_water_count"] <= min(a, b)):
            raise AutomatedOpticalV2Error("V2 holdout positive counts differ from its frozen gate.")
        shared = positive["shared_water_count"]
        feasibility_pass = (
            a >= gate["minimum_event_water_cells_each_method"]
            and b >= gate["minimum_event_water_cells_each_method"]
            and shared >= gate["minimum_shared_water_cells"]
        )
        if positive.get("passes") is not feasibility_pass or not value.get("holdout_consumption_marker_sha256"):
            raise AutomatedOpticalV2Error("V2 holdout feasibility or consumption marker is inconsistent.")
    else:
        if positive is not None or value.get("holdout_consumption_marker_sha256") is not None:
            raise AutomatedOpticalV2Error("Development result must not claim a consumed holdout.")
        shared = round(dice * (a + b) / 2) if dice is not None else 0
        feasibility_pass = True
    expected_dice = (2 * shared / (a + b)) if a + b else None
    if (dice is None) != (expected_dice is None) or (
        dice is not None and not math.isclose(dice, expected_dice, rel_tol=0, abs_tol=1e-12)
    ):
        raise AutomatedOpticalV2Error("V2 Dice differs from reported water counts.")
    po = (n - a - b + 2 * shared) / n
    pe = (a * b + (n - a) * (n - b)) / (n * n)
    expected_kappa = (po - pe) / (1 - pe) if not math.isclose(pe, 1.0, rel_tol=0, abs_tol=1e-15) else None
    if (kappa is None) != (expected_kappa is None) or (
        kappa is not None and not math.isclose(kappa, expected_kappa, rel_tol=0, abs_tol=1e-9)
    ):
        raise AutomatedOpticalV2Error("V2 kappa differs from reported water counts.")
    pair_pass = dice is not None and kappa is not None and dice >= limits["min_water_dice"] and kappa >= limits["min_cohen_kappa"]
    overall_pass = pair_pass and coverage >= limits["min_event_observable_fraction_of_aoi"] and feasibility_pass
    if agreement.get("passes_limits") is not pair_pass or value.get("passes_all_limits") is not overall_pass:
        raise AutomatedOpticalV2Error("V2 result pass flag contradicts its frozen limits.")


def validate_result_artifacts(
    *, result_path: Path, preparation_path: Path, manifest_path: Path,
    external_root: Path, output_dir: Path, quicklook_path: Path,
    development_path: Path | None = None,
) -> dict[str, Any]:
    """Verify a recorded v2 result and its file/marker hashes without rerunning scoring."""
    plan = load_plan()
    result = verify_receipt(result_path, "floodguard.automated_optical_v2_result.v1", plan)
    preparation = verify_receipt(
        preparation_path, "floodguard.automated_optical_v2_preparation.v1", plan,
    )
    role = result["role"]
    if (preparation.get("role") != role
            or result.get("preparation_receipt_sha256") != preparation["receipt_sha256"]
            or result.get("input_manifest_sha256") != file_sha256(manifest_path)
            or preparation.get("asset_manifest_sha256") != result["input_manifest_sha256"]
            or result.get("input_assets") != preparation.get("input_assets")):
        raise AutomatedOpticalV2Error("V2 result and preparation inputs do not match.")
    rows = load_asset_manifest(manifest_path, plan, role)
    if rows != result["input_assets"]:
        raise AutomatedOpticalV2Error("V2 result assets differ from the source manifest.")
    verify_asset_files(rows, scene_root(external_root, role))
    if (result.get("model_raster_sha256") != preparation.get("model_raster_sha256")
            or result.get("model_tiling") != preparation.get("model_tiling")
            or result.get("model_runtime_versions") != preparation.get("model_runtime_versions")
            or result.get("source_timestamp") != preparation.get("source_timestamp")
            or result.get("dry_context_source_timestamp") != preparation.get("dry_context_source_timestamp")):
        raise AutomatedOpticalV2Error("V2 model or source-time provenance differs from preparation.")
    for scene_role in ("event", "dry"):
        for kind in ("input", "output"):
            path = output_dir / f"{scene_role}_native_model_{kind}.tif"
            expected = result["model_raster_sha256"][scene_role][f"{kind}_sha256"]
            if file_sha256(path) != expected:
                raise AutomatedOpticalV2Error("V2 prepared model raster hash mismatch.")
        for method in ("a", "b"):
            key = f"{scene_role}_{method}"
            if file_sha256(output_dir / f"{scene_role}_method_{method}_water.tif") != result["method_raster_sha256"][key]:
                raise AutomatedOpticalV2Error("V2 method raster hash mismatch.")
    if (file_sha256(output_dir / "automated_optical_reference_v2.tif") != result["label_raster_sha256"]
            or file_sha256(quicklook_path) != result["quicklook_sha256"]):
        raise AutomatedOpticalV2Error("V2 label or quicklook hash mismatch.")
    if role == "final_holdout":
        if development_path is None:
            raise AutomatedOpticalV2Error("V2 final verification needs the development receipt.")
        gate = load_feasibility_gate(plan)
        development = verify_receipt(
            development_path, "floodguard.automated_optical_v2_result.v1", plan,
        )
        marker_path = (external_root / "proposal_execution" / "automated_track" / "v2"
                       / "automated_optical_holdout_consumption.json")
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AutomatedOpticalV2Error("V2 exclusive holdout marker is unavailable.") from exc
        if (marker.get("schema") != "floodguard.automated_optical_holdout_consumption.v2"
                or marker.get("marker_sha256") != canonical_sha256(marker, omit="marker_sha256")
                or marker["marker_sha256"] != result["holdout_consumption_marker_sha256"]
                or marker.get("preregistration_sha256") != plan["preregistration_sha256"]
                or marker.get("preregistration_commit") != PLAN_COMMIT
                or marker.get("feasibility_gate_sha256") != gate["feasibility_gate_sha256"]
                or marker.get("feasibility_gate_commit") != FEASIBILITY_COMMIT
                or marker.get("preparation_receipt_sha256") != preparation["receipt_sha256"]
                or marker.get("development_receipt_sha256") != development["receipt_sha256"]
                or result.get("development_receipt_sha256") != development["receipt_sha256"]):
            raise AutomatedOpticalV2Error("V2 holdout marker or development binding is invalid.")
    return result


def utc_now() -> str:
    """Return a machine processing timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def prepare_episode(
    *, role: str, manifest: Path, external_root: Path, output_dir: Path,
    prepare_receipt: Path, research_python: Path,
) -> dict[str, Any]:
    """Prepare full-grid model outputs without comparing holdout water predictions."""
    plan = load_plan()
    gate = load_feasibility_gate(plan) if role == "final_holdout" else None
    if role == "final_holdout" and (external_root / "proposal_execution" / "automated_track" / "v2"
                                    / "automated_optical_holdout_consumption.json").exists():
        raise AutomatedOpticalV2Error("The automated optical v2 holdout was already consumed.")
    rows = load_asset_manifest(manifest, plan, role)
    root = scene_root(external_root, role)
    verify_asset_files(rows, root)
    if role == "development":
        v1_receipt = validate_automated_reference_receipt(
            REPO_ROOT / "outputs/automated_optical_reference_v1.json",
            manifest=REPO_ROOT / plan[role]["asset_manifest_path"],
            raster_path=external_root / "proposal_execution" / "automated_track" / "automated_optical_reference_v1.tif",
        )
        if v1_receipt["receipt_sha256"] != plan[role]["v1_reference_receipt_sha256"]:
            raise AutomatedOpticalV2Error("Frozen v1 reference receipt differs from the v2 plan.")
    grid_transform, grid_shape, inside = reference_grid(plan, role, root / plan[role]["event_item_id"] / "blue.tif")
    model_dir = external_root / "proposal_execution" / "automated_track" / "model"
    weights = list(model_dir.glob("*.pth"))
    if len(weights) != 1 or file_sha256(weights[0]) != plan["methods"]["A"]["model_weights_sha256"]:
        raise AutomatedOpticalV2Error("Pinned optical model weights differ from the plan.")
    output_dir.mkdir(parents=True, exist_ok=True)
    model_hashes = {}
    model_tiling = {}
    quality_counts = {}
    for scene_role in ("event", "dry"):
        bands, observable, scl = read_scene(rows, root, scene_role, grid_transform, grid_shape, inside)
        input_path = output_dir / f"{scene_role}_native_model_input.tif"
        output_path = output_dir / f"{scene_role}_native_model_output.tif"
        stack = model_input(bands, observable)
        model_tiling[scene_role] = effective_model_tiling(stack)
        write_raster(input_path, stack, grid_transform, nodata=-9999)
        command = [
            str(research_python), str(REPO_ROOT / "scripts/run_automated_optical_v2.py"),
            "--model-only", str(input_path), str(output_path),
            "--model-dir", str(model_dir), "--cache-dir", str(output_dir / "cache"),
        ]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise AutomatedOpticalV2Error(f"Native model failed for {scene_role}.") from exc
        # Structural validation only. Holdout water values remain uninspected until consumption.
        import rasterio

        with rasterio.open(output_path) as result:
            if result.count != 1 or result.shape != grid_shape or not result.transform.almost_equals(grid_transform):
                raise AutomatedOpticalV2Error("Native model output grid is invalid.")
        model_hashes[scene_role] = {
            "input_sha256": file_sha256(input_path), "output_sha256": file_sha256(output_path),
        }
        quality_counts[scene_role] = {
            "observable_aoi_cells": int(observable.sum()),
            "scl_class_counts_in_aoi": {str(code): int(np.sum((scl == code) & inside)) for code in range(12)},
        }
    payload = {
        "schema": "floodguard.automated_optical_v2_preparation.v1",
        "role": role, "event_id": plan[role]["event_id"],
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": PLAN_COMMIT,
        "feasibility_gate_sha256": gate["feasibility_gate_sha256"] if gate else None,
        "feasibility_gate_commit": FEASIBILITY_COMMIT if gate else None,
        "asset_manifest_sha256": file_sha256(manifest), "input_assets": rows,
        "source_timestamp": next(row["sensing_utc"] for row in rows if row["scene_role"] == "event"),
        "source_timestamp_kind": "Earth Search STAC item datetime (tile sensing time)",
        "dry_context_source_timestamp": next(
            row["sensing_utc"] for row in rows if row["scene_role"] == "dry"
        ),
        "v1_reference_receipt_source_timestamp": (
            v1_receipt["source_timestamp"] if role == "development" else None
        ),
        "processed_utc": utc_now(),
        "grid": {"width": grid_shape[1], "height": grid_shape[0], "aoi_cells": int(inside.sum()),
                 "transform": list(grid_transform)[:6]},
        "model_raster_sha256": model_hashes, "model_tiling": model_tiling,
        "model_runtime_versions": {
            "geoai_py": "0.41.1", "omniwatermask": "0.5.0", "omnicloudmask": "1.7.1",
        },
        "quality_counts": quality_counts,
        "confidence": "method outputs prepared but cross-review not yet scored",
        "human_reviewed": False, "accepted_observation": False,
        "official_warning": False, "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    return write_self_hashed(payload, prepare_receipt)


def consume_holdout_marker(
    path: Path, *, plan: Mapping[str, Any], gate: Mapping[str, Any],
    development_hash: str, preparation_hash: str,
) -> dict[str, Any]:
    """Create one exclusive local marker before a fresh event-level comparison."""
    path.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "schema": "floodguard.automated_optical_holdout_consumption.v2",
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": PLAN_COMMIT,
        "feasibility_gate_sha256": gate["feasibility_gate_sha256"],
        "feasibility_gate_commit": FEASIBILITY_COMMIT,
        "development_receipt_sha256": development_hash,
        "preparation_receipt_sha256": preparation_hash,
        "consumed_at_utc": utc_now(),
    }
    marker["marker_sha256"] = canonical_sha256(marker, omit="marker_sha256")
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(marker, stream, indent=2)
            stream.write("\n")
    except FileExistsError as exc:
        raise AutomatedOpticalV2Error("The automated optical v2 final holdout was already consumed.") from exc
    return marker


def _quicklook(labels: np.ndarray, path: Path) -> None:
    from PIL import Image

    palette = np.array([
        [202, 207, 198, 255], [33, 128, 215, 255], [22, 68, 140, 255],
        [242, 175, 55, 255], [95, 102, 112, 255],
    ], dtype=np.uint8)
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    for code in range(5):
        rgba[labels == code] = palette[code]
    image = Image.fromarray(rgba, mode="RGBA")
    image.thumbnail((800, 800), resample=Image.Resampling.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def score_episode(
    *, role: str, manifest: Path, external_root: Path, output_dir: Path,
    prepare_receipt: Path, result_path: Path, quicklook_path: Path,
    development_receipt: Path | None = None,
) -> dict[str, Any]:
    """Score development or consume and score the single fresh optical holdout."""
    plan = load_plan()
    gate = load_feasibility_gate(plan) if role == "final_holdout" else None
    if role == "final_holdout" and result_path.exists():
        raise AutomatedOpticalV2Error("The automated optical v2 holdout result already exists.")
    preparation = verify_receipt(prepare_receipt, "floodguard.automated_optical_v2_preparation.v1", plan)
    if preparation.get("role") != role or preparation.get("asset_manifest_sha256") != file_sha256(manifest):
        raise AutomatedOpticalV2Error("V2 preparation belongs to another role or input manifest.")
    rows = load_asset_manifest(manifest, plan, role)
    root = scene_root(external_root, role)
    verify_asset_files(rows, root)
    grid_transform, grid_shape, inside = reference_grid(plan, role, root / plan[role]["event_item_id"] / "blue.tif")
    for scene_role in ("event", "dry"):
        for kind in ("input", "output"):
            path = output_dir / f"{scene_role}_native_model_{kind}.tif"
            expected = preparation["model_raster_sha256"][scene_role][f"{kind}_sha256"]
            if file_sha256(path) != expected:
                raise AutomatedOpticalV2Error("Prepared v2 native model raster differs from its receipt.")
    marker = None
    if role == "final_holdout":
        if development_receipt is None:
            raise AutomatedOpticalV2Error("V2 holdout requires the completed development receipt.")
        development = verify_receipt(development_receipt, "floodguard.automated_optical_v2_result.v1", plan)
        if development.get("role") != "development":
            raise AutomatedOpticalV2Error("V2 development receipt has the wrong role.")
        marker_path = (external_root / "proposal_execution" / "automated_track" / "v2"
                       / "automated_optical_holdout_consumption.json")
        marker = consume_holdout_marker(
            marker_path, plan=plan, gate=gate, development_hash=development["receipt_sha256"],
            preparation_hash=preparation["receipt_sha256"],
        )
    scene_results = {}
    quality = {}
    method_hashes = {}
    for scene_role in ("event", "dry"):
        bands, observable, scl = read_scene(rows, root, scene_role, grid_transform, grid_shape, inside)
        if int(observable.sum()) != preparation["quality_counts"][scene_role]["observable_aoi_cells"]:
            raise AutomatedOpticalV2Error("V2 quality mask differs from preparation.")
        a = model_water(
            output_dir / f"{scene_role}_native_model_input.tif",
            output_dir / f"{scene_role}_native_model_output.tif",
            grid_shape, grid_transform,
        )
        b, valid = spectral_water_rule(bands)
        if np.any(observable & ~valid):
            raise AutomatedOpticalV2Error("V2 spectral rule validity differs from quality mask.")
        scene_results[scene_role] = (a, b, observable)
        quality[scene_role] = {"observable_aoi_cells": int(observable.sum()),
                               "scl_class_counts_in_aoi": {str(code): int(np.sum((scl == code) & inside)) for code in range(12)}}
        for method, water in (("a", a), ("b", b)):
            path = output_dir / f"{scene_role}_method_{method}_water.tif"
            write_raster(path, np.where(observable, water.astype(np.uint8), 255).astype(np.uint8), grid_transform, nodata=255)
            method_hashes[f"{scene_role}_{method}"] = file_sha256(path)
    event_a, event_b, event_observable = scene_results["event"]
    dry_a, dry_b, dry_observable = scene_results["dry"]
    labels = assign_label_codes(
        event_a, event_b, dry_a, dry_b, event_observable, dry_observable, inside,
    )
    label_path = output_dir / "automated_optical_reference_v2.tif"
    write_raster(label_path, labels, grid_transform, nodata=255)
    _quicklook(labels, quicklook_path)
    limits = plan["cross_review_limits"]
    agreement = compute_cross_review(
        event_a, event_b, event_observable,
        min_water_dice=limits["min_water_dice"],
        min_cohen_kappa=limits["min_cohen_kappa"],
    )
    coverage = float(event_observable.sum() / inside.sum())
    positive_feasibility = assess_positive_feasibility(event_a, event_b, event_observable, gate) if gate else None
    passes = bool(
        agreement["passes_limits"] and coverage >= limits["min_event_observable_fraction_of_aoi"]
        and (positive_feasibility is None or positive_feasibility["passes"])
    )
    payload = {
        "schema": "floodguard.automated_optical_v2_result.v1",
        "evidence_tier": "automated_optical_cross_review",
        "reference_kind": "automated_optical_reference",
        "role": role, "event_id": plan[role]["event_id"],
        "source_timestamp": preparation["source_timestamp"],
        "source_timestamp_kind": preparation["source_timestamp_kind"],
        "dry_context_source_timestamp": preparation["dry_context_source_timestamp"],
        "v1_reference_receipt_source_timestamp": preparation["v1_reference_receipt_source_timestamp"],
        "processed_utc": utc_now(),
        "preregistration_sha256": plan["preregistration_sha256"],
        "preregistration_commit": PLAN_COMMIT,
        "feasibility_gate_sha256": gate["feasibility_gate_sha256"] if gate else None,
        "feasibility_gate_commit": FEASIBILITY_COMMIT if gate else None,
        "preparation_receipt_sha256": preparation["receipt_sha256"],
        "input_manifest_sha256": file_sha256(manifest), "input_assets": rows,
        "grid": preparation["grid"], "quality": quality,
        "event_observable_fraction_of_aoi": coverage,
        "class_counts": count_aoi_classes(labels, inside),
        "ab_agreement": agreement,
        "positive_feasibility": positive_feasibility,
        "cross_review_limits": limits,
        "passes_all_limits": passes,
        "model_raster_sha256": preparation["model_raster_sha256"],
        "model_tiling": preparation["model_tiling"],
        "model_runtime_versions": preparation["model_runtime_versions"],
        "method_raster_sha256": method_hashes,
        "label_raster_sha256": file_sha256(label_path),
        "quicklook_sha256": file_sha256(quicklook_path),
        "holdout_consumption_marker_sha256": marker["marker_sha256"] if marker else None,
        "confidence": "limited: agreement of two automated optical methods, with no independent field truth",
        "limitations": [
            "This is agreement between automated optical maps, not flood-detection accuracy.",
            "The dry-context scene may not establish all permanent water; indeterminate cells remain uncertain.",
            "Sentinel-2 SCL and UNOSAT context are diagnostic only, not independent pixelwise truth.",
        ],
        "metric_interpretation": plan["metric_interpretation"],
        "human_reviewed": False, "accepted_observation": False,
        "official_warning": False, "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }
    if role == "final_holdout":
        payload["development_receipt_sha256"] = development["receipt_sha256"]
    return write_self_hashed(payload, result_path)
