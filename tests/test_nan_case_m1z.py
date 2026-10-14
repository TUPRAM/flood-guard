"""M1-z of the Nan case and its staged script, on invented data only.

The pure functions of ``floodguard.m1z`` are checked on small arrays. The four stages of
``scripts/nan_case_method.py`` (tune, freeze, test, maps) are then run on invented areas in a throwaway git
repository with a throwaway remote, including every refusal of the order of the protocol. No real reference and
no real radar pass is read.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from floodguard import m1z

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nan_case_method.py"


# ---------------------------------------------------------------------------
# The method
# ---------------------------------------------------------------------------


def flat(shape: tuple[int, int] = (6, 6), **changes: object) -> dict[str, np.ndarray]:
    """A plain dry scene: VH -12 dB after and before, spread 1 dB, 8 dry passes, low flat cropland."""

    layers = {
        "after": np.full(shape, -12.0, dtype="float32"), "mean": np.full(shape, -12.0, dtype="float32"),
        "std": np.full(shape, 1.0, dtype="float32"), "passes": np.full(shape, 8.0, dtype="float32"),
        "hand": np.full(shape, 1.0, dtype="float32"), "slope": np.zeros(shape, dtype="float32"), "cover": np.full(shape, 40, dtype="uint8"),
    }
    layers.update(changes)  # type: ignore[arg-type]
    return layers


def run(layers: dict[str, np.ndarray], parameters: m1z.M1zParameters) -> tuple[np.ndarray, np.ndarray]:
    return m1z.classify(layers["after"], layers["mean"], layers["std"], layers["passes"], layers["hand"], layers["slope"],
                        layers["cover"], parameters)


PARAMETERS = m1z.M1zParameters(z_vh_max=-2.0, vh_after_max_db=-18.0, hand_max_m=10.0, dry_spread_max_db=3.0)


def test_z_score_and_the_double_rule_flag_only_cells_that_are_anomalous_and_dark() -> None:
    layers = flat()
    layers["after"][1:3, 1:3] = -22.0          # anomalous (z = -10) and dark: flagged
    layers["after"][4, 0:2] = -13.0            # z = -1: not anomalous enough
    layers["mean"][4, 3:5] = -17.0
    layers["after"][4, 3:5] = -19.5            # dark and z = -2.5: flagged
    layers["mean"][0, 4:6] = -30.0
    layers["after"][0, 4:6] = -25.0            # dark but brighter than its own dry mean: not flagged
    z = m1z.z_score(layers["after"], layers["mean"], layers["std"])
    assert z[1, 1] == pytest.approx(-10.0) and z[4, 0] == pytest.approx(-1.0)
    code, reason = run(layers, PARAMETERS)
    expected = np.zeros((6, 6), dtype="uint8")
    expected[1:3, 1:3] = 1
    expected[4, 3:5] = 1
    assert np.array_equal(code, expected)
    assert set(np.unique(reason[code == 1])) == {m1z.REASON_FLAGGED}
    assert set(np.unique(reason[code == 0])) == {m1z.REASON_RADAR_DRY}
    # At the limits exactly: z = -2 and VH = -18 are flagged ("at or below").
    edge = flat((3, 3))
    edge["mean"][:] = -16.0
    edge["after"][:] = -18.0
    assert (run(edge, PARAMETERS)[0] == 1).all()


def test_permanent_water_is_never_flagged_and_says_so() -> None:
    layers = flat()
    layers["after"][:] = -25.0
    layers["cover"][0:2, :] = m1z.PERMANENT_WATER_CLASS
    code, reason = run(layers, PARAMETERS)
    assert (code[0:2] == 0).all() and (reason[0:2] == m1z.REASON_PERMANENT_WATER).all()
    assert (code[2:] == 1).all()


def test_terrain_answers_not_flooded_before_any_no_answer_reason() -> None:
    layers = flat()
    layers["after"][:] = -25.0
    layers["hand"][0, :] = 10.5                 # above the limit of 10 m
    layers["after"][0, 0] = np.nan              # even without radar: terrain answers
    layers["slope"][1, :] = 5.0                 # 5 degrees or more
    layers["passes"][1, 0] = 2                  # even with too few dry passes: terrain answers
    layers["cover"][0, 1] = m1z.BUILT_UP_CLASS  # built-up on high ground: terrain, not no answer
    code, reason = run(layers, PARAMETERS)
    assert (code[0:2] == 0).all()
    assert (reason[0] == m1z.REASON_TERRAIN_HAND).all() and (reason[1] == m1z.REASON_TERRAIN_SLOPE).all()
    assert (code[2:] == 1).all()
    # HAND exactly at the limit is low ground.
    layers["hand"][0, :] = 10.0
    assert run(layers, PARAMETERS)[0][0, 2] == 1


def test_each_no_answer_reason() -> None:
    layers = flat()
    layers["after"][:] = -25.0
    layers["after"][0, 0] = np.nan
    layers["passes"][0, 1] = 5
    layers["std"][0, 2] = 3.5
    layers["cover"][0, 3] = m1z.BUILT_UP_CLASS
    layers["cover"][0, 4] = m1z.TREE_COVER_CLASS
    layers["hand"][0, 5] = np.nan
    layers["mean"][1, 0] = np.nan
    code, reason = run(layers, PARAMETERS)
    assert (code[0] == m1z.NO_ANSWER).all() and code[1, 0] == m1z.NO_ANSWER
    assert list(reason[0]) == [m1z.REASON_NO_RADAR_AFTER, m1z.REASON_FEW_DRY_PASSES, m1z.REASON_DRY_SPREAD, m1z.REASON_BUILT_UP_LOW,
                               m1z.REASON_TREE_COVER_LOW, m1z.REASON_NO_TERRAIN]
    assert reason[1, 0] == m1z.REASON_FEW_DRY_PASSES
    # Six valid dry passes are enough; a spread exactly at the limit is not above it.
    layers["passes"][0, 1] = 6
    layers["std"][0, 2] = 3.0
    code, _reason = run(layers, PARAMETERS)
    assert code[0, 1] == 1 and code[0, 2] == 1


def test_no_limit_on_the_dry_spread_when_the_limit_is_null() -> None:
    layers = flat()
    layers["after"][:] = -25.0
    layers["std"][:] = 9.0
    assert (run(layers, PARAMETERS)[0] == m1z.NO_ANSWER).all()
    open_ended = m1z.M1zParameters(-1.0, -18.0, 10.0, None)
    assert (run(layers, open_ended)[0] == 1).all()


def test_flagged_groups_of_fewer_than_two_cells_are_dropped_eight_connected() -> None:
    layers = flat((7, 7))
    layers["after"][1, 1] = -25.0                     # alone: dropped
    layers["after"][4, 4] = layers["after"][5, 5] = -25.0  # touching at a corner: one group of 2, kept
    layers["after"][2, 5] = -25.0
    layers["cover"][2, 6] = m1z.BUILT_UP_CLASS        # its only neighbour gets no answer: still alone, dropped
    layers["after"][2, 6] = -25.0
    code, reason = run(layers, PARAMETERS)
    assert code[1, 1] == 0 and reason[1, 1] == m1z.REASON_SMALL_GROUP
    assert code[4, 4] == 1 and code[5, 5] == 1
    assert code[2, 5] == 0 and reason[2, 5] == m1z.REASON_SMALL_GROUP and code[2, 6] == m1z.NO_ANSWER
    assert m1z.keep_groups(np.eye(3, dtype=bool), 3).sum() == 3 and m1z.keep_groups(np.eye(3, dtype=bool), 4).sum() == 0


def test_the_three_flood_levels_move_the_z_limit_by_half_a_unit_and_are_nested() -> None:
    levels = m1z.flood_levels(PARAMETERS)
    assert levels["lower"].z_vh_max == -2.5 and levels["upper"].z_vh_max == -1.5
    assert levels["lower"].vh_after_max_db == PARAMETERS.vh_after_max_db == levels["upper"].vh_after_max_db
    layers = flat((5, 5))
    layers["after"][:] = np.array([-13.5, -14.0, -14.5, -15.0, -16.0], dtype="float32")[:, None]
    layers["mean"][:] = -12.0
    loose = m1z.M1zParameters(-2.0, -13.0, 10.0, None)
    maps = m1z.classify_levels(layers["after"], layers["mean"], layers["std"], layers["passes"], layers["hand"], layers["slope"],
                               layers["cover"], loose)
    lower, central, upper = ((maps[name][0] == 1) for name in ("lower", "central", "upper"))
    assert lower.sum() < central.sum() < upper.sum()
    assert not (lower & ~central).any() and not (central & ~upper).any()


def test_parameters_round_trip_and_the_protocol_grid() -> None:
    protocol = json.loads((ROOT / "docs/proposal_execution/nan_case_protocol_v1.json").read_text(encoding="utf-8"))
    values = protocol["method"]["tuned_parameters"]
    assert {key: tuple(float(v) if v is not None else None for v in items) for key, items in values.items()} == m1z.TUNED_PARAMETERS
    grid = m1z.candidate_grid(values)
    assert len(grid) == 360 and grid[0] == m1z.M1zParameters(-1.0, -15.0, 5.0, 2.0) and grid[-1] == m1z.M1zParameters(-3.0, -20.0, 20.0, None)
    assert m1z.M1zParameters.from_json(grid[5].as_json()) == grid[5]
    assert m1z.MIN_DRY_PASSES == protocol["radar"]["dry_season"]["min_valid_passes_per_cell"]


# ---------------------------------------------------------------------------
# The counting
# ---------------------------------------------------------------------------


def test_evaluation_counts_no_answer_as_not_flagged_in_the_binding_figure() -> None:
    code = np.array([[1, 1, 0, 255], [0, 255, 1, 0]], dtype="uint8")
    water = np.array([[1, 0, 1, 1], [0, 0, 1, 0]], dtype=bool)
    compared = np.ones(code.shape, dtype=bool)
    compared[1, 3] = False
    figures = m1z.evaluate(code, water, compared)
    assert figures["true_positive"] == 2 and figures["false_positive"] == 1 and figures["false_negative_answered"] == 1
    assert figures["no_answer_reference_water"] == 1 and figures["no_answer_reference_dry"] == 1 and figures["compared_cells"] == 7
    assert figures["iou_no_answer_as_not_flagged"] == pytest.approx(2 / 5)
    assert figures["iou_answered_cells"] == pytest.approx(2 / 4)
    assert figures["flagged_that_is_reference_water"] == pytest.approx(2 / 3)
    assert figures["reference_water_flagged_no_answer_as_not_flagged"] == pytest.approx(2 / 4)
    assert figures["reference_water_flagged_answered_cells"] == pytest.approx(2 / 3)
    assert figures["no_answer_share"] == pytest.approx(2 / 7)
    empty = m1z.evaluate(np.zeros((2, 2), dtype="uint8"), np.zeros((2, 2), dtype=bool), np.zeros((2, 2), dtype=bool))
    assert empty["iou_no_answer_as_not_flagged"] is None and empty["no_answer_share"] is None


def test_reference_cells_and_the_worldcover_groups() -> None:
    reference = np.array([[1, 0, 255], [1, 7, 0]], dtype="uint8")
    water, compared = m1z.reference_cells(reference, exclude=np.array([[False, False, False], [True, False, False]]))
    assert compared.tolist() == [[True, True, False], [False, False, True]] and water.tolist() == [[True, False, False], [False, False, False]]
    cover = np.array([[50, 40, 10], [80, 30, 0]], dtype="uint8")
    groups = m1z.evaluate_by_cover(np.ones((2, 3), dtype="uint8"), np.ones((2, 3), dtype=bool), np.ones((2, 3), dtype=bool), cover)
    assert {name: entry["compared_cells"] for name, entry in groups.items()} == {"built_up": 1, "cropland": 1, "tree_cover": 1, "other": 3}


def test_the_tile_bootstrap_is_reproducible_and_brackets_the_figure() -> None:
    generator = np.random.default_rng(1)
    water = generator.random((60, 60)) < 0.3
    code = np.where(generator.random((60, 60)) < 0.8, water, ~water).astype("uint8")
    code[:5, :5] = 255
    compared = np.ones(code.shape, dtype=bool)
    first = m1z.tile_bootstrap(code, water, compared, tile_cells=10, resamples=200, seed=7)
    again = m1z.tile_bootstrap(code, water, compared, tile_cells=10, resamples=200, seed=7)
    assert first == again and first["tiles"] == 36 and first["seed"] == 7
    low, high = first["interval"]["iou_no_answer_as_not_flagged"]
    assert low <= m1z.evaluate(code, water, compared)["iou_no_answer_as_not_flagged"] <= high
    defaults = m1z.tile_bootstrap(code, water, compared)
    assert defaults["resamples"] == 1000 and defaults["tile_cells"] == 100 and defaults["seed"] == m1z.BOOTSTRAP_SEED and defaults["tiles"] == 1
    assert m1z.tile_counts(code, water, np.zeros(code.shape, dtype=bool)).shape == (0, 6)


def test_the_share_of_labelled_points_agreed_with() -> None:
    figures = m1z.point_agreement([1, 0, 255, 1, 0], ["water", "water", "water", "not_water", None])
    assert figures["points_with_a_label"] == 4 and figures["points_answered"] == 3
    assert figures["share_agreed_no_answer_as_not_flagged"] == pytest.approx(1 / 4)
    assert figures["share_agreed_answered_points"] == pytest.approx(1 / 3)
    assert figures["table"]["water_no_answer"] == 1


def test_the_20_m_half_rule_on_a_fine_raster() -> None:
    fine = np.zeros((20, 20), dtype="uint8")
    fine[:10, :10] = 1          # the north-west cell: all water
    fine[:10, 10:15] = 1        # the north-east cell: half water
    fine[10:, :10] = 255
    fine[10:12, :10] = 0        # the south-west cell: 20 of 100 hold a value
    water, valid, pixels = m1z.fine_counts_on_grid(fine, fine_west=1000.0, fine_north=2000.0, fine_m=2.0, grid_west=1000.0, grid_north=2000.0,
                                                   rows=2, columns=2)
    assert pixels == 100 and water.tolist() == [[100, 50], [0, 0]] and valid.tolist() == [[100, 100], [20, 100]]
    assert m1z.half_rule(water, valid, pixels).tolist() == [[1, 1], [255, 0]]
    # Offset by one cell: pixels outside the fine raster hold no value.
    water, valid, _ = m1z.fine_counts_on_grid(fine, fine_west=1020.0, fine_north=2000.0, fine_m=2.0, grid_west=1000.0, grid_north=2000.0,
                                              rows=1, columns=3)
    assert valid.tolist() == [[0, 100, 100]] and m1z.half_rule(water, valid, 100).tolist() == [[255, 1, 1]]
    # "Half of its pixels" read as half of all of them (default) or of those that hold a value.
    assert m1z.half_rule(np.array([[40]]), np.array([[60]]), 100).tolist() == [[0]]
    assert m1z.half_rule(np.array([[40]]), np.array([[60]]), 100, basis="valid").tolist() == [[1]]
    with pytest.raises(m1z.M1zError):
        m1z.fine_counts_on_grid(fine, fine_west=1001.0, fine_north=2000.0, fine_m=2.0, grid_west=1000.0, grid_north=2000.0, rows=1, columns=1)


def test_cells_whose_centre_lies_inside_a_rectangle() -> None:
    rows, columns = m1z.centre_window((0.0, 1000.0, 50, 50), {"west": 25.0, "east": 105.0, "north": 975.0, "south": 900.0})
    assert (rows.start, rows.stop, columns.start, columns.stop) == (1, 5, 1, 5)
    with pytest.raises(m1z.M1zError):
        m1z.centre_window((0.0, 1000.0, 5, 5), {"west": 500.0, "east": 600.0, "north": 975.0, "south": 900.0})


# ---------------------------------------------------------------------------
# The selection rule
# ---------------------------------------------------------------------------


def candidate(z: float, vh: float, hand: float, spread: float | None, ious: tuple[float, ...], shares: tuple[float, ...]) -> dict:
    return {"parameters": m1z.M1zParameters(z, vh, hand, spread).as_json(),
            "sets": {f"set_{index}": {"iou_no_answer_as_not_flagged": iou, "no_answer_share": share}
                     for index, (iou, share) in enumerate(zip(ious, shares))}}


def test_selection_applies_the_constraint_then_the_tie_rule() -> None:
    candidates = [
        candidate(-1.0, -15.0, 5, 2.0, (0.70, 0.70), (0.10, 0.25)),   # best score but breaks the constraint in one set
        candidate(-1.0, -18.0, 10, None, (0.55, 0.55), (0.10, 0.10)),  # best eligible: 0.55
        candidate(-2.0, -17.0, 20, None, (0.545, 0.545), (0.10, 0.20)),  # within 0.01, more negative z: wins the tie
        candidate(-2.0, -17.0, 20, 3.0, (0.54, 0.545), (0.10, 0.10)),  # same z, vh and hand; a limit beats no limit
        candidate(-3.0, -20.0, 5, 2.0, (0.50, 0.50), (0.0, 0.0)),      # more negative still, but 0.05 below the best
    ]
    chosen = m1z.select_parameters(candidates)
    assert chosen["eligible"] == 4 and chosen["best_score"] == pytest.approx(0.55)
    assert chosen["selected"] == m1z.M1zParameters(-2.0, -17.0, 20.0, 3.0).as_json()
    assert [entry["z_vh_max"] for entry in chosen["tied"]] == [-2.0, -2.0, -1.0]
    assert m1z.tie_key({"z_vh_max": -1, "vh_after_max_db": -15, "hand_max_m": 5, "dry_spread_max_db": None})[3] == float("inf")


def test_selection_with_no_eligible_candidate_selects_nothing() -> None:
    chosen = m1z.select_parameters([candidate(-1.0, -15.0, 5, 2.0, (0.7,), (0.3,))])
    assert chosen["selected"] is None and chosen["eligible"] == 0 and chosen["best_score_without_the_constraint"] == pytest.approx(0.7)
    assert m1z.mean_score({"a": {"iou_no_answer_as_not_flagged": None}}) is None


# ---------------------------------------------------------------------------
# The comparators
# ---------------------------------------------------------------------------


def linear(decibel: np.ndarray) -> np.ndarray:
    return np.power(10.0, np.asarray(decibel, dtype="float64") / 10.0)


def test_the_frozen_r37_detector_at_20_m_cleans_grows_and_drops() -> None:
    vh = np.full((20, 20), -14.0)
    vh[4:10, 4:10] = -24.0       # a pond: flagged, then grown into its edge
    vh[15, 15] = -40.0           # one dark cell: its 3 by 3 mean is above the threshold, nothing flagged
    vh[14:17, 2:5] = -24.0       # dark, but on a slope of 6 degrees: dropped
    slope = np.zeros(vh.shape)
    slope[13:18, 1:6] = 6.0
    water = np.zeros(vh.shape, dtype=bool)
    water[0, :] = True
    frozen = m1z.frozen_detector_r37(linear(vh), slope, water)
    simple = m1z.simple_threshold_r37(linear(vh), slope, water)
    assert (frozen[0] == m1z.NO_ANSWER).all() and (simple[0] == m1z.NO_ANSWER).all()
    assert frozen[5:9, 5:9].all() and frozen[15, 15] == 0 and (frozen[14:17, 2:5] == 0).all()
    assert (simple[14:17, 2:5] == 1).any()
    assert (frozen == 1).sum() >= (simple[4:10, 4:10] == 1).sum()
    assert m1z.r37_vh_after_db(linear(vh), window=1)[5, 5] == pytest.approx(-24.0, abs=1e-4)


def test_un_spider_with_the_dry_mean_as_the_image_before() -> None:
    dry = np.full((20, 20), -15.0)
    after = np.full((20, 20), -15.0)
    after[5:12, 5:12] = -21.0    # -21 / -15 = 1.4 > 1.25
    code = m1z.un_spider_dry_mean(linear(after), dry, np.zeros((20, 20)), np.zeros((20, 20), dtype=bool))
    assert code[7:10, 7:10].all() and code[15:, 15:].sum() == 0


def test_a_per_tile_rule_runs_tile_by_tile_on_the_lattice() -> None:
    seen = []

    def runner(pre: np.ndarray, post: np.ndarray) -> tuple[np.ndarray]:
        seen.append(int(np.isfinite(post[1]).sum()))
        flags = np.where(np.isfinite(post[1]), (post[1] < pre[1]).astype("uint8"), 255).astype("uint8")
        return (flags,)

    rows, columns = 8, 10
    pre = np.ones((2, rows, columns), dtype="float32")
    post = np.ones((2, rows, columns), dtype="float32")
    post[1, :, 6:] = 0.5
    # A lattice of 100 m tiles (5 cells): the grid starts 60 m into a tile, so it spans 3 by 3 tiles.
    code = m1z.on_lattice(pre, post, runner, grid_west=1060.0, grid_north=2040.0, tile_m=100.0)
    assert len(seen) == 9 and sum(seen) == rows * columns
    assert (code[:, 6:] == 1).all() and (code[:, :6] == 0).all()


# ---------------------------------------------------------------------------
# The stages, on invented areas
# ---------------------------------------------------------------------------

def geo() -> tuple:
    """rasterio and geopandas, or a skip where they are not installed."""

    return pytest.importorskip("rasterio"), pytest.importorskip("geopandas")

TUNING_GRID = {"z_vh_max": [-1.0, -2.0], "vh_after_max_db": [-15.0, -18.0], "hand_max_m": [5, 10], "dry_spread_max_db": [2.0, None]}
SIZE = 40
FRAME = {"west": 600000, "north": 2000000, "rows": 120, "cols": 120}
TOWN = {"west": 601402.0, "south": 1998402.0, "east": 601802.0, "north": 1998802.0}
DRY_HILLS = {"west": 600202.0, "south": 1997802.0, "east": 600602.0, "north": 1998202.0}


def load_script():
    spec = importlib.util.spec_from_file_location("nan_case_method_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def write_tif(path: Path, grid: dict, bands: list[np.ndarray], *, names: list[str] | None = None, nodata: float | None = None) -> None:
    rasterio, _gpd = geo()
    from rasterio.transform import from_origin

    path.parent.mkdir(parents=True, exist_ok=True)
    dtype = bands[0].dtype
    with rasterio.open(path, "w", driver="GTiff", height=grid["rows"], width=grid["cols"], count=len(bands), dtype=dtype, nodata=nodata,
                       crs="EPSG:32647", transform=from_origin(grid["west"], grid["north"], 20.0, 20.0)) as target:
        for index, band in enumerate(bands, start=1):
            target.write(band, index)
            if names:
                target.set_band_description(index, names[index - 1])


def scene(rows: int, cols: int, flood: tuple[slice, slice], *, seed: int, hills: tuple[slice, slice] | None = None,
          built: tuple[slice, slice] | None = None, river: tuple[slice, slice] | None = None) -> dict[str, np.ndarray]:
    """An invented area: flat cropland at -15 dB with 0.4 dB of noise, a flood at -22 dB, hills, a built-up block and a river."""

    generator = np.random.default_rng(seed)
    after = (-15.0 + generator.normal(0, 0.4, (rows, cols))).astype("float32")
    after[flood] = -22.0
    hand = np.full((rows, cols), 1.0, dtype="float32")
    slope = np.zeros((rows, cols), dtype="float32")
    cover = np.full((rows, cols), 40, dtype="uint8")
    if hills is not None:
        hand[hills], slope[hills], cover[hills] = 40.0, 9.0, 10
    if built is not None:
        cover[built] = 50
    if river is not None:
        cover[river] = 80
        after[river] = -24.0
    water = np.zeros((rows, cols), dtype="uint8")
    water[flood] = 1
    return {"after": after, "hand": hand, "slope": slope, "cover": cover, "water": water}


def write_area(external: Path, area: str, grid: dict, layers: dict[str, np.ndarray], passes: list[tuple[str, int, str]], *, reference: bool) -> None:
    rows, cols = grid["rows"], grid["cols"]
    radar = external / "proposal_execution/nan_case_v1/radar" / area
    for stamp, orbit, platform in passes:
        vh = np.power(10.0, layers["after"] / 10.0).astype("float32")
        vv = (vh * 4).astype("float32")
        write_tif(radar / f"event_{stamp}_o{orbit}.tif", grid, [vv, vh], names=["VV", "VH"], nodata=float("nan"))
        (radar / f"event_{stamp}_o{orbit}.json").write_text(json.dumps({"datetime": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:00Z",
                                                                         "relative_orbit": orbit, "platform": platform}), encoding="utf-8")
        mean = np.full((rows, cols), -15.0, dtype="float32")
        write_tif(radar / f"dry_o{orbit}.tif", grid, [mean, np.full((rows, cols), 1.0, dtype="float32"), mean + 6, np.full((rows, cols), 1.0, dtype="float32"),
                                                     np.full((rows, cols), 8.0, dtype="float32")],
                  names=["vh_mean_db", "vh_std_db", "vv_mean_db", "vv_std_db", "n_valid"], nodata=float("nan"))
    terrain = external / "proposal_execution/nan_case_v1/terrain" / area
    write_tif(terrain / "hand_m.tif", grid, [layers["hand"]], nodata=-9999.0)
    write_tif(terrain / "slope_deg.tif", grid, [layers["slope"]], nodata=-9999.0)
    write_tif(terrain / "worldcover.tif", grid, [layers["cover"]], nodata=0)
    write_tif(terrain / "permanent_water.tif", grid, [(layers["cover"] == 80).astype("uint8")])
    if reference:
        code = layers["water"].copy()
        code[:2, :] = 255
        write_tif(external / "proposal_execution/nan_case_v1/references_tuning" / area / "reference_20m.tif", grid, [code], nodata=255)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame_box(rows: slice, cols: slice) -> object:
    from shapely.geometry import box

    west, north = FRAME["west"], FRAME["north"]
    return box(west + cols.start * 20, north - rows.stop * 20, west + cols.stop * 20, north - rows.start * 20)


def jaxa_zip(path: Path, layers: dict[str, list]) -> None:
    """A zip of GeoJSON layers in EPSG:4326, as a JAXA product might hold them."""

    _rasterio, gpd = geo()
    import pyogrio

    work = path.parent / f"_{path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, geometries in layers.items():
            frame = gpd.GeoDataFrame({"name": [name] * len(geometries)}, geometry=geometries, crs="EPSG:32647").to_crs(4326)
            target = work / f"{name}.geojson"
            pyogrio.write_dataframe(frame, target, driver="GeoJSON")
            archive.write(target, f"{name}.geojson")
    shutil.rmtree(work)


@pytest.fixture()
def case(tmp_path: Path) -> dict:
    """A throwaway repository with an invented protocol and an invented external root."""

    rasterio, gpd = geo()
    pytest.importorskip("pyogrio")
    from rasterio.transform import from_origin

    if shutil.which("git") is None:  # pragma: no cover - git is part of the development setup
        pytest.skip("git is needed for the order checks")
    repo, external, remote = tmp_path / "repo", tmp_path / "external", tmp_path / "remote.git"
    for relative in ("src/floodguard/m1z.py", "scripts/nan_case_method.py"):
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, repo / relative)
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.tif binary\n", encoding="utf-8")

    # --- tuning areas: two used, one dropped by the references lane ---------------------------------------------
    tuning_grids = {"sukhothai_chip": {"west": 500000, "north": 1800000, "rows": SIZE, "cols": SIZE},
                    "mae_sai_20241022": {"west": 520000, "north": 1800000, "rows": SIZE, "cols": SIZE}}
    area_events = {"sukhothai_chip": ("20250731T2308", 62, "sentinel-1a"), "mae_sai_20241022": ("20241021T2316", 135, "sentinel-1a")}
    for index, (area, grid) in enumerate(tuning_grids.items()):
        layers = scene(SIZE, SIZE, (slice(10, 20), slice(8, 30)), seed=index, hills=(slice(30, 38), slice(0, 12)),
                       built=(slice(24, 26), slice(30, 34)), river=(slice(2, 40), slice(36, 38)))
        write_area(external, area, grid, layers, [area_events[area]], reference=True)

    # --- the Nan frame -------------------------------------------------------------------------------------------
    flood = (slice(62, 76), slice(72, 88))     # inside the town chip (rows 60-79, columns 70-89)
    nan = scene(FRAME["rows"], FRAME["cols"], flood, seed=9, hills=(slice(90, 112), slice(5, 35)), built=(slice(64, 68), slice(90, 94)),
                river=(slice(0, 120), slice(110, 112)))
    write_area(external, "nan_frame", FRAME, nan, [("20250728T1121", 128, "sentinel-1c"), ("20250731T2308", 62, "sentinel-1a")], reference=False)

    units = gpd.GeoDataFrame({"adm3_pcode": ["TH550101", "TH550102"], "adm2_pcode": ["TH5501", "TH5599"]},
                             geometry=[frame_box(slice(5, 115), slice(5, 108)), frame_box(slice(0, 5), slice(0, 120))], crs="EPSG:32647").to_crs(4326)
    boundaries = external / "boundaries.gpkg"
    units.to_file(boundaries, layer="tha_admin3", driver="GPKG")

    sealed = external / "proposal_execution/nan_case_v1/jaxa_sealed"
    sealed.mkdir(parents=True)
    jaxa_zip(sealed / "JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip",
             {"flood_proxy": [frame_box(*flood)], "observation_area": [frame_box(slice(0, 120), slice(0, 120))]})
    jaxa_zip(sealed / "JAXA_20250719_FPM_ALOS2_Thailand_geojson.zip", {"flood_proxy": [frame_box(slice(62, 66), slice(72, 76))]})
    for name in ("JAXA_20250728_FPM_ALOS2_Thailand_shapefile.zip", "JAXA_20250719_FPM_ALOS2_Thailand_shapefile.zip"):
        with zipfile.ZipFile(sealed / name, "w") as archive:
            archive.writestr("readme.txt", "invented")

    # THEOS-2 rule v2 water of the town chip, 2 m, with water where the flood is.
    fine_rows, fine_cols = int((TOWN["north"] - TOWN["south"]) / 2), int((TOWN["east"] - TOWN["west"]) / 2)
    fine = np.zeros((fine_rows, fine_cols), dtype="uint8")
    flood_box = frame_box(*flood).bounds
    fine[int((TOWN["north"] - flood_box[3]) / 2):int((TOWN["north"] - flood_box[1]) / 2),
         int((flood_box[0] - TOWN["west"]) / 2):int((flood_box[2] - TOWN["west"]) / 2)] = 1
    rule_v2 = external / "proposal_execution/theos2_water_rule_v2" / "water_v2_chip_003_2m.tif"
    rule_v2.parent.mkdir(parents=True)
    with rasterio.open(rule_v2, "w", driver="GTiff", height=fine_rows, width=fine_cols, count=1, dtype="uint8", nodata=255, crs="EPSG:32647",
                       transform=from_origin(TOWN["west"], TOWN["north"], 2.0, 2.0)) as target:
        target.write(fine, 1)

    # --- the records of Git --------------------------------------------------------------------------------------
    protocol = {
        "schema": "floodguard.nan_case_protocol.v1 (invented for the test)",
        "frame": {"district_pcodes": ["TH5501"]},
        "grid": {"chips": {"nan_chip_003": TOWN, "nan_chip_001": DRY_HILLS}},
        "radar": {"dry_season": {"min_valid_passes_per_cell": 6}},
        "method": {"tuned_parameters": TUNING_GRID},
        "tuning": {"sets": [{"id": "sukhothai_theos2_20250730"}, {"id": "mae_sai_20241022"},
                            {"id": "chaiyaphum_20210928", "drop_rule": "dropped if its radar cannot be fetched"}],
                   "constraint": "the no-answer share of compared cells is at most 0.20 in every set"},
        "sealed_references": {"files": {path.name: sha(path) for path in sorted(sealed.iterdir())}},
    }
    areas = {"areas": {"nan_frame": {"grid": FRAME},
                       **{area: {"role": "tuning", "grid": grid, "event": {"pass_utc": f"{area_events[area][0][:4]}-{area_events[area][0][4:6]}-"
                                                                                       f"{area_events[area][0][6:8]}T{area_events[area][0][9:11]}:{area_events[area][0][11:13]}",
                                                                           "relative_orbit": area_events[area][1]},
                                 "dry_season": {"relative_orbit": area_events[area][1]}} for area, grid in tuning_grids.items()},
                       "chaiyaphum_20210928": {"role": "tuning", "grid": {"west": 540000, "north": 1800000, "rows": SIZE, "cols": SIZE}}}}
    references = {"sets": {"sukhothai_theos2_20250730": {"status": "built", "reference_20m": {"name": "reference_20m.tif",
                                                                                              "sha256": sha(external / "proposal_execution/nan_case_v1/references_tuning/sukhothai_chip/reference_20m.tif")}},
                           "mae_sai_20241022": {"status": "built"},
                           "chaiyaphum_20210928": {"dropped": True, "drop_reason": "invented: its reference cannot be read as recorded"}}}
    key_points = [{"id": f"p{index}", "chip": chip, "group": "g", "row": 0, "column": 0, "x": x, "y": y}
                  for index, (chip, x, y) in enumerate([("chip_003", 601450.0, 1998700.0), ("chip_003", 601470.0, 1998690.0),
                                                        ("chip_003", 601790.0, 1998790.0), ("chip_003", 601410.0, 1998410.0),
                                                        ("chip_001", 600300.0, 1998000.0)])]
    files = {
        "docs/proposal_execution/nan_case_protocol_v1.json": protocol,
        "outputs/nan_case/areas_v1.json": areas,
        "outputs/nan_case/tuning_references_v1.json": references,
        "outputs/theos2_water_rule_v2/freeze_v1.json": {"frozen_rule": {"chips": {"chip_003": {"raster_outside_git": {"name": rule_v2.name, "sha256": sha(rule_v2)}}}}},
        "outputs/theos2_water_labels/key_v1.json": {"points": key_points},
    }
    for relative, value in files.items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_bytes((json.dumps(value, indent=1) + "\n").encode("utf-8"))
    sample_id = sha(repo / "outputs/theos2_water_labels/key_v1.json")
    labels = {"p0": "water", "p1": "water", "p2": "not_water", "p3": "not_water", "p4": "not_water"}
    (repo / "outputs/theos2_water_labels/sample_v1.json").write_text(json.dumps({"sample_id": sample_id}) + "\n", encoding="utf-8")
    for person, change in (("ann", {}), ("ben", {"p0": "cannot_tell"}), ("cat", {"p2": "water"})):
        given = {**labels, **change}
        (repo / f"outputs/theos2_water_labels/labels_{person}.json").write_text(
            json.dumps({"sample_id": sample_id, "labeller": person, "labels": {key: {"label": value} for key, value in given.items()}}) + "\n", encoding="utf-8")

    git(tmp_path, "init", "-q", "--bare", "--template=", str(remote))
    git(repo.parent, "init", "-q", "--template=", "-b", "main", str(repo))
    for key, value in (("user.name", "test"), ("user.email", "test@example.org"), ("core.autocrlf", "false")):
        git(repo, "config", key, value)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "invented case")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "-u", "origin", "main")
    return {"repo": repo, "external": external, "boundaries": boundaries, "theos2": tmp_path / "theos2", "script": load_script()}


def stage(case: dict, *args: str, hooks: dict | None = None) -> dict:
    return case["script"].run(list(args), root=case["repo"], hooks=hooks)


def refused(case: dict, *args: str, match: str, hooks: dict | None = None) -> None:
    with pytest.raises(case["script"].StageError, match=match):
        stage(case, *args, hooks=hooks)


def tune_and_freeze(case: dict) -> None:
    repo = case["repo"]
    stage(case, "tune", "--external-root", str(case["external"]))
    stage(case, "freeze")
    git(repo, "add", "outputs/nan_case/tuning_v1.json", "outputs/nan_case/freeze_v1.json")
    git(repo, "commit", "-q", "-m", "freeze")
    git(repo, "push", "-q")


def command_of_the_test(case: dict) -> list[str]:
    return ["test", "--external-root", str(case["external"]), "--theos2-dir", str(case["theos2"]), "--boundaries", str(case["boundaries"])]


def no_gfm(*_args: object) -> None:
    return None


def test_the_stages_run_in_the_order_of_the_protocol_and_refuse_out_of_it(case: dict) -> None:
    repo, external = case["repo"], case["external"]
    tune = ["tune", "--external-root", str(external)]

    # tune: the code must be committed, the references record must exist.
    script_copy = repo / "scripts/nan_case_method.py"
    original = script_copy.read_bytes()
    script_copy.write_bytes(original + b"# changed\n")
    refused(case, *tune, match="commit the code first")
    script_copy.write_bytes(original)
    (repo / "outputs/nan_case/tuning_references_v1.json").rename(repo / "references.json")
    refused(case, *tune, match="tuning_references_v1.json is missing")
    (repo / "references.json").rename(repo / "outputs/nan_case/tuning_references_v1.json")
    refused(case, "freeze", match="no tuning record")
    refused(case, *command_of_the_test(case), match="no freeze record")

    tuning = stage(case, *tune)
    raw = (repo / "outputs/nan_case/tuning_v1.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert tuning["sets_used"] == ["sukhothai_theos2_20250730", "mae_sai_20241022"]
    assert tuning["sets"]["chaiyaphum_20210928"]["dropped"] is True
    assert len(tuning["score_table"]) == 16 and tuning["candidates"] == 16
    # The flood is darker than -18 dB and far below its dry mean; a VH limit of -15 dB also takes noise.
    # Ties go to the most negative z, the smallest HAND limit and the smallest spread limit.
    assert tuning["selection"]["selected"] == {"z_vh_max": -2.0, "vh_after_max_db": -18.0, "hand_max_m": 5.0, "dry_spread_max_db": 2.0}
    assert tuning["selected_on_each_set"]["mae_sai_20241022"]["central"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0)
    assert tuning["git_commit_at_tuning"] == git(repo, "rev-parse", "HEAD")
    low, high = tuning["selection"]["no_answer_share_range_by_set"]["sukhothai_theos2_20250730"]
    assert 0 < low <= high < 0.2
    for field in ("generated_at_utc", "source_timestamp", "confidence_class", "assumptions"):
        assert tuning[field]
    assert tuning["official_warning"] is False and tuning["operational_status"] == "non_operational"
    assert tuning["comparators"]["by_set"]["mae_sai_20241022"]["scores"]["m1_v2_dry_mean_before"]["not_run"]
    assert tuning["comparators"]["by_set"]["mae_sai_20241022"]["scores"]["r37_frozen_detector"]["iou_no_answer_as_not_flagged"] > 0.5
    json.loads(raw)
    refused(case, *tune, match="exists; use --replace")

    # freeze: refuses with uncommitted code, writes the levels, then refuses again.
    script_copy.write_bytes(original + b"# changed\n")
    refused(case, "freeze", match="uncommitted changes")
    script_copy.write_bytes(original)
    freeze = stage(case, "freeze")
    assert freeze["flood_levels"]["lower"]["z_vh_max"] == -2.5 and freeze["flood_levels"]["upper"]["z_vh_max"] == -1.5
    assert freeze["code_sha256"]["src/floodguard/m1z.py"] == sha(ROOT / "src/floodguard/m1z.py")
    assert freeze["code_sha256"]["scripts/nan_case_method.py"] == sha(SCRIPT)
    assert freeze["git_commit_at_tuning"] == tuning["git_commit_at_tuning"] and len(freeze["score_table"]) == 16
    refused(case, "freeze", match="exists; use --replace")
    refused(case, *tune, match="tuning again needs --replace")

    # test: the freeze must be committed in HEAD, unchanged and pushed, and the code must match.
    refused(case, *command_of_the_test(case), match="not in the HEAD commit")
    git(repo, "add", "outputs/nan_case/tuning_v1.json", "outputs/nan_case/freeze_v1.json")
    git(repo, "commit", "-q", "-m", "freeze")
    refused(case, *command_of_the_test(case), match="on no remote branch")
    git(repo, "push", "-q")
    frozen_bytes = (repo / "outputs/nan_case/freeze_v1.json").read_bytes()
    (repo / "outputs/nan_case/freeze_v1.json").write_bytes(frozen_bytes.replace(b'"low"', b'"medium"', 1))
    refused(case, *command_of_the_test(case), match="differs from it")
    (repo / "outputs/nan_case/freeze_v1.json").write_bytes(frozen_bytes)
    script_copy.write_bytes(original + b"# changed\n")
    refused(case, *command_of_the_test(case), match="code differs")
    script_copy.write_bytes(original)
    refused(case, "maps", "--external-root", str(external), "--boundaries", str(case["boundaries"]), match="after the test result exists")

    result = stage(case, *command_of_the_test(case), hooks={"gfm_fetch": no_gfm})
    test1 = result["test_1"]
    assert test1["reference"].startswith("JAXA") and test1["jaxa_usability"]["usable"] is True
    assert test1["pass"]["label"] == "20250728T1121_o128_S1C"          # no zoned time in the files: the protocol's pass
    assert "cannot be read" in test1["pass_choice"]
    assert test1["central"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0) and test1["passes"] is True
    assert test1["central_interval_95"]["resamples"] == 1000 and test1["central_interval_95"]["tiles"] == 4
    assert set(test1["central_by_worldcover_group"]) == {"built_up", "cropland", "tree_cover", "other"}
    assert test1["external_comparator_gfm_same_pass"]["not_run"]
    assert result["test_1b_report_only"]["jaxa_usability"]["usable"] is False
    test2 = result["test_2"]
    assert test2["pass"]["label"] == "20250731T2308_o62_S1A" and test2["hours_after_theos2"] == pytest.approx(19.28, abs=0.01)
    assert test2["central"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0)
    agreement = test2["labelled_points"]["agreement"]["central"]
    assert agreement["points"] == 4 and agreement["points_with_a_label"] == 4 and agreement["share_agreed_no_answer_as_not_flagged"] == 1.0
    assert result["dry_control"]["passes"] is True and result["dry_control"]["central"]["flagged_cells"] == 0
    assert result["binding"]["test_1_passes"] is True and result["binding"]["case_reference_date"] == "2025-07-28"
    assert result["binding"]["flood_input_of_case_N1"]["label"] == "20250728T1121_o128_S1C"
    rasterio, _gpd = geo()
    maps = external / "proposal_execution/nan_case_v1/method/maps"
    assert sorted(path.name for path in maps.glob("*.tif")) == ["m1z_20250728T1121_o128_S1C.tif", "m1z_20250731T2308_o62_S1A.tif"]
    with rasterio.open(maps / "m1z_20250731T2308_o62_S1A.tif") as source:
        assert source.count == 4 and source.descriptions[1] == "code_central" and source.profile["compress"] == "deflate" and source.profile["tiled"]
        central = source.read(2)
    assert (central[62:76, 72:88] == 1).all() and (central[:, 110:112] == 0).all()
    raw = (repo / "outputs/nan_case/test_result_v1.json").read_bytes()
    assert b"\r" not in raw and b'"coordinates"' not in raw  # figures only, no JAXA geometry

    refused(case, *command_of_the_test(case), match="the test runs once")
    refused(case, *command_of_the_test(case), "--replace", match="--replace needs --reason")
    refused(case, *tune, match="never tuned again")
    refused(case, "freeze", match="never frozen again")

    outputs = repo / "outputs/nan_case"
    assert lint_records([outputs / "tuning_v1.json", outputs / "freeze_v1.json", outputs / "test_result_v1.json"]) == []
    index = stage(case, "maps", "--external-root", str(external), "--boundaries", str(case["boundaries"]))
    assert lint_records([maps / "m1z_20250731T2308_o62_S1A.json", maps / "maps_index_v1.json"]) == []
    assert sorted(index["maps"]) == ["20250728T1121_o128_S1C", "20250731T2308_o62_S1A"]
    record = json.loads((maps / "m1z_20250731T2308_o62_S1A.json").read_text(encoding="utf-8"))
    assert record["official_warning"] is False and record["source_timestamp"] == "2025-07-31T23:08:00Z"
    assert record["summary"]["central"]["flagged_km2_frame_land"] > 0 and record["map"]["sha256"] == sha(maps / "m1z_20250731T2308_o62_S1A.tif")


def test_the_gfm_fallback_when_jaxa_does_not_say_where_it_looked(case: dict) -> None:
    sealed = case["external"] / "proposal_execution/nan_case_v1/jaxa_sealed"
    flood = (slice(62, 76), slice(72, 88))
    jaxa_zip(sealed / "JAXA_20250728_FPM_ALOS2_Thailand_geojson.zip", {"flood_proxy": [frame_box(*flood)]})
    protocol_path = case["repo"] / "docs/proposal_execution/nan_case_protocol_v1.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    protocol["sealed_references"]["files"] = {path.name: sha(path) for path in sorted(sealed.iterdir())}
    protocol_path.write_bytes((json.dumps(protocol, indent=1) + "\n").encode("utf-8"))
    git(case["repo"], "commit", "-q", "-am", "an invented seal without an observation area")
    git(case["repo"], "push", "-q")
    tune_and_freeze(case)
    asked = []

    def fake_gfm(grid: tuple, start: object, end: object) -> dict:
        asked.append((start, end))
        rows, cols = grid[2], grid[3]
        flood_map = np.zeros((rows, cols), dtype="uint8")
        flood_map[flood] = 1
        flood_map[:, :10] = 255                       # GFM holds no data there
        exclusion = np.zeros((rows, cols), dtype="uint8")
        exclusion[100:, :] = 1                        # excluded
        return {"flood": flood_map, "exclusion": exclusion, "items": [{"id": "invented", "datetime": "2025-07-31T23:08:30Z"}]}

    result = stage(case, *command_of_the_test(case), hooks={"gfm_fetch": fake_gfm})
    test1 = result["test_1"]
    assert test1["jaxa_usability"]["usable"] is False and "no observation-area geometry" in test1["jaxa_usability"]["why"]
    assert test1["reference"].startswith("GFM") and "same-pass" in test1["label"]
    assert test1["pass"]["label"] == "20250731T2308_o62_S1A" and test1["passes"] is True
    assert str(asked[0][0]).startswith("2025-07-31 22:38") and str(asked[0][1]).startswith("2025-07-31 23:38")
    assert result["binding"]["case_reference_date"] == "2025-07-31"
    assert test1["central"]["compared_cells"] < result["frame"]["frame_land_cells"]
    # GFM of the pass is read once and is also the external comparator of test 2 (report only).
    assert len(asked) == 1
    assert result["test_2"]["external_comparator_gfm_same_pass"]["iou_no_answer_as_not_flagged"] == pytest.approx(1.0)


def test_freeze_refuses_when_the_tuning_selected_nothing(case: dict) -> None:
    script = case["script"]
    repo = case["repo"]
    record = {"code_sha256": script.code_hashes(repo), "protocol": {"sha256": script.sha256_file(repo / script.PROTOCOL)},
              "selection": {"selected": None, "why": "invented"}}
    (repo / "outputs/nan_case/tuning_v1.json").write_text(json.dumps(record) + "\n", encoding="utf-8")
    refused(case, "freeze", match="selected nothing")


def test_the_firewall_keeps_stages_before_the_test_away_from_the_sealed_files() -> None:
    script = load_script()
    for path in ("x/proposal_execution/nan_case_v1/jaxa_sealed/a.zip", "x/theos2_water_rule_v2/water_v2_chip_003_2m.tif",
                 "x/outputs/theos2_water_labels/key_v1.json", "https://data.eodc.eu/collections/GFM/a.tif"):
        for name in ("tune", "freeze", "maps"):
            with pytest.raises(script.StageError, match="firewall"):
                script.guard(path, name)
        script.guard(path, "test")
    with pytest.raises(script.StageError, match="Nan frame"):
        script.guard("x/radar/nan_frame/event_1.tif", "tune")


def test_jaxa_layers_are_sorted_into_flood_observation_area_and_other_water() -> None:
    script = load_script()
    for text in ("observation_area", "Obs_Area", "ALOS-2 observation", "scene_footprint", "coverage", "swath outline"):
        assert script.observation_text(text), text
    for text in ("Observed flood", "observed_flood_extent", "flood_extent", "JAXA_20250728_FPM_ALOS2_Thailand", "Flood observation area"):
        assert not script.observation_text(text), text
    assert script.OTHER_VALUE.fullmatch("Permanent water") and script.OTHER_VALUE.fullmatch("river")
    assert not script.OTHER_VALUE.fullmatch("water increase compared with the image before the event")
    assert script.OTHER_PATTERN.search("reference_water_mask") and not script.OTHER_PATTERN.search("flood_before_after")


def test_pass_times_orbits_and_jaxa_times_are_read_only_when_they_are_given() -> None:
    script = load_script()
    assert str(script.parse_time("20250731T230815")) == "2025-07-31 23:08:15+00:00"
    assert str(script.parse_time("2025-07-28T18:21:00+07:00")) == "2025-07-28 11:21:00+00:00"
    assert script.parse_time("event_20250731_o62") is None
    assert [str(item) for item in script.zoned_times("obs 2025-07-28 14:05:10 JST; 2025-07-28T05:05Z; 2025-07-28 05:05")] == [
        "2025-07-28 05:05:10+00:00", "2025-07-28 05:05:00+00:00"]
    assert script.find_value({"sources": [{"relative_orbit": 62}]}, script.ORBIT_KEYS) == 62
    status = script.reference_status({"sets": [{"id": "a", "status": "dropped: no file"}]}, "a", "area_a")
    assert status["dropped"] is True and status["listed"] is True
    assert script.reference_status({"sets": {}}, "b", "area_b")["dropped"] is True


def test_records_keep_their_wording_and_compact_table() -> None:
    script = load_script()
    text = script.dumps_record({"a": 1, "score_table": [{"x": 1}, {"x": 2}]}, compact=("score_table",))
    assert json.loads(text) == {"a": 1, "score_table": [{"x": 1}, {"x": 2}]} and '\n  {"x": 1},\n  {"x": 2}\n ]' in text
    from floodguard.wording_lint import find_violations, load_rules

    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    sentences = [*script.ASSUMPTIONS_METHOD, *script.LIMITS, *script.COMPARATOR_NOTES.values()]
    # "agreement with <reference>, not accuracy" is the wording the case asks for; the replay page's rules have no
    # allowance for it, so it is taken out before the rest is checked.
    assert any("not accuracy" in sentence for sentence in sentences)
    cleaned = [sentence.replace("not accuracy", "") for sentence in sentences]
    assert [finding for sentence in cleaned for finding in find_violations(sentence, rules)] == []
    for word in ("accurate", "validated", "real-time", "forecast"):
        assert not any(word in sentence.lower() for sentence in sentences)
    from floodguard.wording_lint import python_strings

    for path in (SCRIPT, ROOT / "src/floodguard/m1z.py"):
        texts = python_strings(path.read_text(encoding="utf-8"))
        assert [finding.describe() for text in texts for finding in find_violations(text.replace("not accuracy", ""), rules, path.name)] == []


def lint_records(paths: list[Path]) -> list[str]:
    """Wording findings in the strings of JSON records, with the prescribed "not accuracy" taken out first."""

    from floodguard.wording_lint import find_violations, json_strings, load_rules

    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    return [finding.describe() for path in paths for where, text in json_strings(json.loads(path.read_text(encoding="utf-8")))
            for finding in find_violations(text.replace("not accuracy", ""), rules, f"{path.name} {where}")]


def test_bands_are_found_by_their_descriptions(tmp_path: Path) -> None:
    rasterio, _gpd = geo()
    script = load_script()
    grid = {"west": 1000, "north": 2000, "rows": 3, "cols": 4}
    path = tmp_path / "event_20250731T2308Z_s1a_o62.tif"
    write_tif(path, grid, [np.full((3, 4), 2.0, dtype="float32"), np.full((3, 4), 1.0, dtype="float32")],
              names=["gamma0 VH, linear", "gamma0 VV, linear"], nodata=float("nan"))
    bands = script.read_bands(path, (1000.0, 2000.0, 3, 4), "tune", script.EVENT_BANDS)
    assert (bands["vh"] == 2.0).all() and (bands["vv"] == 1.0).all()
    with pytest.raises(script.StageError, match="not on the grid"):
        script.read_bands(path, (1020.0, 2000.0, 3, 4), "tune", script.EVENT_BANDS)
    described = script.describe_pass(path, "tune")
    assert described.label == "20250731T2308_o62_S1A" and described.orbit == 62


def test_tune_refuses_to_drop_a_set_the_protocol_gives_no_drop_rule(case: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    repo = case["repo"]
    path = repo / "outputs/nan_case/tuning_references_v1.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["sets"]["mae_sai_20241022"] = {"status": "dropped: invented"}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    refused(case, "tune", "--external-root", str(case["external"]), match="no drop rule")
    # On the command line a refusal is an exit code of 2 and a sentence, not a traceback.
    monkeypatch.setattr(case["script"], "ROOT", repo)
    assert case["script"].main(["tune", "--external-root", str(case["external"])]) == 2
    assert "refused: " in capsys.readouterr().err


def test_amendment_1_limits_the_no_answer_share_from_each_sets_own_floor() -> None:
    def candidate(z: float, shares: dict[str, float], iou: float) -> dict:
        return {"parameters": {"z_vh_max": z, "vh_after_max_db": -18.0, "hand_max_m": 5, "dry_spread_max_db": None},
                "sets": {name: {"iou_no_answer_as_not_flagged": iou, "no_answer_share": share} for name, share in shares.items()}}

    candidates = [candidate(-1.0, {"a": 0.40, "b": 0.06}, 0.50), candidate(-2.0, {"a": 0.37, "b": 0.06}, 0.45),
                  candidate(-3.0, {"a": 0.60, "b": 0.06}, 0.60)]
    limits = m1z.no_answer_limits_from_floor(candidates, 0.10)
    assert limits == {"a": 0.47, "b": 0.16}
    # The absolute limit of the protocol as first written selects nothing here.
    assert m1z.select_parameters(candidates)["selected"] is None
    chosen = m1z.select_parameters(candidates, max_no_answer_by_set=limits)
    # The third candidate wins the score only by not answering (0.60 is more than 0.10 above the floor 0.37).
    assert chosen["eligible"] == 2 and chosen["selected"]["z_vh_max"] == -1.0
    assert chosen["max_no_answer_share_by_set"] == limits and chosen["max_no_answer_share"] is None


def test_amendment_1_raises_sentinel_1c_event_passes_and_reads_platform_names() -> None:
    script = load_script()
    assert script.platform_key("Sentinel-1C") == "sentinel-1c"
    assert script.platform_key("S1C") == "sentinel-1c"
    assert script.platform_key("sentinel-1a") == "sentinel-1a"
    offsets = script.platform_offsets(Path(__file__).resolve().parents[1])
    assert offsets == {"sentinel-1c": 0.79}
