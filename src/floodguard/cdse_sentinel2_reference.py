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
import http.client
import os
import re
import time
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from floodguard.cdse_download import (
    CDSE_ACQUISITION_COLUMNS,
    DEFAULT_EXTERNAL_DATA_DIR,
    CDSEDownloadError,
    build_cdse_product_download_url,
    request_cdse_access_token,
)

MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_ID = "f1a638d2-3b8f-4f9a-a862-1b651d6662c3"
MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_NAME = (
    "S2B_MSIL2A_20240915T034529_N0511_R104_T47QNC_20240915T065143.SAFE"
)
# Published by the CDSE catalogue for this product; used to resume and verify.
MAE_SAI_SENTINEL2_REFERENCE_CONTENT_LENGTH = 1_157_904_758
MAE_SAI_SENTINEL2_REFERENCE_PROVIDER_MD5 = "43a17ba47b7235c47a72abbbcb5f27fa"
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
    if not token and not (user and secret):
        row.update(download_status="blocked_missing_cdse_credentials")
        return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)

    def fresh_token() -> str:
        # CDSE access tokens expire after minutes, so each attempt gets a new one when possible.
        return request_cdse_access_token(user, secret) if user and secret else token

    target.parent.mkdir(parents=True, exist_ok=True)
    download_with_resume(
        download_url, target, fresh_token,
        expected_length=MAE_SAI_SENTINEL2_REFERENCE_CONTENT_LENGTH,
        expected_md5=MAE_SAI_SENTINEL2_REFERENCE_PROVIDER_MD5,
    )
    validate_existing_sentinel2_safe_zip(target, expected_product_name=product_name)
    row.update(sha256=_sha256(target), sha256_status="recorded", file_size_bytes=target.stat().st_size,
               download_attempted=True, download_status="downloaded_outside_git_provider_md5_verified")
    return pd.DataFrame([row], columns=CDSE_ACQUISITION_COLUMNS)


def download_with_resume(
    url: str,
    target: Path,
    get_token: Callable[[], str],
    *,
    expected_length: int,
    expected_md5: str,
    attempts: int = 8,
    read_timeout_s: float = 60.0,
    retry_wait_s: float = 5.0,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Download ``url`` to ``target``, resuming a partial file with HTTP Range.

    Each attempt fetches a fresh token and asks for the bytes after the ones
    already on disk. If the server ignores the range (HTTP 200), the file is
    restarted. When the size reaches ``expected_length`` the whole file must
    match the provider's MD5, otherwise it is deleted and an error raised.
    """

    report = progress or _print_progress
    last_error: Exception | None = None
    range_supported = True
    for attempt in range(1, attempts + 1):
        have = target.stat().st_size if target.exists() else 0
        if have == expected_length:
            break
        if have > expected_length or (have and not range_supported):
            target.unlink()
            have = 0
        headers = {"Authorization": f"Bearer {get_token()}", "User-Agent": "FloodGuard-cdse-download/0.2"}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urlopen(Request(url, headers=headers), timeout=read_timeout_s) as response:  # noqa: S310 - official CDSE endpoint
                resumed = have > 0 and getattr(response, "status", 200) == 206
                with target.open("ab" if resumed else "wb") as handle:
                    written = have if resumed else 0
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        handle.write(chunk)
                        written += len(chunk)
                        report(written, expected_length)
        except HTTPError as error:
            last_error = error
            if "Range" in headers and error.code in (416, 501):
                # The CDSE zipper does not implement byte ranges: restart the whole file.
                range_supported = False
                print(f"server refused resume (HTTP {error.code}); restarting the full download", flush=True)
                continue
            print(f"attempt {attempt}/{attempts} failed: HTTP {error.code}; retrying", flush=True)
            time.sleep(retry_wait_s)
            continue
        except (TimeoutError, URLError, ConnectionError, http.client.HTTPException, OSError) as error:
            last_error = error
            print(f"attempt {attempt}/{attempts} interrupted at {target.stat().st_size if target.exists() else 0:,} bytes: {error}; retrying", flush=True)
            time.sleep(retry_wait_s)
            continue
    size = target.stat().st_size if target.exists() else 0
    if size != expected_length:
        raise CDSEDownloadError(f"Download incomplete after {attempts} attempts ({size:,}/{expected_length:,} bytes): {last_error}")
    actual_md5 = _digest(target, "md5")
    if actual_md5 != expected_md5:
        target.unlink()
        raise CDSEDownloadError(f"Downloaded file MD5 {actual_md5} differs from provider MD5 {expected_md5}; file removed.")


_last_reported = [0]


def _print_progress(done: int, total: int) -> None:
    step = 50 * 1024 * 1024
    if done - _last_reported[0] >= step or done == total:
        _last_reported[0] = done
        print(f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB ({100 * done / total:.0f}%)", flush=True)


def _sha256(path: Path) -> str:
    return _digest(path, "sha256")


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
