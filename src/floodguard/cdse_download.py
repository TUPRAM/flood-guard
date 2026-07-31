"""Credential-gated CDSE product acquisition and offline-registration helpers.

This module can download selected Sentinel products outside Git only when a
CDSE token or username/password are provided. Without credentials it writes a
blocked acquisition manifest and performs no download. Complete SAFE ZIPs
that were downloaded separately can be registered without credentials only
after their name, ZIP integrity, and required dual-polarization structure are
validated.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
import zlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from floodguard.ingestion import MAE_SAI_BASELINE_PRODUCT_IDS

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
CDSE_PRODUCT_VALUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
)
DEFAULT_EXTERNAL_DATA_DIR = Path.home() / "Documents" / "FloodGuard_external_data" / "cdse" / "mae_sai_2024"
# Original SAFE product identities approved for the Mae Sai baseline.
MAE_SAI_SELECTED_PRODUCT_IDS: tuple[str, ...] = MAE_SAI_BASELINE_PRODUCT_IDS
MAE_SAI_QUALIFIED_PROCESSING_BLOCKER = (
    "qualified, official, or decision-eligible processing remains blocked because "
    "reference mask status is unresolved; the non-operational cross-border calibration "
    "baseline is governed separately"
)

# Original SAFE editions are required for SNAP calibration. SNAP 13 can read
# the CDSE COG_SAFE editions but warns that their calibration LUT may be
# unreliable. The legacy September 6 / September 15 COG pair also mixes
# acquisition tracks and its local archives were mutated by GDAL PAM access.
# Those COG products therefore remain provenance/inspection records only.
MAE_SAI_RETIRED_COG_PRODUCT_IDS: tuple[str, ...] = (
    "b09f96ca-4a60-43e7-9b8d-158022f0e5bf",
    "20a9c3b8-37df-46d5-81d8-d63c7e460225",
)

CDSE_ACQUISITION_COLUMNS: tuple[str, ...] = (
    "product_id",
    "product_name",
    "candidate_role",
    "acquisition_date",
    "download_url",
    "local_path_hint",
    "sha256",
    "sha256_status",
    "file_size_bytes",
    "download_attempted",
    "download_status",
    "source_license_status",
    "reference_mask_status",
    "processing_allowed",
    "reason_blocked",
    "retrieved_at_utc",
)


class CDSEDownloadError(ValueError):
    """Raised when CDSE acquisition input is invalid."""


def write_cdse_mae_sai_acquisition_manifest(
    metadata_path: str | Path,
    output_path: str | Path,
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
    access_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    product_ids: Sequence[str] = MAE_SAI_SELECTED_PRODUCT_IDS,
    dry_run: bool = False,
    register_existing: bool = False,
    retrieved_at_utc: str | None = None,
) -> Path:
    """Write a CDSE acquisition manifest and optionally download products."""

    metadata = pd.read_csv(metadata_path, dtype=str).fillna("")
    frame = build_cdse_mae_sai_acquisition_manifest(
        metadata,
        external_data_dir=external_data_dir,
        access_token=access_token,
        username=username,
        password=password,
        product_ids=product_ids,
        dry_run=dry_run,
        register_existing=register_existing,
        retrieved_at_utc=retrieved_at_utc,
    )
    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise CDSEDownloadError("CDSE acquisition manifest output must be CSV.")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, lineterminator="\n")
    return target


def build_cdse_mae_sai_acquisition_manifest(
    metadata: pd.DataFrame,
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
    access_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    product_ids: Sequence[str] = MAE_SAI_SELECTED_PRODUCT_IDS,
    dry_run: bool = False,
    register_existing: bool = False,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Build acquisition rows for selected Mae Sai Sentinel-1 products."""

    _validate_metadata(metadata)
    if dry_run and register_existing:
        raise CDSEDownloadError(
            "dry_run and register_existing are mutually exclusive."
        )
    requested_product_ids = tuple(product_ids)
    if not requested_product_ids:
        raise CDSEDownloadError("At least one CDSE product id is required.")
    if any(not product_id.strip() for product_id in requested_product_ids):
        raise CDSEDownloadError("CDSE product ids must not be blank.")
    if len(set(requested_product_ids)) != len(requested_product_ids):
        raise CDSEDownloadError("CDSE product ids must be unique.")

    selected = metadata[
        metadata["cdse_product_id"].isin(requested_product_ids)
    ].copy()
    missing = sorted(set(requested_product_ids) - set(selected["cdse_product_id"]))
    if missing:
        raise CDSEDownloadError(f"Missing selected CDSE product id(s): {', '.join(missing)}")
    duplicates = sorted(
        selected.loc[
            selected["cdse_product_id"].duplicated(keep=False), "cdse_product_id"
        ].unique()
    )
    if duplicates:
        raise CDSEDownloadError(
            f"Duplicate selected CDSE product id(s) in metadata: {', '.join(duplicates)}"
        )
    selection_order = {
        product_id: index for index, product_id in enumerate(requested_product_ids)
    }
    selected["_selection_order"] = selected["cdse_product_id"].map(selection_order)
    selected = selected.sort_values("_selection_order").drop(columns="_selection_order")

    timestamp = retrieved_at_utc or _utc_now()
    token = ""
    if not register_existing:
        token = access_token or os.environ.get("CDSE_ACCESS_TOKEN", "")
        if not token and username and password and not dry_run:
            token = request_cdse_access_token(username, password)
        if not token and not dry_run:
            env_username = os.environ.get("CDSE_USERNAME", "")
            env_password = os.environ.get("CDSE_PASSWORD", "")
            if env_username and env_password:
                token = request_cdse_access_token(env_username, env_password)

    rows: list[dict[str, object]] = []
    target_dir = Path(external_data_dir)
    for _, row in selected.iterrows():
        product_id = row["cdse_product_id"]
        product_name = row["product_name"]
        download_url = build_cdse_product_download_url(product_id)
        target_path = target_dir / _download_file_name(product_name)
        local_path_hint = _external_path_hint(target_path)

        if register_existing:
            expected_content_length = _expected_content_length(row)
            _validate_existing_safe_zip(
                target_path,
                expected_product_name=product_name,
                expected_content_length=expected_content_length,
            )
            rows.append(
                {
                    "product_id": product_id,
                    "product_name": product_name,
                    "candidate_role": _selected_candidate_role(product_id),
                    "acquisition_date": row["acquisition_date"],
                    "download_url": download_url,
                    "local_path_hint": local_path_hint,
                    "sha256": _sha256(target_path),
                    "sha256_status": "recorded",
                    "file_size_bytes": target_path.stat().st_size,
                    "download_attempted": False,
                    "download_status": "registered_existing_validated_safe_zip_outside_git",
                    "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
                    "reference_mask_status": "unresolved",
                    "processing_allowed": False,
                    "reason_blocked": MAE_SAI_QUALIFIED_PROCESSING_BLOCKER,
                    "retrieved_at_utc": timestamp,
                }
            )
            continue

        if dry_run:
            rows.append(
                _blocked_row(
                    row,
                    download_url,
                    local_path_hint,
                    "dry_run_no_download",
                    "dry run requested; no product asset downloaded",
                    timestamp,
                )
            )
            continue
        if not token:
            rows.append(
                _blocked_row(
                    row,
                    download_url,
                    local_path_hint,
                    "blocked_missing_cdse_credentials",
                    "CDSE_ACCESS_TOKEN or CDSE_USERNAME/CDSE_PASSWORD is required for product download",
                    timestamp,
                )
            )
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        download_cdse_product(download_url, target_path, token)
        sha256 = _sha256(target_path)
        rows.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "candidate_role": _selected_candidate_role(product_id),
                "acquisition_date": row["acquisition_date"],
                "download_url": download_url,
                "local_path_hint": local_path_hint,
                "sha256": sha256,
                "sha256_status": "recorded",
                "file_size_bytes": target_path.stat().st_size,
                "download_attempted": True,
                "download_status": "downloaded_outside_git",
                "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
                "reference_mask_status": "unresolved",
                "processing_allowed": False,
                "reason_blocked": MAE_SAI_QUALIFIED_PROCESSING_BLOCKER,
                "retrieved_at_utc": timestamp,
            }
        )
    return pd.DataFrame(rows, columns=CDSE_ACQUISITION_COLUMNS)


def _selected_candidate_role(product_id: str) -> str:
    """Return the active same-track role for a selected original SAFE product."""

    roles = {
        MAE_SAI_SELECTED_PRODUCT_IDS[0]: "selected pre-event original SAFE",
        MAE_SAI_SELECTED_PRODUCT_IDS[1]: "selected post-event original SAFE",
    }
    try:
        return roles[str(product_id)]
    except KeyError as exc:
        raise CDSEDownloadError(
            f"Selected Mae Sai product has no active source role: {product_id}"
        ) from exc


def build_cdse_product_download_url(product_id: str) -> str:
    """Build a CDSE OData product asset download URL."""

    if not product_id:
        raise CDSEDownloadError("product_id is required.")
    return CDSE_PRODUCT_VALUE_URL.format(product_id=quote(product_id, safe="-"))


def request_cdse_access_token(username: str, password: str) -> str:
    """Request a CDSE access token using username/password."""

    data = (
        f"client_id=cdse-public&username={quote(username)}&password={quote(password)}"
        "&grant_type=password"
    ).encode("utf-8")
    request = Request(
        CDSE_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:  # noqa: S310 - official CDSE endpoint
        payload = json.load(response)
    token = str(payload.get("access_token", ""))
    if not token:
        raise CDSEDownloadError("CDSE token response did not include access_token.")
    return token


def download_cdse_product(download_url: str, target_path: Path, access_token: str) -> None:
    """Download one CDSE product asset to an outside-Git target path."""

    request = Request(
        download_url,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": "FloodGuard-cdse-download/0.1"},
    )
    with urlopen(request, timeout=300) as response:  # noqa: S310 - official CDSE endpoint
        with target_path.open("wb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)


def _blocked_row(
    metadata_row: pd.Series,
    download_url: str,
    local_path_hint: str,
    status: str,
    reason: str,
    timestamp: str,
) -> dict[str, object]:
    return {
        "product_id": metadata_row["cdse_product_id"],
        "product_name": metadata_row["product_name"],
        "candidate_role": metadata_row["candidate_role"],
        "acquisition_date": metadata_row["acquisition_date"],
        "download_url": download_url,
        "local_path_hint": local_path_hint,
        "sha256": "not_acquired",
        "sha256_status": "not_recorded",
        "file_size_bytes": "",
        "download_attempted": False,
        "download_status": status,
        "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
        "reference_mask_status": "unresolved",
        "processing_allowed": False,
        "reason_blocked": reason,
        "retrieved_at_utc": timestamp,
    }


def _validate_metadata(metadata: pd.DataFrame) -> None:
    required = {
        "acquisition_date",
        "product_name",
        "cdse_product_id",
        "candidate_role",
    }
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise CDSEDownloadError(f"Missing CDSE metadata column(s): {', '.join(missing)}")


def _download_file_name(product_name: str) -> str:
    return product_name if product_name.lower().endswith(".zip") else f"{product_name}.zip"


def _validate_existing_safe_zip(
    path: Path,
    *,
    expected_product_name: str,
    expected_content_length: int | None,
) -> None:
    """Fail closed unless ``path`` is the exact, complete expected SAFE ZIP."""

    expected_file_name = _download_file_name(expected_product_name)
    if path.name != expected_file_name:
        raise CDSEDownloadError(
            f"Existing product filename must be exactly {expected_file_name}."
        )
    if not expected_product_name.endswith(".SAFE"):
        raise CDSEDownloadError(
            f"Selected product is not an original SAFE product: {expected_product_name}."
        )
    if not path.is_file():
        raise CDSEDownloadError(
            f"Expected existing SAFE ZIP was not found: {expected_file_name}."
        )
    actual_size = path.stat().st_size
    if actual_size <= 0:
        raise CDSEDownloadError(f"Existing SAFE ZIP is empty: {expected_file_name}.")
    if expected_content_length is not None and actual_size != expected_content_length:
        raise CDSEDownloadError(
            "Existing SAFE ZIP ContentLength mismatch for "
            f"{expected_file_name}: expected {expected_content_length}, got {actual_size}."
        )

    product_parts = expected_product_name.removesuffix(".SAFE").split("_")
    if len(product_parts) != 9:
        raise CDSEDownloadError(
            f"Selected product name is not a recognized Sentinel-1 SAFE name: {expected_product_name}."
        )
    platform, mode, product_type = (part.lower() for part in product_parts[:3])
    start, stop, orbit, datatake = (
        product_parts[4].lower(),
        product_parts[5].lower(),
        product_parts[6].lower(),
        product_parts[7].lower(),
    )
    if not re.fullmatch(r"s1[ab]", platform) or product_type != "grdh":
        raise CDSEDownloadError(
            f"Selected product is not a Sentinel-1 GRDH SAFE product: {expected_product_name}."
        )
    member_stem = re.compile(
        rf"^{re.escape(platform)}-{re.escape(mode)}-grd-(vv|vh)-"
        rf"{re.escape(start)}-{re.escape(stop)}-{re.escape(orbit)}-"
        rf"{re.escape(datatake)}-\d{{3}}$"
    )
    expected_root = expected_product_name
    manifest_member = f"{expected_root}/manifest.safe"

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos:
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP contains no members: {expected_file_name}."
                )
            if any(info.flag_bits & 0x1 for info in infos):
                raise CDSEDownloadError(
                    f"Encrypted ZIP members are not accepted: {expected_file_name}."
                )

            names: set[str] = set()
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                member_path = PurePosixPath(normalized)
                if (
                    normalized.startswith("/")
                    or ".." in member_path.parts
                    or not member_path.parts
                    or member_path.parts[0] != expected_root
                ):
                    raise CDSEDownloadError(
                        "Existing SAFE ZIP contains a member outside the exact expected "
                        f"product root {expected_root}."
                    )
                names.add(normalized)

            if manifest_member not in names:
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP is missing {manifest_member}."
                )

            measurement_polarizations: set[str] = set()
            annotation_polarizations: set[str] = set()
            for name in names:
                member_path = PurePosixPath(name)
                if len(member_path.parts) != 3:
                    continue
                folder = member_path.parts[1]
                suffix = member_path.suffix.lower()
                match = member_stem.fullmatch(member_path.stem.lower())
                if not match:
                    continue
                polarization = match.group(1)
                if folder == "measurement" and suffix in {".tif", ".tiff"}:
                    measurement_polarizations.add(polarization)
                elif folder == "annotation" and suffix == ".xml":
                    annotation_polarizations.add(polarization)

            required = {"vv", "vh"}
            if measurement_polarizations != required:
                missing = ", ".join(sorted(required - measurement_polarizations))
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP is missing required measurement polarization(s): {missing}."
                )
            if annotation_polarizations != required:
                missing = ", ".join(sorted(required - annotation_polarizations))
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP is missing required annotation polarization(s): {missing}."
                )

            try:
                corrupt_member = archive.testzip()
            except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP failed CRC validation: {expected_file_name}."
                ) from exc
            if corrupt_member is not None:
                raise CDSEDownloadError(
                    f"Existing SAFE ZIP failed CRC validation at member {corrupt_member}."
                )
    except zipfile.BadZipFile as exc:
        raise CDSEDownloadError(
            f"Existing product is not a complete valid ZIP: {expected_file_name}."
        ) from exc


def _expected_content_length(metadata_row: pd.Series) -> int | None:
    """Return optional CDSE ContentLength from metadata, validating it strictly."""

    for column in ("ContentLength", "content_length", "content_length_bytes"):
        if column not in metadata_row.index:
            continue
        raw_value = str(metadata_row[column]).strip()
        if not raw_value:
            return None
        if not raw_value.isdigit() or int(raw_value) <= 0:
            raise CDSEDownloadError(
                f"Metadata {column} must be a positive integer when provided."
            )
        return int(raw_value)
    return None


def _external_path_hint(path: Path) -> str:
    """Render an outside-Git path hint without embedding a workstation path."""

    workspace = Path.home() / "Documents" / "FloodGuard_external_data"
    try:
        relative = path.resolve().relative_to(workspace.resolve())
    except ValueError:
        relative = Path(path.name)
    return f"<external_data_workspace>/{relative.as_posix()}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
