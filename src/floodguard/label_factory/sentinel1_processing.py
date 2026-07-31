"""Version-pinned Sentinel-1 GRD processing for the label-factory data lane.

This module deliberately stops at calibrated, radiometrically terrain-flattened,
orthorectified evidence on a caller-declared grid.  It does not derive flood
labels, probabilities, FPPS inputs, or warning products.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping
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
    nodata: float | int,
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
