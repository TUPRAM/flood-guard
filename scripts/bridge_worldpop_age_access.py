"""Bind exact-year WorldPop age cells to older, fixed Mae Sai access scenarios.

This is a local research sensitivity. It does not create event-year access,
accepted demographic exposure, an operational route, or an accepted FPPS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from floodguard.equity import compute_equity_gap
from floodguard.evidence_age_surface import (
    AGE_BANDS,
    CHILD_BANDS,
    OLDER_BANDS,
    _coverage,
)
from floodguard.evidence_catalog import canonical_bytes
from floodguard.evidence_scenarios import calculate_total_access

GROUPS = ("children_0_14", "older_60_plus", "other_15_59")
THRESHOLDS = (15, 30, 60)
VARIANT = "hospital-walking-1"
INTERVENTION = "close_edge-1"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _features(path: Path) -> list[dict]:
    data = _read(path)
    if data.get("type") != "FeatureCollection" or not data.get("features"):
        raise ValueError(f"Nonempty GeoJSON FeatureCollection required: {path}")
    return data["features"]


def _check_age_sources(
    manifest_path: Path, review_path: Path, review_units_path: Path,
    aoi_path: Path,
) -> tuple[dict, dict, dict[str, Path]]:
    manifest = _read(manifest_path)
    review = _read(review_path)
    receipt = _read(review_path.with_name("receipt.json"))
    if (manifest.get("schema_version") != "floodguard.worldpop_age_acquisition.v1"
            or manifest.get("status") != "PASS"
            or manifest.get("year_represented") != 2024
            or manifest.get("resolution_code") != "1km"
            or "R2025A v1" not in manifest.get("product", "")):
        raise ValueError("Complete 2024 WorldPop R2025A 1km age source required")
    if (review.get("schema_version") != "floodguard.worldpop_age_review.v1"
            or review.get("status") != "modelled_research_candidate"
            or review.get("year_represented") != 2024
            or review.get("source_resolution") != "1km"
            or review.get("source_acquisition_manifest_sha256") != _sha(manifest_path)
            or review.get("aoi_geometry_sha256") != _sha(aoi_path)
            or review.get("unit_geometry_sha256") != _sha(review_units_path)
            or review.get("official_warning") is not False
            or any(review.get(key) is not None for key in
                   ("accepted_exposure", "accepted_equity", "accepted_fpps"))):
        raise ValueError("Age review source or candidate-only contract mismatch")
    if (receipt.get("output_sha256") != _sha(review_path)
            or receipt.get("source_acquisition_manifest_sha256") != _sha(manifest_path)):
        raise ValueError("Age review receipt mismatch")
    if review.get("age_groups") != {
        "children": "0-14 inclusive", "older_adults": "60+ inclusive",
        "other": "15-59 inclusive",
    }:
        raise ValueError("Age group definition changed")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != len(AGE_BANDS):
        raise ValueError("Twenty age bands are required")
    paths: dict[str, Path] = {}
    for record in files:
        band = record.get("band")
        if band not in AGE_BANDS or band in paths:
            raise ValueError("Unknown or repeated age band")
        name = f"tha_t_{band}_2024_CN_1km_R2025A_UA_v1.tif"
        url = ("https://data.worldpop.org/GIS/AgeSex_structures/"
               "Global_2015_2030/R2025A/2024/THA/v1/1km_ua/constrained/" + name)
        if record.get("file") != name or record.get("url") != url:
            raise ValueError("WorldPop age source filename or URL mismatch")
        path = manifest_path.parent / name
        if (not path.is_file() or path.stat().st_size != record.get("bytes")
                or _sha(path) != record.get("sha256")):
            raise ValueError(f"WorldPop age source byte identity failed: {band}")
        paths[band] = path
    if set(paths) != set(AGE_BANDS):
        raise ValueError("Incomplete WorldPop age bands")
    return manifest, review, paths


def _check_finals(finals_dir: Path, reporting_path: Path) -> tuple[dict, dict, dict]:
    receipt = _read(finals_dir / "build_receipt.json")
    for name in ("analysis.json", "scenario_details.json",
                 "contexts/walking/context_inputs.json"):
        path = finals_dir / name
        if _sha(path) != receipt.get("files", {}).get(name):
            raise ValueError(f"Finals file hash mismatch: {name}")
    if _sha(reporting_path) != receipt.get("reporting_units_sha256"):
        raise ValueError("Finals reporting-unit source mismatch")
    analysis = _read(finals_dir / "analysis.json")
    context = _read(finals_dir / "contexts/walking/context_inputs.json")
    detailed = _read(finals_dir / "scenario_details.json")
    if (analysis.get("status") != "scenario_only"
            or context.get("official_warning") is not False
            or context.get("input_hashes", {}).get("reporting_units")
            != _sha(reporting_path)
            or context.get("canonical_sha256")
            != receipt.get("context_hashes", {}).get("walking")):
        raise ValueError("Finals package is not the expected candidate scenario")
    content = {key: value for key, value in context.items()
               if key not in ("canonical_sha256", "generated_at")}
    if hashlib.sha256(canonical_bytes(content)).hexdigest() != context["canonical_sha256"]:
        raise ValueError("Finals context canonical hash mismatch")
    if VARIANT not in detailed:
        raise ValueError("Fixed hospital walking variant unavailable")
    return analysis, context, detailed[VARIANT]


def _geometries(
    aoi_path: Path, review_units_path: Path, reporting_path: Path, review: dict,
) -> tuple[object, dict[str, object]]:
    aoi_rows = _features(aoi_path)
    if len(aoi_rows) != 1:
        raise ValueError("Exactly one Mae Sai AOI required")
    aoi = shape(aoi_rows[0]["geometry"])
    if not aoi.is_valid or aoi.is_empty:
        raise ValueError("Invalid AOI geometry")
    old = {row["properties"]["subdistrict_id"]: shape(row["geometry"])
           for row in _features(review_units_path)}
    selected = {}
    for feature in _features(reporting_path):
        unit = feature["properties"].get("adm3_pcode")
        geom = shape(feature["geometry"])
        if not isinstance(unit, str) or not unit or not geom.is_valid:
            raise ValueError("Invalid finals reporting unit")
        clipped = geom.intersection(aoi)
        if clipped.is_empty or clipped.area <= 0:
            continue
        if unit in selected or unit not in old:
            raise ValueError("Duplicate or unmatched finals reporting unit")
        selected[unit] = clipped
    expected = {row["unit_id"] for row in review["units"]}
    if not selected or set(selected) != expected:
        raise ValueError("Age review and finals AOI reporting units differ")
    to_m = Transformer.from_crs(4326, 32647, always_xy=True).transform
    for unit, clipped in selected.items():
        mismatch = transform(to_m, clipped.symmetric_difference(old[unit].intersection(aoi))).area
        if mismatch > 1.0:
            raise ValueError(f"Age and finals reporting geometry differ: {unit}")
    pieces = [transform(to_m, geom) for geom in selected.values()]
    if math.fsum(geom.area for geom in pieces) - unary_union(pieces).area > 1.0:
        raise ValueError("Reporting AOI intersections overlap")
    return aoi, selected


def _cell_masses(
    paths: dict[str, Path], selected: dict[str, object], review: dict,
) -> tuple[list[dict], dict]:
    """Read source cells directly; count mass follows projected AOI-unit overlap."""
    rows = []
    per_unit = {}
    by_id = {row["unit_id"]: row["aoi_intersection"] for row in review["units"]}
    with ExitStack() as stack:
        rasters = {band: stack.enter_context(rasterio.open(paths[band]))
                   for band in AGE_BANDS}
        first = rasters[AGE_BANDS[0]]
        if first.crs is None or first.crs.to_epsg() != 4326:
            raise ValueError("WorldPop age grid must be EPSG:4326")
        for band in AGE_BANDS[1:]:
            other = rasters[band]
            if (other.crs != first.crs or other.transform != first.transform
                    or other.width != first.width or other.height != first.height):
                raise ValueError("WorldPop age bands use different grids")
        grid = {"crs": "EPSG:4326", "width": first.width, "height": first.height,
                "transform": tuple(first.transform)[:6]}
        for unit, geometry in sorted(selected.items()):
            window, fractions, area_m2 = _coverage(geometry, first)
            arrays = {band: rasters[band].read(1, window=window, masked=True)
                      for band in AGE_BANDS}
            unit_rows = []
            for local_row, local_col in zip(*np.nonzero(fractions), strict=True):
                source_row = int(window.row_off) + int(local_row)
                source_col = int(window.col_off) + int(local_col)
                values = {}
                valid = True
                for band, array in arrays.items():
                    value = array[local_row, local_col]
                    if np.ma.is_masked(value) or not math.isfinite(float(value)) or float(value) < 0:
                        valid = False
                        break
                    values[band] = float(value) * float(fractions[local_row, local_col])
                groups = None
                if valid:
                    total = math.fsum(values.values())
                    children = math.fsum(values[band] for band in CHILD_BANDS)
                    older = math.fsum(values[band] for band in OLDER_BANDS)
                    groups = {"children_0_14": children, "older_60_plus": older,
                              "other_15_59": total - children - older}
                    if groups["other_15_59"] < -1e-7:
                        raise ValueError("Source age bands do not reconcile")
                unit_rows.append({"unit_id": unit, "raster_row": source_row,
                                  "raster_col": source_col,
                                  "fractional_source_cell": float(fractions[local_row, local_col]),
                                  "covered_m2": float(area_m2[local_row, local_col]),
                                  "band_counts": values if valid else None,
                                  "groups": groups})
            supported = [row for row in unit_rows if row["groups"] is not None]
            totals = {group: math.fsum(row["groups"][group] for row in supported)
                      for group in GROUPS}
            reference = by_id[unit]
            for group, key in (("children_0_14", "children_0_14_estimate"),
                               ("older_60_plus", "older_60_plus_estimate"),
                               ("other_15_59", "other_15_59_estimate")):
                if not math.isclose(totals[group], reference[key], abs_tol=0.01, rel_tol=1e-7):
                    raise ValueError(f"Direct source-grid count differs from age review: {unit}/{group}")
            per_unit[unit] = {
                "source_supported_population": math.fsum(totals.values()),
                "groups": totals,
                "source_supported_area_km2": math.fsum(row["covered_m2"] for row in supported) / 1e6,
                "source_unsupported_area_km2": math.fsum(
                    row["covered_m2"] for row in unit_rows if row["groups"] is None
                ) / 1e6,
            }
            rows.extend(unit_rows)
    return rows, {"grid": grid, "units": per_unit}


def allocate_cell_masses(
    cell_rows: list[dict], population: list[dict], transform_affine,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]], list[dict], dict]:
    """Conserve each supported source-cell/unit group mass on 2020 demand nodes.

    Positive age mass with no positive 2020 node support stays unallocated.
    Invalid age-source cells never become zero counts.
    """
    cells = {(r["unit_id"], r["raster_row"], r["raster_col"]): r for r in cell_rows}
    if len(cells) != len(cell_rows):
        raise ValueError("Duplicate unit/source-cell record")
    nodes: dict[tuple, list[dict]] = defaultdict(list)
    missing_age_node_population = 0.0
    ids = set()
    for row in population:
        pid = row["population_id"]
        value = row["total_population"]
        if (pid in ids or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError("2020 demand IDs and positive counts must be valid")
        ids.add(pid)
        col, raster_row = (~transform_affine) * (row["longitude"], row["latitude"])
        key = (row["subdistrict_id"], math.floor(raster_row), math.floor(col))
        if key not in cells or cells[key]["groups"] is None:
            missing_age_node_population += value
            continue
        nodes[key].append(row)
    node_age: dict[str, dict[str, float]] = defaultdict(
        lambda: {group: 0.0 for group in GROUPS}
    )
    unallocated: dict[str, dict[str, float]] = defaultdict(
        lambda: {group: 0.0 for group in GROUPS}
    )
    ledger = []
    for key, cell in sorted(cells.items()):
        support = sorted(nodes.get(key, []), key=lambda row: row["population_id"])
        weights_total = math.fsum(row["total_population"] for row in support)
        allocated = {group: 0.0 for group in GROUPS}
        unresolved = {group: 0.0 for group in GROUPS}
        if cell["groups"] is not None:
            for group, mass in cell["groups"].items():
                if not support:
                    unresolved[group] = mass
                    unallocated[key[0]][group] += mass
                    continue
                given = []
                for row in support[:-1]:
                    share = mass * row["total_population"] / weights_total
                    node_age[row["population_id"]][group] += share
                    given.append(share)
                residual = mass - math.fsum(given)
                node_age[support[-1]["population_id"]][group] += residual
                allocated[group] = math.fsum((*given, residual))
                if not math.isclose(allocated[group] + unresolved[group], mass,
                                    rel_tol=1e-12, abs_tol=1e-8):
                    raise ValueError("Source-cell age mass was not conserved")
        ledger.append({"unit_id": key[0], "raster_row": key[1], "raster_col": key[2],
                       "source_supported": cell["groups"] is not None,
                       "source_fraction": cell["fractional_source_cell"],
                       "covered_m2": cell["covered_m2"],
                       "age_groups": cell["groups"],
                       "2020_support_nodes": len(support),
                       "2020_support_population": weights_total,
                       "allocated": allocated, "unknown_no_2020_support": unresolved})
    for group in GROUPS:
        source = math.fsum(row["groups"][group] for row in cell_rows if row["groups"] is not None)
        assigned = math.fsum(value[group] for value in node_age.values())
        unknown = math.fsum(value[group] for value in unallocated.values())
        if not math.isclose(source, assigned + unknown, rel_tol=1e-12, abs_tol=1e-7):
            raise ValueError(f"Overall age mass not conserved: {group}")
    return dict(node_age), dict(unallocated), ledger, {
        "2020_demand_population_without_age_source_support": missing_age_node_population,
    }


def _access_summary(
    cell_summary: dict, node_age: dict, unallocated: dict, result: dict,
) -> tuple[dict, dict, list[dict]]:
    by_unit: dict[str, dict] = {}
    for unit, source in cell_summary["units"].items():
        by_unit[unit] = {"source": source, "groups": {}}
        for group in GROUPS:
            by_unit[unit]["groups"][group] = {
                "denominator": source["groups"][group],
                "unknown_no_2020_support": unallocated.get(unit, {}).get(group, 0.0),
                "unknown_missing_connector": 0.0,
                "baseline_reachable": {str(t): 0.0 for t in THRESHOLDS},
                "new_threshold_loss": {str(t): 0.0 for t in THRESHOLDS},
                "new_all_route_loss": 0.0,
            }
    seen = set()
    for row in result["node_results"]:
        pid = row["population_id"]
        if pid in seen:
            raise ValueError("Duplicate access outcome node")
        seen.add(pid)
        if pid not in node_age:
            continue
        for group, mass in node_age[pid].items():
            target = by_unit[row["subdistrict_id"]]["groups"][group]
            if row["snap_status"] != "connected":
                target["unknown_missing_connector"] += mass
                continue
            before = row["normal_access_minutes"]
            after = row["scenario_access_minutes"]
            for threshold in THRESHOLDS:
                if before is not None and before <= threshold:
                    target["baseline_reachable"][str(threshold)] += mass
                    if after is None or after > threshold:
                        target["new_threshold_loss"][str(threshold)] += mass
            if before is not None and after is None:
                target["new_all_route_loss"] += mass
    if set(node_age) - seen:
        raise ValueError("Allocated age node missing from access outcomes")
    contrasts = (("children_vs_15_plus", "children_0_14", ("older_60_plus", "other_15_59")),
                 ("older_vs_under_60", "older_60_plus", ("children_0_14", "other_15_59")),
                 ("children_plus_older_vs_15_59", ("children_0_14", "older_60_plus"), "other_15_59"))
    for unit, entry in by_unit.items():
        for group, values in entry["groups"].items():
            values["access_unknown"] = (values["unknown_no_2020_support"]
                                        + values["unknown_missing_connector"])
            values["known_evaluable"] = values["denominator"] - values["access_unknown"]
            if values["known_evaluable"] < -1e-7:
                raise ValueError("Unknown age mass exceeds denominator")
    aoi = {
        "scope": "AOI intersection with selected reporting-unit union",
        "source": {
            "source_supported_population": math.fsum(
                entry["source"]["source_supported_population"] for entry in by_unit.values()),
            "source_supported_area_km2": math.fsum(
                entry["source"]["source_supported_area_km2"] for entry in by_unit.values()),
            "source_unsupported_area_km2": math.fsum(
                entry["source"]["source_unsupported_area_km2"] for entry in by_unit.values()),
            "groups": {group: math.fsum(
                entry["source"]["groups"][group] for entry in by_unit.values())
                for group in GROUPS},
        },
        "groups": {},
    }
    for group in GROUPS:
        aoi["groups"][group] = {
            field: math.fsum(entry["groups"][group][field] for entry in by_unit.values())
            for field in ("denominator", "unknown_no_2020_support",
                          "unknown_missing_connector", "access_unknown",
                          "known_evaluable", "new_all_route_loss")
        }
        for field in ("baseline_reachable", "new_threshold_loss"):
            aoi["groups"][group][field] = {
                str(threshold): math.fsum(
                    entry["groups"][group][field][str(threshold)]
                    for entry in by_unit.values())
                for threshold in THRESHOLDS
            }
    equity_rows = []
    for unit, entry in [*by_unit.items(), ("AOI-01-reporting-intersection", aoi)]:
        for threshold in THRESHOLDS:
            for name, focal, complement in contrasts:
                def add(keys, field, row=entry):
                    ids = (keys,) if isinstance(keys, str) else keys
                    return math.fsum(row["groups"][key][field] for key in ids)
                def add_loss(keys, row=entry, minutes=threshold):
                    ids = (keys,) if isinstance(keys, str) else keys
                    return math.fsum(row["groups"][key]["new_threshold_loss"][str(minutes)] for key in ids)
                equity_rows.append({
                    "unit_id": unit,
                    "scope": "aoi_reporting_intersection" if entry is aoi else "reporting_unit_aoi_intersection",
                    "contrast": name, "threshold_minutes": threshold,
                    "subdistrict_id": unit, "subdistrict_name": unit,
                    "total_vulnerable_population": add(focal, "denominator"),
                    "vulnerable_population_losing_access": add_loss(focal),
                    "vulnerable_population_access_unknown": add(focal, "access_unknown"),
                    "total_non_vulnerable_population": add(complement, "denominator"),
                    "non_vulnerable_population_losing_access": add_loss(complement),
                    "non_vulnerable_population_access_unknown": add(complement, "access_unknown"),
                    "confidence_class": "low",
                })
    computed = compute_equity_gap(pd.DataFrame(equity_rows))
    output_equity = []
    for row in computed.to_dict("records"):
        output_equity.append({key: None if pd.isna(value) else value
                              for key, value in row.items()})
    return by_unit, aoi, output_equity


def build(
    manifest_path: Path, age_review_path: Path, age_review_units: Path,
    aoi_path: Path, reporting_path: Path, finals_dir: Path, output_dir: Path,
) -> dict:
    """Write an immutable local age-access sensitivity and SHA-256 receipt."""
    if output_dir.exists():
        raise ValueError("Output already exists; choose a new immutable run directory")
    if output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("Detailed research output must remain outside Git")
    manifest, review, paths = _check_age_sources(
        manifest_path, age_review_path, age_review_units, aoi_path)
    _analysis, context, variant = _check_finals(finals_dir, reporting_path)
    aoi, selected = _geometries(aoi_path, age_review_units, reporting_path, review)
    uploaded_aoi = Path(__file__).resolve().parents[1] / "resources/aoi/upload/aoi-01_mae_sai_core.geojson"
    upload = shape(_features(uploaded_aoi)[0]["geometry"])
    if (not aoi.equals(upload)
            or _sha(uploaded_aoi) != _read(finals_dir / "build_receipt.json").get("aoi_sha256")):
        raise ValueError("Age AOI and finals demand AOI differ")
    cell_rows, cell_summary = _cell_masses(paths, selected, review)
    with rasterio.open(paths[AGE_BANDS[0]]) as source:
        node_age, unallocated, ledger, coverage = allocate_cell_masses(
            cell_rows, context["population"], source.transform)
    if variant["baseline"]["official_warning"] is not False:
        raise ValueError("Finals baseline is not non-operational")
    definition = next((row for row in variant["definitions"]
                       if row.get("id") == INTERVENTION), None)
    if definition is None or definition.get("kind") != "close_edge":
        raise ValueError("Preselected road-closure scenario unavailable")
    sites = [row for row in context["osm_facilities"]
             if row.get("service_type") == "hospital"
             and row.get("candidate_destination_eligible") is True
             and row.get("within_routing_context") is True]
    baseline = calculate_total_access(context["population"], context["edges"], sites)
    if baseline["baseline_input_sha256"] != variant["baseline"]["baseline_input_sha256"]:
        raise ValueError("Recomputed access baseline differs from saved finals baseline")
    scenario = calculate_total_access(
        context["population"], context["edges"], sites,
        scenario=definition["scenario"], baseline_result=baseline)
    stored = variant["interventions"][INTERVENTION]
    for field in ("total_population", "people_losing_15_min_access",
                  "people_losing_30_min_access", "people_losing_60_min_access"):
        if not math.isclose(scenario["totals"][field], stored["totals"][field], abs_tol=1e-6):
            raise ValueError(f"Recomputed access consequence differs from finals: {field}")
    by_unit, aoi_total, equity = _access_summary(
        cell_summary, node_age, unallocated, scenario)
    generated = datetime.now(timezone.utc).isoformat()
    summary = {
        "schema_version": "floodguard.mixed_vintage_age_access_sensitivity.v1",
        "generated_at_utc": generated, "status": "candidate_scenario_only",
        "operational_status": "non_operational", "official_warning": False,
        "accepted_exposure": None, "accepted_equity": None,
        "accepted_fpps": None, "accepted_action_class": None,
        "aoi_id": "aoi-01_mae_sai_core", "event_id": "mae-sai-flood-2024-09",
        "age_source_year": 2024, "age_source_publication_date": manifest["publication_date"],
        "demand_year": 2020, "reporting_boundary_date": "2022-01-22",
        "road_source_retrieved_at_utc": context["source_metadata"]["osm"]["retrieved_at_utc"],
        "service": "hospital", "travel_mode": "walking", "speed_factor": 1.0,
        "scenario_id": INTERVENTION, "scenario": definition["scenario"],
        "scenario_selection_method": definition["selection_method"],
        "baseline_input_sha256": baseline["baseline_input_sha256"],
        "source_grid": cell_summary["grid"],
        "reporting_units": by_unit,
        "aoi_reporting_intersection": aoi_total,
        "equity": equity,
        "coverage": {
            **coverage,
            "age_source_supported_population": math.fsum(
                item["source_supported_population"] for item in cell_summary["units"].values()),
            "age_unallocated_no_2020_support": {
                group: math.fsum(value.get(group, 0.0) for value in unallocated.values())
                for group in GROUPS},
            "aoi_outside_reporting_units_km2": review["aoi_outside_selected_reporting_units_km2"],
        },
        "2020_access_comparator": {
            "population": scenario["totals"]["total_population"],
            "new_loss_15_minutes": scenario["totals"]["people_losing_15_min_access"],
            "new_loss_30_minutes": scenario["totals"]["people_losing_30_min_access"],
            "new_loss_60_minutes": scenario["totals"]["people_losing_60_min_access"],
        },
        "assumptions": [
            "2024 modelled residential age counts are intersected fractionally with each AOI reporting unit at their original 1km source grid; no 1km-to-100m raster interpolation.",
            "Within each unit and 1km cell, counts are allocated to fixed positive 2020 demand nodes in proportion to their 2020 total-population weights. This preserves source age mass, not 2024 node observations.",
            "Age mass in a source cell with no 2020 demand node is unknown for access. Missing graph connectors are also access-unknown; neither is zero loss.",
            "The preselected single-edge closure is hypothetical, not an observed flood-road intersection or closure. Existing OSM hospital sites and entrances are unverified.",
            "2024 ages, 2020 demand locations, 2022 reporting boundaries and a later OSM graph form a mixed-vintage sensitivity; this is not historical 2024 access.",
            "Equity intervals bound missing access coverage only, not demographic model uncertainty, event probability or statistical confidence.",
        ],
        "limitations": [
            "Source-grid fractions and 2020 cell-centre demand have different boundary rules; unallocated mass is explicit.",
            "Age-source no-data area has no count denominator and cannot be bounded numerically without another compatible source.",
            "Children mean ages 0-14 inclusive; older adults mean 60+ inclusive. Complements are age categories, not a non-vulnerable population.",
            "No accepted flood observation, observed road closure, facility operation, age equity or FPPS follows from this scenario.",
        ],
    }
    summary["canonical_sha256"] = hashlib.sha256(canonical_bytes(summary)).hexdigest()
    output_dir.mkdir(parents=True)
    output = output_dir / "age_access_sensitivity.json"
    output.write_bytes(canonical_bytes(summary))
    ledger_path = output_dir / "source_cell_ledger.json"
    ledger_path.write_bytes(canonical_bytes({"schema_version": "floodguard.age_cell_ledger.v1",
                                          "source_grid": cell_summary["grid"], "cells": ledger}))
    repo = Path(__file__).resolve().parents[1]
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    git_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repo, text=True).strip()
    receipt = {
        "schema_version": "floodguard.age_access_sensitivity_receipt.v1",
        "generated_at_utc": generated, "source_commit": git_head, "source_tree": git_tree,
        "builder_sha256": _sha(Path(__file__)),
        "inputs": {str(path): {"bytes": path.stat().st_size, "sha256": _sha(path)}
                   for path in (manifest_path, age_review_path,
                                age_review_path.with_name("receipt.json"),
                                age_review_units, aoi_path, uploaded_aoi,
                                reporting_path, finals_dir / "build_receipt.json",
                                finals_dir / "analysis.json",
                                finals_dir / "scenario_details.json",
                                finals_dir / "contexts/walking/context_inputs.json",
                                *paths.values())},
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": _sha(p)}
                    for p in (output, ledger_path)},
        "canonical_sha256": summary["canonical_sha256"],
    }
    (output_dir / "run_receipt.json").write_bytes(canonical_bytes(receipt))
    return {"output_sha256": _sha(output), "receipt_sha256": _sha(output_dir / "run_receipt.json"),
            "age_source_population": summary["coverage"]["age_source_supported_population"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("acquisition_manifest", "age_review", "age_review_units", "aoi",
                 "reporting_units", "finals_dir", "output_dir"):
        parser.add_argument("--" + flag.replace("_", "-"), required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.acquisition_manifest, args.age_review, args.age_review_units,
                           args.aoi, args.reporting_units, args.finals_dir, args.output_dir)))


if __name__ == "__main__":
    main()
