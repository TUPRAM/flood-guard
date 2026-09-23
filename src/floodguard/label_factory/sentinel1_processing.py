"""Version-pinned Sentinel-1 GRD processing for the label-factory data lane.

This module deliberately stops at calibrated, radiometrically terrain-flattened,
orthorectified evidence on a caller-declared grid.  It does not derive flood
labels, probabilities, FPPS inputs, or warning products.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import subprocess
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

CANONICAL_FLOAT_NODATA = -9999.0
CANONICAL_MASK_NODATA = 255
PINNED_SNAP_VERSION = "13.0.0"
SNAP_TILE_CACHE_SIZE = "512M"
SNAP_PARALLELISM = 4
APPROVED_TARGET_CRS = "EPSG:32647"
APPROVED_RESOLUTION_M = 10.0
SNAP_REQUIRED_BANDS: tuple[str, ...] = (
    "Gamma0_VV",
    "Gamma0_VH",
    "localIncidenceAngle",
    "projectedLocalIncidenceAngle",
    "layoverShadowMask",
)
THRESHOLD_BASELINE_SCHEMA = "floodguard.sentinel1_adaptive_otsu_candidate.v1"
THRESHOLD_BASELINE_MAX_CELLS = 10_000_000
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class Sentinel1ProcessingError(RuntimeError):
    """Raised when SNAP execution or canonical raster extraction fails."""


@dataclass(frozen=True)
class _ResolvedSourceProduct:
    """A SNAP-readable source plus deterministic source-package identity."""

    read_path: Path
    product_name: str
    sha256: str
    packaging: str
    file_count: int


@dataclass(frozen=True)
class TargetRasterGrid:
    """One exact projected output grid for all Mae Sai processing artifacts."""

    crs: str
    left: float
    bottom: float
    right: float
    top: float
    resolution_m: float
    grid_contract_sha256: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"EPSG:\d{4,6}", self.crs) is None:
            raise Sentinel1ProcessingError("Target CRS must use canonical EPSG:<code> form.")
        values = (self.left, self.bottom, self.right, self.top, self.resolution_m)
        if any(not math.isfinite(value) for value in values):
            raise Sentinel1ProcessingError("Target grid coordinates must be finite.")
        if self.right <= self.left or self.top <= self.bottom:
            raise Sentinel1ProcessingError("Target grid bounds must have positive area.")
        if self.resolution_m <= 0:
            raise Sentinel1ProcessingError("Target resolution must be positive.")
        if self.crs != APPROVED_TARGET_CRS:
            raise Sentinel1ProcessingError(
                f"This pinned graph requires target CRS {APPROVED_TARGET_CRS}."
            )
        if not math.isclose(
            self.resolution_m, APPROVED_RESOLUTION_M, rel_tol=0.0, abs_tol=1e-9
        ):
            raise Sentinel1ProcessingError(
                f"This pinned graph requires {APPROVED_RESOLUTION_M:g} m pixels."
            )
        _exact_cell_count(self.right - self.left, self.resolution_m, "width")
        _exact_cell_count(self.top - self.bottom, self.resolution_m, "height")
        for coordinate, label in (
            (self.left, "left"),
            (self.bottom, "bottom"),
            (self.right, "right"),
            (self.top, "top"),
        ):
            _require_grid_edge(coordinate, self.resolution_m, label)
        if _SHA256_PATTERN.fullmatch(self.grid_contract_sha256) is None:
            raise Sentinel1ProcessingError(
                "grid_contract_sha256 must be a lowercase complete SHA-256."
            )

    @property
    def width(self) -> int:
        """Return the exact output width in cells."""

        return _exact_cell_count(self.right - self.left, self.resolution_m, "width")

    @property
    def height(self) -> int:
        """Return the exact output height in cells."""

        return _exact_cell_count(self.top - self.bottom, self.resolution_m, "height")

    @property
    def transform(self) -> object:
        """Return the north-up rasterio transform, importing geo code lazily."""

        from rasterio.transform import from_origin

        return from_origin(self.left, self.top, self.resolution_m, self.resolution_m)


@dataclass(frozen=True)
class AdaptiveOtsuConfig:
    """Frozen candidate baseline parameters; these are not accuracy criteria."""

    window_pixels: int = 256
    stride_pixels: int = 128
    min_valid_samples: int = 4096
    histogram_bins: int = 64
    min_class_fraction: float = 0.08
    min_mean_separation_db: float = 1.5
    min_between_variance_fraction: float = 0.72
    max_terrain_slope_degrees: float = 20.0

    def __post_init__(self) -> None:
        if (
            self.window_pixels < 2
            or self.stride_pixels < 1
            or self.stride_pixels > self.window_pixels
            or self.min_valid_samples < 2
            or self.min_valid_samples > self.window_pixels**2
            or self.histogram_bins < 8
            or self.histogram_bins > 512
        ):
            raise Sentinel1ProcessingError("Invalid adaptive Otsu window or histogram support.")
        if not (0 < self.min_class_fraction < 0.5):
            raise Sentinel1ProcessingError("min_class_fraction must be in (0, 0.5).")
        if not (0 < self.min_between_variance_fraction < 1):
            raise Sentinel1ProcessingError("min_between_variance_fraction must be in (0, 1).")
        if (
            not math.isfinite(self.min_mean_separation_db)
            or self.min_mean_separation_db <= 0
            or not math.isfinite(self.max_terrain_slope_degrees)
            or self.max_terrain_slope_degrees <= 0
            or self.max_terrain_slope_degrees >= 90
        ):
            raise Sentinel1ProcessingError("Invalid Otsu separation or terrain slope limit.")


def run_snap_rtc_graph(
    *,
    gpt_path: str | Path,
    graph_path: str | Path,
    source_product: str | Path,
    external_dem: str | Path,
    subset_wkt: str,
    output_dim: str | Path,
    snap_auxdata_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Run the pinned SNAP graph once and return byte-backed execution metadata."""

    gpt = _required_file(gpt_path, "SNAP gpt executable")
    graph = _required_file(graph_path, "SNAP graph")
    source = _resolve_source_product(source_product)
    dem = _required_file(external_dem, "external DEM")
    target = Path(output_dim)
    if target.suffix.lower() != ".dim":
        raise Sentinel1ProcessingError("SNAP intermediate output must use .dim.")
    stdout_path = target.with_suffix(".stdout.log")
    stderr_path = target.with_suffix(".stderr.log")
    if any(
        path.exists()
        for path in (target, target.with_suffix(".data"), stdout_path, stderr_path)
    ):
        raise Sentinel1ProcessingError(
            f"SNAP output is immutable and already exists: {target}"
        )
    if not subset_wkt.strip().upper().startswith("POLYGON"):
        raise Sentinel1ProcessingError("subset_wkt must be a non-blank POLYGON WKT.")
    snap_version = _snap_version(gpt)
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(gpt),
        str(graph),
        "-e",
        "-c",
        SNAP_TILE_CACHE_SIZE,
        "-q",
        str(SNAP_PARALLELISM),
        "-x",
        f"-Pinput={source.read_path}",
        f"-Poutput={target}",
        f"-PexternalDem={dem}",
        f"-PsubsetWkt={subset_wkt}",
    ]
    completed = subprocess.run(
        command,
        cwd=target.parent,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise Sentinel1ProcessingError(
            f"SNAP graph failed with exit code {completed.returncode}; "
            f"inspect {stderr_path}."
        )
    if not target.is_file() or not target.with_suffix(".data").is_dir():
        raise Sentinel1ProcessingError("SNAP exited successfully without complete DIMAP output.")
    warning_text = f"{completed.stdout}\n{completed.stderr}".lower()
    if "calibration lut for this product could be incorrect" in warning_text:
        raise Sentinel1ProcessingError(
            "SNAP reported an unreliable calibration LUT. Use the original SAFE "
            "edition, not the CDSE COG_SAFE conversion."
        )
    dimap_product_name = _dimap_metadata_attribute(target, "PRODUCT")
    source_processing_system = _dimap_metadata_attribute(
        target, "Processing_system_identifier"
    )
    if (
        "_COG" in dimap_product_name.upper()
        or "COGIFIER" in source_processing_system.upper()
    ):
        raise Sentinel1ProcessingError(
            "SNAP output identifies a COG-converted Sentinel-1 product. Use the "
            "original SAFE edition for calibrated evidence."
        )
    orbit_state_vector_file = _dimap_metadata_attribute(
        target, "orbit_state_vector_file"
    )
    orbit_file_name = Path(orbit_state_vector_file.split()[-1]).name
    if "POEORB" not in orbit_file_name.upper():
        raise Sentinel1ProcessingError(
            "SNAP output is not bound to a Sentinel Precise POEORB auxiliary."
        )
    auxdata = (
        Path(snap_auxdata_directory)
        if snap_auxdata_directory is not None
        else Path.home() / ".snap" / "auxdata"
    )
    if not auxdata.is_dir():
        raise Sentinel1ProcessingError(f"SNAP auxiliary-data directory is missing: {auxdata}")
    orbit_auxiliary = _find_unique_auxiliary_file(
        auxdata / "Orbits" / "Sentinel-1", orbit_file_name
    )
    egm96_auxiliary = _required_file(
        auxdata / "dem" / "egm96" / "ww15mgh_b.zip",
        "SNAP EGM96 auxiliary",
    )
    return {
        "gpt_path": str(gpt),
        "gpt_sha256": file_sha256(gpt),
        "snap_version": snap_version,
        "graph_path": str(graph),
        "graph_sha256": file_sha256(graph),
        "source_product_name": source.product_name,
        "source_sha256": source.sha256,
        "source_hash_kind": (
            "safe_tree_sha256_v1"
            if source.packaging == "unpacked_safe_directory"
            else "file_sha256"
        ),
        "source_packaging": source.packaging,
        "source_file_count": source.file_count,
        "dimap_product_name": dimap_product_name,
        "source_processing_system": source_processing_system,
        "orbit_state_vector_file": orbit_state_vector_file,
        "orbit_auxiliary_name": orbit_auxiliary.name,
        "orbit_auxiliary_sha256": file_sha256(orbit_auxiliary),
        "external_dem_name": dem.name,
        "external_dem_sha256": file_sha256(dem),
        "external_dem_expected_vertical_datum": "EGM2008 orthometric",
        "external_dem_apply_egm": True,
        "external_dem_egm_correction": "SNAP bundled EGM96 approximation",
        "snap_egm96_auxiliary_name": egm96_auxiliary.name,
        "snap_egm96_auxiliary_sha256": file_sha256(egm96_auxiliary),
        "external_dem_nodata_value": 0,
        "subset_wkt": subset_wkt,
        "output_dim_name": target.name,
        "stdout_log_sha256": file_sha256(stdout_path),
        "stderr_log_sha256": file_sha256(stderr_path),
        "completed_at_utc": _utc_now(),
        "return_code": completed.returncode,
        "execution_profile": {
            "tile_cache_size": SNAP_TILE_CACHE_SIZE,
            "parallelism": SNAP_PARALLELISM,
            "clear_tile_cache_after_row": True,
        },
    }


def extract_canonical_rtc_layers(
    *,
    snap_dim: str | Path,
    output_directory: str | Path,
    acquisition_prefix: str,
    grid: TargetRasterGrid,
    source_product_id: str,
) -> dict[str, Any]:
    """Extract named SNAP bands, align them exactly, and convert gamma0 to dB."""

    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject, transform_bounds

    dim = _required_file(snap_dim, "SNAP DIMAP header")
    data_dir = dim.with_suffix(".data")
    if not data_dir.is_dir():
        raise Sentinel1ProcessingError(f"Missing SNAP DIMAP data directory: {data_dir}")
    prefix = _canonical_identifier(acquisition_prefix, "acquisition_prefix")
    product_id = source_product_id.strip()
    if not product_id:
        raise Sentinel1ProcessingError("source_product_id must not be blank.")
    target_dir = Path(output_directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    inputs = {name: data_dir / f"{name}.img" for name in SNAP_REQUIRED_BANDS}
    for name, path in inputs.items():
        _required_file(path, f"SNAP band {name}")

    arrays: dict[str, Any] = {}
    source_signatures: dict[str, Any] = {}
    for name, path in inputs.items():
        header_path = _required_file(path.with_suffix(".hdr"), f"SNAP band header {name}")
        with rasterio.open(path) as dataset:
            if dataset.count != 1:
                raise Sentinel1ProcessingError(f"SNAP band {name} must be single-band.")
            if dataset.crs is None:
                raise Sentinel1ProcessingError(f"SNAP band {name} has no CRS.")
            source_bounds = transform_bounds(dataset.crs, grid.crs, *dataset.bounds)
            _require_bounds_cover(source_bounds, grid)
            is_mask = name == "layoverShadowMask"
            destination = np.full(
                (grid.height, grid.width),
                CANONICAL_MASK_NODATA if is_mask else np.nan,
                dtype="uint8" if is_mask else "float32",
            )
            if is_mask:
                source_values: object = rasterio.band(dataset, 1)
                # SNAP describes zero as nodata for this bit band even though
                # zero is also the valid "neither layover nor shadow" code.
                # Radiometric support below supplies the unambiguous footprint.
                source_nodata = None
            else:
                source_values = dataset.read(1).astype("float32", copy=False)
                invalid = ~np.isfinite(source_values) | (source_values <= 0)
                if dataset.nodata is not None and math.isfinite(dataset.nodata):
                    invalid |= source_values == dataset.nodata
                source_values = source_values.copy()
                source_values[invalid] = np.nan
                source_nodata = np.nan
            reproject(
                source=source_values,
                destination=destination,
                src_transform=dataset.transform,
                src_crs=dataset.crs,
                src_nodata=source_nodata,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=CANONICAL_MASK_NODATA if is_mask else np.nan,
                resampling=Resampling.nearest if is_mask else Resampling.bilinear,
                init_dest_nodata=True,
            )
            arrays[name] = destination
            source_signatures[name] = {
                "source_file_name": path.name,
                "source_file_sha256": file_sha256(path),
                "source_header_name": header_path.name,
                "source_header_sha256": file_sha256(header_path),
                "source_crs": str(dataset.crs),
                "source_transform": [float(value) for value in dataset.transform[:6]],
                "source_width": dataset.width,
                "source_height": dataset.height,
                "source_dtype": dataset.dtypes[0],
                "source_nodata": (
                    None if dataset.nodata is None else float(dataset.nodata)
                ),
            }

    layover_shadow = arrays["layoverShadowMask"]
    radiometric_support = np.ones(layover_shadow.shape, dtype=bool)
    for polarization in ("VV", "VH"):
        values = arrays[f"Gamma0_{polarization}"]
        radiometric_support &= np.isfinite(values) & (values > 0)
    supported_geometry = radiometric_support & (layover_shadow == 0)
    outputs: dict[str, Any] = {}
    for polarization in ("VV", "VH"):
        linear = arrays[f"Gamma0_{polarization}"]
        valid = supported_geometry & np.isfinite(linear) & (linear > 0)
        if not bool(valid.any()):
            raise Sentinel1ProcessingError(
                f"No valid {polarization} observations cover the canonical grid."
            )
        db = np.full(linear.shape, CANONICAL_FLOAT_NODATA, dtype="float32")
        db[valid] = 10.0 * np.log10(linear[valid])
        output = target_dir / f"{prefix}_{polarization.lower()}_db.tif"
        _write_geotiff(
            output,
            db,
            grid=grid,
            nodata=CANONICAL_FLOAT_NODATA,
            role=f"{prefix}_{polarization.lower()}_db",
            source_product_id=product_id,
        )
        outputs[polarization.lower()] = _output_record(output, valid)

    for source_name, suffix in (
        ("localIncidenceAngle", "local_incidence_angle"),
        ("projectedLocalIncidenceAngle", "projected_local_incidence_angle"),
    ):
        values = arrays[source_name].astype("float32", copy=False)
        valid = supported_geometry & np.isfinite(values) & (values > 0)
        prepared = np.full(values.shape, CANONICAL_FLOAT_NODATA, dtype="float32")
        prepared[valid] = values[valid]
        output = target_dir / f"{prefix}_{suffix}.tif"
        _write_geotiff(
            output,
            prepared,
            grid=grid,
            nodata=CANONICAL_FLOAT_NODATA,
            role=f"{prefix}_{suffix}",
            source_product_id=product_id,
        )
        outputs[suffix] = _output_record(output, valid)

    mask_output = target_dir / f"{prefix}_layover_shadow_mask.tif"
    prepared_mask = np.full(
        layover_shadow.shape, CANONICAL_MASK_NODATA, dtype="uint8"
    )
    mask_valid = radiometric_support & (layover_shadow != CANONICAL_MASK_NODATA)
    prepared_mask[mask_valid] = layover_shadow[mask_valid]
    _write_geotiff(
        mask_output,
        prepared_mask,
        grid=grid,
        nodata=CANONICAL_MASK_NODATA,
        role=f"{prefix}_layover_shadow_mask",
        source_product_id=product_id,
    )
    outputs["layover_shadow_mask"] = _output_record(mask_output, mask_valid)

    return {
        "artifact_schema": "floodguard.sentinel1_canonical_rtc_layers.v1",
        "source_product_id": product_id,
        "acquisition_prefix": prefix,
        "snap_dim_name": dim.name,
        "snap_dim_sha256": file_sha256(dim),
        "grid": {
            "crs": grid.crs,
            "left": grid.left,
            "bottom": grid.bottom,
            "right": grid.right,
            "top": grid.top,
            "resolution_m": grid.resolution_m,
            "width": grid.width,
            "height": grid.height,
            "grid_contract_sha256": grid.grid_contract_sha256,
        },
        "source_bands": source_signatures,
        "outputs": outputs,
        "created_at_utc": _utc_now(),
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "assumptions": (
            "Gamma0 is radiometrically terrain-flattened and Range-Doppler "
            "orthorectified by the pinned SNAP graph. Zero/nonfinite gamma0 and "
            "layover/shadow cells are unsupported, never dry labels."
        ),
    }


def build_adaptive_otsu_candidate(
    *,
    pre_vv_db: str | Path,
    pre_vh_db: str | Path,
    post_vv_db: str | Path,
    post_vh_db: str | Path,
    pre_layover_shadow: str | Path,
    post_layover_shadow: str | Path,
    permanent_water: str | Path,
    terrain_slope_degrees: str | Path,
    pre_processing_manifest: str | Path,
    post_processing_manifest: str | Path,
    context_alignment_manifest: str | Path,
    pre_observed_at_utc: str,
    post_observed_at_utc: str,
    event_id: str,
    study_area_id: str,
    output_directory: str | Path,
    config: AdaptiveOtsuConfig | None = None,
) -> Path:
    """Write a byte-bound, non-operational threshold candidate from aligned RTC rasters.

    Every input must be a single-band canonical 10 m EPSG:32647 GeoTIFF with the
    same grid-contract tag. Permanent water is binary (0/1), and the terrain
    raster is slope in degrees. Unknown context, layover/shadow, and invalid SAR
    are unsupported; permanent water, steep terrain, and failed histogram QC
    abstain. No output represents flood probability or accepted flood truth.
    """

    from contextlib import ExitStack

    import numpy as np
    import rasterio

    started = time.perf_counter()
    parameters = config or AdaptiveOtsuConfig()
    event = _canonical_identifier(event_id, "event_id")
    area = _canonical_identifier(study_area_id, "study_area_id")
    pre_time = _parse_utc_timestamp(pre_observed_at_utc, "pre_observed_at_utc")
    post_time = _parse_utc_timestamp(post_observed_at_utc, "post_observed_at_utc")
    if pre_time >= post_time:
        raise Sentinel1ProcessingError("Post observation must follow pre observation.")
    source_paths = {
        "pre_vv_db": _required_file(pre_vv_db, "pre VV Gamma0 dB raster"),
        "pre_vh_db": _required_file(pre_vh_db, "pre VH Gamma0 dB raster"),
        "post_vv_db": _required_file(post_vv_db, "post VV Gamma0 dB raster"),
        "post_vh_db": _required_file(post_vh_db, "post VH Gamma0 dB raster"),
        "pre_layover_shadow": _required_file(pre_layover_shadow, "pre layover/shadow mask"),
        "post_layover_shadow": _required_file(post_layover_shadow, "post layover/shadow mask"),
        "permanent_water": _required_file(permanent_water, "permanent-water mask"),
        "terrain_slope_degrees": _required_file(
            terrain_slope_degrees, "terrain slope raster"
        ),
    }
    manifest_paths = {
        "pre_processing_manifest": _required_file(
            pre_processing_manifest, "pre processing manifest"
        ),
        "post_processing_manifest": _required_file(
            post_processing_manifest, "post processing manifest"
        ),
        "context_alignment_manifest": _required_file(
            context_alignment_manifest, "context alignment manifest"
        ),
    }
    target = Path(output_directory)
    if target.exists():
        raise Sentinel1ProcessingError(f"Candidate output is immutable: {target}")
    all_input_paths = {**source_paths, **manifest_paths}
    if any(path.is_symlink() for path in all_input_paths.values()):
        raise Sentinel1ProcessingError("Candidate inputs must be regular files, not symlinks.")
    initial_input_hashes = {
        role: file_sha256(path) for role, path in all_input_paths.items()
    }

    with ExitStack() as stack:
        datasets = {
            role: stack.enter_context(rasterio.open(path))
            for role, path in source_paths.items()
        }
        reference = datasets["pre_vv_db"]
        if (
            reference.crs is None
            or reference.crs.to_string() != APPROVED_TARGET_CRS
            or not math.isclose(abs(reference.transform.a), APPROVED_RESOLUTION_M)
            or not math.isclose(abs(reference.transform.e), APPROVED_RESOLUTION_M)
            or reference.transform.b != 0
            or reference.transform.d != 0
            or reference.transform.e >= 0
        ):
            raise Sentinel1ProcessingError("Candidate rasters require the approved north-up 10 m grid.")
        if reference.width * reference.height > THRESHOLD_BASELINE_MAX_CELLS:
            raise Sentinel1ProcessingError("Candidate grid exceeds the declared 10 million-cell memory limit.")
        grid_hash = reference.tags().get("grid_contract_sha256", "")
        if _SHA256_PATTERN.fullmatch(grid_hash) is None:
            raise Sentinel1ProcessingError("Missing canonical grid-contract SHA-256 tag.")
        sar_roles = (
            "pre_vv_db", "pre_vh_db", "post_vv_db", "post_vh_db",
            "pre_layover_shadow", "post_layover_shadow",
        )
        for role, dataset in datasets.items():
            if (
                dataset.count != 1
                or dataset.crs != reference.crs
                or dataset.transform != reference.transform
                or dataset.width != reference.width
                or dataset.height != reference.height
            ):
                raise Sentinel1ProcessingError(f"{role} does not share the exact canonical grid.")
            if role in sar_roles and dataset.tags().get("grid_contract_sha256") != grid_hash:
                raise Sentinel1ProcessingError(f"{role} has a different SAR grid-contract tag.")
        context_grid_hash = datasets["permanent_water"].tags().get("TARGET_GRID_SHA256", "")
        if context_grid_hash:
            if (
                _SHA256_PATTERN.fullmatch(context_grid_hash) is None
                or datasets["terrain_slope_degrees"].tags().get("TARGET_GRID_SHA256")
                != context_grid_hash
                or datasets["permanent_water"].tags().get("LAYER_ROLE")
                != "permanent_water_context"
                or datasets["terrain_slope_degrees"].tags().get("LAYER_ROLE")
                != "slope"
            ):
                raise Sentinel1ProcessingError("Context rasters have inconsistent alignment tags.")
        elif any(
            datasets[role].tags().get("grid_contract_sha256") != grid_hash
            for role in ("permanent_water", "terrain_slope_degrees")
        ):
            raise Sentinel1ProcessingError("Context rasters have no verified common grid tag.")
        source_ids = {
            role: datasets[role].tags().get("source_product_id", "")
            for role in ("pre_vv_db", "pre_vh_db", "post_vv_db", "post_vh_db")
        }
        if (
            not source_ids["pre_vv_db"]
            or source_ids["pre_vv_db"] != source_ids["pre_vh_db"]
            or not source_ids["post_vv_db"]
            or source_ids["post_vv_db"] != source_ids["post_vh_db"]
            or source_ids["pre_vv_db"] == source_ids["post_vv_db"]
        ):
            raise Sentinel1ProcessingError("Pre/post VV/VH source-product identities are inconsistent.")
        _require_source_time(source_ids["pre_vv_db"], pre_time, "pre")
        _require_source_time(source_ids["post_vv_db"], post_time, "post")
        _verify_processing_manifest(
            manifest_paths["pre_processing_manifest"],
            grid_hash=grid_hash,
            source_product_id=source_ids["pre_vv_db"],
            raster_paths={
                "vv": source_paths["pre_vv_db"],
                "vh": source_paths["pre_vh_db"],
                "layover_shadow_mask": source_paths["pre_layover_shadow"],
            },
        )
        _verify_processing_manifest(
            manifest_paths["post_processing_manifest"],
            grid_hash=grid_hash,
            source_product_id=source_ids["post_vv_db"],
            raster_paths={
                "vv": source_paths["post_vv_db"],
                "vh": source_paths["post_vh_db"],
                "layover_shadow_mask": source_paths["post_layover_shadow"],
            },
        )
        _verify_context_manifest(
            manifest_paths["context_alignment_manifest"],
            context_grid_hash=context_grid_hash or grid_hash,
            raster_paths={
                "permanent_water_context": source_paths["permanent_water"],
                "slope": source_paths["terrain_slope_degrees"],
            },
        )

        arrays = {}
        for role, dataset in datasets.items():
            masked = dataset.read(1, masked=True)
            values = np.asarray(masked.data, dtype="float32").copy()
            values[np.ma.getmaskarray(masked)] = np.nan
            arrays[role] = values
        water = arrays["permanent_water"]
        water_known = np.isfinite(water) & np.isin(water, (0, 1))
        if np.any(np.isfinite(water) & ~water_known):
            raise Sentinel1ProcessingError("Permanent-water raster must use 0/1 and nodata only.")
        slope = arrays["terrain_slope_degrees"]
        slope_known = np.isfinite(slope) & (slope >= 0) & (slope < 90)
        if np.any(np.isfinite(slope) & ~slope_known):
            raise Sentinel1ProcessingError("Terrain slope must be in [0, 90) degrees.")
        radiometric_valid = np.ones(water.shape, dtype=bool)
        for role in ("pre_vv_db", "pre_vh_db", "post_vv_db", "post_vh_db"):
            radiometric_valid &= np.isfinite(arrays[role])
        geometry_clear = (
            arrays["pre_layover_shadow"] == 0
        ) & (arrays["post_layover_shadow"] == 0)
        supported = radiometric_valid & geometry_clear & water_known & slope_known
        water_abstain = supported & (water == 1)
        terrain_abstain = supported & ~water_abstain & (
            slope > parameters.max_terrain_slope_degrees
        )
        eligible = supported & ~water_abstain & ~terrain_abstain
        vv_change = arrays["pre_vv_db"] - arrays["post_vv_db"]
        vh_change = arrays["pre_vh_db"] - arrays["post_vh_db"]
        change = np.float32(0.4) * vv_change + np.float32(0.6) * vh_change
        threshold_sum = np.zeros(water.shape, dtype="float64")
        threshold_count = np.zeros(water.shape, dtype="uint16")
        window_receipts: list[dict[str, Any]] = []
        for row in _window_starts(reference.height, parameters.window_pixels, parameters.stride_pixels):
            row_end = min(row + parameters.window_pixels, reference.height)
            for column in _window_starts(
                reference.width, parameters.window_pixels, parameters.stride_pixels
            ):
                column_end = min(column + parameters.window_pixels, reference.width)
                window = np.s_[row:row_end, column:column_end]
                samples = change[window][eligible[window]]
                threshold, reason, qc = _otsu_threshold(samples, parameters)
                window_receipts.append(
                    {
                        "row": row,
                        "column": column,
                        "height": row_end - row,
                        "width": column_end - column,
                        "valid_samples": int(samples.size),
                        "threshold_db": threshold,
                        "status": "qualified_candidate_window" if threshold is not None else "abstained",
                        "reason": reason,
                        "qc": qc,
                    }
                )
                if threshold is not None:
                    window_sum = threshold_sum[window]
                    window_count = threshold_count[window]
                    window_sum[eligible[window]] += threshold
                    window_count[eligible[window]] += 1
        classified = eligible & (threshold_count > 0)
        threshold_surface = np.full(water.shape, CANONICAL_FLOAT_NODATA, dtype="float32")
        threshold_surface[classified] = (
            threshold_sum[classified] / threshold_count[classified]
        ).astype("float32")
        candidate = np.full(water.shape, CANONICAL_MASK_NODATA, dtype="uint8")
        candidate[classified] = (
            (change[classified] >= threshold_surface[classified])
            & (change[classified] > 0)
            & (vv_change[classified] > 0)
            & (vh_change[classified] > 0)
        ).astype("uint8")
        supported_mask = supported.astype("uint8")
        abstention = np.full(water.shape, CANONICAL_MASK_NODATA, dtype="uint8")
        abstention[supported] = 0
        abstention[water_abstain] = 1
        abstention[terrain_abstain] = 2
        abstention[eligible & ~classified] = 3
        change_output = np.full(water.shape, CANONICAL_FLOAT_NODATA, dtype="float32")
        change_output[supported] = change[supported]
        grid = TargetRasterGrid(
            crs=APPROVED_TARGET_CRS,
            left=float(reference.bounds.left),
            bottom=float(reference.bounds.bottom),
            right=float(reference.bounds.right),
            top=float(reference.bounds.top),
            resolution_m=APPROVED_RESOLUTION_M,
            grid_contract_sha256=grid_hash,
        )

    if any(
        file_sha256(path) != initial_input_hashes[role]
        for role, path in all_input_paths.items()
    ):
        raise Sentinel1ProcessingError("Candidate input bytes changed during processing.")
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    staged.mkdir()
    try:
        outputs = {}
        for name, values, nodata in (
            ("candidate_mask", candidate, CANONICAL_MASK_NODATA),
            ("supported_input_mask", supported_mask, CANONICAL_MASK_NODATA),
            ("abstention_code", abstention, CANONICAL_MASK_NODATA),
            ("change_db", change_output, CANONICAL_FLOAT_NODATA),
            ("threshold_db", threshold_surface, CANONICAL_FLOAT_NODATA),
        ):
            path = staged / f"{name}.tif"
            _write_candidate_geotiff(path, values, grid=grid, nodata=nodata, role=name)
            outputs[name] = {"file_name": path.name, "sha256": file_sha256(path)}
        cell_area_m2 = grid.resolution_m**2
        classified_cells = int(classified.sum())
        candidate_cells = int((candidate == 1).sum())
        receipt: dict[str, Any] = {
            "artifact_schema": THRESHOLD_BASELINE_SCHEMA,
            "event_id": event,
            "study_area_id": area,
            "pre_observed_at_utc": pre_time.isoformat().replace("+00:00", "Z"),
            "post_observed_at_utc": post_time.isoformat().replace("+00:00", "Z"),
            "source_product_ids": {
                "pre": source_ids["pre_vv_db"],
                "post": source_ids["post_vv_db"],
            },
            "grid_contract_sha256": grid.grid_contract_sha256,
            "context_target_grid_sha256": context_grid_hash or grid.grid_contract_sha256,
            "grid": {
                "crs": grid.crs,
                "transform": [float(value) for value in grid.transform[:6]],
                "width": grid.width,
                "height": grid.height,
                "cell_area_m2": cell_area_m2,
            },
            "method": "overlapping_window_otsu_gamma0_db_darkening_v1",
            "configuration": asdict(parameters),
            "seam_treatment": "arithmetic_mean_of_all_qualified_overlapping_window_thresholds",
            "input_files": {
                role: {"file_name": path.name, "sha256": initial_input_hashes[role]}
                for role, path in all_input_paths.items()
            },
            "outputs": outputs,
            "window_receipts": window_receipts,
            "counts": {
                "total_cells": int(candidate.size),
                "unsupported_cells": int((~supported).sum()),
                "permanent_water_abstained_cells": int(water_abstain.sum()),
                "terrain_abstained_cells": int(terrain_abstain.sum()),
                "histogram_abstained_cells": int((eligible & ~classified).sum()),
                "classified_non_candidate_cells": int((candidate == 0).sum()),
                "candidate_cells": candidate_cells,
            },
            "result_status": (
                "candidate_classification_available"
                if classified_cells
                else "abstained_no_classified_cells"
            ),
            "classified_grid_area_km2": round(
                classified_cells * cell_area_m2 / 1_000_000, 9
            ),
            "candidate_grid_area_km2": (
                round(candidate_cells * cell_area_m2 / 1_000_000, 9)
                if classified_cells
                else None
            ),
            "duration_seconds": round(time.perf_counter() - started, 6),
            "runtime_versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "rasterio": rasterio.__version__,
            },
            "estimated_peak_array_bytes": int(candidate.size * 64),
            "measured_peak_process_memory_bytes": None,
            "speckle_filter_applied": False,
            "radiometry": "SNAP terrain-flattened Gamma0, not Sigma0",
            "dataset_mode": "candidate",
            "operational_status": "non_operational",
            "official_warning": False,
            "can_feed_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "created_at_utc": _utc_now(),
        }
        write_processing_run_manifest(receipt, staged / "candidate_receipt.json")
        staged.replace(target)
    except Exception:
        for path in staged.iterdir():
            path.unlink()
        staged.rmdir()
        raise
    return target / "candidate_receipt.json"


def _window_starts(length: int, window: int, stride: int) -> list[int]:
    last = max(0, length - window)
    starts = list(range(0, last + 1, stride))
    if not starts or starts[-1] != last:
        starts.append(last)
    return starts


def _otsu_threshold(samples: object, config: AdaptiveOtsuConfig) -> tuple[float | None, str | None, dict[str, float]]:
    import numpy as np

    values = np.asarray(samples, dtype="float64")
    if values.size < config.min_valid_samples:
        return None, "insufficient_valid_support", {}
    lower, upper = np.quantile(values, (0.01, 0.99))
    if not np.isfinite(lower) or not np.isfinite(upper) or upper - lower < config.min_mean_separation_db:
        return None, "narrow_or_invalid_distribution", {}
    counts, edges = np.histogram(
        np.clip(values, lower, upper), bins=config.histogram_bins, range=(lower, upper)
    )
    centres = (edges[:-1] + edges[1:]) / 2
    cumulative_count = np.cumsum(counts)
    cumulative_sum = np.cumsum(counts * centres)
    total = cumulative_count[-1]
    lower_count = cumulative_count[:-1]
    upper_count = total - lower_count
    valid_split = (lower_count > 0) & (upper_count > 0)
    between = np.zeros(config.histogram_bins - 1, dtype="float64")
    low_mean = np.divide(cumulative_sum[:-1], lower_count, out=np.zeros_like(between), where=valid_split)
    high_mean = np.divide(
        cumulative_sum[-1] - cumulative_sum[:-1],
        upper_count,
        out=np.zeros_like(between),
        where=valid_split,
    )
    between[valid_split] = (
        (lower_count[valid_split] / total)
        * (upper_count[valid_split] / total)
        * (high_mean[valid_split] - low_mean[valid_split]) ** 2
    )
    split = int(np.argmax(between))
    threshold = float(edges[split + 1])
    low = values < threshold
    high = ~low
    if not low.any() or not high.any():
        return None, "empty_histogram_class", {}
    class_fraction = min(float(low.mean()), float(high.mean()))
    mean_separation = float(values[high].mean() - values[low].mean())
    variance = float(np.var(np.clip(values, lower, upper)))
    between_fraction = float(between[split] / variance) if variance > 0 else 0.0
    qc = {
        "class_fraction_min": round(class_fraction, 6),
        "mean_separation_db": round(mean_separation, 6),
        "between_variance_fraction": round(between_fraction, 6),
    }
    if class_fraction < config.min_class_fraction:
        return None, "unbalanced_histogram_classes", qc
    if mean_separation < config.min_mean_separation_db:
        return None, "weak_histogram_separation", qc
    if between_fraction < config.min_between_variance_fraction:
        return None, "unimodal_or_unstable_histogram", qc
    return round(threshold, 6), None, qc


def _write_candidate_geotiff(
    path: Path,
    values: object,
    *,
    grid: TargetRasterGrid,
    nodata: float,
    role: str,
) -> None:
    import numpy as np
    import rasterio

    array = np.asarray(values)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=grid.height,
        width=grid.width,
        count=1,
        dtype=str(array.dtype),
        crs=grid.crs,
        transform=grid.transform,
        nodata=nodata,
        compress="DEFLATE",
        predictor=2 if array.dtype.kind in {"u", "i"} else 3,
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dataset:
        dataset.write(array, 1)
        dataset.set_band_description(1, role)
        dataset.update_tags(
            artifact_schema=THRESHOLD_BASELINE_SCHEMA,
            grid_contract_sha256=grid.grid_contract_sha256,
            floodguard_role=role,
            dataset_mode="candidate",
            operational_status="non_operational",
            official_warning="false",
            can_feed_decision_layer="false",
        )


def _parse_utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Sentinel1ProcessingError(f"{label} must be an ISO UTC timestamp.") from exc
    if parsed.tzinfo != UTC:
        raise Sentinel1ProcessingError(f"{label} must use the UTC offset.")
    return parsed


def _require_source_time(source_product_id: str, observed_at_utc: datetime, role: str) -> None:
    match = re.search(r"_(\d{8}T\d{6})_", source_product_id)
    if match is None:
        raise Sentinel1ProcessingError(f"{role} source product has no parseable acquisition time.")
    source_time = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    if abs((observed_at_utc - source_time).total_seconds()) >= 2:
        raise Sentinel1ProcessingError(f"{role} observation time differs from source product ID.")


def _read_integrity_manifest(path: Path, schema: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Sentinel1ProcessingError(f"Invalid evidence manifest: {path.name}") from exc
    if not isinstance(payload, dict) or payload.get("artifact_schema") != schema:
        raise Sentinel1ProcessingError(f"Wrong evidence manifest schema: {path.name}")
    recorded = payload.get("manifest_sha256")
    body = {key: value for key, value in payload.items() if key != "manifest_sha256"}
    if recorded != _canonical_json_sha256(body):
        raise Sentinel1ProcessingError(f"Evidence manifest self-hash mismatch: {path.name}")
    return payload


def _verify_processing_manifest(
    path: Path,
    *,
    grid_hash: str,
    source_product_id: str,
    raster_paths: Mapping[str, Path],
) -> None:
    payload = _read_integrity_manifest(path, "floodguard.sentinel1_processing_run.v1")
    try:
        layers = payload["canonical_layers"]
        execution = payload["snap_execution"]
        if (
            layers["grid"]["grid_contract_sha256"] != grid_hash
            or layers["source_product_id"] != source_product_id
            or layers["query_model_only"] is not True
            or layers["eligible_for_decision_layer"] is not False
            or execution["snap_version"] != PINNED_SNAP_VERSION
            or "POEORB" not in execution["orbit_auxiliary_name"]
            or "_COG" in execution["source_product_name"].upper()
        ):
            raise Sentinel1ProcessingError(f"Processing lineage is not eligible: {path.name}")
        for role, raster_path in raster_paths.items():
            record = layers["outputs"][role]
            if (
                record["file_name"] != raster_path.name
                or record["sha256"] != file_sha256(raster_path)
            ):
                raise Sentinel1ProcessingError(
                    f"Processed {role} raster differs from its receipt: {path.name}"
                )
    except (KeyError, TypeError) as exc:
        raise Sentinel1ProcessingError(f"Incomplete processing manifest: {path.name}") from exc


def _verify_context_manifest(
    path: Path,
    *,
    context_grid_hash: str,
    raster_paths: Mapping[str, Path],
) -> None:
    payload = _read_integrity_manifest(path, "floodguard.context_alignment_manifest.v1")
    try:
        layers = {layer["layer_role"]: layer for layer in payload["layers"]}
        for role, raster_path in raster_paths.items():
            record = layers[role]
            if (
                record["path_hint"] != raster_path.name
                or record["target_grid_sha256"] != context_grid_hash
                or record["processed_layer_sha256"] != file_sha256(raster_path)
            ):
                raise Sentinel1ProcessingError(
                    f"Context {role} raster differs from its receipt: {path.name}"
                )
    except (KeyError, TypeError) as exc:
        raise Sentinel1ProcessingError(f"Incomplete context manifest: {path.name}") from exc


def write_processing_run_manifest(payload: Mapping[str, Any], path: str | Path) -> Path:
    """Write one self-hashed, immutable processing-run JSON."""

    target = Path(path)
    if target.suffix.lower() != ".json":
        raise Sentinel1ProcessingError("Processing-run manifest must use .json.")
    body = dict(payload)
    body.pop("manifest_sha256", None)
    body["manifest_sha256"] = _canonical_json_sha256(body)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(body, handle, ensure_ascii=True, sort_keys=True, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise Sentinel1ProcessingError(
            f"Processing-run manifest is immutable and already exists: {target}"
        ) from exc
    return target


def file_sha256(path: str | Path) -> str:
    """Return a streaming SHA-256 for a file without loading it into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_geotiff(
    path: Path,
    values: object,
    *,
    grid: TargetRasterGrid,
    nodata: float,
    role: str,
    source_product_id: str,
) -> None:
    import numpy as np
    import rasterio

    if path.exists():
        raise Sentinel1ProcessingError(f"Canonical output is immutable: {path}")
    array = np.asarray(values)
    if array.shape != (grid.height, grid.width):
        raise Sentinel1ProcessingError(f"Output {role} has the wrong array shape.")
    profile = {
        "driver": "GTiff",
        "height": grid.height,
        "width": grid.width,
        "count": 1,
        "dtype": str(array.dtype),
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": nodata,
        "compress": "DEFLATE",
        "predictor": 2 if array.dtype.kind in {"u", "i"} else 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
        "BIGTIFF": "IF_SAFER",
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(array, 1)
        dataset.set_band_description(1, role)
        dataset.update_tags(
            grid_contract_sha256=grid.grid_contract_sha256,
            floodguard_role=role,
            source_product_id=source_product_id,
            query_model_only="true",
            eligible_for_decision_layer="false",
            eligible_for_fpps="false",
            eligible_for_warning="false",
        )


def _output_record(path: Path, valid: object) -> dict[str, Any]:
    import numpy as np

    mask = np.asarray(valid, dtype=bool)
    return {
        "file_name": path.name,
        "sha256": file_sha256(path),
        "valid_cell_count": int(mask.sum()),
        "cell_count": int(mask.size),
        "valid_data_fraction": round(float(mask.mean()), 12),
    }


def _required_file(path: str | Path, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise Sentinel1ProcessingError(f"{label} does not exist: {candidate}")
    return candidate


def _resolve_source_product(path: str | Path) -> _ResolvedSourceProduct:
    """Resolve an archive/file or unpacked ``.SAFE`` directory for SNAP."""

    candidate = Path(path)
    if (
        candidate.is_file()
        and candidate.name.lower() == "manifest.safe"
        and candidate.parent.suffix.lower() == ".safe"
    ):
        candidate = candidate.parent
    if candidate.is_file():
        return _ResolvedSourceProduct(
            read_path=candidate,
            product_name=candidate.name,
            sha256=file_sha256(candidate),
            packaging="product_file",
            file_count=1,
        )
    if not candidate.is_dir():
        raise Sentinel1ProcessingError(
            f"Sentinel-1 source product does not exist: {candidate}"
        )
    if candidate.suffix.lower() != ".safe":
        raise Sentinel1ProcessingError(
            "An unpacked Sentinel-1 product must be a .SAFE directory."
        )
    manifest = candidate / "manifest.safe"
    _required_file(manifest, "unpacked SAFE manifest.safe")
    files = sorted(
        (item for item in candidate.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(candidate).as_posix(),
    )
    if any(item.is_symlink() for item in files):
        raise Sentinel1ProcessingError(
            "Unpacked SAFE products must not contain symbolic links."
        )
    return _ResolvedSourceProduct(
        read_path=manifest,
        product_name=candidate.name,
        sha256=_directory_tree_sha256(candidate, files),
        packaging="unpacked_safe_directory",
        file_count=len(files),
    )


def _directory_tree_sha256(root: Path, files: list[Path]) -> str:
    """Hash relative paths, sizes, and bytes for one unpacked SAFE tree."""

    digest = hashlib.sha256(b"floodguard.safe_tree_sha256.v1\0")
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        size = path.stat().st_size
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _find_unique_auxiliary_file(root: Path, file_name: str) -> Path:
    """Resolve one named SNAP auxiliary, tolerating zipped/unzipped orbit names."""

    if not root.is_dir():
        raise Sentinel1ProcessingError(f"SNAP auxiliary directory is missing: {root}")
    names = {file_name}
    if file_name.lower().endswith(".zip"):
        names.add(file_name[:-4])
    else:
        names.add(f"{file_name}.zip")
    matches = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name in names
    )
    if len(matches) != 1:
        raise Sentinel1ProcessingError(
            f"Expected exactly one local SNAP auxiliary for {file_name}; "
            f"found {len(matches)}."
        )
    return matches[0]


def _snap_version(gpt: Path) -> str:
    version_path = gpt.parent.parent / "VERSION.txt"
    if not version_path.is_file():
        raise Sentinel1ProcessingError(f"Missing pinned SNAP VERSION.txt: {version_path}")
    version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        raise Sentinel1ProcessingError("SNAP VERSION.txt is blank.")
    if version != PINNED_SNAP_VERSION:
        raise Sentinel1ProcessingError(
            f"SNAP version {version!r} is not the pinned {PINNED_SNAP_VERSION}."
        )
    return version


def _dimap_metadata_attribute(path: Path, name: str) -> str:
    """Return one required named metadata attribute from a DIMAP document."""

    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        raise Sentinel1ProcessingError(f"SNAP DIMAP XML is invalid: {path}") from exc
    element = root.find(f".//MDATTR[@name='{name}']")
    value = "" if element is None or element.text is None else element.text.strip()
    if not value:
        raise Sentinel1ProcessingError(
            f"SNAP DIMAP metadata is missing required attribute {name}."
        )
    return value


def _require_bounds_cover(
    bounds: tuple[float, float, float, float], grid: TargetRasterGrid
) -> None:
    tolerance = max(grid.resolution_m * 1e-6, 1e-6)
    left, bottom, right, top = bounds
    if (
        left > grid.left + tolerance
        or bottom > grid.bottom + tolerance
        or right < grid.right - tolerance
        or top < grid.top - tolerance
    ):
        raise Sentinel1ProcessingError(
            "SNAP RTC band does not cover the complete canonical target grid."
        )


def _exact_cell_count(span: float, resolution: float, label: str) -> int:
    count = span / resolution
    rounded = round(count)
    if rounded <= 0 or not math.isclose(count, rounded, abs_tol=1e-9):
        raise Sentinel1ProcessingError(
            f"Target {label} is not an exact integer number of cells."
        )
    return int(rounded)


def _require_grid_edge(coordinate: float, resolution: float, label: str) -> None:
    quotient = coordinate / resolution
    if not math.isclose(quotient, round(quotient), rel_tol=0.0, abs_tol=1e-8):
        raise Sentinel1ProcessingError(
            f"Target {label} must lie on the approved edge-origin grid."
        )


def _canonical_identifier(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized) is None:
        raise Sentinel1ProcessingError(f"{label} is not a canonical identifier.")
    return normalized


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
