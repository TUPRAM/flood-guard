"""Deterministic alignment of static reviewer context to one target grid.

The builder keeps source acquisition, SAR processing, and flood-label logic out
of this module.  It accepts explicit raster paths and an explicit north-up,
projected target grid, then emits byte-hashed static context layers.  Any
uncovered or nodata target cell blocks the entire atomic build.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any

from floodguard.label_factory.tiling import (
    GridContractError,
    validate_projected_metre_crs,
)


CONTEXT_ALIGNMENT_MANIFEST_SCHEMA = "floodguard.context_alignment_manifest.v1"
CONTEXT_ALIGNMENT_BUILDER_ID = "floodguard.label_factory.context_alignment@v1"
CONTEXT_ALIGNMENT_MANIFEST_NAME = "context_alignment_manifest.json"

LAND_COVER_FILE_NAME = "land_cover.tif"
PERMANENT_WATER_FILE_NAME = "permanent_water_context.tif"
ELEVATION_FILE_NAME = "elevation.tif"
SLOPE_FILE_NAME = "slope.tif"
HILLSHADE_FILE_NAME = "dem_hillshade.tif"

WORLD_COVER_CODES = frozenset({10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100})
APPROVED_REVIEW_BUNDLE_ROLES = frozenset(
    {"land_cover", "permanent_water_context", "slope", "dem_hillshade"}
)


class ContextAlignmentError(ValueError):
    """Raised when static context cannot be aligned without missing evidence."""


@dataclass(frozen=True)
class TargetRasterGrid:
    """Explicit north-up target raster contract in a projected metre CRS."""

    crs: str
    affine: tuple[float, float, float, float, float, float]
    width: int
    height: int

    def __post_init__(self) -> None:
        try:
            crs = validate_projected_metre_crs(self.crs)
        except GridContractError as exc:
            raise ContextAlignmentError(str(exc)) from exc
        if len(self.affine) != 6:
            raise ContextAlignmentError(
                "affine must contain exactly six GDAL/rasterio coefficients."
            )
        coefficients: list[float] = []
        for value in self.affine:
            if isinstance(value, bool):
                raise ContextAlignmentError("affine coefficients must be finite numbers.")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ContextAlignmentError(
                    "affine coefficients must be finite numbers."
                ) from exc
            if not math.isfinite(number):
                raise ContextAlignmentError("affine coefficients must be finite numbers.")
            coefficients.append(number)
        a, b, _, d, e, _ = coefficients
        tolerance = max(abs(a), abs(e), 1.0) * 1e-12
        if a <= 0 or e >= 0 or abs(b) > tolerance or abs(d) > tolerance:
            raise ContextAlignmentError(
                "Target affine must be north-up with a > 0, e < 0, and b=d=0."
            )
        for field_name, value in (("width", self.width), ("height", self.height)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 2:
                raise ContextAlignmentError(
                    f"{field_name} must be an integer greater than or equal to 2."
                )
        object.__setattr__(self, "crs", crs)
        object.__setattr__(self, "affine", tuple(coefficients))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Return target bounds as min-x, min-y, max-x, max-y."""

        a, _, c, _, e, f = self.affine
        return (c, f + e * self.height, c + a * self.width, f)

    @property
    def sha256(self) -> str:
        """Return a stable hash of the complete target raster contract."""

        return _canonical_sha256(self.as_dict(include_hash=False))

    def as_dict(self, *, include_hash: bool = True) -> dict[str, object]:
        """Return JSON-safe target-grid metadata."""

        payload: dict[str, object] = {
            "crs": self.crs,
            "affine": list(self.affine),
            "width": self.width,
            "height": self.height,
            "bounds": list(self.bounds),
            "pixel_size_x_m": self.affine[0],
            "pixel_size_y_m": abs(self.affine[4]),
        }
        if include_hash:
            payload["target_grid_sha256"] = self.sha256
        return payload


def build_context_alignment(
    *,
    worldcover_path: str | Path,
    jrc_occurrence_path: str | Path,
    jrc_seasonality_path: str | Path,
    dem_path: str | Path,
    output_directory: str | Path,
    target_grid: TargetRasterGrid,
    permanent_occurrence_threshold_pct: float = 90.0,
    permanent_seasonality_threshold_months: int = 10,
    hillshade_azimuth_deg: float = 315.0,
    hillshade_altitude_deg: float = 45.0,
) -> dict[str, Any]:
    """Align source rasters, derive terrain layers, and atomically write outputs.

    WorldCover and both JRC layers use nearest-neighbour resampling.  The DEM
    uses bilinear resampling.  A cell is marked as permanent-water context only
    when both its JRC occurrence and seasonality meet the declared thresholds.
    This is reviewer context, not a flood label or operational observation.
    """

    np, rasterio = _require_raster_runtime()
    occurrence_threshold = _bounded_number(
        permanent_occurrence_threshold_pct,
        "permanent_occurrence_threshold_pct",
        minimum=0.0,
        maximum=100.0,
    )
    if (
        isinstance(permanent_seasonality_threshold_months, bool)
        or not isinstance(permanent_seasonality_threshold_months, int)
        or not 1 <= permanent_seasonality_threshold_months <= 12
    ):
        raise ContextAlignmentError(
            "permanent_seasonality_threshold_months must be an integer from 1 to 12."
        )
    azimuth = _bounded_number(
        hillshade_azimuth_deg,
        "hillshade_azimuth_deg",
        minimum=0.0,
        maximum=360.0,
        maximum_inclusive=False,
    )
    altitude = _bounded_number(
        hillshade_altitude_deg,
        "hillshade_altitude_deg",
        minimum=0.0,
        maximum=90.0,
        minimum_inclusive=False,
        maximum_inclusive=True,
    )

    source_paths = {
        "worldcover": _require_source_raster(worldcover_path, "worldcover"),
        "jrc_occurrence": _require_source_raster(
            jrc_occurrence_path, "jrc_occurrence"
        ),
        "jrc_seasonality": _require_source_raster(
            jrc_seasonality_path, "jrc_seasonality"
        ),
        "copernicus_dem": _require_source_raster(dem_path, "copernicus_dem"),
    }
    source_metadata = [
        _inspect_source(
            source_paths["worldcover"],
            source_role="worldcover",
            semantic_nodata=0,
            rasterio=rasterio,
        ),
        _inspect_source(
            source_paths["jrc_occurrence"],
            source_role="jrc_occurrence",
            semantic_nodata=255,
            rasterio=rasterio,
        ),
        _inspect_source(
            source_paths["jrc_seasonality"],
            source_role="jrc_seasonality",
            semantic_nodata=255,
            rasterio=rasterio,
        ),
        _inspect_source(
            source_paths["copernicus_dem"],
            source_role="copernicus_dem",
            semantic_nodata=None,
            rasterio=rasterio,
        ),
    ]
    metadata_by_role = {str(row["source_role"]): row for row in source_metadata}
    _require_matching_jrc_grids(
        metadata_by_role["jrc_occurrence"],
        metadata_by_role["jrc_seasonality"],
    )

    output = Path(output_directory)
    if output.exists():
        raise ContextAlignmentError(
            f"Context alignment output is immutable and already exists: {output}"
        )
    parent_existed = output.parent.exists()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    )
    try:
        land_cover = _warp_categorical(
            source_paths["worldcover"],
            source_role="worldcover",
            target_grid=target_grid,
            source_nodata=0,
            destination_nodata=0,
            rasterio=rasterio,
            np=np,
        )
        unknown_land_cover = sorted(
            int(value)
            for value in np.unique(land_cover)
            if int(value) not in WORLD_COVER_CODES
        )
        if unknown_land_cover:
            raise ContextAlignmentError(
                "worldcover contains unsupported target values: "
                + ", ".join(str(value) for value in unknown_land_cover)
            )

        occurrence = _warp_categorical(
            source_paths["jrc_occurrence"],
            source_role="jrc_occurrence",
            target_grid=target_grid,
            source_nodata=255,
            destination_nodata=255,
            rasterio=rasterio,
            np=np,
        )
        if bool(((occurrence < 0) | (occurrence > 100)).any()):
            raise ContextAlignmentError(
                "jrc_occurrence target values must remain within 0..100 percent."
            )
        seasonality = _warp_categorical(
            source_paths["jrc_seasonality"],
            source_role="jrc_seasonality",
            target_grid=target_grid,
            source_nodata=255,
            destination_nodata=255,
            rasterio=rasterio,
            np=np,
        )
        if bool(((seasonality < 0) | (seasonality > 12)).any()):
            raise ContextAlignmentError(
                "jrc_seasonality target values must remain within 0..12 months."
            )
        permanent_water = (
            (occurrence.astype("float32") >= occurrence_threshold)
            & (seasonality >= permanent_seasonality_threshold_months)
        ).astype("uint8")

        elevation = _warp_dem(
            source_paths["copernicus_dem"],
            target_grid=target_grid,
            rasterio=rasterio,
            np=np,
        )
        slope, hillshade = _derive_terrain(
            elevation,
            target_grid=target_grid,
            azimuth_deg=azimuth,
            altitude_deg=altitude,
            np=np,
        )

        source_set_hashes = {
            role: str(metadata_by_role[role]["source_sha256"])
            for role in sorted(metadata_by_role)
        }
        layer_definitions = (
            {
                "layer_id": "land_cover",
                "layer_role": "land_cover",
                "file_name": LAND_COVER_FILE_NAME,
                "array": land_cover,
                "dtype": "uint8",
                "nodata": 0,
                "resampling_method": "nearest",
                "source_roles": ["worldcover"],
                "derivation_method": "aligned_source_values",
                "assumptions": (
                    "ESA WorldCover categorical classes; nearest-neighbour aligned."
                ),
            },
            {
                "layer_id": "permanent_water_context",
                "layer_role": "permanent_water_context",
                "file_name": PERMANENT_WATER_FILE_NAME,
                "array": permanent_water,
                "dtype": "uint8",
                "nodata": 255,
                "resampling_method": "nearest_then_boolean_derivation",
                "source_roles": ["jrc_occurrence", "jrc_seasonality"],
                "derivation_method": (
                    "1 where aligned occurrence >= threshold AND aligned "
                    "seasonality >= threshold; otherwise 0"
                ),
                "assumptions": (
                    "Static likely-permanent-water reviewer context; not an event-time "
                    "flood label. Dual JRC source binding must be preserved."
                ),
            },
            {
                "layer_id": "elevation",
                "layer_role": "elevation",
                "file_name": ELEVATION_FILE_NAME,
                "array": elevation,
                "dtype": "float32",
                "nodata": -9999.0,
                "resampling_method": "bilinear",
                "source_roles": ["copernicus_dem"],
                "derivation_method": "aligned_source_values",
                "assumptions": (
                    "Copernicus DEM elevation in source vertical units; elevation is "
                    "not presently an approved formal review-bundle layer role."
                ),
            },
            {
                "layer_id": "slope",
                "layer_role": "slope",
                "file_name": SLOPE_FILE_NAME,
                "array": slope,
                "dtype": "float32",
                "nodata": -9999.0,
                "resampling_method": "derived_from_bilinear_dem",
                "source_roles": ["copernicus_dem"],
                "derivation_method": "gradient_magnitude_to_degrees",
                "assumptions": (
                    "Slope degrees derived from the aligned DEM using target metre "
                    "pixel spacing and one-sided edge gradients."
                ),
            },
            {
                "layer_id": "dem_hillshade",
                "layer_role": "dem_hillshade",
                "file_name": HILLSHADE_FILE_NAME,
                "array": hillshade,
                "dtype": "uint8",
                "nodata": 255,
                "resampling_method": "derived_from_bilinear_dem",
                "source_roles": ["copernicus_dem"],
                "derivation_method": "surface_normal_fixed_light_hillshade",
                "assumptions": (
                    "Display-only hillshade with fixed azimuth and altitude; not an "
                    "elevation measurement or flood label."
                ),
            },
        )

        layer_rows: list[dict[str, Any]] = []
        for definition in layer_definitions:
            source_roles = list(definition["source_roles"])
            source_hashes = {
                role: source_set_hashes[role] for role in source_roles
            }
            path = temporary / str(definition["file_name"])
            _write_geotiff(
                path,
                array=definition["array"],
                dtype=str(definition["dtype"]),
                nodata=definition["nodata"],
                target_grid=target_grid,
                layer_role=str(definition["layer_role"]),
                source_set_sha256=_canonical_sha256(source_hashes),
                rasterio=rasterio,
                np=np,
            )
            _verify_written_raster(
                path,
                expected=definition["array"],
                target_grid=target_grid,
                expected_dtype=str(definition["dtype"]),
                expected_nodata=definition["nodata"],
                rasterio=rasterio,
                np=np,
            )
            role = str(definition["layer_role"])
            layer_rows.append(
                {
                    "context_layer_candidate_id": role,
                    "layer_role": role,
                    "review_bundle_layer_role": (
                        role if role in APPROVED_REVIEW_BUNDLE_ROLES else None
                    ),
                    "eligible_for_current_context_layers_csv": (
                        role in APPROVED_REVIEW_BUNDLE_ROLES
                    ),
                    "display_name": role.replace("_", " ").title(),
                    "path_hint": str(definition["file_name"]),
                    "processed_layer_sha256": _file_sha256(path),
                    "source_roles": source_roles,
                    "source_sha256s": source_hashes,
                    "source_set_sha256": _canonical_sha256(source_hashes),
                    "resampling_method": definition["resampling_method"],
                    "derivation_method": definition["derivation_method"],
                    "dtype": str(definition["dtype"]),
                    "nodata": definition["nodata"],
                    "valid_data_fraction": 1.0,
                    "minimum_value": _json_number(np.min(definition["array"])),
                    "maximum_value": _json_number(np.max(definition["array"])),
                    "target_grid_sha256": target_grid.sha256,
                    "crs": target_grid.crs,
                    "affine": list(target_grid.affine),
                    "width": target_grid.width,
                    "height": target_grid.height,
                    "allowed_for_blinded_review_candidate": (
                        role in APPROVED_REVIEW_BUNDLE_ROLES
                    ),
                    "confidence_class_candidate": "medium",
                    "assumptions": definition["assumptions"],
                }
            )

        parameters = {
            "worldcover_resampling": "nearest",
            "jrc_occurrence_resampling": "nearest",
            "jrc_seasonality_resampling": "nearest",
            "dem_resampling": "bilinear",
            "permanent_occurrence_threshold_pct": occurrence_threshold,
            "permanent_seasonality_threshold_months": (
                permanent_seasonality_threshold_months
            ),
            "permanent_water_operator": "logical_and",
            "slope_units": "degrees",
            "slope_method": "numpy_gradient_with_one_sided_edges",
            "hillshade_azimuth_deg": azimuth,
            "hillshade_altitude_deg": altitude,
            "hillshade_valid_range": [0, 254],
        }
        payload: dict[str, Any] = {
            "artifact_schema": CONTEXT_ALIGNMENT_MANIFEST_SCHEMA,
            "builder": CONTEXT_ALIGNMENT_BUILDER_ID,
            "target_grid": target_grid.as_dict(),
            "derivation_parameters": parameters,
            "source_inputs": source_metadata,
            "source_inputs_sha256": _canonical_sha256(source_metadata),
            "layers": layer_rows,
            "layer_count": len(layer_rows),
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "assumptions": (
                "Static reviewer context only. Complete raster coverage is proven for "
                "the declared target grid; this artifact does not establish flood "
                "truth, event-time validity, field validation, or operational use."
            ),
        }
        manifest = {**payload, "manifest_sha256": _canonical_sha256(payload)}
        manifest_path = temporary / CONTEXT_ALIGNMENT_MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _validate_manifest_self_hash(manifest)
        temporary.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if not parent_existed:
            try:
                output.parent.rmdir()
            except OSError:
                pass
        raise


def load_context_alignment_manifest(path: str | Path) -> dict[str, Any]:
    """Load and verify a context-alignment manifest's deterministic self-hash."""

    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContextAlignmentError(
            f"Could not read context alignment manifest: {manifest_path}"
        ) from exc
    if not isinstance(value, dict):
        raise ContextAlignmentError("Context alignment manifest must be a JSON object.")
    _validate_manifest_self_hash(value)
    return value


def _require_raster_runtime() -> tuple[Any, Any]:
    try:
        import numpy as np
        import rasterio
    except ImportError as exc:
        raise ContextAlignmentError(
            "Static context alignment requires NumPy and rasterio; install the "
            "project's raster/geospatial optional dependencies."
        ) from exc
    return np, rasterio


def _require_source_raster(path: str | Path, source_role: str) -> Path:
    source = Path(path)
    if not source.is_file():
        raise ContextAlignmentError(
            f"{source_role} source raster does not exist: {source}"
        )
    if source.suffix.lower() not in {".tif", ".tiff"}:
        raise ContextAlignmentError(
            f"{source_role} source must be a GeoTIFF: {source.name}"
        )
    return source


def _inspect_source(
    path: Path,
    *,
    source_role: str,
    semantic_nodata: int | float | None,
    rasterio: Any,
) -> dict[str, Any]:
    try:
        with rasterio.open(path) as dataset:
            if dataset.count != 1:
                raise ContextAlignmentError(
                    f"{source_role} must contain exactly one raster band."
                )
            if dataset.crs is None:
                raise ContextAlignmentError(f"{source_role} has no declared CRS.")
            if dataset.width <= 0 or dataset.height <= 0:
                raise ContextAlignmentError(f"{source_role} has invalid dimensions.")
            transform = dataset.transform
            affine = [
                float(transform.a),
                float(transform.b),
                float(transform.c),
                float(transform.d),
                float(transform.e),
                float(transform.f),
            ]
            if not all(math.isfinite(value) for value in affine):
                raise ContextAlignmentError(
                    f"{source_role} has a non-finite affine transform."
                )
            mask_flags = sorted(flag.name for flag in dataset.mask_flag_enums[0])
            unsupported_flags = set(mask_flags) - {"all_valid", "nodata"}
            if unsupported_flags:
                raise ContextAlignmentError(
                    f"{source_role} uses unsupported source mask flags: "
                    + ", ".join(sorted(unsupported_flags))
                )
            if "nodata" in mask_flags and dataset.nodata is None:
                raise ContextAlignmentError(
                    f"{source_role} declares a nodata mask without a nodata value."
                )
            return {
                "source_role": source_role,
                "source_file_name": path.name,
                "source_size_bytes": path.stat().st_size,
                "source_sha256": _file_sha256(path),
                "driver": dataset.driver,
                "crs": dataset.crs.to_string(),
                "affine": affine,
                "width": dataset.width,
                "height": dataset.height,
                "band_count": dataset.count,
                "dtype": dataset.dtypes[0],
                "declared_nodata": _json_nodata(dataset.nodata),
                "semantic_nodata_used": semantic_nodata,
                "mask_flags": mask_flags,
            }
    except ContextAlignmentError:
        raise
    except Exception as exc:
        raise ContextAlignmentError(
            f"Could not inspect {source_role} source raster: {path}"
        ) from exc


def _require_matching_jrc_grids(
    occurrence: Mapping[str, Any], seasonality: Mapping[str, Any]
) -> None:
    fields = ("crs", "affine", "width", "height")
    mismatched = [field for field in fields if occurrence[field] != seasonality[field]]
    if mismatched:
        raise ContextAlignmentError(
            "JRC occurrence and seasonality must share one raw grid; mismatched: "
            + ", ".join(mismatched)
        )


def _warp_categorical(
    path: Path,
    *,
    source_role: str,
    target_grid: TargetRasterGrid,
    source_nodata: int,
    destination_nodata: int,
    rasterio: Any,
    np: Any,
) -> Any:
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.warp import reproject

    destination = np.full(
        (target_grid.height, target_grid.width),
        destination_nodata,
        dtype="uint8",
    )
    try:
        with rasterio.open(path) as source:
            reproject(
                source=rasterio.band(source, 1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source_nodata,
                dst_transform=Affine(*target_grid.affine),
                dst_crs=target_grid.crs,
                dst_nodata=destination_nodata,
                resampling=Resampling.nearest,
                init_dest_nodata=True,
                num_threads=1,
                warp_mem_limit=64,
            )
    except Exception as exc:
        raise ContextAlignmentError(
            f"Could not align {source_role} to the target grid."
        ) from exc
    invalid = destination == destination_nodata
    _require_complete_coverage(invalid, source_role=source_role, np=np)
    return destination


def _warp_dem(
    path: Path,
    *,
    target_grid: TargetRasterGrid,
    rasterio: Any,
    np: Any,
) -> Any:
    from rasterio.enums import Resampling
    from rasterio.transform import Affine
    from rasterio.warp import reproject

    destination = np.full(
        (target_grid.height, target_grid.width), np.nan, dtype="float32"
    )
    try:
        with rasterio.open(path) as source:
            reproject(
                source=rasterio.band(source, 1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=Affine(*target_grid.affine),
                dst_crs=target_grid.crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
                num_threads=1,
                warp_mem_limit=64,
            )
    except Exception as exc:
        raise ContextAlignmentError(
            "Could not align copernicus_dem to the target grid."
        ) from exc
    invalid = ~np.isfinite(destination)
    _require_complete_coverage(invalid, source_role="copernicus_dem", np=np)
    return destination.astype("float32", copy=False)


def _require_complete_coverage(invalid: Any, *, source_role: str, np: Any) -> None:
    invalid_count = int(np.count_nonzero(invalid))
    if invalid_count:
        total = int(invalid.size)
        raise ContextAlignmentError(
            f"{source_role} has incomplete target coverage or nodata: "
            f"{invalid_count}/{total} target cells are invalid."
        )


def _derive_terrain(
    elevation: Any,
    *,
    target_grid: TargetRasterGrid,
    azimuth_deg: float,
    altitude_deg: float,
    np: Any,
) -> tuple[Any, Any]:
    edge_order = 2 if min(elevation.shape) >= 3 else 1
    row_gradient, dz_dx_east = np.gradient(
        elevation.astype("float64"),
        abs(target_grid.affine[4]),
        target_grid.affine[0],
        edge_order=edge_order,
    )
    dz_dy_north = -row_gradient
    magnitude = np.hypot(dz_dx_east, dz_dy_north)
    slope = np.degrees(np.arctan(magnitude)).astype("float32")

    azimuth = np.radians(azimuth_deg)
    altitude = np.radians(altitude_deg)
    light_x = np.cos(altitude) * np.sin(azimuth)
    light_y = np.cos(altitude) * np.cos(azimuth)
    light_z = np.sin(altitude)
    illumination = (
        -dz_dx_east * light_x - dz_dy_north * light_y + light_z
    ) / np.sqrt(1.0 + dz_dx_east**2 + dz_dy_north**2)
    hillshade = np.rint(np.clip(illumination, 0.0, 1.0) * 254.0).astype(
        "uint8"
    )
    if not bool(np.isfinite(slope).all()):
        raise ContextAlignmentError("Derived slope contains non-finite cells.")
    return slope, hillshade


def _write_geotiff(
    path: Path,
    *,
    array: Any,
    dtype: str,
    nodata: int | float,
    target_grid: TargetRasterGrid,
    layer_role: str,
    source_set_sha256: str,
    rasterio: Any,
    np: Any,
) -> None:
    from rasterio.transform import Affine

    values = np.asarray(array, dtype=dtype)
    if values.shape != (target_grid.height, target_grid.width):
        raise ContextAlignmentError(
            f"{layer_role} array does not match the declared target dimensions."
        )
    if np.issubdtype(values.dtype, np.floating) and not bool(
        np.isfinite(values).all()
    ):
        raise ContextAlignmentError(
            f"{layer_role} contains non-finite values before writing."
        )
    profile: dict[str, Any] = {
        "driver": "GTiff",
        "width": target_grid.width,
        "height": target_grid.height,
        "count": 1,
        "dtype": dtype,
        "crs": target_grid.crs,
        "transform": Affine(*target_grid.affine),
        "nodata": nodata,
        "compress": "DEFLATE",
        "zlevel": 9,
        "predictor": 3 if np.issubdtype(values.dtype, np.floating) else 2,
        "BIGTIFF": "IF_SAFER",
        "num_threads": "1",
    }
    if target_grid.width >= 256 and target_grid.height >= 256:
        profile.update(tiled=True, blockxsize=256, blockysize=256)
    with rasterio.Env(GDAL_NUM_THREADS="1"):
        with rasterio.open(path, "w", **profile) as dataset:
            dataset.write(values, 1)
            dataset.update_tags(
                AREA_OR_POINT="Area",
                BUILDER=CONTEXT_ALIGNMENT_BUILDER_ID,
                LAYER_ROLE=layer_role,
                SOURCE_SET_SHA256=source_set_sha256,
                TARGET_GRID_SHA256=target_grid.sha256,
            )


def _verify_written_raster(
    path: Path,
    *,
    expected: Any,
    target_grid: TargetRasterGrid,
    expected_dtype: str,
    expected_nodata: int | float,
    rasterio: Any,
    np: Any,
) -> None:
    from rasterio.transform import Affine

    try:
        with rasterio.open(path) as dataset:
            if (
                dataset.count != 1
                or dataset.width != target_grid.width
                or dataset.height != target_grid.height
                or dataset.crs is None
                or dataset.crs.to_string() != target_grid.crs
                or dataset.transform != Affine(*target_grid.affine)
                or dataset.dtypes[0] != expected_dtype
                or not _nodata_equal(dataset.nodata, expected_nodata)
            ):
                raise ContextAlignmentError(
                    f"Written raster metadata does not match its target contract: {path.name}"
                )
            observed = dataset.read(1)
    except ContextAlignmentError:
        raise
    except Exception as exc:
        raise ContextAlignmentError(
            f"Could not verify written context raster: {path.name}"
        ) from exc
    if not np.array_equal(observed, np.asarray(expected, dtype=expected_dtype)):
        raise ContextAlignmentError(
            f"Written raster values do not match their derivation: {path.name}"
        )
    if bool(np.any(observed == expected_nodata)):
        raise ContextAlignmentError(
            f"Written raster unexpectedly contains nodata: {path.name}"
        )


def _validate_manifest_self_hash(manifest: Mapping[str, Any]) -> None:
    if manifest.get("artifact_schema") != CONTEXT_ALIGNMENT_MANIFEST_SCHEMA:
        raise ContextAlignmentError("Unknown context alignment manifest schema.")
    declared = manifest.get("manifest_sha256")
    if not isinstance(declared, str) or len(declared) != 64:
        raise ContextAlignmentError(
            "Context alignment manifest has no complete self-hash."
        )
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if _canonical_sha256(unsigned) != declared:
        raise ContextAlignmentError("Context alignment manifest self-hash mismatch.")


def _bounded_number(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
    minimum_inclusive: bool = True,
    maximum_inclusive: bool = True,
) -> float:
    if isinstance(value, bool):
        raise ContextAlignmentError(f"{field_name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContextAlignmentError(f"{field_name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ContextAlignmentError(f"{field_name} must be a finite number.")
    lower_ok = number >= minimum if minimum_inclusive else number > minimum
    upper_ok = number <= maximum if maximum_inclusive else number < maximum
    if not lower_ok or not upper_ok:
        left = "[" if minimum_inclusive else "("
        right = "]" if maximum_inclusive else ")"
        raise ContextAlignmentError(
            f"{field_name} must lie in {left}{minimum}, {maximum}{right}."
        )
    return number


def _file_sha256(path: Path, *, chunk_size: int = 16 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise ContextAlignmentError(f"Could not hash file: {path}") from exc
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_nodata(value: object) -> int | float | str | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number):
        return "nan"
    if not math.isfinite(number):
        return str(number)
    return int(number) if number.is_integer() else number


def _json_number(value: object) -> int | float:
    number = float(value)
    if not math.isfinite(number):
        raise ContextAlignmentError("Layer statistics contain a non-finite value.")
    return int(number) if number.is_integer() else number


def _nodata_equal(left: object, right: object) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=0.0)
