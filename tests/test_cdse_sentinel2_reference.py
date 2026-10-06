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


# --- resumable download -------------------------------------------------------

import floodguard.cdse_sentinel2_reference as s2ref  # noqa: E402

PAYLOAD = bytes(range(256)) * 40  # 10,240 bytes
PAYLOAD_MD5 = hashlib.md5(PAYLOAD).hexdigest()


class _FakeResponse:
    def __init__(self, body: bytes, status: int, fail_after: int | None = None):
        self.body, self.status, self.fail_after, self.sent = body, status, fail_after, 0

    def read(self, size):
        if self.fail_after is not None and self.sent >= self.fail_after:
            raise TimeoutError("The read operation timed out")
        chunk = self.body[self.sent:self.sent + min(size, 1000)]
        self.sent += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _server(monkeypatch, *, honour_range=True, fail_first_after=None):
    calls = []

    def fake_urlopen(request, timeout):
        rng = request.get_header("Range")
        calls.append(rng)
        start = int(rng.split("=")[1].rstrip("-")) if (rng and honour_range) else 0
        fail = fail_first_after if len(calls) == 1 else None
        return _FakeResponse(PAYLOAD[start:], 206 if rng and honour_range else 200, fail)

    monkeypatch.setattr(s2ref, "urlopen", fake_urlopen)
    return calls


def _download(target, **kw):
    s2ref.download_with_resume("https://example.invalid/x", target, lambda: "tok", expected_length=len(PAYLOAD),
                               expected_md5=kw.pop("md5", PAYLOAD_MD5), retry_wait_s=0, progress=lambda *_: None, **kw)


def test_resume_appends_only_the_missing_bytes(tmp_path, monkeypatch):
    target = tmp_path / "p.zip"
    target.write_bytes(PAYLOAD[:4000])
    calls = _server(monkeypatch)
    _download(target)
    assert calls == ["bytes=4000-"]
    assert target.read_bytes() == PAYLOAD


def test_timeout_mid_stream_is_retried_from_where_it_stopped(tmp_path, monkeypatch):
    target = tmp_path / "p.zip"
    calls = _server(monkeypatch, fail_first_after=3000)
    _download(target)
    assert calls[0] is None and calls[1] == "bytes=3000-"
    assert target.read_bytes() == PAYLOAD


def test_server_ignoring_range_restarts_cleanly(tmp_path, monkeypatch):
    target = tmp_path / "p.zip"
    target.write_bytes(PAYLOAD[:4000])
    _server(monkeypatch, honour_range=False)
    _download(target)
    assert target.read_bytes() == PAYLOAD


def test_md5_mismatch_removes_the_file(tmp_path, monkeypatch):
    target = tmp_path / "p.zip"
    _server(monkeypatch)
    with pytest.raises(CDSEDownloadError, match="MD5"):
        _download(target, md5="0" * 32)
    assert not target.exists()


def test_complete_file_is_not_downloaded_again(tmp_path, monkeypatch):
    target = tmp_path / "p.zip"
    target.write_bytes(PAYLOAD)
    calls = _server(monkeypatch)
    _download(target)
    assert calls == []


def test_server_refusing_range_with_501_restarts_the_full_file(tmp_path, monkeypatch):
    from urllib.error import HTTPError

    target = tmp_path / "p.zip"
    target.write_bytes(PAYLOAD[:4000])
    calls = []

    def fake_urlopen(request, timeout):
        rng = request.get_header("Range")
        calls.append(rng)
        if rng:
            raise HTTPError(request.full_url, 501, "Not Implemented", {}, None)
        return _FakeResponse(PAYLOAD, 200)

    monkeypatch.setattr(s2ref, "urlopen", fake_urlopen)
    _download(target)
    assert calls == ["bytes=4000-", None]
    assert target.read_bytes() == PAYLOAD
