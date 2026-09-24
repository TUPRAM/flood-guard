"""Credential-gated acquisition of the Mae Sai Sentinel-2 reference-candidate scene.

The 15 September 2024 Sentinel-2B L2A scene is a *candidate* for independent
optical reference imagery (see ``docs/proposal_execution/GATE_RESEARCH_DOSSIER.md``).
This module downloads or registers its original SAFE archive outside Git and
records the exact bytes by SHA-256. It never labels water, qualifies a
reference, or opens processing: every row keeps ``processing_allowed=False``
until the rights owner and Reference Authority sign.
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import pandas as pd

from floodguard.cdse_download import (
    CDSE_ACQUISITION_COLUMNS,
    DEFAULT_EXTERNAL_DATA_DIR,
    CDSEDownloadError,
    build_cdse_product_download_url,
    download_cdse_product,
    request_cdse_access_token,
)

MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_ID = "f1a638d2-3b8f-4f9a-a862-1b651d6662c3"
MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_NAME = (
    "S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143.SAFE"
)
MAE_SAI_SENTINEL2_REFERENCE_ROLE = "unsigned independent optical reference candidate"
MAE_SAI_SENTINEL2_REFERENCE_BLOCKER = (
    "rights-owner purpose record, Reference Authority qualification and human "
    "blind labels are pending; this scene is imagery for reviewers, not a flood label"
)
_S2_NAME_RE = re.compile(
    r"^S2[ABC]_MSIL2A_\d{8}T\d{6}_N\d{4}_R\d{3}_T\d{2}[A-Z]{3}_\d{8}T\d{6}\.SAFE$"
)
_REQUIRED_BAND_SUFFIXES = ("_B03_10m.jp2", "_B04_10m.jp2", "_B08_10m.jp2", "_B11_20m.jp2", "_SCL_20m.jp2")


def validate_existing_sentinel2_safe_zip(path: Path, *, expected_product_name: str) -> None:
    """Fail closed unless ``path`` is the complete expected Sentinel-2 L2A SAFE ZIP.

    Checks the exact file name, a single product root, the L2A metadata and
    manifest members, the bands reviewers need, no encrypted or escaping
    members, and ZIP CRC integrity.
    """

    if not _S2_NAME_RE.fullmatch(expected_product_name):
        raise CDSEDownloadError(f"Not a Sentinel-2 L2A SAFE product name: {expected_product_name}.")
    expected_file = expected_product_name.removesuffix(".SAFE") + ".zip"
    if path.name != expected_file:
        raise CDSEDownloadError(f"Existing product filename must be exactly {expected_file}.")
    if not path.is_file() or path.stat().st_size <= 0:
        raise CDSEDownloadError(f"Expected non-empty SAFE ZIP was not found: {expected_file}.")
    root = expected_product_name
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if any(info.flag_bits & 0x1 for info in infos):
                raise CDSEDownloadError("Encrypted ZIP members are not accepted.")
            names = set()
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                parts = PurePosixPath(normalized).parts
                if normalized.startswith("/") or ".." in parts or not parts or parts[0] != root:
                    raise CDSEDownloadError(f"SAFE ZIP member lies outside product root {root}.")
                names.add(normalized)
            for member in (f"{root}/MTD_MSIL2A.xml", f"{root}/manifest.safe"):
                if member not in names:
                    raise CDSEDownloadError(f"SAFE ZIP is missing {member}.")
            missing = [s for s in _REQUIRED_BAND_SUFFIXES if not any(n.endswith(s) and "/IMG_DATA/" in n for n in names)]
            if missing:
                raise CDSEDownloadError(f"SAFE ZIP is missing band file(s): {', '.join(missing)}.")
            try:
                corrupt = archive.testzip()
            except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
                raise CDSEDownloadError("SAFE ZIP failed CRC validation.") from exc
            if corrupt is not None:
                raise CDSEDownloadError(f"SAFE ZIP failed CRC validation at member {corrupt}.")
    except zipfile.BadZipFile as exc:
        raise CDSEDownloadError(f"Existing product is not a complete valid ZIP: {expected_file}.") from exc


def build_sentinel2_reference_acquisition_manifest(
    *,
    external_data_dir: str | Path = DEFAULT_EXTERNAL_DATA_DIR,
    access_token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    dry_run: bool = False,
    register_existing: bool = False,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    """Download, register, or record as blocked the Sentinel-2 reference-candidate SAFE.

    Credentials come from the arguments or ``CDSE_ACCESS_TOKEN`` /
    ``CDSE_USERNAME`` + ``CDSE_PASSWORD``. Without them the row is
    ``blocked_missing_cdse_credentials``; nothing is guessed.
    """

    if dry_run and register_existing:
        raise CDSEDownloadError("dry_run and register_existing are mutually exclusive.")
    timestamp = retrieved_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    product_id = MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_ID
    product_name = MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_NAME
    download_url = build_cdse_product_download_url(product_id)
    target = Path(external_data_dir) / (product_name.removesuffix(".SAFE") + ".zip")
    row: dict[str, Any] = {
        "product_id": product_id,
        "product_name": product_name,
        "candidate_role": MAE_SAI_SENTINEL2_REFERENCE_ROLE,
        "acquisition_date": "2024-09-15T03:45:29.024000Z",
        "download_url": download_url,
        "local_path_hint": f"<external_data_workspace>/{target.parent.name}/{target.name}",
        "sha256": "",
        "sha256_status": "not_recorded",
        "file_size_bytes": "",
        "download_attempted": False,
        "download_status": "",
        "source_license_status": "confirmed_copernicus_sentinel_legal_notice",
        "reference_mask_status": "candidate_imagery_not_a_reference",
        "processing_allowed": False,
        "reason_blocked": MAE_SAI_SENTINEL2_REFERENCE_BLOCKER,
        "retrieved_at_utc": timestamp,
    }

    if register_existing:
        validate_existing_sentinel2_safe_zip(target, expected_product_name=product_name)
        row.update(sha256=_sha256(target), sha256_status="recorded", file_size_bytes=target.stat().st_size,
                   download_status="registered_existing_validated_safe_zip_outside_git")
        return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)
    if dry_run:
        row.update(download_status="dry_run_no_download")
        return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)

    token = access_token or os.environ.get("CDSE_ACCESS_TOKEN", "")
    user = username or os.environ.get("CDSE_USERNAME", "")
    secret = password or os.environ.get("CDSE_PASSWORD", "")
    if not token and user and secret:
        token = request_cdse_access_token(user, secret)
    if not token:
        row.update(download_status="blocked_missing_cdse_credentials")
        return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)

    target.parent.mkdir(parents=True, exist_ok=True)
    download_cdse_product(download_url, target, token)
    validate_existing_sentinel2_safe_zip(target, expected_product_name=product_name)
    row.update(sha256=_sha256(target), sha256_status="recorded", file_size_bytes=target.stat().st_size,
               download_attempted=True, download_status="downloaded_outside_git")
    return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
