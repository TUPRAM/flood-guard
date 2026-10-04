"""Calibrated Sentinel-1 GRD backscatter (sigma0) from a SAFE archive.

Plan task A4 names two ways to prepare the Mae Sai radar pair. The first is a
SNAP graph with terrain correction. The second, used when SNAP is not
available, is this module: the digital numbers of the SAFE measurement are
calibrated to sigma0 with the ``sigmaNought`` look-up table of the SAFE
annotation and warped to a map grid with the ground control points of the
product. The plan's label for that path is
``approximate geocoding: GCP affine, no DEM terrain correction``.

What this path does and does not do:

* Calibration: ``sigma0 = DN ** 2 / A ** 2``, with ``A`` interpolated
  bilinearly from the calibration vectors (ESA Sentinel-1 product
  specification). The uncalibrated amplitude is never returned.
* Thermal noise is not removed. Orbit files are not applied.
* Geocoding: the product's ground control points, fitted by GDAL's GCP
  polynomial, as ``scripts/build_mae_sai_flood_timeline.py`` reads the same
  archives. The control points sit at the heights of a coarse terrain model,
  so a cell whose true height differs is displaced along the range direction
  by about ``(control height - true height) / tan(incidence)``.

The module also holds a second mapping, :class:`HeightAwareMapping`, which
uses the same annotation grid with a height for every map cell. It exists to
measure the displacement of the first mapping (see
:func:`estimate_displacement`). It is not the plan's fallback path.

Nothing here reads a flood label or computes a flood candidate. Every reader
takes its file locations as arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Sequence
import xml.etree.ElementTree as ElementTree
import zipfile

import numpy as np

GEOCODING_GCP_POLYNOMIAL: str = "gcp_polynomial"
GEOCODING_HEIGHT_AWARE: str = "annotation_grid_with_cell_height"
PLAN_FALLBACK_LABEL: str = "approximate geocoding: GCP affine, no DEM terrain correction"
POLARISATIONS: tuple[str, ...] = ("vv", "vh")
WINDOW_MARGIN_DEGREES: float = 0.03


class Sentinel1Error(ValueError):
    """The archive, its annotation or the request cannot support the reading."""


# ---------------------------------------------------------------------------
# Map grid
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RasterGrid:
    """A north-up grid of square cells in a projected coordinate system."""

    crs: str
    west: float
    north: float
    cell_m: float
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.cell_m <= 0 or self.width < 1 or self.height < 1:
            raise Sentinel1Error("a grid needs a positive cell size and at least one cell")

    @property
    def shape(self) -> tuple[int, int]:
        """Rows and columns."""

        return (self.height, self.width)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """West, south, east, north."""

        return (
            self.west,
            self.north - self.height * self.cell_m,
            self.west + self.width * self.cell_m,
            self.north,
        )

    @property
    def transform(self) -> Any:
        """The affine transform of the grid (``rasterio.Affine``)."""

        from rasterio.transform import from_origin

        return from_origin(self.west, self.north, self.cell_m, self.cell_m)

    def cell_centres(self) -> tuple[np.ndarray, np.ndarray]:
        """Easting of every column centre and northing of every row centre."""

        x = self.west + (np.arange(self.width) + 0.5) * self.cell_m
        y = self.north - (np.arange(self.height) + 0.5) * self.cell_m
        return x, y


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationLut:
    """The ``sigmaNought`` calibration vectors of one polarisation.

    ``lines`` holds the image line of each vector, ``pixels`` the image
    samples at which each vector is given and ``sigma_nought`` the look-up
    value ``A`` at those samples, one row per vector.
    """

    lines: np.ndarray
    pixels: np.ndarray
    sigma_nought: np.ndarray


def _numbers(text: str | None, name: str) -> np.ndarray:
    if text is None or not text.strip():
        raise Sentinel1Error(f"the annotation has an empty {name}")
    return np.array(text.split(), dtype="float64")


def parse_calibration_lut(xml_text: str) -> CalibrationLut:
    """Read the ``sigmaNought`` vectors from a SAFE calibration annotation.

    Raises:
        Sentinel1Error: when the file has fewer than two vectors, a vector
            whose pixel and value counts differ, vectors of different
            lengths, lines that do not increase or a value that is not
            positive.
    """

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise Sentinel1Error(f"the calibration annotation is not XML: {error}") from error
    lines: list[float] = []
    pixels: list[np.ndarray] = []
    values: list[np.ndarray] = []
    for vector in root.iter("calibrationVector"):
        line = vector.findtext("line")
        if line is None:
            raise Sentinel1Error("a calibration vector has no line")
        pixel = _numbers(vector.findtext("pixel"), "pixel list")
        sigma = _numbers(vector.findtext("sigmaNought"), "sigmaNought list")
        if pixel.size != sigma.size or pixel.size < 2:
            raise Sentinel1Error("a calibration vector needs one value for each of two or more pixels")
        if np.any(np.diff(pixel) <= 0):
            raise Sentinel1Error("the pixels of a calibration vector must increase")
        lines.append(float(line))
        pixels.append(pixel)
        values.append(sigma)
    if len(lines) < 2:
        raise Sentinel1Error("the calibration annotation needs at least two vectors")
    if len({item.size for item in pixels}) != 1:
        raise Sentinel1Error("the calibration vectors have different lengths")
    line_array = np.array(lines, dtype="float64")
    if np.any(np.diff(line_array) <= 0):
        raise Sentinel1Error("the lines of the calibration vectors must increase")
    sigma_array = np.vstack(values)
    if not np.all(np.isfinite(sigma_array)) or np.any(sigma_array <= 0):
        raise Sentinel1Error("every sigmaNought value must be finite and positive")
    return CalibrationLut(lines=line_array, pixels=np.vstack(pixels), sigma_nought=sigma_array)


def calibration_gain(
    lut: CalibrationLut, row_start: int, col_start: int, height: int, width: int
) -> np.ndarray:
    """Interpolate the look-up value ``A`` for every cell of an image window.

    The interpolation is bilinear: along the samples within each vector, then
    linearly between the two vectors that bracket each line. A line before
    the first vector or after the last one takes the nearest vector.
    """

    if height < 1 or width < 1:
        raise Sentinel1Error("the window needs at least one row and one column")
    cols = col_start + np.arange(width, dtype="float64")
    rows = row_start + np.arange(height, dtype="float64")
    along = np.vstack(
        [np.interp(cols, lut.pixels[index], lut.sigma_nought[index]) for index in range(lut.lines.size)]
    )
    upper = np.clip(np.searchsorted(lut.lines, rows, side="right"), 1, lut.lines.size - 1)
    lower = upper - 1
    span = lut.lines[upper] - lut.lines[lower]
    weight = np.clip((rows - lut.lines[lower]) / span, 0.0, 1.0)
    gain = along[lower] * (1.0 - weight)[:, None] + along[upper] * weight[:, None]
    return gain.astype("float64")


def sigma0_from_dn(dn: np.ndarray, gain: np.ndarray) -> np.ndarray:
    """Convert digital numbers to linear sigma0: ``DN ** 2 / A ** 2``.

    A digital number of zero is the product's fill value; it becomes NaN.
    """

    values = np.asarray(dn, dtype="float64")
    table = np.asarray(gain, dtype="float64")
    if values.shape != table.shape:
        raise Sentinel1Error("the digital numbers and the look-up values must share a shape")
    with np.errstate(divide="ignore", invalid="ignore"):
        sigma0 = (values * values) / (table * table)
    return np.where(values > 0, sigma0, np.nan).astype("float32")


# ---------------------------------------------------------------------------
# Annotation: geolocation grid and product description
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeolocationGrid:
    """The geolocation grid of a GRD annotation, as rectangular arrays.

    ``lines`` and ``pixels`` are the image coordinates of the grid rows and
    columns; the other arrays have one value per grid point. ``height`` is
    the terrain height the product assumed at the point, and ``latitude`` and
    ``longitude`` are where a target at that height would lie.
    """

    lines: np.ndarray
    pixels: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    height: np.ndarray
    incidence_deg: np.ndarray


def parse_geolocation_grid(xml_text: str) -> GeolocationGrid:
    """Read the geolocation grid points of a SAFE product annotation.

    Raises:
        Sentinel1Error: when the points do not form a full rectangle of at
            least two lines and two pixels.
    """

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise Sentinel1Error(f"the product annotation is not XML: {error}") from error
    fields = ("line", "pixel", "latitude", "longitude", "height", "incidenceAngle")
    records = []
    for point in root.iter("geolocationGridPoint"):
        try:
            records.append([float(point.findtext(name)) for name in fields])  # type: ignore[arg-type]
        except (TypeError, ValueError) as error:
            raise Sentinel1Error("a geolocation grid point lacks a value") from error
    if not records:
        raise Sentinel1Error("the annotation has no geolocation grid")
    table = np.array(records, dtype="float64")
    lines = np.unique(table[:, 0])
    pixels = np.unique(table[:, 1])
    if lines.size < 2 or pixels.size < 2 or table.shape[0] != lines.size * pixels.size:
        raise Sentinel1Error("the geolocation grid is not a full rectangle")
    order = np.lexsort((table[:, 1], table[:, 0]))
    table = table[order].reshape(lines.size, pixels.size, len(fields))
    if not np.array_equal(table[:, :, 0], np.broadcast_to(lines[:, None], table.shape[:2])):
        raise Sentinel1Error("the geolocation grid is not a full rectangle")
    if not np.array_equal(table[:, :, 1], np.broadcast_to(pixels[None, :], table.shape[:2])):
        raise Sentinel1Error("the geolocation grid is not a full rectangle")
    return GeolocationGrid(
        lines=lines,
        pixels=pixels,
        latitude=table[:, :, 2],
        longitude=table[:, :, 3],
        height=table[:, :, 4],
        incidence_deg=table[:, :, 5],
    )


def _member(names: Sequence[str], pattern: str, what: str) -> str:
    found = [name for name in names if re.search(pattern, name)]
    if len(found) != 1:
        raise Sentinel1Error(f"the archive holds {len(found)} files for {what}; one is needed")
    return found[0]


def measurement_member(names: Sequence[str], polarisation: str) -> str:
    """Name of the measurement GeoTIFF of one polarisation inside a SAFE archive."""

    _check_polarisation(polarisation)
    return _member(names, rf"/measurement/[^/]*-{polarisation}-[^/]*\.tiff?$", f"the {polarisation} measurement")


def calibration_member(names: Sequence[str], polarisation: str) -> str:
    """Name of the calibration annotation of one polarisation inside a SAFE archive."""

    _check_polarisation(polarisation)
    return _member(
        names,
        rf"/annotation/calibration/calibration-[^/]*-{polarisation}-[^/]*\.xml$",
        f"the {polarisation} calibration",
    )


def annotation_member(names: Sequence[str], polarisation: str) -> str:
    """Name of the product annotation of one polarisation inside a SAFE archive."""

    _check_polarisation(polarisation)
    return _member(names, rf"/annotation/[^/]*-{polarisation}-[^/]*\.xml$", f"the {polarisation} annotation")


def _check_polarisation(polarisation: str) -> None:
    if polarisation not in POLARISATIONS:
        raise Sentinel1Error(f"unknown polarisation: {polarisation}")


def _first(pattern: str, text: str, what: str) -> str:
    match = re.search(pattern, text)
    if match is None:
        raise Sentinel1Error(f"the archive does not state {what}")
    return match.group(1)


def read_product_metadata(zip_path: Path | str) -> dict[str, Any]:
    """Describe a SAFE archive from its ``manifest.safe`` and its VH annotation.

    Returns the product name, the pass direction, the relative orbit, the
    acquisition start and stop (UTC, as written in the product), the
    processor version, the projection and the pixel spacing.
    """

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = archive.read(_member(names, r"manifest\.safe$", "the manifest")).decode("utf-8")
        annotation = archive.read(annotation_member(names, "vh")).decode("utf-8")
    product = next((name.split("/")[0] for name in names if ".SAFE/" in name), path.name)
    return {
        "product": product,
        "pass": _first(r"<s1:pass>(\w+)", manifest, "the pass direction").lower(),
        "relative_orbit": int(
            _first(r'relativeOrbitNumber type="start">(\d+)', manifest, "the relative orbit")
        ),
        "acquisition_start_utc": _first(r"<safe:startTime>([^<]+)", manifest, "the start time"),
        "acquisition_stop_utc": _first(r"<safe:stopTime>([^<]+)", manifest, "the stop time"),
        "processor": "Sentinel-1 IPF "
        + _first(r'<safe:software name="Sentinel-1 IPF" version="([^"]+)"', manifest, "the processor"),
        "projection": _first(r"<projection>([^<]+)", annotation, "the projection"),
        "range_pixel_spacing_m": float(
            _first(r"<rangePixelSpacing>([^<]+)", annotation, "the range pixel spacing")
        ),
        "azimuth_pixel_spacing_m": float(
            _first(r"<azimuthPixelSpacing>([^<]+)", annotation, "the azimuth pixel spacing")
        ),
    }


def read_geolocation_grid(zip_path: Path | str, polarisation: str = "vh") -> GeolocationGrid:
    """Read the geolocation grid of one polarisation from a SAFE archive."""

    with zipfile.ZipFile(Path(zip_path)) as archive:
        text = archive.read(annotation_member(archive.namelist(), polarisation)).decode("utf-8")
    return parse_geolocation_grid(text)


# ---------------------------------------------------------------------------
# Reading a calibrated window
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sigma0Window:
    """A calibrated window of one measurement, still in image geometry.

    ``values`` is linear sigma0 (NaN where the product has no data).
    ``row_offset`` and ``col_offset`` place the window in the full image.
    ``gcps`` are the product's control points with their image coordinates
    moved into the window.
    """

    values: np.ndarray
    row_offset: int
    col_offset: int
    gcps: tuple[Any, ...]
    gcp_crs: Any
    image_shape: tuple[int, int]
    gain_range: tuple[float, float]


def read_sigma0_window(
    zip_path: Path | str,
    polarisation: str,
    grid: RasterGrid,
    *,
    margin_degrees: float = WINDOW_MARGIN_DEGREES,
) -> Sigma0Window:
    """Read and calibrate the part of a SAFE measurement that covers a map grid.

    The archive is read in place through GDAL's ``/vsizip``; nothing is
    extracted. The window is the image rectangle that holds the grid's
    geographic bounds plus ``margin_degrees`` on every side, found with the
    product's control points.

    Raises:
        Sentinel1Error: when the product has no control points or the grid
            lies outside the image.
    """

    import rasterio
    from rasterio.control import GroundControlPoint
    from rasterio.transform import GCPTransformer
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window

    path = Path(zip_path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        member = measurement_member(names, polarisation)
        lut = parse_calibration_lut(archive.read(calibration_member(names, polarisation)).decode("utf-8"))
    with rasterio.open(f"/vsizip/{path.as_posix()}/{member}") as source:
        gcps, gcp_crs = source.gcps
        if not gcps:
            raise Sentinel1Error("the measurement has no ground control points")
        west, south, east, north = transform_bounds(grid.crs, gcp_crs, *grid.bounds, densify_pts=21)
        longitudes = [west - margin_degrees, east + margin_degrees] * 2
        latitudes = [south - margin_degrees] * 2 + [north + margin_degrees] * 2
        rows, cols = GCPTransformer(gcps).rowcol(longitudes, latitudes)
        row_start, row_stop = max(int(min(rows)), 0), min(int(max(rows)) + 1, source.height)
        col_start, col_stop = max(int(min(cols)), 0), min(int(max(cols)) + 1, source.width)
        if row_stop <= row_start or col_stop <= col_start:
            raise Sentinel1Error("the grid lies outside the image")
        window = Window(col_start, row_start, col_stop - col_start, row_stop - row_start)
        dn = source.read(1, window=window)
        image_shape = (source.height, source.width)
    gain = calibration_gain(lut, row_start, col_start, dn.shape[0], dn.shape[1])
    shifted = tuple(
        GroundControlPoint(row=point.row - row_start, col=point.col - col_start, x=point.x, y=point.y, z=point.z)
        for point in gcps
    )
    return Sigma0Window(
        values=sigma0_from_dn(dn, gain),
        row_offset=row_start,
        col_offset=col_start,
        gcps=shifted,
        gcp_crs=gcp_crs,
        image_shape=image_shape,
        gain_range=(float(gain.min()), float(gain.max())),
    )


def warp_gcp_polynomial(window: Sigma0Window, grid: RasterGrid) -> np.ndarray:
    """Warp a calibrated window to a map grid with the product's control points.

    This is the plan's fallback geocoding: GDAL fits its GCP polynomial to the
    control points and resamples linear sigma0 bilinearly. No terrain model
    is used. Cells outside the image are NaN.
    """

    from rasterio.warp import Resampling, reproject

    destination = np.full(grid.shape, np.nan, dtype="float32")
    reproject(
        source=window.values.astype("float32"),
        destination=destination,
        gcps=list(window.gcps),
        src_crs=window.gcp_crs,
        src_nodata=np.nan,
        dst_transform=grid.transform,
        dst_crs=grid.crs,
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return destination


# ---------------------------------------------------------------------------
# A mapping that uses a height for every map cell
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeightAwareMapping:
    """Map cell positions and heights to image coordinates with the annotation grid.

    The annotation gives, for a rectangle of image points, where a target at
    the product's assumed height would lie. Moving each grid point along the
    range direction by ``-height / tan(incidence)`` gives where a target at
    height zero would lie; that relation between map position and image
    coordinates is smooth and is interpolated with a thin-plate spline. A map
    cell at height ``h`` is then looked up at its position moved by
    ``-h / tan(incidence)`` along the range direction.

    The arrays are the grid points in a projected coordinate system (metres):
    ``x0`` and ``y0`` at height zero, ``range_x`` and ``range_y`` the unit
    vector of increasing image sample, and ``tan_incidence``.
    """

    lines: np.ndarray
    pixels: np.ndarray
    x0: np.ndarray
    y0: np.ndarray
    range_x: np.ndarray
    range_y: np.ndarray
    tan_incidence: np.ndarray

    @classmethod
    def from_projected_grid(
        cls,
        lines: np.ndarray,
        pixels: np.ndarray,
        x: np.ndarray,
        y: np.ndarray,
        height: np.ndarray,
        incidence_deg: np.ndarray,
    ) -> "HeightAwareMapping":
        """Build the mapping from grid points given in projected metres."""

        lines = np.asarray(lines, dtype="float64")
        pixels = np.asarray(pixels, dtype="float64")
        x = np.asarray(x, dtype="float64")
        y = np.asarray(y, dtype="float64")
        shape = (lines.size, pixels.size)
        if lines.size < 2 or pixels.size < 2 or any(
            np.asarray(item).shape != shape for item in (x, y, height, incidence_deg)
        ):
            raise Sentinel1Error("the grid arrays must be rectangles of at least two lines and two pixels")
        step_x = np.gradient(x, axis=1)
        step_y = np.gradient(y, axis=1)
        length = np.hypot(step_x, step_y)
        if np.any(length <= 0):
            raise Sentinel1Error("two neighbouring grid points share a position")
        range_x = step_x / length
        range_y = step_y / length
        tan_incidence = np.tan(np.radians(np.asarray(incidence_deg, dtype="float64")))
        if np.any(tan_incidence <= 0):
            raise Sentinel1Error("every incidence angle must lie between 0 and 90 degrees")
        shift = -np.asarray(height, dtype="float64") / tan_incidence
        return cls(
            lines=lines,
            pixels=pixels,
            x0=x + range_x * shift,
            y0=y + range_y * shift,
            range_x=range_x,
            range_y=range_y,
            tan_incidence=tan_incidence,
        )

    @classmethod
    def from_geolocation_grid(cls, geolocation: GeolocationGrid, crs: str) -> "HeightAwareMapping":
        """Build the mapping from an annotation grid, projected to ``crs``."""

        from pyproj import Transformer

        to_map = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        x, y = to_map.transform(geolocation.longitude, geolocation.latitude)
        return cls.from_projected_grid(
            geolocation.lines, geolocation.pixels, x, y, geolocation.height, geolocation.incidence_deg
        )

    def _field(self, values: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        from scipy.interpolate import RBFInterpolator

        points = np.column_stack([self.x0.ravel(), self.y0.ravel()]) / 1000.0
        spline = RBFInterpolator(points, values.ravel(), kernel="thin_plate_spline")
        query = np.column_stack([np.ravel(x), np.ravel(y)]) / 1000.0
        return spline(query).reshape(np.shape(x))

    def image_coordinates(
        self, grid: RasterGrid, cell_height: np.ndarray, *, lattice_cells: int = 32
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return the image line and sample of every cell of ``grid``.

        ``cell_height`` holds the height of every cell in the height system
        of the annotation grid. The smooth parts of the mapping are evaluated
        on a coarse lattice (every ``lattice_cells`` cells, with a margin for
        the height shift) and interpolated bilinearly.
        """

        from scipy.interpolate import RegularGridInterpolator

        heights = np.asarray(cell_height, dtype="float64")
        if heights.shape != grid.shape:
            raise Sentinel1Error("cell_height must have the shape of the grid")
        if not np.all(np.isfinite(heights)):
            raise Sentinel1Error("every cell needs a finite height")
        x_centres, y_centres = grid.cell_centres()
        step = lattice_cells * grid.cell_m
        margin = float(np.max(np.abs(heights)) / np.min(self.tan_incidence)) + 2.0 * step
        west, south, east, north = grid.bounds
        lattice_x = np.arange(west - margin, east + margin + step, step)
        lattice_y = np.arange(south - margin, north + margin + step, step)
        mesh_x, mesh_y = np.meshgrid(lattice_x, lattice_y)
        fields = {
            name: RegularGridInterpolator(
                (lattice_y, lattice_x), self._field(values, mesh_x, mesh_y), method="linear"
            )
            for name, values in (
                ("line", np.broadcast_to(self.lines[:, None], self.x0.shape)),
                ("pixel", np.broadcast_to(self.pixels[None, :], self.x0.shape)),
                ("range_x", self.range_x),
                ("range_y", self.range_y),
                ("tan_incidence", self.tan_incidence),
            )
        }
        rows = np.empty(grid.shape, dtype="float64")
        cols = np.empty(grid.shape, dtype="float64")
        for index in range(grid.height):
            here = np.column_stack([np.full(grid.width, y_centres[index]), x_centres])
            shift = -heights[index] / fields["tan_incidence"](here)
            moved = np.column_stack(
                [here[:, 0] + fields["range_y"](here) * shift, here[:, 1] + fields["range_x"](here) * shift]
            )
            rows[index] = fields["line"](moved)
            cols[index] = fields["pixel"](moved)
        return rows, cols


def sample_window(window: Sigma0Window, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """Sample a calibrated window bilinearly at full-image coordinates.

    Positions outside the window, or next to a cell without data, are NaN.
    """

    from scipy.ndimage import map_coordinates

    coordinates = np.stack(
        [np.asarray(rows, dtype="float64") - window.row_offset, np.asarray(cols, dtype="float64") - window.col_offset]
    )
    sampled = map_coordinates(
        window.values.astype("float64"), coordinates, order=1, mode="constant", cval=np.nan, prefilter=False
    )
    return sampled.astype("float32")


# ---------------------------------------------------------------------------
# Measuring a displacement against a map layer
# ---------------------------------------------------------------------------


def estimate_displacement(
    reference: np.ndarray,
    image: np.ndarray,
    valid: np.ndarray,
    *,
    max_shift_cells: int,
) -> dict[str, Any]:
    """Estimate by how many cells an image is displaced from a reference layer.

    Both layers are reduced to zero mean over the valid cells and compared at
    every whole-cell shift up to ``max_shift_cells`` in each direction. The
    result is the shift of the image content relative to the reference at the
    highest correlation: ``east_cells`` positive when the image content lies
    east of where the reference has it, ``north_cells`` positive when it lies
    north. ``correlation`` is the normalised correlation at that shift, and
    ``at_search_edge`` says that the best shift is on the edge of the search
    window, where it cannot be trusted.

    The layers must be positively related (for a water mask and backscatter,
    pass the negated backscatter).
    """

    mask = np.asarray(valid, dtype=bool)
    first = np.asarray(reference, dtype="float64")
    second = np.asarray(image, dtype="float64")
    if first.ndim != 2 or first.shape != second.shape or mask.shape != first.shape:
        raise Sentinel1Error("the reference, the image and the valid mask must share a two-dimensional shape")
    if max_shift_cells < 1 or 2 * max_shift_cells >= min(first.shape):
        raise Sentinel1Error("max_shift_cells must be positive and smaller than half the image")
    mask = mask & np.isfinite(first) & np.isfinite(second)
    count = int(mask.sum())
    if count < 2:
        raise Sentinel1Error("too few valid cells to compare")
    first = np.where(mask, first - first[mask].mean(), 0.0)
    second = np.where(mask, second - second[mask].mean(), 0.0)
    norm = float(np.sqrt((first * first).sum() * (second * second).sum()))
    if norm == 0.0:
        raise Sentinel1Error("one of the layers is constant over the valid cells")
    shape = (first.shape[0] + max_shift_cells, first.shape[1] + max_shift_cells)
    spectrum = np.fft.rfft2(first, shape) * np.conj(np.fft.rfft2(second, shape))
    correlation = np.fft.irfft2(spectrum, shape) / norm
    best = (-np.inf, 0, 0)
    for row_shift in range(-max_shift_cells, max_shift_cells + 1):
        line = correlation[row_shift % shape[0]]
        for col_shift in range(-max_shift_cells, max_shift_cells + 1):
            value = float(line[col_shift % shape[1]])
            if value > best[0]:
                best = (value, row_shift, col_shift)
    value, row_shift, col_shift = best
    # correlation[d] sums reference[p] * image[p - d]: the image content sits at p - d.
    return {
        "east_cells": -col_shift,
        "north_cells": row_shift,
        "correlation": round(value, 6),
        "at_search_edge": abs(row_shift) == max_shift_cells or abs(col_shift) == max_shift_cells,
        "valid_cells": count,
        "max_shift_cells": max_shift_cells,
    }
