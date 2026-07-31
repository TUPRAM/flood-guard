"""Versioned Sentinel-1 feature contracts for label-factory experiments.

The repository has two historical combined-change formulas with reversed VV/VH
weights.  They are preserved as explicitly named legacy schemas so an old
artifact can be reproduced without silently contaminating the canonical v2
feature contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType


class FeatureSchemaError(ValueError):
    """Raised when a feature schema or record violates its versioned contract."""


@dataclass(frozen=True)
class FeatureDefinition:
    """One auditable feature in a versioned schema."""

    name: str
    description: str
    unit: str
    formula: str | None = None
    derived_from: tuple[str, ...] = ()
    required: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise FeatureSchemaError(
                f"Feature name must be lower snake case: {self.name!r}"
            )
        if not self.description.strip():
            raise FeatureSchemaError(f"Feature {self.name!r} needs a description.")
        if not self.unit.strip():
            raise FeatureSchemaError(f"Feature {self.name!r} needs a unit.")


@dataclass(frozen=True)
class FeatureSchema:
    """Immutable ordered feature contract used by a model artifact."""

    version: str
    features: tuple[FeatureDefinition, ...]
    legacy: bool
    intended_use: str
    source_contract: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.version):
            raise FeatureSchemaError(
                f"Schema version must be lower snake case: {self.version!r}"
            )
        if not self.features:
            raise FeatureSchemaError("A feature schema cannot be empty.")
        names = self.feature_names
        if len(names) != len(set(names)):
            raise FeatureSchemaError(
                f"Schema {self.version!r} contains duplicate feature names."
            )
        if not self.intended_use.strip() or not self.source_contract.strip():
            raise FeatureSchemaError(
                "Feature schemas need intended_use and source_contract text."
            )
        if self.version == "sar_change_v2":
            forbidden = {
                "vv_ratio",
                "vh_ratio",
                "combined_drop_db",
                "combined_sar_change_score",
            }
            present = forbidden.intersection(names)
            if present:
                raise FeatureSchemaError(
                    "sar_change_v2 cannot include redundant ratio or legacy "
                    f"combined-formula fields: {sorted(present)}"
                )

    @property
    def feature_names(self) -> tuple[str, ...]:
        """Return feature names in the only valid model-column order."""

        return tuple(feature.name for feature in self.features)

    @property
    def required_feature_names(self) -> tuple[str, ...]:
        """Return required feature names in schema order."""

        return tuple(feature.name for feature in self.features if feature.required)

    def get(self, name: str) -> FeatureDefinition:
        """Return one feature definition or fail with a schema-aware error."""

        for feature in self.features:
            if feature.name == name:
                return feature
        raise FeatureSchemaError(
            f"Feature {name!r} is not part of schema {self.version!r}."
        )

    def validate_columns(
        self,
        columns: Iterable[str],
        *,
        allow_extra: bool = True,
    ) -> tuple[str, ...]:
        """Validate available columns and return them in schema order.

        Optional schema features may be absent.  Required features may not.
        Extra metadata columns are allowed by default because tile identifiers,
        timestamps, and labels are not model inputs.
        """

        available = tuple(columns)
        available_set = set(available)
        missing = [
            name for name in self.required_feature_names if name not in available_set
        ]
        if missing:
            raise FeatureSchemaError(
                f"Schema {self.version!r} is missing required columns: "
                f"{', '.join(missing)}."
            )
        if not allow_extra:
            extra = [name for name in available if name not in self.feature_names]
            if extra:
                raise FeatureSchemaError(
                    f"Schema {self.version!r} received unexpected columns: "
                    f"{', '.join(extra)}."
                )
        return tuple(name for name in self.feature_names if name in available_set)

    def validate_record(
        self,
        record: Mapping[str, object],
        *,
        allow_extra: bool = True,
    ) -> tuple[object, ...]:
        """Validate one mapping and return its ordered model feature values."""

        ordered_names = self.validate_columns(record, allow_extra=allow_extra)
        return tuple(record[name] for name in ordered_names)


LEGACY_SYNTHETIC_BASELINE_V1 = FeatureSchema(
    version="legacy_synthetic_sar_v1",
    legacy=True,
    intended_use=(
        "Reproduce the synthetic threshold baseline only; never combine its "
        "combined_drop_db value with the raster-extractor legacy formula."
    ),
    source_contract="src/floodguard/sar_baseline.py",
    features=(
        FeatureDefinition(
            "pre_vv_db",
            "Pre-event Sentinel-1 VV backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "post_vv_db",
            "Event/post-event Sentinel-1 VV backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "pre_vh_db",
            "Pre-event Sentinel-1 VH backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "post_vh_db",
            "Event/post-event Sentinel-1 VH backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "vv_drop_db",
            "VV backscatter drop from pre-event to post-event.",
            "dB",
            formula="pre_vv_db - post_vv_db",
            derived_from=("pre_vv_db", "post_vv_db"),
        ),
        FeatureDefinition(
            "vh_drop_db",
            "VH backscatter drop from pre-event to post-event.",
            "dB",
            formula="pre_vh_db - post_vh_db",
            derived_from=("pre_vh_db", "post_vh_db"),
        ),
        FeatureDefinition(
            "combined_drop_db",
            "Legacy synthetic combined VV/VH drop.",
            "dB",
            formula="0.6 * vv_drop_db + 0.4 * vh_drop_db",
            derived_from=("vv_drop_db", "vh_drop_db"),
        ),
    ),
)


LEGACY_REAL_RASTER_V1 = FeatureSchema(
    version="legacy_real_weak_sar_v1",
    legacy=True,
    intended_use=(
        "Reproduce existing real-raster weak-label artifacts only; never mix "
        "combined_sar_change_score with the synthetic legacy combined formula."
    ),
    source_contract="src/floodguard/sar_raster_extract.py",
    features=(
        FeatureDefinition(
            "pre_vv_db",
            "Pre-event Sentinel-1 VV backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "post_vv_db",
            "Event/post-event Sentinel-1 VV backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "pre_vh_db",
            "Pre-event Sentinel-1 VH backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "post_vh_db",
            "Event/post-event Sentinel-1 VH backscatter.",
            "dB",
        ),
        FeatureDefinition(
            "vv_drop",
            "VV backscatter drop from pre-event to event-time.",
            "dB",
            formula="pre_vv_db - post_vv_db",
            derived_from=("pre_vv_db", "post_vv_db"),
        ),
        FeatureDefinition(
            "vh_drop",
            "VH backscatter drop from pre-event to event-time.",
            "dB",
            formula="pre_vh_db - post_vh_db",
            derived_from=("pre_vh_db", "post_vh_db"),
        ),
        FeatureDefinition(
            "vv_ratio",
            "Legacy event/pre-event VV ratio on linear backscatter.",
            "ratio",
            formula="event_vv_linear / pre_vv_linear",
            derived_from=("pre_vv_db", "post_vv_db"),
        ),
        FeatureDefinition(
            "vh_ratio",
            "Legacy event/pre-event VH ratio on linear backscatter.",
            "ratio",
            formula="event_vh_linear / pre_vh_linear",
            derived_from=("pre_vh_db", "post_vh_db"),
        ),
        FeatureDefinition(
            "combined_sar_change_score",
            "Legacy real-raster combined VV/VH drop.",
            "dB",
            formula="0.4 * vv_drop + 0.6 * vh_drop",
            derived_from=("vv_drop", "vh_drop"),
        ),
    ),
)


SAR_CHANGE_V2 = FeatureSchema(
    version="sar_change_v2",
    legacy=False,
    intended_use=(
        "Canonical label-factory query-model schema.  It retains raw and direct "
        "change evidence, records context explicitly, and contains no legacy "
        "ratio or combined-change formula."
    ),
    source_contract="FloodGuard label-factory Phase 0 feature contract",
    features=(
        FeatureDefinition(
            "pre_vv_db",
            "Pre-event Sentinel-1 VV backscatter on the canonical grid.",
            "dB",
        ),
        FeatureDefinition(
            "event_vv_db",
            "Event-time Sentinel-1 VV backscatter on the canonical grid.",
            "dB",
        ),
        FeatureDefinition(
            "pre_vh_db",
            "Pre-event Sentinel-1 VH backscatter on the canonical grid.",
            "dB",
        ),
        FeatureDefinition(
            "event_vh_db",
            "Event-time Sentinel-1 VH backscatter on the canonical grid.",
            "dB",
        ),
        FeatureDefinition(
            "vv_change_db",
            "VV backscatter drop from pre-event to event-time.",
            "dB",
            formula="pre_vv_db - event_vv_db",
            derived_from=("pre_vv_db", "event_vv_db"),
        ),
        FeatureDefinition(
            "vh_change_db",
            "VH backscatter drop from pre-event to event-time.",
            "dB",
            formula="pre_vh_db - event_vh_db",
            derived_from=("pre_vh_db", "event_vh_db"),
        ),
        FeatureDefinition(
            "valid_data_fraction",
            "Fraction of supported source observations in the analysis cell or region.",
            "fraction_0_1",
        ),
        FeatureDefinition(
            "vv_change_local_p10_db",
            "Local 10th percentile of VV change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vv_change_local_p50_db",
            "Local median VV change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vv_change_local_p90_db",
            "Local 90th percentile of VV change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vh_change_local_p10_db",
            "Local 10th percentile of VH change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vh_change_local_p50_db",
            "Local median VH change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vh_change_local_p90_db",
            "Local 90th percentile of VH change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vv_change_local_std_db",
            "Local spatial variability of VV change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "vh_change_local_std_db",
            "Local spatial variability of VH change.",
            "dB",
            required=False,
        ),
        FeatureDefinition(
            "elevation_m",
            "Copernicus DEM surface elevation.",
            "m",
            required=False,
        ),
        FeatureDefinition(
            "slope_degrees",
            "Terrain slope derived from the declared DEM.",
            "degrees",
            required=False,
        ),
        FeatureDefinition(
            "permanent_water_fraction",
            "Fraction supported as permanent or pre-existing water.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "urban_fraction",
            "Fraction classified as urban or built-up context.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "forest_fraction",
            "Fraction classified as forest context.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "cropland_fraction",
            "Fraction classified as cropland context.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "other_landcover_fraction",
            "Fraction in remaining declared land-cover classes.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "building_fraction",
            "Fraction intersecting the declared building layer.",
            "fraction_0_1",
            required=False,
        ),
        FeatureDefinition(
            "distance_to_river_m",
            "Planar distance to the declared river or drainage network.",
            "m",
            required=False,
        ),
        FeatureDefinition(
            "incidence_angle_degrees",
            "Sentinel-1 local incidence angle where available.",
            "degrees",
            required=False,
        ),
        FeatureDefinition(
            "pre_post_alignment_error_m",
            "Estimated pre/event co-registration error.",
            "m",
            required=False,
        ),
    ),
)


FEATURE_SCHEMAS: Mapping[str, FeatureSchema] = MappingProxyType(
    {
        schema.version: schema
        for schema in (
            LEGACY_SYNTHETIC_BASELINE_V1,
            LEGACY_REAL_RASTER_V1,
            SAR_CHANGE_V2,
        )
    }
)


def get_feature_schema(version: str) -> FeatureSchema:
    """Return an immutable schema by exact version name."""

    try:
        return FEATURE_SCHEMAS[version]
    except KeyError as exc:
        known = ", ".join(sorted(FEATURE_SCHEMAS))
        raise FeatureSchemaError(
            f"Unknown feature schema {version!r}; known versions: {known}."
        ) from exc
