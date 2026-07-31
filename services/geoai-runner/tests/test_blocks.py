"""Network-free tests for the runner-local spatial-block holdout partition.

These are the acceptance criteria for T0.1. They exist because the leaks they
guard against (a tile straddling roles, a train pixel adjacent to a test pixel,
a non-reproducible assignment) are all silent failures: the pipeline would still
run and still print a number, just a meaningless one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from affine import Affine

from geoai_runner.realpipeline import blocks
from geoai_runner.realpipeline.blocks import (
    BUFFER,
    ROLE_CODES,
    BlockGeometryError,
    assign_spatial_blocks,
    plan_block_geometry,
    tiles_for_role,
)

# Mae Sai bounds from the committed run manifest (outputs/geoai/geoai_metrics.json).
MAE_SAI_BOUNDS = (99.79900844808157, 20.249920253417027, 100.04446066183026, 20.475366822520876)
SHAPE = (1024, 1024)


def _transform(bounds=MAE_SAI_BOUNDS, shape=SHAPE):
    left, bottom, right, top = bounds
    height, width = shape
    return Affine.translation(left, top) * Affine.scale(
        (right - left) / width, (bottom - top) / height
    )


@pytest.fixture(scope="module")
def assignment():
    return assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, seed=0)


# --------------------------------------------------------------------------- #
# Geometry planning
# --------------------------------------------------------------------------- #
def test_plan_derives_block_size_from_tile_and_buffer():
    plan = plan_block_geometry(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0)
    # The binding constraint: a buffered block core must still hold one tile.
    assert plan.block_m >= plan.tile_m + 2 * plan.buffer_m
    assert plan.core_m >= plan.tile_m
    # At Mae Sai's ~25 km extent this forces 3x3, not the 5x5 a small buffer allows.
    assert plan.blocks_per_axis == 3
    assert plan.n_blocks == 9


def test_plan_rejects_geometry_that_cannot_fit_a_tile():
    # A 1600 m buffer with 128 px (~3.2 km) tiles needs ~6.4 km blocks; demanding
    # 25 of them over a 25 km scene is impossible and must fail loudly rather
    # than silently shrinking the buffer.
    with pytest.raises(BlockGeometryError, match="min_blocks"):
        plan_block_geometry(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, min_blocks=25)


def test_smaller_buffer_admits_more_blocks():
    coarse = plan_block_geometry(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0)
    fine = plan_block_geometry(SHAPE, _transform(), tile_size_px=128, buffer_m=500.0)
    assert fine.n_blocks > coarse.n_blocks


def test_pixel_size_is_anisotropic_and_plausible():
    pixel_m_y, pixel_m_x = blocks.pixel_size_metres(_transform(), 20.4)
    assert 24.0 < pixel_m_y < 25.0
    assert 24.5 < pixel_m_x < 25.5
    assert pixel_m_x != pixel_m_y


# --------------------------------------------------------------------------- #
# Assignment invariants
# --------------------------------------------------------------------------- #
def test_roles_are_disjoint_and_cover_the_grid(assignment):
    grid = assignment.role_grid
    valid_codes = set(ROLE_CODES.values()) | {BUFFER}
    assert set(np.unique(grid)).issubset(valid_codes)
    # Every pixel has exactly one role; a uint8 grid makes overlap impossible by
    # construction, so the meaningful check is total coverage.
    total = sum(int((grid == code).sum()) for code in valid_codes)
    assert total == grid.size


def test_every_role_receives_blocks_and_pixels(assignment):
    for role in ROLE_CODES:
        assert assignment.role_block_counts[role] >= 1, role
        assert assignment.mask(role).sum() > 0, role


def test_block_counts_follow_requested_ratios(assignment):
    # 9 blocks at 60/20/20 -> 5/2/2.
    assert assignment.role_block_counts == {"train": 5, "val": 2, "test": 2}


def test_assignment_is_deterministic():
    first = assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, seed=0)
    second = assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, seed=0)
    assert first.assignment_sha256 == second.assignment_sha256
    assert np.array_equal(first.role_grid, second.role_grid)


def test_seed_changes_the_assignment():
    first = assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, seed=0)
    other = assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0, seed=7)
    assert first.assignment_sha256 != other.assignment_sha256


def test_buffer_separates_differing_roles(assignment):
    """No pixel of one role may lie within buffer_m of a pixel of another role."""

    plan = assignment.plan
    buffer_px_y = plan.buffer_m / plan.pixel_m_y
    buffer_px_x = plan.buffer_m / plan.pixel_m_x
    # Sample rather than compute all-pairs: the exact guarantee is enforced in
    # _distance_to_differing_role; this is an independent spot check.
    rng = np.random.default_rng(0)
    grid = assignment.role_grid
    for role, code in ROLE_CODES.items():
        rows, cols = np.nonzero(grid == code)
        if rows.size == 0:  # pragma: no cover - guarded by another test
            continue
        picks = rng.choice(rows.size, size=min(400, rows.size), replace=False)
        for index in picks:
            r, c = int(rows[index]), int(cols[index])
            r0 = max(0, r - int(math.floor(buffer_px_y)))
            r1 = min(grid.shape[0], r + int(math.floor(buffer_px_y)) + 1)
            c0 = max(0, c - int(math.floor(buffer_px_x)))
            c1 = min(grid.shape[1], c + int(math.floor(buffer_px_x)) + 1)
            window = grid[r0:r1, c0:c1]
            others = set(np.unique(window)) - {code, BUFFER}
            assert not others, f"role {role} pixel ({r},{c}) is within the buffer of {others}"


def test_buffer_costs_are_recorded(assignment):
    share = assignment.role_pixel_share
    assert 0.0 < share["buffer"] < 1.0
    assert abs(sum(share.values()) - 1.0) < 1e-9
    # The conservative buffer is expensive; the manifest must say so rather than
    # leaving the reader to infer it.
    assert share["buffer"] > 0.2


# --------------------------------------------------------------------------- #
# Tile containment -- the label-leak guarantee
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role", sorted(ROLE_CODES))
def test_no_tile_crosses_roles(assignment, role):
    origins = tiles_for_role(assignment, role, tile_size=128, stride=32)
    code = ROLE_CODES[role]
    grid = assignment.role_grid
    for row, col in origins:
        window = grid[row : row + 128, col : col + 128]
        assert set(np.unique(window)) == {code}


def test_train_role_yields_usable_tiles(assignment):
    origins = tiles_for_role(assignment, "train", tile_size=128, stride=32)
    # If the geometry ever stops producing training tiles the pipeline would
    # train on nothing and still "succeed", so assert a real floor.
    assert len(origins) >= 20


def test_tile_sets_are_disjoint_across_roles(assignment):
    sets = {
        role: set(tiles_for_role(assignment, role, tile_size=128, stride=32))
        for role in ROLE_CODES
    }
    assert not sets["train"] & sets["val"]
    assert not sets["train"] & sets["test"]
    assert not sets["val"] & sets["test"]


def test_unknown_role_is_rejected(assignment):
    with pytest.raises(BlockGeometryError, match="unknown role"):
        tiles_for_role(assignment, "holdout", tile_size=128, stride=32)


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #
def test_role_ratios_must_sum_to_one():
    with pytest.raises(BlockGeometryError, match="sum to 1.0"):
        assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, ratios=(0.5, 0.2, 0.2))


def test_negative_ratio_is_rejected():
    with pytest.raises(BlockGeometryError, match="non-negative"):
        assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, ratios=(1.2, -0.2, 0.0))


def test_zero_train_ratio_is_rejected():
    with pytest.raises(BlockGeometryError, match="train ratio"):
        assign_spatial_blocks(SHAPE, _transform(), tile_size_px=128, ratios=(0.0, 0.5, 0.5))


def test_manifest_marks_partition_as_not_sealed(assignment):
    payload = assignment.to_dict()
    assert payload["kind"] == blocks.PARTITION_KIND
    assert payload["is_sealed_multi_event_partition"] is False
    assert payload["assignment_sha256"] == assignment.assignment_sha256


# --------------------------------------------------------------------------- #
# Geographic-confound diagnostics
# --------------------------------------------------------------------------- #
def test_contiguity_is_reported_for_every_role(assignment):
    report = assignment.contiguity()
    assert set(report) == set(ROLE_CODES)
    for role, entry in report.items():
        assert entry["n_blocks"] == assignment.role_block_counts[role]
        assert entry["n_components"] >= 1
        assert isinstance(entry["single_patch"], bool)


def test_contiguity_detects_a_single_patch_role():
    # Constructed grid: role 2 occupies one solid column -> a single patch.
    grid = np.array([[0, 0, 2], [0, 1, 2], [0, 1, 2]], dtype="uint8")
    report = blocks._role_block_contiguity(grid)
    assert report["test"]["n_components"] == 1
    assert report["test"]["single_patch"] is True
    assert report["train"]["single_patch"] is True


def test_contiguity_detects_a_dispersed_role():
    # Role 2 in two opposite corners -> two components, no single-patch confound.
    grid = np.array([[2, 0, 0], [0, 1, 1], [0, 0, 2]], dtype="uint8")
    report = blocks._role_block_contiguity(grid)
    assert report["test"]["n_components"] == 2
    assert report["test"]["single_patch"] is False


def test_dispersed_seed_selection_avoids_single_patch_roles():
    seed, report = blocks.select_dispersed_seed(
        SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0
    )
    assert not any(entry["single_patch"] for entry in report.values()), report
    # Seed 0 is known to leave the test role in one eastern patch, so the
    # selector must actually move off the default rather than no-op.
    assert seed != 0


def test_dispersed_seed_selection_is_deterministic():
    first = blocks.select_dispersed_seed(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0)
    second = blocks.select_dispersed_seed(SHAPE, _transform(), tile_size_px=128, buffer_m=1600.0)
    assert first[0] == second[0]


def test_dispersed_seed_selection_falls_back_and_reports():
    # A single-candidate range cannot disperse anything; the selector must return
    # that seed with its confound visible rather than widening the search.
    seed, report = blocks.select_dispersed_seed(
        SHAPE, _transform(), candidate_seeds=range(0, 1), tile_size_px=128, buffer_m=1600.0
    )
    assert seed == 0
    assert report["test"]["single_patch"] is True


def test_block_role_map_matches_block_roles(assignment):
    mapped = assignment.block_role_map()
    assert len(mapped) == assignment.plan.blocks_per_axis
    for row_index, row in enumerate(mapped):
        for col_index, name in enumerate(row):
            assert ROLE_CODES[name] == int(assignment.block_roles[row_index, col_index])
