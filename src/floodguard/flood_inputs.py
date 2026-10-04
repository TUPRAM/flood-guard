"""Flood inputs of the planning overlay: one loader per input the signed protocols name (plan task E1).

Restructuring plan v2, sections 3.1 (stage P1), 3.2 and 4.1. The Mae Sai cases of protocol v1a
(``case_portfolio``) name three flood inputs, and this module has one loader for each:

* :func:`load_se1`: the accumulated layer of UNOSAT/GISTDA product 4009, the 2024 season envelope
  (case SE1, lane SCN-ENV, ``temporal_relation`` ``season_window``);
* :func:`load_o2`: the product 4009 layer of 22 October 2024, its own dated case (case O2, lane OBS, tier T3);
* :func:`load_o1`: an own radar candidate that another lane delivers as a raster with a receipt
  (case O1, lane OBS, tier T2). :data:`RADAR_RECEIPT_KEYS` is the interface that lane writes to.

Every loader does the same six things, each as the signed files state it:

1. **Rights.** :class:`floodguard.rights.RightsRegistry` must allow the use before a file is opened, and the
   source file must be the one the rights record names. The grant, with its rights level, is in the input record.
   Each layer that is read has its own grant: the flood layer and the product footprint can be at different
   levels, each written layer carries the level of the layer it comes from, and a file that holds figures of
   both is at the minimum of the two (protocol v1a, guardrail GR6).
2. **Repair.** Invalid polygon parts are repaired with ``make_valid`` and counted, for each frame as the parts
   that reach the frame.
3. **Clip.** The extent is clipped to every frame of the case: the reporting frame (the units of the case) and
   the routing context (the corridor polygon of protocol v1b).
4. **One-pixel levels.** Protocol v1b, ``ensemble_grid`` (owner choice 2): 20 m for the minus and the plus
   level and for every input, raster or vector; a vector product gets a 20 m negative or positive buffer in
   EPSG:32647. No level is labelled central (protocol v1a, ``date_rule.flood_uncertainty_axis``).
5. **Permanent water.** Protocol v1a, ``scoring_frame``: flood likelihood is the flooded share of the unit's
   non-permanent-water land, and permanent water is ESA WorldCover 2021 v200 class 80 in every case. The
   scoring frame names permanent water for that component only, so the extents themselves are not changed:
   :func:`permanent_water` gives the water of a frame, the record gives the area of each level on and off
   it, and :func:`flooded_land_areas` gives the two areas of one unit that
   ``floodguard.normalisation.flood_likelihood`` takes.
6. **Input record.** Source and SHA-256, source timestamp, lane, tier, temporal relation, footprint, rights,
   confidence and assumptions (:data:`INPUT_RECORD_SCHEMA`).

The product 4009 layers are used as provided. They are unvalidated preliminary agency extents
(Field_Validation=0), and FloodGuard did not validate them. Nothing here is an observation of a road closure,
a warning of any kind or an operational product, and nothing here computes an FPPS, a component value, an A-E
class or an ensemble.

All geometry work is in EPSG:32647, with every vertex projected as it is (the convention of
``floodguard.closure_rules``). Extents are snapped to a 1 mm grid so that the bytes written are the geometry
measured. :func:`encode_layer` writes one extent with its rights and change notice, and
:func:`read_written_input` reads a written input back only as the bytes its record names. What the protocols
leave open is listed in :data:`OPEN_POINTS`; none of it is decided here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any
import warnings

import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import MultiPolygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from floodguard import normalisation, rights, season_envelope

FLOOD_INPUTS_VERSION = "flood_inputs_v1"
INPUT_RECORD_SCHEMA = "floodguard.flood_input.v2"
LAYER_SCHEMA = "floodguard.flood_input_layer.v1"
RADAR_RECEIPT_SCHEMA = "floodguard.radar_candidate_receipt.v1"
INPUT_RECORD_NAME = "input_record.json"
"""The file that holds the input record beside the written layers of one input."""

ANALYSIS_EPSG = 32647
ANALYSIS_CRS = f"EPSG:{ANALYSIS_EPSG}"
WGS84_CRS = "EPSG:4326"
ANALYSIS_CRS_URN = f"urn:ogc:def:crs:EPSG::{ANALYSIS_EPSG}"
COORDINATE_GRID_M = 0.001
REPAIR_METHOD = "make_valid"
BUFFER_QUAD_SEGS = 16
"""Segments per quarter circle of the one-pixel buffer (the GEOS default of shapely; round joins)."""

MINUS, AS_PROVIDED, PLUS = "minus", "as_provided", "plus"
LEVELS: tuple[str, ...] = (MINUS, AS_PROVIDED, PLUS)
"""The three states of the flood-input axis. None of them is a central estimate."""

REPORTING_FRAME, ROUTING_CONTEXT = "reporting_frame", "routing_context"
EVENT_ALIGNED, DATED_OTHER, SEASON_WINDOW = "event_aligned", "dated_other", "season_window"
THRESHOLD_LEVELS, ONE_PIXEL_LEVELS = "threshold", "one_pixel"

GEODATABASE_4009 = "FL20240912THA.gdb"
ANALYSIS_EXTENT_LAYER_4009 = "CHIANGRAI_20240801_20241022_AnalysisExtent"
"""The analysis extent of the Chiang Rai layers of product 4009: the product footprint of both flood layers."""

RADAR_FLOOD, RADAR_NOT_FLOOD = 1, 0
RADAR_RECEIPT_KEYS: tuple[str, ...] = (
    "schema_version", "case_id", "candidate_id", "rights_input_id", "acquisition_time_utc", "acquisition_date",
    "level_kind", "level_parameter", "rasters", "encoding", "protocol_sha256", "inputs", "source_timestamp",
    "generated_at_utc", "confidence_class", "confidence_basis", "assumptions", "official_warning", "operational_status",
)
"""What the receipt of an own radar candidate must hold (the interface of :func:`load_o1`).

``rasters`` maps a level to ``{"path", "sha256"}``, the path relative to the receipt: ``as_provided`` always,
``minus`` and ``plus`` as well when ``level_kind`` is ``threshold`` (the lane that made the candidate ran its
three thresholds). ``encoding`` is ``{"flood": 1, "not_flood": 0, "no_answer": <the raster's nodata value>}``.
Each raster is one band of square cells in EPSG:32647. ``acquisition_date`` is the calendar date of the
acquisition as protocol v1a writes it.

``rights_input_id`` is the key of the candidate's source data in ``floodguard.rights.REGISTERED_RECORDS``. The
receipt chooses among the records of Sentinel-1 data and nothing else: protocol v1a gives case O1 the input
acquisition "Sentinel-1, 16 Sep 2024 06:16 ICT", so :func:`load_o1` refuses a key whose registry entry is a
record of any other source, whatever the receipt says.

``level_kind`` must be the kind protocol v1b states for the candidate (``ensemble_grid``,
``t2_levels_by_input``): ``threshold`` for M1-v2, M1-literal and the A6-prime classifier, ``one_pixel`` for the
UN-SPIDER reproduction. ``level_parameter`` is the candidate lane's own statement of its levels; it is recorded
beside the words of protocol v1b and is not parsed (open point E1-OP11).
"""

O1_SOURCE_WORD = "Sentinel-1"
"""The word of protocol v1a ``case_portfolio`` (case O1, ``input_acquisition``) that names the source of the candidates."""
ONE_PIXEL_WORDING, THRESHOLD_WORDING = "one pixel", "threshold"
"""The words of protocol v1b ``t2_levels_by_input`` that say which kind of levels a T2 input has."""

LEVEL_RULE = (
    "Protocol v1b, ensemble_grid.core_axes (flood_input_single_state), owner choice 2: 20 m for the minus and the "
    "plus level and for every input, raster or vector; a vector product gets a 20 m negative or positive buffer in "
    "EPSG:32647. The buffer is applied to the repaired product before the clip, so a frame edge is neither eroded nor "
    "grown. No level is labelled central (protocol v1a, date_rule.flood_uncertainty_axis)."
)
PERMANENT_WATER_RULE = (
    "Protocol v1a, scoring_frame.components.flood_likelihood_0_100: the component is the flooded share of the unit's "
    "non-permanent-water land, and permanent water is ESA WorldCover 2021 v200 class 80 in every case. The scoring "
    "frame names permanent water for this component only, so the extents are written as they are and are not cut by "
    "it; exposure and closures read the whole extent."
)
STANDARD_CONFIDENCE_BASIS_4009 = (
    "An unvalidated preliminary agency extent (Field_Validation=0), used as provided; FloodGuard did not validate it. "
    "This is the confidence of the layer as evidence. The confidence class of a unit under confidence rule v1 is "
    "not computed here."
)
OPEN_POINTS: tuple[Mapping[str, str], ...] = (
    {
        "id": "E1-OP1",
        "point": "Rights level of the product 4009 layer of 22 October 2024 (case O2) and of the analysis extent, and "
                 "what a local level allows in Git.",
        "signed_files_say": "The rights record names CHIANGRAI_20240801_20241012_AccumulatedFlood as its layer in scope, "
                            "and decision R6 allows publication 'as a season envelope only (D3)'. Plan 4.1 rows 3 and 4 "
                            "expect one record for both layers. Guardrail GR6 speaks of apps/web/public/ only, and plan "
                            "3.1 keeps pitch variants outside Git; neither says whether a figure derived from a "
                            "local-level layer may be committed.",
        "what_this_module_does": "Reads both layers under the confirmed record (decision D2 covers the product). The "
                                 "accumulated layer is at level public; every other layer of the archive is at level "
                                 "local, and a public write of it is refused. Each written layer carries the level of "
                                 "the layer it comes from, so the footprint layers of case SE1 are local although its "
                                 "flood extents are public. Layers stay outside Git; the run receipt in Git holds "
                                 "whole-frame areas and part counts of the local-level layers and says so.",
        "for_the_owners": "Whether the record covers the 22 October layer and the analysis extent for publication; and "
                          "whether local means not in Git. If it does, the whole-frame figures of the 22 October layer "
                          "and of the analysis extent leave the committed receipts and the README (they are in the Git "
                          "history since the first commit of this task). If it does not, the per-tambon tables of case "
                          "O2 can be committed with their licence block.",
    },
    {
        "id": "E1-OP2",
        "point": "No rights record exists for the source data of the own radar candidates (case O1).",
        "signed_files_say": "Protocol v1a gives case O1 the input acquisition 'Sentinel-1, 16 Sep 2024 06:16 ICT'. No "
                            "rights record for Sentinel-1 data exists. The only other record in the repository covers "
                            "Sentinel-2 scenes and is not signed by a human.",
        "what_this_module_does": "load_o1 takes the rights record from the registry entry the receipt names only when "
                                 "that entry is registered as a record of Sentinel-1 data, and the record is confirmed. "
                                 "A receipt that names any other registered record, the product 4009 record included, "
                                 "is refused. No entry is such a record today, so every candidate is refused.",
        "for_the_owners": "A signed record for the Copernicus Sentinel-1 data the candidates are made from, registered "
                          "as such; and whether a candidate of the A6-prime classifier needs a record for its training "
                          "data as well, which this module does not ask for.",
    },
    {
        "id": "E1-OP3",
        "point": "How the 10 m WorldCover grid becomes an area of permanent water.",
        "signed_files_say": "Source and class only (ESA WorldCover 2021 v200, class 80).",
        "what_this_module_does": "Takes the footprint of every class-80 cell as permanent water, projects it to "
                                 "EPSG:32647 and measures areas by polygon overlay. A cell with no land-cover value is "
                                 "not counted as water; its area is reported.",
        "for_the_owners": "Whether another rule is wanted, for example cell centres, or a treatment of cells with no value.",
    },
    {
        "id": "E1-OP4",
        "point": "Shape of the one-pixel buffer.",
        "signed_files_say": "A 20 m negative or positive buffer in EPSG:32647; no join style and no arc resolution.",
        "what_this_module_does": "Round joins with 16 segments per quarter circle (the shapely default).",
        "for_the_owners": "Nothing, unless another shape is wanted.",
    },
    {
        "id": "E1-OP5",
        "point": "The one-pixel levels of a raster input.",
        "signed_files_say": "20 m for every input, raster or vector. For a raster: 'one pixel / 20 m erosion' and 'one "
                            "pixel buffer', with no cell neighbourhood (4 or 8) and no rule for cells with no answer.",
        "what_this_module_does": "Polygonises the flood cells and applies the same 20 m buffer as for a vector product. "
                                 "It refuses a one-pixel raster whose cells are not 20 m.",
        "for_the_owners": "Whether a cell-based erosion and dilation is wanted instead, and with which neighbourhood.",
    },
    {
        "id": "E1-OP6",
        "point": "Which cells form one polygon when polygons under 5 pixels are dropped from a T2 raster.",
        "signed_files_say": "Protocol v1b closure_rule_v1.parameters: polygons under 5 pixels are dropped before "
                            "intersection. Nothing on whether cells that touch at a corner belong to one polygon.",
        "what_this_module_does": "Takes the neighbourhood as an argument and builds no closure extent without it.",
        "for_the_owners": "4-neighbourhood or 8-neighbourhood.",
    },
    {
        "id": "E1-OP7",
        "point": "The calendar in which the days between an acquisition and the case reference date are counted.",
        "signed_files_say": "Acquisition within +/-3 days of the case reference date. Protocol v1a writes the O1 "
                            "acquisition in Thailand time (16 Sep 2024 06:16 ICT); it is 15 Sep 23:16 in UTC.",
        "what_this_module_does": "Counts whole days between two calendar dates and takes the acquisition date as it is "
                                 "given. No case is near the three-day edge.",
        "for_the_owners": "Thailand time or UTC, if a later input falls near the edge.",
    },
    {
        "id": "E1-OP8",
        "point": "The change-notice template of the product 4009 rights record.",
        "signed_files_say": "The template reads 'clipped to Mae Sai district (...)' and 'rasterised to ... m cells'. It was "
                            "written for the replay's raster of the district.",
        "what_this_module_does": "Writes its own notice for each vector layer, with the record's four steps in the "
                                 "record's order: the clip geometry (which can be the corridor), the repair count, the "
                                 "projection, the 20 m buffer of a minus or plus level, and 'not rasterised'.",
        "for_the_owners": "Whether the record's template should be widened to vector layers and to other clips.",
    },
    {
        "id": "E1-OP9",
        "point": "What an unconfirmed rights record allows.",
        "signed_files_say": "Plan 4.1 lets the two product 4009 inputs run at the local level if the record is not signed. "
                            "The task for this module asks for a refusal of any use without a confirmed record.",
        "what_this_module_does": "Refuses every use and every public write until the record is confirmed. The record is "
                                 "confirmed, so nothing is refused today.",
        "for_the_owners": "Which of the two applies, should a later record be pending.",
    },
    {
        "id": "E1-OP10",
        "point": "Which layer of the product archive is the product footprint.",
        "signed_files_say": "Plan 3.1 (stage P1) gives a flood input a footprint, and protocol v1a speaks of 'the "
                            "product footprint or analysis extent' (confidence condition) and of 'the 4009 analysis "
                            "extent' (case SE2-dist). Neither names a layer, and the rights record names the accumulated "
                            "layer only.",
        "what_this_module_does": "Reads CHIANGRAI_20240801_20241022_AnalysisExtent as the footprint of both flood "
                                 "layers. The name is a constant of this module (ANALYSIS_EXTENT_LAYER_4009), chosen "
                                 "because it is the only analysis-extent layer of the Chiang Rai layers in the archive. "
                                 "The layer has its own grant, at level local.",
        "for_the_owners": "Whether this is the layer the protocols mean, and whether the rights record should name it.",
    },
    {
        "id": "E1-OP11",
        "point": "The levels of a threshold candidate are checked by kind, not by value.",
        "signed_files_say": "Protocol v1b t2_levels_by_input states the levels of each T2 input in words: thresholds "
                            "for M1-v2 (-1 / 0 / +1 dB), M1-literal (-1 / 0 / +1 dB) and the A6-prime classifier (0.4 / "
                            "0.5 / 0.6), one pixel for the UN-SPIDER reproduction.",
        "what_this_module_does": "Refuses a candidate whose level_kind is not the kind the protocol states for it. The "
                                 "receipt's level_parameter is free text: it is recorded beside the protocol's words and "
                                 "its values are not compared with them.",
        "for_the_owners": "Whether the candidate receipt should carry its three thresholds as numbers, so that the "
                          "loader can refuse a candidate made at other levels.",
    },
)
"""Points the signed files leave open for this task. Each is reported; none is decided here."""


class FloodInputError(ValueError):
    """Raised when a flood input, its receipt or a frame cannot be used as the signed files state."""


# ---------------------------------------------------------------------------
# What the two signed protocol files say about a flood input
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FloodInputRules:
    """The parameters of this task, each read from protocol v1a or v1b."""

    one_pixel_m: float
    recency_window_days: int
    permanent_water_source: str
    permanent_water_class: int
    raster_minimum_polygon_px: int
    reporting_units: tuple[str, ...]
    accumulated_layer: Mapping[str, Any]
    layer_22_oct: Mapping[str, Any]
    cases: Mapping[str, Mapping[str, Any]]
    standard_4009_sentence: str
    product_4009_credit: str
    routing_geometry_file: Mapping[str, str]
    boundary_file_sha256: str
    protocol_sha256: Mapping[str, str | None]
    o1_levels: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    """For each flood input of case O1: the ``kind`` of its levels and the words protocol v1b ``stated`` for it."""


def level_kind_stated(candidate: str, stated: Any) -> str:
    """Return the kind of levels protocol v1b states for a T2 input: ``threshold`` or ``one_pixel``.

    Protocol v1b (``ensemble_grid``, ``t2_levels_by_input``) states the levels in words. An input whose words
    say "threshold" has three threshold levels; an input whose words say "one pixel" has the spatial levels.

    Raises:
        FloodInputError: when the words say neither, or both.
    """

    text = str(stated)
    kinds = [kind for kind, wording in ((THRESHOLD_LEVELS, THRESHOLD_WORDING), (ONE_PIXEL_LEVELS, ONE_PIXEL_WORDING)) if wording in text]
    if len(kinds) != 1:
        raise FloodInputError(f"protocol v1b states the levels of {candidate!r} in other words than this code reads: {text!r}")
    return kinds[0]


def rules_from_protocols(v1a: Mapping[str, Any], v1b: Mapping[str, Any],
                         protocol_sha256: Mapping[str, str | None] | None = None) -> FloodInputRules:
    """Read the flood-input parameters from the parsed protocols v1a and v1b.

    Raises:
        FloodInputError: when a file is not signed, a parameter is missing, or the one-pixel distance is not
            one number for the minus level, the plus level and vector products.
    """

    try:
        if v1a["status"] != "signed" or v1b["status"] != "signed":
            raise FloodInputError("the flood-input parameters are read from signed protocol files only")
        axis = next(row for row in v1b["ensemble_grid"]["core_axes"] if row["axis"] == "flood_input_single_state")
        pixel = axis["one_pixel_m"]
        distances = {float(pixel[key]) for key in ("minus", "plus", "vector_products")}
        if len(distances) != 1 or not next(iter(distances)) > 0:
            raise FloodInputError("protocol v1b does not give one positive one-pixel distance for every level and input")
        water = v1a["scoring_frame"]["components"]["flood_likelihood_0_100"]["permanent_water"]
        product = v1a["date_rule"]["product_4009"]
        wording = v1a["wording"]
        relations = tuple(v1a["date_rule"]["temporal_relation_values"])
        if set(relations) != {EVENT_ALIGNED, DATED_OTHER, SEASON_WINDOW}:
            raise FloodInputError("protocol v1a declares other temporal relations than this module implements")
        cases = {str(case["id"]): MappingProxyType(dict(case)) for case in v1a["case_portfolio"]["cases"]}
        stated_levels = axis["t2_levels_by_input"]
        o1_levels: dict[str, Mapping[str, str]] = {}
        for candidate in (cases["O1"]["flood_inputs"] if "O1" in cases else ()):
            if candidate not in stated_levels:
                raise FloodInputError(f"protocol v1b states no levels for the O1 flood input {candidate!r}")
            o1_levels[str(candidate)] = MappingProxyType({
                "kind": level_kind_stated(str(candidate), stated_levels[candidate]), "stated": str(stated_levels[candidate])})
        return FloodInputRules(
            one_pixel_m=next(iter(distances)),
            recency_window_days=int(v1a["date_rule"]["recency_window_days"]),
            permanent_water_source=str(water["source"]),
            permanent_water_class=int(water["class"]),
            raster_minimum_polygon_px=int(v1b["closure_rule_v1"]["parameters"]["raster_minimum_polygon_px"]),
            reporting_units=tuple(str(unit) for unit in v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"]),
            accumulated_layer=MappingProxyType(dict(product["accumulated_layer"])),
            layer_22_oct=MappingProxyType(dict(product["layer_22_oct"])),
            cases=MappingProxyType(cases),
            o1_levels=MappingProxyType(o1_levels),
            standard_4009_sentence=str(wording["standard_4009_sentence"]),
            product_4009_credit=str(wording["product_4009_credit"]),
            routing_geometry_file=MappingProxyType({key: str(v1b["corridor_polygon"]["geometry_file"][key]) for key in ("path", "sha256")}),
            boundary_file_sha256=str(v1b["national_vulnerability_anchors"]["inputs"]["tambon_boundaries"]["sha256"]),
            protocol_sha256=MappingProxyType(dict(protocol_sha256 or {name: None for name in normalisation.PROTOCOL_NAMES})),
        )
    except FloodInputError:
        raise
    except (KeyError, TypeError, ValueError, StopIteration) as error:
        raise FloodInputError(f"the protocol files do not hold the flood-input parameters: {error!r}") from error


def load_rules(v1a_path: Path | str, v1b_path: Path | str, receipts_path: Path | str) -> FloodInputRules:
    """Read the flood-input parameters from the two protocol files, which must both be in force.

    Raises:
        floodguard.normalisation.NormalisationError: when a file is not in force.
        FloodInputError: when v1b names another v1a, or a parameter is missing.
    """

    v1a, v1a_sha256 = normalisation.read_protocol_in_force("v1a", v1a_path, receipts_path)
    v1b, v1b_sha256 = normalisation.read_protocol_in_force("v1b", v1b_path, receipts_path)
    if v1b.get("depends_on", {}).get("v1a_sha256") != v1a_sha256:
        raise FloodInputError("protocol v1b does not name the v1a file that was read")
    return rules_from_protocols(v1a, v1b, {"v1a": v1a_sha256, "v1b": v1b_sha256})


def protocol_hashes(rules: FloodInputRules) -> dict[str, str]:
    """Return the SHA-256 of the two protocol files, as ``planning_protocol_v1a`` and ``planning_protocol_v1b``.

    Raises:
        FloodInputError: when the rules were not read from the files in force.
    """

    hashes = {f"planning_protocol_{name}": rules.protocol_sha256.get(name) for name in normalisation.PROTOCOL_NAMES}
    if not all(isinstance(value, str) and value for value in hashes.values()):
        raise FloodInputError("the rules carry no protocol hashes: read them with load_rules, which checks RECEIPTS.jsonl")
    return {key: str(value) for key, value in hashes.items()}


def temporal_relation(acquisition_date: str | None, case_reference_date: str | None, *, window_days: int,
                      season_window: tuple[str, str] | None = None) -> str:
    """Return the temporal relation of an input to its case (protocol v1a, ``date_rule``).

    The rule is strict: an input is ``event_aligned`` only when it has one acquisition date and that date is
    within ``window_days`` of the case reference date. An input that spans a season is ``season_window``
    whatever date it carries, and a dated input with no reference date to meet is ``dated_other``.

    Args:
        acquisition_date: The one acquisition date (``YYYY-MM-DD``), or ``None`` for a season window.
        case_reference_date: The reference date of the case (``YYYY-MM-DD``), or ``None``.
        window_days: The recency window, in days.
        season_window: The first and last date of an input that has no single acquisition date.

    Raises:
        FloodInputError: when an input has both or neither of a date and a season window, or a date is malformed.
    """

    if (acquisition_date is None) == (season_window is None):
        raise FloodInputError("an input has either one acquisition date or a season window")
    try:
        if season_window is not None:
            first, last = (date.fromisoformat(value) for value in season_window)
            if last < first:
                raise FloodInputError("a season window ends before it starts")
            return SEASON_WINDOW
        acquired = date.fromisoformat(str(acquisition_date))
        if case_reference_date is None:
            return DATED_OTHER
        reference = date.fromisoformat(case_reference_date)
    except (TypeError, ValueError) as error:
        raise FloodInputError(f"dates are written YYYY-MM-DD: {error}") from error
    return EVENT_ALIGNED if abs((acquired - reference).days) <= window_days else DATED_OTHER


# ---------------------------------------------------------------------------
# Geometry: parts, projection, repair, levels, clip
# ---------------------------------------------------------------------------


def polygon_parts(geometry: Any) -> np.ndarray:
    """Return the polygon parts of a geometry or of an array of geometries (lines and points are left out)."""

    parts = shapely.get_parts(shapely.get_parts(np.atleast_1d(np.asarray(geometry, dtype=object))))
    return parts[shapely.get_type_id(parts) == 3]


def as_multipolygon(geometry: Any) -> MultiPolygon:
    """Return the polygon parts of ``geometry`` as one valid multipolygon (empty when there is none)."""

    if isinstance(geometry, MultiPolygon) and geometry.is_valid:
        return geometry
    parts = polygon_parts(geometry)
    parts = parts[~shapely.is_empty(parts)]
    if not len(parts):
        return MultiPolygon()
    merged = shapely.union_all(parts)
    parts = polygon_parts(merged if merged.is_valid else shapely.make_valid(merged))
    return MultiPolygon(list(parts))


def project(geometry: Any, source_crs: str, target_crs: str) -> Any:
    """Project a geometry, or an array of geometries, vertex by vertex from ``source_crs`` to ``target_crs``."""

    if source_crs == target_crs:
        return geometry
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return shapely.transform(geometry, lambda xy: np.column_stack(transformer.transform(xy[:, 0], xy[:, 1])))


def snap(geometry: Any) -> MultiPolygon:
    """Snap a geometry to the 1 mm coordinate grid and return its polygons as one valid multipolygon."""

    multipolygon = as_multipolygon(geometry)
    if multipolygon.is_empty:
        return multipolygon
    return as_multipolygon(shapely.set_precision(multipolygon, COORDINATE_GRID_M))


@dataclass(frozen=True)
class Frame:
    """One frame of a case, in EPSG:32647: the reporting frame or the routing context."""

    name: str
    label: str
    geometry: BaseGeometry
    source: Mapping[str, Any]
    units: Mapping[str, BaseGeometry] = field(default_factory=dict)

    @property
    def area_m2(self) -> float:
        """The area of the frame in EPSG:32647."""

        return float(self.geometry.area)


def frame_from_wgs84(name: str, label: str, geometry: BaseGeometry, source: Mapping[str, Any]) -> Frame:
    """Build a frame from one polygon in longitude and latitude (a corridor, an AOI).

    Raises:
        FloodInputError: when the geometry holds no polygon.
    """

    projected = as_multipolygon(project(as_multipolygon(shapely.make_valid(geometry)), WGS84_CRS, ANALYSIS_CRS))
    if projected.is_empty:
        raise FloodInputError(f"frame {name} has no polygon")
    return Frame(name, label, projected, MappingProxyType(dict(source)))


def frame_from_units(name: str, label: str, units: Sequence[tuple[str, BaseGeometry]], source: Mapping[str, Any]) -> Frame:
    """Build a frame as the union of unit polygons given in longitude and latitude (the units of a case).

    Raises:
        FloodInputError: for no unit, a repeated unit or a unit without a polygon.
    """

    identifiers = [unit_id for unit_id, _geometry in units]
    if not identifiers or len(set(identifiers)) != len(identifiers):
        raise FloodInputError(f"frame {name} needs its units, each once")
    projected: dict[str, BaseGeometry] = {}
    for unit_id, geometry in units:
        unit = as_multipolygon(project(as_multipolygon(shapely.make_valid(geometry)), WGS84_CRS, ANALYSIS_CRS))
        if unit.is_empty:
            raise FloodInputError(f"unit {unit_id} has no polygon")
        projected[str(unit_id)] = unit
    union = as_multipolygon(shapely.union_all(list(projected.values())))
    return Frame(name, label, union, MappingProxyType(dict(source)), MappingProxyType(projected))


def repair_product(product: Any, frames: Sequence[Frame], *, source_crs: str, reach_m: float) -> tuple[MultiPolygon, dict[str, Any]]:
    """Repair the polygon parts of a product that can reach a frame, and return them as one extent in EPSG:32647.

    Validity is tested on the coordinates as provided, for every part. A part is read when its bounding box
    comes within ``reach_m`` of the bounding box of a frame: a part farther away cannot reach the frame even
    at the plus level. Those parts are repaired with ``make_valid`` in the source coordinates, projected, and
    repaired once more if the projection left one invalid.

    Reading by bounding box takes in parts that never touch a frame, so the record counts twice. The counts
    of the parts read say what was repaired. The counts for each frame are measured on the geometry itself:
    the parts that intersect the frame, the parts that lie within ``reach_m`` of it (those are the parts whose
    plus level reaches the frame), and the repaired ones among each. A change notice states the second kind
    (:func:`repair_count_of_layer`), because a notice speaks of the parts in its file.

    Returns:
        The extent (the union of the repaired parts) and the repair record: the method, the counts for the
        whole product, the counts for the parts read, and the counts for each frame.
    """

    parts = polygon_parts(product)
    parts = parts[~shapely.is_empty(parts)]
    record: dict[str, Any] = {
        "method": REPAIR_METHOD,
        "source_parts": int(len(parts)),
        "source_parts_invalid": 0,
        "parts_read": 0,
        "parts_repaired": 0,
        "parts_repaired_after_projection": 0,
        "reach_m": reach_m,
        "by_frame": {frame.name: {"parts_read": 0, "parts_read_repaired": 0, "parts_intersecting": 0,
                                  "parts_intersecting_repaired": 0, "parts_within_reach": 0,
                                  "parts_within_reach_repaired": 0} for frame in frames},
        "note": "A part is read when its bounding box comes within reach_m of the bounding box of a frame, so "
                "parts_read holds parts that never touch the frame; parts_repaired counts the invalid ones among the "
                "parts read, and source_parts_invalid counts every invalid part of the layer. For each frame, "
                "parts_intersecting and parts_within_reach are measured on the repaired geometry itself: the parts "
                "that intersect the frame, and the parts within reach_m of it. A change notice states the repaired "
                "ones among these.",
    }
    if not len(parts):
        return MultiPolygon(), record
    invalid = ~shapely.is_valid(parts)
    bounds = shapely.bounds(project(parts, source_crs, ANALYSIS_CRS))
    read = np.zeros(len(parts), dtype=bool)
    near_by_frame: dict[str, np.ndarray] = {}
    for frame in frames:
        west, south, east, north = frame.geometry.bounds
        near = ((bounds[:, 0] <= east + reach_m) & (bounds[:, 2] >= west - reach_m)
                & (bounds[:, 1] <= north + reach_m) & (bounds[:, 3] >= south - reach_m))
        near_by_frame[frame.name] = near
        read |= near
    record.update(source_parts_invalid=int(invalid.sum()), parts_read=int(read.sum()), parts_repaired=int((read & invalid).sum()))
    if not read.any():
        return MultiPolygon(), record
    # One repaired geometry per part read, in the order of the parts, so that a part can be counted for a frame.
    repaired = project(shapely.make_valid(parts[read]), source_crs, ANALYSIS_CRS)
    was_invalid = invalid[read]
    for frame in frames:
        near = near_by_frame[frame.name][read]
        shapely.prepare(frame.geometry)
        intersecting = near & shapely.intersects(frame.geometry, repaired)
        within = (intersecting | (near & shapely.dwithin(frame.geometry, repaired, reach_m))) if reach_m > 0 else intersecting
        record["by_frame"][frame.name] = {
            "parts_read": int(near.sum()),
            "parts_read_repaired": int((near & was_invalid).sum()),
            "parts_intersecting": int(intersecting.sum()),
            "parts_intersecting_repaired": int((intersecting & was_invalid).sum()),
            "parts_within_reach": int(within.sum()),
            "parts_within_reach_repaired": int((within & was_invalid).sum()),
        }
    projected = polygon_parts(repaired)
    still_invalid = ~shapely.is_valid(projected)
    if still_invalid.any():
        record["parts_repaired_after_projection"] = int(still_invalid.sum())
        projected = polygon_parts(shapely.make_valid(projected))
    return as_multipolygon(shapely.union_all(projected)), record


def repair_count_of_layer(repair: Mapping[str, Any], *, frame: str, level: str | None) -> int:
    """Return the repair count a change notice states for one written layer: the repaired parts that are in it.

    For the minus level, the level as provided and a footprint these are the repaired parts that intersect
    the frame. For the plus level they are the repaired parts within the one-pixel distance of the frame: a
    part that lies just outside the frame reaches it once it is grown. A candidate with threshold levels has
    one repair record per level.

    Raises:
        FloodInputError: when the repair record holds no counts for the frame.
    """

    counts = repair.get("by_level", {}).get(level, repair) if level is not None else repair
    by_frame = counts.get("by_frame", {})
    if frame not in by_frame:
        raise FloodInputError(f"the repair record holds no counts for frame {frame}")
    return int(by_frame[frame]["parts_within_reach_repaired" if level == PLUS and "by_level" not in repair
                               else "parts_intersecting_repaired"])


def one_pixel_levels(extent: BaseGeometry, one_pixel_m: float) -> dict[str, MultiPolygon]:
    """Return the minus, as-provided and plus states of an extent in EPSG:32647 (see :data:`LEVEL_RULE`).

    Raises:
        FloodInputError: when the distance is not positive.
    """

    if not one_pixel_m > 0:
        raise FloodInputError("the one-pixel distance must be positive")
    return {
        MINUS: as_multipolygon(extent.buffer(-one_pixel_m, quad_segs=BUFFER_QUAD_SEGS)),
        AS_PROVIDED: as_multipolygon(extent),
        PLUS: as_multipolygon(extent.buffer(one_pixel_m, quad_segs=BUFFER_QUAD_SEGS)),
    }


def clip_to_frame(extent: BaseGeometry, frame: Frame) -> MultiPolygon:
    """Clip an extent in EPSG:32647 to a frame and snap the result to the coordinate grid."""

    if extent.is_empty:
        return MultiPolygon()
    return snap(shapely.intersection(extent, frame.geometry))


def geometry_summary(geometry: BaseGeometry) -> dict[str, Any]:
    """Return the area, the polygon count and the vertex count of an extent in EPSG:32647."""

    return {
        "area_m2": round(float(geometry.area), 3),
        "area_km2": round(float(geometry.area) / 1e6, 6),
        "polygons": int(shapely.get_num_geometries(geometry)) if not geometry.is_empty else 0,
        "vertices": int(shapely.get_num_coordinates(geometry)),
    }


# ---------------------------------------------------------------------------
# Permanent water (protocol v1a scoring frame: ESA WorldCover 2021 v200, class 80)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermanentWater:
    """The permanent water of one frame, in EPSG:32647, and what it was read from."""

    frame: str
    geometry: MultiPolygon
    record: Mapping[str, Any]


def sha256_file(path: Path | str) -> str:
    """Return the SHA-256 of a file as lowercase hexadecimal."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cell_polygons(mask: np.ndarray, transform: Any, connectivity: int = 4) -> np.ndarray:
    """Return the footprints of the true cells of a mask as polygons in the raster's coordinates."""

    from rasterio.features import shapes

    if not mask.any():
        return np.array([], dtype=object)
    found = [shape(geometry) for geometry, _value in shapes(mask.astype("uint8"), mask=mask, transform=transform, connectivity=connectivity)]
    return np.array(found, dtype=object)


def permanent_water(land_cover: Path | str, frame: Frame, *, water_class: int, source_name: str) -> PermanentWater:
    """Read the permanent water of a frame from a land-cover raster (see :data:`PERMANENT_WATER_RULE`).

    The footprint of every cell of class ``water_class`` is permanent water. Cells with no land-cover value
    are not water; their area inside the frame is reported, because unknown is not the same as land.

    Args:
        land_cover: The land-cover raster (for the planning frame: the ESA WorldCover 2021 v200 tile).
        frame: The frame to read, in EPSG:32647.
        water_class: The class value of permanent water (protocol v1a: 80).
        source_name: The name protocol v1a gives the source.

    Raises:
        FloodInputError: when the raster has no coordinate system or does not cover the frame.
    """

    import rasterio
    from rasterio.windows import Window, from_bounds

    path = Path(land_cover)
    with rasterio.open(path) as source:
        if source.crs is None:
            raise FloodInputError("the land-cover raster has no coordinate system")
        raster_crs = source.crs.to_string()
        bounds = project(frame.geometry, ANALYSIS_CRS, raster_crs).bounds
        if not box(*source.bounds).buffer(1e-6 * abs(source.transform.a)).covers(box(*bounds)):
            raise FloodInputError(f"the land-cover raster does not cover frame {frame.name}")
        window = from_bounds(*bounds, transform=source.transform).round_offsets(op="floor").round_lengths(op="ceil")
        # One cell more on every side, so that rounding at the edge of the frame cannot lose a cell.
        window = Window(window.col_off - 1, window.row_off - 1, window.width + 2, window.height + 2)
        window = window.intersection(Window(0, 0, source.width, source.height))
        cells = source.read(1, window=window)
        transform = source.window_transform(window)
        nodata = source.nodata
        tags = source.tags()
        pixel = [abs(source.transform.a), abs(source.transform.e)]
    water_cells = cells == water_class
    no_value_cells = (cells == nodata) if nodata is not None else np.zeros(cells.shape, dtype=bool)

    def inside(mask: np.ndarray) -> MultiPolygon:
        polygons = _cell_polygons(mask, transform)
        if not len(polygons):
            return MultiPolygon()
        return clip_to_frame(as_multipolygon(shapely.union_all(project(polygons, raster_crs, ANALYSIS_CRS))), frame)

    water, no_value = inside(water_cells), inside(no_value_cells)
    record = {
        "rule": PERMANENT_WATER_RULE,
        "source": source_name,
        "class": water_class,
        "file": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "raster_crs": raster_crs,
        "cell_size": pixel,
        "product_version": tags.get("product_version"),
        "time_start": tags.get("time_start"),
        "time_end": tags.get("time_end"),
        "licence": tags.get("license"),
        "attribution": tags.get("copyright"),
        "window": {"col_off": int(window.col_off), "row_off": int(window.row_off), "width": int(window.width), "height": int(window.height)},
        "cells_read": int(cells.size),
        "class_cells_in_window": int(water_cells.sum()),
        "no_value_cells_in_window": int(no_value_cells.sum()),
        "frame": frame.name,
        "frame_km2": round(frame.area_m2 / 1e6, 6),
        "permanent_water_km2": round(float(water.area) / 1e6, 6),
        "non_permanent_water_km2": round((frame.area_m2 - float(water.area)) / 1e6, 6),
        "no_land_cover_value_km2": round(float(no_value.area) / 1e6, 6),
        "measurement": "The footprint of every cell of the class, projected vertex by vertex to EPSG:32647, clipped to "
                       "the frame and snapped to a 1 mm grid; areas by polygon overlay (open point E1-OP3).",
    }
    return PermanentWater(frame.name, water, MappingProxyType(record))


def flooded_land_areas(unit: BaseGeometry, extent: BaseGeometry, water: BaseGeometry) -> dict[str, float]:
    """Return the two areas of one unit that ``floodguard.normalisation.flood_likelihood`` takes, in square metres.

    ``non_permanent_water_land_area`` is the unit with permanent water left out;
    ``flooded_non_permanent_water_land_area`` is the part of it inside the flood extent. All three geometries
    are in EPSG:32647. This computes areas only: the component is computed by the normalisation module.
    """

    land = unit if water.is_empty else shapely.difference(unit, water)
    flooded = shapely.intersection(land, extent) if not extent.is_empty else MultiPolygon()
    return {
        "flooded_non_permanent_water_land_area": float(as_multipolygon(flooded).area),
        "non_permanent_water_land_area": float(as_multipolygon(land).area),
    }


# ---------------------------------------------------------------------------
# The input record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InputSpec:
    """What a flood input is: its case, lane, tier and dates, and where it comes from."""

    case_id: str
    input_id: str
    input_name: str
    lane: str
    tier: str
    case_reference_date: str | None
    acquisition_date: str | None
    season_window: tuple[str, str] | None
    temporal_relation: str
    source_timestamp: str
    source: Mapping[str, Any]
    geometry_kind: str
    confidence_basis: str
    assumptions: tuple[str, ...]
    statements: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FloodInput:
    """One flood input, ready for the planning stages: its extents by level and frame, and its record.

    ``extents`` maps a level to a frame name to the extent in EPSG:32647; ``record`` is the input record as
    plain JSON values; ``closure_extents`` holds the extents of a T2 raster with small polygons dropped, when
    they were built.
    """

    spec: InputSpec
    extents: Mapping[str, Mapping[str, MultiPolygon]]
    footprints: Mapping[str, MultiPolygon]
    record: Mapping[str, Any]
    closure_extents: Mapping[str, Mapping[str, MultiPolygon]] = field(default_factory=dict)

    def extent(self, level: str, frame: str) -> MultiPolygon:
        """Return the extent of one level inside one frame, in EPSG:32647."""

        return self.extents[level][frame]

    def extent_wgs84(self, level: str, frame: str) -> BaseGeometry:
        """Return the same extent in longitude and latitude, as ``floodguard.closure_rules`` takes it."""

        return project(self.extents[level][frame], ANALYSIS_CRS, WGS84_CRS)


def level_sentence(level: str, one_pixel_m: float) -> str:
    """Say what a level changed, for a change notice."""

    if level not in LEVELS:
        raise FloodInputError(f"unknown level {level!r}")
    if level == MINUS:
        return f"extent shrunk by a {one_pixel_m:g} m negative buffer (the minus level of protocol v1b)"
    if level == PLUS:
        return f"extent grown by a {one_pixel_m:g} m buffer (the plus level of protocol v1b)"
    return "extent otherwise as provided"


def change_notice(*, clip_geometry: str, repair_count: int, source_crs: str, change: str, credit: str, licence_name: str,
                  geometry_kind: str = "vector") -> str:
    """Return the change notice of one derived layer.

    The four steps of the product 4009 rights record are stated in its order (clip, geometry repair,
    reprojection, rasterisation), with what this layer did for each, and the buffer of a minus or plus level
    between them. A vector product is not rasterised; a raster candidate is polygonised.

    Raises:
        FloodInputError: for an empty value or a repair count that is not a whole number.
    """

    if isinstance(repair_count, bool) or not isinstance(repair_count, int) or repair_count < 0:
        raise FloodInputError("repair_count must be a whole number of repaired parts")
    values = (clip_geometry, source_crs, change, credit, licence_name)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise FloodInputError("every change-notice value must be stated")
    projection = f"reprojected from {source_crs} to {ANALYSIS_CRS}" if source_crs != ANALYSIS_CRS else f"kept in {ANALYSIS_CRS}"
    raster_step = "not rasterised" if geometry_kind == "vector" else "polygonised from the cells of the raster"
    return (
        f"Changed by FloodGuard: clipped to {clip_geometry}; geometry repaired ({REPAIR_METHOD}; {repair_count} parts "
        f"repaired); {projection}; {change}; coordinates snapped to a {COORDINATE_GRID_M:g} m grid; {raster_step}. "
        f"Source: {credit}, {licence_name}."
    )


FLOOD_EXTENT, PRODUCT_FOOTPRINT = "flood_extent", "product_footprint"
"""What a written layer is: an extent of the flood layer, or the footprint of the product."""


def lineage_rights(grant: rights.RightsGrant, footprint_grant: rights.RightsGrant | None) -> dict[str, Any]:
    """Return the rights level of each kind of file an input writes (protocol v1a, guardrail GR6).

    The level of an output is the minimum across its lineage. A flood extent comes from the flood layer only
    and a footprint layer from the footprint layer only, so each has the level of its layer. The input
    record holds figures of both, so it has the minimum of the two.
    """

    levels = [grant.rights_level] + ([footprint_grant.rights_level] if footprint_grant is not None else [])
    return {
        "rule": "Protocol v1a, guardrail GR6: the rights level of an output is the minimum across its lineage.",
        FLOOD_EXTENT: grant.rights_level,
        PRODUCT_FOOTPRINT: footprint_grant.rights_level if footprint_grant is not None else None,
        "input_record": rights.minimum_level(levels),
        "note": "A flood extent comes from the flood layer only and a footprint layer from the footprint layer only. "
                "The input record holds figures of both, so it is at the minimum of the two.",
    }


def build_flood_input(
    product: Any,
    frames: Sequence[Frame],
    *,
    spec: InputSpec,
    rules: FloodInputRules,
    grant: rights.RightsGrant,
    source_crs: str = WGS84_CRS,
    footprint: Any | None = None,
    footprint_grant: rights.RightsGrant | None = None,
    water: PermanentWater | None = None,
    levels: Mapping[str, MultiPolygon] | None = None,
    repair: Mapping[str, Any] | None = None,
) -> FloodInput:
    """Repair a product, make its three levels, clip them to the frames of the case and write its record.

    This is the common path of every loader, and it takes any agency polygon (plan 4.1).

    Args:
        product: The extent as provided: one geometry or an array of polygon parts, in ``source_crs``.
        frames: The frames of the case, in EPSG:32647.
        spec: What the input is.
        rules: The parameters of the signed protocols.
        grant: The rights grant of the flood layer, from the registry.
        source_crs: The coordinate system of ``product`` and ``footprint``.
        footprint: The product footprint or analysis extent, in ``source_crs``, when the product has one.
        footprint_grant: The rights grant of the footprint layer, from the registry. A footprint is a layer of
            its own, so it needs its own grant; its level can be lower than that of the flood layer.
        water: The permanent water of the reporting frame, when it was read.
        levels: The three levels in EPSG:32647, when the lane that made the input ran them itself
            (a radar candidate with threshold levels). ``product`` is then not read.
        repair: The repair record that goes with ``levels``.

    Raises:
        FloodInputError: for no frame, a repeated frame name, a water layer of another frame, or a footprint
            without its grant.
    """

    names = [frame.name for frame in frames]
    if not names or len(set(names)) != len(names):
        raise FloodInputError("a flood input needs its frames, each once")
    if water is not None and water.frame not in names:
        raise FloodInputError("the permanent water was read for a frame that is not among the frames of the case")
    if (footprint is None) != (footprint_grant is None):
        raise FloodInputError("a footprint is a layer of its own: it is given with the rights grant of its layer, or not at all")
    if levels is None:
        extent, repair_record = repair_product(product, frames, source_crs=source_crs, reach_m=rules.one_pixel_m)
        states = one_pixel_levels(extent, rules.one_pixel_m)
        level_rule = LEVEL_RULE
    else:
        if set(levels) != set(LEVELS) or repair is None:
            raise FloodInputError("supplied levels must be minus, as_provided and plus, with their repair record")
        states, repair_record = {level: as_multipolygon(levels[level]) for level in LEVELS}, dict(repair)
        level_rule = str(spec.statements.get("level_rule", ""))

    extents = {level: {frame.name: clip_to_frame(states[level], frame) for frame in frames} for level in LEVELS}
    level_records: dict[str, Any] = {}
    for level in LEVELS:
        by_frame: dict[str, Any] = {}
        for frame in frames:
            clipped = extents[level][frame.name]
            summary = geometry_summary(clipped)
            if water is not None and water.frame == frame.name:
                on_water = float(as_multipolygon(shapely.intersection(clipped, water.geometry)).area) if not clipped.is_empty else 0.0
                summary["area_on_permanent_water_km2"] = round(on_water / 1e6, 6)
                summary["area_outside_permanent_water_km2"] = round((float(clipped.area) - on_water) / 1e6, 6)
            by_frame[frame.name] = summary
        level_records[level] = by_frame

    footprints: dict[str, MultiPolygon] = {}
    footprint_record: dict[str, Any] | None = None
    if footprint is not None and footprint_grant is not None:
        whole, footprint_repair = repair_product(footprint, frames, source_crs=source_crs, reach_m=0.0)
        footprint_record = {"layer": footprint_grant.layer, "rights": footprint_grant.as_record(),
                            "repair": footprint_repair, "by_frame": {}}
        for frame in frames:
            footprints[frame.name] = clip_to_frame(whole, frame)
            footprint_record["by_frame"][frame.name] = {
                **geometry_summary(footprints[frame.name]),
                "share_of_frame": round(float(footprints[frame.name].area) / frame.area_m2, 6),
            }

    record = {
        "schema_version": INPUT_RECORD_SCHEMA,
        "flood_inputs_version": FLOOD_INPUTS_VERSION,
        "case_id": spec.case_id,
        "input_id": spec.input_id,
        "input_name": spec.input_name,
        "lane": spec.lane,
        "tier": spec.tier,
        "temporal_relation": spec.temporal_relation,
        "case_reference_date": spec.case_reference_date,
        "acquisition_date": spec.acquisition_date,
        "season_window": list(spec.season_window) if spec.season_window else None,
        "source_timestamp": spec.source_timestamp,
        "source": dict(spec.source),
        "geometry_kind": spec.geometry_kind,
        "rights": grant.as_record(),
        "lineage_rights": lineage_rights(grant, footprint_grant),
        "confidence_class": "low",
        "confidence_basis": spec.confidence_basis,
        "assumptions": list(spec.assumptions),
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        **dict(spec.statements),
        "analysis_crs": ANALYSIS_CRS,
        "coordinate_grid_m": COORDINATE_GRID_M,
        "frames": {frame.name: {"label": frame.label, "area_km2": round(frame.area_m2 / 1e6, 6),
                                "units": sorted(frame.units), "source": dict(frame.source)} for frame in frames},
        "repair": repair_record,
        "levels": {
            "rule": level_rule,
            "one_pixel_m": rules.one_pixel_m,
            "buffer": {"join_style": "round", "segments_per_quarter_circle": BUFFER_QUAD_SEGS},
            "none_is_central": True,
            "by_level": level_records,
        },
        "footprint": footprint_record,
        "permanent_water": dict(water.record) if water is not None else None,
        "protocol_sha256": {f"planning_protocol_{name}": rules.protocol_sha256.get(name) for name in normalisation.PROTOCOL_NAMES},
    }
    return FloodInput(spec, MappingProxyType(extents), MappingProxyType(footprints), record)


# ---------------------------------------------------------------------------
# SE1 and O2: the two layers of UNOSAT/GISTDA product 4009
# ---------------------------------------------------------------------------

_SEASON_NAME = re.compile(r"_(\d{4})(\d{2})(\d{2})_(\d{4})(\d{2})(\d{2})_")
_DATED_NAME = re.compile(r"_(\d{4})(\d{2})(\d{2})_(?!\d{8}_)")


def read_product_layer(archive: Path | str, layer: str, geodatabase: str = GEODATABASE_4009) -> tuple[BaseGeometry, dict[str, Any]]:
    """Read one layer of the product archive and return its one geometry with the attributes that date and qualify it.

    Only the named layer is opened, through GDAL's ``/vsizip/``. The layer must hold one dissolved feature in
    longitude and latitude.

    Raises:
        FloodInputError: when the layer does not hold exactly one feature or is not in WGS 84.
    """

    import pyogrio

    with warnings.catch_warnings():
        # GDAL reports the unclosed and self-intersecting rings of the layer as it reads them; repair_product counts them.
        warnings.simplefilter("ignore", RuntimeWarning)
        table = pyogrio.read_dataframe(f"/vsizip/{Path(archive).as_posix()}/{geodatabase}", layer=layer)
    if len(table) != 1:
        raise FloodInputError(f"{layer} must hold one dissolved feature; found {len(table)}")
    # The archive gives a compound system (WGS 84 with EGM96 heights); the horizontal part must be WGS 84.
    horizontal = None if table.crs is None else (table.crs.sub_crs_list[0] if table.crs.is_compound else table.crs)
    if horizontal is None or horizontal.to_epsg() != 4326:
        raise FloodInputError(f"{layer} must be in WGS 84 longitude and latitude")
    row = table.iloc[0]
    attributes: dict[str, Any] = {}
    for key in ("Field_Validation", "Sensor_Date", "EventCode", "Water_Class", "Confidence_ID"):
        if key in table.columns and row[key] is not None and str(row[key]) not in ("nan", "NaT"):
            attributes[key] = str(row[key])[:10] if key == "Sensor_Date" else (str(row[key]) if key == "EventCode" else int(row[key]))
    return shapely.force_2d(table.geometry.iloc[0]), attributes


def product_4009_spec(case_id: str, rules: FloodInputRules, attributes: Mapping[str, Any], archive: Mapping[str, Any],
                      event_code: str) -> InputSpec:
    """Say what the product 4009 layer of case ``SE1`` or ``O2`` is, from protocol v1a and the layer's attributes.

    Raises:
        FloodInputError: when the case is not one of the two, the layer was field-checked or carries another
            event, or the temporal relation the dates give is not the one protocol v1a declares.
    """

    if case_id not in ("SE1", "O2") or case_id not in rules.cases:
        raise FloodInputError(f"case {case_id!r} is not a product 4009 case of protocol v1a")
    case = rules.cases[case_id]
    declared = rules.accumulated_layer if case_id == "SE1" else rules.layer_22_oct
    layer = str(declared["layer"])
    if attributes.get("Field_Validation") != 0:
        raise FloodInputError(f"{layer}: Field_Validation is {attributes.get('Field_Validation')!r}; the standard sentence says 0")
    if attributes.get("EventCode") != event_code:
        raise FloodInputError(f"{layer}: EventCode is {attributes.get('EventCode')!r}, not {event_code}")
    statements: dict[str, Any] = {
        "used_as_provided": True,
        "field_validation": 0,
        "standard_sentence": rules.standard_4009_sentence,
        "credit": rules.product_4009_credit,
    }
    common = [
        "The layer is used as provided: a preliminary agency extent that was not checked in the field "
        "(Field_Validation=0). FloodGuard did not validate it.",
        "Every vertex is projected to EPSG:32647 as it is, and areas are measured there. Coordinates are snapped to a "
        "1 mm grid.",
        "The minus and plus levels are 20 m buffers of the repaired layer (protocol v1b, owner choice 2). They are "
        "perturbations of one product state, not a range of flood depth or of time.",
        "Permanent water (ESA WorldCover 2021 v200, class 80) does not cut the extent. It is left out of the "
        "flood-likelihood areas only, as the scoring frame of protocol v1a states.",
    ]
    if case_id == "SE1":
        match = _SEASON_NAME.search(layer)
        if match is None:
            raise FloodInputError(f"{layer}: the layer name gives no season window")
        window = ("-".join(match.group(1, 2, 3)), "-".join(match.group(4, 5, 6)))
        relation = temporal_relation(None, case.get("case_reference_date"), window_days=rules.recency_window_days, season_window=window)
        statements["not_an_observation_of_any_day"] = True
        statements["sensor_date_attribute"] = attributes.get("Sensor_Date")
        statements["season_window_note"] = (
            "The layer name gives 1 August to 12 October 2024; the product text and the layer's Sensor_Date attribute "
            "run to 22 October 2024. Whichever end date is right, the layer is a season window (protocol v1a, DR-A10)."
        )
        acquisition, timestamp = None, "/".join(window)
        common.append(
            "The layer holds every area mapped as water at some time in the season, with no date per patch. It is a "
            "scenario (lane SCN-ENV): every area is treated as flooded at once. It is not an observation of any day "
            "and not the water of September 2024."
        )
    else:
        match = _DATED_NAME.search(layer)
        acquisition = attributes.get("Sensor_Date")
        if match is None or acquisition != "-".join(match.group(1, 2, 3)):
            raise FloodInputError(f"{layer}: Sensor_Date {acquisition!r} is not the date in the layer name")
        window = None
        relation = temporal_relation(acquisition, case.get("case_reference_date"), window_days=rules.recency_window_days)
        statements["label"] = declared.get("label")
        statements["acquisition_time_precision"] = "date only; the layer gives no time of day"
        timestamp = str(acquisition)
        common.append(
            "The layer is dated 22 October 2024 and is its own case: late-season residual water. It is not a lower "
            "level of the September flood and does not describe the September event."
        )
    if relation != declared.get("temporal_relation"):
        raise FloodInputError(f"{layer}: the dates give {relation}, protocol v1a declares {declared.get('temporal_relation')}")
    if case.get("lane") != declared.get("lane", case.get("lane")):
        raise FloodInputError(f"{layer}: protocol v1a gives the case and the layer different lanes")
    return InputSpec(
        case_id=case_id,
        input_id=f"unosat_4009:{layer}",
        input_name=str(case["flood_inputs"][0]),
        lane=str(case["lane"]),
        tier=str(case["tier"]),
        case_reference_date=case.get("case_reference_date"),
        acquisition_date=acquisition,
        season_window=window,
        temporal_relation=relation,
        source_timestamp=timestamp,
        source={"layer": layer, "layer_attributes": dict(attributes),
                "archive": {key: archive[key] for key in ("file_name", "sha256", "bytes")}},
        geometry_kind="vector",
        confidence_basis=STANDARD_CONFIDENCE_BASIS_4009,
        assumptions=tuple(common),
        statements=MappingProxyType(statements),
    )


def load_product_4009(case_id: str, frames: Sequence[Frame], *, rules: FloodInputRules, registry: rights.RightsRegistry,
                      external_root: Path | str, water: PermanentWater | None = None,
                      footprint_layer: str | None = ANALYSIS_EXTENT_LAYER_4009, geodatabase: str = GEODATABASE_4009) -> FloodInput:
    """Load the product 4009 layer of case ``SE1`` or ``O2`` for the frames of the case.

    The rights registry is asked before any file is opened, and the archive must have the size and SHA-256 the
    rights record names. The credit of the record must be the credit protocol v1a states. The footprint layer
    is asked for separately and keeps its own grant: the registry holds it at ``local`` whatever the level of
    the flood layer (open points E1-OP1 and E1-OP10).

    Raises:
        floodguard.rights.RightsRefusedError: when the registry refuses the use or the archive differs.
        FloodInputError: see :func:`product_4009_spec` and :func:`read_product_layer`.
    """

    if case_id not in ("SE1", "O2"):
        raise FloodInputError(f"case {case_id!r} is not a product 4009 case")
    layer = str((rules.accumulated_layer if case_id == "SE1" else rules.layer_22_oct)["layer"])
    grant = registry.require_use(rights.PRODUCT_4009, layer=layer)
    if grant.attribution != rules.product_4009_credit:
        raise FloodInputError("the credit of the rights record is not the credit protocol v1a states")
    archive_path = registry.verify_source(grant, external_root)
    record, _sha256 = registry.read_record(rights.PRODUCT_4009)
    geometry, attributes = read_product_layer(archive_path, layer, geodatabase)
    spec = product_4009_spec(case_id, rules, attributes, record["archive"], str(record["product"]["event_code"]))
    footprint, footprint_grant = None, None
    if footprint_layer is not None:
        footprint_grant = registry.require_use(rights.PRODUCT_4009, layer=footprint_layer)
        footprint, _attributes = read_product_layer(archive_path, footprint_layer, geodatabase)
        spec = replace(spec, source=MappingProxyType({**spec.source, "footprint_layer": footprint_layer}))
    return build_flood_input(geometry, frames, spec=spec, rules=rules, grant=grant, footprint=footprint,
                             footprint_grant=footprint_grant, water=water)


def load_se1(frames: Sequence[Frame], **arguments: Any) -> FloodInput:
    """Load the flood input of case SE1: the product 4009 accumulated layer, the 2024 season envelope (SCN-ENV)."""

    return load_product_4009("SE1", frames, **arguments)


def load_o2(frames: Sequence[Frame], **arguments: Any) -> FloodInput:
    """Load the flood input of case O2: the product 4009 layer of 22 October 2024 (OBS, tier T3, its own dated case)."""

    return load_product_4009("O2", frames, **arguments)


# ---------------------------------------------------------------------------
# O1: an own radar candidate, delivered as a raster with a receipt
# ---------------------------------------------------------------------------


def read_candidate_raster(path: Path | str, encoding: Mapping[str, Any]) -> dict[str, Any]:
    """Read one level of a radar candidate: its flood cells, its cells with no answer and its grid.

    Raises:
        FloodInputError: when the raster is not one band of square cells in EPSG:32647, its nodata value is
            not the ``no_answer`` value of the receipt, or it holds a value outside the encoding.
    """

    import rasterio

    with rasterio.open(path) as source:
        if source.count != 1:
            raise FloodInputError(f"{Path(path).name}: a candidate raster has one band")
        if source.crs is None or source.crs.to_epsg() != ANALYSIS_EPSG:
            raise FloodInputError(f"{Path(path).name}: a candidate raster is delivered in {ANALYSIS_CRS}")
        transform = source.transform
        if transform.b != 0 or transform.d != 0 or abs(abs(transform.a) - abs(transform.e)) > 1e-9:
            raise FloodInputError(f"{Path(path).name}: a candidate raster has square, north-up cells")
        if source.nodata is None or source.nodata != encoding.get("no_answer"):
            raise FloodInputError(f"{Path(path).name}: the nodata value must be the no_answer value of the receipt")
        cells = source.read(1)
        no_answer = cells == source.nodata
        flood = cells == RADAR_FLOOD
        if np.any(~no_answer & ~flood & (cells != RADAR_NOT_FLOOD)):
            raise FloodInputError(f"{Path(path).name}: a cell is flood (1), not flood (0) or no answer")
        return {"flood": flood, "no_answer": no_answer, "transform": transform, "shape": cells.shape,
                "cell_m": float(abs(transform.a)), "bounds": tuple(source.bounds)}


def drop_small_polygons(flood: np.ndarray, transform: Any, *, minimum_px: int, connectivity: int) -> tuple[MultiPolygon, dict[str, int]]:
    """Polygonise flood cells and drop every polygon of fewer than ``minimum_px`` cells (the closure extent of a T2 raster).

    Protocol v1b, ``closure_rule_v1.parameters``: for T2 rasters, polygons under 5 pixels are dropped before
    intersection. The protocol does not say which cells form one polygon, so the neighbourhood is an argument
    (open point E1-OP6).

    Raises:
        FloodInputError: when the neighbourhood is not 4 or 8.
    """

    if connectivity not in (4, 8):
        raise FloodInputError("the neighbourhood of a raster polygon is 4 or 8; protocol v1b does not fix it (E1-OP6)")
    from scipy import ndimage

    structure = np.ones((3, 3), dtype=bool) if connectivity == 8 else None
    labels, count = ndimage.label(flood, structure=structure)
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    keep = sizes >= minimum_px
    keep[0] = False
    kept = keep[labels]
    polygons = _cell_polygons(kept, transform)
    extent = as_multipolygon(shapely.union_all(polygons)) if len(polygons) else MultiPolygon()
    return extent, {"polygons": int(count), "polygons_dropped": int(count - keep.sum()),
                    "cells_dropped": int(flood.sum() - kept.sum()), "minimum_px": int(minimum_px), "connectivity": int(connectivity)}


def load_o1(receipt_path: Path | str, frames: Sequence[Frame], *, rules: FloodInputRules, registry: rights.RightsRegistry,
            water: PermanentWater | None = None, closure_polygon_connectivity: int | None = None) -> FloodInput:
    """Load an own radar candidate of case O1 from its receipt and its raster or rasters.

    The receipt holds :data:`RADAR_RECEIPT_KEYS`. Every raster must have the SHA-256 the receipt names. With
    ``level_kind`` ``threshold`` the receipt names three rasters on one grid and the levels are those rasters;
    with ``one_pixel`` it names one raster of 20 m cells and the levels are the 20 m buffers of its polygonised
    flood cells (open point E1-OP5). The candidate is a T2 input: an own unqualified candidate, low confidence.

    Two things are not taken from the receipt alone. The kind of levels must be the kind protocol v1b states
    for the candidate (``t2_levels_by_input``). And the rights record must be a record of Sentinel-1 data,
    because protocol v1a says that is what the candidates of case O1 are made from: the receipt's
    ``rights_input_id`` chooses among such records, and a receipt that names the record of another source
    (the product 4009 record, for one) is refused before any raster is opened.

    Args:
        receipt_path: The candidate's receipt; raster paths are relative to it.
        frames: The frames of the case.
        rules: The parameters of the signed protocols.
        registry: The rights registry; the receipt's ``rights_input_id`` must be registered as a record of
            Sentinel-1 data (``floodguard.rights.SOURCE_SENTINEL1``) and the record must be confirmed.
        water: The permanent water of the reporting frame, when it was read.
        closure_polygon_connectivity: 4 or 8, to also build the closure extents with polygons under 5 pixels
            dropped; ``None`` builds none, because protocol v1b does not fix the neighbourhood.

    Raises:
        floodguard.rights.RightsRefusedError: when the registry refuses the use: no record is registered under
            the name, the record is not a record of Sentinel-1 data, or it is not confirmed.
        FloodInputError: for a receipt that lacks a key, names a candidate protocol v1a does not, declares
            another kind of levels than protocol v1b states for the candidate, was made under other protocol
            files, or a raster that differs from the receipt or from the interface.
    """

    receipt_file = Path(receipt_path)
    receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
    missing = [key for key in RADAR_RECEIPT_KEYS if key not in receipt]
    if missing:
        raise FloodInputError(f"the candidate receipt lacks: {', '.join(missing)}")
    if receipt["schema_version"] != RADAR_RECEIPT_SCHEMA:
        raise FloodInputError(f"the candidate receipt is not {RADAR_RECEIPT_SCHEMA}")
    case = rules.cases.get(str(receipt["case_id"]))
    if receipt["case_id"] != "O1" or case is None or receipt["candidate_id"] not in case["flood_inputs"]:
        raise FloodInputError(f"protocol v1a names no flood input {receipt['candidate_id']!r} for case {receipt['case_id']!r}")
    if receipt["official_warning"] is not False or receipt["operational_status"] != "non_operational":
        raise FloodInputError("a candidate receipt is non-operational and not an official warning")
    if receipt["confidence_class"] != "low" or not isinstance(receipt["assumptions"], list) or not receipt["assumptions"]:
        raise FloodInputError("a candidate receipt carries low confidence and its assumptions")
    named = {f"planning_protocol_{name}": rules.protocol_sha256.get(name) for name in normalisation.PROTOCOL_NAMES}
    if all(named.values()) and dict(receipt["protocol_sha256"]) != named:
        raise FloodInputError("the candidate was made under other protocol files than the ones in force")
    kind = receipt["level_kind"]
    wanted = set(LEVELS) if kind == THRESHOLD_LEVELS else {AS_PROVIDED} if kind == ONE_PIXEL_LEVELS else None
    if wanted is None or set(receipt["rasters"]) != wanted:
        raise FloodInputError("level_kind is threshold (three rasters) or one_pixel (the as_provided raster only)")
    stated = rules.o1_levels.get(str(receipt["candidate_id"]))
    if stated is None:
        raise FloodInputError(f"the rules hold no levels of protocol v1b for {receipt['candidate_id']!r}")
    if kind != stated["kind"]:
        raise FloodInputError(
            f"protocol v1b states the levels of {receipt['candidate_id']!r} as {stated['stated']!r} ({stated['kind']} "
            f"levels); the receipt declares level_kind {kind!r}")
    if O1_SOURCE_WORD not in str(case.get("input_acquisition", "")):
        raise FloodInputError("protocol v1a does not say that the candidates of case O1 are made from Sentinel-1 data, "
                              "so this code cannot say which rights record covers one")

    grant = registry.require_use(str(receipt["rights_input_id"]), source=rights.SOURCE_SENTINEL1)

    grids: dict[str, dict[str, Any]] = {}
    files: dict[str, Any] = {}
    for level, entry in receipt["rasters"].items():
        raster = receipt_file.parent / entry["path"]
        digest = sha256_file(raster)
        if digest != entry["sha256"]:
            raise FloodInputError(f"{raster.name} is not the raster the receipt names")
        grids[level] = read_candidate_raster(raster, receipt["encoding"])
        files[level] = {"file": raster.name, "sha256": digest, "bytes": raster.stat().st_size}
    reference = grids[AS_PROVIDED]
    if any(grid["transform"] != reference["transform"] or grid["shape"] != reference["shape"] for grid in grids.values()):
        raise FloodInputError("the three rasters of a candidate share one grid")

    def polygonise(mask: np.ndarray) -> tuple[MultiPolygon, dict[str, Any]]:
        return repair_product(_cell_polygons(mask, reference["transform"]), frames, source_crs=ANALYSIS_CRS, reach_m=rules.one_pixel_m)

    if kind == ONE_PIXEL_LEVELS:
        if abs(reference["cell_m"] - rules.one_pixel_m) > 1e-6:
            raise FloodInputError(f"a one-pixel candidate has {rules.one_pixel_m:g} m cells; this raster has {reference['cell_m']:g} m cells")
        extent, repair = polygonise(reference["flood"])
        states = one_pixel_levels(extent, rules.one_pixel_m)
        level_rule = LEVEL_RULE + " A raster is polygonised first and gets the same buffer (open point E1-OP5)."
    else:
        states, repair = {}, {}
        for level in LEVELS:
            states[level], level_repair = polygonise(grids[level]["flood"])
            repair[level] = level_repair
        repair = {"method": REPAIR_METHOD, "by_level": repair,
                  "parts_repaired": sum(entry["parts_repaired"] for entry in repair.values())}
        level_rule = (
            "Protocol v1b, ensemble_grid.core_axes (t2_levels_by_input): the three levels are the three rasters the "
            f"candidate's lane made ({receipt['level_parameter']}). No buffer is applied."
        )

    relation = temporal_relation(str(receipt["acquisition_date"]), case.get("case_reference_date"), window_days=rules.recency_window_days)
    grid_box = box(*reference["bounds"])
    no_answer, _repair = repair_product(_cell_polygons(reference["no_answer"], reference["transform"]), frames,
                                        source_crs=ANALYSIS_CRS, reach_m=0.0)
    coverage = {}
    for frame in frames:
        inside = float(shapely.intersection(grid_box, frame.geometry).area)
        unanswered = float(as_multipolygon(shapely.intersection(no_answer, frame.geometry)).area)
        coverage[frame.name] = {
            "grid_share_of_frame": round(inside / frame.area_m2, 6),
            "no_answer_share_of_frame": round(unanswered / frame.area_m2, 6),
            "answered_share_of_frame": round((inside - unanswered) / frame.area_m2, 6),
        }
    nested = bool(shapely.covers(states[AS_PROVIDED].buffer(COORDINATE_GRID_M), states[MINUS])
                  and shapely.covers(states[PLUS].buffer(COORDINATE_GRID_M), states[AS_PROVIDED]))
    spec = InputSpec(
        case_id="O1",
        input_id=f"own_radar_candidate:{receipt['candidate_id']}",
        input_name=str(receipt["candidate_id"]),
        lane=str(case["lane"]),
        tier=str(case["tier"]),
        case_reference_date=case.get("case_reference_date"),
        acquisition_date=str(receipt["acquisition_date"]),
        season_window=None,
        temporal_relation=relation,
        source_timestamp=str(receipt["source_timestamp"]),
        source={"receipt": {"file": receipt_file.name, "sha256": sha256_file(receipt_file)}, "rasters": files,
                "acquisition_time_utc": receipt["acquisition_time_utc"], "candidate_inputs": receipt["inputs"],
                "cell_m": reference["cell_m"]},
        geometry_kind="raster",
        confidence_basis="An own unqualified candidate (tier T2): low unless the T2 skill condition of protocol v1a "
                         "passes, which is not tested here. " + str(receipt["confidence_basis"]),
        assumptions=(
            "Flood cells are polygonised as their footprints in EPSG:32647. Cells with no answer are not flood and "
            "not dry: their share of each frame is reported.",
            *(str(line) for line in receipt["assumptions"]),
        ),
        statements=MappingProxyType({
            "own_candidate": True,
            "level_kind": kind,
            "level_parameter": receipt["level_parameter"],
            "levels_stated_by_protocol_v1b": stated["stated"],
            "level_rule": level_rule,
            "levels_nested": nested,
            "coverage": coverage,
        }),
    )
    built = build_flood_input(None, frames, spec=spec, rules=rules, grant=grant, water=water, levels=states, repair=repair)
    record = dict(built.record)
    closure: dict[str, dict[str, MultiPolygon]] = {}
    if closure_polygon_connectivity is None:
        record["closure_extents"] = {
            "built": False,
            "reason": "Protocol v1b drops polygons under "
                      f"{rules.raster_minimum_polygon_px} pixels from a T2 raster before intersection and does not say "
                      "which cells form one polygon (open point E1-OP6). Pass the neighbourhood to build them.",
        }
    else:
        by_level: dict[str, Any] = {}
        sources = grids if kind == THRESHOLD_LEVELS else {AS_PROVIDED: reference}
        for level, grid in sources.items():
            kept, counts = drop_small_polygons(grid["flood"], grid["transform"], minimum_px=rules.raster_minimum_polygon_px,
                                               connectivity=closure_polygon_connectivity)
            closure[level] = {frame.name: clip_to_frame(kept, frame) for frame in frames}
            by_level[level] = {**counts, "by_frame": {frame.name: geometry_summary(closure[level][frame.name]) for frame in frames}}
        record["closure_extents"] = {
            "built": True,
            "rule": "Protocol v1b, closure_rule_v1.parameters.raster_minimum_polygon_px: polygons under "
                    f"{rules.raster_minimum_polygon_px} pixels are dropped before intersection.",
            "levels_built": sorted(by_level),
            "by_level": by_level,
        }
    return FloodInput(spec, built.extents, built.footprints, record, MappingProxyType(closure))


# ---------------------------------------------------------------------------
# Writing and reading a layer
# ---------------------------------------------------------------------------


def encode_layer(geometry: BaseGeometry, properties: Mapping[str, Any], name: str) -> bytes:
    """Serialise one extent as a GeoJSON feature collection in EPSG:32647: ASCII, LF, one final newline.

    The file carries no generation time, so its bytes depend only on the inputs and the code. The coordinate
    system is named in the ``crs`` member, because the coordinates are metres and not longitude and latitude.

    Raises:
        FloodInputError: when the properties lack the source timestamp, the confidence or the assumptions.
    """

    for key in ("source_timestamp", "confidence_class", "confidence_basis", "assumptions", "official_warning", "operational_status"):
        if key not in properties:
            raise FloodInputError(f"a layer states its {key}")
    if properties["official_warning"] is not False or properties["operational_status"] != "non_operational":
        raise FloodInputError("a layer is non-operational and not an official warning")
    collection = {
        "type": "FeatureCollection",
        "name": name,
        "schema_version": LAYER_SCHEMA,
        "crs": {"type": "name", "properties": {"name": ANALYSIS_CRS_URN}},
        "features": [{"type": "Feature", "properties": dict(properties), "geometry": mapping(as_multipolygon(geometry))}],
    }
    return (json.dumps(collection, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def decode_layer(data: bytes) -> tuple[MultiPolygon, dict[str, Any]]:
    """Read a layer written by :func:`encode_layer`: its extent in EPSG:32647 and its properties.

    Raises:
        FloodInputError: when the bytes are not such a layer.
    """

    collection = json.loads(data.decode("ascii"))
    if collection.get("schema_version") != LAYER_SCHEMA or collection.get("crs", {}).get("properties", {}).get("name") != ANALYSIS_CRS_URN:
        raise FloodInputError(f"not a {LAYER_SCHEMA} layer in {ANALYSIS_CRS}")
    features = collection.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise FloodInputError("a flood-input layer holds one feature")
    return as_multipolygon(shape(features[0]["geometry"])), dict(features[0]["properties"])


def layer_properties(flood_input: FloodInput, *, level: str | None, frame: Frame, what: str, change: str) -> dict[str, Any]:
    """Return the properties one written layer carries: what it is, its rights, its change notice and its record fields.

    A layer carries the rights of the layer it comes from: an extent those of the flood layer, a footprint
    those of the footprint layer, which the registry can hold at a lower level. Its change notice counts the
    repaired parts that are in the layer (:func:`repair_count_of_layer`).

    Args:
        flood_input: The input the layer belongs to.
        level: ``minus``, ``as_provided`` or ``plus`` for an extent; ``None`` for a footprint.
        frame: The frame the layer is clipped to.
        what: ``flood_extent`` or ``product_footprint``.
        change: What the layer changed besides the clip, the repair and the projection.

    Raises:
        FloodInputError: when ``what`` is neither, a footprint is asked for of an input that has none, or the
            level does not go with ``what``.
    """

    record = flood_input.record
    if what not in (FLOOD_EXTENT, PRODUCT_FOOTPRINT) or (what == FLOOD_EXTENT) != (level in LEVELS) or (
            what == PRODUCT_FOOTPRINT and level is not None):
        raise FloodInputError("a layer is a flood extent at one of the three levels, or a product footprint with no level")
    if what == PRODUCT_FOOTPRINT and not record.get("footprint"):
        raise FloodInputError("the input has no product footprint")
    rights_record = record["rights"] if what == FLOOD_EXTENT else record["footprint"]["rights"]
    repair = record["repair"] if what == FLOOD_EXTENT else record["footprint"]["repair"]
    repaired = repair_count_of_layer(repair, frame=frame.name, level=level)
    properties = {
        "layer_schema": LAYER_SCHEMA,
        "what": what,
        "case_id": record["case_id"],
        "input_id": record["input_id"],
        "input_name": record["input_name"],
        "lane": record["lane"],
        "tier": record["tier"],
        "temporal_relation": record["temporal_relation"],
        "case_reference_date": record["case_reference_date"],
        "acquisition_date": record["acquisition_date"],
        "season_window": record["season_window"],
        "level": level,
        "frame": frame.name,
        "frame_label": frame.label,
        "source_timestamp": record["source_timestamp"],
        "confidence_class": record["confidence_class"],
        "confidence_basis": record["confidence_basis"],
        "assumptions": list(record["assumptions"]),
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
        "licence": rights_record["licence"],
        "credit": rights_record["attribution"],
        "rights_level": rights_record["rights_level"],
        "rights_level_basis": rights_record["rights_level_basis"],
        "rights_layer": rights_record["layer"],
        "rights_record": {"path": rights_record["record_path"], "sha256": rights_record["record_sha256"]},
        "change_notice": change_notice(
            clip_geometry=frame.label, repair_count=repaired, change=change, credit=rights_record["attribution"],
            licence_name=rights_record["licence"]["name"], geometry_kind=record["geometry_kind"],
            source_crs=WGS84_CRS if record["geometry_kind"] == "vector" else ANALYSIS_CRS),
        "protocol_sha256": record["protocol_sha256"],
    }
    for key in ("standard_sentence", "used_as_provided", "field_validation", "not_an_observation_of_any_day", "label"):
        if key in record:
            properties[key] = record[key]
    if rights_record["share_alike"]:
        properties["share_alike"] = rights_record["share_alike"]
    if not season_envelope.credit_holders(properties["credit"]):
        raise FloodInputError("a layer names the holders of its source")
    return properties


def file_entry(name: str, data: bytes, **what: Any) -> dict[str, Any]:
    """Describe one written file of an input for its record: its name, its SHA-256, its size and what it is."""

    return {"file": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), **what}


def read_written_input(folder: Path | str) -> tuple[dict[str, Any], dict[str, dict[str, MultiPolygon]]]:
    """Read back one written input: its record, and its extents by level and frame in EPSG:32647.

    The folder holds :data:`INPUT_RECORD_NAME` and the layers it lists under ``files``. Every listed file must
    be there with the SHA-256 the record names, so a later stage reads the bytes the run receipt binds.

    Raises:
        FloodInputError: when the record is not an input record, or a file is missing, differs from the
            record or does not say the level and frame the record gives it.
    """

    base = Path(folder)
    record_path = base / INPUT_RECORD_NAME
    if not record_path.is_file():
        raise FloodInputError(f"no {INPUT_RECORD_NAME} in {base.name}")
    record = json.loads(record_path.read_text(encoding="ascii"))
    if record.get("schema_version") != INPUT_RECORD_SCHEMA or not isinstance(record.get("files"), list):
        raise FloodInputError(f"{INPUT_RECORD_NAME} is not a {INPUT_RECORD_SCHEMA} record with its files")
    extents: dict[str, dict[str, MultiPolygon]] = {level: {} for level in LEVELS}
    for entry in record["files"]:
        path = base / entry["file"]
        if not path.is_file():
            raise FloodInputError(f"{entry['file']} is listed in the record and is not in the folder")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise FloodInputError(f"{entry['file']} is not the file the record names")
        if entry.get("what") != "flood_extent":
            continue
        geometry, properties = decode_layer(data)
        named = (entry["level"], entry["frame"], record["input_id"])
        if (properties.get("level"), properties.get("frame"), properties.get("input_id")) != named:
            raise FloodInputError(f"{entry['file']} does not say the level, frame and input the record gives it")
        extents[entry["level"]][entry["frame"]] = geometry
    if any(not extents[level] for level in LEVELS):
        raise FloodInputError("the record does not list an extent for each of the three levels")
    return record, extents
