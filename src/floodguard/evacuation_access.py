"""Stage-dependent evacuation access and shelter-plan ranking for flood replays.

All functions work on a road graph whose edges close once the reconstructed water
depth on them reaches the impassable threshold, and on shelters that stop being
usable once water reaches the site. The capacity-aware plan then asks who fits:
residents are assigned to sites within the walking limit without loading a site
beyond its capacity, under a lower and an upper capacity bound. Everything here
is a planning scenario on a modelled flood, not an observation of who was
actually cut off or sheltered; no priority score and no action class is computed.
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


# --- Capacity-aware plan -------------------------------------------------------------------------------

PEOPLE_UNIT = 0.001
"""Assignments are solved in whole thousandths of a resident, so every flow and every total is exact."""

CAPACITY_BASES = ("estimate", "kind_median", "all_kinds_median", "none")
"""Where a site's upper-bound capacity comes from (see :func:`capacity_bounds`)."""


def capacity_bounds(capacities: Sequence[float | None], kinds: Sequence[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return ``(lower, upper, basis)`` capacities per site for sites whose capacity may be unknown (``None``).

    A known capacity is used as it is in both bounds (basis ``"estimate"``). An unknown one counts as 0 in the
    lower bound; in the upper bound it takes the median of the known capacities of the same site kind, rounded
    down (``"kind_median"``), or the median over every known capacity when no site of that kind has one
    (``"all_kinds_median"``), or 0 when nothing is known at all (``"none"``). Neither bound is a measurement: the
    upper one says "if the unmapped sites are typical of their kind", the lower one "if they hold nobody".
    """
    if len(capacities) != len(kinds):
        raise ValueError("capacities and kinds must have the same length")
    known = [None if c is None else float(c) for c in capacities]
    if any(c is not None and (not np.isfinite(c) or c < 0) for c in known):
        raise ValueError("a known capacity must be a finite number that is not negative")
    by_kind: dict[str, list[float]] = {}
    for capacity, kind in zip(known, kinds):
        if capacity is not None:
            by_kind.setdefault(kind, []).append(capacity)
    everything = [c for values in by_kind.values() for c in values]
    lower = np.zeros(len(known))
    upper = np.zeros(len(known))
    basis: list[str] = []
    for index, (capacity, kind) in enumerate(zip(known, kinds)):
        if capacity is not None:
            lower[index] = upper[index] = capacity
            basis.append("estimate")
        elif kind in by_kind:
            upper[index] = float(np.floor(np.median(by_kind[kind])))
            basis.append("kind_median")
        elif everything:
            upper[index] = float(np.floor(np.median(everything)))
            basis.append("all_kinds_median")
        else:
            basis.append("none")
    return lower, upper, basis


def _people_units(values: Sequence[float] | np.ndarray, what: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all() or (array < 0).any():
        raise ValueError(f"{what} must be a one-dimensional array of finite numbers that are not negative")
    return np.rint(array / PEOPLE_UNIT).astype(np.int64)


def _reach_nodes(reach: Sequence[np.ndarray], demand_units: np.ndarray) -> list[np.ndarray]:
    nodes = []
    for mask in reach:
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != demand_units.shape:
            raise ValueError("every reach mask must have one entry per demand node")
        nodes.append(np.flatnonzero(mask & (demand_units > 0)))
    return nodes


def _max_flow(demand_units: np.ndarray, nodes: Sequence[np.ndarray], capacity_units: np.ndarray, sites: Sequence[int]):
    """Maximum flow source -> sites -> demand nodes -> sink; returns ``(scipy result, used sites, first node index)``."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import maximum_flow

    used = [int(s) for s in sites if capacity_units[s] > 0 and nodes[s].size]
    first = 1 + len(used)
    sink = first + demand_units.size
    if not used:
        return None, used, first
    wanted = np.unique(np.concatenate([nodes[s] for s in used]))
    rows = [np.zeros(len(used), dtype=np.int64)]
    cols = [np.arange(1, first, dtype=np.int64)]
    data = [capacity_units[used]]
    for position, site in enumerate(used, start=1):
        rows.append(np.full(nodes[site].size, position, dtype=np.int64))
        cols.append(first + nodes[site])
        data.append(np.minimum(demand_units[nodes[site]], capacity_units[site]))
    rows.append(first + wanted)
    cols.append(np.full(wanted.size, sink, dtype=np.int64))
    data.append(demand_units[wanted])
    graph = csr_matrix((np.concatenate(data).astype(np.int32), (np.concatenate(rows), np.concatenate(cols))), shape=(sink + 1, sink + 1))
    return maximum_flow(graph, 0, sink), used, first


def _served_units(demand_units: np.ndarray, nodes: Sequence[np.ndarray], capacity_units: np.ndarray, sites: Sequence[int]) -> int:
    result, _, _ = _max_flow(demand_units, nodes, capacity_units, sites)
    return 0 if result is None else int(result.flow_value)


def _checked_units(demand: np.ndarray, reach: Sequence[np.ndarray], *capacities: Sequence[float]) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray]]:
    demand_units = _people_units(demand, "demand")
    capacity_units = [_people_units(capacity, "capacity") for capacity in capacities]
    if any(units.size != len(reach) for units in capacity_units):
        raise ValueError("capacity needs one value per candidate site")
    if int(demand_units.sum()) > np.iinfo(np.int32).max or any(int(units.max(initial=0)) > np.iinfo(np.int32).max for units in capacity_units):
        raise ValueError("demand or capacity is too large to solve in thousandths of a resident")
    return demand_units, _reach_nodes(reach, demand_units), capacity_units


def _people(units: int | np.integer) -> float:
    return round(int(units) * PEOPLE_UNIT, 3)


def capacitated_assignment(demand: np.ndarray, reach: Sequence[np.ndarray], capacity: Sequence[float]) -> dict:
    """Assign residents to sites they can reach without exceeding any site's capacity, serving as many as possible.

    ``reach[j]`` is a boolean mask of the demand nodes within the walking limit of site ``j`` and ``capacity[j]``
    the places it has. The result holds ``demand``, ``served`` and ``overflow`` (``demand - served``: residents
    with no site in reach or no place left), the ``loads`` per site and the ``flows`` as
    ``(site, demand node, residents)`` rows. ``served`` is the unique maximum; which residents go where is one of
    possibly many assignments that reach it. Solved as a maximum flow in whole thousandths of a resident.
    """
    demand_units, nodes, (capacity_units,) = _checked_units(demand, reach, capacity)
    total = int(demand_units.sum())
    result, used, first = _max_flow(demand_units, nodes, capacity_units, range(len(reach)))
    loads = np.zeros(len(reach), dtype=np.int64)
    flows: list[tuple[int, int, float]] = []
    if result is not None:
        flow = result.flow.tocoo()
        for row, col, value in zip(flow.row, flow.col, flow.data):
            if 1 <= row < first and col >= first and value > 0:
                site = used[row - 1]
                loads[site] += int(value)
                flows.append((site, int(col - first), _people(value)))
    served = int(loads.sum())
    return {"demand": _people(total), "served": _people(served), "overflow": _people(total - served),
            "loads": [_people(load) for load in loads], "flows": sorted(flows)}


def capacitated_plan(
    demand: np.ndarray,
    reach: Sequence[np.ndarray],
    capacity_lower: Sequence[float],
    capacity_upper: Sequence[float],
    max_sites: int,
    min_gain_share: float = 0.0,
    order: Sequence[int] | None = None,
) -> dict:
    """Rank candidate sites by how many more residents fit when each is added, under two capacity bounds.

    ``demand`` is residents per demand node, ``reach[j]`` the boolean mask of demand nodes within the walking
    limit of candidate ``j``. ``capacity_lower`` and ``capacity_upper`` are the two capacity bounds per candidate
    (see :func:`capacity_bounds`); the lower may not exceed the upper anywhere.

    One site order serves both bounds, so they describe the same sites. Each step adds the site with the largest
    gain in residents served under the upper bound; ties go to the larger gain under the lower bound, then to
    the lower index. Ranking stops at ``max_sites`` or when the best upper-bound gain is zero or below
    ``min_gain_share`` of total demand. With ``order`` the sites are taken in that order instead (to count what an
    existing ranking can hold) and nothing stops early. Either way the plans are nested: the first ``k`` entries
    are the plan for ``k`` sites.

    Served residents are a maximum flow (see :func:`capacitated_assignment`), which never loads a site beyond its
    capacity and never falls when a site is added, so the gains shrink step by step and each site's ``load`` can
    be taken as the gain it brought: those loads are one valid assignment for every plan size. Because the lower
    capacities never exceed the upper ones, ``served`` under the lower bound never exceeds ``served`` under the
    upper bound.

    Returns ``{"demand", "ranking"}``; each ranking entry has ``candidate``, ``within_reach`` (residents within
    the walking limit of the plan so far, capacity ignored) and, for ``"lower"`` and ``"upper"``: ``capacity``,
    ``load``, ``served`` (cumulative) and ``overflow`` (``demand - served``).
    """
    demand_units, nodes, (lower_units, upper_units) = _checked_units(demand, reach, capacity_lower, capacity_upper)
    if (lower_units > upper_units).any():
        raise ValueError("the lower capacity bound exceeds the upper bound for at least one site")
    total = int(demand_units.sum())
    n_sites = len(reach)
    chosen: list[int] = []
    served = {"lower": 0, "upper": 0}
    covered = np.zeros(demand_units.size, dtype=bool)
    ranking: list[dict] = []

    def gain(units: np.ndarray, key: str, site: int) -> int:
        return _served_units(demand_units, nodes, units, [*chosen, site]) - served[key]

    def add(site: int, upper_gain: int, lower_gain: int) -> None:
        chosen.append(site)
        covered[nodes[site]] = True
        entry: dict = {"candidate": site, "within_reach": _people(demand_units[covered].sum())}
        for key, units, step in (("lower", lower_units, lower_gain), ("upper", upper_units, upper_gain)):
            served[key] += step
            entry[key] = {"capacity": _people(units[site]), "load": _people(step), "served": _people(served[key]),
                          "overflow": _people(total - served[key])}
        ranking.append(entry)

    if order is not None:
        sites = [int(site) for site in order]
        if len(set(sites)) != len(sites) or any(not 0 <= site < n_sites for site in sites):
            raise ValueError("order must name each candidate at most once")
        for site in sites[:max_sites]:
            add(site, gain(upper_units, "upper", site), gain(lower_units, "lower", site))
        return {"demand": _people(total), "ranking": ranking}

    # A site alone serves min(capacity, demand in reach); gains only shrink as the plan grows, so that is an upper
    # limit on every later gain and a stale limit can be refreshed only when it reaches the top (lazy greedy).
    limit = np.array([min(int(upper_units[j]), int(demand_units[nodes[j]].sum())) for j in range(n_sites)], dtype=np.int64)
    remaining = set(range(n_sites))
    floor_units = min_gain_share * total
    while remaining and len(ranking) < max_sites:
        fresh: dict[int, tuple[int, int]] = {}
        best: int | None = None
        while best is None:
            top = max(limit[j] for j in remaining)
            if top <= 0:
                break
            tied = sorted(j for j in remaining if limit[j] == top)
            stale = [j for j in tied if j not in fresh]
            if stale:
                for j in stale:
                    fresh[j] = (gain(upper_units, "upper", j), gain(lower_units, "lower", j))
                    limit[j] = fresh[j][0]
                continue
            best = min(tied, key=lambda j: (-fresh[j][1], j))
        if best is None or fresh[best][0] <= 0 or fresh[best][0] < floor_units:
            break
        remaining.discard(best)
        add(best, *fresh[best])
    return {"demand": _people(total), "ranking": ranking}


def robust_core(rankings: Sequence[Sequence[str]], k: int) -> list[str]:
    """Return the sites among the first ``k`` entries of every ranking, in the order of the first ranking.

    Each ranking is a nested plan for one what-if design stage; a ranking shorter than ``k`` counts in full.
    A site in this core is chosen whichever of the stages is assumed. The stages are what-if levels around an
    illustrative peak, not return periods.
    """
    if k < 1 or not rankings:
        return []
    heads = [set(list(ranking)[:k]) for ranking in rankings[1:]]
    return [site for site in list(rankings[0])[:k] if all(site in head for head in heads)]
