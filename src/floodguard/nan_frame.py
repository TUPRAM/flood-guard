"""The frame and planning context of the Nan case N1 (decision log R51).

``docs/proposal_execution/nan_case_protocol_v1.json``, key ``frame``, fixes the frame of case N1:

* the units: every COD-AB ``tha_admin3`` unit of Mueang Nan (TH5501), Phu Phiang (TH5514) and Wiang Sa
  (TH5507), 35 units (11, 7 and 17);
* the routing geometry: the union of the units buffered by 3 km, the SE2 frame rule of protocol v1b
  (``floodguard.planning_frames.routing_geometry``: EPSG:32647, 16 segments per quarter circle, clipped to the
  COD-AB polygon of Thailand);
* the hospitals: every OSM hospital whose routing point lies inside the routing geometry (the SE2 rule);
* everything else of the planning chain as protocols v1a and v1b state it: the road graph, the grade joins, the
  vehicle travel times and the destinations of plan task E4, the services of ``facility_sets.services`` and the
  demand cells of WorldPop 2020 counted for the unit that holds their centre.

The functions here are pure: they take boundary rows, a planning context and counts that were already read, so
they run on invented fixtures. ``scripts/nan_case_frame.py`` reads the inputs and writes the files.

Nothing here reads a flood layer or computes a flood flag, a closure, an access loss, a component value, an
FPPS, an A-E class or an ensemble. The only access figures are those of the baseline (no flood), per tambon,
so that a later stage can check the baseline it computes itself. Planning guidance only: not an official
warning and not real-time.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import math
from typing import Any

from floodguard import planning_frames

CASE_ID = "N1"
CASE_KEY = "n1"
CASE_SLUG = "n1_nan"
PROVINCE_PCODE = "TH55"
# (district code, English name in COD-AB, number of tha_admin3 units the protocol states).
DISTRICTS: tuple[tuple[str, str, int], ...] = (
    ("TH5501", "Mueang Nan", 11),
    ("TH5514", "Phu Phiang", 7),
    ("TH5507", "Wiang Sa", 17),
)
EXPECTED_UNITS = 35
GRID_EPSG = 32647
GRID_CELL_M = 20
UNIT_RASTER_NONE = 0
UNIT_RASTER_SEVERAL = 255
HOSPITAL = "hospital"
MAIN_ROAD_ENTRY = "main_road_entry"
MAIN_ROAD_CLASSES = ("primary", "trunk")
RECORD_KEYS = ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions", "official_warning",
               "operational_status")
DEMAND_COLUMNS = (
    "population_id", "unit_id", "unit_assignment", "residents_2020", "residents_rescaled_2024",
    "kept_at_2020", "longitude", "latitude", "x_32647", "y_32647", "grid_row", "grid_col", "node_id",
    "snap_distance_m",
)


class NanFrameError(ValueError):
    """Raised when an input of the N1 frame breaks a rule of the case protocol."""


# ---------------------------------------------------------------------------
# What the case protocol states
# ---------------------------------------------------------------------------


def check_protocol_frame(protocol: Mapping[str, Any]) -> dict[str, Any]:
    """Check that the case protocol states the frame this module builds, and return its frame and grid.

    Args:
        protocol: The parsed ``nan_case_protocol_v1.json``.

    Returns:
        ``frame`` (the protocol's frame block) and ``grid`` (``west``, ``north``, ``rows``, ``cols``, ``epsg``,
        ``cell_m``).

    Raises:
        NanFrameError: when the protocol names another case, province, district list, unit count or grid kind.
    """

    try:
        frame = protocol["frame"]
        grid = protocol["grid"]
        if protocol["case_id"] != CASE_ID:
            raise NanFrameError(f"the protocol is for case {protocol['case_id']!r}, not {CASE_ID}")
        if frame["province_pcode"] != PROVINCE_PCODE:
            raise NanFrameError("the protocol names another province")
        if list(frame["district_pcodes"]) != [code for code, _name, _count in DISTRICTS]:
            raise NanFrameError("the protocol names other districts, or another order")
        if list(frame["district_names"]) != [name for _code, name, _count in DISTRICTS]:
            raise NanFrameError("the protocol names the districts otherwise")
        counts = ", ".join(str(count) for _code, _name, count in DISTRICTS[:-1]) + f" and {DISTRICTS[-1][2]}"
        if f"{EXPECTED_UNITS} units: {counts}" not in str(frame["units"]):
            raise NanFrameError("the protocol states another number of units")
        if "buffered by 3 km" not in str(frame["routing_geometry"]):
            raise NanFrameError("the protocol states another routing rule")
        if int(grid["epsg"]) != GRID_EPSG or int(grid["cell_m"]) != GRID_CELL_M:
            raise NanFrameError("the protocol grid is not EPSG:32647 at 20 m")
        cells = grid["frame"]
        return {
            "frame": dict(frame),
            "grid": {"west": int(cells["west"]), "north": int(cells["north"]), "rows": int(cells["rows"]),
                     "cols": int(cells["cols"]), "epsg": GRID_EPSG, "cell_m": GRID_CELL_M},
        }
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, NanFrameError):
            raise
        raise NanFrameError(f"the protocol does not hold the frame of case {CASE_ID}: {error!r}") from error


def frame_units(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the 35 units of the frame, sorted by unit code, after checking each district's count.

    Args:
        rows: Boundary rows in the shape of ``floodguard.planning_frames.district_units`` (``adm3_pcode``,
            ``adm2_pcode`` and a valid shapely ``geometry``), of the three districts and possibly others.

    Raises:
        NanFrameError: when a district does not have the number of units the protocol states, a unit code
            repeats or a district name differs.
        floodguard.planning_frames.PlanningFrameError: for an empty or invalid geometry.
    """

    units: list[dict[str, Any]] = []
    for code, name, count in DISTRICTS:
        selected = planning_frames.district_units(rows, code)
        if len(selected) != count:
            raise NanFrameError(f"district {code} has {len(selected)} units in COD-AB, not {count}")
        names = {str(row.get("adm2_name")) for row in selected}
        if names != {name}:
            raise NanFrameError(f"district {code} is named {sorted(names)} in COD-AB, not {name!r}")
        units.extend(selected)
    codes = [row["adm3_pcode"] for row in units]
    if len(codes) != EXPECTED_UNITS or len(set(codes)) != len(codes):
        raise NanFrameError(f"the frame has {len(set(codes))} distinct units, not {EXPECTED_UNITS}")
    return sorted(units, key=lambda row: row["adm3_pcode"])


def snapped_grid(bounds: Sequence[float], cell_m: int = GRID_CELL_M) -> dict[str, int]:
    """Snap metric bounds outward to a cell size and return the grid as ``west``, ``north``, ``rows``, ``cols``.

    Args:
        bounds: ``(west, south, east, north)`` in metres.
        cell_m: The cell size in metres.

    Raises:
        NanFrameError: for empty bounds or a cell size that is not positive.
    """

    if cell_m <= 0:
        raise NanFrameError("the cell size must be positive")
    west, south, east, north = (float(value) for value in bounds)
    if not (west < east and south < north):
        raise NanFrameError("the bounds are empty")
    left = math.floor(west / cell_m) * cell_m
    right = math.ceil(east / cell_m) * cell_m
    bottom = math.floor(south / cell_m) * cell_m
    top = math.ceil(north / cell_m) * cell_m
    return {"west": int(left), "north": int(top), "rows": int((top - bottom) // cell_m),
            "cols": int((right - left) // cell_m)}


def compare_grid(computed: Mapping[str, int], stated: Mapping[str, int]) -> dict[str, Any]:
    """Compare a grid computed from the frame with the grid the protocol states (``west``, ``north``, ``rows``, ``cols``)."""

    keys = ("west", "north", "rows", "cols")
    differing = [key for key in keys if int(computed[key]) != int(stated[key])]
    return {
        "computed": {key: int(computed[key]) for key in keys},
        "stated_in_the_protocol": {key: int(stated[key]) for key in keys},
        "differing_keys": differing,
        "same": not differing,
    }


def grid_cell(x: float, y: float, grid: Mapping[str, int], cell_m: int = GRID_CELL_M) -> tuple[int, int] | None:
    """Return ``(row, col)`` of the grid cell that holds a point (EPSG:32647), or None outside the grid.

    A point on the west or north edge of a cell belongs to that cell, as ``floor`` places it.
    """

    column = math.floor((float(x) - grid["west"]) / cell_m)
    row = math.floor((grid["north"] - float(y)) / cell_m)
    if 0 <= row < grid["rows"] and 0 <= column < grid["cols"]:
        return int(row), int(column)
    return None


# ---------------------------------------------------------------------------
# Units, hospitals and destinations
# ---------------------------------------------------------------------------


def unit_table(units: Sequence[Mapping[str, Any]], to_metres: Callable[[Any], Any]) -> list[dict[str, Any]]:
    """Return one record per unit: codes, names, area in EPSG:32647 and the value it takes in the unit raster.

    The raster values run from 1 in unit-code order; 0 means a cell centre in no unit and 255 a cell centre in
    more than one.
    """

    if len(units) >= UNIT_RASTER_SEVERAL:
        raise NanFrameError("too many units for an 8-bit unit raster")
    rows = []
    for value, row in enumerate(sorted(units, key=lambda item: item["adm3_pcode"]), start=1):
        rows.append({
            "adm3_pcode": str(row["adm3_pcode"]),
            "adm3_name": str(row["adm3_name"]),
            "adm3_name_th": str(row["adm3_name_th"]),
            "adm2_pcode": str(row["adm2_pcode"]),
            "adm2_name": str(row["adm2_name"]),
            "area_km2": round(to_metres(row["geometry"]).area / 1e6, 6),
            "raster_value": value,
        })
    return rows


def containing_units(point: Any, units: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the codes of every unit whose polygon covers a point (none, one, or more on a shared boundary)."""

    return sorted(str(row["adm3_pcode"]) for row in units if row["geometry"].covers(point))


def node_ids_sha256(node_ids: Sequence[str]) -> str:
    """SHA-256 of a list of node IDs as compact JSON, as the E4 receipt hashes its main-road entries."""

    return hashlib.sha256(json.dumps(list(node_ids), separators=(",", ":")).encode("ascii")).hexdigest()


def main_road_summary(entries: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarise the main-road entries of a context (``floodguard.planning_context.main_road_entries``).

    Args:
        entries: The entries, each with ``node_id`` and ``osm_way_ids``.
        edges: The context's road edges (``edge_id``, ``osm_way_id``, ``road_class``, ``edge_kind``).

    Returns:
        The number of entries, the SHA-256 of their node IDs in the order given, the OSM ways they lie on with
        the road class of each, and the count of ways and of entries per class (a node can lie on both).
    """

    classes: dict[str, set[str]] = {}
    for edge in edges:
        if edge.get("road_class") in MAIN_ROAD_CLASSES and edge.get("edge_kind") is None:
            classes.setdefault(str(edge.get("osm_way_id")), set()).add(str(edge["road_class"]))
    ways = sorted({str(way) for row in entries for way in row["osm_way_ids"]}, key=lambda value: (len(value), value))
    missing = [way for way in ways if way not in classes]
    if missing:
        raise NanFrameError(f"an entry lies on a way with no trunk or primary edge: {missing[:3]}")
    entries_by_class: Counter[str] = Counter()
    for row in entries:
        for road_class in sorted({cls for way in row["osm_way_ids"] for cls in classes[str(way)]}):
            entries_by_class[road_class] += 1
    ways_by_class: Counter[str] = Counter(cls for way in ways for cls in classes[way])
    return {
        "entries": len(entries),
        "node_ids_sha256": node_ids_sha256([str(row["node_id"]) for row in entries]),
        "osm_ways": [{"osm_way_id": way, "road_classes": sorted(classes[way])} for way in ways],
        "ways_by_road_class": dict(sorted(ways_by_class.items())),
        "entries_by_road_class": dict(sorted(entries_by_class.items())),
    }


# ---------------------------------------------------------------------------
# Demand cells
# ---------------------------------------------------------------------------


def demand_rows(
    population: Sequence[Mapping[str, Any]],
    assignment: Mapping[str, Mapping[str, Any]],
    to_metres_xy: Callable[[float, float], tuple[float, float]],
    grid: Mapping[str, int],
    rescaled: Mapping[str, float] | None = None,
    kept_at_2020: Mapping[str, bool] | None = None,
) -> list[list[Any]]:
    """Return the demand cells as rows in the order of ``DEMAND_COLUMNS``, sorted by population ID.

    Args:
        population: The context's demand cells (``population_id``, ``total_population``, ``longitude``,
            ``latitude``, ``node_id``, ``snap_distance_m``).
        assignment: ``floodguard.access_diff.assign_cells`` of those cells: the unit that holds the centre.
        to_metres_xy: Projects a longitude and latitude to EPSG:32647.
        grid: The 20 m frame grid (``west``, ``north``, ``rows``, ``cols``).
        rescaled: The 2024-rescaled count of each cell, or None when it was not built.
        kept_at_2020: The cells whose 1 km cell has no 2024 total, so that they keep their 2020 count.

    Raises:
        NanFrameError: for a repeated population ID, a cell without an assignment or a rescaled count, or a
            resident count that is not finite and at least 0.
    """

    rows = []
    seen: set[str] = set()
    for cell in sorted(population, key=lambda item: str(item["population_id"])):
        identifier = str(cell["population_id"])
        if identifier in seen:
            raise NanFrameError("population IDs must be unique")
        seen.add(identifier)
        if identifier not in assignment:
            raise NanFrameError("every demand cell needs a unit assignment")
        residents = cell["total_population"]
        if isinstance(residents, bool) or not isinstance(residents, (int, float)) or not math.isfinite(residents) \
                or residents < 0:
            raise NanFrameError("a resident count must be a finite number, 0 or more")
        if rescaled is not None and identifier not in rescaled:
            raise NanFrameError("a demand cell has no rescaled count")
        x, y = to_metres_xy(float(cell["longitude"]), float(cell["latitude"]))
        position = grid_cell(x, y, grid)
        rows.append([
            identifier,
            assignment[identifier]["unit_id"],
            assignment[identifier]["unit_assignment"],
            float(residents),
            None if rescaled is None else float(rescaled[identifier]),
            None if kept_at_2020 is None else bool(kept_at_2020.get(identifier, False)),
            float(cell["longitude"]),
            float(cell["latitude"]),
            round(float(x), 3),
            round(float(y), 3),
            None if position is None else position[0],
            None if position is None else position[1],
            cell.get("node_id"),
            cell.get("snap_distance_m"),
        ])
    return rows


def demand_summary(rows: Sequence[Sequence[Any]], unit_ids: Sequence[str]) -> dict[str, Any]:
    """Count the demand cells and residents in total, per unit and outside every unit, for both demands."""

    index = {name: position for position, name in enumerate(DEMAND_COLUMNS)}
    per_unit: dict[str, dict[str, list[float]]] = {str(unit): {"cells": [], "r2020": [], "r2024": []} for unit in unit_ids}
    outside = {"cells": 0, "r2020": [], "r2024": []}
    for row in rows:
        unit = row[index["unit_id"]]
        r2020 = float(row[index["residents_2020"]])
        r2024 = row[index["residents_rescaled_2024"]]
        if unit is None:
            outside["cells"] += 1
            outside["r2020"].append(r2020)
            if r2024 is not None:
                outside["r2024"].append(float(r2024))
            continue
        if str(unit) not in per_unit:
            raise NanFrameError(f"a demand cell counts for unit {unit!r}, which is not a unit of the frame")
        per_unit[str(unit)]["cells"].append(1.0)
        per_unit[str(unit)]["r2020"].append(r2020)
        if r2024 is not None:
            per_unit[str(unit)]["r2024"].append(float(r2024))
    rescaled = any(row[index["residents_rescaled_2024"]] is not None for row in rows)
    return {
        "demand_cells": len(rows),
        "residents_2020": math.fsum(float(row[index["residents_2020"]]) for row in rows),
        "residents_rescaled_2024": math.fsum(float(row[index["residents_rescaled_2024"]]) for row in rows
                                             if row[index["residents_rescaled_2024"]] is not None) if rescaled else None,
        "cells_outside_the_grid": sum(row[index["grid_row"]] is None for row in rows),
        "cells_in_no_unit_or_several": {"demand_cells": outside["cells"], "residents_2020": math.fsum(outside["r2020"]),
                                        "residents_rescaled_2024": math.fsum(outside["r2024"]) if rescaled else None},
        "by_unit": {
            unit: {"demand_cells": int(len(values["cells"])), "residents_2020": math.fsum(values["r2020"]),
                   "residents_rescaled_2024": math.fsum(values["r2024"]) if rescaled else None}
            for unit, values in sorted(per_unit.items())
        },
    }


# ---------------------------------------------------------------------------
# Baseline access (no flood)
# ---------------------------------------------------------------------------


def baseline_row(row: Mapping[str, Any], *, hospital_gap_minutes: int, main_road_gap_minutes: int,
                 no_route_share: Callable[[float, float], float]) -> dict[str, Any]:
    """Return the baseline figures of one row of ``floodguard.access_diff.unit_rows`` run with no flood.

    The row must come from a run whose flooded side is the baseline itself, so only the baseline counts are
    kept: residents, those connected to the graph within 250 m, those with a route to a hospital or a main-road
    entry, those within each reported threshold, and the baseline vehicle no-route share of condition C7
    (connected residents with no route to any hospital, over the connected residents; 1 when nobody is
    connected), computed by ``no_route_share``.

    Raises:
        NanFrameError: when the flooded side of the row differs from its baseline (the run had a flood).
    """

    access = row["access"]
    result: dict[str, Any] = {"residents": float(row["residents"]), "demand_cells": int(row["demand_cells"])}
    services: dict[str, Any] = {}
    for service in (HOSPITAL, MAIN_ROAD_ENTRY):
        detail = access[service]
        for limit, figures in detail["thresholds_minutes"].items():
            if (figures["flooded_access_residents"] != figures["baseline_access_residents"]
                    or figures["newly_lost_residents"] != 0 or figures["newly_gained_residents"] != 0):
                raise NanFrameError(f"the row of service {service} at {limit} minutes is not a baseline-only row")
        if detail["residents_with_a_route_in_the_flooded_run"] != detail["residents_with_a_baseline_route"]:
            raise NanFrameError(f"the row of service {service} is not a baseline-only row")
        services[service] = {
            "residents_with_a_baseline_route": float(detail["residents_with_a_baseline_route"]),
            "baseline_access_residents_by_threshold_minutes": {
                limit: float(figures["baseline_access_residents"])
                for limit, figures in sorted(detail["thresholds_minutes"].items(), key=lambda item: int(item[0]))
            },
        }
    hospital = access[HOSPITAL]
    connected = float(hospital["residents_connected_to_the_graph"])
    with_route = float(hospital["residents_with_a_baseline_route"])
    without = max(0.0, connected - with_route)
    routes = row["routes"]
    result.update({
        "residents_connected_to_the_graph": connected,
        "residents_not_connected_to_the_graph": float(hospital["residents_not_connected_to_the_graph"]),
        "hospital_within_30_minutes_residents":
            float(access[HOSPITAL]["thresholds_minutes"][str(hospital_gap_minutes)]["baseline_access_residents"]),
        "main_road_within_15_minutes_residents":
            float(access[MAIN_ROAD_ENTRY]["thresholds_minutes"][str(main_road_gap_minutes)]["baseline_access_residents"]),
        "connected_residents_without_a_hospital_route": without,
        "baseline_vehicle_no_route_share": no_route_share(connected, without),
        "residents_with_a_route_to_a_hospital_or_main_road": float(routes["residents_with_baseline_route"]),
        "connected_residents_without_any_route": float(routes["connected_residents_without_a_baseline_route"]),
        "services": services,
    })
    return result


def baseline_table(table: Mapping[str, Any], *, hospital_gap_minutes: int, main_road_gap_minutes: int,
                   no_route_share: Callable[[float, float], float]) -> dict[str, Any]:
    """Apply :func:`baseline_row` to every unit row and to the whole frame of a ``unit_rows`` result."""

    def one(row: Mapping[str, Any]) -> dict[str, Any]:
        return baseline_row(row, hospital_gap_minutes=hospital_gap_minutes, main_road_gap_minutes=main_road_gap_minutes,
                            no_route_share=no_route_share)

    return {
        "units": [{"unit_id": str(row["unit_id"]), **one(row)} for row in table["units"]],
        "whole_frame": one(table["whole_frame"]),
        "cells_in_no_unit": dict(table["cells_in_no_unit"]),
    }


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def check_record(payload: Mapping[str, Any]) -> None:
    """Refuse a record without the fields every output of the project carries.

    Every record carries ``generated_at_utc``, ``source_timestamp``, ``confidence_class``, ``assumptions`` (a
    non-empty list of sentences), ``official_warning: false`` and ``operational_status: "non_operational"``.

    Raises:
        NanFrameError: naming the first field that is missing or wrong.
    """

    for key in RECORD_KEYS:
        if key not in payload:
            raise NanFrameError(f"the record has no {key}")
    if not str(payload["generated_at_utc"]).endswith("Z") or not str(payload["source_timestamp"]).strip():
        raise NanFrameError("the record needs a UTC generation time and a source timestamp")
    if payload["official_warning"] is not False or payload["operational_status"] != "non_operational":
        raise NanFrameError("a record of the case is never an official warning and never operational")
    assumptions = payload["assumptions"]
    if not isinstance(assumptions, list) or not assumptions or not all(isinstance(item, str) and item.strip()
                                                                       for item in assumptions):
        raise NanFrameError("assumptions must be a non-empty list of sentences")
    if not str(payload["confidence_class"]).strip():
        raise NanFrameError("the record needs a confidence class")


def encode_record(payload: Mapping[str, Any], *, indent: int | None = 2) -> bytes:
    """Serialise a record after :func:`check_record`: ASCII with escapes, LF, one final newline."""

    check_record(payload)
    separators = None if indent is not None else (",", ":")
    text = json.dumps(payload, indent=indent, ensure_ascii=True, allow_nan=False, separators=separators)
    return (text + "\n").encode("ascii")
