"""Canonical projected-grid, tile, and query-core contracts.

Tile identifiers are derived from a registered projected-grid origin and grid
indices.  They therefore do not depend on export order or on the bounds of a
particular source raster.  Query rows count from the north edge of a tile and
query columns count from its west edge, matching normal raster display order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from typing import Protocol

from floodguard.label_factory.contracts import DatasetRole


class GridContractError(ValueError):
    """Raised when a projected grid, identifier, or core is invalid."""


_EVENT_ID_PATTERN = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*")
_EPSG_PATTERN = re.compile(r"EPSG:(\d+)", flags=re.IGNORECASE)
_FALLBACK_METRE_PROJECTED_EPSG = {
    3395,  # WGS 84 / World Mercator
    3857,  # WGS 84 / Pseudo-Mercator
    24047,  # Indian 1975 / UTM zone 47N
    24048,  # Indian 1975 / UTM zone 48N
}


@dataclass(frozen=True)
class Bounds:
    """Axis-aligned projected bounds in metres."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        values = (self.min_x, self.min_y, self.max_x, self.max_y)
        if not all(math.isfinite(value) for value in values):
            raise GridContractError("Core bounds must contain finite coordinates.")
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise GridContractError(
                "Core bounds require min_x < max_x and min_y < max_y."
            )

    def contains(self, other: Bounds, *, tolerance: float = 1e-9) -> bool:
        """Return whether ``other`` lies fully inside these bounds."""

        return (
            other.min_x >= self.min_x - tolerance
            and other.min_y >= self.min_y - tolerance
            and other.max_x <= self.max_x + tolerance
            and other.max_y <= self.max_y + tolerance
        )

    def overlaps(self, other: Bounds, *, tolerance: float = 1e-9) -> bool:
        """Return whether interiors overlap; edge contact is allowed."""

        overlap_x = min(self.max_x, other.max_x) - max(self.min_x, other.min_x)
        overlap_y = min(self.max_y, other.max_y) - max(self.min_y, other.min_y)
        return overlap_x > tolerance and overlap_y > tolerance


@dataclass(frozen=True)
class ProjectedGridSpec:
    """One metre-based EPSG grid with an immutable registered origin.

    The event registry must freeze ``origin_x`` and ``origin_y`` before IDs are
    issued.  Source rasters must be aligned/resampled to this contract; a
    source-specific raster origin must not silently redefine tile identifiers.
    The default origin is projected coordinate ``(0, 0)``.
    """

    crs: str
    resolution_m: float = 10.0
    tile_size_cells: int = 256
    origin_x: float = 0.0
    origin_y: float = 0.0

    def __post_init__(self) -> None:
        normalized_crs = validate_projected_metre_crs(self.crs)
        resolution = _positive_decimal(self.resolution_m, "resolution_m")
        if isinstance(self.tile_size_cells, bool) or not isinstance(
            self.tile_size_cells, int
        ):
            raise GridContractError("tile_size_cells must be an integer.")
        if self.tile_size_cells <= 0:
            raise GridContractError("tile_size_cells must be positive.")
        origin_x = _finite_decimal(self.origin_x, "origin_x")
        origin_y = _finite_decimal(self.origin_y, "origin_y")
        object.__setattr__(self, "crs", normalized_crs)
        object.__setattr__(self, "resolution_m", float(resolution))
        object.__setattr__(self, "origin_x", float(origin_x))
        object.__setattr__(self, "origin_y", float(origin_y))

    @property
    def epsg_code(self) -> int:
        """Return the validated EPSG code."""

        match = _EPSG_PATTERN.fullmatch(self.crs)
        if match is None:  # Defensive: validation currently guarantees this.
            raise GridContractError(f"Grid CRS has no EPSG code: {self.crs!r}")
        return int(match.group(1))

    @property
    def crs_token(self) -> str:
        """Return a compact stable CRS token used in identifiers."""

        code = self.epsg_code
        if 32601 <= code <= 32660:
            return f"UTM{code - 32600:02d}N"
        if 32701 <= code <= 32760:
            return f"UTM{code - 32700:02d}S"
        return f"EPSG{code}"

    @property
    def resolution_token(self) -> str:
        """Return a filesystem-safe resolution token such as ``10M``."""

        return f"{_decimal_token(self.resolution_m)}M"

    @property
    def grid_id(self) -> str:
        """Return the stable public grid identifier used in manifests."""

        return (
            f"{self.crs_token}_{self.resolution_token}_G{self.contract_sha256[:10].upper()}"
        )

    @property
    def contract_sha256(self) -> str:
        """Fingerprint CRS, resolution, tile size, and registered origin."""

        payload = json.dumps(
            list(self.contract_key),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def tile_span_m(self) -> float:
        """Return the side length of a storage-tile core in metres."""

        return self.resolution_m * self.tile_size_cells

    @property
    def contract_key(self) -> tuple[str, str, int, str, str]:
        """Return an exact comparable key for same-event grid validation."""

        return (
            self.crs,
            self.resolution_token,
            self.tile_size_cells,
            _canonical_decimal_text(self.origin_x),
            _canonical_decimal_text(self.origin_y),
        )


@dataclass(frozen=True)
class TileCore:
    """One non-overlapping storage-tile core on a canonical grid."""

    event_id: str
    grid: ProjectedGridSpec
    x_index: int
    y_index: int
    dataset_role: DatasetRole

    def __post_init__(self) -> None:
        validate_event_id(self.event_id)
        _validate_index(self.x_index, "x_index")
        _validate_index(self.y_index, "y_index")
        if not isinstance(self.dataset_role, DatasetRole):
            raise GridContractError("dataset_role must be a DatasetRole value.")

    @property
    def core_id(self) -> str:
        """Return the stable tile identifier."""

        return self.tile_id

    @property
    def tile_id(self) -> str:
        """Return the stable manifest ``tile_id`` value."""

        return make_tile_id(
            self.event_id,
            self.grid,
            x_index=self.x_index,
            y_index=self.y_index,
        )

    @property
    def bounds(self) -> Bounds:
        """Return tile-core bounds in the grid CRS."""

        span = Decimal(str(self.grid.resolution_m)) * self.grid.tile_size_cells
        min_x = Decimal(str(self.grid.origin_x)) + span * self.x_index
        min_y = Decimal(str(self.grid.origin_y)) + span * self.y_index
        return Bounds(
            min_x=float(min_x),
            min_y=float(min_y),
            max_x=float(min_x + span),
            max_y=float(min_y + span),
        )


@dataclass(frozen=True)
class QueryCore:
    """A square human-annotation core inside one storage tile.

    ``row_index`` and ``column_index`` are query-grid indices, not raw pixel
    offsets.  For a 64-cell query in a 256-cell tile, valid indices are 0..3.
    Rows count from the tile's north edge; columns count from its west edge.
    """

    tile: TileCore
    row_index: int
    column_index: int
    size_cells: int

    def __post_init__(self) -> None:
        _validate_nonnegative_index(self.row_index, "row_index")
        _validate_nonnegative_index(self.column_index, "column_index")
        if isinstance(self.size_cells, bool) or not isinstance(self.size_cells, int):
            raise GridContractError("size_cells must be an integer.")
        if self.size_cells <= 0:
            raise GridContractError("size_cells must be positive.")
        tile_size = self.tile.grid.tile_size_cells
        if tile_size % self.size_cells != 0:
            raise GridContractError(
                "size_cells must divide tile_size_cells so query IDs remain on "
                "a stable non-overlapping lattice."
            )
        query_count = tile_size // self.size_cells
        if self.row_index >= query_count or self.column_index >= query_count:
            raise GridContractError(
                "Query core lies outside its tile: "
                f"valid row/column indices are 0..{query_count - 1}."
            )

    @property
    def event_id(self) -> str:
        """Return the parent event identifier."""

        return self.tile.event_id

    @property
    def grid(self) -> ProjectedGridSpec:
        """Return the parent canonical grid."""

        return self.tile.grid

    @property
    def dataset_role(self) -> DatasetRole:
        """Return the immutable parent tile's dataset role."""

        return self.tile.dataset_role

    @property
    def core_id(self) -> str:
        """Return the stable query-region identifier."""

        return self.query_region_id

    @property
    def query_region_id(self) -> str:
        """Return the stable manifest ``query_region_id`` value."""

        return make_query_region_id(
            self.tile.tile_id,
            row_index=self.row_index,
            column_index=self.column_index,
            size_cells=self.size_cells,
        )

    @property
    def bounds(self) -> Bounds:
        """Return query-core bounds in the grid CRS."""

        resolution = Decimal(str(self.grid.resolution_m))
        size_m = resolution * self.size_cells
        tile_bounds = self.tile.bounds
        min_x = Decimal(str(tile_bounds.min_x)) + size_m * self.column_index
        max_y = Decimal(str(tile_bounds.max_y)) - size_m * self.row_index
        bounds = Bounds(
            min_x=float(min_x),
            min_y=float(max_y - size_m),
            max_x=float(min_x + size_m),
            max_y=float(max_y),
        )
        if not tile_bounds.contains(bounds, tolerance=self.grid.resolution_m * 1e-9):
            raise GridContractError(
                f"Query core {self.core_id} extends outside tile {self.tile.tile_id}."
            )
        return bounds

    def contains_bounds(self, bounds: Bounds) -> bool:
        """Return whether annotation bounds remain inside the query core."""

        return self.bounds.contains(
            bounds,
            tolerance=self.grid.resolution_m * 1e-9,
        )


class _Core(Protocol):
    @property
    def core_id(self) -> str: ...

    @property
    def event_id(self) -> str: ...

    @property
    def grid(self) -> ProjectedGridSpec: ...

    @property
    def bounds(self) -> Bounds: ...


def validate_projected_metre_crs(crs: str) -> str:
    """Validate an EPSG CRS as projected and metre-based, then normalize it.

    WGS 84 UTM, Indian 1975 UTM zones used in Thailand, and common metre-based
    world Mercator codes can be validated without optional dependencies.  For
    other EPSG codes, ``pyproj`` is used when installed; otherwise validation
    fails closed instead of guessing whether angular or foot units were used.
    """

    if not isinstance(crs, str) or not crs.strip():
        raise GridContractError("crs must be a non-empty EPSG string.")
    match = _EPSG_PATTERN.fullmatch(crs.strip())
    if match is None:
        raise GridContractError(
            "crs must use an explicit EPSG:<code> identifier for stable tile IDs."
        )
    code = int(match.group(1))
    normalized = f"EPSG:{code}"

    if (
        32601 <= code <= 32660
        or 32701 <= code <= 32760
        or code in _FALLBACK_METRE_PROJECTED_EPSG
    ):
        return normalized

    try:
        from pyproj import CRS  # type: ignore[import-not-found]
        from pyproj.exceptions import CRSError  # type: ignore[import-not-found]
    except ImportError as exc:
        raise GridContractError(
            f"Cannot verify that {normalized} is projected in metres without "
            "the optional pyproj dependency; use a supported UTM CRS."
        ) from exc

    try:
        parsed = CRS.from_epsg(code)
    except CRSError as exc:
        raise GridContractError(f"Unknown or invalid CRS: {normalized}.") from exc
    if not parsed.is_projected:
        raise GridContractError(f"CRS {normalized} is not projected.")
    axis_info = tuple(parsed.axis_info)
    if not axis_info or any(
        not math.isclose(float(axis.unit_conversion_factor), 1.0, abs_tol=1e-12)
        for axis in axis_info[:2]
    ):
        raise GridContractError(f"CRS {normalized} does not use metre axes.")
    return normalized


def validate_event_id(event_id: str) -> str:
    """Validate and return a canonical event identifier."""

    if not isinstance(event_id, str) or _EVENT_ID_PATTERN.fullmatch(event_id) is None:
        raise GridContractError(
            "event_id must contain uppercase A-Z, digits, and single hyphens only."
        )
    return event_id


def make_tile_id(
    event_id: str,
    grid: ProjectedGridSpec,
    *,
    x_index: int,
    y_index: int,
) -> str:
    """Build a stable storage-tile identifier from canonical grid indices."""

    validate_event_id(event_id)
    _validate_index(x_index, "x_index")
    _validate_index(y_index, "y_index")
    return (
        f"{event_id}_{grid.grid_id}_"
        f"X{_index_token(x_index, width=5)}_Y{_index_token(y_index, width=5)}"
    )


def make_query_region_id(
    tile_id: str,
    *,
    row_index: int,
    column_index: int,
    size_cells: int,
) -> str:
    """Build a stable query identifier from its parent tile and core lattice."""

    if not isinstance(tile_id, str) or not tile_id.strip():
        raise GridContractError("tile_id must be non-empty.")
    _validate_nonnegative_index(row_index, "row_index")
    _validate_nonnegative_index(column_index, "column_index")
    if isinstance(size_cells, bool) or not isinstance(size_cells, int):
        raise GridContractError("size_cells must be an integer.")
    if size_cells <= 0:
        raise GridContractError("size_cells must be positive.")
    return (
        f"{tile_id}_R{row_index:02d}_C{column_index:02d}_S{size_cells}"
    )


def validate_non_overlapping_cores(cores: Sequence[_Core]) -> None:
    """Reject duplicate or spatially overlapping cores within the same event.

    All cores for one event must share exactly one grid contract.  Cores from
    different events may occupy the same geography because their acquisition
    times and labels are independent.  Edge-touching cores are valid.
    """

    seen_ids: set[str] = set()
    event_grids: dict[str, tuple[str, str, int, str, str]] = {}
    for core in cores:
        if core.core_id in seen_ids:
            raise GridContractError(f"Duplicate core identifier: {core.core_id}.")
        seen_ids.add(core.core_id)
        previous_grid = event_grids.setdefault(core.event_id, core.grid.contract_key)
        if previous_grid != core.grid.contract_key:
            raise GridContractError(
                f"Event {core.event_id!r} uses more than one canonical grid contract."
            )

    for index, left in enumerate(cores):
        for right in cores[index + 1 :]:
            if left.event_id != right.event_id:
                continue
            tolerance = left.grid.resolution_m * 1e-9
            if left.bounds.overlaps(right.bounds, tolerance=tolerance):
                raise GridContractError(
                    f"Core interiors overlap: {left.core_id} and {right.core_id}."
                )


def require_bounds_within_query_core(
    annotation_bounds: Bounds,
    query_core: QueryCore,
) -> None:
    """Reject annotation bounds that extend outside their query core."""

    if not query_core.contains_bounds(annotation_bounds):
        raise GridContractError(
            f"Annotation bounds extend outside query core {query_core.core_id}."
        )


def _positive_decimal(value: object, field_name: str) -> Decimal:
    decimal = _finite_decimal(value, field_name)
    if decimal <= 0:
        raise GridContractError(f"{field_name} must be a positive finite number.")
    return decimal


def _finite_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise GridContractError(f"{field_name} must be a finite number.")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GridContractError(f"{field_name} must be a finite number.") from exc
    if not decimal.is_finite():
        raise GridContractError(f"{field_name} must be a finite number.")
    return decimal


def _decimal_token(value: object) -> str:
    decimal = _positive_decimal(value, "resolution_m")
    text = _canonical_decimal_text(decimal)
    return text.replace(".", "P")


def _canonical_decimal_text(value: object) -> str:
    decimal = Decimal(str(value))
    text = format(decimal.normalize(), "f")
    return "0" if text in {"-0", "+0"} else text


def _validate_index(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GridContractError(f"{field_name} must be an integer.")


def _validate_nonnegative_index(value: int, field_name: str) -> None:
    _validate_index(value, field_name)
    if value < 0:
        raise GridContractError(f"{field_name} must be non-negative.")


def _index_token(value: int, *, width: int) -> str:
    sign = "N" if value < 0 else ""
    return f"{sign}{abs(value):0{width}d}"
