"""Fail-closed verification of the static evidence export and local lineage."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from .evidence_catalog import (
    FAMILIES,
    assert_public_safe,
    dataset_applies,
    safe_asset_path,
    sha256_file,
    use_policy,
    validate_layer_export,
)
from .scoring import DEFAULT_WEIGHTS

PREFIX = "/evidence-library/"
HASH = re.compile(r"^[a-f0-9]{64}$")
PUBLIC_DATASETS = {"dataset-14", "context-osm", "context-worldpop", "project-scenarios"}
DATABASE_KEYS = {
    "license",
    "source_urls",
    "attribution",
    "confidence_class",
    "source_timestamp",
    "source_metadata",
    "assumptions",
    "input_hashes",
    "analysis_crs",
    "node_coordinates",
    "population",
    "edges",
    "osm_facilities",
    "coverage",
    "non_operational",
    "official_warning",
    "dataset_mode",
}
SOURCE_METADATA_KEYS = {
    "download_url",
    "license_status",
    "processing_scope",
    "retrieved_at_utc",
    "sha256",
    "source_name",
    "source_url",
}
POPULATION_KEYS = {
    "population_id",
    "subdistrict_id",
    "total_population",
    "node_id",
    "snap_distance_m",
    "longitude",
    "latitude",
    "population_reference_year",
    "population_role",
}
EDGE_KEYS = {
    "edge_id",
    "from_node",
    "to_node",
    "length_m",
    "road_class",
    "normal_minutes",
    "osm_way_id",
    "bridge",
    "layer",
    "tunnel",
}
OSM_SITE_KEYS = {
    "facility_id",
    "name",
    "facility_type",
    "geometry",
    "capacity",
    "identity_reconciled",
    "source_name",
    "source_license",
    "activation_status",
    "osm_amenity",
    "osm_shelter_type",
    "source_description",
    "candidate_destination_eligible",
    "emergency_shelter_role",
    "longitude",
    "latitude",
    "node_id",
    "snap_distance_m",
    "within_routing_context",
    "connector_walkability",
}


class EvidenceValidationError(ValueError):
    """The exported bytes or their declared provenance are inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceValidationError(message)


def _json(data: bytes | str, label: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, f"Duplicate JSON key in {label}")
            result[key] = value
        return result

    def invalid(value):
        raise EvidenceValidationError(f"Non-finite JSON in {label}")

    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, UnicodeError) as error:
        raise EvidenceValidationError(f"Invalid JSON in {label}: {error}") from error


def _read(path: Path) -> Any:
    _require(path.is_file(), f"Missing asset: {path.name}")
    return _json(path.read_bytes(), path.name)


def _unique(rows: list[dict], key: str, label: str) -> dict[str, dict]:
    result = {row[key]: row for row in rows}
    _require(len(result) == len(rows), f"Duplicate {label} identifiers")
    return result


def _asset(root: Path, url: str) -> tuple[str, Path]:
    _require(
        isinstance(url, str) and url.startswith(PREFIX), "Unsafe public asset prefix"
    )
    name = url[len(PREFIX) :]
    _require(
        bool(
            re.fullmatch(
                r"[A-Za-z0-9_/-]+\.(?:json(?:\.gz)?|geojson|md|html|txt|csv|pdf|png|webp)",
                name,
            )
        ),
        "Unsafe public asset path",
    )
    _require(
        all(part not in {"", ".", ".."} for part in name.split("/")),
        "Unsafe public asset segment",
    )
    path = safe_asset_path(root, name)
    _require(
        not any(
            (root / Path(*Path(name).parts[:i])).is_symlink()
            for i in range(1, len(Path(name).parts) + 1)
        ),
        "Symlink public asset",
    )
    _require(path.is_file(), f"Missing public asset: {name}")
    return name, path


def _schema(value: Any, name: str, schemas: Path) -> None:
    validator = Draft202012Validator(
        _read(schemas / f"{name}.schema.json"), format_checker=FormatChecker()
    )
    error = next(validator.iter_errors(value), None)
    if error is not None:
        location = "/".join(map(str, error.absolute_path))
        raise EvidenceValidationError(f"Schema {name} at {location}: {error.message}")


def _hash(expected: str, actual: str, label: str) -> None:
    _require(
        isinstance(expected, str) and HASH.fullmatch(expected) is not None,
        f"Invalid SHA256: {label}",
    )
    _require(expected == actual, f"SHA256 mismatch: {label}")


def _geometry_hash(geometry: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            geometry,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _assessment(assessment: dict) -> None:
    components = _unique(assessment["components"], "id", "assessment component")
    _require(
        set(components) == set(DEFAULT_WEIGHTS),
        "FPPS components differ from the strict scorer",
    )
    for key, weight in DEFAULT_WEIGHTS.items():
        _require(components[key]["weight"] == weight, "FPPS weights were changed")
        _require(
            components[key]["value"] is None,
            "Primary evidence FPPS must retain unknown components",
        )
    _require(
        assessment["bounds"] == {"lower": 0, "upper": 100},
        "Primary FPPS arithmetic bounds changed",
    )


def _database(payload: dict, package: dict, policies: dict[str, dict]) -> None:
    _require(set(payload) == DATABASE_KEYS, "Unexpected source keys in public database")
    assert_public_safe(payload)
    for source in ("context-osm", "context-worldpop"):
        _require(
            policies.get(source, {}).get("rights", {}).get("public_derivatives")
            is True,
            f"Database source publication not permitted: {source}",
        )
    _require(
        payload["confidence_class"] == "low" and payload["source_timestamp"] is None,
        "Database cannot claim event-time confidence",
    )
    _require(
        payload["non_operational"] is True
        and payload["official_warning"] is False
        and payload["dataset_mode"] == "candidate",
        "Database safety status changed",
    )
    _require(
        payload["analysis_crs"] == "EPSG:32647", "Unexpected scenario analysis CRS"
    )
    _require(
        payload["input_hashes"]
        and all(
            package["input_hashes"].get(key) == value
            for key, value in payload["input_hashes"].items()
        ),
        "Mixed database/package input hashes",
    )
    _require(
        {"osm", "worldpop", "aoi_geometry", "routing_geometry"}
        <= payload["input_hashes"].keys(),
        "Database source hashes are incomplete",
    )
    metadata = payload["source_metadata"]
    _require(
        isinstance(metadata, dict) and set(metadata) == {"osm", "worldpop"},
        "Public database source metadata must identify exactly OSM and WorldPop",
    )
    for source, details in metadata.items():
        _require(
            isinstance(details, dict) and set(details) == SOURCE_METADATA_KEYS,
            f"Unexpected source metadata keys: {source}",
        )
        _require(
            all(isinstance(value, str) and value.strip() for value in details.values()),
            f"Source metadata must contain nonempty strings: {source}",
        )
        for key in ("source_url", "download_url"):
            url = details[key]
            parsed = urlsplit(url)
            _require(
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and "\\" not in url
                and not any(character.isspace() for character in url),
                f"Source metadata URL must use HTTPS: {source}/{key}",
            )
        timestamp = details["retrieved_at_utc"]
        try:
            retrieved = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            valid_utc = retrieved.utcoffset() == timezone.utc.utcoffset(None)
        except ValueError:
            valid_utc = False
        _require(
            valid_utc
            and re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", timestamp
            )
            is not None
            and timestamp.endswith(("Z", "+00:00")),
            f"Source retrieval timestamp must be valid UTC: {source}",
        )
        _hash(
            details["sha256"],
            payload["input_hashes"][source],
            f"source metadata {source}",
        )
    nodes = payload["node_coordinates"]
    _require(isinstance(nodes, dict), "Invalid database nodes")
    for field, key, allowed in (
        ("population", "population_id", POPULATION_KEYS),
        ("edges", "edge_id", EDGE_KEYS),
        ("osm_facilities", "facility_id", OSM_SITE_KEYS),
    ):
        _unique(payload[field], key, field)
        for row in payload[field]:
            _require(set(row) == allowed, f"Unexpected source keys in database {field}")
            if field == "population":
                _require(
                    row["population_reference_year"] == 2020
                    and row["total_population"] >= 0,
                    "Population must remain modelled 2020 context",
                )
            elif field == "edges":
                _require(
                    row["from_node"] in nodes and row["to_node"] in nodes,
                    "Database edge references an absent node",
                )
            else:
                _require(
                    row["facility_id"].startswith("OSM-node-")
                    and row["source_license"] == "ODbL-1.0",
                    "Non-OSM source in public OSM facility projection",
                )
                _require(
                    row["capacity"] is None and row["identity_reconciled"] is False,
                    "Public source capacity/identity was promoted",
                )
                _require(
                    row["facility_type"] in {"healthcare", "shelter_context"},
                    "Unreviewed emergency shelter role",
                )
                _require(
                    row["candidate_destination_eligible"]
                    == (row["facility_type"] == "healthcare"),
                    "Generic OSM shelter cannot be an access destination",
                )
            if "node_id" in row:
                _require(
                    row["node_id"] is None or row["node_id"] in nodes,
                    "Database connector references absent node",
                )


class _ReportParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.receipts: list[str] = []
        self._pre: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        _require(
            tag not in {"script", "iframe", "object", "embed"},
            "Active content in public report",
        )
        for key, value in attrs:
            _require(not key.lower().startswith("on"), "Executable report attribute")
            if key in {"href", "src"} and value:
                _require(
                    value.startswith(("https://", "http://", PREFIX, "#")),
                    "Unsafe report URL",
                )
                if value.startswith(PREFIX):
                    self.links.append(value)
        if tag == "pre":
            self._pre = []

    def handle_data(self, data):
        if self._pre is not None:
            self._pre.append(data)

    def handle_endtag(self, tag):
        if tag == "pre" and self._pre is not None:
            self.receipts.append("".join(self._pre))
            self._pre = None


def verify_evidence_library(
    public_dir: str | Path, *, local_dir: str | Path | None = None
) -> dict[str, Any]:
    """Verify an already-complete export, without modifying its source bytes.

    Local mode additionally verifies registry lineage, exact local/public input
    bindings, normalization receipts and the complete export hash inventory.
    This is integrity/publication verification, never scientific qualification.
    """
    root = Path(public_dir).resolve()
    schemas = Path(__file__).resolve().parents[2] / "packages/contracts/schemas"
    catalog = _read(root / "catalog.json")
    _schema(catalog, "evidence-library-catalog", schemas)
    assert_public_safe(catalog)
    aois = _unique(catalog["aois"], "id", "AOI")
    events = _unique(catalog["events"], "id", "event")
    policies = _unique(catalog["datasets"], "id", "dataset")
    entries = _unique(catalog["packages"], "id", "package")
    for identifier, dataset in policies.items():
        permitted = dataset["rights"]["public_derivatives"]
        _require(
            not permitted or identifier in PUBLIC_DATASETS,
            "Unknown source cannot self-authorize publication",
        )
        if identifier.startswith("dataset-"):
            number = int(identifier.removeprefix("dataset-"))
            _require(
                number in FAMILIES
                and permitted == use_policy(FAMILIES[number])["public_derivatives"],
                "Acquired-source publication policy changed",
            )
    expected_pairs = {
        (aoi["id"], event) for aoi in aois.values() for event in aoi["event_ids"]
    }
    _require(
        all(event in events for _, event in expected_pairs),
        "AOI references an unknown event",
    )
    _require(
        {(p["aoi_id"], p["event_id"]) for p in entries.values()} == expected_pairs,
        "Catalog package AOI/event coverage is mixed or incomplete",
    )
    files = {"catalog.json"}
    packages = {}
    downloads_seen: dict[str, str] = {}
    reports = set()
    for identifier, entry in entries.items():
        _require(
            identifier == f"{entry['aoi_id']}_{entry['event_id']}",
            "Package ID does not bind AOI/event",
        )
        name, path = _asset(root, entry["url"])
        _require(
            name == f"packages/{identifier}.json",
            "Package path does not bind package ID",
        )
        files.add(name)
        _hash(entry["sha256"], sha256_file(path), identifier)
        package = _read(path)
        _schema(package, "evidence-library-package", schemas)
        _schema(package["assessment"], "evidence-assessment", schemas)
        assert_public_safe(package)
        _assessment(package["assessment"])
        for key in ("id", "aoi_id", "event_id"):
            _require(package[key] == entry[key], f"Mixed package {key}")
        _require(
            package["package_version"] == catalog["package_version"],
            "Mixed package version",
        )
        _require(
            package["generated_at"] == catalog["generated_at"],
            "Mixed package generation",
        )
        aoi = aois[entry["aoi_id"]]
        _hash(
            aoi.get("sha256"),
            package["input_hashes"].get("aoi_sha256"),
            "AOI geometry source",
        )
        if "aoi_geometry" in package["input_hashes"]:
            _hash(
                package["input_hashes"]["aoi_geometry"],
                _geometry_hash(aoi["geometry"]),
                "AOI geometry content",
            )
        selections = _unique(package["datasets"], "dataset_id", "dataset selection")
        for dataset_id in selections:
            _require(dataset_id in policies, "Unknown dataset selection")
            if dataset_id.startswith("dataset-"):
                _require(
                    dataset_applies(int(dataset_id[-2:]), aoi["id"], entry["event_id"]),
                    "Dataset selection belongs to another AOI/event",
                )
        _unique(package["layers"], "id", "layer")
        _unique(package["scenarios"], "id", "scenario")
        _require(not package["gauges"], "Uncleared gauge observations in public export")
        for layer in package["layers"]:
            _require(layer["dataset_id"] in policies, "Unknown layer source")
            validate_layer_export(layer, policies)
            if "image_url" in layer:
                asset, _ = _asset(root, layer["image_url"])
                _require(
                    asset == f"terrain/{aoi['id']}.png",
                    "Terrain asset belongs to another AOI",
                )
                files.add(asset)
        if package["report_url"]:
            reports.add(package["report_url"])
        for download in package.get("downloads", []):
            asset, path = _asset(root, download["url"])
            _require(
                asset == f"databases/{aoi['id']}.json.gz",
                "Database belongs to another AOI",
            )
            files.add(asset)
            _hash(download["sha256"], sha256_file(path), asset)
            _require(
                asset not in downloads_seen
                or downloads_seen[asset] == download["sha256"],
                "Mixed database versions",
            )
            with gzip.open(path, "rb") as stream:
                # Bound decompression before parsing a potentially untrusted archive.
                content = stream.read(512 * 1024 * 1024 + 1)
            _require(
                len(content) <= 512 * 1024 * 1024,
                "Public database exceeds verification size limit",
            )
            _database(_json(content, asset), package, policies)
            downloads_seen[asset] = download["sha256"]
        packages[identifier] = package
    for url in reports:
        name, path = _asset(root, url)
        files.add(name)
        text = path.read_text(encoding="utf-8")
        assert_public_safe(text)
        parser = _ReportParser()
        parser.feed(text)
        for link in parser.links:
            _require(
                _asset(root, link)[0] in files,
                "Report references an unlisted public asset",
            )
        for content in parser.receipts:
            appendix = _json(content, "report appendix")
            assert_public_safe(appendix)
            _require(
                appendix.get("package_version") == catalog["package_version"],
                "Mixed report package version",
            )
            _require(
                appendix.get("downloadable_packages") == catalog["packages"],
                "Mixed report package bindings",
            )
            _require(
                appendix.get("aois") == catalog["aois"]
                and appendix.get("datasets") == catalog["datasets"],
                "Mixed report source/AOI metadata",
            )
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    _require(
        actual == files,
        f"Unlisted or missing public files: {sorted(actual.symmetric_difference(files))}",
    )
    hashes = {name: sha256_file(root / name) for name in sorted(files)}
    local_result = (
        _verify_local(Path(local_dir), catalog, packages, hashes)
        if local_dir is not None
        else None
    )
    return {
        "schema_version": "floodguard.evidence_export_verification.v1",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "package_version": catalog["package_version"],
        "non_operational": True,
        "catalog_sha256": hashes["catalog.json"],
        "packages": len(packages),
        "aois": len(aois),
        "public_files": len(files),
        "gzip_databases": len(downloads_seen),
        "files": hashes,
        "local_verification": local_result,
        "scientific_or_operational_acceptance": False,
    }


def _verify_local(root: Path, catalog: dict, packages: dict, hashes: dict) -> dict:
    registry = _read(root / "evidence_registry.json")
    assets = _unique(registry["assets"], "id", "local asset")
    datasets = _unique(registry["datasets"], "id", "local dataset")
    local_aois = _unique(registry["aois"], "id", "local AOI")
    for aoi in catalog["aois"]:
        _require(aoi["id"] in local_aois, "Missing local AOI")
        for key in ("sha256", "geometry", "event_ids"):
            _require(
                local_aois[aoi["id"]][key] == aoi[key],
                "Mixed local/public AOI geometry or selection",
            )
    for asset in assets.values():
        safe_asset_path(root, asset["relative_path"])
        parents, expected = (
            asset.get("parent_asset_ids", []),
            asset.get("parent_hashes", []),
        )
        _require(len(parents) == len(expected), "Parent IDs/hash lengths differ")
        _require(len(set(parents)) == len(parents), "Duplicate asset parents")
        for parent, digest in zip(parents, expected):
            _require(
                parent in assets and parent != asset["id"],
                "Missing or self-referencing parent asset",
            )
            _hash(digest, assets[parent]["sha256"], "parent asset")
    for dataset in datasets.values():
        for asset_id in dataset["asset_ids"] + dataset.get("lineage_asset_ids", []):
            _require(
                asset_id in assets, "Dataset references missing parent/source asset"
            )
    for identifier, package in packages.items():
        local = _read(root / "packages" / f"{identifier}.json")
        for key in (
            "id",
            "aoi_id",
            "event_id",
            "package_version",
            "input_hashes",
            "datasets",
        ):
            _require(local[key] == package[key], f"Mixed local/public package {key}")
        _hash(
            package["input_hashes"].get("source_inventory_sha256"),
            registry["source_inventory_sha256"],
            "source inventory",
        )
        details = local["local_detail_files"]
        scenario = safe_asset_path(root, details["scenarios"])
        _require(
            details["scenarios"] == f"scenarios/{package['aoi_id']}.json",
            "Mixed local scenario AOI",
        )
        _hash(
            package["input_hashes"].get("scenario_sha256"),
            sha256_file(scenario),
            "local scenario",
        )
    receipt = _read(root / "normalization_receipt.json")
    _require(bool(receipt["outputs"]), "Empty normalization receipt")
    for name, expected in receipt["outputs"].items():
        path = safe_asset_path(root, name)
        _require(path.is_file(), "Missing normalized output")
        _hash(expected, sha256_file(path), "normalized output")
    exported = _read(root / "public_export_report.json")
    _require(
        exported["package_version"] == catalog["package_version"],
        "Mixed local export version",
    )
    _require(
        exported["files"] == hashes, "Local export receipt differs from public bytes"
    )
    return {
        "status": "passed",
        "assets": len(assets),
        "datasets": len(datasets),
        "normalized_outputs": len(receipt["outputs"]),
        "source_bytes_reverified": False,
        "scope": "Registry lineage and derived outputs; immutable source bundle verification belongs to intake.",
    }
