"""The second class reading of case SE1: triggers B, C and D of class rule v2, which no stage had evaluated.

Class rule v2 (protocol v1a, proposal section 5.2) is a labelled secondary axis. It is never binding. The
published result file of case SE1 says ``not_evaluated`` for it, because three of its triggers needed stages
nobody had run. This script runs them as protocol v1b ``class_rule_v2_inputs`` defines them:

* B: each top-20 critical link that crosses the flood extent is closed on its own; the trigger is met when at
  least 500 residents of the unit who had a vehicle route to a hospital or a main-road entry lose every route.
* C: a hospital or a located DDPM shelter serves a unit when it is the baseline-nearest of its kind for at least
  100 of the unit's residents; the trigger is met when such a facility lies inside the flood extent or loses
  every vehicle route, the planning score is 35 or more and the confidence is not low.
* D: the recurrence flag is set when at least 20 percent of the unit's land outside permanent water has a JRC
  surface-water occurrence of 25 percent or more; the same test at 10 and 30 percent is reported beside it.

Report-only. The published result file is not changed. The binding class of every tambon stays that of class
rule v1. Everything is modelled from a scenario; nothing here is an official warning.

Example::

    python scripts/build_class_v2_reading.py --external-root <external-data-root>
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard import access_diff, flood_inputs  # noqa: E402
from floodguard import class_v2_reading as v2  # noqa: E402

OUTPUT = "outputs/class_v2_reading/se1_mae_sai_v1.json"
OVERLAY = "outputs/planning_v1/overlays/planning_assessment_overlay_se1_mae_sai.json"
TOP_LINKS = "outputs/planning_v1/critical_links_top20_se1_vehicle.geojson"
JRC_LOCAL = Path("open_context") / "jrc_global_surface_water" / "occurrence_90E_30Nv1_4_2021.tif"
JRC_EAST_URL = "https://storage.googleapis.com/global-surface-water/downloads2021/occurrence/occurrence_100E_30Nv1_4_2021.tif"
WORLDCOVER = Path("open_context") / "esa_worldcover" / "ESA_WorldCover_10m_2021_v200_N18E099_Map.tif"
LEVEL = "central"


def load_script(name: str) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"scripts/{name}.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sheet = load_script("build_ko_chang_road_sheet")


def recurrence_shares(external: Path, units: list[tuple[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per unit: the share of its land outside permanent water with a JRC occurrence of 25 percent or more."""

    import rasterio
    from rasterio.features import rasterize
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import from_bounds

    result: dict[str, dict[str, Any]] = {}
    sources = [("on disk", str(external / JRC_LOCAL)), ("read from the provider", JRC_EAST_URL)]
    with rasterio.open(external / WORLDCOVER) as cover:
        for unit_id, geometry in units:
            land_cells, wet_cells, read = 0, 0, []
            for label, address in sources:
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="4"):
                    with rasterio.open(address) as occurrence:
                        west, south, east, north = geometry.bounds
                        left, bottom, right, top = occurrence.bounds
                        if east <= left or west >= right or north <= bottom or south >= top:
                            continue
                        window = from_bounds(max(west, left), max(south, bottom), min(east, right), min(north, top),
                                             transform=occurrence.transform).round_offsets().round_lengths()
                        values = occurrence.read(1, window=window)
                        transform = occurrence.window_transform(window)
                        crs = occurrence.crs
                inside = rasterize([(geometry, 1)], out_shape=values.shape, transform=transform, fill=0, dtype="uint8").astype(bool)
                classes = np.zeros(values.shape, dtype="uint8")
                reproject(rasterio.band(cover, 1), classes, dst_transform=transform, dst_crs=crs, resampling=Resampling.nearest)
                land = inside & (classes != 80) & (classes != 0) & (values != 255)
                land_cells += int(land.sum())
                wet_cells += int((land & (values >= v2.JRC_OCCURRENCE_MIN_PERCENT)).sum())
                read.append(label)
            result[unit_id] = {"land_cells_outside_permanent_water": land_cells, "cells_with_occurrence_of_25_percent_or_more": wet_cells,
                               "share": round(wet_cells / land_cells, 6) if land_cells else None, "tiles": read}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--external-root", required=True)
    arguments = parser.parse_args()
    external = Path(arguments.external_root)

    import shapely
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components, dijkstra

    bad = sheet.load_script("build_access_diff")
    docs = sheet.DOCS
    rules = flood_inputs.load_rules(docs / "planning_protocol_v1a.json", docs / "planning_protocol_v1b.json", docs / "RECEIPTS.jsonl")
    v1b = json.loads((docs / "planning_protocol_v1b.json").read_text(encoding="utf-8"))
    closure = access_diff.closure_arguments(v1b)
    context, _record = bad.load_vehicle_context(v1b, external, bad.OUTPUT_DIR, ROOT)
    graph = bad.mode_graph(access_diff.VEHICLE, context)
    units, _summary = bad.read_units(external / bad.BOUNDARY_RELATIVE_PATH, rules.reporting_units)
    unit_ids = [unit_id for unit_id, _geometry in units]
    assignment = access_diff.assign_cells(graph.population, units)

    extent_path = external / sheet.SEASON_EXTENT
    extent_sha = sheet.sha256_file(extent_path)
    if extent_sha not in (ROOT / sheet.E1_RECEIPT).read_text(encoding="utf-8"):
        raise sheet.BuildError("the season extent is not the layer the committed E1 receipt binds")
    extent_metres, _properties = flood_inputs.decode_layer(extent_path.read_bytes())
    extent = flood_inputs.project(extent_metres, flood_inputs.ANALYSIS_CRS, flood_inputs.WGS84_CRS)
    cache = external / sheet.WORK / f"edge_intersections_{extent_sha[:16]}.json"
    if not cache.exists():
        raise sheet.BuildError("run scripts/build_ko_chang_road_sheet.py first: it caches the edge intersections")
    intersections = json.loads(cache.read_text(encoding="utf-8"))
    crossing = {row["edge_id"] for row in intersections if float(row.get("intersection_length_m") or 0) > 0}

    destination_nodes = {row["node_id"] for name in (access_diff.HOSPITAL, access_diff.MAIN_ROAD_ENTRY) for row in graph.destinations[name]}
    network = sheet.Network(graph.edges, destination_nodes)
    count = len(network.index)
    node_residents = {unit_id: np.zeros(count) for unit_id in unit_ids}
    for row in graph.population:
        unit_id = assignment[row["population_id"]]["unit_id"]
        snap = row.get("snap_distance_m")
        if unit_id in node_residents and row.get("node_id") in network.index and snap is not None and snap <= sheet.POPULATION_SNAP_LIMIT_M:
            node_residents[unit_id][network.index[row["node_id"]]] += float(row["total_population"])
    all_open = np.ones(len(graph.edges), dtype=bool)
    served_before = network.with_a_route(all_open)

    # --- trigger B: each top-20 link that crosses the extent, closed on its own --------------------------------
    links = [feature["properties"] for feature in json.loads((ROOT / TOP_LINKS).read_text(encoding="utf-8"))["features"]]
    link_rows = []
    isolated_most = {unit_id: 0.0 for unit_id in unit_ids}
    for link in sorted(links, key=lambda item: item["rank"]):
        edge_id = link["edge_id"]
        inside = edge_id in crossing
        row = {"rank": link["rank"], "edge_id": edge_id, "osm_way_id": link["osm_way_id"], "road_class": link["road_class"],
               "crosses_the_flood_extent": inside}
        if inside:
            trial = all_open.copy()
            trial[network.position[edge_id]] = False
            served = network.with_a_route(trial)
            lost = {unit_id: float(node_residents[unit_id][served_before & ~served].sum()) for unit_id in unit_ids}
            row["residents_who_lose_every_route_by_unit"] = {unit_id: round(value, 1) for unit_id, value in lost.items() if value > 0}
            for unit_id, value in lost.items():
                isolated_most[unit_id] = max(isolated_most[unit_id], value)
        link_rows.append(row)

    # --- trigger C: the facilities that serve each unit ---------------------------------------------------------
    start, end = network.start, network.end
    minutes = np.array([float(edge["normal_minutes"]) for edge in graph.edges])
    matrix = coo_matrix((np.concatenate([minutes, minutes]), (np.concatenate([start, end]), np.concatenate([end, start]))), shape=(count, count)).tocsr()
    _changed, applied = access_diff.flooded_edges(LEVEL, graph.edges, intersections, flood_input_id="season_layer", arguments=closure)
    closed = set(applied["closed_edge_ids"])
    flooded_open = np.array([edge_id not in closed for edge_id in network.edge_ids], dtype=bool)
    open_matrix = coo_matrix((np.ones(int(flooded_open.sum()), dtype="int8"), (start[flooded_open], end[flooded_open])), shape=(count, count))
    _parts, labels = connected_components(open_matrix, directed=False)
    entry_nodes = [network.index[row["node_id"]] for row in graph.destinations[access_diff.MAIN_ROAD_ENTRY] if row["node_id"] in network.index]
    parts_with_an_entry = set(labels[entry_nodes].tolist())
    facility_points = {str(row["facility_id"]): row for row in context["facilities"]}
    kinds = {"hospital": graph.destinations[access_diff.HOSPITAL], "located_ddpm_shelter": bad.shelter_destinations(context)}
    serving: dict[str, list[dict[str, Any]]] = {unit_id: [] for unit_id in unit_ids}
    facility_counts = {}
    for kind, rows in kinds.items():
        usable = [row for row in rows if row["node_id"] in network.index]
        facility_counts[kind] = len(usable)
        if not usable:
            continue
        sources = [network.index[row["node_id"]] for row in usable]
        distance = dijkstra(matrix, directed=False, indices=sources)
        connector = np.array([float(row["snap_distance_m"]) / 1000 / access_diff.CONNECTOR_SPEED_KMH * 60 for row in usable])
        total = distance + connector[:, None]
        nearest = np.where(np.isfinite(total).any(axis=0), np.argmin(total, axis=0), -1)
        for position, row in enumerate(usable):
            record = facility_points.get(str(row["facility_id"]), {})
            lon, lat = record.get("longitude"), record.get("latitude")
            inside = bool(lon is not None and lat is not None and shapely.contains(extent, shapely.Point(float(lon), float(lat))))
            cut_off = int(labels[sources[position]]) not in parts_with_an_entry
            for unit_id in unit_ids:
                residents = float(node_residents[unit_id][nearest == position].sum())
                if residents >= v2.SERVED_RESIDENTS_MIN:
                    serving[unit_id].append({"kind": kind, "facility_id": str(row["facility_id"]),
                                             "residents_of_the_unit_it_is_nearest_for": round(residents, 1),
                                             "point_inside_the_flood_extent": inside,
                                             "no_vehicle_route_to_a_main_road_entry_in_the_flooded_run": cut_off})

    # --- trigger D: the recurrence flag --------------------------------------------------------------------------
    recurrence = recurrence_shares(external, units)

    overlay = json.loads((ROOT / OVERLAY).read_text(encoding="utf-8"))
    rows_out = {}
    for row in overlay["rows"]:
        unit_id = row["unit_id"]
        earlier = {item["trigger"]: item["met"] for item in row["class_v2"]["trigger_evidence"]}
        facilities = serving[unit_id]
        share = recurrence[unit_id]["share"]
        triggers = v2.evaluate(
            met_e=earlier["E"], met_a=earlier["A"], fpps=row["fpps_0_100"], confidence_class=row["confidence"]["confidence_class"],
            isolated_residents=isolated_most[unit_id],
            facility_hit=any(item["point_inside_the_flood_extent"] or item["no_vehicle_route_to_a_main_road_entry_in_the_flooded_run"] for item in facilities),
            recurrence_share=share)
        rows_out[unit_id] = {
            "unit_name_en": row["unit_name_en"], "binding_class_v1": row["action_class"], "fpps_0_100": row["fpps_0_100"],
            "second_reading_v2": triggers["result"], "same_as_v1": triggers["result"] == row["action_class"],
            "triggers": triggers["triggers"],
            "trigger_B": {"largest_number_of_residents_one_link_isolates": round(isolated_most[unit_id], 1),
                          "needed": v2.ISOLATED_RESIDENTS_MIN},
            "trigger_C": {"serving_facilities": facilities},
            "trigger_D": {**recurrence[unit_id], "flag_at_20_percent": bool(share is not None and share >= 0.20),
                          "flag_at_10_percent": bool(share is not None and share >= 0.10),
                          "flag_at_30_percent": bool(share is not None and share >= 0.30)},
        }
        print(unit_id, row["unit_name_en"], "v1", row["action_class"], "v2", triggers["result"], triggers["triggers"], flush=True)

    result = {
        "schema": "floodguard.class_v2_reading.v1",
        "generated_at_utc": sheet.datetime.now(sheet.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_timestamp": sheet.SOURCE_TIMESTAMP,
        "confidence_class": "low",
        "confidence_basis": "Modelled access and closures on an agency season layer that was not checked in the field; unreviewed critical-link candidates; unverified facility records.",
        "operational_status": "non_operational",
        "official_warning": False,
        "can_feed_decision_layer": False,
        "what_this_is": "Triggers B, C and D of class rule v2 for case SE1, evaluated as protocol v1b defines them, and the second reading they give. Report-only.",
        "binding": "Class rule v1 stays binding (decision D6). The second reading is a labelled secondary axis and changes no published class. The published result file of case SE1 is not changed and still says 'not_evaluated'.",
        "closure_level": LEVEL,
        "rule": {"order": list(v2.ORDER), "fpps_min": v2.FPPS_MIN, "isolated_residents_min": v2.ISOLATED_RESIDENTS_MIN,
                 "served_residents_min": v2.SERVED_RESIDENTS_MIN, "jrc_occurrence_min_percent": v2.JRC_OCCURRENCE_MIN_PERCENT,
                 "recurrence_land_share_min": v2.RECURRENCE_LAND_SHARE_MIN},
        "readings_of_the_drafter": [
            "'Loses all vehicle routes' for a facility is read as: in the flooded run at the central level, no vehicle route joins the facility to any main-road entry.",
            "'Inside the extent' is tested on the facility point of the planning context.",
            "A link 'crosses the flood extent' when the season layer covers any length of it.",
        ],
        "units": rows_out,
        "top_20_links": link_rows,
        "facilities_read": facility_counts,
        "counts": {"units": len(rows_out),
                   "second_reading_differs_from_v1": sum(1 for row in rows_out.values() if not row["same_as_v1"]),
                   "by_second_reading": dict(sorted(defaultdict(int, {key: sum(1 for row in rows_out.values() if row["second_reading_v2"] == key)
                                                                      for key in {row["second_reading_v2"] for row in rows_out.values()}}).items()))},
        "inputs": {"published_result_file": {"path": OVERLAY, "sha256": sheet.sha256_file(ROOT / OVERLAY)},
                   "top_20_links": {"path": TOP_LINKS, "sha256": sheet.sha256_file(ROOT / TOP_LINKS)},
                   "season_extent_sha256": extent_sha,
                   "jrc_occurrence": {"west_tile_on_disk": JRC_LOCAL.as_posix(), "east_tile_read_from": JRC_EAST_URL}},
        "credits": ["JRC Global Surface Water (Pekel et al. 2016), occurrence 1984 to 2021; Copernicus, European Commission.",
                    "ESA WorldCover 2021 v200 (CC BY 4.0).",
                    *json.loads((ROOT / sheet.OUTPUT_DIR / sheet.RESULT_NAME).read_text(encoding="utf-8"))["credits"]],
        "assumptions": sheet.ASSUMPTIONS,
        "limits": [*sheet.LIMITS[:3],
                   "The top-20 links are unreviewed candidates (plan task V1): no link is an observed closure.",
                   "The second reading is not binding and was not run through the uncertainty ensemble."],
    }
    sheet.write_json(ROOT / OUTPUT, result)
    print(json.dumps(result["counts"]))


if __name__ == "__main__":
    main()
