"""Figures that set one flood input beside another (plan: ``docs/proposal_execution/flood_input_comparison_plan_v1.md``).

Pure functions over counts that other modules computed: how two sets of closed road edges overlap, how two
orderings of the same units agree, and the ratio of two totals. They compute no component, no FPPS and no A-E
class, and none of the inputs they compare is a reference for another.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence


class ComparisonError(ValueError):
    """The values cannot be compared."""


def set_overlap(first: Iterable[str], second: Iterable[str]) -> dict[str, Any]:
    """Count the members of two sets: in both, in one only, and the share of the union that is in both."""

    a, b = set(first), set(second)
    both, union = len(a & b), len(a | b)
    return {
        "first": len(a), "second": len(b), "both": both,
        "first_only": len(a - b), "second_only": len(b - a),
        "share_of_union_in_both": round(both / union, 6) if union else None,
    }


def _ranks(values: Sequence[float]) -> list[float]:
    """Ranks from 1, the largest value first; equal values share the mean of their ranks."""

    order = sorted(range(len(values)), key=lambda index: -values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        mean_rank = (position + end) / 2.0 + 1.0
        for index in order[position:end + 1]:
            ranks[index] = mean_rank
        position = end + 1
    return ranks


def spearman(first: Mapping[str, float], second: Mapping[str, float]) -> float | None:
    """Spearman rank correlation of two values over the same units; ``None`` when either does not vary.

    Raises:
        ComparisonError: when the two mappings do not name the same units, or name fewer than three.
    """

    if set(first) != set(second):
        raise ComparisonError("both mappings must name the same units")
    units = sorted(first)
    if len(units) < 3:
        raise ComparisonError("a rank correlation needs at least three units")
    x = _ranks([float(first[unit]) for unit in units])
    y = _ranks([float(second[unit]) for unit in units])
    mean_x, mean_y = math.fsum(x) / len(x), math.fsum(y) / len(y)
    spread_x = math.fsum((value - mean_x) ** 2 for value in x)
    spread_y = math.fsum((value - mean_y) ** 2 for value in y)
    if spread_x == 0 or spread_y == 0:
        return None
    together = math.fsum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    return round(together / math.sqrt(spread_x * spread_y), 6)


def ratio(top: float, bottom: float) -> float | None:
    """``top`` over ``bottom``, or ``None`` when ``bottom`` is zero."""

    return round(float(top) / float(bottom), 6) if bottom else None


def largest(values: Mapping[str, float]) -> dict[str, Any]:
    """The unit with the largest value, and whether another unit ties with it; ``None`` when every value is zero."""

    if not values:
        raise ComparisonError("no unit to rank")
    top = max(values.values())
    holders = sorted(unit for unit, value in values.items() if value == top)
    if top <= 0:
        return {"unit_id": None, "value": 0.0, "tied_with": []}
    return {"unit_id": holders[0], "value": round(float(top), 3), "tied_with": holders[1:]}


def compare_inputs(first: Mapping[str, Any], second: Mapping[str, Any], *, closed_first: Iterable[str],
                   closed_second: Iterable[str]) -> dict[str, Any]:
    """Set the per-unit counts of two flood inputs beside each other.

    ``first`` and ``second`` each hold, per unit ID, ``flooded_land_km2``, ``residents_inside_extent`` and
    ``residents_losing_every_route`` (at one closure level), as counts. The closed edge IDs are those of the same
    closure level.
    """

    def column(rows: Mapping[str, Any], key: str) -> dict[str, float]:
        return {unit: float(row[key]) for unit, row in rows.items()}

    def total(rows: Mapping[str, Any], key: str) -> float:
        return math.fsum(column(rows, key).values())

    result: dict[str, Any] = {"closed_road_edges": set_overlap(closed_first, closed_second)}
    for key in ("flooded_land_km2", "residents_inside_extent", "residents_losing_every_route"):
        result[key] = {
            "first_total": round(total(first, key), 3),
            "second_total": round(total(second, key), 3),
            "first_over_second": ratio(total(first, key), total(second, key)),
            "rank_correlation_of_units": spearman(column(first, key), column(second, key)),
        }
    top_first = largest(column(first, "residents_losing_every_route"))
    top_second = largest(column(second, "residents_losing_every_route"))
    result["unit_with_most_residents_losing_every_route"] = {
        "first": top_first, "second": top_second,
        "same": top_first["unit_id"] is not None and top_first["unit_id"] == top_second["unit_id"],
    }
    return result
