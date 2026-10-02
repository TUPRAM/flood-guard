"""Evidence contract of the Mae Sai replay manifest (``timeline.json``), and the helpers that enforce it.

The replay is a narrative surface (decision D7): a model reconstruction beside dated observations and reported
facts. These tests pin what the committed manifest must say about itself: no score and no action class, not an
official warning, non-operational, a lane and a source timestamp for every part, a licence per input, the input
hashes, and a plain account of which external figures were used or known while the model was tuned.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re

import pytest

from floodguard.replay_manifest import (
    BLOCK_FIELDS,
    ENVELOPE_KEYS,
    LANES,
    REQUIRED_KEYS,
    SCENARIO_TIER,
    ReplayManifestError,
    evidence_problems,
    newest_timestamp,
    normalise_timestamp,
    schema_problems,
    score_or_class_keys,
    uncovered_blocks,
)
from floodguard.rights_basis import load_rights_basis, owner_confirmed, unconfirmed_product_citations

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
SCHEMA_PATH = ROOT / "packages" / "contracts" / "schemas" / "case-replay-timeline.schema.json"
RIGHTS_RECORD = ROOT / "docs" / "proposal_execution" / "rights_basis_4009_v1.json"
LOCAL_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|/Users/|\\Users\\|/home/|%20")


def manifest_path() -> Path:
    """The manifest the page serves, from the one constant in ``flood-timeline.ts``."""
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return WEB / "public" / href.lstrip("/")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(manifest_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def minimal_manifest() -> dict:
    """The smallest manifest that keeps the evidence contract: one scenario block and one observed list."""
    return {
        "study_id": "fixture-study", "revision": "r1", "schema_version": 2, "generated_by": "tests",
        "generated_at": "2026-10-01T16:10:00+07:00", "generated_at_basis": "declared", "git_commit": None, "git_commit_reason": "self_reference",
        "data_version": "fixture-study-r1", "dataset_mode": "historical_reconstruction", "data_mode": "historical_reconstruction",
        "operational_status": "non_operational", "official_warning": False, "real_time": False, "can_feed_decision_layer": False,
        "accepted_fpps": None, "accepted_action_class": None, "protocol_sha256": None, "protocol_sha256_reason": "not_a_protocol_case",
        "permitted_use": "planning exercises", "reason_blocked": "not a protocol case", "confidence": "low", "confidence_class": "low",
        "confidence_reason": "illustrative", "confidence_basis": ["illustrative stages"], "source_name": "fixture", "event_time": {},
        "source_timestamp": "2024-09-05T03:58:19Z/2024-09-19T17:00:00Z", "source_timestamp_note": "span", "timezone": "Asia/Bangkok",
        "lanes": {"SCN": LANES["SCN"], "OBS": LANES["OBS"]},
        "evidence_blocks": [
            {"id": "water", "covers": ["hand", "vectors.roads"], "lane": "SCN", "evidence_tier": SCENARIO_TIER,
             "temporal_relation": "event_window_reconstruction", "source_timestamp": "DEM 2011-2015"},
            {"id": "image", "covers": ["layers[s2]"], "lane": "OBS", "evidence_tier": "Observed image",
             "temporal_relation": "pre_event", "source_timestamp": "2024-09-05T03:58:19Z"},
        ],
        "exploratory_knowledge": {}, "publication_eligibility": {},
        "input_sha256": [{"root": "external", "path": "dem/tile.tif", "bytes": 4, "sha256": "a" * 64}],
        "sources": [], "assumptions": ["illustrative"], "limitations": ["not field-checked"],
        "hand": {"href": "/studies/x/r1/hand.png"}, "vectors": {"roads": {}}, "layers": [{"id": "s2"}],
    }


# --- Helpers -----------------------------------------------------------------------------------------------


def test_timestamps_are_normalised_and_need_an_offset() -> None:
    assert normalise_timestamp("2026-10-01T16:10:00+07:00") == "2026-10-01T16:10:00+07:00"
    assert normalise_timestamp(" 2026-10-01T09:10:00.123456Z ") == "2026-10-01T09:10:00Z"
    assert normalise_timestamp("2026-10-01T09:10:00+00:00") == "2026-10-01T09:10:00Z"
    assert normalise_timestamp("2024-09-18T13:30+07:00") == "2024-09-18T13:30:00+07:00"
    assert normalise_timestamp("2026-09-27") == "2026-09-27T00:00:00Z"  # A bare date is midnight UTC.
    for bad in ("2026-10-01T16:10:00", "1 Oct 2026", "", "2026-13-01"):
        with pytest.raises(ReplayManifestError):
            normalise_timestamp(bad)


def test_newest_timestamp_compares_instants_not_text() -> None:
    assert newest_timestamp(["2024-09-15T23:16:01Z", "2026-07-09", "2026-09-27", "2024-09-20T00:00:00+07:00"]) == "2026-09-27T00:00:00Z"
    # 06:30+07:00 is 23:30 UTC the day before, so the 00:10 UTC stamp is the later instant although its text sorts first.
    assert newest_timestamp(["2024-09-16T06:30:00+07:00", "2024-09-16T00:10:00Z"]) == "2024-09-16T00:10:00Z"
    with pytest.raises(ReplayManifestError, match="at least one"):
        newest_timestamp([])


def test_minimal_manifest_keeps_the_contract_and_each_break_is_named() -> None:
    assert evidence_problems(minimal_manifest()) == []

    def problems(**changes) -> list[str]:
        document = minimal_manifest()
        document.update(changes)
        return evidence_problems(document)

    assert problems(accepted_fpps=81.2) == ["accepted_fpps must be null: the replay computes no score and no action class"]
    assert problems(accepted_action_class="E") == ["accepted_action_class must be null: the replay computes no score and no action class"]
    assert problems(protocol_sha256="a" * 64) == ["protocol_sha256 must be null: the replay is not a protocol case"]
    assert problems(official_warning=True) == ["official_warning must be false"]
    assert problems(real_time=True) == ["real_time must be false"]
    assert problems(can_feed_decision_layer=True) == ["can_feed_decision_layer must be false"]
    assert problems(operational_status="planning_only") == ["operational_status must be non_operational"]
    assert problems(confidence_class="medium") == ["confidence_class must mirror confidence"]
    assert problems(data_mode="fixture_demo") == ["data_mode must mirror dataset_mode"]
    assert problems(input_sha256=[]) == ["input_sha256 must list at least one input"]
    assert problems(generated_at="2026-10-01T16:10:00") == ["generated_at: a timestamp needs a UTC offset (for example +07:00 or Z): '2026-10-01T16:10:00'"]
    assert problems(generated_at="2026-10-01T09:10:00+00:00") == ["generated_at must be a normalised ISO 8601 date-time with a UTC offset"]
    assert any("must be relative to its root" in line for line in problems(input_sha256=[{"root": "external", "path": "C:/data/dem.tif", "sha256": "a" * 64}]))
    assert any("needs a path and a SHA-256" in line for line in problems(input_sha256=[{"root": "external", "path": "dem.tif", "sha256": "abc"}]))
    document = minimal_manifest()
    del document["accepted_fpps"], document["operational_status"]
    found = evidence_problems(document)
    assert "missing key: accepted_fpps" in found and "missing key: operational_status" in found


def test_every_evidence_block_needs_its_lane_tier_relation_and_timestamp() -> None:
    for field in BLOCK_FIELDS:
        if field == "id":
            continue
        document = minimal_manifest()
        del document["evidence_blocks"][0][field]
        found = evidence_problems(document)
        assert f"evidence block water lacks {field}" in found, field
    document = minimal_manifest()
    document["evidence_blocks"][0]["lane"] = "OBSERVED"
    assert "evidence block water has an unknown lane: OBSERVED" in evidence_problems(document)
    document = minimal_manifest()
    document["evidence_blocks"][0]["evidence_tier"] = "T3 agency product"  # A scenario may not borrow another tier.
    assert f"evidence block water is a scenario and must carry the tier {SCENARIO_TIER!r}" in evidence_problems(document)
    document = minimal_manifest()
    del document["lanes"]["OBS"]
    assert "evidence block image uses lane OBS, which the manifest's lanes table does not define" in evidence_problems(document)
    document = minimal_manifest()
    document["evidence_blocks"].append(dict(document["evidence_blocks"][0]))
    assert "evidence block id repeats: water" in evidence_problems(document)


def test_content_without_an_evidence_block_is_found() -> None:
    document = minimal_manifest()
    assert uncovered_blocks(document) == []
    document["rainfall"] = {"stations": []}  # A new block that nobody gave a lane.
    document["layers"].append({"id": "s1"})  # A new image in a list that is covered item by item.
    assert uncovered_blocks(document) == ["layers[s1]", "rainfall"]
    assert "no evidence block covers rainfall" in evidence_problems(document)
    # A block that names content the manifest does not hold is a stale registry entry.
    document = minimal_manifest()
    document["evidence_blocks"][1]["covers"] = ["layers[s2]", "layers[gone]", "viirs_daily"]
    assert uncovered_blocks(document) == ["viirs_daily (named by an evidence block but absent)", "layers[gone] (named by an evidence block but absent)"]
    document["evidence_blocks"][1]["covers"] = ["layers s2"]
    with pytest.raises(ReplayManifestError, match="malformed covers path"):
        uncovered_blocks(document)
    # Envelope keys describe the manifest as a whole and never need a block.
    assert {"sources", "assumptions", "limitations", "generated_at", "input_sha256"} <= ENVELOPE_KEYS


def test_a_new_child_of_an_object_covered_child_by_child_has_no_lane() -> None:
    document = minimal_manifest()
    assert uncovered_blocks(document) == []  # "vectors.roads" names the only child of vectors.
    document["vectors"]["unosat4009_envelope"] = {"href": "/studies/x/r1/envelope.png"}
    assert uncovered_blocks(document) == ["vectors.unosat4009_envelope"]
    assert "no evidence block covers vectors.unosat4009_envelope" in evidence_problems(document)
    document["evidence_blocks"].append({"id": "envelope", "covers": ["vectors.unosat4009_envelope"], "lane": "OBS", "evidence_tier": "x",
                                        "temporal_relation": "event_aligned", "source_timestamp": "2024"})
    assert uncovered_blocks(document) == []
    # A child path below the first level still names its first-level child.
    document["evidence_blocks"][0]["covers"] = ["hand", "vectors.roads.features"]
    assert uncovered_blocks(document) == []
    # A block naming a child the object does not hold is a stale registry entry.
    document["evidence_blocks"][0]["covers"] = ["hand", "vectors.roads", "vectors.gone"]
    assert uncovered_blocks(document) == ["vectors.gone (named by an evidence block but absent)"]
    # A key covered whole lends its lane to every child, old or new; a partly covered key that is not an object is uncovered.
    document = minimal_manifest()
    document["evidence_blocks"][0]["covers"] = ["hand", "vectors"]
    document["vectors"]["later"] = {}
    assert uncovered_blocks(document) == []
    document["evidence_blocks"][0]["covers"] = ["hand", "vectors.roads"]
    document["vectors"] = ["roads"]
    assert uncovered_blocks(document) == ["vectors"]


def test_a_score_or_an_action_class_is_refused_at_any_depth() -> None:
    document = minimal_manifest()
    assert score_or_class_keys(document) == []
    document["hand"]["stats"] = [{"fpps": 81.2}]
    document["vectors"]["roads"]["accepted_action_class_by_tambon"] = {}
    document["layers"][0]["Priority-Score"] = 3
    document["hand"]["accepted_fpps"] = None  # The accepted_* names are reserved for the top level.
    assert score_or_class_keys(document) == ["$.hand.stats[0].fpps", "$.hand.accepted_fpps", "$.vectors.roads.accepted_action_class_by_tambon",
                                             "$.layers[0].Priority-Score"]
    found = evidence_problems(document)
    for path in score_or_class_keys(document):
        assert f"{path} is a score or action-class field: the replay computes no score and no action class" in found
    # Text that mentions a score is not a field, and the two null top-level fields stay allowed.
    document = minimal_manifest()
    document["reason_blocked"] = "No FPPS and no action_class is computed here."
    assert evidence_problems(document) == []


def test_scenario_fields_mark_model_values_inside_another_lane() -> None:
    document = minimal_manifest()
    document["layers"][0]["model_km2"] = 1.0
    image = document["evidence_blocks"][1]
    image["scenario_fields"] = ["layers[].model_km2"]
    assert evidence_problems(document) == []
    image["scenario_fields"] = []
    assert "evidence block image: scenario_fields must list at least one field path" in evidence_problems(document)
    image["scenario_fields"] = ["hand.model_km2"]  # Not inside what this block covers.
    assert "evidence block image: every scenario_fields path must lie inside the content the block covers" in evidence_problems(document)
    del image["scenario_fields"]
    document["evidence_blocks"][0]["scenario_fields"] = ["hand.step_m"]
    assert any("is already a scenario" in line for line in evidence_problems(document))


# --- The committed manifest ---------------------------------------------------------------------------------


def test_committed_manifest_has_every_required_key_and_keeps_the_contract(manifest: dict) -> None:
    assert [key for key in REQUIRED_KEYS if key not in manifest] == []
    assert evidence_problems(manifest) == []
    assert manifest["accepted_fpps"] is None and manifest["accepted_action_class"] is None
    assert manifest["official_warning"] is False and manifest["real_time"] is False and manifest["can_feed_decision_layer"] is False
    assert manifest["operational_status"] == "non_operational"
    assert manifest["protocol_sha256"] is None and manifest["protocol_sha256_reason"] == "not_a_protocol_case"
    assert manifest["dataset_mode"] == manifest["data_mode"] == "historical_reconstruction"
    assert manifest["confidence_class"] == manifest["confidence"] == "low" and len(manifest["confidence_basis"]) >= 4
    assert manifest["revision"] == manifest_path().parent.name and manifest["data_version"] == f"{manifest['study_id']}-{manifest['revision']}"
    assert manifest["permitted_use"] and "not an official warning" in manifest["permitted_use"]
    assert "no A-E action class" in manifest["reason_blocked"] and "not hashed" in manifest["reason_blocked"]
    # No score and no class anywhere in the data: only the two null accepted fields carry those names.
    text = manifest_path().read_text(encoding="utf-8")
    assert sorted(set(re.findall(r'"[a-z_]*(?:fpps|action_class)[a-z_]*"', text))) == ['"accepted_action_class"', '"accepted_fpps"']
    assert not LOCAL_PATH.search(text) and "\r" not in text


def test_committed_manifest_validates_against_its_json_schema(manifest: dict, schema: dict) -> None:
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == manifest["schema_id"]
    assert schema_problems(manifest, schema) == []
    assert set(REQUIRED_KEYS) <= set(schema["required"])  # The schema requires at least what the Python contract requires.
    # The schema itself refuses a score, a class, a warning or an independent label.
    for change, needle in (
        ({"accepted_fpps": 81.2}, "accepted_fpps"),
        ({"accepted_action_class": "E"}, "accepted_action_class"),
        ({"official_warning": True}, "official_warning"),
        ({"operational_status": "agency_operational"}, "operational_status"),
        ({"input_sha256": []}, "input_sha256"),
        ({"protocol_sha256": "a" * 64}, "protocol_sha256"),
        ({"generated_at_basis": "wall_clock"}, "generated_at_basis"),
    ):
        broken = {**manifest, **change}
        assert any(line.startswith(needle) for line in schema_problems(broken, schema)), needle
    broken = copy.deepcopy(manifest)
    broken["external_checks"][1]["role"] = "independent_magnitude_check"
    assert any(line.startswith("external_checks/1/role") for line in schema_problems(broken, schema))
    broken = copy.deepcopy(manifest)
    del broken["evidence_blocks"][0]["lane"]
    assert any(line.startswith("evidence_blocks/0") for line in schema_problems(broken, schema))
    broken = copy.deepcopy(manifest)
    del broken["evidence_blocks"][0]["source_timestamp"]
    assert any(line.startswith("evidence_blocks/0") for line in schema_problems(broken, schema))
    # A scenario block cannot carry scenario_fields, and an unrecorded tuning order is null, never false.
    broken = copy.deepcopy(manifest)
    broken["evidence_blocks"][0]["scenario_fields"] = ["hand.step_m"]
    assert any(line.startswith("evidence_blocks/0") for line in schema_problems(broken, schema))
    broken = copy.deepcopy(manifest)
    viirs = next(item for item in broken["exploratory_knowledge"]["items"] if item["id"] == "viirs-daily")
    viirs["known_during_tuning"] = False
    assert any(line.startswith("exploratory_knowledge/items/3") for line in schema_problems(broken, schema))


def test_generated_at_is_declared_and_git_commit_is_explained(manifest: dict) -> None:
    assert normalise_timestamp(manifest["generated_at"]) == manifest["generated_at"]
    assert manifest["generated_at_basis"] in ("declared", "newest_input_timestamp")
    assert "not read from the machine clock" in manifest["generated_at_note"]
    # A file cannot name the commit that adds it: the field is present, null and explained.
    assert manifest["git_commit"] is None and manifest["git_commit_reason"].startswith("self_reference")
    assert manifest["git_commit_lookup"].endswith(f"{manifest['revision']}/timeline.json")


def test_every_block_has_a_lane_and_a_source_timestamp_in_the_right_lane(manifest: dict) -> None:
    blocks = {block["id"]: block for block in manifest["evidence_blocks"]}
    assert uncovered_blocks(manifest) == []
    for block in blocks.values():
        for field in BLOCK_FIELDS:
            assert block.get(field), (block["id"], field)
        assert block["lane"] in manifest["lanes"]
    lane = lambda name: blocks[name]["lane"]  # noqa: E731
    # The water reconstruction, access and shelters are scenario (model) output, tier T1.
    for name in ("water_reconstruction", "residents_in_water", "evacuation_access", "shelter_plan"):
        assert (lane(name), blocks[name]["evidence_tier"]) == ("SCN", SCENARIO_TIER), name
    # VIIRS, Sentinel-1, Sentinel-2 and rain are observed, each with its own timestamp.
    observed = ("viirs_daily", "sentinel2_20240905", "sentinel2_20240915", "sentinel1_20240906", "sentinel1_20240915", "sentinel1_change", "rainfall")
    assert all(lane(name) == "OBS" for name in observed)
    # The model figures placed beside each VIIRS day are named as scenario values, not filed as the agency's.
    model_fields = sorted({key for day in manifest["viirs_daily"]["days"] for key in day if key.startswith("model_")})
    assert model_fields == ["model_flood_km2_clear", "model_flood_km2_district", "model_stage_m"]
    assert sorted(blocks["viirs_daily"]["scenario_fields"]) == [f"viirs_daily.days[].{field}" for field in model_fields]
    assert SCENARIO_TIER in blocks["viirs_daily"]["note"] and "not part of the agency product" in blocks["viirs_daily"]["note"]
    assert sorted(manifest["viirs_daily"]["model_fields"]["names"]) == model_fields
    assert manifest["viirs_daily"]["model_fields"]["evidence_tier"] == SCENARIO_TIER
    assert not any("scenario_fields" in block for block in blocks.values() if block["id"] != "viirs_daily")
    assert len({blocks[name]["source_timestamp"] for name in observed}) == len(observed)
    assert blocks["sentinel2_20240915"]["source_timestamp"] == "2024-09-15T03:58:15Z"
    assert blocks["sentinel1_20240915"]["source_timestamp"] == "2024-09-15T23:16:01Z"
    assert blocks["viirs_daily"]["source_timestamp"].startswith("2024-09-10T13:30+07:00/2024-09-18T13:30+07:00")
    assert blocks["rainfall"]["source_timestamp"].startswith("2024-09-09T00:00:00+07:00/2024-09-20T00:00:00+07:00")
    # GISTDA is a calibration anchor; the Sentinel-1 and UNOSAT 3991 size comparisons are calibration-informed.
    for name in ("gistda_onset_anchor", "sentinel1_size_comparison", "unosat_3991_size_comparison"):
        assert lane(name) == "CAL", name
    assert "Calibration anchor" in blocks["gistda_onset_anchor"]["evidence_tier"]
    assert "not an independent check" in blocks["sentinel1_size_comparison"]["evidence_tier"]
    assert "not an independent check" in blocks["unosat_3991_size_comparison"]["evidence_tier"]
    # Product 4009 is a season envelope scenario and is not shown.
    envelope = blocks["unosat_4009_season_envelope"]
    assert (envelope["lane"], envelope["temporal_relation"], envelope["shown"]) == ("SCN-ENV", "season_envelope", False)
    assert envelope["season_window"] == "2024-08-01/2024-10-22"
    # Reported facts are never filed as observed or as model output.
    assert lane("reported_shelters") == lane("event_chronology") == "REP"
    assert not any(block["lane"] == "OBS" and block["temporal_relation"] == "season_envelope" for block in blocks.values())


def test_top_level_source_timestamp_covers_every_dated_event_observation(manifest: dict) -> None:
    from datetime import datetime

    def instant(value: str) -> datetime:
        return datetime.fromisoformat(normalise_timestamp(value).replace("Z", "+00:00"))

    start, end = (instant(part) for part in manifest["source_timestamp"].split("/"))
    stamps = [observation["utc"] for observation in manifest["observations"]]
    stamps += [day["nominal_local_time"] for day in manifest["viirs_daily"]["days"]]
    stamps += [manifest["event_time"]["end"]]  # The last rain hour ends with the replay window.
    assert len(stamps) >= 14
    assert all(start <= instant(stamp) <= end for stamp in stamps)
    assert instant(manifest["observations"][0]["utc"]) == start and instant(manifest["event_time"]["end"]) == end
    hours = len(next(iter(manifest["rainfall"]["hourly_mm"].values())))
    assert hours == (instant(manifest["event_time"]["end"]) - instant(manifest["event_time"]["start"])).total_seconds() / 3600
    note = manifest["source_timestamp_note"]
    for needle in ("Sentinel-2", "rain", "VIIRS", "WorldPop 2020", "OpenStreetMap 2026-07-09"):
        assert needle in note, needle


def test_sources_name_both_dem_tiles_worldpop_and_a_licence_for_every_input(manifest: dict) -> None:
    sources = {source["id"]: source for source in manifest["sources"]}
    assert "N20 E099" in sources["copernicus-dem"]["name"] and "N20 E100" in sources["copernicus-dem"]["name"]
    assert sources["worldpop"]["licence"] == "CC BY 4.0" and sources["worldpop"]["name"] == manifest["population"]["source"]
    assert "unconstrained" in sources["worldpop"]["name"]
    eligibility = manifest["publication_eligibility"]
    inputs = {row["id"]: row for row in eligibility["inputs"]}
    expected = {"hii-rain": "CC BY-NC", "osm": "ODbL 1.0", "worldpop": "CC BY 4.0", "cod-ab": "CC BY-IGO",
                "viirs": "No licence stated by the provider", "unosat-4009": "CC BY-SA 4.0",
                "copernicus-dem": "Copernicus DEM licence (free, attribution)",
                "sentinel-1": "Copernicus Sentinel data terms (free, full and open)",
                "sentinel-2": "Copernicus Sentinel data terms (free, full and open)"}
    assert {name: inputs[name]["licence"] for name in expected} == expected
    assert inputs["viirs"]["licence_stated"] is False
    # Every listed source has an eligibility row with the same licence wording (VIIRS states none).
    for source_id, source in sources.items():
        assert source_id in inputs, source_id
        if source_id != "viirs":
            assert inputs[source_id]["licence"] == source["licence"], source_id
    # Product 4009 is listed but not shown, and nothing from it is among the baked files.
    assert inputs["unosat-4009"]["shown"] is False
    assert (ROOT / inputs["unosat-4009"]["rights_record"]).resolve() == RIGHTS_RECORD.resolve()
    assert [row["id"] for row in eligibility["inputs"] if not row["shown"]] == ["unosat-4009"]
    assert not [name for name in (path.name for path in manifest_path().parent.rglob("*")) if "4009" in name]
    assert eligibility["status"] == "conditional" and any("CC BY-NC" in line for line in eligibility["conditions"])


def test_product_4009_status_is_the_rights_records_status(manifest: dict) -> None:
    """The bake reads the product's status from the rights record. A record that changed since needs a new bake."""
    stale = "re-bake the replay manifest: its product 4009 status is read from the rights record at bake time"
    record = load_rights_basis(RIGHTS_RECORD)
    # The manifest carries the SHA-256 of the record it was baked from.
    row = next(row for row in manifest["input_sha256"] if row["path"] == RIGHTS_RECORD.relative_to(ROOT).as_posix())
    import hashlib

    assert row["sha256"] == hashlib.sha256(RIGHTS_RECORD.read_bytes()).hexdigest(), stale
    entry = next(item for item in manifest["publication_eligibility"]["inputs"] if item["id"] == "unosat-4009")
    block = next(item for item in manifest["evidence_blocks"] if item["id"] == "unosat_4009_season_envelope")
    reference = next(item for item in manifest["external_references"] if item["id"] == "unosat-4009")
    condition = next(line for line in manifest["publication_eligibility"]["conditions"] if "product 4009" in line)
    assert entry["licence"] == record["licence"]["name"] == "CC BY-SA 4.0"
    if owner_confirmed(record):
        confirmed = "the owners confirmed the rights record on"
        assert entry["status"].startswith("Not shown in this revision;") and confirmed in entry["status"], stale
        assert confirmed in block["note"] and confirmed in reference["note"] and confirmed in condition, stale
        assert "pending" not in entry["status"]
    else:
        assert entry["status"] == "Not yet shown; rights record pending owner confirmation.", stale
        assert block["note"].endswith("Shown only after the owners confirm the rights record."), stale
        assert "only after the owners confirm the rights record" in reference["note"] and "is signed" not in reference["note"], stale
        assert condition.endswith("it may appear only after the owners confirm the rights record."), stale
        # While the record is unconfirmed the manifest names no file for the product and marks nothing of it as shown.
        assert unconfirmed_product_citations(manifest) == []
    # What the record supports about UNOSAT's reply: its words and the day they were relayed, not the day UNOSAT wrote.
    assert "signed on 30 Sep 2026" in reference["note"] and f'"{record["provider_reply"]["quote"]}"' in reference["note"]
    assert record["provider_reply"]["relayed_on"] == "2026-10-01" and record["provider_reply"]["original_message_in_repo"] is False
    assert '"we approve the use" (relayed by a project owner on 1 Oct 2026)' in reference["note"]
    assert not __import__("re").search(r'approve the use" on \d', reference["note"])


def test_input_hashes_are_the_receipts_and_name_no_machine_path(manifest: dict) -> None:
    rows = manifest["input_sha256"]
    assert len(rows) == 32 and [(row["root"], row["path"]) for row in rows] == sorted((row["root"], row["path"]) for row in rows)
    for row in rows:
        assert row["root"] in ("external", "repo") and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) and row["bytes"] > 0
    receipt = json.loads((ROOT / "docs" / f"mae_sai_timeline_{manifest['revision']}_input_receipt.json").read_text(encoding="utf-8"))
    assert rows == receipt["inputs"]
    assert sum(1 for row in rows if "Copernicus_DSM_COG_10_N20_00_E" in row["path"]) == 2
    assert not LOCAL_PATH.search(json.dumps(rows))
    # OpenStreetMap is the Geofabrik extract itself; no machine-made cache stands in for it.
    assert [row["path"] for row in rows if "osm" in row["path"].lower()] == ["open_context/osm_geofabrik/thailand-latest.osm.pbf"]
    assert not any(row["path"].endswith(".gpkg") or "derived_context" in row["path"] for row in rows)
    # Every shelter candidate therefore lies inside the replay area that the extract is cut to.
    assert manifest["shelters"]["candidates"] and all(candidate["m"] for candidate in manifest["shelters"]["candidates"])


def test_exploratory_knowledge_states_what_was_used_or_known_during_tuning(manifest: dict) -> None:
    disclosure = manifest["exploratory_knowledge"]
    items = {item["id"]: item for item in disclosure["items"]}
    assert (items["gistda-radarsat2-20240910"]["relation"], items["sentinel-1-20240916"]["relation"]) == ("used_for_tuning", "used_for_tuning")
    assert "9.9 km2" in items["gistda-radarsat2-20240910"]["statement"] and "on purpose" in items["gistda-radarsat2-20240910"]["statement"]
    assert "re-tune the recession keyframes (best-fit stage 0.10 m)" in items["sentinel-1-20240916"]["statement"]
    assert items["unosat-3991"]["relation"] == "known_during_tuning" and "70 km2" in items["unosat-3991"]["statement"]
    assert (items["unosat-4009"]["relation"], items["unosat-4009"]["known_during_tuning"]) == ("computed_after_keyframes_final", False)
    assert "was not used for tuning" in items["unosat-4009"]["statement"]
    # VIIRS: the build history shows the comparison and the last stage-knot edit in one change (commit 129ff03), so the
    # manifest claims only what that supports: not used for tuning, order within the change not recorded.
    viirs = items["viirs-daily"]
    assert (viirs["relation"], viirs["known_during_tuning"]) == ("not_used_for_tuning", None)
    assert "was not used for tuning" in viirs["statement"] and "commit 129ff03" in viirs["statement"]
    assert "does not record which came first" in viirs["statement"] and "not presented as an independent check" in viirs["statement"]
    assert "computed after the keyframes were final" not in viirs["statement"]
    assert all(items[name]["known_during_tuning"] for name in ("gistda-radarsat2-20240910", "sentinel-1-20240916", "unosat-3991"))
    assert "28 Sep 2026" in disclosure["depth_factor"] and disclosure["rule"]
    # The disclosure, the labels and the numbers agree: what was used or known is never labelled independent.
    anchor = manifest["s1_anchor"]
    assert anchor["role"] == "calibration_informed_magnitude_check" and round(anchor["best_fit_stage_m"], 2) == 0.10
    roles = {check["id"]: check["role"] for check in manifest["external_checks"]}
    assert roles == {"gistda-radarsat2-20240910": "calibration_anchor", "unosat-3991": "calibration_informed_magnitude_check"}
    assert not re.search(r'"role": "independent', manifest_path().read_text(encoding="utf-8"))
    assert "tuned to one radar pass rather than checked independently" in manifest["confidence_reason"]
    assert any("re-tuned to the 16 September 06:16 ICT Sentinel-1 pass" in line and "not an independent check" in line for line in manifest["assumptions"])
    # The quoted UNOSAT 3991 wording is unchanged from r3 (its exact source wording could not be checked on disk).
    unosat = next(check for check in manifest["external_checks"] if check["id"] == "unosat-3991")
    assert unosat["reported_text"] == "about 70 km2 flood-affected within a 305 km2 analysed area; about 13,600 people exposed (WorldPop 2020); preliminary, not field-validated"


# --- Capacity-aware shelter plan and what-if levels (roadmap P2-9, C-1) ---------------------------------------


def test_capacity_aware_plan_and_robustness_have_their_own_scenario_blocks(manifest: dict) -> None:
    blocks = {block["id"]: block for block in manifest["evidence_blocks"]}
    for name, covers, relation in (("capacity_aware_plan", "shelters.capacitated", "event_window_reconstruction"),
                                   ("plan_robustness", "shelters.robustness", "what_if_levels")):
        block = blocks[name]
        assert (block["lane"], block["evidence_tier"], block["temporal_relation"]) == ("SCN", SCENARIO_TIER, relation), name
        assert block["covers"] == [covers] and block["source_timestamp"], name
    assert "Candidates to verify, not a list of sites to open" in blocks["capacity_aware_plan"]["note"]
    assert "not return periods" in blocks["plan_robustness"]["note"]
    for key in ("capacitated", "robustness"):
        part = manifest["shelters"][key]
        assert part["scenario_tier"] == SCENARIO_TIER and part["confidence"] == "low"
        assert part["confidence_reason"] and part["source_timestamp"] and part["assumptions"]
    # A block that names a missing child is reported, so the two blocks cannot outlive their content.
    broken = copy.deepcopy(manifest)
    del broken["shelters"]["robustness"]
    assert "shelters.robustness (named by an evidence block but absent)" in uncovered_blocks(broken)


def test_capacity_aware_plan_never_loads_a_site_beyond_capacity_and_its_arithmetic_holds(manifest: dict) -> None:
    shelters = manifest["shelters"]
    plan = shelters["capacitated"]
    demand = plan["demand_people"]
    assert demand == shelters["demand_people"]  # The same residents as the coverage ranking: homes that flood at the peak.
    candidates = {candidate["id"]: candidate for candidate in shelters["candidates"]}
    estimate = "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified"
    assert plan["capacity_basis"] == {"estimate": estimate, "unknown": "unknown"}
    for rows in (plan["plan"], plan["coverage_plan"]):
        assert rows and len({row["candidate_id"] for row in rows}) == len(rows)
        for position, row in enumerate(rows, start=1):
            candidate = candidates[row["candidate_id"]]
            assert candidate["eligible"] and row["capacity_est"] == candidate["capacity_est"]
            known = candidate["capacity_est"] is not None
            assert row["capacity_basis"] == (estimate if known else "unknown")
            assert row["upper_capacity_basis"] in (("estimate",) if known else ("kind_median", "all_kinds_median"))
            assert row["lower"]["capacity"] == (candidate["capacity_est"] if known else 0)
            if known:
                assert row["upper"]["capacity"] == candidate["capacity_est"]
            elif row["upper_capacity_basis"] == "kind_median":
                assert row["upper"]["capacity"] == plan["kind_median_capacity"][candidate["kind"]]
            else:
                assert row["upper"]["capacity"] == plan["all_kinds_median_capacity"]
            for key in ("lower", "upper"):
                bound = row[key]
                assert 0 <= bound["load"] <= bound["capacity"], (row["candidate_id"], key)  # Load never exceeds capacity.
                assert bound["overflow"] == demand - bound["served"]  # overflow = demand - served.
                assert bound["served"] == sum(item[key]["load"] for item in rows[:position])  # Nested: a running total.
            assert row["lower"]["served"] <= row["upper"]["served"]  # Lower bound <= upper bound.
    # The medians come from the candidates' own estimates (every candidate with one, eligible or not).
    by_kind: dict[str, list[int]] = {}
    for candidate in shelters["candidates"]:
        if candidate["capacity_est"] is not None:
            by_kind.setdefault(candidate["kind"], []).append(candidate["capacity_est"])
    median = lambda values: sorted(values)[len(values) // 2] if len(values) % 2 else sum(sorted(values)[len(values) // 2 - 1:len(values) // 2 + 1]) // 2  # noqa: E731
    assert plan["kind_median_capacity"] == {kind: median(values) for kind, values in sorted(by_kind.items())}
    assert plan["all_kinds_median_capacity"] == median([value for values in by_kind.values() for value in values])
    # The coverage ranking is counted row for row, in its own order.
    assert [row["candidate_id"] for row in plan["coverage_plan"]] == [entry["candidate_id"] for entry in shelters["plan"]]
    assert all("within_reach" in row for row in plan["plan"]) and not any("within_reach" in row for row in plan["coverage_plan"])
    assert all(row["upper"]["served"] <= row["within_reach"] <= demand - shelters["uncoverable_people"] for row in plan["plan"])
    # Every eligible candidate together is the ceiling of any plan.
    everything = plan["all_eligible"]
    assert everything["sites"] == shelters["eligible_count"] and everything["within_reach"] == demand - shelters["uncoverable_people"]
    for key in ("lower", "upper"):
        assert everything[key]["overflow"] == demand - everything[key]["served"]
        assert everything[key]["served"] <= everything[key]["capacity"]
        assert max(row[key]["served"] for rows in (plan["plan"], plan["coverage_plan"]) for row in rows) <= everything[key]["served"]
    assert everything["lower"]["served"] <= everything["upper"]["served"] < demand


def test_capacity_aware_plan_states_the_roadmap_example_and_its_caveats(manifest: dict) -> None:
    shelters = manifest["shelters"]
    plan = shelters["capacitated"]
    k = shelters["knee_k"]
    # The site the nearest-site rule overloads: 79 places, about 2,430 residents assigned in the default plan.
    first = plan["coverage_plan"][0]
    assert (first["capacity_est"], shelters["plan"][k - 1]["loads"][0]) == (79, 2430)
    assert first["upper"] == {"capacity": 79, "load": 79, "served": 79, "overflow": shelters["demand_people"] - 79}
    # With capacity counted, the default plan's sites hold far fewer residents than can walk to them.
    assert plan["coverage_plan"][k - 1]["upper"]["served"] < 0.2 * shelters["plan"][k - 1]["cumulative_demand"]
    text = " ".join([plan["demand_basis"], plan["method"], *plan["bounds"].values(), *plan["assumptions"]])
    for phrase in ("T1 scenario (model)", "an upper bound", "many people stay with relatives", "unverified", "candidates to verify",
                   "not a list of sites to open", "different source", "overflow = demand_people - served", "counts as 0", "median"):
        assert phrase in text, phrase
    # No participation sweep, no listed capacity and no score: only footprint estimates and their medians.
    flat = json.dumps(plan).lower()
    assert "participation" not in flat and "listed_capacity" not in flat
    assert score_or_class_keys(plan) == []
    assert any("capacity-aware plan" in line and "candidates to verify" in line for line in manifest["assumptions"])


def test_plan_robustness_repeats_the_ranking_at_what_if_levels_not_return_periods(manifest: dict) -> None:
    shelters = manifest["shelters"]
    robustness = shelters["robustness"]
    assert robustness["label"] == "What-if levels around an illustrative peak, not return periods."
    stages = robustness["stages"]
    assert [stage["stage_m"] for stage in stages] == [2.5, 3.5, 4.0]
    assert [stage["modelled_peak"] for stage in stages] == [False, True, False]
    peak = stages[1]
    assert peak["stage_m"] == shelters["method"]["peak_stage_m"]
    # The peak row is the plan the replay shows.
    assert peak["plan"] == [entry["candidate_id"] for entry in shelters["plan"]]
    assert (peak["demand_people"], peak["eligible_count"], peak["uncoverable_people"], peak["knee_k"]) == (
        shelters["demand_people"], shelters["eligible_count"], shelters["uncoverable_people"], shelters["knee_k"])
    assert peak["cumulative_demand"] == [int(entry["cumulative_demand"] + 0.5) for entry in shelters["plan"]]  # Halves up, as the page rounds.
    # Residents whose homes flood at each level (roadmap C-1).
    assert [stage["demand_people"] for stage in stages] == [10333, 14169, 16069]
    eligible = {candidate["id"] for candidate in shelters["candidates"]}
    for stage in stages:
        assert len(set(stage["plan"])) == len(stage["plan"]) == len(stage["cumulative_demand"]) and set(stage["plan"]) <= eligible
        assert stage["cumulative_demand"] == sorted(stage["cumulative_demand"])  # Nested plans: coverage only grows.
        assert stage["cumulative_demand"][-1] <= stage["demand_people"] - stage["uncoverable_people"]
        assert 1 <= stage["knee_k"] <= len(stage["plan"])
    # A higher level floods more homes and can only remove candidates.
    assert stages[0]["eligible_count"] >= stages[1]["eligible_count"] >= stages[2]["eligible_count"]
    # The robust core for k sites: among the first k at every level, in the order of the replay's plan.
    core = robustness["core_by_k"]
    assert len(core) == len(shelters["plan"])
    for k, sites in enumerate(core, start=1):
        heads = [set(stage["plan"][:k]) for stage in stages]
        assert sites == [site for site in peak["plan"][:k] if all(site in head for head in heads)]
    assert core[shelters["knee_k"] - 1], "the default plan has no site that holds at every level"
    text = json.dumps(robustness)
    assert not re.search(r"\b(?:25|100)[- ]?year", text) and "return period" not in text.replace("not return periods", "")
    assert score_or_class_keys(robustness) == []
