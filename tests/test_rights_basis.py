"""Tests for the UNOSAT/GISTDA product 4009 rights record and its publication gate."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re

import pytest

from floodguard.rights_basis import (
    PUBLIC_DERIVATIVE_FOLDER,
    RIGHTS_BASIS_4009_PATH,
    RightsBasisError,
    RightsNotConfirmedError,
    file_sha256,
    load_rights_basis,
    owner_confirmed,
    public_derivative_files,
    require_owner_confirmation,
    validate_rights_basis,
    verify_archive,
)

ROOT = Path(__file__).resolve().parents[1]
RECORD_PATH = ROOT / RIGHTS_BASIS_4009_PATH
PUBLIC_ROOT = ROOT / "apps" / "web" / "public"
ATTRIBUTION = "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
ARCHIVE_SHA256 = "1fe3243c2bc986d4111bb3d82aff292abccf7fb1bb1dd722747e994618b66e85"
ARCHIVE_BYTES = 27_977_189


@pytest.fixture()
def record() -> dict:
    return load_rights_basis(RECORD_PATH)


def confirmed_copy(record: dict) -> dict:
    """What the record looks like once both owners have confirmed it (test-only; never written to disk)."""
    confirmed = copy.deepcopy(record)
    confirmed["owner_confirmation"].update(status="confirmed", confirmed_by=["Putu", "Rachmania"], confirmed_on="2026-10-02")
    confirmed.update(record_status="confirmed", signed_by_human=True, human_rights_clearance=True)
    return confirmed


def pending_copy(record: dict) -> dict:
    """The record in its unconfirmed state, whatever the committed file says (test-only)."""
    pending = copy.deepcopy(record)
    pending["owner_confirmation"].update(status="pending", confirmed_by=[], confirmed_on=None)
    pending.update(record_status="draft_pending_owner_confirmation", signed_by_human=False, human_rights_clearance=False)
    return pending


def test_record_identifies_the_product_archive_and_licence(record: dict) -> None:
    assert record["schema"] == "floodguard.rights_basis_4009.v1"
    assert record["hdx"]["dataset_id"] == "287af09d-7ffd-44c8-8602-f96d6e8375f0"
    assert record["product"]["unosat_product_id"] == "4009"
    assert record["product"]["event_code"] == "FL20240912THA"
    assert record["archive"]["file_name"] == "FL20240912THA_GDB.zip"
    assert record["archive"]["sha256"] == ARCHIVE_SHA256
    assert record["archive"]["bytes"] == ARCHIVE_BYTES
    assert record["licence"]["name"] == "CC BY-SA 4.0"
    assert record["licence"]["url"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    assert record["required_attribution_text"] == ATTRIBUTION


def test_licence_notes_state_the_missing_version_and_the_exact_provider_reply(record: dict) -> None:
    notes = " ".join(record["licence"]["notes"])
    assert '"cc-by-sa"' in notes and "no version" in notes
    assert '"we approve the use"' in notes
    reply = record["provider_reply"]
    assert reply["quote"] == "we approve the use"
    assert reply["relayed_by"] == "Putu" and reply["relayed_on"] == "2026-10-01"
    assert reply["original_message_in_repo"] is False
    assert reply["names_licence_version"] is False and reply["names_credit_wording"] is False
    assert record["hdx"]["licence_as_listed"] == "cc-by-sa" and record["hdx"]["licence_version_listed"] is None


def test_change_notice_covers_clip_repair_reprojection_and_rasterisation(record: dict) -> None:
    notice = record["change_notice"]
    assert [step["id"] for step in notice["steps"]] == ["clip", "geometry_repair", "reprojection", "rasterisation"]
    assert all(step["text"].strip() for step in notice["steps"])
    template = notice["template"]
    for word in ("clipped to Mae Sai district", "repaired", "reprojected", "rasterised", ATTRIBUTION, "CC BY-SA 4.0"):
        assert word in template
    # Every placeholder can be filled, so a derived file never ships a raw "{...}".
    filled = template.format(clip_geometry="x", repair_method="x", repair_count=0, source_crs="x", target_crs="x", cell_size_m=10)
    assert "{" not in filled and "}" not in filled


def test_limits_cover_the_points_every_4009_item_must_carry(record: dict) -> None:
    limits = " ".join(record["limitations"])
    for needle in ("Field_Validation=0", "preliminary", "not relicensed", "archived", "20241012", "22 October 2024",
                   "scenario envelope only", "never an observation"):
        assert needle in limits, needle
    assert record["hdx"]["archived"] is True
    assert record["product"]["layer_in_scope"] == "CHIANGRAI_20240801_20241012_AccumulatedFlood"
    assert record["product"]["layer_attributes_checked"]["Field_Validation"] == 0


def test_decisions_and_both_d2_signers_are_listed(record: dict) -> None:
    assert [ref["id"] for ref in record["decision_refs"]] == ["D2", "D3", "R4"]
    signed = record["signed_decision"]
    assert signed["decision"] == "D2" and signed["signed_on"] == "2026-09-30"
    assert set(signed["signers"]) == {"Putu", "Rachmania"}
    # The decision log this record transcribes names the same signers and date.
    log = (ROOT / record["decision_log"]).read_text(encoding="utf-8")
    assert "Signed: 2026-09-30 by Putu (Pram) and Rachmania." in log
    assert re.search(r"\| D2 \|.*\*\*Adopted, signed by both\*\*", log)


def test_record_carries_timestamp_confidence_assumptions_and_non_operational_flags(record: dict) -> None:
    assert record["source_timestamp"] == "2024-08-01/2024-10-22"
    assert record["confidence"] in ("high", "medium", "low") and record["confidence_reason"].strip()
    assert record["assumptions"]
    assert record["official_warning"] is False
    assert record["operational_status"] == "non_operational"
    assert record["can_feed_decision_layer"] is False
    assert record["not_legal_advice"] is True


def test_committed_record_is_either_pending_or_fully_confirmed(record: dict) -> None:
    """The owners flip the record themselves; until every confirmation field is set, the gate stays closed."""
    confirmation = record["owner_confirmation"]
    assert confirmation["required_from"] == ["Putu", "Rachmania"]
    assert confirmation["how_to_confirm"].strip()
    if confirmation["status"] == "pending":
        assert confirmation["confirmed_by"] == [] and confirmation["confirmed_on"] is None
        assert record["record_status"] == "draft_pending_owner_confirmation"
        assert record["signed_by_human"] is False and record["human_rights_clearance"] is False
        assert owner_confirmed(record) is False
        with pytest.raises(RightsNotConfirmedError, match="not confirmed by the owners"):
            require_owner_confirmation(record)
    else:
        assert confirmation["status"] == "confirmed"
        assert set(confirmation["confirmed_by"]) >= {"Putu", "Rachmania"} and confirmation["confirmed_on"]
        assert record["record_status"] == "confirmed"
        require_owner_confirmation(record)


def test_a_pending_record_keeps_the_gate_closed(record: dict) -> None:
    pending = pending_copy(record)
    validate_rights_basis(pending)
    assert owner_confirmed(pending) is False
    with pytest.raises(RightsNotConfirmedError, match="owner_confirmation.status is 'pending'"):
        require_owner_confirmation(pending)


def test_gate_opens_only_for_a_confirmed_record(record: dict) -> None:
    confirmed = confirmed_copy(record)
    validate_rights_basis(confirmed)
    require_owner_confirmation(confirmed)  # Does not raise.
    assert owner_confirmed(confirmed) is True
    for broken in ({}, {"owner_confirmation": None}, {"owner_confirmation": {"status": "Confirmed"}}, {"owner_confirmation": {"status": True}}):
        with pytest.raises(RightsNotConfirmedError):
            require_owner_confirmation({**pending_copy(record), **broken})


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r["owner_confirmation"].update(confirmed_by=["Putu"]), "missing: Rachmania"),
        (lambda r: r["owner_confirmation"].update(confirmed_on=None), "confirmed_on"),
        (lambda r: r.update(signed_by_human=False), "signed_by_human"),
        (lambda r: r.update(record_status="draft_pending_owner_confirmation"), "record_status must be confirmed"),
    ],
)
def test_a_confirmed_record_needs_both_owners_a_date_and_the_signed_flags(record: dict, mutate, message: str) -> None:
    confirmed = confirmed_copy(record)
    mutate(confirmed)
    with pytest.raises(RightsBasisError, match=message):
        require_owner_confirmation(confirmed)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(required_attribution_text=" "), "required_attribution_text"),
        (lambda r: r["licence"].update(name=""), "licence.name"),
        (lambda r: r["change_notice"].update(template=""), "change_notice.template"),
        (lambda r: r["change_notice"].update(steps=[]), "change_notice.steps"),
        (lambda r: r["archive"].update(sha256="1FE3"), "archive.sha256"),
        (lambda r: r["archive"].update(bytes=0), "archive.bytes"),
        (lambda r: r["archive"].update(relative_path="C:/data/FL20240912THA_GDB.zip"), "relative_path"),
        (lambda r: r["archive"].update(relative_path="../FL20240912THA_GDB.zip"), "relative_path"),
        (lambda r: r["signed_decision"].update(signers=["Putu"]), "both signers"),
        (lambda r: r["owner_confirmation"].update(status="approved"), "owner_confirmation.status"),
        (lambda r: r["owner_confirmation"].update(confirmed_by=["Putu"]), "pending owner confirmation"),
        (lambda r: r.update(human_rights_clearance=True), "pending record"),
        (lambda r: r.update(record_status="confirmed"), "record_status must be draft_pending_owner_confirmation"),
        (lambda r: r.update(limitations=[]), "limitations"),
        (lambda r: r.update(official_warning=True), "official_warning"),
        (lambda r: r.update(operational_status="operational"), "operational_status"),
        (lambda r: r.update(schema="floodguard.automated_rights_basis.v1"), "schema"),
    ],
)
def test_validation_rejects_incomplete_or_inconsistent_records(record: dict, mutate, message: str) -> None:
    pending = pending_copy(record)
    validate_rights_basis(pending)
    mutate(pending)
    with pytest.raises(RightsBasisError, match=message):
        validate_rights_basis(pending)


def test_loading_fails_closed_on_missing_or_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(RightsBasisError, match="not found"):
        load_rights_basis(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(RightsBasisError, match="not valid JSON"):
        load_rights_basis(bad)
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(RightsBasisError, match="JSON object"):
        load_rights_basis(bad)


def test_licence_notice_file_sits_beside_the_record_and_states_credit_licence_and_changes(record: dict) -> None:
    notice_path = ROOT / record["licence_notice_file"]
    assert notice_path.parent == RECORD_PATH.parent
    notice = notice_path.read_text(encoding="utf-8")
    for needle in (ATTRIBUTION, "CC BY-SA 4.0", record["licence"]["url"], record["licence"]["legal_code_url"], ARCHIVE_SHA256,
                   "Field_Validation=0", "clipped to Mae Sai district", "repaired", "reprojected", "rasterised",
                   "not legal advice", "not an official warning"):
        assert needle in notice, needle
    # Reader-facing text is bilingual: the Thai half repeats the credit, licence and limits.
    english, thai = notice.split("-" * 80)
    # The notice says "draft" in both languages exactly as long as the owners have not confirmed the record.
    pending = not owner_confirmed(record)
    assert ("STATUS: DRAFT" in english) is pending
    assert ("สถานะ: ฉบับร่าง" in thai) is pending
    assert re.search(r"[\u0E00-\u0E7F]", thai)
    for needle in (ATTRIBUTION, "CC BY-SA 4.0", record["licence"]["url"], "Field_Validation=0", "ไม่ใช่การเตือนภัยอย่างเป็นทางการ"):
        assert needle in thai, needle


def test_record_and_notice_use_lf_and_carry_no_local_path() -> None:
    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    for path in (RECORD_PATH, ROOT / record["licence_notice_file"]):
        data = path.read_bytes()
        assert b"\r" not in data, path.name
        assert data.endswith(b"\n")
        text = data.decode("utf-8")
        # A drive letter ("C:/..."), a home folder or an escaped space would be a machine-specific path.
        assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|/Users/|\\Users\\|%20", text), path.name


def test_archive_check_compares_size_and_hash(tmp_path: Path, record: dict) -> None:
    target = tmp_path / record["archive"]["relative_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not the archive")
    with pytest.raises(RightsBasisError, match="size differs"):
        verify_archive(record, tmp_path)
    fake = copy.deepcopy(record)
    fake["archive"]["bytes"] = len(b"not the archive")
    with pytest.raises(RightsBasisError, match="SHA-256 differs"):
        verify_archive(fake, tmp_path)
    fake["archive"]["sha256"] = file_sha256(target)
    assert verify_archive(fake, tmp_path) == target
    with pytest.raises(RightsBasisError, match="archive not found"):
        verify_archive(record, tmp_path / "elsewhere")


def test_archive_hash_matches_the_zip_in_the_external_data_root(record: dict) -> None:
    external = os.environ.get("FLOODGUARD_EXTERNAL_DATA")
    if not external:
        pytest.skip("FLOODGUARD_EXTERNAL_DATA is not set; the product 4009 archive stays outside Git")
    path = verify_archive(record, Path(external))
    assert path.name == "FL20240912THA_GDB.zip"
    assert path.stat().st_size == ARCHIVE_BYTES
    assert file_sha256(path) == ARCHIVE_SHA256


def test_gate_no_public_4009_files_while_the_record_is_unconfirmed(record: dict) -> None:
    """GATE: nothing derived from product 4009 may sit under ``apps/web/public`` before the owners confirm."""
    files = public_derivative_files(PUBLIC_ROOT)
    if owner_confirmed(record):
        require_owner_confirmation(record)
        return
    listed = ", ".join(path.relative_to(PUBLIC_ROOT).as_posix() for path in files)
    assert files == [], f"product 4009 files are public while the rights record is still pending: {listed}"


def test_gate_helper_finds_files_in_any_unosat4009_folder(tmp_path: Path) -> None:
    assert public_derivative_files(tmp_path) == []
    assert public_derivative_files(tmp_path / "absent") == []
    folder = tmp_path / "studies" / "mae-sai-2024-timeline" / "r4" / PUBLIC_DERIVATIVE_FOLDER
    (folder / "nested").mkdir(parents=True)
    (folder / "envelope.png").write_bytes(b"x")
    (folder / "nested" / "LICENSE").write_bytes(b"x")
    (tmp_path / "studies" / "other.png").write_bytes(b"x")
    found = [path.relative_to(tmp_path).as_posix() for path in public_derivative_files(tmp_path)]
    assert found == ["studies/mae-sai-2024-timeline/r4/unosat4009/envelope.png",
                     "studies/mae-sai-2024-timeline/r4/unosat4009/nested/LICENSE"]
