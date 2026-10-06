"""Radar flood candidates of case O1 over the eight Mae Sai tambons (plan tasks A2 and A4).

One run reads the local Sentinel-1 pair on relative orbit 135 (3 September
2024, 23:16 UTC, and 15 September 2024, 23:16 UTC, which is 16 September
06:16 in Thailand) and writes three own candidates of tier T2 for the eight
tambons of protocol v1a (``case_portfolio.mae_sai_reporting_frame``):

* the UN-SPIDER recommended practice with its ratio of 1.25, untuned (A2);
* M1-literal and the frozen M1-v2 of ``floodguard.sar_change_v2`` (A4).

For each method and each tambon it reports coverage, the share of cells
without an answer, the candidate extent and its area, and for the frozen
M1-v2 the three Mae Sai conditions of the T2 skill bar of protocol v1a.

It computes no FPPS, no A-E class and no ensemble. A candidate is not an
observation of a flood and never a warning; nothing here is checked against
a reference. In particular no candidate is compared with UNOSAT/GISTDA
product 4009 (guardrail GR4).

Radiometry and geocoding follow the fallback of plan row A4, because SNAP is
not installed: the ``sigmaNought`` look-up table of the SAFE annotation is
applied and the result is warped with the product's ground control points
(``floodguard.sentinel1_sigma0``). The uncalibrated amplitude is never used.

That geocoding displaces the radar layers by several hundred metres at Mae
Sai, for two reasons that add up: the control points sit at the heights of a
coarse terrain model, above the Mae Sai plain, and GDAL's control-point
polynomial (second order for these products, not an affine fit) does not
pass through the control points. Each date has its own polynomial, so the
two images of the run of record are also offset from each other. Each run
measures all of this (``geolocation_check``). A second run,
``--geocoding annotation_grid_with_cell_height``, repeats the three methods
with a mapping that uses a DEM height for every cell. It is a sensitivity
run and not in the plan: the run of record is the plan's fallback, and the
owners decide whether the second geocoding may replace it.

Run it from the repository root. Every input is a read-only file outside
Git, under the external data root::

    python scripts/build_mae_sai_radar_candidates.py --external-data <root>

``--external-data`` defaults to the environment variable
``FLOODGUARD_EXTERNAL_DATA``. The rasters are written outside Git, under
``<root>/proposal_execution/planning_v1/o1_mae_sai/``. The table and its
receipt are written to ``outputs/planning_v1/``.

Every run is reported. The script refuses to run unless protocol v1a and v1b
are in force and the frozen M1-v2 is unchanged
(``floodguard.geoid_m1_review.require_frozen_m1_v2``), and it refuses to
overwrite a table. A second run needs ``--replace --reason "<why>"``; its
receipt names the table and the receipt it supersedes by SHA-256.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import confidence  # noqa: E402
from floodguard import geoid_m1_review as review  # noqa: E402
from floodguard import radar_candidates as rc  # noqa: E402
from floodguard import sar_change_v2 as sar  # noqa: E402
from floodguard import sentinel1_sigma0 as s1  # noqa: E402
from floodguard.normalisation import read_protocol_in_force  # noqa: E402

TABLE_SCHEMA = "floodguard.radar_candidates.v1"
RECEIPT_SCHEMA = "floodguard.radar_candidates_run_receipt.v1"
DOCS = ROOT / "docs" / "proposal_execution"
OUTPUT_DIR = ROOT / "outputs" / "planning_v1"
EXTERNAL_DATA_VARIABLE = "FLOODGUARD_EXTERNAL_DATA"
EXTERNAL_LABEL = "<external_data_workspace>"
CASE_FOLDER = Path("proposal_execution") / "planning_v1" / "o1_mae_sai"
# The run of record is the fallback of plan row A4. The second geocoding is a sensitivity run that the plan
# does not name; it never replaces the run of record without an owner decision. This was fixed before any
# candidate was computed, with only the displacement of the pre-event image in view.
RUN_OF_RECORD = "run_of_record_plan_fallback"
SENSITIVITY_RUN = "sensitivity_run_not_in_the_plan"
HEIGHT_AWARE_LABEL = "sensitivity geocoding, not in the plan: annotation grid with a DEM height for every cell"
# No file name holds the word "candidate": tests/test_planning_v1_outputs.py reserves it for the corridor
# candidates of the E0 spike.
GEOCODINGS: dict[str, dict[str, Any]] = {
    s1.GEOCODING_GCP_POLYNOMIAL: {
        "role": RUN_OF_RECORD,
        "label": s1.PLAN_FALLBACK_LABEL,
        "table": "radar_o1_mae_sai_v1.json",
        "receipt": "radar_o1_mae_sai_v1_receipt.json",
        "raster_folder": CASE_FOLDER / "radar_o1_v1",
    },
    s1.GEOCODING_HEIGHT_AWARE: {
        "role": SENSITIVITY_RUN,
        "label": HEIGHT_AWARE_LABEL,
        "table": "radar_o1_mae_sai_v1_height_aware_sensitivity.json",
        "receipt": "radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json",
        "raster_folder": CASE_FOLDER / "radar_o1_v1_height_aware_sensitivity",
    },
}
SUPERSEDED_FOLDER = CASE_FOLDER / "radar_o1_superseded_runs"
REGISTER_PREFIX = "a2_a4_"
TABLE_NAME = GEOCODINGS[s1.GEOCODING_GCP_POLYNOMIAL]["table"]
RECEIPT_NAME = GEOCODINGS[s1.GEOCODING_GCP_POLYNOMIAL]["receipt"]
GEOID_SUMMARY = ROOT / "outputs" / "geoid_m1_benchmark_v2_summary.json"
RESULT_DOCUMENT = "docs/proposal_execution/automated_track/MAE_SAI_RADAR_CANDIDATES_RESULT.md"
GEOID_DERIVED_CHECKS = ROOT / "outputs" / "geoid_m1_benchmark_v2_derived_checks.json"

PLAN_TASK = "A2 (UN-SPIDER reproduction) and A4 (M1-literal and M1-v2 on the eight-tambon union)"
CASE_ID = "O1"
LANE = "OBS"
TIER = "T2"
GRID_CRS = "EPSG:32647"
LOCAL_TIME_OFFSET_HOURS = 7  # Indochina Time, UTC+7.
BOUNDARY_LAYER = "tha_admin3"
UNIT_ID_FIELD = "adm3_pcode"
UNIT_NAME_FIELD = "adm3_name"
PERMANENT_WATER_CLASS = 80  # ESA WorldCover 2021 v200 (protocol v1a, flood_likelihood_0_100.permanent_water).
JRC_PERENNIAL_MONTHS = 10  # The practice's own layer: JRC seasonality of 10 months or more.
JRC_NO_DATA = 255
DEM_SLOPE_BLOCK = 3  # GLO-30 cells averaged to the 3 arc-second spacing of the practice's DEM.
SLOPE_CLASS_EDGES = (5.0, 10.0, 20.0)
DISPLACEMENT_SEARCH_CELLS = 120
PAIR_SEARCH_CELLS = 20
# The sub-cell estimate of the offset between the two dates is itself good to a metre or two (on the synthetic
# pair of the tests, which has no offset, it reads up to 1 m). Below this size an offset is worded as agreement.
PAIR_AGREEMENT_M = 2.0
DISPLACEMENT_MIN_WATER_CELLS = 2000
DISPLACEMENT_LATTICE_STEP = 8
# No geoid model is on disk. The annotation does not say whether its heights are above the ellipsoid or above
# sea level, so the displacement check is made under both readings. The geoid height near Mae Sai is taken as
# about -35 m; it moves the result by about 5 cells. The sensitivity run uses the second reading: on the
# pre-event image it left 10 m of measured displacement against permanent water, the first one 60 m. That
# was seen in a check of the inputs that computed no change image and no candidate.
HEIGHT_DATUM_READINGS = {
    "annotation_heights_and_dem_share_one_datum": 0.0,
    "annotation_heights_are_ellipsoidal_and_dem_is_above_the_geoid": -35.0,
}
HEIGHT_AWARE_DATUM_READING = "annotation_heights_are_ellipsoidal_and_dem_is_above_the_geoid"
WORLDCOVER_CLASSES = {
    10: "tree_cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built_up",
    60: "bare_or_sparse_vegetation", 80: "permanent_water", 90: "herbaceous_wetland",
}
INPUT_FILES = {
    "pre_safe": "sentinel1_original_safe/S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_055507_06C5C9_72F7.SAFE.zip",
    "post_safe": "sentinel1_original_safe/S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_055682_06CCBA_08DA.SAFE.zip",
    "acquisition_manifest": "sentinel1_original_safe/cdse_mae_sai_acquisition_manifest.csv",
    "boundaries": "open_context/hdx_cod_ab/tha_admin_boundaries.gdb.zip",
    "worldcover": "open_context/esa_worldcover/ESA_WorldCover_10m_2021_v200_N18E099_Map.tif",
    "dem_west": "open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E099_00_DEM.tif",
    "dem_east": "open_context/copernicus_dem_glo30/Copernicus_DSM_COG_10_N20_00_E100_00_DEM.tif",
    "jrc_seasonality": "open_context/jrc_global_surface_water/seasonality_90E_30Nv1_4_2021.tif",
}

COMPUTES = (
    "Radar flood candidates of tier T2 for the eight Mae Sai tambons, with coverage, cells without an answer, "
    "candidate area, validity layers and threshold levels. No FPPS, no A-E class and no ensemble."
)
CONFIDENCE_BASIS = (
    "Own unqualified candidates of tier T2 from one Sentinel-1 pair, with no terrain correction by a "
    "qualified processor and no reference of any kind. Nothing here was checked against a flood map."
)
REQUIRED_STATEMENT_A2 = (
    "Reproduces UN-SPIDER practice; {area} km2 of residual water at 16 Sep 06:16 ICT; "
    "the published 93.38% OA does not transfer"
)
# The outcome of the T2 skill bar for an input, as a later lane may read it. Protocol v1a: "A T2 input is low
# confidence unless all four conditions pass." It does not say whether the two Mae Sai conditions are taken per
# tambon or for the frame (open point A4-OP3), so a pass that holds for one tambon only is never written as a
# pass: it is listed under PER_UNIT_KEY and the outcome says that the reading is undecided.
OUTCOME_MET = "met"
OUTCOME_NOT_MET = "not_met"
OUTCOME_UNDECIDED = "undecided"
PER_UNIT_KEY = "units_passing_only_if_the_conditions_are_read_per_unit"
PER_UNIT_PASS_KEY = "passes_if_read_per_unit"
PER_UNIT_UNDECIDED = "undecided (open point A4-OP3)"
PER_UNIT_NOT_APPLICABLE = "not_applicable (protocol v1a declares this input unable to meet the bar)"
PER_UNIT_SAME = "same_as_the_outcome (every reading gives the same answer for every tambon)"
R15_CAVEATS = [
    "The GEOID result (0.411) is not distinguishable from 0.40 on 14 tiles.",
    "67.9% of the GEOID test cells had no answer.",
    "The GEOID figure measures agreement with a same-pass CEMS map, not an independent check.",
]
ASSUMPTIONS = [
    "One image pair: 3 September 2024 23:16 UTC and 15 September 2024 23:16 UTC (16 September 06:16 in "
    "Thailand), both descending on relative orbit 135. The post-event image is 12 days after the pre-event "
    "image and several days after the flood peak, so a candidate is residual water at that pass at most.",
    "Sigma0 comes from the digital numbers and the sigmaNought look-up table of the SAFE annotation. Thermal "
    "noise is not removed and no orbit file is applied.",
    "{geocoding}",
    "Linear sigma0 is resampled bilinearly to a 10 m grid in EPSG:32647. Resampling changes the speckle "
    "statistics; the speckle filters still assume 4.4 looks, as frozen.",
    "A cell belongs to the tambon that holds its centre (2022 COD-AB tha_admin3 polygons). Areas are cell "
    "counts times 100 m2 on the EPSG:32647 grid.",
    "M1-literal and M1-v2 are run one tile at a time on the lattice of the GEOID sample (1024 by 1024 cells "
    "of 10 m, corners at multiples of 10,240 m), because M1-v2 was frozen on such tiles and declines a whole "
    "tile at a time. A tile holds everything inside it, including land outside the eight tambons.",
    "Permanent water is ESA WorldCover 2021 class 80 (protocol v1a). The slope layer is Copernicus GLO-30 "
    "averaged to 3 arc-seconds, in place of the HydroSHEDS DEM of the UN-SPIDER practice.",
    "{alignment}",
]
GEOCODING_ASSUMPTIONS = {
    s1.GEOCODING_GCP_POLYNOMIAL: {
        "geocoding": "Geocoding is the product's ground control points fitted by GDAL's GCP polynomial{order}, "
                     "each date with its own fit and with no terrain model (plan row A4 fallback). Cells are "
                     "displaced along the radar range direction and the two dates are offset from each other; "
                     "geolocation_check gives the measured displacement, its two parts and the offset.",
        "alignment": "The context layers (tambons, land cover, slope) are in map geometry. The radar layers "
                     "are displaced, so a mask or a tambon boundary does not meet the radar cell it was "
                     "meant for.",
    },
    s1.GEOCODING_HEIGHT_AWARE: {
        "geocoding": "Geocoding uses the geolocation grid of the product annotation with the Copernicus GLO-30 "
                     "height of every cell, taken as 35 m lower above the ellipsoid than above the geoid. "
                     "This mapping is not in the plan and is not SNAP terrain correction: it has no orbit "
                     "file, and layover and shadow are not handled. geolocation_check gives the displacement "
                     "it leaves.",
        "alignment": "The context layers (tambons, land cover, slope) are in map geometry, and the radar "
                     "layers meet them to within about a cell where the terrain is gentle.",
    },
}


def polynomial_order_clause(orders: Sequence[int | None]) -> str:
    """Words for the order of the control-point polynomial that was found for each date."""

    found = set(orders)
    if len(found) != 1 or None in found:
        return " (GDAL chooses the order; see geolocation_check.gcp_polynomial)"
    order = next(iter(found))
    if order == 1:
        return " (order 1, an affine fit: GDAL's own choice)"
    return f" (order {order}: GDAL's own choice, not an affine fit)"


def assumptions_for(geocoding: str, orders: Sequence[int | None] = (None,)) -> list[str]:
    """The assumptions of a run with the sentences that depend on its geocoding filled in.

    ``orders`` are the orders of the control-point polynomial found for the
    two dates (``geolocation_check.gcp_polynomial``).
    """

    filled = {key: text.replace("{order}", polynomial_order_clause(orders))
              for key, text in GEOCODING_ASSUMPTIONS[geocoding].items()}
    return [line.format(**filled) if line.startswith("{") else line for line in ASSUMPTIONS]


def pair_offset_words(pair: Mapping[str, Any]) -> tuple[bool, str]:
    """Say how far the pre-event image lies from the post-event image, from the measured sub-cell offset.

    Returns whether the two images agree to within ``PAIR_AGREEMENT_M``, and the words.
    """

    east, north = float(pair["east_m_subcell"]), float(pair["north_m_subcell"])
    if max(abs(east), abs(north)) < PAIR_AGREEMENT_M:
        return True, f"to within {PAIR_AGREEMENT_M:g} m"
    return False, (f"about {abs(east):.0f} m {'east' if east >= 0 else 'west'} and about {abs(north):.0f} m "
                   f"{'north' if north >= 0 else 'south'}")


def limits_for(pair: Mapping[str, Any], of_record: bool = True) -> list[str]:
    """The limits of a run, with the measured offset between its two images."""

    agree, words = pair_offset_words(pair)
    if agree:
        offset = (f"The two images of this run agree with each other {words} "
                  "(geolocation_check.pre_against_post, a sub-cell estimate)."
                  + ("" if of_record else " The run of record states its own offset in its table."))
    else:
        offset = (f"The two images of this run are not registered to each other: the pre-event content lies "
                  f"{words} of the post-event content (geolocation_check.pre_against_post, a sub-cell estimate; "
                  "a cell is 10 m). Each date is warped with its own control-point polynomial. All three methods "
                  "compare the two dates cell by cell, so the offset adds change that is not on the ground "
                  "wherever the backscatter has an edge. What that does to the candidates was not measured.")
    return [*LIMITS[:2], offset, *LIMITS[2:]]


def pair_offset_difference_from_geoid(pair: Mapping[str, Any]) -> str:
    """The sentence on the offset between the two dates for ``disclosed_differences_from_geoid``."""

    agree, words = pair_offset_words(pair)
    tail = ("The two dates of a GEOID tile came on one grid from their publisher; the offset between them was "
            "not measured here.")
    if agree:
        return (f"The two dates of this run agree with each other {words} "
                f"(geolocation_check.pre_against_post). {tail}")
    return (f"The two dates of this run are offset from each other: the pre-event content lies {words} of the "
            "post-event content (geolocation_check.pre_against_post), because each date is warped with its own "
            f"control-point polynomial. M1-v2 compares the dates cell by cell. {tail}")
LIMITS = [
    "One pair of images, twelve days apart. The second was taken on 16 September 2024 at 06:16 in Thailand, "
    "several days after the flood peak: residual water only. Nothing here describes the peak.",
    "Approximate geocoding in the run of record: no cell-level or road-level use until the displacement is "
    "removed. The sensitivity run removes most of it with a mapping the plan does not name.",
    "No qualified reference exists for Mae Sai. The layers are not validated, and no figure here says how "
    "correct a layer is.",
    "Tier 2 own candidates: verify before action.",
    "Radar shadow and layover are not flagged; that needs the terrain-corrected geometry of the SNAP path.",
    "Urban areas, wet soil, crops that changed between the two dates and wind on water all change the "
    "backscatter. A candidate cell is a cell that became darker, not a cell that was seen under water.",
    "The UN-SPIDER practice divides one dB value by another. Where the smoothed pre-event VH is above 0 dB "
    "(a few very bright cells) its quotient means the opposite of what it means elsewhere.",
]
NOT_COMPUTED = [
    "FPPS", "A-E class", "would-be class", "ensemble cell", "exposure", "road closure", "access loss",
    "confidence class of a unit", "any comparison with UNOSAT/GISTDA product 4009", "A6-prime classifier",
    "M1-v2 Otsu comparator", "HAND or slope mask for M1-literal and M1-v2",
    "minus and plus one-pixel levels of the UN-SPIDER reproduction (protocol v1b, ensemble_grid)",
    "the effect of the offset between the two dates on the candidates",
    "the displacement of the replay's Sentinel-1 layers",
]
OPEN_POINTS = [
    {
        "id": "A4-OP1",
        "point": "Geocoding of the fallback path: the displacement, its two parts, and the offset between the "
                 "two dates.",
        "protocol_says": "Plan row A4: without SNAP, a GCP warp with the sigmaNought table, labelled "
                         "'approximate geocoding: GCP affine, no DEM terrain correction'.",
        "what_this_run_does": "The run of record warps each date with GDAL's control-point polynomial. The radar "
                              "layers are displaced along the range direction, for two reasons that add up "
                              "(geolocation_check.expected_from_geometry, parts). First, the control points sit "
                              "at the heights of a coarse terrain model, above the Mae Sai plain. Second, the "
                              "polynomial does not pass through the control points "
                              "(geolocation_check.gcp_polynomial). Each date has its own polynomial, so the two "
                              "images of the run of record are also offset from each other "
                              "(geolocation_check.pre_against_post gives the measured offset). All three "
                              "methods compare the dates cell by cell; what the offset does to the candidates "
                              "was not measured. The three "
                              "methods were run a second time with a mapping that uses a height per cell, as a "
                              "sensitivity run with its own table and receipt; it replaces nothing.",
        "for_the_owners": "Which layers case O1 uses: the run of record (the plan's fallback: displaced, and its "
                          "two dates offset from each other), the sensitivity run (a mapping the plan does not "
                          "name), a warp that passes through the control points (it would take away the "
                          "polynomial part and should take away the offset between the dates, but not the "
                          "height part; the plan does not name it and it was not run), or a SNAP terrain "
                          "correction once SNAP is installed.",
    },
    {
        "id": "A4-OP2",
        "point": "HAND and slope mask for M1-v2 on Mae Sai.",
        "protocol_says": "Protocol v1a (geoid_split.limits): 'M1-v2 is fixed slope-free on GEOID and the "
                         "HAND/slope mask is applied on Mae Sai as a disclosed difference.' No HAND source, "
                         "no HAND limit and no slope limit is given, and the proposal's 'steep terrain' has "
                         "no number either.",
        "what_this_run_does": "Applies no HAND or slope mask to M1-literal or M1-v2: both are run as they "
                              "were on GEOID. The candidate area of each method is reported by slope class "
                              "so that a limit can be chosen with the figures in view of everyone.",
        "for_the_owners": "The HAND source and limit and the slope limit, or a decision to leave the mask out.",
    },
    {
        "id": "A4-OP3",
        "point": "Which coverage the 0.80 condition means, and over what the 0.20 condition is taken.",
        "protocol_says": "v1a C3: 'unit valid coverage inside the product footprint or analysis extent'. "
                         "v1a t2_skill_bar: 'mae_sai_abstention_fraction_max 0.2' and "
                         "'mae_sai_unit_coverage_min 0.8'. Neither says whether coverage is valid radar "
                         "input or cells with an answer, nor whether abstention is per unit or for the frame.",
        "what_this_run_does": "Reports both coverage readings per unit and the abstention share per unit "
                              "and for the frame, and evaluates the conditions under each reading.",
        "for_the_owners": "The reading of record.",
    },
    {
        "id": "A4-OP4",
        "point": "Permanent water in M1-literal and M1-v2.",
        "protocol_says": "Proposal Method 1, step 5: 'Remove permanent water and steep terrain'. v1a fixes "
                         "permanent water as WorldCover class 80 for the scoring frame. Neither says that "
                         "the candidate raster itself is cut.",
        "what_this_run_does": "Leaves the candidate rasters as the frozen functions return them and gives "
                              "every area twice: all candidate cells, and candidate cells outside class 80.",
        "for_the_owners": "Whether the flood-input reader removes class 80 or the candidate raster does.",
    },
    {
        "id": "A4-OP6",
        "point": "How M1-literal and M1-v2 are tiled on Mae Sai.",
        "protocol_says": "Nothing. M1-v2 was frozen on GEOID tiles of 1024 by 1024 cells of 10 m and declines a "
                         "whole tile at a time; the protocol does not say how a frame that is not made of such "
                         "tiles is cut.",
        "what_this_run_does": "Uses the lattice of the GEOID sample in UTM zone 47N (tile corners at multiples "
                              "of 10,240 m). Nine tiles hold part of the frame. Each tile is run whole, with "
                              "the land outside the eight tambons that it holds, and the result is cut to the "
                              "frame afterwards. Another lattice origin would give other tiles and could give "
                              "other declined tiles; none was tried.",
        "for_the_owners": "To confirm the lattice, or to state another tiling rule.",
    },
    {
        "id": "A2-OP1",
        "point": "Layers of the UN-SPIDER practice that are not on disk.",
        "protocol_says": "Plan row A2: 'UN-SPIDER recommended practice, ratio 1.25, untuned', on the local "
                         "3/15 September pair. The practice masks JRC seasonality of 10 months or more and "
                         "slopes from the HydroSHEDS 3 arc-second DEM, on terrain-corrected Earth Engine "
                         "backscatter with thermal noise removed.",
        "what_this_run_does": "Uses WorldCover class 80 for perennial water (the JRC tile on disk ends at "
                              "100 E and the frame reaches 100.04 E) and Copernicus GLO-30 averaged to 3 "
                              "arc-seconds for the slope. The JRC result on the part of the frame the tile "
                              "covers is given as a sensitivity note. No copy of the practice's script is in "
                              "the repository: its steps were written from the published script as the "
                              "agent knows it and need a check by the GeoAI owner.",
        "for_the_owners": "A check of UnSpiderConfig against the published script; whether to download the "
                          "JRC tile 100E_30N (decision D11 stops downloads).",
    },
    {
        "id": "A4-OP5",
        "point": "The 3 September SAFE in the July acquisition manifest.",
        "protocol_says": "The manifest marks both SAFE files 'processing_allowed False: reference mask "
                         "status remains unresolved; do not run baseline yet'. Decision R14 says that note "
                         "gates the finals baseline, not rights, and allows the replay to read the file. "
                         "Plan rows A2 and A4 name this pair.",
        "what_this_run_does": "Reads both files, as the plan rows say.",
        "for_the_owners": "To confirm that R14 covers plan tasks A2 and A4 as well as the replay.",
    },
    {
        "id": "A4-OP7",
        "point": "The label says 'GCP affine'; the warp that ran is not affine.",
        "protocol_says": "Plan row A4 gives the label 'approximate geocoding: GCP affine, no DEM terrain "
                         "correction' for the GCP warp. It says nothing else about the transform: no polynomial "
                         "order, and no word on whether each date is fitted on its own.",
        "what_this_run_does": "Warps each date with GDAL's control-point polynomial and asks for no order, as "
                              "the replay's bake does. GDAL then chooses the order itself and does not report "
                              "it. geolocation_check.gcp_polynomial gives the order found for each date and how "
                              "far an affine fit lies from it. The label is kept word for word, because the "
                              "plan prescribes it; it names a transform that was not run.",
        "for_the_owners": "Whether the label is reworded to name the transform that ran, or the warp is rerun "
                          "as an affine fit so that the label is true (a new run; none was made), and whether "
                          "the order is fixed in the code and no longer left to GDAL.",
    },
    {
        "id": "A4-OP8",
        "point": "The Sentinel-1 layers of the replay are made with the same warp.",
        "protocol_says": "Nothing. Neither protocol and no plan row speaks of the geocoding of the replay's "
                         "Sentinel-1 layers.",
        "what_this_run_does": "Nothing to the replay. scripts/build_mae_sai_flood_timeline.py (sentinel1_vv) "
                              "reads the 3 September archive this run reads and copies of the 6 and 15 "
                              "September passes, and warps each with the same call: the product's control "
                              "points, moved into the image window, fitted by GDAL's polynomial. The "
                              "displacement measured here was not measured on the replay's layers, and the "
                              "replay's bake was not changed or rerun in this lane. That its layers are "
                              "displaced by a similar distance is an inference from the identical warp, not a "
                              "measurement.",
        "for_the_owners": "For the owners of the replay: to measure the displacement of its Sentinel-1 layers "
                          "against mapped permanent water, and to decide what the page changes or says if the "
                          "displacement is there.",
    },
    {
        "id": "A4-OP9",
        "point": "The +1 dB level of M1-literal is cut at 0 dB.",
        "protocol_says": "Protocol v1b (ensemble_grid, t2_levels_by_input): 'M1-literal: Otsu threshold -1 / 0 / "
                         "+1 dB', accepted by the owners 'as a default and nothing more'. It does not say what "
                         "happens to the second clause of the rule (delta-VH below 0 dB) when the threshold "
                         "is moved.",
        "what_this_run_does": "Moves the Otsu threshold and keeps the second clause, so a moved threshold above "
                              "0 dB is cut at 0 dB. Each tile says what took effect (threshold_levels in its "
                              "whole_tile block), and methods.m1_literal.threshold_levels.upper_level lists the "
                              "tiles. Where the Otsu threshold is 0 dB or more, the +1 dB level is the central "
                              "level again. The band is therefore narrower above the central level than below "
                              "it by construction, not because of the data.",
        "for_the_owners": "Whether the +1 dB level keeps the below-zero clause (as here), drops it, or is "
                          "defined another way. The ensemble lane reads these levels as the flood-state axis "
                          "of M1-literal.",
    },
    {
        "id": "A2-OP2",
        "point": "The minus and plus levels of the UN-SPIDER reproduction are not written.",
        "protocol_says": "Protocol v1b (ensemble_grid, t2_levels_by_input): 'UN-SPIDER reproduction: minus / "
                         "as-provided / plus one pixel on the output extent; the ratio 1.25 is not tuned', with "
                         "20 m for the minus and the plus level (owner choice 2). It does not say how 20 m is "
                         "taken on a 10 m raster (two cells, and in which neighbourhood), nor whether the "
                         "candidate builder or the flood-input reader makes the two levels. Plan row A2 asks "
                         "for the area and the statement.",
        "what_this_run_does": "Writes the as-provided extent only (un_spider_candidate.tif) and lists the two "
                              "levels under not_computed.",
        "for_the_owners": "Who makes the two levels, and with which neighbourhood.",
    },
]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    """Return the current UTC time to the second, as the receipts write it."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file as lowercase hex."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def encode(payload: Mapping[str, Any]) -> bytes:
    """Serialise a table or a receipt: two-space indent, ASCII, LF, one final newline."""

    return (json.dumps(payload, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def repo_label(path: Path, root: Path) -> str:
    """Return a path relative to the repository."""

    return path.resolve().relative_to(root.resolve()).as_posix()


def external_label(relative: str | Path) -> str:
    """Name a file under the external data root without the local path of that root."""

    return f"{EXTERNAL_LABEL}/{Path(relative).as_posix()}"


def local_date(utc_stamp: str) -> date:
    """Return the calendar date in Thailand of a UTC time written as in a SAFE manifest."""

    moment = datetime.fromisoformat(utc_stamp.replace("Z", "")).replace(tzinfo=timezone.utc)
    return (moment + timedelta(hours=LOCAL_TIME_OFFSET_HOURS)).date()


def to_second(utc_stamp: str) -> str:
    """Write a SAFE time to the second with a Z."""

    return utc_stamp.split(".")[0].rstrip("Z") + "Z"


def software_versions() -> dict[str, str]:
    """Versions of the libraries the run used."""

    import pyogrio
    import pyproj
    import rasterio
    import scipy
    import shapely

    return {
        "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
        "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__, "pyproj": pyproj.__version__,
        "shapely": shapely.__version__, "pyogrio": pyogrio.__version__,
    }


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildInputs:
    """The read-only input files of one run, and the folder the rasters go to."""

    pre_safe: Path
    post_safe: Path
    boundaries: Path
    worldcover: Path
    dem_tiles: tuple[Path, ...]
    jrc_seasonality: Path | None
    acquisition_manifest: Path | None
    raster_dir: Path
    labels: Mapping[str, str]

    @classmethod
    def under(cls, external: Path, geocoding: str = s1.GEOCODING_GCP_POLYNOMIAL) -> "BuildInputs":
        """The inputs at their usual places under an external data root, for a run with one geocoding."""

        def place(key: str) -> Path:
            return external / INPUT_FILES[key]

        jrc = place("jrc_seasonality")
        manifest = place("acquisition_manifest")
        labels = {key: external_label(value) for key, value in INPUT_FILES.items()}
        folder = GEOCODINGS[geocoding]["raster_folder"]
        labels["raster_dir"] = external_label(folder)
        return cls(
            pre_safe=place("pre_safe"), post_safe=place("post_safe"), boundaries=place("boundaries"),
            worldcover=place("worldcover"), dem_tiles=(place("dem_west"), place("dem_east")),
            jrc_seasonality=jrc if jrc.is_file() else None,
            acquisition_manifest=manifest if manifest.is_file() else None,
            raster_dir=external / folder, labels=labels,
        )


def protocol_binding(docs: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Read protocol v1a and v1b and require both to be in force.

    Raises:
        ValueError: when a file is not in force or v1b names another v1a.
    """

    receipts = docs / "RECEIPTS.jsonl"
    protocols: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name in ("v1a", "v1b"):
        try:
            protocols[name], digest = read_protocol_in_force(name, docs / f"planning_protocol_{name}.json", receipts)
        except Exception as error:  # NormalisationError is a ValueError; a missing file is an OSError.
            raise ValueError(f"planning protocol {name} is not in force; nothing is computed ({error})") from error
        hashes[f"planning_protocol_{name}"] = digest
    if protocols["v1b"]["depends_on"]["v1a_sha256"] != hashes["planning_protocol_v1a"]:
        raise ValueError("protocol v1b does not depend on this v1a")
    return protocols, hashes


def case_frame(v1a: Mapping[str, Any]) -> dict[str, Any]:
    """Return the units and the dates protocol v1a fixes for case O1."""

    units = sorted(str(unit) for unit in v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"])
    case = next(row for row in v1a["case_portfolio"]["cases"] if row["id"] == CASE_ID)
    if case["lane"] != LANE or case["tier"] != TIER:
        raise ValueError("protocol v1a does not place case O1 in lane OBS at tier T2")
    for name in rc.FLOOD_INPUT_NAMES.values():
        if name not in case["flood_inputs"]:
            raise ValueError(f"protocol v1a does not list {name} as a flood input of case O1")
    if len(units) != len(set(units)) or not units:
        raise ValueError("the reporting frame has no usable unit list")
    return {
        "units": units,
        "case_reference_date": date.fromisoformat(case["case_reference_date"]),
        "input_acquisition": case["input_acquisition"],
        "frame": case["frame"],
    }


def read_units(boundaries: Path, unit_ids: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the unit polygons, repair invalid ones and project them to the grid's coordinate system."""

    import pyogrio
    from pyproj import Transformer
    from shapely import make_valid
    from shapely.ops import transform

    listed = ", ".join(f"'{unit}'" for unit in unit_ids)
    frame = pyogrio.read_dataframe(
        boundaries, layer=BOUNDARY_LAYER, columns=[UNIT_ID_FIELD, UNIT_NAME_FIELD],
        where=f"{UNIT_ID_FIELD} IN ({listed})",
    )
    if frame.crs is None or frame.crs.to_epsg() != 4326:
        raise ValueError("the boundary layer must be EPSG:4326")
    found = sorted(str(code) for code in frame[UNIT_ID_FIELD])
    if found != sorted(unit_ids):
        raise ValueError(f"the boundary layer does not hold exactly the units of the frame: {found}")
    project = Transformer.from_crs("EPSG:4326", GRID_CRS, always_xy=True).transform
    repaired = 0
    units = []
    for code, name, geometry in zip(frame[UNIT_ID_FIELD], frame[UNIT_NAME_FIELD], frame.geometry):
        if geometry is None or geometry.is_empty:
            raise ValueError(f"unit {code} has no geometry")
        if not geometry.is_valid:
            geometry = make_valid(geometry)
            repaired += 1
        units.append({"unit_id": str(code), "unit_name": str(name), "geometry": transform(project, geometry)})
    units.sort(key=lambda unit: unit["unit_id"])
    return units, {"layer": BOUNDARY_LAYER, "units_read": len(units), "repaired_geometries": repaired}


def frame_grid(units: Sequence[Mapping[str, Any]]) -> tuple[s1.RasterGrid, list[rc.LatticeTile], list[rc.LatticeTile]]:
    """Return the processing grid, every lattice tile inside it and the tiles that hold part of the frame."""

    from shapely.geometry import box
    from shapely.ops import unary_union

    union = unary_union([unit["geometry"] for unit in units])
    every = rc.lattice_tiles(union.bounds)
    used = [tile for tile in every if box(tile.west, tile.south, tile.east, tile.north).intersection(union).area > 0]
    west = min(tile.west for tile in used)
    north = max(tile.north for tile in used)
    east = max(tile.east for tile in used)
    south = min(tile.south for tile in used)
    grid = s1.RasterGrid(
        crs=GRID_CRS, west=west, north=north, cell_m=rc.GEOID_CELL_M,
        width=int(round((east - west) / rc.GEOID_CELL_M)), height=int(round((north - south) / rc.GEOID_CELL_M)),
    )
    return grid, every, used


def rasterize_units(units: Sequence[Mapping[str, Any]], grid: s1.RasterGrid) -> np.ndarray:
    """Give every cell the number of the unit that holds its centre (0: no unit)."""

    from rasterio import features

    return features.rasterize(
        [(unit["geometry"], position) for position, unit in enumerate(units, start=1)],
        out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8", all_touched=False,
    )


def warp_file(path: Path, grid: s1.RasterGrid, *, nearest: bool, fill: float, dtype: str) -> np.ndarray:
    """Warp band 1 of a raster file to the grid."""

    import rasterio
    from rasterio.warp import Resampling, reproject

    destination = np.full(grid.shape, fill, dtype=dtype)
    with rasterio.open(path) as source:
        reproject(
            source=rasterio.band(source, 1), destination=destination, dst_transform=grid.transform,
            dst_crs=grid.crs, dst_nodata=fill,
            resampling=Resampling.nearest if nearest else Resampling.bilinear,
        )
    return destination


def terrain_layers(dem_tiles: Sequence[Path], grid: s1.RasterGrid) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Return the height and the slope of every grid cell from the DEM tiles.

    The height is the DEM resampled bilinearly. The slope is computed on the
    DEM averaged to ``DEM_SLOPE_BLOCK`` cells (3 arc-seconds for GLO-30), from
    the four neighbours of each cell, and then resampled bilinearly.
    """

    import rasterio
    from pyproj import Geod
    from rasterio.merge import merge
    from rasterio.warp import Resampling, reproject

    sources = [rasterio.open(path) for path in dem_tiles]
    try:
        if any(source.crs is None or source.crs.to_epsg() != 4326 for source in sources):
            raise ValueError("the DEM tiles must be EPSG:4326")
        mosaic, transform = merge(sources)
    finally:
        for source in sources:
            source.close()
    elevation = mosaic[0].astype("float64")
    height = np.full(grid.shape, np.nan, dtype="float32")
    reproject(
        source=elevation.astype("float32"), destination=height, src_transform=transform, src_crs="EPSG:4326",
        dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.bilinear,
    )
    coarse = rc.block_mean(elevation, DEM_SLOPE_BLOCK)
    step_x, step_y = transform.a * DEM_SLOPE_BLOCK, -transform.e * DEM_SLOPE_BLOCK
    latitudes = transform.f - (np.arange(coarse.shape[0]) + 0.5) * step_y
    geod = Geod(ellps="WGS84")
    across = np.array([geod.inv(transform.c, lat, transform.c + step_x, lat)[2] for lat in latitudes])
    middle = float(latitudes[len(latitudes) // 2])
    along = float(geod.inv(transform.c, middle, transform.c, middle + step_y)[2])
    coarse_slope = rc.slope_degrees(coarse, across, along)
    slope = np.full(grid.shape, np.nan, dtype="float32")
    reproject(
        source=coarse_slope.astype("float32"), destination=slope,
        src_transform=transform * transform.scale(DEM_SLOPE_BLOCK, DEM_SLOPE_BLOCK), src_crs="EPSG:4326",
        src_nodata=np.nan, dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return height, slope, {
        "dem_cell_degrees": transform.a,
        "slope_cell_degrees": step_x,
        "slope_cell_m_east_west_at_mid_latitude": round(float(across[len(across) // 2]), 2),
        "slope_cell_m_north_south": round(along, 2),
    }


def height_aware_coordinates(
    safe: Path, grid: s1.RasterGrid, height: np.ndarray, datum_reading: str
) -> tuple[np.ndarray, np.ndarray]:
    """Image line and sample of every grid cell from the annotation grid and the cell heights."""

    mapping = s1.HeightAwareMapping.from_geolocation_grid(s1.read_geolocation_grid(safe, "vh"), grid.crs)
    filled = np.where(np.isfinite(height), height, float(np.nanmedian(height)))
    return mapping.image_coordinates(grid, filled + HEIGHT_DATUM_READINGS[datum_reading])


def read_pair(
    inputs: BuildInputs, grid: s1.RasterGrid, geocoding: str, height: np.ndarray
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, s1.Sigma0Window]], dict[str, dict[str, Any]]]:
    """Read, calibrate and geocode both dates: ``(2, H, W)`` linear sigma0, VV before VH.

    With the geocoding of the plan's fallback each image is warped with its
    control points. With the height-aware geocoding each image is sampled at
    the image coordinates that its own annotation grid and the cell heights
    give.
    """

    if geocoding not in GEOCODINGS:
        raise ValueError(f"unknown geocoding: {geocoding}")
    images: dict[str, np.ndarray] = {}
    windows: dict[str, dict[str, s1.Sigma0Window]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for role, path in (("pre", inputs.pre_safe), ("post", inputs.post_safe)):
        metadata[role] = s1.read_product_metadata(path)
        windows[role] = {pol: s1.read_sigma0_window(path, pol, grid) for pol in ("vv", "vh")}
        if geocoding == s1.GEOCODING_GCP_POLYNOMIAL:
            images[role] = np.stack([s1.warp_gcp_polynomial(windows[role][pol], grid) for pol in ("vv", "vh")])
        else:
            rows, cols = height_aware_coordinates(path, grid, height, HEIGHT_AWARE_DATUM_READING)
            images[role] = np.stack([s1.sample_window(windows[role][pol], rows, cols) for pol in ("vv", "vh")])
        metadata[role]["calibration_table_range"] = {
            pol: [round(value, 4) for value in windows[role][pol].gain_range] for pol in ("vv", "vh")
        }
        metadata[role]["image_window"] = {
            "row_offset": windows[role]["vh"].row_offset, "col_offset": windows[role]["vh"].col_offset,
            "rows": int(windows[role]["vh"].values.shape[0]), "cols": int(windows[role]["vh"].values.shape[1]),
        }
    first, second = metadata["pre"], metadata["post"]
    if (first["pass"], first["relative_orbit"]) != (second["pass"], second["relative_orbit"]):
        raise ValueError("the two images are not on one track")
    if first["acquisition_start_utc"] >= second["acquisition_start_utc"]:
        raise ValueError("the pre-event image is not earlier than the post-event image")
    return images, windows, metadata


# ---------------------------------------------------------------------------
# Geolocation check (no candidate is involved)
# ---------------------------------------------------------------------------


def _db(values: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.isfinite(values) & (values > 0), 10.0 * np.log10(values), np.nan)


def _metres(result: Mapping[str, Any], cell_m: float) -> dict[str, Any]:
    return {
        "east_m": result["east_cells"] * cell_m, "north_m": result["north_cells"] * cell_m,
        "correlation": result["correlation"], "at_search_edge": result["at_search_edge"],
    }


def displacement_against_water(
    image_db: np.ndarray, water: np.ndarray, grid: s1.RasterGrid, tiles: Sequence[rc.LatticeTile]
) -> dict[str, Any]:
    """Measure where the dark cells of an image lie relative to mapped permanent water.

    Water is dark in the image, so the negated backscatter is compared with
    the water mask, for the whole grid and for each tile with enough water.
    """

    valid = np.isfinite(image_db)
    result: dict[str, Any] = {
        "whole_grid": _metres(
            s1.estimate_displacement(water.astype("float64"), -image_db, valid,
                                     max_shift_cells=DISPLACEMENT_SEARCH_CELLS), grid.cell_m),
        "tiles": {},
    }
    for tile in tiles:
        rows, columns = rc.tile_window(tile, grid.west, grid.north, grid.cell_m)
        cells = int(water[rows, columns].sum())
        if cells < DISPLACEMENT_MIN_WATER_CELLS:
            result["tiles"][tile.name] = {"measured": False, "water_cells": cells,
                                          "reason": "too little mapped water in the tile"}
            continue
        result["tiles"][tile.name] = {
            "measured": True, "water_cells": cells,
            **_metres(s1.estimate_displacement(
                water[rows, columns].astype("float64"), -image_db[rows, columns], valid[rows, columns],
                max_shift_cells=DISPLACEMENT_SEARCH_CELLS), grid.cell_m),
        }
    return result


def _spread(values: np.ndarray) -> dict[str, float]:
    """The 5th percentile, the median and the 95th percentile, to a tenth."""

    return {key: round(float(np.percentile(values, level)), 1) + 0.0
            for key, level in (("p05", 5), ("median", 50), ("p95", 95))}


def pair_offset(pre_db: np.ndarray, post_db: np.ndarray, in_frame: np.ndarray, cell_m: float) -> dict[str, Any]:
    """Measure where the pre-event image content lies relative to the post-event image content.

    Whole cells and a sub-cell estimate, over every cell of the grid and over
    the cells of the frame alone. No candidate is involved.
    """

    both = np.isfinite(pre_db) & np.isfinite(post_db)

    def measured(mask: np.ndarray) -> dict[str, Any]:
        result = s1.estimate_displacement(-post_db, -pre_db, mask, max_shift_cells=PAIR_SEARCH_CELLS)
        return {
            **_metres(result, cell_m),
            "east_m_subcell": round(result["east_cells_subcell"] * cell_m, 1) + 0.0,
            "north_m_subcell": round(result["north_cells_subcell"] * cell_m, 1) + 0.0,
            "correlation_at_zero_shift": result["correlation_at_zero_shift"],
        }

    return {
        "what": "Where the pre-event image content lies relative to the post-event image content, in "
                "the images of this run. east_m and north_m are whole cells. east_m_subcell and north_m_subcell "
                "are an estimate to a fraction of a cell: the vertex of the parabola through the correlation "
                "at the best whole-cell shift and its two neighbours. Another estimator can differ by a metre "
                "or two. correlation_at_zero_shift is the correlation of the two images as the methods read "
                "them.",
        **measured(both),
        "frame_cells_only": measured(both & in_frame),
    }


def polynomial_positions(window: s1.Sigma0Window, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Image line and sample of map positions under GDAL's control-point polynomial, counted as the annotation counts.

    GDAL counts image coordinates from the corner of the first sample; the
    annotation counts samples, so a sample centre is half a cell further in
    GDAL's count. That half cell is taken off here.
    """

    from rasterio.transform import GCPTransformer

    rows, cols = GCPTransformer(list(window.gcps)).rowcol(lon.ravel(), lat.ravel(), op=lambda value: value)
    return (np.asarray(rows, dtype="float64").reshape(lon.shape) + window.row_offset - 0.5,
            np.asarray(cols, dtype="float64").reshape(lon.shape) + window.col_offset - 0.5)


def control_point_fit(
    window: s1.Sigma0Window, crs: str, frame_centre: tuple[float, float], spacing: tuple[float, float]
) -> dict[str, Any]:
    """Describe GDAL's control-point polynomial of one date: its order and its misfit at the control points.

    ``spacing`` is the range and the azimuth pixel spacing in metres. The
    residual is the control point minus the polynomial, so a positive range
    value means the polynomial reads the image nearer to the sensor than the
    control point says.
    """

    from pyproj import Transformer

    order = s1.gcp_polynomial_order(window.gcps)
    row_residual, col_residual = s1.gcp_polynomial_residuals(window.gcps)
    along_range, along_azimuth = col_residual * spacing[0], row_residual * spacing[1]
    source = window.gcp_crs.to_wkt() if hasattr(window.gcp_crs, "to_wkt") else window.gcp_crs
    x, y = Transformer.from_crs(source, crs, always_xy=True).transform(
        [point.x for point in window.gcps], [point.y for point in window.gcps])
    distance = np.hypot(np.asarray(x) - frame_centre[0], np.asarray(y) - frame_centre[1])
    nearest = [
        {"longitude": round(float(window.gcps[index].x), 3), "latitude": round(float(window.gcps[index].y), 3),
         "height_m": round(float(window.gcps[index].z), 1), "distance_from_the_frame_centre_km": round(float(distance[index]) / 1000.0, 1),
         "along_range_residual_m": round(float(along_range[index]), 1) + 0.0}
        for index in np.argsort(distance, kind="stable")[:4]
    ]

    def size(values: np.ndarray) -> dict[str, float]:
        return {"rms": round(float(np.sqrt(np.mean(values * values))), 1),
                "max_abs": round(float(np.abs(values).max()), 1)}

    return {
        **order,
        "residual_at_the_control_points_m": {"along_range": size(along_range), "along_azimuth": size(along_azimuth)},
        "control_points_nearest_the_frame": nearest,
    }


def geolocation_check(
    images: Mapping[str, np.ndarray], windows: Mapping[str, Mapping[str, s1.Sigma0Window]],
    inputs: BuildInputs, grid: s1.RasterGrid, tiles: Sequence[rc.LatticeTile], water: np.ndarray,
    height: np.ndarray, unit_index: np.ndarray, unit_ids: Sequence[str],
) -> dict[str, Any]:
    """Measure the displacement of the radar layers. No candidate is read or written here.

    Measured on the pre-event VH image, whatever geocoding the run uses:
    where its dark cells lie relative to mapped permanent water under the
    control-point warp of the plan's fallback; the same under the mapping
    that uses the DEM height of every cell (two readings of the height
    datum); and, cell by cell, how far the two mappings place the same cell
    apart in the image, split into the part that comes from the height of
    the control points and the part that comes from the misfit of GDAL's
    polynomial. The polynomial of each date is described (its order, its
    misfit at the control points and over the frame), and the two dates are
    compared. ``images`` are the images of the run; its pre-event and
    post-event images are compared with each other to a fraction of a cell.
    """

    from pyproj import Transformer

    window = windows["pre"]["vh"]
    pre_vh_db = _db(images["pre"][1])
    post_vh_db = _db(images["post"][1])
    check: dict[str, Any] = {
        "what": "Displacement of the radar layers, measured on the pre-event VH image against ESA WorldCover "
                "2021 class 80 (permanent water). Positive east_m and north_m: the image content lies east "
                "and north of the mapped water. No flood candidate is involved.",
        "search_cells": DISPLACEMENT_SEARCH_CELLS,
        "min_water_cells_for_a_tile": DISPLACEMENT_MIN_WATER_CELLS,
        "control_point_warp": {
            "geocoding": s1.GEOCODING_GCP_POLYNOMIAL,
            "status": "The fallback of plan row A4 and the geocoding of the run of record.",
            **displacement_against_water(_db(s1.warp_gcp_polynomial(window, grid)), water, grid, tiles),
        },
        "pre_against_post": pair_offset(pre_vh_db, post_vh_db, unit_index > 0, grid.cell_m),
    }
    geolocation = s1.read_geolocation_grid(inputs.pre_safe, "vh")
    mapping = s1.HeightAwareMapping.from_geolocation_grid(geolocation, grid.crs)
    readings: dict[str, Any] = {}
    coordinates: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name, geoid_height in HEIGHT_DATUM_READINGS.items():
        rows, cols = height_aware_coordinates(inputs.pre_safe, grid, height, name)
        coordinates[name] = (rows, cols)
        readings[name] = {
            "height_added_to_the_dem_m": geoid_height,
            **displacement_against_water(_db(s1.sample_window(window, rows, cols)), water, grid, tiles),
        }
    check["height_aware_mapping"] = {
        "geocoding": s1.GEOCODING_HEIGHT_AWARE,
        "status": "Not the plan's fallback path. The sensitivity run uses the reading "
                  f"{HEIGHT_AWARE_DATUM_READING}; the run of record uses neither.",
        "readings": readings,
    }

    # How far apart the mappings place the same cell in the image, on a thinned lattice. Three mappings are
    # compared: GDAL's control-point polynomial (the warp of the run of record), a spline that passes through
    # every control point (the control points at their own heights, with no polynomial in between), and the
    # mapping that uses the DEM height of every cell.
    step = DISPLACEMENT_LATTICE_STEP
    x, y = grid.cell_centres()
    mesh_x, mesh_y = np.meshgrid(x[::step], y[::step])
    lon, lat = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True).transform(mesh_x, mesh_y)
    thinned_units = unit_index[::step, ::step]
    in_frame = thinned_units > 0
    frame_centre = (float(mesh_x[in_frame].mean()), float(mesh_y[in_frame].mean()))
    polynomial: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    exact: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    misfit: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    fits: dict[str, Any] = {}
    control_height = np.zeros(mesh_x.shape)
    for role, path in (("pre", inputs.pre_safe), ("post", inputs.post_safe)):
        product = s1.read_product_metadata(path)
        spacings = (float(product["range_pixel_spacing_m"]), float(product["azimuth_pixel_spacing_m"]))
        polynomial[role] = polynomial_positions(windows[role]["vh"], lon, lat)
        grid_of_date = geolocation if role == "pre" else s1.read_geolocation_grid(path, "vh")
        exact_rows, exact_cols, heights = s1.interpolate_control_points(grid_of_date, grid.crs, mesh_x, mesh_y)
        exact[role] = (exact_rows, exact_cols)
        if role == "pre":
            control_height, spacing, azimuth_spacing = heights, spacings[0], spacings[1]
        misfit[role] = ((exact_cols - polynomial[role][1]) * spacings[0],
                        (exact_rows - polynomial[role][0]) * spacings[1])
        fits[role] = {
            **control_point_fit(windows[role]["vh"], grid.crs, frame_centre, spacings),
            "misfit_over_the_frame_m": {"along_range_m": _spread(misfit[role][0][in_frame]),
                                        "along_azimuth_m": _spread(misfit[role][1][in_frame])},
        }
    affine = [fits[role]["max_difference_from_gdal_px_by_order"].get("1") for role in ("pre", "post")]
    check["gcp_polynomial"] = {
        "what": "The polynomial GDAL fits to the control points of each date, which is the warp of the run of "
                "record. order is the order found (the warp asks GDAL for none, GDAL chooses and does not "
                "report it). residual_at_the_control_points_m is the control point minus the polynomial. "
                "misfit_over_the_frame_m is the image position of each frame cell under a spline that passes "
                f"through every control point minus its position under the polynomial, on every {step}th cell; "
                "it includes the half cell by which GDAL's count of image samples differs from the "
                "annotation's. A positive along-range value means the polynomial reads the image nearer to the "
                "sensor, so the content it shows lies that far towards far range.",
        "order_asked_of_gdal": "none: GDAL chooses the order from the number of control points",
        "found_by": "floodguard.sentinel1_sigma0.gcp_polynomial_order",
        "label_of_the_plan": s1.PLAN_FALLBACK_LABEL,
        "label_note": "The label is the plan's, word for word. An affine fit is a polynomial of order 1. "
                      "max_difference_from_gdal_px_by_order gives, under '1', how many image cells an affine "
                      "fit to the same control points lies from the polynomial that ran (open point A4-OP7).",
        "affine_fit_max_difference_px": {"pre": affine[0], "post": affine[1]},
        "pre": fits["pre"],
        "post": fits["post"],
        "post_minus_pre": {
            "what": "The misfit of the post-event polynomial minus that of the pre-event polynomial, cell by "
                    "cell over the frame. A positive along-range value means the post-event content lies "
                    "that far further towards far range than the pre-event content: the two dates are "
                    "offset from each other by it. pre_against_post measures the same offset on the images.",
            "along_range_m": _spread((misfit["post"][0] - misfit["pre"][0])[in_frame]),
            "along_azimuth_m": _spread((misfit["post"][1] - misfit["pre"][1])[in_frame]),
        },
    }

    polynomial_rows, polynomial_cols = polynomial["pre"]
    exact_rows, exact_cols = exact["pre"]
    expected: dict[str, Any] = {}
    parts: dict[str, Any] = {}
    for name, (rows, cols) in coordinates.items():
        along_range = (cols[::step, ::step] - polynomial_cols) * spacing
        along_azimuth = (rows[::step, ::step] - polynomial_rows) * azimuth_spacing
        expected[name] = {
            "frame": {"along_range_m": _spread(along_range[in_frame]),
                      "along_azimuth_m": _spread(along_azimuth[in_frame])},
            "units": {
                unit_id: {"along_range_m": _spread(along_range[thinned_units == position]),
                          "along_azimuth_m": _spread(along_azimuth[thinned_units == position])}
                for position, unit_id in enumerate(unit_ids, start=1)
            },
        }
        from_height = (cols[::step, ::step] - exact_cols) * spacing
        parts[name] = {
            "control_point_height_part_along_range_m": _spread(from_height[in_frame]),
            "polynomial_misfit_part_along_range_m": _spread(misfit["pre"][0][in_frame]),
            "mean_along_range_m": {
                "whole": round(float(along_range[in_frame].mean()), 1) + 0.0,
                "control_point_height_part": round(float(from_height[in_frame].mean()), 1) + 0.0,
                "polynomial_misfit_part": round(float(misfit["pre"][0][in_frame].mean()), 1) + 0.0,
            },
            "largest_gap_between_the_sum_of_the_parts_and_the_whole_m": round(
                float(np.abs(from_height + misfit["pre"][0] - along_range)[in_frame].max()), 3) + 0.0,
        }
    distance = np.hypot(mapping.x0 - (grid.west + grid.width * grid.cell_m / 2),
                        mapping.y0 - (grid.north - grid.height * grid.cell_m / 2))
    centre = np.unravel_index(int(np.argmin(distance)), distance.shape)
    bearing = (np.degrees(np.arctan2(mapping.range_x[centre], mapping.range_y[centre])) + 360.0) % 360.0
    check["expected_from_geometry"] = {
        "what": "Image position of each cell under the height-aware mapping minus its position under the "
                "control-point warp, in metres, on every "
                f"{step}th cell. A positive along-range value means the control-point warp reads the image "
                "nearer to the sensor than it should, so the content it shows lies that far towards far "
                "range of its true place.",
        "range_direction_bearing_degrees": round(float(bearing), 1),
        "incidence_angle_degrees_near_the_frame": round(float(np.degrees(np.arctan(mapping.tan_incidence[centre]))), 2),
        "annotation_height_near_the_frame_m": round(float(geolocation.height[centre]), 1),
        "annotation_height_near_the_frame_note": "The height of the one control point nearest the centre of "
                                                 "the grid. The control points around the frame have other "
                                                 "heights; control_point_height_over_the_frame_m interpolates "
                                                 "them.",
        "control_point_height_over_the_frame_m": _spread(control_height[in_frame]),
        "median_dem_height_of_the_frame_m": round(float(np.nanmedian(height[unit_index > 0])), 1),
        "readings": expected,
        "parts": {
            "what": "The along-range displacement of each reading, split in two, cell by cell: the part that "
                    "comes from the height of the control points (the height-aware mapping minus a spline "
                    "that passes through every control point) and the part that comes from the misfit of "
                    "GDAL's polynomial (that spline minus the polynomial). The two add up to the whole for "
                    "every cell, and so do their means over the frame (mean_along_range_m); the medians of "
                    "the parts need not add up to the median of the whole.",
            **parts,
        },
    }
    return check


# ---------------------------------------------------------------------------
# Methods and tables
# ---------------------------------------------------------------------------


def method_table(
    name: str, candidate: np.ndarray, reason: np.ndarray, layers: Mapping[str, np.ndarray],
    unit_ids: Sequence[str], unit_names: Mapping[str, str], cell_area_km2: float, thresholds: Mapping[str, float],
    label: str,
) -> dict[str, Any]:
    """Count one method per unit, for the frame and by land-cover and slope class."""

    rows = rc.unit_rows(
        candidate, reason, layers["unit_index"], unit_ids, cell_area_km2=cell_area_km2,
        valid_input=layers["valid_input"], permanent_water=layers["permanent_water"],
        coverage_min=thresholds["coverage_min"], abstention_max=thresholds["abstention_max"],
    )
    rows = [{"unit_id": row["unit_id"], "unit_name": unit_names[row["unit_id"]],
             **{key: value for key, value in row.items() if key != "unit_id"}} for row in rows]
    slope_class, slope_labels = rc.slope_classes(layers["slope"], SLOPE_CLASS_EDGES)
    in_frame = layers["unit_index"] > 0
    return {
        "flood_input": rc.FLOOD_INPUT_NAMES[name],
        "lane": LANE,
        "tier": TIER,
        "label": f"{rc.FLOOD_INPUT_NAMES[name]} ({label})",
        "display": "Own model candidate: verify before action",
        "area_note": "A candidate cell is a cell the method's rule flagged from the change in backscatter. It "
                     "is not a cell that was seen under water.",
        "frame": rc.frame_totals(rows, cell_area_km2=cell_area_km2),
        "units": rows,
        "strata": {
            "by_land_cover_worldcover_2021": rc.strata_areas(
                candidate, in_frame, layers["worldcover"], WORLDCOVER_CLASSES, cell_area_km2=cell_area_km2),
            "by_slope_class": rc.strata_areas(
                candidate, in_frame, slope_class, slope_labels, cell_area_km2=cell_area_km2),
        },
    }


def geocoding_transform(geocoding: str, orders: Sequence[int | None]) -> str:
    """Name the transform a run used to put the image on the map grid."""

    if geocoding == s1.GEOCODING_GCP_POLYNOMIAL:
        return ("GDAL's control-point polynomial" + polynomial_order_clause(orders)
                + ", one fit for each date; no terrain model")
    return ("the geolocation grid of the annotation, interpolated by a thin-plate spline, with the DEM height "
            "of every cell; no polynomial")


def label_note(orders: Sequence[int | None]) -> str:
    """Set the plan's label against the transform that ran, from the order found for each date."""

    found = set(orders)
    if len(found) != 1 or None in found:
        return ("The label is the plan's, word for word. The order of the polynomial that ran could not be told "
                "from these control points (geolocation_check.gcp_polynomial).")
    order = next(iter(found))
    if order == 1:
        return "The label is the plan's, word for word. The polynomial that ran is of order 1: an affine fit."
    return ("The label is the plan's, word for word. The transform that ran is a polynomial of order "
            f"{order}, not the affine fit the label names (open point A4-OP7).")


def literal_upper_level(tiles: Sequence[rc.LatticeTile], summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Say, tile by tile, what the +1 dB level of M1-literal is once the below-zero clause has cut it."""

    def named(outcome: str | None) -> list[str]:
        return [tile.name for tile in tiles if summaries[tile.name]["threshold_levels"]["plus_level"] == outcome]

    return {
        "levels": "strictest, central and loosest level (protocol v1b: the Otsu threshold moved by 1 dB each "
                  "way). The loosest level is cut at 0 dB: see upper_level.",
        "upper_level": {
            "what": "M1-literal flags a cell only where delta-VH is below the threshold and below 0 dB. The "
                    "second clause is kept at every level, so the loosest level is the Otsu threshold moved by "
                    "+1 dB only in the tiles whose Otsu threshold is -1 dB or lower. In the other tiles it is "
                    "cut at 0 dB, and where the Otsu threshold is 0 dB or more it is the central level again. "
                    "The band is narrower above the central level than below it by construction "
                    "(open point A4-OP9).",
            "cap_db": 0.0,
            "tiles_with_the_full_shift": named(rc.PLUS_LEVEL_FULL_SHIFT),
            "tiles_cut_at_0_db": named(rc.PLUS_LEVEL_CUT),
            "tiles_identical_to_the_central_level": named(rc.PLUS_LEVEL_SAME_AS_CENTRAL),
            "tiles_without_a_threshold": named(None),
            "otsu_threshold_db_by_tile": {tile.name: summaries[tile.name]["otsu_threshold_delta_vh_db"]
                                          for tile in tiles},
            "shift_that_took_effect_db_by_tile": {
                tile.name: summaries[tile.name]["threshold_levels"]["plus_level_shift_that_took_effect_db"]
                for tile in tiles},
        },
    }


def declined_because(summary: Mapping[str, Any]) -> str | None:
    """Say why a method gave no answer for a tile, from the summary of the frozen function."""

    if not summary["abstained"]:
        return None
    if "sides" not in summary:
        return "no Otsu threshold"
    if all(side["selected_blocks"] == 0 for side in summary["sides"].values()):
        return "no bimodal block in the tile"
    return ("bimodal blocks were found, but their pooled histogram gave no threshold that the frozen rule "
            "accepts (an interior Kittler-Illingworth minimum between the two fitted modes, above 0 dB)")


def tile_rows(
    tiles: Sequence[rc.LatticeTile], grid: s1.RasterGrid, unit_index: np.ndarray, candidate: np.ndarray,
    summaries: Mapping[str, Mapping[str, Any]], unit_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """One row per tile: its place, how much of the frame it holds and what the method did on it."""

    rows = []
    for tile in tiles:
        window = rc.tile_window(tile, grid.west, grid.north, grid.cell_m)
        summary = {key: value for key, value in summaries[tile.name].items() if key != "configuration"}
        in_frame = unit_index[window] > 0
        counts = np.bincount(unit_index[window].ravel(), minlength=len(unit_ids) + 1)
        rows.append({
            "tile": tile.name,
            "bounds_epsg_32647": [tile.west, tile.south, tile.east, tile.north],
            "frame_cells_in_tile": int(in_frame.sum()),
            "frame_cells_by_unit": {unit_id: int(counts[position])
                                    for position, unit_id in enumerate(unit_ids, start=1) if counts[position]},
            "candidate_cells_in_frame": int((in_frame & (candidate[window] == sar.CANDIDATE_YES)).sum()),
            "declined": bool(summary["abstained"]),
            "declined_because": declined_because(summary),
            "whole_tile": summary,
        })
    return rows


def geoid_condition(rule: confidence.ConfidenceRule) -> dict[str, Any]:
    """Read the GEOID held-out result of M1-v2 from the committed benchmark files."""

    summary = json.loads(GEOID_SUMMARY.read_text(encoding="utf-8"))
    derived = json.loads(GEOID_DERIVED_CHECKS.read_text(encoding="utf-8"))["t2_skill_bar"]
    test = derived["m1_v2_test"]
    literal = summary["results"]["m1_literal"]["test"]["primary"]
    return {
        "source": [repo_label(GEOID_DERIVED_CHECKS, ROOT), repo_label(GEOID_SUMMARY, ROOT)],
        "source_sha256": [sha256_file(GEOID_DERIVED_CHECKS), sha256_file(GEOID_SUMMARY)],
        "minimum": rule.skill_geoid_held_out_test_iou_min,
        "m1_v2_test_iou_strict": test["iou_strict"],
        "m1_v2_test_iou_covered_cells": test["iou_covered"],
        "m1_v2_test_cells_without_an_answer": test["abstained_cell_share"],
        "declared_reading": derived["declared_reading"],
        "point_estimate_reaches_the_minimum": min(test["iou_strict"], test["iou_covered"])
        >= rule.skill_geoid_held_out_test_iou_min,
        "holds_for_every_tile_left_out": test["leave_one_tile_out"]["holds_for_every_tile_left_out"],
        "said_beside_the_result_every_time": R15_CAVEATS,
        "decision": "Decision log R15: v1a is applied as signed; the GEOID condition is met on the point "
                    "estimate, and every report says the three sentences above.",
        "m1_literal_test_iou_strict": literal["strict"]["iou"],
    }


def skill_outcome(
    evaluated: bool, frame_passes: Mapping[str, bool], per_unit: Mapping[str, Sequence[str]], count: int
) -> dict[str, Any]:
    """State the outcome of the T2 skill bar for one input, so that no reading is taken for a decision.

    ``frame_passes`` says, for each coverage reading, whether the four
    conditions pass for the input as a whole: the frame-wide share without an
    answer and the smallest coverage of any unit. ``per_unit`` lists, for
    each coverage reading, the units that pass when the conditions are read
    per unit.

    The outcome is ``met`` only when every reading passes for the frame and
    for every unit, ``not_met`` when no reading passes for the frame, and
    ``undecided`` otherwise. A unit that passes only when the conditions are
    read per unit is listed as undecided: protocol v1a does not say whether
    one unit can pass on its own (open point A4-OP3).
    """

    undecided = sorted({unit for units in per_unit.values() for unit in units})
    everywhere = all(frame_passes.values()) and all(len(units) == count for units in per_unit.values())
    if everywhere:
        value, undecided, reading = OUTCOME_MET, [], PER_UNIT_SAME
        note = "Every reading of the Mae Sai conditions passes, for the frame and for every tambon."
    elif not any(frame_passes.values()):
        value = OUTCOME_NOT_MET
        if not evaluated:
            undecided, reading = [], PER_UNIT_NOT_APPLICABLE
            note = "Protocol v1a declares this input unable to meet the T2 skill bar, whatever its figures are."
        elif undecided:
            reading = PER_UNIT_UNDECIDED
            note = ("The input as a whole does not pass under any reading. Read per tambon, the conditions pass "
                    f"in {', '.join(undecided)} only. Protocol v1a does not say whether one tambon can pass on "
                    "its own (open point A4-OP3), so no pass is of record for any tambon and a later lane must "
                    "not read one from this table.")
        else:
            reading = PER_UNIT_SAME
            note = "The input does not pass under any reading, for the frame or for any tambon."
    else:
        value, reading = OUTCOME_UNDECIDED, PER_UNIT_UNDECIDED
        note = ("The readings of the Mae Sai conditions disagree for the frame (open point A4-OP3). No pass is "
                "of record, and a later lane must not read one from this table.")
    return {"outcome": value, "per_unit_reading": reading, "units_whose_outcome_is_undecided": undecided,
            "outcome_note": note}


def t2_skill_bar(
    rule: confidence.ConfidenceRule, tables: Mapping[str, Mapping[str, Any]], geoid: Mapping[str, Any],
    acquisition_utc: str, reference: date, *, of_record: bool = True,
) -> dict[str, Any]:
    """Evaluate the T2 skill bar of protocol v1a with ``confidence.t2_skill_condition``.

    The rule is applied per unit, as ``floodguard.confidence`` applies it,
    once with each coverage reading, and once for the input as a whole (the
    frame-wide share without an answer and the smallest coverage of any
    unit). The acquisition date is the Thai calendar date of the post-event
    image, as protocol v1a writes it for case O1.

    A pass for a single unit is written as ``passes_if_read_per_unit``, never
    as a pass: see :func:`skill_outcome`. ``outcome_of_record`` is the
    outcome when ``of_record`` is true and ``None`` in a sensitivity run.
    """

    acquired_local = local_date(acquisition_utc)
    acquired_utc = datetime.fromisoformat(acquisition_utc.replace("Z", "")).date()
    iou = {
        "m1_v2": min(geoid["m1_v2_test_iou_strict"], geoid["m1_v2_test_iou_covered_cells"]),
        "m1_literal": geoid["m1_literal_test_iou_strict"],
        "un_spider": None,
    }
    result: dict[str, Any] = {
        "source": "planning_protocol_v1a.json t2_skill_bar, applied by floodguard.confidence.t2_skill_condition",
        "thresholds": {
            "geoid_held_out_test_iou_min": rule.skill_geoid_held_out_test_iou_min,
            "mae_sai_abstention_fraction_max": rule.skill_abstention_fraction_max,
            "mae_sai_unit_coverage_min": rule.skill_unit_coverage_min,
            "recency_window_days": rule.skill_recency_window_days,
        },
        "recency": {
            "post_event_acquisition_utc": to_second(acquisition_utc),
            "acquisition_date_in_thailand": acquired_local.isoformat(),
            "acquisition_date_utc": acquired_utc.isoformat(),
            "case_reference_date": reference.isoformat(),
            "days_by_the_thai_date": abs((acquired_local - reference).days),
            "days_by_the_utc_date": abs((acquired_utc - reference).days),
            "passes": abs((acquired_local - reference).days) <= rule.skill_recency_window_days
            and abs((acquired_utc - reference).days) <= rule.skill_recency_window_days,
            "note": "The date is that of the post-event image. The pre-event image of the pair is 12 days "
                    "earlier; protocol v1a names the 16 September pass as the acquisition of case O1.",
        },
        "geoid_condition": dict(geoid),
        "methods": {},
    }
    for name, table in tables.items():
        flood_input = rc.FLOOD_INPUT_NAMES[name]
        units = []
        for row in table["units"]:
            readings = {}
            for reading in ("input_coverage", "answer_coverage"):
                outcome = confidence.t2_skill_condition(
                    rule, flood_input=flood_input, geoid_held_out_test_iou=iou[name],
                    abstention_fraction=row["abstention_fraction"], unit_valid_coverage=row[reading],
                    acquisition_date=acquired_local, case_reference_date=reference,
                )
                readings[reading] = {PER_UNIT_PASS_KEY: outcome["passes"], "conditions": outcome["conditions"],
                                     "failed_conditions": outcome["failed_conditions"]}
                status = outcome["status"]
            units.append({
                "unit_id": row["unit_id"], "unit_name": row["unit_name"],
                "abstention_fraction": row["abstention_fraction"],
                "input_coverage": row["input_coverage"], "answer_coverage": row["answer_coverage"],
                "coverage_reading": readings,
            })
        frame = table["frame"]
        abstention_units = sum(row["abstention_fraction"] <= rule.skill_abstention_fraction_max for row in table["units"])
        input_units = sum(row["input_coverage"] >= rule.skill_unit_coverage_min for row in table["units"])
        answer_units = sum(row["answer_coverage"] >= rule.skill_unit_coverage_min for row in table["units"])
        count = len(table["units"])
        per_unit = {
            reading: [unit["unit_id"] for unit in units if unit["coverage_reading"][reading][PER_UNIT_PASS_KEY]]
            for reading in ("input_coverage", "answer_coverage")
        }
        frame_passes = {
            reading: bool(confidence.t2_skill_condition(
                rule, flood_input=flood_input, geoid_held_out_test_iou=iou[name],
                abstention_fraction=frame["abstention_fraction"],
                unit_valid_coverage=min(row[reading] for row in table["units"]),
                acquisition_date=acquired_local, case_reference_date=reference,
            )["passes"])
            for reading in ("input_coverage", "answer_coverage")
        }
        outcome = skill_outcome(status == confidence.SKILL_EVALUATED, frame_passes, per_unit, count)
        result["methods"][name] = {
            "flood_input": flood_input,
            "status_in_protocol_v1a": status,
            "outcome_of_record": outcome["outcome"] if of_record else None,
            "outcome_of_this_evaluation": outcome["outcome"],
            "outcome_note": outcome["outcome_note"] if of_record else (
                "Not the evaluation of record: the outcome of record is in the table of the run of record. "
                + outcome["outcome_note"]),
            "per_unit_reading": outcome["per_unit_reading"],
            "units_whose_outcome_is_undecided": outcome["units_whose_outcome_is_undecided"],
            "passes_for_the_input_as_a_whole": {
                "what": "The four conditions applied once to the input: the frame-wide share of cells without "
                        "an answer and the smallest coverage of any tambon, under each coverage reading.",
                **frame_passes,
            },
            "geoid_held_out_test_iou_used": iou[name],
            "mae_sai_conditions": {
                "abstention": {
                    "units_at_most_max": abstention_units, "units": count,
                    "frame_abstention_fraction": frame["abstention_fraction"],
                    "frame_at_most_max": frame["abstention_fraction"] <= rule.skill_abstention_fraction_max,
                    "passes_for_every_unit": abstention_units == count,
                },
                "coverage": {
                    "units_with_input_coverage_at_least_min": input_units,
                    "units_with_answer_coverage_at_least_min": answer_units, "units": count,
                    "passes_for_every_unit_by_input_coverage": input_units == count,
                    "passes_for_every_unit_by_answer_coverage": answer_units == count,
                },
                "recency_passes": result["recency"]["passes"],
            },
            PER_UNIT_KEY: per_unit,
            "units": units,
        }
    return result


def skill_sentence(name: str, entry: Mapping[str, Any], rule: confidence.ConfidenceRule) -> str:
    """Say the outcome of the Mae Sai conditions for one method in one plain sentence."""

    conditions = entry["mae_sai_conditions"]
    abstention, coverage = conditions["abstention"], conditions["coverage"]
    count = abstention["units"]
    parts = [
        f"abstention at most {rule.skill_abstention_fraction_max:g}: {abstention['units_at_most_max']} of {count} "
        f"tambons (frame share without an answer {abstention['frame_abstention_fraction']:.3f})",
        f"coverage at least {rule.skill_unit_coverage_min:g}: {coverage['units_with_input_coverage_at_least_min']} "
        f"of {count} tambons by valid radar input and {coverage['units_with_answer_coverage_at_least_min']} of "
        f"{count} by cells with an answer",
        f"recency: {'pass' if conditions['recency_passes'] else 'fail'}",
    ]
    every = (abstention["passes_for_every_unit"] and coverage["passes_for_every_unit_by_answer_coverage"]
             and conditions["recency_passes"])
    frame_passes = abstention["frame_at_most_max"] and conditions["recency_passes"]
    passing = entry[PER_UNIT_KEY]["answer_coverage"]
    label = rc.FLOOD_INPUT_NAMES[name]
    frame_clause = (
        f"For the frame as a whole, {abstention['frame_abstention_fraction']:.3f} of the cells have no answer, "
        f"{'within' if abstention['frame_at_most_max'] else 'above'} the maximum of "
        f"{rule.skill_abstention_fraction_max:g}."
    )
    if entry["status_in_protocol_v1a"] != confidence.SKILL_EVALUATED:
        verdict = (f"{label} is declared unable to meet the T2 skill bar by protocol v1a, whatever these "
                   "figures are: low confidence.")
    elif every and frame_passes:
        verdict = (f"{label} meets the three Mae Sai conditions in every tambon and for the frame. With the "
                   "GEOID point estimate the rule then evaluates to pass; the three sentences on the GEOID "
                   "result apply.")
    elif not passing:
        verdict = (f"{label} does not meet the Mae Sai conditions in any tambon: it stays at low confidence "
                   f"(tier T2, no demonstrated skill). {frame_clause}")
    else:
        failing = count - len(passing)
        scope = "in" if frame_passes else "for the frame, nor in"
        verdict = (f"{label} does not meet the Mae Sai conditions {scope} {failing} of {count} tambons, where "
                   f"it stays at low confidence (tier T2, no demonstrated skill). {frame_clause} Read tambon by "
                   f"tambon, the conditions pass in {len(passing)} of {count} ({', '.join(passing)}); whether one "
                   "tambon can pass on its own is open point A4-OP3.")
    return f"{verdict} Counts: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Rasters
# ---------------------------------------------------------------------------


def write_raster(
    path: Path, array: np.ndarray, grid: s1.RasterGrid, *, nodata: float | None, tags: Mapping[str, str],
    descriptions: Sequence[str],
) -> dict[str, Any]:
    """Write a GeoTIFF with its provenance tags and return its size and SHA-256."""

    import rasterio

    data = array if array.ndim == 3 else array[None]
    floating = np.issubdtype(data.dtype, np.floating)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=grid.width, height=grid.height, count=data.shape[0],
        dtype=str(data.dtype), crs=grid.crs, transform=grid.transform, nodata=nodata, compress="deflate",
        predictor=3 if floating else 2, tiled=True, blockxsize=512, blockysize=512,
    ) as target:
        target.write(data)
        target.update_tags(**tags)
        for band, description in enumerate(descriptions, start=1):
            target.set_band_description(band, description)
    return {"sha256": sha256_file(path), "bytes": path.stat().st_size}


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def build(
    inputs: BuildInputs, *, geocoding: str = s1.GEOCODING_GCP_POLYNOMIAL, docs: Path = DOCS, root: Path = ROOT
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Compute the table, the receipt (without its outputs) and the rasters to write.

    ``geocoding`` is the fallback of plan row A4 (the run of record) or the
    height-aware mapping (a sensitivity run that the plan does not name).

    Raises:
        ValueError: when a protocol is not in force, the frozen M1-v2 has
            changed, an input is not what the run needs, or a result breaks
            one of the checks the run makes on itself.
    """

    if geocoding not in GEOCODINGS:
        raise ValueError(f"unknown geocoding: {geocoding}")
    run_role, label = GEOCODINGS[geocoding]["role"], GEOCODINGS[geocoding]["label"]
    of_record = run_role == RUN_OF_RECORD
    protocols, protocol_sha256 = protocol_binding(docs)
    rule = confidence.load_confidence_rule(docs / "planning_protocol_v1a.json", docs / "RECEIPTS.jsonl")
    try:
        binding = review.require_frozen_m1_v2(root)
    except review.GeoidReviewError as error:
        raise ValueError(f"the frozen M1-v2 is not intact; nothing is computed ({error})") from error
    v2_config = sar.m1_v2_config_from_json(binding["parameters"])
    literal_config = sar.M1LiteralConfig()
    un_spider_config = rc.UnSpiderConfig()
    frame = case_frame(protocols["v1a"])
    unit_ids = frame["units"]

    units, boundary_summary = read_units(inputs.boundaries, unit_ids)
    unit_names = {unit["unit_id"]: unit["unit_name"] for unit in units}
    grid, lattice, tiles = frame_grid(units)
    cell_area_km2 = grid.cell_m * grid.cell_m / 1e6
    unit_index = rasterize_units(units, grid)
    in_frame = unit_index > 0

    worldcover = warp_file(inputs.worldcover, grid, nearest=True, fill=0, dtype="uint8")
    permanent_water = worldcover == PERMANENT_WATER_CLASS
    height, slope, terrain = terrain_layers(inputs.dem_tiles, grid)
    if not np.isfinite(slope[in_frame]).all():
        raise ValueError("the slope layer does not cover the frame")

    images, windows, products = read_pair(inputs, grid, geocoding, height)
    valid_input = sar.valid_radiometry(images["pre"], images["post"])
    geolocation = geolocation_check(images, windows, inputs, grid, tiles, permanent_water, height, unit_index, unit_ids)
    polynomial_orders = [geolocation["gcp_polynomial"][role]["order"] for role in ("pre", "post")]
    assumptions = assumptions_for(geocoding, polynomial_orders)
    limits = limits_for(geolocation["pre_against_post"], of_record)

    thresholds = {"coverage_min": rule.skill_unit_coverage_min, "abstention_max": rule.skill_abstention_fraction_max}
    layers = {"unit_index": unit_index, "valid_input": valid_input, "permanent_water": permanent_water,
              "worldcover": worldcover, "slope": slope}
    rasters: dict[str, dict[str, Any]] = {}
    tables: dict[str, dict[str, Any]] = {}

    # A2: the UN-SPIDER recommended practice on the frame.
    candidate, reason, quotient, summary = rc.un_spider_candidate(
        images["pre"][1], images["post"][1], in_frame=in_frame, permanent_water=permanent_water, slope=slope,
        cell_m=grid.cell_m, config=un_spider_config)
    tables["un_spider"] = {
        "plan_task": "A2",
        **method_table("un_spider", candidate, reason, layers, unit_ids, unit_names, cell_area_km2, thresholds,
                       label),
        "configuration": summary["configuration"],
        "steps": {key: value for key, value in summary.items() if key not in ("method", "configuration")},
        "differences_from_the_published_practice": [
            "Sigma0 from the SAFE look-up table, geocoded as this run states, not Earth Engine's "
            "terrain-corrected backscatter with thermal noise removed.",
            "Perennial water: ESA WorldCover 2021 class 80, not JRC seasonality of 10 months or more "
            "(the JRC tile on disk does not cover the whole frame).",
            "Slope: Copernicus GLO-30 averaged to 3 arc-seconds, not the HydroSHEDS 3 arc-second DEM.",
            "One image per date, not a mosaic over a date range.",
        ],
    }
    area = tables["un_spider"]["frame"]["candidate_area_km2"]
    tables["un_spider"]["statement"] = REQUIRED_STATEMENT_A2.format(area=f"{area:.2f}")
    rasters["un_spider"] = {"candidate": candidate, "reason": reason, "score": quotient}
    if inputs.jrc_seasonality is not None:
        jrc = warp_file(inputs.jrc_seasonality, grid, nearest=True, fill=JRC_NO_DATA, dtype="uint8")
        covered = in_frame & (jrc != JRC_NO_DATA)
        with_jrc = rc.un_spider_candidate(
            images["pre"][1], images["post"][1], in_frame=covered, permanent_water=jrc >= JRC_PERENNIAL_MONTHS,
            slope=slope, cell_m=grid.cell_m, config=un_spider_config)[0]
        with_worldcover = rc.un_spider_candidate(
            images["pre"][1], images["post"][1], in_frame=covered, permanent_water=permanent_water,
            slope=slope, cell_m=grid.cell_m, config=un_spider_config)[0]
        tables["un_spider"]["jrc_sensitivity_note"] = {
            "what": "The practice's own perennial-water layer (JRC seasonality of 10 months or more) on the "
                    "part of the frame the JRC tile on disk covers, beside WorldCover class 80 on the same part.",
            "share_of_frame_covered_by_the_jrc_tile": round(float(covered.sum()) / float(in_frame.sum()), 6),
            "perennial_water_cells_jrc": int((covered & (jrc >= JRC_PERENNIAL_MONTHS)).sum()),
            "perennial_water_cells_worldcover": int((covered & permanent_water).sum()),
            "candidate_km2_with_jrc": round(int((with_jrc == sar.CANDIDATE_YES).sum()) * cell_area_km2, 4),
            "candidate_km2_with_worldcover": round(int((with_worldcover == sar.CANDIDATE_YES).sum()) * cell_area_km2, 4),
        }

    # A4: M1-literal and the frozen M1-v2, one lattice tile at a time.
    runners = {
        "m1_literal": lambda pre, post: rc.m1_literal_tile(pre, post, literal_config),
        "m1_v2": lambda pre, post: rc.m1_v2_tile(pre, post, v2_config),
    }
    for name, runner in runners.items():
        whole, whole_reason, score, levels, summaries = rc.run_on_tiles(
            images["pre"], images["post"], tiles, runner, grid_west=grid.west, grid_north=grid.north,
            cell_m=grid.cell_m)
        candidate, reason, levels = rc.restrict_to_frame(whole, whole_reason, levels, in_frame)
        assert levels is not None
        tables[name] = {
            "plan_task": "A4",
            **method_table(name, candidate, reason, layers, unit_ids, unit_names, cell_area_km2, thresholds,
                           label),
            "configuration": sar.config_to_json(literal_config if name == "m1_literal" else v2_config),
            "tiles": tile_rows(tiles, grid, unit_index, candidate, summaries, unit_ids),
            "tiles_declined": sorted(tile for tile, item in summaries.items() if item["abstained"]),
            "threshold_levels": rc.level_areas(levels, unit_index, unit_ids, cell_area_km2=cell_area_km2),
        }
        if name == "m1_literal":
            tables[name]["threshold_levels"].update(literal_upper_level(tiles, summaries))
        rasters[name] = {"candidate": candidate, "reason": reason,
                         "score": np.where(in_frame, score, np.nan).astype("float32"), "levels": levels}
    tables["m1_v2"]["frozen_binding"] = {key: value for key, value in binding.items() if key != "parameters"}
    tables["m1_v2"]["disclosed_differences_from_geoid"] = [
        "GEOID tiles were terrain-corrected by their publisher; these are geocoded as this run states.",
        "No HAND or slope mask is applied (see open point A4-OP2).",
        "The pre-event and post-event images are 12 days apart on one track; on GEOID they were almost four "
        "months apart and on different orbit directions.",
        pair_offset_difference_from_geoid(geolocation["pre_against_post"]),
    ]

    geoid = geoid_condition(rule)
    skill = t2_skill_bar(rule, tables, geoid, products["post"]["acquisition_start_utc"], frame["case_reference_date"],
                         of_record=of_record)
    for name in rc.METHODS:
        skill["methods"][name]["result"] = skill_sentence(name, skill["methods"][name], rule)
    skill["evaluation_of_record"] = of_record
    skill["evaluation_note"] = (
        "The evaluation of record: made on the run of record, the fallback of plan row A4."
        if of_record else
        "Not the evaluation of record. It repeats the evaluation on the sensitivity run, whose geocoding the "
        "plan does not name."
    )

    source_timestamp = to_second(products["post"]["acquisition_start_utc"])
    common = {
        "official_warning": False,
        "operational_status": "non_operational",
        "computes": COMPUTES,
        "source_timestamp": source_timestamp,
        "source_timestamps": {
            "pre_event_image_utc": to_second(products["pre"]["acquisition_start_utc"]),
            "post_event_image_utc": source_timestamp,
            "post_event_image_in_thailand": (
                datetime.fromisoformat(source_timestamp[:-1]) + timedelta(hours=LOCAL_TIME_OFFSET_HOURS)
            ).strftime("%Y-%m-%d %H:%M ICT"),
            "worldcover": "2021", "boundaries": "COD-AB tha_admin3 (2022)",
        },
        "confidence_class": "low",
        "confidence_basis": CONFIDENCE_BASIS,
        "protocol_sha256": protocol_sha256,
    }
    grid_record = {
        "crs": grid.crs, "cell_m": grid.cell_m, "width": grid.width, "height": grid.height,
        "bounds": list(grid.bounds),
        "tile_lattice": "The lattice of the GEOID-Flood sample: tiles of 1024 by 1024 cells of 10 m whose corners "
                        "are whole multiples of 10,240 m in the UTM zone. Here: UTM zone 47N.",
        "tiles_in_the_bounding_box": [tile.name for tile in lattice],
        "tiles_holding_part_of_the_frame": [tile.name for tile in tiles],
    }
    table = {
        "schema_version": TABLE_SCHEMA,
        "plan_task": PLAN_TASK,
        "case": {"id": CASE_ID, "lane": LANE, "tier": TIER, "frame": frame["frame"],
                 "case_reference_date": frame["case_reference_date"].isoformat(),
                 "input_acquisition_in_protocol_v1a": frame["input_acquisition"]},
        "result_document": RESULT_DOCUMENT,
        "status": "t2_own_candidates_unqualified",
        "status_note": "Written with protocol v1a and v1b in force (protocol_sha256). Three own candidates of "
                       "tier T2: verify before action. They are not validated: none was compared with a "
                       "reference, and none is an observation of a flood. No FPPS, A-E class or ensemble is here.",
        "run_role": run_role,
        "run_role_note": (
            "The run of record: the fallback of plan row A4, as the plan states it."
            if of_record else
            "A sensitivity run. Its geocoding is not in the plan. It replaces nothing and is not a flood input "
            "of case O1 unless the owners decide so."
        ),
        **common,
        "geocoding": {"label": label, "method": geocoding,
                      "transform": geocoding_transform(geocoding, polynomial_orders),
                      "label_note": label_note(polynomial_orders) if of_record else None,
                      "radiometry": "sigma0 from the sigmaNought look-up table of the SAFE annotation",
                      "resampling": "bilinear on linear sigma0",
                      "height_datum_reading": None if of_record else HEIGHT_AWARE_DATUM_READING},
        "grid": grid_record,
        "units": [{"unit_id": unit["unit_id"], "unit_name": unit["unit_name"],
                   "polygon_area_km2": round(unit["geometry"].area / 1e6, 4),
                   "cells": int((unit_index == position).sum())}
                  for position, unit in enumerate(units, start=1)],
        "image_pair": products,
        "radar_input": {
            "median_sigma0_db_in_frame": {
                f"{role}_{pol}": round(float(np.nanmedian(_db(images[role][band])[in_frame])), 3)
                for role in ("pre", "post") for band, pol in enumerate(("vv", "vh"))
            },
            "frame_cells_with_valid_input_on_both_dates": int((valid_input & in_frame).sum()),
            "frame_cells": int(in_frame.sum()),
        },
        "terrain": terrain,
        "geolocation_check": geolocation,
        "methods": tables,
        "t2_skill_bar": skill,
        "o1_flood_input_interface": {
            "status": "No flood-inputs module (plan task E1, flood_inputs.py) is on this branch. Each candidate "
                      "is therefore a GeoTIFF mask outside Git with this table and its receipt.",
            "mask": "<method>_candidate.tif: 1 flood candidate, 0 not a candidate, 255 no answer.",
            "flood_input_fields": {
                "tier": TIER, "temporal_relation": "event_aligned",
                "acquisition_time": source_timestamp, "case_reference_date": frame["case_reference_date"].isoformat(),
                "rights_level": "not assigned here: the rights registry of the flood-inputs lane assigns it. "
                                "Copernicus Sentinel data are free and open, with attribution.",
                "attribution": "Contains modified Copernicus Sentinel data 2024",
            },
            "use_restriction": (
                "Tambon totals only, and those are displaced too. Not for cell-level or road-level "
                "intersection until the displacement in geolocation_check is removed (open point A4-OP1)."
                if of_record else
                "Not a flood input of case O1 unless the owners decide so (open point A4-OP1)."
            ),
        },
        "open_points": OPEN_POINTS,
        "not_computed": NOT_COMPUTED,
        "assumptions": assumptions,
        "limits": limits,
    }
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    manifest_note = None
    if inputs.acquisition_manifest is not None:
        with inputs.acquisition_manifest.open(newline="", encoding="utf-8") as stream:
            recorded = {row["product_name"]: row for row in csv.DictReader(stream)}
        manifest_note = {
            role: {"sha256_in_the_acquisition_manifest": recorded.get(products[role]["product"], {}).get("sha256"),
                   "processing_allowed_in_the_manifest": recorded.get(products[role]["product"], {}).get("processing_allowed"),
                   "reason_in_the_manifest": recorded.get(products[role]["product"], {}).get("reason_blocked")}
            for role in ("pre", "post")
        }
    input_files = {
        "pre_event_safe": (inputs.pre_safe, inputs.labels["pre_safe"]),
        "post_event_safe": (inputs.post_safe, inputs.labels["post_safe"]),
        "tambon_boundaries": (inputs.boundaries, inputs.labels["boundaries"]),
        "worldcover": (inputs.worldcover, inputs.labels["worldcover"]),
        "dem_west": (inputs.dem_tiles[0], inputs.labels["dem_west"]),
        "dem_east": (inputs.dem_tiles[1], inputs.labels["dem_east"]),
    }
    if inputs.jrc_seasonality is not None:
        input_files["jrc_seasonality"] = (inputs.jrc_seasonality, inputs.labels["jrc_seasonality"])
    if inputs.acquisition_manifest is not None:
        input_files["acquisition_manifest"] = (inputs.acquisition_manifest, inputs.labels["acquisition_manifest"])
    receipt_inputs: dict[str, Any] = {
        key: {"path": label, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for key, (path, label) in input_files.items()
    }
    if manifest_note is not None:
        for role, key in (("pre", "pre_event_safe"), ("post", "post_event_safe")):
            receipt_inputs[key]["acquisition_manifest"] = manifest_note[role]
            receipt_inputs[key]["matches_the_acquisition_manifest"] = (
                manifest_note[role]["sha256_in_the_acquisition_manifest"] == receipt_inputs[key]["sha256"])
    receipt_inputs["tambon_boundaries"].update(boundary_summary)
    for name in ("v1a", "v1b"):
        receipt_inputs[f"planning_protocol_{name}"] = {
            "path": repo_label(docs / f"planning_protocol_{name}.json", root),
            "sha256": protocol_sha256[f"planning_protocol_{name}"]}
    receipt_inputs["protocol_receipts"] = {
        "path": repo_label(docs / "RECEIPTS.jsonl", root), "sha256": sha256_file(docs / "RECEIPTS.jsonl")}
    receipt_inputs["m1_v2_frozen_config"] = {
        "path": review.FROZEN_CONFIG_FILE, "sha256": binding["frozen_config_sha256"]}
    receipt_inputs["m1_v2_freeze_receipt"] = {
        "path": review.FREEZE_RECEIPT_FILE, "sha256": binding["freeze_receipt_sha256"]}
    receipt_inputs["geoid_benchmark_results"] = {
        "path": geoid["source"], "sha256": geoid["source_sha256"]}
    modules = {"builder": Path(__file__), "radar_candidates": Path(str(rc.__file__)),
               "sentinel1_sigma0": Path(str(s1.__file__)), "sar_change_v2": Path(str(sar.__file__)),
               "confidence": Path(str(confidence.__file__))}
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "plan_task": PLAN_TASK,
        "run": f"Radar flood candidates of case {CASE_ID}, eight Mae Sai tambons, three methods",
        "status": "run_receipt",
        "status_note": "Receipt of one run on real units, made with protocol v1a and v1b in force. Every run "
                       "is reported: a second run writes a new receipt that names this one.",
        "run_role": run_role,
        **common,
        "protocol_state": {"v1a": "in_force", "v1b": "in_force"},
        "m1_v2_frozen_binding": {key: value for key, value in binding.items() if key != "parameters"},
        "parameters": {
            "case": CASE_ID,
            "unit_list_source": "planning_protocol_v1a.json/case_portfolio/mae_sai_reporting_frame/units",
            "unit_ids": unit_ids,
            "boundary_layer": BOUNDARY_LAYER,
            "grid": grid_record,
            "geocoding": geocoding,
            "geocoding_label": label,
            "gcp_polynomial": {
                "order_asked_of_gdal": "none: GDAL chooses the order from the number of control points",
                "order_found": {"pre": polynomial_orders[0], "post": polynomial_orders[1]},
                "found_by": "floodguard.sentinel1_sigma0.gcp_polynomial_order",
                "used_for": ("the geocoding of both dates of this run and the displacement check" if of_record
                             else "the displacement check only; this run is not warped with the polynomial"),
            },
            "height_datum_reading": None if of_record else HEIGHT_AWARE_DATUM_READING,
            "window_margin_degrees": s1.WINDOW_MARGIN_DEGREES,
            "resampling": "bilinear on linear sigma0",
            "permanent_water_class": PERMANENT_WATER_CLASS,
            "jrc_perennial_months": JRC_PERENNIAL_MONTHS,
            "dem_slope_block": DEM_SLOPE_BLOCK,
            "slope_class_edges_degrees": list(SLOPE_CLASS_EDGES),
            "un_spider": tables["un_spider"]["configuration"],
            "m1_literal": sar.config_to_json(literal_config),
            "m1_v2": binding["parameters"],
            "threshold_shifts_db": list(rc.THRESHOLD_SHIFTS_DB),
            "displacement_check": {
                "search_cells": DISPLACEMENT_SEARCH_CELLS, "pair_search_cells": PAIR_SEARCH_CELLS,
                "pair_agreement_m": PAIR_AGREEMENT_M,
                "min_water_cells": DISPLACEMENT_MIN_WATER_CELLS, "lattice_step": DISPLACEMENT_LATTICE_STEP,
                "height_datum_readings_m": HEIGHT_DATUM_READINGS,
            },
            "coverage_min": rule.skill_unit_coverage_min,
            "abstention_max": rule.skill_abstention_fraction_max,
        },
        "inputs": receipt_inputs,
        "implementation": {
            "base_commit": commit.stdout.strip() or None,
            "base_commit_note": "The commit the working tree was on. The files below are the ones this run "
                                "loaded, identified by their own SHA-256, committed or not.",
            **{f"{name}_sha256": sha256_file(path) for name, path in modules.items()},
            "software": software_versions(),
        },
        "open_points": OPEN_POINTS,
        "not_computed": NOT_COMPUTED,
        "assumptions": assumptions,
        "limits": limits,
    }
    files = {
        "frame_units.tif": (unit_index, 0, ["tambon number in the order of the table; 0 outside the frame"]),
        "context_worldcover_2021.tif": (worldcover, 0, ["ESA WorldCover 2021 v200 class"]),
        "context_slope_degrees.tif": (slope, float("nan"), ["slope in degrees, GLO-30 averaged to 3 arc-seconds"]),
        "sigma0_pre_20240903.tif": (images["pre"], float("nan"), ["VV linear sigma0", "VH linear sigma0"]),
        "sigma0_post_20240915.tif": (images["post"], float("nan"), ["VV linear sigma0", "VH linear sigma0"]),
    }
    score_names = {
        "un_spider": "after dB divided by before dB (focal mean of 50 m)",
        "m1_literal": "delta-VH in dB, post minus pre, after the Lee filter",
        "m1_v2": "darkening of VH in dB (pre minus post), after the refined-Lee filter",
    }
    reason_legend = "; ".join(f"{code}: {label}" for code, label in rc.REASON_LABELS.items())
    for name in rc.METHODS:
        files[f"{name}_candidate.tif"] = (
            rasters[name]["candidate"], 255, ["1 flood candidate, 0 not a candidate, 255 no answer"])
        files[f"{name}_reason.tif"] = (rasters[name]["reason"], None, [reason_legend])
        files[f"{name}_score.tif"] = (rasters[name]["score"], float("nan"), [score_names[name]])
        if "levels" in rasters[name]:
            files[f"{name}_threshold_levels.tif"] = (
                rasters[name]["levels"], 255,
                ["3 candidate at the strictest threshold, 2 at the central one, 1 at the loosest only, 0 at none"])
    tags = {
        "source_timestamp": source_timestamp,
        "image_pair_utc": f"{common['source_timestamps']['pre_event_image_utc']}/{source_timestamp}",
        "confidence": "low: " + CONFIDENCE_BASIS,
        "assumptions": " | ".join(assumptions),
        "geocoding": label,
        "run_role": run_role,
        "official_warning": "false",
        "evidence": "Tier 2 own candidate: verify before action. Not validated; not an observation.",
        "planning_protocol_v1a_sha256": protocol_sha256["planning_protocol_v1a"],
        "planning_protocol_v1b_sha256": protocol_sha256["planning_protocol_v1b"],
        "attribution": "Contains modified Copernicus Sentinel data 2024",
    }
    return table, receipt, {"files": files, "grid": grid, "tags": tags}


def supersedes(table_path: Path, receipt_path: Path, table: Mapping[str, Any], reason: str,
               archive_dir: Path, archive_label: str) -> dict[str, Any]:
    """Describe the table and the receipt that a replacement run supersedes, and keep a copy of both.

    The copies go to ``archive_dir``, outside Git, under the generation time
    of the superseded run, so a superseded run that was never committed can
    still be read.
    """

    import shutil

    previous = json.loads(table_path.read_text(encoding="utf-8"))
    previous_receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}

    def figures(document: Mapping[str, Any]) -> dict[str, Any]:
        return {name: {"frame": method.get("frame"), "units": method.get("units")}
                for name, method in (document.get("methods") or {}).items()}

    stamp = str(previous.get("generated_at_utc", "unknown")).replace(":", "").replace("-", "")
    archive_dir.mkdir(parents=True, exist_ok=True)
    kept = []
    for path in (table_path, receipt_path):
        if path.exists():
            shutil.copyfile(path, archive_dir / f"{stamp}_{path.name}")
            kept.append(f"{archive_label}/{stamp}_{path.name}")
    return {
        "table_sha256": sha256_file(table_path),
        "receipt_sha256": sha256_file(receipt_path) if receipt_path.exists() else None,
        "generated_at_utc": previous.get("generated_at_utc"),
        "reason": reason,
        "same_frame_and_unit_figures": figures(previous) == figures(table),
        "copies_kept_outside_git": kept,
        "note": "The superseded table and receipt are named by SHA-256 and copied outside Git. They are in "
                "the Git history only if they were committed.",
        "runs_before_the_superseded_one": previous_receipt.get("supersedes"),
    }


def write_register_entries(register_dir: Path, paths: Sequence[Path], root: Path) -> list[str]:
    """Register a run: one small file per output, with its repository path and its SHA-256.

    ``tests/test_planning_protocol.py`` reads these files. A run that
    supersedes a registered output rewrites its entry.
    """

    register_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for path in paths:
        entry = {"path": repo_label(path, root) if _inside(path, root) else path.name, "sha256": sha256_file(path)}
        target = register_dir / f"{REGISTER_PREFIX}{path.name}"
        target.write_bytes(encode(entry))
        written.append(target.name)
    return written


def run(inputs: BuildInputs, output_dir: Path, *, geocoding: str = s1.GEOCODING_GCP_POLYNOMIAL,
        docs: Path = DOCS, root: Path = ROOT, replace_reason: str | None = None,
        notes: Sequence[str] = (), register_dir: Path | None = None) -> dict[str, Any]:
    """Compute, write the rasters, the table and the receipt, and return a short summary.

    The file names depend on the geocoding, so the sensitivity run never
    overwrites the run of record. A sensitivity run names the table and the
    receipt of the run of record by SHA-256 when they exist. With
    ``register_dir`` the table and the receipt are registered there.

    Raises:
        FileExistsError: when the table exists and no replacement reason is given.
        FileNotFoundError: when a replacement is asked for and no table exists.
        ValueError: see :func:`build`.
    """

    if geocoding not in GEOCODINGS:
        raise ValueError(f"unknown geocoding: {geocoding}")
    table_path = output_dir / GEOCODINGS[geocoding]["table"]
    receipt_path = output_dir / GEOCODINGS[geocoding]["receipt"]
    if replace_reason is None and (table_path.exists() or receipt_path.exists()):
        raise FileExistsError("the table or its receipt exists; a second run needs --replace --reason")
    if replace_reason is not None and not table_path.exists():
        raise FileNotFoundError("--replace needs an existing table")
    started = utc_now()
    table, receipt, rasters = build(inputs, geocoding=geocoding, docs=docs, root=root)
    replaced = None
    if replace_reason is not None:
        archive = inputs.raster_dir.parent / SUPERSEDED_FOLDER.name
        label = f"{inputs.labels['raster_dir'].rsplit('/', 1)[0]}/{SUPERSEDED_FOLDER.name}"
        replaced = supersedes(table_path, receipt_path, table, replace_reason, archive, label)
    raster_outputs = []
    for name, (array, nodata, descriptions) in rasters["files"].items():
        written = write_raster(inputs.raster_dir / name, array, rasters["grid"], nodata=nodata,
                               tags={**rasters["tags"], "layer": name}, descriptions=descriptions)
        raster_outputs.append({"path": f"{inputs.labels['raster_dir']}/{name}", **written, "kept_outside_git": True})
    finished = utc_now()
    table = {"schema_version": table["schema_version"], "generated_at_utc": finished,
             "receipt_file": repo_label(receipt_path, root) if _inside(receipt_path, root) else receipt_path.name,
             **{key: value for key, value in table.items() if key != "schema_version"}}
    output_dir.mkdir(parents=True, exist_ok=True)
    table_bytes = encode(table)
    table_path.write_bytes(table_bytes)
    receipt = {
        "schema_version": receipt["schema_version"],
        "generated_at_utc": finished,
        **{key: value for key, value in receipt.items() if key != "schema_version"},
        "timestamps": {"run_started_at_utc": started, "run_finished_at_utc": finished},
        "operator_notes": list(notes),
        "outputs": {
            "table": {"path": repo_label(table_path, root) if _inside(table_path, root) else table_path.name,
                      "sha256": hashlib.sha256(table_bytes).hexdigest(), "bytes": len(table_bytes)},
            "rasters": raster_outputs,
        },
    }
    if replaced is not None:
        receipt["supersedes"] = replaced
    if GEOCODINGS[geocoding]["role"] == SENSITIVITY_RUN:
        record = GEOCODINGS[s1.GEOCODING_GCP_POLYNOMIAL]
        record_table, record_receipt = output_dir / record["table"], output_dir / record["receipt"]
        receipt["run_of_record"] = {
            "table": record["table"], "receipt": record["receipt"],
            "table_sha256": sha256_file(record_table) if record_table.exists() else None,
            "receipt_sha256": sha256_file(record_receipt) if record_receipt.exists() else None,
            "note": "This sensitivity run replaces nothing. The run of record is the fallback of plan row A4.",
        }
    receipt_path.write_bytes(encode(receipt))
    registered = write_register_entries(register_dir, (table_path, receipt_path), root) if register_dir else []
    return {
        "registered": registered,
        "table": table_path.name, "table_sha256": receipt["outputs"]["table"]["sha256"],
        "receipt": receipt_path.name, "receipt_sha256": sha256_file(receipt_path),
        "rasters": len(raster_outputs), "generated_at_utc": finished,
        "candidate_area_km2": {name: method["frame"]["candidate_area_km2"] for name, method in table["methods"].items()},
        "frame_abstention": {name: method["frame"]["abstention_fraction"] for name, method in table["methods"].items()},
    }


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and make one reported run."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--external-data", type=Path, default=None,
                        help=f"external data root; default: the environment variable {EXTERNAL_DATA_VARIABLE}")
    parser.add_argument("--geocoding", choices=sorted(GEOCODINGS), default=s1.GEOCODING_GCP_POLYNOMIAL,
                        help="gcp_polynomial is the run of record (the fallback of plan row A4); "
                             "annotation_grid_with_cell_height is a sensitivity run that the plan does not name")
    parser.add_argument("--replace", action="store_true",
                        help="make a second run over an existing table; needs --reason, and the new receipt names the old")
    parser.add_argument("--reason", help="why the table is replaced (one sentence)")
    parser.add_argument("--note", action="append", default=[],
                        help="a sentence for the receipt, for example about an earlier attempt that wrote nothing")
    args = parser.parse_args(argv)
    if args.replace != bool((args.reason or "").strip()):
        parser.error("--replace and --reason go together")
    external = args.external_data or (
        Path(os.environ[EXTERNAL_DATA_VARIABLE]) if os.environ.get(EXTERNAL_DATA_VARIABLE) else None)
    if external is None:
        parser.error(f"give --external-data or set {EXTERNAL_DATA_VARIABLE}")
    try:
        summary = run(BuildInputs.under(external, args.geocoding), OUTPUT_DIR, geocoding=args.geocoding,
                      replace_reason=args.reason.strip() if args.replace else None, notes=args.note,
                      register_dir=OUTPUT_DIR / "run_register")
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
