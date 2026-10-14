"""The committed records of the label check of the THEOS-2 water rule."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from floodguard import theos2_water_labels as wl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/theos2_water_labels"
SAMPLE = json.loads((OUT / "sample_v1.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "scripts/theos2_water_label_page.html").read_text(encoding="utf-8")
SHA = re.compile(r"^[0-9a-f]{64}$")


def rule_summary(chip: str) -> dict:
    if chip == "sukhothai":
        record = json.loads((ROOT / "outputs/theos2_cross_check/sukhothai_20250730_reference_v1.json").read_text(encoding="utf-8"))
        return record["optical_water_rule"]
    record = json.loads((ROOT / "outputs/radar_detection_improvement/held_out_reference_v1.json").read_text(encoding="utf-8"))
    return record["chips"][chip]["optical_water_rule"]


def test_the_draw_carries_the_fields_of_every_output() -> None:
    assert SAMPLE["schema"] == "floodguard.theos2_water_labels.sample.v1"
    assert SAMPLE["source_timestamp"] and SAMPLE["generated_at_utc"].endswith("Z")
    assert SAMPLE["confidence_class"] == "low" and SAMPLE["confidence_basis"]
    assert SAMPLE["operational_status"] == "non_operational"
    assert SAMPLE["official_warning"] is False and SAMPLE["can_feed_decision_layer"] is False
    assert SAMPLE["plan"]["path"] == "docs/proposal_execution/theos2_water_label_check_plan_v1.md"
    assert (ROOT / SAMPLE["plan"]["path"]).exists() and SHA.match(SAMPLE["plan"]["sha256"])
    assert SAMPLE["limits"]


def test_the_draw_is_the_one_of_the_plan() -> None:
    assert SAMPLE["seed"] == wl.SEED and SAMPLE["edge_distance_px"] == wl.EDGE_PX
    assert SAMPLE["groups"] == list(wl.GROUPS) and SAMPLE["labels"] == list(wl.LABELS)
    assert list(SAMPLE["chips"]) == list(wl.CHIPS)
    assert SAMPLE["points"] == 300 and SAMPLE["practice_points"] == 6
    for chip, record in SAMPLE["chips"].items():
        sizes, points = record["pixels_by_group"], record["points_by_group"]
        assert sum(sizes.values()) == record["pixels_2m"]
        assert points == wl.points_per_group(sizes, wl.PLANNED_POINTS[chip])
        assert record["points"] == sum(wl.PLANNED_POINTS[chip])
        assert all(points[group] <= sizes[group] for group in wl.GROUPS)
        assert SHA.match(record["sha256"])
    assert SAMPLE["chips"]["chip_001"]["points_by_group"]["unobservable"] == 0


def test_the_groups_are_cut_from_the_rule_of_the_committed_records() -> None:
    for chip, record in SAMPLE["chips"].items():
        summary, sizes = rule_summary(chip), record["pixels_by_group"]
        assert sizes["water_inside"] + sizes["water_edge"] == summary["water_pixels"]
        assert sizes["dropped_small_object"] == summary["pixels_dropped_by_object_rule"]
        assert sizes["unobservable"] == summary["pixels"] - summary["observable_pixels"]
        assert record["ndwi_threshold_applied"] == summary["ndwi_threshold_applied"]


def test_the_draw_tells_nobody_where_a_point_is() -> None:
    text = json.dumps(SAMPLE)
    assert '"row"' not in text and '"column"' not in text and "p001" not in text
    assert SAMPLE["key_outside_git"]["sha256"] == SAMPLE["sample_id"] and SHA.match(SAMPLE["sample_id"])
    assert SHA.match(SAMPLE["page_outside_git"]["sha256"])
    assert SAMPLE["page_outside_git"]["holds_the_answer_of_the_rule"] is False
    # The page with its pictures never enters Git.
    assert not list(OUT.glob("*.html"))


def test_the_page_template_holds_no_answer_and_is_the_one_the_draw_used() -> None:
    for token in ("/*SAMPLE_ID*/", "/*PRACTICE*/[]", "/*POINTS*/[]"):
        assert TEMPLATE.count(token) == 1
    for group in wl.GROUPS:
        assert group not in TEMPLATE
    for label in wl.LABELS:
        assert f'"{label}"' in TEMPLATE
    digest = hashlib.sha256((ROOT / "scripts/theos2_water_label_page.html").read_bytes()).hexdigest()
    assert SAMPLE["page_outside_git"]["template"]["sha256"] == digest
    assert "http://" not in TEMPLATE and "https://" not in TEMPLATE


def test_the_key_and_the_labels_enter_git_only_with_the_figures() -> None:
    result, key = OUT / "result_v1.json", OUT / "key_v1.json"
    labels = sorted(OUT.glob("labels_*.json"))
    if not result.exists():
        assert not key.exists() and labels == [] and SAMPLE["labels_received"] == 0
        return
    assert hashlib.sha256(key.read_bytes()).hexdigest() == SAMPLE["key_outside_git"]["sha256"]
    assert len(labels) in (2, 3)
    figures = json.loads(result.read_text(encoding="utf-8"))
    assert figures["official_warning"] is False and figures["confidence_class"] == "low"
    assert len(json.loads(key.read_text(encoding="utf-8"))["points"]) == SAMPLE["points"]
