"""Closure rule v1: the modelled state of a road edge under a flood extent.

Protocol v1b, plan section 5 item 2 (task E3). An edge is ``open``, ``delayed``
or ``closed`` under one of three levels:

* ``permissive``: closed on any intersection (more than 1e-6 m inside the extent);
* ``strict``: closed when at least half of the edge is inside the extent;
* ``central``: closed when at least half is inside, or the length inside reaches
  the threshold of the road class; bridges and culverts close at a quarter.

The measurement is the one the finals code uses
(``floodguard.evidence_flood_scenario``): each edge is the straight segment
between its two nodes in EPSG:32647, and the fraction is the length inside the
extent over the length of that segment. The permissive level therefore has to
reproduce the finals closed-edge IDs exactly.

Two things are not decided by the plan and are open item OI-05 of protocol v1b:
the length threshold for motorway, residential and unclassified roads, and
whether an edge is delayed under the strict level. This module takes both as
arguments and refuses to guess. A flood intersection is a closure assumption,
not an observed closure: results carry ``closure_basis``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

CLOSURE_RULE_VERSION = "closure_rule_v1"
LEVELS: tuple[str, ...] = ("strict", "central", "permissive")
MIN_INTERSECTION_M = 1e-6
CLOSED_FRACTION_MIN = 0.5
BRIDGE_CULVERT_CLOSED_FRACTION_MIN = 0.25
DELAY_MIN_INTERSECTED_LENGTH_M = 20.0
# Plan 5 item 2. Motorway, residential and unclassified are not in the plan (OI-05).
PLAN_LENGTH_THRESHOLD_M: dict[str, float] = {
    "trunk": 50.0, "primary": 50.0, "secondary": 50.0, "tertiary": 30.0, "local": 30.0,
}
# Drafter reading DR-B01 of protocol v1b; the owners confirm the pairing at signing.
DELAY_FACTOR_K: dict[str, int] = {"strict": 2, "central": 4, "permissive": 6}
ANALYSIS_EPSG = 32647


class ClosureRuleError(ValueError):
    """Raised when closure inputs are malformed or a needed parameter is undecided."""


def edge_intersections(
    edges: Sequence[Mapping[str, Any]],
    node_coordinates: Mapping[str, Sequence[float]],
    extent: Any,
) -> list[dict[str, Any]]:
    """Measure how much of each edge lies inside a flood extent.

    Args:
        edges: Context edges with ``edge_id``, ``from_node`` and ``to_node``.
        node_coordinates: Longitude and latitude (WGS84) for every node.
        extent: A shapely polygon or multipolygon in WGS84. It may be empty.

    Returns:
        One row per edge with more than 1e-6 m inside the extent, sorted by
        ``edge_id``: ``edge_id``, ``intersection_length_m`` and
        ``intersection_fraction`` (capped at 1).

    Raises:
        ClosureRuleError: for a repeated edge ID, an unknown node or an invalid extent.
    """

    import numpy as np
    import shapely
    from pyproj import Transformer
    from shapely.ops import transform

    ordered = sorted(edges, key=lambda row: row["edge_id"])
    identifiers = [row["edge_id"] for row in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise ClosureRuleError("edge IDs must be unique")
    if extent is None or extent.is_empty or not ordered:
        return []
    if not extent.is_valid:
        raise ClosureRuleError("the flood extent must be a valid geometry")
    try:
        start = np.array([node_coordinates[row["from_node"]][:2] for row in ordered], dtype="float64")
        end = np.array([node_coordinates[row["to_node"]][:2] for row in ordered], dtype="float64")
    except KeyError as error:
        raise ClosureRuleError(f"edge refers to an unknown node: {error.args[0]}") from error
    projection = Transformer.from_crs(4326, ANALYSIS_EPSG, always_xy=True).transform
    projected = transform(projection, extent)
    start_x, start_y = projection(start[:, 0], start[:, 1])
    end_x, end_y = projection(end[:, 0], end[:, 1])
    lines = shapely.linestrings(np.stack([np.column_stack([start_x, start_y]), np.column_stack([end_x, end_y])], axis=1))
    shapely.prepare(projected)
    candidates = np.nonzero(shapely.intersects(projected, lines))[0]
    rows = []
    for index in candidates:
        line = lines[index]
        length = line.intersection(projected).length
        if length > MIN_INTERSECTION_M:
            rows.append({
                "edge_id": identifiers[index],
                "intersection_length_m": length,
                "intersection_fraction": min(1.0, length / line.length),
            })
    return rows


def is_bridge_or_culvert(edge: Mapping[str, Any]) -> bool:
    """Say whether a context edge carries one of the plan's bridge or culvert tags.

    The plan names ``bridge=yes``, ``tunnel=culvert`` and ``culvert=*``. Context
    edges built by ``build_context_inputs`` carry ``bridge`` and ``tunnel``; a
    ``culvert`` key is read when a later context build adds it.
    """

    culvert = edge.get("culvert")
    return (
        edge.get("bridge") == "yes"
        or edge.get("tunnel") == "culvert"
        or (culvert is not None and str(culvert) not in {"", "no"})
    )


def length_threshold_m(road_class: str, thresholds: Mapping[str, float] | None) -> float:
    """Return L(road class) for the central level, or refuse when it is undecided."""

    if thresholds is None or road_class not in thresholds:
        raise ClosureRuleError(
            f"no length threshold for road class {road_class!r}: the plan gives none and "
            "protocol v1b open item OI-05 has not fixed one"
        )
    value = thresholds[road_class]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ClosureRuleError("length thresholds must be positive numbers of metres")
    return float(value)


def edge_state(
    level: str,
    *,
    intersection_length_m: float,
    intersection_fraction: float,
    road_class: str,
    bridge_or_culvert: bool,
    length_thresholds_m: Mapping[str, float] | None = None,
    strict_delays: bool | None = None,
) -> str:
    """Return ``open``, ``delayed`` or ``closed`` for one edge under one level.

    Args:
        level: ``strict``, ``central`` or ``permissive``.
        intersection_length_m: Length of the edge inside the extent.
        intersection_fraction: That length over the edge length, 0-1.
        road_class: The context road class of the edge.
        bridge_or_culvert: See :func:`is_bridge_or_culvert`.
        length_thresholds_m: L by road class; required by the central level.
        strict_delays: Whether a strict-level edge that stays open is delayed
            when at least 20 m is inside the extent. The plan does not say
            (open item OI-05), so the strict level needs an explicit value
            whenever the answer matters.

    Raises:
        ClosureRuleError: for an unknown level, bad numbers or an undecided parameter.
    """

    if level not in LEVELS:
        raise ClosureRuleError(f"unknown closure level {level!r}")
    if not (math.isfinite(intersection_length_m) and intersection_length_m >= 0):
        raise ClosureRuleError("intersection length must be a non-negative number")
    if not 0 <= intersection_fraction <= 1:
        raise ClosureRuleError("intersection fraction must lie between 0 and 1")
    if intersection_length_m <= MIN_INTERSECTION_M:
        return "open"
    if level == "permissive":
        return "closed"
    if intersection_fraction >= CLOSED_FRACTION_MIN:
        return "closed"
    long_enough_to_delay = intersection_length_m >= DELAY_MIN_INTERSECTED_LENGTH_M
    if level == "strict":
        if not long_enough_to_delay:
            return "open"
        if strict_delays is None:
            raise ClosureRuleError(
                "the delay rule under the strict level is not decided (protocol v1b open item OI-05)"
            )
        return "delayed" if strict_delays else "open"
    if bridge_or_culvert and intersection_fraction >= BRIDGE_CULVERT_CLOSED_FRACTION_MIN:
        return "closed"
    if intersection_length_m >= length_threshold_m(road_class, length_thresholds_m):
        return "closed"
    return "delayed" if long_enough_to_delay else "open"


def apply_closure_rule(
    level: str,
    edges: Sequence[Mapping[str, Any]],
    intersections: Sequence[Mapping[str, Any]],
    *,
    flood_input_id: str,
    length_thresholds_m: Mapping[str, float] | None = None,
    strict_delays: bool | None = None,
) -> dict[str, Any]:
    """Apply one closure level to measured intersections.

    Returns:
        ``closed_edge_ids`` (sorted), ``delayed_edges`` (each with its travel
        time multiplier ``1 + k x f``), the level, the rule version and
        ``closure_basis``. Edges outside the extent are unchanged by
        assumption, not because they were seen dry.
    """

    if not flood_input_id:
        raise ClosureRuleError("a flood input ID is required for closure_basis")
    by_id = {row["edge_id"]: row for row in edges}
    if len(by_id) != len(edges):
        raise ClosureRuleError("edge IDs must be unique")
    closed: list[str] = []
    delayed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in intersections:
        edge_id = row["edge_id"]
        if edge_id not in by_id or edge_id in seen:
            raise ClosureRuleError("intersections must name each known edge at most once")
        seen.add(edge_id)
        edge = by_id[edge_id]
        state = edge_state(
            level,
            intersection_length_m=row["intersection_length_m"],
            intersection_fraction=row["intersection_fraction"],
            road_class=str(edge.get("road_class", "")),
            bridge_or_culvert=is_bridge_or_culvert(edge),
            length_thresholds_m=length_thresholds_m,
            strict_delays=strict_delays,
        )
        if state == "closed":
            closed.append(edge_id)
        elif state == "delayed":
            delayed.append({
                "edge_id": edge_id,
                "travel_time_factor": 1 + DELAY_FACTOR_K[level] * row["intersection_fraction"],
            })
    return {
        "closure_rule_version": CLOSURE_RULE_VERSION,
        "level": level,
        "closure_basis": f"modelled_from_{flood_input_id}",
        "closed_edge_ids": sorted(closed),
        "delayed_edges": sorted(delayed, key=lambda row: row["edge_id"]),
        "intersected_edge_count": len(seen),
    }


def modified_edges(edges: Sequence[Mapping[str, Any]], result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the edge list with closed edges removed and delayed edges slowed.

    A delayed edge needs ``normal_minutes``; its value is multiplied by the
    factor from :func:`apply_closure_rule`. The input rows are not changed.
    """

    closed = set(result["closed_edge_ids"])
    factors = {row["edge_id"]: row["travel_time_factor"] for row in result["delayed_edges"]}
    changed = []
    for edge in edges:
        if edge["edge_id"] in closed:
            continue
        row = dict(edge)
        if row["edge_id"] in factors:
            if "normal_minutes" not in row:
                raise ClosureRuleError("a delayed edge needs normal_minutes")
            row["normal_minutes"] = row["normal_minutes"] * factors[row["edge_id"]]
            row["closure_state"] = "delayed"
        changed.append(row)
    return changed
