"""Report-only bridge from candidate model evidence to the decision table (D-02).

The gap this fills
------------------
`docs/geoai-system-design-v1.md` states that `trusted_zonal_adapter` is "the
only model product to reporting-area bridge", and the audit accordingly
recommended routing the GeoAI real-pipeline through it. That is not
implementable. `create_signed_zonal_receipt` refuses anything that is not
already cleared:

    if metadata.dataset_mode != "official_input":            raise
    if not metadata.can_feed_decision_layer:                 raise

and the runner's own contract layer enforces the mirror image
(`contract.py`: "Candidate GeoAI runs cannot feed the decision layer").
So the trusted adapter is the *operational* lane, and there was no bridge at
all for the *candidate* lane. `realpipeline/run_real.py` consequently imported
`floodguard.scoring.score_subdistricts` directly and produced FPPS values and
A-E action classes with no receipt, no registry entry, and -- most importantly
-- no marker distinguishing them from governed figures once published.

What this module is
-------------------
The candidate lane's equivalent: same signing discipline as the trusted
adapter, opposite tier. It binds the exact bytes that went in and came out,
and it is *structurally incapable* of claiming decision authority --
``can_feed_decision_layer`` is not a parameter, it is a constant.

This does not make candidate evidence trustworthy. It makes it **traceable**,
and it makes the tier machine-readable instead of editorial.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

__all__ = [
    "CandidateReceiptError",
    "EVIDENCE_TIER",
    "build_candidate_zonal_receipt",
    "verify_candidate_zonal_receipt",
    "score_candidate_areas",
]

SCHEMA_VERSION = "candidate-zonal-receipt/1.0"

#: Constants, not parameters. A candidate receipt that could assert decision
#: authority would defeat the tier separation this module exists to enforce.
EVIDENCE_TIER = "candidate"
CAN_FEED_DECISION_LAYER = False
OFFICIAL_WARNING = False

REQUIRED_METADATA = ("study_area_id", "dataset_mode", "source_timestamp", "generated_at")

#: Modes that are report-only by definition. `official_input` is deliberately
#: absent: cleared evidence belongs in the trusted adapter, not here.
CANDIDATE_DATASET_MODES = frozenset({"candidate", "real_licensed_inputs", "fixture_demo"})


class CandidateReceiptError(ValueError):
    """Raised when a candidate receipt is unsafe, malformed, or over-claiming."""


def _canonical_json_bytes(value: object, field: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CandidateReceiptError(
            f"{field} must contain only canonical JSON values."
        ) from exc


def _signing_key(value: object) -> bytes:
    if not isinstance(value, bytes) or len(value) < 32:
        raise CandidateReceiptError(
            "signing_key must be external bytes containing at least 32 bytes."
        )
    return value


def _signature_value(payload: Mapping[str, object], signing_key: bytes) -> str:
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    return hmac.new(
        signing_key, _canonical_json_bytes(unsigned, "candidate receipt"), hashlib.sha256
    ).hexdigest()


def _validated_metadata(source_metadata: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(source_metadata, Mapping):
        raise CandidateReceiptError("source_metadata must be a mapping.")
    missing = [key for key in REQUIRED_METADATA if not str(source_metadata.get(key, "")).strip()]
    if missing:
        raise CandidateReceiptError(f"source_metadata is missing: {sorted(missing)}")

    mode = str(source_metadata["dataset_mode"])
    if mode == "official_input":
        raise CandidateReceiptError(
            "official_input belongs in trusted_zonal_adapter, not the candidate "
            "lane. Cleared evidence must not be downgraded to a report-only "
            "receipt to avoid the operational gate."
        )
    if mode not in CANDIDATE_DATASET_MODES:
        raise CandidateReceiptError(
            f"dataset_mode {mode!r} is not a recognised candidate mode; "
            f"expected one of {sorted(CANDIDATE_DATASET_MODES)}."
        )

    if source_metadata.get("can_feed_decision_layer") not in (None, False):
        raise CandidateReceiptError(
            "can_feed_decision_layer cannot be requested here; the candidate "
            "lane is report-only by construction."
        )
    return {key: str(source_metadata[key]) for key in REQUIRED_METADATA}


def _table_digest(rows: object, field: str) -> tuple[str, int]:
    """Content hash of an area table, order-independent by stable area id."""

    if not isinstance(rows, list) or not rows:
        raise CandidateReceiptError(f"{field} must be a non-empty list of row mappings.")
    normalised = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise CandidateReceiptError(f"{field} rows must be mappings.")
        area_id = str(row.get("subdistrict_id") or row.get("area_id") or "").strip()
        if not area_id:
            raise CandidateReceiptError(f"{field} rows must carry a stable area id.")
        normalised.append((area_id, {str(k): row[k] for k in sorted(row)}))
    normalised.sort(key=lambda item: item[0])
    payload = [entry for _, entry in normalised]
    return hashlib.sha256(_canonical_json_bytes(payload, field)).hexdigest(), len(payload)


def build_candidate_zonal_receipt(
    *,
    input_rows: list[Mapping[str, object]],
    output_rows: list[Mapping[str, object]],
    source_metadata: Mapping[str, object],
    model_run_id: str,
    signing_key: bytes,
    key_id: str,
    generated_at: str,
) -> dict[str, Any]:
    """Bind a candidate model->decision-table transition into a signed receipt.

    ``generated_at`` is caller-supplied so receipt generation is reproducible
    and carries no hidden wall-clock state, matching the trusted adapter.
    """

    secret = _signing_key(signing_key)
    if not str(key_id).strip():
        raise CandidateReceiptError("key_id must be a non-empty string.")
    if not str(model_run_id).strip():
        raise CandidateReceiptError("model_run_id must be a non-empty string.")
    if not str(generated_at).strip():
        raise CandidateReceiptError("generated_at must be a non-empty RFC 3339 timestamp.")

    metadata = _validated_metadata(source_metadata)
    input_sha, input_count = _table_digest(list(input_rows), "input_rows")
    output_sha, output_count = _table_digest(list(output_rows), "output_rows")
    if input_count != output_count:
        raise CandidateReceiptError(
            f"row count changed across scoring ({input_count} -> {output_count}); "
            "the bridge must be one row in, one row out."
        )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "evidence_tier": EVIDENCE_TIER,
        "can_feed_decision_layer": CAN_FEED_DECISION_LAYER,
        "official_warning": OFFICIAL_WARNING,
        "aggregation_status": "report_only",
        "model_run_id": str(model_run_id),
        "study_area_id": metadata["study_area_id"],
        "dataset_mode": metadata["dataset_mode"],
        "source_timestamp": metadata["source_timestamp"],
        "model_generated_at": metadata["generated_at"],
        "generated_at": str(generated_at).strip(),
        "area_count": output_count,
        "input_table_sha256": input_sha,
        "output_table_sha256": output_sha,
        "signature": {"algorithm": "HMAC-SHA256", "key_id": str(key_id)},
    }
    payload["signature"]["value"] = _signature_value(payload, secret)
    return payload


def verify_candidate_zonal_receipt(
    receipt: Mapping[str, object], *, signing_key: bytes
) -> bool:
    """Return True when the receipt is well-formed, report-only, and unmodified."""

    secret = _signing_key(signing_key)
    if not isinstance(receipt, Mapping):
        raise CandidateReceiptError("receipt must be a mapping.")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise CandidateReceiptError("unsupported candidate receipt schema_version.")
    if receipt.get("can_feed_decision_layer") is not False:
        raise CandidateReceiptError(
            "candidate receipt claims decision authority; refusing to verify."
        )
    if receipt.get("evidence_tier") != EVIDENCE_TIER:
        raise CandidateReceiptError("candidate receipt evidence_tier was altered.")

    signature = receipt.get("signature")
    if not isinstance(signature, Mapping) or not isinstance(signature.get("value"), str):
        raise CandidateReceiptError("candidate receipt signature is malformed.")
    expected = _signature_value(receipt, secret)
    return hmac.compare_digest(expected, str(signature["value"]))


def score_candidate_areas(
    frame: Any,
    *,
    source_metadata: Mapping[str, object],
    model_run_id: str,
    signing_key: bytes,
    key_id: str,
    generated_at: str,
    weights: Mapping[str, float] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """The candidate lane's only route to FPPS.

    Returns ``(scored_frame, receipt)``. Scoring itself is unchanged -- this
    calls the same :func:`floodguard.scoring.score_subdistricts` -- so FPPS
    values are byte-identical to the direct call. What changes is that the
    transition is now bound to a signed, report-only receipt instead of being
    invisible.
    """

    from floodguard.scoring import score_subdistricts

    scored = score_subdistricts(frame, weights)
    receipt = build_candidate_zonal_receipt(
        input_rows=frame.to_dict(orient="records"),
        output_rows=scored.to_dict(orient="records"),
        source_metadata=source_metadata,
        model_run_id=model_run_id,
        signing_key=signing_key,
        key_id=key_id,
        generated_at=generated_at,
    )
    return scored, receipt
