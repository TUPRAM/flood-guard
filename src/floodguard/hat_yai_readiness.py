"""Fail-closed readiness evidence for the Hat Yai / Songkhla story tile.

The first Hat Yai milestone is deliberately metadata-only.  This module binds
the committed CDSE candidate snapshot and ingestion/reference rows to a small,
self-hashed receipt.  It does not download data, infer a pre/post pair, create a
reference mask, calculate flood metrics, or promote decision outputs.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import urlparse


SCHEMA_VERSION = "floodguard.hat-yai-readiness.v1"
STUDY_AREA_ID = "hat_yai_2025"
STUDY_AREA_NAME = "Hat Yai / Songkhla 2025"

PINNED_INPUT_SHA256: Mapping[str, str] = {
    "outputs/cdse_hat_yai_2025_metadata.csv": (
        "099cb6fa3f38261e546c09e3fc5c97dbca93055f820844e2ac9f3d5a0c22720b"
    ),
    "outputs/real_data_ingestion_manifest.csv": (
        "c23103f626ed14fe740a66fffa52cfcf0fcd06c9971254293f49b9e7bb941871"
    ),
}
PINNED_PUBLIC_CANDIDATE_SET_SHA256 = (
    "921029aa238fe2e1e7869f80140bc1c5516c385c2d0998d686e204ec23cd3ccb"
)
PINNED_REFERENCE_CANDIDATE_SET_SHA256 = (
    "cf03f010ea1ad8b3e0ad143d43933295bf0e1d95dbc8a08c151736ed576ea7a7"
)

CDSE_REQUIRED_COLUMNS = {
    "acquisition_date",
    "product_name",
    "cdse_product_id",
    "online_status",
    "mission_platform_prefix",
    "product_storage_type",
    "candidate_role",
    "query_profile",
    "source_url",
    "blocker_note",
}
INGESTION_REQUIRED_COLUMNS = {
    "source_name",
    "study_area",
    "source_url",
    "candidate_use",
    "geometry_access_status",
    "license_status",
    "redistribution_status",
    "next_action",
    "product_id",
    "local_path",
    "sha256",
    "source_license_status",
    "reference_mask_status",
    "ingestion_stage",
    "download_permitted_by_skeleton",
    "ready_for_processing",
    "processing_allowed",
    "reason_blocked",
}

SUPPORTED_CANDIDATE_ROLES = {
    f"{period} {storage}"
    for period in ("pre-event", "post-event", "fallback post-event")
    for storage in ("COG candidate", "SAFE alternative")
}
SUPPORTED_STORAGE_TYPES = {"COG", "SAFE"}
EXPECTED_REFERENCE_SOURCES = {
    "International Charter Activation 1004",
    "Sentinel Asia Southern Thailand 2025",
    "Academic or manual reference mask",
}

SELECTED_PRE_PRODUCT_ID = "4e473302-943c-4798-8bfc-8287167792ed"
SELECTED_POST_PRODUCT_ID = "d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc"

BLOCKERS: tuple[dict[str, str], ...] = (
    {
        "code": "selected_pair_assets_not_acquired",
        "detail": "The locked metadata pair has not been downloaded to the controlled external workspace.",
    },
    {
        "code": "selected_pair_checksums_missing",
        "detail": "No file-level SHA-256 checksums bind the selected Hat Yai Sentinel-1 products.",
    },
    {
        "code": "selected_pair_grid_not_verified",
        "detail": "Footprint coverage, CRS, raster grid, polarization bands, and pixel alignment cannot be verified without the selected source assets.",
    },
    {
        "code": "reference_permissions_unresolved",
        "detail": "Reference geometry access, validation use, derived reporting, ML-label use, and redistribution permissions are not cleared.",
    },
    {
        "code": "qualified_reference_mask_missing",
        "detail": "No qualified Hat Yai event-flood reference mask exists in the committed evidence.",
    },
    {
        "code": "manual_weak_reference_mask_missing",
        "detail": "No checksum-bound Hat Yai manual weak-reference mask exists.",
    },
)

NEXT_ACTIONS: tuple[str, ...] = (
    f"Acquire the locked original SAFE pair outside Git ({SELECTED_PRE_PRODUCT_ID} pre-event; {SELECTED_POST_PRODUCT_ID} post-event).",
    "Bind source terms, file sizes, SHA-256 checksums, footprint coverage, polarization bands, CRS, and grid alignment in a Hat Yai file manifest.",
    "Obtain a qualified event reference with explicit validation, derived-reporting, ML-label, and redistribution decisions, or create a separately labeled manual weak-reference mask under the project protocol.",
    "Run the deterministic baseline and spatial validation only after the applicable processing and reference gates pass.",
    "Generate candidate decision inputs and enable the Hat Yai dashboard story only after traceable metrics and non-operational decision artifacts exist.",
)

TOP_LEVEL_FIELDS = {
    "schema_version",
    "study_area_id",
    "study_area_name",
    "dataset_mode",
    "operational_status",
    "official_warning",
    "status",
    "generated_at",
    "source_timestamp",
    "source_name",
    "confidence_class",
    "assumptions",
    "data_version",
    "input_artifacts",
    "candidate_product_ids",
    "sentinel1_candidates",
    "reference_candidates",
    "pre_post_pair_status",
    "locked_pre_post_pair",
    "selected_metadata_pair",
    "pair_assets_acquired",
    "pair_asset_checksums_recorded",
    "checksum_bound_external_assets",
    "qualified_reference_mask_available",
    "manual_weak_reference_mask_available",
    "processing_allowed",
    "candidate_metrics_available",
    "decision_outputs_available",
    "dashboard_story_available",
    "can_feed_decision_layer",
    "reason_blocked",
    "blockers",
    "next_actions",
    "receipt_sha256",
}

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
PRODUCT_NAME_RE = re.compile(
    r"S1[AC]_IW_GRDH_1SDV_\d{8}T\d{6}_\d{8}T\d{6}_\d{6}_"
    r"[0-9A-F]{6}_[0-9A-F]{4}(?:_COG)?\.SAFE"
)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PRIVATE_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:[A-Za-z]:[\\/]|file://|"
    r"\\\\[^\\/\s]+[\\/][^\\/\s]+|"
    r"/(?:home|Users|private|tmp|var|opt|mnt|srv|root|Volumes|data|"
    r"workspace|usr|run)(?:[\\/]|$))",
    re.IGNORECASE,
)


class HatYaiReadinessError(ValueError):
    """Raised when Hat Yai readiness evidence is malformed or substituted."""


def build_hat_yai_readiness_receipt(
    cdse_metadata_path: str | Path,
    ingestion_manifest_path: str | Path,
    *,
    generated_at: str,
) -> dict[str, Any]:
    """Build a pinned, non-operational Hat Yai readiness receipt.

    The input paths may point to byte-identical copies, but their content must
    match the pinned committed snapshots.  This prevents a different product
    list or ingestion manifest from inheriting the same blocked-status receipt.
    """

    generated_at = _utc_timestamp(generated_at, "generated_at")
    source_paths = {
        "outputs/cdse_hat_yai_2025_metadata.csv": Path(cdse_metadata_path),
        "outputs/real_data_ingestion_manifest.csv": Path(ingestion_manifest_path),
    }
    input_artifacts: list[dict[str, str]] = []
    for artifact_id, source_path in source_paths.items():
        if not source_path.is_file():
            raise HatYaiReadinessError(f"Required input does not exist: {artifact_id}")
        digest = compute_sha256(source_path)
        expected = PINNED_INPUT_SHA256[artifact_id]
        if digest != expected:
            raise HatYaiReadinessError(
                f"Pinned SHA-256 mismatch for {artifact_id}; substituted input rejected."
            )
        input_artifacts.append(
            {
                "artifact_id": artifact_id,
                "sha256": digest,
                "role": (
                    "sentinel1_product_candidate_metadata"
                    if "cdse_" in artifact_id
                    else "ingestion_and_reference_candidate_gate"
                ),
            }
        )

    cdse_rows = _read_csv(source_paths["outputs/cdse_hat_yai_2025_metadata.csv"])
    ingestion_rows = _read_csv(
        source_paths["outputs/real_data_ingestion_manifest.csv"]
    )
    candidates = _validate_cdse_rows(cdse_rows)
    references = _validate_ingestion_rows(ingestion_rows)

    source_timestamp = max(row["acquisition_date"] for row in candidates)
    data_version_material = "|".join(
        item["sha256"] for item in sorted(input_artifacts, key=lambda row: row["artifact_id"])
    )
    data_version = "sha256:" + hashlib.sha256(
        data_version_material.encode("ascii")
    ).hexdigest()
    blocker_codes = [item["code"] for item in BLOCKERS]
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "study_area_id": STUDY_AREA_ID,
        "study_area_name": STUDY_AREA_NAME,
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "status": "blocked",
        "generated_at": generated_at,
        "source_timestamp": source_timestamp,
        "source_name": "CDSE Sentinel-1 metadata and FloodGuard ingestion/reference candidate manifest",
        "confidence_class": "low",
        "assumptions": [
            "CDSE rows are catalogue metadata only and do not prove local product acquisition or scene suitability.",
            "The selected original SAFE products form a same-platform 12-day repeat metadata pair, but footprint and grid compatibility still require acquired-asset inspection.",
            "Reference-candidate metadata does not grant validation, ML-label, derived-reporting, screenshot, or redistribution permission.",
            "No Hat Yai flood metric, decision output, or dashboard story is inferred from metadata alone.",
        ],
        "data_version": data_version,
        "input_artifacts": sorted(input_artifacts, key=lambda row: row["artifact_id"]),
        "candidate_product_ids": [row["cdse_product_id"] for row in candidates],
        "sentinel1_candidates": candidates,
        "reference_candidates": references,
        "pre_post_pair_status": "locked_metadata_only",
        "locked_pre_post_pair": True,
        "selected_metadata_pair": _select_metadata_pair(candidates),
        "pair_assets_acquired": False,
        "pair_asset_checksums_recorded": False,
        "checksum_bound_external_assets": False,
        "qualified_reference_mask_available": False,
        "manual_weak_reference_mask_available": False,
        "processing_allowed": False,
        "candidate_metrics_available": False,
        "decision_outputs_available": False,
        "dashboard_story_available": False,
        "can_feed_decision_layer": False,
        "reason_blocked": "; ".join(blocker_codes),
        "blockers": [dict(item) for item in BLOCKERS],
        "next_actions": list(NEXT_ACTIONS),
    }
    _reject_private_paths(receipt)
    receipt["receipt_sha256"] = _receipt_sha256(receipt)
    validate_hat_yai_readiness_receipt(
        receipt,
        cdse_metadata_path=cdse_metadata_path,
        ingestion_manifest_path=ingestion_manifest_path,
    )
    return receipt


def validate_hat_yai_readiness_receipt(
    receipt: Mapping[str, Any],
    *,
    cdse_metadata_path: str | Path | None = None,
    ingestion_manifest_path: str | Path | None = None,
) -> None:
    """Validate receipt structure, safety claims, self-hash, and source binding."""

    if not isinstance(receipt, Mapping):
        raise HatYaiReadinessError("Hat Yai readiness receipt must be an object.")
    fields = set(receipt)
    if fields != TOP_LEVEL_FIELDS:
        missing = sorted(TOP_LEVEL_FIELDS - fields)
        extra = sorted(fields - TOP_LEVEL_FIELDS)
        raise HatYaiReadinessError(
            "Hat Yai readiness receipt fields do not match the v1 contract: "
            f"missing={missing}; extra={extra}."
        )
    _reject_private_paths(receipt)
    if receipt["schema_version"] != SCHEMA_VERSION:
        raise HatYaiReadinessError("Unsupported Hat Yai readiness schema_version.")
    expected_scalars = {
        "study_area_id": STUDY_AREA_ID,
        "study_area_name": STUDY_AREA_NAME,
        "dataset_mode": "candidate",
        "operational_status": "non_operational",
        "official_warning": False,
        "status": "blocked",
        "confidence_class": "low",
        "pre_post_pair_status": "locked_metadata_only",
        "locked_pre_post_pair": True,
        "pair_assets_acquired": False,
        "pair_asset_checksums_recorded": False,
        "checksum_bound_external_assets": False,
        "qualified_reference_mask_available": False,
        "manual_weak_reference_mask_available": False,
        "processing_allowed": False,
        "candidate_metrics_available": False,
        "decision_outputs_available": False,
        "dashboard_story_available": False,
        "can_feed_decision_layer": False,
    }
    for field, expected in expected_scalars.items():
        if receipt[field] != expected or type(receipt[field]) is not type(expected):
            raise HatYaiReadinessError(
                f"Unsupported Hat Yai readiness claim: {field} must be {expected!r}."
            )
    selected_pair = receipt["selected_metadata_pair"]
    if not isinstance(selected_pair, Mapping) or selected_pair != _expected_pair_contract(
        receipt["sentinel1_candidates"]
    ):
        raise HatYaiReadinessError(
            "Hat Yai selected metadata pair is incomplete or substituted."
        )
    _utc_timestamp(str(receipt["generated_at"]), "generated_at")
    _utc_timestamp(str(receipt["source_timestamp"]), "source_timestamp")
    if receipt["blockers"] != [dict(item) for item in BLOCKERS]:
        raise HatYaiReadinessError("Hat Yai blocker set is incomplete or substituted.")
    if receipt["next_actions"] != list(NEXT_ACTIONS):
        raise HatYaiReadinessError("Hat Yai next-action set is incomplete or substituted.")
    expected_reason = "; ".join(item["code"] for item in BLOCKERS)
    if receipt["reason_blocked"] != expected_reason:
        raise HatYaiReadinessError("Hat Yai reason_blocked is inconsistent with blockers.")
    if not isinstance(receipt["assumptions"], list) or not receipt["assumptions"]:
        raise HatYaiReadinessError("Hat Yai assumptions must be a non-empty list.")
    if not isinstance(receipt["sentinel1_candidates"], list) or not receipt[
        "sentinel1_candidates"
    ]:
        raise HatYaiReadinessError("Hat Yai Sentinel-1 candidates must be non-empty.")
    candidate_ids = [
        str(row.get("cdse_product_id", "")) for row in receipt["sentinel1_candidates"]
    ]
    if receipt["candidate_product_ids"] != candidate_ids:
        raise HatYaiReadinessError("Hat Yai product ID list does not match candidate rows.")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise HatYaiReadinessError("Hat Yai product candidate IDs must be unique.")
    for candidate in receipt["sentinel1_candidates"]:
        _validate_public_candidate(candidate)
    if _canonical_digest(receipt["sentinel1_candidates"]) != (
        PINNED_PUBLIC_CANDIDATE_SET_SHA256
    ):
        raise HatYaiReadinessError("Hat Yai public candidate set is substituted.")
    if not isinstance(receipt["reference_candidates"], list) or {
        str(row.get("source_name", "")) for row in receipt["reference_candidates"]
    } != EXPECTED_REFERENCE_SOURCES:
        raise HatYaiReadinessError("Hat Yai reference candidate set is incomplete.")
    if _canonical_digest(receipt["reference_candidates"]) != (
        PINNED_REFERENCE_CANDIDATE_SET_SHA256
    ):
        raise HatYaiReadinessError("Hat Yai reference candidate claims are substituted.")

    input_artifacts = receipt["input_artifacts"]
    if not isinstance(input_artifacts, list) or len(input_artifacts) != 2:
        raise HatYaiReadinessError("Hat Yai receipt must bind exactly two inputs.")
    artifact_hashes: dict[str, str] = {}
    for item in input_artifacts:
        if set(item) != {"artifact_id", "sha256", "role"}:
            raise HatYaiReadinessError("Hat Yai input artifact fields are malformed.")
        artifact_id = str(item["artifact_id"])
        digest = str(item["sha256"])
        if artifact_id not in PINNED_INPUT_SHA256 or digest != PINNED_INPUT_SHA256[
            artifact_id
        ]:
            raise HatYaiReadinessError("Hat Yai input artifact identity is substituted.")
        artifact_hashes[artifact_id] = digest
    if set(artifact_hashes) != set(PINNED_INPUT_SHA256):
        raise HatYaiReadinessError("Hat Yai pinned input set is incomplete.")
    material = "|".join(artifact_hashes[key] for key in sorted(artifact_hashes))
    expected_data_version = "sha256:" + hashlib.sha256(material.encode("ascii")).hexdigest()
    if receipt["data_version"] != expected_data_version:
        raise HatYaiReadinessError("Hat Yai data_version does not bind the input set.")
    recorded_hash = receipt["receipt_sha256"]
    if not isinstance(recorded_hash, str) or not SHA256_RE.fullmatch(recorded_hash):
        raise HatYaiReadinessError("Hat Yai receipt_sha256 must be a lowercase SHA-256.")
    if recorded_hash != _receipt_sha256(receipt):
        raise HatYaiReadinessError("Hat Yai readiness receipt self-hash mismatch.")

    if (cdse_metadata_path is None) != (ingestion_manifest_path is None):
        raise HatYaiReadinessError("Both source inputs are required for source validation.")
    if cdse_metadata_path is not None and ingestion_manifest_path is not None:
        source_paths = {
            "outputs/cdse_hat_yai_2025_metadata.csv": Path(cdse_metadata_path),
            "outputs/real_data_ingestion_manifest.csv": Path(ingestion_manifest_path),
        }
        for artifact_id, source_path in source_paths.items():
            if not source_path.is_file() or compute_sha256(source_path) != artifact_hashes[
                artifact_id
            ]:
                raise HatYaiReadinessError(
                    f"Hat Yai source substitution detected for {artifact_id}."
                )


def write_hat_yai_readiness_outputs(
    receipt: Mapping[str, Any],
    *,
    json_output_path: str | Path,
    markdown_output_path: str | Path,
) -> tuple[Path, Path]:
    """Validate and write the JSON receipt plus its Markdown status view."""

    validate_hat_yai_readiness_receipt(receipt)
    json_target = Path(json_output_path)
    markdown_target = Path(markdown_output_path)
    if json_target.suffix.lower() != ".json":
        raise HatYaiReadinessError("Hat Yai readiness receipt output must be JSON.")
    if markdown_target.suffix.lower() != ".md":
        raise HatYaiReadinessError("Hat Yai readiness summary output must be Markdown.")
    json_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    json_target.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_target.write_text(render_hat_yai_readiness_markdown(receipt), encoding="utf-8")
    return json_target, markdown_target


def load_hat_yai_readiness_receipt(
    path: str | Path,
    *,
    cdse_metadata_path: str | Path | None = None,
    ingestion_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and validate a readiness receipt, optionally against source files."""

    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HatYaiReadinessError("Hat Yai readiness JSON is unreadable or malformed.") from exc
    if not isinstance(value, dict):
        raise HatYaiReadinessError("Hat Yai readiness JSON must contain one object.")
    validate_hat_yai_readiness_receipt(
        value,
        cdse_metadata_path=cdse_metadata_path,
        ingestion_manifest_path=ingestion_manifest_path,
    )
    return value


def render_hat_yai_readiness_markdown(receipt: Mapping[str, Any]) -> str:
    """Render a compact technical status report from a validated receipt."""

    validate_hat_yai_readiness_receipt(receipt)
    lines = [
        "# Hat Yai / Songkhla 2025 Readiness Status",
        "",
        "> **BLOCKED — candidate metadata only. Non-operational. Not an official warning.**",
        "",
        "## Technical summary",
        "",
        f"FloodGuard has a pinned catalogue snapshot with {len(receipt['sentinel1_candidates'])} Sentinel-1 candidates and a locked metadata-only original SAFE pair. The selected files have not been acquired or checksum-bound, their grid compatibility is unverified, and no qualified/manual reference mask exists. Candidate metrics, decision outputs, and the dashboard story therefore remain unavailable.",
        "",
        f"- Dataset mode: `{receipt['dataset_mode']}`",
        f"- Operational status: `{receipt['operational_status']}`",
        f"- Source timestamp: `{receipt['source_timestamp']}`",
        f"- Confidence: `{receipt['confidence_class']}`",
        f"- Receipt SHA-256: `{receipt['receipt_sha256']}`",
        "",
        "## Gate status",
        "",
        "| Gate | Status |",
        "| --- | --- |",
        "| Pre/post metadata pair selection | LOCKED_METADATA_ONLY |",
        "| Selected pair acquired outside Git | BLOCKED |",
        "| Selected pair checksums and grid | BLOCKED |",
        "| Checksum-bound external assets | BLOCKED |",
        "| Qualified event reference mask | BLOCKED |",
        "| Manual weak-reference mask | BLOCKED |",
        "| Processing allowed | NO |",
        "| Candidate metrics available | NO |",
        "| Decision outputs available | NO |",
        "| Dashboard story available | NO |",
        "| Can feed decision layer | NO |",
        "",
        "## Sentinel-1 catalogue candidates",
        "",
        "These are catalogue records. The named pre/post pair is selected at metadata level only; none of these rows proves a downloaded or grid-verified model input.",
        "",
        "| Acquisition (UTC) | Platform | Storage | Candidate role | CDSE product ID |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in receipt["sentinel1_candidates"]:
        lines.append(
            f"| {row['acquisition_date']} | {row['mission_platform_prefix']} | "
            f"{row['product_storage_type']} | {row['candidate_role']} | "
            f"`{row['cdse_product_id']}` |"
        )
    pair = receipt["selected_metadata_pair"]
    lines.extend(
        [
            "",
            "### Locked metadata-only pair",
            "",
            f"- Pre-event original SAFE: `{pair['pre_event']['product_id']}` at `{pair['pre_event']['acquisition_date']}`",
            f"- Post-event original SAFE: `{pair['post_event']['product_id']}` at `{pair['post_event']['acquisition_date']}`",
            f"- Selection basis: {pair['selection_basis']}",
            f"- Asset state: `{pair['asset_state']}`; checksum state: `{pair['checksum_state']}`; grid status: `{pair['grid_compatibility_status']}`",
        ]
    )
    lines.extend(
        [
            "",
            "## Reference candidates",
            "",
            "| Source | Current state | Next action |",
            "| --- | --- | --- |",
        ]
    )
    for row in receipt["reference_candidates"]:
        state = (
            f"geometry={row['geometry_access_status']}; "
            f"license={row['license_status']}; "
            f"reference={row['reference_mask_status']}"
        )
        lines.append(f"| {row['source_name']} | {state} | {row['next_action']} |")
    lines.extend(["", "## Exact blockers", ""])
    for blocker in receipt["blockers"]:
        lines.append(f"- `{blocker['code']}` — {blocker['detail']}")
    lines.extend(["", "## Required next actions", ""])
    for index, action in enumerate(receipt["next_actions"], start=1):
        lines.append(f"{index}. {action}")
    lines.extend(
        [
            "",
            "## Safety and claim boundary",
            "",
            "- No Hat Yai flood accuracy metric has been calculated.",
            "- No road, access, equity, FPPS, or A–E output has been generated for Hat Yai.",
            "- Metadata-level pair selection does not prove acquisition, footprint coverage, scene alignment, flood timing, or fitness for use.",
            "- A future manual mask may support weak-reference candidate metrics only; it cannot establish official accuracy.",
            "- The Hat Yai tile remains a future story/stress-test location until every upstream receipt is traceable and accepted.",
            "",
            "## Reproducibility",
            "",
        ]
    )
    for item in receipt["input_artifacts"]:
        lines.append(f"- `{item['artifact_id']}` — SHA-256 `{item['sha256']}`")
    lines.append("")
    return "\n".join(lines)


def compute_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return the lowercase SHA-256 digest of a local input file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise HatYaiReadinessError(f"CSV header is missing or duplicated: {path.name}")
            return [
                {str(key): str(value or "").strip() for key, value in row.items()}
                for row in reader
            ]
    except (OSError, csv.Error) as exc:
        raise HatYaiReadinessError(f"Unable to read Hat Yai input CSV: {path.name}") from exc


def _validate_cdse_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        raise HatYaiReadinessError("Hat Yai CDSE metadata must contain candidate rows.")
    missing = CDSE_REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise HatYaiReadinessError(
            "Hat Yai CDSE metadata is missing columns: " + ", ".join(sorted(missing))
        )
    candidates: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for row in rows:
        _reject_private_paths(row)
        if any(not row[column] for column in CDSE_REQUIRED_COLUMNS):
            raise HatYaiReadinessError("Hat Yai CDSE metadata contains blank required values.")
        if row["query_profile"] != STUDY_AREA_ID:
            raise HatYaiReadinessError("Hat Yai CDSE query_profile substitution detected.")
        if row["candidate_role"] not in SUPPORTED_CANDIDATE_ROLES:
            raise HatYaiReadinessError(
                "Unsupported Hat Yai product-role claim; v1 accepts event-window metadata only."
            )
        if row["product_storage_type"] not in SUPPORTED_STORAGE_TYPES:
            raise HatYaiReadinessError("Unsupported Hat Yai product storage type.")
        if row["online_status"].casefold() not in {"true", "false"}:
            raise HatYaiReadinessError("Hat Yai online_status must be a strict boolean.")
        if not UUID_RE.fullmatch(row["cdse_product_id"]):
            raise HatYaiReadinessError("Hat Yai CDSE product ID is malformed.")
        if not PRODUCT_NAME_RE.fullmatch(row["product_name"]):
            raise HatYaiReadinessError("Hat Yai Sentinel-1 product name is malformed.")
        if row["mission_platform_prefix"] not in {"S1A", "S1C"} or not row[
            "product_name"
        ].startswith(row["mission_platform_prefix"] + "_"):
            raise HatYaiReadinessError("Hat Yai mission platform identity is inconsistent.")
        expected_storage = "COG" if "_COG.SAFE" in row["product_name"] else "SAFE"
        if row["product_storage_type"] != expected_storage:
            raise HatYaiReadinessError("Hat Yai product storage claim is inconsistent.")
        _utc_timestamp(row["acquisition_date"], "acquisition_date")
        if row["cdse_product_id"] in seen_ids or row["product_name"] in seen_names:
            raise HatYaiReadinessError("Hat Yai CDSE candidates must be unique.")
        seen_ids.add(row["cdse_product_id"])
        seen_names.add(row["product_name"])
        _require_https(row["source_url"], "CDSE source_url")
        candidates.append(
            {
                "acquisition_date": row["acquisition_date"],
                "product_name": row["product_name"],
                "cdse_product_id": row["cdse_product_id"],
                "online_status_at_snapshot": row["online_status"].casefold() == "true",
                "mission_platform_prefix": row["mission_platform_prefix"],
                "product_storage_type": row["product_storage_type"],
                "candidate_role": row["candidate_role"],
            }
        )
    candidates.sort(key=lambda row: (row["acquisition_date"], row["product_name"]))
    _select_metadata_pair(candidates)
    return candidates


def _select_metadata_pair(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the exact original-SAFE metadata pair or fail closed."""

    by_id = {str(row["cdse_product_id"]): row for row in candidates}
    if SELECTED_PRE_PRODUCT_ID not in by_id or SELECTED_POST_PRODUCT_ID not in by_id:
        raise HatYaiReadinessError("Locked Hat Yai metadata pair is missing from CDSE input.")
    pre = by_id[SELECTED_PRE_PRODUCT_ID]
    post = by_id[SELECTED_POST_PRODUCT_ID]
    expected = {
        "pre_event": {
            "product_id": SELECTED_PRE_PRODUCT_ID,
            "product_name": "S1A_IW_GRDH_1SDV_20251111T230309_20251111T230334_061836_07BB06_E216.SAFE",
            "acquisition_date": "2025-11-11T23:03:09.801147Z",
            "candidate_role": "pre-event SAFE alternative",
        },
        "post_event": {
            "product_id": SELECTED_POST_PRODUCT_ID,
            "product_name": "S1A_IW_GRDH_1SDV_20251123T230309_20251123T230334_062011_07C1DB_15C6.SAFE",
            "acquisition_date": "2025-11-23T23:03:09.290537Z",
            "candidate_role": "post-event SAFE alternative",
        },
        "selection_basis": "same S1A platform and IW_GRDH_1SDV mode; 12-day repeat; absolute-orbit difference 175; original SAFE products selected instead of COG derivatives",
        "asset_state": "not_acquired",
        "checksum_state": "not_recorded",
        "grid_compatibility_status": "not_verified_without_assets",
    }
    for role, row in (("pre_event", pre), ("post_event", post)):
        for field, expected_value in expected[role].items():
            source_field = "cdse_product_id" if field == "product_id" else field
            if row[source_field] != expected_value:
                raise HatYaiReadinessError(
                    f"Locked Hat Yai {role} metadata identity is inconsistent."
                )
        if row["product_storage_type"] != "SAFE" or row[
            "mission_platform_prefix"
        ] != "S1A":
            raise HatYaiReadinessError(
                f"Locked Hat Yai {role} product must be an original S1A SAFE row."
            )
    return expected


def _expected_pair_contract(candidates: object) -> dict[str, Any]:
    if not isinstance(candidates, list):
        raise HatYaiReadinessError("Hat Yai candidate list is malformed.")
    return _select_metadata_pair(candidates)


def _validate_ingestion_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        raise HatYaiReadinessError("Ingestion manifest must contain reference rows.")
    missing = INGESTION_REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise HatYaiReadinessError(
            "Ingestion manifest is missing columns: " + ", ".join(sorted(missing))
        )
    selected = [row for row in rows if "Hat Yai / Songkhla 2025" in row["study_area"]]
    if {row["source_name"] for row in selected} != EXPECTED_REFERENCE_SOURCES:
        raise HatYaiReadinessError("Hat Yai ingestion/reference candidate set is substituted.")
    references: list[dict[str, str]] = []
    for row in sorted(selected, key=lambda item: item["source_name"]):
        _reject_private_paths(row)
        for column in INGESTION_REQUIRED_COLUMNS:
            if not row[column]:
                raise HatYaiReadinessError(
                    f"Hat Yai ingestion row has blank required value: {column}."
                )
        for boolean_column in (
            "download_permitted_by_skeleton",
            "ready_for_processing",
            "processing_allowed",
        ):
            if row[boolean_column].casefold() not in {"true", "false"}:
                raise HatYaiReadinessError(
                    f"Hat Yai {boolean_column} must be a strict boolean."
                )
            if row[boolean_column].casefold() != "false":
                raise HatYaiReadinessError(
                    f"Unsupported Hat Yai readiness claim: {boolean_column} must remain false."
                )
        if row["ingestion_stage"] != "metadata_only":
            raise HatYaiReadinessError("Hat Yai ingestion stage must remain metadata_only.")
        if row["product_id"] != "not_selected" or row["local_path"] != "not_acquired":
            raise HatYaiReadinessError(
                "Hat Yai v1 has no selected or acquired reference product; unsupported claim rejected."
            )
        if row["sha256"] != "not_acquired":
            raise HatYaiReadinessError(
                "Hat Yai v1 has no checksum-bound reference asset; unsupported claim rejected."
            )
        if row["reference_mask_status"] not in {"unresolved", "not_confirmed"}:
            raise HatYaiReadinessError(
                "Hat Yai v1 has no qualified reference mask; unsupported claim rejected."
            )
        if row["license_status"] != "unresolved" or row[
            "redistribution_status"
        ] != "unresolved":
            raise HatYaiReadinessError(
                "Hat Yai reference permissions are not cleared in the pinned snapshot."
            )
        if row["source_url"].startswith("http"):
            _require_https(row["source_url"], "reference source_url")
        references.append(
            {
                "source_name": row["source_name"],
                "candidate_use": row["candidate_use"],
                "source_url": row["source_url"],
                "geometry_access_status": row["geometry_access_status"],
                "license_status": row["license_status"],
                "redistribution_status": row["redistribution_status"],
                "reference_mask_status": row["reference_mask_status"],
                "next_action": row["next_action"],
            }
        )
    return references


def _validate_public_candidate(candidate: object) -> None:
    if not isinstance(candidate, Mapping):
        raise HatYaiReadinessError("Hat Yai candidate entry must be an object.")
    required = {
        "acquisition_date",
        "product_name",
        "cdse_product_id",
        "online_status_at_snapshot",
        "mission_platform_prefix",
        "product_storage_type",
        "candidate_role",
    }
    if set(candidate) != required:
        raise HatYaiReadinessError("Hat Yai candidate entry fields are malformed.")
    if candidate["candidate_role"] not in SUPPORTED_CANDIDATE_ROLES:
        raise HatYaiReadinessError("Unsupported Hat Yai pre/post product claim.")
    if type(candidate["online_status_at_snapshot"]) is not bool:
        raise HatYaiReadinessError("Hat Yai candidate online status must be boolean.")
    _utc_timestamp(str(candidate["acquisition_date"]), "candidate acquisition_date")
    if not UUID_RE.fullmatch(str(candidate["cdse_product_id"])):
        raise HatYaiReadinessError("Hat Yai candidate product ID is malformed.")


def _receipt_sha256(receipt: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_timestamp(value: str, label: str) -> str:
    if not value or not value.endswith("Z"):
        raise HatYaiReadinessError(f"{label} must be an ISO-8601 UTC timestamp ending Z.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HatYaiReadinessError(f"{label} is not a valid ISO-8601 timestamp.") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise HatYaiReadinessError(f"{label} must be UTC.")
    return value


def _require_https(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise HatYaiReadinessError(f"{label} must be a public HTTPS URL without credentials.")


def _reject_private_paths(value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if PRIVATE_PATH_RE.search(serialized):
        raise HatYaiReadinessError("Hat Yai public evidence contains a private absolute path.")
