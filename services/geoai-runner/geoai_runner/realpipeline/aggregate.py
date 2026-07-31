"""Bridge AI raster outputs into the FloodGuard decision layer.

This is where GeoAI meets policy. The model tier produces georeferenced rasters
(SAR flood probability, susceptibility surface, building footprints); this module
runs zonal statistics over reporting polygons and emits the per-subdistrict
inputs ``floodguard.scoring`` consumes.

Three corrections landed here in T0.3
-------------------------------------
**1. Absolute scales, not max-normalisation.** The previous real run scaled
``flood_likelihood`` by the *maximum* flooded share among the eight tambons, so
whichever unit happened to be wettest always scored ~96 regardless of absolute
severity -- it would have scored 96 in a dry year too. The value was therefore a
within-district rank, not a likelihood, and could not be compared across events,
districts or time. :class:`FloodLikelihoodAnchor` replaces it with fixed,
versioned anchors. Every published number cites ``anchor_version`` so the scale
can be changed later without silently invalidating earlier outputs.

**2. Population instead of OpenStreetMap building counts.** Exposure used OSM
building density. Measured against WorldPop, OSM captures between 0.9% and 5.1%
of expected structures across Mae Sai's tambons and exactly zero in two of them,
so the old ``exposure_0_100`` was substantially a map of OSM contributor
activity. A signal that captures ~2% of reality with a 25x spread between units
is noise, and it was carrying 25% of the FPPS weight. OSM counts are retained as
a *diagnostic* with an explicit completeness flag; they no longer enter the
score.

**3. Real decision-layer context instead of invented proxies.** The three
non-AI FPPS components (access gap, road criticality, vulnerability) were being
synthesised from the AI signals as "transparent proxies", which both
double-counted the flood term and contradicted the real values the decision
layer already computes in ``outputs/mae_sai_subdistrict_flood_inputs.csv``.
They are now joined from that table. Where it is unavailable the row is marked
``context_source="placeholder"`` and its confidence is forced down, rather than
silently substituting a fabricated number.

The fused flood likelihood still combines two independent AI signals -- SAR
change probability (Component A) and the terrain susceptibility surface
(Component C) -- and sets a confidence class from their agreement.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from geoai_runner.realpipeline.raster_io import read_geotiff


class AggregationError(ValueError):
    """Raised when a decision-bridge input is missing or inconsistent."""


# --------------------------------------------------------------------------- #
# Versioned scale anchors
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FloodLikelihoodAnchor:
    """Fixed, event-independent scale anchors for ``flood_likelihood_0_100``.

    ``observed_saturation_share``: the inundated fraction of a reporting unit that
    maps to a full observed score. 5% of a tambon under water is already a major
    event; the previous implicit anchor of 25% put every realistic value in the
    bottom fifth of the range.

    ``prior_reference_mean``: the susceptibility value that maps to a neutral 0.5.
    Mae Sai's district-wide susceptibility mean is ~0.65 and four tambons sit at
    ~0.90, so an uncentred prior contributed a near-constant offset and destroyed
    discrimination between them. Centring restores it.

    ``prior_gain``: chosen so the prior does **not** clip over the observed
    susceptibility range (0.549-0.917 across Mae Sai's tambons). A larger gain
    saturates the four riverside tambons at exactly 1.0, which re-destroys the
    discrimination centring was introduced to fix and simultaneously maximises
    the apparent signal disagreement. 1.85 maps the highest observed
    susceptibility to ~0.99 without clipping.

    These are provisional planning constants, not calibrated hydrology. They are
    versioned so that a later revision -- ideally from multi-year inundation
    frequency rather than judgement -- is an explicit, auditable change.
    """

    version: str = "fpps_flood_anchor_v1"
    observed_saturation_share: float = 0.05
    observed_weight: float = 0.70
    prior_weight: float = 0.30
    prior_reference_mean: float = 0.65
    prior_gain: float = 1.85


@dataclass(frozen=True)
class ExposureAnchor:
    """Fixed scale anchor for ``exposure_0_100`` from population density.

    ``saturation_density_per_km2``: 1,000 people/km2 maps to a full exposure
    score. Mae Sai's tambons span ~141 to ~829 people/km2, so this anchor keeps
    the whole district on-scale while leaving headroom for genuinely urban units
    elsewhere in Thailand -- which matters because an anchor that saturates
    inside the study area would silently become a max-normalisation again.
    """

    version: str = "fpps_exposure_anchor_v1"
    saturation_density_per_km2: float = 1000.0


DEFAULT_FLOOD_ANCHOR = FloodLikelihoodAnchor()
DEFAULT_EXPOSURE_ANCHOR = ExposureAnchor()

# Below this ratio of mapped buildings to a population-implied expectation, the
# building layer is treated as unusable for any quantitative claim.
OSM_COMPLETENESS_SEVERE_RATIO = 0.25

# Above this ratio the layer is *over* the population-implied expectation, which
# is equally disqualifying and used to be invisible.
#
# The check was one-sided because it was written against OSM, which only ever
# undercounted Mae Sai (ratio 0.009-0.051). Switching Component D to Overture
# takes the district ratio to ~2.69, and with no upper bound that would have
# been stamped "usable" -- a STRONGER claim than before, produced by swapping a
# data source with nothing validated. Overture mixes OSM with ML-derived
# footprints and counts sheds and outbuildings, so a ratio far above expectation
# is a reason to look, not a clean bill of health.
#
# 2.0 is deliberately loose: one building per two residents is already
# implausible for a district of 82k people, so anything past it needs a human.
OSM_COMPLETENESS_OVER_RATIO = 2.0

_PEOPLE_PER_BUILDING = 4.0


def fuse_flood_likelihood(
    flooded_share: float,
    susceptibility_mean: float,
    *,
    anchor: FloodLikelihoodAnchor = DEFAULT_FLOOD_ANCHOR,
) -> tuple[float, dict[str, float]]:
    """Return a 0-100 likelihood plus its decomposed, inspectable terms.

    Args:
        flooded_share: Observed inundated fraction of the unit, in ``[0, 1]``.
        susceptibility_mean: Mean terrain susceptibility of the unit, in ``[0, 1]``.

    Returns:
        ``(likelihood_0_100, terms)`` where ``terms`` exposes the observed and
        prior contributions separately so a reader can see which signal drove the
        score rather than inferring it from a single fused number.
    """

    flooded_share = _unit_interval(flooded_share, "flooded_share")
    susceptibility_mean = _unit_interval(susceptibility_mean, "susceptibility_mean")

    observed = min(1.0, flooded_share / anchor.observed_saturation_share)
    prior = float(
        np.clip(
            0.5 + anchor.prior_gain * (susceptibility_mean - anchor.prior_reference_mean),
            0.0,
            1.0,
        )
    )
    fused = anchor.observed_weight * observed + anchor.prior_weight * prior
    return round(float(np.clip(fused, 0.0, 1.0) * 100.0), 1), {
        "observed_term": round(observed, 4),
        "prior_term": round(prior, 4),
        "observed_weight": anchor.observed_weight,
        "prior_weight": anchor.prior_weight,
    }


def compute_exposure(
    population: float | None,
    area_sq_km: float | None,
    *,
    anchor: ExposureAnchor = DEFAULT_EXPOSURE_ANCHOR,
) -> tuple[float | None, dict[str, float | None]]:
    """Return a 0-100 exposure score from population density.

    Returns ``(None, terms)`` when population or area is unavailable. Returning
    ``None`` rather than 0 matters: absent data is not an absence of people, and
    a silent zero would read as "nobody lives here" in a preparedness ranking.
    """

    if population is None or area_sq_km is None:
        return None, {"population": None, "area_sq_km": None, "density_per_km2": None}
    if not math.isfinite(population) or not math.isfinite(area_sq_km) or area_sq_km <= 0.0:
        return None, {
            "population": population,
            "area_sq_km": area_sq_km,
            "density_per_km2": None,
        }

    density = float(population) / float(area_sq_km)
    score = round(float(np.clip(density / anchor.saturation_density_per_km2, 0.0, 1.0) * 100.0), 1)
    return score, {
        "population": round(float(population), 1),
        "area_sq_km": round(float(area_sq_km), 4),
        "density_per_km2": round(density, 2),
    }


def osm_completeness(building_count: int, population: float | None) -> dict[str, object]:
    """Rate building coverage against a population-implied expectation.

    A crude expectation of one building per four residents is enough to separate
    "sparsely mapped" from "essentially unmapped". OSM's Mae Sai tambons land
    between 0.9% and 5.1% of expectation, which is why building counts inform
    confidence but no longer inform the score.

    The rating is two-sided (see :data:`OSM_COMPLETENESS_OVER_RATIO`): a count
    far *above* expectation is as unusable as one far below, and only the low
    side was checked while OSM was the only source.

    The ``osm_`` field prefix is historical. Component D's source moved to
    Overture on 2026-07-29; the actual source for a run is recorded in
    ``metrics.infrastructure.building_source``. The names are kept because they
    are published in the priority CSV and the web payload.
    """

    if population is None or not math.isfinite(population) or population <= 0:
        return {
            "osm_building_count": int(building_count),
            "osm_expected_buildings": None,
            "osm_completeness_ratio": None,
            "osm_completeness_flag": "unknown_no_population",
        }
    expected = float(population) / _PEOPLE_PER_BUILDING
    ratio = float(building_count) / expected if expected > 0 else 0.0
    if ratio < OSM_COMPLETENESS_SEVERE_RATIO:
        flag = "severely_incomplete"
    elif ratio > OSM_COMPLETENESS_OVER_RATIO:
        flag = "over_expectation_review_needed"
    else:
        flag = "usable"
    return {
        "osm_building_count": int(building_count),
        "osm_expected_buildings": round(expected, 1),
        "osm_completeness_ratio": round(ratio, 4),
        "osm_completeness_flag": flag,
    }


# --------------------------------------------------------------------------- #
# Real decision-layer context
# --------------------------------------------------------------------------- #
CONTEXT_COLUMNS = (
    "access_gap_0_100",
    "road_criticality_0_100",
    "vulnerability_context_0_100",
)


@dataclass(frozen=True)
class SubdistrictContext:
    """Per-subdistrict population, area and non-AI FPPS components.

    Sourced from artifacts the decision layer already produces, so the runner
    consumes real context instead of synthesising proxies from its own AI
    signals -- which would double-count the flood term.
    """

    population: dict[str, float]
    area_sq_km: dict[str, float]
    components: dict[str, dict[str, float]]
    source_name: str
    source_timestamp: str

    def has(self, subdistrict_id: str) -> bool:
        """Return whether full context exists for this subdistrict."""

        key = normalise_subdistrict_id(subdistrict_id)
        return key in self.components and key in self.population


def normalise_subdistrict_id(value: object) -> str:
    """Normalise DOPA (``570901``) and COD-AB (``TH570901``) identifiers."""

    text = str(value or "").strip().upper()
    return text[2:] if text.startswith("TH") else text


def load_subdistrict_context(
    flood_inputs_csv: str | Path,
    admin_geojson: str | Path,
) -> SubdistrictContext:
    """Load real population, area and non-AI FPPS components.

    Args:
        flood_inputs_csv: ``outputs/mae_sai_subdistrict_flood_inputs.csv``.
        admin_geojson: ``outputs/mae_sai_admin_context.geojson`` (for area).
    """

    flood_inputs_csv = Path(flood_inputs_csv)
    admin_geojson = Path(admin_geojson)
    if not flood_inputs_csv.exists():
        raise AggregationError(f"decision-layer context not found: {flood_inputs_csv}")
    if not admin_geojson.exists():
        raise AggregationError(f"admin context not found: {admin_geojson}")

    frame = pd.read_csv(flood_inputs_csv)
    required = (*CONTEXT_COLUMNS, "subdistrict_id", "total_population")
    missing = [column for column in required if column not in frame]
    if missing:
        raise AggregationError(f"{flood_inputs_csv} is missing columns: {missing}")

    population: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    for record in frame.to_dict("records"):
        key = normalise_subdistrict_id(record["subdistrict_id"])
        population[key] = float(record["total_population"])
        components[key] = {column: float(record[column]) for column in CONTEXT_COLUMNS}

    areas: dict[str, float] = {}
    payload = json.loads(admin_geojson.read_text(encoding="utf-8"))
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        key = normalise_subdistrict_id(properties.get("subdistrict_id"))
        if "area_sq_km" in properties:
            areas[key] = float(properties["area_sq_km"])

    source = str(frame.get("source_name", pd.Series(["decision-layer context"])).iloc[0])
    stamp_series = frame.get("source_timestamp")
    stamp = str(stamp_series.iloc[0]) if stamp_series is not None else ""
    return SubdistrictContext(
        population=population,
        area_sq_km=areas,
        components=components,
        source_name=source,
        source_timestamp=stamp,
    )


# --------------------------------------------------------------------------- #
# Zonal aggregation
# --------------------------------------------------------------------------- #
def _rasterize_units(
    features: list[dict], transform, shape: tuple[int, int]
) -> dict[str, np.ndarray]:
    from rasterio.features import rasterize

    masks: dict[str, np.ndarray] = {}
    for feat in features:
        sid = normalise_subdistrict_id(feat["properties"]["subdistrict_id"])
        masks[sid] = rasterize(
            [(feat["geometry"], 1)],
            out_shape=shape,
            transform=transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        ).astype(bool)
    return masks


def aggregate_subdistrict_ai_inputs(
    subdistrict_features: list[dict],
    sar_probability_path: str | Path,
    susceptibility_path: str | Path,
    building_footprints_path: str | Path,
    *,
    context: SubdistrictContext | None = None,
    flood_anchor: FloodLikelihoodAnchor = DEFAULT_FLOOD_ANCHOR,
    exposure_anchor: ExposureAnchor = DEFAULT_EXPOSURE_ANCHOR,
    source_timestamp: str = "2024-09-16T06:00:00Z",
    source_name: str = "FloodGuard GeoAI pipeline",
) -> pd.DataFrame:
    """Zonal-aggregate AI rasters into per-subdistrict FPPS inputs.

    Returns one row per subdistrict with ``flood_likelihood_0_100`` (AI-derived),
    ``exposure_0_100`` (WorldPop density), ``confidence_class`` and full
    provenance, including the anchor versions the scales came from.
    """

    sar_prob, transform, _ = read_geotiff(sar_probability_path)
    sar_prob = sar_prob[0].astype("float64")
    susc, _, _ = read_geotiff(susceptibility_path)
    susc = susc[0].astype("float64") / 100.0  # back to 0..1
    shape = sar_prob.shape

    footprints = json.loads(Path(building_footprints_path).read_text(encoding="utf-8"))
    building_pts = [
        (_centroid(f["geometry"]), bool(f["properties"].get("exposed_to_flood", False)))
        for f in footprints.get("features", [])
    ]

    unit_masks = _rasterize_units(subdistrict_features, transform, shape)
    inv = ~transform

    building_counts: dict[str, int] = {}
    exposed_counts: dict[str, int] = {}
    for sid, mask in unit_masks.items():
        bc = ec = 0
        for (lon, lat), exposed in building_pts:
            col, row = inv * (lon, lat)
            rr, cc = int(row), int(col)
            if 0 <= rr < shape[0] and 0 <= cc < shape[1] and mask[rr, cc]:
                bc += 1
                ec += int(exposed)
        building_counts[sid] = bc
        exposed_counts[sid] = ec

    rows: list[dict] = []
    for feat in subdistrict_features:
        sid = normalise_subdistrict_id(feat["properties"]["subdistrict_id"])
        name = feat["properties"]["subdistrict_name"]
        mask = unit_masks[sid]
        if mask.sum() == 0:
            continue

        sar_mean = float(sar_prob[mask].mean())
        sar_p90 = float(np.percentile(sar_prob[mask], 90))
        susc_mean = float(susc[mask].mean())
        flooded_share = float((sar_prob[mask] >= 0.5).mean())

        likelihood, likelihood_terms = fuse_flood_likelihood(
            flooded_share, susc_mean, anchor=flood_anchor
        )
        population = context.population.get(sid) if context else None
        area = context.area_sq_km.get(sid) if context else None
        exposure, exposure_terms = compute_exposure(population, area, anchor=exposure_anchor)
        completeness = osm_completeness(building_counts[sid], population)

        confidence, agreement_gap = signal_agreement(
            likelihood_terms["observed_term"], likelihood_terms["prior_term"]
        )
        # Missing population context is a separate, harder failure than signal
        # disagreement: exposure cannot be computed at all.
        if exposure is None:
            confidence = "low"

        rows.append(
            {
                "subdistrict_id": sid,
                "subdistrict_name": name,
                "flood_likelihood_0_100": likelihood,
                "exposure_0_100": exposure,
                "confidence_class": confidence,
                "signal_agreement_gap": agreement_gap,
                "ai_sar_probability_mean": round(sar_mean, 4),
                "ai_sar_probability_p90": round(sar_p90, 4),
                "ai_flood_share": round(flooded_share, 5),
                "ai_susceptibility_mean": round(susc_mean, 4),
                "ai_exposed_building_count": exposed_counts[sid],
                "flood_anchor_version": flood_anchor.version,
                "exposure_anchor_version": exposure_anchor.version,
                **{f"flood_{k}": v for k, v in likelihood_terms.items()},
                **exposure_terms,
                **completeness,
                "source_name": source_name,
                "source_timestamp": source_timestamp,
                "assumptions": (
                    "flood_likelihood is AI-derived (Sentinel-1 change detection fused "
                    "with a terrain susceptibility prior) on absolute anchors, not "
                    "normalised to the district maximum. exposure is WorldPop 2020 "
                    "population density; OpenStreetMap building counts are reported as "
                    "a diagnostic only because OSM coverage here is 0.9-5.1% of the "
                    "population-implied expectation. Non-operational; not an official "
                    "warning."
                ),
            }
        )
    return pd.DataFrame(rows)


# Agreement gap thresholds between the two normalised signals that form the score.
AGREEMENT_HIGH_MAX = 0.35
AGREEMENT_MEDIUM_MAX = 0.65


def signal_agreement(
    observed_term: float,
    prior_term: float,
) -> tuple[str, float]:
    """Return ``(confidence_class, gap)`` from the two normalised score terms.

    Confidence here is *epistemic agreement*, not risk level. It compares the
    exact quantities that form ``flood_likelihood`` -- the normalised observed
    term and the centred terrain prior, both in ``[0, 1]`` -- so the confidence
    and the score are always talking about the same thing.

    A large gap means the observation and the terrain tell different stories. At
    Mae Sai that happens systematically because the only same-orbit acquisition
    is four days past the flood peak: terrain says the valley floods, the image
    shows mostly drained ground. That is a genuine epistemic limit of this
    snapshot and it should propagate into the action class, which is why the
    gap itself is published alongside the class rather than being hidden behind
    a threshold.
    """

    gap = abs(float(observed_term) - float(prior_term))
    if gap < AGREEMENT_HIGH_MAX:
        return "high", round(gap, 4)
    if gap < AGREEMENT_MEDIUM_MAX:
        return "medium", round(gap, 4)
    return "low", round(gap, 4)


def build_fpps_input_table(
    ai_inputs: pd.DataFrame,
    *,
    context: SubdistrictContext | None = None,
    placeholder_defaults: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Complete the FPPS input table from AI inputs plus real decision context.

    ``flood_likelihood_0_100`` (weight 0.30) and ``exposure_0_100`` (0.25) are
    produced above. The remaining three components come from the decision layer's
    own real outputs when ``context`` is supplied. When it is not, they fall back
    to declared placeholders and every affected row is marked
    ``context_source="placeholder"`` with its confidence forced to ``low`` -- the
    previous behaviour synthesised them from the AI signals and presented the
    result as if it were context, which both double-counted flooding and inflated
    the apparent realism of the score.
    """

    frame = ai_inputs.copy()
    defaults = {
        "access_gap_0_100": 50.0,
        "road_criticality_0_100": 50.0,
        "vulnerability_context_0_100": 50.0,
    }
    if placeholder_defaults:
        defaults.update(placeholder_defaults)

    sources: list[str] = []
    values: dict[str, list[float]] = {column: [] for column in CONTEXT_COLUMNS}
    for sid in frame["subdistrict_id"]:
        key = normalise_subdistrict_id(sid)
        if context is not None and key in context.components:
            sources.append("decision_layer_real_context")
            for column in CONTEXT_COLUMNS:
                values[column].append(context.components[key][column])
        else:
            sources.append("placeholder")
            for column in CONTEXT_COLUMNS:
                values[column].append(defaults[column])

    for column in CONTEXT_COLUMNS:
        frame[column] = values[column]
    frame["context_source"] = sources
    if "confidence_class" in frame:
        frame.loc[frame["context_source"] == "placeholder", "confidence_class"] = "low"

    # exposure_0_100 is nullable by design; scoring requires a number, so an
    # absent value becomes 0 *and* is marked low confidence rather than silently
    # scoring as if nobody lived there.
    if "exposure_0_100" in frame:
        absent = frame["exposure_0_100"].isna()
        if absent.any():
            frame.loc[absent, "confidence_class"] = "low"
            frame["exposure_0_100"] = frame["exposure_0_100"].fillna(0.0)
    return frame


def _centroid(geometry: dict) -> tuple[float, float]:
    if geometry.get("type") == "Point":
        lon, lat = geometry["coordinates"]
        return float(lon), float(lat)
    ring = geometry["coordinates"][0]
    if isinstance(ring[0][0], list | tuple):  # MultiPolygon
        ring = ring[0]
    xs = [p[0] for p in ring[:-1]] or [p[0] for p in ring]
    ys = [p[1] for p in ring[:-1]] or [p[1] for p in ring]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _unit_interval(value: object, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise AggregationError(f"{label} must be finite; got {value!r}.")
    if number < 0.0 or number > 1.0:
        raise AggregationError(f"{label} must lie in [0, 1]; got {number!r}.")
    return number
