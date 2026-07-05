"""Manual visual-review checklist helpers for THEOS-2 optical context."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REVIEW_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "preview_path",
    "preview_source",
    "visible_water_context",
    "built_up_area_context",
    "road_context",
    "cloud_haze_status",
    "exposure_explanation_usefulness",
    "review_status",
    "reviewer",
    "review_date",
    "review_notes",
    "flood_label_claim",
    "assumptions",
)

SELECTED_REQUIRED_COLUMNS: tuple[str, ...] = (
    "file_name",
    "source_timestamp",
    "category",
    "preview_path",
    "processing_scope",
    "reference_mask_status",
    "processing_allowed",
)

THUMBNAIL_COLUMNS: tuple[str, ...] = (
    "file_name",
    "thumbnail_path",
    "thumbnail_format",
    "raster_reader",
)


class THEOS2ReviewError(ValueError):
    """Raised when THEOS-2 visual-review checklist inputs are invalid."""


def build_theos2_visual_review_checklist(
    selected_manifest: str | Path | pd.DataFrame,
    thumbnail_manifest: str | Path | pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a pending manual-review checklist for selected THEOS-2 previews."""

    selected = _coerce_frame(selected_manifest)
    _require_columns(selected, SELECTED_REQUIRED_COLUMNS, "selected manifest")
    thumbnail_lookup = _thumbnail_lookup(thumbnail_manifest)
    rows: list[dict[str, object]] = []
    for row in selected.to_dict(orient="records"):
        _validate_selected_row(row)
        thumbnail_row = thumbnail_lookup.get(str(row["file_name"]))
        if thumbnail_row is None:
            preview_path = row["preview_path"]
            preview_source = "metadata_svg_preview"
        else:
            preview_path = thumbnail_row["thumbnail_path"]
            preview_source = (
                f"true_{thumbnail_row['thumbnail_format']}_thumbnail_"
                f"via_{thumbnail_row['raster_reader']}"
            )
        rows.append(
            {
                "file_name": row["file_name"],
                "source_timestamp": row["source_timestamp"],
                "category": row["category"],
                "preview_path": preview_path,
                "preview_source": preview_source,
                "visible_water_context": "not_reviewed",
                "built_up_area_context": "not_reviewed",
                "road_context": "not_reviewed",
                "cloud_haze_status": "not_reviewed",
                "exposure_explanation_usefulness": "not_reviewed",
                "review_status": "pending_manual_review",
                "reviewer": "",
                "review_date": "",
                "review_notes": "",
                "flood_label_claim": "not_allowed",
                "assumptions": (
                    "Manual THEOS-2 optical-context review only; not flood validation, "
                    "not a reference mask, not an official warning, and not ML labels."
                ),
            }
        )
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)


def write_theos2_visual_review_checklist(
    selected_manifest_path: str | Path,
    output_path: str | Path,
    thumbnail_manifest_path: str | Path | None = None,
) -> Path:
    """Write the THEOS-2 visual-review checklist CSV."""

    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise THEOS2ReviewError("THEOS-2 visual-review checklist output must be CSV.")
    thumbnail_source = (
        thumbnail_manifest_path
        if thumbnail_manifest_path and Path(thumbnail_manifest_path).exists()
        else None
    )
    checklist = build_theos2_visual_review_checklist(
        selected_manifest_path,
        thumbnail_source,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    checklist.to_csv(target, index=False)
    return target


def _thumbnail_lookup(
    thumbnail_manifest: str | Path | pd.DataFrame | None,
) -> dict[str, dict[str, object]]:
    if thumbnail_manifest is None:
        return {}
    thumbnails = _coerce_frame(thumbnail_manifest)
    _require_columns(thumbnails, THUMBNAIL_COLUMNS, "thumbnail manifest")
    if thumbnails["file_name"].duplicated().any():
        duplicates = sorted(thumbnails.loc[thumbnails["file_name"].duplicated(), "file_name"])
        raise THEOS2ReviewError(
            f"Thumbnail manifest has duplicate file_name rows: {', '.join(duplicates)}"
        )
    return {
        str(row["file_name"]): row
        for row in thumbnails.to_dict(orient="records")
    }


def _validate_selected_row(row: dict[str, object]) -> None:
    if row["processing_scope"] != "theos2_optical_context_preview_only":
        raise THEOS2ReviewError(
            f"THEOS-2 review row is outside preview-only scope: {row['file_name']}"
        )
    if row["reference_mask_status"] != "not_reference_mask":
        raise THEOS2ReviewError(
            f"THEOS-2 review row must not be a reference mask: {row['file_name']}"
        )
    if not _truthy(row["processing_allowed"]):
        raise THEOS2ReviewError(
            f"THEOS-2 review row is not processing allowed: {row['file_name']}"
        )


def _coerce_frame(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    if isinstance(source, pd.DataFrame):
        return source.copy().fillna("")
    return pd.read_csv(source, dtype=str).fillna("")


def _require_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise THEOS2ReviewError(
            f"{label} is missing required columns: {', '.join(missing)}"
        )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}
