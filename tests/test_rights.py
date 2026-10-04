"""The rights registry (plan row G6): no use and no public write without a confirmed rights record.

The tests read the two rights records committed in the repository and invented copies of them. Nothing
here opens a flood layer.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from floodguard import rights, rights_basis
from floodguard.rights import (
    LOCAL_LEVEL,
    PITCH_LEVEL,
    PRODUCT_4009,
    PUBLIC_LEVEL,
    REGISTERED_RECORDS,
    SENTINEL2_AUTOMATED_TRACK,
    RegisteredRecord,
    RightsRefusedError,
    RightsRegistry,
    minimum_level,
)

ROOT = Path(__file__).resolve().parents[1]
ACCUMULATED = "CHIANGRAI_20240801_20241012_AccumulatedFlood"
LAYER_22_OCT = "CHIANGRAI_20241022_FloodExtent"
ANALYSIS_EXTENT = "CHIANGRAI_20240801_20241022_AnalysisExtent"


def committed_record() -> dict:
    return json.loads((ROOT / rights_basis.RIGHTS_BASIS_4009_PATH).read_text(encoding="utf-8"))


def write_record(root: Path, record: dict, relative: str = rights_basis.RIGHTS_BASIS_4009_PATH.as_posix()) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def pending(record: dict) -> dict:
    """The record as it was before the owners confirmed it (test-only; never written into the repository)."""

    changed = copy.deepcopy(record)
    changed["owner_confirmation"].update(status="pending", confirmed_by=[], confirmed_on=None)
    changed.update(record_status="draft_pending_owner_confirmation", signed_by_human=False, human_rights_clearance=False)
    return changed


def test_the_registry_is_a_list_of_the_records_that_exist() -> None:
    assert [entry.input_id for entry in REGISTERED_RECORDS] == [PRODUCT_4009, SENTINEL2_AUTOMATED_TRACK]
    for entry in REGISTERED_RECORDS:
        assert (ROOT / entry.record_path).is_file(), entry.record_path
    assert REGISTERED_RECORDS[0].record_path == rights_basis.RIGHTS_BASIS_4009_PATH.as_posix()
    assert RightsRegistry(ROOT).input_ids() == tuple(sorted([PRODUCT_4009, SENTINEL2_AUTOMATED_TRACK]))


def test_the_confirmed_4009_record_allows_use_and_says_under_what_terms() -> None:
    grant = RightsRegistry(ROOT).require_use(PRODUCT_4009, layer=ACCUMULATED)
    record_path = ROOT / rights_basis.RIGHTS_BASIS_4009_PATH
    assert grant.record_id == "rights_basis_4009_v1"
    assert grant.record_sha256 == hashlib.sha256(record_path.read_bytes()).hexdigest()
    assert grant.licence["name"] == "CC BY-SA 4.0" and grant.licence["url"].startswith("https://creativecommons.org/")
    assert grant.attribution == "UNOSAT and GISTDA, FL20240912THA, UNOSAT product 4009"
    assert grant.confirmed_by == ("Putu", "Rachmania") and grant.confirmed_on == "2026-10-02"
    assert grant.share_alike and "CC BY-SA 4.0" in grant.share_alike
    # The record names this layer as its layer in scope: it may be published, as a season envelope only.
    assert grant.rights_level == PUBLIC_LEVEL and "season envelope only" in grant.rights_level_basis
    as_json = grant.as_record()
    assert json.loads(json.dumps(as_json)) == as_json
    assert as_json["record_status"] == "confirmed" and as_json["not_legal_advice"] is True


@pytest.mark.parametrize("layer", [LAYER_22_OCT, ANALYSIS_EXTENT, None])
def test_a_layer_the_record_does_not_name_is_local_and_never_written_in_public(layer: str | None) -> None:
    """The record names the accumulated layer only, and R6 allows publication as a season envelope only."""

    registry = RightsRegistry(ROOT)
    grant = registry.require_use(PRODUCT_4009, layer=layer)
    assert grant.rights_level == LOCAL_LEVEL
    assert ACCUMULATED in grant.rights_level_basis and "until the owners extend the record" in grant.rights_level_basis
    with pytest.raises(RightsRefusedError, match="apps/web/public"):
        registry.require_public_write(PRODUCT_4009, layer=layer)


def test_a_public_write_of_the_layer_in_scope_is_allowed_while_the_record_is_confirmed() -> None:
    grant = RightsRegistry(ROOT).require_public_write(PRODUCT_4009, layer=ACCUMULATED)
    assert grant.rights_level == PUBLIC_LEVEL


def test_an_unconfirmed_record_refuses_every_use_and_every_public_write(tmp_path: Path) -> None:
    """Plan row G6: a public write without a signed record is rejected. So is a use."""

    write_record(tmp_path, pending(committed_record()))
    registry = RightsRegistry(tmp_path)
    for layer in (ACCUMULATED, LAYER_22_OCT, None):
        with pytest.raises(RightsRefusedError, match="not confirmed by the owners"):
            registry.require_use(PRODUCT_4009, layer=layer)
        with pytest.raises(RightsRefusedError, match="not confirmed by the owners"):
            registry.require_public_write(PRODUCT_4009, layer=layer)


def test_a_confirmation_that_lacks_a_signer_is_refused(tmp_path: Path) -> None:
    record = committed_record()
    record["owner_confirmation"]["confirmed_by"] = ["Putu"]
    write_record(tmp_path, record)
    with pytest.raises(RightsRefusedError, match="Rachmania"):
        RightsRegistry(tmp_path).require_use(PRODUCT_4009, layer=ACCUMULATED)


def test_a_missing_or_broken_record_is_refused(tmp_path: Path) -> None:
    registry = RightsRegistry(tmp_path)
    with pytest.raises(RightsRefusedError, match="not in the repository"):
        registry.require_use(PRODUCT_4009, layer=ACCUMULATED)
    path = write_record(tmp_path, committed_record())
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RightsRefusedError, match="not valid JSON"):
        registry.require_use(PRODUCT_4009, layer=ACCUMULATED)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(RightsRefusedError, match="JSON object"):
        registry.require_use(PRODUCT_4009, layer=ACCUMULATED)
    record = committed_record()
    del record["licence"]
    write_record(tmp_path, record)
    with pytest.raises(RightsRefusedError, match="licence"):
        registry.require_use(PRODUCT_4009, layer=ACCUMULATED)


def test_an_input_with_no_record_may_not_be_used() -> None:
    registry = RightsRegistry(ROOT)
    for call in (registry.require_use, registry.require_public_write):
        with pytest.raises(RightsRefusedError, match="no rights record is registered"):
            call("copernicus_sentinel1_own_radar_candidates")


def test_the_unsigned_sentinel2_legal_notice_record_is_refused() -> None:
    """The automated-track record says signed_by_human false: the registry does not read it as a clearance."""

    record = json.loads((ROOT / REGISTERED_RECORDS[1].record_path).read_text(encoding="utf-8"))
    assert record["signed_by_human"] is False and record["human_rights_clearance"] is False
    with pytest.raises(RightsRefusedError, match="not signed by a human"):
        RightsRegistry(ROOT).require_use(SENTINEL2_AUTOMATED_TRACK)


def signed_generic_record() -> dict:
    return {
        "schema": "floodguard.test_rights_basis.v1",
        "record_id": "invented_record_v1",
        "source": "An invented source",
        "legal_notice_title": "An invented legal notice",
        "legal_notice_url": "https://example.org/notice",
        "required_attribution_text": "Contains invented data",
        "signed_by_human": True,
        "human_rights_clearance": True,
        "official_warning": False,
        "operational_status": "non_operational",
        "can_feed_decision_layer": False,
    }


def invented_registry(root: Path, record: dict) -> RightsRegistry:
    write_record(root, record, "docs/invented_rights.json")
    return RightsRegistry(root, (RegisteredRecord("invented_input", "docs/invented_rights.json", "an invented input"),))


def test_a_signed_record_of_another_schema_allows_local_use_only(tmp_path: Path) -> None:
    registry = invented_registry(tmp_path, signed_generic_record())
    grant = registry.require_use("invented_input")
    assert grant.rights_level == LOCAL_LEVEL and grant.attribution == "Contains invented data"
    assert grant.licence == {"name": "An invented legal notice", "url": "https://example.org/notice"}
    assert grant.record_id == "invented_record_v1" and grant.share_alike is None
    with pytest.raises(RightsRefusedError, match="rights level 'local'"):
        registry.require_public_write("invented_input")
    with pytest.raises(RightsRefusedError, match="names no source archive"):
        registry.verify_source(grant, tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"signed_by_human": False}, "not signed by a human"),
        ({"human_rights_clearance": False}, "not signed by a human"),
        ({"required_attribution_text": " "}, "required_attribution_text"),
        ({"official_warning": True}, "not an official warning"),
        ({"can_feed_decision_layer": True}, "not an official warning"),
        ({"legal_notice_title": ""}, "no licence and no legal notice"),
    ],
)
def test_a_record_of_another_schema_is_refused_when_it_lacks_what_a_use_needs(tmp_path: Path, change: dict, message: str) -> None:
    registry = invented_registry(tmp_path, {**signed_generic_record(), **change})
    with pytest.raises(RightsRefusedError, match=message):
        registry.require_use("invented_input")


def test_a_record_of_another_schema_may_name_its_licence(tmp_path: Path) -> None:
    record = {**signed_generic_record(), "licence": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"},
              "share_alike": "none", "owner_confirmation": {"confirmed_by": ["Putu"], "confirmed_on": "2026-10-04"}}
    grant = invented_registry(tmp_path, record).require_use("invented_input", layer="one")
    assert grant.licence["name"] == "CC BY 4.0" and grant.layer == "one"
    assert grant.confirmed_by == ("Putu",) and grant.confirmed_on == "2026-10-04" and grant.share_alike == "none"


def test_the_level_of_an_output_is_the_minimum_across_its_lineage() -> None:
    """Protocol v1a, guardrail GR6."""

    assert rights.RIGHTS_LEVELS == (LOCAL_LEVEL, PITCH_LEVEL, PUBLIC_LEVEL)
    assert minimum_level([PUBLIC_LEVEL]) == PUBLIC_LEVEL
    assert minimum_level([PUBLIC_LEVEL, PITCH_LEVEL, PUBLIC_LEVEL]) == PITCH_LEVEL
    assert minimum_level([PUBLIC_LEVEL, LOCAL_LEVEL, PITCH_LEVEL]) == LOCAL_LEVEL
    with pytest.raises(RightsRefusedError, match="no lineage"):
        minimum_level([])
    with pytest.raises(RightsRefusedError, match="unknown rights level"):
        minimum_level([PUBLIC_LEVEL, "open"])


def test_the_source_file_must_be_the_one_the_record_names(tmp_path: Path) -> None:
    archive = b"an invented archive"
    record = committed_record()
    record["archive"].update(sha256=hashlib.sha256(archive).hexdigest(), bytes=len(archive))
    record_path = write_record(tmp_path, record)
    registry = RightsRegistry(tmp_path)
    grant = registry.require_use(PRODUCT_4009, layer=ACCUMULATED)
    external = tmp_path / "external"
    with pytest.raises(RightsRefusedError, match="archive not found"):
        registry.verify_source(grant, external)
    target = external / record["archive"]["relative_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(archive)
    assert registry.verify_source(grant, external) == target
    target.write_bytes(b"an invented archivE")
    with pytest.raises(RightsRefusedError, match="SHA-256 differs"):
        registry.verify_source(grant, external)
    target.write_bytes(archive + b"!")
    with pytest.raises(RightsRefusedError, match="size differs"):
        registry.verify_source(grant, external)
    # A record edited after the grant was read does not vouch for a file.
    target.write_bytes(archive)
    record_path.write_text(record_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(RightsRefusedError, match="changed after the grant"):
        registry.verify_source(grant, external)


def test_an_input_is_registered_once() -> None:
    entry = RegisteredRecord("twice", "docs/a.json", "an invented input")
    with pytest.raises(RightsRefusedError, match="registered twice"):
        RightsRegistry(ROOT, (entry, entry))


def test_the_registry_does_not_edit_the_evidence_catalog_policy() -> None:
    """Protocol v1a, guardrail GR6: evidence_catalog._POLICY is not edited. The registry does not import it."""

    source = (ROOT / "src" / "floodguard" / "rights.py").read_text(encoding="utf-8")
    assert "import evidence_catalog" not in source and "from floodguard.evidence_catalog" not in source
