from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from geoai_runner.proposal_evidence import validate_proposal_proof_receipt

RUNNER_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = RUNNER_ROOT / "evidence"
RECEIPT = EVIDENCE / "geoai-proof-receipt.json"
THUMBNAIL = EVIDENCE / "geoai-probability-thumbnail.png"


def test_committed_real_smoke_evidence_is_small_redacted_and_fail_closed() -> None:
    payload = validate_proposal_proof_receipt(RECEIPT)
    assert payload["execution_mode"] == "real_geoai_smoke"
    assert payload["actual_geoai_calls"] == [
        "geoai.utils.training.export_geotiff_tiles",
        "geoai.inference.predict_geotiff",
    ]
    assert payload["training_execution"] == "model_construction_only"
    assert payload["aggregation"]["status"] == "report_only"
    assert payload["aggregation"]["eligible_for_decision_layer"] is False
    assert payload["aggregation"]["eligible_for_fpps"] is False
    assert payload["claim_boundary"] == (
        "Synthetic integration proof; not evidence of real flood-detection accuracy."
    )
    assert RECEIPT.stat().st_size < 64_000
    assert THUMBNAIL.stat().st_size < 128_000
    assert THUMBNAIL.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert hashlib.sha256(THUMBNAIL.read_bytes()).hexdigest() == payload["thumbnail"][
        "sha256"
    ]
    serialized = RECEIPT.read_text(encoding="utf-8")
    assert re.search(
        r"(?:[A-Za-z]:[\\/]|\\\\|file://|/(?:Users|home|root|tmp|var|private)/)",
        serialized,
        flags=re.IGNORECASE,
    ) is None


def test_committed_proof_rejects_checksum_and_claim_substitution(tmp_path: Path) -> None:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    payload["can_feed_decision_layer"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        validate_proposal_proof_receipt(tampered)

    payload.pop("receipt_payload_sha256")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["receipt_payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="fail-closed"):
        validate_proposal_proof_receipt(tampered)


@pytest.mark.parametrize(
    ("field_path", "replacement"),
    [
        (("proof_scope",), "decision_ready"),
        (("execution_mode",), "mocked_unit"),
        (("training_execution",), "one_epoch_completed"),
        (("actual_geoai_calls",), []),
        (("aggregation", "status"), "passed"),
        (("aggregation", "eligible_for_decision_layer"), True),
        (("aggregation", "eligible_for_fpps"), True),
        (("claim_boundary",), "Validated real flood model."),
        (("probability", "class_index"), 0),
        (("probability", "band_name"), "water_probability"),
        (("validation_checks", "crs"), False),
    ],
)
def test_committed_proof_rejects_rehashed_safety_substitution(
    tmp_path: Path,
    field_path: tuple[str, ...],
    replacement: object,
) -> None:
    payload = json.loads(RECEIPT.read_text(encoding="utf-8"))
    payload.pop("receipt_payload_sha256")
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = replacement
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    payload["receipt_payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="fail-closed"):
        validate_proposal_proof_receipt(tampered)
