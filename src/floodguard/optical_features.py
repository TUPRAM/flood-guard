"""Dependency-light tabular optical features for Sentinel-2 Level-2A.

The module accepts already co-registered pre/event pixel rows.  It deliberately
does not open imagery, reproject rasters, infer cloud masks, or create flood
labels.  Callers remain responsible for proving the upstream grid alignment and
source lineage represented by each ``grid_id`` and ``pixel_id`` pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Final

import pandas as pd


OPTICAL_FEATURE_SCHEMA_VERSION: Final = "sentinel2_l2a_optical_features_v1"
OPTICAL_PROCESSING_SCOPE: Final = (
    "sentinel2_l2a_tabular_optical_features_research_context_only"
)
OPTICAL_CONTEXT_WARNING: Final = (
    "Cloud-masked optical research/context features only; not flood truth, not a "
    "flood label, not validation, and not an official warning."
)
THEOS2_PROCESSING_SCOPE: Final = "theos2_pixel_input_eligibility_research_only"
THEOS2_CONTEXT_WARNING: Final = (
    "THEOS-2 eligibility is a fail-closed research-input gate; eligible imagery "
    "is still not flood truth, not a flood label, not validation evidence, and "
    "not an official warning."
)

SENTINEL2_BANDS: Final[tuple[str, ...]] = (
    "B02",
    "B03",
    "B04",
    "B05",
    "B06",
    "B07",
    "B08",
    "B8A",
    "B11",
    "B12",
)

# Sentinel-2 scene-classification values that must not contribute optical
# features.  SCL=1 is included because saturated/defective pixels are not a
# defensible optical input even though it is not itself a cloud class.
MASKED_SCL_CLASSES: Final[frozenset[int]] = frozenset({0, 1, 3, 7, 8, 9, 10, 11})
VALID_CONFIDENCE_CLASSES: Final[frozenset[str]] = frozenset(
    {"high", "medium", "low"}
)

REQUIRED_OPTICAL_COLUMNS: Final[tuple[str, ...]] = (
    "pixel_id",
    "grid_id",
    "source_name",
    "pre_source_timestamp",
    "post_source_timestamp",
    "confidence_class",
    "assumptions",
    *(f"pre_{band}" for band in SENTINEL2_BANDS),
    *(f"post_{band}" for band in SENTINEL2_BANDS),
    "pre_SCL",
    "post_SCL",
    "pre_cloud_distance_m",
    "post_cloud_distance_m",
)

_SCL_MASK_REASONS: Final[dict[int, str]] = {
    0: "scl_nodata",
    1: "scl_saturated_or_defective",
    3: "scl_cloud_shadow",
    7: "scl_unclassified",
    8: "scl_cloud_medium_probability",
    9: "scl_cloud_high_probability",
    10: "scl_thin_cirrus",
    11: "scl_snow_or_ice",
}


class OpticalFeatureError(ValueError):
    """Raised when tabular optical inputs violate the feature contract."""


@dataclass(frozen=True)
class THEOS2PixelEligibility:
    """Fail-closed result for admitting THEOS-2 pixel-level research inputs."""

    eligible: bool
    status: str
    reasons: tuple[str, ...]
    acquisition_timestamp: str
    event_date_overlap: bool
    label_date_overlap: bool
    processing_scope: str = THEOS2_PROCESSING_SCOPE
    warning_text: str = THEOS2_CONTEXT_WARNING


def build_sentinel2_optical_features(
    pixel_rows: pd.DataFrame,
    *,
    minimum_cloud_distance_m: float = 0.0,
    denominator_epsilon: float = 1e-8,
) -> pd.DataFrame:
    """Validate co-registered rows and derive cloud-masked optical features.

    Reflectance inputs must already be scaled to finite values in ``[0, 1]``.
    The normalized indices use these definitions:

    - NDWI: ``(B03 - B08) / (B03 + B08)``
    - MNDWI: ``(B03 - B11) / (B03 + B11)``
    - NDVI: ``(B08 - B04) / (B08 + B04)``
    - AWEI: the shadow-oriented AWEIsh form,
      ``B02 + 2.5*B03 - 1.5*(B08+B11) - 0.25*B12``

    A pre/event phase is valid only when its SCL class is usable, its declared
    cloud distance meets ``minimum_cloud_distance_m``, and every normalized
    index denominator exceeds ``denominator_epsilon``.  Invalid phase features
    and all changes that depend on them are emitted as missing values.
    """

    if not isinstance(pixel_rows, pd.DataFrame):
        raise OpticalFeatureError("pixel_rows must be a pandas DataFrame.")
    if pixel_rows.empty:
        raise OpticalFeatureError("pixel_rows must contain at least one pixel row.")
    cloud_threshold = _finite_number(
        minimum_cloud_distance_m,
        "minimum_cloud_distance_m",
        minimum=0.0,
    )
    epsilon = _finite_number(
        denominator_epsilon,
        "denominator_epsilon",
        minimum=0.0,
        minimum_inclusive=False,
    )
    _require_columns(pixel_rows, REQUIRED_OPTICAL_COLUMNS)

    frame = pixel_rows.copy(deep=True)
    for column in ("pixel_id", "grid_id", "source_name", "assumptions"):
        _require_nonblank_strings(frame, column)
    _validate_confidence(frame)
    duplicate = frame.duplicated(["grid_id", "pixel_id"], keep=False)
    if duplicate.any():
        values = sorted(
            {
                f"{row.grid_id}/{row.pixel_id}"
                for row in frame.loc[duplicate, ["grid_id", "pixel_id"]].itertuples(
                    index=False
                )
            }
        )
        raise OpticalFeatureError(
            "grid_id/pixel_id pairs must be unique; duplicates: "
            + ", ".join(values)
        )

    for phase in ("pre", "post"):
        for band in SENTINEL2_BANDS:
            column = f"{phase}_{band}"
            values = _numeric_series(frame, column)
            outside = (values < 0.0) | (values > 1.0)
            if outside.any():
                raise OpticalFeatureError(
                    f"{column} reflectance must be within 0..1; invalid rows: "
                    f"{_row_labels(frame, outside)}"
                )
            frame[column] = values.astype(float)
        frame[f"{phase}_SCL"] = _validate_scl(frame, f"{phase}_SCL")
        cloud_column = f"{phase}_cloud_distance_m"
        cloud_distance = _numeric_series(frame, cloud_column)
        negative = cloud_distance < 0.0
        if negative.any():
            raise OpticalFeatureError(
                f"{cloud_column} must be non-negative; invalid rows: "
                f"{_row_labels(frame, negative)}"
            )
        frame[cloud_column] = cloud_distance.astype(float)

    pre_times = _normalized_timestamp_series(frame, "pre_source_timestamp")
    post_times = _normalized_timestamp_series(frame, "post_source_timestamp")
    time_order_invalid = pd.Series(
        [pre >= post for pre, post in zip(pre_times["parsed"], post_times["parsed"])],
        index=frame.index,
        dtype=bool,
    )
    if time_order_invalid.any():
        raise OpticalFeatureError(
            "pre_source_timestamp must be earlier than post_source_timestamp; "
            f"invalid rows: {_row_labels(frame, time_order_invalid)}"
        )
    frame["pre_source_timestamp"] = pre_times["normalized"]
    frame["post_source_timestamp"] = post_times["normalized"]

    phase_validity: dict[str, pd.Series] = {}
    phase_reasons: dict[str, list[str]] = {}
    for phase in ("pre", "post"):
        indices = _phase_indices(frame, phase, epsilon)
        scl_valid = ~frame[f"{phase}_SCL"].isin(MASKED_SCL_CLASSES)
        cloud_valid = frame[f"{phase}_cloud_distance_m"] >= cloud_threshold
        denominator_valid = indices.pop("denominator_valid")
        phase_valid = scl_valid & cloud_valid & denominator_valid
        phase_validity[phase] = phase_valid.astype(bool)
        phase_reasons[phase] = [
            _phase_mask_reason(
                scl=int(frame.at[index, f"{phase}_SCL"]),
                cloud_distance_m=float(
                    frame.at[index, f"{phase}_cloud_distance_m"]
                ),
                cloud_threshold_m=cloud_threshold,
                denominator_valid=bool(denominator_valid.at[index]),
            )
            for index in frame.index
        ]
        for name, values in indices.items():
            column = f"{phase}_{name}"
            frame[column] = values.where(phase_valid, float("nan"))
        for band in SENTINEL2_BANDS:
            frame[f"{phase}_{band}_masked"] = frame[f"{phase}_{band}"].where(
                phase_valid,
                float("nan"),
            )
        frame[f"{phase}_optical_valid"] = phase_valid.astype(bool)
        frame[f"{phase}_mask_reason"] = phase_reasons[phase]

    optical_valid = phase_validity["pre"] & phase_validity["post"]
    frame["optical_valid"] = optical_valid.astype(bool)
    frame["optical_invalid_reason"] = [
        _combined_mask_reason(pre_reason, post_reason)
        for pre_reason, post_reason in zip(
            phase_reasons["pre"], phase_reasons["post"]
        )
    ]

    for band in SENTINEL2_BANDS:
        change_column = f"{band}_change"
        frame[change_column] = (
            frame[f"post_{band}_masked"] - frame[f"pre_{band}_masked"]
        ).where(optical_valid, float("nan"))
    for index_name in ("ndwi", "mndwi", "ndvi", "awei"):
        frame[f"{index_name}_change"] = (
            frame[f"post_{index_name}"] - frame[f"pre_{index_name}"]
        ).where(optical_valid, float("nan"))

    frame["minimum_cloud_distance_m"] = frame[
        ["pre_cloud_distance_m", "post_cloud_distance_m"]
    ].min(axis=1)
    frame["cloud_distance_threshold_m"] = cloud_threshold
    frame["awei_variant"] = "AWEIsh"
    frame["feature_schema_version"] = OPTICAL_FEATURE_SCHEMA_VERSION
    frame["processing_scope"] = OPTICAL_PROCESSING_SCOPE
    frame["source_timestamp"] = frame["post_source_timestamp"]
    frame["flood_truth_status"] = "not_flood_truth"
    frame["eligible_for_flood_truth"] = False
    frame["warning_text"] = OPTICAL_CONTEXT_WARNING
    return frame


def build_optical_features(
    pixel_rows: pd.DataFrame,
    *,
    minimum_cloud_distance_m: float = 0.0,
    denominator_epsilon: float = 1e-8,
) -> pd.DataFrame:
    """Alias for :func:`build_sentinel2_optical_features`."""

    return build_sentinel2_optical_features(
        pixel_rows,
        minimum_cloud_distance_m=minimum_cloud_distance_m,
        denominator_epsilon=denominator_epsilon,
    )


def evaluate_theos2_pixel_eligibility(
    *,
    pixel_data_available: bool,
    metadata_only: bool,
    radiometric_calibration_complete: bool,
    georeferencing_complete: bool,
    grid_alignment_complete: bool,
    acquisition_timestamp: str | datetime,
    event_start_timestamp: str | datetime,
    event_end_timestamp: str | datetime,
    label_start_timestamp: str | datetime,
    label_end_timestamp: str | datetime,
    training_permission_granted: bool,
) -> THEOS2PixelEligibility:
    """Return fail-closed THEOS-2 pixel-input eligibility and reason codes.

    A single imagery acquisition must fall inside both the declared flood-event
    window and the label-validity window.  Eligibility also requires actual
    pixels, radiometric calibration, georeferencing, common-grid alignment, and
    explicit training permission.  Metadata-only records are always ineligible.
    """

    flags = {
        "pixel_data_available": pixel_data_available,
        "metadata_only": metadata_only,
        "radiometric_calibration_complete": radiometric_calibration_complete,
        "georeferencing_complete": georeferencing_complete,
        "grid_alignment_complete": grid_alignment_complete,
        "training_permission_granted": training_permission_granted,
    }
    for name, value in flags.items():
        if not isinstance(value, bool):
            raise OpticalFeatureError(f"{name} must be a boolean.")

    acquisition = _parse_aware_timestamp(
        acquisition_timestamp, "acquisition_timestamp"
    )
    event_start = _parse_aware_timestamp(
        event_start_timestamp, "event_start_timestamp"
    )
    event_end = _parse_aware_timestamp(event_end_timestamp, "event_end_timestamp")
    label_start = _parse_aware_timestamp(
        label_start_timestamp, "label_start_timestamp"
    )
    label_end = _parse_aware_timestamp(label_end_timestamp, "label_end_timestamp")
    if event_start > event_end:
        raise OpticalFeatureError(
            "event_start_timestamp must not be later than event_end_timestamp."
        )
    if label_start > label_end:
        raise OpticalFeatureError(
            "label_start_timestamp must not be later than label_end_timestamp."
        )

    event_overlap = event_start <= acquisition <= event_end
    label_overlap = label_start <= acquisition <= label_end
    reasons: list[str] = []
    if metadata_only:
        reasons.append("metadata_only_input")
    if not pixel_data_available:
        reasons.append("pixel_data_unavailable")
    if not radiometric_calibration_complete:
        reasons.append("radiometric_calibration_incomplete")
    if not georeferencing_complete:
        reasons.append("georeferencing_incomplete")
    if not grid_alignment_complete:
        reasons.append("grid_alignment_incomplete")
    if not event_overlap:
        reasons.append("outside_event_window")
    if not label_overlap:
        reasons.append("outside_label_window")
    if not training_permission_granted:
        reasons.append("training_permission_not_granted")

    eligible = not reasons
    return THEOS2PixelEligibility(
        eligible=eligible,
        status=(
            "eligible_for_pixel_level_research_input"
            if eligible
            else "ineligible_for_pixel_level_research_input"
        ),
        reasons=tuple(reasons),
        acquisition_timestamp=_format_timestamp(acquisition),
        event_date_overlap=event_overlap,
        label_date_overlap=label_overlap,
    )


def _phase_indices(
    frame: pd.DataFrame,
    phase: str,
    epsilon: float,
) -> dict[str, pd.Series]:
    green = frame[f"{phase}_B03"]
    red = frame[f"{phase}_B04"]
    nir = frame[f"{phase}_B08"]
    swir1 = frame[f"{phase}_B11"]
    swir2 = frame[f"{phase}_B12"]
    blue = frame[f"{phase}_B02"]

    ndwi, ndwi_valid = _safe_normalized_difference(green, nir, epsilon)
    mndwi, mndwi_valid = _safe_normalized_difference(green, swir1, epsilon)
    ndvi, ndvi_valid = _safe_normalized_difference(nir, red, epsilon)
    awei = blue + 2.5 * green - 1.5 * (nir + swir1) - 0.25 * swir2
    return {
        "ndwi": ndwi,
        "mndwi": mndwi,
        "ndvi": ndvi,
        "awei": awei.astype(float),
        "denominator_valid": ndwi_valid & mndwi_valid & ndvi_valid,
    }


def _safe_normalized_difference(
    first: pd.Series,
    second: pd.Series,
    epsilon: float,
) -> tuple[pd.Series, pd.Series]:
    denominator = first + second
    valid = denominator.abs() > epsilon
    result = ((first - second) / denominator).where(valid, float("nan"))
    return result.astype(float), valid.astype(bool)


def _phase_mask_reason(
    *,
    scl: int,
    cloud_distance_m: float,
    cloud_threshold_m: float,
    denominator_valid: bool,
) -> str:
    reasons: list[str] = []
    if scl in MASKED_SCL_CLASSES:
        reasons.append(_SCL_MASK_REASONS[scl])
    if cloud_distance_m < cloud_threshold_m:
        reasons.append("cloud_distance_below_threshold")
    if not denominator_valid:
        reasons.append("zero_or_near_zero_index_denominator")
    return "|".join(reasons)


def _combined_mask_reason(pre_reason: str, post_reason: str) -> str:
    reasons: list[str] = []
    if pre_reason:
        reasons.append(f"pre:{pre_reason}")
    if post_reason:
        reasons.append(f"post:{post_reason}")
    return ";".join(reasons)


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise OpticalFeatureError(
            "Optical input is missing required columns: " + ", ".join(missing)
        )


def _require_nonblank_strings(frame: pd.DataFrame, column: str) -> None:
    invalid = frame[column].map(
        lambda value: not isinstance(value, str) or not value.strip()
    )
    if invalid.any():
        raise OpticalFeatureError(
            f"{column} must contain non-blank strings; invalid rows: "
            f"{_row_labels(frame, invalid)}"
        )
    frame[column] = frame[column].str.strip()


def _validate_confidence(frame: pd.DataFrame) -> None:
    _require_nonblank_strings(frame, "confidence_class")
    invalid = ~frame["confidence_class"].isin(VALID_CONFIDENCE_CLASSES)
    if invalid.any():
        raise OpticalFeatureError(
            "confidence_class must be one of high, medium, or low; invalid rows: "
            f"{_row_labels(frame, invalid)}"
        )


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    bool_values = frame[column].map(_is_boolean)
    numeric = pd.to_numeric(frame[column], errors="coerce")
    invalid = bool_values | numeric.isna() | ~numeric.map(math.isfinite)
    if invalid.any():
        raise OpticalFeatureError(
            f"{column} must contain finite numeric values; invalid rows: "
            f"{_row_labels(frame, invalid)}"
        )
    return numeric.astype(float)


def _validate_scl(frame: pd.DataFrame, column: str) -> pd.Series:
    values = _numeric_series(frame, column)
    invalid = (values % 1 != 0) | (values < 0) | (values > 11)
    if invalid.any():
        raise OpticalFeatureError(
            f"{column} must contain integer Sentinel-2 SCL values from 0 to 11; "
            f"invalid rows: {_row_labels(frame, invalid)}"
        )
    return values.astype(int)


def _normalized_timestamp_series(
    frame: pd.DataFrame,
    column: str,
) -> dict[str, list[datetime] | list[str]]:
    parsed = [
        _parse_aware_timestamp(value, f"{column} row {index}")
        for index, value in frame[column].items()
    ]
    return {
        "parsed": parsed,
        "normalized": [_format_timestamp(value) for value in parsed],
    }


def _parse_aware_timestamp(value: object, label: str) -> datetime:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise OpticalFeatureError(
                f"{label} must be a valid timezone-aware ISO-8601 timestamp."
            ) from exc
    else:
        raise OpticalFeatureError(
            f"{label} must be a valid timezone-aware ISO-8601 timestamp."
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OpticalFeatureError(
            f"{label} must include an explicit UTC offset or Z suffix."
        )
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _finite_number(
    value: object,
    label: str,
    *,
    minimum: float,
    minimum_inclusive: bool = True,
) -> float:
    if _is_boolean(value):
        raise OpticalFeatureError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OpticalFeatureError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise OpticalFeatureError(f"{label} must be a finite number.")
    below = number < minimum if minimum_inclusive else number <= minimum
    if below:
        operator = "at least" if minimum_inclusive else "greater than"
        raise OpticalFeatureError(f"{label} must be {operator} {minimum}.")
    return number


def _is_boolean(value: object) -> bool:
    value_type = type(value)
    return isinstance(value, bool) or (
        value_type.__module__ == "numpy" and value_type.__name__ in {"bool", "bool_"}
    )


def _row_labels(frame: pd.DataFrame, mask: pd.Series) -> str:
    labels = [str(index) for index in frame.index[mask]]
    return ", ".join(labels)


__all__ = [
    "MASKED_SCL_CLASSES",
    "OPTICAL_CONTEXT_WARNING",
    "OPTICAL_FEATURE_SCHEMA_VERSION",
    "OPTICAL_PROCESSING_SCOPE",
    "OpticalFeatureError",
    "REQUIRED_OPTICAL_COLUMNS",
    "SENTINEL2_BANDS",
    "THEOS2PixelEligibility",
    "build_optical_features",
    "build_sentinel2_optical_features",
    "evaluate_theos2_pixel_eligibility",
]
