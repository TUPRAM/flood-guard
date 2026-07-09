"""Manual QGIS weak-reference mask inspection helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
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

MANUAL_REFERENCE_COLUMNS: tuple[str, ...] = (
    "source_name",
    "study_area",
    "reference_id",
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
    "required_fields",
    "required_fields_present",
    "missing_fields",
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
    sha256 = _sha256(path)
    fields = metadata["fields"]
    missing = [field for field in REQUIRED_MANUAL_REFERENCE_FIELDS if field not in fields]
    fields_present = len(missing) == 0
    not_official_status = metadata["not_official_status"]
    candidate_allowed = (
        fields_present
        and metadata["feature_count"] > 0
        and not_official_status == "confirmed_true"
    )
    reason = (
        "manual weak-reference candidate is complete for candidate metrics only; "
        "it does not clear official reference-mask or ML-label gates"
        if candidate_allowed
        else _manual_blocker(missing, metadata["feature_count"], not_official_status)
    )
    row = {
        "source_name": "FloodGuard manual QGIS Mae Sai weak-reference candidate",
        "study_area": "Chiang Rai / Mae Sai 2024",
        "reference_id": metadata["reference_id"] or "MANUAL-QGIS-MAE-SAI-2024",
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
        "required_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
        "required_fields_present": fields_present,
        "missing_fields": "|".join(missing),
        "not_official_status": not_official_status,
        "reference_mask_status": "weak_reference_candidate",
        "candidate_readiness_status": (
            "ready_for_candidate_metrics" if candidate_allowed else "incomplete_manual_reference"
        ),
        "allowed_use": (
            "candidate validation metrics; visual QA; non-operational demo reporting"
        ),
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
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
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
        "required_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
        "required_fields_present": False,
        "missing_fields": "|".join(REQUIRED_MANUAL_REFERENCE_FIELDS),
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
            not_official_status = _not_official_status(connection, layer_name, fields)
            return {
                "bbox": tuple("" if value is None else round(float(value), 8) for value in contents),
                "geometry_type": str(geometry[0]),
                "crs": _crs_summary(connection, int(geometry[1])),
                "feature_count": feature_count,
                "fields": fields,
                "reference_id": sample.get("reference_id", ""),
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
) -> str:
    blockers: list[str] = []
    if missing_fields:
        blockers.append(f"missing required fields: {'|'.join(missing_fields)}")
    if feature_count <= 0:
        blockers.append("manual layer has no features")
    if not_official_status != "confirmed_true":
        blockers.append(f"not_official status is {not_official_status}")
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
