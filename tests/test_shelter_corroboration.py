"""Shelter corroboration against OSM buildings and amenities, on invented inputs.

The shelters and the OSM objects below are made up. The tests check the match
rule of protocol v1b (a located DDPM row is corroborated when an OSM building
or amenity lies within the match distance) and that only counts come out.
"""

from __future__ import annotations

import json

import pytest
from shapely.geometry import Point, box

from floodguard.ddpm_shelters import LOCATED, LOCATION_UNVERIFIED
from floodguard.shelter_corroboration import (
    AMENITY,
    BUILDING,
    ShelterCorroborationError,
    corroborate_shelters,
    osm_match_kinds,
)

# About 0.001 degree of longitude is 105 m and 0.001 degree of latitude is 111 m at 20 degrees north.
ORIGIN_LON, ORIGIN_LAT = 99.90, 20.40


def _shelter(lon: float, lat: float, places: float, status: str = LOCATED) -> dict:
    return {"longitude": lon, "latitude": lat, "listed_places": places, "location_status": status,
            "place_name_th": "test place"}


def test_match_kinds_read_building_and_amenity_and_ignore_no() -> None:
    assert osm_match_kinds({"building": "yes"}) == frozenset({BUILDING})
    assert osm_match_kinds({"amenity": "school", "building": "school"}) == frozenset({BUILDING, AMENITY})
    assert osm_match_kinds({"amenity": "parking"}) == frozenset({AMENITY})
    assert osm_match_kinds({"building": "no", "amenity": "No"}) == frozenset()
    assert osm_match_kinds({"highway": "primary"}) == frozenset()


def test_a_located_shelter_is_corroborated_within_the_distance_only() -> None:
    footprint = box(ORIGIN_LON, ORIGIN_LAT, ORIGIN_LON + 0.0002, ORIGIN_LAT + 0.0002)
    objects = [(frozenset({BUILDING}), footprint), (frozenset({AMENITY}), Point(ORIGIN_LON + 0.02, ORIGIN_LAT))]
    shelters = [
        _shelter(ORIGIN_LON + 0.0001, ORIGIN_LAT + 0.0001, 100.0),  # inside the building
        _shelter(ORIGIN_LON + 0.0012, ORIGIN_LAT, 50.0),  # about 105 m east of the building
        _shelter(ORIGIN_LON + 0.0040, ORIGIN_LAT, 20.0),  # about 400 m away: no match
        _shelter(ORIGIN_LON + 0.0201, ORIGIN_LAT, 10.0),  # about 10 m from the amenity point
        _shelter(ORIGIN_LON + 0.0001, ORIGIN_LAT + 0.0001, 999.0, LOCATION_UNVERIFIED),  # never tested
    ]
    counts = corroborate_shelters(shelters, objects, distance_m=150.0)
    assert counts["located_rows"] == 4 and counts["located_places"] == 180.0
    assert counts["corroborated_rows"] == 3 and counts["corroborated_places"] == 160.0
    assert counts["matched_to_a_building_rows"] == 2 and counts["matched_to_an_amenity_only_rows"] == 1
    assert counts["not_corroborated_rows"] == 1 and counts["match_rate"] == pytest.approx(0.75)
    assert counts["osm_objects_read"] == {"total": 2, "building": 1, "amenity": 1, "building_and_amenity": 0}

    tight = corroborate_shelters(shelters, objects, distance_m=50.0)
    assert tight["corroborated_rows"] == 2  # the shelter 105 m away no longer matches


def test_counts_only_leave_the_module_and_bad_inputs_are_refused() -> None:
    footprint = box(ORIGIN_LON, ORIGIN_LAT, ORIGIN_LON + 0.0002, ORIGIN_LAT + 0.0002)
    counts = corroborate_shelters([_shelter(ORIGIN_LON, ORIGIN_LAT, 5.0)], [(frozenset({BUILDING}), footprint)],
                                  distance_m=150.0)
    assert "test place" not in json.dumps(counts)
    assert str(ORIGIN_LON) not in json.dumps(counts)
    empty = corroborate_shelters([], [], distance_m=150.0)
    assert empty["located_rows"] == 0 and empty["match_rate"] is None
    no_objects = corroborate_shelters([_shelter(ORIGIN_LON, ORIGIN_LAT, 5.0)], [], distance_m=150.0)
    assert no_objects["corroborated_rows"] == 0 and no_objects["match_rate"] == 0.0
    with pytest.raises(ShelterCorroborationError):
        corroborate_shelters([], [], distance_m=-1.0)
    with pytest.raises(ShelterCorroborationError):
        corroborate_shelters([], [(frozenset(), footprint)], distance_m=150.0)


def test_an_invalid_footprint_is_repaired_before_matching() -> None:
    from shapely.geometry import Polygon

    bow_tie = Polygon([(ORIGIN_LON, ORIGIN_LAT), (ORIGIN_LON + 0.0002, ORIGIN_LAT + 0.0002),
                       (ORIGIN_LON + 0.0002, ORIGIN_LAT), (ORIGIN_LON, ORIGIN_LAT + 0.0002)])
    assert not bow_tie.is_valid
    counts = corroborate_shelters([_shelter(ORIGIN_LON + 0.0001, ORIGIN_LAT + 0.0003, 1.0)],
                                  [(frozenset({BUILDING}), bow_tie)], distance_m=150.0)
    assert counts["corroborated_rows"] == 1
