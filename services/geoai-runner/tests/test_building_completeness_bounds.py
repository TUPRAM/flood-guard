"""Building coverage must be rated in both directions.

The check was written when OSM was the only source, and OSM only ever
undercounted Mae Sai (ratio 0.009-0.051), so a low-side threshold was
sufficient. Component D's move to Overture takes the district ratio to ~2.69.
With no upper bound that would have been reported as "usable" -- a stronger
claim than the previous "severely_incomplete", produced by swapping a data
source with nothing validated.

Overture mixes OSM with ML-derived footprints and counts sheds and
outbuildings, so far-above-expectation is a reason to look rather than a clean
bill of health.
"""

from __future__ import annotations

import pytest

from geoai_runner.realpipeline.aggregate import (
    OSM_COMPLETENESS_OVER_RATIO,
    OSM_COMPLETENESS_SEVERE_RATIO,
    osm_completeness,
)

#: WorldPop total across the 8 Mae Sai tambons, from the committed priority CSV.
DISTRICT_POPULATION = 81_798.0
#: One building per four residents.
IMPLIED_BUILDINGS = DISTRICT_POPULATION / 4.0


def test_thresholds_are_ordered() -> None:
    assert 0 < OSM_COMPLETENESS_SEVERE_RATIO < 1 < OSM_COMPLETENESS_OVER_RATIO


def test_osm_measured_counts_remain_severely_incomplete() -> None:
    """The historical finding must not be rewritten by the new bound."""

    result = osm_completeness(397, DISTRICT_POPULATION)
    assert result["osm_completeness_flag"] == "severely_incomplete"
    assert result["osm_completeness_ratio"] == pytest.approx(0.0194, abs=5e-4)


def test_overture_measured_count_is_flagged_for_review_not_usable() -> None:
    """The trap this test exists for.

    54,978 footprints across the 8 tambons, measured 2026-07-29. Before the
    upper bound this returned "usable".
    """

    result = osm_completeness(54_978, DISTRICT_POPULATION)
    assert result["osm_completeness_ratio"] == pytest.approx(2.69, abs=0.01)
    assert result["osm_completeness_flag"] == "over_expectation_review_needed", (
        "An unvalidated 2.7x-expectation building count must not be reported as "
        "usable; swapping a data source cannot upgrade a claim on its own."
    )


@pytest.mark.parametrize(
    ("count", "expected_flag"),
    [
        (0, "severely_incomplete"),
        (int(IMPLIED_BUILDINGS * 0.10), "severely_incomplete"),
        (int(IMPLIED_BUILDINGS * 0.24), "severely_incomplete"),
        (int(IMPLIED_BUILDINGS * 0.30), "usable"),
        (int(IMPLIED_BUILDINGS * 1.00), "usable"),
        (int(IMPLIED_BUILDINGS * 1.90), "usable"),
        (int(IMPLIED_BUILDINGS * 2.10), "over_expectation_review_needed"),
        (int(IMPLIED_BUILDINGS * 10.0), "over_expectation_review_needed"),
    ],
)
def test_flag_across_the_range(count: int, expected_flag: str) -> None:
    assert osm_completeness(count, DISTRICT_POPULATION)["osm_completeness_flag"] == expected_flag


def test_missing_population_is_still_reported_as_unknown() -> None:
    for population in (None, 0.0, -1.0, float("nan")):
        result = osm_completeness(1_000, population)
        assert result["osm_completeness_flag"] == "unknown_no_population"
        assert result["osm_completeness_ratio"] is None
