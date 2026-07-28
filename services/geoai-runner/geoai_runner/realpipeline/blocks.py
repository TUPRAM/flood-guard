"""Deterministic spatial-block partitioning for runner-local holdout evaluation.

Why this module exists
----------------------
Before this, Component B tiled the *whole* scene with overlapping windows, let
``geoai.train_segmentation_model`` carve a **random** validation split out of
those overlapping tiles, and then reported metrics from inference over the same
full raster it had just trained on. Three separate leaks stacked on top of each
other, so the published IoU measured memorisation, not generalisation.

This module supplies the missing partition: a deterministic assignment of every
pixel to ``train`` / ``val`` / ``test`` in contiguous spatial blocks, with a
dead-zone buffer between blocks of *differing* roles.

What this is NOT
----------------
This is **not** a sealed multi-event partition under
``docs/immutable-multi-event-partitions-v1.md``. That contract requires
qualified label releases, event-level grouping across ≥5 hydrological episodes,
and a signed holdout-custody receipt -- all of which remain externally blocked.
Every artifact this module produces carries
``is_sealed_multi_event_partition=False`` so a runner-local block split can
never be mistaken for that clearance. This is the weaker, honest construct: one
scene, one event, spatially disjoint roles.

Geometry
--------
The buffer exists because a convolutional model's receptive field is much wider
than a pixel. A 128 px tile at ~25 m/px spans ~3.2 km, so a tile whose edge
merely touches a role boundary still *sees* 3.2 km of context across it.
``tiles_for_role`` already guarantees a tile lies wholly inside one role, which
removes label leakage; the buffer additionally removes context leakage by
pushing differing roles ``buffer_m`` apart on each side.

That conservatism is not free, and the cost is structural rather than a tuning
knob: block size must satisfy ``block_m >= tile_m + 2 * buffer_m`` or a block's
post-buffer core cannot hold a single tile. At Mae Sai's ~25 km extent with
128 px tiles and a 1600 m buffer this forces 3x3 = 9 blocks of ~8.3 km rather
than the 5x5 = 25 that a smaller buffer would allow. Fewer, larger blocks mean
higher block-level variance in every reported metric. :func:`plan_block_geometry`
solves the constraint explicitly and records the trade-off in the manifest
instead of leaving it implicit.

Distances are computed in metres on a local planar approximation of the
EPSG:4326 grid, which is accurate to well under a percent over a district-sized
extent and avoids a reprojection dependency in a module that must run in the
runner's dependency-light base environment (numpy only -- no scipy).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np

# --------------------------------------------------------------------------- #
# Role codes
# --------------------------------------------------------------------------- #
TRAIN = 0
VAL = 1
TEST = 2
BUFFER = 255

ROLE_CODES: dict[str, int] = {"train": TRAIN, "val": VAL, "test": TEST}
ROLE_NAMES: dict[int, str] = {code: name for name, code in ROLE_CODES.items()}

PARTITION_KIND = "runner_local_spatial_blocks_v1"

# Local planar approximation constants (WGS84 mean values).
_METRES_PER_DEGREE_LAT = 110_540.0
_METRES_PER_DEGREE_LON = 111_320.0


class BlockGeometryError(ValueError):
    """Raised when a block/buffer/tile geometry cannot satisfy its constraints."""


# --------------------------------------------------------------------------- #
# Pixel geometry
# --------------------------------------------------------------------------- #
def pixel_size_metres(transform, latitude: float) -> tuple[float, float]:
    """Return ``(pixel_m_y, pixel_m_x)`` for an EPSG:4326 affine transform.

    ``transform.a`` is the signed x (longitude) pixel size in degrees and
    ``transform.e`` the signed y (latitude) pixel size. Longitude degrees shrink
    by ``cos(latitude)``; latitude degrees do not.
    """

    if not math.isfinite(latitude) or abs(latitude) > 90.0:
        raise BlockGeometryError(
            f"latitude must be a finite value in [-90, 90]; got {latitude!r}."
        )
    deg_x = abs(float(transform.a))
    deg_y = abs(float(transform.e))
    if deg_x <= 0.0 or deg_y <= 0.0:
        raise BlockGeometryError("transform must have non-zero pixel sizes.")
    pixel_m_x = deg_x * _METRES_PER_DEGREE_LON * math.cos(math.radians(latitude))
    pixel_m_y = deg_y * _METRES_PER_DEGREE_LAT
    if pixel_m_x <= 0.0 or pixel_m_y <= 0.0:
        raise BlockGeometryError("computed pixel size collapsed to zero metres.")
    return pixel_m_y, pixel_m_x


# --------------------------------------------------------------------------- #
# Geometry planning
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BlockGeometryPlan:
    """A viable block geometry, plus the constraint arithmetic that produced it."""

    blocks_per_axis: int
    block_m: float
    buffer_m: float
    tile_size_px: int
    tile_m: float
    core_m: float
    pixel_m_y: float
    pixel_m_x: float
    scene_m_y: float
    scene_m_x: float
    n_blocks: int

    def to_dict(self) -> dict[str, object]:
        """Return manifest-friendly geometry fields."""

        return {
            "blocks_per_axis": self.blocks_per_axis,
            "n_blocks": self.n_blocks,
            "block_m": round(self.block_m, 1),
            "buffer_m": round(self.buffer_m, 1),
            "tile_size_px": self.tile_size_px,
            "tile_m": round(self.tile_m, 1),
            "core_m": round(self.core_m, 1),
            "pixel_m_y": round(self.pixel_m_y, 3),
            "pixel_m_x": round(self.pixel_m_x, 3),
            "scene_m_y": round(self.scene_m_y, 1),
            "scene_m_x": round(self.scene_m_x, 1),
        }


def plan_block_geometry(
    shape: tuple[int, int],
    transform,
    *,
    tile_size_px: int,
    buffer_m: float = 1600.0,
    min_blocks: int = 5,
    latitude: float = 20.4,
) -> BlockGeometryPlan:
    """Solve for the finest block grid whose cores can still hold one tile.

    The binding constraint is ``block_m >= tile_m + 2 * buffer_m``: a block that
    is buffered on all four sides retains a core of ``block_m - 2 * buffer_m``,
    and a tile cannot be placed unless that core is at least as wide as the tile.
    Subject to that, we prefer *more* blocks, because block count is what bounds
    the variance of a per-role metric.

    Raises:
        BlockGeometryError: if no grid satisfies both the tile-fit constraint and
            ``min_blocks``. Failing loudly is deliberate -- silently shrinking the
            buffer would reintroduce the context leak this module exists to remove.
    """

    height, width = _validated_shape(shape)
    if not isinstance(tile_size_px, int) or isinstance(tile_size_px, bool) or tile_size_px <= 0:
        raise BlockGeometryError(f"tile_size_px must be a positive int; got {tile_size_px!r}.")
    if not math.isfinite(buffer_m) or buffer_m < 0.0:
        raise BlockGeometryError(f"buffer_m must be finite and >= 0; got {buffer_m!r}.")
    if not isinstance(min_blocks, int) or isinstance(min_blocks, bool) or min_blocks < 3:
        raise BlockGeometryError(f"min_blocks must be an int >= 3; got {min_blocks!r}.")

    pixel_m_y, pixel_m_x = pixel_size_metres(transform, latitude)
    scene_m_y = height * pixel_m_y
    scene_m_x = width * pixel_m_x
    # Use the coarser axis so a square block is viable in both directions.
    coarse_pixel_m = max(pixel_m_y, pixel_m_x)
    tile_m = tile_size_px * coarse_pixel_m
    required_block_m = tile_m + 2.0 * buffer_m

    span_m = min(scene_m_y, scene_m_x)
    blocks_per_axis = int(span_m // required_block_m)
    if blocks_per_axis < 1:
        raise BlockGeometryError(
            f"scene span {span_m:.0f} m cannot hold even one block of the required "
            f"{required_block_m:.0f} m (tile {tile_m:.0f} m + 2 x buffer {buffer_m:.0f} m). "
            "Reduce tile_size_px or buffer_m, or use a larger study area."
        )
    n_blocks = blocks_per_axis * blocks_per_axis
    if n_blocks < min_blocks:
        raise BlockGeometryError(
            f"geometry yields only {n_blocks} block(s) ({blocks_per_axis}x{blocks_per_axis}) "
            f"but min_blocks={min_blocks}. A {buffer_m:.0f} m buffer with {tile_m:.0f} m tiles "
            f"needs {required_block_m:.0f} m blocks, and the scene spans {span_m:.0f} m. "
            "Lower tile_size_px, lower buffer_m, or accept fewer blocks explicitly."
        )

    block_m = span_m / blocks_per_axis
    return BlockGeometryPlan(
        blocks_per_axis=blocks_per_axis,
        block_m=block_m,
        buffer_m=float(buffer_m),
        tile_size_px=tile_size_px,
        tile_m=tile_m,
        core_m=block_m - 2.0 * buffer_m,
        pixel_m_y=pixel_m_y,
        pixel_m_x=pixel_m_x,
        scene_m_y=scene_m_y,
        scene_m_x=scene_m_x,
        n_blocks=n_blocks,
    )


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BlockAssignment:
    """Deterministic spatial-block role assignment over one scene grid."""

    role_grid: np.ndarray  # (H, W) uint8: 0=train 1=val 2=test 255=buffer
    block_index: np.ndarray  # (H, W) int32 block id, -1 where buffered out
    block_roles: np.ndarray  # (n_blocks_y, n_blocks_x) uint8, pre-buffer
    plan: BlockGeometryPlan
    seed: int
    ratios: tuple[float, float, float]
    role_pixel_share: dict[str, float]
    role_block_counts: dict[str, int]
    assignment_sha256: str

    def mask(self, role: str) -> np.ndarray:
        """Return the boolean pixel mask for one role (buffer excluded)."""

        return self.role_grid == _role_code(role)

    def block_role_map(self) -> list[list[str]]:
        """Return the block grid as role names, north-to-south, west-to-east."""

        return [[ROLE_NAMES[int(code)] for code in row] for row in self.block_roles]

    def contiguity(self) -> dict[str, dict[str, object]]:
        """Report whether each role's blocks form one contiguous region.

        A role whose blocks are 4-connected occupies a single geographic patch,
        which means its metric is confounded with whatever is special about that
        patch -- at Mae Sai, the Sai/Ruak river corridor runs east-west, so a
        test role confined to one column measures geography as much as
        generalisation. This is a real weakness of a 9-block grid and it belongs
        in the manifest rather than in a reader's inference.
        """

        return _role_block_contiguity(self.block_roles)

    def to_dict(self) -> dict[str, object]:
        """Return the manifest projection for ``geoai_metrics.json``."""

        return {
            "kind": PARTITION_KIND,
            # Load-bearing: stops a runner-local split being read as clearance
            # under docs/immutable-multi-event-partitions-v1.md.
            "is_sealed_multi_event_partition": False,
            "seed": self.seed,
            "seed_declared_before_metrics": True,
            "ratios": {"train": self.ratios[0], "val": self.ratios[1], "test": self.ratios[2]},
            "geometry": self.plan.to_dict(),
            "blocks": dict(self.role_block_counts),
            "pixel_share": {k: round(v, 5) for k, v in self.role_pixel_share.items()},
            "block_role_map": self.block_role_map(),
            "contiguity": self.contiguity(),
            "assignment_sha256": self.assignment_sha256,
        }


def assign_spatial_blocks(
    shape: tuple[int, int],
    transform,
    *,
    plan: BlockGeometryPlan | None = None,
    tile_size_px: int = 128,
    buffer_m: float = 1600.0,
    ratios: tuple[float, float, float] = (0.6, 0.2, 0.2),
    seed: int = 0,
    latitude: float = 20.4,
    min_blocks: int = 5,
) -> BlockAssignment:
    """Assign every pixel to train/val/test blocks with a differing-role buffer.

    Blocks are ordered by a stable SHA-256 of ``(seed, block_row, block_col)`` and
    greedily assigned to whichever role is furthest below its target pixel share.
    Hash ordering rather than geographic ordering matters: a naive "test = the
    eastern third" split would confound role with the Sai river corridor, so the
    held-out score would measure geography instead of generalisation.

    The buffer is applied only between blocks whose roles *differ*. Two adjacent
    training blocks need no separation, and buffering them would throw away
    usable scene for nothing.
    """

    height, width = _validated_shape(shape)
    ratios = _validated_ratios(ratios)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise BlockGeometryError(f"seed must be an int; got {seed!r}.")
    if plan is None:
        plan = plan_block_geometry(
            shape,
            transform,
            tile_size_px=tile_size_px,
            buffer_m=buffer_m,
            min_blocks=min_blocks,
            latitude=latitude,
        )

    n_axis = plan.blocks_per_axis
    # Block edges in pixel indices; the final block absorbs the remainder so the
    # grid always covers the scene exactly.
    row_edges = [int(round(i * height / n_axis)) for i in range(n_axis)] + [height]
    col_edges = [int(round(i * width / n_axis)) for i in range(n_axis)] + [width]

    rects: list[tuple[int, int, int, int]] = []
    sizes: list[int] = []
    for br in range(n_axis):
        for bc in range(n_axis):
            r0, r1 = row_edges[br], row_edges[br + 1]
            c0, c1 = col_edges[bc], col_edges[bc + 1]
            rects.append((r0, r1, c0, c1))
            sizes.append((r1 - r0) * (c1 - c0))

    block_role_flat = _greedy_role_assignment(n_axis, sizes, ratios, seed)

    # Pre-buffer role grid and block index.
    role_grid = np.empty((height, width), dtype="uint8")
    block_index = np.empty((height, width), dtype="int32")
    for bid, (r0, r1, c0, c1) in enumerate(rects):
        role_grid[r0:r1, c0:c1] = block_role_flat[bid]
        block_index[r0:r1, c0:c1] = bid

    if plan.buffer_m > 0.0:
        distance = _distance_to_differing_role(
            rects, block_role_flat, (height, width), plan.pixel_m_y, plan.pixel_m_x
        )
        buffered = distance < plan.buffer_m
        role_grid = np.where(buffered, np.uint8(BUFFER), role_grid).astype("uint8")
        block_index = np.where(buffered, np.int32(-1), block_index).astype("int32")

    total = float(height * width)
    role_pixel_share = {
        name: float((role_grid == code).sum()) / total for name, code in ROLE_CODES.items()
    }
    role_pixel_share["buffer"] = float((role_grid == BUFFER).sum()) / total
    role_block_counts = {
        name: int((block_role_flat == code).sum()) for name, code in ROLE_CODES.items()
    }

    plan_dict = plan.to_dict()
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {
                "kind": PARTITION_KIND,
                "seed": seed,
                "ratios": list(ratios),
                "geometry": plan_dict,
                "block_roles": block_role_flat.tolist(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    digest.update(role_grid.tobytes())

    return BlockAssignment(
        role_grid=role_grid,
        block_index=block_index,
        block_roles=block_role_flat.reshape(n_axis, n_axis),
        plan=plan,
        seed=seed,
        ratios=ratios,
        role_pixel_share=role_pixel_share,
        role_block_counts=role_block_counts,
        assignment_sha256=digest.hexdigest(),
    )


def select_dispersed_seed(
    shape: tuple[int, int],
    transform,
    *,
    candidate_seeds: range | None = None,
    **assign_kwargs,
) -> tuple[int, dict[str, dict[str, object]]]:
    """Pick the first seed for which no role collapses into one contiguous patch.

    Seed choice is a genuine hazard here: with only 9 blocks, trying seeds until
    the held-out score looks good would silently turn the holdout into a
    hyperparameter. This selector is safe because it never sees a model, a
    label, or a metric -- it is a pure function of the block geometry, evaluated
    before any training runs, and it stops at the *first* qualifying seed rather
    than optimising anything.

    Returns ``(seed, contiguity_report)``. If no candidate qualifies, the first
    candidate is returned with its report so the caller can record the confound
    instead of silently searching further.
    """

    seeds = candidate_seeds if candidate_seeds is not None else range(16)
    fallback: tuple[int, dict[str, dict[str, object]]] | None = None
    for seed in seeds:
        assignment = assign_spatial_blocks(shape, transform, seed=seed, **assign_kwargs)
        report = assignment.contiguity()
        if fallback is None:
            fallback = (seed, report)
        if not any(entry["single_patch"] for entry in report.values()):
            return seed, report
    if fallback is None:  # pragma: no cover - empty range is a caller error
        raise BlockGeometryError("candidate_seeds was empty.")
    return fallback


def tiles_for_role(
    assignment: BlockAssignment,
    role: str,
    *,
    tile_size: int,
    stride: int,
) -> list[tuple[int, int]]:
    """Return top-left ``(row, col)`` of every tile lying WHOLLY inside ``role``.

    Whole-tile containment is what removes *label* leakage: a training tile can
    never contain a pixel whose label belongs to the held-out role, regardless of
    how the buffer is configured. The buffer removes the weaker *context* leak on
    top of this.
    """

    code = _role_code(role)
    if not isinstance(tile_size, int) or isinstance(tile_size, bool) or tile_size <= 0:
        raise BlockGeometryError(f"tile_size must be a positive int; got {tile_size!r}.")
    if not isinstance(stride, int) or isinstance(stride, bool) or stride <= 0:
        raise BlockGeometryError(f"stride must be a positive int; got {stride!r}.")

    grid = assignment.role_grid
    height, width = grid.shape
    # Integral image of "pixel is not this role" -> O(1) containment test per tile.
    other = (grid != code).astype("int64")
    integral = np.zeros((height + 1, width + 1), dtype="int64")
    np.cumsum(np.cumsum(other, axis=0), axis=1, out=integral[1:, 1:])

    origins: list[tuple[int, int]] = []
    for row in range(0, height - tile_size + 1, stride):
        r1 = row + tile_size
        for col in range(0, width - tile_size + 1, stride):
            c1 = col + tile_size
            impure = (
                integral[r1, c1] - integral[row, c1] - integral[r1, col] + integral[row, col]
            )
            if impure == 0:
                origins.append((row, col))
    return origins


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _greedy_role_assignment(
    n_axis: int,
    sizes: list[int],
    ratios: tuple[float, float, float],
    seed: int,
) -> np.ndarray:
    """Assign blocks to roles by stable hash order, filling the largest deficit.

    Mirrors the determinism contract of
    ``floodguard.label_factory.committee._stable_hash_key``: identical inputs and
    seed must always produce an identical assignment, because the assignment hash
    is what binds a published metric to the partition that produced it.
    """

    order = sorted(
        range(len(sizes)),
        key=lambda bid: (
            hashlib.sha256(
                f"{seed}:{bid // n_axis}:{bid % n_axis}".encode()
            ).hexdigest(),
            bid,
        ),
    )
    targets = np.asarray(ratios, dtype="float64")
    assigned_pixels = np.zeros(3, dtype="float64")
    roles = np.empty(len(sizes), dtype="uint8")
    total = float(sum(sizes)) or 1.0

    for bid in order:
        share = assigned_pixels / total
        # Largest shortfall relative to target; roles with ratio 0 are never chosen.
        deficit = np.where(targets > 0.0, targets - share, -np.inf)
        roles[bid] = int(np.argmax(deficit))
        assigned_pixels[roles[bid]] += float(sizes[bid])

    present = {int(code) for code in np.unique(roles)}
    missing = [
        name for name, code in ROLE_CODES.items() if ratios[code] > 0.0 and code not in present
    ]
    if missing:
        raise BlockGeometryError(
            f"role(s) {missing} received no blocks from {len(sizes)} block(s) at "
            f"ratios {ratios}. Increase the block count or change the ratios."
        )
    return roles


def _role_block_contiguity(block_roles: np.ndarray) -> dict[str, dict[str, object]]:
    """Count 4-connected components of each role in the block grid."""

    n_rows, n_cols = block_roles.shape
    report: dict[str, dict[str, object]] = {}
    for name, code in ROLE_CODES.items():
        member = block_roles == code
        seen = np.zeros_like(member, dtype=bool)
        components = 0
        for start_r in range(n_rows):
            for start_c in range(n_cols):
                if not member[start_r, start_c] or seen[start_r, start_c]:
                    continue
                components += 1
                stack = [(start_r, start_c)]
                seen[start_r, start_c] = True
                while stack:
                    r, c = stack.pop()
                    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nr, nc = r + dr, c + dc
                        if (
                            0 <= nr < n_rows
                            and 0 <= nc < n_cols
                            and member[nr, nc]
                            and not seen[nr, nc]
                        ):
                            seen[nr, nc] = True
                            stack.append((nr, nc))
        n_blocks = int(member.sum())
        report[name] = {
            "n_blocks": n_blocks,
            "n_components": components,
            # One component of >1 block means the role sits in a single
            # geographic patch, so its metric carries a location confound.
            "single_patch": bool(components == 1 and n_blocks > 1),
        }
    return report


def _distance_to_differing_role(
    rects: list[tuple[int, int, int, int]],
    block_roles: np.ndarray,
    shape: tuple[int, int],
    pixel_m_y: float,
    pixel_m_x: float,
) -> np.ndarray:
    """Exact Euclidean metres from each pixel to the nearest differing-role pixel.

    Roles are unions of axis-aligned block rectangles, so the exact distance is
    ``min`` over rectangles of the point-to-rectangle distance -- no distance
    transform and therefore no scipy, which is not in the runner's base
    environment. One pass over blocks maintains a running minimum per role.
    """

    height, width = shape
    ys = (np.arange(height, dtype="float64") + 0.5) * pixel_m_y
    xs = (np.arange(width, dtype="float64") + 0.5) * pixel_m_x

    per_role = {
        code: np.full((height, width), np.inf, dtype="float64") for code in ROLE_CODES.values()
    }

    for bid, (r0, r1, c0, c1) in enumerate(rects):
        top, bottom = r0 * pixel_m_y, r1 * pixel_m_y
        left, right = c0 * pixel_m_x, c1 * pixel_m_x
        dy = np.maximum(np.maximum(top - ys, ys - bottom), 0.0)[:, None]
        dx = np.maximum(np.maximum(left - xs, xs - right), 0.0)[None, :]
        block_distance = np.hypot(dy, dx)
        block_role = int(block_roles[bid])
        for code, running in per_role.items():
            if code != block_role:
                np.minimum(running, block_distance, out=running)

    result = np.full((height, width), np.inf, dtype="float64")
    for bid, (r0, r1, c0, c1) in enumerate(rects):
        result[r0:r1, c0:c1] = per_role[int(block_roles[bid])][r0:r1, c0:c1]
    return result


def _validated_shape(shape: tuple[int, int]) -> tuple[int, int]:
    try:
        height, width = int(shape[0]), int(shape[1])
    except (TypeError, ValueError, IndexError) as exc:
        raise BlockGeometryError(f"shape must be a (height, width) pair; got {shape!r}.") from exc
    if height <= 0 or width <= 0:
        raise BlockGeometryError(f"shape must be positive; got {shape!r}.")
    return height, width


def _validated_ratios(ratios: tuple[float, float, float]) -> tuple[float, float, float]:
    try:
        values = tuple(float(v) for v in ratios)
    except (TypeError, ValueError) as exc:
        raise BlockGeometryError(f"ratios must be three numbers; got {ratios!r}.") from exc
    if len(values) != 3:
        raise BlockGeometryError(f"ratios must have exactly three entries; got {ratios!r}.")
    if any(v < 0.0 or not math.isfinite(v) for v in values):
        raise BlockGeometryError(f"ratios must be finite and non-negative; got {ratios!r}.")
    if abs(sum(values) - 1.0) > 1e-9:
        raise BlockGeometryError(
            f"ratios must sum to 1.0; got {ratios!r} summing to {sum(values)!r}."
        )
    if values[0] <= 0.0:
        raise BlockGeometryError("the train ratio must be positive.")
    return values  # type: ignore[return-value]


def _role_code(role: str) -> int:
    try:
        return ROLE_CODES[role]
    except KeyError as exc:
        raise BlockGeometryError(
            f"unknown role {role!r}; expected one of {sorted(ROLE_CODES)}."
        ) from exc
