"""Fail-closed tests for the pinned Mae Sai browser bundle generator."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps" / "web" / "scripts" / "build-mae-sai-offline-bundle.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mae_sai_offline_builder", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder() -> ModuleType:
    return _module()


@pytest.fixture(scope="module")
def pinned_inputs(builder: ModuleType) -> tuple[dict, dict]:
    manifest = builder._load(builder.SOURCE_MANIFEST_PATH)
    sources = {
        layer_id: builder._load(path)
        for layer_id, path in builder.INPUTS.items()
    }
    return manifest, sources


def test_pinned_generator_inputs_validate_before_build(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
) -> None:
    manifest, sources = pinned_inputs
    builder._validate_pinned_inputs(manifest, sources)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("fpps_0_100", "not-a-number", "finite number"),
        ("source_name", None, "missing required properties"),
    ],
)
def test_pinned_generator_rejects_corrupt_required_values(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
    field: str,
    replacement: object,
    message: str,
) -> None:
    manifest, sources = pinned_inputs
    corrupt_sources = deepcopy(sources)
    properties = corrupt_sources["priority_areas"]["features"][0]["properties"]
    if replacement is None:
        properties.pop(field)
    else:
        properties[field] = replacement
    with pytest.raises(ValueError, match=message):
        builder._validate_pinned_inputs(manifest, corrupt_sources)


def test_pinned_generator_rejects_geometry_substitution(
    builder: ModuleType,
    pinned_inputs: tuple[dict, dict],
) -> None:
    manifest, sources = pinned_inputs
    corrupt_sources = deepcopy(sources)
    corrupt_sources["priority_areas"]["features"][0]["geometry"] = {
        "type": "Point",
        "coordinates": [99.9, 20.4],
    }
    with pytest.raises(ValueError, match="geometry type changed"):
        builder._validate_pinned_inputs(manifest, corrupt_sources)


def test_validation_failure_occurs_before_any_output_write(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes: list[str] = []
    monkeypatch.setattr(builder, "_load", lambda _path: {})
    monkeypatch.setattr(
        builder,
        "_validate_pinned_inputs",
        lambda _manifest, _sources: (_ for _ in ()).throw(ValueError("blocked")),
    )
    monkeypatch.setattr(
        builder,
        "_write",
        lambda name, _value: writes.append(name),
    )
    with pytest.raises(ValueError, match="blocked"):
        builder.main()
    assert writes == []


def test_qualified_evidence_foundation_is_canonical_and_fail_closed(
    builder: ModuleType,
) -> None:
    foundation = builder._qualified_evidence_foundation()
    canonical_sha256 = foundation.pop("canonical_sha256")

    assert canonical_sha256 == builder._canonical_payload_sha256(foundation)
    assert foundation["authoritative_receipt"] is False
    assert foundation["source_timestamp"] == "2026-07-23T12:24:48Z"
    assert foundation["generated_at"] == "2026-07-23T12:24:48Z"
    assert foundation["reference_candidate_binding"] == {
        "manifest_schema": "floodguard.reference_candidate_manifest.v1",
        "product_id": "AIT-VAP001-TH",
        "provider": "Asian Institute of Technology via Sentinel Asia",
        "observation_start_utc": "2024-09-14T00:00:00Z",
        "observation_end_utc": "2024-09-14T23:59:59Z",
        "manifest_canonical_sha256": (
            "be2ce989e21f4ad3d79fe8f643ab13e7a3fc19eac1a8069bb8e83ede90878079"
        ),
        "manifest_file_sha256": builder._sha256(
            builder.AIT_REFERENCE_CANDIDATE_PATH
        ),
        "source_archive_sha256": (
            "762153fe3fd22350070bb788c22f2d4e083866b5d20b1294e8ca27b97367d5d5"
        ),
        "qualification_status": (
            "blocked_external_permission_and_scientific_review"
        ),
        "processing_allowed": False,
    }
    assert [
        (stage["stage_id"], stage["state"])
        for stage in foundation["stages"]
    ] == [
        ("engineering_foundation", "ready"),
        ("qualified_thai_reference", "blocked"),
        ("reviewer_calibration", "blocked"),
        ("blind_review_adjudication", "blocked"),
        ("frozen_label_release", "absent"),
    ]
    assert foundation["permissions"]["source_processing_allowed"] is True
    assert foundation["permissions"]["experiment_processing_allowed"] is False
    assert foundation["permissions"]["qualified_reference_use_allowed"] is False
    assert foundation["permissions"]["training_allowed"] is False
    assert foundation["permissions"]["evaluation_allowed"] is False
    assert foundation["permissions"]["decision_layer_allowed"] is False
    assert foundation["permissions"]["operational_use_allowed"] is False
    assert all(value is False for value in foundation["safety"].values())


def test_qualified_evidence_foundation_rejects_tampered_candidate(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = builder._load(builder.AIT_REFERENCE_CANDIDATE_PATH)
    candidate["qualification_status"] = "qualified"
    monkeypatch.setattr(builder, "_load", lambda _path: candidate)

    with pytest.raises(ValueError, match="canonical SHA-256 is invalid"):
        builder._qualified_evidence_foundation()


def test_qualified_evidence_foundation_rejects_rehashed_semantic_mutation(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = builder._load(builder.AIT_REFERENCE_CANDIDATE_PATH)
    candidate["provider"]["terms_evidence"][
        "no_modification_clause_present"
    ] = False
    unsigned = dict(candidate)
    unsigned.pop("canonical_sha256")
    candidate["canonical_sha256"] = builder._canonical_payload_sha256(unsigned)
    monkeypatch.setattr(builder, "_load", lambda _path: candidate)

    with pytest.raises(ValueError, match="semantic validation failed"):
        builder._qualified_evidence_foundation()


def test_qualified_evidence_foundation_rejects_rehashed_member_substitution(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = builder._load(builder.AIT_REFERENCE_CANDIDATE_PATH)
    candidate["asset_inventory"]["members"][5]["sha256"] = "0" * 64
    unsigned = dict(candidate)
    unsigned.pop("canonical_sha256")
    candidate["canonical_sha256"] = builder._canonical_payload_sha256(unsigned)
    monkeypatch.setattr(builder, "_load", lambda _path: candidate)

    with pytest.raises(ValueError, match="semantic validation failed"):
        builder._qualified_evidence_foundation()


def test_qualified_evidence_foundation_requires_exact_reviewed_candidate(
    builder: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = builder._load(builder.AIT_REFERENCE_CANDIDATE_PATH)
    replacement = "2026-07-24T12:24:48Z"
    candidate["inspected_at_utc"] = replacement
    candidate["temporal_identity"]["accessed_at_utc"] = replacement
    candidate["provider"]["terms_evidence"]["accessed_at_utc"] = replacement
    unsigned = dict(candidate)
    unsigned.pop("canonical_sha256")
    candidate["canonical_sha256"] = builder._canonical_payload_sha256(unsigned)
    monkeypatch.setattr(builder, "_load", lambda _path: candidate)

    with pytest.raises(ValueError, match="reviewed canonical SHA-256 changed"):
        builder._qualified_evidence_foundation()


def test_public_projection_omits_qualified_evidence_foundation(
    builder: ModuleType,
) -> None:
    foundation = builder._qualified_evidence_foundation()
    public = builder._public_bundle(
        {
            "evidence_context": {},
            "evidence_record": {},
            "qualified_evidence_foundation": foundation,
            "public_areas": [],
            "status": {},
            "layers": [],
            "hotlines": [],
        }
    )

    assert "qualified_evidence_foundation" not in public
    assert foundation["foundation_id"] not in str(public)
