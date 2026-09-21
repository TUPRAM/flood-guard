"""Source lineage and bounded facility identity review for local evidence."""

from __future__ import annotations

import copy
import hashlib
import ntpath
from pathlib import Path

from floodguard.evidence_adapters import _csv, _json, _read_json, _utc
from floodguard.evidence_catalog import safe_asset_path, sha256_file


def enrich_registry(
    registry: dict, bundle_root: str | Path, adapter_summary: dict
) -> dict:
    """Add verified source lineage without changing rights or temporal claims.

    Parent assets are checked against the immutable bundle checksum inventory.
    HTTP headers and absolute source paths are never copied into the registry.
    """
    import csv

    root = Path(bundle_root)
    result = copy.deepcopy(registry)
    with (root / "FILES_SHA256.csv").open(encoding="utf-8-sig", newline="") as stream:
        checked = {r["path"].replace("\\", "/"): r for r in csv.DictReader(stream)}
    metadata, parents = {}, {}

    def relative(value: str, folder: str) -> str:
        text = value.replace("\\", "/")
        # Recorded absolute paths are resolved by known folder and filename,
        # never trusted as an authority to read beyond the supplied bundle.
        if ntpath.isabs(value):
            part = text.split(f"/{folder}/", 1)
            return (
                f"{folder}/{part[1]}"
                if len(part) == 2
                else f"{folder}/{ntpath.basename(value)}"
            )
        return text if text.startswith(folder + "/") else f"{folder}/{text}"

    for folder in ("thaiwater", "dopa"):
        for item in _read_json(root / folder / "manifest.json", []):
            metadata[relative(item["path"], folder)] = item
    for item in _read_json(root / "shelters/provenance.json", []):
        metadata[relative(item["file"], "shelters")] = item
    health = _read_json(root / "healthcare/download.json", {})
    if health:
        metadata["healthcare/thailand_health_facilities_th.geojson"] = health
    flood = _read_json(root / "flood_reference/manifest.json", {})
    archive = "flood_reference/FL20240912THA_GDB.zip"
    if flood:
        metadata[archive] = {
            **flood,
            "sha256": flood.get("source_sha256"),
            "role": "raw_source",
        }
        for entry in flood.get("clips", []):
            rel = relative(entry["path"], "flood_reference")
            metadata[rel] = {
                **entry,
                "source_url": flood.get("source_url"),
                "retrieved_at_utc": flood.get("retrieved_at_utc"),
                "source_period": "2024-10-22"
                if "_20241022_FloodExtent" in entry.get("layer", "")
                else "2024-08-01/2024-10-22",
                "role": "derived_aoi_clip",
                "crs": "EPSG:4326",
            }
            parents[rel] = [archive]
    terrain = _read_json(root / "terrain_drainage/manifest.json", {})
    terrain_files = terrain.get("files", [])
    for entry in terrain_files:
        if entry.get("role") in {"aoi_input", "existing_source_reused_read_only"}:
            continue
        rel = relative(entry["path"], "terrain_drainage")
        if rel not in checked:
            continue
        metadata[rel] = {
            **entry,
            "retrieved_at_utc": entry.get("retrieved_at_utc")
            or terrain.get("created_at_utc"),
        }
        if entry.get("role") == "derived_river_clip":
            parents[rel] = ["terrain_drainage/HydroRIVERS_v10_as_shp.zip"]
        elif entry.get("role") == "derived_dem_aoi":
            parents[rel] = [
                relative(p["path"], "terrain_drainage")
                for p in terrain_files
                if p.get("role") == "derived_source_window"
                and ntpath.basename(p["path"]).startswith(entry["aoi"] + "_")
            ]
    for path in sorted((root / "roads/official_reports").glob("*.source.json")):
        entry = _read_json(path)
        stem = path.name.removesuffix(".source.json")
        extension = ".jpg" if "figure_" in stem else ".html"
        rel = "roads/official_reports/" + stem + extension
        if rel in checked and entry.get("http_status", 200) == 200:
            metadata[rel] = entry
    for asset in result["assets"]:
        rel = asset["relative_path"]
        if rel.startswith("shelters/") and rel != "shelters/dpm-gd002_final2.csv":
            parents[rel] = ["shelters/dpm-gd002_final2.csv"]
        if (
            rel.startswith("healthcare/")
            and rel != "healthcare/thailand_health_facilities_th.geojson"
        ):
            parents[rel] = ["healthcare/thailand_health_facilities_th.geojson"]
        if rel.endswith("road_incidents_transcribed.csv"):
            parents[rel] = [
                p
                for p in metadata
                if p.startswith(
                    "roads/official_reports/doh_prd_chiang_rai_roads_2024-09-11"
                )
            ]
    by_path = {a["relative_path"]: a for a in result["assets"]}

    def add_parent(rel: str, family: str) -> dict:
        if rel in by_path:
            return by_path[rel]
        recorded = checked.get(rel)
        if recorded is None:
            raise ValueError(f"Parent asset absent from checksum inventory: {rel}")
        path = safe_asset_path(root, rel)
        digest = sha256_file(path)
        if digest != recorded["sha256"] or path.stat().st_size != int(
            recorded["bytes"]
        ):
            raise ValueError(f"Parent asset integrity failure: {rel}")
        asset = {
            "id": "asset-"
            + hashlib.sha256((rel + "\0" + digest).encode()).hexdigest()[:24],
            "relative_path": rel,
            "sha256": digest,
            "bytes": int(recorded["bytes"]),
            "family": family,
            "role": "verified_lineage_source",
            "parent_hashes": [],
        }
        by_path[rel] = asset
        return asset

    for rel, asset in list(by_path.items()):
        for parent in parents.get(rel, []):
            add_parent(parent, asset["family"])
    for rel, asset in by_path.items():
        entry = metadata.get(rel, {})
        parent_assets = [by_path[p] for p in parents.get(rel, [])]
        inherited = [metadata.get(p["relative_path"], {}) for p in parent_assets]
        urls = {
            e[k]
            for e in [entry, *inherited]
            for k in ("download_url", "source_url", "original_source")
            if isinstance(e.get(k), str) and e[k].startswith(("https://", "http://"))
        }
        retrieved_raw = entry.get("retrieved_utc") or entry.get("retrieved_at_utc")
        asset.update(
            source_urls=sorted(urls),
            parent_asset_ids=[p["id"] for p in parent_assets],
            parent_hashes=[p["sha256"] for p in parent_assets],
            retrieved_at_original=retrieved_raw,
            retrieved_at_utc=_utc(retrieved_raw),
            source_timestamp=entry.get("source_date")
            or entry.get("source_period")
            or entry.get("source_last_updated"),
            source_timestamp_status="source_recorded"
            if entry
            else "inherited_source_context_only",
            role="derived_aoi_or_review_asset"
            if parent_assets
            else entry.get("role", asset["role"]),
            crs=entry.get("crs")
            or entry.get("source_crs")
            or ("EPSG:4326" if rel.endswith(".geojson") else None),
        )
        if parent_assets and not retrieved_raw:
            times = sorted(
                {
                    time
                    for e in inherited
                    if (
                        time := _utc(
                            e.get("retrieved_utc") or e.get("retrieved_at_utc")
                        )
                    )
                }
            )
            asset["parent_retrieval_times_utc"] = times
        if rel.startswith("thaiwater/") and rel.endswith(".csv"):
            asset["observation_timezone"] = "unconfirmed"
        if rel.startswith("terrain_drainage/"):
            asset["source_epoch"] = (
                "2021_release_historical_DSM"
                if "copdem" in rel or "Copernicus" in rel
                else "HydroRIVERS_v1_historical"
            )
            asset["event_observation_interval"] = None
    by_id = {a["id"]: a for a in by_path.values()}
    levels = {
        1: "AOI_clipped_observed_footprint_and_cumulative_polygons",
        2: "AOI_clipped_single_date_polygons",
        3: "station",
        4: "station",
        5: "station",
        6: "district",
        7: "district",
        8: "district",
        9: "province",
        10: "district",
        11: "village_registration",
        12: "unverified_site_records",
        13: "historical_facility_points",
        14: "one_arc_second_surface_grid",
        15: "generalized_river_reaches",
        16: "unlocated_route_chainage_document",
        17: "city_narrative",
    }
    for dataset in result["datasets"]:
        selected = [by_id[i] for i in dataset["asset_ids"]]
        dataset["source_urls"] = sorted(
            set(dataset.get("source_urls", []))
            | {u for a in selected for u in a["source_urls"]}
        )
        dataset["lineage_asset_ids"] = sorted(
            {p for a in selected for p in a["parent_asset_ids"]}
        )
        dataset["geographic_level"] = levels[dataset["number"]]
        family = (
            "flood_reference" if dataset["family"] == "flood" else dataset["family"]
        )
        dataset["normalization_status"] = (
            adapter_summary.get("datasets", {}).get(family, {}).get("status", "not_run")
        )
    result["assets"] = sorted(by_path.values(), key=lambda a: a["id"])
    result["lineage_summary"] = {
        "physical_assets": len(by_path),
        "assets_with_parents": sum(bool(a["parent_hashes"]) for a in by_path.values()),
        "assets_with_source_urls": sum(
            bool(a["source_urls"]) for a in by_path.values()
        ),
        "rights_unchanged": True,
    }
    return result


def build_facility_crosswalk(
    normalized_dir: str | Path,
    output_dir: str | Path,
    review_records: list[dict] | None = None,
) -> dict:
    """Write a core-AOI identity review with evidence-limited website matches.

    A public name/address match never proves point accuracy, opening during a
    historical flood, service availability, or usable shelter/bed capacity.
    """
    normalized, output = Path(normalized_dir), Path(output_dir)
    reviews = {r["source_record_id"]: r for r in (review_records or [])}
    rows = []
    for filename, kind in (
        ("shelter_candidates.geojson", "shelter"),
        ("healthcare_candidates.geojson", "healthcare"),
    ):
        doc = _read_json(normalized / filename, {"features": []})
        for feature in doc["features"]:
            p = feature["properties"]
            matches = [a for a in p["aoi_matches"] if a.endswith("_core")]
            if not matches:
                continue
            review = reviews.get(p["record_id"], {})
            supported = bool(
                review.get("source_url")
                and review.get("official_facility_id")
                and review.get("name_match")
                and review.get("address_match")
            )
            rows.append(
                {
                    "source_record_id": p["record_id"],
                    "kind": kind,
                    "core_aois": matches,
                    "source_name": p.get("place_name")
                    or p.get("source_properties", {}).get("Agency"),
                    "source_feature_index": p.get("source_feature_index"),
                    "source_csv_record": p.get("source_csv_record"),
                    "coordinate_cluster_id": p.get("coordinate_cluster_id"),
                    "records_sharing_coordinate": p.get("records_sharing_coordinate"),
                    "identity_status": "public_name_address_match_supported"
                    if supported
                    else "unresolved",
                    "official_facility_id": review.get("official_facility_id")
                    if supported
                    else None,
                    "evidence_url": review.get("source_url"),
                    "evidence_retrieved_at_utc": review.get("retrieved_at_utc"),
                    "evidence_sha256": review.get("sha256"),
                    "review_note": review.get("note"),
                    "evidence_basis": review.get(
                        "evidence_basis",
                        "downloaded_official_page"
                        if review.get("sha256")
                        else "review_record",
                    ),
                    "snapshot_status": review.get(
                        "snapshot_status",
                        "downloaded" if review.get("sha256") else "not_recorded",
                    ),
                    "coordinate_verified": False,
                    "event_availability": "unknown",
                    "event_available_capacity": None,
                    "identity_merge_approved": False,
                    "assumptions": "current_public_registry_identity_only;no_historical_operation_or_capacity_inference",
                }
            )
    unknown_reviews = sorted(set(reviews) - {r["source_record_id"] for r in rows})
    if unknown_reviews:
        raise ValueError("Public review refers to absent core source records")
    _csv(output / "facility_identity_crosswalk.csv", rows)
    report = {
        "records": len(rows),
        "supported_identity_matches": sum(
            r["identity_status"] == "public_name_address_match_supported" for r in rows
        ),
        "unresolved_identities": sum(
            r["identity_status"] == "unresolved" for r in rows
        ),
        "event_capacity_or_operation_accepted": False,
        "rows": rows,
        "source_timestamp": "review timestamps recorded per evidence page",
        "confidence": "bounded_public_identity_review",
    }
    _json(output / "facility_identity_review.json", report)
    return report
