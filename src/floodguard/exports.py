"""Dashboard-ready GeoJSON export helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class ExportError(ValueError):
    """Raised when GeoJSON export inputs violate the export contract."""


def write_priority_geojson(
    admin_geojson_path: str | Path,
    priority_frame: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Write subdistrict priority features by merging scores into admin geometry."""

    return _write_joined_geojson(
        geometry_path=admin_geojson_path,
        data_frame=priority_frame,
        output_path=output_path,
        join_key="subdistrict_id",
        output_name="priority_subdistricts",
    )


def write_road_risk_geojson(
    roads_geojson_path: str | Path,
    road_risk_frame: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    """Write road-risk features by merging risk rows into road geometry."""

    return _write_joined_geojson(
        geometry_path=roads_geojson_path,
        data_frame=road_risk_frame,
        output_path=output_path,
        join_key="road_id",
        output_name="road_risk",
    )


def _write_joined_geojson(
    geometry_path: str | Path,
    data_frame: pd.DataFrame,
    output_path: str | Path,
    join_key: str,
    output_name: str,
) -> Path:
    if join_key not in data_frame.columns:
        raise ExportError(f"Missing required data column: {join_key}")
    _validate_unique(data_frame, join_key, "data")

    geojson = _read_geojson(geometry_path)
    features_by_key = _features_by_key(geojson, join_key)
    data_keys = set(data_frame[join_key].astype(str))
    missing_geometry = sorted(data_keys - set(features_by_key))
    if missing_geometry:
        raise ExportError(
            f"Missing GeoJSON geometry for {join_key} value(s): "
            + ", ".join(missing_geometry)
        )

    output_features = []
    for _, row in data_frame.iterrows():
        key = str(row[join_key])
        geometry_feature = features_by_key[key]
        properties = dict(geometry_feature.get("properties") or {})
        for column, value in row.items():
            properties[column] = _json_safe(value)
        output_features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometry_feature.get("geometry"),
            }
        )

    output = {
        "type": "FeatureCollection",
        "name": output_name,
        "features": output_features,
    }
    if "crs" in geojson:
        output["crs"] = geojson["crs"]

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return target


def _read_geojson(path: str | Path) -> dict[str, Any]:
    geojson = json.loads(Path(path).read_text(encoding="utf-8"))
    if geojson.get("type") != "FeatureCollection":
        raise ExportError("GeoJSON input must be a FeatureCollection.")
    if not isinstance(geojson.get("features"), list):
        raise ExportError("GeoJSON input must include a features list.")
    return geojson


def _features_by_key(
    geojson: dict[str, Any],
    join_key: str,
) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    missing = 0
    for feature in geojson["features"]:
        properties = feature.get("properties") or {}
        if join_key not in properties:
            missing += 1
            continue
        key = str(properties[join_key])
        if key in by_key:
            duplicates.add(key)
        by_key[key] = feature

    if missing:
        raise ExportError(f"{missing} GeoJSON feature(s) are missing {join_key}.")
    if duplicates:
        raise ExportError(
            f"GeoJSON has duplicate {join_key} value(s): {', '.join(sorted(duplicates))}"
        )
    return by_key


def _validate_unique(frame: pd.DataFrame, column: str, frame_name: str) -> None:
    duplicated = frame[column].astype(str).duplicated(keep=False)
    if duplicated.any():
        values = sorted(set(frame.loc[duplicated, column].astype(str)))
        raise ExportError(
            f"{frame_name} has duplicate {column} value(s): {', '.join(values)}"
        )


def _json_safe(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
