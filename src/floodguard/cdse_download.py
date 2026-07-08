"""Credential-gated CDSE product acquisition helpers.

This module can download selected Sentinel products outside Git only when a
CDSE token or username/password are provided. Without credentials it writes a
blocked acquisition manifest and performs no download.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
CDSE_PRODUCT_VALUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
)
DEFAULT_EXTERNAL_DATA_DIR = Path.home() / "Documents" / "FloodGuard_external_data" / "cdse" / "mae_sai_2024"
MAE_SAI_SELECTED_PRODUCT_IDS: tuple[str, ...] = (
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
    dry_run: bool = False,
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
        dry_run=dry_run,
        retrieved_at_utc=retrieved_at_utc,
    )
    target = Path(output_path)
    if target.suffix.lower() != ".csv":
        raise CDSEDownloadError("CDSE acquisition manifest output must be CSV.")
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    return target


def build_cdse_mae_sai_acquisition_manifest(
    metadata: pd.DataFrame,
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
    access_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    dry_run: bool = False,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Build acquisition rows for selected Mae Sai Sentinel-1 products."""

    _validate_metadata(metadata)
    selected = metadata[
        metadata["cdse_product_id"].isin(MAE_SAI_SELECTED_PRODUCT_IDS)
    ].copy()
    if len(selected) != len(MAE_SAI_SELECTED_PRODUCT_IDS):
        missing = sorted(set(MAE_SAI_SELECTED_PRODUCT_IDS) - set(selected["cdse_product_id"]))
        raise CDSEDownloadError(f"Missing selected CDSE product id(s): {', '.join(missing)}")

    timestamp = retrieved_at_utc or _utc_now()
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
        local_path_hint = f"<external_data_workspace>/cdse/mae_sai_2024/{target_path.name}"

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
                "candidate_role": row["candidate_role"],
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
                "reason_blocked": "reference mask status remains unresolved; do not run baseline yet",
                "retrieved_at_utc": timestamp,
            }
        )
    return pd.DataFrame(rows, columns=CDSE_ACQUISITION_COLUMNS)


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
