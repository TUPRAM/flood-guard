"""Immutable, purpose-specific intake for heterogeneous research evidence.

This registry is independent of qualified-reference ingestion. Availability is
never an authorization to publish an asset or to validate a flood model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import ntpath
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "1.0"
ROLES = {
    "event_observation",
    "historical_context",
    "static_context",
    "candidate_estimate",
    "scenario",
    "unresolved",
}
USES = (
    "local_processing",
    "hosted_display",
    "downloadable_derivatives",
    "model_labels",
    "validation",
)
AOI_NAMES = (
    ("Mae Sai core", "แม่สาย พื้นที่หลัก"),
    ("Mae Sai district", "อำเภอแม่สาย"),
    ("Hat Yai core", "หาดใหญ่ พื้นที่หลัก"),
    ("Hat Yai basin", "ลุ่มน้ำหาดใหญ่"),
    ("Bang Ban / Sena", "บางบาล / เสนา"),
    ("Rangsit", "รังสิต"),
)
EVENTS = [
    {
        "id": "mae_sai_2024",
        "name": "Mae Sai · September 2024",
        "name_th": "แม่สาย · กันยายน 2567",
        "start": "2024-09-01",
        "end": "2024-09-30",
    },
    {
        "id": "hat_yai_2025",
        "name": "Hat Yai · November 2025",
        "name_th": "หาดใหญ่ · พฤศจิกายน 2568",
        "start": "2025-11-01",
        "end": "2025-11-30",
    },
    {
        "id": "chao_phraya_2024",
        "name": "Lower Chao Phraya · 2024",
        "name_th": "เจ้าพระยาตอนล่าง · 2567",
        "start": "2024-09-01",
        "end": "2024-11-30",
    },
    {
        "id": "chao_phraya_2025",
        "name": "Lower Chao Phraya · 2025",
        "name_th": "เจ้าพระยาตอนล่าง · 2568",
        "start": "2025-09-01",
        "end": "2025-11-30",
    },
]

# Dataset-specific policies are deliberately conservative. Missing legal detail
# is not repaired by a generic "government" or "open data" classification.
_POLICY = {
    "flood": (
        "CC BY-SA; version unresolved",
        "https://data.humdata.org/dataset/water-extents-from-1-aug-2024-to-22-october-2024-over-chiang-rai-province",
        "UNOSAT / GISTDA",
        False,
    ),
    "gauges": (
        "CC Attribution Non-Commercial; version unresolved",
        "https://gdcatalog.go.th/dataset/gdpublish-water-level",
        "Hydro-Informatics Institute (HII)",
        False,
    ),
    "population": (
        "Open Data Common; legal variant unresolved",
        "https://stat.bora.dopa.go.th/",
        "DOPA and provincial government data catalogs",
        False,
    ),
    "shelters": (
        "Open Data Common; legal variant unresolved",
        "https://gdcatalog.go.th/en/dataset/gdpublish-dsc_11_01",
        "Department of Disaster Prevention and Mitigation",
        False,
    ),
    "healthcare": (
        "CC BY; version unresolved",
        "https://data.opendevelopmentmekong.net/dataset/health-facilities-in-thailand-2020",
        "DGA CITIZENinfo via Open Development Mekong",
        False,
    ),
    "terrain": (
        "Copernicus GLO-30-F license",
        "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf",
        "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved",
        True,
    ),
    "rivers": (
        "HydroSHEDS custom license; no standalone redistribution",
        "https://www.hydrosheds.org/products/hydrorivers",
        "HydroSHEDS / HydroRIVERS, WWF; Lehner and Grill (2013)",
        False,
    ),
    "roads": (
        "Public documentary evidence; derivative reuse unresolved",
        "https://www.prd.go.th/",
        "Department of Highways / Public Relations Department",
        False,
    ),
}
FAMILIES = {
    1: "flood",
    2: "flood",
    3: "gauges",
    4: "gauges",
    5: "gauges",
    6: "population",
    7: "population",
    8: "population",
    9: "population",
    10: "population",
    11: "population",
    12: "shelters",
    13: "healthcare",
    14: "terrain",
    15: "rivers",
    16: "roads",
    17: "roads",
}
PERIODS = {
    1: (
        "2024-08-01",
        "2024-10-22",
        "conflicting_cumulative_interval",
        "1 August–22 October 2024; layer name ends 12 October",
    ),
    2: (
        "2024-10-22",
        "2024-10-22",
        "observation",
        "22 October 2024; later observation, not September",
    ),
    3: (
        "2024-09-01",
        "2024-11-30",
        "observation",
        "September–November 2024; measurements incomplete",
    ),
    4: (
        "2025-09-01",
        "2025-11-30",
        "observation",
        "September–November 2025; measurements incomplete",
    ),
    5: ("2025-11-01", "2025-11-30", "observation", "November 2025; event-period gaps"),
    6: (None, None, "reference_year", "2018–2023; ปี 2561–2566"),
    7: (None, None, "reference_year", "2025; ปี 2568; not observed 2024 ages"),
    8: (None, None, "reference_year", "2022–2025"),
    9: (None, None, "reference_year", "2018–2024; provincial age bands"),
    10: (None, None, "reference_year", "2019–2025; district and sex, no age bands"),
    11: (None, None, "reference_year", "2023–2025; village registration context"),
    12: (None, None, "inventory_snapshot", "2024 inventory; activation unknown"),
    13: (None, None, "reference_year", "2020 historical healthcare inventory"),
    14: (None, None, "static_release", "2021 release; historical surface elevation"),
    15: (None, None, "static_release", "Version 1; generalized historical network"),
    16: ("2024-09-11", "2024-09-11", "documentary_report", "11 September 2024"),
    17: ("2025-11-27", "2025-11-27", "documentary_report", "27 November 2025"),
}
LIMITATIONS = {
    1: [
        "October 12/22 temporal conflict is unresolved.",
        "No dates for individual patches; September-only extent cannot be recovered.",
        "Outside the analysis footprint is unobserved, not dry.",
        "Source confidence codes are not calibrated percentages.",
    ],
    2: [
        "An October water observation cannot validate September flood accuracy.",
        "Provider source-area fields are not AOI-clipped areas.",
    ],
    3: [
        "Missing readings remain visible; maximum observed level is not necessarily the event peak.",
        "Observation timezone and ambiguous station metadata fields remain unresolved.",
    ],
    4: [
        "Station availability differs from 2024.",
        "No interpolation or verified satellite time alignment while timezone is unresolved.",
    ],
    5: [
        "All four stations have event-period gaps.",
        "ONE037 is outside the uploaded basin AOI; regional context is not local substitution.",
    ],
    6: [
        "No 2024 age records.",
        "Age definitions and overlapping elderly groups need reconciliation.",
        "District statistics are not observed subdistrict/AOI counts.",
    ],
    7: [
        "Shares from 2025 are not observed 2024 counts.",
        "Same three physical files as dataset 6.",
        "Mae Sai 2025 age-category total differs from district total by 37.",
    ],
    8: ["Registered district total is not population inside a search rectangle."],
    9: [
        "Provincial scale; allocating to subdistricts requires explicit assumptions.",
        "No observed 2025 age structure.",
    ],
    10: ["No age bands; district totals cannot directly establish AOI vulnerability."],
    11: [
        "Municipality/village registration coverage and administrative codes need reconciliation."
    ],
    12: [
        "Source update 6 May and file modification 9 August 2024 are not activation dates.",
        "Shared coordinates are unresolved facility identities; capacities must not be summed blindly.",
        "Unknown event availability and capacity remain null.",
    ],
    13: [
        "Historical 2020 derivative; current and event-time operation unknown.",
        "Repeated source IDs are not unique facility identifiers.",
    ],
    14: [
        "DSM includes vegetation and buildings; not bare-earth terrain or flood depth.",
        "Negative values remain under review; no fine drainage or hydraulic modelling.",
        "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.",
    ],
    15: [
        "Missing local drains, culverts and canals do not mean no drainage.",
        "Full-reach and clipped lengths differ; downstream links may leave the AOI.",
    ],
    16: [
        "Route/district and article/photo chainage conflicts remain unresolved.",
        "Documentary evidence is not an observed geocoded closure layer.",
    ],
    17: [
        "Narrative recovery announcement contains no segment-level passability inventory."
    ],
}


def sha256_file(path: Path) -> str:
    """Hash a file without loading a raster/archive into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    """Serialize deterministic UTF-8 JSON, rejecting NaN and infinity."""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def safe_asset_path(root: Path, relative: str) -> Path:
    """Resolve a relative asset while rejecting traversal and absolute paths."""
    name = relative.replace("\\", "/")
    parsed = PurePosixPath(name)
    if (
        not name
        or parsed.is_absolute()
        or ".." in parsed.parts
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise ValueError("Unsafe evidence asset path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Evidence asset leaves configured root")
    return path


def verify_bundle(root: Path) -> dict[str, dict[str, Any]]:
    """Verify every recorded source asset; a mismatch prevents integration."""
    result = {}
    with (root / "FILES_SHA256.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            path = safe_asset_path(root, row["path"])
            if row["path"] in result:
                raise ValueError("Duplicate asset path in checksum inventory")
            if (
                not path.is_file()
                or path.stat().st_size != int(row["bytes"])
                or sha256_file(path) != row["sha256"]
            ):
                raise ValueError(f"Evidence integrity failure: {row['path']}")
            result[row["path"]] = {
                "relative_path": row["path"],
                "sha256": row["sha256"],
                "bytes": int(row["bytes"]),
            }
    if not result:
        raise ValueError("Empty checksum inventory")
    return result


def use_policy(family: str) -> dict[str, Any]:
    """Return reviewable per-purpose policy, never a blanket open-data flag."""
    license_name, url, attribution, publish = _POLICY[family]
    uses = {use: "unresolved" for use in USES}
    uses["local_processing"] = "permitted_research_context"
    uses["model_labels"] = uses["validation"] = "not_qualified"
    if publish:
        uses["hosted_display"] = uses["downloadable_derivatives"] = (
            "permitted_with_attribution"
        )
    return {
        "status": "public_derivatives_permitted"
        if publish
        else "local_context_public_derivatives_unresolved",
        "license": license_name,
        "public_derivatives": publish,
        "attribution": [attribution],
        "evidence_url": url,
        "uses": uses,
    }


def load_aois(directory: Path) -> list[dict[str, Any]]:
    """Read and hash the six uploaded search polygons, retaining their meaning."""
    result = []
    for index, path in enumerate(sorted(directory.glob("aoi-*.geojson"))):
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        feature = obj["features"][0] if obj.get("type") == "FeatureCollection" else obj
        number = int(path.name.split("_")[0].split("-")[1])
        name, thai = AOI_NAMES[number - 1]
        event_ids = (
            [EVENTS[0]["id"]]
            if number <= 2
            else [EVENTS[1]["id"]]
            if number <= 4
            else [EVENTS[2]["id"], EVENTS[3]["id"]]
        )
        result.append(
            {
                "id": path.stem,
                "name": name,
                "name_th": thai,
                "geometry": feature["geometry"],
                "event_ids": event_ids,
                "sha256": sha256_file(path),
                "geographic_role": "search_polygon_not_administrative_boundary",
            }
        )
    if len(result) != 6 or len({r["id"] for r in result}) != 6:
        raise ValueError("Expected exactly six distinct upload AOIs")
    return result


def build_registry(
    bundle_root: Path,
    locations_csv: Path,
    inventory_csv: Path,
    aois: list[dict],
    generated_at: str,
) -> dict:
    """Normalize 17 selections and deduplicate physical assets by relative path."""
    checked = verify_bundle(bundle_root)
    with locations_csv.open(encoding="utf-8-sig", newline="") as stream:
        locations = list(csv.DictReader(stream))
    with inventory_csv.open(encoding="utf-8-sig", newline="") as stream:
        inventory = list(csv.DictReader(stream))
    source_root = ntpath.commonpath([r["absolute_file_path"] for r in locations])
    assets: dict[str, dict] = {}
    by_group: dict[int, list[str]] = {n: [] for n in range(1, 18)}
    for row in locations:
        n = int(row["dataset_row"])
        relative = ntpath.relpath(row["absolute_file_path"], source_root).replace(
            "\\", "/"
        )
        safe_asset_path(bundle_root, relative)
        if relative not in checked:
            raise ValueError(f"Unverified inventory asset: {relative}")
        source = checked[relative]
        asset_id = (
            "asset-"
            + hashlib.sha256((relative + "\0" + source["sha256"]).encode()).hexdigest()[
                :24
            ]
        )
        assets.setdefault(
            asset_id,
            {
                "id": asset_id,
                **source,
                "family": FAMILIES[n],
                "role": "source_or_recorded_derivative",
                "parent_hashes": [],
            },
        )
        by_group[n].append(asset_id)
    datasets = []
    for row in inventory:
        n = int(row["#"])
        family = FAMILIES[n]
        start, end, kind, label = PERIODS[n]
        role = (
            "static_context"
            if n in (14, 15)
            else "event_observation"
            if n in (3, 4, 5, 16, 17)
            else "historical_context"
        )
        temporal = {
            "start": start,
            "end": end,
            "kind": kind,
            "label": label,
            "publication_date": None,
            "source_update_date": None,
            "modified_date": None,
            "release_version": None,
            "activation_date": None,
            "reference_years": [],
            "conflict": n == 1,
            "assertions": [],
        }
        if n == 1:
            temporal["assertions"] = [
                {"field": "description_and_attribute_end", "value": "2024-10-22"},
                {"field": "layer_name_end", "value": "2024-10-12"},
            ]
        if n == 12:
            temporal.update(source_update_date="2024-05-06", modified_date="2024-08-09")
        if n in (14, 15):
            temporal["release_version"] = "2021" if n == 14 else "1.0"
        if n in (6, 7, 8, 9, 10, 11, 13):
            temporal["reference_years"] = {
                6: list(range(2018, 2024)),
                7: [2025],
                8: list(range(2022, 2026)),
                9: list(range(2018, 2025)),
                10: list(range(2019, 2026)),
                11: [2023, 2024, 2025],
                13: [2020],
                14: [2021],
            }[n]
        policy = use_policy(family)
        datasets.append(
            {
                "id": f"dataset-{n:02d}",
                "number": n,
                "title": row["Upload / data acquired"],
                "family": family,
                "role": role,
                "source_urls": [policy["evidence_url"]],
                "temporal": temporal,
                "limitations": LIMITATIONS[n],
                "rights": policy,
                "asset_ids": by_group[n],
                "selection": row.get("Record selection", "All source records"),
                "purpose": row["Purpose"],
                "geographic_level": row["Dataset type"],
            }
        )
    if len(datasets) != 17 or {d["number"] for d in datasets} != set(range(1, 18)):
        raise ValueError("Inventory must contain exactly groups 1–17")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "non_operational": True,
        "source_inventory_sha256": sha256_file(bundle_root / "FILES_SHA256.csv"),
        "verified_asset_count": len(checked),
        "aois": aois,
        "events": EVENTS,
        "datasets": datasets,
        "assets": sorted(assets.values(), key=lambda x: x["id"]),
    }


def assert_public_safe(value: Any) -> None:
    """Reject local paths, secrets, personal fields and non-finite JSON values."""
    encoded = canonical_bytes(value).decode()
    if re.search(
        r"(?<![A-Za-z])[A-Za-z]:[\\/]|file://|/Users/|/home/", encoded, re.IGNORECASE
    ):
        raise ValueError("Local filesystem path in public evidence")
    forbidden = {
        "password",
        "access_token",
        "refresh_token",
        "coordinator_name",
        "telephone",
        "phone",
        "absolute_file_path",
        "local_path",
        "เบอร์โทร",
        "โทรศัพท์",
        "ผู้ประสานงาน",
        "ชื่อผู้ประสานงาน",
        "เบอร์โทรศัพท์",
    }

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            if forbidden.intersection(k.lower() for k in item):
                raise ValueError("Private field in public evidence")
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)


def validate_layer_export(layer: dict, datasets: dict[str, dict]) -> None:
    """Fail if public data objects are not covered by a specific permission."""
    if layer.get("data") is None and layer.get("image_url") is None:
        return
    if layer["role"] == "scenario" and layer["dataset_id"] == "project-scenarios":
        if (
            not datasets.get("project-scenarios", {})
            .get("rights", {})
            .get("public_derivatives")
        ):
            raise ValueError("Synthetic scenario source must be explicitly allowlisted")
        return
    dataset = datasets.get(layer["dataset_id"])
    if not dataset or not dataset["rights"]["public_derivatives"]:
        raise ValueError(f"Public derivative is not permitted: {layer['dataset_id']}")


def dataset_applies(number: int, aoi_id: str, event_id: str) -> bool:
    """Return explicit AOI/event association, without legacy Mae Sai fallback."""
    aoi = int(aoi_id[4:6])
    if number in (1, 2, 6, 7, 8, 16):
        return aoi in (1, 2)
    if number == 3:
        return aoi in (5, 6) and event_id.endswith("2024")
    if number == 4:
        return aoi in (5, 6) and event_id.endswith("2025")
    if number in (5, 10, 11, 17):
        return aoi in (3, 4)
    if number == 9:
        return aoi == 6
    return number in (12, 13, 14, 15)
