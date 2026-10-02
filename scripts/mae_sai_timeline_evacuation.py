"""Population, evacuation-access and shelter-siting stages for the Mae Sai flood timeline bake.

Imported by ``scripts/build_mae_sai_flood_timeline.py``. Pure decision logic lives in
``floodguard.evacuation_access``; this module handles I/O and geometry.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import Window, from_bounds as window_from_bounds
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform

from floodguard.evacuation_access import (
    NEVER_LOST,
    NO_BASELINE_ACCESS,
    closure_stage,
    cutoff_levels_for_sets,
    greedy_plan,
    knee_index,
)
from floodguard.flood_timeline import CHANNEL_CODE, HAND_STEP_M, IMPASSABLE_DEPTH_M, NEVER_CODE

ACCESS_THRESHOLD_M = 2000.0  # About a 30-minute walk at 4 km/h: flash-flood evacuation is largely on foot.
EVACUATION_STAGE_M = 0.0  # Pre-emptive evacuation on normal roads (preparedness planning).
LATE_EVACUATION_STAGE_M = 1.0  # Sensitivity: evacuation that starts once the river is 1 m up.
SHELTER_FREEBOARD_M = 0.5
SPHERE_M2_PER_PERSON = 3.5
USABLE_FLOOR_SHARE = 0.5
MAX_PLAN_SITES = 30
SNAP_MAX_M = 400.0
LEVELS = [round(i * 0.05, 2) for i in range(81)]  # 0.00 .. 4.00 m

SITE_AMENITIES = {
    "school": "school", "kindergarten": "school", "college": "school", "university": "school",
    "place_of_worship": "worship", "townhall": "government", "community_centre": "community",
    "social_facility": "community",
}
# OSM amenity=shelter is mostly bus stops, picnic and field huts, so it is not a mass-shelter candidate.
SITE_BUILDINGS = {"temple": "worship", "church": "worship", "mosque": "worship", "school": "school", "university": "school", "college": "school",
                  "government": "government", "public": "government", "civic": "government"}
FACILITY_TYPES = {"school": "school", "community_facility": "community"}


def tag(other_tags: str | None, key: str) -> str | None:
    """Read one key from an OGR OSM ``other_tags`` hstore string."""
    if not isinstance(other_tags, str) or not other_tags:
        return None
    match = re.search(rf'"{re.escape(key)}"=>"([^"]*)"', other_tags)
    return match.group(1) if match else None


def population_grid(worldpop: Path, aoi) -> tuple[np.ndarray, np.ndarray]:
    """Return (people per 100 m cell, people per 10 m AOI cell) from WorldPop.

    Each 100 m UTM cell takes the WorldPop density (people per source cell / source cell area)
    at its centre; sampling by coordinates avoids resampling kernels shifting mass.
    """
    from pyproj import Transformer

    rows_n, cols_n = aoi.height // 10, aoi.width // 10
    xs = aoi.bounds[0] + (np.arange(cols_n) + 0.5) * 100.0
    ys = aoi.bounds[3] - (np.arange(rows_n) + 0.5) * 100.0
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = Transformer.from_crs(aoi.crs, "EPSG:4326", always_xy=True).transform(gx, gy)
    with rasterio.open(worldpop) as src:
        b = transform_bounds(aoi.crs, src.crs, *aoi.bounds, densify_pts=21)
        win = window_from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
        win = Window(win.col_off - 3, win.row_off - 3, win.width + 6, win.height + 6)
        pop = src.read(1, window=win, boundless=True, fill_value=0).astype(np.float64)  # AOI extends north of the raster (20.463N).
        pop = np.where((pop < 0) | (pop == src.nodata) | ~np.isfinite(pop), 0.0, pop)
        transform = src.window_transform(win)
        res_x, res_y = src.res
    inv = ~transform
    col, row = inv * (lon, lat)
    col, row = np.floor(col).astype(int), np.floor(row).astype(int)
    inside = (row >= 0) & (row < pop.shape[0]) & (col >= 0) & (col < pop.shape[1])
    per_cell = np.zeros(lon.shape)
    per_cell[inside] = pop[row[inside], col[inside]]
    cell_m2 = (res_y * 111320.0) * (res_x * 111320.0 * np.cos(np.radians(lat)))
    coarse = per_cell * (1e4 / cell_m2)
    fine = np.kron(coarse, np.ones((10, 10))) / 100.0
    return coarse, fine


def density_codes(coarse: np.ndarray, aoi, water) -> tuple[np.ndarray, float]:
    """Encode people/ha on the water display grid as log1p codes 0..254; returns (codes, max_per_ha)."""
    per_ha = coarse  # A 100 m cell is one hectare.
    dst = np.zeros(water.shape, dtype=np.float32)
    reproject(per_ha.astype(np.float32), dst, src_transform=rasterio.transform.from_origin(aoi.bounds[0], aoi.bounds[3], 100.0, 100.0),
              src_crs=aoi.crs, dst_transform=water.transform, dst_crs=water.crs, resampling=Resampling.bilinear)
    dst = np.clip(dst, 0, None)
    cap = float(np.percentile(dst[dst > 0], 99.5)) if (dst > 0).any() else 1.0
    codes = np.rint(254 * np.log1p(np.clip(dst, 0, cap)) / math.log1p(cap)).astype(np.uint8)
    return codes, round(cap, 2)


def txt(value) -> str:
    """Return ``value`` if it is a non-empty string, else an empty string (pandas uses NaN for missing tags)."""
    return value if isinstance(value, str) else ""


def node_lonlat(node_id: str) -> tuple[float, float]:
    _, lon, lat = node_id.split("-")
    return float(lon), float(lat)


def sample_eff(codes: np.ndarray, kgrid: np.ndarray, grid, xs: np.ndarray, ys: np.ndarray) -> tuple[float | None, float]:
    """Lowest usable effective HAND (m) among samples and the depth factor there (channel/never ignored)."""
    cols = np.floor((xs - grid.bounds[0]) / grid.res).astype(int)
    rows = np.floor((grid.bounds[3] - ys) / grid.res).astype(int)
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    c = codes[rows[inside], cols[inside]]
    k = kgrid[rows[inside], cols[inside]]
    usable = (c != CHANNEL_CODE) & (c != NEVER_CODE)
    if not usable.any():
        return None, 1.0
    i = int(np.argmin(np.where(usable, c.astype(np.int32), 999)))
    return round(float(c[i]) * HAND_STEP_M, 2), round(float(k[i]), 3)


def sample_road(codes: np.ndarray, kgrid: np.ndarray, grid, xs: np.ndarray, ys: np.ndarray) -> tuple[float | None, float]:
    """Lowest effective HAND among samples and an equivalent closure factor.

    Returns ``(h, k)`` such that ``s > h`` means the element is wet somewhere and ``k * (s - h) >= 0.3`` holds
    exactly when some sample reaches the impassable depth: ``h + 0.3 / k = min_i(h_i + 0.3 / k_i)``.
    """
    cols = np.floor((xs - grid.bounds[0]) / grid.res).astype(int)
    rows = np.floor((grid.bounds[3] - ys) / grid.res).astype(int)
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    c = codes[rows[inside], cols[inside]]
    k = kgrid[rows[inside], cols[inside]]
    usable = (c != CHANNEL_CODE) & (c != NEVER_CODE)
    if not usable.any():
        return None, 1.0
    h_i = c[usable].astype(float) * HAND_STEP_M
    close = float(np.min(h_i + IMPASSABLE_DEPTH_M / k[usable]))
    h = float(h_i.min())
    k_eq = IMPASSABLE_DEPTH_M / max(close - h, IMPASSABLE_DEPTH_M)
    return round(h, 2), round(min(k_eq, 1.0), 4)


def build_graph(root: Path, to_utm, codes: np.ndarray, kgrid: np.ndarray, aoi, track=lambda path: path) -> dict:
    """Load the repo road graph, attach closure stages and population nodes.

    ``track`` is called with each input file as it is opened (the bake records them in its input receipt).
    """
    edges = pd.read_csv(track(root / "outputs/mae_sai_access_edges.csv"))
    pop = pd.read_csv(track(root / "outputs/mae_sai_population_nodes.csv"))
    ids = pd.Index(pd.unique(pd.concat([edges["from_node"], edges["to_node"], pop["node_id"]])))
    lonlat = np.array([node_lonlat(n) for n in ids])
    xy = np.array([to_utm(lon, lat) for lon, lat in lonlat])
    u = ids.get_indexer(edges["from_node"])
    v = ids.get_indexer(edges["to_node"])
    close = np.empty(len(edges))
    lengths = np.empty(len(edges))
    for i, (a, b) in enumerate(zip(u, v)):
        length = float(np.hypot(*(xy[b] - xy[a])))
        lengths[i] = length
        steps = np.linspace(0.0, 1.0, max(2, int(length // 10) + 2))
        pts = xy[a] + np.outer(steps, xy[b] - xy[a])
        h, k = sample_road(codes, kgrid, aoi, pts[:, 0], pts[:, 1])
        close[i] = closure_stage(h, k, IMPASSABLE_DEPTH_M)
    pop_index = ids.get_indexer(pop["node_id"])
    home = [sample_eff(codes, kgrid, aoi, np.array([xy[j, 0]]), np.array([xy[j, 1]])) for j in pop_index]
    home_code = np.array([NEVER_CODE if h is None else int(round(h / HAND_STEP_M)) for h, _ in home], dtype=np.uint8)
    # A node on a channel cell is treated as riverside (wet as soon as the stage rises).
    raw = [codes_at(codes, aoi, xy[j, 0], xy[j, 1]) for j in pop_index]
    home_code = np.where(np.array(raw) == CHANNEL_CODE, CHANNEL_CODE, home_code).astype(np.uint8)
    return {"ids": ids, "lonlat": lonlat, "xy": xy, "u": u, "v": v, "minutes": edges["normal_minutes"].to_numpy(float), "length": lengths,
            "close": close, "pop": pop, "pop_index": pop_index, "home_code": home_code,
            "home_k": np.array([k for _, k in home], dtype=float)}


def codes_at(codes: np.ndarray, grid, x: float, y: float) -> int:
    col = int((x - grid.bounds[0]) // grid.res)
    row = int((grid.bounds[3] - y) // grid.res)
    if 0 <= row < grid.height and 0 <= col < grid.width:
        return int(codes[row, col])
    return NEVER_CODE


def home_wet(home_code: np.ndarray, stage: float) -> np.ndarray:
    """Boolean mask of population nodes whose location is wet at ``stage``."""
    code = home_code.astype(int)
    return (code != NEVER_CODE) & (stage > 0) & ((code == CHANNEL_CODE) | (code * HAND_STEP_M < stage))


def shelter_candidates(osm_polygons, osm_points, facilities_path: Path, to_utm) -> list[dict]:
    """Assemble public-building shelter candidates from OSM polygons, points and the repo facility list."""
    buildings = osm_polygons[osm_polygons["building"].map(lambda v: bool(txt(v)) and v != "no")]
    building_geoms = [shp_transform(to_utm, g) for g in buildings.geometry]
    tree_pts = np.array([[g.centroid.x, g.centroid.y] for g in building_geoms]) if building_geoms else np.zeros((0, 2))
    btree = cKDTree(tree_pts) if len(tree_pts) else None
    sites: list[dict] = []

    def footprint(geom_utm) -> float:
        if btree is None:
            return 0.0
        c = geom_utm.centroid
        radius = max(60.0, math.sqrt(geom_utm.area) if geom_utm.area > 0 else 60.0)
        area = 0.0
        for j in btree.query_ball_point([c.x, c.y], radius * 1.5):
            b = building_geoms[j]
            if geom_utm.area > 0 and b.intersects(geom_utm):
                area += b.intersection(geom_utm).area
            elif geom_utm.area == 0 and b.distance(geom_utm) <= 30:
                area += b.area
        return area

    def add(kind: str, name: str, geom_ll, source: str) -> None:
        geom = shp_transform(to_utm, geom_ll)
        point = geom.representative_point() if geom.area > 0 else geom
        for s in sites:
            if s["kind"] == kind and math.hypot(s["x"] - point.x, s["y"] - point.y) < 80:
                return
        area = footprint(geom)
        ll = geom_ll.representative_point() if geom_ll.area > 0 else geom_ll
        sites.append({"kind": kind, "name": name, "x": point.x, "y": point.y, "lon": round(ll.x, 6), "lat": round(ll.y, 6),
                      "source": source, "footprint_m2": round(area), "has_polygon": geom.area > 0})

    for row in osm_polygons.itertuples():
        kind = SITE_AMENITIES.get(txt(row.amenity)) or SITE_BUILDINGS.get(txt(row.building))
        if kind is None and tag(row.other_tags, "office") == "government":
            kind = "government"
        if kind is None or row.geometry is None:
            continue
        osm = f"way/{txt(row.osm_way_id) or row.osm_way_id}" if txt(row.osm_way_id) or isinstance(row.osm_way_id, int) else f"relation/{txt(row.osm_id)}"
        add(kind, txt(row.name), row.geometry, f"OSM {osm}")
    for row in osm_points.itertuples():
        amenity = tag(row.other_tags, "amenity")
        kind = SITE_AMENITIES.get(amenity or "")
        if kind is None and tag(row.other_tags, "office") == "government":
            kind = "government"
        if kind is None:
            continue
        add(kind, txt(row.name), row.geometry, f"OSM node/{txt(row.osm_id)}")
    for f in json.loads(facilities_path.read_text(encoding="utf-8"))["features"]:
        kind = FACILITY_TYPES.get(f["properties"]["facility_type"])
        if kind:
            add(kind, f["properties"].get("facility_name") or "", shape(f["geometry"]), f"OSM {f['properties']['facility_id'].replace('OSM-', 'node/')}")
    for index, site in enumerate(sites):
        site["id"] = f"C{index + 1:03d}"
        cap = site["footprint_m2"] * USABLE_FLOOR_SHARE / SPHERE_M2_PER_PERSON
        site["capacity_est"] = int(cap) if cap >= 1 else None
    return sites


def evaluate_sites(sites: list[dict], graph: dict, codes, kgrid, aoi, peak_stage: float, valid: np.ndarray | None = None) -> None:
    """Attach modelled site height, freeboard at peak, snapped node and eligibility to each site."""
    tree = cKDTree(graph["xy"])
    for s in sites:
        xs = np.array([s["x"] + dx for dx in (-10, 0, 10) for _ in range(3)])
        ys = np.array([s["y"] + dy for _ in range(3) for dy in (-10, 0, 10)])
        cols = np.floor((xs - aoi.bounds[0]) / aoi.res).astype(int)
        rows = np.floor((aoi.bounds[3] - ys) / aoi.res).astype(int)
        inside = (rows >= 0) & (rows < aoi.height) & (cols >= 0) & (cols < aoi.width)
        c = codes[rows[inside], cols[inside]].astype(int)
        k = kgrid[rows[inside], cols[inside]]
        dist, node = tree.query([s["x"], s["y"]])
        s["node"] = int(node)
        s["snap_m"] = round(float(dist))
        modelled = bool(c.size) and (valid is None or bool(valid[rows[inside], cols[inside]].any()))
        s["m"] = modelled
        if not modelled:
            s.update(h=None, k=1.0, flood_stage=0.0, freeboard_m=None)
        elif (c == CHANNEL_CODE).any():
            s.update(h=None, k=1.0, flood_stage=0.0, freeboard_m=None)
        elif (c == NEVER_CODE).all():
            s.update(h=None, k=1.0, flood_stage=float("inf"), freeboard_m=None)
        else:
            usable = c[c != NEVER_CODE]
            h = float(np.median(usable)) * HAND_STEP_M
            kk = float(np.median(k[c != NEVER_CODE]))
            s.update(h=round(h, 2), k=round(kk, 3), flood_stage=h, freeboard_m=round(kk * (h - peak_stage), 2))
        high_ground = s["flood_stage"] == float("inf")
        reasons = []
        if not modelled:
            reasons.append("outside_model")
        elif not high_ground and (s["freeboard_m"] is None or s["freeboard_m"] < SHELTER_FREEBOARD_M):
            reasons.append("floods_or_under_freeboard_at_peak")
        if s["snap_m"] > SNAP_MAX_M:
            reasons.append("no_road_within_400m")
        s["eligible"] = not reasons
        s["ineligible_reasons"] = reasons


def coverage_masks(sites: list[dict], graph: dict, demand_nodes: np.ndarray, stage: float) -> tuple[list[np.ndarray], np.ndarray]:
    """Per eligible site: boolean mask over demand nodes reachable within the threshold at ``stage``."""
    n = len(graph["ids"])
    mask = graph["close"] > stage
    matrix = coo_matrix((np.maximum(graph["length"][mask], 1e-3), (graph["u"][mask], graph["v"][mask])), shape=(n, n)).tocsr()
    nodes = np.array([s["node"] for s in sites], dtype=int)
    dist = dijkstra(matrix, directed=False, indices=nodes, limit=ACCESS_THRESHOLD_M + 1e-6)
    return [np.isfinite(dist[i, demand_nodes]) & (dist[i, demand_nodes] <= ACCESS_THRESHOLD_M + 1e-6) for i in range(len(sites))], dist


def plan_and_access(sites: list[dict], reported: list[dict], graph: dict, peak_stage: float) -> dict:
    """Rank eligible candidates by greedy coverage and compute per-node cut-off levels for every set."""
    pop = graph["pop"]
    demand_mask = home_wet(graph["home_code"], peak_stage)
    demand_nodes = graph["pop_index"][demand_mask]
    demand_weight = pop["total_population"].to_numpy(float)[demand_mask]
    eligible = [s for s in sites if s["eligible"]]
    masks, dist = coverage_masks(eligible, graph, demand_nodes, EVACUATION_STAGE_M)
    ranking = greedy_plan(demand_weight, masks, MAX_PLAN_SITES)
    for entry in ranking:
        entry["candidate_id"] = eligible[entry.pop("candidate")]["id"]
    order = [next(i for i, s in enumerate(eligible) if s["id"] == e["candidate_id"]) for e in ranking]
    # Load check: each covered demand node goes to its nearest selected site, for every plan size k.
    for k in range(1, len(order) + 1):
        chosen = order[:k]
        d = dist[np.ix_(chosen, demand_nodes)]
        nearest = np.argmin(np.where(np.isfinite(d), d, np.inf), axis=0)
        ok = np.isfinite(d.min(axis=0)) & (d.min(axis=0) <= ACCESS_THRESHOLD_M + 1e-6)
        loads = np.bincount(nearest[ok], weights=demand_weight[ok], minlength=k)
        ranking[k - 1]["loads"] = [round(float(x)) for x in loads]
    uncoverable = float(demand_weight[~np.any(np.array(masks), axis=0)].sum()) if masks else float(demand_weight.sum())
    late_masks, _ = coverage_masks(eligible, graph, demand_nodes, LATE_EVACUATION_STAGE_M)
    for k in range(1, len(order) + 1):
        late = np.any(np.array([late_masks[i] for i in order[:k]]), axis=0)
        ranking[k - 1]["late_cumulative_share"] = round(float(demand_weight[late].sum()) / float(demand_weight.sum()), 4)

    sets = []
    if reported:
        sets.append(("reported_2024", [r["node"] for r in reported], [r["flood_stage"] for r in reported]))
    for k in range(1, len(order) + 1):
        chosen = [eligible[i] for i in order[:k]]
        sets.append((f"plan_{k}", [s["node"] for s in chosen], [s["flood_stage"] for s in chosen]))
    codes = cutoff_levels_for_sets(len(graph["ids"]), graph["u"], graph["v"], graph["length"], graph["close"],
                                   [(n, f) for _, n, f in sets], LEVELS, ACCESS_THRESHOLD_M)
    node_codes = codes[:, graph["pop_index"]]
    return {"ranking": ranking, "knee_k": knee_index(ranking, 0.9), "set_ids": [s[0] for s in sets], "node_codes": node_codes,
            "demand_people": round(float(demand_weight.sum())), "uncoverable_people": round(uncoverable),
            "eligible_count": len(eligible)}


def lost_at(node_codes_row: np.ndarray, stage: float) -> np.ndarray:
    """Nodes that have lost access at ``stage`` (had baseline access)."""
    code = node_codes_row.astype(int)
    level_index = int(math.floor(stage / 0.05 + 1e-6))
    return (code != NEVER_LOST) & (code != NO_BASELINE_ACCESS) & (code <= level_index)
