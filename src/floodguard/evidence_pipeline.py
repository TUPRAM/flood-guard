"""Build local research packages and a separately allowlisted Studio export."""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import platform
import zlib
from importlib import metadata
from pathlib import Path
from typing import Any

from .evidence_catalog import (
    SCHEMA_VERSION,
    assert_public_safe,
    build_registry,
    canonical_bytes,
    dataset_applies,
    load_aois,
    safe_asset_path,
    sha256_file,
    validate_layer_export,
)
from .evidence_decision_brief import build_decision_brief
from .evidence_scenarios import build_illustrative_scenarios, evidence_assessment

TRANSFORMATION_VERSION = "evidence-demo-1"
PUBLIC_PREFIX = "/evidence-library/"


def build_runtime_identity(
    *, context_enabled: bool, lock_path: Path | None = None
) -> dict:
    """Identify numerical/compression runtimes without machine-specific paths.

    Installed versions are recorded independently of the dependency lock. An
    unsynchronized environment cannot share the locked runtime's identity.
    Export verifiers check artifact bytes, not their own runtime environment.
    """
    import pyproj
    import rasterio
    import shapely

    lock = lock_path or Path(__file__).resolve().parents[2] / "uv.lock"
    packages = {}
    for name in (
        "geopandas",
        "networkx",
        "numpy",
        "pandas",
        "Pillow",
        "pyproj",
        "rasterio",
        "requests",
        "shapely",
    ):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    tools = {}
    if context_enabled:
        from .evidence_context import ogr_runtime_identity

        tools["ogr2ogr"] = ogr_runtime_identity()
    identity = {
        "schema_version": "floodguard.build_runtime.v1",
        "uv_lock_sha256": sha256_file(lock),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "packages": packages,
        "native": {
            "rasterio_gdal": rasterio.__gdal_version__,
            "rasterio_proj": getattr(rasterio, "__proj_version__", None),
            "pyproj_proj": pyproj.proj_version_str,
            "shapely_geos": shapely.geos_version_string,
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
        },
        "external_tools": tools,
    }
    assert_public_safe(identity)
    return {**identity, "sha256": hashlib.sha256(canonical_bytes(identity)).hexdigest()}


def _runtime_bound_hash(value: dict, runtime: dict) -> str:
    """Bind transformation input identity to the actual builder runtime."""
    return hashlib.sha256(
        canonical_bytes({"inputs": value, "build_runtime_sha256": runtime["sha256"]})
    ).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """Write deterministic finite JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def _public_json(path: Path, value: Any) -> None:
    """Compact static packages to avoid repeating whitespace in offline caches."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _public_context(context: dict) -> dict:
    """Offer the actual derived routing database, excluding supplied facilities."""
    from .evidence_finals_export import SITE_EXTRA_KEYS
    from .evidence_validation import EDGE_KEYS, OSM_SITE_KEYS, POPULATION_KEYS

    projected = {
        "license": "OSM-derived database: ODbL 1.0; WorldPop population: CC BY 4.0",
        "source_urls": [
            "https://www.openstreetmap.org/copyright",
            "https://opendatacommons.org/licenses/odbl/1-0/",
            "https://hub.worldpop.org/geodata/summary?id=6439",
            "https://creativecommons.org/licenses/by/4.0/",
        ],
        "attribution": [
            "© OpenStreetMap contributors",
            "WorldPop and CIESIN (2018), Global High Resolution Population Denominators Project, doi:10.5258/SOTON/WP00645",
        ],
        "confidence_class": "low",
        "dataset_mode": "candidate",
        "non_operational": True,
        "official_warning": False,
        "source_timestamp": None,
        "assumptions": context["assumptions"],
        "input_hashes": context["input_hashes"],
        "source_metadata": {
            source: {
                key: values[key]
                for key in (
                    "download_url",
                    "license_status",
                    "processing_scope",
                    "retrieved_at_utc",
                    "sha256",
                    "source_name",
                    "source_url",
                )
            }
            for source, values in context["source_metadata"].items()
        },
        "analysis_crs": "EPSG:32647",
        "node_coordinates": context["node_coordinates"],
        "population": [
            {key: value for key, value in row.items() if key in POPULATION_KEYS}
            for row in context["population"]
        ],
        "edges": [
            {key: value for key, value in row.items() if key in EDGE_KEYS}
            for row in context["edges"]
        ],
        "osm_facilities": [
            {
                key: value
                for key, value in row.items()
                if key in OSM_SITE_KEYS | SITE_EXTRA_KEYS
            }
            for row in context["osm_facilities"]
        ],
        "coverage": context["coverage"],
        "connectivity_review": context.get("connectivity_review", {}),
    }
    assert_public_safe(projected)
    return projected


REPORT_PROJECTION = "aggregate_scenarios_v3"
REPORT_OMITTED_FIELDS = frozenset(
    {
        "allocations",
        "population_results",
        "facility_results",
        "node_results",
        "baseline_reachable_pairs",
        "scenario_reachable_pairs",
        "areas",
        "facility_snap_review",
        "map_geojson",
        "layers",
        "geometry",
    }
)


def _compact_details(details: dict) -> dict:
    """Project exact settings and aggregate results, excluding detailed records.

    The same projection covers both capacity presets and participation
    sensitivities, including wrapped results. Full scenario records stay local;
    public geometry and ODbL source databases are separate hash-bound downloads.
    """

    def project(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: project(item)
                for key, item in value.items()
                if key not in REPORT_OMITTED_FIELDS
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    return project(details)


def report_scenario_projection(details: dict) -> dict:
    """Return the explicit compact report projection used by offline verification."""
    return _compact_details(details) | {"summaries": scenario_summaries(details)}


def report_brief_projection(brief: dict | None) -> dict | None:
    """Retain aggregate decisions; bind detailed routes through package downloads."""
    if brief is None or "finals_analysis" not in brief:
        return brief
    finals = brief["finals_analysis"]
    compact = {key: finals[key] for key in (
        "analysis_sha256", "status", "scope", "primary_service", "services", "limitations"
    )}
    if "flood_scenarios" in finals:
        compact["flood_scenarios"] = {
            mode: {key: value for key, value in result.items() if key != "closed_edges"}
            | {"closed_edge_count": len(result["closed_edges"])}
            for mode, result in finals["flood_scenarios"].items()
        }
    return {**brief, "finals_analysis": compact}


def _display_roads(path: Path) -> dict:
    """Keep full source way geometry for display, projecting only road fields."""
    source = json.loads(path.read_text(encoding="utf-8"))
    keys = {"osm_id", "highway", "name", "bridge", "tunnel", "layer"}
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {k: v for k, v in f["properties"].items() if k in keys},
            }
            for f in source["features"]
        ],
    }


def _scenario_features(context: dict, details: dict) -> dict:
    """Expose the exact imposed changes as a separate scenario map layer."""
    selection = details["stress_selection"]
    features = []
    for feature in context["road_geojson"]["features"]:
        if feature["properties"]["edge_id"] == selection["closed_edge_id"]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": feature["geometry"],
                    "properties": {
                        "edge_id": selection["closed_edge_id"],
                        "name": "Imposed closure experiment; not an observed closure",
                        "evidence_role": "scenario",
                    },
                }
            )
    for facility in context["osm_facilities"]:
        if facility["facility_id"] == selection["removed_facility_id"]:
            features.append(
                {
                    "type": "Feature",
                    "geometry": facility["geometry"],
                    "properties": {
                        "facility_id": facility["facility_id"],
                        "name": "Destination-removal experiment; event availability unknown",
                        "evidence_role": "scenario",
                    },
                }
            )
    node = selection["hypothetical_added_node"]
    if node is not None:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": context["node_coordinates"][node],
                },
                "properties": {
                    "facility_id": "scenario-added-destination",
                    "name": "Hypothetical access destination; suitability unverified",
                    "evidence_role": "scenario",
                },
            }
        )
    site = details.get("hypothetical_capacity_site")
    if site:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": site["coordinates"]},
                "properties": {
                    "facility_id": site["facility_id"],
                    "name": "Separate hypothetical capacity site; 50/100/200 places and 5/10/25% residential participation",
                    "evidence_role": "scenario",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _context_scenarios(
    context: dict, aoi_id: str, source: str, path: Path, reuse: bool, runtime: dict
) -> dict:
    from .evidence_context import build_context_scenarios

    binding = {
        "input_sha256": context["canonical_sha256"],
        "facility_source": source,
        "aoi_id": aoi_id,
        "build_runtime_sha256": runtime["sha256"],
        "transformations": {
            name: sha256_file(Path(__file__).parent / name)
            for name in (
                "evidence_context.py",
                "evidence_scenarios.py",
                "evidence_interventions.py",
                "evidence_population_review.py",
            )
        },
    }
    receipt_path = path.with_suffix(".receipt.json")
    if reuse and path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("binding") == binding:
            if sha256_file(path) != receipt["sha256"]:
                raise ValueError("Cached scenario output checksum changed")
            return json.loads(path.read_text(encoding="utf-8"))
    result = build_context_scenarios(context, aoi_id, facility_source=source)
    write_json(path, result)
    write_json(
        receipt_path,
        {"binding": binding, "sha256": sha256_file(path), "build_runtime": runtime},
    )
    return result


def _supporting_dataset(
    identifier: str,
    title: str,
    license_name: str,
    url: str,
    role: str,
    limitations: list[str],
) -> dict:
    return {
        "id": identifier,
        "title": title,
        "role": role,
        "source_urls": [url],
        "temporal": {
            "start": None,
            "end": None,
            "kind": "scenario" if role == "scenario" else "static_context",
            "label": "Explicit synthetic experiment"
            if role == "scenario"
            else "Source snapshot; not event-time conditions",
        },
        "limitations": limitations,
        "rights": {
            "status": "public_derivatives_permitted",
            "license": license_name,
            "public_derivatives": True,
            "attribution": [title],
        },
    }


SUPPORTING = [
    _supporting_dataset(
        "context-sar-candidate",
        "Contains modified Copernicus Sentinel data (2024, 2025), processed by FloodGuard",
        "Copernicus Sentinel Data Legal Notice",
        "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        "candidate_estimate",
        ["Uncalibrated amplitude-change candidates: Mae Sai 3–15 September 2024 UTC and Hat Yai 11–23 November 2025 UTC. Not validated flood extent or probability. No independent accuracy claim."],
    ),
    _supporting_dataset(
        "context-destination-search",
        "OpenStreetMap bounded destination inventory / existing Geofabrik snapshot",
        "Open Database License 1.0",
        "https://www.openstreetmap.org/copyright",
        "static_context",
        ["Hospital-tagged objects within a recorded search buffer, not a complete inventory of distinct operating hospitals. Identity and routing eligibility are reviewed separately."],
    ),
    _supporting_dataset(
        "project-scenarios",
        "FloodGuard illustrative scenarios",
        "Project-owned synthetic data",
        "https://github.com/TUPRAM/flood-guard",
        "scenario",
        [
            "Invented inputs demonstrate mechanics; no local road, shelter, population or event observation."
        ],
    ),
    _supporting_dataset(
        "context-osm",
        "OpenStreetMap contributors / existing Geofabrik snapshot",
        "Open Database License 1.0",
        "https://www.openstreetmap.org/copyright",
        "static_context",
        [
            "Candidate map features; no observed passability, verified shelter designation or activation.",
            "Derived road/site database is available under ODbL 1.0 in the downloadable report appendix.",
        ],
    ),
    _supporting_dataset(
        "context-worldpop",
        "WorldPop Thailand 2020 population estimate",
        "Creative Commons Attribution 4.0",
        "https://hub.worldpop.org/geodata/summary?id=6439",
        "candidate_estimate",
        [
            "Modelled 2020 population; not an observed event-year count or evacuation demand."
        ],
    ),
]


def public_dataset(dataset: dict) -> dict:
    """Project explicitly approved metadata fields, never entire source records."""
    return {
        key: dataset[key]
        for key in ("id", "title", "role", "source_urls", "limitations")
    } | {
        "temporal": {
            key: dataset["temporal"][key] for key in ("start", "end", "kind", "label")
        },
        "rights": {
            key: dataset["rights"][key]
            for key in ("status", "license", "public_derivatives", "attribution")
        },
    }


def _terrain_image(root: Path, aoi_id: str, destination: Path) -> dict:
    import numpy as np
    import rasterio
    from PIL import Image

    paths = list((root / "terrain_drainage").glob(f"*{aoi_id}*.tif"))
    if len(paths) != 1:
        paths = list((root / "terrain_drainage").rglob(f"*{aoi_id}*.tif"))
    if len(paths) != 1:
        raise ValueError(f"Expected one recorded terrain raster for {aoi_id}")
    with rasterio.open(paths[0]) as source:
        data = source.read(1, masked=True)
        valid = ~np.ma.getmaskarray(data) & np.isfinite(data.filled(np.nan))
        lower, upper = np.percentile(np.asarray(data)[valid], [2, 98])
        scaled = np.clip((data.filled(lower) - lower) / max(upper - lower, 1e-6), 0, 1)
        rgba = np.stack(
            (50 + scaled * 184, 100 + scaled * 140, 112 + scaled * 107, valid * 185),
            axis=-1,
        ).astype("uint8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba).save(destination)
        bounds = source.bounds
    return {
        "image_url": PUBLIC_PREFIX + "terrain/" + destination.name,
        "bounds": [[bounds.bottom, bounds.left], [bounds.top, bounds.right]],
        "attribution": "Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018; EU/ESA. Elevation colour stretch is local to each AOI, not flood depth.",
    }


def _assessment(aoi_id: str) -> dict:
    source = evidence_assessment({}, area_id=aoi_id)
    reasons = {
        "flood_likelihood_0_100": "No accepted event-specific likelihood calibration.",
        "exposure_0_100": "No qualified event-matched extent and exposure transformation.",
        "access_gap_0_100": "Access scenarios are modelled assumptions, not an event observation.",
        "road_criticality_0_100": "Event road condition and criticality evidence is incomplete.",
        "vulnerability_context_0_100": "Age definitions, geographic joins and matched-year denominators remain unresolved.",
    }
    return {
        "components": [
            {
                "id": key,
                "label": key.removesuffix("_0_100").replace("_", " ").title(),
                "weight": weight,
                "value": None,
                "reason": reasons.get(
                    key, "No qualified component input; scenario only."
                ),
            }
            for key, weight in source["weights"].items()
        ],
        "fpps": None,
        "action_class": None,
        "bounds": {k: source["fixed_weight_bounds"][k] for k in ("lower", "upper")},
        "limitations": [
            "Bounds are fixed-weight arithmetic sensitivity, not a confidence interval.",
            "Unknown values are not zero and weights are not redistributed.",
            "Completed low-confidence scenarios remain Class E. No demographic equity score is claimed.",
        ],
    }


def scenario_summaries(details: dict) -> list[dict]:
    """Make concise public cards without losing exact scenario definitions locally."""
    rows = []
    for key, result in sorted(details.get("access_scenarios", {}).items()):
        if "result" in result:
            result = result["result"]
        if "totals" not in result:
            rows.append(
                {
                    "id": "access-" + key,
                    "title": key.replace("_", " ").title(),
                    "kind": "unavailable_scenario",
                    "summary": result.get("reason", "No feasible inputs."),
                    "assumptions": [],
                    "metrics": [],
                }
            )
            continue
        totals = result["totals"]
        metrics = [
            {
                "label": key.replace("_", " "),
                "value": round(value, 2) if isinstance(value, (float, int)) else value,
                "unit": "people",
            }
            for key, value in sorted(totals.items())
        ]
        rows.append(
            {
                "id": "access-" + key,
                "title": key.replace("_", " ").title(),
                "kind": "synthetic_access"
                if details.get("synthetic")
                else "modelled_access",
                "summary": "Synthetic mechanics only; no measured local access result."
                if details.get("synthetic")
                else "Existing OSM network and 2020 modelled population; imposed changes are scenarios, not observed closures.",
                "assumptions": result.get("assumptions", [])
                + [
                    "Primary comparison 30 minutes; 15 and 60 minutes also reported.",
                    "100 m facility and 250 m population connectors at 5 km/h.",
                    "Exact imposed changes: "
                    + json.dumps(
                        result.get("scenario", details.get("stress_selection", {})),
                        sort_keys=True,
                    ),
                ],
                "metrics": metrics,
            }
        )
    capacities = details.get("capacity_scenarios", [])
    if isinstance(capacities, dict):
        capacities = [value for _, value in sorted(capacities.items())]
    capacities = [*capacities, *details.get("capacity_participation_sensitivity", [])]
    for index, result in enumerate(capacities):
        label = result.get(
            "title",
            result.get("scenario_id", f"Capacity experiment {index + 1}").replace(
                "_", " "
            ),
        )
        value = result.get("result", result)
        metrics = [
            {
                "label": key.replace("_", " "),
                "value": round(value[key], 2),
                "unit": "people",
            }
            for key in (
                "total_population",
                "served_population",
                "unserved_population",
                "capacity_limited_unmet_population",
                "unreachable_population",
                "excluded_coverage_population",
                "unmet_population_with_unknown_capacity",
            )
            if key in value and isinstance(value[key], (float, int))
        ]
        rows.append(
            {
                "id": f"capacity-{index}",
                "title": label,
                "kind": "capacity_scenario",
                "summary": "Maximum-flow allocation of modelled demand under explicitly assigned capacities; actual available capacity remains unknown.",
                "assumptions": value.get("assumptions", [])
                + [
                    "No double counting of shared demand; no minimum-travel allocation guarantee."
                ],
                "metrics": metrics,
            }
        )
    for completion in details.get("assessment", {}).get("scenario_completions", []):
        rows.append(
            {
                "id": completion["scenario_id"],
                "title": f"Missing components assumed {completion['assumed_missing_value']}",
                "kind": "score_sensitivity",
                "summary": "Assumed normalized components passed through the unchanged scorer.",
                "assumptions": [
                    "All missing components assigned the same explicitly hypothetical value.",
                    "Fixed weights 30/25/20/15/10. Low confidence always yields Class E.",
                ],
                "metrics": [
                    {"label": "Scenario FPPS", "value": completion["fpps_0_100"]},
                    {"label": "Action class", "value": completion["action_class"]},
                    {"label": "Reason", "value": completion["action_reason_code"]},
                ],
            }
        )
    for family, assessment in sorted(details.get("scenario_assessments", {}).items()):
        for completion in assessment.get("scenario_completions", []):
            rows.append(
                {
                    "id": f"score-{family}-{completion['assumed_missing_value']}",
                    "title": f"{family.replace('_', ' ').title()} · other components {completion['assumed_missing_value']}",
                    "kind": "access_score_sensitivity",
                    "summary": "Experimental 30-minute access gap recalculated from this scenario; four other components explicitly assumed.",
                    "assumptions": assessment.get("assumptions", [])
                    + [assessment.get("component_derivation", {}).get("formula", "")],
                    "metrics": [
                        {
                            "label": "Scenario access gap",
                            "value": round(
                                assessment["components"]["access_gap_0_100"], 2
                            ),
                        },
                        {"label": "Scenario FPPS", "value": completion["fpps_0_100"]},
                        {"label": "Action class", "value": completion["action_class"]},
                        {"label": "Reason", "value": completion["action_reason_code"]},
                    ],
                }
            )
    return rows


def _coverage(dataset: dict, summary: dict, aoi: dict, event: str) -> str:
    n = dataset["number"]
    review = summary["aois"][aoi["id"]]
    if n in (1, 2):
        flood = review.get("flood_reference", {})
        return f"Analysis coverage {flood.get('analysis_coverage_fraction', 0):.1%}; outside footprint unobserved. No accepted September-only reference."
    if n in (3, 4, 5):
        return "Station-month observations include missing measurements; absent timestamps and present null/sentinel readings are checked separately. Observation timezone remains unconfirmed."
    if n == 12:
        return f"{review['shelter_records']} source rows at {review['shelter_distinct_coordinates']} distinct coordinates; identity/activation not established."
    if n == 13:
        return f"{review['healthcare_records']} historical 2020 points within the search AOI; event availability unknown."
    if n == 14:
        terrain = review["terrain"]
        return f"{terrain['valid_pixels']} valid pixels; {terrain['negative_pixels']} negative elevations retained for review; min/max {terrain['min_m']:.2f}/{terrain['max_m']:.2f} m."
    return dataset["temporal"]["label"]


def _local_layers(summary: dict, normalized: Path, aoi_id: str) -> list[dict]:
    rows = []
    for category, number in (
        ("analysis_footprint", 1),
        ("accumulated_extent", 1),
        ("single_date_extent", 2),
        ("unobserved", 1),
    ):
        path = normalized / f"flood_{aoi_id}_{category}.geojson"
        if path.exists():
            rows.append(
                {
                    "id": category,
                    "title": category.replace("_", " ").title(),
                    "role": "historical_context",
                    "dataset_id": f"dataset-{number:02d}",
                    "availability": "partial",
                    "reason": "Local research context; public derivative permission unresolved.",
                    "data": json.loads(path.read_text(encoding="utf-8")),
                }
            )
    for name, number in (("shelter_candidates", 12), ("healthcare_candidates", 13)):
        path = normalized / f"{name}.geojson"
        if path.exists():
            collection = json.loads(path.read_text(encoding="utf-8"))
            # Adapter records retain AOI memberships. Spatial filtering uses the
            # exact upload geometry in the main builder below.
            rows.append(
                {
                    "id": name,
                    "title": name.replace("_", " ").title(),
                    "role": "historical_context",
                    "dataset_id": f"dataset-{number:02d}",
                    "availability": "partial",
                    "reason": "Local candidate review; historical availability unknown.",
                    "data": collection,
                }
            )
    river = normalized / f"rivers_{aoi_id}.geojson"
    if river.exists():
        rows.append(
            {
                "id": "rivers",
                "title": "Generalized HydroRIVERS",
                "role": "static_context",
                "dataset_id": "dataset-15",
                "availability": "partial",
                "reason": "Local context; not full local drainage.",
                "data": json.loads(river.read_text(encoding="utf-8")),
            }
        )
    return rows


def build_library(
    *,
    bundle_root: Path,
    locations_csv: Path,
    inventory_csv: Path,
    aoi_dir: Path,
    output_dir: Path,
    public_dir: Path,
    generated_at: str,
    context_root: Path | None = None,
    boundary_archive: Path | None = None,
    reuse_normalized: bool = False,
) -> dict:
    """Verify inputs, normalize locally, compute scenarios and project safe assets."""
    from shapely.geometry import shape

    from .evidence_adapters import normalize_bundle

    aois = load_aois(aoi_dir)
    registry = build_registry(
        bundle_root, locations_csv, inventory_csv, aois, generated_at
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = build_runtime_identity(context_enabled=context_root is not None)
    write_json(output_dir / "build_runtime.json", runtime)
    normalization_key = _runtime_bound_hash(
        {
            "manifest": registry["source_inventory_sha256"],
            "aois": {a["id"]: a["sha256"] for a in aois},
            "adapters": {
                name: sha256_file(Path(__file__).parent / name)
                for name in ("evidence_adapters.py", "evidence_adapters_geo.py")
            },
        },
        runtime,
    )
    receipt = output_dir / "normalization_receipt.json"
    previous = (
        json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    )
    if reuse_normalized and previous.get("key") == normalization_key:
        for path, expected in previous["outputs"].items():
            if sha256_file(safe_asset_path(output_dir, path)) != expected:
                raise ValueError("Changed normalized output")
        summary = json.loads(
            (output_dir / "adapter_summary.json").read_text(encoding="utf-8")
        )
    else:
        summary = normalize_bundle(bundle_root, output_dir, aois)
        files = ["adapter_summary.json", *summary["outputs"].values()]
        write_json(
            receipt,
            {
                "key": normalization_key,
                "build_runtime": runtime,
                "outputs": {p: sha256_file(output_dir / p) for p in sorted(set(files))},
            },
        )
    from .evidence_review import build_facility_crosswalk, enrich_registry

    registry = enrich_registry(registry, bundle_root, summary)
    review_path = output_dir / "facility_review/public_identity_reviews.json"
    reviews = (
        json.loads(review_path.read_text(encoding="utf-8"))
        if review_path.exists()
        else []
    )
    identity_review = build_facility_crosswalk(
        output_dir / "normalized", output_dir / "facility_review", reviews
    )
    summary["facility_identity_review"] = {
        k: v for k, v in identity_review.items() if k != "rows"
    }
    registry["transformation_version"] = TRANSFORMATION_VERSION
    gaps_path = output_dir / "acquisition" / "gap_register.json"
    if gaps_path.exists():
        from .evidence_acquisition import review_public_responses

        review_public_responses(output_dir / "acquisition", aois)
    from .evidence_population_review import build_population_review

    def review_input(name: str) -> list:
        path = output_dir / "review" / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    population_review = build_population_review(
        output_dir / "normalized",
        output_dir / "review",
        source_evidence=review_input("population_definition_evidence.json"),
        identity_reviews=review_input("public_identity_reviews.json"),
        generated_at=generated_at,
    )
    reporting_review, reporting_units, event_evidence = {}, {}, {}
    if boundary_archive is not None:
        from .evidence_event_review import build_event_review

        reporting_review = build_event_review(
            aoi_dir=aoi_dir,
            acquisition_dir=output_dir / "acquisition/event_review",
            output_dir=output_dir / "event_review",
            existing_boundary_zip=boundary_archive,
            prior_evidence_dir=output_dir,
            open_data_dir=bundle_root,
        )
        reporting_units = json.loads(
            (output_dir / "event_review/reporting_units.geojson").read_text(
                encoding="utf-8"
            )
        )
        event_evidence = json.loads(
            (output_dir / "event_review/event_evidence_review.json").read_text(
                encoding="utf-8"
            )
        )
    supplementary = {}
    for relative in (
        "facility_review/public_identity_reviews.json",
        "acquisition/gap_register.json",
        "acquisition/ngis/context_manifest.json",
    ):
        path = output_dir / relative
        if path.exists():
            supplementary[relative] = sha256_file(path)
    finals_by_aoi = {}
    for aoi in aois:
        directory = output_dir / ("finals" if aoi["id"] == "aoi-01_mae_sai_core" else "study_finals/" + aoi["id"])
        if not (directory / "build_receipt.json").is_file():
            continue
        from .evidence_finals_export import load_finals

        analysis, contexts = load_finals(directory, aoi_sha256=aoi["sha256"])
        if analysis["generated_at"] != generated_at:
            raise ValueError("Finals generation metadata differs from package")
        receipt = json.loads((directory / "build_receipt.json").read_bytes())
        for name in ("reporting_units", "reporting_crosswalk"):
            suffix = ".geojson" if name == "reporting_units" else ".json"
            if sha256_file(output_dir / "event_review" / (name + suffix)) != receipt[name + "_sha256"]:
                raise ValueError("Finals reporting geography differs from package")
        finals_by_aoi[aoi["id"]] = (analysis, contexts)
    for directory in (
        "review",
        "event_review",
        "acquisition/event_review",
        "finals",
        "study_finals",
        "flood_candidates",
        "destination_audits",
        "acquisition/shared_cases",
        "public_review",
    ):
        for path in sorted((output_dir / directory).rglob("*")):
            if path.is_file():
                supplementary[path.relative_to(output_dir).as_posix()] = sha256_file(
                    path
                )
    ngis_path = output_dir / "acquisition/ngis/context_manifest.json"
    ngis = (
        json.loads(ngis_path.read_text(encoding="utf-8"))
        if ngis_path.exists()
        else {"records": []}
    )
    for asset in ngis["records"]:
        if asset.get("status") == "downloaded_context_candidate":
            for key in ("file", "count_file"):
                expected = asset["sha256" if key == "file" else "count_sha256"]
                if (
                    sha256_file(safe_asset_path(ngis_path.parent, asset[key]))
                    != expected
                ):
                    raise ValueError("Supplementary NGIS asset checksum changed")
    registry["supplementary_evidence_hashes"] = supplementary
    registry["build_runtime"] = runtime
    write_json(output_dir / "evidence_registry.json", registry)
    # A changed implementation or configuration always creates a new version.
    implementation = {
        p.name: sha256_file(p)
        for p in sorted(Path(__file__).parent.glob("evidence_*.py"))
    }
    version = _runtime_bound_hash(
        {
            "registry": {k: v for k, v in registry.items() if k != "generated_at"},
            "implementation": implementation,
            "use_existing_context": context_root is not None,
            "context_manifest": sha256_file(
                Path(__file__).resolve().parents[2]
                / "outputs/open_context_data_file_manifest.csv"
            )
            if context_root
            else None,
        },
        runtime,
    )[:16]
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "package_version": version,
        "non_operational": True,
        "aois": [
            {
                k: a[k]
                for k in ("id", "name", "name_th", "geometry", "event_ids", "sha256")
            }
            for a in aois
        ],
        "events": registry["events"],
        "datasets": [public_dataset(d) for d in registry["datasets"]] + SUPPORTING,
        "packages": [],
    }
    if reporting_review:
        source = reporting_review["boundary_source"]
        admin = _supporting_dataset(
            "context-admin",
            "Official Thai subdistrict reporting boundaries (2022)",
            source["license"],
            source["source_url"],
            "static_context",
            reporting_review["assumptions"],
        )
        admin["source_urls"].append(source["license_url"])
        admin["rights"]["attribution"] = [source["attribution"]]
        admin["temporal"]["label"] = (
            "Source valid 22 January 2022; event-era boundary currency unverified"
        )
        catalog["datasets"].append(admin)
    public_dir.mkdir(parents=True, exist_ok=True)
    expected_files = {"catalog.json", "report.html"}
    public_packages = []
    local_packages = []
    scenarios_by_aoi = {}
    policies = {d["id"]: d for d in catalog["datasets"]}
    for aoi in aois:
        print(f"Building {aoi['id']}", flush=True)
        image_path = public_dir / "terrain" / (aoi["id"] + ".png")
        image_fields = _terrain_image(bundle_root, aoi["id"], image_path)
        expected_files.add("terrain/" + image_path.name)
        analytical_demo = int(aoi["id"][4:6]) in (1, 3, 5, 6)
        details = (
            build_illustrative_scenarios(aoi["id"], shape(aoi["geometry"]).bounds)
            if analytical_demo
            else {
                "aoi_id": aoi["id"],
                "source_timestamp": None,
                "confidence_class": "low",
                "operational_status": "non_operational",
                "assumptions": [
                    "Surrounding district/basin AOI supplies routing context for the corresponding core demonstration. This package presents evidence coverage and unresolved gaps; no district/basin access result is claimed."
                ],
                "access_scenarios": {},
                "capacity_scenarios": [],
                "assessment": {},
            }
        )
        context = None
        if context_root is not None and analytical_demo:
            from .evidence_context import build_context_inputs

            parent = (
                aois[1]
                if aoi["id"].startswith("aoi-01")
                else aois[3]
                if aoi["id"].startswith("aoi-03")
                else aoi
            )
            facilities = []
            for name in ("shelter_candidates", "healthcare_candidates"):
                collection = json.loads(
                    (output_dir / "normalized" / (name + ".geojson")).read_text(
                        encoding="utf-8"
                    )
                )
                for feature in collection["features"]:
                    if feature["geometry"] and shape(parent["geometry"]).covers(
                        shape(feature["geometry"])
                    ):
                        props = feature["properties"]
                        facilities.append(
                            {
                                "facility_id": props.get(
                                    "source_record_id",
                                    props.get(
                                        "record_id",
                                        hashlib.sha256(
                                            canonical_bytes(feature)
                                        ).hexdigest(),
                                    ),
                                ),
                                "longitude": feature["geometry"]["coordinates"][0],
                                "latitude": feature["geometry"]["coordinates"][1],
                                "capacity": None,
                                "facility_type": "shelter_candidate"
                                if name.startswith("shelter")
                                else "healthcare",
                                "identity_reconciled": False,
                            }
                        )
            context = build_context_inputs(
                context_root,
                aoi["geometry"],
                parent["geometry"],
                facilities,
                output_dir / "context" / aoi["id"],
            )
            write_json(
                output_dir / "context" / aoi["id"] / "context_inputs.json", context
            )
            _context_scenarios(
                context,
                aoi["id"],
                "supplied",
                output_dir / "context" / aoi["id"] / "local_facility_scenarios.json",
                reuse_normalized,
                runtime,
            )
            details = _context_scenarios(
                context,
                aoi["id"],
                "osm",
                output_dir / "context" / aoi["id"] / "osm_context_scenarios.json",
                reuse_normalized,
                runtime,
            )
        scenarios_by_aoi[aoi["id"]] = _compact_details(details)
        write_json(output_dir / "scenarios" / (aoi["id"] + ".json"), details)
        downloads = []
        if context:
            dbfile = public_dir / "databases" / (aoi["id"] + ".json.gz")
            dbfile.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(
                _public_context(context),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            dbfile.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
            expected_files.add("databases/" + dbfile.name)
            downloads = [
                {
                    "title": "OSM / WorldPop scenario database (ODbL / CC BY, gzip JSON)",
                    "url": PUBLIC_PREFIX + "databases/" + dbfile.name,
                    "sha256": sha256_file(dbfile),
                }
            ]
        for event in aoi["event_ids"]:
            identifier = f"{aoi['id']}_{event}"
            datasets = []
            for dataset in registry["datasets"]:
                if dataset_applies(dataset["number"], aoi["id"], event):
                    datasets.append(
                        {
                            "dataset_id": dataset["id"],
                            "availability": "available"
                            if dataset["rights"]["public_derivatives"]
                            else "metadata_only",
                            "coverage": _coverage(dataset, summary, aoi, event),
                            "qc": dataset["limitations"],
                            "summary": dataset["purpose"],
                        }
                    )
            layers = []
            local_layers = _local_layers(summary, output_dir / "normalized", aoi["id"])
            for layer in local_layers:
                if layer["id"].endswith("candidates"):
                    layer["data"]["features"] = [
                        f
                        for f in layer["data"]["features"]
                        if f["geometry"]
                        and shape(aoi["geometry"]).covers(shape(f["geometry"]))
                    ]
                layers.append(
                    {k: v for k, v in layer.items() if k != "data"}
                    | {
                        "availability": "metadata_only",
                        "reason": "Layer exists locally; public derivative permission remains unresolved. See source detail and local report.",
                    }
                )
            terrain_layer = {
                "id": "terrain",
                "title": "Copernicus GLO-30 surface elevation",
                "role": "static_context",
                "dataset_id": "dataset-14",
                "availability": "available",
                "reason": None,
                **image_fields,
            }
            layers.append(terrain_layer)
            if reporting_review:
                boundary_row = next(
                    row
                    for row in reporting_review["crosswalk"]["aois"]
                    if row["aoi_id"] == aoi["id"]
                )
                codes = {row["adm3_pcode"] for row in boundary_row["units"]}
                layers.append(
                    {
                        "id": "reporting-subdistricts",
                        "title": "Official subdistrict boundaries — 2022 reference",
                        "role": "static_context",
                        "dataset_id": "context-admin",
                        "availability": "partial",
                        "reason": "Full source polygons; analytical totals describe only their intersection with the selected AOI.",
                        "attribution": reporting_review["boundary_source"][
                            "attribution"
                        ],
                        "data": {
                            "type": "FeatureCollection",
                            "features": [
                                {k: v for k, v in feature.items() if k != "id"}
                                for feature in reporting_units["features"]
                                if feature["properties"]["adm3_pcode"] in codes
                            ],
                        },
                    }
                )
                datasets.append(
                    {
                        "dataset_id": "context-admin",
                        "availability": "partial",
                        "coverage": f"{len(codes)} intersecting subdistricts; {boundary_row['coverage_fraction']:.2%} of AOI covered. Unassigned land and ambiguous memberships remain explicit.",
                        "qc": policies["context-admin"]["limitations"],
                        "summary": "Royal Thai Survey Department / OCHA COD-AB, CC BY 3.0 IGO. AOI windows are not administrative units.",
                    }
                )
            if context:
                for key, title in (
                    ("road_geojson", "OSM routing context — display ways"),
                    ("osm_facilities_geojson", "OSM candidate destinations"),
                ):
                    if context.get(key):
                        layers.append(
                            {
                                "id": key,
                                "title": title,
                                "role": "static_context",
                                "dataset_id": "context-osm",
                                "availability": "partial",
                                "reason": "Historical OSM snapshot; not event passability or verified shelter activation. Full scenario graph is in the database download.",
                                "attribution": "© OpenStreetMap contributors · ODbL 1.0 · openstreetmap.org/copyright",
                                "data": _display_roads(
                                    output_dir
                                    / "context"
                                    / aoi["id"]
                                    / "osm_roads.geojson"
                                )
                                if key == "road_geojson"
                                else context[key],
                            }
                        )
                layers.append(
                    {
                        "id": "imposed-scenario-changes",
                        "title": "Explicit scenario changes — closure, removal and hypothetical destination",
                        "role": "scenario",
                        "dataset_id": "context-osm",
                        "availability": "available",
                        "reason": "Separate experiments, not simultaneous observed changes. Exact IDs and results are in scenario cards and the report.",
                        "attribution": "© OpenStreetMap contributors · ODbL 1.0 · FloodGuard scenario assumptions",
                        "data": _scenario_features(context, details),
                    }
                )
                coverage = context["coverage"]
                fraction = coverage["population_snap_coverage_fraction"]
                snap_share = (
                    "unavailable (no positive demand)"
                    if fraction is None
                    else f"{fraction:.2%}"
                )
                for key in ("context-osm", "context-worldpop"):
                    explanation = (
                        f"{len(context['edges'])} modelled edges; {coverage.get('connected_components', 'unknown')} disconnected graph components. Paths beyond the routing boundary are unevaluated. {coverage['connected_osm_facilities']}/{coverage['osm_facilities']} mapped sites satisfy the 100 m connector limit; generic shelters are context only."
                        if key == "context-osm"
                        else f"2020 modelled population {coverage['modelled_population_2020']:.2f}; {snap_share} within 250 m. {coverage['missing_or_invalid_population_cells']} nodata/invalid cells have unknown population, separate from known unsnapped demand."
                    )
                    datasets.append(
                        {
                            "dataset_id": key,
                            "availability": "partial",
                            "coverage": explanation,
                            "qc": policies[key]["limitations"],
                            "summary": policies[key]["title"],
                        }
                    )
            elif analytical_demo:
                layers.append(
                    {
                        "id": "illustrative-network",
                        "title": "Synthetic scenario diagram — not local roads",
                        "role": "scenario",
                        "dataset_id": "project-scenarios",
                        "availability": "available",
                        "reason": "Coordinates position a synthetic diagram only.",
                        "data": details["map_geojson"],
                    }
                )
            hashes = {
                "aoi_sha256": aoi["sha256"],
                "build_runtime_sha256": runtime["sha256"],
                "uv_lock_sha256": runtime["uv_lock_sha256"],
                "source_inventory_sha256": registry["source_inventory_sha256"],
                "scenario_sha256": hashlib.sha256(canonical_bytes(details)).hexdigest(),
            }
            if context:
                hashes.update(context["input_hashes"])
            hashes["population_review_sha256"] = hashlib.sha256(
                canonical_bytes(population_review)
            ).hexdigest()
            if reporting_review:
                hashes["event_review_sha256"] = hashlib.sha256(
                    canonical_bytes(reporting_review)
                ).hexdigest()
            event_assumptions = []
            if event == "mae_sai_2024":
                event_assumptions.append(
                    "The preserved /studio/ satellite comparator uses transformed uncalibrated amplitude and cross-border weak-reference metrics. Those metrics do not measure Thailand-side event accuracy and are not FPPS inputs here."
                )
            elif event == "hat_yai_2025":
                event_assumptions.append(
                    "Public metadata identifies the November 11/23 Sentinel-1 pair, but original SAFE archives were not acquired. These imposed access/capacity experiments are the explicit scenario fallback, not a satellite flood candidate."
                )
            else:
                event_assumptions.append(
                    "The 2024 and 2025 packages reuse the same historical OSM/WorldPop context and imposed scenarios. Their event evidence inventories differ; scenario differences between observed flood years are not claimed."
                )
            package = {
                "schema_version": SCHEMA_VERSION,
                "package_version": version,
                "id": identifier,
                "aoi_id": aoi["id"],
                "event_id": event,
                "generated_at": generated_at,
                "confidence_class": "low",
                "source_timestamp": None,
                "assumptions": [
                    "Mixed historical source dates are recorded per dataset; no common event observation timestamp.",
                    "Search AOIs are not administrative reporting boundaries.",
                    "Candidate/scenario outputs are not an official warning.",
                    *event_assumptions,
                    *details["assumptions"],
                ],
                "input_hashes": hashes,
                "dataset_mode": "candidate",
                "official_warning": False,
                "operational_status": "non_operational",
                "datasets": datasets,
                "layers": layers,
                "gauges": [],
                "assessment": _assessment(aoi["id"]),
                "scenarios": scenario_summaries(details),
                "decision_brief": build_decision_brief(
                    aoi_id=aoi["id"],
                    event_id=event,
                    generated_at=generated_at,
                    context=context,
                    details=details,
                    reporting_review=reporting_review,
                    reporting_units=reporting_units,
                    event_evidence=event_evidence,
                    population_review=population_review,
                ),
                "report_url": PUBLIC_PREFIX + "report.html",
                "downloads": downloads,
            }
            if aoi["id"] in finals_by_aoi:
                finals_analysis, finals_contexts = finals_by_aoi[aoi["id"]]
                from .evidence_finals_export import public_finals_database

                audit_path = output_dir / "destination_audits" / aoi["id"] / "destination_audit.json"
                if audit_path.is_file():
                    search = json.loads(audit_path.read_bytes())
                    if search["aoi_sha256"] != aoi["sha256"] or search["source_sha256"] != finals_contexts["walking"]["input_hashes"]["osm"]:
                        raise ValueError("Destination search belongs to different inputs")
                    package["datasets"].append({
                        "dataset_id": "context-destination-search", "availability": "partial",
                        "coverage": f"{search['search_radius_outside_core_m'] / 1000:g} km outside the demand AOI; existing OSM snapshot, points and site polygons.",
                        "summary": f"{search['hospital_count']} hospital-tagged source objects found; these are not necessarily distinct or operating hospitals. Routing eligibility is assessed separately.",
                        "qc": search["limitations"],
                    })
                if finals_analysis.get("flood_scenarios"):
                    flood = finals_analysis["flood_scenarios"]["walking"]
                    candidate_dir = output_dir / ("flood_candidate" if aoi["id"] == "aoi-01_mae_sai_core" else "flood_candidates/" + aoi["id"])
                    provenance = flood["candidate_provenance"]
                    for key, title in (("candidate_extent", "SAR change candidate — unvalidated"), ("observation_footprint", "SAR candidate analysis footprint — not a validation mask")):
                        path = candidate_dir / (key + ".geojson")
                        if sha256_file(path) != flood["candidate_provenance"]["products"][key]["sha256"]:
                            raise ValueError("Published flood geometry differs from its calculation")
                        package["layers"].append({"id": "sar-" + key, "title": title, "role": "candidate_estimate",
                                                 "dataset_id": "context-sar-candidate", "availability": "available",
                                                 "reason": provenance["rights"]["attribution"] + " Fixed amplitude-drop threshold; no validation or observed closure claim.",
                                                 "data": json.loads(path.read_bytes())})
                    package["datasets"].append({"dataset_id": "context-sar-candidate", "availability": "partial",
                                                "coverage": aoi["id"] + ": " + " to ".join(r["acquisition_date"] for r in provenance["sources"]) + "; candidate analysis coverage is separate from Thailand reporting coverage.",
                                                "qc": flood["candidate_provenance"]["limitations"], "summary": "Fixed-threshold SAR candidate drives an explicit road-intersection closure experiment."})
                package["decision_brief"]["finals_analysis"] = finals_analysis
                package["input_hashes"]["finals_analysis_sha256"] = finals_analysis[
                    "analysis_sha256"
                ]
                dbfile = public_dir / "databases" / (aoi["id"] + "-finals.json.gz")
                dbfile.write_bytes(
                    gzip.compress(
                        canonical_bytes(
                            public_finals_database(finals_analysis, finals_contexts)
                        ),
                        compresslevel=9,
                        mtime=0,
                    )
                )
                expected_files.add("databases/" + dbfile.name)
                package["downloads"] = [
                    *downloads,
                    {
                        "title": aoi["id"] + " service, route and sensitivity inputs (ODbL / CC BY, gzip JSON)",
                        "url": PUBLIC_PREFIX + "databases/" + dbfile.name,
                        "sha256": sha256_file(dbfile),
                    },
                ]
            local_package = {
                **package,
                "layers": [*local_layers, terrain_layer, *[
                    layer for layer in package["layers"]
                    if layer["dataset_id"] == "context-sar-candidate"
                ]],
                "local_detail_files": {
                    "adapter_summary": "adapter_summary.json",
                    "scenarios": "scenarios/" + aoi["id"] + ".json",
                },
                "coverage": summary["aois"][aoi["id"]],
            }
            write_json(output_dir / "packages" / (identifier + ".json"), local_package)
            local_packages.append(local_package)
            for layer in layers:
                validate_layer_export(layer, policies)
            assert_public_safe(package)
            path = public_dir / "packages" / (identifier + ".json")
            _public_json(path, package)
            expected_files.add("packages/" + path.name)
            catalog["packages"].append(
                {
                    "id": identifier,
                    "aoi_id": aoi["id"],
                    "event_id": event,
                    "url": PUBLIC_PREFIX + "packages/" + path.name,
                    "sha256": sha256_file(path),
                }
            )
            public_packages.append(package)
    assert_public_safe(catalog)
    write_json(public_dir / "catalog.json", catalog)
    gaps = (
        json.loads(gaps_path.read_text(encoding="utf-8"))
        if gaps_path.exists()
        else {"routes": []}
    )
    gaps["additional_context"] = ngis["records"]
    report = render_report(
        catalog, public_packages, registry, summary, gaps, scenarios_by_aoi
    )
    assert_public_safe(report)
    (public_dir / "report.html").write_text(report, encoding="utf-8")
    (output_dir / "public_evidence_report.html").write_text(report, encoding="utf-8")
    extras = {
        p.relative_to(public_dir).as_posix()
        for p in public_dir.rglob("*")
        if p.is_file()
    } - expected_files
    if extras:
        raise ValueError(f"Unlisted files in public export: {sorted(extras)}")
    export = {
        "schema_version": SCHEMA_VERSION,
        "package_version": version,
        "build_runtime": runtime,
        "source_verified_files": registry["verified_asset_count"],
        "physical_assets": len(registry["assets"]),
        "dataset_groups": 17,
        "aois": 6,
        "packages": 8,
        "files": {
            name: sha256_file(public_dir / name) for name in sorted(expected_files)
        },
        "policy": "Explicit field/layer projection; raw source files are never copied into the hosted directory.",
        "excluded_families": [
            d["id"]
            for d in registry["datasets"]
            if not d["rights"]["public_derivatives"]
        ],
    }
    write_json(output_dir / "public_export_report.json", export)
    from .evidence_local_report import render_local_report

    render_local_report(output_dir, registry, summary)
    return export


def render_report(
    catalog: dict,
    packages: list[dict],
    registry: dict,
    summary: dict,
    gaps: dict,
    scenario_details: dict,
) -> str:
    """Render a self-contained, printable report with no personal filesystem paths."""
    esc = lambda value: html.escape(str(value))
    rows = []
    for dataset in registry["datasets"]:
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{esc(value)}</td>"
                for value in (
                    dataset["number"],
                    dataset["title"],
                    dataset["temporal"]["label"],
                    dataset["role"],
                    dataset["purpose"],
                    dataset["rights"]["license"],
                    "; ".join(dataset["limitations"]),
                )
            )
            + "</tr>"
        )
    source_links = "".join(
        f"<li>{esc(d['title'])}: "
        + "; ".join(
            f'<a href="{esc(u)}">Publisher / terms</a>' for u in d["source_urls"]
        )
        + "</li>"
        for d in catalog["datasets"]
    )
    sections = []
    package_bindings = {entry["id"]: entry for entry in catalog["packages"]}
    for package in packages:
        binding = package_bindings[package["id"]]
        brief = package.get("decision_brief", {})
        context = brief.get("access") or {}
        brief_rows = "".join(
            f"<tr><td>{esc(unit['name'])} ({esc(unit['id'])})</td><td>{unit['unit_coverage_fraction']:.1%}</td><td>{esc((unit.get('population_context') or {}).get('modelled_population', 'unavailable'))}</td><td>{esc((unit.get('population_context') or {}).get('unknown_access_population', 'unavailable'))}</td></tr>"
            for unit in brief.get("reporting", {}).get("units", [])
        )
        concise = (
            (
                "<h3>Decision brief</h3><p>Review priority: verify consequential connections and destinations. Accepted FPPS, action class and flood-affected population remain unavailable.</p>"
                + f"<p>Modelled residential population (2020): {esc(context.get('modelled_population', 'unavailable'))}. Access unknown because no accepted graph connector: {esc(context.get('unknown_access_population', 'unavailable'))}. These counts are not flood exposure or evacuation demand.</p>"
                + "<table><tr><th>Subdistrict / code</th><th>Area inside AOI</th><th>Modelled residents in AOI intersection</th><th>Access unknown</th></tr>"
                + brief_rows
                + "</table>"
                + "<ul>"
                + "".join(
                    f"<li>{esc(item['kind'])}: gain/loss of 30-minute access {item['gaining_30_min_access']} / {item['losing_30_min_access']}; slower/faster population {item['slower_population']} / {item['faster_population']}; mean finite-route travel change {esc(item['mean_travel_time_delta_minutes'])} minutes. {esc(item['result'])}.</li>"
                    for item in brief.get("interventions", [])
                )
                + "</ul>"
                + "<details><summary>Source-review findings</summary><ul>"
                + "".join(
                    f"<li>{esc(note['summary'])} "
                    + " ".join(
                        f'<a href="{esc(url)}">Source</a>'
                        for url in note["source_urls"]
                    )
                    + "</li>"
                    for note in brief.get("evidence_notes", [])
                )
                + "</ul></details>"
            )
            if brief
            else ""
        )
        if "finals_analysis" in brief:
            finals = brief["finals_analysis"]
            routes = finals["routes"]
            origins = {row["id"]: row for row in routes["origins"]}
            route_rows = "".join(
                f"<tr><td>{esc(origins[row['origin_id']]['name'])}</td><td>{esc(row['service_type'])} / {esc(row['travel_mode'])}</td><td>{esc(row['scenario_kind'])}</td><td>{esc(row['baseline']['destination_name'] or 'unavailable')} / {esc(row['baseline']['total_minutes'])}</td><td>{esc(row['after']['destination_name'] or 'unavailable')} / {esc(row['after']['total_minutes'])}</td><td>{esc(row['delta_minutes'])}</td></tr>"
                for row in routes["comparisons"]
            )
            concise = (
                "<h3>Prepared public pins: service-specific before/after scenario</h3>"
                + f"<p>{esc(finals['question'])}</p><p>Thai-scope modelled residential population: {finals['scope']['in_scope_population']:,.2f}; outside-scope exclusion: {finals['scope']['excluded_population']:,.2f}. Mixed source years; no observed flood-affected population or accepted priority.</p>"
                + "<p>Prepared public site markers are not verified entrances. Before/after means an imposed disruption on the same model, not observed event-time road conditions. Hospital, primary care, pharmacy and shelter access remain separate.</p>"
                + "<table><tr><th>Starting place</th><th>Service / mode</th><th>Independent change</th><th>Before destination / minutes</th><th>After destination / minutes</th><th>Delta minutes</th></tr>"
                + route_rows
                + "</table>"
                + "<ul>"
                + "".join(f"<li>{esc(row)}</li>" for row in finals["limitations"])
                + "</ul>"
                + "<details><summary>Earlier mixed-service aggregate comparator — separate assumptions</summary>"
                + concise
                + "</details>"
            )
            if finals.get("flood_scenarios"):
                connection_review = finals.get("facility_connection_comparison", {}).get("walking", {}).get("fixed_edge_comparisons", [])
                spur_note = ""
                if connection_review:
                    spur = connection_review[0]
                    spur_note = f"<p>The original catastrophic closure of internal hospital spur 934550386 depended on its single assumed site connector. Two geometry-checked connections reduce the walking all-route loss for that same spur from {spur['original']['newly_unreachable_population']:,.1f} to {spur['revised']['newly_unreachable_population']:,.1f} residents. Neither connector is a surveyed entrance or evidence of event-time operation.</p>"
                provenance = finals["flood_scenarios"]["walking"]["candidate_provenance"]
                flood_rows = "".join(
                    f"<tr><td>{esc(mode)}</td><td>{len(result['closed_edges'])}</td><td>{result['candidate_affected_population']:,.1f}</td><td>{result['impact']['losing_30_min_access']:,.1f}</td><td>{result['impact']['newly_unreachable_population']:,.1f}</td></tr>"
                    for mode, result in finals["flood_scenarios"].items()
                )
                score_rows = "".join(
                    f"<tr><td>{esc(mode)} / {esc(unit['subdistrict_id'])}</td><td>{unit['candidate_affected_population']:,.1f}</td><td>"
                    + " / ".join(f"{row['fpps_0_100']:.2f} {esc(row['action_class'])}" for row in unit['assessment']['scenario_completions'])
                    + "</td><td>" + esc(" ".join(unit["missing_input_reasons"].values())) + "</td></tr>"
                    for mode, result in finals["flood_scenarios"].items() for unit in result["subdistricts"]
                )
                concise = (
                    "<h3>Candidate flood-driven population comparison</h3><p>" + esc(provenance["rights"]["attribution"]) + " " + esc(" to ".join(r["acquisition_date"] for r in provenance["sources"])) + f". Fixed {provenance['threshold_db']:g} dB uncalibrated amplitude-drop candidate; no independent validation. Every positive-length road intersection imposes a closure assumption, including bridges. Counts are modelled residents, not flood victims or observed isolation.</p>"
                    + "<table><tr><th>Mode</th><th>Imposed closures</th><th>Candidate-overlap residents</th><th>Lose 30-minute access</th><th>Lose all routes</th></tr>" + flood_rows + "</table>"
                    + "<p>Accepted FPPS remains unavailable: calibrated flood likelihood and compatible vulnerability/context are missing. The unchanged scorer produces low-confidence Class E for explicit 0/50/100 missing-input scenarios. Scores concern AOI intersections, not complete subdistricts.</p>"
                    + "<table><tr><th>Mode / reporting intersection</th><th>Candidate overlap</th><th>FPPS at 0 / 50 / 100 assumptions</th><th>Named missing inputs</th></tr>" + score_rows + "</table>"
                    + spur_note
                    + concise
                )
        table = "".join(
            f"<tr><td>{esc(s['title'])}</td><td>{esc(s['kind'])}</td><td>"
            + "<br>".join(
                f"{esc(m['label'])}: {esc(m['value'])} {esc(m.get('unit', ''))}"
                for m in s["metrics"]
            )
            + f"</td><td>{esc('; '.join(s['assumptions']))}</td></tr>"
            for s in package["scenarios"]
        )
        sections.append(
            f"<section><h2>{esc(package['id'])}</h2>{concise}<p>Actual FPPS and action class: unavailable. Fixed-weight sensitivity range 0–100; no qualified event input is silently filled.</p><ul>"
            + "".join(f"<li>{esc(a)}</li>" for a in package["assumptions"])
            + "".join(
                f"<li>{esc(d['dataset_id'])} — {esc(d['coverage'])}</li>"
                for d in package["datasets"]
            )
            + "</ul>"
            + f'<p><a href="{esc(binding["url"])}">Full evidence package and published map geometry (JSON)</a> — SHA-256 <code>{esc(binding["sha256"])}</code></p>'
            + "".join(
                f'<p><a href="{esc(d["url"])}">{esc(d["title"])}</a> — SHA-256 <code>{esc(d["sha256"])}</code></p>'
                for d in package.get("downloads", [])
            )
            + f"<table><tr><th>Experiment</th><th>Role</th><th>Results</th><th>Assumptions</th></tr>{table}</table></section>"
        )
    gap_table = "".join(
        f'<tr><td>{esc(r["id"])}</td><td><a href="{esc(r["url"])}">Public route</a></td><td>{esc(r["access"])}</td><td>{esc(r["fallback"])}</td></tr>'
        for r in gaps["routes"]
    )
    additional = "".join(
        f"<tr><td>{esc(r['aoi_id'])}</td><td>{esc(r['service'])}</td><td>{esc(r.get('feature_count', 'unavailable'))}</td><td>{esc(r['sha256'])}</td></tr>"
        for r in gaps.get("additional_context", [])
        if r.get("status") == "downloaded_context_candidate"
    )
    compact_scenarios = {
        aoi: report_scenario_projection(details)
        for aoi, details in scenario_details.items()
    }
    appendix = {
        "projection": REPORT_PROJECTION,
        "omitted_detail_fields": sorted(REPORT_OMITTED_FIELDS),
        "package_version": catalog["package_version"],
        "build_runtime": registry.get("build_runtime"),
        "source_inventory_sha256": registry["source_inventory_sha256"],
        "aois": catalog["aois"],
        "datasets": catalog["datasets"],
        "scenarios": compact_scenarios,
        "decision_briefs": [report_brief_projection(package.get("decision_brief")) for package in packages],
        "downloadable_packages": catalog["packages"],
        "package_inputs": {
            package["id"]: package["input_hashes"] for package in packages
        },
        "package_downloads": {
            package["id"]: package.get("downloads", []) for package in packages
        },
        "osm_derivative_notice": "Any OSM-derived road/site database in these packages and appendix is offered under Open Database License 1.0: https://opendatacommons.org/licenses/odbl/1-0/ . © OpenStreetMap contributors. WorldPop-derived modelled population retains CC BY 4.0 attribution. Scenario changes are FloodGuard assumptions.",
    }
    assert_public_safe(appendix)
    # Readable JSON in a details element makes this a downloadable analytical
    # receipt and a redistributable derivative-database offer, without scripts.
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>FloodGuard evidence report</title><style>body{font:15px/1.5 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#16364b}h1{font-size:32px}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #b8cbd5;padding:9px;vertical-align:top;overflow-wrap:anywhere}th{background:#e7f1f4;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:10px}.note{background:#fff1ca;padding:16px}section{break-before:page}@media print{body{margin:12mm}thead{display:table-header-group}tr{break-inside:avoid}}</style><body>'
        + f'<h1>FloodGuard · Evidence and scenario report</h1><p>Package {esc(catalog["package_version"])} · generated {esc(catalog["generated_at"])}</p><p class="note">Non-operational research demonstration. Historical observations, candidate estimates and imposed scenarios do not establish event-specific flood accuracy, actual shelter availability or observed road passability.</p><p>{registry["verified_asset_count"]} source files verified; 17 acquired dataset selections across six AOIs and eight event packages. Raw files remain outside the hosted export. Gauge observations and unresolved-rights geometries are available only in the local research package. No private agency export is required.</p><h2>Acquired dataset inventory</h2><table><tr><th>#</th><th>Dataset</th><th>Time meaning</th><th>Role</th><th>Purpose</th><th>Rights</th><th>Limitations</th></tr>'
        + "".join(rows)
        + "</table><h2>Public source checks and unresolved gaps</h2><table><tr><th>Gap</th><th>Website</th><th>Access result</th><th>Fallback</th></tr>"
        + gap_table
        + "</table><h2>Additional public website acquisitions</h2><p>NGIS/DWR natural streams and water bodies were downloaded as full features intersecting each AOI rectangle. Counts overlap between AOIs. Observation epoch and redistribution terms remain unresolved, so geometry stays local and is not an event flood mask or a complete drainage inventory.</p><table><tr><th>AOI</th><th>Service</th><th>Features</th><th>SHA-256</th></tr>"
        + additional
        + "</table><h2>Source and license links</h2><ul>"
        + source_links
        + "</ul>"
        + "".join(sections)
        + "<h2>Reproducibility appendix</h2><p>The JSON below retains exact scenario settings, input identities and aggregate results. Detailed per-cell allocations and routing tables remain in the local research artifacts. Full published map geometry is in the linked evidence packages; the ODbL road, site and modelled-population databases are offered through the separate checksum-bound downloads above. Synthetic diagrams are explicitly identified; OSM/WorldPop scenarios are historical estimates.</p><details><summary>Show compact analytical receipt and database download bindings</summary><pre>"
        + esc(canonical_bytes(appendix).decode())
        + "</pre></details></body></html>"
    )
