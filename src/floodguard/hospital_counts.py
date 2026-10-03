"""Count OSM hospital objects the way protocol v1b counts hospitals (owner choice 22).

Decision log R12 (3 October 2026) adopted owner choice 22: for the plan's "at
least 4 hospitals" test, one hospital is a distinct named hospital. OSM objects
with the same name are one hospital, and an object without a name is not
counted. Two names are the same when they are equal after runs of whitespace
(spaces, tabs, line breaks) are collapsed to one space and the case is folded.

The E0 context spike (``scripts/run_planning_context_spike.py``) and the
planning-frame build (``floodguard.planning_frames``) both count through this
module, so their counts are made under one reading of the rule. Counts only:
nothing here checks that an object is a working hospital.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

# The name floodguard.evidence_context gives an OSM facility that has no name tag.
UNNAMED_FACILITY = "Unnamed OSM candidate"


def hospital_name_key(name: Any) -> str | None:
    """Return the key under which two hospital names count as the same, or None for an unnamed object.

    Args:
        name: The ``name`` of an OSM facility row.

    Returns:
        The name with every run of whitespace collapsed to one space, trimmed and
        case-folded; None when the name is missing, blank or the unnamed label.
    """

    if name is None:
        return None
    text = " ".join(str(name).split())
    if not text or text == UNNAMED_FACILITY:
        return None
    return text.casefold()


def count_hospitals(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Count OSM objects, distinct named hospitals, unnamed objects and repeats of a named hospital.

    Args:
        rows: OSM hospital rows, each with a ``name``.

    Returns:
        ``osm_objects`` (every row), ``distinct_named_hospitals`` (the unit of owner
        choice 22), ``unnamed_objects`` and ``objects_that_repeat_a_named_hospital``.
        The last three always add up to ``osm_objects``.
    """

    keys = [hospital_name_key(row.get("name")) for row in rows]
    named = Counter(key for key in keys if key is not None)
    return {
        "osm_objects": len(keys),
        "distinct_named_hospitals": len(named),
        "unnamed_objects": sum(key is None for key in keys),
        "objects_that_repeat_a_named_hospital": sum(count - 1 for count in named.values()),
    }
