"""Reported flood depths (news, not surveyed) and their consistency with the replay model (roadmap C-2).

Covers the data file (``outputs/mae_sai_reported_depths_2024.json``: its schema, its rules and the copyright guard),
the consistency maths on synthetic grids and stage curves (``floodguard.reported_depths``), the ``reported_depths``
block of the committed manifest and the evidence contract that refuses a broken one
(``floodguard.replay_manifest.reported_depth_problems``). The comparison is a consistency check, never a validation,
and the reports are never used to tune the model; nothing here computes a score or an action class.
"""

from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pytest

from floodguard import reported_depths as rd
from floodguard.flood_timeline import CHANNEL_CODE, NEVER_CODE, stage_anchors, stage_at
from floodguard.replay_manifest import evidence_problems, reported_depth_problems, schema_problems

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / rd.REPORTED_DEPTHS_PATH
DATA_SCHEMA = ROOT / rd.SCHEMA_PATH
MANIFEST_SCHEMA = ROOT / "packages" / "contracts" / "schemas" / "case-replay-timeline.schema.json"
ORIGIN = datetime.fromisoformat("2024-09-09T00:00:00+07:00")


def manifest_path() -> Path:
    source = (ROOT / "apps" / "web" / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return ROOT / "apps" / "web" / "public" / href.lstrip("/")


@pytest.fixture(scope="module")
def document() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(manifest_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def block(manifest: dict) -> dict:
    return manifest["reported_depths"]


# --- The data file ------------------------------------------------------------------------------------------


def test_data_file_keeps_its_schema_and_its_rules(document: dict) -> None:
    schema = json.loads(DATA_SCHEMA.read_text(encoding="utf-8"))
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == document["schema_id"]
    assert schema_problems(document, schema) == []
    assert rd.document_problems(document) == []
    raw = DATA.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    # AGENTS.md: a source timestamp, a confidence and assumptions; the status says what the data are.
    assert document["status"] == "reported (anecdotal, not surveyed)" and document["confidence"] == "low"
    assert document["source_timestamp"].startswith("reports published 2024-09-10T05:32+07:00/2024-09-13T11:32+07:00")
    assert document["assumptions"] and "never used to tune" in document["use_rule"]
    # No score, no action class, no personal phone number copied from an appeal.
    text = raw.decode("utf-8")
    assert not re.search(r"fpps|action_class|priority_score", text, re.IGNORECASE)
    from floodguard.wording_lint import json_strings

    phone = re.compile(r"(?<![0-9])0[0-9]{1,2}[- .]?[0-9]{3}[- .]?[0-9]{3,4}(?![0-9])")
    assert [path for path, value in json_strings(document) if phone.search(value)] == []


def test_data_file_holds_the_kept_reports_with_their_corrections_applied(document: dict) -> None:
    reports = {report["id"]: report for report in document["reports"]}
    assert len(reports) == 21 and "ms-c2-03" not in reports and "ms-c2-05" not in reports and "ms-c2-21" not in reports
    assert {item["id"] for item in document["left_out"]["dropped"]} == {"ms-c2-03", "ms-c2-05", "ms-c2-21"}
    # Six reports give one number, all lower bounds; the others give a range, or a storey or body reference (a class).
    bounds = {name: report["depth"]["lower_bound_m"] for name, report in reports.items() if report["depth"]["kind"] == "lower_bound"}
    assert bounds == {"ms-c2-01": 1.0, "ms-c2-02": 2.0, "ms-c2-06": 1.0, "ms-c2-07": 1.5, "ms-c2-08": 1.5, "ms-c2-09": 1.5, "ms-c2-17": 1.0}
    ranges = {name: (report["depth"]["lower_bound_m"], report["depth"]["upper_m"]) for name, report in reports.items() if report["depth"]["kind"] == "range"}
    assert ranges == {"ms-c2-14": (2.0, 3.0), "ms-c2-15": (2.0, 3.0), "ms-c2-16": (2.0, 3.0), "ms-c2-23": (0.3, 0.5), "ms-c2-24": (0.5, 0.6)}
    classes = {name: report["depth"]["class"] for name, report in reports.items() if report["depth"]["kind"] == "class"}
    assert classes == {"ms-c2-04": "roof_level_refuge", "ms-c2-10": "waist_deep", "ms-c2-11": "ground_floor_submerged", "ms-c2-12": "neck_deep",
                       "ms-c2-13": "chest_deep", "ms-c2-18": "waist_deep", "ms-c2-19": "over_head", "ms-c2-20": "above_ground_floor",
                       "ms-c2-22": "chest_deep"}
    # A point only where the location confidence is medium or high: twelve located reports.
    located = sorted(name for name, report in reports.items() if report["point"])
    assert located == ["ms-c2-01", "ms-c2-02", "ms-c2-07", "ms-c2-08", "ms-c2-09", "ms-c2-12", "ms-c2-14", "ms-c2-15", "ms-c2-18",
                       "ms-c2-19", "ms-c2-20", "ms-c2-22"]
    # The checker's corrections are applied, not only recorded.
    assert "spread" in reports["ms-c2-01"]["depth"]["statement"]["en"] and "overflow" not in reports["ms-c2-01"]["depth"]["statement"]["en"]
    assert "Bangkok Insight" not in reports["ms-c2-01"]["depth"]["statement"]["en"] and "130 m east" in reports["ms-c2-01"]["location_basis"]
    for name in ("ms-c2-14", "ms-c2-15", "ms-c2-16"):
        assert "fairly high" in reports[name]["depth"]["statement"]["en"] and "deepest" not in reports[name]["depth"]["statement"]["en"]
    assert "One Facebook message" in reports["ms-c2-13"]["depth"]["statement"]["en"] and "marked by a black tarpaulin" in reports["ms-c2-13"]["depth"]["statement"]["en"]
    assert "she waded home" in reports["ms-c2-22"]["depth"]["statement"]["en"] and "neighbour" not in reports["ms-c2-22"]["depth"]["statement"]["en"]
    assert "Ko Sai" in reports["ms-c2-24"]["place"]["en"] and "Sai Lom Joy" not in reports["ms-c2-24"]["place"]["en"]
    assert reports["ms-c2-24"]["tambon"]["en"] == "Mae Sai" and reports["ms-c2-24"]["time"]["window_start"] is None
    assert "Mum Khao" in reports["ms-c2-18"]["depth"]["statement"]["en"] and "Siam News" not in reports["ms-c2-18"]["depth"]["statement"]["en"]
    assert "Wiang Phang Kham" in reports["ms-c2-07"]["tambon_note"] and "waist" in reports["ms-c2-10"]["depth"]["statement"]["en"]
    # Every report is bilingual where the page shows it, and dated within the event.
    for report in reports.values():
        for field in (report["place"], report["tambon"], report["depth"]["statement"], report["time"]["text"]):
            assert field["en"] and re.search(r"[฀-๿]", field["th"]), report["id"]
        assert re.search(r"2567 \(2024\)", report["time"]["text"]["th"]) or "2567" not in report["time"]["text"]["th"]
        assert report["source"]["published"][:10] in ("2024-09-10", "2024-09-11", "2024-09-12", "2024-09-13")


def test_copyright_guard_refuses_copied_titles_long_titles_and_more_than_one_quote_per_source(document: dict) -> None:
    assert rd.copyright_problems(document) == []
    copied = copy.deepcopy(document)
    report = copied["reports"][0]
    report["depth"]["statement"]["th"] = f"ข้อความ {report['source']['title']} ต่อท้าย"
    assert any("repeats" in line for line in rd.copyright_problems(copied))
    long_title = copy.deepcopy(document)
    long_title["reports"][1]["source"]["title"] = "ก" * 161
    assert any("longer than 160" in line for line in rd.copyright_problems(long_title))
    quoted = copy.deepcopy(document)
    quoted["reports"][2]["depth"]["statement"]["en"] += ' The appeal said "water to the roof".'
    quoted["reports"][2]["location_basis"] += ' The article said "all night on the roof".'
    assert any("different quoted phrases" in line for line in rd.copyright_problems(quoted))
    long_quote = copy.deepcopy(document)
    long_quote["reports"][3]["depth"]["statement"]["en"] += ' "' + " ".join(["word"] * 15) + '"'
    assert any("quoted phrase has 15 words" in line for line in rd.copyright_problems(long_quote))
    # One short quoted phrase per source is allowed; a place name shared with the title is not a copy.
    assert rd.copied_runs("ตลาดสายลมจอย น้ำลึก", "น้ำท่วมแม่สายตลาดสายลมจอย") == []
    assert rd.quoted_phrases("It's the market's 'fairly high' water, not \"the deepest\"") == ["fairly high", "the deepest"]


def test_data_file_rules_refuse_a_point_at_low_confidence_a_number_for_a_class_and_a_bad_window(document: dict) -> None:
    broken = copy.deepcopy(document)
    low = next(report for report in broken["reports"] if report["location_confidence"] == "low")
    low["point"] = {"lat": 20.44, "lon": 99.88}
    assert any("a point is given exactly where" in line for line in rd.document_problems(broken))
    broken = copy.deepcopy(document)
    cls = next(report for report in broken["reports"] if report["depth"]["kind"] == "class")
    cls["depth"]["lower_bound_m"] = 1.2
    assert any("a class has no number" in line for line in rd.document_problems(broken))
    broken = copy.deepcopy(document)
    broken["reports"][0]["time"]["window_end"] = broken["reports"][0]["time"]["window_start"]
    assert any("must end after it starts" in line for line in rd.document_problems(broken))
    broken = copy.deepcopy(document)
    broken["use_rule"] = "A consistency check."
    assert any("never used to tune" in line for line in rd.document_problems(broken))
    broken = copy.deepcopy(document)
    broken["status"] = "surveyed"
    assert any("status must be" in line for line in rd.document_problems(broken))
    broken = copy.deepcopy(document)
    broken["assumptions_th"] = broken["assumptions_th"][:-1]
    assert any("one Thai assumption per English assumption" in line for line in rd.document_problems(broken))


def test_data_file_records_one_statement_per_community_and_the_records_of_a_statement_agree(document: dict) -> None:
    groups = rd.statement_groups(document["reports"])
    # 21 place records from 17 statements in 14 articles: PPTV's statement names three communities, and so does Thai PBS's.
    assert (len(document["reports"]), len(groups), len({report["source"]["url"] for report in document["reports"]})) == (21, 17, 14)
    shared = {statement: [report["id"] for report in members] for statement, members in groups.items() if len(members) > 1}
    assert shared == {"ms-c2-07": ["ms-c2-07", "ms-c2-08", "ms-c2-09"], "ms-c2-14": ["ms-c2-14", "ms-c2-15", "ms-c2-16"]}
    assert all("statement" in report["depth"]["statement"]["en"] for members in shared.values() for report in groups[members[0]])
    # The shared-statement rule is an assumption of the file, in both languages.
    assert any("recorded once per community" in line and "once per statement" in line for line in document["assumptions"])
    assert len(document["assumptions_th"]) == len(document["assumptions"]) and all(re.search(r"[฀-๿]", line) for line in document["assumptions_th"])
    for change, needle in (
        (lambda value: value["reports"][5].__setitem__("statement_id", "ms-c2-09"), "first place record"),  # ms-c2-08 under ms-c2-09
        (lambda value: value["reports"][6]["time"].__setitem__("window_end", "2024-09-10T11:00:00+07:00"), "share one source, depth and time window"),
        (lambda value: value["reports"][11]["depth"].__setitem__("upper_m", 4.0), "share one source, depth and time window"),
    ):
        broken = copy.deepcopy(document)
        change(broken)
        assert any(needle in line for line in rd.document_problems(broken)), needle


# --- Consistency maths on synthetic cases --------------------------------------------------------------------


ANCHORS = [(0.0, 0.0), (1.0, 0.0), (1.5, 0.1), (2.0, 2.0), (3.0, 3.5), (4.0, 1.0)]


def test_window_max_stage_takes_an_end_or_an_anchor_inside_the_window() -> None:
    assert rd.window_max_stage(1.0, 1.25, ANCHORS) == (pytest.approx(0.05), 1.25)  # Rising: the end.
    assert rd.window_max_stage(2.5, 3.5, ANCHORS) == (3.5, 3.0)  # The anchor inside the window.
    assert rd.window_max_stage(3.2, 3.8, ANCHORS)[1] == 3.2  # Falling: the start.
    assert rd.window_max_stage(5.0, 6.0, ANCHORS) == (1.0, 5.0)  # Held after the last anchor; the earliest of a tie.
    stage, at = rd.window_max_stage(1.0, 1.5, ANCHORS)
    assert (stage, at) == (pytest.approx(0.1), 1.5)
    with pytest.raises(rd.ReportedDepthsError):
        rd.window_max_stage(2.0, 1.0, ANCHORS)
    # On the replay's own curve the maximum agrees with dense sampling.
    anchors = stage_anchors()
    for start, end in ((1.0, 1.23), (1.75, 2.28), (2.0, 2.66), (3.25, 3.55), (4.1, 4.9)):
        dense = max(stage_at(start + (end - start) * index / 2000) for index in range(2001))
        exact = rd.window_max_stage(start, end, anchors)[0]
        assert dense - 1e-9 <= exact <= dense + 1e-3  # Sampling can only miss a knot, never exceed it.


def test_cell_depth_follows_the_replay_rule_and_the_first_wet_hour_the_hourly_grid() -> None:
    assert rd.cell_depth(CHANNEL_CODE, 1.0, 3.0) is None  # The river itself: no street depth to compare.
    assert rd.cell_depth(NEVER_CODE, 1.0, 3.5) == 0.0  # Above the encoded range: dry at every stage.
    assert rd.cell_depth(20, 1.0, 3.5) == pytest.approx(2.5)  # Effective HAND 1.0 m.
    assert rd.cell_depth(20, 0.5, 3.5) == pytest.approx(1.25)  # k * (stage - HAND_eff).
    assert rd.cell_depth(20, 1.0, 0.9) == 0.0
    stages = [0.0, 0.2, 0.6, 1.2, 0.4]
    assert rd.first_wet_hour(10, stages) == 2 and rd.first_wet_hour(30, stages) is None
    assert rd.first_wet_hour(CHANNEL_CODE, stages) is None and rd.first_wet_hour(NEVER_CODE, stages) is None


def synthetic_grid() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    codes = np.full((7, 7), 60, dtype=np.uint8)  # Effective HAND 3.0 m everywhere ...
    codes[3, 3] = CHANNEL_CODE  # ... a channel cell at the centre ...
    codes[3, 4] = 10  # ... a low cell (0.5 m) just east of it ...
    codes[0, 0] = 2  # ... and a very low cell (0.1 m) in the corner, about 14 m from (1, 1).
    factors = np.ones((7, 7), dtype=np.float32)
    factors[3, 4] = 0.8
    valid = np.ones((7, 7), dtype=bool)
    valid[6, 6] = False
    return codes, factors, valid


def test_point_model_reads_the_point_moves_off_the_channel_and_reports_a_tolerance_sensitivity() -> None:
    codes, factors, valid = synthetic_grid()
    hourly = [0.0, 0.5, 1.0, 2.0, 3.5]
    plain = rd.point_model(codes, factors, valid, 1, 1, 10.0, 15.0, 1.0, 3.5, hourly)
    assert plain["comparable"] and plain["cell"] == "point" and plain["depth_m"] == 0.0
    assert plain["peak_depth_m"] == 0.5 and plain["first_wet_hour"] == 4 and plain["height_above_channel_m"] == 3.0
    # Within 15 m of (1, 1) lies the corner cell (0.1 m): the sensitivity sees 0.9 m there.
    assert plain["max_within_tolerance_m"] == 0.9
    channel = rd.point_model(codes, factors, valid, 3, 3, 10.0, 15.0, 1.0, 3.5, hourly)
    assert channel["cell"] == "nearest_out_of_channel" and channel["moved_m"] == 10.0
    assert channel["depth_m"] == 0.0  # The first of the four cells at 10 m in row order: (2, 3), effective HAND 3.0 m.
    assert channel["max_within_tolerance_m"] == pytest.approx(0.4)  # 0.8 * (1.0 - 0.5) at (3, 4).
    assert rd.point_model(codes, factors, valid, 6, 6, 10.0, 15.0, 1.0, 3.5, hourly) == {"comparable": False, "reason": "outside_model"}
    assert rd.point_model(codes, factors, valid, 9, 0, 10.0, 15.0, 1.0, 3.5, hourly)["reason"] == "outside_model"
    only_channel = np.full((3, 3), CHANNEL_CODE, dtype=np.uint8)
    result = rd.point_model(only_channel, np.ones((3, 3)), np.ones((3, 3), dtype=bool), 1, 1, 10.0, 15.0, 1.0, 3.5, hourly)
    assert result == {"comparable": False, "reason": "channel_only_within_tolerance"}


def test_consistency_status_and_counts() -> None:
    status = rd.consistency_status
    assert status("numeric", 1.5, 2.0) == "consistent"
    assert status("numeric", 1.5, 1.5) == "consistent"  # Reaching the lower bound is enough.
    assert status("numeric", 1.5, 0.4) == "model_shallower"
    assert status("numeric", 1.5, 0.0) == "model_dry"
    assert status("numeric", 1.5, None) == "not_comparable"
    # A class is wet or dry only: no depth is compared, so it is never "consistent", however deep the body reference.
    assert status("qualitative", None, 0.05) == "model_wet" and status("qualitative", None, 0.78) == "model_wet"
    assert status("qualitative", None, 0.0) == "model_dry"
    assert status("qualitative", None, None) == "not_comparable"
    with pytest.raises(rd.ReportedDepthsError):
        status("numeric", None, 1.0)
    with pytest.raises(rd.ReportedDepthsError):
        status("survey", 1.0, 1.0)
    counts = rd.consistency_counts([("numeric", "consistent"), ("numeric", "model_dry"), ("qualitative", "model_dry"), ("qualitative", "not_comparable"),
                                    ("qualitative", "model_wet")])
    assert counts["numeric"] == {"consistent": 1, "model_shallower": 0, "model_wet": 0, "model_dry": 1, "not_comparable": 0}
    assert counts["all"] == {"consistent": 1, "model_shallower": 0, "model_wet": 1, "model_dry": 2, "not_comparable": 1}
    for row in (("numeric", "validated"), ("qualitative", "consistent"), ("qualitative", "model_shallower"), ("numeric", "model_wet")):
        with pytest.raises(rd.ReportedDepthsError):
            rd.consistency_counts([row])
    # Once per statement: a statement whose places agree keeps their outcome; one whose places differ is mixed.
    by_statement = rd.statement_counts([("a", "model_dry"), ("a", "model_dry"), ("b", "model_dry"), ("b", "consistent"), ("c", "model_wet")])
    assert by_statement == {"consistent": 0, "model_shallower": 0, "model_wet": 1, "model_dry": 1, "not_comparable": 0, "mixed": 1}


def test_the_assumed_stage_first_rises_above_the_early_level_on_the_evening_of_10_sep() -> None:
    assert rd.early_stage_until([(0.0, 0.0), (1.0, 0.0), (1.5, 0.1), (1.75, 0.1), (2.0, 2.5)], ORIGIN) == datetime.fromisoformat("2024-09-10T18:00:00+07:00")
    assert rd.early_stage_until([(0.0, 0.0), (1.0, 0.3)], ORIGIN) == datetime.fromisoformat("2024-09-09T08:00:00+07:00")
    assert rd.local_iso(rd.early_stage_until(stage_anchors(), ORIGIN)) == "2024-09-10T18:15:00+07:00"
    with pytest.raises(rd.ReportedDepthsError):
        rd.early_stage_until([(0.0, 0.0), (1.0, 0.05)], ORIGIN)


def test_manifest_block_assembles_outcomes_from_the_models_and_keeps_its_rules(document: dict) -> None:
    models = {report["id"]: {"comparable": True, "cell": "point", "moved_m": 0.0, "height_above_channel_m": 1.0, "depth_m": 1.6,
                             "peak_depth_m": 2.5, "first_wet_hour": 40, "max_within_tolerance_m": 1.9}
              for report in document["reports"] if report["point"]}
    built = rd.manifest_block(document, models, origin=ORIGIN, data_file={"path": rd.REPORTED_DEPTHS_PATH.as_posix(), "sha256": "0" * 64},
                              window_stage=lambda start, end: rd.window_max_stage(start, end, stage_anchors()), peak_stage_m=3.5,
                              early_until=rd.early_stage_until(stage_anchors(), ORIGIN))
    assert rd.block_problems(built) == []
    outcome = {report["id"]: report["consistency"] for report in built["reports"]}
    # 1.6 m reaches 1.0 and 1.5 m, not 2.0 m; a class is wet (no depth compared); a report without a point is not comparable.
    assert outcome["ms-c2-01"] == "consistent" and outcome["ms-c2-07"] == "consistent" and outcome["ms-c2-02"] == "model_shallower"
    assert outcome["ms-c2-14"] == "model_shallower" and outcome["ms-c2-12"] == "model_wet" and outcome["ms-c2-04"] == "not_comparable"
    assert built["counted"] == {"place_records": 21, "statements": 17, "articles": 14}
    assert built["assumptions"] == {"en": document["assumptions"], "th": document["assumptions_th"]}
    assert built["counts"]["all"]["not_comparable"] == 9 and sum(built["counts"]["all"].values()) == 21
    assert built["reports"][0]["model"]["first_wet"] == "2024-09-10T16:00:00+07:00"
    # The block refuses outcomes or counts that do not follow from its figures, and a point at low confidence.
    for change, needle in (
        (lambda value: value["reports"][0].__setitem__("consistency", "model_dry"), "does not follow"),
        (lambda value: value["counts"]["all"].__setitem__("consistent", 0), "tallies"),
        (lambda value: value["reports"][2].__setitem__("point", {"lat": 20.44, "lon": 99.88}), "a point is given exactly"),
        (lambda value: value["use_rule"].__setitem__("en", "A consistency check."), "never used to tune"),
        (lambda value: value.__setitem__("status", "observed"), "reported (anecdotal, not surveyed)"),
        (lambda value: value["reports"][9].__setitem__("consistency", "consistent"), "does not follow"),  # ms-c2-12, a class
        (lambda value: value["counted"].__setitem__("statements", 21), "counted"),
        (lambda value: value["counts_by_statement"].__setitem__("mixed", 0), "once"),
        (lambda value: value["shared_statements"].pop(), "more than one place"),
        (lambda value: value["reports"][5].__setitem__("statement_id", "ms-c2-09"), "first place record"),  # ms-c2-08 under ms-c2-09
        (lambda value: value["likely_causes"][1]["text"].__setitem__("en", "Town ground: one point sits above the encoded range."), "rebuilt causes differ"),
        (lambda value: value["likely_causes"][0]["figures"].__setitem__("located_numbers", 12), "rebuilt causes differ"),
        (lambda value: value["assumptions"]["th"].pop(), "assumptions"),
    ):
        broken = copy.deepcopy(built)
        change(broken)
        assert any(needle in line for line in rd.block_problems(broken)), needle


# --- The committed manifest -------------------------------------------------------------------------------------


def test_manifest_carries_the_reported_depths_in_lane_rep_with_the_model_named_as_scenario_values(manifest: dict, block: dict) -> None:
    assert evidence_problems(manifest) == [] and reported_depth_problems(manifest) == [] and rd.block_problems(block) == []
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    assert schema_problems(manifest, schema) == []
    evidence = next(item for item in manifest["evidence_blocks"] if item["id"] == "reported_depths")
    assert (evidence["lane"], evidence["temporal_relation"], evidence["covers"]) == ("REP", "post_event_compilation", ["reported_depths"])
    assert evidence["scenario_fields"] == ["reported_depths.reports[].model"] and "not surveyed" in evidence["evidence_tier"]
    assert "never a validation" in evidence["note"] and "never used to tune" in evidence["note"]
    assert block["status"] == "reported (anecdotal, not surveyed)" and block["lane"] == "REP" and block["confidence"] == "low"
    assert block["source_timestamp"] == evidence["source_timestamp"] == "reports published 2024-09-10T05:32:00+07:00/2024-09-13T11:32:00+07:00; compiled 2026-10-03"
    # The block names the data file it was baked from, by hash; the file is among the receipt's inputs.
    assert block["data_file"] == {"path": "outputs/mae_sai_reported_depths_2024.json", "sha256": hashlib.sha256(DATA.read_bytes()).hexdigest()}
    assert any(row["path"] == block["data_file"]["path"] and row["sha256"] == block["data_file"]["sha256"] for row in manifest["input_sha256"])
    # It is a consistency check, never a validation, and never used for tuning: the block, the assumptions, the tuning
    # disclosure and its recorded rule say so.
    assert "never a validation" in block["use_rule"]["en"] and "never used to tune" in block["use_rule"]["en"]
    assert any("never used to tune the model" in line and "never a validation" in line for line in manifest["assumptions"])
    item = next(entry for entry in manifest["exploratory_knowledge"]["items"] if entry["id"] == "reported-depths-2024")
    assert (item["relation"], item["known_during_tuning"]) == ("computed_after_keyframes_final", False)
    assert "Recorded rule: the reported depths are never used to tune the model." in item["statement"]
    assert manifest["exploratory_knowledge"]["rule"].endswith("The reported depths (news, not surveyed) are never used to tune the model.")
    row = next(entry for entry in manifest["publication_eligibility"]["inputs"] if entry["id"] == "reported-depths")
    assert row["shown"] is True and "paraphrased" in row["licence"]
    text = json.dumps(block, ensure_ascii=False)
    assert not re.search(r"[Vv]alidated|[Cc]onfirm|fpps|action_class", text)


def test_manifest_reports_follow_the_data_file_and_the_counts_are_the_measured_ones(document: dict, block: dict) -> None:
    source = {report["id"]: report for report in document["reports"]}
    assert [report["id"] for report in block["reports"]] == list(source)
    for report in block["reports"]:
        original = source[report["id"]]
        assert report["place"] == original["place"] and report["point"] == original["point"] and report["source"]["url"] == original["source"]["url"]
        assert report["depth"]["statement"] == original["depth"]["statement"] and report["time"]["text"] == original["time"]["text"]
        assert (report["model"] is not None) == (original["point"] is not None and original["time"]["window_start"] is not None)
    outcome = {report["id"]: report["consistency"] for report in block["reports"]}
    # The located reports of the morning and midday of 10 Sep read dry: the assumed level is at most 0.1 m until 18:15.
    for name in ("ms-c2-01", "ms-c2-02", "ms-c2-07", "ms-c2-08", "ms-c2-09", "ms-c2-12"):
        assert outcome[name] == "model_dry", name
        assert next(report for report in block["reports"] if report["id"] == name)["model"]["window_max_stage_m"] <= 0.1
    # One number reaches its lower bound; two storey or body references are wet in the model, with no depth compared
    # (Piyaphon's "chest-deep" beside 0.78 m of modelled water is wet, not consistent).
    assert (outcome["ms-c2-15"], outcome["ms-c2-19"], outcome["ms-c2-22"]) == ("consistent", "model_wet", "model_wet")
    assert (outcome["ms-c2-14"], outcome["ms-c2-18"], outcome["ms-c2-20"]) == ("model_dry", "model_dry", "model_dry")
    assert block["counts"] == {
        "numeric": {"consistent": 1, "model_shallower": 0, "model_wet": 0, "model_dry": 6, "not_comparable": 5},
        "qualitative": {"consistent": 0, "model_shallower": 0, "model_wet": 2, "model_dry": 3, "not_comparable": 4},
        "all": {"consistent": 1, "model_shallower": 0, "model_wet": 2, "model_dry": 9, "not_comparable": 9},
    }
    assert block["counts_within_tolerance"]["all"] == {"consistent": 2, "model_shallower": 3, "model_wet": 4, "model_dry": 3, "not_comparable": 9}
    # 21 place records from 17 statements in 14 articles; counted once per statement, Thai PBS's three places differ.
    assert block["counted"] == {"place_records": 21, "statements": 17, "articles": 14}
    assert block["counts_by_statement"] == {"consistent": 0, "model_shallower": 0, "model_wet": 2, "model_dry": 6, "not_comparable": 8, "mixed": 1}
    assert block["shared_statements"] == [
        {"statement_id": "ms-c2-07", "reports": ["ms-c2-07", "ms-c2-08", "ms-c2-09"], "outcomes": ["model_dry"] * 3},
        {"statement_id": "ms-c2-14", "reports": ["ms-c2-14", "ms-c2-15", "ms-c2-16"], "outcomes": ["model_dry", "consistent", "not_comparable"]},
    ]
    assert block["assumptions"]["en"] == json.loads(DATA.read_text(encoding="utf-8"))["assumptions"]
    # Ko Sai's point falls on the mapped river channel: it is read at the nearest cell outside it.
    ko_sai = next(report for report in block["reports"] if report["id"] == "ms-c2-07")["model"]
    assert ko_sai["cell"] == "nearest_out_of_channel" and 0 < ko_sai["moved_m"] <= 150
    # The likely causes are said plainly, without judging the model or the reports.
    assert [cause["id"] for cause in block["likely_causes"]] == ["timing", "surface_model", "local_drainage", "location"]
    # Every count they state is the reports' own, recounted here from the place records (not from the bake's helper).
    causes = {cause["id"]: cause for cause in block["likely_causes"]}
    located = [report for report in block["reports"] if report["model"]]
    early = [report for report in located if report["model"]["window_max_stage_m"] <= 0.1]
    numbers = [report for report in located if report["depth"]["basis"] == "numeric"]
    early_numbers = [report for report in early if report["depth"]["basis"] == "numeric"]
    assert (len(numbers), len(early_numbers), len(located) - len(numbers), len(early) - len(early_numbers)) == (7, 5, 5, 1)
    assert all(report["consistency"] == "model_dry" for report in early)
    assert causes["timing"]["text"]["en"].startswith("Timing: 5 of the 7 located numbers and 1 of the 5 located storey or body references")
    assert "until 10 Sep 18:15 ICT" in causes["timing"]["text"]["en"] and "all 6 of these read dry" in causes["timing"]["text"]["en"]
    points = {(report["point"]["lat"], report["point"]["lon"]): report["model"]["height_above_channel_m"] for report in located}
    above = sorted(report["id"] for report in located if report["model"]["height_above_channel_m"] is None)
    assert above == ["ms-c2-18", "ms-c2-20"] and len(points) == 9  # The school and Wat Tham Pha Chom: two distinct points.
    raised = sum(1 for height in points.values() if height is not None and height >= 2.0)
    assert f"{raised} of the 9 report points sit 2 m or more above their channel, and 2 sit above the highest level" in causes["surface_model"]["text"]["en"]
    assert "2 จุดอยู่สูงกว่าระดับสูงสุดที่แบบจำลองบันทึกไว้" in causes["surface_model"]["text"]["th"]
    assert "2 statements each name several communities" in causes["location"]["text"]["en"]
    for cause in block["likely_causes"]:
        assert not re.search(r"wrong|too (low|high|shallow|deep)|validat|confirm", cause["text"]["en"], re.IGNORECASE)
        assert re.search(r"[฀-๿]", cause["text"]["th"])


def test_contract_refuses_reported_depths_in_another_lane_or_without_named_model_fields(manifest: dict) -> None:
    def broken(change) -> list[str]:
        value = copy.deepcopy(manifest)
        change(value)
        return reported_depth_problems(value)

    evidence = next(index for index, item in enumerate(manifest["evidence_blocks"]) if item["id"] == "reported_depths")
    assert any("lane REP must cover" in line for line in broken(lambda value: value["evidence_blocks"][evidence].__setitem__("lane", "OBS")))
    assert any("scenario fields" in line for line in broken(lambda value: value["evidence_blocks"][evidence].pop("scenario_fields")))
    assert any("tallies" in line for line in broken(lambda value: value["reported_depths"]["counts"]["numeric"].__setitem__("consistent", 7)))
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    for change, needle in (
        (lambda value: value["reported_depths"]["use_rule"].__setitem__("en", "Validated by news; never used to tune; never a validation."), "reported_depths/use_rule/en"),
        (lambda value: value["reported_depths"].__setitem__("status", "surveyed"), "reported_depths/status"),
        (lambda value: value["reported_depths"]["likely_causes"][0]["text"].__setitem__("en", "The model is wrong in town."), "reported_depths/likely_causes/0/text/en"),
        (lambda value: value["reported_depths"]["reports"][0].__setitem__("consistency", "validated"), "reported_depths/reports/0/consistency"),
    ):
        value = copy.deepcopy(manifest)
        change(value)
        assert any(line.startswith(needle) for line in schema_problems(value, schema)), needle


def test_reported_windows_are_placed_in_time_inside_the_replay() -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("bake_for_dates", ROOT / "scripts" / "build_mae_sai_flood_timeline.py")
    sys.path.insert(0, str(ROOT / "scripts"))
    bake = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bake)
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    dates = [path for path, _ in bake.replay_dates(manifest) if path.startswith("reported_depths.")]
    assert len(dates) == 2 * 20  # Every report with a window, both ends (ms-c2-24 gives no time).
    assert bake.dated_after_replay(manifest) == []
    late = copy.deepcopy(manifest)
    late["reported_depths"]["reports"][0]["time"]["window_end"] = "2024-10-22T12:00:00+07:00"
    assert any(line.startswith("reported_depths.reports[ms-c2-01]") for line in bake.dated_after_replay(late))


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("The modelled depth at Mueang Daeng is confirmed by reports", "report_confirmation"),
        ("The model is validated by news", "validation_as_agreement"),
        ("Depths confirmed by news reports", "report_confirmation"),
        ("Residents' reports confirm the modelled peak", "report_confirmation"),
        ("Confirmed depth at Sai Lom Joy: 2 m", "report_confirmation"),
        ("รายงานข่าวยืนยันความลึกของแบบจำลอง", "report_confirmation"),
        ("ความลึกยืนยันโดยรายงานข่าว", "report_confirmation"),
    ],
)
def test_the_wording_lint_refuses_a_confirmation_or_a_validation_by_reports(text: str, rule: str) -> None:
    from floodguard.wording_lint import find_violations, load_rules

    rules = load_rules(ROOT / "apps" / "web" / "src" / "lib" / "replay-wording-rules.json")
    assert rule in {finding.rule for finding in find_violations(text, rules)}, text
    # The wording the page uses passes.
    for allowed in ("Reported (anecdotal, not surveyed): the model reaches the reported lower bound, so it is consistent with the report.",
                    "A consistency check of anecdotal reports, never a validation; the reports are never used to tune the model.",
                    "the owners confirmed the rights record on 2 Oct 2026", "Tambon ต.เวียงพางคำ is confirmed by PRD."):
        assert find_violations(allowed, rules) == [], allowed
