"""Corroborate DDPM located shelters against OpenStreetMap (protocol v1b, facility set "corroborated").

Plan section 5 item 11 axis 3 defines a "two-source corroborated" facility
level: an OSM hospital matched to a DGA record within 150 m, and a DDPM located
shelter matched to an OSM building or amenity. Protocol v1b fixes the shelter
match distance at 150 m (owner choice 19). This module counts how many located
shelters have an OSM building or amenity within that distance.

A match says that a mapped structure stands near the listed coordinate. It
does not say that the structure is the shelter, that the shelter exists, or
that it was open on any date: the level is labelled "corroborated, not
confirmed-open". The output is counts only; no shelter row, name or
coordinate leaves this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

from floodguard.ddpm_shelters import LOCATED

BUILDING = "building"
AMENITY = "amenity"
MATCH_KINDS = (BUILDING, AMENITY)
METRIC_EPSG = 32647
RULE = (
    "A DDPM row whose location status is 'located' is corroborated when an OSM object tagged building=* (any value "
    "but 'no') or amenity=* (any value but 'no') lies within the match distance of its coordinate, measured in "
    "EPSG:32647 from the shelter point to the nearest point of the object (0 m when the point is inside it)."
)


class ShelterCorroborationError(ValueError):
    """Raised for an invalid match distance or an object without a match kind."""


def osm_match_kinds(tags: Mapping[str, str]) -> frozenset[str]:
    """Return which match kinds an OSM object has: ``building``, ``amenity``, both or neither.

    Args:
        tags: The object's OSM tags (key to value), as ``evidence_context._tags`` returns them.
    """

    kinds = set()
    for kind in MATCH_KINDS:
        value = str(tags.get(kind) or "").strip()
        if value and value.casefold() != "no":
            kinds.add(kind)
    return frozenset(kinds)


def corroborate_shelters(
    shelters: Sequence[Mapping[str, Any]],
    osm_objects: Sequence[tuple[frozenset[str], Any]],
    *,
    distance_m: float,
    metric_epsg: int = METRIC_EPSG,
) -> dict[str, Any]:
    """Count the located shelters that have an OSM building or amenity within ``distance_m``.

    Args:
        shelters: Rows from ``ddpm_shelters.read_ddpm_shelters`` (already limited to the area of interest).
            Only rows whose ``location_status`` is ``located`` are tested.
        osm_objects: ``(kinds, geometry)`` pairs, the geometry a shapely object in WGS84 longitude and
            latitude and ``kinds`` the output of ``osm_match_kinds``. Objects without a kind are refused.
        distance_m: The match distance in metres (protocol v1b: 150).
        metric_epsg: The projected CRS the distance is measured in.

    Returns:
        Counts only: located rows and places, rows and places matched to a building or an amenity, rows
        matched to a building, rows matched to an amenity only, the match rate, and how many OSM objects
        of each kind were read.

    Raises:
        ShelterCorroborationError: for a negative or non-finite distance, or an object without a kind.
    """

    import numpy as np
    from pyproj import Transformer
    import shapely

    if not math.isfinite(distance_m) or distance_m < 0:
        raise ShelterCorroborationError("the match distance must be a finite number of metres, 0 or more")
    for kinds, _geometry in osm_objects:
        if not kinds or not set(kinds) <= set(MATCH_KINDS):
            raise ShelterCorroborationError("every OSM object needs the kind building, amenity or both")

    transformer = Transformer.from_crs(4326, metric_epsg, always_xy=True)

    def to_metres(coordinates: Any) -> Any:
        x, y = transformer.transform(coordinates[:, 0], coordinates[:, 1])
        return np.column_stack([x, y])

    geometries = np.asarray([geometry for _kinds, geometry in osm_objects], dtype=object)
    if len(geometries):
        geometries = shapely.transform(geometries, to_metres)
        invalid = ~shapely.is_valid(geometries)
        if invalid.any():
            geometries[invalid] = shapely.make_valid(geometries[invalid])
    kinds_by_index = [kinds for kinds, _geometry in osm_objects]
    tree = shapely.STRtree(geometries)

    located = [row for row in shelters if row.get("location_status") == LOCATED]
    matched_any = matched_building = matched_amenity_only = 0
    places_any = 0.0
    for row in located:
        x, y = transformer.transform(row["longitude"], row["latitude"])
        hits = tree.query(shapely.points(x, y), predicate="dwithin", distance=distance_m)
        kinds = set().union(*(kinds_by_index[int(index)] for index in hits)) if len(hits) else set()
        if kinds:
            matched_any += 1
            places_any += row.get("listed_places") or 0.0
        if BUILDING in kinds:
            matched_building += 1
        elif AMENITY in kinds:
            matched_amenity_only += 1
    located_places = math.fsum(row.get("listed_places") or 0.0 for row in located)
    return {
        "rule": RULE,
        "match_distance_m": distance_m,
        "metric_epsg": metric_epsg,
        "located_rows": len(located),
        "located_places": located_places,
        "corroborated_rows": matched_any,
        "corroborated_places": places_any,
        "matched_to_a_building_rows": matched_building,
        "matched_to_an_amenity_only_rows": matched_amenity_only,
        "not_corroborated_rows": len(located) - matched_any,
        "match_rate": (matched_any / len(located)) if located else None,
        "osm_objects_read": {
            "total": len(osm_objects),
            "building": sum(BUILDING in kinds for kinds in kinds_by_index),
            "amenity": sum(AMENITY in kinds for kinds in kinds_by_index),
            "building_and_amenity": sum(kinds == frozenset(MATCH_KINDS) for kinds in kinds_by_index),
        },
    }
