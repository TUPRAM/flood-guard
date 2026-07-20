from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from floodguard.cdse_download import (
    CDSEDownloadError,
    MAE_SAI_SELECTED_PRODUCT_IDS,
    build_cdse_mae_sai_acquisition_manifest,
    build_cdse_product_download_url,
)


APPROVED_PRE_PRODUCT_ID = "aaaef3af-fa49-4115-bf0f-f54175e7aedf"
APPROVED_EVENT_PRODUCT_ID = "5251b74b-0bbd-4365-9eb4-fa33292e175a"
APPROVED_PRE_PRODUCT_NAME = (
    "S1A_IW_GRDH_1SDV_20240903T231600_20240903T231625_"
    "055507_06C5C9_72F7.SAFE"
)


def _safe_metadata(*, content_length: str | None = None) -> pd.DataFrame:
    row = {
        "acquisition_date": "2024-09-03T23:16:00Z",
        "product_name": APPROVED_PRE_PRODUCT_NAME,
        "cdse_product_id": APPROVED_PRE_PRODUCT_ID,
        "candidate_role": "pre-event SAFE alternative",
    }
    if content_length is not None:
        row["ContentLength"] = content_length
    return pd.DataFrame([row])


def _write_safe_zip(
    directory: Path,
    *,
    root: str = APPROVED_PRE_PRODUCT_NAME,
    include_vh_annotation: bool = True,
    member_identity: str = (
        "s1a-iw-grd-{polarization}-20240903t231600-20240903t231625-"
        "055507-06c5c9-001"
    ),
) -> Path:
    path = directory / f"{APPROVED_PRE_PRODUCT_NAME}.zip"
    directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{root}/manifest.safe", "<xfdu />")
        for polarization in ("vv", "vh"):
            identity = member_identity.format(polarization=polarization)
            archive.writestr(f"{root}/measurement/{identity}.tiff", b"measurement")
            if polarization != "vh" or include_vh_annotation:
                archive.writestr(f"{root}/annotation/{identity}.xml", "<product />")
    return path


def test_default_mae_sai_product_ids_are_approved_same_track_pair() -> None:
    assert MAE_SAI_SELECTED_PRODUCT_IDS == (
        APPROVED_PRE_PRODUCT_ID,
        APPROVED_EVENT_PRODUCT_ID,
    )


def test_cdse_download_url_targets_odata_value_endpoint() -> None:
    url = build_cdse_product_download_url(APPROVED_PRE_PRODUCT_ID)

    assert url.endswith(
        f"Products({APPROVED_PRE_PRODUCT_ID})/$value"
    )


def test_cdse_acquisition_manifest_blocks_without_credentials() -> None:
    metadata = pd.DataFrame(
        [
            {
                "acquisition_date": "2024-09-03T23:16:00Z",
                "product_name": APPROVED_PRE_PRODUCT_NAME,
                "cdse_product_id": MAE_SAI_SELECTED_PRODUCT_IDS[0],
                "candidate_role": "pre-event original SAFE",
            },
            {
                "acquisition_date": "2024-09-15T23:16:01Z",
                "product_name": (
                    "S1A_IW_GRDH_1SDV_20240915T231601_20240915T231626_"
                    "055682_06CCBA_08DA.SAFE"
                ),
                "cdse_product_id": MAE_SAI_SELECTED_PRODUCT_IDS[1],
                "candidate_role": "post-event original SAFE",
            },
        ]
    )

    manifest = build_cdse_mae_sai_acquisition_manifest(
        metadata,
        access_token="",
        username="",
        password="",
        dry_run=False,
        retrieved_at_utc="2026-07-08T00:00:00Z",
    )

    assert len(manifest) == 2
    assert set(manifest["download_status"]) == {"blocked_missing_cdse_credentials"}
    assert set(manifest["sha256_status"]) == {"not_recorded"}
    assert set(manifest["processing_allowed"]) == {False}
    assert manifest["reason_blocked"].str.contains("CDSE_ACCESS_TOKEN").all()


def test_cdse_acquisition_manifest_accepts_explicit_product_subset() -> None:
    metadata = pd.DataFrame(
        [
            {
                "acquisition_date": "2024-09-03T23:16:00Z",
                "product_name": "S1A_APPROVED_PRE_COG.SAFE",
                "cdse_product_id": APPROVED_PRE_PRODUCT_ID,
                "candidate_role": "pre-event COG candidate",
            },
            {
                "acquisition_date": "2024-09-15T23:16:01Z",
                "product_name": "S1A_APPROVED_EVENT_COG.SAFE",
                "cdse_product_id": APPROVED_EVENT_PRODUCT_ID,
                "candidate_role": "post-event COG candidate",
            },
        ]
    )

    manifest = build_cdse_mae_sai_acquisition_manifest(
        metadata,
        product_ids=(APPROVED_PRE_PRODUCT_ID,),
        dry_run=True,
        retrieved_at_utc="2026-07-10T00:00:00Z",
    )

    assert manifest["product_id"].tolist() == [APPROVED_PRE_PRODUCT_ID]
    assert manifest["download_status"].tolist() == ["dry_run_no_download"]


def test_cdse_acquisition_manifest_registers_valid_existing_safe_zip(
    tmp_path: Path,
) -> None:
    safe_zip = _write_safe_zip(tmp_path)
    metadata = _safe_metadata(content_length=str(safe_zip.stat().st_size))

    manifest = build_cdse_mae_sai_acquisition_manifest(
        metadata,
        external_data_dir=tmp_path,
        product_ids=(APPROVED_PRE_PRODUCT_ID,),
        register_existing=True,
        retrieved_at_utc="2026-07-10T00:00:00Z",
    )

    row = manifest.iloc[0]
    assert row["download_status"] == (
        "registered_existing_validated_safe_zip_outside_git"
    )
    assert row["download_attempted"] == False  # noqa: E712 - numpy bool comparison
    assert row["sha256_status"] == "recorded"
    assert len(row["sha256"]) == 64
    assert row["file_size_bytes"] == safe_zip.stat().st_size
    assert row["processing_allowed"] == False  # noqa: E712 - numpy bool comparison
    assert row["reference_mask_status"] == "unresolved"
    assert row["local_path_hint"].endswith(f"/{safe_zip.name}")


@pytest.mark.parametrize(
    ("fixture_kind", "error_pattern"),
    [
        ("missing", "was not found"),
        ("non_zip", "not a complete valid ZIP"),
        ("wrong_root", "outside the exact expected product root"),
        ("missing_vh_annotation", "missing required annotation polarization"),
        ("wrong_members", "missing required measurement polarization"),
    ],
)
def test_cdse_existing_registration_rejects_unusable_or_mismatched_archives(
    tmp_path: Path,
    fixture_kind: str,
    error_pattern: str,
) -> None:
    if fixture_kind == "non_zip":
        path = tmp_path / f"{APPROVED_PRE_PRODUCT_NAME}.zip"
        path.write_bytes(b"partial download")
    elif fixture_kind == "wrong_root":
        _write_safe_zip(tmp_path, root="S1A_WRONG_PRODUCT.SAFE")
    elif fixture_kind == "missing_vh_annotation":
        _write_safe_zip(tmp_path, include_vh_annotation=False)
    elif fixture_kind == "wrong_members":
        _write_safe_zip(
            tmp_path,
            member_identity=(
                "s1a-iw-grd-{polarization}-20240915t231601-20240915t231626-"
                "055682-06ccba-001"
            ),
        )

    with pytest.raises(CDSEDownloadError, match=error_pattern):
        build_cdse_mae_sai_acquisition_manifest(
            _safe_metadata(),
            external_data_dir=tmp_path,
            product_ids=(APPROVED_PRE_PRODUCT_ID,),
            register_existing=True,
        )


def test_cdse_existing_registration_rejects_content_length_mismatch(
    tmp_path: Path,
) -> None:
    safe_zip = _write_safe_zip(tmp_path)

    with pytest.raises(CDSEDownloadError, match="ContentLength mismatch"):
        build_cdse_mae_sai_acquisition_manifest(
            _safe_metadata(content_length=str(safe_zip.stat().st_size + 1)),
            external_data_dir=tmp_path,
            product_ids=(APPROVED_PRE_PRODUCT_ID,),
            register_existing=True,
        )


def test_cdse_existing_registration_rejects_crc_failure(tmp_path: Path) -> None:
    safe_zip = _write_safe_zip(tmp_path)
    member_name = (
        f"{APPROVED_PRE_PRODUCT_NAME}/measurement/"
        "s1a-iw-grd-vv-20240903t231600-20240903t231625-"
        "055507-06c5c9-001.tiff"
    )
    with zipfile.ZipFile(safe_zip) as archive:
        info = archive.getinfo(member_name)
        data_offset = (
            info.header_offset
            + 30
            + len(info.filename.encode("utf-8"))
            + len(info.extra)
        )
    payload = bytearray(safe_zip.read_bytes())
    payload[data_offset] ^= 0xFF
    safe_zip.write_bytes(payload)

    with pytest.raises(CDSEDownloadError, match="failed CRC validation"):
        build_cdse_mae_sai_acquisition_manifest(
            _safe_metadata(),
            external_data_dir=tmp_path,
            product_ids=(APPROVED_PRE_PRODUCT_ID,),
            register_existing=True,
        )


def test_cdse_existing_registration_rejects_dry_run_combination(
    tmp_path: Path,
) -> None:
    with pytest.raises(CDSEDownloadError, match="mutually exclusive"):
        build_cdse_mae_sai_acquisition_manifest(
            _safe_metadata(),
            external_data_dir=tmp_path,
            product_ids=(APPROVED_PRE_PRODUCT_ID,),
            dry_run=True,
            register_existing=True,
        )


def test_cdse_acquisition_cli_accepts_explicit_product_id(tmp_path: Path) -> None:
    metadata_path = tmp_path / "metadata.csv"
    output_path = tmp_path / "acquisition.csv"
    pd.DataFrame(
        [
            {
                "acquisition_date": "2024-09-03T23:16:00Z",
                "product_name": "S1A_APPROVED_PRE_COG.SAFE",
                "cdse_product_id": APPROVED_PRE_PRODUCT_ID,
                "candidate_role": "pre-event COG candidate",
            }
        ]
    ).to_csv(metadata_path, index=False)
    repo_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(  # noqa: S603 - fixed local test command
        [
            sys.executable,
            str(repo_root / "scripts" / "acquire_cdse_mae_sai_sentinel1.py"),
            "--metadata",
            str(metadata_path),
            "--output",
            str(output_path),
            "--external-data-dir",
            str(tmp_path / "external"),
            "--product-id",
            APPROVED_PRE_PRODUCT_ID,
            "--dry-run",
            "--retrieved-at",
            "2026-07-10T00:00:00Z",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = pd.read_csv(output_path, dtype=str).fillna("")
    assert manifest["product_id"].tolist() == [APPROVED_PRE_PRODUCT_ID]
    assert manifest["download_status"].tolist() == ["dry_run_no_download"]


def test_cdse_acquisition_cli_registers_existing_without_credentials(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path / "external"
    safe_zip = _write_safe_zip(external_dir)
    metadata_path = tmp_path / "metadata.csv"
    output_path = tmp_path / "acquisition.csv"
    _safe_metadata(content_length=str(safe_zip.stat().st_size)).to_csv(
        metadata_path, index=False
    )
    repo_root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(  # noqa: S603 - fixed local test command
        [
            sys.executable,
            str(repo_root / "scripts" / "acquire_cdse_mae_sai_sentinel1.py"),
            "--metadata",
            str(metadata_path),
            "--output",
            str(output_path),
            "--external-data-dir",
            str(external_dir),
            "--product-id",
            APPROVED_PRE_PRODUCT_ID,
            "--register-existing",
            "--retrieved-at",
            "2026-07-10T00:00:00Z",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = pd.read_csv(output_path, dtype=str).fillna("")
    assert manifest["download_status"].tolist() == [
        "registered_existing_validated_safe_zip_outside_git"
    ]
    assert manifest["download_attempted"].tolist() == ["False"]
    assert manifest["processing_allowed"].tolist() == ["False"]
    output_bytes = output_path.read_bytes()
    assert b"\r\n" not in output_bytes
    assert output_bytes.endswith(b"\n")


@pytest.mark.parametrize("product_ids", [(), ("",), ("duplicate", "duplicate")])
def test_cdse_acquisition_manifest_rejects_invalid_product_selection(
    product_ids: tuple[str, ...],
) -> None:
    metadata = pd.DataFrame(
        [
            {
                "acquisition_date": "2024-09-03T23:16:00Z",
                "product_name": "S1A_APPROVED_PRE_COG.SAFE",
                "cdse_product_id": APPROVED_PRE_PRODUCT_ID,
                "candidate_role": "pre-event COG candidate",
            }
        ]
    )

    with pytest.raises(CDSEDownloadError):
        build_cdse_mae_sai_acquisition_manifest(
            metadata,
            product_ids=product_ids,
            dry_run=True,
        )
