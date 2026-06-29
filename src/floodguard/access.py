"""Deterministic access-loss analysis helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
import heapq
import math

import pandas as pd

EDGE_COLUMNS: tuple[str, ...] = (
    "from_node",
    "to_node",
    "normal_minutes",
    "disrupted_minutes",
)

POPULATION_COLUMNS: tuple[str, ...] = (
    "node_id",
    "subdistrict_id",
    "total_population",
    "vulnerable_population",
    "non_vulnerable_population",
)

FACILITY_COLUMNS: tuple[str, ...] = (
    "facility_id",
    "facility_type",
    "node_id",
)

DEFAULT_THRESHOLDS: tuple[int, ...] = (15, 30, 60)


class AccessError(ValueError):
    """Raised when access-loss inputs violate the access contract."""


def calculate_access_loss(
    population: pd.DataFrame,
    edges: pd.DataFrame,
    facilities: pd.DataFrame,
    thresholds: Sequence[int] = DEFAULT_THRESHOLDS,
    facility_types: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Compare normal and disrupted network access by subdistrict.

    A population node counts as losing X-minute access only when it had normal
    access within X minutes and disrupted access is missing or greater than X.
    """

    _validate_columns(population, POPULATION_COLUMNS, "population")
    _validate_columns(edges, EDGE_COLUMNS, "edges")
    _validate_columns(facilities, FACILITY_COLUMNS, "facilities")
    _validate_thresholds(thresholds)

    pop = population.copy()
    edge_frame = edges.copy()
    facility_frame = facilities.copy()

    for column in ("total_population", "vulnerable_population", "non_vulnerable_population"):
        pop[column] = _non_negative_numeric(pop[column], column)

    normal_graph = _build_graph(edge_frame, "normal_minutes", allow_closed=False)
    disrupted_graph = _build_graph(edge_frame, "disrupted_minutes", allow_closed=True)

    selected_facilities = facility_frame
    if facility_types is not None:
        allowed = {facility_type.lower() for facility_type in facility_types}
        selected_facilities = facility_frame[
            facility_frame["facility_type"].astype(str).str.lower().isin(allowed)
        ]
    facility_nodes = set(selected_facilities["node_id"].astype(str))
    if not facility_nodes:
        raise AccessError("At least one facility node is required for access analysis.")

    node_results: list[dict[str, object]] = []
    for _, row in pop.iterrows():
        node = str(row["node_id"])
        normal_minutes = _nearest_facility_minutes(normal_graph, node, facility_nodes)
        disrupted_minutes = _nearest_facility_minutes(disrupted_graph, node, facility_nodes)
        node_record: dict[str, object] = row.to_dict()
        node_record["normal_access_minutes"] = normal_minutes
        node_record["disrupted_access_minutes"] = disrupted_minutes

        for threshold in thresholds:
            loses_access = (
                normal_minutes is not None
                and normal_minutes <= threshold
                and (disrupted_minutes is None or disrupted_minutes > threshold)
            )
            node_record[f"loses_{threshold}_min_access"] = loses_access
        node_results.append(node_record)

    node_frame = pd.DataFrame(node_results)
    group_columns = ["subdistrict_id"]
    if "subdistrict_name" in node_frame.columns:
        group_columns.append("subdistrict_name")

    rows: list[dict[str, object]] = []
    for group_key, group in node_frame.groupby(group_columns, dropna=False, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        output = dict(zip(group_columns, group_key, strict=True))
        output["total_population"] = float(group["total_population"].sum())
        output["total_vulnerable_population"] = float(group["vulnerable_population"].sum())
        output["total_non_vulnerable_population"] = float(
            group["non_vulnerable_population"].sum()
        )

        for threshold in thresholds:
            loss_mask = group[f"loses_{threshold}_min_access"].astype(bool)
            output[f"people_losing_{threshold}_min_access"] = float(
                group.loc[loss_mask, "total_population"].sum()
            )
            output[f"vulnerable_population_losing_{threshold}_min_access"] = float(
                group.loc[loss_mask, "vulnerable_population"].sum()
            )
            output[f"non_vulnerable_population_losing_{threshold}_min_access"] = float(
                group.loc[loss_mask, "non_vulnerable_population"].sum()
            )
        rows.append(output)

    return pd.DataFrame(rows)


def _validate_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    frame_name: str,
) -> None:
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise AccessError(
            f"Missing required {frame_name} column(s): {', '.join(missing)}"
        )


def _validate_thresholds(thresholds: Sequence[int]) -> None:
    if not thresholds:
        raise AccessError("At least one access threshold is required.")
    invalid = [threshold for threshold in thresholds if threshold <= 0]
    if invalid:
        raise AccessError(f"Access thresholds must be positive; invalid: {invalid}")


def _non_negative_numeric(values: pd.Series, column: str) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    invalid = numeric.isna() | (numeric < 0)
    if invalid.any():
        bad_rows = values.index[invalid].tolist()
        raise AccessError(
            f"Column {column} must contain non-negative numeric values; "
            f"invalid row index(es): {bad_rows}"
        )
    return numeric


def _build_graph(
    edges: pd.DataFrame,
    weight_column: str,
    allow_closed: bool,
) -> dict[str, list[tuple[str, float]]]:
    graph: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for index, row in edges.iterrows():
        start = str(row["from_node"])
        end = str(row["to_node"])
        weight = pd.to_numeric(pd.Series([row[weight_column]]), errors="coerce").iloc[0]
        if pd.isna(weight):
            if allow_closed:
                continue
            raise AccessError(
                f"Column {weight_column} must be numeric; invalid row index: {index}"
            )
        minutes = float(weight)
        if minutes < 0:
            raise AccessError(
                f"Column {weight_column} must be non-negative; invalid row index: {index}"
            )
        graph[start].append((end, minutes))
        graph[end].append((start, minutes))
    return dict(graph)


def _nearest_facility_minutes(
    graph: dict[str, list[tuple[str, float]]],
    start_node: str,
    facility_nodes: set[str],
) -> float | None:
    if start_node in facility_nodes:
        return 0.0

    queue: list[tuple[float, str]] = [(0.0, start_node)]
    best: dict[str, float] = {start_node: 0.0}

    while queue:
        minutes, node = heapq.heappop(queue)
        if minutes > best[node]:
            continue
        if node in facility_nodes:
            return minutes
        for neighbor, weight in graph.get(node, []):
            candidate = minutes + weight
            if candidate < best.get(neighbor, math.inf):
                best[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return None
