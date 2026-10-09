"""Class rule v2 as a report-only second reading: the order of its triggers, with B, C and D supplied.

Protocol v1a (``class_rules.v2``) names five triggers and evaluates them in the order E, A, B, C, D; the first one
met gives the letter, and a unit that meets none has ``no_v2_trigger``. Protocol v1b (``class_rule_v2_inputs``)
defines what B, C and D need. :func:`floodguard.planning_assessment.class_v2` writes the same rule into a result
file; this module applies it to triggers a later stage evaluated, without touching that file.

The second reading is never binding: class rule v1 gives the class of a unit (decision D6).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ORDER: tuple[str, ...] = ("E", "A", "B", "C", "D")
NO_V2_TRIGGER = "no_v2_trigger"
NOT_EVALUATED = "not_evaluated"
FPPS_MIN = 35.0
ISOLATED_RESIDENTS_MIN = 500.0
SERVED_RESIDENTS_MIN = 100.0
JRC_OCCURRENCE_MIN_PERCENT = 25
RECURRENCE_LAND_SHARE_MIN = 0.20


class ClassV2ReadingError(ValueError):
    """The inputs of the second reading do not fit together."""


def evaluate(*, met_e: bool | None, met_a: bool | None, fpps: float | None, confidence_class: str,
             isolated_residents: float | None, facility_hit: bool | None, recurrence_share: float | None) -> dict[str, Any]:
    """Apply the order E, A, B, C, D.

    Args:
        met_e: Trigger E as the result file states it.
        met_a: Trigger A as the result file states it.
        fpps: The planning score of the unit.
        confidence_class: ``low`` or ``medium``.
        isolated_residents: The largest number of the unit's residents one top-20 link inside the extent cuts
            off from every route; ``None`` when no stage closed the links.
        facility_hit: Whether a facility that serves the unit lies inside the extent or loses every vehicle
            route; ``None`` when no stage ran the test.
        recurrence_share: The share of the unit's land outside permanent water with a JRC occurrence of 25
            percent or more; ``None`` when it was not computed.

    Returns:
        ``triggers`` (each met, not met or ``None`` for not evaluated) and ``result``: a letter,
        ``no_v2_trigger``, or ``not_evaluated`` when the result depends on a trigger that was not evaluated.
    """

    if confidence_class not in ("low", "medium"):
        raise ClassV2ReadingError("the confidence class must be low or medium")
    if isolated_residents is not None and isolated_residents < 0:
        raise ClassV2ReadingError("isolated residents cannot be below zero")
    if recurrence_share is not None and not 0 <= recurrence_share <= 1:
        raise ClassV2ReadingError("the recurrence share must lie inside 0 to 1")
    scored_enough = fpps is not None and fpps >= FPPS_MIN
    low = confidence_class == "low"
    met: dict[str, bool | None] = {
        "E": met_e,
        "A": met_a,
        "B": None if isolated_residents is None else isolated_residents >= ISOLATED_RESIDENTS_MIN,
        "C": False if (not scored_enough or low) else facility_hit,
        "D": False if not scored_enough else (None if recurrence_share is None else recurrence_share >= RECURRENCE_LAND_SHARE_MIN),
    }
    result = NO_V2_TRIGGER
    for trigger in ORDER:
        if met[trigger] is None:
            result = NOT_EVALUATED
            break
        if met[trigger]:
            result = trigger
            break
    return {"triggers": met, "result": result}


SHELTER_KIND = "located_ddpm_shelter"
PITCH_LEVEL_NOTE = ("Shelter figures are pitch level (protocol v1b; decision log R41): the row identifier of the shelter and the "
                    "number of residents it is nearest for are in a file outside Git.")


def public_facility_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """The form of a serving facility that may stand in a public file.

    A hospital row is public as it is. A located DDPM shelter keeps what trigger C reads (whether its point lies
    inside the flood extent, and whether it loses every vehicle route) and loses its row identifier and the number
    of residents it is nearest for.
    """

    if row.get("kind") != SHELTER_KIND:
        return dict(row)
    return {"kind": SHELTER_KIND,
            "nearest_for_at_least_the_residents_the_trigger_asks": True,
            "point_inside_the_flood_extent": bool(row["point_inside_the_flood_extent"]),
            "no_vehicle_route_to_a_main_road_entry_in_the_flooded_run": bool(row["no_vehicle_route_to_a_main_road_entry_in_the_flooded_run"]),
            "pitch_level": PITCH_LEVEL_NOTE}
