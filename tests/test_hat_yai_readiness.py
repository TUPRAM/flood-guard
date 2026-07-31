from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from floodguard.hat_yai_readiness import (
    BLOCKERS,
    PINNED_INPUT_SHA256,
    HatYaiReadinessError,
    build_hat_yai_readiness_receipt,
    compute_sha256,
    load_hat_yai_readiness_receipt,
    render_hat_yai_readiness_markdown,
    validate_hat_yai_readiness_receipt,
    write_hat_yai_readiness_outputs,
)


REPO_ROOT = Path(__file__).parents[1]
CDSE = REPO_ROOT / "outputs" / "cdse_hat_yai_2025_metadata.csv"
INGESTION = REPO_ROOT / "outputs" / "real_data_ingestion_manifest.csv"
GENERATED_AT = "2026-07-20T12:00:00Z"


def _receipt() -> dict[str, object]:
    return build_hat_yai_readiness_receipt(
        CDSE,
        INGESTION,
        generated_at=GENERATED_AT,
    )


def test_build_receipt_is_pinned_and_fail_closed() -> None:
    receipt = _receipt()

    assert receipt["dataset_mode"] == "candidate"
    assert receipt["operational_status"] == "non_operational"
    assert receipt["official_warning"] is False
    assert receipt["status"] == "blocked"
    assert receipt["pre_post_pair_status"] == "locked_metadata_only"
    assert receipt["locked_pre_post_pair"] is True
    assert receipt["selected_metadata_pair"]["pre_event"]["product_id"] == (
        "4e473302-943c-4798-8bfc-8287167792ed"
    )
    assert receipt["selected_metadata_pair"]["post_event"]["product_id"] == (
        "d80b81cb-c4aa-4dbb-a7de-8a1d01fca2dc"
    )
    assert receipt["pair_assets_acquired"] is False
    assert receipt["pair_asset_checksums_recorded"] is False
    assert receipt["checksum_bound_external_assets"] is False
    assert receipt["qualified_reference_mask_available"] is False
    assert receipt["manual_weak_reference_mask_available"] is False
    assert receipt["processing_allowed"] is False
    assert receipt["candidate_metrics_available"] is False
    assert receipt["decision_outputs_available"] is False
    assert receipt["dashboard_story_available"] is False
    assert receipt["can_feed_decision_layer"] is False
    assert len(receipt["sentinel1_candidates"]) == 14
    assert len(receipt["candidate_product_ids"]) == 14
    assert {row["candidate_role"] for row in receipt["sentinel1_candidates"]} == {
        "pre-event COG candidate",
        "pre-event SAFE alternative",
        "post-event COG candidate",
        "post-event SAFE alternative",
        "fallback post-event COG candidate",
        "fallback post-event SAFE alternative",
    }
    assert {row["source_name"] for row in receipt["reference_candidates"]} == {
        "International Charter Activation 1004",
        "Sentinel Asia Southern Thailand 2025",
        "Academic or manual reference mask",
    }
    assert [item["code"] for item in receipt["blockers"]] == [
        item["code"] for item in BLOCKERS
    ]
    assert receipt["source_timestamp"] == "2025-12-05T23:03:07.854162Z"
    serialized = json.dumps(receipt)
    assert r"C:\\Users" not in serialized
    assert "/home/" not in serialized


def test_pinned_input_hashes_match_committed_snapshots() -> None:
    assert compute_sha256(CDSE) == PINNED_INPUT_SHA256[
        "outputs/cdse_hat_yai_2025_metadata.csv"
    ]
    assert compute_sha256(INGESTION) == PINNED_INPUT_SHA256[
        "outputs/real_data_ingestion_manifest.csv"
    ]


def test_substituted_cdse_snapshot_is_rejected(tmp_path: Path) -> None:
    substituted = tmp_path / "cdse.csv"
    text = CDSE.read_text(encoding="utf-8")
    substituted.write_text(text.replace("325e23d5", "425e23d5", 1), encoding="utf-8")

    with pytest.raises(HatYaiReadinessError, match="substituted input rejected"):
        build_hat_yai_readiness_receipt(
            substituted,
            INGESTION,
            generated_at=GENERATED_AT,
        )


@pytest.mark.parametrize(
    "field",
    [
        "official_warning",
        "processing_allowed",
        "candidate_metrics_available",
        "decision_outputs_available",
        "dashboard_story_available",
        "can_feed_decision_layer",
    ],
)
def test_unsupported_promotion_claims_are_rejected(field: str) -> None:
    receipt = _receipt()
    receipt[field] = True

    with pytest.raises(HatYaiReadinessError, match="Unsupported Hat Yai readiness claim"):
        validate_hat_yai_readiness_receipt(receipt)


def test_locked_metadata_pair_cannot_be_claimed_as_acquired_or_checksum_ready() -> None:
    for field in ("pair_assets_acquired", "pair_asset_checksums_recorded"):
        receipt = _receipt()
        receipt[field] = True
        with pytest.raises(HatYaiReadinessError, match="Unsupported Hat Yai readiness claim"):
            validate_hat_yai_readiness_receipt(receipt)


def test_selected_metadata_pair_substitution_is_rejected() -> None:
    receipt = _receipt()
    receipt["selected_metadata_pair"]["pre_event"]["product_id"] = (
        "967702e5-a008-4774-9400-e28dd1e624c8"
    )
    with pytest.raises(HatYaiReadinessError, match="incomplete or substituted"):
        validate_hat_yai_readiness_receipt(receipt)


def test_unselected_candidate_substitution_is_rejected() -> None:
    receipt = _receipt()
    receipt["sentinel1_candidates"][0]["candidate_role"] = (
        "fallback post-event SAFE alternative"
    )
    with pytest.raises(HatYaiReadinessError, match="public candidate set is substituted"):
        validate_hat_yai_readiness_receipt(receipt)


def test_reference_clearance_substitution_is_rejected() -> None:
    receipt = _receipt()
    receipt["reference_candidates"][0]["license_status"] = "confirmed"
    with pytest.raises(HatYaiReadinessError, match="reference candidate claims are substituted"):
        validate_hat_yai_readiness_receipt(receipt)


def test_malformed_and_tampered_receipts_are_rejected() -> None:
    missing = _receipt()
    del missing["reason_blocked"]
    with pytest.raises(HatYaiReadinessError, match="fields do not match"):
        validate_hat_yai_readiness_receipt(missing)

    tampered = _receipt()
    tampered["assumptions"] = [*tampered["assumptions"], "fabricated"]
    with pytest.raises(HatYaiReadinessError, match="self-hash mismatch"):
        validate_hat_yai_readiness_receipt(tampered)


def test_private_absolute_paths_are_rejected() -> None:
    receipt = _receipt()
    receipt["source_name"] = r"C:\Users\operator\private\mask.gpkg"

    with pytest.raises(HatYaiReadinessError, match="private absolute path"):
        validate_hat_yai_readiness_receipt(receipt)


def test_write_load_and_render_status_artifacts(tmp_path: Path) -> None:
    receipt = _receipt()
    json_path, markdown_path = write_hat_yai_readiness_outputs(
        receipt,
        json_output_path=tmp_path / "hat_yai_readiness.json",
        markdown_output_path=tmp_path / "hat_yai_readiness.md",
    )
    loaded = load_hat_yai_readiness_receipt(
        json_path,
        cdse_metadata_path=CDSE,
        ingestion_manifest_path=INGESTION,
    )
    assert loaded == receipt
    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown == render_hat_yai_readiness_markdown(receipt)
    assert "BLOCKED — candidate metadata only" in markdown
    assert "No Hat Yai flood accuracy metric has been calculated." in markdown
    assert "Pre/post metadata pair selection | LOCKED_METADATA_ONLY" in markdown
    assert "Candidate metrics available | NO" in markdown
    assert "Not an official warning" in markdown


def test_cli_generates_and_checks_without_network(tmp_path: Path) -> None:
    json_output = tmp_path / "hat_yai_readiness.json"
    markdown_output = tmp_path / "hat_yai_readiness.md"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "generate_hat_yai_readiness.py"),
        "--cdse-metadata",
        str(CDSE),
        "--ingestion-manifest",
        str(INGESTION),
        "--json-output",
        str(json_output),
        "--summary-output",
        str(markdown_output),
        "--generated-at",
        GENERATED_AT,
    ]
    generated = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr
    assert json_output.exists()
    assert markdown_output.exists()

    checked = subprocess.run(
        [*command[:-2], "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stderr
    assert "VALID: Hat Yai remains fail-closed" in checked.stdout


def test_source_substitution_is_detected_after_receipt_generation(tmp_path: Path) -> None:
    cdse_copy = tmp_path / "cdse.csv"
    ingestion_copy = tmp_path / "ingestion.csv"
    shutil.copyfile(CDSE, cdse_copy)
    shutil.copyfile(INGESTION, ingestion_copy)
    receipt = build_hat_yai_readiness_receipt(
        cdse_copy,
        ingestion_copy,
        generated_at=GENERATED_AT,
    )
    cdse_copy.write_text(cdse_copy.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(HatYaiReadinessError, match="source substitution detected"):
        validate_hat_yai_readiness_receipt(
            receipt,
            cdse_metadata_path=cdse_copy,
            ingestion_manifest_path=ingestion_copy,
        )
