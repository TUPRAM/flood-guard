"""The score chain of the Nan case: the pure parts (protocol ``nan_case_protocol_v1``, decision log R51).

The Nan case feeds a flood raster on the frame's 20 m grid through the unchanged planning chain of protocols v1a
and v1b (``floodguard.planning_assessment``, ``floodguard.uncertainty_ensemble``) to a score and a class per tambon.
The raster codes are fixed: 1 flagged, 0 not flagged (by radar or by terrain), 255 no answer. This module holds
what the Nan protocol adds or replaces, and nothing else:

* **Rasters to extents.** A mask of cells becomes the union of their footprints in EPSG:32647
  (:func:`cell_footprints`), as task E1 polygonises a raster candidate (open point E1-OP5). In the binding chain a
  no-answer cell counts as not flagged; the sensitivity run counts it as flagged (:func:`treatment_mask`). The
  closure extent of an own (tier T2) raster drops polygons under the pixel count of protocol v1b
  (``closure_rule_v1.parameters.raster_minimum_polygon_px``) through ``floodguard.flood_inputs.drop_small_polygons``.
* **No answer, per tambon** (:func:`no_answer_by_unit`): the no-answer share of the land outside permanent water,
  the residents in no-answer cells and the vehicle edges that cross them. Report-only figures.
* **Confidence of case N1** (:func:`nan_derivation`). Confidence rule v1 applies as written, except that the T2
  skill condition behind C1 is replaced by the binding rule of the Nan protocol: the case-level test outcome (test
  1 and the dry control, an input), the tambon's no-answer share (at most 0.20), the share of its land with an
  answer (at least 0.80) and the days from the pass to the case reference date (at most 3). The record keeps the
  shape of ``floodguard.confidence.t2_skill_condition``; its four slots hold those four measurements. C2 to C8 are
  derived by ``floodguard.confidence.derive_confidence`` unchanged. Case N2 (the reference map as provided, tier
  T3) gets rule v1 as written.
* **Checks of a result file** (:func:`nan_overlay_problems`): the overlay parser bound to the protocols in force,
  with exactly two kinds of refusal accepted, each because the Nan protocol says so.
* **The headline over the cells run** (:func:`headline_over_the_cells_run`): guardrail GR8 over the 180 cells of
  the Nan ensemble, or over 90 when the population axis is dropped.

Every figure the case produces is agreement with a reference layer, not accuracy. A result is planning guidance,
not an official warning, and class E never means safe. The functions read no file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import math
from pathlib import Path
import re
from typing import Any

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

from floodguard import closure_rules, flood_inputs
from floodguard.confidence import (
    CONDITION_IDS,
    FAIL,
    OWN_CANDIDATE_TIER,
    PASS,
    REASON_INSUFFICIENT_DENOMINATOR,
    REASON_LOW_CONFIDENCE,
    SKILL_DECLARED_UNABLE,
    SKILL_EVALUATED,
    ConfidenceInputs,
    ConfidenceRule,
    derive_confidence,
    recency_days,
)
from floodguard.planning_overlay import (
    CASE_NOT_PROTOCOL_CASE,
    CONFIDENCE_NOT_RULE_RECORD,
    GUARDRAIL_GR8,
    PORTFOLIO_KIND,
    ProtocolBinding,
    overlay_problems,
)

CHAIN_VERSION = "nan_case_chain_v1"
NAN_PROTOCOL_SCHEMA = "floodguard.nan_case_protocol.v1"
FLAGGED, NOT_FLAGGED, NO_ANSWER = 1, 0, 255
"""The codes of a flood raster of the case (task statement of the score chain, Nan protocol ``grid``)."""
RASTER_CODES: frozenset[int] = frozenset({FLAGGED, NOT_FLAGGED, NO_ANSWER})
BINDING_TREATMENT = "no_answer_counted_as_not_flagged"
SENSITIVITY_TREATMENT = "no_answer_counted_as_flagged"
TREATMENTS: tuple[str, ...] = (BINDING_TREATMENT, SENSITIVITY_TREATMENT)
GRID_EPSG = 32647
GRID_CELL_M = 20.0
CLOSURE_POLYGON_CONNECTIVITY = 8
"""Which cells form one polygon when the closure extent of a tier T2 raster drops small polygons. Protocol v1b
does not say (open point E1-OP6); the M1-z method cleans its flags with 8-connected groups, and the chain reads the
closure rule the same way."""
TILE_CELLS = 64
"""Side of the tiles a large mask is polygonised in for the report-only figures (cells)."""
NAN_TEST_IOU_MIN = 0.40
NAN_NO_ANSWER_SHARE_MAX = 0.20
NAN_ANSWERED_SHARE_MIN = 0.80
NAN_PASS_WINDOW_DAYS = 3.0
"""The four thresholds of the Nan binding rule (``binding_rule`` and ``tests.test_1_district_water.pass_if``). They
are the four thresholds of the T2 skill bar of protocol v1a; :func:`check_rule_thresholds` refuses a rule that
states others."""
FLOOD_AXIS_KEYS: Mapping[str, str] = {
    "lower": flood_inputs.MINUS,
    "central": flood_inputs.AS_PROVIDED,
    "upper": flood_inputs.PLUS,
}
"""The three flood rasters of the Nan ensemble and the level of the v1b grid each takes the place of."""
SEALED_FOLDER_NAMES: tuple[str, ...] = ("jaxa_sealed",)
SEALED_NAME_PATTERNS: tuple[str, ...] = (
    r"IMG_T2V_20250731035100",
    r"water_v2_chip_00[13]_2m",
    r"chip_00[13]_2m\.npz",
    r"held_chip_00\d*_reference",
)
"""What the score chain never opens (the firewall of the Nan case): the sealed folder of the JAXA files and the
THEOS-2 scene of 31 July 2025 with everything derived from its two Nan chips."""

NAN_RULE_SENTENCE = (
    "Nan case binding rule (nan_case_protocol_v1, binding_rule) in the place of the T2 skill condition behind C1: "
    "t2_skill_condition holds the case-level test outcome (test 1 and the dry control, an input) in the status, the "
    "binding test 1 figure in geoid_held_out_test_iou, the tambon's no-answer share of its land outside permanent "
    "water in abstention_fraction, the share of that land with an answer (radar or terrain) in unit_valid_coverage "
    "and the days from the pass to the case reference date in recency_days, against the same four thresholds. C2 to "
    "C8 are confidence rule v1 as written."
)


class NanChainError(ValueError):
    """Raised when an input of the score chain breaks its contract or the rules of the Nan protocol."""


# ---------------------------------------------------------------------------
# The grid and the flood raster
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RasterGrid:
    """A north-up grid in EPSG:32647: ``west`` and ``north`` of its outer edge, its rows, columns and cell size."""

    west: float
    north: float
    rows: int
    cols: int
    cell_m: float = GRID_CELL_M
    epsg: int = GRID_EPSG

    @property
    def transform(self) -> Any:
        """The affine transform of the grid (rasterio)."""

        from rasterio.transform import from_origin

        return from_origin(self.west, self.north, self.cell_m, self.cell_m)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east and north of the grid in metres."""

        return (self.west, self.north - self.rows * self.cell_m, self.west + self.cols * self.cell_m, self.north)

    def as_record(self) -> dict[str, Any]:
        """The grid as plain JSON values."""

        return {"west": self.west, "north": self.north, "rows": self.rows, "cols": self.cols, "cell_m": self.cell_m,
                "epsg": self.epsg}


def grid_from_record(record: Mapping[str, Any]) -> RasterGrid:
    """Build a grid from ``west``, ``north``, ``rows`` and ``cols`` (``outputs/nan_case/areas_v1.json`` writes them).

    Raises:
        NanChainError: for a grid without cells or with values that are not numbers.
    """

    try:
        grid = RasterGrid(float(record["west"]), float(record["north"]), int(record["rows"]), int(record["cols"]),
                          float(record.get("cell_m", GRID_CELL_M)), int(record.get("epsg", GRID_EPSG)))
    except (KeyError, TypeError, ValueError) as error:
        raise NanChainError(f"a grid is west, north, rows and cols: {error!r}") from error
    if grid.rows <= 0 or grid.cols <= 0 or not grid.cell_m > 0 or grid.epsg != GRID_EPSG:
        raise NanChainError(f"a grid of the case has cells, a positive cell size and EPSG:{GRID_EPSG}")
    return grid


def check_flood_values(values: np.ndarray, grid: RasterGrid | None = None) -> dict[str, int]:
    """Check that a flood raster holds only the three codes of the case, on the grid's shape; count each.

    Raises:
        NanChainError: for an array that is not two-dimensional, has another shape than the grid, or holds a value
            other than 1, 0 and 255.
    """

    array = np.asarray(values)
    if array.ndim != 2:
        raise NanChainError("a flood raster has one band of rows and columns")
    if grid is not None and array.shape != (grid.rows, grid.cols):
        raise NanChainError(f"the flood raster has {array.shape[0]} rows and {array.shape[1]} columns; the grid has "
                            f"{grid.rows} and {grid.cols}")
    found = set(np.unique(array).tolist())
    if not found <= RASTER_CODES:
        raise NanChainError(f"a flood raster holds 1 (flagged), 0 (not flagged) and 255 (no answer) only, not {sorted(found - RASTER_CODES)}")
    return {"cells": int(array.size), "flagged": int((array == FLAGGED).sum()),
            "not_flagged": int((array == NOT_FLAGGED).sum()), "no_answer": int((array == NO_ANSWER).sum())}


def treatment_mask(values: np.ndarray, treatment: str) -> np.ndarray:
    """Return the cells a treatment counts as flagged.

    ``no_answer_counted_as_not_flagged`` is the binding chain (as test 1 counts a no-answer cell);
    ``no_answer_counted_as_flagged`` is the sensitivity run of the central cell.

    Raises:
        NanChainError: for another treatment.
    """

    array = np.asarray(values)
    if treatment == BINDING_TREATMENT:
        return array == FLAGGED
    if treatment == SENSITIVITY_TREATMENT:
        return (array == FLAGGED) | (array == NO_ANSWER)
    raise NanChainError(f"the treatment of a no-answer cell is one of {TREATMENTS}")


def cell_footprints(mask: np.ndarray, transform: Any) -> MultiPolygon:
    """Return the union of the footprints of the true cells of a mask, in the coordinates of the transform.

    The cells are traced as 4-connected regions (``rasterio.features.shapes``), as task E1 polygonises a raster
    (``floodguard.flood_inputs``), and joined into one valid multipolygon.
    """

    pieces = _footprint_list(np.asarray(mask, dtype=bool), transform)
    if not pieces:
        return MultiPolygon()
    return flood_inputs.as_multipolygon(shapely.union_all(np.array(pieces, dtype=object)))


def _footprint_list(mask: np.ndarray, transform: Any) -> list[BaseGeometry]:
    from rasterio.features import shapes

    if not mask.any():
        return []
    return [shape(geometry) for geometry, _value in
            shapes(mask.astype("uint8"), mask=mask, transform=transform, connectivity=4)]


def tiled_footprints(mask: np.ndarray, transform: Any, *, tile_cells: int = TILE_CELLS) -> list[BaseGeometry]:
    """Return the footprints of the true cells of a mask, traced tile by tile, so that no piece is large.

    The pieces do not overlap; together they cover exactly the cells of the mask. They serve the report-only
    figures over wide masks (the no-answer cells), where one union would be slow to measure.

    Raises:
        NanChainError: for a tile size under one cell.
    """

    if tile_cells < 1:
        raise NanChainError("a tile holds at least one cell")
    from rasterio.windows import Window
    from rasterio.windows import transform as window_transform

    array = np.asarray(mask, dtype=bool)
    pieces: list[BaseGeometry] = []
    for row in range(0, array.shape[0], tile_cells):
        for col in range(0, array.shape[1], tile_cells):
            window = array[row:row + tile_cells, col:col + tile_cells]
            if window.any():
                where = Window(col, row, window.shape[1], window.shape[0])
                pieces.extend(_footprint_list(window, window_transform(where, transform)))
    return pieces


def closure_extent(mask: np.ndarray, transform: Any, *, tier: str, minimum_px: int,
                   connectivity: int = CLOSURE_POLYGON_CONNECTIVITY) -> tuple[MultiPolygon, dict[str, Any]]:
    """Return the extent the closure rule measures roads against, with what was dropped.

    Protocol v1b ``closure_rule_v1.parameters``: "For T2 rasters, polygons under 5 pixels are dropped before
    intersection" (``floodguard.flood_inputs.drop_small_polygons``). A raster of another tier is used whole.
    """

    if tier == OWN_CANDIDATE_TIER:
        extent, counts = flood_inputs.drop_small_polygons(np.asarray(mask, dtype=bool), transform, minimum_px=minimum_px,
                                                          connectivity=connectivity)
        return extent, {"rule": "polygons under the minimum dropped (tier T2 raster)", **counts}
    return cell_footprints(mask, transform), {"rule": f"no polygon dropped: the rule names T2 rasters, and this input is tier {tier}",
                                              "minimum_px": minimum_px}


# ---------------------------------------------------------------------------
# Report-only figures: the no-answer cells of each tambon
# ---------------------------------------------------------------------------


def edge_lines_in_metres(edges: Sequence[Mapping[str, Any]], node_coordinates: Mapping[str, Sequence[float]]
                         ) -> tuple[list[str], np.ndarray]:
    """Return the edge identifiers (sorted) and the straight node-to-node segments in EPSG:32647.

    The segment is the one closure rule v1 measures (protocol v1b ``closure_rule_v1.geometry``).

    Raises:
        NanChainError: for a repeated edge identifier or an unknown node.
    """

    from pyproj import Transformer

    ordered = sorted(edges, key=lambda row: row["edge_id"])
    identifiers = [str(row["edge_id"]) for row in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise NanChainError("edge identifiers must be unique")
    if not ordered:
        return [], np.array([], dtype=object)
    try:
        start = np.array([node_coordinates[row["from_node"]][:2] for row in ordered], dtype="float64")
        end = np.array([node_coordinates[row["to_node"]][:2] for row in ordered], dtype="float64")
    except KeyError as error:
        raise NanChainError(f"an edge names an unknown node: {error.args[0]}") from error
    projection = Transformer.from_crs(4326, closure_rules.ANALYSIS_EPSG, always_xy=True).transform
    start_x, start_y = projection(start[:, 0], start[:, 1])
    end_x, end_y = projection(end[:, 0], end[:, 1])
    lines = shapely.linestrings(np.stack([np.column_stack([start_x, start_y]), np.column_stack([end_x, end_y])], axis=1))
    return identifiers, lines


def edge_lengths_inside_pieces(identifiers: Sequence[str], lines: np.ndarray, pieces: Sequence[BaseGeometry]
                               ) -> list[dict[str, Any]]:
    """Measure how much of each edge lies inside a set of non-overlapping pieces, as closure rule v1 measures it.

    The length inside is summed over the pieces an edge crosses; an edge counts when that sum is above 1e-6 m.
    The rows have the shape of ``floodguard.closure_rules.edge_intersections``, sorted by edge identifier.
    """

    if not len(pieces) or not len(lines):
        return []
    tree = shapely.STRtree(np.array(list(pieces), dtype=object))
    line_index, piece_index = tree.query(lines, predicate="intersects")
    if not len(line_index):
        return []
    lengths = shapely.length(shapely.intersection(lines[line_index], tree.geometries[piece_index]))
    totals = np.bincount(line_index, weights=lengths, minlength=len(lines))
    rows = []
    for index in np.nonzero(totals > closure_rules.MIN_INTERSECTION_M)[0]:
        length = float(totals[index])
        rows.append({"edge_id": identifiers[int(index)], "intersection_length_m": length,
                     "intersection_fraction": min(1.0, length / float(lines[int(index)].length))})
    return rows


def edges_crossing_by_unit(identifiers: Sequence[str], lines: np.ndarray, pieces: Sequence[BaseGeometry],
                           units: Mapping[str, BaseGeometry]) -> dict[str, dict[str, Any]]:
    """Count, for each unit, the edges with a stretch inside the pieces, and the length of those stretches.

    A stretch counts for the unit that holds its midpoint (a point on its boundary counts for one unit only), so an
    edge whose stretches lie in two units counts in both. Report-only; no closure follows from it.
    """

    found = {unit_id: {"edges": 0, "length_inside_m": 0.0} for unit_id in units}
    if not len(pieces) or not len(lines):
        return found
    tree = shapely.STRtree(np.array(list(pieces), dtype=object))
    line_index, piece_index = tree.query(lines, predicate="intersects")
    if not len(line_index):
        return found
    stretches = shapely.intersection(lines[line_index], tree.geometries[piece_index])
    lengths = shapely.length(stretches)
    keep = lengths > closure_rules.MIN_INTERSECTION_M
    stretches, lengths, line_index = stretches[keep], lengths[keep], line_index[keep]
    if not len(stretches):
        return found
    lineal = np.isin(shapely.get_type_id(stretches), (1, 5))
    midpoints = shapely.point_on_surface(stretches)
    if lineal.any():
        midpoints[lineal] = shapely.line_interpolate_point(stretches[lineal], 0.5, normalized=True)
    names = list(units)
    unit_tree = shapely.STRtree(np.array([units[name] for name in names], dtype=object))
    point_index, unit_index = unit_tree.query(midpoints, predicate="intersects")
    holder: dict[int, int] = {}
    for point, unit in zip(point_index.tolist(), unit_index.tolist()):
        holder[point] = min(unit, holder.get(point, unit))  # a point on a shared boundary counts once, for the first unit
    edges_by_unit: dict[str, set[int]] = {name: set() for name in names}
    for point, unit in sorted(holder.items()):
        name = names[unit]
        edges_by_unit[name].add(int(line_index[point]))
        found[name]["length_inside_m"] += float(lengths[point])
    for name in names:
        found[name]["edges"] = len(edges_by_unit[name])
    return found


def grid_values_at(values: np.ndarray, grid: RasterGrid, x: Sequence[float], y: Sequence[float]) -> np.ndarray:
    """Return the raster value under each point (EPSG:32647); -1 for a point outside the grid."""

    xs, ys = np.asarray(x, dtype="float64"), np.asarray(y, dtype="float64")
    cols = np.floor((xs - grid.west) / grid.cell_m).astype("int64")
    rows = np.floor((grid.north - ys) / grid.cell_m).astype("int64")
    inside = (rows >= 0) & (rows < grid.rows) & (cols >= 0) & (cols < grid.cols)
    result = np.full(xs.shape, -1, dtype="int64")
    result[inside] = np.asarray(values)[rows[inside], cols[inside]]
    return result


def no_answer_by_unit(
    *,
    units: Mapping[str, BaseGeometry],
    water: BaseGeometry,
    no_answer_pieces: Sequence[BaseGeometry],
    cells: Sequence[Mapping[str, Any]],
    cell_values: Sequence[int],
    edges_crossing: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """The report-only figures of the no-answer cells of each tambon.

    Args:
        units: Unit polygons in EPSG:32647.
        water: The permanent water in EPSG:32647 (ESA WorldCover 2021 class 80).
        no_answer_pieces: The footprints of the no-answer cells (:func:`tiled_footprints`).
        cells: The demand cells (``unit_id``, ``residents``).
        cell_values: The raster value under the centre of each cell, in the order of ``cells``.
        edges_crossing: :func:`edges_crossing_by_unit` over the no-answer pieces.

    Returns:
        ``unit_id ->`` the land outside permanent water, its part in no-answer cells and the share, the share with
        an answer, the residents and those in no-answer cells, and the vehicle edges crossing no-answer cells.
    """

    tree = shapely.STRtree(np.array(list(no_answer_pieces), dtype=object)) if len(no_answer_pieces) else None
    residents: dict[str, list[float]] = {unit_id: [] for unit_id in units}
    unanswered: dict[str, list[float]] = {unit_id: [] for unit_id in units}
    for cell, value in zip(cells, cell_values):
        unit_id = cell.get("unit_id")
        if unit_id in residents:
            residents[unit_id].append(float(cell["residents"]))
            if int(value) == NO_ANSWER:
                unanswered[unit_id].append(float(cell["residents"]))
    result: dict[str, dict[str, Any]] = {}
    for unit_id, unit in units.items():
        land = unit if water.is_empty else shapely.difference(unit, water)
        land_area = float(flood_inputs.as_multipolygon(land).area)
        no_answer_area = 0.0
        if tree is not None and land_area > 0:
            shapely.prepare(land)
            hits = tree.query(land, predicate="intersects")
            if len(hits):
                no_answer_area = math.fsum(shapely.area(shapely.intersection(land, tree.geometries[hits])).tolist())
        share = None if land_area <= 0 else min(1.0, no_answer_area / land_area)
        crossing = edges_crossing.get(unit_id, {"edges": 0, "length_inside_m": 0.0})
        result[unit_id] = {
            "land_outside_permanent_water_m2": land_area,
            "no_answer_land_m2": no_answer_area,
            "no_answer_share_of_land": share,
            "answered_share_of_land": None if share is None else 1.0 - share,
            "residents": math.fsum(residents[unit_id]),
            "residents_in_no_answer_cells": math.fsum(unanswered[unit_id]),
            "vehicle_edges_crossing_no_answer_cells": int(crossing["edges"]),
            "length_of_those_edges_inside_no_answer_cells_m": float(crossing["length_inside_m"]),
        }
    return result


# ---------------------------------------------------------------------------
# Confidence: the Nan binding rule in the place of the T2 skill condition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseOutcome:
    """The case-level outcome of the tests the Nan binding rule reads, as the test stage reports it.

    Attributes:
        test_1_passed: Test 1 met its pass rule (IoU with no answer counted as not flagged >= 0.40, no-answer share
            <= 0.20); ``None`` when it has not been read.
        dry_control_passed: Our map flags at most 0.05 of the answered cells of the dry chip; ``None`` when not read.
        test_1_iou: The binding test 1 figure (agreement with the reference, not accuracy); ``None`` when not read.
        reference: The reference of test 1, in words (the JAXA map, or the GFM map under the fallback).
        case_reference_date: 2025-07-28, or 2025-07-31 under the fallback.
        fallback: Whether test 1 used its fallback (a same-pass CEMS map, not independent).
    """

    test_1_passed: bool | None
    dry_control_passed: bool | None
    test_1_iou: float | None
    reference: str
    case_reference_date: date
    fallback: bool = False

    @property
    def passed(self) -> bool:
        """Test 1 and the dry control both passed."""

        return self.test_1_passed is True and self.dry_control_passed is True

    def as_record(self) -> dict[str, Any]:
        """The outcome as plain JSON values."""

        return {"test_1_passed": self.test_1_passed, "dry_control_passed": self.dry_control_passed,
                "test_1_iou_no_answer_counted_as_not_flagged": self.test_1_iou, "reference": self.reference,
                "case_reference_date": self.case_reference_date.isoformat(), "fallback_used": self.fallback,
                "case_level_test_outcome_passed": self.passed,
                "wording": f"agreement with {self.reference}, not accuracy"}


def check_outcome(outcome: CaseOutcome) -> CaseOutcome:
    """Refuse an outcome whose parts do not fit together.

    Raises:
        NanChainError: when test 1 is said to pass while its binding figure is missing or under 0.40, a figure lies
            outside 0 to 1, or the reference date is not one the Nan protocol names.
    """

    if outcome.test_1_iou is not None and not 0.0 <= float(outcome.test_1_iou) <= 1.0:
        raise NanChainError("the test 1 figure is an IoU between 0 and 1")
    if outcome.test_1_passed is True and (outcome.test_1_iou is None or float(outcome.test_1_iou) < NAN_TEST_IOU_MIN):
        raise NanChainError(f"test 1 passes only with an IoU of at least {NAN_TEST_IOU_MIN:g}; the outcome says it passed")
    if not outcome.reference.strip():
        raise NanChainError("the outcome names the reference of test 1")
    expected = date(2025, 7, 31) if outcome.fallback else date(2025, 7, 28)
    if outcome.case_reference_date != expected:
        raise NanChainError(f"the case reference date is {expected.isoformat()} "
                            f"({'under the fallback' if outcome.fallback else 'the JAXA date'})")
    return outcome


def check_rule_thresholds(rule: ConfidenceRule) -> None:
    """Refuse a confidence rule whose skill-bar thresholds are not the four thresholds of the Nan binding rule.

    The Nan rule replaces the measurements of the T2 skill condition and keeps its four thresholds (0.40, 0.20,
    0.80 and 3 days), so the record keeps the shape the overlay schema fixes.

    Raises:
        NanChainError: when a threshold differs.
    """

    stated = (rule.skill_geoid_held_out_test_iou_min, rule.skill_abstention_fraction_max, rule.skill_unit_coverage_min,
              rule.skill_recency_window_days)
    if stated != (NAN_TEST_IOU_MIN, NAN_NO_ANSWER_SHARE_MAX, NAN_ANSWERED_SHARE_MIN, NAN_PASS_WINDOW_DAYS):
        raise NanChainError(f"the T2 skill bar of protocol v1a states {stated}; the Nan binding rule uses "
                            f"{(NAN_TEST_IOU_MIN, NAN_NO_ANSWER_SHARE_MAX, NAN_ANSWERED_SHARE_MIN, NAN_PASS_WINDOW_DAYS)}")


def _met(passes: bool) -> str:
    return PASS if passes else FAIL


def nan_skill_record(rule: ConfidenceRule, *, flood_input: str, outcome: CaseOutcome, no_answer_share: float | None,
                     answered_share: float | None, acquisition_date: date | None, case_reference_date: date | None
                     ) -> dict[str, Any]:
    """The record of the Nan binding rule, in the shape of ``floodguard.confidence.t2_skill_condition``.

    The status is ``evaluated`` when the case-level test outcome passed (test 1 and the dry control) and
    ``declared_unable_to_meet`` otherwise: then the map does not pass whatever the numbers of the tambon are.
    """

    check_rule_thresholds(rule)
    days = recency_days(acquisition_date, case_reference_date)
    iou = outcome.test_1_iou
    conditions = {
        "geoid_held_out_test_iou_min": _met(iou is not None and iou >= rule.skill_geoid_held_out_test_iou_min),
        "mae_sai_abstention_fraction_max": _met(no_answer_share is not None and no_answer_share <= rule.skill_abstention_fraction_max),
        "mae_sai_unit_coverage_min": _met(answered_share is not None and answered_share >= rule.skill_unit_coverage_min),
        "recency_window_days": _met(days is not None and days <= rule.skill_recency_window_days),
    }
    status = SKILL_EVALUATED if outcome.passed else SKILL_DECLARED_UNABLE
    failed = [name for name, value in conditions.items() if value == FAIL]
    wording = f"agreement with {outcome.reference}, not accuracy"
    if outcome.fallback:
        wording += " (a same-pass CEMS map, not independent)"
    return {
        "flood_input": flood_input,
        "status": status,
        "passes": status == SKILL_EVALUATED and not failed,
        "conditions": conditions,
        "failed_conditions": failed,
        "measurements": {
            "geoid_held_out_test_iou": None if iou is None else float(iou),
            "abstention_fraction": no_answer_share,
            "unit_valid_coverage": answered_share,
            "recency_days": days,
        },
        "thresholds": {
            "geoid_held_out_test_iou_min": rule.skill_geoid_held_out_test_iou_min,
            "mae_sai_abstention_fraction_max": rule.skill_abstention_fraction_max,
            "mae_sai_unit_coverage_min": rule.skill_unit_coverage_min,
            "recency_window_days": rule.skill_recency_window_days,
        },
        "metric_wording": wording,
        "protocol_v1a_sha256": rule.protocol_sha256,
    }


def nan_derivation(outcome: CaseOutcome) -> Any:
    """Return the confidence derivation of the Nan case: rule v1, with the binding rule in the place of C1's skill bar.

    For a tier T2 row (case N1, our own map) the record of ``derive_confidence`` is kept, its skill record is
    replaced by :func:`nan_skill_record` and C1 follows it; the class, the failed conditions and the reason code
    are then those of rule v1 over the eight conditions (guardrail GR1 keeps ``insufficient_denominator``). Any
    other row (case N2, tier T3) gets ``derive_confidence`` unchanged. The function has the arguments of
    ``derive_confidence`` (``floodguard.planning_assessment.ConfidenceDerivation``).
    """

    check_outcome(outcome)

    def derive(inputs: ConfidenceInputs, rule: ConfidenceRule) -> dict[str, Any]:
        record = derive_confidence(inputs, rule)
        if inputs.tier != OWN_CANDIDATE_TIER:
            return record
        if inputs.t2_geoid_held_out_test_iou != outcome.test_1_iou:
            raise NanChainError("a row of case N1 carries the case-level test 1 figure of the outcome it is judged by")
        skill = nan_skill_record(rule, flood_input=inputs.flood_input, outcome=outcome,
                                 no_answer_share=inputs.t2_abstention_fraction, answered_share=inputs.unit_valid_coverage,
                                 acquisition_date=inputs.acquisition_date, case_reference_date=inputs.case_reference_date)
        basis = dict(record["basis"])
        basis["C1_tier"] = _met(bool(skill["passes"]))
        failed = [condition for condition in CONDITION_IDS if basis[condition] == FAIL]
        reason = REASON_LOW_CONFIDENCE if failed else None
        if record["guardrail_gr1"]["applies"]:
            reason = REASON_INSUFFICIENT_DENOMINATOR
        return {**record, "confidence_class": "low" if failed else "medium", "basis": basis, "failed_conditions": failed,
                "reason_code": reason, "t2_skill_condition": skill,
                "assumptions": [*record["assumptions"], NAN_RULE_SENTENCE]}

    return derive


def confidence_inputs_from_record(record: Mapping[str, Any]) -> ConfidenceInputs:
    """Rebuild the inputs of the confidence rule from the measurements a confidence record echoes."""

    measurements = record["measurements"]
    skill = record["t2_skill_condition"]
    acquired, reference = measurements["acquisition_date"], measurements["case_reference_date"]
    return ConfidenceInputs(
        unit_id=record["unit_id"], lane=record["lane"], tier=record["tier"], flood_input=record["flood_input"],
        scenario_base=record["scenario_base"],
        acquisition_date=None if acquired is None else date.fromisoformat(acquired),
        case_reference_date=None if reference is None else date.fromisoformat(reference),
        unit_valid_coverage=measurements["unit_valid_coverage"],
        coverage_by_construction=measurements["coverage_by_construction"],
        exposure_plus_one_pixel_0_100=measurements["exposure_plus_one_pixel_0_100"],
        exposure_minus_one_pixel_0_100=measurements["exposure_minus_one_pixel_0_100"],
        t2_abstention_fraction=measurements["t2_abstention_fraction"],
        t2_geoid_held_out_test_iou=None if skill is None else skill["measurements"]["geoid_held_out_test_iou"],
        component_status=measurements["component_status"], unit_residents=measurements["unit_residents"],
        baseline_vehicle_no_route_share=measurements["baseline_vehicle_no_route_share"],
        hospitals_reachable_at_baseline=measurements["hospitals_reachable_at_baseline"],
    )


# ---------------------------------------------------------------------------
# Checks of a result file
# ---------------------------------------------------------------------------


_ROW_CONFIDENCE = re.compile(r"^\$\.rows\[(\d+)\]\.confidence$")


def nan_overlay_problems(overlay: Mapping[str, Any], schema: Mapping[str, Any], binding: ProtocolBinding,
                         derive: Any) -> dict[str, Any]:
    """Check a result file of the Nan case with the overlay parser bound to the protocols in force.

    Two refusals of the parser follow from the Nan protocol, and only these are accepted:

    * ``case_not_protocol_case`` at ``$.case.case_id`` for a portfolio case that protocol v1a does not hold
      (the Nan cases are cases of the Nan protocol);
    * ``confidence_not_rule_record`` on a tier T2 row whose confidence record is exactly what ``derive`` gives
      from the measurements the record echoes (the binding rule in the place of the T2 skill condition).

    Every other problem refuses the file. Every tier T2 row is also derived again with ``derive``, whether or not
    the parser named it.

    Returns:
        ``verified``, the accepted problems (each with why), the refused ones, and the rows derived again.
    """

    problems = overlay_problems(overlay, schema, binding=binding)
    rows = list(overlay.get("rows") or [])
    case = overlay.get("case") or {}
    accepted: list[dict[str, str]] = []
    refused: list[dict[str, str]] = []
    rederived: dict[int, bool] = {}

    def again(index: int) -> bool:
        if index not in rederived:
            record = rows[index]["confidence"]
            try:
                rederived[index] = derive(confidence_inputs_from_record(record), binding.rule) == record
            except (ValueError, KeyError, TypeError):
                rederived[index] = False
        return rederived[index]

    for problem in problems:
        item = {"code": problem.code, "path": problem.path, "message": problem.message}
        found = _ROW_CONFIDENCE.match(problem.path)
        if (problem.code == CASE_NOT_PROTOCOL_CASE and problem.path == "$.case.case_id"
                and case.get("kind") == PORTFOLIO_KIND and case.get("case_id") not in binding.cases):
            accepted.append({**item, "why": "The case is a case of the Nan protocol (nan_case_protocol_v1), not of protocol v1a."})
        elif (problem.code == CONFIDENCE_NOT_RULE_RECORD and found is not None and int(found.group(1)) < len(rows)
              and rows[int(found.group(1))]["tier"] == OWN_CANDIDATE_TIER and again(int(found.group(1)))):
            accepted.append({**item, "why": "The Nan binding rule replaces the T2 skill condition behind C1; the record is "
                                            "exactly what that rule derives from the measurements it echoes."})
        else:
            refused.append(item)
    for index, row in enumerate(rows):
        if row.get("tier") == OWN_CANDIDATE_TIER and not again(index):
            refused.append({"code": "nan_rule_record_mismatch", "path": f"$.rows[{index}].confidence",
                            "message": "the Nan binding rule derives another record from the measurements the row echoes"})
    return {"verified": not refused, "accepted": accepted, "refused": refused,
            "tier_t2_rows_derived_again": sum(1 for row in rows if row.get("tier") == OWN_CANDIDATE_TIER),
            "parser": "floodguard.planning_overlay.overlay_problems, bound to the two protocol files in force"}


# ---------------------------------------------------------------------------
# The ensemble: the headline over the cells run
# ---------------------------------------------------------------------------


def class_under_medium(cell: Mapping[str, Any]) -> str | None:
    """The class a cell gives with confidence medium: its binding class, or its would-be class when it is low."""

    if cell.get("would_be_class") is not None:
        return str(cell["would_be_class"])
    if cell.get("action_reason_code") == REASON_LOW_CONFIDENCE:
        return None
    return None if cell.get("action_class") is None else str(cell["action_class"])


def headline_over_the_cells_run(grid: Any, unit: Mapping[str, Any], *, scope: Iterable[str], over: str) -> dict[str, Any]:
    """Apply guardrail GR8 to one unit over the cells of the Nan ensemble that were run.

    The Nan protocol takes retention over its 180 cells, or over 90 when the population axis is dropped. Every
    cell run in ``scope`` counts; a failed cell keeps no class. The record is that of
    ``floodguard.uncertainty_ensemble.headline_record`` with the cells run as the set of the rule.
    """

    from floodguard import uncertainty_ensemble as ensemble

    wanted = set(scope)
    cells = [cell for cell in unit["cells"] if cell["cell_id"] in wanted]
    reference = unit["reference_cell"]
    reference_class = None if reference is None else reference["action_class"]
    classed = [cell["action_class"] for cell in cells if cell.get("status") == "computed" and cell.get("action_class") is not None]
    kept = sum(1 for value in classed if value == reference_class) if reference_class is not None else 0
    if not cells:
        raise NanChainError("no cell of the Nan ensemble was run for this unit")
    return ensemble.headline_record(grid, reference_class=reference_class, kept=kept, with_a_class=len(classed),
                                    protocol_cells=len(cells), over=over, cells_run=len(cells))


def would_be_retention(unit: Mapping[str, Any], *, scope: Iterable[str]) -> dict[str, Any]:
    """The share of the cells run that keep the class the default cell gives with confidence medium (report-only)."""

    wanted = set(scope)
    cells = [cell for cell in unit["cells"] if cell["cell_id"] in wanted and cell.get("status") == "computed"]
    reference = unit["reference_cell"]
    target = None if reference is None else class_under_medium(reference)
    kept = sum(1 for cell in cells if target is not None and class_under_medium(cell) == target)
    return {"class_with_confidence_medium_in_the_default_cell": target, "cells": len(cells),
            "cells_keeping_it": kept, "share": None if not cells or target is None else kept / len(cells),
            "note": "Report-only: the binding class or, for a low-confidence cell, the would-be class. Never binding."}


def headline_slot(record: Mapping[str, Any]) -> dict[str, Any]:
    """The headline slot of a result row (overlay schema ``headlineStability``) from a headline record."""

    return {"guardrail": GUARDRAIL_GR8, "status": record["status"], "class_retention": record["class_retention"],
            "class_retention_min": record["class_retention_min"]}


# ---------------------------------------------------------------------------
# Test 5 helper, the sensitivity table and the firewall
# ---------------------------------------------------------------------------


def row_class(row: Mapping[str, Any]) -> str | None:
    """The class test 5 reads of a row: the binding class, or the would-be class of a low-confidence row."""

    if row.get("would_be_class") is not None:
        return str(row["would_be_class"])
    return None if row.get("action_class") is None else str(row["action_class"])


def class_agreement(rows_a: Sequence[Mapping[str, Any]], rows_b: Sequence[Mapping[str, Any]], *,
                    share_min: float = 0.70) -> dict[str, Any]:
    """Compare the class of each tambon in two cases (test 5 of the Nan protocol: at least 70% the same).

    Raises:
        NanChainError: when the two cases do not hold the same tambons.
    """

    first = {str(row["unit_id"]): row_class(row) for row in rows_a}
    second = {str(row["unit_id"]): row_class(row) for row in rows_b}
    if set(first) != set(second) or not first:
        raise NanChainError("test 5 compares the same tambons in both cases")
    same = sorted(unit for unit in first if first[unit] is not None and first[unit] == second[unit])
    share = len(same) / len(first)
    return {"tambons": len(first), "same_class": len(same), "share": share, "share_min": share_min,
            "passes": share >= share_min,
            "class_read": "binding class, or the would-be class of a low-confidence row",
            "wording": "agreement between two planning chains, not accuracy"}


def sensitivity_table(binding_rows: Sequence[Mapping[str, Any]], sensitivity_rows: Sequence[Mapping[str, Any]]
                      ) -> list[dict[str, Any]]:
    """Set the central cell with no answer counted as flagged beside the binding row, tambon by tambon.

    Raises:
        NanChainError: when the two runs do not hold the same tambons.
    """

    other = {str(row["unit_id"]): row for row in sensitivity_rows}
    if set(other) != {str(row["unit_id"]) for row in binding_rows}:
        raise NanChainError("the sensitivity run holds the tambons of the binding run")

    def values(row: Mapping[str, Any]) -> dict[str, float | None]:
        return {name: None if record is None else float(record["value_0_100"]) for name, record in row["components"].items()}

    table = []
    for row in binding_rows:
        twin = other[str(row["unit_id"])]
        table.append({
            "unit_id": row["unit_id"],
            "binding": {"components": values(row), "fpps_0_100": row["fpps_0_100"], "action_class": row["action_class"],
                        "action_reason_code": row["action_reason_code"], "would_be_class": row["would_be_class"],
                        "confidence_class": row["confidence"]["confidence_class"]},
            "no_answer_counted_as_flagged": {
                "components": values(twin), "fpps_0_100": twin["fpps_0_100"], "action_class": twin["action_class"],
                "action_reason_code": twin["action_reason_code"], "would_be_class": twin["would_be_class"],
                "confidence_class": twin["confidence"]["confidence_class"]},
            "class_same": row_class(row) == row_class(twin),
        })
    return table


def firewall_refusal(path: Path | str) -> str | None:
    """Say why the score chain may not open a path, or ``None`` when it may.

    The chain never opens the sealed folder of the JAXA files, nor the THEOS-2 scene of 31 July 2025 or anything
    derived from its two Nan chips (the firewall of the Nan case). A reference map enters case N2 only as a raster
    the test stage wrote after the test.
    """

    text = Path(path).as_posix()
    parts = [part.lower() for part in Path(path).parts]
    if any(name in parts for name in SEALED_FOLDER_NAMES):
        return f"{text} lies in the sealed folder of the JAXA files; the chain never opens it"
    for pattern in SEALED_NAME_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return f"{text} is a THEOS-2 file of 31 July 2025 or is derived from it; the chain never opens it"
    return None

