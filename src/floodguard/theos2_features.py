"""Non-ML THEOS-2 optical context feature prototypes."""

from __future__ import annotations

from collections.abc import Iterable
import math
from pathlib import Path

import pandas as pd

FEATURE_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "has_disaster_context",
    "has_lulc_context",
    "has_urban_context",
    "has_agri_context",
    "has_coastal_context",
    "rough_bbox_area_sq_km",
    "mvp_overlap",
    "built_up_exposure_note",
    "water_context_note",
    "floodguard_use",
    "confidence_class",
    "assumptions",
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "mvp_overlap",
    "processing_allowed",
    "reference_mask_status",
)


class THEOS2FeatureError(ValueError):
    """Raised when THEOS-2 feature inputs violate the feature contract."""


def build_theos2_landcover_exposure_features(
    selected_manifest: str | Path | pd.DataFrame,
) -> pd.DataFrame:
    """Build a tiny non-ML feature table from selected THEOS-2 metadata."""

    frame = _coerce_frame(selected_manifest)
    _require_columns(frame, REQUIRED_COLUMNS)
    rows: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        if not _truthy(row["processing_allowed"]):
            continue
        if row["reference_mask_status"] != "not_reference_mask":
            raise THEOS2FeatureError(
                f"THEOS-2 row must not be treated as reference mask: {row['file_name']}"
            )
        labels = _category_labels(row["category"])
        area = _rough_bbox_area(row)
        rows.append(
            {
                "file_name": row["file_name"],
                "source_timestamp": row["source_timestamp"],
                "category": row["category"],
                "has_disaster_context": "Disaster" in labels,
                "has_lulc_context": "LULC" in labels,
                "has_urban_context": "Urban" in labels,
                "has_agri_context": "Agri" in labels,
                "has_coastal_context": "Coastal" in labels,
                "rough_bbox_area_sq_km": area,
                "mvp_overlap": row["mvp_overlap"],
                "built_up_exposure_note": _built_up_note(labels),
                "water_context_note": _water_note(labels),
                "floodguard_use": _floodguard_use(labels, row["mvp_overlap"]),
                "confidence_class": "medium" if area is not None else "low",
                "assumptions": (
                    "Non-ML THEOS-2 metadata feature prototype; optical context only; "
                    "not flood validation or labels."
                ),
            }
        )
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS)


def write_theos2_landcover_exposure_features(
    selected_manifest_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Write the THEOS-2 land-cover/exposure feature prototype CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise THEOS2FeatureError("THEOS-2 feature output must be CSV.")
    features = build_theos2_landcover_exposure_features(selected_manifest_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(target, index=False)
    return target


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(frame: pd.DataFrame, required_columns: Iterable[str]) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise THEOS2FeatureError(
            f"THEOS-2 selected manifest is missing required columns: {', '.join(missing)}"
        )


def _category_labels(value: object) -> set[str]:
    return {part.strip() for part in str(value).split("|") if part.strip()}


def _rough_bbox_area(row: dict[str, object]) -> float | None:
    try:
        lon_min = float(row["bbox_lon_min"])
        lat_min = float(row["bbox_lat_min"])
        lon_max = float(row["bbox_lon_max"])
        lat_max = float(row["bbox_lat_max"])
    except (TypeError, ValueError):
        return None
    mean_lat_rad = math.radians((lat_min + lat_max) / 2)
    width_km = abs(lon_max - lon_min) * 111.32 * math.cos(mean_lat_rad)
    height_km = abs(lat_max - lat_min) * 110.57
    return round(width_km * height_km, 3)


def _built_up_note(labels: set[str]) -> str:
    if "Urban" in labels:
        return "urban-context sample; useful for built-up exposure interpretation"
    if "LULC" in labels:
        return "land-cover context sample; built-up exposure requires visual review"
    if "Disaster" in labels:
        return "disaster-context sample; built-up exposure not inferred automatically"
    return "no built-up exposure inference from metadata alone"


def _water_note(labels: set[str]) -> str:
    if "Coastal" in labels:
        return "coastal/water-edge context may support false-positive review"
    if "Disaster" in labels:
        return "disaster-context optical sample; visible-water review may be useful"
    return "water context not inferred from metadata alone"


def _floodguard_use(labels: set[str], overlap: object) -> str:
    if str(overlap) != "none_of_current_mvp_points":
        return "candidate optical context for a current MVP point"
    if "Disaster" in labels and "LULC" in labels:
        return "method-development context for disaster and land-cover interpretation"
    if "Disaster" in labels:
        return "method-development context for disaster optical review"
    return "general optical context for exposure interpretation"


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
