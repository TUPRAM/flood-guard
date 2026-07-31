"""Build byte-bound ``sar_change_v2`` cells from aligned Sentinel-1 rasters.

This module is deliberately downstream of SAR preprocessing.  It does not
calibrate, terrain-correct, resample, or co-register Sentinel-1 data.  Instead,
it requires four already calibrated dB rasters to prove that they share the
same canonical grid before extracting one deterministic feature row per query
cell.

No nodata value is imputed.  A canonical query containing an unsupported cell
blocks the build because silently replacing missing backscatter would create
model evidence that is not present in the source rasters.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from floodguard.label_factory.contracts import DatasetRole
from floodguard.label_factory.feature_schema import get_feature_schema
from floodguard.label_factory.manifests import QUERY_MANIFEST_COLUMNS


FEATURE_ARTIFACT_SCHEMA = "floodguard.sar_change_v2_features.v1"
FEATURE_SCHEMA_VERSION = "sar_change_v2"
FEATURE_CSV_FILENAME = "sar_change_v2_cells.csv"
FEATURE_MANIFEST_FILENAME = "sar_change_v2_derivation.json"
GRID_CONTRACT_TAG = "grid_contract_sha256"

RASTER_ROLES: tuple[str, ...] = (
    "pre_vv_db",
    "event_vv_db",
    "pre_vh_db",
    "event_vh_db",
)
FEATURE_COLUMNS: tuple[str, ...] = (
    "sample_id",
    "query_region_id",
    "cell_id",
    "grid_contract_sha256",
    "event_id",
    "tile_id",
    "source_registry_sha256",
    "processing_alignment_receipt_sha256",
    "row_index",
    "column_index",
    "spatial_group_id",
    "dataset_role",
    "feature_schema_version",
    *get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names,
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_WINDOW_TOLERANCE = 1e-7


class SarChangeFeatureError(ValueError):
    """Raised when raster, grid, query, or feature evidence fails closed."""


@dataclass(frozen=True, slots=True)
class SarChangeFeaturePaths:
    """Immutable artifacts written by one feature extraction."""

    feature_csv: Path
    derivation_manifest: Path

    def as_dict(self) -> dict[str, Path]:
        return {
            "feature_csv": self.feature_csv,
            "derivation_manifest": self.derivation_manifest,
        }


@dataclass(frozen=True, slots=True)
class VerifiedSarChangeFeatures:
    """Provenance returned after rechecking a feature artifact byte-for-byte."""

    grid_contract_sha256: str
    feature_csv_sha256: str
    derivation_manifest_sha256: str
    query_region_ids: tuple[str, ...]
    row_count: int


@dataclass(frozen=True, slots=True)
class _RasterSignature:
    crs_wkt: str
    transform: tuple[float, ...]
    width: int
    height: int
    nodata: float
    dtype: str
    grid_contract_sha256: str

    def as_manifest_fields(self) -> dict[str, object]:
        return {
            "crs_wkt": self.crs_wkt,
            "affine": list(self.transform),
            "width_pixels": self.width,
            "height_pixels": self.height,
            "nodata": _json_number(self.nodata),
            "dtype": self.dtype,
            "grid_contract_sha256": self.grid_contract_sha256,
        }


def build_sar_change_v2_features(
    *,
    pre_vv_path: str | Path,
    event_vv_path: str | Path,
    pre_vh_path: str | Path,
    event_vh_path: str | Path,
    query_manifest: pd.DataFrame | str | Path,
) -> pd.DataFrame:
    """Return deterministic, training-join-compatible per-cell features.

    All four rasters must be single-band GeoTIFFs on exactly the same affine,
    dimensions, CRS, nodata convention, dtype, and tagged grid contract.  The
    canonical queries must align exactly to that grid and may not overlap.
    """

    raster_paths = _coerce_raster_paths(
        pre_vv_db=pre_vv_path,
        event_vv_db=event_vv_path,
        pre_vh_db=pre_vh_path,
        event_vh_db=event_vh_path,
    )
    queries = _load_query_manifest(query_manifest)

    rasterio, windows = _load_rasterio()
    rows: list[dict[str, object]] = []
    with ExitStack() as stack:
        datasets = {
            role: stack.enter_context(rasterio.open(path))
            for role, path in raster_paths.items()
        }
        signature = _validate_raster_contract(datasets, queries)
        canonical_crs = next(iter(datasets.values())).crs
        query_windows = _validate_queries_and_windows(
            queries,
            transform=next(iter(datasets.values())).transform,
            raster_width=signature.width,
            raster_height=signature.height,
            raster_crs=canonical_crs,
            windows=windows,
        )
        query_by_id = {
            str(row["query_region_id"]): row
            for row in queries.to_dict("records")
        }
        for query_id in sorted(query_by_id):
            query = query_by_id[query_id]
            window = query_windows[query_id]
            arrays: dict[str, np.ndarray] = {}
            invalid_counts: dict[str, int] = {}
            for role in RASTER_ROLES:
                masked = datasets[role].read(1, window=window, masked=True)
                values = np.asarray(masked.data, dtype=np.float64)
                invalid = np.ma.getmaskarray(masked) | ~np.isfinite(values)
                invalid_count = int(np.count_nonzero(invalid))
                if invalid_count:
                    invalid_counts[role] = invalid_count
                arrays[role] = values
            if invalid_counts:
                details = ", ".join(
                    f"{role}={count}" for role, count in sorted(invalid_counts.items())
                )
                raise SarChangeFeatureError(
                    f"Query {query_id!r} contains unsupported or non-finite source "
                    f"cells ({details}); nodata is never imputed."
                )

            size = _positive_integer(query["query_size_pixels"], "query_size_pixels")
            expected_shape = (size, size)
            for role, values in arrays.items():
                if values.shape != expected_shape:
                    raise SarChangeFeatureError(
                        f"Query {query_id!r} read {values.shape!r} from {role}; "
                        f"expected {expected_shape!r}."
                    )
            vv_change = arrays["pre_vv_db"] - arrays["event_vv_db"]
            vh_change = arrays["pre_vh_db"] - arrays["event_vh_db"]
            for row_index in range(size):
                for column_index in range(size):
                    cell_id = (
                        f"{query_id}_R{row_index:04d}_C{column_index:04d}"
                    )
                    rows.append(
                        {
                            "sample_id": cell_id,
                            "query_region_id": query_id,
                            "cell_id": cell_id,
                            "grid_contract_sha256": signature.grid_contract_sha256,
                            "event_id": str(query["event_id"]),
                            "tile_id": str(query["tile_id"]),
                            "source_registry_sha256": str(
                                query["source_registry_sha256"]
                            ).lower(),
                            "processing_alignment_receipt_sha256": str(
                                query["processing_alignment_receipt_sha256"]
                            ).lower(),
                            "row_index": row_index,
                            "column_index": column_index,
                            "spatial_group_id": str(query["overlap_group_id"]),
                            "dataset_role": str(query["dataset_role"]),
                            "feature_schema_version": FEATURE_SCHEMA_VERSION,
                            "pre_vv_db": float(arrays["pre_vv_db"][row_index, column_index]),
                            "event_vv_db": float(
                                arrays["event_vv_db"][row_index, column_index]
                            ),
                            "pre_vh_db": float(arrays["pre_vh_db"][row_index, column_index]),
                            "event_vh_db": float(
                                arrays["event_vh_db"][row_index, column_index]
                            ),
                            "vv_change_db": float(vv_change[row_index, column_index]),
                            "vh_change_db": float(vh_change[row_index, column_index]),
                            # This strict extractor emits a row only after all four
                            # source observations have proved valid.
                            "valid_data_fraction": 1.0,
                        }
                    )

    features = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    if features.empty:
        raise SarChangeFeatureError("Feature extraction produced no cells.")
    features = features.sort_values(
        ["query_region_id", "row_index", "column_index"], kind="stable"
    ).reset_index(drop=True)
    _validate_feature_frame(features)
    return features


def build_and_write_sar_change_v2_features(
    *,
    pre_vv_path: str | Path,
    event_vv_path: str | Path,
    pre_vh_path: str | Path,
    event_vh_path: str | Path,
    query_manifest_path: str | Path,
    output_directory: str | Path,
    created_at_utc: datetime | str | None = None,
) -> SarChangeFeaturePaths:
    """Build and atomically publish an immutable feature CSV and derivation."""

    output = Path(output_directory)
    if output.exists():
        raise SarChangeFeatureError(
            f"Output directory already exists and cannot be overwritten: {output}"
        )
    query_path = _existing_file(query_manifest_path, "canonical query manifest")
    raster_paths = _coerce_raster_paths(
        pre_vv_db=pre_vv_path,
        event_vv_db=event_vv_path,
        pre_vh_db=pre_vh_path,
        event_vh_db=event_vh_path,
    )
    source_hashes = {
        "query_manifest": _file_sha256(query_path),
        **{role: _file_sha256(path) for role, path in raster_paths.items()},
    }
    queries = _load_query_manifest(query_path)
    features = build_sar_change_v2_features(
        pre_vv_path=raster_paths["pre_vv_db"],
        event_vv_path=raster_paths["event_vv_db"],
        pre_vh_path=raster_paths["pre_vh_db"],
        event_vh_path=raster_paths["event_vh_db"],
        query_manifest=queries,
    )
    timestamp = _utc_timestamp(created_at_utc)
    raster_evidence = _raster_evidence(raster_paths)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        feature_path = temporary / FEATURE_CSV_FILENAME
        manifest_path = temporary / FEATURE_MANIFEST_FILENAME
        features.to_csv(
            feature_path,
            index=False,
            lineterminator="\n",
            float_format="%.17g",
        )
        feature_sha256 = _file_sha256(feature_path)
        manifest = _build_derivation_manifest(
            features,
            queries=queries,
            query_path=query_path,
            raster_paths=raster_paths,
            raster_evidence=raster_evidence,
            source_hashes=source_hashes,
            feature_sha256=feature_sha256,
            timestamp=timestamp,
        )
        manifest_path.write_text(_json_text(manifest), encoding="utf-8")

        observed_hashes = {
            "query_manifest": _file_sha256(query_path),
            **{role: _file_sha256(path) for role, path in raster_paths.items()},
        }
        if observed_hashes != source_hashes:
            raise SarChangeFeatureError(
                "A source raster or query manifest changed during feature extraction."
            )
        _verify_derivation_payload(manifest)
        if output.exists():
            raise SarChangeFeatureError(
                f"Output directory appeared during extraction and will not be overwritten: {output}"
            )
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return SarChangeFeaturePaths(
        feature_csv=output / FEATURE_CSV_FILENAME,
        derivation_manifest=output / FEATURE_MANIFEST_FILENAME,
    )


def verify_sar_change_v2_feature_artifact(
    *,
    feature_csv: str | Path,
    derivation_manifest_path: str | Path,
    query_manifest_path: str | Path,
    pre_vv_path: str | Path,
    event_vv_path: str | Path,
    pre_vh_path: str | Path,
    event_vh_path: str | Path,
) -> VerifiedSarChangeFeatures:
    """Recheck generated bytes and every declared authoritative source hash."""

    feature_path = _existing_file(feature_csv, "sar_change_v2 feature CSV")
    manifest_path = _existing_file(
        derivation_manifest_path, "sar_change_v2 derivation manifest"
    )
    query_path = _existing_file(query_manifest_path, "canonical query manifest")
    raster_paths = _coerce_raster_paths(
        pre_vv_db=pre_vv_path,
        event_vv_db=event_vv_path,
        pre_vh_db=pre_vh_path,
        event_vh_db=event_vh_path,
    )
    payload = _load_json_object(manifest_path, "sar_change_v2 derivation manifest")
    logical_sha256 = _verify_derivation_payload(payload)
    declared_sources = payload.get("sources")
    if not isinstance(declared_sources, Mapping):
        raise SarChangeFeatureError("Derivation sources must be an object.")
    query_source = declared_sources.get("query_manifest")
    if not isinstance(query_source, Mapping) or query_source.get(
        "file_sha256"
    ) != _file_sha256(query_path):
        raise SarChangeFeatureError(
            "Canonical query manifest does not match the derivation source hash."
        )
    raster_sources = declared_sources.get("rasters")
    if not isinstance(raster_sources, Mapping):
        raise SarChangeFeatureError("Derivation raster sources must be an object.")
    for role, path in raster_paths.items():
        source = raster_sources.get(role)
        if not isinstance(source, Mapping) or source.get("file_sha256") != _file_sha256(path):
            raise SarChangeFeatureError(
                f"Raster {role} does not match the derivation source hash."
            )
    output = payload.get("output")
    if not isinstance(output, Mapping):
        raise SarChangeFeatureError("Derivation output must be an object.")
    feature_sha256 = _file_sha256(feature_path)
    if output.get("feature_csv_sha256") != feature_sha256:
        raise SarChangeFeatureError("Feature CSV does not match its declared SHA-256.")
    frame = pd.read_csv(feature_path)
    _validate_feature_frame(frame)
    if int(output.get("row_count", -1)) != len(frame):
        raise SarChangeFeatureError("Feature CSV row count differs from the derivation.")
    query_ids = tuple(sorted(set(frame["query_region_id"].astype(str))))
    if list(query_ids) != output.get("query_region_ids"):
        raise SarChangeFeatureError(
            "Feature CSV query coverage differs from the derivation."
        )
    return VerifiedSarChangeFeatures(
        grid_contract_sha256=str(payload["grid_contract_sha256"]),
        feature_csv_sha256=feature_sha256,
        derivation_manifest_sha256=logical_sha256,
        query_region_ids=query_ids,
        row_count=len(frame),
    )


def _coerce_raster_paths(**paths: str | Path) -> dict[str, Path]:
    result = {
        role: _existing_file(value, role.replace("_", " ") + " raster")
        for role, value in paths.items()
    }
    if set(result) != set(RASTER_ROLES):
        raise SarChangeFeatureError(
            f"Raster roles must be exactly {list(RASTER_ROLES)!r}."
        )
    resolved = [path.resolve() for path in result.values()]
    if len(resolved) != len(set(resolved)):
        raise SarChangeFeatureError(
            "Pre/event VV/VH inputs must be four distinct raster files."
        )
    return result


def _load_query_manifest(source: pd.DataFrame | str | Path) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        frame = source.copy()
    else:
        path = _existing_file(source, "canonical query manifest")
        if path.suffix.lower() != ".csv":
            raise SarChangeFeatureError("Canonical query manifest must be CSV.")
        try:
            frame = pd.read_csv(path)
        except (OSError, UnicodeError, pd.errors.ParserError) as exc:
            raise SarChangeFeatureError(
                f"Could not read canonical query manifest: {exc}"
            ) from exc
    missing = [name for name in QUERY_MANIFEST_COLUMNS if name not in frame.columns]
    if missing:
        raise SarChangeFeatureError(
            "Canonical query manifest is missing columns: " + ", ".join(missing) + "."
        )
    if frame.empty:
        raise SarChangeFeatureError("Canonical query manifest must not be empty.")
    queries = frame.loc[:, QUERY_MANIFEST_COLUMNS].copy().fillna("")
    query_ids = [_identifier(value, "query_region_id") for value in queries["query_region_id"]]
    if len(query_ids) != len(set(query_ids)):
        raise SarChangeFeatureError("Canonical query_region_id values must be unique.")
    if not queries["feature_schema_version"].astype(str).eq(
        FEATURE_SCHEMA_VERSION
    ).all():
        raise SarChangeFeatureError(
            f"Every query must use feature_schema_version={FEATURE_SCHEMA_VERSION!r}."
        )
    grid_hashes = {
        _sha256(value, "grid_contract_sha256")
        for value in queries["grid_contract_sha256"]
    }
    if len(grid_hashes) != 1:
        raise SarChangeFeatureError(
            "One feature extraction cannot mix grid_contract_sha256 values."
        )
    for column in ("source_registry_sha256", "processing_alignment_receipt_sha256"):
        for value in queries[column]:
            _sha256(value, column)
    known_roles = {role.value for role in DatasetRole}
    roles = {str(value) for value in queries["dataset_role"]}
    unknown_roles = sorted(roles - known_roles)
    if unknown_roles:
        raise SarChangeFeatureError(
            f"Canonical query manifest contains unknown dataset roles: {unknown_roles}."
        )
    for column in ("event_id", "tile_id", "grid_id", "overlap_group_id"):
        for value in queries[column]:
            _identifier(value, column)
    for column, expected in (
        ("query_model_only", True),
        ("eligible_for_decision_layer", False),
        ("eligible_for_fpps", False),
        ("eligible_for_warning", False),
    ):
        observed = [_boolean(value, column) for value in queries[column]]
        if any(value is not expected for value in observed):
            raise SarChangeFeatureError(
                f"Canonical query manifest must keep {column}={expected}."
            )
    return queries


def _validate_raster_contract(
    datasets: Mapping[str, Any], queries: pd.DataFrame
) -> _RasterSignature:
    expected_grid = _sha256(
        queries.iloc[0]["grid_contract_sha256"], "grid_contract_sha256"
    )
    signatures: dict[str, _RasterSignature] = {}
    for role in RASTER_ROLES:
        dataset = datasets[role]
        if dataset.count != 1:
            raise SarChangeFeatureError(
                f"Raster {role} must have exactly one band; found {dataset.count}."
            )
        if dataset.crs is None:
            raise SarChangeFeatureError(f"Raster {role} has no declared CRS.")
        if not dataset.crs.is_projected:
            raise SarChangeFeatureError(f"Raster {role} CRS must be projected.")
        transform = dataset.transform
        if not (
            transform.a > 0
            and transform.e < 0
            and transform.b == 0
            and transform.d == 0
        ):
            raise SarChangeFeatureError(
                f"Raster {role} must use a north-up, unrotated affine transform."
            )
        if dataset.nodata is None:
            raise SarChangeFeatureError(
                f"Raster {role} must declare an explicit nodata value."
            )
        grid_tag = _casefold_tag(dataset.tags(), GRID_CONTRACT_TAG)
        if grid_tag is None:
            raise SarChangeFeatureError(
                f"Raster {role} lacks required {GRID_CONTRACT_TAG!r} metadata."
            )
        normalized_tag = _sha256(grid_tag, f"{role} {GRID_CONTRACT_TAG}")
        if normalized_tag != expected_grid:
            raise SarChangeFeatureError(
                f"Raster {role} grid contract does not match the query manifest."
            )
        signatures[role] = _RasterSignature(
            crs_wkt=dataset.crs.to_wkt(),
            transform=tuple(float(value) for value in transform),
            width=int(dataset.width),
            height=int(dataset.height),
            nodata=float(dataset.nodata),
            dtype=str(dataset.dtypes[0]),
            grid_contract_sha256=normalized_tag,
        )
    reference = signatures[RASTER_ROLES[0]]
    for role in RASTER_ROLES[1:]:
        observed = signatures[role]
        mismatches: list[str] = []
        if observed.crs_wkt != reference.crs_wkt:
            mismatches.append("CRS")
        if observed.transform != reference.transform:
            mismatches.append("affine")
        if (observed.width, observed.height) != (reference.width, reference.height):
            mismatches.append("dimensions")
        if not _nodata_equal(observed.nodata, reference.nodata):
            mismatches.append("nodata")
        if observed.dtype != reference.dtype:
            mismatches.append("dtype")
        if observed.grid_contract_sha256 != reference.grid_contract_sha256:
            mismatches.append("grid identity")
        if mismatches:
            raise SarChangeFeatureError(
                f"Raster {role} does not match {RASTER_ROLES[0]} for: "
                + ", ".join(mismatches)
                + "."
            )
    return reference


def _validate_queries_and_windows(
    queries: pd.DataFrame,
    *,
    transform: Any,
    raster_width: int,
    raster_height: int,
    raster_crs: Any,
    windows: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    occupied_cells: dict[tuple[int, int], str] = {}
    for query in queries.to_dict("records"):
        query_id = str(query["query_region_id"])
        try:
            query_crs = raster_crs.from_user_input(str(query["crs"]))
        except Exception as exc:
            raise SarChangeFeatureError(
                f"Query {query_id!r} has invalid CRS {query['crs']!r}."
            ) from exc
        if query_crs != raster_crs:
            raise SarChangeFeatureError(
                f"Query {query_id!r} CRS does not match the source rasters."
            )
        resolution = _positive_float(query["resolution_m"], "resolution_m")
        if not math.isclose(resolution, float(transform.a), rel_tol=0, abs_tol=1e-9) or not math.isclose(
            resolution, abs(float(transform.e)), rel_tol=0, abs_tol=1e-9
        ):
            raise SarChangeFeatureError(
                f"Query {query_id!r} resolution does not match the raster affine."
            )
        size = _positive_integer(query["query_size_pixels"], "query_size_pixels")
        min_x = _finite_float(query["bbox_min_x"], "bbox_min_x")
        min_y = _finite_float(query["bbox_min_y"], "bbox_min_y")
        max_x = _finite_float(query["bbox_max_x"], "bbox_max_x")
        max_y = _finite_float(query["bbox_max_y"], "bbox_max_y")
        expected_span = size * resolution
        if not math.isclose(max_x - min_x, expected_span, rel_tol=0, abs_tol=1e-6) or not math.isclose(
            max_y - min_y, expected_span, rel_tol=0, abs_tol=1e-6
        ):
            raise SarChangeFeatureError(
                f"Query {query_id!r} bounds do not equal query_size_pixels * resolution_m."
            )
        raw_window = windows.from_bounds(
            min_x, min_y, max_x, max_y, transform=transform
        )
        offsets = (
            float(raw_window.row_off),
            float(raw_window.col_off),
            float(raw_window.height),
            float(raw_window.width),
        )
        rounded = tuple(round(value) for value in offsets)
        if any(
            not math.isclose(value, integer, rel_tol=0, abs_tol=_WINDOW_TOLERANCE)
            for value, integer in zip(offsets, rounded, strict=True)
        ):
            raise SarChangeFeatureError(
                f"Query {query_id!r} bounds are not aligned to integer raster cells."
            )
        row_off, col_off, height, width = (int(value) for value in rounded)
        if height != size or width != size:
            raise SarChangeFeatureError(
                f"Query {query_id!r} raster window is {height}x{width}; expected {size}x{size}."
            )
        if row_off < 0 or col_off < 0 or row_off + height > raster_height or col_off + width > raster_width:
            raise SarChangeFeatureError(
                f"Query {query_id!r} extends outside the source raster extent."
            )
        for raster_row in range(row_off, row_off + height):
            for raster_column in range(col_off, col_off + width):
                coordinate = (raster_row, raster_column)
                previous = occupied_cells.get(coordinate)
                if previous is not None:
                    raise SarChangeFeatureError(
                        f"Queries {previous!r} and {query_id!r} overlap raster cell "
                        f"{raster_row}/{raster_column}."
                    )
                occupied_cells[coordinate] = query_id
        result[query_id] = windows.Window(
            col_off=col_off,
            row_off=row_off,
            width=width,
            height=height,
        )
    return result


def _validate_feature_frame(frame: pd.DataFrame) -> None:
    missing = [name for name in FEATURE_COLUMNS if name not in frame.columns]
    if missing:
        raise SarChangeFeatureError(
            "sar_change_v2 feature CSV is missing columns: " + ", ".join(missing) + "."
        )
    if frame.empty:
        raise SarChangeFeatureError("sar_change_v2 feature CSV must not be empty.")
    if frame.duplicated(["query_region_id", "cell_id", "grid_contract_sha256"]).any():
        raise SarChangeFeatureError("Feature join keys must be unique.")
    if frame["cell_id"].astype(str).duplicated().any():
        raise SarChangeFeatureError("Feature cell_id values must be globally unique.")
    if not frame["sample_id"].astype(str).equals(frame["cell_id"].astype(str)):
        raise SarChangeFeatureError("Feature sample_id must equal canonical cell_id.")
    if not frame["feature_schema_version"].astype(str).eq(FEATURE_SCHEMA_VERSION).all():
        raise SarChangeFeatureError(
            f"Every feature row must use {FEATURE_SCHEMA_VERSION}."
        )
    model_columns = get_feature_schema(
        FEATURE_SCHEMA_VERSION
    ).required_feature_names
    for column in model_columns:
        try:
            values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise SarChangeFeatureError(
                f"Feature column {column!r} must be numeric."
            ) from exc
        if not np.isfinite(values).all():
            raise SarChangeFeatureError(
                f"Feature column {column!r} contains non-finite values."
            )
    valid_fraction = pd.to_numeric(
        frame["valid_data_fraction"], errors="raise"
    ).to_numpy(dtype=float)
    if not np.equal(valid_fraction, 1.0).all():
        raise SarChangeFeatureError(
            "Strict sar_change_v2 extraction requires valid_data_fraction=1.0."
        )


def _raster_evidence(raster_paths: Mapping[str, Path]) -> dict[str, dict[str, object]]:
    rasterio, _windows = _load_rasterio()
    evidence: dict[str, dict[str, object]] = {}
    for role, path in raster_paths.items():
        with rasterio.open(path) as dataset:
            grid_tag = _casefold_tag(dataset.tags(), GRID_CONTRACT_TAG)
            if grid_tag is None:
                raise SarChangeFeatureError(
                    f"Raster {role} lacks required {GRID_CONTRACT_TAG!r} metadata."
                )
            signature = _RasterSignature(
                crs_wkt=dataset.crs.to_wkt(),
                transform=tuple(float(value) for value in dataset.transform),
                width=int(dataset.width),
                height=int(dataset.height),
                nodata=float(dataset.nodata),
                dtype=str(dataset.dtypes[0]),
                grid_contract_sha256=_sha256(grid_tag, GRID_CONTRACT_TAG),
            )
            evidence[role] = signature.as_manifest_fields()
    return evidence


def _build_derivation_manifest(
    features: pd.DataFrame,
    *,
    queries: pd.DataFrame,
    query_path: Path,
    raster_paths: Mapping[str, Path],
    raster_evidence: Mapping[str, Mapping[str, object]],
    source_hashes: Mapping[str, str],
    feature_sha256: str,
    timestamp: str,
) -> dict[str, object]:
    grid_hash = _sha256(
        features.iloc[0]["grid_contract_sha256"], "grid_contract_sha256"
    )
    query_ids = sorted(set(features["query_region_id"].astype(str)))
    unsigned: dict[str, object] = {
        "artifact_schema": FEATURE_ARTIFACT_SCHEMA,
        "created_at_utc": timestamp,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_order": list(
            get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names
        ),
        "grid_contract_sha256": grid_hash,
        "cell_identity": (
            "query_region_id + zero-based query-local row/column; "
            "cell_id=<query>_R####_C####"
        ),
        "spatial_group_source": "canonical_query_manifest.overlap_group_id",
        "formulas": {
            "vv_change_db": "pre_vv_db - event_vv_db",
            "vh_change_db": "pre_vh_db - event_vh_db",
            "valid_data_fraction": (
                "1.0 only after all four source observations are valid; "
                "otherwise extraction blocks"
            ),
        },
        "sources": {
            "query_manifest": {
                "file": query_path.name,
                "file_sha256": source_hashes["query_manifest"],
                "row_count": len(queries),
                "query_region_ids": query_ids,
            },
            "rasters": {
                role: {
                    "file": raster_paths[role].name,
                    "file_sha256": source_hashes[role],
                    **dict(raster_evidence[role]),
                }
                for role in RASTER_ROLES
            },
        },
        "output": {
            "file": FEATURE_CSV_FILENAME,
            "feature_csv_sha256": feature_sha256,
            "row_count": len(features),
            "query_region_ids": query_ids,
            "columns": list(FEATURE_COLUMNS),
        },
        "safety": {
            "query_model_only": True,
            "eligible_for_decision_layer": False,
            "eligible_for_fpps": False,
            "eligible_for_warning": False,
            "allowed_output_use": "query_committee_features_only",
        },
        "assumptions": (
            "Inputs are calibrated dB GeoTIFFs produced by an independently "
            "verified SAR preprocessing/alignment workflow. This extractor "
            "does not prove calibration, terrain correction, co-registration, "
            "or flood truth."
        ),
    }
    unsigned["manifest_sha256"] = _canonical_sha256(unsigned)
    return unsigned


def _verify_derivation_payload(payload: Mapping[str, object]) -> str:
    if payload.get("artifact_schema") != FEATURE_ARTIFACT_SCHEMA:
        raise SarChangeFeatureError("Unknown sar_change_v2 derivation schema.")
    if payload.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise SarChangeFeatureError("Derivation is not sar_change_v2.")
    expected_order = list(
        get_feature_schema(FEATURE_SCHEMA_VERSION).required_feature_names
    )
    if payload.get("feature_order") != expected_order:
        raise SarChangeFeatureError("Derivation feature order is not canonical.")
    _sha256(payload.get("grid_contract_sha256"), "grid_contract_sha256")
    declared = _sha256(payload.get("manifest_sha256"), "manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    observed = _canonical_sha256(unsigned)
    if declared != observed:
        raise SarChangeFeatureError("Derivation manifest self-hash is invalid.")
    safety = payload.get("safety")
    if not isinstance(safety, Mapping) or safety != {
        "query_model_only": True,
        "eligible_for_decision_layer": False,
        "eligible_for_fpps": False,
        "eligible_for_warning": False,
        "allowed_output_use": "query_committee_features_only",
    }:
        raise SarChangeFeatureError("Derivation safety contract is invalid.")
    return observed


def _load_rasterio() -> tuple[Any, Any]:
    try:
        import rasterio
        from rasterio import windows
    except ImportError as exc:  # pragma: no cover - environment-specific guard
        raise SarChangeFeatureError(
            "Real-raster feature extraction requires rasterio; install the "
            "project's raster/geospatial dependencies."
        ) from exc
    return rasterio, windows


def _casefold_tag(tags: Mapping[str, str], target: str) -> str | None:
    matches = [value for key, value in tags.items() if key.casefold() == target.casefold()]
    if len(matches) > 1:
        raise SarChangeFeatureError(f"Raster contains duplicate {target!r} tags.")
    return matches[0] if matches else None


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise SarChangeFeatureError(f"{label} does not exist or is not a file: {path}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise SarChangeFeatureError(f"Could not hash {path.name}: {exc}") from exc
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SarChangeFeatureError(f"Could not read {label}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise SarChangeFeatureError(f"{label} must contain a JSON object.")
    return payload


def _sha256(value: object, label: str) -> str:
    text = str(value).strip().lower()
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise SarChangeFeatureError(f"{label} must be a complete lowercase SHA-256.")
    return text


def _identifier(value: object, label: str) -> str:
    text = str(value).strip()
    if _IDENTIFIER_PATTERN.fullmatch(text) is None:
        raise SarChangeFeatureError(
            f"{label} must use letters, digits, dot, underscore, colon, or hyphen."
        )
    return text


def _positive_integer(value: object, label: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SarChangeFeatureError(f"{label} must be a positive integer.") from exc
    if not math.isfinite(number) or not number.is_integer() or number <= 0:
        raise SarChangeFeatureError(f"{label} must be a positive integer.")
    return int(number)


def _positive_float(value: object, label: str) -> float:
    number = _finite_float(value, label)
    if number <= 0:
        raise SarChangeFeatureError(f"{label} must be greater than zero.")
    return number


def _finite_float(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SarChangeFeatureError(f"{label} must be finite.") from exc
    if not math.isfinite(number):
        raise SarChangeFeatureError(f"{label} must be finite.")
    return number


def _boolean(value: object, label: str) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise SarChangeFeatureError(f"{label} must be true or false.")


def _nodata_equal(left: float, right: float) -> bool:
    if math.isnan(left) and math.isnan(right):
        return True
    return left == right


def _json_number(value: float) -> float | str:
    return "NaN" if math.isnan(value) else value


def _utc_timestamp(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(UTC)
    elif isinstance(value, datetime):
        timestamp = value
    else:
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise SarChangeFeatureError(
                "created_at_utc must be a valid timezone-aware ISO-8601 timestamp."
            ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise SarChangeFeatureError("created_at_utc must be timezone-aware.")
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
