"""Separate, non-operational automated optical reference for the Mae Sai study area.

This module never invokes the human reference, review, or release contracts.
Only Sentinel-2 optical bands enter its two water methods; SAR candidates are
handled later by the separate automated evaluation contract.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from floodguard.label_factory.agreement import compute_agreement

PREREG_PATH = Path(__file__).resolve().parents[2] / "docs" / "proposal_execution" / "automated_track" / "preregistration_v1.json"
PREREG_COMMIT = "77833df9d595429c1cf903c9a841e86aa8668b79"
RECEIPT_SCHEMA = "floodguard.automated_optical_reference.v1"
ASSET_FIELDS = (
    "scene_role", "item_id", "product_uri", "asset", "asset_url",
    "file_size_bytes", "sha256", "source_edition", "original_safe_sha256",
)
EXPECTED_ASSETS = {"blue", "green", "red", "nir", "nir08", "swir16", "swir22", "scl"}


class AutomatedReferenceError(ValueError):
    """Raised when optical inputs or the automated reference receipt are invalid."""


def _canonical_sha256(payload: Mapping[str, Any], excluded: str) -> str:
    value = {key: entry for key, entry in payload.items() if key != excluded}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_preregistration(path: Path = PREREG_PATH) -> dict[str, Any]:
    """Load and verify the committed automated pre-registration self-hash."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomatedReferenceError("Automated pre-registration is unavailable or invalid.") from exc
    if payload.get("schema") != "floodguard.automated_preregistration.v1":
        raise AutomatedReferenceError("Unexpected automated pre-registration schema.")
    if payload.get("preregistration_sha256") != _canonical_sha256(payload, "preregistration_sha256"):
        raise AutomatedReferenceError("Automated pre-registration self-hash mismatch.")
    return payload


def load_asset_manifest(path: Path) -> list[dict[str, Any]]:
    """Read all 16 exact optical COG receipts, rejecting gaps or duplicates."""
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            raw_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise AutomatedReferenceError("Earth Search asset manifest is unavailable.") from exc
    if len(raw_rows) != 16:
        raise AutomatedReferenceError("Earth Search asset manifest must contain 16 rows.")
    rows = []
    keys = set()
    for raw in raw_rows:
        try:
            row = {key: raw[key] for key in ASSET_FIELDS}
            row["file_size_bytes"] = int(row["file_size_bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AutomatedReferenceError("Earth Search asset manifest row is incomplete.") from exc
        key = (row["scene_role"], row["asset"])
        if key in keys or row["scene_role"] not in {"event", "dry"} or row["asset"] not in EXPECTED_ASSETS:
            raise AutomatedReferenceError("Earth Search asset manifest has duplicate or unexpected assets.")
        if row["file_size_bytes"] <= 0 or len(row["sha256"]) != 64:
            raise AutomatedReferenceError("Earth Search asset size or hash is invalid.")
        if row["source_edition"] != "element84_cog_of_l2a" or row["original_safe_sha256"] != "not_recorded":
            raise AutomatedReferenceError("Earth Search source edition differs from the pre-registration.")
        keys.add(key)
        rows.append(row)
    if keys != {(role, asset) for role in ("event", "dry") for asset in EXPECTED_ASSETS}:
        raise AutomatedReferenceError("Earth Search asset manifest lacks required assets.")
    return sorted(rows, key=lambda row: (row["scene_role"], row["asset"]))


def reflectance_from_dn(dn: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert Element84 L2A digital numbers using STAC scale and offset."""
    valid = np.asarray(dn) > 0
    reflectance = np.clip(np.asarray(dn, dtype=np.float32) * 0.0001 - 0.1, 0.0, 1.0)
    return reflectance, valid


def spectral_water_rule(bands: Mapping[str, np.ndarray], *, epsilon: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Apply the pre-registered MNDWI, AWEIsh, and NDVI conjunction."""
    needed = ("blue", "green", "red", "nir", "swir16", "swir22")
    if not all(name in bands for name in needed):
        raise AutomatedReferenceError("Spectral water rule is missing a required band.")
    values = {name: np.asarray(bands[name], dtype=np.float32) for name in needed}
    shape = values["blue"].shape
    if any(value.shape != shape for value in values.values()):
        raise AutomatedReferenceError("Spectral water bands do not share the reference grid.")
    blue, green, red = values["blue"], values["green"], values["red"]
    nir, swir16, swir22 = values["nir"], values["swir16"], values["swir22"]
    mndwi_denominator = green + swir16
    ndvi_denominator = nir + red
    valid = (
        np.isfinite(blue) & np.isfinite(green) & np.isfinite(red)
        & np.isfinite(nir) & np.isfinite(swir16) & np.isfinite(swir22)
        & (mndwi_denominator > epsilon) & (ndvi_denominator > epsilon)
    )
    mndwi = (green - swir16) / np.maximum(mndwi_denominator, epsilon)
    awei_sh = blue + 2.5 * green - 1.5 * (nir + swir16) - 0.25 * swir22
    ndvi = (nir - red) / np.maximum(ndvi_denominator, epsilon)
    water = (mndwi > 0.10) & (awei_sh > 0.0) & (ndvi < 0.20) & valid
    return water, valid


def scl_unobservable_mask(scl: np.ndarray, *, pixel_size_m: int = 10, buffer_m: int = 20) -> np.ndarray:
    """Buffer SCL 0/3/8/9/10 by Euclidean pixel-center distance."""
    values = np.asarray(scl)
    if values.ndim != 2 or pixel_size_m <= 0 or buffer_m < 0:
        raise AutomatedReferenceError("SCL buffer needs a 2D grid and valid distances.")
    seed = np.isin(values, (0, 3, 8, 9, 10))
    result = np.zeros_like(seed)
    radius = math.ceil(buffer_m / pixel_size_m)
    height, width = seed.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if (dx * pixel_size_m) ** 2 + (dy * pixel_size_m) ** 2 > buffer_m * buffer_m:
                continue
            source_y = slice(max(0, -dy), min(height, height - dy))
            source_x = slice(max(0, -dx), min(width, width - dx))
            target_y = slice(max(0, dy), min(height, height + dy))
            target_x = slice(max(0, dx), min(width, width + dx))
            result[target_y, target_x] |= seed[source_y, source_x]
    return result


def assign_label_codes(
    event_a: np.ndarray,
    event_b: np.ndarray,
    dry_a: np.ndarray,
    dry_b: np.ndarray,
    event_observable: np.ndarray,
    dry_observable: np.ndarray,
    inside_aoi: np.ndarray,
) -> np.ndarray:
    """Assign flood_label_v1 codes from two optical methods and dry context."""
    arrays = [np.asarray(value, dtype=bool) for value in (
        event_a, event_b, dry_a, dry_b, event_observable, dry_observable, inside_aoi,
    )]
    if any(array.shape != arrays[0].shape for array in arrays) or arrays[0].ndim != 2:
        raise AutomatedReferenceError("Label inputs must share a two-dimensional grid.")
    ea, eb, da, db, eo, do, inside = arrays
    labels = np.full(ea.shape, 255, dtype=np.uint8)
    visible = inside & eo
    labels[inside & ~eo] = 4
    labels[visible & (ea != eb)] = 3
    labels[visible & ~ea & ~eb] = 0
    event_water = visible & ea & eb
    labels[event_water & (~do | (da != db))] = 3
    labels[event_water & do & da & db] = 2
    labels[event_water & do & ~da & ~db] = 1
    return labels


def compute_cross_review(
    event_a: np.ndarray,
    event_b: np.ndarray,
    observable_aoi: np.ndarray,
    *,
    min_water_dice: float,
    min_cohen_kappa: float,
) -> dict[str, Any]:
    """Measure optical A/B agreement using the existing label-factory metric."""
    mask = np.asarray(observable_aoi, dtype=bool)
    a = np.asarray(event_a, dtype=bool)
    b = np.asarray(event_b, dtype=bool)
    if a.shape != b.shape or a.shape != mask.shape or not np.any(mask):
        raise AutomatedReferenceError("No comparable optical A/B cells exist.")
    report = compute_agreement(a[mask].astype(np.uint8).tolist(), b[mask].astype(np.uint8).tolist(), labels=(0, 1))
    water_dice = report.class_metrics(1).dice_f1
    kappa = report.cohen_kappa if report.cohen_kappa is not None and math.isfinite(report.cohen_kappa) else None
    return {
        "evidence_tier": "automated_cross_review",
        "water_dice": water_dice,
        "cohen_kappa": kappa,
        "valid_pair_count": report.valid_pair_count,
        "ignored_pair_count": report.ignored_pair_count,
        "water_count_a": int(a[mask].sum()),
        "water_count_b": int(b[mask].sum()),
        "passes_limits": (
            water_dice is not None and kappa is not None
            and water_dice >= min_water_dice and kappa >= min_cohen_kappa
        ),
        "human_reviewed": False,
    }


def count_aoi_classes(labels: np.ndarray, inside_aoi: np.ndarray) -> dict[str, int]:
    """Count codes 0-4 inside the declared AOI; exclude outside code 255."""
    values = np.asarray(labels)[np.asarray(inside_aoi, dtype=bool)]
    if np.any(~np.isin(values, (0, 1, 2, 3, 4))):
        raise AutomatedReferenceError("AOI label raster contains an invalid code.")
    return {str(code): int(np.sum(values == code)) for code in range(5)}


def validate_automated_reference_receipt(
    receipt: Mapping[str, Any] | Path,
    *,
    manifest: Path,
    raster_path: Path | None = None,
) -> dict[str, Any]:
    """Verify self-hash, exact optical inputs, preregistration, and optional raster."""
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8")) if isinstance(receipt, Path) else dict(receipt)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AutomatedReferenceError("Automated reference receipt is unavailable or invalid.") from exc
    if payload.get("schema") != RECEIPT_SCHEMA or payload.get("evidence_tier") != "automated_optical_reference":
        raise AutomatedReferenceError("Unexpected automated reference receipt schema or tier.")
    if payload.get("receipt_sha256") != _canonical_sha256(payload, "receipt_sha256"):
        raise AutomatedReferenceError("Automated reference receipt self-hash mismatch.")
    prereg = load_preregistration()
    if payload.get("preregistration_sha256") != prereg["preregistration_sha256"]:
        raise AutomatedReferenceError("Automated reference pre-registration hash mismatch.")
    if payload.get("preregistration_commit") != PREREG_COMMIT:
        raise AutomatedReferenceError("Automated reference pre-registration commit mismatch.")
    try:
        manifest_sha256 = _file_sha256(manifest)
    except OSError as exc:
        raise AutomatedReferenceError("Earth Search asset manifest is unavailable.") from exc
    rows = load_asset_manifest(manifest)
    if payload.get("input_manifest_sha256") != manifest_sha256 or payload.get("input_assets") != rows:
        raise AutomatedReferenceError("Automated reference optical input manifest mismatch.")
    for role, item_key, product_key in (
        ("event", "event_item_id", "event_product_uri"),
        ("dry", "dry_context_item_id", "dry_context_product_uri"),
    ):
        if any(
            row["item_id"] != prereg["source"][item_key]
            or row["product_uri"] != prereg["source"][product_key]
            for row in rows if row["scene_role"] == role
        ):
            raise AutomatedReferenceError("Automated reference input product differs from pre-registration.")
    for field, expected in (
        ("human_reviewed", False), ("official_warning", False),
        ("can_feed_decision_layer", False), ("operational_status", "non_operational"),
    ):
        value = payload.get(field)
        mismatch = value is not expected if isinstance(expected, bool) else value != expected
        if mismatch:
            raise AutomatedReferenceError(f"Automated reference safety field {field} differs.")
    review = payload.get("ab_agreement")
    if not isinstance(review, dict) or review.get("evidence_tier") != "automated_cross_review" or review.get("human_reviewed") is not False:
        raise AutomatedReferenceError("Automated cross-review evidence is missing or invalid.")
    dice = review.get("water_dice")
    kappa = review.get("cohen_kappa")
    if dice is not None and (not isinstance(dice, (int, float)) or isinstance(dice, bool) or not 0 <= dice <= 1):
        raise AutomatedReferenceError("Automated cross-review Dice is invalid.")
    if kappa is not None and (not isinstance(kappa, (int, float)) or isinstance(kappa, bool) or not -1 <= kappa <= 1):
        raise AutomatedReferenceError("Automated cross-review kappa is invalid.")
    limits = prereg["cross_review_limits"]
    passes = (
        dice is not None and kappa is not None
        and dice >= limits["min_water_dice"] and kappa >= limits["min_cohen_kappa"]
    )
    if review.get("passes_limits") is not passes:
        raise AutomatedReferenceError("Automated cross-review pass flag contradicts pre-registered limits.")
    counts = payload.get("class_counts")
    if not isinstance(counts, dict) or set(counts) != {str(code) for code in range(5)}:
        raise AutomatedReferenceError("Automated reference class counts are missing.")
    if any(not isinstance(count, int) or count < 0 for count in counts.values()):
        raise AutomatedReferenceError("Automated reference class counts are invalid.")
    if sum(counts.values()) != payload.get("aoi_cell_count"):
        raise AutomatedReferenceError("Automated reference AOI class counts do not reconcile.")
    if raster_path is not None:
        try:
            raster_sha256 = _file_sha256(raster_path)
        except OSError as exc:
            raise AutomatedReferenceError("Automated label raster is unavailable.") from exc
        if payload.get("label_raster_sha256") != raster_sha256:
            raise AutomatedReferenceError("Automated label raster SHA-256 mismatch.")
    return payload


def write_receipt(payload: dict[str, Any], path: Path) -> dict[str, Any]:
    """Write a self-hashed automated reference receipt and verify it in memory."""
    completed = dict(payload)
    completed["receipt_sha256"] = _canonical_sha256(completed, "receipt_sha256")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(completed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return completed


def utc_now() -> str:
    """Return a UTC source-processing timestamp for the receipt."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reference_grid(aoi_path: Path, event_blue_path: Path) -> tuple[Any, tuple[int, int], np.ndarray]:
    import rasterio
    from pyproj import Transformer
    from rasterio.features import geometry_mask
    from shapely.geometry import shape
    from shapely.ops import transform as transform_geometry
    from shapely.ops import unary_union

    source = json.loads(aoi_path.read_text(encoding="utf-8"))
    features = source["features"] if source.get("type") == "FeatureCollection" else [source]
    geometry_wgs84 = unary_union([shape(feature["geometry"]) for feature in features])
    geometry = transform_geometry(
        Transformer.from_crs("EPSG:4326", "EPSG:32647", always_xy=True).transform,
        geometry_wgs84,
    )
    with rasterio.open(event_blue_path) as dataset:
        if dataset.crs.to_string() != "EPSG:32647" or dataset.res != (10.0, 10.0):
            raise AutomatedReferenceError("Event blue COG does not define the pre-registered 10 m grid.")
        origin_x, origin_y = dataset.transform.c, dataset.transform.f
        min_x, min_y, max_x, max_y = geometry.bounds
        col_start = math.floor((min_x - origin_x) / 10)
        col_end = math.ceil((max_x - origin_x) / 10)
        row_start = math.floor((origin_y - max_y) / 10)
        row_end = math.ceil((origin_y - min_y) / 10)
        if not (0 <= col_start < col_end <= dataset.width and 0 <= row_start < row_end <= dataset.height):
            raise AutomatedReferenceError("Mae Sai AOI extends beyond the exact T47QNC event tile.")
        grid_transform = dataset.transform * rasterio.Affine.translation(col_start, row_start)
    grid_shape = (row_end - row_start, col_end - col_start)
    inside_aoi = geometry_mask(
        [geometry], out_shape=grid_shape, transform=grid_transform,
        invert=True, all_touched=False,
    )
    if not np.any(inside_aoi):
        raise AutomatedReferenceError("Mae Sai AOI contains no reference grid cells.")
    return grid_transform, grid_shape, inside_aoi


def _read_scene(
    scene_dir: Path,
    *,
    grid_transform: Any,
    grid_shape: tuple[int, int],
    inside_aoi: np.ndarray,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    reflectance: dict[str, np.ndarray] = {}
    valid_bands: list[np.ndarray] = []
    for asset in ("blue", "green", "red", "nir", "nir08", "swir16", "swir22"):
        path = scene_dir / f"{asset}.tif"
        digital_numbers = np.zeros(grid_shape, dtype=np.float32)
        with rasterio.open(path) as source:
            if source.crs.to_string() != "EPSG:32647":
                raise AutomatedReferenceError(f"Optical asset {path.name} has an unexpected CRS.")
            reproject(
                source=rasterio.band(source, 1), destination=digital_numbers,
                src_transform=source.transform, src_crs=source.crs, src_nodata=0,
                dst_transform=grid_transform, dst_crs="EPSG:32647", dst_nodata=0,
                resampling=Resampling.nearest if asset in {"blue", "green", "red", "nir"} else Resampling.bilinear,
            )
        reflectance[asset], valid = reflectance_from_dn(digital_numbers)
        valid_bands.append(valid)
    scl = np.zeros(grid_shape, dtype=np.uint8)
    with rasterio.open(scene_dir / "scl.tif") as source:
        reproject(
            source=rasterio.band(source, 1), destination=scl,
            src_transform=source.transform, src_crs=source.crs, src_nodata=0,
            dst_transform=grid_transform, dst_crs="EPSG:32647", dst_nodata=0,
            resampling=Resampling.nearest,
        )
    spectral_water, spectral_valid = spectral_water_rule(reflectance)
    observable = (
        inside_aoi & ~scl_unobservable_mask(scl) & np.logical_and.reduce(valid_bands)
        & spectral_valid
    )
    return reflectance, spectral_water, observable, scl


def _write_raster(path: Path, values: np.ndarray, transform: Any, *, nodata: float) -> None:
    import rasterio

    path.parent.mkdir(parents=True, exist_ok=True)
    if values.ndim == 2:
        data = values[np.newaxis, :, :]
    elif values.ndim == 3:
        data = values
    else:
        raise AutomatedReferenceError("Raster output must have two or three dimensions.")
    with rasterio.open(
        path, "w", driver="GTiff", width=data.shape[2], height=data.shape[1],
        count=data.shape[0], dtype=data.dtype, crs="EPSG:32647", transform=transform,
        nodata=nodata, compress="deflate", tiled=True, blockxsize=256, blockysize=256,
    ) as destination:
        destination.write(data)


def _model_input(
    reflectance: Mapping[str, np.ndarray], observable: np.ndarray, transform: Any,
) -> tuple[np.ndarray, Any]:
    import rasterio

    stack = np.stack([reflectance[name] for name in ("blue", "green", "red", "nir", "swir16", "swir22")])
    stack[:, ~observable] = -9999.0
    _, height, width = stack.shape
    scale = min(1.0, 512 / max(height, width))
    small_height = max(1, round(height * scale))
    small_width = max(1, round(width * scale))
    row_indices = np.linspace(0, height - 1, small_height).astype(int)
    column_indices = np.linspace(0, width - 1, small_width).astype(int)
    small = stack[:, row_indices[:, None], column_indices[None, :]].astype(np.float32)
    small_transform = transform * rasterio.Affine.scale(width / small_width, height / small_height)
    return small, small_transform


def run_omniwatermask_model(input_path: Path, output_path: Path, *, model_dir: Path, cache_dir: Path) -> None:
    """Run the pinned optical model in the separate research environment."""
    import geoai
    import omniwatermask

    if geoai.__version__ != "0.41.1" or omniwatermask.__version__ != "0.5.0":
        raise AutomatedReferenceError("Research environment lacks the pre-registered model versions.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    geoai.segment_water(
        str(input_path), band_order=[3, 2, 1, 4], output_raster=str(output_path),
        batch_size=1, device="cpu", dtype="float32", no_data_value=-9999,
        patch_size=512, overlap_size=0, use_osm_water=False,
        use_osm_building=False, use_osm_roads=False, use_cache=False,
        cache_dir=str(cache_dir), model_dir=str(model_dir),
        version="OmniWaterMask_0.5.0", model_download_source="hugging_face",
        verbose=True,
    )
    if not output_path.is_file():
        raise AutomatedReferenceError("OmniWaterMask produced no optical mask.")


def _model_water_on_grid(
    model_output: Path, model_input: Path, grid_shape: tuple[int, int], grid_transform: Any,
) -> np.ndarray:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    full = np.zeros(grid_shape, dtype=np.uint8)
    with rasterio.open(model_input) as expected, rasterio.open(model_output) as source:
        if source.count != 1 or source.crs.to_string() != "EPSG:32647":
            raise AutomatedReferenceError("OmniWaterMask output has unexpected bands or CRS.")
        if source.shape != expected.shape or not source.transform.almost_equals(expected.transform):
            raise AutomatedReferenceError("OmniWaterMask output is not aligned to its pre-registered input grid.")
        reproject(
            source=rasterio.band(source, 1), destination=full,
            src_transform=source.transform, src_crs=source.crs,
            dst_transform=grid_transform, dst_crs="EPSG:32647", dst_nodata=0,
            resampling=Resampling.nearest,
        )
    return full > 0


def _quicklook(labels: np.ndarray, path: Path) -> None:
    from PIL import Image

    palette = np.array([
        [202, 207, 198, 255],  # dry
        [33, 128, 215, 255],  # temporary flood
        [22, 68, 140, 255],  # permanent water
        [242, 175, 55, 255],  # uncertain
        [95, 102, 112, 255],  # unobservable
    ], dtype=np.uint8)
    rgba = np.zeros((*labels.shape, 4), dtype=np.uint8)
    for code in range(5):
        rgba[labels == code] = palette[code]
    image = Image.fromarray(rgba, mode="RGBA")
    image.thumbnail((800, 800), resample=Image.Resampling.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def build_automated_optical_reference(
    *,
    manifest: Path,
    external_data_root: Path,
    output_dir: Path,
    receipt_path: Path,
    quicklook_path: Path,
    research_python: Path,
) -> dict[str, Any]:
    """Build the two-method optical label and its self-hashed evidence receipt."""
    prereg = load_preregistration()
    rows = load_asset_manifest(manifest)
    expected = {
        "event": (prereg["source"]["event_item_id"], prereg["source"]["event_product_uri"]),
        "dry": (prereg["source"]["dry_context_item_id"], prereg["source"]["dry_context_product_uri"]),
    }
    scene_dirs = {}
    for role, (item_id, product_uri) in expected.items():
        scene_dirs[role] = external_data_root / "earth_search" / "mae_sai_2024" / item_id
        for row in (entry for entry in rows if entry["scene_role"] == role):
            if row["item_id"] != item_id or row["product_uri"] != product_uri:
                raise AutomatedReferenceError("Optical asset manifest product differs from pre-registration.")
            asset_path = scene_dirs[role] / f"{row['asset']}.tif"
            if not asset_path.is_file() or asset_path.stat().st_size != row["file_size_bytes"]:
                raise AutomatedReferenceError(f"Optical asset is missing or incomplete: {role}/{row['asset']}.")
            if _file_sha256(asset_path) != row["sha256"]:
                raise AutomatedReferenceError(f"Optical asset SHA-256 mismatch: {role}/{row['asset']}.")
    output_dir.mkdir(parents=True, exist_ok=True)
    aoi_path = Path(__file__).resolve().parents[2] / prereg["grid"]["aoi_path"]
    grid_transform, grid_shape, inside_aoi = _reference_grid(aoi_path, scene_dirs["event"] / "blue.tif")
    scene_results: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    method_raster_sha256: dict[str, str] = {}
    for role in ("event", "dry"):
        reflectance, spectral_water, observable, _ = _read_scene(
            scene_dirs[role], grid_transform=grid_transform, grid_shape=grid_shape, inside_aoi=inside_aoi,
        )
        model_input, model_transform = _model_input(reflectance, observable, grid_transform)
        model_input_path = output_dir / f"{role}_omniwatermask_input.tif"
        model_output_path = output_dir / f"{role}_omniwatermask_output.tif"
        _write_raster(model_input_path, model_input, model_transform, nodata=-9999)
        command = [
            str(research_python), str(Path(__file__).resolve().parents[2] / "scripts" / "build_automated_optical_reference.py"),
            "--model-only", str(model_input_path), str(model_output_path),
            "--model-dir", str(output_dir / "model"), "--cache-dir", str(output_dir / "cache"),
        ]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise AutomatedReferenceError(f"Pinned optical model failed for {role}.") from exc
        model_water = _model_water_on_grid(model_output_path, model_input_path, grid_shape, grid_transform)
        scene_results[role] = model_water, spectral_water, observable
        for method, water in (("a", model_water), ("b", spectral_water)):
            mask_path = output_dir / f"{role}_method_{method}_water.tif"
            values = np.where(observable, water.astype(np.uint8), 255).astype(np.uint8)
            _write_raster(mask_path, values, grid_transform, nodata=255)
            method_raster_sha256[f"{role}_{method}"] = _file_sha256(mask_path)
    event_a, event_b, event_observable = scene_results["event"]
    dry_a, dry_b, dry_observable = scene_results["dry"]
    labels = assign_label_codes(
        event_a, event_b, dry_a, dry_b, event_observable, dry_observable, inside_aoi,
    )
    label_path = output_dir / "automated_optical_reference_v1.tif"
    _write_raster(label_path, labels, grid_transform, nodata=255)
    _quicklook(labels, quicklook_path)
    agreement = compute_cross_review(
        event_a, event_b, event_observable & inside_aoi,
        min_water_dice=prereg["cross_review_limits"]["min_water_dice"],
        min_cohen_kappa=prereg["cross_review_limits"]["min_cohen_kappa"],
    )
    model_files = list((output_dir / "model").glob("*.pth"))
    if len(model_files) != 1:
        raise AutomatedReferenceError("Expected one pinned OmniWaterMask model weight file.")
    model_weight = model_files[0]
    counts = count_aoi_classes(labels, inside_aoi)
    limitations = [
        "The 15 September optical scene precedes the SAR post-acquisition by 19 h 31 min; flood evolution or recession may change the extent.",
        "Turbid floodwater is often missed by spectral rules. The repository Component ★ finding found MNDWI > 0 flagged 8.7× the reference area on a dry-season scene.",
        "OmniWaterMask is pretrained and its published training lineage includes S1S2-Water, but this run ingests only Sentinel-2 optical bands; neither method establishes independent human flood truth.",
        "OmniWaterMask inference uses a maximum 512-pixel input dimension and nearest-neighbor upsampling to the 10 m grid, so its effective detail is coarser.",
        "The pinned model package may internally reduce the requested 512-pixel patch size when large masked areas are present; both scene runs emitted this adjustment warning.",
        "Cloud, shadow, invalid reflectance, and ambiguous dry context are excluded or marked uncertain; only codes 0 and 1 are eligible for later evaluation.",
    ]
    if not agreement["passes_limits"]:
        limitations.append("The two optical methods failed at least one pre-registered cross-review agreement limit; this result was retained without threshold tuning.")
    payload = {
        "schema": RECEIPT_SCHEMA,
        "evidence_tier": "automated_optical_reference",
        "reference_kind": "automated_optical_reference",
        "event_id": prereg["event_id"],
        "study_area_id": prereg["study_area_id"],
        "source_timestamp": prereg["source"]["event_sensing_utc"],
        "processed_utc": utc_now(),
        "confidence": "limited: two automated optical methods with cloud, turbidity, date-gap, and model-resolution uncertainty",
        "assumptions": [
            "Element84 COG reflectance follows the STAC scale 0.0001 and offset -0.1, clipped to unit reflectance for DN > 0.",
            "The 5 September scene is dry context for permanent water, not event-time flood truth.",
            "All model vector and OSM inputs are disabled; the pinned model still has its published training lineage.",
        ],
        "preregistration_path": "docs/proposal_execution/automated_track/preregistration_v1.json",
        "preregistration_sha256": prereg["preregistration_sha256"],
        "preregistration_commit": PREREG_COMMIT,
        "input_manifest_path": "outputs/earth_search_mae_sai_sentinel2_reference_assets.csv",
        "input_manifest_sha256": _file_sha256(manifest),
        "input_assets": rows,
        "grid": {
            "crs": "EPSG:32647", "pixel_size_m": 10,
            "transform": [float(grid_transform.a), float(grid_transform.b), float(grid_transform.c),
                          float(grid_transform.d), float(grid_transform.e), float(grid_transform.f)],
            "width": grid_shape[1], "height": grid_shape[0],
            "aoi_sha256": _file_sha256(aoi_path),
        },
        "label_raster_path_hint": "<external_data_workspace>/proposal_execution/automated_track/automated_optical_reference_v1.tif",
        "label_raster_sha256": _file_sha256(label_path),
        "method_raster_sha256": method_raster_sha256,
        "quicklook_path": "outputs/automated_optical_reference_v1.png",
        "quicklook_sha256": _file_sha256(quicklook_path),
        "class_counts": counts,
        "aoi_cell_count": int(inside_aoi.sum()),
        "ab_agreement": agreement,
        "method_versions": {
            "A": {"id": "omniwatermask_optical_v1", "geoai_py": "0.41.1", "omniwatermask": "0.5.0",
                  "model_weights_file": model_weight.name, "model_weights_sha256": _file_sha256(model_weight),
                  "model_weights_license": "MIT", "vector_inputs": "disabled", "max_input_dimension_pixels": 512,
                  "requested_patch_size_pixels": 512, "internal_patch_size_adaptation": "observed_on_both_scenes"},
            "B": {"id": "fixed_multi_index_spectral_v1", "mndwi_gt": 0.10,
                  "awei_sh_gt": 0.0, "ndvi_lt": 0.20},
        },
        "human_reviewed": False,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "accepted_observation": False,
        "limitations": limitations,
    }
    receipt = write_receipt(payload, receipt_path)
    return validate_automated_reference_receipt(receipt, manifest=manifest, raster_path=label_path)
