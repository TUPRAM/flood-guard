"""Tests for the Mae Sai replay's export pack (``floodguard.replay_exports``).

The first half runs the pure writers on a small synthetic replay. The second half reads the committed pack under
``apps/web/public/studies/mae-sai-2024-timeline/<revision>/exports`` and checks it against the manifest that
lists it, the source road file, the two parity fixtures and the shared wording rules. Nothing here needs the
external data; the real bake's byte-for-byte check lives in ``tests/test_bake_receipt.py``.
"""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
import pytest

from floodguard import replay_exports as exports
from floodguard.evacuation_access import NEVER_LOST, NO_BASELINE_ACCESS
from floodguard.flood_timeline import road_state
from floodguard.shelter_set_comparison import shelter_set_summary
from floodguard.wording_lint import find_violations, load_rules

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
RULES = load_rules(WEB / "src" / "lib" / "replay-wording-rules.json")
THAI = re.compile(r"[฀-๿]")
REQUIRED_FIELDS = ("title", "title_th", "tier", "tier_th", "operational_status", "confidence_class", "confidence_reason", "confidence_reason_th",
                   "lanes", "source_timestamp", "generated_at", "generated_by", "study", "accepted", "licence", "licence_th", "attribution",
                   "licence_inputs", "not_included", "not_included_th", "assumption_1", "assumption_1_th", "input_receipt", "git_commit")
EVENT_START = "2024-09-09T00:00:00+07:00"
SOURCES = [
    {"id": "copernicus-dem", "name": "Copernicus DEM GLO-30", "licence": "Copernicus DEM licence (free, attribution)", "attribution": "DLR and Airbus"},
    {"id": "osm", "name": "OpenStreetMap roads and candidate facilities", "licence": "ODbL 1.0", "attribution": "© OpenStreetMap contributors"},
    {"id": "worldpop", "name": "WorldPop Thailand 2020", "licence": "CC BY 4.0", "attribution": "WorldPop"},
    {"id": "cod-ab", "name": "HDX Thailand COD-AB", "licence": "CC BY-IGO", "attribution": "OCHA / HDX"},
    {"id": "viirs", "name": "VIIRS daily flood maps", "licence": "No licence stated by the provider; attribution given", "attribution": "NOAA / GMU"},
    {"id": "hii-rain", "name": "HII rain gauges", "licence": "CC BY-NC", "attribution": "HII"},
    {"id": "reported-shelters", "name": "Shelters reported in use in September 2024", "attribution": "FloodGuard desk research",
     "licence": "Facts with citations; OSM-derived coordinates © OpenStreetMap contributors (ODbL)."},
]
INPUT_PATHS = (exports._ROADS, exports._EDGES, exports._NODES, exports._ADMIN, exports._FACILITIES, exports._REPORTED, exports._OSM_PBF, *exports._DEM)


def synthetic_context(**changes) -> exports.ExportContext:
    """A replay small enough to check by hand: three ways, two subdistricts, six resident nodes, four candidates."""
    stages = [0.0, 0.0, 0.2, 0.6, 1.5, 3.5, 3.5, 2.0, 0.9, 0.4, 0.1, 0.0]
    candidates = [
        {"id": "C001", "kind": "school", "name": "โรงเรียนบ้านตัวอย่าง", "lon": 99.88, "lat": 20.43, "source": "OSM way/1", "capacity_est": 120,
         "freeboard_m": 1.2, "high_ground": False, "eligible": True, "ineligible_reasons": [], "m": True},
        {"id": "C002", "kind": "worship", "name": "", "lon": 99.89, "lat": 20.44, "source": "OSM node/2", "capacity_est": None,
         "freeboard_m": None, "high_ground": True, "eligible": True, "ineligible_reasons": [], "m": True},
        {"id": "C003", "kind": "government", "name": "=SUM(A1)", "lon": 99.87, "lat": 20.42, "source": "OSM way/3", "capacity_est": 40,
         "freeboard_m": -0.4, "high_ground": False, "eligible": False, "ineligible_reasons": ["floods_or_under_freeboard_at_peak"], "m": True},
        {"id": "C004", "kind": "community", "name": "Hall", "lon": 99.9, "lat": 20.45, "source": "OSM way/4", "capacity_est": 60,
         "freeboard_m": 2.0, "high_ground": False, "eligible": True, "ineligible_reasons": [], "m": True},
    ]
    bound = lambda capacity, load, served: {"capacity": capacity, "load": load, "served": served, "overflow": 500 - served}  # noqa: E731
    context = exports.ExportContext(
        study_id="mae-sai-2024-flood-timeline", revision="r9", generated_at="2026-10-02T15:00:00+07:00",
        generated_by="scripts/build_mae_sai_flood_timeline.py",
        receipt_path="docs/mae_sai_timeline_r9_input_receipt.json", repo_folder="apps/web/public/studies/x/r9/exports",
        inputs=[{"root": "repo" if path.startswith("outputs/") else "external", "path": path, "bytes": 10 + index,
                 "sha256": hashlib.sha256(path.encode()).hexdigest()} for index, path in enumerate(INPUT_PATHS)],
        sources=SOURCES, hourly_stages=stages, event_start=EVENT_START, osm_extract_date="2026-07-09", reported_compiled="2026-09-27",
        impassable_depth_m=0.3, road_classes=("trunk", "primary", "residential"),
        ways=[
            {"road_id": "200", "road_name": "ถนนพหลโยธิน", "road_class": "trunk", "bridge_flag": True, "tambon_id": "T1", "length_m": 240.4,
             "pieces": [(0.2, 1.0, True), (5.0, 1.0, True)],
             # A way dict may still carry the source file's legacy columns; the writer must not copy them.
             "road_disruption_probability_0_1": 0.9, "candidate_status": "candidate_closed", "confidence_class": "low"},
            {"road_id": "30", "road_name": "", "road_class": "residential", "bridge_flag": False, "tambon_id": "T2", "length_m": 80.0,
             "pieces": [(4.0, 1.0, True), (None, 1.0, True)]},
            {"road_id": "1000", "road_name": "Soi 1", "road_class": "residential", "bridge_flag": False, "tambon_id": "T9", "length_m": 60.0,
             "pieces": [(0.1, 0.5, False)]},
        ],
        tambons=[{"id": "T1", "en": "Mae Sai", "th": "แม่สาย"}, {"id": "T2", "en": "Ko Chang", "th": "เกาะช้าง"}],
        node_tambon=np.array([1, 1, 1, 2, 2, 0], dtype=np.uint8),
        node_population=np.array([10.5, 20.25, 30.0, 40.0, 5.5, 99.0]),
        cut_codes={"reported_2024": np.array([4, NEVER_LOST, NO_BASELINE_ACCESS, 12, 30, 1], dtype=np.uint8),
                   "plan_2": np.array([NO_BASELINE_ACCESS, 8, 9, NEVER_LOST, 70, 1], dtype=np.uint8)},
        level_step_m=0.05, knee_k=2, candidates=candidates,
        plan=[{"candidate_id": "C004", "marginal_demand": 300.44, "cumulative_demand": 300.44, "cumulative_share": 0.6009, "late_cumulative_share": 0.4},
              {"candidate_id": "C001", "marginal_demand": 99.96, "cumulative_demand": 400.4, "cumulative_share": 0.8008, "late_cumulative_share": 0.5},
              {"candidate_id": "C002", "marginal_demand": 12.0, "cumulative_demand": 412.4, "cumulative_share": 0.8248, "late_cumulative_share": 0.5}],
        capacitated={"demand_people": 500, "capacity_basis": {"estimate": "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified", "unknown": "unknown"},
                     "plan": [{"candidate_id": "C001", "capacity_est": 120, "capacity_basis": "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified",
                               "upper_capacity_basis": "estimate", "within_reach": 180, "lower": bound(120, 120, 120), "upper": bound(120, 120, 120)},
                              {"candidate_id": "C002", "capacity_est": None, "capacity_basis": "unknown", "upper_capacity_basis": "kind_median",
                               "within_reach": 260, "lower": bound(0, 0, 120), "upper": bound(76, 60, 180)}]},
        robust_core=["C004"],
        reported=[{"id": "R01", "name_en": "Wat Example shelter", "name_th": "ศูนย์พักพิงวัดตัวอย่าง", "type": "temple", "tambon": "แม่สาย",
                   "lon": 99.8843199, "lat": 20.4265331, "location_method": "osm_feature", "location_confidence": "high", "role": "shelter",
                   "first_use": "2024-09-11", "in_access_set": True, "access_set_note": "Reported in use by 15 Sep.", "evidence_strength": "official",
                   "sources": [{"url": "https://example.org/a"}, {"url": "https://example.org/b"}],
                   "reported_capacity_or_occupancy": "Occupancy: 341. A municipal list gives about 200.", "period_used": "34 people at 01:00",
                   "model_check": {"m": True, "floods_at_modelled_peak": False, "freeboard_m": 3.85}},
                  {"id": "R02", "name_en": "Village hall", "name_th": "ศาลาหมู่บ้าน", "type": "other", "tambon": "เกาะช้าง", "lon": None, "lat": None,
                   "location_method": "not_located", "location_confidence": "low", "role": "shelter", "first_use": "2024-09-15 or earlier",
                   "in_access_set": True, "access_set_note": "Not located.", "evidence_strength": "media", "sources": [], "model_check": None}],
        peak_stage_m=3.5, walk_limit_m=2000.0, freeboard_m=0.5, snap_max_m=400.0)
    return replace(context, **changes)


def pack(context: exports.ExportContext | None = None) -> dict[str, exports.ExportFile]:
    return {file.id: file for file in exports.export_pack(context or synthetic_context())}


def header_texts(file: exports.ExportFile) -> list[tuple[str, str]]:
    """Every piece of header text of a file, as ``(source, text)`` for the wording lint (data rows are not copy)."""
    if file.media_type == "text/csv":
        fields, _, _ = exports.read_export_csv(file.data)
        lines = file.data.decode("utf-8-sig").split("\n")
        return [(f"{file.name} header", "\n".join(lines[:file.header_lines + 1])), *((f"{file.name} {key}", value) for key, value in fields.items())]
    if file.media_type == "application/geo+json":
        metadata = json.loads(file.data)["metadata"]
        return [(f"{file.name} metadata", json.dumps(metadata, ensure_ascii=False))]
    return [(file.name, file.data.decode("utf-8"))]


def ids(findings) -> list[str]:
    return sorted({finding.rule for finding in findings})


# --- Hours ---------------------------------------------------------------------------------------------------


def test_hour_local_time_counts_from_the_replay_origin_in_local_time() -> None:
    assert exports.hour_local_time(0, EVENT_START) == "2024-09-09T00:00:00+07:00"
    assert exports.hour_local_time(46, EVENT_START) == "2024-09-10T22:00:00+07:00"
    assert exports.hour_local_time(263, EVENT_START) == "2024-09-19T23:00:00+07:00"


def test_impassable_hours_follow_the_road_state_rule_piece_by_piece() -> None:
    stages = [0.0, 0.2, 0.49, 0.5, 0.51, 3.5, 0.5, 0.3, 0.0]
    mask = exports.impassable_hours([(0.2, 1.0, True)], stages)
    assert mask.tolist() == [road_state(0.2, stage, 1.0) == "impassable" for stage in stages]
    assert mask.tolist() == [False, False, False, True, True, True, True, False, False]  # 0.3 m of depth is impassable.
    # A depth factor below 1 delays the first impassable hour: depth = k * (stage - h).
    assert exports.impassable_hours([(0.2, 0.5, True)], stages).tolist() == [False, False, False, False, False, True, False, False, False]
    # A way is impassable when any of its pieces is; a piece outside the model, or without a usable height, never counts.
    both = exports.impassable_hours([(3.0, 1.0, True), (0.2, 1.0, True), (0.0, 1.0, False), (None, 1.0, True)], stages)
    assert both.tolist() == mask.tolist()
    assert not exports.impassable_hours([(0.0, 1.0, False), (None, 1.0, True)], stages).any()
    assert not exports.impassable_hours([], stages).any()


def test_impassable_interval_gives_first_hour_passable_again_hour_and_count() -> None:
    interval = exports.impassable_interval
    assert interval(np.array([False, False, True, True, False])) == (2, 4, 2)
    assert interval(np.array([False, False, False])) == (None, None, 0)  # Never impassable.
    assert interval(np.array([False, True, True])) == (1, None, 2)  # Still impassable at the last replay hour.
    assert interval(np.array([True, False, False])) == (0, 1, 1)
    # Two separate spells: the passable-again hour follows the last one, and the count shows the gap.
    assert interval(np.array([False, True, False, True, False])) == (1, 4, 2)


# --- Tables --------------------------------------------------------------------------------------------------


def test_road_rows_are_one_per_way_with_hours_and_without_the_legacy_columns() -> None:
    context = synthetic_context()
    rows = exports.road_inundation_rows(context.ways, context.hourly_stages, context.tambons, EVENT_START)
    assert [row["road_id"] for row in rows] == ["30", "200", "1000"]  # Numeric order of the way ids.
    keys = [column.key for column in exports.ROAD_COLUMNS]
    assert all(list(row) == keys for row in rows)
    assert not set(keys) & set(exports.LEGACY_ROAD_COLUMNS)
    trunk = rows[1]
    assert (trunk["road_name"], trunk["road_class"], trunk["bridge_flag"], trunk["length_m"]) == ("ถนนพหลโยธิน", "trunk", True, 240)
    assert (trunk["tambon_id"], trunk["tambon_name_th"], trunk["tambon_name_en"]) == ("T1", "แม่สาย", "Mae Sai")
    # Stage reaches 0.5 m (0.2 m + 0.3 m of depth) at hour 3 and is below it again from hour 9.
    assert (trunk["modelled_first_impassable_hour"], trunk["modelled_passable_again_hour"], trunk["modelled_impassable_hours"]) == (3, 9, 6)
    assert trunk["modelled_first_impassable_local_time"] == "2024-09-09T03:00:00+07:00"
    assert trunk["modelled_passable_again_local_time"] == "2024-09-09T09:00:00+07:00"
    high = rows[0]  # 4.0 m above the channel: never 0.3 m deep at a 3.5 m peak.
    assert high["in_model_area"] is True and high["modelled_first_impassable_hour"] is None and high["modelled_impassable_hours"] == 0
    assert high["modelled_first_impassable_local_time"] is None and high["modelled_passable_again_hour"] is None
    outside = rows[2]  # Outside the model: unknown, not "never"; and a subdistrict the table does not know stays blank.
    assert outside["in_model_area"] is False and outside["modelled_first_impassable_hour"] is None
    assert (outside["tambon_id"], outside["tambon_name_th"]) == ("T9", "")


def test_access_rows_count_each_set_against_its_own_baseline_per_subdistrict_and_hour() -> None:
    context = synthetic_context()
    rows = exports.access_loss_rows(context.tambons, context.node_tambon, context.node_population, context.cut_codes,
                                    context.hourly_stages, EVENT_START, 0.05, "plan_2")
    assert len(rows) == 2 * len(context.hourly_stages)
    assert [column.key for column in exports.access_columns(2)] == list(rows[0])
    first = [row for row in rows if row["tambon_id"] == "T1"]
    assert [row["replay_hour"] for row in first] == list(range(12))
    assert {row["residents"] for row in first} == {60.8}  # 10.5 + 20.25 + 30.0, to one decimal; the node without a subdistrict is not counted.
    # Reported set in T1: baseline = the two nodes with a code other than 255; the 10.5 node is lost from level 4 (0.2 m).
    assert {row["reported_2024_within_reach_before_flood"] for row in first} == {30.8}
    assert [row["reported_2024_lost_access"] for row in first] == [0.0, 0.0, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 0.0, 0.0]
    # Plan in T1: baseline 50.25; codes 8 (0.4 m) and 9 (0.45 m).
    assert {row["knee_plan_within_reach_before_flood"] for row in first} == {50.2}
    assert [row["knee_plan_lost_access"] for row in first] == [0.0, 0.0, 0.0, 50.2, 50.2, 50.2, 50.2, 50.2, 50.2, 20.2, 0.0, 0.0]
    assert [row["modelled_stage_m"] for row in first] == context.hourly_stages
    # The twin module that the page's parity fixture uses gives the same counts for each subdistrict.
    for position, tambon in enumerate(context.tambons, start=1):
        mask = context.node_tambon == position
        for label, set_id in (("reported_2024", "reported_2024"), ("knee_plan", "plan_2")):
            for hour, stage in enumerate(context.hourly_stages):
                summary = shelter_set_summary(context.node_population, context.cut_codes[set_id], stage, context.hourly_stages, mask=mask)
                row = next(row for row in rows if row["tambon_id"] == tambon["id"] and row["replay_hour"] == hour)
                assert row[f"{label}_within_reach_before_flood"] == round(summary.baseline, 1)
                assert row[f"{label}_lost_access"] == round(summary.lost, 1)
    with pytest.raises(exports.ReplayExportError, match="cut codes of the knee_plan set"):
        exports.access_loss_rows(context.tambons, context.node_tambon, context.node_population, context.cut_codes, context.hourly_stages,
                                 EVENT_START, 0.05, "plan_7")
    with pytest.raises(exports.ReplayExportError, match="one value per node"):
        exports.access_loss_rows(context.tambons, context.node_tambon[:3], context.node_population, context.cut_codes, context.hourly_stages,
                                 EVENT_START, 0.05, "plan_2")


def test_plan_tables_follow_the_rankings_and_never_publish_an_occupancy_or_listed_capacity() -> None:
    context = synthetic_context()
    plan = exports.plan_rows(context)
    assert [(row["rank"], row["candidate_id"], row["in_knee_plan"], row["in_robust_core"]) for row in plan] == [
        (1, "C004", True, True), (2, "C001", True, False), (3, "C002", False, False)]
    assert (plan[0]["added_flooded_home_residents"], plan[1]["cumulative_flooded_home_residents"], plan[1]["cumulative_share"]) == (300.4, 400.4, 0.8008)
    assert (plan[2]["estimated_capacity"], plan[2]["capacity_basis"]) == (None, "unknown")
    assert plan[1]["capacity_basis"] == "OSM footprint x 0.5 / 3.5 m2 (Sphere), unverified"
    capacity = exports.capacitated_rows(context)
    assert [(row["rank"], row["candidate_id"]) for row in capacity] == [(1, "C001"), (2, "C002")]
    assert (capacity[1]["lower_capacity"], capacity[1]["lower_load"], capacity[1]["lower_cumulative_fit"], capacity[1]["lower_overflow"]) == (0, 0, 120, 380)
    assert (capacity[1]["upper_capacity"], capacity[1]["upper_load"], capacity[1]["upper_cumulative_fit"], capacity[1]["upper_overflow"]) == (76, 60, 180, 320)
    reported = exports.reported_rows(context)
    assert [row["site_id"] for row in reported] == ["R01", "R02"]
    assert reported[0]["source_urls"] == "https://example.org/a https://example.org/b"
    assert (reported[0]["modelled_floods_at_peak"], reported[0]["modelled_freeboard_m"], reported[0]["counted_in_access_set"]) == (False, 3.85, True)
    assert (reported[1]["lat"], reported[1]["modelled_in_model_area"], reported[1]["modelled_floods_at_peak"]) == (None, None, None)
    text = json.dumps(reported, ensure_ascii=False)
    assert "341" not in text and "about 200" not in text and "34 people" not in text  # No occupancy count and no listed capacity.
    assert not any("occupancy" in column.key or "period" in column.key for column in exports.REPORTED_COLUMNS)


def test_site_features_hold_every_candidate_and_every_located_reported_site() -> None:
    features = exports.site_features(synthetic_context())
    assert [feature["properties"]["id"] for feature in features] == ["C001", "C002", "C003", "C004", "R01"]  # R02 has no coordinates.
    keys = [column.key for column in exports.SITE_FIELDS]
    assert all(list(feature["properties"]) == keys and feature["geometry"]["type"] == "Point" for feature in features)
    by_id = {feature["properties"]["id"]: feature["properties"] for feature in features}
    assert (by_id["C004"]["coverage_rank"], by_id["C004"]["in_knee_plan"], by_id["C004"]["in_robust_core"], by_id["C004"]["capacity_rank"]) == (1, True, True, None)
    assert (by_id["C002"]["coverage_rank"], by_id["C002"]["in_knee_plan"], by_id["C002"]["capacity_rank"]) == (3, False, 2)
    assert (by_id["C003"]["modelled_eligible"], by_id["C003"]["modelled_ineligible_reasons"], by_id["C003"]["modelled_floods_at_peak"]) == (
        False, "floods_or_under_freeboard_at_peak", True)
    assert (by_id["C002"]["modelled_floods_at_peak"], by_id["C001"]["modelled_floods_at_peak"]) == (False, False)
    assert (by_id["R01"]["site_set"], by_id["R01"]["counted_in_access_set"], by_id["R01"]["modelled_eligible"]) == ("reported_2024", True, None)
    assert features[0]["geometry"]["coordinates"] == [99.88, 20.43]


def test_verification_sheet_lists_the_eligible_candidates_with_the_checker_columns_empty() -> None:
    context = synthetic_context()
    rows = exports.sheet_rows(context)
    assert [row["candidate_id"] for row in rows] == ["C001", "C002", "C004"]  # C003 is not eligible.
    whitelist = ["candidate_id", "kind", "name", "lat", "lon", "estimated_capacity", "capacity_basis",
                 "usable_as_shelter", "verified_capacity", "access_notes", "checked_by_role", "checked_on"]
    assert [column.key for column in exports.SHEET_COLUMNS] == whitelist
    assert all(list(row) == whitelist for row in rows)
    assert all(row[key] is None for row in rows for key in whitelist[7:])  # No result is implied.
    assert (rows[1]["estimated_capacity"], rows[1]["capacity_basis"]) == (None, "unknown")
    fingerprint = exports.candidate_set_sha256(context.candidates)
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert exports.candidate_set_sha256(list(reversed(context.candidates))) == fingerprint  # Order does not matter.
    moved = [{**site, "lon": site["lon"] + (0.001 if site["id"] == "C001" else 0)} for site in context.candidates]
    assert exports.candidate_set_sha256(moved) != fingerprint
    renamed = [{**site, "name": "another name"} for site in context.candidates]
    assert exports.candidate_set_sha256(renamed) == fingerprint  # A name is not what a check is matched on.
    not_eligible = [{**site, "eligible": site["id"] != "C004"} for site in context.candidates]
    assert exports.candidate_set_sha256(not_eligible) != fingerprint


# --- Files: headers, encoding and format -----------------------------------------------------------------------


def test_pack_holds_the_eight_files_with_fixed_names() -> None:
    files = exports.export_pack(synthetic_context())
    assert [file.name for file in files] == [
        "shelter_plan_reported_2024.csv", "shelter_plan_k.csv", "shelter_plan_capacitated.csv", "shelter_sites.geojson",
        "modelled_road_inundation_by_hour.csv", "modelled_access_loss_by_hour.csv", "shelter_candidate_verification_sheet.csv",
        "README_licences.txt"]
    assert [file.rows for file in files] == [2, 3, 2, 5, 3, 24, 3, None]
    for file in files:
        assert not re.search(r"schedule|closure|cut[-_]?off|4009|unosat", file.name, re.IGNORECASE), file.name
        record = file.record("/studies/x/r9/exports/")
        assert record["href"] == f"/studies/x/r9/exports/{file.name}" and record["bytes"] == len(file.data)
        assert record["sha256"] == hashlib.sha256(file.data).hexdigest() and record["licence"] == "ODbL 1.0"
        assert set(record["title"]) == {"en", "th"} and THAI.search(record["title"]["th"]) and not THAI.search(record["title"]["en"])
    assert exports.export_pack(synthetic_context()) == files  # The same data gives the same bytes.


def test_every_csv_is_utf8_with_bom_lf_only_and_starts_with_its_provenance_lines() -> None:
    for file in pack().values():
        if file.media_type != "text/csv":
            continue
        assert file.data.startswith(exports.BOM), file.name  # Excel reads the Thai text only with the byte-order mark.
        assert b"\r" not in file.data, file.name
        lines = file.data.decode("utf-8-sig").split("\n")
        assert lines[-1] == "" and all(line.startswith("#") for line in lines[:file.header_lines]), file.name
        assert lines[0] == f"# floodguard_export,{file.name}"
        assert lines[1].startswith(f"# header_lines,{file.header_lines},")
        assert f"skiprows={file.header_lines}" in lines[1] and f"line {file.header_lines + 1}" in lines[1]
        header = next(csv.reader([lines[file.header_lines]]))
        assert header == [column.label for column in file.columns]
        assert len(lines) == file.header_lines + 1 + file.rows + 1
        fields, keys, rows = exports.read_export_csv(file.data)
        assert keys == [column.key for column in file.columns] and len(rows) == file.rows
        assert int(fields["header_lines"]) == file.header_lines


def test_every_column_header_is_bilingual() -> None:
    tables = (exports.ROAD_COLUMNS, exports.access_columns(8), exports.PLAN_COLUMNS, exports.CAPACITATED_COLUMNS, exports.REPORTED_COLUMNS,
              exports.SHEET_COLUMNS, exports.SITE_FIELDS)
    for columns in tables:
        keys = [column.key for column in columns]
        assert len(set(keys)) == len(keys)
        for column in columns:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", column.key), column.key
            assert THAI.search(column.th) and not THAI.search(column.en) and column.en, column.key
            assert column.label == f"{column.key} ({column.th})"
            # No letter of the Buddhist era goes without its CE year.
            assert not re.search(r"25[67]\d(?! \(20\d\d\))", column.th), column.th


def test_every_file_header_carries_the_evidence_fields() -> None:
    context = synthetic_context()
    digest = exports.input_set_sha256(context.inputs)
    for file in pack(context).values():
        if file.media_type == "text/csv":
            fields = exports.read_export_csv(file.data)[0]
        elif file.media_type == "application/geo+json":
            fields = json.loads(file.data)["metadata"]
        else:
            text = file.data.decode("utf-8")
            fields = dict(re.findall(r"^# ([a-z0-9_]+): (.*)$", text, re.MULTILINE))
            assert text.startswith("# floodguard_export: README_licences.txt\n# title: ")
        for key in REQUIRED_FIELDS:
            assert fields.get(key), f"{file.name} lacks {key}"
        assert fields["tier"] == exports.EXPORT_TIER and fields["tier_th"] == exports.EXPORT_TIER_TH
        assert fields["operational_status"] == "non_operational" and fields["confidence_class"] == "low"
        assert fields["generated_at"] == context.generated_at and fields["study"] == "mae-sai-2024-flood-timeline r9"
        assert "accepted_fpps=null" in fields["accepted"] and "accepted_action_class=null" in fields["accepted"]
        assert fields["licence"].startswith("ODbL 1.0") and "© OpenStreetMap contributors" in fields["attribution"]
        assert context.receipt_path in fields["input_receipt"] and f"input_set_sha256={digest}" in fields["input_receipt"]
        assert fields["git_commit"].startswith("null:") and f"{context.repo_folder}/{file.name}" in fields["git_commit"]
        assert set(fields["lanes"].split(", ")) == set(file.lanes)
        assumptions = [key for key in fields if re.fullmatch(r"assumption_\d+", key)]
        assert assumptions and all(THAI.search(fields[f"{key}_th"]) for key in assumptions)
        if file.id != "readme_licences":
            for part in fields["input_sha256"].split("; "):
                location, sha256 = part.rsplit("=", 1)
                root, path = location.split(":", 1)
                assert {"root": root, "path": path, "sha256": sha256} in [{key: row[key] for key in ("root", "path", "sha256")} for row in context.inputs]
    assert "T1 scenario (model) replay of a reconstructed 2024 event" in exports.EXPORT_TIER
    assert "not a forecast, not an observed closure record, not an official warning" in exports.EXPORT_TIER
    assert "2567 (2024)" in exports.EXPORT_TIER_TH


def test_header_refuses_an_input_the_receipt_does_not_list() -> None:
    context = synthetic_context()
    with pytest.raises(exports.ReplayExportError, match="not in the input receipt"):
        exports.export_pack(replace(context, inputs=[row for row in context.inputs if row["path"] != exports._ROADS]))
    first = exports.input_set_sha256(context.inputs)
    assert exports.input_set_sha256(list(reversed(context.inputs))) == first
    changed = [{**row, "sha256": "0" * 64} if index == 0 else row for index, row in enumerate(context.inputs)]
    assert exports.input_set_sha256(changed) != first


def test_cells_are_plain_values_and_never_a_spreadsheet_formula() -> None:
    assert [exports._cell(value) for value in (None, True, False, 12, 0.6009, 99.8843199, -0.4, "ถนน")] == [
        "", "yes", "no", "12", "0.6009", "99.8843199", "-0.4", "ถนน"]
    assert exports._cell("=SUM(A1)") == "'=SUM(A1)" and exports._cell("+66 5373") == "'+66 5373" and exports._cell("@cmd") == "'@cmd"
    assert exports._cell("-12.5") == "-12.5" and exports._cell("- note") == "'- note"
    assert exports._cell("two\nlines\r\nhere") == "two lines here"
    with pytest.raises(exports.ReplayExportError, match="finite"):
        exports._cell(float("nan"))
    sheet = pack()["shelter_candidate_verification_sheet"]
    names = {row["candidate_id"]: row["name"] for row in exports.read_export_csv(pack()["shelter_plan_k"].data)[2]}
    assert names["C001"] == "โรงเรียนบ้านตัวอย่าง"
    features = json.loads(pack()["shelter_sites"].data)["features"]
    assert next(f for f in features if f["properties"]["id"] == "C003")["properties"]["name"] == "=SUM(A1)"  # JSON is not a spreadsheet.
    assert sheet.rows == 3
    with pytest.raises(exports.ReplayExportError, match="outside the table"):
        exports.csv_bytes("x.csv", [("title", "t")], exports.ROAD_COLUMNS[:2], [{"road_id": "1", "road_name": "a", "extra": 1}])


def test_geojson_is_a_feature_collection_with_the_metadata_before_the_features() -> None:
    file = pack()["shelter_sites"]
    text = file.data.decode("utf-8")
    assert b"\r" not in file.data and not file.data.startswith(exports.BOM) and text.endswith("\n")
    assert text.startswith('{\n "type": "FeatureCollection",\n "name": "shelter_sites",\n "metadata": {')
    assert text.index('"metadata"') < text.index('"features"')
    document = json.loads(text)
    assert list(document) == ["type", "name", "metadata", "features"] and len(document["features"]) == file.rows == 5
    assert document["metadata"]["floodguard_export"] == "shelter_sites.geojson" and document["metadata"]["crs"].startswith("WGS 84")
    assert [field["key"] for field in document["metadata"]["fields"]] == [column.key for column in exports.SITE_FIELDS]
    assert all(THAI.search(field["th"]) for field in document["metadata"]["fields"])
    pyogrio = pytest.importorskip("pyogrio")
    frame = pyogrio.read_dataframe(io.BytesIO(file.data))  # A GIS reader opens it as it is.
    assert len(frame) == 5 and set(frame["site_set"]) == {"candidate", "reported_2024"}
    with pytest.raises(exports.ReplayExportError, match="differ from the declared fields"):
        exports.geojson_bytes("x.geojson", [], exports.SITE_FIELDS, [{"type": "Feature", "geometry": None, "properties": {"id": "C001"}}])


def test_sheet_and_readme_stop_saying_not_conducted_once_a_check_has_been_imported() -> None:
    blank = pack()
    fields = exports.read_export_csv(blank["shelter_candidate_verification_sheet"].data)[0]
    assert fields["verification_status"] == "not_conducted" and fields["title"].endswith("(no check has been conducted)")
    assert "no check has been conducted for this revision, and no result is implied" in fields["assumption_1"]
    assert "No check has been conducted for this revision." in blank["readme_licences"].data.decode("utf-8")
    checked = pack(synthetic_context(verification_status="conducted"))
    sheet = checked["shelter_candidate_verification_sheet"]
    fields, _, rows = exports.read_export_csv(sheet.data)
    assert fields["verification_status"] == "conducted"
    assert "no check has been conducted" not in sheet.data.decode("utf-8-sig") and "ยังไม่มีการตรวจสอบ" not in fields["title_th"]
    assert "A check has been returned for this revision" in fields["assumption_1"] and THAI.search(fields["assumption_1_th"])
    # The sheet itself stays a blank form: the checked rows are in the manifest, never copied into the download.
    assert all(row[column.key] == "" for row in rows for column in exports.SHEET_CHECKER)
    readme = checked["readme_licences"].data.decode("utf-8")
    assert "A check has been returned for this revision" in readme and "No check has been conducted" not in readme
    for file in checked.values():
        for source, text in header_texts(file):
            assert [finding.describe() for finding in find_violations(text, RULES, source)] == []
    with pytest.raises(exports.ReplayExportError, match="unknown verification status"):
        exports.export_pack(synthetic_context(verification_status="checked"))


def test_readme_lists_every_file_its_hash_its_licence_and_what_is_left_out() -> None:
    files = exports.export_pack(synthetic_context())
    readme = files[-1].data.decode("utf-8")
    assert b"\r" not in files[-1].data and readme.endswith("\n") and not readme.endswith("\n\n")
    for file in files[:-1]:
        assert file.name in readme and file.sha256 in readme and f"{len(file.data):,} bytes" in readme
    for needle in ("Open Database License", "ODbL", "© OpenStreetMap contributors", "CC BY-NC", "UNOSAT/GISTDA product 4009", "byte-order mark",
                   "Number of header lines to", "สัญญาอนุญาต", "ไม่ใช่การพยากรณ์", exports.VERIFICATION_LABEL, exports.VERIFICATION_LABEL_TH,
                   "No check has been conducted", "WorldPop", "No listed capacity from a shelter register"):
        assert needle in readme, needle
    # The rain gauges and the VIIRS maps are named only as things that are left out.
    assert "HII rain gauges" not in readme and "VIIRS daily flood maps: " not in readme


# --- Licence separation and banned columns ------------------------------------------------------------------------


def test_one_licence_lineage_per_file() -> None:
    allowed = {"osm", "worldpop", "cod-ab", "copernicus-dem", "reported-shelters"}
    for file in pack().values():
        assert "osm" in file.sources and set(file.sources) <= allowed, file.name
        assert exports.licence_problems(file.name, file.sources, SOURCES) == []
        assert not set(file.sources) & exports.FORBIDDEN_SOURCES
    problems = exports.licence_problems
    assert problems("x.csv", ["osm", "hii-rain"], SOURCES) == ["x.csv: source hii-rain may not feed an export"]
    assert problems("x.csv", ["osm", "viirs"], SOURCES) == ["x.csv: source viirs may not feed an export"]
    assert problems("x.csv", ["osm", "unosat-4009"], SOURCES) == ["x.csv: source unosat-4009 may not feed an export"]
    assert problems("x.csv", ["osm", "envelope-4009-clip"], SOURCES) == ["x.csv: source envelope-4009-clip may not feed an export"]
    assert problems("x.csv", ["worldpop"], SOURCES) == ["x.csv: an export is OpenStreetMap-derived and must name the osm source"]
    assert problems("x.csv", ["osm", "mystery"], SOURCES) == ["x.csv: unknown source mystery"]
    # A CC BY-SA source beside OpenStreetMap is a second share-alike lineage; a non-commercial or unlicensed one is refused under any id.
    extra = [*SOURCES, {"id": "season-envelope", "name": "A share-alike product", "licence": "CC BY-SA 4.0", "attribution": "x"},
             {"id": "gauges", "name": "Gauges", "licence": "CC BY-NC 4.0", "attribution": "x"},
             {"id": "maps", "name": "Maps", "licence": "No licence stated by the provider", "attribution": "x"}]
    assert "second share-alike lineage" in problems("x.csv", ["osm", "season-envelope"], extra)[0]
    assert "non-commercial" in problems("x.csv", ["osm", "gauges"], extra)[0]
    assert "no stated licence" in problems("x.csv", ["osm", "maps"], extra)[0]
    for bad in ("hii-rain", "viirs", "unosat-4009"):
        with pytest.raises(exports.ReplayExportError, match="may not feed an export"):
            exports.export_pack(synthetic_context(licence_overrides={"modelled_access_loss_by_hour.csv": ("osm", "worldpop", bad)}))


def test_no_export_column_is_a_legacy_candidate_column_rain_a_score_or_an_action_class() -> None:
    assert exports.LEGACY_ROAD_COLUMNS == ("road_disruption_probability_0_1", "candidate_status", "confidence_class")
    for file in pack().values():
        assert exports.column_problems(file.name, (column.key for column in file.columns)) == []
    problems = exports.column_problems
    for key in exports.LEGACY_ROAD_COLUMNS:
        assert problems("x.csv", [key]) == [f"x.csv: legacy column {key} comes from the superseded candidate lane"]
    for key in ("rain_mm", "hourly_rainfall", "total_mm", "unosat_envelope", "inside_4009", "viirs_flood_km2", "fpps", "accepted_fpps",
                "action_class", "priority_score"):
        assert problems("x.csv", [key]) == [f"x.csv: column {key} is not allowed in an export"], key
    assert problems("x.csv", ["road_id", "length_m", "modelled_stage_m", "estimated_capacity"]) == []
    with pytest.raises(exports.ReplayExportError, match="legacy column candidate_status"):
        exports.csv_bytes("x.csv", [], [exports.Column("candidate_status", "สถานะ", "Legacy")], [])
    roads = pack()["modelled_road_inundation_by_hour"].data.decode("utf-8-sig")
    assert "candidate_closed" not in roads and "0.9" not in roads.split("\n")[-4]


# --- Wording ---------------------------------------------------------------------------------------------------


def test_wording_lint_is_clean_over_every_export_header_and_fails_on_a_seeded_bad_one() -> None:
    files = pack()
    for file in files.values():
        for source, text in header_texts(file):
            assert [finding.describe() for finding in find_violations(text, RULES, source)] == []
    assert find_violations(exports.EXPORT_TIER, RULES) == [] and find_violations(exports.EXPORT_TIER_TH, RULES) == []
    # The same check fails on the names and claims the pack must never carry.
    assert ids(find_violations("# title,Road closure schedule by hour", RULES)) == ["road_schedule"]
    assert ids(find_violations("# title,Cut-off list by subdistrict", RULES)) == ["road_schedule"]
    assert ids(find_violations("# title_th,ตารางปิดถนนรายชั่วโมง", RULES)) == ["road_schedule"]
    assert ids(find_violations("# assumption_1,The plan is the better set; open these shelters first", RULES)) == ["set_ranking", "shelter_directive"]
    assert ids(find_violations("# tier,Flood forecast and official warning for district officers", RULES)) == ["forecast", "warning"]
    seeded = header_texts(files["modelled_road_inundation_by_hour"])[0][1].replace("Modelled road inundation by hour", "Road closure schedule")
    assert ids(find_violations(seeded, RULES)) == ["road_schedule"]


# --- The committed pack ---------------------------------------------------------------------------------------------


def manifest_path() -> Path:
    source = (WEB / "src" / "lib" / "flood-timeline.ts").read_text(encoding="utf-8")
    href = re.search(r'TIMELINE_MANIFEST_URL = "([^"]+)"', source).group(1)
    return WEB / "public" / href.lstrip("/")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(manifest_path().read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def committed(manifest: dict) -> dict[str, dict]:
    """The committed export files by id: the manifest record, the bytes and, for a CSV, the parsed table."""
    out = {}
    for record in manifest["exports"]["files"]:
        data = (WEB / "public" / record["href"].lstrip("/")).read_bytes()
        entry = {"record": record, "data": data}
        if record["media_type"] == "text/csv":
            entry["fields"], entry["keys"], entry["rows"] = exports.read_export_csv(data)
        out[record["id"]] = entry
    return out


def fixture(name: str) -> dict:
    return json.loads((WEB / "src" / "lib" / "__fixtures__" / name).read_text(encoding="utf-8"))


def test_committed_pack_is_exactly_what_the_manifest_lists(manifest: dict, committed: dict[str, dict]) -> None:
    pack_info = manifest["exports"]
    folder = manifest_path().parent / exports.EXPORT_FOLDER
    assert pack_info["folder"] == f"/studies/mae-sai-2024-timeline/{manifest['revision']}/exports/"
    assert sorted(path.name for path in folder.iterdir()) == sorted(entry["record"]["name"] for entry in committed.values())
    assert sorted(entry["record"]["name"] for entry in committed.values()) == sorted([
        "shelter_plan_reported_2024.csv", "shelter_plan_k.csv", "shelter_plan_capacitated.csv", "shelter_sites.geojson",
        "modelled_road_inundation_by_hour.csv", "modelled_access_loss_by_hour.csv", "shelter_candidate_verification_sheet.csv",
        "README_licences.txt"])
    for entry in committed.values():
        record, data = entry["record"], entry["data"]
        assert hashlib.sha256(data).hexdigest() == record["sha256"] and len(data) == record["bytes"], record["name"]
        assert b"\r" not in data and record["licence"] == "ODbL 1.0" and "osm" in record["source_ids"]
        assert not set(record["source_ids"]) & exports.FORBIDDEN_SOURCES
    assert pack_info["file_count"] == len(committed) == 8
    assert pack_info["bytes"] == sum(len(entry["data"]) for entry in committed.values())
    assert pack_info["tier"] == exports.EXPORT_TIER and pack_info["scenario_tier"] == "T1 scenario (model)"
    assert pack_info["confidence"] == "low" and pack_info["confidence_reason"] and pack_info["source_timestamp"] and pack_info["assumptions"]
    block = next(block for block in manifest["evidence_blocks"] if block["id"] == "export_pack")
    assert (block["lane"], block["evidence_tier"], block["temporal_relation"], block["covers"]) == (
        "SCN", "T1 scenario (model)", "event_window_reconstruction", ["exports"])
    assert block["source_timestamp"] == pack_info["source_timestamp"]


def test_committed_headers_carry_the_manifests_time_tier_and_input_hashes(manifest: dict, committed: dict[str, dict]) -> None:
    digest = exports.input_set_sha256(manifest["input_sha256"])
    known = {(row["root"], row["path"]): row["sha256"] for row in manifest["input_sha256"]}
    for entry in committed.values():
        record = entry["record"]
        if record["media_type"] == "text/csv":
            fields = entry["fields"]
            assert entry["data"].startswith(exports.BOM) and int(fields["header_lines"]) == record["header_lines"]
        elif record["media_type"] == "application/geo+json":
            fields = json.loads(entry["data"])["metadata"]
        else:
            fields = dict(re.findall(r"^# ([a-z0-9_]+): (.*)$", entry["data"].decode("utf-8"), re.MULTILINE))
        for key in REQUIRED_FIELDS:
            assert fields.get(key), f"{record['name']} lacks {key}"
        assert fields["generated_at"] == manifest["generated_at"] and fields["study"] == f"{manifest['study_id']} {manifest['revision']}"
        assert fields["tier"] == exports.EXPORT_TIER and fields["operational_status"] == manifest["operational_status"] == "non_operational"
        assert fields["confidence_class"] == manifest["confidence_class"] == "low"
        assert fields["title"] == record["title"]["en"] and fields["title_th"] == record["title"]["th"]
        assert f"input_set_sha256={digest}" in fields["input_receipt"]
        assert f"docs/mae_sai_timeline_{manifest['revision']}_input_receipt.json" in fields["input_receipt"]
        if "input_sha256" in fields:
            for part in fields["input_sha256"].split("; "):
                location, sha256 = part.rsplit("=", 1)
                assert known[tuple(location.split(":", 1))] == sha256, part
        # Licence lineage: only sources the manifest names, one share-alike licence, no rain, no unlicensed product.
        sources = [*manifest["sources"], {"id": "reported-shelters", "licence": "Facts with citations"}]
        assert exports.licence_problems(record["name"], record["source_ids"], sources) == []
        for source_id in record["source_ids"]:
            if source_id != "reported-shelters":
                source = next(source for source in manifest["sources"] if source["id"] == source_id)
                assert source["attribution"] in fields["attribution"], (record["name"], source_id)


def test_committed_files_hold_no_rain_value_no_legacy_column_and_nothing_from_product_4009(manifest: dict, committed: dict[str, dict]) -> None:
    stations = [station["code"] for station in manifest["rainfall"]["stations"]]
    assert stations
    for entry in committed.values():
        record, text = entry["record"], entry["data"].decode("utf-8-sig")
        assert not re.search(r"unosat[-_ ]?4009", record["name"], re.IGNORECASE)
        for code in stations:
            assert code not in text, (record["name"], code)
        if record["media_type"] == "text/csv":
            assert exports.column_problems(record["name"], entry["keys"]) == []
            assert not set(entry["keys"]) & set(exports.LEGACY_ROAD_COLUMNS)
            assert not any(re.search(r"rain|4009|unosat|viirs|fpps|action_class", key) for key in entry["keys"])
        if record["id"] != "readme_licences":
            assert "4009" not in text.replace(exports.NOT_INCLUDED, "").replace(exports.NOT_INCLUDED_TH, ""), record["name"]
    roads = committed["modelled_road_inundation_by_hour"]["data"].decode("utf-8-sig")
    assert "candidate_open" not in roads and "candidate_closed" not in roads and "road_disruption" not in roads


def test_committed_road_table_has_one_row_per_modelled_way_from_the_source_file(committed: dict[str, dict]) -> None:
    source = json.loads((ROOT / "outputs" / "mae_sai_road_risk.geojson").read_text(encoding="utf-8"))["features"]
    classes = ("trunk", "primary", "secondary", "tertiary", "unclassified", "residential")
    ways = {feature["properties"]["road_id"]: feature["properties"] for feature in source if feature["properties"]["road_class"] in classes}
    table = committed["modelled_road_inundation_by_hour"]
    assert table["keys"] == [column.key for column in exports.ROAD_COLUMNS]
    rows = {row["road_id"]: row for row in table["rows"]}
    assert len(rows) == len(table["rows"]) == len(ways) == table["record"]["rows"]
    assert set(rows) == set(ways)
    for road_id, row in rows.items():
        props = ways[road_id]
        assert row["road_name"].lstrip("'") == (props.get("road_name") or ""), road_id
        assert (row["road_class"], row["bridge_flag"], row["tambon_id"]) == (props["road_class"], "yes" if props["bridge_flag"] else "no", props["subdistrict_id"])
        first, again, count = (row[f"modelled_{key}"] for key in ("first_impassable_hour", "passable_again_hour", "impassable_hours"))
        if first == "":
            assert again == "" and count == "0" and row["modelled_first_impassable_local_time"] == ""
        else:
            assert 0 <= int(first) < 264 and int(count) >= 1
            assert row["modelled_first_impassable_local_time"] == exports.hour_local_time(int(first), EVENT_START)
            if again != "":
                assert int(first) < int(again) <= 263 and int(count) <= int(again) - int(first)
                assert row["modelled_passable_again_local_time"] == exports.hour_local_time(int(again), EVENT_START)
    assert sum(1 for row in rows.values() if row["modelled_first_impassable_hour"] != "") > 100


def test_committed_road_hours_agree_with_the_road_state_parity_fixture(committed: dict[str, dict]) -> None:
    parity = fixture("mae-sai-road-state-hourly.json")
    hours = parity["hours"]
    assert parity["columns"] == ["hour", "stage_m", "road_km_wet", "road_km_impassable"] and len(hours) == 264
    rows = committed["modelled_road_inundation_by_hour"]["rows"]
    impassable = np.zeros(264, dtype=int)
    for row in rows:
        if row["modelled_first_impassable_hour"] == "":
            continue
        first = int(row["modelled_first_impassable_hour"])
        again = int(row["modelled_passable_again_hour"]) if row["modelled_passable_again_hour"] != "" else 264
        assert int(row["modelled_impassable_hours"]) == again - first  # The stage rises once and falls once: one spell per way.
        impassable[first:again] += 1
    # At every replay hour, some way is impassable in the table exactly when the page counts impassable road length.
    for hour, _, _, km_impassable in hours:
        assert (impassable[hour] > 0) == (km_impassable > 0), hour
    with_water = [hour for hour, _, _, km in hours if km > 0]
    firsts = [int(row["modelled_first_impassable_hour"]) for row in rows if row["modelled_first_impassable_hour"] != ""]
    agains = [int(row["modelled_passable_again_hour"]) for row in rows if row["modelled_passable_again_hour"] != ""]
    assert min(firsts) == with_water[0] and max(agains) == with_water[-1] + 1
    # The hour with the most impassable ways is an hour of the page's largest impassable length.
    peak_km = max(km for _, _, _, km in hours)
    assert hours[int(np.argmax(impassable))][3] == peak_km
    # The access table's stage column is the fixture's stage at every hour: one hourly grid for the page and the pack.
    access = committed["modelled_access_loss_by_hour"]["rows"]
    stage_by_hour = {int(row["replay_hour"]): float(row["modelled_stage_m"]) for row in access}
    assert stage_by_hour == {hour: round(stage, 3) for hour, stage, _, _ in hours}


def test_committed_access_table_agrees_with_the_equity_access_parity_fixture(manifest: dict, committed: dict[str, dict]) -> None:
    table = committed["modelled_access_loss_by_hour"]
    knee = manifest["shelters"]["knee_k"]
    assert table["keys"] == [column.key for column in exports.access_columns(knee)] and table["fields"]["knee_k"] == str(knee)
    rows = table["rows"]
    tambons = manifest["access"]["tambons"]
    assert len(rows) == len(tambons) * 264 == table["record"]["rows"]
    assert sorted({row["tambon_id"] for row in rows}) == sorted(tambons)
    assert all(THAI.search(row["tambon_name_th"]) and row["tambon_name_en"] for row in rows)
    assert rows[0]["local_time"] == EVENT_START and rows[263]["local_time"] == "2024-09-19T23:00:00+07:00"
    parity = fixture("mae-sai-equity-access-parity.json")
    for label, set_id in (("reported_2024", "reported_2024"), ("knee_plan", f"plan_{knee}")):
        comparison = next(item for item in parity["set_comparison"] if item["set"] == set_id and item["scope"] == "all")
        by_hour: dict[int, list[float]] = {}
        baseline = 0.0
        for row in rows:
            by_hour.setdefault(int(row["replay_hour"]), []).append(float(row[f"{label}_lost_access"]))
            if row["replay_hour"] == "0":
                baseline += float(row[f"{label}_within_reach_before_flood"])
                assert float(row[f"{label}_lost_access"]) == 0.0
        # Eight subdistrict figures, each rounded to one decimal, against the fixture's unrounded district figure.
        assert baseline == pytest.approx(comparison["baseline"], abs=0.45)
        for hour, _, lost, _ in comparison["hours"]:
            assert sum(by_hour[hour]) == pytest.approx(lost, abs=0.45), (set_id, hour)
        assert max(sum(values) for values in by_hour.values()) == pytest.approx(comparison["at_peak"]["lost"], abs=0.45)
    residents = sum(float(row["residents"]) for row in rows if row["replay_hour"] == "0")
    assert residents == pytest.approx(manifest["access"]["totals"]["population"], abs=1.0)
    for row in rows:
        for label in ("reported_2024", "knee_plan"):
            assert float(row[f"{label}_lost_access"]) <= float(row[f"{label}_within_reach_before_flood"]) <= float(row["residents"]) + 0.05


def test_committed_shelter_tables_repeat_the_manifests_plans_and_no_listed_capacity(manifest: dict, committed: dict[str, dict]) -> None:
    shelters = manifest["shelters"]
    sites = {site["id"]: site for site in shelters["candidates"]}
    plan = committed["shelter_plan_k"]["rows"]
    assert [row["candidate_id"] for row in plan] == [entry["candidate_id"] for entry in shelters["plan"]]
    assert [row["rank"] for row in plan] == [str(index) for index in range(1, len(plan) + 1)]
    assert [row["in_knee_plan"] for row in plan] == ["yes"] * shelters["knee_k"] + ["no"] * (len(plan) - shelters["knee_k"])
    core = set(shelters["robustness"]["core_by_k"][shelters["knee_k"] - 1])
    assert {row["candidate_id"] for row in plan if row["in_robust_core"] == "yes"} == core
    for row, entry in zip(plan, shelters["plan"]):
        site = sites[row["candidate_id"]]
        assert (float(row["lat"]), float(row["lon"]), row["kind"]) == (site["lat"], site["lon"], site["kind"])
        assert float(row["cumulative_share"]) == entry["cumulative_share"]
        assert row["estimated_capacity"] == ("" if site["capacity_est"] is None else str(site["capacity_est"]))
    capacity = committed["shelter_plan_capacitated"]["rows"]
    assert [row["candidate_id"] for row in capacity] == [entry["candidate_id"] for entry in shelters["capacitated"]["plan"]]
    for row, entry in zip(capacity, shelters["capacitated"]["plan"]):
        for bound in ("lower", "upper"):
            assert [int(row[f"{bound}_{key}"]) for key in ("capacity", "load", "cumulative_fit", "overflow")] == [
                entry[bound][key] for key in ("capacity", "load", "served", "overflow")]
            assert int(row[f"{bound}_load"]) <= int(row[f"{bound}_capacity"])
    reported = committed["shelter_plan_reported_2024"]["rows"]
    assert [row["site_id"] for row in reported] == [site["id"] for site in shelters["reported"]]
    assert committed["shelter_plan_reported_2024"]["record"]["lanes"] == ["REP", "SCN"]
    text = committed["shelter_plan_reported_2024"]["data"].decode("utf-8-sig")
    for site in shelters["reported"]:
        figure = site.get("reported_capacity_or_occupancy")
        assert not figure or figure not in text
    assert "Occupancy:" not in text and "municipal list" not in text
    layer = json.loads(committed["shelter_sites"]["data"])
    located = [site for site in shelters["reported"] if site["lat"] is not None]
    assert len(layer["features"]) == len(shelters["candidates"]) + len(located) == committed["shelter_sites"]["record"]["rows"]
    assert all(list(feature["properties"]) == [column.key for column in exports.SITE_FIELDS] for feature in layer["features"])


def test_committed_verification_sheet_is_blank_and_the_manifest_says_not_conducted(manifest: dict, committed: dict[str, dict]) -> None:
    sheet = committed["shelter_candidate_verification_sheet"]
    eligible = sorted(site["id"] for site in manifest["shelters"]["candidates"] if site["eligible"])
    assert sheet["keys"] == [column.key for column in exports.SHEET_COLUMNS]
    assert [row["candidate_id"] for row in sheet["rows"]] == eligible
    for row in sheet["rows"]:
        assert all(row[column.key] == "" for column in exports.SHEET_CHECKER), row["candidate_id"]
    fingerprint = exports.candidate_set_sha256(manifest["shelters"]["candidates"])
    assert sheet["fields"]["candidate_set_sha256"] == fingerprint
    assert sheet["fields"]["verification_status"] == "not_conducted"
    assert sheet["fields"]["verification_label"] == "Checked by <role> on <date>; not an official shelter register"
    check = manifest["shelters"]["verification"]
    if (ROOT / "outputs" / "mae_sai_shelter_validation.json").exists():
        assert check["status"] == "conducted" and check["checked"]
    else:  # No sheet has been returned: no result may be stated.
        assert check["status"] == "not_conducted" and check["checked"] == [] and "not conducted" in check["statement"]
        assert "counts" not in check and "returned_file_sha256" not in check
    assert (check["candidate_set_sha256"], check["candidates_listed"], check["sheet"]) == (fingerprint, len(eligible), "shelter_candidate_verification_sheet")
    assert check["label_template"] == exports.VERIFICATION_LABEL
    block = next(block for block in manifest["evidence_blocks"] if block["id"] == "shelter_candidate_check")
    assert (block["lane"], block["covers"]) == ("REP", ["shelters.verification"]) and "not an official shelter register" in block["evidence_tier"]


def test_wording_lint_is_clean_over_every_committed_export_header(committed: dict[str, dict]) -> None:
    checked = 0
    for entry in committed.values():
        record = entry["record"]
        if record["media_type"] == "text/csv":
            lines = entry["data"].decode("utf-8-sig").split("\n")
            texts = ["\n".join(lines[:record["header_lines"] + 1])]
        elif record["media_type"] == "application/geo+json":
            texts = [json.dumps(json.loads(entry["data"])["metadata"], ensure_ascii=False)]
        else:
            texts = [entry["data"].decode("utf-8")]
        texts += [record["name"], record["title"]["en"], record["title"]["th"]]
        for text in texts:
            findings = find_violations(text, RULES, record["name"])
            assert [finding.describe() for finding in findings] == []
            checked += 1
    assert checked == 8 * 4
