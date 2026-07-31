"""Feature/mask preparation and guarded GeoAI tile export."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import rasterio
from rasterio.enums import Resampling

from .contract import GeoAIRunContract, SpatialPartitionContract
from .preprocess import validate_transform_sidecar
from .validate import (
    RasterGrid,
    read_grid,
    validate_aligned_feature_and_mask,
    validate_grid_matches_contract,
)


@dataclass(frozen=True, slots=True)
class TileMembership:
    """Declared training pair paths; spatial membership is derived from bounds."""

    image_path: str
    label_path: str


@dataclass(frozen=True, slots=True)
class PreparedTileRow:
    """One immutable image/label pair in a prepared training manifest."""

    image_path: str
    label_path: str
    spatial_group_id: str
    image_sha256: str
    label_sha256: str


@dataclass(frozen=True, slots=True)
class TileExportReceipt:
    """Safe post-export partitioning and prepared-manifest evidence."""

    grid: RasterGrid
    prepared_manifest_relative_path: str
    prepared_manifest_sha256: str
    training_tile_count: int
    holdout_tile_count: int
    rejected_boundary_tile_count: int


def require_within_workspace(path: Path, workspace: Path) -> Path:
    target = path.resolve()
    root = workspace.resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path escapes the declared external workspace.")
    return target


def require_file_sha256(path: Path, expected_sha256: str, label: str) -> str:
    """Recompute one consumed file receipt immediately before use."""

    receipt = file_sha256(path)
    if receipt != expected_sha256:
        raise ValueError(f"{label} checksum does not match the run contract.")
    return receipt


def file_sha256(path: Path) -> str:
    """Return a streaming SHA-256 receipt for a local file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_prepared_inputs(
    contract: GeoAIRunContract,
    feature_path: Path,
    mask_path: Path,
    sidecar_path: Path,
) -> RasterGrid:
    """Bind prepared feature/mask bytes and grids to the immutable run contract."""

    contract.validate()
    feature = require_within_workspace(feature_path, contract.external_output_workspace)
    mask = require_within_workspace(mask_path, contract.external_output_workspace)
    sidecar = require_within_workspace(
        sidecar_path,
        contract.external_output_workspace,
    )
    validate_transform_sidecar(sidecar, contract.preprocessing)
    require_file_sha256(
        feature,
        contract.encoded_feature_sha256,
        "Encoded feature",
    )
    require_file_sha256(mask, contract.reference_mask_sha256, "Reference mask")
    grid = validate_aligned_feature_and_mask(feature, mask)
    validate_grid_matches_contract(grid, contract)
    return grid


def write_prepared_tile_manifest(
    contract: GeoAIRunContract,
    images_dir: Path,
    labels_dir: Path,
    memberships: Iterable[TileMembership],
    output_path: Path,
) -> str:
    """Write canonical, exact-coverage tile membership evidence and return its hash."""

    contract.validate()
    images, labels = _training_directories(contract, images_dir, labels_dir)
    output = require_within_workspace(output_path, contract.external_output_workspace)
    if output in (images, labels) or images in output.parents or labels in output.parents:
        raise ValueError("Prepared tile manifest must be outside image and label directories.")
    declared = tuple(memberships)
    rows = _materialize_tile_rows(contract, images, labels, declared)
    payload = {
        "schema_version": "1.0",
        "run_id": contract.run_id,
        "encoded_feature_sha256": contract.encoded_feature_sha256,
        "reference_mask_sha256": contract.reference_mask_sha256,
        "preprocessing_sidecar_sha256": contract.preprocessing.sidecar_sha256,
        "tiles": [asdict(row) for row in rows],
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    receipt = hashlib.sha256(encoded).hexdigest()
    if (
        contract.prepared_tile_manifest_sha256 is not None
        and contract.prepared_tile_manifest_sha256 != receipt
    ):
        raise ValueError("Prepared tile manifest does not match its contract receipt.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(output)
    return receipt


def validate_prepared_tile_manifest(
    contract: GeoAIRunContract,
    images_dir: Path,
    labels_dir: Path,
    manifest_path: Path,
) -> tuple[PreparedTileRow, ...]:
    """Verify manifest bytes, exact directory coverage, membership, and tile bytes."""

    contract.validate()
    if contract.prepared_tile_manifest_sha256 is None:
        raise ValueError("Training requires a prepared tile manifest SHA-256 receipt.")
    images, labels = _training_directories(contract, images_dir, labels_dir)
    manifest = require_within_workspace(
        manifest_path,
        contract.external_output_workspace,
    )
    require_file_sha256(
        manifest,
        contract.prepared_tile_manifest_sha256,
        "Prepared tile manifest",
    )
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read prepared tile manifest: {exc}") from exc
    expected_keys = {
        "schema_version",
        "run_id",
        "encoded_feature_sha256",
        "reference_mask_sha256",
        "preprocessing_sidecar_sha256",
        "tiles",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise ValueError("Prepared tile manifest fields are invalid.")
    expected_header = {
        "schema_version": "1.0",
        "run_id": contract.run_id,
        "encoded_feature_sha256": contract.encoded_feature_sha256,
        "reference_mask_sha256": contract.reference_mask_sha256,
        "preprocessing_sidecar_sha256": contract.preprocessing.sidecar_sha256,
    }
    if any(payload[name] != value for name, value in expected_header.items()):
        raise ValueError("Prepared tile manifest provenance does not match the run contract.")
    raw_tiles = payload["tiles"]
    if not isinstance(raw_tiles, list):
        raise ValueError("Prepared tile manifest tiles must be an array.")
    try:
        rows = tuple(PreparedTileRow(**raw) for raw in raw_tiles)
    except TypeError as exc:
        raise ValueError(f"Prepared tile manifest row is invalid: {exc}") from exc
    _validate_materialized_tile_rows(contract, images, labels, rows)
    return rows


def _training_directories(
    contract: GeoAIRunContract,
    images_dir: Path,
    labels_dir: Path,
) -> tuple[Path, Path]:
    images = require_within_workspace(images_dir, contract.external_output_workspace)
    labels = require_within_workspace(labels_dir, contract.external_output_workspace)
    if not images.is_dir() or not labels.is_dir():
        raise FileNotFoundError("Prepared training image and label directories are required.")
    if images == labels:
        raise ValueError("Training image and label directories must be distinct.")
    return images, labels


def _materialize_tile_rows(
    contract: GeoAIRunContract,
    images_dir: Path,
    labels_dir: Path,
    memberships: tuple[TileMembership, ...],
) -> tuple[PreparedTileRow, ...]:
    if not memberships or any(not isinstance(row, TileMembership) for row in memberships):
        raise ValueError("At least one typed tile membership row is required.")
    rows = tuple(
        PreparedTileRow(
            image_path=row.image_path,
            label_path=row.label_path,
            spatial_group_id=_derive_tile_partition(
                contract,
                _resolve_relative_file(images_dir, row.image_path),
                _resolve_relative_file(labels_dir, row.label_path),
            ).spatial_group_id,
            image_sha256=file_sha256(_resolve_relative_file(images_dir, row.image_path)),
            label_sha256=file_sha256(_resolve_relative_file(labels_dir, row.label_path)),
        )
        for row in memberships
    )
    _validate_materialized_tile_rows(contract, images_dir, labels_dir, rows)
    return rows


def _validate_materialized_tile_rows(
    contract: GeoAIRunContract,
    images_dir: Path,
    labels_dir: Path,
    rows: tuple[PreparedTileRow, ...],
) -> None:
    if not rows:
        raise ValueError("Prepared tile manifest must contain at least one tile pair.")
    image_paths: list[str] = []
    label_paths: list[str] = []
    for row in rows:
        image = _resolve_relative_file(images_dir, row.image_path)
        label = _resolve_relative_file(labels_dir, row.label_path)
        partition = _derive_tile_partition(contract, image, label)
        if partition.spatial_group_id != row.spatial_group_id:
            raise ValueError("Prepared tile spatial_group_id does not match geospatial bounds.")
        if partition.split == "holdout":
            raise ValueError(
                f"Spatial holdout group cannot enter training: {partition.spatial_group_id}"
            )
        require_file_sha256(image, row.image_sha256, "Prepared image tile")
        require_file_sha256(label, row.label_sha256, "Prepared label tile")
        image_paths.append(row.image_path)
        label_paths.append(row.label_path)
    if len(set(image_paths)) != len(image_paths) or len(set(label_paths)) != len(label_paths):
        raise ValueError("Prepared tile manifest contains duplicate image or label paths.")
    actual_images = _relative_file_set(images_dir)
    actual_labels = _relative_file_set(labels_dir)
    if actual_images != set(image_paths) or actual_labels != set(label_paths):
        raise ValueError("Prepared tile manifest does not exactly cover the tile directories.")


def _resolve_relative_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("Tile paths must be non-empty relative POSIX paths.")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != relative:
        raise ValueError("Tile paths must be normalized relative POSIX paths.")
    path = (root / Path(*pure.parts)).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError(f"Declared tile file is missing or escapes its directory: {relative}")
    return path


def _relative_file_set(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def _derive_tile_partition(
    contract: GeoAIRunContract,
    image_path: Path,
    label_path: Path,
    *,
    allow_unassigned: bool = False,
) -> SpatialPartitionContract | None:
    image = read_grid(image_path)
    label = read_grid(label_path)
    for name in ("crs", "transform", "width", "height", "bounds"):
        if getattr(image, name) != getattr(label, name):
            raise ValueError(f"Prepared image/label tile {name} differs.")
    if image.crs.upper() != contract.target_crs.upper():
        raise ValueError("Prepared tile CRS does not match the run contract.")
    if not 6 <= image.count <= 8 or set(image.dtypes) != {"uint8"}:
        raise ValueError("Prepared image tile must contain 6-8 uint8 bands.")
    if label.count != 1 or label.dtypes != ("uint8",) or label.nodata != 255:
        raise ValueError("Prepared label tile must contain one uint8 band with nodata=255.")
    with rasterio.open(label_path) as source:
        label_classes = set(np.unique(source.read(1)).tolist())
    if not label_classes.issubset({0, 1, 255}) or not label_classes.intersection({0, 1}):
        raise ValueError(
            "Prepared label tile values must stay in {0,1,255} and include a valid class."
        )
    matches = [
        partition
        for partition in contract.spatial_partitions
        if _bounds_contain(partition.bounds, image.bounds)
    ]
    if len(matches) != 1:
        if allow_unassigned:
            return None
        raise ValueError("Prepared tile bounds cross or fall outside committed spatial partitions.")
    return matches[0]


def _bounds_contain(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
) -> bool:
    tolerance = 1e-7
    return (
        outer[0] - tolerance <= inner[0]
        and outer[1] - tolerance <= inner[1]
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def export_training_tiles(
    contract: GeoAIRunContract,
    feature_path: Path,
    mask_path: Path,
    sidecar_path: Path,
    output_dir: Path,
    *,
    exporter: Callable[..., Any] | None = None,
) -> TileExportReceipt:
    """Validate alignment before invoking `geoai.utils.training.export_geotiff_tiles`."""

    contract.validate()
    if not contract.processing_allowed:
        raise PermissionError("Run contract blocks processing.")
    if contract.prepared_tile_manifest_sha256 is not None:
        raise ValueError("Tile export requires an unprepared contract without a manifest receipt.")
    feature = require_within_workspace(feature_path, contract.external_output_workspace)
    mask = require_within_workspace(mask_path, contract.external_output_workspace)
    grid = validate_prepared_inputs(contract, feature, mask, sidecar_path)
    output = require_within_workspace(output_dir, contract.external_output_workspace)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Tile export directory must be absent or empty.")
    output.mkdir(parents=True, exist_ok=True)
    if exporter is None:
        exporter = import_module("geoai.utils.training").export_geotiff_tiles
    geoai_mask = output / ".floodguard-geoai-export-mask.tif"
    _write_geoai_export_mask(mask, geoai_mask)
    try:
        exporter(
            str(feature),
            str(output),
            in_class_data=str(geoai_mask),
            tile_size=contract.tile_size,
            stride=contract.stride,
            quiet=True,
            skip_empty_tiles=False,
            apply_augmentation=False,
        )
    finally:
        geoai_mask.unlink(missing_ok=True)
    manifest_sha256, training_count, holdout_count, rejected_count = _partition_exported_tiles(
        contract, output, mask
    )
    return TileExportReceipt(
        grid=grid,
        prepared_manifest_relative_path="prepared-tile-manifest.json",
        prepared_manifest_sha256=manifest_sha256,
        training_tile_count=training_count,
        holdout_tile_count=holdout_count,
        rejected_boundary_tile_count=rejected_count,
    )


def _partition_exported_tiles(
    contract: GeoAIRunContract,
    output_dir: Path,
    source_mask_path: Path,
) -> tuple[str, int, int, int]:
    images = output_dir / "images"
    labels = output_dir / "labels"
    if not images.is_dir() or not labels.is_dir():
        raise ValueError("GeoAI tile export must create image and label directories.")
    _bind_exported_label_nodata(labels, source_mask_path)
    image_paths = _relative_file_set(images)
    label_paths = _relative_file_set(labels)
    if not image_paths or image_paths != label_paths:
        raise ValueError("GeoAI tile image and label paths must match exactly.")
    memberships: list[TileMembership] = []
    holdout_count = 0
    rejected_count = 0
    for relative in sorted(image_paths):
        image = _resolve_relative_file(images, relative)
        label = _resolve_relative_file(labels, relative)
        partition = _derive_tile_partition(
            contract,
            image,
            label,
            allow_unassigned=True,
        )
        if partition is None:
            _move_tile_pair(
                image,
                label,
                output_dir / "rejected-boundary",
                relative,
            )
            rejected_count += 1
        elif partition.split == "holdout":
            _move_tile_pair(image, label, output_dir / "holdout", relative)
            holdout_count += 1
        else:
            memberships.append(TileMembership(image_path=relative, label_path=relative))
    manifest_sha256 = write_prepared_tile_manifest(
        contract,
        images,
        labels,
        memberships,
        output_dir / "prepared-tile-manifest.json",
    )
    return manifest_sha256, len(memberships), holdout_count, rejected_count


def _write_geoai_export_mask(source_mask_path: Path, target_path: Path) -> None:
    """Write a temporary binary mask that GeoAI cannot remap nodata as a class."""

    with rasterio.open(source_mask_path) as source:
        values = source.read(1)
        classes = set(np.unique(values).tolist())
        if not classes.issubset({0, 1, 255}):
            raise ValueError("Reference-mask values must stay in {0,1,255}.")
        profile = source.profile.copy()
        profile.pop("nodata", None)
    geoai_values = values.copy()
    geoai_values[geoai_values == 255] = 0
    with rasterio.open(target_path, "w", **profile) as target:
        target.write(geoai_values, 1)
        target.set_band_description(1, "flood_class_without_nodata")


def _bind_exported_label_nodata(labels_dir: Path, source_mask_path: Path) -> None:
    """Verify GeoAI class bytes, then restore nodata from the bound source mask.

    GeoAI 0.41.1 treats every positive raster value as a semantic class and
    omits nodata metadata from exported label profiles. FloodGuard therefore
    exports through a temporary 0/1 mask, compares every valid tile cell back
    to the checksum-bound original 0/1/255 mask, and restores 255 only at the
    original nodata cells. Any class drift fails before partitioning or hashing.
    """

    label_paths = sorted(path for path in labels_dir.rglob("*") if path.is_file())
    if not label_paths:
        raise ValueError("GeoAI tile export did not create label tiles.")
    with rasterio.open(source_mask_path) as source_mask:
        for label_path in label_paths:
            with rasterio.open(label_path, "r+") as label:
                if label.count != 1 or label.dtypes != ("uint8",):
                    raise ValueError("Prepared label tile must contain one uint8 band.")
                exported = label.read(1)
                label_classes = set(np.unique(exported).tolist())
                if not label_classes.issubset({0, 1, 255}):
                    raise ValueError("Prepared label tile values must stay in {0,1,255}.")
                if label.nodata not in (None, 255):
                    raise ValueError("Prepared label tile has conflicting nodata metadata.")
                source_window = rasterio.windows.from_bounds(
                    *label.bounds,
                    transform=source_mask.transform,
                )
                original = source_mask.read(
                    1,
                    window=source_window,
                    out_shape=(label.height, label.width),
                    boundless=True,
                    fill_value=255,
                    resampling=Resampling.nearest,
                )
                original_classes = set(np.unique(original).tolist())
                if not original_classes.issubset({0, 1, 255}):
                    raise ValueError("Bound source-mask tile values must stay in {0,1,255}.")
                valid = original != 255
                if not np.array_equal(exported[valid], original[valid]):
                    raise ValueError(
                        "GeoAI exported label classes differ from the bound source mask."
                    )
                normalized = exported.copy()
                normalized[~valid] = 255
                label.write(normalized, 1)
                label.nodata = 255
                label.set_band_description(1, "flood_class")


def _move_tile_pair(
    image: Path,
    label: Path,
    destination_root: Path,
    relative: str,
) -> None:
    image_target = destination_root / "images" / Path(*PurePosixPath(relative).parts)
    label_target = destination_root / "labels" / Path(*PurePosixPath(relative).parts)
    image_target.parent.mkdir(parents=True, exist_ok=True)
    label_target.parent.mkdir(parents=True, exist_ok=True)
    image.replace(image_target)
    label.replace(label_target)
