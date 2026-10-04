"""Layers the envelope figures of plan task A1 are measured on (restructuring plan v2, section 4.2, row A1).

Three diagnosis figures are measured against the accumulated layer of UNOSAT/GISTDA product 4009 inside
AOI-01: the share of the layer the retired M2 pilot grid leaves out, and the separation of the radar
darkening and of two terrain features against it. This module reads the layers those figures need and
puts them on one grid. It adds no rule of its own:

* the accumulated layer is read through :func:`floodguard.flood_inputs.load_se1`, so the rights registry is
  asked first and the archive must be the file the confirmed rights record names (plan row G6, guardrail
  GR6). Only that layer is read: it is the record's layer in scope, at rights level ``public``. The analysis
  extent of the product is held at ``local`` and is **not** read here;
* the stored sigma0 rasters of plan tasks A2 and A4 are read back as the bytes their registered receipt
  binds; nothing is calibrated or geocoded again;
* a layer becomes a grid by the cell-centre rule (a cell belongs to a polygon when its centre lies in it).

The accumulated layer is a 2024 season envelope: every area mapped as water at some time between 1 August
and October 2024, with no date per patch. It is not an event map, and it is not a reference. A figure
measured against it describes separation against that envelope and nothing else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np

from floodguard import diagnosis_run, flood_inputs, rights

AOI_01_PATH = Path("resources") / "aoi" / "aoi-01_mae_sai_core.geojson"
AOI_01_NAME = "aoi_01"
AOI_01_LABEL = "AOI-01 (resources/aoi/aoi-01_mae_sai_core.geojson)"
BOUNDARY_RELATIVE_PATH = Path("open_context") / "hdx_cod_ab" / "tha_admin_boundaries.gdb.zip"
BOUNDARY_LAYER = "tha_admin3"
UNIT_ID_FIELD = "adm3_pcode"
RADAR_RECEIPTS = {
    "gcp_polynomial": Path("outputs") / "planning_v1" / "radar_o1_mae_sai_v1_receipt.json",
    "annotation_grid_with_cell_height": Path("outputs") / "planning_v1" / "radar_o1_mae_sai_v1_height_aware_sensitivity_receipt.json",
}
"""The registered receipts of plan tasks A2 and A4, by the geocoding of their sigma0 rasters."""
SIGMA0_NAMES = {"pre": "sigma0_pre_20240903.tif", "post": "sigma0_post_20240915.tif"}
VH_BAND = 2
"""Band 2 of a stored sigma0 raster is VH linear sigma0 (band 1 is VV)."""

STANDARD_LIMIT = (
    "The accumulated layer of product 4009 is a 2024 season envelope: every area mapped as water at some time between "
    "1 August and October 2024, with no date per patch. It is not an event map of September 2024, it was not checked "
    "in the field (Field_Validation=0), and FloodGuard did not validate it. A figure measured against it is a "
    "comparison with a season envelope, not a validation."
)


class DiagnosisLayerError(ValueError):
    """Raised when a layer of a diagnosis figure is missing, differs from its receipt or cannot be gridded."""


@dataclass(frozen=True)
class Grid:
    """A north-up grid in EPSG:32647: its upper-left corner, its cell size and its size in cells."""

    left: float
    top: float
    cell_m: float
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        """Rows and columns."""

        return (self.height, self.width)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east and north edges."""

        return (self.left, self.top - self.height * self.cell_m, self.left + self.width * self.cell_m, self.top)

    @property
    def transform(self) -> Any:
        """The affine transform of the grid, as rasterio takes it."""

        from rasterio.transform import from_origin

        return from_origin(self.left, self.top, self.cell_m, self.cell_m)

    def record(self) -> dict[str, Any]:
        """The grid as plain JSON values."""

        return {"crs": flood_inputs.ANALYSIS_CRS, "cell_m": self.cell_m, "width": self.width, "height": self.height,
                "bounds": [round(value, 3) for value in self.bounds]}


def analysis_grid(frame_bounds: Sequence[float], source: Grid, *, cell_m: float, margin_m: float) -> Grid:
    """Return a grid of ``cell_m`` cells around a frame, aligned to the lattice of a finer source grid.

    The frame's bounding box is widened by ``margin_m`` and then outward to whole cells counted from the
    upper-left corner of the source grid, so that each cell is a whole block of source cells.

    Raises:
        DiagnosisLayerError: when ``cell_m`` is not a whole multiple of the source cell, or the widened box
            leaves the source grid.
    """

    factor = cell_m / source.cell_m
    if factor < 1 or abs(factor - round(factor)) > 1e-9:
        raise DiagnosisLayerError("the cell size must be a whole multiple of the source cell size")
    west, south, east, north = frame_bounds
    first_col = int(np.floor((west - margin_m - source.left) / cell_m))
    last_col = int(np.ceil((east + margin_m - source.left) / cell_m))
    first_row = int(np.floor((source.top - (north + margin_m)) / cell_m))
    last_row = int(np.ceil((source.top - (south - margin_m)) / cell_m))
    grid = Grid(source.left + first_col * cell_m, source.top - first_row * cell_m, float(cell_m), last_col - first_col, last_row - first_row)
    source_west, source_south, source_east, source_north = source.bounds
    grid_west, grid_south, grid_east, grid_north = grid.bounds
    if grid_west < source_west or grid_east > source_east or grid_south < source_south or grid_north > source_north:
        raise DiagnosisLayerError("the frame and its margin are not inside the source grid")
    return grid


def cell_centre_mask(geometry: Any, grid: Grid) -> np.ndarray:
    """Return the cells of ``grid`` whose centre lies inside ``geometry`` (EPSG:32647)."""

    from rasterio.features import rasterize

    if geometry is None or geometry.is_empty:
        return np.zeros(grid.shape, dtype=bool)
    return rasterize([(geometry, 1)], out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8",
                     all_touched=False).astype(bool)


def read_polygon_file(path: Path | str) -> Any:
    """Read the union of the polygons of a GeoJSON file given in longitude and latitude."""

    import shapely
    from shapely.geometry import shape

    collection = json.loads(Path(path).read_text(encoding="utf-8"))
    return shapely.union_all([shape(feature["geometry"]) for feature in collection["features"]])


def aoi_frame(root: Path, external: Path | None) -> flood_inputs.Frame:
    """Return AOI-01 as a frame in EPSG:32647, with the record of its file."""

    path = root / AOI_01_PATH
    return flood_inputs.frame_from_wgs84(AOI_01_NAME, AOI_01_LABEL, read_polygon_file(path), diagnosis_run.file_record(path, root, external))


def change_notice(*, repair_count: int, credit: str, licence_name: str, raster_cell_m: float | None, then: str) -> str:
    """Return the change notice of a figure derived from the accumulated layer, in the order of the rights record.

    The record's four steps are the clip, the geometry repair, the reprojection and the rasterisation; the
    notice then says what was computed from the result.
    """

    raster = "not rasterised" if raster_cell_m is None else f"rasterised to {raster_cell_m:g} m cells by cell centre"
    return (
        f"Changed by FloodGuard: clipped to {AOI_01_LABEL}; geometry repaired ({flood_inputs.REPAIR_METHOD}; {repair_count} "
        f"parts repaired); reprojected from {flood_inputs.WGS84_CRS} to {flood_inputs.ANALYSIS_CRS}; {raster}; {then}. "
        f"Source: {credit}, {licence_name}."
    )


@dataclass(frozen=True)
class Envelope:
    """The accumulated layer of product 4009 inside AOI-01, with what the run needs to say about it."""

    frame: flood_inputs.Frame
    geometry: Any
    repair_count: int
    inputs: Mapping[str, Any]
    rights: Mapping[str, Any]
    credit: str
    licence_name: str
    standard_sentence: str
    layer: str
    source_timestamp: str

    def licence(self, *, raster_cell_m: float | None, then: str) -> dict[str, Any]:
        """Return the licence block of a figures file derived from the layer: licence, credit and change notice."""

        grant = self.rights["grant"]
        return {
            "applies_to": "every figure of this file that is measured against UNOSAT/GISTDA product 4009",
            "name": self.licence_name,
            "url": grant["licence"].get("url"),
            "credit": self.credit,
            "share_alike": grant["share_alike"],
            "change_notice": change_notice(repair_count=self.repair_count, credit=self.credit, licence_name=self.licence_name,
                                           raster_cell_m=raster_cell_m, then=then),
            "standard_sentence": self.standard_sentence,
            "used_as": "a 2024 season envelope (lane SCN-ENV): a comparison layer, never an event map and never a reference",
            "rights_record": {"path": grant["record_path"], "sha256": grant["record_sha256"]},
            "not_legal_advice": True,
        }


def load_envelope(root: Path, external: Path) -> Envelope:
    """Read the accumulated layer of product 4009 and clip it to AOI-01.

    The read goes through the rights registry and :func:`floodguard.flood_inputs.load_se1`: the registry is
    asked before any file is opened, and the archive must have the size and SHA-256 the confirmed rights
    record names. The footprint layer (the analysis extent, rights level ``local``) is not read.

    Raises:
        floodguard.rights.RightsRefusedError: when the registry refuses the use or the archive differs.
        DiagnosisLayerError: when the layer is not at the public level.
    """

    docs = root / diagnosis_run.DOCS
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    registry = rights.RightsRegistry(root)
    frame = aoi_frame(root, external)
    loaded = flood_inputs.load_se1([frame], rules=rules, registry=registry, external_root=external, footprint_layer=None)
    grant = loaded.record["rights"]
    if grant["rights_level"] != rights.PUBLIC_LEVEL:
        raise DiagnosisLayerError("the accumulated layer is not at the public level: its figures may not be committed")
    record_4009, _sha256 = registry.read_record(rights.PRODUCT_4009)
    archive_path = external / record_4009["archive"]["relative_path"]
    repair = loaded.record["repair"]
    summary = loaded.record["levels"]["by_level"][flood_inputs.AS_PROVIDED][frame.name]
    inputs = {
        "product_4009_archive": {**diagnosis_run.file_record(archive_path, root, external),
                                 "geodatabase": flood_inputs.GEODATABASE_4009, "layer": loaded.record["source"]["layer"],
                                 "layer_attributes": loaded.record["source"]["layer_attributes"]},
        "rights_record_4009": diagnosis_run.file_record(root / grant["record_path"], root, external),
        "aoi_01": {**dict(frame.source), "area_km2_epsg32647": round(frame.area_m2 / 1e6, 6)},
    }
    return Envelope(
        frame=frame,
        geometry=loaded.extent(flood_inputs.AS_PROVIDED, frame.name),
        repair_count=int(repair["by_frame"][frame.name]["parts_intersecting_repaired"]),
        inputs=inputs,
        rights={
            "grant": grant,
            "lineage": "The accumulated layer is the layer in scope of the confirmed rights record, at rights level public. "
                       "The analysis extent and the layer of 22 October 2024 (rights level local) were not read.",
            "envelope_in_aoi_01": {"area_km2": summary["area_km2"], "polygons": summary["polygons"],
                                   "parts_intersecting": repair["by_frame"][frame.name]["parts_intersecting"],
                                   "parts_repaired": repair["by_frame"][frame.name]["parts_intersecting_repaired"]},
        },
        credit=rules.product_4009_credit,
        licence_name=str(grant["licence"]["name"]),
        standard_sentence=rules.standard_4009_sentence,
        layer=str(loaded.record["source"]["layer"]),
        source_timestamp=str(loaded.record["source_timestamp"]),
    )


def thailand_side(boundaries: Path, frame: flood_inputs.Frame, reporting_units: Sequence[str]) -> tuple[Any, dict[str, Any]]:
    """Return the part of a frame that lies inside Thai ``tha_admin3`` units, and which units those are.

    Product 4009 maps Chiang Rai Province, so a cell across the national border is not a cell the product
    left dry: it is a cell the product does not cover. The domain of a comparison is therefore the Thai side
    of the frame, taken from the public COD-AB boundaries and not from the product's analysis extent.

    Raises:
        DiagnosisLayerError: when no unit meets the frame.
    """

    import pyogrio
    import shapely

    bounds = flood_inputs.project(frame.geometry, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS).bounds
    table = pyogrio.read_dataframe(boundaries, layer=BOUNDARY_LAYER, columns=[UNIT_ID_FIELD], bbox=bounds)
    if table.crs is None or table.crs.to_epsg() != 4326:
        raise DiagnosisLayerError("the boundary layer must be EPSG:4326")
    units = flood_inputs.project(shapely.make_valid(table.geometry.values), flood_inputs.WGS84_CRS, flood_inputs.ANALYSIS_CRS)
    meeting = shapely.intersects(units, frame.geometry)
    if not meeting.any():
        raise DiagnosisLayerError("no tha_admin3 unit meets the frame")
    inside = flood_inputs.as_multipolygon(shapely.intersection(frame.geometry, shapely.union_all(units[meeting])))
    identifiers = sorted(str(code) for code in table[UNIT_ID_FIELD].values[meeting])
    return inside, {
        "rule": "The Thai side of the frame: the union of the COD-AB tha_admin3 polygons that meet it, cut to the frame.",
        "units_meeting_the_frame": identifiers,
        "all_units_are_in_the_reporting_frame_of_protocol_v1a": set(identifiers) <= set(reporting_units),
        "area_km2": round(float(inside.area) / 1e6, 6),
        "share_of_frame": round(float(inside.area) / frame.area_m2, 6),
    }


def reporting_units(root: Path) -> tuple[str, ...]:
    """Return the eight Mae Sai tambons of protocol v1a (``case_portfolio.mae_sai_reporting_frame.units``)."""

    v1a = json.loads((root / diagnosis_run.DOCS / "planning_protocol_v1a.json").read_text(encoding="utf-8"))
    return tuple(str(unit) for unit in v1a["case_portfolio"]["mae_sai_reporting_frame"]["units"])


def boundary_file(root: Path, external: Path, path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Return the COD-AB boundary file and its record, and refuse a file that is not the one protocol v1b names."""

    target = path or external / BOUNDARY_RELATIVE_PATH
    record = diagnosis_run.file_record(target, root, external, layer=BOUNDARY_LAYER)
    v1b = json.loads((root / diagnosis_run.DOCS / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    if record["sha256"] != v1b["national_vulnerability_anchors"]["inputs"]["tambon_boundaries"]["sha256"]:
        raise DiagnosisLayerError("the boundary file is not the one protocol v1b names")
    return target, record


# ---------------------------------------------------------------------------
# The stored sigma0 rasters of plan tasks A2 and A4
# ---------------------------------------------------------------------------


def _external_path(label: str, external: Path) -> Path:
    prefix = diagnosis_run.EXTERNAL_LABEL + "/"
    if not label.startswith(prefix):
        raise DiagnosisLayerError(f"{label} is not a file under the external data root")
    return external / label[len(prefix):]


def registered_receipt(root: Path, relative: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read a receipt of ``outputs/planning_v1`` and check that the run register names exactly these bytes.

    Raises:
        DiagnosisLayerError: when the receipt is not registered or its bytes differ from the register entry.
    """

    path = root / relative
    sha256 = diagnosis_run.sha256_file(path)
    registered = {}
    for entry_path in sorted((root / diagnosis_run.REGISTER_DIR).glob("*.json")):
        entry = json.loads(entry_path.read_text(encoding="ascii"))
        registered[entry["path"]] = entry["sha256"]
    if registered.get(relative.as_posix()) != sha256:
        raise DiagnosisLayerError(f"{relative.as_posix()} is not the receipt the run register names")
    return json.loads(path.read_text(encoding="ascii")), {"path": relative.as_posix(), "sha256": sha256}


def bound_file(receipt: Mapping[str, Any], name: str, external: Path) -> tuple[Path, dict[str, Any]]:
    """Return a raster a radar receipt binds, after checking that the file on disk has the SHA-256 it names.

    Raises:
        DiagnosisLayerError: when the receipt binds no such file, or the file differs.
    """

    for entry in receipt["outputs"]["rasters"]:
        if entry["path"].rsplit("/", 1)[-1] == name:
            path = _external_path(entry["path"], external)
            if not path.is_file() or diagnosis_run.sha256_file(path) != entry["sha256"]:
                raise DiagnosisLayerError(f"{entry['path']} is not the file its receipt binds")
            return path, {"path": entry["path"], "sha256": entry["sha256"], "bytes": entry["bytes"]}
    raise DiagnosisLayerError(f"the receipt binds no raster named {name}")


def bound_input(receipt: Mapping[str, Any], key: str, external: Path) -> tuple[Path, dict[str, Any]]:
    """Return an input file of a radar receipt, after checking that the file on disk has the SHA-256 it names."""

    entry = receipt["inputs"][key]
    path = _external_path(entry["path"], external)
    if not path.is_file() or diagnosis_run.sha256_file(path) != entry["sha256"]:
        raise DiagnosisLayerError(f"{entry['path']} is not the file the radar receipt names")
    return path, {"path": entry["path"], "sha256": entry["sha256"], "bytes": entry["bytes"]}


def source_grid(path: Path) -> Grid:
    """Return the grid of a stored raster, which must be north-up in EPSG:32647 with square cells."""

    import rasterio

    with rasterio.open(path) as source:
        transform = source.transform
        if source.crs is None or source.crs.to_epsg() != flood_inputs.ANALYSIS_EPSG or transform.b != 0 or transform.d != 0 \
                or abs(transform.a + transform.e) > 1e-9:
            raise DiagnosisLayerError(f"{path.name} is not a north-up raster in {flood_inputs.ANALYSIS_CRS} with square cells")
        return Grid(float(transform.c), float(transform.f), float(transform.a), int(source.width), int(source.height))


def read_block_mean(path: Path, grid: Grid, *, band: int) -> np.ndarray:
    """Read one band of a stored raster over ``grid`` and average its cells into the cells of the grid.

    Raises:
        DiagnosisLayerError: when the grid is not aligned to the raster's lattice.
    """

    import rasterio
    from rasterio.windows import Window

    from floodguard.abstention_diagnosis import block_mean

    source = source_grid(path)
    factor = grid.cell_m / source.cell_m
    col = (grid.left - source.left) / source.cell_m
    row = (source.top - grid.top) / source.cell_m
    if any(abs(value - round(value)) > 1e-6 for value in (factor, col, row)):
        raise DiagnosisLayerError("the grid is not aligned to the lattice of the stored raster")
    factor_cells = int(round(factor))
    window = Window(int(round(col)), int(round(row)), grid.width * factor_cells, grid.height * factor_cells)
    with rasterio.open(path) as dataset:
        values = dataset.read(band, window=window, boundless=False).astype("float64")
        nodata = dataset.nodata
    if nodata is not None and not np.isnan(nodata):
        values[values == nodata] = np.nan
    values[~np.isfinite(values) | (values <= 0)] = np.nan
    return block_mean(values, factor_cells)


def warp_to_grid(path: Path, grid: Grid, *, resampling: str) -> np.ndarray:
    """Warp band 1 of a raster in any coordinate system onto ``grid`` (``nearest`` or ``bilinear``).

    Raises:
        DiagnosisLayerError: for another resampling.
    """

    import rasterio
    from rasterio.warp import Resampling, reproject

    methods = {"nearest": Resampling.nearest, "bilinear": Resampling.bilinear}
    if resampling not in methods:
        raise DiagnosisLayerError("the resampling must be nearest or bilinear")
    out = np.full(grid.shape, np.nan, dtype="float32")
    with rasterio.open(path) as source:
        reproject(rasterio.band(source, 1), out, dst_transform=grid.transform, dst_crs=flood_inputs.ANALYSIS_CRS,
                  resampling=methods[resampling], dst_nodata=np.nan)
    return out.astype("float64")


# ---------------------------------------------------------------------------
# The cells a feature is compared on
# ---------------------------------------------------------------------------

CELL_M = 20.0
"""Cell size of the comparison grid: a 2 by 2 block of the 10 m cells of the stored radar rasters."""
MARGIN_M = 1000.0
"""Margin around AOI-01, so that a 5 by 5 mean and a slope have their neighbours at the edge of the AOI."""
JRC_OCCURRENCE_RELATIVE_PATH = Path("open_context") / "jrc_global_surface_water" / "occurrence_90E_30Nv1_4_2021.tif"
JRC_PERENNIAL_MONTHS = 10
JRC_OCCURRENCE_PERCENT = 80
WORLDCOVER_WATER_CLASS = 80
WATER_JRC = "jrc_surface_water"
WATER_WORLDCOVER = "worldcover_class_80"
WATER_NONE = "nothing_left_out"
WATER_READINGS: tuple[str, ...] = (WATER_JRC, WATER_WORLDCOVER, WATER_NONE)
"""The three ways permanent water is left out of a comparison (open point A1-OP4)."""


def receipt_grid(receipt: Mapping[str, Any]) -> Grid:
    """Return the grid a radar receipt states for its rasters (``parameters.grid``).

    Raises:
        DiagnosisLayerError: when the grid is not in EPSG:32647.
    """

    grid = receipt["parameters"]["grid"]
    if grid["crs"] != flood_inputs.ANALYSIS_CRS:
        raise DiagnosisLayerError(f"the radar grid is not in {flood_inputs.ANALYSIS_CRS}")
    west, _south, _east, north = grid["bounds"]
    return Grid(float(west), float(north), float(grid["cell_m"]), int(grid["width"]), int(grid["height"]))


@dataclass(frozen=True)
class ComparisonDomain:
    """The grid, the envelope cells and the cells a feature is compared on, for each permanent-water reading."""

    grid: Grid
    inside: np.ndarray
    base: np.ndarray
    water: Mapping[str, np.ndarray]
    record: Mapping[str, Any]
    inputs: Mapping[str, Any]

    def cells(self, reading: str) -> np.ndarray:
        """Return the cells of one reading: AOI-01 on the Thai side, without the permanent water of the reading."""

        return self.base & ~self.water[reading]


def comparison_domain(root: Path, external: Path, envelope: Envelope) -> ComparisonDomain:
    """Build the comparison grid of AOI-01 and the cells a feature is compared on.

    The grid has 20 m cells aligned to the 10 m lattice of the stored radar rasters. A cell belongs to the
    envelope, to AOI-01 and to the Thai side by its centre. Permanent water is read three ways, each warped
    to the grid by the nearest cell: JRC Global Surface Water (seasonality of 10 months or more, or
    occurrence of 80 percent or more; a cell with no JRC value is not water), ESA WorldCover 2021 class 80,
    and nothing.

    Raises:
        DiagnosisLayerError: when a Thai unit that meets AOI-01 is outside the reporting frame of protocol
            v1a, for which task E1 measured that the product's footprint covers it.
    """

    radar_receipt, radar_record = registered_receipt(root, RADAR_RECEIPTS["gcp_polynomial"])
    grid = analysis_grid(envelope.frame.geometry.bounds, receipt_grid(radar_receipt), cell_m=CELL_M, margin_m=MARGIN_M)
    boundaries, boundary_record = boundary_file(root, external)
    thai, thai_record = thailand_side(boundaries, envelope.frame, reporting_units(root))
    if not thai_record["all_units_are_in_the_reporting_frame_of_protocol_v1a"]:
        raise DiagnosisLayerError("a Thai unit that meets AOI-01 is outside the reporting frame of protocol v1a")
    seasonality_path, seasonality_record = bound_input(radar_receipt, "jrc_seasonality", external)
    worldcover_path, worldcover_record = bound_input(radar_receipt, "worldcover", external)
    occurrence_path = external / JRC_OCCURRENCE_RELATIVE_PATH
    seasonality = warp_to_grid(seasonality_path, grid, resampling="nearest")
    occurrence = warp_to_grid(occurrence_path, grid, resampling="nearest")
    worldcover = warp_to_grid(worldcover_path, grid, resampling="nearest")
    jrc = ((seasonality >= JRC_PERENNIAL_MONTHS) & (seasonality <= 12)) | ((occurrence >= JRC_OCCURRENCE_PERCENT) & (occurrence <= 100))
    water = {WATER_JRC: jrc, WATER_WORLDCOVER: worldcover == WORLDCOVER_WATER_CLASS, WATER_NONE: np.zeros(grid.shape, dtype=bool)}
    inside = cell_centre_mask(envelope.geometry, grid)
    aoi = cell_centre_mask(envelope.frame.geometry, grid)
    base = aoi & cell_centre_mask(thai, grid)
    cell_km2 = grid.cell_m * grid.cell_m / 1e6
    jrc_valued = np.isfinite(seasonality) & (seasonality <= 12) & np.isfinite(occurrence) & (occurrence <= 100)
    record = {
        "grid": grid.record(),
        "cell_rule": "A cell belongs to a polygon when its centre lies in it.",
        "thai_side_of_aoi_01": thai_record,
        "why_the_thai_side": "Product 4009 maps Chiang Rai Province. A cell across the border is not a cell the product left "
                             "dry, so it is in no comparison. Task E1 measured that the product's footprint covers the whole "
                             "reporting frame of protocol v1a, and every Thai unit that meets AOI-01 is in that frame; the "
                             "footprint layer itself (rights level local) is not read here.",
        "cells_in_aoi_01": int(aoi.sum()),
        "cells_in_aoi_01_on_the_thai_side": int(base.sum()),
        "envelope_cells_in_aoi_01_on_the_thai_side": int((base & inside).sum()),
        "envelope_km2_by_cell_count": round(float((base & inside).sum()) * cell_km2, 3),
        "envelope_cells_outside_the_thai_side": int((aoi & inside & ~base).sum()),
        "jrc_cells_with_no_value_in_the_domain": int((base & ~jrc_valued).sum()),
        "by_permanent_water_reading": {
            reading: {
                "cells_left_out_as_permanent_water": int((base & water[reading]).sum()),
                "envelope_cells_left_out_as_permanent_water": int((base & water[reading] & inside).sum()),
                "cells": int((base & ~water[reading]).sum()),
                "envelope_cells": int((base & ~water[reading] & inside).sum()),
                "envelope_share_of_the_cells": round(float((base & ~water[reading] & inside).sum()) / float((base & ~water[reading]).sum()), 6),
            } for reading in WATER_READINGS
        },
    }
    inputs = {
        **dict(envelope.inputs),
        "tambon_boundaries": boundary_record,
        "radar_receipt_read_for_the_grid_and_the_context_files": radar_record,
        "jrc_seasonality": seasonality_record,
        "jrc_occurrence": diagnosis_run.file_record(occurrence_path, root, external),
        "worldcover": worldcover_record,
    }
    return ComparisonDomain(grid, inside, base, water, record, inputs)


def comparison_parameters() -> dict[str, Any]:
    """Return the parameters of the comparison grid and of the permanent-water readings."""

    return {
        "cell_m": CELL_M,
        "margin_m": MARGIN_M,
        "frame": AOI_01_LABEL,
        "envelope_level": flood_inputs.AS_PROVIDED,
        "cell_rule": "cell centre",
        "permanent_water_readings": {
            WATER_JRC: f"JRC Global Surface Water v1.4 (2021): seasonality of {JRC_PERENNIAL_MONTHS} months or more, or occurrence "
                       f"of {JRC_OCCURRENCE_PERCENT} percent or more; nearest cell",
            WATER_WORLDCOVER: f"ESA WorldCover 2021 v200, class {WORLDCOVER_WATER_CLASS}; nearest cell",
            WATER_NONE: "no cell is left out as permanent water",
        },
        "footprint_layer_read": False,
    }
