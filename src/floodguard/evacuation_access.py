"""Stage-dependent evacuation access and shelter-plan ranking for flood replays.

All functions work on a road graph whose edges close once the reconstructed water
depth on them reaches the impassable threshold, and on shelters that stop being
usable once water reaches the site. Everything here is a planning scenario on a
modelled flood, not an observation of who was actually cut off.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

NEVER_LOST = 254
"""Cut-off code for nodes that keep access at every evaluated level."""

NO_BASELINE_ACCESS = 255
"""Cut-off code for nodes without access even before flooding (level 0)."""


def closure_stage(min_hand_eff: float | None, depth_factor: float, impassable_depth_m: float = 0.3) -> float:
    """Return the stage at which a road element becomes impassable (``inf`` if never).

    Depth on the element is ``depth_factor * (stage - min_hand_eff)``, so it closes
    once ``stage >= min_hand_eff + impassable_depth_m / depth_factor``.
    """
    if min_hand_eff is None or not np.isfinite(min_hand_eff) or depth_factor <= 0:
        return float("inf")
    return round(float(min_hand_eff) + impassable_depth_m / float(depth_factor), 6)


def reachable_within(
    n_nodes: int,
    edge_u: np.ndarray,
    edge_v: np.ndarray,
    edge_minutes: np.ndarray,
    open_edges: np.ndarray,
    sources: Sequence[int],
    threshold_minutes: float,
) -> np.ndarray:
    """Return a boolean mask of nodes within ``threshold_minutes`` of any source over open edges."""
    reached = np.zeros(n_nodes, dtype=bool)
    if len(sources) == 0:
        return reached
    mask = np.asarray(open_edges, dtype=bool)
    # Zero-length edges would vanish from a sparse matrix; give them a tiny positive weight.
    weights = np.maximum(np.asarray(edge_minutes, dtype=float)[mask], 1e-6)
    graph = coo_matrix((weights, (edge_u[mask], edge_v[mask])), shape=(n_nodes, n_nodes)).tocsr()
    dist = dijkstra(graph, directed=False, indices=np.unique(np.asarray(sources, dtype=int)), min_only=True,
                    limit=threshold_minutes + 1e-9)
    reached[np.isfinite(dist) & (dist <= threshold_minutes + 1e-9)] = True
    return reached


def cutoff_levels(
    n_nodes: int,
    edge_u: np.ndarray,
    edge_v: np.ndarray,
    edge_minutes: np.ndarray,
    edge_close_stage: np.ndarray,
    shelter_nodes: Sequence[int],
    shelter_flood_stage: Sequence[float],
    levels: Sequence[float],
    threshold_minutes: float,
) -> np.ndarray:
    """Return, per node, the index into ``levels`` at which it first loses shelter access.

    ``levels[0]`` is the baseline. Nodes without baseline access get
    ``NO_BASELINE_ACCESS``; nodes that never lose access get ``NEVER_LOST``.
    Access is monotone in stage (edges only close, shelters only flood), so the
    first loss is final.
    """
    if len(levels) > NEVER_LOST:
        raise ValueError("at most 254 levels are supported")
    close = np.asarray(edge_close_stage, dtype=float)
    shelters = np.asarray(shelter_nodes, dtype=int)
    flood = np.asarray(shelter_flood_stage, dtype=float)
    codes = np.full(n_nodes, NEVER_LOST, dtype=np.uint8)
    baseline = None
    for index, level in enumerate(levels):
        open_edges = close > level
        active = shelters[flood > level]
        reached = reachable_within(n_nodes, edge_u, edge_v, edge_minutes, open_edges, active, threshold_minutes)
        if baseline is None:
            baseline = reached
            codes[~baseline] = NO_BASELINE_ACCESS
            continue
        newly_lost = baseline & ~reached & (codes == NEVER_LOST)
        codes[newly_lost] = index
    return codes


def cutoff_levels_for_sets(
    n_nodes: int,
    edge_u: np.ndarray,
    edge_v: np.ndarray,
    edge_minutes: np.ndarray,
    edge_close_stage: np.ndarray,
    shelter_sets: Sequence[tuple[Sequence[int], Sequence[float]]],
    levels: Sequence[float],
    threshold_minutes: float,
) -> np.ndarray:
    """Vectorised :func:`cutoff_levels` for several shelter sets; returns ``(n_sets, n_nodes)`` codes.

    The graph is rebuilt once per level and shared by every set.
    """
    if len(levels) > NEVER_LOST:
        raise ValueError("at most 254 levels are supported")
    close = np.asarray(edge_close_stage, dtype=float)
    weights_all = np.maximum(np.asarray(edge_minutes, dtype=float), 1e-6)
    codes = np.full((len(shelter_sets), n_nodes), NEVER_LOST, dtype=np.uint8)
    baselines: list[np.ndarray] = []
    for index, level in enumerate(levels):
        mask = close > level
        graph = coo_matrix((weights_all[mask], (edge_u[mask], edge_v[mask])), shape=(n_nodes, n_nodes)).tocsr()
        for set_index, (nodes, flood_stage) in enumerate(shelter_sets):
            nodes_arr = np.asarray(nodes, dtype=int)
            active = np.unique(nodes_arr[np.asarray(flood_stage, dtype=float) > level])
            reached = np.zeros(n_nodes, dtype=bool)
            if active.size:
                dist = dijkstra(graph, directed=False, indices=active, min_only=True, limit=threshold_minutes + 1e-9)
                reached = np.isfinite(dist) & (dist <= threshold_minutes + 1e-9)
            if index == 0:
                baselines.append(reached)
                codes[set_index, ~reached] = NO_BASELINE_ACCESS
                continue
            row = codes[set_index]
            row[baselines[set_index] & ~reached & (row == NEVER_LOST)] = index
    return codes


def greedy_plan(
    demand: np.ndarray,
    coverage: Sequence[np.ndarray],
    max_sites: int,
    min_gain_share: float = 0.005,
) -> list[dict]:
    """Rank candidate sites by greedy maximal coverage of ``demand``.

    ``coverage[j]`` is a boolean mask of demand nodes that candidate ``j`` serves.
    Each step adds the site with the largest newly covered demand (ties go to the
    lower index). The ranking stops at ``max_sites`` or when the best gain falls
    below ``min_gain_share`` of total demand. Greedy is the standard (1 - 1/e)
    approximation for the maximal covering location problem and gives nested
    plans: the first ``k`` entries are the plan for ``k`` shelters.
    """
    weights = np.asarray(demand, dtype=float)
    total = float(weights.sum())
    covered = np.zeros(weights.shape, dtype=bool)
    remaining = list(range(len(coverage)))
    ranking: list[dict] = []
    while remaining and len(ranking) < max_sites:
        gains = [float(weights[np.asarray(coverage[j], dtype=bool) & ~covered].sum()) for j in remaining]
        best_pos = int(np.argmax(gains))
        best_gain = gains[best_pos]
        if total <= 0 or best_gain <= 0 or best_gain < min_gain_share * total:
            break
        site = remaining.pop(best_pos)
        covered |= np.asarray(coverage[site], dtype=bool)
        ranking.append({
            "candidate": site,
            "marginal_demand": round(best_gain, 1),
            "cumulative_demand": round(float(weights[covered].sum()), 1),
            "cumulative_share": round(float(weights[covered].sum()) / total, 4) if total else 0.0,
        })
    return ranking


def knee_index(ranking: Sequence[dict], share_of_best: float = 0.9) -> int | None:
    """Return the smallest plan size reaching ``share_of_best`` of the final coverage (1-based)."""
    if not ranking:
        return None
    best = ranking[-1]["cumulative_demand"]
    for position, entry in enumerate(ranking, start=1):
        if entry["cumulative_demand"] >= share_of_best * best:
            return position
    return len(ranking)
