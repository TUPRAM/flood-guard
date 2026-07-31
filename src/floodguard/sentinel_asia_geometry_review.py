"""QGIS/GDAL-backed Sentinel Asia geometry quality review helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
import shutil
import subprocess

import pandas as pd

DEFAULT_SENTINEL_ASIA_ZIP = (
    Path.home()
    / "Documents"
    / "FloodGuard_external_data"
    / "sentinel_asia"
    / "MBRSC_THAILAND_FLOOD-MAP-SHP.zip"
)
DEFAULT_QGIS_OGRINFO = Path("C:/Program Files/QGIS 4.0.3/bin/ogrinfo.exe")
MAE_SAI_REVIEW_BBOX = (99.72, 20.30, 100.03, 20.56)

GEOMETRY_REVIEW_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_url",
    "local_path_hint",
    "qgis_tool",
    "qgis_gdal_version",
    "layer_name",
    "geometry_type",
    "crs",
    "dbf_update_date",
    "attribute_fields",
    "feature_count",
    "area_field_sum_m2",
    "area_field_sum_km2",
    "area_field_min_m2",
    "area_field_max_m2",
    "gridcode_values",
    "mae_sai_review_bbox",
    "mae_sai_review_feature_count",
    "mae_sai_review_area_sum_m2",
    "mae_sai_review_area_sum_km2",
    "mae_sai_review_area_min_m2",
    "mae_sai_review_area_max_m2",
    "geometry_quality_status",
    "flood_extent_interpretation",
    "validation_use_status",
    "ml_label_use_status",
    "review_notes",
    "reviewed_at_utc",
)


class SentinelAsiaGeometryReviewError(ValueError):
    """Raised when Sentinel Asia geometry review cannot run or parse output."""


def write_sentinel_asia_geometry_review(
    inspection_manifest_path: str | Path,
    output_path: str | Path,
    notes_path: str | Path,
    *,
    zip_path: str | Path = DEFAULT_SENTINEL_ASIA_ZIP,
    ogrinfo_path: str | Path | None = None,
    reviewed_at_utc: str | None = None,
) -> tuple[Path, Path]:
    """Run QGIS/GDAL geometry review and write CSV plus Markdown notes."""

    inspection = pd.read_csv(inspection_manifest_path, dtype=str).fillna("")
    if inspection.empty:
        raise SentinelAsiaGeometryReviewError("Inspection manifest is empty.")

    review = build_sentinel_asia_geometry_review(
        inspection.iloc[0],
        zip_path=zip_path,
        ogrinfo_path=ogrinfo_path,
        reviewed_at_utc=reviewed_at_utc,
    )
    csv_target = Path(output_path)
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(csv_target, index=False)

    md_target = Path(notes_path)
    md_target.parent.mkdir(parents=True, exist_ok=True)
    md_target.write_text(build_geometry_quality_notes(review.iloc[0]), encoding="utf-8")
    return csv_target, md_target


def build_sentinel_asia_geometry_review(
    inspection_row: pd.Series,
    *,
    zip_path: str | Path,
    ogrinfo_path: str | Path | None = None,
    reviewed_at_utc: str | None = None,
) -> pd.DataFrame:
    """Build one geometry-review row using QGIS/GDAL `ogrinfo`."""

    ogrinfo = _resolve_ogrinfo(ogrinfo_path)
    source_zip = Path(zip_path)
    if not source_zip.exists():
        raise SentinelAsiaGeometryReviewError(f"Sentinel Asia ZIP not found: {source_zip}")

    vsi_path = _vsi_shapefile_path(source_zip)
    version = _run_ogrinfo(ogrinfo, ["--version"]).strip()
    layer_summary = _run_ogrinfo(ogrinfo, ["-ro", "-al", "-so", vsi_path])
    full_stats = _run_ogrinfo(
        ogrinfo,
        [
            "-ro",
            vsi_path,
            "-dialect",
            "SQLite",
            "-sql",
            (
                "SELECT COUNT(*) AS feature_count, SUM(Area) AS area_sum, "
                "MIN(Area) AS area_min, MAX(Area) AS area_max, "
                "COUNT(DISTINCT gridcode) AS gridcode_count FROM Thailand_flood"
            ),
        ],
    )
    mae_sai_stats = _run_ogrinfo(
        ogrinfo,
        [
            "-ro",
            vsi_path,
            "-dialect",
            "SQLite",
            "-sql",
            (
                "SELECT COUNT(*) AS feature_count, SUM(Area) AS area_sum, "
                "MIN(Area) AS area_min, MAX(Area) AS area_max "
                "FROM Thailand_flood WHERE "
                "ST_Intersects(geometry, BuildMbr(99.72,20.30,100.03,20.56))"
            ),
        ],
    )
    gridcode_stats = _run_ogrinfo(
        ogrinfo,
        [
            "-ro",
            vsi_path,
            "-dialect",
            "SQLite",
            "-sql",
            "SELECT gridcode FROM Thailand_flood GROUP BY gridcode ORDER BY gridcode",
        ],
    )

    layer = _parse_layer_summary(layer_summary)
    full = _parse_ogr_feature_values(full_stats)
    mae_sai = _parse_ogr_feature_values(mae_sai_stats)
    gridcodes = _parse_gridcodes(gridcode_stats)

    feature_count = int(float(full["feature_count"]))
    area_sum_m2 = float(full["area_sum"])
    mae_sai_count = int(float(mae_sai["feature_count"]))
    mae_sai_area_m2 = float(mae_sai["area_sum"])
    status = _geometry_quality_status(feature_count, mae_sai_count, gridcodes)

    row = {
        "source_name": inspection_row.get("source_name", ""),
        "source_url": inspection_row.get("source_url", ""),
        "local_path_hint": inspection_row.get("local_path_hint", ""),
        "qgis_tool": "QGIS/GDAL ogrinfo",
        "qgis_gdal_version": version,
        "layer_name": layer["layer_name"],
        "geometry_type": layer["geometry_type"],
        "crs": layer["crs"],
        "dbf_update_date": layer["dbf_update_date"],
        "attribute_fields": layer["attribute_fields"],
        "feature_count": feature_count,
        "area_field_sum_m2": round(area_sum_m2, 2),
        "area_field_sum_km2": round(area_sum_m2 / 1_000_000, 3),
        "area_field_min_m2": round(float(full["area_min"]), 2),
        "area_field_max_m2": round(float(full["area_max"]), 2),
        "gridcode_values": "|".join(gridcodes),
        "mae_sai_review_bbox": ",".join(str(value) for value in MAE_SAI_REVIEW_BBOX),
        "mae_sai_review_feature_count": mae_sai_count,
        "mae_sai_review_area_sum_m2": round(mae_sai_area_m2, 2),
        "mae_sai_review_area_sum_km2": round(mae_sai_area_m2 / 1_000_000, 3),
        "mae_sai_review_area_min_m2": round(float(mae_sai["area_min"]), 2),
        "mae_sai_review_area_max_m2": round(float(mae_sai["area_max"]), 2),
        "geometry_quality_status": status,
        "flood_extent_interpretation": (
            "attributes and lineage support flood-water extent polygons from a "
            "raster-to-polygon workflow, but the layer covers broader northern "
            "Thailand and still needs visual QA before validation use"
        ),
        "validation_use_status": "reference_candidate_terms_and_quality_review_required",
        "ml_label_use_status": "not_cleared_for_ml_labels",
        "review_notes": (
            "QGIS/GDAL review confirms machine-readable polygon geometry over the "
            "Mae Sai review bbox. Keep as reference candidate until Sentinel Asia/MBRSC "
            "terms and visual geometry quality are resolved."
        ),
        "reviewed_at_utc": reviewed_at_utc
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    return pd.DataFrame([row], columns=GEOMETRY_REVIEW_COLUMNS)


def build_geometry_quality_notes(review_row: pd.Series) -> str:
    """Build Markdown notes for the Sentinel Asia geometry quality review."""

    return "\n".join(
        [
            "# Sentinel Asia Geometry Quality Notes",
            "",
            "Status: reference candidate, not validation truth and not ML labels.",
            "",
            "## QGIS/GDAL Inspection",
            "",
            f"- Tool: `{review_row['qgis_gdal_version']}`",
            f"- Layer: `{review_row['layer_name']}`",
            f"- Geometry: `{review_row['geometry_type']}`",
            f"- CRS: `{review_row['crs']}`",
            f"- Attribute fields: `{review_row['attribute_fields']}`",
            f"- DBF update date: `{review_row['dbf_update_date']}`",
            "",
            "## Spatial Findings",
            "",
            f"- Full layer features: {review_row['feature_count']}",
            f"- Full layer area field sum: {review_row['area_field_sum_km2']} km2",
            f"- Mae Sai review bbox: `{review_row['mae_sai_review_bbox']}`",
            f"- Mae Sai-intersecting features: {review_row['mae_sai_review_feature_count']}",
            f"- Mae Sai-intersecting area field sum: {review_row['mae_sai_review_area_sum_km2']} km2",
            f"- Gridcode values: `{review_row['gridcode_values']}`",
            "",
            "## Interpretation",
            "",
            (
                "- The layer is much broader than Mae Sai, but it contains many polygon "
                "features intersecting the Mae Sai review bbox."
            ),
            (
                "- The shapefile metadata lineage indicates a raster-to-polygon flood "
                "workflow and an area field calculated in square meters."
            ),
            (
                "- This supports treating the file as a practical public flood-water "
                "reference candidate for Mae Sai review, not as cleared validation truth."
            ),
            "",
            "## Remaining Blockers",
            "",
            "- Product-level terms for validation metrics, screenshots, derived metrics, redistribution, and ML-label use are unresolved.",
            "- Human visual QA in QGIS should inspect polygon alignment against basemap, river corridor, and known Mae Sai flood reports.",
            (
                "- Do not use this Sentinel Asia reference candidate for qualified "
                "validation or as a baseline reference until its own manifest row passes "
                "without `--allow-blocked`. The separate manual cross-border weak-reference "
                "calibration does not clear this source's gates."
            ),
            "",
            "## How To Open In QGIS",
            "",
            "1. Open QGIS.",
            "2. Add vector layer from the external ZIP path:",
            "   `<external_data_workspace>/sentinel_asia/MBRSC_THAILAND_FLOOD-MAP-SHP.zip`.",
            "3. Select layer `Thailand_flood`.",
            "4. Add an OpenStreetMap or other allowed basemap.",
            "5. Zoom to Mae Sai around `99.88, 20.43`.",
            "6. Confirm whether polygons align with plausible flood-water areas, not only broad event extents.",
            "",
        ]
    )


def _resolve_ogrinfo(ogrinfo_path: str | Path | None) -> Path:
    if ogrinfo_path is not None:
        candidate = Path(ogrinfo_path)
        if candidate.exists():
            return candidate
        raise SentinelAsiaGeometryReviewError(f"ogrinfo not found: {candidate}")
    if DEFAULT_QGIS_OGRINFO.exists():
        return DEFAULT_QGIS_OGRINFO
    found = shutil.which("ogrinfo")
    if found:
        return Path(found)
    raise SentinelAsiaGeometryReviewError(
        "QGIS/GDAL ogrinfo was not found. Install QGIS or pass --ogrinfo-path."
    )


def _vsi_shapefile_path(zip_path: Path) -> str:
    normalized = zip_path.resolve().as_posix()
    return f"/vsizip/{normalized}/Thailand_flood.shp"


def _run_ogrinfo(ogrinfo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        [str(ogrinfo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise SentinelAsiaGeometryReviewError(output.strip() or "ogrinfo failed")
    return output


def _parse_layer_summary(text: str) -> dict[str, str]:
    fields = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*: (Integer64|Integer|Real|String|Date|DateTime|Time)(?: .*)?$",
            stripped,
        ):
            fields.append(stripped)
    return {
        "layer_name": _match(text, r"Layer name:\s*(.+)", "unknown"),
        "geometry_type": _match(text, r"Geometry:\s*(.+)", "unknown"),
        "crs": _match(text, r'ID\["EPSG",(\d+)\]', "unknown_epsg"),
        "dbf_update_date": _match(text, r"DBF_DATE_LAST_UPDATE=(.+)", "unknown"),
        "attribute_fields": "|".join(fields),
    }


def _parse_ogr_feature_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = re.search(r"^\s+([A-Za-z_][A-Za-z0-9_]*) \([^)]+\) = (.+)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    if not values:
        raise SentinelAsiaGeometryReviewError("No OGR SQL values were parsed.")
    return values


def _parse_gridcodes(text: str) -> list[str]:
    values = [
        match.group(1).strip()
        for match in re.finditer(r"gridcode \([^)]+\) = (.+)", text)
    ]
    return values or ["unknown"]


def _match(text: str, pattern: str, default: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else default


def _geometry_quality_status(
    feature_count: int,
    mae_sai_feature_count: int,
    gridcodes: list[str],
) -> str:
    if feature_count <= 0:
        return "blocked_no_features"
    if mae_sai_feature_count <= 0:
        return "blocked_no_mae_sai_overlap"
    if set(gridcodes) == {"1"}:
        return "usable_reference_candidate_pending_terms_and_visual_qa"
    return "reference_candidate_needs_gridcode_review"
