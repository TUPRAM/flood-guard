"""Real Sentinel-1 raster extraction for weak-reference candidate baselines."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import hmac
import math
from pathlib import Path
import sqlite3
import struct
import zipfile

import pandas as pd

from floodguard.ingestion import (
    MAE_SAI_BASELINE_POST_PRODUCT_ID,
    MAE_SAI_BASELINE_PRE_PRODUCT_ID,
)

DEFAULT_EXTERNAL_DATA_DIR = Path.home() / "Documents" / "FloodGuard_external_data"
DEFAULT_OUTPUT_SHAPE: tuple[int, int] = (256, 256)
SAR_MEASUREMENT_DOMAIN = "sentinel1_uncalibrated_amplitude"
SAR_LOG_TRANSFORM = "20_log10_amplitude"
SAR_RADIOMETRIC_CALIBRATION_STATUS = "not_sigma0_beta0_or_gamma0_calibrated"

SAR_FEATURE_COLUMNS: tuple[str, ...] = (
    "pixel_id",
    "row",
    "col",
    "pre_vv_db",
    "post_vv_db",
    "pre_vh_db",
    "post_vh_db",
    "vv_drop",
    "vh_drop",
    "vv_ratio",
    "vh_ratio",
    "combined_sar_change_score",
    "flood_probability_0_1",
    "binary_flood_extent",
    "reference_flood_extent",
)

SAR_FEATURE_MANIFEST_COLUMNS: tuple[str, ...] = (
    "study_area",
    "processing_scope",
    "pre_product_id",
    "post_product_id",
    "pre_source_name",
    "post_source_name",
    "reference_product_id",
    "reference_status",
    "pre_source_sha256",
    "post_source_sha256",
    "reference_sha256",
    "source_integrity_status",
    "measurement_domain",
    "log_transform",
    "radiometric_calibration_status",
    "reference_spatial_relation",
    "reference_in_study_area_overlap",
    "reference_distance_to_study_area_km",
    "sample_pixel_count",
    "reference_positive_pixel_count",
    "predicted_positive_pixel_count",
    "sample_width",
    "sample_height",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "window_strategy",
    "georeferencing_method",
    "probability_threshold",
    "dry_change_db",
    "flood_change_db",
    "mean_combined_sar_change_score",
    "mean_flood_probability_0_1",
    "source_timestamp",
    "confidence_class",
    "assumptions",
)

SAR_CONTEXT_SUMMARY_COLUMNS: tuple[str, ...] = (
    "subdistrict_id",
    "subdistrict_name",
    "mean_flood_probability_0_1",
    "p90_flood_probability_0_1",
    "binary_flood_share_0_1",
    "mean_combined_sar_change_score",
    "sample_pixel_count",
    "source_timestamp",
    "confidence_class",
    "processing_scope",
    "assumptions",
)


class SARRasterExtractError(ValueError):
    """Raised when real Sentinel-1 weak-reference extraction is blocked."""


@dataclass(frozen=True)
class SARRasterInputs:
    """External raster paths and reference mask inputs for extraction."""

    pre_vv_uri: str
    pre_vh_uri: str
    post_vv_uri: str
    post_vh_uri: str
    reference_geometries: tuple[dict[str, object], ...]
    reference_crs: str = "EPSG:4326"
    pre_source_sha256: str = ""
    post_source_sha256: str = ""
    reference_sha256: str = ""
    source_integrity_status: str = "unverified"
    reference_spatial_relation: str = "unverified"
    reference_in_study_area_overlap: bool | None = None
    reference_distance_to_study_area_km: float | None = None


@dataclass(frozen=True)
class SARChangeArrays:
    """Aligned Sentinel-1 change arrays for one geographic window."""

    pre_vv_db: object
    post_vv_db: object
    pre_vh_db: object
    post_vh_db: object
    vv_drop: object
    vh_drop: object
    vv_ratio: object
    vh_ratio: object
    combined: object
    probability: object
    binary: object
    valid: object
    transform: object
    georeferencing_method: str


def resolve_external_path_hint(
    path_hint: str,
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
) -> Path:
    """Resolve a redacted external-data path hint into a local path."""

    normalized = str(path_hint).strip()
    if not normalized or normalized in {"not_acquired", "unknown", "not_selected"}:
        raise SARRasterExtractError(f"External path hint is unresolved: {path_hint}")
    if normalized.startswith("<external_data_workspace>/"):
        suffix = normalized.removeprefix("<external_data_workspace>/")
        return Path(external_data_dir) / Path(suffix)
    return Path(normalized)


def build_sentinel1_safe_band_uri(zip_path: str | Path, polarization: str) -> str:
    """Build an explicit uncalibrated-amplitude GDAL SAFE subdataset URI."""

    zip_file = Path(zip_path)
    if not zip_file.exists():
        raise SARRasterExtractError(f"Sentinel-1 ZIP does not exist: {zip_file}")
    pol = polarization.upper()
    if pol not in {"VV", "VH"}:
        raise SARRasterExtractError("Sentinel-1 polarization must be VV or VH.")
    with zipfile.ZipFile(zip_file) as archive:
        manifest_members = [
            name for name in archive.namelist() if name.lower().endswith("/manifest.safe")
        ]
    if len(manifest_members) != 1:
        raise SARRasterExtractError(
            f"Expected exactly one manifest.safe in {zip_file.name}, found {len(manifest_members)}."
        )
    return (
        f"SENTINEL1_CALIB:UNCALIB:/vsizip/{zip_file.as_posix()}/"
        f"{manifest_members[0]}:IW_{pol}:AMPLITUDE"
    )


def build_sentinel1_inputs_from_manifests(
    file_manifest: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
    reference_path: str | Path | None = None,
) -> SARRasterInputs:
    """Build raster input URIs from the committed metadata manifests."""

    _require_columns(
        file_manifest,
        (
            "source_name",
            "candidate_use",
            "product_id",
            "local_path",
            "sha256",
            "source_license_status",
        ),
        "Mae Sai file manifest",
    )
    _require_columns(
        manual_reference_manifest,
        (
            "reference_id",
            "local_path_hint",
            "sha256",
            "sha256_status",
            "candidate_validation_metrics_allowed",
            "reference_mask_status",
            "spatial_relation",
            "in_study_area_overlap",
            "distance_to_study_area_km",
            "spatial_relation_status",
        ),
        "manual reference manifest",
    )
    if manual_reference_manifest.empty:
        raise SARRasterExtractError("Manual reference manifest has no rows.")
    manual_row = manual_reference_manifest.iloc[0]
    if str(manual_row["candidate_validation_metrics_allowed"]).lower() != "true":
        raise SARRasterExtractError(
            "Manual reference mask is not ready for candidate metrics."
        )
    if str(manual_row["spatial_relation_status"]) != "verified_geometry_intersection":
        raise SARRasterExtractError(
            "Manual reference spatial relation is not verified."
        )
    if str(manual_row["spatial_relation"]) != "cross_border_calibration_only":
        raise SARRasterExtractError(
            "This weak-reference lane requires cross-border calibration-only status."
        )
    if str(manual_row["in_study_area_overlap"]).strip().lower() not in {
        "false",
        "0",
        "no",
    }:
        raise SARRasterExtractError(
            "Cross-border weak reference must record in-study-area overlap as false."
        )
    try:
        reference_distance_km = float(manual_row["distance_to_study_area_km"])
    except (TypeError, ValueError) as exc:
        raise SARRasterExtractError(
            "Cross-border weak reference distance is not recorded."
        ) from exc
    if reference_distance_km <= 0:
        raise SARRasterExtractError(
            "Cross-border weak reference distance must be greater than zero."
        )

    pre_row = _select_manifest_row(
        file_manifest,
        "pre-event SAR source for non-ML baseline",
    )
    post_row = _select_manifest_row(
        file_manifest,
        "post-event SAR source for non-ML baseline",
    )
    _require_approved_mae_sai_baseline_pair(pre_row, post_row)
    for row in (pre_row, post_row):
        if str(row["source_license_status"]) != "confirmed":
            raise SARRasterExtractError(
                f"Sentinel-1 source license is not confirmed for {row['source_name']}."
            )
        if not _valid_sha256(str(row["sha256"])):
            raise SARRasterExtractError(
                f"Sentinel-1 source checksum is not recorded for {row['source_name']}."
            )

    pre_zip = resolve_external_path_hint(
        str(pre_row["local_path"]),
        external_data_dir=external_data_dir,
    )
    post_zip = resolve_external_path_hint(
        str(post_row["local_path"]),
        external_data_dir=external_data_dir,
    )
    ref_path = Path(reference_path) if reference_path is not None else resolve_external_path_hint(
        str(manual_row["local_path_hint"]),
        external_data_dir=external_data_dir,
    )
    if str(manual_row["sha256_status"]) != "recorded":
        raise SARRasterExtractError(
            "Manual reference checksum status is not recorded; raster reads are blocked."
        )

    # Validate immutable inputs before opening SAFE content through GDAL or
    # querying the reference GeoPackage. This detects both substitution and
    # archives changed by PAM sidecar insertion.
    pre_sha256 = _verify_file_sha256(
        pre_zip,
        str(pre_row["sha256"]),
        label=f"pre-event Sentinel-1 source {pre_row['source_name']}",
    )
    post_sha256 = _verify_file_sha256(
        post_zip,
        str(post_row["sha256"]),
        label=f"post-event Sentinel-1 source {post_row['source_name']}",
    )
    reference_sha256 = _verify_file_sha256(
        ref_path,
        str(manual_row["sha256"]),
        label=f"manual reference {manual_row['reference_id']}",
    )
    geometries, reference_crs = read_manual_reference_geometries(ref_path)
    return SARRasterInputs(
        pre_vv_uri=build_sentinel1_safe_band_uri(pre_zip, "VV"),
        pre_vh_uri=build_sentinel1_safe_band_uri(pre_zip, "VH"),
        post_vv_uri=build_sentinel1_safe_band_uri(post_zip, "VV"),
        post_vh_uri=build_sentinel1_safe_band_uri(post_zip, "VH"),
        reference_geometries=tuple(geometries),
        reference_crs=reference_crs,
        pre_source_sha256=pre_sha256,
        post_source_sha256=post_sha256,
        reference_sha256=reference_sha256,
        source_integrity_status="verified_sha256_before_raster_read",
        reference_spatial_relation="cross_border_calibration_only",
        reference_in_study_area_overlap=False,
        reference_distance_to_study_area_km=reference_distance_km,
    )


def read_manual_reference_geometries(
    reference_path: str | Path,
    *,
    layer_name: str = "manual_flood_extent",
) -> tuple[list[dict[str, object]], str]:
    """Read GeoJSON-like geometries from the manual reference GeoPackage."""

    path = Path(reference_path)
    if not path.exists():
        raise SARRasterExtractError(f"Manual reference mask does not exist: {path}")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        geometry_row = connection.execute(
            """
            SELECT column_name, srs_id
            FROM gpkg_geometry_columns
            WHERE table_name = ?
            """,
            (layer_name,),
        ).fetchone()
        if geometry_row is None:
            raise SARRasterExtractError(f"GeoPackage layer not found: {layer_name}")
        geometry_column, srs_id = geometry_row
        quoted_layer = _quote_identifier(layer_name)
        quoted_geometry = _quote_identifier(str(geometry_column))
        rows = connection.execute(
            f"SELECT {quoted_geometry} FROM {quoted_layer}"
        ).fetchall()
        crs = _crs_summary(connection, int(srs_id))
    geometries = [_parse_geopackage_geometry(row[0]) for row in rows if row[0] is not None]
    if not geometries:
        raise SARRasterExtractError("Manual reference layer has no geometries.")
    return geometries, crs


def extract_sar_change_features(
    inputs: SARRasterInputs,
    *,
    output_shape: tuple[int, int] = DEFAULT_OUTPUT_SHAPE,
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
    buffer_degrees: float = 0.0025,
) -> pd.DataFrame:
    """Extract a weak-reference SAR change feature table from external rasters."""

    if flood_change_db <= dry_change_db:
        raise SARRasterExtractError("flood_change_db must be greater than dry_change_db.")
    if not 0 <= probability_threshold <= 1:
        raise SARRasterExtractError("probability_threshold must be between 0 and 1.")
    if output_shape[0] <= 0 or output_shape[1] <= 0:
        raise SARRasterExtractError("output_shape dimensions must be positive.")

    reference_geometries = _validated_polygon_geometries(
        inputs.reference_geometries,
        label="manual reference geometry",
    )
    import numpy as np
    from rasterio.features import rasterize

    bbox = _geometry_bounds(reference_geometries, buffer_degrees=buffer_degrees)
    arrays = _read_sar_change_arrays(
        inputs,
        bbox,
        output_shape=output_shape,
        probability_threshold=probability_threshold,
        dry_change_db=dry_change_db,
        flood_change_db=flood_change_db,
    )
    sample_height, sample_width = output_shape
    reference_mask = rasterize(
        [(geometry, 1) for geometry in reference_geometries],
        out_shape=output_shape,
        transform=arrays.transform,
        fill=0,
        all_touched=True,
        dtype="uint8",
    )

    if not bool(arrays.valid.any()):
        raise SARRasterExtractError("No valid SAR pixels were extracted.")
    if int(reference_mask.sum()) <= 0:
        raise SARRasterExtractError(
            "Manual weak-reference geometry did not overlap the extracted SAR sample."
        )

    rows, cols = np.indices(output_shape)
    frame = pd.DataFrame(
        {
            "pixel_id": [
                f"MS-WEAK-{idx:06d}" for idx in range(1, sample_height * sample_width + 1)
            ],
            "row": rows.reshape(-1),
            "col": cols.reshape(-1),
            "pre_vv_db": arrays.pre_vv_db.reshape(-1),
            "post_vv_db": arrays.post_vv_db.reshape(-1),
            "pre_vh_db": arrays.pre_vh_db.reshape(-1),
            "post_vh_db": arrays.post_vh_db.reshape(-1),
            "vv_drop": arrays.vv_drop.reshape(-1),
            "vh_drop": arrays.vh_drop.reshape(-1),
            "vv_ratio": arrays.vv_ratio.reshape(-1),
            "vh_ratio": arrays.vh_ratio.reshape(-1),
            "combined_sar_change_score": arrays.combined.reshape(-1),
            "flood_probability_0_1": arrays.probability.reshape(-1),
            "binary_flood_extent": arrays.binary.reshape(-1),
            "reference_flood_extent": reference_mask.reshape(-1),
            "_valid": arrays.valid.reshape(-1),
        }
    )
    frame = frame[frame["_valid"]].drop(columns=["_valid"]).reset_index(drop=True)
    numeric_columns = [
        "pre_vv_db",
        "post_vv_db",
        "pre_vh_db",
        "post_vh_db",
        "vv_drop",
        "vh_drop",
        "vv_ratio",
        "vh_ratio",
        "combined_sar_change_score",
        "flood_probability_0_1",
    ]
    frame[numeric_columns] = frame[numeric_columns].round(6)
    frame["binary_flood_extent"] = frame["binary_flood_extent"].astype(int)
    frame["reference_flood_extent"] = frame["reference_flood_extent"].astype(int)
    frame.attrs["bbox"] = bbox
    frame.attrs["sample_width"] = sample_width
    frame.attrs["sample_height"] = sample_height
    frame.attrs["georeferencing_method"] = arrays.georeferencing_method
    return frame.loc[:, SAR_FEATURE_COLUMNS]


def summarize_sar_probability_by_geometries(
    inputs: SARRasterInputs,
    features: Sequence[Mapping[str, object]],
    *,
    id_property: str = "subdistrict_id",
    name_property: str = "subdistrict_name",
    output_shape: tuple[int, int] = (128, 128),
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
    source_timestamp: str = "2024-09-15T23:16:01Z",
) -> pd.DataFrame:
    """Summarize Sentinel-1 change probabilities inside reporting polygons.

    Reporting polygons are spatial aggregation units only. They are never
    rasterized as flood labels or used to compute validation metrics.
    """

    import numpy as np
    from rasterio.features import rasterize

    if not features:
        raise SARRasterExtractError("At least one reporting geometry is required.")
    if output_shape[0] <= 0 or output_shape[1] <= 0:
        raise SARRasterExtractError("output_shape dimensions must be positive.")

    rows: list[dict[str, object]] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise SARRasterExtractError(
                f"Reporting feature {index} must contain properties and geometry."
            )
        subdistrict_id = str(properties.get(id_property, "")).strip()
        subdistrict_name = str(properties.get(name_property, "")).strip()
        if not subdistrict_id or not subdistrict_name:
            raise SARRasterExtractError(
                f"Reporting feature {index} is missing {id_property} or {name_property}."
            )
        geometry_dict = dict(geometry)
        validated_geometries = _validated_polygon_geometries(
            (geometry_dict,),
            label=f"reporting geometry {subdistrict_id}",
        )
        geometry_dict = validated_geometries[0]
        bbox = _geometry_bounds(validated_geometries, buffer_degrees=0.0)
        arrays = _read_sar_change_arrays(
            inputs,
            bbox,
            output_shape=output_shape,
            probability_threshold=probability_threshold,
            dry_change_db=dry_change_db,
            flood_change_db=flood_change_db,
        )
        polygon_mask = rasterize(
            [(geometry_dict, 1)],
            out_shape=output_shape,
            transform=arrays.transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
        selected = polygon_mask & arrays.valid
        if not bool(selected.any()):
            raise SARRasterExtractError(
                f"No valid SAR pixels overlap reporting unit {subdistrict_id}."
            )
        probabilities = arrays.probability[selected]
        combined = arrays.combined[selected]
        binary = arrays.binary[selected]
        rows.append(
            {
                "subdistrict_id": subdistrict_id,
                "subdistrict_name": subdistrict_name,
                "mean_flood_probability_0_1": round(float(np.mean(probabilities)), 6),
                "p90_flood_probability_0_1": round(
                    float(np.percentile(probabilities, 90)), 6
                ),
                "binary_flood_share_0_1": round(float(np.mean(binary)), 6),
                "mean_combined_sar_change_score": round(float(np.mean(combined)), 6),
                "sample_pixel_count": int(selected.sum()),
                "source_timestamp": source_timestamp,
                "confidence_class": "low",
                "processing_scope": "real_sentinel1_adm3_candidate_context",
                "assumptions": (
                    "Real CDSE Sentinel-1 pre/post change summarized inside COD-AB "
                    "ADM3 geometry. The manual weak-reference mask is a nearby "
                    "cross-border calibration candidate, not the aggregation geometry. "
                    "Non-operational and not official validation."
                ),
            }
        )
    return pd.DataFrame(rows, columns=SAR_CONTEXT_SUMMARY_COLUMNS)


def build_sar_feature_manifest(
    features: pd.DataFrame,
    *,
    file_manifest: pd.DataFrame,
    manual_reference_manifest: pd.DataFrame,
    verified_inputs: SARRasterInputs,
    probability_threshold: float = 0.5,
    dry_change_db: float = 0.5,
    flood_change_db: float = 4.0,
    source_timestamp: str = "2024-09-15T23:16:01Z",
) -> pd.DataFrame:
    """Build a compact manifest for the extracted weak-reference feature sample."""

    _require_columns(features, SAR_FEATURE_COLUMNS, "SAR feature table")
    bbox = tuple(features.attrs.get("bbox", ("", "", "", "")))
    if len(bbox) != 4:
        bbox = ("", "", "", "")
    pre = _select_manifest_row(file_manifest, "pre-event SAR source for non-ML baseline")
    post = _select_manifest_row(file_manifest, "post-event SAR source for non-ML baseline")
    reference = manual_reference_manifest.iloc[0]
    _require_verified_input_lineage(verified_inputs)
    row = {
        "study_area": "Chiang Rai / Mae Sai 2024",
        "processing_scope": "weak_reference_real_sentinel1_non_ml_candidate",
        "pre_product_id": pre["product_id"],
        "post_product_id": post["product_id"],
        "pre_source_name": pre["source_name"],
        "post_source_name": post["source_name"],
        "reference_product_id": reference["reference_id"],
        "reference_status": reference["reference_mask_status"],
        "pre_source_sha256": verified_inputs.pre_source_sha256,
        "post_source_sha256": verified_inputs.post_source_sha256,
        "reference_sha256": verified_inputs.reference_sha256,
        "source_integrity_status": verified_inputs.source_integrity_status,
        "measurement_domain": SAR_MEASUREMENT_DOMAIN,
        "log_transform": SAR_LOG_TRANSFORM,
        "radiometric_calibration_status": SAR_RADIOMETRIC_CALIBRATION_STATUS,
        "reference_spatial_relation": verified_inputs.reference_spatial_relation,
        "reference_in_study_area_overlap": (
            verified_inputs.reference_in_study_area_overlap
        ),
        "reference_distance_to_study_area_km": (
            verified_inputs.reference_distance_to_study_area_km
        ),
        "sample_pixel_count": int(len(features)),
        "reference_positive_pixel_count": int(features["reference_flood_extent"].sum()),
        "predicted_positive_pixel_count": int(features["binary_flood_extent"].sum()),
        "sample_width": int(features.attrs.get("sample_width", 0)),
        "sample_height": int(features.attrs.get("sample_height", 0)),
        "bbox_lon_min": bbox[0],
        "bbox_lat_min": bbox[1],
        "bbox_lon_max": bbox[2],
        "bbox_lat_max": bbox[3],
        "window_strategy": "manual_reference_bbox_plus_buffer",
        "georeferencing_method": features.attrs.get("georeferencing_method", ""),
        "probability_threshold": probability_threshold,
        "dry_change_db": dry_change_db,
        "flood_change_db": flood_change_db,
        "mean_combined_sar_change_score": round(
            float(features["combined_sar_change_score"].mean()),
            6,
        ),
        "mean_flood_probability_0_1": round(
            float(features["flood_probability_0_1"].mean()),
            6,
        ),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "assumptions": (
            "Cross-border calibration metrics against a manually digitized "
            "weak-reference mask; not Mae Sai Thailand ADM3 validation. "
            "Non-operational. Not official validation. Not field validated. "
            "The active GDAL subdataset is uncalibrated amplitude, converted with "
            "20*log10(amplitude); it is not Sigma0/Beta0/Gamma0 calibrated. "
            "Sentinel-1 SAFE GCP georeferencing is approximated for this first baseline."
        ),
    }
    return pd.DataFrame([row], columns=SAR_FEATURE_MANIFEST_COLUMNS)


def _read_sar_change_arrays(
    inputs: SARRasterInputs,
    bbox: tuple[float, float, float, float],
    *,
    output_shape: tuple[int, int],
    probability_threshold: float,
    dry_change_db: float,
    flood_change_db: float,
) -> SARChangeArrays:
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling

    if flood_change_db <= dry_change_db:
        raise SARRasterExtractError("flood_change_db must be greater than dry_change_db.")
    if not 0 <= probability_threshold <= 1:
        raise SARRasterExtractError("probability_threshold must be between 0 and 1.")

    with rasterio.Env(GDAL_PAM_ENABLED="NO"), rasterio.open(
        inputs.post_vh_uri
    ) as post_vh_dataset:
        post_transform, post_crs, georeferencing_method = _dataset_geo_transform(
            post_vh_dataset
        )
        _require_compatible_crs(inputs.reference_crs, post_crs)
        post_window = _window_from_geo_bounds(
            bbox,
            post_transform,
            post_vh_dataset.width,
            post_vh_dataset.height,
        )
        window_transform = _window_transform(
            post_transform,
            post_window,
            output_shape=output_shape,
        )
        post_vh = _read_on_common_grid(
            post_vh_dataset,
            source_transform=post_transform,
            source_crs=post_crs,
            target_transform=window_transform,
            target_crs=post_crs,
            output_shape=output_shape,
            resampling=Resampling.bilinear,
        )

    post_vv = _read_on_declared_grid(
        inputs.post_vv_uri,
        reference_crs=inputs.reference_crs,
        target_transform=window_transform,
        target_crs=post_crs,
        output_shape=output_shape,
    )
    pre_vv = _read_on_declared_grid(
        inputs.pre_vv_uri,
        reference_crs=inputs.reference_crs,
        target_transform=window_transform,
        target_crs=post_crs,
        output_shape=output_shape,
    )
    pre_vh = _read_on_declared_grid(
        inputs.pre_vh_uri,
        reference_crs=inputs.reference_crs,
        target_transform=window_transform,
        target_crs=post_crs,
        output_shape=output_shape,
    )

    pre_vv_db = _amplitude_to_db(pre_vv)
    post_vv_db = _amplitude_to_db(post_vv)
    pre_vh_db = _amplitude_to_db(pre_vh)
    post_vh_db = _amplitude_to_db(post_vh)
    vv_drop = pre_vv_db - post_vv_db
    vh_drop = pre_vh_db - post_vh_db
    vv_ratio = np.divide(
        post_vv,
        pre_vv,
        out=np.full_like(post_vv, np.nan, dtype="float32"),
        where=pre_vv > 0,
    )
    vh_ratio = np.divide(
        post_vh,
        pre_vh,
        out=np.full_like(post_vh, np.nan, dtype="float32"),
        where=pre_vh > 0,
    )
    combined = 0.4 * vv_drop + 0.6 * vh_drop
    probability = np.clip(
        (combined - dry_change_db) / (flood_change_db - dry_change_db),
        0.0,
        1.0,
    )
    binary = (probability >= probability_threshold).astype("uint8")
    valid = (
        np.isfinite(pre_vv_db)
        & np.isfinite(post_vv_db)
        & np.isfinite(pre_vh_db)
        & np.isfinite(post_vh_db)
        & np.isfinite(combined)
    )
    if not bool(valid.any()):
        raise SARRasterExtractError("No valid SAR pixels were extracted.")
    return SARChangeArrays(
        pre_vv_db=pre_vv_db,
        post_vv_db=post_vv_db,
        pre_vh_db=pre_vh_db,
        post_vh_db=post_vh_db,
        vv_drop=vv_drop,
        vh_drop=vh_drop,
        vv_ratio=vv_ratio,
        vh_ratio=vh_ratio,
        combined=combined,
        probability=probability,
        binary=binary,
        valid=valid,
        transform=window_transform,
        georeferencing_method=(
            f"{georeferencing_method};exact_common_grid_reprojection"
        ),
    )


def _read_on_declared_grid(
    uri: str,
    *,
    reference_crs: str,
    target_transform: object,
    target_crs: str,
    output_shape: tuple[int, int],
) -> object:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.Env(GDAL_PAM_ENABLED="NO"), rasterio.open(uri) as dataset:
        source_transform, source_crs, _method = _dataset_geo_transform(dataset)
        _require_compatible_crs(reference_crs, source_crs)
        _require_compatible_crs(target_crs, source_crs)
        return _read_on_common_grid(
            dataset,
            source_transform=source_transform,
            source_crs=source_crs,
            target_transform=target_transform,
            target_crs=target_crs,
            output_shape=output_shape,
            resampling=Resampling.bilinear,
        )


def _read_on_common_grid(
    dataset: object,
    *,
    source_transform: object,
    source_crs: str,
    target_transform: object,
    target_crs: str,
    output_shape: tuple[int, int],
    resampling: object,
) -> object:
    """Reproject one source band onto the exact declared comparison grid."""

    import numpy as np
    import rasterio
    from rasterio.warp import reproject

    destination = np.full(output_shape, np.nan, dtype="float32")
    reproject(
        source=rasterio.band(dataset, 1),
        destination=destination,
        src_transform=source_transform,
        src_crs=source_crs,
        src_nodata=getattr(dataset, "nodata", None),
        dst_transform=target_transform,
        dst_crs=target_crs,
        dst_nodata=np.nan,
        resampling=resampling,
        init_dest_nodata=True,
        num_threads=1,
    )
    if destination.shape != output_shape:
        raise SARRasterExtractError(
            "SAR source did not reproject to the declared common-grid shape."
        )
    return destination


def _dataset_geo_transform(dataset: object) -> tuple[object, str, str]:
    from rasterio.transform import Affine, from_gcps

    identity = Affine.identity()
    if dataset.crs is not None and dataset.transform != identity:
        return dataset.transform, str(dataset.crs), "dataset_affine_transform"
    gcps, gcp_crs = dataset.gcps
    if gcps and gcp_crs is not None:
        return from_gcps(gcps), str(gcp_crs), "sentinel1_safe_gcps_affine_fit"
    raise SARRasterExtractError(
        "Raster does not expose a CRS transform or Sentinel-1 GCP georeferencing."
    )


def _window_from_geo_bounds(
    bbox: tuple[float, float, float, float],
    transform: object,
    width: int,
    height: int,
) -> object:
    from rasterio.windows import Window

    left, bottom, right, top = bbox
    inverse = ~transform
    points = [
        inverse * (left, bottom),
        inverse * (left, top),
        inverse * (right, bottom),
        inverse * (right, top),
    ]
    cols = [point[0] for point in points]
    rows = [point[1] for point in points]
    col_min = max(0, math.floor(min(cols)))
    row_min = max(0, math.floor(min(rows)))
    col_max = min(width, math.ceil(max(cols)))
    row_max = min(height, math.ceil(max(rows)))
    if col_max <= col_min or row_max <= row_min:
        raise SARRasterExtractError("Reference bbox does not overlap raster bounds.")
    return Window(
        col_off=col_min,
        row_off=row_min,
        width=col_max - col_min,
        height=row_max - row_min,
    )


def _window_transform(transform: object, window: object, *, output_shape: tuple[int, int]) -> object:
    from affine import Affine

    out_height, out_width = output_shape
    return (
        transform
        * Affine.translation(window.col_off, window.row_off)
        * Affine.scale(window.width / out_width, window.height / out_height)
    )


def _amplitude_to_db(values: object) -> object:
    """Convert positive uncalibrated amplitude to dB without claiming Sigma0."""

    import numpy as np

    array = np.asarray(values, dtype="float32")
    array = np.where(array > 0, array, np.nan)
    return 20.0 * np.log10(array)


def _geometry_bounds(
    geometries: Sequence[dict[str, object]],
    *,
    buffer_degrees: float,
) -> tuple[float, float, float, float]:
    coordinates: list[tuple[float, float]] = []
    for geometry in geometries:
        coordinates.extend(_iter_geometry_coordinates(geometry))
    if not coordinates:
        raise SARRasterExtractError("Reference geometries have no coordinates.")
    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    return (
        min(xs) - buffer_degrees,
        min(ys) - buffer_degrees,
        max(xs) + buffer_degrees,
        max(ys) + buffer_degrees,
    )


def _validated_polygon_geometries(
    geometries: Sequence[dict[str, object]],
    *,
    label: str,
) -> tuple[dict[str, object], ...]:
    """Validate finite, non-empty, topologically simple positive-area geometry."""

    if not geometries:
        raise SARRasterExtractError(f"{label} collection is empty.")
    validated: list[dict[str, object]] = []
    for geometry_index, geometry in enumerate(geometries):
        if not isinstance(geometry, Mapping):
            raise SARRasterExtractError(
                f"{label} {geometry_index} must be a GeoJSON geometry object."
            )
        geometry_type = str(geometry.get("type", ""))
        coordinates = geometry.get("coordinates")
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            if not _coordinate_sequence(coordinates):
                raise SARRasterExtractError(
                    f"{label} {geometry_index} MultiPolygon is empty."
                )
            polygons = list(coordinates)
        else:
            raise SARRasterExtractError(
                f"{label} {geometry_index} must be Polygon or MultiPolygon."
            )
        normalized_polygons: list[tuple[tuple[tuple[float, float], ...], ...]] = []
        total_area = 0.0
        for polygon_index, polygon in enumerate(polygons):
            rings, area = _validated_polygon(
                polygon,
                label=f"{label} {geometry_index} polygon {polygon_index}",
            )
            normalized_polygons.append(rings)
            total_area += area
        for first_index, first in enumerate(normalized_polygons):
            for second_index in range(first_index + 1, len(normalized_polygons)):
                _require_disjoint_polygons(
                    first,
                    normalized_polygons[second_index],
                    label=(
                        f"{label} {geometry_index} polygons {first_index} and "
                        f"{second_index}"
                    ),
                )
        if not math.isfinite(total_area) or total_area <= 0:
            raise SARRasterExtractError(f"{label} {geometry_index} has no positive area.")
        validated.append(dict(geometry))
    return tuple(validated)


def _validated_polygon(
    polygon: object,
    *,
    label: str,
) -> tuple[tuple[tuple[tuple[float, float], ...], ...], float]:
    if not _coordinate_sequence(polygon):
        raise SARRasterExtractError(f"{label} has no rings.")
    rings = tuple(
        _validated_ring(ring, label=f"{label} ring {ring_index}")
        for ring_index, ring in enumerate(polygon)
    )
    exterior = rings[0]
    holes = rings[1:]
    exterior_area = abs(_ring_signed_area(exterior))
    hole_area = sum(abs(_ring_signed_area(hole)) for hole in holes)
    for hole_index, hole in enumerate(holes):
        if not _point_in_ring(hole[0], exterior):
            raise SARRasterExtractError(
                f"{label} hole {hole_index} is not strictly inside its exterior ring."
            )
        if _rings_intersect(exterior, hole):
            raise SARRasterExtractError(
                f"{label} hole {hole_index} intersects its exterior ring."
            )
    for first_index, first in enumerate(holes):
        for second_index in range(first_index + 1, len(holes)):
            second = holes[second_index]
            if (
                _rings_intersect(first, second)
                or _point_in_ring(first[0], second)
                or _point_in_ring(second[0], first)
            ):
                raise SARRasterExtractError(f"{label} contains overlapping holes.")
    net_area = exterior_area - hole_area
    if not math.isfinite(net_area) or net_area <= 0:
        raise SARRasterExtractError(f"{label} has no positive area.")
    return rings, net_area


def _validated_ring(ring: object, *, label: str) -> tuple[tuple[float, float], ...]:
    if not _coordinate_sequence(ring) or len(ring) < 4:
        raise SARRasterExtractError(f"{label} must contain at least four coordinates.")
    points: list[tuple[float, float]] = []
    for coordinate_index, coordinate in enumerate(ring):
        if not _coordinate_sequence(coordinate) or len(coordinate) < 2:
            raise SARRasterExtractError(
                f"{label} coordinate {coordinate_index} is malformed."
            )
        try:
            point = (float(coordinate[0]), float(coordinate[1]))
        except (TypeError, ValueError) as exc:
            raise SARRasterExtractError(
                f"{label} coordinate {coordinate_index} is not numeric."
            ) from exc
        if not all(math.isfinite(value) for value in point):
            raise SARRasterExtractError(
                f"{label} coordinate {coordinate_index} is not finite."
            )
        if points and point == points[-1]:
            raise SARRasterExtractError(f"{label} has a zero-length edge.")
        points.append(point)
    if points[0] != points[-1]:
        raise SARRasterExtractError(f"{label} is not closed.")
    if len(set(points[:-1])) < 3 or abs(_ring_signed_area(tuple(points))) <= 0:
        raise SARRasterExtractError(f"{label} has no positive area.")
    segments = list(zip(points[:-1], points[1:], strict=True))
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 1, len(segments)):
            if second_index in {first_index, first_index + 1} or (
                first_index == 0 and second_index == len(segments) - 1
            ):
                continue
            if _segments_intersect(
                first[0],
                first[1],
                segments[second_index][0],
                segments[second_index][1],
            ):
                raise SARRasterExtractError(f"{label} self-intersects.")
    return tuple(points)


def _require_disjoint_polygons(
    first: tuple[tuple[tuple[float, float], ...], ...],
    second: tuple[tuple[tuple[float, float], ...], ...],
    *,
    label: str,
) -> None:
    if any(
        _rings_cross_or_share_segment(left, right)
        for left in first
        for right in second
    ):
        raise SARRasterExtractError(f"{label} overlap or share a boundary segment.")
    if any(_point_in_polygon(point, second) for point in first[0][:-1]) or any(
        _point_in_polygon(point, first) for point in second[0][:-1]
    ):
        raise SARRasterExtractError(f"{label} overlap.")


def _rings_cross_or_share_segment(
    first: tuple[tuple[float, float], ...],
    second: tuple[tuple[float, float], ...],
) -> bool:
    """Return true for interior crossings or positive-length boundary overlap.

    OGC-valid MultiPolygon members may meet at isolated boundary points. Such
    point contacts do not create shared interior area and must not be rejected
    as overlap. Proper segment crossings and collinear shared segments remain
    fail-closed because they make the multipart geometry invalid or ambiguous.
    """

    return any(
        _segments_properly_intersect(first_start, first_end, second_start, second_end)
        or _collinear_segments_overlap(first_start, first_end, second_start, second_end)
        for first_start, first_end in zip(first[:-1], first[1:], strict=True)
        for second_start, second_end in zip(second[:-1], second[1:], strict=True)
    )


def _segments_properly_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    orientations = (
        _orientation(first_start, first_end, second_start),
        _orientation(first_start, first_end, second_end),
        _orientation(second_start, second_end, first_start),
        _orientation(second_start, second_end, first_end),
    )
    return (
        orientations[0] * orientations[1] < 0
        and orientations[2] * orientations[3] < 0
    )


def _collinear_segments_overlap(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    if any(
        orientation != 0
        for orientation in (
            _orientation(first_start, first_end, second_start),
            _orientation(first_start, first_end, second_end),
            _orientation(second_start, second_end, first_start),
            _orientation(second_start, second_end, first_end),
        )
    ):
        return False

    axis = 0 if abs(first_end[0] - first_start[0]) >= abs(
        first_end[1] - first_start[1]
    ) else 1
    overlap = min(
        max(first_start[axis], first_end[axis]),
        max(second_start[axis], second_end[axis]),
    ) - max(
        min(first_start[axis], first_end[axis]),
        min(second_start[axis], second_end[axis]),
    )
    return overlap > 1e-12


def _point_in_polygon(
    point: tuple[float, float],
    polygon: tuple[tuple[tuple[float, float], ...], ...],
) -> bool:
    return _point_in_ring(point, polygon[0]) and not any(
        _point_in_ring(point, hole) for hole in polygon[1:]
    )


def _point_in_ring(
    point: tuple[float, float],
    ring: tuple[tuple[float, float], ...],
) -> bool:
    x, y = point
    inside = False
    for start, end in zip(ring[:-1], ring[1:], strict=True):
        if _point_on_segment(point, start, end):
            return False
        if (start[1] > y) != (end[1] > y):
            intersect_x = start[0] + (y - start[1]) * (end[0] - start[0]) / (
                end[1] - start[1]
            )
            if intersect_x > x:
                inside = not inside
    return inside


def _rings_intersect(
    first: tuple[tuple[float, float], ...],
    second: tuple[tuple[float, float], ...],
) -> bool:
    return any(
        _segments_intersect(first_start, first_end, second_start, second_end)
        for first_start, first_end in zip(first[:-1], first[1:], strict=True)
        for second_start, second_end in zip(second[:-1], second[1:], strict=True)
    )


def _segments_intersect(
    first_start: tuple[float, float],
    first_end: tuple[float, float],
    second_start: tuple[float, float],
    second_end: tuple[float, float],
) -> bool:
    orientations = (
        _orientation(first_start, first_end, second_start),
        _orientation(first_start, first_end, second_end),
        _orientation(second_start, second_end, first_start),
        _orientation(second_start, second_end, first_end),
    )
    if (
        orientations[0] * orientations[1] < 0
        and orientations[2] * orientations[3] < 0
    ):
        return True
    return any(
        orientation == 0 and _point_on_segment(point, start, end)
        for orientation, point, start, end in (
            (orientations[0], second_start, first_start, first_end),
            (orientations[1], second_end, first_start, first_end),
            (orientations[2], first_start, second_start, second_end),
            (orientations[3], first_end, second_start, second_end),
        )
    )


def _orientation(
    start: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
) -> int:
    cross = (end[0] - start[0]) * (point[1] - start[1]) - (
        end[1] - start[1]
    ) * (point[0] - start[0])
    tolerance = 1e-12
    return 0 if abs(cross) <= tolerance else 1 if cross > 0 else -1


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    if _orientation(start, end, point) != 0:
        return False
    tolerance = 1e-12
    return (
        min(start[0], end[0]) - tolerance
        <= point[0]
        <= max(start[0], end[0]) + tolerance
        and min(start[1], end[1]) - tolerance
        <= point[1]
        <= max(start[1], end[1]) + tolerance
    )


def _ring_signed_area(ring: tuple[tuple[float, float], ...]) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(ring[:-1], ring[1:], strict=True)
    )


def _coordinate_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ) and len(value) > 0


def _iter_geometry_coordinates(geometry: dict[str, object]) -> Iterable[tuple[float, float]]:
    geometry_type = str(geometry.get("type", ""))
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        for ring in coordinates:
            for coordinate in ring:
                yield float(coordinate[0]), float(coordinate[1])
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for coordinate in ring:
                    yield float(coordinate[0]), float(coordinate[1])
    else:
        raise SARRasterExtractError(f"Unsupported reference geometry type: {geometry_type}")


def _parse_geopackage_geometry(blob: bytes) -> dict[str, object]:
    data = bytes(blob)
    if len(data) < 9 or data[:2] != b"GP":
        raise SARRasterExtractError("Invalid GeoPackage geometry binary header.")
    flags = data[3]
    envelope_indicator = (flags >> 1) & 0b111
    envelope_size = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(envelope_indicator)
    if envelope_size is None:
        raise SARRasterExtractError("Unsupported GeoPackage geometry envelope.")
    offset = 8 + envelope_size
    return _parse_wkb_geometry(data[offset:])


def _parse_wkb_geometry(data: bytes) -> dict[str, object]:
    geometry, offset = _parse_wkb_at(data, 0)
    if offset > len(data):
        raise SARRasterExtractError("Invalid WKB geometry length.")
    return geometry


def _parse_wkb_at(data: bytes, offset: int) -> tuple[dict[str, object], int]:
    if offset + 5 > len(data):
        raise SARRasterExtractError("Invalid WKB geometry.")
    byte_order = data[offset]
    endian = "<" if byte_order == 1 else ">"
    geometry_type = struct.unpack_from(f"{endian}I", data, offset + 1)[0]
    base_type = geometry_type % 1000
    cursor = offset + 5
    if base_type == 3:
        ring_count = struct.unpack_from(f"{endian}I", data, cursor)[0]
        cursor += 4
        rings = []
        for _ in range(ring_count):
            point_count = struct.unpack_from(f"{endian}I", data, cursor)[0]
            cursor += 4
            ring = []
            for _ in range(point_count):
                x, y = struct.unpack_from(f"{endian}dd", data, cursor)
                cursor += 16
                ring.append((x, y))
            rings.append(ring)
        return {"type": "Polygon", "coordinates": rings}, cursor
    if base_type == 6:
        polygon_count = struct.unpack_from(f"{endian}I", data, cursor)[0]
        cursor += 4
        polygons = []
        for _ in range(polygon_count):
            polygon, cursor = _parse_wkb_at(data, cursor)
            if polygon["type"] != "Polygon":
                raise SARRasterExtractError("Invalid MultiPolygon WKB member.")
            polygons.append(polygon["coordinates"])
        return {"type": "MultiPolygon", "coordinates": polygons}, cursor
    raise SARRasterExtractError(f"Unsupported WKB geometry type: {geometry_type}")


def _select_manifest_row(manifest: pd.DataFrame, candidate_use: str) -> pd.Series:
    matches = manifest[manifest["candidate_use"].astype(str) == candidate_use]
    if candidate_use == "post-event SAR source for non-ML baseline":
        primary = matches[
            matches["source_name"].astype(str).str.contains(
                "primary",
                case=False,
                regex=False,
            )
        ]
        if not primary.empty:
            matches = primary
    if matches.empty:
        raise SARRasterExtractError(f"Missing manifest role: {candidate_use}")
    return matches.iloc[0]


def _require_approved_mae_sai_baseline_pair(
    pre_row: pd.Series,
    post_row: pd.Series,
) -> None:
    """Reject retired COG, cross-track, or substituted baseline identities."""

    actual = (str(pre_row["product_id"]), str(post_row["product_id"]))
    expected = (
        MAE_SAI_BASELINE_PRE_PRODUCT_ID,
        MAE_SAI_BASELINE_POST_PRODUCT_ID,
    )
    if actual != expected:
        raise SARRasterExtractError(
            "Mae Sai weak-reference extraction requires the approved same-track "
            "original SAFE pair; retired COG, cross-track, or substituted product "
            f"identities are blocked. Expected {expected[0]} / {expected[1]}, got "
            f"{actual[0]} / {actual[1]}."
        )


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file_sha256(path: Path, expected_sha256: str, *, label: str) -> str:
    if not path.is_file():
        raise SARRasterExtractError(f"{label} does not exist: {path}")
    expected = expected_sha256.strip().lower()
    if not _valid_sha256(expected):
        raise SARRasterExtractError(
            f"{label} has no valid manifest SHA-256; raster reads are blocked."
        )
    actual = _sha256(path)
    if not hmac.compare_digest(actual, expected):
        raise SARRasterExtractError(
            f"{label} SHA-256 mismatch. Raster reads are blocked before GDAL access; "
            "the external source may have been substituted or mutated."
        )
    return actual


def _require_verified_input_lineage(inputs: SARRasterInputs) -> None:
    checksums = (
        inputs.pre_source_sha256,
        inputs.post_source_sha256,
        inputs.reference_sha256,
    )
    if inputs.source_integrity_status != "verified_sha256_before_raster_read":
        raise SARRasterExtractError(
            "SAR feature lineage requires inputs verified before raster reads."
        )
    if not all(_valid_sha256(value) for value in checksums):
        raise SARRasterExtractError(
            "SAR feature lineage requires valid pre, post, and reference SHA-256 values."
        )
    if (
        inputs.reference_spatial_relation != "cross_border_calibration_only"
        or inputs.reference_in_study_area_overlap is not False
        or inputs.reference_distance_to_study_area_km is None
        or inputs.reference_distance_to_study_area_km <= 0
    ):
        raise SARRasterExtractError(
            "SAR feature lineage requires verified cross-border non-overlap metadata."
        )


def _require_compatible_crs(reference_crs: str, raster_crs: str) -> None:
    if _normalize_crs(reference_crs) != _normalize_crs(raster_crs):
        raise SARRasterExtractError(
            f"Reference CRS {reference_crs} does not match raster georeferencing CRS {raster_crs}."
        )


def _normalize_crs(value: str) -> str:
    return str(value).upper().replace("EPSG:", "EPSG:")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    label: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise SARRasterExtractError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _quote_identifier(value: str) -> str:
    if "\x00" in value:
        raise SARRasterExtractError("Invalid GeoPackage identifier.")
    return '"' + value.replace('"', '""') + '"'


def _crs_summary(connection: sqlite3.Connection, srs_id: int) -> str:
    row = connection.execute(
        """
        SELECT organization, organization_coordsys_id
        FROM gpkg_spatial_ref_sys
        WHERE srs_id = ?
        """,
        (srs_id,),
    ).fetchone()
    if row is None:
        return f"srs_id:{srs_id}"
    organization, coordsys_id = row
    return f"{organization}:{coordsys_id}"
