"""Summarise a weak polygon over canonical query cores without creating truth.

The existing Mae Sai polygon is positive-unlabelled evidence: polygon-covered
cell centres are weak positives and every other cell remains unreviewed.  This
module converts that evidence into one internal summary row per canonical query
so an operator can inspect weak-reference overlap while the reviewer-facing
bundle remains blinded.

The source vector, its safety manifest, and the canonical query manifest are
all checksum-bound.  Outputs are immutable, self-hashed, query-model-only, and
explicitly ineligible for decision, FPPS, warning, or training use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping

import numpy as np
import pandas as pd

from floodguard.label_factory.contracts import QUERY_MODEL_ELIGIBILITY


WEAK_QUERY_SUMMARY_SCHEMA = "floodguard.weak_query_summary.v1"
WEAK_QUERY_SUMMARY_FILENAME = "weak_query_summary.csv"
WEAK_QUERY_MANIFEST_FILENAME = "weak_query_summary_manifest.json"

REQUIRED_QUERY_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "event_id",
    "tile_id",
    "grid_contract_sha256",
    "query_size_pixels",
    "resolution_m",
    "bbox_min_x",
    "bbox_min_y",
    "bbox_max_x",
    "bbox_max_y",
    "crs",
    "dataset_role",
    "query_model_only",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

SUMMARY_COLUMNS: tuple[str, ...] = (
    "query_region_id",
    "event_id",
    "tile_id",
    "grid_contract_sha256",
    "weak_label",
    "weak_positive_fraction",
    "weak_uncertain_fraction",
    "weak_unreviewed_fraction",
    "weak_boundary_query",
    "weak_source_type",
    "weak_source_file_hint",
    "weak_source_sha256",
    "weak_source_manifest_sha256",
    "query_manifest_sha256",
    "weak_summary_manifest_sha256",
    "source_timestamp",
    "confidence_class",
    "assumptions",
    "operator_internal_only",
    "selection_creates_flood_truth",
    "eligible_for_query_model_training",
    "model_purpose",
    "query_model_only",
    "eligible_for_review_queue",
    "eligible_for_training_after_human_review",
    "eligible_for_decision_layer",
    "eligible_for_fpps",
    "eligible_for_warning",
)

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class WeakQuerySummaryError(ValueError):
    """Raised when weak evidence cannot be summarised without ambiguity."""


@dataclass(frozen=True, slots=True)
class WeakQuerySummaryPaths:
    """Paths published for one immutable weak-query summary."""

    summary_csv: Path
    manifest_json: Path

    def as_dict(self) -> dict[str, Path]:
        """Return paths under stable artifact labels."""

        return {
            "summary_csv": self.summary_csv,
            "manifest_json": self.manifest_json,
        }


def build_weak_query_summary(
    *,
    weak_vector_path: str | Path,
    weak_source_manifest: pd.DataFrame | str | Path,
    query_manifest: pd.DataFrame | str | Path,
    vector_layer: str | None = None,
    repair_invalid_geometry: bool = False,
    generated_at_utc: datetime | str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return positive-unlabelled overlap summaries and unsigned provenance.

    The vector is reprojected to the one projected CRS declared by the query
    manifest.  Inclusion uses canonical query-cell centres.  A zero overlap is
    labelled ``unreviewed`` rather than dry land; a non-zero overlap is labelled
    ``weak_positive_present``.  No binary non-flood label is manufactured.
    """

    vector_path = _existing_file(weak_vector_path, "weak vector")
    source_manifest_path: Path | None = None
    if isinstance(weak_source_manifest, pd.DataFrame):
        source_manifest = weak_source_manifest.copy().fillna("")
    else:
        source_manifest_path = _existing_file(
            weak_source_manifest, "weak source manifest"
        )
        source_manifest = _read_csv(source_manifest_path, "weak source manifest")
    query_manifest_path: Path | None = None
    if isinstance(query_manifest, pd.DataFrame):
        queries = query_manifest.copy().fillna("")
    else:
        query_manifest_path = _existing_file(query_manifest, "query manifest")
        queries = _read_csv(query_manifest_path, "query manifest")

    _require_columns(queries, REQUIRED_QUERY_COLUMNS, "query manifest")
    if queries.empty:
        raise WeakQuerySummaryError("Query manifest must not be empty.")
    if queries["query_region_id"].astype(str).duplicated().any():
        raise WeakQuerySummaryError("query_region_id must be unique.")
    _validate_query_safety(queries)
    crs_values = tuple(sorted(set(queries["crs"].astype(str).str.strip())))
    if len(crs_values) != 1 or not crs_values[0]:
        raise WeakQuerySummaryError("Query manifest must declare exactly one CRS.")
    grid_hashes = tuple(
        sorted(set(queries["grid_contract_sha256"].astype(str).str.lower()))
    )
    if len(grid_hashes) != 1 or not _SHA256_PATTERN.fullmatch(grid_hashes[0]):
        raise WeakQuerySummaryError(
            "Query manifest must declare one complete grid-contract SHA-256."
        )

    vector_hash = _file_sha256(vector_path)
    source_row, source_manifest_hash = _validate_source_manifest(
        source_manifest,
        vector_path=vector_path,
        vector_hash=vector_hash,
        source_manifest_path=source_manifest_path,
    )
    source_timestamp = _utc_timestamp(
        source_row.get("inspected_at_utc") or source_row.get("source_timestamp")
    )
    generated_timestamp = _utc_timestamp(generated_at_utc or "")
    query_manifest_hash = (
        _file_sha256(query_manifest_path)
        if query_manifest_path is not None
        else _frame_sha256(queries)
    )

    gpd, shapely = _load_geo_runtime()
    try:
        vectors = gpd.read_file(vector_path, layer=vector_layer)
    except Exception as exc:  # pragma: no cover - backend-specific exception set
        raise WeakQuerySummaryError(f"Could not read weak vector: {exc}") from exc
    if vectors.empty or "geometry" not in vectors:
        raise WeakQuerySummaryError("Weak vector contains no geometry.")
    if vectors.crs is None:
        raise WeakQuerySummaryError("Weak vector must declare its source CRS.")
    if not isinstance(repair_invalid_geometry, bool):
        raise WeakQuerySummaryError("repair_invalid_geometry must be boolean.")
    geometries = vectors.geometry
    if geometries.isna().any() or geometries.is_empty.any():
        raise WeakQuerySummaryError("Weak vector contains null or empty geometry.")
    invalid_mask = ~geometries.is_valid
    invalid_reasons = [
        str(shapely.is_valid_reason(geometry))
        for geometry in geometries.loc[invalid_mask]
    ]
    if invalid_mask.any():
        if not repair_invalid_geometry:
            details = "; ".join(invalid_reasons[:3])
            raise WeakQuerySummaryError(
                "Weak vector contains invalid geometry"
                + (f": {details}." if details else ".")
            )
        repaired = [
            shapely.make_valid(geometry) if is_invalid else geometry
            for geometry, is_invalid in zip(geometries, invalid_mask)
        ]
        repaired_types = {str(geometry.geom_type) for geometry in repaired}
        unsupported_repaired = sorted(
            repaired_types - {"Polygon", "MultiPolygon"}
        )
        if unsupported_repaired or any(
            geometry.is_empty or not geometry.is_valid for geometry in repaired
        ):
            raise WeakQuerySummaryError(
                "make_valid did not produce only valid polygonal geometry; found: "
                + ", ".join(unsupported_repaired or sorted(repaired_types))
            )
        vectors = vectors.copy()
        vectors.geometry = gpd.GeoSeries(repaired, index=vectors.index, crs=vectors.crs)
        geometries = vectors.geometry
    unsupported = sorted(
        set(geometries.geom_type.astype(str)) - {"Polygon", "MultiPolygon"}
    )
    if unsupported:
        raise WeakQuerySummaryError(
            "Weak vector must contain only polygon geometry; found: "
            + ", ".join(unsupported)
        )
    if "not_official" in vectors:
        if not vectors["not_official"].map(_strict_bool).all():
            raise WeakQuerySummaryError(
                "Every weak-vector feature must retain not_official=true."
            )
    try:
        projected = vectors.to_crs(crs_values[0])
    except Exception as exc:  # pragma: no cover - backend-specific exception set
        raise WeakQuerySummaryError(
            f"Could not reproject weak vector to {crs_values[0]}: {exc}"
        ) from exc
    union = projected.geometry.union_all()
    if union.is_empty or not union.is_valid:
        raise WeakQuerySummaryError("Reprojected weak geometry union is invalid.")

    assumptions = (
        "Positive-unlabelled weak-reference overlap from canonical cell centres; "
        "polygon exterior is unreviewed, never dry land; no human review, flood "
        "truth, model target, decision-layer, FPPS, warning, or field-validation "
        "status is created."
    )
    rows: list[dict[str, object]] = []
    for row_number, query in queries.sort_values(
        "query_region_id", kind="stable"
    ).reset_index(drop=True).iterrows():
        query_id = _non_blank(
            query["query_region_id"], "query_region_id", row_number
        )
        size = _positive_integer(
            query["query_size_pixels"], "query_size_pixels", row_number
        )
        resolution = _positive_number(
            query["resolution_m"], "resolution_m", row_number
        )
        xmin, ymin, xmax, ymax = (
            _finite_number(query[column], column, row_number)
            for column in (
                "bbox_min_x",
                "bbox_min_y",
                "bbox_max_x",
                "bbox_max_y",
            )
        )
        if not xmin < xmax or not ymin < ymax:
            raise WeakQuerySummaryError(
                f"Query {query_id!r} has invalid projected bounds."
            )
        tolerance = max(resolution, 1.0) * 1e-7
        if not math.isclose(xmax - xmin, size * resolution, abs_tol=tolerance):
            raise WeakQuerySummaryError(
                f"Query {query_id!r} width does not match size and resolution."
            )
        if not math.isclose(ymax - ymin, size * resolution, abs_tol=tolerance):
            raise WeakQuerySummaryError(
                f"Query {query_id!r} height does not match size and resolution."
            )
        x = xmin + (np.arange(size, dtype=float) + 0.5) * resolution
        y = ymax - (np.arange(size, dtype=float) + 0.5) * resolution
        xx, yy = np.meshgrid(x, y)
        # intersects_xy includes the measure-zero case where a cell centre lies
        # exactly on the polygon boundary and is deterministic across input order.
        covered = np.asarray(shapely.intersects_xy(union, xx, yy), dtype=bool)
        positive_count = int(np.count_nonzero(covered))
        cell_count = int(covered.size)
        positive_fraction = positive_count / cell_count
        unreviewed_fraction = 1.0 - positive_fraction
        boundary_query = 0 < positive_count < cell_count
        weak_label = "weak_positive_present" if positive_count else "unreviewed"
        rows.append(
            {
                "query_region_id": query_id,
                "event_id": _non_blank(query["event_id"], "event_id", row_number),
                "tile_id": _non_blank(query["tile_id"], "tile_id", row_number),
                "grid_contract_sha256": grid_hashes[0],
                "weak_label": weak_label,
                "weak_positive_fraction": positive_fraction,
                "weak_uncertain_fraction": 0.0,
                "weak_unreviewed_fraction": unreviewed_fraction,
                "weak_boundary_query": boundary_query,
                "weak_source_type": "positive_unlabeled_weak_seed",
                "weak_source_file_hint": vector_path.name,
                "weak_source_sha256": vector_hash,
                "weak_source_manifest_sha256": source_manifest_hash,
                "query_manifest_sha256": query_manifest_hash,
                # Filled after the unsigned manifest is canonicalised.
                "weak_summary_manifest_sha256": "",
                "source_timestamp": source_timestamp,
                "confidence_class": "low",
                "assumptions": assumptions,
                "operator_internal_only": True,
                "selection_creates_flood_truth": False,
                "eligible_for_query_model_training": False,
                **QUERY_MODEL_ELIGIBILITY.as_manifest_fields(),
            }
        )
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    if summary.empty or len(summary) != len(queries):
        raise WeakQuerySummaryError("Weak summary did not preserve query coverage.")
    manifest: dict[str, Any] = {
        "artifact_schema": WEAK_QUERY_SUMMARY_SCHEMA,
        "created_at_utc": generated_timestamp,
        "source": {
            "file_hint": vector_path.name,
            "file_sha256": vector_hash,
            "layer": vector_layer or "",
            "source_crs": str(vectors.crs),
            "feature_count": int(len(vectors)),
            "source_manifest_sha256": source_manifest_hash,
            "source_status": "weak_reference_candidate_positive_unlabeled_only",
            "geometry_validation": {
                "invalid_feature_count": int(invalid_mask.sum()),
                "invalid_reasons": invalid_reasons,
                "repair_requested": repair_invalid_geometry,
                "repair_method": (
                    "shapely.make_valid"
                    if repair_invalid_geometry and bool(invalid_mask.any())
                    else "none"
                ),
                "repaired_geometry_is_not_new_truth": True,
            },
        },
        "query_contract": {
            "query_manifest_sha256": query_manifest_hash,
            "grid_contract_sha256": grid_hashes[0],
            "target_crs": crs_values[0],
            "query_count": int(len(summary)),
        },
        "interpretation": {
            "covered_cell_centres": "weak_positive",
            "exterior_cell_centres": "unreviewed_not_dry",
            "weak_uncertain_fraction": "0 because no boundary buffer was applied",
            "reviewed_truth": False,
        },
        "counts": {
            "queries_with_weak_positive": int(
                summary["weak_positive_fraction"].gt(0).sum()
            ),
            "weak_boundary_queries": int(summary["weak_boundary_query"].sum()),
            "fully_unreviewed_queries": int(
                summary["weak_positive_fraction"].eq(0).sum()
            ),
        },
        "safety": {
            "operator_internal_only": True,
            "selection_creates_flood_truth": False,
            "eligible_for_query_model_training": False,
            **QUERY_MODEL_ELIGIBILITY.as_manifest_fields(),
        },
        "assumptions": assumptions,
    }
    return summary, manifest


def write_weak_query_summary(
    *,
    weak_vector_path: str | Path,
    weak_source_manifest: pd.DataFrame | str | Path,
    query_manifest: pd.DataFrame | str | Path,
    output_directory: str | Path,
    vector_layer: str | None = None,
    repair_invalid_geometry: bool = False,
    generated_at_utc: datetime | str | None = None,
) -> WeakQuerySummaryPaths:
    """Build and atomically publish a write-once CSV plus self-hashed JSON."""

    output = Path(output_directory)
    if output.exists():
        raise WeakQuerySummaryError(
            f"Output directory already exists and cannot be overwritten: {output}"
        )
    summary, manifest = build_weak_query_summary(
        weak_vector_path=weak_vector_path,
        weak_source_manifest=weak_source_manifest,
        query_manifest=query_manifest,
        vector_layer=vector_layer,
        repair_invalid_geometry=repair_invalid_geometry,
        generated_at_utc=generated_at_utc,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        csv_path = temporary / WEAK_QUERY_SUMMARY_FILENAME
        manifest_path = temporary / WEAK_QUERY_MANIFEST_FILENAME
        # Serialise once with a blank manifest binding so the logical hash uses
        # exactly the same string representation that a later reader observes.
        summary.to_csv(
            csv_path,
            index=False,
            lineterminator="\n",
            float_format="%.17g",
        )
        serialized = _read_csv(csv_path, "provisional weak summary CSV")
        manifest["summary_logical_sha256"] = _frame_sha256(
            serialized.drop(columns=["weak_summary_manifest_sha256"])
        )
        manifest_hash = _canonical_sha256(manifest)
        manifest["manifest_sha256"] = manifest_hash
        summary["weak_summary_manifest_sha256"] = manifest_hash
        summary.to_csv(
            csv_path,
            index=False,
            lineterminator="\n",
            float_format="%.17g",
        )
        manifest_path.write_text(_json_text(manifest), encoding="utf-8")
        if output.exists():
            raise WeakQuerySummaryError(
                f"Output directory appeared during build: {output}"
            )
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return WeakQuerySummaryPaths(
        summary_csv=output / WEAK_QUERY_SUMMARY_FILENAME,
        manifest_json=output / WEAK_QUERY_MANIFEST_FILENAME,
    )


def verify_weak_query_summary(
    *, summary_csv: str | Path, manifest_json: str | Path
) -> pd.DataFrame:
    """Revalidate a published weak-query summary and its safety contract."""

    csv_path = _existing_file(summary_csv, "weak summary CSV")
    manifest_path = _existing_file(manifest_json, "weak summary manifest")
    manifest = _load_json_object(manifest_path, "weak summary manifest")
    if manifest.get("artifact_schema") != WEAK_QUERY_SUMMARY_SCHEMA:
        raise WeakQuerySummaryError("Weak summary manifest schema is unsupported.")
    declared_hash = str(manifest.get("manifest_sha256", "")).lower()
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    if not _SHA256_PATTERN.fullmatch(declared_hash) or _canonical_sha256(
        unsigned
    ) != declared_hash:
        raise WeakQuerySummaryError("Weak summary manifest self-hash is invalid.")
    frame = _read_csv(csv_path, "weak summary CSV")
    _require_columns(frame, SUMMARY_COLUMNS, "weak summary CSV")
    if frame.empty or frame["query_region_id"].duplicated().any():
        raise WeakQuerySummaryError("Weak summary query ids must be non-empty and unique.")
    if not frame["weak_summary_manifest_sha256"].astype(str).eq(declared_hash).all():
        raise WeakQuerySummaryError("Weak summary rows do not bind the manifest hash.")
    logical = frame.drop(columns=["weak_summary_manifest_sha256"])
    if manifest.get("summary_logical_sha256") != _frame_sha256(logical):
        raise WeakQuerySummaryError("Weak summary logical row hash does not match manifest.")
    safety = manifest.get("safety")
    if not isinstance(safety, Mapping):
        raise WeakQuerySummaryError("Weak summary manifest safety block is missing.")
    expected = {
        "operator_internal_only": True,
        "selection_creates_flood_truth": False,
        "eligible_for_query_model_training": False,
        **QUERY_MODEL_ELIGIBILITY.as_manifest_fields(),
    }
    for field, value in expected.items():
        if safety.get(field) is not value and safety.get(field) != value:
            raise WeakQuerySummaryError(f"Weak summary safety field {field} changed.")
        if field not in frame:
            raise WeakQuerySummaryError(f"Weak summary rows are missing {field}.")
        observed = (
            frame[field].map(_strict_bool)
            if isinstance(value, bool)
            else frame[field].astype(str)
        )
        if not observed.eq(value).all():
            raise WeakQuerySummaryError(f"Weak summary row safety field {field} changed.")
    fractions = frame[
        [
            "weak_positive_fraction",
            "weak_uncertain_fraction",
            "weak_unreviewed_fraction",
        ]
    ].apply(pd.to_numeric, errors="coerce")
    if fractions.isna().any().any() or not (
        (fractions >= 0.0) & (fractions <= 1.0)
    ).all().all():
        raise WeakQuerySummaryError("Weak summary fractions must be in 0..1.")
    if not np.allclose(fractions.sum(axis=1), 1.0, atol=1e-9, rtol=0.0):
        raise WeakQuerySummaryError("Weak summary fractions must sum to one.")
    return frame


def _validate_source_manifest(
    frame: pd.DataFrame,
    *,
    vector_path: Path,
    vector_hash: str,
    source_manifest_path: Path | None,
) -> tuple[Mapping[str, object], str]:
    required = (
        "file_name",
        "sha256",
        "reference_mask_status",
        "candidate_validation_metrics_allowed",
        "official_validation_truth_allowed",
        "unqualified_ml_label_allowed",
    )
    _require_columns(frame, required, "weak source manifest")
    matches = frame[frame["file_name"].astype(str).eq(vector_path.name)]
    if len(matches) != 1:
        raise WeakQuerySummaryError(
            "Weak source manifest must contain exactly one row for the vector filename."
        )
    row = matches.iloc[0].to_dict()
    if str(row["sha256"]).strip().lower() != vector_hash:
        raise WeakQuerySummaryError("Weak vector hash differs from source manifest.")
    if str(row["reference_mask_status"]).strip() != "weak_reference_candidate":
        raise WeakQuerySummaryError("Source is not declared a weak-reference candidate.")
    if not _strict_bool(row["candidate_validation_metrics_allowed"]):
        raise WeakQuerySummaryError("Weak source is not allowed for candidate diagnostics.")
    if _strict_bool(row["official_validation_truth_allowed"]):
        raise WeakQuerySummaryError("Weak source must not claim official validation truth.")
    if _strict_bool(row["unqualified_ml_label_allowed"]):
        raise WeakQuerySummaryError("Weak source must not allow unqualified ML labels.")
    manifest_hash = (
        _file_sha256(source_manifest_path)
        if source_manifest_path is not None
        else _frame_sha256(frame)
    )
    return row, manifest_hash


def _validate_query_safety(frame: pd.DataFrame) -> None:
    expected = QUERY_MODEL_ELIGIBILITY.as_manifest_fields()
    for field in (
        "query_model_only",
        "eligible_for_decision_layer",
        "eligible_for_fpps",
        "eligible_for_warning",
    ):
        required = expected[field]
        observed = frame[field].map(_strict_bool)
        if not observed.eq(required).all():
            raise WeakQuerySummaryError(
                f"Query safety field {field} must remain {required}."
            )


def _load_geo_runtime() -> tuple[Any, Any]:
    try:
        import geopandas as gpd
        import shapely
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise WeakQuerySummaryError(
            "Weak query summaries require the optional geo dependencies."
        ) from exc
    if not hasattr(shapely, "intersects_xy"):
        raise WeakQuerySummaryError("Weak query summaries require Shapely 2 or newer.")
    return gpd, shapely


def _strict_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise WeakQuerySummaryError(f"Expected an explicit boolean; found {value!r}.")


def _non_blank(value: object, field: str, row_number: int) -> str:
    text = str(value).strip()
    if not text:
        raise WeakQuerySummaryError(f"Row {row_number} {field} must not be blank.")
    return text


def _positive_integer(value: object, field: str, row_number: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeakQuerySummaryError(
            f"Row {row_number} {field} must be a positive integer."
        ) from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise WeakQuerySummaryError(
            f"Row {row_number} {field} must be a positive integer."
        )
    return int(number)


def _positive_number(value: object, field: str, row_number: int) -> float:
    number = _finite_number(value, field, row_number)
    if number <= 0:
        raise WeakQuerySummaryError(f"Row {row_number} {field} must be positive.")
    return number


def _finite_number(value: object, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeakQuerySummaryError(
            f"Row {row_number} {field} must be finite."
        ) from exc
    if not math.isfinite(number):
        raise WeakQuerySummaryError(f"Row {row_number} {field} must be finite.")
    return number


def _utc_timestamp(value: object) -> str:
    text = str(value).strip()
    if not text:
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WeakQuerySummaryError("Source timestamp is not valid ISO-8601.") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise WeakQuerySummaryError("Source timestamp must be timezone-aware.")
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_columns(
    frame: pd.DataFrame, required: tuple[str, ...], label: str
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise WeakQuerySummaryError(
            f"{label} is missing columns: {', '.join(missing)}."
        )


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise WeakQuerySummaryError(f"{label} does not exist: {path}")
    return path


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype=object, keep_default_na=False)
    except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise WeakQuerySummaryError(f"Could not read {label}: {exc}") from exc


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WeakQuerySummaryError(f"Could not read {label}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise WeakQuerySummaryError(f"{label} root must be an object.")
    return value


def _frame_sha256(frame: pd.DataFrame) -> str:
    normalized = frame.copy().fillna("")
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    normalized = normalized.sort_values(list(normalized.columns), kind="stable")
    encoded = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise WeakQuerySummaryError(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WeakQuerySummaryError(f"Artifact is not canonical JSON: {exc}") from exc
    return hashlib.sha256(encoded).hexdigest()


def _json_text(value: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
