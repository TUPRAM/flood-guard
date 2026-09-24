import hashlib
import zipfile
from pathlib import Path

import pytest

from floodguard.cdse_download import CDSEDownloadError
from floodguard.cdse_sentinel2_reference import (
    MAE_SAI_SENTINEL2_REFERENCE_PRODUCT_NAME as NAME,
    build_sentinel2_reference_acquisition_manifest,
    validate_existing_sentinel2_safe_zip,
)

ROOT = NAME
GRANULE = f"{ROOT}/GRANULE/L2A_T47QNC_A039415_20240915T040209"
BANDS = [
    f"{GRANULE}/IMG_DATA/R10m/T47QNC_20240915T034529_B03_10m.jp2",
    f"{GRANULE}/IMG_DATA/R10m/T47QNC_20240915T034529_B04_10m.jp2",
    f"{GRANULE}/IMG_DATA/R10m/T47QNC_20240915T034529_B08_10m.jp2",
    f"{GRANULE}/IMG_DATA/R20m/T47QNC_20240915T034529_B11_20m.jp2",
    f"{GRANULE}/IMG_DATA/R20m/T47QNC_20240915T034529_SCL_20m.jp2",
]


def _zip(directory: Path, members: list[str]) -> Path:
    path = directory / (NAME.removesuffix(".SAFE") + ".zip")
    with zipfile.ZipFile(path, "w") as archive:
        for member in members:
            archive.writestr(member, b"x")
    return path


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch):
    for key in ("CDSE_ACCESS_TOKEN", "CDSE_USERNAME", "CDSE_PASSWORD"):
        monkeypatch.delenv(key, raising=False)


def test_without_credentials_the_row_is_blocked_and_never_processing_allowed(tmp_path):
    frame = build_sentinel2_reference_acquisition_manifest(external_data_dir=tmp_path, retrieved_at_utc="2026-09-24T00:00:00Z")
    row = frame.iloc[0]
    assert row["download_status"] == "blocked_missing_cdse_credentials"
    assert row["sha256_status"] == "not_recorded"
    assert bool(row["processing_allowed"]) is False
    assert row["reference_mask_status"] == "candidate_imagery_not_a_reference"
    assert not any(tmp_path.iterdir())


def test_register_existing_hashes_a_complete_safe_zip(tmp_path):
    path = _zip(tmp_path, [f"{ROOT}/MTD_MSIL2A.xml", f"{ROOT}/manifest.safe", *BANDS])
    frame = build_sentinel2_reference_acquisition_manifest(external_data_dir=tmp_path, register_existing=True)
    row = frame.iloc[0]
    assert row["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert row["download_status"] == "registered_existing_validated_safe_zip_outside_git"
    assert bool(row["processing_allowed"]) is False


@pytest.mark.parametrize(
    "members, message",
    [
        ([f"{ROOT}/manifest.safe", *BANDS], "MTD_MSIL2A.xml"),
        ([f"{ROOT}/MTD_MSIL2A.xml", f"{ROOT}/manifest.safe", *BANDS[:-1]], "SCL_20m"),
        ([f"{ROOT}/MTD_MSIL2A.xml", f"{ROOT}/manifest.safe", *BANDS, "other/escape.txt"], "outside product root"),
    ],
)
def test_register_existing_fails_closed_on_incomplete_or_unsafe_archives(tmp_path, members, message):
    _zip(tmp_path, members)
    with pytest.raises(CDSEDownloadError, match=message):
        build_sentinel2_reference_acquisition_manifest(external_data_dir=tmp_path, register_existing=True)


def test_validator_rejects_non_sentinel2_names(tmp_path):
    with pytest.raises(CDSEDownloadError, match="Sentinel-2"):
        validate_existing_sentinel2_safe_zip(tmp_path / "x.zip", expected_product_name="S1A_IW_GRDH_x.SAFE")
