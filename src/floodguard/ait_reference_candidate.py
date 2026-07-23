"""Fail-closed inspection for the Sentinel Asia AIT flood-vector candidate.

The source archive remains outside Git.  This module records checksum-backed,
sanitized facts about the package and its relationship to the committed Mae
Sai study-area geometry.  It deliberately cannot qualify the product for
validation, ML labels, model evaluation, or decision use.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import stat
from tempfile import TemporaryDirectory
from typing import Any, Mapping
import zipfile


REFERENCE_CANDIDATE_SCHEMA = "floodguard.reference_candidate_manifest.v1"
AIT_PRODUCT_ID = "AIT-VAP001-TH"
AIT_SOURCE_URL = (
    "https://sentinel-asia.org/EO/2024/article20240910TH/AIT/AIT-VAP001-TH.zip"
)
SENTINEL_ASIA_TERMS_URL = "https://sentinel-asia.org/sitepolicy/SitePolicy.html"
AIT_PROVIDER = "Asian Institute of Technology via Sentinel Asia"
AIT_DATASET_ID = "sentinel-asia-20240910-thailand-flood"
AIT_REFERENCE_ID = "sentinel-asia-ait-vap001-th-2024"
AIT_EVENT_ID = "mae-sai-flood-2024-09"
AIT_STUDY_AREA_ID = "mae_sai_candidate_v1"
AIT_TARGET_DEFINITION_ID = "temporary-flood-extent-multiclass-v1"
AIT_OBSERVATION_START_UTC = "2024-09-14T00:00:00Z"
AIT_OBSERVATION_END_UTC = "2024-09-14T23:59:59Z"
AIT_PROVIDER_SOURCE_TIMESTAMP = "2024-09-15T00:00:00Z"
AIT_EVENT_TARGET_TIMESTAMP = "2024-09-15T23:16:01Z"
AIT_QUALIFICATION_STATUS = "blocked_external_permission_and_scientific_review"
AIT_REVIEWED_REFERENCE_VERSION = "source-archive-1"
AIT_SYNTHETIC_FIXTURE_VERSION = "synthetic-fixture-v1"
AIT_REVIEWED_ARCHIVE_BYTE_SIZE = 7_907_308
AIT_REVIEWED_ARCHIVE_SHA256 = (
    "762153fe3fd22350070bb788c22f2d4e083866b5d20b1294e8ca27b97367d5d5"
)
AIT_REVIEWED_MANIFEST_CANONICAL_SHA256 = (
    "be2ce989e21f4ad3d79fe8f643ab13e7a3fc19eac1a8069bb8e83ede90878079"
)
AIT_REVIEWED_MANIFEST_FILE_SHA256 = (
    "6f1de97bb3bbc1119124d45d5de3e4e6c59fb541a3045ec90f97615fc2172c8c"
)
AIT_REVIEWED_STUDY_AREA_GEOMETRY_SHA256 = (
    "5cd03ca936c188d37704f5249afa87da0c687b967db8a0f9c9ebd72b27204db1"
)
AIT_REVIEWED_CATALOG_EVIDENCE = (
    "sentinel_asia_20240910TH_event.html",
    37_112,
    "a8728834f12b33b5bac163f8a0c46331ab57f15db77873c5cef2946710857372",
)
AIT_REVIEWED_TERMS_EVIDENCE = (
    "sentinel_asia_site_policy_2026-07-23.html",
    20_840,
    "ce1727cb81d8ca9311e6eeccf2981cab1cc3622ef23be4740c60bbd665519f91",
)
AIT_REVIEWED_ARCHIVE_MEMBERS = {
    "AIT-VAP001-TH/AIT-VAP001-TH.cpg": (
        5,
        "3ad3031f5503a4404af825262ee8232cc04d4ea6683d42c5dd0a2f2a27ac9824",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.dbf": (
        2_589_950,
        "97f66bde18dc96a80801955b15f34c56a80383a202651d6fb895bbb46b63c036",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.prj": (
        522,
        "72f2d5e83461bdf4ca967efd056a7b6cce8edac5098b91ffe93034cfe1e9ec5c",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.sbn": (
        345_004,
        "67f183a3ff780ca187a6b52dd29d1cad421ad2630a56a2cb46016ba436b3bef1",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.sbx": (
        14_620,
        "e2899fb5bfd61e1fc5bc31c320755b966015ffd8806482d91bb0b024b03b14aa",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.shp": (
        29_725_536,
        "8af51454716c879ba919952cfdeb6a86e84003f4c7c59f80bcd43fc2362ea6e4",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.shp.xml": (
        11_645,
        "c15961d3c12d88b33006e4b18e12c2c0aea4d48d132e7d896387479a09a85711",
    ),
    "AIT-VAP001-TH/AIT-VAP001-TH.shx": (
        265_716,
        "29b9ed40df096654385c833fda38e7986939753b0910ed8d0bf33292feb55d9e",
    ),
}
AIT_REVIEWED_NATIVE_SPATIAL_SHA256 = (
    "db7ee8857ba552d78bfab4d2a088ec163e84da02a953886bea030a4a0e07c16d"
)
AIT_REVIEWED_STUDY_AREA_RELATIONSHIP_SHA256 = (
    "d4db8713fd6a2a111c4176964d0308c422f941c67494623f2f8907ea16472f54"
)
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBER_COUNT = 64
MAX_MEMBER_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_PRIVATE_PATH_RE = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\|"
    r"/(?:home|users?|mnt|var|tmp|workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)


class AitReferenceCandidateError(ValueError):
    """Raised when the AIT candidate package or receipt is malformed."""


def inspect_ait_reference_candidate(
    archive_path: str | Path,
    study_area_path: str | Path,
    *,
    catalog_evidence_path: str | Path,
    terms_evidence_path: str | Path,
    inspected_at_utc: datetime | None = None,
    reference_version: str = AIT_REVIEWED_REFERENCE_VERSION,
    local_path_hint: str = (
        "<external_data_workspace>/reference_candidates/"
        "sentinel_asia_ait/AIT-VAP001-TH.zip"
    ),
) -> dict[str, Any]:
    """Inspect exact archive bytes and build a non-authoritative candidate receipt.

    GeoPandas, Shapely, and PyProj are imported only while this optional
    geospatial inspection runs.  The normal FloodGuard decision package remains
    free of those optional dependencies.
    """

    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise AitReferenceCandidateError(
            "AIT inspection requires the FloodGuard geo dependencies."
        ) from exc

    archive = Path(archive_path)
    study_area = Path(study_area_path)
    catalog_evidence = Path(catalog_evidence_path)
    terms_evidence = Path(terms_evidence_path)
    if not archive.is_file() or archive.suffix.lower() != ".zip":
        raise AitReferenceCandidateError(
            "AIT reference candidate must be an existing ZIP archive."
        )
    if archive.stat().st_size <= 0 or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise AitReferenceCandidateError(
            "AIT archive byte size is outside the bounded inspection limit."
        )
    if not study_area.is_file():
        raise AitReferenceCandidateError("Study-area geometry file is missing.")
    if not catalog_evidence.is_file() or not terms_evidence.is_file():
        raise AitReferenceCandidateError(
            "Catalog and terms evidence files must both be supplied."
        )
    _validate_redacted_hint(local_path_hint)
    inspected_at = _as_utc(inspected_at_utc or datetime.now(UTC))
    catalog_text = catalog_evidence.read_text(encoding="utf-8", errors="replace")
    terms_text = terms_evidence.read_text(encoding="utf-8", errors="replace")
    if AIT_PRODUCT_ID not in catalog_text or "14 September 2024" not in catalog_text:
        raise AitReferenceCandidateError(
            "Catalog evidence does not bind the exact product and observation date."
        )
    if (
        "scientific/educational" not in terms_text
        or "No modification is allowed" not in terms_text
    ):
        raise AitReferenceCandidateError(
            "Terms evidence does not contain the reviewed scientific-use and "
            "no-modification clauses."
        )

    with zipfile.ZipFile(archive) as package:
        file_infos = _validate_archive_infos(package.infolist())
        file_members = [info.filename for info in file_infos]
        member_hashes = {
            info.filename: _zip_member_sha256(package, info) for info in file_infos
        }
        metadata_private_path_detected = any(
            info.filename.lower().endswith((".xml", ".shp.xml"))
            and _PRIVATE_PATH_RE.search(_read_zip_text(package, info)) is not None
            for info in file_infos
        )
        with TemporaryDirectory(prefix="floodguard-ait-reference-") as temp_dir:
            temp_root = Path(temp_dir)
            _safe_extract(package, temp_root)
            shape_path = next(temp_root.rglob("*.shp"))
            candidate = gpd.read_file(shape_path)

    area = gpd.read_file(study_area)
    if candidate.empty:
        raise AitReferenceCandidateError("AIT candidate contains no features.")
    if area.empty:
        raise AitReferenceCandidateError("Study-area geometry contains no features.")
    if candidate.crs is None or not candidate.crs.is_projected:
        raise AitReferenceCandidateError(
            "AIT candidate must declare a projected native CRS."
        )
    if area.crs is None:
        raise AitReferenceCandidateError("Study-area geometry must declare a CRS.")
    if candidate.geometry.is_empty.any() or candidate.geometry.isna().any():
        raise AitReferenceCandidateError(
            "AIT candidate contains empty or missing geometries."
        )

    study_projected = area.to_crs(candidate.crs)
    study_union = study_projected.geometry.union_all()
    if study_union.is_empty or not study_union.is_valid:
        raise AitReferenceCandidateError(
            "Authoritative study-area union is empty or invalid."
        )

    raw_valid = candidate.geometry.is_valid
    diagnostic_geometry = candidate.geometry.make_valid()
    intersects = diagnostic_geometry.intersects(study_union)
    intersecting = diagnostic_geometry.loc[intersects]
    if intersecting.empty:
        raise AitReferenceCandidateError(
            "AIT candidate has no geometry intersecting the study area."
        )
    clipped = intersecting.intersection(study_union)
    clipped_union = clipped.union_all()
    candidate_wgs84 = candidate.to_crs(4326)
    bounds = [round(float(value), 8) for value in candidate_wgs84.total_bounds]
    study_area_m2 = float(study_union.area)
    intersection_m2 = float(clipped_union.area)
    archive_sha256 = _file_sha256(archive)
    study_area_sha256 = _file_sha256(study_area)
    gridcodes = _sorted_values(candidate, "gridcode")
    id_unique = _column_unique(candidate, "Id")

    payload: dict[str, Any] = {
        "schema_version": REFERENCE_CANDIDATE_SCHEMA,
        "reference_id": AIT_REFERENCE_ID,
        "reference_version": reference_version,
        "event_id": AIT_EVENT_ID,
        "study_area_id": AIT_STUDY_AREA_ID,
        "study_area_geometry_sha256": study_area_sha256,
        "target_definition_id": AIT_TARGET_DEFINITION_ID,
        "reference_evidence_class": "expert_interpretation",
        "authority_basis": "provider_product_without_project_acceptance",
        "production_method": "agency_algorithmic_product",
        "provider": {
            "organization": AIT_PROVIDER,
            "dataset_id": AIT_DATASET_ID,
            "product_id": AIT_PRODUCT_ID,
            "source_url": AIT_SOURCE_URL,
            "terms_url": SENTINEL_ASIA_TERMS_URL,
            "catalog_evidence": {
                "file_name": catalog_evidence.name,
                "byte_size": catalog_evidence.stat().st_size,
                "sha256": _file_sha256(catalog_evidence),
                "exact_product_and_observation_date_present": True,
            },
            "terms_evidence": {
                "file_name": terms_evidence.name,
                "byte_size": terms_evidence.stat().st_size,
                "sha256": _file_sha256(terms_evidence),
                "scientific_use_clause_present": True,
                "no_modification_clause_present": True,
                "accessed_at_utc": _format_utc(inspected_at),
            },
        },
        "temporal_identity": {
            "observation_start_utc": AIT_OBSERVATION_START_UTC,
            "observation_end_utc": AIT_OBSERVATION_END_UTC,
            "provider_source_timestamp": AIT_PROVIDER_SOURCE_TIMESTAMP,
            "accessed_at_utc": _format_utc(inspected_at),
            "event_target_timestamp": AIT_EVENT_TARGET_TIMESTAMP,
            "allowable_temporal_delta_hours": None,
            "temporal_qualification_status": "blocked_tolerance_not_approved",
        },
        "asset_inventory": {
            "archive": {
                "file_name": archive.name,
                "byte_size": archive.stat().st_size,
                "sha256": archive_sha256,
                "local_path_hint": local_path_hint,
            },
            "members": [
                {
                    "relative_path": PurePosixPath(member).as_posix(),
                    "byte_size": _member_size(archive, member),
                    "sha256": member_hashes[member],
                }
                for member in file_members
            ],
            "complete_shapefile_component_set": True,
        },
        "native_spatial_contract": {
            "crs": candidate.crs.to_string(),
            "bounds_wgs84": bounds,
            "geometry_types": sorted(set(candidate.geom_type.astype(str))),
            "feature_count": int(len(candidate)),
            "valid_feature_count": int(raw_valid.sum()),
            "invalid_feature_count": int((~raw_valid).sum()),
            "gridcode_values": gridcodes,
            "feature_id_unique": id_unique,
            "class_mapping": {
                "1": "detected_flood_water",
                "dry": "not_provided",
                "permanent_water": "removed_during_provider_processing",
                "unknown": "not_encoded",
                "nodata": "not_encoded",
            },
        },
        "study_area_relationship": {
            "study_area_feature_count": int(len(area)),
            "study_area_area_km2": round(study_area_m2 / 1_000_000, 3),
            "intersecting_feature_count": int(intersects.sum()),
            "invalid_intersecting_feature_count": int(
                ((~raw_valid) & intersects).sum()
            ),
            "diagnostic_repair_applied": True,
            "diagnostic_intersection_area_km2": round(intersection_m2 / 1_000_000, 3),
            "diagnostic_intersection_fraction": round(
                intersection_m2 / study_area_m2, 6
            ),
            "complete_study_area_coverage_claimed": False,
        },
        "provenance": {
            "provider_lineage_present": True,
            "metadata_contains_private_provider_paths": metadata_private_path_detected,
            "private_provider_paths_published": False,
            "known_uncertainty": [
                "The package provides detected-flood polygons but no explicit dry, unknown, or nodata class.",
                "Invalid source geometries require a separately checksummed repair receipt before any derived raster.",
                "No second independently qualified corroborating reference is bound to this manifest.",
            ],
            "assumptions": [
                "Observation time is derived from the Sentinel Asia event listing.",
                "Diagnostic make-valid geometry is used only to measure intersection and confers no qualification.",
            ],
        },
        "permission_status": {
            "general_scientific_use_described": True,
            "general_terms_prohibit_modification": True,
            "product_specific_rasterization_permission_confirmed": False,
            "ml_label_use_allowed": False,
            "model_evaluation_use_allowed": False,
            "redistribution_status": "unresolved_product_specific",
            "reference_authority_accepted": False,
        },
        "qualification_status": AIT_QUALIFICATION_STATUS,
        "processing_allowed": False,
        "blockers": [
            "Product-specific permission for rasterization, derived metrics, ML-label use, and model evaluation is unresolved.",
            "A Reference Authority has not accepted the product for any FloodGuard scientific purpose.",
            "The source contains invalid geometries and has no immutable repair receipt.",
            "Dry, permanent-water, unknown, nodata, and validity-mask semantics are incomplete.",
            "The allowable event-time tolerance has not been predeclared and approved.",
        ],
        "safety": {
            "eligible_for_decision_layer": False,
            "eligible_for_access_analysis": False,
            "eligible_for_equity_analysis": False,
            "eligible_for_fpps": False,
            "eligible_for_action_class": False,
            "official_warning": False,
        },
        "inspected_at_utc": _format_utc(inspected_at),
        "canonical_sha256": "",
    }
    payload["canonical_sha256"] = _canonical_sha256(
        {key: value for key, value in payload.items() if key != "canonical_sha256"}
    )
    validate_ait_reference_candidate(payload)
    return payload


def validate_ait_reference_candidate(payload: Mapping[str, Any]) -> None:
    """Validate a sanitized AIT candidate receipt and its fail-closed claims."""

    if not isinstance(payload, Mapping):
        raise AitReferenceCandidateError("AIT candidate receipt must be an object.")
    required = {
        "schema_version",
        "reference_id",
        "reference_version",
        "event_id",
        "study_area_id",
        "study_area_geometry_sha256",
        "target_definition_id",
        "reference_evidence_class",
        "authority_basis",
        "production_method",
        "provider",
        "temporal_identity",
        "asset_inventory",
        "native_spatial_contract",
        "study_area_relationship",
        "provenance",
        "permission_status",
        "qualification_status",
        "processing_allowed",
        "blockers",
        "safety",
        "inspected_at_utc",
        "canonical_sha256",
    }
    if set(payload) != required:
        raise AitReferenceCandidateError(
            "AIT candidate receipt has unexpected or missing fields."
        )
    if payload["schema_version"] != REFERENCE_CANDIDATE_SCHEMA:
        raise AitReferenceCandidateError("Unsupported AIT candidate schema.")
    identity = {
        "reference_id": AIT_REFERENCE_ID,
        "event_id": AIT_EVENT_ID,
        "study_area_id": AIT_STUDY_AREA_ID,
        "target_definition_id": AIT_TARGET_DEFINITION_ID,
        "authority_basis": "provider_product_without_project_acceptance",
        "production_method": "agency_algorithmic_product",
    }
    for field, expected in identity.items():
        if payload[field] != expected:
            raise AitReferenceCandidateError(
                f"AIT candidate {field} is not the reviewed source identity."
            )
        if field not in {"authority_basis", "production_method"} and not _is_id(
            payload[field]
        ):
            raise AitReferenceCandidateError(
                f"AIT candidate {field} is not a valid identifier."
            )
    if payload["reference_version"] not in {
        AIT_REVIEWED_REFERENCE_VERSION,
        AIT_SYNTHETIC_FIXTURE_VERSION,
    }:
        raise AitReferenceCandidateError(
            "AIT candidate reference_version is not a supported reviewed or "
            "synthetic-fixture identity."
        )
    if payload["reference_evidence_class"] != "expert_interpretation":
        raise AitReferenceCandidateError(
            "AIT product may only be recorded as an expert-interpretation candidate."
        )
    if payload["processing_allowed"] is not False:
        raise AitReferenceCandidateError(
            "AIT candidate cannot be marked processing_allowed."
        )
    if payload["qualification_status"] != AIT_QUALIFICATION_STATUS:
        raise AitReferenceCandidateError(
            "AIT candidate qualification must remain explicitly blocked."
        )
    if not _is_sha256(payload["study_area_geometry_sha256"]):
        raise AitReferenceCandidateError(
            "Study-area geometry checksum must be SHA-256."
        )
    provider = _require_mapping(payload["provider"], "provider")
    _require_exact_keys(
        provider,
        {
            "organization",
            "dataset_id",
            "product_id",
            "source_url",
            "terms_url",
            "catalog_evidence",
            "terms_evidence",
        },
        "provider",
    )
    provider_identity = {
        "organization": AIT_PROVIDER,
        "dataset_id": AIT_DATASET_ID,
        "product_id": AIT_PRODUCT_ID,
        "source_url": AIT_SOURCE_URL,
        "terms_url": SENTINEL_ASIA_TERMS_URL,
    }
    for field, expected in provider_identity.items():
        if provider[field] != expected:
            raise AitReferenceCandidateError(
                f"AIT provider {field} is not the reviewed source identity."
            )

    catalog = _require_mapping(
        provider["catalog_evidence"], "provider.catalog_evidence"
    )
    _require_exact_keys(
        catalog,
        {
            "file_name",
            "byte_size",
            "sha256",
            "exact_product_and_observation_date_present",
        },
        "provider.catalog_evidence",
    )
    _validate_evidence_file(catalog, "provider.catalog_evidence")
    if catalog["exact_product_and_observation_date_present"] is not True:
        raise AitReferenceCandidateError(
            "AIT catalog evidence must bind the exact product and observation date."
        )

    terms = _require_mapping(provider["terms_evidence"], "provider.terms_evidence")
    _require_exact_keys(
        terms,
        {
            "file_name",
            "byte_size",
            "sha256",
            "scientific_use_clause_present",
            "no_modification_clause_present",
            "accessed_at_utc",
        },
        "provider.terms_evidence",
    )
    _validate_evidence_file(terms, "provider.terms_evidence")
    if (
        terms["scientific_use_clause_present"] is not True
        or terms["no_modification_clause_present"] is not True
    ):
        raise AitReferenceCandidateError(
            "AIT terms evidence must preserve the reviewed scientific-use and "
            "no-modification clauses."
        )
    terms_accessed = _parse_timestamp(
        terms["accessed_at_utc"], "provider.terms_evidence.accessed_at_utc"
    )

    temporal = _require_mapping(payload["temporal_identity"], "temporal_identity")
    _require_exact_keys(
        temporal,
        {
            "observation_start_utc",
            "observation_end_utc",
            "provider_source_timestamp",
            "accessed_at_utc",
            "event_target_timestamp",
            "allowable_temporal_delta_hours",
            "temporal_qualification_status",
        },
        "temporal_identity",
    )
    expected_temporal = {
        "observation_start_utc": AIT_OBSERVATION_START_UTC,
        "observation_end_utc": AIT_OBSERVATION_END_UTC,
        "provider_source_timestamp": AIT_PROVIDER_SOURCE_TIMESTAMP,
        "event_target_timestamp": AIT_EVENT_TARGET_TIMESTAMP,
        "allowable_temporal_delta_hours": None,
        "temporal_qualification_status": "blocked_tolerance_not_approved",
    }
    for field, expected in expected_temporal.items():
        if temporal[field] != expected:
            raise AitReferenceCandidateError(
                f"AIT temporal {field} is not the reviewed blocked identity."
            )
    observation_start = _parse_timestamp(
        temporal["observation_start_utc"],
        "temporal_identity.observation_start_utc",
    )
    observation_end = _parse_timestamp(
        temporal["observation_end_utc"],
        "temporal_identity.observation_end_utc",
    )
    provider_source = _parse_timestamp(
        temporal["provider_source_timestamp"],
        "temporal_identity.provider_source_timestamp",
    )
    event_target = _parse_timestamp(
        temporal["event_target_timestamp"],
        "temporal_identity.event_target_timestamp",
    )
    temporal_accessed = _parse_timestamp(
        temporal["accessed_at_utc"], "temporal_identity.accessed_at_utc"
    )
    inspected_at = _parse_timestamp(payload["inspected_at_utc"], "inspected_at_utc")
    if not (observation_start <= observation_end < provider_source <= event_target):
        raise AitReferenceCandidateError("AIT temporal chronology is inconsistent.")
    if not (terms_accessed == temporal_accessed == inspected_at):
        raise AitReferenceCandidateError(
            "AIT access and inspection timestamps must identify one evidence capture."
        )

    permissions = _require_mapping(payload["permission_status"], "permission_status")
    _require_exact_keys(
        permissions,
        {
            "general_scientific_use_described",
            "general_terms_prohibit_modification",
            "product_specific_rasterization_permission_confirmed",
            "ml_label_use_allowed",
            "model_evaluation_use_allowed",
            "redistribution_status",
            "reference_authority_accepted",
        },
        "permission_status",
    )
    if (
        permissions["general_scientific_use_described"] is not True
        or permissions["general_terms_prohibit_modification"] is not True
        or permissions["redistribution_status"] != "unresolved_product_specific"
        or any(
            permissions[field] is not False
            for field in (
                "product_specific_rasterization_permission_confirmed",
                "ml_label_use_allowed",
                "model_evaluation_use_allowed",
                "reference_authority_accepted",
            )
        )
    ):
        raise AitReferenceCandidateError(
            "AIT legal and permission semantics must remain explicitly unresolved "
            "and fail closed."
        )

    inventory = _require_mapping(payload["asset_inventory"], "asset_inventory")
    _require_exact_keys(
        inventory,
        {"archive", "members", "complete_shapefile_component_set"},
        "asset_inventory",
    )
    if inventory["complete_shapefile_component_set"] is not True:
        raise AitReferenceCandidateError(
            "AIT archive must retain a complete shapefile component set."
        )
    archive = _require_mapping(inventory["archive"], "asset_inventory.archive")
    _require_exact_keys(
        archive,
        {"file_name", "byte_size", "sha256", "local_path_hint"},
        "asset_inventory.archive",
    )
    if archive["file_name"] != f"{AIT_PRODUCT_ID}.zip":
        raise AitReferenceCandidateError(
            "AIT archive file name does not match the reviewed product."
        )
    archive_size = _require_positive_int(
        archive["byte_size"], "asset_inventory.archive.byte_size"
    )
    if archive_size > MAX_ARCHIVE_BYTES:
        raise AitReferenceCandidateError(
            "AIT archive byte size exceeds the bounded inspection limit."
        )
    if not _is_sha256(archive["sha256"]):
        raise AitReferenceCandidateError("AIT archive checksum must be SHA-256.")
    _validate_redacted_hint(str(archive["local_path_hint"]))

    members = inventory["members"]
    if not isinstance(members, list):
        raise AitReferenceCandidateError(
            "AIT asset_inventory.members must be an array."
        )
    if not 4 <= len(members) <= MAX_ARCHIVE_MEMBER_COUNT:
        raise AitReferenceCandidateError(
            "AIT archive member count is outside the bounded inspection limit."
        )
    member_paths: list[str] = []
    total_member_bytes = 0
    for index, member_value in enumerate(members):
        member = _require_mapping(member_value, f"asset_inventory.members[{index}]")
        _require_exact_keys(
            member,
            {"relative_path", "byte_size", "sha256"},
            f"asset_inventory.members[{index}]",
        )
        relative_path = member["relative_path"]
        if not isinstance(relative_path, str) or not relative_path:
            raise AitReferenceCandidateError(
                f"AIT member {index} has an invalid relative path."
            )
        member_bytes = _require_nonnegative_int(
            member["byte_size"], f"asset_inventory.members[{index}].byte_size"
        )
        if member_bytes > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise AitReferenceCandidateError(
                "AIT archive member exceeds the bounded uncompressed-size limit."
            )
        if not _is_sha256(member["sha256"]):
            raise AitReferenceCandidateError(
                f"AIT member {index} checksum must be SHA-256."
            )
        member_paths.append(relative_path)
        total_member_bytes += member_bytes
    if total_member_bytes > MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise AitReferenceCandidateError(
            "AIT archive total uncompressed size exceeds the bounded limit."
        )
    _validate_archive_members(member_paths)

    spatial = _require_mapping(
        payload["native_spatial_contract"], "native_spatial_contract"
    )
    _require_exact_keys(
        spatial,
        {
            "crs",
            "bounds_wgs84",
            "geometry_types",
            "feature_count",
            "valid_feature_count",
            "invalid_feature_count",
            "gridcode_values",
            "feature_id_unique",
            "class_mapping",
        },
        "native_spatial_contract",
    )
    _require_nonempty_text(spatial["crs"], "native_spatial_contract.crs")
    bounds = spatial["bounds_wgs84"]
    if (
        not isinstance(bounds, list)
        or len(bounds) != 4
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in bounds
        )
        or not (-180 <= bounds[0] < bounds[2] <= 180)
        or not (-90 <= bounds[1] < bounds[3] <= 90)
    ):
        raise AitReferenceCandidateError(
            "AIT WGS84 bounds must be a finite ordered bounding box."
        )
    geometry_types = _require_nonempty_unique_text_list(
        spatial["geometry_types"], "native_spatial_contract.geometry_types"
    )
    if any(item not in {"Polygon", "MultiPolygon"} for item in geometry_types):
        raise AitReferenceCandidateError(
            "AIT candidate geometry types must remain polygonal."
        )
    feature_count = _require_positive_int(
        spatial["feature_count"], "native_spatial_contract.feature_count"
    )
    valid_count = _require_nonnegative_int(
        spatial["valid_feature_count"],
        "native_spatial_contract.valid_feature_count",
    )
    invalid_count = _require_nonnegative_int(
        spatial["invalid_feature_count"],
        "native_spatial_contract.invalid_feature_count",
    )
    if valid_count + invalid_count != feature_count:
        raise AitReferenceCandidateError(
            "AIT valid and invalid feature counts must sum to feature_count."
        )
    gridcodes = _require_unique_text_list(
        spatial["gridcode_values"], "native_spatial_contract.gridcode_values"
    )
    if gridcodes != ["1"]:
        raise AitReferenceCandidateError(
            "AIT source class identity must remain the single reviewed gridcode 1."
        )
    if spatial["feature_id_unique"] is not None and not isinstance(
        spatial["feature_id_unique"], bool
    ):
        raise AitReferenceCandidateError(
            "AIT feature_id_unique must be boolean or null."
        )
    class_mapping = _require_mapping(
        spatial["class_mapping"], "native_spatial_contract.class_mapping"
    )
    expected_class_mapping = {
        "1": "detected_flood_water",
        "dry": "not_provided",
        "permanent_water": "removed_during_provider_processing",
        "unknown": "not_encoded",
        "nodata": "not_encoded",
    }
    if dict(class_mapping) != expected_class_mapping:
        raise AitReferenceCandidateError(
            "AIT class mapping must preserve missing dry, unknown, and nodata semantics."
        )

    relationship = _require_mapping(
        payload["study_area_relationship"], "study_area_relationship"
    )
    _require_exact_keys(
        relationship,
        {
            "study_area_feature_count",
            "study_area_area_km2",
            "intersecting_feature_count",
            "invalid_intersecting_feature_count",
            "diagnostic_repair_applied",
            "diagnostic_intersection_area_km2",
            "diagnostic_intersection_fraction",
            "complete_study_area_coverage_claimed",
        },
        "study_area_relationship",
    )
    _require_positive_int(
        relationship["study_area_feature_count"],
        "study_area_relationship.study_area_feature_count",
    )
    study_area_km2 = _require_positive_number(
        relationship["study_area_area_km2"],
        "study_area_relationship.study_area_area_km2",
    )
    intersecting_count = _require_positive_int(
        relationship["intersecting_feature_count"],
        "study_area_relationship.intersecting_feature_count",
    )
    invalid_intersecting = _require_nonnegative_int(
        relationship["invalid_intersecting_feature_count"],
        "study_area_relationship.invalid_intersecting_feature_count",
    )
    intersection_km2 = _require_positive_number(
        relationship["diagnostic_intersection_area_km2"],
        "study_area_relationship.diagnostic_intersection_area_km2",
    )
    intersection_fraction = _require_positive_number(
        relationship["diagnostic_intersection_fraction"],
        "study_area_relationship.diagnostic_intersection_fraction",
    )
    if (
        relationship["diagnostic_repair_applied"] is not True
        or relationship["complete_study_area_coverage_claimed"] is not False
        or intersecting_count > feature_count
        or invalid_intersecting > min(intersecting_count, invalid_count)
        or intersection_km2 > study_area_km2
        or not 0 < intersection_fraction <= 1
        or not math.isclose(
            intersection_fraction,
            intersection_km2 / study_area_km2,
            rel_tol=0.0,
            abs_tol=0.002,
        )
    ):
        raise AitReferenceCandidateError(
            "AIT study-area relationship is internally inconsistent."
        )

    if payload["reference_version"] == AIT_REVIEWED_REFERENCE_VERSION:
        reviewed_catalog = (
            catalog["file_name"],
            catalog["byte_size"],
            catalog["sha256"],
        )
        reviewed_terms = (
            terms["file_name"],
            terms["byte_size"],
            terms["sha256"],
        )
        reviewed_members = {
            str(member["relative_path"]): (
                int(member["byte_size"]),
                str(member["sha256"]),
            )
            for member in members
        }
        if payload["study_area_geometry_sha256"] != (
            AIT_REVIEWED_STUDY_AREA_GEOMETRY_SHA256
        ):
            raise AitReferenceCandidateError(
                "AIT reviewed study-area geometry checksum changed."
            )
        if reviewed_catalog != AIT_REVIEWED_CATALOG_EVIDENCE:
            raise AitReferenceCandidateError(
                "AIT reviewed catalog-evidence identity changed."
            )
        if reviewed_terms != AIT_REVIEWED_TERMS_EVIDENCE:
            raise AitReferenceCandidateError(
                "AIT reviewed terms-evidence identity changed."
            )
        if (
            archive_size != AIT_REVIEWED_ARCHIVE_BYTE_SIZE
            or archive["sha256"] != AIT_REVIEWED_ARCHIVE_SHA256
        ):
            raise AitReferenceCandidateError(
                "AIT reviewed source-archive identity changed."
            )
        if reviewed_members != AIT_REVIEWED_ARCHIVE_MEMBERS:
            raise AitReferenceCandidateError(
                "AIT reviewed archive-member identity changed."
            )
        if _canonical_sha256(spatial) != AIT_REVIEWED_NATIVE_SPATIAL_SHA256:
            raise AitReferenceCandidateError(
                "AIT reviewed native spatial facts changed."
            )
        if _canonical_sha256(relationship) != (
            AIT_REVIEWED_STUDY_AREA_RELATIONSHIP_SHA256
        ):
            raise AitReferenceCandidateError(
                "AIT reviewed study-area relationship facts changed."
            )

    provenance = _require_mapping(payload["provenance"], "provenance")
    _require_exact_keys(
        provenance,
        {
            "provider_lineage_present",
            "metadata_contains_private_provider_paths",
            "private_provider_paths_published",
            "known_uncertainty",
            "assumptions",
        },
        "provenance",
    )
    if (
        provenance["provider_lineage_present"] is not True
        or not isinstance(provenance["metadata_contains_private_provider_paths"], bool)
        or provenance["private_provider_paths_published"] is not False
    ):
        raise AitReferenceCandidateError(
            "AIT provenance must preserve lineage and redact private provider paths."
        )
    _require_nonempty_unique_text_list(
        provenance["known_uncertainty"], "provenance.known_uncertainty"
    )
    _require_nonempty_unique_text_list(
        provenance["assumptions"], "provenance.assumptions"
    )
    _require_nonempty_unique_text_list(payload["blockers"], "blockers")

    safety = _require_mapping(payload["safety"], "safety")
    _require_exact_keys(
        safety,
        {
            "eligible_for_decision_layer",
            "eligible_for_access_analysis",
            "eligible_for_equity_analysis",
            "eligible_for_fpps",
            "eligible_for_action_class",
            "official_warning",
        },
        "safety",
    )
    if any(value is not False for value in safety.values()):
        raise AitReferenceCandidateError(
            "AIT candidate cannot carry downstream or warning authority."
        )
    if _PRIVATE_PATH_RE.search(json.dumps(payload, ensure_ascii=True)):
        raise AitReferenceCandidateError(
            "AIT candidate receipt contains a private absolute path."
        )
    unsigned = {
        key: value for key, value in payload.items() if key != "canonical_sha256"
    }
    if payload["canonical_sha256"] != _canonical_sha256(unsigned):
        raise AitReferenceCandidateError("AIT candidate self-hash mismatch.")


def write_ait_reference_candidate(
    payload: Mapping[str, Any],
    output_path: str | Path,
) -> Path:
    """Validate and write one deterministic sanitized JSON receipt."""

    validate_ait_reference_candidate(payload)
    target = Path(output_path)
    if target.suffix.lower() != ".json":
        raise AitReferenceCandidateError("AIT candidate output must be JSON.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return target


def _validate_archive_members(members: list[str]) -> None:
    if (
        not members
        or len(members) > MAX_ARCHIVE_MEMBER_COUNT
        or len(members) != len(set(members))
    ):
        raise AitReferenceCandidateError(
            "AIT archive members must be non-empty, unique, and bounded."
        )
    shape_members = [item for item in members if item.lower().endswith(".shp")]
    if len(shape_members) != 1:
        raise AitReferenceCandidateError(
            "AIT archive must contain exactly one shapefile."
        )
    base = str(PurePosixPath(shape_members[0]).with_suffix(""))
    lowered = {item.lower() for item in members}
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        if (base + suffix).lower() not in lowered:
            raise AitReferenceCandidateError(
                f"AIT shapefile component is missing: {suffix}"
            )
    for member in members:
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts or "\\" in member:
            raise AitReferenceCandidateError(
                "AIT archive contains an unsafe member path."
            )


def _validate_archive_infos(
    infos: list[zipfile.ZipInfo],
) -> list[zipfile.ZipInfo]:
    files = sorted(
        (info for info in infos if not info.is_dir()),
        key=lambda info: info.filename,
    )
    _validate_archive_members([info.filename for info in files])
    total_uncompressed = 0
    for info in files:
        if info.flag_bits & 0x1:
            raise AitReferenceCandidateError(
                "AIT archive must not contain encrypted members."
            )
        file_mode = (info.external_attr >> 16) & 0o170000
        if file_mode == stat.S_IFLNK:
            raise AitReferenceCandidateError(
                "AIT archive must not contain symbolic links."
            )
        if info.file_size < 0 or info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise AitReferenceCandidateError(
                "AIT archive member exceeds the bounded uncompressed-size limit."
            )
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise AitReferenceCandidateError(
                "AIT archive total uncompressed size exceeds the bounded limit."
            )
        if (
            info.file_size > 0
            and info.compress_size == 0
            or (
                info.compress_size > 0
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            )
        ):
            raise AitReferenceCandidateError(
                "AIT archive member exceeds the bounded compression ratio."
            )
    return files


def _safe_extract(package: zipfile.ZipFile, target: Path) -> None:
    for info in package.infolist():
        if info.is_dir():
            continue
        relative = PurePosixPath(info.filename)
        destination = target.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with package.open(info, "r") as source, destination.open("wb") as sink:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > min(info.file_size, MAX_MEMBER_UNCOMPRESSED_BYTES):
                    raise AitReferenceCandidateError(
                        "AIT archive member expanded beyond its declared bound."
                    )
                sink.write(chunk)
        if written != info.file_size:
            raise AitReferenceCandidateError(
                "AIT archive member size does not match its ZIP declaration."
            )


def _member_size(archive: Path, member: str) -> int:
    with zipfile.ZipFile(archive) as package:
        return package.getinfo(member).file_size


def _zip_member_sha256(package: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    digest = hashlib.sha256()
    read = 0
    with package.open(info, "r") as stream:
        while chunk := stream.read(1024 * 1024):
            read += len(chunk)
            if read > min(info.file_size, MAX_MEMBER_UNCOMPRESSED_BYTES):
                raise AitReferenceCandidateError(
                    "AIT archive member expanded beyond its declared bound."
                )
            digest.update(chunk)
    if read != info.file_size:
        raise AitReferenceCandidateError(
            "AIT archive member size does not match its ZIP declaration."
        )
    return digest.hexdigest()


def _read_zip_text(package: zipfile.ZipFile, info: zipfile.ZipInfo) -> str:
    if info.file_size > 2 * 1024 * 1024:
        raise AitReferenceCandidateError(
            "AIT metadata member exceeds the bounded text-inspection limit."
        )
    with package.open(info, "r") as stream:
        return stream.read(2 * 1024 * 1024 + 1).decode("utf-8", errors="replace")


def _sorted_values(frame: Any, column: str) -> list[str]:
    if column not in frame.columns:
        return []
    return sorted({str(value) for value in frame[column].dropna().tolist()})


def _column_unique(frame: Any, column: str) -> bool | None:
    if column not in frame.columns:
        return None
    return bool(frame[column].is_unique)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _is_id(value: object) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AitReferenceCandidateError(f"AIT {label} must be an object.")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise AitReferenceCandidateError(
            f"AIT {label} has unexpected or missing fields."
        )


def _require_nonempty_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AitReferenceCandidateError(f"AIT {label} must be non-empty text.")
    return value


def _require_unique_text_list(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise AitReferenceCandidateError(
            f"AIT {label} must contain unique non-empty text."
        )
    return value


def _require_nonempty_unique_text_list(value: object, label: str) -> list[str]:
    result = _require_unique_text_list(value, label)
    if not result:
        raise AitReferenceCandidateError(f"AIT {label} must not be empty.")
    return result


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AitReferenceCandidateError(f"AIT {label} must be a positive integer.")
    return value


def _require_nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AitReferenceCandidateError(f"AIT {label} must be a nonnegative integer.")
    return value


def _require_positive_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise AitReferenceCandidateError(
            f"AIT {label} must be a positive finite number."
        )
    return float(value)


def _validate_evidence_file(evidence: Mapping[str, Any], label: str) -> None:
    file_name = _require_nonempty_text(evidence["file_name"], f"{label}.file_name")
    if (
        PurePosixPath(file_name).name != file_name
        or "\\" in file_name
        or ".." in file_name
        or ":" in file_name
    ):
        raise AitReferenceCandidateError(
            f"AIT {label}.file_name must be a safe file name."
        )
    _require_positive_int(evidence["byte_size"], f"{label}.byte_size")
    if not _is_sha256(evidence["sha256"]):
        raise AitReferenceCandidateError(
            f"AIT {label} must bind an exact evidence-file SHA-256."
        )


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise AitReferenceCandidateError(
            f"AIT {label} must be a timezone-aware timestamp."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AitReferenceCandidateError(
            f"AIT {label} must be a timezone-aware timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise AitReferenceCandidateError(
            f"AIT {label} must be a timezone-aware timestamp."
        )
    return parsed.astimezone(UTC)


def _validate_redacted_hint(value: str) -> None:
    if (
        not value.startswith("<external_data_workspace>/")
        or _PRIVATE_PATH_RE.search(value)
        or "\\" in value
    ):
        raise AitReferenceCandidateError(
            "Local path hint must use the redacted external-workspace form."
        )


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AitReferenceCandidateError("Inspection timestamp must be timezone-aware.")
    return value.astimezone(UTC).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
