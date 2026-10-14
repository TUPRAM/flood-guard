"""M1-z, the radar method of the Nan case, with its comparators, its counting and its selection rule.

The rules are those of ``docs/proposal_execution/nan_case_protocol_v1.json`` ("method", "tuning", "tests");
``docs/proposal_execution/nan_case_plan_v1.md`` says the same in words. Every function here is pure: it takes
numpy arrays on one 20 m grid and returns arrays or plain records. ``scripts/nan_case_method.py`` reads the files
and runs the stages.

M1-z sets each cell's VH backscatter on the flood day against its own dry-season mean and spread. A cell is
flagged when it is both anomalous (``z_vh <= z_vh_max``) and dark (``VH_after_db <= vh_after_max_db``).
Permanent water is never flagged; high or steep ground is answered "not flooded" by terrain; cells where the
radar cannot be asked get no answer; flagged groups of fewer than 2 cells (8-connected) are dropped.

Map codes: 1 flagged, 0 not flagged (by the radar, by terrain, or permanent water), 255 no answer. A second
raster gives the reason of every cell (``REASON_LABELS``).

Every figure made with these functions is agreement with a reference layer, not accuracy. Nothing here computes
a planning score or a class, and no map is an official warning. Planning guidance only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

import numpy as np

CELL_M: float = 20.0
PERMANENT_WATER_CLASS: int = 80
BUILT_UP_CLASS: int = 50
CROPLAND_CLASS: int = 40
TREE_COVER_CLASS: int = 10
MIN_DRY_PASSES: int = 6
MAX_SLOPE_DEG: float = 5.0
MIN_GROUP_CELLS: int = 2
"""800 m2 at 20 m: the 8 cells at 10 m of the October detector."""
FLOOD_AXIS_STEP_Z: float = 0.5
"""Lower flood = the selected z_vh_max minus 0.5; upper flood = plus 0.5 (protocol, tuning)."""

TUNED_PARAMETERS: dict[str, tuple[Any, ...]] = {
    "z_vh_max": (-1.0, -1.5, -2.0, -2.5, -3.0),
    "vh_after_max_db": (-15.0, -16.0, -17.0, -18.0, -19.0, -20.0),
    "hand_max_m": (5.0, 10.0, 15.0, 20.0),
    "dry_spread_max_db": (2.0, 3.0, None),
}
"""The candidate values of protocol v1 ("method", "tuned_parameters"); the script reads them from the protocol."""
MAX_NO_ANSWER_SHARE: float = 0.20
TIE_MARGIN: float = 0.01

FLAGGED: int = 1
NOT_FLAGGED: int = 0
NO_ANSWER: int = 255

REASON_ASKED: int = 0
"""Only inside :func:`static_reasons`: the cell is asked of the radar. Never left in a finished reason raster."""
REASON_FLAGGED: int = 1
REASON_RADAR_DRY: int = 2
REASON_SMALL_GROUP: int = 3
REASON_TERRAIN_HAND: int = 10
REASON_TERRAIN_SLOPE: int = 11
REASON_PERMANENT_WATER: int = 20
REASON_NO_RADAR_AFTER: int = 101
REASON_FEW_DRY_PASSES: int = 102
REASON_DRY_SPREAD: int = 103
REASON_BUILT_UP_LOW: int = 104
REASON_TREE_COVER_LOW: int = 105
REASON_NO_TERRAIN: int = 106
REASON_LABELS: dict[int, str] = {
    REASON_FLAGGED: "flagged",
    REASON_RADAR_DRY: "not_flagged_radar_dry",
    REASON_SMALL_GROUP: "not_flagged_group_of_fewer_than_2_cells_dropped",
    REASON_TERRAIN_HAND: "not_flagged_terrain_hand_above_the_limit",
    REASON_TERRAIN_SLOPE: "not_flagged_terrain_slope_5_degrees_or_more",
    REASON_PERMANENT_WATER: "not_flagged_permanent_water",
    REASON_NO_RADAR_AFTER: "no_answer_rtc_no_data_after",
    REASON_FEW_DRY_PASSES: "no_answer_fewer_than_6_valid_dry_passes",
    REASON_DRY_SPREAD: "no_answer_vh_dry_spread_above_the_limit",
    REASON_BUILT_UP_LOW: "no_answer_built_up_at_low_hand",
    REASON_TREE_COVER_LOW: "no_answer_tree_cover_at_low_hand",
    REASON_NO_TERRAIN: "no_answer_no_terrain_value",
}
NOT_FLAGGED_REASONS: tuple[int, ...] = (REASON_RADAR_DRY, REASON_SMALL_GROUP, REASON_TERRAIN_HAND, REASON_TERRAIN_SLOPE,
                                        REASON_PERMANENT_WATER)
NO_ANSWER_REASONS: tuple[int, ...] = (REASON_NO_RADAR_AFTER, REASON_FEW_DRY_PASSES, REASON_DRY_SPREAD, REASON_BUILT_UP_LOW,
                                      REASON_TREE_COVER_LOW, REASON_NO_TERRAIN)

# The comparators of decision log R37 (outputs/radar_detection_improvement/freeze_v1.json, step simple_threshold_cleaned).
R37_THRESHOLD_DB: float = -18.46
R37_GROW_DB: float = 1.5
R37_MAX_SLOPE_DEG: float = 5.0
R37_WINDOW_10M: int = 5
R37_WINDOW_20M: int = 3
"""The 5 by 5 mean of 10 m cells covers 50 m; at 20 m the nearest odd window is 3 by 3 (60 m)."""
UN_SPIDER_MIN_CELLS_20M: int = 2
"""The practice drops groups of fewer than 8 cells of 10 m (800 m2); at 20 m that is 2 cells."""
GEOID_TILE_M: float = 10240.0
"""The lattice of M1-literal and M1-v2: tiles of 1024 cells of 10 m, corners at whole multiples of 10,240 m."""

COVER_GROUPS: dict[str, tuple[int, ...]] = {"built_up": (BUILT_UP_CLASS,), "cropland": (CROPLAND_CLASS,), "tree_cover": (TREE_COVER_CLASS,)}
"""ESA WorldCover groups of the protocol's measures; every other class is ``other``."""

BOOTSTRAP_TILE_CELLS: int = 100
"""2 km at 20 m."""
BOOTSTRAP_RESAMPLES: int = 1000
BOOTSTRAP_SEED: int = 20261014

WATER_LABEL: str = "water"
NOT_WATER_LABEL: str = "not_water"


class M1zError(ValueError):
    """The arrays or the parameters cannot support the method."""


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class M1zParameters:
    """The four tuned limits of M1-z. ``dry_spread_max_db`` ``None`` means no limit on the dry spread."""

    z_vh_max: float
    vh_after_max_db: float
    hand_max_m: float
    dry_spread_max_db: float | None

    def as_json(self) -> dict[str, Any]:
        """The parameters as a JSON object."""

        return {"z_vh_max": float(self.z_vh_max), "vh_after_max_db": float(self.vh_after_max_db), "hand_max_m": float(self.hand_max_m),
                "dry_spread_max_db": None if self.dry_spread_max_db is None else float(self.dry_spread_max_db)}

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "M1zParameters":
        """Read parameters from a JSON object written by :meth:`as_json`."""

        spread = value.get("dry_spread_max_db")
        return cls(z_vh_max=float(value["z_vh_max"]), vh_after_max_db=float(value["vh_after_max_db"]),
                   hand_max_m=float(value["hand_max_m"]), dry_spread_max_db=None if spread is None else float(spread))

    def with_z(self, z_vh_max: float) -> "M1zParameters":
        """The same parameters with another z limit."""

        return M1zParameters(float(z_vh_max), self.vh_after_max_db, self.hand_max_m, self.dry_spread_max_db)


def candidate_grid(values: Mapping[str, Sequence[Any]] = TUNED_PARAMETERS) -> list[M1zParameters]:
    """Every combination of the tuned values, in the protocol's order (z outermost, dry spread innermost)."""

    for name in ("z_vh_max", "vh_after_max_db", "hand_max_m", "dry_spread_max_db"):
        if not values.get(name):
            raise M1zError(f"no candidate value for {name}")
    return [M1zParameters(float(z), float(vh), float(hand), None if spread is None else float(spread))
            for z in values["z_vh_max"] for vh in values["vh_after_max_db"] for hand in values["hand_max_m"]
            for spread in values["dry_spread_max_db"]]


def flood_levels(selected: M1zParameters, step: float = FLOOD_AXIS_STEP_Z) -> dict[str, M1zParameters]:
    """The flood axis of the ensemble: lower (z limit minus ``step``), central, upper (plus ``step``)."""

    return {"lower": selected.with_z(selected.z_vh_max - step), "central": selected, "upper": selected.with_z(selected.z_vh_max + step)}


# ---------------------------------------------------------------------------
# The method
# ---------------------------------------------------------------------------


def to_db(linear: np.ndarray) -> np.ndarray:
    """10 log10 of linear backscatter, float32; NaN where the value is not finite or not above zero."""

    values = np.asarray(linear, dtype="float32")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.isfinite(values) & (values > 0), 10.0 * np.log10(values), np.nan).astype("float32")


def z_score(vh_after_db: np.ndarray, dry_mean_db: np.ndarray, dry_std_db: np.ndarray) -> np.ndarray:
    """``(VH_after_db - VH_dry_mean_db) / VH_dry_std_db``, float32.

    A spread of zero gives minus or plus infinity (or NaN where the two values are equal); a missing value gives NaN.
    """

    after, mean, spread = (np.asarray(item, dtype="float32") for item in (vh_after_db, dry_mean_db, dry_std_db))
    if not (after.shape == mean.shape == spread.shape):
        raise M1zError("the image after and the dry-season statistics must share one shape")
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((after - mean) / spread).astype("float32")


def radar_flag(vh_after_db: np.ndarray, z: np.ndarray, z_vh_max: float, vh_after_max_db: float) -> np.ndarray:
    """The double rule: anomalous (``z <= z_vh_max``) and dark (``VH_after_db <= vh_after_max_db``)."""

    after, score = np.asarray(vh_after_db), np.asarray(z)
    if after.shape != score.shape:
        raise M1zError("VH after and z must share one shape")
    with np.errstate(invalid="ignore"):
        return (score <= z_vh_max) & (after <= vh_after_max_db)


def _check_layers(shape: tuple[int, ...], **layers: np.ndarray) -> None:
    if len(shape) != 2:
        raise M1zError("the layers must be two-dimensional")
    for name, layer in layers.items():
        if np.asarray(layer).shape != shape:
            raise M1zError(f"{name} does not have the shape of VH after")


def static_reasons(vh_after_db: np.ndarray, dry_mean_db: np.ndarray, dry_std_db: np.ndarray, dry_valid_passes: np.ndarray,
                   hand_m: np.ndarray, slope_deg: np.ndarray, land_cover: np.ndarray, *, hand_max_m: float,
                   dry_spread_max_db: float | None, permanent_water: np.ndarray | None = None,
                   min_dry_passes: int = MIN_DRY_PASSES, max_slope_deg: float = MAX_SLOPE_DEG) -> np.ndarray:
    """The reason of every cell that the radar is not asked about; ``REASON_ASKED`` (0) where it is.

    Precedence, first match wins: permanent water (``permanent_water``, by default ESA WorldCover class 80); the
    terrain answer (slope of ``max_slope_deg`` or more, then HAND above ``hand_max_m``); then no answer: RTC no data
    after, fewer than ``min_dry_passes`` valid dry passes (or no dry mean or spread), VH dry spread above
    ``dry_spread_max_db`` when that limit is not ``None``, no HAND or slope value, built-up (50) and tree cover (10)
    at HAND at or below ``hand_max_m``. Returns ``uint8``.
    """

    after = np.asarray(vh_after_db, dtype="float32")
    _check_layers(after.shape, dry_mean_db=dry_mean_db, dry_std_db=dry_std_db, dry_valid_passes=dry_valid_passes,
                  hand_m=hand_m, slope_deg=slope_deg, land_cover=land_cover)
    cover = np.asarray(land_cover)
    water = cover == PERMANENT_WATER_CLASS if permanent_water is None else np.asarray(permanent_water, dtype=bool)
    if water.shape != after.shape:
        raise M1zError("permanent_water does not have the shape of VH after")
    hand = np.asarray(hand_m, dtype="float32")
    slope = np.asarray(slope_deg, dtype="float32")
    mean = np.asarray(dry_mean_db, dtype="float32")
    spread = np.asarray(dry_std_db, dtype="float32")
    passes = np.nan_to_num(np.asarray(dry_valid_passes, dtype="float32"), nan=0.0)
    with np.errstate(invalid="ignore"):
        steep = np.isfinite(slope) & (slope >= max_slope_deg)
        high = np.isfinite(hand) & (hand > hand_max_m)
        low = np.isfinite(hand) & (hand <= hand_max_m)
        no_after = ~np.isfinite(after)
        few = (passes < min_dry_passes) | ~np.isfinite(mean) | ~np.isfinite(spread)
        unstable = np.zeros(after.shape, dtype=bool) if dry_spread_max_db is None else (spread > float(dry_spread_max_db))
    no_terrain = ~np.isfinite(hand) | ~np.isfinite(slope)
    conditions = [water, steep, high, no_after, few, unstable, no_terrain, low & (cover == BUILT_UP_CLASS), low & (cover == TREE_COVER_CLASS)]
    choices = [REASON_PERMANENT_WATER, REASON_TERRAIN_SLOPE, REASON_TERRAIN_HAND, REASON_NO_RADAR_AFTER, REASON_FEW_DRY_PASSES,
               REASON_DRY_SPREAD, REASON_NO_TERRAIN, REASON_BUILT_UP_LOW, REASON_TREE_COVER_LOW]
    return np.select(conditions, choices, default=REASON_ASKED).astype("uint8")


def keep_groups(mask: np.ndarray, min_cells: int = MIN_GROUP_CELLS) -> np.ndarray:
    """The cells of ``mask`` that belong to an 8-connected group of at least ``min_cells`` cells."""

    from scipy import ndimage

    flags = np.asarray(mask, dtype=bool)
    if flags.ndim != 2:
        raise M1zError("the mask must be two-dimensional")
    if min_cells < 1:
        raise M1zError("min_cells must be at least 1")
    if min_cells == 1 or not flags.any():
        return flags.copy()
    labels, count = ndimage.label(flags, structure=np.ones((3, 3), dtype=bool))
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    keep = sizes >= min_cells
    keep[0] = False
    return keep[labels]


def finish(static: np.ndarray, raw_flag: np.ndarray, *, min_group: int = MIN_GROUP_CELLS) -> tuple[np.ndarray, np.ndarray]:
    """Combine the static reasons with the radar's double rule into the map codes and the reasons.

    Only cells asked of the radar can be flagged; flagged groups of fewer than ``min_group`` cells are dropped
    afterwards. Returns ``(code, reason)``, both ``uint8``.
    """

    reasons = np.asarray(static, dtype="uint8")
    flag = np.asarray(raw_flag, dtype=bool)
    if reasons.shape != flag.shape:
        raise M1zError("the static reasons and the radar flags must share one shape")
    asked = reasons == REASON_ASKED
    flagged = asked & flag
    kept = keep_groups(flagged, min_group)
    code = np.full(reasons.shape, NO_ANSWER, dtype="uint8")
    code[np.isin(reasons, (REASON_PERMANENT_WATER, REASON_TERRAIN_HAND, REASON_TERRAIN_SLOPE)) | asked] = NOT_FLAGGED
    code[kept] = FLAGGED
    reason = reasons.copy()
    reason[asked] = REASON_RADAR_DRY
    reason[flagged & ~kept] = REASON_SMALL_GROUP
    reason[kept] = REASON_FLAGGED
    return code, reason


def classify(vh_after_db: np.ndarray, dry_mean_db: np.ndarray, dry_std_db: np.ndarray, dry_valid_passes: np.ndarray,
             hand_m: np.ndarray, slope_deg: np.ndarray, land_cover: np.ndarray, parameters: M1zParameters, *,
             permanent_water: np.ndarray | None = None, min_dry_passes: int = MIN_DRY_PASSES,
             max_slope_deg: float = MAX_SLOPE_DEG, min_group: int = MIN_GROUP_CELLS) -> tuple[np.ndarray, np.ndarray]:
    """M1-z on one pass: the map codes (1, 0, 255) and the reason of every cell.

    ``vh_after_db`` is VH of the pass in dB on the 20 m grid; ``dry_mean_db`` and ``dry_std_db`` the dry-season
    mean and population spread of VH dB of the same orbit; ``dry_valid_passes`` the number of valid dry passes;
    ``hand_m``, ``slope_deg`` and ``land_cover`` (ESA WorldCover classes) the terrain of the same cells.
    """

    static = static_reasons(vh_after_db, dry_mean_db, dry_std_db, dry_valid_passes, hand_m, slope_deg, land_cover,
                            hand_max_m=parameters.hand_max_m, dry_spread_max_db=parameters.dry_spread_max_db,
                            permanent_water=permanent_water, min_dry_passes=min_dry_passes, max_slope_deg=max_slope_deg)
    z = z_score(vh_after_db, dry_mean_db, dry_std_db)
    return finish(static, radar_flag(vh_after_db, z, parameters.z_vh_max, parameters.vh_after_max_db), min_group=min_group)


def classify_levels(vh_after_db: np.ndarray, dry_mean_db: np.ndarray, dry_std_db: np.ndarray, dry_valid_passes: np.ndarray,
                    hand_m: np.ndarray, slope_deg: np.ndarray, land_cover: np.ndarray, selected: M1zParameters, *,
                    permanent_water: np.ndarray | None = None, step: float = FLOOD_AXIS_STEP_Z) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """The lower, central and upper maps of one pass (:func:`flood_levels`); each is ``(code, reason)``.

    The three share every reason but the radar's, because only the z limit moves.
    """

    static = static_reasons(vh_after_db, dry_mean_db, dry_std_db, dry_valid_passes, hand_m, slope_deg, land_cover,
                            hand_max_m=selected.hand_max_m, dry_spread_max_db=selected.dry_spread_max_db, permanent_water=permanent_water)
    z = z_score(vh_after_db, dry_mean_db, dry_std_db)
    return {name: finish(static, radar_flag(vh_after_db, z, level.z_vh_max, level.vh_after_max_db))
            for name, level in flood_levels(selected, step).items()}


def reason_counts(reason: np.ndarray, where: np.ndarray | None = None) -> dict[str, int]:
    """Cells per reason label (only labels that occur)."""

    values = np.asarray(reason, dtype="uint8")
    if where is not None:
        values = values[np.asarray(where, dtype=bool)]
    counts = np.bincount(values.ravel(), minlength=256)
    return {REASON_LABELS.get(code, f"code_{code}"): int(counts[code]) for code in range(256) if counts[code]}


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------


def r37_vh_after_db(vh_after_linear: np.ndarray, window: int = R37_WINDOW_20M) -> np.ndarray:
    """VH after as the R37 detectors read it: the mean of the valid linear VH in a ``window`` square
    (:func:`floodguard.radar_flood_classifier.focal_mean`), then dB."""

    from floodguard import radar_flood_classifier as rfc

    linear = np.asarray(vh_after_linear, dtype="float64")
    with np.errstate(invalid="ignore"):
        linear = np.where(np.isfinite(linear) & (linear > 0), linear, np.nan)
    return to_db(rfc.focal_mean(linear, window))


def _r37_usable(vh_db: np.ndarray, slope_deg: np.ndarray, permanent_water: np.ndarray) -> np.ndarray:
    slope, water = np.asarray(slope_deg, dtype="float64"), np.asarray(permanent_water, dtype=bool)
    if slope.shape != vh_db.shape or water.shape != vh_db.shape:
        raise M1zError("slope and permanent water must have the shape of VH after")
    return np.isfinite(vh_db) & np.isfinite(slope) & ~water


def simple_threshold_r37(vh_after_linear: np.ndarray, slope_deg: np.ndarray, permanent_water: np.ndarray, *,
                         threshold_db: float = R37_THRESHOLD_DB, window: int = R37_WINDOW_20M) -> np.ndarray:
    """The simple VH threshold of R37: VH after (a ``window`` mean) at or below ``threshold_db``. Codes 1, 0, 255.

    A cell is answered where VH after and the slope have a value and the cell is not permanent water.
    """

    vh = r37_vh_after_db(vh_after_linear, window)
    usable = _r37_usable(vh, slope_deg, permanent_water)
    code = np.full(vh.shape, NO_ANSWER, dtype="uint8")
    code[usable] = NOT_FLAGGED
    with np.errstate(invalid="ignore"):
        code[usable & (vh <= threshold_db)] = FLAGGED
    return code


def frozen_detector_r37(vh_after_linear: np.ndarray, slope_deg: np.ndarray, permanent_water: np.ndarray, *,
                        threshold_db: float = R37_THRESHOLD_DB, grow_db: float = R37_GROW_DB, max_slope_deg: float = R37_MAX_SLOPE_DEG,
                        min_group: int = MIN_GROUP_CELLS, window: int = R37_WINDOW_20M) -> np.ndarray:
    """The detector frozen in decision log R37 (``simple_threshold_cleaned``), on the 20 m grid. Codes 1, 0, 255.

    The simple threshold, then the cleaning of :func:`floodguard.radar_detection.clean`: flags on slopes of
    ``max_slope_deg`` or more are dropped, then 8-connected groups of fewer than ``min_group`` cells; a kept group
    grows into the touching cells within ``grow_db`` of the threshold.
    """

    from floodguard import radar_detection as rd

    vh = r37_vh_after_db(vh_after_linear, window)
    usable = _r37_usable(vh, slope_deg, permanent_water)
    with np.errstate(invalid="ignore"):
        flag = usable & (vh <= threshold_db)
        nearly = usable & (vh <= threshold_db + grow_db)
    cleaned = rd.clean(flag, np.asarray(slope_deg, dtype="float64"), grow_from=nearly, max_slope=max_slope_deg, min_group=min_group)
    code = np.full(vh.shape, NO_ANSWER, dtype="uint8")
    code[usable] = NOT_FLAGGED
    code[cleaned & usable] = FLAGGED
    return code


def un_spider_dry_mean(vh_after_linear: np.ndarray, vh_dry_mean_db: np.ndarray, slope_deg: np.ndarray, permanent_water: np.ndarray,
                       *, cell_m: float = CELL_M, min_connected_cells: int = UN_SPIDER_MIN_CELLS_20M) -> np.ndarray:
    """The UN-SPIDER recommended practice with the dry-season mean as its image before. Codes 1, 0, 255.

    :func:`floodguard.radar_candidates.un_spider_candidate` with its published values, but for the group size,
    which is given in cells and set to the same area at 20 m (``min_connected_cells``).
    """

    from floodguard import radar_candidates as rc

    before = np.power(10.0, np.asarray(vh_dry_mean_db, dtype="float64") / 10.0)
    after = np.asarray(vh_after_linear, dtype="float64")
    config = rc.UnSpiderConfig(min_connected_cells=int(min_connected_cells))
    candidate, _reason, _quotient, _summary = rc.un_spider_candidate(
        before, after, in_frame=np.ones(after.shape, dtype=bool), permanent_water=np.asarray(permanent_water, dtype=bool),
        slope=np.asarray(slope_deg, dtype="float64"), cell_m=cell_m, config=config)
    return candidate.astype("uint8")


TileRunner = Callable[[np.ndarray, np.ndarray], tuple[Any, ...]]


def on_lattice(pre: np.ndarray, post: np.ndarray, runner: TileRunner, *, grid_west: float, grid_north: float,
               cell_m: float = CELL_M, tile_m: float = GEOID_TILE_M) -> np.ndarray:
    """Run a per-tile radar rule tile by tile on the GEOID lattice and put the candidates back on the grid.

    ``pre`` and ``post`` are ``(2, H, W)`` linear backscatter, VV before VH. Each lattice tile that overlaps the grid
    is handed to ``runner`` whole; the part of a tile outside the grid is NaN, so the rule sees no value there.
    ``runner`` returns the candidate (codes 1, 0, 255) first, as
    :func:`floodguard.radar_candidates.m1_literal_tile` and ``m1_v2_tile`` do.
    """

    from floodguard import radar_candidates as rc

    before, after = np.asarray(pre, dtype="float32"), np.asarray(post, dtype="float32")
    if before.ndim != 3 or before.shape[0] != 2 or after.shape != before.shape:
        raise M1zError("pre and post must share the shape (2, H, W)")
    rows, columns = before.shape[1:]
    tile_cells = tile_m / cell_m
    if abs(tile_cells - round(tile_cells)) > 1e-9:
        raise M1zError("the tile size must be a whole number of cells")
    size = int(round(tile_cells))
    bounds = (grid_west, grid_north - rows * cell_m, grid_west + columns * cell_m, grid_north)
    code = np.full((rows, columns), NO_ANSWER, dtype="uint8")
    for tile in rc.lattice_tiles(bounds, tile_cells=size, cell_m=cell_m):
        first_row = (grid_north - tile.north) / cell_m
        first_column = (tile.west - grid_west) / cell_m
        if any(abs(value - round(value)) > 1e-6 for value in (first_row, first_column)):
            raise M1zError("the grid is not aligned to the lattice")
        r0, c0 = int(round(first_row)), int(round(first_column))
        rs, re_ = max(r0, 0), min(r0 + size, rows)
        cs, ce = max(c0, 0), min(c0 + size, columns)
        if rs >= re_ or cs >= ce:
            continue
        block_pre = np.full((2, size, size), np.nan, dtype="float32")
        block_post = np.full((2, size, size), np.nan, dtype="float32")
        block_pre[:, rs - r0:re_ - r0, cs - c0:ce - c0] = before[:, rs:re_, cs:ce]
        block_post[:, rs - r0:re_ - r0, cs - c0:ce - c0] = after[:, rs:re_, cs:ce]
        candidate = np.asarray(runner(block_pre, block_post)[0], dtype="uint8")
        code[rs:re_, cs:ce] = candidate[rs - r0:re_ - r0, cs - c0:ce - c0]
    return code


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def reference_cells(reference_code: np.ndarray, *, exclude: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """``(water, compared)`` of a reference raster coded 1 water, 0 dry, anything else not compared.

    Cells of ``exclude`` (for instance permanent water) are not compared either.
    """

    codes = np.asarray(reference_code)
    compared = np.isin(codes, (0, 1))
    if exclude is not None:
        excluded = np.asarray(exclude, dtype=bool)
        if excluded.shape != codes.shape:
            raise M1zError("the excluded cells must have the shape of the reference")
        compared &= ~excluded
    return compared & (codes == 1), compared


def confusion(code: np.ndarray, reference_water: np.ndarray, compared: np.ndarray) -> dict[str, int]:
    """Counts on the compared cells: flagged and not flagged against the reference, and the cells without an answer."""

    values = np.asarray(code)
    water, where = np.asarray(reference_water, dtype=bool), np.asarray(compared, dtype=bool)
    if values.shape != water.shape or values.shape != where.shape:
        raise M1zError("the map, the reference and the compared cells must share one shape")
    flagged = where & (values == FLAGGED)
    answered = where & np.isin(values, (FLAGGED, NOT_FLAGGED))
    none = where & ~answered
    return {
        "compared_cells": int(where.sum()), "reference_water_cells": int((where & water).sum()),
        "answered_cells": int(answered.sum()), "no_answer_cells": int(none.sum()),
        "true_positive": int((flagged & water).sum()), "false_positive": int((flagged & ~water).sum()),
        "false_negative_answered": int((answered & ~flagged & water).sum()), "true_negative_answered": int((answered & ~flagged & ~water).sum()),
        "no_answer_reference_water": int((none & water).sum()), "no_answer_reference_dry": int((none & ~water).sum()),
    }


def _ratio(top: float, bottom: float) -> float | None:
    return round(float(top) / float(bottom), 6) if bottom else None


def measures(counts: Mapping[str, int]) -> dict[str, float | None]:
    """IoU with no-answer cells counted as not flagged (the binding figure), IoU on answered cells, the share of
    flagged cells that are reference water (the protocol's precision), the share of reference water flagged (its
    recall; both ways) and the no-answer share. The names follow the R37 records of the repository."""

    tp, fp = counts["true_positive"], counts["false_positive"]
    fn_answered, fn_none = counts["false_negative_answered"], counts["no_answer_reference_water"]
    return {
        "iou_no_answer_as_not_flagged": _ratio(tp, tp + fp + fn_answered + fn_none),
        "iou_answered_cells": _ratio(tp, tp + fp + fn_answered),
        "flagged_that_is_reference_water": _ratio(tp, tp + fp),
        "reference_water_flagged_no_answer_as_not_flagged": _ratio(tp, tp + fn_answered + fn_none),
        "reference_water_flagged_answered_cells": _ratio(tp, tp + fn_answered),
        "no_answer_share": _ratio(counts["no_answer_cells"], counts["compared_cells"]),
    }


def evaluate(code: np.ndarray, reference_water: np.ndarray, compared: np.ndarray) -> dict[str, Any]:
    """:func:`confusion` and :func:`measures` together."""

    counts = confusion(code, reference_water, compared)
    return {**counts, **measures(counts)}


def cover_groups(land_cover: np.ndarray) -> dict[str, np.ndarray]:
    """The masks of the WorldCover groups of the measures: built-up (50), cropland (40), tree cover (10), other."""

    cover = np.asarray(land_cover)
    masks = {name: np.isin(cover, classes) for name, classes in COVER_GROUPS.items()}
    masks["other"] = ~np.isin(cover, [value for classes in COVER_GROUPS.values() for value in classes])
    return masks


def evaluate_by_cover(code: np.ndarray, reference_water: np.ndarray, compared: np.ndarray, land_cover: np.ndarray) -> dict[str, Any]:
    """:func:`evaluate` on the compared cells of each WorldCover group."""

    where = np.asarray(compared, dtype=bool)
    if np.asarray(land_cover).shape != where.shape:
        raise M1zError("land cover must have the shape of the compared cells")
    return {name: evaluate(code, reference_water, where & mask) for name, mask in cover_groups(land_cover).items()}


_TILE_FIELDS: tuple[str, ...] = ("true_positive", "false_positive", "false_negative_answered", "no_answer_reference_water",
                                 "no_answer_cells", "compared_cells")


def tile_counts(code: np.ndarray, reference_water: np.ndarray, compared: np.ndarray, *, tile_cells: int = BOOTSTRAP_TILE_CELLS) -> np.ndarray:
    """Counts per square tile of ``tile_cells`` cells from the north-west corner of the grid.

    Returns ``(tiles, 6)`` in the order of ``_TILE_FIELDS``, for the tiles that hold at least one compared cell.
    """

    values = np.asarray(code)
    water, where = np.asarray(reference_water, dtype=bool), np.asarray(compared, dtype=bool)
    if values.shape != water.shape or values.shape != where.shape or values.ndim != 2:
        raise M1zError("the map, the reference and the compared cells must share one two-dimensional shape")
    if tile_cells < 1:
        raise M1zError("tile_cells must be positive")
    rows, columns = values.shape
    tile_row = (np.arange(rows) // tile_cells)[:, None]
    tile_column = (np.arange(columns) // tile_cells)[None, :]
    tiles_across = (columns + tile_cells - 1) // tile_cells
    index = (tile_row * tiles_across + tile_column)[where]
    flagged = (values == FLAGGED)[where]
    answered = np.isin(values, (FLAGGED, NOT_FLAGGED))[where]
    wet = water[where]
    total = ((rows + tile_cells - 1) // tile_cells) * tiles_across
    columns_of = [flagged & wet, flagged & ~wet, answered & ~flagged & wet, ~answered & wet, ~answered, np.ones(index.shape, dtype=bool)]
    table = np.stack([np.bincount(index, weights=item.astype("float64"), minlength=total) for item in columns_of], axis=1)
    return table[table[:, 5] > 0]


def tile_bootstrap(code: np.ndarray, reference_water: np.ndarray, compared: np.ndarray, *, tile_cells: int = BOOTSTRAP_TILE_CELLS,
                   resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """A 95% interval of the measures from ``resamples`` draws, with replacement, of the tiles that hold compared cells.

    Each draw takes as many tiles as there are and sums their counts. Percentiles 2.5 and 97.5; a draw where a
    figure is undefined (a zero denominator) is left out of that figure's interval.
    """

    table = tile_counts(code, reference_water, compared, tile_cells=tile_cells)
    record: dict[str, Any] = {"resamples": int(resamples), "seed": int(seed), "tile_cells": int(tile_cells),
                              "tile_m": float(tile_cells * CELL_M), "tiles": int(table.shape[0]), "percentiles": [2.5, 97.5]}
    if table.shape[0] == 0 or resamples < 1:
        record["interval"] = None
        return record
    generator = np.random.default_rng(seed)
    draws = generator.integers(0, table.shape[0], size=(resamples, table.shape[0]))
    sums = table[draws].sum(axis=1)
    tp, fp, fn_answered, fn_none, none, compared_cells = (sums[:, column] for column in range(6))
    with np.errstate(invalid="ignore", divide="ignore"):
        figures = {
            "iou_no_answer_as_not_flagged": tp / (tp + fp + fn_answered + fn_none),
            "iou_answered_cells": tp / (tp + fp + fn_answered),
            "flagged_that_is_reference_water": tp / (tp + fp),
            "reference_water_flagged_no_answer_as_not_flagged": tp / (tp + fn_answered + fn_none),
            "no_answer_share": none / compared_cells,
        }
    interval = {}
    for name, values in figures.items():
        finite = values[np.isfinite(values)]
        interval[name] = None if finite.size == 0 else [round(float(np.percentile(finite, 2.5)), 6), round(float(np.percentile(finite, 97.5)), 6)]
        if finite.size < values.size:
            interval[f"{name}_draws_left_out"] = int(values.size - finite.size)
    record["interval"] = interval
    return record


def point_agreement(answers: Sequence[int], labels: Sequence[str | None]) -> dict[str, Any]:
    """The share of labelled points our map agrees with.

    ``answers`` are the map codes at the points; ``labels`` are ``"water"``, ``"not_water"`` or ``None`` (no label
    to score with). The binding share counts a point without an answer as not flagged; the second share is on
    answered points only.
    """

    if len(answers) != len(labels):
        raise M1zError("one answer per labelled point")
    scored = [(int(code), label) for code, label in zip(answers, labels) if label in (WATER_LABEL, NOT_WATER_LABEL)]
    agree = sum(1 for code, label in scored if (code == FLAGGED) == (label == WATER_LABEL))
    answered = [(code, label) for code, label in scored if code in (FLAGGED, NOT_FLAGGED)]
    agree_answered = sum(1 for code, label in answered if (code == FLAGGED) == (label == WATER_LABEL))
    table = {f"{label}_{name}": sum(1 for code, given in scored if given == label and code == value)
             for label in (WATER_LABEL, NOT_WATER_LABEL) for name, value in (("flagged", FLAGGED), ("not_flagged", NOT_FLAGGED), ("no_answer", NO_ANSWER))}
    return {"points": len(labels), "points_with_a_label": len(scored), "points_answered": len(answered),
            "share_agreed_no_answer_as_not_flagged": _ratio(agree, len(scored)),
            "share_agreed_answered_points": _ratio(agree_answered, len(answered)), "table": table}


# ---------------------------------------------------------------------------
# Fine references on the 20 m grid
# ---------------------------------------------------------------------------


def centre_window(grid: Sequence[float], rectangle: Mapping[str, float], *, cell_m: float = CELL_M) -> tuple[slice, slice]:
    """Rows and columns of the cells of ``grid`` (west, north, rows, columns) whose centre lies inside ``rectangle``.

    ``rectangle`` holds west, south, east and north; an edge that runs through a centre counts as inside.
    """

    west, north, rows, columns = float(grid[0]), float(grid[1]), int(grid[2]), int(grid[3])
    first_column = max(0, math.ceil((float(rectangle["west"]) - west) / cell_m - 0.5))
    last_column = min(columns - 1, math.floor((float(rectangle["east"]) - west) / cell_m - 0.5))
    first_row = max(0, math.ceil((north - float(rectangle["north"])) / cell_m - 0.5))
    last_row = min(rows - 1, math.floor((north - float(rectangle["south"])) / cell_m - 0.5))
    if last_column < first_column or last_row < first_row:
        raise M1zError("no cell centre of the grid lies inside the rectangle")
    return slice(first_row, last_row + 1), slice(first_column, last_column + 1)


def fine_counts_on_grid(fine: np.ndarray, *, fine_west: float, fine_north: float, fine_m: float, grid_west: float, grid_north: float,
                        rows: int, columns: int, cell_m: float = CELL_M, water_value: int = 1,
                        nodata_value: int = 255) -> tuple[np.ndarray, np.ndarray, int]:
    """Per cell of a grid window: how many fine pixels are water, how many hold a value, and how many it has.

    The fine raster must be aligned to the grid: whole fine pixels per cell, and corners a whole number of fine
    pixels apart. Pixels outside the fine raster hold no value. Values other than ``water_value`` and
    ``nodata_value`` are not water.
    """

    data = np.asarray(fine)
    if data.ndim != 2:
        raise M1zError("the fine raster must be two-dimensional")
    factor = cell_m / fine_m
    offset_column = (fine_west - grid_west) / fine_m
    offset_row = (grid_north - fine_north) / fine_m
    if any(abs(value - round(value)) > 1e-6 for value in (factor, offset_column, offset_row)) or factor < 1:
        raise M1zError("the fine raster is not aligned to the grid")
    factor, offset_column, offset_row = int(round(factor)), int(round(offset_column)), int(round(offset_row))
    canvas = np.full((rows * factor, columns * factor), nodata_value, dtype=data.dtype)
    top, left = max(0, offset_row), max(0, offset_column)
    bottom, right = min(rows * factor, offset_row + data.shape[0]), min(columns * factor, offset_column + data.shape[1])
    if bottom > top and right > left:
        canvas[top:bottom, left:right] = data[top - offset_row:bottom - offset_row, left - offset_column:right - offset_column]
    blocks = canvas.reshape(rows, factor, columns, factor)
    water = (blocks == water_value).sum(axis=(1, 3))
    valid = (blocks != nodata_value).sum(axis=(1, 3))
    return water.astype("int32"), valid.astype("int32"), factor * factor


def half_rule(water: np.ndarray, valid: np.ndarray, pixels_per_cell: int, *, basis: str = "all") -> np.ndarray:
    """The 20 m half rule of the protocol: 255 (not compared) when fewer than half of a cell's fine pixels hold a value;
    otherwise 1 (water) when at least half of its fine pixels are water, else 0.

    ``basis`` ``"all"`` reads "half of its fine pixels" as half of all of them (the protocol's words);
    ``"valid"`` as half of those that hold a value.
    """

    wet, seen = np.asarray(water), np.asarray(valid)
    if wet.shape != seen.shape:
        raise M1zError("the two count rasters must share one shape")
    if basis not in ("all", "valid"):
        raise M1zError("basis is 'all' or 'valid'")
    code = np.full(wet.shape, NO_ANSWER, dtype="uint8")
    compared = 2 * seen >= pixels_per_cell
    base = np.full(wet.shape, pixels_per_cell) if basis == "all" else seen
    code[compared] = 0
    code[compared & (2 * wet >= base)] = 1
    return code


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def mean_score(per_set: Mapping[str, Mapping[str, Any]], key: str = "iou_no_answer_as_not_flagged") -> float | None:
    """The mean over the sets of ``key``; ``None`` when a set has no value."""

    values = [entry.get(key) for entry in per_set.values()]
    if not values or any(value is None for value in values):
        return None
    return round(float(np.mean([float(value) for value in values])), 6)


def tie_key(parameters: Mapping[str, Any]) -> tuple[float, float, float, float]:
    """The tie rule's order: most negative z limit, then most negative VH limit, then smallest HAND limit, then
    smallest dry spread limit (no limit counts as the largest)."""

    spread = parameters.get("dry_spread_max_db")
    return (float(parameters["z_vh_max"]), float(parameters["vh_after_max_db"]), float(parameters["hand_max_m"]),
            math.inf if spread is None else float(spread))


def no_answer_limits_from_floor(candidates: Sequence[Mapping[str, Any]], margin: float) -> dict[str, float]:
    """Amendment 1 of the protocol: per set, the lowest no-answer share any candidate reaches there, plus ``margin``."""

    floors: dict[str, float] = {}
    for candidate in candidates:
        for set_id, entry in candidate["sets"].items():
            share = entry.get("no_answer_share")
            if share is not None:
                floors[set_id] = min(floors.get(set_id, math.inf), float(share))
    return {set_id: round(floor + margin, 6) for set_id, floor in floors.items()}


def select_parameters(candidates: Sequence[Mapping[str, Any]], *, max_no_answer_share: float = MAX_NO_ANSWER_SHARE,
                      tie_margin: float = TIE_MARGIN, max_no_answer_by_set: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Apply the protocol's selection rule, constraint and tie rule.

    Each candidate holds ``parameters`` and ``sets`` (per set ``iou_no_answer_as_not_flagged`` and
    ``no_answer_share``). Eligible: a score on every set and a no-answer share of at most ``max_no_answer_share`` in
    every set, or, when ``max_no_answer_by_set`` is given (amendment 1), at most that set's own limit. Score: the
    mean IoU over the sets. Every eligible candidate within ``tie_margin`` of the best score is tied, and
    :func:`tie_key` picks one. With no eligible candidate nothing is selected; the protocol gives no rule for that case.
    """

    def limit_of(set_id: str) -> float:
        if max_no_answer_by_set is not None:
            return float(max_no_answer_by_set[set_id])
        return max_no_answer_share

    rows = []
    for candidate in candidates:
        sets = candidate["sets"]
        score = mean_score(sets)
        within = bool(sets) and all(entry.get("no_answer_share") is not None and float(entry["no_answer_share"]) <= limit_of(set_id) + 1e-12
                                    for set_id, entry in sets.items())
        rows.append({"parameters": dict(candidate["parameters"]), "score": score, "meets_the_constraint": within})
    eligible = [row for row in rows if row["meets_the_constraint"] and row["score"] is not None]
    result: dict[str, Any] = {"candidates": len(rows), "eligible": len(eligible), "max_no_answer_share": max_no_answer_share,
                              "tie_margin": tie_margin}
    if max_no_answer_by_set is not None:
        result["max_no_answer_share"] = None
        result["max_no_answer_share_by_set"] = dict(max_no_answer_by_set)
    if not eligible:
        best_any = max((row for row in rows if row["score"] is not None), key=lambda row: row["score"], default=None)
        result.update(best_score=None, tied=[], selected=None,
                      why="no candidate holds a no-answer share of at most the limit in every set; the protocol gives no rule for this case",
                      best_score_without_the_constraint=None if best_any is None else best_any["score"],
                      best_without_the_constraint=None if best_any is None else best_any["parameters"])
        return result
    best = max(row["score"] for row in eligible)
    tied = sorted((row for row in eligible if row["score"] >= best - tie_margin - 1e-12), key=lambda row: tie_key(row["parameters"]))
    result.update(best_score=best, tied=[{**row["parameters"], "score": row["score"]} for row in tied], selected=tied[0]["parameters"],
                  selected_score=tied[0]["score"],
                  why=f"{len(tied)} eligible candidate(s) within {tie_margin} of the best mean IoU {best}; the tie rule took the first")
    return result
