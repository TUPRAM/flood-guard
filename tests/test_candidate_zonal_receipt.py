"""The candidate lane must be traceable and structurally unable to over-claim (D-02)."""

from __future__ import annotations

import pandas as pd
import pytest

from floodguard.candidate_zonal_receipt import (
    CandidateReceiptError,
    build_candidate_zonal_receipt,
    score_candidate_areas,
    verify_candidate_zonal_receipt,
)

KEY = b"k" * 32
META = {
    "study_area_id": "mae_sai",
    "dataset_mode": "real_licensed_inputs",
    "source_timestamp": "2024-09-15T00:00:00Z",
    "generated_at": "2026-07-29T00:00:00Z",
}


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "subdistrict_id": "570901",
                "subdistrict_name": "Mae Sai",
                "confidence_class": "low",
                "flood_likelihood_0_100": 47.3,
                "exposure_0_100": 14.1,
                "access_gap_0_100": 86.37,
                "road_criticality_0_100": 37.04,
                "vulnerability_context_0_100": 0.37,
            },
            {
                "subdistrict_id": "570902",
                "subdistrict_name": "Pong Pha",
                "confidence_class": "low",
                "flood_likelihood_0_100": 30.9,
                "exposure_0_100": 82.9,
                "access_gap_0_100": 0.41,
                "road_criticality_0_100": 14.21,
                "vulnerability_context_0_100": 0.31,
            },
        ]
    )


def _receipt(**overrides):
    kwargs = dict(
        input_rows=_frame().to_dict(orient="records"),
        output_rows=_frame().to_dict(orient="records"),
        source_metadata=META,
        model_run_id="run-1",
        signing_key=KEY,
        key_id="candidate-key",
        generated_at="2026-07-29T12:00:00Z",
    )
    kwargs.update(overrides)
    return build_candidate_zonal_receipt(**kwargs)


# --------------------------------------------------------------------------- #
# The property the module exists for
# --------------------------------------------------------------------------- #


def test_receipt_can_never_claim_decision_authority() -> None:
    receipt = _receipt()
    assert receipt["can_feed_decision_layer"] is False
    assert receipt["official_warning"] is False
    assert receipt["evidence_tier"] == "candidate"
    assert receipt["aggregation_status"] == "report_only"


def test_requesting_decision_authority_is_refused() -> None:
    with pytest.raises(CandidateReceiptError, match="report-only by construction"):
        _receipt(source_metadata={**META, "can_feed_decision_layer": True})


def test_official_input_may_not_be_downgraded_into_this_lane() -> None:
    """Cleared evidence must not dodge the operational gate by coming here."""

    with pytest.raises(CandidateReceiptError, match="trusted_zonal_adapter"):
        _receipt(source_metadata={**META, "dataset_mode": "official_input"})


def test_a_tampered_receipt_fails_verification() -> None:
    receipt = _receipt()
    assert verify_candidate_zonal_receipt(receipt, signing_key=KEY) is True

    tampered = dict(receipt)
    tampered["area_count"] = 99
    assert verify_candidate_zonal_receipt(tampered, signing_key=KEY) is False


def test_flipping_the_tier_flag_is_rejected_outright() -> None:
    receipt = dict(_receipt())
    receipt["can_feed_decision_layer"] = True
    with pytest.raises(CandidateReceiptError, match="claims decision authority"):
        verify_candidate_zonal_receipt(receipt, signing_key=KEY)


def test_a_different_key_does_not_verify() -> None:
    assert verify_candidate_zonal_receipt(_receipt(), signing_key=b"x" * 32) is False


# --------------------------------------------------------------------------- #
# Binding and hygiene
# --------------------------------------------------------------------------- #


def test_receipt_binds_the_actual_table_contents() -> None:
    base = _receipt()
    changed = _frame()
    changed.loc[0, "flood_likelihood_0_100"] = 99.9
    other = _receipt(input_rows=changed.to_dict(orient="records"))
    assert base["input_table_sha256"] != other["input_table_sha256"]


def test_row_order_does_not_change_the_digest() -> None:
    forward = _frame().to_dict(orient="records")
    assert _receipt(input_rows=forward)["input_table_sha256"] == (
        _receipt(input_rows=list(reversed(forward)))["input_table_sha256"]
    )


def test_dropping_a_row_across_scoring_is_refused() -> None:
    with pytest.raises(CandidateReceiptError, match="one row in, one row out"):
        _receipt(output_rows=_frame().to_dict(orient="records")[:1])


def test_a_weak_signing_key_is_refused() -> None:
    with pytest.raises(CandidateReceiptError, match="at least 32 bytes"):
        _receipt(signing_key=b"short")


def test_generated_at_must_be_supplied_by_the_caller() -> None:
    """No hidden wall-clock state; receipts stay reproducible."""

    with pytest.raises(CandidateReceiptError, match="generated_at"):
        _receipt(generated_at="  ")


# --------------------------------------------------------------------------- #
# The bridge itself
# --------------------------------------------------------------------------- #


def test_scoring_through_the_receipt_is_behaviour_preserving() -> None:
    """The receipt must add traceability without moving a single FPPS value."""

    from floodguard.scoring import score_subdistricts

    frame = _frame()
    direct = score_subdistricts(frame.copy())
    routed, receipt = score_candidate_areas(
        frame.copy(),
        source_metadata=META,
        model_run_id="run-1",
        signing_key=KEY,
        key_id="candidate-key",
        generated_at="2026-07-29T12:00:00Z",
    )

    pd.testing.assert_frame_equal(direct, routed)
    assert verify_candidate_zonal_receipt(receipt, signing_key=KEY) is True
    assert receipt["area_count"] == 2
