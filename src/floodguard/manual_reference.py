"""Manual QGIS weak-reference mask inspection helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import pandas as pd

DEFAULT_EXTERNAL_DATA_DIR = Path.home() / "Documents" / "FloodGuard_external_data"
DEFAULT_MANUAL_REFERENCE_PATH = (
    DEFAULT_EXTERNAL_DATA_DIR
    / "manual_reference"
    / "mae_sai_2024"
    / "mae_sai_manual_flood_reference.gpkg"
)
DEFAULT_MANUAL_REFERENCE_HINT = (
    "<external_data_workspace>/manual_reference/mae_sai_2024/"
    "mae_sai_manual_flood_reference.gpkg"
)
DEFAULT_MANUAL_REFERENCE_LAYER = "manual_flood_extent"

REQUIRED_MANUAL_REFERENCE_FIELDS: tuple[str, ...] = (
    "reference_id",
    "confidence",
    "source_basis",
    "digitized_by",
    "digitized_at",
    "notes",
    "not_official",
)

ALLOWED_MANUAL_REFERENCE_CONFIDENCE: frozenset[str] = frozenset(
    {"low", "medium", "high"}
)

MANUAL_REFERENCE_COLUMNS: tuple[str, ...] = (
    "source_name",
    "study_area",
    "reference_id",
    "confidence",
    "source_basis",
    "digitized_by",
    "digitized_at",
    "notes",
    "file_name",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "file_size_bytes",
    "file_found",
    "source_type",
    "layer_name",
    "geometry_type",
    "crs",
    "bbox_lon_min",
    "bbox_lat_min",
    "bbox_lon_max",
    "bbox_lat_max",
    "feature_count",
    "spatial_relation",
    "in_study_area_overlap",
    "distance_to_study_area_km",
    "spatial_relation_status",
    "required_fields",
    "required_fields_present",
    "missing_fields",
    "attribute_values_status",
    "attribute_value_blockers",
    "not_official_status",
    "reference_mask_status",
    "candidate_readiness_status",
    "allowed_use",
    "not_allowed_use",
    "candidate_validation_metrics_allowed",
    "visual_qa_allowed",
    "non_operational_demo_reporting_allowed",
    "official_validation_truth_allowed",
    "official_warning_allowed",
    "redistributable_source_claim_allowed",
    "unqualified_ml_label_allowed",
    "processing_allowed",
    "reason_blocked",
    "next_action",
    "inspected_at_utc",
)


class ManualReferenceError(ValueError):
    """Raised when a manual weak-reference mask cannot be inspected."""


def inspect_manual_reference_mask(
    reference_path: str | Path = DEFAULT_MANUAL_REFERENCE_PATH,
    *,
    layer_name: str = DEFAULT_MANUAL_REFERENCE_LAYER,
    local_path_hint: str = DEFAULT_MANUAL_REFERENCE_HINT,
    inspected_at_utc: str | None = None,
    allow_missing: bool = True,
    study_area_geometry_path: str | Path | None = None,
) -> pd.DataFrame:
    """Inspect a local manual QGIS weak-reference mask without copying it.

    The resulting row never clears the official reference-mask gate. A complete
    manual mask can support candidate validation metrics and visual QA only.
    """

    path = Path(reference_path)
    timestamp = inspected_at_utc or _utc_now()
    if not path.exists():
        if not allow_missing:
            raise ManualReferenceError(f"Manual reference mask does not exist: {path}")
        return _missing_reference_row(
            path,
            layer_name=layer_name,
            local_path_hint=local_path_hint,
            inspected_at_utc=timestamp,
        )
    if path.suffix.lower() != ".gpkg":
        raise ManualReferenceError("Manual reference mask must be a GeoPackage (.gpkg).")

    metadata = _inspect_geopackage(path, layer_name)
    spatial = (
        _inspect_spatial_relation(path, layer_name, Path(study_area_geometry_path))
        if study_area_geometry_path is not None
        else {
            "spatial_relation": "not_evaluated",
            "in_study_area_overlap": "",
            "distance_to_study_area_km": "",
            "spatial_relation_status": "not_evaluated",
        }
    )
    sha256 = _sha256(path)
    fields = metadata["fields"]
    missing = [field for field in REQUIRED_MANUAL_REFERENCE_FIELDS if field not in fields]
    fields_present = len(missing) == 0
    attribute_blockers = metadata["attribute_value_blockers"]
    not_official_status = metadata["not_official_status"]
    spatial_ready = (
        spatial["spatial_relation_status"] == "verified_geometry_intersection"
        and spatial["spatial_relation"]
        in {"in_study_area_weak_reference", "cross_border_calibration_only"}
        and isinstance(spatial["in_study_area_overlap"], bool)
    )
    candidate_allowed = (
        fields_present
        and metadata["feature_count"] > 0
        and not attribute_blockers
        and not_official_status == "confirmed_true"
        and spatial_ready
    )
    cross_border_only = spatial["spatial_relation"] == "cross_border_calibration_only"
    allowed_use = (
        "cross-border calibration metrics only; visual QA; non-operational demo reporting"
        if cross_border_only
        else "candidate validation metrics; visual QA; non-operational demo reporting"
    )
    candidate_metric_scope = (
        "cross-border calibration metrics only"
        if cross_border_only
        else "candidate metrics only"
    )
    reason = (
        f"manual weak-reference candidate is complete for {candidate_metric_scope}; "
        "it does not clear official reference-mask or ML-label gates"
        if candidate_allowed
        else _manual_blocker(
            missing,
            metadata["feature_count"],
            not_official_status,
            attribute_blockers,
            str(spatial["spatial_relation_status"]),
            str(spatial["spatial_relation"]),
        )
    )
    row = {
        "source_name": "FloodGuard manual QGIS Mae Sai weak-reference candidate",
        "study_area": "Chiang Rai / Mae Sai 2024",
        # A present feature with a blank id is invalid. Never replace it with a
        # plausible-looking synthetic identifier because that would hide the
        # failed source contract.
        "reference_id": metadata["reference_id"],
        "confidence": metadata["confidence"],
        "source_basis": metadata["source_basis"],
        "digitized_by": metadata["digitized_by"],
        "digitized_at": metadata["digitized_at"],
        "notes": metadata["notes"],
        "file_name": path.name,
        "local_path_hint": local_path_hint,
        "sha256": sha256,
        "sha256_status": "recorded",
        "file_size_bytes": path.stat().st_size,
        "file_found": True,
        "source_type": "manual_qgis_weak_reference",
        "layer_name": layer_name,
        "geometry_type": metadata["geometry_type"],
        "crs": metadata["crs"],
        "bbox_lon_min": metadata["bbox"][0],
        "bbox_lat_min": metadata["bbox"][1],
        "bbox_lon_max": metadata["bbox"][2],
        "bbox_lat_max": metadata["bbox"][3],
        "feature_count": metadata["feature_count"],
        **spatial,
        "required_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
        "required_fields_present": fields_present,
        "missing_fields": "|".join(missing),
        "attribute_values_status": (
            "valid" if not attribute_blockers else "invalid"
        ),
        "attribute_value_blockers": "|".join(attribute_blockers),
        "not_official_status": not_official_status,
        "reference_mask_status": "weak_reference_candidate",
        "candidate_readiness_status": (
            "ready_for_candidate_metrics"
            if candidate_allowed
            else (
                "spatially_unqualified"
                if not spatial_ready
                else "incomplete_manual_reference"
            )
        ),
        "allowed_use": allowed_use,
        "not_allowed_use": (
            "official validation truth; official warning; redistributed source data "
            "claim; unqualified ML labels"
        ),
        "candidate_validation_metrics_allowed": candidate_allowed,
        "visual_qa_allowed": candidate_allowed,
        "non_operational_demo_reporting_allowed": candidate_allowed,
        "official_validation_truth_allowed": False,
        "official_warning_allowed": False,
        "redistributable_source_claim_allowed": False,
        "unqualified_ml_label_allowed": False,
        "processing_allowed": False,
        "reason_blocked": reason,
        "next_action": (
            "use only for weak/candidate baseline metrics; keep official validation "
            "and ML-label gates blocked unless a cleared reference mask is acquired"
        ),
        "inspected_at_utc": timestamp,
    }
    return pd.DataFrame([row], columns=MANUAL_REFERENCE_COLUMNS)


def write_manual_reference_manifest(
    output_path: str | Path,
    *,
    reference_path: str | Path = DEFAULT_MANUAL_REFERENCE_PATH,
    layer_name: str = DEFAULT_MANUAL_REFERENCE_LAYER,
    local_path_hint: str = DEFAULT_MANUAL_REFERENCE_HINT,
    inspected_at_utc: str | None = None,
    allow_missing: bool = True,
    study_area_geometry_path: str | Path | None = None,
) -> Path:
    """Write the manual weak-reference manifest CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise ManualReferenceError("Manual reference manifest must be a CSV file.")
    frame = inspect_manual_reference_mask(
        reference_path,
        layer_name=layer_name,
        local_path_hint=local_path_hint,
        inspected_at_utc=inspected_at_utc,
        allow_missing=allow_missing,
        study_area_geometry_path=study_area_geometry_path,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, lineterminator="\n")
    return target


def _missing_reference_row(
    path: Path,
    *,
    layer_name: str,
    local_path_hint: str,
    inspected_at_utc: str,
) -> pd.DataFrame:
    row = {
        "source_name": "FloodGuard manual QGIS Mae Sai weak-reference candidate",
        "study_area": "Chiang Rai / Mae Sai 2024",
        "reference_id": "MANUAL-QGIS-MAE-SAI-2024",
        "confidence": "",
        "source_basis": "",
        "digitized_by": "",
        "digitized_at": "",
        "notes": "",
        "file_name": path.name,
        "local_path_hint": local_path_hint,
        "sha256": "not_acquired",
        "sha256_status": "missing_source_file",
        "file_size_bytes": "",
        "file_found": False,
        "source_type": "manual_qgis_weak_reference",
        "layer_name": layer_name,
        "geometry_type": "not_inspected",
        "crs": "not_inspected",
        "bbox_lon_min": "",
        "bbox_lat_min": "",
        "bbox_lon_max": "",
        "bbox_lat_max": "",
        "feature_count": "",
        "spatial_relation": "not_inspected",
        "in_study_area_overlap": "",
        "distance_to_study_area_km": "",
        "spatial_relation_status": "not_inspected",
        "required_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
        "required_fields_present": False,
        "missing_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
        "attribute_values_status": "not_inspected",
        "attribute_value_blockers": "source_file_missing",
        "not_official_status": "not_inspected",
        "reference_mask_status": "weak_reference_candidate",
        "candidate_readiness_status": "missing_source_file",
        "allowed_use": (
            "candidate validation metrics; visual QA; non-operational demo reporting"
        ),
        "not_allowed_use": (
            "official validation truth; official warning; redistributed source data "
            "claim; unqualified ML labels"
        ),
        "candidate_validation_metrics_allowed": False,
        "visual_qa_allowed": False,
        "non_operational_demo_reporting_allowed": False,
        "official_validation_truth_allowed": False,
        "official_warning_allowed": False,
        "redistributable_source_claim_allowed": False,
        "unqualified_ml_label_allowed": False,
        "processing_allowed": False,
        "reason_blocked": (
            "manual QGIS reference mask not found outside Git; create the GeoPackage "
            "and rerun inspection before candidate metrics"
        ),
        "next_action": (
            "digitize mae_sai_manual_flood_reference.gpkg outside Git with the "
            "required fields, then rerun scripts/inspect_manual_reference_mask.py"
        ),
        "inspected_at_utc": inspected_at_utc,
    }
    return pd.DataFrame([row], columns=MANUAL_REFERENCE_COLUMNS)


def _inspect_geopackage(path: Path, layer_name: str) -> dict[str, object]:
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            contents = _fetch_one(
                connection,
                """
                SELECT min_x, min_y, max_x, max_y
                FROM gpkg_contents
                WHERE table_name = ?
                """,
                (layer_name,),
            )
            if contents is None:
                raise ManualReferenceError(
                    f"GeoPackage layer not found in gpkg_contents: {layer_name}"
                )
            geometry = _fetch_one(
                connection,
                """
                SELECT geometry_type_name, srs_id
                FROM gpkg_geometry_columns
                WHERE table_name = ?
                """,
                (layer_name,),
            )
            if geometry is None:
                raise ManualReferenceError(
                    f"GeoPackage layer not found in gpkg_geometry_columns: {layer_name}"
                )
            fields = _field_names(connection, layer_name)
            quoted_layer = _quote_identifier(layer_name)
            feature_count = int(
                connection.execute(f"SELECT COUNT(*) FROM {quoted_layer}").fetchone()[0]
            )
            sample = _sample_attributes(connection, layer_name, fields)
            attribute_value_blockers = _attribute_value_blockers(
                connection,
                layer_name,
                fields,
            )
            not_official_status = _not_official_status(connection, layer_name, fields)
            return {
                "bbox": tuple("" if value is None else round(float(value), 8) for value in contents),
                "geometry_type": str(geometry[0]),
                "crs": _crs_summary(connection, int(geometry[1])),
                "feature_count": feature_count,
                "fields": fields,
                "reference_id": sample.get("reference_id", "").strip(),
                "confidence": sample.get("confidence", "").strip(),
                "source_basis": sample.get("source_basis", "").strip(),
                "digitized_by": sample.get("digitized_by", "").strip(),
                "digitized_at": sample.get("digitized_at", "").strip(),
                "notes": sample.get("notes", "").strip(),
                "attribute_value_blockers": attribute_value_blockers,
                "not_official_status": not_official_status,
            }
    except sqlite3.DatabaseError as exc:
        raise ManualReferenceError(f"Could not inspect GeoPackage metadata: {exc}") from exc


def _fetch_one(
    connection: sqlite3.Connection,
    query: str,
    parameters: Sequence[object],
) -> tuple[object, ...] | None:
    return connection.execute(query, tuple(parameters)).fetchone()


def _field_names(connection: sqlite3.Connection, layer_name: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({_quote_identifier(layer_name)})").fetchall()
    if not rows:
        raise ManualReferenceError(f"GeoPackage feature table not found: {layer_name}")
    return [str(row[1]) for row in rows]


def _sample_attributes(
    connection: sqlite3.Connection,
    layer_name: str,
    fields: list[str],
) -> dict[str, str]:
    selected = [field for field in REQUIRED_MANUAL_REFERENCE_FIELDS if field in fields]
    if not selected:
        return {}
    quoted_fields = ", ".join(_quote_identifier(field) for field in selected)
    quoted_layer = _quote_identifier(layer_name)
    row = connection.execute(
        f"SELECT {quoted_fields} FROM {quoted_layer} LIMIT 1"
    ).fetchone()
    if row is None:
        return {}
    return {field: "" if value is None else str(value) for field, value in zip(selected, row)}


def _not_official_status(
    connection: sqlite3.Connection,
    layer_name: str,
    fields: list[str],
) -> str:
    if "not_official" not in fields:
        return "missing_field"
    quoted_layer = _quote_identifier(layer_name)
    rows = connection.execute(f"SELECT not_official FROM {quoted_layer}").fetchall()
    if not rows:
        return "no_features"
    normalized = {_normalize_bool(value[0]) for value in rows}
    if normalized == {True}:
        return "confirmed_true"
    if False in normalized:
        return "contains_false"
    return "unresolved_values"


def _inspect_spatial_relation(
    reference_path: Path,
    layer_name: str,
    study_area_geometry_path: Path,
) -> dict[str, object]:
    if not study_area_geometry_path.is_file():
        raise ManualReferenceError(
            f"Study-area geometry does not exist: {study_area_geometry_path}"
        )
    try:
        from floodguard.sar_raster_extract import read_manual_reference_geometries

        manual_geometries, reference_crs = read_manual_reference_geometries(
            reference_path,
            layer_name=layer_name,
        )
        if reference_crs.upper() != "EPSG:4326":
            raise ManualReferenceError(
                "Manual-reference spatial comparison requires EPSG:4326 geometry."
            )
        payload = json.loads(study_area_geometry_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        study_geometries = [
            feature["geometry"]
            for feature in features
            if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict)
        ]
        if not study_geometries:
            raise ManualReferenceError("Study-area GeoJSON has no feature geometries.")
        return _classify_spatial_relation(manual_geometries, study_geometries)
    except ManualReferenceError:
        raise
    except Exception as exc:
        raise ManualReferenceError(
            f"Could not verify manual-reference spatial relation: {exc}"
        ) from exc


def _classify_spatial_relation(
    manual_geometries: Sequence[dict[str, object]],
    study_area_geometries: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Classify and measure the manual mask against official ADM3 geometry."""

    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    project = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:32647",
        always_xy=True,
    ).transform
    manual = _validated_polygon_union(
        manual_geometries,
        label="Manual-reference",
        shape=shape,
        unary_union=unary_union,
    )
    study_area = _validated_polygon_union(
        study_area_geometries,
        label="Study-area",
        shape=shape,
        unary_union=unary_union,
    )
    projected_manual = transform(project, manual)
    projected_study_area = transform(project, study_area)
    if projected_manual.area <= 0 or projected_study_area.area <= 0:
        raise ManualReferenceError(
            "Spatial comparison polygons must have positive projected area."
        )
    overlap = bool(manual.intersects(study_area))
    distance_km = projected_manual.distance(projected_study_area) / 1000
    return {
        "spatial_relation": (
            "in_study_area_weak_reference"
            if overlap
            else "cross_border_calibration_only"
        ),
        "in_study_area_overlap": overlap,
        "distance_to_study_area_km": round(float(distance_km), 6),
        "spatial_relation_status": "verified_geometry_intersection",
    }


def _validated_polygon_union(
    geometries: Sequence[dict[str, object]],
    *,
    label: str,
    shape: object,
    unary_union: object,
) -> object:
    """Return a valid polygonal union or fail before spatial classification."""

    if not geometries:
        raise ManualReferenceError(f"{label} geometry collection must not be empty.")
    parsed: list[object] = []
    for index, geometry_mapping in enumerate(geometries, start=1):
        geometry_type = str(geometry_mapping.get("type", ""))
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise ManualReferenceError(
                f"{label} geometry {index} must be Polygon or MultiPolygon."
            )
        try:
            geometry = shape(geometry_mapping)  # type: ignore[operator]
        except Exception as exc:
            raise ManualReferenceError(
                f"{label} geometry {index} could not be parsed: {exc}"
            ) from exc
        bounds = tuple(float(value) for value in geometry.bounds)
        if (
            geometry.is_empty
            or not geometry.is_valid
            or geometry.area <= 0
            or len(bounds) != 4
            or not all(math.isfinite(value) for value in bounds)
        ):
            raise ManualReferenceError(
                f"{label} geometry {index} must be non-empty, valid, finite, "
                "and have positive area."
            )
        parsed.append(geometry)
    union = unary_union(parsed)  # type: ignore[operator]
    if union.is_empty or not union.is_valid:
        raise ManualReferenceError(f"{label} geometry union must be non-empty and valid.")
    return union


def _attribute_value_blockers(
    connection: sqlite3.Connection,
    layer_name: str,
    fields: list[str],
) -> list[str]:
    """Return deterministic blockers for invalid per-feature attributes.

    The literal ``[blank]`` is accepted for ``digitized_by`` because the
    manual-mask protocol uses it as an explicit disclosure that the operator
    identity was not recorded. A SQL NULL or empty string is not equivalent:
    it is ambiguous and therefore fails closed.
    """

    selected = [field for field in REQUIRED_MANUAL_REFERENCE_FIELDS if field in fields]
    if not selected:
        return []
    quoted_fields = ", ".join(_quote_identifier(field) for field in selected)
    quoted_layer = _quote_identifier(layer_name)
    rows = connection.execute(
        f"SELECT {quoted_fields} FROM {quoted_layer} ORDER BY rowid"
    ).fetchall()
    blockers: list[str] = []
    reference_ids: list[str] = []
    required_text_fields = (
        "reference_id",
        "confidence",
        "source_basis",
        "digitized_by",
        "digitized_at",
        "notes",
    )
    for feature_number, row in enumerate(rows, start=1):
        values = dict(zip(selected, row))
        texts = {
            field: "" if values.get(field) is None else str(values[field]).strip()
            for field in required_text_fields
            if field in values
        }
        for field, text in texts.items():
            if not text:
                blockers.append(f"feature_{feature_number}:{field}:blank")

        reference_id = texts.get("reference_id", "")
        if reference_id:
            reference_ids.append(reference_id)

        confidence = texts.get("confidence", "")
        if confidence and confidence.lower() not in ALLOWED_MANUAL_REFERENCE_CONFIDENCE:
            blockers.append(
                f"feature_{feature_number}:confidence:invalid_{confidence.lower()}"
            )

        digitized_by = texts.get("digitized_by", "")
        if digitized_by.lower() in {"blank", "none", "unknown", "n/a", "na"}:
            blockers.append(
                f"feature_{feature_number}:digitized_by:explicit_placeholder_required"
            )

        digitized_at = texts.get("digitized_at", "")
        if digitized_at:
            try:
                datetime.strptime(digitized_at, "%Y-%m-%d")
            except ValueError:
                blockers.append(
                    f"feature_{feature_number}:digitized_at:invalid_iso_date"
                )

    duplicates = sorted(
        reference_id
        for reference_id in set(reference_ids)
        if reference_ids.count(reference_id) > 1
    )
    blockers.extend(f"reference_id:duplicate_{value}" for value in duplicates)
    return blockers


def _normalize_bool(value: object) -> bool | str:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return "unresolved"


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


def _quote_identifier(value: str) -> str:
    if "\x00" in value:
        raise ManualReferenceError("Invalid GeoPackage identifier.")
    return '"' + value.replace('"', '""') + '"'


def _manual_blocker(
    missing_fields: list[str],
    feature_count: int,
    not_official_status: str,
    attribute_value_blockers: list[str],
    spatial_relation_status: str,
    spatial_relation: str,
) -> str:
    blockers: list[str] = []
    if missing_fields:
        blockers.append(f"missing required fields: {'|'.join(missing_fields)}")
    if feature_count <= 0:
        blockers.append("manual layer has no features")
    if attribute_value_blockers:
        blockers.append(
            "invalid feature attributes: " + "|".join(attribute_value_blockers)
        )
    if not_official_status != "confirmed_true":
        blockers.append(f"not_official status is {not_official_status}")
    if (
        spatial_relation_status != "verified_geometry_intersection"
        or spatial_relation
        not in {"in_study_area_weak_reference", "cross_border_calibration_only"}
    ):
        blockers.append(
            "manual-reference spatial relation is not verified for a supported scope"
        )
    blockers.append("manual weak-reference lane does not clear official validation or ML-label gates")
    return "; ".join(blockers)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
