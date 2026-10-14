"""Put the recorded reference of each tuning area of the Nan case onto its 20 m grid (case N1, tuning sets).

The rules of the case are ``docs/proposal_execution/nan_case_protocol_v1.json`` (in words:
``docs/proposal_execution/nan_case_plan_v1.md``); the grids are ``outputs/nan_case/areas_v1.json``. For each of the
three tuning areas the script reads the reference an earlier work package recorded, checks it against the record
that binds it (SHA-256 and recorded counts), and writes ``reference_20m.tif`` (uint8: 1 water, 0 dry, 255 not
compared) with a record beside it into the work folder outside Git:

``sukhothai_chip``
    The frozen THEOS-2 water rule v2 at 2 m (0 not water, 1 water, 255 unobservable). A 20 m cell is water when at
    least half of its 2 m pixels are water, dry when at least half hold a value and fewer than half are water, and
    not compared when fewer than half hold a value or its centre lies outside the chip rectangle. The Sukhothai label
    points of the team's check are written beside it, each with its 20 m cell and the label at least two of the
    three labellers gave.
``mae_sai_20241022``
    The dated agency layer of 22 October 2024 at 10 m, compared only where the dated radar check of work package 3
    compared (inside Mae Sai district, outside permanent water, with a radar value after). A 20 m cell is compared
    when at least half of its four 10 m cells were compared, and water when at least half of its compared 10 m
    cells are agency water. The layer is held at the local level (decision log R33): the rasters stay in the work
    folder and the record in Git holds whole-district figures only.
``chaiyaphum_20210928``
    The automated optical reference v2 of the final hold-out (1 temporary flood agreed by both methods, 0 both dry,
    2 water on both dates, 3 disagreement, 4 unobservable, 255 outside the area). A 20 m cell is water when at least
    half of its 10 m cells are code 1, dry when at least half are code 0 and none is code 1, and otherwise not
    compared.

A reference that cannot be read as recorded is dropped by the protocol's drop rule: the reason is written into
``outputs/nan_case/tuning_references_v1.json`` and the set is marked dropped. Nothing of the Nan frame is read: no
JAXA file, no GFM value, no THEOS-2 file of 31 July 2025 and nothing derived from one. Every path the script opens is
checked against that list first (:func:`refuse_firewalled`).

Every figure here is a count of reference cells. A radar map set against these layers gives agreement with a
reference, not accuracy. Planning guidance only; nothing here is an official warning.

Example::

    python scripts/nan_case_tuning_references.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePath
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PROTOCOL = "docs/proposal_execution/nan_case_protocol_v1.json"
PLAN = "docs/proposal_execution/nan_case_plan_v1.md"
AREAS = "outputs/nan_case/areas_v1.json"
RECORD = "outputs/nan_case/tuning_references_v1.json"
FREEZE = "outputs/nan_case/freeze_v1.json"
SCRIPT = "scripts/nan_case_tuning_references.py"
WORK = PurePath("proposal_execution") / "nan_case_v1" / "references_tuning"
LOG_NAME = "build_log.txt"
RASTER_NAME = "reference_20m.tif"
SIDE_RECORD_NAME = "reference_20m.json"
POINTS_NAME = "points_sukhothai.json"

EPSG = 32647
CELL_M = 20.0
WATER = 1
DRY = 0
NOT_COMPARED = 255
VALUE_CODES = {str(WATER): "water", str(DRY): "dry", str(NOT_COMPARED): "not compared"}

FIREWALL_PARTS: tuple[str, ...] = (
    "jaxa_sealed", "img_t2v_20250731035100", "water_v2_chip_001", "water_v2_chip_003", "chip_001_2m", "chip_003_2m",
    "held_chip_00", "gfm",
)
"""Pieces of a path that name a file of the Nan frame this lane may never open (the firewall of the case)."""

# --- the Sukhothai chip ----------------------------------------------------------------------------------------------
SUKHOTHAI = "sukhothai_chip"
SUKHOTHAI_RASTER = PurePath("proposal_execution") / "theos2_water_rule_v2" / "water_v2_sukhothai_2m.tif"
RULE_V2_FREEZE = "outputs/theos2_water_rule_v2/freeze_v1.json"
CROSS_CHECK_REFERENCE = "outputs/theos2_cross_check/sukhothai_20250730_reference_v1.json"
LABEL_DIR = "outputs/theos2_water_labels"
LABEL_SAMPLE = f"{LABEL_DIR}/sample_v1.json"
LABEL_KEY = f"{LABEL_DIR}/key_v1.json"
LABEL_FILES: tuple[str, ...] = (f"{LABEL_DIR}/labels_callixta.json", f"{LABEL_DIR}/labels_putu.json",
                                f"{LABEL_DIR}/labels_rachmania.json")
LABEL_CHIP = "sukhothai"
LABELS: tuple[str, ...] = ("water", "not_water", "cannot_tell")
RULE_V2_NO, RULE_V2_YES, RULE_V2_UNOBSERVABLE = 0, 1, 255

# --- Mae Sai ---------------------------------------------------------------------------------------------------------
MAE_SAI = "mae_sai_20241022"
MAE_SAI_FOLDER = PurePath("proposal_execution") / "dated_radar_check_v1"
MAE_SAI_RASTER = MAE_SAI_FOLDER / "dated_reference_10m.tif"
MAE_SAI_POST = MAE_SAI_FOLDER / "s1_post_gamma0.tif"
DATED_REFERENCE = "outputs/dated_radar_check/mae_sai_20241022_reference_v1.json"
DATED_RESULT = "outputs/dated_radar_check/mae_sai_20241022_v1.json"
DATED_RECEIPT = "outputs/dated_radar_check/mae_sai_20241022_v1_receipt.json"
DATED_BANDS: tuple[str, ...] = ("agency water", "in the district", "permanent water", "not at the edge of the layer",
                                "season layer")
DATED_LAYER = "CHIANGRAI_20241022_FloodExtent"
BOUNDARIES = PurePath("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
DISTRICT = "TH5709"

# --- Chaiyaphum ------------------------------------------------------------------------------------------------------
CHAIYAPHUM = "chaiyaphum_20210928"
CHAIYAPHUM_RASTER = PurePath("proposal_execution") / "automated_track" / "v2" / "final_holdout" / "automated_optical_reference_v2.tif"
HOLDOUT_RECORD = "outputs/automated_optical_v2_holdout.json"
SENTINEL2_RIGHTS_RECORD = "docs/proposal_execution/automated_track/rights_basis_v1.json"
OPTICAL_CODES = {"0": "both methods dry", "1": "temporary flood agreed by both methods", "2": "water on both dates",
                 "3": "method disagreement or indeterminate dry context", "4": "unobservable (SCL) and buffered cells",
                 "255": "outside the area of the hold-out"}

AREA_TO_SET = {SUKHOTHAI: "sukhothai_theos2_20250730", MAE_SAI: "mae_sai_20241022", CHAIYAPHUM: "chaiyaphum_20210928"}

RULES = {
    SUKHOTHAI: ("A 20 m cell is water when at least half of its 2 m pixels (50 of 100) are water under the frozen THEOS-2 "
                "water rule v2; dry when at least half hold a value (0 or 1) and fewer than half are water; not compared "
                "when fewer than half hold a value or the cell centre lies outside the chip rectangle "
                "(valid_rectangle_epsg32647 of the cross-check reference record). Pixels outside the chip hold no value."),
    MAE_SAI: ("A 10 m cell is compared where the dated radar check of work package 3 compared it: inside Mae Sai district "
              "(COD-AB tha_admin3 units with adm2_pcode TH5709), outside ESA WorldCover permanent water, with a valid "
              "radar value after. A 20 m cell is compared when at least half of its four 10 m cells (two or more) were "
              "compared; it is water when at least half of its compared 10 m cells are agency water, dry otherwise; "
              "every other 20 m cell is not compared."),
    CHAIYAPHUM: ("A 20 m cell is water when at least half of its four 10 m cells (two or more) are code 1; dry when at "
                 "least half are code 0 and none is code 1; otherwise not compared. Codes 2, 3, 4 and 255 are neither "
                 "water nor dry, and so are 10 m cells outside the raster."),
}

SOURCE_TIMESTAMPS = {
    SUKHOTHAI: "THEOS-2 2025-07-30T03:33:31Z",
    MAE_SAI: "agency layer dated 2024-10-22 (UNOSAT and GISTDA, product 4009); radar check pass 2024-10-21T23:16:14Z",
    CHAIYAPHUM: "Sentinel-2B 2021-09-28T03:53:49Z (event), dry context Sentinel-2B 2021-09-18T03:53:47Z",
}

ASSUMPTIONS = [
    "Each reference is the layer an earlier work package recorded, read unchanged and checked against the SHA-256 and the counts of the record that binds it.",
    "A 20 m cell takes part in tuning only where the rule of its set gives water (1) or dry (0); every other cell is 255 and takes no part.",
    "Sukhothai: a 2 m pixel holds a value when the frozen rule v2 gave it 0 or 1; 255 (cloud) and pixels outside the chip hold none.",
    "Mae Sai: the rule given for the set is silent on 20 m cells of which only one of four 10 m cells was compared; this lane leaves them out, by the half rule the other two sets use, and counts them.",
    "Mae Sai: where the agency mapped no water the cell counts as dry, as in the dated radar check; the layer has no 'not observed' class.",
    "Chaiyaphum: code 2 records water on both optical dates, not independently established permanent water, and is not compared.",
    "No radar map is set against any reference here: the counts describe the references only.",
]

LIMITS = [
    "The references are not ground observations: an optical rule at Sukhothai, an agency layer at Mae Sai that was not checked in the field, and two automated optical methods at Chaiyaphum.",
    "Sukhothai and Mae Sai were seen as development data before this case (R37); Chaiyaphum's optical reference was used once for the optical v2 test.",
    "Any figure computed against these layers is agreement with a reference, not accuracy. Planning guidance only.",
]


class BuildError(RuntimeError):
    """The run cannot start, or it would break the order or the firewall of the case."""


class TuningReferenceError(ValueError):
    """A reference cannot be read as recorded: the protocol's drop rule applies and the set is dropped."""


Grid = tuple[float, float, int, int]
"""West, north, rows, columns of a north-up grid (as ``floodguard.s1_rtc.Grid``)."""


# ---------------------------------------------------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------------------------------------------------

def refuse_firewalled(path: Path | PurePath | str) -> Path:
    """Return ``path`` as a :class:`Path`, or raise :class:`BuildError` when it names a file behind the firewall.

    The firewall of the case: the sealed JAXA folder, any GFM file, the THEOS-2 files of 31 July 2025 and anything
    derived from them (the rule v2 rasters and caches of chip_001 and chip_003, the held chips).
    """

    text = PurePath(path).as_posix().lower()
    for part in FIREWALL_PARTS:
        if part in text:
            raise BuildError(f"refused to open {PurePath(path).name!r}: it lies behind the firewall of the case ({part})")
    return Path(path)


def grid_of(area: Mapping[str, Any]) -> Grid:
    """The (west, north, rows, columns) of an area of ``outputs/nan_case/areas_v1.json``."""

    grid = area["grid"]
    return (float(grid["west"]), float(grid["north"]), int(grid["rows"]), int(grid["cols"]))


def fine_placement(fine_west: float, fine_north: float, fine_cell_m: float, grid: Grid,
                   cell_m: float = CELL_M) -> tuple[int, int, int]:
    """How a fine raster sits in a coarse grid: (factor, row offset, column offset), offsets in fine pixels.

    The fine pixels must nest in the coarse cells: the coarse cell is a whole number of fine pixels and both grids
    share cell edges. A positive offset means the fine raster starts inside the coarse grid.

    Raises:
        TuningReferenceError: when the two grids do not nest.
    """

    west, north, _rows, _columns = grid
    factor = cell_m / fine_cell_m
    columns = (fine_west - west) / fine_cell_m
    rows = (north - fine_north) / fine_cell_m
    for name, value in (("cell ratio", factor), ("column offset", columns), ("row offset", rows)):
        if abs(value - round(value)) > 1e-6:
            raise TuningReferenceError(f"the fine raster does not nest in the 20 m grid: {name} is {value}")
    if round(factor) < 1:
        raise TuningReferenceError("the fine raster is coarser than the 20 m grid")
    return int(round(factor)), int(round(rows)), int(round(columns))


def block_counts(mask: np.ndarray, shape: tuple[int, int], factor: int, row_offset: int = 0,
                 column_offset: int = 0) -> np.ndarray:
    """Count the true fine pixels of ``mask`` inside each coarse cell of a grid of ``shape``.

    ``mask`` starts ``row_offset`` fine rows and ``column_offset`` fine columns from the corner of the coarse grid
    (negative where it starts before it). Fine pixels outside the coarse grid are ignored; coarse area the mask does
    not cover counts as false.
    """

    rows, columns = shape
    canvas = np.zeros((rows * factor, columns * factor), dtype=bool)
    source = np.asarray(mask, dtype=bool)
    target_row, target_column = max(row_offset, 0), max(column_offset, 0)
    source_row, source_column = max(-row_offset, 0), max(-column_offset, 0)
    height = min(source.shape[0] - source_row, canvas.shape[0] - target_row)
    width = min(source.shape[1] - source_column, canvas.shape[1] - target_column)
    if height > 0 and width > 0:
        canvas[target_row:target_row + height, target_column:target_column + width] = \
            source[source_row:source_row + height, source_column:source_column + width]
    return canvas.reshape(rows, factor, columns, factor).sum(axis=(1, 3), dtype=np.int32)


def centres_inside(grid: Grid, rectangle: Mapping[str, float], cell_m: float = CELL_M) -> np.ndarray:
    """True for the cells of ``grid`` whose centre lies inside ``rectangle`` (west, south, east, north; edges inside)."""

    west, north, rows, columns = grid
    x = west + (np.arange(columns) + 0.5) * cell_m
    y = north - (np.arange(rows) + 0.5) * cell_m
    inside_x = (x >= float(rectangle["west"])) & (x <= float(rectangle["east"]))
    inside_y = (y >= float(rectangle["south"])) & (y <= float(rectangle["north"]))
    return inside_y[:, None] & inside_x[None, :]


def theos2_cells(water_pixels: np.ndarray, valued_pixels: np.ndarray, centre_inside: np.ndarray,
                 pixels_per_cell: int) -> np.ndarray:
    """The 20 m reference of the THEOS-2 rule from per-cell pixel counts.

    Water when at least half of the cell's pixels are water; dry when at least half hold a value and fewer than
    half are water; not compared when fewer than half hold a value or the centre lies outside the chip.
    """

    water_pixels = np.asarray(water_pixels)
    valued_pixels = np.asarray(valued_pixels)
    if np.any(water_pixels > valued_pixels):
        raise ValueError("a cell cannot hold more water pixels than pixels with a value")
    water = 2 * water_pixels >= pixels_per_cell
    dry = (2 * valued_pixels >= pixels_per_cell) & ~water
    reference = np.full(water_pixels.shape, NOT_COMPARED, dtype="uint8")
    inside = np.asarray(centre_inside, dtype=bool)
    reference[dry & inside] = DRY
    reference[water & inside] = WATER
    return reference


def agency_cells(water_compared: np.ndarray, compared: np.ndarray, cells_per_cell: int) -> np.ndarray:
    """The 20 m reference of the agency layer from per-cell counts of compared 10 m cells.

    A 20 m cell is compared when at least half of its 10 m cells were compared; it is water when at least half of
    its compared 10 m cells are agency water, and dry otherwise.
    """

    water_compared = np.asarray(water_compared)
    compared = np.asarray(compared)
    if np.any(water_compared > compared):
        raise ValueError("a cell cannot hold more compared water cells than compared cells")
    answered = (compared > 0) & (2 * compared >= cells_per_cell)
    water = answered & (2 * water_compared >= compared)
    reference = np.full(compared.shape, NOT_COMPARED, dtype="uint8")
    reference[answered & ~water] = DRY
    reference[water] = WATER
    return reference


def optical_cells(code_1: np.ndarray, code_0: np.ndarray, cells_per_cell: int) -> np.ndarray:
    """The 20 m reference of the automated optical reference from per-cell counts of codes 1 and 0.

    Water when at least half of the 10 m cells are code 1; dry when at least half are code 0 and none is code 1;
    otherwise not compared.
    """

    code_1 = np.asarray(code_1)
    code_0 = np.asarray(code_0)
    if np.any(code_1 + code_0 > cells_per_cell):
        raise ValueError("a cell cannot hold more 10 m cells than it has")
    water = 2 * code_1 >= cells_per_cell
    dry = (2 * code_0 >= cells_per_cell) & (code_1 == 0)
    reference = np.full(code_1.shape, NOT_COMPARED, dtype="uint8")
    reference[dry] = DRY
    reference[water] = WATER
    return reference


def reference_counts(reference: np.ndarray, cell_m: float = CELL_M) -> dict[str, Any]:
    """The cells of a 20 m reference: compared, water, dry, not compared, the water share of the compared cells."""

    reference = np.asarray(reference)
    unknown = sorted(set(np.unique(reference).tolist()) - {WATER, DRY, NOT_COMPARED})
    if unknown:
        raise ValueError(f"values that are not a reference code: {unknown}")
    water = int((reference == WATER).sum())
    dry = int((reference == DRY).sum())
    compared = water + dry
    cell_km2 = cell_m * cell_m / 1e6
    return {
        "cells": int(reference.size),
        "compared_cells": compared,
        "water_cells": water,
        "dry_cells": dry,
        "not_compared_cells": int(reference.size) - compared,
        "water_share_of_compared": round(water / compared, 6) if compared else None,
        "compared_km2": round(compared * cell_km2, 4),
        "water_km2": round(water * cell_km2, 4),
    }


def label_two_of_three(given: Sequence[str]) -> str | None:
    """The label at least two of three labellers gave (water, not water or cannot tell); ``None`` when all differ."""

    if len(given) != 3:
        raise ValueError("a point needs the labels of exactly three labellers")
    unknown = sorted({label for label in given if label not in LABELS})
    if unknown:
        raise ValueError(f"labels that are not one of the three: {unknown}")
    return next((label for label in LABELS if list(given).count(label) >= 2), None)


def cell_of(x: float, y: float, grid: Grid, cell_m: float = CELL_M) -> tuple[int, int] | None:
    """The (row, column) of the grid cell that holds the point (x, y), or ``None`` outside the grid."""

    west, north, rows, columns = grid
    row = int(np.floor((north - y) / cell_m))
    column = int(np.floor((x - west) / cell_m))
    if 0 <= row < rows and 0 <= column < columns:
        return row, column
    return None


def sukhothai_points(points: Sequence[Mapping[str, Any]], labels: Mapping[str, Mapping[str, str]], grid: Grid,
                     reference: np.ndarray, cell_m: float = CELL_M) -> list[dict[str, Any]]:
    """The Sukhothai label points with their 20 m cell, the label at least two of three gave and the reference there.

    Only points whose chip is ``sukhothai`` are kept; any other point is skipped before its position or label is
    looked at. ``labels`` maps each labeller to their label of every Sukhothai point.
    """

    result: list[dict[str, Any]] = []
    labellers = sorted(labels)
    if len(labellers) != 3:
        raise ValueError("the Sukhothai points need the labels of three labellers")
    for point in points:
        if point.get("chip") != LABEL_CHIP:
            continue
        identifier = str(point["id"])
        given = [labels[labeller][identifier] for labeller in labellers]
        cell = cell_of(float(point["x"]), float(point["y"]), grid, cell_m)
        result.append({
            "id": identifier,
            "x": float(point["x"]),
            "y": float(point["y"]),
            "row_2m": int(point["row"]),
            "column_2m": int(point["column"]),
            "stratum_of_the_draw": str(point["group"]),
            "row_20m": None if cell is None else cell[0],
            "column_20m": None if cell is None else cell[1],
            "label_two_of_three": label_two_of_three(given),
            "reference_20m": None if cell is None else int(reference[cell]),
        })
    return result


def points_crosstab(points: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Counts of the points by the label at least two of three gave and by the 20 m reference at their cell."""

    labels = [*LABELS, "no_two_alike"]
    values = {WATER: "water", DRY: "dry", NOT_COMPARED: "not_compared", None: "outside_the_grid"}
    table = {label: {name: 0 for name in values.values()} for label in labels}
    for point in points:
        label = point["label_two_of_three"] or "no_two_alike"
        table[label][values[point["reference_20m"]]] += 1
    return table


# ---------------------------------------------------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------------------------------------------------

def now_utc() -> str:
    """The time now, UTC, to the second."""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    """The SHA-256 of a file's bytes."""

    digest = hashlib.sha256()
    with refuse_firewalled(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write JSON as UTF-8 with LF line ends, so the SHA-256 holds for the bytes Git stores."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, indent=1, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    """Read a JSON file after the firewall check."""

    return json.loads(refuse_firewalled(path).read_text(encoding="utf-8"))


class Log:
    """Lines of progress, printed and appended to the log of the work folder (LF line ends)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, text: str) -> None:
        line = f"{now_utc()} {text}"
        print(line, flush=True)
        with open(self.path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")


def envelope(source_timestamp: str) -> dict[str, Any]:
    """The fields every record of the case carries."""

    return {
        "generated_at_utc": now_utc(),
        "source_timestamp": source_timestamp,
        "confidence_class": "low",
        "confidence_basis": "Reference layers from one optical scene, one agency layer and two automated optical methods; no ground check.",
        "assumptions": ASSUMPTIONS,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }


def write_reference(path: Path, reference: np.ndarray, grid: Grid, cell_m: float = CELL_M) -> str:
    """Write a 20 m reference as a tiled, DEFLATE-compressed uint8 GeoTIFF, read it back, and return its SHA-256."""

    import rasterio
    from rasterio.transform import from_origin

    west, north, rows, columns = grid
    if reference.shape != (rows, columns):
        raise BuildError(f"the reference is {reference.shape}, the grid {rows} by {columns}")
    smaller = min(rows, columns)
    block = 256 if smaller >= 256 else 128 if smaller >= 128 else 16
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=rows, width=columns, count=1, dtype="uint8",
                       nodata=NOT_COMPARED, crs=f"EPSG:{EPSG}", compress="deflate", tiled=True, blockxsize=block,
                       blockysize=block, transform=from_origin(west, north, cell_m, cell_m)) as target:
        target.write(np.asarray(reference, dtype="uint8"), 1)
        target.set_band_description(1, "reference: 1 water, 0 dry, 255 not compared")
    with rasterio.open(path) as source:
        if not np.array_equal(source.read(1), reference):
            raise BuildError(f"{path.name} does not read back as written")
    return sha256_file(path)


def open_raster(path: Path) -> Any:
    """Open a raster after the firewall check; a missing file cannot be read as recorded."""

    import rasterio

    if not refuse_firewalled(path).exists():
        raise TuningReferenceError(f"{path.name} is not in the work folder of its work package")
    return rasterio.open(path)


def require_hash(path: Path, recorded: str, what: str) -> str:
    """The SHA-256 of ``path``, which must be the one its record holds."""

    found = sha256_file(path)
    if found != recorded:
        raise TuningReferenceError(f"{path.name} is not the {what} its record binds (SHA-256 {found}, recorded {recorded})")
    return found


def git_file(relative: str) -> dict[str, str]:
    """A file of the repository by path and SHA-256."""

    return {"path": relative, "sha256": sha256_file(ROOT / relative)}


# ---------------------------------------------------------------------------------------------------------------------
# The three sets
# ---------------------------------------------------------------------------------------------------------------------

def build_sukhothai(external: Path, grid: Grid) -> tuple[np.ndarray, dict[str, Any]]:
    """The 20 m reference of the Sukhothai chip from the frozen THEOS-2 water rule v2."""

    freeze = read_json(ROOT / RULE_V2_FREEZE)
    recorded = freeze["frozen_rule"]["chips"][LABEL_CHIP]   # only the Sukhothai entry is looked at
    del freeze
    raster_record = recorded["raster_outside_git"]
    path = external / SUKHOTHAI_RASTER
    if raster_record["name"] != path.name:
        raise TuningReferenceError(f"the freeze record names {raster_record['name']}, not {path.name}")
    with open_raster(path) as source:
        found = require_hash(path, raster_record["sha256"], "frozen rule v2 raster")
        if source.crs is None or source.crs.to_epsg() != EPSG or source.count != 1 or source.dtypes[0] != "uint8":
            raise TuningReferenceError(f"{path.name} is not one uint8 band in EPSG:{EPSG}")
        transform = source.transform
        if abs(transform.a - 2.0) > 1e-9 or abs(transform.e + 2.0) > 1e-9 or transform.b or transform.d:
            raise TuningReferenceError(f"{path.name} is not a north-up raster of 2 m pixels")
        pixels = source.read(1)
        bounds = source.bounds
    values = set(np.unique(pixels).tolist())
    if not values <= {RULE_V2_NO, RULE_V2_YES, RULE_V2_UNOBSERVABLE}:
        raise TuningReferenceError(f"{path.name} holds values outside 0, 1 and 255: {sorted(values)}")
    summary = recorded["rule_v2"]
    water_px = pixels == RULE_V2_YES
    valued_px = pixels != RULE_V2_UNOBSERVABLE
    checks = {
        "sha256_matches_the_freeze_record": True,
        "water_pixels": int(water_px.sum()),
        "water_pixels_recorded": int(summary["water_pixels"]),
        "unobservable_pixels": int((~valued_px).sum()),
        "unobservable_pixels_recorded": int(summary["unobservable_cloud_pixels"]),
    }
    if checks["water_pixels"] != checks["water_pixels_recorded"] or \
            checks["unobservable_pixels"] != checks["unobservable_pixels_recorded"]:
        raise TuningReferenceError(f"{path.name} does not hold the pixel counts of the freeze record: {checks}")

    cross = read_json(ROOT / CROSS_CHECK_REFERENCE)
    rectangle = {key: float(value) for key, value in cross["theos2_scene"]["valid_rectangle_epsg32647"].items()}
    raster_rectangle = {"west": bounds.left, "south": bounds.bottom, "east": bounds.right, "north": bounds.top}
    checks["raster_covers_the_chip_rectangle_exactly"] = all(abs(raster_rectangle[key] - rectangle[key]) < 1e-6
                                                             for key in rectangle)

    factor, row_offset, column_offset = fine_placement(transform.c, transform.f, 2.0, grid)
    shape = (grid[2], grid[3])
    water = block_counts(water_px, shape, factor, row_offset, column_offset)
    valued = block_counts(valued_px, shape, factor, row_offset, column_offset)
    inside = centres_inside(grid, rectangle)
    reference = theos2_cells(water, valued, inside, factor * factor)
    half = 2 * valued >= factor * factor
    details = {
        "source": {
            "what": "the frozen THEOS-2 water rule v2 (floodguard.theos2_water_rule_v2.water_v2) on the Sukhothai chip",
            "file": f"<external>/{SUKHOTHAI_RASTER.as_posix()}",
            "sha256": found,
            "bound_by": git_file(RULE_V2_FREEZE),
            "value_codes": {"0": "not water", "1": "water", "255": "unobservable (cloud)"},
            "scene": cross["theos2_scene"]["file_name"],
            "chip_rectangle_epsg32647": rectangle,
            "chip_rectangle_from": git_file(CROSS_CHECK_REFERENCE),
            "pixel_m": 2.0,
            "pixels_per_20m_cell": factor * factor,
            "offset_in_2m_pixels": {"rows": row_offset, "columns": column_offset},
        },
        "checks": checks,
        "not_compared_by_reason": {
            "fewer_than_half_of_the_pixels_hold_a_value": int((~half).sum()),
            "at_least_half_hold_a_value_but_the_centre_lies_outside_the_chip": int((half & ~inside).sum()),
        },
    }
    return reference, details


def build_points(grid: Grid, reference: np.ndarray) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The Sukhothai label points of the team's check. No position or label of another chip is kept."""

    sample = read_json(ROOT / LABEL_SAMPLE)
    key_path = ROOT / LABEL_KEY
    key_sha = sha256_file(key_path)
    if key_sha != sample["key_outside_git"]["sha256"]:
        raise TuningReferenceError("the label key in the repository is not the key the draw record binds")
    groups = sample["chips"][LABEL_CHIP]["pixels_by_group"]
    sample_id = sample["sample_id"]
    del sample
    key = read_json(key_path)
    if int(key.get("epsg", 0)) != EPSG:
        raise TuningReferenceError(f"the label key is not in EPSG:{EPSG}")
    points = [dict(point) for point in key["points"] if point.get("chip") == LABEL_CHIP]
    del key   # the points of the other chips are dropped unread
    identifiers = [str(point["id"]) for point in points]
    labels: dict[str, dict[str, str]] = {}
    files = []
    for relative in LABEL_FILES:
        record = read_json(ROOT / relative)
        if record.get("sample_id") != sample_id:
            raise TuningReferenceError(f"{relative} was made for another draw of points")
        given = record["labels"]
        missing = [identifier for identifier in identifiers if identifier not in given]
        if missing:
            raise TuningReferenceError(f"{relative} has no label for {len(missing)} Sukhothai points")
        labels[str(record["labeller"])] = {identifier: str(given[identifier]["label"]) for identifier in identifiers}
        del record, given   # the labels of the other chips are dropped unread
        files.append(git_file(relative))
    kept = sukhothai_points(points, labels, grid, reference)
    summary = {
        "points": len(kept),
        "labellers": sorted(labels),
        "key": {"path": LABEL_KEY, "sha256": key_sha},
        "label_files": files,
        "points_by_label_and_reference_cell": points_crosstab(kept),
        "pixels_by_stratum_of_the_draw": groups,
        "note": "Points were drawn at random within six strata of rule v1 (outputs/theos2_water_labels/sample_v1.json); "
                "a figure from them needs the stratum weights. Only the Sukhothai points were kept; the key and the "
                "label files were parsed whole as JSON and every other point was dropped unread.",
    }
    return kept, summary


def build_mae_sai(external: Path, grid: Grid) -> tuple[np.ndarray, dict[str, Any]]:
    """The 20 m reference of Mae Sai from the dated agency layer, where the dated radar check compared."""

    import geopandas as gpd
    from rasterio.features import rasterize
    import shapely

    record = read_json(ROOT / DATED_REFERENCE)
    result = read_json(ROOT / DATED_RESULT)
    receipt = read_json(ROOT / DATED_RECEIPT)
    raster_record = record["rasters_outside_git"]["dated_reference_10m.tif"]
    if tuple(raster_record["bands"]) != DATED_BANDS:
        raise TuningReferenceError(f"the reference record names the bands {raster_record['bands']}")
    path = external / MAE_SAI_RASTER
    with open_raster(path) as source:
        found = require_hash(path, raster_record["sha256"], "dated reference raster")
        grid_10m = record["grid_10m"]
        transform = source.transform
        if (source.count != len(DATED_BANDS) or source.crs is None or source.crs.to_epsg() != EPSG
                or abs(transform.c - grid_10m["west"]) > 1e-6 or abs(transform.f - grid_10m["north"]) > 1e-6
                or source.height != grid_10m["rows"] or source.width != grid_10m["columns"]
                or abs(transform.a - grid_10m["cell_m"]) > 1e-9):
            raise TuningReferenceError(f"{path.name} is not on the 10 m grid of its record")
        agency, in_district, permanent, _interior, _season = (source.read(band).astype(bool) for band in range(1, 6))
    post_path = external / MAE_SAI_POST
    with open_raster(post_path) as source:
        post_sha = require_hash(post_path, receipt["inputs"]["sentinel1"]["post"]["window_sha256"], "radar after-image window")
        valid_post = np.isfinite(source.read().astype("float64")).all(axis=0)
    compared_10m = in_district & ~permanent & valid_post
    counts = record["counts"]
    checks = {
        "sha256_matches_the_reference_record": True,
        "district_cells": int(in_district.sum()),
        "district_cells_recorded": int(counts["district_cells"]),
        "compared_10m_cells": int(compared_10m.sum()),
        "compared_10m_cells_recorded": int(result["compared_cells"]["cells"]),
        "agency_water_10m_cells_compared": int((agency & compared_10m).sum()),
        "agency_water_10m_cells_compared_recorded": int(result["compared_cells"]["reference_wet_cells"]),
        "district_cells_without_radar_after": int((in_district & ~permanent & ~valid_post).sum()),
    }
    for name in ("district_cells", "compared_10m_cells", "agency_water_10m_cells_compared"):
        if checks[name] != checks[f"{name}_recorded"]:
            raise TuningReferenceError(f"{path.name} does not give the recorded {name}: {checks}")

    # The district from COD-AB, as the reference stage of the dated radar check drew it.
    boundary_path = refuse_firewalled(external / BOUNDARIES)
    if not boundary_path.exists():
        raise TuningReferenceError("the COD-AB boundary file is not in the external data root")
    units = gpd.read_file(f"/vsizip/{boundary_path.as_posix()}", layer="tha_admin3",
                          where=f"adm2_pcode = '{DISTRICT}'").to_crs(EPSG)
    district = shapely.union_all(list(units.geometry))
    redrawn = rasterize([(district, 1)], out_shape=in_district.shape, transform=transform, fill=0,
                        dtype="uint8").astype(bool)
    checks["district_units"] = int(len(units))
    checks["district_redrawn_from_cod_ab_equals_band_2"] = bool(np.array_equal(redrawn, in_district))
    if not checks["district_redrawn_from_cod_ab_equals_band_2"]:
        raise TuningReferenceError("the district drawn from COD-AB is not the district band of the dated reference")

    factor, row_offset, column_offset = fine_placement(transform.c, transform.f, float(grid_10m["cell_m"]), grid)
    shape = (grid[2], grid[3])
    compared = block_counts(compared_10m, shape, factor, row_offset, column_offset)
    water = block_counts(agency & compared_10m, shape, factor, row_offset, column_offset)
    reference = agency_cells(water, compared, factor * factor)
    partial = (compared > 0) & (2 * compared < factor * factor)
    details = {
        "source": {
            "what": "the layer UNOSAT and GISTDA dated 22 October 2024 (CHIANGRAI_20241022_FloodExtent), as rasterised "
                    "on 10 m by the dated radar check of work package 3 (cell centre inside the layer)",
            "file": f"<external>/{MAE_SAI_RASTER.as_posix()}",
            "sha256": found,
            "bound_by": git_file(DATED_REFERENCE),
            "compared_cells_from": git_file(DATED_RESULT),
            "bands": {str(index): name for index, name in enumerate(DATED_BANDS, start=1)},
            "band_used_as_reference": "1 (agency water)",
            "compared_10m": "band 2 (in the district) and not band 3 (permanent water) and a finite VV and VH value "
                            "in the radar after-image window of the check",
            "radar_after_window": {"file": f"<external>/{MAE_SAI_POST.as_posix()}", "sha256": post_sha,
                                   "bound_by": git_file(DATED_RECEIPT), "read_for": "its valid cells only"},
            "boundaries": f"<external>/{BOUNDARIES.as_posix()}, layer tha_admin3, adm2_pcode {DISTRICT}",
            "cells_per_20m_cell": factor * factor,
        },
        "checks": checks,
        "not_compared_by_reason": {
            "no_10m_cell_compared": int((compared == 0).sum()),
            "one_of_four_10m_cells_compared": int(partial.sum()),
            "of_those_with_the_one_cell_agency_water": int((partial & (water > 0)).sum()),
        },
        "rights_note": "Held at the local level (decision log R33): the rasters stay in the work folder; this record "
                       "holds whole-district figures only.",
    }
    return reference, details


def build_chaiyaphum(external: Path, grid: Grid) -> tuple[np.ndarray, dict[str, Any]]:
    """The 20 m reference of Chaiyaphum from the automated optical reference v2 of the final hold-out."""

    record = read_json(ROOT / HOLDOUT_RECORD)
    path = external / CHAIYAPHUM_RASTER
    with open_raster(path) as source:
        found = require_hash(path, record["label_raster_sha256"], "automated optical reference")
        transform = source.transform
        recorded_grid = record["grid"]
        expected = [float(value) for value in recorded_grid["transform"]]
        if (source.crs is None or source.crs.to_epsg() != EPSG or source.count != 1
                or source.width != int(recorded_grid["width"]) or source.height != int(recorded_grid["height"])
                or any(abs(a - b) > 1e-6 for a, b in zip(list(transform)[:6], expected))):
            raise TuningReferenceError(f"{path.name} is not on the grid its record names")
        codes = source.read(1)
    values = set(np.unique(codes).tolist())
    if not values <= {0, 1, 2, 3, 4, 255}:
        raise TuningReferenceError(f"{path.name} holds codes outside 0 to 4 and 255: {sorted(values)}")
    found_counts = {str(code): int((codes == code).sum()) for code in range(5)}
    recorded_counts = {str(code): int(count) for code, count in record["class_counts"].items()}
    checks = {
        "sha256_matches_the_holdout_record": True,
        "class_counts": found_counts,
        "class_counts_recorded": recorded_counts,
        "cells_outside_the_area_code_255": int((codes == 255).sum()),
    }
    if found_counts != recorded_counts:
        raise TuningReferenceError(f"{path.name} does not hold the class counts of its record: {checks}")

    factor, row_offset, column_offset = fine_placement(transform.c, transform.f, float(transform.a), grid)
    shape = (grid[2], grid[3])
    code_1 = block_counts(codes == 1, shape, factor, row_offset, column_offset)
    code_0 = block_counts(codes == 0, shape, factor, row_offset, column_offset)
    reference = optical_cells(code_1, code_0, factor * factor)
    not_compared = reference == NOT_COMPARED
    details = {
        "source": {
            "what": "automated_optical_reference_v2.tif of the optical v2 final hold-out (two automated optical methods "
                    "on Sentinel-2B of 2021-09-28, dry context 2021-09-18)",
            "file": f"<external>/{CHAIYAPHUM_RASTER.as_posix()}",
            "sha256": found,
            "bound_by": git_file(HOLDOUT_RECORD),
            "value_codes": OPTICAL_CODES,
            "codes_described_in": "docs/proposal_execution/GATE_RESEARCH_DOSSIER.md and outputs/automated_optical_v2_holdout.json",
            "cells_per_20m_cell": factor * factor,
            "offset_in_10m_cells": {"rows": row_offset, "columns": column_offset},
        },
        "checks": checks,
        "not_compared_by_reason": {
            "with_one_code_1_cell": int((not_compared & (code_1 == 1)).sum()),
            "without_code_1_and_fewer_than_half_code_0": int((not_compared & (code_1 == 0)).sum()),
        },
    }
    return reference, details


# ---------------------------------------------------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------------------------------------------------

def rights_of(area: str) -> dict[str, Any]:
    """The rights level of a set and what it allows in Git."""

    from floodguard import rights

    if area == MAE_SAI:
        grant = rights.RightsRegistry(ROOT).require_use(rights.PRODUCT_4009, layer=DATED_LAYER,
                                                        source=rights.SOURCE_PRODUCT_4009)
        return {"rights_level": grant.rights_level, "level_from": "floodguard.rights registry grant",
                "grant": grant.as_record(),
                "in_git": "whole-district counts and shares only (decision log R33)",
                "outside_git": [RASTER_NAME, SIDE_RECORD_NAME]}
    if area == SUKHOTHAI:
        return {"rights_level": "unassigned", "level_from": "no record of THEOS-2 in floodguard.rights.REGISTERED_RECORDS",
                "basis": "THEOS-2 sample imagery provided by GISTDA for GeoHackathon 2026; the owner reported on 3 July "
                         "2026 that it can be used freely (docs/theos2_usage_terms_log.md). Protocol N1 (rights_in_git) "
                         "allows THEOS-2-derived figures in Git and keeps the originals and every raster outside Git.",
                "in_git": "counts of the 20 m reference and of the label points (the points themselves are already "
                          "committed in outputs/theos2_water_labels/)",
                "outside_git": [RASTER_NAME, SIDE_RECORD_NAME, POINTS_NAME]}
    try:
        rights.RightsRegistry(ROOT).require_use(rights.SENTINEL2_AUTOMATED_TRACK, source=rights.SOURCE_SENTINEL2)
        refusal = None
    except rights.RightsRefusedError as error:
        refusal = str(error)
    return {"rights_level": "unassigned",
            "level_from": "the registry refuses the record of the automated optical track"
                          if refusal else "the registry grants the record of the automated optical track",
            "registry_answer": refusal,
            "basis": "Copernicus Sentinel-2 Level-2A data under the Copernicus legal notice, which permits "
                     "reproduction, distribution and adaptation with credit (record " + SENTINEL2_RIGHTS_RECORD + ", "
                     "an automated legal-notice record not signed by a human). Protocol N1 (rights_in_git) allows "
                     "records and figures of Copernicus Sentinel data in Git; rasters stay outside Git.",
            "credit": "Contains modified Copernicus Sentinel data 2021",
            "in_git": "counts of the 20 m reference",
            "outside_git": [RASTER_NAME, SIDE_RECORD_NAME]}


BUILDERS = {SUKHOTHAI: build_sukhothai, MAE_SAI: build_mae_sai, CHAIYAPHUM: build_chaiyaphum}


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    """Build the three tuning references and write the record of the set."""

    external = Path(arguments.external_root)
    if not external.is_dir():
        raise BuildError(f"the external data root {external} is not a folder")
    if (ROOT / FREEZE).exists():
        raise BuildError("the method of the case is frozen; the references it was tuned on are not rebuilt after the freeze")
    record_path = ROOT / RECORD
    if record_path.exists() and not arguments.replace:
        raise BuildError(f"{RECORD} exists; use --replace with --reason")
    if arguments.replace and not arguments.reason:
        raise BuildError("--replace needs --reason")
    work = external / WORK
    log = Log(work / LOG_NAME)
    log(f"start: {SCRIPT}")
    areas_record = read_json(ROOT / AREAS)
    protocol = read_json(ROOT / PROTOCOL)
    protocol_sets = {entry["id"]: entry for entry in protocol["tuning"]["sets"]}

    sets: dict[str, Any] = {}
    for area, builder in BUILDERS.items():
        area_record = areas_record["areas"][area]
        if area_record.get("role") != "tuning":
            raise BuildError(f"{area} is not a tuning area in {AREAS}")
        grid = grid_of(area_record)
        protocol_set = protocol_sets[AREA_TO_SET[area]]
        entry: dict[str, Any] = {
            "protocol_set_id": AREA_TO_SET[area],
            "protocol_reference": protocol_set["reference"],
            "source_timestamp": SOURCE_TIMESTAMPS[area],
            "grid_20m": {"epsg": EPSG, "cell_m": CELL_M, "west": grid[0], "north": grid[1], "rows": grid[2], "cols": grid[3]},
            "rule": RULES[area],
            "rights": rights_of(area),
        }
        log(f"{area}: reading the reference")
        try:
            reference, details = builder(external, grid)
        except TuningReferenceError as error:
            log(f"{area}: dropped: {error}")
            entry.update({"status": "dropped", "dropped_reason": str(error),
                          "drop_rule": protocol_set.get("drop_rule", "the drop rule of the protocol (set dropped before "
                                                                    "the freeze, with the reason recorded)")})
            sets[area] = entry
            continue
        counts = reference_counts(reference)
        folder = work / area
        raster_sha = write_reference(folder / RASTER_NAME, reference, grid)
        outside: dict[str, Any] = {RASTER_NAME: {"sha256": raster_sha}}
        side = {
            "schema": "floodguard.nan_case_tuning_reference.v1",
            **envelope(SOURCE_TIMESTAMPS[area]),
            "area": area,
            "protocol": git_file(PROTOCOL),
            "areas": git_file(AREAS),
            "raster": {"name": RASTER_NAME, "sha256": raster_sha, "dtype": "uint8", "value_codes": VALUE_CODES},
            "grid_20m": entry["grid_20m"],
            "rule": RULES[area],
            "counts": counts,
            **details,
            "rights": entry["rights"],
            "code": git_file(SCRIPT),
            "limits": LIMITS,
        }
        if area == SUKHOTHAI:
            points, points_summary = build_points(grid, reference)
            points_record = {
                "schema": "floodguard.nan_case_tuning_points.v1",
                **envelope(SOURCE_TIMESTAMPS[area]),
                "what_this_is": "The label points of the team's THEOS-2 water check on the Sukhothai chip only, with "
                                "their cell of the 20 m grid, the label at least two of the three labellers gave "
                                "(null where all three differ) and the 20 m reference at that cell.",
                "grid_20m": entry["grid_20m"],
                **{key: value for key, value in points_summary.items() if key != "points"},
                "points": points,
            }
            write_json(folder / POINTS_NAME, points_record)
            outside[POINTS_NAME] = {"sha256": sha256_file(folder / POINTS_NAME)}
            side["points"] = {"name": POINTS_NAME, "sha256": outside[POINTS_NAME]["sha256"],
                              "count": points_summary["points"]}
            entry["points"] = {key: value for key, value in points_summary.items()}
            entry["points"]["file_outside_git"] = POINTS_NAME
        write_json(folder / SIDE_RECORD_NAME, side)
        outside[SIDE_RECORD_NAME] = {"sha256": sha256_file(folder / SIDE_RECORD_NAME)}
        entry.update({"status": "built", "counts": counts, **details,
                      "files_outside_git": {"folder": f"<external>/{(WORK / area).as_posix()}", **outside}})
        sets[area] = entry
        log(f"{area}: built: {counts['compared_cells']} compared cells, {counts['water_cells']} water, "
            f"water share {counts['water_share_of_compared']}")

    record = {
        "schema": "floodguard.nan_case_tuning_references.v1",
        **envelope("; ".join(f"{area}: {stamp}" for area, stamp in SOURCE_TIMESTAMPS.items())),
        "what_this_is": "The recorded reference of each tuning area of the Nan case on that area's 20 m grid, built "
                        "before the method is tuned. Counts of reference cells only; no radar map is set against them here.",
        "label": "Reference layers for tuning. Agreement of a radar map with them is agreement with a reference, not accuracy.",
        "protocol": git_file(PROTOCOL),
        "plan": git_file(PLAN),
        "areas": git_file(AREAS),
        "value_codes": VALUE_CODES,
        "sets": sets,
        "sets_built": [area for area, entry in sets.items() if entry["status"] == "built"],
        "sets_dropped": [area for area, entry in sets.items() if entry["status"] == "dropped"],
        "firewall": "No file of the Nan frame was opened: not the sealed JAXA folder, not any GFM file, not the THEOS-2 "
                    "files of 31 July 2025 nor anything derived from them. Every path was checked against that list "
                    "before it was opened.",
        "code": git_file(SCRIPT),
        "limits": LIMITS,
        "supersedes": None,
    }
    if record_path.exists():
        old = json.loads(record_path.read_text(encoding="utf-8"))
        record["supersedes"] = {
            "reason": arguments.reason,
            "generated_at_utc": old.get("generated_at_utc"),
            "canonical_json_sha256": hashlib.sha256(json.dumps(old, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
            "figures_same": {area: (old.get("sets", {}).get(area, {}).get("counts") == entry.get("counts"))
                             for area, entry in sets.items()},
        }
    write_json(record_path, record)
    log(f"done: {RECORD} sha256 {sha256_file(record_path)}")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True, help="the external data root (outside Git)")
    parser.add_argument("--replace", action="store_true", help="write over an existing record")
    parser.add_argument("--reason", default="", help="why an existing record is replaced")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
