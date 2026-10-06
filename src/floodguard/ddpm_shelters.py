"""Read the DDPM listed-shelter file through a column whitelist (plan 2.2 G32, G33).

The DDPM file (``dpm-gd002_final2.csv``) carries a coordinator name and a phone
number on every row. This reader never returns them: it copies only the
whitelisted columns, and a test checks that the output keys are a subset of
the whitelist.

It also applies the location rule of protocol v1b: a coordinate shared by at
least three rows is treated as a placeholder, and those rows are flagged
``location_unverified`` and left out of the located set.

A listed shelter is a line in a planning list. Nothing here says that a site
was open, usable or safe on any date: capacity is ``listed_planned_unverified``.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import csv
import math
from pathlib import Path
from typing import Any

# Source column -> output key. Columns not listed here are never read into the output.
COLUMN_WHITELIST: dict[str, str] = {
    "ที่": "source_row_number",
    "จังหวัด": "province_th",
    "อำเภอ": "district_th",
    "ตำบล": "tambon_th",
    "สถานที่": "place_name_th",
    "รองรับ": "listed_places",
    "ละติจูด": "latitude",
    "ลองจิจูด": "longitude",
}
DERIVED_KEYS = ("location_status", "capacity_status", "label")
OUTPUT_KEYS = frozenset((*COLUMN_WHITELIST.values(), *DERIVED_KEYS))
SHARED_COORDINATE_ROWS_MIN = 3
CAPACITY_STATUS = "listed_planned_unverified"
LABEL = "listed, operating status unverified"
LOCATED = "located"
LOCATION_UNVERIFIED = "location_unverified"
LOCATION_MISSING = "location_missing"


class DdpmShelterError(ValueError):
    """Raised when the shelter file does not have the expected columns."""


def _number(text: Any) -> float | None:
    """Parse a count or coordinate; thousands separators are removed, blanks give None."""

    cleaned = str(text or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def whitelist_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Copy only the whitelisted columns of each source row.

    Raises:
        DdpmShelterError: when a whitelisted column is missing from a row.
    """

    output = []
    for source in rows:
        missing = [column for column in COLUMN_WHITELIST if column not in source]
        if missing:
            raise DdpmShelterError(f"the shelter file lacks {len(missing)} expected column(s)")
        row: dict[str, Any] = {}
        for column, key in COLUMN_WHITELIST.items():
            value = source[column]
            if key in {"listed_places", "latitude", "longitude"}:
                row[key] = _number(value)
            else:
                row[key] = str(value or "").strip()
        output.append(row)
    return output


def flag_locations(
    rows: Sequence[Mapping[str, Any]], *, shared_rows_min: int = SHARED_COORDINATE_ROWS_MIN
) -> list[dict[str, Any]]:
    """Add ``location_status`` to every row under the shared-coordinate rule.

    A row is ``location_missing`` without a valid WGS84 coordinate,
    ``location_unverified`` when at least ``shared_rows_min`` rows of the whole
    file carry its exact coordinate, and ``located`` otherwise.
    """

    if shared_rows_min < 2:
        raise DdpmShelterError("the shared-coordinate rule needs a minimum of at least 2 rows")

    def coordinate(row: Mapping[str, Any]) -> tuple[float, float] | None:
        latitude, longitude = row.get("latitude"), row.get("longitude")
        if latitude is None or longitude is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        return (latitude, longitude)

    shared = Counter(point for point in map(coordinate, rows) if point is not None)
    flagged = []
    for source in rows:
        point = coordinate(source)
        if point is None:
            status = LOCATION_MISSING
        elif shared[point] >= shared_rows_min:
            status = LOCATION_UNVERIFIED
        else:
            status = LOCATED
        flagged.append({**source, "location_status": status, "capacity_status": CAPACITY_STATUS, "label": LABEL})
    return flagged


def read_ddpm_shelters(path: str | Path) -> list[dict[str, Any]]:
    """Read the national DDPM file and return whitelisted, location-flagged rows."""

    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(COLUMN_WHITELIST) <= set(reader.fieldnames):
            raise DdpmShelterError("the shelter file does not have the expected header")
        rows = whitelist_rows(reader)
    return flag_locations(rows)


def summarise(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count rows and listed places, in total and for the located rows."""

    def places(selected: Iterable[Mapping[str, Any]]) -> float:
        return math.fsum(row["listed_places"] or 0.0 for row in selected)

    located = [row for row in rows if row["location_status"] == LOCATED]
    return {
        "listed_rows": len(rows),
        "listed_places": places(rows),
        "located_rows": len(located),
        "located_places": places(located),
        "unlocated_rows": len(rows) - len(located),
        "unlocated_places": places(rows) - places(located),
        "rows_without_a_listed_capacity": sum(row["listed_places"] is None for row in rows),
    }
